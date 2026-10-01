"""Screenshot annotation editor for Charlie Translate Desktop.

Ordinary annotations are editable/undoable. Privacy redaction is committed
straight into the base bitmap and creates an irreversible history barrier.
"""
import copy
import tkinter as tk
from tkinter import colorchooser, simpledialog, ttk
from PIL import Image, ImageDraw, ImageFilter, ImageTk, ImageFont
import os
from pathlib import Path

TOOLS = (
    ("选择", "select"), ("矩形", "rect"), ("圆/椭圆", "ellipse"),
    ("直线", "line"), ("箭头", "arrow"), ("铅笔", "pencil"),
    ("荧光笔", "highlight"), ("文字", "text"), ("序号", "number"),
    ("隐私马赛克", "redact_pixel"), ("隐私模糊", "redact_blur"),
    ("隐私遮盖", "redact_solid"),
)


def apply_redaction(image, box, mode, color="#000000"):
    """Destructively replace pixels inside box; returns no reversible snapshot."""
    crop = image.crop(box)
    try:
        if mode == "redact_pixel":
            w, h = crop.size
            small = crop.resize((max(1, w // 12), max(1, h // 12)), Image.Resampling.BILINEAR)
            redacted = small.resize((w, h), Image.Resampling.NEAREST)
            small.close()
        elif mode == "redact_blur":
            redacted = crop.filter(ImageFilter.GaussianBlur(radius=max(8, min(crop.size) / 12)))
        elif mode == "redact_solid":
            redacted = Image.new("RGB", crop.size, color)
        else:
            raise ValueError("unknown redaction mode")
        image.paste(redacted, box[:2])
        redacted.close()
    finally:
        crop.close()


class ScreenshotEditor:
    BORDER = 3
    BUTTON_SIZE = 30
    BUTTON_STEP = 36
    def __init__(self, root, image, done, cancel, position=None):
        self.root, self.done, self.cancel_cb = root, done, cancel
        self.base = image.convert("RGB")
        image.close()
        self.annotations, self.undo_stack, self.redo_stack = [], [], []
        self.tool, self.color, self.width = "arrow", "#ff2d2d", 4
        self.fill = tk.BooleanVar(value=False)
        self.radius = tk.IntVar(value=12)
        self.sequence = 1
        self.start = self.current = self.temp = None
        self.selected = None
        self.position = position
        self.tooltip = None
        self.window = tk.Toplevel(root)
        self.window.title("Charlie Capture · 标注与隐私遮盖")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self._build()
        self._fit()
        self._render()
    def _build(self):
        self.status = tk.StringVar(value="普通标注可撤销；隐私遮盖一旦应用不可撤销、不可删除。")
        self.canvas = tk.Canvas(self.window, highlightthickness=self.BORDER, highlightbackground="#2563eb", highlightcolor="#2563eb", bg="white", cursor="crosshair")
        self.canvas.pack()
        self.toolbar = tk.Toplevel(self.window)
        self.toolbar.title("Charlie Capture · 工具栏")
        self.toolbar.overrideredirect(True)
        self.toolbar.attributes("-topmost", True)
        self.toolbar.configure(bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        self.icons = tk.Canvas(self.toolbar, height=44, bg="white", highlightthickness=0)
        self.icons.pack()
        self.tool_actions = [(label, tool, lambda t=tool: self.set_tool(t)) for label, tool in TOOLS]
        self.tool_actions += [("撤销 Ctrl+Z", "undo", self.undo), ("重做 Ctrl+Y", "redo", self.redo), ("删除普通标注", "delete", self.delete_selected), ("识字翻译", "ocr", lambda: self.finish("ocr")), ("复制并完成 Enter", "finish", self.finish), ("取消 Esc", "cancel", self.cancel)]
        self.button_positions = []
        self.group_separators = []
        x = 8
        for index in range(len(self.tool_actions)):
            if index in (9, 12, 15):
                self.group_separators.append(x + 1)
                x += 9
            self.button_positions.append(x)
            x += self.BUTTON_STEP
        self.toolbar_width = x + 8
        self.icons.configure(width=self.toolbar_width-2)
        self.icons.bind("<Button-1>", self._toolbar_click)
        self.icons.bind("<Motion>", self._toolbar_hover)
        self.icons.bind("<Leave>", self._toolbar_leave)
        tk.Frame(self.toolbar, height=1, bg="#e2e8f0").pack(fill="x", padx=8, pady=(0, 5))
        options = tk.Frame(self.toolbar, bg="white")
        options.pack(fill="x", padx=8, pady=(0, 5))
        for color in ("#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#ffffff", "#111827"):
            tk.Button(options, bg=color, activebackground=color, width=2, bd=0, command=lambda c=color: self._color(c)).pack(side="left", padx=3)
        tk.Button(options, text="+", bd=0, bg="white", fg="#64748b", command=self.pick_color).pack(side="left", padx=2)
        tk.Label(options, text="粗细", bg="white", fg="#64748b", font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(9,3))
        self.width_box = ttk.Spinbox(options, from_=1, to=20, width=3, command=self._sync_width)
        self.width_box.set("4")
        self.width_box.pack(side="left")
        tk.Checkbutton(options, text="填充", variable=self.fill, bg="white", activebackground="white", font=("Microsoft YaHei UI",9), bd=0).pack(side="left", padx=8)
        tk.Label(options, text="圆角", bg="white", fg="#64748b", font=("Microsoft YaHei UI",9)).pack(side="left")
        ttk.Spinbox(options, from_=0, to=80, width=3, textvariable=self.radius).pack(side="left", padx=3)
        self._draw_toolbar()
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.move)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.window.bind("<Control-z>", lambda _e: self.undo())
        self.window.bind("<Control-y>", lambda _e: self.redo())
        self.window.bind("<Delete>", lambda _e: self.delete_selected())
        self.window.bind("<Escape>", lambda _e: self.cancel())
        self.window.bind("<Return>", lambda _e: self.finish())
        self.toolbar.bind("<Escape>", lambda _e: self.cancel())
        self.toolbar.bind("<Return>", lambda _e: self.finish())
    def _fit(self):
        sw, sh = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        max_w, max_h = sw - 24, sh - 120
        self.scale = min(1.0, max_w / self.base.width, max_h / self.base.height)
        self.view_w = max(1, round(self.base.width * self.scale))
        self.view_h = max(1, round(self.base.height * self.scale))
        self.canvas.configure(width=self.view_w, height=self.view_h)
        x,y = self.position or ((sw-self.view_w)//2, (sh-self.view_h-90)//2)
        self._place(self.window,x-self.BORDER,y-self.BORDER,self.view_w+2*self.BORDER,self.view_h+2*self.BORDER)
        tx=max(0,min(sw-self.toolbar_width,x+self.view_w-self.toolbar_width))
        ty=y+self.view_h+8
        if ty+84 > sh:
            ty=max(0,y-92)
        self._place(self.toolbar,tx,ty,self.toolbar_width,84)
        self.window.focus_force()

    @staticmethod
    def _place(window, x, y, width, height):
        window.geometry(f"{width}x{height}{x:+d}{y:+d}")
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            window.update_idletasks()
            user=ctypes.windll.user32
            user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
            user.GetAncestor.restype=wintypes.HWND
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowPos(user.GetAncestor(window.winfo_id(),2),wintypes.HWND(-1),x,y,width,height,0x10)

    def _color(self, color):
        self.color=color

    def _toolbar_click(self, event):
        index=self._toolbar_hit(event)
        if index is not None:
            self._hide_tip()
            self.tool_actions[index][2]()

    def _toolbar_hit(self, event):
        if not 6 <= event.y <= 36:
            return None
        return next((index for index,x in enumerate(self.button_positions) if x <= event.x <= x+self.BUTTON_SIZE), None)

    def _toolbar_leave(self, _event):
        self.hover_index=None
        self._hide_tip()
        self._draw_toolbar()

    def _hide_tip(self):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip=None

    def _toolbar_hover(self, event):
        index=self._toolbar_hit(event)
        if getattr(self,"hover_index",None) == index:
            return
        self.hover_index=index
        self._draw_toolbar()
        self._hide_tip()
        if index is not None:
            self.tooltip=tk.Toplevel(self.toolbar)
            self.tooltip.overrideredirect(True)
            self.tooltip.attributes("-topmost",True)
            text=self.tool_actions[index][0]
            if self.tool_actions[index][1].startswith("redact_"):
                text += " · 不可撤销"
            tk.Label(self.tooltip,text=text,bg="#111827",fg="white",padx=8,pady=4,font=("Microsoft YaHei UI",9)).pack()
            self.tooltip.geometry(f"+{event.x_root-20}+{event.y_root-36}")

    def _draw_toolbar(self):
        self.icons.delete("all")
        for x in self.group_separators:
            self.icons.create_line(x,10,x,33,fill="#cbd5e1")
        for index,(_label,tool,_action) in enumerate(self.tool_actions):
            x=self.button_positions[index]
            active=tool==self.tool
            hover=getattr(self,"hover_index",None)==index
            fill="#2563eb" if active else ("#dbeafe" if hover else "#f1f5f9")
            border="#2563eb" if active or hover else "#cbd5e1"
            if tool=="finish" and not active:
                fill="#dcfce7";border="#86efac"
            self.icons.create_rectangle(x,6,x+30,36,fill=fill,outline=border)
            color="white" if active else ("#15803d" if tool=="finish" else "#334155")
            self._draw_icon(tool,x+15,21,color)

    def _draw_icon(self, tool, x, y, color):
        canvas=self.icons
        def line(*points, **kwargs):
            canvas.create_line(*sum(([x+a,y+b] for a,b in points),[]),fill=color,width=2,capstyle="round",joinstyle="round",**kwargs)
        if tool=="select":
            line((-7,-8),(-7,7),(-2,3),(2,9));line((-7,-8),(6,2),(-2,3))
        elif tool=="rect":
            canvas.create_rectangle(x-8,y-7,x+8,y+7,outline=color,width=2)
        elif tool=="ellipse":
            canvas.create_oval(x-8,y-7,x+8,y+7,outline=color,width=2)
        elif tool in ("line","arrow"):
            line((-8,7),(7,-7))
            if tool=="arrow": line((0,-7),(7,-7),(7,0))
        elif tool in ("pencil","highlight"):
            canvas.create_polygon(x-7,y+4,x+3,y-7,x+7,y-3,x-3,y+8,outline=color,fill=color if tool=="highlight" else "",width=2)
            line((-7,4),(-8,9),(-3,8))
        elif tool=="text":
            line((-7,-7),(7,-7));line((0,-7),(0,8));line((-4,8),(4,8))
        elif tool=="number":
            canvas.create_oval(x-9,y-9,x+9,y+9,outline=color,width=2)
            canvas.create_text(x,y,text="1",fill=color,font=("Segoe UI",10,"bold"))
        elif tool=="redact_pixel":
            for a in (-6,0,6):
                for b in (-6,0,6):
                    canvas.create_rectangle(x+a-2,y+b-2,x+a+2,y+b+2,fill=color,outline="")
        elif tool=="redact_blur":
            for b in (-5,0,5):
                line((-8,b),(-4,b-2),(0,b),(4,b+2),(8,b))
        elif tool=="redact_solid":
            canvas.create_rectangle(x-8,y-7,x+8,y+7,fill=color,outline="")
        elif tool in ("undo","redo"):
            flip=-1 if tool=="redo" else 1
            line((-7*flip,-3),(2*flip,-3),(7*flip,1),(7*flip,6))
            line((-3*flip,-7),(-7*flip,-3),(-3*flip,1))
        elif tool=="delete":
            canvas.create_rectangle(x-5,y-4,x+5,y+8,outline=color,width=2)
            line((-8,-6),(8,-6));line((-2,-9),(2,-9))
            line((-2,-1),(-2,5));line((2,-1),(2,5))
        elif tool=="ocr":
            canvas.create_text(x,y,text="译",fill=color,font=("Microsoft YaHei UI",12,"bold"))
        elif tool=="finish":
            line((-8,0),(-2,6),(8,-7))
        elif tool=="cancel":
            line((-6,-6),(6,6));line((-6,6),(6,-6))

    def set_tool(self, tool):
        self.tool = tool
        self.selected = None
        self._draw_toolbar()
        if tool.startswith("redact_"):
            self.status.set("隐私遮盖会立即改写底层像素，并清空此前可恢复历史；此操作不可撤销。")
        else:
            self.status.set(f"当前工具：{dict((v,k) for k,v in TOOLS).get(tool, tool)}")

    def pick_color(self):
        color = colorchooser.askcolor(self.color, parent=self.window)[1]
        if color:
            self.color = color

    def _sync_width(self):
        try:
            self.width = max(1, min(20, int(self.width_box.get())))
        except ValueError:
            self.width = 4

    def _point(self, event):
        return (max(0, min(self.base.width, round((event.x-self.BORDER) / self.scale))),
                max(0, min(self.base.height, round((event.y-self.BORDER) / self.scale))))

    def _screen_point(self, point):
        return tuple(round(v * self.scale)+self.BORDER for v in point)

    def _snapshot(self):
        self.undo_stack.append(copy.deepcopy(self.annotations))
        self.redo_stack.clear()
    def press(self, event):
        self._sync_width()
        point = self._point(event)
        if self.tool == "select":
            self.selected = self._hit(point)
            self._render()
            return
        if self.tool in ("text", "number"):
            self._snapshot()
            if self.tool == "text":
                value = simpledialog.askstring("文字标注", "输入文字：", parent=self.window)
                if not value:
                    self.undo_stack.pop()
                    return
                self.annotations.append({"type":"text","p":point,"text":value,"color":self.color,"width":self.width})
            else:
                self.annotations.append({"type":"number","p":point,"text":str(self.sequence),"color":self.color,"width":self.width})
                self.sequence += 1
            self._render()
            return
        self.start = point
        self.current = {"type": self.tool, "points": [point], "color": self.color,
                        "width": self.width, "fill": bool(self.fill.get()), "radius": int(self.radius.get())}

    def move(self, event):
        if not self.current:
            return
        point = self._point(event)
        if self.tool in ("pencil", "highlight"):
            self.current["points"].append(point)
        else:
            if len(self.current["points"]) == 1:
                self.current["points"].append(point)
            else:
                self.current["points"][-1] = point
        self._render(self.current)

    def release(self, event):
        if not self.current:
            return
        point = self._point(event)
        if self.tool not in ("pencil", "highlight"):
            if len(self.current["points"]) == 1:
                self.current["points"].append(point)
            else:
                self.current["points"][-1] = point
        item, self.current = self.current, None
        if self.tool.startswith("redact_"):
            self._commit_redaction(item)
            return
        self._snapshot()
        self.annotations.append(item)
        self._render()
    def _hit(self, point):
        x, y = point
        for index in range(len(self.annotations)-1, -1, -1):
            item = self.annotations[index]
            pts = item.get("points") or [item.get("p"), item.get("p")]
            xs, ys = [p[0] for p in pts if p], [p[1] for p in pts if p]
            if xs and min(xs)-12 <= x <= max(xs)+12 and min(ys)-12 <= y <= max(ys)+12:
                return index
        return None

    def delete_selected(self):
        if self.selected is None or not (0 <= self.selected < len(self.annotations)):
            return
        self._snapshot()
        del self.annotations[self.selected]
        self.selected = None
        self._render()

    def undo(self):
        if not self.undo_stack:
            self.status.set("已到隐私提交边界；隐私遮盖不可撤销。")
            return
        self.redo_stack.append(copy.deepcopy(self.annotations))
        self.annotations = self.undo_stack.pop()
        self.selected = None
        self._render()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.annotations))
        self.annotations = self.redo_stack.pop()
        self.selected = None
        self._render()

    def _redact_box(self, item):
        if len(item["points"]) < 2:
            return None
        (x1,y1),(x2,y2)=item["points"][0],item["points"][-1]
        box=(max(0,min(x1,x2)),max(0,min(y1,y2)),min(self.base.width,max(x1,x2)),min(self.base.height,max(y1,y2)))
        return box if box[2]-box[0] >= 3 and box[3]-box[1] >= 3 else None
    def _commit_redaction(self, item):
        box = self._redact_box(item)
        if not box:
            return
        apply_redaction(self.base, box, item["type"], self.color if self.color else "#000000")
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.selected = None
        self.status.set("隐私遮盖已永久写入当前截图像素；不能撤销、删除或恢复原区域。")
        self._render()

    def _render(self, transient=None):
        flattened = self._flatten()
        display = flattened.resize((self.view_w,self.view_h), Image.Resampling.LANCZOS)
        flattened.close()
        self.photo = ImageTk.PhotoImage(display)
        display.close()
        self.canvas.delete("all")
        self.canvas.create_image(self.BORDER,self.BORDER,anchor="nw",image=self.photo)
        if self.selected is not None and self.selected < len(self.annotations):
            self._draw_canvas(self.annotations[self.selected], selected=True)
        if transient:
            self._draw_canvas(transient, selected=False)

    def _draw_canvas(self, item, selected=False):
        t=item["type"]; c=item.get("color",self.color); w=max(1,round(item.get("width",4)*self.scale))
        pts=[self._screen_point(p) for p in item.get("points",[])]
        outline="#00a8ff" if selected else c
        if t.startswith("redact_") and len(pts)>1:
            self.canvas.create_rectangle(*pts[0],*pts[-1],outline="#00a8ff",width=2,dash=(5,3))
        elif t=="rect" and len(pts)>1:
            self.canvas.create_rectangle(*pts[0],*pts[-1],outline=outline,width=w,fill=(c if item.get("fill") else ""))
        elif t=="ellipse" and len(pts)>1:
            self.canvas.create_oval(*pts[0],*pts[-1],outline=outline,width=w,fill=(c if item.get("fill") else ""))
        elif t in ("line","arrow") and len(pts)>1:
            self.canvas.create_line(*pts[0],*pts[-1],fill=outline,width=w,arrow=("last" if t=="arrow" else "none"))
        elif t in ("pencil","highlight") and len(pts)>1:
            self.canvas.create_line(*sum((tuple(p) for p in pts),()),fill=outline,
                                    width=max(w,8 if t=="highlight" else w),smooth=True,
                                    stipple=("gray50" if t=="highlight" else ""))
        elif t in ("text","number"):
            p=self._screen_point(item["p"])
            if t=="number":
                r=max(10,8+w);self.canvas.create_oval(p[0]-r,p[1]-r,p[0]+r,p[1]+r,fill=c,outline=c)
                self.canvas.create_text(*p,text=item["text"],fill="white",font=("Microsoft YaHei UI",max(10,10+w),"bold"))
            else:
                self.canvas.create_text(*p,anchor="nw",text=item["text"],fill=outline,font=("Microsoft YaHei UI",max(10,10+w)))

    def _flatten(self):
        out=self.base.copy()
        draw=ImageDraw.Draw(out,"RGBA")
        for item in self.annotations:
            t=item["type"]; c=item.get("color","#ff2d2d"); w=item.get("width",4); pts=item.get("points",[])
            fill=c if item.get("fill") else None
            if t=="rect" and len(pts)>1:
                xy=self._ordered_box(pts[0],pts[-1]); radius=max(0,item.get("radius",0))
                if radius: draw.rounded_rectangle(xy,radius=radius,outline=c,fill=fill,width=w)
                else: draw.rectangle(xy,outline=c,fill=fill,width=w)
            elif t=="ellipse" and len(pts)>1: draw.ellipse(self._ordered_box(pts[0],pts[-1]),outline=c,fill=fill,width=w)
            elif t in ("line","arrow") and len(pts)>1:
                draw.line([pts[0],pts[-1]],fill=c,width=w)
                if t=="arrow": self._arrow_head(draw,pts[0],pts[-1],c,w)
            elif t in ("pencil","highlight") and len(pts)>1:
                rgba=self._rgba(c,110 if t=="highlight" else 255)
                draw.line(pts,fill=rgba,width=max(w,10 if t=="highlight" else w),joint="curve")
            elif t=="text": draw.text(item["p"],item["text"],fill=c,font=self._font(14+w))
            elif t=="number":
                x,y=item["p"];r=max(11,8+w);draw.ellipse((x-r,y-r,x+r,y+r),fill=c)
                draw.text((x,y),item["text"],fill="white",font=self._font(12+w),anchor="mm")
        return out

    @staticmethod
    def _ordered_box(start, end):
        return (min(start[0],end[0]),min(start[1],end[1]),max(start[0],end[0]),max(start[1],end[1]))

    @staticmethod
    def _font(size):
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(str(fonts / name), size)
            except OSError:
                continue
        return ImageFont.load_default()
    @staticmethod
    def _rgba(color, alpha):
        value=color.lstrip("#")
        if len(value)==6:
            return tuple(int(value[i:i+2],16) for i in (0,2,4))+(alpha,)
        return (255,45,45,alpha)

    @staticmethod
    def _arrow_head(draw, start, end, color, width):
        import math
        x1,y1=start;x2,y2=end
        angle=math.atan2(y2-y1,x2-x1);size=max(10,width*3)
        left=(x2-size*math.cos(angle-math.pi/6),y2-size*math.sin(angle-math.pi/6))
        right=(x2-size*math.cos(angle+math.pi/6),y2-size*math.sin(angle+math.pi/6))
        draw.polygon([end,left,right],fill=color)

    def finish(self, action="copy"):
        image=self._flatten()
        self.base.close()
        self.base=None
        self._hide_tip()
        self.toolbar.destroy()
        self.window.destroy()
        self.done(image, action)

    def cancel(self):
        if self.base:
            self.base.close()
            self.base=None
        self._hide_tip()
        self.toolbar.destroy()
        self.window.destroy()
        self.cancel_cb()
