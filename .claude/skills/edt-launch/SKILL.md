---
name: edt-launch
description: Use when launching 1C:EDT from code or command line, discovering installed EDT versions and their JDK, reading the 1C:EDT Start registry (products.json/projects.json), listing projects of an Eclipse workspace, building 1cedt.exe or 1cedtcli.exe command lines, or running EDT CLI commands (build, import, validate, project) and reading their output, exit codes and encoding
---

# Запуск 1C:EDT, реестр EDT Start и CLI `1cedtcli.exe`

Полные таблицы — ключи JSON EDT Start, команды и ключи CLI, коды завершения, формат
`.location` — в `reference.md` в этом каталоге. Всё снято с машины заказчика 10–20.09.2026
(EDT 2025.2.6+4 и 2026.1.2+2, EDT Start 0.10.0.448, Windows 11); протоколы —
`docs/research/t17-edt-experiments.md`, `docs/research/t19-edt-scheme-experiments.md`.
Легенда: **[Ф]** проверено на машине,
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
`C0 58 FB F3 23 BC 00 14 1A 51 F3 8C 7B BB 77 C6`. Перед записью Eclipse очищает файл
(`Workspace.clear`) — в здоровом файле один чанк; берите последний `BEGIN_CHUNK` — это
страховка от оборванной записи, как в `SafeChunkyInputStream.refineChunk` **[Д]**. Кириллица
в URI — без `%XX`, пробел — `%20`; UNC — `file:////srv/share` (четыре слэша, `URIUtil.toURI`)
**[Д]**. Разбор — `domain/edt_cli.py::parse_project_location`.

## Цвета редактора

**[Ф]** Цвета редактора кода EDT хранятся в workspace в двух файлах Java properties под
`<workspace>\.metadata\.plugins\org.eclipse.core.runtime\.settings\`: `com._1c.g5.v8.dt.bsl.ui.prefs`
(11 токенов подсветки, ключи `com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles.<Имя>.color=R,G,B`,
пробел в имени экранирован — `Builtin\ function`) и `org.eclipse.ui.editors.prefs` (11 цветов
редактора, у пяти — парный ключ `<ключ>.SystemDefault=false`). Полная таблица 22 ключей и
умолчаний EDT — `reference.md`, раздел 8.

**[Ф]** 20.09.2026, Э8.3: `.SystemDefault=false` у своих пяти ключей **обязателен** — без него
EDT берёт системный цвет (фон остался белым, хотя в файле лежало наше значение).

**[Ф]** Формат — Java properties: `ключ=значение`, `eclipse.preferences.version=1`, CRLF, ключи
по алфавиту; чужие ключи и мусорные строки не теряются. 20.09.2026, Э9: EDT переписала
`editors.prefs` при смене темы **байт в байт** с нашим файлом (тот же порядок, CRLF, чужой ключ
`onecstarter.canary` сохранён) — подтверждает и формат записи, и то, что EDT читает эти файлы
при старте.

**[Ф]** 20.09.2026, Э8.2: при выходе EDT переписывает только узлы настроек, изменённые в памяти
(dirty-флаги Eclipse Preferences) — правка файла при запущенной EDT **пережила** выход, если
EDT эти цвета не трогала. Смена цвета в самой EDT одновременно с внешней правкой не проверялась
**[Д]** — тогда EDT сбросит свои значения на диск и правка потеряется. Отсюда предусловие:
писать эти файлы только при закрытой EDT на этой рабочей области.

**[Ф]** Тема окна — третий файл, `org.eclipse.e4.ui.css.swt.theme.prefs`, ключ `themeid`:
`org.eclipse.e4.ui.css.theme.e4_dark` (тёмная) / `org.eclipse.e4.ui.css.theme.e4_default`
(светлая, Light). 20.09.2026, Э9: ключ читается при старте (окно уходит в тёмную/светлую тему
по нашему файлу) и переписывается самой EDT при смене темы в Preferences.

**[Ф]** 20.09.2026, Э9: `css/dark/edt-dark_preferencestyle.css` из `bsl.ui` (стилизует 9 из 11
токенов под тёмной темой) **не перекрывает** значения, уже лежащие в prefs, и ничего не пишет
в файл — предупреждение о тёмной теме не нужно.

**[Д]** Цвета EDT по умолчанию (светлая схема) не записаны в prefs: 11 токенов — байткод класса
`BslHighlightingConfiguration`, 11 цветов редактора — `plugin.xml` плагинов
`org.eclipse.ui.editors`, `org.eclipse.xtext.ui`, `org.eclipse.debug.ui` (Э10, 18.09.2026);
таблица значений — `reference.md`, раздел 8.

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

**[Ф]** Грамматика обёртки (usage из строк `1cedtcli.exe`, Э12 17.09.2026):
`1cedtcli -data <ws> [-timeout N] [-ini-file <ini>] [-vmargs <args…>] (-command <cmd> <args…> | -file <скрипт>)`.
**Ключа `-vm` у обёртки нет.** В режиме `-command` весь хвост строки уходит лаунчеру сырым —
поэтому `-vm "…"` после `-command` работает (строка выше). После `-file` обёртка пересобирает
хвост **без кавычек**: `-vm "C:\Program Files\…\bin"` доходит как `C:\Program` → код 1 за 1 с,
в `<ws>\.metadata\1cedtcli.log` «No Java virtual machine was found … C:\Program»; `-vm` до
`-file` — «Unrecognized option: -vm» от самой обёртки. JDK для скрипта — через `-ini-file`:

```text
"<установка>\1cedtcli.exe" -data "<workspace>" -ini-file "<наш.ini>" -vmargs <args продукта>
  -Djava.library.path= <args проекта> -file "<скрипт.cli>"
