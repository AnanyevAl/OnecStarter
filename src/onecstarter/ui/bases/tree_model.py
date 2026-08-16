"""Qt-модель раздела «Базы»: QStandardItemModel, пересобираемая целиком.

Список измеряется килобайтами — пересборка при каждом изменении дешевле
бухгалтерии индексов QAbstractItemModel. Состояние развёрнутости
восстанавливает view по ключам (bases/view.py).
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel

from onecstarter.services.connection import BADGE_LABELS
from onecstarter.services.display import Row, RowKind, VersionCell, row_label
from onecstarter.ui.bases.icons import placement_icon
from onecstarter.ui.theme import Palette

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2

COLUMNS = ("База", "Версия", "Последний запуск")


def build_model(
    rows: Sequence[Row],
    cells: Mapping[str, VersionCell],
    format_stamp: Callable[[datetime], str],
    palette: Palette,
) -> QStandardItemModel:
    model = QStandardItemModel(0, len(COLUMNS))
    model.setHorizontalHeaderLabels(list(COLUMNS))
    for row in rows:
        model.appendRow(_items_for(row, cells, format_stamp, palette))
    return model


def _items_for(
    row: Row,
    cells: Mapping[str, VersionCell],
    format_stamp: Callable[[datetime], str],
    palette: Palette,
) -> list[QStandardItem]:
    # Пометки считает витрина (services/display.row_label): «в общем списке» —
    # дубль «пользовательская + общая», штатное состояние после первого
    # запуска общей базы ([Ф] T-05.2), удалять его не предлагаем; «не  # noqa: RUF003
    # разобрано» — битая запись (спека 4a, §2). Здесь только рисуем.
    name = QStandardItem(row_label(row))
    version = QStandardItem("")
    launched = QStandardItem("")
    for item in (name, version, launched):
        item.setEditable(False)
    name.setData(row.kind.value, KIND_ROLE)
    name.setData(None, KEY_ROLE)
    # Значок размещения получают только строки баз (не группы — их отличает
    # структура дерева, спека 4b §1.3). Для них тултип собирает note и подпись
    # вида вместе; для остальных строк действует прежняя одиночная установка
    # ниже, чтобы обе установки не затирали друг друга.  # noqa: RUF003
    has_placement_icon = (
        row.item is not None and not row.item.is_group and row.kind is RowKind.BASE
    )
    if row.note and not has_placement_icon:
        name.setToolTip(row.note)
    if row.kind is RowKind.SECTION:
        font = name.font()
        font.setBold(True)
        name.setFont(font)
    if row.kind in (RowKind.IMPLICIT_GROUP, RowKind.NOTE):
        name.setForeground(QBrush(QColor(palette.text_dim)))
    if row.item is not None:
        if has_placement_icon:
            name.setIcon(placement_icon(row.item.kind, palette))
            label = BADGE_LABELS[row.item.kind]
            name.setToolTip(f"{row.note}\n{label}" if row.note else label)
        if row.item.parse_error:
            name.setForeground(QBrush(QColor(palette.problem)))
        name.setData(row.item.key, KEY_ROLE)
        cell = cells.get(row.item.key)
        if cell is not None:
            version.setText(cell.text)
            if cell.hint:
                version.setToolTip(cell.hint)
            if cell.problem:
                version.setForeground(QBrush(QColor(palette.problem)))
        if row.item.last_launched_at is not None:
            launched.setText(format_stamp(row.item.last_launched_at))
    for child in row.children:
        name.appendRow(_items_for(child, cells, format_stamp, palette))
    return [name, version, launched]
