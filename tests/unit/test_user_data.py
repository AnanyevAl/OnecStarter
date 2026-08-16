import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from onecstarter.services.errors import ServicesError
from onecstarter.services.user_data import (
    BaseUserData,
    InvalidRequestError,
    UserDataUnavailableError,
    load_user_data,
    record_launch,
    rekey,
    save_user_data,
    set_favorite,
)

WHEN = datetime(2026, 8, 4, 7, 12, 44, tzinfo=UTC)


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_user_data(tmp_path / "bases.json") == {}


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "bases.json"
    entries = {"id:abc": BaseUserData(True, WHEN, 17, "thin")}
    save_user_data(path, entries)
    assert load_user_data(path) == entries


def test_saved_file_is_schema_versioned(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    save_user_data(path, {"id:abc": BaseUserData(launch_count=1)})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert "id:abc" in payload["entries"]


def test_broken_file_is_moved_aside(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    path.write_text("{не json", encoding="utf-8")
    assert load_user_data(path) == {}
    assert (tmp_path / "bases.json.bad").read_text(encoding="utf-8") == "{не json"
    assert not path.exists()


def test_unknown_schema_is_treated_as_broken(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    path.write_text('{"schema": 99, "entries": {}}', encoding="utf-8")
    assert load_user_data(path) == {}
    assert (tmp_path / "bases.json.bad").exists()


def test_unreadable_file_raises_and_is_not_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Файл есть, но недоступен для чтения (блокировка антивирусом, права,
    # отвалившийся сетевой диск) — это не порча содержимого. Подменять его  # noqa: RUF003
    # пустыми данными нельзя: следующее сохранение затрёт историю без следа.
    path = tmp_path / "bases.json"
    path.write_text('{"schema": 1, "entries": {}}', encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise PermissionError(13, "Отказано в доступе")
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    with pytest.raises(UserDataUnavailableError):
        load_user_data(path)
    assert path.exists()


def test_broken_file_that_cannot_be_moved_aside_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Испорченный файл, который не удалось перенести в .bad, нельзя тихо
    # заменить пустыми данными: то, что из него можно было бы достать, будет
    # потеряно без следа.
    path = tmp_path / "bases.json"
    path.write_text("{не json", encoding="utf-8")
    original_replace = Path.replace

    def fake_replace(self: Path, target: str | Path) -> Path:
        if self == path:
            raise PermissionError(13, "Отказано в доступе")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fake_replace)
    with pytest.raises(UserDataUnavailableError):
        load_user_data(path)
    assert path.exists()


def test_record_launch_is_pure_and_counts(tmp_path: Path) -> None:
    entries: dict[str, BaseUserData] = {}
    once = record_launch(entries, "id:abc", "thin", WHEN)
    twice = record_launch(once, "id:abc", "thick", WHEN)
    assert entries == {}
    assert once["id:abc"].launch_count == 1
    assert twice["id:abc"].launch_count == 2
    assert twice["id:abc"].last_client == "thick"
    assert twice["id:abc"].last_launched_at == WHEN


def test_record_launch_keeps_favorite() -> None:
    entries = {"id:abc": BaseUserData(favorite=True)}
    assert record_launch(entries, "id:abc", "thin", WHEN)["id:abc"].favorite


def test_record_launch_rejects_naive_datetime() -> None:
    # Наивное время Python молча трактует как локальное — архитектура
    # требует UTC везде, кроме отображения; тихая порча истории недопустима.
    # Тип — из иерархии слоя: исключение достижимо из Workspace.launch,
    # и UI обязан отличить его от случайного ValueError в чужом коде.  # noqa: RUF003
    naive_when = datetime(2026, 8, 4, 7, 12, 44)
    with pytest.raises(InvalidRequestError, match="часов"):
        record_launch({}, "id:abc", "thin", naive_when)
    assert issubclass(InvalidRequestError, ServicesError)


def test_set_favorite_toggles() -> None:
    entries = set_favorite({}, "id:abc", True)
    assert entries["id:abc"].favorite
    before = dict(entries)
    after = set_favorite(entries, "id:abc", False)
    assert not after["id:abc"].favorite
    assert entries == before


def test_rekey_moves_entry() -> None:
    entries = {"cs:0123456789abcdef|демо": BaseUserData(launch_count=3)}
    before = dict(entries)
    moved = rekey(entries, "cs:0123456789abcdef|демо", "id:abc")
    assert moved == {"id:abc": BaseUserData(launch_count=3)}
    assert entries == before


def test_rekey_of_absent_entry_is_noop() -> None:
    entries: dict[str, BaseUserData] = {}
    result = rekey(entries, "cs:нет", "id:abc")
    assert result == {}
    assert result is not entries
