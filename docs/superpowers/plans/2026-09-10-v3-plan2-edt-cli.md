# Проекты EDT — план 2 реализации v3: CLI и консоль

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** четыре команды CLI EDT из контекстного меню записи (`build`, `import`, `validate`, `project`) с выводом в сворачиваемую консоль, которая раскрывается только при запуске команды.

**Architecture:** сборка командной строки `1cedtcli.exe` и строк команд — чистые функции в `domain/edt_cli.py`; порождение — тем же `platform_1c/server_spawn.py` (stdout в файл журнала хендлом `FILE_APPEND_DATA`, процесс в `Job`), расширенным функцией, возвращающей `Popen`; координация одной команды на запись и журнал — `services/edt_cli.py::EdtCli`; ожидание кода завершения — поток-демон в `ui/edt/cli_watch.py` с сигналом Qt; консоль — обёртка над `ui/servers/journal_panel.py::JournalPanel`.

**Tech Stack:** Python 3.13, PySide6, ctypes (Job Object — существующий `platform_1c/job.py`), pytest + pytest-qt, ruff, mypy strict.

Спека — [2026-09-10-v3-edt-design.md](../specs/2026-09-10-v3-edt-design.md), §0-Д, §14.
База — завершённый [план 1](2026-09-10-v3-plan1-edt-section.md) на ветке `feat/2026-09-10-v3-edt`.

## Global Constraints

- Всё из Global Constraints плана 1 (инварианты 1, 2, 4, 5; сторож `CORE`; прогон pytest
  в файл; русские тексты; коммиты без атрибуции).
- **CLI только на закрытом workspace** (спека §14.1): подменю CLI неактивно для записи
  со статусом «запущен» и для записи с выполняющейся командой; «Открыть в EDT»
  неактивен, пока команда выполняется. Проверка — в координаторе, не только в меню.
- **`-command` до `-vmargs`** ([?] спека §0-Д, эксперимент 6): порядок фиксирован
  в `build_cli_command` и табличном тесте.
- **`build` всегда с `--yes`** ([Д] спека §0-Д): без него команда ждёт подтверждения.
- **Аргументы внутри `-command`** — в одинарных кавычках ([Д] справка CLI); значение
  с кавычкой внутри — одинарной или двойной (вся команда идёт как `-command "…"`,
  правка M3 финального ревью) — диалог не принимает.
- Точные строки UI: подменю `CLI`; пункты `Пересобрать проекты`, `Импортировать проект…`,
  `Проверить проекты…`, `Информация по проектам`; подсказки `Закройте EDT: workspace занят`,
  `Выполняется команда CLI`, `В установке <версия> нет 1cedtcli.exe`; заголовок консоли
  `Консоль`; состояния `выполняется`, `завершено, код N`, `прервано`, `не запущен`.
- Журналы — `%APPDATA%\OneCStarter\logs\edt\<id записи>.log` (+ `.1.log` прошлый).
- 1С, EDT и CLI не запускать. Тесты подменяют `spawn_logged`, `wait`, `Job`.

## Карта файлов

| Файл | Ответственность | Задачи |
| --- | --- | --- |
| `src/onecstarter/domain/edt_cli.py` | `quote_cli_arg`, `cli_build_args`, `cli_project_args`, `cli_import_args`, `cli_validate_args`, `workspace_projects`, `build_cli_command`, `ImportForm`, `CLI_ENCODING_ARGS` | 1 |
| `src/onecstarter/platform_1c/server_spawn.py` | `spawn_logged(...) -> LoggedProcess` (общее ядро с `spawn_server`) | 2 |
| `src/onecstarter/services/edt.py` | `cli_busy` в статусе, отказ `launch` при занятом workspace | 3 |
| `src/onecstarter/services/edt_cli.py` | `EdtCli`: одна команда на запись, журнал, прерывание, подсчёт живых | 3 |
| `src/onecstarter/ui/edt/cli_watch.py` | `CliWatcher`: ожидание кода в потоке-демоне → сигнал | 4 |
| `src/onecstarter/ui/edt/console_panel.py` | `EdtConsole`: сворачиваемая обёртка над `JournalPanel` | 4 |
| `src/onecstarter/ui/edt/cli_import_dialog.py` | `CliImportDialog` → `ImportForm` | 5 |
| `src/onecstarter/ui/edt/cli_validate_dialog.py` | `CliValidateDialog` → пути и TSV | 5 |
| `src/onecstarter/ui/edt/view.py` | подменю CLI, запуск команд, консоль под деревом | 6 |
| `src/onecstarter/ui/app.py` | `EdtCli`, `CliWatcher`, гейт выхода с живыми командами | 6 |
| `docs/tasks.md` | T-17.2 и мутации | 7 |

---

### Task 1: Домен — строки команд и командная строка `1cedtcli.exe`

**Files:**
- Create: `src/onecstarter/domain/edt_cli.py`
- Create: `tests/unit/test_edt_cli_domain.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.domain.edt_cli"`)

**Interfaces:**
- Consumes: `CLI_EXE`, `EdtProject`, `EdtInstallation` (`domain/edt.py`, план 1); `LaunchCommand`.
- Produces:

```python
CLI_ENCODING_ARGS = "-Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8"

class CliQuoteError(ValueError): ...
def quote_cli_arg(value: str) -> str                      # 'значение'; кавычка внутри (' или ") → CliQuoteError
def cli_build_args() -> str                               # "build --yes"
def cli_project_args() -> str                             # "project"

@dataclass(frozen=True)
class ImportForm:
    existing_project_dir: str = ""      # вариант «существующий проект EDT»
    configuration_files: str = ""       # вариант «файлы конфигурации XML»
    project_dir: str = ""
    project_name: str = ""
    base_project_name: str = ""
    platform_version: str = ""
    build_after: bool = False

def cli_import_args(form: ImportForm) -> str              # ValueError на пустой/двойственной форме
def cli_validate_args(paths: Sequence[str], tsv: str) -> str

@dataclass(frozen=True)
class WorkspaceEntry:
    name: str
    path: str
    is_project: bool                    # есть файл .project

def workspace_projects(entries: Sequence[WorkspaceEntry], project_dir: str) -> list[str]  # пути для validate
def build_cli_command(exe: Path, workspace: str, command: str, jvm_dir: Path, installation_vm_args: str, project_vm_args: str) -> LaunchCommand
```

- [ ] **Step 1: Написать падающие тесты**

`tests/unit/test_edt_cli_domain.py`:

```python
"""Домен CLI EDT: строки команд и командная строка 1cedtcli.exe (спека §14.2–14.3, факты §0-Д)."""

from pathlib import Path

import pytest

from onecstarter.domain.edt_cli import (
    CLI_ENCODING_ARGS,
    CliQuoteError,
    ImportForm,
    WorkspaceEntry,
    build_cli_command,
    cli_build_args,
    cli_import_args,
    cli_project_args,
    cli_validate_args,
    quote_cli_arg,
    workspace_projects,
)

CLI = Path(r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedtcli.exe")
JDK = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin")


class TestQuote:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (r"D:\edt\a", "'D:\\edt\\a'"),
            (r"D:\edt\a b\проект", "'D:\\edt\\a b\\проект'"),
            ("name", "'name'"),
        ],
    )
    def test_single_quotes(self, value: str, expected: str) -> None:
        assert quote_cli_arg(value) == expected

    @pytest.mark.parametrize(
        ("value", "quote"),
        [
            ("O'Reilly", "'"),  # одинарная — экранирование Gogo не проверялось
            ('conf "v2"', '"'),  # двойная разорвёт внешние кавычки -command "…" (M3 ревью)
            ('D:\\ws\\"a', '"'),
        ],
    )
    def test_quote_inside_rejected(self, value: str, quote: str) -> None:
        with pytest.raises(CliQuoteError, match="Кавычка в значении недопустима") as excinfo:
            quote_cli_arg(value)
        assert value in str(excinfo.value)
        assert quote in value


def test_fixed_commands() -> None:
    assert cli_build_args() == "build --yes"  # [Д] без --yes ждёт подтверждения
    assert cli_project_args() == "project"


class TestImportArgs:
    def test_existing_project(self) -> None:
        assert cli_import_args(ImportForm(existing_project_dir=r"D:\src\proj")) == (
            "import --project 'D:\\src\\proj'"
        )

    def test_xml_into_project_dir_minimal(self) -> None:
        form = ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\edt\ws\new")
        assert cli_import_args(form) == (
            "import --configuration-files 'D:\\xml' --project 'D:\\edt\\ws\\new'"
        )

    def test_xml_into_named_project_full(self) -> None:
        form = ImportForm(
            configuration_files=r"D:\xml",
            project_name="ext_a",
            base_project_name="base",
            platform_version="8.3.24",
            build_after=True,
        )
        assert cli_import_args(form) == (
            "import --configuration-files 'D:\\xml' --project-name 'ext_a' "
            "--base-project-name 'base' --version 8.3.24 --build"
        )

    def test_both_variants_rejected(self) -> None:
        with pytest.raises(ValueError, match="один вариант"):
            cli_import_args(ImportForm(existing_project_dir=r"D:\a", configuration_files=r"D:\xml"))

    def test_xml_without_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="каталог или имя"):
            cli_import_args(ImportForm(configuration_files=r"D:\xml"))

    def test_xml_with_both_targets_rejected(self) -> None:
        with pytest.raises(ValueError, match="каталог или имя"):
            cli_import_args(
                ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\p", project_name="n")
            )

    def test_empty_form_rejected(self) -> None:
        with pytest.raises(ValueError):
            cli_import_args(ImportForm())

    def test_bad_platform_version_rejected(self) -> None:
        with pytest.raises(ValueError, match="8.3.x"):
            cli_import_args(
                ImportForm(configuration_files=r"D:\xml", project_name="n", platform_version="8;3")
            )


class TestValidateArgs:
    def test_single_path(self) -> None:
        assert cli_validate_args([r"D:\ws\p"], r"D:\out\r.tsv") == (
            "validate --project-list 'D:\\ws\\p' --file 'D:\\out\\r.tsv'"
        )

    def test_several_paths_space_separated(self) -> None:
        # [?] спека §0-Д: разделитель списка — эксперимент 6; константа _LIST_SEPARATOR в одном месте
        assert cli_validate_args([r"D:\ws\a", r"D:\ws\b c"], r"D:\r.tsv") == (
            "validate --project-list 'D:\\ws\\a' 'D:\\ws\\b c' --file 'D:\\r.tsv'"
        )

    def test_empty_paths_rejected(self) -> None:
        with pytest.raises(ValueError):
            cli_validate_args([], r"D:\r.tsv")


class TestWorkspaceProjects:
    ENTRIES = [
        WorkspaceEntry(".metadata", r"D:\ws\.metadata", False),
        WorkspaceEntry("conf", r"D:\ws\conf", True),
        WorkspaceEntry("conf.ext", r"D:\ws\conf.ext", True),
        WorkspaceEntry("Серверы", r"D:\ws\Серверы", True),
        WorkspaceEntry("junk", r"D:\ws\junk", False),
    ]

    def test_only_dirs_with_dot_project(self) -> None:
        assert workspace_projects(self.ENTRIES, "") == [r"D:\ws\conf", r"D:\ws\conf.ext", r"D:\ws\Серверы"]

    def test_project_dir_outside_added_first(self) -> None:
        assert workspace_projects(self.ENTRIES, r"E:\git\repo")[0] == r"E:\git\repo"

    def test_project_dir_inside_not_duplicated(self) -> None:
        result = workspace_projects(self.ENTRIES, r"d:\WS\conf")
        assert result.count(r"D:\ws\conf") == 1
        assert r"d:\WS\conf" not in result


class TestBuildCliCommand:
    def test_order_command_before_vmargs_with_encoding(self) -> None:
        command = build_cli_command(
            CLI, r"D:\edt\ws", "build --yes", JDK, "-Xmx8192m -Dx=1", "-Xmx4g"
        )
        assert command.executable == CLI
        assert command.arguments == (
            f'-data "D:\\edt\\ws" -command "build --yes" -vm "{JDK}" --launcher.appendVmargs '
            f"-vmargs -Xmx8192m -Dx=1 -Djava.library.path= -Xmx4g {CLI_ENCODING_ARGS}"
        )

    def test_empty_vm_args(self) -> None:
        command = build_cli_command(CLI, r"D:\ws", "project", JDK, "", "")
        assert command.arguments == (
            f'-data "D:\\ws" -command "project" -vm "{JDK}" --launcher.appendVmargs '
            f"-vmargs -Djava.library.path= {CLI_ENCODING_ARGS}"
        )

    def test_command_with_single_quotes_survives_double_quoting(self) -> None:
        command = build_cli_command(CLI, r"D:\ws", "import --project 'D:\\a b'", JDK, "", "")
        assert '-command "import --project \'D:\\a b\'"' in command.arguments
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_cli_domain.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать**

`src/onecstarter/domain/edt_cli.py`:

```python
"""Домен CLI EDT (спека v3, §14; факты — §0-Д): строки команд и командная строка.

Чистые функции: ни ФС, ни процессов. Имена команд `import`/`validate` —
[?] выведены из имён методов плагина, подтверждаются экспериментом 6;
ключи — [Д] ресурсы CLI. Разделитель списка `--project-list` — [?],
константа `_LIST_SEPARATOR` в одном месте.
"""  # noqa: RUF002

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from onecstarter.domain.launch import LaunchCommand

