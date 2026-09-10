"""Фоновый монитор раздела «EDT»: скан процессов и каталогов + обнаружение установок.

Калька `ui/servers/monitor.py::ServerMonitor` (её докстринг — прочитать целиком):
`QTimer` в главном потоке тикает каждые `interval_ms`, каждый тик — новый скан
в потоке-демоне; занятый скан пропускает тик. Отличия: два вида задач —
периодический `scan_edt` (процессы `1cedt.exe` + `isdir` каждого workspace)
и обнаружение установок по требованию (`discover_now`, старт и `F5`),
у каждой свой флаг занятости и свой сигнал. Список записей снимается
в главном потоке до спавна задачи — координатор из потока-демона не трогается.
"""  # noqa: RUF002

import logging
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.platform_1c.process_scan import ProcessScanner
from onecstarter.services.edt import EdtScan, scan_edt

_log = logging.getLogger("onecstarter.edt")


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


def _log_failure(stage: str, exc: BaseException) -> None:
    """Тип и кадры без текста исключения — инвариант 5 (см. `background.py`)."""
    frames = " -> ".join(
        f"{Path(frame.filename).name}:{frame.lineno}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
    _log.error("%s: отказ (%s @ %s)", stage, type(exc).__name__, frames)


class EdtMonitor(QObject):
    scan_ready = Signal(object)  # EdtScan
    installations_ready = Signal(object)  # list[EdtInstallation]

    def __init__(
        self,
        scanner: ProcessScanner,
        projects: Callable[[], list[EdtProject]],
        discover: Callable[[], list[EdtInstallation]],
        *,
        interval_ms: int = 5000,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._projects = projects
        self._discover = discover
        self._spawn = spawn
        self._scan_busy = False
        self._discover_busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.scan_now)

    def start(self) -> None:
        self.discover_now()
        self.scan_now()
        self._timer.start()

    def scan_now(self) -> None:
        if self._scan_busy:
            return
        self._scan_busy = True
        projects = self._projects()

        def run() -> None:
            try:
                scan = scan_edt(self._scanner, projects)
            except Exception as exc:
                _log_failure("скан EDT", exc)
                scan = EdtScan(running={}, present={})
            self._scan_busy = False
            self.scan_ready.emit(scan)

        self._spawn(run)

    def discover_now(self) -> None:
        if self._discover_busy:
            return
        self._discover_busy = True

        def run() -> None:
            try:
                found = self._discover()
            except Exception as exc:
                _log_failure("обнаружение EDT", exc)
                found = []
            self._discover_busy = False
            self.installations_ready.emit(found)

        self._spawn(run)
