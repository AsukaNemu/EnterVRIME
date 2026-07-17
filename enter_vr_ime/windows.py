from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]

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
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL


def is_process_running(executable_name: str) -> bool:
    """Return whether a process with the exact executable name is running."""
    wanted = executable_name.casefold()
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return False
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not _kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            if entry.szExeFile.casefold() == wanted:
                return True
            if not _kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        _kernel32.CloseHandle(snapshot)


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
