"""Витрина раздела «Базы»: чистая логика представления, без Qt (инвариант 1).

Строки дерева, фильтрация и содержимое колонки версии считаются здесь
и покрываются табличными тестами; слой ui только отображает готовое.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum

from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.selection import ResolutionSource, resolve_version
from onecstarter.domain.version import Arch, Installation
from onecstarter.services.catalog import CommonListError, TreeNode, build_tree
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.settings import ListOrder

CONTENT_NAME_LIMIT = 10
# Помечает подгруппу в плоском списке имён `group_contents`: без пометки
# «Розница» (подгруппа) неотличима от «Демо Розница» (база внутри неё) —
# ровно та информация, которая нужна перед каскадным удалением (круг
# правок 1 ревью задачи 12).
GROUP_CONTENT_MARK = " (группа)"

_EPOCH = datetime.min.replace(tzinfo=UTC)

IMPLICIT_NOTE = (
    "Группы нет в файле — есть только путь Folder. Платформа рисует такой "
    "узел, не создавая секции; операции над ним невозможны."
)
COMMON_NOTE = (
    "Запись из общего списка (CommonInfoBases). Общий список доступен "
    "только для чтения."
)
EMPTY_CONNECT_NOTE = (
    "У секции пустой ключ Connect=. Платформа показывает её группой, "  # noqa: RUF001
    "но при первой же перезаписи удалит Connect= и вычистит Version."
)

# Видимые пометки в самой метке строки. Тултипа недостаточно: раздел
# рассчитан на работу с клавиатуры, наведения мышью может не быть вовсе.  # noqa: RUF003
BROKEN_SUFFIX = "(не разобрано)"
COMMON_SUFFIX = "(в общем списке)"


class RowKind(Enum):
    SECTION = "section"
    GROUP = "group"
    IMPLICIT_GROUP = "implicit-group"
    BASE = "base"
    NOTE = "note"


@dataclass(frozen=True)
class Row:
    kind: RowKind
    label: str
    item: InfobaseItem | None
    children: tuple["Row", ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class VersionCell:
    text: str
    problem: bool
    hint: str | None


def display_forest(
    items: Sequence[InfobaseItem],
    tree: Sequence[TreeNode],
    common_errors: Sequence[CommonListError],
    *,
    recent_limit: int,
    order: ListOrder,
) -> list[Row]:
    """Собрать лес раздела: Избранное, Недавние, дерево файла, Общие списки.

    Пустые виртуальные ветки не показываются — они шум. Порядок записей
    внутри веток повторяет порядок items (он уже отсортирован по OrderInList),
    Недавние — по времени запуска, новые сверху.

    `recent_limit` — обязательный аргумент, а не константа с умолчанием:
    это пользовательская настройка (спека §5), и значение по умолчанию
    здесь было бы вторым источником истины рядом с
    `settings.DEFAULT_RECENT_LIMIT`. `0` гасит ветку целиком. `order` —
    так же обязателен и по той же причине; `ALPHABETICAL` сортирует дерево
    файла, «Избранное» и «Общие списки» (`sort_rows`), «Недавние» всегда
    по времени.
    """  # noqa: RUF002
    alphabetical = order is ListOrder.ALPHABETICAL
    forest: list[Row] = []
    bases = [item for item in items if not item.is_group]
    favorites = [_base_row(item) for item in bases if item.favorite]
    if alphabetical:
        favorites = _sorted_siblings(favorites)
    if favorites:
        forest.append(Row(RowKind.SECTION, "Избранное", None, tuple(favorites)))
    launched = sorted(
        (item for item in bases if item.last_launched_at is not None),
        key=lambda item: item.last_launched_at or _EPOCH,
        reverse=True,
    )
    recent = tuple(_base_row(item) for item in launched[:recent_limit])
    if recent:
        forest.append(Row(RowKind.SECTION, "Недавние", None, recent))
    file_rows = [_row_of(node) for node in tree]
    forest.extend(sort_rows(file_rows) if alphabetical else file_rows)
    common = [item for item in items if item.source is InfobaseSource.COMMON]
    common_rows = [_row_of(node) for node in build_tree(common)]
    if alphabetical:
        common_rows = sort_rows(common_rows)
    common_rows.extend(
        Row(RowKind.NOTE, f"{error.path}: {error.message}", None)
        for error in common_errors
    )
    if common_rows:
        forest.append(Row(RowKind.SECTION, "Общие списки", None, tuple(common_rows)))
    return forest


def filter_rows(rows: Sequence[Row], query: str) -> list[Row]:
    """Отфильтровать лес по подстроке имени без учёта регистра.

    [Ф] T-05.3: платформа сравнивает имена баз регистронезависимо — поиск
    ведёт себя так же (casefold). Совпавший узел остаётся со всем поддеревом;
    предок совпавшего — с отфильтрованными потомками. NOTE-строки сами
    не совпадают никогда и выживают только в поддереве совпавшего узла.
    """  # noqa: RUF002
    needle = query.strip().casefold()
    if not needle:
        return list(rows)
    kept: list[Row] = []
    for row in rows:
        if row.kind is not RowKind.NOTE and needle in row.label.casefold():
            kept.append(row)
            continue
        children = filter_rows(row.children, query)
        if children:
            kept.append(replace(row, children=tuple(children)))
    return kept


def collation_key(text: str) -> tuple[str, str]:
    """Ключ алфавитного порядка (T-11, п. 2): без учёта регистра, «ё» как «е».

    [Р] Детерминированное правило вместо `locale.strxfrm`: результат
    не зависит от локали машины и проверяется таблично. Латиница идёт
    перед кириллицей — как в Проводнике Windows; «ё» приравнена к «е»,
    как в словарях (по кодам она стояла бы после «я»). Второй элемент —
    полный casefold — делает порядок «Ель»/«Ёль» устойчивым.
    """  # noqa: RUF002
    folded = text.casefold()
    return (folded.replace("ё", "е"), folded)  # noqa: RUF001


def _sorted_siblings(rows: Sequence[Row]) -> list[Row]:
    """Группы (и неявные узлы) перед базами, внутри класса — по `collation_key`;

    NOTE — в конце, строки других видов (SECTION) — в конце как есть, без
    сортировки (находка финального ревью ветки: раньше отбрасывались молча).
    """
    groups = sorted(
        (row for row in rows if row.kind in (RowKind.GROUP, RowKind.IMPLICIT_GROUP)),
        key=lambda row: collation_key(row.label),
    )
    bases = sorted(
        (row for row in rows if row.kind is RowKind.BASE),
        key=lambda row: collation_key(row.label),
    )
    notes = [row for row in rows if row.kind is RowKind.NOTE]
    others = [
        row
        for row in rows
        if row.kind not in (RowKind.GROUP, RowKind.IMPLICIT_GROUP, RowKind.BASE, RowKind.NOTE)
    ]
    return [*groups, *bases, *notes, *others]


def sort_rows(rows: Sequence[Row]) -> list[Row]:
    """Алфавитный порядок всего поддерева, рекурсивно (режим `ListOrder.ALPHABETICAL`)."""
    return [
        replace(row, children=tuple(sort_rows(row.children)))
        for row in _sorted_siblings(rows)
    ]


def row_label(row: Row) -> str:
    """Метка строки с видимыми пометками — то, что рисуется в колонке имени.

    Считается здесь, а не в Qt-слое: пометка «не разобрано» — обязательство
    спеки 4a, §2, и его нужно проверять табличным тестом, а не через
    QStandardItem. Само `row.label` остаётся чистым именем — по нему идёт
    поиск, и суффикс не должен ни мешать найти базу, ни находиться сам.
    """  # noqa: RUF002
    item = row.item
    if item is None:
        return row.label
    parts = [row.label]
    if item.parse_error:
        parts.append(BROKEN_SUFFIX)
    if item.in_common_list:
        parts.append(COMMON_SUFFIX)
    return " ".join(parts)


def version_cell(
    item: InfobaseItem,
    installations: Sequence[Installation],
    cfg_rules: Sequence[DefaultVersionRule],
    *,
    discovery_pending: bool = False,
) -> VersionCell:
    """Колонка версии: наш выбор, подсветка проблемы, подсказка о расхождении.

    Подсказка «штатный стартер запустил бы …» появляется только при
    фактическом расхождении с платформой: fallback уже посчитан
    по платформенным правилам ([Ф] T-05.5, задача 1 этого плана).

    `discovery_pending` — обнаружение платформ ещё идёт (спека T-04.6, §3.4):
    колонка показывает «…» вместо разрешения версии, потому что пустой
    список установок в этот момент означает «ещё не искали», а не «нет
    установленных версий». Веб-баз не касается — им версия не разрешается.
    """  # noqa: RUF002
    if item.is_group:
        return VersionCell("", False, None)
    if item.kind is ConnectKind.WEB:
        return VersionCell("веб", False, None)
    if discovery_pending:
        # Пустой список установок и «обнаружение не завершено» — разные
        # состояния (спека T-04.6, §3.4): вывести второе из первого нельзя,
        # колонка врала бы «нет установленных версий», пока фон работает.
        return VersionCell("…", False, None)
    resolution = resolve_version(
        item.requested_version,
        item.section_default_version,
        cfg_rules,
        [installation.version for installation in installations],
    )
    if resolution.version is None:
        if resolution.source is ResolutionSource.INVALID_REQUEST:
            text = f"{item.requested_version} — не разобрана"
        elif item.requested_version is None:
            text = "нет установленных версий"
        else:
            text = f"{item.requested_version} — не установлена"
        if resolution.fallback is not None:
            hint = f"Штатный стартер молча запустил бы {resolution.fallback}"
        else:
            hint = "Установленных версий платформы не найдено"
        return VersionCell(text, True, hint)
    arch = next(
        (
            _ARCH_LABEL[installation.arch]
            for installation in installations
            if installation.version == resolution.version
        ),
        "",
    )
    text = f"{resolution.version} {arch}".strip()
    if resolution.fallback == resolution.version:
        return VersionCell(text, False, None)
    if resolution.fallback is None:
        return VersionCell(
            text, False, "Штатный стартер не нашёл бы установленной версии"
        )
    return VersionCell(text, False, f"Штатный стартер запустил бы {resolution.fallback}")


_ARCH_LABEL = {Arch.X64: "x64", Arch.X86: "x86", Arch.UNKNOWN: ""}


def is_degraded_group(item: InfobaseItem) -> bool:
    """Секция-группа с пустым `Connect=`, а не с отсутствующим ключом.

    `is_group` у обеих True ([Ф] T-05.6), различает их только пустая строка
    против `None`: `V8iSection.connect` возвращает значение ключа как есть.
    """  # noqa: RUF002
    return item.is_group and item.connect == ""


def _base_note(item: InfobaseItem) -> str | None:
    parts: list[str] = []
    if item.parse_error:
        parts.append(f"Не разобрано: {item.parse_error}")  # noqa: RUF001
    if item.source is InfobaseSource.COMMON or item.in_common_list:
        parts.append(COMMON_NOTE)
    if is_degraded_group(item):
        parts.append(EMPTY_CONNECT_NOTE)
    return "\n".join(parts) or None


def _base_row(item: InfobaseItem) -> Row:
    return Row(RowKind.BASE, item.name, item, (), _base_note(item))


def group_contents(node: TreeNode) -> tuple[list[str], int, int]:
    """Что лежит в группе: имена (до 10), число баз, число подгрупп.

    Считается по всему поддереву, а не по прямым детям (обходом в глубину,
    рекурсивно): удаление группы каскадное ([Ф] T-05.9 — единственный вопрос
    платформы «Удалить группу "имя"?» одинаков для пустой и непустой группы,
    и «Да» молча удаляет всё поддерево), и «пусто на первом уровне» ничего
    не обещает о том, что реально пропадёт. Обязательство 3 блока Б: быть
    не хуже платформы недостаточно — подтверждение обязано перечислить
    содержимое (`confirm.group_removal_question` строит текст по этим трём
    значениям).

    До `CONTENT_NAME_LIMIT` элементов — именами (порядок обхода в глубину,
    как в дереве), больше — только числами: длинный список в тексте
    диалога перестаёт быть читаемым и превращается в шум, который
    пользователь просто перестанет читать, — то же самое молчание, только
    многословное.

    Имена подгрупп несут `GROUP_CONTENT_MARK` — без пометки «Розница»
    (подгруппа) неотличима от «Демо Розница» (база внутри неё) в одном
    плоском списке, хотя при каскадном удалении это ровно та информация,
    которая нужна пользователю (круг правок 1 ревью задачи 12).
    """  # noqa: RUF002
    names: list[str] = []
    bases = 0
    groups = 0

    def walk(children: Sequence[TreeNode]) -> None:
        nonlocal bases, groups
        for child in children:
            if child.item is not None and not child.item.is_group:
                bases += 1
                names.append(child.label)
            else:
                groups += 1
                names.append(f"{child.label}{GROUP_CONTENT_MARK}")
            walk(child.children)

    walk(node.children)
    return (names if len(names) <= CONTENT_NAME_LIMIT else []), bases, groups


def _row_of(node: TreeNode) -> Row:
    children = tuple(_row_of(child) for child in node.children)
    if node.item is None:
        return Row(RowKind.IMPLICIT_GROUP, node.label, None, children, IMPLICIT_NOTE)
    if node.item.is_group:
        return Row(RowKind.GROUP, node.label, node.item, children, _base_note(node.item))
    return Row(RowKind.BASE, node.label, node.item, children, _base_note(node.item))
