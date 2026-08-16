"""Наши данные о базах: избранное и история запусков.

Файл лежит в %APPDATA%\\OneCStarter\\bases.json и принадлежит только этому
слою. В ibases.v8i свои ключи не пишем — привязка идёт ключом из model.
Время хранится в UTC; в локальное переводит слой представления.

Испорченное содержимое (не парсится как JSON, неизвестная схема) не чинится
и не затирается: файл уезжает в <имя>.bad, а работа продолжается с пустыми
данными. Недоступный файл (блокировка, права, отвалившийся сетевой диск) —
другой случай: это не порча содержимого, и подменять его пустыми данными
нельзя, иначе первое же сохранение затрёт живую историю без следа. Такой
случай — это `UserDataUnavailableError`, а не пустой результат.
"""  # noqa: RUF002

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.services.errors import InvalidRequestError, UserDataUnavailableError

SCHEMA_VERSION = 1

__all__ = [
    "SCHEMA_VERSION",
    "BaseUserData",
    "InvalidRequestError",
    "UserDataUnavailableError",
    "load_user_data",
    "record_launch",
    "rekey",
    "save_user_data",
    "set_favorite",
]


@dataclass(frozen=True)
class BaseUserData:
    favorite: bool = False
    last_launched_at: datetime | None = None
    launch_count: int = 0
    last_client: str | None = None


def load_user_data(path: Path) -> dict[str, BaseUserData]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        # Файл есть, но недоступен: блокировка, права, отвалившийся сетевой
        # диск. Это не порча содержимого, и подменять его пустыми данными  # noqa: RUF003
        # нельзя — следующее сохранение затрёт историю пользователя.
        raise UserDataUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
        entries = payload["entries"]
        if not isinstance(entries, dict):
            raise ValueError("entries не объект")
        return {str(key): _decode(value) for key, value in entries.items()}
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_user_data(path: Path, entries: Mapping[str, BaseUserData]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "entries": {key: _encode(value) for key, value in entries.items()},
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, text.encode("utf-8"))


def record_launch(
    entries: Mapping[str, BaseUserData], key: str, client: str, when: datetime
) -> dict[str, BaseUserData]:
    if when.tzinfo is None:
        # Тип из иерархии слоя, а не голый ValueError: исключение достижимо  # noqa: RUF003
        # из Workspace.launch, причём уже после порождения процесса, и UI
        # обязан отличить его от случайной ошибки в чужом коде.  # noqa: RUF003
        raise InvalidRequestError(
            "Время запуска должно быть с часовым поясом, ожидается UTC"  # noqa: RUF001
        )
    current = entries.get(key, BaseUserData())
    updated = replace(
        current,
        last_launched_at=when.astimezone(UTC),
        launch_count=current.launch_count + 1,
        last_client=client,
    )
    return {**entries, key: updated}


def set_favorite(
    entries: Mapping[str, BaseUserData], key: str, value: bool
) -> dict[str, BaseUserData]:
    current = entries.get(key, BaseUserData())
    return {**entries, key: replace(current, favorite=value)}


def rekey(
    entries: Mapping[str, BaseUserData], old_key: str, new_key: str
) -> dict[str, BaseUserData]:
    if old_key not in entries:
        return dict(entries)
    moved = dict(entries)
    moved[new_key] = moved.pop(old_key)
    return moved


def _move_aside(path: Path) -> dict[str, BaseUserData]:
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError as error:
        # Не сумев убрать испорченный файл, продолжать с пустыми данными  # noqa: RUF003
        # нельзя: первое же сохранение затрёт то, что пользователь мог бы
        # из него достать.
        raise UserDataUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"  # noqa: RUF001
        ) from error
    return {}


def _encode(data: BaseUserData) -> dict[str, Any]:
    stamp = data.last_launched_at
    return {
        "favorite": data.favorite,
        "last_launched_at": (
            stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None
        ),
        "launch_count": data.launch_count,
        "last_client": data.last_client,
    }


def _decode(value: Any) -> BaseUserData:
    if not isinstance(value, dict):
        raise ValueError("запись не объект")
    stamp = value.get("last_launched_at")
    return BaseUserData(
        favorite=bool(value.get("favorite", False)),
        last_launched_at=datetime.fromisoformat(stamp) if stamp else None,
        launch_count=int(value.get("launch_count", 0)),
        last_client=value.get("last_client"),
    )
