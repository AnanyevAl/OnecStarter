"""Владелец режима темы: применение, сохранение, следование системе.

О виджетах контроллер не знает: он применяет общий stylesheet и сообщает
сигналом `changed`. Кто из виджетов запекает цвет в объект и обязан
перерисоваться — решает сборка приложения (ui/app.py). Иначе контроллер
пришлось бы учить про BasesView, и его нельзя было бы проверить без окна.
"""  # noqa: RUF002

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import ThemeMode
from onecstarter.ui import theme
from onecstarter.ui.settings_store import SettingsStore


def detect_system_mode() -> ThemeMode:
    """Системная тема Windows глазами Qt. Возвращает LIGHT или DARK, но не AUTO.

    **[Ф] 08.08.2026, PySide6 6.11.1, платформа `windows`.** На настоящей
    платформе `QStyleHints.colorScheme()` даёт `ColorScheme.Dark` и совпадает
    с реестром `AppsUseLightTheme=0` (шаг 7 задачи 3 плана 4b) — Qt отвечает
    не наугад. Сигнал `colorSchemeChanged` в сборке есть.

    Под `QT_QPA_PLATFORM=offscreen` та же `colorScheme()` всегда даёт
    `ColorScheme.Unknown` — offscreen-платформа не подключена к реальной теме
    Windows и не может её знать. Первая редакция шага 7 мерила именно так —
    это была ошибка плана, замер повторён на настоящей платформе.

    Следствие для тестов: наши UI-тесты идут под offscreen, то есть
    `detect_system_mode()` там всегда вернул бы `DARK`. Поэтому
    `ThemeController` принимает `system_mode` параметром, а не зовёт
    эту функцию напрямую — тест, полагающийся на настоящее определение,
    был бы зелёным по совпадению платформы, а не по существу поведения.
    Инъекцию нельзя убирать «для простоты»: без неё AUTO нечем проверить.

    `ColorScheme.Unknown` даёт тёмную — поведение 4a, менять его молча нельзя.
    """  # noqa: RUF002
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme()
    return ThemeMode.LIGHT if scheme == Qt.ColorScheme.Light else ThemeMode.DARK


class ThemeController(QObject):
    changed = Signal()

    def __init__(
        self,
        application: QApplication,
        store: SettingsStore,
        *,
        system_mode: Callable[[], ThemeMode] = detect_system_mode,
    ) -> None:
        super().__init__(application)
        self._application = application
        self._store = store
        self._system_mode = system_mode
        self._mode = store.settings.theme
        self._palette = theme.palette_for(self._mode, self._system_mode())
        self._apply()

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def palette(self) -> theme.Palette:
        return self._palette

    @property
    def path(self) -> Path:
        """Куда пишутся настройки — разделу «Настройки» для подписи."""
        return self._store.path

    @property
    def last_save_error(self) -> str | None:
        """Отказ записи виден там же, где был: файл теперь пишет store."""
        return self._store.last_save_error

    def set_mode(self, mode: ThemeMode) -> None:
        self._mode = mode
        # Тема применяется всегда: пользователь её выбрал. Отказ записи
        # не гасится — раздел «Настройки» покажет причину из store.
        self._store.update(theme=mode)
        self._repaint()

    def refresh_system(self) -> None:
        """Системная тема сменилась. При явно выбранной теме — ничего не делаем."""
        if self._mode is ThemeMode.AUTO:
            self._repaint()

    def _repaint(self) -> None:
        self._palette = theme.palette_for(self._mode, self._system_mode())
        self._apply()
        self.changed.emit()

    def _apply(self) -> None:
        self._application.setStyleSheet(theme.stylesheet(self._palette))
