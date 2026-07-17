from __future__ import annotations

import ctypes
import sys

from enter_vr_ime.app import VRChatImeApp
from enter_vr_ime.diagnostics import DiagnosticManager
from enter_vr_ime.single_instance import SingleInstanceMutex, show_existing_instance


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


def show_error(code: str, detail: str) -> None:
    message = f"EnterVRIME 无法继续运行。\n\n错误编号：{code}\n{detail}"
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "EnterVRIME", 0x10)
    except (AttributeError, OSError):
        print(message)


def show_fatal_error(log_path: str) -> None:
    show_error("E900", f"请把下面的日志路径发给开发者：\n{log_path}")


def main() -> int:
    if sys.platform != "win32":
        print("EnterVRIME 目前只支持 Windows。")
        return 1

    enable_per_monitor_dpi_awareness()
    instance = SingleInstanceMutex()
    try:
        if not instance.acquire():
            show_existing_instance()
            return 0
    except OSError as exc:
        show_error("E101", f"无法完成启动检查：\n{exc}")
        return 1

    try:
        diagnostics = DiagnosticManager()
        app: VRChatImeApp | None = None
        try:
            startup_launch = "--startup" in sys.argv
            diagnostics.logger.info("E106 startup_launch_mode enabled=%s", startup_launch)
            app = VRChatImeApp(diagnostics, startup_launch=startup_launch)
            if "--smoke-test" in sys.argv:
                app.close_for_smoke_test()
                return 0
            if "--overlay-smoke-test" in sys.argv:
                app.root.after(800, app.activate_input)
                app.root.after(4500, app.overlay.force_standby_promotion)
                app.root.after(8500, app.overlay.force_standby_promotion)
                app.root.after(10500, app.overlay.force_transient_failures)
                app.root.after(10600, app.overlay.force_standby_promotion)
                app.root.after(18000, app.quit)
            if "--runtime-smoke-test" in sys.argv:
                app.root.after(2500, app.quit)
            app.run()
            return 0
        except Exception:
            diagnostics.logger.critical("E900 application_unhandled", exc_info=True)
            diagnostics.flush()
            show_fatal_error(str(diagnostics.session_log))
            return 1
        finally:
            diagnostics.shutdown()
    finally:
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
