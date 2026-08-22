"""Патч секции ibases.v8i и его применение к разобранному документу.

Единица записи — патч, а не «сохранить документ»: при внешнем изменении
файла патч переигрывается на свежем состоянии (см. writer). Цель ищется
по ID или суррогатному ключу, но никогда по позиции секции — порядок
секций между сеансами не сохраняется ([Ф] каноникализация платформы).

Состав ключей новой записи: имя секции, Connect, наш ID и OrderInList=-1.
Известен [Ф] состав, который мастер стартера пишет для секции-группы;
для секции-базы он не снят, поэтому OrderInTree и External не выдумываем.
"""  # noqa: RUF002

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from onecstarter.config.v8i import KeyValueLine, V8iDocument, V8iSection
from onecstarter.services.errors import InvalidRequestError, TargetGoneError
from onecstarter.services.groups import (
    GroupPatch,
    apply_group_patch,
    require_group_exists,
)
from onecstarter.services.model import (
    PatchResult,
    find_target,
    key_of_section,
    parse_order,
    validate_connect,
    validate_section_name,
)
from onecstarter.services.order import format_order, reorder_values, sort_key
from onecstarter.services.paths import normalize_folder, render_folder

__all__ = [
    "InvalidRequestError",
    "Patch",
    "PatchKind",
    "PatchResult",
    "ReorderPatch",
    "SectionPatch",
    "TargetGoneError",
    "apply_patch",
    "find_target",
]


class PatchKind(Enum):
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


