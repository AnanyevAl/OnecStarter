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


def test_show_run_sets_title_state_and_journal(  # type: ignore[no-untyped-def]
    qtbot, tmp_path: Path
) -> None:
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
    assert state_finished(7) == "завершено, код 7"  # неизвестный код — только число


@pytest.mark.parametrize(
    ("code", "text"),
    [
        (0, "завершено, код 0"),
        (1, "завершено, код 1 (CLI не запустился: нет 1cedt.ini или прав на временные файлы)"),
        (200, "завершено, код 200 (общая ошибка, см. журналы workspace)"),
        (202, "завершено, код 202 (workspace занят другим приложением)"),
        (204, "завершено, код 204 (команда прервана исключением, см. журналы workspace)"),
    ],
)
def test_state_finished_names_known_codes(code: int, text: str) -> None:
    # Таблица `help --status-codes` 1cedtcli.exe 2026.1.2+2 (Э7, 13.09.2026)
    assert state_finished(code) == text


@pytest.mark.parametrize(
    ("name", "label", "expected"),
    [("Розница", "Сборка", "Розница · Сборка"), ("Розница", "", "Розница"), ("", "", "")],
)
def test_title_drops_empty_parts(  # type: ignore[no-untyped-def]
    qtbot, name: str, label: str, expected: str
) -> None:
    console = EdtConsole(palette=DARK)
    qtbot.addWidget(console)
    console.show_run(name, label, STATE_RUNNING, None)
    assert console.title_label().text() == expected
