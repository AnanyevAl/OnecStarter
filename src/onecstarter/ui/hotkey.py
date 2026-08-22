"""Глобальный хоткей: поднять окно с фокусом в поиске.

Windows-only (v1 — только Windows, requirements.md §4): RegisterHotKey +
WM_HOTKEY через QAbstractNativeEventFilter. Функции user32 инжектируются —
тесты не трогают реальную регистрацию.

Сочетание приходит из настроек и меняется на лету (спека §4.2), поэтому
конструктор ничего не регистрирует: регистрацию ставит `rebind`. Занятое
сочетание не роняет приложение — `rebind` отдаёт False, всё остальное
работает ([Р] спека 4a, §3).

**[Проверено, 19.08.2026, эксперимент §7 спеки вехи]** Перерегистрация
в одном процессе работает, освобождение сочетания мгновенно, доставка
WM_HOTKEY после смены сохраняется.
"""  # noqa: RUF002

import ctypes
import typing
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

from onecstarter.services.hotkeys import HotkeySpec

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
        self._register = register
        self._unregister = unregister
        self.registered = False

    def rebind(self, spec: HotkeySpec | None) -> bool:
        """Снять прежнюю регистрацию и повесить новую. False — сочетание занято.

        `None` — хоткей выключен: снимаем и ничего не регистрируем, ответ True
        (выключение удалось). Прежнее снимается ДО попытки нового, в том числе
        когда новое сочетание совпадает со старым: иначе мы сами держали бы
        его занятым и отказали бы себе же.
        """  # noqa: RUF002
        if self.registered:
            self._unregister(None, HOTKEY_ID)
            self.registered = False
        if spec is None:
            return True
        self.registered = bool(self._register(None, HOTKEY_ID, spec.modifiers, spec.vk))
        return self.registered

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
