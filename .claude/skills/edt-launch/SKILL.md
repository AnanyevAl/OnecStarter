---
name: edt-launch
description: Use when launching 1C:EDT from code or command line, discovering installed EDT versions and their JDK, reading the 1C:EDT Start registry (products.json/projects.json), listing projects of an Eclipse workspace, building 1cedt.exe or 1cedtcli.exe command lines, or running EDT CLI commands (build, import, validate, project) and reading their output, exit codes and encoding
---

# Запуск 1C:EDT, реестр EDT Start и CLI `1cedtcli.exe`

Полные таблицы — ключи JSON EDT Start, команды и ключи CLI, коды завершения, формат
`.location` — в `reference.md` в этом каталоге. Всё снято с машины заказчика 10–13.09.2026
(EDT 2025.2.6+4 и 2026.1.2+2, EDT Start 0.10.0.448, Windows 11); протоколы —
`docs/research/t17-edt-experiments.md`. Легенда: **[Ф]** проверено на машине,
**[Д]** из документации/исходников/ресурсов плагина, **[?]** не проверено, **[Р]** наше решение.

## Раскладка на диске

**[Ф]** Установки: `%ProgramFiles%\1C\1CE\components\1c-edt-<версия>-x86_64\` —
внутри `1cedt.exe` (окно), `1cedtc.exe` (консольный EDT), `1cedtcli.exe` (обёртка CLI),
`1cedt.ini`. Рядом `axiom-jdk-full-<версия>-x86_64\` (JDK, `bin\` внутри) и
`1c-edt-start-<версия>-x86_64\1cedtstart.exe`. Версия — из имени каталога
(`2025.2.6+4`), она же `installedVersion.label` в `products.json`.

**[Р]** Номер сборки (`+4`) и версия JDK (`17.0.16+12`) — значения с одной машины на одну
дату, **не хардкодить**: установку искать сканом `components\1c-edt-*-x86_64\1cedt.exe`
или по `products.json`, JDK — по `jvmPath` продукта или сканом `axiom-jdk-full-*`.

**[Ф]** Каталог версии может быть **пустышкой**: `1c-edt-2024.2.6+7-x86_64\` содержит
только `1cedt.ini`. Установка = каталог по маске **и** `1cedt.exe` в нём.

**[Ф]** Второй корень — `%LOCALAPPDATA%\1C\1cedtstart\installations\`
(`productsRoot` в `preferences.json`); раскладка внутри **[?]** — каталог пуст.

## Реестр 1C:EDT Start

**[Ф]** `%LOCALAPPDATA%\1C\1cedtstart\`: `products.json` (установленные EDT),
`projects.json` (проекты), `preferences.json`, `project-types.json`. Формат —
`{"version": "1.1", "data": [ … ]}`, UTF-8. Ключи — `reference.md`.

**[Ф]** `location` записи проекта — **Eclipse-workspace** (каталог с `.metadata`),
не каталог проекта. Сами EDT-проекты обычно лежат **вне** workspace (см. «Реестр проектов
workspace»).

**[Ф]** `jvmPath` продукта — URL `file:///C:/Program%20Files/…/axiom-jdk-full-17.0.16+12-x86_64/bin/`
(с `%20`, с завершающим `/`). `args` — список токенов JVM: у продукта
`["-Xmx8192m", "-DnativeFormBufferedLayoutRender=true"]`, у проекта `["-Xmx8192m"]`.

**[Ф]** Язык интерфейса хранится **в `args` проекта** обычным токеном
`-Duser.language=ru`; отдельного поля нет. EDT Start пишет `projects.json` **сразу** при
добавлении/изменении проекта (mtime секунда в секунду с `ProjectRegistry: added/updated`
в `logs\1cedtstart.log`).

