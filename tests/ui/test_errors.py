"""Tests for error dialogs."""

from PySide6.QtWidgets import QApplication

from onecstarter.services.errors import LaunchError
from onecstarter.ui.errors import build_error_box


def test_box_shows_message_and_copy_button(qtbot):
    error = LaunchError("Не удалось запустить: Команда: \"C:\\bin\\1cv8c.exe\" ENTERPRISE")  # noqa: RUF001
    box = build_error_box(None, error)
    assert "1cv8c.exe" in box.text()
    labels = [button.text() for button in box.buttons()]
    assert "Скопировать" in labels


def test_copy_button_puts_message_into_clipboard(qtbot):
    error = LaunchError("текст для отчёта")
    box = build_error_box(None, error)
    copy_button = next(b for b in box.buttons() if b.text() == "Скопировать")
    copy_button.click()
    assert QApplication.clipboard().text() == "текст для отчёта"
