"""FreedomTime — перерывы по таймеру: блокировка экрана или напоминание."""

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
import tkinter.font as tkfont
from PIL import Image, ImageDraw

WORK_MINUTES = 45.0
BREAK_MINUTES = 7.0
WARN_MINUTES = 5.0
SNOOZE_MINUTES = 20.0
SKIP_HOLD_SECONDS = 3.0
TICK_MS = 100

BG = "#0e1014"
TITLEBAR = "#0e1014"
TITLEBAR_HOVER = "#262a34"
TITLEBAR_CLOSE_HOVER = "#e5484d"
CARD = "#171a21"
BORDER = "#2c313c"
HOVER = "#242833"
TEXT = "#f4f5f7"
MUTED = "#979eab"
ACCENT = "#7c93ff"
ACCENT_HOVER = "#6b84f7"
BREAK_ACCENT = "#ff8b5a"
WARN_ACCENT = "#f0c14d"
GREEN = "#3ecf8e"
ERROR = "#ff6b6b"
SELECTED = "#1a2033"
MODE_LOCK = "lock"
MODE_REMIND = "remind"
MAX_MINUTES = 600.0

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


def ui_font(size: int, weight: str = "normal") -> tuple:
    if weight == "bold":
        return ("Segoe UI", size, "bold")
    return ("Segoe UI", size)


def _rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255


def paint_round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs):
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class CountdownRing(tk.Canvas):
    def __init__(self, parent: tk.Misc, size: int = 208, font_size: int = 28, bg: str = BG) -> None:
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self._size = size
        self._font_size = font_size
        self.set(1, GREEN, "00:00")

    def set(self, fraction: float, color: str, label: str) -> None:
        self.delete("all")
        size = self._size
        pad = max(10, int(size * 0.07))
        width = max(7, int(size * 0.034))
        fraction = max(0.0, min(1.0, fraction))
        self.create_oval(pad, pad, size - pad, size - pad, outline=BORDER, width=width)
        if fraction > 0.004:
            self.create_arc(
                pad,
                pad,
                size - pad,
                size - pad,
                start=90,
                extent=-359.9 * fraction,
                style="arc",
                outline=color,
                width=width,
            )
        self.create_text(
            size / 2,
            size / 2 + 1,
            text=label,
            fill=TEXT,
            font=ui_font(self._font_size, "bold"),
        )


class PillButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command=None,
        *,
        fill: str = CARD,
        fg: str = TEXT,
        hover: str | None = None,
        bg: str = BG,
    ) -> None:
        self._text = text
        self._command = command
        self._fill = fill
        self._fg = fg
        self._hover_fill = hover or HOVER
        self._bg = bg
        self._state = "normal"
        self._hovered = False
        self._font = ui_font(10)
        width = self._text_width() + 36
        super().__init__(
            parent,
            width=width,
            height=36,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._redraw()

    def _text_width(self) -> int:
        return tkfont.Font(font=self._font).measure(self._text)

    def _on_enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self._redraw()

    def _on_click(self, _event: tk.Event) -> None:
        if self._state == "disabled" or self._command is None:
            return
        self._command()

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
        state = kwargs.pop("state", None)
        text = kwargs.pop("text", None)
        if state is not None:
            self._state = state
        if text is not None:
            self._text = text
            super().configure(width=self._text_width() + 36)
        if kwargs:
            super().configure(**kwargs)
        cursor = "arrow" if self._state == "disabled" else "hand2"
        super().configure(cursor=cursor)
        self._redraw()

    config = configure

    def _redraw(self) -> None:
        self.delete("all")
        width = int(self.cget("width"))
        height = int(self.cget("height"))
        disabled = self._state == "disabled"
        fill = CARD if disabled else (self._hover_fill if self._hovered else self._fill)
        fg = MUTED if disabled else self._fg
        paint_round_rect(self, 1, 1, width - 1, height - 1, 18, fill=fill, outline="")
        self.create_text(width / 2, height / 2, text=self._text, fill=fg, font=self._font)


class Toggle(tk.Canvas):
    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar, bg: str = CARD) -> None:
        super().__init__(parent, width=42, height=24, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.variable = variable
        self._bg = bg
        self.variable.trace_add("write", self._on_var)
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _on_var(self, *_args) -> None:
        try:
            self._draw()
        except tk.TclError:
            pass

    def _toggle(self, _event: tk.Event | None = None) -> None:
        self.variable.set(not bool(self.variable.get()))

    def _draw(self) -> None:
        self.delete("all")
        on = bool(self.variable.get())
        paint_round_rect(self, 1, 2, 41, 22, 10, fill=ACCENT if on else "#3a4050", outline="")
        knob = 23 if on else 4
        self.create_oval(knob, 5, knob + 14, 19, fill="#f7f8fb", outline="")


class StepButton(tk.Canvas):
    def __init__(self, parent: tk.Misc, text: str, command, bg: str = CARD) -> None:
        super().__init__(parent, width=28, height=28, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._text = text
        self._hover = False
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    def _on_click(self, _event: tk.Event) -> None:
        self._command()

    def _on_enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        paint_round_rect(self, 1, 1, 27, 27, 8, fill="#2c3140" if self._hover else HOVER, outline="")
        self.create_text(14, 14, text=self._text, fill=TEXT, font=ui_font(14))


def make_tray_image(on_break: bool = False, warning: bool = False) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if on_break:
        fill = _rgba(BREAK_ACCENT)
    elif warning:
        fill = _rgba(WARN_ACCENT)
    else:
        fill = _rgba(GREEN)
    draw.ellipse((2, 2, size - 3, size - 3), fill=fill)
    draw.ellipse((18, 18, size - 19, size - 19), fill=_rgba(BG))
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


def positive_float(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        number = float(value)
    except ValueError:
        return default
    if number <= 0:
        return default
    return number


def warn_seconds_for(work_seconds: float) -> float:
    warn = WARN_MINUTES * 60.0
    if work_seconds > warn + 1:
        return warn
    return max(1.0, work_seconds * 0.5)


def format_minutes(seconds: float) -> str:
    minutes = seconds / 60.0
    if abs(minutes - round(minutes)) < 1e-6:
        return str(int(round(minutes)))
    return f"{minutes:.2f}".rstrip("0").rstrip(".")


def make_settings(
    work_minutes: float,
    break_minutes: float,
    mode: str,
    snooze_seconds: float | None = None,
) -> Settings:
    if mode not in (MODE_LOCK, MODE_REMIND):
        mode = MODE_LOCK
    work_seconds = work_minutes * 60.0
    return Settings(
        work_seconds=work_seconds,
        break_seconds=break_minutes * 60.0,
        warn_seconds=warn_seconds_for(work_seconds),
        snooze_seconds=SNOOZE_MINUTES * 60.0 if snooze_seconds is None else snooze_seconds,
        mode=mode,
    )


def settings_from_config(config: dict) -> Settings:
    mode = config.get("mode")
    if mode not in (MODE_LOCK, MODE_REMIND):
        mode = MODE_LOCK
    return make_settings(
        positive_float(config.get("work_minutes"), WORK_MINUTES),
        positive_float(config.get("break_minutes"), BREAK_MINUTES),
        mode,
    )


@dataclass
class Settings:
    work_seconds: float
    break_seconds: float
    warn_seconds: float
    snooze_seconds: float
    mode: str = MODE_LOCK


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
        self.overlay_ring: CountdownRing | None = None
        self.warn_win: tk.Toplevel | None = None
        self.warn_time: tk.Label | None = None
        self.warn_body: tk.Label | None = None
        self.remind_win: tk.Toplevel | None = None
        self.remind_time: tk.Label | None = None
        self._settings_visible = False
        self._main_width = 0

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
            pystray.MenuItem("Настройки", self._tray_settings),
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

    def _tray_settings(self, _icon=None, _item=None) -> None:
        self._tray_call(self.open_settings)

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
        if self.on_break and self.settings.mode == MODE_LOCK:
            return
        self.root.withdraw()
        self._window_visible = False

    def toggle_pin(self) -> None:
        self.set_pinned(not self.pinned)

    def toggle_autostart(self) -> None:
        self._apply_autostart(not self.autostart_enabled)

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
        bar = tk.Frame(self.root, bg=TITLEBAR, height=42)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        mark = tk.Label(bar, text="●", bg=TITLEBAR, fg=GREEN, font=ui_font(8))
        mark.pack(side="left", padx=(16, 0))
        title = tk.Label(
            bar,
            text="FreedomTime",
            bg=TITLEBAR,
            fg=TEXT,
            font=ui_font(10, "bold"),
            anchor="w",
        )
        title.pack(side="left", padx=(8, 0), fill="y")

        for widget in (bar, mark, title):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)

        close_btn = self._caption_button(bar, "\uE8BB", self.hide_to_tray, close=True)
        close_btn.pack(side="right", fill="y")
        min_btn = self._caption_button(bar, "\uE921", self.hide_to_tray)
        min_btn.pack(side="right", fill="y")
        self.pin_btn = self._caption_button(bar, "\uE718", self.toggle_pin)
        self.pin_btn.pack(side="right", fill="y")
        self._refresh_pin_button()

    def _caption_button(self, parent: tk.Misc, glyph: str, command, close: bool = False) -> tk.Label:
        button = tk.Label(
            parent,
            text=glyph,
            font=("Segoe MDL2 Assets", 9),
            bg=TITLEBAR,
            fg=MUTED,
            width=5,
            cursor="hand2",
        )

        def on_enter(_event: tk.Event) -> None:
            if close:
                button.configure(bg=TITLEBAR_CLOSE_HOVER, fg=TEXT)
            elif button is self.pin_btn and self.pinned:
                button.configure(bg=TITLEBAR_HOVER, fg=ACCENT)
            else:
                button.configure(bg=TITLEBAR_HOVER, fg=TEXT)

        def on_leave(_event: tk.Event) -> None:
            if button is getattr(self, "pin_btn", None):
                self._refresh_pin_button()
                return
            button.configure(bg=TITLEBAR, fg=MUTED)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<Button-1>", lambda _event: command())
        return button

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

    def _refresh_pin_button(self) -> None:
        if not hasattr(self, "pin_btn"):
            return
        if self.pinned:
            self.pin_btn.configure(text="\uE840", bg=TITLEBAR, fg=ACCENT)
        else:
            self.pin_btn.configure(text="\uE718", bg=TITLEBAR, fg=MUTED)

    def _build_panel(self) -> None:
        self.main_frame = tk.Frame(self.root, bg=BG)
        self.main_frame.pack(fill="both", expand=True)
        pad = tk.Frame(self.main_frame, bg=BG, padx=32, pady=22)
        pad.pack(fill="both", expand=True)

        self.subtitle = tk.Label(
            pad,
            text=self._schedule_text(),
            bg=BG,
            fg=MUTED,
            font=ui_font(9),
            justify="center",
        )
        self.subtitle.pack(pady=(0, 8))

        self.ring = CountdownRing(pad, size=208, font_size=28)
        self.ring.pack(pady=(4, 2))
        self.ring.set(1, GREEN, format_hms(self.settings.work_seconds))

        self.timer_label = tk.Label(pad, text=format_hms(self.settings.work_seconds), bg=BG, fg=TEXT)

        self.status_label = tk.Label(
            pad,
            text="Работа",
            bg=BG,
            fg=GREEN,
            font=ui_font(12, "bold"),
        )
        self.status_label.pack(pady=(8, 0))

        self.hint_label = tk.Label(
            pad,
            text=self._work_hint(),
            bg=BG,
            fg=MUTED,
            font=ui_font(10),
        )
        self.hint_label.pack(pady=(2, 0))

        buttons = tk.Frame(pad, bg=BG)
        buttons.pack(fill="x", pady=(22, 0))

        actions = tk.Frame(buttons, bg=BG)
        actions.pack(side="left")
        self.break_btn = PillButton(actions, "Перерыв сейчас", self.start_break, fill=CARD, fg=TEXT)
        self.break_btn.pack(side="left")
        self.snooze_btn = PillButton(
            actions,
            self._snooze_label(),
            self.snooze,
            fill=CARD,
            fg=WARN_ACCENT,
        )
        self.snooze_btn.pack(side="left", padx=(8, 0))
        self.snooze_btn.configure(state="disabled")

        settings_btn = PillButton(buttons, "Настройки", self.open_settings, fill=CARD, fg=TEXT)
        settings_btn.pack(side="right")

        self.hotkeys_label = tk.Label(
            pad,
            text=self._hotkeys_text(),
            bg=BG,
            fg=MUTED,
            font=ui_font(8),
            justify="center",
            wraplength=420,
        )
        self.hotkeys_label.pack(pady=(18, 0))
        self._build_settings_view()

    def _schedule_text(self) -> str:
        mode = "блокировка" if self.settings.mode == MODE_LOCK else "напоминание"
        return (
            f"Работа {format_hms(self.settings.work_seconds)}  ·  "
            f"перерыв {format_hms(self.settings.break_seconds)}  ·  {mode}"
        )

    def _work_hint(self) -> str:
        if self.settings.mode == MODE_LOCK:
            return "до блокировки мыши"
        return "до напоминания"

    def _break_hint(self) -> str:
        if self.settings.mode == MODE_LOCK:
            return "мышь, звук и микрофон выключены"
        return "напоминание о перерыве"

    def _warning_body(self) -> str:
        if self.settings.mode == MODE_LOCK:
            return "Мышь будет заблокирована. Можно отложить перерыв."
        return "Появится напоминание. Можно отложить перерыв."

    def _warning_notify(self) -> str:
        if self.settings.mode == MODE_LOCK:
            what = "Мышь заблокируется"
        else:
            what = "Появится напоминание"
        return f"{what} через {format_hms(self.remaining())}. {self._snooze_label()}."

    def _hotkeys_text(self) -> str:
        if self.settings.mode == MODE_LOCK:
            skip = "На перерыве удерживайте Escape 3 секунды, чтобы пропустить"
        else:
            skip = "В режиме напоминания окно можно закрыть и продолжить работу"
        return (
            "Иконка в трее (стрелка ^). Закрытие окна не завершает программу.\n"
            "Ctrl+Alt+U — закончить перерыв   ·   Ctrl+Alt+Q — выход\n"
            + skip
        )

    def _refresh_schedule_labels(self) -> None:
        self.subtitle.configure(text=self._schedule_text())
        self.hotkeys_label.configure(text=self._hotkeys_text())

    def _persist_settings(self) -> None:
        self._config["autostart"] = self.autostart_enabled
        self._config["work_minutes"] = self.settings.work_seconds / 60.0
        self._config["break_minutes"] = self.settings.break_seconds / 60.0
        self._config["mode"] = self.settings.mode
        save_config(self._config)

    def _apply_runtime_settings(self, new: Settings) -> None:
        old_mode = self.settings.mode
        self.settings = new
        self._refresh_schedule_labels()
        if self.on_break and old_mode != new.mode:
            self._switch_break_mode()
            return
        if self.on_break:
            self.hint_label.configure(text=self._break_hint(), fg=MUTED)
            return
        if self._in_warning_window():
            self.hint_label.configure(text="можно отложить", fg=WARN_ACCENT)
            self._set_snooze_enabled(True)
            if self.warn_body is not None:
                self.warn_body.configure(text=self._warning_body())
            return
        self._warning_shown = False
        self._hide_warning()
        self._set_snooze_enabled(False)
        self.status_label.configure(text="Работа", fg=GREEN)
        self.hint_label.configure(text=self._work_hint(), fg=MUTED)

    def _switch_break_mode(self) -> None:
        if self.settings.mode == MODE_LOCK:
            self._hide_reminder()
            self.hint_label.configure(text=self._break_hint(), fg=MUTED)
            self._show_overlay()
            self.blocker.lock()
            self.audio.silence()
            return
        self.audio.restore()
        self.blocker.unlock()
        self._hide_overlay()
        self._restore_root_after_overlay()
        self.hint_label.configure(text=self._break_hint(), fg=MUTED)
        self._show_reminder()

    def open_settings(self) -> None:
        if self._quitting or (self.on_break and self.settings.mode == MODE_LOCK):
            return
        self.show_window()
        self._load_settings_form()
        if self._settings_visible:
            self._work_entry.focus_set()
            return
        self.root.update_idletasks()
        self._main_width = max(self._main_width, self.root.winfo_width(), self.root.winfo_reqwidth())
        self.main_frame.pack_forget()
        self.settings_frame.pack(fill="both", expand=True)
        self._settings_visible = True
        self.root.bind("<Escape>", self._on_settings_escape)
        self._fit_window()
        self._apply_window_chrome()
        self._work_entry.focus_set()

    def _build_settings_view(self) -> None:
        self.settings_frame = tk.Frame(self.root, bg=BG)
        pad = tk.Frame(self.settings_frame, bg=BG, padx=32, pady=22)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Настройки", bg=BG, fg=TEXT, font=ui_font(20, "bold")).pack(anchor="w")
        tk.Label(
            pad,
            text="Расписание и то, как приложение зовёт на перерыв",
            bg=BG,
            fg=MUTED,
            font=ui_font(9),
        ).pack(anchor="w", pady=(4, 0))

        schedule = tk.Frame(pad, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        schedule.pack(fill="x", pady=(18, 0))
        self._settings_autostart = tk.BooleanVar(value=self.autostart_enabled)
        self._switch_row(schedule, "Запускать вместе с Windows")
        self._settings_divider(schedule)
        self._work_entry = self._minutes_row(schedule, "Время работы")
        self._settings_divider(schedule)
        self._break_entry = self._minutes_row(schedule, "Время перерыва")
        self._work_entry.insert(0, format_minutes(self.settings.work_seconds))
        self._break_entry.insert(0, format_minutes(self.settings.break_seconds))

        tk.Label(pad, text="Режим", bg=BG, fg=MUTED, font=ui_font(9)).pack(anchor="w", pady=(18, 8))

        modes = tk.Frame(pad, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        modes.pack(fill="x")
        self._mode_var = tk.StringVar(value=self.settings.mode)
        self._mode_cards: dict[str, tuple[tk.Frame, tk.Frame, tk.Frame, tk.Label, tk.Label, tk.Canvas]] = {}
        options = (
            (MODE_LOCK, "Блокировка экрана", "Мышь, звук и микрофон выключаются"),
            (MODE_REMIND, "Напоминание", "Окно с таймером, работать можно"),
        )
        for index, (value, title, detail) in enumerate(options):
            if index:
                self._settings_divider(modes)
            self._mode_row(modes, value, title, detail)
        self._paint_mode_cards()

        self._settings_error = tk.Label(
            pad,
            text="",
            bg=BG,
            fg=ERROR,
            font=ui_font(9),
            wraplength=420,
            justify="left",
            anchor="w",
        )

        self._settings_buttons = tk.Frame(pad, bg=BG)
        self._settings_buttons.pack(fill="x", pady=(18, 0))
        actions = tk.Frame(self._settings_buttons, bg=BG)
        actions.pack(side="right")
        PillButton(actions, "Отмена", self._hide_settings, fill=CARD, fg=MUTED).pack(side="left")
        PillButton(
            actions,
            "Сохранить",
            self._save_settings_dialog,
            fill=ACCENT,
            hover=ACCENT_HOVER,
            fg="#f7f8ff",
        ).pack(side="left", padx=(8, 0))

    def _settings_divider(self, parent: tk.Misc) -> None:
        line = tk.Frame(parent, bg=BORDER, height=1)
        line.pack_propagate(False)
        line.pack(fill="x")

    def _switch_row(self, parent: tk.Misc, caption: str) -> None:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=16, pady=14)
        tk.Label(row, text=caption, bg=CARD, fg=TEXT, font=ui_font(10)).pack(side="left")
        Toggle(row, self._settings_autostart, bg=CARD).pack(side="right")

    def _minutes_row(self, parent: tk.Misc, caption: str) -> tk.Entry:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=16, pady=10)
        tk.Label(row, text=caption, bg=CARD, fg=TEXT, font=ui_font(10)).pack(side="left")
        cluster = tk.Frame(row, bg=CARD)
        cluster.pack(side="right")
        shell = tk.Frame(cluster, bg=BORDER)
        entry = tk.Entry(
            shell,
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=ui_font(12),
            width=4,
            justify="center",
            selectbackground=ACCENT,
            selectforeground="#0e1014",
        )
        entry.pack(padx=1, pady=1, ipady=4, ipadx=4)
        entry.bind("<Return>", lambda _event: self._save_settings_dialog())
        entry.bind("<FocusIn>", lambda _event, border=shell: border.configure(bg=ACCENT))
        entry.bind("<FocusOut>", lambda _event, border=shell: border.configure(bg=BORDER))
        StepButton(cluster, "−", lambda field=entry: self._step_minutes(field, -1)).pack(side="left")
        shell.pack(side="left", padx=(8, 0))
        tk.Label(cluster, text="мин", bg=CARD, fg=MUTED, font=ui_font(10)).pack(side="left", padx=(8, 8))
        StepButton(cluster, "+", lambda field=entry: self._step_minutes(field, 1)).pack(side="left")
        return entry

    def _step_minutes(self, entry: tk.Entry, delta: float) -> None:
        try:
            current = float(entry.get().strip().replace(",", "."))
        except ValueError:
            current = 0
        updated = min(MAX_MINUTES, max(1.0, current + delta))
        entry.delete(0, "end")
        if abs(updated - round(updated)) < 1e-6:
            entry.insert(0, str(int(round(updated))))
            return
        entry.insert(0, f"{updated:.2f}".rstrip("0").rstrip("."))

    def _mode_row(self, parent: tk.Misc, value: str, title: str, detail: str) -> None:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x")
        inner = tk.Frame(row, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)
        dot = tk.Canvas(inner, width=18, height=18, bg=CARD, highlightthickness=0, bd=0)
        dot.pack(side="left", padx=(0, 12))
        texts = tk.Frame(inner, bg=CARD)
        texts.pack(side="left", fill="x", expand=True)
        title_lbl = tk.Label(texts, text=title, bg=CARD, fg=TEXT, font=ui_font(10, "bold"), anchor="w")
        title_lbl.pack(anchor="w")
        detail_lbl = tk.Label(texts, text=detail, bg=CARD, fg=MUTED, font=ui_font(9), anchor="w")
        detail_lbl.pack(anchor="w", pady=(2, 0))
        self._mode_cards[value] = (row, inner, texts, title_lbl, detail_lbl, dot)
        for widget in (row, inner, dot, texts, title_lbl, detail_lbl):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event, mode=value: self._select_mode(mode))

    def _show_settings_error(self, text: str) -> None:
        self._settings_error.configure(text=text)
        if not text:
            if self._settings_error.winfo_ismapped():
                self._settings_error.pack_forget()
            return
        if not self._settings_error.winfo_ismapped():
            self._settings_error.pack(anchor="w", fill="x", pady=(10, 0), before=self._settings_buttons)
        self._fit_window()

    def _load_settings_form(self) -> None:
        self._settings_autostart.set(self.autostart_enabled)
        self._work_entry.delete(0, "end")
        self._work_entry.insert(0, format_minutes(self.settings.work_seconds))
        self._break_entry.delete(0, "end")
        self._break_entry.insert(0, format_minutes(self.settings.break_seconds))
        self._mode_var.set(self.settings.mode)
        self._paint_mode_cards()
        self._show_settings_error("")

    def _on_settings_escape(self, _event: tk.Event) -> str:
        self._hide_settings()
        return "break"

    def _fit_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        if self._settings_visible:
            width = max(width, self._main_width)
        else:
            self._main_width = width
        self.root.geometry(f"{width}x{height}")

    def _select_mode(self, mode: str) -> None:
        self._mode_var.set(mode)
        self._paint_mode_cards()

    def _paint_mode_cards(self) -> None:
        selected = self._mode_var.get()
        for value, (row, inner, texts, title_lbl, detail_lbl, dot) in self._mode_cards.items():
            active = value == selected
            bg = SELECTED if active else CARD
            row.configure(bg=bg)
            inner.configure(bg=bg)
            texts.configure(bg=bg)
            title_lbl.configure(bg=bg, fg=ACCENT if active else TEXT)
            detail_lbl.configure(bg=bg)
            dot.configure(bg=bg)
            dot.delete("all")
            dot.create_oval(1, 1, 16, 16, outline=ACCENT if active else BORDER, width=2)
            if active:
                dot.create_oval(5, 5, 12, 12, fill=ACCENT, outline="")

    def _save_settings_dialog(self) -> None:
        if not self._settings_visible:
            return
        try:
            work = float(self._work_entry.get().strip().replace(",", "."))
            brk = float(self._break_entry.get().strip().replace(",", "."))
        except ValueError:
            self._show_settings_error("Введите число минут")
            return
        if work <= 0 or brk <= 0 or work > MAX_MINUTES or brk > MAX_MINUTES:
            self._show_settings_error(f"Время: больше 0 и не больше {int(MAX_MINUTES)} минут")
            return
        mode = self._mode_var.get()
        if mode not in (MODE_LOCK, MODE_REMIND):
            mode = MODE_LOCK
        wanted_autostart = bool(self._settings_autostart.get())
        switching_to_lock = (
            self.on_break and mode == MODE_LOCK and self.settings.mode != MODE_LOCK
        )
        if switching_to_lock:
            self._hide_settings()
        self._apply_autostart(wanted_autostart)
        autostart_ok = self.autostart_enabled == wanted_autostart
        self._apply_runtime_settings(
            make_settings(work, brk, mode, self.settings.snooze_seconds)
        )
        self._persist_settings()
        if not autostart_ok and self._settings_visible:
            self._settings_autostart.set(self.autostart_enabled)
            self._show_settings_error("Не удалось изменить автозапуск. Остальные настройки сохранены.")
            return
        self._hide_settings()

    def _hide_settings(self) -> None:
        if not self._settings_visible:
            return
        self.root.unbind("<Escape>")
        self.settings_frame.pack_forget()
        self.main_frame.pack(fill="both", expand=True)
        self._settings_visible = False
        self._fit_window()
        self._apply_window_chrome()

    def _place_bottom_right(self, win: tk.Misc) -> None:
        win.update_idletasks()
        width = win.winfo_reqwidth()
        height = win.winfo_reqheight()
        ax, ay, aw, ah = work_area()
        win.geometry(f"{width}x{height}+{ax + aw - width - 16}+{ay + ah - height - 16}")

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
        self.hint_label.configure(text=self._work_hint(), fg=MUTED)
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
            self._hide_settings()
            self._warning_shown = False
            self._set_snooze_enabled(False)
            self.on_break = True
            self.period_started = time.monotonic()
            self.esc_held = 0.0
            self._overlay_tick = 0
            self.break_btn.configure(state="disabled")
            self.status_label.configure(text="Перерыв", fg=BREAK_ACCENT)
            self.hint_label.configure(text=self._break_hint(), fg=MUTED)
            self._refresh_tray(force_icon=True)
            beep_start()
            if self.settings.mode == MODE_LOCK:
                self._show_overlay()
                self.blocker.lock()
                self.audio.silence()
            else:
                self._show_reminder()
                if self.icon is not None:
                    try:
                        self.icon.notify(
                            "Пора сделать перерыв. Окно можно закрыть и продолжить работу.",
                            "Перерыв",
                        )
                    except Exception:
                        pass
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
            self._hide_reminder()
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
        self._hide_reminder()
        self._restore_root_after_overlay()
        self.break_btn.configure(state="normal")
        self.status_label.configure(text="Работа", fg=GREEN)
        self.hint_label.configure(text=self._work_hint(), fg=MUTED)
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

        wrap = tk.Frame(
            overlay,
            bg=CARD,
            padx=56,
            pady=42,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(wrap, text="Перерыв", bg=CARD, fg=BREAK_ACCENT, font=ui_font(13, "bold")).pack()
        self.overlay_ring = CountdownRing(wrap, size=280, font_size=42, bg=CARD)
        self.overlay_ring.pack(pady=(12, 8))
        self.overlay_ring.set(1, BREAK_ACCENT, format_hms(self.settings.break_seconds))
        self.overlay_time = tk.Label(wrap, bg=CARD, fg=TEXT)

        tk.Label(
            wrap,
            text="Мышь, звук и микрофон выключены.\nВстань, разомнись, посмотри вдаль.",
            bg=CARD,
            fg=MUTED,
            font=ui_font(14),
            justify="center",
        ).pack(pady=(8, 0))

        self.overlay_skip = tk.Label(
            wrap,
            text="Удерживайте Escape 3 секунды, чтобы пропустить",
            bg=CARD,
            fg=MUTED,
            font=ui_font(10),
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
            self.overlay_ring = None

    def _show_reminder(self) -> None:
        if self.remind_win is not None:
            return
        self._map_root_for_popup()
        win, pad = self._floating_card()
        win.protocol("WM_DELETE_WINDOW", self._hide_reminder)
        accent = tk.Frame(pad, bg=BREAK_ACCENT, height=3)
        accent.pack_propagate(False)
        accent.pack(fill="x")
        body = tk.Frame(pad, bg=BG, padx=22, pady=18)
        body.pack(fill="both")
        tk.Label(body, text="Перерыв", bg=BG, fg=BREAK_ACCENT, font=ui_font(12, "bold")).pack(anchor="w")
        self.remind_time = tk.Label(
            body,
            text=format_hms(max(0.0, self.remaining())),
            bg=BG,
            fg=TEXT,
            font=ui_font(36, "bold"),
        )
        self.remind_time.pack(anchor="w", pady=(2, 8))
        tk.Label(
            body,
            text="Встань, разомнись, посмотри вдаль.\nОкно можно закрыть и продолжить работу.",
            bg=BG,
            fg=MUTED,
            font=ui_font(10),
            justify="left",
        ).pack(anchor="w")

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", pady=(18, 0))
        PillButton(
            buttons,
            "Закончить перерыв",
            self.end_break,
            fill=CARD,
            fg=BREAK_ACCENT,
        ).pack(side="left")
        PillButton(buttons, "Закрыть", self._hide_reminder, fill=CARD, fg=MUTED).pack(side="right")

        self._place_bottom_right(win)
        win.deiconify()
        win.lift()
        self.remind_win = win

    def _hide_reminder(self) -> None:
        if self.remind_win is None:
            return
        try:
            self.remind_win.destroy()
        except tk.TclError:
            pass
        self.remind_win = None
        self.remind_time = None

    def _show_warning(self) -> None:
        self._set_snooze_enabled(True)
        self.status_label.configure(text="Скоро перерыв", fg=WARN_ACCENT)
        self.hint_label.configure(text="можно отложить", fg=WARN_ACCENT)
        self._refresh_tray(force_icon=True)
        beep_start()
        if self.icon is not None:
            try:
                self.icon.notify(self._warning_notify(), "Скоро перерыв")
            except Exception:
                pass
        if self.warn_win is not None:
            return

        self._map_root_for_popup()
        win, pad = self._floating_card()
        win.protocol("WM_DELETE_WINDOW", self._hide_warning)
        accent = tk.Frame(pad, bg=WARN_ACCENT, height=3)
        accent.pack_propagate(False)
        accent.pack(fill="x")
        body = tk.Frame(pad, bg=BG, padx=22, pady=18)
        body.pack(fill="both")
        tk.Label(body, text="Скоро перерыв", bg=BG, fg=WARN_ACCENT, font=ui_font(12, "bold")).pack(anchor="w")
        self.warn_time = tk.Label(
            body,
            text=format_hms(self.remaining()),
            bg=BG,
            fg=TEXT,
            font=ui_font(36, "bold"),
        )
        self.warn_time.pack(anchor="w", pady=(2, 8))
        self.warn_body = tk.Label(
            body,
            text=self._warning_body(),
            bg=BG,
            fg=MUTED,
            font=ui_font(10),
            wraplength=320,
            justify="left",
        )
        self.warn_body.pack(anchor="w")

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", pady=(18, 0))
        PillButton(
            buttons,
            self._snooze_label(),
            self.snooze,
            fill=CARD,
            fg=WARN_ACCENT,
        ).pack(side="left")
        PillButton(buttons, "Закрыть", self._hide_warning, fill=CARD, fg=MUTED).pack(side="right")

        self._place_bottom_right(win)
        win.deiconify()
        win.lift()
        self.warn_win = win

    def _floating_card(self) -> tuple[tk.Toplevel, tk.Frame]:
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=BORDER)
        win.attributes("-topmost", True)
        shell = tk.Frame(win, bg=BG)
        shell.pack(padx=1, pady=1)
        return win, shell

    def _hide_warning(self) -> None:
        if self.warn_win is not None:
            try:
                self.warn_win.destroy()
            except tk.TclError:
                pass
            self.warn_win = None
            self.warn_time = None
            self.warn_body = None

    def _tick(self) -> None:
        try:
            self._update()
        except Exception:
            self.blocker.unlock()
            raise
        if self.root.winfo_exists():
            self.root.after(TICK_MS, self._tick)

    def _sync_ring(self, left: float) -> None:
        total = self.settings.break_seconds if self.on_break else self.settings.work_seconds
        shown = max(0.0, left)
        fraction = 0.0 if total <= 0 else max(0.0, min(1.0, shown / total))
        if self.on_break:
            color = BREAK_ACCENT
        elif self._in_warning_window():
            color = WARN_ACCENT
        else:
            color = GREEN
        self.ring.set(fraction, color, format_hms(shown))

    def _update(self) -> None:
        left = self.remaining()
        self.timer_label.configure(text=format_hms(left))
        self._sync_ring(left)
        self._refresh_tray()

        if self.on_break:
            if self.settings.mode == MODE_LOCK:
                if self.overlay is not None:
                    self.overlay.attributes("-topmost", True)
                    self.overlay.lift()
                    if self.overlay_time is not None:
                        self.overlay_time.configure(text=format_hms(left))
                    if self.overlay_ring is not None:
                        total = self.settings.break_seconds or 1
                        self.overlay_ring.set(
                            max(0.0, left) / total,
                            BREAK_ACCENT,
                            format_hms(max(0.0, left)),
                        )
                self.blocker.lock()
                self._overlay_tick += 1
                if self._overlay_tick % 20 == 0:
                    self.audio.keep_silenced()
            elif self.remind_time is not None:
                self.remind_time.configure(text=format_hms(max(0.0, left)))
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
                    self.warn_body = None
            self.status_label.configure(text="Скоро перерыв", fg=WARN_ACCENT)
            self.hint_label.configure(text="можно отложить", fg=WARN_ACCENT)
        else:
            if self._warning_shown:
                self._warning_shown = False
                self._hide_warning()
                self.status_label.configure(text="Работа", fg=GREEN)
                self.hint_label.configure(text=self._work_hint(), fg=MUTED)
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

        if self.on_break and self.settings.mode == MODE_LOCK and esc:
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


def parse_args(argv: list[str], config: dict) -> Settings:
    parser = argparse.ArgumentParser(description="FreedomTime — перерывы по таймеру")
    parser.add_argument("--work", type=float, default=None, help="Минуты работы")
    parser.add_argument("--break", dest="brk", type=float, default=None, help="Минуты перерыва")
    parser.add_argument("--test", action="store_true", help="Короткий цикл для проверки предупреждения")
    args = parser.parse_args(argv)
    saved = settings_from_config(config)
    if args.test:
        return Settings(
            work_seconds=20.0,
            break_seconds=10.0,
            warn_seconds=8.0,
            snooze_seconds=15.0,
            mode=saved.mode,
        )
    work_minutes = saved.work_seconds / 60.0 if args.work is None else args.work
    break_minutes = saved.break_seconds / 60.0 if args.brk is None else args.brk
    if work_minutes <= 0 or break_minutes <= 0:
        parser.error("Интервалы должны быть больше нуля")
    return make_settings(work_minutes, break_minutes, saved.mode, saved.snooze_seconds)


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
    settings = parse_args(sys.argv[1:], load_config())
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
