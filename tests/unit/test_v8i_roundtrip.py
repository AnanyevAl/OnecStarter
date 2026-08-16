import pytest

from onecstarter.config.v8i import parse_v8i, serialize_v8i

CASES = [
    pytest.param(b"", id="empty"),
    pytest.param(
        "[А]\r\nConnect=File=\"C:\\B\";\r\n".encode(),  # noqa: RUF001
        id="basic",
    ),
    pytest.param(
        b"\xef\xbb\xbf" + "[А]\r\nConnect=File=\"C:\\B\";\r\n".encode(),  # noqa: RUF001
        id="utf8-bom",
    ),
    pytest.param(
        "[А]\nConnect=File=\"C:\\B\";\nID=x".encode("cp1251"),  # noqa: RUF001
        id="cp1251-lf-no-final-newline",
    ),
    pytest.param(
        (
            "; пролог\r\n\r\n[А]\r\nмусор\r\n"  # noqa: RUF001
            "Connect = странные пробелы\r\n"
        ).encode(),
        id="garbage-preserved",
    ),
    pytest.param(
        (
            "[Группа]\r\nID=22222222-2222-2222-2222-222222222222\r\n"
            "OrderInList=-1\r\nFolder=/\r\n"
        ).encode(),
        id="group-section",
    ),
    pytest.param(
        "[А]\r\nOrderInList=60.6814814814813\r\n".encode(),  # noqa: RUF001
        id="fractional-order",
    ),
]


@pytest.mark.parametrize("data", CASES)
def test_roundtrip_byte_exact(data: bytes) -> None:
    assert serialize_v8i(parse_v8i(data)) == data
