from __future__ import annotations

import faulthandler
import ipaddress
import json
import logging
import os
import platform
import sys
import threading
import zipfile
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from . import __version__
from .config import AppConfig, app_data_dir


LOG_RETENTION = 10
LOG_MAX_BYTES = 2 * 1024 * 1024


class DiagnosticManager:
    """Own session logs, crash hooks, privacy filtering, and diagnostic exports."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or app_data_dir()
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_id = f"{stamp}-{os.getpid()}"
        self.session_log = self.logs_dir / f"session-{self.session_id}.log"
        self.crash_log = self.logs_dir / f"crash-{self.session_id}.log"
        self.logger = logging.getLogger(f"entervrime.{self.session_id}.{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        handler = RotatingFileHandler(
            self.session_log,
            maxBytes=LOG_MAX_BYTES,
            backupCount=1,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s.%(msecs)03d %(levelname)s [%(threadName)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self.logger.addHandler(handler)
        self._handler = handler
        self._closed = False
        self._previous_sys_hook = sys.excepthook
        self._previous_thread_hook = threading.excepthook
        self._crash_stream = self.crash_log.open("a", encoding="utf-8")
        try:
            faulthandler.enable(file=self._crash_stream, all_threads=True)
        except (OSError, RuntimeError):
            pass
        self._install_exception_hooks()
        self._prune_old_logs()
        self.logger.info(
            "E000 app_start version=%s os=%s release=%s frozen=%s pid=%d",
            __version__,
            platform.system(),
            platform.release(),
            bool(getattr(sys, "frozen", False)),
            os.getpid(),
        )

    def safe_config(self, config: AppConfig) -> dict[str, Any]:
        return {
            "osc_host_class": self._classify_host(config.osc_host),
            "osc_port": config.osc_port,
            "notify_sound": config.notify_sound,
            "overlay_width_m": config.overlay_width_m,
            "overlay_y_m": config.overlay_y_m,
            "overlay_z_m": config.overlay_z_m,
            "capture_fps": config.capture_fps,
            "window_width_px": config.window_width_px,
            "window_height_px": config.window_height_px,
            "max_characters": config.max_characters,
        }

    def default_export_name(self) -> str:
        return f"EnterVRIME-Diagnostics-{self.session_id}.zip"

    def build_summary(self, status: dict[str, Any]) -> str:
        lines = [
            f"EnterVRIME {__version__}",
            f"Session: {self.session_id}",
            f"Windows: {platform.platform()}",
            f"Frozen build: {bool(getattr(sys, 'frozen', False))}",
        ]
        for key, value in status.items():
            lines.append(f"{key}: {value}")
        lines.append(f"Log: {self.session_log}")
        return "\n".join(lines)

    def export_zip(
        self,
        destination: Path,
        config: AppConfig,
        status: dict[str, Any],
        display: dict[str, Any],
    ) -> Path:
        destination = destination.with_suffix(".zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".zip.tmp")
        temporary.unlink(missing_ok=True)
        self.flush()

        log_paths = self._recent_logs(limit=8)
        manifest = {
            "schema_version": 1,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "app_version": __version__,
            "session_id": self.session_id,
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "frozen_build": bool(getattr(sys, "frozen", False)),
                "machine": platform.machine(),
            },
            "config": self.safe_config(config),
            "display": display,
            "status": status,
            "included_logs": [path.name for path in log_paths],
            "privacy": {
                "chat_text_recorded": False,
                "ime_candidates_recorded": False,
                "user_paths_redacted": True,
            },
        }

        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "diagnostics.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            archive.writestr(
                "README.txt",
                "EnterVRIME 诊断包\n\n"
                "本文件用于定位启动、热键、SteamVR、悬浮层、捕获与 OSC 问题。\n"
                "诊断包不会包含聊天正文、拼音组合内容或候选词。\n"
                "用户目录路径已在导出时脱敏。\n",
            )
            for path in log_paths:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    content = f"E905 log_read_failed type={exc.__class__.__name__}\n"
                archive.writestr(f"logs/{path.name}", self._redact(content))

        os.replace(temporary, destination)
        self.logger.info(
            "E120 diagnostics_exported file=%s logs=%d",
            destination.name,
            len(log_paths),
        )
        return destination

    def open_logs_folder(self) -> None:
        os.startfile(self.logs_dir)  # type: ignore[attr-defined]
        self.logger.info("E121 logs_folder_opened")

    def report_tk_exception(self, exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        self.logger.critical("E902 tk_callback_unhandled", exc_info=(exc_type, exc, tb))

    def flush(self) -> None:
        for handler in self.logger.handlers:
            handler.flush()
        self._crash_stream.flush()

    def shutdown(self) -> None:
        if self._closed:
            return
        self.logger.info("E099 app_stop")
        self.flush()
        sys.excepthook = self._previous_sys_hook
        threading.excepthook = self._previous_thread_hook
        try:
            faulthandler.disable()
        except RuntimeError:
            pass
        self._crash_stream.close()
        self._handler.close()
        self.logger.removeHandler(self._handler)
        self._closed = True

    def _install_exception_hooks(self) -> None:
        def sys_hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
            self.logger.critical("E900 main_thread_unhandled", exc_info=(exc_type, exc, tb))
            self.flush()

        def thread_hook(args: threading.ExceptHookArgs) -> None:
            self.logger.critical(
                "E901 background_thread_unhandled thread=%s",
                args.thread.name if args.thread else "unknown",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            self.flush()

        sys.excepthook = sys_hook
        threading.excepthook = thread_hook

    def _prune_old_logs(self) -> None:
        for pattern in ("session-*.log*", "crash-*.log*"):
            paths = sorted(
                self.logs_dir.glob(pattern),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for path in paths[LOG_RETENTION:]:
                try:
                    path.unlink()
                except OSError:
                    self.logger.warning("E904 log_prune_failed file=%s", path.name)

    def _recent_logs(self, limit: int) -> list[Path]:
        paths = list(self.logs_dir.glob("session-*.log*")) + list(
            self.logs_dir.glob("crash-*.log*")
        )
        return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]

    @staticmethod
    def _classify_host(host: str) -> str:
        normalized = host.strip().lower()
        if normalized in {"localhost", "127.0.0.1", "::1"}:
            return "loopback"
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError:
            return "custom-host"
        if address.is_loopback:
            return "loopback"
        if address.is_private:
            return "private-network"
        return "public-network"

    @staticmethod
    def _redact(text: str) -> str:
        replacements = {
            str(Path.home()): "%USERPROFILE%",
            os.environ.get("LOCALAPPDATA", ""): "%LOCALAPPDATA%",
            os.environ.get("APPDATA", ""): "%APPDATA%",
            os.environ.get("USERNAME", ""): "%USERNAME%",
        }
        result = text
        for original, replacement in replacements.items():
            if original:
                result = result.replace(original, replacement)
                result = result.replace(original.replace("\\", "/"), replacement)
        return result
