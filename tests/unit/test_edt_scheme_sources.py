"""Разбор источников схем: .csi, IDEA XML/.jar, .tmTheme (спека v3.2, §3)."""

import io
import zipfile
from pathlib import Path

import pytest

from onecstarter.domain.edt_scheme import (
    COLOR_KEYS,
    EDT_DEFAULTS,
    Scheme,
    parse_csi,
    parse_idea_jar,
    parse_idea_xml,
    parse_tmtheme,
    tm_color,
    to_csi,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edt_schemes"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- .csi ---


def test_parse_csi_reads_edt_colors_skips_unknown_and_designer() -> None:
    colors = parse_csi(_read("dark22.csi"))
    assert len(colors) == 22
    assert colors["Builtinfunction"] == (255, 198, 109)
    assert colors["Background"] == (43, 43, 43)
    assert "Unknown" not in colors
    assert "Keywords" not in colors


def test_parse_csi_tolerates_bom_and_bad_colors() -> None:
    text = (
        "﻿"
        + '{"EDTColors": [{"Name": "Strings", "Color": "zzz"}, '
        '{"Name": "Numbers", "Color": "#010203"}, 5]}'
    )
    assert parse_csi(text) == {"Numbers": (1, 2, 3)}


@pytest.mark.parametrize("text", ['{"DesignerColors": []}', "[]", "not json", '{"EDTColors": 1}'])
def test_parse_csi_rejects_without_section(text: str) -> None:
    with pytest.raises(ValueError):
        parse_csi(text)


def test_to_csi_round_trips_and_writes_only_edt_colors() -> None:
    scheme = Scheme("x", parse_csi(_read("dark22.csi")))
    text = to_csi(scheme)
    assert text.endswith("\n")
    assert '"DesignerColors"' not in text
    assert parse_csi(text) == scheme.colors
    assert text.index('"BSL_Keywords"') < text.index('"printMarginColor"')


# --- IDEA ---


def test_parse_idea_xml_maps_attributes_and_colors() -> None:
    name, colors = parse_idea_xml(_read("idea-six.xml"))
    assert name == "Шесть атрибутов"
    assert colors["BSL_Keywords"] == (204, 120, 50)
    assert colors["Strings"] == (106, 135, 89)
    assert colors["Numbers"] == (104, 151, 187)
    assert colors["Comment"] == (128, 128, 128)
    assert colors["Builtinfunction"] == (0, 0, 255)  # `ff` без ведущих нулей
    assert colors["Background"] == (43, 43, 43)
    assert colors["Foreground"] == (169, 183, 198)
    assert colors["currentLineColor"] == (50, 50, 50)
    assert colors["lineNumberColor"] == (96, 99, 102)
    assert colors["SelectionBackground"] == (33, 66, 131)
    assert colors["printMarginColor"] == (47, 47, 47)  # `#2f2f2f`
    assert "SelectionForeground" not in colors  # пустое значение
    assert "Label" not in colors  # baseAttributes без value
    assert "Others" not in colors


def test_parse_idea_xml_without_colors_section_and_without_name() -> None:
    text = (
        "<scheme version=\"1\"><attributes><option name=\"DEFAULT_KEYWORD\"><value>"
        "<option name=\"FOREGROUND\" value=\"1\"/></value></option></attributes></scheme>"
    )
    name, colors = parse_idea_xml(text)
    assert name == ""
    assert colors == {"BSL_Keywords": (0, 0, 1)}


@pytest.mark.parametrize(
    "text",
    ["<theme name=\"x\"/>", "<scheme name=\"x\"", "", "plain text"],
)
def test_parse_idea_xml_rejects_non_scheme(text: str) -> None:
    with pytest.raises(ValueError):
        parse_idea_xml(text)


def _jar(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_parse_idea_jar_takes_first_scheme_under_colors() -> None:
    data = _jar(
        {
            "META-INF/plugin.xml": "<idea-plugin/>",
            "colors/Six.xml": _read("idea-six.xml"),
            "colors/Zeta.xml": "<scheme name=\"zeta\"/>",
        }
    )
    name, colors = parse_idea_jar(data)
    assert name == "Шесть атрибутов"  # первый по имени среди colors/*.xml
    assert colors["BSL_Keywords"] == (204, 120, 50)


def test_parse_idea_jar_falls_back_to_any_scheme_xml() -> None:
    data = _jar({"META-INF/plugin.xml": "<idea-plugin/>", "themes/Six.xml": _read("idea-six.xml")})
    assert parse_idea_jar(data)[0] == "Шесть атрибутов"


@pytest.mark.parametrize(
    "data",
    [
        b"not a zip",
        _jar({"META-INF/plugin.xml": "<idea-plugin/>"}),
        _jar({"colors/bad.xml": "<x>"}),
    ],
)
def test_parse_idea_jar_rejects(data: bytes) -> None:
    with pytest.raises(ValueError):
        parse_idea_jar(data)


def test_parse_idea_jar_corrupted_entry_is_value_error() -> None:
    data = bytearray(_jar({"colors/x.xml": _read("idea-six.xml")}))
    # портим имя в локальном заголовке первой записи (смещение 30 — начало имени):
    # каталог архива цел, а `read()` поднимает BadZipFile  # noqa: RUF003
    # «File name in directory ... differ»
    data[30] = ord("z")
    with pytest.raises(ValueError, match="нет темы"):
        parse_idea_jar(bytes(data))


# --- tmTheme ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#1E1E1E", (30, 30, 30)),
        ("#2A2A2AAA", (42, 42, 42)),
        ("1e1e1e", (30, 30, 30)),
        ("#12", None),
        ("", None),
    ],
)
def test_tm_color_strips_alpha(text: str, expected: tuple[int, int, int] | None) -> None:
    assert tm_color(text) == expected


