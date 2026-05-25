; ═══════════════════════════════════════════════════════════════════════════════
;  United Mobile EPOS — Inno Setup 6 Script
;  Compile with Inno Setup 6 (https://jrsoftware.org/isinfo.php)
;
;  BEFORE COMPILING:
;    1. Run build.bat first to create dist\UnitedMobileEPOS\
;    2. Open this file in Inno Setup
;    3. Press Ctrl+F9 to compile
;    4. Output: installer\UnitedMobile_Setup_v1.0.exe
; ═══════════════════════════════════════════════════════════════════════════════

#define MyAppName      "United Mobile EPOS"
#define MyAppVersion   "1.0"
#define MyAppPublisher "United Mobile, Multan"
#define MyAppContact   "0323-9637000"
#define MyAppExeName   "UnitedMobileEPOS.exe"
#define MyAppInstDir   "C:\UnitedMobile"
#define MySourceDir    "dist\UnitedMobileEPOS"

; ── [Setup] ───────────────────────────────────────────────────────────────────
[Setup]

; App identity
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppContact={#MyAppContact}
AppComments=Electronic Point of Sale system for United Mobile, Multan

; Fixed install directory — no user selection required
DefaultDirName={#MyAppInstDir}
DisableDirPage=yes

; Start menu group
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Require admin (writing to C:\ needs elevation)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Output
OutputDir=installer
OutputBaseFilename=UnitedMobile_Setup_v1.0

; Compression — lzma gives the smallest installer file
Compression=lzma
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Appearance
WizardStyle=modern
WizardSizePercent=100
SetupIconFile=icon.ico

; Uninstaller
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
Uninstallable=yes
CreateUninstallRegKey=yes

; Automatically close the running app before updating
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no

; Minimum supported Windows version: Windows 10
MinVersion=10.0

; ── [Languages] ───────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── [Messages] ────────────────────────────────────────────────────────────────
[Messages]
; Customise the finish-page checkbox label
FinishedLabel=Setup has finished installing {#MyAppName} on your computer.%nThe application is ready to use.

; ── [Dirs] ────────────────────────────────────────────────────────────────────
[Dirs]
; Create the backups sub-folder — the app writes monthly auto-backups here
Name: "{app}\backups"

; ── [Files] ───────────────────────────────────────────────────────────────────
[Files]
; Copy entire PyInstaller output folder to C:\UnitedMobile\
;
; ignoreversion     — always overwrite (don't compare file versions)
; recursesubdirs    — include the _internal\ subfolder PyInstaller creates
; createallsubdirs  — recreate the subfolder structure at the destination
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── [Icons] ───────────────────────────────────────────────────────────────────
[Icons]
; Desktop shortcut (all users — requires admin which we already have)
Name: "{commondesktop}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    IconFilename: "{app}\icon.ico"; \
    Comment: "United Mobile EPOS - Point of Sale System"

; Start menu shortcut
Name: "{group}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    IconFilename: "{app}\icon.ico"; \
    Comment: "United Mobile EPOS - Point of Sale System"

; Uninstall shortcut in Start menu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; ── [Run] — post-install actions ──────────────────────────────────────────────
[Run]
; After setup completes, offer to launch the app immediately.
; postinstall  — shows a "Launch now?" checkbox on the final wizard page
; nowait       — setup doesn't wait for the app to close
; skipifsilent — skip this when running in silent/unattended mode
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName} now"; \
    Flags: nowait postinstall skipifsilent

; ── [UninstallRun] — cleanup before/after uninstall ──────────────────────────
[UninstallRun]
; Remove the Windows startup registry entry the app writes at first launch.
; Uses cmd /c so we can append 2>nul and avoid an error if key doesn't exist.
Filename: "cmd.exe"; \
    Parameters: "/c reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v UnitedMobileEPOS /f 2>nul"; \
    Flags: runhidden; \
    RunOnceId: "RemoveStartupKey"

; ── [Code] — Pascal script for smart uninstall ────────────────────────────────
[Code]

{ ── Ask whether to keep the database on uninstall ─────────────────────────── }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DbFile:      String;
  BackupsDir:  String;
  Msg:         String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DbFile := ExpandConstant('{app}\united_mobile.db');
    if FileExists(DbFile) then
    begin
      Msg := 'Do you want to keep the database file?' + #13#10 +
             '' + #13#10 +
             '    united_mobile.db' + #13#10 +
             '' + #13#10 +
             'This file contains all your sales records, purchases,' + #13#10 +
             'customer accounts and stock history.' + #13#10 +
             '' + #13#10 +
             'Click YES to keep it (recommended).' + #13#10 +
             'Click NO to delete it permanently.';

      if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDNO then
        DeleteFile(DbFile);
    end;

    { Also offer to remove the backups folder if it has content }
    BackupsDir := ExpandConstant('{app}\backups');
    if DirExists(BackupsDir) then
    begin
      Msg := 'Do you want to keep the backups folder?' + #13#10 +
             '' + #13#10 +
             '    ' + BackupsDir + #13#10 +
             '' + #13#10 +
             'Click YES to keep it, NO to delete it.';
      if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDNO then
        DelTree(BackupsDir, True, True, True);
    end;
  end;
end;

{ ── Prevent downgrade: warn if a newer version is already installed ─────────── }
function InitializeSetup(): Boolean;
var
  InstalledVersion: String;
begin
  Result := True;
  if RegQueryStringValue(HKLM,
       'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1',
       'DisplayVersion', InstalledVersion) then
  begin
    if InstalledVersion > '{#MyAppVersion}' then
    begin
      if MsgBox('A newer version (' + InstalledVersion + ') is already installed.' + #13#10 +
                'Do you want to continue installing v{#MyAppVersion}?',
                mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end;
  end;
end;
