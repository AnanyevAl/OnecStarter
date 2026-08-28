"""Панель «Журнал профиля» — живой tail файла журнала (T-10, задача 5).

Файл — `services/server_journal.py`: два независимых писателя одного файла
(наши события с временными метками и захваченный stdout дерева процессов,
[Ф] А1 T-09, спека §12.5). Панель читает ХВОСТ файла целиком на каждый
`refresh()` — не держит файл открытым и не подписывается на изменения ФС
(файл дозаписывается снаружи двумя независимыми процессами, периодический
опрос надёжнее вотчера). Кодировка платформенного вывода не снята
([Ф] А1/А4 T-09) — декодирование `utf-8, errors="replace"` не роняет
панель ни на каких байтах, включая произвольный мусор посреди файла.

`QTimer` тикает раз в секунду, но только пока панель ВИДИМА и профиль
ВЫБРАН (путь задан) — `_sync_timer` держит `isActive()` ровно в этом
состоянии; вызывается и на смену пути (`show_journal`), и на показ/скрытие
виджета (`showEvent`/`hideEvent`). Тесты не ждут тика: `refresh()` —
публичный метод, зовётся явно и детерминированно, таймер в них не участвует.

Приём «карточка → плейсхолдер/полоса» — тот же, что `ConnectionPanel`
(`ui/bases/panel.py`): плейсхолдер красится через `QPalette.PlaceholderText`
поверх стиля поля, а не через отдельный виджет-заглушку.
"""  # noqa: RUF002

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QHideEvent, QPalette, QShowEvent, QTextCursor
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from onecstarter.ui.theme import Palette

_MONO = "font-family: Consolas, 'Cascadia Mono', monospace;"
_TAIL_LINES = 500
_TIMER_INTERVAL_MS = 1000
_SCROLL_TOLERANCE = 2
_PLACEHOLDER_TITLE = "Журнал профиля"
_PLACEHOLDER_TEXT = "Выберите профиль слева, чтобы увидеть его журнал"  # noqa: RUF001


class JournalPanel(QWidget):
    def __init__(self, *, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("JournalPanel")
        self._palette = palette
        self._path: Path | None = None

        self._title = QLabel()
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)

        self._text = QPlainTextEdit()
        self._text.setObjectName("JournalPanelText")
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._text)

        # Главный поток (тот же владелец, что и `ServerMonitor._timer`,
        # см. её докстринг) — сам таймер сетью/файлами не занимается,
        # только зовёт refresh().
        self._timer = QTimer(self)
        self._timer.setInterval(_TIMER_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)

        self.show_journal("", None)

    # -- показ ----------------------------------------------------------------

    def show_journal(self, title: str, path: Path | None) -> None:
        """Показать журнал профиля (`path`) либо плейсхолдер (`path is None`).

        `title` игнорируется в плейсхолдерном состоянии — сообщение
        «выберите профиль» фиксированное независимо от того, что передал
        вызывающий.
        """
        self._path = path
        if path is None:
            self._title.setText(_PLACEHOLDER_TITLE)
            self._text.setPlainText("")
            self._text.setPlaceholderText(_PLACEHOLDER_TEXT)
        else:
            self._title.setText(title)
            # Пустой журнал реального профиля (только что создан, ещё не
            # запускался) не должен показывать плейсхолдер «выберите
            # профиль» — он уже выбран, журнал просто пуст.
            self._text.setPlaceholderText("")
            self.refresh()
        self._apply_style()
        self._sync_timer()

    def refresh(self) -> None:
        """Перечитать хвост файла (последние ≤ 500 строк). No-op без выбранного профиля.

        Отсутствующий файл (профиль ещё ни разу не запускался) — не отказ,
        а такой же пустой хвост, как и у пустого файла: `OSError` глотается
        молча, тем же приёмом, что `ServersWorkspace.log_event`.
        """  # noqa: RUF002
        if self._path is None:
            return
        try:
            raw = self._path.read_bytes()
        except OSError:
            raw = b""
        content = raw.decode("utf-8", errors="replace")
        lines = content.splitlines()
        tail = "\n".join(lines[-_TAIL_LINES:])
        was_at_bottom = self._is_at_bottom()
        self._text.setPlainText(tail)
        if was_at_bottom:
            self._scroll_to_bottom()

    # -- доступ для тестов ------------------------------------------------------

    def text(self) -> str:
        return self._text.toPlainText()

    def title_label(self) -> QLabel:
        return self._title

    def placeholder(self) -> str:
        return self._text.placeholderText()

    def text_widget(self) -> QPlainTextEdit:
        return self._text

    # -- палитра ----------------------------------------------------------------

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._apply_style()

    # -- таймер: тикает только пока видима и путь задан --------------------------

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        super().hideEvent(event)
        self._sync_timer()

    def _sync_timer(self) -> None:
        should_run = self.isVisible() and self._path is not None
        if should_run and not self._timer.isActive():
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()

    # -- вспомогательное ---------------------------------------------------------

    def _is_at_bottom(self) -> bool:
        bar = self._text.verticalScrollBar()
        return bar.value() >= bar.maximum() - _SCROLL_TOLERANCE

    def _scroll_to_bottom(self) -> None:
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def _apply_style(self) -> None:
        palette = self._palette
        title_colour = palette.text_dim if self._path is None else palette.text
        self._title.setStyleSheet(f"color: {title_colour};")
        self._text.setStyleSheet(
            f"background: {palette.background}; color: {palette.text}; "
            f"border: 1px solid {palette.border}; {_MONO}"
        )
        field_palette = self._text.palette()
        field_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette.text_dim))
        self._text.setPalette(field_palette)
