"""Владелец режима темы: применение, сохранение, следование системе.

О виджетах контроллер не знает: он применяет общий stylesheet и цветовую схему Qt
(план Б, задача 2) и сообщает сигналом `changed`. Кто из виджетов запекает цвет в объект и обязан
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


def color_scheme_for(mode: ThemeMode, palette: theme.Palette) -> Qt.ColorScheme:
    """Схема нативного стиля: явная тема — по палитре, AUTO — системная.

    Б0 [проверено] 21.11.2026 (аудит плана Б, раздел 6): `windows11` рисует кнопки и
    флажки по цветовой схеме Qt, а не по нашему stylesheet. Без неё при светлой теме
    на тёмной Windows у «…» нет рамки (В2), флажок «запомнить» не виден (В3).
    AUTO — `Unknown` (из документации Qt: сброс к системной схеме), а не схема по
    палитре: явная схема подменяет ответ `colorScheme()`, и `detect_system_mode`
    перестал бы видеть смену темы Windows.
    """  # noqa: RUF002
    if mode is ThemeMode.AUTO:
        return Qt.ColorScheme.Unknown
    return Qt.ColorScheme.Light if palette is theme.LIGHT else Qt.ColorScheme.Dark


def set_application_color_scheme(scheme: Qt.ColorScheme) -> None:
    QGuiApplication.styleHints().setColorScheme(scheme)


class ThemeController(QObject):
    changed = Signal()

    def __init__(
        self,
        application: QApplication,
        store: SettingsStore,
        *,
        system_mode: Callable[[], ThemeMode] = detect_system_mode,
        set_color_scheme: Callable[[Qt.ColorScheme], None] | None = None,
    ) -> None:
        super().__init__(application)
        self._application = application
        self._store = store
        self._system_mode = system_mode
        # Модульная функция ищется здесь, а не в значении по умолчанию: так её можно  # noqa: RUF003
        # подменить в тестах на уровне модуля.
        self._set_color_scheme = set_color_scheme or set_application_color_scheme
        self._repainting = False
        self._mode = store.settings.theme
        self._palette = self._resolve_palette()
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
        """Системная тема сменилась. При явно выбранной теме — ничего не делаем.

        Во время собственной перекраски — тоже ничего: `setColorScheme`, [гипотеза],
        поднимает `colorSchemeChanged` синхронно, а `ui/app.py` подписан на него этим
        методом. При асинхронной доставке выйдет одна лишняя идемпотентная перекраска.
        """  # noqa: RUF002
        if self._mode is ThemeMode.AUTO and not self._repainting:
            self._repaint()

    def _repaint(self) -> None:
        self._repainting = True
        try:
            self._palette = self._resolve_palette()
            self._apply()
        finally:
            self._repainting = False
        self.changed.emit()

    def _resolve_palette(self) -> theme.Palette:
        if self._mode is ThemeMode.AUTO:
            # Сначала сброс: иначе colorScheme() вернул бы нашу прошлую явную схему.  # noqa: RUF003
            self._set_color_scheme(Qt.ColorScheme.Unknown)
        return theme.palette_for(self._mode, self._system_mode())

    def _apply(self) -> None:
        self._application.setStyleSheet(theme.stylesheet(self._palette))
        self._set_color_scheme(color_scheme_for(self._mode, self._palette))
        # Родные флажки и переключатели — акцентом Windows: роль палитры Accent = жёлтый
        # программы (Б5) отменена живой приёмкой 22.11.2026 [проверено] — в тёмной схеме
        # `windows11` рисует галочку почти белой, на жёлтом контраст 1,2:1 (спека §7.8).
