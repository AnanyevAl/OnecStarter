"""Порождение серверных процессов 1С — скрытая консоль, файл-журнал, Job.

`CREATE_NO_WINDOW` вместо `DETACHED_PROCESS`, которым запускается клиент
(`process.py::spawn`): `DETACHED_PROCESS` лишает `ragent` консоли, и его дети
(`rmngr`, `rphost`, `dbgs`, `dbda`, `java` из `dbgs`), не найдя её, заводят
каждый своё окно — это и есть дефект ручного чек-листа 28.08.2026
(`docs/tasks.md`, «Находка ручного чек-листа»). Скрытая консоль
(`CREATE_NO_WINDOW`) даёт `ragent` консоль, просто невидимую, — дети её
наследуют и своих окон не открывают. Ссылка на факт составная (уточнение
финального ревью ветки T-10): А3 (T-09.4, «ни одного окна у всего дерева,
дерево живо») измерялся PowerShell'ом (`Start-Process -WindowStyle Hidden`),
не самим флагом `CREATE_NO_WINDOW`; сам флаг — то, что реально используется
здесь, — подтверждён Б2 (T-09.5б/T-09.7, скрипт `e:\tmp\t09\b2_job.py`,
эталон структур и последовательности вызовов): живое дерево `ragent` в Job,
`conhost` в списке живых процессов (значит, скрытая КОНСОЛЬ реально создана,
а не просто скрыто окно PowerShell) — `docs/research/t09-protocol.md`,
[Ф] Б2 T-09 (флаг), А3 (механизм окон).

stdout `ragent` перенаправляется в файл журнала. Ловить этим файлом весь
вывод дерева не получится и не нужно: баннеры `rmngr`/`rphost` существуют
только в их собственных окнах и не попадают ни в унаследованную консоль, ни
в редирект — в файле практически оказывается только строка `dbgs`, и это
ожидаемый результат, а не недостача ([Ф] А1 T-09, эксперимент T-09.2).

`job.assign()` обязан идти сразу после `Popen`, до того как `ragent`
породит первого ребёнка: `AssignProcessToJobObject` не поглощает уже
существующих потомков — находка задачи 1 T-10 (`platform_1c/job.py`,
`test_job.py::test_close_kills_parent_and_grandchild`). Между `Popen` и
`assign` стоит только выход из `with` (закрытие родительского хендла файла
журнала) — он намеренный и безопасный: закрытие родительской стороны
файла не влияет на уже унаследованный дочерним процессом дескриптор.
В проде запас времени до первого ребёнка ~12 c, но порядок вызовов здесь —
часть контракта, а не оптимизация под конкретный замер.

Если `job.assign()` откажет (`JobError`), уже порождённый процесс сервера
жёстко убивается здесь же, до того как исключение уйдёт наружу: сервер без
Job — это сервер без гарантии kill-on-close, ради которой всё строилось
(`platform_1c/job.py`), и оставлять его висеть в этом состоянии нельзя.
Жёсткое `process.kill()` (`TerminateProcess` под капотом) в этой ситуации
безопасно — то же решение, что и штатное завершение через Job Object
([Ф] Б2 T-07: `TerminateProcess` не портит файлы кластера).

НАХОДКА 1 ручного чек-листа T-10 (Critical, 29.08.2026,
`.superpowers/sdd/2026-08-28-v2-servers-journal/manual-checklist.md`,
раздел «Шаг 2»): до этой правки хендл журнала ребёнку открывался обычным
`Path.open("ab")` — Windows даёт такому хендлу СВОЙ файловый указатель,
застывающий на позиции конца файла в момент открытия. Координатор
(`services/servers.py::log_event` → `server_journal.append_event`) пишет
ОТДЕЛЬНЫМ хендлом (`open("a")` при каждом вызове) и честно попадает
в фактический конец файла — но когда ребёнок затем пишет через СВОЙ,
уже устаревший хендл, запись идёт по ЕГО указателю, поверх уже дописанной
строки координатора: в живом прогоне так пропали события `порождён PID`
и `работает · PID` (баннер платформы длиннее события — затирал его
целиком, без следа). `_open_append_shared` открывает хендл ребёнку через
`CreateFileW` с правом `FILE_APPEND_DATA` БЕЗ `FILE_WRITE_DATA` — запись
по такому хендлу ОС атомарно направляет в фактический конец файла
НЕЗАВИСИМО от указателя, сохранённого в самом хендле (тот же класс
гарантии, что `O_APPEND` на POSIX, только на уровне драйвера NTFS, а не
эмуляции рантайма) — затирание становится невозможно. Побочный эффект
того же вызова — `FILE_SHARE_DELETE`: закрывает причину долга ротации
(`docs/tasks.md`, долг вехи T-10, п.3) — `Path.replace` внутри
`server_journal.rotate_journal` теперь проходит и при живом ребёнке-
писателе; best-effort ветка `services/servers.py::start` остаётся
страховкой ТОЛЬКО для чужих держателей, открывших файл обычным `open()`
(`tests/unit/test_servers.py::
test_start_survives_rotation_failure_when_previous_journal_is_locked`).
"""  # noqa: RUF002

