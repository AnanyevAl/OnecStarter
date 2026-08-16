"""Значки видов размещения, нарисованные кодом из действующей палитры.

Готовых PNG нет намеренно: значки создаются внутри build_model, а модель
пересобирается при смене темы, — значит новой запечённой точки цвета
не появляется (спека 4b, §1.3).

UNKNOWN рисуется иначе трёх известных и цветом проблемы: это не «прочее»,
а «строку соединения не разобрали» (§9 п. 2 спеки 4a).

Все фигуры — контур, не заливка (smoke №1, 08.08.2026, замечание 2):
на 16 px заливка съедает силуэт, и папка со стойкой заливкой выглядели
одинаковыми тёмными квадратами. Вид узнаётся формой целиком — папка
заметно шире, чем выше, полки заметно шире, чем выше, и разделены
просветом, глобус вообще круглый — а не деталями внутри контура
(мокап рестайла, спека рестайла §5). Проверочный скрипт
`.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py` показывает
все четыре значка натурально и увеличенными в обеих палитрах.
"""  # noqa: RUF002

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from onecstarter.domain.connect import ConnectKind
from onecstarter.ui.theme import Palette

_SIZE = 16


def _colour_for(kind: ConnectKind, palette: Palette) -> QColor:
    """Цвет значка: UNKNOWN — цвет проблемы, остальные — приглушённый текст.

    Отдельная функция, а не выражение внутри `placement_icon`: сравнение
    сырых пикселей готового значка не различает цвет отдельно от формы —
    пунктир и «?» перекрывают пиксели совсем в других местах, чем сплошная
    заливка, поэтому два значка разного цвета, но и разной формы, отличались
    бы пикселями, даже если бы кто-то по ошибке свёл их цвета к одному.
    Требование заказчика — различие и по форме, и по цвету одновременно
    (§1.3), и по форме одной проверки уже недостаточно (находка мутационной
    проверки задачи 5, шаг 10, мутация 2).
    """  # noqa: RUF002
    return QColor(palette.problem if kind is ConnectKind.UNKNOWN else palette.text_dim)


def placement_icon(kind: ConnectKind, palette: Palette) -> QIcon:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    colour = _colour_for(kind, palette)
    pen = QPen(colour)
    pen.setWidthF(1.4)
    painter.setPen(pen)
    _DRAW[kind](painter, colour)
    painter.end()
    return QIcon(pixmap)


def _draw_file(painter: QPainter, colour: QColor) -> None:
    """Папка контуром: язычок сверху слева, тело заметно шире, чем выше.

    Заливка (была в прежней редакции) на 16 px съедает силуэт — заказчик
    видел на скриншоте одинаковые тёмные квадраты (smoke №1, 08.08.2026,
    замечание 2). Вид теперь узнаётся формой контура, не деталями внутри.
    """
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(1.5, 4.0)
    path.lineTo(6.0, 4.0)
    path.lineTo(6.0, 5.5)
    path.lineTo(14.5, 5.5)
    path.lineTo(14.5, 12.0)
    path.lineTo(1.5, 12.0)
    path.closeSubpath()
    painter.drawPath(path)


def _draw_server(painter: QPainter, colour: QColor) -> None:
    """Две полки со скруглением и индикаторами — серверная мокапа.

    От папки отличается структурой: два раздельных прямоугольника
    с просветом против сплошного контура с язычком (спека рестайла §5).

    Нижняя полка сдвинута на y=9.7, а не 9.0 из спеки: перо шириной 1.4
    рисует верхнюю грань полосой ±0.7 от линии, и при y=9.0 эта полоса
    захватывает пиксельную строку y=8 (алгоритм: [5..11]×8 непрозрачны),
    хотя мокап требует там сплошной просвет. Измерено на офскрин-рендере
    16×16 (PySide6 6.11.1): y=9.65 всё ещё даёт alpha=12 на строке 8,
    y=9.7 — первое значение с alpha=0 по всей строке (см. задачу 5 отчёта
    рестайла). Отклонение больше ±0.3 px, потому и не молчаливое —
    зафиксировано также в плане рестайла.
    """  # noqa: RUF002
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(2.5, 3.0, 11.0, 3.4), 0.7, 0.7)
    painter.drawRoundedRect(QRectF(2.5, 9.7, 11.0, 3.4), 0.7, 0.7)
    painter.setBrush(colour)
    painter.drawEllipse(QPointF(4.6, 4.7), 0.6, 0.6)
    painter.drawEllipse(QPointF(4.6, 11.4), 0.6, 0.6)


def _draw_web(painter: QPainter, colour: QColor) -> None:
    """Глобус контуром: круг — самое сильное отличие от прямоугольных

    значков в наборе, файловой и серверной баз. Экватор и меридиан —
    вспомогательные линии внутри, круг несёт узнавание.
    """
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(1.5, 1.5, 13.0, 13.0))
    painter.drawLine(QPointF(1.5, 8.0), QPointF(14.5, 8.0))
    painter.drawEllipse(QRectF(5.0, 1.5, 6.0, 13.0))


def _draw_unknown(painter: QPainter, colour: QColor) -> None:
    """Пунктирный круг со знаком вопроса: строку соединения не разобрали.

    Глобус веб-базы тоже круглый — различие держат пунктир, «?» внутри
    и цвет проблемы (спека рестайла §5; требование §1.3 спеки 4b
    «формой и цветом» выполняется контуром и цветом).
    """  # noqa: RUF002
    pen = QPen(colour)
    pen.setWidthF(1.4)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(2.4, 2.4, 11.2, 11.2))
    painter.setPen(QPen(colour))
    font = painter.font()
    font.setBold(True)
    font.setPointSizeF(7.0)
    painter.setFont(font)
    painter.drawText(QRectF(2.4, 2.4, 11.2, 11.2), Qt.AlignmentFlag.AlignCenter, "?")


_DRAW = {
    ConnectKind.FILE: _draw_file,
    ConnectKind.SERVER: _draw_server,
    ConnectKind.WEB: _draw_web,
    ConnectKind.UNKNOWN: _draw_unknown,
}
