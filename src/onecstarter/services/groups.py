"""Операции над секциями-группами ibases.v8i.

Группа — секция, где `Connect` отсутствует или пуст (**[Ф]** скил
v8i-format, T-05.6). Её имя входит
в `Folder` каждой вложенной записи, поэтому смена имени или родителя обязана
переписать `Folder` всего поддерева: иначе потомки продолжат ссылаться
на путь, которого больше нет, — такой висячий `Folder` UI отрисует неявным
узлом-группой, как это делает платформа ([Ф] T-05.7), а не потеряет и не
свалит в корень.

Каскад считается по тому документу, в который патч применяется сейчас.
Список целей, собранный до чтения свежего файла, устарел бы: writer
переигрывает патч на свежем состоянии, и база, добавленную в группу штатным
стартером между попытками, такой список не переписал бы.
"""  # noqa: RUF002

from dataclasses import dataclass
from enum import Enum

from onecstarter.config.v8i import V8iDocument, V8iSection
from onecstarter.services.errors import InvalidRequestError, TargetGoneError
from onecstarter.services.model import (
    PatchResult,
    find_target,
    key_of_section,
    validate_section_name,
)
from onecstarter.services.paths import (
    ROOT,
    group_path,
    is_inside,
    normalize_folder,
    render_folder,
    retarget,
)

__all__ = [
    "GroupPatch",
    "GroupPatchKind",
    "GroupRemoval",
    "apply_group_patch",
    "group_paths",
    "require_group_exists",
]


class GroupPatchKind(Enum):
    CREATE = "create"
    RETARGET = "retarget"
    REMOVE = "remove"


class GroupRemoval(Enum):
    """Что делать с содержимым удаляемой группы.

    Значения по умолчанию нет намеренно: удалить дерево баз по невнимательности
    вызывающего нельзя.
    """  # noqa: RUF002

    PROMOTE = "promote"
    RECURSIVE = "recursive"


@dataclass(frozen=True)
class GroupPatch:
    kind: GroupPatchKind
    target_key: str | None = None
    name: str | None = None
    new_name: str | None = None
    new_folder: str | None = None
    removal: GroupRemoval | None = None


def group_paths(document: V8iDocument, skip: V8iSection | None = None) -> set[str]:
    """Собственные пути всех секций-групп документа."""
    return {
        group_path(section.folder, section.name)
        for section in document.sections
        if section.is_group and section is not skip
    }


def apply_group_patch(
    document: V8iDocument, patch: GroupPatch, new_id: str
) -> PatchResult:
    if patch.kind is GroupPatchKind.CREATE:
        return _create(document, patch, new_id)
    if patch.kind is GroupPatchKind.REMOVE:
        return _remove_group(document, patch)
    section = _target_group(document, patch)
    return _retarget_group(document, section, patch)


def _remove_group(document: V8iDocument, patch: GroupPatch) -> PatchResult:
    if patch.removal is None:
        raise InvalidRequestError(
            "Для удаления группы нужна политика для её содержимого: "
            "поднять к родителю или удалить вместе с группой"  # noqa: RUF001
        )
    if patch.target_key is None:
        raise InvalidRequestError("Для операции над группой нужен target_key")
    if find_target(document, patch.target_key) is None:
        # Идемпотентно, как удаление записи базы: пользователь хотел,
        # чтобы группы не было, — её нет. Но applied=False сообщает,  # noqa: RUF003
        # что цель не нашлась: её ключ мог смениться, а не исчезнуть.  # noqa: RUF003
        return PatchResult(applied=False, key=None)
    section = _target_group(document, patch)
    old = group_path(section.folder, section.name)
    inside = [
        other
        for other in document.sections
        if other is not section and is_inside(normalize_folder(other.folder), old)
    ]
    if patch.removal is GroupRemoval.RECURSIVE:
        for other in inside:
            document.remove_section(other)
    else:
        parent = normalize_folder(section.folder)
        _require_promotion_is_free(document, section, inside, old, parent)
        for other in inside:
            moved = retarget(normalize_folder(other.folder), old, parent)
            other.set("Folder", render_folder(moved))
    document.remove_section(section)
    return PatchResult(applied=True, key=None)


def _require_promotion_is_free(
    document: V8iDocument,
    section: V8iSection,
    inside: list[V8iSection],
    old: str,
    parent: str,
) -> None:
    """Отказать, если подъём содержимого создаст две группы с одним путём."""  # noqa: RUF002
    taken = _paths_outside(document, section, old)
    for other in inside:
        if not other.is_group:
            continue
        moved = retarget(group_path(other.folder, other.name), old, parent)
        if moved in taken:
            raise InvalidRequestError(
                f"Подгруппу «{other.name}» некуда поднять: группа «{moved}» уже есть"
            )
        taken.add(moved)


def _paths_outside(document: V8iDocument, section: V8iSection, old: str) -> set[str]:
    """Пути групп, которые останутся на месте после удаления `section`."""
    result: set[str] = set()
    for other in document.sections:
        if not other.is_group or other is section:
            continue
        path = group_path(other.folder, other.name)
        if not is_inside(path, old):
            result.add(path)
    return result


