"""Домен цветовой схемы EDT: модель, ключи, цвета (спека v3.2, §2)."""

import pytest

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    EDITORS_PREFS,
    EDT_DEFAULTS,
    KEY_BY_NAME,
    RGB,
    Scheme,
    complete,
    fill_missing,
    format_rgb,
    from_hex,
    idea_color,
    invert,
    is_dark,
    parse_rgb,
    to_hex,
)

TOKEN_PREFIX = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


def test_color_keys_are_22_tokens_then_editor() -> None:
    assert len(COLOR_KEYS) == 22
    files = [key.prefs_file for key in COLOR_KEYS]
    assert files[:11] == [BSL_PREFS] * 11
    assert files[11:] == [EDITORS_PREFS] * 11
    assert len(KEY_BY_NAME) == 22
    assert all(key.title for key in COLOR_KEYS)


def test_token_keys_match_edt_identifiers() -> None:
    """11 идентификаторов — [Д] строки класса BslHighlightingConfiguration плагина
    bsl.ui (18.09.2026); пробел в `Builtin function` в файле экранирован ([Ф] спека §0)."""
    tokens = {key.prefs_key for key in COLOR_KEYS if key.prefs_file == BSL_PREFS}
    names = (
        "BSL_Keywords",
        "BSL_Pragmas",
        "Brackets",
        "Builtin\\ function",
        "Comment",
        "Label",
        "Numbers",
        "Operators",
        "Others",
        "Preprocessor",
        "Strings",
    )
    assert tokens == {f"{TOKEN_PREFIX}{name}.color" for name in names}
    assert KEY_BY_NAME["Builtinfunction"].prefs_key == f"{TOKEN_PREFIX}Builtin\\ function.color"


def test_editor_keys_and_flags() -> None:
    editor = {key.name: key for key in COLOR_KEYS if key.prefs_file == EDITORS_PREFS}
    assert editor["Background"].prefs_key == "AbstractTextEditor.Color.Background"
    assert editor["FindScope"].prefs_key == "AbstractTextEditor.Color.FindScope"
    assert editor["lineNumberColor"].prefs_key == "lineNumberColor"
    assert {name for name, key in editor.items() if key.system_default} == {
        "Background",
        "Foreground",
        "SelectionBackground",
        "SelectionForeground",
        "hyperlinkColor",
    }
    assert {key.name for key in COLOR_KEYS if key.background} == {
        "Background",
        "SelectionBackground",
        "currentLineColor",
        "occurrenceIndicationColor",
        "FindScope",
        "currentIPColor",
    }


def test_scheme_requires_all_keys_and_drops_extras() -> None:
    with pytest.raises(ValueError, match="Background"):
        Scheme("x", {"BSL_Keywords": (1, 2, 3)})
    scheme = Scheme("x", {**EDT_DEFAULTS, "Extra": (0, 0, 0)}, "C:/x.csi")
    assert "Extra" not in scheme.colors
    assert list(scheme.colors) == [key.name for key in COLOR_KEYS]
    assert scheme.source == "C:/x.csi"


def test_edt_defaults_cover_all_keys() -> None:
    assert set(EDT_DEFAULTS) == set(KEY_BY_NAME)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#FF8000", (255, 128, 0)),
        ("ff8000", (255, 128, 0)),
        ("#F80", (255, 136, 0)),
        (" #ff8000 ", (255, 128, 0)),
        ("#FF80", None),
        ("ggg", None),
        ("", None),
        ("#FF8000FF", None),
    ],
)
def test_from_hex(text: str, expected: RGB | None) -> None:
    assert from_hex(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    # [Ф] 18.09.2026, 641 тема каталога заказчика: hex без ведущих нулей (Java
    # Integer.toHexString), встречаются `#RRGGBB`, пустое и `undefined`.
    [
        ("ff", (0, 0, 255)),
        ("7f00", (0, 127, 0)),
        ("0", (0, 0, 0)),
        ("2b2b2b", (43, 43, 43)),
        ("#112328", (17, 35, 40)),
        ("A3A08", (10, 58, 8)),
        ("fff", (0, 15, 255)),
        ("", None),
        ("undefined", None),
        ("1234567", None),
    ],
)
def test_idea_color(text: str, expected: RGB | None) -> None:
    assert idea_color(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("255,140,110", (255, 140, 110)),
        (" 1, 2 ,3 ", (1, 2, 3)),
        ("256,0,0", None),
        ("-1,0,0", None),
        ("1,2", None),
        ("a,b,c", None),
        ("", None),
    ],
)
def test_parse_rgb(text: str, expected: RGB | None) -> None:
    assert parse_rgb(text) == expected