# [?] спека §0-Д: обе пары свойств — для JDK 17 (sun.*) и 19+; эксперимент 6.
CLI_ENCODING_ARGS = (
    "-Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8 "
    "-Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8"
)
_LIST_SEPARATOR = " "
_PLATFORM_VERSION = re.compile(r"^\d+(\.\d+){1,3}$")


class CliQuoteError(ValueError):
    """Значение содержит кавычку (спека §14.2): одинарную — экранирование Gogo
    не проверялось; двойную — вся команда идёт как `-command "…"` (§14.3), и `"`
    внутри разорвёт внешние кавычки (правка M3 финального ревью плана 2).
    """


def quote_cli_arg(value: str) -> str:
    """Одинарные кавычки — [Д] справка CLI («use single quotes … interpreter rules»)."""
    if "'" in value or '"' in value:
        raise CliQuoteError(f"Кавычка в значении недопустима: {value}")
    return f"'{value}'"


def cli_build_args() -> str:
    return "build --yes"  # [Д] без --yes команда спрашивает «Really build? (y/n)»


def cli_project_args() -> str:
    return "project"


@dataclass(frozen=True)
class ImportForm:
    existing_project_dir: str = ""
    configuration_files: str = ""
    project_dir: str = ""
    project_name: str = ""
    base_project_name: str = ""
    platform_version: str = ""
    build_after: bool = False


def cli_import_args(form: ImportForm) -> str:
    existing = form.existing_project_dir.strip()
    xml = form.configuration_files.strip()
    if existing and xml:
        raise ValueError("Выберите один вариант импорта: существующий проект или файлы XML")
    if existing:
        return f"import --project {quote_cli_arg(existing)}"
    if not xml:
        raise ValueError("Укажите каталог проекта или каталог файлов конфигурации")
    project_dir = form.project_dir.strip()
    project_name = form.project_name.strip()
    if bool(project_dir) == bool(project_name):
        raise ValueError("Для файлов XML укажите каталог или имя нового проекта — одно из двух")
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
    return " ".join(parts)


def cli_validate_args(paths: Sequence[str], tsv: str) -> str:
    if not paths:
        raise ValueError("Не выбран ни один проект")
    quoted = _LIST_SEPARATOR.join(quote_cli_arg(path) for path in paths)
    return f"validate --project-list {quoted} --file {quote_cli_arg(tsv)}"


@dataclass(frozen=True)
class WorkspaceEntry:
    name: str
    path: str
    is_project: bool


def workspace_projects(entries: Sequence[WorkspaceEntry], project_dir: str) -> list[str]:
    """Пути проектов для `validate`: подкаталоги с `.project` + `project_dir`, если он вне."""
    result = [entry.path for entry in entries if entry.is_project]
    if project_dir:
        keys = {os.path.normcase(os.path.normpath(path)) for path in result}
        if os.path.normcase(os.path.normpath(project_dir)) not in keys:
            result.insert(0, project_dir)
    return result


def build_cli_command(
    exe: Path,
    workspace: str,
    command: str,
    jvm_dir: Path,
    installation_vm_args: str,
    project_vm_args: str,
) -> LaunchCommand:
    """`-command` до `-vmargs` ([?] спека §0-Д): всё после `-vmargs` уходит JVM."""
    parts = [
        f'-data "{workspace}"',
        f'-command "{command}"',
        f'-vm "{jvm_dir}"',
        "--launcher.appendVmargs",
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
        CLI_ENCODING_ARGS,
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))
```

- [ ] **Step 4: Сторож, прогон, коммит**

В `CORE` после `"onecstarter.domain.edt",` — `"onecstarter.domain.edt_cli",`.

Run: `uv run pytest tests/unit/test_edt_cli_domain.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

```bash
git add src/onecstarter/domain/edt_cli.py tests/unit/test_edt_cli_domain.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(domain): строки команд CLI EDT и командная строка 1cedtcli.exe"
```

---

### Task 2: `spawn_logged` — порождение с журналом, возвращающее процесс

**Files:**
- Modify: `src/onecstarter/platform_1c/server_spawn.py`
- Modify: `tests/unit/test_server_spawn.py`

**Interfaces:**
- Consumes: `_open_append_shared`, `spawn_server` (существуют).
- Produces: `LoggedProcess(pid: int, process: subprocess.Popen[bytes])`; `spawn_logged(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess`; `spawn_server` — прежняя сигнатура и поведение, реализована через общее ядро.

- [ ] **Step 1: Падающие тесты**

В `tests/unit/test_server_spawn.py` — тем же способом, что соседние тесты: настоящий
дочерний `python.exe`, `NullJob`, уборка через `_kill_if_alive`:

```python
from onecstarter.platform_1c.server_spawn import LoggedProcess, spawn_logged


def test_spawn_logged_returns_process_whose_exit_code_is_readable(tmp_path: Path) -> None:
    """CLI EDT (спека §14.4): Popen остаётся вызывающему — wait() даёт код завершения."""
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments='-c "print('cli out', flush=True); raise SystemExit(7)"',
    )
    log_path = tmp_path / "cli.log"
    result = spawn_logged(command, log_path, NullJob())
    try:
        assert isinstance(result, LoggedProcess)
        assert result.pid == result.process.pid
        assert result.process.wait(timeout=10) == 7
        assert "cli out" in log_path.read_text(encoding="ascii", errors="replace")
    finally:
        _kill_if_alive(result.pid)


def test_spawn_logged_kills_process_when_job_assign_fails(tmp_path: Path) -> None:
    token = f"onecstarter-marker-{uuid.uuid4().hex}"
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments=f'-c "import time; time.sleep(30)  # {token}"',
    )
    with pytest.raises(JobError):
        spawn_logged(command, tmp_path / "cli.log", _FailingJob())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        alive = [
            p for p in psutil.process_iter(attrs=["cmdline"])
            if token in " ".join(p.info.get("cmdline") or [])
        ]
        if not alive:
            break
        time.sleep(0.05)
    assert not alive, "процесс без Job пережил отказ assign()"
```

(Ожидание смерти процесса по токену — тот же приём, что в
`test_spawn_server_kills_process_when_job_assign_fails`; если там есть вспомогательная
функция для этого цикла, использовать её.) Существующие тесты `spawn_server` остаются
зелёными без правок.

- [ ] **Step 2: Реализовать**

В `server_spawn.py` — общее ядро и две обёртки:

```python
@dataclass(frozen=True)
class LoggedProcess:
    pid: int
    process: subprocess.Popen[bytes]


def _spawn_into_job(command: LaunchCommand, log_path: Path, job: Job) -> subprocess.Popen[bytes]:
    fd = _open_append_shared(log_path)
    try:
        process = subprocess.Popen(
            command.command_line,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=fd,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    finally:
        os.close(fd)
    try:
        job.assign(int(process._handle))  # type: ignore[attr-defined]
    except JobError:
        process.kill()
        raise
    return process


def spawn_logged(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess:
    """Как `spawn_server`, но `Popen` остаётся у вызывающего — для `wait()` и `returncode`.

    Для CLI EDT (спека v3, §14.4): команда конечна, её код завершения нужен
    консоли. Сервер же живёт дольше Popen-объекта, потому `spawn_server`
    объект бросает.
    """
    process = _spawn_into_job(command, log_path, job)
    return LoggedProcess(pid=process.pid, process=process)


def spawn_server(command: LaunchCommand, log_path: Path, job: Job) -> int:
    <прежний докстринг>
    process = _spawn_into_job(command, log_path, job)
    pid = process.pid
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        del process
    return pid
```

Комментарии из прежнего тела `spawn_server` (про `assign` до первого ребёнка, про
закрытие родительского дескриптора) переносятся в `_spawn_into_job` дословно.

- [ ] **Step 3: Прогон и коммит**

Run: `uv run pytest tests/unit/test_server_spawn.py tests/unit/test_servers.py tests/ui/test_servers_view.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

```bash
git add src/onecstarter/platform_1c/server_spawn.py tests/unit/test_server_spawn.py
git commit -m "refactor(platform): spawn_logged — общее ядро с spawn_server, Popen остаётся вызывающему"
```

---

### Task 3: Координатор `EdtCli` и занятость workspace в `EdtWorkspace`

**Files:**
- Modify: `src/onecstarter/services/edt.py`
- Create: `src/onecstarter/services/edt_cli.py`
- Modify: `tests/unit/test_edt_workspace.py`
- Create: `tests/unit/test_edt_cli.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.services.edt_cli"`)

**Interfaces:**
- Consumes: `EdtWorkspace`, `EdtStatus`, `EdtLaunchError`, `EdtError` (план 1); `build_cli_command`, `WorkspaceEntry` (Task 1); `spawn_logged`, `LoggedProcess` (Task 2); `Job`, `JobError`; `server_journal.journal_path`, `rotate_journal`, `append_event`; `CLI_EXE`, `effective_jvm`.
- Produces в `services/edt.py`: `EdtWorkspace.mark_cli_busy(project_id)`, `clear_cli_busy(project_id)`, `cli_busy(project_id) -> bool`; `status().cli_busy`; `launch()` → `EdtLaunchError("Workspace занят командой CLI — дождитесь завершения или прервите её")` при занятости; `remove_project()` → `InvalidRequestError("Команда CLI выполняется — дождитесь завершения или прервите её")` при занятости (правка M6 финального ревью: запись — ключ `_runs` и журнала); `update_project()` при занятости разрешён — командная строка уже собрана.
- Produces в `services/edt_cli.py`:

```python
@dataclass(frozen=True)
class CliRun:
    project_id: str
    label: str
    command: str
    pid: int
    process: subprocess.Popen[bytes]
    job: Job
    result_file: str

@dataclass(frozen=True)
class CliResult:
    label: str
    code: int | None          # None — прервано
    interrupted: bool
    result_file: str

def workspace_entries(workspace: str, listdir: Callable[[str], list[str]] = os.listdir, is_file: Callable[[str], bool] = os.path.isfile) -> list[WorkspaceEntry]

class EdtCli:
    def __init__(self, workspace: EdtWorkspace, logs_dir: Path, *, job_factory: Callable[[], Job], spawn: Callable[[LaunchCommand, Path, Job], LoggedProcess] = spawn_logged, is_file: Callable[[Path], bool] = Path.is_file, now: Callable[[], datetime] = datetime.now) -> None
    def unavailable_reason(self, project_id: str) -> str      # "" — можно запускать
    def start(self, project_id: str, label: str, command: str, result_file: str = "") -> CliRun
    def run(self, project_id: str) -> CliRun | None
    def busy(self, project_id: str) -> bool
    def running_count(self) -> int
    def finish(self, run: CliRun, code: int | None) -> None       # сам run: чужой/прерванный — no-op (M5 ревью)
    def interrupt(self, project_id: str) -> None                  # JobError из close() → EdtError, run остаётся (M7 ревью)
    def journal_path(self, project_id: str) -> Path
    def last_result(self, project_id: str) -> CliResult | None
    def log_shutdown(self) -> int
```

- [ ] **Step 1: Занятость в `EdtWorkspace` — падающие тесты**

В `tests/unit/test_edt_workspace.py`:

