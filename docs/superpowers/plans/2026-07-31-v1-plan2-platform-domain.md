# План 2 v1: `domain` + `platform_1c` — версии, выбор, командная строка, обнаружение

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Чистая доменная логика выбора версии платформы и сборки командной строки запуска плюс пакет `platform_1c`: декларативный реестр раскладки версий, обнаружение установленных версий по файловой системе, порождение процесса.

**Architecture:** `domain` — только чистые функции и неизменяемые dataclass'ы, ни ФС, ни процессов, ни Qt (инварианты 1–2 CLAUDE.md); всё окружение подаётся аргументами. `platform_1c` — побочные эффекты (ФС, процессы), импортирует `domain` и `config`, обратной зависимости нет. Раскладка версий (имена клиентов, каталог `bin`) — данные в TOML, не код (боль Д требований).

**Tech Stack:** Python 3.13, stdlib (`dataclasses`, `enum`, `tomllib`, `importlib.resources`, `subprocess`), pytest. Зависимостей не добавляем.

**Контекст серии:** план 2 из ~5 по спеке [../specs/2026-07-30-v1-core-design.md](../specs/2026-07-30-v1-core-design.md), продолжение [плана 1](2026-07-31-v1-plan1-config-core.md) (слой `config` готов). Доменные факты о запуске — скил `.claude/skills/platform-launch/` (SKILL.md + reference.md), о формате — скил `.claude/skills/v8i-format/`; утверждения оттуда здесь не перепроверять, метки достоверности — в скилах. Эксперименты T-02 закрыты, их результаты уже в скилах с меткой **[Ф]**.

## Global Constraints

- Python ≥ 3.13; `uv` для окружения; команды запускать как `uv run …` из корня репозитория.
- `mypy --strict` распространяется на `src` И `tests` — тестовые функции аннотируются (`-> None`).
- `ruff` с правилами `PTH` (pathlib), `I` (сортировка импортов) — писать сразу совместимо.
- Пакеты `domain` и `platform_1c` не импортируют `PySide6` ни прямо, ни транзитивно (инвариант 1).
- Выбор версии — чистая функция без обращений к ФС и процессам, табличные тесты (инвариант 2).
- **Процессы 1С в тестах не запускаются никогда** — тест запуска использует `sys.executable` со скриптом-заглушкой.
- В тестах — только обезличенные имена и пути (`C:\Bases\Demo`, `empty`, `srv-1c`). Версии платформы — реальный набор с машины экспериментов, он уже опубликован в скиле.
- Коммиты после каждой задачи; сообщения — `тип: описание по-русски`, как в истории репозитория.

## Решения плана (зафиксированы здесь, чтобы не переигрывать в задачах)

1. **Запуск по `/IBName` — основной путь.** Совпадает со снятыми командными строками штатного стартера **[Ф]**, платформа сама читает из `.v8i` ключи `WA`, `AdditionalParameters`, `ClientConnectionSpeed` (перевоспроизводить их семантику не нужно — **[Ф]** факт 6 скила platform-launch), секреты из `Connect` не попадают в argv. Запасной путь — `/IBConnectionString` целиком (для баз вне `ibases.v8i`, например из общих списков). Способ присоединения значения к ключу `/IBConnectionString"..."` — **[не проверено]**, принят по аналогии со снятой формой `/IBName"..."`; проверить при первом реальном запуске (план 3), результат вернуть в скил platform-launch.
2. **Командная строка — строка, а не argv-список.** Тест фиксирует наш канонический порядок аргументов побайтово; как 1С разбирает нестандартное квотирование argv-списка — неизвестно, а форма `/IBName"..."` снята с реального процесса **[Ф]**. Важно: **порядок ключей у штатного стартера плавает** — в снапшотах встречаются и `/AppAutoCheckVersion /AppAutoCheckMode`, и `/AppAutoCheckMode /AppAutoCheckVersion` (и даже двойной пробел между ключами), поэтому эталон тестов — одна из снятых форм, а не «единственная форма стартера». Расхождение будущего снапшота с тестом по порядку ключей — не опровержение. `spawn` передаёт строку в `Popen` как есть.
3. **Полная версия = 4 числовых компонента** (`8.3.25.1633`). ИТС говорит «полный номер», не определяя его; все наблюдавшиеся установленные версии четырёхкомпонентны **[Ф]**. Это решение, не факт формата.
4. **Неустановленная версия — не молчаливый фолбэк.** Штатный стартер молча запускает максимальную установленную (**[Ф]** T-02.8); наш продукт обязан показать проблему до запуска (боль А). Поэтому `resolve_version` возвращает `NOT_INSTALLED` + отдельно `fallback` — «что молча запустил бы штатный стартер», UI решает, что с этим делать.
5. **`DefaultVersion` секции применяется, только если уточняет маску `Version`** (префиксное совпадение). Случай `DefaultVersion`, не соответствующего маске, экспериментально не проверен (отмечено в скиле v8i-format) — игнорируем такое значение и идём дальше по цепочке.
6. **`1cescmn.cfg` в v1 не читаем.** Его расположение («каталог установки/дистрибутивов») не подтверждено на реальной машине. Читаются два `1cestart.cfg` (`%ALLUSERSPROFILE%` и `%APPDATA%`) в порядке приоритета `InstalledLocation` из ИТС. Ограничение зафиксировать в докстринге `discovery.py`.
7. **`spawn` входит в этот план.** Спека относит порождение процессов к `platform_1c`; план 3 (`services`) должен только вызывать готовую функцию, а не дописывать чужой пакет.
8. **WebClient не запускается исполняемым файлом** — это браузер, зона `services`/UI (план 3+). `choose_client` на `App=WebClient` бросает `ValueError`, чтобы ошибка слоя выше была громкой, а не тихим запуском не того клиента.
9. **База без `Version` → максимальная установленная (`MAX_INSTALLED`)** — решение плана, не факт: поведение штатного стартера для секции вообще без `Version` не снималось, ИТС его не описывает. Подстановка по правилам cfg при отсутствии запроса неприменима (правилу нужна маска-запрос). При случае снять поведение штатного стартера экспериментом и вернуть в скил.
10. **Маска правила cfg сопоставляется с запросом точным равенством кортежей** (`substitute`: запрос `8.3.24` правилом `8.3-…` не ловится) — решение плана: примеры ИТС показывают только точное совпадение («база просит 8.3»), префиксная семантика не документирована и не проверялась.

## Чего в этом плане нет

Слежение за файлом и слияние по `ID` (план 3), история/избранное/`%APPDATA%` (план 3), UI (план 4), открытие веб-баз в браузере (план 3), чтение `1cescmn.cfg` (решение 6), автоустановка дистрибутивов (`DistributiveLocation` — вне v1).

## Структура файлов плана

| Файл | Ответственность |
| --- | --- |
| `src/onecstarter/domain/version.py` | `VersionNumber`: разбор, числовое сравнение, префикс-маски; `Arch`; `Installation` |
| `src/onecstarter/domain/default_version.py` | Грамматика `DefaultVersion` из `1cestart.cfg`: `<маска>[-<полная>][;<разрядность>]` |
| `src/onecstarter/domain/selection.py` | `resolve_version` — чистая функция выбора версии с источником решения |
| `src/onecstarter/domain/connect.py` | Разбор строки соединения на фрагменты (read-only), классификация файловая/серверная/веб |
| `src/onecstarter/domain/launch.py` | Выбор клиента по `App`/`DefaultApp`, соглашения раскладки, сборка командной строки |
| `src/onecstarter/platform_1c/registry.toml` | Декларативный реестр раскладки версий — данные поставки |
| `src/onecstarter/platform_1c/registry.py` | Загрузка реестра (TOML → `ClientConvention`) |
| `src/onecstarter/platform_1c/discovery.py` | Корни установки из env и cfg, скан ФС, разрядность exe по PE-заголовку |
| `src/onecstarter/platform_1c/process.py` | `spawn` — единственное место порождения процессов |
| `tests/unit/test_version.py`, `test_default_version.py`, `test_selection.py`, `test_connect.py`, `test_launch.py`, `test_registry.py`, `test_discovery.py`, `test_process.py` | Тесты соответствующих модулей |

Зависимости: `version ← default_version ← selection`; `version ← launch`; `connect` автономен; `platform_1c/*` импортирует `domain` и `config.cestart_cfg`. `domain` не импортирует ничего из `platform_1c` и `config`.

---

### Task 1: `domain/version.py` — номер версии, разрядность, установка

**Files:**

- Create: `src/onecstarter/domain/version.py`
- Test: `tests/unit/test_version.py`

**Interfaces:**

