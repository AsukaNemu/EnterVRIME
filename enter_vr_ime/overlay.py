from __future__ import annotations

import ctypes
import logging
import threading
import time
from dataclasses import dataclass

import openvr


MAX_RAW_UPDATES_PER_SECOND = 10.0
TRANSIENT_RETRY_LIMIT = 5
TRANSIENT_RETRY_SECONDS = 0.18


@dataclass(frozen=True, slots=True)
class OverlayPosition:
    width_m: float
    y_m: float
    z_m: float


class SteamVROverlay:
    """Render the latest captured RGBA frame as a head-locked OpenVR overlay."""

    def __init__(self, position: OverlayPosition, logger: logging.Logger) -> None:
        self.position = position
        self.logger = logger
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
        self.logger.info("E300 overlay_thread_started")

    def show(self) -> None:
        with self._lock:
            self._visible_requested = True
        self._wake.set()
        self.logger.debug("E310 overlay_show_requested")

    def hide(self) -> None:
        with self._lock:
            self._visible_requested = False
        self._wake.set()
        self.logger.debug("E311 overlay_hide_requested")

    def submit_rgba(self, rgba: bytes, width: int, height: int) -> None:
        with self._lock:
            self._latest_frame = (rgba, width, height)
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=3.0)
        self.logger.info("E309 overlay_thread_stopped")

    def _set_state(self, value: str) -> bool:
        with self._lock:
            if self._state == value:
                return False
            self._state = value
            return True

    def _run(self) -> None:
        overlay = None
        handle = None
        shown = False
        pending_frame: tuple[bytes, int, int] | None = None
        submitted_frame: tuple[bytes, int, int] | None = None
        last_submit_at = 0.0
        transient_failures = 0

        while not self._stop.is_set():
            if overlay is None or handle is None:
                try:
                    hmd_present = openvr.isHmdPresent()
                except Exception:
                    hmd_present = False
                if not hmd_present:
                    if self._set_state("等待 Virtual Desktop 与 SteamVR 头显连接"):
                        self.logger.info("E301 hmd_waiting")
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
                    submitted_frame = None
                    last_submit_at = 0.0
                    transient_failures = 0
                    self._set_state("SteamVR 已连接")
                    self.logger.info("E302 overlay_connected")
                except Exception as exc:  # OpenVR exposes several exception classes.
                    friendly = self._friendly_error(exc)
                    self._set_state(f"[E303] SteamVR 未就绪：{friendly}")
                    self.logger.warning("E303 overlay_connect_failed error=%s", friendly, exc_info=True)
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

            if frame is not None:
                pending_frame = frame

            if pending_frame == submitted_frame:
                pending_frame = None

            try:
                if pending_frame is not None:
                    elapsed = time.monotonic() - last_submit_at
                    minimum_interval = 1.0 / MAX_RAW_UPDATES_PER_SECOND
                    if elapsed < minimum_interval:
                        self._wake.wait(timeout=minimum_interval - elapsed)
                        self._wake.clear()
                        if self._stop.is_set():
                            break

                    rgba, width, height = pending_frame
                    buffer_type = ctypes.c_ubyte * len(rgba)
                    buffer = buffer_type.from_buffer_copy(rgba)
                    overlay.setOverlayRaw(handle, buffer, width, height, 4)
                    submitted_frame = pending_frame
                    pending_frame = None
                    last_submit_at = time.monotonic()
                    if transient_failures:
                        self.logger.info(
                            "E306 overlay_frame_recovered retries=%d",
                            transient_failures,
                        )
                        transient_failures = 0
                        self._set_state("SteamVR 已连接")

                if visible and submitted_frame is not None and not shown:
                    overlay.showOverlay(handle)
                    shown = True
                elif not visible and shown:
                    overlay.hideOverlay(handle)
                    shown = False
            except Exception as exc:
                friendly = self._friendly_error(exc)
                is_transient = "RequestFailed" in friendly
                if is_transient:
                    transient_failures += 1
                    if transient_failures < TRANSIENT_RETRY_LIMIT:
                        if transient_failures == 1:
                            self.logger.warning(
                                "E304 overlay_frame_retry error=%s",
                                friendly,
                            )
                        self._wake.wait(timeout=TRANSIENT_RETRY_SECONDS)
                        self._wake.clear()
                        continue

                self._set_state(f"[E304] SteamVR 连接中断：{friendly}")
                self.logger.error(
                    "E307 overlay_reconnecting error=%s retries=%d",
                    friendly,
                    transient_failures,
                    exc_info=True,
                )
                overlay = None
                handle = None
                shown = False
                pending_frame = None
                submitted_frame = None
                transient_failures = 0
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