```python
class TestCliBusy:
    def test_status_reflects_busy(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        assert h.workspace.status(p.id).cli_busy is False
        h.workspace.mark_cli_busy(p.id)
        assert h.workspace.status(p.id).cli_busy is True
        assert h.workspace.cli_busy(p.id) is True
        h.workspace.clear_cli_busy(p.id)
        assert h.workspace.status(p.id).cli_busy is False

    def test_launch_refused_while_busy(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.mark_cli_busy(p.id)
        with pytest.raises(EdtLaunchError, match="занят командой CLI"):
            h.workspace.launch(p.id)
        assert h.spawned == []

    def test_remove_refused_while_busy(self, tmp_path: Path) -> None:
        """Правка M6 финального ревью: запись с живой командой не удаляется (она — ключ
        `EdtCli._runs` и журнала); правка через `update_project` разрешена."""
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.mark_cli_busy(p.id)
        with pytest.raises(InvalidRequestError, match="Команда CLI выполняется"):
            h.workspace.remove_project(p.id)
        assert [x.id for x in h.workspace.projects()] == [p.id]
        h.workspace.update_project(replace(p, name="b"))  # правка — можно
        h.workspace.clear_cli_busy(p.id)
        h.workspace.remove_project(p.id)
        assert h.workspace.projects() == []
```

Реализация в `services/edt.py`: поле `self._cli_busy: set[str] = set()` в `__init__`;

```python
    def mark_cli_busy(self, project_id: str) -> None:
        self._cli_busy.add(project_id)

    def clear_cli_busy(self, project_id: str) -> None:
        self._cli_busy.discard(project_id)

    def cli_busy(self, project_id: str) -> bool:
        return project_id in self._cli_busy
```

в `status()` — `cli_busy=project_id in self._cli_busy`; в `launch()` первой проверкой:

```python
        if project_id in self._cli_busy:
            raise EdtLaunchError(
                "Workspace занят командой CLI — дождитесь завершения или прервите её"
            )
```

в `remove_project()` первой проверкой (правка M6 финального ревью; `update_project`
не трогается — докстринг объясняет, что у живой команды командная строка уже собрана):

```python
        if project_id in self._cli_busy:
            raise InvalidRequestError(
                "Команда CLI выполняется — дождитесь завершения или прервите её"
            )
```

Run: `uv run pytest tests/unit/test_edt_workspace.py -q` — зелёное.

- [ ] **Step 2: `EdtCli` — падающие тесты**

`tests/unit/test_edt_cli.py`:

```python
"""EdtCli: одна команда на запись, журнал с ротацией, прерывание, отказы (спека §14.4)."""

import subprocess
from collections.abc import Callable
from datetime import datetime
from itertools import count
from pathlib import Path

import pytest

from onecstarter.domain.edt import EdtInstallation, EdtProject, EditorResolution
from onecstarter.domain.edt_cli import WorkspaceEntry
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import Job, JobError
from onecstarter.platform_1c.server_spawn import LoggedProcess
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.services.edt_cli import CliResult, EdtCli, workspace_entries
from onecstarter.services.errors import EdtError

EXE_DIR = Path(r"C:\edt\1c-edt-2025.2.6+4-x86_64")
JDK = Path(r"C:\jdk\bin")
INSTALLED = [EdtInstallation("2025.2.6+4", EXE_DIR / "1cedt.exe", JDK, "-Xmx8192m", 17, "products.json")]
NOW = datetime(2026, 9, 10, 12, 0, 0)


class FakeJob:
    """`close_error` — `JobError`, который `close()` поднимает вместо закрытия (M7 ревью)."""

    def __init__(self) -> None:
        self.assigned: list[int] = []
        self.closed = False
        self.close_error: JobError | None = None

    def assign(self, process_handle: int) -> None:
        self.assigned.append(process_handle)

    def pids(self) -> tuple[int, ...]:
        return () if self.closed else (4242,)

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class FakeProcess:
    """Достаточная часть Popen: pid и код завершения для CliRun."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


class Harness:
    def __init__(self, tmp_path: Path, *, cli_exists: bool = True) -> None:
        ids = count(1)
        self.spawned: list[tuple[LaunchCommand, Path]] = []
        self.jobs: list[FakeJob] = []
        self.workspace = EdtWorkspace(
            tmp_path / "edt.json",
            discover=lambda: list(INSTALLED),
            edtstart=lambda: None,
            editors=lambda kind: EditorResolution(None, "", "x"),
            spawn=lambda c: 1,
            activate=lambda p: True,
            open_file=lambda p: None,
            new_id=lambda: f"id-{next(ids)}",
        )
        self.workspace.refresh_installations()

        def spawn(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess:
            # Дописываем, а не перезаписываем: настоящий spawn_logged отдаёт ребёнку
            # хендл FILE_APPEND_DATA и никогда не обрезает журнал (находка ревью Task 3:
            # фейк с write_text стирал события, записанные до spawn).
            self.spawned.append((command, log_path))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as journal:
                journal.write("вывод cli\n")
            return LoggedProcess(pid=4242, process=FakeProcess(4242))  # type: ignore[arg-type]

        def job_factory() -> Job:
            job = FakeJob()
            self.jobs.append(job)
            return job

        self.cli = EdtCli(
            self.workspace,
            tmp_path / "logs" / "edt",
            job_factory=job_factory,
            spawn=spawn,
            is_file=lambda p: cli_exists and p.name == "1cedtcli.exe",
            now=lambda: NOW,
        )

    def project(self, **overrides: object) -> EdtProject:
        values: dict[str, object] = {"id": "", "name": "a", "workspace": r"D:\edt\a", "edt_version": "2025.2.6+4"}
        values.update(overrides)
        return self.workspace.add_project(EdtProject(**values))  # type: ignore[arg-type]


class TestStart:
    def test_start_builds_command_rotates_journal_and_marks_busy(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project(vm_args="-Xmx4g")
        old = h.cli.journal_path(p.id)
        old.parent.mkdir(parents=True)
        old.write_text("прошлый\n", encoding="utf-8")
        run = h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        assert run.pid == 4242 and run.label == "Пересобрать проекты"
        [(command, log_path)] = h.spawned
        assert command.executable == EXE_DIR / "1cedtcli.exe"
        assert '-command "build --yes"' in command.arguments
        assert "-Xmx8192m -Djava.library.path= -Xmx4g" in command.arguments
        assert log_path == h.cli.journal_path(p.id)
        assert (old.parent / f"{p.id}.1.log").read_text(encoding="utf-8") == "прошлый\n"
        text = log_path.read_text(encoding="utf-8")
        assert "[12:00:00] ▶ Пересобрать проекты: build --yes" in text
        assert str(command.executable) in text
        # Порядок в журнале: событие старта и командная строка — ДО вывода ребёнка
        # (спека §14.4; servers.py пишет «запуск:» до spawn_server тем же приёмом).
        assert text.index("▶ Пересобрать проекты") < text.index("вывод cli")
        assert h.workspace.status(p.id).cli_busy is True
        assert h.cli.running_count() == 1

    def test_second_start_on_same_project_refused(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        with pytest.raises(EdtError, match="уже выполняется"):
            h.cli.start(p.id, "Информация по проектам", "project")
        assert len(h.spawned) == 1

    def test_running_edt_refused_before_spawn(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={}))
        assert h.cli.unavailable_reason(p.id) == "Закройте EDT: workspace занят"
        with pytest.raises(EdtError, match="workspace занят"):
            h.cli.start(p.id, "Информация по проектам", "project")
        assert h.spawned == []

    def test_missing_cli_exe_refused(self, tmp_path: Path) -> None:
        h = Harness(tmp_path, cli_exists=False)
        p = h.project()
        assert h.cli.unavailable_reason(p.id) == "В установке 2025.2.6+4 нет 1cedtcli.exe"
        with pytest.raises(EdtError):
            h.cli.start(p.id, "Информация по проектам", "project")

    def test_version_not_installed_refused(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project(edt_version="2024.2.6+7")
        assert h.cli.unavailable_reason(p.id) == "EDT 2024.2.6+7 не найден среди установок"

    def test_spawn_oserror_becomes_edt_error_and_not_busy(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()

        def broken(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess:
            raise OSError("нет файла")

        h.cli = EdtCli(h.workspace, tmp_path / "logs", job_factory=FakeJob, spawn=broken, is_file=lambda p: True, now=lambda: NOW)
        with pytest.raises(EdtError) as excinfo:
            h.cli.start(p.id, "Информация по проектам", "project")
        message = str(excinfo.value)  # спека §8: ошибка с командной строкой (правка I2)
        assert message.startswith("Не удалось запустить 1cedtcli.exe: нет файла.")
        assert "\nКоманда: " in message
        assert f'"{EXE_DIR / "1cedtcli.exe"}" -data "D:\\edt\\a" -command "project"' in message
        assert h.workspace.status(p.id).cli_busy is False
        assert h.cli.running_count() == 0
        journal = h.cli.journal_path(p.id).read_text(encoding="utf-8")
        assert "▶ Информация по проектам: project" in journal  # что пытались запустить
        assert "■ не запущен: OSError" in journal


class TestFinishAndInterrupt:
    def test_finish_writes_code_clears_busy_keeps_result(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        run = h.cli.start(p.id, "Проверить проекты", "validate …", result_file=r"D:\r.tsv")
        h.cli.finish(run, 0)
        assert h.workspace.status(p.id).cli_busy is False
        assert h.cli.run(p.id) is None
        assert h.cli.last_result(p.id) == CliResult("Проверить проекты", 0, False, r"D:\r.tsv")
        assert "[12:00:00] ■ завершено, код 0" in h.cli.journal_path(p.id).read_text(encoding="utf-8")
        assert h.jobs[0].closed is True

    def test_interrupt_closes_job_and_marks_interrupted(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        h.cli.interrupt(p.id)
        assert h.jobs[0].closed is True
        assert h.cli.last_result(p.id) == CliResult("Пересобрать проекты", None, True, "")
        assert h.workspace.status(p.id).cli_busy is False
        assert "■ прервано пользователем" in h.cli.journal_path(p.id).read_text(encoding="utf-8")

    def test_finish_after_interrupt_is_noop(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        run = h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        h.cli.interrupt(p.id)
        h.cli.finish(run, 1)
        assert h.cli.last_result(p.id) == CliResult("Пересобрать проекты", None, True, "")

    def test_interrupt_close_failure_keeps_run_and_raises(self, tmp_path: Path) -> None:
        """`JobError` из `close()` (правка M7 ревью): run остаётся, «прервано» не пишется,
        занятость не снимается, наружу — `EdtError` с меткой команды."""
        h = Harness(tmp_path)
        p = h.project()
        run = h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        h.jobs[0].close_error = JobError("CloseHandle отказал")
        with pytest.raises(EdtError, match="Не удалось прервать «Пересобрать проекты»"):
            h.cli.interrupt(p.id)
        assert h.cli.run(p.id) is run
        assert h.workspace.status(p.id).cli_busy is True
        assert h.cli.last_result(p.id) is None
        assert "прервано" not in h.cli.journal_path(p.id).read_text(encoding="utf-8")
        h.jobs[0].close_error = None  # повтор после устранения причины — штатно
        h.cli.interrupt(p.id)
        assert h.cli.run(p.id) is None

    def test_finish_of_stale_run_keeps_new_run(self, tmp_path: Path) -> None:
        """Прервать → запустить снова → запоздавший код старого run (правка M5 ревью).
        Мутация: убрать `is not run` — новый run закроется чужим кодом."""
        h = Harness(tmp_path)
        p = h.project()
        old = h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        h.cli.interrupt(p.id)
        new = h.cli.start(p.id, "Информация по проектам", "project")
        h.cli.finish(old, 1)
        assert h.cli.run(p.id) is new
        assert h.workspace.status(p.id).cli_busy is True
        assert h.jobs[1].closed is False
        assert h.cli.last_result(p.id) == CliResult("Пересобрать проекты", None, True, "")
        h.cli.finish(new, 0)  # свой же код закрывает новый run штатно
        assert h.cli.run(p.id) is None

    def test_log_shutdown_marks_live_runs(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        assert h.cli.log_shutdown() == 1
        assert "■ прервано выходом из программы" in h.cli.journal_path(p.id).read_text(encoding="utf-8")


class TestJournalOsError:
    """Правка I1 финального ревью плана 2: `OSError` журнала не уходит наружу голым
    и не держит запись занятой. `Harness(tmp_path, logs_dir=...)` подменяет каталог журналов."""

    def test_unwritable_logs_dir_becomes_edt_error_and_nothing_busy(self, tmp_path: Path) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("", encoding="utf-8")
        h = Harness(tmp_path, logs_dir=blocker / "edt")  # каталог под обычным файлом
        p = h.project()
        with pytest.raises(EdtError, match="Не удалось запустить"):
            h.cli.start(p.id, "Информация по проектам", "project")
        assert h.spawned == []
        assert h.workspace.status(p.id).cli_busy is False
        assert h.cli.run(p.id) is None
        assert h.jobs[-1].closed is True

    def test_rotation_failure_is_logged_and_launch_continues(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        current = h.cli.journal_path(p.id)
        current.parent.mkdir(parents=True)
        current.write_text("прошлый\n", encoding="utf-8")
        (current.parent / f"{p.id}.1.log").mkdir()  # Path.replace на каталог падает
        run = h.cli.start(p.id, "Информация по проектам", "project")
        assert run.pid == 4242 and len(h.spawned) == 1
        text = current.read_text(encoding="utf-8")
        assert "ротация журнала не удалась" in text
        assert text.index("ротация журнала не удалась") < text.index("▶ Информация по проектам")

    def test_finish_completes_when_journal_unwritable(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        run = h.cli.start(p.id, "Проверить проекты", "validate …", result_file=r"D:\r.tsv")
        journal = h.cli.journal_path(p.id)
        journal.unlink()
        journal.mkdir()  # каталог на месте файла — open("a") падает PermissionError
        h.cli.finish(run, 0)
        assert h.cli.run(p.id) is None
        assert h.workspace.status(p.id).cli_busy is False
        assert h.jobs[0].closed is True
        assert h.cli.last_result(p.id) == CliResult("Проверить проекты", 0, False, r"D:\r.tsv")

    # test_interrupt_completes_when_journal_unwritable и
    # test_log_shutdown_survives_unwritable_journal — по тому же образцу.


def test_workspace_entries_marks_dot_project(tmp_path: Path) -> None:
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / ".project").write_text("", encoding="utf-8")
    (tmp_path / ".metadata").mkdir()
    (tmp_path / "file.txt").write_text("", encoding="utf-8")
    entries = workspace_entries(str(tmp_path))
    assert entries == [
        WorkspaceEntry(".metadata", str(tmp_path / ".metadata"), False),
        WorkspaceEntry("conf", str(tmp_path / "conf"), True),
    ]


def test_workspace_entries_missing_dir_is_empty(tmp_path: Path) -> None:
    assert workspace_entries(str(tmp_path / "nope")) == []
```

