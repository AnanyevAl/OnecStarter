"""Сборка модели списка баз из источников и построение дерева.

Источники: пользовательский ibases.v8i (чтение и запись) и общие списки
из ключа CommonInfoBases файлов 1cestart.cfg (только чтение). Наши данные
подмешиваются по ключу привязки.

Порядок секций между сеансами не сохраняется ([Ф] скил v8i-format: перезапись
платформы каноникализирует весь файл), поэтому сортировка идёт по OrderInList,
а исходный порядок разрешает только равенство.
"""  # noqa: RUF002

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from onecstarter.config.cestart_cfg import common_infobase_sources, parse_cestart_cfg
from onecstarter.config.v8i import V8iDocument, parse_v8i
from onecstarter.services.model import InfobaseItem, InfobaseSource, item_from_section
from onecstarter.services.order import sort_key
from onecstarter.services.paths import ROOT, group_path, normalize_folder
from onecstarter.services.user_data import BaseUserData


@dataclass(frozen=True)
class CommonListError:
    path: Path
    message: str


@dataclass(frozen=True)
class TreeNode:
    """Узел дерева раздела «Базы».

    `item is None` — неявный узел: группа существует только как путь `Folder`
    ([Ф] T-05.7 — платформа рисует такой узел, не создавая секции). У него нет
    ни секции, ни ключа привязки, операции над ним невозможны (спека 4a, §2).
    """  # noqa: RUF002

    label: str
    item: InfobaseItem | None
    children: tuple["TreeNode", ...]


def items_from_document(
    document: V8iDocument,
    source: InfobaseSource,
    entries: Mapping[str, BaseUserData],
) -> list[InfobaseItem]:
    """Превратить секции документа в список записей, отсортированный по решению 5.

    Стабильная сортировка ключом `order.sort_key`: записи с OrderInList идут
    по возрастанию значения, записи без него сохраняют порядок появления
    в файле и уходят в конец. Ключ общий с `edit._apply_reorder` (задача 15) —
    своя копия здесь разошлась бы с ним, и позиция, которую считает патч,
    перестала бы совпадать с тем, что показывает дерево.
    """  # noqa: RUF002
    items = [item_from_section(section, source) for section in document.sections]
    merged = [_merge(item, entries) for item in items]
    return sorted(merged, key=lambda item: sort_key(item.order))


def common_list_paths(cfg_paths: Iterable[Path]) -> list[Path]:
    """Собрать пути общих списков из CommonInfoBases файлов 1cestart.cfg.

    Порядок — по мере обхода переданных файлов уровней, без дублей.
    Недоступный cfg-файл молча пропускается: он не общий список, а конфиг
    уровня, и его отсутствие — не ошибка загрузки общих списков.
    """  # noqa: RUF002
    found: list[Path] = []
    for cfg in cfg_paths:
        try:
            entries = parse_cestart_cfg(cfg.read_bytes())
        except OSError:
            continue
        for value in common_infobase_sources(entries):
            path = Path(value.strip())
            if path not in found:
                found.append(path)
    return found


@dataclass(frozen=True)
class CommonListData:
    """Прочитанные, но не разобранные общие списки: снимок для Workspace.

    Байты, а не разобранные записи: наши данные (избранное, история)
    подмешиваются при разборе, и после каждого их изменения разбор
    повторяется по этому же снимку — без нового похода по сети.
    """  # noqa: RUF002

    payloads: tuple[tuple[Path, bytes], ...]
    errors: tuple[CommonListError, ...]


EMPTY_COMMON_DATA = CommonListData((), ())


def read_common_lists(cfg_paths: Iterable[Path]) -> CommonListData:
    """Прочитать общие списки с диска. Единственный эффект — чтение.

    Вызывается из фонового потока (спека T-04.6, §3.2): сетевые шары
    из CommonInfoBases не должны блокировать показ окна. Недоступный
    список попадает в ошибки, остальные читаются дальше.
    """  # noqa: RUF002
    payloads: list[tuple[Path, bytes]] = []
    errors: list[CommonListError] = []
    for path in common_list_paths(cfg_paths):
        try:
            payloads.append((path, path.read_bytes()))
        except OSError as error:
            errors.append(CommonListError(path, str(error)))
    return CommonListData(tuple(payloads), tuple(errors))


