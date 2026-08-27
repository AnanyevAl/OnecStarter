"""Повышение прав для регистрации консоли администрирования кластера.

`ShellExecuteExW` с `lpVerb="runas"` — штатный способ Windows поднять
UAC-диалог без собственного окна и без обхода политики системы.
`SEE_MASK_NOCLOSEPROCESS` возвращает хендл процесса — без этого флага
`ShellExecuteExW` хендл не отдаёт, и дождаться завершения `regsvr32`
и забрать его код возврата было бы нечем.

Отказ пользователя в диалоге UAC — не ошибка нашего кода, а решение
человека: `ShellExecuteExW` возвращает `FALSE`, `GetLastError() ==
ERROR_CANCELLED` (1223) ([Ф] Г2, 26.08.2026, `docs/research/
t07-protocol.md` — «отказ UAC ловится на нашей стороне как
ERROR_CANCELLED»). `ElevationDeclinedError` даёт вызывающему коду отличить
этот случай от прочих сбоев запуска.

`shell_execute` — инъекция для тестов (тот же приём, что `register`/
`unregister` в `ui/hotkey.py` и `Registry` в `services/autostart.py`):
вся ctypes-механика подменяется одним вызовом `(executable, arguments)
-> код возврата`; тестовый колбэк, поднимающий `ElevationDeclinedError`,
имитирует отказ UAC без настоящего диалога.
"""  # noqa: RUF002

import ctypes
from collections.abc import Callable
from ctypes import wintypes

__all__ = ["ElevationDeclinedError", "run_elevated"]

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_SHOWNORMAL = 1
_INFINITE = 0xFFFFFFFF
_ERROR_CANCELLED = 1223


class ElevationDeclinedError(Exception):
    """Пользователь отказал в диалоге UAC."""


class _ShellExecuteInfoW(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),  # часть union {hIcon; hMonitor} — размер тот же
        ("hProcess", wintypes.HANDLE),
    )


def _default_shell_execute(executable: str, arguments: str) -> int:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    info = _ShellExecuteInfoW()
    info.cbSize = ctypes.sizeof(_ShellExecuteInfoW)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.hwnd = None
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = arguments
    info.lpDirectory = None
    info.nShow = _SW_SHOWNORMAL
    info.hInstApp = None
    info.lpIDList = None
    info.lpClass = None
    info.hkeyClass = None
    info.dwHotKey = 0
    info.hIcon = None
    info.hProcess = None

    ok = shell32.ShellExecuteExW(ctypes.byref(info))
    if not ok:
        error = ctypes.get_last_error()
        if error == _ERROR_CANCELLED:
            raise ElevationDeclinedError(
                f"пользователь отказал в повышении прав для {executable}"
            )
        raise OSError(error, f"ShellExecuteExW не смог запустить {executable}")

    kernel32.WaitForSingleObject(info.hProcess, _INFINITE)
    exit_code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code))
    kernel32.CloseHandle(info.hProcess)
    return exit_code.value


def run_elevated(
    executable: str,
    arguments: str,
    *,
    shell_execute: Callable[[str, str], int] | None = None,
) -> int:
    """Запустить `executable arguments` с повышением прав и дождаться кода возврата.

    `shell_execute=None` (по умолчанию, боевой путь) — настоящий `ShellExecuteExW`
    с UAC. Задан — вызывается вместо всей ctypes-механики (для тестов).
    """  # noqa: RUF002
    execute = shell_execute if shell_execute is not None else _default_shell_execute
    return execute(executable, arguments)
