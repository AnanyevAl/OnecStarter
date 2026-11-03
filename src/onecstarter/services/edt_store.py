"""Хранилище раздела «EDT» — `%APPDATA%\\OneCStarter\\edt.json` (спека v3, §2).

Файл наш: формат не согласуется ни с кем, неизвестные ключи не сохраняются.
Политика повреждённого файла — та же, что у `server_store.py`: перенос в `.bad`
с пустым списком дальше; не сумели перенести — `EdtUnavailableError`, потому что
первое же сохранение затёрло бы то, что пользователь мог бы достать из файла.

`launches` (T-37) — время последнего открытия EDT по id записи. Отдельно от `EdtProject`:
диалог свойств пересобирает запись целиком и стёр бы его. Негодная пара отбрасывается
поштучно — статистика не стоит записей пользователя, `.bad` из-за неё не бывает.
"""  # noqa: RUF002

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    launches: dict[str, datetime] = field(default_factory=dict)


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
        decoded_groups = tuple(_decode_group(entry) for entry in groups)
        decoded_projects = tuple(_decode_project(entry) for entry in projects)
        known = {project.id for project in decoded_projects}
        return EdtRegistry(
            decoded_groups, decoded_projects, _decode_launches(payload.get("launches"), known)
        )
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_registry(path: Path, registry: EdtRegistry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "groups": [_encode_group(group) for group in registry.groups],
        "projects": [_encode_project(project) for project in registry.projects],
        "launches": {
            project_id: stamp.astimezone(UTC).isoformat()
            for project_id, stamp in registry.launches.items()
        },
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


def _decode_launches(value: Any, known: set[str]) -> dict[str, datetime]:
    """Время запусков (T-37): поштучно, без `.bad`; чужой id и время без пояса — мимо."""
    if not isinstance(value, dict):
        return {}
    launches: dict[str, datetime] = {}
    for project_id, stamp in value.items():
        if project_id not in known or not isinstance(stamp, str):
            continue
        try:
            parsed = datetime.fromisoformat(stamp)
            if parsed.tzinfo is None:
                continue
            # Крайние значения (0001-01-01+05:00, 9999-12-31-05:00) не переводятся в UTC и
            # в местное время: OverflowError здесь — такая же негодная пара, как ValueError.
            moment = parsed.astimezone(UTC)
            moment.astimezone()
        except (ValueError, OverflowError):
            continue
        launches[project_id] = moment
    return launches
