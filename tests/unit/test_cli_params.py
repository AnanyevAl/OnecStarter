"""Разбор строки параметров без потерь (спека v4, §4.1; [Ф] T-42 Э2, Э4)."""

import pytest

from onecstarter.domain.cli_catalog import Catalog, load_catalog
from onecstarter.domain.cli_params import (
    bind,
    format_key,
    key_count,
    parse,
    quote,
    render,
    unquote,
    with_key,
    without_key,
)


def _catalog() -> Catalog:
    def key(name: str, args: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "name": name, "group": "g", "modes": ["enterprise", "designer"],
            "summary": "к", "description": "о", "its": "7.3", "reliability": "doc",  # noqa: RUF001
            "args": args or [],
        }

    return load_catalog(
        {
            "group": [{"id": "g", "title": "Г", "order": 1}],
            "key": [
                key("/L", [{"kind": "string", "attached": True, "required": True}]),
                key("/N", [{"kind": "string", "attached": True, "quoted": True, "required": True}]),
                key("/P", [{"kind": "secret", "attached": True, "quoted": True}]),
                key("/C", [{"kind": "string", "required": True}]),
                key("/Out", [
                    {"kind": "file", "required": True},
                    {"kind": "flag", "flag": "-NoTruncate"},
                ]),
                key("/Debug", [
                    {"kind": "enum", "values": ["-tcp", "-http"]},
                    {"kind": "flag", "flag": "-attach", "requires": "-http"},
                ]),
                key("/TestClient", [{"kind": "int", "flag": "-TPort", "attached": True}]),
                key("/Proxy", [
                    {"kind": "string", "flag": "-PSrv", "required": True},
                    {"kind": "secret", "flag": "-PPwd"},
                ]),
                key("/NoProxy"),
                key("/WA", [{"kind": "enum", "values": ["+", "-"], "attached": True}]),
            ],
        }
    )


ROUND_TRIP = [
    "",
    "   ",
    "/Len",
    "  /DisableStartupMessages   /Lru  ",
    '/C "T42 Q2 ""в кавычках"""',
    '/C "Q3 \\"в кавычках\\""',
    "/C Q4 без кавычек",
    '/Out "C:\\каталог с пробелом\\out.txt" -NoTruncate /Foo bar',  # noqa: RUF001
    'мусор /Len',
    '/C "незакрытая',
    "/Debug -http -attach\t/WA-",
    '/N"tester" /P"секрет"',
]


@pytest.mark.parametrize("text", ROUND_TRIP)
def test_render_of_parse_is_byte_exact(text: str) -> None:
    assert render(parse(text, _catalog())) == text


def test_tokens_split_by_keys_and_keep_unknown() -> None:
    parsed = parse('мусор /Lru /Foo bar /C "a b"', _catalog())
    stray, language, unknown, parameter = parsed.tokens
    assert stray.stray and stray.word == "мусор"
    assert language.key is not None and language.key.name == "/L" and language.attached == "ru"
    assert unknown.key is None and unknown.word == "/Foo" and unknown.words == ("bar",)
    assert parameter.words == ('"a b"',)
    assert key_count(parsed) == 3


def test_key_names_are_case_insensitive() -> None:
    """[Ф] T-42 Э2."""
    token = parse("/len", _catalog()).tokens[0]
    assert token.key is not None and token.key.name == "/L" and token.attached == "en"
    assert token.name == "/l"


def test_unclosed_quote_is_reported() -> None:
    assert parse('/C "незакрытая', _catalog()).unclosed_quote
    assert not parse('/C "закрытая"', _catalog()).unclosed_quote


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ('"a ""b"" c"', ('a "b" c', "")),
        ('"Q3 \\"в', ("Q3 \\", "в")),
        ("plain", ("plain", "")),
        ('"open', ("open", "")),
        ('""', ("", "")),
    ],
)
def test_unquote_follows_platform(word: str, expected: tuple[str, str]) -> None:
    """[Ф] T-42 Э4: удвоенная кавычка — одна; `\\"` закрывает значение."""
    assert unquote(word) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("ru", "ru"), ("a b", '"a b"'), ('a"b', '"a""b"'), ("", '""'), ("/x", '"/x"')],
)
def test_quote_only_when_needed(value: str, expected: str) -> None:
    assert quote(value) == expected


def _bound(text: str) -> tuple[tuple[str | None, ...], tuple[str, ...]]:
    binding = bind(parse(text, _catalog()).tokens[0])
    return binding.values, binding.extra


