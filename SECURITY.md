# Security Policy

## Supported versions

Security fixes are provided for the latest published preview.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature when available. Do not open a public issue for vulnerabilities involving input capture, unintended network destinations, or arbitrary code execution.

Include the affected version, reproduction steps, impact, and any suggested mitigation. Please avoid including private chat text or personal IME data.

## Security model

- EnterVRIME does not require administrator privileges.
- It does not inject code into VRChat.
- It does not collect telemetry or send text to a hosted service.
- Session logs contain component state, error codes, and exception traces, but never chat text, IME composition, or candidate words.
- Diagnostic ZIP exports redact the Windows username and user-profile paths.
- OSC defaults to local loopback UDP at `127.0.0.1:9000`.
- Release binaries are currently unsigned; verify that downloads come from this repository's Releases page.
