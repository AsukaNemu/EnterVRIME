from __future__ import annotations

import unittest

from enter_vr_ime.windows import is_vrchat_executable


class ForegroundExecutableTests(unittest.TestCase):
    def test_vrchat_executable_is_allowed_case_insensitively(self) -> None:
        self.assertTrue(is_vrchat_executable("VRChat.exe"))
        self.assertTrue(is_vrchat_executable("vrchat.exe"))

    def test_other_or_unknown_executable_is_rejected(self) -> None:
        self.assertFalse(is_vrchat_executable("chrome.exe"))
        self.assertFalse(is_vrchat_executable(None))


if __name__ == "__main__":
    unittest.main()
