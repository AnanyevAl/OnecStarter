# План 4 — операции над группами и дедупликация источников

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** дать слою `services` полный набор операций над секциями-группами `.v8i`
(создание, каскадное переименование и перемещение, удаление с явной политикой)
и свести пользовательский список баз с общими списками без дублей.

**Architecture:** арифметика путей групп выносится в отдельный модуль `services/paths.py`
и становится единственным источником правды и для построения дерева, и для каскада.
Групповые операции получают собственный тип патча `GroupPatch` в `services/groups.py`;
`edit.apply_patch` становится диспетчером по типу патча, а цикл записи в `writer.py`
не меняется вовсе — каскад считается внутри применения патча к тому документу, в который
патч сейчас пишется, поэтому переигрывание при внешнем изменении файла корректно
по построению. Дедупликация — чистая функция в `catalog`, вызываемая координатором.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `mypy --strict`, `ruff`. Ни одной новой
зависимости план не добавляет.

**Спека:** [2026-08-04-v1-groups-and-dedupe-design.md](../specs/2026-08-04-v1-groups-and-dedupe-design.md).
Задача бэклога — `T-04.4` в [tasks.md](../../tasks.md).

## Global Constraints

- **Qt только в `src/onecstarter/ui/`.** Новые модули `paths.py` и `groups.py` не импортируют
  `PySide6` ни прямо, ни транзитивно (инвариант 1 `CLAUDE.md`). Существующий тест
  `tests/unit/test_no_qt_in_core.py` проверяет это в подпроцессе и покрывает новые модули
  автоматически, потому что импортирует пакет `onecstarter.services` целиком.
- **`mypy` в режиме `strict`** для всего, кроме `onecstarter.ui.*`. Весь новый код — под strict.
- **`ruff`**, `line-length = 100`, набор правил `E, F, W, I, N, UP, B, A, C4, PTH, RUF`.
- **Процессы 1С в тестах не запускаются никогда.** Ни один тест этого плана не порождает
  процессов и не читает реестр.
- **Секреты не попадают в сообщения об ошибках** (инвариант 5). В сообщениях этого плана
  фигурируют имена и пути групп — они секретами не являются; ключи привязки в сообщения
  не идут, потому что суррогатный ключ несёт хеш строки соединения.
- **Метки достоверности обязательны.** Утверждение о поведении платформы без метки
  (**[Ф]** проверено / **[Д]** из документации / **[Р]** наше решение / **[не проверено]**)
  в код и docstring не попадает.
- **Docstring и комментарии — на русском**, как во всём слое `services`.
- **Формат `Folder` при записи — с ведущим слэшем**: `/` для корня, `/Клиенты/Розница` иначе.
  **[Ф]** так пишет мастер штатного стартера (эксперимент T-02.3, фикстура
  `tests/fixtures/anonymized.v8i`).
- **Команды проверки:**
  ```powershell
  uv run pytest        # тесты
  uv run ruff check .  # линт
  uv run mypy          # типы
  ```
- **Коммит после каждой задачи.** Сообщение на русском, тело объясняет «почему», а не «что».

## Структура файлов

| Файл | Ответственность | Действие |
| --- | --- | --- |
| `src/onecstarter/services/paths.py` | Арифметика путей секций-групп: нормализация, собственный путь, вложенность, замена префикса, запись в файл | создать |
| `src/onecstarter/services/groups.py` | `GroupPatch` и его применение: создание, каскад, удаление с политикой | создать |
| `src/onecstarter/services/model.py` | Плюс общий словарь патчей: `key_of_section`, `find_target`, `PatchResult` | изменить |
| `src/onecstarter/services/edit.py` | Диспетчер `apply_patch` по типу патча; запрет операций над базой на секции-группе; проверка целевой группы при смене `Folder` | изменить |
| `src/onecstarter/services/writer.py` | Тип параметра расширяется до `Patch`; логика цикла не меняется | изменить |
| `src/onecstarter/services/catalog.py` | Переход на `paths`; чистая функция `dedupe` | изменить |
| `src/onecstarter/services/workspace.py` | `add_group` / `update_group` / `remove_group`; вызов `dedupe` | изменить |
| `src/onecstarter/services/__init__.py` | Экспорт `GroupRemoval` наружу слоя | изменить |
| `tests/unit/test_paths.py` | Табличные тесты арифметики путей | создать |
| `tests/unit/test_groups.py` | Применение групповых патчей к документу | создать |
| `tests/unit/test_catalog.py` | Плюс тесты `dedupe` | изменить |
| `tests/unit/test_edit.py` | Плюс тесты закрытых лазеек | изменить |
| `tests/unit/test_workspace.py` | Плюс тесты операций координатора; правка теста дублей | изменить |
| `tests/unit/test_writer.py` | Плюс тест переигрывания каскада | изменить |

**Почему `PatchResult` и `find_target` переезжают в `model.py`.** `groups.py` обязан
возвращать `PatchResult` и искать цель по ключу привязки, а `edit.py` обязан вызывать
`groups.apply_group_patch` — если оба типа останутся в `edit.py`, импорт станет
циклическим. `model.py` уже владеет словарём идентичности записи (`binding_key`),
и результат применения патча — про ту же идентичность: применился ли патч и каким стал
ключ цели. `edit.py` их реэкспортирует, поэтому существующие импорты
(`from onecstarter.services.edit import PatchResult`) продолжают работать.

---

## Task 1: Модуль путей и перевод `catalog` на него

**Files:**
- Create: `src/onecstarter/services/paths.py`
- Create: `tests/unit/test_paths.py`
- Modify: `src/onecstarter/services/catalog.py:91-141`

**Interfaces:**
- Consumes: ничего (первая задача плана).
- Produces:
  - `ROOT: str` — канонический корень, значение `"/"`
  - `normalize_folder(folder: str | None) -> str`
  - `group_path(folder: str | None, name: str) -> str`
  - `is_inside(path: str, ancestor: str) -> bool`
  - `retarget(path: str, old_ancestor: str, new_ancestor: str) -> str`
  - `render_folder(path: str) -> str`

- [ ] **Step 1: Написать падающие тесты арифметики путей**

Создать `tests/unit/test_paths.py`:

```python
import pytest

from onecstarter.services.paths import (
    ROOT,
    group_path,
    is_inside,
    normalize_folder,
    render_folder,
    retarget,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ROOT),
        ("", ROOT),
        ("   ", ROOT),
        ("/", ROOT),
        ("//", ROOT),
        ("/Клиенты", "Клиенты"),
        ("Клиенты", "Клиенты"),
        ("/Клиенты/Розница/", "Клиенты/Розница"),
    ],
)
def test_normalize_folder(raw: str | None, expected: str) -> None:
    assert normalize_folder(raw) == expected


def test_group_path_of_root_group_is_its_name() -> None:
    assert group_path("/", "Клиенты") == "Клиенты"


def test_group_path_appends_name_to_parent() -> None:
    assert group_path("/Клиенты", "Розница") == "Клиенты/Розница"


@pytest.mark.parametrize(
    ("path", "ancestor", "expected"),
    [
        ("Клиенты", "Клиенты", True),
        ("Клиенты/Розница", "Клиенты", True),
        ("КлиентыVIP", "Клиенты", False),
        ("КлиентыVIP/Опт", "Клиенты", False),
        ("Клиенты", "Клиенты/Розница", False),
        ("Клиенты", ROOT, True),
    ],
)
def test_is_inside_compares_by_segments(path: str, ancestor: str, expected: bool) -> None:
    """`Клиенты` и `КлиентыVIP` совпадают как префиксы строк, но потомками
    друг другу не приходятся: наивный startswith утащил бы чужую ветку.
    """  # noqa: RUF002
    assert is_inside(path, ancestor) is expected


@pytest.mark.parametrize(
    ("path", "old", "new", "expected"),
    [
        ("Клиенты", "Клиенты", "Партнёры", "Партнёры"),
        ("Клиенты/Розница", "Клиенты", "Партнёры", "Партнёры/Розница"),
        ("Клиенты/Розница/Опт", "Клиенты", "Архив/Партнёры", "Архив/Партнёры/Розница/Опт"),
        ("КлиентыVIP", "Клиенты", "Партнёры", "КлиентыVIP"),
        ("Клиенты/Розница", "Клиенты", ROOT, "Розница"),
        ("Клиенты", "Клиенты", ROOT, ROOT),
        (ROOT, ROOT, "Архив", "Архив"),
        ("Клиенты", ROOT, "Архив", "Архив/Клиенты"),
    ],
)
def test_retarget_replaces_ancestor_prefix(
    path: str, old: str, new: str, expected: str
) -> None:
    assert retarget(path, old, new) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [(ROOT, "/"), ("Клиенты", "/Клиенты"), ("Клиенты/Розница", "/Клиенты/Розница")],
)
def test_render_folder_writes_leading_slash(path: str, expected: str) -> None:
    """[Ф] мастер стартера пишет `Folder=/` и `Folder=/<путь родителя>`."""
    assert render_folder(path) == expected
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_paths.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.paths'`

