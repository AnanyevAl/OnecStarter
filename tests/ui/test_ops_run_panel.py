"""Панель хода выполнения (спека v4, §7.6): таблица «база × шаг», отмена, журнал, повтор."""  # noqa: RUF002

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QPlainTextEdit
from pytestqt.qtbot import QtBot

from onecstarter.domain.operations import BaseOutcome, Scenario, StepResult, StepStatus
from onecstarter.services.operations_runner import StepFinished, StepStarted, step_log_path
from onecstarter.ui.ops.controller import OperationsController
from onecstarter.ui.ops.run_panel import (
    ABORT_TEXT,
    ABORT_TITLE,
    ABORT_WARNING,
    RunPanel,
    Tone,
    abort_confirmed,
    build_abort_box,
    build_log_dialog,
    outcome_tone,
    step_tone,
    tone_colour,
)
from onecstarter.ui.theme import LIGHT
from tests.ui.ops_fakes import dump_scenario, make_controller, plan_for


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _panel(
    qtbot: QtBot, controller: OperationsController, **kwargs: Any
) -> tuple[RunPanel, list[str], list[tuple[str, str]], list[tuple[Scenario, list[str]]]]:
    opened: list[str] = []

    def open_path(path: str) -> bool:
        opened.append(path)
        return True

    logs: list[tuple[str, str]] = []
    retries: list[tuple[Scenario, list[str]]] = []
    panel = RunPanel(
        controller,
        open_path=open_path,
        show_log=lambda _parent, title, text: logs.append((title, text)),
        **kwargs,
    )
    qtbot.addWidget(panel)
    panel.retry_requested.connect(lambda scenario, keys: retries.append((scenario, list(keys))))
    return panel, opened, logs, retries


def test_idle_panel(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path)
    panel, _, _, _ = _panel(qtbot, controller)
    assert panel.header_text() == "В этом сеансе сценарии не запускались"  # noqa: RUF001
    assert panel.cells() == [] and panel.history_text() == "История: 0 запусков"
    for button in (
        panel.soft_button(),
        panel.hard_button(),
        panel.log_button(),
        panel.output_button(),
        panel.retry_button(),
    ):
        assert not button.isEnabled()


def test_finished_run_shows_cells_outcomes_and_summary(qtbot: QtBot, tmp_path: Path) -> None:
    controller, runner = make_controller(tmp_path)
    runner.outcomes["id:2"] = BaseOutcome.FAILED
    panel, _, _, retries = _panel(qtbot, controller)
    scenario = dump_scenario(tmp_path)

    controller.start(plan_for(controller, scenario, ["id:1", "id:2", "id:9"]))

    assert panel.column_titles() == ["База", "1. /DumpIB", "Итог"]
    assert panel.cells() == [
        ["Бухгалтерия", "✓ 00:02 · 0", "готово"],
        ["Склад", "✗ 00:02 · 1", "ошибка: объект захвачен"],
        ["", "—", "пропущена: база не найдена в списке"],
    ]
    assert panel.header_text() == (
        "Завершён «Ночной архив» · начато 14.11.2026 09:05 · готово: 1, с ошибкой: 1, пропущено: 1"  # noqa: RUF001
    )
    assert panel.history_text() == "История: 1 запуск"
    assert not panel.soft_button().isEnabled() and not panel.hard_button().isEnabled()
    assert panel.cell_tooltip(1, 1) == "объект захвачен"
    assert panel.retry_button().isEnabled()
    panel.retry_button().click()
    assert retries == [(scenario, ["id:2"])]


