from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.services.catalog import CommonListError, TreeNode, build_tree, items_from_document
from onecstarter.services.display import (
    BROKEN_SUFFIX,
    COMMON_SUFFIX,
    EMPTY_CONNECT_NOTE,
    GROUP_CONTENT_MARK,
    IMPLICIT_NOTE,
    Row,
    RowKind,
    collation_key,
    display_forest,
    filter_rows,
    group_contents,
    is_degraded_group,
    row_label,
    sort_rows,
    version_cell,
)
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.settings import DEFAULT_RECENT_LIMIT, ListOrder
from onecstarter.services.user_data import BaseUserData

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"

INSTALLED = [
    Installation(parse_version("8.3.22.1923"), Path(r"C:\1cv8\8.3.22.1923"), Arch.X86),
    Installation(parse_version("8.3.25.1633"), Path(r"C:\1cv8\8.3.25.1633"), Arch.X64),
    Installation(parse_version("8.3.27.2214"), Path(r"C:\1cv8\8.3.27.2214"), Arch.X64),
]


def _items(entries: dict[str, BaseUserData] | None = None) -> list[InfobaseItem]:
    document = parse_v8i(FIXTURE.read_bytes())
    return items_from_document(document, InfobaseSource.USER, entries or {})


def _forest(
    entries: dict[str, BaseUserData] | None = None, *, order: ListOrder = ListOrder.FILE
) -> list[Row]:
    items = _items(entries)
    return display_forest(
        items, build_tree(items), [], recent_limit=DEFAULT_RECENT_LIMIT, order=order
    )


def test_forest_without_user_data_has_no_virtual_sections() -> None:
    labels = [row.label for row in _forest()]
    assert "Избранное" not in labels
    assert "Недавние" not in labels
    assert "Общие списки" not in labels


def test_favorites_section_lists_marked_bases_first() -> None:
    entries = {"id:44444444-4444-4444-4444-444444444444": BaseUserData(favorite=True)}
    forest = _forest(entries)
    assert forest[0].kind is RowKind.SECTION
    assert forest[0].label == "Избранное"
    assert [row.label for row in forest[0].children] == ["Демо Бухгалтерия"]


def test_recent_section_sorted_by_launch_time_desc() -> None:
    stamp = datetime(2026, 8, 1, tzinfo=UTC)
    entries = {
        "id:44444444-4444-4444-4444-444444444444": BaseUserData(
            last_launched_at=stamp.replace(day=2), launch_count=1
        ),
        "id:55555555-5555-5555-5555-555555555555": BaseUserData(
            last_launched_at=stamp.replace(day=3), launch_count=2
        ),
    }
    recent = next(row for row in _forest(entries) if row.label == "Недавние")
    assert [row.label for row in recent.children] == ["Демо Розница", "Демо Бухгалтерия"]


def _stamp(index: int) -> datetime:
    return datetime(2026, 8, 1, tzinfo=UTC) + timedelta(minutes=index)


def _base_item(*, name: str, last_launched_at: datetime) -> InfobaseItem:
    return InfobaseItem(
        key=f"id:{name}", name=name, folder="/", is_group=False, connect='File="C:\\b";',
        kind=ConnectKind.FILE, requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id=name,
        last_launched_at=last_launched_at,
    )


def test_recent_limit_zero_hides_the_branch() -> None:
    """0 — ветки «Недавние» нет вовсе (подпись мокапа, спека §5)."""
    items = [
        _base_item(name=f"База {index}", last_launched_at=_stamp(index))
        for index in range(3)
    ]
    forest = display_forest(items, build_tree(items), [], recent_limit=0, order=ListOrder.FILE)
    assert all(row.label != "Недавние" for row in forest)


def test_recent_limit_cuts_the_branch() -> None:
    items = [
        _base_item(name=f"База {index}", last_launched_at=_stamp(index))
        for index in range(5)
    ]
    forest = display_forest(items, build_tree(items), [], recent_limit=2, order=ListOrder.FILE)
    recent = next(row for row in forest if row.label == "Недавние")
    assert len(recent.children) == 2


def _broken_item() -> InfobaseItem:
    """Запись с непрочитанной строкой — источник parse_error."""  # noqa: RUF002
    data = '[Битая]\r\nConnect=File="C:\\B";\r\nмусор без равенства\r\n'.encode()  # noqa: RUF001
    (item,) = items_from_document(parse_v8i(data), InfobaseSource.USER, {})
    assert item.parse_error is not None
    return item


