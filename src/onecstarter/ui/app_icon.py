"""Фирменный значок приложения — единственный источник глифа.

Заказчик на контрольной точке 16.08.2026 показал скриншот с тремя РАЗНЫМИ
значками одновременно: заголовок окна (Qt-иконка не ставилась вовсе, Windows
подставляла своё), панель задач (`build/onecstarter.ico`, «полки» — верный
бренд) и трей (свой жёлтый треугольник запуска, `ui/tray.py`). Решение
заказчика: значки обязаны быть одинаковыми — «полки», как в exe.

Рисование живёт здесь один раз. `build/make_icon.py` и `onecstarter.ui.tray`
импортируют отсюда, а не рисуют сами — до этой задачи оба места держали
собственную копию похожего, но не идентичного рисования.
"""  # noqa: RUF002

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from onecstarter.ui import theme

# Кадры QIcon — заголовок окна (Alt-Tab), панель задач через QApplication
# и трей. `build/make_icon.py` собирает `.ico` из другого, большего набора
# размеров (свой SIZES там) — тот же рисунок, другое место назначения.
ICON_SIZES = (16, 24, 32, 48, 256)


def draw_app_icon(size: int) -> QImage:
    """Фирменный значок: скруглённый квадрат surface + «полки» accent_fill.

    Палитра НЕ параметр: значок — идентичность приложения в заголовке,
    панели задач и трее, он не перекрашивается при смене темы (решение
    заказчика 16.08.2026: все значки одинаковые, всегда). Рисование — то же,
    что раньше жило в `build/make_icon.py::draw_frame` (тот теперь
    импортирует отсюда), пропорции не менялись: radius 0.2, margin 0.22,
    bar 0.12, step 0.2.
    """  # noqa: RUF002
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.DARK.surface))
    radius = size * 0.2
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setBrush(QColor(theme.DARK.accent_fill))
    margin = size * 0.22
    bar_height = size * 0.12
    step = size * 0.2
    for row in range(3):
        top = margin + row * step
        painter.drawRoundedRect(
            QRectF(margin, top, size - 2 * margin, bar_height),
            bar_height / 2,
            bar_height / 2,
        )
    painter.end()
    return image


def application_icon() -> QIcon:
    """QIcon из кадров `ICON_SIZES` — на `QApplication` и/или окно.

    Один и тот же результат ставится и на приложение (панель задач/Alt-Tab
    через `QApplication.setWindowIcon`, единственная точка в `ui/app.py`),
    и собирается тонкой обёрткой в трее (`ui/tray.py::make_icon`) — оба
    потребителя получают идентичные пиксели, не только «похожий» рисунок.
    """  # noqa: RUF002
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(draw_app_icon(size)))
    return icon
