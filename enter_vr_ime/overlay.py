from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import openvr


MAX_RAW_UPDATES_PER_SECOND = 10.0
TRANSIENT_RETRY_LIMIT = 5
TRANSIENT_RETRY_SECONDS = 0.18
OVERLAY_POOL_SIZE = 3
PRESENTATION_FRAME_COUNT = 2
FRAME_SYNC_TIMEOUT_MS = 50
POOL_FAILURE_LIMIT = 5


@dataclass(frozen=True, slots=True)
class OverlayPosition:
    width_m: float
    y_m: float
    z_m: float


class _OverlaySwapChain:
    """Keep two visible generations while rotating through three overlay handles."""

    def __init__(self, overlay: openvr.IVROverlay, handles: list[int]) -> None:
        if len(handles) != OVERLAY_POOL_SIZE:
            raise ValueError(f"overlay pool must contain {OVERLAY_POOL_SIZE} handles")
        self.overlay = overlay
        self.handles = handles
        self.active_index = 0
        self.visible_indices: list[int] = []
        self.generation = 0

    @property
    def active_handle(self) -> int:
        return self.handles[self.active_index]

    def set_visible(self, visible: bool) -> None:
        if visible:
            if self.active_index in self.visible_indices:
                return
            self.generation += 1
            self.overlay.setOverlaySortOrder(self.active_handle, self.generation)
            self.overlay.showOverlay(self.active_handle)
            self.visible_indices.append(self.active_index)
            return

        indices = self.visible_indices
        failed_indices: list[int] = []
        first_error: Exception | None = None
        for index in indices:
            try:
                self.overlay.hideOverlay(self.handles[index])
            except Exception as exc:
                first_error = first_error or exc
                failed_indices.append(index)
        self.visible_indices = failed_indices
        if first_error is not None:
            raise first_error

    def promote(self, submit: Callable[[int], None], visible: bool) -> int:
        candidates = [
            index
            for index in range(len(self.handles))
            if index != self.active_index and index not in self.visible_indices
        ]
        if not candidates:
            raise RuntimeError("no hidden standby overlay is available")

        last_error: Exception | None = None
        for candidate in candidates:
            handle = self.handles[candidate]
            shown = False
            try:
                submit(handle)
                if visible:
                    next_generation = self.generation + 1
                    self.overlay.setOverlaySortOrder(handle, next_generation)
                    self.overlay.showOverlay(handle)
                    shown = True
                    for _ in range(PRESENTATION_FRAME_COUNT):
                        try:
                            self.overlay.waitFrameSync(FRAME_SYNC_TIMEOUT_MS)
                        except Exception as exc:
                            # SteamVR times out while the headset/compositor is idle. The
                            # timeout itself supplies the grace period, and the higher sort
                            # order still makes the standby layer win when rendering resumes.
                            if "TimedOut" not in str(exc) and "TimedOut" not in type(exc).__name__:
                                raise

                    next_visible = [*self.visible_indices, candidate]
                    while len(next_visible) > 2:
                        oldest = next_visible.pop(0)
                        self.overlay.hideOverlay(self.handles[oldest])
                    self.visible_indices = next_visible
                    self.generation = next_generation
                else:
                    self.set_visible(False)
                self.active_index = candidate
                return handle
            except Exception as exc:
                last_error = exc
                if shown:
                    try:
                        self.overlay.hideOverlay(handle)
                    except Exception as hide_exc:
                        if candidate not in self.visible_indices:
                            self.visible_indices.append(candidate)
                        last_error = hide_exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("standby overlay promotion failed")

    def close(self) -> None:
        try:
            self.set_visible(False)
        except Exception:
            pass
        for handle in self.handles:
            try:
                self.overlay.destroyOverlay(handle)
            except Exception:
                pass


