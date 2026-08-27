"""Остановка дерева процессов сервера 1С: `PsutilControl` и её заглушка.

`TerminateProcess` на `ragent` **не убивает детей** ([Ф] Б2, 26.08.2026,
`docs/research/t07-protocol.md`): `rmngr` и `rphost` продолжают работать
и держать свои порты — остановка обязана гасить дерево целиком (снимок
детей по `ParentProcessId` живого `ragent`, затем убийство; порядок и
состав дерева — забота вызывающего кода, здесь только примитивы). Тот же
замер подтвердил целостность: кластер переживает жёсткое убийство —
повторный запуск на том же `-d` поднимается с тем же `clstid`, файлы
реестра без обломков. Поэтому жёсткое `kill()` (`TerminateProcess`)
безопасно для кластера и не требует мягкого сигнала остановки.

`terminate` принимает не голый `pid`, а пару `(pid, expected_create_time)`:
Windows переиспользует PID после завершения процесса, и без сверки
времени создания есть риск убить чужой, случайно занявший тот же PID,
процесс. Источник сверки — тот же `psutil`, что и снимок дерева, поэтому
допуск 0.5 с — это только погрешность двух независимых чтений `float`,
не неопределённость самого времени создания.
"""  # noqa: RUF002

from pathlib import Path
from typing import Protocol

import psutil

from onecstarter.platform_1c.process_scan import ProcessInfo

__all__ = [
    "NullControl",
    "ProcessAccessError",
    "ProcessControl",
    "ProcessMismatchError",
    "PsutilControl",
]

_CREATE_TIME_TOLERANCE = 0.5


class ProcessMismatchError(Exception):
    """`create_time` процесса с данным `pid` разошёлся с ожидаемым.

    Означает, что PID переиспользован другим процессом с момента снимка —
    завершать его нельзя, это не тот процесс, который имелся в виду.
    """  # noqa: RUF002


class ProcessAccessError(Exception):
    """Нет прав на `kill()`/чтение `create_time()` данного процесса.

    Находка финального ревью ветки v2-servers (CRITICAL 1b): `psutil.AccessDenied`
    уходил из `PsutilControl.terminate` голым исключением психутила мимо всех
    ловцов слоя `services` (`ServersWorkspace` ловит только `ProcessMismatchError`),
    и «Остановить» на процессе другого пользователя/службы падало трассировкой
    вместо внятного сообщения. `services/servers.py::_terminate_or_raise`
    переводит это исключение в `ServerStopError`.
    """


class ProcessControl(Protocol):
    def children(self, pid: int) -> list[ProcessInfo]: ...

    def terminate(self, pid: int, expected_create_time: float) -> None: ...


class PsutilControl:
    """Настоящее управление процессами. Единственное (кроме `process_scan`) место с `psutil`."""  # noqa: RUF002

    def children(self, pid: int) -> list[ProcessInfo]:
        try:
            children = psutil.Process(pid).children(recursive=False)
        except psutil.NoSuchProcess:
            return []
        result: list[ProcessInfo] = []
        for child in children:
            try:
                info = child.as_dict(attrs=["pid", "name", "cmdline", "exe", "create_time"])
            except psutil.NoSuchProcess:
                # Гонка: ребёнок умер между .children() и .as_dict() — пропускаем
                # только его. AccessDenied здесь не ловим: as_dict гасит его сам  # noqa: RUF003
                # на каждом поле по отдельности, подставляя None (см. исходник
                # psutil.Process.as_dict — except (AccessDenied, ZombieProcess):
                # ret = ad_value) — до этого except он никогда не долетает.
                continue
            cmdline = info.get("cmdline")
            exe = info.get("exe")
            create_time = info.get("create_time")
            result.append(
                ProcessInfo(
                    pid=info["pid"],
                    name=info.get("name") or "",
                    executable=Path(exe) if exe else None,
                    argv=tuple(cmdline) if cmdline else None,
                    create_time=float(create_time) if create_time is not None else 0.0,
                )
            )
        return result

    def terminate(self, pid: int, expected_create_time: float) -> None:
        try:
            process = psutil.Process(pid)
            actual_create_time = process.create_time()
            if abs(actual_create_time - expected_create_time) > _CREATE_TIME_TOLERANCE:
                raise ProcessMismatchError(
                    f"pid {pid}: create_time {actual_create_time} не совпадает "
                    f"с ожидаемым {expected_create_time} — PID переиспользован, не трогаем"  # noqa: RUF001
                )
            process.kill()
        except psutil.NoSuchProcess:
            return  # уже нет — цель достигнута
        except psutil.AccessDenied as error:
            # Процесс другого пользователя или службы: create_time()/kill()
            # отказывают правами, а не «процесса нет» — честный отказ слоя,  # noqa: RUF003
            # не голый psutil.AccessDenied наружу (CRITICAL 1b, финальное
            # ревью ветки).
            raise ProcessAccessError(
                f"pid {pid}: нет прав на завершение процесса"
            ) from error


class NullControl:
    """Управление, которого нет: для самопроверки собранного экземпляра."""

    def children(self, pid: int) -> list[ProcessInfo]:
        return []

    def terminate(self, pid: int, expected_create_time: float) -> None:
        pass