- [ ] **Step 3: Написать модуль**

Создать `src/onecstarter/services/paths.py`:

```python
"""Арифметика путей секций-групп .v8i — общий источник для дерева и каскада.

**[Ф]** T-02.3 и скил v8i-format: у секции-группы `Folder` — путь родителя,
собственный путь группы = `Folder` + `/` + имя секции.

Знание о том, кто чей потомок, существует ровно в одном экземпляре. Копия
этой арифметики в модуле правок разъехалась бы с построением дерева, и записи
осиротели бы не от ошибки в алгоритме, а от рассинхронизации двух реализаций.

Сравнение путей посегментное и с учётом регистра. Посегментность обязательна:
`Клиенты` и `КлиентыVIP` совпадают как префиксы строк, но потомками друг другу
не приходятся. Регистр — **[не проверено]**: как штатный стартер сопоставляет
`Folder` с именем группы, не измерялось, поэтому сохраняется семантика,
с которой дерево работало с плана 3.
"""  # noqa: RUF002

ROOT = "/"


def normalize_folder(folder: str | None) -> str:
    """Канонический вид пути: корень — `/`, иначе без обрамляющих слэшей.

    `/Клиенты`, `Клиенты` и `/Клиенты/` — один и тот же путь. Строка
    из одних слэшей — тоже корень: иначе она дала бы пустой путь, не равный
    ни одному узлу дерева.
    """  # noqa: RUF002
    stripped = (folder or "").strip()
    return stripped.strip("/") or ROOT


def group_path(folder: str | None, name: str) -> str:
    """Собственный путь секции-группы: путь родителя плюс имя секции."""
    parent = normalize_folder(folder)
    return name if parent == ROOT else f"{parent}/{name}"


def is_inside(path: str, ancestor: str) -> bool:
    """Лежит ли `path` внутри `ancestor` (или равен ему). Сравнение посегментное.

    Внутри корня лежит всё: у корня нет пути, который мог бы не совпасть.
    """  # noqa: RUF002
    if ancestor == ROOT:
        return True
    return path == ancestor or path.startswith(f"{ancestor}/")


def retarget(path: str, old_ancestor: str, new_ancestor: str) -> str:
    """Заменить предка в пути. Путь вне поддерева возвращается как есть.

    Путь, равный предку, становится новым предком целиком. Предок-корень
    означает, что заменяется не префикс, а всё расположение пути: у корня
    префикса нет.
    """  # noqa: RUF002
    if not is_inside(path, old_ancestor):
        return path
    if path == old_ancestor:
        return new_ancestor
    tail = path if old_ancestor == ROOT else path[len(old_ancestor) + 1 :]
    return tail if new_ancestor == ROOT else f"{new_ancestor}/{tail}"


def render_folder(path: str) -> str:
    """Записать путь в файл так, как это делает платформа: с ведущим слэшем.

    **[Ф]** мастер стартера пишет `Folder=/` для корня и `Folder=/<путь родителя>`
    для вложенных. Своя форма записи в том же файле рядом со штатной — лишний
    непроверенный риск на ровном месте.
    """  # noqa: RUF002
    return ROOT if path == ROOT else f"/{path}"
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest tests/unit/test_paths.py -q`
Expected: PASS, 27 тестов.

- [ ] **Step 5: Перевести `catalog` на общий модуль**

В `src/onecstarter/services/catalog.py` удалить приватные `_group_path` и
`_normalized_folder` (строки 127–141) и заменить их вызовы на функции из `paths`.

Импорт добавить рядом с существующими:

```python
from onecstarter.services.paths import ROOT, group_path, is_inside, normalize_folder
```

`is_inside` в этом файле пока не нужен — импортировать только используемое:

```python
from onecstarter.services.paths import ROOT, group_path, normalize_folder
```

Заменить тело `build_tree` и `_node`:

```python
def build_tree(items: Sequence[InfobaseItem]) -> list[TreeNode]:
    """Построить дерево групп и баз по полю Folder.

    Запись, чей Folder указывает на несуществующую группу, попадает в корень
    и помечается флагом orphan у узла дерева (решение 3): это свойство
    размещения в дереве, а не свойство самой записи.
    """  # noqa: RUF002
    group_paths = {group_path(item.folder, item.name) for item in items if item.is_group}
    children: dict[str, list[InfobaseItem]] = {path: [] for path in group_paths}
    roots: list[tuple[InfobaseItem, bool]] = []
    for item in items:
        parent = normalize_folder(item.folder)
        if parent == ROOT:
            roots.append((item, False))
        elif parent in children:
            children[parent].append(item)
        else:
            # Folder указывает на несуществующую группу: показываем в корне
            # и помечаем. Невидимая база хуже базы не на своём месте.
            roots.append((item, True))
    return [_node(item, children, orphan) for item, orphan in roots]


def _node(
    item: InfobaseItem,
    children: Mapping[str, list[InfobaseItem]],
    orphan: bool,
) -> TreeNode:
    if not item.is_group:
        return TreeNode(item, (), orphan)
    nested = tuple(
        _node(child, children, False)
        for child in children.get(group_path(item.folder, item.name), [])
    )
    return TreeNode(item, nested, orphan)
```

- [ ] **Step 6: Убедиться, что рефактор ничего не сломал**

Run: `uv run pytest -q`
Expected: PASS, все существующие тесты плюс новые. Поведение `build_tree` не менялось,
поэтому тесты `test_catalog.py` обязаны пройти без правок.

- [ ] **Step 7: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 8: Коммит**

```bash
git add src/onecstarter/services/paths.py src/onecstarter/services/catalog.py tests/unit/test_paths.py
git commit -m "$(cat <<'EOF'
feat: арифметика путей групп единым модулем

Знание о том, кто чей потомок, было приватным в catalog, а каскадному
обновлению Folder нужно то же самое. Копия разъехалась бы с оригиналом,
и записи осиротели бы от рассинхронизации двух реализаций, а не от ошибки
в алгоритме.

Сравнение посегментное: Клиенты и КлиентыVIP совпадают как префиксы строк,
но потомками друг другу не приходятся.
EOF
)"
```

---

## Task 2: Каркас групповых патчей и создание группы

**Files:**
- Create: `src/onecstarter/services/groups.py`
- Create: `tests/unit/test_groups.py`
- Modify: `src/onecstarter/services/model.py` (добавить `PatchResult`, `find_target`, `key_of_section`)
- Modify: `src/onecstarter/services/edit.py` (реэкспорт, диспетчер, тип `Patch`)
- Modify: `src/onecstarter/services/writer.py:29-31` (тип параметра)

