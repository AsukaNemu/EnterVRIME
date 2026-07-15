$ErrorActionPreference = 'Stop'

& '.\.venv\Scripts\python.exe' -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name 'EnterVRIME' `
  --icon 'assets\EnterVRIME.ico' `
  --version-file 'packaging\version_info.txt' `
  --collect-binaries 'openvr' `
  --hidden-import 'pystray._win32' `
  'main.py'

$package = 'dist\EnterVRIME-v0.1.0-alpha.1-win-x64.zip'
$checksum = 'dist\EnterVRIME-v0.1.0-alpha.1-win-x64.sha256.txt'

Copy-Item -LiteralPath 'README.md' -Destination 'dist\EnterVRIME\README.md' -Force
Compress-Archive -Path 'dist\EnterVRIME\*' -DestinationPath $package -Force
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $package).Hash.ToLowerInvariant()
Set-Content -LiteralPath $checksum -Value "$hash  EnterVRIME-v0.1.0-alpha.1-win-x64.zip" -Encoding ascii

Write-Host "Build complete: $package"
