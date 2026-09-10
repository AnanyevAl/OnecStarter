"""EdtView: дерево, фильтр, запуск по Enter/двойному клику, статус, F5 (спека §7)."""

from itertools import count
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from onecstarter.domain.edt import EditorResolution, EdtInstallation, EdtProject
from onecstarter.domain.launch import LaunchCommand
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.ui.edt.tree_model import ID_ROLE, RUNNING_GLYPH
from onecstarter.ui.edt.view import EdtView
from onecstarter.ui.theme import DARK

INSTALLED = [
    EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")
]


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        ids = count(1)
        self.spawned: list[LaunchCommand] = []
        self.activated: list[int] = []
        self.opened: list[str] = []
        self.errors: list[str] = []
        self.scans_requested = 0
        self.discovers_requested = 0
        self.editor = EditorResolution(None, "", "Не найден — укажите путь в Настройках")  # noqa: RUF001
        self.workspace = EdtWorkspace(
            tmp_path / "edt.json",
            discover=lambda: list(INSTALLED),
            edtstart=lambda: None,
            editors=lambda kind: self.editor,
            spawn=self._spawn,
            activate=self._activate,
            open_file=self.opened.append,
            new_id=lambda: f"id-{next(ids)}",
        )
        self.workspace.refresh_installations()

    def _spawn(self, command: LaunchCommand) -> int:
        self.spawned.append(command)
        return 1

    def _activate(self, pid: int) -> bool:
        self.activated.append(pid)
        return True

    def _scan(self) -> None:
        self.scans_requested += 1

    def _discover(self) -> None:
        self.discovers_requested += 1

    def view(self) -> EdtView:
        return EdtView(
            self.workspace,
            palette=DARK,
            request_scan=self._scan,
            request_discover=self._discover,
            show_error=self.errors.append,
        )


@pytest.fixture
def harness(tmp_path: Path, qtbot) -> Harness:  # type: ignore[no-untyped-def]
    return Harness(tmp_path)


def _add(h: Harness, name: str, **overrides: object) -> EdtProject:
    values: dict[str, object] = {
        "id": "",
        "name": name,
        "workspace": rf"D:\edt\{name}",
        "edt_version": "2025.2.6+4",
    }
    values.update(overrides)
    return h.workspace.add_project(EdtProject(**values))  # type: ignore[arg-type]


def _select(view: EdtView, project_id: str) -> None:
    model = view.model()
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(ID_ROLE) == project_id:
            view.tree().setCurrentIndex(index)
            return
    raise AssertionError(f"нет строки {project_id}")


def test_tree_shows_projects(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    _add(harness, "a")
    _add(harness, "b")
    view = harness.view()
    qtbot.addWidget(view)
    assert view.model().rowCount() == 2


def test_search_filters_and_enter_launches_first(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    _add(harness, "Розница")
    b = _add(harness, "Опт")
    view = harness.view()
    qtbot.addWidget(view)
    view.search().setText("опт")
    assert view.model().rowCount() == 1
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert [c.arguments for c in harness.spawned] == [
        f'-data "{b.workspace}" -vm "C:\\j\\bin" --launcher.appendVmargs '
        "-vmargs -Djava.library.path="
    ]


def test_double_click_launches(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    _select(view, p.id)
    view.tree().doubleClicked.emit(view.tree().currentIndex())
    assert len(harness.spawned) == 1
    assert harness.scans_requested == 1  # подтверждающий скан после запуска


def test_launch_running_activates(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.on_scan(EdtScan(running={p.id: 77}, present={p.id: True}))
    assert view.model().item(0, 2).text() == RUNNING_GLYPH
    view.launch_id(p.id)
    assert harness.activated == [77]
    assert harness.spawned == []


def test_launch_error_is_shown_not_raised(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    p = _add(harness, "a", edt_version="2024.2.6+7")
    view = harness.view()
    qtbot.addWidget(view)
    view.launch_id(p.id)
    assert harness.errors == ["EDT 2024.2.6+7 не найден среди установок"]


def test_f5_requests_scan_and_discover(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    qtbot.keyClick(view.tree(), Qt.Key.Key_F5)
    assert harness.scans_requested == 1
    assert harness.discovers_requested == 1


def test_installations_arrival_rebuilds_version_marks(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    _add(harness, "a", edt_version="2026.1.2+2")
    view = harness.view()
    qtbot.addWidget(view)
    assert view.model().item(0, 1).toolTip() == "EDT 2026.1.2+2 не найден"
    view.on_installations(
        [EdtInstallation("2026.1.2+2", Path(r"C:\e2\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")]
    )
    assert view.model().item(0, 1).toolTip() == ""


def test_current_returns_kind_and_id(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    assert view.current() is None
    _select(view, p.id)
    assert view.current() == ("project", p.id)


def test_expansion_survives_rebuild(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    _add(harness, "a", group_id=g.id)
    view = harness.view()
    qtbot.addWidget(view)
    view.tree().collapse(view.model().index(0, 0))
    view.rebuild()
    assert view.tree().isExpanded(view.model().index(0, 0)) is False
    view.tree().expand(view.model().index(0, 0))
    view.rebuild()
    assert view.tree().isExpanded(view.model().index(0, 0)) is True