class SteamVROverlay:
    """Render the latest captured RGBA frame as a head-locked OpenVR overlay."""

    def __init__(self, position: OverlayPosition, logger: logging.Logger) -> None:
        self.position = position
        self.logger = logger
        self._thread = threading.Thread(target=self._run, name="steamvr-overlay", daemon=True)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._force_promotion = threading.Event()
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

    def force_standby_promotion(self) -> None:
        """Exercise the make-before-break path during an overlay smoke test."""
        self._force_promotion.set()
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
        swap_chain: _OverlaySwapChain | None = None
        pending_frame: tuple[bytes, int, int] | None = None
        submitted_frame: tuple[bytes, int, int] | None = None
        last_submit_at = 0.0
        transient_failures = 0
        pool_failures = 0

        while not self._stop.is_set():
            if overlay is None or swap_chain is None:
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
                    handles = []
                    for index in range(OVERLAY_POOL_SIZE):
                        handle = overlay.createOverlay(
                            f"enter.vr.ime.chatbox.{index}",
                            f"EnterVRIME 中文输入 {index + 1}",
                        )
                        self._configure(overlay, handle)
                        handles.append(handle)
                    swap_chain = _OverlaySwapChain(overlay, handles)
                    submitted_frame = None
                    last_submit_at = 0.0
                    transient_failures = 0
                    pool_failures = 0
                    self._set_state("SteamVR 已连接")
                    self.logger.info("E302 overlay_connected pool=%d", len(handles))
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

                    self._submit_frame(overlay, swap_chain.active_handle, pending_frame)
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

                if submitted_frame is not None:
                    swap_chain.set_visible(visible)
                    if self._force_promotion.is_set():
                        self._force_promotion.clear()
                        promoted_handle = swap_chain.promote(
                            lambda standby_handle: self._submit_frame(
                                overlay,
                                standby_handle,
                                submitted_frame,
                            ),
                            visible,
                        )
                        last_submit_at = time.monotonic()
                        self.logger.info(
                            "E313 overlay_smoke_promotion handle=%d",
                            promoted_handle,
                        )
                pool_failures = 0
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

                replacement_frame = pending_frame or submitted_frame
                if replacement_frame is not None:
                    try:
                        promoted_handle = swap_chain.promote(
                            lambda standby_handle: self._submit_frame(
                                overlay,
                                standby_handle,
                                replacement_frame,
                            ),
                            visible,
                        )
                        submitted_frame = replacement_frame
                        pending_frame = None
                        last_submit_at = time.monotonic()
                        transient_failures = 0
                        pool_failures = 0
                        self._set_state("SteamVR 已连接")
                        self.logger.warning(
                            "E308 overlay_standby_promoted handle=%d error=%s",
                            promoted_handle,
                            friendly,
                        )
                        continue
                    except Exception as promotion_exc:
                        pool_failures += 1
                        self._set_state(
                            f"[E304] SteamVR 画面重试中：{self._friendly_error(promotion_exc)}"
                        )
                        self.logger.error(
                            "E307 overlay_pool_retry error=%s attempts=%d",
                            self._friendly_error(promotion_exc),
                            pool_failures,
                            exc_info=True,
                        )
                        if pool_failures < POOL_FAILURE_LIMIT:
                            self._wake.wait(timeout=0.4)
                            self._wake.clear()
                            continue

                self._set_state(f"[E304] SteamVR 连接中断：{friendly}")
                self.logger.critical(
                    "E312 overlay_session_reconnecting error=%s pool_failures=%d",
                    friendly,
                    pool_failures,
                    exc_info=True,
                )
                if swap_chain is not None:
                    swap_chain.close()
                overlay = None
                swap_chain = None
                pending_frame = None
                submitted_frame = None
                transient_failures = 0
                pool_failures = 0
                try:
                    openvr.shutdown()
                except Exception:
                    pass

        if swap_chain is not None:
            swap_chain.close()
        try:
            openvr.shutdown()
        except Exception:
            pass

    @staticmethod
    def _submit_frame(
        overlay: openvr.IVROverlay,
        handle: int,
        frame: tuple[bytes, int, int],
    ) -> None:
        rgba, width, height = frame
        buffer_type = ctypes.c_ubyte * len(rgba)
        buffer = buffer_type.from_buffer_copy(rgba)
        overlay.setOverlayRaw(handle, buffer, width, height, 4)

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
