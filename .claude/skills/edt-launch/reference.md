# Справочник: EDT Start, командные строки EDT и CLI, коды, форматы

Дополнение к `SKILL.md`. Легенда та же: **[Ф]** проверено на машине заказчика
(10–13.09.2026, EDT 2025.2.6+4 / 2026.1.2+2, EDT Start 0.10.0.448), **[Д]** документация,
исходники Eclipse или ресурсы плагинов CLI (`plugin.xml`, `messages.properties`
в `com.e1c.g5.v8.dt.cli.api_4.0.201` и `com.e1c.g5.v8.dt.cli.commands.builtin_1.0.600` —
тот же текст, что выводит `help`), **[?]** не проверено.

## 1. Файлы EDT Start — `%LOCALAPPDATA%\1C\1cedtstart\`

Все — `{"version": "1.1", "data": [ … ]}` (у `preferences.json` — плоский объект с `"version": "1.5"`), UTF-8.

### `products.json` — установленные EDT **[Ф]**

| Ключ | Пример | Примечание |
| --- | --- | --- |
| `id` | `de5146ed-…` | GUID продукта; на него ссылается `productId` проекта |
| `label` | `1C:Enterprise Development Tools` | |
| `location` | `C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedt.exe` | путь к exe, обратные слэши |
| `jvmPath` | `file:///C:/Program%20Files/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/` | URL на каталог `bin`, `%20`, завершающий `/` |
| `args` | `["-Xmx8192m", "-DnativeFormBufferedLayoutRender=true"]` | токены JVM продукта |
| `installedVersion.label` / `.name` | `2025.2.6+4` | равно версии в имени каталога |
| `installedVersion.starterUpdateRequired`, `.isClientUpdateRequired` | `false` | |
| `name` | `epp.package.1cedt` | |
| `description`, `icon`, `vendor`, `local` | … | `icon` — `…\products\1c-edt-product-offline-<версия>-x86_64\logo.png` |

### `projects.json` — проекты **[Ф]** (11 записей у заказчика)

| Ключ | Пример | Примечание |
| --- | --- | --- |
| `id` | `734bb861-…` | GUID |
| `label` | `conv3_extension` | имя в списке EDT Start |
| `location` | `e:\edt\2026-1-2\conv3_extension` | **workspace** (каталог с `.metadata`), не проект |
| `productId` | GUID из `products.json` | версия EDT |
| `projectTypeId` | `7f5f86e2-6077-4a4e-9582-aed75e5d9cba` | тип из `project-types.json` |
| `args` | `["-Xmx8192m", "-Duser.language=ru"]` | необязателен; язык — обычный токен здесь |

Ключа JVM у проекта **нет**; выбор Java VM в диалоге проекта на диск не пишется **[Ф]** Э4.

### `preferences.json` **[Ф]**

`projectsRoot` (`file:///e:/edt/2026-1-2/`), `productsRoot`
(`file:///C:/Users/<user>/AppData/Local/1C/1cedtstart/installations/`), `autoUpdate`,
`monitoringEnabled`, `bundlePoolEnabled`, `showWelcomePage`, `multiUserInstallEnabled`,
`hideNotificationsEnabled`, `windowHeight`, `windowPosition`, `colorTheme`, `jvmInfo` —
словарь по feature-версии Java: `"17": {"jvmPath": "file:///…/axiom-jdk-full-17.0.16+12-x86_64/bin/", "jvmVersion": {"featureVersion": 17}}`
(у заказчика ещё `"11"` — Liberica 11).

### Лог `logs\1cedtstart.log` **[Ф]**

Строки при запуске проекта: `JreInfo - JRE short version was resolved: 17.0.16`,
`ProjectPresentationManager - JVM path was resolved: <jdk>\bin`,
`Project with id: "<id>" will be launched on JVM: "<jdk>\bin"`; при правке реестра —
`AbstractRegistry - ProjectRegistry: added new ProjectInstallation{…}` / `updated …`;
при выходе — `ApplicationService - Shutting down...`. Каждые 15 с — шум
`Illegal timestamp … read from file` (разбор `.metadata` workspace).

## 2. Командные строки, снятые с процессов **[Ф]**

EDT из EDT Start (2026.1.2+2, проект с `-Duser.language=ru`):