def _target_group(document: V8iDocument, patch: GroupPatch) -> V8iSection:
    if patch.target_key is None:
        raise InvalidRequestError("Для операции над группой нужен target_key")
    section = find_target(document, patch.target_key)
    if section is None:
        # Внутренний ключ в сообщение не идёт: пользователю он бесполезен,
        # а формат ключей — деталь реализации.  # noqa: RUF003
        raise TargetGoneError("Целевая группа удалена извне")
    if not section.is_group:
        # Вид секции определяется по свежему документу, а не по модели  # noqa: RUF003
        # координатора: [Ф] T-02.9 — база, у которой платформа перестала  # noqa: RUF003
        # распознавать Connect, деградирует до группы.
        raise InvalidRequestError(f"«{section.name}» — не группа, а запись базы")  # noqa: RUF001
    # Ключ группы — её собственный путь, и создавать две группы с одним путём  # noqa: RUF003
    # мы запрещаем. Но файл параллельно правит штатный стартер, поэтому такой  # noqa: RUF003
    # дубль в нём представим, а find_target вернул бы первую попавшуюся:  # noqa: RUF003
    # каскад и удаление ушли бы не в то поддерево. Внутренний ключ
    # в сообщение не идёт — формат ключей не для пользователя.
    matches = [
        other for other in document.sections if key_of_section(other) == patch.target_key
    ]
    if len(matches) > 1:
        raise InvalidRequestError(
            f"Ключу отвечает несколько секций ({len(matches)}): "
            "операция над группой неоднозначна, устраните дубль в списке"
        )
    return section


def _retarget_group(
    document: V8iDocument, section: V8iSection, patch: GroupPatch
) -> PatchResult:
    name = section.name if patch.new_name is None else patch.new_name.strip()
    _validate_name(name)
    parent = normalize_folder(
        section.folder if patch.new_folder is None else patch.new_folder
    )
    old = group_path(section.folder, section.name)
    new = group_path(parent, name)
    if new == old:
        return PatchResult(applied=True, key=key_of_section(section))
    if is_inside(parent, old):
        raise InvalidRequestError(
            f"Группу «{old}» нельзя переместить внутрь себя или своего потомка"
        )
    require_group_exists(document, parent)
    _require_path_free(document, new, skip=section)
    if name != section.name:
        section.rename(name)
    section.set("Folder", render_folder(parent))
    # Один проход по всем секциям: прямые дети, вложенные группы и их
    # содержимое несут в Folder полный путь, начинающийся с old, поэтому  # noqa: RUF003
    # посегментная замена префикса чинит поддерево целиком без рекурсии.
    for other in document.sections:
        if other is section:
            continue
        folder = normalize_folder(other.folder)
        if is_inside(folder, old):
            other.set("Folder", render_folder(retarget(folder, old, new)))
    return PatchResult(applied=True, key=key_of_section(section))


def _create(document: V8iDocument, patch: GroupPatch, new_id: str) -> PatchResult:
    name = (patch.name or "").strip()
    _validate_name(name)
    parent = normalize_folder(patch.new_folder)
    require_group_exists(document, parent)
    _require_path_free(document, group_path(parent, name), skip=None)
    section = document.append_section(name)
    # Порядок ключей — как у мастера стартера [Ф], без OrderInTree:  # noqa: RUF003
    # [Ф] T-05.8 — группа в этом составе стартеру видна и безвредна,
    # OrderInTree платформа дописывает сама при следующей перезаписи.
    section.set("ID", new_id)
    section.set("OrderInList", "-1")
    section.set("Folder", render_folder(parent))
    section.set("External", "0")
    return PatchResult(applied=True, key=key_of_section(section))


def _validate_name(name: str) -> None:
    validate_section_name(name)
    if "/" in name:
        raise InvalidRequestError(
            f"Имя группы «{name}» содержит «/» — этот символ разделяет уровни пути"
        )


def require_group_exists(document: V8iDocument, parent: str) -> None:
    """Отказать, если группы с таким путём в списке нет. Корень есть всегда.

    Платформа висячий `Folder` переживает — рисует из пути неявную группу
    без секции ([Ф] T-05.7). Но неявная группа не редактируема (нет секции —
    нет ключа), поэтому свои операции держат файл согласованным и висячих
    путей не плодят. Правило одно на весь слой: и операции над группами,
    и перенос записи базы отвергают несуществующего родителя. Живёт здесь,
    потому что здесь же живут пути групп; второй экземпляр этой проверки
    неизбежно разошёлся бы с этим и текстом, и условием.
    """  # noqa: RUF002
    if parent == ROOT:
        return
    if parent not in group_paths(document):
        raise InvalidRequestError(f"Группы «{parent}» в списке нет")


def _require_path_free(
    document: V8iDocument, path: str, skip: V8iSection | None
) -> None:
    if path in group_paths(document, skip):
        raise InvalidRequestError(f"Группа «{path}» уже существует")
