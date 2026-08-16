import pytest

from onecstarter.config.v8i import parse_v8i, serialize_v8i
from onecstarter.services.edit import (
    InvalidRequestError,
    PatchKind,
    ReorderPatch,
    SectionPatch,
    TargetGoneError,
    apply_patch,
    find_target,
)
from onecstarter.services.errors import ServicesError
from onecstarter.services.groups import GroupPatch, GroupPatchKind
from onecstarter.services.model import binding_key

TWO_SECTIONS = (
    "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\nVersion=8.3.25\r\n"
    "[Ручная]\r\nConnect=File=\"C:\\Bases\\Manual\";\r\n"
).encode()

GROUP_AND_CHILD = (
    "[Клиенты]\r\nID=grp\r\nFolder=/\r\n"
    "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\nFolder=/Клиенты\r\n"
).encode()

THREE_IN_ROOT = (
    "[Первая]\r\nConnect=File=\"C:\\Bases\\A\";\r\nID=a1\r\nOrderInList=10\r\n"
    "[Вторая]\r\nConnect=File=\"C:\\Bases\\B\";\r\nID=a2\r\nOrderInList=20\r\n"
    "[Третья]\r\nConnect=File=\"C:\\Bases\\C\";\r\nID=a3\r\nOrderInList=30\r\n"
).encode()

NEW_ID = "99999999-9999-9999-9999-999999999999"


def test_find_target_by_id() -> None:
    document = parse_v8i(TWO_SECTIONS)
    assert find_target(document, "id:abc") is document.sections[0]


def test_find_target_by_surrogate() -> None:
    document = parse_v8i(TWO_SECTIONS)
    key = binding_key(None, 'File="C:\\Bases\\Manual";', "Ручная")
    assert find_target(document, key) is document.sections[1]


def test_add_writes_minimal_key_set() -> None:
    document = parse_v8i("[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n".encode())
    apply_patch(
        document,
        SectionPatch(
            PatchKind.ADD,
            name="Новая",
            changes={"Connect": 'File="C:\\Bases\\New";', "Folder": "/Клиенты"},
        ),
        NEW_ID,
    )
    assert serialize_v8i(document) == (
        "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
        "[Новая]\r\nConnect=File=\"C:\\Bases\\New\";\r\nFolder=/Клиенты\r\n"
        f"ID={NEW_ID}\r\nOrderInList=-1\r\n"
    ).encode()


def test_update_changes_only_named_keys() -> None:
    document = parse_v8i(TWO_SECTIONS)
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={"Version": "8.3.27.2214"}),
        NEW_ID,
    )
    assert b"Version=8.3.27.2214" in serialize_v8i(document)
    assert b'Connect=File="C:\\Bases\\Demo";' in serialize_v8i(document)


def test_update_with_none_removes_key() -> None:
    document = parse_v8i(TWO_SECTIONS)
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={"Version": None}),
        NEW_ID,
    )
    assert b"Version" not in serialize_v8i(document)


def test_update_of_section_without_id_adds_one() -> None:
    document = parse_v8i(TWO_SECTIONS)
    key = binding_key(None, 'File="C:\\Bases\\Manual";', "Ручная")
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key=key, changes={"Version": "8.3.25"}),
        NEW_ID,
    )
    assert document.sections[1].id == NEW_ID


def test_update_renames_section() -> None:
    document = parse_v8i(TWO_SECTIONS)
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", new_name="Демо 2026"),
        NEW_ID,
    )
    assert document.sections[0].name == "Демо 2026"
    assert b"[\xd0\x94\xd0\xb5\xd0\xbc\xd0\xbe 2026]" in serialize_v8i(document)


def test_update_of_missing_target_raises() -> None:
    document = parse_v8i(TWO_SECTIONS)
    with pytest.raises(TargetGoneError):
        apply_patch(
            document,
            SectionPatch(PatchKind.UPDATE, target_key="id:нет", changes={"Version": "8.3.25"}),
            NEW_ID,
        )


