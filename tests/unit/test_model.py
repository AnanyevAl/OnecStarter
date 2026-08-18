import pytest

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.connect import ConnectKind
from onecstarter.services.errors import InvalidRequestError
from onecstarter.services.model import (
    InfobaseSource,
    binding_key,
    item_from_section,
    key_of_section,
    normalize,
    parse_order,
    validate_connect,
)


def test_normalize_strips_and_casefolds() -> None:
    assert normalize("  Демо  ") == "демо"


def test_binding_key_prefers_id() -> None:
    assert binding_key("ABC", 'File="C:\\B";', "Демо") == "id:ABC"


def test_binding_key_falls_back_to_surrogate() -> None:
    key = binding_key(None, 'File="C:\\B";', "Демо")
    assert key.startswith("cs:")
    assert key.endswith("|демо")
    assert 'file="c:\\b";' not in key


def test_surrogate_is_case_and_space_insensitive() -> None:
    first = binding_key(None, ' File="C:\\B"; ', "Демо ")
    second = binding_key(None, 'file="c:\\b";', "демо")
    assert first == second


def test_surrogate_does_not_leak_password() -> None:
    connect = 'Srvr="s";Ref="b";Pwd="hunter2";'
    key = binding_key(None, connect, "Демо")
    assert "hunter2" not in key
    assert "srvr" not in key.casefold()


def test_surrogate_differs_for_different_connect_strings() -> None:
    first = binding_key(None, 'File="C:\\A";', "Демо")
    second = binding_key(None, 'File="C:\\B";', "Демо")
    assert first != second


def test_surrogate_never_collides_with_id() -> None:
    assert binding_key(None, None, "Клиенты").startswith("cs:")
    assert binding_key("11111111-1111-1111-1111-111111111111", None, "x").startswith("id:")


def test_group_keys_differing_only_in_case_are_distinct() -> None:
    """[Ф] T-05.7: сопоставление `Folder` с именем группы регистрозависимое —
    путь `/t05-группа` при группе `[T05-Группа]` дал отдельный узел дерева,
    а не попадание внутрь. Ключ привязки группы обязан различать пути,
    различающиеся только регистром: casefold склеил бы две разные группы.
    """  # noqa: RUF002
    upper = parse_v8i("[Группа]\r\nFolder=/\r\nOrderInList=-1\r\n".encode()).sections[0]
    lower = parse_v8i("[группа]\r\nFolder=/\r\nOrderInList=-1\r\n".encode()).sections[0]
    assert key_of_section(upper) != key_of_section(lower)


def test_validate_connect_accepts_filled_placements() -> None:
    validate_connect('File="C:\\Bases\\Demo";')
    validate_connect('Srvr="srv";Ref="demo";')
    validate_connect('ws="https://host/demo";')


def test_validate_connect_accepts_unknown_kind() -> None:
    # Незнакомую строку соединения не отвергаем: чем она должна быть,
    # мы не знаем, а запереть экзотическую живую запись — хуже, чем  # noqa: RUF003
    # пропустить. Рубеж — про пустоту того, что мы понимаем.
    validate_connect("Нечто=1")


def test_validate_connect_rejects_blank_string() -> None:
    # Пустой Connect= — признак группы ([Ф] T-05.6): запись базы с такой  # noqa: RUF003
    # строкой молча сменила бы вид секции.
    for connect in ("", "   "):
        with pytest.raises(InvalidRequestError):
            validate_connect(connect)


def test_validate_connect_rejects_empty_placement_value() -> None:
    for connect in (
        'File="";',  # ровно то, что собирает build_connect(FILE, file_path="")
        'File="   ";',
        'file="";',  # имя фрагмента — без учёта регистра, как в формате
        'Srvr="srv";Ref="";',
        'Srvr="";Ref="demo";',
        'ws="";',
    ):
        with pytest.raises(InvalidRequestError):
            validate_connect(connect)


def test_validate_connect_ignores_empty_non_placement_fragments() -> None:
    # Пустое значение не-размещения (Usr="" пишет и платформа) — не повод
    # запирать правку записи, пришедшей из файла.
    validate_connect('File="C:\\Bases\\Demo";Usr="";')


def test_parse_order_accepts_fractional_and_negative() -> None:
    assert parse_order("60.6814814814813") == 60.6814814814813
    assert parse_order("-1") == -1.0
    assert parse_order("311296") == 311296.0
    assert parse_order(None) is None
    assert parse_order("мусор") is None


def test_item_from_group_section() -> None:
    doc = parse_v8i("[Клиенты]\r\nID=abc\r\nFolder=/\r\nOrderInList=-1\r\n".encode())
    item = item_from_section(doc.sections[0], InfobaseSource.USER)
    assert item.is_group
    assert item.name == "Клиенты"
    assert item.folder == "/"
    assert item.kind is ConnectKind.UNKNOWN
    assert item.order == -1.0
    assert item.parse_error is None


def test_item_from_base_section() -> None:
    raw = (
        "[Демо]\r\nConnect=Srvr=\"srv-1c\";Ref=\"acc\";\r\n"
        "ID=abc\r\nVersion=8.3.25\r\nDefaultVersion=8.3.25.1633\r\nApp=ThinClient\r\n"
    ).encode()
    item = item_from_section(parse_v8i(raw).sections[0], InfobaseSource.USER)
    assert not item.is_group
    assert item.kind is ConnectKind.SERVER
    assert item.requested_version == "8.3.25"
    assert item.section_default_version == "8.3.25.1633"
    assert item.app == "ThinClient"
    assert item.key == "id:abc"


def test_missing_folder_means_root() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\n".encode())
    assert item_from_section(doc.sections[0], InfobaseSource.USER).folder == "/"


def test_unparsed_line_becomes_parse_error() -> None:
    data = "[Демо]\r\nConnect=File=\"C:\\B\";\r\nмусор без равенства\r\n".encode()  # noqa: RUF001
    doc = parse_v8i(data)
    item = item_from_section(doc.sections[0], InfobaseSource.USER)
    assert item.parse_error is not None
    assert "мусор" not in item.parse_error  # содержимое строки в сообщение не тащим


def test_broken_order_becomes_parse_error() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\nOrderInList=abc\r\n".encode())
    item = item_from_section(doc.sections[0], InfobaseSource.USER)
    assert item.order is None
    assert item.parse_error is not None


def test_item_carries_all_section_keys_in_file_order() -> None:
    """Диалогу свойств нужны прочие ключи секции — в модели их не было.

    Порядок файловый: платформа переносит ключи при каноникализации,
    и показывать их в своём порядке значило бы врать про содержимое файла.
    """
    document = parse_v8i(
        '[База]\r\nConnect=File="D:\\b";\r\nVersion=8.3.25\r\nXTest=1\r\n'.encode()
    )
    item = item_from_section(document.sections[0], InfobaseSource.USER)
    assert item.keys == (("Connect", 'File="D:\\b";'), ("Version", "8.3.25"), ("XTest", "1"))
