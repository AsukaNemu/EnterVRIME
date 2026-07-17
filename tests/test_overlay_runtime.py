from __future__ import annotations

import logging
import threading
import time
import unittest
from collections.abc import Callable
from unittest.mock import patch

from enter_vr_ime import overlay as overlay_module
from enter_vr_ime.overlay import OverlayPosition, SteamVROverlay


class FakeRuntimeOverlay:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.create_calls = 0
        self.failure_remaining = 0
        self.fail_handles: set[int] = set()
        self.raw_attempts = 0
        self.raw_success_handles: list[int] = []
        self.show_calls: list[int] = []
        self.hide_calls: list[int] = []
        self.destroy_calls: list[int] = []
        self.events: list[tuple[str, int]] = []

    def createOverlay(self, _key: str, _name: str) -> int:
        with self._lock:
            handle = 500 + self.create_calls
            self.create_calls += 1
            self.events.append(("create", handle))
            return handle

    def setOverlayWidthInMeters(self, _handle: int, _width: float) -> None:
        pass

    def setOverlayAlpha(self, _handle: int, _alpha: float) -> None:
        pass

    def setOverlayInputMethod(self, _handle: int, _method: int) -> None:
        pass

    def setOverlayTransformTrackedDeviceRelative(
        self,
        _handle: int,
        _device: int,
        _transform: object,
    ) -> None:
        pass

    def setOverlaySortOrder(self, _handle: int, _order: int) -> None:
        pass

    def showOverlay(self, handle: int) -> None:
        with self._lock:
            self.show_calls.append(handle)
            self.events.append(("show", handle))

    def hideOverlay(self, handle: int) -> None:
        with self._lock:
            self.hide_calls.append(handle)
            self.events.append(("hide", handle))

    def destroyOverlay(self, handle: int) -> None:
        with self._lock:
            self.destroy_calls.append(handle)
            self.events.append(("destroy", handle))

    def waitFrameSync(self, _timeout_ms: int) -> None:
        pass

    def setOverlayRaw(
        self,
        handle: int,
        _buffer: object,
        _width: int,
        _height: int,
        _depth: int,
    ) -> None:
        with self._lock:
            self.raw_attempts += 1
            if handle in self.fail_handles or self.failure_remaining:
                self.events.append(("submit-failed", handle))
                if handle in self.fail_handles:
                    raise RuntimeError("OverlayError_RequestFailed")
                self.failure_remaining -= 1
                raise RuntimeError("OverlayError_RequestFailed")
            self.raw_success_handles.append(handle)
            self.events.append(("submit", handle))

    def inject_failures(self, count: int) -> None:
        with self._lock:
            self.failure_remaining = count

    def fail_only_handles(self, handles: set[int]) -> None:
        with self._lock:
            self.fail_handles = set(handles)

    def snapshot(
        self,
    ) -> tuple[int, int, list[int], list[int], list[int], list[int], list[tuple[str, int]]]:
        with self._lock:
            return (
                self.create_calls,
                self.raw_attempts,
                list(self.raw_success_handles),
                list(self.show_calls),
                list(self.hide_calls),
                list(self.destroy_calls),
                list(self.events),
            )


class OverlayRuntimeTests(unittest.TestCase):
    @staticmethod
    def logger(name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        return logger

    @staticmethod
    def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("condition was not reached before timeout")

    def test_startup_mode_waits_without_touching_openvr_until_steamvr_runs(self) -> None:
        logger = self.logger("test.overlay.startup-wait")
        service = SteamVROverlay(
            OverlayPosition(1.0, -0.3, -1.0),
            logger,
            wait_for_running_runtime=True,
        )

        def runtime_missing(_executable_name: str) -> bool:
            service._stop.set()
            service._wake.set()
            return False

        with (
            patch.object(overlay_module, "is_process_running", side_effect=runtime_missing),
            patch.object(overlay_module.openvr, "isHmdPresent") as hmd_present,
            patch.object(overlay_module.openvr, "init") as init_mock,
            patch.object(overlay_module.openvr, "shutdown"),
        ):
            service._run()

        hmd_present.assert_not_called()
        init_mock.assert_not_called()
        self.assertIn("不会自动打开", service.state)

    def test_request_failed_never_reconnects_or_removes_the_last_valid_layer(self) -> None:
        fake = FakeRuntimeOverlay()
        logger = self.logger("test.overlay.runtime")
        service = SteamVROverlay(OverlayPosition(1.0, -0.3, -1.0), logger)

        with (
            patch.object(overlay_module.openvr, "isHmdPresent", return_value=True),
            patch.object(overlay_module.openvr, "init"),
            patch.object(overlay_module.openvr, "shutdown"),
            patch.object(overlay_module.openvr, "VROverlay", return_value=fake),
            patch.object(overlay_module, "TRANSIENT_RETRY_SECONDS", 0.01),
            patch.object(overlay_module, "TRANSIENT_HANDOVER_INTERVAL", 100),
        ):
            service.start()
            try:
                service.show()
                service.submit_rgba(b"\x10\x20\x30\xff", 1, 1)
                self.wait_until(lambda: len(fake.snapshot()[2]) >= 1)

                first = fake.snapshot()
                self.assertEqual(first[0], 3)
                self.assertEqual(first[2], [500])
                self.assertEqual(first[3], [500])

                fake.inject_failures(12)
                service.submit_rgba(b"\x40\x50\x60\xff", 1, 1)
                self.wait_until(lambda: len(fake.snapshot()[2]) >= 2)

                recovered = fake.snapshot()
                self.assertEqual(recovered[0], 3)
                self.assertGreaterEqual(recovered[1], 14)
                self.assertEqual(recovered[2][0], 500)
                self.assertIn(recovered[2][1], (501, 502))
                self.assertEqual(recovered[4], [])
                self.assertEqual(recovered[5], [])
            finally:
                service.stop()

    def test_stuck_pool_hands_over_only_after_replacement_is_visible(self) -> None:
        fake = FakeRuntimeOverlay()
        logger = self.logger("test.overlay.handover")
        service = SteamVROverlay(OverlayPosition(1.0, -0.3, -1.0), logger)

        with (
            patch.object(overlay_module.openvr, "isHmdPresent", return_value=True),
            patch.object(overlay_module.openvr, "init") as init_mock,
            patch.object(overlay_module.openvr, "shutdown"),
            patch.object(overlay_module.openvr, "VROverlay", return_value=fake),
            patch.object(overlay_module, "TRANSIENT_RETRY_SECONDS", 0.01),
            patch.object(overlay_module, "TRANSIENT_HANDOVER_INTERVAL", 3),
        ):
            service.start()
            try:
                service.show()
                service.submit_rgba(b"\x10\x20\x30\xff", 1, 1)
                self.wait_until(lambda: len(fake.snapshot()[2]) >= 1)

                fake.fail_only_handles({500, 501, 502})
                service.submit_rgba(b"\x70\x80\x90\xff", 1, 1)
                self.wait_until(lambda: 503 in fake.snapshot()[2])

                recovered = fake.snapshot()
                events = recovered[6]
                self.assertEqual(init_mock.call_count, 1)
                self.assertEqual(recovered[0], 6)
                self.assertIn(503, recovered[3])
                self.assertEqual(recovered[5], [500, 501, 502])
                self.assertLess(events.index(("show", 503)), events.index(("hide", 500)))
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
