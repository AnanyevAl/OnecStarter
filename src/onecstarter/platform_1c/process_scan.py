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
import threading
import time
from collections.abc import Callable
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


# Снимок общий на процесс, а не на экземпляр сканера: мониторы серверов и EDT  # noqa: RUF003
# тикают почти одновременно (по логам сервера — расхождение 22-80 мс), и второй
# обязан получить готовый снимок бесплатно. Порог в 2 с выбран между разбросом  # noqa: RUF003
# тиков и интервалом монитора (5 с) с запасом в обе стороны; при разъезде  # noqa: RUF003
# таймеров деградация мягкая — два снимка вместо одного.
_SNAPSHOT_TTL_S = 2.0
_snapshot_cache: tuple[float, list[tuple[int, str]]] | None = None
# Мониторы серверов и EDT — не последовательные тики одного потока, а два  # noqa: RUF003
# отдельных `threading.Thread` (ServerMonitor/EdtMonitor), стартующих подряд
# из ui/app.py: оба входят в _shared_snapshot почти одновременно и без  # noqa: RUF003
# блокировки оба видят пустой/протухший кэш — проверка кэша без синхронизации  # noqa: RUF003
# гонку не устраняет, а гарантирует её на каждом сдвоенном тике ([Ф] лог  # noqa: RUF003
# заказчика 25.09.2026: два скана по 49 мс с разницей в 1 мс).  # noqa: RUF003
_snapshot_cache_lock = threading.Lock()


def reset_snapshot_cache() -> None:
    """Сбросить общий снимок. Для тестов."""
    global _snapshot_cache
    with _snapshot_cache_lock:
        _snapshot_cache = None


def _shared_snapshot(clock: Callable[[], float]) -> list[tuple[int, str]]:
    global _snapshot_cache
    now = clock()
    cached = _snapshot_cache
    if cached is not None and now - cached[0] < _SNAPSHOT_TTL_S:
        return cached[1]
    # Снимок под блокировкой: CreateToolhelp32Snapshot — быстрый локальный
    # вызов без сети и без открытия процессов, поэтому держать блокировку на
    # время самого снимка безопасно. Повторная проверка кэша ПОСЛЕ захвата —
    # пока этот поток ждал, снимок мог уже сделать другой: тогда снимок
    # берётся один раз на двоих, а не по разу на каждый вызов.  # noqa: RUF003
    with _snapshot_cache_lock:
        now = clock()
        cached = _snapshot_cache
        if cached is not None and now - cached[0] < _SNAPSHOT_TTL_S:
            return cached[1]
        entries = snapshot_all()
        _snapshot_cache = (now, entries)
        return entries


# Срок годности записи кэша деталей по PID (Important 3 финального ревью ветки
# 3.2.2): сверка имени (см. `_details_of`) закрывает переиспользование номера
# процессом с ДРУГИМ именем, но не тем же — Windows выдаёт номер только что  # noqa: RUF003
# умершего процесса новому сразу, и без срока кэш отдавал бы командную строку
# остановленного профиля работающему вечно. Минута выбрана между ценой
# перечитывания (на сервере заказчика — два-три процесса по ~15 мс раз в минуту,
# то есть доли процента бюджета скана) и заметностью устаревших данных для
# пользователя — обе стороны в бюджете вехи неощутимы.  # noqa: RUF003
_DETAILS_TTL_S = 60.0


class WindowsProcessScanner:
    """Снимок Toolhelp для списка, `psutil` — только для деталей совпавших.

    Прежнее имя (`PsutilScanner`) стало бы ложным указателем: список процессов
    даёт теперь Windows одним снимком, а `psutil` остаётся только там, где нужны
    `exe` и `argv`, — у двух-трёх процессов вместо восьмисот.

    Детали кэшируются по PID: на сервере заказчика они стоят ~54 мс на пару
    процессов, больше самого снимка ([Ф], спека 3.2.2 «снимок процессов» §3).

    Запись кэша годится не дольше `_DETAILS_TTL_S` (Important 3 финального ревью
    ветки 3.2.2). Сверка имени при том же PID закрывает переиспользование номера
    процессом с ДРУГИМ именем — но не тем же: Windows выдаёт номер только что
    умершего процесса новому СРАЗУ, разрыва между двумя снимками может не быть
    вовсе, а если новый процесс называется так же (пользователь остановил один
    профиль сервера и тут же запустил другой `ragent.exe`), имя в кэше не
    меняется, и сверка имени этот случай не ловит. Без срока годности кэш отдавал
    бы командную строку остановленного профиля работающему — навсегда, до смерти
    самого нового процесса. Срок годности закрывает то, чего не закрывает сверка
    имени; вместе оба правила покрывают оба случая переиспользования PID.
    """  # noqa: RUF002

    def __init__(self, label: str = "", *, clock: Callable[[], float] = time.monotonic) -> None:
        self._label = label
        self._clock = clock
        # pid -> (время чтения, имя на тот момент, exe, argv). Имя закрывает
        # переиспользование PID процессом с ДРУГИМ именем — без сверки мы отдали  # noqa: RUF003
        # бы данные покойника живому процессу другого рода. Время чтения плюс
        # `_DETAILS_TTL_S` в `_details_of` закрывают случай, которого сверка имени
        # не видит: тот же PID и то же имя, но уже ДРУГОЙ процесс (докстринг
        # класса выше, Important 3 финального ревью ветки 3.2.2).
        self._details: dict[int, tuple[float, str, Path | None, tuple[str, ...] | None]] = {}

    def cached_pids(self) -> set[int]:
        """Для тестов: какие PID сейчас в кэше деталей."""
        return set(self._details)

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        stage = f"скан процессов ({self._label})" if self._label else "скан процессов"
        with perf.measure(stage) as counters:
            try:
                entries = _shared_snapshot(self._clock)
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

        Запись годится, только если имя совпало И она не старше `_DETAILS_TTL_S`
        (Important 3 финального ревью ветки 3.2.2, докстринг класса выше): сверка
        имени одна не ловит переиспользование PID процессом с ТЕМ ЖЕ именем —
        Windows выдаёт номер умершего процесса новому сразу, разрыва между
        снимками может не быть вовсе. Минута — между двумя-тремя обращениями
        к процессу (~15 мс на сервере заказчика, §0/§1 спеки снимка) раз в минуту
        и заметностью устаревших данных для пользователя: цена в бюджете вехи
        неощутима, а окно ошибки короче, чем время, за которое пользователь
        успеет заметить и предпринять что-то по неверной карточке.
        """  # noqa: RUF002
        cached = self._details.get(pid)
        if cached is not None and cached[1] == name and self._clock() - cached[0] < _DETAILS_TTL_S:
            return cached[2], cached[3]
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
        self._details[pid] = (self._clock(), name, executable, argv)
        return executable, argv


class NullScanner:
    """Снимок, которого нет: для самопроверки собранного экземпляра (долг №8)."""

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        return []
