# План 1 v1: слой `config` — чтение/запись файлов 1С без потерь

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Библиотека чтения/записи `ibases.v8i` и `1cestart.cfg` с побайтовым round-trip, атомарной записью и обнаружением внешних изменений.

**Architecture:** Пакет `onecstarter.config` без Qt и без знаний о запуске: модель документа `.v8i` хранит исходные строки и переиздаёт байт-в-байт всё, что не менялось; кодировка и переводы строк определяются по факту и сохраняются. Запись — временный файл в том же каталоге + замена, с проверкой снапшота от момента чтения.

**Tech Stack:** Python 3.13, stdlib (dataclasses, hashlib, tempfile, pathlib), pytest. Зависимостей не добавляем.

**Контекст серии:** это план 1 из ~5 по спеке [../specs/2026-07-30-v1-core-design.md](../specs/2026-07-30-v1-core-design.md). Ничего в этом плане не блокировано экспериментами T-02. Доменные факты о формате — скил `.claude/skills/v8i-format/` (SKILL.md + reference.md); утверждения оттуда в этом плане не перепроверять, они помечены достоверностью в самом скиле.

## Global Constraints

- Python ≥ 3.13; `uv` для окружения; команды запускать как `uv run …` из корня репозитория.
- `mypy --strict` распространяется на `src` И `tests` (см. pyproject) — тестовые функции тоже аннотируются (`-> None`).
- `ruff` с правилами `PTH` (pathlib вместо os.path), `I` (сортировка импортов) — писать сразу совместимо.
- Пакет `config` не импортирует `PySide6` ни прямо, ни транзитивно (инвариант 1 CLAUDE.md).
- Кодировка файлов определяется по факту, не хардкодится (инвариант 3).
- В фикстурах и тестах — только обезличенные имена и пути (`C:\Bases\Demo`, GUID из повторяющихся цифр). Реальные базы заказчика не упоминать.
- Процессы 1С в тестах не запускаются.
- Коммиты после каждой задачи; сообщения — `тип: описание по-русски`, как в истории репозитория.

## Структура файлов плана

| Файл | Ответственность |
| --- | --- |
| `src/onecstarter/config/encoding.py` | Байты ↔ текст: BOM, определение кодировки, обратная кодировка |
| `src/onecstarter/config/v8i.py` | Модель и разбор/сериализация `.v8i`: документ, секции, строки |
| `src/onecstarter/config/atomic.py` | Атомарная запись, снапшот файла, обнаружение внешнего изменения |
| `src/onecstarter/config/cestart_cfg.py` | Чтение `1cestart.cfg`, извлечение `CommonInfoBases` |
| `tests/unit/test_encoding.py`, `test_v8i_parse.py`, `test_v8i_roundtrip.py`, `test_v8i_sections.py`, `test_v8i_document.py`, `test_atomic.py`, `test_cestart_cfg.py` | Тесты соответствующих модулей |
| `.github/workflows/ci.yml` | CI: ruff, mypy, pytest на windows-latest |

Фикстуры кодировок и переводов строк задаются **байтовыми константами прямо в тестах**, а не файлами: редакторы и git молча нормализуют BOM/CRLF, файловые фикстуры для этого класса тестов ненадёжны. Каталог `tests/fixtures/` остаётся для будущих обезличенных реальных файлов.

---

### Task 1: Каркас в git, зелёный тулчейн, CI

**Files:**

