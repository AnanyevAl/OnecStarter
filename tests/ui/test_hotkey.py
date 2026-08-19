from typing import Any

from onecstarter.services.hotkeys import parse_hotkey
from onecstarter.ui.hotkey import HOTKEY_ID, WM_HOTKEY, GlobalHotkey

CTRL_ALT_B = parse_hotkey("Ctrl+Alt+B")
CTRL_ALT_Y = parse_hotkey("Ctrl+Alt+Y")


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


def test_constructor_registers_nothing() -> None:
    """Сочетание приходит из настроек — регистрировать в конструкторе нечего."""
    hotkey, calls, _ = _hotkey()
    assert not hotkey.registered
    assert calls["register"] == []


def test_rebind_registers_and_dispatches() -> None:
    hotkey, calls, fired = _hotkey()
    assert CTRL_ALT_B is not None
    assert hotkey.rebind(CTRL_ALT_B) is True
    assert hotkey.registered
    assert calls["register"] == [(HOTKEY_ID, CTRL_ALT_B.modifiers, CTRL_ALT_B.vk)]
    assert hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == [1]


def test_rebind_releases_previous_registration() -> None:
    """Снять прежнее до регистрации нового — иначе сочетание останется занятым нами.

    **[Проверено, 19.08.2026, эксперимент §7 спеки]**: освобождение мгновенно,
    то же сочетание тут же берётся другой регистрацией.
    """
    hotkey, calls, _ = _hotkey()
    assert CTRL_ALT_B is not None
    assert CTRL_ALT_Y is not None
    hotkey.rebind(CTRL_ALT_B)
    hotkey.rebind(CTRL_ALT_Y)
    assert calls["unregister"] == [HOTKEY_ID]
    assert calls["register"][-1] == (HOTKEY_ID, CTRL_ALT_Y.modifiers, CTRL_ALT_Y.vk)


def test_rebind_to_none_disables() -> None:
    """Защитный: выключенный хоткей не регистрируется вовсе (спека §4.1).

    Мутация: убрать ранний выход по `spec is None` — тест обязан упасть
    на непустом `calls["register"]`.
    """
    hotkey, calls, fired = _hotkey()
    assert CTRL_ALT_B is not None
    hotkey.rebind(CTRL_ALT_B)
    calls["register"].clear()

    assert hotkey.rebind(None) is True

    assert not hotkey.registered
    assert calls["register"] == []
    assert calls["unregister"] == [HOTKEY_ID]
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == []


def test_busy_combination_reports_false_and_keeps_app_alive() -> None:
    hotkey, _, fired = _hotkey(register_result=0)
    assert CTRL_ALT_B is not None
    assert hotkey.rebind(CTRL_ALT_B) is False
    assert not hotkey.registered
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == []


def test_foreign_messages_are_ignored() -> None:
    hotkey, _, fired = _hotkey()
    assert CTRL_ALT_B is not None
    hotkey.rebind(CTRL_ALT_B)
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID + 1)
    assert not hotkey.handle(0x0400, HOTKEY_ID)
    assert fired == []


def test_dispose_unregisters_only_when_registered() -> None:
    hotkey, calls, _ = _hotkey()
    assert CTRL_ALT_B is not None
    hotkey.rebind(CTRL_ALT_B)
    hotkey.dispose()
    assert calls["unregister"] == [HOTKEY_ID]

    busy, busy_calls, _ = _hotkey(register_result=0)
    busy.rebind(CTRL_ALT_B)
    busy.dispose()
    assert busy_calls["unregister"] == []