**[Ф]** Выбор Java VM у **проекта** EDT Start 0.10.0.448 **на диск не пишет**: поле живёт
в памяти сеанса, после штатного выхода — снова JDK продукта; ни один файл в `1cedtstart\`,
`~\.eclipse\`, `.metadata` не меняется. Ключа переопределения JVM у записи проекта нет.

**[Ф]** Реестр и диск расходятся: каталог 2024.2.6+7 есть в `components`, в `products.json`
его нет. Обнаружение — по диску, реестр только обогащает.

**[Ф]** Крестик окна EDT Start **не завершает** процесс — он остаётся в трее;
выход — «Выход» в меню трея. Лог `logs\1cedtstart.log` при запуске проекта пишет
`JVM path was resolved: <jdk>\bin` и `Project with id: "<id>" will be launched on JVM: …`.

## Командная строка EDT

**[Ф]** Так запускает EDT Start (снято с процессов, подтверждено нашей строкой — Э1, Э5):

```text
"<components>\1c-edt-2025.2.6+4-x86_64\1cedt.exe" -data <workspace>
  -vm "<components>\axiom-jdk-full-17.0.16+12-x86_64\bin" --launcher.appendVmargs
  -vmargs <args продукта> -Djava.library.path= <args проекта> [-Duser.language=ru]
```

- `-vm` — **каталог `bin`** JDK, не `javaw.exe` (так передаёт EDT Start). `-vm` в `1cedt.ini`
  может указывать и на `javaw.exe` — тогда берём его каталог (`edt_discovery._ini_vm`).
  `--launcher.appendVmargs` — наши `-vmargs` **дописываются** к `-vmargs` из `1cedt.ini`
  (`--add-opens` и прочее остаются): **[Д]** семантика лаунчера Eclipse, запуск без флага
  не измерялся.
- **[Ф]** `1cedt.ini` установок 2025.2.6 и 2026.1.2 **без `-vm`**: голый `1cedt.exe -data`
  ненадёжен, JVM подаём сами. В ini — `-Dosgi.requiredJavaVersion=17` (порог для
  автоподбора JDK) и `-Xmx4096m`. У пустышки 2024.2.6 в ini `-vm C:\Program Files\Zulu\zulu-17\bin\javaw.exe`,
  и этот Zulu на диске есть — вне `components`.
- **[Ф]** При повторе `-Xmx` действует **последний**: продукт `-Xmx8192m`, проект `-Xmx6144m`
  → `jcmd VM.flags` даёт `MaxHeapSize=6442450944`. Аргументы проекта идут после аргументов
  продукта, язык — последним.
- **[Ф]** `-Djava.library.path=` (пустое) EDT Start передаёт всегда; назначение
  `-DnativeFormBufferedLayoutRender=true` **[?]** — передаём как есть.
- **[Р]** Цепочка выбора JDK в OneCStarter: `jvmPath` продукта → `-vm` из `1cedt.ini`
  (**[?]** не на чем проверить) → JDK из настроек → самый новый найденный JDK с версией
  ≥ `requiredJavaVersion`. Версия JDK — из файла `release` (`JAVA_VERSION`) без запуска
  `java -version` **[Ф]**.

**[Ф]** Окно принадлежит процессу `1cedt.exe` (JVM грузится в него, `javaw.exe` нет) —
статус «запущен» по `-data` в командной строке `1cedt.exe`, активация окна по PID.
Повторный «запуск» на уже открытом workspace: пока окна нет (splash), активировать
нечего — ничего не происходит, второй процесс не поднимаем; когда окно есть,
`SetForegroundWindow` поднимает его из-за других окон и из свёрнутого.

**[Ф]** `-data` на **пустой существующий** каталог: EDT создаёт `.metadata` сам.
Несуществующий каталог — **[?]**.

## Реестр проектов workspace

**[Ф]** Перечень проектов workspace — **не** подкаталоги workspace: у пяти из одиннадцати
workspace заказчика внутри нет ни одного каталога с `.project`, конфигурации лежат в
`E:\edt\…\src\cf`, `…\cfe_*` и привязаны на месте. Импорт (`import --project`) проект
**не копирует**.

**[Ф]+[Д]** Реестр: `<workspace>\.metadata\.plugins\org.eclipse.core.resources\.projects\<имя>\`.
Файл `.location` в нём — путь проекта вне workspace; нет файла — проект в
`<workspace>\<имя>`. Записи с точкой (`.org.eclipse.egit.core.cmp`) — служебные. Формат
`.location` (исходники Eclipse `LocalMetaArea`, байты совпали): чанк `SafeChunkyOutputStream` —
16 байт `40 B1 8B 81 23 BC 00 14 1A 25 96 E7 A3 93 BE 1E`, затем `DataOutputStream.writeUTF`
(2 байта длины big-endian + modified UTF-8) строки `URI//file:/E:/tmp/x` (пустая строка —
расположение по умолчанию), затем `int` числа ссылок и их имена, затем 16 байт `END_CHUNK`
`C0 58 FB F3 23 BC 00 14 1A 51 F3 8C 7B BB 77 C6`. При перезаписи чанки **дописываются** —
действителен последний. Кириллица в URI — без `%XX`, пробел — `%20`. Разбор —
`domain/edt_cli.py::parse_project_location`.

