from __future__ import annotations

import ctypes
import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import mss
from PIL import Image

from .config import AppConfig, load_config
from .diagnostics import DiagnosticManager
from .hotkey import EnterHotkey
from .osc import VRChatOscClient
from .overlay import OverlayPosition, SteamVROverlay
from .startup import is_startup_enabled, set_startup_enabled
from .tray import TrayIcon
from .windows import foreground_executable_name, is_vrchat_executable


BG = "#07111f"
PANEL = "#0f1d31"
INPUT_BG = "#172a46"
PRIMARY = "#22d3ee"
TEXT = "#f8fafc"
MUTED = "#9fb2c9"
ERROR = "#fb7185"


class VRChatImeApp:
    def __init__(self, diagnostics: DiagnosticManager) -> None:
        self.diagnostics = diagnostics
        self.logger = diagnostics.logger
        self.config: AppConfig = load_config(self.logger)
        self.logger.info("E103 config_ready values=%s", diagnostics.safe_config(self.config))
        self.events: queue.Queue[str] = queue.Queue()
        self.root = tk.Tk(className="EnterVRIME")
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.report_callback_exception = self._report_callback_exception

        self.active = False
        self.previous_foreground_window = 0
        self.last_text_change = 0.0
        self.last_error_code = ""
        self.last_error = ""
        self._capture_error_active = False
        self._osc_receiver_available: bool | None = None
        self._osc_receiver_pid: int | None = None
        self.control_window: tk.Toplevel | None = None
        self.control_status: tk.StringVar | None = None
        self.start_with_windows = tk.BooleanVar(value=is_startup_enabled())
        self.counter = tk.StringVar(value=f"0 / {self.config.max_characters}")
        self.message = tk.StringVar(value="输入完成后按回车发送")

        self._build_input_panel()
        self.capture = mss.mss()
        self.osc = VRChatOscClient(
            self.config.osc_host,
            self.config.osc_port,
            self.logger,
        )
        self.hotkey = EnterHotkey(self.events, self.logger)
        self.overlay = SteamVROverlay(
            OverlayPosition(
                self.config.overlay_width_m,
                self.config.overlay_y_m,
                self.config.overlay_z_m,
            ),
            self.logger,
        )
        self.tray = TrayIcon(self.events, self.logger)
        self.logger.info(
            "E104 ui_ready screen=%dx%d panel=%dx%d",
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            self.config.window_width_px,
            self.config.window_height_px,
        )

    def run(self) -> None:
        self.hotkey.start()
        self.overlay.start()
        self.tray.start()
        self.show_control_window()
        self.root.after(50, self._poll_events)
        self.root.after(100, self._refresh_hotkey_context)
        self.root.after(500, self._refresh_control_status)
        self.root.after(800, self.tray.notify_ready)
        self.logger.info("E105 main_loop_started")
        try:
            self.root.mainloop()
        finally:
            self._shutdown_services()

    def close_for_smoke_test(self) -> None:
        self.osc.close()
        self.capture.close()
        self.root.destroy()

    def _build_input_panel(self) -> None:
        width = self.config.window_width_px
        height = self.config.window_height_px
        self.root.geometry(f"{width}x{height}+0+0")

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=34, pady=(24, 10))
        tk.Label(
            header,
            text="VRCHAT 中文输入",
            bg=BG,
            fg=PRIMARY,
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            textvariable=self.counter,
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 13),
        ).pack(side="right")

        input_shell = tk.Frame(self.root, bg=PRIMARY, padx=2, pady=2)
        input_shell.pack(fill="x", padx=34)
        self.text = tk.Text(
            input_shell,
            height=3,
            wrap="word",
            undo=True,
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=PRIMARY,
            selectbackground="#155e75",
            selectforeground=TEXT,
            relief="flat",
            borderwidth=0,
            padx=18,
            pady=13,
            font=("Microsoft YaHei UI", 25),
        )
        self.text.pack(fill="x")
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<Shift-Return>", self._on_shift_return)
        self.text.bind("<Escape>", self._on_escape)
        self.text.bind("<<Modified>>", self._on_text_modified)

        candidate_space = tk.Frame(self.root, bg=PANEL, height=105)
        candidate_space.pack(fill="x", padx=34, pady=(12, 0))
        candidate_space.pack_propagate(False)
        tk.Label(
            candidate_space,
            text="候选词会显示在这里",
            bg=PANEL,
            fg="#5f7896",
            font=("Microsoft YaHei UI", 13),
        ).pack(anchor="nw", padx=16, pady=12)

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=36, pady=12)
        self.message_label = tk.Label(
            footer,
            textvariable=self.message,
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 13),
        )
        self.message_label.pack(side="left")
        tk.Label(
            footer,
            text="Enter 发送   Shift+Enter 换行   Esc 取消",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 13),
        ).pack(side="right")

    def activate_input(self) -> None:
        if self.active:
            self.root.lift()
            self.text.focus_force()
            return

        self.active = True
        self.hotkey.disable()
        self.previous_foreground_window = ctypes.windll.user32.GetForegroundWindow()
        self.text.delete("1.0", "end")
        self.text.edit_modified(False)
        self.counter.set(f"0 / {self.config.max_characters}")
        if self._update_osc_receiver_status() is False:
            self._set_message(
                "[E505] VRChat 未监听 OSC；请打开操作菜单 → OSC → OSC Debug",
                error=True,
            )
        else:
            self._set_message("正在输入；中文候选词会显示在下方")

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - self.config.window_width_px) // 2)
        y = max(20, (screen_height - self.config.window_height_px) // 2)
        self.root.geometry(
            f"{self.config.window_width_px}x{self.config.window_height_px}+{x}+{y}"
        )
        self.root.deiconify()
        self.root.lift()
        self.root.update_idletasks()
        self.text.focus_force()
        try:
            self.osc.send_typing(True)
        except OSError as exc:
            self._record_error("E501", "osc_typing_start_failed", exc)
            self._set_message("[E501] OSC 输入状态发送失败；仍可继续输入", error=True)
        self.overlay.show()
        self.logger.info("E110 input_activated")
        self.root.after(20, self._capture_frame)

    def send_input(self) -> None:
        text = self.text.get("1.0", "end-1c").rstrip("\n")
        if not text.strip():
            self.logger.info("E112 empty_input_cancelled")
            self.cancel_input()
            return
        if len(text) > self.config.max_characters:
            self._set_message(
                f"超过 VRChat 的 {self.config.max_characters} 字限制，请删掉 {len(text) - self.config.max_characters} 字",
                error=True,
            )
            self.logger.warning("E113 input_too_long characters=%d", len(text))
            return
        if self._update_osc_receiver_status() is False:
            self.last_error_code = "E505"
            self.last_error = "OscReceiverMissing"
            self._set_message(
                "[E505] VRChat 未监听 OSC；打开操作菜单 → OSC → OSC Debug 后再次回车",
                error=True,
            )
            self.logger.warning("E505 osc_receiver_missing port=%d", self.config.osc_port)
            return
        try:
            self.osc.send_chatbox(text, self.config.notify_sound)
            self.osc.send_typing(False)
        except OSError as exc:
            self._record_error("E501", "osc_chat_send_failed", exc)
            self._set_message("[E501] 发送失败，请导出诊断包", error=True)
            return
        self.logger.info("E111 input_sent characters=%d lines=%d", len(text), text.count("\n") + 1)
        self._finish_input()

    def cancel_input(self) -> None:
        if not self.active:
            return
        try:
            self.osc.send_typing(False)
        except OSError as exc:
            self._record_error("E501", "osc_typing_stop_failed", exc)
        self.logger.info("E114 input_cancelled")
        self._finish_input()

    def _finish_input(self) -> None:
        self.active = False
        self.overlay.hide()
        self.root.withdraw()
        if self.previous_foreground_window:
            try:
                ctypes.windll.user32.SetForegroundWindow(self.previous_foreground_window)
            except OSError as exc:
                self.logger.warning("E115 foreground_restore_failed type=%s", exc.__class__.__name__)

    def _on_return(self, _event: tk.Event) -> str:
        if time.monotonic() - self.last_text_change < 0.08:
            return "break"
        self.root.after_idle(self.send_input)
        return "break"

    def _on_shift_return(self, _event: tk.Event) -> str:
        self.text.insert("insert", "\n")
        return "break"

    def _on_escape(self, _event: tk.Event) -> str:
        self.cancel_input()
        return "break"

    def _on_text_modified(self, _event: tk.Event) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self.last_text_change = time.monotonic()
        length = len(self.text.get("1.0", "end-1c"))
        self.counter.set(f"{length} / {self.config.max_characters}")
        if length > self.config.max_characters:
            self._set_message("文字过长，计数回到限制内前无法发送", error=True)
        else:
            if self._osc_receiver_available is False:
                self._set_message(
                    "[E505] VRChat 未监听 OSC；请打开操作菜单 → OSC → OSC Debug",
                    error=True,
                )
            else:
                self._set_message("正在输入；中文候选词会显示在下方")

    def _capture_frame(self) -> None:
        if not self.active:
            return
        try:
            self.root.update_idletasks()
            left = self.root.winfo_rootx()
            top = self.root.winfo_rooty()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            shot = self.capture.grab({"left": left, "top": top, "width": width, "height": height})
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            rgba = image.convert("RGBA").tobytes()
            self.overlay.submit_rgba(rgba, width, height)
            if self._capture_error_active:
                self.logger.info("E402 capture_recovered")
                self._capture_error_active = False
        except Exception as exc:
            self.last_error_code = "E401"
            self.last_error = exc.__class__.__name__
            if not self._capture_error_active:
                self.logger.error("E401 screen_capture_failed", exc_info=True)
                self._capture_error_active = True
                self._set_message("[E401] 画面捕获失败，请导出诊断包", error=True)
        interval_ms = max(33, round(1000 / self.config.capture_fps))
        self.root.after(interval_ms, self._capture_frame)

    def show_control_window(self) -> None:
        if self.control_window is not None and self.control_window.winfo_exists():
            self.control_window.deiconify()
            self.control_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.control_window = window
        window.title("EnterVRIME")
        window.geometry("660x680")
        window.minsize(660, 680)
        window.configure(bg="#f5f7fb")
        window.protocol("WM_DELETE_WINDOW", window.withdraw)

        body = ttk.Frame(window, padding=28)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="EnterVRIME", font=("Microsoft YaHei UI", 24, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="Virtual Desktop + SteamVR + VRChat 的实体键盘中文输入",
            font=("Microsoft YaHei UI", 11),
        ).pack(anchor="w", pady=(2, 22))

        self.control_status = tk.StringVar(value="正在检查 SteamVR…")
        status_box = ttk.LabelFrame(body, text="当前状态", padding=16)
        status_box.pack(fill="x")
        ttk.Label(
            status_box,
            textvariable=self.control_status,
            font=("Microsoft YaHei UI", 11),
            wraplength=550,
        ).pack(anchor="w")
        ttk.Label(
            status_box,
            text=f"OSC 目标：{self.config.osc_host}:{self.config.osc_port}",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(8, 0))

        tk.Label(
            body,
            text=(
                "开始前必须在 VRChat 内开启 OSC\n"
                "路径：快捷菜单 → OSC → 开启（或打开 OSC Debug）"
            ),
            justify="left",
            anchor="w",
            bg="#fff4e5",
            fg="#b45309",
            bd=1,
            relief="solid",
            padx=14,
            pady=10,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(fill="x", pady=(14, 0))

        instructions = (
            "1. 用 Virtual Desktop 连接 Quest 3，并启动 SteamVR。\n"
            "2. 从 SteamVR 启动 VRChat，不要使用 VDXR 直连。\n"
            "3. 在 VRChat 快捷菜单中确认 OSC 已开启。\n"
            "4. 戴上头显后按回车输入，再按回车发送。"
        )
        ttk.Label(
            body,
            text=instructions,
            justify="left",
            font=("Microsoft YaHei UI", 11),
            wraplength=580,
        ).pack(anchor="w", pady=20)

        ttk.Checkbutton(
            body,
            text="随 Windows 登录自动启动（安装版默认开启，推荐保持开启）",
            variable=self.start_with_windows,
            command=self._toggle_startup,
        ).pack(anchor="w", pady=(0, 14))

        diagnostics_row = ttk.LabelFrame(body, text="测试与诊断", padding=12)
        diagnostics_row.pack(fill="x", pady=(0, 18))
        ttk.Button(diagnostics_row, text="导出诊断包", command=self.export_diagnostics).pack(side="left")
        ttk.Button(diagnostics_row, text="打开日志目录", command=self.open_logs_folder).pack(side="left", padx=8)
        ttk.Button(diagnostics_row, text="复制诊断摘要", command=self.copy_diagnostic_summary).pack(side="left")

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="退出", command=self.quit).pack(side="right")
        ttk.Button(buttons, text="隐藏到托盘", command=window.withdraw).pack(side="right", padx=10)
        ttk.Button(buttons, text="立即输入", command=self.activate_input).pack(side="left")

    def export_diagnostics(self) -> None:
        desktop = Path.home() / "Desktop"
        parent = self.control_window if self.control_window is not None else self.root
        destination = filedialog.asksaveasfilename(
            parent=parent,
            title="导出 EnterVRIME 诊断包",
            initialdir=str(desktop if desktop.exists() else Path.home()),
            initialfile=self.diagnostics.default_export_name(),
            defaultextension=".zip",
            filetypes=[("ZIP 诊断包", "*.zip")],
        )
        if not destination:
            self.logger.info("E122 diagnostics_export_cancelled")
            return
        try:
            result = self.diagnostics.export_zip(
                Path(destination),
                self.config,
                self._diagnostic_status(),
                self._display_info(),
            )
        except Exception as exc:
            self._record_error("E123", "diagnostics_export_failed", exc)
            messagebox.showerror("EnterVRIME", "[E123] 诊断包导出失败，请打开日志目录。", parent=parent)
            return
        messagebox.showinfo("EnterVRIME", f"诊断包已导出：\n{result}", parent=parent)

    def _toggle_startup(self) -> None:
        enabled = self.start_with_windows.get()
        try:
            set_startup_enabled(enabled)
        except Exception as exc:
            self.start_with_windows.set(not enabled)
            self._record_error("E126", "startup_setting_failed", exc)
            messagebox.showerror(
                "EnterVRIME",
                "[E126] 无法修改开机启动设置。",
                parent=self.control_window,
            )
            return
        self.logger.info("E127 startup_setting_changed enabled=%s", enabled)

    def open_logs_folder(self) -> None:
        try:
            self.diagnostics.open_logs_folder()
        except OSError as exc:
            self._record_error("E124", "logs_folder_open_failed", exc)
            messagebox.showerror("EnterVRIME", "[E124] 无法打开日志目录。")

    def copy_diagnostic_summary(self) -> None:
        summary = self.diagnostics.build_summary(self._diagnostic_status())
        self.root.clipboard_clear()
        self.root.clipboard_append(summary)
        self.root.update()
        self.logger.info("E125 diagnostics_summary_copied")
        messagebox.showinfo("EnterVRIME", "诊断摘要已复制到剪贴板。")

    def _diagnostic_status(self) -> dict[str, object]:
        return {
            "overlay": self.overlay.state,
            "hotkey_registered": self.hotkey.registered,
            "hotkey_error": self.hotkey.error or "none",
            "startup_at_login": self.start_with_windows.get(),
            "osc_receiver": self._osc_receiver_label(),
            "osc_receiver_pid": self._osc_receiver_pid or "none",
            "input_active": self.active,
            "last_error_code": self.last_error_code or "none",
            "last_error_type": self.last_error or "none",
        }

    def _display_info(self) -> dict[str, int]:
        return {
            "screen_width_px": self.root.winfo_screenwidth(),
            "screen_height_px": self.root.winfo_screenheight(),
            "panel_width_px": self.config.window_width_px,
            "panel_height_px": self.config.window_height_px,
        }

    def _refresh_control_status(self) -> None:
        self._update_osc_receiver_status()
        if self.control_status is not None:
            if self.hotkey.error:
                hotkey_state = self.hotkey.error
            elif self.active:
                hotkey_state = "回车监听：输入中"
            elif self.hotkey.registered:
                hotkey_state = "回车监听：VRChat 前台，已就绪"
            else:
                hotkey_state = "回车监听：仅在 VRChat 位于前台时启用"
            error_state = f"\n最近错误：{self.last_error_code}" if self.last_error_code else ""
            startup_state = "已开启" if self.start_with_windows.get() else "未开启"
            self.control_status.set(
                f"{self.overlay.state}\n{hotkey_state}\n{self._osc_receiver_label()}"
                f"\n开机自动启动：{startup_state}{error_state}"
            )
        if self.root.winfo_exists():
            self.root.after(1000, self._refresh_control_status)

    def _refresh_hotkey_context(self) -> None:
        foreground = foreground_executable_name()
        should_register = not self.active and is_vrchat_executable(foreground)
        if should_register and not self.hotkey.registered:
            self.hotkey.enable()
        elif not should_register and self.hotkey.registered:
            self.hotkey.disable()
        if self.root.winfo_exists():
            self.root.after(150, self._refresh_hotkey_context)

    def _update_osc_receiver_status(self) -> bool | None:
        status = self.osc.receiver_status()
        previous = self._osc_receiver_available
        self._osc_receiver_available = status.available
        self._osc_receiver_pid = status.pid
        if status.available != previous:
            if status.available is True:
                self.logger.info(
                    "E506 osc_receiver_detected port=%d pid=%d",
                    self.config.osc_port,
                    status.pid or 0,
                )
                if self.last_error_code == "E505":
                    self.last_error_code = ""
                    self.last_error = ""
                    if self.active:
                        self._set_message("OSC 已连接；再次按回车即可发送")
            elif status.available is False:
                self.logger.warning("E505 osc_receiver_missing port=%d", self.config.osc_port)
            else:
                self.logger.info("E507 osc_receiver_unverifiable")
        return status.available

    def _osc_receiver_label(self) -> str:
        if self._osc_receiver_available is True:
            return f"OSC：VRChat 已监听 {self.config.osc_host}:{self.config.osc_port}"
        if self._osc_receiver_available is False:
            return "OSC：[E505] 未检测到监听，请打开操作菜单 → OSC → OSC Debug"
        return f"OSC：目标 {self.config.osc_host}:{self.config.osc_port}（远程或无法检测）"

    def _set_message(self, text: str, error: bool = False) -> None:
        self.message.set(text)
        self.message_label.configure(fg=ERROR if error else MUTED)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event == "activate":
                    foreground = foreground_executable_name()
                    if is_vrchat_executable(foreground):
                        self.activate_input()
                    else:
                        self.logger.debug(
                            "E210 hotkey_activation_ignored foreground=%s",
                            foreground or "unknown",
                        )
                elif event == "show_control":
                    self.show_control_window()
                elif event == "export_diagnostics":
                    self.export_diagnostics()
                elif event == "open_logs":
                    self.open_logs_folder()
                elif event == "quit":
                    self.quit()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(50, self._poll_events)

    def _record_error(self, code: str, event: str, exc: BaseException) -> None:
        self.last_error_code = code
        self.last_error = exc.__class__.__name__
        self.logger.error("%s %s type=%s", code, event, exc.__class__.__name__, exc_info=True)

    def _report_callback_exception(
        self,
        exc_type: type[BaseException],
        exc: BaseException,
        tb: object,
    ) -> None:
        self.last_error_code = "E902"
        self.last_error = exc.__class__.__name__
        self.diagnostics.report_tk_exception(exc_type, exc, tb)
        try:
            messagebox.showerror("EnterVRIME", "[E902] 界面操作发生异常，请导出诊断包。")
        except tk.TclError:
            pass

    def quit(self) -> None:
        if self.active:
            self.cancel_input()
        self.logger.info("E106 quit_requested")
        self.root.quit()

    def _shutdown_services(self) -> None:
        self.logger.info("E107 services_stopping")
        try:
            self.hotkey.stop()
        except Exception:
            self.logger.error("E203 hotkey_stop_failed", exc_info=True)
        try:
            self.overlay.stop()
        except Exception:
            self.logger.error("E305 overlay_stop_failed", exc_info=True)
        try:
            self.osc.close()
        except Exception:
            self.logger.error("E504 osc_close_failed", exc_info=True)
        try:
            self.capture.close()
        except Exception:
            self.logger.error("E403 capture_close_failed", exc_info=True)
        try:
            self.tray.stop()
        except Exception:
            self.logger.error("E131 tray_stop_failed", exc_info=True)
        self.logger.info("E108 services_stopped")
