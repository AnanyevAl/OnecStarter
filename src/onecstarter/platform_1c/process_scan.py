"""Список процессов — снимок Toolhelp, детали (`exe`/`cmdline`) — `psutil`.

Список процессов даёт не `psutil`, а `process_snapshot.snapshot_all()` (задача 1,
спека 3.2.2 «снимок процессов» §0): `Process.name()`/`process_iter` на Windows
читают путь образа, а это обращение к процессу — на сервере заказчика такое
обращение проходит через агент безопасности и стоит ~15 мс ([Ф] замер
25.09.2026), тогда как снимок Toolhelp не открывает ни одного процесса.
`psutil` остаётся здесь только для `exe`/`cmdline` у процессов, чьё имя из
снимка совпало с одним из искомых, — таких на сервере заказчика два-три
из восьмисот, и их детали кэшируются по PID (см. `WindowsProcessScanner`).

`exe()`/`cmdline()` читаются ПООТДЕЛЬНОСТИ, и `AccessDenied` на одном не
отменяет другое — так вело себя старое `Process.as_dict` (переводил
недоступное поле в `None` сам): общий `try` вокруг обоих чтений потерял бы
доступный `argv` у процесса с недоступным `exe` ([Ф] В1: чужой процесс или
служба SYSTEM). `NoSuchProcess` на любом из полей — процесс исчез между
снимком и чтением деталей, запись в результат не попадает вовсе (поведение
3.2.1 §4, не меняется).
"""  # noqa: RUF002

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psutil as psutil  # реэкспорт: process_scan.psutil в тестах

from onecstarter import perf
from onecstarter.platform_1c.process_snapshot import SnapshotError, snapshot_all

__all__ = [
    "NullScanner",
    "ProcessInfo",
    "ProcessScanner",
    "WindowsProcessScanner",
]

_log = logging.getLogger("onecstarter.process_scan")


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    executable: Path | None  # None — нет доступа ([Ф] В1: чужой процесс/служба)  # noqa: RUF003
    argv: tuple[str, ...] | None  # None — нет доступа либо пустая cmdline


class ProcessScanner(Protocol):
    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]: ...


def _process_by_pid(pid: int) -> psutil.Process:
    """Отдельной функцией — тест подменяет её, не трогая psutil целиком."""
    return psutil.Process(pid)


class WindowsProcessScanner:
    """Снимок Toolhelp для списка, `psutil` — только для деталей совпавших.

    Прежнее имя (`PsutilScanner`) стало бы ложным указателем: список процессов
    даёт теперь Windows одним снимком, а `psutil` остаётся только там, где нужны
    `exe` и `argv`, — у двух-трёх процессов вместо восьмисот.

    Детали кэшируются по PID: на сервере заказчика они стоят ~54 мс на пару
    процессов, больше самого снимка ([Ф], спека 3.2.2 «снимок процессов» §3).
    """  # noqa: RUF002

    def __init__(self, label: str = "") -> None:
        self._label = label
        # pid -> (имя на момент чтения, exe, argv). Имя хранится, чтобы отличить
        # переиспользованный PID: Windows выдаёт номера умерших процессов новым,
        # и без сверки мы отдали бы данные покойника живому процессу.
        self._details: dict[int, tuple[str, Path | None, tuple[str, ...] | None]] = {}

    def cached_pids(self) -> set[int]:
        """Для тестов: какие PID сейчас в кэше деталей."""
        return set(self._details)

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        stage = f"скан процессов ({self._label})" if self._label else "скан процессов"
        with perf.measure(stage) as counters:
            try:
                entries = snapshot_all()
            except SnapshotError as error:
                # Тот же исход, что у прежнего отказа скана: пустой список,  # noqa: RUF003
                # карточки покажут «не работает», причина — в логе.
                _log.warning("снимок процессов не удался: %s", error.strerror)
                counters["просмотрено"] = 0
                counters["совпало"] = 0
                return []

            alive = {pid for pid, _name in entries}
            # Записи умерших процессов уходят вместе с ними, иначе кэш растёт  # noqa: RUF003
            # на каждом завершившемся процессе до конца сессии.
            for pid in list(self._details):
                if pid not in alive:
                    del self._details[pid]

            result: list[ProcessInfo] = []
            for pid, name in entries:
                if name.casefold() not in names:
                    continue
                details = self._details_of(pid, name)
                if details is None:
                    continue
                executable, argv = details
                result.append(
                    ProcessInfo(pid=pid, name=name, executable=executable, argv=argv)
                )
            counters["просмотрено"] = len(entries)
            counters["совпало"] = len(result)
            return result

    def _details_of(
        self, pid: int, name: str
    ) -> tuple[Path | None, tuple[str, ...] | None] | None:
        """`exe` и `argv` процесса; `None` — процесса уже нет.

        `AccessDenied` кэшируется как `None` наравне с успехом: недоступный
        чужой процесс (служба SYSTEM) — именно тот, кто дорог, и повторять
        отказ на каждом скане значило бы сохранить половину прежней цены.
        `NoSuchProcess` не кэшируется: процесса нет, записи о нём не нужно.
        """  # noqa: RUF002
        cached = self._details.get(pid)
        if cached is not None and cached[0] == name:
            return cached[1], cached[2]
        try:
            process = _process_by_pid(pid)
        except psutil.NoSuchProcess:
            return None
        try:
            exe = process.exe()
        except psutil.NoSuchProcess:
            return None
        except psutil.AccessDenied:
            exe = None
        try:
            cmdline = process.cmdline()
        except psutil.NoSuchProcess:
            return None
        except psutil.AccessDenied:
            cmdline = None
        executable = Path(exe) if exe else None
        argv = tuple(cmdline) if cmdline else None
        self._details[pid] = (name, executable, argv)
        return executable, argv


class NullScanner:
    """Снимок, которого нет: для самопроверки собранного экземпляра (долг №8)."""

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        return []