- [ ] **Step 3: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_cli.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Реализовать `services/edt_cli.py`**

```python
"""Команды CLI EDT (спека v3, §14.4): одна команда на запись, журнал, прерывание.

Порождение — `platform_1c/server_spawn.py::spawn_logged` (stdout ребёнка в файл
журнала хендлом `FILE_APPEND_DATA`, процесс в `Job`); журнал и ротация — те же
функции, что у серверов (`services/server_journal.py`). Ожидание кода
завершения — не здесь: `Popen` отдаётся вызывающему (`ui/edt/cli_watch.py`),
а результат возвращается через `finish()`.

Workspace, открытый в EDT, для CLI занят ([Д] спека §0-Д, `WORKSPACE_IN_USE`),
и наоборот — отсюда `unavailable_reason` до запуска и `mark_cli_busy`
в координаторе раздела, который отказывает «Открыть в EDT» на время команды.

`OSError` журнала никогда не уходит наружу голым (правка I1 финального ревью
плана 2; тот же принцип, что у `services/servers.py::start`/`log_event`): в `start`
отказ ротации — best-effort событие и запуск продолжается, отказ записи событий
старта — `EdtError`; в `finish`/`interrupt`/`log_shutdown` события пишутся через
`_log_event`, который глотает `OSError`, — переход состояния (снятие занятости,
закрытие Job, результат) от журнала не зависит.
"""  # noqa: RUF002

import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from onecstarter.domain.edt import CLI_EXE, EdtProject, effective_jvm
from onecstarter.domain.edt_cli import WorkspaceEntry, build_cli_command
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import Job, JobError
from onecstarter.platform_1c.server_spawn import LoggedProcess, spawn_logged
from onecstarter.services.edt import EdtWorkspace
from onecstarter.services.errors import EdtError
from onecstarter.services.server_journal import append_event, journal_path, rotate_journal

__all__ = ["CliResult", "CliRun", "EdtCli", "workspace_entries"]

_log = logging.getLogger("onecstarter.edt_cli")

RUNNING_REASON = "Закройте EDT: workspace занят"
BUSY_REASON = "Команда CLI уже выполняется для этой записи"


@dataclass(frozen=True)
class CliRun:
    project_id: str
    label: str
    command: str
    pid: int
    process: subprocess.Popen[bytes]
    job: Job
    result_file: str


@dataclass(frozen=True)
class CliResult:
    label: str
    code: int | None
    interrupted: bool
    result_file: str


def workspace_entries(
    workspace: str,
    listdir: Callable[[str], list[str]] = os.listdir,
    is_file: Callable[[str], bool] = os.path.isfile,
) -> list[WorkspaceEntry]:
    """Подкаталоги workspace одного уровня с признаком `.project` (спека §14.2)."""
    try:
        names = sorted(listdir(workspace))
    except OSError:
        return []
    entries: list[WorkspaceEntry] = []
    for name in names:
        path = os.path.join(workspace, name)
        if is_file(path):
            continue
        entries.append(WorkspaceEntry(name, path, is_file(os.path.join(path, ".project"))))
    return entries


class EdtCli:
    def __init__(
        self,
        workspace: EdtWorkspace,
        logs_dir: Path,
        *,
        job_factory: Callable[[], Job],
        spawn: Callable[[LaunchCommand, Path, Job], LoggedProcess] = spawn_logged,
        is_file: Callable[[Path], bool] = Path.is_file,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._workspace = workspace
        self._logs_dir = logs_dir
        self._job_factory = job_factory
        self._spawn = spawn
        self._is_file = is_file
        self._now = now
        self._runs: dict[str, CliRun] = {}
        self._results: dict[str, CliResult] = {}

    def unavailable_reason(self, project_id: str) -> str:
        if project_id in self._runs:
            return BUSY_REASON
        if self._workspace.running_pid(project_id) is not None:
            return RUNNING_REASON
        project = self._workspace.project(project_id)
        installation = self._workspace.installation_for(project)
        if installation is None:
            return f"EDT {project.edt_version or '(версия не задана)'} не найден среди установок"
        if not self._is_file(installation.exe.parent / CLI_EXE):
            return f"В установке {installation.version} нет {CLI_EXE}"
        if effective_jvm(project, installation) is None:
            return f"JDK для EDT {installation.version} не найден"
        return ""

    def start(self, project_id: str, label: str, command: str, result_file: str = "") -> CliRun:
        reason = self.unavailable_reason(project_id)
        if reason:
            raise EdtError(reason if reason != BUSY_REASON else "Команда уже выполняется")
        project = self._workspace.project(project_id)
        installation = self._workspace.installation_for(project)
        assert installation is not None  # unavailable_reason проверил
        jvm = effective_jvm(project, installation)
        assert jvm is not None
        launch = build_cli_command(
            installation.exe.parent / CLI_EXE,
            project.workspace,
            command,
            jvm,
            installation.vm_args,
            project.vm_args,
        )
        path = self.journal_path(project_id)
        try:
            rotate_journal(self._logs_dir, project_id)
        except OSError as error:
            # Ротация — best-effort в своём try (как servers.py::start): прошлый
            # журнал может держать переживший процесс, и это не отказ запуска —
            # записи продолжаются в тот же файл. Текст — фактический str(error).
            self._log_event(
                project_id,
                f"ротация журнала не удалась ({error}), записи продолжаются в тот же файл",
            )
        job = self._job_factory()
        try:
            # События — ДО spawn (спека §14.4): ребёнок получает хендл FILE_APPEND_DATA
            # и может написать в журнал раньше этого кода — порядок в файле обязан
            # быть предсказуем независимо от гонки с дочерним процессом.
            append_event(path, f"▶ {label}: {command}", self._now())
            append_event(path, launch.command_line, self._now())
            spawned = self._spawn(launch, path, job)
        except (OSError, JobError) as error:
            # OSError здесь — и отказ записи событий (каталог журналов недоступен),
            # и отказ порождения; оба — отказ запуска с причиной от системы.
            self._close_job(job)
            self._log_event(project_id, f"■ не запущен: {type(error).__name__}")
            # Спека §8: «ошибка с командной строкой» — как ServerError в servers.py::start
            # (правка I2 финального ревью плана 2); секретов в команде CLI нет.
            raise EdtError(
                f"Не удалось запустить {CLI_EXE}: {error}.\nКоманда: {launch.command_line}"
            ) from error
        run = CliRun(project_id, label, command, spawned.pid, spawned.process, job, result_file)
        self._runs[project_id] = run
        self._workspace.mark_cli_busy(project_id)
        return run

    def run(self, project_id: str) -> CliRun | None:
        return self._runs.get(project_id)

    def busy(self, project_id: str) -> bool:
        return project_id in self._runs

    def running_count(self) -> int:
        return len(self._runs)

    def finish(self, run: CliRun, code: int | None) -> None:
        """Код завершения ИМЕННО этого run; чужой или прерванный — молча ничего.

        Сам объект, а не id записи (правка M5 финального ревью плана 2): после
        «Прервать» и повторного запуска на той же записи запоздавший код старого
        run не должен закрыть новый — сверка идентичности живёт здесь, а слот
        вьюхи (`EdtView.on_cli_finished`) лишь дублирует её.
        """
        project_id = run.project_id
        if self._runs.get(project_id) is not run:
            return  # прервано раньше или уже идёт другой run — результат не наш
        del self._runs[project_id]
        text = f"■ завершено, код {code}" if code is not None else "■ завершено, код неизвестен"
        self._log_event(project_id, text)
        self._results[project_id] = CliResult(run.label, code, False, run.result_file)
        self._workspace.clear_cli_busy(project_id)
        self._close_job(run.job)

    def interrupt(self, project_id: str) -> None:
        """Прервать команду: `job.close()` — kill-on-close гасит дерево процесса.

        Отказ `close()` (`JobError`) — `EdtError`, а run ОСТАЁТСЯ в учёте с занятостью
        и без «прервано» в журнале (правка M7 финального ревью плана 2): процесс жив,
        считать его прерванным было бы враньём — принцип `services/servers.py::stop`.
        """
        run = self._runs.get(project_id)
        if run is None:
            return
        try:
            run.job.close()
        except JobError as error:
            raise EdtError(f"Не удалось прервать «{run.label}»: {error}") from error
        del self._runs[project_id]
        self._log_event(project_id, "■ прервано пользователем")
        self._results[project_id] = CliResult(run.label, None, True, "")
        self._workspace.clear_cli_busy(project_id)

    def journal_path(self, project_id: str) -> Path:
        return journal_path(self._logs_dir, project_id)

    def last_result(self, project_id: str) -> CliResult | None:
        return self._results.get(project_id)

    def log_shutdown(self) -> int:
        """Отметить живые команды в журналах при выходе; сами процессы гасит Job."""
        for project_id in list(self._runs):
            self._log_event(project_id, "■ прервано выходом из программы")
        return len(self._runs)

    def _log_event(self, project_id: str, text: str) -> None:
        """Событие в журнал записи; `OSError` глотается — журнал не условие операции.

        В `_log` — только тип ошибки, без пути (инвариант 5).
        """
        try:
            append_event(self.journal_path(project_id), text, self._now())
        except OSError as error:
            _log.warning("журнал CLI EDT недоступен: %s", type(error).__name__)

    @staticmethod
    def _close_job(job: Job) -> None:
        try:
            job.close()
        except JobError:
            return
```

`journal_path(logs_dir, project_id)` из `server_journal` даёт `<id>.log`, `rotate_journal`
— `<id>.1.log` (те же имена, что у серверов; каталог другой — `logs/edt`).

- [ ] **Step 5: Сторож, прогон, мутации, коммит**

В `CORE` после `"onecstarter.services.edt",` — `"onecstarter.services.edt_cli",`.