def test_broken_record_note_carries_parse_error() -> None:
    # Спека 4a, §2: битая запись не валит приложение — показывается
    # с пометкой «не разобрано» и текстом parse_error.  # noqa: RUF003
    item = _broken_item()
    problem = item.parse_error
    assert problem is not None
    (row,) = display_forest(
        [item], build_tree([item]), [], recent_limit=DEFAULT_RECENT_LIMIT, order=ListOrder.FILE
    )
    assert row.note is not None
    assert problem in row.note


def test_broken_record_label_is_visibly_marked() -> None:
    # Тултип виден только под мышью, а раздел рассчитан на работу  # noqa: RUF003
    # с клавиатуры — пометка обязана быть в самой метке строки  # noqa: RUF003
    # (находка финального ревью 07.08.2026).
    item = _broken_item()
    (row,) = display_forest(
        [item], build_tree([item]), [], recent_limit=DEFAULT_RECENT_LIMIT, order=ListOrder.FILE
    )
    assert row_label(row) == f"Битая {BROKEN_SUFFIX}"


def test_common_list_record_label_is_marked() -> None:
    item = replace(_broken_item(), parse_error=None, in_common_list=True)
    row = Row(RowKind.BASE, item.name, item)
    assert row_label(row) == f"Битая {COMMON_SUFFIX}"


def test_label_of_healthy_row_is_untouched() -> None:
    item = replace(_broken_item(), parse_error=None)
    assert row_label(Row(RowKind.BASE, item.name, item)) == "Битая"
    assert row_label(Row(RowKind.SECTION, "Избранное", None)) == "Избранное"


def test_filter_matches_name_without_the_marker() -> None:
    # Пометка — свойство показа, а не имени: поиск идёт по row.label,  # noqa: RUF003
    # поэтому суффикс не мешает найти базу и не находится сам.
    item = _broken_item()
    forest = display_forest(
        [item], build_tree([item]), [], recent_limit=DEFAULT_RECENT_LIMIT, order=ListOrder.FILE
    )
    assert [row.label for row in filter_rows(forest, "битая")] == ["Битая"]
    assert filter_rows(forest, "не разобрано") == []


def test_implicit_group_row_carries_explanation() -> None:
    implicit = next(row for row in _forest() if row.label == "Нет такой группы")
    assert implicit.kind is RowKind.IMPLICIT_GROUP
    assert implicit.item is None
    assert implicit.note == IMPLICIT_NOTE


def test_common_branch_collects_items_and_errors() -> None:
    items = _items()
    common = list(
        items_from_document(
            parse_v8i('[Общая]\r\nConnect=File="C:\\S";\r\nID=aaaa\r\n'.encode()),
            InfobaseSource.COMMON,
            {},
        )
    )
    error = CommonListError(Path(r"C:\нет.v8i"), "нет файла")
    forest = display_forest(
        items + common,
        build_tree(items),
        [error],
        recent_limit=DEFAULT_RECENT_LIMIT,
        order=ListOrder.FILE,
    )
    branch = next(row for row in forest if row.label == "Общие списки")
    labels = [row.label for row in branch.children]
    assert "Общая" in labels
    assert any(row.kind is RowKind.NOTE and "нет файла" in row.label for row in branch.children)


def test_filter_is_case_insensitive_and_keeps_ancestors() -> None:
    # [Ф] T-05.3: платформа сравнивает имена баз без учёта регистра — поиск тоже.
    forest = _forest()
    kept = filter_rows(forest, "демо роз")
    clients = next(row for row in kept if row.label == "Клиенты")
    retail = next(row for row in clients.children if row.label == "Розница")
    assert [row.label for row in retail.children] == ["Демо Розница"]
    assert not any(row.label == "Демо Бухгалтерия" for row in clients.children)


def test_filter_on_group_name_keeps_whole_subtree() -> None:
    kept = filter_rows(_forest(), "клиенты")
    clients = next(row for row in kept if row.label == "Клиенты")
    assert {row.label for row in clients.children} == {"Демо Бухгалтерия", "Розница"}


def test_empty_filter_returns_everything() -> None:
    forest = _forest()
    assert filter_rows(forest, "  ") == forest


def _base(version: str | None, default: str | None = None) -> InfobaseItem:
    item = next(entry for entry in _items() if entry.name == "Демо Бухгалтерия")
    return replace(item, requested_version=version, section_default_version=default)


def test_version_cell_shows_choice_with_arch() -> None:
    cell = version_cell(_base("8.3.25.1633"), INSTALLED, [])
    assert cell.text == "8.3.25.1633 x64"
    assert not cell.problem
    assert cell.hint is None


