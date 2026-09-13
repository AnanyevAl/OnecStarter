"""Поиск редакторов: известные пути [Ф] спека §0, приоритет — спека §5."""

from pathlib import Path

from onecstarter.domain.edt import EDITOR_MISSING_NOTE
from onecstarter.platform_1c.editors import (
    EDITOR_LABELS,
    EditorKind,
    find_editor,
    known_locations,
)

ENV = {"LOCALAPPDATA": r"C:\Users\u\AppData\Local", "ProgramFiles": r"C:\Program Files"}
CODE_USER = Path(r"C:\Users\u\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd")
CODE_SYSTEM = Path(r"C:\Program Files\Microsoft VS Code\bin\code.cmd")
ANTI = Path(r"C:\Users\u\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd")


def test_labels() -> None:
    assert EDITOR_LABELS == {EditorKind.VSCODE: "VS Code", EditorKind.ANTIGRAVITY: "Antigravity"}


def test_known_locations() -> None:
    assert known_locations(EditorKind.VSCODE, ENV) == [CODE_USER, CODE_SYSTEM]
    assert known_locations(EditorKind.ANTIGRAVITY, ENV) == [ANTI]


def _which(hits: dict[str, str]):  # type: ignore[no-untyped-def]
    return lambda name: hits.get(name)


def test_path_hit_wins_over_known() -> None:
    result = find_editor(
        EditorKind.VSCODE,
        "",
        ENV,
        which=_which({"code.cmd": r"D:\portable\code.cmd"}),
        is_file=lambda p: True,
    )
    assert result.path == Path(r"D:\portable\code.cmd")
    assert result.source == "PATH"


def test_known_fallback_only_existing() -> None:
    result = find_editor(
        EditorKind.VSCODE, "", ENV, which=_which({}), is_file=lambda p: p == CODE_SYSTEM
    )
    assert result.path == CODE_SYSTEM
    assert result.source == "known"


def test_antigravity_not_in_path_found_by_known_dir() -> None:
    result = find_editor(
        EditorKind.ANTIGRAVITY, "", ENV, which=_which({}), is_file=lambda p: p == ANTI
    )
    assert result.path == ANTI


def test_setting_missing_reports_note() -> None:
    result = find_editor(
        EditorKind.VSCODE, r"D:\nope\code.cmd", ENV, which=_which({}), is_file=lambda p: False
    )
    assert result.path is None
    assert "не существует" in result.note


def test_nothing_found() -> None:
    result = find_editor(EditorKind.VSCODE, "", ENV, which=_which({}), is_file=lambda p: False)
    assert result.path is None
    assert result.note == EDITOR_MISSING_NOTE
