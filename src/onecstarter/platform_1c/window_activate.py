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
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[WindowInfo] = []

    def visit(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        found.append(
            WindowInfo(
                hwnd=hwnd,
                pid=pid.value,
                visible=bool(user32.IsWindowVisible(hwnd)),
                title=buffer.value,
                owner=int(user32.GetWindow(hwnd, 4) or 0),  # GW_OWNER = 4
            )
        )
        return True

    user32.EnumWindows(proc_type(visit), 0)
    return found


def bring_to_front(hwnd: int) -> bool:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _SW_RESTORE)
    return bool(user32.SetForegroundWindow(hwnd))


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
