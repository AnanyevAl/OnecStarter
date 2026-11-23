"""Контроллер темы: применение, сохранение, следование системе."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import Settings, ThemeMode, save_settings
from onecstarter.ui import theme, theme_controller
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.theme_controller import (
    ThemeController,
    color_scheme_for,
    set_application_color_scheme,
)


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


@pytest.fixture(autouse=True)
def _reset_stylesheet(application: QApplication) -> Iterator[None]:
    """Каждый контроллер этого файла ставит таблицу стилей приложения — вернуть.

    Таблица темы (шрифт 10pt) иначе доживает до соседних файлов и расширяет текст в тестах,
    меряющих ширину (план В, полный прогон).
    """  # noqa: RUF002
    sheet_before = application.styleSheet()
    yield
    if application.styleSheet() != sheet_before:
        application.setStyleSheet(sheet_before)


def test_application_palette_is_not_pinned(application: QApplication, tmp_path: Path) -> None:
    """Б5 отменён живой приёмкой (спека §7.8): родные флажки — акцентом Windows.

    Роль Accent палитры приложения программа не закрепляет: жёлтый под белой галочкой
    тёмной схемы `windows11` дал контраст 1,2:1.
    """
    path = tmp_path / "s.json"
    save_settings(path, Settings(theme=ThemeMode.DARK))
    _controller(application, path)
    assert not application.palette().isBrushSet(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Accent
    )


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


@pytest.mark.parametrize(
    ("mode", "palette", "expected"),
    [
        (ThemeMode.LIGHT, theme.LIGHT, Qt.ColorScheme.Light),
        (ThemeMode.DARK, theme.DARK, Qt.ColorScheme.Dark),
        (ThemeMode.AUTO, theme.LIGHT, Qt.ColorScheme.Unknown),
        (ThemeMode.AUTO, theme.DARK, Qt.ColorScheme.Unknown),
    ],
)
def test_color_scheme_for(
    mode: ThemeMode, palette: theme.Palette, expected: Qt.ColorScheme
) -> None:
    """Явная тема — схема по палитре; AUTO — сброс к системной (иначе AUTO замёрз бы)."""  # noqa: RUF002
    assert color_scheme_for(mode, palette) == expected


def test_native_style_scheme_follows_the_applied_theme(
    application: QApplication, tmp_path: Path
) -> None:
    """Б0 [проверено] 21.11.2026: без схемы светлая тема рисуется тёмными кнопками (В2, В3)."""  # noqa: RUF002
    schemes: list[Qt.ColorScheme] = []
    controller = ThemeController(
        application,
        SettingsStore(tmp_path / "s.json"),
        system_mode=lambda: ThemeMode.DARK,
        set_color_scheme=schemes.append,
    )
    assert schemes[-1:] == [Qt.ColorScheme.Unknown]  # по умолчанию AUTO
    controller.set_mode(ThemeMode.LIGHT)
    assert schemes[-1:] == [Qt.ColorScheme.Light]
    controller.set_mode(ThemeMode.DARK)
    assert schemes[-1:] == [Qt.ColorScheme.Dark]


def test_switching_to_auto_resets_the_scheme_before_reading_the_system(
    application: QApplication, tmp_path: Path
) -> None:
    """Иначе `detect_system_mode` прочитал бы нашу же прошлую схему, а не Windows."""  # noqa: RUF002
    events: list[str] = []

    def system() -> ThemeMode:
        events.append("system")
        return ThemeMode.DARK

    controller = ThemeController(
        application,
        SettingsStore(tmp_path / "s.json"),
        system_mode=system,
        set_color_scheme=lambda scheme: events.append(scheme.name),
    )
    controller.set_mode(ThemeMode.LIGHT)
    events.clear()
    controller.set_mode(ThemeMode.AUTO)
    assert events[:2] == ["Unknown", "system"]


def test_scheme_signal_during_repaint_does_not_repaint_again(
    application: QApplication, tmp_path: Path
) -> None:
    """Qt, [гипотеза], поднимает `colorSchemeChanged` синхронно, а `ui/app.py` подписан на него.

    При асинхронной доставке выйдет одна лишняя идемпотентная перекраска. Флаг не должен
    застревать: после перекраски смена системной темы снова обрабатывается.
    """  # noqa: RUF002
    current = {"mode": ThemeMode.DARK}
    holder: dict[str, ThemeController] = {}

    def setter(_scheme: Qt.ColorScheme) -> None:
        if "controller" in holder:
            holder["controller"].refresh_system()

    controller = ThemeController(
        application,
        SettingsStore(tmp_path / "s.json"),
        system_mode=lambda: current["mode"],
        set_color_scheme=setter,
    )
    holder["controller"] = controller
    seen: list[int] = []
    controller.changed.connect(lambda: seen.append(1))
    controller.set_mode(ThemeMode.LIGHT)
    controller.set_mode(ThemeMode.AUTO)
    assert seen == [1, 1]
    current["mode"] = ThemeMode.LIGHT
    controller.refresh_system()
    assert seen == [1, 1, 1]
    assert controller.palette is theme.LIGHT


def test_scheme_setter_reaches_style_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Настоящая функция зовёт `styleHints().setColorScheme`.

    Заглушка, а не настоящий `styleHints()`: офскрин запрос схемы игнорирует
    (проверено 21.11.2026), а на живой платформе смена схемы будила бы подписки.
    """  # noqa: RUF002
    requested: list[Qt.ColorScheme] = []
    hints = SimpleNamespace(setColorScheme=requested.append)
    monkeypatch.setattr(
        theme_controller, "QGuiApplication", SimpleNamespace(styleHints=lambda: hints)
    )
    set_application_color_scheme(Qt.ColorScheme.Light)
    set_application_color_scheme(Qt.ColorScheme.Unknown)
    assert requested == [Qt.ColorScheme.Light, Qt.ColorScheme.Unknown]
