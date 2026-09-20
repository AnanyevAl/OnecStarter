"""Java properties без потерь и prefs рабочей области (спека v3.2, §3; инвариант 3)."""

from pathlib import Path

import pytest

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    CURRENT_NAME,
    EDITORS_PREFS,
    EDT_DEFAULTS,
    NEW_PREFS_NEWLINE,
    PREFS_VERSION_LINE,
    THEME_IDS,
    THEME_KEY,
    Scheme,
    ThemeChoice,
    parse_prefs,
    parse_prefs_line,
    prefs_removals,
    prefs_updates,
    render_prefs,
    scheme_from_workspace_prefs,
    theme_prefs_update,
    unescape_property,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "edt_schemes" / "bsl-crlf.prefs"
TOKEN = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


def _fixture() -> str:
    return FIXTURE.read_bytes().decode("latin-1")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Builtin\\ function", "Builtin function"),
        ("a\\=b\\:c", "a=b:c"),
        ("x\\\\y", "x\\y"),
        ("\\u00EF\\u00BB\\u00BF", "ï»¿"),
        ("tab\\there", "tab\there"),
        ("trailing\\", "trailing\\"),
        ("\\uZZZZ", "uZZZZ"),
    ],
)
def test_unescape_property(text: str, expected: str) -> None:
    assert unescape_property(text) == expected


def test_parse_prefs_line_classifies() -> None:
    assert parse_prefs_line("# comment").key is None
    assert parse_prefs_line("! comment").key is None
    assert parse_prefs_line("").key is None
    assert parse_prefs_line("no separator").key is None
    line = parse_prefs_line(" key\\ one = value=with=eq")
    assert (line.key, line.key_text, line.value) == (
        "key one",
        " key\\ one ",
        "value=with=eq",
    )


def test_parse_prefs_unescapes_and_keeps_garbage_keys() -> None:
    parsed = parse_prefs(_fixture())
    assert parsed[f"{TOKEN}Builtin function.color"] == "255,198,109"
    assert parsed[f"{TOKEN}BSL_Keywords.color"] == "204,120,50"
    assert parsed["eclipse.preferences.version"] == "1"
    assert parsed[""] == ""
    assert parsed["ï»¿"] == ""


def test_render_roundtrip_identity_crlf_and_lf() -> None:
    text = _fixture()
    assert "\r\n" in text
    assert render_prefs(text, {}) == text
    lf = text.replace("\r\n", "\n")
    assert render_prefs(lf, {}) == lf


def test_render_replaces_in_place_keeps_order_garbage_and_crlf() -> None:
    text = _fixture()
    rendered = render_prefs(text, {f"{TOKEN}Strings.color": "1,2,3"})
    lines = rendered.split("\r\n")
    assert lines[0] == "="
    assert lines[3] == f"{TOKEN}Strings.color=1,2,3"
    assert lines[-2] == "\\u00EF\\u00BB\\u00BF="
    assert lines[-1] == ""
    assert "\n" not in rendered.replace("\r\n", "")
    assert len(lines) == len(text.split("\r\n"))


def test_render_inserts_new_key_in_sorted_position_by_unescaped_key() -> None:
    rendered = render_prefs(_fixture(), {f"{TOKEN}Comment.color": "9,9,9"})
    keys = [line.split("=")[0] for line in rendered.split("\r\n") if line]
    assert (
        keys.index(f"{TOKEN}Comment.color")
        == keys.index(f"{TOKEN}Builtin\\ function.color") + 1
    )
    assert (
        keys.index(f"{TOKEN}Comment.color")
        == keys.index(f"{TOKEN}Strings.color") - 1
    )


def test_render_new_file_has_version_line_sorted_keys_and_newline() -> None:
    rendered = render_prefs(
        "",
        {
            "lineNumberColor": "1,1,1",
            "AbstractTextEditor.Color.Background": "2,2,2",
        },
    )
    assert rendered == NEW_PREFS_NEWLINE.join(
        ["AbstractTextEditor.Color.Background=2,2,2", PREFS_VERSION_LINE,
         "lineNumberColor=1,1,1", ""]
    )


def test_render_preserves_comments_blank_lines_and_foreign_keys() -> None:
    existing = "# note\n\nforeign=1\nlineNumberColor=0,0,0\n"
    rendered = render_prefs(existing, {"lineNumberColor": "5,5,5"})
    assert rendered == "# note\n\nforeign=1\nlineNumberColor=5,5,5\n"


def test_render_without_trailing_newline_stays_without() -> None:
    assert render_prefs("a=1\nb=2", {"b": "3"}) == "a=1\nb=3"
    assert render_prefs("a=1\nb=2", {"c": "0"}) == "a=1\nb=2\nc=0"


