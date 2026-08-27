"""Хранилище профилей серверов: калька политики `.bad` из `test_user_data.py`."""

import json
from pathlib import Path

import pytest

from onecstarter.domain.server import ServerProfile
from onecstarter.services.errors import ServersUnavailableError
from onecstarter.services.server_store import load_profiles, save_profiles


def _profile(**overrides: object) -> ServerProfile:
    values: dict[str, str | int | bool] = {
        "id": "a" * 32,
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


class TestRoundTrip:
    def test_profiles_survive_save_load(self, tmp_path: Path) -> None:
        path = tmp_path / "servers.json"
        save_profiles(path, [_profile()])
        assert load_profiles(path) == [_profile()]

    def test_range_is_serialized_as_colon_string(self, tmp_path: Path) -> None:
        path = tmp_path / "servers.json"
        save_profiles(path, [_profile()])
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["profiles"][0]["range"] == "1560:1591"

    def test_missing_file_is_empty_list(self, tmp_path: Path) -> None:
        assert load_profiles(tmp_path / "нет.json") == []


class TestBadPolicy:
    def test_corrupt_file_moves_to_bad(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: испорченный файл уезжает в .bad, не затирается молча."""  # noqa: RUF002
        path = tmp_path / "servers.json"
        path.write_text("{мусор", encoding="utf-8")
        assert load_profiles(path) == []
        assert (tmp_path / "servers.json.bad").exists() and not path.exists()

    def test_unreadable_file_raises_not_empty(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: недоступный файл — ошибка, не пустой список.

        Молчаливая подмена пустотой означала бы, что первое же сохранение
        затрёт профили пользователя (докстринг user_data.py — тот же довод).
        """  # noqa: RUF002
        directory = tmp_path / "servers.json"
        directory.mkdir()  # каталог на месте файла: IsADirectoryError=OSError
        with pytest.raises(ServersUnavailableError):
            load_profiles(directory)
