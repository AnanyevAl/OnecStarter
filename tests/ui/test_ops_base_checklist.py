"""Дерево баз с флажками — окно запуска и список баз сценария (спека v4, §7.4, §7.5)."""  # noqa: RUF002

from dataclasses import replace
from typing import Any

from PySide6.QtCore import Qt

from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.operations import BaseRef
from onecstarter.services.model import InfobaseItem
from onecstarter.ui.ops.base_checklist import BaseChecklist, BaseListDialog
from onecstarter.ui.theme import LIGHT


def _items(workspace_factory: Any) -> list[InfobaseItem]:
    workspace, _, _ = workspace_factory()
    items: list[InfobaseItem] = workspace.items()
    return items


def _bases(items: list[InfobaseItem]) -> list[InfobaseItem]:
    return [item for item in items if not item.is_group]


def test_bases_are_listed_under_their_groups_and_checked_by_key(
    qtbot: Any, workspace_factory: Any
) -> None:
    items = _items(workspace_factory)
    bases = _bases(items)
    widget = BaseChecklist(items, checked=[bases[0].key])
    qtbot.addWidget(widget)
    assert len(widget.base_labels()) == len(bases)
    assert widget.checked_keys() == [bases[0].key]
    assert widget.count_text() == "отмечено 1"
    assert not any(item.is_group and item.name in widget.base_labels() for item in items)


def test_checking_emits_changed_and_keeps_display_order(qtbot: Any, workspace_factory: Any) -> None:
    items = _items(workspace_factory)
    bases = _bases(items)
    widget = BaseChecklist(items)
    qtbot.addWidget(widget)
    changes: list[int] = []
    widget.changed.connect(lambda: changes.append(1))

    widget.set_checked(bases[-1].key, True)
    widget.set_checked(bases[0].key, True)

    assert len(changes) == 2
    shown = [key for key in widget.all_keys() if key in (bases[0].key, bases[-1].key)]
    assert widget.checked_keys() == shown
    assert widget.checked_refs() == [
        BaseRef(key, next(b.name for b in bases if b.key == key)) for key in shown
    ]


def test_group_checkbox_checks_its_bases_and_shows_partial_state(
    qtbot: Any, workspace_factory: Any
) -> None:
    items = _items(workspace_factory)
    widget = BaseChecklist(items)
    qtbot.addWidget(widget)
    path = widget.group_paths()[0]
    members = widget.group_keys(path)
    assert members and widget.group_state(path) == Qt.CheckState.Unchecked

    widget.set_checked(members[0], True)
    expected = Qt.CheckState.Checked if len(members) == 1 else Qt.CheckState.PartiallyChecked
    assert widget.group_state(path) == expected

    widget.set_group_checked(path, True)
    assert set(members) <= set(widget.checked_keys())
    assert widget.group_state(path) == Qt.CheckState.Checked
    widget.set_group_checked(path, False)
    assert not set(members) & set(widget.checked_keys())


def test_missing_saved_bases_are_listed_separately_and_checked(
    qtbot: Any, workspace_factory: Any
) -> None:
    items = _items(workspace_factory)
    widget = BaseChecklist(items, missing=[BaseRef("id:gone", "Розница старая")])
    qtbot.addWidget(widget)
    assert widget.group_paths()[-1] == "Из сохранённого списка"
    assert "Розница старая — не найдена в списке баз" in widget.base_labels()
    assert widget.checked_keys() == ["id:gone"]
    assert widget.checked_refs() == [BaseRef("id:gone", "Розница старая")]


def test_web_base_is_marked(qtbot: Any, workspace_factory: Any) -> None:
    items = _items(workspace_factory)
    web = next(item for item in _bases(items) if item.kind is ConnectKind.WEB)
    widget = BaseChecklist(items)
    qtbot.addWidget(widget)
    assert f"{web.name} · веб" in widget.base_labels()


