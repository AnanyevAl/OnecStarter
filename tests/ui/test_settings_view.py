"""Раздел «Настройки»: четыре группы мокапа."""

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.services.autostart import VALUE_NAME, autostart_command
from onecstarter.services.settings import Settings, ThemeMode, save_settings
from onecstarter.ui.hotkey_edit import HotkeyEdit
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.settings_view import SettingsView
from onecstarter.ui.theme_controller import ThemeController

EXE = r"C:\Programs\OneCStarter\OneCStarter.exe"


class FakeRegistry:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, data: str) -> None:
        self.values[name] = data

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


class BrokenRegistry(FakeRegistry):
    def write(self, name: str, data: str) -> None:
        raise PermissionError(5, "отказано в доступе")


class UnreadableRegistry(FakeRegistry):
    def read(self, name: str) -> str | None:
        raise PermissionError(5, "отказано в доступе")


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def _view(
    application: QApplication,
    tmp_path: Path,
    *,
    registry: FakeRegistry | None = None,
    frozen: bool = True,
    on_hotkey: Callable[[str], str | None] | None = None,
) -> tuple[SettingsView, SettingsStore]:
    store = SettingsStore(tmp_path / "settings.json")
    controller = ThemeController(application, store, system_mode=lambda: ThemeMode.DARK)
    view = SettingsView(
        controller,
        store,
        autostart_registry=registry if registry is not None else FakeRegistry(),
        frozen=frozen,
        executable=EXE,
        on_hotkey=on_hotkey,
    )
    return view, store


# -- тема (существовали до этой задачи, конструктор подогнан под новую
# сигнатуру SettingsView(controller, store, ...); проверка того же
# поведения, только через store вместо снятого из _view контроллера) -------


def test_three_choices_with_current_selected(
    application: QApplication, tmp_path: Path
) -> None:
    view, _ = _view(application, tmp_path)
    assert [button.text() for button in view.theme_buttons()] == [
        "Авто",
        "Светлая",
        "Тёмная",
    ]
    assert view.theme_buttons()[0].isChecked()


def test_header_shows_the_live_settings_path(
    application: QApplication, tmp_path: Path
) -> None:
    view, store = _view(application, tmp_path)
    assert str(store.path) in view.path_text()
    assert "применяются сразу" in view.path_text()


def test_choice_switches_theme(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path)
    view.theme_buttons()[1].click()
    assert store.settings.theme is ThemeMode.LIGHT


def test_save_failure_is_visible(application: QApplication, tmp_path: Path) -> None:
    """Отказ записи виден в разделе, а не только в поле контроллера."""  # noqa: RUF002
    blocked = tmp_path / "busy"
    blocked.write_text("", encoding="utf-8")
    store = SettingsStore(blocked / "settings.json")
    controller = ThemeController(application, store, system_mode=lambda: ThemeMode.DARK)
    view = SettingsView(
        controller,
        store,
        autostart_registry=FakeRegistry(),
        frozen=True,
        executable=EXE,
    )
    view.theme_buttons()[1].click()
    assert "не удалось сохранить" in view.status_text().casefold()


# -- четыре группы мокапа -----------------------------------------------------


def test_groups_are_in_mockup_order(application: QApplication, tmp_path: Path) -> None:
    view, _ = _view(application, tmp_path)
    assert view.group_labels() == [
        "ВНЕШНИЙ ВИД",
        "ОКНО И ЗАПУСК",  # noqa: RUF001
        "ГОРЯЧИЕ КЛАВИШИ",
        "СПИСОК БАЗ",
    ]


def test_tray_toggle_persists(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path)
    assert view.tray_checkbox().isChecked() is True

    view.tray_checkbox().setChecked(False)

    assert store.settings.close_to_tray is False


def test_tray_toggle_starts_from_file(application: QApplication, tmp_path: Path) -> None:
    save_settings(tmp_path / "settings.json", Settings(close_to_tray=False))
    view, _ = _view(application, tmp_path)
    assert view.tray_checkbox().isChecked() is False


def test_autostart_disabled_when_not_frozen(
    application: QApplication, tmp_path: Path
) -> None:
    """Из исходников автозапуск недоступен: ссылка в реестре протухнет (спека §3.3)."""
    view, _ = _view(application, tmp_path, frozen=False)
    assert view.autostart_checkbox().isEnabled() is False
    assert "установленной версии" in view.autostart_note()


def test_autostart_reflects_registry(application: QApplication, tmp_path: Path) -> None:
    registry = FakeRegistry({VALUE_NAME: autostart_command(EXE)})
    view, _ = _view(application, tmp_path, registry=registry)
    assert view.autostart_checkbox().isChecked() is True


