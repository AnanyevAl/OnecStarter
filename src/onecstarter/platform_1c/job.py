"""Job Object: дерево серверов умирает вместе с лаунчером ([Ф] Б1/Б2 T-09).

Штатное `TerminateProcess` на `ragent` не убивает детей ([Ф] Б2,
`process_control.py`) — но и явный обход дерева не спасает от аварийного
завершения лаунчера (крах, `TaskKill /F`, отключение питания): рядом
запущенные `rmngr`/`rphost` в этом случае просто осиротеют и продолжат
жить. Windows Job Object с флагом `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
гасит всё дерево процессов, помещённых в Job, **при закрытии хендла
Job** — а хендл гарантированно закрывается самой ОС при смерти процесса,
который его держит (лаунчера), независимо от причины смерти. Поэтому
`ServerJob` держит хендл открытым до конца процесса лаунчера намеренно:
досрочное закрытие — единственное действие, которое погасит дерево, и
это не должно происходить иначе как через смерть самого лаунчера.

Структуры ctypes и последовательность вызовов (`CreateJobObjectW` →
`SetInformationJobObject` → `AssignProcessToJobObject`) — дословно из
эталона `e:\\tmp\\t09\\b2_job.py`, проверенного живым деревом `ragent`
([Ф] Б2 T-09: закрытие хендла Job погасило родителя и внука целиком;
кластер пережил это без порчи файлов реестра).
"""  # noqa: RUF002

import ctypes
from ctypes import wintypes
from typing import Protocol

__all__ = ["JobError", "NullJob", "ServerJob"]

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


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


class JobError(Exception):
    """Отказ вызова WinAPI при создании Job или помещении в него процесса."""


class Job(Protocol):
    def assign(self, process_handle: int) -> None: ...


class ServerJob:
    """Настоящий Job Object с kill-on-close. Единственное место с этой ctypes-механикой."""  # noqa: RUF002

    def __init__(self) -> None:
        self._handle: int | None = None

    def assign(self, process_handle: int) -> None:
        """Положить процесс в Job, создав Job при первом вызове.

        Ленивое создание — Job нужен, только если вообще что-то запускается;
        лаунчер без единого сервера не должен держать лишний хендл.
        """
        if self._handle is None:
            self._handle = self._create_job()
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not k32.AssignProcessToJobObject(self._handle, process_handle):
            error = ctypes.get_last_error()
            raise JobError(
                f"AssignProcessToJobObject не смог поместить процесс в Job: "
                f"GetLastError={error}"
            )

    @staticmethod
    def _create_job() -> int:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.CreateJobObjectW(None, None)
        if not handle:
            error = ctypes.get_last_error()
            raise JobError(f"CreateJobObjectW не смог создать Job: GetLastError={error}")

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = k32.SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            error = ctypes.get_last_error()
            k32.CloseHandle(handle)
            raise JobError(
                f"SetInformationJobObject не смог включить kill-on-close: "
                f"GetLastError={error}"
            )
        return int(handle)

    def _close_for_tests(self) -> None:
        """Закрыть хендл Job досрочно — только для тестов.

        В проде не вызывается: хендл обязан жить до конца процесса лаунчера,
        и его закрытие ОС при смерти лаунчера — единственная гарантия,
        на которой стоит этот модуль (см. докстринг модуля).
        """  # noqa: RUF002
        if self._handle is not None:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CloseHandle(self._handle)
            self._handle = None


class NullJob:
    """Job, которого нет: для самопроверки собранного экземпляра и smoke-тестов."""

    def assign(self, process_handle: int) -> None:
        pass