Run: `uv run pytest tests/unit/test_edt_cli.py tests/unit/test_edt_workspace.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

Мутации (спека §9): 1) в `unavailable_reason` убрать проверку `running_pid` → падает
`test_running_edt_refused_before_spawn` на `spawned == []`; 2) в `start` убрать проверку
`project_id in self._runs` (через `unavailable_reason`) → падает
`test_second_start_on_same_project_refused` на `len(h.spawned) == 1`; 3) (правка I1) события
старта вынести из `try` — падает `test_unwritable_logs_dir_becomes_edt_error_and_nothing_busy`
непойманным `OSError` (`FileExistsError`). Откатить, записать.

```bash
git add src/onecstarter/services/edt.py src/onecstarter/services/edt_cli.py tests/unit/test_edt_cli.py tests/unit/test_edt_workspace.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(services): EdtCli — одна команда на запись, журнал с ротацией, прерывание, занятость workspace (мутации: 2 проверены)"
```

---

### Task 4: UI — ожидание кода завершения и консоль

**Files:**
- Create: `src/onecstarter/ui/edt/cli_watch.py`
- Create: `src/onecstarter/ui/edt/console_panel.py`
- Create: `tests/ui/test_edt_cli_watch.py`
- Create: `tests/ui/test_edt_console.py`

**Interfaces:**
- Consumes: `CliRun` (Task 3); `JournalPanel` (`ui/servers/journal_panel.py`: `show_journal(title, path)`, `refresh()`); `Palette`.
- Produces: `CliWatcher(QObject)` с сигналом `finished(object, object)` (сам `CliRun`, код `int | None`) и методом `watch(run: CliRun)` — сигнал несёт **объект run**, а не id записи: запоздавший сигнал после «Прервать» и повторного запуска не должен закрыть новый run той же записи (находка ревью Task 6); конструктор `CliWatcher(*, spawn: Callable[[Callable[[], None]], None] = _spawn_daemon, parent=None)`; `EdtConsole(QWidget)` с сигналами `interrupt_requested()`, `open_journal_requested()`, `open_result_requested()`, методами `show_run(project_name: str, label: str, state: str, path: Path | None)`, `set_state(state: str)`, `set_buttons(*, interrupt: bool, journal: bool, result: bool)`, `expand()`, `collapse()`, `is_expanded() -> bool`, `apply_palette(palette)`, аксессорами `header_button()`, `title_label()`, `state_label()`, `interrupt_button()`, `journal_button()`, `result_button()`, `journal_panel()`; константы `CONSOLE_TITLE = "Консоль"`, `STATE_RUNNING = "выполняется"`, `STATE_INTERRUPTED = "прервано"`, `STATE_NOT_STARTED = "не запущен"`, функция `state_finished(code: int) -> str` → `"завершено, код N"`.

- [ ] **Step 1: Watcher — тест и реализация**

`tests/ui/test_edt_cli_watch.py`:

```python
from collections.abc import Callable

from onecstarter.services.edt_cli import CliRun
from onecstarter.ui.edt.cli_watch import CliWatcher


class FakeProcess:
    def __init__(self, code: int) -> None:
        self.pid = 1
        self._code = code

    def wait(self, timeout: float | None = None) -> int:
        return self._code


class FakeJob:
    def assign(self, process_handle: int) -> None: ...
    def pids(self) -> tuple[int, ...]:
        return ()
    def close(self) -> None: ...


def _run(code: int) -> CliRun:
    return CliRun("p1", "Пересобрать проекты", "build --yes", 1, FakeProcess(code), FakeJob(), "")  # type: ignore[arg-type]


def test_watch_emits_exit_code(qapp) -> None:  # type: ignore[no-untyped-def]
    watcher = CliWatcher(spawn=lambda task: task())
    got: list[tuple[object, object]] = []
    watcher.finished.connect(lambda run, code: got.append((run, code)))
    run = _run(3)
    watcher.watch(run)
    assert got == [(run, 3)]  # сам объект run, не id — см. интерфейс


def test_wait_failure_emits_none(qapp) -> None:  # type: ignore[no-untyped-def]
    class Broken(FakeProcess):
        def wait(self, timeout: float | None = None) -> int:
            raise OSError("хендл закрыт")

    run = CliRun("p1", "x", "project", 1, Broken(0), FakeJob(), "")  # type: ignore[arg-type]
    watcher = CliWatcher(spawn=lambda task: task())
    got: list[object] = []
    watcher.finished.connect(lambda finished_run, code: got.append(code))
    watcher.watch(run)
    assert got == [None]
```

`src/onecstarter/ui/edt/cli_watch.py`:

```python
"""Ожидание кода завершения команды CLI в потоке-демоне → сигнал Qt (спека §14.4).

Тот же приём, что у фоновых проб (`ui/background.py`): поток ждёт `Popen.wait()`,
результат уходит сигналом в главный поток, где `EdtView` зовёт `EdtCli.finish`.
Отказ `wait()` (хендл закрыт прерыванием) — `None`, не исключение из потока.
"""  # noqa: RUF002

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from onecstarter.services.edt_cli import CliRun


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


