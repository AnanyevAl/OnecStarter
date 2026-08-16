"""Раздел «Настройки»: выбор темы и честное сообщение об отказе записи."""  # noqa: RUF002

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import ThemeMode
from onecstarter.ui.settings_view import SettingsView
from onecstarter.ui.theme_controller import ThemeController


def _view(
    qtbot: Any, application: QApplication, path: Path
) -> tuple[SettingsView, ThemeController]:
    controller = ThemeController(application, path, system_mode=lambda: ThemeMode.DARK)
    view = SettingsView(controller)
    qtbot.addWidget(view)
    return view, controller


def test_three_choices_with_current_selected(
    qtbot: Any, qapp: QApplication, tmp_path: Path
) -> None:
    view, _ = _view(qtbot, qapp, tmp_path / "s.json")
    assert [button.text() for button in view.theme_buttons()] == [
        "Авто",
        "Светлая",
        "Тёмная",
    ]
    assert view.theme_buttons()[0].isChecked()


def test_header_shows_the_live_settings_path(
    qtbot: Any, qapp: QApplication, tmp_path: Path
) -> None:
    view, controller = _view(qtbot, qapp, tmp_path / "s.json")
    assert str(controller.path) in view.path_text()
    assert "применяются сразу" in view.path_text()


def test_choice_switches_theme(qtbot: Any, qapp: QApplication, tmp_path: Path) -> None:
    view, controller = _view(qtbot, qapp, tmp_path / "s.json")
    view.theme_buttons()[1].click()
    assert controller.mode is ThemeMode.LIGHT


def test_save_failure_is_visible(qtbot: Any, qapp: QApplication, tmp_path: Path) -> None:
    """Отказ записи виден в разделе, а не только в поле контроллера."""  # noqa: RUF002
    blocked = tmp_path / "busy"
    blocked.write_text("", encoding="utf-8")
    view, _ = _view(qtbot, qapp, blocked / "settings.json")
    view.theme_buttons()[1].click()
    assert "не удалось сохранить" in view.status_text().casefold()
