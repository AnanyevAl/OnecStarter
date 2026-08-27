"""Фоновый монитор процессов серверов: периодический скан плюс скан по требованию.

Калька `ui/background.py::StartupTasks` (её докстринг — прочитать целиком перед
правкой этого файла): потоки-демоны, `_log_failure` без содержимого исключения
(инвариант 5), логгер модуля вместо содержимого в сообщении. Отличие от
`StartupTasks` — периодичность и повторный вызов: `StartupTasks.start()` спавнит
задачу один раз, здесь `QTimer` в главном потоке тикает каждые `interval_ms`
и на каждый тик спавнит новый скан в демон-потоке (спека §4.4), а `scan_now()`
даёт внеочередной тик — им пользуется `ServersView` сразу после «Запустить»/
«Остановить» и после удаления профиля (T-08, задача 14; здесь — задача 16,
подтверждающий скан §8).

Пока предыдущий скан не завершился, новый тик (плановый или `scan_now()`)
пропускается — флаг занятости сбрасывается внутри задачи ПЕРЕД `emit`, не
после: висящий скан (антивирус на `psutil.process_iter`, залипший процесс)
не должен плодить поток на каждый интервал поверх ещё не завершившегося —
тот же довод, что у демон-потоков `StartupTasks` (см. её докстринг, абзац
про `open()` на мёртвой шаре).
"""  # noqa: RUF002

import logging
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from onecstarter.platform_1c.process_scan import ProcessScanner
from onecstarter.services.servers import ScanSnapshot, scan_servers

_log = logging.getLogger("onecstarter.servers")


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


def _log_failure(stage: str, exc: BaseException) -> None:
    """Отказ скана: тип исключения и места кадров, без текста сообщения.

    Тот же приём и тот же довод, что `background.py::_log_failure` (см. его
    докстринг): сообщение исключения может нести содержимое (путь, за который
    зацепился `psutil`), а лог прикладывают к issue.
    """  # noqa: RUF002
    frames = " -> ".join(
        f"{Path(frame.filename).name}:{frame.lineno}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
    _log.error("%s: отказ (%s @ %s)", stage, type(exc).__name__, frames)


class ServerMonitor(QObject):
    """Периодический + внеочередной скан ragent/rmngr, доставленный сигналом."""

    snapshot_ready = Signal(object)  # ScanSnapshot

    def __init__(
        self,
        scanner: ProcessScanner,
        *,
        interval_ms: int = 5000,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._spawn = spawn
        self._busy = False
        # QTimer — в главном потоке (тот же владелец, что и сам монитор):
        # тикает и спавнит поток на каждый тик, сам сетью/процессами не
        # занимается (инвариант T-04.6, §3.5 — эффекты только в потоке).
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def scan_now(self) -> None:
        """Внеочередной тик — тот же путь, что и плановый (§4.4, §8 спеки).

        Можно звать и до, и после `start()`: сам таймер для внеочередного
        скана не нужен, только флаг занятости.
        """
        self._tick()

    def _tick(self) -> None:
        if self._busy:
            # Предыдущий скан ещё не завершился — пропускаем тик, а не  # noqa: RUF003
            # плодим второй поток поверх первого (докстринг модуля).
            return
        self._busy = True
        self._spawn(self._run_scan)

    def _run_scan(self) -> None:
        try:
            snapshot = scan_servers(self._scanner)
        except Exception as exc:
            _log_failure("скан серверов", exc)
            snapshot = ScanSnapshot(agents=(), managers=())
        # Сброс ДО emit (докстринг модуля): к моменту, когда подписчик  # noqa: RUF003
        # (главный поток, через сигнал) решит позвать scan_now() из своего
        # обработчика, новый тик обязан быть уже разрешён.
        self._busy = False
        self.snapshot_ready.emit(snapshot)