def test_to_hex_and_format_rgb() -> None:
    assert to_hex((255, 128, 0)) == "#FF8000"
    assert format_rgb((1, 2, 3)) == "1,2,3"
    assert from_hex(to_hex((7, 8, 9))) == (7, 8, 9)


def _scheme(**overrides: RGB) -> Scheme:
    return Scheme("t", {**EDT_DEFAULTS, **overrides})


@pytest.mark.parametrize(
    ("background", "dark"),
    [((30, 30, 30), True), ((255, 255, 255), False), ((128, 128, 128), False), ((0, 0, 200), True)],
)
def test_is_dark_by_background_luminance(background: RGB, dark: bool) -> None:
    assert is_dark(_scheme(Background=background)) is dark


def test_invert_flips_every_channel_and_keeps_name() -> None:
    scheme = Scheme("Тёмная", {**EDT_DEFAULTS, "Background": (10, 20, 30)}, "x.csi")
    inverted = invert(scheme)
    assert inverted.name == "Тёмная"
    assert inverted.source == "x.csi"
    assert inverted.colors["Background"] == (245, 235, 225)
    assert all(
        inverted.colors[name] == tuple(255 - c for c in rgb) for name, rgb in scheme.colors.items()
    )
    assert invert(inverted) == scheme


def test_fill_missing_light_shifts_towards_each_other() -> None:
    filled = fill_missing({}, (0, 0, 0), (255, 255, 255))
    assert set(filled) == set(KEY_BY_NAME)
    assert filled["Background"] == (255, 255, 255)
    assert filled["Foreground"] == (0, 0, 0)
    assert filled["currentLineColor"] == (235, 235, 235)  # фоновый ключ: фон −20  # noqa: RUF003
    assert filled["BSL_Keywords"] == (20, 20, 20)  # текстовый ключ: текст +20


def test_fill_missing_dark_uses_partial_background_and_fallback_foreground() -> None:
    filled = fill_missing(
        {"Background": (10, 10, 10), "Strings": (1, 2, 3)}, (240, 240, 240), (0, 0, 0)
    )
    assert filled["Background"] == (10, 10, 10)
    assert filled["Foreground"] == (240, 240, 240)
    assert filled["Strings"] == (1, 2, 3)
    assert filled["currentLineColor"] == (30, 30, 30)
    assert filled["Comment"] == (220, 220, 220)


def test_fill_missing_clamps_channels() -> None:
    filled = fill_missing(
        {"Background": (0, 0, 0), "Foreground": (10, 10, 10)}, (0, 0, 0), (0, 0, 0)
    )
    assert filled["Comment"] == (0, 0, 0)
    light = fill_missing(
        {"Background": (250, 250, 250), "Foreground": (250, 250, 250)}, (0, 0, 0), (0, 0, 0)
    )
    assert light["Comment"] == (255, 255, 255)
    assert light["currentLineColor"] == (230, 230, 230)


def test_fill_missing_and_is_dark_agree_at_mid_grey() -> None:
    """(128,128,128) — ровно порог: не тёмный для обеих функций (целочисленная яркость)."""
    grey: RGB = (128, 128, 128)
    assert is_dark(_scheme(Background=grey)) is False
    filled = fill_missing(
        {"Background": grey, "Foreground": (0, 0, 0)}, (0, 0, 0), (0, 0, 0)
    )
    assert filled["currentLineColor"] == (108, 108, 108)  # светлая ветка: фон −20  # noqa: RUF003
    assert filled["Comment"] == (20, 20, 20)  # текст +20
    dark: RGB = (127, 128, 128)
    assert is_dark(_scheme(Background=dark)) is True
    assert (
        fill_missing({"Background": dark}, (0, 0, 0), (0, 0, 0))["currentLineColor"]
        == (147, 148, 148)
    )


def test_complete_fills_from_edt_defaults() -> None:
    scheme = complete("t", {"BSL_Keywords": (1, 2, 3)}, "C:/t.xml")
    assert scheme.name == "t"
    assert scheme.source == "C:/t.xml"
    assert scheme.colors["BSL_Keywords"] == (1, 2, 3)
    assert scheme.colors["Background"] == EDT_DEFAULTS["Background"]
    assert scheme.colors["Foreground"] == EDT_DEFAULTS["Foreground"]