- Consumes: —
- Produces (используют Task 2–7):
  - `@dataclass(frozen=True, order=True) VersionNumber(parts: tuple[int, ...])` — сравнение покомпонентное числовое; `is_full: bool` (4 компонента, решение 3); `starts_with(prefix: VersionNumber) -> bool` — сравнение кортежей, не строк; `__str__` — `"8.3.25.1633"`
  - `parse_version(text: str) -> VersionNumber` — `ValueError` на всё, что не `цифры(.цифры)*`
  - `class Arch(Enum)`: `X86 = "x86"`, `X64 = "x86_64"`, `UNKNOWN = "unknown"` — фактическая разрядность exe (не путать со словарём предпочтений `AppArch`: `x86_prt` и т.п. — это другой словарь, он остаётся строками)
  - `@dataclass(frozen=True) Installation(version: VersionNumber, path: Path, arch: Arch)` — найденная установка платформы

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_version.py
from pathlib import Path

import pytest

from onecstarter.domain.version import Arch, Installation, VersionNumber, parse_version


def test_parse_full_version() -> None:
    version = parse_version("8.3.25.1633")
    assert version.parts == (8, 3, 25, 1633)
    assert version.is_full
    assert str(version) == "8.3.25.1633"


def test_parse_mask_is_not_full() -> None:
    assert not parse_version("8.3.25").is_full
    assert not parse_version("8.3").is_full


@pytest.mark.parametrize(
    "bad",
    ["", "8.", ".8", "8..3", "8.3a", "8. 3", "v8.3", "8,3", "8.3.25.1633 "],
)
def test_parse_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError, match="версии"):
        parse_version(bad)


def test_numeric_component_order() -> None:
    # Лексикографически 8.3.9 > 8.3.18 > 8.3.10 — числовой порядок обратный
    # (факт 5 скила platform-launch).
    assert parse_version("8.3.9") < parse_version("8.3.10") < parse_version("8.3.18")


def test_starts_with_compares_tuples_not_strings() -> None:
    mask = parse_version("8.3.25")
    assert parse_version("8.3.25.1633").starts_with(mask)
    # startswith по строке поймал бы 8.3.250.1 — по кортежам не должен.
    assert not parse_version("8.3.250.1").starts_with(mask)


def test_starts_with_longer_prefix_is_false() -> None:
    assert not parse_version("8.3.25").starts_with(parse_version("8.3.25.1633"))


def test_installation_holds_data() -> None:
    installation = Installation(
        version=parse_version("8.3.25.1633"),
        path=Path("C:/Program Files/1cv8/8.3.25.1633"),
        arch=Arch.X64,
    )
    assert installation.arch is Arch.X64
    assert installation.version == VersionNumber((8, 3, 25, 1633))
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_version.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.domain.version'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/domain/version.py
"""Номера версий платформы 1С: разбор, числовое сравнение, маски.

Сравнение — покомпонентное числовое: лексикографический порядок строк
даёт 8.3.9 > 8.3.18 и ломает выбор версии (скил platform-launch, факт 5).
Маска сравнивается как кортеж чисел: startswith по строке ловит 8.3.250.1
маской 8.3.25. «Полная» версия = 4 компонента — решение плана 2, не факт
формата: ИТС термин «полный номер» не определяет.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")

FULL_VERSION_PARTS = 4


@dataclass(frozen=True, order=True)
class VersionNumber:
    parts: tuple[int, ...]

    @property
    def is_full(self) -> bool:
        return len(self.parts) == FULL_VERSION_PARTS

    def starts_with(self, prefix: "VersionNumber") -> bool:
        return self.parts[: len(prefix.parts)] == prefix.parts

    def __str__(self) -> str:
        return ".".join(str(part) for part in self.parts)


def parse_version(text: str) -> VersionNumber:
    if not _VERSION_RE.match(text):
        raise ValueError(f"Некорректный номер версии: {text!r}")
    return VersionNumber(tuple(int(part) for part in text.split(".")))


class Arch(Enum):
    """Фактическая разрядность исполняемого файла.

    Не путать со словарём предпочтений AppArch (x86_prt, x86_64_prt) —
    тот остаётся строками там, где читается из файлов 1С.
    """

    X86 = "x86"
    X64 = "x86_64"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Installation:
    version: VersionNumber
    path: Path
    arch: Arch
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_version.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS, ruff и mypy чистые.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/version.py tests/unit/test_version.py
git commit -m "feat: номера версий платформы — разбор, сравнение, маски"
```

---

### Task 2: `domain/default_version.py` — правила `DefaultVersion` конфигурационных файлов

**Files:**

- Create: `src/onecstarter/domain/default_version.py`
- Test: `tests/unit/test_default_version.py`

**Interfaces:**

- Consumes: `VersionNumber`, `parse_version` из Task 1.
- Produces (использует Task 3):
  - `@dataclass(frozen=True) DefaultVersionRule(mask: VersionNumber, target: VersionNumber | None, arch: str | None)`
  - `parse_default_version_rule(value: str) -> DefaultVersionRule` — `ValueError` на мусор
  - `default_version_rules(entries: Iterable[tuple[str, str]]) -> list[DefaultVersionRule]` — из пар `parse_cestart_cfg`; ключ `DefaultVersion` сравнивается регистронезависимо (**[Ф]** факт о регистре ключей, скил platform-launch); неразборные значения пропускаются
  - `substitute(mask: VersionNumber, rules: Sequence[DefaultVersionRule]) -> VersionNumber | None` — первое правило с `rule.mask == mask` (точное равенство кортежей — решение 10 плана, не документированный факт) и полной `target`

Грамматика (скил platform-launch, факт 4): `<маска>[-<полная версия>][;<разрядность>]`, разделитель маски и цели — **дефис**, не второй `=`. Правило без цели (`8.3;x86_64_prt`) задаёт предпочтение разрядности — `substitute` его пропускает, разрядность в v1 не используется при выборе версии (сохранена в модели на будущее). Порядок правил задаёт вызывающий код (порядок файлов); при нескольких подходящих побеждает первое — приоритет уровней для объединяемого `DefaultVersion` в ИТС не задан, это решение плана.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_default_version.py
import pytest

from onecstarter.domain.default_version import (
    DefaultVersionRule,
    default_version_rules,
    parse_default_version_rule,
    substitute,
)
from onecstarter.domain.version import parse_version


def test_parse_mask_with_target() -> None:
    rule = parse_default_version_rule("8.3-8.3.24.100")
    assert rule.mask == parse_version("8.3")
    assert rule.target == parse_version("8.3.24.100")
    assert rule.arch is None


def test_parse_mask_only() -> None:
    rule = parse_default_version_rule("8.2.15")
    assert rule == DefaultVersionRule(mask=parse_version("8.2.15"), target=None, arch=None)


def test_parse_mask_with_arch() -> None:
    rule = parse_default_version_rule("8.3;x86_64_prt")
    assert rule.mask == parse_version("8.3")
    assert rule.target is None
    assert rule.arch == "x86_64_prt"


def test_parse_garbage_raises() -> None:
    with pytest.raises(ValueError, match="версии"):
        parse_default_version_rule("не версия")


def test_rules_from_entries_key_is_case_insensitive() -> None:
    entries = [
        ("DefaultVersion", "8.3-8.3.24.100"),
        ("DEFAULTVERSION", "8.2.15-8.2.15.315"),
        ("CommonInfoBases", r"\\server\share\bases.v8i"),
        ("DefaultVersion", "мусор — пропустить"),
    ]
    rules = default_version_rules(entries)
    assert [str(rule.mask) for rule in rules] == ["8.3", "8.2.15"]


def test_substitute_exact_mask_match() -> None:
    rules = default_version_rules([("DefaultVersion", "8.3-8.3.24.100")])
    assert substitute(parse_version("8.3"), rules) == parse_version("8.3.24.100")
    # 8.3.24 ≠ 8.3: маска правила сопоставляется точным равенством, не префиксом.
    assert substitute(parse_version("8.3.24"), rules) is None


def test_substitute_first_match_wins() -> None:
    rules = default_version_rules(
        [("DefaultVersion", "8.3-8.3.24.100"), ("DefaultVersion", "8.3-8.3.22.1923")]
    )
    assert substitute(parse_version("8.3"), rules) == parse_version("8.3.24.100")


def test_substitute_skips_rule_without_full_target() -> None:
    rules = default_version_rules([("DefaultVersion", "8.3;x86_64_prt")])
    assert substitute(parse_version("8.3"), rules) is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_default_version.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.domain.default_version'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/domain/default_version.py
"""Правила DefaultVersion из 1cestart.cfg: таблица подстановки, не скаляр.

Грамматика <маска>[-<полная версия>][;<разрядность>] — скил platform-launch.
Разделитель маски и цели — дефис. Правило без цели задаёт предпочтение
разрядности; в подстановке версии не участвует.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from onecstarter.domain.version import VersionNumber, parse_version