def test_remove_deletes_section() -> None:
    document = parse_v8i(TWO_SECTIONS)
    apply_patch(document, SectionPatch(PatchKind.REMOVE, target_key="id:abc"), NEW_ID)
    assert [section.name for section in document.sections] == ["Ручная"]


def test_remove_of_missing_target_is_success() -> None:
    document = parse_v8i(TWO_SECTIONS)
    apply_patch(document, SectionPatch(PatchKind.REMOVE, target_key="id:нет"), NEW_ID)
    assert len(document.sections) == 2


def test_move_to_folder_is_an_update() -> None:
    document = parse_v8i(
        TWO_SECTIONS + "[Архив]\r\nID=arc\r\nOrderInList=-1\r\nFolder=/\r\n".encode()
    )
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "/Архив"}),
        NEW_ID,
    )
    assert document.sections[0].folder == "/Архив"


def test_group_update_is_rejected_entirely() -> None:
    """Запрет только переименования дыру не закрывал: смена Folder у секции-
    группы проходила без проверок и разрушала дерево тем же способом.
    У групп своя операция, она переписывает Folder потомков.
    """  # noqa: RUF002
    document = parse_v8i(GROUP_AND_CHILD)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(PatchKind.UPDATE, target_key="id:grp", new_name="Партнёры"),
            NEW_ID,
        )
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(PatchKind.UPDATE, target_key="id:grp", changes={"Folder": "/"}),
            NEW_ID,
        )
    assert document.sections[0].name == "Клиенты"
    assert document.sections[0].folder == "/"
    assert document.sections[1].folder == "/Клиенты"
    assert serialize_v8i(document) == GROUP_AND_CHILD


def test_update_cannot_turn_a_base_into_a_group() -> None:
    """Признак группы — отсутствие Connect ([Ф] скил v8i-format). Сняв ключ,
    обычная правка делала из базы группу: наши данные группам не подмешиваются,
    и избранное с историей молча отвязывались. Имя ключа сравнивается без учёта
    регистра — так же, как его находит сам формат.
    """  # noqa: RUF002
    for spelling in ("Connect", "connect"):
        document = parse_v8i(TWO_SECTIONS)
        with pytest.raises(InvalidRequestError):
            apply_patch(
                document,
                SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={spelling: None}),
                NEW_ID,
            )
        assert serialize_v8i(document) == TWO_SECTIONS


def test_group_remove_is_rejected() -> None:
    """Удаление секции-группы оставляло потомков сиротами."""
    document = parse_v8i(GROUP_AND_CHILD)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document, SectionPatch(PatchKind.REMOVE, target_key="id:grp"), NEW_ID
        )
    assert len(document.sections) == 2
    assert serialize_v8i(document) == GROUP_AND_CHILD


def test_move_of_base_requires_existing_group() -> None:
    """Записать в Folder базы любой путь означало сделать её сиротой."""
    document = parse_v8i(GROUP_AND_CHILD)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(
                PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "/Нет такой"}
            ),
            NEW_ID,
        )
    assert document.sections[1].folder == "/Клиенты"
    assert serialize_v8i(document) == GROUP_AND_CHILD


def test_move_of_base_to_root_is_allowed() -> None:
    document = parse_v8i(GROUP_AND_CHILD)
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "/"}),
        NEW_ID,
    )
    assert document.sections[1].folder == "/"


def test_folder_of_updated_base_is_written_in_platform_form() -> None:
    """[Ф] мастер стартера пишет Folder с ведущим слэшем. Путь принимается
    в любой форме, но в файл идёт та, которую мы понимаем без нормализации:
    иначе значение проходило проверку существования группы как «Клиенты»,
    а записывалось как «  Клиенты  ».
    """  # noqa: RUF002
    document = parse_v8i(GROUP_AND_CHILD)
    apply_patch(
        document,
        SectionPatch(
            PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "  Клиенты  "}
        ),
        NEW_ID,
    )
    assert document.sections[1].folder == "/Клиенты"


