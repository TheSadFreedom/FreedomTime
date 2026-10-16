"""FreedomTime — каждые 45 минут блокирует мышь на 7 минут."""

from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import os
import sys
import threading
import time
import warnings
import winreg
import winsound
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

import pystray
import tkinter as tk
from PIL import Image, ImageDraw

WORK_MINUTES = 45.0
BREAK_MINUTES = 7.0
WARN_MINUTES = 5.0
SNOOZE_MINUTES = 20.0
SKIP_HOLD_SECONDS = 3.0
TICK_MS = 100

BG = "#0d1117"
TITLEBAR = "#0d1117"
TITLEBAR_HOVER = "#21262d"
TITLEBAR_CLOSE_HOVER = "#c42b1c"
CARD = "#161b22"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#58a6ff"
BREAK_ACCENT = "#f0883e"
WARN_ACCENT = "#e3b341"
GREEN = "#3fb950"

WH_MOUSE_LL = 14
WM_QUIT = 0x0012
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_U = 0x55
VK_Q = 0x51

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    ctypes.c_uint,
    ctypes.c_uint,
]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    ctypes.c_uint,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.ClipCursor.argtypes = [ctypes.c_void_p]
user32.ClipCursor.restype = wintypes.BOOL
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.ShowCursor.argtypes = [wintypes.BOOL]
user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
]
user32.SystemParametersInfoW.restype = wintypes.BOOL
SPI_GETWORKAREA = 0x0030
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
ERROR_ALREADY_EXISTS = 183
AUTOSTART_NAME = "FreedomTime"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.ReleaseCapture.restype = wintypes.BOOL
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [
    wintypes.HWND,
    ctypes.c_uint,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.RedrawWindow.argtypes = [
    wintypes.HWND,
    ctypes.c_void_p,
    wintypes.HRGN,
    ctypes.c_uint,
]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowRect.restype = wintypes.BOOL

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWCP_ROUND = 2
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOCOPYBITS = 0x0100
SWP_FRAMECHANGED = 0x0020
GA_ROOT = 2
RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_FRAME = 0x0400
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100


def _colorref(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    red, green, blue = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return red | (green << 8) | (blue << 16)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    if getattr(sys, "frozen", False):
        folder = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "FreedomTime"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "config.json"
    return Path(__file__).resolve().parent / "freedom_time.json"


def _pythonw_path() -> Path:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    return exe


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{_pythonw_path()}" "{Path(__file__).resolve()}"'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def load_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_config(data: dict) -> None:
    try:
        config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


_mutex_handle = None


def already_running() -> bool:
    global _mutex_handle
    _mutex_handle = kernel32.CreateMutexW(None, True, "FreedomTime.SingleInstance")
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def format_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def virtual_screen() -> tuple[int, int, int, int]:
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


def work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return virtual_screen()


def beep_start() -> None:
    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass


def beep_end() -> None:
    try:
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


def make_tray_image(on_break: bool = False, warning: bool = False) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if on_break:
        fill = (240, 136, 62, 255)
    elif warning:
        fill = (227, 179, 65, 255)
    else:
        fill = (63, 185, 80, 255)
    draw.ellipse((2, 2, size - 3, size - 3), fill=fill)
    draw.ellipse((18, 18, size - 19, size - 19), fill=(13, 17, 23, 255))
    draw.pieslice((18, 18, size - 19, size - 19), start=-90, end=50, fill=fill)
    return img


class MouseBlocker:
    """Глобальный низкоуровневый хук мыши + ClipCursor."""

    def __init__(self) -> None:
        self._blocking = False
        self._hook: wintypes.HHOOK | None = None
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._cursor_hidden = False
        # Ссылка обязана жить, иначе ctypes соберёт callback сборщиком мусора.
        self._proc = HOOKPROC(self._low_level_mouse)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._pump, name="MouseHook", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3)

    def stop(self) -> None:
        self.unlock()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def lock(self) -> None:
        self._blocking = True
        self._clip_and_hide()

    def unlock(self) -> None:
        self._blocking = False
        self._unclip_and_show()

    def _low_level_mouse(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0 and self._blocking:
            return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _module_candidates(self) -> list[object]:
        names = (
            None,
            f"python{sys.version_info.major}{sys.version_info.minor}.dll",
            "python3.dll",
        )
        handles: list[object] = [None]
        for name in names:
            handle = kernel32.GetModuleHandleW(name)
            if handle and handle not in handles:
                handles.append(handle)
        return handles

    def _try_install(self) -> wintypes.HHOOK | None:
        for module in self._module_candidates():
            hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, module, 0)
            if hook:
                return hook
        return None

    def _pump(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = self._try_install()
        self._ready.set()
        if not self._hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _clip_and_hide(self) -> None:
        x, y, w, h = virtual_screen()
        cx = x + w // 2
        cy = y + h // 2
        user32.SetCursorPos(cx, cy)
        rect = wintypes.RECT(cx, cy, cx + 1, cy + 1)
        user32.ClipCursor(ctypes.byref(rect))
        if not self._cursor_hidden:
            while user32.ShowCursor(False) >= 0:
                pass
            self._cursor_hidden = True

    def _unclip_and_show(self) -> None:
        user32.ClipCursor(None)
        if self._cursor_hidden:
            while user32.ShowCursor(True) < 0:
                pass
            self._cursor_hidden = False


class AudioSilencer:
    """Глушит звук и микрофон по умолчанию. Работает в фоне, чтобы не замораживать окно."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token = 0
        self._saved: dict[str, bool] | None = None

    def silence(self) -> None:
        with self._lock:
            self._token += 1
            token = self._token
        threading.Thread(target=self._mute_worker, args=(token,), daemon=True, name="AudioMute").start()

    def keep_silenced(self) -> None:
        with self._lock:
            if self._saved is None:
                return
            token = self._token
        threading.Thread(target=self._mute_worker, args=(token,), daemon=True, name="AudioRemute").start()

    def restore(self) -> None:
        with self._lock:
            self._token += 1
            saved = self._saved
            self._saved = None
        if saved is None:
            return
        threading.Thread(target=self._restore_worker, args=(saved,), daemon=True, name="AudioRestore").start()

    def _mute_worker(self, token: int) -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                snapshot: dict[str, bool] = {}
                for device in self._default_devices():
                    volume = device.EndpointVolume
                    snapshot[device.id] = bool(volume.GetMute())
                    volume.SetMute(1, None)
                with self._lock:
                    if token != self._token:
                        return
                    if self._saved is None:
                        self._saved = snapshot
            finally:
                comtypes.CoUninitialize()
        except Exception:
            pass

    def _restore_worker(self, saved: dict[str, bool]) -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                for device in self._default_devices():
                    if device.id in saved:
                        device.EndpointVolume.SetMute(1 if saved[device.id] else 0, None)
            finally:
                comtypes.CoUninitialize()
        except Exception:
            pass

    def _default_devices(self) -> list:
        from pycaw.pycaw import AudioUtilities

        devices = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                speakers = AudioUtilities.GetSpeakers()
                if speakers is not None and getattr(speakers, "id", None):
                    devices.append(speakers)
            except Exception:
                pass
            try:
                raw = AudioUtilities.GetMicrophone()
                mic = AudioUtilities.CreateDevice(raw) if raw is not None else None
                if mic is not None and getattr(mic, "id", None):
                    devices.append(mic)
            except Exception:
                pass
        return devices


@dataclass
class Settings:
    work_seconds: float
    break_seconds: float
    warn_seconds: float
    snooze_seconds: float


class FreedomTimeApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.blocker = MouseBlocker()
        self.audio = AudioSilencer()
        atexit.register(self.audio.restore)
        self.on_break = False
        self.period_started = time.monotonic()
        self.esc_held = 0.0
        self._hotkey_armed = True
        self._quitting = False
        self._last_tray_title = ""
        self.pinned = True
        self._warning_shown = False
        self._last_icon_mode = "work"
        self._window_visible = True
        self._overlay_tick = 0
        self.icon: pystray.Icon | None = None
        self._config = load_config()
        self.autostart_enabled = bool(self._config.get("autostart", True))

        self.root = tk.Tk()
        self.root.title("FreedomTime")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._set_window_icon()
        self.pin_var = tk.BooleanVar(value=True)
        self.autostart_var = tk.BooleanVar(value=self.autostart_enabled)

        self._build_titlebar()
        self._build_panel()
        self.set_pinned(True)
        self.root.after(0, self._apply_window_chrome)
        self.overlay: tk.Toplevel | None = None
        self.overlay_time: tk.Label | None = None
        self.overlay_skip: tk.Label | None = None
        self.warn_win: tk.Toplevel | None = None
        self.warn_time: tk.Label | None = None

    def run(self) -> None:
        self._apply_autostart(self.autostart_enabled)
        self.blocker.start()
        self._start_tray()
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self._window_visible = True
        self.root.after(TICK_MS, self._tick)
        self.root.mainloop()

    def _set_window_icon(self) -> None:
        try:
            img = make_tray_image(False)
            if getattr(sys, "frozen", False):
                from PIL import ImageTk

                self._icon_photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self._icon_photo)
                return
            ico_path = app_dir() / "freedom_time.ico"
            img.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
            self.root.iconbitmap(default=str(ico_path))
        except Exception:
            pass

    def _start_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Показать окно", self._tray_show, default=True),
            pystray.MenuItem(
                "Перерыв сейчас",
                self._tray_break,
                enabled=lambda _item: not self.on_break,
            ),
            pystray.MenuItem(
                "Поверх всех окон",
                self._tray_pin,
                checked=lambda _item: self.pinned,
            ),
            pystray.MenuItem(
                "Запускать с Windows",
                self._tray_autostart,
                checked=lambda _item: self.autostart_enabled,
            ),
            pystray.MenuItem(
                self._snooze_label(),
                self._tray_snooze,
                enabled=lambda _item: self._can_snooze(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._tray_quit),
        )
        self.icon = pystray.Icon(
            "FreedomTime",
            make_tray_image(False),
            "FreedomTime",
            menu,
        )
        threading.Thread(target=self.icon.run, name="TrayIcon", daemon=True).start()

    def _notify_tray(self) -> None:
        if self.icon is None:
            return
        if not getattr(self.icon, "visible", False):
            self.root.after(200, self._notify_tray)
            return
        try:
            self.icon.notify(
                "Программа в области уведомлений (стрелка ^ на панели задач).",
                "FreedomTime",
            )
        except Exception:
            pass

    def _tray_call(self, fn) -> None:
        if self._quitting:
            return
        try:
            self.root.after(0, fn)
        except tk.TclError:
            pass

    def _tray_show(self, _icon=None, _item=None) -> None:
        self._tray_call(self.show_window)

    def _tray_break(self, _icon=None, _item=None) -> None:
        self._tray_call(self.start_break)

    def _tray_quit(self, _icon=None, _item=None) -> None:
        self._tray_call(self.quit_app)

    def _tray_pin(self, _icon=None, _item=None) -> None:
        self._tray_call(self.toggle_pin)

    def _tray_autostart(self, _icon=None, _item=None) -> None:
        self._tray_call(self.toggle_autostart)

    def _tray_snooze(self, _icon=None, _item=None) -> None:
        self._tray_call(self.snooze)

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.attributes("-topmost", self.pinned)
        self._apply_window_chrome()
        self.root.lift()
        self.root.focus_force()
        self._window_visible = True

    def hide_to_tray(self) -> None:
        if self.on_break:
            return
        self.root.withdraw()
        self._window_visible = False

    def toggle_pin(self) -> None:
        self.set_pinned(not self.pinned)

    def toggle_autostart(self) -> None:
        self._apply_autostart(not self.autostart_enabled)

    def _on_autostart_toggle(self) -> None:
        self._apply_autostart(bool(self.autostart_var.get()))

    def _apply_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
            self.autostart_enabled = enabled
        except OSError:
            self.autostart_enabled = is_autostart_enabled()
        if self.autostart_var.get() != self.autostart_enabled:
            self.autostart_var.set(self.autostart_enabled)
        self._config["autostart"] = self.autostart_enabled
        save_config(self._config)

    def set_pinned(self, pinned: bool) -> None:
        self.pinned = bool(pinned)
        if self.pin_var.get() != self.pinned:
            self.pin_var.set(self.pinned)
        self.root.attributes("-topmost", self.pinned)
        self._refresh_pin_button()
        if self.pinned:
            self.root.deiconify()
            self.root.lift()

    def _hwnd(self) -> int:
        inner = int(self.root.winfo_id())
        root = user32.GetAncestor(inner, GA_ROOT)
        return int(root) if root else inner

    def _apply_window_chrome(self) -> None:
        try:
            self.root.update_idletasks()
            hwnd = self._hwnd()
            dwmapi = ctypes.WinDLL("dwmapi")
            dark = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), 4
            )
            caption = ctypes.c_int(_colorref(TITLEBAR))
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), 4
            )
            text = ctypes.c_int(_colorref(TEXT))
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text), 4
            )
            corners = ctypes.c_int(DWMWCP_ROUND)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corners), 4
            )
            style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style & ~WS_CAPTION)
            user32.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOCOPYBITS,
            )
            user32.RedrawWindow(
                hwnd,
                None,
                None,
                RDW_INVALIDATE | RDW_ERASE | RDW_FRAME | RDW_ALLCHILDREN | RDW_UPDATENOW,
            )
        except Exception:
            pass

    def _build_titlebar(self) -> None:
        bar = tk.Frame(self.root, bg=TITLEBAR, height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        title = tk.Label(
            bar,
            text="  FreedomTime",
            bg=TITLEBAR,
            fg=TEXT,
            font=("Segoe UI", 10),
            anchor="w",
        )
        title.pack(side="left", fill="y")

        for widget in (bar, title):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)

        close_btn = tk.Label(
            bar,
            text="\uE8BB",
            font=("Segoe MDL2 Assets", 8),
            bg=TITLEBAR,
            fg=MUTED,
            width=4,
            cursor="hand2",
        )
        close_btn.pack(side="right", fill="y")
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(bg=TITLEBAR_CLOSE_HOVER, fg=TEXT))
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(bg=TITLEBAR, fg=MUTED))
        close_btn.bind("<Button-1>", lambda _e: self.hide_to_tray())

        min_btn = tk.Label(
            bar,
            text="\uE921",
            font=("Segoe MDL2 Assets", 8),
            bg=TITLEBAR,
            fg=MUTED,
            width=4,
            cursor="hand2",
        )
        min_btn.pack(side="right", fill="y")
        min_btn.bind("<Enter>", lambda _e: min_btn.configure(bg=TITLEBAR_HOVER, fg=TEXT))
        min_btn.bind("<Leave>", lambda _e: min_btn.configure(bg=TITLEBAR, fg=MUTED))
        min_btn.bind("<Button-1>", lambda _e: self.hide_to_tray())

        self.pin_btn = tk.Label(
            bar,
            text="\uE718",
            font=("Segoe MDL2 Assets", 8),
            bg=TITLEBAR,
            fg=MUTED,
            width=4,
            cursor="hand2",
        )
        self.pin_btn.pack(side="right", fill="y")
        self.pin_btn.bind("<Enter>", self._pin_enter)
        self.pin_btn.bind("<Leave>", self._pin_leave)
        self.pin_btn.bind("<Button-1>", lambda _e: self.toggle_pin())
        self._refresh_pin_button()

        tk.Frame(self.root, bg="#21262d", height=1).pack(fill="x")

    def _start_move(self, event: tk.Event) -> None:
        hwnd = self._hwnd()
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        self._drag_hwnd = hwnd
        self._drag_offset = (event.x_root - rect.left, event.y_root - rect.top)

    def _on_move(self, event: tk.Event) -> None:
        hwnd = getattr(self, "_drag_hwnd", 0)
        offset = getattr(self, "_drag_offset", None)
        if not hwnd or offset is None:
            return
        x = event.x_root - offset[0]
        y = event.y_root - offset[1]
        user32.SetWindowPos(
            hwnd,
            None,
            x,
            y,
            0,
            0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOCOPYBITS,
        )

    def _pin_enter(self, _event: tk.Event | None = None) -> None:
        self.pin_btn.configure(bg=TITLEBAR_HOVER, fg=ACCENT if self.pinned else TEXT)

    def _pin_leave(self, _event: tk.Event | None = None) -> None:
        self._refresh_pin_button()

    def _refresh_pin_button(self) -> None:
        if not hasattr(self, "pin_btn"):
            return
        if self.pinned:
            self.pin_btn.configure(text="\uE840", bg=TITLEBAR, fg=ACCENT)
        else:
            self.pin_btn.configure(text="\uE718", bg=TITLEBAR, fg=MUTED)

    def _build_panel(self) -> None:
        pad = tk.Frame(self.root, bg=BG, padx=28, pady=20)
        pad.pack()

        subtitle = tk.Label(
            pad,
            text=f"Работа {format_hms(self.settings.work_seconds)}  ·  "
            f"перерыв {format_hms(self.settings.break_seconds)}",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(0, 18))

        card = tk.Frame(pad, bg=CARD, padx=20, pady=16)
        card.pack(fill="x")

        self.status_label = tk.Label(
            card,
            text="Работа",
            bg=CARD,
            fg=GREEN,
            font=("Segoe UI", 12, "bold"),
        )
        self.status_label.pack(anchor="w")

        self.timer_label = tk.Label(
            card,
            text="00:00",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 32, "bold"),
        )
        self.timer_label.pack(anchor="w", pady=(4, 0))

        self.hint_label = tk.Label(
            card,
            text="до блокировки мыши",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        self.hint_label.pack(anchor="w")

        buttons = tk.Frame(pad, bg=BG)
        buttons.pack(fill="x", pady=(18, 0))

        self.break_btn = tk.Button(
            buttons,
            text="Перерыв сейчас",
            command=self.start_break,
            bg=CARD,
            fg=TEXT,
            activebackground="#21262d",
            activeforeground=TEXT,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10),
        )
        self.break_btn.pack(side="left")

        self.snooze_btn = tk.Button(
            buttons,
            text=self._snooze_label(),
            command=self.snooze,
            bg=CARD,
            fg=WARN_ACCENT,
            activebackground="#21262d",
            activeforeground=WARN_ACCENT,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10),
            state="disabled",
        )
        self.snooze_btn.pack(side="left", padx=(8, 0))

        hide_btn = tk.Button(
            buttons,
            text="В трей",
            command=self.hide_to_tray,
            bg=CARD,
            fg=MUTED,
            activebackground="#21262d",
            activeforeground=TEXT,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10),
        )
        hide_btn.pack(side="right")

        self.autostart_check = tk.Checkbutton(
            pad,
            text="Запускать вместе с Windows",
            variable=self.autostart_var,
            command=self._on_autostart_toggle,
            bg=BG,
            fg=MUTED,
            selectcolor=CARD,
            activebackground=BG,
            activeforeground=TEXT,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9),
        )
        self.autostart_check.pack(anchor="w", pady=(16, 0))

        hotkeys = tk.Label(
            pad,
            text="Иконка в трее (стрелка ^). Закрытие окна не завершает программу.\n"
            "Ctrl+Alt+U — снять блокировку   ·   Ctrl+Alt+Q — выход\n"
            "На перерыве удерживайте Escape 3 секунды, чтобы пропустить",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
            justify="left",
        )
        hotkeys.pack(anchor="w", pady=(16, 0))

    def remaining(self) -> float:
        elapsed = time.monotonic() - self.period_started
        total = self.settings.break_seconds if self.on_break else self.settings.work_seconds
        return total - elapsed

    def _snooze_label(self) -> str:
        sec = int(self.settings.snooze_seconds)
        if sec % 60 == 0:
            return f"Отложить на {sec // 60} мин"
        return f"Отложить на {sec} с"

    def _in_warning_window(self) -> bool:
        if self.on_break:
            return False
        left = self.remaining()
        return 0 < left <= self.settings.warn_seconds

    def _can_snooze(self) -> bool:
        return self._in_warning_window()

    def _set_snooze_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        try:
            self.snooze_btn.configure(state=state)
        except tk.TclError:
            pass

    def snooze(self) -> None:
        if not self._can_snooze():
            return
        self.period_started += self.settings.snooze_seconds
        self._warning_shown = False
        self._hide_warning()
        self._set_snooze_enabled(False)
        self.status_label.configure(text="Работа", fg=GREEN)
        self.hint_label.configure(text="до блокировки мыши", fg=MUTED)
        self._refresh_tray(force_icon=True)
        if self.icon is not None:
            try:
                self.icon.notify("Перерыв отложен", "FreedomTime")
            except Exception:
                pass

    def start_break(self) -> None:
        if self.on_break:
            return
        try:
            self._hide_warning()
            self._warning_shown = False
            self._set_snooze_enabled(False)
            self.on_break = True
            self.period_started = time.monotonic()
            self.esc_held = 0.0
            self._overlay_tick = 0
            self._show_overlay()
            self.break_btn.configure(state="disabled")
            self.status_label.configure(text="Перерыв", fg=BREAK_ACCENT)
            self.hint_label.configure(text="мышь, звук и микрофон выключены", fg=MUTED)
            self._refresh_tray(force_icon=True)
            self.blocker.lock()
            beep_start()
            self.audio.silence()
        except Exception as exc:
            self.on_break = False
            try:
                self.blocker.unlock()
            except Exception:
                pass
            try:
                self.audio.restore()
            except Exception:
                pass
            self._hide_overlay()
            self.break_btn.configure(state="normal")
            user32.MessageBoxW(None, str(exc), "FreedomTime", 0x10)

    def end_break(self) -> None:
        if not self.on_break:
            return
        self.on_break = False
        self.period_started = time.monotonic()
        self.esc_held = 0.0
        self._warning_shown = False
        self.audio.restore()
        self.blocker.unlock()
        self._hide_overlay()
        self._restore_root_after_overlay()
        self.break_btn.configure(state="normal")
        self.status_label.configure(text="Работа", fg=GREEN)
        self.hint_label.configure(text="до блокировки мыши", fg=MUTED)
        self._refresh_tray(force_icon=True)
        beep_end()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            self.audio.restore()
        except Exception:
            pass
        try:
            self.blocker.stop()
        except Exception:
            pass
        icon = self.icon
        self.icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _show_overlay(self) -> None:
        if self.overlay is not None:
            return
        self._map_root_for_popup()
        x, y, w, h = virtual_screen()
        if w <= 0 or h <= 0:
            w, h = 1920, 1080
            x, y = 0, 0
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.configure(bg=BG)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{w}x{h}+{x}+{y}")

        wrap = tk.Frame(overlay, bg=BG)
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            wrap,
            text="ПЕРЕРЫВ",
            bg=BG,
            fg=BREAK_ACCENT,
            font=("Segoe UI", 18, "bold"),
        ).pack()

        self.overlay_time = tk.Label(
            wrap,
            text=format_hms(self.settings.break_seconds),
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 96, "bold"),
        )
        self.overlay_time.pack(pady=(8, 16))

        tk.Label(
            wrap,
            text="Мышь, звук и микрофон выключены. Встань, разомнись, посмотри вдаль.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 16),
        ).pack()

        self.overlay_skip = tk.Label(
            wrap,
            text="Удерживайте Escape 3 секунды, чтобы пропустить",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 11),
        )
        self.overlay_skip.pack(pady=(28, 0))

        overlay.update_idletasks()
        overlay.deiconify()
        overlay.lift()
        overlay.attributes("-topmost", True)
        overlay.focus_force()
        overlay.update()
        self.overlay = overlay

    def _map_root_for_popup(self) -> None:
        # Toplevel не появляется, пока скрыт корневой Tk.
        self.root.deiconify()
        self.root.update_idletasks()

    def _restore_root_after_overlay(self) -> None:
        if self._window_visible:
            self.root.deiconify()
            self.root.attributes("-topmost", self.pinned)
        else:
            self.root.withdraw()

    def _hide_overlay(self) -> None:
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
            self.overlay_time = None
            self.overlay_skip = None

    def _show_warning(self) -> None:
        self._set_snooze_enabled(True)
        self.status_label.configure(text="Скоро перерыв", fg=WARN_ACCENT)
        self.hint_label.configure(text="можно отложить", fg=WARN_ACCENT)
        self._refresh_tray(force_icon=True)
        beep_start()
        if self.icon is not None:
            try:
                self.icon.notify(
                    f"Мышь заблокируется через {format_hms(self.remaining())}. "
                    f"{self._snooze_label()}.",
                    "Скоро перерыв",
                )
            except Exception:
                pass
        if self.warn_win is not None:
            return

        self._map_root_for_popup()
        win = tk.Toplevel(self.root)
        win.title("Скоро перерыв")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._hide_warning)

        pad = tk.Frame(win, bg=BG, padx=24, pady=20)
        pad.pack()
        tk.Label(
            pad,
            text="Скоро перерыв",
            bg=BG,
            fg=WARN_ACCENT,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.warn_time = tk.Label(
            pad,
            text=format_hms(self.remaining()),
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 28, "bold"),
        )
        self.warn_time.pack(anchor="w", pady=(4, 8))
        tk.Label(
            pad,
            text="Мышь будет заблокирована. Можно отложить перерыв.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        buttons = tk.Frame(pad, bg=BG)
        buttons.pack(fill="x", pady=(16, 0))
        tk.Button(
            buttons,
            text=self._snooze_label(),
            command=self.snooze,
            bg=CARD,
            fg=WARN_ACCENT,
            activebackground="#21262d",
            activeforeground=WARN_ACCENT,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10),
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Закрыть",
            command=self._hide_warning,
            bg=CARD,
            fg=MUTED,
            activebackground="#21262d",
            activeforeground=TEXT,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10),
        ).pack(side="right")

        win.update_idletasks()
        ww = win.winfo_reqwidth()
        wh = win.winfo_reqheight()
        ax, ay, aw, ah = work_area()
        win.geometry(f"{ww}x{wh}+{ax + aw - ww - 16}+{ay + ah - wh - 16}")
        self.warn_win = win

    def _hide_warning(self) -> None:
        if self.warn_win is not None:
            try:
                self.warn_win.destroy()
            except tk.TclError:
                pass
            self.warn_win = None
            self.warn_time = None

    def _tick(self) -> None:
        try:
            self._update()
        except Exception:
            self.blocker.unlock()
            raise
        if self.root.winfo_exists():
            self.root.after(TICK_MS, self._tick)

    def _update(self) -> None:
        left = self.remaining()
        self.timer_label.configure(text=format_hms(left))
        self._refresh_tray()

        if self.on_break:
            if self.overlay is not None:
                self.overlay.attributes("-topmost", True)
                self.overlay.lift()
                if self.overlay_time is not None:
                    self.overlay_time.configure(text=format_hms(left))
            self.blocker.lock()
            self._overlay_tick += 1
            if self._overlay_tick % 20 == 0:
                self.audio.keep_silenced()
            self._handle_skip_and_hotkeys()
            if left <= 0:
                self.end_break()
            return

        self._handle_skip_and_hotkeys()
        if left <= 0:
            self.start_break()
            return
        if left <= self.settings.warn_seconds:
            if not self._warning_shown:
                self._warning_shown = True
                self._show_warning()
            else:
                self._set_snooze_enabled(True)
            if self.warn_time is not None:
                self.warn_time.configure(text=format_hms(left))
            if self.warn_win is not None:
                try:
                    self.warn_win.attributes("-topmost", True)
                except tk.TclError:
                    self.warn_win = None
                    self.warn_time = None
            self.status_label.configure(text="Скоро перерыв", fg=WARN_ACCENT)
            self.hint_label.configure(text="можно отложить", fg=WARN_ACCENT)
        else:
            self._set_snooze_enabled(False)

    def _handle_skip_and_hotkeys(self) -> None:
        ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        u = bool(user32.GetAsyncKeyState(VK_U) & 0x8000)
        q = bool(user32.GetAsyncKeyState(VK_Q) & 0x8000)
        esc = bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)

        combo = ctrl and alt and (u or q)
        if combo and self._hotkey_armed:
            self._hotkey_armed = False
            if q:
                self.quit_app()
                return
            if u and self.on_break:
                self.end_break()
                return
        if not combo:
            self._hotkey_armed = True

        if self.on_break and esc:
            self.esc_held += TICK_MS / 1000.0
            remain = max(0.0, SKIP_HOLD_SECONDS - self.esc_held)
            if self.overlay_skip is not None:
                self.overlay_skip.configure(
                    text=f"Пропуск через {remain:.1f} с…",
                    fg=BREAK_ACCENT,
                )
            if self.esc_held >= SKIP_HOLD_SECONDS:
                self.end_break()
        else:
            self.esc_held = 0.0
            if self.on_break and self.overlay_skip is not None:
                self.overlay_skip.configure(
                    text="Удерживайте Escape 3 секунды, чтобы пропустить",
                    fg=MUTED,
                )

    def _refresh_tray(self, force_icon: bool = False) -> None:
        if self.icon is None:
            return
        left = self.remaining()
        warning = self._in_warning_window()
        if self.on_break:
            mode = "Перерыв"
        elif warning:
            mode = "Скоро перерыв"
        else:
            mode = "Работа"
        title = f"FreedomTime — {mode} {format_hms(left)}"
        if title != self._last_tray_title:
            self.icon.title = title
            self._last_tray_title = title
        icon_mode = "break" if self.on_break else ("warn" if warning else "work")
        if force_icon or icon_mode != self._last_icon_mode:
            try:
                self.icon.icon = make_tray_image(self.on_break, warning)
                self._last_icon_mode = icon_mode
            except Exception:
                pass


def parse_args(argv: list[str]) -> Settings:
    parser = argparse.ArgumentParser(description="FreedomTime — принудительные перерывы")
    parser.add_argument("--work", type=float, default=WORK_MINUTES, help="Минуты работы")
    parser.add_argument("--break", dest="brk", type=float, default=BREAK_MINUTES, help="Минуты перерыва")
    parser.add_argument("--test", action="store_true", help="Короткий цикл для проверки предупреждения")
    args = parser.parse_args(argv)
    if args.test:
        return Settings(
            work_seconds=20.0,
            break_seconds=10.0,
            warn_seconds=8.0,
            snooze_seconds=15.0,
        )
    if args.work <= 0 or args.brk <= 0:
        parser.error("Интервалы должны быть больше нуля")
    return Settings(
        work_seconds=args.work * 60.0,
        break_seconds=args.brk * 60.0,
        warn_seconds=WARN_MINUTES * 60.0,
        snooze_seconds=SNOOZE_MINUTES * 60.0,
    )


def main() -> None:
    if sys.platform != "win32":
        print("FreedomTime работает только в Windows")
        sys.exit(1)
    _enable_dpi_awareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FreedomTime.BreakEnforcer")
    except Exception:
        pass
    if already_running():
        user32.MessageBoxW(None, "FreedomTime уже запущена.", "FreedomTime", 0x40)
        sys.exit(0)
    settings = parse_args(sys.argv[1:])
    app = FreedomTimeApp(settings)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            user32.MessageBoxW(None, str(exc), "FreedomTime", 0x10)
        except Exception:
            print(exc, file=sys.stderr)
        sys.exit(1)