**Interfaces:**
- Consumes: `paths.ROOT`, `paths.group_path`, `paths.normalize_folder`, `paths.render_folder` (Task 1).
- Produces:
  - `model.PatchResult` — `@dataclass(frozen=True)` с полями `applied: bool`, `key: str | None`
  - `model.find_target(document: V8iDocument, key: str) -> V8iSection | None`
  - `model.key_of_section(section: V8iSection) -> str`
  - `groups.GroupPatchKind` — `CREATE | RETARGET | REMOVE`
  - `groups.GroupRemoval` — `PROMOTE | RECURSIVE`
  - `groups.GroupPatch(kind, target_key=None, name=None, new_name=None, new_folder=None, removal=None)`
  - `groups.apply_group_patch(document: V8iDocument, patch: GroupPatch, new_id: str) -> PatchResult`
  - `groups.group_paths(document: V8iDocument, skip: V8iSection | None = None) -> set[str]`
  - `edit.Patch` — псевдоним типа `SectionPatch | GroupPatch`

- [ ] **Step 1: Написать падающие тесты создания группы**

Создать `tests/unit/test_groups.py`:

```python
import pytest

from onecstarter.config.v8i import parse_v8i, serialize_v8i
from onecstarter.services.errors import InvalidRequestError
from onecstarter.services.groups import (
    GroupPatch,
    GroupPatchKind,
    apply_group_patch,
)

NEW_ID = "99999999-9999-9999-9999-999999999999"

# Дерево с вложенностью, базой в подгруппе, записью без ID и соседом,
# чьё имя начинается с имени группы: Клиенты / КлиентыVIP.
NESTED = (
    "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
    "[Розница]\r\nID=sub\r\nOrderInList=-1\r\nFolder=/Клиенты\r\n"
    "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\nFolder=/Клиенты\r\n"
    "[Ручная]\r\nConnect=File=\"C:\\Bases\\Manual\";\r\nFolder=/Клиенты\r\n"
    "[Опт]\r\nConnect=File=\"C:\\Bases\\Opt\";\r\nID=opt\r\nFolder=/Клиенты/Розница\r\n"
    "[КлиентыVIP]\r\nID=vip\r\nOrderInList=-1\r\nFolder=/\r\n"
    "[Крупный]\r\nConnect=File=\"C:\\Bases\\Big\";\r\nID=big\r\nFolder=/КлиентыVIP\r\n"
).encode()


def _by_id(data: bytes) -> dict[str | None, str | None]:
    """Снять карту ID → Folder: каскад проверяется именно по ней."""  # noqa: RUF002
    return {section.id: section.folder for section in parse_v8i(data).sections}


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
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_groups.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.groups'`

- [ ] **Step 3: Перенести общий словарь патчей в `model.py`**

В `src/onecstarter/services/model.py` добавить импорт документа и три сущности.

Заменить строку импорта:

```python
from onecstarter.config.v8i import KeyValueLine, V8iDocument, V8iSection
```

Добавить в конец файла:

```python
@dataclass(frozen=True)
class PatchResult:
    """Что патч сделал на самом деле.

    `applied` — цель найдена и патч применён. `key` — фактический ключ цели
    после применения; `None`, если цели в документе больше нет (удалённая
    секция или ненайденная цель удаления). Без этого вызывающий не отличит
    «удалили» от «не нашли» и не узнает, что ключ записи сменился, — а он
    меняется всякий раз, когда записи дописывается `ID`.

    Живёт здесь, а не в модуле правок: результат применения патча нужен
    и правкам записей, и операциям над группами, а модуль групп импортировать
    модуль правок не может — импорт стал бы циклическим.
    """  # noqa: RUF002

    applied: bool
    key: str | None


def key_of_section(section: V8iSection) -> str:
    """Ключ привязки секции документа."""
    return binding_key(section.id, section.connect, section.name)


def find_target(document: V8iDocument, key: str) -> V8iSection | None:
    """Найти секцию по ключу привязки. Никогда не по позиции: порядок секций
    между сеансами не сохраняется ([Ф] каноникализация платформы).
    """  # noqa: RUF002
    for section in document.sections:
        if key_of_section(section) == key:
            return section
    return None


def validate_section_name(name: str) -> None:
    """Отвергнуть имя секции, которое нельзя записать в файл без потерь.

    Заголовок секции пишется как `[<имя>]` одной строкой и не экранируется:
    перевод строки внутри имени превратил бы одну секцию в несколько,
    подделав записи в файле, который мы делим со штатным стартером.
    """  # noqa: RUF002
    if not name.strip():
        raise InvalidRequestError("Имя секции не может быть пустым")
    if "\r" in name or "\n" in name:
        raise InvalidRequestError("Имя секции не может содержать перевод строки")
```

`InvalidRequestError` импортируется в `model.py` из `onecstarter.services.errors` —
этот модуль ни от кого в слое не зависит, цикла не будет.

Из `src/onecstarter/services/edit.py` удалить определения `PatchResult`, `find_target`
и `_key_of`, заменив их импортом и реэкспортом:

```python
from onecstarter.services.model import PatchResult, binding_key, find_target, key_of_section
```

Все обращения `_key_of(section)` в `edit.py` заменить на `key_of_section(section)`.
`binding_key` в `edit.py` после этого не используется — убрать из импорта.

В `__all__` модуля `edit.py` состав не меняется: `PatchResult` и `find_target` остаются
в списке, теперь как реэкспорт.

- [ ] **Step 4: Убедиться, что перенос ничего не сломал**

Run: `uv run pytest -q --ignore=tests/unit/test_groups.py`
Expected: PASS. Это чистый перенос: ни одна сигнатура не изменилась, тесты
`test_edit.py` и `test_workspace.py` импортируют те же имена из тех же модулей.

`test_groups.py` из шага 1 исключается намеренно: модуль `groups.py` появится только
в шаге 5, а до тех пор этот файл падает на сборе и прерывает прогон всей сюиты,
а не одного файла. Проверить надо именно то, что перенос не тронул существующее.

- [ ] **Step 5: Написать модуль групп с операцией создания**

Создать `src/onecstarter/services/groups.py`:

```python
"""Операции над секциями-группами ibases.v8i.

Группа — секция без `Connect` (**[Ф]** скил v8i-format). Её имя входит
в `Folder` каждой вложенной записи, поэтому смена имени или родителя обязана
переписать `Folder` всего поддерева: иначе потомки продолжат ссылаться
на старый путь и высыпятся в корень как orphan.

Каскад считается по тому документу, в который патч применяется сейчас.
Список целей, собранный до чтения свежего файла, устарел бы: writer
переигрывает патч на свежем состоянии, и база, добавленную в группу штатным
стартером между попытками, такой список не переписал бы.
"""  # noqa: RUF002

from dataclasses import dataclass
from enum import Enum

from onecstarter.config.v8i import V8iDocument, V8iSection
from onecstarter.services.errors import InvalidRequestError
from onecstarter.services.model import PatchResult, key_of_section
from onecstarter.services.paths import ROOT, group_path, normalize_folder, render_folder

__all__ = [
    "GroupPatch",
    "GroupPatchKind",
    "GroupRemoval",
    "apply_group_patch",
    "group_paths",
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
    raise InvalidRequestError("Операция над группой не поддерживается")


def _create(document: V8iDocument, patch: GroupPatch, new_id: str) -> PatchResult:
    name = (patch.name or "").strip()
    _validate_name(name)
    parent = normalize_folder(patch.new_folder)
    _require_group_exists(document, parent)
    _require_path_free(document, group_path(parent, name), skip=None)
    section = document.append_section(name)
    # Порядок ключей — как у мастера стартера [Ф], без OrderInTree.
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


def _require_group_exists(document: V8iDocument, parent: str) -> None:
    if parent == ROOT:
        return
    if parent not in group_paths(document):
        raise InvalidRequestError(f"Группы «{parent}» в списке нет")


def _require_path_free(
    document: V8iDocument, path: str, skip: V8iSection | None
) -> None:
    if path in group_paths(document, skip):
        raise InvalidRequestError(f"Группа «{path}» уже существует")
```

- [ ] **Step 6: Сделать `apply_patch` диспетчером**

В `src/onecstarter/services/edit.py` добавить импорт и псевдоним типа:

```python
from onecstarter.services.groups import GroupPatch, apply_group_patch

Patch = SectionPatch | GroupPatch
```

Псевдоним объявить после определения `SectionPatch`. Добавить `"Patch"` в `__all__`.

