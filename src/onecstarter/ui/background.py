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
import os
import threading
import time
import traceback
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from onecstarter.domain.version import Installation
from onecstarter.services.availability import Availability, ProbeTarget, probe_paths
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


class AvailabilityProbe(QObject):
    """Проверка каталогов файловых баз в фоне — перезапускаемая.

    Отдельно от `StartupTasks`: та поднимает два задания один раз за жизнь
    окна, а проба перезапускается по `F5` (спека §5). Поток — демон по той же
    причине, что и там: `stat` на мёртвой сетевой шаре не прерывается
    (инцидент 15.08.2026), и висящий поток не должен удерживать процесс
    при выходе.

    Результат отдаётся по одному пути за сигнал, а не пачкой в конце: иначе
    одна медленная шара держала бы метки всех остальных баз (спека §3.4).

    Поколения (§3.4, находка I-2): каждый `start()` заводит новое поколение,
    и сигналы устаревшего (перекрытого следующим `start()`) молчат — иначе
    F5 поверх зависшей пробы мог бы задним числом затереть свежий результат
    старым.

    В лог — счётчики и длительность, не пути: лог прикладывают к issue
    (докстринг модуля, инвариант 5).
    """  # noqa: RUF002

    probed = Signal(str, object)  # ключ пути, Availability

    def __init__(
        self,
        stat: Callable[[str], os.stat_result] = os.stat,
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._stat = stat
        self._spawn = spawn
        # Поколение пробы (находка I-2 финального ревью ветки, спека §3.4):
        # `start()` пишет из главного потока при каждом перезапуске (F5 поверх
        # ещё не завершённой пробы), `report` внутри `_run` читает его из  # noqa: RUF003
        # рабочего потока. `int` в CPython — атомарный тип (GIL сериализует
        # каждую байткод-операцию чтения/записи ссылки), гонки на самом
        # значении нет, и отдельный `Lock` был бы лишним усложнением.
        # Устаревший результат (захваченное в `_run` поколение не совпадает
        # с текущим `self._generation`) отбрасывается молча: зависший поток  # noqa: RUF003
        # старой пробы, дождавшись отказа сети, иначе отдал бы MISSING поверх
        # свежего PRESENT новой пробы.
        self._generation = 0

    def start(self, targets: Sequence[ProbeTarget]) -> None:
        ordered = list(targets)
        self._generation += 1
        generation = self._generation
        self._spawn(lambda: self._run(ordered, generation))

    def _run(self, targets: Sequence[ProbeTarget], generation: int) -> None:
        started = time.monotonic()
        _log.info("доступность каталогов: начато, целей %d", len(targets))
        missing = 0

        def report(key: str, state: Availability) -> None:
            nonlocal missing
            if state is Availability.MISSING:
                missing += 1
            # Молчаливый сброс устаревшего результата — см. комментарий  # noqa: RUF003
            # у self._generation в __init__.  # noqa: RUF003
            if generation == self._generation:
                self.probed.emit(key, state)

        try:
            probe_paths(targets, self._stat, report)
        except Exception as exc:
            # Падение фона не должно оставлять список без меток молча:
            # причина уходит в лог теми же местами кадров, без сообщения
            # исключения (оно несёт путь — см. докстринг _log_failure).
            _log_failure("доступность каталогов", exc)
        stale = generation != self._generation
        _log.info(
            "доступность каталогов: закончено%s за %d мс, недоступных %d",
            " (устарела)" if stale else "",
            int((time.monotonic() - started) * 1000),
            missing,
        )
