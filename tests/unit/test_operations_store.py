"""operations.json: сценарии, история, политика повреждённого файла (спека v4, §5.3)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from onecstarter.domain.operations import (
    BUILTIN_SCENARIOS,
    BaseOutcome,
    BaseRef,
    BaseResult,
    RunRecord,
    Scenario,
    Step,
    StepResult,
    StepStatus,
)
from onecstarter.services.errors import InvalidRequestError, OperationsUnavailableError
from onecstarter.services.operations_store import (
    HISTORY_LIMIT,
    OperationsData,
    add_run,
    all_scenarios,
    copy_of,
    load_operations,
    prune_logs,
    remove_scenario,
    save_operations,
    upsert_scenario,
)

SCENARIO = Scenario(
    "u1", "Ночной резерв",
    (Step("/DumpIB", (r"D:\{база}.dt",), overwrite=True, create_dirs=False), Step("/UpdateDBCfg")),
    stop_on_error=False, bases=(BaseRef("id:1", "Бухгалтерия"),),
)


def _record(index: int) -> RunRecord:
    return RunRecord(
        "u1", "Ночной резерв", datetime(2026, 11, 13, 9, 0, index % 60), f"C:\\ops\\run{index}",
        (
            BaseResult(
                "id:1", "Бухгалтерия", BaseOutcome.FAILED,
                (StepResult("/DumpIB", StepStatus.FAILED, 1, 2.5, "Файл занят"),),
                logs_dir=f"C:\\ops\\run{index}\\01_Бухгалтерия",
            ),
            BaseResult(
                "id:2", "Склад", BaseOutcome.NOT_READY, (), ("нужен пароль пользователя «a»",)
            ),
        ),
    )


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_operations(tmp_path / "operations.json") == OperationsData()


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    data = OperationsData((SCENARIO, Scenario("u2", "Спросить", (), bases=None)), (_record(1),))
    save_operations(path, data)
    assert load_operations(path) == data
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 1


def test_base_logs_dir_round_trips_and_old_files_read(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    save_operations(path, OperationsData((), (_record(1),)))
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["history"][0]["bases"][0]["logs_dir"] == r"C:\ops\run1\01_Бухгалтерия"
    assert load_operations(path).history[0].bases[0].logs_dir == r"C:\ops\run1\01_Бухгалтерия"
    for base in stored["history"][0]["bases"]:
        del base["logs_dir"]  # файл прежней версии: поля нет
    path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    assert [base.logs_dir for base in load_operations(path).history[0].bases] == ["", ""]


def test_builtin_scenarios_are_never_written(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    save_operations(path, OperationsData((SCENARIO,)))
    assert "builtin:" not in path.read_text(encoding="utf-8")
    assert all_scenarios(load_operations(path)) == (*BUILTIN_SCENARIOS, SCENARIO)


def test_save_filters_out_builtin_scenarios(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    save_operations(path, OperationsData((BUILTIN_SCENARIOS[0], SCENARIO)))
    assert "builtin:" not in path.read_text(encoding="utf-8")
    assert load_operations(path).scenarios == (SCENARIO,)


@pytest.mark.parametrize(
    "content",
    ["{не json", '{"schema": 0, "scenarios": [], "history": []}', '{"schema": 1, "scenarios": {}}',
     '{"schema": 1, "scenarios": [{"id": "x"}], "history": []}', "[]",
     '{"schema": 1, "scenarios": [{"id": "x", "name": "n", "steps": [{"command": "c", '
     '"values": [{}]}], "bases": [1]}]}'],
)
def test_corrupt_file_moves_to_bad(tmp_path: Path, content: str) -> None:
    path = tmp_path / "operations.json"
    path.write_text(content, encoding="utf-8")
    assert load_operations(path) == OperationsData()
    assert not path.exists()
    assert (tmp_path / "operations.json.bad").read_text(encoding="utf-8") == content


def test_unreadable_file_is_not_replaced_by_empty_data(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    path.mkdir()  # чтение каталога как файла — OSError
    with pytest.raises(OperationsUnavailableError):
        load_operations(path)


def test_corrupt_file_that_cannot_be_moved_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "operations.json"
    path.write_text("{не json", encoding="utf-8")

    def refuse(self: Path, target: Path) -> Path:
        raise OSError("занят")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OperationsUnavailableError):
        load_operations(path)
    assert path.read_text(encoding="utf-8") == "{не json"


def test_upsert_replaces_by_id_and_appends_new() -> None:
    data = upsert_scenario(OperationsData(), SCENARIO)
    renamed = Scenario("u1", "Дневной резерв", SCENARIO.steps)
    assert upsert_scenario(data, renamed).scenarios == (renamed,)
    other = Scenario("u2", "Другой", ())
    assert upsert_scenario(data, other).scenarios == (SCENARIO, other)


@pytest.mark.parametrize(
    "scenario",
    [Scenario("builtin:dump-dt", "Своя", ()), Scenario("u9", "X", (), builtin=True),
     Scenario("u9", "  ", ()), Scenario("", "Имя", ())],
)
def test_upsert_refuses_builtin_and_nameless(scenario: Scenario) -> None:
    with pytest.raises(InvalidRequestError):
        upsert_scenario(OperationsData(), scenario)


def test_remove_scenario() -> None:
    data = OperationsData((SCENARIO,))
    assert remove_scenario(data, "u1").scenarios == ()
    with pytest.raises(InvalidRequestError):
        remove_scenario(data, "builtin:dump-dt")


def test_copy_of_builtin_is_an_editable_scenario_with_a_free_name() -> None:
    copy = copy_of(BUILTIN_SCENARIOS[0], "u7", {"Выгрузить в .dt — копия"})
    assert (copy.id, copy.builtin) == ("u7", False)
    assert copy.name == "Выгрузить в .dt — копия 2"
    assert copy.steps == BUILTIN_SCENARIOS[0].steps
    assert copy_of(SCENARIO, "u8", set()).name == "Ночной резерв — копия"


def test_history_keeps_the_last_fifty_and_reports_dropped_dirs() -> None:
    data = OperationsData()
    dropped_total: list[str] = []
    for index in range(HISTORY_LIMIT + 2):
        data, dropped = add_run(data, _record(index))
        dropped_total += dropped
    assert len(data.history) == HISTORY_LIMIT
    assert data.history[-1].logs_dir == f"C:\\ops\\run{HISTORY_LIMIT + 1}"
    assert dropped_total == ["C:\\ops\\run0", "C:\\ops\\run1"]


def test_add_run_does_not_report_a_dir_still_used_by_a_kept_record() -> None:
    data = OperationsData()
    shared = _record(0)
    data, _ = add_run(data, shared)
    for index in range(1, HISTORY_LIMIT - 1):
        data, _ = add_run(data, _record(index))
    # запись 0 вытесняется, но каталог тот же, что у последней, оставшейся в истории  # noqa: RUF003
    data, _ = add_run(data, _record(HISTORY_LIMIT - 1))
    twin = RunRecord("u1", "Ночной резерв", shared.started, shared.logs_dir, ())
    data, dropped = add_run(data, twin)
    assert dropped == ()
    assert data.history[-1].logs_dir == shared.logs_dir


def test_add_run_reports_each_dropped_dir_once_in_order() -> None:
    # файл, правленный руками: записей больше предела, у первых двух — один каталог  # noqa: RUF003
    twin = RunRecord("u1", "Ночной резерв", _record(0).started, _record(0).logs_dir, ())
    history = (_record(0), twin, *(_record(index) for index in range(1, HISTORY_LIMIT + 2)))
    _, dropped = add_run(OperationsData((), history), _record(HISTORY_LIMIT + 5))
    expected = tuple(_record(index).logs_dir for index in range(3))
    assert dropped == expected


ROOT = Path(r"C:\ops")


def test_prune_logs_deletes_only_proper_children_of_the_root() -> None:
    removed: list[str] = []
    prune_logs(
        [r"C:\ops\run1", r"c:\OPS\run2", r"C:\other\run3", r"C:\opsx\run4", "run5", r"C:\ops",
         r"C:\ops\..\other", r"C:\ops\..", "", r"\ops\run6"],
        ROOT,
        removed.append,
    )
    assert removed == [r"C:\ops\run1", r"c:\OPS\run2"]


@pytest.mark.parametrize(
    "directory",
    [
        r"C:\ops\...", r"C:\ops\. ", r"C:\ops\run ", r"C:\ops\run.", r"C:\ops\a\b",
        r"C:\ops\.", r"C:\ops\run::$DATA", "C:\\ops\\run\x00",
    ],
)
def test_prune_logs_skips_what_win32_would_collapse_to_the_root(directory: str) -> None:
    """Win32 отбрасывает завершающие точки и пробелы: `C:\\ops\\...` для него — `C:\\ops`."""
    removed: list[str] = []
    prune_logs([directory], ROOT, removed.append)
    assert removed == []


def test_prune_logs_removes_a_direct_child() -> None:
    removed: list[str] = []
    prune_logs([r"C:\ops\2026-11-13_090507_Резерв_ ночь"], ROOT, removed.append)
    assert removed == [r"C:\ops\2026-11-13_090507_Резерв_ ночь"]


def test_prune_logs_survives_failing_removals(caplog: pytest.LogCaptureFixture) -> None:
    removed: list[str] = []

    def rmtree(path: str) -> None:
        if path.endswith("a"):
            raise OSError("занят")
        if path.endswith("n"):
            raise ValueError("embedded null")
        removed.append(path)

    prune_logs([r"C:\ops\a", r"C:\ops\n", r"C:\ops\b"], ROOT, rmtree)
    assert removed == [r"C:\ops\b"]
    assert "OSError" in caplog.text
    assert r"C:\ops" not in caplog.text


def test_prune_logs_skip_warning_names_no_path(caplog: pytest.LogCaptureFixture) -> None:
    prune_logs([r"D:\secret\dir"], ROOT, lambda path: None)
    assert "secret" not in caplog.text
    assert "вне каталога операций" in caplog.text


def test_newer_schema_raises_and_leaves_the_file_alone(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    original = b'{"schema": 2, "scenarios": [], "history": [], "new": true}'
    path.write_bytes(original)
    with pytest.raises(OperationsUnavailableError, match="новой версией"):
        load_operations(path)
    assert path.read_bytes() == original
    assert not (tmp_path / "operations.json.bad").exists()


def test_bad_history_keeps_scenarios_and_copies_the_file(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    save_operations(path, OperationsData((SCENARIO,), (_record(1),)))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["history"][0]["bases"][0]["outcome"] = "exploded"
    original = json.dumps(payload, ensure_ascii=False)
    path.write_text(original, encoding="utf-8")
    assert load_operations(path) == OperationsData((SCENARIO,), ())
    assert path.read_text(encoding="utf-8") == original
    assert (tmp_path / "operations.json.bad").read_text(encoding="utf-8") == original


def test_history_not_a_list_is_treated_as_bad_history(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    path.write_text('{"schema": 1, "scenarios": [], "history": {}}', encoding="utf-8")
    assert load_operations(path) == OperationsData()
    assert path.exists()
    assert (tmp_path / "operations.json.bad").exists()


def test_bad_history_survives_a_failing_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "operations.json"
    path.write_text('{"schema": 1, "scenarios": [], "history": [5]}', encoding="utf-8")

    def refuse(src: object, dst: object) -> None:
        raise OSError("занят")

    monkeypatch.setattr("onecstarter.services.operations_store.shutil.copyfile", refuse)
    assert load_operations(path) == OperationsData()
    assert path.exists()


@pytest.mark.parametrize("history", ['"history": null, ', ""])
def test_null_or_missing_history_is_empty_without_bad(tmp_path: Path, history: str) -> None:
    path = tmp_path / "operations.json"
    path.write_text('{' + history + '"schema": 1, "scenarios": []}', encoding="utf-8")
    assert load_operations(path) == OperationsData()
    assert not (tmp_path / "operations.json.bad").exists()


def test_bom_prefixed_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    save_operations(path, OperationsData((SCENARIO,), (_record(1),)))
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert load_operations(path) == OperationsData((SCENARIO,), (_record(1),))
    assert not (tmp_path / "operations.json.bad").exists()


def test_overflow_in_history_does_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "operations.json"
    bad_code = (
        '{"schema": 1, "scenarios": [], "history": [{"scenario_id": "a", "scenario_name": "b", '
        '"started": "2026-11-13T09:00:00", "logs_dir": "d", "bases": [{"key": "k", "name": "n", '
        '"outcome": "ok", "steps": [{"command": "c", "status": "ok", "code": 1e999}]}]}]}'
    )
    path.write_text(bad_code, encoding="utf-8")
    assert load_operations(path) == OperationsData()
