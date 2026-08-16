# План 4a — UI раздела «Базы»: просмотр и запуск (T-04.5a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Работающее окно OneCStarter: дерево баз из `ibases.v8i` и общих списков, поиск набором текста, запуск с клавиатуры выбранным клиентом, контроль версии до запуска, избранное/недавние, трей, глобальный хоткей, слежение за файлом.

**Architecture:** Вся презентационная логика, которую можно посчитать без Qt (строки дерева, фильтрация, содержимое колонки версии), живёт в `services/display.py` и покрыта табличными тестами; Qt-слой (`onecstarter.ui`) только отображает готовые структуры и зовёт `Workspace`. Модель дерева — `QStandardItemModel`, пересобираемая целиком при каждом изменении: файл измеряется килобайтами, пересборка дешевле бухгалтерии индексов `QAbstractItemModel`. Домен дополняется решением спеки §4 (гибрид `resolve_version`), services — неявными узлами `build_tree` (спека §2).

**Tech Stack:** Python 3.13, PySide6 ≥ 6.10, pytest + pytest-qt (offscreen), ruff, mypy strict (кроме `onecstarter.ui.*`).

**Спека:** [2026-08-05-v1-ui-bases-design.md](../specs/2026-08-05-v1-ui-bases-design.md). **Ветка:** `feature/v1-plan4a-ui-bases` (создаётся при исполнении через superpowers:using-git-worktrees).

## Global Constraints

- Инвариант 1 CLAUDE.md: Qt импортируется только в `src/onecstarter/ui/`. Ни `services`, ни `domain` не получают ни одного Qt-импорта (тест `tests/unit/test_no_qt_in_core.py` уже стережёт это — не ломать).
- Инвариант 2: `resolve_version` остаётся чистой функцией — всё окружение аргументами.
- Инвариант 5: секреты не попадают ни в сообщения, ни в логи. Командная строка по `/IBName` секретов не несёт — только её и показываем.
- Процессы 1С в тестах не запускаются никогда: `spawn` и `open_url` всегда инжектируются фейками.
- Факты платформы в комментариях помечаются: **[Ф]** проверено, **[Д]** из документации, **[Р]** наше решение. Утверждение без метки в код не попадает.
- Русские докстринги требуют `# noqa: RUF001/RUF002/RUF003` там же, где их ставит существующий код (ruff flag ambiguous-unicode).
- Строки ≤ 100 символов (ruff), `uv run pytest`, `uv run ruff check .`, `uv run mypy` зелёные после каждой задачи.
- Коммит после каждой задачи. Сообщения — как в истории репозитория: `feat:`/`docs:`/`fix:` + русское описание.
- UI-тексты — по-русски, «база», «группа», «общий список» — терминология штатного стартера.

---

### Задача 1. `resolve_version`: гибрид и платформенный `fallback`

Спека §4. Наш выбор: установленный `DefaultVersion` побеждает маску даже вне её (как платформа, [Ф] T-05.5); заданный, но не установленный — игнорируется (тихий максимум-вообще не воспроизводим). `fallback` считается отдельной функцией по платформенным правилам — сейчас он всегда «максимум вообще» и врёт для большинства случаев.

**Files:**
- Modify: `src/onecstarter/domain/selection.py`
- Modify: `tests/unit/test_selection.py`

**Interfaces:**
- Consumes: `parse_version`, `VersionNumber`, `DefaultVersionRule`, `substitute` — без изменений.
- Produces: сигнатура `resolve_version(requested, section_default, cfg_rules, installed) -> VersionResolution` не меняется; меняется семантика: `SECTION_DEFAULT` возможен вне маски, `fallback` = «что молча запустил бы штатный стартер» по фактическим правилам платформы. `services/launch.py` и `services/display.py` (задача 3) читают `resolution.fallback` как есть.

- [x] **Step 1: Поправить и дополнить табличные тесты**

В `tests/unit/test_selection.py`:

1. Перевернуть строку `section-default-outside-mask-ignored` (была — решение 5 плана 2, опровергнута [Ф] T-05.5):

```python
    pytest.param(
        "8.3.25", "8.3.22.1923", NO_RULES, "8.3.22.1923", ResolutionSource.SECTION_DEFAULT,
        id="section-default-outside-mask-wins",  # [Ф] T-05.5, спека 4a §4
    ),
```

2. Добавить строку про неустановленный `DefaultVersion` (наш выбор — не подменять молча):

```python
    pytest.param(
        "8.3.25", "8.3.25.9999", NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="section-default-not-installed-ignored-for-our-choice",  # [Ф] T-05.5, спека 4a §4
    ),
```

3. Добавить тесты `fallback` (после `test_fallback_is_overall_max`, который остаётся как есть — [Ф] T-02.8):

```python
def test_fallback_of_installed_exact_version_is_itself() -> None:
    # Штатный стартер запустил бы ту же точную версию — подсказки быть не должно.
    resolution = resolve_version("8.3.25.1560", None, [], INSTALLED)
    assert resolution.fallback == resolution.version


def test_fallback_follows_section_default_outside_mask() -> None:
    # [Ф] T-05.5: DefaultVersion побеждает маску даже вне её.
    resolution = resolve_version("8.3.25", "8.3.22.1923", [], INSTALLED)
    assert resolution.fallback == parse_version("8.3.22.1923")
    assert resolution.fallback == resolution.version  # гибрид: мы следуем платформе


def test_fallback_of_missing_section_default_is_overall_max() -> None:
    # [Ф] T-05.5: не установленный DefaultVersion — тихий максимум вообще,
    # к максимуму с префиксом платформа не возвращается. Мы выбираем префикс,
    # поэтому подсказка обязана показать расхождение.
    resolution = resolve_version("8.3.25", "8.3.25.9999", [], INSTALLED)
    assert resolution.version == parse_version("8.3.25.1633")
    assert resolution.fallback == parse_version("8.3.27.2214")


def test_fallback_of_prefix_max_matches_our_choice() -> None:
    # [Ф] T-02.1: маска без DefaultVersion → максимум с префиксом у обоих.
    resolution = resolve_version("8.3.25", None, [], INSTALLED)
    assert resolution.fallback == resolution.version
```

- [x] **Step 2: Прогнать тесты — новые падают**

Run: `uv run pytest tests/unit/test_selection.py -v`
Expected: FAIL — `section-default-outside-mask-wins` (получен PREFIX_MAX), `test_fallback_of_installed_exact_version_is_itself`, `test_fallback_follows_section_default_outside_mask` (fallback = 8.3.27.2214).

- [x] **Step 3: Реализация**

Заменить `resolve_version` и добавить `_platform_choice` в `src/onecstarter/domain/selection.py` (модульный докстринг обновить: убрать «уточняющий маску», описать гибрид со ссылкой на спеку 4a §4 и [Ф] T-05.5):

```python
def resolve_version(
    requested: str | None,
    section_default: str | None,
    cfg_rules: Sequence[DefaultVersionRule],
    installed: Iterable[VersionNumber],
) -> VersionResolution:
    pool = sorted(set(installed))
    overall = pool[-1] if pool else None

    if requested is not None:
        try:
            wanted = parse_version(requested)
        except ValueError:
            return VersionResolution(None, ResolutionSource.INVALID_REQUEST, None, overall)
    else:
        wanted = None

    fallback = _platform_choice(wanted, section_default, cfg_rules, pool, overall)

    if wanted is None:
        if overall is not None:
            return VersionResolution(overall, ResolutionSource.MAX_INSTALLED, None, fallback)
        return VersionResolution(None, ResolutionSource.NOT_INSTALLED, None, None)

    if wanted.is_full:
        if wanted in pool:
            return VersionResolution(wanted, ResolutionSource.EXACT, wanted, fallback)
        return VersionResolution(None, ResolutionSource.NOT_INSTALLED, wanted, fallback)

    refined = _try_parse(section_default) if section_default is not None else None
    if refined is not None and refined.is_full and refined in pool:
        # [Ф] T-05.5: DefaultVersion побеждает неполную Version даже вне маски —
        # здесь мы следуем платформе (спека 4a, §4: это явное значение штатного
        # ключа, а не тихая подмена).
        return VersionResolution(refined, ResolutionSource.SECTION_DEFAULT, wanted, fallback)
    # [Р] спека 4a, §4: заданный, но не установленный DefaultVersion платформа
    # молча меняет на максимум вообще ([Ф] T-05.5). Тихую подмену не
    # воспроизводим: идём дальше по цепочке, расхождение показывает fallback.

    target = substitute(wanted, cfg_rules)
    if target is not None and target in pool:
        return VersionResolution(target, ResolutionSource.CFG_DEFAULT, wanted, fallback)

    matching = [version for version in pool if version.starts_with(wanted)]
    if matching:
        return VersionResolution(matching[-1], ResolutionSource.PREFIX_MAX, wanted, fallback)
    return VersionResolution(None, ResolutionSource.NOT_INSTALLED, wanted, fallback)


def _platform_choice(
    wanted: VersionNumber | None,
    section_default: str | None,
    cfg_rules: Sequence[DefaultVersionRule],
    pool: Sequence[VersionNumber],
    overall: VersionNumber | None,
) -> VersionNumber | None:
    """Что молча запустил бы штатный стартер — по правилам платформы.

    Отдельная логика, а не копия нашего выбора (спека 4a, §4): расхождения
    и есть то, что подсказка в UI обязана показать честно.

    - полная версия: установлена — она и есть; нет — максимум вообще ([Ф] T-02.8);
    - маска + DefaultVersion секции: установлен — побеждает даже вне маски,
      не установлен — максимум вообще, без возврата к префиксу ([Ф] T-05.5);
    - маска без DefaultVersion: подстановка cfg ([Д] ИТС, цель должна быть
      установлена — [Р] экстраполяция), затем максимум с префиксом ([Ф] T-02.1);
    - маска без совпадений и версия без запроса — максимум вообще
      ([Р] экстраполяция T-02.8, поведение платформы не снималось).

    DefaultVersion неполный или неразбираемый трактуется как отсутствующий —
    [Р], этот случай экспериментально не снимался.
    """  # noqa: RUF002
    if wanted is None:
        return overall
    if wanted.is_full:
        return wanted if wanted in pool else overall
    refined = _try_parse(section_default) if section_default is not None else None
    if refined is not None and refined.is_full:
        return refined if refined in pool else overall
    target = substitute(wanted, cfg_rules)
    if target is not None and target in pool:
        return target
    matching = [version for version in pool if version.starts_with(wanted)]
    if matching:
        return matching[-1]
    return overall
```

В докстринге `VersionResolution` (если появится) и модуля зафиксировать: `fallback` = платформенный выбор, `None` только при пустом пуле установленных.

- [x] **Step 4: Прогнать тесты и статику**

Run: `uv run pytest tests/unit/test_selection.py tests/unit/test_services_launch.py -v && uv run ruff check . && uv run mypy`
Expected: PASS (тесты `services_launch` не трогают изменённые случаи, но обязаны остаться зелёными).

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/domain/selection.py tests/unit/test_selection.py
git commit -m "feat: resolve_version по гибриду спеки 4a — DefaultVersion вне маски побеждает, fallback платформенный"
```

---

### Задача 2. `build_tree`: неявные узлы вместо пометки orphan

Спека §2, обязательство 5 блока Б: висячий `Folder` рисуется неявным узлом-группой, как платформа ([Ф] T-05.7). Пометка `orphan` уходит.

**Files:**
- Modify: `src/onecstarter/services/catalog.py`
- Modify: `tests/unit/test_catalog.py`
- Modify: `tests/unit/test_workspace.py` (использования `node.item` — теперь `item: InfobaseItem | None`)

**Interfaces:**
- Produces: `TreeNode(label: str, item: InfobaseItem | None, children: tuple[TreeNode, ...])`. `item is None` ⇔ неявный узел (группы нет в файле, операции невозможны). Поле `orphan` удалено. `Workspace.tree()` сигнатуру не меняет. Задача 3 потребляет `TreeNode` в этом виде.

- [x] **Step 1: Переписать тесты дерева**

В `tests/unit/test_catalog.py` заменить `test_orphan_folder_shows_in_root_and_is_marked` на:

```python
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
    # [Р] вложение неявной цепочки по сегментам пути — экстраполяция:
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
```

В существующих тестах этого файла заменить обращения `node.item.name` на `node.label` (mypy strict: `item` теперь Optional): `test_tree_nests_groups_and_bases`, `test_empty_group_has_no_children`, `test_empty_connect_is_group_like_platform_shows_it` — сравнение по `label`; там, где проверяется `is_group`, оставить через `node.item` с явным `assert node.item is not None` строкой выше.

В `tests/unit/test_workspace.py`:
- строки 314 и 354: `node.item.key` → `node.item is not None and node.item.key == ...` (в 354 — условие внутри `next(...)`);
- строки 362, 369, 419: `node.item.name` → `node.label`.

- [x] **Step 2: Прогнать — новые падают**

Run: `uv run pytest tests/unit/test_catalog.py -v`
Expected: FAIL — `TreeNode` не имеет `label`, старое поведение кладёт «Потерянную» в корень.

- [x] **Step 3: Реализация**

В `src/onecstarter/services/catalog.py` заменить `TreeNode`, `build_tree` и `_node`:

```python
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
```

Функцию `_node` удалить. Докстринг `Workspace.tree()` не меняется.

- [x] **Step 4: Полный прогон и статика**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS — включая `test_groups.py` и `test_workspace.py` (они ходят по дереву).

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/services/catalog.py tests/unit/test_catalog.py tests/unit/test_workspace.py
git commit -m "feat: build_tree рисует неявные узлы висячего Folder, как платформа (Ф T-05.7)"
```

---

### Задача 3. `services/display.py`: витрина раздела «Базы»

