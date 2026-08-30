"""Тесты `run_elevated` на фейковом `shell_execute`.

Настоящий UAC-диалог и `ShellExecuteExW` в тестах не трогаются — только
инъекция `shell_execute`, как задумано интерфейсом модуля.
"""

import pytest

from onecstarter.platform_1c.elevation import ElevationDeclinedError, run_elevated


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
