"""Координатор раздела «EDT» (спека v3): реестр записей и групп, установки, запуск.

Калька `services/servers.py::ServersWorkspace`: всё, что трогает процессы,
диск и Win32, приходит аргументами конструктора и подменяется тестами;
каждая правка списка сразу пишется в `edt.json` (инвариант 4 — через
`edt_store.save_registry`).

Порядок записей и групп — порядок в массиве (спека §2): перестановка —
удаление из одного места и вставка в другое, без арифметики `OrderInList`.

Эта задача (Task 13) добавляет сами эффекты: установки (`refresh_installations`,
`installation_for` — точное совпадение версии, спека §2), запуск (`launch` —
активация уже запущенного окна вместо второго процесса, спека §4; отказ до
порождения процесса при не найденной версии или JDK), внешние редакторы
(`open_in_editor`, `open_folder`) и импорт из EDT Start (`import_candidates`,
`import_projects` — идемпотентно по нормализованному workspace, спека §6).
Статус записи (`status`) — производная от последнего применённого скана
(`apply_scan`) и списка установок; сам скан (`scan_edt`) — модульная функция
без состояния, зовётся из потока-демона по образцу `servers.py::scan_servers`.
"""

import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from onecstarter.domain.edt import (
    EditorResolution,
    EdtGroup,
    EdtInstallation,
    EdtProject,
    ImportCandidate,
    build_edt_command,
    effective_jvm,
    import_candidates,
    running_workspaces,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c import process, window_activate
from onecstarter.platform_1c.editors import EditorKind
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry
from onecstarter.platform_1c.process_scan import ProcessScanner
from onecstarter.services.edt_store import EdtRegistry, load_registry, save_registry
from onecstarter.services.errors import (
    EdtError,
    EdtLaunchError,
    InvalidRequestError,
    UnknownItemError,
)

__all__ = [
    "EDT_PROCESS_NAMES",
    "EdtScan",
    "EdtStatus",
    "EdtWorkspace",
    "LaunchOutcome",
    "scan_edt",
]


def _new_id() -> str:
    return uuid.uuid4().hex


EDT_PROCESS_NAMES = frozenset({"1cedt.exe"})


class LaunchOutcome(Enum):
    STARTED = "started"
    ACTIVATED = "activated"
    ACTIVATION_MISSED = "missed"  # окно не нашлось — молча (спека §4)


@dataclass(frozen=True)
class EdtScan:
    running: dict[str, int]
    present: dict[str, bool]


@dataclass(frozen=True)
class EdtStatus:
    running_pid: int | None
    workspace_present: bool | None
    installed: bool
    cli_busy: bool = False


def scan_edt(
    scanner: ProcessScanner,
    projects: Sequence[EdtProject],
    is_dir: Callable[[str], bool] = os.path.isdir,
) -> EdtScan:
    """Снимок для монитора: кто запущен и чьи каталоги на месте. Зовётся из потока-демона."""
    processes = scanner.snapshot(EDT_PROCESS_NAMES)
    running = running_workspaces(((p.pid, p.argv) for p in processes), projects)
    present = {project.id: is_dir(project.workspace) for project in projects}
    return EdtScan(running=running, present=present)


class EdtWorkspace:
    def __init__(
        self,
        path: Path,
        *,
        discover: Callable[[], list[EdtInstallation]],
        edtstart: Callable[[], EdtStartRegistry | None],
        editors: Callable[[EditorKind], EditorResolution],
        spawn: Callable[[LaunchCommand], int] = process.spawn,
        activate: Callable[[int], bool] = window_activate.activate_window,
        open_file: Callable[[str], None] = os.startfile,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self._path = path
        self._discover = discover
        self._edtstart = edtstart
        self._editors = editors
        self._spawn = spawn
        self._activate = activate
        self._open_file = open_file
        self._new_id = new_id
        registry = load_registry(path)
        self._groups: list[EdtGroup] = list(registry.groups)
        self._projects: list[EdtProject] = list(registry.projects)
        self._installations: list[EdtInstallation] = []
        self._installations_ready = False
        self._running: dict[str, int] = {}
        self._present: dict[str, bool] = {}

    # --- записи -----------------------------------------------------------

    def projects(self) -> list[EdtProject]:
        return list(self._projects)

    def project(self, project_id: str) -> EdtProject:
        for project in self._projects:
            if project.id == project_id:
                return project
        raise UnknownItemError(f"Запись EDT не найдена: {project_id}")

    def add_project(self, project: EdtProject) -> EdtProject:
        self._validate_project(project)
        if project.group_id is not None:
            self._group(project.group_id)
        stored = replace(project, id=project.id or self._new_id())
        self._projects.append(stored)
        self._save()
        return stored

    def update_project(self, project: EdtProject) -> None:
        self._validate_project(project)
        if project.group_id is not None:
            self._group(project.group_id)
        index = self._project_index(project.id)
        self._projects[index] = project
        self._save()

    def remove_project(self, project_id: str) -> None:
        del self._projects[self._project_index(project_id)]
        self._save()

    # --- группы -----------------------------------------------------------

    def groups(self) -> list[EdtGroup]:
        return list(self._groups)

    def add_group(self, name: str, parent_id: str | None) -> EdtGroup:
        if not name.strip():
            raise InvalidRequestError("Имя группы пусто")
        if parent_id is not None:
            self._group(parent_id)
        group = EdtGroup(id=self._new_id(), name=name.strip(), parent_id=parent_id)
        self._groups.append(group)
        self._save()
        return group

    def rename_group(self, group_id: str, name: str) -> None:
        if not name.strip():
            raise InvalidRequestError("Имя группы пусто")
        index = self._group_index(group_id)
        self._groups[index] = EdtGroup(
            id=group_id, name=name.strip(), parent_id=self._groups[index].parent_id
        )
        self._save()

    def remove_group(self, group_id: str) -> None:
        """Содержимое уходит к родителю (спека §7): выбора нет — записей мало."""
        removed = self._group(group_id)
        self._groups = [
            EdtGroup(id=g.id, name=g.name, parent_id=removed.parent_id)
            if g.parent_id == group_id
            else g
            for g in self._groups
            if g.id != group_id
        ]
        self._projects = [
            replace(p, group_id=removed.parent_id) if p.group_id == group_id else p
            for p in self._projects
        ]
        self._save()

    def children(self, group_id: str | None) -> tuple[list[EdtGroup], list[EdtProject]]:
        return (
            [g for g in self._groups if g.parent_id == group_id],
            [p for p in self._projects if p.group_id == group_id],
        )

    # --- перестановка -----------------------------------------------------

    def move_project(self, project_id: str, group_id: str | None, position: int) -> None:
        if group_id is not None:
            self._group(group_id)
        moving = self._projects.pop(self._project_index(project_id))
        moved = replace(moving, group_id=group_id)
        self._projects.insert(self._insert_index(self._projects, group_id, position), moved)
        self._save()

    def move_group(self, group_id: str, parent_id: str | None, position: int) -> None:
        if parent_id is not None:
            self._group(parent_id)
            if parent_id == group_id or self._is_descendant(parent_id, group_id):
                raise InvalidRequestError("Группу нельзя переместить внутрь самой себя")
        moving = self._groups.pop(self._group_index(group_id))
        moved = EdtGroup(id=moving.id, name=moving.name, parent_id=parent_id)
        self._groups.insert(self._insert_index(self._groups, parent_id, position), moved)
        self._save()

    # --- установки --------------------------------------------------------

    def set_installations(self, installations: Sequence[EdtInstallation]) -> None:
        self._installations = list(installations)
        self._installations_ready = True

    def refresh_installations(self) -> list[EdtInstallation]:
        self.set_installations(self._discover())
        return self.installations()

    def installations(self) -> list[EdtInstallation]:
        return list(self._installations)

    def installations_ready(self) -> bool:
        return self._installations_ready

    def installation_for(self, project: EdtProject) -> EdtInstallation | None:
        """Точное совпадение строки версии (спека §2) — никакой «ближайшей»."""
        for installation in self._installations:
            if installation.version == project.edt_version:
                return installation
        return None

    # --- статус -----------------------------------------------------------

    def apply_scan(self, scan: EdtScan) -> None:
        self._running = dict(scan.running)
        self._present.update(scan.present)

    def running_pid(self, project_id: str) -> int | None:
        return self._running.get(project_id)

    def status(self, project_id: str) -> EdtStatus:
        project = self.project(project_id)
        return EdtStatus(
            running_pid=self._running.get(project_id),
            workspace_present=self._present.get(project_id),
            installed=self.installation_for(project) is not None,
        )

    # --- запуск -----------------------------------------------------------

    def launch(self, project_id: str) -> LaunchOutcome:
        project = self.project(project_id)
        pid = self._running.get(project_id)
        if pid is not None:
            if self._activate(pid):
                return LaunchOutcome.ACTIVATED
            return LaunchOutcome.ACTIVATION_MISSED
        installation = self.installation_for(project)
        if installation is None:
            raise EdtLaunchError(
                f"EDT {project.edt_version or '(версия не задана)'} не найден среди установок"
            )
        jvm = effective_jvm(project, installation)
        if jvm is None:
            raise EdtLaunchError(
                f"JDK для EDT {installation.version} не найден: нужна Java "
                f"{installation.required_java}+; укажите каталог bin JDK в Настройках "
                "или в записи"
            )
        command = build_edt_command(
            installation.exe, project.workspace, jvm, installation.vm_args, project.vm_args
        )
        self._run(command)
        return LaunchOutcome.STARTED

    def editor(self, kind: EditorKind) -> EditorResolution:
        return self._editors(kind)

    def open_in_editor(self, project_id: str, kind: EditorKind) -> None:
        project = self.project(project_id)
        resolution = self._editors(kind)
        if resolution.path is None:
            raise EdtError(resolution.note)
        arguments = f'"{self._folder(project)}"'
        self._run(LaunchCommand(executable=resolution.path, arguments=arguments))

    def open_folder(self, project_id: str) -> None:
        try:
            self._open_file(self._folder(self.project(project_id)))
        except OSError as error:
            raise EdtError(f"Не удалось открыть каталог: {error}") from error  # noqa: RUF001

    # --- импорт -----------------------------------------------------------

    def edtstart_available(self) -> bool:
        return self._edtstart() is not None

    def edtstart_skipped(self) -> int:
        registry = self._edtstart()
        return registry.skipped if registry is not None else 0

    def import_candidates(self) -> list[ImportCandidate] | None:
        registry = self._edtstart()
        if registry is None:
            return None
        return import_candidates(
            registry.projects, registry.products, self._projects, self._new_id
        )

    def import_projects(self, candidates: Sequence[ImportCandidate]) -> int:
        known = {p.workspace for p in self._projects}
        added = 0
        for candidate in candidates:
            if candidate.project.workspace in known:
                continue
            self._projects.append(candidate.project)
            known.add(candidate.project.workspace)
            added += 1
        if added:
            self._save()
        return added

    # --- внутреннее -------------------------------------------------------

    @staticmethod
    def _insert_index(
        items: Sequence[EdtGroup | EdtProject], parent: str | None, position: int
    ) -> int:
        """Индекс в общем массиве, соответствующий `position` среди соседей."""
        siblings = [
            index
            for index, item in enumerate(items)
            if (item.parent_id if isinstance(item, EdtGroup) else item.group_id) == parent
        ]
        if position < len(siblings):
            return siblings[position]
        return siblings[-1] + 1 if siblings else len(items)

    def _is_descendant(self, candidate: str, ancestor: str) -> bool:
        current: str | None = candidate
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            parent = self._group(current).parent_id
            if parent == ancestor:
                return True
            current = parent
        return False

    def _validate_project(self, project: EdtProject) -> None:
        if not project.name.strip():
            raise InvalidRequestError("Имя записи пусто")
        if not project.workspace.strip():
            raise InvalidRequestError("Путь workspace пуст")
        if not Path(project.workspace).is_absolute():
            raise InvalidRequestError("Путь workspace должен быть абсолютным")

    def _project_index(self, project_id: str) -> int:
        for index, project in enumerate(self._projects):
            if project.id == project_id:
                return index
        raise UnknownItemError(f"Запись EDT не найдена: {project_id}")

    def _group_index(self, group_id: str) -> int:
        for index, group in enumerate(self._groups):
            if group.id == group_id:
                return index
        raise UnknownItemError(f"Группа не найдена: {group_id}")

    def _group(self, group_id: str) -> EdtGroup:
        return self._groups[self._group_index(group_id)]

    def _save(self) -> None:
        save_registry(self._path, EdtRegistry(tuple(self._groups), tuple(self._projects)))

    @staticmethod
    def _folder(project: EdtProject) -> str:
        return project.project_dir or project.workspace

    def _run(self, command: LaunchCommand) -> None:
        try:
            self._spawn(command)
        except OSError as error:
            message = f"Не удалось запустить: {command.executable} ({error})"  # noqa: RUF001
            raise EdtLaunchError(message) from error
