"""Windows portable screenshot/OCR UI. All image processing stays in this process."""
import ctypes
import io
import json
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageGrab, ImageTk

from desktop.local_translation import LocalTranslation
from desktop.privacy import install_network_guard
from desktop.editor import ScreenshotEditor
from desktop.retention import CacheRetention
from desktop.translation_bridge import start_translation_bridge
from desktop.floating import FloatingButton
from desktop.hotkeys import Hotkeys, IDS, DEFAULTS, event_hotkey, WindowsHotkeyPump
from services.ocr.server import create_engine, Handler, ThreadingHTTPServer

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def region(start, end, width, height):
    x1, y1 = start
    x2, y2 = end
    box = (max(0, min(x1, x2)), max(0, min(y1, y2)), min(width, max(x1, x2)), min(height, max(y1, y2)))
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 3 or h < 3 or w * h > 16_000_000:
        raise ValueError("请选择清晰的区域，最大 1600 万像素")
    return box


class Selection:
    def __init__(self, root, image, origin, done):
        self.image, self.done, self.start = image, done, None
        self.origin = origin
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        x, y = origin
        self.window.geometry(f"{image.width}x{image.height}{x:+d}{y:+d}")
        # Tk's negative geometry coordinates are right/bottom offsets, not virtual
        # desktop coordinates. Position explicitly for monitors left of primary.
        if sys.platform == "win32":
            from ctypes import wintypes
            self.window.update_idletasks()
            user = ctypes.windll.user32
            user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user.GetAncestor.restype = wintypes.HWND
            user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            handle = user.GetAncestor(self.window.winfo_id(), 2)
            user.SetWindowPos(handle, wintypes.HWND(-1), x, y, image.width, image.height, 0x10)
        self.canvas = tk.Canvas(self.window, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.create_rectangle(10, 10, 490, 48, fill="#132941", outline="")
        self.canvas.create_text(24, 29, anchor="w", fill="white", text="拖动框选 · 松开完成 · Esc / 右键取消", font=("Microsoft YaHei UI", 13))
        self.outline = None
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.move)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Button-3>", lambda _e: self.finish(None))
        self.window.bind("<Escape>", lambda _e: self.finish(None))
        self.window.focus_force()
        self.window.grab_set()

    def press(self, event):
        self.start = (event.x, event.y)
        if self.outline:
            self.canvas.delete(self.outline)
        self.outline = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#168bff", width=3)

    def move(self, event):
        if self.start:
            self.canvas.coords(self.outline, *self.start, event.x, event.y)

    def release(self, event):
        if self.start:
            try:
                box = region(self.start, (event.x, event.y), self.image.width, self.image.height)
                self.finish(self.image.crop(box), (self.origin[0] + box[0], self.origin[1] + box[1]))
            except ValueError:
                self.finish(None)

    def finish(self, crop, position=None):
        self.window.grab_release()
        self.window.destroy()
        self.image.close()
        self.image = None
        self.photo = None
        self.done(crop, position)


