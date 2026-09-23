"""Heartbeat главного потока: опоздание тика — это простой."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject

from onecstarter import perf
from onecstarter.ui.heartbeat import Heartbeat, maybe_start_heartbeat


class _Clock:
    """Часы под управлением теста: ждать настоящие 150 мс незачем."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _lines(path: Path) -> list[str]:
    for handler in logging.getLogger("onecstarter.perf").handlers:
        handler.flush()
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_long_stall_is_reported(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        clock.now += 0.430  # 430 мс вместо ожидаемых 50
        beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert len(lines) == 1
    assert "главный поток стоял 430 мс" in lines[0]


def test_short_gap_is_silent(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        clock.now += 0.120  # 120 мс — меньше порога
        beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert lines == []


def test_each_tick_measures_from_the_previous_one(tmp_path: Path) -> None:
    # Без обновления отметки на каждом тике второй тик посчитал бы
    # паузу от самого старта и отчитался бы о простое, которого не было.  # noqa: RUF003
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        clock.now += 0.430
        beat._tick()
        clock.now += 0.050
        beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert len(lines) == 1


def test_consecutive_short_ticks_stay_silent(tmp_path: Path) -> None:
    # Мутация «обновлять `_last` только в ветке отчёта» на этом тесте не
    # проходит: если ни один тик сам не превысил порог, отметка никогда
    # не обновляется, и разрыв копится от старта — 4x50 мс дают 200 мс
    # «простоя», которого не было. Правильная реализация обновляет
    # `_last` на каждом тике и не даёт разрыву накопиться.
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        for _ in range(4):
            clock.now += 0.050
            beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert lines == []


def test_not_started_when_perf_is_off(tmp_path: Path) -> None:
    perf.setup({"APPDATA": str(tmp_path)})
    parent = QObject()
    try:
        assert maybe_start_heartbeat({"APPDATA": str(tmp_path)}, parent) is None
    finally:
        perf.reset_for_tests()


def test_started_when_perf_is_on(tmp_path: Path) -> None:
    env = {"APPDATA": str(tmp_path), perf.ENV_NAME: "1"}
    perf.setup(env)
    parent = QObject()
    try:
        beat = maybe_start_heartbeat(env, parent)
        assert beat is not None
        assert beat.parent() is parent
    finally:
        perf.reset_for_tests()