@dataclass(frozen=True)
class DefaultVersionRule:
    mask: VersionNumber
    target: VersionNumber | None
    arch: str | None


def parse_default_version_rule(value: str) -> DefaultVersionRule:
    body, has_arch, arch = value.partition(";")
    mask_text, has_target, target_text = body.partition("-")
    return DefaultVersionRule(
        mask=parse_version(mask_text.strip()),
        target=parse_version(target_text.strip()) if has_target else None,
        arch=arch.strip() if has_arch else None,
    )


def default_version_rules(entries: Iterable[tuple[str, str]]) -> list[DefaultVersionRule]:
    rules: list[DefaultVersionRule] = []
    for key, value in entries:
        if key.casefold() != "defaultversion":
            continue
        try:
            rules.append(parse_default_version_rule(value))
        except ValueError:
            continue
    return rules


def substitute(mask: VersionNumber, rules: Sequence[DefaultVersionRule]) -> VersionNumber | None:
    for rule in rules:
        if rule.mask == mask and rule.target is not None and rule.target.is_full:
            return rule.target
    return None
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_default_version.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/default_version.py tests/unit/test_default_version.py
git commit -m "feat: правила DefaultVersion конфигурационных файлов"
```

---

### Task 3: `domain/selection.py` — выбор версии платформы

Сердце плана: чистая функция, воспроизводящая проверенный порядок разрешения
(скил platform-launch, «Алгоритм подбора версии», факты **[Ф]** T-02.1/2/8) и
делающая видимым то, что штатный стартер прячет.

**Files:**

- Create: `src/onecstarter/domain/selection.py`
- Test: `tests/unit/test_selection.py`

**Interfaces:**

- Consumes: `VersionNumber`, `parse_version` (Task 1); `DefaultVersionRule`, `substitute` (Task 2).
- Produces (используют план 3 — services и план 4 — UI-колонка версии):
  - `class ResolutionSource(Enum)`: `EXACT`, `SECTION_DEFAULT`, `CFG_DEFAULT`, `PREFIX_MAX`, `MAX_INSTALLED`, `NOT_INSTALLED`, `INVALID_REQUEST` — источник решения, логируется и показывается в UI (требование скила: явное логирование источника)
  - `@dataclass(frozen=True) VersionResolution(version: VersionNumber | None, source: ResolutionSource, requested: VersionNumber | None, fallback: VersionNumber | None)` — `version=None` значит «запускать нечем/нельзя молча»; `fallback` — максимальная установленная вообще, «что молча запустил бы штатный стартер». Метка честности: **[Ф]** это только для несуществующей *полной* версии (T-02.8); для `INVALID_REQUEST` и маски без совпадений — экстраполяция, поведение штатного не снималось (отразить в докстринге). При `INVALID_REQUEST` исходная неразборная строка в результате не хранится (`requested=None`) — осознанное решение: UI показывает сырое значение `Version` из секции, дублировать его в результате не нужно
  - `resolve_version(requested: str | None, section_default: str | None, cfg_rules: Sequence[DefaultVersionRule], installed: Iterable[VersionNumber]) -> VersionResolution`

Порядок разрешения:

1. `requested` не разбирается как версия → `INVALID_REQUEST` (порчу показываем, не чиним — философия факта 6 скила v8i-format).
2. `requested is None` → максимальная установленная (`MAX_INSTALLED`) — решение 9 плана, не снятый факт; нечего ставить → `NOT_INSTALLED`.
3. Полная `requested`: установлена → `EXACT` (**[Ф]** точная `Version` бьёт `DefaultVersion`, T-02.2); нет → `NOT_INSTALLED` + `fallback` (**[Ф]** T-02.8 — штатный молчит, мы показываем).
4. Маска: `DefaultVersion` секции, если полная, уточняет маску (префикс) и установлена → `SECTION_DEFAULT` (**[Ф]** T-02.2); иначе подстановка по правилам cfg → `CFG_DEFAULT`; иначе максимальная установленная **с этим префиксом** → `PREFIX_MAX` (**[Ф]** T-02.1); иначе `NOT_INSTALLED`.

- [ ] **Step 1: Написать падающие табличные тесты**

```python
# tests/unit/test_selection.py
import pytest

from onecstarter.domain.default_version import DefaultVersionRule, default_version_rules
from onecstarter.domain.selection import ResolutionSource, resolve_version
from onecstarter.domain.version import VersionNumber, parse_version

# Реальный набор машины экспериментов T-02 (скил platform-launch, [Ф]).
INSTALLED = [
    parse_version(text)
    for text in (
        "8.3.10.2252",
        "8.3.18.1334",
        "8.3.20.2290",
        "8.3.22.1923",
        "8.3.25.1560",
        "8.3.25.1633",
        "8.3.27.2214",
    )
]

NO_RULES: list[DefaultVersionRule] = []
RULE_8_3_TO_22 = default_version_rules([("DefaultVersion", "8.3-8.3.22.1923")])
RULE_8_3_TO_MISSING = default_version_rules([("DefaultVersion", "8.3-8.3.24.100")])

CASES = [
    # (requested, section_default, cfg_rules, ожидаемая версия, источник)
    pytest.param(
        "8.3.25.1560", "8.3.25.1633", NO_RULES, "8.3.25.1560", ResolutionSource.EXACT,
        id="exact-beats-section-default",  # [Ф] T-02.2
    ),
    pytest.param(
        "8.3.25", "8.3.25.1560", NO_RULES, "8.3.25.1560", ResolutionSource.SECTION_DEFAULT,
        id="mask-refined-by-section-default",  # [Ф] T-02.2
    ),
    pytest.param(
        "8.3.25", None, NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="mask-resolves-to-prefix-max",  # [Ф] T-02.1
    ),
    pytest.param(
        "8.3.2", None, NO_RULES, None, ResolutionSource.NOT_INSTALLED,
        id="mask-8.3.2-does-not-catch-8.3.20",  # кортежи, не startswith
    ),
    pytest.param(
        "8.3.99.1", None, NO_RULES, None, ResolutionSource.NOT_INSTALLED,
        id="missing-full-version-is-visible",  # [Ф] T-02.8, штатный молчит
    ),
    pytest.param(
        "8.3", None, RULE_8_3_TO_22, "8.3.22.1923", ResolutionSource.CFG_DEFAULT,
        id="cfg-rule-beats-prefix-max",
    ),
    pytest.param(
        "8.3", None, RULE_8_3_TO_MISSING, "8.3.27.2214", ResolutionSource.PREFIX_MAX,
        id="cfg-rule-with-missing-target-skipped",
    ),
    pytest.param(
        "8.3.25", "8.3.22.1923", NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="section-default-outside-mask-ignored",  # решение 5 плана
    ),
    pytest.param(
        "8.3.25", "8.3", NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="section-default-mask-ignored",
    ),
    pytest.param(
        "8.3.25", "8.3.25.1560", RULE_8_3_TO_22, "8.3.25.1560", ResolutionSource.SECTION_DEFAULT,
        id="section-default-beats-cfg-rule",
    ),
    pytest.param(
        None, None, NO_RULES, "8.3.27.2214", ResolutionSource.MAX_INSTALLED,
        id="no-version-takes-max-installed",
    ),
    pytest.param(
        "8.3.abc", None, NO_RULES, None, ResolutionSource.INVALID_REQUEST,
        id="broken-version-is-reported-not-fixed",
    ),
]


@pytest.mark.parametrize(("requested", "section_default", "rules", "expected", "source"), CASES)
def test_resolution_table(
    requested: str | None,
    section_default: str | None,
    rules: list[DefaultVersionRule],
    expected: str | None,
    source: ResolutionSource,
) -> None:
    resolution = resolve_version(requested, section_default, rules, INSTALLED)
    assert resolution.source is source
    if expected is None:
        assert resolution.version is None
    else:
        assert resolution.version == parse_version(expected)


def test_fallback_is_overall_max() -> None:
    resolution = resolve_version("8.3.99.1", None, [], INSTALLED)
    assert resolution.fallback == parse_version("8.3.27.2214")
    assert resolution.requested == parse_version("8.3.99.1")


def test_empty_pool_has_no_fallback() -> None:
    resolution = resolve_version("8.3.25", None, [], [])
    assert resolution.source is ResolutionSource.NOT_INSTALLED
    assert resolution.version is None
    assert resolution.fallback is None


