"""Modal native-Tk text annotation dialog with real font and color settings."""
import re
import tkinter as tk
from tkinter import colorchooser, ttk

DEFAULT_TEXT_SIZE = 22
TEXT_SIZE_MIN = 12
TEXT_SIZE_MAX = 72
TEXT_SWATCHES = ("#ff2d2d", "#f59e0b", "#22c55e", "#3b82f6", "#111827", "#ffffff")


def normalized_color(value, fallback="#ff2d2d"):
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    return fallback


def font_size_from(value, default=DEFAULT_TEXT_SIZE):
    try:
        number = int(value)
        return number if TEXT_SIZE_MIN <= number <= TEXT_SIZE_MAX else default
    except (TypeError, ValueError, OverflowError):
        return default


class TextAnnotationDialog(tk.Toplevel):
    """Keep all changes local until OK; Cancel must not alter the screenshot."""

    def __init__(self, parent, initial_color="#ff2d2d", initial_size=DEFAULT_TEXT_SIZE):
        super().__init__(parent)
        self.result = None
        self.color = normalized_color(initial_color)
        self.size_var = tk.StringVar(value=str(font_size_from(initial_size)))
        self.title("文字标注 · 字号与颜色")
        self.resizable(False, False)
        self.configure(bg="#ffffff")
        self.attributes("-topmost", True)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        panel = tk.Frame(self, bg="#ffffff", padx=18, pady=14)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="输入文字", bg="white", fg="#334155",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        self.entry = ttk.Entry(panel, width=48, font=("Microsoft YaHei UI", 11))
        self.entry.pack(fill="x", pady=(5, 12), ipady=4)
        line = tk.Frame(panel, bg="white")
        line.pack(fill="x", pady=(0, 10))
        tk.Label(line, text="文字大小", bg="white", fg="#334155").pack(side="left")
        self.size_box = ttk.Spinbox(
            line, from_=TEXT_SIZE_MIN, to=TEXT_SIZE_MAX, increment=1,
            textvariable=self.size_var, width=5, command=self.update_preview,
        )
        self.size_box.pack(side="left", padx=(9, 5))
        tk.Label(line, text="12–72", bg="white", fg="#64748b").pack(side="left")
        self.size_box.bind("<KeyRelease>", self.update_preview)
        self.size_box.bind("<FocusOut>", self.update_preview)
        color_line = tk.Frame(panel, bg="white")
        color_line.pack(fill="x", pady=(0, 10))
        tk.Label(color_line, text="文字颜色", bg="white", fg="#334155").pack(side="left")
        self.swatch_buttons = {}
        for value in TEXT_SWATCHES:
            swatch = tk.Button(color_line, bg=value, activebackground=value,
                              width=2, bd=1, relief="solid",
                              command=lambda selected=value: self.set_color(selected))
            swatch.pack(side="left", padx=(5, 0))
            self.swatch_buttons[value] = swatch
        self.custom_color = ttk.Button(color_line, text="更多…", width=6, command=self.choose_color)
        self.custom_color.pack(side="left", padx=(8, 0))
        self.selected_color_label = tk.Label(
            panel, text="", bg="white", fg="#64748b", font=("Consolas", 9)
        )
        self.selected_color_label.pack(anchor="w", pady=(0, 4))
        self.preview = tk.Label(
            panel, text="文字预览：你好 Charlie 123", bg="#f8fafc",
            anchor="w", padx=9, height=2,
        )
        self.preview.pack(fill="x", pady=(0, 8))
        self.error_label = tk.Label(panel, text="", bg="white", fg="#b91c1c")
        self.error_label.pack(anchor="w")
        actions = tk.Frame(panel, bg="white")
        actions.pack(fill="x", pady=(7, 0))
        ttk.Button(actions, text="取消", command=self.cancel).pack(side="right")
        ttk.Button(actions, text="确定", command=self.confirm).pack(side="right", padx=(0, 8))
        self.bind("<Return>", self.confirm)
        self.bind("<Escape>", self.cancel)
        self.update_preview()
        self.update_idletasks()
        parent_x, parent_y = parent.winfo_rootx(), parent.winfo_rooty()
        left = max(0, parent_x + max(0, (parent.winfo_width() - self.winfo_reqwidth()) // 2))
        top = max(0, parent_y + 25)
        self.geometry(f"+{left}+{top}")
        self.entry.focus_set()

    def set_color(self, value):
        self.color = normalized_color(value, self.color)
        self.update_preview()

    def choose_color(self):
        selected = colorchooser.askcolor(color=self.color, parent=self)[1]
        if selected:
            self.set_color(selected)

    def update_preview(self, _event=None):
        size = font_size_from(self.size_var.get())
        self.preview.configure(fg=self.color, font=("Microsoft YaHei UI", -min(48, size)))
        self.selected_color_label.configure(text=f"已选颜色：{self.color.upper()} · 字号 {size}")
    def _close(self):
        # Destroy Tk variables on the UI thread, before OCR/hotkey worker
        # threads or cyclic widget references can finalize them at shutdown.
        self.size_box.configure(textvariable="")
        value = self.size_var
        self.size_var = None
        del value
        self.destroy()

    def confirm(self, _event=None):
        text = self.entry.get().strip()
        if not text:
            self.error_label.configure(text="请输入文字后再确认。")
            self.entry.focus_set()
            return "break"
        try:
            size = int(self.size_var.get())
        except (ValueError, OverflowError):
            size = 0
        if not TEXT_SIZE_MIN <= size <= TEXT_SIZE_MAX:
            self.error_label.configure(text=f"字号必须在 {TEXT_SIZE_MIN} 到 {TEXT_SIZE_MAX} 之间。")
            self.size_box.focus_set()
            return "break"
        self.result = (text, size, self.color)
        self._close()
        return "break"

    def cancel(self, _event=None):
        self.result = None
        self._close()
        return "break"

    @classmethod
    def ask(cls, parent, *, initial_color, initial_size):
        dialog = cls(parent, initial_color=initial_color, initial_size=initial_size)
        dialog.wait_visibility()
        dialog.grab_set()
        dialog.entry.focus_set()
        dialog.wait_window()
        return dialog.result
