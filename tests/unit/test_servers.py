"""ServersWorkspace: координатор профилей серверов и их хранения (T-08, T-10)."""

import subprocess
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import ServerConvention, ServerProfile
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.platform_1c.job import JobError
from onecstarter.platform_1c.process_control import ProcessAccessError, ProcessMismatchError
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.platform_1c.server_discovery import ServerInstallation, console_path
from onecstarter.services import server_journal
from onecstarter.services.errors import (
    ConsoleRegistrationDeclinedError,
    ConsoleRegistrationError,
    ServerError,
    ServerStopError,
    UnknownItemError,
)
from onecstarter.services.server_store import load_profiles
from onecstarter.services.servers import SCAN_NAMES, ScanSnapshot, ServersWorkspace, scan_servers

CONV = ServerConvention(
    parse_version("8.2"), "bin", "ragent.exe", "radmin.dll", "common/1CV8 Servers (x86-64).msc"
)


@dataclass
class FakeControl:
    """ProcessControl с детьми по словарю `pid -> [ProcessInfo]` и журналом вызовов.

    `mismatched` — pid-ы, на которых `terminate` кидает `ProcessMismatchError`
    (гонка PID, §6.2) вместо обычного успеха. `access_denied` — pid-ы, на
    которых `terminate` кидает `ProcessAccessError` (CRITICAL 1b, финальное
    ревью ветки: `psutil.AccessDenied` — процесс другого пользователя или
    службы). Запись в `calls` для `terminate` добавляется ДО проверки на
    несовпадение/отказ прав — так тест видит, что попытка была (ровно одна),
    а не просто отсутствие последствий.
    """  # noqa: RUF002

    children_map: dict[int, list[ProcessInfo]] = field(default_factory=dict)
    mismatched: frozenset[int] = field(default_factory=frozenset)
    access_denied: frozenset[int] = field(default_factory=frozenset)
    calls: list[tuple[str, int]] = field(default_factory=list)

    def children(self, pid: int) -> list[ProcessInfo]:
        self.calls.append(("children", pid))
        return list(self.children_map.get(pid, []))

    def terminate(self, pid: int, expected_create_time: float) -> None:
        self.calls.append(("terminate", pid))
        if pid in self.mismatched:
            raise ProcessMismatchError(
                f"pid {pid}: create_time не совпадает с ожидаемым — PID переиспользован"  # noqa: RUF001
            )
        if pid in self.access_denied:
            raise ProcessAccessError(f"pid {pid}: нет прав на завершение процесса")


@dataclass
class FakeServerSpawn:
    """Журнал `(command_line, log_path)`, с которыми звали `server_spawn`; отдаёт `pid`.

    Сигнатура — `Callable[[LaunchCommand, Path], int]` (T-10, задача 4):
    журнал хранит `command.command_line` (строку), а не сам `LaunchCommand`
    — так тест сравнивает байт-в-байт собранную командную строку, не завися
    от идентичности объекта. `error`, если задан, — исключение, которое
    `__call__` поднимает вместо возврата `pid`: `OSError` (CRITICAL 1a,
    финальное ревью ветки T-08 — обязан переводиться в `ServerError`) или
    `JobError` (T-10, задача 2 — отказ `job.assign()` внутри `spawn_server`,
    тот же перевод), тот же приём, что `FakeRunElevated`.
    """  # noqa: RUF002

    pid: int = 4242
    error: Exception | None = None
    calls: list[tuple[str, Path]] = field(default_factory=list)

    def __call__(self, command: LaunchCommand, log_path: Path) -> int:
        self.calls.append((command.command_line, log_path))
        if self.error is not None:
            raise self.error
        return self.pid


