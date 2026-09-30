"""Validated, persistent Windows global hotkeys with rollback on conflicts."""
import json
from pathlib import Path

DEFAULTS = {"capture": "F1", "translate": "F2"}
IDS = {"capture": 0x4348, "translate": 0x4349}


def parse_hotkey(value):
    if not isinstance(value, str):
        raise ValueError("快捷键格式无效")
    parts = [part.strip().upper() for part in value.split("+")]
    modifiers = {"CTRL": 2, "ALT": 1, "SHIFT": 4}
    if not parts or any(p not in modifiers for p in parts[:-1]) or len(set(parts[:-1])) != len(parts[:-1]):
        raise ValueError("请按 F1–F12，或 Ctrl、Alt、Shift 与字母、数字的组合")
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
        key = "F" + str(int(key[1:]))
    else:
        raise ValueError("末尾按键须为字母、数字或 F1–F12")
    if len(parts) == 1 and not key.startswith("F"):
        raise ValueError("字母与数字须搭配 Ctrl、Alt 或 Shift；F1–F12 可单独使用")
    canonical = "+".join([p.title() for p in ("CTRL", "ALT", "SHIFT") if p in parts[:-1]] + [key])
    return canonical, sum(modifiers[p] for p in parts[:-1]) | 0x4000, vk


def event_hotkey(event, state=None):
    """Translate Tk key presses into one complete shortcut, not typed characters."""
    state = event.state if state is None else state
    key = event.keysym.upper()
    modifiers = []
    if state & 0x4:
        modifiers.append("Ctrl")
    if state & 0x20000:
        modifiers.append("Alt")
    if state & 0x1:
        modifiers.append("Shift")
    return parse_hotkey("+".join(modifiers + [key]))[0]


class Hotkeys:
    def __init__(self, directory, api):
        self.path = Path(directory) / "hotkeys.json"
        self.api = api
        self.values = dict(DEFAULTS)
        self.active = {}
        try:
            self.values = self.validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError):
            pass

    @staticmethod
    def validate(values):
        result = {name: parse_hotkey(values[name])[0] for name in IDS}
        if len(set(result.values())) != len(result):
            raise ValueError("截图与翻译不能使用同一个快捷键")
        return result

    def register(self, name, value):
        _, modifiers, key = parse_hotkey(value)
        if self.api and self.api.RegisterHotKey(None, IDS[name], modifiers, key):
            self.active[name] = value
            return True
        return False

    def start(self):
        for name, value in self.values.items():
            self.register(name, value)

    def close(self):
        for name in list(self.active):
            self.api.UnregisterHotKey(None, IDS[name])
        self.active.clear()

    def apply(self, values):
        values = self.validate(values)
        previous = dict(self.active)
        self.close()
        try:
            for name, value in values.items():
                if not self.register(name, value):
                    raise ValueError(f"{value} 已被占用或无法注册，请换一个组合")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except (OSError, ValueError):
            self.close()
            for name, value in previous.items():
                self.register(name, value)
            raise
        self.values = values


class WindowsHotkeyPump:
    """Own hotkeys on a dedicated Windows message thread; Tk cannot consume them."""
    def __init__(self):
        import queue
        import threading
        self.commands, self.events = queue.Queue(), queue.Queue()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            raise RuntimeError("快捷键接收线程启动失败")

    def _run(self):
        import ctypes
        import queue
        from ctypes import wintypes
        user = ctypes.windll.user32
        message = wintypes.MSG()
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self.ready.set()
        while True:
            try:
                command, args, result = self.commands.get(timeout=0.02)
                if command == "stop":
                    result.put(True)
                    return
                result.put(bool(getattr(user, command)(*args)))
            except queue.Empty:
                pass
            while user.PeekMessageW(ctypes.byref(message), None, 0x312, 0x312, 1):
                self.events.put(int(message.wParam))

    def _call(self, command, *args):
        import queue
        result = queue.Queue()
        self.commands.put((command, args, result))
        return result.get(timeout=3)

    def RegisterHotKey(self, *args):
        return self._call("RegisterHotKey", *args)

    def UnregisterHotKey(self, *args):
        return self._call("UnregisterHotKey", *args)

    def shutdown(self):
        self._call("stop")
        self.thread.join(timeout=3)
