"""Хранилище раздела «EDT» — `%APPDATA%\\OneCStarter\\edt.json` (спека v3, §2).

Файл наш: формат не согласуется ни с кем, неизвестные ключи не сохраняются.
Политика повреждённого файла — та же, что у `server_store.py`: перенос в `.bad`
с пустым списком дальше; не сумели перенести — `EdtUnavailableError`, потому что
первое же сохранение затёрло бы то, что пользователь мог бы достать из файла.
"""  # noqa: RUF002

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.edt import EdtGroup, EdtProject
from onecstarter.services.errors import EdtUnavailableError

__all__ = ["SCHEMA_VERSION", "EdtRegistry", "load_registry", "save_registry"]

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EdtRegistry:
    groups: tuple[EdtGroup, ...]
    projects: tuple[EdtProject, ...]


def load_registry(path: Path) -> EdtRegistry:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return EdtRegistry((), ())
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        # Файл есть, но недоступен: блокировка, права, отвалившийся диск. Это
        # не порча содержимого — в `.bad` его не уносим и пустым не подменяем:  # noqa: RUF003
        # следующее сохранение затёрло бы записи пользователя (как в server_store).
        raise EdtUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
        groups = payload.get("groups", [])
        projects = payload.get("projects", [])
        if not isinstance(groups, list) or not isinstance(projects, list):
            raise ValueError("groups/projects не списки")
        return EdtRegistry(
            tuple(_decode_group(entry) for entry in groups),
            tuple(_decode_project(entry) for entry in projects),
        )
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_registry(path: Path, registry: EdtRegistry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "groups": [_encode_group(group) for group in registry.groups],
        "projects": [_encode_project(project) for project in registry.projects],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write(path, text.encode("utf-8"))


def _move_aside(path: Path) -> EdtRegistry:
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError as error:
        raise EdtUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"  # noqa: RUF001
        ) from error
    return EdtRegistry((), ())


def _encode_group(group: EdtGroup) -> dict[str, Any]:
    return {"id": group.id, "name": group.name, "parent_id": group.parent_id}


def _decode_group(value: Any) -> EdtGroup:
    if not isinstance(value, dict):
        raise ValueError("группа не объект")
    parent = value.get("parent_id")
    return EdtGroup(
        id=str(value["id"]),
        name=str(value["name"]),
        parent_id=str(parent) if isinstance(parent, str) else None,
    )


def _encode_project(project: EdtProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "workspace": project.workspace,
        "project_dir": project.project_dir,
        "edt_version": project.edt_version,
        "jvm_dir": project.jvm_dir,
        "vm_args": project.vm_args,
        "group_id": project.group_id,
    }


def _decode_project(value: Any) -> EdtProject:
    if not isinstance(value, dict):
        raise ValueError("запись не объект")
    group = value.get("group_id")
    return EdtProject(
        id=str(value["id"]),
        name=str(value["name"]),
        workspace=str(value["workspace"]),
        project_dir=str(value.get("project_dir", "")),
        edt_version=str(value.get("edt_version", "")),
        jvm_dir=str(value.get("jvm_dir", "")),
        vm_args=str(value.get("vm_args", "")),
        group_id=str(group) if isinstance(group, str) else None,
    )