- Create: `tests/unit/test_package.py`, `.github/workflows/ci.yml`
- Commit (уже существуют): `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `CLAUDE.md`, `src/**`, `tests/**`, `.claude/**`

**Interfaces:**

- Consumes: —
- Produces: зелёный baseline `ruff` + `mypy` + `pytest` локально и в CI; весь дальнейший код ложится поверх.

- [ ] **Step 1: Смоук-тест импорта пакета**

```python
# tests/unit/test_package.py
import onecstarter


def test_package_imports() -> None:
    assert onecstarter.__name__ == "onecstarter"
```

- [ ] **Step 2: Прогнать тулчейн**

Run: `uv sync`, затем `uv run pytest -q`, `uv run ruff check .`, `uv run mypy`
Expected: pytest — `1 passed`; ruff — без ошибок; mypy — `Success`. Если ruff/mypy падают на существующем каркасе — чинить каркас (это часть задачи), не отключать правила.

- [ ] **Step 3: CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:

jobs:
  checks:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run mypy
      - run: uv run pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: каркас проекта, тулчейн и CI"
```

Примечание: `temp/` должен быть в `.gitignore` (материалы заказчика не идут в репозиторий) — проверить перед `git add -A`, при отсутствии добавить строку `temp/`.

---

### Task 2: `encoding.py` — байты ↔ текст с сохранением формата

**Files:**

- Create: `src/onecstarter/config/encoding.py`
- Test: `tests/unit/test_encoding.py`

**Interfaces:**

- Consumes: —
- Produces:
  - `@dataclass(frozen=True) TextFormat(encoding: str, bom: bytes)`
  - `decode(data: bytes) -> tuple[str, TextFormat]`
  - `encode(text: str, fmt: TextFormat) -> bytes`
  - Гарантия: `encode(*decode(data)) == data` для любых корректных входов.

Порядок определения кодировки: BOM UTF-8 → BOM UTF-16 LE → BOM UTF-16 BE → попытка UTF-8 strict → попытка cp1251 → **latin-1 как терминальный фолбэк**. Реальные факты: `ibases.v8i` — UTF-8 без BOM, `1cestart.cfg` — UTF-16 LE с BOM (скил v8i-format, проверено). cp1251 — для legacy-файлов, но он не тотален (байт `0x98` не назначен); latin-1 декодирует любые байты и побайтово обратим, поэтому `decode` никогда не бросает исключений, а round-trip сохраняется даже для нечитаемого файла. Если BOM совпал, но дальше битые байты (обрезанный UTF-16) — тоже уходим в терминальный фолбэк, декодируя файл целиком (включая байты BOM) как latin-1 с `bom=b""`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_encoding.py
import pytest

from onecstarter.config.encoding import TextFormat, decode, encode

SAMPLES = [
    pytest.param("Бухгалтерия (демо)\r\n".encode("utf-8"), "utf-8", b"", id="utf8-no-bom"),
    pytest.param(b"\xef\xbb\xbf" + "База\r\n".encode("utf-8"), "utf-8", b"\xef\xbb\xbf", id="utf8-bom"),
    pytest.param(b"\xff\xfe" + "База\r\n".encode("utf-16-le"), "utf-16-le", b"\xff\xfe", id="utf16le-bom"),
    pytest.param(b"\xfe\xff" + "База\r\n".encode("utf-16-be"), "utf-16-be", b"\xfe\xff", id="utf16be-bom"),
    pytest.param("База\r\n".encode("cp1251"), "cp1251", b"", id="cp1251-fallback"),
]


@pytest.mark.parametrize(("data", "encoding", "bom"), SAMPLES)
def test_decode_detects_format(data: bytes, encoding: str, bom: bytes) -> None:
    text, fmt = decode(data)
    assert fmt == TextFormat(encoding=encoding, bom=bom)
    assert "База" in text or "Бухгалтерия" in text


@pytest.mark.parametrize(("data", "encoding", "bom"), SAMPLES)
def test_encode_roundtrip(data: bytes, encoding: str, bom: bytes) -> None:
    text, fmt = decode(data)
    assert encode(text, fmt) == data


def test_empty_file_is_utf8() -> None:
    text, fmt = decode(b"")
    assert text == ""
    assert fmt == TextFormat(encoding="utf-8", bom=b"")


def test_undecodable_byte_falls_back_to_latin1() -> None:
    data = b"\x98\xff\x00"  # 0x98 не назначен в cp1251 и не валиден как utf-8
    text, fmt = decode(data)
    assert fmt == TextFormat(encoding="latin-1", bom=b"")
    assert encode(text, fmt) == data


def test_corrupt_payload_after_bom_falls_back_to_latin1() -> None:
    data = b"\xff\xfe\x41"  # BOM UTF-16 LE, но нечётный «хвост» — битый файл
    text, fmt = decode(data)
    assert fmt == TextFormat(encoding="latin-1", bom=b"")
    assert encode(text, fmt) == data
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_encoding.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.config.encoding'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/config/encoding.py
"""Байты ↔ текст для файлов 1С: кодировка и BOM определяются по факту."""

import codecs
from dataclasses import dataclass

_BOMS: list[tuple[bytes, str]] = [
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
]


@dataclass(frozen=True)
class TextFormat:
    encoding: str
    bom: bytes


def _terminal(data: bytes) -> tuple[str, TextFormat]:
    return data.decode("latin-1"), TextFormat("latin-1", b"")


def decode(data: bytes) -> tuple[str, TextFormat]:
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data[len(bom):].decode(encoding), TextFormat(encoding, bom)
            except UnicodeDecodeError:
                return _terminal(data)
    for encoding in ("utf-8", "cp1251"):
        try:
            return data.decode(encoding), TextFormat(encoding, b"")
        except UnicodeDecodeError:
            continue
    return _terminal(data)


def encode(text: str, fmt: TextFormat) -> bytes:
    return fmt.bom + text.encode(fmt.encoding)
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_encoding.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS, ruff и mypy чистые.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/encoding.py tests/unit/test_encoding.py
git commit -m "feat: определение и сохранение кодировки файлов 1С"
```

---

### Task 3: `v8i.py` — модель документа и разбор

**Files:**

- Create: `src/onecstarter/config/v8i.py`
- Test: `tests/unit/test_v8i_parse.py`

**Interfaces:**

- Consumes: `decode`, `TextFormat` из Task 2.
- Produces (модель — её используют Task 4–6 и планы 2–3):
  - `@dataclass RawLine(text: str, ending: str)` — любая строка, которую не трогаем (комментарий, пустая, битая); `text` без перевода строки, `ending ∈ {"\r\n", "\n", ""}`
  - `@dataclass KeyValueLine(key: str, value: str, text: str, ending: str)` — `text` хранит исходное написание строки
  - `@dataclass V8iSection(header: RawLine, lines: list[KeyValueLine | RawLine], default_ending: str)`
  - `@dataclass V8iDocument(prologue: list[RawLine], sections: list[V8iSection], fmt: TextFormat, default_ending: str)`
  - `parse_v8i(data: bytes) -> V8iDocument`

Правила разбора (факты — скил v8i-format): строка-заголовок — `[Имя]`; `Ключ=Значение` делится по **первому** `=`; строка соединения не разбирается; строки без `=` внутри секции — `RawLine`, сохраняются как есть.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_v8i_parse.py
from onecstarter.config.v8i import KeyValueLine, RawLine, parse_v8i

BASIC = (
    '[Бухгалтерия (демо)]\r\n'
    'Connect=File="C:\\Bases\\Demo";\r\n'
    'ID=11111111-1111-1111-1111-111111111111\r\n'
    'OrderInList=20.2271604938271\r\n'
    'Folder=/Демо\r\n'
    'Version=8.3.25\r\n'
    '[Клиенты]\r\n'
    'ID=22222222-2222-2222-2222-222222222222\r\n'
    'OrderInList=-1\r\n'
    'Folder=/\r\n'
).encode("utf-8")


def test_parse_sections_and_keys() -> None:
    doc = parse_v8i(BASIC)
    assert doc.prologue == []
    assert [s.name for s in doc.sections] == ["Бухгалтерия (демо)", "Клиенты"]
    first = doc.sections[0]
    kv = [line for line in first.lines if isinstance(line, KeyValueLine)]
    assert [line.key for line in kv] == ["Connect", "ID", "OrderInList", "Folder", "Version"]


def test_connect_split_on_first_equals_only() -> None:
    doc = parse_v8i(BASIC)
    connect = doc.sections[0].lines[0]
    assert isinstance(connect, KeyValueLine)
    assert connect.key == "Connect"
    assert connect.value == 'File="C:\\Bases\\Demo";'


def test_malformed_line_kept_as_raw() -> None:
    data = "[База]\r\nConnect=File=\"C:\\B\";\r\nмусор без равно\r\n".encode("utf-8")
    doc = parse_v8i(data)
    raw = doc.sections[0].lines[1]
    assert isinstance(raw, RawLine)
    assert raw.text == "мусор без равно"


def test_prologue_before_first_section() -> None:
    data = "; комментарий\r\n[База]\r\nConnect=File=\"C:\\B\";\r\n".encode("utf-8")
    doc = parse_v8i(data)
    assert [line.text for line in doc.prologue] == ["; комментарий"]


def test_line_endings_preserved_per_line() -> None:
    data = '[А]\nConnect=File="C:\\B";\r\nID=x'.encode("utf-8")
    doc = parse_v8i(data)
    section = doc.sections[0]
    assert section.header.ending == "\n"
    assert section.lines[0].ending == "\r\n"
    assert section.lines[1].ending == ""  # последняя строка без перевода


def test_default_ending_is_dominant() -> None:
    doc = parse_v8i(BASIC)
    assert doc.default_ending == "\r\n"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_v8i_parse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.config.v8i'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/config/v8i.py
"""Модель и разбор ibases.v8i: всё исходное сохраняется для round-trip."""

from collections import Counter
from dataclasses import dataclass, field

from onecstarter.config.encoding import TextFormat, decode


@dataclass
class RawLine:
    text: str
    ending: str


@dataclass
class KeyValueLine:
    key: str
    value: str
    text: str
    ending: str


@dataclass
class V8iSection:
    header: RawLine
    lines: list[KeyValueLine | RawLine] = field(default_factory=list)
    default_ending: str = "\r\n"

    @property
    def name(self) -> str:
        return self.header.text.strip()[1:-1]


@dataclass
class V8iDocument:
    prologue: list[RawLine]
    sections: list[V8iSection]
    fmt: TextFormat
    default_ending: str


def _split_ending(raw: str) -> tuple[str, str]:
    if raw.endswith("\r\n"):
        return raw[:-2], "\r\n"
    if raw.endswith("\n"):
        return raw[:-1], "\n"
    return raw, ""


def _is_header(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("[") and stripped.endswith("]") and len(stripped) >= 2


def parse_v8i(data: bytes) -> V8iDocument:
    text, fmt = decode(data)
    endings: Counter[str] = Counter()
    prologue: list[RawLine] = []
    sections: list[V8iSection] = []
    for raw in text.splitlines(keepends=True):
        line_text, ending = _split_ending(raw)
        if ending:
            endings[ending] += 1
        if _is_header(line_text):
            sections.append(V8iSection(header=RawLine(line_text, ending)))
            continue
        parsed: KeyValueLine | RawLine
        if "=" in line_text and not sections:
            parsed = RawLine(line_text, ending)
        elif "=" in line_text:
            key, _, value = line_text.partition("=")
            parsed = KeyValueLine(key, value, line_text, ending)
        else:
            parsed = RawLine(line_text, ending)
        if sections:
            sections[-1].lines.append(parsed)
        else:
            prologue.append(parsed if isinstance(parsed, RawLine) else RawLine(line_text, ending))
    default_ending = endings.most_common(1)[0][0] if endings else "\r\n"
    for section in sections:
        section.default_ending = default_ending
    return V8iDocument(prologue, sections, fmt, default_ending)
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_v8i_parse.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS, ruff и mypy чистые.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/v8i.py tests/unit/test_v8i_parse.py
git commit -m "feat: разбор ibases.v8i с сохранением исходных строк"
```

---

### Task 4: Сериализация и побайтовый round-trip

**Files:**

- Modify: `src/onecstarter/config/v8i.py` (добавить функцию в конец файла)
- Test: `tests/unit/test_v8i_roundtrip.py`

**Interfaces:**

- Consumes: `V8iDocument`, `parse_v8i`, `encode` из Task 2–3.
- Produces: `serialize_v8i(doc: V8iDocument) -> bytes`; гарантия `serialize_v8i(parse_v8i(x)) == x` для любого входа.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_v8i_roundtrip.py
import pytest

from onecstarter.config.v8i import parse_v8i, serialize_v8i

CASES = [
    pytest.param(b"", id="empty"),
    pytest.param("[А]\r\nConnect=File=\"C:\\B\";\r\n".encode("utf-8"), id="basic"),
    pytest.param(
        b"\xef\xbb\xbf" + "[А]\r\nConnect=File=\"C:\\B\";\r\n".encode("utf-8"),
        id="utf8-bom",
    ),
    pytest.param("[А]\nConnect=File=\"C:\\B\";\nID=x".encode("cp1251"), id="cp1251-lf-no-final-newline"),
    pytest.param("; пролог\r\n\r\n[А]\r\nмусор\r\nConnect = странные пробелы\r\n".encode("utf-8"), id="garbage-preserved"),
    pytest.param(
        "[Группа]\r\nID=22222222-2222-2222-2222-222222222222\r\nOrderInList=-1\r\nFolder=/\r\n".encode("utf-8"),
        id="group-section",
    ),
    pytest.param("[А]\r\nOrderInList=60.6814814814813\r\n".encode("utf-8"), id="fractional-order"),
]


@pytest.mark.parametrize("data", CASES)
def test_roundtrip_byte_exact(data: bytes) -> None:
    assert serialize_v8i(parse_v8i(data)) == data
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_v8i_roundtrip.py -q`
Expected: FAIL — `ImportError: cannot import name 'serialize_v8i'`

- [ ] **Step 3: Реализация**

Импорт в начале `v8i.py` расширить до `from onecstarter.config.encoding import TextFormat, decode, encode`, функцию добавить в конец файла:

```python
def serialize_v8i(doc: V8iDocument) -> bytes:
    parts: list[str] = []
    for line in doc.prologue:
        parts.append(line.text + line.ending)
    for section in doc.sections:
        parts.append(section.header.text + section.header.ending)
        for body_line in section.lines:
            parts.append(body_line.text + body_line.ending)
    return encode("".join(parts), doc.fmt)
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_v8i_roundtrip.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/v8i.py tests/unit/test_v8i_roundtrip.py
git commit -m "feat: сериализация v8i с побайтовым round-trip"
```

---

### Task 5: Типизированный доступ к секции и мутации

**Files:**

- Modify: `src/onecstarter/config/v8i.py` (методы `V8iSection`)
- Test: `tests/unit/test_v8i_sections.py`

**Interfaces:**

- Consumes: модель из Task 3–4.
- Produces (методы `V8iSection`; используются services и UI в планах 3–4):
  - `get(key: str) -> str | None` — значение первого вхождения ключа, точное совпадение имени
  - `set(key: str, value: str) -> None` — заменяет значение первого вхождения (строка переиздаётся как `f"{key}={value}"`), иначе добавляет строку в конец секции с `default_ending`
  - свойства: `connect: str | None`, `id: str | None`, `version: str | None`, `default_version: str | None`, `folder: str | None`, `is_group: bool` (признак группы — отсутствие `Connect`, факт из скила v8i-format)

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_v8i_sections.py
from onecstarter.config.v8i import parse_v8i, serialize_v8i

DATA = (
    '[База]\r\n'
    'Connect=Srvr="srv";Ref="demo";\r\n'
    'ID=11111111-1111-1111-1111-111111111111\r\n'
    'Version=8.3.25\r\n'
    'DefaultVersion=8.3.25.1633\r\n'
    'Folder=/Демо\r\n'
    '[Группа]\r\n'
    'ID=22222222-2222-2222-2222-222222222222\r\n'
    'Folder=/\r\n'
).encode("utf-8")


def test_typed_properties() -> None:
    base, group = parse_v8i(DATA).sections
    assert base.connect == 'Srvr="srv";Ref="demo";'
    assert base.id == "11111111-1111-1111-1111-111111111111"
    assert base.version == "8.3.25"
    assert base.default_version == "8.3.25.1633"
    assert base.folder == "/Демо"
    assert not base.is_group
    assert group.is_group
    assert group.connect is None


def test_get_missing_key_returns_none() -> None:
    base = parse_v8i(DATA).sections[0]
    assert base.get("НетТакогоКлюча") is None


def test_set_existing_key_preserves_position_and_neighbors() -> None:
    doc = parse_v8i(DATA)
    doc.sections[0].set("Version", "8.5.1")
    out = serialize_v8i(doc).decode("utf-8")
    lines = out.splitlines()
    assert lines[3] == "Version=8.5.1"
    assert lines[2] == "ID=11111111-1111-1111-1111-111111111111"  # соседи не тронуты
    assert lines[4] == "DefaultVersion=8.3.25.1633"


def test_set_new_key_appends_to_section_end() -> None:
    doc = parse_v8i(DATA)
    doc.sections[0].set("App", "ThinClient")
    out = serialize_v8i(doc).decode("utf-8")
    lines = out.splitlines()
    assert lines[6] == "App=ThinClient"
    assert lines[7] == "[Группа]"


def test_set_after_line_without_final_newline() -> None:
    doc = parse_v8i('[А]\r\nConnect=File="C:\\B";'.encode("utf-8"))
    doc.sections[0].set("ID", "x")
    assert serialize_v8i(doc) == '[А]\r\nConnect=File="C:\\B";\r\nID=x'.encode("utf-8")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_v8i_sections.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'connect'` (и далее по списку).

- [ ] **Step 3: Реализация** (методы внутри `class V8iSection`)

Правило переводов строк при добавлении: новая строка наследует «хвост» файла — если прежняя последняя строка секции была без перевода (конец файла), перевод получает она, а новая строка добавляется без перевода; иначе новая строка получает `default_ending`.

```python
    def get(self, key: str) -> str | None:
        for line in self.lines:
            if isinstance(line, KeyValueLine) and line.key == key:
                return line.value
        return None

    def set(self, key: str, value: str) -> None:
        for line in self.lines:
            if isinstance(line, KeyValueLine) and line.key == key:
                line.value = value
                line.text = f"{key}={value}"
                return
        if self.lines and self.lines[-1].ending == "":
            self.lines[-1].ending = self.default_ending
            new_ending = ""
        elif not self.lines and self.header.ending == "":
            self.header.ending = self.default_ending
            new_ending = ""
        else:
            new_ending = self.default_ending
        self.lines.append(KeyValueLine(key, value, f"{key}={value}", new_ending))

    @property
    def connect(self) -> str | None:
        return self.get("Connect")

    @property
    def id(self) -> str | None:
        return self.get("ID")

    @property
    def version(self) -> str | None:
        return self.get("Version")

    @property
    def default_version(self) -> str | None:
        return self.get("DefaultVersion")

    @property
    def folder(self) -> str | None:
        return self.get("Folder")

    @property
    def is_group(self) -> bool:
        return self.connect is None
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_v8i_sections.py tests/unit/test_v8i_roundtrip.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS (round-trip не сломан мутациями).

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/v8i.py tests/unit/test_v8i_sections.py
git commit -m "feat: типизированный доступ и правка секций v8i"
```

---

### Task 6: Операции уровня документа

**Files:**

- Modify: `src/onecstarter/config/v8i.py` (методы `V8iDocument`)
- Test: `tests/unit/test_v8i_document.py`

**Interfaces:**

- Consumes: модель из Task 3–5.
- Produces (методы `V8iDocument`):
  - `find_by_id(section_id: str) -> V8iSection | None` — поиск по ключу `ID` (ключ идентичности формата, факт из скила)
  - `append_section(name: str) -> V8iSection` — новая секция в конце документа, заголовок `[name]`
  - `remove_section(section: V8iSection) -> None` — удаляет именно переданный объект (сравнение по идентичности `is`, не по равенству содержимого); `ValueError`, если секции нет в документе

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_v8i_document.py
from onecstarter.config.v8i import parse_v8i, serialize_v8i

DATA = (
    '[Первая]\r\n'
    'Connect=File="C:\\Bases\\A";\r\n'
    'ID=11111111-1111-1111-1111-111111111111\r\n'
    '[Вторая]\r\n'
    'Connect=File="C:\\Bases\\B";\r\n'
    'ID=22222222-2222-2222-2222-222222222222\r\n'
).encode("utf-8")


def test_find_by_id() -> None:
    doc = parse_v8i(DATA)
    found = doc.find_by_id("22222222-2222-2222-2222-222222222222")
    assert found is not None
    assert found.name == "Вторая"
    assert doc.find_by_id("нет-такого") is None


def test_append_section() -> None:
    doc = parse_v8i(DATA)
    section = doc.append_section("Новая база")
    section.set("Connect", 'File="C:\\Bases\\C";')
    out = serialize_v8i(doc).decode("utf-8")
    assert out.endswith('[Новая база]\r\nConnect=File="C:\\Bases\\C";\r\n')


def test_append_to_empty_document() -> None:
    doc = parse_v8i(b"")
    doc.append_section("База")
    assert serialize_v8i(doc) == "[База]\r\n".encode("utf-8")


def test_remove_section() -> None:
    doc = parse_v8i(DATA)
    doc.remove_section(doc.sections[0])
    out = serialize_v8i(doc).decode("utf-8")
    assert "[Первая]" not in out
    assert out.startswith("[Вторая]")


def test_remove_section_removes_exact_object_among_duplicates() -> None:
    data = "[Группа]\r\nID=x\r\n[Группа]\r\nID=x\r\n".encode()
    doc = parse_v8i(data)
    first, second = doc.sections
    doc.remove_section(second)
    assert doc.sections == [first]
    assert doc.sections[0] is first


def test_remove_section_not_in_document_raises() -> None:
    doc = parse_v8i(DATA)
    foreign = parse_v8i(DATA).sections[0]  # равная по содержимому, но чужая секция
    import pytest

    with pytest.raises(ValueError, match="не входит в документ"):
        doc.remove_section(foreign)
```

(Импорт `pytest` в реальном файле разместить вверху модуля, не внутри функции.)

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_v8i_document.py -q`
Expected: FAIL — `AttributeError: 'V8iDocument' object has no attribute 'find_by_id'`.

- [ ] **Step 3: Реализация** (методы внутри `class V8iDocument`)

```python
    def find_by_id(self, section_id: str) -> V8iSection | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def append_section(self, name: str) -> V8iSection:
        if self.sections:
            last = self.sections[-1]
            if last.lines and last.lines[-1].ending == "":
                last.lines[-1].ending = self.default_ending
            elif not last.lines and last.header.ending == "":
                last.header.ending = self.default_ending
        section = V8iSection(
            header=RawLine(f"[{name}]", self.default_ending),
            default_ending=self.default_ending,
        )
        self.sections.append(section)
        return section

    def remove_section(self, section: V8iSection) -> None:
        for index, candidate in enumerate(self.sections):
            if candidate is section:
                del self.sections[index]
                return
        raise ValueError("Секция не входит в документ")
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/v8i.py tests/unit/test_v8i_document.py
git commit -m "feat: операции документа v8i — поиск, добавление, удаление секций"
```

---

### Task 7: `atomic.py` — атомарная запись и обнаружение внешних изменений

**Files:**

- Create: `src/onecstarter/config/atomic.py`
- Test: `tests/unit/test_atomic.py`

**Interfaces:**

- Consumes: —
- Produces:
  - `@dataclass(frozen=True) FileSnapshot(path: Path, digest: str)` — sha256 содержимого на момент чтения
  - `read_with_snapshot(path: Path) -> tuple[bytes, FileSnapshot]`
  - `atomic_write(path: Path, data: bytes) -> None` — временный файл в том же каталоге + `Path.replace`
  - `atomic_write_if_unchanged(path: Path, data: bytes, snapshot: FileSnapshot) -> None` — бросает `ExternalChangeError`, если файл изменился после снапшота
  - `class ExternalChangeError(Exception)`

Известное ограничение (зафиксировать в докстринге модуля): между проверкой снапшота и заменой файла есть окно гонки; слой services (план 3) обрабатывает это слиянием по `ID` при `ExternalChangeError` и повтором. Файловых блокировок в v1 не делаем.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_atomic.py
from pathlib import Path

import pytest

from onecstarter.config.atomic import (
    ExternalChangeError,
    atomic_write,
    atomic_write_if_unchanged,
    read_with_snapshot,
)


def test_atomic_write_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"first")
    assert target.read_bytes() == b"first"
    atomic_write(target, b"second")
    assert target.read_bytes() == b"second"


def test_no_temp_files_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"data")
    assert [p.name for p in tmp_path.iterdir()] == ["ibases.v8i"]


def test_write_if_unchanged_passes_when_untouched(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"original")
    data, snapshot = read_with_snapshot(target)
    assert data == b"original"
    atomic_write_if_unchanged(target, b"updated", snapshot)
    assert target.read_bytes() == b"updated"


def test_write_if_unchanged_detects_external_change(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"original")
    _, snapshot = read_with_snapshot(target)
    target.write_bytes(b"changed by 1cestart")
    with pytest.raises(ExternalChangeError):
        atomic_write_if_unchanged(target, b"updated", snapshot)
    assert target.read_bytes() == b"changed by 1cestart"


def test_write_if_unchanged_detects_deleted_file(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"original")
    _, snapshot = read_with_snapshot(target)
    target.unlink()
    with pytest.raises(ExternalChangeError):
        atomic_write_if_unchanged(target, b"updated", snapshot)
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_atomic.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.config.atomic'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/config/atomic.py
"""Атомарная запись пользовательских файлов 1С.

ibases.v8i параллельно перезаписывает штатный 1cestart.exe, поэтому запись
только через временный файл в том же каталоге + замена, с проверкой снапшота.
Между проверкой снапшота и заменой остаётся окно гонки: слой services
обрабатывает ExternalChangeError слиянием и повтором. Блокировок нет.
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ExternalChangeError(Exception):
    """Файл изменён извне после того, как мы его прочитали."""


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    digest: str


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_with_snapshot(path: Path) -> tuple[bytes, FileSnapshot]:
    data = path.read_bytes()
    return data, FileSnapshot(path=path, digest=_digest(data))


def atomic_write(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_if_unchanged(path: Path, data: bytes, snapshot: FileSnapshot) -> None:
    try:
        current = path.read_bytes()
    except FileNotFoundError as error:
        raise ExternalChangeError(f"{path} удалён после чтения") from error
    if _digest(current) != snapshot.digest:
        raise ExternalChangeError(f"{path} изменён извне после чтения")
    atomic_write(path, data)
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_atomic.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/atomic.py tests/unit/test_atomic.py
git commit -m "feat: атомарная запись с обнаружением внешних изменений"
```

---

### Task 8: `cestart_cfg.py` — чтение `1cestart.cfg` и `CommonInfoBases`

**Files:**

- Create: `src/onecstarter/config/cestart_cfg.py`
- Test: `tests/unit/test_cestart_cfg.py`

**Interfaces:**

- Consumes: `decode` из Task 2.
- Produces:
  - `parse_cestart_cfg(data: bytes) -> list[tuple[str, str]]` — пары ключ-значение в порядке файла, повторяющиеся ключи допустимы, разбиение по первому `=`, строки без `=` пропускаются
  - `common_infobase_sources(entries: list[tuple[str, str]]) -> list[str]` — значения всех ключей `CommonInfoBases` в порядке появления

Факты: `1cestart.cfg` — UTF-16 LE с BOM (скил v8i-format, проверено); ключ `CommonInfoBases` может повторяться и указывать путь или URL общего списка (скил platform-launch / Приложение 3 ИТС). В v1 файл только читается.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_cestart_cfg.py
import codecs

from onecstarter.config.cestart_cfg import common_infobase_sources, parse_cestart_cfg

CFG_TEXT = (
    "CommonInfoBases=\\\\server\\share\\bases.v8i\r\n"
    "CommonInfoBases=http://portal.example/bases.v8i\r\n"
    "DefaultVersion=8.3.25\r\n"
    "строка без разделителя\r\n"
)
CFG = codecs.BOM_UTF16_LE + CFG_TEXT.encode("utf-16-le")


def test_parse_keeps_order_and_duplicates() -> None:
    entries = parse_cestart_cfg(CFG)
    assert entries == [
        ("CommonInfoBases", "\\\\server\\share\\bases.v8i"),
        ("CommonInfoBases", "http://portal.example/bases.v8i"),
        ("DefaultVersion", "8.3.25"),
    ]


def test_common_infobase_sources() -> None:
    entries = parse_cestart_cfg(CFG)
    assert common_infobase_sources(entries) == [
        "\\\\server\\share\\bases.v8i",
        "http://portal.example/bases.v8i",
    ]


def test_empty_cfg() -> None:
    assert parse_cestart_cfg(b"") == []
    assert common_infobase_sources([]) == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_cestart_cfg.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.config.cestart_cfg'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/config/cestart_cfg.py
"""Чтение 1cestart.cfg. В v1 файл только читается, запись не поддерживается."""

from onecstarter.config.encoding import decode


def parse_cestart_cfg(data: bytes) -> list[tuple[str, str]]:
    text, _ = decode(data)
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        entries.append((key, value))
    return entries


def common_infobase_sources(entries: list[tuple[str, str]]) -> list[str]:
    return [value for key, value in entries if key == "CommonInfoBases"]
```

- [ ] **Step 4: Прогнать весь набор**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: все PASS, весь пакет зелёный.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/config/cestart_cfg.py tests/unit/test_cestart_cfg.py
git commit -m "feat: чтение 1cestart.cfg и общих списков CommonInfoBases"
```

---

## Отклонения при исполнении (пост-фактум)

Финальное ревью ветки нашло и доказало три дефекта кода самого плана; исправлены с одобрения заказчика (коммиты `2c4e9fd`, `84ac6f6`, `a331ffb`):

1. Разбор строк: `splitlines(keepends=True)` резал и по экзотическим Unicode-границам → заменён ручным делением только по `\n`/`\r\n` (`_iter_raw_lines`); `ending == ""` теперь возможен только у последней строки файла.
2. `append_section` не закрывал перевод строки у пролога; логика «закрыть хвост» вынесена в общий хелпер `_close_last_ending`.
3. `common_infobase_sources` сравнивает ключ регистронезависимо (`casefold`) — по проверенному факту скила platform-launch о регистре ключей.

## Что осталось за пределами плана 1

Следующие планы серии (пишутся после выполнения этого): план 2 — `platform_1c` + `domain` (реестр версий, обнаружение установок, выбор версии — после экспериментов T-02), план 3 — `services` + наши данные в `%APPDATA%`, план 4 — UI раздела «Базы», план 5 — поставка. Слияние по `ID` при `ExternalChangeError` — план 3.