Спека §2–§4: виртуальные ветки, фильтрация casefold, содержимое колонки версии с подсказкой fallback — всё чистыми функциями, без Qt.

**Files:**
- Create: `src/onecstarter/services/display.py`
- Test: `tests/unit/test_display.py`

**Interfaces:**
- Consumes: `TreeNode` (задача 2), `resolve_version` (задача 1), `InfobaseItem`, `CommonListError`, `build_tree`, `Installation`, `Arch`, `DefaultVersionRule`, `ConnectKind`.
- Produces (задачи 6–8 потребляют):
  - `RowKind(Enum)`: `SECTION | GROUP | IMPLICIT_GROUP | BASE | NOTE`
  - `Row(kind: RowKind, label: str, item: InfobaseItem | None, children: tuple[Row, ...] = (), note: str | None = None)` — frozen dataclass
  - `display_forest(items: Sequence[InfobaseItem], tree: Sequence[TreeNode], common_errors: Sequence[CommonListError]) -> list[Row]`
  - `filter_rows(rows: Sequence[Row], query: str) -> list[Row]`
  - `row_label(row: Row) -> str` — метка с видимыми пометками; `row.label` остаётся чистым именем, по нему идёт поиск
  - `VersionCell(text: str, problem: bool, hint: str | None)` — frozen dataclass
  - `version_cell(item: InfobaseItem, installations: Sequence[Installation], cfg_rules: Sequence[DefaultVersionRule]) -> VersionCell`
  - константы `RECENT_LIMIT = 10`, `IMPLICIT_NOTE`, `COMMON_NOTE`, `BROKEN_SUFFIX`, `COMMON_SUFFIX`

- [x] **Step 1: Написать тесты**

`tests/unit/test_display.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.services.catalog import CommonListError, build_tree, items_from_document
from onecstarter.services.display import (
    BROKEN_SUFFIX,
    COMMON_SUFFIX,
    IMPLICIT_NOTE,
    RECENT_LIMIT,
    Row,
    RowKind,
    display_forest,
    filter_rows,
    row_label,
    version_cell,
)
from onecstarter.services.model import InfobaseItem, InfobaseSource
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


def _forest(entries: dict[str, BaseUserData] | None = None) -> list[Row]:
    items = _items(entries)
    return display_forest(items, build_tree(items), [])


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


def test_recent_section_sorted_by_launch_time_desc_and_limited() -> None:
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
    assert RECENT_LIMIT == 10


def _broken_item() -> InfobaseItem:
    """Запись с непрочитанной строкой — источник parse_error."""  # noqa: RUF002
    data = '[Битая]\r\nConnect=File="C:\\B";\r\nмусор без равенства\r\n'.encode()  # noqa: RUF001
    (item,) = items_from_document(parse_v8i(data), InfobaseSource.USER, {})
    assert item.parse_error is not None
    return item


def test_broken_record_note_carries_parse_error() -> None:
    # Спека 4a, §2: битая запись не валит приложение — показывается
    # с пометкой «не разобрано» и текстом parse_error.
    item = _broken_item()
    problem = item.parse_error
    assert problem is not None
    (row,) = display_forest([item], build_tree([item]), [])
    assert row.note is not None
    assert problem in row.note


def test_broken_record_label_is_visibly_marked() -> None:
    # Тултип виден только под мышью, а раздел рассчитан на работу
    # с клавиатуры — пометка обязана быть в самой метке строки.
    item = _broken_item()
    (row,) = display_forest([item], build_tree([item]), [])
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
    # Пометка — свойство показа, а не имени: поиск идёт по row.label,
    # поэтому суффикс не мешает найти базу и не находится сам.
    item = _broken_item()
    forest = display_forest([item], build_tree([item]), [])
    assert [row.label for row in filter_rows(forest, "битая")] == ["Битая"]
    assert filter_rows(forest, "не разобрано") == []


def test_implicit_group_row_carries_explanation() -> None:
    implicit = next(row for row in _forest() if row.label == "Нет такой группы")
    assert implicit.kind is RowKind.IMPLICIT_GROUP
    assert implicit.item is None
    assert implicit.note == IMPLICIT_NOTE


def test_common_branch_collects_items_and_errors() -> None:
    items = _items()
    common = [
        item_common
        for item_common in items_from_document(
            parse_v8i('[Общая]\r\nConnect=File="C:\\S";\r\nID=aaaa\r\n'.encode()),
            InfobaseSource.COMMON,
            {},
        )
    ]
    error = CommonListError(Path(r"C:\нет.v8i"), "нет файла")
    forest = display_forest(items + common, build_tree(items), [error])
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
```

Хелпер и тесты `version_cell` (в тот же файл; `replace` — из `dataclasses`, импорт в шапку):

```python
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
    # обязана появиться до запуска (боль А).
    cell = version_cell(_base("8.3.99.1"), INSTALLED, [])
    assert cell.problem
    assert cell.text == "8.3.99.1 — не установлена"
    assert cell.hint is not None and "8.3.27.2214" in cell.hint


def test_version_cell_hints_when_platform_would_differ() -> None:
    # [Ф] T-05.5: неустановленный DefaultVersion — платформа молча взяла бы
    # максимум вообще, мы берём максимум по маске и говорим об этом.
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
```

Импорт `ClientConvention` из шапки убрать (он не нужен — артефакт черновика).

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/unit/test_display.py -v`
Expected: FAIL — `ModuleNotFoundError: onecstarter.services.display`.

- [x] **Step 3: Реализация**

`src/onecstarter/services/display.py`:

```python
"""Витрина раздела «Базы»: чистая логика представления, без Qt (инвариант 1).

Строки дерева, фильтрация и содержимое колонки версии считаются здесь
и покрываются табличными тестами; слой ui только отображает готовое.
"""  # noqa: RUF002

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

RECENT_LIMIT = 10

_EPOCH = datetime.min.replace(tzinfo=UTC)

IMPLICIT_NOTE = (
    "Группы нет в файле — есть только путь Folder. Платформа рисует такой "
    "узел, не создавая секции; операции над ним невозможны."
)
COMMON_NOTE = (
    "Запись из общего списка (CommonInfoBases). Общий список доступен "
    "только для чтения."
)

# Видимые пометки в самой метке строки. Тултипа недостаточно: раздел
# рассчитан на работу с клавиатуры, наведения мышью может не быть вовсе.
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
) -> list[Row]:
    """Собрать лес раздела: Избранное, Недавние, дерево файла, Общие списки.

    Пустые виртуальные ветки не показываются — они шум. Порядок записей
    внутри веток повторяет порядок items (он уже отсортирован по OrderInList),
    Недавние — по времени запуска, новые сверху.
    """  # noqa: RUF002
    forest: list[Row] = []
    bases = [item for item in items if not item.is_group]
    favorites = tuple(_base_row(item) for item in bases if item.favorite)
    if favorites:
        forest.append(Row(RowKind.SECTION, "Избранное", None, favorites))
    launched = sorted(
        (item for item in bases if item.last_launched_at is not None),
        key=lambda item: item.last_launched_at or _EPOCH,
        reverse=True,
    )
    recent = tuple(_base_row(item) for item in launched[:RECENT_LIMIT])
    if recent:
        forest.append(Row(RowKind.SECTION, "Недавние", None, recent))
    forest.extend(_row_of(node) for node in tree)
    common = [item for item in items if item.source is InfobaseSource.COMMON]
    common_rows = [_row_of(node) for node in build_tree(common)]
    common_rows.extend(
        Row(RowKind.NOTE, f"{error.path}: {error.message}", None) for error in common_errors
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
) -> VersionCell:
    """Колонка версии: наш выбор, подсветка проблемы, подсказка о расхождении.

    Подсказка «штатный стартер запустил бы …» появляется только при
    фактическом расхождении с платформой: fallback уже посчитан
    по платформенным правилам ([Ф] T-05.5, задача 1 этого плана).
    """  # noqa: RUF002
    if item.is_group:
        return VersionCell("", False, None)
    if item.kind is ConnectKind.WEB:
        return VersionCell("веб", False, None)
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
        return VersionCell(text, False, "Штатный стартер не нашёл бы установленной версии")
    return VersionCell(text, False, f"Штатный стартер запустил бы {resolution.fallback}")


_ARCH_LABEL = {Arch.X64: "x64", Arch.X86: "x86", Arch.UNKNOWN: ""}


def _base_note(item: InfobaseItem) -> str | None:
    parts: list[str] = []
    if item.parse_error:
        parts.append(f"Не разобрано: {item.parse_error}")
    if item.source is InfobaseSource.COMMON or item.in_common_list:
        parts.append(COMMON_NOTE)
    return "\n".join(parts) or None


def _base_row(item: InfobaseItem) -> Row:
    return Row(RowKind.BASE, item.name, item, (), _base_note(item))


def _row_of(node: TreeNode) -> Row:
    children = tuple(_row_of(child) for child in node.children)
    if node.item is None:
        return Row(RowKind.IMPLICIT_GROUP, node.label, None, children, IMPLICIT_NOTE)
    if node.item.is_group:
        return Row(RowKind.GROUP, node.label, node.item, children, _base_note(node.item))
    return Row(RowKind.BASE, node.label, node.item, children, _base_note(node.item))
```

- [x] **Step 4: Прогнать тесты и статику**

Run: `uv run pytest tests/unit/test_display.py -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/services/display.py tests/unit/test_display.py
git commit -m "feat: витрина раздела Базы — лес строк, фильтр casefold, колонка версии с fallback-подсказкой"
```

---

### Задача 4. Ошибка порождения процесса — `LaunchError` с командной строкой

Спека §3: сообщение об ошибке запуска несёт фактическую командную строку. Сейчас `OSError` из `spawn` уходит наверх голым — UI показал бы трассировку.

**Files:**
- Modify: `src/onecstarter/services/launch.py`
- Modify: `tests/unit/test_services_launch.py`

**Interfaces:**
- Produces: `launch_infobase` поднимает `LaunchError` (не `OSError`) при отказе порождения процесса; текст содержит `command.command_line`. Секретов в командной строке по `/IBName` нет (инвариант 5 соблюдён по построению — `build_arguments` отклоняет секреты в connect-ветке).

- [x] **Step 1: Написать тест**

В `tests/unit/test_services_launch.py` (рядом с существующими тестами запуска; фикстуры-константы файла переиспользовать):

```python
def test_spawn_failure_becomes_launch_error_with_command_line() -> None:
    # Спека 4a, §3: ошибка запуска — сообщение с фактической командной
    # строкой, а не трассировка OSError.
    item = _file_item()  # использовать локальный хелпер файла с файловой базой

    def failing_spawn(command: LaunchCommand) -> int:
        raise OSError("описание отказа системы")

    with pytest.raises(LaunchError) as excinfo:
        launch_infobase(
            item,
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=failing_spawn,
            open_url=lambda url: True,
        )
    message = str(excinfo.value)
    assert "1cv8c.exe" in message
    assert "/IBName" in message
```

Точные имена хелпера записи и констант взять из шапки самого файла `test_services_launch.py` (там уже есть создание `InfobaseItem` файловой базы и наборы `INSTALLED`/`CONVENTIONS`); тест обязан использовать их, не создавая новых.

- [x] **Step 2: Прогнать — падает**

Run: `uv run pytest tests/unit/test_services_launch.py -v -k spawn_failure`
Expected: FAIL — поднялся голый `OSError`, а не `LaunchError`.

- [x] **Step 3: Реализация**

В `launch_infobase` заменить `pid = spawn(command)` на:

```python
    try:
        pid = spawn(command)
    except OSError as error:
        # Спека 4a, §3: командная строка в сообщении — для «скопировать
        # для отчёта». Секретов в ней нет: запуск идёт по /IBName.
        raise LaunchError(
            f"Не удалось запустить клиента для «{item.name}»: {error}.\n"  # noqa: RUF001
            f"Команда: {command.command_line}"
        ) from error
