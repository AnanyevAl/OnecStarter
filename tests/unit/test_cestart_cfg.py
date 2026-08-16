import codecs

from onecstarter.config.cestart_cfg import common_infobase_sources, parse_cestart_cfg

CFG_TEXT = (
    "CommonInfoBases=\\\\server\\share\\bases.v8i\r\n"
    "CommonInfoBases=http://portal.example/bases.v8i\r\n"
    "DefaultVersion=8.3.25\r\n"
    "строка без разделителя\r\n"
)
CFG = codecs.BOM_UTF16_LE + CFG_TEXT.encode("utf-16-le")


def test_parse_keeps_order_and_duplicates() -> None:
    entries = parse_cestart_cfg(CFG)
    assert entries == [
        ("CommonInfoBases", "\\\\server\\share\\bases.v8i"),
        ("CommonInfoBases", "http://portal.example/bases.v8i"),
        ("DefaultVersion", "8.3.25"),
    ]


def test_common_infobase_sources() -> None:
    entries = parse_cestart_cfg(CFG)
    assert common_infobase_sources(entries) == [
        "\\\\server\\share\\bases.v8i",
        "http://portal.example/bases.v8i",
    ]


def test_empty_cfg() -> None:
    assert parse_cestart_cfg(b"") == []
    assert common_infobase_sources([]) == []


def test_common_infobase_sources_case_insensitive() -> None:
    entries = [("COMMONINFOBASES", "a.v8i"), ("commoninfobases", "b.v8i"), ("Other", "x")]
    assert common_infobase_sources(entries) == ["a.v8i", "b.v8i"]
