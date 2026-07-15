from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass

import openvr


@dataclass(frozen=True, slots=True)
class OverlayPosition:
    width_m: float
    y_m: float
    z_m: float


class SteamVROverlay:
    """Render the latest captured RGBA frame as a head-locked OpenVR overlay."""

    def __init__(self, position: OverlayPosition) -> None:
        self.position = position
        self._thread = threading.Thread(target=self._run, name="steamvr-overlay", daemon=True)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame: tuple[bytes, int, int] | None = None
        self._visible_requested = False
        self._state = "正在连接 SteamVR"

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def start(self) -> None:
        self._thread.start()

    def show(self) -> None:
        with self._lock:
            self._visible_requested = True
        self._wake.set()

    def hide(self) -> None:
        with self._lock:
            self._visible_requested = False
        self._wake.set()

    def submit_rgba(self, rgba: bytes, width: int, height: int) -> None:
        with self._lock:
            self._latest_frame = (rgba, width, height)
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=3.0)

    def _set_state(self, value: str) -> None:
        with self._lock:
            self._state = value

    def _run(self) -> None:
        overlay = None
        handle = None
        shown = False

        while not self._stop.is_set():
            if overlay is None or handle is None:
                try:
                    hmd_present = openvr.isHmdPresent()
                except Exception:
                    hmd_present = False
                if not hmd_present:
                    self._set_state("等待 Virtual Desktop 与 SteamVR 头显连接")
                    self._wake.wait(timeout=2.0)
                    self._wake.clear()
                    continue
                try:
                    openvr.init(openvr.VRApplication_Overlay)
                    overlay = openvr.VROverlay()
                    handle = overlay.createOverlay(
                        "enter.vr.ime.chatbox",
                        "EnterVRIME 中文输入",
                    )
                    self._configure(overlay, handle)
                    shown = False
                    self._set_state("SteamVR 已连接")
                except Exception as exc:  # OpenVR exposes several exception classes.
                    self._set_state(f"SteamVR 未就绪：{self._friendly_error(exc)}")
                    try:
                        openvr.shutdown()
                    except Exception:
                        pass
                    self._wake.wait(timeout=3.0)
                    self._wake.clear()
                    continue

            self._wake.wait(timeout=0.1)
            self._wake.clear()
            if self._stop.is_set():
                break

            with self._lock:
                frame = self._latest_frame
                self._latest_frame = None
                visible = self._visible_requested

            try:
                if frame is not None:
                    rgba, width, height = frame
                    buffer_type = ctypes.c_ubyte * len(rgba)
                    buffer = buffer_type.from_buffer_copy(rgba)
                    overlay.setOverlayRaw(handle, buffer, width, height, 4)
                if visible and frame is not None and not shown:
                    overlay.showOverlay(handle)
                    shown = True
                elif not visible and shown:
                    overlay.hideOverlay(handle)
                    shown = False
            except Exception as exc:
                self._set_state(f"SteamVR 连接中断：{self._friendly_error(exc)}")
                overlay = None
                handle = None
                shown = False
                try:
                    openvr.shutdown()
                except Exception:
                    pass

        if overlay is not None and handle is not None:
            try:
                overlay.hideOverlay(handle)
                overlay.destroyOverlay(handle)
            except Exception:
                pass
        try:
            openvr.shutdown()
        except Exception:
            pass

    def _configure(self, overlay: openvr.IVROverlay, handle: int) -> None:
        overlay.setOverlayWidthInMeters(handle, self.position.width_m)
        overlay.setOverlayAlpha(handle, 1.0)
        overlay.setOverlayInputMethod(handle, openvr.VROverlayInputMethod_None)

        transform = openvr.HmdMatrix34_t()
        values = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, self.position.y_m),
            (0.0, 0.0, 1.0, self.position.z_m),
        )
        for row in range(3):
            for column in range(4):
                transform.m[row][column] = values[row][column]
        overlay.setOverlayTransformTrackedDeviceRelative(
            handle,
            openvr.k_unTrackedDeviceIndex_Hmd,
            transform,
        )

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc).replace("\n", " ").strip()
        if "HmdNotFound" in message or "HMD Not Found" in message:
            return "没有检测到头显，请先连接 Virtual Desktop"
        if "NoServerForBackgroundApp" in message:
            return "请先启动 SteamVR"
        return message[:120] or exc.__class__.__name__
