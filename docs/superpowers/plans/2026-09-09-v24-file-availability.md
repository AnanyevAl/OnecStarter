# Метка отсутствующего каталога у файловых баз — план реализации v2.4

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** файловая база, каталога которой нет на диске, отличима в списке без наведения мыши и без попытки запуска.

**Architecture:** доступность считается в новом чистом модуле `services/availability.py` (обращение к ФС подаётся аргументом), обходится демон-потоком в `ui/background.py`, накапливается во вьюхе по нормализованному ключу пути и попадает в модель дерева отдельным отображением — рядом с `cells`, тем же приёмом, каким уже носится колонка версии. Метка двойная: крестик на значке размещения и суффикс `(нет каталога)` в метке строки.

**Tech Stack:** Python 3.13, PySide6 (Qt 6.11), pytest + pytest-qt, ruff, mypy strict.

Спека — [2026-09-09-v24-file-availability-design.md](../specs/2026-09-09-v24-file-availability-design.md).
Базовая точка — ветка `feat/2026-09-09-v24-file-availability`, коммит `891803b`
(v2.3 закрыта, 1962 теста зелёные).

## Global Constraints

- **Инвариант 1.** `PySide6` не импортируется из `domain`, `config`, `platform_1c`,
  `security`, `services` — ни прямо, ни транзитивно. Новый модуль ядра обязан
  появиться строкой в `CORE` внутри `tests/unit/test_no_qt_in_core.py`, иначе
  сторож пройдёт зелёным мимо него.
- **Инвариант 2.** Решение о доступности — чистая функция: обращения к ФС внутри
  нет, `stat` подаётся аргументом.
- **Инвариант 5.** Ни путь, ни имя базы не попадают в лог. В лог — только счётчики
  и длительности (докстринг `ui/background.py`).
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` — все три обязаны быть
  зелёными перед каждым коммитом. `mypy` в режиме `strict` для всего, кроме
  `onecstarter.ui.*`.
- Полный прогон pytest — **в файл**, не в `tail`: `uv run pytest -q > e:/tmp/<имя>.log 2>&1`.
  Интермиттентный `access violation` pytest-qt (T-12 п. 15) иначе теряет блок падения.
- Имя `1Cv8.1CD` живёт ровно в одном месте — `DB_FILE_NAME` в `services/availability.py`.
- Сообщения коммитов — по-русски, в стиле репозитория (`feat(ui): …`, `test(services): …`).
  Строк атрибуции не добавлять.
- Тексты в UI — по-русски. Суффикс метки — ровно `(нет каталога)`, подсказка —
  ровно `Каталог не найден: <путь>`, подсказка относительного пути — ровно
  `Путь относительный — доступность не проверялась`.

---

### Task 1: Замер T-05.17 — состав каталога файловой ИБ

**Выполняет заказчик на своей машине.** Агент 1С не запускает (граница в `CLAUDE.md`).
Задача блокирует Task 3 и только её: Task 2 и Tasks 4–6 от неё не зависят.

**Files:**

- Create: `docs/research/t05-17-file-infobase-directory.md`
- Modify: `.claude/skills/v8i-format/reference.md` (раздел с наблюдениями на реальном файле)
- Modify: `docs/tasks.md` (строка замера T-05.17)

**Interfaces:**

- Consumes: ничего.
- Produces: подтверждённое имя файла базы данных для константы `DB_FILE_NAME`
  в Task 3 и уровень достоверности **[Ф]** вместо **[Д]**.

- [ ] **Step 1: Снять состав каталога свежесозданной файловой базы**

Создать пустую файловую базу штатным способом, затем:

```powershell
Get-ChildItem "<каталог новой базы>" -Force | Select-Object Name, Length | Format-Table
```

Записать полный список имён **с точным регистром**.

- [ ] **Step 2: Снять состав каталога рабочей базы**

Тот же вызов на каталоге базы, которой пользуются. Цель — убедиться, что файл
базы данных присутствует и в рабочем каталоге, а не только в свежесозданном.

- [ ] **Step 3: Проверить каталог с удалённым файлом базы**

Скопировать каталог базы в сторону, удалить из копии файл базы данных, попробовать
запустить копию штатным стартером. Записать дословно, что скажет платформа.

- [ ] **Step 4: Записать результат**

Создать `docs/research/t05-17-file-infobase-directory.md` по образцу соседних
файлов `docs/research/`: дата, машина, версия платформы, дословные выводы,
пометка **[Ф]** у каждого. Обязательно зафиксировать:

1. точное имя и регистр файла базы данных;
2. присутствует ли он в каталоге и свежей, и рабочей базы;
3. поведение платформы на каталоге без него.

- [ ] **Step 5: Вернуть факт в скил**

Дописать факт в `.claude/skills/v8i-format/reference.md` со ссылкой на замер.
Скил, разошедшийся с реальностью, хуже отсутствующего (`CLAUDE.md`).

- [ ] **Step 6: Commit**

```bash
git add docs/research/t05-17-file-infobase-directory.md .claude/skills/v8i-format/reference.md docs/tasks.md
git commit -m "docs: замер T-05.17 — состав каталога файловой ИБ"
```

**Если замер показал имя, отличное от `1Cv8.1CD`** — Task 3 берёт имя из замера.
**Если замер показал, что единого имени нет** — остановиться и обсудить с заказчиком:
проверка §2 спеки в этом случае неисполнима и правится спека, а не подгоняется код.

---

### Task 2: `services/availability.py` — выборка целей проверки

**Files:**

- Create: `src/onecstarter/services/availability.py`
- Create: `tests/unit/test_availability.py`
- Modify: `tests/unit/test_no_qt_in_core.py:8-39` (кортеж `CORE`)

**Interfaces:**

- Consumes: `InfobaseItem` из `onecstarter.services.model`; `ConnectKind`,
  `find_fragment`, `parse_connect` из `onecstarter.domain.connect`.
- Produces:
  - `class Availability(Enum)` со значениями `UNKNOWN`, `PRESENT`, `MISSING`;
  - `@dataclass(frozen=True) class ProbeTarget` с полями `key: str`, `path: str`;
  - `path_key(value: str) -> str`;
  - `file_path_of(item: InfobaseItem) -> str | None`;
  - `probe_targets(items: Iterable[InfobaseItem]) -> dict[str, ProbeTarget]`
    (ключ словаря — `item.key`);
  - `relative_path_note(item: InfobaseItem) -> str | None`;
  - `availability_hint(state: Availability, path: str) -> str | None`.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_availability.py`:

```python
"""Выборка целей проверки доступности: что проверяем и что нет (спека §2)."""

import pytest

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.availability import (
    Availability,
    ProbeTarget,
    availability_hint,
    file_path_of,
    path_key,
    probe_targets,
    relative_path_note,
)
from onecstarter.services.model import InfobaseItem, InfobaseSource


def _item(
    key: str = "id:a",
    connect: str | None = r'File="D:\bases\acc";',
    kind: ConnectKind = ConnectKind.FILE,
    is_group: bool = False,
) -> InfobaseItem:
    return InfobaseItem(
        key=key,
        name="База",
        folder="/",
        is_group=is_group,
        connect=connect,
        kind=kind,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id=None,
    )


def test_file_base_with_absolute_path_is_a_target() -> None:
    targets = probe_targets([_item()])
    assert targets == {"id:a": ProbeTarget(path_key(r"D:\bases\acc"), r"D:\bases\acc")}


def test_unc_path_is_a_target_too() -> None:
    """UNC абсолютен по `Path.is_absolute()` и проверяется наравне с локальным (спека §2)."""
    item = _item(connect=r'File="\\srv\share\acc";')
    assert list(probe_targets([item])) == ["id:a"]


@pytest.mark.parametrize(
    "kind",
    [ConnectKind.SERVER, ConnectKind.WEB, ConnectKind.UNKNOWN],
)
def test_non_file_kinds_are_not_targets(kind: ConnectKind) -> None:
    assert probe_targets([_item(kind=kind)]) == {}


def test_group_is_not_a_target() -> None:
    assert probe_targets([_item(connect=None, is_group=True)]) == {}


def test_empty_file_fragment_is_not_a_target() -> None:
    assert probe_targets([_item(connect='File="";')]) == {}


def test_relative_path_is_not_a_target() -> None:
    """Относительно чего платформа его разрешает — [Д], замера нет (спека §2)."""
    assert probe_targets([_item(connect='File="bases\\acc";')]) == {}


def test_drive_relative_path_is_not_a_target() -> None:
    """`D:база` — относительный от текущего каталога диска, не абсолютный."""
    assert probe_targets([_item(connect='File="D:acc";')]) == {}


def test_two_bases_in_one_directory_share_one_path_key() -> None:
    first = _item(key="id:a", connect=r'File="D:\bases\acc";')
    second = _item(key="id:b", connect=r'File="d:/BASES/acc";')
    targets = probe_targets([first, second])
    assert targets["id:a"].key == targets["id:b"].key


def test_file_path_of_returns_none_for_non_file_records() -> None:
    assert file_path_of(_item(kind=ConnectKind.SERVER)) is None
    assert file_path_of(_item(connect=None, is_group=True)) is None


def test_relative_path_note_only_for_relative_file_records() -> None:
    assert relative_path_note(_item(connect='File="bases\\acc";')) == (
        "Путь относительный — доступность не проверялась"
    )
    assert relative_path_note(_item()) is None
    assert relative_path_note(_item(kind=ConnectKind.SERVER)) is None


def test_availability_hint_speaks_only_about_missing() -> None:
    assert availability_hint(Availability.MISSING, r"D:\b") == r"Каталог не найден: D:\b"
    assert availability_hint(Availability.PRESENT, r"D:\b") is None
    assert availability_hint(Availability.UNKNOWN, r"D:\b") is None
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/unit/test_availability.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.availability'`

- [ ] **Step 3: Написать модуль**

Создать `src/onecstarter/services/availability.py`:

```python
"""Доступность каталога файловой базы — чистая логика, без Qt и без ФС внутри.

Инвариант 1: модуль не импортирует PySide6. Инвариант 2: решение о доступности
принимается по данным, поданным аргументами, — обращение к файловой системе
(`stat`) подаётся вызывающим, поэтому вся таблица случаев проверяется без диска.

Проверяются только файловые записи с абсолютным путём. Относительный путь
в `File=` не разрешается: относительно чего это делает платформа — [Д],
замера нет, а разрешить его относительно каталога `ibases.v8i` было бы
догадкой, выданной за факт (спека §2).

Спека — docs/superpowers/specs/2026-09-09-v24-file-availability-design.md.
"""  # noqa: RUF002

import os
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from onecstarter.domain.connect import ConnectKind, find_fragment, parse_connect
from onecstarter.services.model import InfobaseItem

RELATIVE_NOTE = "Путь относительный — доступность не проверялась"


class Availability(Enum):
    """Три состояния во времени, два в исходе (спека §1).

    `UNKNOWN` — не «не удалось проверить», а «ещё не проверяли»: пока фоновый
    проход идёт, крестика нет. Тот же приём, что `«…»` в колонке версии, пока
    не закончилось обнаружение платформ (спека T-04.6 §3.4). Без него весь
    список на старте на мгновение становился бы битым.
    """  # noqa: RUF002

    UNKNOWN = "unknown"
    PRESENT = "present"
    MISSING = "missing"


@dataclass(frozen=True)
class ProbeTarget:
    """Что и под каким ключом проверять.

    `key` — нормализованный путь, по нему снимаются дубли и хранится результат.
    `path` — исходное значение `File=` из файла: `stat` зовётся именно на нём,
    чтобы проверить ровно то, что откроет платформа, а не результат нашей
    нормализации.
    """  # noqa: RUF002

    key: str
    path: str


def path_key(value: str) -> str:
    """Ключ пути для сравнения и дедупликации.

    `normcase` на Windows приводит регистр и разделители к одному виду,
    `normpath` схлопывает `.` и `..`. Только ключ — не адрес для `stat`.
    """
    return os.path.normcase(os.path.normpath(value))


def file_path_of(item: InfobaseItem) -> str | None:
    """Значение `File=` файловой записи; `None` — проверять нечего."""
    if item.is_group or item.kind is not ConnectKind.FILE or not item.connect:
        return None
    value = find_fragment(parse_connect(item.connect), "File")
    return value or None


def probe_targets(items: Iterable[InfobaseItem]) -> dict[str, ProbeTarget]:
    """Ключ записи → цель проверки. К файловой системе не обращается."""
    targets: dict[str, ProbeTarget] = {}
    for item in items:
        value = file_path_of(item)
        if value is None or not Path(value).is_absolute():
            continue
        targets[item.key] = ProbeTarget(path_key(value), value)
    return targets


def relative_path_note(item: InfobaseItem) -> str | None:
    """Почему запись не проверялась, если причина — относительный путь."""
    value = file_path_of(item)
    if value is None or Path(value).is_absolute():
        return None
    return RELATIVE_NOTE


def availability_hint(state: Availability, path: str) -> str | None:
    """Строка подсказки о доступности; `None` — говорить нечего."""
    if state is Availability.MISSING:
        return f"Каталог не найден: {path}"
    return None
```

- [ ] **Step 4: Добавить модуль в сторож инварианта 1**

В `tests/unit/test_no_qt_in_core.py`, в кортеж `CORE`, рядом с
`"onecstarter.services.connection",`:

```python
    "onecstarter.services.availability",
```

Без этой строки сторож прошёл бы мимо нового модуля зелёным — ровно тот
дефект, который ревью вехи «Завершение v1» уже находило однажды.

- [ ] **Step 5: Прогнать тесты**

Run: `uv run pytest tests/unit/test_availability.py tests/unit/test_no_qt_in_core.py -q`
Expected: PASS, 14 тестов

- [ ] **Step 6: Линт и типы**

Run: `uv run ruff check . && uv run mypy`
Expected: `All checks passed!` и `Success: no issues found`

- [ ] **Step 7: Commit**

```bash
git add src/onecstarter/services/availability.py tests/unit/test_availability.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(services): выборка целей проверки доступности каталога"
```

---

### Task 3: `services/availability.py` — проба файловой системы

**Блокируется Task 1.** Без замера имя `1Cv8.1CD` в коде было бы догадкой,
выданной за факт.

**Files:**

- Modify: `src/onecstarter/services/availability.py`
- Modify: `tests/unit/test_availability.py`

**Interfaces:**

- Consumes: `Availability`, `ProbeTarget` из Task 2.
- Produces:
  - `DB_FILE_NAME: str` — имя файла базы данных внутри каталога;
  - `probe_paths(targets: Iterable[ProbeTarget], stat: Callable[[str], os.stat_result], report: Callable[[str, Availability], None]) -> None`
    — обходит уникальные цели и отдаёт результат по одной через `report`.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_availability.py`:

```python
import os
from stat import S_IFDIR, S_IFREG

from onecstarter.services.availability import DB_FILE_NAME, probe_paths


def _stat_result(mode: int) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, 0, 0, 0, 0, 0, 0))


_DIR = _stat_result(S_IFDIR | 0o755)
_FILE = _stat_result(S_IFREG | 0o644)


def _collect(targets, stat) -> dict[str, Availability]:
    got: dict[str, Availability] = {}
    probe_paths(targets, stat, lambda key, state: got.__setitem__(key, state))
    return got


def test_directory_with_the_database_file_is_present() -> None:
    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], lambda _p: _DIR) == {target.key: Availability.PRESENT}


def test_missing_directory_is_missing() -> None:
    def stat(_path: str) -> os.stat_result:
        raise FileNotFoundError

    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_path_that_is_a_file_is_missing() -> None:
    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], lambda _p: _FILE) == {target.key: Availability.MISSING}


