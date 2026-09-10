"""StartupTasks: доставка результатов фона сигналами и лог фаз."""

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from stat import S_IFDIR

from onecstarter.domain.version import Installation
from onecstarter.services.availability import Availability, ProbeTarget
from onecstarter.services.catalog import EMPTY_COMMON_DATA
from onecstarter.ui.background import AvailabilityProbe, StartupTasks

_SYNC = lambda task: task()  # noqa: E731 — синхронный «поток» для детерминизма

_DIR = os.stat_result((S_IFDIR | 0o755, 0, 0, 1, 0, 0, 0, 0, 0, 0))


def test_start_emits_both_results(qtbot):
    got: dict[str, object] = {}
    tasks = StartupTasks(lambda: ["inst"], lambda: EMPTY_COMMON_DATA, spawn=_SYNC)  # type: ignore[list-item]
    tasks.installations_ready.connect(lambda found: got.__setitem__("inst", found))
    tasks.common_lists_ready.connect(lambda data: got.__setitem__("common", data))
    tasks.start()
    assert got == {"inst": ["inst"], "common": EMPTY_COMMON_DATA}


def test_real_threads_deliver_into_the_event_loop(qtbot):
    tasks = StartupTasks(lambda: [], lambda: EMPTY_COMMON_DATA)
    with qtbot.waitSignals(
        [tasks.installations_ready, tasks.common_lists_ready], timeout=5000
    ):
        tasks.start()


def test_default_spawn_uses_daemon_threads():
    seen: list[bool] = []
    done = threading.Event()

    def discover() -> list[Installation]:
        seen.append(threading.current_thread().daemon)
        done.set()  # взводится в самом фоновом потоке — сигнал тут не нужен
        return []

    tasks = StartupTasks(discover, lambda: EMPTY_COMMON_DATA)
    tasks.start()
    assert done.wait(5), "фоновая задача не завершилась за 5 с"  # noqa: RUF001
    assert seen == [True]


def test_failed_task_logs_and_emits_empty(qtbot, caplog):
    def explode() -> list[Installation]:
        raise RuntimeError("нет доступа")

    got: dict[str, object] = {}
    tasks = StartupTasks(explode, lambda: EMPTY_COMMON_DATA, spawn=_SYNC)
    tasks.installations_ready.connect(lambda found: got.__setitem__("inst", found))
    with caplog.at_level(logging.ERROR):
        tasks.start()
    assert got["inst"] == []
    assert "обнаружение" in caplog.text


def test_failed_task_log_carries_type_not_message(caplog):
    """Сторож инварианта 5 на пути отказа (МУТАЦИЯ): текст исключения — не в лог.

    Сообщение исключения несёт содержимое: `OSError` вкладывает путь —
    UNC-сервер общего списка из cfg, каталог установки, — а лог прикладывают
    к issue. Поэтому ветка отказа пишет тип исключения, не его текст
    и не traceback (его последняя строка — тот же текст).
    """  # noqa: RUF002
    from onecstarter.services.catalog import CommonListData

    def explode_discovery() -> list[Installation]:
        raise OSError(r"C:\Секретный каталог\1cv8.exe недоступен")

    def explode_lists() -> CommonListData:
        raise OSError(r"\\скрытый-сервер\список.v8i недоступен")

    tasks = StartupTasks(explode_discovery, explode_lists, spawn=_SYNC)
    with caplog.at_level(logging.ERROR):
        tasks.start()
    assert "Секретный каталог" not in caplog.text
    assert "скрытый-сервер" not in caplog.text
    assert caplog.text.count("OSError") == 2
    # Места кадров (файл:строка, без строк исходника) — обязаны остаться:
    # без них тип исключения не локализует шаг, на котором упало
    # (финальное ревью ветки 18.08.2026).
    assert "test_background.py" in caplog.text


def test_log_carries_counts_not_paths(caplog):
    """Сторож инварианта 5: в лог — счётчики, не содержимое (МУТАЦИЯ)."""
    from onecstarter.services.catalog import CommonListData

    payload = 'Srvr="секретный-сервер";Ref="скрытая";'.encode()
    data = CommonListData(((Path(r"\\share\список.v8i"), payload),), ())
    tasks = StartupTasks(lambda: [], lambda: data, spawn=_SYNC)
    with caplog.at_level(logging.INFO):
        tasks.start()
    assert "секретный-сервер" not in caplog.text
    assert "share" not in caplog.text


