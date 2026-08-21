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

[Registry]
; Значение автозапуска пишет само приложение (спека §3.1: истина — реестр).
; Установщик его не создаёт, но обязан убрать при удалении: иначе после
; деинсталляции Windows будет пытаться запустить стёртый exe.
;
; `ValueType: none` — не описка и не «тип не указан». **[Из документации
; Inno Setup]** «If none (the default setting) is specified, Setup will create
; the key but _not_ a value»: запись существует ровно ради `uninsdeletevalue`.
;
; **[Проверено, 21.08.2026, шаг А3 ручного прогона]** Прежняя редакция строки
; несла `ValueType: string` и полагалась на `dontcreatekey` — и СОЗДАВАЛА
; в Run пустое значение `OneCStarter` (0 символов). Флаг относится к КЛЮЧУ
; («Setup will not attempt to create the key or any value if the key did not
; already exist»), а ключ Run есть на любой машине всегда, поэтому значение
; создавалось беспрепятственно. Цена — не мусор в реестре, а ложь о состоянии:
; `is_enabled` считал автозапуск включённым, раздел «Настройки» показывал
; тумблер включённым, а Windows при входе выполнять было нечего.
; `dontcreatekey` оставлен: ключа Run может не быть в экзотическом окружении,
; и создавать его ради записи, которой мы не пишем, незачем.
;
; **[Из документации Inno Setup, не проверено]** Что `uninsdeletevalue` удалит
; значение, которое установщик НЕ создавал, — всё ещё утверждение документации:
; проверяется шагом А6 протокола docs/research/t04-7-settings-protocol.md.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "OneCStarter"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\OneCStarter.exe"; Description: "{cm:LaunchProgram,OneCStarter}"; Flags: nowait postinstall skipifsilent

; [UninstallDelete] намеренно НЕТ: %APPDATA%\OneCStarter (история, избранное,
; настройки) и ibases.v8i переживают удаление — «удаление ничего не теряет».
