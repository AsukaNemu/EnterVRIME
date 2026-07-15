# Changelog

All notable changes to EnterVRIME are documented here.

## [0.1.1-alpha.1] - 2026-07-16

### Added

- Privacy-safe per-session logs with stable error codes and full exception traces.
- One-click diagnostic ZIP export from the control window and system tray.
- Automatic user-path redaction and an explicit no-chat-text privacy manifest.
- Direct access to the local log folder and a copyable diagnostic summary.
- A console-enabled Debug package for startup and early-crash investigations.

### Changed

- Runtime status now surfaces the most recent error code.
- Release checksums for the normal and Debug packages are grouped in one file.

## [0.1.0-alpha.1] - 2026-07-16

### Added

- Global `Enter` hotkey to open the input panel.
- Native Windows IME composition and candidate-window capture.
- Head-relative SteamVR OpenVR overlay for Virtual Desktop users.
- UTF-8 VRChat OSC chatbox sending and typing indicator.
- `Shift + Enter` newline and `Esc` cancellation.
- 144-character validation, system tray controls, and Chinese diagnostics.
- Standalone Windows executable packaging.

### Known limitations

- Direct VDXR and standalone Quest VRChat are not supported.
- Overlay placement is currently configured through a local JSON file.
- Release binaries are not code-signed.
