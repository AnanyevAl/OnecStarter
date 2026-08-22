"""StartupTasks: доставка результатов фона сигналами и лог фаз."""

import logging
import threading
from pathlib import Path

from onecstarter.domain.version import Installation
from onecstarter.services.catalog import EMPTY_COMMON_DATA
from onecstarter.ui.background import StartupTasks

_SYNC = lambda task: task()  # noqa: E731 — синхронный «поток» для детерминизма


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
