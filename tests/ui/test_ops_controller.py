"""Координатор пакетных операций: сценарии, готовность и запуск в потоках (план 2б, задача 2)."""  # noqa: RUF002

import gc
import threading
import weakref
from collections.abc import Callable
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from onecstarter.domain.operations import (
    BUILTIN_SCENARIOS,
    BaseOutcome,
    BaseResult,
    RunRecord,
    Scenario,
)
from onecstarter.services import operations_store
from onecstarter.services.errors import OperationsBusyError
from onecstarter.services.operations_runner import BUSY_TEXT, BaseFinished, RunPlan
from onecstarter.services.operations_store import OperationsData, load_operations
from onecstarter.ui.ops.controller import INTERNAL_FAILURE, OperationsController, Prepared, RunInfo
from tests.ui.ops_fakes import (
    NOT_FOUND,
    STARTED,
    dump_scenario,
    make_controller,
    plan_for,
    target,
)


def test_scenarios_are_builtin_plus_own_and_saved_to_disk(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path)
    scenario = dump_scenario(tmp_path)
    changed: list[int] = []
    controller.scenarios_changed.connect(lambda: changed.append(1))
    assert controller.scenarios() == BUILTIN_SCENARIOS

    assert controller.save_scenario(scenario) is None

    assert controller.scenarios() == (*BUILTIN_SCENARIOS, scenario)
    assert controller.scenario("u1") == scenario and controller.scenario("нет") is None
    assert load_operations(tmp_path / "operations.json").scenarios == (scenario,)
    assert changed == [1]


def test_name_must_be_unique_ignoring_case_and_builtin_is_refused(
    qtbot: QtBot, tmp_path: Path
) -> None:
    controller, _ = make_controller(tmp_path)
    controller.save_scenario(dump_scenario(tmp_path))
    twin = Scenario("u2", " ночной АРХИВ ", ())
    assert controller.save_scenario(twin) == "Сценарий с именем «ночной АРХИВ» уже есть"  # noqa: RUF001
    assert controller.save_scenario(Scenario("u1", "Ночной архив 2", ())) is None  # своё имя
    assert controller.save_scenario(Scenario("u3", "выгрузить в .dt", ())) is not None
    refused = controller.save_scenario(BUILTIN_SCENARIOS[0])
    assert refused is not None and "Заготовку изменить нельзя" in refused
    assert controller.remove_scenario("builtin:dump-dt") is not None


def test_new_copy_and_remove(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path)
    fresh = controller.new_scenario()
    assert (fresh.id, fresh.name, fresh.steps, fresh.builtin) == (
        "new1",
        "Новый сценарий",
        (),
        False,
    )
    controller.save_scenario(fresh)
    assert controller.new_scenario().name == "Новый сценарий 2"

    copy = controller.copy_scenario("builtin:dump-dt")
    assert copy is not None and copy.name == "Выгрузить в .dt — копия" and not copy.builtin
    assert controller.scenario(copy.id) == copy
    assert controller.copy_scenario("нет") is None

    assert controller.remove_scenario(copy.id) is None
    assert controller.scenario(copy.id) is None


