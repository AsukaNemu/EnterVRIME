from __future__ import annotations

import ctypes
import sys

from enter_vr_ime.app import VRChatImeApp


def enable_per_monitor_dpi_awareness() -> None:
    """Keep Tk coordinates aligned with screen-capture pixels on scaled displays."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def main() -> int:
    if sys.platform != "win32":
        print("EnterVRIME 目前只支持 Windows。")
        return 1

    enable_per_monitor_dpi_awareness()
    app = VRChatImeApp()
    if "--smoke-test" in sys.argv:
        app.root.update_idletasks()
        app.capture.close()
        app.osc.close()
        app.root.destroy()
        return 0
    if "--runtime-smoke-test" in sys.argv:
        app.root.after(2500, app.quit)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