class CliWatcher(QObject):
    finished = Signal(object, object)  # CliRun, int | None

    def __init__(
        self,
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._spawn = spawn

    def watch(self, run: CliRun) -> None:
        def wait() -> None:
            try:
                code: int | None = run.process.wait()
            except OSError:
                code = None
            self.finished.emit(run, code)

        self._spawn(wait)
```

Run: `uv run pytest tests/ui/test_edt_cli_watch.py -q` — зелёное.

- [ ] **Step 2: Консоль — падающие тесты**

`tests/ui/test_edt_console.py`:

```python
from pathlib import Path

import pytest

from onecstarter.ui.edt.console_panel import (
    CONSOLE_TITLE,
    STATE_INTERRUPTED,
    STATE_RUNNING,
    EdtConsole,
    state_finished,
)
from onecstarter.ui.theme import DARK


def test_collapsed_by_default_and_toggles(qtbot) -> None:  # type: ignore[no-untyped-def]
    console = EdtConsole(palette=DARK)
    qtbot.addWidget(console)
    assert console.is_expanded() is False
    assert console.journal_panel().isHidden() is True
    assert console.header_button().text() == f"{CONSOLE_TITLE} ▸"
    console.header_button().click()
    assert console.is_expanded() is True
    assert console.journal_panel().isHidden() is False
    assert console.header_button().text() == f"{CONSOLE_TITLE} ▾"
    console.collapse()
    assert console.is_expanded() is False
    console.expand()
    assert console.is_expanded() is True
    assert console.journal_panel().isHidden() is False


def test_show_run_sets_title_state_and_journal(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    console = EdtConsole(palette=DARK)
    qtbot.addWidget(console)
    log = tmp_path / "p.log"
    log.write_text("строка\n", encoding="utf-8")
    console.show_run("Розница", "Пересобрать проекты", STATE_RUNNING, log)
    assert console.title_label().text() == "Розница · Пересобрать проекты"
    assert console.state_label().text() == STATE_RUNNING
    console.journal_panel().refresh()
    assert "строка" in console.journal_panel().text()
    console.set_state(state_finished(0))
    assert console.state_label().text() == "завершено, код 0"


def test_buttons_emit_signals_and_hide(qtbot) -> None:  # type: ignore[no-untyped-def]
    console = EdtConsole(palette=DARK)
    qtbot.addWidget(console)
    got: list[str] = []
    console.interrupt_requested.connect(lambda: got.append("interrupt"))
    console.open_journal_requested.connect(lambda: got.append("journal"))
    console.open_result_requested.connect(lambda: got.append("result"))
    console.set_buttons(interrupt=True, journal=True, result=False)
    assert console.result_button().isHidden() is True
    console.interrupt_button().click()
    console.journal_button().click()
    console.set_buttons(interrupt=False, journal=True, result=True)
    console.result_button().click()
    assert got == ["interrupt", "journal", "result"]
    assert console.interrupt_button().isHidden() is True


def test_state_constants() -> None:
    assert STATE_INTERRUPTED == "прервано"
    assert state_finished(7) == "завершено, код 7"


@pytest.mark.parametrize(
    ("name", "label", "expected"),
    [("Розница", "Сборка", "Розница · Сборка"), ("Розница", "", "Розница"), ("", "", "")],
)
def test_title_drops_empty_parts(qtbot, name: str, label: str, expected: str) -> None:  # type: ignore[no-untyped-def]
    console = EdtConsole(palette=DARK)
    qtbot.addWidget(console)
    console.show_run(name, label, STATE_RUNNING, None)
    assert console.title_label().text() == expected
```

- [ ] **Step 3: Консоль — реализация**

`src/onecstarter/ui/edt/console_panel.py`:

```python
"""Консоль раздела «EDT» (спека v3, §14.5): сворачиваемая обёртка над `JournalPanel`.

Свёрнута по умолчанию — виден только заголовок; раскрывается вьюхой при запуске
команды; свёрнутая вручную остаётся свёрнутой до следующего запуска. Состояние
между сеансами не хранится.
"""  # noqa: RUF002

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from onecstarter.ui.servers.journal_panel import JournalPanel
from onecstarter.ui.theme import Palette

CONSOLE_TITLE = "Консоль"
STATE_RUNNING = "выполняется"
STATE_INTERRUPTED = "прервано"
STATE_NOT_STARTED = "не запущен"


def state_finished(code: int) -> str:
    return f"завершено, код {code}"


class EdtConsole(QWidget):
    interrupt_requested = Signal()
    open_journal_requested = Signal()
    open_result_requested = Signal()

    def __init__(self, *, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = False
        self._header = QToolButton()
        self._header.setAutoRaise(True)
        self._header.clicked.connect(self._toggle)
        self._title = QLabel("")
        self._state = QLabel(STATE_NOT_STARTED)
        self._state.setObjectName("SettingsNote")
        self._interrupt = QPushButton("Прервать")
        self._interrupt.clicked.connect(self.interrupt_requested)
        self._journal = QPushButton("Открыть журнал")
        self._journal.clicked.connect(self.open_journal_requested)
        self._result = QPushButton("Открыть результат")
        self._result.clicked.connect(self.open_result_requested)
        self._panel = JournalPanel(palette=palette)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._header)
        header.addWidget(self._title, 1)
        header.addWidget(self._state)
        header.addWidget(self._interrupt)
        header.addWidget(self._journal)
        header.addWidget(self._result)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self._panel)
        self.set_buttons(interrupt=False, journal=False, result=False)
        self._apply_expanded()

    # --- состояние -------------------------------------------------------

    def show_run(self, project_name: str, label: str, state: str, path: Path | None) -> None:
        # Пустые части опускаются: «прошлый запуск» без метки и пустое состояние
        # консоли не должны давать « · » (используется `_sync_console`, Task 6).
        self._title.setText(" · ".join(part for part in (project_name, label) if part))
        self._state.setText(state)
        self._panel.show_journal(project_name, path)

    def set_state(self, state: str) -> None:
        self._state.setText(state)

    def set_buttons(self, *, interrupt: bool, journal: bool, result: bool) -> None:
        self._interrupt.setVisible(interrupt)
        self._journal.setVisible(journal)
        self._result.setVisible(result)

    def expand(self) -> None:
        self._expanded = True
        self._apply_expanded()

    def collapse(self) -> None:
        self._expanded = False
        self._apply_expanded()

    def is_expanded(self) -> bool:
        return self._expanded

    def apply_palette(self, palette: Palette) -> None:
        self._panel.apply_palette(palette)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._apply_expanded()

    def _apply_expanded(self) -> None:
        self._header.setText(f"{CONSOLE_TITLE} {'▾' if self._expanded else '▸'}")
        self._panel.setVisible(self._expanded)

    # --- доступ ----------------------------------------------------------

    def header_button(self) -> QToolButton:
        return self._header

    def title_label(self) -> QLabel:
        return self._title

    def state_label(self) -> QLabel:
        return self._state

    def interrupt_button(self) -> QPushButton:
        return self._interrupt

    def journal_button(self) -> QPushButton:
        return self._journal

    def result_button(self) -> QPushButton:
        return self._result

    def journal_panel(self) -> JournalPanel:
        return self._panel
```

`JournalPanel.showEvent`/`hideEvent` включают и выключают таймер обновления —
свёрнутая консоль файл не читает.

- [ ] **Step 4: Прогон и коммит**

Run: `uv run pytest tests/ui/test_edt_cli_watch.py tests/ui/test_edt_console.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

```bash
git add src/onecstarter/ui/edt/cli_watch.py src/onecstarter/ui/edt/console_panel.py tests/ui/test_edt_cli_watch.py tests/ui/test_edt_console.py
git commit -m "feat(ui): ожидание кода команды CLI в потоке-демоне и сворачиваемая консоль над JournalPanel"
```

---

### Task 5: UI — диалоги `import` и `validate`

**Files:**
- Create: `src/onecstarter/ui/edt/cli_import_dialog.py`
- Create: `src/onecstarter/ui/edt/cli_validate_dialog.py`
- Create: `tests/ui/test_edt_cli_dialogs.py`

**Interfaces:**
- Consumes: `ImportForm`, `cli_import_args`, `CliQuoteError` (Task 1); `russian_button_box`, `ButtonKind`; `browse_for_directory` (`ui/edt/dialog.py`, план 1).
- Produces: `CliImportDialog(*, choose_directory=browse_for_directory, parent=None)` с `form() -> ImportForm`, `ok_button()`, `error_text()`, аксессорами `existing_radio()`, `xml_radio()`, `existing_dir_edit()`, `xml_dir_edit()`, `project_dir_edit()`, `project_name_edit()`, `base_project_edit()`, `platform_version_edit()`, `build_checkbox()`; `CliValidateDialog(paths: Sequence[str], initial_dir: str, default_name: str, *, choose_save: Callable[[str], str] = browse_for_tsv, exists: Callable[[str], bool] = os.path.exists, parent=None)` с `selected_paths() -> list[str]`, `result_file() -> str`, `ok_button()`, `error_text()`, `list_widget()`, `file_edit()`, `browse_button()`; `browse_for_tsv(initial: str) -> str` (диалог сохранения, фильтр `TSV (*.tsv)`).

- [ ] **Step 1: Падающие тесты**

`tests/ui/test_edt_cli_dialogs.py`:

```python
from PySide6.QtCore import Qt

from onecstarter.domain.edt_cli import ImportForm
from onecstarter.ui.edt.cli_import_dialog import CliImportDialog
from onecstarter.ui.edt.cli_validate_dialog import CliValidateDialog


class TestImportDialog:
    def test_existing_variant(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        assert dialog.existing_radio().isChecked() is True
        assert dialog.ok_button().isEnabled() is False
        dialog.existing_dir_edit().setText(r"D:\src\proj")
        assert dialog.ok_button().isEnabled() is True
        assert dialog.form() == ImportForm(existing_project_dir=r"D:\src\proj")

    def test_xml_variant_fields(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        dialog.xml_radio().setChecked(True)
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

    def test_variant_switch_clears_other_fields_from_form(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        dialog.existing_dir_edit().setText(r"D:\a")
        dialog.xml_radio().setChecked(True)
        dialog.xml_dir_edit().setText(r"D:\xml")
        dialog.project_dir_edit().setText(r"D:\new")
        assert dialog.form().existing_project_dir == ""
        assert dialog.error_text() == ""

    def test_single_quote_reports_error(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        dialog.existing_dir_edit().setText(r"D:\O'Reilly")
        assert dialog.ok_button().isEnabled() is False
        assert "Кавычка в значении недопустима" in dialog.error_text()

    def test_browse_fills_active_field(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: r"D:\picked")
        qtbot.addWidget(dialog)
        dialog.existing_browse().click()
        assert dialog.existing_dir_edit().text() == r"D:\picked"


PATHS = [r"D:\ws\conf", r"D:\ws\conf.ext"]


def _dirs_only(path: str) -> bool:
    """Фейк `os.path.exists`: каталоги есть, файла результата нет (правка M4 финального
    ревью: диалог проверяет и каталог результата — `exists=lambda p: False` его отверг бы)."""
    return not path.lower().endswith(".tsv")


class TestValidateDialog:
    def test_all_checked_and_default_file(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            PATHS, r"C:\Users\u\Documents", "validate-a-20260910-1200.tsv",
            choose_save=lambda initial: "", exists=_dirs_only,
        )
        qtbot.addWidget(dialog)
        assert dialog.selected_paths() == PATHS
        assert dialog.file_edit().text() == r"C:\Users\u\Documents\validate-a-20260910-1200.tsv"
        assert dialog.ok_button().isEnabled() is True

    def test_nothing_checked_disables_ok(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(PATHS, r"C:\d", "r.tsv", choose_save=lambda i: "", exists=_dirs_only)
        qtbot.addWidget(dialog)
        for row in range(2):
            dialog.list_widget().item(row).setCheckState(Qt.CheckState.Unchecked)
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == "Не выбран ни один проект"

    def test_existing_file_rejected(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(PATHS, r"C:\d", "r.tsv", choose_save=lambda i: "", exists=lambda p: True)
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == "Файл уже существует — CLI откажет; выберите другое имя"

    def test_browse_replaces_file(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(PATHS, r"C:\d", "r.tsv", choose_save=lambda i: r"E:\out\x.tsv", exists=_dirs_only)
        qtbot.addWidget(dialog)
        dialog.browse_button().click()
        assert dialog.result_file() == r"E:\out\x.tsv"

    def test_empty_paths_list(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog([], r"C:\d", "r.tsv", choose_save=lambda i: "", exists=_dirs_only)
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False

    def test_single_quote_in_path_reports_error(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog([r"D:\O'Reilly\conf"], r"C:\d", "r.tsv", choose_save=lambda i: "", exists=_dirs_only)
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False
        assert "Кавычка в значении недопустима" in dialog.error_text()

    def test_missing_result_dir_rejected(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Правка M4 финального ревью: `Documents` может не существовать (OneDrive KFM),
        CLI каталог для TSV не создаёт — проверка каталога тем же `exists`, что и файла."""
        seen: list[str] = []

        def exists(path: str) -> bool:
            seen.append(path)
            return False

        dialog = CliValidateDialog(PATHS, r"C:\nope\Documents", "r.tsv", choose_save=lambda i: "", exists=exists)
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == "Каталог результата не существует"
        assert r"C:\nope\Documents" in seen  # проверялся именно родитель файла
```

- [ ] **Step 2: Реализовать `cli_import_dialog.py`**

```python
"""Диалог `import` CLI EDT (спека §14.2): существующий проект или файлы XML."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from onecstarter.domain.edt_cli import ImportForm, cli_import_args
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.edt.dialog import browse_for_directory


class CliImportDialog(QDialog):
    def __init__(
        self,
        *,
        choose_directory: Callable[[], str] = browse_for_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импортировать проект (CLI EDT)")
        self._choose_directory = choose_directory
        self._existing = QRadioButton("Существующий проект EDT")
        self._xml = QRadioButton("Файлы конфигурации XML")
        self._existing.setChecked(True)
        self._existing_dir = QLineEdit()
        self._existing_browse = QPushButton("Обзор…")
        self._existing_browse.clicked.connect(lambda: self._browse_into(self._existing_dir))
        self._xml_dir = QLineEdit()
        self._xml_browse = QPushButton("Обзор…")
        self._xml_browse.clicked.connect(lambda: self._browse_into(self._xml_dir))
        self._project_dir = QLineEdit()
        self._project_dir.setPlaceholderText("каталог нового проекта — или имя ниже")
        self._project_dir_browse = QPushButton("Обзор…")
        self._project_dir_browse.clicked.connect(lambda: self._browse_into(self._project_dir))
        self._project_name = QLineEdit()
        self._project_name.setPlaceholderText("имя нового проекта в workspace")
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

        form = QFormLayout()
        form.addRow(self._existing)
        form.addRow("Каталог проекта", self._row(self._existing_dir, self._existing_browse))
        form.addRow(self._xml)
        form.addRow("Каталог файлов XML", self._row(self._xml_dir, self._xml_browse))
        form.addRow("Каталог нового проекта", self._row(self._project_dir, self._project_dir_browse))
        form.addRow("Имя нового проекта", self._project_name)
        form.addRow("Базовый проект", self._base_project)
        form.addRow("Версия платформы", self._platform_version)
        form.addRow("", self._build)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)

        for widget in (self._existing_dir, self._xml_dir, self._project_dir, self._project_name,
                       self._base_project, self._platform_version):
            widget.textChanged.connect(self._refresh)
        self._existing.toggled.connect(self._refresh)
        self._build.toggled.connect(self._refresh)
        self._refresh()

    def form(self) -> ImportForm:
        if self._existing.isChecked():
            return ImportForm(existing_project_dir=self._existing_dir.text().strip())
        return ImportForm(
            configuration_files=self._xml_dir.text().strip(),
            project_dir=self._project_dir.text().strip(),
            project_name=self._project_name.text().strip(),
            base_project_name=self._base_project.text().strip(),
            platform_version=self._platform_version.text().strip(),
            build_after=self._build.isChecked(),
        )

    def _refresh(self, *_args: object) -> None:
        xml = self._xml.isChecked()
        for widget in (self._xml_dir, self._xml_browse, self._project_dir, self._project_dir_browse,
                       self._project_name, self._base_project, self._platform_version, self._build):
            widget.setEnabled(xml)
        for widget in (self._existing_dir, self._existing_browse):
            widget.setEnabled(not xml)
        try:
            cli_import_args(self.form())
        except ValueError as error:
            self._error.setText(str(error))
            self.ok_button().setEnabled(False)
            return
        self._error.setText("")
        self.ok_button().setEnabled(True)

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

`cli_import_args` на пустой форме поднимает `ValueError("Укажите каталог проекта…")` —
это и есть текст ошибки до ввода; тест `test_existing_variant` проверяет только
`isEnabled() is False`.

- [ ] **Step 3: Реализовать `cli_validate_dialog.py`**

```python
"""Диалог `validate` CLI EDT (спека §14.2): перечень проектов и файл TSV."""

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from onecstarter.domain.edt_cli import cli_validate_args
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

EXISTS_ERROR = "Файл уже существует — CLI откажет; выберите другое имя"
NO_DIR_ERROR = "Каталог результата не существует"  # правка M4 финального ревью


def browse_for_tsv(initial: str) -> str:
    """Диалог сохранения TSV; пустая строка — отмена."""
    return QFileDialog.getSaveFileName(None, "Файл результата", initial, "TSV (*.tsv)")[0]


class CliValidateDialog(QDialog):
    def __init__(
        self,
        paths: Sequence[str],
        initial_dir: str,
        default_name: str,
        *,
        choose_save: Callable[[str], str] = browse_for_tsv,
        exists: Callable[[str], bool] = os.path.exists,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Проверить проекты (CLI EDT)")
        self._paths = list(paths)
        self._exists = exists
        self._choose_save = choose_save
        self._list = QListWidget()
        for path in self._paths:
            item = QListWidgetItem(path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._refresh)
        self._file = QLineEdit(str(Path(initial_dir) / default_name))
        self._file.textChanged.connect(self._refresh)
        self._browse = QPushButton("Обзор…")
        self._browse.clicked.connect(self._pick)
        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self._file, 1)
        file_layout.addWidget(self._browse)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Проекты для проверки:"))
        layout.addWidget(self._list, 1)
        layout.addWidget(QLabel("Файл результата (TSV):"))
        layout.addWidget(file_row)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)
        self.resize(640, 420)
        self._refresh()

    def selected_paths(self) -> list[str]:
        return [
            path
            for index, path in enumerate(self._paths)
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def result_file(self) -> str:
        return self._file.text().strip()

    def _refresh(self, *_args: object) -> None:
        error = ""
        file = self.result_file()
        if not self.selected_paths():
            error = "Не выбран ни один проект"
        elif not file:
            error = "Укажите файл результата"
        elif self._exists(file):
            error = EXISTS_ERROR
        elif not self._exists(str(Path(file).parent)):
            # M4 ревью: каталог по умолчанию может не существовать (OneDrive KFM),
            # CLI каталог для TSV не создаёт — отказ здесь, не кодом после запуска.
            error = NO_DIR_ERROR
        else:
            try:
                cli_validate_args(self.selected_paths(), file)
            except ValueError as validation_error:  # CliQuoteError — подкласс; как в import-диалоге
                error = str(validation_error)
        self._error.setText(error)
        self.ok_button().setEnabled(not error)

    def _pick(self) -> None:
        chosen = self._choose_save(self._file.text())
        if chosen:
            self._file.setText(chosen)

    # --- доступ ---
    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]

    def error_text(self) -> str:
        return self._error.text()

    def list_widget(self) -> QListWidget:
        return self._list

    def file_edit(self) -> QLineEdit:
        return self._file

    def browse_button(self) -> QPushButton:
        return self._browse
```

- [ ] **Step 4: Прогон и коммит**

Run: `uv run pytest tests/ui/test_edt_cli_dialogs.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

```bash
git add src/onecstarter/ui/edt/cli_import_dialog.py src/onecstarter/ui/edt/cli_validate_dialog.py tests/ui/test_edt_cli_dialogs.py
git commit -m "feat(ui): диалоги CLI EDT — import с двумя вариантами и validate с перечнем проектов и TSV"
```

---

### Task 6: Подменю CLI во вьюхе, консоль под деревом, сборка и гейт выхода

**Files:**
- Modify: `src/onecstarter/services/edt.py` (`open_path`)
- Modify: `src/onecstarter/ui/edt/view.py`
- Modify: `src/onecstarter/ui/app.py`
- Modify: `tests/ui/test_edt_view.py`
- Modify: `tests/ui/test_app.py`

