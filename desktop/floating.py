"""Small movable always-on-top capture launcher for Charlie Translate Desktop."""
import json
import re
import tkinter as tk
from tkinter import colorchooser
from pathlib import Path
from PIL import Image, ImageDraw, ImageTk


class FloatingButton:
    SIZE = 56
    DEFAULT_COLOR = "#16a34a"

    def __init__(self, root, capture, show_main, settings_dir, on_hidden=None):
        self.root = root
        self.capture = capture
        self.show_main = show_main
        self.on_hidden = on_hidden
        self.settings_path = Path(settings_dir) / "floating.json"
        saved_color = self._read_config().get("color", self.DEFAULT_COLOR)
        self.color = saved_color if self._valid_color(saved_color) else self.DEFAULT_COLOR
        self.window = None
        self.drag_start = None
        self.origin = None
        self.moved = False

    @staticmethod
    def _valid_color(color):
        return isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) is not None

    def set_color(self, color):
        if not self._valid_color(color):
            raise ValueError("请选择有效的图标颜色")
        self.color = color.lower()
        data = self._read_config()
        data["color"] = self.color
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if self.window and self.window.winfo_exists():
            self._hover(self.canvas, False)

    def choose_color(self):
        color = colorchooser.askcolor(self.color, title="悬浮图标颜色", parent=self.window)[1]
        if color:
            self.set_color(color)

    def _read_config(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _load_position(self):
        data = self._read_config()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if "x" in data and "y" in data:
            try:
                return max(0, min(sw - self.SIZE, int(data["x"]))), max(0, min(sh - self.SIZE, int(data["y"])))
            except (ValueError, TypeError):
                pass
        return max(20, sw - self.SIZE - 28), 140

    def default_enabled(self):
        return bool(self._read_config().get("enabled", True))

    def set_enabled(self, enabled):
        data = self._read_config()
        data["enabled"] = bool(enabled)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _save_position(self):
        if not self.window:
            return
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._read_config()
        data.update({"x": self.window.winfo_x(), "y": self.window.winfo_y()})
        self.settings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def show(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        self.window = tk.Toplevel(self.root)
        self.window.title("Charlie Translate · 悬浮截图")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        transparent = "#010203"
        self.window.configure(bg=transparent)
        try:
            self.window.attributes("-transparentcolor", transparent)
        except tk.TclError:
            pass
        x, y = self._load_position()
        self.window.geometry(f"{self.SIZE}x{self.SIZE}{x:+d}{y:+d}")
        canvas = tk.Canvas(
            self.window,
            width=self.SIZE,
            height=self.SIZE,
            highlightthickness=0,
            bg=transparent,
            cursor="hand2",
        )
        canvas.pack(fill="both", expand=True)
        self.canvas = canvas
        self.icon = ImageTk.PhotoImage(self.display_icon_image(color=self.color))
        canvas.create_image(self.SIZE//2, self.SIZE//2, image=self.icon)
        canvas.bind("<Enter>", lambda _e: self._hover(canvas, True))
        canvas.bind("<Leave>", lambda _e: self._hover(canvas, False))
        canvas.bind("<ButtonPress-1>", self._press)
        canvas.bind("<B1-Motion>", self._drag)
        canvas.bind("<ButtonRelease-1>", self._release)
        canvas.bind("<Button-3>", self._menu)

    @classmethod
    def icon_image(cls, hover=False, color=DEFAULT_COLOR):
        # Native vector geometry rendered at 4x for a crisp, transparent icon.
        factor = 4
        image = Image.new("RGBA", (cls.SIZE*factor, cls.SIZE*factor))
        draw = ImageDraw.Draw(image)
        def box(values):
            return tuple(round(value*factor) for value in values)
        if not cls._valid_color(color):
            color = cls.DEFAULT_COLOR
        rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        face = tuple(round(v + (255-v)*0.12) for v in rgb) if hover else rgb
        # Keep the monogram readable even when the user selects a pale color.
        foreground = "#163127" if sum(v*w for v,w in zip(rgb,(0.299,0.587,0.114))) > 175 else "#ffffff"
        draw.rounded_rectangle(box((3, 3, 53, 53)), radius=17*factor, fill=face)
        # A quiet C monogram: one geometric stroke, one small capture indicator.
        draw.arc(box((16, 15, 40, 39)), 48, 312, fill=foreground, width=4*factor)
        draw.ellipse(box((37, 24, 43, 30)), fill=foreground)
        return image.resize((cls.SIZE, cls.SIZE), Image.Resampling.LANCZOS)

    @classmethod
    def display_icon_image(cls, hover=False, color=DEFAULT_COLOR):
        image = cls.icon_image(hover, color)
        # Tk on Windows uses a color key, not per-pixel window alpha. Partial
        # alpha otherwise blends with the dark key and leaves a visible halo.
        color = color if cls._valid_color(color) else cls.DEFAULT_COLOR
        rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        face = tuple(round(v + (255-v)*0.12) for v in rgb) if hover else rgb
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                r, g, b, alpha = pixels[x, y]
                if alpha < 128:
                    pixels[x, y] = (0, 0, 0, 0)
                elif alpha < 255:
                    pixels[x, y] = (*face, 255)
        return image

    def _hover(self, canvas, enabled):
        self.icon = ImageTk.PhotoImage(self.display_icon_image(enabled, self.color))
        canvas.itemconfigure(1, image=self.icon)
    def _press(self, event):
        self.drag_start = (event.x_root, event.y_root)
        self.origin = (self.window.winfo_x(), self.window.winfo_y())
        self.moved = False

    def _drag(self, event):
        if not self.drag_start:
            return
        dx = event.x_root - self.drag_start[0]
        dy = event.y_root - self.drag_start[1]
        if abs(dx) + abs(dy) > 4:
            self.moved = True
        x = self.origin[0] + dx
        y = self.origin[1] + dy
        sw, sh = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        x = max(0, min(sw - self.SIZE, x))
        y = max(0, min(sh - self.SIZE, y))
        self.window.geometry(f"+{x}+{y}")

    def _release(self, _event):
        if self.moved:
            self._save_position()
        else:
            self.capture()
        self.drag_start = None
        self.origin = None

    def _menu(self, event):
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label="截图并标注", command=self.capture)
        menu.add_command(label="打开主窗口", command=self.show_main)
        menu.add_separator()
        menu.add_command(label="自定义图标颜色…", command=self.choose_color)
        menu.add_command(label="恢复默认绿色", command=lambda: self.set_color(self.DEFAULT_COLOR))
        menu.add_separator()
        menu.add_command(label="隐藏悬浮按钮", command=self.hide)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def suspend(self):
        if self.window and self.window.winfo_exists():
            self.window.withdraw()

    def resume(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()

    def hide(self):
        if self.window and self.window.winfo_exists():
            self._save_position()
            self.window.withdraw()
        self.set_enabled(False)
        if self.on_hidden:
            self.on_hidden()

    def destroy(self):
        if self.window and self.window.winfo_exists():
            self._save_position()
            self.window.destroy()
        self.window = None
