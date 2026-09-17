# T-20. Э12 — несколько `import` одним сеансом CLI EDT (v3.1.1)

Проведён 17.09.2026 с разрешения заказчика; три EDT заказчика оставались открытыми на
других рабочих областях (пересечения по `-data` нет, замеры времени завышены). Агент
запускал `docs/research/t20-edt-import.py <шаг>` — командная строка собирается и
заворачивается тем же `wrap_console_utf8`, что в программе, и уходит в `CreateProcess`
строкой, как у `spawn_logged`. Каждый исход правит метку в спеке v3.1.1 §0 и строку
скила `edt-launch`; опровергнутый факт — код и тест в том же коммите.

Установка — EDT 2026.1.2+2, JDK Axiom 17.0.16 (как в Э6). Проекты: `E:\tmp\edt-test\dev_tools`
(расширение, из Э6), `E:\tmp\edt-test\konsol`, копия `E:\tmp\edt-test\imp\консоль копия`
(кириллица и пробел). Рабочие области `ws-imp1..3` — пустые каталоги (EDT создаёт
`.metadata` сам, [Ф] Э1); `E:\edt\тест_2026` — из v3, в ней `dev_tools` уже привязан ([Ф] Э6).

## Зонды a–i: как обёртка `1cedtcli.exe` обращается с `-file`

Первый запуск шага 1 (`-data … -file "<скрипт>" -vm "C:\Program Files\…\bin" --launcher.appendVmargs
-vmargs …`, порядок ключей как у `-command` в Э6) — **код 1 за 1 с**, в `.metadata\1cedtcli.log`:
«No Java virtual machine was found after searching the following locations: `C:\Program`».
Тот же результат через PowerShell `Start-Process` и через код программы — виновата не
оболочка. Разбор по одному отличию за раз:

| Зонд | Командная строка (после `-data`) | Итог |
| --- | --- | --- |
| a | `-command "project" -vm "C:\Program Files\…"` (обратные слэши в `-data`) | код 0, 204 с — обратные слэши ни при чём |
| b | `-file "E:/tmp/…/s1.cli" -vm "C:\Program Files\…"` (прямые слэши в `-file`) | код 1, `C:\Program` — слэши ни при чём |
| d | `-vm "…" -file "…"` (`-vm` до `-file`) | код 1, обёртка печатает `Unrecognized option: -vm` (UTF-16, её собственное сообщение) |
| e | `-file "…" -vm C:\PROGRA~1\1C\1CE\COMPON~1\AXIOM-~1.16_\bin` (JDK без пробелов) | **код 0, 59 с, оба проекта в реестре** — `-file` работает, ломается только кавычка у `-vm` |
| h | `-ini-file "E:\tmp\…\edt test\cli test.ini" -vmargs … -file "E:\tmp\…\edt test\s1 copy.cli"` (пробелы в обоих путях; ini = копия `1cedt.ini` + `-vm`) | **код 0, 56 с, оба в реестре** |
| i | `-command "import --project 'a'; import --project 'b'"` | код 204 «Не найден вариант вызова команды» — `;` не разделитель, весь хвост — одна команда |

Строки самой обёртки (usage, снято из `1cedtcli.exe`) **[Ф]**:

```text
Usage: 1cedtcli -data <workspace> [OPTIONS]
  -timeout N                 terminate command (or script) if it takes more than N seconds to run
  -command <command> <args>  execute the given command with the given arguments and exit
  -file <script file>        execute commands from the given file (script) and exit
  -ini-file <ini file>       config file to use. If not specified, the 1cedt.ini file from the install directory is used
  -vmargs <JVM args>         specify one or more additional JVM arguments (like -Xmx, -D, etc)
Примеры: 1cedtcli -data ws -timeout 3600 -vmargs -Xmx8g -command import --configuration-files "/path/to/project1" --project-name "project1"
         1cedtcli -data ws -timeout 3600 -file "/path/to/script/file"
```

