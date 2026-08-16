import codecs
from pathlib import Path

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.connect import ConnectKind
from onecstarter.services.catalog import (
    EMPTY_COMMON_DATA,
    CommonListData,
    CommonListError,
    build_tree,
    common_items_from_data,
    common_list_paths,
    dedupe,
    items_from_document,
    read_common_lists,
)
from onecstarter.services.model import InfobaseItem, InfobaseSource, binding_key
from onecstarter.services.user_data import BaseUserData

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"


def _fixture_items(
    entries: dict[str, BaseUserData] | None = None,
) -> list[InfobaseItem]:
    document = parse_v8i(FIXTURE.read_bytes())
    return items_from_document(document, InfobaseSource.USER, entries or {})


def test_items_cover_every_section() -> None:
    items = _fixture_items()
    assert len(items) == 9
    assert sum(1 for item in items if item.is_group) == 3


def test_items_sorted_by_order_in_list() -> None:
    orders = [item.order for item in _fixture_items()]
    assert orders == sorted(orders, key=lambda value: (value is None, value))


def test_user_data_is_merged_by_key() -> None:
    entries = {"id:44444444-4444-4444-4444-444444444444": BaseUserData(True, None, 5, "thin")}
    demo = next(item for item in _fixture_items(entries) if item.name == "Демо Бухгалтерия")
    assert demo.favorite
    assert demo.launch_count == 5


def test_user_data_is_merged_by_surrogate_key() -> None:
    key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    entries = {key: BaseUserData(favorite=True)}
    item = next(item for item in _fixture_items(entries) if item.name == "Без идентификатора")
    assert item.favorite


def test_tree_nests_groups_and_bases() -> None:
    nodes = build_tree(_fixture_items())
    by_label = {node.label: node for node in nodes}
    clients = by_label["Клиенты"]
    assert clients.item is not None
    assert {child.label for child in clients.children} == {"Демо Бухгалтерия", "Розница"}
    retail = next(child for child in clients.children if child.label == "Розница")
    assert {child.label for child in retail.children} == {"Демо Розница"}


def test_empty_group_has_no_children() -> None:
    nodes = build_tree(_fixture_items())
    assert next(node for node in nodes if node.label == "Пустая группа").children == ()


def test_dangling_folder_becomes_implicit_node_like_platform() -> None:
    # [Ф] T-05.7: несовпавший путь Folder платформа рисует неявным узлом
    # без секции; база — не сирота и не падает в корень. Спека 4a, §2.
    nodes = build_tree(_fixture_items())
    implicit = next(node for node in nodes if node.label == "Нет такой группы")
    assert implicit.item is None
    assert [child.label for child in implicit.children] == ["Потерянная"]
    assert not any(node.label == "Потерянная" for node in nodes)


def test_implicit_node_keeps_case_of_folder() -> None:
    # [Ф] T-05.7: сопоставление регистрозависимое, регистр не нормализуется —
    # «клиенты» и «Клиенты» это два разных узла.
    data = (
        "[Клиенты]\r\nID=11111111-1111-1111-1111-111111111111\r\n"
        "OrderInList=-1\r\nFolder=/\r\n"
        '[База]\r\nConnect=File="C:\\A";\r\nFolder=/клиенты\r\n'
    ).encode()
    nodes = build_tree(items_from_document(parse_v8i(data), InfobaseSource.USER, {}))
    labels = [node.label for node in nodes]
    assert labels == ["Клиенты", "клиенты"]
    implicit = nodes[1]
    assert implicit.item is None
    assert [child.label for child in implicit.children] == ["База"]


def test_implicit_chain_is_nested_by_segments() -> None:
    # [Р] вложение неявной цепочки по сегментам пути — экстраполяция:  # noqa: RUF003
    # платформа снята на одном уровне ([Ф] T-05.7), сегментность путей
    # подтверждена арифметикой Folder (services/paths.py).
    data = ('[База]\r\nConnect=File="C:\\A";\r\nFolder=/a/b\r\n').encode()
    nodes = build_tree(items_from_document(parse_v8i(data), InfobaseSource.USER, {}))
    assert [node.label for node in nodes] == ["a"]
    assert nodes[0].item is None
    (b_node,) = nodes[0].children
    assert b_node.label == "b"
    assert b_node.item is None
    assert [child.label for child in b_node.children] == ["База"]


