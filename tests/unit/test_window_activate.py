"""Активация окна по PID: выбор окна — чистая функция; Win32-часть — эксперимент 2 (спека §10)."""

from onecstarter.platform_1c.window_activate import (
    WindowInfo,
    activate_window,
    pick_window,
)

MAIN = WindowInfo(hwnd=10, pid=42, visible=True, title="intertop — 1C:EDT", owner=0)
SPLASH = WindowInfo(hwnd=11, pid=42, visible=True, title="", owner=0)
TOOLTIP = WindowInfo(hwnd=12, pid=42, visible=True, title="tip", owner=10)
HIDDEN = WindowInfo(hwnd=13, pid=42, visible=False, title="hidden", owner=0)
OTHER = WindowInfo(hwnd=20, pid=7, visible=True, title="other", owner=0)


class TestPickWindow:
    def test_visible_titled_top_level_of_pid(self) -> None:
        assert pick_window([OTHER, SPLASH, TOOLTIP, HIDDEN, MAIN], 42) == 10

    def test_splash_without_title_not_picked(self) -> None:
        assert pick_window([SPLASH], 42) is None

    def test_owned_window_not_picked(self) -> None:
        assert pick_window([TOOLTIP], 42) is None

    def test_other_pid_not_picked(self) -> None:
        assert pick_window([OTHER], 42) is None

    def test_empty(self) -> None:
        assert pick_window([], 42) is None


class TestActivateWindow:
    def test_brings_picked_window(self) -> None:
        brought: list[int] = []

        def bring(hwnd: int) -> bool:
            brought.append(hwnd)
            return True

        assert (
            activate_window(42, windows=lambda: [SPLASH, MAIN], bring=bring)
            is True
        )
        assert brought == [10]

    def test_no_window_is_false_without_bring(self) -> None:
        brought: list[int] = []

        def bring(hwnd: int) -> bool:
            brought.append(hwnd)
            return True

        assert (
            activate_window(42, windows=lambda: [SPLASH], bring=bring)
            is False
        )
        assert brought == []

    def test_bring_failure_is_false(self) -> None:
        assert (
            activate_window(
                42, windows=lambda: [MAIN], bring=lambda h: False
            )
            is False
        )
