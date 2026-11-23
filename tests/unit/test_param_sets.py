"""Именованные наборы параметров запуска (спека v4, §4.6)."""

import logging
from pathlib import Path

import pytest

from onecstarter.domain.cli_catalog import Mode
from onecstarter.services.errors import InvalidRequestError, ParamSetsUnavailableError
from onecstarter.services.param_sets import (
    ParamSet,
    load_param_sets,
    remove_set,
    save_param_sets,
    sets_for,
    upsert_set,
)

DEBUG = ParamSet("Отладка", Mode.ENTERPRISE, "/Debug -http")
QUIET = ParamSet("Тихо", Mode.DESIGNER, "/DisableStartupMessages")


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_param_sets(tmp_path / "param_sets.json") == ()


def test_round_trip_keeps_order(tmp_path: Path) -> None:
    path = tmp_path / "param_sets.json"
    save_param_sets(path, (DEBUG, QUIET))
    assert load_param_sets(path) == (DEBUG, QUIET)


@pytest.mark.parametrize(
    "content",
    [
        "не json",
        '{"schema": 2, "sets": []}',
        '{"schema": 1, "sets": {}}',
        '{"schema": 1, "sets": [{"name": "x", "mode": "web", "params": ""}]}',
        '{"schema": 1, "sets": [{"mode": "enterprise", "params": ""}]}',
    ],
)
def test_damaged_file_moves_aside(tmp_path: Path, content: str) -> None:
    """Мутационная проверка обязательна: испорченный файл уезжает в .bad, а не затирается."""  # noqa: RUF002
    path = tmp_path / "param_sets.json"
    path.write_text(content, encoding="utf-8")
    assert load_param_sets(path) == ()
    assert not path.exists()
    assert (tmp_path / "param_sets.json.bad").read_text(encoding="utf-8") == content


def test_unreadable_file_is_an_error_not_empty(tmp_path: Path) -> None:
    path = tmp_path / "param_sets.json"
    path.mkdir()
    with pytest.raises(ParamSetsUnavailableError):
        load_param_sets(path)


def test_failed_quarantine_is_an_error_and_keeps_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Не сумели перенести в .bad — ошибка, файл на месте (иначе сохранение затрёт наборы)."""  # noqa: RUF002
    path = tmp_path / "param_sets.json"
    path.write_text("не json", encoding="utf-8")

    def refuse(self: Path, target: object) -> Path:
        raise PermissionError("занят")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(ParamSetsUnavailableError):
        load_param_sets(path)
    assert path.read_text(encoding="utf-8") == "не json"


def test_upsert_replaces_by_name_ignoring_case() -> None:
    updated = upsert_set((DEBUG, QUIET), ParamSet("отладка", Mode.ENTERPRISE, "/Debug -tcp"))
    assert updated == (ParamSet("отладка", Mode.ENTERPRISE, "/Debug -tcp"), QUIET)


def test_upsert_appends_new() -> None:
    assert upsert_set((DEBUG,), QUIET) == (DEBUG, QUIET)


@pytest.mark.parametrize("name", ["", "   "])
def test_upsert_rejects_empty_name(name: str) -> None:
    with pytest.raises(InvalidRequestError, match="имя набора"):
        upsert_set((), ParamSet(name, Mode.ENTERPRISE, "/Len"))


def test_upsert_rejects_line_break() -> None:
    with pytest.raises(InvalidRequestError, match="перевод строки"):
        upsert_set((), ParamSet("x", Mode.ENTERPRISE, "/Len\n/C x"))


def test_remove_and_filter_by_mode() -> None:
    assert remove_set((DEBUG, QUIET), "ОТЛАДКА") == (QUIET,)
    assert sets_for((DEBUG, QUIET), Mode.DESIGNER) == (QUIET,)


def test_moving_aside_is_logged_without_file_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Финальное ревью, F7: перенос в .bad — строка в лог; содержимое файла в лог не идёт."""
    path = tmp_path / "param_sets.json"
    path.write_text('{"schema": 99, "sets": [{"params": "/WSP zzz"}]}', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="onecstarter.param_sets"):
        assert load_param_sets(path) == ()
    records = [r for r in caplog.records if r.name == "onecstarter.param_sets"]
    assert len(records) == 1
    assert "param_sets.json.bad" in records[0].getMessage()
    assert "zzz" not in caplog.text
