"""Смотр значков видов размещения — smoke №1 (08.08.2026), замечание 2.

Заказчик: «значки не читаются», на скриншоте все четыре — одинаковые
тёмные квадраты. Причина — заливка (`painter.setBrush(colour)` + `drawRect`)
на 16 px съедает силуэт, плюс у папки и стойки были одинаковые пропорции
(оба почти квадрат). Правка в `ui/bases/icons.py` переводит все фигуры
на контур и разводит пропорции: папка заметно шире, чем выше, стойка
заметно выше, чем шире, глобус — круг против прямоугольников остальных.

Этот скрипт показывает натуральный размер (16 px, как в дереве) и
увеличенный (×8 = 128 px, тем же самым QPixmap — не перерисован заново,
поэтому форма ровно та, что попадёт на экран) для обеих палитр. Для папки
и стойки — два варианта силуэта: A — тот, что сейчас в коде, B — запасной,
на выбор заказчику, если A не устроит по прочтении. Веб и «не разобрано»
показаны в одном варианте: круг и так самый сильный контраст в наборе,
а пунктир+«?» заказчик уже видел и просил не трогать.

Не тест и не часть пакета — рабочий файл процесса, в git не идёт.

Запуск (интерактивный показ, как раньше): uv run python .superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py
Запуск (офскрин-снимок в PNG, для контрольной точки без живого дисплея):
uv run python .superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py --save путь/к/файлу.png

Задача 5 (веха v2.4, крестик «нет каталога» у файловой базы) дописала секцию
сравнения обычного файлового значка и значка с `missing=True` — рядом,
натурально и увеличенно, в обеих палитрах: контрольная точка §4.1 спеки
требует смотреть глазами, читается ли крестик 6×6 на 16 px.
"""  # noqa: RUF002

import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.connect import ConnectKind
from onecstarter.ui import theme
from onecstarter.ui.bases.icons import placement_icon
from onecstarter.ui.theme import Palette

_SIZE = 16
_ZOOM = 8


# -- Вариант B (запасной) для папки и стойки — тот же приём, другая форма --


def _draw_file_b(painter: QPainter, colour: QColor) -> None:
    """Папка, вариант B: язычок отдельным прямоугольником, тело скруглённое."""  # noqa: RUF002
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(1.5, 4.0, 4.5, 1.8))
    painter.drawRoundedRect(QRectF(1.5, 5.8, 13.0, 7.2), 1.2, 1.2)


def _draw_server_b(painter: QPainter, colour: QColor) -> None:
    """Стойка, вариант B: три отдельных юнита с зазорами вместо линий внутри."""  # noqa: RUF002
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for top in (1.5, 6.2, 10.9):
        painter.drawRoundedRect(QRectF(5.0, top, 6.0, 3.6), 0.8, 0.8)
    painter.setBrush(colour)
    painter.drawEllipse(QPointF(9.3, 3.3), 0.6, 0.6)


def _icon_variant(draw, kind: ConnectKind, palette: Palette) -> QIcon:
    """Та же сборка, что и placement_icon, но с чужой функцией рисования —

    для показа альтернативы без правки production-кода icons.py.
    """  # noqa: RUF002
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    colour = QColor(palette.problem if kind is ConnectKind.UNKNOWN else palette.text_dim)
    pen = QPen(colour)
    pen.setWidthF(1.4)
    painter.setPen(pen)
    draw(painter, colour)
    painter.end()
    return QIcon(pixmap)


