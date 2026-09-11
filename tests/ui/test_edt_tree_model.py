"""Модель дерева EDT: группы, фильтр, версия, статус, метка каталога (спека §7)."""

from itertools import count
from pathlib import Path

from PySide6.QtGui import QColor, QStandardItemModel
from PySide6.QtWidgets import QApplication

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.ui.edt.tree_model import (
    ID_ROLE,
    KIND_GROUP,
    KIND_PROJECT,
    KIND_ROLE,
    MISSING_SUFFIX,
    build_edt_model,
    matches,
)
from onecstarter.ui.theme import DARK

INSTALLED = [
    EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")
]


def _workspace(tmp_path: Path) -> EdtWorkspace:
    ids = count(1)
    ws = EdtWorkspace(
        tmp_path / "edt.json",
        discover=lambda: INSTALLED,
        edtstart=lambda: None,
        editors=lambda kind: None,  # type: ignore[arg-type, return-value]
        spawn=lambda c: 1,
        activate=lambda p: True,
        open_file=lambda p: None,
        new_id=lambda: f"id-{next(ids)}",
    )
    ws.refresh_installations()
    return ws


def _names(model: QStandardItemModel) -> list[tuple[str, str, int]]:
    """(kind, текст, глубина) в порядке обхода."""
    out: list[tuple[str, str, int]] = []

    def walk(parent, depth: int) -> None:  # type: ignore[no-untyped-def]
        for row in range(parent.rowCount()):
            item = parent.child(row, 0)
            out.append((item.data(KIND_ROLE), item.text(), depth))
            walk(item, depth + 1)

    walk(model.invisibleRootItem(), 0)
    return out


def test_tree_shape_follows_workspace_order(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    g = ws.add_group("2025", None)
    ws.add_project(
        EdtProject("", "Розница", r"D:\a", edt_version="2025.2.6+4", group_id=g.id)
    )
    ws.add_project(EdtProject("", "Опт", r"D:\b", edt_version="2025.2.6+4"))
    model = build_edt_model(ws, "", DARK)
    assert _names(model) == [
        (KIND_GROUP, "2025", 0),
        (KIND_PROJECT, "Розница", 1),
        (KIND_PROJECT, "Опт", 0),
    ]
    assert model.item(0, 0).data(ID_ROLE) == g.id


def test_filter_keeps_group_with_matching_descendant(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    g = ws.add_group("2025", None)
    ws.add_project(EdtProject("", "Розница", r"D:\a", group_id=g.id))
    ws.add_project(EdtProject("", "Опт", r"D:\b"))
    model = build_edt_model(ws, "роз", DARK)
    assert _names(model) == [(KIND_GROUP, "2025", 0), (KIND_PROJECT, "Розница", 1)]


def test_empty_group_visible_without_filter(tmp_path: Path) -> None:
    """C1 финального ревью: «Создать группу» без записей обязана дать видимую строку."""
    ws = _workspace(tmp_path)
    g = ws.add_group("Пустая", None)
    nested = ws.add_group("Вложенная пустая", g.id)
    model = build_edt_model(ws, "", DARK)
    assert _names(model) == [
        (KIND_GROUP, "Пустая", 0),
        (KIND_GROUP, "Вложенная пустая", 1),
    ]
    assert model.item(0, 0).data(ID_ROLE) == g.id
    assert model.item(0, 0).child(0, 0).data(ID_ROLE) == nested.id


def test_empty_group_hidden_under_filter(tmp_path: Path) -> None:
    """Под непустым фильтром показываются только группы с совпадениями."""  # noqa: RUF002
    ws = _workspace(tmp_path)
    ws.add_group("Пустая", None)
    ws.add_project(EdtProject("", "Розница", r"D:\a"))
    model = build_edt_model(ws, "роз", DARK)
    assert _names(model) == [(KIND_PROJECT, "Розница", 0)]
    assert _names(build_edt_model(ws, "   ", DARK)) == [
        (KIND_GROUP, "Пустая", 0),
        (KIND_PROJECT, "Розница", 0),
    ]


def test_filter_matches_workspace_path_too(tmp_path: Path) -> None:
    project = EdtProject("", "Опт", r"D:\edt\wholesale")
    assert matches(project, "WHOLE") is True
    assert matches(project, "розн") is False
    assert matches(project, "") is True


def test_version_column_marks_not_installed(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Старая", r"D:\a", edt_version="2024.2.6+7"))
    ws.add_project(EdtProject("", "Новая", r"D:\b", edt_version="2025.2.6+4"))
    model = build_edt_model(ws, "", DARK)
    old, new = model.item(0, 1), model.item(1, 1)
    assert old.text() == "2024.2.6+7"
    assert old.toolTip() == "EDT 2024.2.6+7 не найден"
    assert old.foreground().color() == QColor(DARK.problem)
    assert new.toolTip() == ""
    assert new.foreground().color() != QColor(DARK.problem)


def test_empty_version_shows_dash(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Без версии", r"D:\a"))
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 1).text() == "—"
    assert model.item(0, 1).toolTip() == "Версия EDT не задана"


def test_running_icon_and_missing_dir_after_scan(tmp_path: Path, qapp: QApplication) -> None:
    ws = _workspace(tmp_path)
    p = ws.add_project(EdtProject("", "Розница", r"D:\a", edt_version="2025.2.6+4"))
    ws.apply_scan(EdtScan(running={p.id: 42}, present={p.id: False}))
    model = build_edt_model(ws, "", DARK)
    name = model.item(0, 0)
    assert name.text() == "Розница" + MISSING_SUFFIX
    assert not name.icon().isNull()
    assert "Запущен (PID 42)" in name.toolTip()
    assert model.columnCount() == 2


def test_no_status_before_scan(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Розница", r"D:\a"))
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 0).text() == "Розница"
    assert model.item(0, 0).icon().isNull()
    assert model.item(0, 0).toolTip() == r"D:\a"


def test_tooltip_lists_project_dir(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Р", r"D:\a", project_dir=r"D:\a\proj"))  # noqa: RUF001
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 0).toolTip() == "D:\\a\nПроект: D:\\a\\proj"  # noqa: RUF001
