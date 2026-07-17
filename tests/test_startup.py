from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from enter_vr_ime import startup


class StartupTests(unittest.TestCase):
    def test_enabled_command_marks_the_launch_as_startup_mode(self) -> None:
        key_context = MagicMock()
        key_context.__enter__.return_value = MagicMock()
        executable = r"C:\Program Files\EnterVRIME\EnterVRIME.exe"

        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", executable),
            patch.object(startup.winreg, "CreateKey", return_value=key_context),
            patch.object(startup.winreg, "SetValueEx") as set_value,
        ):
            startup.set_startup_enabled(True)

        self.assertEqual(
            set_value.call_args.args[4],
            subprocess.list2cmdline([executable, "--startup"]),
        )

    def test_source_mode_cannot_create_a_broken_startup_entry(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            with self.assertRaisesRegex(RuntimeError, "只能在打包版"):
                startup.set_startup_enabled(True)


if __name__ == "__main__":
    unittest.main()