def test_installed_order_does_not_matter() -> None:
    shuffled = list(reversed(INSTALLED))
    resolution = resolve_version("8.3.25", None, [], shuffled)
    assert resolution.version == VersionNumber((8, 3, 25, 1633))
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_selection.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.domain.selection'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/domain/selection.py
"""Выбор версии платформы: чистая функция, всё окружение аргументами.

Порядок разрешения повторяет проверенный порядок штатного стартера
(скил platform-launch, [Ф] T-02.1/2): точная Version → DefaultVersion
секции, уточняющий маску → таблица DefaultVersion конфигурационных
файлов → максимальная установленная с этим префиксом. Отличие от
штатного — неустановленная версия не подменяется молча ([Ф] T-02.8):
возвращается NOT_INSTALLED, а «что молча запустил бы штатный стартер»
отдаётся отдельным полем fallback.

fallback подтверждён экспериментом только для несуществующей полной
версии (T-02.8); для INVALID_REQUEST и маски без совпадений это
экстраполяция. Секция без Version → максимальная установленная —
решение 9 плана 2, поведение штатного стартера не снималось.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from onecstarter.domain.default_version import DefaultVersionRule, substitute
from onecstarter.domain.version import VersionNumber, parse_version


class ResolutionSource(Enum):
    EXACT = "exact"
    SECTION_DEFAULT = "section-default"
    CFG_DEFAULT = "cfg-default"
    PREFIX_MAX = "prefix-max"
    MAX_INSTALLED = "max-installed"
    NOT_INSTALLED = "not-installed"
    INVALID_REQUEST = "invalid-request"


@dataclass(frozen=True)
class VersionResolution:
    version: VersionNumber | None
    source: ResolutionSource
    requested: VersionNumber | None
    fallback: VersionNumber | None


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

    if wanted is None:
        if overall is not None:
            return VersionResolution(overall, ResolutionSource.MAX_INSTALLED, None, overall)
        return VersionResolution(None, ResolutionSource.NOT_INSTALLED, None, None)

    if wanted.is_full:
        if wanted in pool:
            return VersionResolution(wanted, ResolutionSource.EXACT, wanted, overall)
        return VersionResolution(None, ResolutionSource.NOT_INSTALLED, wanted, overall)

    if section_default is not None:
        refined = _try_parse(section_default)
        if (
            refined is not None
            and refined.is_full
            and refined.starts_with(wanted)
            and refined in pool
        ):
            return VersionResolution(refined, ResolutionSource.SECTION_DEFAULT, wanted, overall)

    target = substitute(wanted, cfg_rules)
    if target is not None and target in pool:
        return VersionResolution(target, ResolutionSource.CFG_DEFAULT, wanted, overall)

    matching = [version for version in pool if version.starts_with(wanted)]
    if matching:
        return VersionResolution(matching[-1], ResolutionSource.PREFIX_MAX, wanted, overall)
    return VersionResolution(None, ResolutionSource.NOT_INSTALLED, wanted, overall)


def _try_parse(text: str) -> VersionNumber | None:
    try:
        return parse_version(text)
    except ValueError:
        return None
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_selection.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/selection.py tests/unit/test_selection.py
git commit -m "feat: выбор версии платформы с источником решения"
```

---

### Task 4: `domain/connect.py` — разбор строки соединения

Read-only интерпретация: фрагменты извлекаются для классификации и показа,
исходная строка `Connect` никогда не пересобирается из фрагментов —
round-trip держит слой `config` (инвариант 3).

**Files:**

- Create: `src/onecstarter/domain/connect.py`
- Test: `tests/unit/test_connect.py`

**Interfaces:**

- Consumes: —
- Produces (используют план 3 — выбор клиента/браузера, план 4 — диалоги):
  - `@dataclass(frozen=True) ConnectFragment(name: str, value: str)` — `value` раскавычен
  - `class ConnectKind(Enum)`: `FILE`, `SERVER`, `WEB`, `UNKNOWN`
  - `parse_connect(connect: str) -> list[ConnectFragment]` — фрагменты `Имя=Значение` через `;`, `;` внутри кавычек не разделитель; фрагмент без `=` пропускается
  - `find_fragment(fragments: Sequence[ConnectFragment], name: str) -> str | None` — имя регистронезависимо (в реальных файлах `File=`/`Srvr=` с заглавной, но `ws=` строчными — **[Ф]** скил v8i-format)
  - `classify_connect(connect: str) -> ConnectKind` — `File` → FILE, `ws` → WEB, `Srvr`/`Ref` → SERVER, иначе UNKNOWN

Правило кавычек: значение в двойных кавычках, `""` внутри — литеральная кавычка.
Экранирование кавычек в `Connect` экспериментально **не проверено** (отмечено в скиле
v8i-format) — правило удвоения принято по аналогии с документированным правилом
`/IBConnectionString`; зафиксировать допущение в докстринге. `Srvr` дальше не разбирается:
IPv6-адреса содержат двоеточия и скобки (скил platform-launch), а для v1 разбор адреса не нужен.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_connect.py
from onecstarter.domain.connect import (
    ConnectFragment,
    ConnectKind,
    classify_connect,
    find_fragment,
    parse_connect,
)


def test_file_connect() -> None:
    fragments = parse_connect('File="C:\\Bases\\Demo";')
    assert fragments == [ConnectFragment(name="File", value="C:\\Bases\\Demo")]
    assert classify_connect('File="C:\\Bases\\Demo";') is ConnectKind.FILE


def test_server_connect() -> None:
    fragments = parse_connect('Srvr="srv-1c:1541";Ref="demo";')
    assert fragments == [
        ConnectFragment(name="Srvr", value="srv-1c:1541"),
        ConnectFragment(name="Ref", value="demo"),
    ]
    assert classify_connect('Srvr="srv-1c:1541";Ref="demo";') is ConnectKind.SERVER


def test_web_connect_lowercase_name() -> None:
    # [Ф] в реальных файлах имя фрагмента ws — строчными.
    assert classify_connect('ws="http://web-server/resource/";') is ConnectKind.WEB


def test_classification_is_case_insensitive() -> None:
    assert classify_connect('FILE="C:\\Bases\\Demo";') is ConnectKind.FILE


def test_semicolon_inside_quotes_is_not_separator() -> None:
    fragments = parse_connect('Srvr="srv;backup";Ref="demo";')
    assert fragments[0] == ConnectFragment(name="Srvr", value="srv;backup")


def test_doubled_quotes_become_literal_quote() -> None:
    fragments = parse_connect('File="C:\\Каталог с ""кавычкой""";')
    assert fragments[0].value == 'C:\\Каталог с "кавычкой"'


def test_unquoted_value() -> None:
    fragments = parse_connect("Srvr=srv;Ref=demo;")
    assert fragments == [
        ConnectFragment(name="Srvr", value="srv"),
        ConnectFragment(name="Ref", value="demo"),
    ]


def test_find_fragment_case_insensitive() -> None:
    fragments = parse_connect('File="C:\\Bases\\Demo";')
    assert find_fragment(fragments, "file") == "C:\\Bases\\Demo"
    assert find_fragment(fragments, "Srvr") is None