**Interfaces:**
- Consumes: `EdtCli`, `CliRun`, `CliResult`, `workspace_entries` (Task 3); `CliWatcher`, `EdtConsole`, состояния (Task 4); диалоги (Task 5); `cli_build_args`, `cli_project_args`, `cli_import_args`, `cli_validate_args`, `workspace_projects` (Task 1); `spawn_logged` (Task 2); `ServerJob`; `_confirm_quit_with_servers` (`app.py`); `ui/edt/icons.py::running_icon` (план 1, Task 21) — по его образцу `cli_busy_icon(palette)`: закрашенный круг цветом `palette.accent`, 16 px; `tree_model._project_row` ставит его в ячейку имени при `status.cli_busy` (и не ставит ▶), подсказка дополняется `CLI_BUSY_HINT`; `ui/edt/view.py::_on_current_changed` (план 1, Task 22) — общий слот смены выделения, куда добавляется `_sync_console()`.
- Produces: `EdtWorkspace.open_path(path: str)`; `EdtView(cli: EdtCli | None = None, watcher: CliWatcher | None = None, documents_dir: str = str(Path.home() / "Documents"))`; методы `cli_build(project_id)`, `cli_import(project_id)`, `cli_validate(project_id)`, `cli_project(project_id)`, `on_cli_finished(run, code)` (сам `CliRun` от наблюдателя), `interrupt_current_cli()`, `console() -> EdtConsole`, `tsv_dir() -> str` (каталог следующего диалога `validate`; правка M4); константы `MENU_CLI = "CLI"`, `CLI_BUILD = "Пересобрать проекты"`, `CLI_IMPORT = "Импортировать проект…"`, `CLI_VALIDATE = "Проверить проекты…"`, `CLI_PROJECT = "Информация по проектам"`, `CLI_BUSY_HINT = "Выполняется команда CLI"`; в `app.py` — `_confirm_quit_with_cli(running_count, ask) -> bool`.

- [ ] **Step 1: Падающие тесты вьюхи**

В `tests/ui/test_edt_view.py` — расширить `Harness`: поля `self.jobs`, `self.cli`, `self.watcher`,
`self.exit_codes: dict[str, int] = {}`; после `self.workspace.refresh_installations()`:

```python
        from onecstarter.platform_1c.server_spawn import LoggedProcess
        from onecstarter.services.edt_cli import EdtCli
        from onecstarter.ui.edt.cli_watch import CliWatcher

        self.cli_spawned: list[LaunchCommand] = []

        def spawn_cli(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess:
            self.cli_spawned.append(command)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("вывод\n", encoding="utf-8")
            return LoggedProcess(pid=9, process=FakeProcess(self.exit_codes.get("code", 0)))  # type: ignore[arg-type]

        self.cli = EdtCli(
            self.workspace, tmp_path / "logs" / "edt",
            job_factory=FakeJob, spawn=spawn_cli, is_file=lambda p: True,
        )
        self.pending: list[Callable[[], None]] = []
        self.watcher = CliWatcher(spawn=self.pending.append)
```

`FakeJob`, `FakeProcess` — как в `tests/unit/test_edt_cli.py` (скопировать в этот файл:
модули тестов друг друга не импортируют). `view()` передаёт `cli=self.cli, watcher=self.watcher,
documents_dir=str(tmp_path / "Documents")`, `confirm` по умолчанию.

Тесты:

```python
from onecstarter.ui.edt.console_panel import STATE_INTERRUPTED, STATE_RUNNING
from onecstarter.ui.edt.view import (
    CLI_BUILD, CLI_BUSY_HINT, CLI_IMPORT, CLI_PROJECT, CLI_VALIDATE, MENU_CLI,
)


def _cli_menu(view: EdtView, project_id: str) -> QMenu:
    menu = view.build_menu("project", project_id)
    action = next(a for a in menu.actions() if a.text() == MENU_CLI)
    return action.menu()


def test_cli_submenu_items_enabled_on_idle_project(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    assert _actions(_cli_menu(view, p.id)) == {
        CLI_BUILD: True, CLI_IMPORT: True, CLI_VALIDATE: True, CLI_PROJECT: True,
    }


def test_cli_submenu_disabled_when_edt_running(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.on_scan(EdtScan(running={p.id: 77}, present={}))
    menu = view.build_menu("project", p.id)
    cli = next(a for a in menu.actions() if a.text() == MENU_CLI)
    assert cli.isEnabled() is False
    assert cli.toolTip() == "Закройте EDT: workspace занят"


def test_cli_build_confirms_starts_and_expands_console(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    asked: list[str] = []
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: asked.append(text) or True)
    assert view.console().is_expanded() is False
    view.cli_build(p.id)
    assert asked == ["Пересобрать все проекты workspace «a»? Это займёт время"]
    assert '-command "build --yes"' in harness.cli_spawned[0].arguments
    assert view.console().is_expanded() is True
    assert view.console().state_label().text() == STATE_RUNNING
    assert view.console().title_label().text() == "a · Пересобрать проекты"
    assert view.console().interrupt_button().isHidden() is False
    assert not view.model().item(0, 0).icon().isNull()  # значок «выполняется команда CLI»
    assert CLI_BUSY_HINT in view.model().item(0, 0).toolTip()
    open_edt = next(a for a in view.build_menu("project", p.id).actions() if a.text() == MENU_OPEN_EDT)
    assert open_edt.isEnabled() is False and open_edt.toolTip() == CLI_BUSY_HINT
    assert len(harness.pending) == 1


def test_cli_finish_updates_console_and_menu(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    harness.exit_codes["code"] = 3
    view.cli_build(p.id)
    harness.pending[0]()  # поток-демон «дождался»
    assert view.console().state_label().text() == "завершено, код 3"
    assert view.console().interrupt_button().isHidden() is True
    assert view.model().item(0, 0).icon().isNull()
    assert _actions(_cli_menu(view, p.id))[CLI_PROJECT] is True


def test_cli_project_without_confirm(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: (_ for _ in ()).throw(AssertionError("не должен спрашивать")))
    view.cli_project(p.id)
    assert '-command "project"' in harness.cli_spawned[0].arguments


def test_cli_interrupt_confirms_and_marks(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    view.cli_build(p.id)
    view.console().interrupt_button().click()
    assert harness.jobs[-1].closed is True
    assert view.console().state_label().text() == STATE_INTERRUPTED
    assert harness.workspace.status(p.id).cli_busy is False


def test_cli_validate_builds_paths_and_result_button(harness: Harness, qtbot, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ws = tmp_path / "ws"
    (ws / "conf").mkdir(parents=True)
    (ws / "conf" / ".project").write_text("", encoding="utf-8")
    p = _add(harness, "a", workspace=str(ws))
    view = harness.view()
    qtbot.addWidget(view)

    initial_name = ""

    def run_dialog(dialog):  # type: ignore[no-untyped-def]
        nonlocal initial_name
        initial_name = Path(dialog.file_edit().text()).name
        dialog.file_edit().setText(str(tmp_path / "out.tsv"))
        return True

    monkeypatch.setattr(view, "_run_dialog", run_dialog)
    view.cli_validate(p.id)
    args = harness.cli_spawned[0].arguments
    assert f"validate --project-list '{ws / 'conf'}' --file '{tmp_path / 'out.tsv'}'" in args
    assert re.fullmatch(r"validate-a-\d{8}-\d{4}\.tsv", initial_name)  # штамп yyyyMMdd-HHmm
    (tmp_path / "out.tsv").write_text("", encoding="utf-8")
    harness.pending[0]()
    assert view.console().result_button().isHidden() is False
    view.console().result_button().click()
    assert harness.opened[-1] == str(tmp_path / "out.tsv")


def test_cli_import_runs_dialog_form(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)

    def run_dialog(dialog):  # type: ignore[no-untyped-def]
        dialog.existing_dir_edit().setText(r"D:\src\proj")
        return True

    monkeypatch.setattr(view, "_run_dialog", run_dialog)
    view.cli_import(p.id)
    assert "-command \"import --project 'D:\\src\\proj'\"" in harness.cli_spawned[0].arguments


def test_stale_watcher_signal_does_not_finish_new_run(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Прервать → запустить снова → приходит сигнал старого run: новый run жив."""
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    view.cli_build(p.id)
    stale = harness.pending[0]
    view.console().interrupt_button().click()
    view.cli_project(p.id)
    stale()  # поток-демон старого run «дождался» уже после нового запуска
    assert harness.cli.run(p.id) is not None
    assert harness.jobs[-1].closed is False
    assert view.console().state_label().text() == STATE_RUNNING


def test_cli_error_is_shown(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a", edt_version="2024.2.6+7")
    view = harness.view()
    qtbot.addWidget(view)
    view.cli_project(p.id)
    assert harness.errors == ["EDT 2024.2.6+7 не найден среди установок"]
    assert view.console().is_expanded() is False


def test_selecting_project_shows_its_journal_without_expanding(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    a = _add(harness, "a")
    b = _add(harness, "b")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    view.cli_build(a.id)
    harness.pending[0]()
    view.console().collapse()
    _select(view, b.id)
    assert view.console().title_label().text() == ""
    _select(view, a.id)
    assert view.console().title_label().text() == "a · Пересобрать проекты"
    assert view.console().is_expanded() is False
```

- [ ] **Step 2: Реализовать во вьюхе**

`services/edt.py` — метод рядом с `open_folder`:

```python
    def open_path(self, path: str) -> None:
        try:
            self._open_file(path)
        except OSError as error:
            raise EdtError(f"Не удалось открыть: {error}") from error
```

`ui/edt/view.py` — импорты:

```python
from datetime import datetime

from onecstarter.domain.edt_cli import (
    cli_build_args, cli_import_args, cli_project_args, cli_validate_args, workspace_projects,
)
from onecstarter.services.edt_cli import CliRun, EdtCli, workspace_entries
from onecstarter.ui.edt.cli_import_dialog import CliImportDialog
from onecstarter.ui.edt.cli_validate_dialog import CliValidateDialog
from onecstarter.ui.edt.cli_watch import CliWatcher
from onecstarter.ui.edt.console_panel import (
    STATE_INTERRUPTED, STATE_NOT_STARTED, STATE_RUNNING, EdtConsole, state_finished,
)
```

Константы:

```python
MENU_CLI = "CLI"
CLI_BUILD = "Пересобрать проекты"
CLI_IMPORT = "Импортировать проект…"
CLI_VALIDATE = "Проверить проекты…"
CLI_PROJECT = "Информация по проектам"
CLI_BUSY_HINT = "Выполняется команда CLI"
```

Конструктор — параметры `cli: EdtCli | None = None`, `watcher: CliWatcher | None = None`,
`documents_dir: str = str(Path.home() / "Documents")`; поля; консоль под деревом:

```python
        self._cli = cli
        self._watcher = watcher
        self._documents_dir = documents_dir
        self._last_tsv_dir = documents_dir
        self._console_project: str | None = None
        self._console = EdtConsole(palette=palette)
        self._console.interrupt_requested.connect(self.interrupt_current_cli)
        self._console.open_journal_requested.connect(self._open_console_journal)
        self._console.open_result_requested.connect(self._open_console_result)
        if watcher is not None:
            watcher.finished.connect(self.on_cli_finished)
        ...
        layout.addWidget(self._tree, 1)
        layout.addWidget(self._console)
```

В `_on_current_changed` (Task 22 плана 1 — общий слот, уже подключён к
`selectionModel().currentChanged` после каждого `setModel`) добавить вызов
`self._sync_console()` после `self._sync_panel()`.

В `ui/edt/tree_model.py::_project_row` — ветка `status.cli_busy`: `name.setIcon(cli_busy_icon(palette))`
и `tooltip += f"\n{CLI_BUSY_HINT}"` (ветка `running_pid` остаётся первой: запущенный EDT
важнее). В `ui/edt/icons.py`:

```python
def cli_busy_icon(palette: Palette) -> QIcon:
    """Закрашенный круг цветом акцента — выполняется команда CLI (спека §14.6)."""
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(palette.accent))
    painter.drawEllipse(3, 3, 10, 10)
    painter.end()
    return QIcon(pixmap)
```

с тестом в `tests/ui/test_edt_icons.py` (пиксель (8, 8) — цвет акцента, угол прозрачен)
и тестом модели `test_cli_busy_icon_after_mark` в `tests/ui/test_edt_tree_model.py`
(`ws.mark_cli_busy(p.id)` → значок не пуст, `CLI_BUSY_HINT` в подсказке).

В `_fill_project_menu` — после «Открыть в Проводнике»; и «Открыть в EDT» неактивен при `cli_busy`:

```python
        if status.cli_busy:
            open_edt.setEnabled(False)
            open_edt.setToolTip(CLI_BUSY_HINT)
        ...
        if self._cli is not None:
            cli_menu = menu.addMenu(MENU_CLI)
            cli_menu.setToolTipsVisible(True)
            reason = self._cli.unavailable_reason(project.id)
            cli_action = cli_menu.menuAction()
            if reason:
                cli_action.setEnabled(False)
                cli_action.setToolTip(reason if not status.cli_busy else CLI_BUSY_HINT)
            cli_menu.addAction(CLI_BUILD, lambda: self.cli_build(project.id))
            cli_menu.addAction(CLI_IMPORT, lambda: self.cli_import(project.id))
            cli_menu.addAction(CLI_VALIDATE, lambda: self.cli_validate(project.id))
            cli_menu.addAction(CLI_PROJECT, lambda: self.cli_project(project.id))
```

Команды:

```python
    # --- CLI ------------------------------------------------------------------

    def cli_build(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        question = f"Пересобрать все проекты workspace «{project.name}»? Это займёт время"
        if self._confirm(self, "Пересборка", question):
            self._start_cli(project_id, CLI_BUILD, cli_build_args())

    def cli_project(self, project_id: str) -> None:
        self._start_cli(project_id, CLI_PROJECT, cli_project_args())

    def cli_import(self, project_id: str) -> None:
        dialog = CliImportDialog(choose_directory=self._choose_directory, parent=self)
        if self._run_dialog(dialog):
            self._start_cli(project_id, CLI_IMPORT.rstrip("…"), cli_import_args(dialog.form()))

    def cli_validate(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        paths = workspace_projects(workspace_entries(project.workspace), project.project_dir)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        dialog = CliValidateDialog(
            paths, self._last_tsv_dir, f"validate-{project.name}-{stamp}.tsv", parent=self
        )
        if not self._run_dialog(dialog):
            return
        tsv = dialog.result_file()
        self._last_tsv_dir = str(Path(tsv).parent)
        self._start_cli(
            project_id,
            CLI_VALIDATE.rstrip("…"),
            cli_validate_args(dialog.selected_paths(), tsv),
            result_file=tsv,
        )

    def _start_cli(self, project_id: str, label: str, command: str, result_file: str = "") -> None:
        if self._cli is None:
            return
        try:
            run = self._cli.start(project_id, label, command, result_file)
        except ServicesError as error:
            self._show_error(str(error))
            return
        project = self._workspace.project(project_id)
        self._console_project = project_id
        self._console.show_run(project.name, label, STATE_RUNNING, self._cli.journal_path(project_id))
        self._console.set_buttons(interrupt=True, journal=True, result=False)
        self._console.expand()
        if self._watcher is not None:
            self._watcher.watch(run)
        self.rebuild()

    def on_cli_finished(self, run: object, code: object) -> None:
        """Код завершения от наблюдателя. Запоздавший сигнал чужого run игнорируется.

        После «Прервать» `Popen.wait()` в потоке-демоне возвращается не сразу;
        если пользователь успел запустить на той же записи новую команду,
        сигнал старого run не должен закрыть новый (находка ревью Task 6).
        """
        if self._cli is None or not isinstance(run, CliRun):
            return
        if self._cli.run(run.project_id) is not run:
            return  # ту же сверку делает и EdtCli.finish (M5 ревью) — здесь ради консоли
        project_id = run.project_id
        self._cli.finish(run, code if isinstance(code, int) else None)
        if self._console_project == project_id:
            self._refresh_console_state(project_id)
        self.rebuild()

    def interrupt_current_cli(self) -> None:
        if self._cli is None or self._console_project is None:
            return
        run = self._cli.run(self._console_project)
        if run is None:
            return
        question = (
            f"Прервать «{run.label}»? Сборка останется незавершённой, "
            "EDT пересоберёт при следующем открытии"
        )
        if not self._confirm(self, "Прерывание", question):
            return
        self._cli.interrupt(self._console_project)
        self._refresh_console_state(self._console_project)
        self.rebuild()

    def _refresh_console_state(self, project_id: str) -> None:
        assert self._cli is not None
        result = self._cli.last_result(project_id)
        if result is None:
            self._console.set_state(STATE_NOT_STARTED)
            self._console.set_buttons(interrupt=False, journal=True, result=False)
            return
        if result.interrupted:
            self._console.set_state(STATE_INTERRUPTED)
        elif result.code is None:
            self._console.set_state("завершено, код неизвестен")
        else:
            self._console.set_state(state_finished(result.code))
        has_result = bool(result.result_file) and result.code == 0 and Path(result.result_file).exists()
        self._console.set_buttons(interrupt=False, journal=True, result=has_result)

    def _sync_console(self) -> None:
        """Выбор записи переключает журнал консоли, не раскрывая её (спека §14.5)."""
        if self._cli is None:
            return
        current = self.current()
        if current is None or current[0] != KIND_PROJECT:
            return
        project_id = current[1]
        run = self._cli.run(project_id)
        result = self._cli.last_result(project_id)
        path = self._cli.journal_path(project_id)
        project = self._workspace.project(project_id)
        self._console_project = project_id
        if run is not None:
            self._console.show_run(project.name, run.label, STATE_RUNNING, path)
            self._console.set_buttons(interrupt=True, journal=True, result=False)
        elif result is not None:
            self._console.show_run(project.name, result.label, "", path)
            self._refresh_console_state(project_id)
        elif path.exists():
            self._console.show_run(project.name, "прошлый запуск", STATE_NOT_STARTED, path)
            self._console.set_buttons(interrupt=False, journal=True, result=False)
        else:
            self._console.show_run("", "", STATE_NOT_STARTED, None)
            self._console.set_buttons(interrupt=False, journal=False, result=False)

    def _open_console_journal(self) -> None:
        if self._cli is not None and self._console_project is not None:
            self._apply(lambda: self._workspace.open_path(str(self._cli.journal_path(self._console_project))), rebuild=False)  # type: ignore[union-attr, arg-type]

    def _open_console_result(self) -> None:
        if self._cli is None or self._console_project is None:
            return
        result = self._cli.last_result(self._console_project)
        if result is not None and result.result_file:
            self._apply(lambda: self._workspace.open_path(result.result_file), rebuild=False)

    def console(self) -> EdtConsole:
        return self._console
```

`EdtConsole.show_run` уже опускает пустые части заголовка (Task 4).
`apply_palette` вьюхи — добавить `self._console.apply_palette(palette)`.

Тест `test_selecting_project_shows_its_journal_without_expanding` ожидает у записи `b`
пустой заголовок — журнала у `b` нет, ветка `else`.

- [ ] **Step 3: Сборка в `app.py` и гейт выхода — тесты**

В `tests/ui/test_app.py`:

```python
from onecstarter.ui.app import _confirm_quit_with_cli


def test_confirm_quit_with_cli_silent_when_none() -> None:
    asked: list[str] = []
    assert _confirm_quit_with_cli(lambda: 0, lambda text: asked.append(text) or False) is True
    assert asked == []


def test_confirm_quit_with_cli_asks_with_count() -> None:
    asked: list[str] = []
    assert _confirm_quit_with_cli(lambda: 2, lambda text: asked.append(text) or True) is True
    assert asked == ["Выполняются команды CLI EDT: 2. Прервать их и выйти?"]


def test_confirm_quit_with_cli_declined() -> None:
    assert _confirm_quit_with_cli(lambda: 1, lambda text: False) is False
```

- [ ] **Step 4: Реализовать в `app.py`**

Импорты: `from onecstarter.platform_1c.server_spawn import spawn_logged, spawn_server`
(дополнить), `from onecstarter.services.edt_cli import EdtCli`, `from onecstarter.ui.edt.cli_watch import CliWatcher`.

В `_build_main_window` после `edt_workspace`:

```python
    edt_cli = EdtCli(
        edt_workspace,
        runtime.servers.parent / "logs" / "edt",
        job_factory=job_factory if job_factory is not None else ServerJob,
        spawn=spawn_logged,
    )
    cli_watcher = CliWatcher()
```

`EdtView(..., cli=edt_cli, watcher=cli_watcher, documents_dir=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))`
— правка M4 финального ревью: не `Path.home() / "Documents"` (при OneDrive KFM «Документы»
живут в другом месте и `~/Documents` может не существовать), а тот же источник, что у ярлыков
в `ui/bases/view.py`; тест `test_build_main_window_gives_edt_view_the_cli_and_watcher`
сверяет `edt_view.tsv_dir()` с этим значением. После создания `window` —
`cli_watcher.setParent(window)`.

Гейт выхода — рядом с `_confirm_quit_with_servers`:

```python
def _confirm_quit_with_cli(running_count: Callable[[], int], ask: Callable[[str], bool]) -> bool:
    """Живые команды CLI EDT при выходе (спека v3, §14.4): вопрос, не молчаливое убийство."""
    count = running_count()
    if count == 0:
        return True
    return ask(f"Выполняются команды CLI EDT: {count}. Прервать их и выйти?")
```

В `_build_confirm_quit.confirm_quit` после подтверждения серверов:

```python
            if confirmed:
                confirmed = _confirm_quit_with_cli(
                    edt_cli.running_count, lambda message: dialog(window, message)
                )
            if confirmed:
                try:
                    servers_workspace.log_shutdown()
                except ServicesError as error:
                    _log.warning("не удалось отметить выход в журналах серверов: %s", error)
                try:
                    edt_cli.log_shutdown()
                except OSError:
                    _log.warning("не удалось отметить выход в журналах CLI EDT")
```

Процессы CLI гасит закрытие хендлов Job при выходе (kill-on-close) — как у серверов.

- [ ] **Step 5: Полный прогон, ручной чек-лист, коммит**

Run: `uv run pytest -q > e:/tmp/v3-plan2-task6.log 2>&1; tail -3 e:/tmp/v3-plan2-task6.log && uv run ruff check . && uv run mypy`
Expected: зелёное.

Вручную (с разрешения заказчика, на **тестовом** workspace, спека §10): ПКМ → CLI →
«Информация по проектам» — консоль раскрылась, состояние «выполняется», после
завершения — «завершено, код N», вывод виден; повтор на записи с открытым EDT — подменю
неактивно с подсказкой. Это одновременно первая половина эксперимента 6.

```bash
git add src/onecstarter/services/edt.py src/onecstarter/ui/edt/view.py src/onecstarter/ui/edt/console_panel.py src/onecstarter/ui/app.py tests/ui/test_edt_view.py tests/ui/test_app.py
git commit -m "feat(ui): подменю CLI EDT, консоль под деревом, гейт выхода с живыми командами"
```

---

### Task 7: Verification-only — мутации и `tasks.md`

**Files:**
- Modify: `docs/tasks.md` (T-17.2, таблица мутаций плана 2)

- [ ] **Step 1: Полный прогон в файл**

Run: `uv run pytest -q > e:/tmp/v3-plan2-final.log 2>&1; tail -3 e:/tmp/v3-plan2-final.log && uv run ruff check . && uv run mypy`

- [ ] **Step 2: Мутационная стадия чужими руками**

1. `services/edt_cli.py::unavailable_reason` без проверки `running_pid` →
   `test_running_edt_refused_before_spawn` падает на `spawned == []`.
2. `services/edt_cli.py::start` без отказа при `project_id in self._runs` →
   `test_second_start_on_same_project_refused` падает.
3. `services/edt.py::launch` без проверки `_cli_busy` → `test_launch_refused_while_busy` падает.
4. `domain/edt_cli.py::cli_build_args` → `"build"` → `test_fixed_commands` падает.
5. `domain/edt_cli.py::build_cli_command` — `-command` после `-vmargs` →
   `test_order_command_before_vmargs_with_encoding` падает.
6. `ui/edt/view.py::_start_cli` без `self._console.expand()` →
   `test_cli_build_confirms_starts_and_expands_console` падает.

Каждую — правкой файла, прогон названного теста, дословный `FAILED`, откат правкой.

- [ ] **Step 3: `docs/tasks.md`**

В T-17: строка T-17.2 → `DONE`, ссылка на этот план
(`superpowers/plans/2026-09-10-v3-plan2-edt-cli.md`), таблица «Мутационные проверки
плана 2 (дата)» по образцу плана 1 с шестью строками выше и дословными результатами.

- [ ] **Step 4: Commit**

```bash
git add docs/tasks.md
git commit -m "docs: T-17.2 — план 2 (CLI EDT) закрыт, мутационная стадия записана"
```

---

## Чего в плане нет — сознательно

- Таблица числовых кодов возврата → имён (`WORKSPACE_IN_USE` и др.) — после эксперимента 7
  (план 3), тогда `state_finished` получит имя рядом с числом.
- `export`, `delete`, свободная строка команды — вне v3 (решение заказчика, спека §1).
- Таймаут команды (`edtcli.timeout`) — не задаём; «Прервать» — наш.