def test_running_step_ticks_and_buttons_follow_the_run(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, runner = make_controller(tmp_path, spawn=pending.append)
    clock = Clock()
    panel, _, _, _ = _panel(qtbot, controller, clock=clock)
    scenario = dump_scenario(tmp_path)
    controller.request_prepare(scenario, ["id:1", "id:2"])
    results: list[Any] = []
    controller.prepared.connect(results.append)
    pending.pop()()
    controller.start(results[-1].plan)

    assert panel.header_text() == "Выполняется «Ночной архив» · начато 14.11.2026 09:05"
    assert panel.cells() == [["Бухгалтерия", "ждёт", "ждёт"], ["Склад", "ждёт", "ждёт"]]
    assert panel.soft_button().isEnabled() and panel.hard_button().isEnabled()
    assert not panel.retry_button().isEnabled()

    controller.run_event.emit(StepStarted("id:1", 0))
    assert panel.cells()[0] == ["Бухгалтерия", "⟳ 00:00…", "выполняется"]
    clock.now += 37
    panel.tick()
    assert panel.cells()[0][1] == "⟳ 00:37…"
    controller.run_event.emit(
        StepFinished("id:1", 0, StepResult("/DumpIB", StepStatus.OK, 0, 41.0))
    )
    assert panel.cells()[0][1] == "✓ 00:41 · 0"

    panel.soft_button().click()
    assert not panel.soft_button().isEnabled() and panel.hard_button().isEnabled()
    assert panel.header_text().endswith(" · отмена после текущего шага")
    pending.pop()()
    assert runner.run_calls[0]["soft"] is True and runner.run_calls[0]["hard"] is False


def test_hard_cancel_asks_first(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pending: list[Callable[[], None]] = []
    controller, _ = make_controller(tmp_path, spawn=pending.append)
    answers = iter([False, True])
    panel, _, _, _ = _panel(qtbot, controller, confirm_abort=lambda _parent: next(answers))
    controller.request_prepare(dump_scenario(tmp_path), ["id:1"])
    results: list[Any] = []
    controller.prepared.connect(results.append)
    pending.pop()()
    controller.start(results[-1].plan)
    hard: list[int] = []
    monkeypatch.setattr(controller, "cancel_hard", lambda: hard.append(1))

    panel.hard_button().click()  # ответ «Продолжить выполнение»
    assert hard == []
    panel.hard_button().click()  # ответ «Прервать»
    assert hard == [1]


def test_abort_dialog_defaults_to_continue_and_warns(qtbot: QtBot) -> None:
    """Мокап (стр. 377–382): выноска о порче базы; «Прервать» опасная, «Продолжить» по умолчанию."""  # noqa: RUF002
    dialog = build_abort_box(None)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == ABORT_TITLE == "Прервать сейчас?"
    assert dialog.text() == ABORT_TEXT
    assert dialog.note_list().texts() == [ABORT_WARNING]
    assert dialog.note_list().levels() == ["warning"]
    keep, abort = dialog.button("keep"), dialog.button("abort")
    assert (keep.text(), abort.text()) == ("Продолжить выполнение", "Прервать")
    assert keep.isDefault() and keep.property("role") == "primary"
    assert abort.property("role") == "danger"
    assert not abort_confirmed(dialog)
    abort.click()
    assert abort_confirmed(dialog)


def test_step_log_is_read_by_fact_and_missing_log_is_explained(
    qtbot: QtBot, tmp_path: Path
) -> None:
    controller, _ = make_controller(tmp_path)
    panel, _, logs, _ = _panel(qtbot, controller)
    plan = plan_for(controller, dump_scenario(tmp_path), ["id:1", "id:2"])
    base_dir = plan.bases[0].logs_dir
    assert base_dir is not None
    base_dir.mkdir(parents=True)
    step_log_path(base_dir, 0).write_bytes(b"\xef\xbb\xbf" + "Выгрузка завершена".encode())
    controller.start(plan)

    panel.open_step_log("id:1", 0)
    panel.open_step_log("id:2", 0)
    assert logs == [
        ("Журнал: «Бухгалтерия», шаг 1 — Выгрузить информационную базу в файл .dt",
         "Выгрузка завершена"),
        ("Журнал: «Склад», шаг 1 — Выгрузить информационную базу в файл .dt",
         "Журнал шага пуст или ещё не создан."),
    ]


def test_open_buttons_use_the_selected_base(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path)
    panel, opened, _, _ = _panel(qtbot, controller)
    plan = plan_for(controller, dump_scenario(tmp_path), ["id:1", "id:9"])
    run_dir = str(plan.logs_dir)
    controller.start(plan)

    panel.log_button().click()  # строка не выбрана — каталог запуска
    panel.select_base("id:1")
    panel.log_button().click()
    panel.output_button().click()
    panel.select_base("id:9")  # в работу не шла
    panel.log_button().click()
    # своей выгрузки нет — первая база с выходным файлом  # noqa: RUF003
    panel.output_button().click()
    assert opened == [
        run_dir,
        str(plan.bases[0].logs_dir),
        str(tmp_path / "out"),
        run_dir,
        str(tmp_path / "out"),
    ]


def test_failed_launch_of_the_run_is_shown(qtbot: QtBot, tmp_path: Path) -> None:
    controller, runner = make_controller(tmp_path)
    runner.run_error = RuntimeError("сбой")
    panel, _, _, _ = _panel(qtbot, controller)
    controller.start(plan_for(controller, dump_scenario(tmp_path), ["id:1"]))
    assert panel.header_text() == "Запуск «Ночной архив» сорван ошибкой программы"
    assert not panel.soft_button().isEnabled() and not panel.retry_button().isEnabled()


def test_second_run_starts_from_a_clean_table(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    auto = [True]

    def spawn(task: Callable[[], None]) -> None:
        task() if auto[0] else pending.append(task)

    controller, runner = make_controller(tmp_path, spawn=spawn)
    runner.outcomes["id:2"] = BaseOutcome.FAILED
    panel, _, _, _ = _panel(qtbot, controller)
    scenario = dump_scenario(tmp_path)
    first = plan_for(controller, scenario, ["id:1", "id:2"])
    controller.start(first)
    assert panel.retry_button().isEnabled()
    assert panel.header_text().startswith("Завершён")

    auto[0] = False
    controller.start(first)  # второй запуск зависает на порождении

    assert panel.cells() == [["Бухгалтерия", "ждёт", "ждёт"], ["Склад", "ждёт", "ждёт"]]
    assert panel.header_text().startswith("Выполняется")
    assert not panel.retry_button().isEnabled()
    assert panel.cell_tooltip(1, 1) == "" and panel.cell_tooltip(1, 2) == ""


def test_one_second_timer_runs_only_while_the_run_is_active(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, _ = make_controller(tmp_path, spawn=pending.append)
    panel, _, _, _ = _panel(qtbot, controller)
    assert not panel.timer_active()
    controller.request_prepare(dump_scenario(tmp_path), ["id:1"])
    results: list[Any] = []
    controller.prepared.connect(results.append)
    pending.pop()()
    controller.start(results[-1].plan)
    assert panel.timer_active()
    pending.pop()()  # исполнитель доигрывает запуск
    assert panel.header_text().startswith("Завершён")
    assert not panel.timer_active()


def test_failed_run_does_not_leave_steps_looking_alive(qtbot: QtBot, tmp_path: Path) -> None:
    pending: list[Callable[[], None]] = []
    controller, runner = make_controller(tmp_path, spawn=pending.append)
    runner.run_error = RuntimeError("сбой")
    panel, _, _, _ = _panel(qtbot, controller)
    controller.request_prepare(dump_scenario(tmp_path), ["id:1", "id:2"])
    results: list[Any] = []
    controller.prepared.connect(results.append)
    pending.pop()()
    controller.start(results[-1].plan)
    controller.run_event.emit(StepStarted("id:1", 0))
    assert panel.cells()[0] == ["Бухгалтерия", "⟳ 00:00…", "выполняется"]

    pending.pop()()  # исполнитель падает -> run_finished(None)

    assert panel.header_text() == "Запуск «Ночной архив» сорван ошибкой программы"
    assert panel.cells() == [["Бухгалтерия", "—", "не завершена"], ["Склад", "—", "не завершена"]]


@pytest.mark.parametrize(
    ("result", "running", "tone"),
    [
        (None, False, Tone.MUTED),
        (None, True, Tone.RUNNING),
        (StepResult("/DumpIB", StepStatus.OK, 0, 2.0), False, Tone.OK),
        (StepResult("/DumpIB", StepStatus.FAILED, 1, 2.0), False, Tone.ERROR),
        (StepResult("/DumpIB", StepStatus.INTERRUPTED, None, 2.0), False, Tone.ERROR),
        (StepResult("/DumpIB", StepStatus.SKIPPED, None, 0.0), False, Tone.MUTED),
    ],
)
def test_step_tone(result: StepResult | None, running: bool, tone: Tone) -> None:
    """Мокап `.ok`, `.err`, `.run` (info), `.wait` (dim) — стр. 64, 366–368."""  # noqa: RUF002
    assert step_tone(result, running) is tone


@pytest.mark.parametrize(
    ("outcome", "tone"),
    [
        (BaseOutcome.OK, Tone.OK),
        (BaseOutcome.FAILED, Tone.ERROR),
        (BaseOutcome.INTERRUPTED, Tone.ERROR),
        (BaseOutcome.CANCELLED, Tone.WARNING),
        (BaseOutcome.NOT_READY, Tone.MUTED),
    ],
)
def test_outcome_tone(outcome: BaseOutcome, tone: Tone) -> None:
    assert outcome_tone(outcome) is tone


def test_tone_names_a_palette_role() -> None:
    assert tone_colour(Tone.OK, LIGHT) == LIGHT.running
    assert tone_colour(Tone.RUNNING, LIGHT) == LIGHT.info


def test_table_fills_the_panel_and_step_titles_are_short(qtbot: QtBot, tmp_path: Path) -> None:
    """В14, решение заказчика 6: «N. /Команда», полное название — подсказкой; шаги растягиваются."""  # noqa: RUF002
    controller, _ = make_controller(tmp_path)
    panel, _, _, _ = _panel(qtbot, controller)
    controller.start(plan_for(controller, dump_scenario(tmp_path), ["id:1", "id:2"]))
    assert panel.column_titles() == ["База", "1. /DumpIB", "Итог"]
    assert panel.header_tooltips() == ["", "1. Выгрузить информационную базу в файл .dt", ""]
    header = panel.table().horizontalHeader()
    mode = QHeaderView.ResizeMode
    assert [header.sectionResizeMode(column) for column in range(3)] == [
        mode.ResizeToContents, mode.Stretch, mode.ResizeToContents,
    ]
    assert header.defaultAlignment() & Qt.AlignmentFlag.AlignLeft
    assert panel.table().objectName() == "OpsTable" and not panel.table().showGrid()


def test_cells_are_coloured_by_status(qtbot: QtBot, tmp_path: Path) -> None:
    controller, runner = make_controller(tmp_path)
    runner.outcomes["id:2"] = BaseOutcome.FAILED
    panel, _, _, _ = _panel(qtbot, controller, palette=LIGHT)
    controller.start(plan_for(controller, dump_scenario(tmp_path), ["id:1", "id:2"]))
    assert (panel.cell_colour(0, 1), panel.cell_colour(0, 2)) == (LIGHT.running, LIGHT.running)
    assert (panel.cell_colour(1, 1), panel.cell_colour(1, 2)) == (LIGHT.problem, LIGHT.problem)


def test_header_bar_and_danger_abort(qtbot: QtBot, tmp_path: Path) -> None:
    controller, _ = make_controller(tmp_path)
    panel, _, _, _ = _panel(qtbot, controller)
    assert panel.header_bar().objectName() == "PanelHeader"
    assert panel.hard_button().property("role") == "danger"


def test_log_dialog_is_monospace(qtbot: QtBot) -> None:
    """Решение заказчика 3: окно журнала остаётся, текст моноширинный (`#CodePreview`)."""
    dialog = build_log_dialog(None, "Журнал", "текст")
    qtbot.addWidget(dialog)
    view = dialog.findChild(QPlainTextEdit)
    assert view is not None and view.objectName() == "CodePreview"
