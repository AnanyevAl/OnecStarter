"""EdtView: дерево, фильтр, запуск по Enter/двойному клику, статус, F5 (спека §7)."""

from itertools import count
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from onecstarter.domain.edt import (
    EditorResolution,
    EdtInstallation,
    EdtProject,
    EdtStartProduct,
    EdtStartProject,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.editors import EditorKind
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.ui.edt.tree_model import ID_ROLE, KIND_GROUP, KIND_ROLE
from onecstarter.ui.edt.view import (
    MENU_ADD,
    MENU_ADD_GROUP,
    MENU_EDIT,
    MENU_IMPORT,
    MENU_OPEN_EDT,
    MENU_OPEN_EXPLORER,
    MENU_REMOVE,
    MENU_REMOVE_GROUP,
    MENU_RENAME_GROUP,
    DropTarget,
    EdtView,
)
from onecstarter.ui.theme import DARK

INSTALLED = [
    EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")
]
PRODUCT = EdtStartProduct("prod", "2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), ())
ES = EdtStartProject("es", "(2025) А", Path(r"D:\edt\a"), "prod", ("-Xmx8192m",), None)  # noqa: RUF001


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        ids = count(1)
        self.spawned: list[LaunchCommand] = []
        self.activated: list[int] = []
        self.opened: list[str] = []
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.registry: EdtStartRegistry | None = None
        self.scans_requested = 0
        self.discovers_requested = 0
        self.editor = EditorResolution(None, "", "Не найден — укажите путь в Настройках")  # noqa: RUF001
        self.workspace = EdtWorkspace(
            tmp_path / "edt.json",
            discover=lambda: list(INSTALLED),
            edtstart=lambda: self.registry,
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
            show_info=self.infos.append,
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


def test_name_column_draws_decoration_on_the_right(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

    _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    delegate = view.tree().itemDelegateForColumn(0)
    assert isinstance(delegate, QStyledItemDelegate)
    option = QStyleOptionViewItem()
    delegate.initStyleOption(option, view.model().index(0, 0))
    assert option.decorationPosition == QStyleOptionViewItem.Position.Right


def test_launch_running_activates(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.on_scan(EdtScan(running={p.id: 77}, present={p.id: True}))
    assert not view.model().item(0, 0).icon().isNull()
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


def test_unchanged_scan_does_not_rebuild(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    """I2 финального ревью: тик монитора с тем же снимком не перестраивает модель.

    `rebuild()` подменяет модель целиком — сбрасывает текущую строку, ширины
    колонок и рвёт начатое перетаскивание; делать это каждые 5 секунд без
    изменений нельзя. Равный снимок (новый экземпляр с тем же содержимым)
    применяется к координатору, но модель остаётся прежней; изменившийся —
    перестраивает.
    """  # noqa: RUF002
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.on_scan(EdtScan(running={p.id: 5}, present={p.id: True}))
    model_after_first = view.model()
    assert not model_after_first.item(0, 0).icon().isNull()
    view.on_scan(EdtScan(running={p.id: 5}, present={p.id: True}))
    assert view.model() is model_after_first
    view.on_scan(EdtScan(running={}, present={p.id: True}))
    assert view.model() is not model_after_first
    assert view.model().item(0, 0).icon().isNull()


def test_current_row_and_widths_survive_rebuild(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    """I2 финального ревью: перестройка возвращает текущую строку и ширины колонок."""
    _add(harness, "a")
    b = _add(harness, "b")
    view = harness.view()
    qtbot.addWidget(view)
    assert (view.tree().columnWidth(0), view.tree().columnWidth(1)) == (320, 110)  # умолчания
    _select(view, b.id)
    view.tree().setColumnWidth(0, 200)
    view.tree().setColumnWidth(1, 90)
    view.rebuild()
    assert view.current() == ("project", b.id)
    assert (view.tree().columnWidth(0), view.tree().columnWidth(1)) == (200, 90)


def test_version_column_keeps_width_in_shown_window(harness: Harness, qtbot, qapp) -> None:  # type: ignore[no-untyped-def]
    """Ревью Task 21: с двумя колонками «EDT» стала последней и наследует

    штатное растяжение Qt (`stretchLastSection=True`) — в показанном окне
    версия раздувается на всю оставшуюся ширину, а ручная `setColumnWidth`
    молча игнорируется. `qtbot.addWidget()` без `show()`/`resize()` раскладку
    не делает и это не ловит — нужна настоящая геометрия.
    """  # noqa: RUF002
    _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.show()
    view.resize(1000, 600)
    qapp.processEvents()
    assert view.tree().columnWidth(1) == 110
    view.tree().setColumnWidth(1, 90)
    view.rebuild()
    qapp.processEvents()
    assert view.tree().columnWidth(1) == 90


def test_collapse_survives_empty_filter_round_trip(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    """Фильтр без совпадений опустошает модель; сброс фильтра не должен раскрывать свёрнутое."""  # noqa: RUF002
    g = harness.workspace.add_group("2025", None)
    _add(harness, "a", group_id=g.id)
    view = harness.view()
    qtbot.addWidget(view)
    view.tree().collapse(view.model().index(0, 0))
    view.search().setText("нет такого")
    assert view.model().rowCount() == 0
    view.search().setText("")
    assert view.tree().isExpanded(view.model().index(0, 0)) is False


def _actions(menu: QMenu) -> dict[str, bool]:
    return {a.text(): a.isEnabled() for a in menu.actions() if not a.isSeparator()}


def test_project_menu_items_and_editor_state(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    actions = _actions(view.build_menu("project", p.id))
    assert actions[MENU_OPEN_EDT] is True
    assert actions["Открыть в VS Code"] is False  # редактор не найден
    assert actions["Открыть в Antigravity"] is False
    assert actions[MENU_OPEN_EXPLORER] is True
    assert {MENU_ADD, MENU_EDIT, MENU_REMOVE, MENU_ADD_GROUP, MENU_IMPORT} <= actions.keys()
    tooltips = {a.text(): a.toolTip() for a in view.build_menu("project", p.id).actions()}
    assert tooltips["Открыть в VS Code"] == "Не найден — укажите путь в Настройках"  # noqa: RUF001


def test_project_menu_open_edt_disabled_when_not_installed(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    p = _add(harness, "a", edt_version="2024.2.6+7")
    view = harness.view()
    qtbot.addWidget(view)
    menu = view.build_menu("project", p.id)
    action = next(a for a in menu.actions() if a.text() == MENU_OPEN_EDT)
    assert action.isEnabled() is False
    assert action.toolTip() == "EDT 2024.2.6+7 не найден"


def test_editor_enabled_when_found_and_opens_folder(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    harness.editor = EditorResolution(Path(r"C:\code\code.cmd"), "PATH", "")
    p = _add(harness, "a", project_dir=r"D:\edt\a\proj")
    view = harness.view()
    qtbot.addWidget(view)
    assert _actions(view.build_menu("project", p.id))["Открыть в VS Code"] is True
    view.open_in_editor(p.id, EditorKind.VSCODE)
    assert harness.spawned[-1].arguments == '"D:\\edt\\a\\proj"'
    view.open_folder(p.id)
    assert harness.opened == [r"D:\edt\a\proj"]


def test_group_and_empty_menus(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    view = harness.view()
    qtbot.addWidget(view)
    group_actions = _actions(view.build_menu("group", g.id))
    assert {MENU_ADD, MENU_ADD_GROUP, MENU_RENAME_GROUP, MENU_REMOVE_GROUP} <= group_actions.keys()
    assert MENU_OPEN_EDT not in group_actions
    empty_actions = _actions(view.build_menu(None, None))
    assert set(empty_actions) == {MENU_ADD, MENU_ADD_GROUP, MENU_IMPORT}


def test_add_project_via_dialog(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    view = harness.view()
    qtbot.addWidget(view)

    def fake_exec(dialog):
        dialog.name_edit().setText("Новая")
        dialog.workspace_edit().setText(r"D:\edt\new")
        return True

    monkeypatch.setattr(view, "_run_dialog", fake_exec)
    view.add_project(g.id)
    [project] = harness.workspace.projects()
    assert project.name == "Новая"
    assert project.group_id == g.id
    assert project.vm_args == "-Xmx8192m"  # умолчание из dialog_defaults


def test_edit_and_remove_project(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)

    def rename(dialog):
        dialog.name_edit().setText("b")
        return True

    monkeypatch.setattr(view, "_run_dialog", rename)
    view.edit_project(p.id)
    assert harness.workspace.project(p.id).name == "b"
    confirmed: list[str] = []

    def confirm(parent: object, title: str, text: str) -> bool:
        confirmed.append(text)
        return True

    monkeypatch.setattr(view, "_confirm", confirm)
    view.remove_project(p.id)
    assert harness.workspace.projects() == []
    assert confirmed == ["Удалить запись «b»? Каталоги на диске не трогаются."]


def test_remove_declined_keeps_project(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: False)
    view.remove_project(p.id)
    assert len(harness.workspace.projects()) == 1


def test_group_lifecycle_via_view(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    view = harness.view()
    qtbot.addWidget(view)
    names = iter(["2025", "Опт"])

    def name_dialog(dialog):
        dialog.name_edit().setText(next(names))
        return True

    monkeypatch.setattr(view, "_run_dialog", name_dialog)
    view.add_group(None)
    [g] = harness.workspace.groups()
    assert g.name == "2025"
    # C1 финального ревью: пустая группа обязана быть видна сразу после создания.
    assert view.model().rowCount() == 1
    assert view.model().item(0, 0).data(KIND_ROLE) == KIND_GROUP
    assert view.model().item(0, 0).data(ID_ROLE) == g.id
    view.rename_group(g.id)
    assert harness.workspace.groups()[0].name == "Опт"
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    view.remove_group(g.id)
    assert harness.workspace.groups() == []


def test_handle_drop_moves_project_into_group_and_reorders(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    g = harness.workspace.add_group("2025", None)
    a = _add(harness, "a")
    b = _add(harness, "b")
    view = harness.view()
    qtbot.addWidget(view)
    view.handle_drop(("project", a.id), ("group", g.id), DropTarget.INTO)
    assert harness.workspace.project(a.id).group_id == g.id
    view.handle_drop(("project", a.id), ("project", b.id), DropTarget.BEFORE)
    assert [p.id for p in harness.workspace.children(None)[1]] == [a.id, b.id]
    view.handle_drop(("project", a.id), ("project", b.id), DropTarget.AFTER)
    assert [p.id for p in harness.workspace.children(None)[1]] == [b.id, a.id]
    view.handle_drop(("project", a.id), None, DropTarget.INTO)
    assert harness.workspace.project(a.id).group_id is None


def test_handle_drop_group_into_descendant_shows_error(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    root = harness.workspace.add_group("root", None)
    child = harness.workspace.add_group("child", root.id)
    view = harness.view()
    qtbot.addWidget(view)
    view.handle_drop(("group", root.id), ("group", child.id), DropTarget.INTO)
    assert harness.errors == ["Группу нельзя переместить внутрь самой себя"]


def test_directory_drop_opens_prefilled_dialog(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    view = harness.view()
    qtbot.addWidget(view)
    seen: list[tuple[str, str]] = []

    def capture(dialog):
        seen.append((dialog.workspace_edit().text(), dialog.name_edit().text()))
        return False

    monkeypatch.setattr(view, "_run_dialog", capture)
    view.add_project_from_directory(r"D:\edt\dropped", ("group", g.id))
    assert seen == [(r"D:\edt\dropped", "dropped")]
    assert harness.workspace.projects() == []


def test_delete_key_removes_current_with_confirm(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    _select(view, p.id)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    qtbot.keyClick(view.tree(), Qt.Key.Key_Delete)
    assert harness.workspace.projects() == []


def test_banner_only_when_empty_and_registry_present(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    view = harness.view()
    qtbot.addWidget(view)
    assert view.banner().isHidden() is True
    harness.registry = EdtStartRegistry((PRODUCT,), (ES,), 0)
    view.rebuild()
    assert view.banner().isHidden() is False
    _add(harness, "a")
    view.rebuild()
    assert view.banner().isHidden() is True


def test_import_adds_selected(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    harness.registry = EdtStartRegistry((PRODUCT,), (ES,), 0)
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_run_dialog", lambda dialog: True)
    view.import_from_edtstart()
    [project] = harness.workspace.projects()
    assert project.workspace == r"D:\edt\a"
    assert project.edt_version == "2025.2.6+4"
    assert harness.infos == ["Импортировано записей: 1"]


def test_import_without_registry_shows_error(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    view = harness.view()
    qtbot.addWidget(view)
    view.import_from_edtstart()
    expected = "EDT Start не найден: реестр %LOCALAPPDATA%\\1C\\1cedtstart не читается"
    assert harness.errors == [expected]


def test_import_nothing_new_shows_info(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    harness.registry = EdtStartRegistry((PRODUCT,), (ES,), 0)
    _add(harness, "a", workspace=r"D:\edt\a")
    view = harness.view()
    qtbot.addWidget(view)
    view.import_from_edtstart()
    assert harness.infos == ["Новых проектов в EDT Start нет"]
