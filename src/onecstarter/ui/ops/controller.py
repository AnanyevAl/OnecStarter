"""Координатор пакетных операций для окон (спека v4, §6.4, §6.7; план 2б).

Владеет единственным `OperationsRunner` программы и данными `operations.json`. Готовность
(`prepare`) и выполнение (`run`) идут в потоках-демонах; результат уходит приватным
сигналом в слот этого объекта, а тот уже в главном потоке испускает публичный сигнал —
окна подключаются только к публичным и о потоках не знают.

`RunPlan` (в нём введённые пароли) контроллер не хранит: план живёт в замыкании рабочего
потока до конца `run`. Для окон есть `RunInfo` — то же без паролей.
"""  # noqa: RUF002

import logging
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from onecstarter.domain.cli_catalog import Catalog
from onecstarter.domain.operations import RunRecord, Scenario
from onecstarter.services.errors import ServicesError
from onecstarter.services.operations_runner import (
    BUSY_TEXT,
    BaseFinished,
    CancelToken,
    OperationsRunner,
    PreparedBase,
    RunEvent,
    RunFinished,
    RunPlan,
    readiness_text,
)
from onecstarter.services.operations_store import (
    OperationsData,
    add_run,
    all_scenarios,
    copy_of,
    prune_logs,
    remove_scenario,
    save_operations,
    upsert_scenario,
)
from onecstarter.services.workspace import BatchTarget

_log = logging.getLogger("onecstarter.operations")

NEW_SCENARIO_NAME = "Новый сценарий"
INTERNAL_FAILURE = (
    "Выполнение сценария прервано внутренней ошибкой — подробности в журнале программы"
)


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


@dataclass(frozen=True)
class RunBase:
    key: str
    name: str
    ready: bool
    problems: tuple[str, ...]
    logs_dir: str
    output_dir: str  # каталог первого выходного файла; "" — выходных файлов нет или база не готова


@dataclass(frozen=True)
class RunInfo:
    """Запуск глазами окон: сценарий, базы и каталоги. Паролей здесь нет по построению."""

    scenario: Scenario
    started: datetime
    logs_dir: str
    bases: tuple[RunBase, ...]


@dataclass(frozen=True)
class Prepared:
    generation: int
    plan: RunPlan | None = field(repr=False)  # None — проверка готовности сорвалась
    versions: Mapping[str, str]


def _output_dir(base: PreparedBase) -> str:
    # у неготовой базы выгружать нечего: каталог показывать незачем  # noqa: RUF003
    if not base.ready:
        return ""
    for step in base.steps:
        for output in step.outputs:
            return str(output.parent)
    return ""


def _info_of(plan: RunPlan) -> RunInfo:
    return RunInfo(
        plan.scenario,
        plan.started,
        str(plan.logs_dir),
        tuple(
            RunBase(
                base.key,
                base.name,
                base.ready,
                readiness_text(base),
                str(base.logs_dir) if base.logs_dir is not None else "",
                _output_dir(base),
            )
            for base in plan.bases
        ),
    )