@dataclass
class FakeRunElevated:
    """Журнал `(executable, arguments)`, с которыми звали `run_elevated`.

    `exit_code` — что вернуть при успехе; `error`, если задан, — исключение,
    которое `__call__` поднимает вместо возврата (имитация отказа UAC через
    `ElevationDeclinedError`, тот же приём, что `FakeControl.terminate`).
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
    control: object = None,
    server_spawn: object = None,
    logs_dir: object = None,
    run_elevated: object = None,
    open_file: object = None,
    registered_radmin: object = None,
    now: object = None,
) -> ServersWorkspace:
    kwargs: dict[str, object] = {
        "control": control if control is not None else FakeControl(),
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
        assert status.orphans == ()
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


class TestOrphanManagers:
    def test_orphan_manager_is_reported(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        rmngr, сидящий на regport профиля, без живого ragent обязан попасть
        в orphans — иначе следующий запуск того же профиля молча умрёт
        об уже занятый порт ([Ф] А3, t07-protocol.md).
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "n" * 32)
        workspace.add_profile(_profile())  # regport=1541
        profile = workspace.profiles()[0]
        manager = _manager(300, ("rmngr.exe", "-port", "1541"))

        workspace.apply_scan(ScanSnapshot(agents=(), managers=(manager,)))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert [o.pid for o in status.orphans] == [300]
        assert [o.pid for o in workspace.orphan_managers(profile.id)] == [300]

    def test_orphan_managers_unknown_profile_raises(self, tmp_path: Path) -> None:
        """Неизвестный `profile_id` — явный отказ, а не тихий `[]`.

        Манера слоя services — `Workspace.find_by_name`/`_item`: тихая пустота
        замаскировала бы программную ошибку вызывающего под честное «сирот
        нет».
        """  # noqa: RUF002
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.orphan_managers("ghost" * 6)

    def test_orphan_manager_matched_by_cluster_dir(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "o" * 32)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        # Порт rmngr здесь не совпадает ни с чем — совпасть обязан каталог кластера.  # noqa: RUF003
        manager = _manager(400, ("rmngr.exe", "-port", "9999", "-d", profile.cluster_dir))

        workspace.apply_scan(ScanSnapshot(agents=(), managers=(manager,)))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert [o.pid for o in status.orphans] == [400]

    def test_orphan_not_reported_when_agent_is_running(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "p" * 32)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(
            500,
            ("ragent.exe", "-port", "1540", "-regport", "1541", "-d", profile.cluster_dir),
        )
        manager = _manager(501, ("rmngr.exe", "-port", "1541"))

        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=(manager,)))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert status.orphans == ()

    def test_manager_with_none_argv_is_skipped(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "q" * 32)
        workspace.add_profile(_profile())
        manager = _manager(600, None)

        workspace.apply_scan(ScanSnapshot(agents=(), managers=(manager,)))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert status.orphans == ()

    def test_orphan_excluded_when_it_sits_on_a_live_foreign_agents_directory(
        self, tmp_path: Path
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        IMPORTANT 5 финального ревью: rmngr на НАШЕМ `regport`, чей `-d`
        указывает на каталог ЖИВОГО чужого ragent того же снимка, не
        сирота — он держит порт живого чужого кластера, а не забытый порт
        нашего профиля. Раньше `-port`-эвристика предложила бы «Погасить»
        такой rmngr только из-за коллизии портов, убив часть чужого
        работающего дерева.
        Мутация: убрать проверку `live_agent_dirs` в `_orphans_for` — тест
        обязан упасть (rmngr снова попадёт в orphans).
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "gg" * 16)
        workspace.add_profile(_profile())  # regport=1541
        foreign_dir = r"D:\foreign\cluster"
        foreign_agent = _agent(700, ("ragent.exe", "-port", "9999", "-d", foreign_dir))
        candidate = _manager(701, ("rmngr.exe", "-port", "1541", "-d", foreign_dir))

        workspace.apply_scan(ScanSnapshot(agents=(foreign_agent,), managers=(candidate,)))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert status.orphans == ()

    def test_regression_a3_orphan_still_reported_without_live_agents(
        self, tmp_path: Path
    ) -> None:
        """Регресс-контроль IMPORTANT 5: измеренный сирота А3 остаётся сиротой.

        rmngr на нашем `regport`, без `-d` вовсе, и БЕЗ живых агентов
        в снимке — сценарий А3 (t07-protocol.md): `ragent` на занятом
        порту умер, `rmngr` остался сиротой. Новая проверка «живых
        каталогов» не должна поглотить этот случай — при пустом
        `self._snapshot.agents` `live_agent_dirs` пуст, и старая
        `-port`-эвристика обязана сработать как раньше.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "hh" * 16)
        workspace.add_profile(_profile())  # regport=1541
        manager = _manager(702, ("rmngr.exe", "-port", "1541"))

        workspace.apply_scan(ScanSnapshot(agents=(), managers=(manager,)))
        status = workspace.statuses([parse_version("8.3.25.1633")])[0]

        assert [o.pid for o in status.orphans] == [702]


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
        command_line, log_path = spawn.calls[0]
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
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        with pytest.raises(ServerError):
            workspace.start(profile.id, [installation])

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
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

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
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        with pytest.raises(ServerError):
            workspace.start(profile.id, [installation])

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ запуска" in content
        assert "не удалось создать процесс" in content


