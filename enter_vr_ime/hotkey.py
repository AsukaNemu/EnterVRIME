from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes


WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_ENABLE_HOTKEY = WM_APP + 41
WM_DISABLE_HOTKEY = WM_APP + 42
WM_STOP_HOTKEY = WM_APP + 43
VK_RETURN = 0x0D
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0x4556


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


class EnterHotkey:
    """Own a thread-scoped, no-modifier Return hotkey without an admin hook."""

    def __init__(self, events: queue.Queue[str]) -> None:
        self.events = events
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._message_loop, name="enter-hotkey", daemon=True)
        self._thread_id = 0
        self._registered = False
        self.error: str | None = None

    @property
    def registered(self) -> bool:
        return self._registered

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def enable(self) -> None:
        self._post(WM_ENABLE_HOTKEY)

    def disable(self) -> None:
        self._post(WM_DISABLE_HOTKEY)

    def stop(self) -> None:
        self._post(WM_STOP_HOTKEY)
        self._thread.join(timeout=1.0)

    def _post(self, message: int) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, message, 0, 0)

    def _register(self) -> None:
        if self._registered:
            return
        success = ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_RETURN)
        self._registered = bool(success)
        if not success:
            self.error = "回车键被其他程序占用"

    def _unregister(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def _message_loop(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        # Force Windows to create this thread's message queue before signalling ready.
        msg = MSG()
        ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._register()
        self._ready.set()

        while True:
            result = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.events.put("activate")
            elif msg.message == WM_ENABLE_HOTKEY:
                self._register()
            elif msg.message == WM_DISABLE_HOTKEY:
                self._unregister()
            elif msg.message == WM_STOP_HOTKEY:
                self._unregister()
                break