def test_version_cell_flags_not_installed_and_tells_platform_fallback() -> None:
    # [Ф] T-02.8: штатный молча запустил бы максимум вообще — наша подсветка
    # обязана появиться до запуска (боль А).  # noqa: RUF003
    cell = version_cell(_base("8.3.99.1"), INSTALLED, [])
    assert cell.problem
    assert cell.text == "8.3.99.1 — не установлена"
    assert cell.hint is not None and "8.3.27.2214" in cell.hint


def test_version_cell_hints_when_platform_would_differ() -> None:
    # [Ф] T-05.5: неустановленный DefaultVersion — платформа молча взяла бы
    # максимум вообще, мы берём максимум по маске и говорим об этом.  # noqa: RUF003
    cell = version_cell(_base("8.3.25", "8.3.25.9999"), INSTALLED, [])
    assert cell.text == "8.3.25.1633 x64"
    assert not cell.problem
    assert cell.hint is not None and "8.3.27.2214" in cell.hint


def test_version_cell_silent_when_choice_matches_platform() -> None:
    cell = version_cell(_base("8.3.25", "8.3.22.1923"), INSTALLED, [])
    assert cell.text == "8.3.22.1923 x86"
    assert cell.hint is None


def test_version_cell_for_web_base_has_no_version() -> None:
    web = next(entry for entry in _items() if entry.name == "Портал")
    cell = version_cell(web, INSTALLED, [])
    assert cell.text == "веб"
    assert not cell.problem


def test_version_cell_for_group_is_empty() -> None:
    group = next(entry for entry in _items() if entry.name == "Клиенты")
    assert version_cell(group, INSTALLED, []).text == ""


def test_version_cell_without_any_installation() -> None:
    cell = version_cell(_base("8.3.25"), [], [])
    assert cell.problem
    assert cell.hint == "Установленных версий платформы не найдено"


@pytest.mark.parametrize(
    ("connect", "expected_text"),
    [
        ('File="C:\\demo";', "…"),
        ('Srvr="s";Ref="d";', "…"),
        ("мусор", "…"),
    ],
)
def test_version_cell_pending_shows_ellipsis_without_problem(
    connect: str, expected_text: str
) -> None:
    item = InfobaseItem(
        key="id:test", name="Test", folder="/", is_group=False, connect=connect,
        kind=classify_connect(connect), requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id="test",
    )
    cell = version_cell(item, [], [], discovery_pending=True)
    assert cell.text == expected_text
    assert not cell.problem
    assert cell.hint is None


def test_version_cell_pending_keeps_web_and_group_behaviour() -> None:
    web = next(entry for entry in _items() if entry.name == "Портал")
    web_cell = version_cell(web, [], [], discovery_pending=True)
    assert web_cell.text == "веб"

    group = next(entry for entry in _items() if entry.name == "Клиенты")
    group_cell = version_cell(group, [], [], discovery_pending=True)
    assert group_cell.text == ""


# -- Задача 12: содержимое группы (обязательство 3 блока Б) ----------------


def _base_leaf(name: str) -> InfobaseItem:
    return InfobaseItem(
        key=f"id:{name}", name=name, folder="/", is_group=False, connect='File="C:\\b";',
        kind=ConnectKind.FILE, requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id=name,
    )


def _group_leaf(name: str) -> InfobaseItem:
    return InfobaseItem(
        key=f"grp:{name}", name=name, folder="/", is_group=True, connect=None,
        kind=ConnectKind.UNKNOWN, requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id=None,
    )


def _group_node(*, bases: int, subgroups: int) -> TreeNode:
    """Дерево группы для теста `group_contents`.

    При наличии подгрупп все базы кладутся ВНУТРЬ первой подгруппы, а не
    прямыми детьми узла: иначе подсчёт «только прямые дети» дал бы те же
    числа, что и рекурсивный по всему поддереву, и мутация шага 5 (обрезать
    рекурсию `walk(child.children)`) осталась бы незамеченной этим тестом.
    """  # noqa: RUF002
    base_nodes = tuple(TreeNode(f"База {i}", _base_leaf(f"База {i}"), ()) for i in range(bases))
    if subgroups:
        nested = TreeNode("Подгруппа 0", _group_leaf("Подгруппа 0"), base_nodes)
        siblings = tuple(
            TreeNode(f"Подгруппа {i}", _group_leaf(f"Подгруппа {i}"), ())
            for i in range(1, subgroups)
        )
        children = (nested, *siblings)
    else:
        children = base_nodes
    return TreeNode("Группа", _group_leaf("Группа"), children)


