"""Серверный spawn: скрытая консоль, редирект stdout в файл, Job (T-10, задача 2)."""

import sys
import time
import uuid
from pathlib import Path

import psutil
import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import NullJob, ServerJob
from onecstarter.platform_1c.server_spawn import spawn_server


def _printing_command() -> LaunchCommand:
    return LaunchCommand(
        executable=Path(sys.executable),
        arguments='-c "print(\'hello from child\', flush=True); import time; time.sleep(30)"',
    )


def _kill_if_alive(pid: int) -> None:
    if psutil.pid_exists(pid):
        psutil.Process(pid).kill()


def test_spawn_server_redirects_stdout_to_log_file(tmp_path: Path) -> None:
    log_path = tmp_path / "j.log"
    pid = spawn_server(_printing_command(), log_path, NullJob())
    try:
        assert psutil.pid_exists(pid)
        deadline = time.monotonic() + 5
        content = ""
        while time.monotonic() < deadline:
            if log_path.exists():
                content = log_path.read_text(encoding="ascii", errors="replace")
                if "hello from child" in content:
                    break
            time.sleep(0.05)
        assert "hello from child" in content, f"строка не появилась в журнале за 5 с: {content!r}"  # noqa: RUF001
    finally:
        _kill_if_alive(pid)


def test_spawn_server_process_dies_when_job_closes(tmp_path: Path) -> None:
    log_path = tmp_path / "j.log"
    job = ServerJob()
    pid = spawn_server(_printing_command(), log_path, job)
    try:
        assert psutil.pid_exists(pid)
        job._close_for_tests()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and psutil.pid_exists(pid):
            time.sleep(0.05)
        assert not psutil.pid_exists(pid), "процесс пережил закрытие Job"
    finally:
        _kill_if_alive(pid)


def test_spawn_server_missing_log_dir_raises_oserror_and_spawns_nothing(tmp_path: Path) -> None:
    # Уникальный токен в аргументах — чтобы найти в дереве процессов именно
    # ЭТОТ вызов, а не случайный python.exe системы (антивирус, индексатор).  # noqa: RUF003
    token = f"onecstarter-marker-{uuid.uuid4().hex}"
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments=f'-c "import time; time.sleep(30)  # {token}"',
    )
    log_path = tmp_path / "no-such-dir" / "j.log"

    with pytest.raises(OSError):
        spawn_server(command, log_path, NullJob())

    time.sleep(0.2)  # дать бы успевшему стартовать процессу засветиться
    spawned = [
        proc
        for proc in psutil.process_iter(["cmdline"])
        if proc.info["cmdline"] and any(token in part for part in proc.info["cmdline"])
    ]
    for proc in spawned:
        proc.kill()
    assert not spawned, "процесс порождён, хотя открытие журнала должно было упасть раньше Popen"