@dataclass(frozen=True)
class SectionPatch:
    kind: PatchKind
    target_key: str | None = None
    name: str | None = None
    new_name: str | None = None
    changes: Mapping[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ReorderPatch:
    """Переставить запись внутри её группы. `after_key is None` — в начало.

    Только позиция среди соседей одной группы — задача 15, спека 4b, §4.
    Перенос между группами не отсюда: он меняет `Folder` и остаётся
    операцией `SectionPatch`/`GroupPatch` ([Р] ограничение v1, §12 — задача 14).
    """  # noqa: RUF002

    target_key: str
    after_key: str | None = None


Patch = SectionPatch | GroupPatch | ReorderPatch


def apply_patch(document: V8iDocument, patch: Patch, new_id: str) -> PatchResult:
    if isinstance(patch, ReorderPatch):
        return _apply_reorder(document, patch)
    if isinstance(patch, GroupPatch):
        return apply_group_patch(document, patch, new_id)
    if patch.kind is PatchKind.ADD:
        return _apply_add(document, patch, new_id)
    if patch.target_key is None:
        raise InvalidRequestError("Для UPDATE и REMOVE нужен target_key")
    section = find_target(document, patch.target_key)
    if patch.kind is PatchKind.REMOVE:
        # Идемпотентно: пользователь хотел, чтобы записи не было — её нет.
        # Но «не нашли» и «удалили» — разные исходы, и вызывающий обязан их  # noqa: RUF003
        # различать: цель могла сменить ключ, а не исчезнуть.  # noqa: RUF003
        if section is None:
            return PatchResult(applied=False, key=None)
        _reject_group(section, GROUP_REMOVE_HINT)
        document.remove_section(section)
        return PatchResult(applied=True, key=None)
    if section is None:
        # Ключ может быть хешем строки соединения — не тащим его в сообщение.  # noqa: RUF003
        raise TargetGoneError("Целевая запись удалена извне")
    _reject_group(section, GROUP_UPDATE_HINT)
    _apply_update(document, section, patch, new_id)
    return PatchResult(applied=True, key=key_of_section(section))


GROUP_UPDATE_HINT = (
    "используйте изменение группы — оно переписывает Folder вложенных записей"
)
GROUP_REMOVE_HINT = (
    "используйте удаление группы с явной политикой для её содержимого"  # noqa: RUF001
)


def _reject_group(section: V8iSection, hint: str) -> None:
    """Отсеять секцию-группу из операций над записью базы.

    Имя группы входит в `Folder` каждой вложенной записи, поэтому правка
    её заголовка или `Folder` в обход каскада разрушает дерево, а удаление
    оставляет потомков сиротами.
    """  # noqa: RUF002
    if section.is_group:
        raise InvalidRequestError(f"«{section.name}» — секция-группа: {hint}")


def _require_target_folder_exists(
    document: V8iDocument, changes: Mapping[str, str | None]
) -> None:
    """Проверить, что группа, в которую переносится запись, существует.

    Без проверки в `Folder` попадал любой путь, и запись становилась сиротой:
    в дереве она видна в корне с пометкой, но пользователь просил другого.

    Сам предикат — общий с операциями над группами: правило одно, и своя
    копия здесь разошлась бы с ним текстом сообщения или условием.
    """  # noqa: RUF002
    for key, value in changes.items():
        if key.casefold() != "folder" or value is None:
            continue
        require_group_exists(document, normalize_folder(value))


def _reject_ambiguous_keys(changes: Mapping[str, str | None]) -> None:
    """Отвергнуть изменения с дублями ключей, различающимися регистром.

    Применение пишет каждый ключ изменений, а `V8iSection.set` сливает их
    без учёта регистра — побеждает последний. Валидация, смотревшая
    на первое совпадение, при дубле ничего не гарантирует: финальное ревью
    ветки (18.08.2026) воспроизвело, как `Connect`/`CONNECT` доносил пустое
    размещение до файла в обход рубежа. Дубль — противоречивый запрос,
    а не вариант записи.
    """  # noqa: RUF002
    seen: dict[str, str] = {}
    for key in changes:
        first = seen.setdefault(key.casefold(), key)
        if first != key:
            raise InvalidRequestError(
                f"Изменения содержат один ключ дважды в разном регистре: "
                f"{first} и {key}"
            )


def _connect_change(changes: Mapping[str, str | None]) -> tuple[bool, str | None]:
    """`Connect` из патча: (ключ присутствует, значение).

    Три состояния в одной точке: (False, None) — ключ не трогают,
    (True, None) — ключ снимается, (True, str) — новое значение. Раньше
    их восстанавливали две функции с зависимостью от порядка вызова.
    Имя ключа сравнивается без учёта регистра — так же, как его находит
    сам формат (`_remove_key`); дубли отсеяны `_reject_ambiguous_keys`
    до этого вызова, поэтому совпадение не больше одного.
    """  # noqa: RUF002
    for key, value in changes.items():
        if key.casefold() == "connect":
            return True, value
    return False, None


def _apply_reorder(document: V8iDocument, patch: ReorderPatch) -> PatchResult:
    """Переставить секцию внутри своей группы правкой `OrderInList` соседей.

    Соседи собираются заново из **свежего** документа: тот же приём, что
    у каскада групп (`groups.apply_group_patch`) — writer переигрывает патч
    поверх состояния, изменившегося извне (штатным стартером между нашими
    попытками), и список целей, собранный раньше, был бы устаревшим.

    Сортировка соседей — `order.sort_key`, тот же ключ, что строит показ
    в `catalog.items_from_document`. Подпоследовательность стабильно
    отсортированного списка совпадает со стабильной сортировкой
    подпоследовательности, поэтому сбор в файловом порядке (`document.sections`)
    плюс стабильная сортировка этим ключом даёт тот же порядок, что видит
    пользователь. Две копии этого правила разъехались бы — отсюда общая
    функция вместо своей копии здесь.

    Соседи собираются по `normalize_folder(other.folder) == parent`, а не по
    сырому `other.folder == section.folder`: **[Ф]** T-02.3 — у секции без
    ключа `Folder` вовсе и у секции с `Folder=/` один и тот же родитель
    (корень), платформа производит оба варианта. Сырое сравнение отличило бы
    `None` от `"/"` и разорвало бы такой корень пополам — часть вырожденной
    группы осталась бы непересчитанной (найдено ревью, круг правок 1,
    задача 15; см. `test_reorder_treats_implicit_and_explicit_root_as_one_
    group`).
    """  # noqa: RUF002
    section = find_target(document, patch.target_key)
    if section is None:
        raise TargetGoneError("Переставляемая запись удалена извне")
    parent = normalize_folder(section.folder)
    siblings = sorted(
        (other for other in document.sections if normalize_folder(other.folder) == parent),
        key=lambda other: sort_key(parse_order(other.get("OrderInList"))),
    )
    orders = [parse_order(other.get("OrderInList")) for other in siblings]
    # Поиск по идентичности объекта, а не по `list.index`/`in`: `V8iSection` —  # noqa: RUF003
    # обычный dataclass со структурным `__eq__`, и две секции с побайтово  # noqa: RUF003
    # одинаковым содержимым (не такая уж редкость — скопированная запись)
    # сравнялись бы равными, отдав не тот индекс (находка ревью, круг
    # правок 1, задача 15; мелочь, но ловушка на будущее).
    moved = _index_of(siblings, section)
    # `section` — источник `parent` и попадает в `siblings` по построению
    # (тот же фильтр, что собрал сам `siblings`): `assert`, а не ещё одна  # noqa: RUF003
    # проверка на None, только чтобы объяснить mypy структурную гарантию.
    assert moved is not None
    after: int | None = None
    if patch.after_key is not None:
        anchor = find_target(document, patch.after_key)
        anchor_index = _index_of(siblings, anchor) if anchor is not None else None
        if anchor_index is None:
            raise InvalidRequestError(
                "Запись, после которой нужно поставить, лежит в другой группе "
                "или удалена извне"
            )
        after = anchor_index
    for index, value in reorder_values(orders, moved, after).items():
        siblings[index].set("OrderInList", format_order(value))
    return PatchResult(applied=True, key=key_of_section(section))


def _index_of(siblings: list[V8iSection], target: V8iSection) -> int | None:
    """Индекс `target` в `siblings` по идентичности объекта, не по значению."""
    return next((index for index, other in enumerate(siblings) if other is target), None)


def _apply_add(document: V8iDocument, patch: SectionPatch, new_id: str) -> PatchResult:
    # Значение сохраняется в переменную, а не подставляется дважды: mypy --strict  # noqa: RUF003
    # не связывает аргумент вызова с `patch.name`, и после проверки тип остался бы  # noqa: RUF003
    # `str | None` для `append_section`.
    name = patch.name or ""
    validate_section_name(name)
    _reject_ambiguous_keys(patch.changes)
    _present, connect = _connect_change(patch.changes)
    if connect is None:
        # `{"Connect": None}` и отсутствие ключа равносильны: значения None
        # ADD не пишет, а секция без Connect — группа, у групп своя операция.  # noqa: RUF003
        raise InvalidRequestError(
            "Новой записи базы нужна строка соединения: секция без Connect — "
            "это группа, группы создаёт своя операция"
        )
    validate_connect(connect)
    _require_target_folder_exists(document, patch.changes)
    section = document.append_section(name)
    for key, value in patch.changes.items():
        if value is not None:
            _set_value(section, key, value)
    section.set("ID", new_id)
    section.set("OrderInList", "-1")
    return PatchResult(applied=True, key=key_of_section(section))


def _apply_update(
    document: V8iDocument, section: V8iSection, patch: SectionPatch, new_id: str
) -> None:
    _reject_ambiguous_keys(patch.changes)
    present, connect = _connect_change(patch.changes)
    if present and connect is None:
        # Признак группы — отсутствие Connect ([Ф] скил v8i-format): снятие
        # ключа меняет не значение, а вид секции — наши данные группам  # noqa: RUF003
        # не подмешиваются, избранное с историей молча отвязались бы.  # noqa: RUF003
        raise InvalidRequestError(
            "Снять Connect у записи базы нельзя: без него секция станет "  # noqa: RUF001
            "группой. Удалите запись, если она больше не нужна, или "
            "задайте другую строку соединения"
        )
    if connect is not None:
        validate_connect(connect)
    _require_target_folder_exists(document, patch.changes)
    if patch.new_name:
        _rename(section, patch.new_name)
    for key, value in patch.changes.items():
        if value is None:
            _remove_key(section, key)
        else:
            _set_value(section, key, value)
    # ID дописывается только той записи, которую пользователь правит через нас.
    # Проверка идёт по истинности, а не по `is None`: ключ `ID=` с пустым  # noqa: RUF003
    # значением binding_key уже считает отсутствующим, и расхождение этих двух
    # проверок молча теряло привязку наших данных.
    #
    # Вид секции здесь не проверяется: группа сюда не доходит. На входе её  # noqa: RUF003
    # отсеивает `_reject_group`, а стать группой по ходу правки секция  # noqa: RUF003
    # не может — снятие `Connect` отвергнуто выше (`present and connect is None`).
    if not section.id:
        section.set("ID", new_id)


def _rename(section: V8iSection, new_name: str) -> None:
    # Два рубежа по слоям: `services` владеет контрактом запроса и отказывает
    # раньше и своим типом исключения, `config` владеет форматом и обязан
    # отказать в порче байтов, кто бы его ни звал.  # noqa: RUF003
    validate_section_name(new_name)
    section.rename(new_name)


def _set_value(section: V8iSection, key: str, value: str) -> None:
    """Записать пару ключ-значение, приведя `Folder` к форме платформы.

    Путь мы принимаем в любой форме, а хранить обязаны в одной: существование
    группы проверяется по нормализованному значению, и запись сырого означала
    бы, что в файл попадает то, что мы сами понимаем только после нормализации.
    Форму задаёт `paths.render_folder` — та же, которой пишут `Folder`
    операции над группами, иначе в одном файле оказались бы две формы записи
    одного пути.

    Общая точка для `ADD` и `UPDATE`: разойдясь, они писали бы `Folder`
    по-разному в зависимости от того, как запись создана.
    """  # noqa: RUF002
    if key.casefold() == "folder":
        section.set(key, render_folder(normalize_folder(value)))
        return
    section.set(key, value)


def _remove_key(section: V8iSection, key: str) -> None:
    wanted = key.casefold()
    section.lines[:] = [
        line
        for line in section.lines
        if not (isinstance(line, KeyValueLine) and line.key.casefold() == wanted)
    ]
