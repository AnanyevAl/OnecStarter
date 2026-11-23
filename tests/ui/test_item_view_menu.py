"""Клавиша контекстного меню в дереве — меню текущей строки (T-46).

Клавиша меню на Windows приходит как WM_CONTEXTMENU, и Qt шлёт фокусному виджету
`QContextMenuEvent(Keyboard)` с позицией центра `inputMethodQuery(ImCursorRectangle)`
в координатах САМОГО дерева, а `customContextMenuRequested` у `QAbstractScrollArea`
отдаёт её как есть — тогда как мышь даёт координаты viewport. `keyboard_event`
повторяет путь Qt: `QTest.keyClick(..., Key_Menu)` до меню не доходит вовсе.
"""  # noqa: RUF002

from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QTreeView

from onecstarter.ui.item_view_menu import route_keyboard_menu


def keyboard_event(tree: QTreeView) -> None:
    """Послать дереву событие меню так, как это делает Qt по клавише меню."""
    pos = tree.inputMethodQuery(Qt.InputMethodQuery.ImCursorRectangle).center()
    QApplication.sendEvent(
        tree, QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, pos, tree.mapToGlobal(pos))
    )


def _tree(qtbot: Any, rows: int = 12) -> QTreeView:
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["База", "Версия"])
    for i in range(rows):
        model.appendRow([QStandardItem(f"base{i}"), QStandardItem("8.3")])
    tree = QTreeView()
    tree.setModel(model)
    tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    tree.resize(400, 300)
    qtbot.addWidget(tree)
    with qtbot.waitExposed(tree):
        tree.show()
    return tree


def _requested_rows(tree: QTreeView) -> list[str]:
    rows: list[str] = []
    tree.customContextMenuRequested.connect(lambda pos: rows.append(tree.indexAt(pos).data()))
    return rows


def test_keyboard_menu_targets_the_current_row(qtbot):
    tree = _tree(qtbot)
    route_keyboard_menu(tree)
    rows = _requested_rows(tree)
    model = tree.model()
    for row in (0, 3, 7):
        tree.setCurrentIndex(model.index(row, 0))
        keyboard_event(tree)
    assert rows == ["base0", "base3", "base7"]


def test_keyboard_menu_scrolls_to_a_current_row_out_of_view(qtbot):
    """Строка за краем прокрутки: `indexAt` нашёл бы её и так, но меню открылось бы
    за пределами видимой области — позиция обязана лежать внутри viewport."""
    tree = _tree(qtbot, rows=200)
    route_keyboard_menu(tree)
    seen: list[QPoint] = []
    tree.customContextMenuRequested.connect(seen.append)
    model = tree.model()
    tree.setCurrentIndex(model.index(150, 0))
    tree.scrollToTop()
    keyboard_event(tree)
    assert len(seen) == 1
    assert tree.viewport().rect().contains(seen[0])
    assert tree.indexAt(seen[0]).data() == "base150"


def test_mouse_menu_position_is_left_as_is(qtbot):
    tree = _tree(qtbot)
    route_keyboard_menu(tree)
    seen: list[QPoint] = []
    tree.customContextMenuRequested.connect(seen.append)
    pos = QPoint(5, 7)
    QApplication.sendEvent(
        tree.viewport(),
        QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, tree.viewport().mapToGlobal(pos)),
    )
    assert seen == [pos]


def test_keyboard_menu_without_current_row_targets_no_row(qtbot):
    tree = _tree(qtbot, rows=2)
    route_keyboard_menu(tree)
    rows = _requested_rows(tree)
    tree.setCurrentIndex(tree.model().index(-1, -1))
    keyboard_event(tree)
    assert rows == [None]
