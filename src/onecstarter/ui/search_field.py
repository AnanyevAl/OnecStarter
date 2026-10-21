"""Поле поиска разделов (спека v3.1, §6): крестик очистки и подсказка Ctrl+F.

Своё действие очистки, а не `setClearButtonEnabled`: у штатного значок — из
системной темы Qt, и его видимость на нашей тёмной палитре ничем не
гарантирована. Значок рисуется цветом `palette.text_dim` по образцу
`ui/rail_icons.py` и перерисовывается при смене темы.
"""  # noqa: RUF002

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLineEdit, QWidget

from onecstarter.ui.theme import Palette

HOTKEY_SUFFIX = " (Ctrl+F)"
_SIZE = 16


def clear_icon(palette: Palette) -> QIcon:
    """Косой крест 8×8 в центре 16×16, цвет — `palette.text_dim`."""  # noqa: RUF002
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(palette.text_dim))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(4, 4), QPointF(12, 12))
    painter.drawLine(QPointF(12, 4), QPointF(4, 12))
    painter.end()
    return QIcon(pixmap)


class SearchField(QLineEdit):
    """Поле поиска раздела: подсказка с хоткеем и свой крестик очистки.

    `list_navigation` (T-35): Enter и Tab подают `list_requested` — раздел
    переводит фокус в свой список. Выключено по умолчанию: поле стоит и
    в диалоге «Цветовая схема…», где Tab обязан работать как обычно.
    """  # noqa: RUF002

    list_requested = Signal()
    # Атрибут класса, а не только экземпляра: `event()` может прийти во время  # noqa: RUF003
    # `super().__init__`, раньше присваивания в конструкторе.
    _list_navigation = False

    def __init__(
        self,
        hint: str,
        palette: Palette,
        parent: QWidget | None = None,
        *,
        list_navigation: bool = False,
    ) -> None:
        super().__init__(parent)
        self._list_navigation = list_navigation
        self.setPlaceholderText(hint + HOTKEY_SUFFIX)
        self._clear = QAction("Очистить", self)
        self._clear.setIcon(clear_icon(palette))
        self._clear.setVisible(False)
        self._clear.triggered.connect(self.clear)
        self.addAction(self._clear, QLineEdit.ActionPosition.TrailingPosition)
        self.textChanged.connect(lambda text: self._clear.setVisible(bool(text)))
        if list_navigation:
            self.returnPressed.connect(self.list_requested.emit)

    def event(self, event: QEvent) -> bool:
        # Tab Qt разбирает в QWidget.event (смена фокуса) раньше keyPressEvent,
        # поэтому перехват — здесь. Shift+Tab не трогаем.
        if (
            self._list_navigation
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Tab
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.list_requested.emit()
            return True
        return super().event(event)

    def apply_palette(self, palette: Palette) -> None:
        """Перерисовать крестик под новую палитру — цвет запечён в пиксмап."""
        self._clear.setIcon(clear_icon(palette))

    def clear_action(self) -> QAction:
        return self._clear
