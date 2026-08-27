"""Тесты остановки дерева процессов: `NullControl` и `PsutilControl`.

Живой ragent/1С не участвует (правило проекта — не запускать процессы 1С):
интеграционные тесты поднимают подставной python-процесс (`Popen sleep 30`)
и завершают/сканируют именно его. `finally` фикстур подчищает процесс, если
`terminate` его не убил (ЗАЩИТНЫЙ ТЕСТ) или тест упал раньше.
"""  # noqa: RUF002

import os
import subprocess
import sys
from collections.abc import Iterator

import psutil
import pytest

from onecstarter.platform_1c.process_control import (
    NullControl,
    ProcessMismatchError,
    PsutilControl,
)


class TestNullControl:
    def test_children_is_always_empty(self) -> None:
        assert NullControl().children(1234) == []

    def test_terminate_is_noop(self) -> None:
        NullControl().terminate(1234, 0.0)  # не поднимает исключение


class TestPsutilControlChildren:
    @pytest.fixture
    def fake_child(self) -> Iterator[subprocess.Popen[bytes]]:
        popen = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            yield popen
        finally:
            popen.kill()
            popen.wait()

    def test_finds_fake_child_of_current_process(
        self, fake_child: subprocess.Popen[bytes]
    ) -> None:
        result = PsutilControl().children(os.getpid())
        assert any(child.pid == fake_child.pid for child in result)

    def test_children_of_nonexistent_pid_is_empty(self) -> None:
        popen = subprocess.Popen([sys.executable, "-c", "pass"])
        popen.wait()
        # PID теперь свободен (процесс завершён и дождан) — заведомо нет такого.
        assert PsutilControl().children(popen.pid) == []


class TestPsutilControlTerminate:
    @pytest.fixture
    def fake_process(self) -> Iterator[subprocess.Popen[bytes]]:
        popen = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            yield popen
        finally:
            if popen.poll() is None:
                popen.kill()
            popen.wait()

    def test_terminate_with_correct_create_time_kills_process(
        self, fake_process: subprocess.Popen[bytes]
    ) -> None:
        create_time = psutil.Process(fake_process.pid).create_time()
        PsutilControl().terminate(fake_process.pid, create_time)
        fake_process.wait(timeout=5)
        assert fake_process.returncode is not None

    def test_terminate_with_mismatched_create_time_refuses_and_keeps_process_alive(
        self, fake_process: subprocess.Popen[bytes]
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: расхождение create_time на час не должно убивать процесс."""  # noqa: RUF002
        actual_create_time = psutil.Process(fake_process.pid).create_time()
        wrong_create_time = actual_create_time + 3600
        with pytest.raises(ProcessMismatchError):
            PsutilControl().terminate(fake_process.pid, wrong_create_time)
        assert psutil.Process(fake_process.pid).is_running()

    def test_terminate_on_freed_pid_is_silent(self) -> None:
        popen = subprocess.Popen([sys.executable, "-c", "pass"])
        popen.wait()
        # PID заведомо свободен — процесс завершён и дождан.
        PsutilControl().terminate(popen.pid, 0.0)  # не поднимает исключение
