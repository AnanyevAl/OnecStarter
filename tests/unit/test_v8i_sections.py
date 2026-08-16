import pytest

from onecstarter.config.v8i import LineBreakRejectedError, parse_v8i, serialize_v8i

DATA = (
    '[База]\r\n'
    'Connect=Srvr="srv";Ref="demo";\r\n'
    'ID=11111111-1111-1111-1111-111111111111\r\n'
    'Version=8.3.25\r\n'
    'DefaultVersion=8.3.25.1633\r\n'
    'Folder=/Демо\r\n'
    '[Группа]\r\n'
    'ID=22222222-2222-2222-2222-222222222222\r\n'
    'Folder=/\r\n'
).encode()


def test_typed_properties() -> None:
    base, group = parse_v8i(DATA).sections
    assert base.connect == 'Srvr="srv";Ref="demo";'
    assert base.id == "11111111-1111-1111-1111-111111111111"
    assert base.version == "8.3.25"
    assert base.default_version == "8.3.25.1633"
    assert base.folder == "/Демо"
    assert not base.is_group
    assert group.is_group
    assert group.connect is None


def test_empty_connect_value_means_group() -> None:
    """[Ф] T-05.6: секцию с `Connect=` (ключ есть, значение пустое) стартер
    показывает группой, а при первой полной перезаписи довершает превращение:
    удаляет `Connect=` и `Version`, дописывает групповые ключи. Разбор,
    считающий такую секцию базой, даёт фантомную базу без строки соединения.
    """  # noqa: RUF002
    doc = parse_v8i("[Пустой]\r\nConnect=\r\nID=abc\r\nVersion=8.3.25\r\n".encode())
    assert doc.sections[0].is_group


def test_get_missing_key_returns_none() -> None:
    base = parse_v8i(DATA).sections[0]
    assert base.get("НетТакогоКлюча") is None


def test_set_existing_key_preserves_position_and_neighbors() -> None:
    doc = parse_v8i(DATA)
    doc.sections[0].set("Version", "8.5.1")
    out = serialize_v8i(doc).decode("utf-8")
    lines = out.splitlines()
    assert lines[3] == "Version=8.5.1"
    assert lines[2] == "ID=11111111-1111-1111-1111-111111111111"  # соседи не тронуты
    assert lines[4] == "DefaultVersion=8.3.25.1633"


def test_set_new_key_appends_to_section_end() -> None:
    doc = parse_v8i(DATA)
    doc.sections[0].set("App", "ThinClient")
    out = serialize_v8i(doc).decode("utf-8")
    lines = out.splitlines()
    assert lines[6] == "App=ThinClient"
    assert lines[7] == "[Группа]"


def test_set_after_line_without_final_newline() -> None:
    doc = parse_v8i('[А]\r\nConnect=File="C:\\B";'.encode())  # noqa: RUF001
    doc.sections[0].set("ID", "x")
    assert serialize_v8i(doc) == '[А]\r\nConnect=File="C:\\B";\r\nID=x'.encode()  # noqa: RUF001


def test_set_not_confused_by_exotic_separator_inside_file() -> None:
    # \x85 (NEL) — граница строки для str.splitlines, но не для формата v8i:
    # он не должен порождать ending == "" в середине файла. Раздел [B] в
    # исходном тексте — не настоящий заголовок: он приклеен к NEL внутри
    # значения K и в разобранном документе остаётся частью текста строки K,
    # а не становится отдельной секцией — поэтому реальная вторая секция  # noqa: RUF003
    # здесь [C].
    data = "[A]\r\nK=V\x85[B]\r\nID=x\r\n[C]\r\nID=y\r\n".encode()
    doc = parse_v8i(data)
    assert serialize_v8i(doc) == data  # round-trip цел
    doc.sections[0].set("New", "y")
    out = serialize_v8i(doc).decode()
    assert "New=y\r\n" in out  # не приклеен к следующему заголовку


def test_get_is_case_insensitive() -> None:
    doc = parse_v8i("[Демо]\r\nid=abc\r\nCONNECT=File=\"C:\\B\";\r\n".encode())
    section = doc.sections[0]
    assert section.get("ID") == "abc"
    assert section.id == "abc"
    assert section.connect == 'File="C:\\B";'


def test_set_keeps_original_key_spelling() -> None:
    doc = parse_v8i("[Демо]\r\nversion=8.3.24\r\n".encode())
    section = doc.sections[0]
    section.set("Version", "8.3.25")
    assert serialize_v8i(doc) == "[Демо]\r\nversion=8.3.25\r\n".encode()


def test_set_uses_requested_spelling_for_new_key() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\n".encode())
    doc.sections[0].set("Version", "8.3.25")
    assert b"Version=8.3.25" in serialize_v8i(doc)


def test_find_by_id_is_case_insensitive() -> None:
    doc = parse_v8i("[Демо]\r\nid=abc\r\nConnect=File=\"C:\\B\";\r\n".encode())
    assert doc.find_by_id("abc") is doc.sections[0]


def test_set_rejects_line_break_in_value() -> None:
    """Значение с переводом строки подделало бы секцию: после записи
    и повторного разбора в документе оказалось бы две секции вместо одной.
    """  # noqa: RUF002
    document = parse_v8i("[Демо]\r\nID=abc\r\n".encode())
    with pytest.raises(LineBreakRejectedError):
        document.sections[0].set("Connect", 'File="C:\\A";\r\n[Чужая]\r\nID=evil')


def test_set_rejects_line_break_in_key() -> None:
    document = parse_v8i("[Демо]\r\nID=abc\r\n".encode())
    with pytest.raises(LineBreakRejectedError):
        document.sections[0].set("X\r\n[Чужая]\r\nID", "1")


def test_rejected_set_leaves_section_untouched() -> None:
    """Отказ обязан наступить до мутации: половина записанного ключа хуже,
    чем отказ целиком.
    """
    data = "[Демо]\r\nID=abc\r\n".encode()
    document = parse_v8i(data)
    with pytest.raises(LineBreakRejectedError):
        document.sections[0].set("Connect", "File\r\n[Чужая]")
    assert serialize_v8i(document) == data


def test_rename_rewrites_only_the_header() -> None:
    document = parse_v8i("[Демо]\r\nID=abc\r\n".encode())
    document.sections[0].rename("Демо 2026")
    assert serialize_v8i(document) == "[Демо 2026]\r\nID=abc\r\n".encode()


def test_rename_rejects_line_break_in_name() -> None:
    """Переименование — последний вход в заголовок секции, и прямое
    присваивание `header.text` проверку формата обходило. Заголовок пишется
    одной строкой без экранирования: имя с переводом строки дописало бы
    в файл пользователя чужие секции.
    """  # noqa: RUF002
    data = "[Демо]\r\nID=abc\r\n".encode()
    document = parse_v8i(data)
    with pytest.raises(LineBreakRejectedError):
        document.sections[0].rename('Имя\r\n[Чужая]\r\nConnect=File="C:\\X";')
    assert serialize_v8i(document) == data


def test_append_section_rejects_line_break_in_name() -> None:
    data = "[Демо]\r\nID=abc\r\n".encode()
    document = parse_v8i(data)
    with pytest.raises(LineBreakRejectedError):
        document.append_section("Новая\r\n[Чужая]")
    assert serialize_v8i(document) == data
