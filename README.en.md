<div align="center">
  <img src="docs/assets/hero.svg" alt="EnterVRIME — Press Enter. Type Chinese. Stay in VR." width="100%" />

  **Press Enter. Type Chinese with your physical keyboard. Stay in VR.**

  Quest 3 · Virtual Desktop · SteamVR · VRChat

  [中文](README.md) · [Quick start](#quick-start) · [How it works](#how-it-works)
</div>

---

EnterVRIME is a lightweight Windows companion for VRChat PCVR. Press `Enter` on your physical keyboard to open a head-mounted input panel, use your existing Windows Chinese IME with visible composition text and candidates, then press `Enter` again to send through VRChat OSC.

> This early preview targets **Virtual Desktop + SteamVR**. Direct VDXR support is not available yet.

## Highlights

- Keeps Microsoft Pinyin, Sogou, and other native Windows IME behavior.
- Shows both composing text and the system candidate window inside the headset.
- Uses a head-locked SteamVR overlay that stays below your main view.
- Uses a true triple-buffer ring: new pixels are written only to the fully hidden third layer, which is shown before the oldest layer is retired.
- Keeps the last top layer intact through transient failures and hands over stuck pools only after the replacement is visible.
- Sends locally through VRChat's official OSC Chatbox endpoint.
- No account, telemetry, or cloud service.

<div align="center">
  <img src="docs/assets/input-panel.png" alt="EnterVRIME input panel" width="900" />
</div>

## Quick start

1. Connect Quest 3 to Windows with Virtual Desktop.
2. Use SteamVR as the runtime and launch VRChat from SteamVR, not direct VDXR.
3. Enable OSC in VRChat's quick menu.
4. Download `EnterVRIME-Setup-*-win-x64.exe` from [Releases](../../releases) and open it once. No directory or Next-button choices are required: it installs without administrator rights, creates shortcuts, and launches EnterVRIME automatically. Startup-at-login stays off unless the user explicitly enables it in the control window.
5. Press `Enter` to type, `Shift + Enter` for a newline, and `Esc` to cancel.

> **OSC must be enabled inside VRChat before sending: Quick Menu → OSC → Enable.** Opening `OSC Debug` also enables it and makes the listener easy to verify.

> Preview binaries are not code-signed yet. If Windows SmartScreen reports an unknown publisher, first verify that the file came from this repository's Releases page, then choose “Run anyway.”

EnterVRIME can start before Virtual Desktop, SteamVR, or VRChat and will wait for them automatically. An opted-in Windows startup launch waits for an existing SteamVR process and never starts SteamVR itself. Opening the shortcut again restores the existing window instead of creating duplicate overlays. The public release intentionally offers one installer so ordinary users do not have to choose between builds.

VRChat currently limits chatbox input to 144 characters and 9 lines.

## How it works

EnterVRIME gives focus to a native Windows text field, captures the text field and the operating system's candidate popup, and submits those pixels to a head-relative OpenVR overlay. Confirmed text is sent to `/chatbox/input` over local UDP.

See [Architecture](docs/ARCHITECTURE.md) for details.

## Testing and diagnostics

Every run creates a local session log under `%LOCALAPPDATA%\EnterVRIME\logs`. The control window and tray menu can export a diagnostic ZIP containing environment details, component status, error codes, stack traces, and recent logs.

Chat text, IME composition, and candidate words are never logged. Exported archives also redact the Windows username and user-profile paths. If the app exits before an archive can be exported, attach the latest files from `%LOCALAPPDATA%\EnterVRIME\logs`; maintainers can provide a console-enabled Debug build privately when it is genuinely needed.

Error-code groups are `E1xx` startup/configuration, `E2xx` hotkey, `E3xx` SteamVR/overlay, `E4xx` capture, `E5xx` OSC, and `E9xx` unhandled exceptions or crashes.

The control window verifies that local VRChat is actually listening for OSC. If it shows `E505`, open `Action Menu → OSC → OSC Debug`, then retry when the status changes to “VRChat is listening.” Unsent text remains in the editor.

The unmodified `Enter` hotkey is registered only while `VRChat.exe` owns the foreground window. Switching to a browser, launcher, editor, or the desktop unregisters it, so EnterVRIME cannot swallow Enter or steal focus outside VRChat.

## Compatibility

| Environment | Status |
| --- | --- |
| Quest 3 + Virtual Desktop + SteamVR | Primary target |
| Windows 10 / 11 | Supported |
| VRChat PCVR + OSC | Supported |
| Direct VDXR | Not supported yet |
| Standalone Quest VRChat | Not supported |

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change.

If EnterVRIME helps you stay immersed, a **Star** makes the project easier for other VR users to discover.

## License

[MIT](LICENSE)
