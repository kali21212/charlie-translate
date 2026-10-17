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
from desktop.text_layout import format_ocr_result, reflow_plain_text
from desktop.hotkeys import Hotkeys, IDS, DEFAULTS, event_hotkey, WindowsHotkeyPump
from services.ocr.server import create_engine, Handler, ThreadingHTTPServer

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
WINDOW_TITLE = "Charlie Translate · 截图 / OCR / 翻译"


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
        self.tray = None
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
        root.title(WINDOW_TITLE)
        saved_geometry = self.retention.get_ui_setting("mainWindowGeometry", "1120x780")
        try:
            root.geometry(str(saved_geometry))
        except tk.TclError:
            root.geometry("1120x780")
        root.minsize(760, 620)
        root.configure(bg="#f5f7fb")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f7fb")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f5f7fb", font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background="#ffffff", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(9, 6), background="#ffffff", borderwidth=0, relief="flat")
        style.map("TButton", background=[("active", "#e7edf5")])
        style.configure("Primary.TButton", background="#2563eb", foreground="white", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#cbd5e1")])
        style.configure("Subtle.TButton", background="#eef2f7", foreground="#334155", borderwidth=0)
        style.map("Subtle.TButton", background=[("active", "#dde6f0")])
        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        footer = ttk.Frame(frame)
        footer.pack(side="bottom", fill="x")
        header = ttk.Frame(frame)
        header.pack(fill="x")
        ttk.Label(header, text="Charlie Translate", font=("Microsoft YaHei UI", 20, "bold")).pack(side="left")
        ttk.Button(header, text="设置", command=self.open_settings, style="Subtle.TButton").pack(side="right")
        ttk.Label(frame, text="本机截图 · PP-OCRv5 · 段落智能整理 · 本地翻译；图片不自动上传或保存").pack(anchor="w", pady=(2, 8))
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
        self.panels = ttk.Frame(frame)
        self.panels.pack(fill="both", expand=True)
        self.original_heading = tk.StringVar(value="原文 · 可以编辑")
        self.original_card = ttk.Frame(self.panels, style="Card.TFrame", padding=8)
        self.translated_card = ttk.Frame(self.panels, style="Card.TFrame", padding=8)
        self.original_card.columnconfigure(0, weight=1)
        self.original_card.rowconfigure(1, weight=1)
        self.translated_card.columnconfigure(0, weight=1)
        self.translated_card.rowconfigure(1, weight=1)
        ttk.Label(self.original_card, textvariable=self.original_heading, style="Card.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(self.translated_card, text="简体中文译文", style="Card.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.original = tk.Text(
            self.original_card, width=35, height=8, wrap="word",
            font=("Microsoft YaHei UI", 12), padx=12, pady=10, undo=True,
            relief="flat", bd=0, bg="#ffffff", fg="#0f172a",
            selectbackground="#bfdbfe", spacing1=2, spacing3=6,
        )
        self.translated = tk.Text(
            self.translated_card, width=35, height=8, wrap="word",
            font=("Microsoft YaHei UI", 12), padx=12, pady=10, state="disabled",
            relief="flat", bd=0, bg="#f8fafc", fg="#0f172a",
            selectbackground="#bfdbfe", spacing1=2, spacing3=6,
        )
        self.original_scroll = ttk.Scrollbar(self.original_card, orient="vertical", command=self.original.yview)
        self.translated_scroll = ttk.Scrollbar(self.translated_card, orient="vertical", command=self.translated.yview)
        self.original.configure(yscrollcommand=self.original_scroll.set)
        self.translated.configure(yscrollcommand=self.translated_scroll.set)
        self.original.grid(row=1, column=0, sticky="nsew")
        self.original_scroll.grid(row=1, column=1, sticky="ns")
        self.translated.grid(row=1, column=0, sticky="nsew")
        self.translated_scroll.grid(row=1, column=1, sticky="ns")
        self.original.bind("<Control-Return>", self.translate_shortcut)
        self.panel_layout_mode = None
        self.panels.bind("<Configure>", self._layout_text_panels)
        self.root.after_idle(self._layout_text_panels)

        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(6, 6))
        self.translate_button = ttk.Button(actions, text="翻译为中文（本机）", command=self.translate, style="Primary.TButton")
        self.translate_button.pack(side="left")
        ttk.Button(actions, text="整理段落", command=self.reflow_original, style="Subtle.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="复制原文", command=lambda: self.copy_text(self.original)).pack(side="left", padx=6)
        ttk.Button(actions, text="复制译文", command=lambda: self.copy_text(self.translated)).pack(side="left")
        self.on_top = tk.BooleanVar(value=bool(self.retention.get_ui_setting("mainAlwaysOnTop", False)))
        self.root.attributes("-topmost", self.on_top.get())
        ttk.Checkbutton(actions, text="置顶", variable=self.on_top, command=self.toggle_on_top).pack(side="right")
        self.floating_enabled = tk.BooleanVar(value=self.floating.default_enabled())
        ttk.Checkbutton(actions, text="悬浮截图", variable=self.floating_enabled, command=self.toggle_floating).pack(side="right", padx=(0, 10))

        self.retention_days = tk.StringVar(value=str(self.retention.days))
        self.cache_location = tk.StringVar(value=str(self.retention.cache_dir))
        self.save_location = tk.StringVar(value=str(self.retention.save_directory))
        self.auto_reflow_ocr = tk.BooleanVar(value=bool(self.retention.get_ui_setting("autoReflowOcr", True)))
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(2, 5))
        self.task_serial = 0
        self.status = tk.StringVar(value="正在加载增强 OCR 模型…")
        self.status_label = ttk.Label(footer, textvariable=self.status, wraplength=1000)
        self.status_label.pack(anchor="w", fill="x")
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
        root.protocol("WM_DELETE_WINDOW", self.request_close)
        root.bind("<Unmap>", self._on_unmap, add="+")

    def _layout_text_panels(self, event=None):
        if event is not None and event.widget is not self.panels:
            return
        width = self.panels.winfo_width()
        mode = "columns" if width >= 900 else "rows"
        self.status_label.configure(wraplength=max(420, self.root.winfo_width() - 50))
        if mode == self.panel_layout_mode:
            return
        self.panel_layout_mode = mode
        self.original_card.grid_forget()
        self.translated_card.grid_forget()
        for index in (0, 1):
            self.panels.columnconfigure(index, weight=0, uniform="")
            self.panels.rowconfigure(index, weight=0, uniform="")
        if mode == "columns":
            self.panels.columnconfigure((0, 1), weight=1, uniform="translation")
            self.panels.rowconfigure(0, weight=1)
            self.original_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
            self.translated_card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        else:
            self.panels.columnconfigure(0, weight=1)
            self.panels.rowconfigure((0, 1), weight=1, uniform="translation")
            self.original_card.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
            self.translated_card.grid(row=1, column=0, sticky="nsew", pady=(5, 0))

    def toggle_on_top(self):
        value = bool(self.on_top.get())
        self.root.attributes("-topmost", value)
        self.retention.set_ui_setting("mainAlwaysOnTop", value)

    def set_auto_reflow(self):
        self.retention.set_ui_setting("autoReflowOcr", bool(self.auto_reflow_ocr.get()))
        self.status.set(
            "OCR 段落智能整理已开启。" if self.auto_reflow_ocr.get()
            else "OCR 段落智能整理已关闭；将保留识别引擎原始换行。"
        )

    def open_settings(self):
        dialog = getattr(self, "settings_dialog", None)
        if dialog and dialog.winfo_exists():
            dialog.deiconify()
            dialog.lift()
            return
        dialog = self.settings_dialog = tk.Toplevel(self.root)
        dialog.title("Charlie Translate · 设置")
        dialog.geometry("720x430")
        dialog.minsize(620, 390)
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="界面与本地数据", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Checkbutton(
            body,
            text="OCR 后自动整理段落与阅读顺序（推荐）",
            variable=self.auto_reflow_ocr,
            command=self.set_auto_reflow,
        ).pack(anchor="w", pady=(12, 8))

        retention_row = ttk.Frame(body)
        retention_row.pack(fill="x", pady=(2, 12))
        ttk.Label(retention_row, text="应用缓存有效期").pack(side="left")
        retention = ttk.Combobox(
            retention_row,
            width=8,
            state="readonly",
            textvariable=self.retention_days,
            values=("0", "1", "3", "7", "14", "30"),
        )
        retention.pack(side="left", padx=8)
        ttk.Label(retention_row, text="天（0=仅本次；手动保存文件不自动删除）").pack(side="left")
        retention.bind("<<ComboboxSelected>>", self.change_retention)

        for label, variable, kind in (
            ("缓存位置", self.cache_location, "cache"),
            ("默认保存位置", self.save_location, "save"),
        ):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=12).pack(side="left")
            ttk.Entry(row, textvariable=variable, state="readonly").pack(
                side="left", fill="x", expand=True, padx=6
            )
            ttk.Button(row, text="打开", command=lambda k=kind: self.open_directory(k)).pack(side="left", padx=3)
            ttk.Button(row, text="修改", command=lambda k=kind: self.choose_directory(k)).pack(side="left")

        ttk.Separator(body).pack(fill="x", pady=14)
        privacy = (
            "隐私抹除仍采用 Charlie 安全语义：实色 / 安全马赛克 / 安全模糊一旦提交，"
            "都会直接改写底层像素并清空可恢复历史，不能撤销恢复。"
        )
        ttk.Label(body, text=privacy, wraplength=650, justify="left").pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="快捷键设置", command=self.configure_hotkeys).pack(side="left")
        ttk.Button(buttons, text="关闭", command=dialog.destroy, style="Primary.TButton").pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def reflow_original(self):
        if self.busy:
            return
        current = self.original.get("1.0", "end-1c")
        value = reflow_plain_text(current)
        if value and value != current:
            self.original.delete("1.0", "end")
            self.original.insert("1.0", value)
            self.original.edit_reset()
            self.set_translation("")
            self.status.set("已重新整理原文段落与硬换行。")
        elif value:
            self.status.set("当前原文已经不需要进一步整理。")

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
            # Never copy an unredacted capture before the privacy editor.
            # Only the finalized (possibly redacted) image may reach clipboard.
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
        elif action == "save":
            self.show_main()
            self.root.after_idle(self.save_image)

    def editor_cancelled(self):
        self.editor = None
        if getattr(self, "capture_main_visible", True):
            self.show_main()
        if self.floating and self.floating_enabled.get():
            self.floating.resume()
        self.status.set("已退出标注；未将原始框选图片复制到剪贴板，也未保存文件。")

    def set_image(self, image):
        if image.width * image.height > 16_000_000:
            image.close()
            raise ValueError("图片过大，请选择较小区域")
        if self.image:
            self.image.close()
        self.image = image.convert("RGB")
        image.close()
        thumb = self.image.copy()
        thumb.thumbnail((1040, 125))
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
        smart_layout = bool(self.auto_reflow_ocr.get())
        self.original_heading.set("原文 · 正在识字，请稍候…")
        self.status.set("正在本机识字并分析阅读顺序，图片不会发送给翻译服务…")
        def work():
            if not self.ocr_lock.acquire(blocking=False):
                raise ValueError("浏览器正在识字，请稍后再试")
            try:
                result = self.engine(raw)
                raw_text = "\n".join(result.txts if result.txts is not None else ())
                text = format_ocr_result(result) if smart_layout else raw_text
                return {"text": text, "raw": raw_text, "smart": smart_layout}
            finally:
                self.ocr_lock.release()
        self.submit(work, self.recognized)

    def recognized(self, value):
        self.original_heading.set("原文 · 可以编辑")
        if isinstance(value, dict):
            text = value.get("text") or ""
            self.last_ocr_raw = value.get("raw") or text
            smart_layout = bool(value.get("smart"))
        else:
            text = value or ""
            self.last_ocr_raw = text
            smart_layout = False
        self.original.delete("1.0", "end")
        self.original.insert("1.0", text)
        self.original.edit_reset()
        self.set_translation("")
        if text:
            note = "已按阅读顺序整理段落；" if smart_layout else ""
            self.status.set(f"识字完成。{note}可继续编辑，翻译只向本机发送文字。")
        else:
            self.status.set("未识别到文字，请选择清晰区域。")
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
        if not text.strip():
            self.status.set("请先输入或识别需要翻译的文字。")
            return
        self.status.set("正在本机按段落翻译为中文…")
        self.submit(lambda: self.translation.translate_document(text), self.translation_done)

    def translation_done(self, text):
        self.set_translation(text)
        self.status.set("本机翻译完成；长文章已按段落保留阅读结构。")

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

    def attach_tray(self, tray):
        self.tray = tray

    def request_close(self):
        if self.tray:
            self.hide_to_tray()
        else:
            self.close()

    def hide_to_tray(self):
        if self.closed:
            return
        try:
            if self.root.state() != "withdrawn":
                self.retention.set_ui_setting("mainWindowGeometry", self.root.winfo_geometry())
            self.root.withdraw()
            self.status.set("Charlie Translate 已驻留 Windows 系统托盘；双击或单击托盘图标可恢复。")
        except tk.TclError:
            pass

    def _on_unmap(self, event):
        if event.widget is not self.root or not self.tray or self.closed:
            return
        self.root.after_idle(self._finish_minimize_to_tray)

    def _finish_minimize_to_tray(self):
        if self.closed or not self.tray:
            return
        try:
            if self.root.state() == "iconic":
                self.hide_to_tray()
        except tk.TclError:
            pass

    def show_main(self):
        if self.closed:
            return
        self.root.deiconify()
        try:
            self.root.state("normal")
        except tk.TclError:
            pass
        self.root.lift()
        self.root.focus_force()

    def toggle_floating_from_tray(self):
        if not hasattr(self, "floating_enabled"):
            return
        self.floating_enabled.set(not bool(self.floating_enabled.get()))
        self.toggle_floating()

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
        try:
            if self.root.state() not in ("withdrawn", "iconic"):
                self.retention.set_ui_setting("mainWindowGeometry", self.root.winfo_geometry())
            self.retention.set_ui_setting("mainAlwaysOnTop", bool(self.on_top.get()))
            self.retention.set_ui_setting("autoReflowOcr", bool(self.auto_reflow_ocr.get()))
        except (OSError, tk.TclError):
            pass
        self.closed = True
        self.generation += 1
        tray, self.tray = self.tray, None
        if tray:
            tray.stop()
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
        try:
            for after_id in self.root.tk.call("after", "info"):
                self.root.after_cancel(after_id)
        except tk.TclError:
            pass
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