```

- [x] **Step 4: Прогнать и статика**

Run: `uv run pytest tests/unit/test_services_launch.py -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/services/launch.py tests/unit/test_services_launch.py
git commit -m "feat: отказ порождения процесса — LaunchError с командной строкой вместо голого OSError"
```

---

### Задача 5. Каркас UI: тема, главное окно, тестовая оснастка

Спека §1. Появляется первая Qt-кода: тема QSS по мотивам `temp/style/` (тёмный фон, жёлтый акцент, без бренда 1С), окно с узкой навигацией и заглушкой раздела, offscreen-тесты.

**Files:**
- Create: `src/onecstarter/ui/theme.py`
- Create: `src/onecstarter/ui/shell.py`
- Create: `tests/ui/conftest.py`
- Test: `tests/ui/test_shell.py`
- Modify: `pyproject.toml` (mypy-override для `tests.ui.*`)

**Interfaces:**
- Produces:
  - `theme.STYLESHEET: str`, константы `BACKGROUND`, `SURFACE`, `SURFACE_RAISED`, `BORDER`, `TEXT`, `TEXT_DIM`, `ACCENT`, `PROBLEM` (hex-строки) — задачи 6, 10 потребляют
  - `shell.MainWindow(section: QWidget)` — QMainWindow; `show_and_focus_search()` (зовёт `section.focus_search()`, если метод есть); свойство `close_to_tray: bool` (по умолчанию False; при True `closeEvent` прячет окно вместо закрытия)
- Consumes: ничего из новых модулей.

- [x] **Step 1: Тестовая оснастка**

`tests/ui/conftest.py`:

```python
"""Оснастка UI-тестов: offscreen-платформа Qt до первого импорта PySide6."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

В `pyproject.toml` после override для `onecstarter.ui.*` добавить (то же обоснование — Qt-сигналы и qtbot без строгих типов):

```toml
[[tool.mypy.overrides]]
module = "tests.ui.*"
disallow_untyped_defs = false
```

- [x] **Step 2: Написать smoke-тест окна**

Актуальный листинг (после финального ревью всей ветки): добавлены
`_StubSection` и два теста — `test_show_and_focus_search_calls_section_focus_search`
(шов `show_and_focus_search` → `section.focus_search()` не был покрыт: остальные
тесты используют `QLabel`, у которого `focus_search` просто нет, и
`getattr(...)/callable(...)` в реализации молча ничего не зовёт) и
`test_show_and_focus_search_keeps_maximized_window` (защита от регрессии Step 4).

`tests/ui/test_shell.py`:

```python
from PySide6.QtWidgets import QLabel, QWidget

from onecstarter.ui import theme
from onecstarter.ui.shell import MainWindow


class _StubSection(QWidget):
    """Раздел-заглушка с настоящим focus_search — в отличие от QLabel

    у остальных тестов файла, где focus_search просто отсутствует и шов
    getattr(...)/callable(...) в show_and_focus_search молча не срабатывает.
    """  # noqa: RUF002

    def __init__(self) -> None:
        super().__init__()
        self.focus_calls = 0

    def focus_search(self) -> None:
        self.focus_calls += 1


def test_window_builds_with_section_and_title(qtbot):
    window = MainWindow(QLabel("заглушка"))
    qtbot.addWidget(window)
    assert window.windowTitle() == "OneCStarter"
    assert window.centralWidget() is not None


def test_stylesheet_is_dark_with_accent():
    assert theme.BACKGROUND.startswith("#")
    assert theme.ACCENT.startswith("#")
    assert "QTreeView" in theme.STYLESHEET


def test_close_to_tray_hides_instead_of_closing(qtbot):
    window = MainWindow(QLabel("заглушка"))
    qtbot.addWidget(window)
    window.close_to_tray = True
    window.show()
    window.close()
    assert window.isHidden()
    # Окно живо: показ после «закрытия» возможен.
    window.show()
    assert not window.isHidden()


def test_show_and_focus_search_calls_section_focus_search(qtbot):
    section = _StubSection()
    window = MainWindow(section)
    qtbot.addWidget(window)
    window.show_and_focus_search()
    assert section.focus_calls == 1


def test_show_and_focus_search_keeps_maximized_window(qtbot):
    # showNormal() безусловно сбрасывал развёрнутое окно — хоткей/трей на
    # развёрнутом окне откатывали бы его в обычный размер незаметно
    # для пользователя.
    window = MainWindow(QLabel("заглушка"))
    qtbot.addWidget(window)
    window.showMaximized()
    assert window.isMaximized()
    window.show_and_focus_search()
    assert window.isMaximized()
```

- [x] **Step 3: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/ -v`
Expected: FAIL — модулей `theme`/`shell` нет.

- [x] **Step 4: Реализация**

`src/onecstarter/ui/theme.py`:

```python
"""Тёмная тема по мотивам портала «1С для разработчиков» (temp/style/).

