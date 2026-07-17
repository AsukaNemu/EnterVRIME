from __future__ import annotations

import os
import socket
import sys
import unittest

from enter_vr_ime.osc import VRChatOscClient, build_osc_message


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

    @unittest.skipUnless(sys.platform == "win32", "Windows UDP owner table")
    def test_receiver_status_detects_bound_local_port(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind(("127.0.0.1", 0))
        client = VRChatOscClient("127.0.0.1", listener.getsockname()[1])
        try:
            status = client.receiver_status()
            self.assertTrue(status.available)
            self.assertEqual(status.pid, os.getpid())
        finally:
            client.close()
            listener.close()


if __name__ == "__main__":
    unittest.main()