def common_items_from_data(
    data: CommonListData, entries: Mapping[str, BaseUserData]
) -> tuple[list[InfobaseItem], list[CommonListError]]:
    """Разобрать снимок общих списков. Чистая функция — ничего не читает."""
    items: list[InfobaseItem] = []
    for _path, payload in data.payloads:
        items.extend(
            items_from_document(parse_v8i(payload), InfobaseSource.COMMON, entries)
        )
    return items, list(data.errors)


def dedupe(
    user_items: Sequence[InfobaseItem], common_items: Sequence[InfobaseItem]
) -> list[InfobaseItem]:
    """Свести источники: одна база — одна запись.

    Совпадение определяется по ключу привязки: `ID` либо хеш строки соединения
    и имя. Совпавшая запись из общего списка отбрасывается, пользовательская
    помечается `in_common_list`.

    Общие списки сводятся по ключу целиком, а не пофайлово: `CommonInfoBases`
    объединяется со всех уровней `1cestart.cfg`, и одна база встречается
    в нескольких файлах. Совпадение ключа внутри одного файла тоже сводится —
    там это либо патология формата (`ID` обязан быть уникален), либо две секции
    с одинаковыми именем и строкой соединения; вторая запись не несёт
    информации, а источник доступен только для чтения, и чинить пользователю
    в нём нечего. Выигрывает встреченная раньше, то есть общий список более
    раннего уровня.

    Пользовательский список не сводится никогда: он редактируемый, и дубль
    в нём пользователь обязан увидеть, чтобы убрать.

    Записи с разными `ID` не сводятся: такая пара неотличима от двух настоящих
    разных баз, и угадывать здесь нечего.
    """  # noqa: RUF002
    shared = {item.key for item in common_items}
    merged = [
        replace(item, in_common_list=True) if item.key in shared else item
        for item in user_items
    ]
    seen = {item.key for item in user_items}
    for item in common_items:
        if item.key in seen:
            continue
        seen.add(item.key)
        merged.append(item)
    return merged


def build_tree(items: Sequence[InfobaseItem]) -> list[TreeNode]:
    """Построить дерево групп и баз по полю Folder.

    Висячий `Folder` даёт неявные узлы, как у платформы ([Ф] T-05.7).
    Вложение неявной цепочки по сегментам пути — [Р] экстраполяция: платформа
    снята на одном уровне. Неявный узел занимает позицию первой записи,
    породившей его; регистр пути сохраняется ([Ф] T-05.7 — не нормализуется).
    """  # noqa: RUF002
    known = {group_path(item.folder, item.name) for item in items if item.is_group}
    entries: dict[str, list[InfobaseItem | str]] = {ROOT: []}
    for path in known:
        entries.setdefault(path, [])
    implicit: set[str] = set()

    def ensure_chain(path: str) -> None:
        """Достроить неявные узлы для каждого отсутствующего сегмента пути."""
        parent = ROOT
        current = ""
        for segment in path.split("/"):
            current = segment if not current else f"{current}/{segment}"
            if current not in known and current not in implicit:
                implicit.add(current)
                entries.setdefault(current, [])
                entries[parent].append(current)
            parent = current

    for item in items:
        parent = normalize_folder(item.folder)
        if parent != ROOT and parent not in known:
            ensure_chain(parent)
        entries.setdefault(parent, []).append(item)

    return _children_of(ROOT, entries)


def _children_of(path: str, entries: Mapping[str, list[InfobaseItem | str]]) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    for entry in entries.get(path, []):
        if isinstance(entry, str):
            label = entry.rsplit("/", 1)[-1]
            nodes.append(TreeNode(label, None, tuple(_children_of(entry, entries))))
        elif entry.is_group:
            own = group_path(entry.folder, entry.name)
            nodes.append(TreeNode(entry.name, entry, tuple(_children_of(own, entries))))
        else:
            nodes.append(TreeNode(entry.name, entry, ()))
    return nodes


def _merge(item: InfobaseItem, entries: Mapping[str, BaseUserData]) -> InfobaseItem:
    """Подмешать наши данные к записи базы. Группам история не подмешивается (решение 4)."""
    if item.is_group:
        return item
    data = entries.get(item.key)
    if data is None:
        return item
    return replace(
        item,
        favorite=data.favorite,
        last_launched_at=data.last_launched_at,
        launch_count=data.launch_count,
    )