import ctypes
import msvcrt
import os
import subprocess
import warnings
from ctypes import wintypes
from pathlib import Path

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import JobError, NullJob, ServerJob

__all__ = ["spawn_server"]

_FILE_APPEND_DATA = 0x0004
_SYNCHRONIZE = 0x00100000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_ALWAYS = 4
_FILE_ATTRIBUTE_NORMAL = 0x80
# `c_void_p(-1).value` — то же битовое представление, что INVALID_HANDLE_VALUE
# у CreateFileW (все биты установлены), в том виде, в каком ctypes отдаёт  # noqa: RUF003
# результат HANDLE-возврата (см. докстринг `_open_append_shared`).
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def _open_append_shared(path: Path) -> int:
    """Открыть журнал хендлом, который пишет строго в конец файла — [Ф] 29.08.2026.

    Лекарство находки 1 ручного чек-листа T-10 (докстринг модуля):
    `CreateFileW` с правом `FILE_APPEND_DATA` (без `FILE_WRITE_DATA`) —
    единственный способ на Windows получить хендл, для которого КАЖДАЯ
    запись атомарно уходит в фактический конец файла независимо от
    указателя, хранящегося в самом хендле; обычный `open("ab")` такой
    гарантии не даёт (указатель хендла фиксируется в момент открытия
    и не следует за чужими дозаписями). `FILE_SHARE_DELETE` в наборе
    флагов расшаривания — попутное лекарство долга ротации (см. докстринг
    модуля): `Path.replace` проходит, пока этот хендл жив.

    `use_last_error=True` и явные `argtypes`/`restype` — гигиена ctypes,
    для НОВОГО кода этой волны исправлений, в отличие от долга
    `platform_1c/job.py` (см. `docs/tasks.md`, долг вехи T-10), не
    повторяем. Возвращает файловый дескриптор C-рантайма
    (`msvcrt.open_osfhandle`) — тот вид хендла, что принимает `stdout=`
    у `subprocess.Popen`; `os.O_APPEND` на самом дескрипторе избыточен
    поверх `FILE_APPEND_DATA`, но не вредит и оставлен для симметрии
    с обычным файловым API.

    `OSError` (через `ctypes.WinError`, несёт `GetLastError()` и текст
    сообщения ОС) — если `CreateFileW` отказал (`INVALID_HANDLE_VALUE`):
    например, каталог журнала не существует. Уходит наружу как есть —
    тот же контракт, что раньше нёс `Path.open("ab")` (`OSError` слоя
    `services` переводит его в `ServerError`).
    """  # noqa: RUF002
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    handle = k32.CreateFileW(
        str(path),
        _FILE_APPEND_DATA | _SYNCHRONIZE,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_ALWAYS,
        _FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)
    return msvcrt.open_osfhandle(handle, os.O_APPEND)


def spawn_server(command: LaunchCommand, log_path: Path, job: ServerJob | NullJob) -> int:
    """Запустить серверный процесс тихо, с редиректом stdout в `log_path`, в `job`.

    `OSError` (файл журнала не открылся, `Popen` не смог создать процесс)
    уходит наружу как есть: перевод в `ServerError` — дело вызывающего слоя
    (`services`), контракт T-08 этот модуль не меняет. `JobError` (отказ
    `job.assign()`) тоже уходит наружу как есть, но не раньше, чем уже
    порождённый процесс будет убит — сервер без Job здесь не оставляем.

    Хендл журнала ребёнку — `_open_append_shared` (находка 1 ручного
    чек-листа T-10, см. докстринг модуля), не `Path.open("ab")`: `finally`
    вокруг `Popen` закрывает РОДИТЕЛЬСКУЮ копию дескриптора сразу после
    порождения процесса (успешного или нет) — тот же приём, что раньше
    давал выход из `with`, и та же безопасность: закрытие родительской
    стороны не трогает уже унаследованный дочерним процессом хендл
    (`Popen` дублирует его как наследуемый перед `CreateProcess`).
    """  # noqa: RUF002
    fd = _open_append_shared(log_path)
    try:
        process = subprocess.Popen(
            command.command_line,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=fd,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    finally:
        os.close(fd)
    # КРИТИЧНО ([Ф] находка задачи 1 T-10, см. докстринг модуля): assign
    # сразу после Popen, до того как ragent породит первого ребёнка.
    try:
        job.assign(int(process._handle))  # type: ignore[attr-defined]
    except JobError:
        # Круг исправлений 1 (ревью задачи 2, Important): без Job процесс  # noqa: RUF003
        # не даёт той гарантии смерти с лаунчером, ради которой весь этот  # noqa: RUF003
        # модуль существует — сервер без Job не оставляем. Popen.kill()
        # на Windows уже безопасен, если процесс успел умереть сам
        # (ловит PermissionError и сверяет код выхода — cpython subprocess).
        process.kill()
        raise
    pid = process.pid
    # Процесс брошен намеренно: жизнь сервера определяет Job, а не время  # noqa: RUF003
    # жизни Popen-объекта. Тот же приём, что в process.py::spawn — точечно
    # подавляем ResourceWarning «subprocess N is still running» при del.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        del process
    return pid
