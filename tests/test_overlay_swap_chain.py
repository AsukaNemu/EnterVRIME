from __future__ import annotations

import unittest

from enter_vr_ime.overlay import _OverlaySwapChain


class FakeOverlay:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.hide_failures: set[int] = set()
        self.wait_timeout = False

    def setOverlaySortOrder(self, handle: int, order: int) -> None:
        self.calls.append(("sort", handle, order))

    def showOverlay(self, handle: int) -> None:
        self.calls.append(("show", handle))

    def hideOverlay(self, handle: int) -> None:
        self.calls.append(("hide", handle))
        if handle in self.hide_failures:
            raise RuntimeError(f"hide failed for {handle}")

    def waitFrameSync(self, timeout_ms: int) -> None:
        self.calls.append(("wait", timeout_ms))
        if self.wait_timeout:
            raise RuntimeError("OverlayError_TimedOut")

    def destroyOverlay(self, handle: int) -> None:
        self.calls.append(("destroy", handle))


class OverlaySwapChainTests(unittest.TestCase):
    def test_third_layer_is_shown_before_oldest_is_retired(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [100, 101, 102])
        chain.set_visible(True)

        chain.promote(lambda handle: overlay.calls.append(("submit", handle)), True)
        self.assertEqual(chain.visible_indices, [0, 1])

        chain.promote(lambda handle: overlay.calls.append(("submit", handle)), True)
        self.assertEqual(chain.active_handle, 102)
        self.assertEqual(chain.visible_indices, [1, 2])
        self.assertLess(overlay.calls.index(("show", 102)), overlay.calls.index(("hide", 100)))

        def submit_hidden(handle: int) -> None:
            self.assertEqual(chain.active_handle, 102)
            self.assertNotIn(chain.handles.index(handle), chain.visible_indices)
            overlay.calls.append(("submit", handle))

        chain.promote(submit_hidden, True)

        self.assertEqual(chain.active_handle, 100)
        self.assertEqual(chain.visible_indices, [2, 0])
        self.assertEqual(overlay.calls.count(("show", 100)), 2)
        latest_show = max(
            index for index, call in enumerate(overlay.calls) if call == ("show", 100)
        )
        self.assertLess(latest_show, overlay.calls.index(("hide", 101)))

    def test_upload_waits_behind_old_frame_before_promoting_new_frame(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [150, 151, 152])
        chain.set_visible(True)

        chain.promote(lambda handle: overlay.calls.append(("submit", handle)), True)

        submit_new = overlay.calls.index(("submit", 151))
        self.assertEqual(
            overlay.calls[submit_new : submit_new + 5],
            [
                ("submit", 151),
                ("wait", 50),
                ("sort", 151, 2),
                ("show", 151),
                ("wait", 50),
            ],
        )

    def test_failed_standby_upload_tries_the_next_hidden_slot(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [200, 201, 202])
        chain.set_visible(True)

        def submit(handle: int) -> None:
            overlay.calls.append(("submit", handle))
            if handle == 201:
                raise RuntimeError("first standby failed")

        promoted = chain.promote(submit, True)

        self.assertEqual(promoted, 202)
        self.assertEqual(chain.active_handle, 202)
        self.assertEqual(chain.visible_indices, [0, 2])
        self.assertNotIn(("show", 201), overlay.calls)

    def test_idle_compositor_timeout_still_completes_promotion(self) -> None:
        overlay = FakeOverlay()
        overlay.wait_timeout = True
        chain = _OverlaySwapChain(overlay, [250, 251, 252])
        chain.set_visible(True)

        promoted = chain.promote(lambda _handle: None, True)

        self.assertEqual(promoted, 251)
        self.assertEqual(chain.visible_indices, [0, 1])
        self.assertEqual(overlay.calls.count(("wait", 50)), 2)

    def test_failed_back_buffer_uploads_preserve_the_current_top_layer(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [275, 276, 277])
        chain.set_visible(True)
        chain.promote(lambda _handle: None, True)
        chain.promote(lambda _handle: None, True)
        hide_count = sum(call[0] == "hide" for call in overlay.calls)

        def fail_submit(_handle: int) -> None:
            raise RuntimeError("OverlayError_RequestFailed")

        with self.assertRaisesRegex(RuntimeError, "RequestFailed"):
            chain.promote(fail_submit, True)

        self.assertEqual(chain.active_handle, 277)
        self.assertEqual(chain.visible_indices, [1, 2])
        self.assertEqual(sum(call[0] == "hide" for call in overlay.calls), hide_count)

    def test_failed_retirement_is_retried_before_reusing_the_hidden_slot(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [280, 281, 282])
        chain.set_visible(True)
        chain.promote(lambda _handle: None, True)

        overlay.hide_failures.add(280)
        chain.promote(lambda _handle: None, True)
        self.assertEqual(chain.active_handle, 282)
        self.assertEqual(chain.visible_indices, [0, 1, 2])

        overlay.hide_failures.clear()
        submitted: list[int] = []
        chain.promote(submitted.append, True)

        self.assertEqual(submitted, [280])
        self.assertEqual(chain.active_handle, 280)
        self.assertEqual(chain.visible_indices, [2, 0])

    def test_hide_releases_every_visible_generation(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [300, 301, 302])
        chain.set_visible(True)
        chain.promote(lambda _handle: None, True)
        chain.promote(lambda _handle: None, True)

        chain.set_visible(False)

        self.assertEqual(chain.visible_indices, [])
        self.assertIn(("hide", 300), overlay.calls)
        self.assertIn(("hide", 301), overlay.calls)
        self.assertIn(("hide", 302), overlay.calls)

    def test_failed_hide_remains_tracked_for_a_later_retry(self) -> None:
        overlay = FakeOverlay()
        chain = _OverlaySwapChain(overlay, [400, 401, 402])
        chain.set_visible(True)
        chain.promote(lambda _handle: None, True)
        overlay.hide_failures.add(400)

        with self.assertRaisesRegex(RuntimeError, "hide failed"):
            chain.set_visible(False)

        self.assertEqual(chain.visible_indices, [0])
        overlay.hide_failures.clear()
        chain.set_visible(False)
        self.assertEqual(chain.visible_indices, [])


if __name__ == "__main__":
    unittest.main()
