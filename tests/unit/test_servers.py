"""ServersWorkspace: координатор профилей серверов и их хранения (T-08, задачи 10-11)."""

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from onecstarter.domain.server import ServerProfile
from onecstarter.domain.version import parse_version
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.errors import ServerError, UnknownItemError
from onecstarter.services.server_store import load_profiles
from onecstarter.services.servers import SCAN_NAMES, ScanSnapshot, ServersWorkspace, scan_servers


@dataclass
class FakeControl:
    """Минимальная реализация ProcessControl с журналом вызовов.

    В этой задаче координатор сканов/остановок не делает — задел под
    следующие задачи; журнал здесь только для проверки, что он не тронут.
    """  # noqa: RUF002

    calls: list[str] = field(default_factory=list)

    def children(self, pid: int) -> list[ProcessInfo]:
        self.calls.append(f"children:{pid}")
        return []

    def terminate(self, pid: int, expected_create_time: float) -> None:
        self.calls.append(f"terminate:{pid}")


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


def _workspace(store_path: Path, new_id: object = None) -> ServersWorkspace:
    control = FakeControl()
    kwargs: dict[str, object] = {"control": control}
    if new_id is not None:
        kwargs["new_id"] = new_id
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
