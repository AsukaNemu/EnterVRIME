$ErrorActionPreference = 'Stop'

$version = 'v0.1.3-alpha.1'
$normalPackage = "dist\EnterVRIME-$version-win-x64.zip"
$debugPackage = "dist\EnterVRIME-Debug-$version-win-x64.zip"
$checksumFile = "dist\SHA256SUMS-$version.txt"

function Build-EnterVRIME {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][ValidateSet('windowed', 'console')][string]$Mode
  )

  $arguments = @(
    '--noconfirm',
    '--clean',
    '--onedir',
    "--$Mode",
    '--name', $Name,
    '--icon', 'assets\EnterVRIME.ico',
    '--version-file', 'packaging\version_info.txt',
    '--collect-binaries', 'openvr',
    '--hidden-import', 'pystray._win32',
    'main.py'
  )
  & '.\.venv\Scripts\python.exe' -m PyInstaller @arguments
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed for $Name with exit code $LASTEXITCODE"
  }
}

Build-EnterVRIME -Name 'EnterVRIME' -Mode 'windowed'
Build-EnterVRIME -Name 'EnterVRIME-Debug' -Mode 'console'

Copy-Item -LiteralPath 'README.md' -Destination 'dist\EnterVRIME\README.md' -Force
Copy-Item -LiteralPath 'README.md' -Destination 'dist\EnterVRIME-Debug\README.md' -Force
Copy-Item -LiteralPath 'packaging\DEBUG-README.md' -Destination 'dist\EnterVRIME-Debug\DEBUG-README.md' -Force

Compress-Archive -Path 'dist\EnterVRIME\*' -DestinationPath $normalPackage -Force
Compress-Archive -Path 'dist\EnterVRIME-Debug\*' -DestinationPath $debugPackage -Force

$checksumLines = @($normalPackage, $debugPackage) | ForEach-Object {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_).Hash.ToLowerInvariant()
  "$hash  $(Split-Path -Leaf $_)"
}
Set-Content -LiteralPath $checksumFile -Value $checksumLines -Encoding ascii

Write-Host "Normal build: $normalPackage"
Write-Host "Debug build:  $debugPackage"
Write-Host "Checksums:    $checksumFile"
