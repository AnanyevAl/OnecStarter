"""Исполнитель пакетных операций Конфигуратора (спека v4, §6) — без Qt и без потоков.

`prepare` проверяет готовность каждой базы до первого процесса и ничего не меняет на
диске. `run` (задача 8) ведёт очередь одним циклом опроса процессов. Всё о базе
исполнитель получает одной функцией `targets(key) -> BatchTarget` — в проде это
`Workspace.batch_target`.
"""  # noqa: RUF002

import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PureWindowsPath

from onecstarter.domain.cli_catalog import ArgKind, Catalog, CatalogCommand
from onecstarter.domain.launch import Credentials, LaunchCommand
from onecstarter.domain.operations import (
    BaseOutcome,
    BaseResult,
    RepositoryAccess,
    RunRecord,
    Scenario,
    StepResult,
    StepStatus,
    SubstitutionContext,
    SubstitutionError,
    build_step_arguments,
    decode_log,
    error_text,
    has_control_chars,
    leftovers,
    padded,
    sanitize_component,
    step_problems,
    step_succeeded,
    substitute,
)
from onecstarter.platform_1c.job import Job, JobError, ServerJob
from onecstarter.platform_1c.server_spawn import LoggedProcess, spawn_logged
from onecstarter.security.secrets import redact_arguments
from onecstarter.services.errors import OperationsBusyError
from onecstarter.services.server_journal import append_event
from onecstarter.services.workspace import BatchTarget

__all__ = [
    "BUSY_TEXT",
    "MAX_PARALLEL",
    "NO_RESULT_TEXT",
    "POLL_SECONDS",
    "STORE_UNAVAILABLE_TEXT",
    "BaseFinished",
    "CancelToken",
    "OperationsRunner",
    "PreparedBase",
    "PreparedStep",
    "RunEvent",
    "RunFinished",
    "RunPlan",
    "StepFinished",
    "StepStarted",
    "readiness_text",
    "step_log_path",
    "step_result_path",
]

_PATH_KINDS = (ArgKind.FILE, ArgKind.DIR)

MAX_PARALLEL = 4
POLL_SECONDS = 0.2
BUSY_TEXT = "Уже выполняется другой сценарий — дождитесь его завершения или отмените"  # noqa: RUF001
# Код 0, а файла /DumpResult нет — ошибка шага (решение заказчика 14.11.2026).  # noqa: RUF003
NO_RESULT_TEXT = "результат не получен (нет файла /DumpResult)"
STORE_UNAVAILABLE_TEXT = "диспетчер учётных данных Windows недоступен — пароль нужно ввести"

_log = logging.getLogger("onecstarter.operations_runner")


class CancelToken:
    """Флаги отмены; ставит их другой поток (окно), читает цикл исполнителя."""

    def __init__(self) -> None:
        self._soft = threading.Event()
        self._hard = threading.Event()

    def request_soft(self) -> None:
        self._soft.set()

    def request_hard(self) -> None:
        self._soft.set()
        self._hard.set()

    def revoke_soft(self) -> None:
        """Снять мягкую отмену (Р4). Жёсткую не снять: процесс уже снимается."""  # noqa: RUF002
        if not self._hard.is_set():
            self._soft.clear()

    @property
    def soft(self) -> bool:
        return self._soft.is_set()

    @property
    def hard(self) -> bool:
        return self._hard.is_set()


@dataclass(frozen=True)
class StepStarted:
    key: str
    index: int


@dataclass(frozen=True)
class StepFinished:
    key: str
    index: int
    result: StepResult


@dataclass(frozen=True)
class BaseFinished:
    result: BaseResult


@dataclass(frozen=True)
class RunFinished:
    record: RunRecord


RunEvent = StepStarted | StepFinished | BaseFinished | RunFinished


@dataclass(frozen=True)
class PreparedStep:
    command: CatalogCommand
    values: tuple[str | None, ...]  # подстановки раскрыты
    overwrite: bool
    create_dirs: bool
    outputs: tuple[Path, ...]


