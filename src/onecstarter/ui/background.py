"""Фоновые задачи старта: обнаружение платформ и общие списки.

Потоки и сигналы живут здесь, в ui (инвариант 1); сами задачи — чистые
функции, они возвращают данные, применяет их главный поток по сигналу.
Потоки — демоны: поток, заблокированный в `open()` на exe под антивирусом
или на мёртвой шаре, убить нельзя, и он не должен удерживать процесс
при выходе (спека T-04.6, §3.5, инцидент 15.08.2026).

В лог — счётчики и длительности, не содержимое: лог прикладывают
к issue (спека §4.1, инвариант 5).
"""  # noqa: RUF002

import logging
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from onecstarter.domain.version import Installation
from onecstarter.services.catalog import EMPTY_COMMON_DATA, CommonListData

_log = logging.getLogger("onecstarter.startup")


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


def _log_failure(stage: str, exc: BaseException) -> None:
    """Отказ фоновой задачи: тип исключения и места кадров, без текста.

    Сообщение исключения несёт содержимое — `OSError` вкладывает путь
    (UNC общего списка из cfg, каталог установки), — а лог прикладывают
    к issue (докстринг модуля, инвариант 5). Полный traceback непригоден
    по той же причине: его последняя строка — то же сообщение, а строки
    исходника могут нести литералы. Места кадров (имя файла кода : строка)
    содержимого пользователя не несут, а шаг, на котором упало,
    локализуют — одного имени типа для этого мало (финальное ревью
    ветки 18.08.2026).
    """  # noqa: RUF002
    frames = " -> ".join(
        f"{Path(frame.filename).name}:{frame.lineno}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
    _log.error("%s: отказ (%s @ %s)", stage, type(exc).__name__, frames)


class StartupTasks(QObject):
    """Две независимые задачи: зависание одной не топит вторую (спека §3.2)."""

    installations_ready = Signal(object)  # list[Installation]
    common_lists_ready = Signal(object)  # CommonListData

    def __init__(
        self,
        discover: Callable[[], list[Installation]],
        read_common: Callable[[], CommonListData],
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._discover = discover
        self._read_common = read_common
        self._spawn = spawn

    def start(self) -> None:
        self._spawn(self._run_discovery)
        self._spawn(self._run_common)

    def _run_discovery(self) -> None:
        started = time.monotonic()
        _log.info("обнаружение платформ: начато")
        try:
            found = self._discover()
        except Exception as exc:
            # Падение фона не должно оставлять окно в вечном «…»: логируем
            # причину (что и почему нельзя — докстринг _log_failure) и отдаём
            # пустой результат — состояние видно и в окне, и в логе.
            _log_failure("обнаружение платформ", exc)
            found = []
        _log.info(
            "обнаружение платформ: закончено за %d мс, найдено %d",
            int((time.monotonic() - started) * 1000),
            len(found),
        )
        self.installations_ready.emit(found)

    def _run_common(self) -> None:
        started = time.monotonic()
        _log.info("общие списки: чтение начато")
        try:
            data = self._read_common()
        except Exception as exc:
            _log_failure("общие списки", exc)
            data = EMPTY_COMMON_DATA
        _log.info(
            "общие списки: закончено за %d мс, файлов %d, ошибок %d",
            int((time.monotonic() - started) * 1000),
            len(data.payloads),
            len(data.errors),
        )
        self.common_lists_ready.emit(data)