def test_probe_emits_one_signal_per_path(qtbot):
    got: list[tuple[str, Availability]] = []
    probe = AvailabilityProbe(lambda _p: _DIR, spawn=_SYNC)
    probe.probed.connect(lambda key, state: got.append((key, state)))
    probe.start([ProbeTarget("a", r"D:\a"), ProbeTarget("b", r"D:\b")])
    assert got == [("a", Availability.PRESENT), ("b", Availability.PRESENT)]


def test_probe_reports_missing(qtbot):
    def stat(_path: str) -> os.stat_result:
        raise FileNotFoundError

    got: list[Availability] = []
    probe = AvailabilityProbe(stat, spawn=_SYNC)
    probe.probed.connect(lambda _key, state: got.append(state))
    probe.start([ProbeTarget("a", r"D:\a")])
    assert got == [Availability.MISSING]


def test_probe_can_be_restarted(qtbot):
    """F5 перезапускает пробу — `start` не одноразов, в отличие от StartupTasks."""
    got: list[str] = []
    probe = AvailabilityProbe(lambda _p: _DIR, spawn=_SYNC)
    probe.probed.connect(lambda key, _state: got.append(key))
    probe.start([ProbeTarget("a", r"D:\a")])
    probe.start([ProbeTarget("a", r"D:\a")])
    assert got == ["a", "a"]


def test_stale_generation_is_discarded_on_restart(qtbot):
    """I-2: F5 поверх зависшей пробы не должен затереть свежий результат старым.

    `spawn` здесь только складывает задания в список, ничего не запуская, —
    это и моделирует «зависшую» пробу: оба `start()` уже случились (значит,
    текущее поколение — уже второе) раньше, чем выполнится хоть одно
    задание. `tasks[0]` — первая (устаревшая) проба, `tasks[1]` — вторая
    (текущая); порядок выполнения ниже — первая после того, как обе стартовали.
    """  # noqa: RUF002
    tasks: list[Callable[[], None]] = []
    probe = AvailabilityProbe(lambda _p: _DIR, spawn=tasks.append)
    got: list[tuple[str, Availability]] = []
    probe.probed.connect(lambda key, state: got.append((key, state)))

    probe.start([ProbeTarget("old", r"D:\old")])
    probe.start([ProbeTarget("new", r"D:\new")])
    assert len(tasks) == 2

    tasks[0]()  # устаревшая проба — поколение к этому моменту уже второе
    assert got == [], "результат устаревшей пробы не должен доходить до сигнала"

    tasks[1]()  # текущая проба — её поколение всё ещё актуально
    assert got == [("new", Availability.PRESENT)]


def test_single_start_still_emits_as_before(qtbot):
    """Регрессия: без перезапуска поколения не мешают обычному одиночному старту."""
    tasks: list[Callable[[], None]] = []
    probe = AvailabilityProbe(lambda _p: _DIR, spawn=tasks.append)
    got: list[tuple[str, Availability]] = []
    probe.probed.connect(lambda key, state: got.append((key, state)))

    probe.start([ProbeTarget("a", r"D:\a")])
    assert len(tasks) == 1
    tasks[0]()
    assert got == [("a", Availability.PRESENT)]


def test_probe_uses_daemon_threads(qtbot):
    done = threading.Event()
    seen: list[bool] = []

    def stat(_path: str) -> os.stat_result:
        seen.append(threading.current_thread().daemon)
        done.set()
        return _DIR

    AvailabilityProbe(stat).start([ProbeTarget("a", r"D:\a")])
    assert done.wait(5), "проба не завершилась за 5 с"  # noqa: RUF001
    assert seen[0] is True


def test_probe_failure_is_logged_without_the_path(qtbot, caplog):
    """Инвариант 5: путь пользователя не попадает ни в одну строку лога (МУТАЦИЯ).

    М-5: `caplog.at_level(logging.ERROR, ...)` фильтровал INFO-записи
    («начато», «закончено») — путь, попавший бы в них, тест бы не увидел.
    Уровень поднят до INFO (тот же, на котором работает сторож `StartupTasks`
    на счётчики, `test_log_carries_counts_not_paths`); отсутствие пути
    проверяется по ВСЕМУ тексту лога, а сам факт отказа — отдельно, строкой
    с меткой стадии и типом исключения.
    """  # noqa: RUF002

    def stat(_path: str) -> os.stat_result:
        raise RuntimeError(r"\\srv\секретная-шара\база")

    with caplog.at_level(logging.INFO, logger="onecstarter.startup"):
        AvailabilityProbe(stat, spawn=_SYNC).start([ProbeTarget("a", r"D:\a")])
    assert "секретная-шара" not in caplog.text
    assert "доступность каталогов: отказ" in caplog.text
    assert "RuntimeError" in caplog.text
