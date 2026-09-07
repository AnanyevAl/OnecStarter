"""Job Object на запуск профиля: дерево серверов умирает вместе с ним (T-12, спека §3).

Штатное `TerminateProcess` на `ragent` не убивает детей ([Ф] Б2 T-07) — но и
явный обход дерева не спасает от аварийного завершения лаунчера
(крах, `TaskKill /F`, отключение питания): рядом запущенные
`rmngr`/`rphost` в этом случае просто осиротеют и продолжат
жить. Windows Job Object с флагом `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
гасит всё дерево процессов, помещённых в Job, **при закрытии хендла
Job**. До T-12 хендл держался открытым до конца процесса лаунчера — один
Job на весь лаунчер. Начиная с T-12 Job заводится на каждый запуск
профиля отдельно: хендл закрывается явно, вызовом `close()`, из
`ServersWorkspace.stop()` («Погасить») или при гашении остатков
осиротевшего профиля. Гарантия §12.4 при этом не теряется: если лаунчер
умирает раньше собственного вызова `close()` (крах, `TaskKill /F`,
отключение питания), хендл Job закрывает сама ОС при завершении
процесса, который его держит, — и kill-on-close срабатывает так же, как
и раньше (**[Ф]** Б2 T-09 и п. 6 ручного чек-листа T-10: дерево гасло
при аварийном снятии самого лаунчера, без его собственного `close()`;
долг T-12, п. 14 — абзац стоял без метки достоверности).

Структуры ctypes и последовательность вызовов (`CreateJobObjectW` →
`SetInformationJobObject` → `AssignProcessToJobObject`) — дословно из
эталона `e:\\tmp\\t09\\b2_job.py`, проверенного живым деревом `ragent`
([Ф] Б2 T-09: закрытие хендла Job погасило родителя и внука целиком;
кластер пережил это без порчи файлов реестра).

[Ф] 29.08.2026 (проба `QueryInformationJobObject(JobObjectBasicProcessIdList)`
на этой машине, задача 1 T-12): список отдаёт PID всего дерева процессов,
СЕЙЧАС находящихся в Job — включая `conhost` и прочих посредников, не
только прямых детей. Если родителя (`ragent`) снять извне, как из
Диспетчера задач, остальное дерево остаётся в Job и продолжает быть
видно в списке; самого родителя в списке уже нет. `CloseHandle` на Job
с kill-on-close гасит все остатки разом, вне зависимости от того, жив
ли ещё исходный родитель. Пустой (только что созданный, ни разу не
получивший `assign`) Job на запрос списка отдаёт `(0, ())` — ноль
назначенных процессов, пустой список PID.
"""  # noqa: RUF002

import ctypes
from ctypes import wintypes
from typing import Any, Protocol

__all__ = ["Job", "JobError", "NullJob", "ServerJob"]

JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_ERROR_MORE_DATA = 234
_PID_LIST_INITIAL_CAPACITY = 64
# Долг T-12, п. 12: потолок попыток чтения списка PID. Ёмкость удваивается,
# поэтому реальному дереву хватает ≤ 2 итераций; восемь — запас, за которым
# начинается не рост дерева, а патология, и её честнее назвать отказом,  # noqa: RUF003
# чем удваивать буфер до MemoryError.
_PID_LIST_MAX_ATTEMPTS = 8

# Один WinDLL на модуль, argtypes/restype у каждой функции  # noqa: RUF003
# (долг T-10 «гигиена ctypes»).
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateJobObjectW.restype = wintypes.HANDLE
_k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_k32.SetInformationJobObject.restype = wintypes.BOOL
_k32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
]
_k32.AssignProcessToJobObject.restype = wintypes.BOOL
_k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_k32.QueryInformationJobObject.restype = wintypes.BOOL
_k32.QueryInformationJobObject.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


class IO_COUNTERS(ctypes.Structure):  # noqa: N801 — имя структуры WinAPI как есть
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _pid_list_type(capacity: int) -> Any:
    """`JOBOBJECT_BASIC_PROCESS_ID_LIST` с массивом на `capacity` записей (ULONG_PTR = c_size_t).

    Размер структуры зависит от `capacity`, известной только в момент
    вызова — обычный `ctypes.Structure` с фиксированным `_fields_` этого
    не умеет, поэтому класс собирается динамически при каждом вызове
    `pids()`. Возврат типизирован как `Any`: mypy strict не умеет вывести
    тип у структуры, чьи `_fields_` строятся во время выполнения.
    """  # noqa: RUF002

    class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * capacity),
        ]

    return JOBOBJECT_BASIC_PROCESS_ID_LIST


class JobError(Exception):
    """Отказ вызова WinAPI Job Object (создание, assign, чтение списка, закрытие)."""


class Job(Protocol):
    """Контракт, которым пользуется `spawn_server` и координатор (`services/servers.py`).

    `ServerJob` — настоящий Job Object; `NullJob` — заглушка для
    самопроверки собранного экземпляра и smoke-тестов, где реального
    процесса сервера нет и Job создавать незачем.
    """

    def assign(self, process_handle: int) -> None: ...
    def pids(self) -> tuple[int, ...]: ...
    def close(self) -> None: ...