@pytest.mark.parametrize(
    ("bases", "subgroups", "expect_names"),
    [
        (0, 0, True),
        (3, 1, True),
        (12, 0, False),
        # Круг правок 1, замечание 4: граница CONTENT_NAME_LIMIT (10) не была  # noqa: RUF003
        # проверена — параметризация брала только 4 и 12, ошибка на единицу
        # (`<` вместо `<=`) осталась бы невидимой. Ровно 10 — последнее
        # значение, ещё показанное именами; 11 — первое, уже свёрнутое в счёт.
        (10, 0, True),
        (11, 0, False),
    ],
)
def test_group_contents_lists_names_up_to_ten(
    bases: int, subgroups: int, expect_names: bool
) -> None:
    """До 10 элементов — именами, дальше — количеством.

    Обязательство 3 блока Б: платформа спрашивает «Удалить группу "имя"?»
    и каскадит молча ([Ф] T-05.9). Быть не хуже недостаточно.
    """
    node = _group_node(bases=bases, subgroups=subgroups)
    names, base_count, group_count = group_contents(node)
    assert base_count == bases
    assert group_count == subgroups
    assert bool(names) is (expect_names and bases + subgroups > 0)
    assert len(names) <= 10


def test_group_contents_marks_subgroups_not_bases() -> None:
    """Круг правок 1, замечание 5: «Розница» (подгруппа) неотличима от

    «Демо Розница» (база внутри неё) в одном плоском списке имён, хотя
    при каскадном удалении это ровно та информация, которая нужна.
    Подгруппа несёт `GROUP_CONTENT_MARK`, база — нет.
    """  # noqa: RUF002
    node = _group_node(bases=1, subgroups=1)
    names, _bases, _groups = group_contents(node)
    assert f"Подгруппа 0{GROUP_CONTENT_MARK}" in names
    assert "База 0" in names
    assert f"База 0{GROUP_CONTENT_MARK}" not in names


# -- Задача 13: секция с пустым Connect= (обязательство 4 блока Б) ---------  # noqa: RUF003


def _group_item(connect: str | None) -> InfobaseItem:
    return InfobaseItem(
        key="grp:x", name="Группа", folder="/", is_group=True, connect=connect,
        kind=ConnectKind.UNKNOWN, requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id=None,
    )


@pytest.mark.parametrize(
    ("connect", "degraded"),
    [(None, False), ("", True), ('Srvr="s";', False)],
)
def test_is_degraded_group(connect: str | None, degraded: bool) -> None:
    """Пустой Connect= отличается от отсутствующего.

    Обе секции платформа показывает группой ([Ф] T-05.6), но у первой
    первая же перезапись удалит Connect= и вычистит Version. Настоящая
    группа этого не переживает — ей нечего терять.
    """  # noqa: RUF002
    assert is_degraded_group(_group_item(connect=connect)) is degraded


def test_degraded_group_row_carries_a_warning() -> None:
    rows = display_forest(
        [_group_item(connect="")],
        build_tree([_group_item(connect="")]),
        [],
        recent_limit=DEFAULT_RECENT_LIMIT,
        order=ListOrder.FILE,
    )
    assert EMPTY_CONNECT_NOTE in (rows[0].note or "")


# -- T-11, п. 2: алфавитный режим показа ---------------------------------------


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["Портал", "база", "Архив"], ["Архив", "база", "Портал"]),
        (["Ёлка", "Дом", "Еда", "Жук"], ["Дом", "Еда", "Ёлка", "Жук"]),
        (["Яблоко", "Zed", "апрель", "Beta"], ["Beta", "Zed", "апрель", "Яблоко"]),
        (["б2", "Б1", "б10"], ["Б1", "б2", "б10"]),  # noqa: RUF001
        (["База 10", "База 2", "База 1"], ["База 1", "База 2", "База 10"]),
        (["8.3.24", "8.3.9"], ["8.3.9", "8.3.24"]),
        (["База 1", "База"], ["База", "База 1"]),
        (["a1b", "a01b"], ["a01b", "a1b"]),
    ],
)
def test_collation_key_table(names: list[str], expected: list[str]) -> None:
    """Регистр не важен, «ё» как «е», латиница перед кириллицей, цифры — как числа ([Р]).

    Числа — как в Проводнике Windows (`StrCmpLogicalW`): «База 2» перед
    «База 10», «8.3.9» перед «8.3.24» (решение заказчика 30.08.2026).
    Равные числа с разной записью («a01b»/«a1b») упорядочены устойчиво
    вторым элементом ключа, а не порядком ввода.
    """  # noqa: RUF002
    assert sorted(names, key=collation_key) == expected


