"""Windows portable screenshot/OCR UI. All image processing stays in this process."""
import ctypes
import io
import json
import queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageGrab, ImageTk

from desktop.local_translation import LocalTranslation
from desktop.privacy import install_network_guard
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
                self.finish(self.image.crop(box))
            except ValueError:
                self.finish(None)

    def finish(self, crop):
        self.window.grab_release()
        self.window.destroy()
        self.image.close()
        self.image = None
        self.photo = None
        self.done(crop)


class App:
    def __init__(self, root):
        self.root, self.image, self.photo = root, None, None
        self.engine, self.api, self.busy, self.selection = None, None, False, None
        self.generation, self.closed = 0, False
        self.ocr_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.results = queue.Queue()
        self.translation = LocalTranslation(ROOT)
        root.title("Charlie Translate · 本地截图识字")
        root.geometry("940x730")
        root.minsize(750, 580)
        root.configure(bg="#eef3f9")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f9")
        style.configure("TLabel", background="#eef3f9", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(9, 6))
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Charlie Translate", font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
        ttk.Label(frame, text="截图与增强识字留在本机 · 翻译只连接本机服务 · 不自动保存图片").pack(anchor="w", pady=(3, 12))
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.controls = []
        for name, action in [("框选截图", self.capture), ("打开图片", self.open_image), ("增强识字", self.recognize), ("保存截图", self.save_image), ("复制截图", self.copy_image), ("清空", self.clear)]:
            button = ttk.Button(bar, text=name, command=action)
            button.pack(side="left", padx=(0, 6))
            self.controls.append(button)
        self.preview = tk.Label(frame, bg="#dce6f0", text="框选桌面、其他软件或浏览器，也可以打开本机图片", font=("Microsoft YaHei UI", 12), fg="#38516a")
        self.preview.pack(fill="x", pady=12, ipady=4)
        panels = ttk.Frame(frame)
        panels.pack(fill="both", expand=True)
        panels.columnconfigure((0, 1), weight=1)
        panels.rowconfigure(1, weight=1)
        ttk.Label(panels, text="原文 · 可以编辑").grid(row=0, column=0, sticky="w")
        ttk.Label(panels, text="简体中文译文").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.original = tk.Text(panels, width=35, height=6, wrap="word", font=("Microsoft YaHei UI", 12), padx=10, pady=10, undo=True)
        self.translated = tk.Text(panels, width=35, height=6, wrap="word", font=("Microsoft YaHei UI", 12), padx=10, pady=10, state="disabled")
        self.original.grid(row=1, column=0, sticky="nsew", pady=6)
        self.translated.grid(row=1, column=1, sticky="nsew", pady=6, padx=(12, 0))
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(6, 10))
        self.translate_button = ttk.Button(actions, text="翻译为中文（本机）", command=self.translate)
        self.translate_button.pack(side="left")
        ttk.Button(actions, text="复制原文", command=lambda: self.copy_text(self.original)).pack(side="left", padx=6)
        ttk.Button(actions, text="复制译文", command=lambda: self.copy_text(self.translated)).pack(side="left")
        self.on_top = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions,text="置顶浮窗",variable=self.on_top,command=lambda: self.root.attributes("-topmost",self.on_top.get())).pack(side="right")
        self.status = tk.StringVar(value="正在加载增强 OCR 模型…")
        ttk.Label(frame, textvariable=self.status, wraplength=880).pack(anchor="w")
        self.submit(self.initialize, self.ready)
        self.hotkey = False
        if sys.platform == "win32":
            self.hotkey = bool(ctypes.windll.user32.RegisterHotKey(None, 0x4348, 0x4003, 0x51))
            root.after(100, self.poll_hotkey)
        root.after(80, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def initialize(self):
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
        note = "浏览器可共用本机 OCR。" if self.api else "8990 端口被占用，桌面识字仍可用。"
        shortcut="Ctrl+Alt+Q 框选后预览。" if self.hotkey else "快捷键被占用，请点击框选截图。"
        self.status.set("增强 OCR 就绪。" + shortcut + note)

    def submit(self, work, done):
        if self.busy:
            return
        self.busy = True
        self.enable(False)
        generation = self.generation
        def run():
            try:
                self.results.put((generation, done, work(), None))
            except Exception as error:
                self.results.put((generation, done, None, str(error)))
        self.executor.submit(run)

    def enable(self, value):
        state = "normal" if value else "disabled"
        for button in self.controls + [self.translate_button]:
            button.configure(state=state)
        self.original.configure(state=state)

    def poll(self):
        while not self.results.empty():
            generation, done, value, error = self.results.get_nowait()
            self.busy = False
            self.enable(True)
            if generation == self.generation:
                if error:
                    self.status.set("操作失败：" + error)
                else:
                    done(value)
        if not self.closed:
            self.root.after(80, self.poll)

    def poll_hotkey(self):
        from ctypes import wintypes
        message = wintypes.MSG()
        if self.hotkey:
            while ctypes.windll.user32.PeekMessageW(ctypes.byref(message), None, 0x312, 0x312, 1):
                self.capture()
        if not self.closed:
            self.root.after(100, self.poll_hotkey)

    def capture(self):
        if self.busy or self.selection:
            return
        self.root.withdraw()
        self.root.after(180, self.select_screen)

    def select_screen(self):
        try:
            image = ImageGrab.grab(all_screens=True)
            origin = (ctypes.windll.user32.GetSystemMetrics(76), ctypes.windll.user32.GetSystemMetrics(77))
            self.selection = Selection(self.root, image, origin, self.selected)
        except Exception as error:
            self.root.deiconify()
            self.status.set("截图失败：" + str(error))

    def selected(self, image):
        self.selection = None
        self.root.deiconify()
        self.root.lift()
        if image:
            self.set_image(image)
        else:
            self.status.set("截图已取消，未识字、未保存。")

    def set_image(self, image):
        if image.width * image.height > 16_000_000:
            image.close()
            raise ValueError("图片过大，请选择较小区域")
        if self.image:
            self.image.close()
        self.image = image.convert("RGB")
        image.close()
        thumb = self.image.copy()
        thumb.thumbnail((860, 150))
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
            self.status.set("请先选择图片，并等待模型加载。")
            return
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        raw = buffer.getvalue()
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
        self.original.delete("1.0", "end")
        self.original.insert("1.0", text)
        self.set_translation("")
        self.status.set("识字完成。可编辑原文；点击翻译只向本机发送文字。" if text else "未识别到文字，请选择清晰区域。")

    def set_translation(self, text):
        self.translated.configure(state="normal")
        self.translated.delete("1.0", "end")
        self.translated.insert("1.0", text)
        self.translated.configure(state="disabled")

    def translate(self):
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
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile="Charlie-screenshot.png", filetypes=[("PNG", "*.png")])
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
        except OSError as error:
            self.status.set(str(error))
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

    def close(self):
        if self.busy:
            self.status.set("正在退出，等待当前本机任务结束…")
            self.root.after(120, self.close)
            return
        self.closed = True
        self.generation += 1
        if self.hotkey:
            ctypes.windll.user32.UnregisterHotKey(None, 0x4348)
        if self.api:
            self.api.shutdown()
            self.api.server_close()
        self.translation.close()
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
    install_network_guard()
    root = tk.Tk()
    app=App(root)
    if test_args:
        self_test(app,test_args.fixture,test_args.output)
    root.mainloop()


if __name__ == "__main__":
    main()
