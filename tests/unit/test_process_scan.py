"""Тесты сканера процессов: `NullScanner` и `PsutilScanner`.

Живой ragent/1С не участвует (правило проекта — не запускать процессы 1С):
интеграционный тест поднимает подставной python-процесс с ragent-подобным
хвостом argv (`-port 9999 -d <tmp_path>`) и сканирует именно его.
"""  # noqa: RUF002

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

from onecstarter.platform_1c.process_scan import NullScanner, PsutilScanner


class TestNullScanner:
    def test_snapshot_is_always_empty(self) -> None:
        assert NullScanner().snapshot(frozenset({"ragent.exe", "rmngr.exe"})) == []


class TestPsutilScanner:
    @pytest.fixture
    def fake_process(self, tmp_path: Path) -> Iterator[psutil.Process]:
        popen = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
                "-port",
                "9999",
                "-d",
                str(tmp_path),
            ]
        )
        try:
            yield psutil.Process(popen.pid)
        finally:
            popen.kill()
            popen.wait()

    def test_finds_fake_process_by_own_name(self, fake_process: psutil.Process) -> None:
        # Имя процесса python.exe/python3.13.exe зависит от машины — берём
        # фактическое имя у самого процесса, а не угадываем интерпретатор.  # noqa: RUF003
        name = fake_process.name().casefold()
        result = PsutilScanner().snapshot(frozenset({name}))
        found = next((p for p in result if p.pid == fake_process.pid), None)
        assert found is not None
        assert found.argv is not None
        assert "-port" in found.argv
        assert "9999" in found.argv

    def test_unrelated_name_does_not_match_fake_process(
        self, fake_process: psutil.Process
    ) -> None:
        result = PsutilScanner().snapshot(frozenset({"нет-такого.exe"}))
        assert all(p.pid != fake_process.pid for p in result)