@dataclass(frozen=True)
class PreparedBase:
    """База в плане запуска.

    Готовность типизирована: `problems` — то, что ввод пароля не исправит;
    `needs_password` (логин, для которого нужен пароль базы) и
    `needs_repository_password` — то, что исправит окно запуска. Тексты для показа —
    `readiness_text`. `logs_dir` — каталог журналов базы `<каталог запуска>/<NN>_<имя>`.
    """

    key: str
    name: str
    executable: Path | None
    credentials: Credentials | None
    repository: RepositoryAccess | None
    steps: tuple[PreparedStep, ...]
    problems: tuple[str, ...]
    needs_password: str | None = None
    needs_repository_password: bool = False
    store_unavailable: bool = False
    logs_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return (
            not self.problems
            and self.needs_password is None
            and not self.needs_repository_password
        )


def readiness_text(base: PreparedBase) -> tuple[str, ...]:
    """Что мешает базе — тексты для показа: проблемы и недостающие пароли.

    Недоступный диспетчер учётных данных — одна строка, только когда пароль ещё
    нужно ввести: введённый пароль базу уже спас.
    """
    texts = list(base.problems)
    if base.needs_password is not None:
        texts.append(f"нужен пароль пользователя «{base.needs_password}»")
    if base.needs_repository_password:
        texts.append("нужен пароль хранилища конфигурации")
    if base.store_unavailable and (
        base.needs_password is not None or base.needs_repository_password
    ):
        texts.append(STORE_UNAVAILABLE_TEXT)
    return tuple(texts)


@dataclass(frozen=True)
class RunPlan:
    scenario: Scenario
    started: datetime
    logs_dir: Path
    bases: tuple[PreparedBase, ...]


@dataclass
class _Active:
    """База в работе: её каталог журналов, идущий шаг и накопленные итоги."""

    position: int
    base: PreparedBase
    directory: Path
    results: list[StepResult] = field(default_factory=list)
    process: LoggedProcess | None = None
    job: Job | None = None
    started_at: float = 0.0

    @property
    def index(self) -> int:
        return len(self.results)