def test_autostart_writes_registry_not_settings_file(
    application: QApplication, tmp_path: Path
) -> None:
    """Защитный: истина автозапуска — реестр, в файл он не попадает (спека §3.1).

    Мутация: добавить в `Settings` поле автозапуска и писать его в store —
    тест обязан упасть.

    Проверка на содержимом JSON одна не ловит эту мутацию: `save_settings`
    перечисляет ключи payload явно, и поле, добавленное только в `Settings`
    без правки сериализации, в файл не протечёт, а `store.update` при этом
    уже произошёл — store.settings.autostart существует и тест обязан это
    заметить. Поэтому сначала — прямая проверка store.settings (мутация
    ловится гарантированно, вне зависимости от того, тронута сериализация
    или нет), и только затем — содержимое файла как второй, более слабый
    рубеж.
    """  # noqa: RUF002
    registry = FakeRegistry()
    view, store = _view(application, tmp_path, registry=registry)

    view.autostart_checkbox().setChecked(True)

    assert registry.values[VALUE_NAME] == autostart_command(EXE)
    # Store не тронут вовсе: ни одно поле `Settings` не изменилось и не
    # появилось новое (спека §3.1) — сильнее, чем «в файле нет ключа»,
    # и не зависит от того, попадёт ли поле в сериализацию.
    assert store.settings == Settings()
    import json

    settings_path = tmp_path / "settings.json"
    # Файл мог ни разу не записаться до этого момента — store не вызывался.
    # Отсутствие файла и файл без ключа значат одно и то же: автозапуск
    # в settings.json не попал. Падать на FileNotFoundError здесь означало
    # бы путать «не проверено» с «проверено и хорошо».  # noqa: RUF003
    payload = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.exists()
        else {}
    )
    assert "autostart" not in payload


def test_autostart_write_failure_rolls_back_toggle(
    application: QApplication, tmp_path: Path
) -> None:
    """Отказ записи не смеет оставить включённый тумблер (спека §3.6)."""
    view, _ = _view(application, tmp_path, registry=BrokenRegistry())

    view.autostart_checkbox().setChecked(True)

    assert view.autostart_checkbox().isChecked() is False
    assert "отказано" in view.autostart_note()


def test_unreadable_registry_blocks_the_toggle(
    application: QApplication, tmp_path: Path
) -> None:
    """Состояние неизвестно — «выключено» как факт показывать нельзя (спека §3.6)."""
    view, _ = _view(application, tmp_path, registry=UnreadableRegistry())
    assert view.autostart_checkbox().isEnabled() is False
    assert view.autostart_checkbox().isChecked() is False
    assert "отказано" in view.autostart_note()


def test_hotkey_field_shows_saved_value(
    application: QApplication, tmp_path: Path
) -> None:
    save_settings(tmp_path / "settings.json", Settings(hotkey="Win+F9"))
    view, _ = _view(application, tmp_path)
    assert view.hotkey_edit().text() == "Win+F9"


def test_hotkey_capture_saves_and_reports_success(
    application: QApplication, tmp_path: Path
) -> None:
    view, store = _view(application, tmp_path, on_hotkey=lambda _text: None)

    view.hotkey_edit().captured.emit("Ctrl+Alt+Y")

    assert store.settings.hotkey == "Ctrl+Alt+Y"
    assert view.hotkey_note() == ""


def test_busy_hotkey_is_saved_with_honest_status(
    application: QApplication, tmp_path: Path
) -> None:
    """Занятое сочетание сохраняется — оно может освободиться (спека §4.2)."""
    view, store = _view(
        application, tmp_path, on_hotkey=lambda _text: "сочетание занято другим приложением"
    )

    view.hotkey_edit().captured.emit("Ctrl+Alt+Y")

    assert store.settings.hotkey == "Ctrl+Alt+Y"
    assert "занято" in view.hotkey_note()


def test_hotkey_can_be_cleared(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path, on_hotkey=lambda _text: None)

    view.hotkey_edit().captured.emit("")

    assert store.settings.hotkey == ""
    assert view.hotkey_edit().text() == HotkeyEdit.DISABLED_TEXT


def test_recent_spinbox_bounds_and_persistence(
    application: QApplication, tmp_path: Path
) -> None:
    view, store = _view(application, tmp_path)
    spin = view.recent_spinbox()
    assert (spin.minimum(), spin.maximum()) == (0, 50)
    assert spin.value() == 10

    spin.setValue(0)

    assert store.settings.recent_limit == 0
