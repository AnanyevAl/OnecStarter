import pytest

from onecstarter.config.v8i import V8iDocument, parse_v8i, serialize_v8i
from onecstarter.services.errors import InvalidRequestError, TargetGoneError
from onecstarter.services.groups import (
    GroupPatch,
    GroupPatchKind,
    GroupRemoval,
    apply_group_patch,
)
from onecstarter.services.model import binding_key, find_target, group_binding_key

NEW_ID = "99999999-9999-9999-9999-999999999999"

# Дерево с вложенностью, базой в подгруппе, записью без ID и соседом,  # noqa: RUF003
# чьё имя начинается с имени группы: Клиенты / КлиентыVIP.  # noqa: RUF003
NESTED = (
    "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
    "[Розница]\r\nID=sub\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
    "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\nFolder=/Клиенты\r\n"
    "[Ручная]\r\nConnect=File=\"C:\\Bases\\Manual\";\r\nFolder=/Клиенты\r\n"
    "[Опт]\r\nConnect=File=\"C:\\Bases\\Opt\";\r\nID=opt\r\nFolder=/Клиенты/Розница\r\n"
    "[КлиентыVIP]\r\nID=vip\r\nOrderInList=-1\r\nFolder=/\r\n"  # noqa: RUF001
    "[Крупный]\r\nConnect=File=\"C:\\Bases\\Big\";\r\nID=big\r\nFolder=/КлиентыVIP\r\n"  # noqa: RUF001
).encode()


# Две группы «Архив» без ID под разными родителями. Их суррогатные ключи
# различаются только собственным путём: Connect у группы всегда None,  # noqa: RUF003
# поэтому хеш в суррогате у обеих один и тот же.  # noqa: RUF003
TWIN_GROUPS = (
    "[Клиенты]\r\nID=cli\r\nOrderInList=-1\r\nFolder=/\r\n"
    "[Поставщики]\r\nID=sup\r\nOrderInList=-1\r\nFolder=/\r\n"
    "[Архив]\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
    "[Архив]\r\nOrderInList=-1\r\nFolder=/Поставщики\r\n"
    "[Старая]\r\nConnect=File=\"C:\\Bases\\CliOld\";\r\nID=cliold\r\nFolder=/Клиенты/Архив\r\n"
    "[Прайсы]\r\nConnect=File=\"C:\\Bases\\SupOld\";\r\nID=supold\r\nFolder=/Поставщики/Архив\r\n"
).encode()

# Один и тот же собственный путь у двух групп: сами мы такое создать  # noqa: RUF003
# не даём, но файл параллельно правит штатный стартер.
SAME_PATH_GROUPS = (
    "[Клиенты]\r\nID=cli\r\nOrderInList=-1\r\nFolder=/\r\n"
    "[Архив]\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
    "[Архив]\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
).encode()


def _by_id(data: bytes) -> dict[str | None, str | None]:
    """Снять карту ID → Folder: каскад проверяется именно по ней."""
    return {section.id: section.folder for section in parse_v8i(data).sections}


def _folders_by_name(document: V8iDocument, name: str) -> list[str | None]:
    """Folder всех секций с данным именем, в порядке появления в документе."""  # noqa: RUF002
    return [section.folder for section in document.sections if section.name == name]


def test_create_writes_group_key_set() -> None:
    """[Ф] мастер стартера пишет группе ID, OrderInList=-1, Folder, OrderInTree,
    External=0. OrderInTree мы не пишем: осмысленное значение неизвестно,
    а выдуманное расставило бы группы в дереве наугад. [Ф] платформа его
    пересчитывает сама и [Ф] неизвестные ключи не удаляет — отсюда [Р],
    что отсутствие ключа безвредно.
    """  # noqa: RUF002
    document = parse_v8i(b"")
    result = apply_group_patch(
        document, GroupPatch(GroupPatchKind.CREATE, name="Архив"), NEW_ID
    )
    assert serialize_v8i(document) == (
        f"[Архив]\r\nID={NEW_ID}\r\nOrderInList=-1\r\nFolder=/\r\nExternal=0\r\n"
    ).encode()
    assert result.applied
    assert result.key == f"id:{NEW_ID}"


def test_created_section_is_a_group() -> None:
    """Признак группы — отсутствие Connect ([Ф] скил v8i-format)."""
    document = parse_v8i(b"")
    apply_group_patch(document, GroupPatch(GroupPatchKind.CREATE, name="Архив"), NEW_ID)
    assert document.sections[0].is_group


