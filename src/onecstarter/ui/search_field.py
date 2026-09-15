"""Поле поиска разделов (спека v3.1, §6): крестик очистки и подсказка Ctrl+F.

Своё действие очистки, а не `setClearButtonEnabled`: у штатного значок — из
системной темы Qt, и его видимость на нашей тёмной палитре ничем не
гарантирована. Значок рисуется цветом `palette.text_dim` по образцу
`ui/rail_icons.py` и перерисовывается при смене темы.
"""  # noqa: RUF002

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
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
    """Поле поиска раздела: подсказка с хоткеем и свой крестик очистки."""  # noqa: RUF002

    def __init__(self, hint: str, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(hint + HOTKEY_SUFFIX)
        self._clear = QAction("Очистить", self)
        self._clear.setIcon(clear_icon(palette))
        self._clear.setVisible(False)
        self._clear.triggered.connect(self.clear)
        self.addAction(self._clear, QLineEdit.ActionPosition.TrailingPosition)
        self.textChanged.connect(lambda text: self._clear.setVisible(bool(text)))

    def apply_palette(self, palette: Palette) -> None:
        """Перерисовать крестик под новую палитру — цвет запечён в пиксмап."""
        self._clear.setIcon(clear_icon(palette))

    def clear_action(self) -> QAction:
        return self._clear
