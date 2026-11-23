"""Предпросмотр командной строки с раскраской (мокап `.preview`; план Б, задача 8)."""  # noqa: RUF002

from typing import Any

import pytest
from PySide6.QtGui import QFont, QTextCharFormat

from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.ui import theme
from onecstarter.ui.command_line import (
    CommandLineView,
    SpanKind,
    base_length_through,
    catalog_word_known,
    command_spans,
)

KNOWN = {"/Debug", "/Out", "/L"}
BASE = '1cv8c.exe ENTERPRISE /IBName"Б"'
K, U, T, B = SpanKind.KEY, SpanKind.UNKNOWN, SpanKind.TEXT, SpanKind.BASE


def _spans(line: str, base: int = 0) -> tuple[tuple[SpanKind, str], ...]:
    spans = command_spans(line, base_length=base, is_known=lambda word: word in KNOWN)
    assert "".join(span.text for span in spans) == line  # ничего не теряется
    return tuple((span.kind, span.text) for span in spans)


@pytest.mark.parametrize(
    ("line", "base", "expected"),
    [
        ("", 0, ()),
        (
            f"{BASE} /Debug -http /Foo",
            len(BASE),
            ((B, BASE), (T, " "), (K, "/Debug"), (T, " -http "), (U, "/Foo")),
        ),
        (
            '/Out "C:\\a b\\c.log" /L ru',
            0,
            ((K, "/Out"), (T, ' "C:\\a b\\c.log" '), (K, "/L"), (T, " ru")),
        ),
        # Кавычки не рвут слово; прижатый в кавычках ключ — незнакомый (решение 4).
        ('/C"a b" x', 0, ((U, '/C"a b"'), (T, " x"))),
        ('/C "abc /Debug', 0, ((U, "/C"), (T, ' "abc /Debug'))),  # незакрытая кавычка — до конца
        ("/WSN u /WSP ***", 0, ((U, "/WSN"), (T, " u "), (U, "/WSP"), (T, " ***"))),
        ('/Out "a ""b"" c"', 0, ((K, "/Out"), (T, ' "a ""b"" c"'))),
    ],
)
def test_command_spans(line: str, base: int, expected: tuple[tuple[SpanKind, str], ...]) -> None:
    assert _spans(line, base) == expected


@pytest.mark.parametrize(
    ("word", "known"),
    [
        ("/Debug", True),  # ключ
        ("/Lru", True),  # значение, прижатое по правилам ключа (Catalog.match)
        ("/DumpIB", True),  # команда Конфигуратора
        ('/C"abc"', False),  # прижатое в кавычках — unknown везде (решение 4, предпроверка 1.2)
        ("/Foo", False),
    ],
)
def test_catalog_word_known(word: str, known: bool) -> None:
    assert catalog_word_known(load_cli_catalog())(word) is known


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('1cv8.exe DESIGNER /IBName"a b" /DumpIB x', len('1cv8.exe DESIGNER /IBName"a b"')),
        ('1cv8.exe DESIGNER /IBName"a ""b""" /Out y', len('1cv8.exe DESIGNER /IBName"a ""b"""')),
        ("1cv8.exe DESIGNER /DumpIB x", 0),
        ("", 0),
    ],
)
def test_base_length_through(line: str, expected: int) -> None:
    """Начало строки шага до `/IBName…` — `.base` мокапа (задача 16)."""
    assert base_length_through(line, "/IBName") == expected


def test_view_colours_base_keys_and_unknown(qtbot: Any) -> None:
    view = CommandLineView(theme.LIGHT)
    qtbot.addWidget(view)
    line = f"{BASE} /Debug /Foo"
    view.show_line(line, base_length=len(BASE), is_known=lambda word: word == "/Debug")
    assert view.toPlainText() == line
    assert view.objectName() == "CodePreview" and view.isReadOnly()
    assert view.format_at(0).foreground().color().name() == theme.LIGHT.text_dim
    key = view.format_at(line.index("/Debug"))
    assert key.foreground().color().name() == theme.LIGHT.accent
    assert key.fontWeight() == QFont.Weight.DemiBold.value
    unknown = view.format_at(line.index("/Foo"))
    assert unknown.foreground().color().name() == theme.LIGHT.unknown
    assert unknown.underlineStyle() == QTextCharFormat.UnderlineStyle.DotLine
    view.set_palette(theme.DARK)
    assert view.format_at(line.index("/Debug")).foreground().color().name() == theme.DARK.accent
