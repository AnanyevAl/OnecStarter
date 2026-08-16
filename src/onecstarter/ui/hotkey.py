"""Глобальный хоткей Ctrl+Alt+B: поднять окно с фокусом в поиске.

Windows-only (v1 — только Windows, requirements.md §4): RegisterHotKey +
WM_HOTKEY через QAbstractNativeEventFilter. Функции user32 инжектируются —
тесты не трогают реальную регистрацию. Занятое сочетание не роняет
приложение: registered=False, всё остальное работает ([Р] спека 4a, §3).
"""  # noqa: RUF002

import ctypes
import typing
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MODIFIERS = MOD_CONTROL | MOD_ALT
VK_B = 0x42
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xA11C


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(
        self,
        callback: Callable[[], None],
        *,
        register: Callable[..., int] | None = None,
        unregister: Callable[..., int] | None = None,
    ) -> None:
        super().__init__()
        self._callback = callback
        if register is None or unregister is None:
            user32 = ctypes.windll.user32
            register = user32.RegisterHotKey
            unregister = user32.UnregisterHotKey
        self._unregister = unregister
        self.registered = bool(register(None, HOTKEY_ID, MODIFIERS, VK_B))

    def handle(self, message_id: int, wparam: int) -> bool:
        """Чистая часть диспетчеризации — тестируется без нативных событий."""
        if not self.registered:
            return False
        if message_id == WM_HOTKEY and wparam == HOTKEY_ID:
            self._callback()
            return True
        return False

    @typing.override
    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if self.handle(msg.message, msg.wParam):
                return True, 0
        return False, 0

    def dispose(self) -> None:
        if self.registered:
            self._unregister(None, HOTKEY_ID)
            self.registered = False
