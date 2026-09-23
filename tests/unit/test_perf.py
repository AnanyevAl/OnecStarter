"""perf: замеры под флагом — без Qt, отдельный файл лога."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from onecstarter import perf


def _cleanup() -> None:
    """Снять обработчики своего логгера и сбросить флаг между тестами.

    Тот же приём, что `_cleanup_root` в test_diagnostics.py, но логгер
    свой, а не корневой: perf не имеет права добавлять обработчики
    в корень — иначе его строки утекли бы в onecstarter.log.
    """  # noqa: RUF002
    perf.reset_for_tests()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    _cleanup()
    yield
    _cleanup()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("Yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("мусор", False),
    ],
)
def test_is_enabled(value: str, expected: bool) -> None:
    assert perf.is_enabled({perf.ENV_NAME: value}) is expected


def test_is_enabled_without_the_variable() -> None:
    assert perf.is_enabled({}) is False


def test_setup_creates_the_file_when_enabled(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path == tmp_path / "OneCStarter" / "logs" / "perf.log"


def test_setup_does_nothing_when_disabled(tmp_path: Path) -> None:
    assert perf.setup({"APPDATA": str(tmp_path)}) is None
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()


def test_setup_survives_unwritable_directory(tmp_path: Path) -> None:
    blocker = tmp_path / "APPDATA"
    blocker.write_text("файл на месте каталога", encoding="utf-8")
    assert perf.setup({"APPDATA": str(blocker), perf.ENV_NAME: "1"}) is None


def _read(path: Path) -> str:
    for handler in logging.getLogger("onecstarter.perf").handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def test_measure_writes_stage_duration_and_counters(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None

    with perf.measure("скан процессов (servers)", просмотрено=1183) as counters:
        counters["совпало"] = 7

    line = _read(path).strip()
    assert " PERF скан процессов (servers): " in line
    assert " мс, просмотрено=1183, совпало=7" in line


def test_measure_writes_nothing_when_disabled(tmp_path: Path) -> None:
    perf.setup({"APPDATA": str(tmp_path)})
    with perf.measure("что-то", строк=3) as counters:
        counters["ещё"] = 1
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()


def test_measure_reports_even_when_the_block_raises(tmp_path: Path) -> None:
    # Замер — диагностика; потерять его на отказе значило бы потерять  # noqa: RUF003
    # ровно тот случай, ради которого он и включён.
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    with pytest.raises(ValueError), perf.measure("падучая операция"):
        raise ValueError("нарочно")
    assert "падучая операция" in _read(path)


def test_log_line_carries_no_logger_name_and_no_level(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    with perf.measure("операция"):
        pass
    line = _read(path).strip()
    assert "onecstarter.perf" not in line
    assert "INFO" not in line


def test_enabled_reflects_setup(tmp_path: Path) -> None:
    assert perf.enabled() is False
    perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert perf.enabled() is True


def test_repeated_setup_does_not_duplicate_log_lines(tmp_path: Path) -> None:
    # Повторный setup — не гипотетика: в __main__ он может позваться дважды
    # при повторном входе в main (тесты, будущие сценарии перезапуска).
    # Второй RotatingFileHandler на тот же файл задвоил бы каждую строку
    # замера, и любой подсчёт по логу стал бы неверным вдвое.
    env = {"APPDATA": str(tmp_path), perf.ENV_NAME: "1"}
    first = perf.setup(env)
    second = perf.setup(env)
    assert first == second
    assert first is not None

    with perf.measure("test-stage", n=1):
        pass

    lines = [line for line in _read(first).splitlines() if line.strip()]
    assert len(lines) == 1