def test_folder_of_added_base_is_written_in_platform_form() -> None:
    """Внутренняя форма пути (`catalog.group_path`) — без ведущего слэша,
    и именно её естественно передать при перетаскивании записи в дереве.
    """
    document = parse_v8i(GROUP_AND_CHILD)
    apply_patch(
        document,
        SectionPatch(
            PatchKind.ADD,
            name="Новая",
            changes={"Connect": 'File="C:\\B";', "Folder": "Клиенты"},
        ),
        NEW_ID,
    )
    assert document.sections[-1].folder == "/Клиенты"


def test_group_and_base_agree_on_the_form_of_folder() -> None:
    """Один и тот же родитель, записанный операцией над группой и правкой
    записи базы, обязан дать один и тот же Folder: две формы одного пути
    в одном файле — состояние, в котором мы сами себя не узнаём.
    """
    document = parse_v8i(b"")
    apply_patch(document, GroupPatch(GroupPatchKind.CREATE, name="Клиенты"), "id-1")
    apply_patch(
        document,
        GroupPatch(GroupPatchKind.CREATE, name="Розница", new_folder="Клиенты"),
        "id-2",
    )
    apply_patch(
        document,
        SectionPatch(
            PatchKind.ADD,
            name="Новая",
            changes={"Connect": 'File="C:\\B";', "Folder": "Клиенты"},
        ),
        "id-3",
    )
    subgroup, base = document.sections[1], document.sections[2]
    assert subgroup.folder == base.folder == "/Клиенты"


def test_add_of_base_requires_existing_group() -> None:
    document = parse_v8i(GROUP_AND_CHILD)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(
                PatchKind.ADD,
                name="Новая",
                changes={"Connect": 'File="C:\\B";', "Folder": "/Нет такой"},
            ),
            NEW_ID,
        )
    assert len(document.sections) == 2


def test_missing_group_is_reported_the_same_way_from_both_operations() -> None:
    """Предикат «такой группы нет» один на весь слой. Пока копий было две,
    они могли разойтись и текстом, и условием — при одинаковой по сути
    ошибке пользователь получал бы разные сообщения.
    """
    document = parse_v8i(GROUP_AND_CHILD)
    with pytest.raises(InvalidRequestError) as from_base:
        apply_patch(
            document,
            SectionPatch(
                PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "/Нет такой"}
            ),
            NEW_ID,
        )
    with pytest.raises(InvalidRequestError) as from_group:
        apply_patch(
            document,
            GroupPatch(GroupPatchKind.CREATE, name="Новая", new_folder="/Нет такой"),
            NEW_ID,
        )
    assert str(from_base.value) == str(from_group.value)


def test_layer_errors_share_one_base() -> None:
    """UI ловит один тип, а не семь разных."""  # noqa: RUF002
    assert issubclass(InvalidRequestError, ServicesError)
    assert issubclass(TargetGoneError, ServicesError)


def test_patch_without_target_key_raises_layer_error() -> None:
    document = parse_v8i(TWO_SECTIONS)
    with pytest.raises(InvalidRequestError):
        apply_patch(document, SectionPatch(PatchKind.UPDATE, changes={"Version": "8.3"}), NEW_ID)


def test_add_reports_key_of_new_section() -> None:
    document = parse_v8i(b"")
    result = apply_patch(
        document,
        SectionPatch(PatchKind.ADD, name="Новая", changes={"Connect": 'File="C:\\B";'}),
        NEW_ID,
    )
    assert result.applied
    assert result.key == f"id:{NEW_ID}"


def test_update_reports_key_recomputed_after_apply() -> None:
    """Запись без `ID` получает его при правке — ключ обязан быть новым,
    иначе наши данные перевешиваются не туда.
    """  # noqa: RUF002
    document = parse_v8i(TWO_SECTIONS)
    key = binding_key(None, 'File="C:\\Bases\\Manual";', "Ручная")
    result = apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key=key, changes={"Version": "8.3.25"}),
        NEW_ID,
    )
    assert result.applied
    assert result.key == f"id:{NEW_ID}"