def test_search_hides_bases_and_bulk_buttons_touch_only_visible(
    qtbot: Any, workspace_factory: Any
) -> None:
    items = _items(workspace_factory)
    bases = _bases(items)
    widget = BaseChecklist(items)
    qtbot.addWidget(widget)
    needle = bases[0].name
    widget.search(needle.upper())
    visible = widget.visible_keys()
    assert bases[0].key in visible and len(visible) < len(bases)

    widget.check_all()
    assert sorted(widget.checked_keys()) == sorted(visible)
    widget.search("")
    widget.check_all()
    assert len(widget.checked_keys()) == len(bases)
    widget.search(needle)
    widget.uncheck_all()
    assert not set(visible) & set(widget.checked_keys())
    assert len(widget.checked_keys()) == len(bases) - len(visible)


def test_group_checkbox_toggles_back_under_search(qtbot: Any, workspace_factory: Any) -> None:
    template = _bases(_items(workspace_factory))[0]
    items = [
        replace(template, key=f"id:g{n}", name=name, folder="Группа", kind=ConnectKind.FILE)
        for n, name in enumerate(["Альфа", "Альфонс", "Бета"])
    ]
    widget = BaseChecklist(items)
    qtbot.addWidget(widget)
    path = widget.group_paths()[0]
    members = widget.group_keys(path)
    widget.search("альф")
    visible = [key for key in members if key in widget.visible_keys()]
    hidden = [key for key in members if key not in visible]
    assert visible == ["id:g0", "id:g1"] and hidden == ["id:g2"]

    widget.set_group_checked(path, True)
    assert set(visible) <= set(widget.checked_keys())
    assert not set(hidden) & set(widget.checked_keys())
    assert widget.group_state(path) == Qt.CheckState.Checked

    widget.set_group_checked(path, False)
    assert not set(members) & set(widget.checked_keys())
    assert widget.group_state(path) == Qt.CheckState.Unchecked


def test_search_matches_base_name_not_caption(qtbot: Any, workspace_factory: Any) -> None:
    items = _items(workspace_factory)
    web = next(item for item in _bases(items) if item.kind is ConnectKind.WEB)
    widget = BaseChecklist(items, missing=[BaseRef("id:gone", "Розница старая")])
    qtbot.addWidget(widget)
    assert "веб" not in web.name.casefold()
    widget.search("· веб")
    assert web.key not in widget.visible_keys()
    widget.search("не найдена")
    assert "id:gone" not in widget.visible_keys()
    widget.search("розница стар")
    assert widget.visible_keys() == ["id:gone"]


def test_base_in_items_and_missing_checks_the_existing_row(
    qtbot: Any, workspace_factory: Any
) -> None:
    items = _items(workspace_factory)
    base = _bases(items)[0]
    widget = BaseChecklist(items, missing=[BaseRef(base.key, base.name)])
    qtbot.addWidget(widget)
    assert widget.all_keys().count(base.key) == 1
    assert "Из сохранённого списка" not in widget.group_paths()
    assert widget.checked_keys() == [base.key]


def test_dialog_wraps_the_checklist(qtbot: Any, workspace_factory: Any) -> None:
    items = _items(workspace_factory)
    bases = _bases(items)
    dialog = BaseListDialog(items, checked=[bases[1].key])
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Список баз сценария"
    assert dialog.checklist().checked_keys() == [bases[1].key]


def test_groups_are_bold_and_missing_bases_are_red(qtbot: Any, workspace_factory: Any) -> None:
    """Мокап, экран 5 (стр. 312, 320, 322): `.g` жирно, «не найдена» — `--err`, счётчик — `.q`."""
    items = _items(workspace_factory)
    widget = BaseChecklist(items, missing=[BaseRef("id:gone", "Розница старая")], palette=LIGHT)
    qtbot.addWidget(widget)
    assert widget.group_paths()
    for path in widget.group_paths():
        assert widget.group_item(path).font(0).bold()
    assert widget.base_item("id:gone").foreground(0).color().name() == LIGHT.problem
    present = _bases(items)[0].key
    assert widget.base_item(present).foreground(0).color().name() != LIGHT.problem
    assert widget.count_label().objectName() == "Hint"
