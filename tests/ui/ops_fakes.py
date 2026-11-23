"""Двойники для тестов экранов пакетных операций: настоящая готовность, подменное выполнение.

Процессы 1С не порождаются: `ScriptedRunner.run` играет события по плану.
"""  # noqa: RUF002

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from onecstarter.domain.operations import (
    BaseOutcome,
    BaseResult,
    RunRecord,
    Scenario,
    Step,
    StepResult,
    StepStatus,
)
from onecstarter.domain.version import parse_version
from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.services.operations_runner import (
    BaseFinished,
    OperationsRunner,
    RunFinished,
    RunPlan,
    StepFinished,
    StepStarted,
    readiness_text,
)
from onecstarter.services.operations_store import OperationsData
from onecstarter.services.workspace import BatchTarget
from onecstarter.ui.ops.controller import OperationsController

CATALOG = load_cli_catalog()
STARTED = datetime(2026, 11, 14, 9, 5, 7)
EXE = Path(r"C:\Program Files\1cv8\8.3.27.2214\bin\1cv8.exe")
NOT_FOUND = "база не найдена в списке"
FAILURE_TEXT = "объект захвачен"


def target(key: str = "id:1", name: str = "Бухгалтерия", **changes: object) -> BatchTarget:
    fields: dict[str, object] = {
        "key": key,
        "name": name,
        "group": "Клиенты",
        "executable": EXE,
        "version": parse_version("8.3.27.2214"),
    }
    fields.update(changes)
    return BatchTarget(**fields)  # type: ignore[arg-type]


def dump_scenario(tmp_path: Path, scenario_id: str = "u1", name: str = "Ночной архив") -> Scenario:
    return Scenario(scenario_id, name, (Step("/DumpIB", (str(tmp_path / "out" / "{база}.dt"),)),))


class ScriptedRunner(OperationsRunner):
    """`prepare` — настоящий; `run` выдаёт события без процессов.

    `outcomes` задаёт исход готовой базы (по умолчанию OK); FAILED — её шаги с ошибкой.
    """  # noqa: RUF002

    def __init__(self, ops_dir: Path, targets: dict[str, BatchTarget]) -> None:
        self.targets = targets
        super().__init__(
            self.target_of,
            CATALOG,
            ops_dir,
            environ={"USERPROFILE": str(ops_dir.parent / "home")},
            now=lambda: STARTED,
        )
        self.run_calls: list[dict[str, Any]] = []
        self.outcomes: dict[str, BaseOutcome] = {}
        self.run_error: Exception | None = None
        self.prepare_error: Exception | None = None

    def target_of(self, key: str) -> BatchTarget:
        return self.targets.get(key, BatchTarget(key, "", problems=(NOT_FOUND,)))

    def prepare(self, scenario, keys, passwords=None, repository_passwords=None, *, targets=None):
        if self.prepare_error is not None:
            raise self.prepare_error
        return super().prepare(scenario, keys, passwords, repository_passwords, targets=targets)

    def run(self, plan, events, cancel, *, parallel=False):
        self.run_calls.append(
            {
                "keys": [base.key for base in plan.bases],
                "soft": cancel.soft,
                "hard": cancel.hard,
                "parallel": parallel,
            }
        )
        if self.run_error is not None:
            raise self.run_error
        results: list[BaseResult] = []
        for base in plan.bases:
            if not base.ready:
                result = BaseResult(
                    base.key, base.name, BaseOutcome.NOT_READY, (), readiness_text(base)
                )
            else:
                outcome = self.outcomes.get(base.key, BaseOutcome.OK)
                failed = outcome is BaseOutcome.FAILED
                steps: list[StepResult] = []
                for index, step in enumerate(base.steps):
                    events(StepStarted(base.key, index))
                    done = StepResult(
                        step.command.name,
                        StepStatus.FAILED if failed else StepStatus.OK,
                        1 if failed else 0,
                        2.0,
                        FAILURE_TEXT if failed else "",
                    )
                    steps.append(done)
                    events(StepFinished(base.key, index, done))
                result = BaseResult(
                    base.key, base.name, outcome, tuple(steps), logs_dir=str(base.logs_dir)
                )
            results.append(result)
            events(BaseFinished(result))
        record = RunRecord(
            plan.scenario.id, plan.scenario.name, plan.started, str(plan.logs_dir), tuple(results)
        )
        events(RunFinished(record))
        return record


def sync(task: Callable[[], None]) -> None:
    task()


def make_controller(
    tmp_path: Path,
    *,
    targets: dict[str, BatchTarget] | None = None,
    data: OperationsData | None = None,
    spawn: Callable[[Callable[[], None]], None] | None = sync,
) -> tuple[OperationsController, ScriptedRunner]:
    """Контроллер над `ScriptedRunner`. `spawn=None` — настоящие потоки-демоны."""
    runner = ScriptedRunner(
        tmp_path / "ops",
        targets if targets is not None else {"id:1": target(), "id:2": target("id:2", "Склад")},
    )
    ids = iter(f"new{number}" for number in range(1, 100))
    kwargs: dict[str, Any] = {} if spawn is None else {"spawn": spawn}
    controller = OperationsController(
        runner,
        CATALOG,
        data or OperationsData(),
        tmp_path / "operations.json",
        tmp_path / "ops",
        targets=runner.target_of,
        new_id=lambda: next(ids),
        **kwargs,
    )
    return controller, runner


def plan_for(
    controller: OperationsController, scenario: Scenario, keys: list[str], **typed: Any
) -> RunPlan:
    """План готовности синхронно — для контроллера с `spawn=sync`."""  # noqa: RUF002
    results: list[Any] = []
    controller.prepared.connect(results.append)
    controller.request_prepare(scenario, keys, **typed)
    controller.prepared.disconnect(results.append)
    assert results and results[-1].plan is not None
    plan: RunPlan = results[-1].plan
    return plan