def test_update_of_section_with_empty_id_adds_one() -> None:
    """`ID=` с пустым значением binding_key считает отсутствующим. Проверка
    `is None` в `_apply_update` с этим расходилась, и правка такой записи
    молча теряла избранное и историю.
    """  # noqa: RUF002
    document = parse_v8i('[Пустой]\r\nConnect=File="C:\\B";\r\nID=\r\n'.encode())
    key = binding_key(None, 'File="C:\\B";', "Пустой")
    result = apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key=key, changes={"Version": "8.3.25"}),
        NEW_ID,
    )
    assert document.sections[0].id == NEW_ID
    assert result.key == f"id:{NEW_ID}"


def test_remove_reports_whether_it_found_the_target() -> None:
    document = parse_v8i(TWO_SECTIONS)
    found = apply_patch(document, SectionPatch(PatchKind.REMOVE, target_key="id:abc"), NEW_ID)
    assert (found.applied, found.key) == (True, None)
    missing = apply_patch(document, SectionPatch(PatchKind.REMOVE, target_key="id:нет"), NEW_ID)
    assert (missing.applied, missing.key) == (False, None)


def test_apply_patch_dispatches_group_patches() -> None:
    """В проде writer зовёт apply_patch, а не apply_group_patch: ветка
    диспетчера обязана быть покрыта через публичную точку входа.
    """  # noqa: RUF002
    document = parse_v8i(b"")
    result = apply_patch(
        document, GroupPatch(GroupPatchKind.CREATE, name="Архив"), NEW_ID
    )
    assert result.key == f"id:{NEW_ID}"
    assert document.sections[0].is_group


def test_add_rejects_newline_in_name() -> None:
    document = parse_v8i(b"")
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(
                PatchKind.ADD,
                name='Новая\r\n[Чужая]',
                changes={"Connect": 'File="C:\\B";'},
            ),
            NEW_ID,
        )
    assert document.sections == []


def test_rename_rejects_newline_in_name() -> None:
    """Последний неэкранированный вход в заголовок секции: правка имени."""
    document = parse_v8i(TWO_SECTIONS)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(PatchKind.UPDATE, target_key="id:abc", new_name="Демо\r\n[Чужая]"),
            NEW_ID,
        )
    assert document.sections[0].name == "Демо"
    assert len(document.sections) == 2


# -- ReorderPatch: перестановка внутри группы (задача 15) ------------------


def test_apply_patch_dispatches_reorder_patches() -> None:
    """ReorderPatch — не GroupPatch и не SectionPatch: без своей ветки раньше
    проверки GroupPatch диспетчер провалился бы в `patch.kind`, которого
    у ReorderPatch нет (`AttributeError` вместо ошибки слоя services).
    """  # noqa: RUF002
    document = parse_v8i(THREE_IN_ROOT)
    result = apply_patch(
        document, ReorderPatch(target_key="id:a3", after_key="id:a1"), NEW_ID
    )
    assert result.applied
    assert document.sections[2].get("OrderInList") == "15"


def test_reorder_changes_only_the_moved_value_when_gap_exists() -> None:
    """Зазор есть — правится одно значение, соседи не тронуты."""
    document = parse_v8i(THREE_IN_ROOT)
    apply_patch(document, ReorderPatch(target_key="id:a3", after_key="id:a1"), NEW_ID)
    values = {section.id: section.get("OrderInList") for section in document.sections}
    assert values == {"a1": "10", "a2": "20", "a3": "15"}


def test_reorder_to_front_when_after_key_is_none() -> None:
    document = parse_v8i(THREE_IN_ROOT)
    apply_patch(document, ReorderPatch(target_key="id:a3", after_key=None), NEW_ID)
    assert document.sections[2].get("OrderInList") == "9"


