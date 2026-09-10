"""Координатор раздела «EDT» (спека v3): реестр записей и групп, установки, запуск.

Калька `services/servers.py::ServersWorkspace`: всё, что трогает процессы,
диск и Win32, приходит аргументами конструктора и подменяется тестами;
каждая правка списка сразу пишется в `edt.json` (инвариант 4 — через
`edt_store.save_registry`).

Порядок записей и групп — порядок в массиве (спека §2): перестановка —
удаление из одного места и вставка в другое, без арифметики `OrderInList`.
"""

import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from onecstarter.domain.edt import (
    EditorResolution,
    EdtGroup,
    EdtInstallation,
    EdtProject,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c import process, window_activate
from onecstarter.platform_1c.editors import EditorKind
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry
from onecstarter.services.edt_store import EdtRegistry, load_registry, save_registry
from onecstarter.services.errors import InvalidRequestError, UnknownItemError

__all__ = ["EdtWorkspace"]


def _new_id() -> str:
    return uuid.uuid4().hex


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
