from __future__ import annotations

import ctypes
import queue
import time
import tkinter as tk
from tkinter import ttk

import mss
from PIL import Image

from .config import AppConfig, load_config
from .hotkey import EnterHotkey
from .osc import VRChatOscClient
from .overlay import OverlayPosition, SteamVROverlay
from .tray import TrayIcon


BG = "#07111f"
PANEL = "#0f1d31"
INPUT_BG = "#172a46"
PRIMARY = "#22d3ee"
TEXT = "#f8fafc"
MUTED = "#9fb2c9"
ERROR = "#fb7185"


class VRChatImeApp:
    def __init__(self) -> None:
        self.config: AppConfig = load_config()
        self.events: queue.Queue[str] = queue.Queue()
        self.root = tk.Tk(className="EnterVRIME")
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)

        self.active = False
        self.previous_foreground_window = 0
        self.last_text_change = 0.0
        self.last_error = ""
        self.control_window: tk.Toplevel | None = None
        self.control_status: tk.StringVar | None = None
        self.counter = tk.StringVar(value=f"0 / {self.config.max_characters}")
        self.message = tk.StringVar(value="输入完成后按回车发送")

        self._build_input_panel()
        self.capture = mss.mss()
        self.osc = VRChatOscClient(self.config.osc_host, self.config.osc_port)
        self.hotkey = EnterHotkey(self.events)
        self.overlay = SteamVROverlay(
            OverlayPosition(
                self.config.overlay_width_m,
                self.config.overlay_y_m,
                self.config.overlay_z_m,
            )
        )
        self.tray = TrayIcon(self.events)

    def run(self) -> None:
        self.hotkey.start()
        self.overlay.start()
        self.tray.start()
        self.show_control_window()
        self.root.after(50, self._poll_events)
        self.root.after(500, self._refresh_control_status)
        self.root.after(800, self.tray.notify_ready)
        try:
            self.root.mainloop()
        finally:
            self._shutdown_services()

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

        # This space deliberately remains inside the captured panel: Windows IME
        # candidate windows open below the caret and are captured here as pixels.
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
        self.osc.send_typing(True)
        self.overlay.show()
        self.root.after(20, self._capture_frame)

    def send_input(self) -> None:
        text = self.text.get("1.0", "end-1c").rstrip("\n")
        if not text.strip():
            self.cancel_input()
            return
        if len(text) > self.config.max_characters:
            self._set_message(
                f"超过 VRChat 的 {self.config.max_characters} 字限制，请删掉 {len(text) - self.config.max_characters} 字",
                error=True,
            )
            return
        try:
            self.osc.send_chatbox(text, self.config.notify_sound)
            self.osc.send_typing(False)
        except OSError as exc:
            self._set_message(f"发送失败：{exc}", error=True)
            return
        self._finish_input()

    def cancel_input(self) -> None:
        if not self.active:
            return
        try:
            self.osc.send_typing(False)
        except OSError:
            pass
        self._finish_input()

    def _finish_input(self) -> None:
        self.active = False
        self.overlay.hide()
        self.root.withdraw()
        self.hotkey.enable()
        if self.previous_foreground_window:
            try:
                ctypes.windll.user32.SetForegroundWindow(self.previous_foreground_window)
            except OSError:
                pass

    def _on_return(self, _event: tk.Event) -> str:
        # Microsoft Pinyin and Sogou normally consume Return while composing.
        # The small guard also prevents a just-committed candidate from being
        # sent by the same physical key press on IMEs that forward that event.
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
            self._set_message("文字过长，红色计数归零前无法发送", error=True)
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
        except Exception as exc:
            self.last_error = str(exc)
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
        window.geometry("620x470")
        window.minsize(620, 470)
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
            wraplength=510,
        ).pack(anchor="w")
        ttk.Label(
            status_box,
            text=f"OSC 目标：{self.config.osc_host}:{self.config.osc_port}",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(8, 0))

        instructions = (
            "1. 用 Virtual Desktop 连接 Quest 3，并启动 SteamVR。\n"
            "2. 从 SteamVR 启动 VRChat，不要使用 VDXR 直连。\n"
            "3. 在 VRChat 快捷菜单中打开 OSC。\n"
            "4. 戴上头显后按回车，使用你原来的中文输入法；再按回车发送。"
        )
        ttk.Label(
            body,
            text=instructions,
            justify="left",
            font=("Microsoft YaHei UI", 11),
            wraplength=540,
        ).pack(anchor="w", pady=22)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="退出", command=self.quit).pack(side="right")
        ttk.Button(buttons, text="隐藏到托盘", command=window.withdraw).pack(side="right", padx=10)
        ttk.Button(buttons, text="立即输入", command=self.activate_input).pack(side="left")

    def _refresh_control_status(self) -> None:
        if self.control_status is not None:
            hotkey_state = "回车键已就绪" if self.hotkey.registered else (self.hotkey.error or "回车键未就绪")
            self.control_status.set(f"{self.overlay.state}\n{hotkey_state}")
        if self.root.winfo_exists():
            self.root.after(500, self._refresh_control_status)

    def _set_message(self, text: str, error: bool = False) -> None:
        self.message.set(text)
        self.message_label.configure(fg=ERROR if error else MUTED)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event == "activate":
                    self.activate_input()
                elif event == "show_control":
                    self.show_control_window()
                elif event == "quit":
                    self.quit()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(50, self._poll_events)

    def quit(self) -> None:
        if self.active:
            self.cancel_input()
        self.root.quit()

    def _shutdown_services(self) -> None:
        try:
            self.hotkey.stop()
        finally:
            try:
                self.overlay.stop()
            finally:
                self.osc.close()
                self.capture.close()
                self.tray.stop()