def test_garbage_is_unknown() -> None:
    assert parse_connect("просто текст") == []
    assert classify_connect("просто текст") is ConnectKind.UNKNOWN
    assert classify_connect("") is ConnectKind.UNKNOWN
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_connect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.domain.connect'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/domain/connect.py
"""Read-only разбор строки соединения Connect.

Строка соединения — не INI: фрагменты Имя=Значение через ";", значение
может быть в двойных кавычках, ";" внутри кавычек — часть значения.
Правило «"" внутри кавычек = литеральная кавычка» — допущение по аналогии
с документированным правилом /IBConnectionString; экранирование кавычек
в Connect экспериментально не проверено (скил v8i-format, «Непроверенное»).
Исходная строка никогда не пересобирается из фрагментов — round-trip
держит слой config.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ConnectFragment:
    name: str
    value: str


class ConnectKind(Enum):
    FILE = "file"
    SERVER = "server"
    WEB = "web"
    UNKNOWN = "unknown"


def parse_connect(connect: str) -> list[ConnectFragment]:
    fragments: list[ConnectFragment] = []
    for part in _split_fragments(connect):
        name, has_eq, value = part.partition("=")
        if not has_eq:
            continue
        fragments.append(ConnectFragment(name=name, value=_unquote(value)))
    return fragments


def find_fragment(fragments: Sequence[ConnectFragment], name: str) -> str | None:
    wanted = name.casefold()
    for fragment in fragments:
        if fragment.name.casefold() == wanted:
            return fragment.value
    return None


def classify_connect(connect: str) -> ConnectKind:
    names = {fragment.name.casefold() for fragment in parse_connect(connect)}
    if "file" in names:
        return ConnectKind.FILE
    if "ws" in names:
        return ConnectKind.WEB
    if "srvr" in names or "ref" in names:
        return ConnectKind.SERVER
    return ConnectKind.UNKNOWN


def _split_fragments(text: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            buffer.append(char)
        elif char == ";" and not in_quotes:
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    parts.append("".join(buffer))
    return [part for part in (raw.strip() for raw in parts) if part]


def _unquote(value: str) -> str:
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value
```

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_connect.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/connect.py tests/unit/test_connect.py
git commit -m "feat: разбор и классификация строки соединения"
```

---

### Task 5: `domain/launch.py` — выбор клиента и сборка командной строки

**Files:**

- Create: `src/onecstarter/domain/launch.py`
- Test: `tests/unit/test_launch.py`

**Interfaces:**

- Consumes: `Installation`, `VersionNumber` из Task 1.
- Produces (используют Task 6–8 и план 3):
  - `class ClientKind(Enum)`: `THIN = "thin"`, `THICK = "thick"`, `DESIGNER = "designer"` — значения совпадают с ключами `registry.toml`
  - `@dataclass(frozen=True) ClientConvention(min_version: VersionNumber, bin_dir: str, executables: Mapping[ClientKind, str])`
  - `convention_for(version: VersionNumber, conventions: Sequence[ClientConvention]) -> ClientConvention | None` — запись с максимальной `min_version ≤ version`
  - `@dataclass(frozen=True) ClientChoice(client: ClientKind, auto_check_mode: bool)`
  - `choose_client(app: str | None, default_app: str | None, forced: ClientKind | None = None) -> ClientChoice`
  - `quote_launch_value(value: str) -> str` — кавычки вокруг, внутренние удвоены
  - `build_arguments(client: ClientKind, *, ib_name: str | None = None, connect: str | None = None, auto_check_version: bool, auto_check_mode: bool) -> str` — ровно одно из `ib_name`/`connect`, иначе `ValueError`
  - `@dataclass(frozen=True) LaunchCommand(executable: Path, arguments: str)` со свойством `command_line: str` = `f'"{executable}" {arguments}'`
  - `build_launch_command(installation: Installation, convention: ClientConvention, client: ClientKind, arguments: str) -> LaunchCommand`

Правила `choose_client` (**[Ф]** T-02.6 и справочник v8i-format):

- `forced` (пользователь явно выбрал клиента/конфигуратор в UI) → он, `auto_check_mode=False`;
- явный `App=ThinClient|ThickClient` → соответствующий клиент, `auto_check_mode=False` — **[Ф]** при явном `App` стартер не передаёт `/AppAutoCheckMode`;
- `App=Auto`, отсутствует или незнакомое значение → `DefaultApp`, если задан, иначе тонкий клиент; `auto_check_mode=True` (из документации: `DefaultApp` запускается тоже с `/AppAutoCheckMode`);
- `App=WebClient` → `ValueError`: веб-клиент запускается браузером (решение 8), слой выше обязан проверить `classify_connect`/`App` раньше.

Правила `build_arguments`:

- первый аргумент — режим: `DESIGNER` для `ClientKind.DESIGNER`, иначе `ENTERPRISE`;
- `/IBName"<имя>"` — значение в кавычках, внутренние удвоены (правило из Приложения 7 ИТС); форма присоединения снята с реального процесса **[Ф]**;
- `/IBConnectionString"<строка>"` — вся строка в кавычках, внутренние удвоены (документировано); способ присоединения к ключу — по аналогии, **[не проверено]** (решение 1);
- `/AppAutoCheckVersion` при `auto_check_version=True` (позитивная форма явно — побайтовое совпадение со штатным), `/AppAutoCheckVersion-` при `False` — обязателен, когда версию выбрали мы, иначе платформа переиграет выбор (скил platform-launch);
- `/AppAutoCheckMode` — только при `auto_check_mode=True`, последним. Порядок двух
  `/AppAutoCheck*`-ключей — наш канонический (решение 2): штатный стартер выдаёт их
  в разном порядке от запуска к запуску, семантика от порядка не зависит.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_launch.py
from pathlib import Path

import pytest

from onecstarter.domain.launch import (
    ClientChoice,
    ClientConvention,
    ClientKind,
    LaunchCommand,
    build_arguments,
    build_launch_command,
    choose_client,
    convention_for,
    quote_launch_value,
)
from onecstarter.domain.version import Arch, Installation, parse_version

CONVENTION_8_2 = ClientConvention(
    min_version=parse_version("8.2"),
    bin_dir="bin",
    executables={
        ClientKind.THIN: "1cv8c.exe",
        ClientKind.THICK: "1cv8.exe",
        ClientKind.DESIGNER: "1cv8.exe",
    },
)


class TestChooseClient:
    def test_auto_defaults_to_thin_with_check_mode(self) -> None:
        # [Ф] штатный при App=Auto: 1cv8c.exe ... /AppAutoCheckMode
        assert choose_client(None, None) == ClientChoice(ClientKind.THIN, auto_check_mode=True)
        assert choose_client("Auto", None) == ClientChoice(ClientKind.THIN, auto_check_mode=True)

    def test_auto_uses_default_app(self) -> None:
        choice = choose_client("Auto", "ThickClient")
        assert choice == ClientChoice(ClientKind.THICK, auto_check_mode=True)

    def test_explicit_app_disables_check_mode(self) -> None:
        # [Ф] T-02.6: при явном App стартер не передаёт /AppAutoCheckMode.
        assert choose_client("ThinClient", None) == ClientChoice(
            ClientKind.THIN, auto_check_mode=False
        )
        assert choose_client("thickclient", None) == ClientChoice(
            ClientKind.THICK, auto_check_mode=False
        )

    def test_forced_client_wins(self) -> None:
        choice = choose_client("ThinClient", None, forced=ClientKind.DESIGNER)
        assert choice == ClientChoice(ClientKind.DESIGNER, auto_check_mode=False)

    def test_web_client_is_not_an_executable(self) -> None:
        with pytest.raises(ValueError, match="браузером"):
            choose_client("WebClient", None)

    def test_unknown_app_value_behaves_like_auto(self) -> None:
        choice = choose_client("НечтоНовое", None)
        assert choice == ClientChoice(ClientKind.THIN, auto_check_mode=True)


class TestBuildArguments:
    def test_matches_starter_snapshot_for_auto(self) -> None:
        # [Ф] снято с реального процесса:
        # 1cv8c.exe ENTERPRISE /IBName"empty" /AppAutoCheckVersion /AppAutoCheckMode
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=True, auto_check_mode=True
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /AppAutoCheckVersion /AppAutoCheckMode'

    def test_matches_starter_snapshot_for_explicit_app(self) -> None:
        # [Ф] T-02.6: ENTERPRISE /IBName"..." /AppAutoCheckVersion
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=True, auto_check_mode=False
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /AppAutoCheckVersion'

    def test_self_resolved_version_disables_auto_check(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=False, auto_check_mode=True
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /AppAutoCheckVersion- /AppAutoCheckMode'

    def test_designer_mode_is_first_argument(self) -> None:
        arguments = build_arguments(
            ClientKind.DESIGNER, ib_name="empty", auto_check_version=False, auto_check_mode=False
        )
        assert arguments == 'DESIGNER /IBName"empty" /AppAutoCheckVersion-'

    def test_quotes_in_name_are_doubled(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN,
            ib_name='База "СтройТорг"',
            auto_check_version=False,
            auto_check_mode=False,
        )
        assert '/IBName"База ""СтройТорг"""' in arguments

    def test_connect_route(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN,
            connect='File="C:\\Bases\\Demo";',
            auto_check_version=False,
            auto_check_mode=True,
        )
        assert arguments == (
            'ENTERPRISE /IBConnectionString"File=""C:\\Bases\\Demo"";"'
            " /AppAutoCheckVersion- /AppAutoCheckMode"
        )

    def test_exactly_one_target_required(self) -> None:
        with pytest.raises(ValueError, match="ровно одно"):
            build_arguments(
                ClientKind.THIN, auto_check_version=True, auto_check_mode=True
            )
        with pytest.raises(ValueError, match="ровно одно"):
            build_arguments(
                ClientKind.THIN,
                ib_name="empty",
                connect='File="C:\\B";',
                auto_check_version=True,
                auto_check_mode=True,
            )


def test_quote_launch_value() -> None:
    assert quote_launch_value("empty") == '"empty"'
    assert quote_launch_value('a"b') == '"a""b"'


def test_convention_for_picks_highest_applicable() -> None:
    newer = ClientConvention(
        min_version=parse_version("8.5"),
        bin_dir="bin",
        executables={ClientKind.THIN: "newclient.exe"},
    )
    conventions = [CONVENTION_8_2, newer]
    assert convention_for(parse_version("8.3.25.1633"), conventions) is CONVENTION_8_2
    assert convention_for(parse_version("8.5.4.100"), conventions) is newer
    assert convention_for(parse_version("8.1.5.100"), conventions) is None