def test_create_inside_existing_group() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.CREATE, name="Архив", new_folder="/Клиенты"),
        NEW_ID,
    )
    assert document.sections[-1].folder == "/Клиенты"


def test_create_rejects_missing_parent() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(GroupPatchKind.CREATE, name="Архив", new_folder="/Нет такой"),
            NEW_ID,
        )
    assert len(document.sections) == 7


def test_create_rejects_slash_in_name() -> None:
    """Слэш разделяет уровни в Folder: имя с ним сделало бы путь неразбираемым."""  # noqa: RUF002
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document, GroupPatch(GroupPatchKind.CREATE, name="Клиенты/Опт"), NEW_ID
        )


def test_create_rejects_empty_name() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(document, GroupPatch(GroupPatchKind.CREATE, name="   "), NEW_ID)


def test_create_rejects_occupied_path() -> None:
    """Две группы с одним путём ломают дерево: build_tree держит потомков
    в словаре по пути, и обе группы получили бы один список детей.
    """  # noqa: RUF002
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(document, GroupPatch(GroupPatchKind.CREATE, name="Клиенты"), NEW_ID)


def test_create_rejects_newline_in_name() -> None:
    """Заголовок секции не экранируется: имя с переводом строки записало бы
    в файл пользователя лишние секции.
    """  # noqa: RUF002
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(GroupPatchKind.CREATE, name='Архив\r\n[Чужая]\r\nConnect=File="C:\\X";'),
            NEW_ID,
        )
    assert len(document.sections) == 7


def test_rename_group_rewrites_folder_of_whole_subtree() -> None:
    """Имя группы входит в Folder каждой вложенной записи ([Ф] T-02.3):
    переименовав только заголовок, мы оторвали бы от группы всё её содержимое.
    """
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["sub"] == "/Партнёры"
    assert folders["abc"] == "/Партнёры"
    assert folders["opt"] == "/Партнёры/Розница"


def test_rename_group_changes_its_own_header() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    assert document.sections[0].name == "Партнёры"


def test_rename_does_not_touch_prefix_sibling() -> None:
    """`КлиентыVIP` начинается с `Клиенты`, но потомком ей не приходится."""  # noqa: RUF002
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["vip"] == "/"
    assert folders["big"] == "/КлиентыVIP"  # noqa: RUF001


def test_move_group_rewrites_subtree() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.RETARGET, target_key="id:sub", new_folder="/КлиентыVIP"  # noqa: RUF001
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["sub"] == "/КлиентыVIP"  # noqa: RUF001
    assert folders["opt"] == "/КлиентыVIP/Розница"  # noqa: RUF001


def test_move_group_to_root() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:sub", new_folder="/"),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["sub"] == "/"
    assert folders["opt"] == "/Розница"


def test_rename_and_move_at_once() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.RETARGET,
            target_key="id:sub",
            new_name="Опт и розница",
            new_folder="/КлиентыVIP",  # noqa: RUF001
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["sub"] == "/КлиентыVIP"  # noqa: RUF001
    assert folders["opt"] == "/КлиентыVIP/Опт и розница"  # noqa: RUF001


def test_binding_keys_of_children_survive_the_cascade() -> None:
    """Ключ привязки строится из ID либо из хеша Connect и имени; Folder
    в него не входит. Значит избранное и история потомков остаются на местах.
    """
    document = parse_v8i(NESTED)
    manual = binding_key(None, 'File="C:\\Bases\\Manual";', "Ручная")
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    assert find_target(document, manual) is not None
    assert find_target(document, "id:opt") is not None


def test_retarget_to_the_same_path_is_a_noop() -> None:
    document = parse_v8i(NESTED)
    before = serialize_v8i(parse_v8i(NESTED))
    result = apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Клиенты"),
        NEW_ID,
    )
    assert result.applied
    assert serialize_v8i(document) == before


def test_move_into_own_descendant_is_rejected() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.RETARGET,
                target_key="id:grp",
                new_folder="/Клиенты/Розница",
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == NESTED


def test_move_into_itself_is_rejected() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.RETARGET, target_key="id:grp", new_folder="/Клиенты"
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == NESTED


def test_retarget_rejects_occupied_path() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.RETARGET, target_key="id:vip", new_name="Клиенты"
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == NESTED


def test_retarget_rejects_missing_parent() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.RETARGET, target_key="id:sub", new_folder="/Нет такой"
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == NESTED