def test_implicit_node_under_real_group() -> None:
    data = (
        "[Родитель]\r\nID=11111111-1111-1111-1111-111111111111\r\n"
        "OrderInList=-1\r\nFolder=/\r\n"
        '[База]\r\nConnect=File="C:\\A";\r\nFolder=/Родитель/Нет\r\n'
    ).encode()
    nodes = build_tree(items_from_document(parse_v8i(data), InfobaseSource.USER, {}))
    (parent,) = nodes
    assert parent.label == "Родитель"
    (implicit,) = parent.children
    assert implicit.label == "Нет"
    assert implicit.item is None
    assert [child.label for child in implicit.children] == ["База"]


def test_implicit_node_takes_position_of_first_referencing_item() -> None:
    data = (
        '[Первая]\r\nConnect=File="C:\\A";\r\nOrderInList=1\r\n'
        '[Висячая]\r\nConnect=File="C:\\B";\r\nOrderInList=2\r\nFolder=/Нет\r\n'
        '[Третья]\r\nConnect=File="C:\\C";\r\nOrderInList=3\r\n'
    ).encode()
    nodes = build_tree(items_from_document(parse_v8i(data), InfobaseSource.USER, {}))
    assert [node.label for node in nodes] == ["Первая", "Нет", "Третья"]


def test_common_list_paths_are_deduplicated(tmp_path: Path) -> None:
    first = tmp_path / "all.cfg"
    second = tmp_path / "local.cfg"
    text = "CommonInfoBases=C:\\Common\\shared.v8i\r\n"
    first.write_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
    second.write_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
    assert common_list_paths([first, second, tmp_path / "нет.cfg"]) == [
        Path("C:\\Common\\shared.v8i")
    ]


def test_read_common_lists_reads_payloads_and_collects_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "1cestart.cfg"
    good = tmp_path / "good.v8i"
    good.write_bytes("[Общая]\r\nConnect=File=\"C:\\demo\";\r\n".encode("utf-8-sig"))
    missing = tmp_path / "нет-такого.v8i"
    # BOM обязателен: 1cestart.cfg — UTF-16LE ([Ф] platform-launch reference.md).
    # decode() определяет UTF-16LE только по BOM (config/encoding.py) — без него
    # байты молча читаются как UTF-8, и CommonInfoBases не находится.
    cfg.write_bytes(
        codecs.BOM_UTF16_LE
        + f"CommonInfoBases={good}\r\nCommonInfoBases={missing}\r\n".encode("utf-16-le")
    )
    data = read_common_lists([cfg])
    assert [path for path, _ in data.payloads] == [good]
    assert data.payloads[0][1] == good.read_bytes()
    assert [error.path for error in data.errors] == [missing]


def test_common_items_from_data_parses_each_payload_and_keeps_errors(tmp_path: Path) -> None:
    payload = "[Общая]\r\nConnect=File=\"C:\\demo\";\r\n".encode("utf-8-sig")
    error = CommonListError(tmp_path / "битый.v8i", "нет доступа")
    data = CommonListData(((tmp_path / "a.v8i", payload),), (error,))
    items, errors = common_items_from_data(data, {})
    assert [item.name for item in items] == ["Общая"]
    assert errors == [error]


def test_empty_common_data_gives_no_items_and_no_errors() -> None:
    items, errors = common_items_from_data(EMPTY_COMMON_DATA, {})
    assert items == []
    assert errors == []


def test_items_without_order_go_to_the_end() -> None:
    # Ветка `order is None` в сортировке: без флага запись без OrderInList
    # легла бы к нулю, то есть между -1 и 10 — в середину списка.
    data = (
        "[Первая]\r\nConnect=File=\"C:\\A\";\r\nOrderInList=-1\r\n"
        "[Без порядка]\r\nConnect=File=\"C:\\B\";\r\n"
        "[Вторая]\r\nConnect=File=\"C:\\C\";\r\nOrderInList=10\r\n"
    ).encode()
    items = items_from_document(parse_v8i(data), InfobaseSource.USER, {})
    assert [item.name for item in items] == ["Первая", "Вторая", "Без порядка"]


def _item(key: str, name: str, source: InfobaseSource) -> InfobaseItem:
    """Собрать запись напрямую: дедупликация смотрит только на ключ и источник."""
    return InfobaseItem(
        key=key,
        name=name,
        folder="/",
        is_group=False,
        connect='File="C:\\B";',
        kind=ConnectKind.FILE,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=source,
        order=None,
        section_id=None,
    )