```

`<наш.ini>` — строки `1cedt.ini` установки без `-Dosgi.debug=.options` (так же делает
обёртка, копируя ini во `%TEMP%`) плюс `-vm` и `<jdk>\bin` перед `-vmargs`; относительные
`plugins/…` лаунчер разрешает от каталога exe. `-ini-file` и `-vmargs` — **до** `-file`;
список `-vmargs` не должен быть пустым (иначе `-file` ушёл бы в аргументы JVM). Свои
`-vmargs` (`-Declipse.ignoreApp=true … -Dfile.encoding=UTF-8`) обёртка ставит **после**
наших — наш `-Xmx` последний (снято с командной строки дочернего `1cedtc.exe`). Пробелы и
кириллица в путях ini и скрипта — приняты. Скрипт: по команде на строку, UTF-8 без BOM, LF;
два `import` — 56–65 с одним сеансом против ≈48 с на каждый порознь. При ошибке скрипт
**останавливается** на первой неудавшейся команде: код 204, текст ошибки в stdout
(UTF-8), стек — в `1cedtcli.log`; при успехе stdout пуст. `;` внутри `-command` — не
разделитель (код 204, хвост — одна команда). Раннер и зонды —
`docs/research/t20-edt-import.py`, протокол — `t20-edt-import-experiments.md`.

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
  отвергаем; `& | < > ^` cmd толкует **вне** кавычек (внутри `"…"` целы, `!` гасит `/v:off`)
  — в нашей строке без кавычек идут только `vm_args`, их с такими символами отвергаем;
  предел длины строки cmd — 8191 символ (**[Ф]** замеры ревью 13.09.2026). Исключение
  (**[Ф]** Э12): текст «Не найден вариант вызова команды … Варианты вызова» при коде 204
  печатается в **cp1251** и при `chcp 65001` — в UTF-8-журнале нечитаем.
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
| `import --project '<каталог>'` | Привязывает проект на месте, вывода «импортировано» нет; имя в реестре — из `.project` (`КонсольКода` для каталога `консоль копия`, Э12), а `validate` регистрирует по каталогу (`konsol`, Э6); **список Gogo не принят** — код 204, usage «`--project "строка"`» (Э12); повтор на привязанном — код 0, реестр не меняется, но полный сеанс (33 с); `--configuration-files '<xml>'` + `--project`/`--project-name` **[Д]** |
| `validate --project-list ['<p1>' '<p2>'] --file '<tsv>'` | Несколько путей — **список Gogo в квадратных скобках**; через пробел без скобок — код 204 «Не найден вариант вызова команды»; один путь в скобках тоже принят; непроверенный проект сначала импортируется; существующий `--file` — ошибка **[Д]** |

**[Ф]** TSV `validate`: UTF-8 без BOM, CRLF, **без заголовка**, 8 колонок через табуляцию:
метка времени ISO с зоной (`2026-09-13T09:29:28+0500`), серьёзность («Незначительная»),
категория («Стандарты кодирования»), проект, id проверки
(`com.e1c.v8codestyle.bsl:empty-except-statement`), объект, «строка N», сообщение.
Имя проекта в TSV и в реестре — по каталогу (`konsol`), не из `.project` (`КонсольКода`)
(так регистрирует `validate`; `import --project` — под именем из `.project`, Э12).

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
- Правка prefs при запущенной EDT, если пользователь одновременно меняет цвета в самой EDT.

## Где это в коде OneCStarter

`domain/edt.py` (модель, `build_edt_command`, `pick_jvm`, `split/join_vm_args`),
`domain/edt_cli.py` (`build_cli_command`, `wrap_console_utf8`, `quote_cli_arg`,
`cli_*_args`, `parse_project_location`), `domain/edt_scheme.py` (модель 22 ключей,
`render_prefs`, парсеры тем), `platform_1c/edt_discovery.py`, `platform_1c/edtstart_registry.py`,
`platform_1c/window_activate.py`, `services/edt.py`, `services/edt_cli.py`
(`workspace_entries`), `services/edt_scheme.py` (запись в рабочую область — задача 6 плана v3.2).
