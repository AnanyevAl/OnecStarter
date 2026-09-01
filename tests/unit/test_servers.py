"""ServersWorkspace: координатор профилей серверов и их хранения (T-08, T-10)."""

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import ServerConvention, ServerProfile
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.platform_1c.job import Job, JobError
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.platform_1c.server_discovery import ServerInstallation, console_path
from onecstarter.services import server_journal
from onecstarter.services.errors import (
    ConsoleRegistrationDeclinedError,
    ConsoleRegistrationError,
    ServerError,
    UnknownItemError,
)
from onecstarter.services.server_store import load_profiles
from onecstarter.services.servers import SCAN_NAMES, ScanSnapshot, ServersWorkspace, scan_servers

CONV = ServerConvention(
    parse_version("8.2"), "bin", "ragent.exe", "radmin.dll", "common/1CV8 Servers (x86-64).msc"
)


@dataclass
class FakeJob:
    """Job с управляемым списком PID (T-12): `pids_value` — что «живёт» в Job;
    `close()` опустошает список и ставит `closed`; `close_error` — `JobError`,
    который поднимает `close()` вместо закрытия."""  # noqa: RUF002

    pids_value: tuple[int, ...] = ()
    closed: bool = False
    close_error: JobError | None = None
    assigned: list[int] = field(default_factory=list)

    def assign(self, process_handle: int) -> None:
        self.assigned.append(process_handle)

    def pids(self) -> tuple[int, ...]:
        return () if self.closed else self.pids_value

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def is_empty(self) -> bool:
        return not self.pids()


@dataclass
class FakeJobFactory:
    """`job_factory`: новый пустой `FakeJob` на каждый вызов, все созданные — в `created`."""

    created: list[FakeJob] = field(default_factory=list)

    def __call__(self) -> FakeJob:
        job = FakeJob()
        self.created.append(job)
        return job


@dataclass
class FakeServerSpawn:
    """Журнал вызовов `server_spawn` (T-12: третий аргумент — Job запуска).

    Как настоящий `spawn_server`, кладёт «порождённый» `pid` в переданный
    `FakeJob` — после успешного вызова `job.pids()` содержит `pid`.
    `probe`, если задан, вызывается В МОМЕНТ spawn, результат — в `probed`:
    так тест проверяет состояние мира (например, «старый Job уже закрыт»)
    именно на границе порождения, а не после возврата из `start()`.
    """  # noqa: RUF002

    pid: int = 4242
    error: Exception | None = None
    probe: Callable[[], object] | None = None
    calls: list[tuple[str, Path, Job]] = field(default_factory=list)
    probed: list[object] = field(default_factory=list)

    def __call__(self, command: LaunchCommand, log_path: Path, job: Job) -> int:
        self.calls.append((command.command_line, log_path, job))
        if self.probe is not None:
            self.probed.append(self.probe())
        if self.error is not None:
            raise self.error
        if isinstance(job, FakeJob):
            job.pids_value = (*job.pids_value, self.pid)
        return self.pid


@dataclass
class FakeRunElevated:
    """Журнал `(executable, arguments)`, с которыми звали `run_elevated`.

    `exit_code` — что вернуть при успехе; `error`, если задан, — исключение,
    которое `__call__` поднимает вместо возврата (имитация отказа UAC через
    `ElevationDeclinedError`, тот же приём, что `FakeServerSpawn.__call__`).
    """  # noqa: RUF002

    exit_code: int = 0
    error: Exception | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, executable: str, arguments: str) -> int:
        self.calls.append((executable, arguments))
        if self.error is not None:
            raise self.error
        return self.exit_code


@dataclass
class FakeOpenFile:
    """Журнал путей, с которыми звали `open_file`.

    `error`, если задан, — исключение, которое `__call__` поднимает вместо
    обычного успеха (CRITICAL 1c, финальное ревью ветки: `OSError` из
    `os.startfile` обязан переводиться в `ServerError`).
    """  # noqa: RUF002

    error: Exception | None = None
    calls: list[str] = field(default_factory=list)

    def __call__(self, path: str) -> None:
        self.calls.append(path)
        if self.error is not None:
            raise self.error


def _server_installation(
    version: str, ragent: Path, *, arch: Arch = Arch.X64
) -> ServerInstallation:
    installation = Installation(
        version=parse_version(version), path=ragent.parent.parent, arch=arch
    )
    return ServerInstallation(
        installation=installation, ragent=ragent, radmin=ragent.with_name("radmin.dll")
    )


def _installation_in(tmp_path: Path) -> ServerInstallation:
    return _server_installation(
        "8.3.25.1633", tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
    )


def _profile(**overrides: object) -> ServerProfile:
    values: dict[str, str | int | bool] = {
        "id": "",
        "name": "8.3.25 отладка",
        "version": "8.3.25",
        "port": 1540,
        "regport": 1541,
        "range_start": 1560,
        "range_end": 1591,
        "cluster_dir": r"E:\srv\srv_8.3.25.1633",
    }
    values.update(overrides)  # type: ignore[arg-type]
    return ServerProfile(**values)  # type: ignore[arg-type]


def _workspace(
    store_path: Path,
    new_id: object = None,
    job_factory: object = None,
    server_spawn: object = None,
    logs_dir: object = None,
    run_elevated: object = None,
    open_file: object = None,
    registered_radmin: object = None,
    now: object = None,
) -> ServersWorkspace:
    kwargs: dict[str, object] = {
        "job_factory": job_factory if job_factory is not None else FakeJobFactory(),
        "server_spawn": server_spawn if server_spawn is not None else FakeServerSpawn(),
        "logs_dir": logs_dir if logs_dir is not None else store_path.parent / "logs",
    }
    if new_id is not None:
        kwargs["new_id"] = new_id
    if run_elevated is not None:
        kwargs["run_elevated"] = run_elevated
    if open_file is not None:
        kwargs["open_file"] = open_file
    if registered_radmin is not None:
        kwargs["registered_radmin"] = registered_radmin
    if now is not None:
        kwargs["now"] = now
    return ServersWorkspace(store_path, **kwargs)  # type: ignore[arg-type]