def test_render_removes_keys_and_keeps_rest() -> None:
    rendered = render_prefs(
        _fixture(),
        {},
        remove=[f"{TOKEN}Builtin\\ function.color", "absent"],
    )
    assert "Builtin" not in rendered
    assert rendered.startswith("=\r\n")
    assert rendered.endswith("\\u00EF\\u00BB\\u00BF=\r\n")


def test_prefs_updates_split_by_file_with_system_default_flags() -> None:
    updates = prefs_updates(Scheme("x", EDT_DEFAULTS))
    assert set(updates) == {BSL_PREFS, EDITORS_PREFS}
    assert len(updates[BSL_PREFS]) == 11
    assert len(updates[EDITORS_PREFS]) == 16
    assert updates[BSL_PREFS][f"{TOKEN}Builtin\\ function.color"] == "127,0,85"
    assert (
        updates[EDITORS_PREFS]["AbstractTextEditor.Color.Background.SystemDefault"]
        == "false"
    )
    assert updates[EDITORS_PREFS]["hyperlinkColor.SystemDefault"] == "false"
    assert "lineNumberColor.SystemDefault" not in updates[EDITORS_PREFS]
    assert set(prefs_removals()[EDITORS_PREFS]) == set(
        updates[EDITORS_PREFS]
    )
    assert set(prefs_removals()[BSL_PREFS]) == set(updates[BSL_PREFS])


def test_scheme_from_workspace_prefs_uses_file_values_else_defaults() -> None:
    bsl = f"{TOKEN}BSL_Keywords.color=1,2,3\r\n{TOKEN}Strings.color=300,0,0\r\n"
    editors = "lineNumberColor=7,7,7\nAbstractTextEditor.Color.Background=bad\n"
    scheme = scheme_from_workspace_prefs(bsl, editors, EDT_DEFAULTS)
    assert scheme.name == CURRENT_NAME
    assert scheme.colors["BSL_Keywords"] == (1, 2, 3)
    assert scheme.colors["Strings"] == EDT_DEFAULTS["Strings"]
    assert scheme.colors["lineNumberColor"] == (7, 7, 7)
    assert scheme.colors["Background"] == EDT_DEFAULTS["Background"]
    empty = scheme_from_workspace_prefs("", "", EDT_DEFAULTS)
    assert empty.colors == {key.name: EDT_DEFAULTS[key.name] for key in COLOR_KEYS}


def test_theme_prefs_update_follows_theme_ids() -> None:
    assert theme_prefs_update(ThemeChoice.KEEP) is None
    assert THEME_IDS[ThemeChoice.DARK] == "org.eclipse.e4.ui.css.theme.e4_dark"
    assert theme_prefs_update(ThemeChoice.DARK) == {
        THEME_KEY: THEME_IDS[ThemeChoice.DARK]
    }
    assert THEME_IDS[ThemeChoice.LIGHT] == "org.eclipse.e4.ui.css.theme.e4_default"
    assert theme_prefs_update(ThemeChoice.LIGHT) == {
        THEME_KEY: "org.eclipse.e4.ui.css.theme.e4_default"
    }


def test_render_keeps_each_line_ending_as_is() -> None:
    mixed = "a=1\nb=2\r\nc=3\rd=4"
    assert render_prefs(mixed, {}) == mixed
    assert render_prefs(mixed, {"b": "9"}) == "a=1\nb=9\r\nc=3\rd=4"
    # новый ключ — доминирующим переводом строки файла (CRLF, если встречается)
    assert render_prefs(mixed, {"e": "5"}) == "a=1\nb=2\r\nc=3\rd=4\r\ne=5"
    assert render_prefs("a=1\nb=2\n", {"c": "0"}) == "a=1\nb=2\nc=0\n"


def test_render_empty_existing_is_a_new_file_not_identity() -> None:
    assert render_prefs("", {}) == PREFS_VERSION_LINE + NEW_PREFS_NEWLINE


def test_render_trailing_newline_survives_removal_and_mixed_endings() -> None:
    assert render_prefs("a=1\nb=2", {"c": "3"}, remove=["b"]) == "a=1\nc=3"
    assert render_prefs("a=1\nb=2\n", {}, remove=["b"]) == "a=1\n"
    assert render_prefs("a=1\r\nb=2\n", {}) == "a=1\r\nb=2\n"
    assert render_prefs("a=1\r\nb=2\n", {"c": "3"}) == "a=1\r\nb=2\nc=3\r\n"
