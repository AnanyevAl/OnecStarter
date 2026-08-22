"""Контроллер темы: применение, сохранение, следование системе."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import Settings, ThemeMode, save_settings
from onecstarter.ui import theme
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.theme_controller import ThemeController


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def _controller(
    application: QApplication, path: Path, system: ThemeMode = ThemeMode.DARK
) -> ThemeController:
    return ThemeController(application, SettingsStore(path), system_mode=lambda: system)


def test_starts_from_saved_mode(application: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.LIGHT))
    controller = _controller(application, path)
    assert controller.mode is ThemeMode.LIGHT
    assert controller.palette is theme.LIGHT


def test_auto_follows_system(application: QApplication, tmp_path: Path) -> None:
    controller = _controller(application, tmp_path / "s.json", system=ThemeMode.LIGHT)
    assert controller.mode is ThemeMode.AUTO
    assert controller.palette is theme.LIGHT


def test_set_mode_applies_stylesheet_and_persists(
    application: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "settings.json"
    controller = _controller(application, path)
    seen: list[int] = []
    controller.changed.connect(lambda: seen.append(1))

    controller.set_mode(ThemeMode.LIGHT)

    assert controller.palette is theme.LIGHT
    assert theme.LIGHT.accent in application.styleSheet()
    assert path.exists()
    assert seen == [1]


def test_refresh_system_repaints_only_in_auto(
    application: QApplication, tmp_path: Path
) -> None:
    """В AUTO смена системной темы меняет палитру; при явном выборе — нет."""  # noqa: RUF002
    current = {"mode": ThemeMode.DARK}
    controller = ThemeController(
        application, SettingsStore(tmp_path / "s.json"), system_mode=lambda: current["mode"]
    )
    current["mode"] = ThemeMode.LIGHT
    controller.refresh_system()
    assert controller.palette is theme.LIGHT

    controller.set_mode(ThemeMode.DARK)
    current["mode"] = ThemeMode.LIGHT
    controller.refresh_system()
    assert controller.palette is theme.DARK


def test_controller_exposes_its_settings_path(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Разделу настроек нужен живой путь для подписи — не литерал %APPDATA%."""
    target = tmp_path / "settings.json"
    controller = ThemeController(qapp, SettingsStore(target), system_mode=lambda: ThemeMode.DARK)
    assert controller.path == target


def test_save_failure_is_reported_not_raised(
    application: QApplication, tmp_path: Path
) -> None:
    """Тема применяется, но приложение честно говорит, что не запомнило её.

    Молча проглотить отказ нельзя: пользователь решит, что выбор сохранён,
    и удивится при следующем запуске.
    """
    blocked = tmp_path / "busy"
    blocked.write_text("", encoding="utf-8")
    controller = _controller(application, blocked / "settings.json")

    controller.set_mode(ThemeMode.LIGHT)

    assert controller.palette is theme.LIGHT
    assert controller.last_save_error is not None
    assert "settings.json" in controller.last_save_error
