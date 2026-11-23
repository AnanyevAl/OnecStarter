"""Окно запуска сценария (спека v4, §7.5): готовность, пароли, заменяющий сценарий."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView
from pytestqt.qtbot import QtBot

from onecstarter.domain.operations import BUILTIN_SCENARIOS, BaseRef, Scenario, Step
from onecstarter.domain.operations_text import (
    PASSWORD_ARGV_NOTE,
    PASSWORD_ONCE_NOTE,
    replace_warning,
)
from onecstarter.services.model import InfobaseItem
from onecstarter.ui.ops.run_dialog import (
    CHECK_FAILED,
    HEADERS,
    LOGIN_COLUMN_MAX,
    READY_SKIPPED,
    REASONS_MAX_HEIGHT,
    REASONS_SHOWN,
    TABLE_MIN_ROWS,
    PasswordCell,
    RunDialog,
    RunRequest,
)
from onecstarter.ui.theme import DARK, stylesheet
from tests.ui.ops_fakes import ScriptedRunner, dump_scenario, make_controller, sync, target

RESTORE = next(s for s in BUILTIN_SCENARIOS if s.id == "builtin:restore-dt")


def _setup(
    qtbot: QtBot,
    tmp_path: Path,
    workspace_factory: Any,
    scenario: Scenario | None = None,
    *,
    second: dict[str, Any] | None = None,
    checked: int = 2,
    spawn: Callable[[Callable[[], None]], None] | None = None,
    missing: tuple[BaseRef, ...] = (),
) -> tuple[RunDialog, list[InfobaseItem], ScriptedRunner]:
    """Окно над двумя первыми базами фикстуры; вторая — с пользователем без пароля."""  # noqa: RUF002
    workspace, _, _ = workspace_factory()
    items = workspace.items()
    bases = [item for item in items if not item.is_group][:2]
    targets = {
        bases[0].key: target(bases[0].key, bases[0].name),
        bases[1].key: target(
            bases[1].key, bases[1].name, **({"login": "Иванов"} if second is None else second)
        ),
    }
    controller, runner = make_controller(
        tmp_path, targets=targets, spawn=sync if spawn is None else spawn
    )
    dialog = RunDialog(
        controller,
        scenario or dump_scenario(tmp_path),
        items,
        checked=[base.key for base in bases[:checked]],
        missing=missing,
        delay_ms=0,
    )
    qtbot.addWidget(dialog)
    dialog.refresh_now()
    return dialog, bases, runner


def _cell(dialog: RunDialog, key: str) -> PasswordCell:
    cell = dialog.password_cell(key)
    assert cell is not None
    return cell


def _outcome(dialog: RunDialog) -> RunRequest:
    request = dialog.outcome()
    assert request is not None
    return request


def _credentials(request: RunRequest, index: int) -> str | None:
    credentials = request.plan.bases[index].credentials
    assert credentials is not None
    return credentials.password


def test_readiness_table_and_action_count(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    assert dialog.windowTitle() == "Выполнить сценарий «Ночной архив»"
    assert dialog.table_rows() == [
        [bases[0].name, "8.3.27.2214", "без пользователя", "✓"],
        [
            bases[1].name,
            "8.3.27.2214",
            "Иванов · пароль не сохранён",
            READY_SKIPPED,
        ],
    ]
    assert dialog.reasons_text() == f"{bases[1].name}: нужен пароль пользователя «Иванов»"
    assert dialog.password_cell(bases[0].key) is None
    assert dialog.password_cell(bases[1].key) is not None
    assert not dialog.repository_column_visible()
    action = dialog.action_button()
    assert action.text() == "Выполнить для 1 базы" and action.isEnabled() and action.isDefault()
    assert dialog.warning_text() == ""
    assert "может понадобиться монопольный доступ" in dialog.notes_text()
    assert dialog.footer_hint_text() == PASSWORD_ONCE_NOTE
    assert PASSWORD_ARGV_NOTE in dialog.notes_text()


def test_typed_password_makes_the_base_ready_and_reaches_the_plan(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    cell = _cell(dialog, bases[1].key)
    cell.set_text("Секрет-42")
    assert not dialog.action_button().isEnabled()  # план устарел в момент правки
    assert dialog.status_text() == "Проверка готовности…"
    dialog.refresh_now()

    assert dialog.password_cell(bases[1].key) is cell  # поле не пересоздано
    assert dialog.table_rows()[1][2:] == ["Иванов", "✓"]
    assert dialog.action_button().text() == "Выполнить для 2 баз"
    dialog.parallel_checkbox().setChecked(True)
    dialog.action_button().click()
    request = _outcome(dialog)
    assert request is not None and request.parallel and not request.remember
    assert [base.ready for base in request.plan.bases] == [True, True]
    assert _credentials(request, 1) == "Секрет-42"
    assert request.refs == (
        BaseRef(bases[0].key, bases[0].name),
        BaseRef(bases[1].key, bases[1].name),
    )
    assert "Секрет-42" not in repr(request)


def test_empty_password_checkbox_sends_an_empty_password(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    cell = _cell(dialog, bases[1].key)
    assert cell.value() is None
    cell.set_empty(True)
    assert cell.value() == ""
    dialog.refresh_now()
    dialog.action_button().click()
    assert _credentials(_outcome(dialog), 1) == ""


def test_unchecking_bases_updates_rows_and_disables_the_action(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    dialog.checklist().set_checked(bases[1].key, False)
    dialog.refresh_now()
    assert [row[0] for row in dialog.table_rows()] == [bases[0].name]
    dialog.checklist().set_checked(bases[0].key, False)
    dialog.refresh_now()
    assert dialog.table_rows() == []
    assert not dialog.action_button().isEnabled()
    assert dialog.action_button().text() == "Выполнить для 0 баз"
    assert dialog.status_text() == "Отметьте базы слева"


def test_replacing_scenario_asks_for_the_file_and_defaults_to_cancel(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, RESTORE, checked=1)
    action = dialog.action_button()
    assert action.text() == "Заменить данные 0 баз" and not action.isEnabled()
    assert dialog.cancel_button().isDefault() and not action.isDefault()
    assert action.autoDefault() is False
    assert "не задан обязательный параметр «файл выгрузки»" in dialog.reasons_text()

    source = tmp_path / "source.dt"
    source.write_bytes(b"dt")
    dialog.set_input(0, 0, str(source))
    dialog.refresh_now()

    assert dialog.table_rows()[0][3] == "✓"
    assert action.text() == "Заменить данные 1 базы" and action.isEnabled()
    assert dialog.warning_text() == replace_warning(1)
    assert not dialog.remember_checkbox().isEnabled()  # заготовку не изменить
    action.click()
    request = _outcome(dialog)
    assert request.scenario.steps[0].values[0] == str(source)
    assert RESTORE.steps[0].values == (None,)  # сама заготовка не тронута


def test_remember_is_offered_for_own_scenarios(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory, checked=1)
    assert dialog.remember_checkbox().isEnabled()
    dialog.remember_checkbox().setChecked(True)
    dialog.action_button().click()
    request = _outcome(dialog)
    assert request.remember and request.refs == (BaseRef(bases[0].key, bases[0].name),)


def test_repository_password_column_for_repository_scenarios(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    scenario = Scenario("u2", "Из хранилища", (Step("/ConfigurationRepositoryUpdateCfg"),))
    dialog, bases, _ = _setup(
        qtbot, tmp_path, workspace_factory, scenario, second={"repository_user": "dev"}
    )
    assert dialog.repository_column_visible()
    assert dialog.table_rows()[0][3] == READY_SKIPPED
    assert dialog.table_rows()[1][3] == READY_SKIPPED
    assert "не задан пользователь хранилища конфигурации" in dialog.reasons_text()
    assert "нужен пароль хранилища конфигурации" in dialog.reasons_text()
    repository = dialog.repository_cell(bases[1].key)
    assert repository is not None
    repository.set_text("rp")
    dialog.refresh_now()
    assert dialog.table_rows()[1][3] == "✓"
    dialog.action_button().click()
    access = _outcome(dialog).plan.bases[1].repository
    assert access is not None and access.password == "rp"


def test_only_the_latest_readiness_result_is_shown(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    pending: list[Callable[[], None]] = []
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory, spawn=pending.append)
    assert dialog.table_rows() == [] and dialog.status_text() == "Проверка готовности…"
    dialog.checklist().set_checked(bases[1].key, False)
    dialog.refresh_now()
    assert len(pending) == 2
    pending[1]()  # свежий результат пришёл первым
    assert [row[0] for row in dialog.table_rows()] == [bases[0].name]
    pending[0]()  # устаревший — отброшен
    assert [row[0] for row in dialog.table_rows()] == [bases[0].name]
    assert dialog.action_button().isEnabled()


def test_result_in_flight_before_a_change_is_dropped(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    pending: list[Callable[[], None]] = []
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory, spawn=pending.append)
    dialog._timer.setInterval(60_000)  # новый запрос ещё не ушёл
    dialog.checklist().set_checked(bases[1].key, False)
    assert not dialog.action_button().isEnabled()
    pending[0]()  # результат запроса, ушедшего до правки, приходит до таймера
    assert dialog.table_rows() == []
    assert not dialog.action_button().isEnabled()
    assert dialog.status_text() == "Проверка готовности…"

    dialog.refresh_now()
    assert len(pending) == 2
    pending[1]()
    assert [row[0] for row in dialog.table_rows()] == [bases[0].name]
    assert dialog.action_button().isEnabled()


def test_run_refuses_a_plan_for_other_bases(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    assert dialog.action_button().isEnabled()
    dialog.checklist().blockSignals(True)  # правка прошла мимо окна: вторая линия защиты
    dialog.checklist().set_checked(bases[0].key, False)
    dialog.checklist().blockSignals(False)
    dialog.action_button().click()
    assert dialog.outcome() is None


def test_password_survives_uncheck_and_recheck(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    _cell(dialog, bases[1].key).set_text("Секрет-42")
    dialog.refresh_now()
    dialog.checklist().set_checked(bases[1].key, False)
    dialog.refresh_now()
    assert dialog.password_cell(bases[1].key) is None
    dialog.checklist().set_checked(bases[1].key, True)
    dialog.refresh_now()
    assert (
        dialog.table_rows()[1][3] == "✓"
    )  # поле показывает пароль — проверка его получила  # noqa: RUF003
    dialog.action_button().click()
    assert _credentials(_outcome(dialog), 1) == "Секрет-42"


def test_empty_flag_survives_uncheck_and_recheck(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    _cell(dialog, bases[1].key).set_empty(True)
    dialog.refresh_now()
    dialog.checklist().set_checked(bases[1].key, False)
    dialog.refresh_now()
    dialog.checklist().set_checked(bases[1].key, True)
    dialog.refresh_now()
    assert dialog.table_rows()[1][3] == "✓"


def test_accepting_wipes_passwords_but_keeps_the_request(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    cell = _cell(dialog, bases[1].key)
    cell.set_text("Секрет-42")
    dialog.refresh_now()
    dialog.action_button().click()

    request = _outcome(dialog)
    assert _credentials(request, 1) == "Секрет-42"  # запрос — то, что возвращает окно
    assert cell.value() is None and cell.state() == ("", False)
    assert dialog._plan is None
    for held in (*dialog._cells.values(), *dialog._repository_cells.values()):
        assert held.value() is None
    dialog.forget()
    assert dialog.outcome() is None


def test_accepting_wipes_saved_passwords_of_unchecked_bases(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    _cell(dialog, bases[1].key).set_text("Секрет-42")
    dialog.refresh_now()
    dialog.checklist().set_checked(bases[1].key, False)  # пароль уходит в сохранённые
    dialog.refresh_now()
    assert dialog._saved[bases[1].key] == ("Секрет-42", False)
    dialog.action_button().click()
    assert _outcome(dialog).refs == (BaseRef(bases[0].key, bases[0].name),)
    assert not dialog._saved and not dialog._saved_repository


def test_missing_saved_base_is_shown_as_not_found(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, _bases, _ = _setup(
        qtbot,
        tmp_path,
        workspace_factory,
        checked=0,
        missing=(BaseRef("id:gone", "Розница старая"),),
    )
    assert dialog.table_rows() == [["", "", "без пользователя", READY_SKIPPED]]
    assert dialog.reasons_text() == "Розница старая: база не найдена в списке"
    assert not dialog.action_button().isEnabled()


def test_failed_readiness_check_is_reported(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, _bases, runner = _setup(qtbot, tmp_path, workspace_factory)
    assert dialog.reasons_text()  # вторая база ждёт пароль
    runner.prepare_error = RuntimeError("сбой")
    dialog.refresh_now()
    assert dialog.status_text() == (
        "Проверка готовности не удалась — подробности в журнале программы"
    )
    assert not dialog.action_button().isEnabled()
    # Предпроверка, п. 18: причины прошлого расчёта не остаются под таблицей.
    assert dialog.reasons_text() == ""
    assert dialog.reasons_list().isHidden()


def test_closing_without_run_forgets_plan_and_passwords(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    cell = _cell(dialog, bases[1].key)
    cell.set_text("Секрет-42")
    dialog.refresh_now()
    dialog.reject()
    assert dialog.outcome() is None and cell.value() is None

    again, bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    again.action_button().click()
    assert again.outcome() is not None
    again.forget()
    assert again.outcome() is None


def test_columns_fit_their_content_and_readiness_stretches(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """В13 (приёмка 21.11.2026): «Вход» и «Готовность» читаются при обычной ширине окна."""  # noqa: RUF002
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    table = dialog.table()
    header = table.horizontalHeader()
    mode = QHeaderView.ResizeMode
    assert [header.sectionResizeMode(column) for column in range(6)] == [
        mode.ResizeToContents, mode.ResizeToContents, mode.Interactive,
        mode.Fixed, mode.Fixed, mode.Stretch,
    ]
    assert table.columnWidth(2) <= LOGIN_COLUMN_MAX
    assert table.wordWrap() and not table.showGrid()
    assert table.objectName() == "OpsTable"
    assert header.defaultAlignment() & Qt.AlignmentFlag.AlignLeft


def test_row_height_follows_the_width_of_the_readiness_column(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Финальное ревью плана Б, F3: «Готовность» растянута и переносится — высота строк
    следует за шириной окна, а не только за заполнением таблицы.

    Ширины — с запасом под колонки по содержимому (~840 px на офскрине): при 1300 px на
    «Готовность» остаётся около 70 px, при 2400 — больше 1100.
    """  # noqa: RUF002
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    table = dialog.table()
    assert table.verticalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    item = table.item(0, 5)
    assert item is not None
    item.setText(" ".join(["причина"] * 30))
    dialog.resize(2400, 500)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: table.columnWidth(5) > 1000, timeout=2000)
    qtbot.waitUntil(lambda: table.rowHeight(0) == table.sizeHintForRow(0), timeout=2000)
    wide = table.rowHeight(0)
    dialog.resize(1300, 500)
    qtbot.waitUntil(lambda: table.rowHeight(0) > wide, timeout=2000)
    assert table.rowHeight(0) == table.sizeHintForRow(0)
    dialog.resize(2400, 500)
    qtbot.waitUntil(lambda: table.rowHeight(0) == wide, timeout=2000)


