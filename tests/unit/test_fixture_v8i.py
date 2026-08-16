import codecs
from pathlib import Path

from onecstarter.config.v8i import parse_v8i, serialize_v8i

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"


def test_fixture_is_utf8_without_bom() -> None:
    data = FIXTURE.read_bytes()
    assert not data.startswith(codecs.BOM_UTF8)
    data.decode("utf-8")


def test_fixture_roundtrips_byte_for_byte() -> None:
    data = FIXTURE.read_bytes()
    assert serialize_v8i(parse_v8i(data)) == data


def test_fixture_carries_required_edge_cases() -> None:
    doc = parse_v8i(FIXTURE.read_bytes())
    by_name = {section.name: section for section in doc.sections}
    assert len(doc.sections) == 9
    assert sum(1 for section in doc.sections if section.is_group) == 3
    assert by_name["Розница"].folder == "/Клиенты"
    assert by_name["Демо Бухгалтерия"].get("OrderInList") == "60.6814814814813"
    assert by_name["Демо Бухгалтерия"].version == "8.3.25"
    assert by_name["Демо Розница"].get("XTest") == "1"
    assert by_name["Учёт серверный"].default_version == "8.3.25.1633"
    assert by_name["Учёт серверный"].connect == 'Srvr="srv-1c";Ref="accounting";'
    assert by_name["Портал"].connect == 'ws="http://web-server/resource/";'
    assert by_name["Без идентификатора"].id is None
    assert by_name["Потерянная"].folder == "/Нет такой группы"
    assert by_name["Пустая группа"].is_group
    assert all(section.folder != "/Пустая группа" for section in doc.sections)
