from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from enter_vr_ime.config import AppConfig
from enter_vr_ime.diagnostics import DiagnosticManager


class DiagnosticManagerTests(unittest.TestCase):
    def test_export_is_redacted_and_privacy_manifest_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base_dir = Path(temporary) / "app-data"
            manager = DiagnosticManager(base_dir=base_dir)
            try:
                private_path = str(Path.home() / "SecretFolder" / "trace.txt")
                manager.logger.error("E999 test_path=%s", private_path)
                manager.flush()

                destination = manager.export_zip(
                    Path(temporary) / "diagnostics.zip",
                    AppConfig(),
                    {"last_error_code": "E999"},
                    {"screen_width_px": 1920, "screen_height_px": 1080},
                )

                with zipfile.ZipFile(destination) as archive:
                    manifest = json.loads(archive.read("diagnostics.json"))
                    exported_logs = "\n".join(
                        archive.read(name).decode("utf-8")
                        for name in archive.namelist()
                        if name.startswith("logs/")
                    )

                self.assertEqual(manifest["config"]["osc_host_class"], "loopback")
                self.assertFalse(manifest["privacy"]["chat_text_recorded"])
                self.assertFalse(manifest["privacy"]["ime_candidates_recorded"])
                self.assertTrue(manifest["privacy"]["user_paths_redacted"])
                self.assertNotIn(str(Path.home()), exported_logs)
                username = os.environ.get("USERNAME")
                if username:
                    self.assertNotIn(username, exported_logs)
                self.assertIn("%USERPROFILE%", exported_logs)
                self.assertIn("E999", exported_logs)
            finally:
                manager.shutdown()

    def test_host_is_classified_without_exporting_the_address(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = DiagnosticManager(base_dir=Path(temporary))
            try:
                safe = manager.safe_config(AppConfig(osc_host="192.168.50.25"))
                self.assertEqual(safe["osc_host_class"], "private-network")
                self.assertNotIn("osc_host", safe)
            finally:
                manager.shutdown()


if __name__ == "__main__":
    unittest.main()
