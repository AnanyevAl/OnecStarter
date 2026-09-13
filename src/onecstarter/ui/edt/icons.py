"""Значки раздела «EDT»: зелёный ▶ — запись запущена (решение заказчика 11.09.2026),
закрашенный круг цветом акцента — выполняется команда CLI (спека §14.6).
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF

from onecstarter.ui.theme import Palette

_SIZE = 16


def running_icon(palette: Palette) -> QIcon:
    """Закрашенный треугольник вершиной вправо, цвет — `palette.running`."""
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(palette.running))
    painter.drawPolygon(QPolygonF([QPointF(3, 2), QPointF(14, 8), QPointF(3, 14)]))
    painter.end()
    return QIcon(pixmap)


def cli_busy_icon(palette: Palette) -> QIcon:
    """Закрашенный круг цветом акцента — выполняется команда CLI (спека §14.6)."""
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(palette.accent))
    painter.drawEllipse(3, 3, 10, 10)
    painter.end()
    return QIcon(pixmap)