def _label_for(icon: QIcon, background: str) -> QLabel:
    pixmap = icon.pixmap(_SIZE, _SIZE)
    zoomed = pixmap.scaled(
        _SIZE * _ZOOM,
        _SIZE * _ZOOM,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    label = QLabel()
    label.setPixmap(zoomed)
    label.setStyleSheet(f"background: {background}; padding: 6px;")
    label.setFixedSize(_SIZE * _ZOOM + 12, _SIZE * _ZOOM + 12)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _natural_label(icon: QIcon, background: str) -> QLabel:
    label = QLabel()
    label.setPixmap(icon.pixmap(_SIZE, _SIZE))
    label.setStyleSheet(f"background: {background}; padding: 6px;")
    label.setFixedSize(_SIZE + 12, _SIZE + 12)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


_KIND_LABEL = {
    ConnectKind.FILE: "Файловая",
    ConnectKind.SERVER: "Серверная",
    ConnectKind.WEB: "Веб",
    ConnectKind.UNKNOWN: "Не разобрано",
}

_VARIANT_B = {
    ConnectKind.FILE: _draw_file_b,
    ConnectKind.SERVER: _draw_server_b,
}


def _palette_section(palette: Palette, title: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setStyleSheet(
        f"QGroupBox {{ background: {palette.background}; color: {palette.text}; "
        f"font-weight: bold; border: 1px solid {palette.border}; margin-top: 8px; }}"
        f"QGroupBox::title {{ subcontrol-origin: margin; padding: 0 4px; }}"
    )
    grid = QGridLayout(box)

    headers = ["Вид", "16 px (A)", "×8 (A)", "16 px (B)", "×8 (B)"]
    for column, text in enumerate(headers):
        header = QLabel(text)
        header.setStyleSheet(f"color: {palette.text_dim};")
        grid.addWidget(header, 0, column)

    for row, kind in enumerate(ConnectKind, start=1):
        name = QLabel(_KIND_LABEL[kind])
        name.setStyleSheet(f"color: {palette.text};")
        grid.addWidget(name, row, 0)

        icon_a = placement_icon(kind, palette)
        grid.addWidget(_natural_label(icon_a, palette.background), row, 1)
        grid.addWidget(_label_for(icon_a, palette.background), row, 2)

        draw_b = _VARIANT_B.get(kind)
        if draw_b is not None:
            icon_b = _icon_variant(draw_b, kind, palette)
            grid.addWidget(_natural_label(icon_b, palette.background), row, 3)
            grid.addWidget(_label_for(icon_b, palette.background), row, 4)

    return box


def _missing_mark_section(palette: Palette, title: str) -> QGroupBox:
    """Файловый значок обычный и с крестиком «нет каталога» — рядом, для сравнения.

    Задача 5 (веха v2.4): контрольная точка §4.1 спеки требует смотреть
    глазами, а не рассуждением — на 16 px крестик 6×6 это четыре пикселя
    линии, и читается он или нет, решает факт рендера.
    """  # noqa: RUF002
    box = QGroupBox(title)
    box.setStyleSheet(
        f"QGroupBox {{ background: {palette.background}; color: {palette.text}; "
        f"font-weight: bold; border: 1px solid {palette.border}; margin-top: 8px; }}"
        f"QGroupBox::title {{ subcontrol-origin: margin; padding: 0 4px; }}"
    )
    grid = QGridLayout(box)

    headers = ["Вариант", "16 px", "×8"]
    for column, text in enumerate(headers):
        header = QLabel(text)
        header.setStyleSheet(f"color: {palette.text_dim};")
        grid.addWidget(header, 0, column)

    rows = (
        ("Обычная", placement_icon(ConnectKind.FILE, palette)),
        ("Нет каталога", placement_icon(ConnectKind.FILE, palette, missing=True)),
    )
    for row, (label_text, icon) in enumerate(rows, start=1):
        name = QLabel(label_text)
        name.setStyleSheet(f"color: {palette.text};")
        grid.addWidget(name, row, 0)
        grid.addWidget(_natural_label(icon, palette.background), row, 1)
        grid.addWidget(_label_for(icon, palette.background), row, 2)

    return box


def _save_path(argv: list[str]) -> str | None:
    """Путь для офскрин-снимка, если он запрошен флагом `--save PATH`.

    Без флага поведение не меняется — интерактивный показ, как и раньше.
    С флагом снимок не требует живого дисплея (контрольная точка §4.1
    задачи 5 снималась в агентской сессии без окна).
    """  # noqa: RUF002
    if "--save" in argv:
        return argv[argv.index("--save") + 1]
    return None


def main() -> int:
    save_path = _save_path(sys.argv[1:])
    if save_path is not None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    application = QApplication(sys.argv[:1])
    window = QWidget()
    window.setWindowTitle("Значки размещения — smoke №1, замечание 2")
    layout = QVBoxLayout(window)
    note = QLabel(
        "Смотреть без прищура: на 16 px все четыре значка обязаны различаться.\n"
        "Вариант A — в коде сейчас; вариант B — запасной, на выбор для папки и стойки.\n"
        "Веб и «не разобрано» показаны в одном варианте (см. докстринг файла).\n"
        "Ниже — файловый значок с крестиком «нет каталога» (задача 5, веха v2.4)."
    )
    layout.addWidget(note)
    layout.addWidget(_palette_section(theme.DARK, "Тёмная"))
    layout.addWidget(_palette_section(theme.LIGHT, "Светлая"))
    layout.addWidget(_missing_mark_section(theme.DARK, "Нет каталога — тёмная"))
    layout.addWidget(_missing_mark_section(theme.LIGHT, "Нет каталога — светлая"))
    window.show()

    if save_path is not None:
        application.processEvents()
        window.adjustSize()
        application.processEvents()
        image = window.grab().toImage()
        image.save(save_path)
        return 0

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
