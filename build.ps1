$ErrorActionPreference = 'Stop'

$version = 'v0.1.6-alpha.1'
$appVersion = '0.1.6-alpha.1'
$numericVersion = '0.1.6.1'
$stageRoot = "dist\stage-$version"
$normalStage = Join-Path $stageRoot 'EnterVRIME'
$debugStage = Join-Path $stageRoot 'EnterVRIME-Debug'
$normalPackage = "dist\EnterVRIME-$version-win-x64.zip"
$debugPackage = "dist\EnterVRIME-Debug-$version-win-x64.zip"
$installerPackage = "dist\EnterVRIME-Setup-$version-win-x64.exe"
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
    '--distpath', $stageRoot,
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

Copy-Item -LiteralPath 'README.md' -Destination (Join-Path $normalStage 'README.md') -Force
Copy-Item -LiteralPath 'README.md' -Destination (Join-Path $debugStage 'README.md') -Force
Copy-Item -LiteralPath 'packaging\DEBUG-README.md' -Destination (Join-Path $debugStage 'DEBUG-README.md') -Force

Compress-Archive -Path (Join-Path $normalStage '*') -DestinationPath $normalPackage -Force
Compress-Archive -Path (Join-Path $debugStage '*') -DestinationPath $debugPackage -Force

$isccCandidates = @(
  (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
  (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
  throw 'Inno Setup 6 compiler not found. Install JRSoftware.InnoSetup with winget.'
}
$installerSource = (Resolve-Path $normalStage).Path
& $iscc "/DAppVersion=$appVersion" "/DAppNumericVersion=$numericVersion" "/DSourceDir=$installerSource" 'packaging\EnterVRIME.iss'
if ($LASTEXITCODE -ne 0) {
  throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$checksumLines = @($installerPackage) | ForEach-Object {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_).Hash.ToLowerInvariant()
  "$hash  $(Split-Path -Leaf $_)"
}
Set-Content -LiteralPath $checksumFile -Value $checksumLines -Encoding ascii

Write-Host "Normal build: $normalPackage"
Write-Host "Debug build:  $debugPackage"
Write-Host "Installer:    $installerPackage"
Write-Host "Checksums:    $checksumFile"
