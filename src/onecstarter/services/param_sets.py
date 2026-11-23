"""Именованные наборы параметров запуска — %APPDATA%\\OneCStarter\\param_sets.json (спека v4, §4.6).

Набор общий для всех баз, у него есть режим (1С:Предприятие / Конфигуратор). Файл наш:
формат не согласуется ни с кем. Политика повреждённого файла — та же, что у
`edt_store.py`: перенос в `.bad` с пустым списком; не сумели перенести или файл
недоступен — `ParamSetsUnavailableError`, чтобы первое же сохранение не затёрло
наборы пользователя.
"""  # noqa: RUF002

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.cli_catalog import Mode
from onecstarter.services.errors import InvalidRequestError, ParamSetsUnavailableError

__all__ = [
    "SCHEMA_VERSION",
    "ParamSet",
    "load_param_sets",
    "remove_set",
    "save_param_sets",
    "sets_for",
    "upsert_set",
]

SCHEMA_VERSION = 1

_log = logging.getLogger("onecstarter.param_sets")


@dataclass(frozen=True)
class ParamSet:
    name: str
    mode: Mode
    params: str


def load_param_sets(path: Path) -> tuple[ParamSet, ...]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        raise ParamSetsUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
        entries = payload.get("sets")
        if not isinstance(entries, list):
            raise ValueError("sets не список")
        return tuple(_decode(entry) for entry in entries)
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_param_sets(path: Path, sets: Sequence[ParamSet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "sets": [{"name": s.name, "mode": s.mode.value, "params": s.params} for s in sets],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write(path, text.encode("utf-8"))


def upsert_set(sets: Sequence[ParamSet], new: ParamSet) -> tuple[ParamSet, ...]:
    """Заменить набор с тем же именем (без учёта регистра) или дописать в конец."""  # noqa: RUF002
    if not new.name.strip():
        raise InvalidRequestError("Не задано имя набора")  # noqa: RUF001
    if "\r" in new.params or "\n" in new.params:
        raise InvalidRequestError("Параметры набора не могут содержать перевод строки")
    wanted = new.name.strip().casefold()
    replaced = False
    result: list[ParamSet] = []
    for current in sets:
        if current.name.strip().casefold() == wanted:
            result.append(new)
            replaced = True
        else:
            result.append(current)
    if not replaced:
        result.append(new)
    return tuple(result)


def remove_set(sets: Sequence[ParamSet], name: str) -> tuple[ParamSet, ...]:
    wanted = name.strip().casefold()
    return tuple(s for s in sets if s.name.strip().casefold() != wanted)


def sets_for(sets: Sequence[ParamSet], mode: Mode) -> tuple[ParamSet, ...]:
    return tuple(s for s in sets if s.mode is mode)


def _decode(value: Any) -> ParamSet:
    if not isinstance(value, dict):
        raise ValueError("набор не объект")
    return ParamSet(
        name=str(value["name"]),
        mode=Mode(str(value["mode"])),
        params=str(value.get("params", "")),
    )


def _move_aside(path: Path) -> tuple[ParamSet, ...]:
    """Перенести повреждённый файл в `.bad`; в лог — только имена файлов.

    Содержимое в лог не идёт: в наборе, правленном руками, может оказаться пароль
    (инвариант 5; финальное ревью блока 1, F7).
    """
    bad = path.with_name(path.name + ".bad")
    try:
        path.replace(bad)
    except OSError as error:
        raise ParamSetsUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"  # noqa: RUF001
        ) from error
    _log.warning("%s повреждён и перенесён в %s, наборы пусты", path.name, bad.name)
    return ()