def start_system_tray(app):
    if sys.platform != "win32":
        return None
    try:
        from desktop.tray import SystemTray
        icon_path = app.retention.root / "tray.ico"
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        icon = app.floating.icon_image(color=app.floating.color)
        try:
            icon.save(
                icon_path,
                format="ICO",
                sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64)],
            )
        finally:
            icon.close()
        tray = SystemTray(
            icon_path,
            schedule=lambda action: app.root.after(0, action),
            capture=lambda: app.capture(False),
            translate=lambda: app.capture(True),
            show_main=app.show_main,
            toggle_floating=app.toggle_floating_from_tray,
            floating_enabled=lambda: bool(app.floating_enabled.get()),
            exit_app=app.close,
            tooltip="Charlie Translate · 本地截图 / OCR / 翻译",
        )
        if not tray.start():
            return None
        app.attach_tray(tray)
        return tray
    except (OSError, ValueError, tk.TclError):
        return None


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
            hwnd = user.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                user.ShowWindow(hwnd, 9)
                user.SetForegroundWindow(hwnd)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(INSTANCE_MUTEX)
            return
    install_network_guard()
    root = tk.Tk()
    app = App(root)
    if not test_args and sys.platform == "win32":
        tray = start_system_tray(app)
        if tray:
            root.after(
                250,
                lambda: app.status.set(
                    "Charlie Translate 已启用 Windows 系统托盘；最小化或关闭主窗口后仍在后台运行。"
                ) if not app.busy else None,
            )
    if test_args:
        self_test(app,test_args.fixture,test_args.output)
    root.mainloop()


if __name__ == "__main__":
    main()
