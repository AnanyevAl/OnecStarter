"""EdtMonitor — калька test_server_monitor.py: скан и обнаружение в подставном «потоке»."""

from collections.abc import Callable
from pathlib import Path

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.edt import EdtScan
from onecstarter.ui.edt.monitor import EdtMonitor


class FakeScanner:
    def __init__(self, processes: list[ProcessInfo]) -> None:
        self._processes = processes

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        return list(self._processes)


def _inline(task: Callable[[], None]) -> None:
    task()


def test_scan_now_emits_scan(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    project = EdtProject("p1", "a", str(ws_dir))
    proc = ProcessInfo(pid=5, name="1cedt.exe", executable=None, argv=("x", "-data", str(ws_dir)))
    monitor = EdtMonitor(FakeScanner([proc]), lambda: [project], lambda: [], spawn=_inline)
    received: list[EdtScan] = []
    monitor.scan_ready.connect(received.append)
    monitor.scan_now()
    assert received == [EdtScan(running={"p1": 5}, present={"p1": True})]


def test_discover_now_emits_installations(qapp) -> None:  # type: ignore[no-untyped-def]
    installed = [EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), None, "", 17, "")]
    monitor = EdtMonitor(FakeScanner([]), lambda: [], lambda: list(installed), spawn=_inline)
    received: list[list[EdtInstallation]] = []
    monitor.installations_ready.connect(received.append)
    monitor.discover_now()
    assert received == [installed]


def test_busy_scan_skips_tick(qapp) -> None:  # type: ignore[no-untyped-def]
    pending: list[Callable[[], None]] = []
    monitor = EdtMonitor(FakeScanner([]), lambda: [], lambda: [], spawn=pending.append)
    monitor.scan_now()
    monitor.scan_now()
    assert len(pending) == 1
    pending[0]()
    monitor.scan_now()
    assert len(pending) == 2


def test_scan_failure_emits_empty_scan(qapp) -> None:  # type: ignore[no-untyped-def]
    class Broken:
        def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
            raise RuntimeError("psutil упал")

    monitor = EdtMonitor(Broken(), lambda: [], lambda: [], spawn=_inline)
    received: list[EdtScan] = []
    monitor.scan_ready.connect(received.append)
    monitor.scan_now()
    assert received == [EdtScan(running={}, present={})]


def test_discover_failure_emits_empty_list(qapp) -> None:  # type: ignore[no-untyped-def]
    def broken() -> list[EdtInstallation]:
        raise OSError("диск")

    monitor = EdtMonitor(FakeScanner([]), lambda: [], broken, spawn=_inline)
    received: list[list[EdtInstallation]] = []
    monitor.installations_ready.connect(received.append)
    monitor.discover_now()
    assert received == [[]]