def test_reorder_of_missing_target_raises() -> None:
    document = parse_v8i(THREE_IN_ROOT)
    with pytest.raises(TargetGoneError):
        apply_patch(document, ReorderPatch(target_key="id:нет"), NEW_ID)


def test_reorder_anchor_from_another_group_is_rejected() -> None:
    """Ставить «после» записи из чужой группы бессмысленно — это перенос,
    а перенос между группами делает `SectionPatch`/`GroupPatch`, не эта операция.
    """  # noqa: RUF002
    document = parse_v8i(
        GROUP_AND_CHILD
        + (
            '[Отдельная]\r\nConnect=File="C:\\Bases\\S";\r\nID=sep\r\n'
            "OrderInList=5\r\nFolder=/\r\n"
        ).encode()
    )
    with pytest.raises(InvalidRequestError):
        apply_patch(document, ReorderPatch(target_key="id:sep", after_key="id:abc"), NEW_ID)


def test_reorder_anchor_that_no_longer_exists_is_rejected() -> None:
    """Ключ мог указывать на запись, удалённую извне между попытками записи."""
    document = parse_v8i(THREE_IN_ROOT)
    with pytest.raises(InvalidRequestError):
        apply_patch(document, ReorderPatch(target_key="id:a3", after_key="id:нет"), NEW_ID)


def test_reorder_reports_key_of_the_moved_section() -> None:
    document = parse_v8i(THREE_IN_ROOT)
    result = apply_patch(
        document, ReorderPatch(target_key="id:a3", after_key="id:a1"), NEW_ID
    )
    assert result.key == "id:a3"


def test_reorder_treats_implicit_and_explicit_root_as_one_group() -> None:
    """Секция без ключа `Folder` вовсе и секция с `Folder=/` — один корень.

    Найдено ревью (круг правок 1, задача 15): платформа производит именно
    такие файлы ([Ф] T-02.3 — у секции без `Folder` и секции `Folder=/`
    один и тот же родитель). Фильтр соседей идёт по
    `normalize_folder(other.folder) == parent`, а не по сырому
    `other.folder == section.folder` — сырое сравнение отличило бы `None`
    от `"/"` и разорвало бы вырожденный корень пополам: пересчиталась бы
    только часть группы, а не она целиком.
    """  # noqa: RUF002
    document = parse_v8i(
        (
            # Корень: A и C вовсе без ключа Folder, B — с Folder=/ явно.  # noqa: RUF003
            # Все три вырождены одним и тем же OrderInList=-1.  # noqa: RUF003
            '[A]\r\nConnect=File="D:\\a";\r\nID=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\r\n'
            "OrderInList=-1\r\n"
            '[B]\r\nConnect=File="D:\\b";\r\nID=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\r\n'
            "OrderInList=-1\r\nFolder=/\r\n"
            '[C]\r\nConnect=File="D:\\c";\r\nID=cccccccc-cccc-cccc-cccc-cccccccccccc\r\n'
            "OrderInList=-1\r\n"
            # Отдельная, непересекающаяся группа — её значение обязано
            # остаться нетронутым побайтово.
            '[D]\r\nConnect=File="D:\\d";\r\nID=dddddddd-dddd-dddd-dddd-dddddddddddd\r\n'
            "OrderInList=77\r\nFolder=/Клиенты\r\n"
        ).encode()
    )

    apply_patch(
        document,
        ReorderPatch(target_key="id:cccccccc-cccc-cccc-cccc-cccccccccccc", after_key=None),
        NEW_ID,
    )

    values = {section.name: section.get("OrderInList") for section in document.sections}
    # Корень пересчитан целиком: A и B тоже получили новые значения — иначе
    # часть вырожденной группы (например, обе секции без Folder) осталась  # noqa: RUF003
    # бы с прежним -1, и грузчик пересчитал бы только часть.  # noqa: RUF003
    assert values["C"] == "0"
    assert values["A"] == "1"
    assert values["B"] == "2"
    # Другая группа не тронута — ни байтом.
    assert values["D"] == "77"
