from __future__ import annotations

import ctypes


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\EnterVRIME.SingleInstance"


class SingleInstanceMutex:
    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self.handle: int | None = None

    def acquire(self) -> bool:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError()
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self.handle = int(handle)
        return True

    def close(self) -> None:
        if self.handle is None:
            return
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
        self.handle = None


def show_existing_instance() -> None:
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    hwnd = user32.FindWindowW(None, "EnterVRIME")
    if hwnd:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        return
    user32.MessageBoxW(
        None,
        "EnterVRIME 已经在运行。请查看桌面右下角的系统托盘图标。",
        "EnterVRIME",
        0x40,
    )
