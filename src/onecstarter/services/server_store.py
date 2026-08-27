"""Профили локальных серверов 1С: `%APPDATA%\\OneCStarter\\servers.json`.

Файл — калька политики `services/user_data.py`, но не наследник её кода:
профили серверов не привязаны к записям `ibases.v8i` и живут отдельным
жизненным циклом (создаются и правятся из раздела «Серверы», не при
каждом запуске базы).

Испорченное содержимое (не парсится как JSON, неизвестная схема, битая
запись) не чинится и не затирается: файл уезжает в `<имя>.bad`, а работа
продолжается с пустым списком профилей. Недоступный файл (блокировка,
права, отвалившийся сетевой диск) — другой случай: это не порча
содержимого, и подменять его пустым списком нельзя, иначе первое же
сохранение затрёт настроенные профили серверов без следа. Такой случай —
это `ServersUnavailableError`, а не пустой список.

`range_start`/`range_end` пишутся одной строкой `"start:end"` (спека §5):
это диапазон портов, ragport в JSON пары читались бы отдельными числами
не хуже, но JSON-схема зафиксирована спекой в этом виде. Неизвестные ключи
внутри записи профиля игнорируются — задел под будущие поля без миграции,
тот же приём, что и в `settings.py`.
"""  # noqa: RUF002

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.server import ServerProfile
from onecstarter.services.errors import ServersUnavailableError

SCHEMA_VERSION = 1

__all__ = [
    "SCHEMA_VERSION",
    "ServersUnavailableError",
    "load_profiles",
    "save_profiles",
]


def load_profiles(path: Path) -> list[ServerProfile]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        # Файл есть, но недоступен: блокировка, права, отвалившийся сетевой
        # диск. Это не порча содержимого, и подменять его пустым списком  # noqa: RUF003
        # нельзя — следующее сохранение затрёт профили пользователя.
        raise ServersUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
        entries = payload["profiles"]
        if not isinstance(entries, list):
            raise ValueError("profiles не список")
        return [_decode(entry) for entry in entries]
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_profiles(path: Path, profiles: Sequence[ServerProfile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "profiles": [_encode(profile) for profile in profiles],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write(path, text.encode("utf-8"))


def _move_aside(path: Path) -> list[ServerProfile]:
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError as error:
        # Не сумев убрать испорченный файл, продолжать с пустым списком  # noqa: RUF003
        # нельзя: первое же сохранение затрёт то, что пользователь мог бы
        # из него достать.
        raise ServersUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"  # noqa: RUF001
        ) from error
    return []


def _encode(profile: ServerProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "version": profile.version,
        "port": profile.port,
        "regport": profile.regport,
        "range": f"{profile.range_start}:{profile.range_end}",
        "cluster_dir": profile.cluster_dir,
        "debug": profile.debug,
        "http": profile.http,
        "extra_args": profile.extra_args,
    }


def _decode(value: Any) -> ServerProfile:
    if not isinstance(value, dict):
        raise ValueError("запись профиля не объект")
    range_start, _, range_end = str(value["range"]).partition(":")
    return ServerProfile(
        id=str(value["id"]),
        name=str(value["name"]),
        version=str(value["version"]),
        port=int(value["port"]),
        regport=int(value["regport"]),
        range_start=int(range_start),
        range_end=int(range_end),
        cluster_dir=str(value["cluster_dir"]),
        debug=bool(value.get("debug", True)),
        http=bool(value.get("http", True)),
        extra_args=str(value.get("extra_args", "")),
    )
