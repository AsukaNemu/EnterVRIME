# Changelog

All notable changes to EnterVRIME are documented here.

## [0.1.5-alpha.1] - 2026-07-17

### Fixed

- Route every visible frame update through a true triple-buffer ring instead of rewriting the top layer in place.
- Keep all three opaque layers alive after warm-up and update only an occluded back layer before promoting its sort order.
- Preserve the last valid top layer indefinitely when SteamVR returns transient `OverlayError_RequestFailed` responses.
- Stop transient upload failures from destroying and rebuilding the complete OpenVR overlay session.
- Hand over a stuck three-layer pool to a fresh pool only after its replacement top layer is visible.
- Clear submitted frames between input sessions so a previous message cannot flash before the first fresh capture.

### Added

- A prominent in-app reminder that VRChat OSC must be enabled before sending.
- A SteamVR smoke-test fault injection that verifies recovery after more transient failures than the old reconnect threshold.

## [0.1.4-alpha.1] - 2026-07-17

### Fixed

- Replace destructive overlay rebuilds with a three-handle make-before-break pool.
- Present a replacement overlay for two SteamVR compositor frames before hiding the oldest visible generation.
- Assign explicit overlay sort orders so overlapping recovery layers do not fight for presentation.
- Keep the last valid layer visible while a standby handle receives the replacement texture.

### Changed

- Recycle hidden overlay handles instead of destroying and recreating them during frame recovery.
- Reconnect the entire OpenVR overlay session only after the standby pool repeatedly fails.
- Exercise two real standby promotions during the SteamVR overlay smoke test.

## [0.1.3-alpha.1] - 2026-07-17

### Fixed

- Register the no-modifier `Enter` hotkey only while `VRChat.exe` owns the foreground window.
- Fully release `Enter` to browsers, launchers, editors, and the desktop instead of swallowing unrelated key presses.
- Defensively reject a queued activation if VRChat loses focus before the event is handled.

### Changed

- Start with the hotkey unregistered and dynamically follow foreground-window changes.
- Direct `E505` recovery guidance to VRChat's `OSC Debug` screen, which also enables OSC.

## [0.1.2-alpha.1] - 2026-07-17

### Fixed

- Stop recreating the SteamVR overlay after a single transient `OverlayError_RequestFailed` response.
- Reduce raw texture updates to 10 FPS and skip unchanged frames to prevent rapid overlay flashing.
- Detect whether local VRChat is actually listening on the configured OSC input port.
- Keep unsent text open and show `E505` instead of reporting a false successful send when OSC is unavailable.

### Added

- Live OSC receiver status and listening-process diagnostics in the control window and diagnostic ZIP.
- A real SteamVR overlay smoke-test mode for packaged-build validation.

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
