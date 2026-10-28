from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from tools import generate_assets


class ImageCompatibilityTests(unittest.TestCase):
    def test_asset_generator_writes_readable_png_and_multisize_ico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            with patch.object(generate_assets, "ASSETS", assets):
                generate_assets.main()
            with Image.open(assets / "EnterVRIME.png") as image:
                image.load()
                self.assertEqual(image.size, (256, 256))
                self.assertEqual(image.mode, "RGBA")
            with Image.open(assets / "EnterVRIME.ico") as image:
                image.load()
                self.assertEqual(image.format, "ICO")
                self.assertIn((16, 16), image.ico.sizes())
                self.assertIn((256, 256), image.ico.sizes())

    @unittest.skipUnless(sys.platform == "win32", "Windows tray backend")
    def test_tray_icon_can_be_rendered_with_current_pillow(self) -> None:
        from enter_vr_ime.tray import _icon_image

        image = _icon_image()
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.mode, "RGBA")
        self.assertIsNotNone(image.getbbox())


if __name__ == "__main__":
    unittest.main()