def test_retarget_rejects_a_base() -> None:
    """Вид секции определяется по свежему документу: [Ф] T-02.9 — база,
    у которой платформа перестала распознавать Connect, деградирует до группы.
    """  # noqa: RUF002
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(GroupPatchKind.RETARGET, target_key="id:abc", new_name="Другое"),
            NEW_ID,
        )
    assert serialize_v8i(document) == NESTED


def test_cascade_ignores_sections_without_folder() -> None:
    """Секция без ключа Folder лежит в корне: собственный путь группы никогда
    не равен корню, поэтому потомком она быть не может и каскад её не трогает.

    Проверяется вместе с тем, что каскад вообще отработал: без этого тест
    остался бы зелёным и при полностью неработающей операции.
    """  # noqa: RUF002
    data = (
        "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
        '[Ничейная]\r\nConnect=File="C:\\Bases\\Loose";\r\nID=loose\r\n'
    ).encode()
    document = parse_v8i(data)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    group = next(section for section in document.sections if section.id == "grp")
    assert group.name == "Партнёры"
    loose = next(section for section in document.sections if section.id == "loose")
    assert loose.folder is None


def test_retarget_of_missing_target_raises() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(TargetGoneError):
        apply_group_patch(
            document,
            GroupPatch(GroupPatchKind.RETARGET, target_key="id:нет", new_name="Другое"),
            NEW_ID,
        )


def test_promote_lifts_children_to_the_parent() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE, target_key="id:grp", removal=GroupRemoval.PROMOTE
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert "grp" not in folders
    assert folders["sub"] == "/"
    assert folders["abc"] == "/"
    # Относительная структура подгруппы сохраняется: база осталась в Рознице.
    assert folders["opt"] == "/Розница"


def test_promote_of_nested_group_lifts_to_its_own_parent() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE, target_key="id:sub", removal=GroupRemoval.PROMOTE
        ),
        NEW_ID,
    )
    assert _by_id(serialize_v8i(document))["opt"] == "/Клиенты"


def test_recursive_removes_the_whole_subtree() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE, target_key="id:grp", removal=GroupRemoval.RECURSIVE
        ),
        NEW_ID,
    )
    names = [section.name for section in document.sections]
    assert names == ["КлиентыVIP", "Крупный"]  # noqa: RUF001


def test_recursive_keeps_everything_outside() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE, target_key="id:vip", removal=GroupRemoval.RECURSIVE
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert "vip" not in folders
    assert "big" not in folders
    assert folders["opt"] == "/Клиенты/Розница"


def test_removal_without_policy_is_rejected() -> None:
    """Политика обязательна: удалить дерево баз по невнимательности нельзя."""
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document, GroupPatch(GroupPatchKind.REMOVE, target_key="id:grp"), NEW_ID
        )
    # Сравнение с исходными байтами, а не только числом секций: усечённая  # noqa: RUF003
    # мутация могла бы поменять Folder потомков, не тронув их количество.
    assert serialize_v8i(document) == NESTED


def test_promote_rejects_name_collision_at_the_parent() -> None:
    """Подъём, создающий два одинаковых пути, — тот же дефект, что запрещает
    RETARGET: build_tree отдал бы обеим группам один список потомков.
    """
    data = (
        "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
        "[Розница]\r\nID=sub\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
        "[Розница]\r\nID=twin\r\nOrderInList=-1\r\nFolder=/\r\n"
    ).encode()
    document = parse_v8i(data)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.REMOVE, target_key="id:grp", removal=GroupRemoval.PROMOTE
            ),
            NEW_ID,
        )
    # Сравнение с исходными байтами собственной фикстуры, а не только числом  # noqa: RUF003
    # секций: усечённая мутация могла бы поменять Folder, не тронув их число.
    assert serialize_v8i(document) == data


def test_promote_rejects_collision_between_two_lifted_subgroups() -> None:
    """Две поднимаемые подгруппы с одинаковым именем столкнутся друг с другом
    у общего родителя — коллизия ловится и без внешнего дубля.
    """  # noqa: RUF002
    data = (
        "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
        "[Розница]\r\nID=one\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
        "[Розница]\r\nID=two\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
    ).encode()
    document = parse_v8i(data)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.REMOVE, target_key="id:grp", removal=GroupRemoval.PROMOTE
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == data


