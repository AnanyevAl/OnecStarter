from onecstarter.config.v8i import KeyValueLine, RawLine, parse_v8i

BASIC = (
    '[Бухгалтерия (демо)]\r\n'
    'Connect=File="C:\\Bases\\Demo";\r\n'
    'ID=11111111-1111-1111-1111-111111111111\r\n'
    'OrderInList=20.2271604938271\r\n'
    'Folder=/Демо\r\n'
    'Version=8.3.25\r\n'
    '[Клиенты]\r\n'
    'ID=22222222-2222-2222-2222-222222222222\r\n'
    'OrderInList=-1\r\n'
    'Folder=/\r\n'
).encode()


def test_parse_sections_and_keys() -> None:
    doc = parse_v8i(BASIC)
    assert doc.prologue == []
    assert [s.name for s in doc.sections] == ["Бухгалтерия (демо)", "Клиенты"]
    first = doc.sections[0]
    kv = [line for line in first.lines if isinstance(line, KeyValueLine)]
    assert [line.key for line in kv] == ["Connect", "ID", "OrderInList", "Folder", "Version"]


def test_connect_split_on_first_equals_only() -> None:
    doc = parse_v8i(BASIC)
    connect = doc.sections[0].lines[0]
    assert isinstance(connect, KeyValueLine)
    assert connect.key == "Connect"
    assert connect.value == 'File="C:\\Bases\\Demo";'


def test_malformed_line_kept_as_raw() -> None:
    data = "[База]\r\nConnect=File=\"C:\\B\";\r\nмусор без равно\r\n".encode()  # noqa: RUF001
    doc = parse_v8i(data)
    raw = doc.sections[0].lines[1]
    assert isinstance(raw, RawLine)
    assert raw.text == "мусор без равно"


def test_prologue_before_first_section() -> None:
    data = "; комментарий\r\n[База]\r\nConnect=File=\"C:\\B\";\r\n".encode()
    doc = parse_v8i(data)
    assert [line.text for line in doc.prologue] == ["; комментарий"]


def test_line_endings_preserved_per_line() -> None:
    data = '[А]\nConnect=File="C:\\B";\r\nID=x'.encode()  # noqa: RUF001
    doc = parse_v8i(data)
    section = doc.sections[0]
    assert section.header.ending == "\n"
    assert section.lines[0].ending == "\r\n"
    assert section.lines[1].ending == ""  # последняя строка без перевода


def test_default_ending_is_dominant() -> None:
    doc = parse_v8i(BASIC)
    assert doc.default_ending == "\r\n"