Заменить начало `apply_patch`:

```python
def apply_patch(document: V8iDocument, patch: Patch, new_id: str) -> PatchResult:
    if isinstance(patch, GroupPatch):
        return apply_group_patch(document, patch, new_id)
    if patch.kind is PatchKind.ADD:
        return _apply_add(document, patch, new_id)
    ...
```

Остальное тело `apply_patch` не трогать.

В `src/onecstarter/services/writer.py` расширить тип параметра и импорт:

```python
from onecstarter.services.edit import Patch, PatchResult, apply_patch


def write_patch(
    path: Path, patch: Patch, new_id: str, attempts: int = 3
) -> tuple[bytes, PatchResult]:
```

Такую же замену сделать в сигнатуре приватной `_create` того же модуля:

```python
def _create(
    path: Path, patch: Patch, new_id: str
) -> tuple[bytes, PatchResult] | None:
```

`SectionPatch` в импорте `writer.py` больше не нужен — убрать.

- [ ] **Step 7: Убедиться, что тесты проходят**

Run: `uv run pytest tests/unit/test_groups.py -q`
Expected: PASS, 7 тестов.

Run: `uv run pytest -q`
Expected: PASS, вся сюита.

- [ ] **Step 8: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 9: Коммит**

```bash
git add src/onecstarter/services/groups.py src/onecstarter/services/model.py \
        src/onecstarter/services/edit.py src/onecstarter/services/writer.py \
        tests/unit/test_groups.py
git commit -m "$(cat <<'EOF'
feat: групповые патчи отдельным типом и создание группы

SectionPatch не расширяем: поля вроде политики удаления осмысленны только
для одного вида патча, и в общем типе стал бы представим ADD с политикой.
apply_patch становится диспетчером по типу, цикл записи не меняется.

PatchResult и find_target переехали в model: модуль групп обязан их
использовать, а импортировать edit не может — импорт стал бы циклическим.

Создать группу до сих пор было нечем: add_infobase всегда пишет Connect,
то есть всегда создаёт базу.
EOF
)"
```

---

## Task 3: Каскадное обновление пути группы

**Files:**
- Modify: `src/onecstarter/services/groups.py`
- Modify: `tests/unit/test_groups.py`

**Interfaces:**
- Consumes: `groups.GroupPatch`, `groups.group_paths`, `paths.is_inside`, `paths.retarget` (Tasks 1–2).
- Produces: ветка `GroupPatchKind.RETARGET` в `apply_group_patch`. Возвращает
  `PatchResult(applied=True, key=<ключ группы после применения>)`.

- [ ] **Step 1: Написать падающие тесты каскада**

Дописать в `tests/unit/test_groups.py`. Импорты дополнить:

```python
from onecstarter.services.errors import InvalidRequestError, TargetGoneError
from onecstarter.services.model import binding_key, find_target
```

Тесты:

```python
def test_rename_group_rewrites_folder_of_whole_subtree() -> None:
    """Имя группы входит в Folder каждой вложенной записи ([Ф] T-02.3):
    переименовав только заголовок, мы оторвали бы от группы всё её содержимое.
    """  # noqa: RUF002
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
    """`КлиентыVIP` начинается с `Клиенты`, но потомком ей не приходится."""
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["vip"] == "/"
    assert folders["big"] == "/КлиентыVIP"


def test_move_group_rewrites_subtree() -> None:
    document = parse_v8i(NESTED)
    apply_group_patch(
        document,
        GroupPatch(
            GroupPatchKind.RETARGET, target_key="id:sub", new_folder="/КлиентыVIP"
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["sub"] == "/КлиентыVIP"
    assert folders["opt"] == "/КлиентыVIP/Розница"


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
            new_folder="/КлиентыVIP",
        ),
        NEW_ID,
    )
    folders = _by_id(serialize_v8i(document))
    assert folders["sub"] == "/КлиентыVIP"
    assert folders["opt"] == "/КлиентыVIP/Опт и розница"


def test_binding_keys_of_children_survive_the_cascade() -> None:
    """Ключ привязки строится из ID либо из хеша Connect и имени; Folder
    в него не входит. Значит избранное и история потомков остаются на местах.
    """  # noqa: RUF002
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
    assert _by_id(serialize_v8i(document))["sub"] == "/Клиенты"


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


def test_retarget_of_missing_target_raises() -> None:
    document = parse_v8i(NESTED)
    with pytest.raises(TargetGoneError):
        apply_group_patch(
            document,
            GroupPatch(GroupPatchKind.RETARGET, target_key="id:нет", new_name="Другое"),
            NEW_ID,
        )
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_groups.py -q`
Expected: FAIL — `InvalidRequestError: Операция над группой не поддерживается`
на всех новых тестах, кроме тех, что ждут `InvalidRequestError`. Тесты
`test_retarget_of_missing_target_raises`, `test_move_into_own_descendant_is_rejected`
и подобные пройдут по неверной причине — их корректность подтверждает Step 4.

- [ ] **Step 3: Реализовать каскад**

В `src/onecstarter/services/groups.py` дополнить импорты — `TargetGoneError` и `find_target`
до этой задачи не использовались, поэтому и не импортировались:

```python
from onecstarter.services.errors import InvalidRequestError, TargetGoneError
from onecstarter.services.model import PatchResult, find_target, key_of_section
from onecstarter.services.paths import (
    ROOT,
    group_path,
    is_inside,
    normalize_folder,
    render_folder,
    retarget,
)
```

Заменить диспетчер:

```python
def apply_group_patch(
    document: V8iDocument, patch: GroupPatch, new_id: str
) -> PatchResult:
    if patch.kind is GroupPatchKind.CREATE:
        return _create(document, patch, new_id)
    section = _target_group(document, patch)
    if patch.kind is GroupPatchKind.RETARGET:
        return _retarget_group(document, section, patch)
    raise InvalidRequestError("Операция над группой не поддерживается")


def _target_group(document: V8iDocument, patch: GroupPatch) -> V8iSection:
    if patch.target_key is None:
        raise InvalidRequestError("Для операции над группой нужен target_key")
    section = find_target(document, patch.target_key)
    if section is None:
        # Ключ может быть суррогатом с хешем строки соединения — в сообщение
        # он не идёт (инвариант 5).
        raise TargetGoneError("Целевая группа удалена извне")
    if not section.is_group:
        # Вид секции определяется по свежему документу, а не по модели
        # координатора: [Ф] T-02.9 — база, у которой платформа перестала
        # распознавать Connect, деградирует до группы.
        raise InvalidRequestError(f"«{section.name}» — не группа, а запись базы")
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
    _require_group_exists(document, parent)
    _require_path_free(document, new, skip=section)
    if name != section.name:
        section.header.text = f"[{name}]"
    section.set("Folder", render_folder(parent))
    # Один проход по всем секциям: прямые дети, вложенные группы и их
    # содержимое несут в Folder полный путь, начинающийся с old, поэтому
    # посегментная замена префикса чинит поддерево целиком без рекурсии.
    for other in document.sections:
        if other is section:
            continue
        folder = normalize_folder(other.folder)
        if is_inside(folder, old):
            other.set("Folder", render_folder(retarget(folder, old, new)))
    return PatchResult(applied=True, key=key_of_section(section))
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest tests/unit/test_groups.py -q`
Expected: PASS, 22 теста (8 от задачи 2, включая тест на перевод строки в имени,
плюс 14 новых).

- [ ] **Step 5: Убедиться, что остальная сюита цела**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 7: Коммит**

```bash
git add src/onecstarter/services/groups.py tests/unit/test_groups.py
git commit -m "$(cat <<'EOF'
feat: каскадное обновление пути группы

Переименование и перемещение — одна операция: меняется собственный путь
группы, потомкам переписывается префикс Folder. Порознь их решать
бессмысленно, а запрет одного лишь переименования дыру не закрывал —
смена Folder у секции-группы проходила без единой проверки.

Замена префикса посегментная и одним проходом по всем секциям: вложенные
группы и их содержимое несут полный путь, поэтому рекурсия не нужна,
а сосед с именем-префиксом остаётся нетронутым.
EOF
)"
```