```text
"C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64\1cedt.exe" -data e:\edt\2026-1-2\conv3_extension -vm "C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin" --launcher.appendVmargs -vmargs -Xmx8192m -DnativeFormBufferedLayoutRender=true -Djava.library.path= -Xmx8192m -Duser.language=ru
```

Дочерний `1cedtc.exe`, порождённый `1cedtcli.exe` (наши аргументы после `-vmargs` сохранены,
свои обёртка дописала после них):

```text
C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64\1cedtc.exe --launcher.suppressErrors --launcher.appendVmargs --launcher.ini "C:\Users\<user>\AppData\Local\Temp\1cedt.ini" -nosplash -console -data "E:\edt\тест_2026" -command validate --project-list ['E:/tmp/edt-test/dev_tools' 'E:/tmp/edt-test/konsol'] --file 'E:/tmp/edt-test/validate-two.tsv' -vm "C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin" --launcher.appendVmargs -vmargs -Xmx8192m "-DnativeFormBufferedLayoutRender=true" "-Djava.library.path=" -vmargs -Declipse.ignoreApp=true -Dosgi.noShutdown=true -Dfile.encoding=cp866 -Dgosh.args="--quiet 'file:///C:/Users/<user>/AppData/Local/Temp/1cedtcli-startup.txt'" -Dedtcli.prompt=
```

С `chcp 65001` в той же консоли до запуска — `-Dfile.encoding=UTF-8`. `%TEMP%\1cedtcli-startup.txt`:
`equinox:start com.e1c.g5.v8.dt.cli.api` → `gogo:until { gogo:type -q 1csupport:edtsh } { … sleep 1000 }` → `1csupport:edtsh`.

`1cedt.ini` (2025.2.6+4 и 2026.1.2+2, без `-vm`): `-startup plugins/org.eclipse.equinox.launcher_1.6.600…jar`,
`--launcher.library …`, `-showsplash com._1c.g5.v8.dt.product.application`, `-vmargs`,
`-Dosgi.requiredJavaVersion=17`, `--add-modules=ALL-SYSTEM`, набор `--add-opens=…`, `-Xmx4096m`.

## 3. Команды CLI

Режимы **[Д]**: `-command "<команда>"` (результат команды — код возврата), `-file <скрипт>`,
интерактивный; workspace — `-data`, для команд над проектами обязателен явный.

| Команда | Ключи | Достоверность |
| --- | --- | --- |
| `project` | без аргументов — список проектов (имя, расположение); `project <имя> --details` | **[Ф]** список; `--details` **[Д]** |
| `build` | `--yes` (без него «Really build? (y/n; default=n)») | **[Ф]** |
| `import` | `--project '<каталог>'` (существующий проект EDT) **[Ф]**; `--configuration-files '<каталог XML>'` + `--project '<каталог>'` **или** `--project-name '<имя>'`, `--base-project-name '<имя>'`, `--version <8.3.x>`, `--build` | **[Д]** ресурсы CLI |
| `validate` | `--project-list ['<путь>' …]` **[Ф]**; `--project-name-list [...]` **[Д]**; `--file '<tsv>'` — существующий файл ошибка **[Д]**; варианта «все проекты» нет **[Д]** | подсказка CLI при ошибке: `validate --file "строка" --project-list ["строка1" "строка2" "строка3"...]` |
| `help`, `help --status-codes`, `help <команда>` | | **[Ф]** |
| `export`, `delete`, `start`, `version`, `platform-versions`, `install-platform-support`; ключи `--delete-content`, `--features`, `--quiet` | | **[Д]** имена из ресурсов, не запускались |

Кавычки: «use single quotes … to avoid conflicts with 1C:EDT CLI interpreter rules» **[Д]**
(справка `find`); одинарная кавычка **внутри** значения — экранирование **[?]**; двойная
внутри разорвёт внешние `-command "…"`.

Таймаут: свойства JVM `edtcli.timeout`, `edtcli.timeoutHardExit` **[Д]** имена; единицы
и умолчания **[?]**.

## 4. Коды завершения — `help --status-codes` **[Ф]** (перевод CLI дословный)

