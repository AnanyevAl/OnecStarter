"""Простой главного потока, измеренный опозданием собственного тика.

Таймер живёт в главном потоке и обязан тикать каждые `interval_ms`.
Если тик пришёл заметно позже — ровно столько главный поток был ничем
не занят по своей воле: его держали. Причина безразлична — GIL под
нативным вызовом, долгая отрисовка, чужой код; поэтому heartbeat
остаётся полезным, даже если диагноз спеки 3.2.1 §2 окажется неверным.

Создаётся только при включённом perf-режиме: 20 пробуждений в секунду
даром не нужны (спека §11).
"""  # noqa: RUF002

import logging
import time
from collections.abc import Callable, Mapping

from PySide6.QtCore import QObject, QTimer

from onecstarter import perf

_log = logging.getLogger("onecstarter.perf")


class Heartbeat(QObject):
    """Тикает в главном потоке и докладывает о собственных опозданиях."""  # noqa: RUF002

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        interval_ms: int = 50,
        threshold_ms: int = 150,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._threshold_ms = threshold_ms
        # Часы инъекцией: тест не обязан ждать настоящие 150 мс, чтобы
        # проверить порог, — тот же приём, что `now=` у Workspace.  # noqa: RUF003
        self._clock = clock
        self._last = clock()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._last = self._clock()
        self._timer.start()

    def _tick(self) -> None:
        now = self._clock()
        # round(), не int(): при накоплении дробных секунд (клок теста,
        # монотонные часы) усечение вниз однажды уже дало 429 мс вместо
        # фактических 430 — ошибка представления float, не логики.
        gap_ms = round((now - self._last) * 1000)
        # Отметка обновляется ВСЕГДА, до всякого решения о записи: иначе  # noqa: RUF003
        # следующий тик считал бы паузу от предыдущего опоздания и
        # доложил бы о простое, которого не было.  # noqa: RUF003
        self._last = now
        if gap_ms >= self._threshold_ms:
            _log.info("главный поток стоял %d мс", gap_ms)


def maybe_start_heartbeat(env: Mapping[str, str], parent: QObject) -> Heartbeat | None:
    """Завести heartbeat, если режим включён. `None` — выключен.

    Отдельная функция, а не условие в `main`: развилка проверяется
    таблично, без поднятия окна.
    """  # noqa: RUF002
    if not perf.is_enabled(env):
        return None
    beat = Heartbeat(parent)
    beat.start()
    return beat
