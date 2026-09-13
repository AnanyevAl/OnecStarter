"""Окно процесса на передний план (спека v3, §4) — единственный Win32-модуль вехи.

Окно EDT принадлежит самому `1cedt.exe` ([Ф] спека §0: JVM грузится в процесс
лаунчера). Выбор окна среди перечисленных — чистая функция `pick_window`:
видимое, верхнего уровня (без владельца), с непустым заголовком — splash без
заголовка не подходит. `SetForegroundWindow` разрешён процессу, у которого
сейчас фокус ввода, — у нас, пользователь только что кликнул ([?] спека §0,
эксперимент 2). Не нашлось — `False`, вызывающий молчит: ложное «не запущен»
хуже отсутствия реакции.
"""  # noqa: RUF002

import ctypes
from collections.abc import Callable, Sequence
from ctypes import wintypes
from dataclasses import dataclass

__all__ = [
    "WindowInfo",
    "activate_window",
    "bring_to_front",
    "enumerate_windows",
    "pick_window",
]

_SW_RESTORE = 9
_GW_OWNER = 4

# Один WinDLL на модуль, argtypes/restype у каждой функции — та же гигиена  # noqa: RUF003
# ctypes, что в `platform_1c/job.py` (долг T-10). Без argtypes целый `hwnd`
# уходил бы 32-битным `long` (LLP64), без restype HWND возвращался бы `c_int`.
_WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.EnumWindows.restype = wintypes.BOOL
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.IsIconic.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    visible: bool
    title: str
    owner: int  # 0 — окно верхнего уровня


def pick_window(windows: Sequence[WindowInfo], pid: int) -> int | None:
    for window in windows:
        if (
            window.pid == pid
            and window.visible
            and window.owner == 0
            and window.title
        ):
            return window.hwnd
    return None


def enumerate_windows() -> list[WindowInfo]:
    found: list[WindowInfo] = []

    def visit(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = _user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        owner = _user32.GetWindow(hwnd, _GW_OWNER)
        found.append(
            WindowInfo(
                hwnd=hwnd,
                pid=pid.value,
                visible=bool(_user32.IsWindowVisible(hwnd)),
                title=buffer.value,
                owner=int(owner) if owner else 0,
            )
        )
        return True

    # Ссылка на callback живёт до возврата EnumWindows — локальная переменная,
    # не временный объект внутри вызова.
    callback = _WNDENUMPROC(visit)
    _user32.EnumWindows(callback, 0)
    return found


def bring_to_front(hwnd: int) -> bool:
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    return bool(_user32.SetForegroundWindow(hwnd))


def activate_window(
    pid: int,
    *,
    windows: Callable[[], list[WindowInfo]] = enumerate_windows,
    bring: Callable[[int], bool] = bring_to_front,
) -> bool:
    hwnd = pick_window(windows(), pid)
    if hwnd is None:
        return False
    return bring(hwnd)