class App:
    def __init__(self, root):
        self.root, self.image, self.photo = root, None, None
        self.engine, self.api, self.translate_api, self.busy, self.selection, self.editor = None, None, None, False, None, None
        self.generation, self.closed = 0, False
        self.ocr_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.results = queue.Queue()
        self.translation = LocalTranslation(ROOT)
        self.retention = CacheRetention()
        self.retention.cleanup()
        self.floating = FloatingButton(
            root,
            self.capture,
            self.show_main,
            self.retention.root,
            self.floating_hidden,
        )
        root.title("Charlie Translate · 本地截图识字")
        root.geometry("980x840")
        root.minsize(820, 760)
        root.configure(bg="#eef3f9")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f9")
        style.configure("TLabel", background="#eef3f9", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(9, 6))
        style.configure("Primary.TButton", background="#2563eb", foreground="white", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#cbd5e1")])
        style.configure("TButton", background="#ffffff", borderwidth=0, relief="flat")
        style.map("TButton", background=[("active", "#e2e8f0")])
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        footer = ttk.Frame(frame)
        footer.pack(side="bottom", fill="x")
        ttk.Label(frame, text="Charlie Translate", font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
        ttk.Label(frame, text="截图与增强识字留在本机 · 翻译只连接本机服务 · 不自动保存图片").pack(anchor="w", pady=(3, 12))
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.controls = []
        for name, action in [("框选截图", self.capture), ("打开图片", self.open_image), ("增强识字", self.recognize), ("保存截图", self.save_image), ("复制截图", self.copy_image), ("清空", self.clear)]:
            button = ttk.Button(bar, text=name, command=action)
            if name == "框选截图":
                button.configure(style="Primary.TButton")
            button.pack(side="left", padx=(0, 6))
            self.controls.append(button)
        self.preview = tk.Label(frame, bg="#dce6f0", text="框选桌面、其他软件或浏览器，也可以打开本机图片", font=("Microsoft YaHei UI", 12), fg="#38516a")
        self.preview.pack(fill="x", pady=12, ipady=4)
        panels = ttk.Frame(frame)
        panels.pack(fill="both", expand=True)
        panels.columnconfigure((0, 1), weight=1)
        panels.rowconfigure(1, weight=1)
        self.original_heading = tk.StringVar(value="原文 · 可以编辑")
        ttk.Label(panels, textvariable=self.original_heading).grid(row=0, column=0, sticky="w")
        ttk.Label(panels, text="简体中文译文").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.original = tk.Text(panels, width=35, height=6, wrap="word", font=("Microsoft YaHei UI", 12), padx=10, pady=10, undo=True)
        self.translated = tk.Text(panels, width=35, height=6, wrap="word", font=("Microsoft YaHei UI", 12), padx=10, pady=10, state="disabled")
        self.original.bind("<Control-Return>", self.translate_shortcut)
        self.original.grid(row=1, column=0, sticky="nsew", pady=6)
        self.translated.grid(row=1, column=1, sticky="nsew", pady=6, padx=(12, 0))
        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(6, 10))
        self.translate_button = ttk.Button(actions, text="翻译为中文（本机）", command=self.translate, style="Primary.TButton")
        self.translate_button.pack(side="left")
        ttk.Button(actions, text="复制原文", command=lambda: self.copy_text(self.original)).pack(side="left", padx=6)
        ttk.Button(actions, text="复制译文", command=lambda: self.copy_text(self.translated)).pack(side="left")
        self.on_top = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions,text="置顶主窗口",variable=self.on_top,command=lambda: self.root.attributes("-topmost",self.on_top.get())).pack(side="right")
        self.floating_enabled = tk.BooleanVar(value=self.floating.default_enabled())
        ttk.Checkbutton(actions,text="悬浮截图按钮",variable=self.floating_enabled,command=self.toggle_floating).pack(side="right", padx=(0, 10))
        retention_bar = ttk.Frame(footer)
        retention_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(retention_bar, text="应用缓存有效期").pack(side="left")
        self.retention_days = tk.StringVar(value=str(self.retention.days))
        retention = ttk.Combobox(
            retention_bar,
            width=10,
            state="readonly",
            textvariable=self.retention_days,
            values=("0", "1", "3", "7", "14", "30"),
        )
        retention.pack(side="left", padx=6)
        ttk.Label(retention_bar, text="天（0=仅本次；默认7天。手动保存的文件不自动删除）").pack(side="left")
        retention.bind("<<ComboboxSelected>>", self.change_retention)
        ttk.Button(retention_bar, text="快捷键设置", command=self.configure_hotkeys).pack(side="right")
        self.cache_location = tk.StringVar(value=str(self.retention.cache_dir))
        self.save_location = tk.StringVar(value=str(self.retention.save_directory))
        for label, variable, kind in (("缓存位置", self.cache_location, "cache"), ("默认保存位置", self.save_location, "save")):
            row = ttk.Frame(footer)
            row.pack(fill="x", pady=(0, 6))
            ttk.Label(row, text=label, width=13).pack(side="left")
            ttk.Entry(row, textvariable=variable, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
            ttk.Button(row, text="打开文件夹", command=lambda k=kind: self.open_directory(k)).pack(side="left", padx=3)
            ttk.Button(row, text="修改路径", command=lambda k=kind: self.choose_directory(k)).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(3, 6))
        self.task_serial = 0
        self.status = tk.StringVar(value="正在加载增强 OCR 模型…")
        ttk.Label(footer, textvariable=self.status, wraplength=880).pack(anchor="w")
        self.submit(self.initialize, self.ready)
        self.hotkey_api = WindowsHotkeyPump() if sys.platform == "win32" else None
        self.hotkeys = Hotkeys(self.retention.root, self.hotkey_api)
        self.hotkeys.start()
        self.hotkey = "capture" in self.hotkeys.active
        if sys.platform == "win32":
            root.after(100, self.poll_hotkey)
        if self.floating_enabled.get():
            self.floating.show()
        root.after(80, self.poll)
        root.after(6 * 60 * 60 * 1000, self.cleanup_cache)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def initialize(self):
        try:
            self.translate_api = start_translation_bridge(self.translation)
        except OSError:
            self.translate_api = None
        engine = create_engine(ROOT / "models")
        try:
            self.api = ThreadingHTTPServer(("127.0.0.1", 8990), Handler)
            self.api.engine = engine
            self.api.ocr_lock = self.ocr_lock
            threading.Thread(target=self.api.serve_forever, daemon=True).start()
        except OSError:
            self.api = None
        return engine

    def ready(self, engine):
        self.engine = engine
        ocr_note = "浏览器可共用本机 OCR。" if self.api else "8990 端口被占用，桌面识字仍可用。"
        trans_note = "浏览器网页翻译可共用 EXE 内置离线翻译。" if self.translate_api else "8992 端口被占用，浏览器无法共用 EXE 翻译。"
        shortcut = self.shortcut_status()
        self.status.set("增强 OCR 就绪。" + shortcut + ocr_note + trans_note)

    def submit(self, work, done):
        if self.busy:
            return
        self.busy = True
        self.task_serial += 1
        self.task_started = time.perf_counter()
        self.task_caption = self.status.get()
        self.progress.start(12)
        self.root.after(250, lambda serial=self.task_serial: self.update_task_progress(serial))
        self.enable(False)
        generation = self.generation
        def run():
            try:
                self.results.put((generation, done, work(), None))
            except Exception as error:
                self.results.put((generation, done, None, str(error)))
        self.executor.submit(run)

    def update_task_progress(self, serial):
        if self.closed or not self.busy or serial != self.task_serial:
            return
        elapsed = time.perf_counter() - self.task_started
        self.status.set(f"{self.task_caption}  已用 {elapsed:.1f} 秒")
        self.root.after(250, lambda: self.update_task_progress(serial))

    def enable(self, value):
        state = "normal" if value else "disabled"
        for button in self.controls + [self.translate_button]:
            button.configure(state=state)
        self.original.configure(state=state)

    def poll(self):
        while not self.results.empty():
            generation, done, value, error = self.results.get_nowait()
            self.busy = False
            self.progress.stop()
            self.enable(True)
            if generation == self.generation:
                if error:
                    self.original_heading.set("原文 · 可以编辑")
                    self.capture_auto_translate = False
                    self.status.set("操作失败：" + error)
                else:
                    done(value)
        if not self.closed:
            self.root.after(80, self.poll)

    def translate_shortcut(self, _event=None):
        self.translate()
        return "break"

    def shortcut_status(self):
        labels = {"capture": "截图", "translate": "截图翻译"}
        return " ".join(f"{labels[name]}：{value}" + ("。" if name in self.hotkeys.active else "（被占用，请在快捷键设置中修改）。") for name, value in self.hotkeys.values.items())

    def configure_hotkeys(self):
        if getattr(self, "hotkey_dialog", None) and self.hotkey_dialog.winfo_exists():
            self.hotkey_dialog.lift()
            return
        self.hotkeys.close()
        dialog = self.hotkey_dialog = tk.Toplevel(self.root)
        dialog.title("快捷键设置")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="全局快捷键", font=("Microsoft YaHei UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        variables = {}
        for row, (name, label) in enumerate((("capture", "截图与标注"), ("translate", "截图后自动翻译")), 1):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 20), pady=6)
            variables[name] = tk.StringVar(value=self.hotkeys.values[name])
            entry = ttk.Entry(body, textvariable=variables[name], width=24, state="readonly")
            entry.grid(row=row, column=1, pady=6)
            entry.bind("<KeyPress>", lambda event, variable=variables[name]: self.record_hotkey(event, variable))
            entry.bind("<Button-1>", lambda _event, widget=entry: widget.focus_set())
        ttk.Label(body, text="点击输入框，然后直接按所需快捷键\nF1–F12 可单独使用，也支持 Ctrl / Alt / Shift 组合\n在主窗口原文框中，Ctrl+Enter 翻译当前文字。", justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=12)
        feedback = tk.StringVar()
        ttk.Label(body, textvariable=feedback, foreground="#b91c1c", wraplength=390).grid(row=4, column=0, columnspan=2, sticky="w")
        def save():
            try:
                self.hotkeys.apply({name: value.get() for name, value in variables.items()})
            except (ValueError, OSError) as error:
                feedback.set(str(error))
                return
            self.hotkey = "capture" in self.hotkeys.active
            self.status.set("快捷键已保存，立即生效。" + self.shortcut_status())
            dialog.destroy()
        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="恢复默认", command=lambda: [variables[name].set(value) for name, value in DEFAULTS.items()]).pack(side="left")
        ttk.Button(buttons, text="保存", style="Primary.TButton", command=save).pack(side="right")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=6)
        def restore(event):
            if event.widget is dialog and not self.closed:
                if not self.hotkeys.active:
                    self.hotkeys.start()
                self.hotkey = "capture" in self.hotkeys.active
        dialog.bind("<Destroy>", restore)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def record_hotkey(self, event, variable):
        if event.keysym in ("Tab", "ISO_Left_Tab", "Escape"):
            return None
        try:
            state = event.state
            if sys.platform == "win32":
                # Tk Mod1 (0x8) is NumLock on Windows. Query actual pressed keys.
                state = sum(mask for key, mask in ((0x11, 0x4), (0x12, 0x20000), (0x10, 0x1)) if ctypes.windll.user32.GetKeyState(key) & 0x8000)
            variable.set(event_hotkey(event, state))
        except ValueError:
            pass
        return "break"

    def poll_hotkey(self):
        while not self.hotkey_api.events.empty():
            identifier = self.hotkey_api.events.get_nowait()
            if getattr(self, "hotkey_dialog", None) and self.hotkey_dialog.winfo_exists():
                continue
            if identifier == IDS["capture"]:
                self.capture()
            elif identifier == IDS["translate"]:
                self.capture(translate=True)
        if not self.closed:
            self.root.after(30, self.poll_hotkey)

    def capture(self, translate=False):
        if self.busy or self.selection or self.editor:
            return
        self.capture_translate = translate
        self.capture_auto_translate = False
        self.capture_main_visible = self.root.state() != "withdrawn"
        if self.floating and self.floating_enabled.get():
            self.floating.suspend()
        self.root.withdraw()
        self.root.after(180, self.select_screen)

    def select_screen(self):
        try:
            image = ImageGrab.grab(all_screens=True)
            origin = (ctypes.windll.user32.GetSystemMetrics(76), ctypes.windll.user32.GetSystemMetrics(77))
            self.selection = Selection(self.root, image, origin, self.selected)
        except Exception as error:
            self.root.deiconify()
            if self.floating and self.floating_enabled.get():
                self.floating.resume()
            self.status.set("截图失败：" + str(error))

    def selected(self, image, position=None):
        self.selection = None
        if image and getattr(self, "capture_translate", False):
            self.set_image(image)
            self.copy_image()
            self.capture_auto_translate = True
            self.show_main()
            if self.floating and self.floating_enabled.get():
                self.floating.resume()
            self.recognize()
        elif image:
            self.set_image(image.copy())
            self.copy_image()
            self.editor = ScreenshotEditor(
                self.root,
                image,
                self.editor_done,
                self.editor_cancelled,
                position=position,
            )
        else:
            if getattr(self, "capture_main_visible", True):
                self.show_main()
            if self.floating and self.floating_enabled.get():
                self.floating.resume()
            self.status.set("截图已取消，未识字、未保存。")

    def editor_done(self, image, action="copy"):
        self.editor = None
        self.set_image(image)
        copied = self.copy_image()
        if self.floating and self.floating_enabled.get():
            self.floating.resume()
        if copied:
            self.status.set("截图标注完成并已自动复制，可直接 Ctrl+V 粘贴；隐私遮盖已永久写入像素。")
        if action == "ocr":
            self.capture_auto_translate = True
            self.show_main()
            self.recognize()

    def editor_cancelled(self):
        self.editor = None
        if getattr(self, "capture_main_visible", True):
            self.show_main()
        if self.floating and self.floating_enabled.get():
            self.floating.resume()
        self.status.set("已退出标注，框选图片已自动复制，未保存文件。")

    def set_image(self, image):
        if image.width * image.height > 16_000_000:
            image.close()
            raise ValueError("图片过大，请选择较小区域")
        if self.image:
            self.image.close()
        self.image = image.convert("RGB")
        image.close()
        thumb = self.image.copy()
        thumb.thumbnail((860, 170))
        self.photo = ImageTk.PhotoImage(thumb)
        thumb.close()
        self.preview.configure(image=self.photo, text="", pady=0)
        self.original.delete("1.0", "end")
        self.original.edit_reset()
        self.set_translation("")
        self.status.set("图片已在内存中预览。检查内容后点击增强识字。")

    def open_image(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            try:
                with Image.open(path) as image:
                    self.set_image(image.copy())
            except Exception as error:
                self.status.set("打开失败：" + str(error))

    def recognize(self):
        if not self.image or not self.engine:
            self.capture_auto_translate = False
            self.status.set("请先选择图片，并等待模型加载。")
            return
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        raw = buffer.getvalue()
        self.original_heading.set("原文 · 正在识字，请稍候…")
        self.status.set("正在本机识字，图片不会发送给翻译服务…")
        def work():
            if not self.ocr_lock.acquire(blocking=False):
                raise ValueError("浏览器正在识字，请稍后再试")
            try:
                result = self.engine(raw)
                return "\n".join(result.txts if result.txts is not None else ())
            finally:
                self.ocr_lock.release()
        self.submit(work, self.recognized)

    def recognized(self, text):
        self.original_heading.set("原文 · 可以编辑")
        self.original.delete("1.0", "end")
        self.original.insert("1.0", text)
        self.set_translation("")
        self.status.set("识字完成。可编辑原文；点击翻译只向本机发送文字。" if text else "未识别到文字，请选择清晰区域。")
        if getattr(self, "capture_auto_translate", False):
            self.capture_auto_translate = False
            if text:
                self.translate()

    def set_translation(self, text):
        self.translated.configure(state="normal")
        self.translated.delete("1.0", "end")
        self.translated.insert("1.0", text)
        self.translated.configure(state="disabled")

    def translate(self):
        if self.busy:
            return
        text = self.original.get("1.0", "end-1c")
        self.status.set("正在本机翻译为中文…")
        self.submit(lambda: self.translation.translate(text), self.translation_done)

    def translation_done(self, text):
        self.set_translation(text)
        self.status.set("本机翻译完成。")

    def copy_text(self, widget):
        value = widget.get("1.0", "end-1c")
        if value:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.status.set("文字已复制到系统剪贴板。")

    def save_image(self):
        if not self.image:
            return
        self.retention.save_directory.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(defaultextension=".png", initialdir=str(self.retention.save_directory), initialfile="Charlie-screenshot.png", filetypes=[("PNG", "*.png")])
        if path:
            try:
                drive_type = ctypes.windll.kernel32.GetDriveTypeW
                drive_type.argtypes = [ctypes.c_wchar_p]
                drive_type.restype = ctypes.c_uint
                if path.startswith("\\\\") or drive_type(str(Path(path).anchor)) == 4:
                    raise ValueError("仅允许保存到本机磁盘，不保存到网络共享")
                self.image.save(path, format="PNG")
                self.status.set("截图已保存到你选择的本机文件。")
            except (OSError, ValueError) as error:
                self.status.set("保存失败：" + str(error))

    def copy_image(self):
        if not self.image:
            return
        # Windows CF_DIB owns the allocated memory after SetClipboardData succeeds.
        stream = io.BytesIO()
        self.image.save(stream, format="BMP")
        data = stream.getvalue()[14:]
        kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
        from ctypes import wintypes
        kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        user.OpenClipboard.argtypes = [wintypes.HWND]
        kernel.GlobalAlloc.restype = ctypes.c_void_p
        kernel.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel.GlobalLock.restype = ctypes.c_void_p
        kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel.GlobalFree.argtypes = [ctypes.c_void_p]
        user.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user.SetClipboardData.restype = ctypes.c_void_p
        memory = kernel.GlobalAlloc(0x2, len(data))
        opened = False
        try:
            pointer = kernel.GlobalLock(memory)
            if not pointer:
                raise OSError("无法分配剪贴板内存")
            ctypes.memmove(pointer, data, len(data))
            kernel.GlobalUnlock(memory)
            if not user.OpenClipboard(self.root.winfo_id()):
                raise OSError("剪贴板被占用，请重试")
            opened = True
            user.EmptyClipboard()
            if not user.SetClipboardData(8, memory):
                raise OSError("无法复制图片")
            memory = None
            self.status.set("图片已复制到系统剪贴板。")
            return True
        except OSError as error:
            self.status.set(str(error))
            return False
        finally:
            if opened:
                user.CloseClipboard()
            if memory:
                kernel.GlobalFree(memory)

    def clear(self):
        if self.busy:
            return
        self.generation += 1
        if self.image:
            self.image.close()
        self.image, self.photo = None, None
        self.preview.configure(image="", text="已清空图片与文字")
        self.original.delete("1.0", "end")
        self.original.edit_reset()
        self.set_translation("")
        self.status.set("已清空，不保留截图历史。")

    def show_main(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def floating_hidden(self):
        if hasattr(self, "floating_enabled"):
            self.floating_enabled.set(False)

    def toggle_floating(self):
        if not self.floating:
            return
        if self.floating_enabled.get():
            self.floating.set_enabled(True)
            self.floating.show()
        else:
            self.floating.hide()

    def change_retention(self, _event=None):
        try:
            self.retention.set_days(int(self.retention_days.get()))
            self.status.set(f"应用缓存有效期已设为 {self.retention.days} 天；过期缓存已清理。")
        except ValueError as error:
            self.status.set("缓存设置失败：" + str(error))

    def open_directory(self, kind):
        directory = self.retention.cache_dir if kind == "cache" else self.retention.save_directory
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.startfile(str(directory))
        except OSError as error:
            self.status.set("打开文件夹失败：" + str(error))

    def choose_directory(self, kind):
        current = self.retention.cache_dir if kind == "cache" else self.retention.save_directory
        path = filedialog.askdirectory(title="选择缓存所在文件夹" if kind == "cache" else "选择默认保存文件夹", initialdir=str(current if current.exists() else current.parent))
        if not path:
            return
        try:
            if kind == "cache":
                old = self.retention.cache_dir
                self.retention.cleanup()
                self.retention.set_cache_directory(path)
                self.cache_location.set(str(self.retention.cache_dir))
                self.status.set(f"缓存路径已修改；旧缓存仍在 {old}，可手动删除。新位置只清理 CharlieTranslateCache 内的文件。")
            else:
                self.retention.set_save_directory(path)
                self.save_location.set(str(self.retention.save_directory))
                self.status.set("默认保存位置已修改；手动保存的图片可自行删除，不受缓存有效期影响。")
        except OSError as error:
            self.status.set("修改路径失败：" + str(error))

    def cleanup_cache(self):
        removed = self.retention.cleanup()
        if removed:
            self.status.set(f"已自动清理 {removed} 个过期缓存文件。")
        if not self.closed:
            self.root.after(6 * 60 * 60 * 1000, self.cleanup_cache)

    def close(self):
        if self.busy:
            self.status.set("正在退出，等待当前本机任务结束…")
            self.root.after(120, self.close)
            return
        self.closed = True
        self.generation += 1
        self.hotkeys.close()
        if self.hotkey_api:
            self.hotkey_api.shutdown()
        if self.api:
            self.api.shutdown()
            self.api.server_close()
        if self.translate_api:
            self.translate_api.shutdown()
            self.translate_api.server_close()
        self.translation.close()
        self.retention.close_session()
        if self.floating:
            self.floating.destroy()
        if self.editor:
            self.editor.cancel()
        if self.image:
            self.image.close()
            self.image = None
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def window_image(root):
    """Render only our HWND, so proof images cannot capture an overlapping app."""
    from ctypes import wintypes
    user,gdi=ctypes.windll.user32,ctypes.windll.gdi32
    user.GetDC.argtypes=[wintypes.HWND];user.GetDC.restype=wintypes.HDC
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=ctypes.c_void_p
    gdi.SelectObject.argtypes=[wintypes.HDC,ctypes.c_void_p];gdi.SelectObject.restype=ctypes.c_void_p
    gdi.DeleteObject.argtypes=[ctypes.c_void_p];gdi.DeleteDC.argtypes=[wintypes.HDC]
    class Header(ctypes.Structure):
        _fields_=[("size",wintypes.DWORD),("width",wintypes.LONG),("height",wintypes.LONG),("planes",wintypes.WORD),("bits",wintypes.WORD),("compression",wintypes.DWORD),("image_size",wintypes.DWORD),("x",wintypes.LONG),("y",wintypes.LONG),("used",wintypes.DWORD),("important",wintypes.DWORD)]
    w,h=root.winfo_width(),root.winfo_height()
    hwnd=root.winfo_id();dc=user.GetDC(hwnd);memory=gdi.CreateCompatibleDC(dc)
    bitmap=gdi.CreateCompatibleBitmap(dc,w,h);previous=gdi.SelectObject(memory,bitmap)
    try:
        if not user.PrintWindow(hwnd,memory,2): raise OSError("Unable to render own window")
        header=Header(ctypes.sizeof(Header),w,-h,1,32,0,w*h*4,0,0,0,0)
        data=ctypes.create_string_buffer(w*h*4)
        gdi.GetDIBits.argtypes=[wintypes.HDC,ctypes.c_void_p,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
        gdi.SelectObject(memory,previous)
        if not gdi.GetDIBits(memory,bitmap,0,h,data,ctypes.byref(header),0): raise OSError("Unable to read own window")
        return Image.frombytes("RGB",(w,h),data.raw,"raw","BGRX")
    finally:
        gdi.SelectObject(memory,previous);gdi.DeleteObject(bitmap);gdi.DeleteDC(memory);user.ReleaseDC(hwnd,dc)


def self_test(app, fixture, output):
    """Exercise the actual UI/inference/translation using an owned public fixture."""
    import time
    start = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    stage = ["ready"]
    def fail(message):
        (output / "result.json").write_text(json.dumps({"ok":False,"error":message},ensure_ascii=False),encoding="utf-8")
        app.close()
    def step():
        if time.monotonic() - start > 150:
            return fail("self-test timed out: " + app.status.get())
        if app.busy:
            return app.root.after(100,step)
        try:
            if stage[0] == "ready":
                if app.engine is None:
                    return fail(app.status.get())
                with Image.open(fixture) as image:
                    app.set_image(image.copy())
                app.recognize()
                stage[0] = "ocr"
            elif stage[0] == "ocr":
                text = app.original.get("1.0","end-1c")
                if not all(word in text for word in ("Charlie","Translate","你好世界")):
                    return fail("unexpected OCR: " + text)
                # Test translation with a deterministic English sentence, not mixed OCR.
                app.original.delete("1.0","end")
                app.original.insert("1.0","Hello world. This is a local translation test.")
                app.translate()
                stage[0] = "translation"
            else:
                text = app.translated.get("1.0","end-1c")
                if not text or text.startswith("Hello"):
                    return fail("translation failed: " + app.status.get())
                app.root.update_idletasks()
                window_image(app.root).save(output/"desktop-proof.png")
                app.image.save(output/"saved-fixture.png",format="PNG")
                (output / "result.json").write_text(json.dumps({"ok":True,"translation":text,"engine":"PP-OCRv5 server","api_ready":app.api is not None,"hotkey_registered":app.hotkey},ensure_ascii=False,indent=2),encoding="utf-8")
                return app.close()
        except Exception as error:
            return fail(str(error))
        app.root.after(100,step)
    app.root.after(100,step)


def main():
    global ROOT
    test_args = None
    if "--self-test" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--self-test",action="store_true")
        parser.add_argument("--fixture",type=Path,required=True)
        parser.add_argument("--output",type=Path,required=True)
        parser.add_argument("--data-dir",type=Path)
        test_args=parser.parse_args()
        if test_args.data_dir:
            ROOT=test_args.data_dir.resolve()
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except OSError:
            ctypes.windll.user32.SetProcessDPIAware()
    if sys.platform == "win32" and not test_args:
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        global INSTANCE_MUTEX
        INSTANCE_MUTEX = kernel.CreateMutexW(None, False, "Local\\CharlieTranslateDesktopV1")
        if ctypes.get_last_error() == 183:
            user = ctypes.windll.user32
            user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user.FindWindowW.restype = wintypes.HWND
            hwnd = user.FindWindowW(None, "Charlie Translate · 本地截图识字")
            if hwnd:
                user.ShowWindow(hwnd, 9)
                user.SetForegroundWindow(hwnd)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(INSTANCE_MUTEX)
            return
    install_network_guard()
    root = tk.Tk()
    app=App(root)
    if test_args:
        self_test(app,test_args.fixture,test_args.output)
    root.mainloop()


if __name__ == "__main__":
    main()
