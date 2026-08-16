; Per-user установщик OneCStarter (спека T-04.6, §6): без прав
; администратора, данные пользователя при удалении не трогаются.
; AppId зафиксирован навсегда — по нему Windows узнаёт обновление.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C1F4A2E-9D37-4B6A-A1C5-0E2D7F5B9C41}
AppName=OneCStarter
AppVersion={#AppVersion}
AppPublisher=OneCStarter project
DefaultDirName={localappdata}\Programs\OneCStarter
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\OneCStarter.exe
OutputBaseFilename=OneCStarter-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\OneCStarter\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\OneCStarter"; Filename: "{app}\OneCStarter.exe"

[Run]
Filename: "{app}\OneCStarter.exe"; Description: "{cm:LaunchProgram,OneCStarter}"; Flags: nowait postinstall skipifsilent

; [UninstallDelete] намеренно НЕТ: %APPDATA%\OneCStarter (история, избранное,
; настройки) и ibases.v8i переживают удаление — «удаление ничего не теряет».
