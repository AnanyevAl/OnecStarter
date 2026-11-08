"""Признак «программа уже запущена» — именованный мьютекс Windows (T-39, спека 3.2.5 §6.2).

Без Qt (инвариант 1). Мьютекс создаёт ядро атомарно, поэтому два одновременных
запуска не проходят оба; при падении процесса ОС освобождает его сама. `Local\\` —
пространство сеанса ([Д] документация Windows): сеансы терминального сервера
не пересекаются. Имя — хэш учётной записи и сеанса, чтобы имя пользователя
не попадало в имена объектов ядра; session id нужен и каналу (`ui/single_instance.py`):
имена каналов в Windows общие на машину ([Д] документация Windows, именованные каналы).
"""  # noqa: RUF002

import ctypes
import hashlib
from collections.abc import Mapping
from ctypes import wintypes

__all__ = [
    "ERROR_ACCESS_DENIED",
    "ERROR_ALREADY_EXISTS",
    "InstanceLock",
    "acquire",
    "allow_foreground_for_any",
    "current_session_id",
    "instance_id",
]

ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183
_ASFW_ANY = 0xFFFFFFFF  # (DWORD)-1

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.GetCurrentProcessId.restype = wintypes.DWORD
_kernel32.GetCurrentProcessId.argtypes = []
_kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
_kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.AllowSetForegroundWindow.restype = wintypes.BOOL
_user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]


def instance_id(env: Mapping[str, str], session_id: int) -> str:
    """Имя признака и канала: учётная запись `USERDOMAIN\\USERNAME` и номер сеанса.

    Имя — контракт между версиями начиная с 3.2.5, менять нельзя: иначе версии
    с разными формулами не увидят признак друг друга и запустятся одновременно.
    Обе части приводятся `casefold()` до склейки: Windows не различает регистр
    в имени учётной записи, а переменные окружения могут прийти в разном написании.
    """  # noqa: RUF002
    domain = env.get("USERDOMAIN", "").casefold()
    user = env.get("USERNAME", "").casefold()
    account = f"{domain}\\{user}|{session_id}"
    return "OneCStarter-" + hashlib.sha256(account.encode("utf-8")).hexdigest()[:16]


def current_session_id() -> int:
    session = wintypes.DWORD()
    if not _kernel32.ProcessIdToSessionId(_kernel32.GetCurrentProcessId(), ctypes.byref(session)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(session.value)


class InstanceLock:
    """Захваченный признак; держится до `release()` или до конца процесса."""

    def __init__(self, handle: int) -> None:
        self._handle = handle

    def release(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = 0


def acquire(name: str) -> InstanceLock | None:
    """Захватить признак. `None` — его держит другой экземпляр (или этот же процесс).

    Отказ `CreateMutexW` с `ERROR_ACCESS_DENIED` — тоже «занято»: мьютекс есть,
    но создан процессом с другими правами (например, OneCStarter «от имени
    администратора»), и открыть его нельзя ([?] известное поведение Windows,
    вживую не проверено). Остальные отказы — `OSError`.
    """  # noqa: RUF002
    # Последняя ошибка обнуляется явно: при создании нового мьютекса
    # CreateMutexW не обязана её сбрасывать.
    ctypes.set_last_error(0)
    handle = _kernel32.CreateMutexW(None, False, f"Local\\{name}")
    error = ctypes.get_last_error()
    if not handle:
        if error == ERROR_ACCESS_DENIED:
            return None
        raise ctypes.WinError(error)
    if error == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return None
    return InstanceLock(handle)


def allow_foreground_for_any() -> None:
    """Отдать право переднего плана: зовёт второй экземпляр перед просьбой к первому.

    Отказ не исключение — повод косметический: окно в худшем случае замигает
    на панели задач вместо выхода вперёд ([?] спека §6.2).
    """
    _user32.AllowSetForegroundWindow(_ASFW_ANY)