---

## Task 4: Удаление группы с явной политикой

**Files:**
- Modify: `src/onecstarter/services/groups.py`
- Modify: `tests/unit/test_groups.py`

**Interfaces:**
- Consumes: всё из Tasks 1–3.
- Produces: ветка `GroupPatchKind.REMOVE` в `apply_group_patch`.
  `PatchResult(applied=True, key=None)` при удалении;
  `PatchResult(applied=False, key=None)`, если цели нет — удаление идемпотентно.

- [ ] **Step 1: Написать падающие тесты удаления**

Дописать в `tests/unit/test_groups.py`. Импорт дополнить: `GroupRemoval`.

```python
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
    assert [section.name for section in document.sections] == ["КлиентыVIP", "Крупный"]


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
    """Политика обязательна: удалить дерево баз по невнимательности нельзя."""  # noqa: RUF002
    document = parse_v8i(NESTED)
    with pytest.raises(InvalidRequestError):
        apply_group_patch(
            document, GroupPatch(GroupPatchKind.REMOVE, target_key="id:grp"), NEW_ID
        )
    assert len(document.sections) == 7


def test_promote_rejects_name_collision_at_the_parent() -> None:
    """Подъём, создающий два одинаковых пути, — тот же дефект, что запрещает
    RETARGET: build_tree отдал бы обеим группам один список потомков.
    """  # noqa: RUF002
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
    assert len(document.sections) == 3


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
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_groups.py -q`
Expected: FAIL — `InvalidRequestError: Операция над группой не поддерживается`.

- [ ] **Step 3: Реализовать удаление**

В `src/onecstarter/services/groups.py` заменить хвост диспетчера и дописать функции.
Удаление обрабатывается до `_target_group`, потому что оно идемпотентно и на исчезнувшей
цели обязано вернуть результат, а не подняться исключением:

```python
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
            "поднять к родителю или удалить вместе с группой"
        )
    if patch.target_key is None:
        raise InvalidRequestError("Для операции над группой нужен target_key")
    if find_target(document, patch.target_key) is None:
        # Идемпотентно, как удаление записи базы: пользователь хотел,
        # чтобы группы не было, — её нет. Но applied=False сообщает,
        # что цель не нашлась: её ключ мог смениться, а не исчезнуть.
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
    """Отказать, если подъём содержимого создаст две группы с одним путём."""
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


def _paths_outside(
    document: V8iDocument, section: V8iSection, old: str
) -> set[str]:
    """Пути групп, которые останутся на месте после удаления `section`."""
    result: set[str] = set()
    for other in document.sections:
        if not other.is_group or other is section:
            continue
        path = group_path(other.folder, other.name)
        if not is_inside(path, old):
            result.add(path)
    return result
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest tests/unit/test_groups.py -q`
Expected: PASS, 30 тестов.

- [ ] **Step 5: Убедиться, что остальная сюита цела**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 7: Коммит**

```bash
git add src/onecstarter/services/groups.py tests/unit/test_groups.py
git commit -m "$(cat <<'EOF'
feat: удаление группы с явной политикой для содержимого

remove_infobase на секции-группе оставлял потомков сиротами: их Folder
указывал на исчезнувший путь, и дерево молча рассыпалось в корень.

Политика обязательна, значения по умолчанию нет: удалить дерево баз
по невнимательности вызывающего нельзя. Подъём проверяет коллизию имён —
иначе операция своими руками создала бы задвоенный путь, который
переименование запрещает.
EOF
)"
```

---

## Task 5: Закрытие лазеек в операциях над записью базы

**Files:**
- Modify: `src/onecstarter/services/edit.py`
- Modify: `tests/unit/test_edit.py`

**Interfaces:**
- Consumes: `groups.group_paths`, `paths.ROOT`, `paths.normalize_folder` (Tasks 1–2).
- Produces: `SectionPatch` с видами `UPDATE` и `REMOVE` отвергается на секции-группе;
  смена `Folder` у записи базы требует существующей целевой группы.

- [ ] **Step 1: Написать падающие тесты**

В `tests/unit/test_edit.py` заменить `test_group_rename_is_rejected` (строки 131–144)
на набор тестов и дополнить импорты (`PatchResult` уже не нужен, добавить ничего
не требуется):

```python
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
            SectionPatch(
                PatchKind.UPDATE, target_key="id:grp", changes={"Folder": "/Архив"}
            ),
            NEW_ID,
        )
    assert document.sections[0].name == "Клиенты"
    assert document.sections[0].folder == "/"
    assert document.sections[1].folder == "/Клиенты"


def test_group_remove_is_rejected() -> None:
    """Удаление секции-группы оставляло потомков сиротами."""
    document = parse_v8i(GROUP_AND_CHILD)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document, SectionPatch(PatchKind.REMOVE, target_key="id:grp"), NEW_ID
        )
    assert len(document.sections) == 2


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


def test_move_of_base_to_root_is_allowed() -> None:
    document = parse_v8i(GROUP_AND_CHILD)
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "/"}),
        NEW_ID,
    )
    assert document.sections[1].folder == "/"


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
```

Существующий `test_move_to_folder_is_an_update` (строки 121–129) переводит базу
в `/Архив`, которого в `TWO_SECTIONS` нет. Заменить его целевую группу на существующую,
дописав группу в документ:

```python
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
```

Существующий `test_add_writes_minimal_key_set` (строки 39–53) добавляет запись
в `/Клиенты` в пустой документ, где такой группы нет, — новая проверка его отвергнет.
Дописать группу в исходный документ и в ожидаемый результат:

```python
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
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_edit.py -q`
Expected: FAIL. `test_group_update_is_rejected_entirely` падает на второй половине
(смена `Folder` проходит без ошибки), `test_group_remove_is_rejected`,
`test_move_of_base_requires_existing_group` и `test_add_of_base_requires_existing_group`
падают с `Failed: DID NOT RAISE`. `test_add_writes_minimal_key_set` падает на сравнении
байтов — в ожидаемый результат добавилась секция группы.

- [ ] **Step 3: Реализовать проверки**

В `src/onecstarter/services/edit.py` дополнить импорты:

```python
from onecstarter.services.groups import GroupPatch, apply_group_patch, group_paths
from onecstarter.services.paths import ROOT, normalize_folder
```

Заменить тело `apply_patch` после диспетчера:

```python
def apply_patch(document: V8iDocument, patch: Patch, new_id: str) -> PatchResult:
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
```

Добавить подсказки и проверки:

```python
GROUP_UPDATE_HINT = (
    "используйте изменение группы — оно переписывает Folder вложенных записей"
)
GROUP_REMOVE_HINT = (
    "используйте удаление группы с явной политикой для её содержимого"
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
    """  # noqa: RUF002
    for key, value in changes.items():
        if key.casefold() != "folder" or value is None:
            continue
        parent = normalize_folder(value)
        if parent != ROOT and parent not in group_paths(document):
            raise InvalidRequestError(f"Группы «{parent}» в списке нет")
```

В `_apply_add` добавить проверку первой строкой после проверки имени:

```python
def _apply_add(document: V8iDocument, patch: SectionPatch, new_id: str) -> PatchResult:
    # Значение сохраняется в переменную, а не подставляется дважды: mypy --strict
    # не связывает аргумент вызова с `patch.name`, и после проверки тип остался бы
    # `str | None` для `append_section`.
    name = patch.name or ""
    validate_section_name(name)
    _require_target_folder_exists(document, patch.changes)
    section = document.append_section(patch.name)
    ...
```

`_apply_update` получает документ и вызывает ту же проверку до изменения ключей:

```python
def _apply_update(
    document: V8iDocument, section: V8iSection, patch: SectionPatch, new_id: str
) -> None:
    _require_target_folder_exists(document, patch.changes)
    if patch.new_name:
        _rename(section, patch.new_name)
    ...
```

