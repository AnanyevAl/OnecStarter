import sys
import time
from pathlib import Path

import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.process import spawn


def test_spawn_runs_detached_program(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    script = tmp_path / "stub.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ok')\n",
        encoding="utf-8",
    )
    command = LaunchCommand(executable=Path(sys.executable), arguments=f'"{script}"')
    pid = spawn(command)
    assert pid > 0
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.05)
    assert marker.exists(), "процесс-заглушка не отработал за 10 секунд"
    assert marker.read_text(encoding="utf-8") == "ok"


def test_spawn_quotes_executable_with_spaces(tmp_path: Path) -> None:
    # Косвенная проверка формы командной строки: exe в кавычках + пробел.
    exe = Path(r"C:\Program Files\1cv8\bin\1cv8c.exe")
    command = LaunchCommand(executable=exe, arguments="ENTERPRISE")
    assert command.command_line == r'"C:\Program Files\1cv8\bin\1cv8c.exe" ENTERPRISE'


def test_spawn_runs_without_the_inherited_dll_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Н1: клиент 1С не должен грузить DLL из `_internal` (он держал бы их до закрытия)."""  # noqa: RUF002
    from onecstarter.platform_1c import dll_search, process

    state: dict[str, str | None] = {"dir": r"C:\app\_internal"}
    monkeypatch.setattr(dll_search, "get_dll_directory", lambda: state["dir"])
    monkeypatch.setattr(dll_search, "set_dll_directory", lambda p: state.__setitem__("dir", p))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    seen: list[str | None] = []

    class FakePopen:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            seen.append(state["dir"])
            self.pid = 42

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)  # type: ignore[attr-defined]
    assert spawn(LaunchCommand(executable=Path("C:/x.exe"), arguments="")) == 42
    assert seen == [None]
    assert state["dir"] == r"C:\app\_internal"
