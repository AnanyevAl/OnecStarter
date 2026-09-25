"""Снимок процессов через Toolhelp: список без открытия процессов."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

from onecstarter.platform_1c.process_snapshot import SnapshotError, snapshot_all


@pytest.fixture
def fake_process(tmp_path: Path) -> Iterator[psutil.Process]:
    popen = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        yield psutil.Process(popen.pid)
    finally:
        popen.kill()
        popen.wait()


def test_snapshot_finds_a_live_process(fake_process: psutil.Process) -> None:
    found = dict(snapshot_all())
    assert fake_process.pid in found
    assert found[fake_process.pid].casefold() == fake_process.name().casefold()


def _is_known_pseudo_process_quirk(pid: int, toolhelp_name: str, psutil_name: str) -> bool:
    """Расхождение у двух безобразных псевдопроцессов — не баг раскладки.

    [Ф] измерено 25.09.2026 на машине разработчика (Windows 11, psutil 7.2.2,
    x64): у процессов без настоящего файла образа Toolhelp и `psutil` дают
    разные, но каждый по-своему легитимные имена. PID 0 (простой системы):
    Toolhelp — `[System Process]`, `psutil` — `System Idle Process`.
    Псевдопроцесс сжатия памяти: Toolhelp — `Memory Compression`, `psutil` —
    `MemCompression`. Раскладка `PROCESSENTRY32W` при ошибке в типе поля
    даёт мусор массово, на многих процессах сразу, а не точечно на этих
    двух именованных — поэтому им точечное исключение, а не общий допуск
    по количеству. [?] не проверено на других версиях Windows: если
    появится третий подобный псевдопроцесс, тест упадёт и укажет, на каком
    PID — это сигнал расширить список, а не ослаблять проверку.
    """  # noqa: RUF002
    if pid == 0:
        return True
    return {toolhelp_name, psutil_name} == {"memory compression", "memcompression"}


def test_snapshot_agrees_with_psutil() -> None:
    # Страховка от ошибки в раскладке PROCESSENTRY32W: неверный тип поля даёт
    # не падение, а правдоподобный мусор — сдвигаются все последующие поля.  # noqa: RUF003
    # Списки снимаются не одновременно, поэтому сверяется пересечение, а не  # noqa: RUF003
    # равенство: процессы рождаются и умирают между двумя вызовами.
    snapshot = {pid: name.casefold() for pid, name in snapshot_all()}
    live = {}
    for process in psutil.process_iter(attrs=["pid", "name"]):
        try:
            info = process.info
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if info.get("name"):
            live[info["pid"]] = info["name"].casefold()

    common = snapshot.keys() & live.keys()
    assert len(common) > 20, "снимки почти не пересеклись — раскладка структуры под вопросом"
    mismatched = {
        pid
        for pid in common
        if snapshot[pid] != live[pid]
        and not _is_known_pseudo_process_quirk(pid, snapshot[pid], live[pid])
    }
    assert not mismatched


def test_snapshot_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from onecstarter.platform_1c import process_snapshot

    class _Failing:
        def CreateToolhelp32Snapshot(self, flags: int, pid: int) -> int | None:  # noqa: N802
            return process_snapshot.INVALID_HANDLE_VALUE

    monkeypatch.setattr(process_snapshot, "_kernel32", lambda: _Failing())
    with pytest.raises(SnapshotError):
        snapshot_all()