Ключа `-vm` у обёртки **нет**. Командная строка дочернего `1cedtc.exe` (снята
`Win32_Process` во время запуска) **[Ф]**:

- режим по умолчанию (зонд e): `1cedtc.exe --launcher.suppressErrors --launcher.appendVmargs
  --launcher.ini "%TEMP%\1cedt.ini" -nosplash -console -data "…" -file "…" -vm C:\PROGRA~1\…
  --launcher.appendVmargs -vmargs <наши> -vmargs -Declipse.ignoreApp=true -Dosgi.noShutdown=true
  -Dfile.encoding=UTF-8 -Dgosh.args="--quiet 'file:///%TEMP%/1cedtcli-startup.txt'" -Dedtcli.prompt=` —
  `-data` и `-file` обёртка кавычит сама, остальной хвост выдаёт **без кавычек** (отсюда
  `C:\Program`); `%TEMP%\1cedt.ini` — копия `1cedt.ini` установки **без `-Dosgi.debug=.options`**,
  относительные `plugins/…` оставлены (лаунчер разрешает их от каталога exe);
- режим `-ini-file` (зонд h): `… --launcher.ini "<наш ini>" -nosplash -console -data "…"
  -file "…" -vmargs -Declipse.ignoreApp=true … -Dedtcli.prompt= <наши -vmargs>` — наши
  аргументы JVM идут **после** аргументов обёртки, наш `-Xmx` последний.
- В режиме `-command` (Э6) хвост уходит лаунчеру сырым — потому `-vm "…"` там работал.

Вывод: несколько команд одним сеансом = `-data "<ws>" -ini-file "<ini>" -vmargs <args>
-file "<скрипт>"`, где ini — копия `1cedt.ini` установки без `-Dosgi.debug` плюс строки
`-vm` и `<каталог bin JDK>` перед `-vmargs`. Порядок ключей обёртки: `-ini-file` и `-vmargs`
**до** `-file`/`-command`.

## Шаг 1. Скрипт `-file` с двумя `import` (факты 6, 7-кодировка)

Команда: `-data "E:\tmp\edt-test\ws-imp1" -ini-file "E:\tmp\edt-test\imp\cli.ini" -vmargs -Xmx8192m
-DnativeFormBufferedLayoutRender=true -Djava.library.path= -file "E:\tmp\edt-test\imp\s1.cli"`.
Скрипт: две строки `import --project 'E:/tmp/edt-test/dev_tools'`,
`import --project 'E:/tmp/edt-test/imp/консоль копия'`, UTF-8 без BOM, LF.

| Поле | Результат |
| --- | --- |
| Код завершения | **0** |
| Длительность | 62 с (зонды e/h: 59/56/65 с) — один сеанс на два импорта, против ≈48 с на каждый по отдельности (Э6) |
| Реестр `.projects` после | `dev_tools`, `КонсольКода`, `.org.eclipse.egit.core.cmp` |
| `.location` «консоль копия» | `E:\tmp\edt-test\imp\консоль копия` (через `parse_project_location`) — кириллица и пробел прочитаны из скрипта верно |
| Вывод | stdout **пуст** (0 байт); лог CLI — `<ws>\.metadata\1cedtcli.log` (618 байт: SLF4J/NLS warnings), строки «импортировано» нет, как в Э6 |

Исход: `-file` **[Ф]** (с `-ini-file`); кодировка скрипта UTF-8 без BOM, LF **[Ф]**.

**Находка (правит факт 2 спеки):** проект зарегистрирован как `КонсольКода` — имя из
`.project`, **не** имя каталога `консоль копия`. В Э6 имя `konsol` «по каталогу» дал
`validate --project-list` (он импортирует непроверенные проекты сам), а не `import`.
`import --project` регистрирует под именем из `.project` **[Ф]**; `validate` — по каталогу
**[Ф, Э6]**.

## Шаг 2. Ошибка в середине скрипта (факт 7)

