"""Клавиша контекстного меню в дереве — меню текущей строки, а не соседней (T-46).

Клавиша меню на Windows приходит как WM_CONTEXTMENU, и Qt шлёт фокусному виджету
`QContextMenuEvent(Keyboard)` с позицией центра текущей строки — но в координатах
самого дерева, а не его viewport. `QAbstractScrollArea` такое событие не переводит
и отдаёт позицию в `customContextMenuRequested` как есть, хотя от мыши тот же сигнал
приходит в координатах viewport. Обработчики меню разбирают позицию через
`indexAt`, то есть как координаты viewport, и попадали на строку ниже текущей:
сдвиг — высота заголовка с рамкой (зонд 23.11.2026: 26 px, base3 → base4). В «Базах»
меню строилось для чужой базы («Свойства…» открывали другую), в EDT курсор ещё
и съезжал на строку ниже — `_show_menu` делает найденную строку текущей.

Исправление одно на оба дерева: событие с причиной `Keyboard` перехватывается
до Qt, и сигнал получает центр текущей строки в координатах viewport — после
`scrollTo`, чтобы строка, уехавшая за край прокрутки, была видна и под меню.
Нет текущей строки — позиция вне всех строк (`indexAt` даёт пустой индекс),
и обработчик показывает меню пустого места. Мышь не трогается.
"""  # noqa: RUF002

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QAbstractItemView

# Вне всех строк: `indexAt` от точки за пределами viewport даёт пустой индекс.
_NO_ROW = QPoint(-1, -1)


class _KeyboardMenuFilter(QObject):
    def __init__(self, view: QAbstractItemView) -> None:
        super().__init__(view)
        self._view = view

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 — имя Qt
        if (
            watched is not self._view
            or event.type() != QEvent.Type.ContextMenu
            or not isinstance(event, QContextMenuEvent)
            or event.reason() != QContextMenuEvent.Reason.Keyboard
            or self._view.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu
        ):
            return False
        view = self._view
        current = view.currentIndex()
        if current.isValid():
            view.scrollTo(current)
            position = view.visualRect(current).center()
        else:
            position = _NO_ROW
        view.customContextMenuRequested.emit(position)
        return True


def route_keyboard_menu(view: QAbstractItemView) -> None:
    """Клавиша меню открывает меню текущей строки `view` (см. докстринг модуля)."""
    view.installEventFilter(_KeyboardMenuFilter(view))