class OperationsRunner:
    def __init__(
        self,
        targets: Callable[[str], BatchTarget],
        catalog: Catalog,
        ops_dir: Path,
        *,
        environ: Mapping[str, str] | None = None,
        job_factory: Callable[[], Job] = ServerJob,
        spawn: Callable[[LaunchCommand, Path, Job], LoggedProcess] = spawn_logged,
        now: Callable[[], datetime] = datetime.now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._targets = targets
        self._catalog = catalog
        self._ops_dir = ops_dir
        self._environ = environ
        self._job_factory = job_factory
        self._spawn = spawn
        self._now = now
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._busy: frozenset[str] = frozenset()
        self._listener_failure: Exception | None = None

    def prepare(
        self,
        scenario: Scenario,
        keys: Sequence[str],
        passwords: Mapping[str, str] | None = None,
        repository_passwords: Mapping[str, str] | None = None,
        *,
        targets: Callable[[str], BatchTarget] | None = None,
    ) -> RunPlan:
        """Готовность каждой базы — до первого процесса (спека §6.3). На диск не пишет.

        `passwords` и `repository_passwords` — пароли базы и хранилища конфигурации,
        введённые в окне запуска (ключ базы → пароль); пустая строка — «пароль пустой».
        Введённый пароль важнее сохранённого и живёт только в памяти этого плана.

        Каталог запуска — `<дата>_<время>_<сценарий>`; если такой уже есть (два запуска
        в одну секунду), к имени добавляется `_2`, `_3`… (только чтение диска).

        `targets` — снимок баз, снятый вызывающим в своём потоке (план 2б): окно запуска
        считает готовность в рабочем потоке, а `Workspace` читается только в главном.
        Без него базы берутся из источника, заданного при создании исполнителя.
        """  # noqa: RUF002
        source = targets if targets is not None else self._targets
        started = self._now().replace(microsecond=0)
        stem = f"{started:%Y-%m-%d_%H%M%S}_{sanitize_component(scenario.name)}"
        logs_dir = self._ops_dir / stem
        suffix = 2
        while logs_dir.exists():
            logs_dir = self._ops_dir / f"{stem}_{suffix}"
            suffix += 1
        typed = passwords or {}
        typed_repository = repository_passwords or {}
        claimed: dict[Path, tuple[str, str]] = {}  # выходной файл → (ключ, имя) заявившей базы
        bases = tuple(
            self._prepare_base(
                source,
                scenario,
                key,
                started,
                typed,
                typed_repository,
                claimed,
                logs_dir,
                position,
            )
            for position, key in enumerate(keys)
        )
        return RunPlan(scenario, started, logs_dir, bases)

    def _prepare_base(
        self,
        targets: Callable[[str], BatchTarget],
        scenario: Scenario,
        key: str,
        started: datetime,
        typed: Mapping[str, str],
        typed_repository: Mapping[str, str],
        claimed: dict[Path, tuple[str, str]],
        logs_dir: Path,
        position: int,
    ) -> PreparedBase:
        target = targets(key)
        problems = list(target.problems)
        if has_control_chars(target.name):
            problems.append("имя базы содержит управляющий символ")
        credentials: Credentials | None = None
        needs_password: str | None = None
        if target.login is not None:
            password = typed.get(key, target.password)
            if has_control_chars(target.login):
                problems.append("имя пользователя базы содержит управляющий символ")
            if password is None:
                needs_password = target.login
            elif has_control_chars(password):
                problems.append("пароль содержит управляющий символ")
            credentials = Credentials(target.login, password)
        needs_repository = any(
            command is not None and command.bound
            for command in (self._catalog.command(step.command) for step in scenario.steps)
        )
        repository: RepositoryAccess | None = None
        needs_repository_password = False
        if needs_repository:
            if target.repository_address is not None and has_control_chars(
                target.repository_address
            ):
                problems.append("адрес хранилища содержит управляющий символ")
            if target.repository_user is None:
                problems.append("не задан пользователь хранилища конфигурации")
            else:
                if has_control_chars(target.repository_user):
                    problems.append("пользователь хранилища содержит управляющий символ")
                repository_password = typed_repository.get(key, target.repository_password)
                if repository_password is None:
                    needs_repository_password = True
                else:
                    if has_control_chars(repository_password):
                        problems.append("пароль хранилища содержит управляющий символ")
                    repository = RepositoryAccess(
                        target.repository_address, target.repository_user, repository_password
                    )
        if target.file_path is not None and not Path(target.file_path).is_dir():
            problems.append(f"каталог базы недоступен: {target.file_path}")
        context = SubstitutionContext(
            base=target.name,
            group=target.group,
            version=str(target.version) if target.version is not None else "",
            started=started,
        )
        environ = self._environ if self._environ is not None else os.environ
        steps: list[PreparedStep] = []
        planned: set[Path] = set()
        for number, step in enumerate(scenario.steps, start=1):
            prefix = f"шаг {number} ({step.command}): "
            own = step_problems(step, self._catalog)
            command = self._catalog.command(step.command)
            if own or command is None:
                # Готовая база всегда несёт ровно len(scenario.steps) шагов: шаг,
                # отброшенный без причины, не должен исчезать молча.
                problems += [prefix + problem for problem in own] or [
                    f"{prefix}команды нет в каталоге"
                ]
                continue
            values: list[str | None] = []
            outputs: list[Path] = []
            failed = False
            for arg, value in zip(command.args, padded(step.values, command.args), strict=True):
                if value is None or arg.kind is ArgKind.BOUND:
                    values.append(None)
                    continue
                try:
                    resolved = substitute(value, context, environ)
                except SubstitutionError as error:
                    problems.append(prefix + str(error))
                    failed = True
                    break
                values.append(resolved)
                if arg.required and not resolved.strip():
                    # `{группа}` у базы в корне раскрывается в пустую строку.  # noqa: RUF003
                    problems.append(f"{prefix}не задан обязательный параметр «{arg.label}»")
                    continue
                if has_control_chars(resolved):
                    # Переменная окружения вставляется как есть.
                    problems.append(f"{prefix}параметр «{arg.label}» содержит управляющий символ")
                    continue
                if arg.kind not in _PATH_KINDS:
                    continue
                if not PureWindowsPath(resolved).is_absolute():
                    # Относительный путь считался бы от текущего каталога программы.
                    problems.append(f"{prefix}путь должен быть полным: {resolved}")
                    continue
                path = Path(resolved)
                # Вход удовлетворён файлом на диске или выходом ранее идущего шага;
                # `planned` пополняется после шага, поэтому собственный выход не считается.
                if arg.role == "input" and not (path.exists() or path in planned):
                    problems.append(f"{prefix}входной файл не найден: {path}")
                if arg.role == "output":
                    if not step.overwrite and (path.exists() or path in planned):
                        problems.append(f"{prefix}файл уже существует: {path}")
                    owner = claimed.setdefault(path, (key, target.name))
                    if owner[0] != key:
                        # Один файл у двух баз — всегда проблема, даже с overwrite.  # noqa: RUF003
                        problems.append(f"{prefix}тот же файл пишет база «{owner[1]}»: {path}")
                    outputs.append(path)
            if failed:
                continue
            planned.update(outputs)
            steps.append(
                PreparedStep(
                    command, tuple(values), step.overwrite, step.create_dirs, tuple(outputs)
                )
            )
        return PreparedBase(
            key=key,
            name=target.name,
            executable=target.executable,
            credentials=credentials,
            repository=repository,
            steps=tuple(steps),
            problems=tuple(problems),
            needs_password=needs_password,
            needs_repository_password=needs_repository_password,
            store_unavailable=target.store_unavailable,
            # Формула одна и для неготовой базы — по позиции в плане.
            logs_dir=logs_dir / f"{position + 1:02d}_{sanitize_component(target.name)}",
        )

    def busy_keys(self) -> frozenset[str]:
        """Базы активного запуска (пусто, когда запуска нет)."""
        return self._busy

    def run(
        self,
        plan: RunPlan,
        events: Callable[[RunEvent], None],
        cancel: CancelToken,
        *,
        parallel: bool = False,
    ) -> RunRecord:
        """Выполнить план: синхронно, один цикл опроса процессов (спека §6.4–§6.7).

        Исключение слушателя `events` (`Exception`) ловится, в лог программы идёт
        только имя типа, выполнение продолжается: ошибка в окне не должна снимать
        Конфигуратор посреди `/RestoreIB` ([Ф] Э10). Первое такое исключение — в
        `listener_failure`; `run` всё равно доводит план до конца и возвращает запись.
        `KeyboardInterrupt`, `SystemExit` и прочие `BaseException` не ловятся: идущие
        процессы снимаются (Job закрывается), занятость снимается, исключение уходит
        наружу.
        """  # noqa: RUF002
        if not self._lock.acquire(blocking=False):
            raise OperationsBusyError(BUSY_TEXT)
        active: list[_Active] = []
        try:
            self._listener_failure = None
            self._busy = frozenset(base.key for base in plan.bases if base.ready)
            emit = self._guarded(events)
            return self._run(plan, emit, cancel, MAX_PARALLEL if parallel else 1, active)
        finally:
            for state in active:
                self._close(state)
            self._busy = frozenset()
            self._lock.release()

    @property
    def listener_failure(self) -> Exception | None:
        """Первое исключение слушателя событий в последнем запуске (`None` — не было)."""
        return self._listener_failure

    @property
    def running(self) -> bool:
        """Идёт ли запуск — для диалога выхода из программы."""
        return self._lock.locked()

    def _guarded(self, events: Callable[[RunEvent], None]) -> Callable[[RunEvent], None]:
        def emit(event: RunEvent) -> None:
            try:
                events(event)
            except Exception as error:  # сбой окна не должен снимать идущие шаги
                if self._listener_failure is None:
                    self._listener_failure = error
                _log.warning(
                    "слушатель событий пакетной операции упал: %s", type(error).__name__
                )

        return emit

    def _run(
        self,
        plan: RunPlan,
        events: Callable[[RunEvent], None],
        cancel: CancelToken,
        limit: int,
        active: list[_Active],
    ) -> RunRecord:
        finished: dict[int, BaseResult] = {}

        def finish(position: int, result: BaseResult) -> None:
            finished[position] = result
            events(BaseFinished(result))

        queue: list[_Active] = []
        for position, base in enumerate(plan.bases):
            if base.ready and base.logs_dir is not None:
                queue.append(_Active(position, base, base.logs_dir))
            else:
                problems = readiness_text(base)
                if base.ready:  # план собран не `prepare`: процесс без журналов не порождаем
                    problems = (*problems, "не задан каталог журналов базы")
                finish(
                    position,
                    BaseResult(base.key, base.name, BaseOutcome.NOT_READY, (), problems),
                )

        def conclude(state: _Active, outcome: BaseOutcome) -> None:
            skipped = [
                StepResult(step.command.name, StepStatus.SKIPPED)
                for step in state.base.steps[len(state.results) :]
            ]
            active.remove(state)
            finish(
                state.position,
                BaseResult(
                    state.base.key,
                    state.base.name,
                    outcome,
                    (*state.results, *skipped),
                    logs_dir=str(state.directory),
                ),
            )

        def advance(state: _Active) -> None:
            """Запускать шаги базы, пока очередной не породит процесс или база не кончится."""
            while True:
                failed = any(r.status is StepStatus.FAILED for r in state.results)
                if failed and plan.scenario.stop_on_error:
                    conclude(state, BaseOutcome.FAILED)
                    return
                if state.index >= len(state.base.steps):
                    conclude(state, BaseOutcome.FAILED if failed else BaseOutcome.OK)
                    return
                if cancel.soft:
                    conclude(state, BaseOutcome.CANCELLED)
                    return
                index = state.index
                events(StepStarted(state.base.key, index))
                if cancel.hard:  # отмена пришла между событием и порождением
                    cut = StepResult(state.base.steps[index].command.name, StepStatus.INTERRUPTED)
                    state.results.append(cut)
                    events(StepFinished(state.base.key, index, cut))
                    conclude(state, BaseOutcome.INTERRUPTED)
                    return
                refused = self._start_step(state)
                if refused is None:
                    return  # процесс идёт
                state.results.append(refused)
                events(StepFinished(state.base.key, index, refused))

        while queue or active:
            if cancel.hard:
                for state in list(active):
                    index = state.index
                    code = state.process.process.poll() if state.process is not None else None
                    if code is not None:
                        # Процесс уже закончился сам: законченный шаг не выдаём за прерванный.
                        done = self._finish_step(state, code)
                        state.results.append(done)
                        events(StepFinished(state.base.key, index, done))
                        failed = any(r.status is StepStatus.FAILED for r in state.results)
                        if failed and plan.scenario.stop_on_error:
                            # Остальные шаги не пошли бы и без отмены — это ошибка базы.
                            outcome = BaseOutcome.FAILED
                        elif state.index < len(state.base.steps):
                            outcome = BaseOutcome.INTERRUPTED
                        elif failed:
                            outcome = BaseOutcome.FAILED
                        else:
                            outcome = BaseOutcome.OK
                        conclude(state, outcome)
                        continue
                    result = self._interrupt(state)
                    state.results.append(result)
                    events(StepFinished(state.base.key, index, result))
                    conclude(state, BaseOutcome.INTERRUPTED)
                break
            while queue and len(active) < limit and not cancel.soft:
                state = queue.pop(0)
                active.append(state)
                advance(state)
            for state in list(active):
                if state.process is None:
                    continue
                code = state.process.process.poll()
                if code is None:
                    continue
                index = state.index
                result = self._finish_step(state, code)
                state.results.append(result)
                events(StepFinished(state.base.key, index, result))
                advance(state)
            if cancel.soft and not active:
                break
            if active:
                self._sleep(POLL_SECONDS)
        for state in queue:
            finish(
                state.position,
                BaseResult(state.base.key, state.base.name, BaseOutcome.CANCELLED),
            )
        record = RunRecord(
            plan.scenario.id,
            plan.scenario.name,
            plan.started,
            str(plan.logs_dir),
            tuple(finished[position] for position in sorted(finished)),
        )
        events(RunFinished(record))
        return record

    def _start_step(self, state: _Active) -> StepResult | None:
        """Породить процесс шага. `None` — процесс идёт; `StepResult` — отказ без процесса."""
        step = state.base.steps[state.index]
        name = step.command.name
        number = state.index + 1
        try:
            state.directory.mkdir(parents=True, exist_ok=True)
            # Файлы прежнего запуска в том же каталоге не должны сойти за результат этого.
            step_log_path(state.directory, state.index).unlink(missing_ok=True)
            step_result_path(state.directory, state.index).unlink(missing_ok=True)
            for output in step.outputs:
                if not step.overwrite and output.exists():
                    return StepResult(
                        name, StepStatus.FAILED, message=f"файл уже существует: {output}"
                    )
                if step.create_dirs:
                    output.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return StepResult(
                name, StepStatus.FAILED, message=f"Не удалось подготовить каталоги: {error}"  # noqa: RUF001
            )
        assert state.base.executable is not None  # готовая база: версия разрешена
        run_log = state.directory / "run.log"
        job: Job | None = None
        try:
            arguments = build_step_arguments(
                ib_name=state.base.name,
                credentials=state.base.credentials,
                out_path=str(step_log_path(state.directory, state.index)),
                result_path=str(step_result_path(state.directory, state.index)),
                repository=state.base.repository,
                command=step.command,
                values=step.values,
            )
            command = LaunchCommand(state.base.executable, arguments)
            job = self._job_factory()
            # Событие — до порождения: процесс получает тот же файл для stdout и может
            # написать в него раньше нас (тот же приём, что в services/edt_cli.py).
            append_event(
                run_log,
                f'шаг {number}: "{command.executable}" {redact_arguments(arguments)}',
                self._now(),
            )
            spawned = self._spawn(command, run_log, job)
        except (OSError, JobError, ValueError) as error:
            if job is not None:
                self._close_job(job)
            self._log(state, f"шаг {number}: не запущен ({type(error).__name__})")
            # Текст ValueError мог бы нести значение аргумента (в том числе пароль) —
            # наружу только тип.
            reason = (
                "недопустимая командная строка"
                if isinstance(error, ValueError)
                else str(error)
            )
            return StepResult(
                name, StepStatus.FAILED, message=f"Не удалось запустить Конфигуратор: {reason}"  # noqa: RUF001
            )
        state.process, state.job, state.started_at = spawned, job, self._monotonic()
        return None

    def _finish_step(self, state: _Active, code: int) -> StepResult:
        step = state.base.steps[state.index]
        number = state.index + 1
        seconds = self._monotonic() - state.started_at
        log_text = _read(step_log_path(state.directory, state.index)) or ""
        dump_result = _read(step_result_path(state.directory, state.index))
        ok = step_succeeded(code, dump_result)
        self._close(state)
        self._log(state, f"шаг {number}: код возврата {code}, {'успех' if ok else 'ошибка'}")
        message = ""
        if not ok:
            if code == 0 and dump_result is None and not log_text.strip():
                message = NO_RESULT_TEXT
            else:
                message = error_text(log_text, code)
        return StepResult(
            step.command.name,
            StepStatus.OK if ok else StepStatus.FAILED,
            code,
            seconds,
            message,
        )

    def _interrupt(self, state: _Active) -> StepResult:
        """Жёсткая отмена шага: закрыть Job, убрать недописанное (спека §6.6, [Ф] Э10)."""
        step = state.base.steps[state.index]
        number = state.index + 1
        seconds = self._monotonic() - state.started_at
        message = ""
        process, job = state.process, state.job
        state.process, state.job = None, None
        if job is not None:
            try:
                job.close()
            except JobError as error:
                killed = False
                if process is not None:
                    try:  # запасной путь — как при неудачном assign в server_spawn
                        process.process.kill()
                        killed = True
                    except OSError:
                        pass
                if killed:
                    # Хендл Job не теряем: ещё одна попытка закрыть, отказ не роняет отмену.
                    self._close_job(job)
                else:
                    message = f"не удалось снять процесс: {error}"
        if process is not None and not message:
            try:
                process.process.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass
            for leftover in leftovers(step.command, step.values):
                try:
                    Path(leftover).unlink(missing_ok=True)
                except OSError as error:
                    self._log(
                        state, f"шаг {number}: недописанный файл не удалён ({type(error).__name__})"
                    )
        self._log(state, f"шаг {number}: прервано пользователем")
        return StepResult(step.command.name, StepStatus.INTERRUPTED, None, seconds, message)

    def _close(self, state: _Active) -> None:
        job, state.process, state.job = state.job, None, None
        if job is not None:
            self._close_job(job)

    @staticmethod
    def _close_job(job: Job) -> None:
        try:
            job.close()
        except JobError:
            return

    def _log(self, state: _Active, text: str) -> None:
        """Событие в `run.log` базы; отказ журнала операцию не ломает."""
        try:
            append_event(state.directory / "run.log", text, self._now())
        except OSError as error:
            _log.warning("журнал пакетной операции недоступен: %s", type(error).__name__)


def step_log_path(base_dir: Path, index: int) -> Path:
    """Журнал `/Out` шага `index` (с нуля) в каталоге базы: `step1.log`, `step2.log`…"""  # noqa: RUF002
    return base_dir / f"step{index + 1}.log"


def step_result_path(base_dir: Path, index: int) -> Path:
    """Файл `/DumpResult` шага `index` (с нуля) в каталоге базы: `step1.result`…"""  # noqa: RUF002
    return base_dir / f"step{index + 1}.result"


def _read(path: Path) -> str | None:
    """Текст файла `/Out` или `/DumpResult`; файла нет или он не читается — `None`."""
    try:
        return decode_log(path.read_bytes())
    except OSError:
        return None
