"""Команды CLI EDT (спека v3, §14.4): одна команда на запись, журнал, прерывание.

Порождение — `platform_1c/server_spawn.py::spawn_logged` (stdout ребёнка в файл
журнала хендлом `FILE_APPEND_DATA`, процесс в `Job`); журнал и ротация — те же
функции, что у серверов (`services/server_journal.py`). Ожидание кода
завершения — не здесь: `Popen` отдаётся вызывающему (`ui/edt/cli_watch.py`),
а результат возвращается через `finish()`.

Workspace, открытый в EDT, для CLI занят ([Д] спека §0-Д, `WORKSPACE_IN_USE`),
и наоборот — отсюда `unavailable_reason` до запуска и `mark_cli_busy`
в координаторе раздела, который отказывает «Открыть в EDT» на время команды.

`finish()`/`interrupt()` вызываются из основного потока: код завершения доставляет
наблюдатель (`ui/edt/cli_watch.py`) через сигнал Qt, поэтому `_runs`/`_results`
не нуждаются в блокировке.

`finish()` пишет в журнал не голый код, а код с расшифровкой из
`domain/edt_cli.py::status_text` (Task 9 спеки v3.2): журнал — файл, который
пользователь присылает в поддержку, и живёт дольше шапки консоли (та расшифровку
уже показывала, но только до следующего запуска).

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from onecstarter.domain.edt import CLI_EXE, EdtInstallation, EdtProject, effective_jvm
from onecstarter.domain.edt_cli import (
    INSTALLATION_INI,
    PROJECTS_REGISTRY,
    CliQuoteError,
    ProjectCandidate,
    WorkspaceEntry,
    build_cli_command,
    build_cli_script_command,
    cli_ini_text,
    parse_project_location,
    status_text,
    wrap_console_utf8,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import Job, JobError
from onecstarter.platform_1c.server_spawn import LoggedProcess, spawn_logged
from onecstarter.services.edt import EdtWorkspace
from onecstarter.services.errors import EdtError
from onecstarter.services.server_journal import append_event, journal_path, rotate_journal

__all__ = ["SCAN_MAX_DEPTH", "CliResult", "CliRun", "EdtCli", "scan_projects", "workspace_entries"]

_log = logging.getLogger("onecstarter.edt_cli")

RUNNING_REASON = "Закройте EDT: рабочая область занята"
BUSY_REASON = "Команда CLI уже выполняется для этой записи"


def default_comspec() -> Path:
    """`%SystemRoot%\\System32\\cmd.exe` для `wrap_console_utf8` (Э6), не `%ComSpec%`:
    обёртка рассчитана на разбор именно cmd.exe (`/d`, `/v:off`, снятие первой и последней
    кавычки), а `ComSpec` пользователь может переопределить (M3 финального ревью плана 3)."""  # noqa: RUF002
    return Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "cmd.exe"


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


def _read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def workspace_entries(
    workspace: str,
    listdir: Callable[[str], list[str]] = os.listdir,
    is_file: Callable[[str], bool] = os.path.isfile,
    read_bytes: Callable[[str], bytes] = _read_bytes,
) -> list[WorkspaceEntry]:
    """Проекты из реестра workspace `.metadata/…/.projects/<имя>` (спека §14.2, [Ф] Э6).

    Путь — из `.location` (проект привязан на месте, обычно вне каталога
    workspace), без него — `<workspace>/<имя>`; признак — `.project` по этому пути.
    Скрытые записи Eclipse (`.org.eclipse.egit.core.cmp`) начинаются с точки.
    Подкаталог workspace без записи в реестре — не проект workspace: `validate`
    импортировал бы его как побочный эффект.
    """  # noqa: RUF002
    registry = Path(workspace) / PROJECTS_REGISTRY
    try:
        names = sorted(listdir(str(registry)))
    except OSError:
        return []
    entries: list[WorkspaceEntry] = []
    for name in names:
        if name.startswith(".") or is_file(str(registry / name)):
            continue
        location = registry / name / ".location"
        path: str | None = None
        if is_file(str(location)):
            try:
                path = parse_project_location(read_bytes(str(location)))
            except OSError:
                path = None
        if path is None:
            path = str(Path(workspace) / name)
        entries.append(WorkspaceEntry(name, path, is_file(str(Path(path) / ".project"))))
    return entries


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
        if is_file(os.path.join(directory, ".project")):  # noqa: PTH118
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
            child = os.path.join(directory, name)  # noqa: PTH118
            if is_dir(child):
                walk(child, f"{relative}/{name}" if relative else name, depth + 1)

    walk(root, "", 0)
    found.sort(key=lambda candidate: candidate.relative.casefold())
    return found


CliBuilder = Callable[[Path, str, Path, str, str], LaunchCommand]
"""(exe, workspace, jvm_dir, installation_vm_args, project_vm_args) → командная строка CLI."""


def _by_command(command: str) -> CliBuilder:
    return lambda exe, workspace, jvm, installation_args, project_args: build_cli_command(
        exe, workspace, command, jvm, installation_args, project_args
    )


def _by_script(script: Path, ini: Path) -> CliBuilder:
    # JDK уже в ini: у обёртки нет ключа -vm ([Ф] Э12), jvm_dir строке не нужен  # noqa: RUF003
    return lambda exe, workspace, _jvm, installation_args, project_args: build_cli_script_command(
        exe, workspace, script, ini, installation_args, project_args
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
        comspec: Path | None = None,
        read_text: Callable[[Path], str] = _read_text,
    ) -> None:
        self._workspace = workspace
        self._logs_dir = logs_dir
        self._job_factory = job_factory
        self._spawn = spawn
        self._is_file = is_file
        self._now = now
        self._comspec = comspec if comspec is not None else default_comspec()
        self._read_text = read_text
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
            return f"В установке {installation.version} нет {CLI_EXE}"  # noqa: RUF001
        if effective_jvm(project, installation) is None:
            return f"JDK для EDT {installation.version} не найден"
        return ""

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
        _, installation, jvm = self._resolve(project_id)
        try:
            installation_ini = self._read_text(installation.exe.parent / INSTALLATION_INI)
        except (OSError, UnicodeDecodeError) as error:
            raise EdtError(
                f"Не удалось прочитать {INSTALLATION_INI} установки: {error}"  # noqa: RUF001
            ) from error
        script, ini = self.script_path(project_id), self.ini_path(project_id)
        try:
            script.parent.mkdir(parents=True, exist_ok=True)
            ini.write_text(cli_ini_text(installation_ini, jvm), encoding="utf-8", newline="\n")
            with script.open("w", encoding="utf-8", newline="\n") as handle:
                handle.writelines(f"{command}\n" for command in commands)
        except OSError as error:
            raise EdtError(f"Не удалось записать скрипт CLI: {error}") from error  # noqa: RUF001
        events = [f"▶ {label}: скрипт {script.name}, команд: {len(commands)}", *commands]
        return self._start(
            project_id, label, "\n".join(commands), events, _by_script(script, ini), ""
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
            # Ротация — best-effort в своём try (как servers.py::start): прошлый
            # журнал может держать переживший процесс, и это не отказ запуска —
            # записи продолжаются в тот же файл. Текст — фактический str(error).
            self._log_event(
                project_id,
                f"ротация журнала не удалась ({error}), записи продолжаются в тот же файл",
            )
        job = self._job_factory()
        try:
            # События — ДО spawn (спека §14.4; тот же приём, что «запуск:» перед
            # spawn_server в services/servers.py::start): ребёнок получает хендл
            # FILE_APPEND_DATA и может успеть написать в журнал раньше, чем
            # выполнится этот Python-код, — порядок в файле обязан быть
            # предсказуем независимо от гонки с дочерним процессом.  # noqa: RUF003
            for event in events:
                append_event(path, event, self._now())
            append_event(path, launch.command_line, self._now())
            spawned = self._spawn(launch, path, job)
        except (OSError, JobError) as error:
            # OSError здесь — и отказ записи событий (каталог журналов недоступен),
            # и отказ порождения; оба — отказ запуска с причиной от системы.  # noqa: RUF003
            self._close_job(job)
            self._log_event(project_id, f"■ не запущен: {type(error).__name__}")
            # Спека §8: «ошибка с командной строкой» — приём ServerError  # noqa: RUF003
            # в servers.py::start; секретов в команде CLI нет, показывать можно целиком.
            raise EdtError(
                f"Не удалось запустить {CLI_EXE}: {error}.\nКоманда: {launch.command_line}"  # noqa: RUF001
            ) from error
        run = CliRun(
            project_id, label, command_text, spawned.pid, spawned.process, job, result_file
        )
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
        """  # noqa: RUF002
        project_id = run.project_id
        if self._runs.get(project_id) is not run:
            return  # прервано раньше или уже идёт другой run — результат не наш
        del self._runs[project_id]
        if code is None:
            text = "■ завершено, код неизвестен"  # процесс не дал кода — расшифровывать нечего
        else:
            explanation = status_text(code)
            text = f"■ завершено, код {code}" + (f" ({explanation})" if explanation else "")
        self._log_event(project_id, text)
        self._results[project_id] = CliResult(run.label, code, False, run.result_file)
        self._workspace.clear_cli_busy(project_id)
        self._close_job(run.job)

    def interrupt(self, project_id: str) -> None:
        """Прервать команду: `job.close()` — kill-on-close гасит дерево процесса.

        Отказ `close()` (`JobError`: `CloseHandle` вернул ошибку) — `EdtError`,
        а run ОСТАЁТСЯ в учёте с занятостью и без «прервано» в журнале (правка M7
        финального ревью плана 2): `ServerJob.close()` на неудаче хендл не теряет,
        процесс жив, и считать его прерванным было бы враньём — тот же принцип,
        что у `services/servers.py::stop`.
        """  # noqa: RUF002
        run = self._runs.get(project_id)
        if run is None:
            return
        try:
            run.job.close()
        except JobError as error:
            raise EdtError(f"Не удалось прервать «{run.label}»: {error}") from error  # noqa: RUF001
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

        В `_log` — только тип ошибки, без пути (инвариант 5: секретов в пути нет,
        но и пользовательских путей в логе программы быть не должно).
        """  # noqa: RUF002
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