Из `_rename` убрать ветку `if section.is_group` целиком: она недостижима, потому что
`_reject_group` отвергает группу раньше. Взамен добавить проверку имени — заголовок
здесь пишется тем же неэкранированным `f"[{...}]"`, что и при добавлении, а значит имя
с переводом строки подделает секции в файле пользователя. Задача 2 закрыла этот вход
у `_apply_add` и `groups._create`, `_rename` остался последним:

```python
def _rename(section: V8iSection, new_name: str) -> None:
    validate_section_name(new_name)
    section.header.text = f"[{new_name}]"
```

Тест на этот вход:

```python
def test_rename_rejects_newline_in_name() -> None:
    """Последний неэкранированный вход в заголовок секции: правка имени."""  # noqa: RUF002
    document = parse_v8i(TWO_SECTIONS)
    with pytest.raises(InvalidRequestError):
        apply_patch(
            document,
            SectionPatch(PatchKind.UPDATE, target_key="id:abc", new_name="Демо\r\n[Чужая]"),
            NEW_ID,
        )
    assert document.sections[0].name == "Демо"
    assert len(document.sections) == 2
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `uv run pytest tests/unit/test_edit.py -q`
Expected: PASS.

- [ ] **Step 5: Убедиться, что остальная сюита цела**

Run: `uv run pytest -q`
Expected: PASS. Обратить внимание на `tests/unit/test_workspace.py` — фикстура
`anonymized.v8i` содержит запись `Потерянная` с `Folder=/Нет такой группы`, но ни один
тест её не переносит и не правит, поэтому новая проверка их не задевает.

- [ ] **Step 6: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 7: Коммит**

```bash
git add src/onecstarter/services/edit.py tests/unit/test_edit.py
git commit -m "$(cat <<'EOF'
fix: операции над записью базы больше не портят дерево групп

Запрет переименования группы закрывал один вход из трёх. Смена Folder
у секции-группы проходила без проверок и разрушала дерево тем же способом,
а удаление секции-группы оставляло потомков сиротами.