Команда: как шаг 1, `-data "…\ws-imp2"`, `-file "…\s2.cli"`. Скрипт: первая строка —
несуществующий каталог `E:/tmp/edt-test/imp/нет такого`, вторая — `konsol`.

| Поле | Результат |
| --- | --- |
| Код завершения | **204** («прервано исключением») |
| Реестр `.projects` после (есть ли `konsol`) | только `.org.eclipse.egit.core.cmp` — **вторая команда не выполнена** |
| Вывод | stdout 161 байт, UTF-8: «Не удалось прочитать файл описания проекта из расположения E:\tmp\edt-test\imp\нет такого\.project.»; стек `CliCommandException` → `ResourceException` → `FileNotFoundException` — в `1cedtcli.log` (3251 байт) |

Исход: при ошибке скрипт **останавливается** на первой неудавшейся команде, код 204,
сообщение об ошибке — в stdout **[Ф]**. Длительность 27 с.

## Шаг 3. Список Gogo у `import --project` (факт 5)

Команда: `-data "…\ws-imp3" -command "import --project ['E:/tmp/edt-test/dev_tools'
'E:/tmp/edt-test/imp/консоль копия']" -vm "…" --launcher.appendVmargs -vmargs …`.

| Поле | Результат |
| --- | --- |
| Код завершения | **204** |
| Реестр `.projects` после | только `.org.eclipse.egit.core.cmp` |
| Вывод | 513 байт **в cp1251** (не UTF-8): «Не найден вариант вызова команды, подходящий под переданные аргументы. Варианты вызова: 1. import --project "строка" 2. import --version "строка" --base-project-name "строка" --configuration-files "строка" --project "строка" --build <true/false> 3. … --project-name "строка" …» |

Исход: список у `import --project` **не принят** — факт 5 опровергнут **[Ф]**. Попутно:
текст «варианты вызова» при коде 204 печатается в **cp1251**, а не в UTF-8 консоли **[Ф]**
(журнал программы покажет его нечитаемым; в Э6 то же сообщение читали, видимо, из другой
кодировки — уточнение для скила, исправление журнала — вне вехи).

## Шаг 4. Повторный `import` привязанного проекта (факт 8)

Команда: `-data "E:\edt\тест_2026" -command "import --project 'E:/tmp/edt-test/dev_tools'" -vm "…" …`.

| Поле | Результат |
| --- | --- |
| Код завершения | **0** |
| Длительность | 33 с |
| Вывод | stdout пуст |
| `.location` `dev_tools` | не изменился (`E:\tmp\edt-test\dev_tools`), реестр прежний (`dev_tools`, `konsol`) |

Исход: повтор **безвреден, код 0**, но стоит полного сеанса — пометка «уже в рабочей
области» и недоступность элемента в диалоге обоснованы временем, не ошибкой **[Ф]**.

## Куда уходит

- Спека v3.1.1 §0 — факты 2 (имя по `.project`), 5 (список — нет), 6 (`-file` — да, через
  `-ini-file`), 7 (UTF-8; остановка на первой ошибке, код 204), 8 (повтор — код 0);
  §4.2 — командная строка с `-ini-file`; §4.3 и §4.4 — отклонены.
- Скил `edt-launch`: `SKILL.md` таблица команд (строка `-file`), usage обёртки, `-ini-file`,
  потеря кавычек после `-file`, `;` не разделитель, имя проекта при `import`, повтор
  `import`, cp1251 у сообщения 204; `reference.md` §3 «Режимы».
- План — Task 3 (`build_cli_script_command` с `ini`, `cli_ini_text`), Task 4 (`start_script`
  пишет и ini), приложение «Варианты по итогам Э12» удалено.
- Не закрыто **[?]**: два кандидата с одинаковым именем в `.project` в одной рабочей области
  (вторая команда, вероятно, упадёт и остановит скрипт); действует ли наш `-Xmx` в режиме
  `-ini-file` (в командной строке он последний, `jcmd` не снимался).
