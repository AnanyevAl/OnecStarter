"""ServersWorkspace: координатор профилей серверов и их хранения (T-08, задача 10)."""

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from onecstarter.domain.server import ServerProfile
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.errors import ServerError
from onecstarter.services.server_store import load_profiles
from onecstarter.services.servers import ServersWorkspace


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
