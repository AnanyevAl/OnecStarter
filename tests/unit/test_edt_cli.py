"""EdtCli: одна команда на запись, журнал с ротацией, прерывание, отказы (спека §14.4)."""  # noqa: RUF002

from datetime import datetime
from itertools import count
from pathlib import Path

import pytest

from onecstarter.domain.edt import EditorResolution, EdtInstallation, EdtProject
from onecstarter.domain.edt_cli import WorkspaceEntry
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import Job
from onecstarter.platform_1c.server_spawn import LoggedProcess
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.services.edt_cli import CliResult, EdtCli, workspace_entries
from onecstarter.services.errors import EdtError

EXE_DIR = Path(r"C:\edt\1c-edt-2025.2.6+4-x86_64")
JDK = Path(r"C:\jdk\bin")
INSTALLED = [
    EdtInstallation("2025.2.6+4", EXE_DIR / "1cedt.exe", JDK, "-Xmx8192m", 17, "products.json")
]
NOW = datetime(2026, 9, 10, 12, 0, 0)


class FakeJob:
    def __init__(self) -> None:
        self.assigned: list[int] = []
        self.closed = False

    def assign(self, process_handle: int) -> None:
        self.assigned.append(process_handle)

    def pids(self) -> tuple[int, ...]:
        return () if self.closed else (4242,)

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    """Достаточная часть Popen: pid и код завершения для CliRun."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


class Harness:
    def __init__(self, tmp_path: Path, *, cli_exists: bool = True) -> None:
        ids = count(1)
        self.spawned: list[tuple[LaunchCommand, Path]] = []
        self.jobs: list[FakeJob] = []
        self.workspace = EdtWorkspace(
            tmp_path / "edt.json",
            discover=lambda: list(INSTALLED),
            edtstart=lambda: None,
            editors=lambda kind: EditorResolution(None, "", "x"),
            spawn=lambda c: 1,
            activate=lambda p: True,
            open_file=lambda p: None,
            new_id=lambda: f"id-{next(ids)}",
        )
        self.workspace.refresh_installations()

        def spawn(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess:
            # Дописываем, а не перезаписываем: настоящий spawn_logged отдаёт ребёнку  # noqa: RUF003
            # хендл FILE_APPEND_DATA и никогда не обрезает журнал (находка ревью
            # Task 3: фейк с write_text стирал события, записанные до spawn).  # noqa: RUF003
            self.spawned.append((command, log_path))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as journal:
                journal.write("вывод cli\n")
            return LoggedProcess(pid=4242, process=FakeProcess(4242))  # type: ignore[arg-type]

        def job_factory() -> Job:
            job = FakeJob()
            self.jobs.append(job)
            return job

        self.cli = EdtCli(
            self.workspace,
            tmp_path / "logs" / "edt",
            job_factory=job_factory,
            spawn=spawn,
            is_file=lambda p: cli_exists and p.name == "1cedtcli.exe",
            now=lambda: NOW,
        )

    def project(self, **overrides: object) -> EdtProject:
        values: dict[str, object] = {
            "id": "",
            "name": "a",
            "workspace": r"D:\edt\a",
            "edt_version": "2025.2.6+4",
        }
        values.update(overrides)
        return self.workspace.add_project(EdtProject(**values))  # type: ignore[arg-type]


class TestStart:
    def test_start_builds_command_rotates_journal_and_marks_busy(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project(vm_args="-Xmx4g")
        old = h.cli.journal_path(p.id)
        old.parent.mkdir(parents=True)
        old.write_text("прошлый\n", encoding="utf-8")
        run = h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        assert run.pid == 4242 and run.label == "Пересобрать проекты"
        [(command, log_path)] = h.spawned
        assert command.executable == EXE_DIR / "1cedtcli.exe"
        assert '-command "build --yes"' in command.arguments
        assert "-Xmx8192m -Djava.library.path= -Xmx4g" in command.arguments
        assert log_path == h.cli.journal_path(p.id)
        assert (old.parent / f"{p.id}.1.log").read_text(encoding="utf-8") == "прошлый\n"
        text = log_path.read_text(encoding="utf-8")
        assert "[12:00:00] ▶ Пересобрать проекты: build --yes" in text
        assert str(command.executable) in text
        # Порядок в журнале: событие старта и командная строка — ДО вывода ребёнка
        # (спека §14.4; servers.py пишет «запуск:» до spawn_server тем же приёмом).
        assert text.index("▶ Пересобрать проекты") < text.index("вывод cli")
        assert h.workspace.status(p.id).cli_busy is True
        assert h.cli.running_count() == 1

    def test_second_start_on_same_project_refused(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        with pytest.raises(EdtError, match="уже выполняется"):
            h.cli.start(p.id, "Информация по проектам", "project")
        assert len(h.spawned) == 1

    def test_running_edt_refused_before_spawn(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={}))
        assert h.cli.unavailable_reason(p.id) == "Закройте EDT: workspace занят"
        with pytest.raises(EdtError, match="workspace занят"):
            h.cli.start(p.id, "Информация по проектам", "project")
        assert h.spawned == []

    def test_missing_cli_exe_refused(self, tmp_path: Path) -> None:
        h = Harness(tmp_path, cli_exists=False)
        p = h.project()
        reason = h.cli.unavailable_reason(p.id)
        assert reason == "В установке 2025.2.6+4 нет 1cedtcli.exe"  # noqa: RUF001
        with pytest.raises(EdtError):
            h.cli.start(p.id, "Информация по проектам", "project")

    def test_version_not_installed_refused(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project(edt_version="2024.2.6+7")
        assert h.cli.unavailable_reason(p.id) == "EDT 2024.2.6+7 не найден среди установок"

    def test_spawn_oserror_becomes_edt_error_and_not_busy(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()

        def broken(command: LaunchCommand, log_path: Path, job: Job) -> LoggedProcess:
            raise OSError("нет файла")

        h.cli = EdtCli(
            h.workspace,
            tmp_path / "logs",
            job_factory=FakeJob,
            spawn=broken,
            is_file=lambda p: True,
            now=lambda: NOW,
        )
        with pytest.raises(EdtError):
            h.cli.start(p.id, "Информация по проектам", "project")
        assert h.workspace.status(p.id).cli_busy is False
        assert h.cli.running_count() == 0
        journal = h.cli.journal_path(p.id).read_text(encoding="utf-8")
        assert "▶ Информация по проектам: project" in journal  # что пытались запустить
        assert "■ не запущен: OSError" in journal


class TestFinishAndInterrupt:
    def test_finish_writes_code_clears_busy_keeps_result(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Проверить проекты", "validate …", result_file=r"D:\r.tsv")
        h.cli.finish(p.id, 0)
        assert h.workspace.status(p.id).cli_busy is False
        assert h.cli.run(p.id) is None
        assert h.cli.last_result(p.id) == CliResult("Проверить проекты", 0, False, r"D:\r.tsv")
        journal = h.cli.journal_path(p.id).read_text(encoding="utf-8")
        assert "[12:00:00] ■ завершено, код 0" in journal
        assert h.jobs[0].closed is True

    def test_interrupt_closes_job_and_marks_interrupted(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        h.cli.interrupt(p.id)
        assert h.jobs[0].closed is True
        assert h.cli.last_result(p.id) == CliResult("Пересобрать проекты", None, True, "")
        assert h.workspace.status(p.id).cli_busy is False
        assert "■ прервано пользователем" in h.cli.journal_path(p.id).read_text(encoding="utf-8")

    def test_finish_after_interrupt_is_noop(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        h.cli.interrupt(p.id)
        h.cli.finish(p.id, 1)
        assert h.cli.last_result(p.id) == CliResult("Пересобрать проекты", None, True, "")

    def test_log_shutdown_marks_live_runs(self, tmp_path: Path) -> None:
        h = Harness(tmp_path)
        p = h.project()
        h.cli.start(p.id, "Пересобрать проекты", "build --yes")
        assert h.cli.log_shutdown() == 1
        journal = h.cli.journal_path(p.id).read_text(encoding="utf-8")
        assert "■ прервано выходом из программы" in journal


def test_workspace_entries_marks_dot_project(tmp_path: Path) -> None:
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / ".project").write_text("", encoding="utf-8")
    (tmp_path / ".metadata").mkdir()
    (tmp_path / "file.txt").write_text("", encoding="utf-8")
    entries = workspace_entries(str(tmp_path))
    assert entries == [
        WorkspaceEntry(".metadata", str(tmp_path / ".metadata"), False),
        WorkspaceEntry("conf", str(tmp_path / "conf"), True),
    ]


def test_workspace_entries_missing_dir_is_empty(tmp_path: Path) -> None:
    assert workspace_entries(str(tmp_path / "nope")) == []
