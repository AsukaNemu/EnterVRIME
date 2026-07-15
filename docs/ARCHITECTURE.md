# Architecture

EnterVRIME is intentionally small. It coordinates four existing systems instead of replacing them.

## Data flow

1. A thread-scoped Windows global hotkey listens for `Enter` while the app is idle.
2. The hotkey is temporarily unregistered while a native Tk text widget owns keyboard focus.
3. Windows IME handles composition, candidate ranking, and personal dictionaries as usual.
4. The visible input region and candidate popup are captured at up to 20 FPS.
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

## Design choices

### Native IME instead of an embedded pinyin engine

Users keep their existing IME, learned vocabulary, cloud settings, and muscle memory. Capturing the candidate window also avoids fragile attempts to read private TSF state from specific IME implementations.

### SteamVR overlay instead of injection

OpenVR overlays are compositor-supported and do not modify or inject code into VRChat. This reduces maintenance and keeps the app compatible with VRChat updates. The trade-off is that direct VDXR currently needs a separate implementation.

### Local OSC instead of simulated keyboard input

VRChat officially supports UTF-8 chatbox text through `/chatbox/input`. OSC avoids focus-sensitive keystroke injection and keeps the integration explicit.

## Privacy boundary

No input text, IME composition, or candidate words are persisted. Local diagnostics retain component state, error codes, and stack traces; exported archives redact user-profile paths and usernames. No telemetry or remote API is used. The default network destination is loopback (`127.0.0.1:9000`).
