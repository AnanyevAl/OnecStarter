"""Координатор раздела EDT: записи, группы, порядок (спека §2), сохранение после каждой правки."""

from dataclasses import dataclass, field, replace
from itertools import count
from pathlib import Path

import pytest

from onecstarter.domain.edt import (
    EditorResolution,
    EdtInstallation,
    EdtProject,
    EdtStartProduct,
    EdtStartProject,
    ImportCandidate,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.editors import EditorKind
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.edt import (
    EdtNotes,
    EdtScan,
    EdtWorkspace,
    LaunchOutcome,
    scan_edt,
    settings_notes,
)
from onecstarter.services.edt_store import load_registry
from onecstarter.services.errors import (
    EdtError,
    EdtLaunchError,
    InvalidRequestError,
    UnknownItemError,
)


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


JDK = Path(r"C:\jdk\bin")
EXE_2025 = Path(r"C:\edt\1c-edt-2025.2.6+4-x86_64\1cedt.exe")
INSTALLED = [
    EdtInstallation("2025.2.6+4", EXE_2025, JDK, "-Xmx8192m -Dx=1", 17, "products.json"),
]


@dataclass
class Harness:
    workspace: EdtWorkspace
    spawned: list[LaunchCommand] = field(default_factory=list)
    activated: list[int] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)


def _harness(
    tmp_path: Path,
    *,
    installed: list[EdtInstallation] | None = None,
    edtstart: EdtStartRegistry | None = None,
    editor: EditorResolution | None = None,
    activate_result: bool = True,
    spawn_error: bool = False,
) -> Harness:
    harness = Harness(workspace=None)  # type: ignore[arg-type]
    ids = count(1)

    def spawn(command: LaunchCommand) -> int:
        if spawn_error:
            raise OSError("нет файла")
        harness.spawned.append(command)
        return 500

    def activate(pid: int) -> bool:
        harness.activated.append(pid)
        return activate_result

    harness.workspace = EdtWorkspace(
        tmp_path / "edt.json",
        discover=lambda: list(installed or []),
        edtstart=lambda: edtstart,
        editors=lambda kind: editor
        or EditorResolution(None, "", "Не найден — укажите путь в Настройках"),  # noqa: RUF001
        spawn=spawn,
        activate=activate,
        open_file=harness.opened.append,
        new_id=lambda: f"id-{next(ids)}",
    )
    return harness


def _proc(pid: int, workspace: str) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name="1cedt.exe",
        executable=EXE_2025,
        argv=(str(EXE_2025), "-data", workspace, "-vm", str(JDK)),
    )


