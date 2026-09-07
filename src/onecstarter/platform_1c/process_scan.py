"""Снимок процессов серверов 1С: `psutil` и его пустая заглушка.

Механизм скана выбран экспериментом, не догадкой ([Ф] 26.08.2026, замер В3,
`docs/research/t07-protocol.md`): тёплый снимок `psutil` 7.x на 659 процессах
берёт ~90 мс против ~0,8 с у WMI (`Get-CimInstance Win32_Process`) — в 9 раз
дешевле, что важно при периодическом скане (§4.4 спеки). Тот же замер:
`psutil` отдаёт путь `exe` SYSTEM-процессов без повышения прав (107/107
в замере) — WMI не отдаёт вовсе (0/107), а значит без `psutil` версия
непрозрачного чужого сервера была бы не видна.

Командная строка (`cmdline`) чужого процесса всё равно недоступна без
повышения ([Ф] В1) — это ограничение уровня ОС, а не выбора библиотеки:
других пользователей и служб SYSTEM `cmdline`/`exe`-ограничение накрывает
одинаково что WMI, что `psutil`, что `CommandLineToArgvW`. Поэтому
недоступные поля `ProcessInfo` — честный `None`, а не выдумка, и снимок не
падает целиком из-за одного недоступного или исчезнувшего процесса:
`AccessDenied` на отдельном поле `psutil` сам превращает в `None`
(`Process.as_dict`), `NoSuchProcess` на процессе `psutil` сам глотает внутри
`process_iter` — здесь это подстраховано ещё раз на случай гонки между
проверкой имени и чтением полей.
"""  # noqa: RUF002

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psutil

__all__ = [
    "NullScanner",
    "ProcessInfo",
    "ProcessScanner",
    "PsutilScanner",
]


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    executable: Path | None  # None — нет доступа ([Ф] В1: чужой процесс/служба)  # noqa: RUF003
    argv: tuple[str, ...] | None  # None — нет доступа либо пустая cmdline


class ProcessScanner(Protocol):
    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]: ...


class PsutilScanner:
    """Настоящий снимок процессов. Единственное место в проекте с `psutil`."""  # noqa: RUF002

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        result: list[ProcessInfo] = []
        processes = psutil.process_iter(attrs=["pid", "name", "cmdline", "exe"])
        for process in processes:
            try:
                info = process.info
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
            name = info.get("name")
            if name is None or name.casefold() not in names:
                continue
            cmdline = info.get("cmdline")
            argv = tuple(cmdline) if cmdline else None
            exe = info.get("exe")
            executable = Path(exe) if exe else None
            result.append(
                ProcessInfo(pid=info["pid"], name=name, executable=executable, argv=argv)
            )
        return result


class NullScanner:
    """Снимок, которого нет: для самопроверки собранного экземпляра (долг №8)."""

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        return []