## CLI `1cedtcli.exe`

**[Ф]** `1cedtcli.exe` — **обёртка**: пишет `%TEMP%\1cedt.ini` и Gogo-скрипт
`%TEMP%\1cedtcli-startup.txt`, порождает дочерний `1cedtc.exe -console … -command <токены>
-vm … -vmargs <наши> -vmargs -Declipse.ignoreApp=true -Dosgi.noShutdown=true
-Dfile.encoding=<кодовая страница консоли> -Dgosh.args=…`. Ребёнок живёт до конца команды,
наследует Job родителя.

```text
"<установка>\1cedtcli.exe" -data "<workspace>" -command "<команда>" -vm "<jdk>\bin"
  --launcher.appendVmargs -vmargs <args продукта> -Djava.library.path= <args проекта>
```

- **[Ф]** `-command` — вся команда одним аргументом в двойных кавычках, **до** `-vmargs`.
  `-data` обязателен и при абсолютных путях в `--project-list`/`--project` (**[Д]** «для
  команд над проектами»; все снятые запуски — с `-data`, без него не запускалось).
  Значения внутри — в **одинарных** кавычках, **только с прямыми слэшами**:
  `'E:/tmp/a b/проект'` принят (пробел, кириллица); `'E:\tmp\x'` — Gogo кавычки не снимает,
  команда получает значение с кавычками и падает кодом 204
  `edtsh: Illegal char <:> at index 2: 'E:\tmp\x'`. `-data` снаружи `-command` —
  обратные слэши допустимы.
- **[Ф]** Кодировка вывода — **кодовая страница консоли**, не флаги JVM:
  `-Dsun.stdout.encoding=UTF-8`/`-Dstdout.encoding=UTF-8` бесполезны (обёртка дописывает
  свой `-Dfile.encoding` после них). Из GUI-процесса с `CREATE_NO_WINDOW` консоль скрытая, её
  страница — OEM **cp866**, и таким же выходит и вывод команды, и внутренний лог EDT.
  Лечит `cmd.exe /d /v:off /c "chcp 65001 >nul & "<1cedtcli.exe>" …"` — ребёнок получает
  `-Dfile.encoding=UTF-8`. Плата: cmd раскрывает `%ИМЯ%` даже в кавычках — значения с `%`
  отвергаем.
- **[Ф]** Workspace, открытый в EDT: код **202**, единственная строка вывода
  «Не удалось запустить 1C:EDT CLI по причине того, что рабочая область '…' уже используется
  другим приложением». Обратное (EDT на workspace, где идёт CLI) **[?]**.
