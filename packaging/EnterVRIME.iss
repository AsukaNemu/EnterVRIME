#ifndef AppVersion
  #define AppVersion "0.1.7-alpha.1"
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion "0.1.7.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\EnterVRIME"
#endif

[Setup]
AppId={{CCB41C04-784C-4D5B-AF5B-0DA3C3FF42C8}
AppName=EnterVRIME
AppVersion={#AppVersion}
AppVerName=EnterVRIME {#AppVersion}
AppPublisher=EnterVRIME contributors
AppPublisherURL=https://github.com/AsukaNemu/EnterVRIME
AppSupportURL=https://github.com/AsukaNemu/EnterVRIME/issues
AppUpdatesURL=https://github.com/AsukaNemu/EnterVRIME/releases
DefaultDirName={localappdata}\Programs\EnterVRIME
DefaultGroupName=EnterVRIME
OutputDir=..\dist
OutputBaseFilename=EnterVRIME-Setup-v{#AppVersion}-win-x64
SetupIconFile=..\assets\EnterVRIME.ico
UninstallDisplayIcon={app}\EnterVRIME.exe
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=yes
DisableStartupPrompt=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
CloseApplications=force
CloseApplicationsFilter=EnterVRIME.exe
RestartApplications=no
VersionInfoVersion={#AppNumericVersion}
VersionInfoCompany=EnterVRIME contributors
VersionInfoDescription=Quest 3 VRChat Chinese input overlay installer
VersionInfoProductName=EnterVRIME
VersionInfoProductVersion={#AppNumericVersion}
VersionInfoTextVersion={#AppVersion}
MinVersion=10.0.17763

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\EnterVRIME"; Filename: "{app}\EnterVRIME.exe"; WorkingDir: "{app}"
Name: "{group}\EnterVRIME"; Filename: "{app}\EnterVRIME.exe"; WorkingDir: "{app}"
Name: "{group}\卸载 EnterVRIME"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\EnterVRIME.exe"; WorkingDir: "{app}"; Flags: nowait

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM EnterVRIME.exe"; Flags: runhidden waituntilterminated; RunOnceId: "StopEnterVRIME"

[Code]
const
  StartupRunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{CCB41C04-784C-4D5B-AF5B-0DA3C3FF42C8}_is1';

var
  ResetLegacyStartup: Boolean;

procedure CurPageChanged(CurPageID: Integer);
begin
  { Inno keeps the Ready page when every earlier page is hidden. Advance it
    automatically so a normal double-click is still a true one-click install. }
  if CurPageID = wpReady then
    PostMessage(WizardForm.NextButton.Handle, $00F5, 0, 0); { BM_CLICK }
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  InstalledVersion: String;
begin
  ResetLegacyStartup := False;
  if RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', InstalledVersion) then
    ResetLegacyStartup := Pos('0.1.6', InstalledVersion) = 1;

  { EnterVRIME has no unsaved document state. Stop any old copy so an upgrade
    remains one-click and never pauses on Inno Setup's files-in-use page. }
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /IM EnterVRIME.exe',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { v0.1.6 enabled startup for every install. Reset that legacy default once;
    later versions preserve the user's explicit checkbox choice. }
  if (CurStep = ssInstall) and ResetLegacyStartup then
  begin
    RegDeleteValue(HKCU, StartupRunKey, 'EnterVRIME');
    Log('Removed v0.1.6 default startup entry; startup is now opt-in.');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKCU, StartupRunKey, 'EnterVRIME');
end;