Плоские списки, боковая навигация, жёлтый акцент. Без бренда 1С
(requirements.md, §4). Цвета собраны с эталонных скриншотов.
"""  # noqa: RUF002

BACKGROUND = "#161616"
SURFACE = "#1e1e1e"
SURFACE_RAISED = "#262626"
BORDER = "#333333"
TEXT = "#e8e8e8"
TEXT_DIM = "#9a9a9a"
ACCENT = "#f2d54c"
PROBLEM = "#e57373"

STYLESHEET = f"""
QMainWindow, QDialog, QMessageBox {{ background: {BACKGROUND}; }}
QWidget {{ color: {TEXT}; font-size: 10pt; }}
#NavRail {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#NavRail QToolButton {{ border: none; padding: 10px 12px; color: {TEXT_DIM}; }}
#NavRail QToolButton:checked {{ color: {ACCENT}; border-left: 2px solid {ACCENT}; }}
QLineEdit {{
    background: {SURFACE_RAISED}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 6px 8px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QTreeView {{ background: {BACKGROUND}; border: none; }}
QTreeView::item {{ padding: 4px; }}
QTreeView::item:selected {{ background: {SURFACE_RAISED}; }}
QHeaderView::section {{
    background: {SURFACE}; color: {TEXT_DIM}; border: none; padding: 4px 8px;
}}
QMenu {{ background: {SURFACE_RAISED}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {SURFACE}; color: {ACCENT}; }}
QToolTip {{ background: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""
```

`src/onecstarter/ui/shell.py`:

Актуальный листинг (после финального ревью всей ветки, Minor-замечание):
`show_and_focus_search` вызывал `showNormal()` безусловно — на развёрнутом
(maximized) окне хоткей/трей незаметно откатывали бы его в обычный размер.
Фикс: `showNormal()` только если окно скрыто или свёрнуто (`isHidden()`/
`isMinimized()`), иначе обычный `show()`, не трогающий geometry. Заодно
ушёл лишний неиспользуемый импорт `from PySide6.QtCore import Qt` (в
исходном черновике плана он не использовался нигде в файле), а `closeEvent`
получил `# noqa: N802` — имя метода диктует API `QWidget.closeEvent`, не
naming convention проекта.

```python
"""Главное окно: узкая навигация разделов + текущий раздел.

В v1 раздел один («Базы»), панель свёрнута до колонки с одной кнопкой —
каркас держит разделы v2+ как независимые виджеты (спека 4a, §1).
"""  # noqa: RUF002

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self, section: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OneCStarter")
        self.resize(900, 600)
        self.close_to_tray = False
        self._section = section

        rail = QFrame()
        rail.setObjectName("NavRail")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 8, 0, 8)
        bases_button = QToolButton()
        bases_button.setText("Базы")
        bases_button.setCheckable(True)
        bases_button.setChecked(True)
        rail_layout.addWidget(bases_button)
        rail_layout.addStretch(1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(rail)
        layout.addWidget(section, stretch=1)
        self.setCentralWidget(central)

    def show_and_focus_search(self) -> None:
        """Поднять окно и поставить фокус в поиск раздела (хоткей, трей).

        showNormal() сбрасывает развёрнутое (maximized) состояние окна —
        вызывать его нужно только чтобы вывести окно из свёрнутого
        (minimized) или скрытого (hide()) состояния. Если окно уже видимо
        развёрнутым, обычный show() поднимает его, не трогая geometry.
        """  # noqa: RUF002
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        focus = getattr(self._section, "focus_search", None)
        if callable(focus):
            focus()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # Закрытие при живом трее — сворачивание: приложение продолжает
        # работать в фоне ради глобального хоткея ([Р] спека 4a, §3).  # noqa: RUF003
        if self.close_to_tray:
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)
```

- [x] **Step 5: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/onecstarter/ui/theme.py src/onecstarter/ui/shell.py tests/ui/conftest.py tests/ui/test_shell.py pyproject.toml
git commit -m "feat: каркас окна OneCStarter — тёмная тема, навигация разделов, offscreen-тесты"
```

---

### Задача 6. Qt-модель дерева

Спека §2: колонки «База · Версия · Последний запуск», подсветка проблем, тултипы-подсказки, пометки неявных узлов и записей из общих списков.

**Files:**
- Create: `src/onecstarter/ui/bases/__init__.py` (пустой)
- Create: `src/onecstarter/ui/bases/tree_model.py`
- Test: `tests/ui/test_tree_model.py`

**Interfaces:**
- Consumes: `Row`, `RowKind`, `VersionCell` (задача 3), `theme` (задача 5).
- Produces (задача 8 потребляет):
  - `KEY_ROLE`, `KIND_ROLE` — роли `Qt.UserRole + 1/2`; `KEY_ROLE` несёт `item.key` (str) или `None`, `KIND_ROLE` — `RowKind.value` (str)
  - `COLUMNS = ("База", "Версия", "Последний запуск")`
  - `build_model(rows: Sequence[Row], cells: Mapping[str, VersionCell], format_stamp: Callable[[datetime], str]) -> QStandardItemModel`

- [x] **Step 1: Написать тест**

`tests/ui/test_tree_model.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import Qt

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.display import Row, RowKind, VersionCell
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui.bases.tree_model import COLUMNS, KEY_ROLE, KIND_ROLE, build_model


def _stamp(value):
    return value.strftime("%d.%m.%Y")


def _base_row(key="id:aaa", label="Демо", note=None, launched=None):
    item = InfobaseItem(
        key=key,
        name=label,
        folder="/",
        is_group=False,
        connect='File="C:\\B";',
        kind=ConnectKind.FILE,
        requested_version="8.3.25",
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id=None,
        last_launched_at=launched,
    )
    return Row(RowKind.BASE, label, item, (), note)


def test_model_has_columns_and_hierarchy(qtbot):
    rows = [
        Row(RowKind.SECTION, "Избранное", None, (_base_row(),)),
        Row(RowKind.GROUP, "Клиенты", _base_row(label="Клиенты").item, (_base_row(key="id:bbb"),)),
    ]
    cells = {"id:aaa": VersionCell("8.3.25.1633 x64", False, None)}
    model = build_model(rows, cells, _stamp)
    assert [
        model.headerData(i, Qt.Orientation.Horizontal) for i in range(len(COLUMNS))
    ] == list(COLUMNS)
    assert model.rowCount() == 2
    section = model.item(0, 0)
    assert section.rowCount() == 1
    base = section.child(0, 0)
    assert base.data(KEY_ROLE) == "id:aaa"
    assert base.data(KIND_ROLE) == RowKind.BASE.value
    assert section.child(0, 1).text() == "8.3.25.1633 x64"


def test_problem_cell_is_highlighted_and_hint_in_tooltip(qtbot):
    cell = VersionCell(
        "8.3.99.1 — не установлена", True, "Штатный стартер молча запустил бы 8.3.27.2214"
    )
    model = build_model([_base_row()], {"id:aaa": cell}, _stamp)
    version_item = model.item(0, 1)
    assert version_item.text() == "8.3.99.1 — не установлена"
    assert "8.3.27.2214" in version_item.toolTip()
    assert version_item.foreground().color().name() != model.item(0, 0).foreground().color().name()


def test_launch_stamp_is_formatted(qtbot):
    launched = datetime(2026, 8, 5, tzinfo=UTC)
    model = build_model([_base_row(launched=launched)], {}, _stamp)
    assert model.item(0, 2).text() == "05.08.2026"


def test_implicit_group_is_dimmed_with_note(qtbot):
    row = Row(RowKind.IMPLICIT_GROUP, "Нет такой группы", None, (), "группы нет в файле")
    model = build_model([row], {}, _stamp)
    name = model.item(0, 0)
    assert name.data(KEY_ROLE) is None
    assert "нет в файле" in name.toolTip()


def test_common_list_marker_suffix(qtbot):
    row = _base_row()
    marked = Row(row.kind, row.label, replace(row.item, in_common_list=True), (), None)
    model = build_model([marked], {}, _stamp)
    assert model.item(0, 0).text() == "Демо (в общем списке)"


def test_broken_record_is_marked_in_label_and_colour(qtbot):
    # Спека 4a, §2: битая запись показывается с пометкой «не разобрано».
    # Тултипа мало — раздел рассчитан на работу с клавиатуры, наведение
    # мышью не подразумевается.
    row = _base_row(note="Не разобрано: строка 3 не прочитана")
    item = replace(row.item, parse_error="строка 3 не прочитана")
    broken = Row(row.kind, row.label, item, (), row.note)
    # Модели держим переменными: без ссылки QStandardItemModel собирается
    # сборщиком мусора вместе со своими QStandardItem.
    healthy_model = build_model([_base_row()], {}, _stamp)
    broken_model = build_model([broken], {}, _stamp)
    healthy = healthy_model.item(0, 0)
    name = broken_model.item(0, 0)
    assert name.text() == "Демо (не разобрано)"
    assert "строка 3 не прочитана" in name.toolTip()
    assert name.foreground().color().name() != healthy.foreground().color().name()
```

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_tree_model.py -v`
Expected: FAIL — модуля нет.

- [x] **Step 3: Реализация**

`src/onecstarter/ui/bases/tree_model.py`:

```python
"""Qt-модель раздела «Базы»: QStandardItemModel, пересобираемая целиком.

Список измеряется килобайтами — пересборка при каждом изменении дешевле
бухгалтерии индексов QAbstractItemModel. Состояние развёрнутости
восстанавливает view по ключам (bases/view.py).
"""  # noqa: RUF002

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel

from onecstarter.services.display import Row, RowKind, VersionCell, row_label
from onecstarter.ui import theme

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2

COLUMNS = ("База", "Версия", "Последний запуск")


def build_model(
    rows: Sequence[Row],
    cells: Mapping[str, VersionCell],
    format_stamp: Callable[[datetime], str],
) -> QStandardItemModel:
    model = QStandardItemModel(0, len(COLUMNS))
    model.setHorizontalHeaderLabels(list(COLUMNS))
    for row in rows:
        model.appendRow(_items_for(row, cells, format_stamp))
    return model


def _items_for(row, cells, format_stamp):
    # Пометки считает витрина (services/display.row_label): «в общем списке» —
    # дубль «пользовательская + общая», штатное состояние после первого
    # запуска общей базы ([Ф] T-05.2), удалять его не предлагаем; «не
    # разобрано» — битая запись (спека 4a, §2). Здесь только рисуем.
    name = QStandardItem(row_label(row))
    version = QStandardItem("")
    launched = QStandardItem("")
    for cell in (name, version, launched):
        cell.setEditable(False)
    name.setData(row.kind.value, KIND_ROLE)
    name.setData(None, KEY_ROLE)
    if row.note:
        name.setToolTip(row.note)
    if row.kind is RowKind.SECTION:
        font = name.font()
        font.setBold(True)
        name.setFont(font)
    if row.kind in (RowKind.IMPLICIT_GROUP, RowKind.NOTE):
        name.setForeground(QBrush(QColor(theme.TEXT_DIM)))
    if row.item is not None:
        if row.item.parse_error:
            name.setForeground(QBrush(QColor(theme.PROBLEM)))
        name.setData(row.item.key, KEY_ROLE)
        cell = cells.get(row.item.key)
        if cell is not None:
            version.setText(cell.text)
            if cell.hint:
                version.setToolTip(cell.hint)
            if cell.problem:
                version.setForeground(QBrush(QColor(theme.PROBLEM)))
        if row.item.last_launched_at is not None:
            launched.setText(format_stamp(row.item.last_launched_at))
    for child in row.children:
        name.appendRow(_items_for(child, cells, format_stamp))
    return [name, version, launched]
```

- [x] **Step 4: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/ui/bases/__init__.py src/onecstarter/ui/bases/tree_model.py tests/ui/test_tree_model.py
git commit -m "feat: Qt-модель дерева баз — колонки, подсветка проблем, тултипы, пометки"
```

---

### Задача 7. Показ ошибок: `ui/errors.py`

Спека §3: `ServicesError` — человеческое сообщение с кнопкой «Скопировать», не трассировка.

**Files:**
- Create: `src/onecstarter/ui/errors.py`
- Test: `tests/ui/test_errors.py`

**Interfaces:**
- Consumes: `ServicesError` (иерархия из `services/errors.py`).
- Produces (задачи 8, 12 потребляют):
  - `build_error_box(parent: QWidget | None, error: ServicesError) -> QMessageBox` — собранный, но не показанный диалог; кнопка «Скопировать» кладёт текст ошибки в буфер
  - `show_service_error(parent: QWidget | None, error: ServicesError) -> None` — `build_error_box(...).exec()`

- [x] **Step 1: Написать тест**

`tests/ui/test_errors.py`:

```python
from PySide6.QtWidgets import QApplication

from onecstarter.services.errors import LaunchError
from onecstarter.ui.errors import build_error_box


def test_box_shows_message_and_copy_button(qtbot):
    error = LaunchError("Не удалось запустить: Команда: \"C:\\bin\\1cv8c.exe\" ENTERPRISE")  # noqa: RUF001
    box = build_error_box(None, error)
    assert "1cv8c.exe" in box.text()
    labels = [button.text() for button in box.buttons()]
    assert "Скопировать" in labels


def test_copy_button_puts_message_into_clipboard(qtbot):
    error = LaunchError("текст для отчёта")
    box = build_error_box(None, error)
    copy_button = next(b for b in box.buttons() if b.text() == "Скопировать")
    copy_button.click()
    assert QApplication.clipboard().text() == "текст для отчёта"
```

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_errors.py -v`
Expected: FAIL.

- [x] **Step 3: Реализация**

`src/onecstarter/ui/errors.py`:

```python
"""Показ ошибок слоя services: сообщение вместо трассировки (спека 4a, §3).

Текст любого ServicesError безопасен для показа и для буфера обмена:
слой services гарантирует отсутствие секретов в сообщениях (инвариант 5).
"""  # noqa: RUF002

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from onecstarter.services.errors import ServicesError


def build_error_box(parent: QWidget | None, error: ServicesError) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("OneCStarter")
    box.setText(str(error))
    box.addButton(QMessageBox.StandardButton.Ok)
    copy_button = box.addButton("Скопировать", QMessageBox.ButtonRole.ActionRole)
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(str(error)))
    return box


def show_service_error(parent: QWidget | None, error: ServicesError) -> None:
    build_error_box(parent, error).exec()
```

- [x] **Step 4: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/ui/errors.py tests/ui/test_errors.py
git commit -m "feat: диалог ошибок services — сообщение с кнопкой Скопировать вместо трассировки"
```

---

### Задача 8. Раздел «Базы»: виджет с поиском и запуском

Спека §2–§3: дерево + поиск + запуск с клавиатуры. Ядро пользовательского сценария: «2–3 буквы → Enter».

**Files:**
- Create: `src/onecstarter/ui/bases/view.py`
- Modify: `tests/ui/conftest.py` (фабрика Workspace)
- Test: `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `Workspace` (services), `display_forest`/`filter_rows`/`version_cell` (задача 3), `build_model`/роли (задача 6), `show_service_error` (задача 7), `ClientKind` (domain).
- Produces (задачи 10, 12 потребляют):
  - `BasesView(workspace: Workspace, installations: Sequence[Installation], cfg_rules: Sequence[DefaultVersionRule], on_error: Callable[[ServicesError], None] | None = None)`
  - `rebuild() -> None` — перечитать `items()/tree()/common_errors()` из workspace и перестроить модель (ключи не кешируются между вызовами — спека §2)
  - `focus_search() -> None`
  - `launch_key(key: str, forced: ClientKind | None = None) -> None` — запуск с обработкой `ServicesError` (нужен трею)

- [x] **Step 1: Фабрика Workspace в conftest**

Дополнить `tests/ui/conftest.py` (ниже установки offscreen; фикстура повторяет паттерн `tests/unit/test_workspace.py` — жёсткая копия осознанна, импорт между тест-модулями хрупок):

```python
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from onecstarter.domain.launch import ClientConvention, ClientKind, LaunchCommand
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.services.workspace import Workspace, WorkspacePaths

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"

CONVENTIONS = [
    ClientConvention(
        min_version=parse_version("8.2"),
        bin_dir="bin",
        executables={
            ClientKind.THIN: "1cv8c.exe",
            ClientKind.THICK: "1cv8.exe",
            ClientKind.DESIGNER: "1cv8.exe",
        },
    )
]
INSTALLED = [
    Installation(parse_version("8.3.25.1633"), Path(r"C:\Program Files\1cv8\8.3.25.1633"), Arch.X64)
]


@pytest.fixture
def workspace_factory(tmp_path):
    def factory(installations=None):
        calls: list[LaunchCommand] = []
        ibases = tmp_path / "ibases.v8i"
        if not ibases.exists():
            shutil.copyfile(FIXTURE, ibases)

        def fake_spawn(command: LaunchCommand) -> int:
            calls.append(command)
            return 7

        workspace = Workspace(
            WorkspacePaths(ibases=ibases, user_data=tmp_path / "bases.json"),
            installations=INSTALLED if installations is None else installations,
            conventions=CONVENTIONS,
            cfg_rules=[],
            default_app=None,
            spawn=fake_spawn,
            open_url=lambda url: True,
            now=lambda: datetime.fromisoformat("2026-08-07T10:00:00+00:00"),
            new_id=lambda: "99999999-9999-9999-9999-999999999999",
        )
        return workspace, calls

    return factory
```

- [x] **Step 2: Написать тесты**

`tests/ui/test_bases_view.py`:

Актуальный листинг (после fix round 1, ревью — см. Important-замечание про
отсутствие покрытия веб-меню и шорткатов): `qtbot.keyClicks` заменён на
локальный хелпер `_type()` (на этой машине зависает на кириллице — детали
в `task-8-report.md`), добавлены `_select_key()` и три теста на
`_build_menu`/`Ctrl+1`/`Ctrl+D`.

Актуальный листинг (после финального ревью всей ветки, два Minor-замечания):
`_view()` и `workspace_factory` (`tests/ui/conftest.py`) отдают четвёртым
элементом `opened: list[str]` — записанные вызовы `open_url`, до этого
раунда фабрика собирала только `calls` (spawn) и не давала способа
проверить, что база открылась браузером, а не процессом. Добавлены
`test_enter_in_empty_search_launches_nothing` /
`test_enter_in_whitespace_only_search_launches_nothing` (пустой поиск + Enter
не должен запускать первую базу леса) и
`test_ctrl_1_on_web_base_does_not_pass_forced_client_through` (Ctrl+1/2/3 на
веб-базе не должен протаскивать `forced_client` в `workspace.launch()` — тест
подменяет `workspace.launch` шпионом, а не только проверяет исход, потому что
`launch_infobase` и так игнорирует `forced_client` для `WEB`, и проверка
одного исхода не отличила бы старое поведение от нового).

```python
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QEvent, QModelIndex, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from onecstarter.domain.launch import ClientKind, LaunchCommand
from onecstarter.domain.version import Installation
from onecstarter.services.errors import LaunchError, ServicesError
from onecstarter.services.launch import LaunchOutcome
from onecstarter.ui.bases.tree_model import KEY_ROLE
from onecstarter.ui.bases.view import BasesView

from .conftest import INSTALLED


def _view(
    qtbot: Any,
    workspace_factory: Any,
    installations: Sequence[Installation] | None = None,
    errors: list[ServicesError] | None = None,
) -> tuple[BasesView, list[LaunchCommand], list[ServicesError], list[str]]:
    workspace, calls, opened = workspace_factory(installations)
    recorded = errors if errors is not None else []
    view = BasesView(
        workspace,
        installations=INSTALLED if installations is None else installations,
        cfg_rules=[],
        on_error=recorded.append,
    )
    qtbot.addWidget(view)
    return view, calls, recorded, opened


def _type(widget: QWidget, text: str) -> None:
    """Набрать текст посимвольно в обход qtbot.keyClicks.

    На этой машине (PySide6 6.11.1, Qt 6.11.1, QT_QPA_PLATFORM=offscreen)
    QTest.keyClicks зависает насмерть на кириллице — воспроизводится и на
    голом QLineEdit без единой строчки кода проекта, значит баг в
    биндинге/платформенном плагине, а не в реализации. Однобуквенный
    QTest.keyClick(widget, char) не зависает, но портит небайтовые символы
    (наблюдался мохибейк: UTF-8 байты символа возвращались как два разных
    Latin-1 символа). Рабочий обходной путь — тот же приём, которым Qt
    пользуется внутри qWait: собрать QKeyEvent с текстом и отправить его
    виджету напрямую, в обход платформенной раскладки клавиатуры.
    Поведение виджета (посимвольный textChanged) не отличается от реального
    набора — проверено: количество сигналов textChanged равно длине текста.
    """  # noqa: RUF002
    for char in text:
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(
                widget, QKeyEvent(kind, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, char)
            )


def _select_key(view: BasesView, key: str) -> None:
    """Поставить currentIndex дерева на строку базы с данным ключом.

    Поиск идёт по KEY_ROLE колонки 0 (роли на других колонках не выставлены —
    ui/bases/tree_model.py), рекурсивно по всему дереву модели.
    """  # noqa: RUF002
    model = view.model()

    def walk(parent: QModelIndex) -> QModelIndex | None:
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            if index.data(KEY_ROLE) == key:
                return index
            found = walk(index)
            if found is not None:
                return found
        return None

    index = walk(QModelIndex())
    assert index is not None, f"строка с ключом {key!r} не найдена в дереве"  # noqa: RUF001
    view._tree.setCurrentIndex(index)


def test_tree_is_populated_from_file(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert "Клиенты" in labels
    assert "Учёт серверный" in labels
    assert "Нет такой группы" in labels  # неявный узел


def test_typing_filters_tree(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    _type(view.search(), "демо роз")
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert labels == ["Клиенты"]


def test_enter_in_search_launches_first_visible_base(qtbot, workspace_factory):
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    _type(view.search(), "демо бух")  # noqa: RUF001
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert errors == []
    assert len(calls) == 1
    assert '/IBName"Демо Бухгалтерия"' in calls[0].command_line
    assert "/AppAutoCheckVersion-" in calls[0].command_line


def test_activating_group_row_does_not_launch(qtbot, workspace_factory):
    # Спека 4a, §3: Enter и двойной клик по группе, неявному узлу или
    # заголовку ветки ничего не запускают. Проверяются и вызовы, и ошибки:
    # без guard'а запуск группы дал бы LaunchError в on_error, а не вызов.  # noqa: RUF003
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    model = view.model()
    group_item = next(
        model.item(i, 0) for i in range(model.rowCount())
        if model.item(i, 0).text() == "Клиенты"
    )
    view._launch_index(model.indexFromItem(group_item))
    assert calls == []
    assert errors == []


def test_launch_error_goes_to_handler_not_up(qtbot, workspace_factory):
    view, calls, errors, _ = _view(qtbot, workspace_factory, installations=[])
    _type(view.search(), "демо бух")  # noqa: RUF001
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert calls == []
    assert len(errors) == 1
    assert isinstance(errors[0], LaunchError)


def test_favorite_toggle_shows_favorites_branch(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    view.toggle_favorite(key)
    first = view.model().item(0, 0)
    assert first.text() == "Избранное"
    assert first.child(0, 0).text() == "Демо Бухгалтерия"


def test_recent_branch_appears_after_launch(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    _type(view.search(), "демо бух")  # noqa: RUF001
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    view.search().clear()
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert labels[0] == "Недавние"


def test_rebuild_rereads_keys_from_workspace(qtbot, workspace_factory):
    # Спека 4a, §2: после операции UI берёт свежие items()/tree(), ключи
    # не кешируются — они меняются при дописывании ID.
    view, _, _, _ = _view(qtbot, workspace_factory)
    workspace = view.workspace()
    path = workspace.paths.ibases
    path.write_bytes(path.read_bytes() + '[Новая]\r\nConnect=File="C:\\N";\r\n'.encode())
    assert workspace.reload_if_changed()
    view.rebuild()
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert "Новая" in labels


def test_web_base_context_menu_has_only_browser_action(qtbot, workspace_factory):
    # Ветка ConnectKind.WEB в _build_menu: у веб-базы нет исполняемого файла,  # noqa: RUF003
    # поэтому пункты клиентов («Тонкий клиент», «Конфигуратор») не показываются
    # (services/launch.py — веб-база открывается браузером, а не процессом).  # noqa: RUF003
    view, _, _, _ = _view(qtbot, workspace_factory)
    item = next(i for i in view.workspace().items() if i.name == "Портал")
    menu = view._build_menu(item, item.key)
    texts = [action.text() for action in menu.actions()]
    assert any("Открыть в браузере" in text for text in texts)
    assert not any("Тонкий клиент" in text for text in texts)
    assert not any("Конфигуратор" in text for text in texts)


def test_ctrl_1_launches_thin_client_on_current_row(qtbot, workspace_factory):
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    _select_key(view, "id:44444444-4444-4444-4444-444444444444")
    view._launch_current(ClientKind.THIN)
    assert errors == []
    assert len(calls) == 1
    assert "1cv8c.exe" in calls[0].command_line


def test_ctrl_d_toggles_favorite_on_current_row(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    _select_key(view, "id:44444444-4444-4444-4444-444444444444")
    view._toggle_current_favorite()
    first = view.model().item(0, 0)
    assert first.text() == "Избранное"
    assert first.child(0, 0).text() == "Демо Бухгалтерия"


def test_enter_in_empty_search_launches_nothing(qtbot, workspace_factory):
    # Minor-замечание финального ревью: случайный Enter в пустом поиске
    # (например, сразу после хоткея, до первой буквы) не должен запустить
    # первую базу леса — единственное нажатие запускало бы чужую реальную
    # базу.
    view, calls, errors, opened = _view(qtbot, workspace_factory)
    assert view.search().text().strip() == ""
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert calls == []
    assert opened == []
    assert errors == []


def test_enter_in_whitespace_only_search_launches_nothing(qtbot, workspace_factory):
    # Пробелы без букв — тоже "пустой" поиск после strip().
    view, calls, errors, opened = _view(qtbot, workspace_factory)
    _type(view.search(), "   ")
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert calls == []
    assert opened == []
    assert errors == []


def test_ctrl_1_on_web_base_does_not_pass_forced_client_through(qtbot, workspace_factory):
    # Minor-замечание финального ревью: Ctrl+1/2/3 на веб-базе раньше молча
    # протаскивали forced_client в workspace.launch(), хотя контекстное меню
    # честно прячет клиентские пункты для такой базы — расхождение вводило
    # в заблуждение. launch_infobase сегодня игнорирует forced_client для
    # WEB, так что итоговый вызов (браузер, без процесса) не отличался бы —
    # поэтому здесь проверяется не только исход, а фактическое значение,
    # дошедшее до workspace.launch: оно обязано быть None, а не THIN.
    view, calls, errors, opened = _view(qtbot, workspace_factory)
    portal = next(i for i in view.workspace().items() if i.name == "Портал")
    _select_key(view, portal.key)

    workspace = view.workspace()
    received: list[ClientKind | None] = []
    original_launch = workspace.launch

    def spy_launch(key: str, forced_client: ClientKind | None = None) -> LaunchOutcome:
        received.append(forced_client)
        return original_launch(key, forced_client)

    workspace.launch = spy_launch  # type: ignore[method-assign]

    view._launch_current(ClientKind.THIN)

    assert received == [None]
    assert errors == []
    assert calls == []
    assert len(opened) == 1
```

Соответствующая правка `tests/ui/conftest.py` (Step 1 выше): фабрика
`workspace_factory` заводит `fake_open_url`, записывающий переданные URL
в список `opened`, и передаёт его в конструктор `Workspace(..., open_url=...)`
вместо прежней заглушки `lambda url: True`; возвращает `(workspace, calls, opened)`.

- [x] **Step 3: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_bases_view.py -v`
Expected: FAIL.

- [x] **Step 4: Реализация**

`src/onecstarter/ui/bases/view.py`:

Актуальный листинг (после fix round 1, ревью): `_show_menu` разбит на
`_build_menu(item, key) -> QMenu` (сборка меню без `exec` — тестируется
напрямую без блокирующего показа) и `_show_menu` (поиск строки под курсором
и вызов `exec`), `ConnectKind` импортируется в шапке модуля сразу (не
довеском после листинга). Точечные правки под `mypy --strict`/`ruff` (typed
`_first_base`/`_show_menu`, `cast` в `model()`, `isinstance`-проверка
в `_current_base_key()`, убранный неиспользуемый `QAction`) — см.
`task-8-report.md`.

Актуальный листинг (после финального ревью всей ветки, два Minor-замечания):

- `_launch_first_visible` при пустом (после `strip()`) тексте поиска ничего
  не запускает — случайный `Enter` сразу после хоткея, до первой буквы,
  запускал первую базу леса (чужую реальную базу одним нажатием).
- `_launch_current` для веб-базы (`item.kind is ConnectKind.WEB`) вызывает
  `launch_key(key)` без `forced` — раньше `forced` протаскивался в
  `workspace.launch()` и там молча терялся (`launch_infobase` не использует
  `forced_client` для `WEB`), хотя контекстное меню (`_build_menu`) честно
  прячет клиентские пункты для такой базы. Итоговый результат («Портал»
  открывается браузером) не изменился, но вызов больше не врёт о том,
  что запрашивался конкретный клиент.

```python
"""Раздел «Базы»: поиск, дерево, запуск. Целевой сценарий — хоткей →
2–3 буквы → Enter (requirements.md, боль Б).

Виджет не кеширует ни ключи, ни строки: любое изменение — rebuild()
и свежие items()/tree() из Workspace (спека 4a, §2). Расчёты без Qt
живут в services/display.py, здесь — только отображение и события.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtGui import QKeySequence, QShortcut, QStandardItemModel
from PySide6.QtWidgets import QLineEdit, QMenu, QTreeView, QVBoxLayout, QWidget

from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import ClientKind
from onecstarter.domain.version import Installation
from onecstarter.services.display import Row, RowKind, display_forest, filter_rows, version_cell
from onecstarter.services.errors import ServicesError
from onecstarter.services.model import InfobaseItem
from onecstarter.services.workspace import Workspace
from onecstarter.ui import errors as error_ui
from onecstarter.ui.bases.tree_model import KEY_ROLE, KIND_ROLE, build_model


def _format_stamp(stamp: datetime) -> str:
    return stamp.astimezone().strftime("%d.%m.%Y %H:%M")


class BasesView(QWidget):
    def __init__(
        self,
        workspace: Workspace,
        *,
        installations: Sequence[Installation],
        cfg_rules: Sequence[DefaultVersionRule],
        on_error: Callable[[ServicesError], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._installations = list(installations)
        self._cfg_rules = list(cfg_rules)
        self._on_error = on_error or (lambda error: error_ui.show_service_error(self, error))
        self._rows: list[Row] = []
        # Развёрнутость «чистого» (нефильтрованного) дерева и признак того,
        # что сейчас показан результат фильтра. Разделены намеренно: см.
        # rebuild().
        self._expansion: set[str] = set()
        self._filtered = False

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск: начните вводить имя базы")
        self._tree = QTreeView()
        self._tree.setHeaderHidden(False)
        self._tree.setAlternatingRowColors(False)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._search)
        layout.addWidget(self._tree, stretch=1)

        self._search.textChanged.connect(lambda _text: self.rebuild())
        self._search.returnPressed.connect(self._launch_first_visible)
        self._tree.activated.connect(self._launch_index)
        self._tree.customContextMenuRequested.connect(self._show_menu)
        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_current_favorite)
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self._launch_current(ClientKind.THIN))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self._launch_current(ClientKind.THICK))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self._launch_current(ClientKind.DESIGNER))

        self.rebuild()

    # -- доступ для тестов, трея и оболочки --------------------------------

    def workspace(self) -> Workspace:
        return self._workspace

    def model(self) -> QStandardItemModel:
        # _tree.model() возвращает базовый QAbstractItemModel по стубам Qt,
        # но rebuild() всегда ставит именно QStandardItemModel из build_model.
        return cast(QStandardItemModel, self._tree.model())

    def search(self) -> QLineEdit:
        return self._search

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    # -- перестройка --------------------------------------------------------

    def rebuild(self) -> None:
        """Пересобрать модель и вернуть дереву прежнюю развёрнутость.

        Слепок развёрнутости снимается только с нефильтрованного дерева:
        `expandAll()` на время поиска — следствие фильтра, а не выбор
        пользователя. Снимая слепок с развёрнутого фильтром дерева, мы бы
        запомнили «развёрнуто всё» и уже не вернулись бы к свёрнутому виду
        никогда (находка финального ревью 07.08.2026).
        """  # noqa: RUF002
        items = self._workspace.items()
        forest = display_forest(items, self._workspace.tree(), self._workspace.common_errors())
        query = self._search.text()
        self._rows = filter_rows(forest, query)
        cells = {
            item.key: version_cell(item, self._installations, self._cfg_rules)
            for item in items
            if not item.is_group
        }
        if not self._filtered:
            self._expansion = self._expanded_keys()
        model = build_model(self._rows, cells, _format_stamp)
        self._tree.setModel(model)
        for column in range(model.columnCount()):
            self._tree.resizeColumnToContents(column)
        self._filtered = bool(query.strip())
        if self._filtered:
            self._tree.expandAll()
        else:
            self._restore_expansion(self._expansion)

    @staticmethod
    def _marker(index: QModelIndex, path: str) -> str:
        """Устойчивый маркер узла для запоминания развёрнутости.

        Ключ привязки, если он есть: он переживает и переименование
        родителя, и смену порядка. Иначе — полный путь меток: у секций
        и неявных узлов ключа нет, а одной метки мало — два узла «Старое»
        на разных ветках разворачивались бы вместе.
        """  # noqa: RUF002
        key = index.data(KEY_ROLE)
        return key if isinstance(key, str) else f"label:{path}"

    def _expanded_keys(self) -> set[str]:
        model = self._tree.model()
        if model is None:
            return set()
        keys: set[str] = set()

        def walk(parent: QModelIndex, path: str) -> None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                here = f"{path}/{index.data()}"
                if self._tree.isExpanded(index):
                    keys.add(self._marker(index, here))
                walk(index, here)

        walk(QModelIndex(), "")
        return keys

    def _restore_expansion(self, keys: set[str]) -> None:
        model = self._tree.model()

        def walk(parent: QModelIndex, path: str) -> None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                here = f"{path}/{index.data()}"
                if self._marker(index, here) in keys:
                    self._tree.expand(index)
                walk(index, here)

        walk(QModelIndex(), "")

    # -- запуск и операции ---------------------------------------------------

    def launch_key(self, key: str, forced: ClientKind | None = None) -> None:
        try:
            self._workspace.launch(key, forced)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def toggle_favorite(self, key: str) -> None:
        item = next((i for i in self._workspace.items() if i.key == key), None)
        try:
            self._workspace.set_favorite(key, not (item.favorite if item else False))
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def _launch_index(self, index: QModelIndex) -> None:
        if index.siblingAtColumn(0).data(KIND_ROLE) != RowKind.BASE.value:
            return  # группы, неявные узлы и заголовки не запускаются
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        if key:
            self.launch_key(key)

    def _launch_first_visible(self) -> None:
        # Пустой поиск (после strip) — ничего не запускаем: случайный Enter
        # (например, сразу после хоткея, до первой буквы) не должен
        # запустить первую базу леса — чужую реальную базу одним нажатием.
        if not self._search.text().strip():
            return
        first = self._first_base(self._rows)
        if first is not None:
            self.launch_key(first)

    def _first_base(self, rows: Sequence[Row]) -> str | None:
        for row in rows:
            if row.kind is RowKind.BASE and row.item is not None:
                return row.item.key
            nested = self._first_base(row.children)
            if nested is not None:
                return nested
        return None

    def _current_base_key(self) -> str | None:
        index = self._tree.currentIndex()
        if not index.isValid():
            return None
        if index.siblingAtColumn(0).data(KIND_ROLE) != RowKind.BASE.value:
            return None
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        return key if isinstance(key, str) else None

    def _launch_current(self, forced: ClientKind | None) -> None:
        key = self._current_base_key()
        if not key:
            return
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is not None and item.kind is ConnectKind.WEB:
            # launch_infobase игнорирует forced_client для веб-баз (нет
            # исполняемого файла клиента) — контекстное меню честно прячет
            # пункты «Тонкий клиент»/«Конфигуратор» для WEB (_build_menu),
            # а хоткей Ctrl+1/2/3 раньше молча протаскивал forced дальше
            # в workspace.launch(), хотя тот его для WEB не использует.
            # Здесь — тот же результат («Портал» открывается браузером),
            # но без обмана: клиент не запрашивается вовсе.
            self.launch_key(key)
        else:
            self.launch_key(key, forced)

    def _toggle_current_favorite(self) -> None:
        key = self._current_base_key()
        if key:
            self.toggle_favorite(key)

    def _build_menu(self, item: InfobaseItem, key: str) -> QMenu:
        """Собрать контекстное меню базы без показа (для тестов и _show_menu).

        Отделено от _show_menu ради проверки состава пунктов без блокирующего
        QMenu.exec — вызов из теста строит меню и читает тексты действий.
        """
        menu = QMenu(self)
        if item.kind is ConnectKind.WEB:
            menu.addAction("Открыть в браузере", lambda: self.launch_key(key))
        else:
            menu.addAction("Запустить", lambda: self.launch_key(key))
            menu.addAction(
                "Тонкий клиент\tCtrl+1", lambda: self.launch_key(key, ClientKind.THIN)
            )
            menu.addAction(
                "Толстый клиент\tCtrl+2", lambda: self.launch_key(key, ClientKind.THICK)
            )
            menu.addAction(
                "Конфигуратор\tCtrl+3", lambda: self.launch_key(key, ClientKind.DESIGNER)
            )
        menu.addSeparator()
        star = "Убрать из избранного" if item.favorite else "В избранное"  # noqa: RUF001
        menu.addAction(f"{star}\tCtrl+D", lambda: self.toggle_favorite(key))
        return menu

    def _show_menu(self, position: QPoint) -> None:
        index = self._tree.indexAt(position)
        if not index.isValid():
            return
        kind = index.siblingAtColumn(0).data(KIND_ROLE)
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        if kind != RowKind.BASE.value or not key:
            return
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return
        menu = self._build_menu(item, key)
        menu.exec(self._tree.viewport().mapToGlobal(position))
```

- [x] **Step 5: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/onecstarter/ui/bases/view.py tests/ui/conftest.py tests/ui/test_bases_view.py
git commit -m "feat: раздел Базы — дерево, поиск, запуск с клавиатуры, избранное, контекстное меню"
```

---

### Задача 9. Слежение за файлом: `ui/watcher.py`

Спека §5: watcher живёт в `ui` (инвариант 1), переживает атомарную замену файла, гасит дребезг.

**Files:**
- Create: `src/onecstarter/ui/watcher.py`
- Test: `tests/ui/test_watcher.py`

**Interfaces:**
- Consumes: только Qt и `pathlib`.
- Produces (задача 12 потребляет): `FileWatcher(path: Path, debounce_ms: int = 200, parent: QObject | None = None)` с сигналом `changed` (без аргументов).

- [x] **Step 1: Написать тесты**

`tests/ui/test_watcher.py`:

```python
import os
import tempfile
import time
from pathlib import Path

from onecstarter.ui.watcher import FileWatcher


def _replace_atomically(path: Path, payload: bytes, attempts: int = 20) -> None:
    """Как пишет и платформа, и наш atomic_write: временный файл + замена.

    Ретрай — на гонку файловых хендлов Windows: два быстрых `os.replace`
    подряд изредка встречают `PermissionError [WinError 5]` (антивирус,
    индексатор, ещё не закрытый хендл watcher'а). Это свойство среды,
    а не дефект продукта, поэтому ретрай здесь, в тестовом хелпере,
    и не в `atomic_write`.
    """  # noqa: RUF002
    handle, temp_name = tempfile.mkstemp(dir=path.parent)
    os.close(handle)
    temp = Path(temp_name)
    temp.write_bytes(payload)
    for attempt in range(attempts):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def test_plain_write_emits_changed(qtbot, tmp_path):
    target = tmp_path / "ibases.v8i"
    target.write_bytes(b"[A]\r\n")
    watcher = FileWatcher(target, debounce_ms=50)
    with qtbot.waitSignal(watcher.changed, timeout=3000):
        target.write_bytes(b"[A]\r\nConnect=x\r\n")


def test_atomic_replace_keeps_watching(qtbot, tmp_path):
    # Спека 4a, §5: полная перезапись (материализация общей базы, перезапись
    # штатным стартером) не должна отключать слежение.
    target = tmp_path / "ibases.v8i"
    target.write_bytes(b"[A]\r\n")
    watcher = FileWatcher(target, debounce_ms=50)
    with qtbot.waitSignal(watcher.changed, timeout=3000):
        _replace_atomically(target, b"[B]\r\n")
    # Второе срабатывание — доказательство переподписки после замены.
    with qtbot.waitSignal(watcher.changed, timeout=3000):
        _replace_atomically(target, b"[C]\r\n")


def test_debounce_merges_bursts(qtbot, tmp_path):
    target = tmp_path / "ibases.v8i"
    target.write_bytes(b"[A]\r\n")
    watcher = FileWatcher(target, debounce_ms=200)
    fired = []
    watcher.changed.connect(lambda: fired.append(1))
    target.write_bytes(b"[B]\r\n")
    target.write_bytes(b"[C]\r\n")
    qtbot.wait(700)
    assert len(fired) == 1
```

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_watcher.py -v`
Expected: FAIL.

- [x] **Step 3: Реализация**

`src/onecstarter/ui/watcher.py`:

```python
"""Слежение за ibases.v8i. Живёт в ui — инвариант 1 (Qt вне ядра запрещён).

Спека 4a, §5: watcher обязан переживать полную перезапись (наша запись и
перезапись платформой — [Ф] скил v8i-format). [Ф] 07.08.2026, замер на Windows +
PySide6/Qt 6.11.1: после os.replace QFileSystemWatcher файл не теряет — Windows-бэкенд
(ReadDirectoryChangesW) следит через каталог и видит изменение. Потеря watch после
замены — известное поведение inotify-бэкенда (Linux). [Д]

Переподписка в _touched — защитная страховка на случай смены бэкенда/версии Qt и для
файла, который не существует при инициализации. Не исправление наблюдаемой потери.

Дребезг (несколько событий на одну перезапись) гасится одноразовым таймером.
"""  # noqa: RUF002

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


class FileWatcher(QObject):
    changed = Signal()

    def __init__(self, path: Path, debounce_ms: int = 200, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._watcher = QFileSystemWatcher(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.changed)
        self._watcher.fileChanged.connect(self._touched)
        self._watcher.directoryChanged.connect(self._touched)
        self._resubscribe()

    def _resubscribe(self) -> None:
        directory = str(self._path.parent)
        if self._path.parent.is_dir() and directory not in self._watcher.directories():
            self._watcher.addPath(directory)
        if self._path.is_file() and str(self._path) not in self._watcher.files():
            self._watcher.addPath(str(self._path))

    def _touched(self, _path: str) -> None:
        self._resubscribe()
        self._timer.start()
```

- [x] **Step 4: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/ui/watcher.py tests/ui/test_watcher.py
git commit -m "feat: watcher файла списка — переживает атомарную замену, гасит дребезг"
```

**Находка ревью 07.08.2026:** [Ф] замер на Windows + PySide6/Qt 6.11.1 показал, что QFileSystemWatcher файл после os.replace не теряет (Windows-бэкенд следит через каталог). Переподписка в `_touched` — защитная страховка на случай смены бэкенда/версии Qt, а не исправление наблюдаемой потери. Мутационный тест (отключение `_resubscribe`) на Windows не валит тесты, что доказано в Task 13 Step 2.

**Известный флак (наблюдался однократно 07.08.2026):** `test_atomic_replace_keeps_watching` в полном прогоне `tests/ui/` может редко падать с `PermissionError: [WinError 5]` на втором быстром `os.replace` — гонка файловых хендлов Windows (антивирус/индексатор), не дефект логики; в изоляции тест стабилен. **Закрыто 07.08.2026** при финальном ревью ветки: флак наблюдался второй раз в полном прогоне, ретрай замены добавлен в тестовый хелпер `_replace_atomically` (не в продукт). Шесть подряд полных прогонов `tests/ui/` после правки — зелёные.

---

### Задача 10. Трей: `ui/tray.py`

Спека §3: сворачивание в трей, запуск избранного из меню.

**Files:**
- Create: `src/onecstarter/ui/tray.py`
- Test: `tests/ui/test_tray.py`

**Interfaces:**
- Consumes: `InfobaseItem`, `theme`.
- Produces (задача 12 потребляет):
  - `make_icon() -> QIcon` — нарисованная иконка (тёмный фон, жёлтый треугольник ▶; без символики 1С)
  - `populate_tray_menu(menu: QMenu, favorites: Sequence[InfobaseItem], on_show: Callable[[], None], on_launch: Callable[[str], None], on_quit: Callable[[], None]) -> None`
    — очищает переданное меню и наполняет заново (Показать / избранное / Выход)
  - `create_tray(window, favorites_provider: Callable[[], list[InfobaseItem]], on_launch, on_quit) -> QSystemTrayIcon | None` — `None`, если системный трей недоступен; держит одно `QMenu` на весь срок жизни трея, наполняет его через `populate_tray_menu` в собственном `aboutToShow`

Важное замечание финального ревью всей ветки (Important): исходная реализация
строила НОВОЕ `QMenu` на каждое открытие (`build_tray_menu(...)`) и подменяла
его через `tray.setContextMenu(menu)`, подключая `aboutToShow` уже нового меню
к той же функции. Qt показывает то меню, что было текущим на момент клика —
т.е. предыдущее, собранное при прошлом открытии: список избранного отставал
на один показ. Дополнительно каждое замещённое `QMenu` не уничтожалось —
утечка по одному объекту на открытие. Фикс: `build_tray_menu` разделена на
`populate_tray_menu` (принимает существующее меню, `menu.clear()` + заново
`addAction`) и `create_tray`, который заводит ОДНО `QMenu`, подключает его
`aboutToShow` к наполнению один раз и вызывает `tray.setContextMenu(menu)`
тоже один раз — не на каждую перестройку.

- [x] **Step 1: Написать тест меню (сам QSystemTrayIcon в offscreen недоступен — его не тестируем)**

`tests/ui/test_tray.py`:

Актуальный листинг (после финального ревью всей ветки): тесты меню строят
собственный `QMenu` и зовут `populate_tray_menu(menu, ...)` вместо прежнего
`build_tray_menu(...) -> QMenu`. Добавлен обязательный тест
`test_menu_refreshes_favorites_on_each_show` — воспроизводит ровно тот
паттерн, что и `create_tray` (одно `QMenu`, `aboutToShow` подключён один раз
к `populate_tray_menu`), меняет список избранного между двумя `aboutToShow.emit()`
и проверяет, что состав действий меняется, а не отстаёт: `create_tray` целиком
через `qtbot` не протестировать — `QSystemTrayIcon.isSystemTrayAvailable()`
под `QT_QPA_PLATFORM=offscreen` всегда `False`, проверено на этой машине.

```python
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QMenu

from onecstarter.config.v8i import parse_v8i
from onecstarter.services.catalog import items_from_document
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui.tray import make_icon, populate_tray_menu

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"


def _favorites() -> list[InfobaseItem]:
    document = parse_v8i(FIXTURE.read_bytes())
    items = items_from_document(document, InfobaseSource.USER, {})
    base1 = next(item for item in items if item.name == "Демо Бухгалтерия")
    base2 = next(item for item in items if item.name == "Демо Розница")
    return [replace(base1, favorite=True), replace(base2, favorite=True)]


def test_menu_lists_show_favorites_and_quit(qtbot):
    launched: list[str] = []
    shown: list[int] = []
    quit_calls: list[int] = []
    menu = QMenu()
    populate_tray_menu(
        menu, _favorites(), lambda: shown.append(1), launched.append, lambda: quit_calls.append(1)
    )
    labels = [action.text() for action in menu.actions() if action.text()]
    assert labels[0] == "Показать"
    assert "Демо Бухгалтерия" in labels
    assert "Демо Розница" in labels
    assert labels[-1] == "Выход"


def test_menu_actions_trigger_callbacks(qtbot):
    launched: list[str] = []
    shown: list[int] = []
    quit_calls: list[int] = []
    menu = QMenu()
    populate_tray_menu(
        menu, _favorites(), lambda: shown.append(1), launched.append, lambda: quit_calls.append(1)
    )
    actions = {action.text(): action for action in menu.actions() if action.text()}
    actions["Показать"].trigger()
    actions["Демо Бухгалтерия"].trigger()
    actions["Демо Розница"].trigger()
    actions["Выход"].trigger()
    assert shown == [1]
    favorites = _favorites()
    assert launched == [favorites[0].key, favorites[1].key]
    assert quit_calls == [1]


def test_icon_is_not_null(qtbot):
    assert not make_icon().isNull()


def test_menu_refreshes_favorites_on_each_show(qtbot):
    # Important-замечание финального ревью: трей держит ОДНО постоянное
    # QMenu и наполняет его заново в собственном aboutToShow (см.
    # create_tray.rebuild_menu). Старая реализация строила новое QMenu на
    # каждое открытие и подменяла его через setContextMenu — Qt в момент
    # показа уже использовал предыдущее меню, так что список избранного
    # отставал на один показ. Здесь тот же паттерн: aboutToShow подключён
    # один раз к одному menu, а провайдер favorites между эмиссиями меняется.
    favorites = _favorites()[:1]
    menu = QMenu()
    menu.aboutToShow.connect(
        lambda: populate_tray_menu(menu, favorites, lambda: None, lambda key: None, lambda: None)
    )

    menu.aboutToShow.emit()
    labels_before = [action.text() for action in menu.actions() if action.text()]
    assert "Демо Бухгалтерия" in labels_before
    assert "Демо Розница" not in labels_before

    favorites.append(_favorites()[1])
    menu.aboutToShow.emit()
    labels_after = [action.text() for action in menu.actions() if action.text()]
    assert "Демо Бухгалтерия" in labels_after
    assert "Демо Розница" in labels_after
```

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_tray.py -v`
Expected: FAIL.

- [x] **Step 3: Реализация**

`src/onecstarter/ui/tray.py`:

```python
"""Трей: поднять окно, запустить избранную базу, выйти.

Иконка рисуется кодом — жёлтый треугольник запуска на тёмном поле.
Символика 1С не используется (requirements.md, §4: без бренда).
"""  # noqa: RUF002

from collections.abc import Callable, Sequence

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from onecstarter.services.model import InfobaseItem
from onecstarter.ui import theme


def make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(theme.SURFACE))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(theme.ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(
        QPolygonF([QPointF(20, 14), QPointF(52, 32), QPointF(20, 50)])
    )
    painter.end()
    return QIcon(pixmap)


def populate_tray_menu(
    menu: QMenu,
    favorites: Sequence[InfobaseItem],
    on_show: Callable[[], None],
    on_launch: Callable[[str], None],
    on_quit: Callable[[], None],
) -> None:
    """Очистить и заново наполнить меню трея: Показать / избранное / Выход.

    Принимает уже существующее меню, а не создаёт новое — трей держит одно
    QMenu на весь срок жизни (см. create_tray) и наполняет его перед каждым
    показом через aboutToShow. Раньше здесь строилось новое QMenu на каждое
    открытие и подменялось через setContextMenu — Qt в момент показа уже
    использовал предыдущее меню (aboutToShow нового срабатывает не раньше
    следующего открытия), так что список избранного отставал на один показ,
    а замещённые QMenu не освобождались (утечка по одному на открытие).
    """  # noqa: RUF002
    menu.clear()
    menu.addAction("Показать", on_show)
    if favorites:
        menu.addSeparator()
        for item in favorites:
            key = item.key
            menu.addAction(item.name, lambda checked=False, key=key: on_launch(key))
    menu.addSeparator()
    menu.addAction("Выход", on_quit)


def create_tray(
    window: QWidget,
    favorites_provider: Callable[[], list[InfobaseItem]],
    on_launch: Callable[[str], None],
    on_quit: Callable[[], None],
) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(make_icon(), window)
    tray.setToolTip("OneCStarter")

    def show_window() -> None:
        show = getattr(window, "show_and_focus_search", window.show)
        show()

    menu = QMenu()

    def rebuild_menu() -> None:
        # Список избранного живой — наполняем перед каждым показом. menu —
        # один и тот же объект на весь срок жизни трея: setContextMenu
        # вызывается один раз ниже, а не на каждую перестройку.
        populate_tray_menu(menu, favorites_provider(), show_window, on_launch, on_quit)

    menu.aboutToShow.connect(rebuild_menu)
    rebuild_menu()
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: show_window()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()
    return tray
```

- [x] **Step 4: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/ui/tray.py tests/ui/test_tray.py
git commit -m "feat: трей — показать окно, запуск избранного, выход; иконка без бренда 1С"
```

---

### Задача 11. Глобальный хоткей: `ui/hotkey.py`

Спека §3: хоткей поднимает окно с фокусом в поиске. Windows API `RegisterHotKey` + `WM_HOTKEY` через нативный фильтр событий; функции user32 инжектируются для тестов.

**Files:**
- Create: `src/onecstarter/ui/hotkey.py`
- Test: `tests/ui/test_hotkey.py`

**Interfaces:**
- Produces (задача 12 потребляет):
  - `GlobalHotkey(callback: Callable[[], None], *, register: Callable[..., int] | None = None, unregister: Callable[..., int] | None = None)`
  - атрибут `registered: bool` — False, если сочетание занято другим приложением (приложение работает дальше без хоткея)
  - `handle(message_id: int, wparam: int) -> bool` — чистая часть, зовёт callback на своём `WM_HOTKEY`
  - `dispose() -> None`
  - Сочетание v1: **Ctrl+Alt+B** (константы `MODIFIERS`, `VK_B`); настройка сочетания — вне 4a ([Р])

- [x] **Step 1: Написать тесты**

`tests/ui/test_hotkey.py`:

```python
from onecstarter.ui.hotkey import HOTKEY_ID, WM_HOTKEY, GlobalHotkey


def _hotkey(register_result=1):
    calls = {"register": [], "unregister": []}

    def register(hwnd, hotkey_id, modifiers, vk):
        calls["register"].append((hotkey_id, modifiers, vk))
        return register_result

    def unregister(hwnd, hotkey_id):
        calls["unregister"].append(hotkey_id)
        return 1

    fired = []
    hotkey = GlobalHotkey(lambda: fired.append(1), register=register, unregister=unregister)
    return hotkey, calls, fired


def test_registration_success_and_dispatch():
    hotkey, calls, fired = _hotkey()
    assert hotkey.registered
    assert calls["register"][0][0] == HOTKEY_ID
    assert hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == [1]


def test_foreign_messages_are_ignored():
    hotkey, _, fired = _hotkey()
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID + 1)
    assert not hotkey.handle(0x0400, HOTKEY_ID)
    assert fired == []


def test_busy_hotkey_does_not_break_startup():
    hotkey, _, fired = _hotkey(register_result=0)
    assert not hotkey.registered
    # Сообщение всё равно не наше — колбэк не дёргается.
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == []


def test_dispose_unregisters_only_when_registered():
    hotkey, calls, _ = _hotkey()
    hotkey.dispose()
    assert calls["unregister"] == [HOTKEY_ID]
    busy, busy_calls, _ = _hotkey(register_result=0)
    busy.dispose()
    assert busy_calls["unregister"] == []
```

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_hotkey.py -v`
Expected: FAIL.

- [x] **Step 3: Реализация**

`src/onecstarter/ui/hotkey.py`:

```python
"""Глобальный хоткей Ctrl+Alt+B: поднять окно с фокусом в поиске.

Windows-only (v1 — только Windows, requirements.md §4): RegisterHotKey +
WM_HOTKEY через QAbstractNativeEventFilter. Функции user32 инжектируются —
тесты не трогают реальную регистрацию. Занятое сочетание не роняет
приложение: registered=False, всё остальное работает ([Р] спека 4a, §3).
"""  # noqa: RUF002

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MODIFIERS = MOD_CONTROL | MOD_ALT
VK_B = 0x42
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xA11C


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(
        self,
        callback: Callable[[], None],
        *,
        register: Callable[..., int] | None = None,
        unregister: Callable[..., int] | None = None,
    ) -> None:
        super().__init__()
        self._callback = callback
        if register is None or unregister is None:
            user32 = ctypes.windll.user32
            register = user32.RegisterHotKey
            unregister = user32.UnregisterHotKey
        self._unregister = unregister
        self.registered = bool(register(None, HOTKEY_ID, MODIFIERS, VK_B))

    def handle(self, message_id: int, wparam: int) -> bool:
        """Чистая часть диспетчеризации — тестируется без нативных событий."""
        if not self.registered:
            return False
        if message_id == WM_HOTKEY and wparam == HOTKEY_ID:
            self._callback()
            return True
        return False

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if self.handle(msg.message, msg.wParam):
                return True, 0
        return False, 0

    def dispose(self) -> None:
        if self.registered:
            self._unregister(None, HOTKEY_ID)
            self.registered = False
```

- [x] **Step 4: Прогнать и статика**

Run: `uv run pytest tests/ui/ -v && uv run ruff check . && uv run mypy`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/ui/hotkey.py tests/ui/test_hotkey.py
git commit -m "feat: глобальный хоткей Ctrl+Alt+B через RegisterHotKey, занятость не роняет запуск"
```

---

### Задача 12. Сборка приложения: `ui/app.py` и `__main__.py`

Всё в одно целое: окружение → `Workspace` → окно + watcher + трей + хоткей. Точка входа уже объявлена в `pyproject.toml` (`onecstarter.__main__:main`) — файла пока нет.

**Files:**
- Create: `src/onecstarter/ui/app.py`
- Create: `src/onecstarter/__main__.py`
- Test: `tests/ui/test_app.py`

**Interfaces:**
- Consumes: всё из задач 5–11; `load_conventions`, `find_installations`, `cfg_paths`, `parse_cestart_cfg`, `default_version_rules`, `Workspace`, `WorkspacePaths`, `UserDataUnavailableError`.
- Produces:
  - `app.build_runtime(env: Mapping[str, str]) -> Runtime` — frozen dataclass `Runtime(workspace: Workspace, installations: list[Installation], cfg_rules: list[DefaultVersionRule])`
  - `app.main(argv: list[str] | None = None) -> int`
  - `onecstarter.__main__.main` — реэкспорт

- [x] **Step 1: Написать тест сборки окружения**

`tests/ui/test_app.py`:

```python
from onecstarter.ui.app import build_runtime


def test_runtime_builds_on_empty_machine(tmp_path):
    # Пустое окружение: ни платформы, ни файлов — приложение всё равно
    # обязано собраться (пустой список, ошибок нет).
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)
    assert runtime.workspace.items() == []
    assert runtime.installations == []
    assert runtime.cfg_rules == []


def test_runtime_reads_ibases_and_cfg(tmp_path):
    appdata = tmp_path / "appdata"
    start = appdata / "1C" / "1CEStart"
    start.mkdir(parents=True)
    (start / "ibases.v8i").write_bytes('[База]\r\nConnect=File="C:\\B";\r\n'.encode())
    import codecs

    (start / "1cestart.cfg").write_bytes(
        codecs.BOM_UTF16_LE + "DefaultVersion=8.3-8.3.22.1923\r\n".encode("utf-16-le")
    )
    runtime = build_runtime({"APPDATA": str(appdata)})
    assert [item.name for item in runtime.workspace.items()] == ["База"]
    assert len(runtime.cfg_rules) == 1
```

- [x] **Step 2: Прогнать — падает на импорте**

Run: `uv run pytest tests/ui/test_app.py -v`
Expected: FAIL.

- [x] **Step 3: Реализация**

`src/onecstarter/ui/app.py`:

```python
"""Сборка приложения: окружение → Workspace → окно, трей, хоткей, watcher.

Единственное место, где ui знает про расположение файлов и обнаружение
платформы. default_app в v1 не читается из cfg: существование параметра App
уровня 1cestart.cfg экспериментально не подтверждено — None, клиент
выбирается по App секции либо тонкий ([Ф] T-02.6).
"""  # noqa: RUF002

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from onecstarter.config.cestart_cfg import parse_cestart_cfg
from onecstarter.domain.default_version import DefaultVersionRule, default_version_rules
from onecstarter.domain.version import Installation
from onecstarter.platform_1c.discovery import cfg_paths, find_installations
from onecstarter.platform_1c.registry import load_conventions
from onecstarter.services.errors import UserDataUnavailableError
from onecstarter.services.workspace import Workspace, WorkspacePaths
from onecstarter.ui import theme
from onecstarter.ui.bases.view import BasesView
from onecstarter.ui.hotkey import GlobalHotkey
from onecstarter.ui.shell import MainWindow
from onecstarter.ui.tray import create_tray
from onecstarter.ui.watcher import FileWatcher


@dataclass(frozen=True)
class Runtime:
    workspace: Workspace
    installations: list[Installation]
    cfg_rules: list[DefaultVersionRule]


def build_runtime(env: Mapping[str, str]) -> Runtime:
    conventions = load_conventions()
    installations = find_installations(env, conventions)
    cfgs = cfg_paths(env)
    entries: list[tuple[str, str]] = []
    for cfg in cfgs:
        try:
            entries.extend(parse_cestart_cfg(cfg.read_bytes()))
        except OSError:
            continue
    rules = default_version_rules(entries)
    appdata = Path(env.get("APPDATA", "."))
    paths = WorkspacePaths(
        ibases=appdata / "1C" / "1CEStart" / "ibases.v8i",
        user_data=appdata / "OneCStarter" / "bases.json",
        cfg_paths=tuple(cfgs),
    )
    workspace = Workspace(
        paths,
        installations=installations,
        conventions=conventions,
        cfg_rules=rules,
        default_app=None,
    )
    return Runtime(workspace, installations, rules)


def main(argv: list[str] | None = None) -> int:
    application = QApplication(argv if argv is not None else sys.argv)
    application.setApplicationName("OneCStarter")
    application.setStyleSheet(theme.STYLESHEET)
    try:
        runtime = build_runtime(os.environ)
    except UserDataUnavailableError as error:
        # Молча подменить данные пустыми нельзя — затрётся живая история
        # (докстринг Workspace). Сообщение с путём, не трассировка.
        QMessageBox.critical(None, "OneCStarter", str(error))
        return 1
    except OSError as error:
        # Список баз нечитаем по-настоящему: нет прав, недоступен сетевой
        # профиль. Гонку с перезаписью платформой гасит reload_if_changed,
        # сюда доходит только устойчивый отказ. Стартовать с пустым списком
        # нельзя — пользователь решит, что базы пропали.
        QMessageBox.critical(
            None, "OneCStarter", f"Не удалось прочитать список баз: {error}"
        )
        return 1

    view = BasesView(
        runtime.workspace,
        installations=runtime.installations,
        cfg_rules=runtime.cfg_rules,
    )
    window = MainWindow(view)

    watcher = FileWatcher(runtime.workspace.paths.ibases, parent=window)

    def on_file_changed() -> None:
        if runtime.workspace.reload_if_changed():
            view.rebuild()

    watcher.changed.connect(on_file_changed)

    def favorites() -> list:
        return [
            item
            for item in runtime.workspace.items()
            if not item.is_group and item.favorite
        ]

    tray = create_tray(window, favorites, view.launch_key, application.quit)
    window.close_to_tray = tray is not None

    hotkey = GlobalHotkey(window.show_and_focus_search)
    if hotkey.registered:
        application.installNativeEventFilter(hotkey)
        if tray is not None:
            tray.setToolTip("OneCStarter — Ctrl+Alt+B")
    elif tray is not None:
        tray.setToolTip("OneCStarter — хоткей Ctrl+Alt+B занят другим приложением")
    application.aboutToQuit.connect(hotkey.dispose)

    window.show()
    return application.exec()
```

`src/onecstarter/__main__.py`:

```python
"""Точка входа gui-скрипта onecstarter (pyproject: onecstarter.__main__:main)."""

from onecstarter.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Прогнать всё и статику**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS. `test_no_qt_in_core` обязан остаться зелёным: `__main__.py` импортирует ui, но сам лежит вне ядра — если тест сочтёт иначе, обсуждать, а не ослаблять тест.

- [x] **Step 5: Commit**

```bash
git add src/onecstarter/ui/app.py src/onecstarter/__main__.py tests/ui/test_app.py
git commit -m "feat: сборка приложения — окружение, окно, watcher, трей, хоткей, точка входа"
```

---

### Задача 13. Финальная верификация плана

**Files:**
- Modify: `docs/tasks.md` (статус T-04.5a)

- [x] **Step 1: Полный прогон**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: всё зелёное; количество тестов заметно выросло относительно 372.

- [x] **Step 2: Мутационная проверка защитных тестов (правило CLAUDe.md)**

Для каждой пары «сломать → увидеть падение → откатить», результат записать в отчёт задачи:

1. **Переподписка watcher'а**: на Linux — в `ui/watcher.py` убрать вызов `self._resubscribe()` из `_touched`, ожидание: `test_atomic_replace_keeps_watching` падает на втором `waitSignal` (timeout). На Windows эта мутация не валит тесты ([Ф] 07.08.2026: бэкенд не теряет файл после os.replace), проверка исключена; вместо неё — примечание в конце Task 9. Откатить.
2. **Обёртка ошибки spawn**: в `services/launch.py` вернуть голый `pid = spawn(command)` без try/except. Ожидание: `test_spawn_failure_becomes_launch_error_with_command_line` падает — `OSError` вместо `LaunchError`. Откатить.
3. **Запрет запуска группы**: в `ui/bases/view.py` в `_launch_index` убрать проверку `KIND_ROLE != RowKind.BASE.value`. Ожидание: `test_activating_group_row_does_not_launch` падает на `assert errors == []` — запуск группы даёт `LaunchError` («группа, а не информационная база») в обработчик. Откатить.
4. **Обработка ServicesError вместо трассировки**: в `launch_key` убрать `except ServicesError`. Ожидание: `test_launch_error_goes_to_handler_not_up` падает с непойманным `LaunchError`. Откатить.

**Отчёт (проведено 07.08.2026 при финальном ревью ветки).** Каждая мутация
вносилась в чистое дерево, прогонялся адресный тест, мутация откатывалась
`git checkout --`; чистота дерева проверялась `git status` после каждого шага.

| # | Мутация | Тест | Факт |
| --- | --- | --- | --- |
| 1 | убрать `_resubscribe()` из `_touched` | `test_atomic_replace_keeps_watching` | **не валит** на Windows — [Ф] бэкенд не теряет файл после `os.replace`; проверка исключена, см. примечание Task 9 |
| 2 | голый `pid = spawn(command)` | `test_spawn_failure_becomes_launch_error_with_command_line` | **упал**: `OSError` вместо `LaunchError` |
| 3 | убрать guard `KIND_ROLE != BASE` в `_launch_index` | `test_activating_group_row_does_not_launch` | **упал** на `assert errors == []` — запуск группы дал `LaunchError` |
| 4 | убрать `except ServicesError` в `launch_key` | `test_launch_error_goes_to_handler_not_up` | **упал** непойманным `LaunchError` |

Защитные тесты задачи 14 проверены тем же способом:

| # | Мутация | Тест | Факт |
| --- | --- | --- | --- |
| 5 | снимок развёрнутости снимается всегда (убрать `if not self._filtered`) | `test_collapsed_state_survives_a_search_cycle`, `test_expansion_made_during_search_is_not_remembered` | **упали оба** |
| 6 | маркер узла из одной метки, без пути | `test_same_label_nodes_expand_independently` | **упал** |
| 7 | `row_label` не добавляет `BROKEN_SUFFIX` | `test_broken_record_label_is_visibly_marked`, `test_broken_record_is_marked_in_label_and_colour` | **упали оба** |
| 8 | битая запись не подсвечивается в `tree_model` | `test_broken_record_is_marked_in_label_and_colour` | **упал** |
| 9 | убрать `except OSError` в `reload_if_changed` | `test_reload_survives_unreadable_file` | **упал** непойманным `PermissionError` |

Ловушка, стоившая одного повтора: мутацию нельзя откатывать `git checkout --`,
пока сама правка не закоммичена — откатывается и она. Правка → коммит → мутация.

- [x] **Step 3: Ручной smoke на машине заказчика**

`uv run onecstarter` — проверить глазами: окно в тёмной теме; дерево реального `ibases.v8i` с группами; «Нет такой группы»-подобные неявные узлы, если есть; фильтр по 2–3 буквам; колонка версий с подсветкой; трей и Ctrl+Alt+B. **Запуск реальной базы — только по желанию заказчика** (правило CLAUDE.md: процессы 1С — по явной просьбе). Окно закрыть — приложение остаётся в трее; выход — из меню трея.

**Проведён 07.08.2026 заказчиком.** Окружение: 7 установленных версий платформы,
64 записи, 6 групп, ошибок чтения общих списков нет.

| Проверка | Результат |
| --- | --- |
| окно, тёмная тема, дерево реального `ibases.v8i` с группами | пройдено |
| фильтр по 2–3 буквам, затем очистка поиска | работает — подтверждает правку задачи 14 (свёрнутость возвращается) |
| колонка версий | есть |
| трей, закрытие окна в трей | есть |
| глобальный хоткей `Ctrl+Alt+B` | проверен 07.08.2026: свёрнутое в трей окно открывается сочетанием |
| запуск реальной базы | не проводился (правило CLAUDE.md) |

Найден дефект показа контекстного меню — задача 15. Остальные замечания
заказчика (значок вида размещения, панель строки соединения, диагностика
молчаливого отказа старта) — вне объёма 4a, разнесены по спеке §9.

- [x] **Step 4: Обновить tasks.md**

В строке T-04.5a: статус → `DONE (реализация)`, добавить ссылку на этот план. Формулировку сверить с фактом (если ревью ещё впереди — статус `WIP`, ревью).

- [x] **Step 5: Commit и финальное ревью**

```bash
git add docs/tasks.md
git commit -m "docs: план 4a выполнен — раздел Базы: просмотр и запуск"
```

Дальше — финальное ревью всей ветки на самой сильной модели (процесс проекта), замечания — через superpowers:receiving-code-review. Слияние ветки — после ревью и подтверждения заказчика.

---

### Задача 14. Правки по финальному ревью ветки (07.08.2026)

Ревью всей ветки на самой сильной модели. Критических находок нет; закрыты три
поведенческих дефекта и один процессный долг. Листинги задач 3, 6, 8, 9 и 12 выше
**исправлены вслед за кодом** (правило CLAUDE.md: документ, разошедшийся с кодом,
врёт следующему исполнителю) — здесь только то, чего не было ни в одной задаче.

Что нашло ревью и почему это дефект:

1. **Свёрнутость дерева терялась навсегда после первого поиска.** `expandAll()`
   на время фильтра попадал в слепок развёрнутости, и возврат к пустому поиску
   восстанавливал «развёрнуто всё». Целевой сценарий (§3 спеки) прогоняет через
   поиск каждый запуск — дефект срабатывал в первую минуту. Правка в задаче 8.
2. **Маркер узла без ключа строился из одной метки** — одноимённые узлы на разных
   ветках разворачивались вместе. Правка в задаче 8.
3. **`parse_error` показывался только тултипом**, визуальной пометки не было,
   тестов показа не было ни одного — при том, что §2 спеки требует пометку
   «не разобрано», а раздел рассчитан на работу без мыши. Правка в задачах 3 и 6:
   пометки метки вынесены в чистую `display.row_label`, Qt-слой только рисует.
4. **Отказ чтения списка не обрабатывался.** См. ниже — правка в `services`,
   вне задач этого плана.
5. **Процессный долг**: 67 чекбоксов не проставлены при выполненном плане,
   мутационная проверка Task 13 Step 2 без письменного отчёта. Закрыто.

**Files:**
- Modify: `src/onecstarter/services/workspace.py`
- Modify: `tests/unit/test_workspace.py`

- [x] **Step 1: Тест на отказ чтения**

```python
def test_reload_survives_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Отказ чтения — не изменение: состояние прежнее, попытка повторяема.

    Штатный стартер перезаписывает `ibases.v8i` целиком, и на Windows чтение
    в этот момент может упасть отказом доступа. `reload_if_changed` зовёт
    watcher из Qt-слота: исключение оттуда пользователю не показывается
    (в оконной сборке консоли нет), поэтому отказ обязан быть тихим
    и обратимым, а не терять список и не ронять обновление навсегда.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    before = workspace.items()
    path = workspace.paths.ibases
    path.write_bytes(path.read_bytes() + '[Чужая]\r\nConnect=File="C:\B";\r\n'.encode())
    original = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self == path:
            raise PermissionError(13, "файл занят другим процессом")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    assert not workspace.reload_if_changed()
    assert workspace.items() == before

    # Файл освободился — следующее событие watcher'а подхватывает правку.
    monkeypatch.undo()
    assert workspace.reload_if_changed()
    assert len(workspace.items()) == len(before) + 1
```

- [x] **Step 2: Реализация**

`Workspace.reload_if_changed` перестаёт звать `_reload()` и обрабатывает отказ сам.
Конструктор остаётся строгим: там ошибка чтения означает не гонку с перезаписью,
а нерабочее окружение, и её показывает `ui/app.py` (задача 12).

```python
    def reload_if_changed(self) -> bool:
        """Перечитать файл, если он изменился. `False` — перечитывать нечего.

        Отказ чтения тоже даёт `False`: штатный стартер перезаписывает файл
        целиком, и на Windows чтение в этот момент может упасть отказом
        доступа. Вызывает этот метод watcher из Qt-слота, где исключение
        пользователю не показывается (в оконной сборке консоли нет), поэтому
        отказ обязан быть тихим и обратимым — состояние остаётся прежним,
        а следующее событие watcher'а повторит попытку.

        Ошибка чтения при построении (конструктор) не гасится: там она
        означает не гонку с перезаписью, а нерабочее окружение.
        """  # noqa: RUF002
        try:
            payload = self._read_bytes()
        except OSError:
            return False
        if payload == self._raw:
            return False
        self._raw = payload
        self._rebuild()
        return True
```

- [x] **Step 3: Прогон и мутационная проверка**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Факт: 447 тестов зелёные (было 436), ruff и mypy чистые. Мутации 5–9 — в отчёте
Task 13 Step 2.

**Осталось незакрытым (осознанно):**

- Ветка `except OSError` в `main()` (задача 12) тестом не покрыта — как и соседняя
  `except UserDataUnavailableError`: обе требуют модального `QMessageBox`.
  Покрывается ручным smoke.
- `nativeEventFilter` в `ui/hotkey.py` не покрыт: нативные сообщения в offscreen
  не подделать. Чистая часть `handle()` покрыта. Риск — молчаливая поломка при
  смене мажорной версии PySide6.
- Сообщение `UnknownItemError` («Записи с таким ключом нет в списке») не предлагает
  обновить список, хотя §3 спеки это обещает. Мелочь, оставлена на 4b — там же
  будут остальные тексты операций.

---

### Задача 15. Контекстное меню базы отрисовано скомканно (ручной smoke 07.08.2026)

Спека 4a, §9 п. 1. Дефект показа, найденный заказчиком при первом запуске
на рабочей машине. Механику запуска не затрагивает.

**Симптом [Ф], Windows 11, 07.08.2026** (скриншот заказчика): в контекстном меню
базы подсказка сочетания налезает на название пункта — «Тонкий клиенCtrl+1»,
«Толстый клиенCtrl+2», «КонфигураторCtrl+3». Меню на скриншоте ~151 px шириной.

**Что уже измерено [Ф] 07.08.2026** — и почему очевидная правка не годится:
offscreen дефект не воспроизводится **ни в одном** из четырёх доступных стилей.
`sizeHint().width()` меню с теми же пятью пунктами:

| стиль | без QSS | тема проекта | тема + `padding` у `QMenu::item` |
| --- | --- | --- | --- |
| windows11 | 267 | 282 | 316 |
| windowsvista | 298 | 313 | 316 |
| Windows | 297 | 315 | 318 |
| Fusion | 363 | 391 | 316 |

Ширины хватает везде. Значит «добавить `padding` в QSS» — догадка, а не лекарство,
и вносить её вслепую нельзя (CLAUDE.md: не выдавать догадку за факт).

**Files:**
- Modify: `src/onecstarter/ui/bases/view.py` (`_build_menu`) и/или `src/onecstarter/ui/theme.py` — по итогу диагностики
- Test: `tests/ui/test_bases_view.py`

- [ ] **Step 1: Снять причину на реальном экране (сессия с заказчиком)**

Меню показывается на настоящем экране, не offscreen. Замерить и записать сюда:

1. фактическая ширина меню (`menu.sizeHint()` и `menu.width()` после показа)
   и `QApplication.style().objectName()` на машине заказчика;
2. масштаб экрана: `QGuiApplication.primaryScreen().devicePixelRatio()`
   и `logicalDotsPerInch()` — если не 100 %, это отдельная гипотеза;
3. то же меню, собранное через `QAction.setShortcut()` вместо табуляции в тексте:
   меняется ли отрисовка;
4. то же меню без темы (`app.setStyleSheet("")`): меняется ли отрисовка.

Пары 3 и 4 разделяют три кандидата из §9 спеки. Без этих четырёх замеров
к правке не переходить.

- [ ] **Step 2: Правка по снятой причине**

Если причина — табуляция: заменить `"Тонкий клиент\tCtrl+1"` на `menu.addAction("Тонкий клиент")`
+ `action.setShortcut(QKeySequence("Ctrl+1"))`. Тогда сочетание рисует Qt,
а не наш текст, и заодно исчезает дублирование текста и `QShortcut`.
Если причина — стилизация `QMenu::item`: явный `padding` в теме.
Если масштабирование — правка выходит за меню и требует отдельного решения по всей теме.

- [ ] **Step 3: Тест**

Offscreen дефект не воспроизводится, поэтому тест на ширину бессмыслен —
он был бы зелёным и до правки. Проверяемое утверждение выбрать по итогу Step 2:
при замене на `setShortcut` — что у действий меню выставлен `shortcut()`
и в `text()` нет табуляции. Это не «тест на дефект», а страховка от отката правки;
записать в тесте прямо, что показ проверяется глазами.

- [ ] **Step 4: Повторный smoke на машине заказчика**

Единственная настоящая проверка этого дефекта.