Заодно перенос записи в несуществующую группу: раньше в Folder попадал
любой путь, и запись молча становилась сиротой.
EOF
)"
```

### Добавлено в ходе исполнения: защита формата в `config` (согласовано 04.08.2026)

Ревью задачи 5 показало, что защита имени секции в `services` закрывает не весь класс.
Имя ключа и **значение** в `V8iSection.set` пишутся тем же неэкранированным способом.
Проверено на реальном коде: значение `File="C:\A";\r\n[Injected]\r\nConnect=...` после
записи и повторного разбора даёт в документе две секции вместо одной. Записанное перестаёт
читаться как записанное — нарушение инварианта 3 `CLAUDE.md`. Вход достижим: `add_infobase`
передаёт строку соединения от вызывающего прямо в `set`, а вводит её пользователь.

Заказчик выбрал `config` как место защиты — единственное узкое место записи вместо
очередной проверки у точки вызова. Две предыдущие попытки закрыть этот класс дыр
в `services` каждый раз оставляли ещё один открытый вход.

- `config/v8i.py` получает свой тип исключения `LineBreakRejectedError(ValueError)` —
  по образцу `ExternalChangeError` в `config/atomic.py`: слой держит исключения у себя.
- Проверка стоит первыми строками `V8iSection.set` (ключ и значение)
  и `V8iDocument.append_section` (имя) — **до** `_close_last_ending`, иначе отказ оставит
  дописанный перевод строки в хвосте предыдущей секции.
- `writer.write_patch` переводит `LineBreakRejectedError` в `InvalidRequestError`: наружу
  слой отдаёт одну иерархию от `ServicesError` и голых `ValueError` не выпускает.
- В `serialize_v8i` проверки нет: там она сработала бы после мутации и не назвала бы,
  какой ключ виноват.
- `writer` сводит **оба** вызова `apply_patch` — основной цикл и путь создания
  отсутствующего файла — через одну приватную обёртку. Обёртка вокруг одного из них
  оставила бы ровно тот четвёртый вход, ради которого защита и переезжала в `config`.

Защита в итоге двухуровневая, и это стоит назвать прямо. Переименование пишет заголовок
прямым присваиванием `section.header.text` — в `edit._rename` и в `groups._retarget_group`, —
минуя `V8iSection.set` и `append_section`. Эти два пути закрыты в `services` функцией
`model.validate_section_name`, которая проверяет то же самое и поднимает уже правильный
для слоя тип. Дублирование правила «без перевода строки» здесь осознанное: сведение
его в один экземпляр поменяло бы тип исключения на уровне `apply_patch`, а он зафиксирован
тестами и означает для вызывающего разное. Правило тривиально и разъехаться не может —
в отличие от арифметики путей, ради которой в задаче 1 заводился отдельный модуль.

---

## Task 6: Операции групп в координаторе

**Files:**
- Modify: `src/onecstarter/services/workspace.py`
- Modify: `src/onecstarter/services/__init__.py`
- Modify: `tests/unit/test_workspace.py`
- Modify: `tests/unit/test_writer.py`

**Interfaces:**
- Consumes: `groups.GroupPatch`, `groups.GroupPatchKind`, `groups.GroupRemoval` (Tasks 2–4).
- Produces:
  - `Workspace.add_group(name: str, folder: str | None = None) -> str`
  - `Workspace.update_group(key: str, *, new_name: str | None = None, new_folder: str | None = None) -> str`
  - `Workspace.remove_group(key: str, removal: GroupRemoval) -> bool`
  - `onecstarter.services.GroupRemoval` — реэкспорт для слоя представления

- [ ] **Step 1: Написать падающий тест переигрывания каскада**

Дописать в `tests/unit/test_writer.py`. Импорты дополнить:

```python
from onecstarter.services.groups import GroupPatch, GroupPatchKind
```

```python
def test_group_cascade_is_computed_on_the_fresh_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Каскад обязан считаться по тому документу, в который мы пишем сейчас.
    Список целей, собранный до чтения свежего файла, пропустил бы базу,
    которую штатный стартер добавил в группу между нашими попытками, —
    и она осталась бы с Folder на исчезнувший путь.
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    group = "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
    path.write_bytes(group.encode())
    original = atomic.atomic_write_if_unchanged
    state = {"first": True}

    def meddling(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        if state["first"]:
            state["first"] = False
            target.write_bytes(
                (
                    group + '[Новая]\r\nConnect=File="C:\\Bases\\New";\r\n'
                    "ID=new\r\nFolder=/Клиенты\r\n"
                ).encode()
            )
        original(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", meddling)
    write_patch(
        path,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    folders = {
        section.id: section.folder for section in parse_v8i(path.read_bytes()).sections
    }
    assert folders["grp"] == "/"
    assert folders["new"] == "/Партнёры"
```

- [ ] **Step 2: Убедиться, что тест проходит**

Run: `uv run pytest tests/unit/test_writer.py::test_group_cascade_is_computed_on_the_fresh_document -q`
Expected: PASS — механика уже готова (Tasks 2–3), тест её фиксирует. Если тест падает,
значит каскад где-то считается вне применения патча, и это нужно чинить, а не обходить.

- [ ] **Step 3: Написать падающие тесты координатора**

Дописать в `tests/unit/test_workspace.py`. Импорты дополнить:

```python
from onecstarter.services.groups import GroupRemoval
```

```python
def test_add_group_creates_a_node_in_the_tree(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = workspace.add_group("Архив")
    node = next(node for node in workspace.tree() if node.item.key == key)
    assert node.item.is_group
    assert node.children == ()


def test_add_group_inside_existing_group(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = workspace.add_group("Архив", folder="/Клиенты")
    clients = next(node for node in workspace.tree() if node.item.name == "Клиенты")
    assert any(child.item.key == key for child in clients.children)


def test_update_group_moves_the_whole_subtree(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.update_group("id:11111111-1111-1111-1111-111111111111", new_name="Партнёры")
    partners = next(node for node in workspace.tree() if node.item.name == "Партнёры")
    names = {child.item.name for child in partners.children}
    assert names == {"Демо Бухгалтерия", "Розница"}
    retail = next(child for child in partners.children if child.item.name == "Розница")
    assert {child.item.name for child in retail.children} == {"Демо Розница"}


def test_update_group_keeps_user_data_of_children(tmp_path: Path) -> None:
    """Ключ привязки потомка не зависит от Folder, поэтому избранное
    и история переживают каскад.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    child = "id:55555555-5555-5555-5555-555555555555"
    workspace.set_favorite(child, True)
    workspace.update_group("id:11111111-1111-1111-1111-111111111111", new_name="Партнёры")
    assert next(item for item in workspace.items() if item.key == child).favorite


def test_remove_group_promotes_children(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.PROMOTE
    )
    names = {node.item.name for node in workspace.tree()}
    assert "Клиенты" not in names
    assert {"Демо Бухгалтерия", "Розница"} <= names


def test_remove_group_recursive_drops_the_subtree(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.RECURSIVE
    )
    names = {item.name for item in workspace.items()}
    assert names.isdisjoint({"Клиенты", "Розница", "Демо Бухгалтерия", "Демо Розница"})


def test_remove_group_reports_missing_target(tmp_path: Path) -> None:
    assert not _workspace(tmp_path).remove_group("id:нет такого", GroupRemoval.PROMOTE)


def test_group_operations_refuse_common_list(tmp_path: Path) -> None:
    shared = tmp_path / "shared.v8i"
    shared.write_bytes("[Общая группа]\r\nID=aaaa\r\nOrderInList=-1\r\nFolder=/\r\n".encode())
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    with pytest.raises(ReadOnlySourceError):
        workspace.update_group("id:aaaa", new_name="Другое")
    with pytest.raises(ReadOnlySourceError):
        workspace.remove_group("id:aaaa", GroupRemoval.PROMOTE)


def test_group_removal_is_exported_from_the_layer() -> None:
    """UI обязан уметь назвать политику, не импортируя внутренний модуль."""
    from onecstarter import services

    assert services.GroupRemoval is GroupRemoval
```

- [ ] **Step 4: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_workspace.py -q`
Expected: FAIL — `AttributeError: 'Workspace' object has no attribute 'add_group'`.

- [ ] **Step 5: Реализовать методы координатора**

В `src/onecstarter/services/workspace.py` дополнить импорты:

```python
from onecstarter.services.groups import GroupPatch, GroupPatchKind, GroupRemoval
```

Добавить методы после `remove_infobase`:

```python
    def add_group(self, name: str, folder: str | None = None) -> str:
        """Создать секцию-группу и вернуть её ключ привязки."""
        result = self._write(
            GroupPatch(GroupPatchKind.CREATE, name=name, new_folder=folder)
        )
        if result.key is None:
            # Недостижимо: создание всегда даёт секцию и её ключ.
            raise ServicesError("Группа создана, но её ключ неизвестен")
        return result.key

    def update_group(
        self,
        key: str,
        *,
        new_name: str | None = None,
        new_folder: str | None = None,
    ) -> str:
        """Переименовать и/или переместить группу, переписав Folder потомков.

        Одна операция, а не две: и переименование, и перемещение меняют
        собственный путь группы, а значит требуют одного и того же каскада.
        Возвращает фактический ключ группы после применения — он меняется,
        если у секции не было `ID`.
        """  # noqa: RUF002
        self._reject_common(key)
        result = self._write(
            GroupPatch(
                GroupPatchKind.RETARGET,
                target_key=key,
                new_name=new_name,
                new_folder=new_folder,
            ),
            rekey_from=key,
        )
        if result.key is None:
            # Недостижимо: RETARGET либо применяется, либо поднимает исключение.
            raise ServicesError("Группа изменена, но её ключ неизвестен")
        return result.key

    def remove_group(self, key: str, removal: GroupRemoval) -> bool:
        """Удалить группу. `False` — цели с таким ключом в файле не нашлось.

        Политика для содержимого обязательна: `PROMOTE` поднимает потомков
        к родителю удаляемой группы, `RECURSIVE` удаляет их вместе с ней.
        """  # noqa: RUF002
        self._reject_common(key)
        return self._write(
            GroupPatch(GroupPatchKind.REMOVE, target_key=key, removal=removal)
        ).applied
```

Расширить тип параметра `_write`:

```python
    def _write(self, patch: Patch, rekey_from: str | None = None) -> PatchResult:
```

и импорт из `edit`:

```python
from onecstarter.services.edit import Patch, PatchKind, PatchResult, SectionPatch
```

В `src/onecstarter/services/__init__.py`:

```python
"""Сценарии поверх config, domain и platform_1c. Qt здесь запрещён."""

from onecstarter.services.errors import ServicesError
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.workspace import Workspace, WorkspacePaths

__all__ = ["GroupRemoval", "ServicesError", "Workspace", "WorkspacePaths"]
```

- [ ] **Step 6: Убедиться, что тесты проходят**

Run: `uv run pytest tests/unit/test_workspace.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 8: Коммит**

```bash
git add src/onecstarter/services/workspace.py src/onecstarter/services/__init__.py \
        tests/unit/test_workspace.py tests/unit/test_writer.py
git commit -m "$(cat <<'EOF'
feat: операции над группами в координаторе слоя

add_group, update_group и remove_group замыкают набор: до сих пор группы
читались и собирались в дерево, но создать, переместить или осмысленно
удалить их было нечем.

Тест переигрывания фиксирует главное свойство каскада: база, добавленную
в группу штатным стартером между нашими попытками записи, каскад тоже
переписывает — цели считаются по свежему документу.
EOF
)"
```

---

## Task 7: Дедупликация пользовательского и общего списков

**Files:**
- Modify: `src/onecstarter/services/model.py` (поле `in_common_list`)
- Modify: `src/onecstarter/services/catalog.py` (функция `dedupe`)
- Modify: `src/onecstarter/services/workspace.py:297-302` (`_rebuild`)
- Modify: `tests/unit/test_catalog.py`
- Modify: `tests/unit/test_workspace.py:146-160`

**Interfaces:**
- Consumes: `model.InfobaseItem` (существует).
- Produces:
  - поле `InfobaseItem.in_common_list: bool` со значением по умолчанию `False`
  - `catalog.dedupe(user_items: Sequence[InfobaseItem], common_items: Sequence[InfobaseItem]) -> list[InfobaseItem]`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_catalog.py`. Импорт дополнить: `dedupe`.

```python
def _item(key: str, name: str, source: InfobaseSource) -> InfobaseItem:
    """Собрать запись напрямую: дедупликация смотрит только на ключ и источник."""  # noqa: RUF002
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
    """  # noqa: RUF002
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
```

В `tests/unit/test_workspace.py` заменить `test_same_base_in_both_lists_is_not_a_duplicate`
(строки 146–160) на:

```python
def test_same_base_in_both_lists_is_shown_once(tmp_path: Path) -> None:
    """[Ф] скил v8i-format: `ID` — ключ идентичности и слияния, значит это
    одна база. Выигрывает пользовательская запись, а пометка сообщает UI,
    что та же база есть и в общем списке.
    """  # noqa: RUF002
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Демо Бухгалтерия]\r\nConnect=File="C:\\Bases\\Demo";\r\n'
        "ID=44444444-4444-4444-4444-444444444444\r\n".encode()
    )
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    key = "id:44444444-4444-4444-4444-444444444444"
    matching = [item for item in workspace.items() if item.key == key]
    assert len(matching) == 1
    assert matching[0].source is InfobaseSource.USER
    assert matching[0].in_common_list
    assert workspace.launch(key).pid == 7
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_catalog.py tests/unit/test_workspace.py -q`
Expected: FAIL — `ImportError: cannot import name 'dedupe'`.

- [ ] **Step 3: Добавить поле модели**

В `src/onecstarter/services/model.py` в `InfobaseItem` после `parse_error`:

```python
    parse_error: str | None = None
    # Та же запись есть и в общем списке. Показывается один раз —
    # выигрывает пользовательская, потому что её файл мы вправе править.
    in_common_list: bool = False
```

- [ ] **Step 4: Реализовать `dedupe`**

В `src/onecstarter/services/catalog.py` добавить функцию после `load_common_items`:

```python
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
```

`replace` и `Sequence` в этом модуле уже импортированы.

- [ ] **Step 5: Подключить дедупликацию в координаторе**

В `src/onecstarter/services/workspace.py` в импорте из `catalog` добавить `dedupe`
и заменить `_rebuild`:

```python
    def _rebuild(self) -> None:
        document = parse_v8i(self._raw)
        items = items_from_document(document, InfobaseSource.USER, self._user)
        common, errors = load_common_items(common_list_paths(self.paths.cfg_paths), self._user)
        self._items = dedupe(items, common)
        self._common_errors = errors
```

- [ ] **Step 6: Убедиться, что тесты проходят**

Run: `uv run pytest -q`
Expected: PASS, вся сюита.

- [ ] **Step 7: Линт и типы**

Run: `uv run ruff check .` — Expected: `All checks passed!`
Run: `uv run mypy` — Expected: `Success: no issues found`

- [ ] **Step 8: Коммит**

```bash
git add src/onecstarter/services/model.py src/onecstarter/services/catalog.py \
        src/onecstarter/services/workspace.py tests/unit/test_catalog.py \
        tests/unit/test_workspace.py
git commit -m "$(cat <<'EOF'
feat: одна база — одна запись при слиянии источников

Запись, попавшая и в пользовательский список, и в общий, выдавалась items()
дважды: политика в дизайне плана 3 задана не была.

Выигрывает пользовательская — её файл мы вправе править. Пометка
in_common_list оставляет UI возможность объяснить происхождение записи,
не показывая её второй раз.
EOF
)"
```

---

## Task 8: Проверка целиком и статус в бэклоге

**Files:**
- Modify: `docs/tasks.md` (строка `T-04.4`)
- Modify: `docs/superpowers/specs/2026-08-04-v1-groups-and-dedupe-design.md` (раздел отступлений, если они были)

**Interfaces:**
- Consumes: результат Tasks 1–7.
- Produces: ничего для кода; фиксирует состояние задачи в бэклоге.

- [ ] **Step 1: Полный прогон**

Run: `uv run pytest -q`
Expected: PASS, ни одного пропущенного и ни одного `xfail`.

Run: `uv run ruff check .`
Expected: `All checks passed!`

Run: `uv run mypy`
Expected: `Success: no issues found`

- [ ] **Step 2: Проверить инвариант 1 отдельно**

Run: `uv run pytest tests/unit/test_no_qt_in_core.py -v`
Expected: PASS. Тест импортирует ядро в подпроцессе и убеждается, что `PySide6`
не оказался в `sys.modules`; новые модули `paths` и `groups` попадают под него
через импорт пакета `onecstarter.services`.

- [ ] **Step 3: Сверить реализацию со спекой**

Пройти по разделам спеки §2–§5 и убедиться, что каждое решение реализовано:
арифметика путей в одном экземпляре, `OrderInTree` не пишется, каскад одним проходом,
политика удаления обязательна, лазейки закрыты, дедупликация по ключу привязки.
Расхождения, если они появились по ходу работы, дописать в спеку отдельным разделом
«Отступления реализации от этого дизайна» — по образцу раздела 11
[дизайна плана 3](../specs/2026-08-03-v1-plan3-services-design.md). Если расхождений нет,
раздел не создавать.

- [ ] **Step 4: Обновить статус в бэклоге**

В `docs/tasks.md` в строке `T-04.4` заменить `дизайн утверждён, план не написан`
на ссылку на этот план и статус `DONE`:

```markdown
| T-04.4 | [Операции над группами и дедупликация источников](superpowers/plans/2026-08-04-v1-plan4-groups-and-dedupe.md) | DONE | нет |
```

В блоке обязательств из финального ревью плана 3 пункты 1 и 3 пометить закрытыми:
заменить `T-04.4` в колонке «Кому» на `DONE (T-04.4)`.

- [ ] **Step 5: Коммит**

```bash
git add docs/tasks.md docs/superpowers/specs/2026-08-04-v1-groups-and-dedupe-design.md
git commit -m "docs: план 4 закрыт — операции над группами и дедупликация"
```

---

## Что план сознательно не делает

- **UI.** Подтверждение перед `RECURSIVE`, показ пометки `in_common_list` и два пункта
  меню под две политики удаления — план раздела «Базы».

### Отложено финальным ревью ветки (04.08.2026)

Ни одно из этих наблюдений не блокирует слияние; все проверены и признаны безопасными.

| Что | Почему отложено, что делать дальше |
| --- | --- |
| Ключи вложенных подгрупп меняются каскадом молча. Подгруппа без `ID` при переносе родителя меняет путь, а значит и ключ, но `update_group` возвращает новый ключ только целевой группы | Данных не теряется — у групп нет ни избранного, ни истории; обращение по устаревшему ключу даёт `TargetGoneError` или `applied=False`, а не порчу. Но контракт этого не проговаривает: **UI обязан перечитывать ключи из `items()` после любой операции над группой, а не кешировать их**. Дописать фразу в докстринги `update_group` и `remove_group` в плане UI |
| Backstop неоднозначности заведён только для групп. Две секции без `ID` с одинаковыми `Connect` и именем дают один ключ, и `find_target` берёт первую | Состояние досталось от прежних планов, эта ветка его не меняла. На запуске частично прикрыто `_reject_ambiguous_name`. Переносить групповой guard на записи баз нельзя: две секции с одинаковыми именем и `Connect` — это одна база, и отказ сломал бы штатное удаление дубля |
| Ложное срабатывание backstop-а теоретически возможно для секции с пустым `Connect=`, чьё имя совпадает с путём корневой группы | Исход — отказ с внятным текстом, не порча данных. Относится к уже открытому вопросу «считает ли платформа `Connect=` группой», стоящему в `docs/tasks.md` строкой экспериментов |
| `binding_key` приводит путь группы к нижнему регистру, а сравнение путей в `paths` регистрозависимое | Сами создать коллизию не можем: созданным группам всегда пишется `ID`. Риск только от групп без `ID`, созданных сторонним инструментом. Решается вместе с экспериментом о регистре при сопоставлении `Folder` |

### Что финальное ревью нашло и что было исправлено до слияния

| Находка | Суть |
| --- | --- |
| **Critical** — суррогатный ключ группы вырождался в её имя | У группы `Connect` всегда `None`, хеш в суррогате — константа. Две группы без `ID` с одним именем под разными родителями были неразличимы, и `remove_group` с политикой `RECURSIVE` сносил первую попавшуюся вместе с содержимым, возвращая `True`. В суррогат группы внесён её собственный путь |
| Базу можно было превратить в группу правкой `{"Connect": None}` | Избранное молча отваливалось, а при совпадении имени возникали две группы с одним путём — состояние, которое план запрещает создавать |
| `Folder` у записи базы писался в непроверенной форме | Проверка нормализовала значение, а запись шла сырой: в одном файле уживались `/Клиенты` и `Клиенты/Розница`, а `"  Клиенты  "` записывался с пробелами |
| Защита формата не покрывала путь переименования | Заголовок присваивался напрямую в обход `config`. Заведён `V8iSection.rename`, оба переименования проведены через него |
| Один предикат и одно сообщение в двух экземплярах | `require_group_exists` сведена в один экземпляр |
| Докстринг `InvalidRequestError` разошёлся с кодом | Описывал переименование группы как неподдержанное, хотя ветка его реализовала |
- **Эксперименты на платформе.** Три вопроса из §7 спеки (регистр при сопоставлении
  `Folder`, видимость группы без `OrderInTree`, поведение стартера при удалении группы)
  занесены в `docs/tasks.md` строкой 5 обязательств плана 3 и проверяются на машине.
- **`PPasswd` в `security.secrets`.** Обязательство 2 ревью плана 3 остаётся за планом UI:
  ключ станет достижим, когда UI покажет свойства записи.
- **Дедупликация записей с разными `ID`.** Принципиально неотличима от двух настоящих
  разных баз (§1 спеки).