class OperationsController(QObject):
    prepared = Signal(object)  # Prepared
    run_event = Signal(object)  # RunEvent; не `event`: так зовётся виртуальный QObject.event
    run_started = Signal(object)  # RunInfo
    run_finished = Signal(object)  # RunRecord | None (запуск сорвался)
    scenarios_changed = Signal()
    problem = Signal(str)

    _raw_prepared = Signal(object)
    _raw_event = Signal(object)
    _raw_failure = Signal(str)

    def __init__(
        self,
        runner: OperationsRunner,
        catalog: Catalog,
        data: OperationsData,
        path: Path,
        ops_dir: Path,
        *,
        targets: Callable[[str], BatchTarget],
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._catalog = catalog
        self._data = data
        self._path = path
        self._ops_dir = ops_dir
        self._targets = targets
        self._spawn = spawn
        self._new_id = new_id
        self._generation = 0
        self._cancel: CancelToken | None = None
        self._soft_by_panel = False
        self._soft_by_quit = False
        self._info: RunInfo | None = None
        self._done = 0
        # Слоты — методы этого объекта: событие из рабочего потока встаёт в очередь
        # главного, а публичный сигнал испускается уже из него.  # noqa: RUF003
        self._raw_prepared.connect(self._on_prepared)
        self._raw_event.connect(self._on_event)
        self._raw_failure.connect(self._on_failure)

    # -- сценарии ------------------------------------------------------------

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    @property
    def ops_dir(self) -> Path:
        return self._ops_dir

    def scenarios(self) -> tuple[Scenario, ...]:
        return all_scenarios(self._data)

    def scenario(self, scenario_id: str) -> Scenario | None:
        return next((s for s in self.scenarios() if s.id == scenario_id), None)

    def history_count(self) -> int:
        return len(self._data.history)

    def new_scenario(self) -> Scenario:
        taken = {scenario.name.strip().casefold() for scenario in self.scenarios()}
        name = NEW_SCENARIO_NAME
        number = 2
        while name.casefold() in taken:
            name = f"{NEW_SCENARIO_NAME} {number}"
            number += 1
        return Scenario(self._new_id(), name, ())

    def save_scenario(self, scenario: Scenario) -> str | None:
        """Записать сценарий; текст отказа либо `None`. Имя уникально без учёта регистра."""
        name = scenario.name.strip()
        folded = name.casefold()
        if any(
            other.id != scenario.id and other.name.strip().casefold() == folded
            for other in self.scenarios()
        ):
            return f"Сценарий с именем «{name}» уже есть"  # noqa: RUF001
        return self._commit(lambda: upsert_scenario(self._data, replace(scenario, name=name)))

    def remove_scenario(self, scenario_id: str) -> str | None:
        return self._commit(lambda: remove_scenario(self._data, scenario_id))

    def copy_scenario(self, scenario_id: str) -> Scenario | None:
        source = self.scenario(scenario_id)
        if source is None:
            return None
        copy = copy_of(source, self._new_id(), [s.name for s in self.scenarios()])
        error = self._commit(lambda: upsert_scenario(self._data, copy))
        if error is not None:
            self.problem.emit(error)
            return None
        return copy

    def _commit(self, change: Callable[[], OperationsData]) -> str | None:
        try:
            data = change()
            save_operations(self._path, data)
        except (ServicesError, OSError) as error:
            return f"Сценарий не сохранён: {error}"
        self._data = data
        self.scenarios_changed.emit()
        return None

    # -- готовность ----------------------------------------------------------

    def request_prepare(
        self,
        scenario: Scenario,
        keys: Sequence[str],
        passwords: Mapping[str, str] | None = None,
        repository_passwords: Mapping[str, str] | None = None,
    ) -> int:
        """Посчитать готовность в рабочем потоке; результат — сигналом `prepared`.

        Базы читаются здесь, в главном потоке (`Workspace` из другого потока не читается),
        поток получает снимок. Возвращает номер поколения: окно принимает только результат
        с номером своего последнего запроса.
        """  # noqa: RUF002
        self._generation += 1
        generation = self._generation
        order = list(keys)
        snapshot = {key: self._targets(key) for key in order}
        versions = {
            key: str(target.version)
            for key, target in snapshot.items()
            if target.version is not None
        }
        typed = dict(passwords or {})
        typed_repository = dict(repository_passwords or {})

        def work() -> None:
            plan: RunPlan | None = None
            try:
                plan = self._runner.prepare(
                    scenario, order, typed, typed_repository, targets=snapshot.__getitem__
                )
            except Exception as error:  # сбой проверки не должен ронять поток молча
                _log.warning("проверка готовности не удалась: %s", type(error).__name__)
            self._raw_prepared.emit(Prepared(generation, plan, versions))

        self._spawn(work)
        return generation

    def _on_prepared(self, result: Prepared) -> None:
        self.prepared.emit(result)

    # -- выполнение ----------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._info is not None

    def busy_keys(self) -> frozenset[str]:
        return self._runner.busy_keys()

    def start(self, plan: RunPlan, *, parallel: bool = False) -> str | None:
        """Запустить план в рабочем потоке. Текст отказа либо `None`."""
        if self._info is not None or self._runner.running:
            return BUSY_TEXT
        cancel = CancelToken()
        self._cancel = cancel
        self._soft_by_panel = False
        self._soft_by_quit = False
        self._info = _info_of(plan)
        self._done = 0
        self.run_started.emit(self._info)

        def work() -> None:
            try:
                self._runner.run(plan, self._raw_event.emit, cancel, parallel=parallel)
            except ServicesError as error:
                self._raw_failure.emit(str(error))
            except Exception as error:
                _log.error("выполнение сценария упало: %s", type(error).__name__)
                self._raw_failure.emit(INTERNAL_FAILURE)
            failure = self._runner.listener_failure
            if failure is not None:  # ссылку не храним: за ней трассировка и план
                _log.warning("окно не обработало событие операции: %s", type(failure).__name__)

        try:
            self._spawn(work)
        except Exception as error:
            # поток не создан: без сброса контроллер навсегда остался бы в running  # noqa: RUF003
            _log.error("не удалось запустить выполнение сценария: %s", type(error).__name__)
            self._cancel = None
            self._info = None
            self.run_finished.emit(None)
            return INTERNAL_FAILURE
        return None

    def cancel_soft(self) -> None:
        """Мягкая отмена кнопкой панели: выходом её не снять (Р4)."""  # noqa: RUF002
        if self._cancel is not None:
            self._soft_by_panel = True
            self._cancel.request_soft()

    def cancel_soft_for_quit(self) -> None:
        """Мягкая отмена от «Дождаться шага и выйти»."""
        if self._cancel is not None:
            self._soft_by_quit = True
            self._cancel.request_soft()

    def revoke_quit_cancel(self) -> None:
        """«Не выходить» после «Дождаться»: снять отмену, если её подал только выход (Р4)."""  # noqa: RUF002
        if self._cancel is not None and self._soft_by_quit and not self._soft_by_panel:
            self._cancel.revoke_soft()
        self._soft_by_quit = False

    def cancel_hard(self) -> None:
        if self._cancel is not None:
            self._cancel.request_hard()

    def quit_question(self) -> str:
        info = self._info
        if info is None:
            return ""
        return (
            f"Сценарий «{info.scenario.name}» ещё выполняется: "
            f"завершено баз — {self._done} из {len(info.bases)}."
        )

    def _on_event(self, event: RunEvent) -> None:
        if isinstance(event, BaseFinished):
            self._done += 1
        self.run_event.emit(event)
        if isinstance(event, RunFinished):
            self._finish(event.record)

    def _finish(self, record: RunRecord) -> None:
        self._cancel = None
        self._info = None
        data, dropped = add_run(self._data, record)
        try:
            save_operations(self._path, data)
        except (ServicesError, OSError) as error:
            self.problem.emit(f"История запуска не сохранена: {error}")
        else:
            self._data = data
            prune_logs(dropped, self._ops_dir)
        self.run_finished.emit(record)

    def _on_failure(self, text: str) -> None:
        self._cancel = None
        self._info = None
        self.problem.emit(text)
        self.run_finished.emit(None)
