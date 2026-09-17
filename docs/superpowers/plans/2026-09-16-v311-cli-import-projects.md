# v3.1.1 — импорт выбранных проектов через CLI EDT: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** диалог «Импортировать проекты (CLI EDT)» подставляет каталог проекта записи, показывает найденные в нём проекты EDT с флажками (уже привязанные — сняты и недоступны) и импортирует отмеченные одним сеансом CLI; версия `3.1.1` собрана и прошла smoke.

**Architecture:** сканер каталога — `services/edt_cli.py::scan_projects` (ФС через инъекцию, правило мастера Eclipse: каталог с `.project` — проект, внутрь не заходим; предел 3 уровня; каталоги на точку пропускаются); пометка привязанных — чистая `domain/edt_cli.py::mark_in_workspace` по реестру `workspace_entries`; команды — `cli_import_commands(form) -> list[str]`; несколько команд — скрипт `<logs_dir>/<id>.cli` в режиме `-file`, JDK — через свой ini `<logs_dir>/<id>.ini` и ключ `-ini-file` (`EdtCli.start_script`, `build_cli_script_command`, `cli_ini_text`) — по итогам Э12 (17.09.2026): у обёртки `1cedtcli.exe` нет ключа `-vm`, список Gogo у `import` не принят, очередь не нужна.

**Tech Stack:** Python 3.13, PySide6 6.11 (только `ui/`), pytest + pytest-qt (offscreen), ruff, mypy strict вне `ui.*`, PyInstaller + Inno Setup (`build/build.ps1`).

Спека — [2026-09-16-v311-cli-import-projects-design.md](../specs/2026-09-16-v311-cli-import-projects-design.md).
Ветка — `feat/2026-09-16-v311` от вершины v3.1 `09c1b72`. Скилы `edt-launch`, `platform-launch`
читать перед работой с CLI EDT (CLAUDE.md).

## Global Constraints

- **Запуск `1cedtcli.exe` — только на тестовых рабочих областях `E:\tmp\edt-test\ws-imp*` и
  `E:\edt\тест_2026`, только с явного разрешения заказчика** (спека §6; CLAUDE.md «Границы»).
  Рабочие области заказчика не трогать. Перед запуском EDT закрыт.
- **Факт без метки не попадает ни в скил, ни в `docs/`.** Опровергнутый факт правится в спеке,
  коде и тесте одним коммитом.
- **Qt только в `ui/`**: `domain`, `services` не импортируют PySide6. `scan_projects` — ФС через
  инъекцию (`listdir`, `is_dir`, `is_file`), тесты без диска.
- **Правило сканера** (спека §2): каталог с `.project` — кандидат, внутрь не заходим; подкаталоги с
  именем на точку пропускаются; корень — уровень 0, проверяются уровни 0…`SCAN_MAX_DEPTH` = 3
  включительно; `OSError` на подкаталоге — пропуск, на корне — пустой список; сортировка по
  `relative` без учёта регистра; `relative` — через `/`, корень-проект — имя его каталога.
- **Имя проекта — по каталогу, не из `.project`** (спека факт 2, [Ф] Э6).
- **Тексты дословно**: заголовок «Импортировать проекты (CLI EDT)»; переключатель «Проекты EDT в
  каталоге»; placeholder «каталог с проектами EDT, например клон репозитория»; суффикс
  « — уже в рабочей области»; строки состояния «Найдено N, уже в рабочей области M»,
  «Проектов не найдено: каталог с .project ищется до 3 уровней», «Каталог не существует»;
  ошибка «Не выбран ни один проект»; кнопки «Выбрать всё», «Снять всё»; пункт меню
  «Импортировать проекты…»; метка консоли «Импортировать (проектов: N)» при N ≥ 2 и
  «Импортировать» при одной; событие журнала `▶ <label>: скрипт <имя>, команд: N`;
  ошибка «Не удалось записать скрипт CLI: …».
- **Скрипт CLI**: `<logs_dir>/<project_id>.cli`, по строке на команду, UTF-8 без BOM, LF;
  ini — `<logs_dir>/<project_id>.ini` = строки `1cedt.ini` установки без `-Dosgi.debug…` и
  старого `-vm`, плюс `-vm`/`<bin JDK>` перед `-vmargs`; оба перезаписываются каждым запуском;
  `unavailable_reason` проверяется **до** записи (живая команда читает свой скрипт).
  Командная строка скрипта: `-data "<ws>" -ini-file "<ini>" -vmargs <args> -file "<скрипт>"` —
  `-ini-file` и `-vmargs` **до** `-file`, список `-vmargs` никогда не пуст (`-Djava.library.path=`).
  Одна команда — по-прежнему `-command` с `-vm` ([Ф] Э6).
- **Пути в командах CLI — прямые слэши, одинарные кавычки** (`quote_cli_arg`, [Ф] Э6); `%` и
  кавычки в путях — отказ до запуска.
- **Мутационная проверка** (CLAUDE.md): тест «привязанный не попадает в `form()`» — сломать
  `mark_in_workspace` (всегда `False`), увидеть `FAILED`, откатить, записать в отчёт.
- Полный прогон pytest — в файл (`uv run pytest -q > e:/tmp/<имя>.log 2>&1`), не в tail;
  субагенты запускают pytest только в обычном (не фоновом) режиме. Флейк pytest-qt
  `access violation` — повторить прогон.
- Версия — только `pyproject.toml` (`3.1.1`); smoke собранного экземпляра обязателен.
- Коммиты по-русски, без атрибуции.

---

### Task 1: Протокол Э12, тестовые данные и скрипт запуска

**Files:**
- Create: `docs/research/t20-edt-import-experiments.md`
- Create: `docs/research/t20-edt-import.ps1` → **заменён** при выполнении Task 2 на
  `docs/research/t20-edt-import.py` (PowerShell `Start-Process` терял кавычки; Python-раннер
  собирает строку тем же `wrap_console_utf8`, что программа)
- Create (вне репозитория): `E:\tmp\edt-test\ws-imp1`, `ws-imp2`, `ws-imp3` (пустые),
  `E:\tmp\edt-test\imp\консоль копия` (копия `E:\tmp\edt-test\konsol`), `E:\tmp\edt-test\imp\s1.cli`,
  `s2.cli`

**Interfaces:**
- Consumes: спека §0 факты 5–8, §6; журнал Э6 (командная строка `1cedtcli.exe`, JDK).
- Produces: протокол с полями результата; скрипт, печатающий код, длительность и реестр
  `.projects` после каждого шага.

- [ ] **Step 1: Тестовые данные**

```powershell
New-Item -ItemType Directory -Force E:\tmp\edt-test\ws-imp1, E:\tmp\edt-test\ws-imp2, E:\tmp\edt-test\ws-imp3, E:\tmp\edt-test\imp | Out-Null
Copy-Item -Recurse E:\tmp\edt-test\konsol "E:\tmp\edt-test\imp\консоль копия"
Test-Path "E:\tmp\edt-test\imp\консоль копия\.project"   # True
```

Скрипты CLI — Python, чтобы гарантировать UTF-8 без BOM и LF (как будет писать `start_script`):

```python
from pathlib import Path
imp = Path(r"E:\tmp\edt-test\imp")
(imp / "s1.cli").write_text(
    "import --project 'E:/tmp/edt-test/dev_tools'\n"
    "import --project 'E:/tmp/edt-test/imp/консоль копия'\n",
    encoding="utf-8", newline="\n",
)
(imp / "s2.cli").write_text(
    "import --project 'E:/tmp/edt-test/imp/нет такого'\n"
    "import --project 'E:/tmp/edt-test/konsol'\n",
    encoding="utf-8", newline="\n",
)
```

- [ ] **Step 2: Скрипт запуска `docs/research/t20-edt-import.ps1`**

```powershell
# T-20 / Э12: 1cedtcli.exe в режимах -file и -command на тестовых рабочих областях.
# Запуск: powershell -ExecutionPolicy Bypass -File docs/research/t20-edt-import.ps1 -Step 1
# Обёртка та же, что у OneCStarter (wrap_console_utf8): chcp 65001 в той же консоли до CLI.
param([Parameter(Mandatory = $true)][int]$Step)

$Cli = 'C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64\1cedtcli.exe'
$Jdk = 'C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin'
$Base = 'E:\tmp\edt-test'
$Imp = "$Base\imp"
$Tail = "-vm `"$Jdk`" --launcher.appendVmargs -vmargs -Xmx8192m -DnativeFormBufferedLayoutRender=true -Djava.library.path="