@dataclass
class FakeScanner:
    """Снимок из заранее заданного списка `ProcessInfo`, фильтр — как у настоящего.

    `received` запоминает последний набор имён, с которым звали `snapshot`, —
    так тест может проверить, что `scan_servers` действительно просит именно
    `SCAN_NAMES`, а не что-то ещё.
    """  # noqa: RUF002

    processes: list[ProcessInfo]
    received: frozenset[str] | None = field(default=None, init=False)

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        self.received = names
        return [p for p in self.processes if p.name.casefold() in names]


def _agent(
    pid: int,
    argv: tuple[str, ...] | None,
    *,
    exe: str | None = r"C:\Program Files\1cv8\8.3.25.1633\bin\ragent.exe",
) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name="ragent.exe",
        executable=Path(exe) if exe else None,
        argv=argv,
        create_time=100.0 + pid,
    )


def _manager(pid: int, argv: tuple[str, ...] | None) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name="rmngr.exe",
        executable=Path(r"C:\Program Files\1cv8\8.3.25.1633\bin\rmngr.exe"),
        argv=argv,
        create_time=100.0 + pid,
    )


class TestConstructor:
    def test_empty_store_starts_with_no_profiles(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        assert workspace.profiles() == []

    def test_constructor_reads_existing_profiles(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        first = _workspace(store_path, new_id=lambda: "a" * 32)
        first.add_profile(_profile())

        second = _workspace(store_path)
        assert [p.name for p in second.profiles()] == ["8.3.25 отладка"]


class TestDefaultNow:
    def test_default_now_is_local_time(self, tmp_path: Path) -> None:
        """НАХОДКА 2 ручного чек-листа T-10 (Important): дефолт `now`
        конструктора обязан отдавать локальное время, не UTC — журнал
        читает человек рядом с часами Windows, а `app.py` `now` не
        передаёт (дефолт конструктора — то, что реально идёт в прод).
        До этой правки дефолт был `lambda: datetime.now(UTC)` (задача 4):
        в живом прогоне `[05:30:03]` в журнале при 10:30 локальных
        (UTC+5).

        Если локальный часовой пояс машины прогона САМ является UTC,
        разница необнаружима этим тестом — честный `pytest.skip`
        с причиной, а не притворное прохождение.

        Мутация: вернуть дефолт на `datetime.now(UTC)` — тест обязан
        упасть (`utcoffset() == timedelta(0)` вместо локального оффсета).
        """  # noqa: RUF002
        expected_offset = datetime.now().astimezone().utcoffset()
        if expected_offset == timedelta(0):
            pytest.skip("локальный часовой пояс машины прогона — UTC, тест неразличим")
        workspace = _workspace(tmp_path / "servers.json")

        actual = workspace._now()

        assert actual.utcoffset() == expected_offset
        assert actual.utcoffset() != timedelta(0)


class TestAddProfile:
    def test_empty_id_is_assigned_by_new_id(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "b" * 32)
        workspace.add_profile(_profile(id=""))

        assert workspace.profiles()[0].id == "b" * 32

    def test_added_profile_is_persisted_and_reread(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "c" * 32)
        workspace.add_profile(_profile())

        reread = load_profiles(store_path)
        assert len(reread) == 1
        assert reread[0].name == "8.3.25 отладка"
        assert reread[0].id == "c" * 32

        # Второй координатор на том же файле видит то же самое.
        other = _workspace(store_path)
        assert other.profiles() == workspace.profiles()

    def test_explicit_id_duplicate_is_rejected(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "d" * 32)
        workspace.add_profile(_profile(id="d" * 32))

        with pytest.raises(ServerError):
            workspace.add_profile(
                _profile(
                    id="d" * 32,
                    name="дубль",
                    port=2540,
                    regport=2541,
                    cluster_dir=r"E:\srv\other",
                )
            )
        assert len(workspace.profiles()) == 1

    def test_validation_failure_rejects_and_leaves_file_untouched(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "e" * 32)
        workspace.add_profile(_profile())
        before = store_path.read_bytes()

        with pytest.raises(ServerError):
            # Дубль порта с уже сохранённым профилем ([Ф] validate_profile).  # noqa: RUF003
            workspace.add_profile(
                _profile(name="конфликт по порту", cluster_dir=r"E:\srv\other")
            )

        after = store_path.read_bytes()
        assert before == after
        assert len(workspace.profiles()) == 1

    def test_validation_error_message_is_first_error(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path)
        with pytest.raises(ServerError) as excinfo:
            workspace.add_profile(_profile(name="  "))
        assert "имя" in str(excinfo.value).casefold()


class TestUpdateProfile:
    def test_update_changes_profile_and_persists(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "f" * 32)
        workspace.add_profile(_profile())

        updated = replace(workspace.profiles()[0], name="переименован")
        workspace.update_profile(updated)

        assert workspace.profiles()[0].name == "переименован"
        other = _workspace(store_path)
        assert other.profiles()[0].name == "переименован"

    def test_update_unknown_id_is_rejected(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path)
        with pytest.raises(ServerError):
            workspace.update_profile(_profile(id="ghost" * 6))

    def test_update_validates_against_others_not_self(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "g" * 32)
        workspace.add_profile(_profile())

        # Правка того же профиля с теми же портами не должна конфликтовать  # noqa: RUF003
        # сама с собой — others обязаны исключать правимый id.  # noqa: RUF003
        same = workspace.profiles()[0]
        workspace.update_profile(same)
        assert workspace.profiles() == [same]

    def test_update_validation_failure_leaves_file_untouched(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        ids = iter(["h" * 32, "h2" * 16])
        workspace = _workspace(store_path, new_id=lambda: next(ids))
        workspace.add_profile(_profile())
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        before = store_path.read_bytes()

        first, second = workspace.profiles()
        clashing = replace(second, port=first.port)
        with pytest.raises(ServerError):
            workspace.update_profile(clashing)

        after = store_path.read_bytes()
        assert before == after


class TestRematchAfterSave:
    def test_update_rematches_existing_snapshot_without_waiting_for_new_scan(
        self, tmp_path: Path
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        IMPORTANT 6 финального ревью: правка каталога кластера профиля
        обязана пересопоставить УЖЕ ИМЕЮЩИЙСЯ снимок процессов немедленно.
        Без этого `statuses()` продолжал бы показывать процесс СТАРОГО
        каталога как «работает» до следующего планового скана (до 5 с,
        спека §4.4), хотя профиль в файле уже ссылается на другой каталог —
        снимок живых PID не изменился, поменялся только список профилей.
        Мутация: убрать пересопоставление в конце `ServersWorkspace._save` —
        тест обязан упасть (старый процесс останется в `status.processes`).
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "ii" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(111, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        assert workspace.statuses([parse_version("8.3.25.1633")])[0].processes != ()

        updated = replace(profile, cluster_dir=r"E:\srv\new_cluster_dir")
        workspace.update_profile(updated)

        status = workspace.statuses([parse_version("8.3.25.1633")])[0]
        assert status.processes == ()
        # Старый процесс обязан переехать в чужие — тот же снимок, новая
        # классификация по обновлённому списку профилей.
        assert any(f.process.pid == 111 for f in workspace.foreign_servers())

    def test_add_profile_rematches_existing_snapshot(self, tmp_path: Path) -> None:
        """Добавление профиля тоже пересопоставляет снимок: живой процесс,
        случайно уже стоящий на каталоге НОВОГО профиля, обязан сразу
        показаться «работает», а не оставаться в чужих до следующего скана.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "jj" * 16)
        foreign_dir = r"E:\srv\srv_8.3.25.1633"
        agent = _agent(222, ("ragent.exe", "-port", "1540", "-d", foreign_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        assert workspace.foreign_servers()  # процесс пока чужой — профиля ещё нет

        workspace.add_profile(_profile(cluster_dir=foreign_dir))

        status = workspace.statuses([parse_version("8.3.25.1633")])[0]
        assert [p.pid for p in status.processes] == [222]
        assert workspace.foreign_servers() == []


class TestRemoveProfile:
    def test_remove_deletes_and_persists(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "i" * 32)
        workspace.add_profile(_profile())

        workspace.remove_profile("i" * 32)

        assert workspace.profiles() == []
        other = _workspace(store_path)
        assert other.profiles() == []

    def test_remove_unknown_id_is_rejected(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path)
        with pytest.raises(ServerError):
            workspace.remove_profile("ghost" * 6)


class TestFailedSaveRollsBackMemory:
    def test_failed_save_rolls_back_memory(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        Отказ записи не должен разойтись с памятью: экран, построенный
        по `profiles()`, обязан показывать то же, что реально лежит
        в файле, — иначе пользователь увидит профиль, которого на диске
        нет (образец — `Workspace._store_user`, CLAUDE.md §5 «правки»).
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "j" * 32)
        workspace.add_profile(_profile())
        assert len(workspace.profiles()) == 1

        # Честный способ уронить следующую запись на Windows: убрать файл
        # и создать на его месте каталог с тем же именем — Path.replace  # noqa: RUF003
        # временного файла поверх каталога падает OSError.
        store_path.unlink()
        store_path.mkdir()

        with pytest.raises(ServerError):
            workspace.add_profile(
                _profile(name="второй", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
            )

        # Память не разошлась с (недоступным для перезаписи) диском:  # noqa: RUF003
        # прежний список из одного профиля, а не два.  # noqa: RUF003
        names = [p.name for p in workspace.profiles()]
        assert names == ["8.3.25 отладка"]


class TestScanServers:
    def test_splits_agents_and_managers_by_name(self) -> None:
        agent = _agent(1, ("ragent.exe", "-port", "2540", "-d", r"E:\srv\a"))
        manager = _manager(2, ("rmngr.exe", "-port", "1541"))
        other = ProcessInfo(pid=3, name="rphost.exe", executable=None, argv=None, create_time=1.0)
        scanner = FakeScanner([agent, manager, other])

        snapshot = scan_servers(scanner)

        # rphost/dbda не входят в SCAN_NAMES ([Ф] Б1) — scan_servers обязан
        # спросить у сканера именно этот набор, а не всё подряд.  # noqa: RUF003
        assert scanner.received == SCAN_NAMES
        assert snapshot.agents == (agent,)
        assert snapshot.managers == (manager,)


class TestScanPending:
    def test_pending_before_and_after_apply_scan(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        assert workspace.scan_pending is True

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
        assert workspace.scan_pending is False

    def test_statuses_before_scan_are_empty_not_stopped(self, tmp_path: Path) -> None:
        """До первого apply_scan снимка нет вовсе — это не то же самое, что «пусто»."""
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "k" * 32)
        workspace.add_profile(_profile())

        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert status.processes == ()
        assert status.port_holders == ()
        assert status.job_pids == ()
        assert workspace.foreign_servers() == []


class TestStatuses:
    def test_running_with_one_process(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "l" * 32)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(
            100,
            ("ragent.exe", "-port", "1540", "-regport", "1541", "-d", profile.cluster_dir),
        )

        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert [p.pid for p in status.processes] == [100]

    def test_stopped_with_zero_processes(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "l2" * 16)
        workspace.add_profile(_profile())

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert status.processes == ()

    def test_two_processes_on_same_profile(self, tmp_path: Path) -> None:
        # Комментарий по мокапу T-08: при 2 живых процессах кнопка «Стоп»
        # становится неактивна в UI — состав самого snapshot это не меняет,
        # но статус обязан отдать оба процесса, а не один.  # noqa: RUF003
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "l3" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent1 = _agent(101, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        agent2 = _agent(102, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir + "\\"))

        workspace.apply_scan(ScanSnapshot(agents=(agent1, agent2), managers=()))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert {p.pid for p in status.processes} == {101, 102}

    def test_resolved_by_mask_against_installed(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "l4" * 16)
        workspace.add_profile(_profile(version="8.3.25"))
        installed = [parse_version("8.3.25.1560"), parse_version("8.3.25.1633")]

        status = workspace.statuses(installed)[0]

        assert status.resolved == parse_version("8.3.25.1633")


class TestForeignServers:
    def test_foreign_before_scan_is_empty(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        assert workspace.foreign_servers() == []

    def test_foreign_with_and_without_argv(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "m" * 32)
        workspace.add_profile(_profile())  # cluster_dir E:\srv\srv_8.3.25.1633
        # Видимый чужой: другой каталог, argv читается — версия и параметры есть.
        visible = _agent(200, ("ragent.exe", "-port", "9999", "-d", r"D:\other\cluster"))
        # [Ф] В1 — непрозрачный чужой/служба: exe и argv недоступны,  # noqa: RUF003
        # версия и параметры честно None, а не выдуманы.  # noqa: RUF003
        opaque = _agent(201, None, exe=None)

        workspace.apply_scan(ScanSnapshot(agents=(visible, opaque), managers=()))
        foreign = {f.process.pid: f for f in workspace.foreign_servers()}

        assert len(foreign) == 2
        assert foreign[200].version is not None
        assert foreign[200].params is not None
        assert foreign[201].version is None
        assert foreign[201].params is None


class TestDirMismatch:
    def test_true_when_leaf_dir_version_differs_from_resolved(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "r" * 32)
        workspace.add_profile(_profile(version="8.3.25", cluster_dir=r"E:\srv\srv_8.3.25.1560"))
        installed = [parse_version("8.3.25.1560"), parse_version("8.3.25.1633")]

        status = workspace.statuses(installed)[0]

        assert status.resolved == parse_version("8.3.25.1633")
        assert status.dir_mismatch is True

    def test_false_when_exact_version_and_matching_dir(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "s" * 32)
        workspace.add_profile(
            _profile(version="8.3.25.1633", cluster_dir=r"E:\srv\srv_8.3.25.1633")
        )
        installed = [parse_version("8.3.25.1633")]

        status = workspace.statuses(installed)[0]

        assert status.dir_mismatch is False

    def test_false_when_leaf_dir_has_no_version_number(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "t" * 32)
        workspace.add_profile(_profile(version="8.3.25", cluster_dir=r"E:\srv\cluster"))
        installed = [parse_version("8.3.25.1633")]

        status = workspace.statuses(installed)[0]

        assert status.dir_mismatch is False


class TestStart:
    def test_start_builds_command_byte_exact_and_spawns(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(
            store_path, new_id=lambda: "u" * 32, server_spawn=spawn, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        pid = workspace.start(profile.id, [installation])

        assert pid == 4242
        assert len(spawn.calls) == 1
        command_line, log_path, _job = spawn.calls[0]
        assert command_line == (
            f'"{ragent}" -debug -http -port 1540 -regport 1541 '
            r"-range 1560:1591 -d E:\srv\srv_8.3.25.1633"
        )
        assert log_path == server_journal.journal_path(logs_dir, profile.id)

    def test_start_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.start("ghost" * 6, [])

    def test_start_refuses_when_version_not_installed(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        spawn = FakeServerSpawn()
        workspace = _workspace(store_path, new_id=lambda: "v" * 32, server_spawn=spawn)
        workspace.add_profile(_profile(version="8.3.99"))
        profile = workspace.profiles()[0]

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [])

        # Сообщение обязано называть именно запрошенную версию — иначе
        # пользователь не поймёт, что заводить установку не той версии.
        assert "8.3.99" in str(excinfo.value)
        assert spawn.calls == []

    def test_start_refuses_when_already_running(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        §6.4: второй `ragent` на том же каталоге кластера не запускается
        нами никогда — платформа не гарантирует безопасное поведение при
        двух `ragent` на одном `-d`. `FakeServerSpawn.calls` обязан остаться
        пустым — отказ ДО порождения, без частичных эффектов.
        Мутация: убрать проверку снимка перед `spawn` — тест обязан упасть.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        spawn = FakeServerSpawn()
        workspace = _workspace(store_path, new_id=lambda: "w" * 32, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerError):
            workspace.start(profile.id, [_installation_in(tmp_path)])

        assert spawn.calls == []

    def test_start_wraps_spawn_oserror_in_servererror(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        CRITICAL 1a финального ревью: `OSError` из `self._server_spawn(...)`
        уходил бы наружу голым — мимо `ServicesError`, единственного типа,
        который ловит слой представления (UI ловит `ServicesError`, а не
        `Exception`), и падал бы трассировкой пользователю. Тот же приём,
        что `services/launch.py::launch_infobase` — `ServerError` с текстом
        отказа и командной строкой (секретов в ней нет, §8 спеки).
        Мутация: убрать `try/except OSError` вокруг `self._server_spawn(...)` —
        тест обязан упасть непойманным `OSError`.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        spawn = FakeServerSpawn(error=OSError("не удалось создать процесс"))
        workspace = _workspace(store_path, new_id=lambda: "ax" * 16, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

        assert str(ragent) in str(excinfo.value)
        assert len(spawn.calls) == 1

    def test_start_wraps_job_error_in_servererror(self, tmp_path: Path) -> None:
        """`JobError` (T-10, задача 2 — отказ `job.assign()` внутри `spawn_server`)
        переводится в `ServerError` тем же путём, что `OSError` (см. тест выше):
        `services` не выпускает наружу голых исключений `platform_1c`.
        """
        store_path = tmp_path / "servers.json"
        spawn = FakeServerSpawn(error=JobError("AssignProcessToJobObject отказал"))
        workspace = _workspace(store_path, new_id=lambda: "bc" * 16, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [_installation_in(tmp_path)])

        assert "AssignProcessToJobObject" in str(excinfo.value)

    def test_start_rotates_journal_and_logs_command(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        Прошлый журнал не теряется, команда записана (T-10, задача 4, спека
        §12.6): `start` обязан ротировать журнал профиля (текущий → `.1.log`)
        и записать событие `запуск: <командная строка>` в НОВЫЙ текущий
        журнал ДО вызова `server_spawn` — тем же файлом, в который
        `spawn_server` затем перенаправит stdout дерева процессов.
        Мутация: убрать вызов `rotate_journal`/`append_event` перед
        `self._server_spawn(...)` в `start` — тест обязан упасть (нет
        `.1.log` со старым содержимым, либо в новом журнале нет строки
        запуска).
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(
            store_path, new_id=lambda: "az" * 16, server_spawn=spawn, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        current = server_journal.journal_path(logs_dir, profile.id)
        previous = server_journal.previous_journal_path(logs_dir, profile.id)
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text("прошлый запуск\n", encoding="utf-8")
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        pid = workspace.start(profile.id, [installation])

        assert previous.read_text(encoding="utf-8") == "прошлый запуск\n"
        content = current.read_text(encoding="utf-8")
        assert f'запуск: "{ragent}" -debug -http -port 1540' in content
        # Important 1 финального ревью ветки T-10: событие "порождён PID"
        # обязано появиться в журнале после успешного server_spawn — тем же
        # приёмом, что и "запуск: …" выше.
        assert f"порождён PID {pid}" in content

    def test_start_survives_rotation_failure_when_previous_journal_is_locked(
        self, tmp_path: Path
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        Important 1 финального ревью ветки T-10: `Path.replace` внутри
        `rotate_journal` падает `PermissionError [WinError 32]`, если журнал
        ещё держит открытым процесс прошлого запуска (`dbgs`/`rmngr`,
        переживший `ragent`, снятый из Диспетчера задач без штатной
        остановки) — Python `open()` не даёт `FILE_SHARE_DELETE`. Держатель
        здесь настоящий: подставной ребёнок-python со stdout, перенаправленным
        в ТЕКУЩИЙ журнал, — тот же честный способ занять файл на Windows, что
        и `TestFailedSaveRollsBackMemory` использует для каталога. Раньше
        `rotate_journal` стоял в общем `try` со spawn — любой `OSError` (в
        том числе отсюда) переводился в «отказ запуска» и `ServerError`,
        и профиль было не запустить, хотя причина вообще не в spawn. `start`
        обязан продолжить как обычно: запись о неудавшейся ротации в журнал,
        затем `запуск: …`, `server_spawn` и `порождён PID` — без исключения.

        Правка координатора (после первой волны исправлений): событие несёт
        ФАКТИЧЕСКИЙ текст исключения (`str(error)`), а не предполагаемую
        причину — `"WinError 32"` в проверке ниже подтверждён ЭКСПЕРИМЕНТОМ
        на этой машине (реальный `PermissionError` от держателя файла),
        а не взят из документации или домысла.
        Мутация: вернуть `rotate_journal` внутрь общего
        `try/except (OSError, JobError)` вместе со spawn — тест обязан
        упасть `ServerError`.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(
            store_path, new_id=lambda: "bd" * 16, server_spawn=spawn, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        current = server_journal.journal_path(logs_dir, profile.id)
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text("прошлый запуск\n", encoding="utf-8")
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        holder_stdout = current.open("ab")
        holder = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=holder_stdout,
        )
        holder_stdout.close()
        try:
            pid = workspace.start(profile.id, [installation])
        finally:
            holder.kill()
            holder.wait()

        assert pid == 4242
        content = current.read_text(encoding="utf-8")
        assert "прошлый запуск" in content
        assert "ротация журнала не удалась" in content
        # Текст исключения — фактический (str(error) от системы), не наша
        # догадка о причине: на Windows PermissionError от занятого файла  # noqa: RUF003
        # реально несёт "WinError 32" (проверено этим же тестом на живом
        # держателе, не взято из документации).
        assert "WinError 32" in content
        assert f'запуск: "{ragent}" -debug -http -port 1540' in content
        assert f"порождён PID {pid}" in content
        # Ротация действительно не удалась — файла .1.log нет, старое
        # содержимое осталось в текущем файле (см. asserts выше).
        assert not server_journal.previous_journal_path(logs_dir, profile.id).exists()

    def test_failed_spawn_logs_the_refusal(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        Отказ `server_spawn` обязан попасть в журнал профиля ДО того, как
        `ServerError` уйдёт наружу — иначе панель «Журнал профиля» (T-10,
        задача 5) не покажет пользователю причину отказа старта.
        Мутация: убрать запись события `отказ запуска` в обработчике
        `except (OSError, JobError)` внутри `start` — тест обязан упасть
        (строки «отказ запуска» в журнале не будет, хотя `ServerError`
        всё ещё поднимется).
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(error=OSError("не удалось создать процесс"))
        workspace = _workspace(
            store_path, new_id=lambda: "ba" * 16, server_spawn=spawn, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        with pytest.raises(ServerError):
            workspace.start(profile.id, [_installation_in(tmp_path)])

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ запуска" in content
        assert "не удалось создать процесс" in content


class TestStartWithJob:
    def test_start_creates_a_job_per_launch_and_records_spawned_pid(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ja" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        pid = workspace.start(profile.id, [_installation_in(tmp_path)])

        assert pid == 4242
        assert len(factory.created) == 1
        assert spawn.calls[0][2] is factory.created[0]
        status = workspace.statuses([])[0]
        assert status.job_pids == (4242,)
        assert status.spawned_pid == 4242
        assert workspace.running_count() == 1

    def test_start_refuses_while_own_ragent_is_alive_in_job(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: истина о нашем ragent — Job, не снимок (спека T-12 §3).

        Второй `start()` сразу после первого (снимка ещё не было) обязан
        отказать по `spawned_pid in job.pids()`, не порождая второй ragent.
        Мутация: убрать проверку живого ragent в Job — тест обязан упасть
        (второй spawn состоится).
        """  # noqa: RUF002
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jb" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

        assert "4242" in str(excinfo.value)
        assert len(spawn.calls) == 1
        assert len(factory.created) == 1

    def test_start_with_remnants_closes_old_job_before_spawn_and_logs(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: решение 2 (29.08.2026) — «Запустить» при остатках
        прошлого дерева гасит их САМ (закрывает старый Job) ДО spawn и пишет
        `погашены остатки прошлого запуска: PID …`.
        Мутация: перенести `old_job.close()` после `server_spawn` (или убрать) —
        `spawn.probed[0]` станет `False`.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jc" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        old = factory.created[0]
        old.pids_value = (4300, 4301)  # ragent 4242 снят извне, дети остались
        spawn.pid = 4343
        spawn.probe = lambda: old.closed

        pid = workspace.start(profile.id, [installation])

        assert pid == 4343
        assert spawn.probed == [True]
        assert spawn.calls[1][2] is factory.created[1]
        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "погашены остатки прошлого запуска: PID 4300, 4301" in content
        assert content.index("погашены остатки") < content.index("запуск:")
        status = workspace.statuses([])[0]
        assert status.job_pids == (4343,)
        assert status.spawned_pid == 4343

    def test_start_refuses_when_a_foreign_process_holds_the_profile_port(
        self, tmp_path: Path
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: чужой держатель порта (спека T-12 §4) — отказ ДО
        ротации и spawn, событие `отказ запуска: порт регистрации …`.
        Мутация: убрать проверку `port_holders` в `start` — тест обязан упасть
        (spawn состоится, прошлый журнал уедет в `.1.log`).
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn()
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jd" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())  # regport=1541
        profile = workspace.profiles()[0]
        current = server_journal.journal_path(logs_dir, profile.id)
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text("прошлый запуск\n", encoding="utf-8")
        holder = _manager(300, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(holder,)))

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [_installation_in(tmp_path)])

        expected = "порт регистрации 1541 занят PID 300 (запущен не лаунчером)"
        assert expected in str(excinfo.value)
        assert spawn.calls == []
        assert factory.created == []
        assert not server_journal.previous_journal_path(logs_dir, profile.id).exists()
        content = current.read_text(encoding="utf-8")
        assert "прошлый запуск" in content
        assert f"отказ запуска: {expected}" in content

    def test_start_does_not_treat_own_remnants_as_port_holders(self, tmp_path: Path) -> None:
        """Остаток НАШЕГО дерева (PID в нашем Job) в снимке с нашим regport —
        не чужой держатель: запуск проходит, остатки гасятся (решение 2)."""  # noqa: RUF002
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "je" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        factory.created[0].pids_value = (4300,)
        remnant = _manager(4300, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(remnant,)))
        assert workspace.port_holders(profile.id) == []

        workspace.start(profile.id, [installation])

        assert factory.created[0].closed is True
        assert len(spawn.calls) == 2

    def test_start_spawn_failure_closes_the_fresh_job_and_forgets_it(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(error=OSError("не удалось создать процесс"))
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jf" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        with pytest.raises(ServerError):
            workspace.start(profile.id, [_installation_in(tmp_path)])

        assert factory.created[0].closed is True
        assert workspace.statuses([])[0].job_pids == ()
        assert workspace.running_count() == 0

    def test_start_reports_failed_remnant_close_and_keeps_remnants(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jg" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        old = factory.created[0]
        old.pids_value = (4300,)
        old.close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

        assert "CloseHandle отказал" in str(excinfo.value)
        assert len(spawn.calls) == 1
        assert workspace.statuses([])[0].job_pids == (4300,)
        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ запуска: не удалось погасить остатки прошлого запуска" in content

    def test_failed_remnant_close_keeps_spawned_pid(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: отказ гашения возвращает и Job, и порождённый PID.

        Долг T-12, п. 4: `_spawned.pop` сделан ДО `old_job.close()`, и в ветке
        `JobError` в `_jobs` Job возвращается, а порождённый PID — нет. Откат
        обязан быть симметричным: иначе `spawned_pid` теряется, и событие
        «ragent завершился извне» в этом окне реконсиляции уже не с чего
        записать — забывать нечего. Мутация: не возвращать `_spawned` —
        тест обязан упасть.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jh" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        assert workspace.statuses([])[0].spawned_pid == 4242

        old = factory.created[0]
        old.pids_value = (4300,)
        old.close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError):
            workspace.start(profile.id, [installation])

        assert workspace.statuses([])[0].spawned_pid == 4242

    def test_failed_remnant_close_without_pids_omits_empty_pid_list(
        self, tmp_path: Path
    ) -> None:
        """Пустой Job не даёт «(PID )» в тексте отказа (долг T-12, п. 4).

        `pids_text` собирается из `job_pids`; когда старый Job уже пуст,
        а `close()` всё равно отказал, пользователь получал «остатки прошлого
        запуска (PID ) не погашены» — скобку с пустым списком.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ji" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])

        old = factory.created[0]
        old.pids_value = ()
        old.close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

        assert "(PID )" not in str(excinfo.value)
        assert "CloseHandle отказал" in str(excinfo.value)


class TestStopWithJob:
    def test_stop_closes_only_this_profiles_job(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: `stop()` закрывает Job ИМЕННО этого профиля; сосед
        жив. Мутация: закрывать все Job — тест обязан упасть.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        ids = iter(["ka" * 16, "kb" * 16])
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: next(ids),
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        first, second = workspace.profiles()
        installation = _installation_in(tmp_path)
        workspace.start(first.id, [installation])
        spawn.pid = 4343
        workspace.start(second.id, [installation])

        workspace.stop(first.id)

        assert factory.created[0].closed is True
        assert factory.created[1].closed is False
        statuses = {s.profile.id: s for s in workspace.statuses([])}
        assert statuses[first.id].job_pids == ()
        assert statuses[first.id].spawned_pid is None
        assert statuses[second.id].job_pids == (4343,)
        content = server_journal.journal_path(logs_dir, first.id).read_text(encoding="utf-8")
        assert "остановка по команде пользователя" in content

    def test_stop_without_job_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "kc" * 16)
        workspace.add_profile(_profile())
        with pytest.raises(ServerError):
            workspace.stop(workspace.profiles()[0].id)

    def test_stop_ignores_a_foreign_matched_ragent(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: решение 4 — совпавший по каталогу ЧУЖОЙ ragent не
        останавливается: Job нет → `ServerError`, ни одного Job не создано.
        Мутация: вернуть остановку по совпавшим процессам снимка — упадёт.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        workspace = _workspace(
            tmp_path / "servers.json", new_id=lambda: "kd" * 16, job_factory=factory
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

        assert factory.created == []

    def test_stop_with_empty_job_raises_and_forgets_it(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ke" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        factory.created[0].pids_value = ()  # дерево умерло целиком

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

        assert factory.created[0].closed is True
        assert workspace.running_count() == 0

    def test_stop_close_failure_logs_refusal_and_raises_server_error(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "kf" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        factory.created[0].close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ остановки" in content
        assert "CloseHandle отказал" in content
        assert workspace.statuses([])[0].job_pids == (4242,)  # Job остался — остатки видны


class TestRemoveProfileStopsJob:
    def test_remove_running_profile_closes_its_job(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: решение 3 — удаление работающего профиля = остановка.
        Мутация: убрать `stop()` из `remove_profile` — Job останется открытым.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "la" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])

        workspace.remove_profile(profile.id)

        assert factory.created[0].closed is True
        assert workspace.profiles() == []
        assert workspace.running_count() == 0

    def test_remove_profile_keeps_it_when_job_close_fails(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "lb" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        factory.created[0].close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError):
            workspace.remove_profile(profile.id)

        assert [p.id for p in workspace.profiles()] == [profile.id]


class TestPortHoldersInWorkspace:
    def test_empty_before_scan(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ma" * 16)
        workspace.add_profile(_profile())
        assert workspace.port_holders(workspace.profiles()[0].id) == []

    def test_foreign_rmngr_on_regport_is_a_holder(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "mb" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        holder = _manager(300, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(holder,)))
        assert [h.pid for h in workspace.port_holders(profile.id)] == [300]
        assert [h.pid for h in workspace.statuses([])[0].port_holders] == [300]

    def test_holders_suppressed_while_a_matched_ragent_is_alive(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "mc" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(
            700, ("ragent.exe", "-port", "1540", "-regport", "1541", "-d", profile.cluster_dir)
        )
        manager = _manager(701, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=(manager,)))
        assert workspace.port_holders(profile.id) == []

    def test_unknown_profile_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnknownItemError):
            _workspace(tmp_path / "servers.json").port_holders("ghost" * 6)


class TestStop:
    def test_stop_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.stop("ghost" * 6)

    def test_stop_success_logs_event(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(
            store_path, new_id=lambda: "ad" * 16, server_spawn=spawn, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])

        workspace.stop(profile.id)

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "остановка по команде пользователя" in content


class TestJournalPath:
    def test_journal_path_for_known_profile(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        workspace = _workspace(store_path, new_id=lambda: "gj" * 16, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        assert workspace.journal_path(profile.id) == logs_dir / f"{profile.id}.log"

    def test_journal_path_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.journal_path("ghost" * 6)


class TestLogEvent:
    def test_log_event_appends_with_timestamp(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        stamp = datetime.fromisoformat("2026-08-28T09:05:07")
        workspace = _workspace(
            store_path, new_id=lambda: "gk" * 16, logs_dir=logs_dir, now=lambda: stamp
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        workspace.log_event(profile.id, "тестовое событие")

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert content == "[09:05:07] тестовое событие\n"

    def test_log_event_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.log_event("ghost" * 6, "текст")

    def test_log_event_swallows_oserror(self, tmp_path: Path) -> None:
        """`OSError` из записи журнала не мешает вызывающему (T-10, задача 4):
        единственное место в модуле, где отказ ФС не поднимает исключение.
        Каталог на месте файла журнала — честный способ уронить `open("a")`
        (тот же приём, что `TestFailedSaveRollsBackMemory`).
        """
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        workspace = _workspace(store_path, new_id=lambda: "gl" * 16, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        journal = server_journal.journal_path(logs_dir, profile.id)
        journal.mkdir(parents=True)

        workspace.log_event(profile.id, "не должно упасть")  # не поднимает исключение


class TestLogShutdown:
    """НАХОДКА 4 ручного чек-листа T-10 (Minor): выход не оставлял следа в
    журнале — дерево гасит ОС (Job kill-on-close), кода остановки нет
    (§12.4), и конец сессии читателю журнала не виден. `log_shutdown`
    закрывает эту дыру: пишет одно событие в журнал КАЖДОГО профиля
    с НЕПУСТЫМ Job (T-12 — «работает» значит «запущен нами и жив», снимок
    в этом вопросе не участвует).
    """  # noqa: RUF002

    def test_writes_only_to_running_profiles_and_returns_their_count(
        self, tmp_path: Path
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        Два профиля, из них один запущен нами (непустой Job) — `log_shutdown`
        обязан дописать событие ТОЛЬКО в его журнал и вернуть `1`, не
        создавая журнал у профиля без Job.
        Мутация: перебирать `self._profiles` без проверки `_job_pids`
        (писать всем без разбора) — тест обязан упасть на `not exists()`
        журнала простаивающего профиля.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        ids = iter(["ha" * 16, "hb" * 16])
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(
            store_path, new_id=lambda: next(ids), server_spawn=spawn, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())  # cluster_dir E:\srv\srv_8.3.25.1633
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        running, idle = workspace.profiles()
        workspace.start(running.id, [_installation_in(tmp_path)])

        count = workspace.log_shutdown()

        assert count == 1
        running_journal = server_journal.journal_path(logs_dir, running.id).read_text(
            encoding="utf-8"
        )
        assert "выход лаунчера — сервер будет остановлен вместе с ним" in running_journal  # noqa: RUF001
        assert not server_journal.journal_path(logs_dir, idle.id).exists()

    def test_ignores_a_foreign_matched_ragent(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: долг T-10 — событие выхода писалось и ЧУЖОМУ
        процессу, совпавшему по каталогу; мы его не останавливаем, значит
        и «будет остановлен вместе с ним» о нём — неправда.
        Мутация: считать по `_matched_processes` — тест обязан упасть.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        workspace = _workspace(store_path, new_id=lambda: "he" * 16, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        assert workspace.log_shutdown() == 0
        assert not server_journal.journal_path(logs_dir, profile.id).exists()

    def test_returns_zero_before_any_scan(self, tmp_path: Path) -> None:
        """До первого `apply_scan` — та же семантика, что у `running_count`:
        Job ни у кого нет, писать в журнал некому.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "hc" * 16)
        workspace.add_profile(_profile())

        assert workspace.log_shutdown() == 0

    def test_returns_zero_after_scan_with_nothing_running(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        workspace = _workspace(store_path, new_id=lambda: "hd" * 16, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        assert workspace.log_shutdown() == 0


class TestRunningCount:
    def test_zero_without_jobs(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "na" * 16)
        workspace.add_profile(_profile())
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
        assert workspace.running_count() == 0

    def test_counts_profiles_with_a_non_empty_job(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        ids = iter(["nb" * 16, "nc" * 16])
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: next(ids),
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        first, _second = workspace.profiles()
        workspace.start(first.id, [_installation_in(tmp_path)])
        assert workspace.running_count() == 1
        factory.created[0].pids_value = ()
        assert workspace.running_count() == 0

    def test_ignores_a_foreign_matched_ragent(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: долг T-10 — вопрос выхода считал ЧУЖИЕ процессы,
        совпавшие по каталогу; мы их не остановим, считать нельзя.
        Мутация: считать по `_match.by_profile` — тест обязан упасть.
        """  # noqa: RUF002
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "nd" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        assert workspace.running_count() == 0


class TestCurrentConsoleVersion:
    def test_none_when_console_not_registered(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", registered_radmin=lambda: None)
        assert workspace.current_console_version() is None

    def test_version_parsed_from_registered_radmin_path(self, tmp_path: Path) -> None:
        path = Path(r"C:\Program Files\1cv8\8.3.25.1633\bin\radmin.dll")
        workspace = _workspace(tmp_path / "servers.json", registered_radmin=lambda: path)

        assert workspace.current_console_version() == parse_version("8.3.25.1633")


class TestRegisterConsole:
    def test_success_calls_run_elevated_with_expected_arguments(self, tmp_path: Path) -> None:
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        target = _server_installation("8.3.25.1633", ragent)
        run_elevated = FakeRunElevated(exit_code=0)
        workspace = _workspace(tmp_path / "servers.json", run_elevated=run_elevated)

        workspace.register_console(target)

        assert run_elevated.calls == [("regsvr32", f'/s "{target.radmin}"')]

    def test_nonzero_exit_code_raises_with_code_in_message(self, tmp_path: Path) -> None:
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        target = _server_installation("8.3.25.1633", ragent)
        run_elevated = FakeRunElevated(exit_code=3)
        workspace = _workspace(tmp_path / "servers.json", run_elevated=run_elevated)

        with pytest.raises(ConsoleRegistrationError) as excinfo:
            workspace.register_console(target)
        assert "3" in str(excinfo.value)

    def test_elevation_declined_is_reported_as_normal_outcome(self, tmp_path: Path) -> None:
        """Отказ UAC — штатный исход §7, а не ошибка программы.

        `ElevationDeclinedError` (из `platform_1c.elevation`) обязан
        транслироваться в `ConsoleRegistrationDeclinedError`, а не всплывать
        голым и не превращаться в `ConsoleRegistrationError`, — UI различает
        эти два случая текстом сообщения (T-08 §7).
        """  # noqa: RUF002
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        target = _server_installation("8.3.25.1633", ragent)
        run_elevated = FakeRunElevated(error=ElevationDeclinedError("отказ пользователя"))
        workspace = _workspace(tmp_path / "servers.json", run_elevated=run_elevated)

        with pytest.raises(ConsoleRegistrationDeclinedError):
            workspace.register_console(target)


class TestOpenConsole:
    def test_open_console_opens_msc_from_root(self, tmp_path: Path) -> None:
        open_file = FakeOpenFile()
        workspace = _workspace(tmp_path / "servers.json", open_file=open_file)

        workspace.open_console(tmp_path, CONV)

        assert open_file.calls == [str(console_path(tmp_path, CONV))]

    def test_open_console_wraps_oserror_in_servererror(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        CRITICAL 1c финального ревью: `OSError` из `os.startfile` (файла
        `.msc` нет, нет ассоциации) обязан переводиться в `ServerError`,
        а не всплывать голым мимо `ServicesError`-ловцов UI.
        Мутация: убрать `try/except OSError` вокруг `self._open_file(...)` —
        тест обязан упасть непойманным `OSError`.
        """  # noqa: RUF002
        open_file = FakeOpenFile(error=OSError("файл не найден"))
        workspace = _workspace(tmp_path / "servers.json", open_file=open_file)

        with pytest.raises(ServerError):
            workspace.open_console(tmp_path, CONV)

        assert open_file.calls == [str(console_path(tmp_path, CONV))]


class TestNothingRegistersWithoutExplicitCall:
    def test_nothing_registers_without_explicit_call(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        §7: регистрация консоли (UAC-повышение) зовётся ТОЛЬКО из явного
        действия пользователя в UI — конструктор, `apply_scan`, `statuses`
        и `foreign_servers` не имеют права коснуться `run_elevated` даже
        краем, иначе пользователь увидит диалог UAC при простом открытии
        раздела «Серверы». Журнал фейка обязан остаться пустым после всех
        операций, которые НЕ являются `register_console`.
        Мутация: вызвать `run_elevated` из конструктора или `apply_scan` —
        тест обязан упасть.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        run_elevated = FakeRunElevated()
        workspace = _workspace(
            store_path, new_id=lambda: "ff" * 16, run_elevated=run_elevated
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(
            999, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir)
        )

        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        workspace.statuses([parse_version("8.3.25.1633")])
        workspace.foreign_servers()

        assert run_elevated.calls == []


class TestReconcileOnScan:
    """Спека T-12 §4: обнаружение остатков — на снимке монитора, событие один раз."""

    def _running(
        self, tmp_path: Path, prefix: str
    ) -> tuple[ServersWorkspace, FakeJobFactory, ServerProfile]:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: prefix * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=tmp_path / "logs")
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        return workspace, factory, profile

    def test_external_ragent_death_is_logged_once(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: переход «ragent был в Job → его нет, Job не пуст»
        пишется в журнал РОВНО один раз, `spawned_pid` после него — `None`.
        Мутация: не забывать `spawned_pid` после события — второй снимок
        напишет его ещё раз.
        """  # noqa: RUF002
        workspace, factory, profile = self._running(tmp_path, "ra")
        factory.created[0].pids_value = (4300, 4301)  # ragent 4242 снят извне

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        content = server_journal.journal_path(tmp_path / "logs", profile.id).read_text(
            encoding="utf-8"
        )
        assert content.count("ragent завершился извне; остатки дерева: PID 4300, 4301") == 1
        status = workspace.statuses([])[0]
        assert status.spawned_pid is None
        assert status.job_pids == (4300, 4301)
        assert workspace.running_count() == 1  # остатки — всё ещё наш Job (гейт выхода)

    def test_job_whose_tree_is_gone_is_released(self, tmp_path: Path) -> None:
        workspace, factory, profile = self._running(tmp_path, "rb")
        factory.created[0].pids_value = ()

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        assert factory.created[0].closed is True
        status = workspace.statuses([])[0]
        assert status.job_pids == () and status.spawned_pid is None
        assert workspace.running_count() == 0
        content = server_journal.journal_path(tmp_path / "logs", profile.id).read_text(
            encoding="utf-8"
        )
        assert "завершился извне" not in content

    def test_healthy_job_stays_silent(self, tmp_path: Path) -> None:
        workspace, _factory, profile = self._running(tmp_path, "rc")

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        assert workspace.statuses([])[0].spawned_pid == 4242
        content = server_journal.journal_path(tmp_path / "logs", profile.id).read_text(
            encoding="utf-8"
        )
        assert "завершился извне" not in content
