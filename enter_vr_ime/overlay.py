from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import openvr

from .windows import is_process_running


MAX_RAW_UPDATES_PER_SECOND = 10.0
TRANSIENT_RETRY_SECONDS = 0.18
TRANSIENT_LOG_INTERVAL = 20
TRANSIENT_HANDOVER_INTERVAL = 8
OVERLAY_POOL_SIZE = 3
FRAME_SYNC_TIMEOUT_MS = 50
POOL_FAILURE_LIMIT = 5


@dataclass(frozen=True, slots=True)
class OverlayPosition:
    width_m: float
    y_m: float
    z_m: float


class _OverlaySwapChain:
    """Upload only to a hidden layer, then retire the oldest visible layer."""

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
        retirement_error = self._retire_excess_visible()
        hidden_candidates = [
            index
            for index in range(len(self.handles))
            if index != self.active_index and index not in self.visible_indices
        ]
        if not hidden_candidates:
            if retirement_error is not None:
                raise retirement_error
            raise RuntimeError("no standby overlay is available")

        last_error: Exception | None = None
        for candidate in hidden_candidates:
            handle = self.handles[candidate]
            shown = False
            committed = False
            try:
                submit(handle)
                if visible:
                    self._wait_for_frame_sync()
                    next_generation = self.generation + 1
                    self.overlay.setOverlaySortOrder(handle, next_generation)
                    self.overlay.showOverlay(handle)
                    shown = True
                    self.visible_indices.append(candidate)
                    self.generation = next_generation
                    self.active_index = candidate
                    committed = True
                    self._wait_for_frame_sync()
                    # Keep the previous top layer as a fallback, but retire the
                    # oldest generation only after the new one has survived a
                    # compositor frame. A failed hide remains tracked and is
                    # retried before the next upload.
                    self._retire_excess_visible()
                else:
                    self.set_visible(False)
                    self.active_index = candidate
                return handle
            except Exception as exc:
                if committed:
                    raise
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

    def _retire_excess_visible(self) -> Exception | None:
        first_error: Exception | None = None
        while len(self.visible_indices) > 2:
            oldest = next(
                index for index in self.visible_indices if index != self.active_index
            )
            try:
                self.overlay.hideOverlay(self.handles[oldest])
            except Exception as exc:
                first_error = first_error or exc
                break
            self.visible_indices.remove(oldest)
        return first_error

    def _wait_for_frame_sync(self) -> None:
        try:
            self.overlay.waitFrameSync(FRAME_SYNC_TIMEOUT_MS)
        except Exception as exc:
            # SteamVR times out while the headset/compositor is idle. The timeout
            # itself supplies the grace period, so the current top layer stays valid.
            if "TimedOut" not in str(exc) and "TimedOut" not in type(exc).__name__:
                raise

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

    def __init__(
        self,
        position: OverlayPosition,
        logger: logging.Logger,
        *,
        wait_for_running_runtime: bool = False,
    ) -> None:
        self.position = position
        self.logger = logger
        self.wait_for_running_runtime = wait_for_running_runtime
        self._thread = threading.Thread(target=self._run, name="steamvr-overlay", daemon=True)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._force_promotion = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame: tuple[bytes, int, int] | None = None
        self._discard_submitted = False
        self._forced_submit_failures = 0
        self._visible_requested = False
        self._state = (
            "等待用户启动 SteamVR（开机启动不会自动打开）"
            if wait_for_running_runtime
            else "正在连接 SteamVR"
        )

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def start(self) -> None:
        self._thread.start()
        self.logger.info("E300 overlay_thread_started")
        if self.wait_for_running_runtime:
            self.logger.info("E305 startup_waiting_mode steamvr_autolaunch=False")

    def show(self) -> None:
        with self._lock:
            self._visible_requested = True
        self._wake.set()
        self.logger.debug("E310 overlay_show_requested")

    def hide(self) -> None:
        with self._lock:
            self._visible_requested = False
            self._latest_frame = None
            self._discard_submitted = True
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

    def force_transient_failures(self, count: int = 16) -> None:
        """Inject transient upload failures during a packaged SteamVR smoke test."""
        with self._lock:
            self._forced_submit_failures = max(0, count)
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
        pool_epoch = 0

        while not self._stop.is_set():
            if overlay is None or swap_chain is None:
                if self.wait_for_running_runtime and not is_process_running("vrserver.exe"):
                    if self._set_state("等待用户启动 SteamVR（开机启动不会自动打开）"):
                        self.logger.info("E305 startup_waiting_for_steamvr")
                    self._wake.wait(timeout=3.0)
                    self._wake.clear()
                    continue
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
                    pool_epoch += 1
                    swap_chain = self._create_swap_chain(overlay, pool_epoch)
                    submitted_frame = None
                    last_submit_at = 0.0
                    transient_failures = 0
                    pool_failures = 0
                    self._set_state("SteamVR 已连接")
                    self.logger.info(
                        "E302 overlay_connected pool=%d epoch=%d",
                        len(swap_chain.handles),
                        pool_epoch,
                    )
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
                discard_submitted = self._discard_submitted
                self._discard_submitted = False

            if discard_submitted:
                pending_frame = None
                submitted_frame = None

            if frame is not None:
                pending_frame = frame

            if pending_frame == submitted_frame:
                pending_frame = None

            try:
                if discard_submitted:
                    swap_chain.set_visible(False)

                if pending_frame is not None:
                    elapsed = time.monotonic() - last_submit_at
                    minimum_interval = 1.0 / MAX_RAW_UPDATES_PER_SECOND
                    if elapsed < minimum_interval:
                        self._wake.wait(timeout=minimum_interval - elapsed)
                        self._wake.clear()
                        if self._stop.is_set():
                            break

                    if visible and submitted_frame is not None:
                        promoted_handle = swap_chain.promote(
                            lambda standby_handle: self._submit_frame(
                                overlay,
                                standby_handle,
                                pending_frame,
                            ),
                            True,
                        )
                        self.logger.debug(
                            "E314 overlay_frame_promoted handle=%d generation=%d visible_layers=%d",
                            promoted_handle,
                            swap_chain.generation,
                            len(swap_chain.visible_indices),
                        )
                    else:
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
                        promoted_handle = swap_chain.promote(
                            lambda standby_handle: self._submit_frame(
                                overlay,
                                standby_handle,
                                submitted_frame,
                            ),
                            visible,
                        )
                        self._force_promotion.clear()
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
                    self._set_state("[E304] SteamVR 正忙；保留上一帧并继续重试")
                    if transient_failures == 1 or transient_failures % TRANSIENT_LOG_INTERVAL == 0:
                        self.logger.warning(
                            "E304 overlay_frame_preserved error=%s retries=%d",
                            friendly,
                            transient_failures,
                        )
                    if (
                        visible
                        and submitted_frame is not None
                        and transient_failures % TRANSIENT_HANDOVER_INTERVAL == 0
                    ):
                        replacement_frame = pending_frame or submitted_frame
                        next_epoch = pool_epoch + 1
                        try:
                            replacement_chain = self._handover_pool(
                                overlay,
                                swap_chain,
                                replacement_frame,
                                next_epoch,
                            )
                        except Exception as handover_exc:
                            self.logger.debug(
                                "E308 overlay_pool_handover_deferred error=%s retries=%d",
                                self._friendly_error(handover_exc),
                                transient_failures,
                            )
                        else:
                            swap_chain = replacement_chain
                            pool_epoch = next_epoch
                            submitted_frame = replacement_frame
                            pending_frame = None
                            transient_failures = 0
                            pool_failures = 0
                            self._force_promotion.clear()
                            last_submit_at = time.monotonic()
                            self._set_state("SteamVR 已连接")
                            self.logger.warning(
                                "E308 overlay_pool_handover epoch=%d",
                                pool_epoch,
                            )
                            continue
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
                        promotion_friendly = self._friendly_error(promotion_exc)
                        if "RequestFailed" in promotion_friendly:
                            transient_failures += 1
                            self._set_state("[E304] SteamVR 正忙；保留上一帧并继续重试")
                            if (
                                transient_failures == 1
                                or transient_failures % TRANSIENT_LOG_INTERVAL == 0
                            ):
                                self.logger.warning(
                                    "E304 overlay_frame_preserved error=%s retries=%d",
                                    promotion_friendly,
                                    transient_failures,
                                )
                            self._wake.wait(timeout=TRANSIENT_RETRY_SECONDS)
                            self._wake.clear()
                            continue
                        pool_failures += 1
                        self._set_state(
                            f"[E304] SteamVR 画面重试中：{promotion_friendly}"
                        )
                        self.logger.error(
                            "E307 overlay_pool_retry error=%s attempts=%d",
                            promotion_friendly,
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

    def _create_swap_chain(
        self,
        overlay: openvr.IVROverlay,
        epoch: int,
        starting_generation: int = 0,
    ) -> _OverlaySwapChain:
        handles: list[int] = []
        try:
            for index in range(OVERLAY_POOL_SIZE):
                handle = overlay.createOverlay(
                    f"enter.vr.ime.chatbox.{epoch}.{index}",
                    f"EnterVRIME 中文输入 {index + 1}",
                )
                self._configure(overlay, handle)
                handles.append(handle)
        except Exception:
            for handle in handles:
                try:
                    overlay.destroyOverlay(handle)
                except Exception:
                    pass
            raise
        swap_chain = _OverlaySwapChain(overlay, handles)
        swap_chain.generation = starting_generation
        return swap_chain

    def _handover_pool(
        self,
        overlay: openvr.IVROverlay,
        current: _OverlaySwapChain,
        frame: tuple[bytes, int, int],
        next_epoch: int,
    ) -> _OverlaySwapChain:
        replacement = self._create_swap_chain(
            overlay,
            next_epoch,
            starting_generation=current.generation,
        )
        try:
            self._submit_frame(overlay, replacement.active_handle, frame)
            replacement._wait_for_frame_sync()
            replacement.set_visible(True)
            replacement._wait_for_frame_sync()
        except Exception:
            replacement.close()
            raise
        current.close()
        return replacement

    def _submit_frame(
        self,
        overlay: openvr.IVROverlay,
        handle: int,
        frame: tuple[bytes, int, int],
    ) -> None:
        with self._lock:
            if self._forced_submit_failures:
                self._forced_submit_failures -= 1
                raise RuntimeError("OverlayError_RequestFailed [smoke-test]")
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
