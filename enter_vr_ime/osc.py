from __future__ import annotations

import socket
import logging
import struct
from collections.abc import Iterable
from typing import Any


def _osc_string(value: str) -> bytes:
    encoded = value.encode("utf-8") + b"\x00"
    return encoded + (b"\x00" * ((-len(encoded)) % 4))


def build_osc_message(address: str, arguments: Iterable[Any] = ()) -> bytes:
    if not address.startswith("/"):
        raise ValueError("OSC 地址必须以 / 开头")

    tags: list[str] = [","]
    payload: list[bytes] = []
    for value in arguments:
        if isinstance(value, bool):
            tags.append("T" if value else "F")
        elif isinstance(value, str):
            tags.append("s")
            payload.append(_osc_string(value))
        elif isinstance(value, int):
            tags.append("i")
            payload.append(struct.pack(">i", value))
        elif isinstance(value, float):
            tags.append("f")
            payload.append(struct.pack(">f", value))
        else:
            raise TypeError(f"不支持的 OSC 参数类型：{type(value).__name__}")

    return _osc_string(address) + _osc_string("".join(tags)) + b"".join(payload)


class VRChatOscClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        logger: logging.Logger | None = None,
    ) -> None:
        self.target = (host, port)
        self.logger = logger or logging.getLogger(__name__)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.logger.info("E500 osc_client_ready port=%d", port)

    def send_typing(self, active: bool) -> None:
        self._send("/chatbox/typing", [active])
        self.logger.debug("E502 osc_typing_sent active=%s", active)

    def send_chatbox(self, text: str, notify_sound: bool = False) -> None:
        # True bypasses VRChat's virtual keyboard and sends immediately.
        self._send("/chatbox/input", [text, True, notify_sound])
        self.logger.info(
            "E503 osc_chatbox_sent characters=%d lines=%d notify=%s",
            len(text),
            text.count("\n") + 1,
            notify_sound,
        )

    def close(self) -> None:
        self._socket.close()
        self.logger.info("E509 osc_client_closed")

    def _send(self, address: str, arguments: Iterable[Any]) -> None:
        self._socket.sendto(build_osc_message(address, arguments), self.target)
