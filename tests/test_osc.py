from __future__ import annotations

import unittest

from enter_vr_ime.osc import build_osc_message


class OscEncodingTests(unittest.TestCase):
    def test_typing_true(self) -> None:
        self.assertEqual(
            build_osc_message("/chatbox/typing", [True]),
            b"/chatbox/typing\x00,T\x00\x00",
        )

    def test_utf8_chatbox_message(self) -> None:
        packet = build_osc_message("/chatbox/input", ["你好", True, False])
        self.assertTrue(packet.startswith(b"/chatbox/input\x00\x00,sTF\x00\x00\x00\x00"))
        self.assertTrue(packet.endswith("你好".encode("utf-8") + b"\x00\x00"))

    def test_address_must_start_with_slash(self) -> None:
        with self.assertRaises(ValueError):
            build_osc_message("chatbox/input", [])


if __name__ == "__main__":
    unittest.main()
