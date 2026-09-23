"""Тесты сканера процессов: `NullScanner` и `PsutilScanner`.

Живой ragent/1С не участвует (правило проекта — не запускать процессы 1С):
интеграционный тест поднимает подставной python-процесс с ragent-подобным
хвостом argv (`-port 9999 -d <tmp_path>`) и сканирует именно его.
"""  # noqa: RUF002

import logging
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

from onecstarter import perf
from onecstarter.platform_1c import process_scan
from onecstarter.platform_1c.process_scan import NullScanner, PsutilScanner


class TestNullScanner:
    def test_snapshot_is_always_empty(self) -> None:
        assert NullScanner().snapshot(frozenset({"ragent.exe", "rmngr.exe"})) == []


class TestPsutilScanner:
    @pytest.fixture
    def fake_process(self, tmp_path: Path) -> Iterator[psutil.Process]:
        popen = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
                "-port",
                "9999",
                "-d",
                str(tmp_path),
            ]
        )
        try:
            yield psutil.Process(popen.pid)
        finally:
            popen.kill()
            popen.wait()

    def test_finds_fake_process_by_own_name(self, fake_process: psutil.Process) -> None:
        # Имя процесса python.exe/python3.13.exe зависит от машины — берём
        # фактическое имя у самого процесса, а не угадываем интерпретатор.  # noqa: RUF003
        name = fake_process.name().casefold()
        result = PsutilScanner().snapshot(frozenset({name}))
        found = next((p for p in result if p.pid == fake_process.pid), None)
        assert found is not None
        assert found.argv is not None
        assert "-port" in found.argv
        assert "9999" in found.argv

    def test_unrelated_name_does_not_match_fake_process(
        self, fake_process: psutil.Process
    ) -> None:
        result = PsutilScanner().snapshot(frozenset({"нет-такого.exe"}))
        assert all(p.pid != fake_process.pid for p in result)


class _FakeProcess:
    """Процесс, считающий обращения к дорогим полям.

    `exe()`/`cmdline()` на Windows требуют открыть процесс и прочитать
    его адресное пространство, поэтому счётчик обращений — и есть
    предмет проверки: у несовпавших по имени их звать нельзя.
    """  # noqa: RUF002

    def __init__(
        self,
        pid: int,
        name: str,
        exe: str | None = r"C:\1cv8\bin\ragent.exe",
        argv: list[str] | None = None,
        exe_error: BaseException | type[BaseException] | None = None,
        cmdline_error: BaseException | type[BaseException] | None = None,
    ) -> None:
        self.pid = pid
        self.info = {"pid": pid, "name": name}
        self._exe = exe
        self._argv = [] if argv is None else argv
        self._exe_error = exe_error
        self._cmdline_error = cmdline_error
        self.detail_calls = 0

    def exe(self) -> str | None:
        self.detail_calls += 1
        if self._exe_error is not None:
            raise self._exe_error
        return self._exe

    def cmdline(self) -> list[str]:
        self.detail_calls += 1
        if self._cmdline_error is not None:
            raise self._cmdline_error
        return self._argv


def _with_processes(
    monkeypatch: pytest.MonkeyPatch, processes: list[_FakeProcess]
) -> None:
    monkeypatch.setattr(
        process_scan.psutil, "process_iter", lambda attrs: list(processes)
    )


def test_details_are_read_only_for_matching_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matching = _FakeProcess(1, "ragent.exe")
    others = [_FakeProcess(pid, f"chrome{pid}.exe") for pid in range(2, 40)]
    _with_processes(monkeypatch, [matching, *others])

    result = PsutilScanner().snapshot(frozenset({"ragent.exe"}))

    assert [p.pid for p in result] == [1]
    assert matching.detail_calls == 2  # exe + cmdline
    assert [p.detail_calls for p in others] == [0] * len(others)


def test_access_denied_on_one_field_keeps_the_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Прежняя редакция звала Process.as_dict, и тот сам переводил
    # недоступное поле в None ПООТДЕЛЬНОСТИ. Общий try вокруг обоих
    # чтений потерял бы доступный argv у процесса с недоступным exe.  # noqa: RUF003
    process = _FakeProcess(
        7, "ragent.exe", exe_error=psutil.AccessDenied, argv=["ragent", "-port", "1540"]
    )
    _with_processes(monkeypatch, [process])

    found = PsutilScanner().snapshot(frozenset({"ragent.exe"}))[0]

    assert found.executable is None
    assert found.argv == ("ragent", "-port", "1540")


def test_process_that_died_between_name_and_details_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Прежняя редакция делала `continue` на NoSuchProcess, и процесс
    # в результат не попадал вовсе. Отдать его с пустыми полями значило бы  # noqa: RUF003
    # выдумать факт о том, чего уже нет.  # noqa: RUF003
    # NoSuchProcess (в отличие от AccessDenied) требует pid при создании
    # (psutil 7.x) — бросить голый класс нельзя, нужен экземпляр.
    _with_processes(
        monkeypatch,
        [_FakeProcess(9, "ragent.exe", exe_error=psutil.NoSuchProcess(9))],
    )

    assert PsutilScanner().snapshot(frozenset({"ragent.exe"})) == []


def test_label_is_accepted_and_does_not_change_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(3, "ragent.exe")])

    labelled = PsutilScanner("servers").snapshot(frozenset({"ragent.exe"}))
    plain = PsutilScanner().snapshot(frozenset({"ragent.exe"}))

    assert labelled == plain


def test_scan_is_measured_with_counters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_processes(
        monkeypatch,
        [_FakeProcess(1, "ragent.exe"), _FakeProcess(2, "chrome.exe")],
    )
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    try:
        PsutilScanner("servers").snapshot(frozenset({"ragent.exe"}))
        for handler in logging.getLogger("onecstarter.perf").handlers:
            handler.flush()
        line = path.read_text(encoding="utf-8").strip()
    finally:
        perf.reset_for_tests()
    assert "скан процессов (servers): " in line
    assert "просмотрено=2" in line
    assert "совпало=1" in line


def test_scan_without_label_still_names_the_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(1, "ragent.exe")])
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    try:
        PsutilScanner().snapshot(frozenset({"ragent.exe"}))
        for handler in logging.getLogger("onecstarter.perf").handlers:
            handler.flush()
        line = path.read_text(encoding="utf-8").strip()
    finally:
        perf.reset_for_tests()
    assert "скан процессов: " in line
    assert "()" not in line


def test_scan_writes_nothing_when_perf_is_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(1, "ragent.exe")])
    perf.setup({"APPDATA": str(tmp_path)})
    try:
        PsutilScanner("servers").snapshot(frozenset({"ragent.exe"}))
    finally:
        perf.reset_for_tests()
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()
