"""Хранилище edt.json: калька политики `.bad` из `test_server_store.py` (спека §2)."""

import json
from pathlib import Path

import pytest

from onecstarter.domain.edt import EdtGroup, EdtProject
from onecstarter.services.edt_store import (
    SCHEMA_VERSION,
    EdtRegistry,
    load_registry,
    save_registry,
)
from onecstarter.services.errors import EdtUnavailableError

GROUP = EdtGroup(id="g1", name="2025", parent_id=None)
CHILD = EdtGroup(id="g2", name="Розница", parent_id="g1")
PROJECT = EdtProject(
    id="p1",
    name="Розница (2025)",
    workspace=r"D:\edt\2025\retail",
    project_dir=r"D:\edt\2025\retail\retail",
    edt_version="2025.2.6+4",
    jvm_dir="",
    vm_args="-Xmx8192m",
    group_id="g2",
)
REGISTRY = EdtRegistry(groups=(GROUP, CHILD), projects=(PROJECT,))


class TestRoundTrip:
    def test_survives_save_load(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        save_registry(path, REGISTRY)
        assert load_registry(path) == REGISTRY

    def test_order_is_array_order(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        second = EdtProject(id="p2", name="Б", workspace=r"D:\b")
        first = EdtProject(id="p1", name="А", workspace=r"D:\a")  # noqa: RUF001
        save_registry(path, EdtRegistry(groups=(), projects=(second, first)))
        assert [p.id for p in load_registry(path).projects] == ["p2", "p1"]

    def test_payload_shape(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        save_registry(path, REGISTRY)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema"] == SCHEMA_VERSION
        assert payload["groups"][0] == {"id": "g1", "name": "2025", "parent_id": None}
        assert payload["projects"][0]["workspace"] == r"D:\edt\2025\retail"
        assert payload["projects"][0]["group_id"] == "g2"

    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert load_registry(tmp_path / "edt.json") == EdtRegistry(groups=(), projects=())

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        path = tmp_path / "OneCStarter" / "edt.json"
        save_registry(path, REGISTRY)
        assert path.exists()


class TestTolerance:
    def test_missing_optional_fields_default(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        path.write_text(
            json.dumps(
                {
                    "schema": SCHEMA_VERSION,
                    "groups": [],
                    "projects": [{"id": "p", "name": "n", "workspace": r"D:\w"}],
                }
            ),
            encoding="utf-8",
        )
        [project] = load_registry(path).projects
        assert project == EdtProject(id="p", name="n", workspace=r"D:\w")

    def test_unknown_keys_are_dropped_on_save(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        path.write_text(
            json.dumps(
                {
                    "schema": SCHEMA_VERSION,
                    "groups": [],
                    "projects": [{"id": "p", "name": "n", "workspace": r"D:\w", "future": 1}],
                }
            ),
            encoding="utf-8",
        )
        save_registry(path, load_registry(path))
        assert "future" not in path.read_text(encoding="utf-8")


class TestBadFile:
    @pytest.mark.parametrize(
        "text",
        [
            "{",
            "[]",
            '{"schema": 99, "groups": [], "projects": []}',
            '{"schema": 1, "projects": {}}',
        ],
    )
    def test_corrupt_moves_aside_and_starts_empty(self, tmp_path: Path, text: str) -> None:
        path = tmp_path / "edt.json"
        path.write_text(text, encoding="utf-8")
        assert load_registry(path) == EdtRegistry(groups=(), projects=())
        assert not path.exists()
        assert (tmp_path / "edt.json.bad").read_text(encoding="utf-8") == text

    def test_cannot_move_aside_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "edt.json"
        path.write_text("{", encoding="utf-8")

        def refuse(self: Path, target: Path) -> Path:
            raise OSError("занят")

        monkeypatch.setattr(Path, "replace", refuse)
        with pytest.raises(EdtUnavailableError):
            load_registry(path)
        assert path.exists()
