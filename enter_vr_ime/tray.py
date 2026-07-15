from __future__ import annotations

import queue
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont


def _icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), "#0b1220")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#22d3ee")
    font_path = Path("C:/Windows/Fonts/msyhbd.ttc")
    try:
        font = ImageFont.truetype(str(font_path), 35)
    except OSError:
        font = ImageFont.load_default()
    draw.text((32, 31), "中", anchor="mm", font=font, fill="#07111f")
    return image


class TrayIcon:
    def __init__(self, events: queue.Queue[str]) -> None:
        self.events = events
        menu = pystray.Menu(
            pystray.MenuItem("立即输入", lambda *_: self.events.put("activate"), default=True),
            pystray.MenuItem("状态与说明", lambda *_: self.events.put("show_control")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda *_: self.events.put("quit")),
        )
        self.icon = pystray.Icon("EnterVRIME", _icon_image(), "EnterVRIME 中文输入", menu)
        self._thread = threading.Thread(target=self.icon.run, name="tray-icon", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def notify_ready(self) -> None:
        try:
            self.icon.notify("按回车开始中文输入", "EnterVRIME 已就绪")
        except (NotImplementedError, OSError):
            pass

    def stop(self) -> None:
        self.icon.stop()
        self._thread.join(timeout=2.0)
