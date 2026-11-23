"""Выход из программы при активном запуске сценария (спека v4, §6.6, §7.7; мокап, экран 7)."""

import pytest
from PySide6.QtCore import Qt

from onecstarter.ui.ops.quit_dialog import (
    QUIT_TITLE,
    QuitChoice,
    build_operations_quit_box,
    read_quit_choice,
)

MESSAGE = "Сценарий «X» ещё выполняется: завершено баз — 0 из 2."


def test_dialog_offers_three_answers_in_the_mockup_order(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = build_operations_quit_box(None, MESSAGE)
    qtbot.addWidget(dialog)
    dialog.resize(640, 160)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.windowTitle() == QUIT_TITLE == "Выполняется сценарий"
    assert dialog.text() == MESSAGE
    stay, wait, abort = (dialog.button(key) for key in ("stay", "wait", "abort"))
    assert [stay.text(), wait.text(), abort.text()] == [
        "Не выходить", "Дождаться шага и выйти", "Прервать и выйти",  # noqa: RUF001
    ]
    assert stay.x() < wait.x() < abort.x()
    assert (wait.property("role"), abort.property("role")) == ("primary", "danger")
    assert read_quit_choice(dialog) is QuitChoice.STAY  # закрыли без ответа — не выходить


@pytest.mark.parametrize(
    ("key", "choice"),
    [(Qt.Key.Key_Return, QuitChoice.WAIT), (Qt.Key.Key_Escape, QuitChoice.STAY)],
)
def test_enter_waits_and_escape_stays(qtbot, key, choice) -> None:  # type: ignore[no-untyped-def]
    """Страховка от случайного Enter: он не прерывает. Мутационная проверка — шаг 4."""
    dialog = build_operations_quit_box(None, MESSAGE)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.button("abort").setFocus()
    # Финальное ревью плана Б, F5: клавиша — в сфокусированную «Прервать и выйти».
    qtbot.keyClick(dialog.button("abort"), key)
    assert read_quit_choice(dialog) is choice


@pytest.mark.parametrize(
    ("key", "choice"),
    [("wait", QuitChoice.WAIT), ("abort", QuitChoice.ABORT), ("stay", QuitChoice.STAY)],
)
def test_each_button_maps_to_its_choice(qtbot, key, choice) -> None:  # type: ignore[no-untyped-def]
    dialog = build_operations_quit_box(None, "…")
    qtbot.addWidget(dialog)
    dialog.button(key).click()
    assert read_quit_choice(dialog) is choice
