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

import psutil as psutil  # реэкспорт: process_scan.psutil в тестах

from onecstarter import perf

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
    """Настоящий снимок процессов. Единственное место в проекте с `psutil`.

    Имя берётся у всех процессов, `exe`/`cmdline` — только у совпавших.

    **[Ф] проверено по исходникам psutil 7.2.2** (`psutil/__init__.py`,
    `psutil/_pswindows.py`, `psutil/arch/windows/proc.c` — тот дистрибутив,
    что стоит в `.venv` проекта): имя процесса на Windows — НЕ один системный
    вызов на весь список. `Process.name()` вызывает `self.exe()`, а тот на
    каждый ещё не виденный процесс делает пару вызовов ядра: `OpenProcess`
    (проверка, что процесс жив) и `NtQuerySystemInformation` с классом
    `SystemProcessIdInformation` (путь исполняемого файла, из которого берётся
    basename). Прежняя редакция запрашивала это поле у всех процессов системы
    ради семи — расточительность была настоящей, но не по той причине,
    которую называла первая редакция этого докстринга.

    Экономия правки реальна по другой причине: `Process.name()` (публичный
    класс, `psutil/__init__.py`) кэширует результат в `self._name`
    БЕЗУСЛОВНО, с первого успешного вызова, а `process_iter()` держит сами
    объекты `Process` между вызовами в собственном глобальном кэше — так что
    для процесса, уже встреченного на предыдущем скане, имя отдаётся без
    обращения к ОС вообще. `cmdline()` кэшируется точно так же скудно, как
    описано изначально: у него нет ни этого кэша, ни `memoize_when_activated`
    на уровне `_pswindows` — каждый вызов идёт в ОС заново. Поэтому старая
    редакция платила за `cmdline()` у всех процессов на КАЖДОМ скане (перечитывая
    его каждые 5 с), а не только на первом — именно это и есть настоящая
    дороговизна, которую правка снимает.

    Следствие, важное для чтения `perf.log`: раз кэш имени пуст до первого
    скана, ПЕРВЫЙ скан после запуска остаётся дорогим и после этой правки —
    он платит за имя всех процессов так же, как платил раньше. Дешевеют
    только повторные сканы (спека 3.2.1, §2, §8, §9). Замер 22.09.2026 на
    651 процессе: 81–128 мс против 4,7–5,7 мс при том же результате — то
    сравнение снято на ТЁПЛОМ повторном скане (спека 3.2.1, §4).
    """  # noqa: RUF002

    def __init__(self, label: str = "") -> None:
        # Метка попадает в perf-строку (задача 3) и отличает скан серверов
        # от скана EDT: оба монитора держат свой экземпляр сканера.  # noqa: RUF003
        # На результат не влияет.  # noqa: RUF003
        self._label = label

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        # `stage` — литерал: метка приходит из кода проводки окна
        # ("servers"/"edt", инвариант 5), не из файлов, окружения
        # или самих процессов.
        stage = f"скан процессов ({self._label})" if self._label else "скан процессов"
        with perf.measure(stage) as counters:
            result: list[ProcessInfo] = []
            seen = 0
            for process in psutil.process_iter(attrs=["pid", "name"]):
                seen += 1
                try:
                    info = process.info
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
                name = info.get("name")
                if name is None or name.casefold() not in names:
                    continue
                details = _details_of(process)
                if details is None:
                    # Процесс умер между чтением имени и чтением деталей.
                    # Прежняя редакция теряла его тем же способом (`continue`  # noqa: RUF003
                    # на NoSuchProcess), и это правильное поведение: отдать
                    # запись с пустыми полями значило бы выдумать факт.  # noqa: RUF003
                    continue
                executable, argv = details
                result.append(
                    ProcessInfo(pid=info["pid"], name=name, executable=executable, argv=argv)
                )
            # Счётчики заполняются ДО выхода из блока — `measure` читает
            # словарь в `finally`, и дописать в него после выхода поздно.
            counters["просмотрено"] = seen
            counters["совпало"] = len(result)
            return result


def _details_of(
    process: psutil.Process,
) -> tuple[Path | None, tuple[str, ...] | None] | None:
    """`exe` и `cmdline` совпавшего процесса. `None` — процесса уже нет.

    Поля читаются ПООТДЕЛЬНОСТИ, и `AccessDenied` на одном не отменяет
    другое: ровно так вёл себя `Process.as_dict` в прежней редакции —
    он переводил каждое недоступное поле в `None` сам. Общий `try`
    вокруг обоих чтений молча потерял бы доступный `argv` у процесса
    с недоступным `exe` ([Ф] В1: чужой процесс или служба SYSTEM).
    """  # noqa: RUF002
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
    return (Path(exe) if exe else None, tuple(cmdline) if cmdline else None)


class NullScanner:
    """Снимок, которого нет: для самопроверки собранного экземпляра (долг №8)."""

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        return []