def test_failed_save_keeps_memory_and_reports(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, _ = make_controller(tmp_path)

    def refuse(path: Path, data: OperationsData) -> None:
        raise OSError("диск занят")

    monkeypatch.setattr("onecstarter.ui.ops.controller.save_operations", refuse)
    assert controller.save_scenario(dump_scenario(tmp_path)) == "Сценарий не сохранён: диск занят"
    assert (
        controller.scenarios() == BUILTIN_SCENARIOS
    )  # память не разошлась с диском  # noqa: RUF003


def test_prepare_uses_a_snapshot_taken_at_request_time(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, runner = make_controller(
        tmp_path, targets={"id:1": target(login="Иванов")}, spawn=pending.append
    )
    results: list[Prepared] = []
    controller.prepared.connect(results.append)
    scenario = dump_scenario(tmp_path)

    first = controller.request_prepare(scenario, ["id:1"], {"id:1": "pw"})
    runner.targets["id:1"] = target(name="Новое имя")  # список изменился до работы потока
    second = controller.request_prepare(scenario, ["id:1"])
    assert (first, second) == (1, 2) and results == []
    for task in pending:
        task()

    assert [result.generation for result in results] == [1, 2]
    old, new = results[0].plan, results[1].plan
    assert old is not None and new is not None
    assert old.bases[0].name == "Бухгалтерия" and new.bases[0].name == "Новое имя"
    assert old.bases[0].ready and old.bases[0].credentials is not None
    assert old.bases[0].credentials.password == "pw"  # введённый пароль дошёл до плана
    assert results[0].versions == {"id:1": "8.3.27.2214"}
    assert "pw" not in repr(results[0])


def test_failed_prepare_reports_none_without_details(
    qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    controller, runner = make_controller(tmp_path)
    runner.prepare_error = RuntimeError("пароль=секрет")
    results: list[Prepared] = []
    controller.prepared.connect(results.append)
    controller.request_prepare(dump_scenario(tmp_path), ["id:1"])
    assert results[0].plan is None
    assert "секрет" not in caplog.text and "RuntimeError" in caplog.text


def test_start_relays_events_writes_history_and_prunes(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = tuple(
        RunRecord("u0", "Старый", STARTED, str(tmp_path / "ops" / f"old{number}"), ())
        for number in range(operations_store.HISTORY_LIMIT)
    )
    controller, runner = make_controller(tmp_path, data=OperationsData(history=old))
    pruned: list[tuple[tuple[str, ...], Path]] = []
    monkeypatch.setattr(
        "onecstarter.ui.ops.controller.prune_logs",
        lambda dirs, root: pruned.append((tuple(dirs), root)),
    )
    started: list[RunInfo] = []
    events: list[object] = []
    finished: list[object] = []
    controller.run_started.connect(started.append)
    controller.run_event.connect(events.append)
    controller.run_finished.connect(finished.append)
    scenario = dump_scenario(tmp_path)

    assert controller.start(plan_for(controller, scenario, ["id:1", "id:9"]), parallel=True) is None

    info = started[0]
    run_dir = tmp_path / "ops" / "2026-11-14_090507_Ночной архив"
    assert info.scenario == scenario and info.logs_dir == str(run_dir)
    assert [(base.key, base.ready, base.problems) for base in info.bases] == [
        ("id:1", True, ()),
        ("id:9", False, (NOT_FOUND,)),
    ]
    assert info.bases[0].logs_dir == str(run_dir / "01_Бухгалтерия")
    # у неготовой базы каталога выгрузки нет  # noqa: RUF003
    assert info.bases[0].output_dir == str(tmp_path / "out") and info.bases[1].output_dir == ""
    assert [type(event).__name__ for event in events] == [
        "StepStarted",
        "StepFinished",
        "BaseFinished",
        "BaseFinished",
        "RunFinished",
    ]
    assert runner.run_calls[0]["parallel"] is True
    record = finished[0]
    assert isinstance(record, RunRecord) and record.scenario_name == "Ночной архив"
    assert not controller.running
    assert controller.history_count() == operations_store.HISTORY_LIMIT
    stored = load_operations(tmp_path / "operations.json").history
    assert stored[-1] == record and len(stored) == operations_store.HISTORY_LIMIT
    assert pruned == [((str(tmp_path / "ops" / "old0"),), tmp_path / "ops")]


def test_plan_is_not_kept_after_the_run(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path)
    plan = plan_for(controller, dump_scenario(tmp_path), ["id:1"])
    reference = weakref.ref(plan)
    controller.start(plan)
    del plan
    gc.collect()
    assert reference() is None


def _pending_plan(
    controller: OperationsController,
    pending: list[Callable[[], None]],
    tmp_path: Path,
    keys: list[str],
) -> RunPlan:
    results: list[Prepared] = []
    controller.prepared.connect(results.append)
    controller.request_prepare(dump_scenario(tmp_path), keys)
    pending.pop()()
    controller.prepared.disconnect(results.append)
    assert results[-1].plan is not None
    return results[-1].plan


def test_second_start_is_refused_while_running(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, runner = make_controller(tmp_path, spawn=pending.append)
    plan = _pending_plan(controller, pending, tmp_path, ["id:1"])
    assert controller.start(plan) is None
    assert controller.running
    assert controller.start(plan) == BUSY_TEXT
    assert len(pending) == 1
    pending.pop()()
    assert not controller.running and len(runner.run_calls) == 1


def test_cancel_reaches_the_token_of_the_active_run(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, runner = make_controller(tmp_path, spawn=pending.append)
    controller.cancel_soft()  # без запуска — ничего не происходит
    controller.start(_pending_plan(controller, pending, tmp_path, ["id:1"]))
    controller.cancel_soft()
    controller.cancel_hard()
    pending.pop()()
    assert (runner.run_calls[0]["soft"], runner.run_calls[0]["hard"]) == (True, True)


def test_quit_cancel_is_revoked_unless_the_panel_asked_too(qtbot: QtBot, tmp_path: Path) -> None:
    """Приёмка 21.11.2026, Р4."""  # noqa: RUF002
    pending: list[Callable[[], None]] = []
    controller, runner = make_controller(tmp_path, spawn=pending.append)
    controller.start(_pending_plan(controller, pending, tmp_path, ["id:1"]))
    controller.cancel_soft_for_quit()
    controller.revoke_quit_cancel()
    pending.pop()()
    assert runner.run_calls[0]["soft"] is False

    controller.start(_pending_plan(controller, pending, tmp_path, ["id:1"]))
    controller.cancel_soft()  # кнопка панели
    controller.cancel_soft_for_quit()
    controller.revoke_quit_cancel()
    pending.pop()()
    assert runner.run_calls[1]["soft"] is True

    # Финальное ревью плана А, T4-a: флаг «панель просила» не переживает запуск.  # noqa: RUF003
    controller.start(_pending_plan(controller, pending, tmp_path, ["id:1"]))
    controller.cancel_soft_for_quit()
    controller.revoke_quit_cancel()
    pending.pop()()
    assert runner.run_calls[2]["soft"] is False


def test_run_failure_frees_the_controller_and_reports(
    qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    controller, runner = make_controller(tmp_path)
    runner.run_error = OperationsBusyError(BUSY_TEXT)
    problems: list[str] = []
    finished: list[object] = []
    controller.problem.connect(problems.append)
    controller.run_finished.connect(finished.append)
    scenario = dump_scenario(tmp_path)
    controller.start(plan_for(controller, scenario, ["id:1"]))
    assert problems == [BUSY_TEXT] and finished == [None] and not controller.running

    runner.run_error = RuntimeError("пароль=секрет")
    controller.start(plan_for(controller, scenario, ["id:1"]))
    assert problems[-1] == (
        "Выполнение сценария прервано внутренней ошибкой — подробности в журнале программы"
    )
    assert "секрет" not in caplog.text and "RuntimeError" in caplog.text


def test_history_save_failure_is_reported_but_run_finishes(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, _ = make_controller(tmp_path)
    plan = plan_for(controller, dump_scenario(tmp_path), ["id:1"])

    def refuse(path: Path, data: OperationsData) -> None:
        raise OSError("диск занят")

    monkeypatch.setattr("onecstarter.ui.ops.controller.save_operations", refuse)
    problems: list[str] = []
    finished: list[object] = []
    controller.problem.connect(problems.append)
    controller.run_finished.connect(finished.append)
    controller.start(plan)
    assert problems == ["История запуска не сохранена: диск занят"]
    assert isinstance(finished[0], RunRecord) and controller.history_count() == 0


def test_quit_question_counts_finished_bases(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, _ = make_controller(tmp_path, spawn=pending.append)
    assert controller.quit_question() == ""
    controller.start(_pending_plan(controller, pending, tmp_path, ["id:1", "id:2"]))
    assert controller.quit_question() == (
        "Сценарий «Ночной архив» ещё выполняется: завершено баз — 0 из 2."
    )
    controller._raw_event.emit(BaseFinished(BaseResult("id:1", "Бухгалтерия", BaseOutcome.OK, ())))
    assert controller.quit_question() == (
        "Сценарий «Ночной архив» ещё выполняется: завершено баз — 1 из 2."
    )


def test_start_is_refused_while_the_runner_is_busy(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, runner = make_controller(tmp_path)
    plan = plan_for(controller, dump_scenario(tmp_path), ["id:1"])
    monkeypatch.setattr(type(runner), "running", property(lambda self: True))
    started: list[object] = []
    controller.run_started.connect(started.append)
    assert controller.start(plan) == BUSY_TEXT
    assert started == [] and runner.run_calls == [] and not controller.running


def test_spawn_failure_frees_the_controller(
    qtbot: QtBot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(task: Callable[[], None]) -> None:
        raise RuntimeError("пароль=секрет")

    controller, _ = make_controller(tmp_path)
    plan = plan_for(controller, dump_scenario(tmp_path), ["id:1"])
    controller._spawn = broken
    started: list[object] = []
    finished: list[object] = []
    controller.run_started.connect(started.append)
    controller.run_finished.connect(finished.append)
    assert controller.start(plan) == INTERNAL_FAILURE
    assert len(started) == 1 and finished == [None] and not controller.running
    assert "секрет" not in caplog.text and "RuntimeError" in caplog.text
    controller._spawn = lambda task: task()
    assert controller.start(plan) is None  # контроллер снова свободен


def test_events_arrive_in_the_main_thread_from_a_real_worker(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path, spawn=None)  # настоящие потоки-демоны
    seen: list[bool] = []
    controller.run_event.connect(
        lambda _event: seen.append(threading.current_thread() is threading.main_thread())
    )
    with qtbot.waitSignal(controller.prepared, timeout=5000) as prepared:
        controller.request_prepare(dump_scenario(tmp_path), ["id:1"])
    with qtbot.waitSignal(controller.run_finished, timeout=5000):
        assert controller.start(prepared.args[0].plan) is None
    assert seen and all(seen)