class TestStop:
    def test_stop_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.stop("ghost" * 6)

    def test_stop_without_snapshot_raises(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "x" * 32)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

    def test_stop_without_matched_process_raises(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "y" * 32)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

    def test_stop_kills_exactly_matched_pid_and_children(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        [Ф] Б2: `TerminateProcess` не убивает детей — дерево обязано
        гаситься целиком. Проверяем и состав (ровно PID профиля + его
        дети из `children()`, чужой ragent из того же снимка не тронут),
        и порядок (снимок детей ДО убийства родителя — иначе можно
        упустить ребёнка, порождённого между снимком и `terminate`).
        Мутация: поменять местами вызовы `children()`/`terminate()`
        или тронуть чужой PID — тест обязан упасть.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        agent_pid = 800
        child = ProcessInfo(
            pid=801, name="rmngr.exe", executable=None, argv=None, create_time=555.0
        )
        control = FakeControl(children_map={agent_pid: [child]})
        workspace = _workspace(store_path, new_id=lambda: "z" * 32, control=control)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(agent_pid, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        # Чужой ragent того же снимка — другой каталог, профилю не сопоставлен.
        foreign = _agent(900, ("ragent.exe", "-port", "9999", "-d", r"D:\other\cluster"))
        workspace.apply_scan(ScanSnapshot(agents=(agent, foreign), managers=()))

        workspace.stop(profile.id)

        assert control.calls == [
            ("children", agent_pid),
            ("terminate", agent_pid),
            ("terminate", child.pid),
        ]

    def test_stop_mismatched_create_time_raises_and_kills_nobody(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        §6.2, гонка PID: `create_time` агента разошёлся со снимком — PID
        переиспользован системой. `ServerStopError`, не завершение чужого
        процесса; терминация агента упала ДО детей, поэтому реальных
        убийств — ровно 0, и журнал `terminate` содержит только одну
        (неудавшуюся) попытку — по агенту, дети вообще не тронуты.
        Мутация: заменить `raise` на `pass`/`continue` в обработчике
        `ProcessMismatchError` — тест обязан упасть.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        agent_pid = 850
        child = ProcessInfo(
            pid=851, name="rmngr.exe", executable=None, argv=None, create_time=555.0
        )
        control = FakeControl(
            children_map={agent_pid: [child]}, mismatched=frozenset({agent_pid})
        )
        workspace = _workspace(store_path, new_id=lambda: "aa" * 16, control=control)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(agent_pid, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerStopError):
            workspace.stop(profile.id)

        assert control.calls == [("children", agent_pid), ("terminate", agent_pid)]

    def test_stop_mismatched_child_also_raises_honestly(self, tmp_path: Path) -> None:
        """Ребёнок, а не агент, попал под гонку PID — тоже честный отказ.

        Спека: несовпадение `create_time` ребёнка тоже обязано дойти до
        вызывающего как `ServerStopError`, а не проглатываться молча —
        иначе пользователь решит, что дерево остановлено целиком, хотя
        часть его жива.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        agent_pid = 860
        child = ProcessInfo(
            pid=861, name="rmngr.exe", executable=None, argv=None, create_time=555.0
        )
        control = FakeControl(
            children_map={agent_pid: [child]}, mismatched=frozenset({child.pid})
        )
        workspace = _workspace(store_path, new_id=lambda: "bb" * 16, control=control)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(agent_pid, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerStopError):
            workspace.stop(profile.id)

        # Агент успел завершиться (не в mismatched), ребёнок — нет.
        assert control.calls == [
            ("children", agent_pid),
            ("terminate", agent_pid),
            ("terminate", child.pid),
        ]

    def test_stop_access_denied_raises_server_stop_error(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ.

        CRITICAL 1b финального ревью: `ProcessAccessError` (перевод
        `psutil.AccessDenied` из `PsutilControl.terminate`, процесс другого
        пользователя или службы) обязан переводиться в `ServerStopError`
        слоя `services`, а не всплывать голым исключением `platform_1c` мимо
        `ServicesError`-ловцов UI.
        Мутация: убрать `except ProcessAccessError` из `_terminate_or_raise` —
        тест обязан упасть непойманным `ProcessAccessError`.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        agent_pid = 870
        control = FakeControl(access_denied=frozenset({agent_pid}))
        workspace = _workspace(store_path, new_id=lambda: "ac" * 16, control=control)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(agent_pid, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerStopError) as excinfo:
            workspace.stop(profile.id)

        assert str(agent_pid) in str(excinfo.value)
        assert control.calls == [("children", agent_pid), ("terminate", agent_pid)]

    def test_stop_success_logs_event(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        agent_pid = 880
        workspace = _workspace(store_path, new_id=lambda: "ad" * 16, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(agent_pid, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        workspace.stop(profile.id)

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "остановка по команде пользователя" in content

    def test_stop_failure_logs_refusal_before_raise(self, tmp_path: Path) -> None:
        """Отказ остановки (гонка PID, §6.2) обязан попасть в журнал ДО
        `raise` — иначе панель «Журнал профиля» (T-10, задача 5) не покажет
        причину отказа."""
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        agent_pid = 890
        control = FakeControl(mismatched=frozenset({agent_pid}))
        workspace = _workspace(
            store_path, new_id=lambda: "ae" * 16, control=control, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(agent_pid, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerStopError):
            workspace.stop(profile.id)

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ остановки" in content
        assert str(agent_pid) in content


class TestStopOrphans:
    def test_stop_orphans_terminates_only_this_profiles_orphans(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        control = FakeControl()
        ids = iter(["cc" * 16, "dd" * 16])
        workspace = _workspace(store_path, new_id=lambda: next(ids), control=control)
        workspace.add_profile(_profile())  # regport=1541
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        profile, _other = workspace.profiles()
        own_orphan = _manager(950, ("rmngr.exe", "-port", "1541"))
        other_orphan = _manager(951, ("rmngr.exe", "-port", "2541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(own_orphan, other_orphan)))

        workspace.stop_orphans(profile.id)

        assert control.calls == [("terminate", 950)]

    def test_stop_orphans_empty_is_noop(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        control = FakeControl()
        workspace = _workspace(
            store_path, new_id=lambda: "ee" * 16, control=control, logs_dir=logs_dir
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        workspace.stop_orphans(profile.id)  # без апасений — сирот нет, значит нет и вызовов

        assert control.calls == []
        # Гасить было нечего — событие в журнал не пишется (нет даже файла).
        assert not server_journal.journal_path(logs_dir, profile.id).exists()

    def test_stop_orphans_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.stop_orphans("ghost" * 6)

    def test_stop_orphans_success_logs_event_with_pids(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        logs_dir = tmp_path / "logs"
        workspace = _workspace(store_path, new_id=lambda: "ge" * 16, logs_dir=logs_dir)
        workspace.add_profile(_profile())  # regport=1541
        profile = workspace.profiles()[0]
        orphan = _manager(960, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(orphan,)))

        workspace.stop_orphans(profile.id)

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "гашение сирот: PID 960" in content


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


class TestRunningCount:
    def test_zero_before_scan(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        assert workspace.running_count() == 0

    def test_counts_profiles_with_at_least_one_process(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        ids = iter(["gm" * 16, "gn" * 16])
        workspace = _workspace(store_path, new_id=lambda: next(ids))
        workspace.add_profile(_profile())  # cluster_dir E:\srv\srv_8.3.25.1633
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        profile, _other = workspace.profiles()
        # Два процесса на ОДНОМ профиле считаются один раз — число профилей,
        # не процессов; второй профиль без процессов не учитывается.
        agent1 = _agent(970, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        agent2 = _agent(971, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir + "\\"))
        workspace.apply_scan(ScanSnapshot(agents=(agent1, agent2), managers=()))

        assert workspace.running_count() == 1

    def test_zero_after_scan_with_nothing_running(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        workspace = _workspace(store_path, new_id=lambda: "go" * 16)
        workspace.add_profile(_profile())
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

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