def test_dedupe_keeps_the_user_record_and_marks_it() -> None:
    """Выигрывает пользовательская: её файл мы вправе править. Пометка нужна
    UI, чтобы объяснить происхождение записи.
    """
    user = [_item("id:aaa", "Демо", InfobaseSource.USER)]
    common = [_item("id:aaa", "Демо", InfobaseSource.COMMON)]
    merged = dedupe(user, common)
    assert len(merged) == 1
    assert merged[0].source is InfobaseSource.USER
    assert merged[0].in_common_list


def test_dedupe_matches_surrogate_keys_too() -> None:
    key = binding_key(None, 'File="C:\\B";', "Демо")
    merged = dedupe(
        [_item(key, "Демо", InfobaseSource.USER)],
        [_item(key, "Демо", InfobaseSource.COMMON)],
    )
    assert len(merged) == 1
    assert merged[0].in_common_list


def test_dedupe_keeps_records_that_are_only_in_the_common_list() -> None:
    merged = dedupe(
        [_item("id:aaa", "Демо", InfobaseSource.USER)],
        [_item("id:bbb", "Общая", InfobaseSource.COMMON)],
    )
    assert [item.key for item in merged] == ["id:aaa", "id:bbb"]
    assert not merged[0].in_common_list


def test_dedupe_leaves_untouched_records_unmarked() -> None:
    merged = dedupe([_item("id:aaa", "Демо", InfobaseSource.USER)], [])
    assert not merged[0].in_common_list


def test_dedupe_does_not_reorder_sources() -> None:
    user = [_item("id:a", "A", InfobaseSource.USER), _item("id:b", "B", InfobaseSource.USER)]
    common = [_item("id:c", "C", InfobaseSource.COMMON)]
    assert [item.key for item in dedupe(user, common)] == ["id:a", "id:b", "id:c"]


def test_dedupe_drops_duplicates_between_common_lists() -> None:
    """Общих списков несколько файлов, и уникальность ID — свойство файла,
    а не набора: одна база из двух общих списков показывается один раз.
    """  # noqa: RUF002
    common = [
        _item("id:aaa", "Общая", InfobaseSource.COMMON),
        _item("id:aaa", "Общая", InfobaseSource.COMMON),
    ]
    merged = dedupe([], common)
    assert [item.key for item in merged] == ["id:aaa"]


def test_dedupe_keeps_the_first_of_two_common_lists() -> None:
    """Выигрывает та запись, что встретилась раньше, — то есть общий список
    более раннего уровня 1cestart.cfg.
    """
    common = [
        _item("id:aaa", "Из первого", InfobaseSource.COMMON),
        _item("id:aaa", "Из второго", InfobaseSource.COMMON),
    ]
    assert [item.name for item in dedupe([], common)] == ["Из первого"]


def test_dedupe_collapses_duplicates_inside_one_common_file() -> None:
    """Совпадение ключа в одном общем файле — патология формата либо две
    неотличимые секции. Источник только для чтения, чинить там нечего,
    поэтому запись показывается один раз.
    """
    data = (
        '[Общая]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'
        '[Общая]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'
    ).encode()
    common = items_from_document(parse_v8i(data), InfobaseSource.COMMON, {})
    assert len(common) == 2
    assert [item.key for item in dedupe([], common)] == ["id:aaaa"]


def test_dedupe_keeps_duplicates_of_the_user_list() -> None:
    """Пользовательский файл редактируемый: дубль в нём пользователь обязан
    увидеть, чтобы убрать.
    """
    user = [
        _item("id:aaa", "Демо", InfobaseSource.USER),
        _item("id:aaa", "Демо", InfobaseSource.USER),
    ]
    assert len(dedupe(user, [])) == 2


def test_empty_connect_is_group_like_platform_shows_it() -> None:
    # [Ф] T-05.6: секцию с Connect= (ключ есть, значение пустое) стартер  # noqa: RUF003
    # показывает группой, а при первой полной перезаписи довершает  # noqa: RUF003
    # превращение: удаляет Connect= и Version, дописывает групповые ключи.
    # Прежнее [Р] «пустое значение — база с неизвестным видом строки  # noqa: RUF003
    # соединения» опровергнуто этим экспериментом.
    data = (
        "[Пустой коннект]\r\n"
        "ID=99999999-9999-9999-9999-999999999999\r\n"
        "Connect=\r\n"
        "Folder=/\r\n"
    ).encode()
    document = parse_v8i(data)
    items = items_from_document(document, InfobaseSource.USER, {})
    assert len(items) == 1
    item = items[0]
    assert item.is_group

    nodes = build_tree(items)
    assert len(nodes) == 1
    assert nodes[0].label == "Пустой коннект"
    assert nodes[0].item is not None
    assert nodes[0].item.is_group
    assert nodes[0].children == ()
