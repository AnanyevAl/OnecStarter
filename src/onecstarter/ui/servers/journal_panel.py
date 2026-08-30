"""Панель «Журнал профиля» — живой tail файла журнала (T-10, задача 5).

Файл — `services/server_journal.py`: два независимых писателя одного файла
(наши события с временными метками и захваченный stdout дерева процессов,
[Ф] А1 T-09, спека §12.5). Панель читает ХВОСТ файла на каждый `refresh()` —
не держит файл открытым и не подписывается на изменения ФС (файл
дозаписывается снаружи двумя независимыми процессами, периодический опрос
надёжнее вотчера). Кодировка платформенного вывода не снята ([Ф] А1/А4
T-09) — декодирование `utf-8, errors="replace"` не роняет панель ни на
каких байтах, включая произвольный мусор посреди файла.

**Ревью задачи 5, IMPORTANT** (исправлено 28.08.2026): `refresh()` читает
не файл целиком, а не более `_TAIL_BYTES` (256 КиБ) с КОНЦА файла
(`_read_tail_bytes` — `seek` от найденного смещения, без загрузки головы
файла в память). Журнал ротируется только на `start()` (см.
`services/server_journal.py`) — при долгой работе сервера файл растёт
неограниченно, а `refresh()` зовётся раз в секунду синхронно в UI-потоке;
без ограничения объёма каждый тик блокировал бы интерфейс на чтение/decode/
splitlines всего файла целиком.

`QTimer` тикает раз в секунду, но только пока панель ВИДИМА и профиль
ВЫБРАН (путь задан) — `_sync_timer` держит `isActive()` ровно в этом
состоянии; вызывается и на смену пути (`show_journal`), и на показ/скрытие
виджета (`showEvent`/`hideEvent`). Тесты не ждут тика: `refresh()` —
публичный метод, зовётся явно и детерминированно, таймер в них не участвует.

**Ревью задачи 5, CRITICAL** (исправлено 28.08.2026): `QPlainTextEdit.
setPlainText()` безусловно пересобирает документ и сбрасывает scrollbar
в 0 — НЕЗАВИСИМО от того, совпадает ли новый текст со старым (измерено
ревьюером на этом же PySide6: ручная прокрутка к середине, `setPlainText()`
ТЕМ ЖЕ текстом — `value()` всё равно улетает в 0). Раньше `refresh()` звал
`setPlainText()` на каждый тик безусловно, а «прокрутка не поедет» держалось
на неверном допущении «текст не менялся → Qt сам ничего не сдвинет».
Теперь `refresh()`: (1) не зовёт `setPlainText()` вовсе, если хвост не
изменился (`tail == self._text.toPlainText()`); (2) если изменился и
пользователь НЕ был у низа — явно возвращает прежнее значение scrollbar
(`bar.setValue(previous_value)`) уже ПОСЛЕ `setPlainText()`, а не полагается
на то, что Qt его не тронет. Прокрутка везде — через `QScrollBar`
(`verticalScrollBar()`), единый механизм для «к низу» и «на прежнее место»
(до правки «к низу» двигало текстовый курсор — раздвоение без причины).

Приём «карточка → плейсхолдер/полоса» — тот же, что `ConnectionPanel`
(`ui/bases/panel.py`): плейсхолдер красится через `QPalette.PlaceholderText`
поверх стиля поля, а не через отдельный виджет-заглушку.
"""  # noqa: RUF002

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QHideEvent, QPalette, QShowEvent
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QScrollBar, QVBoxLayout, QWidget

from onecstarter.ui.theme import Palette

_MONO = "font-family: Consolas, 'Cascadia Mono', monospace;"
_TAIL_LINES = 500
_TAIL_BYTES = 256 * 1024  # 256 КиБ — буфер чтения хвоста (ревью задачи 5, IMPORTANT)
_TIMER_INTERVAL_MS = 1000
_SCROLL_TOLERANCE = 2
_PLACEHOLDER_TITLE = "Журнал профиля"
_PLACEHOLDER_TEXT = "Выберите профиль слева, чтобы увидеть его журнал"  # noqa: RUF001


def _read_tail_bytes(path: Path, max_bytes: int) -> bytes:
    """Прочитать не более `max_bytes` байт с КОНЦА файла — без чтения файла целиком.

    Отсутствующий/недоступный файл — `OSError` глотается молча (тот же
    приём, что `ServersWorkspace.log_event`): пустой хвост неотличим от
    только что созданного, ни разу не запускавшегося профиля.

    Первая строка буфера может оказаться обрезанной посередине (байт-смещение
    внутри файла, а не граница строки) — не страшно: `_read_tail`
    декодирует буфер с `errors="replace"` (обрубок многобайтового UTF-8
    символа заменяется на `�`, не падает) и берёт только последние ≤ 500
    строк — буфер (256 КиБ) почти всегда на порядки больше 500 строк
    журнала, так что обрезанная первая строка либо не попадает в показ
    вовсе, либо ведёт себя как обычная «грязная» строка платформенного
    stdout (то же допущение, что и у произвольных байт вообще).
    """  # noqa: RUF002
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read()
    except OSError:
        return b""


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
        """Перечитать хвост файла (последние ≤ 500 строк из ≤ 256 КиБ с конца).

        No-op без выбранного профиля. Если хвост не изменился с прошлого
        раза — `QPlainTextEdit` вообще не трогается (см. докстринг модуля,
        CRITICAL): `setPlainText()` безусловно сбрасывает прокрутку в 0,
        поэтому единственная надёжная защита — не звать его, когда текст
        совпадает. Если хвост изменился и пользователь не был у низа —
        прежняя позиция прокрутки восстанавливается явно ПОСЛЕ `setPlainText()`.
        """  # noqa: RUF002
        if self._path is None:
            return
        tail = self._read_tail(self._path)
        if tail == self._text.toPlainText():
            return
        bar = self._text.verticalScrollBar()
        was_at_bottom = self._is_at_bottom(bar)
        previous_value = bar.value()
        self._text.setPlainText(tail)
        if was_at_bottom:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(previous_value)

    def _read_tail(self, path: Path) -> str:
        raw = _read_tail_bytes(path, _TAIL_BYTES)
        content = raw.decode("utf-8", errors="replace")
        lines = content.splitlines()
        return "\n".join(lines[-_TAIL_LINES:])

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

    def _is_at_bottom(self, bar: QScrollBar) -> bool:
        return bar.value() >= bar.maximum() - _SCROLL_TOLERANCE

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
