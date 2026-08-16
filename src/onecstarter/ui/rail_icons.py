"""Значки разделов рельсы, нарисованные кодом из действующей палитры.

Тот же принцип, что у значков размещения (bases/icons.py): готовых PNG нет,
цвет не запекается — QIcon несёт Off-пиксмап приглушённым цветом и On-пиксмап
акцентным, перерисовка при смене темы — новая пара пиксмапов через
MainWindow.apply_palette (спека рестайла §3).
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from onecstarter.ui.theme import Palette

_SIZE = 16
_Draw = Callable[[QPainter], None]


def _pixmap(colour: str, draw: _Draw) -> QPixmap:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour))
    pen.setWidthF(1.4)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter)
    painter.end()
    return pixmap


def _icon(palette: Palette, draw: _Draw) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_pixmap(palette.text_dim, draw), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_pixmap(palette.accent, draw), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def _draw_bases(painter: QPainter) -> None:
    """▤ мокапа: прямоугольник со строками — список баз.

    Контур сдвинут на 0.3 px от целых координат (как и обе внутренние
    линии) — на самой границе пиксельной сетки перо 1.4 px даёт на каждой
    точке стороны частичное покрытие (~0.7 вместо 1.0), и после round-trip
    через premultiplied QImage большинство точек стороны отличаются от
    чистого цвета палитры на 1 младший бит: `_dominant` в тесте берёт
    большинство, и им оказывается не палитровый цвет, а его соседний
    оттенок (проверено: 80 точек #…4d против 4 точек точного #…4c
    у прежнего варианта с целыми координатами; со сдвигом — 67 против 34
    в пользу точного цвета).
    """  # noqa: RUF002
    painter.drawRect(QRectF(2.3, 3.3, 12.0, 10.0))
    painter.drawLine(QPointF(2.3, 6.3), QPointF(14.3, 6.3))
    painter.drawLine(QPointF(2.3, 9.7), QPointF(14.3, 9.7))


def _draw_settings(painter: QPainter) -> None:
    """⚙ мокапа: окружность с восемью зубьями и втулкой."""  # noqa: RUF002
    painter.drawEllipse(QPointF(8.0, 8.0), 4.2, 4.2)
    painter.drawEllipse(QPointF(8.0, 8.0), 1.6, 1.6)
    for step in range(8):
        painter.save()
        painter.translate(8.0, 8.0)
        painter.rotate(step * 45.0)
        painter.drawLine(QPointF(0.0, -4.2), QPointF(0.0, -6.3))
        painter.restore()


def bases_icon(palette: Palette) -> QIcon:
    return _icon(palette, _draw_bases)


def settings_icon(palette: Palette) -> QIcon:
    return _icon(palette, _draw_settings)
