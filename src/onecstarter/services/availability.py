"""Доступность каталога файловой базы — чистая логика, без Qt и без ФС внутри.

Инвариант 1: модуль не импортирует PySide6. Инвариант 2: решение о доступности
принимается по данным, поданным аргументами, — обращение к файловой системе
(`stat`) подаётся вызывающим, поэтому вся таблица случаев проверяется без диска.

Проверяются только файловые записи с абсолютным путём. Относительный путь
в `File=` не разрешается: относительно чего это делает платформа — [Д],
замера нет, а разрешить его относительно каталога `ibases.v8i` было бы
догадкой, выданной за факт (спека §2).

Спека — docs/superpowers/specs/2026-09-09-v24-file-availability-design.md.
"""  # noqa: RUF002

import os
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from onecstarter.domain.connect import ConnectKind, find_fragment, parse_connect
from onecstarter.services.model import InfobaseItem

RELATIVE_NOTE = "Путь относительный — доступность не проверялась"


class Availability(Enum):
    """Три состояния во времени, два в исходе (спека §1).

    `UNKNOWN` — не «не удалось проверить», а «ещё не проверяли»: пока фоновый
    проход идёт, крестика нет. Тот же приём, что `«…»` в колонке версии, пока
    не закончилось обнаружение платформ (спека T-04.6 §3.4). Без него весь
    список на старте на мгновение становился бы битым.
    """  # noqa: RUF002

    UNKNOWN = "unknown"
    PRESENT = "present"
    MISSING = "missing"


@dataclass(frozen=True)
class ProbeTarget:
    """Что и под каким ключом проверять.

    `key` — нормализованный путь, по нему снимаются дубли и хранится результат.
    `path` — исходное значение `File=` из файла: `stat` зовётся именно на нём,
    чтобы проверить ровно то, что откроет платформа, а не результат нашей
    нормализации.
    """  # noqa: RUF002

    key: str
    path: str


def path_key(value: str) -> str:
    """Ключ пути для сравнения и дедупликации.

    `normcase` на Windows приводит регистр и разделители к одному виду,
    `normpath` схлопывает `.` и `..`. Только ключ — не адрес для `stat`.
    """
    return os.path.normcase(os.path.normpath(value))


def file_path_of(item: InfobaseItem) -> str | None:
    """Значение `File=` файловой записи; `None` — проверять нечего."""
    if item.is_group or item.kind is not ConnectKind.FILE or not item.connect:
        return None
    value = find_fragment(parse_connect(item.connect), "File")
    return value or None


def probe_targets(items: Iterable[InfobaseItem]) -> dict[str, ProbeTarget]:
    """Ключ записи → цель проверки. К файловой системе не обращается."""  # noqa: RUF002
    targets: dict[str, ProbeTarget] = {}
    for item in items:
        value = file_path_of(item)
        if value is None or not Path(value).is_absolute():
            continue
        targets[item.key] = ProbeTarget(path_key(value), value)
    return targets


def relative_path_note(item: InfobaseItem) -> str | None:
    """Почему запись не проверялась, если причина — относительный путь."""
    value = file_path_of(item)
    if value is None or Path(value).is_absolute():
        return None
    return RELATIVE_NOTE


def availability_hint(state: Availability, path: str) -> str | None:
    """Строка подсказки о доступности; `None` — говорить нечего."""  # noqa: RUF002
    if state is Availability.MISSING:
        return f"Каталог не найден: {path}"
    return None
