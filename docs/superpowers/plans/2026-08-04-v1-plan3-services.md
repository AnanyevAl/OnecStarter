# План 3 v1: `services` — агрегация списка, запись с разрешением конфликта, запуск, наши данные

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Слой сценариев: собрать список баз из `ibases.v8i`, общих списков и наших данных; писать в `ibases.v8i` патчами с переигрыванием при внешнем изменении; запускать базу; хранить историю и избранное в `%APPDATA%\OneCStarter\bases.json`.

**Architecture:** Четыре узких модуля (`model`, `user_data`, `catalog`, `edit`, `launch`) и тонкий координатор `workspace`, держащий состояние: документ, снапшот, наши данные, список установок. Чистая логика отделена от ввода-вывода: разбор, сборка дерева, применение патча и мутации наших данных — чистые функции; ФС трогают только загрузка/сохранение и цикл записи. Побочные эффекты (порождение процесса, открытие браузера, текущее время, генерация UUID) инжектируются в координатор аргументами — процессы 1С в тестах не запускаются никогда.

**Tech Stack:** Python 3.13, stdlib (`dataclasses`, `enum`, `json`, `datetime`, `uuid`, `webbrowser`, `pathlib`), pytest. Зависимостей не добавляем.

**Контекст серии:** план 3 из ~5 по спеке [../specs/2026-07-30-v1-core-design.md](../specs/2026-07-30-v1-core-design.md), детали — [дизайн плана 3](../specs/2026-08-03-v1-plan3-services-design.md). Слои `config` ([план 1](2026-07-31-v1-plan1-config-core.md)), `domain` и `platform_1c` ([план 2](2026-07-31-v1-plan2-platform-domain.md)) готовы и здесь только используются. Факты о 1С — скилы `.claude/skills/v8i-format/` и `.claude/skills/platform-launch/`; здесь их не перепроверять.

## Global Constraints

- Python ≥ 3.13; `uv` для окружения; команды запускать как `uv run …` из корня репозитория.
- `mypy --strict` распространяется на `src` И `tests` — тестовые функции аннотируются (`-> None`).
- `ruff` с правилами `E,F,W,I,N,UP,B,A,C4,PTH,RUF`, `line-length = 100`. `PTH` запрещает `os.path` — только `pathlib`.
- Пакет `services` не импортирует `PySide6` ни прямо, ни транзитивно (инвариант 1 `CLAUDE.md`).
- Секреты — только через `security/` (инвариант 5). Значения секретных ключей не попадают ни в сообщения, ни в логи.
- Запись в пользовательские файлы — только атомарная, через готовые функции `config.atomic` (инвариант 4).
- **Процессы 1С в тестах не запускаются никогда**: `spawn` и открытие браузера подменяются заглушками.
- В тестах и фикстурах — только обезличенные имена и пути (`C:\Bases\Demo`, `Демо Бухгалтерия`, `srv-1c`).
- Коммиты после каждой задачи; сообщения — `тип: описание по-русски`, как в истории репозитория.

## Решения плана (зафиксированы здесь, чтобы не переигрывать в задачах)

1. **Регистронезависимое сравнение имён ключей секции.** `V8iSection.get`/`set` сейчас сравнивают имя ключа побайтово. Для этого плана это не косметика: не найдя `id=` строчными, мы сочли бы запись «без `ID`» и дописали второй ключ `ID=` в ту же секцию — порча файла пользователя. Исправляется Task 1; исходное написание ключа при записи сохраняется.
2. **Ключ привязки — строка с префиксом**: `id:<uuid>` или `cs:<connect>|<name>` (нормализация — `strip` + `casefold`). Префикс обязателен, иначе суррогат столкнётся с UUID.
3. **Наши данные — только для баз.** У секций-групп нет ни истории, ни избранного.
4. **`OrderInList` — дробное число** (**[Ф]** реальные значения `60.6814814814813`, `-1`, `311296`). Разбирается как `float`; неразбираемое значение — не отказ, а `parse_error` у записи.
5. **Сортировка списка — стабильная по `(order is None, order)`**: записи с `OrderInList` идут по возрастанию, без него — сохраняют порядок появления в файле и уходят в конец. Опираться на порядок секций между сеансами нельзя (**[Ф]** каноникализация платформы), поэтому порядок в файле используется только как способ разрешить равенство.
6. **Создание отсутствующего `ibases.v8i` — эксклюзивное**, через `open(path, "xb")`, а не через `atomic_write`: семантика «создать, если никто не создал» защищает от гонки с штатным стартером, который может создать файл между нашей проверкой и записью. При сбое записи созданный файл удаляется: раз эксклюзивное создание удалось, файл создали мы и до нас его не было, а оставить на его месте пустой или обрезанный `ibases.v8i` хуже, чем не создать вовсе. Порядок веток обработки важен — `FileExistsError` разбирается до общего случая, иначе уборка снесёт чужой файл.
7. **`UnicodeEncodeError` при записи — отказ операции**, не пересохранение в UTF-8. `latin-1` декодирует любые байты, поэтому под фолбэком может лежать другая однобайтовая кодировка с кириллицей, и «починка» уничтожит данные необратимо.
8. **Запуск идёт по `/IBName`** — включая базы из общих списков (**[не проверено]**, решение дизайна §7). Веб-базы (`ConnectKind.WEB`) идут мимо `spawn`: открывается значение `ws` (**[не проверено]** форма URL).
9. **Время и UUID подаются аргументами** в чистые функции; координатор берёт `datetime.now(UTC)` и `uuid.uuid4()`. Иначе тесты истории и добавления записи недетерминированы.

## Чего в этом плане нет

Очистка кэша и ярлыки `.lnk` (ждут экспериментов на реальной машине), триггер watcher на Qt и настройки окна (план UI), сам UI, чтение `1cescmn.cfg` (решение 6 плана 2), редактирование общих списков (вне v1).

## Структура файлов плана

| Файл | Ответственность |
| --- | --- |
| `src/onecstarter/config/v8i.py` | *Правка:* регистронезависимый поиск ключа в секции |
| `src/onecstarter/security/secrets.py` | *Правка:* `redact_connect` — строка соединения без значений секретов |
| `src/onecstarter/services/model.py` | Типы модели списка и ключ привязки наших данных |
| `src/onecstarter/services/user_data.py` | `bases.json`: загрузка, сохранение, чистые мутации истории и избранного |
| `src/onecstarter/services/catalog.py` | Сборка записей из документов, общие списки, дерево |
| `src/onecstarter/services/edit.py` | Патч секции и его применение к документу (чистая часть) |
| `src/onecstarter/services/writer.py` | Цикл записи с повтором, создание файла, политика кодировки |
| `src/onecstarter/services/launch.py` | Сценарий запуска: команда → процесс или браузер → история |
| `src/onecstarter/services/workspace.py` | Координатор: состояние, перечитывание, операции, инъекция эффектов |
| `tests/fixtures/anonymized.v8i` | Обезличенный список баз с обязательными краевыми случаями |
| `tests/unit/test_v8i_sections.py` | *Правка:* тесты регистронезависимости |
| `tests/unit/test_fixture_v8i.py`, `test_model.py`, `test_user_data.py`, `test_catalog.py`, `test_edit.py`, `test_writer.py`, `test_services_launch.py`, `test_workspace.py` | Тесты соответствующих модулей |

Зависимости: `model ← catalog`, `model ← edit`, `model ← launch`; `user_data` автономен; `edit ← writer`; `workspace` импортирует всё перечисленное. `services` импортирует `config`, `domain`, `platform_1c`, `security`; обратной зависимости нет.

---

### Task 1: регистронезависимый доступ к ключам секции

**Files:**

- Modify: `src/onecstarter/config/v8i.py:34-51`
- Test: `tests/unit/test_v8i_sections.py`

**Interfaces:**

- Consumes: —
- Produces (используют Task 3–8): `V8iSection.get(key)` и `V8iSection.set(key, value)` находят ключ независимо от регистра его написания в файле; `set` сохраняет исходное написание уже существующего ключа и использует переданное написание для нового.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_v8i_sections.py`:

```python
def test_get_is_case_insensitive() -> None:
    doc = parse_v8i("[Демо]\r\nid=abc\r\nCONNECT=File=\"C:\\B\";\r\n".encode())
    section = doc.sections[0]
    assert section.get("ID") == "abc"
    assert section.id == "abc"
    assert section.connect == 'File="C:\\B";'


def test_set_keeps_original_key_spelling() -> None:
    doc = parse_v8i("[Демо]\r\nversion=8.3.24\r\n".encode())
    section = doc.sections[0]
    section.set("Version", "8.3.25")
    assert serialize_v8i(doc) == "[Демо]\r\nversion=8.3.25\r\n".encode()


def test_set_uses_requested_spelling_for_new_key() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\n".encode())
    doc.sections[0].set("Version", "8.3.25")
    assert b"Version=8.3.25" in serialize_v8i(doc)


def test_find_by_id_is_case_insensitive() -> None:
    doc = parse_v8i("[Демо]\r\nid=abc\r\nConnect=File=\"C:\\B\";\r\n".encode())
    assert doc.find_by_id("abc") is doc.sections[0]
```

Если в файле нет импорта `serialize_v8i` — добавить его в существующую строку импорта из `onecstarter.config.v8i`.

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_v8i_sections.py -q`
Expected: FAIL — `assert None == 'abc'` в трёх тестах поиска; тест нового ключа проходит уже сейчас.

