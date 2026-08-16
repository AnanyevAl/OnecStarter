import pytest

from onecstarter.config.encoding import TextFormat, decode, encode

SAMPLES = [
    pytest.param("Бухгалтерия (демо)\r\n".encode(), "utf-8", b"", id="utf8-no-bom"),
    pytest.param(
        b"\xef\xbb\xbf" + "База\r\n".encode(),
        "utf-8",
        b"\xef\xbb\xbf",
        id="utf8-bom",
    ),
    pytest.param(
        b"\xff\xfe" + "База\r\n".encode("utf-16-le"),
        "utf-16-le",
        b"\xff\xfe",
        id="utf16le-bom",
    ),
    pytest.param(
        b"\xfe\xff" + "База\r\n".encode("utf-16-be"),
        "utf-16-be",
        b"\xfe\xff",
        id="utf16be-bom",
    ),
    pytest.param(
        "База\r\n".encode("cp1251"),
        "cp1251",
        b"",
        id="cp1251-fallback",
    ),
]


@pytest.mark.parametrize(("data", "encoding", "bom"), SAMPLES)
def test_decode_detects_format(data: bytes, encoding: str, bom: bytes) -> None:
    text, fmt = decode(data)
    assert fmt == TextFormat(encoding=encoding, bom=bom)
    assert "База" in text or "Бухгалтерия" in text


@pytest.mark.parametrize(("data", "encoding", "bom"), SAMPLES)
def test_encode_roundtrip(data: bytes, encoding: str, bom: bytes) -> None:
    text, fmt = decode(data)
    assert encode(text, fmt) == data


def test_empty_file_is_utf8() -> None:
    text, fmt = decode(b"")
    assert text == ""
    assert fmt == TextFormat(encoding="utf-8", bom=b"")


def test_undecodable_byte_falls_back_to_latin1() -> None:
    data = b"\x98\xff\x00"  # 0x98 не назначен в cp1251 и не валиден как utf-8
    text, fmt = decode(data)
    assert fmt == TextFormat(encoding="latin-1", bom=b"")
    assert encode(text, fmt) == data


def test_corrupt_payload_after_bom_falls_back_to_latin1() -> None:
    data = b"\xff\xfe\x41"  # BOM UTF-16 LE, но нечётный «хвост» — битый файл
    text, fmt = decode(data)
    assert fmt == TextFormat(encoding="latin-1", bom=b"")
    assert encode(text, fmt) == data
