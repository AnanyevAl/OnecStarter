"""ServersWorkspace: координатор профилей серверов и их хранения (T-08, задачи 10-12)."""

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import ServerProfile
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.process_control import ProcessMismatchError
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.services.errors import ServerError, ServerStopError, UnknownItemError
from onecstarter.services.server_store import load_profiles
from onecstarter.services.servers import SCAN_NAMES, ScanSnapshot, ServersWorkspace, scan_servers


@dataclass
class FakeControl:
    """ProcessControl с детьми по словарю `pid -> [ProcessInfo]` и журналом вызовов.

    `mismatched` — pid-ы, на которых `terminate` кидает `ProcessMismatchError`
    (гонка PID, §6.2) вместо обычного успеха. Запись в `calls` для `terminate`
    добавляется ДО проверки на несовпадение — так тест видит, что попытка
    была (ровно одна), а не просто отсутствие последствий.
    """  # noqa: RUF002

    children_map: dict[int, list[ProcessInfo]] = field(default_factory=dict)
    mismatched: frozenset[int] = field(default_factory=frozenset)
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


@dataclass
class FakeSpawn:
    """Журнал `LaunchCommand`, с которыми звали `spawn`; возвращает заданный `pid`."""  # noqa: RUF002

    pid: int = 4242
    calls: list[LaunchCommand] = field(default_factory=list)

    def __call__(self, command: LaunchCommand) -> int:
        self.calls.append(command)
        return self.pid


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
    spawn: object = None,
) -> ServersWorkspace:
    kwargs: dict[str, object] = {"control": control if control is not None else FakeControl()}
    if new_id is not None:
        kwargs["new_id"] = new_id
    if spawn is not None:
        kwargs["spawn"] = spawn
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
        spawn = FakeSpawn(pid=4242)
        workspace = _workspace(store_path, new_id=lambda: "u" * 32, spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        pid = workspace.start(profile.id, [installation])

        assert pid == 4242
        assert len(spawn.calls) == 1
        command = spawn.calls[0]
        assert command.executable == ragent
        assert command.command_line == (
            f'"{ragent}" -debug -http -port 1540 -regport 1541 '
            r"-range 1560:1591 -d E:\srv\srv_8.3.25.1633"
        )

    def test_start_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.start("ghost" * 6, [])

    def test_start_refuses_when_version_not_installed(self, tmp_path: Path) -> None:
        store_path = tmp_path / "servers.json"
        spawn = FakeSpawn()
        workspace = _workspace(store_path, new_id=lambda: "v" * 32, spawn=spawn)
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
        двух `ragent` на одном `-d`. `FakeSpawn.calls` обязан остаться
        пустым — отказ ДО порождения, без частичных эффектов.
        Мутация: убрать проверку снимка перед `spawn` — тест обязан упасть.
        """  # noqa: RUF002
        store_path = tmp_path / "servers.json"
        spawn = FakeSpawn()
        workspace = _workspace(store_path, new_id=lambda: "w" * 32, spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        ragent = tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
        installation = _server_installation("8.3.25.1633", ragent)

        with pytest.raises(ServerError):
            workspace.start(profile.id, [installation])

        assert spawn.calls == []


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
        control = FakeControl()
        workspace = _workspace(store_path, new_id=lambda: "ee" * 16, control=control)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        workspace.stop_orphans(profile.id)  # без апасений — сирот нет, значит нет и вызовов

        assert control.calls == []

    def test_stop_orphans_unknown_profile_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json")
        with pytest.raises(UnknownItemError):
            workspace.stop_orphans("ghost" * 6)
