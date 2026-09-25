"""Тесты сканера процессов: `NullScanner` и `WindowsProcessScanner`.

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
from onecstarter.platform_1c.process_scan import NullScanner, WindowsProcessScanner
from onecstarter.platform_1c.process_snapshot import SnapshotError


@pytest.fixture(autouse=True)
def _reset_snapshot_cache() -> Iterator[None]:
    """Кэш снимка — состояние модуля, общее на весь процесс `pytest`.

    Сброс только в хелпере `_with_snapshot` защищал бы лишь тех, кто через
    него проходит: живые тесты `TestWindowsProcessScanner` зовут настоящий
    `snapshot_all()` напрямую и кэш не трогают вовсе, поэтому мокнутый снимок
    соседнего теста (с настоящей отметкой времени) в пределах окна в 2 с
    достался бы им бесплатно и без всякого отношения к правде. Автоприменяемая
    фикстура сбрасывает кэш и до, и после каждого теста файла — изоляция не
    зависит от того, какой тест был перед этим и через какой хелпер он шёл.
    """  # noqa: RUF002
    process_scan.reset_snapshot_cache()
    yield
    process_scan.reset_snapshot_cache()


class TestNullScanner:
    def test_snapshot_is_always_empty(self) -> None:
        assert NullScanner().snapshot(frozenset({"ragent.exe", "rmngr.exe"})) == []


class TestWindowsProcessScanner:
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
        result = WindowsProcessScanner().snapshot(frozenset({name}))
        found = next((p for p in result if p.pid == fake_process.pid), None)
        assert found is not None
        assert found.argv is not None
        assert "-port" in found.argv
        assert "9999" in found.argv

    def test_unrelated_name_does_not_match_fake_process(
        self, fake_process: psutil.Process
    ) -> None:
        result = WindowsProcessScanner().snapshot(frozenset({"нет-такого.exe"}))
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


def _with_snapshot(
    monkeypatch: pytest.MonkeyPatch, entries: list[tuple[int, str]]
) -> None:
    # Сброс здесь — не про изоляцию между тестами (её теперь даёт файловая  # noqa: RUF003
    # автофикстура `_reset_snapshot_cache`), а про повторный вызов ВНУТРИ  # noqa: RUF003
    # одного теста: `test_same_pid_with_new_name_is_read_again` и
    # `test_cache_drops_processes_missing_from_snapshot` зовут `_with_snapshot`
    # дважды, чтобы подменить снимок на лету, — без сброса второй вызов  # noqa: RUF003
    # получил бы кэш первого (оба в пределах TTL) и не заметил бы подмену.  # noqa: RUF003
    process_scan.reset_snapshot_cache()
    monkeypatch.setattr(process_scan, "snapshot_all", lambda: list(entries))


def _with_processes(
    monkeypatch: pytest.MonkeyPatch, processes: list[_FakeProcess]
) -> None:
    """Снимок и чтение деталей — оба из одного и того же списка фейков.

    Список процессов даёт `snapshot_all()`, а `psutil.Process(pid)` зовёт только
    у совпавших по имени (задача 2, спека 3.2.2 «снимок процессов» §3) — поэтому
    подмена стоит на обеих точках сразу.
    """  # noqa: RUF002
    by_pid = {process.pid: process for process in processes}
    entries = [(pid, str(proc.info["name"])) for pid, proc in by_pid.items()]
    _with_snapshot(monkeypatch, entries)
    monkeypatch.setattr(process_scan, "_process_by_pid", lambda pid: by_pid[pid])


def test_details_are_read_only_for_matching_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matching = _FakeProcess(1, "ragent.exe")
    others = [_FakeProcess(pid, f"chrome{pid}.exe") for pid in range(2, 40)]
    _with_processes(monkeypatch, [matching, *others])

    result = WindowsProcessScanner().snapshot(frozenset({"ragent.exe"}))

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

    found = WindowsProcessScanner().snapshot(frozenset({"ragent.exe"}))[0]

    assert found.executable is None
    assert found.argv == ("ragent", "-port", "1540")


def test_access_denied_on_cmdline_keeps_the_exe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Зеркало test_access_denied_on_one_field_keeps_the_other: там недоступен
    # exe, здесь — cmdline. Общий try вокруг обоих чтений потерял бы доступный
    # exe у процесса с недоступным cmdline — та же ловушка, с другой стороны.  # noqa: RUF003
    process = _FakeProcess(
        8,
        "ragent.exe",
        exe=r"C:\1cv8\bin\ragent.exe",
        cmdline_error=psutil.AccessDenied,
    )
    _with_processes(monkeypatch, [process])

    found = WindowsProcessScanner().snapshot(frozenset({"ragent.exe"}))[0]

    assert found.executable == Path(r"C:\1cv8\bin\ragent.exe")
    assert found.argv is None


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

    assert WindowsProcessScanner().snapshot(frozenset({"ragent.exe"})) == []


def test_label_is_accepted_and_does_not_change_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(3, "ragent.exe")])

    labelled = WindowsProcessScanner("servers").snapshot(frozenset({"ragent.exe"}))
    plain = WindowsProcessScanner().snapshot(frozenset({"ragent.exe"}))

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
        WindowsProcessScanner("servers").snapshot(frozenset({"ragent.exe"}))
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
        WindowsProcessScanner().snapshot(frozenset({"ragent.exe"}))
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
        WindowsProcessScanner("servers").snapshot(frozenset({"ragent.exe"}))
    finally:
        perf.reset_for_tests()
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()


def test_details_are_read_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(1, "ragent.exe")
    _with_snapshot(monkeypatch, [(1, "ragent.exe"), (2, "chrome.exe")])
    monkeypatch.setattr(process_scan, "_process_by_pid", lambda pid: process)

    scanner = WindowsProcessScanner()
    first = scanner.snapshot(frozenset({"ragent.exe"}))
    second = scanner.snapshot(frozenset({"ragent.exe"}))

    assert first == second
    assert process.detail_calls == 2  # exe + cmdline, ОДИН раз на оба скана  # noqa: RUF003


def test_same_pid_with_new_name_is_read_again(monkeypatch: pytest.MonkeyPatch) -> None:
    # Windows переиспользует PID. Без сверки имени кэш подставил бы данные
    # умершего процесса живому — и мы отрапортовали бы о работающем сервере,  # noqa: RUF003
    # которого нет.
    first_process = _FakeProcess(7, "ragent.exe", argv=["ragent", "-port", "1540"])
    second_process = _FakeProcess(7, "rmngr.exe", argv=["rmngr", "-port", "1541"])
    holder = {"current": first_process}
    monkeypatch.setattr(process_scan, "_process_by_pid", lambda pid: holder["current"])

    scanner = WindowsProcessScanner()
    _with_snapshot(monkeypatch, [(7, "ragent.exe")])
    assert scanner.snapshot(frozenset({"ragent.exe", "rmngr.exe"}))[0].name == "ragent.exe"

    holder["current"] = second_process
    _with_snapshot(monkeypatch, [(7, "rmngr.exe")])
    result = scanner.snapshot(frozenset({"ragent.exe", "rmngr.exe"}))[0]

    assert result.name == "rmngr.exe"
    assert result.argv == ("rmngr", "-port", "1541")
    assert second_process.detail_calls == 2


def test_cache_drops_processes_missing_from_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Без удаления кэш рос бы на каждом умершем процессе: 17 тысяч сканов  # noqa: RUF003
    # в сутки — тысячи мёртвых записей.
    monkeypatch.setattr(
        process_scan, "_process_by_pid", lambda pid: _FakeProcess(pid, "ragent.exe")
    )
    scanner = WindowsProcessScanner()
    _with_snapshot(monkeypatch, [(1, "ragent.exe"), (2, "ragent.exe")])
    scanner.snapshot(frozenset({"ragent.exe"}))
    assert scanner.cached_pids() == {1, 2}

    _with_snapshot(monkeypatch, [(2, "ragent.exe")])
    scanner.snapshot(frozenset({"ragent.exe"}))
    assert scanner.cached_pids() == {2}


def test_access_denied_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    # Недоступный чужой процесс — именно тот, кто дорог: без кэша он платил бы
    # пошлину на каждом скане вечно.
    process = _FakeProcess(
        3, "ragent.exe", exe_error=psutil.AccessDenied, cmdline_error=psutil.AccessDenied
    )
    _with_snapshot(monkeypatch, [(3, "ragent.exe")])
    monkeypatch.setattr(process_scan, "_process_by_pid", lambda pid: process)

    scanner = WindowsProcessScanner()
    scanner.snapshot(frozenset({"ragent.exe"}))
    scanner.snapshot(frozenset({"ragent.exe"}))

    assert process.detail_calls == 2  # один раз на оба скана  # noqa: RUF003
    assert scanner.snapshot(frozenset({"ragent.exe"}))[0].executable is None


def test_snapshot_failure_gives_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> list[tuple[int, str]]:
        raise SnapshotError(5, "нет доступа")

    monkeypatch.setattr(process_scan, "snapshot_all", boom)
    assert WindowsProcessScanner().snapshot(frozenset({"ragent.exe"})) == []


class _Clock:
    """Часы под управлением теста: ждать настоящие секунды незачем."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_snapshot_is_shared_between_scanners_within_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Два монитора тикают почти одновременно (по логам сервера — 22-80 мс),
    # и второй обязан получить снимок бесплатно.
    calls = {"n": 0}

    def counting() -> list[tuple[int, str]]:
        calls["n"] += 1
        return [(1, "ragent.exe")]

    monkeypatch.setattr(process_scan, "snapshot_all", counting)
    monkeypatch.setattr(process_scan, "_process_by_pid", lambda pid: _FakeProcess(1, "ragent.exe"))
    clock = _Clock()
    process_scan.reset_snapshot_cache()

    servers = WindowsProcessScanner("servers", clock=clock)
    edt = WindowsProcessScanner("edt", clock=clock)
    servers.snapshot(frozenset({"ragent.exe"}))
    clock.now += 0.05
    edt.snapshot(frozenset({"1cedt.exe"}))

    assert calls["n"] == 1


def test_snapshot_is_taken_again_after_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def counting() -> list[tuple[int, str]]:
        calls["n"] += 1
        return [(1, "ragent.exe")]

    monkeypatch.setattr(process_scan, "snapshot_all", counting)
    monkeypatch.setattr(process_scan, "_process_by_pid", lambda pid: _FakeProcess(1, "ragent.exe"))
    clock = _Clock()
    process_scan.reset_snapshot_cache()

    scanner = WindowsProcessScanner("servers", clock=clock)
    scanner.snapshot(frozenset({"ragent.exe"}))
    clock.now += 3.0
    scanner.snapshot(frozenset({"ragent.exe"}))

    assert calls["n"] == 2
