"""Координатор раздела EDT: записи, группы, порядок (спека §2), сохранение после каждой правки."""

from itertools import count
from pathlib import Path

import pytest

from onecstarter.domain.edt import EdtProject
from onecstarter.services.edt import EdtWorkspace
from onecstarter.services.edt_store import load_registry
from onecstarter.services.errors import InvalidRequestError, UnknownItemError


def _workspace(tmp_path: Path) -> EdtWorkspace:
    ids = count(1)
    return EdtWorkspace(
        tmp_path / "edt.json",
        discover=lambda: [],
        edtstart=lambda: None,
        editors=lambda kind: None,  # type: ignore[arg-type, return-value]
        spawn=lambda command: 1,
        activate=lambda pid: True,
        open_file=lambda path: None,
        new_id=lambda: f"id-{next(ids)}",
    )


def _project(name: str, **overrides: object) -> EdtProject:
    values: dict[str, object] = {"id": "", "name": name, "workspace": rf"D:\edt\{name}"}
    values.update(overrides)
    return EdtProject(**values)  # type: ignore[arg-type]


class TestProjects:
    def test_add_assigns_id_and_saves(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        added = ws.add_project(_project("a"))
        assert added.id == "id-1"
        assert [p.id for p in load_registry(tmp_path / "edt.json").projects] == ["id-1"]

    def test_add_rejects_empty_name_or_workspace(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        with pytest.raises(InvalidRequestError):
            ws.add_project(_project("", workspace=r"D:\x"))
        with pytest.raises(InvalidRequestError):
            ws.add_project(_project("a", workspace="  "))

    def test_add_rejects_relative_workspace(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidRequestError):
            _workspace(tmp_path).add_project(_project("a", workspace=r"edt\a"))

    def test_update_and_remove(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        added = ws.add_project(_project("a"))
        ws.update_project(EdtProject(id=added.id, name="b", workspace=added.workspace))
        assert ws.project(added.id).name == "b"
        ws.remove_project(added.id)
        assert ws.projects() == []
        with pytest.raises(UnknownItemError):
            ws.project(added.id)

    def test_update_unknown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnknownItemError):
            _workspace(tmp_path).update_project(_project("a", id="ghost"))


class TestGroups:
    def test_add_rename_remove_promotes_children(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("2025", None)
        child = ws.add_group("Розница", root.id)
        project = ws.add_project(_project("a", group_id=child.id))
        ws.rename_group(child.id, "Опт")
        assert [g.name for g in ws.groups()] == ["2025", "Опт"]
        ws.remove_group(child.id)
        assert ws.project(project.id).group_id == root.id
        assert [g.id for g in ws.groups()] == [root.id]

    def test_remove_root_group_promotes_to_root(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("2025", None)
        sub = ws.add_group("x", root.id)
        ws.remove_group(root.id)
        assert ws.groups()[0].id == sub.id
        assert ws.groups()[0].parent_id is None

    def test_add_rejects_empty_name_and_unknown_parent(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        with pytest.raises(InvalidRequestError):
            ws.add_group("  ", None)
        with pytest.raises(UnknownItemError):
            ws.add_group("x", "ghost")

    def test_children_lists_direct_only_in_order(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("2025", None)
        ws.add_group("inner", root.id)
        b = ws.add_project(_project("b", group_id=root.id))
        a = ws.add_project(_project("a", group_id=root.id))
        top = ws.add_project(_project("top"))
        groups, projects = ws.children(root.id)
        assert [g.name for g in groups] == ["inner"]
        assert [p.id for p in projects] == [b.id, a.id]
        assert [p.id for p in ws.children(None)[1]] == [top.id]


class TestMove:
    def test_move_project_between_groups_and_positions(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        g = ws.add_group("g", None)
        a = ws.add_project(_project("a"))
        b = ws.add_project(_project("b"))
        c = ws.add_project(_project("c"))
        ws.move_project(c.id, None, 0)
        assert [p.id for p in ws.children(None)[1]] == [c.id, a.id, b.id]
        ws.move_project(a.id, g.id, 0)
        assert [p.id for p in ws.children(g.id)[1]] == [a.id]
        assert [p.id for p in ws.children(None)[1]] == [c.id, b.id]
        ws.move_project(b.id, None, 0)
        assert [p.id for p in ws.children(None)[1]] == [b.id, c.id]

    def test_move_project_position_past_end_appends(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        a = ws.add_project(_project("a"))
        b = ws.add_project(_project("b"))
        ws.move_project(a.id, None, 99)
        assert [p.id for p in ws.children(None)[1]] == [b.id, a.id]

    def test_move_group_into_own_descendant_rejected(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("root", None)
        child = ws.add_group("child", root.id)
        with pytest.raises(InvalidRequestError):
            ws.move_group(root.id, child.id, 0)
        with pytest.raises(InvalidRequestError):
            ws.move_group(root.id, root.id, 0)

    def test_move_group_reorders_siblings(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        a = ws.add_group("a", None)
        b = ws.add_group("b", None)
        ws.move_group(b.id, None, 0)
        assert [g.id for g in ws.children(None)[0]] == [b.id, a.id]

    def test_moves_are_persisted(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        a = ws.add_project(_project("a"))
        b = ws.add_project(_project("b"))
        ws.move_project(b.id, None, 0)
        assert [p.id for p in load_registry(tmp_path / "edt.json").projects] == [b.id, a.id]
