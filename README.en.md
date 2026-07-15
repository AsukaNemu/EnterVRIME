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
- Sends locally through VRChat's official OSC Chatbox endpoint.
- No account, telemetry, or cloud service.

<div align="center">
  <img src="docs/assets/input-panel.png" alt="EnterVRIME input panel" width="900" />
</div>

## Quick start

1. Connect Quest 3 to Windows with Virtual Desktop.
2. Use SteamVR as the runtime and launch VRChat from SteamVR, not direct VDXR.
3. Enable OSC in VRChat's quick menu.
4. Download `EnterVRIME-*-win-x64.zip` from [Releases](../../releases), extract it, and launch `EnterVRIME.exe`.
5. Press `Enter` to type, `Shift + Enter` for a newline, and `Esc` to cancel.

VRChat currently limits chatbox input to 144 characters and 9 lines.

## How it works

EnterVRIME gives focus to a native Windows text field, captures the text field and the operating system's candidate popup, and submits those pixels to a head-relative OpenVR overlay. Confirmed text is sent to `/chatbox/input` over local UDP.

See [Architecture](docs/ARCHITECTURE.md) for details.

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
