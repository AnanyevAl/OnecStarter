from pathlib import Path

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
    assert console.header_button().text().startswith(CONSOLE_TITLE)
    console.header_button().click()
    assert console.is_expanded() is True
    assert console.journal_panel().isHidden() is False
    console.collapse()
    assert console.is_expanded() is False


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
    assert state_finished(7) == "завершено, код 7"