def test_permission_error_counts_as_missing() -> None:
    """Решение заказчика 09.09.2026: два состояния в исходе (спека §1).

    Отказ ФС — не отдельное «не знаю», а тот же крестик. Цена решения
    признана и записана в спеке; тест закрепляет именно её.
    """
    def stat(_path: str) -> os.stat_result:
        raise PermissionError

    target = ProbeTarget(path_key(r"\\srv\share\b"), r"\\srv\share\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_arbitrary_oserror_counts_as_missing() -> None:
    def stat(_path: str) -> os.stat_result:
        raise OSError(1231, "сеть недоступна")

    target = ProbeTarget(path_key(r"\\srv\share\b"), r"\\srv\share\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_directory_without_the_database_file_is_missing() -> None:
    """Каталог остался, базу перенесли — решение заказчика ловить и это (спека §2)."""
    def stat(path: str) -> os.stat_result:
        if path.endswith(DB_FILE_NAME):
            raise FileNotFoundError
        return _DIR

    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_duplicate_paths_cost_one_stat() -> None:
    calls: list[str] = []

    def stat(path: str) -> os.stat_result:
        calls.append(path)
        return _DIR

    same = path_key(r"D:\b")
    _collect([ProbeTarget(same, r"D:\b"), ProbeTarget(same, r"d:/B")], stat)
    assert calls == [r"D:\b", os.path.join(r"D:\b", DB_FILE_NAME)]


def test_stat_is_called_on_the_original_value_not_the_key() -> None:
    """Проверяем ровно то, что откроет платформа, а не нашу нормализацию."""
    calls: list[str] = []

    def stat(path: str) -> os.stat_result:
        calls.append(path)
        return _DIR

    _collect([ProbeTarget(path_key(r"D:\b\..\b"), r"D:\b\..\b")], stat)
    assert calls[0] == r"D:\b\..\b"
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/unit/test_availability.py -q -k "present or missing or duplicate or original"`
Expected: FAIL — `ImportError: cannot import name 'DB_FILE_NAME'`

- [ ] **Step 3: Дописать модуль**

В `src/onecstarter/services/availability.py` добавить импорты и код:

```python
from collections.abc import Callable, Iterable
from stat import S_ISDIR
```

```python
# Имя файла базы данных внутри каталога файловой ИБ. Единственное место
# в коде с этим именем. Достоверность — [Ф] по замеру T-05.17
# (docs/research/t05-17-file-infobase-directory.md).
DB_FILE_NAME = "1Cv8.1CD"


def probe_paths(
    targets: Iterable[ProbeTarget],
    stat: Callable[[str], os.stat_result],
    report: Callable[[str, Availability], None],
) -> None:
    """Обойти уникальные цели, отдавая результат по одной через `report`.

    Результат отдаётся по мере готовности, а не пачкой в конце: локальные
    базы помечаются за миллисекунды и не ждут медленную сетевую шару,
    которая ответит на порядки позже (спека §3.4).

    Дубли снимаются по нормализованному ключу — две базы в одном каталоге
    стоят одного вызова `stat`.
    """  # noqa: RUF002
    seen: set[str] = set()
    for target in targets:
        if target.key in seen:
            continue
        seen.add(target.key)
        report(target.key, _probe_one(target.path, stat))


def _probe_one(path: str, stat: Callable[[str], os.stat_result]) -> Availability:
    """Одна проба: каталог есть и в нём есть файл базы — иначе `MISSING`.

    Любой `OSError` — `MISSING`, включая `PermissionError` и отказ сети:
    решение заказчика 09.09.2026, два состояния в исходе (спека §1).
    Отдельного «не удалось проверить» в исходе нет; `UNKNOWN` означает
    только «проверка ещё не дошла».

    Ловится `OSError`, а не голое `except`: `KeyboardInterrupt` и
    `SystemExit` из него не наследуются и проходят насквозь.
    """  # noqa: RUF002
    try:
        info = stat(path)
    except OSError:
        return Availability.MISSING
    if not S_ISDIR(info.st_mode):
        return Availability.MISSING
    try:
        stat(os.path.join(path, DB_FILE_NAME))
    except OSError:
        return Availability.MISSING
    return Availability.PRESENT
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_availability.py -q`
Expected: PASS, 20 тестов

- [ ] **Step 5: Линт и типы**

Run: `uv run ruff check . && uv run mypy`
Expected: коды 0

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/services/availability.py tests/unit/test_availability.py
git commit -m "feat(services): проба каталога файловой базы с инжектируемым stat"
```

---

### Task 4: Суффикс `(нет каталога)` в метке строки

**Files:**

- Modify: `src/onecstarter/services/display.py:44-46` (константы), `:213-229` (`row_label`)
- Modify: `tests/unit/test_display.py`

**Interfaces:**

- Consumes: ничего из Tasks 2–3 (принимает `bool`, не enum, — `display.py`
  остаётся независимым от `availability.py`).
- Produces:
  - `MISSING_SUFFIX = "(нет каталога)"`;
  - `row_label(row: Row, *, missing: bool = False) -> str`.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_display.py` (импорт `MISSING_SUFFIX` добавить
в существующий блок импорта из `onecstarter.services.display`):

```python
def test_missing_directory_shows_in_the_label() -> None:
    """Тултипа мало: раздел рассчитан на работу с клавиатуры (спека §4.2)."""
    item = _item(name="Бухгалтерия")
    row = Row(RowKind.BASE, item.name, item)
    assert row_label(row, missing=True) == f"Бухгалтерия {MISSING_SUFFIX}"


def test_missing_suffix_defaults_to_absent() -> None:
    item = _item(name="Бухгалтерия")
    assert row_label(Row(RowKind.BASE, item.name, item)) == "Бухгалтерия"


def test_all_three_marks_keep_their_order() -> None:
    """Порядок фиксирован спекой §4.2: разбор, каталог, общий список."""
    item = _item(name="Битая", parse_error="OrderInList не число", in_common_list=True)
    row = Row(RowKind.BASE, item.name, item)
    assert row_label(row, missing=True) == (
        f"Битая {BROKEN_SUFFIX} {MISSING_SUFFIX} {COMMON_SUFFIX}"
    )


def test_rows_without_an_item_ignore_the_flag() -> None:
    assert row_label(Row(RowKind.SECTION, "Избранное", None), missing=True) == "Избранное"
```

Вспомогательная `_item` в файле уже есть — если её сигнатура не принимает
`parse_error`/`in_common_list`, использовать `dataclasses.replace` над её
результатом, как это делают соседние тесты файла.

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/unit/test_display.py -q -k missing`
Expected: FAIL — `ImportError: cannot import name 'MISSING_SUFFIX'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/services/display.py`, рядом с `BROKEN_SUFFIX` и `COMMON_SUFFIX`:

```python
MISSING_SUFFIX = "(нет каталога)"
```

и заменить `row_label`:

```python
def row_label(row: Row, *, missing: bool = False) -> str:
    """Метка строки с видимыми пометками — то, что рисуется в колонке имени.

    Считается здесь, а не в Qt-слое: пометка «не разобрано» — обязательство
    спеки 4a, §2, и его нужно проверять табличным тестом, а не через
    QStandardItem. Само `row.label` остаётся чистым именем — по нему идёт
    поиск, и суффикс не должен ни мешать найти базу, ни находиться сам.

    `missing` — флаг, а не состояние `Availability`: витрина дерева
    не должна зависеть от модуля доступности ради одного булева значения,
    а решение «крестик или нет» уже принято вызывающим (спека §4.2).
    """  # noqa: RUF002
    item = row.item
    if item is None:
        return row.label
    parts = [row.label]
    if item.parse_error:
        parts.append(BROKEN_SUFFIX)
    if missing:
        parts.append(MISSING_SUFFIX)
    if item.in_common_list:
        parts.append(COMMON_SUFFIX)
    return " ".join(parts)
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_display.py -q`
Expected: PASS

- [ ] **Step 5: Линт, типы, commit**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/services/display.py tests/unit/test_display.py
git commit -m "feat(services): суффикс «(нет каталога)» в метке строки"
```

---

### Task 5: Крестик на значке размещения

**Files:**

- Modify: `src/onecstarter/ui/bases/icons.py:41-53` (`placement_icon`)
- Modify: `tests/ui/test_icons.py`

**Interfaces:**

- Consumes: `Palette` из `onecstarter.ui.theme` (поля `problem`, `text_dim`).
- Produces: `placement_icon(kind: ConnectKind, palette: Palette, *, missing: bool = False) -> QIcon`.
  Параметр именованный с умолчанием `False` — вызов из `ui/bases/panel.py:115`
  остаётся рабочим и значка без метки не теряет.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_icons.py`:

```python
def test_missing_mark_changes_the_icon(qapp: QApplication) -> None:
    for kind in _KNOWN:
        plain = _pixels(placement_icon(kind, theme.DARK))
        marked = _pixels(placement_icon(kind, theme.DARK, missing=True))
        assert plain != marked, kind


def test_missing_mark_is_drawn_in_the_problem_colour(qapp: QApplication) -> None:
    """Крестик — цветом проблемы палитры, а не запечённым красным."""
    for palette in _PALETTES:
        drawn = _opaque_colours(placement_icon(ConnectKind.FILE, palette, missing=True))
        assert palette.problem.casefold() in drawn, palette


def test_plain_icon_carries_no_problem_colour(qapp: QApplication) -> None:
    """Сторож обратной стороны: без флага цвета проблемы в файловом значке нет."""
    drawn = _opaque_colours(placement_icon(ConnectKind.FILE, theme.DARK))
    assert theme.DARK.problem.casefold() not in drawn


def test_missing_mark_sits_in_the_bottom_right_corner(qapp: QApplication) -> None:
    """Спека §4.1: справа внизу — там, где его ждёт заказчик."""
    image = placement_icon(ConnectKind.FILE, theme.DARK, missing=True).pixmap(16, 16).toImage()
    problem = theme.DARK.problem.casefold()
    marked = [
        (x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).name().casefold() == problem
    ]
    assert marked, "крестик не найден вовсе"
    assert all(x >= 8 and y >= 8 for x, y in marked), marked


def test_missing_mark_clears_a_notch_in_the_icon(qapp: QApplication) -> None:
    """Подложка вырезается прозрачностью, а не заливается цветом фона.

    Строка бывает выделенной, и подложка цветом фона на выделении выглядела бы
    заплаткой. Вырез прозрачностью работает на любом фоне (спека §4.1).
    """
    image = placement_icon(ConnectKind.FILE, theme.DARK, missing=True).pixmap(16, 16).toImage()
    corner = [
        image.pixelColor(x, y).alpha()
        for x in range(9, 16)
        for y in range(9, 16)
    ]
    assert 0 in corner, "выреза нет: крестик нарисован без подложки"
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/ui/test_icons.py -q -k missing`
Expected: FAIL — `TypeError: placement_icon() got an unexpected keyword argument 'missing'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/bases/icons.py` заменить `placement_icon` и добавить
рисование метки:

```python
def placement_icon(
    kind: ConnectKind, palette: Palette, *, missing: bool = False
) -> QIcon:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    colour = _colour_for(kind, palette)
    pen = QPen(colour)
    pen.setWidthF(1.4)
    painter.setPen(pen)
    _DRAW[kind](painter, colour)
    if missing:
        _draw_missing_mark(painter, palette)
    painter.end()
    return QIcon(pixmap)


def _draw_missing_mark(painter: QPainter, palette: Palette) -> None:
    """Крестик справа внизу: каталога файловой базы нет (спека §4.1).

    Подложка вырезается прозрачностью (`CompositionMode_Clear`), а не
    заливается цветом фона: строка бывает выделенной, и заплатка цветом
    фона на выделении была бы видна. Вырез читается на любом фоне.

    Без подложки крестик сливался бы с контуром значка на пересечении —
    все значки набора контурные, не залитые (докстринг модуля).
    """  # noqa: RUF002
    box = QRectF(9.0, 9.0, 6.0, 6.0)
    diagonals = (
        (box.topLeft(), box.bottomRight()),
        (box.topRight(), box.bottomLeft()),
    )
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    notch = QPen(QColor(Qt.GlobalColor.transparent))
    notch.setWidthF(3.4)
    notch.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(notch)
    for start, end in diagonals:
        painter.drawLine(start, end)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    mark = QPen(QColor(palette.problem))
    mark.setWidthF(1.6)
    mark.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(mark)
    for start, end in diagonals:
        painter.drawLine(start, end)
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/ui/test_icons.py -q`
Expected: PASS

- [ ] **Step 5: Показать значки заказчику — контрольная точка**

Спека §4.1 требует смотреть глазами: на 16 px крестик 6×6 — четыре пикселя линии.

Дописать в `.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py` показ
файлового значка с `missing=True` рядом с обычным, натурально и увеличенно,
в обеих палитрах. Запустить, сохранить снимок и **остановиться**: показать
заказчику и получить ответ.

Пути отхода, если крестик не читается (спека §4.1): увеличить `_SIZE` до 20 либо
заменить крестик другой фигурой. Выбор — за заказчиком, по факту рендера.

- [ ] **Step 6: Линт, типы, commit**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/bases/icons.py tests/ui/test_icons.py .superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py
git commit -m "feat(ui): крестик отсутствующего каталога на значке размещения"
```

---

### Task 6: Модель дерева — крестик, суффикс, подсказка

**Files:**

- Modify: `src/onecstarter/ui/bases/tree_model.py`
- Modify: `tests/ui/test_tree_model.py`

**Interfaces:**

- Consumes: `Availability`, `availability_hint`, `file_path_of`, `relative_path_note`
  из Task 2–3; `MISSING_SUFFIX`, `row_label(row, *, missing=)` из Task 4;
  `placement_icon(kind, palette, *, missing=)` из Task 5.
- Produces: `build_model(rows, cells, format_stamp, palette, *, availability: Mapping[str, Availability] | None = None) -> QStandardItemModel`.
  Ключ `availability` — **ключ записи** (`item.key`), не ключ пути: перевод
  делает вызывающий (Task 8).

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_tree_model.py`:

```python
from onecstarter.services.availability import Availability
from onecstarter.services.display import MISSING_SUFFIX


def _model_with(availability):
    row = Row(RowKind.BASE, "Файловая", _file_item())
    return build_model([row], {}, _stamp, theme.DARK, availability=availability)


def test_missing_base_gets_the_suffix(qapp: QApplication) -> None:
    model = _model_with({"id:file": Availability.MISSING})
    assert model.item(0, 0).text() == f"Файловая {MISSING_SUFFIX}"


def test_missing_base_tooltip_names_the_directory(qapp: QApplication) -> None:
    model = _model_with({"id:file": Availability.MISSING})
    assert r"Каталог не найден: D:\bases\acc" in model.item(0, 0).toolTip()


def test_present_base_carries_no_mark(qapp: QApplication) -> None:
    model = _model_with({"id:file": Availability.PRESENT})
    assert model.item(0, 0).text() == "Файловая"
    assert "Каталог не найден" not in model.item(0, 0).toolTip()


def test_unknown_state_carries_no_mark(qapp: QApplication) -> None:
    """Пока проход идёт, крестика нет — иначе список на старте весь битый (спека §1)."""
    model = _model_with({"id:file": Availability.UNKNOWN})
    assert model.item(0, 0).text() == "Файловая"


def test_record_absent_from_the_mapping_is_unknown(qapp: QApplication) -> None:
    model = _model_with({})
    assert model.item(0, 0).text() == "Файловая"


def test_availability_defaults_to_nothing_marked(qapp: QApplication) -> None:
    row = Row(RowKind.BASE, "Файловая", _file_item())
    model = build_model([row], {}, _stamp, theme.DARK)
    assert model.item(0, 0).text() == "Файловая"


def test_missing_base_icon_differs_from_present(qapp: QApplication) -> None:
    missing = _model_with({"id:file": Availability.MISSING}).item(0, 0)
    present = _model_with({"id:file": Availability.PRESENT}).item(0, 0)
    assert (
        missing.icon().pixmap(16, 16).toImage()
        != present.icon().pixmap(16, 16).toImage()
    )


def test_relative_path_gets_an_honest_note(qapp: QApplication) -> None:
    """Относительный путь не проверяется — и тултип об этом говорит (спека §2)."""
    item = replace(_file_item(), connect='File="bases\\acc";')
    row = Row(RowKind.BASE, "Относительная", item)
    model = build_model([row], {}, _stamp, theme.DARK, availability={})
    assert "Путь относительный" in model.item(0, 0).toolTip()
    assert model.item(0, 0).text() == "Относительная"
```

Проверить, что `_file_item()` в файле даёт `key="id:file"` и
`connect=r'File="D:\bases\acc";'` — тесты выше опираются на эти значения.
Если нет, поправить константы в тестах под фактическую фабрику.

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/ui/test_tree_model.py -q -k "missing or unknown or relative or availability or present"`
Expected: FAIL — `TypeError: build_model() got an unexpected keyword argument 'availability'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/bases/tree_model.py` заменить импорты и обе функции:

```python
from onecstarter.services.availability import (
    Availability,
    availability_hint,
    file_path_of,
    relative_path_note,
)
from onecstarter.services.connection import BADGE_LABELS
from onecstarter.services.display import Row, RowKind, VersionCell, row_label
```

```python
def build_model(
    rows: Sequence[Row],
    cells: Mapping[str, VersionCell],
    format_stamp: Callable[[datetime], str],
    palette: Palette,
    *,
    availability: Mapping[str, Availability] | None = None,
) -> QStandardItemModel:
    """Собрать модель дерева целиком.

    `availability` ключуется **ключом записи**, не путём: перевод «ключ пути →
    ключ записи» делает вьюха, у которой есть и список записей, и накопленные
    результаты пробы (спека §3.5). Умолчание `None` — «ничего не помечено»:
    единственный боевой вызов передаёт отображение явно и покрыт тестом
    вьюхи, а десятки тестов модели, к доступности отношения не имеющих,
    не обязаны его знать.
    """  # noqa: RUF002
    states = availability or {}
    model = QStandardItemModel(0, len(COLUMNS))
    model.setHorizontalHeaderLabels(list(COLUMNS))
    for row in rows:
        model.appendRow(_items_for(row, cells, format_stamp, palette, states))
    return model
```

В `_items_for` добавить параметр `states: Mapping[str, Availability]`, заменить
построение метки и блок значка:

```python
    state = (
        states.get(row.item.key, Availability.UNKNOWN)
        if row.item is not None
        else Availability.UNKNOWN
    )
    missing = state is Availability.MISSING
    name = QStandardItem(row_label(row, missing=missing))
```

и внутри `if has_placement_icon:` (`row.item` там заведомо не `None`):

```python
        if has_placement_icon:
            name.setIcon(placement_icon(row.item.kind, palette, missing=missing))
            parts = [row.note] if row.note else []
            parts.append(BADGE_LABELS[row.item.kind])
            path = file_path_of(row.item)
            extra = (
                availability_hint(state, path)
                if path is not None
                else None
            ) or relative_path_note(row.item)
            if extra:
                parts.append(extra)
            name.setToolTip("\n".join(parts))
```

Рекурсивный вызов в конце `_items_for` тоже получает `states`:

```python
    for child in row.children:
        name.appendRow(_items_for(child, cells, format_stamp, palette, states))
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/ui/test_tree_model.py -q`
Expected: PASS — включая все существующие тесты файла

- [ ] **Step 5: Линт, типы, commit**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/bases/tree_model.py tests/ui/test_tree_model.py
git commit -m "feat(ui): модель дерева помечает базы с отсутствующим каталогом"
```

---

### Task 7: Фоновая проба в `ui/background.py`

**Files:**

- Modify: `src/onecstarter/ui/background.py`
- Modify: `tests/ui/test_background.py`

**Interfaces:**

- Consumes: `Availability`, `ProbeTarget`, `probe_paths` из Tasks 2–3.
- Produces: `class AvailabilityProbe(QObject)` с сигналом
  `probed = Signal(str, object)` (ключ пути, `Availability`) и методом
  `start(targets: Sequence[ProbeTarget]) -> None`.
  Конструктор: `AvailabilityProbe(stat=os.stat, *, spawn=_spawn_daemon, parent=None)`.

Отдельный класс, а не третья задача внутри `StartupTasks`: `StartupTasks.start()`
одноразова (два задания за жизнь окна), а проба перезапускается по F5.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_background.py`:

```python
import os
from stat import S_IFDIR

from onecstarter.services.availability import Availability, ProbeTarget
from onecstarter.ui.background import AvailabilityProbe

_DIR = os.stat_result((S_IFDIR | 0o755, 0, 0, 1, 0, 0, 0, 0, 0, 0))


def test_probe_emits_one_signal_per_path(qtbot):
    got: list[tuple[str, Availability]] = []
    probe = AvailabilityProbe(lambda _p: _DIR, spawn=_SYNC)
    probe.probed.connect(lambda key, state: got.append((key, state)))
    probe.start([ProbeTarget("a", r"D:\a"), ProbeTarget("b", r"D:\b")])
    assert got == [("a", Availability.PRESENT), ("b", Availability.PRESENT)]


def test_probe_reports_missing(qtbot):
    def stat(_path: str) -> os.stat_result:
        raise FileNotFoundError

    got: list[Availability] = []
    probe = AvailabilityProbe(stat, spawn=_SYNC)
    probe.probed.connect(lambda _key, state: got.append(state))
    probe.start([ProbeTarget("a", r"D:\a")])
    assert got == [Availability.MISSING]


def test_probe_can_be_restarted(qtbot):
    """F5 перезапускает пробу — `start` не одноразов, в отличие от StartupTasks."""
    got: list[str] = []
    probe = AvailabilityProbe(lambda _p: _DIR, spawn=_SYNC)
    probe.probed.connect(lambda key, _state: got.append(key))
    probe.start([ProbeTarget("a", r"D:\a")])
    probe.start([ProbeTarget("a", r"D:\a")])
    assert got == ["a", "a"]


def test_probe_uses_daemon_threads(qtbot):
    done = threading.Event()
    seen: list[bool] = []

    def stat(_path: str) -> os.stat_result:
        seen.append(threading.current_thread().daemon)
        done.set()
        return _DIR

    AvailabilityProbe(stat).start([ProbeTarget("a", r"D:\a")])
    assert done.wait(5), "проба не завершилась за 5 с"
    assert seen[0] is True


def test_probe_failure_is_logged_without_the_path(qtbot, caplog):
    """Инвариант 5: путь пользователя в лог не попадает даже при отказе."""
    def stat(_path: str) -> os.stat_result:
        raise RuntimeError(r"\\srv\секретная-шара\база")

    with caplog.at_level(logging.ERROR, logger="onecstarter.startup"):
        AvailabilityProbe(stat, spawn=_SYNC).start([ProbeTarget("a", r"D:\a")])
    assert "секретная-шара" not in caplog.text
    assert "доступность каталогов" in caplog.text
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/ui/test_background.py -q -k probe`
Expected: FAIL — `ImportError: cannot import name 'AvailabilityProbe'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/background.py` добавить импорты:

```python
import os
from collections.abc import Sequence

from onecstarter.services.availability import Availability, ProbeTarget, probe_paths
```

и класс в конце модуля:

```python
class AvailabilityProbe(QObject):
    """Проверка каталогов файловых баз в фоне — перезапускаемая.

    Отдельно от `StartupTasks`: та поднимает два задания один раз за жизнь
    окна, а проба перезапускается по `F5` (спека §5). Поток — демон по той же
    причине, что и там: `stat` на мёртвой сетевой шаре не прерывается
    (инцидент 15.08.2026), и висящий поток не должен удерживать процесс
    при выходе.

    Результат отдаётся по одному пути за сигнал, а не пачкой в конце: иначе
    одна медленная шара держала бы метки всех остальных баз (спека §3.4).

    В лог — счётчики и длительность, не пути: лог прикладывают к issue
    (докстринг модуля, инвариант 5).
    """  # noqa: RUF002

    probed = Signal(str, object)  # ключ пути, Availability

    def __init__(
        self,
        stat: Callable[[str], os.stat_result] = os.stat,
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._stat = stat
        self._spawn = spawn

    def start(self, targets: Sequence[ProbeTarget]) -> None:
        ordered = list(targets)
        self._spawn(lambda: self._run(ordered))

    def _run(self, targets: Sequence[ProbeTarget]) -> None:
        started = time.monotonic()
        _log.info("доступность каталогов: начато, целей %d", len(targets))
        missing = 0

        def report(key: str, state: Availability) -> None:
            nonlocal missing
            if state is Availability.MISSING:
                missing += 1
            self.probed.emit(key, state)

        try:
            probe_paths(targets, self._stat, report)
        except Exception as exc:
            # Падение фона не должно оставлять список без меток молча:
            # причина уходит в лог теми же местами кадров, без сообщения
            # исключения (оно несёт путь — см. докстринг _log_failure).
            _log_failure("доступность каталогов", exc)
        _log.info(
            "доступность каталогов: закончено за %d мс, недоступных %d",
            int((time.monotonic() - started) * 1000),
            missing,
        )
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/ui/test_background.py -q`
Expected: PASS

- [ ] **Step 5: Линт, типы, commit**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/background.py tests/ui/test_background.py
git commit -m "feat(ui): фоновая проба доступности каталогов, перезапускаемая"
```

---

### Task 8: `BasesView` — накопление состояний и коалесинг перерисовки

**Files:**

- Modify: `src/onecstarter/ui/bases/view.py` (`BasesView.__init__`, `rebuild`, новый метод)
- Modify: `tests/ui/test_bases_view.py`

**Interfaces:**

- Consumes: `Availability`, `probe_targets` из Task 2; `build_model(..., availability=)` из Task 6.
- Produces:
  - `BasesView.apply_availability(self, key: str, state: Availability) -> None`
    — слот под сигнал `AvailabilityProbe.probed`;
  - `BasesView.probe_requested = Signal()` — вьюха просит запустить пробу,
    сам объект пробы ей не принадлежит;
  - атрибут `_availability: dict[str, Availability]` (по ключу пути).

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_bases_view.py`:

```python
from onecstarter.services.availability import Availability, path_key
from onecstarter.services.display import MISSING_SUFFIX


def test_availability_reaches_the_model_after_debounce(qtbot, workspace_factory):
    """Результат пробы доезжает до метки строки — через коалесинг в 200 мс."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = path_key(_DEMO_ACCOUNTING_PATH)
    view.apply_availability(key, Availability.MISSING)
    qtbot.waitUntil(lambda: MISSING_SUFFIX in _all_labels(view), timeout=2000)


def test_repeated_reports_cause_one_rebuild(qtbot, workspace_factory, monkeypatch):
    """Коалесинг: пятьдесят сигналов подряд — одна пересборка, не пятьдесят."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    rebuilds: list[int] = []
    original = view.rebuild
    monkeypatch.setattr(view, "rebuild", lambda: (rebuilds.append(1), original())[1])
    for _ in range(50):
        view.apply_availability(path_key(_DEMO_ACCOUNTING_PATH), Availability.MISSING)
    qtbot.waitUntil(lambda: bool(rebuilds), timeout=2000)
    assert len(rebuilds) == 1


def test_unknown_paths_do_not_mark_anything(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    view.apply_availability(path_key(r"D:\чужой\путь"), Availability.MISSING)
    qtbot.wait(400)
    assert MISSING_SUFFIX not in _all_labels(view)
```

Вспомогательная функция рядом с существующими помощниками файла:

```python
def _all_labels(view: BasesView) -> str:
    """Все метки дерева одной строкой — для проверок «есть/нет пометки»."""
    model = view._tree.model()
    labels: list[str] = []

    def walk(parent) -> None:
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            labels.append(str(index.data()))
            walk(index)

    walk(QModelIndex())
    return "\n".join(labels)
```

`_DEMO_ACCOUNTING_PATH` — путь файловой базы из фикстуры, на которой стоит
`_DEMO_ACCOUNTING_KEY` (он в файле уже есть). Взять значение `File=` из
`tests/fixtures/` и объявить константу рядом с `_DEMO_ACCOUNTING_KEY`.

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/ui/test_bases_view.py -q -k availability`
Expected: FAIL — `AttributeError: 'BasesView' object has no attribute 'apply_availability'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/bases/view.py` добавить импорты:

```python
from onecstarter.services.availability import Availability, probe_targets
```

В объявление класса, рядом с `launched = Signal(str)`:

```python
    # Вьюха просит запустить пробу доступности, но объектом пробы не владеет:
    # он живёт в проводке `ui/app.py` рядом со StartupTasks. Так `F5` работает
    # без того, чтобы раздел знал про потоки.  # noqa: RUF003
    probe_requested = Signal()
```

В конец `__init__` (после установки `self._palette`, до первой `rebuild()`):

```python
        # Доступность каталогов приходит из фона по одному пути за сигнал
        # и ключуется НОРМАЛИЗОВАННЫМ ПУТЁМ, а не ключом записи: так дубли
        # снимаются сами (две базы в одном каталоге), а правка имени записи
        # не теряет уже известный результат (спека §3.5).
        self._availability: dict[str, Availability] = {}
        # Коалесинг: проба на пятидесяти базах даёт пятьдесят сигналов подряд,
        # а пересборка модели целиком стоит дорого. Тот же приём и тот же
        # интервал, что гасят дребезг перезаписи файла в ui/watcher.py.
        self._availability_timer = QTimer(self)
        self._availability_timer.setSingleShot(True)
        self._availability_timer.setInterval(200)
        self._availability_timer.timeout.connect(self.rebuild)
```

Новый метод рядом с `apply_installations`:

```python
    def apply_availability(self, key: str, state: Availability) -> None:
        """Один результат пробы: `key` — нормализованный путь, не ключ записи."""
        if self._availability.get(key) is state:
            return
        self._availability[key] = state
        self._availability_timer.start()
```

В `rebuild()`, рядом со сборкой `cells`:

```python
        # Перевод «ключ записи → состояние» из двух готовых отображений:
        # probe_targets даёт «ключ записи → ключ пути», self._availability —
        # «ключ пути → состояние». Запись, которую не проверяем вовсе
        # (не файловая, пустой или относительный путь), в targets не попадает
        # и получает UNKNOWN (спека §3.5).
        targets = probe_targets(items)
        availability = {
            key: self._availability.get(target.key, Availability.UNKNOWN)
            for key, target in targets.items()
        }
```

и передать в `build_model`:

```python
        model = build_model(
            self._rows, cells, _format_stamp, self._palette, availability=availability
        )
```

Проверить, что `QTimer` уже импортирован в модуле; если нет — добавить
в существующий импорт из `PySide6.QtCore`.

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/ui/test_bases_view.py -q`
Expected: PASS

- [ ] **Step 5: Линт, типы, commit**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/bases/view.py tests/ui/test_bases_view.py
git commit -m "feat(ui): раздел «Базы» накапливает доступность каталогов"
```

---

### Task 9: `F5` и пункт «Обновить»

**Files:**

- Modify: `src/onecstarter/ui/shortcuts.py:28-48` (кортеж `BASES_SHORTCUTS`)
- Modify: `src/onecstarter/ui/bases/view.py` (регистрация сочетаний, `_build_empty_space_menu`)
- Modify: `tests/ui/test_bases_view.py`

**Interfaces:**

- Consumes: `probe_requested` из Task 8.
- Produces: `BasesView.refresh_all(self) -> None` — перечитать `ibases.v8i`,
  пересобрать дерево и попросить новую пробу.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_bases_view.py`:

```python
def test_refresh_all_asks_for_a_new_probe(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    with qtbot.waitSignal(view.probe_requested, timeout=1000):
        view.refresh_all()


def test_refresh_keeps_known_states(qtbot, workspace_factory):
    """F5 не сбрасывает известное в UNKNOWN — иначе крестики мигали бы (спека §5)."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = path_key(_DEMO_ACCOUNTING_PATH)
    view.apply_availability(key, Availability.MISSING)
    view.refresh_all()
    assert view._availability[key] is Availability.MISSING


def test_empty_space_menu_offers_refresh(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    menu = view._build_empty_space_menu()
    assert "Обновить\tF5" in [action.text() for action in menu.actions()]
```

Существующий `test_shortcut_reference_matches_registered_shortcuts` начнёт падать
сразу, как только `F5` появится в таблице без регистрации (и наоборот), — отдельный
тест на регистрацию не нужен.

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/ui/test_bases_view.py -q -k "refresh or shortcut_reference"`
Expected: FAIL — `AttributeError: 'BasesView' object has no attribute 'refresh_all'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/shortcuts.py`, в кортеж `BASES_SHORTCUTS`, после строки `F4`:

```python
    ShortcutSpec("F5", "Обновить список и перепроверить доступность каталогов", ("F5",)),
```

В `src/onecstarter/ui/bases/view.py`, рядом с регистрацией `F3`/`F4`:

```python
        QShortcut(QKeySequence("F5"), self, self.refresh_all)
```

Новый метод рядом с `rebuild`:

```python
    def refresh_all(self) -> None:
        """`F5`: перечитать файл, пересобрать дерево, попросить новую пробу.

        Накопленные состояния НЕ сбрасываются в `UNKNOWN`: иначе каждое `F5`
        гасило бы все крестики и зажигало их заново, и список мигал бы
        на ровном месте (спека §5). Результаты заменяются по мере готовности.
        """  # noqa: RUF002
        self._workspace.reload_if_changed()
        self.rebuild()
        self.probe_requested.emit()
```

В `_build_empty_space_menu`, первым пунктом:

```python
        menu.addAction("Обновить\tF5", self.refresh_all)
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/ui/test_bases_view.py tests/ui/test_settings_view.py -q`
Expected: PASS — справочник сочетаний в настройках подхватывает `F5` из таблицы
без правок

- [ ] **Step 5: Линт, типы, commit**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/shortcuts.py src/onecstarter/ui/bases/view.py tests/ui/test_bases_view.py
git commit -m "feat(ui): F5 обновляет список и перепроверяет каталоги"
```

---

### Task 10: Проводка в `ui/app.py`

**Files:**

- Modify: `src/onecstarter/ui/app.py:663-1100` (`_build_main_window`), `:1134` и `:404` (распаковка), `:1151` (старт)
- Modify: `tests/ui/test_app.py`

**Interfaces:**

- Consumes: `AvailabilityProbe` (Task 7), `probe_requested`/`apply_availability` (Tasks 8–9),
  `probe_targets` (Task 2).
- Produces: `_build_main_window` возвращает кортеж из **четырёх** элементов:
  `(window, tasks, monitor, start_probe)`, где `start_probe: Callable[[], None]`.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/ui/test_app.py` (рядом с существующими тестами сборки окна,
используя их фикстуры окружения):

```python
def test_main_window_wires_the_availability_probe(qtbot, ...):
    """Проба заведена, подписана на вьюху и не стартует внутри сборки окна.

    `_build_main_window` собирает, но не запускает (её докстринг): проба
    обязана стартовать только после того, как окно решило, показываться ему
    или остаться в трее.
    """
    window, _tasks, _monitor, start_probe = _build_main_window(...)
    assert callable(start_probe)
```

Точные фикстуры и аргументы взять у ближайшего существующего теста файла,
который зовёт `_build_main_window` или `main` — сигнатура у неё длинная,
дублировать её здесь бессмысленно.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/ui/test_app.py -q -k availability`
Expected: FAIL — `ValueError: not enough values to unpack (expected 4, got 3)`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/app.py` добавить импорты:

```python
from onecstarter.services.availability import probe_targets
from onecstarter.ui.background import AvailabilityProbe, StartupTasks
```

В `_build_main_window`, рядом со сборкой `tasks`:

```python
    probe = AvailabilityProbe(parent=window)
    probe.probed.connect(view.apply_availability)

    def start_probe() -> None:
        probe.start(list(probe_targets(runtime.workspace.items()).values()))

    # F5 во вьюхе просит пробу, не владея ею: раздел «Базы» о потоках
    # не знает (спека §3, докстринг `BasesView.probe_requested`).
    view.probe_requested.connect(start_probe)
```

Изменить тип возврата и `return`:

```python
) -> tuple[MainWindow, StartupTasks, ServerMonitor, Callable[[], None]]:
```

```python
    return window, tasks, monitor, start_probe
```

Обновить обе распаковки. На строке ~404:

```python
        window, built_tasks, _monitor, _start_probe = _build_main_window(
```

На строке ~1134:

```python
        window, tasks, monitor, start_probe = _build_main_window(
```

Рядом с `tasks.start()` и `monitor.start()`:

```python
    tasks.start()
    # Проба доступности — там же, где остальной фон, и по той же причине:
    # обращения к сетевым шарам не должны начаться раньше, чем окно решило,
    # показываться ему или остаться скрытым в трее.
    start_probe()
    monitor.start()
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/ui/test_app.py -q`
Expected: PASS

- [ ] **Step 5: Полный прогон, линт, типы**

```bash
uv run pytest -q > e:/tmp/v24-task10.log 2>&1
uv run ruff check . && uv run mypy
```

Ожидание: все тесты зелёные. При `Windows fatal exception: access violation`
в `pytestqt/plugin.py` — это известный T-12 п. 15; сверить место по
`uv run pytest --collect-only -q` и прогнать повторно, зафиксировав проявление.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/ui/app.py tests/ui/test_app.py
git commit -m "feat(ui): проводка пробы доступности при старте и по F5"
```

---

### Task 11: Мутационные проверки

Правило проекта: тест, проверяющий отказ операции или сохранность
пользовательского файла, обязан падать на сломанной реализации. Протокол —
мутация правкой файла, прогон названного теста, **дословный** `FAILED`,
откат правкой файла, тот же тест зелёным повторно.

**Files:**

- Modify: `docs/tasks.md` (таблица мутационных проверок вехи)

**Interfaces:**

- Consumes: тесты из Tasks 2–9.
- Produces: раздел «Мутационные проверки вехи v2.4» в `docs/tasks.md`.

- [ ] **Step 1: Мутация 1 — отказ ФС считать успехом**

В `services/availability.py`, `_probe_one`: заменить первый
`except OSError: return Availability.MISSING` на
`except OSError: return Availability.PRESENT`.

Run: `uv run pytest tests/unit/test_availability.py -q -k "permission or arbitrary_oserror or missing_directory"`
Expected: FAIL — три теста. Записать дословный вывод, откатить, прогнать снова.

- [ ] **Step 2: Мутация 2 — непроверенное красить крестиком**

В `ui/bases/tree_model.py`, `_items_for`: заменить
`missing = state is Availability.MISSING` на
`missing = state is not Availability.PRESENT`.

Run: `uv run pytest tests/ui/test_tree_model.py -q -k "unknown or absent_from_the_mapping or defaults or relative"`
Expected: FAIL — тесты `UNKNOWN`. Записать, откатить, прогнать снова.

- [ ] **Step 3: Мутация 3 — снять дедупликацию путей**

В `services/availability.py`, `probe_paths`: удалить строки
`if target.key in seen: continue` и `seen.add(target.key)`.

Run: `uv run pytest tests/unit/test_availability.py -q -k duplicate`
Expected: FAIL. Записать, откатить, прогнать снова.

- [ ] **Step 4: Мутация 4 — не проверять файл базы**

В `services/availability.py`, `_probe_one`: удалить второй блок `try`/`except`
целиком (проверку `DB_FILE_NAME`).

Run: `uv run pytest tests/unit/test_availability.py -q -k without_the_database_file`
Expected: FAIL. Записать, откатить, прогнать снова.

- [ ] **Step 5: Мутация 5 — снять коалесинг**

В `ui/bases/view.py`, `apply_availability`: заменить
`self._availability_timer.start()` на `self.rebuild()`.

Run: `uv run pytest tests/ui/test_bases_view.py -q -k repeated_reports`
Expected: FAIL — пересборок 50 вместо одной. Записать, откатить, прогнать снова.

- [ ] **Step 6: Мутация 6 — F5 сбрасывает известное**

В `ui/bases/view.py`, `refresh_all`: добавить `self._availability.clear()`
первой строкой.

Run: `uv run pytest tests/ui/test_bases_view.py -q -k refresh_keeps_known`
Expected: FAIL — `KeyError`. Записать, откатить, прогнать снова.

- [ ] **Step 7: Записать результаты**

Дописать в `docs/tasks.md` раздел «Мутационные проверки вехи v2.4» таблицей
того же вида, что у предыдущих вех: `# | Находка | Мутация | Ф / Т | Результат`,
с дословными строками падения. Мутация, которую набор **не убил**, — находка:
дописать тест и повторить, а не смягчать формулировку.

- [ ] **Step 8: Commit**

```bash
git add docs/tasks.md
git commit -m "docs: мутационные проверки вехи v2.4 — шесть мутаций"
```

---

### Task 12: Документы, версия и гейты вехи

**Files:**

- Modify: `docs/requirements.md:75-100` (§5 роадмап), `:23-33` (§2 таблица болей), `:100-106` (§6)
- Modify: `docs/tasks.md`
- Modify: `pyproject.toml:3`, `uv.lock`
- Modify: `README.md`

**Interfaces:**

- Consumes: результат всех предыдущих задач.
- Produces: выпускаемое состояние вехи.

- [ ] **Step 1: Спросить заказчика про строку боли**

Спека §8 оставила это решение открытым: ни одна существующая боль в §2
`requirements.md` сюда не подходит. Варианты — новая строка «З» («битая ссылка
не видна: штатный стартер показывает запись с несуществующим каталогом наравне
с живой, отказ виден только после запуска», измеряется «база с удалённым
каталогом отличима в списке без наведения мыши и без запуска») либо «—», как
у v2.1, v3 и v5. **Спросить и сделать по ответу.**

- [ ] **Step 2: Роадмап**

В `docs/requirements.md` §5 добавить строку между `v2.3` и `v3`:

```text
| v2.4 | Доступность файловых баз: метка отсутствующего каталога в списке, обновление по `F5` | <по ответу из шага 1> |
```

Ниже, в абзаце о выпущенных версиях, добавить `v2.4` к перечню после выпуска.

- [ ] **Step 3: Открытый вопрос**

В `docs/requirements.md` §6 записать открытый вопрос: «Относительный путь
в `File=` — относительно чего его разрешает платформа? До замера T-05.18
такие записи не проверяются на доступность (спека v2.4, §2)».

- [ ] **Step 4: Задачи и замеры**

В `docs/tasks.md`: строка вехи v2.4 со ссылками на спеку и этот план;
строка замера T-05.17 (закрыт Task 1) и T-05.18 (открыт, веху не блокирует).

- [ ] **Step 5: Версия**

В `pyproject.toml` поднять `version = "2.4.0"`, затем:

```bash
uv sync
```

чтобы `uv.lock` догнал версию (иначе расхождение всплывёт на сборке — так
уже было в вехе v2.3, `b68f3f6`).

- [ ] **Step 6: README**

Дописать метку отсутствующего каталога и `F5` в описание раздела «Базы»
и в перечень сочетаний клавиш, если он там есть.

- [ ] **Step 7: Гейты вехи**

```bash
uv run pytest -q > e:/tmp/v24-final.log 2>&1
uv run ruff check .
uv run mypy
```

Ожидание: все три кода 0. Число тестов записать в `docs/tasks.md` рядом
с базовым 1962.

- [ ] **Step 8: Сборка и smoke**

```bash
uv run pyinstaller build/onecstarter.spec --noconfirm
```

Сборка обязана заканчиваться smoke-тестом собранного экземпляра, а не фактом
успешной упаковки (`CLAUDE.md`). В smoke обязательно проверить глазами:
база с удалённым каталогом помечена крестиком и суффиксом, `F5` перепроверяет,
живые базы не помечены.

- [ ] **Step 9: Commit**

```bash
git add docs/requirements.md docs/tasks.md pyproject.toml uv.lock README.md
git commit -m "docs: веха v2.4 — метка отсутствующего каталога, версия 2.4.0"
```

---

## Self-Review плана

**Покрытие спеки.** §0 → Task 1 (замер T-05.17) и Task 12 шаг 3 (T-05.18);
§1 (три состояния, два исхода) → Tasks 2, 3, 6; §2 (что проверяем) → Tasks 2, 3;
§3 (архитектура) → Tasks 2, 3, 6, 7, 8, 10; §3.1 → Task 8 (состояния вне
`rebuild`); §3.5 (хранение по пути) → Task 8; §4.1 (значок) → Task 5;
§4.2 (суффикс) → Task 4; §4.3 (тултип) → Task 6; §5 (F5) → Task 9;
§6 (границы) → нигде и намеренно: путь запуска не трогается ни одной задачей;
§7.1–7.2 → тесты в Tasks 2–9; §7.3 → Task 11; §7.4 → Task 1 и Task 12;
§8 → Task 12.

**Расхождения плана со спекой, найденные при планировании.** Три. Спека
**уже исправлена** тем же коммитом, что вносит этот план, — документ правится
вслед за находкой сразу, а не после реализации: разошедшаяся спека соврала бы
исполнителю, который читает её первой (правило `CLAUDE.md`).

1. Спека §3 называет `availability_suffix(state)`. План его не заводит:
   `row_label` принимает `bool`, и `services/display.py` остаётся независимым
   от `services/availability.py`. Меньше связности за ту же функцию.
2. Спека §3 говорит «третья задача рядом с обнаружением платформ». План заводит
   **отдельный класс** `AvailabilityProbe`: `StartupTasks.start()` одноразова,
   а проба перезапускается по `F5`.
3. Спека §4.1 говорит «обводка цветом фона». План вырезает подложку
   прозрачностью (`CompositionMode_Clear`): строка бывает выделенной, и заплатка
   цветом фона на выделении была бы видна.

Плюс одна граница, спекой не названная: значок в панели размещения
(`ui/bases/panel.py:115`) метку **не получает** — умолчание `missing=False`
оставляет его как есть. Метка живёт в списке, как и просил заказчик.

**Placeholder-скан.** Три места, где план сознательно не приводит код целиком,
и все три — не заглушки, а ссылки на существующий контекст: фикстуры
`_build_main_window` в Task 10 шаг 1 (сигнатура длинная, берётся у соседнего
теста), константа `_DEMO_ACCOUNTING_PATH` в Task 8 (значение берётся из фикстуры
репозитория) и точный вид `_item` в Task 4 (в файле уже есть). Каждое из трёх
названо явно с указанием, откуда брать.

**Согласованность имён.** `Availability`, `ProbeTarget`, `path_key`,
`file_path_of`, `probe_targets`, `probe_paths`, `relative_path_note`,
`availability_hint`, `DB_FILE_NAME`, `RELATIVE_NOTE`, `MISSING_SUFFIX`,
`placement_icon(..., missing=)`, `row_label(..., missing=)`,
`build_model(..., availability=)`, `AvailabilityProbe.probed`,
`BasesView.apply_availability`, `BasesView.probe_requested`,
`BasesView.refresh_all` — каждое объявлено в блоке **Produces** ровно одной
задачи и употребляется дальше в той же форме.
