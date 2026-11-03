"""ColumnWidths (T-38): растяжение имени, восстановление и отложенная запись ширин."""

from typing import Any

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QHeaderView, QTreeView

from onecstarter.ui.column_widths import ColumnWidths

IDS = ("name", "a", "b")


def _model() -> QStandardItemModel:
    model = QStandardItemModel(0, len(IDS))
    model.setHorizontalHeaderLabels(["Имя", "А", "Б"])  # noqa: RUF001
    model.appendRow([QStandardItem("строка"), QStandardItem("1"), QStandardItem("2")])
    return model


def _tree(qtbot: Any) -> QTreeView:
    tree = QTreeView()
    qtbot.addWidget(tree)
    return tree


def _keeper(
    tree: QTreeView,
    saved: dict[str, int] | None = None,
    saves: list[dict[str, int]] | None = None,
) -> ColumnWidths:
    record = saves if saves is not None else []
    keeper = ColumnWidths(tree, IDS, saved or {}, record.append, delay_ms=20)
    with keeper.rebuilding():
        tree.setModel(_model())
    return keeper


def test_name_column_stretches_after_each_rebuild(qtbot: Any) -> None:
    tree = _tree(qtbot)
    keeper = _keeper(tree)
    with keeper.rebuilding():
        tree.setModel(_model())
    header = tree.header()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert not header.stretchLastSection()


def test_saved_widths_are_applied_and_name_and_unknown_ignored(qtbot: Any) -> None:
    tree = _tree(qtbot)
    keeper = _keeper(tree, saved={"a": 77, "b": 55, "name": 999, "unknown": 10})
    assert tree.columnWidth(1) == 77
    assert tree.columnWidth(2) == 55
    assert set(keeper.widths()) == {"a", "b"}


def test_missing_widths_are_fitted_once_and_kept_in_session(qtbot: Any) -> None:
    tree = _tree(qtbot)
    keeper = _keeper(tree)
    assert set(keeper.widths()) == {"a", "b"}
    fitted = tree.columnWidth(1)
    with keeper.rebuilding():
        tree.setModel(_model())
    assert tree.columnWidth(1) == fitted


def test_user_width_survives_rebuild(qtbot: Any) -> None:
    tree = _tree(qtbot)
    keeper = _keeper(tree)
    tree.setColumnWidth(1, 66)
    with keeper.rebuilding():
        tree.setModel(_model())
    assert tree.columnWidth(1) == 66


def test_series_of_resizes_gives_one_save_without_name(qtbot: Any) -> None:
    tree = _tree(qtbot)
    saves: list[dict[str, int]] = []
    _keeper(tree, saves=saves)
    for width in (60, 61, 62, 63):
        tree.setColumnWidth(1, width)
    qtbot.waitUntil(lambda: len(saves) == 1, timeout=1000)
    qtbot.wait(80)
    assert len(saves) == 1
    assert saves[0]["a"] == 63
    assert "name" not in saves[0]


def test_programmatic_rebuild_does_not_save(qtbot: Any) -> None:
    tree = _tree(qtbot)
    saves: list[dict[str, int]] = []
    keeper = _keeper(tree, saved={"a": 70}, saves=saves)
    with keeper.rebuilding():
        tree.setModel(_model())
    qtbot.wait(80)
    assert saves == []
