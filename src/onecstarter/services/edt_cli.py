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

from onecstarter.domain.edt import CLI_EXE, effective_jvm
from onecstarter.domain.edt_cli import (
    PROJECTS_REGISTRY,
    CliQuoteError,
    WorkspaceEntry,
    build_cli_command,
    parse_project_location,
    wrap_console_utf8,
)
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
_DEFAULT_COMSPEC = Path(r"C:\Windows\System32\cmd.exe")


def default_comspec() -> Path:
    """`%ComSpec%` — cmd.exe для `wrap_console_utf8` (Э6); без переменной — системный путь."""
    return Path(os.environ.get("ComSpec") or _DEFAULT_COMSPEC)


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
    ) -> None:
        self._workspace = workspace
        self._logs_dir = logs_dir
        self._job_factory = job_factory
        self._spawn = spawn
        self._is_file = is_file
        self._now = now
        self._comspec = comspec if comspec is not None else default_comspec()
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
        project = self._workspace.project(project_id)
        installation = self._workspace.installation_for(project)
        assert installation is not None  # unavailable_reason проверил
        jvm = effective_jvm(project, installation)
        assert jvm is not None
        cli = build_cli_command(
            installation.exe.parent / CLI_EXE,
            project.workspace,
            command,
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
            append_event(path, f"▶ {label}: {command}", self._now())
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
        """  # noqa: RUF002
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