def test_file_order_is_untouched_by_default() -> None:
    labels = [row.label for row in _forest()]
    assert labels == [row.label for row in _forest(order=ListOrder.FILE)]
    assert (
        labels.index("Учёт серверный") < labels.index("Портал") < labels.index("Без идентификатора")
    )


def test_alphabetical_order_puts_groups_first_then_bases_by_name() -> None:
    forest = _forest(order=ListOrder.ALPHABETICAL)
    assert [row.label for row in forest] == [
        "Клиенты", "Нет такой группы", "Пустая группа",
        "Без идентификатора", "Портал", "Учёт серверный",
    ]
    clients = forest[0]
    assert [row.label for row in clients.children] == ["Розница", "Демо Бухгалтерия"]
    assert [row.kind for row in forest[:3]] == [
        RowKind.GROUP, RowKind.IMPLICIT_GROUP, RowKind.GROUP
    ]


def test_alphabetical_order_sorts_favorites_but_not_recent() -> None:
    stamp = datetime(2026, 8, 1, tzinfo=UTC)
    entries = {
        "id:44444444-4444-4444-4444-444444444444": BaseUserData(
            favorite=True, last_launched_at=stamp.replace(day=2), launch_count=1
        ),
        "id:55555555-5555-5555-5555-555555555555": BaseUserData(
            favorite=True, last_launched_at=stamp.replace(day=3), launch_count=2
        ),
    }
    forest = _forest(entries, order=ListOrder.ALPHABETICAL)
    favorites = next(row for row in forest if row.label == "Избранное")
    recent = next(row for row in forest if row.label == "Недавние")
    assert [row.label for row in favorites.children] == ["Демо Бухгалтерия", "Демо Розница"]
    assert [row.label for row in recent.children] == ["Демо Розница", "Демо Бухгалтерия"]


def test_sort_rows_keeps_note_rows_last() -> None:
    rows = [
        Row(RowKind.NOTE, "ошибка", None),
        Row(RowKind.BASE, "Яблоко", None),
        Row(RowKind.GROUP, "Архив", None),
    ]
    assert [row.label for row in sort_rows(rows)] == ["Архив", "Яблоко", "ошибка"]


def test_sort_rows_keeps_section_rows_last_as_is() -> None:
    """Строка вида SECTION — не GROUP/BASE/NOTE — раньше отбрасывалась молча (находка

    финального ревью ветки T-11): `_sorted_siblings` собирала только group/base/note
    и не переносила остальное в результат. Теперь такая строка выживает и идёт
    последней, после NOTE, без сортировки.
    """
    rows = [
        Row(RowKind.SECTION, "Избранное", None),
        Row(RowKind.NOTE, "ошибка", None),
        Row(RowKind.BASE, "Яблоко", None),
        Row(RowKind.GROUP, "Архив", None),
    ]
    assert [row.label for row in sort_rows(rows)] == ["Архив", "Яблоко", "ошибка", "Избранное"]


def test_sort_rows_sorts_nested_children_recursively() -> None:
    """ЗАЩИТНЫЙ ТЕСТ: рекурсия `sort_rows` — дети и внуки тоже сортируются.

    Мутация: `replace(row, children=tuple(sort_rows(row.children)))` → `row`
    (без рекурсии). На фикстуре `anonymized.v8i` эта мутация невидима: у
    «Клиенты» единственная подгруппа и так стоит первой (`OrderInList=-1`),
    поэтому дерево строится вручную с нарушенным порядком на двух уровнях.
    """  # noqa: RUF002
    inner = Row(RowKind.GROUP, "Бета", None, (
        Row(RowKind.BASE, "яблоко", None),
        Row(RowKind.BASE, "Апрель", None),
    ))
    rows = [
        Row(RowKind.GROUP, "Архив", None, (
            Row(RowKind.BASE, "Портал", None),
            inner,
            Row(RowKind.BASE, "база", None),
        )),
    ]
    (archive,) = sort_rows(rows)
    assert [row.label for row in archive.children] == ["Бета", "база", "Портал"]
    beta = archive.children[0]
    assert [row.label for row in beta.children] == ["Апрель", "яблоко"]
