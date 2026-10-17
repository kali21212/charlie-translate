"""Native Windows notification-area tray for Charlie Translate.

No third-party tray runtime is used. The implementation is intentionally small:
it wraps Shell_NotifyIconW and a hidden Win32 message window via ctypes.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from pathlib import Path


if os.name == "nt":
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", GUID),
            ("hBalloonIcon", wintypes.HICON),
        ]


class SystemTray:
    WM_USER = 0x0400
    WM_COMMAND = 0x0111
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    CALLBACK_MESSAGE = WM_USER + 20

    NIM_ADD = 0
    NIM_DELETE = 2
    NIF_MESSAGE = 0x0001
    NIF_ICON = 0x0002
    NIF_TIP = 0x0004

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    LR_DEFAULTSIZE = 0x0040

    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    TPM_RIGHTBUTTON = 0x0002
    TPM_RETURNCMD = 0x0100
    TPM_NONOTIFY = 0x0080

    MENU_CAPTURE = 1001
    MENU_TRANSLATE = 1002
    MENU_SHOW = 1003
    MENU_FLOATING = 1004
    MENU_EXIT = 1099

    def __init__(
        self,
        icon_path,
        *,
        schedule,
        capture,
        translate,
        show_main,
        toggle_floating,
        floating_enabled,
        exit_app,
        tooltip="Charlie Translate",
    ):
        self.icon_path = Path(icon_path)
        self.schedule = schedule
        self.capture_action = capture
        self.translate_action = translate
        self.show_action = show_main
        self.toggle_floating_action = toggle_floating
        self.floating_enabled = floating_enabled
        self.exit_action = exit_app
        self.tooltip = str(tooltip)[:127]
        self.thread = None
        self.ready = threading.Event()
        self.hwnd = None
        self.hicon = None
        self.class_name = f"CharlieTranslateTray_{os.getpid()}"
        self._wndproc = None
        self.taskbar_created = 0
        self.error = None

    @property
    def available(self):
        return os.name == "nt"

    def start(self, timeout=3.0):
        if not self.available:
            return False
        if self.thread and self.thread.is_alive():
            return True
        self.ready.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="CharlieSystemTray",
            daemon=True,
        )
        self.thread.start()
        self.ready.wait(timeout)
        return bool(self.hwnd and not self.error)

    def _schedule(self, action):
        try:
            self.schedule(action)
        except Exception:
            pass

    def _run(self):
        try:
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            kernel32 = ctypes.windll.kernel32

            user32.DefWindowProcW.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
            ]
            user32.DefWindowProcW.restype = LRESULT
            user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
            user32.RegisterClassW.restype = wintypes.ATOM
            user32.CreateWindowExW.argtypes = [
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
            ]
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.LoadImageW.argtypes = [
                wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            ]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.CreatePopupMenu.restype = wintypes.HMENU
            user32.TrackPopupMenu.restype = wintypes.UINT
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            shell32.Shell_NotifyIconW.argtypes = [
                wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)
            ]
            shell32.Shell_NotifyIconW.restype = wintypes.BOOL

            self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

            @WNDPROC
            def wndproc(hwnd, msg, wparam, lparam):
                if msg == self.CALLBACK_MESSAGE:
                    event = int(lparam)
                    if event in (self.WM_LBUTTONUP, self.WM_LBUTTONDBLCLK):
                        self._schedule(self.show_action)
                        return 0
                    if event == self.WM_RBUTTONUP:
                        self._show_menu(hwnd)
                        return 0
                elif msg == self.WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                elif msg == self.WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                elif self.taskbar_created and msg == self.taskbar_created:
                    self._add_icon()
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            self._wndproc = wndproc
            hinstance = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.lpfnWndProc = wndproc
            wc.hInstance = hinstance
            wc.lpszClassName = self.class_name
            atom = user32.RegisterClassW(ctypes.byref(wc))
            if not atom and ctypes.get_last_error() != 1410:
                raise ctypes.WinError(ctypes.get_last_error())

            self.hwnd = user32.CreateWindowExW(
                0,
                self.class_name,
                "Charlie Translate Tray",
                0,
                0, 0, 0, 0,
                None, None, hinstance, None,
            )
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())

            icon_width = max(16, int(user32.GetSystemMetrics(49)))   # SM_CXSMICON
            icon_height = max(16, int(user32.GetSystemMetrics(50)))  # SM_CYSMICON
            self.hicon = user32.LoadImageW(
                None,
                str(self.icon_path),
                self.IMAGE_ICON,
                icon_width,
                icon_height,
                self.LR_LOADFROMFILE,
            )
            if not self.hicon:
                raise ctypes.WinError(ctypes.get_last_error())

            self._add_icon(shell32)
            self.ready.set()

            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self.error = exc
            self.ready.set()
        finally:
            try:
                self._delete_icon()
            except Exception:
                pass
            try:
                if self.hicon:
                    ctypes.windll.user32.DestroyIcon(self.hicon)
            except Exception:
                pass
            self.hicon = None
            self.hwnd = None

    def _notify_data(self):
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        data.uCallbackMessage = self.CALLBACK_MESSAGE
        data.hIcon = self.hicon
        data.szTip = self.tooltip
        return data

    def _add_icon(self, shell32=None):
        if not self.hwnd or not self.hicon:
            return False
        shell32 = shell32 or ctypes.windll.shell32
        data = self._notify_data()
        return bool(shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(data)))

    def _delete_icon(self):
        if not self.hwnd:
            return
        data = self._notify_data()
        ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(data))

    def _show_menu(self, hwnd):
        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, self.MF_STRING, self.MENU_CAPTURE, "截图并标注")
            user32.AppendMenuW(menu, self.MF_STRING, self.MENU_TRANSLATE, "截图识字并翻译")
            user32.AppendMenuW(menu, self.MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, self.MF_STRING, self.MENU_SHOW, "打开 Charlie Translate")
            label = "隐藏悬浮截图按钮" if self.floating_enabled() else "显示悬浮截图按钮"
            user32.AppendMenuW(menu, self.MF_STRING, self.MENU_FLOATING, label)
            user32.AppendMenuW(menu, self.MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, self.MF_STRING, self.MENU_EXIT, "退出 Charlie Translate")

            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(hwnd)
            command = user32.TrackPopupMenu(
                menu,
                self.TPM_RIGHTBUTTON | self.TPM_RETURNCMD | self.TPM_NONOTIFY,
                point.x,
                point.y,
                0,
                hwnd,
                None,
            )
            if command:
                self._dispatch_menu(int(command))
        finally:
            user32.DestroyMenu(menu)

    def _dispatch_menu(self, command):
        action = {
            self.MENU_CAPTURE: self.capture_action,
            self.MENU_TRANSLATE: self.translate_action,
            self.MENU_SHOW: self.show_action,
            self.MENU_FLOATING: self.toggle_floating_action,
            self.MENU_EXIT: self.exit_action,
        }.get(command)
        if action:
            self._schedule(action)

    def stop(self, timeout=2.0):
        if not self.available:
            return
        hwnd = self.hwnd
        if hwnd:
            try:
                ctypes.windll.user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self.thread and self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout)