class FakeScanner:
    def __init__(self, processes: list[ProcessInfo]) -> None:
        self._processes = processes
        self.names: list[frozenset[str]] = []

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        self.names.append(names)
        return list(self._processes)


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

    def test_update_with_unknown_group_raises_and_keeps_record(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        added = ws.add_project(_project("a"))
        with pytest.raises(UnknownItemError):
            ws.update_project(
                EdtProject(id=added.id, name="a", workspace=added.workspace, group_id="ghost")
            )
        assert ws.project(added.id).group_id is None
        assert [p.id for p in ws.children(None)[1]] == [added.id]


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


class TestScan:
    def test_scan_edt_maps_running_and_presence(self, tmp_path: Path) -> None:
        present = tmp_path / "ws"
        present.mkdir()
        projects = [
            EdtProject(id="p1", name="a", workspace=str(present)),
            EdtProject(id="p2", name="b", workspace=str(tmp_path / "gone")),
        ]
        scanner = FakeScanner([_proc(77, str(present))])
        scan = scan_edt(scanner, projects)
        assert scan == EdtScan(running={"p1": 77}, present={"p1": True, "p2": False})
        assert scanner.names == [frozenset({"1cedt.exe"})]

    def test_status_before_and_after_scan(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        before = h.workspace.status(p.id)
        assert before.running_pid is None
        assert before.workspace_present is None
        assert before.installed is True
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={p.id: False}))
        after = h.workspace.status(p.id)
        assert after.running_pid == 9
        assert after.workspace_present is False

    def test_status_not_installed(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2024.2.6+7"))
        assert h.workspace.status(p.id).installed is False


class TestLaunch:
    def test_started_with_full_command(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4", vm_args="-Xmx4g"))
        assert h.workspace.launch(p.id) is LaunchOutcome.STARTED
        [command] = h.spawned
        assert command.executable == EXE_2025
        assert command.arguments == (
            f'-data "{p.workspace}" -vm "{JDK}" --launcher.appendVmargs '
            "-vmargs -Xmx8192m -Dx=1 -Djava.library.path= -Xmx4g"
        )

    def test_project_jvm_override(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(
            _project("a", edt_version="2025.2.6+4", jvm_dir=r"D:\my\bin")
        )
        h.workspace.launch(p.id)
        assert '-vm "D:\\my\\bin"' in h.spawned[0].arguments

    def test_running_activates_instead_of_spawn(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={}))
        assert h.workspace.launch(p.id) is LaunchOutcome.ACTIVATED
        assert h.activated == [9]
        assert h.spawned == []

    def test_activation_missed_is_silent_outcome(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED, activate_result=False)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={}))
        assert h.workspace.launch(p.id) is LaunchOutcome.ACTIVATION_MISSED
        assert h.spawned == []

    def test_version_not_installed_refuses(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2024.2.6+7"))
        with pytest.raises(EdtLaunchError, match=r"EDT 2024.2.6\+7 не найден"):
            h.workspace.launch(p.id)
        assert h.spawned == []

    def test_no_jvm_refuses_before_spawn(self, tmp_path: Path) -> None:
        no_jvm = [EdtInstallation("2025.2.6+4", EXE_2025, None, "", 17, "")]
        h = _harness(tmp_path, installed=no_jvm)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        with pytest.raises(EdtLaunchError, match="JDK"):
            h.workspace.launch(p.id)
        assert h.spawned == []

    def test_spawn_oserror_becomes_launch_error(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED, spawn_error=True)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        with pytest.raises(EdtLaunchError):
            h.workspace.launch(p.id)


class TestEditorsAndExplorer:
    def test_opens_project_dir_in_editor(self, tmp_path: Path) -> None:
        code = Path(r"C:\code\code.cmd")
        h = _harness(tmp_path, editor=EditorResolution(code, "PATH", ""))
        p = h.workspace.add_project(_project("a", project_dir=r"D:\edt\a\proj"))
        h.workspace.open_in_editor(p.id, EditorKind.VSCODE)
        [command] = h.spawned
        assert command.executable == code
        assert command.arguments == '"D:\\edt\\a\\proj"'

    def test_empty_project_dir_opens_workspace(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, editor=EditorResolution(Path(r"C:\code\code.cmd"), "PATH", ""))
        p = h.workspace.add_project(_project("a"))
        h.workspace.open_in_editor(p.id, EditorKind.VSCODE)
        assert h.spawned[0].arguments == f'"{p.workspace}"'

    def test_missing_editor_refuses(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        p = h.workspace.add_project(_project("a"))
        with pytest.raises(EdtError, match="Не найден"):  # noqa: RUF001
            h.workspace.open_in_editor(p.id, EditorKind.ANTIGRAVITY)
        assert h.spawned == []

    def test_open_folder_uses_startfile(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        p = h.workspace.add_project(_project("a", project_dir=r"D:\edt\a\proj"))
        h.workspace.open_folder(p.id)
        assert h.opened == [r"D:\edt\a\proj"]

    def test_open_path_uses_startfile_and_wraps_oserror(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        h.workspace.open_path(r"D:\out\validate.tsv")
        assert h.opened == [r"D:\out\validate.tsv"]

        def refuse(path: str) -> None:
            raise OSError("нет ассоциации")

        h.workspace._open_file = refuse
        with pytest.raises(EdtError, match="Не удалось открыть: нет ассоциации"):  # noqa: RUF001
            h.workspace.open_path(r"D:\out\validate.tsv")


PRODUCT = EdtStartProduct("prod", "2025.2.6+4", EXE_2025, JDK, ("-Xmx8192m",))
ES_PROJECT = EdtStartProject(
    "es", "(2025) А", Path(r"D:\edt\2025\a"), "prod", ("-Xmx8192m",), None  # noqa: RUF001
)


class TestImport:
    def test_candidates_none_without_registry(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        assert h.workspace.import_candidates() is None
        assert h.workspace.edtstart_available() is False

    def test_import_adds_selected_and_is_idempotent(self, tmp_path: Path) -> None:
        registry = EdtStartRegistry((PRODUCT,), (ES_PROJECT,), 0)
        h = _harness(tmp_path, edtstart=registry)
        candidates = h.workspace.import_candidates()
        assert candidates is not None and len(candidates) == 1
        assert h.workspace.import_projects(candidates) == 1
        assert h.workspace.projects()[0].workspace == r"D:\edt\2025\a"
        assert h.workspace.import_candidates() == []

    def test_import_nothing_selected(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, edtstart=EdtStartRegistry((PRODUCT,), (ES_PROJECT,), 0))
        assert h.workspace.import_projects([]) == 0
        assert h.workspace.projects() == []

    def test_import_skips_workspace_present_by_key(self, tmp_path: Path) -> None:
        """Минор финального ревью: `import_projects` сравнивает по `workspace_key`.

        `import_candidates` нормализует путь (регистр, разделители, хвостовой
        слеш), а `import_projects` сравнивал сырые строки — кандидат, собранный
        не через `import_candidates` (или файл, где путь записан иначе),
        давал дубликат записи.
        """  # noqa: RUF002
        h = _harness(tmp_path)
        h.workspace.add_project(_project("a", workspace=r"d:/EDT/2025/A/"))
        candidates = [
            ImportCandidate(EdtProject(id="x1", name="A", workspace=r"D:\edt\2025\a"), True),
            ImportCandidate(EdtProject(id="x2", name="B", workspace="D:\\edt\\2025\\b\\"), True),
            ImportCandidate(EdtProject(id="x3", name="B2", workspace=r"d:/edt/2025/B"), True),
        ]
        assert h.workspace.import_projects(candidates) == 1
        assert [p.workspace for p in h.workspace.projects()] == [
            r"d:/EDT/2025/A/",
            "D:\\edt\\2025\\b\\",
        ]


class TestSettingsNotes:
    def test_empty_jvm_explains_auto(self) -> None:
        notes: EdtNotes = settings_notes(
            "", lambda kind: EditorResolution(None, "", "x"), lambda p: None
        )
        assert notes.jvm == (
            "Не задан — JDK подбирается из products.json, 1cedt.ini или соседних JDK"  # noqa: RUF001
        )

    def test_jvm_with_release(self) -> None:
        notes = settings_notes(
            r"C:\jdk\bin", lambda kind: EditorResolution(None, "", "x"), lambda p: "17.0.16"
        )
        assert notes.jvm == "Java 17.0.16"

    def test_jvm_without_release(self) -> None:
        notes = settings_notes(
            r"C:\nope\bin", lambda kind: EditorResolution(None, "", "x"), lambda p: None
        )
        assert notes.jvm == "Файл release не найден: версия неизвестна"

    def test_editor_notes(self) -> None:
        def editors(kind: EditorKind) -> EditorResolution:
            if kind is EditorKind.VSCODE:
                return EditorResolution(Path(r"C:\code\code.cmd"), "PATH", "")
            return EditorResolution(None, "", "Не найден — укажите путь в Настройках")  # noqa: RUF001

        notes = settings_notes("", editors, lambda p: None)
        assert notes.vscode == r"Найден: C:\code\code.cmd"
        assert notes.antigravity == "Не найден — укажите путь в Настройках"  # noqa: RUF001


class TestCliBusy:
    def test_status_reflects_busy(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        assert h.workspace.status(p.id).cli_busy is False
        h.workspace.mark_cli_busy(p.id)
        assert h.workspace.status(p.id).cli_busy is True
        assert h.workspace.cli_busy(p.id) is True
        h.workspace.clear_cli_busy(p.id)
        assert h.workspace.status(p.id).cli_busy is False

    def test_launch_refused_while_busy(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.mark_cli_busy(p.id)
        with pytest.raises(EdtLaunchError, match="занят командой CLI"):
            h.workspace.launch(p.id)
        assert h.spawned == []

    def test_remove_refused_while_busy(self, tmp_path: Path) -> None:
        """Удаление записи с живой командой (M6 ревью): запись — ключ `EdtCli._runs`
        и журнала, без неё некому принять код завершения. Правка разрешена
        (`update_project`) — командная строка уже собрана. Мутация: убрать проверку
        `_cli_busy` в `remove_project` — тест падает `DID NOT RAISE`.
        """  # noqa: RUF002
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.mark_cli_busy(p.id)
        with pytest.raises(InvalidRequestError, match="Команда CLI выполняется"):
            h.workspace.remove_project(p.id)
        assert [x.id for x in h.workspace.projects()] == [p.id]
        assert [x.id for x in load_registry(tmp_path / "edt.json").projects] == [p.id]
        h.workspace.update_project(replace(p, name="b"))  # правка — можно
        assert h.workspace.project(p.id).name == "b"
        h.workspace.clear_cli_busy(p.id)
        h.workspace.remove_project(p.id)
        assert h.workspace.projects() == []
