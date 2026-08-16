import pytest

from onecstarter.config.v8i import parse_v8i, serialize_v8i

DATA = (
    "[Первая]\r\n"
    'Connect=File="C:\\Bases\\A";\r\n'
    "ID=11111111-1111-1111-1111-111111111111\r\n"
    "[Вторая]\r\n"
    'Connect=File="C:\\Bases\\B";\r\n'
    "ID=22222222-2222-2222-2222-222222222222\r\n"
).encode()


def test_find_by_id() -> None:
    doc = parse_v8i(DATA)
    found = doc.find_by_id("22222222-2222-2222-2222-222222222222")
    assert found is not None
    assert found.name == "Вторая"
    assert doc.find_by_id("нет-такого") is None


def test_append_section() -> None:
    doc = parse_v8i(DATA)
    section = doc.append_section("Новая база")
    section.set("Connect", 'File="C:\\Bases\\C";')
    out = serialize_v8i(doc).decode()
    assert out.endswith("[Новая база]\r\nConnect=File=\"C:\\Bases\\C\";\r\n")


def test_append_to_empty_document() -> None:
    doc = parse_v8i(b"")
    doc.append_section("База")
    assert serialize_v8i(doc) == "[База]\r\n".encode()


def test_remove_section() -> None:
    doc = parse_v8i(DATA)
    doc.remove_section(doc.sections[0])
    out = serialize_v8i(doc).decode()
    assert "[Первая]" not in out
    assert out.startswith("[Вторая]")


def test_remove_section_removes_exact_object_among_duplicates() -> None:
    data = "[Группа]\r\nID=x\r\n[Группа]\r\nID=x\r\n".encode()
    doc = parse_v8i(data)
    first, second = doc.sections
    doc.remove_section(second)
    assert doc.sections == [first]
    assert doc.sections[0] is first


def test_remove_section_not_in_document_raises() -> None:
    doc = parse_v8i(DATA)
    foreign = parse_v8i(DATA).sections[0]  # равная по содержимому, но чужая секция
    with pytest.raises(ValueError, match="не входит в документ"):
        doc.remove_section(foreign)


def test_append_section_after_prologue_without_final_newline() -> None:
    doc = parse_v8i(b"; comment")
    doc.append_section("NewBase")
    assert serialize_v8i(doc) == b"; comment\r\n[NewBase]\r\n"