class ServerJob:
    """Настоящий Job Object с kill-on-close. Единственное место с этой ctypes-механикой."""  # noqa: RUF002

    def __init__(self) -> None:
        self._handle: int | None = None

    def assign(self, process_handle: int) -> None:
        """Положить процесс в Job, создав Job при первом вызове.

        Ленивое создание — Job нужен, только если вообще что-то запускается;
        профиль без единого запущенного сервера не должен держать лишний хендл.
        """
        if self._handle is None:
            self._handle = self._create_job()
        if not _k32.AssignProcessToJobObject(self._handle, process_handle):
            error = ctypes.get_last_error()
            raise JobError(
                f"AssignProcessToJobObject не смог поместить процесс в Job: "
                f"GetLastError={error}"
            )

    def pids(self) -> tuple[int, ...]:
        """PID всех процессов, СЕЙЧАС находящихся в Job — всё дерево ([Ф] 29.08.2026,
        докстринг модуля).

        `()`, пока Job не создан (до первого `assign`) или после `close()`.
        Буфер `JOBOBJECT_BASIC_PROCESS_ID_LIST` стартует с ёмкости
        `_PID_LIST_INITIAL_CAPACITY` и растёт при `ERROR_MORE_DATA` (234) —
        [Д] в этой ситуации WinAPI отдаёт фактическое число процессов
        в `NumberOfAssignedProcesses`, буфер пересоздаётся под этот размер
        (с запасом от удвоения — дерево между двумя вызовами могло вырасти).

        Попыток не больше `_PID_LIST_MAX_ATTEMPTS` (долг T-12, п. 12):
        реальному дереву хватает ≤ 2, а бесконечное удвоение на
        патологическом `ERROR_MORE_DATA` кончилось бы `MemoryError`
        вместо внятного отказа. Исчерпание потолка — `JobError`.
        """  # noqa: RUF002
        if self._handle is None:
            return ()
        capacity = _PID_LIST_INITIAL_CAPACITY
        for _attempt in range(_PID_LIST_MAX_ATTEMPTS):
            buffer: Any = _pid_list_type(capacity)()
            ok = _k32.QueryInformationJobObject(
                self._handle, JobObjectBasicProcessIdList,
                ctypes.byref(buffer), ctypes.sizeof(buffer), None,
            )
            if ok:
                count = int(buffer.NumberOfProcessIdsInList)
                return tuple(int(buffer.ProcessIdList[i]) for i in range(count))
            error = ctypes.get_last_error()
            if error != _ERROR_MORE_DATA:
                raise JobError(
                    f"QueryInformationJobObject не смог прочитать список процессов Job: "
                    f"GetLastError={error}"
                )
            capacity = max(capacity * 2, int(buffer.NumberOfAssignedProcesses))
        raise JobError(
            f"QueryInformationJobObject не отдал список процессов Job "
            f"за {_PID_LIST_MAX_ATTEMPTS} попыток (последняя ёмкость {capacity})"
        )

    def close(self) -> None:
        """Закрыть хендл Job — kill-on-close гасит всё, что в нём ([Ф] 29.08.2026).

        Идемпотентно только на успешном пути: если Job не создан или уже
        закрыт, второй и любой следующий вызов — no-op, без исключения.
        После УСПЕШНОГО закрытия `pids()` снова отдаёт `()`.

        Если `CloseHandle` отказал, `_handle` НЕ обнуляется (ревью задачи 1
        T-12, Important 1): неудачный вызов не должен выглядеть как
        успешный — `pids()` обязан по-прежнему отвечать по
        живому хендлу (координатору `services` это нужно, чтобы после
        отказавшего `close()` остатки дерева оставались видны), а сам
        `close()` остаётся вызываемым повторно, а не превращается в no-op
        из-за потерянного хендла.
        """  # noqa: RUF002
        if self._handle is None:
            return
        handle = self._handle
        if not _k32.CloseHandle(handle):
            error = ctypes.get_last_error()
            raise JobError(f"CloseHandle не смог закрыть Job: GetLastError={error}")
        self._handle = None

    @staticmethod
    def _create_job() -> int:
        handle = _k32.CreateJobObjectW(None, None)
        if not handle:
            error = ctypes.get_last_error()
            raise JobError(f"CreateJobObjectW не смог создать Job: GetLastError={error}")

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _k32.SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            error = ctypes.get_last_error()
            _k32.CloseHandle(handle)
            raise JobError(
                f"SetInformationJobObject не смог включить kill-on-close: "
                f"GetLastError={error}"
            )
        return int(handle)


class NullJob:
    """Job, которого нет: для самопроверки собранного экземпляра и smoke-тестов."""

    def assign(self, process_handle: int) -> None:
        pass

    def pids(self) -> tuple[int, ...]:
        return ()

    def close(self) -> None:
        pass
