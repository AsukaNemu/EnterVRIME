from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


def foreground_executable_name() -> str | None:
    """Return the lowercase executable name owning the foreground window."""
    window = _user32.GetForegroundWindow()
    if not window:
        return None

    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    if not pid.value:
        return None

    process = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not process:
        return None
    try:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not _kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(capacity)):
            return None
        return Path(buffer.value).name.lower()
    finally:
        _kernel32.CloseHandle(process)


def is_vrchat_executable(executable_name: str | None) -> bool:
    return bool(executable_name and executable_name.casefold() == "vrchat.exe")


def is_vrchat_foreground() -> bool:
    return is_vrchat_executable(foreground_executable_name())
