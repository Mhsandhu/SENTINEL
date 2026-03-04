; ═══════════════════════════════════════════════════════════════════
;  SENTINEL Installer — Inno Setup Script
;  Creates a single Setup_SENTINEL.exe that installs the app,
;  creates Start-menu & Desktop shortcuts, and registers uninstall.
;
;  Prerequisites:
;    1. Build with  build_desktop.bat  first  (creates dist\SENTINEL\)
;    2. Install Inno Setup 6+  from  https://jrsoftware.org/isinfo.php
;    3. Open this file in Inno Setup Compiler → Build → Compile
; ═══════════════════════════════════════════════════════════════════

#define MyAppName      "SENTINEL"
#define MyAppVersion   "2.2"
#define MyAppPublisher "SENTINEL Security"
#define MyAppExeName   "SENTINEL.exe"
#define MyAppURL       "https://github.com/Mhsandhu/SENTINEL"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Setup_SENTINEL_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Bundle everything from PyInstaller output
Source: "dist\SENTINEL\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SENTINEL"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\database"
Type: filesandordirs; Name: "{app}\vault_storage"
Type: filesandordirs; Name: "{app}\__pycache__"
