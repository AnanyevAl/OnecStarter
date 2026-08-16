from typing import Any

from onecstarter.ui.hotkey import HOTKEY_ID, WM_HOTKEY, GlobalHotkey


def _hotkey(
    register_result: int = 1,
) -> tuple[GlobalHotkey, dict[str, list[Any]], list[int]]:
    calls: dict[str, list[Any]] = {"register": [], "unregister": []}

    def register(hwnd: int | None, hotkey_id: int, modifiers: int, vk: int) -> int:
        calls["register"].append((hotkey_id, modifiers, vk))
        return register_result

    def unregister(hwnd: int | None, hotkey_id: int) -> int:
        calls["unregister"].append(hotkey_id)
        return 1

    fired: list[int] = []
    hotkey = GlobalHotkey(lambda: fired.append(1), register=register, unregister=unregister)
    return hotkey, calls, fired


def test_registration_success_and_dispatch():
    hotkey, calls, fired = _hotkey()
    assert hotkey.registered
    assert calls["register"][0][0] == HOTKEY_ID
    assert hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == [1]


def test_foreign_messages_are_ignored():
    hotkey, _, fired = _hotkey()
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID + 1)
    assert not hotkey.handle(0x0400, HOTKEY_ID)
    assert fired == []


def test_busy_hotkey_does_not_break_startup():
    hotkey, _, fired = _hotkey(register_result=0)
    assert not hotkey.registered
    # Сообщение всё равно не наше — колбэк не дёргается.
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == []


def test_dispose_unregisters_only_when_registered():
    hotkey, calls, _ = _hotkey()
    hotkey.dispose()
    assert calls["unregister"] == [HOTKEY_ID]
    busy, busy_calls, _ = _hotkey(register_result=0)
    busy.dispose()
    assert busy_calls["unregister"] == []