- [ ] **Step 3: Исправить `get` и `set`**

В `src/onecstarter/config/v8i.py` заменить тела `get` и начало `set`:

```python
    def get(self, key: str) -> str | None:
        wanted = key.casefold()
        for line in self.lines:
            if isinstance(line, KeyValueLine) and line.key.casefold() == wanted:
                return line.value
        return None

    def set(self, key: str, value: str) -> None:
        wanted = key.casefold()
        for line in self.lines:
            if isinstance(line, KeyValueLine) and line.key.casefold() == wanted:
                line.value = value
                # Написание имени ключа в файле сохраняется: правка значения
                # не повод переименовывать чужой ключ.
                line.text = f"{line.key}={value}"
                return
```

Остаток `set` (добавление новой строки) не меняется.

Дополнить докстринг модуля строкой:

```python
"""Модель и разбор ibases.v8i: всё исходное сохраняется для round-trip.

Имена ключей сравниваются без учёта регистра. Регистр имён ключей в .v8i
экспериментально не проверялся — скилы проекта про него молчат, поэтому
регистронезависимое сравнение выбрано как безопасное: не найдя ключ,
записанный иначе, мы сочли бы его отсутствующим и дописали второй такой же.
При изменении значения написание ключа в файле сохраняется.
"""
```

Формулировка важна: утверждать «платформа пишет каноническое написание» нельзя —
это факт о поведении 1С, которого нет ни в одном скиле, а `CLAUDE.md` запрещает
утверждения без метки достоверности. Регистронезависимость здесь — наше решение
по соображениям безопасности, а не вывод из поведения платформы.

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_v8i_sections.py tests/unit/test_v8i_roundtrip.py -q`
Expected: PASS, включая все round-trip кейсы плана 1.

- [ ] **Step 5: Полный прогон и коммит**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy
git add src/onecstarter/config/v8i.py tests/unit/test_v8i_sections.py
git commit -m "fix: регистронезависимый поиск ключа в секции .v8i"
```

---

### Task 2: обезличенная фикстура `ibases.v8i`

**Files:**

- Create: `tests/fixtures/anonymized.v8i`
- Test: `tests/unit/test_fixture_v8i.py`

**Interfaces:**

- Consumes: `parse_v8i` из `onecstarter.config.v8i`
- Produces (используют Task 5, 7, 9): файл `tests/fixtures/anonymized.v8i` — 9 секций (6 баз + 3 группы), UTF-8 без BOM, `\r\n`, обязательные краевые случаи `CLAUDE.md`.

- [ ] **Step 1: Создать фикстуру**

Файл `tests/fixtures/anonymized.v8i`, кодировка UTF-8 **без BOM**, переводы строк `\r\n`, финальный перевод строки есть:

```ini
[Клиенты]
ID=11111111-1111-1111-1111-111111111111
OrderInList=-1
Folder=/
OrderInTree=16640
External=0
[Розница]
ID=22222222-2222-2222-2222-222222222222
OrderInList=-1
Folder=/Клиенты
OrderInTree=17664
External=0
[Пустая группа]
ID=33333333-3333-3333-3333-333333333333
OrderInList=-1
Folder=/
OrderInTree=18688
External=0
[Демо Бухгалтерия]
Connect=File="C:\Bases\Demo";
ID=44444444-4444-4444-4444-444444444444
OrderInList=60.6814814814813
OrderInTree=768
Folder=/Клиенты
Version=8.3.25
App=Auto
[Демо Розница]
Connect=File="C:\Bases\Retail";
ID=55555555-5555-5555-5555-555555555555
OrderInList=20.2271604938271
OrderInTree=1024
Folder=/Клиенты/Розница
Version=8.3.25.1633
App=ThinClient
XTest=1
[Учёт серверный]
Connect=Srvr="srv-1c";Ref="accounting";
ID=66666666-6666-6666-6666-666666666666
OrderInList=311296
OrderInTree=1280
Folder=/
DefaultVersion=8.3.25.1633
[Портал]
Connect=ws="http://web-server/resource/";
ID=77777777-7777-7777-7777-777777777777
OrderInList=311552
OrderInTree=1536
Folder=/
[Без идентификатора]
Connect=File="C:\Bases\Manual";
OrderInList=311808
Folder=/
[Потерянная]
Connect=File="C:\Bases\Orphan";
ID=88888888-8888-8888-8888-888888888888
OrderInList=312064
Folder=/Нет такой группы
```

Краевые случаи, ради которых фикстура и нужна: секция-группа без `Connect`; вложенная группа (`Folder=/Клиенты`); пустая группа; дробный `OrderInList`; неполная `Version=8.3.25`; неизвестный ключ `XTest=1`; клиент-серверная и `ws`-строки соединения; запись без `ID` (суррогатный ключ); запись с `Folder` на несуществующую группу.

- [ ] **Step 2: Написать тест фикстуры**

```python
# tests/unit/test_fixture_v8i.py
import codecs
from pathlib import Path

from onecstarter.config.v8i import parse_v8i, serialize_v8i

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"


def test_fixture_is_utf8_without_bom() -> None:
    data = FIXTURE.read_bytes()
    assert not data.startswith(codecs.BOM_UTF8)
    data.decode("utf-8")


def test_fixture_roundtrips_byte_for_byte() -> None:
    data = FIXTURE.read_bytes()
    assert serialize_v8i(parse_v8i(data)) == data


def test_fixture_carries_required_edge_cases() -> None:
    doc = parse_v8i(FIXTURE.read_bytes())
    by_name = {section.name: section for section in doc.sections}
    assert len(doc.sections) == 9
    assert sum(1 for section in doc.sections if section.is_group) == 3
    assert by_name["Розница"].folder == "/Клиенты"
    assert by_name["Демо Бухгалтерия"].get("OrderInList") == "60.6814814814813"
    assert by_name["Демо Бухгалтерия"].version == "8.3.25"
    assert by_name["Демо Розница"].get("XTest") == "1"
    assert by_name["Учёт серверный"].default_version == "8.3.25.1633"
    assert by_name["Учёт серверный"].connect == 'Srvr="srv-1c";Ref="accounting";'
    assert by_name["Портал"].connect == 'ws="http://web-server/resource/";'
    assert by_name["Без идентификатора"].id is None
    assert by_name["Потерянная"].folder == "/Нет такой группы"
    assert by_name["Пустая группа"].is_group
    assert all(section.folder != "/Пустая группа" for section in doc.sections)
```

Каждый из девяти краевых случаев обязан быть закреплён утверждением. Случай,
который лежит в фикстуре, но не проверяется, следующая правка снесёт молча —
и файл продолжит выглядеть достаточным. Последняя проверка выражает суть
пустой группы: секция есть, ссылок на неё нет.

- [ ] **Step 3: Прогнать тест**

Run: `uv run pytest tests/unit/test_fixture_v8i.py -q`
Expected: PASS. Падение на `test_fixture_roundtrips_byte_for_byte` означает, что редактор испортил кодировку или переводы строк — пересоздать файл, не править тест.

- [ ] **Step 4: Коммит**

```bash
git add tests/fixtures/anonymized.v8i tests/unit/test_fixture_v8i.py
git commit -m "тест: обезличенная фикстура списка баз с краевыми случаями"
```

---

### Task 3: `services/model.py` — модель записи и ключ привязки

**Files:**

- Create: `src/onecstarter/services/model.py`
- Test: `tests/unit/test_model.py`

**Interfaces:**

- Consumes: `V8iSection` (`config.v8i`), `ConnectKind`, `classify_connect` (`domain.connect`)
- Produces (используют Task 4–9):
  - `class InfobaseSource(Enum)`: `USER = "user"`, `COMMON = "common"`
  - `def normalize(text: str) -> str` — `strip` + `casefold`
  - `def binding_key(section_id: str | None, connect: str | None, name: str) -> str` — `"id:<uuid>"` либо `"cs:<connect>|<name>"`
  - `def parse_order(value: str | None) -> float | None`
  - `@dataclass(frozen=True) InfobaseItem` с полями: `key: str`, `name: str`, `folder: str`, `is_group: bool`, `connect: str | None`, `kind: ConnectKind`, `requested_version: str | None`, `section_default_version: str | None`, `app: str | None`, `source: InfobaseSource`, `order: float | None`, `section_id: str | None`, `favorite: bool`, `last_launched_at: datetime | None`, `launch_count: int`, `parse_error: str | None`
  - `def item_from_section(section: V8iSection, source: InfobaseSource) -> InfobaseItem` — наши данные не заполняет (значения по умолчанию)

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_model.py
from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.connect import ConnectKind
from onecstarter.services.model import (
    InfobaseSource,
    binding_key,
    item_from_section,
    normalize,
    parse_order,
)


def test_binding_key_prefers_id() -> None:
    assert binding_key("ABC", 'File="C:\\B";', "Демо") == "id:ABC"


def test_binding_key_falls_back_to_surrogate() -> None:
    key = binding_key(None, 'File="C:\\B";', "Демо")
    assert key.startswith("cs:")
    assert key.endswith("|демо")
    assert 'file="c:\\b";' not in key


def test_surrogate_never_carries_the_connection_string() -> None:
    # Connect несёт пароли, а ключи привязки индексируют bases.json и попадают
    # в сообщения об ошибках. Инвариант 5: секретов там быть не должно.
    key = binding_key(None, 'Srvr="s";Ref="b";Pwd="hunter2";', "Бухгалтерия")
    assert "hunter2" not in key
    assert "srvr" not in key


