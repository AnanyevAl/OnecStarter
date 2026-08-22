"""Единственный писатель settings.json: пишет целиком, не теряя чужих полей."""

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import Settings, ThemeMode, load_settings, save_settings
from onecstarter.ui.settings_store import SettingsStore


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def test_starts_from_file(application: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.LIGHT, recent_limit=3))
    store = SettingsStore(path)
    assert store.settings.theme is ThemeMode.LIGHT
    assert store.settings.recent_limit == 3


def test_missing_file_gives_defaults(application: QApplication, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    assert store.settings == Settings()


def test_update_persists_and_signals(application: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    seen: list[int] = []
    store.changed.connect(lambda: seen.append(1))

    store.update(recent_limit=0)

    assert store.settings.recent_limit == 0
    assert load_settings(path).recent_limit == 0
    assert seen == [1]


def test_update_keeps_other_fields(application: QApplication, tmp_path: Path) -> None:
    """Защитный: точечная правка не смеет затирать соседние поля.

    До вехи `ThemeController.set_mode` писал `Settings(theme=mode)` — целый
    файл из одного поля. С четырьмя полями это молча стирало бы выбор
    пользователя (спека §6.2). Мутация: вернуть в `update` запись
    `Settings(**changes)` вместо `replace` — тест обязан упасть.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.update(close_to_tray=False, hotkey="Win+F9", recent_limit=42)

    store.update(theme=ThemeMode.DARK)

    assert store.settings.close_to_tray is False
    assert store.settings.hotkey == "Win+F9"
    assert store.settings.recent_limit == 42
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["close_to_tray"] is False
    assert on_disk["hotkey"] == "Win+F9"
    assert on_disk["recent_limit"] == 42


def test_save_failure_is_reported_not_raised(
    application: QApplication, tmp_path: Path
) -> None:
    """Соврать «запомнили» нельзя: причина ложится в last_save_error.

    Препятствие — каталог на месте целевого файла: `atomic_write` не сможет
    переставить временный файл поверх него (тот же приём, что
    в `test_settings.py::test_save_reports_failure`).
    """
    path = tmp_path / "settings.json"
    path.mkdir()
    store = SettingsStore(path)

    store.update(recent_limit=1)

    assert store.last_save_error is not None
    assert "settings.json" in store.last_save_error
    # Значение всё равно применено: пользователь его выбрал.  # noqa: RUF003
    assert store.settings.recent_limit == 1


def test_successful_save_clears_previous_error(
    application: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "sub" / "settings.json"
    store = SettingsStore(path)
    store.last_save_error = "старая ошибка"

    store.update(recent_limit=2)

    assert store.last_save_error is None
