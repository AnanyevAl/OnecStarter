"""Тесты `run_elevated` на фейковом `shell_execute`.

Настоящий UAC-диалог и `ShellExecuteExW` в тестах не трогаются — только
инъекция `shell_execute`, как задумано интерфейсом модуля.
"""

from pathlib import Path

import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.elevation import (
    ElevationDeclinedError,
    run_elevated,
    spawn_elevated,
)

COMMAND = LaunchCommand(Path(r"C:\1cv8\8.3.25\bin\1cv8.exe"), 'DESIGNER /IBName"База"')


class TestRunElevated:
    @pytest.mark.parametrize("code", [0, 3])
    def test_return_code_passes_through(self, code: int) -> None:
        result = run_elevated(
            "regsvr32", '/s "C:\\dll"', shell_execute=lambda _exe, _args: code
        )
        assert result == code

    def test_shell_execute_receives_executable_and_arguments(self) -> None:
        seen: list[tuple[str, str]] = []

        def fake(executable: str, arguments: str) -> int:
            seen.append((executable, arguments))
            return 0

        run_elevated("regsvr32", '/s "C:\\dll"', shell_execute=fake)
        assert seen == [("regsvr32", '/s "C:\\dll"')]

    def test_declined_callback_propagates(self) -> None:
        def declining(_executable: str, _arguments: str) -> int:
            raise ElevationDeclinedError("пользователь отказал")

        with pytest.raises(ElevationDeclinedError):
            run_elevated("regsvr32", '/s "C:\\dll"', shell_execute=declining)


class TestSpawnElevated:
    def test_passes_executable_and_arguments_and_returns_pid(self) -> None:
        seen: list[tuple[str, str]] = []

        def fake(executable: str, arguments: str) -> int:
            seen.append((executable, arguments))
            return 4321

        assert spawn_elevated(COMMAND, shell_execute=fake) == 4321
        assert seen == [(r"C:\1cv8\8.3.25\bin\1cv8.exe", 'DESIGNER /IBName"База"')]

    def test_declined_propagates(self) -> None:
        def declining(_executable: str, _arguments: str) -> int:
            raise ElevationDeclinedError("пользователь отказал")

        with pytest.raises(ElevationDeclinedError):
            spawn_elevated(COMMAND, shell_execute=declining)


def test_shell_execute_runs_without_the_inherited_dll_directory_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Н1, ревью задачи 10, п. 2: `ShellExecuteExW` с `runas` — тоже без `_internal`.

    Допущение «процесс создаёт служба согласия» не проверено: при уже повышенных правах
    оболочка может создать процесс из нашего — путь DLL и окружение очищаются и здесь.
    """  # noqa: RUF002
    import ctypes
    import os
    import sys

    from onecstarter.platform_1c import dll_search, elevation

    bundle = r"C:\app\_internal"
    state: dict[str, str | None] = {"dir": bundle}
    monkeypatch.setattr(dll_search, "get_dll_directory", lambda: state["dir"])
    monkeypatch.setattr(dll_search, "set_dll_directory", lambda p: state.__setitem__("dir", p))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", bundle, raising=False)
    path = os.pathsep.join([bundle, r"C:\Windows\system32"])
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("QT_PLUGIN_PATH", bundle + r"\PySide6\plugins")
    seen: list[tuple[str | None, str, str | None]] = []

    class FakeShell32:
        def ShellExecuteExW(self, _info: object) -> int:  # noqa: N802 — имя функции WinAPI
            seen.append((state["dir"], os.environ["PATH"], os.environ.get("QT_PLUGIN_PATH")))
            return 1

    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: FakeShell32())
    assert elevation._start("regsvr32", r'/s "C:\dll"') == 0
    assert seen == [(None, r"C:\Windows\system32", None)]
    assert state["dir"] == bundle
    assert os.environ["PATH"] == path
    assert os.environ["QT_PLUGIN_PATH"] == bundle + r"\PySide6\plugins"