@pytest.mark.parametrize(
    ("text", "values", "extra"),
    [
        ("/Lru", ("ru",), ()),
        ('/N"Иван Петров"', ("Иван Петров",), ()),
        ('/C "Q1 с пробелом"', ("Q1 с пробелом",), ()),  # noqa: RUF001
        ("/C Q4 без кавычек", ("Q4",), ("без", "кавычек")),
        ('/C "Q3 \\"в кавычках\\""', ("Q3 \\",), ("в", 'кавычках\\""')),
        ('/Out "C:\\a b\\o.txt" -NoTruncate', ("C:\\a b\\o.txt", ""), ()),
        ("/Debug -http -attach", ("-http", ""), ()),
        ("/Debug -attach", (None, ""), ()),
        ("/TestClient -TPort1538", ("1538",), ()),
        ('/Proxy -PSrv "srv" -PPwd "x"', ("srv", "x"), ()),
        ("/Proxy -PSrv", ("",), ()),
        ("/WA-", ("-",), ()),
        ("/NoProxy лишнее", (), ("лишнее",)),
    ],
)
def test_bind_assigns_words_to_args(
    text: str, values: tuple[str | None, ...], extra: tuple[str, ...]
) -> None:
    got_values, got_extra = _bound(text)
    assert got_values[: len(values)] == values
    assert got_extra == extra


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("/L", ("en",), "/Len"),
        ("/N", ("Иван Петров",), '/N"Иван Петров"'),
        ("/N", ("tester",), '/N"tester"'),
        ("/C", ('a "b"',), '/C "a ""b"""'),
        ("/Out", ("C:\\o.txt", ""), "/Out C:\\o.txt -NoTruncate"),
        ("/Out", ("C:\\o.txt", None), "/Out C:\\o.txt"),
        ("/Debug", ("-http", ""), "/Debug -http -attach"),
        ("/TestClient", ("1538",), "/TestClient -TPort1538"),
        ("/Proxy", ("srv", "x"), "/Proxy -PSrv srv -PPwd x"),
        ("/WA", ("+",), "/WA+"),
        ("/NoProxy", (), "/NoProxy"),
    ],
)
def test_format_key(name: str, values: tuple[str | None, ...], expected: str) -> None:
    key = _catalog().key(name)
    assert key is not None
    assert format_key(key, values) == expected


def test_format_key_keeps_spelling() -> None:
    key = _catalog().key("/L")
    assert key is not None
    assert format_key(key, ("ru",), spelled="/l") == "/lru"


def test_with_key_replaces_only_its_fragment() -> None:
    catalog = _catalog()
    key = catalog.key("/C")
    assert key is not None
    text = '  /Lru   /c "старое"  /Foo bar  '
    updated = with_key(parse(text, catalog), key, ("новое",), catalog)
    assert render(updated) == '  /Lru   /c новое  /Foo bar  '


def test_with_key_appends_missing_key() -> None:
    catalog = _catalog()
    key = catalog.key("/NoProxy")
    assert key is not None
    assert render(with_key(parse("/Lru  ", catalog), key, (), catalog)) == "/Lru /NoProxy  "
    assert render(with_key(parse("", catalog), key, (), catalog)) == "/NoProxy"


def test_without_key_removes_its_fragment_and_keeps_rest() -> None:
    catalog = _catalog()
    parsed = parse("/DisableX /Lru  /C x /Foo", catalog)
    # Уходит « /Lru» целиком; у соседа остаются его два пробела.  # noqa: RUF003
    assert render(without_key(parsed, "/l", catalog)) == "/DisableX  /C x /Foo"
    assert render(without_key(parse("/Lru  /C x", catalog), "/L", catalog)) == "/C x"
    assert render(without_key(parse("/Lru", catalog), "/L", catalog)) == ""


def test_with_key_closes_an_unclosed_quote_first() -> None:
    """Ревью задачи 4: без этого ключ проваливался внутрь открытого значения."""
    catalog = _catalog()
    key = catalog.key("/L")
    assert key is not None
    updated = with_key(parse('/C "незакрытая', catalog), key, ("ru",), catalog)
    assert render(updated) == '/C "незакрытая" /Lru'
    assert not updated.unclosed_quote and updated.find("/L") is not None


def test_without_key_closes_an_unclosed_quote_first() -> None:
    catalog = _catalog()
    updated = without_key(parse('/Lru /C "x', catalog), "/L", catalog)
    assert render(updated) == '/C "x"'


def test_value_starting_with_slash_stays_one_value() -> None:
    """Ревью задачи 4: `/C /x` разбирался бы как два ключа."""
    catalog = _catalog()
    key = catalog.key("/C")
    assert key is not None
    updated = with_key(parse("/C a", catalog), key, ("/x",), catalog)
    assert render(updated) == '/C "/x"'
    assert [token.name for token in updated.key_tokens()] == ["/C"]