def test_build_launch_command_composes_path() -> None:
    installation = Installation(
        version=parse_version("8.3.25.1633"),
        path=Path("C:/Program Files/1cv8/8.3.25.1633"),
        arch=Arch.X64,
    )
    command = build_launch_command(installation, CONVENTION_8_2, ClientKind.THIN, "ENTERPRISE")
    assert command == LaunchCommand(
        executable=Path("C:/Program Files/1cv8/8.3.25.1633/bin/1cv8c.exe"),
        arguments="ENTERPRISE",
    )
    assert command.command_line == (
        '"C:\\Program Files\\1cv8\\8.3.25.1633\\bin\\1cv8c.exe" ENTERPRISE'
    )
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_launch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.domain.launch'`

Примечание: `command.command_line` сравнивается со строкой с `\\` — `Path` на Windows
нормализует разделители; если тест упадёт на форме слэшей, эталон поправить по факту
вывода `Path`, важна логика «exe в кавычках + пробел + аргументы».

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/domain/launch.py
"""Выбор клиента и сборка командной строки запуска.

Командная строка собирается строкой, а не argv-списком: эталон — снятые
с реального процесса командные строки штатного стартера ([Ф] скил
platform-launch), побайтовое совпадение с ними проверяется тестами.
Секреты в аргументы не попадают: основной путь запуска — /IBName, при
котором платформа сама читает всё нужное из ibases.v8i.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from onecstarter.domain.version import Installation, VersionNumber


class ClientKind(Enum):
    THIN = "thin"
    THICK = "thick"
    DESIGNER = "designer"


@dataclass(frozen=True)
class ClientConvention:
    min_version: VersionNumber
    bin_dir: str
    executables: Mapping[ClientKind, str]


def convention_for(
    version: VersionNumber, conventions: Sequence[ClientConvention]
) -> ClientConvention | None:
    best: ClientConvention | None = None
    for convention in conventions:
        if version < convention.min_version:
            continue
        if best is None or convention.min_version > best.min_version:
            best = convention
    return best


@dataclass(frozen=True)
class ClientChoice:
    client: ClientKind
    auto_check_mode: bool


_APP_CLIENTS = {"thinclient": ClientKind.THIN, "thickclient": ClientKind.THICK}


def choose_client(
    app: str | None,
    default_app: str | None,
    forced: ClientKind | None = None,
) -> ClientChoice:
    if forced is not None:
        return ClientChoice(forced, auto_check_mode=False)
    explicit = _client_from_app(app)
    if explicit is not None:
        # [Ф] T-02.6: при явном App стартер не передаёт /AppAutoCheckMode.
        return ClientChoice(explicit, auto_check_mode=False)
    fallback = _client_from_app(default_app) or ClientKind.THIN
    return ClientChoice(fallback, auto_check_mode=True)


def _client_from_app(app: str | None) -> ClientKind | None:
    if app is None:
        return None
    normalized = app.casefold()
    if normalized == "webclient":
        raise ValueError("App=WebClient запускается браузером, а не исполняемым файлом")
    return _APP_CLIENTS.get(normalized)


def quote_launch_value(value: str) -> str:
    doubled = value.replace('"', '""')
    return f'"{doubled}"'


def build_arguments(
    client: ClientKind,
    *,
    ib_name: str | None = None,
    connect: str | None = None,
    auto_check_version: bool,
    auto_check_mode: bool,
) -> str:
    if (ib_name is None) == (connect is None):
        raise ValueError("Нужно ровно одно из: ib_name, connect")
    mode = "DESIGNER" if client is ClientKind.DESIGNER else "ENTERPRISE"
    parts = [mode]
    if ib_name is not None:
        parts.append(f"/IBName{quote_launch_value(ib_name)}")
    else:
        assert connect is not None
        # Способ присоединения значения к /IBConnectionString не проверен
        # экспериментально — принят по аналогии со снятой формой /IBName
        # (решение 1 плана 2); проверить при первом реальном запуске.
        parts.append(f"/IBConnectionString{quote_launch_value(connect)}")
    parts.append("/AppAutoCheckVersion" if auto_check_version else "/AppAutoCheckVersion-")
    if auto_check_mode:
        parts.append("/AppAutoCheckMode")
    return " ".join(parts)


@dataclass(frozen=True)
class LaunchCommand:
    executable: Path
    arguments: str

    @property
    def command_line(self) -> str:
        return f'"{self.executable}" {self.arguments}'


def build_launch_command(
    installation: Installation,
    convention: ClientConvention,
    client: ClientKind,
    arguments: str,
) -> LaunchCommand:
    executable = installation.path / convention.bin_dir / convention.executables[client]
    return LaunchCommand(executable=executable, arguments=arguments)
```

Примечание: если `ruff` ругается на `assert` в теле функции (`S101` включается только
в тестах по умолчанию — обычно нет) — заменить на явную проверку `if connect is None: raise`.
`mypy --strict` без `assert` не сузит тип — при замене использовать
`typing.cast` не нужно, достаточно ветвления.

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_launch.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/launch.py tests/unit/test_launch.py
git commit -m "feat: выбор клиента и сборка командной строки запуска"
```

---

### Task 6: `platform_1c/registry.toml` + загрузчик — раскладка версий как данные

**Files:**

- Create: `src/onecstarter/platform_1c/registry.toml`
- Create: `src/onecstarter/platform_1c/registry.py`
- Test: `tests/unit/test_registry.py`

**Interfaces:**

- Consumes: `ClientConvention`, `ClientKind`, `convention_for` (Task 5); `parse_version` (Task 1).
- Produces (используют Task 7 и план 3):
  - `load_conventions(data: bytes | None = None) -> list[ClientConvention]` — без аргумента читает `registry.toml` из пакета через `importlib.resources`; с аргументом — переданные байты (тестируемость и будущая подмена реестра без релиза)

Содержимое реестра — проверенные факты **[Ф]**: клиенты в `<корень>\<версия>\bin\`,
тонкий — `1cv8c.exe` (в т.ч. для файловых баз, T-02.6), толстый и конфигуратор — `1cv8.exe`.
`1cv8s.exe` намеренно не используется. Нижняя граница `8.2` — по алгоритму ИТС
(8.0/8.1 живут по другим правилам и в v1 не поддерживаются).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_registry.py
import pytest

from onecstarter.domain.launch import ClientKind, convention_for
from onecstarter.domain.version import parse_version
from onecstarter.platform_1c.registry import load_conventions


def test_packaged_registry_loads() -> None:
    conventions = load_conventions()
    assert len(conventions) == 1
    convention = conventions[0]
    assert convention.min_version == parse_version("8.2")
    assert convention.bin_dir == "bin"
    # [Ф] T-02.6: тонкий клиент файловой базы — 1cv8c.exe, не 1cv8s.exe.
    assert convention.executables[ClientKind.THIN] == "1cv8c.exe"
    assert convention.executables[ClientKind.THICK] == "1cv8.exe"
    assert convention.executables[ClientKind.DESIGNER] == "1cv8.exe"


def test_packaged_registry_covers_experiment_versions() -> None:
    conventions = load_conventions()
    assert convention_for(parse_version("8.3.25.1633"), conventions) is not None
    assert convention_for(parse_version("8.1.5.100"), conventions) is None


def test_custom_data_overrides_packaged_file() -> None:
    data = b"""
[[conventions]]
min_version = "9.0"
bin_dir = "app"

[conventions.executables]
thin = "client.exe"
"""
    conventions = load_conventions(data)
    assert len(conventions) == 1
    assert conventions[0].min_version == parse_version("9.0")
    assert conventions[0].executables == {ClientKind.THIN: "client.exe"}


def test_unknown_client_key_fails_loud() -> None:
    data = b"""
[[conventions]]
min_version = "8.2"
bin_dir = "bin"

