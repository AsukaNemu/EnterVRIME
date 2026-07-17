# Architecture

EnterVRIME is intentionally small. It coordinates four existing systems instead of replacing them.

## Data flow

1. A thread-scoped Windows hotkey listens for `Enter` only while `VRChat.exe` owns the foreground window and the app is idle.
2. The hotkey is temporarily unregistered while a native Tk text widget owns keyboard focus.
3. Windows IME handles composition, candidate ranking, and personal dictionaries as usual.
4. The visible input region and candidate popup are captured at 10 FPS; unchanged frames are not resubmitted.
5. RGBA frames are submitted to a head-relative SteamVR overlay through OpenVR.
6. Confirmed UTF-8 text is encoded as an OSC message and sent to VRChat on UDP port `9000`.

## Main modules

| Module | Responsibility |
| --- | --- |
| `app.py` | UI lifecycle, focus, capture, and interaction state |
| `hotkey.py` | Windows `RegisterHotKey` message loop |
| `overlay.py` | OpenVR connection and raw overlay frames |
| `osc.py` | Minimal OSC encoder and VRChat chatbox client |
| `tray.py` | Windows notification-area controls |
| `diagnostics.py` | Session logs, exception hooks, privacy filtering, and ZIP export |
| `windows.py` | Foreground-window ownership checks for the VRChat-only hotkey gate |
| `single_instance.py` | Windows mutex and duplicate-launch window restoration |
| `startup.py` | Per-user startup-at-login setting through the Windows Run key |

## Design choices

### Native IME instead of an embedded pinyin engine

Users keep their existing IME, learned vocabulary, cloud settings, and muscle memory. Capturing the candidate window also avoids fragile attempts to read private TSF state from specific IME implementations.

### SteamVR overlay instead of injection

OpenVR overlays are compositor-supported and do not modify or inject code into VRChat. This reduces maintenance and keeps the app compatible with VRChat updates. The trade-off is that direct VDXR currently needs a separate implementation.

Raw texture submissions are rate-limited and use three preconfigured overlay handles as a true ring. After warm-up all three opaque layers remain visible with explicit sort orders. New pixels are uploaded only to the oldest layer underneath the current top layer; after a compositor grace frame, that back layer receives the highest sort order. No visible layer is hidden or rewritten during an ordinary update. A transient `RequestFailed` response preserves the current top layer and retries at a bounded rate. If all three handles remain stuck, a fresh pool is created in the same OpenVR session and the old pool is retired only after the replacement top layer is visible. Only repeated non-transient failures rebuild the complete OpenVR session.

### Local OSC instead of simulated keyboard input

VRChat officially supports UTF-8 chatbox text through `/chatbox/input`. OSC avoids focus-sensitive keystroke injection and keeps the integration explicit.

Before sending to a local target, EnterVRIME checks the Windows UDP owner table for a listener on the configured port. A missing listener produces `E505` and preserves the typed text instead of treating UDP transmission as delivery confirmation.

## Privacy boundary

No input text, IME composition, or candidate words are persisted. Local diagnostics retain component state, error codes, and stack traces; exported archives redact user-profile paths and usernames. No telemetry or remote API is used. The default network destination is loopback (`127.0.0.1:9000`).

## Distribution lifecycle

The recommended installer writes only to the current user's `%LOCALAPPDATA%\Programs\EnterVRIME`, so elevation is not required. It creates shortcuts and launches the app after installation, but startup-at-login is opt-in. If enabled, the Run-key command includes `--startup`; this mode checks for `vrserver.exe` before making any OpenVR call, which prevents a Windows login from launching SteamVR. During an upgrade the installer stops the old process before replacing files, then launches the new copy. A named per-session mutex prevents duplicate hotkey and overlay processes. The app may start before the VR runtime and keeps polling until Virtual Desktop and SteamVR become available.
