from __future__ import annotations

import sys
import unittest
from pathlib import Path

from enter_vr_ime.windows import is_process_running, is_vrchat_executable


class ForegroundExecutableTests(unittest.TestCase):
    def test_process_lookup_finds_the_current_python_runtime(self) -> None:
        self.assertTrue(is_process_running(Path(sys.executable).name))
        self.assertFalse(is_process_running("EnterVRIME-process-that-does-not-exist.exe"))

    def test_vrchat_executable_is_allowed_case_insensitively(self) -> None:
        self.assertTrue(is_vrchat_executable("VRChat.exe"))
        self.assertTrue(is_vrchat_executable("vrchat.exe"))

    def test_other_or_unknown_executable_is_rejected(self) -> None:
        self.assertFalse(is_vrchat_executable("chrome.exe"))
        self.assertFalse(is_vrchat_executable(None))


if __name__ == "__main__":
    unittest.main()
