"""Выбор группы деревом — `GroupPicker` (T-11, п. 5)."""

from typing import Any

import pytest

from onecstarter.ui.dialogs.group_picker import INDENT, ROOT_LABEL, GroupPicker, build_items


def test_items_follow_tree_order_with_indent() -> None:
    assert build_items(["/", "Клиенты/Розница", "Клиенты", "Архив"]) == [
        (ROOT_LABEL, "/"),
        ("Архив", "Архив"),
        ("Клиенты", "Клиенты"),
        (f"{INDENT}Розница", "Клиенты/Розница"),
    ]


def test_root_is_added_even_when_absent() -> None:
    assert build_items(["Клиенты"])[0] == (ROOT_LABEL, "/")


def test_path_without_parent_is_shown_whole() -> None:
    """Неявная группа записи ([Ф] T-05.7): родителя в списке нет — путь целиком, без отступа."""
    assert build_items(["/", "Нет такой группы/Вложенная"]) == [
        (ROOT_LABEL, "/"),
        ("Нет такой группы/Вложенная", "Нет такой группы/Вложенная"),
    ]


def test_picker_reports_paths_not_labels(qtbot: Any) -> None:
    picker = GroupPicker(["/", "Клиенты", "Клиенты/Розница"])
    qtbot.addWidget(picker)
    assert picker.paths() == ["/", "Клиенты", "Клиенты/Розница"]
    assert picker.current_path() == "/"


def test_set_current_path_selects_by_path(qtbot: Any) -> None:
    picker = GroupPicker(["/", "Клиенты", "Клиенты/Розница"])
    qtbot.addWidget(picker)
    picker.set_current_path("Клиенты/Розница")
    assert picker.current_path() == "Клиенты/Розница"
    assert picker.currentText() == f"{INDENT}Розница"


def test_set_current_path_rejects_unknown_path(qtbot: Any) -> None:
    picker = GroupPicker(["/"])
    qtbot.addWidget(picker)
    with pytest.raises(ValueError, match="Незнакомая"):
        picker.set_current_path("Незнакомая")


def test_ensure_path_keeps_order_and_selection(qtbot: Any) -> None:
    picker = GroupPicker(["/", "Клиенты"])
    qtbot.addWidget(picker)
    picker.set_current_path("Клиенты")
    picker.ensure_path("Архив")
    assert picker.paths() == ["/", "Архив", "Клиенты"]
    assert picker.current_path() == "Клиенты"
    picker.ensure_path("Клиенты")
    assert picker.paths() == ["/", "Архив", "Клиенты"]