function Invoke-Cli([string]$Workspace, [string]$Mode, [string]$Out) {
    $line = "chcp 65001 >nul & `"$Cli`" -data `"$Workspace`" $Mode $Tail > `"$Out`" 2>&1"
    $started = Get-Date
    $proc = Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
        -ArgumentList "/d /v:off /c `"$line`"" -Wait -PassThru -NoNewWindow
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    "шаг: код $($proc.ExitCode), $seconds с, вывод: $Out"
    $registry = Join-Path $Workspace '.metadata\.plugins\org.eclipse.core.resources\.projects'
    if (Test-Path $registry) { 'реестр: ' + ((Get-ChildItem $registry -Name) -join ', ') }
    else { 'реестр: каталога нет' }
}

switch ($Step) {
    1 { Invoke-Cli "$Base\ws-imp1" "-file `"$Imp\s1.cli`"" "$Imp\s1.out" }
    2 { Invoke-Cli "$Base\ws-imp2" "-file `"$Imp\s2.cli`"" "$Imp\s2.out" }
    3 { Invoke-Cli "$Base\ws-imp3" "-command `"import --project ['E:/tmp/edt-test/dev_tools' 'E:/tmp/edt-test/imp/консоль копия']`"" "$Imp\s3.out" }
    4 { Invoke-Cli 'E:\edt\тест_2026' "-command `"import --project 'E:/tmp/edt-test/dev_tools'`"" "$Imp\s4.out" }
    default { throw "шаг 1..4" }
}
```

Записать файл с BOM: `Set-Content -Encoding UTF8` в PowerShell 5.1 ставит BOM; из Python —
`encoding="utf-8-sig"`.

- [ ] **Step 3: Протокол `docs/research/t20-edt-import-experiments.md`**

```markdown
# T-20. Э12 — несколько `import` одним сеансом CLI EDT (v3.1.1)

Выполняется 16.09.2026: заказчик закрывает EDT и даёт разрешение на запуск `1cedtcli.exe`
на тестовых рабочих областях; агент запускает `docs/research/t20-edt-import.ps1 -Step N`,
снимает код, длительность, вывод и реестр `.projects`. Каждый исход правит метку в спеке
v3.1.1 §0 и строку скила `edt-launch`; опровергнутый факт — код и тест в том же коммите.

Установка — EDT 2026.1.2+2, JDK Axiom 17.0.16 (как в Э6). Проекты: `E:\tmp\edt-test\dev_tools`
(расширение, из Э6), `E:\tmp\edt-test\konsol`, копия `E:\tmp\edt-test\imp\консоль копия`
(кириллица и пробел). Рабочие области `ws-imp1..3` — пустые каталоги (EDT создаёт
`.metadata` сам, [Ф] Э1); `E:\edt\тест_2026` — из v3, в ней `dev_tools` уже привязан ([Ф] Э6).

## Шаг 1. Скрипт `-file` с двумя `import` (факты 6, 7-кодировка)

Команда: `-data "E:\tmp\edt-test\ws-imp1" -file "E:\tmp\edt-test\imp\s1.cli"`.
Скрипт: две строки `import --project '…dev_tools'`, `import --project '…/консоль копия'`,
UTF-8 без BOM, LF.

| Поле | Результат |
| --- | --- |
| Код завершения | |
| Длительность | |
| Реестр `.projects` после | |
| `.location` «консоль копия» (путь через `parse_project_location`) | |
| Вывод: строки с `import`/`Exception`/`ошибк` | |

Исход: `-file` [Ф]/опровергнут; кодировка скрипта UTF-8 [Ф]/опровергнута.

## Шаг 2. Ошибка в середине скрипта (факт 7)

Команда: `-data "E:\tmp\edt-test\ws-imp2" -file "E:\tmp\edt-test\imp\s2.cli"`.
Скрипт: первая строка — несуществующий каталог, вторая — `konsol`.

| Поле | Результат |
| --- | --- |
| Код завершения | |
| Реестр `.projects` после (есть ли `konsol`) | |
| Вывод: что сказано про несуществующий путь | |

Исход: при ошибке скрипт продолжается / останавливается; код — какой.

## Шаг 3. Список Gogo у `import --project` (факт 5)

Команда: `-data "E:\tmp\edt-test\ws-imp3" -command "import --project ['…dev_tools' '…/консоль копия']"`.

| Поле | Результат |
| --- | --- |
| Код завершения | |
| Реестр `.projects` после | |
| Вывод | |

Исход: список принят / код 204 (или иной).

## Шаг 4. Повторный `import` привязанного проекта (факт 8)

Команда: `-data "E:\edt\тест_2026" -command "import --project 'E:/tmp/edt-test/dev_tools'"`.

| Поле | Результат |
| --- | --- |
| Код завершения | |
| Вывод | |
| `.location` `dev_tools` не изменился | |

Исход: повтор безвреден с кодом 0 / ошибка с кодом N.

## Куда уходит

- Спека v3.1.1 §0 — факты 5, 6, 7, 8; §4 — оставить одну ветку (§4.2 скрипт / §4.3 список /
  §4.4 очередь), остальные — в «отклонено» с итогом.
- Скил `edt-launch`: `SKILL.md` таблица команд (строка `-file`), `reference.md` §3 «Режимы»
  (`-file` — метка), строка про повтор `import`.
- План — Task 4/Task 5 или приложение «Варианты по итогам Э12».
```

- [ ] **Step 4: Коммит**

```bash
git add docs/research/t20-edt-import-experiments.md docs/research/t20-edt-import.ps1
git commit -m "docs: T-20 — протокол Э12 и скрипт запуска (несколько import одним сеансом CLI)"
```

---

### Task 2: Проведение Э12 и возврат исходов

**Выполняется координатором с заказчиком** (не субагентом): нужны закрытый EDT и разрешение
на запуск CLI. Четыре запуска ≈ 4 × 50 с.

**Files:**
- Modify: `docs/research/t20-edt-import-experiments.md` (результаты)
- Modify: `docs/superpowers/specs/2026-09-16-v311-cli-import-projects-design.md` (§0, §4)
- Modify: `.claude/skills/edt-launch/SKILL.md` (таблица «Четыре команды» → строка `-file`),
  `.claude/skills/edt-launch/reference.md` (§3 «Режимы», строка `import`)
- Modify: этот план (Task 4, Task 5, приложение)

- [ ] **Step 1: Разрешение и предусловие**

Спросить заказчика: EDT закрыт (все окна, включая «Выход» в трее); разрешение на четыре
запуска `1cedtcli.exe` на `ws-imp1..3` и `тест_2026`. Проверить процесс:
`Get-CimInstance Win32_Process -Filter "Name='1cedt.exe'" | Select-Object ProcessId, CommandLine`
— пусто.

- [ ] **Step 2: Шаги 1–4 по очереди**

Run: `powershell -ExecutionPolicy Bypass -File docs/research/t20-edt-import.ps1 -Step 1`
(затем 2, 3, 4). После каждого — вписать код, длительность, реестр, выдержки вывода
(`Select-String -Path E:\tmp\edt-test\imp\sN.out -Pattern 'import|Exception|ошиб' | Select-Object -First 10`)
в протокол дословно. `.location` — расшифровать:
`uv run python -c "from pathlib import Path; from onecstarter.domain.edt_cli import parse_project_location as p; print(p(Path(r'E:\tmp\edt-test\ws-imp1\.metadata\.plugins\org.eclipse.core.resources\.projects\консоль копия\.location').read_bytes()))"`.

- [ ] **Step 3: Метки в спеке и скиле**

Факты 5–8 §0 → **[Ф]** с датой и «Э12» либо переписаны по факту. В `SKILL.md` таблицу команд
дополнить строкой `-file '<скрипт>'` с исходом; в `reference.md` §3 «Режимы **[Д]**» разбить:
`-command` [Ф] Э6, `-file` — метка по Э12, интерактивный — [Д]. Повтор `import` — строка в
`SKILL.md` рядом с «Привязывает проект на месте».

- [ ] **Step 4: Выбор ветки плана**

| Итог Э12 | Ветка спеки | В плане |
| --- | --- | --- |
| Шаг 1 код 0, оба проекта в реестре, путь с кириллицей верен | §4.2 скрипт | Task 4 и Task 5 как написаны; приложение удалить |
| Шаг 1 провален, шаг 3 код 0 и оба в реестре | §4.3 список | Task 3 — вариант В1 приложения; из Task 4 убрать `start_script`, из Task 3 — `build_cli_script_command`; Task 5 — вариант В1 |
| Оба провалены | §4.4 очередь | Task 4 без `start_script`, Task 3 без `build_cli_script_command`; Task 5 — вариант В2 |

Если шаг 2 показал, что скрипт **останавливается** на первой ошибке, — в §4.2 спеки и в Task 6
это отразить текстом консоли не нужно (код сеанса виден), но записать в §0 факт 7 дословно.
Если шаг 4 дал ненулевой код — суффикс « — уже в рабочей области» и недоступность элемента
обоснованы фактом; если код 0 — тоже (48 с впустую), но записать «безвреден».

- [x] **Step 5: Коммит** — 17.09.2026. **Итог Э12:** шаг 1 код 0 (скрипт работает, но только с
  JDK через `-ini-file` — у обёртки нет `-vm`, после `-file` кавычки хвоста теряются); шаг 2 —
  стоп на первой ошибке, код 204; шаг 3 — список не принят, код 204; шаг 4 — повтор код 0.
  Ветка плана — §4.2 (скрипт + `-ini-file`); приложение с вариантами В1/В2 удалено.
  Попутно: `import` регистрирует проект под именем из `.project` (факт 2 спеки исправлен).

---

### Task 3: Домен — кандидаты, пометка привязанных, команды импорта, `-file`

**Files:**
- Modify: `src/onecstarter/domain/edt_cli.py` (импорты; `ImportForm`; `cli_import_args` →
  `cli_import_commands`; новые `ProjectCandidate`, `mark_in_workspace`,
  `build_cli_script_command`, `cli_ini_text`)
- Modify: `src/onecstarter/ui/edt/cli_import_dialog.py` (только вызовы: `form()`, `_refresh`)
- Modify: `src/onecstarter/ui/edt/view.py:675-678` (`cli_import` — `cli_import_commands(...)[0]`,
  временно до Task 5)
- Test: `tests/unit/test_edt_cli_domain.py`, `tests/ui/test_edt_cli_dialogs.py` (только
  `ImportForm`)

**Interfaces:**
- Consumes: `quote_cli_arg`, `WorkspaceEntry`, `workspace_key`, `LaunchCommand`.
- Produces:
  - `ProjectCandidate(path: str, relative: str, in_workspace: bool = False)` (frozen dataclass);
  - `mark_in_workspace(candidates: Sequence[ProjectCandidate], entries: Sequence[WorkspaceEntry]) -> list[ProjectCandidate]`;
  - `ImportForm(existing_project_dirs: tuple[str, ...] = (), configuration_files="", project_dir="", project_name="", base_project_name="", platform_version="", build_after=False)`;
  - `cli_import_commands(form: ImportForm) -> list[str]` (`ValueError`/`CliQuoteError` как раньше);
  - `build_cli_script_command(exe: Path, workspace: str, script: Path, ini: Path, installation_vm_args: str, project_vm_args: str) -> LaunchCommand`;
  - `cli_ini_text(installation_ini: str, jvm_dir: Path) -> str`.

- [ ] **Step 1: Тесты домена**

В `tests/unit/test_edt_cli_domain.py` импорт дополнить `ProjectCandidate`,
`build_cli_script_command`, `cli_import_commands`, `cli_ini_text`, `mark_in_workspace`;
`cli_import_args` убрать. Класс `TestImportArgs` заменить:

```python
class TestImportCommands:
    def test_one_command_per_existing_project_in_order(self) -> None:
        form = ImportForm(existing_project_dirs=(r"D:\repo\src\cfe_b", r"D:\repo\src\cf a"))
        assert cli_import_commands(form) == [
            "import --project 'D:/repo/src/cfe_b'",
            "import --project 'D:/repo/src/cf a'",
        ]

    def test_blank_entries_skipped(self) -> None:
        form = ImportForm(existing_project_dirs=("", "  D:\\a  "))
        assert cli_import_commands(form) == ["import --project 'D:/a'"]

    def test_xml_into_project_dir_minimal(self) -> None:
        form = ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\edt\ws\new")
        assert cli_import_commands(form) == [
            "import --configuration-files 'D:/xml' --project 'D:/edt/ws/new'"
        ]

    def test_xml_into_named_project_full(self) -> None:
        form = ImportForm(
            configuration_files=r"D:\xml",
            project_name="ext_a",
            base_project_name="base",
            platform_version="8.3.24",
            build_after=True,
        )
        assert cli_import_commands(form) == [
            "import --configuration-files 'D:/xml' --project-name 'ext_a' "
            "--base-project-name 'base' --version 8.3.24 --build"
        ]

    def test_both_variants_rejected(self) -> None:
        with pytest.raises(ValueError, match="один вариант"):
            cli_import_commands(
                ImportForm(existing_project_dirs=(r"D:\a",), configuration_files=r"D:\xml")
            )

    def test_xml_without_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="каталог или имя"):
            cli_import_commands(ImportForm(configuration_files=r"D:\xml"))

    def test_xml_with_both_targets_rejected(self) -> None:
        with pytest.raises(ValueError, match="каталог или имя"):
            cli_import_commands(
                ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\p", project_name="n")
            )

    def test_empty_form_rejected(self) -> None:
        with pytest.raises(ValueError, match="Укажите каталог"):
            cli_import_commands(ImportForm())

    def test_quote_in_project_path_rejected(self) -> None:
        with pytest.raises(CliQuoteError):
            cli_import_commands(ImportForm(existing_project_dirs=(r"D:\O'Reilly",)))

    def test_bad_platform_version_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"8\.3\.x"):
            cli_import_commands(
                ImportForm(configuration_files=r"D:\xml", project_name="n", platform_version="8;3")
            )


class TestMarkInWorkspace:
    ENTRIES = (
        WorkspaceEntry("cf", r"D:\repo\src\cf", True),
        WorkspaceEntry("junk", r"D:\ws\junk", False),  # без .project, но привязан
    )

    def test_matches_ignore_case_and_slashes(self) -> None:
        candidates = [
            ProjectCandidate("d:/REPO/src/CF", "src/CF"),
            ProjectCandidate(r"D:\repo\src\cfe_a", "src/cfe_a"),
            ProjectCandidate(r"D:\ws\junk", "junk"),
        ]
        marked = mark_in_workspace(candidates, self.ENTRIES)
        assert [c.in_workspace for c in marked] == [True, False, True]
        assert [c.relative for c in marked] == ["src/CF", "src/cfe_a", "junk"]  # порядок и поля целы

    def test_no_entries_marks_nothing(self) -> None:
        marked = mark_in_workspace([ProjectCandidate(r"D:\a", "a")], [])
        assert marked == [ProjectCandidate(r"D:\a", "a", False)]
```

В `TestBuildCliCommand` добавить:

```python
    def test_script_mode_ini_then_vmargs_then_file(self) -> None:
        # [Ф] Э12: у обёртки нет -vm — JDK в ini; -ini-file и -vmargs ДО -file
        script = Path(r"C:\Users\u u\AppData\Roaming\OneCStarter\logs\edt\id-1.cli")
        ini = script.with_suffix(".ini")
        command = build_cli_script_command(CLI, r"D:\ws", script, ini, "-Xmx8192m", "-Xmx4g")
        assert command.executable == CLI
        assert command.arguments == (
            f'-data "D:\\ws" -ini-file "{ini}" -vmargs -Xmx8192m -Djava.library.path= -Xmx4g '
            f'-file "{script}"'
        )
        assert "-vm " not in command.arguments and "-command" not in command.arguments

    def test_script_mode_empty_vm_args_keeps_library_path(self) -> None:
        # Список -vmargs не пуст никогда: иначе обёртка приняла бы -file за аргумент JVM
        command = build_cli_script_command(
            CLI, r"D:\ws", Path(r"D:\s.cli"), Path(r"D:\s.ini"), "", ""
        )
        assert '-vmargs -Djava.library.path= -file "D:\\s.cli"' in command.arguments


class TestCliIniText:
    INSTALL = (
        "-startup\nplugins/launcher.jar\n-showsplash\nx\n-vmargs\n"
        "-Dosgi.requiredJavaVersion=17\n-Dosgi.debug=.options\n-Xmx4096m\n"
    )

    def test_inserts_vm_before_vmargs_and_drops_osgi_debug(self) -> None:
        assert cli_ini_text(self.INSTALL, JDK) == (
            f"-startup\nplugins/launcher.jar\n-showsplash\nx\n-vm\n{JDK}\n-vmargs\n"
            "-Dosgi.requiredJavaVersion=17\n-Xmx4096m\n"
        )

    def test_replaces_existing_vm_pair(self) -> None:
        assert cli_ini_text("-vm\nC:/old/bin\n-vmargs\n-Xmx1g\n", JDK) == (
            f"-vm\n{JDK}\n-vmargs\n-Xmx1g\n"
        )

    def test_without_vmargs_appends_vm(self) -> None:
        assert cli_ini_text("-startup\na.jar\n", JDK) == f"-startup\na.jar\n-vm\n{JDK}\n"

    def test_crlf_input_gives_lf(self) -> None:
        assert cli_ini_text("-vmargs\r\n-Xmx1g\r\n", JDK) == f"-vm\n{JDK}\n-vmargs\n-Xmx1g\n"
```

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/unit/test_edt_cli_domain.py -q`
Expected: `ImportError` (`cli_import_commands`, `ProjectCandidate`, …).

- [ ] **Step 3: Реализация в `domain/edt_cli.py`**

Импорты: `from dataclasses import dataclass, replace`. Модульный docstring дополнить абзацем:

```python
"""
Несколько проектов — по одной команде `import --project` на каталог
(`cli_import_commands`); одним сеансом их выполняет режим `-file <скрипт>`. У обёртки
`1cedtcli.exe` нет ключа `-vm`, а после `-file` она пересобирает хвост без кавычек,
поэтому JDK для скрипта задаётся своим ini через `-ini-file` (`cli_ini_text`,
`build_cli_script_command`; [Ф] Э12, `docs/research/t20-edt-import-experiments.md`).
Кандидаты на импорт (`ProjectCandidate`) находит `services/edt_cli.py::scan_projects`,
привязанных помечает `mark_in_workspace` по реестру рабочей области.
"""
```

`ImportForm` и команды:

```python
@dataclass(frozen=True)
class ImportForm:
    existing_project_dirs: tuple[str, ...] = ()
    configuration_files: str = ""
    project_dir: str = ""
    project_name: str = ""
    base_project_name: str = ""
    platform_version: str = ""
    build_after: bool = False


def cli_import_commands(form: ImportForm) -> list[str]:
    """Команды `import`: по одной на каталог проекта; файлы XML — одна (спека v3.1.1 §4.1).

    Порядок — как в форме: успех `import` от порядка не зависит ([Ф] Э6 — расширение
    без базовой конфигурации импортировано с кодом 0).
    """  # noqa: RUF002
    existing = [path.strip() for path in form.existing_project_dirs if path.strip()]
    xml = form.configuration_files.strip()
    if existing and xml:
        msg = "Выберите один вариант импорта: существующий проект или файлы XML"
        raise ValueError(msg)
    if existing:
        return [f"import --project {quote_cli_arg(path)}" for path in existing]
    if not xml:
        msg = "Укажите каталог проекта или каталог файлов конфигурации"
        raise ValueError(msg)
    project_dir = form.project_dir.strip()
    project_name = form.project_name.strip()
    if bool(project_dir) == bool(project_name):
        msg = "Для файлов XML укажите каталог или имя нового проекта — одно из двух"
        raise ValueError(msg)
    parts = ["import", "--configuration-files", quote_cli_arg(xml)]
    if project_dir:
        parts += ["--project", quote_cli_arg(project_dir)]
    else:
        parts += ["--project-name", quote_cli_arg(project_name)]
    if form.base_project_name.strip():
        parts += ["--base-project-name", quote_cli_arg(form.base_project_name.strip())]
    if form.platform_version.strip():
        version = form.platform_version.strip()
        if not _PLATFORM_VERSION.match(version):
            raise ValueError("Версия платформы — вида 8.3.x")
        parts += ["--version", version]
    if form.build_after:
        parts.append("--build")
    return [" ".join(parts)]
```

Кандидаты (рядом с `WorkspaceEntry`):

```python
@dataclass(frozen=True)
class ProjectCandidate:
    """Каталог с `.project`, найденный `services/edt_cli.py::scan_projects` (спека v3.1.1 §2).

    `relative` — путь от корня сканирования через `/` (корень-проект — имя его каталога);
    имя из `.project` не читаем: CLI регистрирует проект по каталогу ([Ф] Э6).
    """  # noqa: RUF002

    path: str
    relative: str
    in_workspace: bool = False


def mark_in_workspace(
    candidates: Sequence[ProjectCandidate], entries: Sequence[WorkspaceEntry]
) -> list[ProjectCandidate]:
    """`in_workspace` по реестру рабочей области: совпадение `workspace_key` с путём
    любой записи — и без `.project` тоже, привязка есть."""  # noqa: RUF002
    keys = {workspace_key(entry.path) for entry in entries}
    return [
        replace(candidate, in_workspace=workspace_key(candidate.path) in keys)
        for candidate in candidates
    ]
```

Командная строка: `build_cli_command` не меняется; рядом — режим скрипта и ini:

```python
INSTALLATION_INI = "1cedt.ini"


def build_cli_script_command(
    exe: Path,
    workspace: str,
    script: Path,
    ini: Path,
    installation_vm_args: str,
    project_vm_args: str,
) -> LaunchCommand:
    """`-data "<ws>" -ini-file "<ini>" -vmargs <args> -file "<скрипт>"` ([Ф] Э12).

    У обёртки `1cedtcli.exe` нет ключа `-vm`: после `-file` хвост уходит лаунчеру без
    кавычек и `-vm "C:\\Program Files\\…"` превращается в `C:\\Program`. JDK — в ini
    (`cli_ini_text`). `-ini-file` и `-vmargs` — до `-file` (грамматика обёртки); список
    `-vmargs` не пуст никогда, иначе обёртка приняла бы `-file` за аргумент JVM.
    """  # noqa: RUF002
    parts = [
        f'-data "{workspace}"',
        f'-ini-file "{ini}"',
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
        f'-file "{script}"',
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))


def cli_ini_text(installation_ini: str, jvm_dir: Path) -> str:
    """Свой ini для `-ini-file` ([Ф] Э12): строки `1cedt.ini` установки без `-Dosgi.debug…`
    (так же делает обёртка, копируя ini во `%TEMP%`) и без прежней пары `-vm`/<путь>,
    плюс `-vm` и `<bin JDK>` перед `-vmargs`; нет `-vmargs` — в конец. LF."""  # noqa: RUF002
    lines: list[str] = []
    skip_path = False
    inserted = False
    for line in installation_ini.splitlines():
        if skip_path:
            skip_path = False
            continue
        if line.strip() == "-vm":
            skip_path = True
            continue
        if line.startswith("-Dosgi.debug"):
            continue
        if line.strip() == "-vmargs" and not inserted:
            lines += ["-vm", str(jvm_dir)]
            inserted = True
        lines.append(line)
    if not inserted:
        lines += ["-vm", str(jvm_dir)]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Вызывающий код — минимально, чтобы suite остался зелёным**

`ui/edt/cli_import_dialog.py`: импорт `cli_import_commands` вместо `cli_import_args`;
в `form()`:

```python
        if self._existing.isChecked():
            text = self._existing_dir.text().strip()
            return ImportForm(existing_project_dirs=(text,) if text else ())
```

в `_refresh()`: `cli_import_commands(self.form())`.

`ui/edt/view.py`: импорт `cli_import_commands`; в `cli_import`:

```python
        if self._run_dialog(dialog):
            self._start_cli(
                project_id, CLI_IMPORT.rstrip("…"), cli_import_commands(dialog.form())[0]
            )
```

`tests/ui/test_edt_cli_dialogs.py`: `ImportForm(existing_project_dir=r"D:\src\proj")` →
`ImportForm(existing_project_dirs=(r"D:\src\proj",))`;
`dialog.form().existing_project_dir == ""` → `dialog.form().existing_project_dirs == ()`.

- [ ] **Step 5: Прогон — зелёный**

Run: `uv run pytest tests/unit/test_edt_cli_domain.py tests/ui/test_edt_cli_dialogs.py tests/ui/test_edt_view.py -q && uv run ruff check . && uv run mypy`
Expected: PASS, `All checks passed!`, `Success`.

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/domain/edt_cli.py src/onecstarter/ui/edt/cli_import_dialog.py src/onecstarter/ui/edt/view.py tests/unit/test_edt_cli_domain.py tests/ui/test_edt_cli_dialogs.py
git commit -m "feat(domain): кандидаты импорта, пометка привязанных, cli_import_commands, режим -file"
```

---

### Task 4: Сервис — `scan_projects` и `EdtCli.start_script`

**Files:**
- Modify: `src/onecstarter/services/edt_cli.py` (`__all__`, импорты, `SCAN_MAX_DEPTH`,
  `scan_projects`, `CliBuilder`, `_by_command`, `_by_script`, `EdtCli.__init__` — `read_text`,
  `EdtCli.start` → общий `_start`, `start_script`, `script_path`, `ini_path`)
- Test: `tests/unit/test_edt_cli.py`

**Interfaces:**
- Consumes: `ProjectCandidate`, `build_cli_command`, `build_cli_script_command`, `cli_ini_text`,
  `INSTALLATION_INI` (Task 3).
- Produces:
  - `SCAN_MAX_DEPTH: int = 3`;
  - `scan_projects(root: str, *, max_depth: int = SCAN_MAX_DEPTH, listdir=os.listdir, is_dir=os.path.isdir, is_file=os.path.isfile) -> list[ProjectCandidate]`;
  - `EdtCli(…, read_text: Callable[[Path], str] = _read_text)` — чтение `1cedt.ini` установки;
  - `EdtCli.start_script(project_id: str, label: str, commands: Sequence[str]) -> CliRun`;
  - `EdtCli.script_path(project_id: str) -> Path` — `<logs_dir>/<project_id>.cli`;
  - `EdtCli.ini_path(project_id: str) -> Path` — `<logs_dir>/<project_id>.ini`.

- [ ] **Step 1: Тесты сканера**

В `tests/unit/test_edt_cli.py` импорт: `from onecstarter.services.edt_cli import CliResult, EdtCli, scan_projects, workspace_entries`; `from onecstarter.domain.edt_cli import ProjectCandidate, WorkspaceEntry, location_blob`; `import os`. `Harness` — см. конец Step 2 (`read_text`).

```python
class FakeTree:
    """Дерево каталогов без диска: `dirs` — каталог → имена внутри, `files` — полные пути
    файлов, `broken` — каталоги, на которых listdir даёт OSError (нет прав)."""

    def __init__(
        self, dirs: dict[str, list[str]], files: set[str], broken: set[str] = frozenset()
    ) -> None:
        self.dirs = dirs
        self.files = files
        self.broken = broken

    def listdir(self, path: str) -> list[str]:
        # Неизвестный путь — как несуществующий каталог, а не KeyError: сканер зовёт
        # listdir для корня без проверки is_dir и глотает только OSError
        if path in self.broken or path not in self.dirs:
            raise FileNotFoundError(path)
        return self.dirs[path]

    def is_dir(self, path: str) -> bool:
        return path in self.dirs

    def is_file(self, path: str) -> bool:
        return path in self.files

    def scan(self, root: str, **kwargs: object) -> list[ProjectCandidate]:
        return scan_projects(
            root, listdir=self.listdir, is_dir=self.is_dir, is_file=self.is_file, **kwargs  # type: ignore[arg-type]
        )


def _p(*parts: str) -> str:
    return os.path.join(*parts)


ROOT = r"D:\repo"


class TestScanProjects:
    def test_root_itself_is_a_project(self) -> None:
        tree = FakeTree({ROOT: ["src"], _p(ROOT, "src"): []}, {_p(ROOT, ".project")})
        assert tree.scan(ROOT) == [ProjectCandidate(ROOT, "repo")]

    def test_clone_layout_src_name_sorted_case_insensitive(self) -> None:
        src = _p(ROOT, "src")
        tree = FakeTree(
            {
                ROOT: [".git", "src", "README.md"],
                _p(ROOT, ".git"): ["hooks"],
                src: ["cfe_b", "CF", "docs"],
                _p(src, "cfe_b"): [], _p(src, "CF"): [], _p(src, "docs"): [],
            },
            {_p(src, "cfe_b", ".project"), _p(src, "CF", ".project"), _p(ROOT, ".git", ".project")},
        )
        assert tree.scan(ROOT) == [
            ProjectCandidate(_p(src, "CF"), "src/CF"),
            ProjectCandidate(_p(src, "cfe_b"), "src/cfe_b"),
        ]

    def test_project_dir_is_not_descended(self) -> None:
        cf = _p(ROOT, "cf")
        tree = FakeTree(
            {ROOT: ["cf"], cf: ["nested"], _p(cf, "nested"): []},
            {_p(cf, ".project"), _p(cf, "nested", ".project")},
        )
        assert tree.scan(ROOT) == [ProjectCandidate(cf, "cf")]

    def test_depth_limit_inclusive(self) -> None:
        a, b, c, d = _p(ROOT, "a"), _p(ROOT, "a", "b"), _p(ROOT, "a", "b", "c"), _p(ROOT, "a", "b", "c", "d")
        tree = FakeTree(
            {ROOT: ["a"], a: ["b"], b: ["c"], c: ["d"], d: []},
            {_p(c, ".project"), _p(d, ".project")},
        )
        assert tree.scan(ROOT) == [ProjectCandidate(c, "a/b/c")]  # уровень 3 найден
        deep = FakeTree({ROOT: ["a"], a: ["b"], b: ["c"], c: ["d"], d: []}, {_p(d, ".project")})
        assert deep.scan(ROOT) == []  # уровень 4 не проверяется
        assert deep.scan(ROOT, max_depth=4) == [ProjectCandidate(d, "a/b/c/d")]

    def test_unreadable_subdir_skipped_unreadable_root_empty(self) -> None:
        ok, bad = _p(ROOT, "ok"), _p(ROOT, "bad")
        tree = FakeTree(
            {ROOT: ["bad", "ok"], ok: [], bad: []}, {_p(ok, ".project")}, broken={bad}
        )
        assert tree.scan(ROOT) == [ProjectCandidate(ok, "ok")]
        assert FakeTree({}, set(), broken={ROOT}).scan(ROOT) == []
        assert FakeTree({}, set()).scan(r"D:\nowhere") == []  # несуществующий корень
```

- [ ] **Step 2: Тесты `start_script`**

В класс `TestStart` (или новый `TestStartScript`) в `tests/unit/test_edt_cli.py`:

```python
class TestStartScript:
    COMMANDS = ["import --project 'D:/repo/src/cf'", "import --project 'D:/repo/src/cfe a'"]

    def test_writes_script_and_ini_and_launches_in_file_mode(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project(vm_args="-Xmx4g")
        run = h.cli.start_script(p.id, "Импортировать (проектов: 2)", self.COMMANDS)
        script, ini = h.cli.script_path(p.id), h.cli.ini_path(p.id)
        assert script == tmp_path / "logs" / "edt" / f"{p.id}.cli"
        assert ini == tmp_path / "logs" / "edt" / f"{p.id}.ini"
        raw = script.read_bytes()
        assert raw == b"import --project 'D:/repo/src/cf'\nimport --project 'D:/repo/src/cfe a'\n"
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
        # ini: 1cedt.ini установки без -Dosgi.debug, с -vm перед -vmargs ([Ф] Э12)
        assert h.ini_reads == [EXE_DIR / "1cedt.ini"]
        assert ini.read_bytes() == (
            b"-startup\nplugins/launcher.jar\n-vm\n" + str(JDK).encode() + b"\n-vmargs\n-Xmx4096m\n"
        )
        [(command, log_path)] = h.spawned
        assert f'-ini-file "{ini}" -vmargs -Xmx8192m -Djava.library.path= -Xmx4g -file "{script}"' in command.arguments
        assert "-command" not in command.arguments and "-vm " not in command.arguments
        text = log_path.read_text(encoding="utf-8")
        header = f"▶ Импортировать (проектов: 2): скрипт {p.id}.cli, команд: 2"
        assert header in text
        assert text.index(header) < text.index(self.COMMANDS[0]) < text.index(self.COMMANDS[1])
        assert text.index(self.COMMANDS[1]) < text.index("вывод cli")
        assert run.label == "Импортировать (проектов: 2)"
        assert h.workspace.status(p.id).cli_busy is True

    def test_busy_refused_before_script_overwrite(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start_script(p.id, "Импортировать (проектов: 2)", self.COMMANDS)
        before = h.cli.script_path(p.id).read_bytes()
        with pytest.raises(EdtError, match="уже выполняется"):
            h.cli.start_script(p.id, "Импортировать (проектов: 2)", ["import --project 'D:/x'"])
        assert h.cli.script_path(p.id).read_bytes() == before  # живая команда читает свой скрипт
        assert len(h.spawned) == 1

    def test_script_write_failure_is_edt_error(self, tmp_path: Path) -> None:
        logs = tmp_path / "logs"
        logs.write_text("файл на месте каталога", encoding="utf-8")
        h = Harness(tmp_path, logs_dir=logs)
        p = h.project()
        with pytest.raises(EdtError, match="Не удалось записать скрипт CLI"):
            h.cli.start_script(p.id, "Импортировать (проектов: 2)", self.COMMANDS)
        assert h.spawned == []
        assert h.workspace.status(p.id).cli_busy is False

    def test_unreadable_installation_ini_is_edt_error(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        h.installation_ini = None  # read_text бросит OSError
        p = h.project()
        with pytest.raises(EdtError, match="1cedt.ini"):
            h.cli.start_script(p.id, "Импортировать (проектов: 2)", self.COMMANDS)
        assert h.spawned == []
        assert not h.cli.script_path(p.id).exists()
        assert h.workspace.status(p.id).cli_busy is False
```

`Harness` в том же файле: поле `self.installation_ini: str | None = INSTALL_INI`, список
`self.ini_reads: list[Path] = []`, метод

```python
    def _read_text(self, path: Path) -> str:
        self.ini_reads.append(path)
        if self.installation_ini is None:
            raise FileNotFoundError(path)
        return self.installation_ini
```

и передача `read_text=self._read_text` в `EdtCli(...)` (метод определить до конструктора
`EdtCli` или ссылаться на `self._read_text` — метод класса доступен в `__init__`).
Константа модуля:

```python
INSTALL_INI = "-startup\nplugins/launcher.jar\n-vmargs\n-Dosgi.debug=.options\n-Xmx4096m\n"
```

- [ ] **Step 3: Прогон — падает**

Run: `uv run pytest tests/unit/test_edt_cli.py -q`
Expected: `ImportError: cannot import name 'scan_projects'`.

- [ ] **Step 4: Реализация в `services/edt_cli.py`**

`__all__ = ["SCAN_MAX_DEPTH", "CliResult", "CliRun", "EdtCli", "scan_projects", "workspace_entries"]`.
Импорты: `from onecstarter.domain.edt_cli import (INSTALLATION_INI, PROJECTS_REGISTRY, CliQuoteError, ProjectCandidate, WorkspaceEntry, build_cli_command, build_cli_script_command, cli_ini_text, parse_project_location, wrap_console_utf8)`; `from collections.abc import Callable, Sequence`; `from onecstarter.domain.edt import CLI_EXE, EdtInstallation, EdtProject, effective_jvm`.

Сканер — после `workspace_entries`:

```python
SCAN_MAX_DEPTH = 3  # корень — уровень 0; клон репозитория: `src/<имя>` — уровень 2


def scan_projects(
    root: str,
    *,
    max_depth: int = SCAN_MAX_DEPTH,
    listdir: Callable[[str], list[str]] = os.listdir,
    is_dir: Callable[[str], bool] = os.path.isdir,
    is_file: Callable[[str], bool] = os.path.isfile,
) -> list[ProjectCandidate]:
    """Проекты EDT под `root` — правило мастера импорта Eclipse (спека v3.1.1 §2, факт 9):
    каталог с `.project` — проект, внутрь не заходим; иначе — в подкаталоги.

    Наши ограничения: каталоги на точку (`.git`, `.metadata`) пропускаются; уровни
    0…`max_depth` включительно — чтобы ошибочно выбранный `E:\\` не обходился целиком;
    `OSError` на подкаталоге — пропуск, на корне — пустой список.
    """  # noqa: RUF002
    found: list[ProjectCandidate] = []
    root_name = Path(root).name or root

    def walk(directory: str, relative: str, depth: int) -> None:
        if is_file(os.path.join(directory, ".project")):
            found.append(ProjectCandidate(directory, relative or root_name))
            return
        if depth >= max_depth:
            return
        try:
            names = listdir(directory)
        except OSError:
            return
        for name in names:
            if name.startswith("."):
                continue
            child = os.path.join(directory, name)
            if is_dir(child):
                walk(child, f"{relative}/{name}" if relative else name, depth + 1)

    walk(root, "", 0)
    found.sort(key=lambda candidate: candidate.relative.casefold())
    return found
```

Сборка командной строки — перед классом `EdtCli`:

```python
CliBuilder = Callable[[Path, str, Path, str, str], LaunchCommand]
"""(exe, workspace, jvm_dir, installation_vm_args, project_vm_args) → командная строка CLI."""


def _by_command(command: str) -> CliBuilder:
    return lambda exe, workspace, jvm, installation_args, project_args: build_cli_command(
        exe, workspace, command, jvm, installation_args, project_args
    )


def _by_script(script: Path, ini: Path) -> CliBuilder:
    # JDK уже в ini: у обёртки нет ключа -vm ([Ф] Э12), jvm_dir строке не нужен
    return lambda exe, workspace, _jvm, installation_args, project_args: build_cli_script_command(
        exe, workspace, script, ini, installation_args, project_args
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
```

`EdtCli.__init__` — параметр `read_text: Callable[[Path], str] = _read_text` после `comspec`,
поле `self._read_text`.

`EdtCli.start` — тело после проверки `unavailable_reason` уходит в `_start`:

```python
    def start(self, project_id: str, label: str, command: str, result_file: str = "") -> CliRun:
        reason = self.unavailable_reason(project_id)
        if reason:
            raise EdtError(reason)
        return self._start(
            project_id, label, command, [f"▶ {label}: {command}"], _by_command(command), result_file
        )

    def start_script(self, project_id: str, label: str, commands: Sequence[str]) -> CliRun:
        """Несколько команд одним сеансом: скрипт `<logs_dir>/<id>.cli` в режиме `-file`,
        JDK — через ini `<logs_dir>/<id>.ini` и `-ini-file` (спека v3.1.1 §4.2, [Ф] Э12:
        у обёртки нет ключа `-vm`). Оба файла наши, не пользовательские: обычная
        перезапись; лежат рядом с журналом ради диагностики.

        `unavailable_reason` — ДО записи: живая команда на этой записи читает свой скрипт,
        перезаписывать его нельзя.
        """  # noqa: RUF002
        reason = self.unavailable_reason(project_id)
        if reason:
            raise EdtError(reason)
        project, installation, jvm = self._resolve(project_id)
        try:
            installation_ini = self._read_text(installation.exe.parent / INSTALLATION_INI)
        except OSError as error:
            raise EdtError(f"Не удалось прочитать {INSTALLATION_INI} установки: {error}") from error
        script, ini = self.script_path(project_id), self.ini_path(project_id)
        try:
            script.parent.mkdir(parents=True, exist_ok=True)
            ini.write_text(cli_ini_text(installation_ini, jvm), encoding="utf-8", newline="\n")
            with script.open("w", encoding="utf-8", newline="\n") as handle:
                handle.writelines(f"{command}\n" for command in commands)
        except OSError as error:
            raise EdtError(f"Не удалось записать скрипт CLI: {error}") from error
        events = [f"▶ {label}: скрипт {script.name}, команд: {len(commands)}", *commands]
        return self._start(
            project_id, label, "; ".join(commands), events, _by_script(script, ini), ""
        )

    def script_path(self, project_id: str) -> Path:
        return self._logs_dir / f"{project_id}.cli"

    def ini_path(self, project_id: str) -> Path:
        return self._logs_dir / f"{project_id}.ini"

    def _resolve(self, project_id: str) -> tuple[EdtProject, EdtInstallation, Path]:
        """Запись, установка и JDK; вызывается после `unavailable_reason`."""
        project = self._workspace.project(project_id)
        installation = self._workspace.installation_for(project)
        assert installation is not None  # unavailable_reason проверил
        jvm = effective_jvm(project, installation)
        assert jvm is not None
        return project, installation, jvm

    def _start(
        self,
        project_id: str,
        label: str,
        command_text: str,
        events: Sequence[str],
        build: CliBuilder,
        result_file: str,
    ) -> CliRun:
        project, installation, jvm = self._resolve(project_id)
        cli = build(
            installation.exe.parent / CLI_EXE,
            project.workspace,
            jvm,
            installation.vm_args,
            project.vm_args,
        )
        try:
            # Кодировка вывода — кодовая страница скрытой консоли, не флаги JVM (Э6)
            launch = wrap_console_utf8(cli, self._comspec)
        except CliQuoteError as error:
            raise EdtError(str(error)) from error
        path = self.journal_path(project_id)
        try:
            rotate_journal(self._logs_dir, project_id)
        except OSError as error:
            self._log_event(
                project_id,
                f"ротация журнала не удалась ({error}), записи продолжаются в тот же файл",
            )
        job = self._job_factory()
        try:
            # События — ДО spawn (спека §14.4): ребёнок получает хендл FILE_APPEND_DATA
            # и может написать в журнал раньше этого кода.  # noqa: RUF003
            for event in events:
                append_event(path, event, self._now())
            append_event(path, launch.command_line, self._now())
            spawned = self._spawn(launch, path, job)
        except (OSError, JobError) as error:
            self._close_job(job)
            self._log_event(project_id, f"■ не запущен: {type(error).__name__}")
            raise EdtError(
                f"Не удалось запустить {CLI_EXE}: {error}.\nКоманда: {launch.command_line}"  # noqa: RUF001
            ) from error
        run = CliRun(
            project_id, label, command_text, spawned.pid, spawned.process, job, result_file
        )
        self._runs[project_id] = run
        self._workspace.mark_cli_busy(project_id)
        return run
```

Существующие комментарии из старого `start` (про ротацию best-effort, порядок событий,
`ServerError`) перенести в `_start` дословно — они объясняют решения ревью v3.

- [ ] **Step 5: Прогон — зелёный**

Run: `uv run pytest tests/unit/test_edt_cli.py tests/ui/test_edt_view.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/services/edt_cli.py tests/unit/test_edt_cli.py
git commit -m "feat(services): scan_projects по правилу мастера Eclipse, EdtCli.start_script — скрипт -file с JDK через -ini-file"
```

---

### Task 5: Диалог и вьюха — автоподстановка, список с флажками, скрипт для нескольких проектов

Одна задача, а не две: диалог меняет конструктор и `form()`, вьюха — единственный вызывающий
код; промежуточное состояние «новый диалог со старой вьюхой» не собирается в зелёный suite
без временных правок, которые следующая задача тут же снимала бы.

**Files:**
- Rewrite: `src/onecstarter/ui/edt/cli_import_dialog.py`
- Modify: `src/onecstarter/ui/edt/view.py` (`CLI_IMPORT`, `cli_import`, `_start_cli` →
  `_run_cli`, новый `_start_cli_script`)
- Test: `tests/ui/test_edt_cli_dialogs.py` (класс `TestImportDialog`), `tests/ui/test_edt_view.py`

**Interfaces:**
- Consumes: `ImportForm`, `ProjectCandidate`, `WorkspaceEntry`, `cli_import_commands`,
  `mark_in_workspace` (Task 3); `SCAN_MAX_DEPTH`, `scan_projects`, `EdtCli.start_script`,
  `script_path` (Task 4); `workspace_entries`; `russian_button_box`, `browse_for_directory`.
- Produces: `CliImportDialog(project_dir: str, entries: Sequence[WorkspaceEntry], *, scan=scan_projects, is_dir=os.path.isdir, choose_directory=browse_for_directory, parent=None)`;
  `form() -> ImportForm`; `selected_paths() -> list[str]`; доступ для тестов: `list_widget()`,
  `status_text()`, `select_all_button()`, `select_none_button()`, прежние `ok_button()`,
  `error_text()`, `existing_radio()`, `xml_radio()`, `existing_dir_edit()`, `existing_browse()`,
  `xml_dir_edit()`, `project_dir_edit()`, `project_name_edit()`, `base_project_edit()`,
  `platform_version_edit()`, `build_checkbox()`. Константы `IN_WORKSPACE_SUFFIX`, `NOT_FOUND`,
  `NO_DIR`, `NONE_SELECTED`, `PLACEHOLDER`. Во вьюхе: `CLI_IMPORT = "Импортировать проекты…"`,
  метка запуска «Импортировать (проектов: N)» / «Импортировать».

- [ ] **Step 1: Тесты диалога**

Заменить класс `TestImportDialog` в `tests/ui/test_edt_cli_dialogs.py`:

```python
from PySide6.QtCore import Qt

from onecstarter.domain.edt_cli import ImportForm, ProjectCandidate, WorkspaceEntry
from onecstarter.ui.edt.cli_import_dialog import (
    IN_WORKSPACE_SUFFIX,
    NO_DIR,
    NONE_SELECTED,
    NOT_FOUND,
    CliImportDialog,
)
from onecstarter.ui.edt.cli_validate_dialog import CliValidateDialog

CANDIDATES = [
    ProjectCandidate(r"D:\repo\src\cf", "src/cf"),
    ProjectCandidate(r"D:\repo\src\cfe_a", "src/cfe_a"),
    ProjectCandidate(r"D:\repo\src\cfe_b", "src/cfe_b"),
]
ENTRIES = [WorkspaceEntry("cfe_a", r"D:\repo\src\cfe_a", True)]


class ScanSpy:
    def __init__(self, result: list[ProjectCandidate]) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, root: str) -> list[ProjectCandidate]:
        self.calls.append(root)
        return list(self.result)


def _dialog(qtbot, project_dir: str = r"D:\repo", scan: ScanSpy | None = None, **kwargs):  # type: ignore[no-untyped-def]
    spy = scan if scan is not None else ScanSpy(CANDIDATES)
    kwargs.setdefault("is_dir", lambda p: True)
    kwargs.setdefault("choose_directory", lambda: "")
    dialog = CliImportDialog(project_dir, ENTRIES, scan=spy, **kwargs)
    qtbot.addWidget(dialog)
    return dialog, spy


class TestImportDialog:
    def test_prefilled_dir_scanned_on_open(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot)
        assert dialog.windowTitle() == "Импортировать проекты (CLI EDT)"
        assert dialog.existing_dir_edit().text() == r"D:\repo"
        assert spy.calls == [r"D:\repo"]
        items = [dialog.list_widget().item(i) for i in range(dialog.list_widget().count())]
        assert [item.text() for item in items] == [
            "src/cf", "src/cfe_a" + IN_WORKSPACE_SUFFIX, "src/cfe_b"
        ]
        assert [item.checkState() for item in items] == [
            Qt.CheckState.Checked, Qt.CheckState.Unchecked, Qt.CheckState.Checked
        ]
        assert not items[1].flags() & Qt.ItemFlag.ItemIsEnabled
        assert not items[1].flags() & Qt.ItemFlag.ItemIsUserCheckable
        assert items[0].toolTip() == r"D:\repo\src\cf"
        assert dialog.status_text() == "Найдено 3, уже в рабочей области 1"
        assert dialog.ok_button().isEnabled() is True
        assert dialog.form() == ImportForm(
            existing_project_dirs=(r"D:\repo\src\cf", r"D:\repo\src\cfe_b")
        )

    def test_bound_project_never_in_form(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        # Мутационная проверка: mark_in_workspace → всегда False должен уронить этот тест
        dialog, _ = _dialog(qtbot)
        dialog.select_all_button().click()
        assert r"D:\repo\src\cfe_a" not in dialog.selected_paths()

    def test_empty_project_dir_no_scan(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot, project_dir="")
        assert spy.calls == []
        assert dialog.existing_dir_edit().placeholderText() == (
            "каталог с проектами EDT, например клон репозитория"
        )
        assert dialog.status_text() == ""
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == NONE_SELECTED

    def test_browse_rescans(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot, project_dir="", choose_directory=lambda: r"D:\picked")
        dialog.existing_browse().click()
        assert dialog.existing_dir_edit().text() == r"D:\picked"
        assert spy.calls == [r"D:\picked"]
        assert dialog.list_widget().count() == 3

    def test_editing_finished_rescans(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot, project_dir="")
        dialog.existing_dir_edit().setText(r"D:\typed")
        assert spy.calls == []  # не на каждый символ
        dialog.existing_dir_edit().editingFinished.emit()
        assert spy.calls == [r"D:\typed"]

    def test_select_all_and_none_skip_bound(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)
        dialog.select_none_button().click()
        assert dialog.selected_paths() == []
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == NONE_SELECTED
        dialog.select_all_button().click()
        assert dialog.selected_paths() == [r"D:\repo\src\cf", r"D:\repo\src\cfe_b"]
        assert dialog.list_widget().item(1).checkState() == Qt.CheckState.Unchecked

    def test_unchecked_item_excluded_in_order(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)
        dialog.list_widget().item(0).setCheckState(Qt.CheckState.Unchecked)
        assert dialog.form().existing_project_dirs == (r"D:\repo\src\cfe_b",)

    def test_no_projects_status(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, scan=ScanSpy([]))
        assert dialog.status_text() == NOT_FOUND
        assert dialog.ok_button().isEnabled() is False

    def test_missing_dir_status(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, scan=ScanSpy([]), is_dir=lambda p: False)
        assert dialog.status_text() == NO_DIR
        assert dialog.ok_button().isEnabled() is False

    def test_quote_in_candidate_path_reports_error(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, scan=ScanSpy([ProjectCandidate(r"D:\O'Reilly\p", "p")]))
        assert dialog.ok_button().isEnabled() is False
        assert "Кавычка в значении недопустима" in dialog.error_text()

    def test_xml_variant_fields(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, project_dir="")
        dialog.xml_radio().setChecked(True)
        assert dialog.list_widget().isEnabled() is False
        dialog.xml_dir_edit().setText(r"D:\xml")
        assert dialog.ok_button().isEnabled() is False  # нет каталога/имени
        dialog.project_name_edit().setText("ext")
        dialog.base_project_edit().setText("base")
        dialog.platform_version_edit().setText("8.3.24")
        dialog.build_checkbox().setChecked(True)
        assert dialog.ok_button().isEnabled() is True
        assert dialog.form() == ImportForm(
            configuration_files=r"D:\xml",
            project_name="ext",
            base_project_name="base",
            platform_version="8.3.24",
            build_after=True,
        )

    def test_variant_switch_drops_projects_from_form(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)
        dialog.xml_radio().setChecked(True)
        dialog.xml_dir_edit().setText(r"D:\xml")
        dialog.project_dir_edit().setText(r"D:\new")
        assert dialog.form().existing_project_dirs == ()
        assert dialog.error_text() == ""
```

Остальные тесты файла (`CliValidateDialog`) не меняются.

- [ ] **Step 2: Тесты вьюхи**

В `tests/ui/test_edt_view.py` заменить `test_cli_import_runs_dialog_form`:

```python
def _repo(tmp_path: Path, *names: str) -> Path:
    """Клон с проектами `src/<имя>/.project` — как у заказчика (спека v3.1.1, факт 9)."""
    repo = tmp_path / "repo"
    for name in names:
        (repo / "src" / name).mkdir(parents=True)
        (repo / "src" / name / ".project").write_text("<projectDescription/>", encoding="utf-8")
    return repo


def test_cli_import_prefills_dir_and_imports_selected_by_script(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(harness.tmp_path, "cf", "cfe_a")
    p = _add(harness, "a", project_dir=str(repo))
    view = harness.view()
    qtbot.addWidget(view)
    seen: list[str] = []

    def run_dialog(dialog):
        seen.append(dialog.existing_dir_edit().text())
        return True  # все найденные отмечены по умолчанию

    monkeypatch.setattr(view, "_run_dialog", run_dialog)
    view.cli_import(p.id)
    assert seen == [str(repo)]
    script, ini = harness.cli.script_path(p.id), harness.cli.ini_path(p.id)
    assert f'-ini-file "{ini}"' in harness.cli_spawned[0].arguments
    assert f'-file "{script}"' in harness.cli_spawned[0].arguments
    assert "-vm\n" in ini.read_text(encoding="utf-8")
    cf = str(repo / "src" / "cf").replace("\\", "/")
    cfe = str(repo / "src" / "cfe_a").replace("\\", "/")
    assert script.read_text(encoding="utf-8") == (
        f"import --project '{cf}'\nimport --project '{cfe}'\n"
    )
    assert view.console().title_label().text() == "a · Импортировать (проектов: 2)"


def test_cli_import_single_project_uses_command(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(harness.tmp_path, "cf")
    p = _add(harness, "a", project_dir=str(repo))
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_run_dialog", lambda dialog: True)
    view.cli_import(p.id)
    cf = str(repo / "src" / "cf").replace("\\", "/")
    # Прямые слэши в -command ([Ф] Э6: с обратными Gogo не снимает кавычки, код 204)  # noqa: RUF003
    assert f"-command \"import --project '{cf}'\"" in harness.cli_spawned[0].arguments
    assert view.console().title_label().text() == "a · Импортировать"


def test_cli_import_bound_projects_are_not_offered(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = _repo(harness.tmp_path, "cf", "cfe_a")
    ws = harness.tmp_path / "ws"
    registry = ws / ".metadata" / ".plugins" / "org.eclipse.core.resources" / ".projects" / "cf"
    registry.mkdir(parents=True)
    (registry / ".location").write_bytes(location_blob((repo / "src" / "cf").as_uri()))
    p = _add(harness, "a", workspace=str(ws), project_dir=str(repo))
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_run_dialog", lambda dialog: True)
    view.cli_import(p.id)
    cfe = str(repo / "src" / "cfe_a").replace("\\", "/")
    assert f"-command \"import --project '{cfe}'\"" in harness.cli_spawned[0].arguments
```

`location_blob` уже импортируется в `tests/unit/test_edt_cli.py` из `onecstarter.domain.edt_cli`;
в `test_edt_view.py` добавить тот же импорт. `test_cli_import_cancelled_starts_nothing`
оставить как есть. `Harness` в `test_edt_view.py`: в `EdtCli(...)` добавить
`read_text=lambda p: "-vmargs\n-Xmx4096m\n"` — путь установки в тестах фиктивный,
настоящий `1cedt.ini` читать нельзя.

- [ ] **Step 3: Прогон — падает**

Run: `uv run pytest tests/ui/test_edt_cli_dialogs.py tests/ui/test_edt_view.py -q -k "ImportDialog or cli_import"`
Expected: `ImportError` (`IN_WORKSPACE_SUFFIX`, …).

- [ ] **Step 4: Реализация `ui/edt/cli_import_dialog.py`**

```python
"""Диалог `import` CLI EDT (спека v3 §14.2, v3.1.1 §3): проекты в каталоге или файлы XML.

Каталог подставляется из записи, проекты в нём находит `scan_projects` (правило
мастера импорта Eclipse), уже привязанные к рабочей области — сняты и недоступны:
повторный `import` стоит ≈48 с и ничего не даёт ([Ф] Э6, Э12).
"""  # noqa: RUF002

import os
from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt_cli import (
    ImportForm,
    ProjectCandidate,
    WorkspaceEntry,
    cli_import_commands,
    mark_in_workspace,
)
from onecstarter.services.edt_cli import SCAN_MAX_DEPTH, scan_projects
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.edt.dialog import browse_for_directory

IN_WORKSPACE_SUFFIX = " — уже в рабочей области"
NOT_FOUND = f"Проектов не найдено: каталог с .project ищется до {SCAN_MAX_DEPTH} уровней"
NO_DIR = "Каталог не существует"
NONE_SELECTED = "Не выбран ни один проект"  # noqa: RUF001
PLACEHOLDER = "каталог с проектами EDT, например клон репозитория"


class CliImportDialog(QDialog):
    def __init__(
        self,
        project_dir: str,
        entries: Sequence[WorkspaceEntry],
        *,
        scan: Callable[[str], list[ProjectCandidate]] = scan_projects,
        is_dir: Callable[[str], bool] = os.path.isdir,
        choose_directory: Callable[[], str] = browse_for_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импортировать проекты (CLI EDT)")
        self._entries = list(entries)
        self._scan = scan
        self._is_dir = is_dir
        self._choose_directory = choose_directory
        self._candidates: list[ProjectCandidate] = []

        self._existing = QRadioButton("Проекты EDT в каталоге")
        self._xml = QRadioButton("Файлы конфигурации XML")
        self._existing.setChecked(True)
        self._existing_dir = QLineEdit(project_dir)
        self._existing_dir.setPlaceholderText(PLACEHOLDER)
        # Не textChanged: обход трёх уровней от `E:\` не мгновенный
        self._existing_dir.editingFinished.connect(self._rescan)
        self._existing_browse = QPushButton("Обзор…")
        self._existing_browse.clicked.connect(self._browse_existing)
        self._list = QListWidget()
        self._list.setMinimumHeight(180)
        self._list.itemChanged.connect(self._refresh)
        self._select_all = QPushButton("Выбрать всё")
        self._select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self._select_none = QPushButton("Снять всё")
        self._select_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self._status = QLabel("")

        self._xml_dir = QLineEdit()
        self._xml_browse = QPushButton("Обзор…")
        self._xml_browse.clicked.connect(lambda: self._browse_into(self._xml_dir))
        self._project_dir = QLineEdit()
        self._project_dir.setPlaceholderText("каталог нового проекта — или имя ниже")
        self._project_dir_browse = QPushButton("Обзор…")
        self._project_dir_browse.clicked.connect(lambda: self._browse_into(self._project_dir))
        self._project_name = QLineEdit()
        self._project_name.setPlaceholderText("имя нового проекта в рабочей области")
        self._base_project = QLineEdit()
        self._base_project.setPlaceholderText("для расширений и внешних обработок")
        self._platform_version = QLineEdit()
        self._platform_version.setPlaceholderText("8.3.24 — пусто: из файлов")
        self._build = QCheckBox("Собрать после импорта (--build)")
        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        tools = QWidget()
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.addWidget(self._select_all)
        tools_layout.addWidget(self._select_none)
        tools_layout.addStretch(1)
        tools_layout.addWidget(self._status)

        form = QFormLayout()
        form.addRow(self._existing)
        form.addRow("Каталог", self._row(self._existing_dir, self._existing_browse))
        form.addRow(self._list)
        form.addRow(tools)
        form.addRow(self._xml)
        form.addRow("Каталог файлов XML", self._row(self._xml_dir, self._xml_browse))
        form.addRow(
            "Каталог нового проекта", self._row(self._project_dir, self._project_dir_browse)
        )
        form.addRow("Имя нового проекта", self._project_name)
        form.addRow("Базовый проект", self._base_project)
        form.addRow("Версия платформы", self._platform_version)
        form.addRow("", self._build)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)
        self.resize(720, 640)

        for widget in (
            self._xml_dir,
            self._project_dir,
            self._project_name,
            self._base_project,
            self._platform_version,
        ):
            widget.textChanged.connect(self._refresh)
        self._existing.toggled.connect(self._refresh)
        self._build.toggled.connect(self._refresh)
        if project_dir:
            self._rescan()
        else:
            self._refresh()

    def form(self) -> ImportForm:
        if self._existing.isChecked():
            return ImportForm(existing_project_dirs=tuple(self.selected_paths()))
        return ImportForm(
            configuration_files=self._xml_dir.text().strip(),
            project_dir=self._project_dir.text().strip(),
            project_name=self._project_name.text().strip(),
            base_project_name=self._base_project.text().strip(),
            platform_version=self._platform_version.text().strip(),
            build_after=self._build.isChecked(),
        )

    def selected_paths(self) -> list[str]:
        return [
            candidate.path
            for index, candidate in enumerate(self._candidates)
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _rescan(self) -> None:
        root = self._existing_dir.text().strip()
        self._list.blockSignals(True)  # itemChanged на каждом addItem — лишние _refresh
        self._list.clear()
        self._candidates = []
        status = ""
        if root:
            self._candidates = mark_in_workspace(self._scan(root), self._entries)
            for candidate in self._candidates:
                suffix = IN_WORKSPACE_SUFFIX if candidate.in_workspace else ""
                item = QListWidgetItem(candidate.relative + suffix)
                item.setToolTip(candidate.path)
                if candidate.in_workspace:
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                self._list.addItem(item)
            bound = sum(1 for candidate in self._candidates if candidate.in_workspace)
            if self._candidates:
                status = f"Найдено {len(self._candidates)}, уже в рабочей области {bound}"
            elif self._is_dir(root):
                status = NOT_FOUND
            else:
                status = NO_DIR
        self._status.setText(status)
        self._list.blockSignals(False)
        self._refresh()

    def _set_all(self, state: Qt.CheckState) -> None:
        for index, candidate in enumerate(self._candidates):
            if not candidate.in_workspace:
                self._list.item(index).setCheckState(state)

    def _refresh(self, *_args: object) -> None:
        xml = self._xml.isChecked()
        for widget in (
            self._xml_dir,
            self._xml_browse,
            self._project_dir,
            self._project_dir_browse,
            self._project_name,
            self._base_project,
            self._platform_version,
            self._build,
        ):
            widget.setEnabled(xml)
        for widget in (
            self._existing_dir,
            self._existing_browse,
            self._list,
            self._select_all,
            self._select_none,
        ):
            widget.setEnabled(not xml)
        error = ""
        if not xml and not self.selected_paths():
            error = NONE_SELECTED
        else:
            try:
                cli_import_commands(self.form())
            except ValueError as validation_error:  # CliQuoteError — подкласс
                error = str(validation_error)
        self._error.setText(error)
        self.ok_button().setEnabled(not error)

    def _browse_existing(self) -> None:
        chosen = self._choose_directory()
        if chosen:
            self._existing_dir.setText(chosen)
            self._rescan()

    def _browse_into(self, edit: QLineEdit) -> None:
        chosen = self._choose_directory()
        if chosen:
            edit.setText(chosen)

    @staticmethod
    def _row(edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    # --- доступ ---
    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]

    def error_text(self) -> str:
        return self._error.text()

    def status_text(self) -> str:
        return self._status.text()

    def list_widget(self) -> QListWidget:
        return self._list

    def select_all_button(self) -> QPushButton:
        return self._select_all

    def select_none_button(self) -> QPushButton:
        return self._select_none

    def existing_radio(self) -> QRadioButton:
        return self._existing

    def xml_radio(self) -> QRadioButton:
        return self._xml

    def existing_dir_edit(self) -> QLineEdit:
        return self._existing_dir

    def existing_browse(self) -> QPushButton:
        return self._existing_browse

    def xml_dir_edit(self) -> QLineEdit:
        return self._xml_dir

    def project_dir_edit(self) -> QLineEdit:
        return self._project_dir

    def project_name_edit(self) -> QLineEdit:
        return self._project_name

    def base_project_edit(self) -> QLineEdit:
        return self._base_project

    def platform_version_edit(self) -> QLineEdit:
        return self._platform_version

    def build_checkbox(self) -> QCheckBox:
        return self._build
```

- [ ] **Step 5: Реализация в `view.py`**

`CLI_IMPORT = "Импортировать проекты…"`. Импорт `cli_import_commands` (уже с Task 3).

```python
    def cli_import(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        dialog = CliImportDialog(
            project.project_dir,
            workspace_entries(project.workspace),
            choose_directory=self._choose_directory,
            parent=self,
        )
        if not self._run_dialog(dialog):
            return
        try:
            commands = cli_import_commands(dialog.form())
        except ValueError as error:  # диалог не даёт ОК без команд — страховка
            self._show_error(str(error))
            return
        label = "Импортировать"  # не CLI_IMPORT.rstrip("…"): тот даёт «Импортировать проекты»
        if len(commands) == 1:
            self._start_cli(project_id, label, commands[0])
        else:
            self._start_cli_script(project_id, f"{label} (проектов: {len(commands)})", commands)
```

`_start_cli` разделить на запуск и общую часть:

```python
    def _start_cli(self, project_id: str, label: str, command: str, result_file: str = "") -> None:
        if self._cli is None:
            return
        cli = self._cli
        self._run_cli(project_id, label, lambda: cli.start(project_id, label, command, result_file))

    def _start_cli_script(self, project_id: str, label: str, commands: Sequence[str]) -> None:
        """Несколько команд одним сеансом — скрипт `-file` (спека v3.1.1 §4.2)."""
        if self._cli is None:
            return
        cli = self._cli
        self._run_cli(project_id, label, lambda: cli.start_script(project_id, label, commands))

    def _run_cli(self, project_id: str, label: str, start: Callable[[], CliRun]) -> None:
        if self._cli is None:
            return
        try:
            run = start()
        except ServicesError as error:
            self._show_error(str(error))
            return
        project = self._workspace.project(project_id)
        self._console_project = project_id
        self._console.show_run(
            project.name, label, STATE_RUNNING, self._cli.journal_path(project_id)
        )
        self._console.set_buttons(interrupt=True, journal=True, result=False)
        self._console.expand()  # единственное место, где консоль раскрывается сама (§14.5)
        if self._watcher is not None:
            self._watcher.watch(run)
        self.rebuild()
```

- [ ] **Step 6: Прогон — зелёный, мутационная проверка**

Run: `uv run pytest tests/ui/test_edt_cli_dialogs.py tests/ui/test_edt_view.py -q && uv run ruff check . && uv run mypy`
Expected: PASS. Если где-то в тестах остался текст «Импортировать проект…» пункта меню —
обновить на «Импортировать проекты…».

Мутация: в `domain/edt_cli.py::mark_in_workspace` заменить `in_workspace=workspace_key(candidate.path) in keys`
на `in_workspace=False`; `uv run pytest tests/ui/test_edt_cli_dialogs.py -q` → ожидается
`FAILED …::test_bound_project_never_in_form` и `test_prefilled_dir_scanned_on_open`; откатить
`git checkout -- src/onecstarter/domain/edt_cli.py`; `git status --short` — файл чист;
прогон зелёный повторно. Результат — в отчёт задачи.

- [ ] **Step 7: Коммит**

```bash
git add src/onecstarter/ui/edt/cli_import_dialog.py src/onecstarter/ui/edt/view.py tests/ui/test_edt_cli_dialogs.py tests/ui/test_edt_view.py
git commit -m "feat(ui): диалог импорта — каталог записи, найденные проекты с флажками, импорт отмеченных одним сеансом CLI"
```

---

### Task 6: Документы, версия 3.1.1, сборка и smoke

**Files:**
- Modify: `README.md` (абзац про подменю «CLI», строки 84–88), `docs/requirements.md` (§5
  таблица вех — строка `v3.1.1`), `docs/tasks.md` (новый раздел `T-20`), `pyproject.toml`
  (`version = "3.1.1"`)
- Run: полный прогон, `build/build.ps1`

- [ ] **Step 1: README и requirements**

README, абзац про подменю «CLI»: после «сборка, импорт, проверка и информация по …» добавить
предложение: «Импорт берёт каталог проекта записи, находит в нём проекты EDT (каталоги с
`.project`, до трёх уровней вглубь) и импортирует отмеченные одним сеансом CLI; уже привязанные
к рабочей области в списке недоступны.»

`docs/requirements.md` §5, после строки `v3.1` (если её нет — после `v3`):
`| v3.1.1 | Импорт выбранных проектов через CLI EDT: каталог записи, список найденных проектов с флажками, один сеанс CLI на все отмеченные | — |`
(последняя колонка — как у соседних строк).

- [ ] **Step 2: tasks.md — раздел T-20**

Перед разделом про v3.2/после T-18, по образцу T-18:

```markdown
## T-20. v3.1.1 — импорт выбранных проектов через CLI EDT — DONE (<дата>, ветка `feat/2026-09-16-v311`)

Дизайн — [спека v3.1.1](superpowers/specs/2026-09-16-v311-cli-import-projects-design.md). План —
[план v3.1.1](superpowers/plans/2026-09-16-v311-cli-import-projects.md). Эксперимент Э12 —
[t20-edt-import-experiments.md](research/t20-edt-import-experiments.md).

| # | Задача | Коммит(ы) |
| --- | --- | --- |
| 1 | Протокол Э12, скрипт запуска | … |
| 2 | Э12 проведён, метки, скил | … |
| 3 | Домен: кандидаты, `cli_import_commands`, `-file` | … |
| 4 | Сервис: `scan_projects`, `start_script` | … |
| 5 | Диалог и вьюха | … |
| 6 | Документы, 3.1.1, сборка | … |

### Полный прогон и статика (<дата>)

### Мутационные проверки (<дата>)

### Гейты сборки 3.1.1 (<дата>)
```

Коммиты — из `git log --oneline`; результаты прогона и мутационной проверки — из отчётов
задач 5 и 6.

- [ ] **Step 3: Версия и полный прогон**

`pyproject.toml`: `version = "3.1.1"`. `uv sync` (обновит метаданные пакета — «О программе»
читает их через `importlib.metadata`).

Run: `uv run pytest -q > e:/tmp/v311-full.log 2>&1; tail -3 e:/tmp/v311-full.log && uv run ruff check . && uv run mypy`
Expected: `… passed`, `All checks passed!`, `Success`. Флейк `access violation` — повторить.

- [ ] **Step 4: Сборка и smoke**

Run: `powershell -ExecutionPolicy Bypass -File build/build.ps1`
Expected: в конце `smoke: frozen`, `smoke: keyring=ok`, `smoke: edt=<n>`, `smoke: version=3.1.1`,
артефакты `dist/OneCStarter-3.1.1-setup.exe`, `dist/OneCStarter-3.1.1-portable.zip`.

- [ ] **Step 5: Коммит**

```bash
git add README.md docs/requirements.md docs/tasks.md pyproject.toml uv.lock
git commit -m "docs: v3.1.1 — T-20, README, requirements; версия 3.1.1, гейты сборки"
```

Ручной smoke заказчика (после сборки): открыть «Импортировать проекты…» на записи с клоном —
каталог подставлен, список найден, привязанные недоступны; импорт двух проектов — консоль
«Импортировать (проектов: 2)», код 0, при повторном открытии оба недоступны. Слияние в
`master`, тег `v3.1.1`, push — после подтверждения.

---