[conventions.executables]
hologram = "1cv9.exe"
"""
    with pytest.raises(ValueError):
        load_conventions(data)
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.platform_1c.registry'`

- [ ] **Step 3: Создать `registry.toml`**

```toml
# Реестр раскладки версий платформы 1С — данные, не код (боль Д требований).
# Новая версия с теми же соглашениями работает без правок; изменение
# соглашений — новая запись [[conventions]] с большей min_version.
# Факты [Ф]: клиенты в <корень>\<версия>\bin\; тонкий клиент — 1cv8c.exe
# (в т.ч. для файловых баз, T-02.6); толстый и конфигуратор — 1cv8.exe.

[[conventions]]
min_version = "8.2"
bin_dir = "bin"

[conventions.executables]
thin = "1cv8c.exe"
thick = "1cv8.exe"
designer = "1cv8.exe"
```

- [ ] **Step 4: Реализация загрузчика**

```python
# src/onecstarter/platform_1c/registry.py
"""Загрузка реестра раскладки версий платформы из TOML-данных поставки."""

import tomllib
from importlib import resources

from onecstarter.domain.launch import ClientConvention, ClientKind
from onecstarter.domain.version import parse_version


def load_conventions(data: bytes | None = None) -> list[ClientConvention]:
    if data is None:
        data = (resources.files("onecstarter.platform_1c") / "registry.toml").read_bytes()
    payload = tomllib.loads(data.decode("utf-8"))
    conventions: list[ClientConvention] = []
    for entry in payload["conventions"]:
        executables = {
            ClientKind(kind): name for kind, name in entry["executables"].items()
        }
        conventions.append(
            ClientConvention(
                min_version=parse_version(entry["min_version"]),
                bin_dir=entry["bin_dir"],
                executables=executables,
            )
        )
    return conventions
```

`ClientKind("hologram")` бросает `ValueError` сам — «громкий» отказ на битом реестре
получается без дополнительного кода.

- [ ] **Step 5: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_registry.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS. Если `importlib.resources` не находит `registry.toml` — проверить,
что сборочный бэкенд в `pyproject.toml` включает не-Python файлы пакета (hatchling
включает всё содержимое пакета по умолчанию; для setuptools потребуется
`package-data`). Починить конфигурацию, не тест.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/platform_1c/registry.toml src/onecstarter/platform_1c/registry.py tests/unit/test_registry.py
git commit -m "feat: декларативный реестр раскладки версий платформы"
```

---

### Task 7: `platform_1c/discovery.py` — обнаружение установленных версий

**Files:**

- Create: `src/onecstarter/platform_1c/discovery.py`
- Test: `tests/unit/test_discovery.py`

**Interfaces:**

- Consumes: `parse_cestart_cfg` (config, план 1); `Arch`, `Installation`, `parse_version` (Task 1); `ClientConvention`, `ClientKind`, `convention_for` (Task 5).
- Produces (использует план 3):
  - `cfg_paths(env: Mapping[str, str]) -> list[Path]` — `%ALLUSERSPROFILE%\1C\1CEStart\1cestart.cfg`, `%APPDATA%\1C\1CEStart\1cestart.cfg` (в этом порядке — порядок уровней `InstalledLocation` из ИТС: общий → для всех → локальный; общий `1cescmn.cfg` в v1 не читается, решение 6)
  - `default_roots(env: Mapping[str, str]) -> list[Path]` — `%ProgramFiles%\1cv8`, `%ProgramFiles(x86)%\1cv8` (**[Ф]** реальный корень `C:\Program Files\1cv8`; каталог x86 может не существовать — скан это переживает)
  - `installed_location_roots(entries: Iterable[tuple[str, str]]) -> list[Path]` — значения `InstalledLocation`, ключ регистронезависимо (**[Ф]** прецедент `UseHWLicenses`)
  - `executable_arch(path: Path) -> Arch` — разрядность exe по полю `Machine` PE-заголовка (формат PE — общедоступная спецификация Windows, не факт 1С)
  - `discover_installations(roots: Iterable[Path], conventions: Sequence[ClientConvention]) -> list[Installation]` — подкаталог считается установкой, только если имя разбирается как версия И присутствует толстый клиент по соглашению раскладки (источник истины — файловая система, скил platform-launch, факт 2); первый найденный экземпляр версии побеждает; результат отсортирован по версии
  - `find_installations(env: Mapping[str, str], conventions: Sequence[ClientConvention]) -> list[Installation]` — композиция: cfg → корни (+умолчания, без дубликатов) → скан. Окружение подаётся аргументом — тестируется без реальной машины

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_discovery.py
import codecs
from pathlib import Path

from onecstarter.domain.launch import ClientConvention, ClientKind
from onecstarter.domain.version import Arch, parse_version
from onecstarter.platform_1c.discovery import (
    cfg_paths,
    default_roots,
    discover_installations,
    executable_arch,
    find_installations,
    installed_location_roots,
)

CONVENTIONS = [
    ClientConvention(
        min_version=parse_version("8.2"),
        bin_dir="bin",
        executables={ClientKind.THIN: "1cv8c.exe", ClientKind.THICK: "1cv8.exe"},
    )
]


def _fake_pe(machine: int) -> bytes:
    header = bytearray(64)
    header[0:2] = b"MZ"
    header[60:64] = (64).to_bytes(4, "little")
    return bytes(header) + b"PE\x00\x00" + machine.to_bytes(2, "little")


def _make_installation(root: Path, version: str, machine: int = 0x8664) -> None:
    bin_dir = root / version / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "1cv8.exe").write_bytes(_fake_pe(machine))


def test_executable_arch_x64_and_x86(tmp_path: Path) -> None:
    x64 = tmp_path / "x64.exe"
    x64.write_bytes(_fake_pe(0x8664))
    x86 = tmp_path / "x86.exe"
    x86.write_bytes(_fake_pe(0x14C))
    assert executable_arch(x64) is Arch.X64
    assert executable_arch(x86) is Arch.X86


def test_executable_arch_garbage_is_unknown(tmp_path: Path) -> None:
    not_pe = tmp_path / "data.exe"
    not_pe.write_bytes(b"\x00" * 128)
    assert executable_arch(not_pe) is Arch.UNKNOWN
    assert executable_arch(tmp_path / "missing.exe") is Arch.UNKNOWN


def test_discover_validates_layout_not_just_name(tmp_path: Path) -> None:
    _make_installation(tmp_path, "8.3.25.1633")
    _make_installation(tmp_path, "8.3.10.2252", machine=0x14C)
    (tmp_path / "common").mkdir()  # служебный каталог — не версия
    (tmp_path / "8.3.27.2214").mkdir()  # имя-версия без bin\1cv8.exe — не установка
    installations = discover_installations([tmp_path], CONVENTIONS)
    assert [str(item.version) for item in installations] == ["8.3.10.2252", "8.3.25.1633"]
    assert installations[0].arch is Arch.X86
    assert installations[1].arch is Arch.X64
    assert installations[1].path == tmp_path / "8.3.25.1633"


def test_discover_first_root_wins_for_duplicate_version(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _make_installation(first, "8.3.25.1633")
    _make_installation(second, "8.3.25.1633")
    installations = discover_installations([first, second], CONVENTIONS)
    assert len(installations) == 1
    assert installations[0].path == first / "8.3.25.1633"


def test_discover_survives_missing_root(tmp_path: Path) -> None:
    assert discover_installations([tmp_path / "нет"], CONVENTIONS) == []


def test_installed_location_key_is_case_insensitive() -> None:
    entries = [
        ("InstalledLocation", r"C:\Program Files\1cv8"),
        ("INSTALLEDLOCATION", r"D:\1cv8"),
        ("DefaultVersion", "8.3"),
    ]
    assert installed_location_roots(entries) == [
        Path(r"C:\Program Files\1cv8"),
        Path(r"D:\1cv8"),
    ]


def test_cfg_paths_and_default_roots() -> None:
    env = {
        "ALLUSERSPROFILE": r"C:\ProgramData",
        "APPDATA": r"C:\Users\demo\AppData\Roaming",
        "ProgramFiles": r"C:\Program Files",
    }
    assert cfg_paths(env) == [
        Path(r"C:\ProgramData\1C\1CEStart\1cestart.cfg"),
        Path(r"C:\Users\demo\AppData\Roaming\1C\1CEStart\1cestart.cfg"),
    ]
    assert default_roots(env) == [Path(r"C:\Program Files\1cv8")]


def test_find_installations_reads_cfg_and_defaults(tmp_path: Path) -> None:
    custom_root = tmp_path / "custom"
    _make_installation(custom_root, "8.3.25.1633")
    default_root = tmp_path / "pf" / "1cv8"
    _make_installation(default_root, "8.3.22.1923")
    appdata = tmp_path / "appdata"
    cfg_dir = appdata / "1C" / "1CEStart"
    cfg_dir.mkdir(parents=True)
    cfg_text = f"InstalledLocation={custom_root}\r\n"
    (cfg_dir / "1cestart.cfg").write_bytes(
        codecs.BOM_UTF16_LE + cfg_text.encode("utf-16-le")
    )
    env = {"APPDATA": str(appdata), "ProgramFiles": str(tmp_path / "pf")}
    installations = find_installations(env, CONVENTIONS)
    assert [str(item.version) for item in installations] == ["8.3.22.1923", "8.3.25.1633"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_discovery.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.platform_1c.discovery'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/platform_1c/discovery.py
"""Обнаружение установленных версий платформы.

Источник истины — файловая система: реестровых ключей 1С может не быть
даже при семи установленных версиях ([Ф] скил platform-launch, факт 2).
Каталог признаётся установкой, только если его имя разбирается как номер
версии И на месте толстый клиент по соглашению раскладки.

