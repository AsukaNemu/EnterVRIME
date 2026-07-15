# Contributing to EnterVRIME

Thanks for helping make Chinese text input less awkward in VR.

## Before opening an issue

- Confirm that VRChat is running through SteamVR, not direct VDXR.
- Confirm that OSC is enabled in VRChat.
- Search existing issues for the same headset, IME, or display-scaling problem.

For bugs, include Windows version, display scaling, Virtual Desktop runtime, SteamVR version, IME name, and clear reproduction steps. Never attach personal dictionaries or text you did not intend to share.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py
```

## Pull requests

- Keep changes focused and explain the user impact.
- Add tests for protocol and state-management changes.
- Verify the input panel at 100%, 125%, and 150% Windows scaling when changing layout or capture code.
- Do not add telemetry, advertising, or network services without prior discussion.

By contributing, you agree that your contribution is licensed under the MIT License.