- **[Ф]** Длительность на workspace с одним расширением: `project` 144 с, `build --yes` 55 с,
  `import` 48 с, `validate` 39–56 с, `help` 32 с — каждая команда поднимает headless-Eclipse.

**[Ф]** Четыре команды (остальные — `reference.md`):

| Команда | Что даёт |
| --- | --- |
| `project` | Имена проектов workspace по одному на строку (`dev_tools`), дальше — внутренний лог EDT (стеки `Error executing EValidator` у расширения без базы) |
| `build --yes` | Без `--yes` ждёт «Really build? (y/n)» **[Д]**; вывода нет вообще |
| `import --project '<каталог>'` | Привязывает проект на месте, вывода «импортировано» нет; `--configuration-files '<xml>'` + `--project`/`--project-name` **[Д]** |
| `validate --project-list ['<p1>' '<p2>'] --file '<tsv>'` | Несколько путей — **список Gogo в квадратных скобках**; через пробел без скобок — код 204 «Не найден вариант вызова команды»; один путь в скобках тоже принят; непроверенный проект сначала импортируется; существующий `--file` — ошибка **[Д]** |

**[Ф]** TSV `validate`: UTF-8 без BOM, CRLF, **без заголовка**, 8 колонок через табуляцию:
метка времени ISO с зоной (`2026-09-13T09:29:28+0500`), серьёзность («Незначительная»),
категория («Стандарты кодирования»), проект, id проверки
(`com.e1c.v8codestyle.bsl:empty-except-statement`), объект, «строка N», сообщение.
Имя проекта в TSV и в реестре — по каталогу (`konsol`), не из `.project` (`КонсольКода`).

**[Ф]** Коды (`help --status-codes`): 0 норма; 1 CLI не запустился (нет `1cedt.ini`/прав на
временные файлы и workspace); 200 общая ошибка; 201 файл скрипта (`-file`) не найден;
**202 workspace занят**; 203 прервано по таймауту; 204 прервано исключением
(в т. ч. неверные аргументы); 205 таймаут, процесс убит; `128 + сигнал`; код JVM (13 —
32-разрядная JVM); число, возвращённое командой; `exit <n>`. Имена из ресурсов плагина
(`WORKSPACE_IN_USE`, …) сопоставлены с числами по смыслу — **[?]**.

## Редакторы

**[Ф]** VS Code — `code.cmd` в PATH и `%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd`;
Antigravity — `%LOCALAPPDATA%\Programs\Antigravity IDE\bin\antigravity-ide.cmd`, в PATH **нет**.
`<cmd> "<каталог>"` открывает каталог с пробелом и кириллицей в обоих (по наблюдению; аргумент
уходит уже работающему экземпляру, в `Win32_Process` его не видно).

## Что не проверено

- `-data` на несуществующий каталог; поведение EDT при запуске на workspace, где идёт CLI.
- Шаг 2 цепочки JDK (`-vm` из `1cedt.ini`) — установки с `-vm` в ini нет.
- Экранирование одинарной кавычки внутри значения Gogo; свойства таймаута `edtcli.timeout`,
  `edtcli.timeoutHardExit` (единицы, умолчания).
- Раскладка `1cedtstart\installations\`; назначение `-DnativeFormBufferedLayoutRender`.
- Соответствие имён кодов (`GENERAL_ERROR`, …) числам; схемы URI в `.location`, кроме `file:`.

## Где это в коде OneCStarter

`domain/edt.py` (модель, `build_edt_command`, `pick_jvm`, `split/join_vm_args`),
`domain/edt_cli.py` (`build_cli_command`, `wrap_console_utf8`, `quote_cli_arg`,
`cli_*_args`, `parse_project_location`), `platform_1c/edt_discovery.py`,
`platform_1c/edtstart_registry.py`, `platform_1c/window_activate.py`,
`services/edt.py`, `services/edt_cli.py` (`workspace_entries`).