Ограничение v1: общий 1cescmn.cfg не читается — его расположение
не подтверждено на реальной машине (решение 6 плана 2). Читаются два
1cestart.cfg в порядке уровней InstalledLocation из ИТС:
для всех пользователей → локальный.
"""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from onecstarter.config.cestart_cfg import parse_cestart_cfg
from onecstarter.domain.launch import ClientConvention, ClientKind, convention_for
from onecstarter.domain.version import Arch, Installation, VersionNumber, parse_version

_PE_MACHINE = {0x8664: Arch.X64, 0x14C: Arch.X86}
_MZ_HEADER_SIZE = 64


def cfg_paths(env: Mapping[str, str]) -> list[Path]:
    paths: list[Path] = []
    for variable in ("ALLUSERSPROFILE", "APPDATA"):
        root = env.get(variable)
        if root:
            paths.append(Path(root) / "1C" / "1CEStart" / "1cestart.cfg")
    return paths


def default_roots(env: Mapping[str, str]) -> list[Path]:
    roots: list[Path] = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = env.get(variable)
        if base:
            roots.append(Path(base) / "1cv8")
    return roots


def installed_location_roots(entries: Iterable[tuple[str, str]]) -> list[Path]:
    return [
        Path(value) for key, value in entries if key.casefold() == "installedlocation"
    ]


def executable_arch(path: Path) -> Arch:
    try:
        with path.open("rb") as file:
            header = file.read(_MZ_HEADER_SIZE)
            if len(header) < _MZ_HEADER_SIZE or header[:2] != b"MZ":
                return Arch.UNKNOWN
            pe_offset = int.from_bytes(header[60:64], "little")
            file.seek(pe_offset)
            signature = file.read(6)
    except OSError:
        return Arch.UNKNOWN
    if len(signature) < 6 or signature[:4] != b"PE\x00\x00":
        return Arch.UNKNOWN
    machine = int.from_bytes(signature[4:6], "little")
    return _PE_MACHINE.get(machine, Arch.UNKNOWN)


def discover_installations(
    roots: Iterable[Path], conventions: Sequence[ClientConvention]
) -> list[Installation]:
    found: dict[VersionNumber, Installation] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            try:
                version = parse_version(child.name)
            except ValueError:
                continue
            if version in found:
                continue
            convention = convention_for(version, conventions)
            if convention is None:
                continue
            marker = convention.executables.get(ClientKind.THICK)
            if marker is None:
                continue
            executable = child / convention.bin_dir / marker
            if not executable.is_file():
                continue
            found[version] = Installation(
                version=version, path=child, arch=executable_arch(executable)
            )
    return sorted(found.values(), key=lambda item: item.version)


def find_installations(
    env: Mapping[str, str], conventions: Sequence[ClientConvention]
) -> list[Installation]:
    entries: list[tuple[str, str]] = []
    for cfg in cfg_paths(env):
        try:
            entries.extend(parse_cestart_cfg(cfg.read_bytes()))
        except OSError:
            continue
    roots = installed_location_roots(entries) + default_roots(env)
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return discover_installations(unique, conventions)
```

Примечание: `convention.executables.get(...)` требует, чтобы `executables` был
`Mapping` с методом `.get` — у `dict` он есть; если `mypy` сузит `Mapping.get`
до `str | None`, это ожидаемый тип `marker`.

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_discovery.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/platform_1c/discovery.py tests/unit/test_discovery.py
git commit -m "feat: обнаружение установленных версий платформы по файловой системе"
```

---

### Task 8: `platform_1c/process.py` — порождение процесса и финал плана

**Files:**

- Create: `src/onecstarter/platform_1c/process.py`
- Test: `tests/unit/test_process.py`
- Modify: `docs/tasks.md` (строка T-04.2)

**Interfaces:**

- Consumes: `LaunchCommand` (Task 5).
- Produces (использует план 3): `spawn(command: LaunchCommand) -> int` — запускает процесс отсоединённым, не ждёт завершения, возвращает pid.

**Процессы 1С в тестах не запускаются** (граница CLAUDE.md): тест использует
`sys.executable` со скриптом-заглушкой, которая пишет файл-маркер.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/test_process.py
import sys
import time
from pathlib import Path

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.process import spawn


def test_spawn_runs_detached_program(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    script = tmp_path / "stub.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ok')\n",
        encoding="utf-8",
    )
    command = LaunchCommand(executable=Path(sys.executable), arguments=f'"{script}"')
    pid = spawn(command)
    assert pid > 0
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.05)
    assert marker.exists(), "процесс-заглушка не отработал за 10 секунд"
    assert marker.read_text(encoding="utf-8") == "ok"


def test_spawn_quotes_executable_with_spaces(tmp_path: Path) -> None:
    # Косвенная проверка формы командной строки: exe в кавычках + пробел + аргументы.
    command = LaunchCommand(executable=Path(r"C:\Program Files\1cv8\bin\1cv8c.exe"), arguments="ENTERPRISE")
    assert command.command_line == r'"C:\Program Files\1cv8\bin\1cv8c.exe" ENTERPRISE'
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest tests/unit/test_process.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.platform_1c.process'`

- [ ] **Step 3: Реализация**

```python
# src/onecstarter/platform_1c/process.py
"""Порождение процессов клиентов 1С — единственное такое место в приложении.

Командная строка передаётся строкой, а не списком: форма аргументов
(/IBName"...") снята с реального процесса штатного стартера, и Popen
не должен переигрывать её квотирование. Процесс отсоединяется: судьба
клиента 1С не связана с жизнью OneCStarter.
"""

import subprocess
import warnings

from onecstarter.domain.launch import LaunchCommand


def spawn(command: LaunchCommand) -> int:
    process = subprocess.Popen(
        command.command_line,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    pid = process.pid
    # Ожидание завершения намеренно пропущено: судьба клиента 1С не связана
    # с жизнью OneCStarter. Брошенный Popen издаёт в __del__ ResourceWarning
    # «subprocess N is still running» — подавляем его точечно при удалении.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        del process
    return pid
```

Примечание (решение заказчика 01.08.2026, ревью Task 8): первоначальный вариант
`return process.pid` без удержания объекта издавал `ResourceWarning` в `__del__`
брошенного `Popen` при каждом запуске (в обычном выводе pytest невидим, ловится
`-W error::ResourceWarning`). Принято точечное подавление при `del process` —
без глобального состояния и без изменения семантики «не ждать».

Примечание: `subprocess.DETACHED_PROCESS` есть только на Windows — проект
объявлен Windows-only (требования, §4), охранных `sys.platform`-веток не делать.
Если `ruff` включит правило о `subprocess` без `check` — здесь это осознанно:
процесс не ожидается; подавить точечным `noqa` с комментарием, не отключать
правило глобально.

- [ ] **Step 4: Прогнать тесты и линтеры**

Run: `uv run pytest tests/unit/test_process.py -q && uv run ruff check . && uv run mypy`
Expected: все PASS.

- [ ] **Step 5: Полный прогон пакета**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: весь набор зелёный, включая тесты плана 1 (round-trip не задет — файлы плана 1 не менялись).

- [ ] **Step 6: Обновить статус T-04.2 в бэклоге**

В `docs/tasks.md` в строке T-04.2 заменить статус на `DONE` (ссылка на этот план там уже стоит).

- [ ] **Step 7: Commit**

```bash
git add src/onecstarter/platform_1c/process.py tests/unit/test_process.py docs/tasks.md
git commit -m "feat: порождение процесса клиента 1С; план 2 закрыт"
```

---

## Self-Review

Проверено при написании плана:

1. **Покрытие T-04.2 из tasks.md:** реестр версий — Task 6; обнаружение — Task 7; выбор версии — Task 1–3; командная строка — Task 4–5. Дополнительно `spawn` (Task 8) — обязанность `platform_1c` по спеке, решение 7.
2. **Инварианты CLAUDE.md:** Qt нигде не импортируется; выбор версии — чистая функция с табличными тестами (Task 3); секреты в командную строку не попадают (решение 1, `/IBName`); файлы 1С в этом плане не пишутся вообще.
3. **Согласованность типов между задачами:** `VersionNumber`/`Arch`/`Installation` (Task 1) используются в Task 2–7 под теми же именами; `ClientConvention.executables: Mapping[ClientKind, str]` одинаков в Task 5 (модель), 6 (загрузка), 7 (маркер `THICK`); `LaunchCommand.command_line` — единственная точка сборки полной строки, `spawn` её не дублирует.
4. **Факты помечены:** каждое поведенческое правило со ссылкой на скил и меткой [Ф]/[из документации]/[не проверено]/[решение]. Непроверенные допущения (форма `/IBConnectionString`, удвоение кавычек в `Connect`, «полная = 4 компонента») зафиксированы в докстрингах — при первой реальной проверке результат вернуть в скилы.