def test_promote_rejects_collision_when_only_one_subgroup_conflicts() -> None:
    """Коллизия ловится, даже когда сталкивается лишь одна из нескольких
    поднимаемых подгрупп, а остальные поднялись бы свободно.
    """  # noqa: RUF002
    data = (
        "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
        "[Опт]\r\nID=two\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
        "[Розница]\r\nID=one\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
        "[Розница]\r\nID=twin\r\nOrderInList=-1\r\nFolder=/\r\n"
    ).encode()
    document = parse_v8i(data)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.REMOVE, target_key="id:grp", removal=GroupRemoval.PROMOTE
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == data


def test_remove_of_missing_target_is_idempotent() -> None:
    """Пользователь хотел, чтобы группы не было, — её нет. Но «не нашли»
    и «удалили» вызывающий обязан различать: ключ мог смениться извне.
    """  # noqa: RUF002
    document = parse_v8i(NESTED)
    result = apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE, target_key="id:нет", removal=GroupRemoval.PROMOTE
        ),
        NEW_ID,
    )
    assert (result.applied, result.key) == (False, None)
    assert len(document.sections) == 7


def test_remove_rejects_a_base() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.REMOVE, target_key="id:abc", removal=GroupRemoval.PROMOTE
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == NESTED


def test_recursive_removes_only_the_group_at_the_requested_path() -> None:
    """Одинаковые имена подгрупп под разными родителями — норма. Если бы
    суррогатный ключ группы строился из имени, RECURSIVE снёс бы первую
    попавшуюся «Архив» вместе с чужим содержимым и отчитался об успехе.
    """  # noqa: RUF002
    document = parse_v8i(TWIN_GROUPS)
    result = apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE,
            target_key=group_binding_key(None, "Поставщики/Архив"),
            removal=GroupRemoval.RECURSIVE,
        ),
        NEW_ID,
    )
    assert result.applied
    assert _folders_by_name(document, "Архив") == ["/Клиенты"]
    folders = _by_id(serialize_v8i(document))
    assert folders["cliold"] == "/Клиенты/Архив"
    assert "supold" not in folders


def test_retarget_cascades_only_over_its_own_subtree() -> None:
    """Каскад идёт по пути, а тёзка под другим родителем к поддереву
    не относится: её содержимое обязано остаться на месте.
    """  # noqa: RUF002
    document = parse_v8i(TWIN_GROUPS)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.RETARGET,
            target_key=group_binding_key(None, "Клиенты/Архив"),
            new_name="Хранилище",
        ),
        NEW_ID,
    )
    assert _folders_by_name(document, "Архив") == ["/Поставщики"]
    assert _folders_by_name(document, "Хранилище") == ["/Клиенты"]
    folders = _by_id(serialize_v8i(document))
    assert folders["cliold"] == "/Клиенты/Хранилище"
    assert folders["supold"] == "/Поставщики/Архив"


def test_operation_on_ambiguous_key_is_rejected() -> None:
    """Две группы с одним путём мы создать не даём, но штатный стартер правит
    тот же файл. Молча выбрать первую значило бы каскадить наугад.
    """  # noqa: RUF002
    document = parse_v8i(SAME_PATH_GROUPS)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.REMOVE,
                target_key=group_binding_key(None, "Клиенты/Архив"),
                removal=GroupRemoval.RECURSIVE,
            ),
            NEW_ID,
        )
    assert serialize_v8i(document) == SAME_PATH_GROUPS


def test_ambiguous_key_message_carries_no_binding_key() -> None:
    """Внутренний ключ в сообщение пользователю не идёт: формат ключей —
    деталь реализации, притом суррогат ключа базы несёт хеш строки
    соединения (инвариант 5 CLAUDE.md).
    """
    document = parse_v8i(SAME_PATH_GROUPS)
    key = group_binding_key(None, "Клиенты/Архив")
    with pytest.raises(InvalidRequestError) as info:
        apply_group_patch(
            document,
            GroupPatch(
                GroupPatchKind.REMOVE, target_key=key, removal=GroupRemoval.RECURSIVE
            ),
            NEW_ID,
        )
    assert key not in str(info.value)


def test_promote_lifts_a_base_to_the_root() -> None:
    """Отдельный случай: родитель удаляемой группы — корень, и Folder
    потомка обязан записаться как `/`, а не пустой строкой.
    """  # noqa: RUF002
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.REMOVE, target_key="id:vip", removal=GroupRemoval.PROMOTE
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert "vip" not in folders
    assert folders["big"] == "/"
