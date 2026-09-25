"""Список процессов одним снимком Windows — без открытия процессов.

Зачем отдельно от `psutil`: `Process.name()` на Windows читает путь образа,
а это обращение к процессу. На сервере заказчика каждое такое обращение
проходит через агент безопасности и стоит ~15 мс, отчего обход 793 процессов
занимает там 12 секунд в одном потоке ([Ф] замер 25.09.2026, спека 3.2.2
«снимок процессов» §0). Снимок Toolhelp не открывает ни одного процесса
и стоит на том же сервере 28,7 мс.

Единственное место в проекте с Toolhelp. Без Qt (инвариант 1) и без состояния.
"""  # noqa: RUF002

import ctypes
from ctypes import wintypes

__all__ = [
    "INVALID_HANDLE_VALUE",
    "SnapshotError",
    "snapshot_all",
]

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260


class SnapshotError(OSError):
    """Снимок не удался. Вызывающий решает, что показать пользователю."""


class PROCESSENTRY32W(ctypes.Structure):
    """Запись снимка. Поля и порядок — как в tlhelp32.h."""

    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        # ULONG_PTR: на x64 это 8 байт, и c_size_t даёт правильный размер
        # структуры. Ошибка здесь не уронила бы снимок, а сдвинула все  # noqa: RUF003
        # последующие поля — от этого класса ошибки страхует тест сверки
        # с psutil, а не проверка внутри кода.  # noqa: RUF003
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    )


def _kernel32() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    dll.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    dll.Process32FirstW.restype = wintypes.BOOL
    dll.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    dll.Process32NextW.restype = wintypes.BOOL
    dll.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    dll.CloseHandle.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = (wintypes.HANDLE,)
    return dll


def snapshot_all() -> list[tuple[int, str]]:
    """PID и имя каждого процесса. `SnapshotError` — снимок не удался."""
    dll = _kernel32()
    snapshot = dll.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise SnapshotError(ctypes.get_last_error(), "снимок процессов не создан")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        found: list[tuple[int, str]] = []
        ok = dll.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            found.append((entry.th32ProcessID, entry.szExeFile))
            ok = dll.Process32NextW(snapshot, ctypes.byref(entry))
        return found
    finally:
        dll.CloseHandle(snapshot)