| Код | Текст CLI |
| --- | --- |
| 0 | Нормальное завершение |
| 1 | Не удалось запустить 1C:EDT CLI. Проверьте наличие 1cedt.ini и наличие у процесса разрешений на создание временных файлов и создание (или запись в) рабочей области |
| 200 | Общая ошибка. Проверьте журналы рабочей области |
| 201 | Файл скрипта не найден (в режиме -file) |
| 202 | Другой процесс использует рабочую область |
| 203 | Выполнение команды было прервано (скорее всего, из-за таймаута) |
| 204 | Выполнение команды прекращено с исключением. Проверьте журналы рабочей области |
| 205 | Время выполнения команды превысило таймаут, но обычное прерывание не сработало, поэтому процесс был убит |
| 128 + сигнал | Процесс прерван сигналом (137 — SIGKILL) |
| код JVM | Например, 13 — 32-разрядная JVM |
| результат команды | Число, возвращённое командой в `-command` (или последней в `-file`) |
| `exit <n>` | Произвольный код через команду `exit` («help exit») |

Наблюдалось: 202 на открытом в EDT workspace («Не удалось запустить 1C:EDT CLI по причине
того, что рабочая область 'E:\edt\тест_2026' уже используется другим приложением»); 204 при
неверных аргументах (`--project-list 'a' 'b'` без скобок; путь с обратными слэшами —
`edtsh: Illegal char <:> at index 2: 'E:\tmp\x'`).

Имена из ресурсов плагина — `OK`, `LAUNCHER_ERROR`, `GENERAL_ERROR`, `FILE_NOT_FOUND`,
`WORKSPACE_IN_USE`, `INTERRUPTED`, `EXCEPTION`, `HARD_EXIT` **[Д]**; соответствие числам
(0, 1, 200, 201, 202, 203, 204, 205) — по смыслу текстов **[?]**.

## 5. TSV `validate` **[Ф]**

UTF-8 без BOM, CRLF, без строки заголовка, 8 колонок через `\t`:

```text
2026-09-13T09:29:28+0500	Незначительная	Стандарты кодирования	dev_tools	com.e1c.v8codestyle.bsl:empty-except-statement	ОбщийМодуль.dev_tools_ИнициализацияРедактораКлиент.Модуль	строка 88	"Попытка...Исключение" не содержит кода в исключении
```

## 6. Реестр проектов workspace и `.location` **[Ф]+[Д]**

`<workspace>\.metadata\.plugins\org.eclipse.core.resources\.projects\<имя>\` — подкаталог на
проект; внутри `.location` (если проект не в `<workspace>\<имя>`), `.markers`, каталоги плагинов.
Служебные записи начинаются с точки.

`.location` (`org.eclipse.core.internal.resources.LocalMetaArea.writePrivateDescription`,
`SafeChunkyOutputStream`):

```text
40 B1 8B 81 23 BC 00 14 1A 25 96 E7 A3 93 BE 1E   BEGIN_CHUNK
00 24                                              длина writeUTF (big-endian)
55 52 49 2F 2F 66 69 6C 65 3A 2F 45 3A 2F …        "URI//file:/E:/tmp/edt-test/dev_tools"
00 00 00 00                                        число динамических ссылок (далее — их имена writeUTF)
C0 58 FB F3 23 BC 00 14 1A 51 F3 8C 7B BB 77 C6   END_CHUNK
```

Пустая строка вместо `URI//…` — расположение по умолчанию. Перед записью файл очищается
(`Workspace.clear`), чанк один; читатель Eclipse при оборванной записи берёт последний
`BEGIN_CHUNK` (`SafeChunkyInputStream.refineChunk`) **[Д]**. Кириллица — сырой UTF-8,
пробел — `%20`; UNC — `file:////srv/share/x` (`URIUtil.toURI`) **[Д]**. Снятые примеры:
`URI//file:/E:/tmp/edt-test/dev_tools`, `URI//file:/E:/edt/тест_2026/.metadata/.plugins/org.eclipse.egit.core/.org.eclipse.egit.core.cmp`,
`file:/E:/work-spaces/projects/conv3_extension/src/КонсольКода`.

## 7. Замеры длительности **[Ф]** (workspace с одним расширением, JDK 17, SSD)

| Команда | Время |
| --- | --- |
| `help --status-codes` | 32 с |
| `validate` (1–2 проекта) | 39–56 с |
| `import --project` | 48 с |
| `build --yes` | 55 с |
| `project` | 144 с |
| `project` на занятом workspace (код 202) | 54 с |