def test_readiness_and_login_cells_are_coloured(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап `.ok`, `.err`, `.warnc` (стр. 64, 327-330)."""
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    table = dialog.table()
    ready_ok, ready_bad, login = table.item(0, 5), table.item(1, 5), table.item(1, 2)
    assert ready_ok is not None and ready_bad is not None and login is not None
    assert ready_ok.foreground().color().name() == DARK.running
    assert ready_bad.foreground().color().name() == DARK.problem
    assert login.foreground().color().name() == DARK.warning
    assert login.toolTip() == login.text()


def test_plain_scenario_runs_from_a_primary_button(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Решение заказчика 1, мокап (стр. 338). Мутационная проверка — шаг 6."""
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    assert dialog.action_button().property("role") == "primary"
    assert dialog.cancel_button().property("role") is None


def test_replacing_scenario_has_a_danger_action_and_a_primary_cancel(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап (стр. 352): «Заменить данные» — красная рамка, «Отмена» — жёлтая и по умолчанию."""
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, RESTORE, checked=1)
    assert dialog.action_button().property("role") == "danger"
    assert dialog.cancel_button().property("role") == "primary"
    assert dialog.cancel_button().isDefault()


def test_notes_are_callouts_and_the_once_note_is_in_the_footer(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory)
    assert set(dialog.notes_list().levels()) == {"warning", "info"}
    assert PASSWORD_ARGV_NOTE in dialog.notes_text()
    assert PASSWORD_ONCE_NOTE not in dialog.notes_text()
    assert dialog.footer_hint_text() == PASSWORD_ONCE_NOTE


def test_replace_warning_is_an_error_callout_with_a_bold_lead(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап `.msg.err` с жирной первой фразой (стр. 350)."""  # noqa: RUF002
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, RESTORE, checked=1)
    source = tmp_path / "source.dt"
    source.write_bytes(b"dt")
    dialog.set_input(0, 0, str(source))
    dialog.refresh_now()
    assert dialog.warning_list().levels() == ["error"]
    label = dialog.warning_list().labels()[0]
    assert label.text().startswith("<b>Данные 1 базы будут полностью заменены.</b>")
    assert dialog.warning_text() == replace_warning(1)


def test_readiness_cell_is_short_and_reasons_are_callouts(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """План В, Б3: в ячейке — «✗ будет пропущена», «Вход» не шире 150, «Готовность» — остаток.

    Предпроверка 22.11.2026, п. 1: шрифты офскрина примерно в 1,5 раза шире Segoe UI, при 980
    «Готовность» здесь на минимуме секции. Поэтому при 980 проверяется то, что от шрифта не
    зависит, «вмещает текст» — при 1300, а «читается при 980» — живой чек-лист, п. 3.
    """  # noqa: RUF002
    dialog, _, _ = _setup(qtbot, tmp_path, workspace_factory)
    dialog.resize(980, 560)
    dialog.show()
    qtbot.waitExposed(dialog)
    table = dialog.table()
    assert dialog.table_rows()[1][3] == READY_SKIPPED
    assert table.columnWidth(2) <= LOGIN_COLUMN_MAX
    assert not dialog.reasons_list().isHidden()
    others = sum(
        table.columnWidth(column) for column in range(5) if not table.isColumnHidden(column)
    )
    assert table.columnWidth(5) >= table.viewport().width() - others - 2
    dialog.resize(1300, 560)
    metrics = table.fontMetrics()
    qtbot.waitUntil(
        lambda: table.columnWidth(5) >= metrics.horizontalAdvance(READY_SKIPPED) + 16,
        timeout=2000,
    )
    qtbot.waitUntil(lambda: table.rowHeight(1) <= 3 * metrics.height() + 12, timeout=2000)


def test_missing_base_without_a_name_is_called_unnamed(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Предпроверка плана В, п. 17: «база без имени» — только если имени нет и в списке."""  # noqa: RUF002
    dialog, _bases, _ = _setup(
        qtbot, tmp_path, workspace_factory, checked=0, missing=(BaseRef("id:gone", ""),)
    )
    assert dialog.reasons_text() == "база без имени: база не найдена в списке"


def test_reasons_scroll_and_table_keeps_three_rows(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """План В, Б3′ (решение заказчика 22.11.2026): при 980×560 и многих неготовых базах
    выноски — в области прокрутки не выше REASONS_MAX_HEIGHT, таблица — не ниже шапки и
    трёх строк, окно не растёт."""  # noqa: RUF002
    long = "Очень длинное имя неготовой информационной базы для переноса причины " * 3
    missing = tuple(BaseRef(f"id:gone{index}", f"{long}{index}") for index in range(7))
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, checked=0, missing=missing)
    dialog.resize(980, 560)
    dialog.show()
    qtbot.waitExposed(dialog)
    area = dialog.reasons_area()
    labels = dialog.reasons_list().labels()
    qtbot.waitUntil(lambda: area.isVisible() and len(labels) == REASONS_SHOWN + 1)
    table = dialog.table()
    assert dialog.height() == 560
    floor = (
        table.horizontalHeader().height()
        + TABLE_MIN_ROWS * table.verticalHeader().defaultSectionSize()
    )
    assert table.minimumHeight() >= floor
    assert table.height() >= table.minimumHeight()
    assert area.height() <= REASONS_MAX_HEIGHT
    assert area.maximumHeight() <= REASONS_MAX_HEIGHT  # не вырастет и в большом окне
    assert area.verticalScrollBar().maximum() > 0  # и есть куда прокручивать
    qtbot.waitUntil(lambda: area.verticalScrollBar().isVisibleTo(area))  # полоса видна
    # Содержимое выше области — иначе проверка прокрутки ничего не доказывает.
    assert dialog.reasons_list().height() > area.height()
    last = labels[-1]
    assert last.text().startswith("и ещё 2 базы")
    area.ensureWidgetVisible(last)
    top = last.mapTo(area.viewport(), last.rect().topLeft()).y()
    bottom = last.mapTo(area.viewport(), last.rect().bottomLeft()).y()
    assert top >= 0 and bottom <= area.viewport().height()


def test_reasons_area_is_hidden_without_reasons(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Пустого зазора в 96 px под таблицей нет: нет выносок — нет и области."""
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, checked=0)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert not dialog.reasons_area().isVisible()


def test_reasons_scrollbar_is_hidden_for_a_short_list(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Ревью Б3′, M1: одна выноска помещается — полосы прокрутки нет."""  # noqa: RUF002
    missing = (BaseRef("id:gone", "Старая"),)
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, checked=0, missing=missing)
    dialog.show()
    qtbot.waitExposed(dialog)
    area = dialog.reasons_area()
    assert area.isVisible()
    assert not area.verticalScrollBar().isVisibleTo(area)


def test_reasons_gap_is_painted_with_the_dialog_background(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Ревью Б3′, I1: `QScrollArea.setWidget` включает заливку содержимого цветом Window
    системы — между выносками была светлая полоса (#efefef) в обеих темах."""  # noqa: RUF002
    missing = tuple(BaseRef(f"id:gone{index}", f"Старая {index}") for index in range(3))
    dialog, _bases, _ = _setup(qtbot, tmp_path, workspace_factory, checked=0, missing=missing)
    dialog.setStyleSheet(stylesheet(DARK))
    dialog.resize(980, 560)
    dialog.show()
    qtbot.waitExposed(dialog)
    first, second = dialog.reasons_list().labels()[:2]
    gap = (first.geometry().bottom() + second.geometry().top()) // 2
    # Снимок всего окна: `grab()` области сам заливает прозрачный фон цветом Window.
    point = dialog.reasons_list().mapTo(dialog, QPoint(first.geometry().center().x(), gap))
    pixel = dialog.grab().toImage().pixelColor(point)
    assert pixel == QColor(DARK.background)


def test_readiness_failure_hides_the_reasons_area(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Ревью Б3′, M2: сорвавшаяся проверка стирает причины прошлого расчёта и прячет область."""  # noqa: RUF002
    missing = (BaseRef("id:gone", "Старая"),)
    dialog, _bases, runner = _setup(
        qtbot, tmp_path, workspace_factory, checked=0, missing=missing
    )
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.reasons_area().isVisible()
    runner.prepare_error = RuntimeError("сбой")
    dialog.refresh_now()
    assert dialog.status_text() == CHECK_FAILED
    assert dialog.reasons_text() == ""
    assert not dialog.reasons_area().isVisible()


@pytest.mark.parametrize(("count", "shown"), [(5, 5), (7, 6)])
def test_reason_callouts_are_capped(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any, count: int, shown: int
) -> None:
    """Решение заказчика 22.11.2026 (предпроверка, п. 28): не больше пяти выносок причин,
    остальные базы — одной выноской, иначе выноски сжимают таблицу до шапки."""
    missing = tuple(BaseRef(f"id:gone{index}", f"Старая {index}") for index in range(count))
    dialog, _bases, _ = _setup(
        qtbot, tmp_path, workspace_factory, checked=0, missing=missing
    )
    labels = dialog.reasons_list().labels()
    assert len(labels) == shown
    assert labels[0].text().startswith("Старая 0: база не найдена в списке")
    if count > REASONS_SHOWN:
        assert labels[-1].text() == (
            "и ещё 2 базы — причины в подсказке ячейки «Готовность»"
        )
        # Скрытая выноской база: причина лежит в подсказке «Готовности».
        ready = dialog.table().item(count - 1, HEADERS.index("Готовность"))
        assert ready is not None
        assert "база не найдена в списке" in ready.toolTip()
    else:
        assert labels[-1].text().startswith("Старая 4: база не найдена в списке")
