"""ServerMonitor: калька StartupTasks — периодический скан + скан по требованию.

Приём тот же, что `test_background.py`: синхронный `spawn=lambda task: task()`
делает поведение детерминированным без реального потока там, где важен только
факт снимка/лога; отдельный тест ниже проверяет настоящие демон-потоки —
тем же способом, что `test_default_spawn_uses_daemon_threads`.
"""

import logging
import threading
from collections.abc import Callable

from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.servers import SCAN_NAMES, ScanSnapshot
from onecstarter.ui.servers.monitor import ServerMonitor

_SYNC = lambda task: task()  # noqa: E731 — синхронный «поток» для детерминизма


class _FakeScanner:
    """`ProcessScanner`, отдающий заранее заданный список без psutil."""

    def __init__(self, processes: list[ProcessInfo]) -> None:
        self._processes = processes
        self.calls: list[frozenset[str]] = []

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        self.calls.append(names)
        return list(self._processes)


class _ExplodingScanner:
    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        raise RuntimeError("нет доступа к списку процессов")


def _agent(pid: int) -> ProcessInfo:
    return ProcessInfo(
        pid=pid, name="ragent.exe", executable=None, argv=None, create_time=1.0
    )


def test_scan_now_emits_snapshot_with_sync_spawn():
    scanner = _FakeScanner([_agent(100)])
    monitor = ServerMonitor(scanner, spawn=_SYNC)
    got: list[ScanSnapshot] = []
    monitor.snapshot_ready.connect(got.append)

    monitor.scan_now()

    assert len(got) == 1
    assert got[0].agents == (_agent(100),)
    assert got[0].managers == ()
    assert scanner.calls == [SCAN_NAMES]


def test_scan_failure_logs_without_content_and_emits_empty_snapshot(caplog):
    monitor = ServerMonitor(_ExplodingScanner(), spawn=_SYNC)
    got: list[ScanSnapshot] = []
    monitor.snapshot_ready.connect(got.append)

    with caplog.at_level(logging.ERROR):
        monitor.scan_now()

    assert got == [ScanSnapshot(agents=(), managers=())]
    # Инвариант 5: тип исключения — в логе, содержимого (сообщения) — нет.
    assert "RuntimeError" in caplog.text
    assert "нет доступа" not in caplog.text


def test_busy_scan_skips_the_next_tick():
    """Занятость: пока задача не завершилась (не позвала spawn ещё раз), новый
    тик пропускается — тот же довод, что у демон-потоков StartupTasks: висящий
    скан не должен плодить поток на каждый интервал/scan_now().
    """  # noqa: RUF002
    scanner = _FakeScanner([])
    calls: list[int] = []

    def hanging_spawn(task: Callable[[], None]) -> None:
        # Задача «подвисает»: спавн зарегистрирован, но сама задача ни разу
        # не вызывается — busy остаётся True до тех пор, пока её кто-то
        # не выполнит вручную.
        calls.append(1)

    monitor = ServerMonitor(scanner, spawn=hanging_spawn)

    monitor.scan_now()
    monitor.scan_now()

    assert calls == [1], "второй тик обязан быть пропущен, пока первый не завершился"


def test_scan_allowed_again_after_previous_finished():
    scanner = _FakeScanner([])
    spawned: list[Callable[[], None]] = []

    def capturing_spawn(task: Callable[[], None]) -> None:
        spawned.append(task)

    monitor = ServerMonitor(scanner, spawn=capturing_spawn)

    monitor.scan_now()
    spawned[0]()  # выполняем «зависшую» задачу вручную — busy сбрасывается
    monitor.scan_now()

    assert len(spawned) == 2


def test_default_spawn_uses_daemon_threads():
    seen: list[bool] = []
    done = threading.Event()

    class _RecordingScanner:
        def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
            seen.append(threading.current_thread().daemon)
            done.set()
            return []

    monitor = ServerMonitor(_RecordingScanner())
    monitor.scan_now()

    assert done.wait(5), "фоновый скан не завершился за 5 с"  # noqa: RUF001
    assert seen == [True]


def test_real_timer_delivers_snapshot_through_the_event_loop(qtbot):
    scanner = _FakeScanner([_agent(7)])
    monitor = ServerMonitor(scanner, interval_ms=10)

    with qtbot.waitSignal(monitor.snapshot_ready, timeout=5000):
        monitor.start()

    monitor._timer.stop()  # не оставлять тикающий таймер после теста


def test_start_configures_the_timer_with_the_given_interval():
    monitor = ServerMonitor(_FakeScanner([]), interval_ms=1234)
    assert monitor._timer.interval() == 1234
    assert not monitor._timer.isActive()

    monitor.start()

    assert monitor._timer.isActive()