def test_parse_tmtheme_maps_general_and_scopes() -> None:
    name, colors = parse_tmtheme(_read("four-scopes.tmTheme"))
    assert name == "Четыре области"
    assert colors["Background"] == (30, 30, 30)
    assert colors["Foreground"] == (212, 212, 212)
    assert colors["currentLineColor"] == (42, 42, 42)
    assert colors["SelectionBackground"] == (38, 79, 120)
    assert colors["BSL_Keywords"] == (86, 156, 214)
    assert colors["Strings"] == (206, 145, 120)
    assert colors["Comment"] == (106, 153, 85)
    assert colors["Numbers"] == (181, 206, 168)
    assert "Operators" not in colors
    assert "lineNumberColor" not in colors


def test_parse_tmtheme_scope_precedence_and_first_match_wins() -> None:
    text = (
        '<plist version="1.0"><dict><key>settings</key><array>'
        "<dict><key>scope</key><string>keyword.operator</string><key>settings</key><dict>"
        "<key>foreground</key><string>#010101</string></dict></dict>"
        "<dict><key>scope</key><string>keyword.control.import</string><key>settings</key><dict>"
        "<key>foreground</key><string>#020202</string></dict></dict>"
        "<dict><key>scope</key><string>keyword</string><key>settings</key><dict>"
        "<key>foreground</key><string>#030303</string></dict></dict>"
        "<dict><key>scope</key><string>keyword.control</string><key>settings</key><dict>"
        "<key>foreground</key><string>#040404</string></dict></dict>"
        "</array></dict></plist>"
    )
    name, colors = parse_tmtheme(text)
    assert name == ""
    assert colors["Operators"] == (1, 1, 1)
    assert colors["Preprocessor"] == (2, 2, 2)
    assert colors["BSL_Keywords"] == (3, 3, 3)  # первое совпадение, `keyword.control` позже


@pytest.mark.parametrize(
    "text",
    ["<plist version=\"1.0\"><dict><key>name</key><string>x</string></dict></plist>",
     "<plist>", "", "<plist version=\"1.0\"><array/></plist>"],
)
def test_parse_tmtheme_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_tmtheme(text)


def test_every_parser_output_completes_to_scheme() -> None:
    for colors in (
        parse_csi(_read("dark22.csi")),
        parse_idea_xml(_read("idea-six.xml"))[1],
        parse_tmtheme(_read("four-scopes.tmTheme"))[1],
    ):
        scheme = Scheme("x", {**EDT_DEFAULTS, **colors})
        assert list(scheme.colors) == [key.name for key in COLOR_KEYS]
