from onecstarter.services.edt_cli import CliRun
from onecstarter.ui.edt.cli_watch import CliWatcher


class FakeProcess:
    def __init__(self, code: int) -> None:
        self.pid = 1
        self._code = code

    def wait(self, timeout: float | None = None) -> int:
        return self._code


class FakeJob:
    def assign(self, process_handle: int) -> None: ...
    def pids(self) -> tuple[int, ...]:
        return ()
    def close(self) -> None: ...


def _run(code: int) -> CliRun:
    return CliRun(
        "p1",
        "Пересобрать проекты",
        "build --yes",
        1,
        FakeProcess(code),  # type: ignore[arg-type]
        FakeJob(),
        "",
    )


def test_watch_emits_run_and_exit_code(qapp) -> None:  # type: ignore[no-untyped-def]
    watcher = CliWatcher(spawn=lambda task: task())
    got: list[tuple[object, object]] = []
    watcher.finished.connect(lambda run, code: got.append((run, code)))
    run = _run(3)
    watcher.watch(run)
    assert len(got) == 1
    assert got[0][0] is run  # сам объект run, не id — см. интерфейс
    assert got[0][1] == 3


def test_wait_failure_emits_none(qapp) -> None:  # type: ignore[no-untyped-def]
    class Broken(FakeProcess):
        def wait(self, timeout: float | None = None) -> int:
            raise OSError("хендл закрыт")

    run = CliRun("p1", "x", "project", 1, Broken(0), FakeJob(), "")  # type: ignore[arg-type]
    watcher = CliWatcher(spawn=lambda task: task())
    got: list[object] = []
    watcher.finished.connect(lambda finished_run, code: got.append(code))
    watcher.watch(run)
    assert got == [None]
