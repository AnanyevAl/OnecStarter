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