def test_surrogate_distinguishes_different_connections() -> None:
    first = binding_key(None, 'File="C:\\A";', "Демо")
    second = binding_key(None, 'File="C:\\B";', "Демо")
    assert first != second


def test_surrogate_is_case_and_space_insensitive() -> None:
    first = binding_key(None, ' File="C:\\B"; ', "Демо ")
    second = binding_key(None, 'file="c:\\b";', "демо")
    assert first == second


def test_surrogate_never_collides_with_id() -> None:
    assert binding_key(None, None, "Клиенты").startswith("cs:")
    assert binding_key("11111111-1111-1111-1111-111111111111", None, "x").startswith("id:")


def test_parse_order_accepts_fractional_and_negative() -> None:
    assert parse_order("60.6814814814813") == 60.6814814814813
    assert parse_order("-1") == -1.0
    assert parse_order("311296") == 311296.0
    assert parse_order(None) is None
    assert parse_order("мусор") is None


def test_item_from_group_section() -> None:
    doc = parse_v8i("[Клиенты]\r\nID=abc\r\nFolder=/\r\nOrderInList=-1\r\n".encode())
    item = item_from_section(doc.sections[0], InfobaseSource.USER)
    assert item.is_group
    assert item.name == "Клиенты"
    assert item.folder == "/"
    assert item.kind is ConnectKind.UNKNOWN
    assert item.order == -1.0
    assert item.parse_error is None


def test_item_from_base_section() -> None:
    raw = (
        "[Демо]\r\nConnect=Srvr=\"srv-1c\";Ref=\"acc\";\r\n"
        "ID=abc\r\nVersion=8.3.25\r\nDefaultVersion=8.3.25.1633\r\nApp=ThinClient\r\n"
    ).encode()
    item = item_from_section(parse_v8i(raw).sections[0], InfobaseSource.USER)
    assert not item.is_group
    assert item.kind is ConnectKind.SERVER
    assert item.requested_version == "8.3.25"
    assert item.section_default_version == "8.3.25.1633"
    assert item.app == "ThinClient"
    assert item.key == "id:abc"


def test_missing_folder_means_root() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\n".encode())
    assert item_from_section(doc.sections[0], InfobaseSource.USER).folder == "/"


def test_unparsed_line_becomes_parse_error() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\nмусор без равенства\r\n".encode())
    item = item_from_section(doc.sections[0], InfobaseSource.USER)
    assert item.parse_error is not None
    assert "мусор" not in item.parse_error  # содержимое строки в сообщение не тащим


def test_broken_order_becomes_parse_error() -> None:
    doc = parse_v8i("[Демо]\r\nConnect=File=\"C:\\B\";\r\nOrderInList=abc\r\n".encode())
    item = item_from_section(doc.sections[0], InfobaseSource.USER)
    assert item.order is None
    assert item.parse_error is not None
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_model.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.model'`.

- [ ] **Step 3: Реализовать модуль**

```python
# src/onecstarter/services/model.py
"""Модель записи списка баз и ключ привязки наших данных.

Ключ привязки: ID секции, если он есть, иначе суррогат из хеша строки
соединения и имени. Префикс обязателен, иначе суррогат столкнётся с UUID.
Слияние по ID — [Ф] скил v8i-format: Connect ключом идентичности
не является, допустимы несколько секций с одинаковой строкой соединения.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from onecstarter.config.v8i import KeyValueLine, V8iSection
from onecstarter.domain.connect import ConnectKind, classify_connect


_SURROGATE_DIGEST_LENGTH = 16


class InfobaseSource(Enum):
    USER = "user"
    COMMON = "common"


def normalize(text: str) -> str:
    return text.strip().casefold()


def binding_key(section_id: str | None, connect: str | None, name: str) -> str:
    if section_id:
        return f"id:{section_id}"
    # Строка соединения несёт пароли (Pwd, DBPwd, SPwd, wsp, wsppwd), а ключи
    # привязки индексируют bases.json и попадают в сообщения об ошибках.
    # Поэтому в ключ идёт только хеш: инвариант 5 запрещает секреты и в наших
    # файлах, и в сообщениях. Имя базы не секрет и остаётся открытым.
    digest = hashlib.sha256(normalize(connect or "").encode("utf-8")).hexdigest()
    return f"cs:{digest[:_SURROGATE_DIGEST_LENGTH]}|{normalize(name)}"


def parse_order(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class InfobaseItem:
    key: str
    name: str
    folder: str
    is_group: bool
    connect: str | None
    kind: ConnectKind
    requested_version: str | None
    section_default_version: str | None
    app: str | None
    source: InfobaseSource
    order: float | None
    section_id: str | None
    favorite: bool = False
    last_launched_at: datetime | None = None
    launch_count: int = 0
    parse_error: str | None = None


def item_from_section(section: V8iSection, source: InfobaseSource) -> InfobaseItem:
    connect = section.connect
    order_value = section.get("OrderInList")
    order = parse_order(order_value)
    problems: list[str] = []
    if order_value is not None and order is None:
        problems.append("OrderInList не число")
    unparsed = sum(
        1
        for line in section.lines
        if not isinstance(line, KeyValueLine) and line.text.strip()
    )
    if unparsed:
        problems.append(f"нераспознанных строк: {unparsed}")
    return InfobaseItem(
        key=binding_key(section.id, connect, section.name),
        name=section.name,
        folder=section.folder or "/",
        is_group=section.is_group,
        connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=section.version,
        section_default_version=section.default_version,
        app=section.get("App"),
        source=source,
        order=order,
        section_id=section.id,
        parse_error="; ".join(problems) or None,
    )
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_model.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/services/model.py tests/unit/test_model.py
git commit -m "feat: модель записи списка баз и ключ привязки наших данных"
```

---

### Task 4: `services/user_data.py` — `bases.json`

**Files:**

- Create: `src/onecstarter/services/user_data.py`
- Test: `tests/unit/test_user_data.py`

**Interfaces:**

- Consumes: `config.atomic.atomic_write`
- Produces (используют Task 5, 8, 9):
  - `SCHEMA_VERSION: int = 1`
  - `@dataclass(frozen=True) BaseUserData(favorite: bool = False, last_launched_at: datetime | None = None, launch_count: int = 0, last_client: str | None = None)`
  - `def load_user_data(path: Path) -> dict[str, BaseUserData]` — нет файла → `{}`; битый → переименовать в `<имя>.bad` и вернуть `{}`
  - `def save_user_data(path: Path, entries: Mapping[str, BaseUserData]) -> None` — создаёт каталог, пишет атомарно
  - `def record_launch(entries, key: str, client: str, when: datetime) -> dict[str, BaseUserData]` — чистая
  - `def set_favorite(entries, key: str, value: bool) -> dict[str, BaseUserData]` — чистая
  - `def rekey(entries, old_key: str, new_key: str) -> dict[str, BaseUserData]` — чистая

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_user_data.py
import json
from datetime import UTC, datetime
from pathlib import Path

from onecstarter.services.user_data import (
    BaseUserData,
    load_user_data,
    record_launch,
    rekey,
    save_user_data,
    set_favorite,
)

WHEN = datetime(2026, 8, 4, 7, 12, 44, tzinfo=UTC)


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_user_data(tmp_path / "bases.json") == {}


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "bases.json"
    entries = {"id:abc": BaseUserData(True, WHEN, 17, "thin")}
    save_user_data(path, entries)
    assert load_user_data(path) == entries


def test_saved_file_is_schema_versioned(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    save_user_data(path, {"id:abc": BaseUserData(launch_count=1)})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert "id:abc" in payload["entries"]


def test_broken_file_is_moved_aside(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    path.write_text("{не json", encoding="utf-8")
    assert load_user_data(path) == {}
    assert (tmp_path / "bases.json.bad").read_text(encoding="utf-8") == "{не json"
    assert not path.exists()


def test_unknown_schema_is_treated_as_broken(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    path.write_text('{"schema": 99, "entries": {}}', encoding="utf-8")
    assert load_user_data(path) == {}
    assert (tmp_path / "bases.json.bad").exists()


def test_record_launch_is_pure_and_counts(tmp_path: Path) -> None:
    entries: dict[str, BaseUserData] = {}
    once = record_launch(entries, "id:abc", "thin", WHEN)
    twice = record_launch(once, "id:abc", "thick", WHEN)
    assert entries == {}
    assert once["id:abc"].launch_count == 1
    assert twice["id:abc"].launch_count == 2
    assert twice["id:abc"].last_client == "thick"
    assert twice["id:abc"].last_launched_at == WHEN


def test_record_launch_keeps_favorite() -> None:
    entries = {"id:abc": BaseUserData(favorite=True)}
    assert record_launch(entries, "id:abc", "thin", WHEN)["id:abc"].favorite


def test_set_favorite_toggles() -> None:
    entries = set_favorite({}, "id:abc", True)
    assert entries["id:abc"].favorite
    assert not set_favorite(entries, "id:abc", False)["id:abc"].favorite


def test_rekey_moves_entry() -> None:
    entries = {"cs:0123456789abcdef|демо": BaseUserData(launch_count=3)}
    moved = rekey(entries, "cs:0123456789abcdef|демо", "id:abc")
    assert moved == {"id:abc": BaseUserData(launch_count=3)}


def test_rekey_of_absent_entry_is_noop() -> None:
    assert rekey({}, "cs:нет", "id:abc") == {}
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_user_data.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.user_data'`.

- [ ] **Step 3: Реализовать модуль**

```python
# src/onecstarter/services/user_data.py
"""Наши данные о базах: избранное и история запусков.

Файл лежит в %APPDATA%\\OneCStarter\\bases.json и принадлежит только этому
слою. В ibases.v8i свои ключи не пишем — привязка идёт ключом из model.
Время хранится в UTC; в локальное переводит слой представления.

Битый файл не чинится и не затирается: он уезжает в <имя>.bad, а работа
продолжается с пустыми данными. Молча съеденная история — потеря без следа.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BaseUserData:
    favorite: bool = False
    last_launched_at: datetime | None = None
    launch_count: int = 0
    last_client: str | None = None


class UserDataUnavailableError(Exception):
    """Файл наших данных существует, но прочитать или убрать его не удалось."""


def load_user_data(path: Path) -> dict[str, BaseUserData]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        # Файл есть, но недоступен: блокировка, права, отвалившийся сетевой диск.
        # Это не порча содержимого, и подменять его пустыми данными нельзя —
        # следующее сохранение затрёт историю пользователя.
        raise UserDataUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
        entries = payload["entries"]
        if not isinstance(entries, dict):
            raise ValueError("entries не объект")
        return {str(key): _decode(value) for key, value in entries.items()}
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_user_data(path: Path, entries: Mapping[str, BaseUserData]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "entries": {key: _encode(value) for key, value in entries.items()},
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, text.encode("utf-8"))


def record_launch(
    entries: Mapping[str, BaseUserData], key: str, client: str, when: datetime
) -> dict[str, BaseUserData]:
    if when.tzinfo is None:
        # astimezone на наивном времени молча считает его локальным и пересчитывает.
        # Архитектура требует UTC везде, кроме показа, — ловим ошибку здесь.
        raise ValueError("Время запуска должно быть с часовым поясом, ожидается UTC")
    current = entries.get(key, BaseUserData())
    updated = replace(
        current,
        last_launched_at=when.astimezone(UTC),
        launch_count=current.launch_count + 1,
        last_client=client,
    )
    return {**entries, key: updated}


def set_favorite(
    entries: Mapping[str, BaseUserData], key: str, value: bool
) -> dict[str, BaseUserData]:
    current = entries.get(key, BaseUserData())
    return {**entries, key: replace(current, favorite=value)}


def rekey(
    entries: Mapping[str, BaseUserData], old_key: str, new_key: str
) -> dict[str, BaseUserData]:
    if old_key not in entries:
        return dict(entries)
    moved = dict(entries)
    moved[new_key] = moved.pop(old_key)
    return moved


def _move_aside(path: Path) -> dict[str, BaseUserData]:
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError as error:
        # Не сумев убрать испорченный файл, продолжать с пустыми данными нельзя:
        # первое же сохранение затрёт то, что пользователь мог бы из него достать.
        raise UserDataUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"
        ) from error
    return {}


def _encode(data: BaseUserData) -> dict[str, Any]:
    stamp = data.last_launched_at
    return {
        "favorite": data.favorite,
        "last_launched_at": (
            stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None
        ),
        "launch_count": data.launch_count,
        "last_client": data.last_client,
    }


def _decode(value: Any) -> BaseUserData:
    if not isinstance(value, dict):
        raise ValueError("запись не объект")
    stamp = value.get("last_launched_at")
    return BaseUserData(
        favorite=bool(value.get("favorite", False)),
        last_launched_at=datetime.fromisoformat(stamp) if stamp else None,
        launch_count=int(value.get("launch_count", 0)),
        last_client=value.get("last_client"),
    )
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_user_data.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/services/user_data.py tests/unit/test_user_data.py
git commit -m "feat: наши данные о базах — избранное и история запусков"
```

---

### Task 5: `services/catalog.py` — сборка списка и дерево

**Files:**

- Create: `src/onecstarter/services/catalog.py`
- Test: `tests/unit/test_catalog.py`

**Interfaces:**

- Consumes: `model` (Task 3), `user_data.BaseUserData` (Task 4), `config.v8i.parse_v8i`, `config.cestart_cfg.{parse_cestart_cfg, common_infobase_sources}`
- Produces (используют Task 9):
  - `def items_from_document(document: V8iDocument, source: InfobaseSource, entries: Mapping[str, BaseUserData]) -> list[InfobaseItem]` — отсортировано по решению 5
  - `@dataclass(frozen=True) CommonListError(path: Path, message: str)`
  - `def load_common_items(paths: Iterable[Path], entries) -> tuple[list[InfobaseItem], list[CommonListError]]`
  - `def common_list_paths(cfg_paths: Iterable[Path]) -> list[Path]` — из `1cestart.cfg` в порядке уровней, без дублей
  - `@dataclass(frozen=True) TreeNode(item: InfobaseItem, children: tuple[TreeNode, ...], orphan: bool)`
  - `def build_tree(items: Sequence[InfobaseItem]) -> list[TreeNode]`

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_catalog.py
import codecs
from pathlib import Path

from onecstarter.config.v8i import parse_v8i
from onecstarter.services.catalog import (
    build_tree,
    common_list_paths,
    items_from_document,
    load_common_items,
)
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.user_data import BaseUserData

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"


def _fixture_items(
    entries: dict[str, BaseUserData] | None = None,
) -> list[InfobaseItem]:
    document = parse_v8i(FIXTURE.read_bytes())
    return items_from_document(document, InfobaseSource.USER, entries or {})


def test_items_cover_every_section() -> None:
    items = _fixture_items()
    assert len(items) == 9
    assert sum(1 for item in items if item.is_group) == 3


def test_items_sorted_by_order_in_list() -> None:
    orders = [item.order for item in _fixture_items()]
    assert orders == sorted(orders, key=lambda value: (value is None, value))


def test_user_data_is_merged_by_key() -> None:
    entries = {"id:44444444-4444-4444-4444-444444444444": BaseUserData(True, None, 5, "thin")}
    demo = next(item for item in _fixture_items(entries) if item.name == "Демо Бухгалтерия")
    assert demo.favorite
    assert demo.launch_count == 5


def test_user_data_is_merged_by_surrogate_key() -> None:
    key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    entries = {key: BaseUserData(favorite=True)}
    item = next(item for item in _fixture_items(entries) if item.name == "Без идентификатора")
    assert item.favorite


def test_tree_nests_groups_and_bases() -> None:
    nodes = build_tree(_fixture_items())
    by_name = {node.item.name: node for node in nodes}
    clients = by_name["Клиенты"]
    assert {child.item.name for child in clients.children} == {"Демо Бухгалтерия", "Розница"}
    retail = next(child for child in clients.children if child.item.name == "Розница")
    assert {child.item.name for child in retail.children} == {"Демо Розница"}


def test_empty_group_has_no_children() -> None:
    nodes = build_tree(_fixture_items())
    assert next(node for node in nodes if node.item.name == "Пустая группа").children == ()


def test_orphan_folder_shows_in_root_and_is_marked() -> None:
    nodes = build_tree(_fixture_items())
    orphan = next(node for node in nodes if node.item.name == "Потерянная")
    assert orphan.orphan


def test_common_list_paths_are_deduplicated(tmp_path: Path) -> None:
    first = tmp_path / "all.cfg"
    second = tmp_path / "local.cfg"
    text = "CommonInfoBases=C:\\Common\\shared.v8i\r\n"
    first.write_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
    second.write_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
    assert common_list_paths([first, second, tmp_path / "нет.cfg"]) == [
        Path("C:\\Common\\shared.v8i")
    ]


def test_common_items_are_read_only_source(tmp_path: Path) -> None:
    shared = tmp_path / "shared.v8i"
    shared.write_bytes("[Общая]\r\nConnect=File=\"C:\\Bases\\Shared\";\r\n".encode())
    items, errors = load_common_items([shared], {})
    assert errors == []
    assert [item.source for item in items] == [InfobaseSource.COMMON]


def test_unreadable_common_list_is_reported_not_raised(tmp_path: Path) -> None:
    items, errors = load_common_items([tmp_path / "нет.v8i"], {})
    assert items == []
    assert len(errors) == 1
    assert errors[0].path == tmp_path / "нет.v8i"
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_catalog.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.catalog'`.

- [ ] **Step 3: Реализовать модуль**

```python
# src/onecstarter/services/catalog.py
"""Сборка модели списка баз из источников и построение дерева.

Источники: пользовательский ibases.v8i (чтение и запись) и общие списки
из ключа CommonInfoBases файлов 1cestart.cfg (только чтение). Наши данные
подмешиваются по ключу привязки.

Порядок секций между сеансами не сохраняется ([Ф] перезапись платформы
каноникализирует весь файл), поэтому сортировка идёт по OrderInList,
а исходный порядок разрешает только равенство.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from onecstarter.config.cestart_cfg import common_infobase_sources, parse_cestart_cfg
from onecstarter.config.v8i import V8iDocument, parse_v8i
from onecstarter.services.model import InfobaseItem, InfobaseSource, item_from_section
from onecstarter.services.user_data import BaseUserData


@dataclass(frozen=True)
class CommonListError:
    path: Path
    message: str


@dataclass(frozen=True)
class TreeNode:
    item: InfobaseItem
    children: tuple["TreeNode", ...]
    orphan: bool


def items_from_document(
    document: V8iDocument,
    source: InfobaseSource,
    entries: Mapping[str, BaseUserData],
) -> list[InfobaseItem]:
    items = [item_from_section(section, source) for section in document.sections]
    merged = [_merge(item, entries) for item in items]
    return sorted(merged, key=lambda item: (item.order is None, item.order or 0.0))


def common_list_paths(cfg_paths: Iterable[Path]) -> list[Path]:
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


def load_common_items(
    paths: Iterable[Path], entries: Mapping[str, BaseUserData]
) -> tuple[list[InfobaseItem], list[CommonListError]]:
    items: list[InfobaseItem] = []
    errors: list[CommonListError] = []
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError as error:
            errors.append(CommonListError(path, str(error)))
            continue
        items.extend(items_from_document(parse_v8i(data), InfobaseSource.COMMON, entries))
    return items, errors


def build_tree(items: Sequence[InfobaseItem]) -> list[TreeNode]:
    group_paths = {_group_path(item) for item in items if item.is_group}
    children: dict[str, list[InfobaseItem]] = {path: [] for path in group_paths}
    roots: list[tuple[InfobaseItem, bool]] = []
    for item in items:
        parent = _normalized_folder(item.folder)
        if parent == "/":
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
        _node(child, children, False) for child in children.get(_group_path(item), [])
    )
    return TreeNode(item, nested, orphan)


def _group_path(item: InfobaseItem) -> str:
    parent = _normalized_folder(item.folder)
    return item.name if parent == "/" else f"{parent}/{item.name}"


def _normalized_folder(folder: str) -> str:
    stripped = folder.strip()
    if stripped in ("", "/"):
        return "/"
    return stripped.strip("/")


def _merge(item: InfobaseItem, entries: Mapping[str, BaseUserData]) -> InfobaseItem:
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
```

Пояснение к `_normalized_folder`: `Folder=/Клиенты` и `Folder=Клиенты` — один и тот же
родитель; корень записывается как `/`, отсутствие ключа модель уже привела к `/`.

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_catalog.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/services/catalog.py tests/unit/test_catalog.py
git commit -m "feat: сборка списка баз из источников и построение дерева"
```

---

### Task 6: `services/edit.py` — патч секции и его применение

**Files:**

- Create: `src/onecstarter/services/edit.py`
- Test: `tests/unit/test_edit.py`

**Interfaces:**

- Consumes: `config.v8i.{V8iDocument, V8iSection}`, `model.binding_key`
- Produces (использует Task 7, 9):
  - `class PatchKind(Enum)`: `ADD`, `UPDATE`, `REMOVE`
  - `class TargetGoneError(Exception)`
  - `@dataclass(frozen=True) SectionPatch(kind: PatchKind, target_key: str | None = None, name: str | None = None, new_name: str | None = None, changes: Mapping[str, str | None] = ...)`
  - `def find_target(document: V8iDocument, key: str) -> V8iSection | None`
  - `def apply_patch(document: V8iDocument, patch: SectionPatch, new_id: str) -> None`

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_edit.py
import pytest

from onecstarter.config.v8i import parse_v8i, serialize_v8i
from onecstarter.services.edit import (
    PatchKind,
    SectionPatch,
    TargetGoneError,
    apply_patch,
    find_target,
)

TWO_SECTIONS = (
    "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\nVersion=8.3.25\r\n"
    "[Ручная]\r\nConnect=File=\"C:\\Bases\\Manual\";\r\n"
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
    document = parse_v8i(b"")
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
    document = parse_v8i(TWO_SECTIONS)
    apply_patch(
        document,
        SectionPatch(PatchKind.UPDATE, target_key="id:abc", changes={"Folder": "/Архив"}),
        NEW_ID,
    )
    assert document.sections[0].folder == "/Архив"
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_edit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.edit'`.

- [ ] **Step 3: Реализовать модуль**

```python
# src/onecstarter/services/edit.py
"""Патч секции ibases.v8i и его применение к разобранному документу.

Единица записи — патч, а не «сохранить документ»: при внешнем изменении
файла патч переигрывается на свежем состоянии (см. writer). Цель ищется
по ID или суррогатному ключу, но никогда по позиции секции — порядок
секций между сеансами не сохраняется ([Ф] каноникализация платформы).

Состав ключей новой записи: имя секции, Connect, наш ID и OrderInList=-1.
Известен [Ф] состав, который мастер стартера пишет для секции-группы;
для секции-базы он не снят, поэтому OrderInTree и External не выдумываем.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from onecstarter.config.v8i import KeyValueLine, V8iDocument, V8iSection
from onecstarter.services.model import binding_key


class PatchKind(Enum):
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


class TargetGoneError(Exception):
    """Секция, которую собирались править, исчезла из файла."""


@dataclass(frozen=True)
class SectionPatch:
    kind: PatchKind
    target_key: str | None = None
    name: str | None = None
    new_name: str | None = None
    changes: Mapping[str, str | None] = field(default_factory=dict)


def find_target(document: V8iDocument, key: str) -> V8iSection | None:
    for section in document.sections:
        if binding_key(section.id, section.connect, section.name) == key:
            return section
    return None


def apply_patch(document: V8iDocument, patch: SectionPatch, new_id: str) -> None:
    if patch.kind is PatchKind.ADD:
        _apply_add(document, patch, new_id)
        return
    if patch.target_key is None:
        raise ValueError("Для UPDATE и REMOVE нужен target_key")
    section = find_target(document, patch.target_key)
    if patch.kind is PatchKind.REMOVE:
        # Идемпотентно: пользователь хотел, чтобы записи не было — её нет.
        if section is not None:
            document.remove_section(section)
        return
    if section is None:
        raise TargetGoneError(f"Запись {patch.target_key} удалена извне")
    _apply_update(section, patch, new_id)


def _apply_add(document: V8iDocument, patch: SectionPatch, new_id: str) -> None:
    if not patch.name:
        raise ValueError("Для ADD нужно имя секции")
    section = document.append_section(patch.name)
    for key, value in patch.changes.items():
        if value is not None:
            section.set(key, value)
    section.set("ID", new_id)
    section.set("OrderInList", "-1")


def _apply_update(section: V8iSection, patch: SectionPatch, new_id: str) -> None:
    if patch.new_name:
        _rename(section, patch.new_name)
    for key, value in patch.changes.items():
        if value is None:
            _remove_key(section, key)
        else:
            section.set(key, value)
    # ID дописывается только той записи, которую пользователь правит через нас.
    if section.id is None and not section.is_group:
        section.set("ID", new_id)


def _rename(section: V8iSection, new_name: str) -> None:
    section.header.text = f"[{new_name}]"


def _remove_key(section: V8iSection, key: str) -> None:
    wanted = key.casefold()
    section.lines[:] = [
        line
        for line in section.lines
        if not (isinstance(line, KeyValueLine) and line.key.casefold() == wanted)
    ]
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_edit.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/services/edit.py tests/unit/test_edit.py
git commit -m "feat: патч секции списка баз и его применение к документу"
```

---

### Task 7: `services/writer.py` — цикл записи с повтором

**Files:**

- Create: `src/onecstarter/services/writer.py`
- Test: `tests/unit/test_writer.py`

**Interfaces:**

- Consumes: `edit.{SectionPatch, apply_patch}`, `config.atomic.{read_with_snapshot, atomic_write_if_unchanged, ExternalChangeError}`, `config.v8i.{parse_v8i, serialize_v8i}`
- Produces (использует Task 9):
  - `class ConcurrentEditError(Exception)`
  - `class EncodingRejectedError(Exception)`
  - `def write_patch(path: Path, patch: SectionPatch, new_id: str, attempts: int = 3) -> bytes` — возвращает записанные байты, чтобы координатор обновил снапшот без повторного чтения

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_writer.py
from pathlib import Path

import pytest

from onecstarter.config import atomic
from onecstarter.config.v8i import parse_v8i
from onecstarter.services.edit import PatchKind, SectionPatch
from onecstarter.services.writer import (
    ConcurrentEditError,
    EncodingRejectedError,
    write_patch,
)

NEW_ID = "99999999-9999-9999-9999-999999999999"
ONE_SECTION = "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\n".encode()

ADD = SectionPatch(PatchKind.ADD, name="Новая", changes={"Connect": 'File="C:\\Bases\\New";'})


def test_creates_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    write_patch(path, ADD, NEW_ID)
    document = parse_v8i(path.read_bytes())
    assert [section.name for section in document.sections] == ["Новая"]


def test_appends_to_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    write_patch(path, ADD, NEW_ID)
    names = [section.name for section in parse_v8i(path.read_bytes()).sections]
    assert names == ["Демо", "Новая"]


def test_keeps_source_encoding(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes("[Демо]\r\nConnect=File=\"C:\\B\";\r\n".encode("cp1251"))
    write_patch(path, ADD, NEW_ID)
    data = path.read_bytes()
    assert "Новая".encode("cp1251") in data
    assert "Новая".encode() not in data


def test_external_change_is_replayed_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    original = atomic.atomic_write_if_unchanged
    state = {"first": True}

    def meddling(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        if state["first"]:
            state["first"] = False
            # Штатный стартер дописал свою секцию между нашим чтением и записью.
            target.write_bytes(
                ONE_SECTION + "[Чужая]\r\nConnect=File=\"C:\\Bases\\Other\";\r\n".encode()
            )
        original(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", meddling)
    write_patch(path, ADD, NEW_ID)
    names = [section.name for section in parse_v8i(path.read_bytes()).sections]
    assert names == ["Демо", "Чужая", "Новая"]


def test_gives_up_after_three_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)

    def always_changed(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        raise atomic.ExternalChangeError("изменён извне")

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", always_changed)
    with pytest.raises(ConcurrentEditError):
        write_patch(path, ADD, NEW_ID)


def test_unencodable_text_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    # 0x98 — единственный неопределённый байт cp1251, поэтому файл не читается
    # ни в UTF-8, ни в cp1251 и достаётся фолбэку latin-1. Проверено: другие
    # «мусорные» байты (0x81, 0x8d, 0xff) в cp1251 разбираются, и тогда
    # кириллица записалась бы штатно.
    path.write_bytes(b"[Demo]\r\nConnect=File=\"C:\\B\";\r\nX=\x98\r\n")
    with pytest.raises(EncodingRejectedError):
        write_patch(path, SectionPatch(PatchKind.ADD, name="Кириллица", changes={}), NEW_ID)
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_writer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.writer'`.

- [ ] **Step 3: Реализовать модуль**

```python
# src/onecstarter/services/writer.py
"""Цикл записи патча в ibases.v8i с переигрыванием при внешнем изменении.

Файл параллельно правит штатный 1cestart.exe и перезаписывает целиком
([Ф] скил v8i-format), поэтому расхождение снапшота — рядовое событие:
патч просто накладывается заново на свежее состояние. Чужие правки
в других секциях и ключах переживают запись; совпавший ключ получает
значение пользователя — он только что его задал.

Ретраев по PermissionError нет: файл не блокируется ни открытым стартером,
ни работающим клиентом ([Ф] T-02.4), поэтому отказ в доступе — настоящая
проблема (права, антивирус), и повторы её только спрячут.
"""

import os
from pathlib import Path

from onecstarter.config.atomic import (
    ExternalChangeError,
    atomic_write_if_unchanged,
    read_with_snapshot,
)
from onecstarter.config.v8i import V8iDocument, parse_v8i, serialize_v8i
from onecstarter.services.edit import SectionPatch, apply_patch


class ConcurrentEditError(Exception):
    """Файл меняется извне быстрее, чем мы успеваем записать патч."""


class EncodingRejectedError(Exception):
    """Текст не кодируется в исходную кодировку файла."""


def write_patch(path: Path, patch: SectionPatch, new_id: str, attempts: int = 3) -> bytes:
    for _ in range(attempts):
        try:
            data, snapshot = read_with_snapshot(path)
        except FileNotFoundError:
            created = _create(path, patch, new_id)
            if created is not None:
                return created
            continue
        document = parse_v8i(data)
        apply_patch(document, patch, new_id)
        payload = _serialize(document)
        try:
            atomic_write_if_unchanged(path, payload, snapshot)
        except ExternalChangeError:
            continue
        return payload
    raise ConcurrentEditError(
        f"{path} меняется извне: патч не удалось применить за {attempts} попытки"
    )


def _create(path: Path, patch: SectionPatch, new_id: str) -> bytes | None:
    """Создать файл эксклюзивно. `None` — кто-то создал его раньше нас."""
    document = parse_v8i(b"")
    apply_patch(document, patch, new_id)
    payload = _serialize(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        # Файл появился между нашей проверкой и созданием: его создал кто-то
        # другой, трогать его нельзя — цикл пойдёт обычным путём.
        return None
    except BaseException:
        # Эксклюзивное создание удалось, значит файл создали мы, и до нас его
        # не было. Убираем за собой, чтобы не оставить битый ibases.v8i там,
        # где раньше не было ничего.
        path.unlink(missing_ok=True)
        raise
    return payload


def _serialize(document: V8iDocument) -> bytes:
    try:
        return serialize_v8i(document)
    except UnicodeEncodeError as error:
        raise EncodingRejectedError(
            "Файл прочитан в кодировке, в которую новый текст не записывается. "
            "Пересохранение в UTF-8 не выполняется: под фолбэковой кодировкой "
            "может лежать другая однобайтовая кодировка, и перекодирование "
            "необратимо испортит данные."
        ) from error
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_writer.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/services/writer.py tests/unit/test_writer.py
git commit -m "feat: цикл записи патча с переигрыванием при внешнем изменении"
```

---

### Task 8: `services/launch.py` — сценарий запуска

**Files:**

- Create: `src/onecstarter/services/launch.py`
- Modify: `src/onecstarter/security/secrets.py`
- Test: `tests/unit/test_services_launch.py`

**Interfaces:**

- Consumes: `domain.selection.resolve_version`, `domain.launch.{choose_client, convention_for, build_arguments, build_launch_command, ClientKind}`, `domain.connect.{ConnectKind, parse_connect, find_fragment}`, `platform_1c.process.spawn`, `model.InfobaseItem`
- Produces (использует Task 9):
  - `def redact_connect(connect: str) -> str` в `security.secrets` — значения секретных ключей заменены на `***`
  - `class LaunchKind(Enum)`: `PROCESS`, `BROWSER`
  - `@dataclass(frozen=True) LaunchOutcome(kind: LaunchKind, client: ClientKind | None, command_line: str | None, url: str | None, pid: int | None, version: VersionNumber | None)`
  - `class LaunchError(Exception)`
  - `def launch_infobase(item, *, installations, cfg_rules, conventions, default_app, forced_client=None, spawn=spawn, open_url=webbrowser.open) -> LaunchOutcome`

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_services_launch.py
from pathlib import Path

import pytest

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.launch import ClientConvention, ClientKind, LaunchCommand
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.security.secrets import redact_connect
from onecstarter.services.launch import LaunchError, LaunchKind, launch_infobase
from onecstarter.services.model import InfobaseItem, InfobaseSource, item_from_section

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


def _item(raw: str) -> InfobaseItem:
    return item_from_section(parse_v8i(raw.encode()).sections[0], InfobaseSource.USER)


def test_redact_connect_hides_values_not_names() -> None:
    redacted = redact_connect('Srvr="srv-1c";Ref="acc";DBPwd=тайна;Usr=Иванов;')
    assert "тайна" not in redacted
    assert "DBPwd=***" in redacted
    assert "Usr=Иванов" in redacted


def test_launch_spawns_thin_client_by_ibname() -> None:
    calls: list[LaunchCommand] = []
    outcome = launch_infobase(
        _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        spawn=lambda command: (calls.append(command), 4242)[1],
        open_url=lambda url: pytest.fail("браузер не должен открываться"),
    )
    assert outcome.kind is LaunchKind.PROCESS
    assert outcome.pid == 4242
    assert outcome.client is ClientKind.THIN
    assert calls[0].executable.name == "1cv8c.exe"
    assert '/IBName"Демо"' in calls[0].arguments
    assert "/AppAutoCheckVersion-" in calls[0].arguments


def test_forced_designer_uses_thick_executable() -> None:
    calls: list[LaunchCommand] = []
    launch_infobase(
        _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        forced_client=ClientKind.DESIGNER,
        spawn=lambda command: (calls.append(command), 1)[1],
        open_url=lambda url: pytest.fail("браузер не должен открываться"),
    )
    assert calls[0].arguments.startswith("DESIGNER ")
    assert calls[0].executable.name == "1cv8.exe"


def test_web_base_opens_browser() -> None:
    opened: list[str] = []
    outcome = launch_infobase(
        _item('[Портал]\r\nConnect=ws="http://web-server/resource/";\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        spawn=lambda command: pytest.fail("процесс не должен порождаться"),
        open_url=lambda url: opened.append(url) or True,
    )
    assert outcome.kind is LaunchKind.BROWSER
    assert opened == ["http://web-server/resource/"]


def test_not_installed_version_fails_before_spawn() -> None:
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.99.1\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "8.3.99.1" in str(error.value)


def test_group_cannot_be_launched() -> None:
    with pytest.raises(LaunchError):
        launch_infobase(
            _item("[Клиенты]\r\nFolder=/\r\n"),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )


def test_error_message_hides_secret_values() -> None:
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Тайная]\r\nConnect=Srvr="s";Ref="r";DBPwd=тайна;\r\nVersion=8.3.99.1\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "тайна" not in str(error.value)
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `uv run pytest tests/unit/test_services_launch.py -q`
Expected: FAIL — `ImportError: cannot import name 'redact_connect'`.

- [ ] **Step 3: Добавить `redact_connect` в `security/secrets.py`**

Добавить импорт в начало файла и функцию в конец:

```python
from onecstarter.domain.connect import parse_connect
```

```python
def redact_connect(connect: str) -> str:
    """Строка соединения без значений секретных ключей — для показа человеку.

    Результат собирается заново из разобранных фрагментов, а не правится
    поиском и заменой в исходной строке: значение секретного ключа в вывод
    не переносится вообще, поэтому утечка невозможна по построению.
    Замена по совпадению значения так не умеет — parse_connect снимает
    кавычки, и значение с экранированной кавычкой в исходном тексте
    не находится, а одинаковые значения у секретного и обычного ключа
    затираются оба.

    Строка при этом нормализуется: исходные кавычки, пробелы и фрагменты
    без «=» не сохраняются. Это допустимо — результат идёт в сообщение
    пользователю и обратно в .v8i не пишется никогда.
    """
    fragments = parse_connect(connect)
    if not fragments:
        return connect
    parts = [
        f"{fragment.name}=***"
        if is_secret_key(fragment.name) and fragment.value
        else f"{fragment.name}={fragment.value}"
        for fragment in fragments
    ]
    return ";".join(parts) + ";"
```

Замена по совпадению значения (`connect.replace(fragment.value, "***")`) здесь не работает
и была исправлена по итогам ревью Task 8: `parse_connect` снимает кавычки, поэтому пароль
вида `Pwd="sec""ret";` в исходном тексте не находится и остаётся в сообщении целиком —
проверено на реальном коде. Тест обязан брать пароль с экранированной кавычкой: простой
пароль ловится и сломанной реализацией.

Цикла импорта здесь нет: `domain.connect` ни от чего не зависит, все `__init__.py`
пакетов пусты. Зависимость `security → domain.connect` односторонняя.

- [ ] **Step 4: Реализовать `services/launch.py`**

```python
# src/onecstarter/services/launch.py
"""Сценарий запуска базы: команда → процесс или браузер.

Своей логики почти нет — склеиваются готовые слои. Запуск идёт по /IBName:
платформа сама читает из ibases.v8i ключи WA, AdditionalParameters и прочие
([Ф] скил platform-launch), а секреты из строки соединения не попадают
в argv. Базы из общих списков запускаются так же — [не проверено],
проверить экспериментом (дизайн плана 3, §7).

Ошибки поднимаются до порождения процесса: неустановленная версия видна
пользователю заранее, а не после падения клиента.
"""

import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from onecstarter.domain.connect import ConnectKind, find_fragment, parse_connect
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import (
    ClientConvention,
    ClientKind,
    LaunchCommand,
    build_arguments,
    build_launch_command,
    choose_client,
    convention_for,
)
from onecstarter.domain.selection import ResolutionSource, resolve_version
from onecstarter.domain.version import Installation, VersionNumber
from onecstarter.platform_1c.process import spawn as spawn_process
from onecstarter.security.secrets import redact_connect
from onecstarter.services.model import InfobaseItem


class LaunchKind(Enum):
    PROCESS = "process"
    BROWSER = "browser"


@dataclass(frozen=True)
class LaunchOutcome:
    kind: LaunchKind
    client: ClientKind | None
    command_line: str | None
    url: str | None
    pid: int | None
    version: VersionNumber | None


class LaunchError(Exception):
    """Запуск невозможен; сообщение безопасно показывать пользователю."""


def launch_infobase(
    item: InfobaseItem,
    *,
    installations: Sequence[Installation],
    cfg_rules: Sequence[DefaultVersionRule],
    conventions: Sequence[ClientConvention],
    default_app: str | None,
    forced_client: ClientKind | None = None,
    spawn: Callable[[LaunchCommand], int] = spawn_process,
    open_url: Callable[[str], bool] = webbrowser.open,
) -> LaunchOutcome:
    if item.is_group or item.connect is None:
        raise LaunchError(f"«{item.name}» — группа, а не информационная база")

    if item.kind is ConnectKind.WEB:
        return _launch_web(item, open_url)

    resolution = resolve_version(
        item.requested_version,
        item.section_default_version,
        cfg_rules,
        [installation.version for installation in installations],
    )
    if resolution.version is None:
        raise LaunchError(_version_problem(item, resolution.source))
    installation = next(
        installation
        for installation in installations
        if installation.version == resolution.version
    )
    convention = convention_for(resolution.version, conventions)
    if convention is None:
        raise LaunchError(
            f"Для версии {resolution.version} нет соглашения раскладки в реестре версий"
        )
    choice = choose_client(item.app, default_app, forced_client)
    arguments = build_arguments(
        choice.client,
        ib_name=item.name,
        auto_check_version=False,
        auto_check_mode=choice.auto_check_mode,
    )
    command = build_launch_command(installation, convention, choice.client, arguments)
    pid = spawn(command)
    return LaunchOutcome(
        kind=LaunchKind.PROCESS,
        client=choice.client,
        command_line=command.command_line,
        url=None,
        pid=pid,
        version=resolution.version,
    )


def _launch_web(item: InfobaseItem, open_url: Callable[[str], bool]) -> LaunchOutcome:
    # Форма URL веб-базы [не проверено]: берём значение ws как есть.
    url = find_fragment(parse_connect(item.connect or ""), "ws")
    if not url:
        raise LaunchError(f"У «{item.name}» не найден адрес публикации (ws)")
    open_url(url)
    return LaunchOutcome(
        kind=LaunchKind.BROWSER, client=None, command_line=None, url=url, pid=None, version=None
    )


def _version_problem(item: InfobaseItem, source: ResolutionSource) -> str:
    safe_connect = redact_connect(item.connect or "")
    if source is ResolutionSource.INVALID_REQUEST:
        return f"У «{item.name}» неразбираемая версия «{item.requested_version}» ({safe_connect})"
    return (
        f"Для «{item.name}» запрошена версия {item.requested_version}, "
        f"на этой машине она не установлена ({safe_connect})"
    )
```

Замечание к `auto_check_version=False`: версию мы разрешаем сами и запускаем
конкретный исполняемый файл, поэтому автопроверка версии платформой не нужна
(решение 4 плана 2 — неустановленная версия не должна подменяться молча).

- [ ] **Step 5: Прогнать тесты**

Run: `uv run pytest tests/unit/test_services_launch.py -q && uv run ruff check . && uv run mypy`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/services/launch.py src/onecstarter/security/secrets.py \
        tests/unit/test_services_launch.py
git commit -m "feat: сценарий запуска базы процессом или браузером"
```

---

### Task 9: `services/workspace.py` — координатор и защита инварианта

**Files:**

- Create: `src/onecstarter/services/workspace.py`
- Test: `tests/unit/test_workspace.py`
- Test: `tests/unit/test_no_qt_in_core.py`

**Interfaces:**

- Consumes: всё из Task 3–8
- Produces (использует план UI):
  - `@dataclass(frozen=True) WorkspacePaths(ibases: Path, user_data: Path, cfg_paths: tuple[Path, ...])`
  - `class Workspace` с методами: `reload_if_changed() -> bool`, `items() -> list[InfobaseItem]`, `tree() -> list[TreeNode]`, `common_errors() -> list[CommonListError]`, `add_infobase(name, connect, folder=None) -> None`, `update_infobase(key, changes, new_name=None) -> None`, `remove_infobase(key) -> None`, `set_favorite(key, value) -> None`, `launch(key, forced_client=None) -> LaunchOutcome`

- [ ] **Step 1: Написать падающий тест инварианта 1**

```python
# tests/unit/test_no_qt_in_core.py
import subprocess
import sys

# Пакеты-контейнеры импортировать бесполезно: их __init__ пуст, и протечка
# в подмодуле осталась бы незамеченной. Перечисляем сами модули ядра.
CORE = (
    "onecstarter.services",
    "onecstarter.services.workspace",
    "onecstarter.config.v8i",
    "onecstarter.config.atomic",
    "onecstarter.config.cestart_cfg",
    "onecstarter.domain.launch",
    "onecstarter.domain.selection",
    "onecstarter.platform_1c.discovery",
    "onecstarter.platform_1c.process",
    "onecstarter.platform_1c.registry",
    "onecstarter.security.secrets",
)

PROBE = (
    "import sys;"
    + "".join(f"import {module};" for module in CORE)
    + "leaked=[m for m in sys.modules if m.split('.')[0]=='PySide6'];"
    "print(leaked)"
)


def test_core_packages_do_not_import_qt() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", f"Qt протёк в ядро: {result.stdout}"
```

Тест начнёт проходить только после Step 4 (`services/__init__.py` с публичными
именами) — до этого он падает на `ModuleNotFoundError`, и это ожидаемо.

- [ ] **Step 2: Написать падающие тесты координатора**

```python
# tests/unit/test_workspace.py
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
STAMP = "2026-08-04T07:12:44+00:00"


def _workspace(tmp_path: Path, calls: list[LaunchCommand] | None = None) -> Workspace:
    ibases = tmp_path / "ibases.v8i"
    shutil.copyfile(FIXTURE, ibases)
    recorded = calls if calls is not None else []

    def fake_spawn(command: LaunchCommand) -> int:
        recorded.append(command)
        return 7

    return Workspace(
        WorkspacePaths(ibases=ibases, user_data=tmp_path / "bases.json", cfg_paths=()),
        installations=INSTALLED,
        conventions=CONVENTIONS,
        cfg_rules=[],
        default_app=None,
        spawn=fake_spawn,
        open_url=lambda url: True,
        now=lambda: datetime.fromisoformat(STAMP),
        new_id=lambda: "99999999-9999-9999-9999-999999999999",
    )


def test_items_are_loaded_from_file(tmp_path: Path) -> None:
    assert len(_workspace(tmp_path).items()) == 9


def test_reload_detects_external_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert not workspace.reload_if_changed()
    path = workspace.paths.ibases
    path.write_bytes(path.read_bytes() + "[Чужая]\r\nConnect=File=\"C:\\B\";\r\n".encode())
    assert workspace.reload_if_changed()
    assert len(workspace.items()) == 10


def test_own_write_does_not_look_like_external_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Новая", 'File="C:\\Bases\\New";')
    assert not workspace.reload_if_changed()
    assert any(item.name == "Новая" for item in workspace.items())


def test_favorite_survives_reload(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = "id:44444444-4444-4444-4444-444444444444"
    workspace.set_favorite(key, True)
    workspace.reload_if_changed()
    assert next(item for item in workspace.items() if item.key == key).favorite


def test_update_of_section_without_id_rekeys_user_data(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    old_key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    workspace.set_favorite(old_key, True)
    workspace.update_infobase(old_key, {"Version": "8.3.25"})
    new_key = "id:99999999-9999-9999-9999-999999999999"
    item = next(item for item in workspace.items() if item.key == new_key)
    assert item.favorite


def test_launch_records_history(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls)
    key = "id:44444444-4444-4444-4444-444444444444"
    workspace.launch(key)
    item = next(item for item in workspace.items() if item.key == key)
    assert item.launch_count == 1
    assert item.last_launched_at is not None
    assert len(calls) == 1


def test_launch_of_unknown_key_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        _workspace(tmp_path).launch("id:нет такого")


def test_remove_drops_section(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.remove_infobase("id:44444444-4444-4444-4444-444444444444")
    assert not any(item.name == "Демо Бухгалтерия" for item in workspace.items())
```

- [ ] **Step 3: Реализовать координатор**

```python
# src/onecstarter/services/workspace.py
"""Координатор слоя services: состояние и сценарии поверх узких модулей.

Держит разобранный документ, его digest, наши данные и список установок.
Эффекты — порождение процесса, открытие браузера, текущее время и генерация
UUID — инжектируются: без этого тесты недетерминированы, а процессы 1С
запускались бы по-настоящему.

Слежения за файлом здесь нет: reload_if_changed вызывает слой представления
по своему триггеру (QFileSystemWatcher живёт в ui — инвариант 1).
"""

import uuid
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import ClientConvention, ClientKind, LaunchCommand
from onecstarter.domain.version import Installation
from onecstarter.platform_1c.process import spawn as spawn_process
from onecstarter.services.catalog import (
    CommonListError,
    TreeNode,
    build_tree,
    common_list_paths,
    items_from_document,
    load_common_items,
)
from onecstarter.services.edit import PatchKind, SectionPatch
from onecstarter.services.launch import LaunchOutcome, launch_infobase
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.user_data import (
    BaseUserData,
    load_user_data,
    record_launch,
    rekey,
    save_user_data,
    set_favorite,
)
from onecstarter.services.writer import write_patch


@dataclass(frozen=True)
class WorkspacePaths:
    ibases: Path
    user_data: Path
    cfg_paths: tuple[Path, ...] = ()


class Workspace:
    def __init__(
        self,
        paths: WorkspacePaths,
        *,
        installations: Sequence[Installation],
        conventions: Sequence[ClientConvention],
        cfg_rules: Sequence[DefaultVersionRule],
        default_app: str | None = None,
        spawn: Callable[[LaunchCommand], int] = spawn_process,
        open_url: Callable[[str], bool] = webbrowser.open,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.paths = paths
        self._installations = list(installations)
        self._conventions = list(conventions)
        self._cfg_rules = list(cfg_rules)
        self._default_app = default_app
        self._spawn = spawn
        self._open_url = open_url
        self._now = now
        self._new_id = new_id
        # Храним сами байты файла, а не хеш: список баз измеряется килобайтами,
        # хеш экономии не даёт, а байты избавляют от повторного чтения при
        # перестроении модели.
        self._raw = b""
        self._items: list[InfobaseItem] = []
        self._common_errors: list[CommonListError] = []
        self._user: Mapping[str, BaseUserData] = load_user_data(paths.user_data)
        self._reload()

    def items(self) -> list[InfobaseItem]:
        return list(self._items)

    def tree(self) -> list[TreeNode]:
        # Дерево строится только по пользовательскому списку. Базы из общих
        # списков — отдельная ветка UI (спека v1, §2), они доступны через items().
        return build_tree([item for item in self._items if item.source is InfobaseSource.USER])

    def common_errors(self) -> list[CommonListError]:
        return list(self._common_errors)

    def reload_if_changed(self) -> bool:
        if self._read_bytes() == self._raw:
            return False
        self._reload()
        return True

    def add_infobase(self, name: str, connect: str, folder: str | None = None) -> None:
        changes: dict[str, str | None] = {"Connect": connect}
        if folder:
            changes["Folder"] = folder
        self._write(SectionPatch(PatchKind.ADD, name=name, changes=changes))

    def update_infobase(
        self,
        key: str,
        changes: Mapping[str, str | None],
        new_name: str | None = None,
    ) -> None:
        self._write(
            SectionPatch(
                PatchKind.UPDATE, target_key=key, changes=dict(changes), new_name=new_name
            ),
            rekey_from=key,
        )

    def remove_infobase(self, key: str) -> None:
        self._write(SectionPatch(PatchKind.REMOVE, target_key=key))

    def set_favorite(self, key: str, value: bool) -> None:
        self._user = set_favorite(self._user, key, value)
        save_user_data(self.paths.user_data, self._user)
        self._rebuild()

    def launch(self, key: str, forced_client: ClientKind | None = None) -> LaunchOutcome:
        item = self._item(key)
        outcome = launch_infobase(
            item,
            installations=self._installations,
            cfg_rules=self._cfg_rules,
            conventions=self._conventions,
            default_app=self._default_app,
            forced_client=forced_client,
            spawn=self._spawn,
            open_url=self._open_url,
        )
        client = outcome.client.value if outcome.client else "browser"
        self._user = record_launch(self._user, key, client, self._now())
        save_user_data(self.paths.user_data, self._user)
        self._rebuild()
        return outcome

    def _item(self, key: str) -> InfobaseItem:
        for item in self._items:
            if item.key == key:
                return item
        raise KeyError(key)

    def _write(self, patch: SectionPatch, rekey_from: str | None = None) -> None:
        new_id = self._new_id()
        payload = write_patch(self.paths.ibases, patch, new_id)
        if rekey_from is not None and rekey_from.startswith("cs:"):
            self._user = rekey(self._user, rekey_from, f"id:{new_id}")
            save_user_data(self.paths.user_data, self._user)
        self._raw = payload
        self._rebuild()

    def _reload(self) -> None:
        self._raw = self._read_bytes()
        self._rebuild()

    def _rebuild(self) -> None:
        document = parse_v8i(self._raw)
        items = items_from_document(document, InfobaseSource.USER, self._user)
        common, errors = load_common_items(common_list_paths(self.paths.cfg_paths), self._user)
        self._items = items + common
        self._common_errors = errors

    def _read_bytes(self) -> bytes:
        try:
            return self.paths.ibases.read_bytes()
        except FileNotFoundError:
            return b""
```

- [ ] **Step 4: Дополнить `services/__init__.py`**

```python
# src/onecstarter/services/__init__.py
"""Сценарии поверх config, domain и platform_1c. Qt здесь запрещён."""

from onecstarter.services.workspace import Workspace, WorkspacePaths

__all__ = ["Workspace", "WorkspacePaths"]
```

- [ ] **Step 5: Прогнать тесты**

Run: `uv run pytest tests/unit/test_workspace.py tests/unit/test_no_qt_in_core.py -q`
Expected: PASS.

- [ ] **Step 6: Полный прогон и коммит**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy
git add src/onecstarter/services/ tests/unit/test_workspace.py tests/unit/test_no_qt_in_core.py
git commit -m "feat: координатор слоя services; план 3 закрыт"
```

- [ ] **Step 7: Обновить статус T-04.3 в бэклоге**

В `docs/tasks.md` в строке T-04.3 заменить `план не написан` на ссылку на этот план
и статус `DONE`; в разделе обязательств из ревью плана 2 отметить, что пункт 3
(форма `/IBConnectionString`) остаётся открытым и переходит в план UI вместе
с проверкой запуска баз из общих списков.

```bash
git add docs/tasks.md
git commit -m "docs: статус T-04.3 и перенос открытых экспериментов"
```

---

## Self-Review

Проверено при написании плана:

1. **Покрытие дизайна.** §1 границы → «Чего в этом плане нет»; §2 форма слоя → структура файлов и Task 3–9; §3 источники и модель → Task 3, 5; §4 ключ привязки → Task 3, 4 (`rekey`), 9; §5 запись и конфликт → Task 6, 7; отсутствующий файл и кодировка → Task 7; §6 реакция на внешнее изменение → Task 9 (`reload_if_changed`); §7 запуск → Task 8; §8 тестирование → Task 2 (фикстура), Task 9 (инвариант 1), Task 7 (конфликтная запись), Task 4 (наши данные).
2. **Инварианты `CLAUDE.md`.** Qt не импортируется нигде в `services` и проверяется тестом в подпроцессе (Task 9). Запись только через `config.atomic` (Task 7). Секреты только через `security` (Task 8). Выбор версии остаётся чистой функцией `domain` — `services` её только вызывает.
3. **Согласованность имён между задачами.** `binding_key` (Task 3) используется в `find_target` (Task 6) и `_merge` (Task 5) под тем же именем; `BaseUserData` (Task 4) — в Task 5 и 9; `SectionPatch`/`apply_patch` (Task 6) — в Task 7; `write_patch` возвращает записанные байты и они же кладутся в состояние координатора (Task 9); `LaunchOutcome.client` (Task 8) читается в `Workspace.launch` (Task 9).
4. **Правка чужого слоя обоснована.** Task 1 меняет `config.v8i` не ради удобства: регистрозависимый поиск ключа привёл бы к дописыванию второго `ID` в секцию пользователя.
5. **Непроверенные допущения помечены** и собраны для эксперимента: форма `/IBConnectionString`, запуск баз из общих списков по `/IBName`, форма URL веб-базы, смысл `OrderInList=-1`.
