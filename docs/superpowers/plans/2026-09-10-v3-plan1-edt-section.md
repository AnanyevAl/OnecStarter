# Проекты EDT — план 1 реализации v3: раздел «EDT»

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** новый раздел «EDT» — собственный реестр workspace'ов с группами, запуск EDT нужной версии с правильной JVM, открытие каталога проекта в VS Code/Antigravity, импорт из EDT Start, статус «запущен» с активацией окна.

**Architecture:** всё, что решает, — чистые функции в `domain/edt.py` (командная строка, подбор JDK, разбор `vm_args`, сопоставление процессов, дифф импорта); всё, что трогает диск, реестр EDT Start и Win32, — в `platform_1c/` (обнаружение установок, чтение `products.json`/`projects.json`, поиск редакторов, активация окна); хранение и оркестрация — `services/edt_store.py` + `services/edt.py::EdtWorkspace` по образцу `services/servers.py::ServersWorkspace`; Qt — только в `ui/edt/`. Фоновый опрос процессов и каталогов — калька `ui/servers/monitor.py`.

**Tech Stack:** Python 3.13, PySide6 (Qt 6.11), psutil, ctypes (Win32), pytest + pytest-qt, ruff, mypy strict.

Спека — [2026-09-10-v3-edt-design.md](../specs/2026-09-10-v3-edt-design.md), §0–§13.
CLI (§14) — план 2, закрытие вехи (эксперименты §10, скил §11, документы §13) — план 3.
Базовая точка — `master@55e7b1b` (v2.4 выпущена, 2021 тестов собираются).
Ветка — `feat/2026-09-10-v3-edt`, создаётся в Task 1.

## Global Constraints

- **Инвариант 1.** `PySide6` не импортируется из `domain`, `config`, `platform_1c`,
  `security`, `services` — ни прямо, ни транзитивно. Каждый новый модуль ядра
  добавляется строкой в `CORE` внутри `tests/unit/test_no_qt_in_core.py` в той же
  задаче, где создаётся, иначе сторож пройдёт зелёным мимо него.
- **Инвариант 2.** Командная строка, подбор JDK, сопоставление процессов, дифф
  импорта — чистые функции: ни ФС, ни процессов внутри, всё окружение аргументами.
- **Инвариант 4.** `edt.json` пишется только через `config.atomic.atomic_write`.
- **Инвариант 5.** В лог — только счётчики, типы исключений и места кадров; ни пути
  workspace, ни имени записи (`ui/background.py::_log_failure`, тот же приём).
- **Версия EDT — точное совпадение строк** (`edt_version == installation.version`),
  никакого «ближайшей» (спека §2).
- **Кавычки.** `-data` и `-vm` в командной строке EDT всегда в двойных кавычках
  (спека §3; [Ф] EDT Start квотирует `-vm`).
- Тексты в UI — по-русски. Точные строки: суффикс `(нет каталога)`; подсказка
  версии `EDT <версия> не найден`; пункт «Открыть в VS Code», «Открыть в Antigravity»,
  «Открыть в Проводнике», «Импорт из EDT Start…»; подсказка неактивного редактора
  `Не найден — укажите путь в Настройках`.
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` — зелёные перед каждым коммитом.
  Полный прогон pytest — в файл: `uv run pytest -q > e:/tmp/<имя>.log 2>&1`, не в `tail`
  (T-12 п. 15: интермиттентный access violation pytest-qt теряет блок падения).
  Субагент запускает pytest только в обычном режиме, не в фоне.
- Фикстуры `tests/fixtures/edtstart/*.json` — обезличенные: пути вида `D:\edt\...`,
  метки вида `Проект А`; структура реальная (продукт с `args`, проект без `args`,
  проект с `jvmPath`, `location` с кириллицей и пробелом, `jvmPath` с `%20`).
- Сообщения коммитов — по-русски, в стиле репозитория (`feat(domain): …`,
  `test(services): …`). Строк атрибуции не добавлять.
- 1С и EDT не запускать. Тесты подменяют `spawn`, `activate`, `startfile`.

## Карта файлов

| Файл | Ответственность | Задачи |
| --- | --- | --- |
| `src/onecstarter/domain/edt.py` | модель (`EdtGroup`, `EdtProject`, `EdtInstallation`, `EdtStartProduct`, `EdtStartProject`, `ImportCandidate`), `workspace_key`, `version_from_dir_name`, `parse_ini`, `parse_release`, `java_major`, `split_vm_args`/`join_vm_args`, `pick_jvm`, `build_edt_command`, `running_workspaces`, `resolve_editor`, `import_candidates` | 1–4, 6 |
| `src/onecstarter/platform_1c/edtstart_registry.py` | `file_url_to_path`, `parse_products`, `parse_projects`, `read_registry` | 5 |
| `src/onecstarter/platform_1c/edt_discovery.py` | `default_roots`, `discover_edt`, `read_jdk_version` | 7 |
| `src/onecstarter/platform_1c/editors.py` | `EditorKind`, `find_editor` | 8 |
| `src/onecstarter/platform_1c/window_activate.py` | `pick_window` (чистая), `activate_window` (ctypes) | 9 |
| `src/onecstarter/services/errors.py` | `EdtError`, `EdtUnavailableError`, `EdtLaunchError` | 10 |
| `src/onecstarter/services/edt_store.py` | `EdtRegistry`, `load_registry`, `save_registry` | 10 |
| `src/onecstarter/services/settings.py` | пять полей группы «EDT» | 11 |
| `src/onecstarter/services/edt.py` | `EdtWorkspace`, `EdtScan`, `scan_edt`, `EdtStatus`, `LaunchOutcome` | 12–13 |
| `src/onecstarter/ui/rail_icons.py` | `edt_icon` | 14 |
| `src/onecstarter/ui/edt/tree_model.py` | `build_edt_model`, роли, `visible_ids` | 14 |
| `src/onecstarter/ui/edt/monitor.py` | `EdtMonitor` | 14 |
| `src/onecstarter/ui/edt/view.py` | `EdtView`, `_EdtTree` | 14, 16, 17 |
| `src/onecstarter/ui/edt/dialog.py` | `EdtProjectDialog` | 15 |
| `src/onecstarter/ui/edt/group_dialog.py` | `EdtGroupDialog` | 16 |
| `src/onecstarter/ui/edt/import_dialog.py` | `EdtImportDialog` | 17 |
| `src/onecstarter/ui/settings_view.py` | группа «EDT» | 18 |
| `src/onecstarter/ui/app.py` | сборка раздела, монитор, обнаружение | 19 |
| `docs/tasks.md` | T-17 | 20 |

---

### Task 1: Ветка, модель домена, разбор имён и ini

**Files:**
- Create: `src/onecstarter/domain/edt.py`
- Create: `tests/unit/test_edt_domain.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.domain.edt"`)

**Interfaces:**
- Consumes: ничего.
- Produces: dataclass'ы `EdtGroup(id, name, parent_id)`, `EdtProject(id, name, workspace, project_dir, edt_version, jvm_dir, vm_args, group_id)`, `EdtInstallation(version, exe, jvm_dir, vm_args, required_java, jvm_source)`, `EdtStartProduct(id, version, exe, jvm_dir, args)`, `EdtStartProject(id, label, workspace, product_id, args, jvm_dir)`; функции `workspace_key(str) -> str`, `version_from_dir_name(str) -> str | None`, `parse_ini(str) -> IniInfo`, `parse_release(str) -> str | None`, `java_major(str) -> int | None`; константы `EDT_EXE = "1cedt.exe"`, `CLI_EXE = "1cedtcli.exe"`, `DEFAULT_REQUIRED_JAVA = 17`.

- [ ] **Step 1: Создать ветку**

```bash
git checkout -b feat/2026-09-10-v3-edt master
```

- [ ] **Step 2: Написать падающие тесты модели и разборов**

`tests/unit/test_edt_domain.py`:

```python
"""Домен EDT: модель, разбор имён каталогов, 1cedt.ini и release JDK (спека §0, §3)."""

import pytest

from onecstarter.domain.edt import (
    DEFAULT_REQUIRED_JAVA,
    EdtProject,
    IniInfo,
    java_major,
    parse_ini,
    parse_release,
    version_from_dir_name,
    workspace_key,
)


class TestModel:
    def test_project_defaults_are_empty(self) -> None:
        project = EdtProject(id="p1", name="Розница", workspace=r"D:\edt\retail")
        assert project.project_dir == ""
        assert project.edt_version == ""
        assert project.jvm_dir == ""
        assert project.vm_args == ""
        assert project.group_id is None


class TestWorkspaceKey:
    @pytest.mark.parametrize(
        ("left", "right"),
        [
            (r"D:\edt\Retail", r"d:\EDT\retail"),
            (r"D:\edt\retail\.", r"D:\edt\retail"),
            (r"D:/edt/retail", r"D:\edt\retail"),
            (r"D:\edt\x\..\retail", r"D:\edt\retail"),
        ],
    )
    def test_equal_keys(self, left: str, right: str) -> None:
        assert workspace_key(left) == workspace_key(right)

    def test_different_dirs_differ(self) -> None:
        assert workspace_key(r"D:\edt\a") != workspace_key(r"D:\edt\b")


class TestVersionFromDirName:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("1c-edt-2025.2.6+4-x86_64", "2025.2.6+4"),
            ("1c-edt-2026.1.2+2-x86_64", "2026.1.2+2"),
            ("1c-edt-2024.2.6+7-x86_64", "2024.2.6+7"),
            ("1c-edt-start-0.10.0+448-x86_64", None),  # лаунчер — не EDT
            ("axiom-jdk-full-17.0.16+12-x86_64", None),
            ("1c-edt-2025.2.6+4", None),  # без суффикса разрядности
            ("", None),
        ],
    )
    def test_table(self, name: str, expected: str | None) -> None:
        assert version_from_dir_name(name) == expected


INI_2025 = """-startup
plugins/org.eclipse.equinox.launcher_1.6.600.v20231106-1826.jar
-showsplash
com._1c.g5.v8.dt.product.application
-vmargs
-Dosgi.requiredJavaVersion=17
-Xms80m
-Xmx4096m
"""

INI_2024 = """-startup
plugins/org.eclipse.equinox.launcher_1.6.600.v20231106-1826.jar
-vm
C:\\Program Files\\Zulu\\zulu-17\\bin\\javaw.exe
-vmargs
-Dosgi.requiredJavaVersion=17
-Xmx4096m
"""


class TestParseIni:
    def test_without_vm(self) -> None:
        assert parse_ini(INI_2025) == IniInfo(vm=None, required_java=17)

    def test_with_vm(self) -> None:
        info = parse_ini(INI_2024)
        assert info.vm == r"C:\Program Files\Zulu\zulu-17\bin\javaw.exe"
        assert info.required_java == 17

    def test_required_java_defaults_when_absent(self) -> None:
        assert parse_ini("-vmargs\n-Xmx1g\n").required_java == DEFAULT_REQUIRED_JAVA

    def test_required_java_garbage_defaults(self) -> None:
        assert parse_ini("-Dosgi.requiredJavaVersion=abc\n").required_java == DEFAULT_REQUIRED_JAVA

    def test_vm_at_end_without_value_is_none(self) -> None:
        assert parse_ini("-vmargs\n-vm\n").vm is None

    def test_empty_text(self) -> None:
        assert parse_ini("") == IniInfo(vm=None, required_java=DEFAULT_REQUIRED_JAVA)


RELEASE = """IMPLEMENTOR="Axiom JSC"
JAVA_RUNTIME_VERSION="17.0.16+12-LTS"
JAVA_VERSION="17.0.16"
JAVA_VERSION_DATE="2025-07-15"
"""


class TestRelease:
    def test_parse_release(self) -> None:
        assert parse_release(RELEASE) == "17.0.16"

    def test_parse_release_missing(self) -> None:
        assert parse_release('IMPLEMENTOR="X"\n') is None

    @pytest.mark.parametrize(
        ("version", "expected"),
        [("17.0.16", 17), ("25.0.2", 25), ("1.8.0_392", 8), ("21", 21), ("", None), ("x.y", None)],
    )
    def test_java_major(self, version: str, expected: int | None) -> None:
        assert java_major(version) == expected
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_edt_domain.py -q`
Expected: ошибка импорта `onecstarter.domain.edt`.

- [ ] **Step 4: Написать модуль**

`src/onecstarter/domain/edt.py`:

```python
"""Домен раздела «EDT»: модель записей, установок и чистые решения (спека v3, §2–§6).

Ничего из этого модуля не обращается к ФС и процессам: всё окружение подаётся
аргументами (инвариант 2). Факты о раскладке EDT — спека §0, метки достоверности
там же; здесь они повторяются рядом с константами, которые на них опираются.
"""  # noqa: RUF002

import os
import re
from dataclasses import dataclass
from pathlib import Path

EDT_EXE = "1cedt.exe"  # [Ф] спека §0: каталог установки
CLI_EXE = "1cedtcli.exe"  # [Ф] спека §0-Д: консольная подсистема
DEFAULT_REQUIRED_JAVA = 17  # [Ф] -Dosgi.requiredJavaVersion=17 у всех трёх установок

# [Ф] спека §0: `1c-edt-<версия>-x86_64`; версия совпадает с installedVersion.label.
_EDT_DIR = re.compile(r"^1c-edt-(?P<version>\d[0-9A-Za-z.+]*)-x86_64$")
_REQUIRED_JAVA = re.compile(r"^-Dosgi\.requiredJavaVersion=(\d+)$")
_RELEASE_VERSION = re.compile(r'^JAVA_VERSION="([^"]+)"$', re.MULTILINE)


@dataclass(frozen=True)
class EdtGroup:
    id: str
    name: str
    parent_id: str | None = None


@dataclass(frozen=True)
class EdtProject:
    id: str
    name: str
    workspace: str  # путь для -data; обязателен
    project_dir: str = ""  # каталог для редакторов; "" — редакторы получают workspace
    edt_version: str = ""  # точно как в имени каталога установки: "2025.2.6+4"
    jvm_dir: str = ""  # каталог bin JDK; "" — JVM установки
    vm_args: str = ""  # аргументы JVM записи; "" — действуют 1cedt.ini и установка
    group_id: str | None = None


@dataclass(frozen=True)
class EdtInstallation:
    version: str
    exe: Path
    jvm_dir: Path | None  # подобранный каталог bin; None — не найден
    vm_args: str  # args продукта из products.json; "" — продукта там нет
    required_java: int
    jvm_source: str  # "products.json" | "1cedt.ini" | "settings" | "auto" | ""


@dataclass(frozen=True)
class EdtStartProduct:
    id: str
    version: str  # installedVersion.label
    exe: Path
    jvm_dir: Path | None
    args: tuple[str, ...]


@dataclass(frozen=True)
class EdtStartProject:
    id: str
    label: str
    workspace: Path
    product_id: str
    args: tuple[str, ...]
    jvm_dir: Path | None  # [?] ключ jvmPath у записи — спека §0, эксперимент 4


@dataclass(frozen=True)
class IniInfo:
    vm: str | None
    required_java: int


def workspace_key(path: str) -> str:
    """Ключ пути для сравнения: регистр, разделители, `.`/`..` — без обращения к диску.

    Та же формула, что `services/availability.py::path_key`; повторена здесь,
    потому что `domain` не импортирует `services`.
    """
    return os.path.normcase(os.path.normpath(path))


def version_from_dir_name(name: str) -> str | None:
    match = _EDT_DIR.match(name)
    return match.group("version") if match else None


def parse_ini(text: str) -> IniInfo:
    """`-vm` — строка после него (если есть), `-Dosgi.requiredJavaVersion=N` — порог JDK."""
    lines = [line.strip() for line in text.splitlines()]
    vm: str | None = None
    required = DEFAULT_REQUIRED_JAVA
    for index, line in enumerate(lines):
        if line == "-vm" and index + 1 < len(lines) and lines[index + 1]:
            vm = lines[index + 1]
            continue
        match = _REQUIRED_JAVA.match(line)
        if match:
            required = int(match.group(1))
    return IniInfo(vm=vm, required_java=required)


def parse_release(text: str) -> str | None:
    """`JAVA_VERSION="17.0.16"` из файла `release` в каталоге JDK ([Ф] спека §0)."""
    match = _RELEASE_VERSION.search(text)
    return match.group(1) if match else None


def java_major(version: str) -> int | None:
    """`17.0.16` → 17; старая схема `1.8.0_392` → 8."""
    parts = version.split(".")
    try:
        first = int(parts[0])
    except ValueError:
        return None
    if first == 1 and len(parts) > 1:
        try:
            return int(parts[1].split("_")[0])
        except ValueError:
            return None
    return first
```

- [ ] **Step 5: Добавить модуль в сторож инварианта 1**

В `tests/unit/test_no_qt_in_core.py`, в кортеж `CORE`, после `"onecstarter.domain.server_match",`:

```python
    "onecstarter.domain.edt",
```

- [ ] **Step 6: Прогнать тесты, линт, типы**

Run: `uv run pytest tests/unit/test_edt_domain.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: всё зелёное.

- [ ] **Step 7: Commit**

```bash
git add src/onecstarter/domain/edt.py tests/unit/test_edt_domain.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(domain): модель раздела EDT, разбор имени установки, 1cedt.ini и release JDK"
```

---

### Task 2: Домен — `vm_args`: одна строка, два фасада

**Files:**
- Modify: `src/onecstarter/domain/edt.py`
- Modify: `tests/unit/test_edt_domain.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `VmArgsParts(max_heap_mb: int | None, language: str | None, rest: tuple[str, ...])`, `split_vm_args(text: str) -> VmArgsParts`, `join_vm_args(max_heap_mb: int | None, language: str | None, rest: Sequence[str]) -> str`, `LANGUAGES: tuple[tuple[str, str], ...]` (`("", "По умолчанию"), ("ru", "Русский"), ("en", "English")`).

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_edt_domain.py`:

```python
from onecstarter.domain.edt import LANGUAGES, VmArgsParts, join_vm_args, split_vm_args


class TestSplitVmArgs:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("", VmArgsParts(None, None, ())),
            ("-Xmx8192m", VmArgsParts(8192, None, ())),
            ("-Xmx8g", VmArgsParts(8192, None, ())),
            ("-Xmx524288k", VmArgsParts(512, None, ())),
            ("-Xmx1073741824", VmArgsParts(1024, None, ())),
            ("-Duser.language=ru", VmArgsParts(None, "ru", ())),
            (
                "-Xmx4096m -DnativeFormBufferedLayoutRender=true -Xmx8192m",
                VmArgsParts(8192, None, ("-DnativeFormBufferedLayoutRender=true",)),
            ),  # повтор -Xmx — берётся последний (спека §2)
            (
                '-Dfoo="a b" -Xmx2g',
                VmArgsParts(2048, None, ('-Dfoo="a b"',)),
            ),
            ("-Xmxabc", VmArgsParts(None, None, ("-Xmxabc",))),  # неразбираемый — в «прочее»
            ('-Dbroken="unterminated', VmArgsParts(None, None, ('-Dbroken="unterminated',))),
        ],
    )
    def test_table(self, text: str, expected: VmArgsParts) -> None:
        assert split_vm_args(text) == expected


class TestJoinVmArgs:
    @pytest.mark.parametrize(
        ("heap", "language", "rest", "expected"),
        [
            (None, None, (), ""),
            (8192, None, (), "-Xmx8192m"),
            (None, "ru", (), "-Duser.language=ru"),
            (8192, "en", ("-Dx=1",), "-Dx=1 -Xmx8192m -Duser.language=en"),
            (None, "", ("-Dx=1",), "-Dx=1"),  # пустой язык = «по умолчанию», токена нет
        ],
    )
    def test_table(
        self, heap: int | None, language: str | None, rest: tuple[str, ...], expected: str
    ) -> None:
        assert join_vm_args(heap, language, rest) == expected

    @pytest.mark.parametrize(
        "text",
        ["-Xmx8192m", "-Dx=1 -Xmx8192m -Duser.language=ru", "-DnativeFormBufferedLayoutRender=true"],
    )
    def test_roundtrip(self, text: str) -> None:
        parts = split_vm_args(text)
        assert split_vm_args(join_vm_args(parts.max_heap_mb, parts.language, parts.rest)) == parts


def test_languages_have_default_first() -> None:
    assert LANGUAGES[0] == ("", "По умолчанию")
    assert [code for code, _label in LANGUAGES] == ["", "ru", "en"]
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_domain.py -q`
Expected: `ImportError: cannot import name 'VmArgsParts'`.

- [ ] **Step 3: Реализовать**

Добавить в `src/onecstarter/domain/edt.py` (импорты `shlex` и `Sequence` из `collections.abc` — в шапку):

```python
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("", "По умолчанию"),
    ("ru", "Русский"),
    ("en", "English"),
)

_XMX = re.compile(r"^-Xmx(\d+)([kKmMgG]?)$")
_LANGUAGE = re.compile(r"^-Duser\.language=(.+)$")


@dataclass(frozen=True)
class VmArgsParts:
    max_heap_mb: int | None
    language: str | None
    rest: tuple[str, ...]


def _tokens(text: str) -> list[str]:
    """Разбить строку аргументов, сохраняя кавычки в токенах.

    Незакрытая кавычка — не повод терять текст: вся строка становится
    одним токеном и уходит в «прочее» как есть.
    """
    if not text.strip():
        return []
    try:
        return shlex.split(text, posix=False)
    except ValueError:
        return [text.strip()]


def _heap_mb(amount: str, unit: str) -> int | None:
    value = int(amount)
    unit = unit.lower()
    if unit == "m":
        return value
    if unit == "g":
        return value * 1024
    if unit == "k":
        return value // 1024
    return value // (1024 * 1024)


def split_vm_args(text: str) -> VmArgsParts:
    """Память и язык — из токенов; при повторе `-Xmx` действует последний (спека §2)."""
    heap: int | None = None
    language: str | None = None
    rest: list[str] = []
    for token in _tokens(text):
        xmx = _XMX.match(token)
        if xmx:
            heap = _heap_mb(xmx.group(1), xmx.group(2))
            continue
        lang = _LANGUAGE.match(token)
        if lang:
            language = lang.group(1)
            continue
        rest.append(token)
    return VmArgsParts(max_heap_mb=heap, language=language, rest=tuple(rest))


def join_vm_args(max_heap_mb: int | None, language: str | None, rest: Sequence[str]) -> str:
    """Порядок сборки: прочее, затем `-Xmx`, затем `-Duser.language` (спека §2)."""
    tokens = list(rest)
    if max_heap_mb is not None:
        tokens.append(f"-Xmx{max_heap_mb}m")
    if language:
        tokens.append(f"-Duser.language={language}")
    return " ".join(tokens)
```

**Правка по итогам реализации (10.09.2026, коммит `a6bdd13`).** `shlex.split(text, posix=False)`
не держит кавычку внутри токена: `-Dfoo="a b" -Xmx2g` → `['-Dfoo="a', 'b"', '-Xmx2g']`, и тест
таблицы выше на нём падает. `_tokens` реализован своим проходом по строке: разделитель —
пробел вне двойных кавычек, кавычки остаются в токене, незакрытая кавычка — вся строка
одним токеном. Одинарные кавычки — обычные символы (спека §2: «кавычки Windows»).

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/unit/test_edt_domain.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/edt.py tests/unit/test_edt_domain.py
git commit -m "feat(domain): фасады памяти и языка над строкой vm_args записи EDT"
```

---

### Task 3: Домен — подбор JDK и командная строка EDT

**Files:**
- Modify: `src/onecstarter/domain/edt.py`
- Modify: `tests/unit/test_edt_domain.py`

**Interfaces:**
- Consumes: `EdtInstallation`, `EdtProject` (Task 1).
- Produces: `pick_jvm(*, product: Path | None, ini: Path | None, settings: Path | None, auto: Sequence[tuple[str, Path]], required_java: int) -> tuple[Path, str] | None` (`auto` — пары «строка `JAVA_VERSION` из `release`, каталог `bin`»; среди подходящих по major побеждает старшая полная версия, сравниваемая числами); `java_version_key(version: str) -> tuple[int, ...]`; `build_edt_command(exe: Path, workspace: str, jvm_dir: Path, installation_vm_args: str, project_vm_args: str) -> LaunchCommand`; `effective_jvm(project: EdtProject, installation: EdtInstallation) -> Path | None`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_edt_domain.py`:

```python
from pathlib import Path

from onecstarter.domain.edt import (
    EdtInstallation,
    build_edt_command,
    effective_jvm,
    java_version_key,
    pick_jvm,
)

JDK17 = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin")
JDK25 = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-25.0.2+12-x86_64\bin")
ZULU = Path(r"C:\Program Files\Zulu\zulu-17\bin")
MINE = Path(r"D:\jdk\bin")


class TestPickJvm:
    def test_products_json_wins(self) -> None:
        assert pick_jvm(
            product=JDK17, ini=ZULU, settings=MINE, auto=[("25.0.2", JDK25)], required_java=17
        ) == (JDK17, "products.json")

    def test_ini_when_no_product(self) -> None:
        assert pick_jvm(product=None, ini=ZULU, settings=MINE, auto=[], required_java=17) == (
            ZULU,
            "1cedt.ini",
        )

    def test_settings_when_no_product_and_ini(self) -> None:
        assert pick_jvm(product=None, ini=None, settings=MINE, auto=[], required_java=17) == (
            MINE,
            "settings",
        )

    def test_auto_picks_newest_fitting(self) -> None:
        assert pick_jvm(
            product=None, ini=None, settings=None,
            auto=[("17.0.16", JDK17), ("25.0.2", JDK25)], required_java=17,
        ) == (JDK25, "auto")

    def test_auto_same_major_picks_newest_full_version_numerically(self) -> None:
        older = Path(r"C:\jdk\axiom-jdk-full-17.0.9+7-x86_64\bin")
        assert pick_jvm(
            product=None, ini=None, settings=None,
            auto=[("17.0.9", older), ("17.0.16", JDK17)], required_java=17,
        ) == (JDK17, "auto")  # строкой "17.0.9" > "17.0.16" — потому сравнение числами

    def test_auto_skips_too_old(self) -> None:
        assert pick_jvm(
            product=None, ini=None, settings=None,
            auto=[("11.0.2", MINE), ("17.0.16", JDK17)], required_java=17,
        ) == (JDK17, "auto")

    def test_nothing_fits(self) -> None:
        assert pick_jvm(
            product=None, ini=None, settings=None, auto=[("11.0.2", MINE)], required_java=17
        ) is None

    @pytest.mark.parametrize(
        ("version", "expected"),
        [("17.0.16", (17, 0, 16)), ("25", (25,)), ("1.8.0_392", (1, 8, 0, 392)), ("", ()), ("x", ())],
    )
    def test_java_version_key(self, version: str, expected: tuple[int, ...]) -> None:
        assert java_version_key(version) == expected


def _installation(**overrides: object) -> EdtInstallation:
    values: dict[str, object] = {
        "version": "2025.2.6+4",
        "exe": Path(r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedt.exe"),
        "jvm_dir": JDK17,
        "vm_args": "-Xmx8192m -DnativeFormBufferedLayoutRender=true",
        "required_java": 17,
        "jvm_source": "products.json",
    }
    values.update(overrides)
    return EdtInstallation(**values)  # type: ignore[arg-type]


class TestBuildEdtCommand:
    def test_repeats_edt_start_line(self) -> None:
        # [Ф] спека §0: снято с живого процесса 1cedt.exe
        command = build_edt_command(
            _installation().exe,
            r"D:\edt\2025\retail",
            JDK17,
            "-Xmx8192m -DnativeFormBufferedLayoutRender=true",
            "-Xmx8192m",
        )
        assert command.executable == _installation().exe
        assert command.arguments == (
            f'-data "D:\\edt\\2025\\retail" -vm "{JDK17}" --launcher.appendVmargs '
            "-vmargs -Xmx8192m -DnativeFormBufferedLayoutRender=true "
            "-Djava.library.path= -Xmx8192m"
        )

    def test_empty_args_on_both_levels(self) -> None:
        command = build_edt_command(_installation().exe, r"D:\edt\a b", JDK17, "", "")
        assert command.arguments == (
            f'-data "D:\\edt\\a b" -vm "{JDK17}" --launcher.appendVmargs '
            "-vmargs -Djava.library.path="
        )

    def test_command_line_quotes_executable(self) -> None:
        command = build_edt_command(_installation().exe, r"D:\edt\a", JDK17, "", "")
        assert command.command_line.startswith('"C:\\Program Files\\1C\\1CE\\')


class TestEffectiveJvm:
    def test_project_override_wins(self) -> None:
        project = EdtProject(id="p", name="n", workspace=r"D:\w", jvm_dir=str(MINE))
        assert effective_jvm(project, _installation()) == MINE

    def test_installation_when_project_empty(self) -> None:
        project = EdtProject(id="p", name="n", workspace=r"D:\w")
        assert effective_jvm(project, _installation()) == JDK17

    def test_none_when_neither(self) -> None:
        project = EdtProject(id="p", name="n", workspace=r"D:\w")
        assert effective_jvm(project, _installation(jvm_dir=None)) is None
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_domain.py -q`
Expected: `ImportError` на `build_edt_command`.

- [ ] **Step 3: Реализовать**

Добавить в `src/onecstarter/domain/edt.py` (импорт `from onecstarter.domain.launch import LaunchCommand` — в шапку):

```python
def java_version_key(version: str) -> tuple[int, ...]:
    """`17.0.16` → (17, 0, 16); `1.8.0_392` → (1, 8, 0, 392) — для сравнения числами."""
    return tuple(int(part) for part in re.findall(r"\d+", version))


def pick_jvm(
    *,
    product: Path | None,
    ini: Path | None,
    settings: Path | None,
    auto: Sequence[tuple[str, Path]],
    required_java: int,
) -> tuple[Path, str] | None:
    """Цепочка спеки §3: products.json → 1cedt.ini → настройка → старший подходящий JDK.

    Все пути уже проверены на существование вызывающим (иначе `None`);
    здесь — только порядок предпочтения. `auto` — пары «`JAVA_VERSION`
    из `release`, каталог bin»: подходит major ≥ требуемого, побеждает старшая
    полная версия, сравниваемая числами (строкой `17.0.9` > `17.0.16` —
    находка ревью Task 3). Возвращает путь и имя источника для диалога записи.
    """
    for path, source in ((product, "products.json"), (ini, "1cedt.ini"), (settings, "settings")):
        if path is not None:
            return path, source
    fitting = [
        (version, path)
        for version, path in auto
        if (java_major(version) or 0) >= required_java
    ]
    if not fitting:
        return None
    _version, best = max(fitting, key=lambda pair: (java_version_key(pair[0]), str(pair[1])))
    return best, "auto"


def effective_jvm(project: EdtProject, installation: EdtInstallation) -> Path | None:
    if project.jvm_dir:
        return Path(project.jvm_dir)
    return installation.jvm_dir


def build_edt_command(
    exe: Path,
    workspace: str,
    jvm_dir: Path,
    installation_vm_args: str,
    project_vm_args: str,
) -> LaunchCommand:
    """Дословно строка EDT Start ([Ф] спека §0), включая `-Djava.library.path=`.

    Аргументы установки идут до аргументов записи: при повторе `-Xmx`
    JVM берёт последний ([?] спека §0, эксперимент 1), и запись побеждает.
    """
    parts = [
        f'-data "{workspace}"',
        f'-vm "{jvm_dir}"',
        "--launcher.appendVmargs",
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))
```

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/unit/test_edt_domain.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/edt.py tests/unit/test_edt_domain.py
git commit -m "feat(domain): подбор JDK по цепочке и командная строка запуска EDT"
```

---

### Task 4: Домен — сопоставление процессов с записями и выбор редактора

**Files:**
- Modify: `src/onecstarter/domain/edt.py`
- Modify: `tests/unit/test_edt_domain.py`

**Interfaces:**
- Consumes: `EdtProject`, `workspace_key` (Task 1).
- Produces: `running_workspaces(processes: Iterable[tuple[int, tuple[str, ...] | None]], projects: Iterable[EdtProject]) -> dict[str, int]` (id записи → pid); `EditorResolution(path: Path | None, source: str, note: str)`; `resolve_editor(setting: str, setting_exists: bool, found_in_path: Path | None, known_existing: Sequence[Path]) -> EditorResolution`; константа `EDITOR_MISSING_NOTE = "Не найден — укажите путь в Настройках"`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_edt_domain.py`:

```python
from onecstarter.domain.edt import (
    EDITOR_MISSING_NOTE,
    EditorResolution,
    resolve_editor,
    running_workspaces,
)

EXE = r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedt.exe"


def _argv(workspace: str) -> tuple[str, ...]:
    # [Ф] спека §0: форма argv живого 1cedt.exe
    return (EXE, "-data", workspace, "-vm", str(JDK17), "--launcher.appendVmargs", "-vmargs")


class TestRunningWorkspaces:
    def test_matches_by_normalized_workspace(self) -> None:
        projects = [EdtProject(id="p1", name="a", workspace=r"D:\edt\Retail")]
        result = running_workspaces([(4242, _argv(r"d:/EDT/retail/"))], projects)
        assert result == {"p1": 4242}

    def test_quoted_data_value(self) -> None:
        projects = [EdtProject(id="p1", name="a", workspace=r"D:\edt\a b")]
        result = running_workspaces([(1, _argv('"D:\\edt\\a b"'))], projects)
        assert result == {"p1": 1}

    def test_unrelated_process_ignored(self) -> None:
        projects = [EdtProject(id="p1", name="a", workspace=r"D:\edt\a")]
        assert running_workspaces([(1, _argv(r"D:\edt\other"))], projects) == {}

    def test_argv_none_skipped(self) -> None:
        projects = [EdtProject(id="p1", name="a", workspace=r"D:\edt\a")]
        assert running_workspaces([(1, None)], projects) == {}

    def test_data_without_value_skipped(self) -> None:
        projects = [EdtProject(id="p1", name="a", workspace=r"D:\edt\a")]
        assert running_workspaces([(1, (EXE, "-data"))], projects) == {}

    def test_first_pid_kept_for_duplicate(self) -> None:
        projects = [EdtProject(id="p1", name="a", workspace=r"D:\edt\a")]
        result = running_workspaces([(1, _argv(r"D:\edt\a")), (2, _argv(r"D:\edt\a"))], projects)
        assert result == {"p1": 1}


CODE = Path(r"C:\Users\u\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd")


class TestResolveEditor:
    def test_setting_existing_wins(self) -> None:
        assert resolve_editor(r"D:\tools\code.cmd", True, CODE, [CODE]) == EditorResolution(
            Path(r"D:\tools\code.cmd"), "settings", ""
        )

    def test_setting_missing_is_not_replaced_silently(self) -> None:
        result = resolve_editor(r"D:\tools\code.cmd", False, CODE, [CODE])
        assert result.path is None
        assert result.source == "settings"
        assert result.note == r"Указанный путь не существует: D:\tools\code.cmd"

    def test_path_hit(self) -> None:
        assert resolve_editor("", False, CODE, []) == EditorResolution(CODE, "PATH", "")

    def test_known_dir_fallback(self) -> None:
        assert resolve_editor("", False, None, [CODE]) == EditorResolution(CODE, "known", "")

    def test_nothing(self) -> None:
        assert resolve_editor("", False, None, []) == EditorResolution(
            None, "", EDITOR_MISSING_NOTE
        )
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_domain.py -q`
Expected: `ImportError` на `running_workspaces`.

- [ ] **Step 3: Реализовать**

Добавить в `src/onecstarter/domain/edt.py` (`Iterable` — в импорт из `collections.abc`):

```python
EDITOR_MISSING_NOTE = "Не найден — укажите путь в Настройках"


def running_workspaces(
    processes: Iterable[tuple[int, tuple[str, ...] | None]],
    projects: Iterable[EdtProject],
) -> dict[str, int]:
    """`-data <путь>` в argv `1cedt.exe` → запись с тем же ключом workspace (спека §4).

    `argv is None` — нет доступа к процессу, пропускается. Первый найденный
    pid остаётся: второго EDT на том же workspace не бывает (блокировка Eclipse),
    а если снимок застал два — активировать первый не хуже второго.
    """
    by_key = {workspace_key(project.workspace): project.id for project in projects}
    result: dict[str, int] = {}
    for pid, argv in processes:
        if not argv:
            continue
        for index, token in enumerate(argv[:-1]):
            if token != "-data":
                continue
            project_id = by_key.get(workspace_key(argv[index + 1].strip('"')))
            if project_id is not None and project_id not in result:
                result[project_id] = pid
            break
    return result


@dataclass(frozen=True)
class EditorResolution:
    path: Path | None
    source: str  # "settings" | "PATH" | "known" | ""
    note: str  # причина отказа для подсказки; "" — найден


def resolve_editor(
    setting: str,
    setting_exists: bool,
    found_in_path: Path | None,
    known_existing: Sequence[Path],
) -> EditorResolution:
    """Приоритет спеки §5: настройка непуста — только она; пуста — PATH, затем каталоги.

    Явно указанный несуществующий путь — «не найден», без тихого отката
    к автопоиску: пользователь увидит в Настройках, что путь не существует.
    """
    if setting:
        if setting_exists:
            return EditorResolution(Path(setting), "settings", "")
        return EditorResolution(None, "settings", f"Указанный путь не существует: {setting}")
    if found_in_path is not None:
        return EditorResolution(found_in_path, "PATH", "")
    if known_existing:
        return EditorResolution(known_existing[0], "known", "")
    return EditorResolution(None, "", EDITOR_MISSING_NOTE)
```

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/unit/test_edt_domain.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/edt.py tests/unit/test_edt_domain.py
git commit -m "feat(domain): статус «запущен» по argv 1cedt.exe и приоритет поиска редактора"
```

---

### Task 5: Чтение реестра EDT Start

**Files:**
- Create: `src/onecstarter/platform_1c/edtstart_registry.py`
- Create: `tests/fixtures/edtstart/products.json`
- Create: `tests/fixtures/edtstart/projects.json`
- Create: `tests/unit/test_edtstart_registry.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.platform_1c.edtstart_registry"`)

**Interfaces:**
- Consumes: `EdtStartProduct`, `EdtStartProject` (Task 1).
- Produces: `file_url_to_path(url: str) -> Path`; `parse_products(text: str) -> list[EdtStartProduct]`; `parse_projects(text: str) -> tuple[list[EdtStartProject], int]` (второй элемент — сколько записей пропущено); `EdtStartRegistry(products: tuple[EdtStartProduct, ...], projects: tuple[EdtStartProject, ...], skipped: int)`; `read_registry(root: Path) -> EdtStartRegistry | None` (`None` — каталога/файлов нет либо JSON битый); `default_edtstart_root(env: Mapping[str, str]) -> Path` (`%LOCALAPPDATA%\1C\1cedtstart`).

- [ ] **Step 1: Создать обезличенные фикстуры**

`tests/fixtures/edtstart/products.json` (структура [Ф] спека §0; пути и имена вымышленные):

```json
{
  "version" : "1.1",
  "data" : [ {
    "id" : "11111111-1111-1111-1111-111111111111",
    "label" : "1C:Enterprise Development Tools",
    "location" : "C:\\Program Files\\1C\\1CE\\components\\1c-edt-2025.2.6+4-x86_64\\1cedt.exe",
    "jvmPath" : "file:///C:/Program%20Files/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/",
    "description" : "Среда разработки 1C:Enterprise Development Tools",
    "name" : "epp.package.1cedt",
    "icon" : "C:\\Program Files\\1C\\1CE\\products\\1c-edt-product-offline-2025.2.6+4-x86_64\\logo.png",
    "vendor" : "",
    "installedVersion" : {
      "id" : "11111111-1111-1111-1111-111111111111",
      "label" : "2025.2.6+4",
      "name" : "2025.2.6+4",
      "starterUpdateRequired" : false,
      "isClientUpdateRequired" : false
    },
    "local" : true,
    "args" : [ "-Xmx8192m", "-DnativeFormBufferedLayoutRender=true" ]
  }, {
    "id" : "22222222-2222-2222-2222-222222222222",
    "label" : "1C:Enterprise Development Tools",
    "location" : "C:\\Program Files\\1C\\1CE\\components\\1c-edt-2026.1.2+2-x86_64\\1cedt.exe",
    "jvmPath" : "file:///C:/Program%20Files/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/",
    "name" : "epp.package.1cedt",
    "installedVersion" : {
      "id" : "22222222-2222-2222-2222-222222222222",
      "label" : "2026.1.2+2",
      "name" : "2026.1.2+2"
    },
    "local" : true,
    "unknownFutureKey" : { "nested" : true }
  } ]
}
```

`tests/fixtures/edtstart/projects.json`:

```json
{
  "version" : "1.1",
  "data" : [ {
    "id" : "aaaaaaaa-0000-0000-0000-000000000001",
    "label" : "(2025) Проект А",
    "location" : "D:\\edt\\2025-2-6\\project_a",
    "productId" : "11111111-1111-1111-1111-111111111111",
    "projectTypeId" : "7f5f86e2-6077-4a4e-9582-aed75e5d9cba",
    "args" : [ "-Xmx8192m" ]
  }, {
    "id" : "aaaaaaaa-0000-0000-0000-000000000002",
    "label" : "Проект Б без args",
    "location" : "d:\\edt\\2026-1-2\\project_b",
    "productId" : "22222222-2222-2222-2222-222222222222",
    "projectTypeId" : "7f5f86e2-6077-4a4e-9582-aed75e5d9cba"
  }, {
    "id" : "aaaaaaaa-0000-0000-0000-000000000003",
    "label" : "(2025) Проект В (с пробелом)",
    "location" : "D:\\edt\\2025-2-6\\(2025) проект в_ws",
    "productId" : "11111111-1111-1111-1111-111111111111",
    "projectTypeId" : "7f5f86e2-6077-4a4e-9582-aed75e5d9cba",
    "jvmPath" : "file:///D:/jdk/bin/",
    "args" : [ "-Xmx4096m", "-Duser.language=ru" ]
  }, {
    "id" : "aaaaaaaa-0000-0000-0000-000000000004",
    "label" : "Проект Г — продукт удалён",
    "location" : "D:\\edt\\2024\\project_g",
    "productId" : "99999999-9999-9999-9999-999999999999",
    "projectTypeId" : "7f5f86e2-6077-4a4e-9582-aed75e5d9cba"
  }, {
    "id" : "aaaaaaaa-0000-0000-0000-000000000005",
    "label" : "Битая запись без location",
    "productId" : "11111111-1111-1111-1111-111111111111"
  } ]
}
```

- [ ] **Step 2: Написать падающие тесты**

`tests/unit/test_edtstart_registry.py`:

```python
"""Чтение реестра EDT Start: терпимый разбор products.json / projects.json (спека §6)."""

import json
import shutil
from pathlib import Path

import pytest

from onecstarter.platform_1c.edtstart_registry import (
    EdtStartRegistry,
    default_edtstart_root,
    file_url_to_path,
    parse_products,
    parse_projects,
    read_registry,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edtstart"


class TestFileUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "file:///C:/Program%20Files/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/",
                Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin"),
            ),
            ("file:///D:/jdk/bin/", Path(r"D:\jdk\bin")),
            ("file:///D:/%D0%BF%D1%83%D1%82%D1%8C/bin", Path(r"D:\путь\bin")),
        ],
    )
    def test_table(self, url: str, expected: Path) -> None:
        assert file_url_to_path(url) == expected


class TestParseProducts:
    def test_reads_fixture(self) -> None:
        products = parse_products((FIXTURES / "products.json").read_text(encoding="utf-8"))
        assert [p.version for p in products] == ["2025.2.6+4", "2026.1.2+2"]
        first = products[0]
        assert first.id == "11111111-1111-1111-1111-111111111111"
        assert first.exe == Path(
            r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedt.exe"
        )
        assert first.jvm_dir == Path(
            r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin"
        )
        assert first.args == ("-Xmx8192m", "-DnativeFormBufferedLayoutRender=true")

    def test_product_without_args_has_empty_tuple(self) -> None:
        products = parse_products((FIXTURES / "products.json").read_text(encoding="utf-8"))
        assert products[1].args == ()

    def test_product_without_location_skipped(self) -> None:
        text = json.dumps({"data": [{"id": "x", "installedVersion": {"label": "1"}}]})
        assert parse_products(text) == []

    def test_not_a_dict_is_empty(self) -> None:
        assert parse_products("[]") == []


class TestParseProjects:
    def test_reads_fixture_and_counts_skipped(self) -> None:
        projects, skipped = parse_projects(
            (FIXTURES / "projects.json").read_text(encoding="utf-8")
        )
        assert skipped == 1
        assert [p.label for p in projects] == [
            "(2025) Проект А",
            "Проект Б без args",
            "(2025) Проект В (с пробелом)",
            "Проект Г — продукт удалён",
        ]

    def test_args_and_jvm(self) -> None:
        projects, _ = parse_projects((FIXTURES / "projects.json").read_text(encoding="utf-8"))
        assert projects[0].args == ("-Xmx8192m",)
        assert projects[0].jvm_dir is None
        assert projects[1].args == ()
        assert projects[2].jvm_dir == Path(r"D:\jdk\bin")
        assert projects[2].workspace == Path(r"D:\edt\2025-2-6\(2025) проект в_ws")


class TestReadRegistry:
    def test_reads_both_files(self, tmp_path: Path) -> None:
        shutil.copytree(FIXTURES, tmp_path / "1cedtstart")
        registry = read_registry(tmp_path / "1cedtstart")
        assert isinstance(registry, EdtStartRegistry)
        assert len(registry.products) == 2
        assert len(registry.projects) == 4
        assert registry.skipped == 1

    def test_missing_root_is_none(self, tmp_path: Path) -> None:
        assert read_registry(tmp_path / "nope") is None

    def test_broken_json_is_none(self, tmp_path: Path) -> None:
        root = tmp_path / "1cedtstart"
        root.mkdir()
        (root / "products.json").write_text("{", encoding="utf-8")
        (root / "projects.json").write_text("{}", encoding="utf-8")
        assert read_registry(root) is None

    def test_missing_projects_file_gives_empty_projects(self, tmp_path: Path) -> None:
        root = tmp_path / "1cedtstart"
        root.mkdir()
        shutil.copy(FIXTURES / "products.json", root / "products.json")
        registry = read_registry(root)
        assert registry is not None
        assert registry.projects == ()


def test_default_root() -> None:
    assert default_edtstart_root({"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}) == Path(
        r"C:\Users\u\AppData\Local\1C\1cedtstart"
    )
```

- [ ] **Step 3: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edtstart_registry.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Реализовать**

`src/onecstarter/platform_1c/edtstart_registry.py`:

```python
"""Реестр 1C:EDT Start — только чтение (спека v3, §6; факты — §0).

`%LOCALAPPDATA%\\1C\\1cedtstart\\products.json` — установленные EDT с JVM
и аргументами уровня «среда разработки»; `projects.json` — workspace'ы.
Разбор терпимый: неизвестные ключи игнорируются, запись без обязательных
ключей пропускается со счётчиком. В эти файлы никогда не пишем (решение
заказчика, спека §1).
"""  # noqa: RUF002

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from onecstarter.domain.edt import EdtStartProduct, EdtStartProject

__all__ = [
    "EdtStartRegistry",
    "default_edtstart_root",
    "file_url_to_path",
    "parse_products",
    "parse_projects",
    "read_registry",
]


@dataclass(frozen=True)
class EdtStartRegistry:
    products: tuple[EdtStartProduct, ...]
    projects: tuple[EdtStartProject, ...]
    skipped: int


def default_edtstart_root(env: Mapping[str, str]) -> Path:
    return Path(env.get("LOCALAPPDATA", ".")) / "1C" / "1cedtstart"


def file_url_to_path(url: str) -> Path:
    """`file:///C:/Program%20Files/x/bin/` → `C:\\Program Files\\x\\bin` ([Ф] спека §0)."""
    parsed = urlparse(url)
    raw = unquote(parsed.path)
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw[1:]
    return Path(raw.rstrip("/\\"))


def _jvm_of(entry: Mapping[str, Any]) -> Path | None:
    value = entry.get("jvmPath")
    return file_url_to_path(value) if isinstance(value, str) and value else None


def _args_of(entry: Mapping[str, Any]) -> tuple[str, ...]:
    value = entry.get("args")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _entries(text: str) -> list[Mapping[str, Any]]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def parse_products(text: str) -> list[EdtStartProduct]:
    products: list[EdtStartProduct] = []
    for entry in _entries(text):
        location = entry.get("location")
        installed = entry.get("installedVersion")
        version = installed.get("label") if isinstance(installed, dict) else None
        if not isinstance(location, str) or not isinstance(version, str):
            continue
        products.append(
            EdtStartProduct(
                id=str(entry.get("id", "")),
                version=version,
                exe=Path(location),
                jvm_dir=_jvm_of(entry),
                args=_args_of(entry),
            )
        )
    return products


def parse_projects(text: str) -> tuple[list[EdtStartProject], int]:
    projects: list[EdtStartProject] = []
    skipped = 0
    for entry in _entries(text):
        location = entry.get("location")
        product_id = entry.get("productId")
        if not isinstance(location, str) or not isinstance(product_id, str):
            skipped += 1
            continue
        projects.append(
            EdtStartProject(
                id=str(entry.get("id", "")),
                label=str(entry.get("label", "")),
                workspace=Path(location),
                product_id=product_id,
                args=_args_of(entry),
                jvm_dir=_jvm_of(entry),
            )
        )
    return projects, skipped


def read_registry(root: Path) -> EdtStartRegistry | None:
    """`None` — реестра нет или он не читается; раздел живёт без него (спека §6)."""
    products_path = root / "products.json"
    projects_path = root / "projects.json"
    try:
        products = parse_products(products_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    try:
        projects, skipped = parse_projects(projects_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        projects, skipped = [], 0
    except (OSError, ValueError):
        return None
    return EdtStartRegistry(tuple(products), tuple(projects), skipped)
```

- [ ] **Step 5: Сторож инварианта 1**

В `CORE` (`tests/unit/test_no_qt_in_core.py`) после `"onecstarter.platform_1c.server_spawn",`:

```python
    "onecstarter.platform_1c.edtstart_registry",
```

- [ ] **Step 6: Прогнать**

Run: `uv run pytest tests/unit/test_edtstart_registry.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 7: Commit**

```bash
git add src/onecstarter/platform_1c/edtstart_registry.py tests/unit/test_edtstart_registry.py tests/fixtures/edtstart tests/unit/test_no_qt_in_core.py
git commit -m "feat(platform): чтение реестра EDT Start с обезличенными фикстурами"
```

---

### Task 6: Домен — дифф импорта из EDT Start

**Files:**
- Modify: `src/onecstarter/domain/edt.py`
- Modify: `tests/unit/test_edt_domain.py`

**Interfaces:**
- Consumes: `EdtStartProduct`, `EdtStartProject`, `EdtProject`, `workspace_key` (Task 1).
- Produces: `ImportCandidate(project: EdtProject, version_known: bool)`; `import_candidates(projects: Sequence[EdtStartProject], products: Sequence[EdtStartProduct], existing: Iterable[EdtProject], new_id: Callable[[], str]) -> list[ImportCandidate]`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_edt_domain.py`:

```python
from itertools import count

from onecstarter.domain.edt import EdtStartProduct, EdtStartProject, ImportCandidate, import_candidates

PRODUCT = EdtStartProduct(
    id="prod-1",
    version="2025.2.6+4",
    exe=Path(EXE),
    jvm_dir=JDK17,
    args=("-Xmx8192m", "-DnativeFormBufferedLayoutRender=true"),
)


def _es_project(**overrides: object) -> EdtStartProject:
    values: dict[str, object] = {
        "id": "es-1",
        "label": "(2025) Проект А",
        "workspace": Path(r"D:\edt\2025\a"),
        "product_id": "prod-1",
        "args": ("-Xmx8192m",),
        "jvm_dir": None,
    }
    values.update(overrides)
    return EdtStartProject(**values)  # type: ignore[arg-type]


def _ids() -> "Callable[[], str]":
    counter = count(1)
    return lambda: f"id-{next(counter)}"


class TestImportCandidates:
    def test_maps_fields(self) -> None:
        [candidate] = import_candidates([_es_project()], [PRODUCT], [], _ids())
        assert candidate == ImportCandidate(
            EdtProject(
                id="id-1",
                name="(2025) Проект А",
                workspace=r"D:\edt\2025\a",
                project_dir="",
                edt_version="2025.2.6+4",
                jvm_dir="",
                vm_args="-Xmx8192m",
                group_id=None,
            ),
            version_known=True,
        )

    def test_product_args_not_copied_into_record(self) -> None:
        [candidate] = import_candidates([_es_project()], [PRODUCT], [], _ids())
        assert "nativeFormBufferedLayoutRender" not in candidate.project.vm_args

    def test_existing_workspace_excluded_by_normalized_key(self) -> None:
        existing = [EdtProject(id="x", name="есть", workspace=r"d:/EDT/2025/A/")]
        assert import_candidates([_es_project()], [PRODUCT], existing, _ids()) == []

    def test_idempotent_second_pass(self) -> None:
        first = import_candidates([_es_project()], [PRODUCT], [], _ids())
        second = import_candidates([_es_project()], [PRODUCT], [c.project for c in first], _ids())
        assert second == []

    def test_unknown_product_marked(self) -> None:
        [candidate] = import_candidates([_es_project(product_id="gone")], [PRODUCT], [], _ids())
        assert candidate.version_known is False
        assert candidate.project.edt_version == ""

    def test_project_jvm_override_copied(self) -> None:
        [candidate] = import_candidates([_es_project(jvm_dir=MINE)], [PRODUCT], [], _ids())
        assert candidate.project.jvm_dir == str(MINE)

    def test_empty_label_falls_back_to_dir_name(self) -> None:
        [candidate] = import_candidates([_es_project(label="")], [PRODUCT], [], _ids())
        assert candidate.project.name == "a"
```

Импорт `Callable` — из `collections.abc`, в шапку файла тестов.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_domain.py -q`
Expected: `ImportError` на `ImportCandidate`.

- [ ] **Step 3: Реализовать**

Добавить в `src/onecstarter/domain/edt.py` (`Callable` — в импорт из `collections.abc`):

```python
@dataclass(frozen=True)
class ImportCandidate:
    project: EdtProject
    version_known: bool  # False — productId без продукта в products.json (спека §6)


def import_candidates(
    projects: Sequence[EdtStartProject],
    products: Sequence[EdtStartProduct],
    existing: Iterable[EdtProject],
    new_id: Callable[[], str],
) -> list[ImportCandidate]:
    """Кандидат — проект EDT Start, чьего workspace у нас ещё нет (спека §6).

    `args` продукта в запись не копируются: они остаются на уровне установки
    и читаются вживую (спека §2, три уровня). Повторный вызов на результате
    предыдущего пуст — идемпотентность проверяется тестом и мутацией (§9).
    """
    known = {workspace_key(project.workspace) for project in existing}
    versions = {product.id: product.version for product in products}
    result: list[ImportCandidate] = []
    for source in projects:
        workspace = str(source.workspace)
        if workspace_key(workspace) in known:
            continue
        version = versions.get(source.product_id)
        result.append(
            ImportCandidate(
                EdtProject(
                    id=new_id(),
                    name=source.label or source.workspace.name,
                    workspace=workspace,
                    edt_version=version or "",
                    jvm_dir=str(source.jvm_dir) if source.jvm_dir is not None else "",
                    vm_args=" ".join(source.args),
                ),
                version_known=version is not None,
            )
        )
    return result
```

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/unit/test_edt_domain.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/edt.py tests/unit/test_edt_domain.py
git commit -m "feat(domain): дифф импорта из EDT Start — только новое, идемпотентно"
```

---

### Task 7: Обнаружение установок EDT и JDK на диске

**Files:**
- Create: `src/onecstarter/platform_1c/edt_discovery.py`
- Create: `tests/unit/test_edt_discovery.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.platform_1c.edt_discovery"`)

**Interfaces:**
- Consumes: `EdtInstallation`, `EDT_EXE`, `version_from_dir_name`, `parse_ini`, `parse_release`, `java_major`, `pick_jvm` (Tasks 1, 3); `EdtStartRegistry` (Task 5).
- Produces: `default_roots(env: Mapping[str, str]) -> list[Path]`; `read_jdk_version(jdk_root: Path) -> str | None`; `discover_edt(roots: Sequence[Path], registry: EdtStartRegistry | None, settings_jvm: str) -> list[EdtInstallation]` (отсортировано по версии по убыванию строк).

- [ ] **Step 1: Написать падающие тесты**

`tests/unit/test_edt_discovery.py`:

```python
"""Обнаружение EDT и JDK на диске: раскладка [Ф] спека §0, цепочка JDK §3."""

from pathlib import Path

from onecstarter.domain.edt import EdtStartProduct
from onecstarter.platform_1c.edt_discovery import default_roots, discover_edt, read_jdk_version
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry

INI_NO_VM = "-vmargs\n-Dosgi.requiredJavaVersion=17\n-Xmx4096m\n"


def _edt(root: Path, version: str, ini: str = INI_NO_VM) -> Path:
    folder = root / f"1c-edt-{version}-x86_64"
    folder.mkdir(parents=True)
    (folder / "1cedt.exe").write_bytes(b"")
    (folder / "1cedt.ini").write_text(ini, encoding="utf-8")
    return folder


def _jdk(root: Path, version: str) -> Path:
    folder = root / f"axiom-jdk-full-{version}+12-x86_64"
    (folder / "bin").mkdir(parents=True)
    (folder / "release").write_text(f'JAVA_VERSION="{version}"\n', encoding="utf-8")
    return folder


def test_default_roots() -> None:
    env = {"ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
    assert default_roots(env) == [
        Path(r"C:\Program Files\1C\1CE\components"),
        Path(r"C:\Users\u\AppData\Local\1C\1cedtstart\installations"),
    ]


def test_read_jdk_version(tmp_path: Path) -> None:
    assert read_jdk_version(_jdk(tmp_path, "17.0.16")) == "17.0.16"
    assert read_jdk_version(tmp_path / "nope") is None


class TestDiscover:
    def test_finds_installations_and_auto_jdk(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _edt(tmp_path, "2026.1.2+2")
        jdk17 = _jdk(tmp_path, "17.0.16")
        jdk25 = _jdk(tmp_path, "25.0.2")
        (tmp_path / "1c-edt-start-0.10.0+448-x86_64").mkdir()  # лаунчер — не EDT
        found = discover_edt([tmp_path], None, "")
        assert [i.version for i in found] == ["2026.1.2+2", "2025.2.6+4"]
        assert found[0].exe == tmp_path / "1c-edt-2026.1.2+2-x86_64" / "1cedt.exe"
        assert found[0].jvm_dir == jdk25 / "bin"
        assert found[0].jvm_source == "auto"
        assert found[0].required_java == 17
        assert found[0].vm_args == ""
        assert found[0].jvm_dir != jdk17 / "bin"  # старший из подходящих, не первый

    def test_products_json_enriches_jvm_and_args(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        jdk17 = _jdk(tmp_path, "17.0.16")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p",
                    version="2025.2.6+4",
                    exe=edt / "1cedt.exe",
                    jvm_dir=jdk17 / "bin",
                    args=("-Xmx8192m", "-DnativeFormBufferedLayoutRender=true"),
                ),
            ),
            projects=(),
            skipped=0,
        )
        [found] = discover_edt([tmp_path], registry, "")
        assert found.jvm_dir == jdk17 / "bin"
        assert found.jvm_source == "products.json"
        assert found.vm_args == "-Xmx8192m -DnativeFormBufferedLayoutRender=true"

    def test_product_jvm_missing_on_disk_falls_through(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        jdk17 = _jdk(tmp_path, "17.0.16")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p",
                    version="2025.2.6+4",
                    exe=edt / "1cedt.exe",
                    jvm_dir=tmp_path / "gone" / "bin",
                    args=(),
                ),
            ),
            projects=(),
            skipped=0,
        )
        [found] = discover_edt([tmp_path], registry, "")
        assert found.jvm_dir == jdk17 / "bin"
        assert found.jvm_source == "auto"

    def test_ini_vm_used_when_exists(self, tmp_path: Path) -> None:
        zulu = tmp_path / "zulu" / "bin"
        zulu.mkdir(parents=True)
        (zulu / "javaw.exe").write_bytes(b"")
        ini = f"-vm\n{zulu / 'javaw.exe'}\n-vmargs\n-Dosgi.requiredJavaVersion=17\n"
        _edt(tmp_path, "2024.2.6+7", ini)
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir == zulu
        assert found.jvm_source == "1cedt.ini"

    def test_ini_vm_missing_on_disk_ignored(self, tmp_path: Path) -> None:
        # Путь из tmp_path, не реальный Zulu: на машине заказчика Zulu 17 существует
        # (находка Task 7, спека §0 исправлена).
        ini = f"-vm\n{tmp_path / 'gone' / 'bin' / 'javaw.exe'}\n-vmargs\n"
        _edt(tmp_path, "2024.2.6+7", ini)
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir is None
        assert found.jvm_source == ""

    def test_settings_jvm(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        mine = tmp_path / "myjdk" / "bin"
        mine.mkdir(parents=True)
        [found] = discover_edt([tmp_path], None, str(mine))
        assert found.jvm_dir == mine
        assert found.jvm_source == "settings"

    def test_too_old_auto_jdk_not_picked(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _jdk(tmp_path, "11.0.2")
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir is None

    def test_same_major_newest_full_version_wins(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _jdk(tmp_path, "17.0.9")
        newest = _jdk(tmp_path, "17.0.16")
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir == newest / "bin"

    def test_product_location_outside_roots(self, tmp_path: Path) -> None:
        elsewhere = _edt(tmp_path / "elsewhere", "2025.2.6+4")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p", version="2025.2.6+4", exe=elsewhere / "1cedt.exe", jvm_dir=None, args=()
                ),
            ),
            projects=(),
            skipped=0,
        )
        roots = tmp_path / "roots"
        roots.mkdir()
        [found] = discover_edt([roots], registry, "")
        assert found.exe == elsewhere / "1cedt.exe"

    def test_same_install_from_root_and_product_not_duplicated(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p", version="2025.2.6+4", exe=edt / "1cedt.exe", jvm_dir=None, args=()
                ),
            ),
            projects=(),
            skipped=0,
        )
        assert len(discover_edt([tmp_path], registry, "")) == 1

    def test_missing_root_and_dir_without_exe(self, tmp_path: Path) -> None:
        (tmp_path / "1c-edt-2025.2.6+4-x86_64").mkdir()  # без 1cedt.exe
        assert discover_edt([tmp_path, tmp_path / "nope"], None, "") == []
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_discovery.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать**

`src/onecstarter/platform_1c/edt_discovery.py`:

```python
"""Обнаружение установок EDT и JDK на диске (спека v3, §3; факты — §0).

Единственное место, где раздел «EDT» ходит по каталогам установок. Что
именно считать установкой и как выбрать JDK — решает `domain.edt`
(`version_from_dir_name`, `pick_jvm`); здесь — только сбор существующих
кандидатов.
"""  # noqa: RUF002

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from onecstarter.domain.edt import (
    EDT_EXE,
    EdtInstallation,
    java_major,
    parse_ini,
    parse_release,
    pick_jvm,
    version_from_dir_name,
)
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry

__all__ = ["default_roots", "discover_edt", "read_jdk_version"]


def default_roots(env: Mapping[str, str]) -> list[Path]:
    """Общая установка ([Ф]) и пользовательская (`productsRoot`, раскладка [?])."""
    return [
        Path(env.get("ProgramFiles", r"C:\Program Files")) / "1C" / "1CE" / "components",
        Path(env.get("LOCALAPPDATA", ".")) / "1C" / "1cedtstart" / "installations",
    ]


def read_jdk_version(jdk_root: Path) -> str | None:
    try:
        return parse_release((jdk_root / "release").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def _children(root: Path) -> list[Path]:
    try:
        return [child for child in root.iterdir() if child.is_dir()]
    except OSError:
        return []


def _auto_jdks(roots: Sequence[Path]) -> list[tuple[str, Path]]:
    """Пары «JAVA_VERSION из release, каталог bin» — выбор делает `pick_jvm`."""
    found: list[tuple[str, Path]] = []
    for root in roots:
        for child in _children(root):
            version = read_jdk_version(child)
            if version and java_major(version) is not None and (child / "bin").is_dir():
                found.append((version, child / "bin"))
    return found


def _existing_dir(path: Path | None) -> Path | None:
    return path if path is not None and path.is_dir() else None


def _ini_vm(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_file():
        return candidate.parent
    return candidate if candidate.is_dir() else None


def _read_ini(folder: Path) -> str:
    try:
        return (folder / "1cedt.ini").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def discover_edt(
    roots: Sequence[Path],
    registry: EdtStartRegistry | None,
    settings_jvm: str,
) -> list[EdtInstallation]:
    """Каталоги `1c-edt-<версия>-x86_64` с `1cedt.exe` в корнях и по `location` продуктов."""
    products = {
        os.path.normcase(str(product.exe)): product
        for product in (registry.products if registry is not None else ())
    }
    folders: dict[str, Path] = {}
    for root in roots:
        for child in _children(root):
            folders.setdefault(os.path.normcase(str(child / EDT_EXE)), child)
    for product in products.values():
        folders.setdefault(os.path.normcase(str(product.exe)), product.exe.parent)

    auto = _auto_jdks(roots)
    settings = _existing_dir(Path(settings_jvm)) if settings_jvm else None
    found: list[EdtInstallation] = []
    for exe_key, folder in folders.items():
        version = version_from_dir_name(folder.name)
        exe = folder / EDT_EXE
        if version is None or not exe.is_file():
            continue
        ini = parse_ini(_read_ini(folder))
        product = products.get(exe_key)
        picked = pick_jvm(
            product=_existing_dir(product.jvm_dir) if product is not None else None,
            ini=_ini_vm(ini.vm),
            settings=settings,
            auto=auto,
            required_java=ini.required_java,
        )
        found.append(
            EdtInstallation(
                version=version,
                exe=exe,
                jvm_dir=picked[0] if picked else None,
                vm_args=" ".join(product.args) if product is not None else "",
                required_java=ini.required_java,
                jvm_source=picked[1] if picked else "",
            )
        )
    return sorted(found, key=lambda item: item.version, reverse=True)
```

- [ ] **Step 4: Сторож инварианта 1**

В `CORE` после `"onecstarter.platform_1c.edtstart_registry",`:

```python
    "onecstarter.platform_1c.edt_discovery",
```

- [ ] **Step 5: Прогнать**

Run: `uv run pytest tests/unit/test_edt_discovery.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/platform_1c/edt_discovery.py tests/unit/test_edt_discovery.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(platform): обнаружение установок EDT по двум корням и products.json, подбор JDK"
```

---

### Task 8: Поиск редакторов VS Code и Antigravity

**Files:**
- Create: `src/onecstarter/platform_1c/editors.py`
- Create: `tests/unit/test_editors.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.platform_1c.editors"`)

**Interfaces:**
- Consumes: `EditorResolution`, `resolve_editor` (Task 4).
- Produces: `EditorKind(Enum)` с `VSCODE = "vscode"`, `ANTIGRAVITY = "antigravity"`; `EDITOR_LABELS: dict[EditorKind, str]` (`"VS Code"`, `"Antigravity"`); `known_locations(kind: EditorKind, env: Mapping[str, str]) -> list[Path]`; `find_editor(kind: EditorKind, setting: str, env: Mapping[str, str], *, which: Callable[[str], str | None] = shutil.which, is_file: Callable[[Path], bool] = Path.is_file) -> EditorResolution`.

- [ ] **Step 1: Написать падающие тесты**

`tests/unit/test_editors.py`:

```python
"""Поиск редакторов: известные пути [Ф] спека §0, приоритет — спека §5."""

from pathlib import Path

from onecstarter.domain.edt import EDITOR_MISSING_NOTE
from onecstarter.platform_1c.editors import (
    EDITOR_LABELS,
    EditorKind,
    find_editor,
    known_locations,
)

ENV = {"LOCALAPPDATA": r"C:\Users\u\AppData\Local", "ProgramFiles": r"C:\Program Files"}
CODE_USER = Path(r"C:\Users\u\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd")
CODE_SYSTEM = Path(r"C:\Program Files\Microsoft VS Code\bin\code.cmd")
ANTI = Path(r"C:\Users\u\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd")


def test_labels() -> None:
    assert EDITOR_LABELS == {EditorKind.VSCODE: "VS Code", EditorKind.ANTIGRAVITY: "Antigravity"}


def test_known_locations() -> None:
    assert known_locations(EditorKind.VSCODE, ENV) == [CODE_USER, CODE_SYSTEM]
    assert known_locations(EditorKind.ANTIGRAVITY, ENV) == [ANTI]


def _which(hits: dict[str, str]):  # type: ignore[no-untyped-def]
    return lambda name: hits.get(name)


def test_path_hit_wins_over_known() -> None:
    result = find_editor(
        EditorKind.VSCODE,
        "",
        ENV,
        which=_which({"code.cmd": r"D:\portable\code.cmd"}),
        is_file=lambda p: True,
    )
    assert result.path == Path(r"D:\portable\code.cmd")
    assert result.source == "PATH"


def test_known_fallback_only_existing() -> None:
    result = find_editor(
        EditorKind.VSCODE, "", ENV, which=_which({}), is_file=lambda p: p == CODE_SYSTEM
    )
    assert result.path == CODE_SYSTEM
    assert result.source == "known"


def test_antigravity_not_in_path_found_by_known_dir() -> None:
    result = find_editor(
        EditorKind.ANTIGRAVITY, "", ENV, which=_which({}), is_file=lambda p: p == ANTI
    )
    assert result.path == ANTI


def test_setting_missing_reports_note() -> None:
    result = find_editor(
        EditorKind.VSCODE, r"D:\nope\code.cmd", ENV, which=_which({}), is_file=lambda p: False
    )
    assert result.path is None
    assert "не существует" in result.note


def test_nothing_found() -> None:
    result = find_editor(EditorKind.VSCODE, "", ENV, which=_which({}), is_file=lambda p: False)
    assert result.path is None
    assert result.note == EDITOR_MISSING_NOTE
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_editors.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать**

`src/onecstarter/platform_1c/editors.py`:

```python
"""Поиск внешних редакторов (спека v3, §5): настройка → PATH → известные каталоги.

Известные каталоги — [Ф] спека §0 для пользовательской установки VS Code
и Antigravity; системная установка VS Code — [?]. Приоритет решает
`domain.edt.resolve_editor`; здесь — только сбор существующих кандидатов.
"""  # noqa: RUF002

import shutil
from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path

from onecstarter.domain.edt import EditorResolution, resolve_editor

__all__ = ["EDITOR_LABELS", "EditorKind", "find_editor", "known_locations"]


class EditorKind(Enum):
    VSCODE = "vscode"
    ANTIGRAVITY = "antigravity"


EDITOR_LABELS: dict[EditorKind, str] = {
    EditorKind.VSCODE: "VS Code",
    EditorKind.ANTIGRAVITY: "Antigravity",
}

_PATH_NAMES: dict[EditorKind, tuple[str, ...]] = {
    EditorKind.VSCODE: ("code.cmd", "code"),
    EditorKind.ANTIGRAVITY: ("antigravity-ide.cmd", "antigravity-ide"),
}


def known_locations(kind: EditorKind, env: Mapping[str, str]) -> list[Path]:
    local = Path(env.get("LOCALAPPDATA", ".")) / "Programs"
    if kind is EditorKind.VSCODE:
        program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
        return [
            local / "Microsoft VS Code" / "bin" / "code.cmd",
            program_files / "Microsoft VS Code" / "bin" / "code.cmd",
        ]
    return [local / "Antigravity IDE" / "bin" / "antigravity-ide.cmd"]


def find_editor(
    kind: EditorKind,
    setting: str,
    env: Mapping[str, str],
    *,
    which: Callable[[str], str | None] = shutil.which,
    is_file: Callable[[Path], bool] = Path.is_file,
) -> EditorResolution:
    in_path: Path | None = None
    for name in _PATH_NAMES[kind]:
        hit = which(name)
        if hit:
            in_path = Path(hit)
            break
    known = [path for path in known_locations(kind, env) if is_file(path)]
    return resolve_editor(setting, bool(setting) and is_file(Path(setting)), in_path, known)
```

- [ ] **Step 4: Сторож инварианта 1**

В `CORE` после `"onecstarter.platform_1c.edt_discovery",`:

```python
    "onecstarter.platform_1c.editors",
```

- [ ] **Step 5: Прогнать**

Run: `uv run pytest tests/unit/test_editors.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/platform_1c/editors.py tests/unit/test_editors.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(platform): автопоиск VS Code и Antigravity с переопределением из настроек"
```

---

### Task 9: Активация окна запущенного EDT (Win32)

**Files:**
- Create: `src/onecstarter/platform_1c/window_activate.py`
- Create: `tests/unit/test_window_activate.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.platform_1c.window_activate"`)

**Interfaces:**
- Consumes: ничего.
- Produces: `WindowInfo(hwnd: int, pid: int, visible: bool, title: str, owner: int)`; `pick_window(windows: Sequence[WindowInfo], pid: int) -> int | None` (чистая); `enumerate_windows() -> list[WindowInfo]` (ctypes); `activate_window(pid: int, *, windows: Callable[[], list[WindowInfo]] = enumerate_windows, bring: Callable[[int], bool] = bring_to_front) -> bool`; `bring_to_front(hwnd: int) -> bool` (ctypes: `ShowWindow(SW_RESTORE)` если свёрнуто, затем `SetForegroundWindow`).

- [ ] **Step 1: Написать падающие тесты**

`tests/unit/test_window_activate.py`:

```python
"""Активация окна по PID: выбор окна — чистая функция; Win32-часть — эксперимент 2 (спека §10)."""

from onecstarter.platform_1c.window_activate import WindowInfo, activate_window, pick_window

MAIN = WindowInfo(hwnd=10, pid=42, visible=True, title="intertop — 1C:EDT", owner=0)
SPLASH = WindowInfo(hwnd=11, pid=42, visible=True, title="", owner=0)
TOOLTIP = WindowInfo(hwnd=12, pid=42, visible=True, title="tip", owner=10)
HIDDEN = WindowInfo(hwnd=13, pid=42, visible=False, title="hidden", owner=0)
OTHER = WindowInfo(hwnd=20, pid=7, visible=True, title="other", owner=0)


class TestPickWindow:
    def test_visible_titled_top_level_of_pid(self) -> None:
        assert pick_window([OTHER, SPLASH, TOOLTIP, HIDDEN, MAIN], 42) == 10

    def test_splash_without_title_not_picked(self) -> None:
        assert pick_window([SPLASH], 42) is None

    def test_owned_window_not_picked(self) -> None:
        assert pick_window([TOOLTIP], 42) is None

    def test_other_pid_not_picked(self) -> None:
        assert pick_window([OTHER], 42) is None

    def test_empty(self) -> None:
        assert pick_window([], 42) is None


class TestActivateWindow:
    def test_brings_picked_window(self) -> None:
        brought: list[int] = []

        def bring(hwnd: int) -> bool:
            brought.append(hwnd)
            return True

        assert activate_window(42, windows=lambda: [SPLASH, MAIN], bring=bring) is True
        assert brought == [10]

    def test_no_window_is_false_without_bring(self) -> None:
        brought: list[int] = []

        def bring(hwnd: int) -> bool:
            brought.append(hwnd)
            return True

        assert activate_window(42, windows=lambda: [SPLASH], bring=bring) is False
        assert brought == []

    def test_bring_failure_is_false(self) -> None:
        assert activate_window(42, windows=lambda: [MAIN], bring=lambda h: False) is False
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_window_activate.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать**

`src/onecstarter/platform_1c/window_activate.py`:

```python
"""Окно процесса на передний план (спека v3, §4) — единственный Win32-модуль вехи.

Окно EDT принадлежит самому `1cedt.exe` ([Ф] спека §0: JVM грузится в процесс
лаунчера). Выбор окна среди перечисленных — чистая функция `pick_window`:
видимое, верхнего уровня (без владельца), с непустым заголовком — splash без
заголовка не подходит. `SetForegroundWindow` разрешён процессу, у которого
сейчас фокус ввода, — у нас, пользователь только что кликнул ([?] спека §0,
эксперимент 2). Не нашлось — `False`, вызывающий молчит: ложное «не запущен»
хуже отсутствия реакции.
"""  # noqa: RUF002

import ctypes
from collections.abc import Callable, Sequence
from ctypes import wintypes
from dataclasses import dataclass

__all__ = ["WindowInfo", "activate_window", "bring_to_front", "enumerate_windows", "pick_window"]

_SW_RESTORE = 9
_GW_OWNER = 4

# Один WinDLL на модуль, argtypes/restype у каждой функции — та же гигиена
# ctypes, что в `platform_1c/job.py` (долг T-10). Без argtypes целый `hwnd`
# уходил бы 32-битным `long` (LLP64), без restype HWND возвращался бы `c_int`.
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.EnumWindows.restype = wintypes.BOOL
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.IsIconic.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    visible: bool
    title: str
    owner: int  # 0 — окно верхнего уровня


def pick_window(windows: Sequence[WindowInfo], pid: int) -> int | None:
    for window in windows:
        if window.pid == pid and window.visible and window.owner == 0 and window.title:
            return window.hwnd
    return None


def enumerate_windows() -> list[WindowInfo]:
    found: list[WindowInfo] = []

    def visit(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = _user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        owner = _user32.GetWindow(hwnd, _GW_OWNER)
        found.append(
            WindowInfo(
                hwnd=hwnd,
                pid=pid.value,
                visible=bool(_user32.IsWindowVisible(hwnd)),
                title=buffer.value,
                owner=int(owner) if owner else 0,
            )
        )
        return True

    # Ссылка на callback живёт до возврата EnumWindows — локальная переменная,
    # не временный объект внутри вызова.
    callback = _WNDENUMPROC(visit)
    _user32.EnumWindows(callback, 0)
    return found


def bring_to_front(hwnd: int) -> bool:
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    return bool(_user32.SetForegroundWindow(hwnd))


def activate_window(
    pid: int,
    *,
    windows: Callable[[], list[WindowInfo]] = enumerate_windows,
    bring: Callable[[int], bool] = bring_to_front,
) -> bool:
    hwnd = pick_window(windows(), pid)
    if hwnd is None:
        return False
    return bring(hwnd)
```

- [ ] **Step 4: Сторож инварианта 1**

В `CORE` после `"onecstarter.platform_1c.editors",`:

```python
    "onecstarter.platform_1c.window_activate",
```

- [ ] **Step 5: Прогнать**

Run: `uv run pytest tests/unit/test_window_activate.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/platform_1c/window_activate.py tests/unit/test_window_activate.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(platform): активация окна процесса по PID — выбор окна чистой функцией"
```

---

### Task 10: Хранилище `edt.json` и ошибки раздела

**Files:**
- Modify: `src/onecstarter/services/errors.py`
- Create: `src/onecstarter/services/edt_store.py`
- Create: `tests/unit/test_edt_store.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.services.edt_store"`)

**Interfaces:**
- Consumes: `EdtGroup`, `EdtProject` (Task 1); `config.atomic.atomic_write`.
- Produces: `EdtError(ServicesError)`, `EdtUnavailableError(EdtError)`, `EdtLaunchError(EdtError)`; `EdtRegistry(groups: tuple[EdtGroup, ...], projects: tuple[EdtProject, ...])`; `load_registry(path: Path) -> EdtRegistry`; `save_registry(path: Path, registry: EdtRegistry) -> None`; `SCHEMA_VERSION = 1`.

- [ ] **Step 1: Написать падающие тесты**

`tests/unit/test_edt_store.py`:

```python
"""Хранилище edt.json: калька политики `.bad` из `test_server_store.py` (спека §2)."""

import json
from pathlib import Path

import pytest

from onecstarter.domain.edt import EdtGroup, EdtProject
from onecstarter.services.edt_store import (
    SCHEMA_VERSION,
    EdtRegistry,
    load_registry,
    save_registry,
)
from onecstarter.services.errors import EdtUnavailableError

GROUP = EdtGroup(id="g1", name="2025", parent_id=None)
CHILD = EdtGroup(id="g2", name="Розница", parent_id="g1")
PROJECT = EdtProject(
    id="p1",
    name="Розница (2025)",
    workspace=r"D:\edt\2025\retail",
    project_dir=r"D:\edt\2025\retail\retail",
    edt_version="2025.2.6+4",
    jvm_dir="",
    vm_args="-Xmx8192m",
    group_id="g2",
)
REGISTRY = EdtRegistry(groups=(GROUP, CHILD), projects=(PROJECT,))


class TestRoundTrip:
    def test_survives_save_load(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        save_registry(path, REGISTRY)
        assert load_registry(path) == REGISTRY

    def test_order_is_array_order(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        second = EdtProject(id="p2", name="Б", workspace=r"D:\b")
        first = EdtProject(id="p1", name="А", workspace=r"D:\a")
        save_registry(path, EdtRegistry(groups=(), projects=(second, first)))
        assert [p.id for p in load_registry(path).projects] == ["p2", "p1"]

    def test_payload_shape(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        save_registry(path, REGISTRY)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema"] == SCHEMA_VERSION
        assert payload["groups"][0] == {"id": "g1", "name": "2025", "parent_id": None}
        assert payload["projects"][0]["workspace"] == r"D:\edt\2025\retail"
        assert payload["projects"][0]["group_id"] == "g2"

    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert load_registry(tmp_path / "edt.json") == EdtRegistry(groups=(), projects=())

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        path = tmp_path / "OneCStarter" / "edt.json"
        save_registry(path, REGISTRY)
        assert path.exists()


class TestTolerance:
    def test_missing_optional_fields_default(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        path.write_text(
            json.dumps(
                {
                    "schema": SCHEMA_VERSION,
                    "groups": [],
                    "projects": [{"id": "p", "name": "n", "workspace": r"D:\w"}],
                }
            ),
            encoding="utf-8",
        )
        [project] = load_registry(path).projects
        assert project == EdtProject(id="p", name="n", workspace=r"D:\w")

    def test_unknown_keys_are_dropped_on_save(self, tmp_path: Path) -> None:
        path = tmp_path / "edt.json"
        path.write_text(
            json.dumps(
                {
                    "schema": SCHEMA_VERSION,
                    "groups": [],
                    "projects": [{"id": "p", "name": "n", "workspace": r"D:\w", "future": 1}],
                }
            ),
            encoding="utf-8",
        )
        save_registry(path, load_registry(path))
        assert "future" not in path.read_text(encoding="utf-8")


class TestBadFile:
    @pytest.mark.parametrize(
        "text",
        ["{", "[]", '{"schema": 99, "groups": [], "projects": []}', '{"schema": 1, "projects": {}}'],
    )
    def test_corrupt_moves_aside_and_starts_empty(self, tmp_path: Path, text: str) -> None:
        path = tmp_path / "edt.json"
        path.write_text(text, encoding="utf-8")
        assert load_registry(path) == EdtRegistry(groups=(), projects=())
        assert not path.exists()
        assert (tmp_path / "edt.json.bad").read_text(encoding="utf-8") == text

    def test_unreadable_file_raises_not_empty(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: недоступный файл — ошибка, не пустой список и не `.bad`."""
        directory = tmp_path / "edt.json"
        directory.mkdir()  # каталог на месте файла: IsADirectoryError=OSError
        with pytest.raises(EdtUnavailableError):
            load_registry(directory)
        assert directory.exists()
        assert not (tmp_path / "edt.json.bad").exists()

    def test_cannot_move_aside_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "edt.json"
        path.write_text("{", encoding="utf-8")

        def refuse(self: Path, target: Path) -> Path:
            raise OSError("занят")

        monkeypatch.setattr(Path, "replace", refuse)
        with pytest.raises(EdtUnavailableError):
            load_registry(path)
        assert path.exists()
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_store.py -q`
Expected: `ImportError` на `EdtUnavailableError` либо `ModuleNotFoundError`.

- [ ] **Step 3: Добавить ошибки**

В конец `src/onecstarter/services/errors.py`:

```python
class EdtError(ServicesError):
    """Отказ раздела «EDT» (спека v3, §8)."""


class EdtUnavailableError(EdtError):
    """`edt.json` повреждён и не переносится в `.bad` — раздел недоступен."""


class EdtLaunchError(EdtError):
    """Запуск EDT или редактора отказал до или при порождении процесса."""
```

- [ ] **Step 4: Реализовать хранилище**

`src/onecstarter/services/edt_store.py`:

```python
"""Хранилище раздела «EDT» — `%APPDATA%\\OneCStarter\\edt.json` (спека v3, §2).

Файл наш: формат не согласуется ни с кем, неизвестные ключи не сохраняются.
Политика повреждённого файла — та же, что у `server_store.py`: перенос в `.bad`
с пустым списком дальше; не сумели перенести — `EdtUnavailableError`, потому что
первое же сохранение затёрло бы то, что пользователь мог бы достать из файла.
"""  # noqa: RUF002

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.edt import EdtGroup, EdtProject
from onecstarter.services.errors import EdtUnavailableError

__all__ = ["SCHEMA_VERSION", "EdtRegistry", "load_registry", "save_registry"]

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EdtRegistry:
    groups: tuple[EdtGroup, ...]
    projects: tuple[EdtProject, ...]


def load_registry(path: Path) -> EdtRegistry:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return EdtRegistry((), ())
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        # Файл есть, но недоступен: блокировка, права, отвалившийся диск. Это
        # не порча содержимого — в `.bad` его не уносим и пустым не подменяем:
        # следующее сохранение затёрло бы записи пользователя (как в server_store).
        raise EdtUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
        groups = payload.get("groups", [])
        projects = payload.get("projects", [])
        if not isinstance(groups, list) or not isinstance(projects, list):
            raise ValueError("groups/projects не списки")
        return EdtRegistry(
            tuple(_decode_group(entry) for entry in groups),
            tuple(_decode_project(entry) for entry in projects),
        )
    except (ValueError, KeyError, TypeError):
        return _move_aside(path)


def save_registry(path: Path, registry: EdtRegistry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "groups": [_encode_group(group) for group in registry.groups],
        "projects": [_encode_project(project) for project in registry.projects],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write(path, text.encode("utf-8"))


def _move_aside(path: Path) -> EdtRegistry:
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError as error:
        raise EdtUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"  # noqa: RUF001
        ) from error
    return EdtRegistry((), ())


def _encode_group(group: EdtGroup) -> dict[str, Any]:
    return {"id": group.id, "name": group.name, "parent_id": group.parent_id}


def _decode_group(value: Any) -> EdtGroup:
    if not isinstance(value, dict):
        raise ValueError("группа не объект")
    parent = value.get("parent_id")
    return EdtGroup(
        id=str(value["id"]),
        name=str(value["name"]),
        parent_id=str(parent) if isinstance(parent, str) else None,
    )


def _encode_project(project: EdtProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "workspace": project.workspace,
        "project_dir": project.project_dir,
        "edt_version": project.edt_version,
        "jvm_dir": project.jvm_dir,
        "vm_args": project.vm_args,
        "group_id": project.group_id,
    }


def _decode_project(value: Any) -> EdtProject:
    if not isinstance(value, dict):
        raise ValueError("запись не объект")
    group = value.get("group_id")
    return EdtProject(
        id=str(value["id"]),
        name=str(value["name"]),
        workspace=str(value["workspace"]),
        project_dir=str(value.get("project_dir", "")),
        edt_version=str(value.get("edt_version", "")),
        jvm_dir=str(value.get("jvm_dir", "")),
        vm_args=str(value.get("vm_args", "")),
        group_id=str(group) if isinstance(group, str) else None,
    )
```

- [ ] **Step 5: Сторож инварианта 1**

В `CORE` после `"onecstarter.services.servers",`:

```python
    "onecstarter.services.edt_store",
```

- [ ] **Step 6: Прогнать, затем мутационная проверка `.bad`**

Run: `uv run pytest tests/unit/test_edt_store.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

Мутация (CLAUDE.md, «Процесс»): в `_move_aside` временно заменить тело на
`return EdtRegistry((), ())` (без `replace`). Run: `uv run pytest tests/unit/test_edt_store.py -q`.
Expected: `test_corrupt_moves_aside_and_starts_empty` падает на `assert not path.exists()`,
`test_cannot_move_aside_raises` — на отсутствии исключения. Откатить мутацию, прогнать
снова — зелёное. Результат записать в сообщение коммита.

- [ ] **Step 7: Commit**

```bash
git add src/onecstarter/services/errors.py src/onecstarter/services/edt_store.py tests/unit/test_edt_store.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(services): хранилище edt.json с политикой .bad (мутация: 2 теста падают без переноса)"
```

---

### Task 11: Настройки — группа «EDT»

**Files:**
- Modify: `src/onecstarter/services/settings.py`
- Modify: `tests/unit/test_settings.py`

**Interfaces:**
- Consumes: `LANGUAGES` (Task 2).
- Produces: поля `Settings.edt_jvm_dir: str = ""`, `Settings.edt_default_max_heap_mb: int = 8192`, `Settings.edt_default_language: str = ""`, `Settings.editor_vscode: str = ""`, `Settings.editor_antigravity: str = ""`; константы `DEFAULT_EDT_HEAP_MB = 8192`, `EDT_HEAP_MIN = 256`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/unit/test_settings.py` — в `test_schema_is_written` расширить ожидаемый словарь пятью ключами:

```python
        "edt_jvm_dir": "",
        "edt_default_max_heap_mb": 8192,
        "edt_default_language": "",
        "editor_vscode": "",
        "editor_antigravity": "",
```

и добавить в конец файла:

```python
def test_edt_fields_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings(
        edt_jvm_dir=r"D:\jdk\bin",
        edt_default_max_heap_mb=4096,
        edt_default_language="ru",
        editor_vscode=r"D:\code\code.cmd",
        editor_antigravity=r"D:\ag\antigravity-ide.cmd",
    )
    save_settings(path, settings)
    assert load_settings(path) == settings


@pytest.mark.parametrize(
    ("value", "expected"),
    [(4096, 4096), (True, 8192), ("8192", 8192), (0, 8192), (-5, 8192), (256, 256), (255, 8192)],
)
def test_edt_heap_tolerance(tmp_path: Path, value: object, expected: int) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema": SCHEMA_VERSION, "edt_default_max_heap_mb": value}), encoding="utf-8"
    )
    assert load_settings(path).edt_default_max_heap_mb == expected


@pytest.mark.parametrize(("value", "expected"), [("ru", "ru"), ("en", "en"), ("", ""), ("xx", ""), (5, "")])
def test_edt_language_tolerance(tmp_path: Path, value: object, expected: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema": SCHEMA_VERSION, "edt_default_language": value}), encoding="utf-8"
    )
    assert load_settings(path).edt_default_language == expected


def test_edt_path_fields_non_string_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema": SCHEMA_VERSION, "edt_jvm_dir": 1, "editor_vscode": None}),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded.edt_jvm_dir == ""
    assert loaded.editor_vscode == ""
```

(`json`, `pytest`, `SCHEMA_VERSION` в файле уже импортированы — проверить шапку.)

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_settings.py -q`
Expected: `TypeError: Settings.__init__() got an unexpected keyword argument 'edt_jvm_dir'` и падение `test_schema_is_written`.

- [ ] **Step 3: Реализовать**

В `src/onecstarter/services/settings.py`:

Константы рядом с `DEFAULT_RECENT_LIMIT`:

```python
DEFAULT_EDT_HEAP_MB = 8192  # умолчание EDT Start (скриншот заказчика, спека §2)
EDT_HEAP_MIN = 256
```

Импорт: `from onecstarter.domain.edt import LANGUAGES`.

Поля в конец `Settings` (после `web_launch`):

```python
    # Спека v3, §2 — уровень «программа» настроек запуска EDT: умолчания для
    # НОВЫХ записей и JDK на случай, когда автоподбор промахнулся. Пути не
    # валидируются здесь — несуществующий каталог не порча файла настроек.
    edt_jvm_dir: str = ""
    edt_default_max_heap_mb: int = DEFAULT_EDT_HEAP_MB
    edt_default_language: str = ""
    editor_vscode: str = ""
    editor_antigravity: str = ""
```

В `load_settings` — в конструктор `Settings(...)`:

```python
        edt_jvm_dir=_text_of(payload.get("edt_jvm_dir")),
        edt_default_max_heap_mb=_heap_of(payload.get("edt_default_max_heap_mb")),
        edt_default_language=_language_of(payload.get("edt_default_language")),
        editor_vscode=_text_of(payload.get("editor_vscode")),
        editor_antigravity=_text_of(payload.get("editor_antigravity")),
```

В `save_settings` — в `payload`:

```python
        "edt_jvm_dir": settings.edt_jvm_dir,
        "edt_default_max_heap_mb": settings.edt_default_max_heap_mb,
        "edt_default_language": settings.edt_default_language,
        "editor_vscode": settings.editor_vscode,
        "editor_antigravity": settings.editor_antigravity,
```

Декодеры (рядом с `_servers_root_of`):

```python
def _text_of(value: Any) -> str:
    """Не-строка — не порча файла: пустая строка, «не задано»."""
    return value if isinstance(value, str) else ""


def _heap_of(value: Any) -> int:
    """`bool` отсекается первым (подкласс `int`); меньше минимума — дефолт."""
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_EDT_HEAP_MB
    return value if value >= EDT_HEAP_MIN else DEFAULT_EDT_HEAP_MB


def _language_of(value: Any) -> str:
    """Незнакомый код — «по умолчанию», не порча."""
    codes = {code for code, _label in LANGUAGES}
    return value if isinstance(value, str) and value in codes else ""
```

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/unit/test_settings.py tests/unit/test_no_qt_in_core.py tests/ui/test_settings_view.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное (тесты вьюхи настроек проверяют полный состав ключей — если один из них перечисляет поля, дополнить его теми же пятью).

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/services/settings.py tests/unit/test_settings.py
git commit -m "feat(services): пять полей настроек группы EDT — JDK, память, язык, редакторы"
```

---

### Task 12: Координатор `EdtWorkspace` — записи, группы, порядок

**Files:**
- Create: `src/onecstarter/services/edt.py`
- Create: `tests/unit/test_edt_workspace.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.services.edt"`)

**Interfaces:**
- Consumes: `EdtGroup`, `EdtProject`, `EdtInstallation`, `EditorResolution` (Tasks 1, 4); `EdtRegistry`, `load_registry`, `save_registry` (Task 10); `EditorKind` (Task 8); `EdtStartRegistry` (Task 5); `LaunchCommand`; `InvalidRequestError`, `UnknownItemError` (существуют в `services/errors.py`).
- Produces: класс `EdtWorkspace` с конструктором

```python
EdtWorkspace(
    path: Path,
    *,
    discover: Callable[[], list[EdtInstallation]],
    edtstart: Callable[[], EdtStartRegistry | None],
    editors: Callable[[EditorKind], EditorResolution],
    spawn: Callable[[LaunchCommand], int] = process.spawn,
    activate: Callable[[int], bool] = window_activate.activate_window,
    open_file: Callable[[str], None] = os.startfile,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
)
```

и методами этой задачи: `groups() -> list[EdtGroup]`, `projects() -> list[EdtProject]`, `project(project_id) -> EdtProject` (`UnknownItemError`), `add_project(project: EdtProject) -> EdtProject` (id выдаётся, если пуст), `update_project(project: EdtProject) -> None`, `remove_project(project_id) -> None`, `add_group(name: str, parent_id: str | None) -> EdtGroup`, `rename_group(group_id, name) -> None`, `remove_group(group_id) -> None` (содержимое — к родителю), `move_project(project_id, group_id: str | None, position: int) -> None`, `move_group(group_id, parent_id: str | None, position: int) -> None` (цикл — `InvalidRequestError`), `children(group_id: str | None) -> tuple[list[EdtGroup], list[EdtProject]]`.

- [ ] **Step 1: Написать падающие тесты**

`tests/unit/test_edt_workspace.py`:

```python
"""Координатор раздела EDT: записи, группы, порядок (спека §2), сохранение после каждой правки."""

from itertools import count
from pathlib import Path

import pytest

from onecstarter.domain.edt import EdtProject
from onecstarter.services.edt import EdtWorkspace
from onecstarter.services.edt_store import load_registry
from onecstarter.services.errors import InvalidRequestError, UnknownItemError


def _workspace(tmp_path: Path) -> EdtWorkspace:
    ids = count(1)
    return EdtWorkspace(
        tmp_path / "edt.json",
        discover=lambda: [],
        edtstart=lambda: None,
        editors=lambda kind: None,  # type: ignore[arg-type, return-value]
        spawn=lambda command: 1,
        activate=lambda pid: True,
        open_file=lambda path: None,
        new_id=lambda: f"id-{next(ids)}",
    )


def _project(name: str, **overrides: object) -> EdtProject:
    values: dict[str, object] = {"id": "", "name": name, "workspace": rf"D:\edt\{name}"}
    values.update(overrides)
    return EdtProject(**values)  # type: ignore[arg-type]


class TestProjects:
    def test_add_assigns_id_and_saves(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        added = ws.add_project(_project("a"))
        assert added.id == "id-1"
        assert [p.id for p in load_registry(tmp_path / "edt.json").projects] == ["id-1"]

    def test_add_rejects_empty_name_or_workspace(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        with pytest.raises(InvalidRequestError):
            ws.add_project(_project("", workspace=r"D:\x"))
        with pytest.raises(InvalidRequestError):
            ws.add_project(_project("a", workspace="  "))

    def test_add_rejects_relative_workspace(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidRequestError):
            _workspace(tmp_path).add_project(_project("a", workspace=r"edt\a"))

    def test_update_and_remove(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        added = ws.add_project(_project("a"))
        ws.update_project(EdtProject(id=added.id, name="b", workspace=added.workspace))
        assert ws.project(added.id).name == "b"
        ws.remove_project(added.id)
        assert ws.projects() == []
        with pytest.raises(UnknownItemError):
            ws.project(added.id)

    def test_update_unknown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnknownItemError):
            _workspace(tmp_path).update_project(_project("a", id="ghost"))

    def test_update_with_unknown_group_raises_and_keeps_record(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        added = ws.add_project(_project("a"))
        with pytest.raises(UnknownItemError):
            ws.update_project(EdtProject(id=added.id, name="a", workspace=added.workspace, group_id="ghost"))
        assert ws.project(added.id).group_id is None
        assert [p.id for p in ws.children(None)[1]] == [added.id]


class TestGroups:
    def test_add_rename_remove_promotes_children(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("2025", None)
        child = ws.add_group("Розница", root.id)
        project = ws.add_project(_project("a", group_id=child.id))
        ws.rename_group(child.id, "Опт")
        assert [g.name for g in ws.groups()] == ["2025", "Опт"]
        ws.remove_group(child.id)
        assert ws.project(project.id).group_id == root.id
        assert [g.id for g in ws.groups()] == [root.id]

    def test_remove_root_group_promotes_to_root(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("2025", None)
        sub = ws.add_group("x", root.id)
        ws.remove_group(root.id)
        assert ws.groups()[0].id == sub.id
        assert ws.groups()[0].parent_id is None

    def test_add_rejects_empty_name_and_unknown_parent(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        with pytest.raises(InvalidRequestError):
            ws.add_group("  ", None)
        with pytest.raises(UnknownItemError):
            ws.add_group("x", "ghost")

    def test_children_lists_direct_only_in_order(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("2025", None)
        ws.add_group("inner", root.id)
        b = ws.add_project(_project("b", group_id=root.id))
        a = ws.add_project(_project("a", group_id=root.id))
        top = ws.add_project(_project("top"))
        groups, projects = ws.children(root.id)
        assert [g.name for g in groups] == ["inner"]
        assert [p.id for p in projects] == [b.id, a.id]
        assert [p.id for p in ws.children(None)[1]] == [top.id]


class TestMove:
    def test_move_project_between_groups_and_positions(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        g = ws.add_group("g", None)
        a = ws.add_project(_project("a"))
        b = ws.add_project(_project("b"))
        c = ws.add_project(_project("c"))
        ws.move_project(c.id, None, 0)
        assert [p.id for p in ws.children(None)[1]] == [c.id, a.id, b.id]
        ws.move_project(a.id, g.id, 0)
        assert [p.id for p in ws.children(g.id)[1]] == [a.id]
        assert [p.id for p in ws.children(None)[1]] == [c.id, b.id]
        ws.move_project(b.id, None, 0)
        assert [p.id for p in ws.children(None)[1]] == [b.id, c.id]

    def test_move_project_position_past_end_appends(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        a = ws.add_project(_project("a"))
        b = ws.add_project(_project("b"))
        ws.move_project(a.id, None, 99)
        assert [p.id for p in ws.children(None)[1]] == [b.id, a.id]

    def test_move_group_into_own_descendant_rejected(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = ws.add_group("root", None)
        child = ws.add_group("child", root.id)
        with pytest.raises(InvalidRequestError):
            ws.move_group(root.id, child.id, 0)
        with pytest.raises(InvalidRequestError):
            ws.move_group(root.id, root.id, 0)

    def test_move_group_reorders_siblings(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        a = ws.add_group("a", None)
        b = ws.add_group("b", None)
        ws.move_group(b.id, None, 0)
        assert [g.id for g in ws.children(None)[0]] == [b.id, a.id]

    def test_moves_are_persisted(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        a = ws.add_project(_project("a"))
        b = ws.add_project(_project("b"))
        ws.move_project(b.id, None, 0)
        assert [p.id for p in load_registry(tmp_path / "edt.json").projects] == [b.id, a.id]
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_workspace.py -q`
Expected: `ModuleNotFoundError: onecstarter.services.edt`.

- [ ] **Step 3: Реализовать**

`src/onecstarter/services/edt.py`:

```python
"""Координатор раздела «EDT» (спека v3): реестр записей и групп, установки, запуск.

Калька `services/servers.py::ServersWorkspace`: всё, что трогает процессы,
диск и Win32, приходит аргументами конструктора и подменяется тестами;
каждая правка списка сразу пишется в `edt.json` (инвариант 4 — через
`edt_store.save_registry`).

Порядок записей и групп — порядок в массиве (спека §2): перестановка —
удаление из одного места и вставка в другое, без арифметики `OrderInList`.
"""  # noqa: RUF002

import os
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from onecstarter.domain.edt import (
    EdtGroup,
    EdtInstallation,
    EdtProject,
    EditorResolution,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c import process, window_activate
from onecstarter.platform_1c.editors import EditorKind
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry
from onecstarter.services.edt_store import EdtRegistry, load_registry, save_registry
from onecstarter.services.errors import InvalidRequestError, UnknownItemError

__all__ = ["EdtWorkspace"]


def _new_id() -> str:
    return uuid.uuid4().hex


class EdtWorkspace:
    def __init__(
        self,
        path: Path,
        *,
        discover: Callable[[], list[EdtInstallation]],
        edtstart: Callable[[], EdtStartRegistry | None],
        editors: Callable[[EditorKind], EditorResolution],
        spawn: Callable[[LaunchCommand], int] = process.spawn,
        activate: Callable[[int], bool] = window_activate.activate_window,
        open_file: Callable[[str], None] = os.startfile,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self._path = path
        self._discover = discover
        self._edtstart = edtstart
        self._editors = editors
        self._spawn = spawn
        self._activate = activate
        self._open_file = open_file
        self._new_id = new_id
        registry = load_registry(path)
        self._groups: list[EdtGroup] = list(registry.groups)
        self._projects: list[EdtProject] = list(registry.projects)
        self._installations: list[EdtInstallation] = []
        self._installations_ready = False

    # --- записи -----------------------------------------------------------

    def projects(self) -> list[EdtProject]:
        return list(self._projects)

    def project(self, project_id: str) -> EdtProject:
        for project in self._projects:
            if project.id == project_id:
                return project
        raise UnknownItemError(f"Запись EDT не найдена: {project_id}")

    def add_project(self, project: EdtProject) -> EdtProject:
        self._validate_project(project)
        if project.group_id is not None:
            self._group(project.group_id)
        stored = replace(project, id=project.id or self._new_id())
        self._projects.append(stored)
        self._save()
        return stored

    def update_project(self, project: EdtProject) -> None:
        self._validate_project(project)
        if project.group_id is not None:
            self._group(project.group_id)  # неизвестная группа — UnknownItemError, как в add
        index = self._project_index(project.id)
        self._projects[index] = project
        self._save()

    def remove_project(self, project_id: str) -> None:
        del self._projects[self._project_index(project_id)]
        self._save()

    # --- группы -----------------------------------------------------------

    def groups(self) -> list[EdtGroup]:
        return list(self._groups)

    def add_group(self, name: str, parent_id: str | None) -> EdtGroup:
        if not name.strip():
            raise InvalidRequestError("Имя группы пусто")
        if parent_id is not None:
            self._group(parent_id)
        group = EdtGroup(id=self._new_id(), name=name.strip(), parent_id=parent_id)
        self._groups.append(group)
        self._save()
        return group

    def rename_group(self, group_id: str, name: str) -> None:
        if not name.strip():
            raise InvalidRequestError("Имя группы пусто")
        index = self._group_index(group_id)
        self._groups[index] = EdtGroup(id=group_id, name=name.strip(), parent_id=self._groups[index].parent_id)
        self._save()

    def remove_group(self, group_id: str) -> None:
        """Содержимое уходит к родителю (спека §7): выбора нет — записей мало."""
        removed = self._group(group_id)
        self._groups = [
            EdtGroup(id=g.id, name=g.name, parent_id=removed.parent_id)
            if g.parent_id == group_id
            else g
            for g in self._groups
            if g.id != group_id
        ]
        self._projects = [
            replace(p, group_id=removed.parent_id) if p.group_id == group_id else p
            for p in self._projects
        ]
        self._save()

    def children(self, group_id: str | None) -> tuple[list[EdtGroup], list[EdtProject]]:
        return (
            [g for g in self._groups if g.parent_id == group_id],
            [p for p in self._projects if p.group_id == group_id],
        )

    # --- перестановка -----------------------------------------------------

    def move_project(self, project_id: str, group_id: str | None, position: int) -> None:
        if group_id is not None:
            self._group(group_id)
        moving = self._projects.pop(self._project_index(project_id))
        moved = replace(moving, group_id=group_id)
        self._projects.insert(self._insert_index(self._projects, group_id, position), moved)
        self._save()

    def move_group(self, group_id: str, parent_id: str | None, position: int) -> None:
        if parent_id is not None:
            self._group(parent_id)
            if parent_id == group_id or self._is_descendant(parent_id, group_id):
                raise InvalidRequestError("Группу нельзя переместить внутрь самой себя")
        moving = self._groups.pop(self._group_index(group_id))
        moved = EdtGroup(id=moving.id, name=moving.name, parent_id=parent_id)
        self._groups.insert(self._insert_index(self._groups, parent_id, position), moved)
        self._save()

    # --- внутреннее -------------------------------------------------------

    @staticmethod
    def _insert_index(
        items: Sequence[EdtGroup | EdtProject], parent: str | None, position: int
    ) -> int:
        """Индекс в общем массиве, соответствующий `position` среди соседей."""
        siblings = [
            index
            for index, item in enumerate(items)
            if (item.parent_id if isinstance(item, EdtGroup) else item.group_id) == parent
        ]
        if position < len(siblings):
            return siblings[position]
        return siblings[-1] + 1 if siblings else len(items)

    def _is_descendant(self, candidate: str, ancestor: str) -> bool:
        current: str | None = candidate
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            parent = self._group(current).parent_id
            if parent == ancestor:
                return True
            current = parent
        return False

    def _validate_project(self, project: EdtProject) -> None:
        if not project.name.strip():
            raise InvalidRequestError("Имя записи пусто")
        if not project.workspace.strip():
            raise InvalidRequestError("Путь workspace пуст")
        if not Path(project.workspace).is_absolute():  # без обращения к диску (ruff PTH117)
            raise InvalidRequestError("Путь workspace должен быть абсолютным")

    def _project_index(self, project_id: str) -> int:
        for index, project in enumerate(self._projects):
            if project.id == project_id:
                return index
        raise UnknownItemError(f"Запись EDT не найдена: {project_id}")

    def _group_index(self, group_id: str) -> int:
        for index, group in enumerate(self._groups):
            if group.id == group_id:
                return index
        raise UnknownItemError(f"Группа не найдена: {group_id}")

    def _group(self, group_id: str) -> EdtGroup:
        return self._groups[self._group_index(group_id)]

    def _save(self) -> None:
        save_registry(self._path, EdtRegistry(tuple(self._groups), tuple(self._projects)))
```

`Path.is_absolute()` — без обращения к диску; проверка существования каталога — не здесь (спека §8: отсутствующий каталог — метка, не отказ). **Правка по итогам реализации (ef66de3):** `os.path.isabs` заменён на `Path.is_absolute()` (ruff PTH117), `_insert_index` типизирован `Sequence[EdtGroup | EdtProject]` (mypy strict); `update_project` проверяет `group_id` как `add_project` — находка ревью.

- [ ] **Step 4: Сторож инварианта 1**

В `CORE` после `"onecstarter.services.edt_store",`:

```python
    "onecstarter.services.edt",
```

- [ ] **Step 5: Прогнать**

Run: `uv run pytest tests/unit/test_edt_workspace.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/services/edt.py tests/unit/test_edt_workspace.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(services): координатор EDT — записи, группы, перестановка с сохранением"
```

---

### Task 13: Координатор — установки, запуск, редакторы, статус, импорт

**Files:**
- Modify: `src/onecstarter/services/edt.py`
- Modify: `tests/unit/test_edt_workspace.py`

**Interfaces:**
- Consumes: Task 12; `build_edt_command`, `effective_jvm`, `running_workspaces`, `import_candidates`, `ImportCandidate` (Tasks 3, 4, 6); `ProcessInfo`, `ProcessScanner` (`platform_1c/process_scan.py`, существуют); `EdtLaunchError`, `EdtError` (Task 10).
- Produces:

```python
class LaunchOutcome(Enum): STARTED = "started"; ACTIVATED = "activated"; ACTIVATION_MISSED = "missed"

@dataclass(frozen=True)
class EdtScan:
    running: dict[str, int]          # id записи → pid
    present: dict[str, bool]         # id записи → каталог workspace существует

@dataclass(frozen=True)
class EdtStatus:
    running_pid: int | None
    workspace_present: bool | None   # None — ещё не проверяли
    installed: bool                  # версия записи есть среди установок
    cli_busy: bool = False           # план 2

def scan_edt(scanner: ProcessScanner, projects: Sequence[EdtProject], is_dir: Callable[[str], bool] = os.path.isdir) -> EdtScan
```

методы `EdtWorkspace`: `refresh_installations() -> list[EdtInstallation]` (зовёт `discover`), `installations() -> list[EdtInstallation]`, `installations_ready() -> bool`, `installation_for(project) -> EdtInstallation | None`, `apply_scan(scan: EdtScan) -> None`, `status(project_id) -> EdtStatus`, `running_pid(project_id) -> int | None`, `launch(project_id) -> LaunchOutcome`, `editor(kind) -> EditorResolution`, `open_in_editor(project_id, kind) -> None`, `open_folder(project_id) -> None`, `import_candidates() -> list[ImportCandidate] | None` (`None` — реестра EDT Start нет), `import_projects(candidates: Sequence[ImportCandidate]) -> int`, `edtstart_available() -> bool`, `edtstart_skipped() -> int` (записей `projects.json` без обязательных ключей; 0 без реестра).

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_edt_workspace.py`:

```python
from dataclasses import dataclass, field

from onecstarter.domain.edt import (
    EdtInstallation,
    EdtStartProduct,
    EdtStartProject,
    EditorResolution,
)
from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.editors import EditorKind
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.edt import EdtScan, LaunchOutcome, scan_edt
from onecstarter.services.errors import EdtError, EdtLaunchError

JDK = Path(r"C:\jdk\bin")
EXE_2025 = Path(r"C:\edt\1c-edt-2025.2.6+4-x86_64\1cedt.exe")
INSTALLED = [
    EdtInstallation("2025.2.6+4", EXE_2025, JDK, "-Xmx8192m -Dx=1", 17, "products.json"),
]


@dataclass
class Harness:
    workspace: EdtWorkspace
    spawned: list[LaunchCommand] = field(default_factory=list)
    activated: list[int] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)


def _harness(
    tmp_path: Path,
    *,
    installed: list[EdtInstallation] | None = None,
    edtstart: EdtStartRegistry | None = None,
    editor: EditorResolution | None = None,
    activate_result: bool = True,
    spawn_error: bool = False,
) -> Harness:
    harness = Harness(workspace=None)  # type: ignore[arg-type]
    ids = count(1)

    def spawn(command: LaunchCommand) -> int:
        if spawn_error:
            raise OSError("нет файла")
        harness.spawned.append(command)
        return 500

    def activate(pid: int) -> bool:
        harness.activated.append(pid)
        return activate_result

    harness.workspace = EdtWorkspace(
        tmp_path / "edt.json",
        discover=lambda: list(installed or []),
        edtstart=lambda: edtstart,
        editors=lambda kind: editor or EditorResolution(None, "", "Не найден — укажите путь в Настройках"),
        spawn=spawn,
        activate=activate,
        open_file=harness.opened.append,
        new_id=lambda: f"id-{next(ids)}",
    )
    return harness


def _proc(pid: int, workspace: str) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name="1cedt.exe",
        executable=EXE_2025,
        argv=(str(EXE_2025), "-data", workspace, "-vm", str(JDK)),
    )


class FakeScanner:
    def __init__(self, processes: list[ProcessInfo]) -> None:
        self._processes = processes
        self.names: list[frozenset[str]] = []

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        self.names.append(names)
        return list(self._processes)


class TestScan:
    def test_scan_edt_maps_running_and_presence(self, tmp_path: Path) -> None:
        present = tmp_path / "ws"
        present.mkdir()
        projects = [
            EdtProject(id="p1", name="a", workspace=str(present)),
            EdtProject(id="p2", name="b", workspace=str(tmp_path / "gone")),
        ]
        scanner = FakeScanner([_proc(77, str(present))])
        scan = scan_edt(scanner, projects)
        assert scan == EdtScan(running={"p1": 77}, present={"p1": True, "p2": False})
        assert scanner.names == [frozenset({"1cedt.exe"})]

    def test_status_before_and_after_scan(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        before = h.workspace.status(p.id)
        assert before.running_pid is None
        assert before.workspace_present is None
        assert before.installed is True
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={p.id: False}))
        after = h.workspace.status(p.id)
        assert after.running_pid == 9
        assert after.workspace_present is False

    def test_status_not_installed(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2024.2.6+7"))
        assert h.workspace.status(p.id).installed is False


class TestLaunch:
    def test_started_with_full_command(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4", vm_args="-Xmx4g"))
        assert h.workspace.launch(p.id) is LaunchOutcome.STARTED
        [command] = h.spawned
        assert command.executable == EXE_2025
        assert command.arguments == (
            f'-data "{p.workspace}" -vm "{JDK}" --launcher.appendVmargs '
            "-vmargs -Xmx8192m -Dx=1 -Djava.library.path= -Xmx4g"
        )

    def test_project_jvm_override(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(
            _project("a", edt_version="2025.2.6+4", jvm_dir=r"D:\my\bin")
        )
        h.workspace.launch(p.id)
        assert '-vm "D:\\my\\bin"' in h.spawned[0].arguments

    def test_running_activates_instead_of_spawn(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={}))
        assert h.workspace.launch(p.id) is LaunchOutcome.ACTIVATED
        assert h.activated == [9]
        assert h.spawned == []

    def test_activation_missed_is_silent_outcome(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED, activate_result=False)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        h.workspace.apply_scan(EdtScan(running={p.id: 9}, present={}))
        assert h.workspace.launch(p.id) is LaunchOutcome.ACTIVATION_MISSED
        assert h.spawned == []

    def test_version_not_installed_refuses(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2024.2.6+7"))
        with pytest.raises(EdtLaunchError, match="EDT 2024.2.6\\+7 не найден"):
            h.workspace.launch(p.id)
        assert h.spawned == []

    def test_no_jvm_refuses_before_spawn(self, tmp_path: Path) -> None:
        no_jvm = [EdtInstallation("2025.2.6+4", EXE_2025, None, "", 17, "")]
        h = _harness(tmp_path, installed=no_jvm)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        with pytest.raises(EdtLaunchError, match="JDK"):
            h.workspace.launch(p.id)
        assert h.spawned == []

    def test_spawn_oserror_becomes_launch_error(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, installed=INSTALLED, spawn_error=True)
        h.workspace.refresh_installations()
        p = h.workspace.add_project(_project("a", edt_version="2025.2.6+4"))
        with pytest.raises(EdtLaunchError):
            h.workspace.launch(p.id)


class TestEditorsAndExplorer:
    def test_opens_project_dir_in_editor(self, tmp_path: Path) -> None:
        code = Path(r"C:\code\code.cmd")
        h = _harness(tmp_path, editor=EditorResolution(code, "PATH", ""))
        p = h.workspace.add_project(_project("a", project_dir=r"D:\edt\a\proj"))
        h.workspace.open_in_editor(p.id, EditorKind.VSCODE)
        [command] = h.spawned
        assert command.executable == code
        assert command.arguments == '"D:\\edt\\a\\proj"'

    def test_empty_project_dir_opens_workspace(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, editor=EditorResolution(Path(r"C:\code\code.cmd"), "PATH", ""))
        p = h.workspace.add_project(_project("a"))
        h.workspace.open_in_editor(p.id, EditorKind.VSCODE)
        assert h.spawned[0].arguments == f'"{p.workspace}"'

    def test_missing_editor_refuses(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        p = h.workspace.add_project(_project("a"))
        with pytest.raises(EdtError, match="Не найден"):
            h.workspace.open_in_editor(p.id, EditorKind.ANTIGRAVITY)
        assert h.spawned == []

    def test_open_folder_uses_startfile(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        p = h.workspace.add_project(_project("a", project_dir=r"D:\edt\a\proj"))
        h.workspace.open_folder(p.id)
        assert h.opened == [r"D:\edt\a\proj"]


PRODUCT = EdtStartProduct("prod", "2025.2.6+4", EXE_2025, JDK, ("-Xmx8192m",))
ES_PROJECT = EdtStartProject("es", "(2025) А", Path(r"D:\edt\2025\a"), "prod", ("-Xmx8192m",), None)


class TestImport:
    def test_candidates_none_without_registry(self, tmp_path: Path) -> None:
        h = _harness(tmp_path)
        assert h.workspace.import_candidates() is None
        assert h.workspace.edtstart_available() is False

    def test_import_adds_selected_and_is_idempotent(self, tmp_path: Path) -> None:
        registry = EdtStartRegistry((PRODUCT,), (ES_PROJECT,), 0)
        h = _harness(tmp_path, edtstart=registry)
        candidates = h.workspace.import_candidates()
        assert candidates is not None and len(candidates) == 1
        assert h.workspace.import_projects(candidates) == 1
        assert h.workspace.projects()[0].workspace == r"D:\edt\2025\a"
        assert h.workspace.import_candidates() == []

    def test_import_nothing_selected(self, tmp_path: Path) -> None:
        h = _harness(tmp_path, edtstart=EdtStartRegistry((PRODUCT,), (ES_PROJECT,), 0))
        assert h.workspace.import_projects([]) == 0
        assert h.workspace.projects() == []
```

Функция `_project` из Task 12 принимает `**overrides` — `edt_version`, `vm_args`, `jvm_dir`, `project_dir` идут через неё.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_edt_workspace.py -q`
Expected: `ImportError` на `EdtScan`.

- [ ] **Step 3: Реализовать**

В `src/onecstarter/services/edt.py` добавить импорты:

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from onecstarter.domain.edt import (
    ImportCandidate,
    build_edt_command,
    effective_jvm,
    import_candidates,
    running_workspaces,
)
from onecstarter.platform_1c.process_scan import ProcessScanner
from onecstarter.services.errors import EdtError, EdtLaunchError
```

Типы и скан — на уровне модуля, перед классом:

```python
EDT_PROCESS_NAMES = frozenset({"1cedt.exe"})


class LaunchOutcome(Enum):
    STARTED = "started"
    ACTIVATED = "activated"
    ACTIVATION_MISSED = "missed"  # окно не нашлось — молча (спека §4)


@dataclass(frozen=True)
class EdtScan:
    running: dict[str, int]
    present: dict[str, bool]


@dataclass(frozen=True)
class EdtStatus:
    running_pid: int | None
    workspace_present: bool | None
    installed: bool
    cli_busy: bool = False


def scan_edt(
    scanner: ProcessScanner,
    projects: Sequence[EdtProject],
    is_dir: Callable[[str], bool] = os.path.isdir,
) -> EdtScan:
    """Снимок для монитора: кто запущен и чьи каталоги на месте. Зовётся из потока-демона."""
    processes = scanner.snapshot(EDT_PROCESS_NAMES)
    running = running_workspaces(((p.pid, p.argv) for p in processes), projects)
    present = {project.id: is_dir(project.workspace) for project in projects}
    return EdtScan(running=running, present=present)
```

В `__init__` добавить:

```python
        self._running: dict[str, int] = {}
        self._present: dict[str, bool] = {}
```

Методы класса (после «перестановки», перед «внутреннее»):

```python
    # --- установки --------------------------------------------------------

    def refresh_installations(self) -> list[EdtInstallation]:
        self._installations = list(self._discover())
        self._installations_ready = True
        return list(self._installations)

    def installations(self) -> list[EdtInstallation]:
        return list(self._installations)

    def installations_ready(self) -> bool:
        return self._installations_ready

    def installation_for(self, project: EdtProject) -> EdtInstallation | None:
        """Точное совпадение строки версии (спека §2) — никакой «ближайшей»."""
        for installation in self._installations:
            if installation.version == project.edt_version:
                return installation
        return None

    # --- статус -----------------------------------------------------------

    def apply_scan(self, scan: EdtScan) -> None:
        self._running = dict(scan.running)
        self._present.update(scan.present)

    def running_pid(self, project_id: str) -> int | None:
        return self._running.get(project_id)

    def status(self, project_id: str) -> EdtStatus:
        project = self.project(project_id)
        return EdtStatus(
            running_pid=self._running.get(project_id),
            workspace_present=self._present.get(project_id),
            installed=self.installation_for(project) is not None,
        )

    # --- запуск -----------------------------------------------------------

    def launch(self, project_id: str) -> LaunchOutcome:
        project = self.project(project_id)
        pid = self._running.get(project_id)
        if pid is not None:
            return LaunchOutcome.ACTIVATED if self._activate(pid) else LaunchOutcome.ACTIVATION_MISSED
        installation = self.installation_for(project)
        if installation is None:
            raise EdtLaunchError(
                f"EDT {project.edt_version or '(версия не задана)'} не найден среди установок"
            )
        jvm = effective_jvm(project, installation)
        if jvm is None:
            raise EdtLaunchError(
                f"JDK для EDT {installation.version} не найден: нужна Java "
                f"{installation.required_java}+; укажите каталог bin JDK в Настройках "
                "или в записи"
            )
        command = build_edt_command(
            installation.exe, project.workspace, jvm, installation.vm_args, project.vm_args
        )
        self._run(command)
        return LaunchOutcome.STARTED

    def editor(self, kind: EditorKind) -> EditorResolution:
        return self._editors(kind)

    def open_in_editor(self, project_id: str, kind: EditorKind) -> None:
        project = self.project(project_id)
        resolution = self._editors(kind)
        if resolution.path is None:
            raise EdtError(resolution.note)
        self._run(LaunchCommand(executable=resolution.path, arguments=f'"{self._folder(project)}"'))

    def open_folder(self, project_id: str) -> None:
        try:
            self._open_file(self._folder(self.project(project_id)))
        except OSError as error:
            raise EdtError(f"Не удалось открыть каталог: {error}") from error

    # --- импорт -----------------------------------------------------------

    def edtstart_available(self) -> bool:
        return self._edtstart() is not None

    def edtstart_skipped(self) -> int:
        registry = self._edtstart()
        return registry.skipped if registry is not None else 0

    def import_candidates(self) -> list[ImportCandidate] | None:
        registry = self._edtstart()
        if registry is None:
            return None
        return import_candidates(registry.projects, registry.products, self._projects, self._new_id)

    def import_projects(self, candidates: Sequence[ImportCandidate]) -> int:
        known = {p.workspace for p in self._projects}
        added = 0
        for candidate in candidates:
            if candidate.project.workspace in known:
                continue
            self._projects.append(candidate.project)
            known.add(candidate.project.workspace)
            added += 1
        if added:
            self._save()
        return added
```

И во «внутреннее»:

```python
    @staticmethod
    def _folder(project: EdtProject) -> str:
        return project.project_dir or project.workspace

    def _run(self, command: LaunchCommand) -> None:
        try:
            self._spawn(command)
        except OSError as error:
            raise EdtLaunchError(f"Не удалось запустить: {command.executable} ({error})") from error
```

- [ ] **Step 4: Прогнать, затем три мутации**

Run: `uv run pytest tests/unit/test_edt_workspace.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

Мутация 1 — «отказ без JDK»: в `launch` временно убрать `if jvm is None: raise …`
и подставить `jvm = jvm or Path("x")`. Expected: `test_no_jvm_refuses_before_spawn` падает
(нет исключения / `spawned` не пуст). Откатить.

Мутация 2 — «повтор не плодит второй процесс»: временно убрать ветку `if pid is not None`.
Expected: `test_running_activates_instead_of_spawn` падает на `h.spawned == []`. Откатить.

Мутация 3 — «идемпотентность импорта»: в `domain.edt.import_candidates` временно
заменить `if workspace_key(workspace) in known: continue` на `pass`. Expected:
`test_idempotent_second_pass` (Task 6) и `test_import_adds_selected_and_is_idempotent`
падают на дубле. Откатить.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/services/edt.py tests/unit/test_edt_workspace.py
git commit -m "feat(services): запуск EDT с активацией окна, редакторы, статус по скану, импорт из EDT Start (мутации: 3 проверены)"
```

---

### Task 14: UI — значок раздела, модель дерева, монитор, каркас `EdtView`

**Files:**
- Modify: `src/onecstarter/ui/rail_icons.py`
- Create: `src/onecstarter/ui/edt/__init__.py` (пустой)
- Create: `src/onecstarter/ui/edt/tree_model.py`
- Create: `src/onecstarter/ui/edt/monitor.py`
- Create: `src/onecstarter/ui/edt/view.py`
- Create: `tests/ui/test_edt_tree_model.py`
- Create: `tests/ui/test_edt_monitor.py`
- Create: `tests/ui/test_edt_view.py`
- Modify: `tests/ui/test_rail_icons.py`

**Interfaces:**
- Consumes: `EdtWorkspace` (`children`, `status`, `launch`, `projects`, `installations_ready`, `set_installations`, `apply_scan`, `edtstart_available`), `EdtScan`, `scan_edt`, `LaunchOutcome` (Tasks 12–13); `ProcessScanner`; `Palette`; `EdtError`.
- Produces: `rail_icons.edt_icon(palette) -> QIcon`; в `tree_model`: `ID_ROLE`, `KIND_ROLE`, `KIND_GROUP = "group"`, `KIND_PROJECT = "project"`, `COLUMNS = ("Проект", "EDT", "")`, `MISSING_SUFFIX = " (нет каталога)"`, `RUNNING_GLYPH = "●"`, `matches(project, query) -> bool`, `build_edt_model(workspace, query, palette) -> QStandardItemModel`; `EdtMonitor(scanner, projects: Callable[[], list[EdtProject]], discover: Callable[[], list[EdtInstallation]], *, interval_ms=5000, spawn=_spawn_daemon, parent=None)` с сигналами `scan_ready(object)`, `installations_ready(object)` и методами `start()`, `scan_now()`, `discover_now()`; `EdtView(workspace, *, palette, request_scan=lambda: None, request_discover=lambda: None, show_error=None, parent=None)` с методами `rebuild()`, `apply_palette(palette)`, `on_scan(scan)`, `on_installations(items)`, `launch_id(project_id)`, `current() -> tuple[str, str] | None` (kind, id), `tree()`, `model()`, `search()`, `banner()`, `focus_search()`.

Перед началом — в `services/edt.py` (Task 13) добавить метод, которого требует монитор (обнаружение идёт в потоке-демоне, а список кладётся в координатор из главного потока):

```python
    def set_installations(self, installations: Sequence[EdtInstallation]) -> None:
        self._installations = list(installations)
        self._installations_ready = True
```

и переписать `refresh_installations` через него: `self.set_installations(self._discover()); return self.installations()`.

- [ ] **Step 1: Значок раздела — тест и рисунок**

В `tests/ui/test_rail_icons.py` добавить (по образцу существующего теста `servers_icon`):

```python
def test_edt_icon_is_not_empty(qapp: QApplication) -> None:
    icon = rail_icons.edt_icon(DARK)
    assert not icon.isNull()
    # Слэш глифа проходит через центр — пиксель (8, 8) непрозрачен.
    assert icon.pixmap(16, 16).toImage().pixelColor(8, 8).alpha() > 0
```

(`DARK`/`qapp` — как в соседних тестах файла; если палитра там называется иначе — взять её имя.)

В `src/onecstarter/ui/rail_icons.py` после `_draw_servers`:

```python
def _draw_edt(painter: QPainter) -> None:
    """Угловые скобки кода `< >` со слэшем — «исходники», без чужих знаков."""
    pen = painter.pen()
    pen.setWidthF(1.6)
    painter.setPen(pen)
    painter.drawLine(5, 4, 1, 8)
    painter.drawLine(1, 8, 5, 12)
    painter.drawLine(11, 4, 15, 8)
    painter.drawLine(15, 8, 11, 12)
    painter.drawLine(9, 3, 7, 13)


def edt_icon(palette: Palette) -> QIcon:
    return _icon(palette, _draw_edt)
```

(`_icon` принимает функцию рисования и красит пером палитры — см. `_draw_servers`/`servers_icon`; если `_draw_*` в файле сами ставят перо, повторить их манеру.)

- [ ] **Step 2: Модель дерева — падающие тесты**

`tests/ui/test_edt_tree_model.py`:

```python
"""Модель дерева EDT: группы, фильтр, версия, статус, метка каталога (спека §7)."""

from itertools import count
from pathlib import Path

from PySide6.QtGui import QColor, QStandardItemModel

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.ui.edt.tree_model import (
    ID_ROLE,
    KIND_GROUP,
    KIND_PROJECT,
    KIND_ROLE,
    MISSING_SUFFIX,
    RUNNING_GLYPH,
    build_edt_model,
    matches,
)
from onecstarter.ui.theme import DARK

INSTALLED = [EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")]


def _workspace(tmp_path: Path) -> EdtWorkspace:
    ids = count(1)
    ws = EdtWorkspace(
        tmp_path / "edt.json",
        discover=lambda: INSTALLED,
        edtstart=lambda: None,
        editors=lambda kind: None,  # type: ignore[arg-type, return-value]
        spawn=lambda c: 1,
        activate=lambda p: True,
        open_file=lambda p: None,
        new_id=lambda: f"id-{next(ids)}",
    )
    ws.refresh_installations()
    return ws


def _names(model: QStandardItemModel) -> list[tuple[str, str, int]]:
    """(kind, текст, глубина) в порядке обхода."""
    out: list[tuple[str, str, int]] = []

    def walk(parent, depth: int) -> None:  # type: ignore[no-untyped-def]
        for row in range(parent.rowCount()):
            item = parent.child(row, 0)
            out.append((item.data(KIND_ROLE), item.text(), depth))
            walk(item, depth + 1)

    walk(model.invisibleRootItem(), 0)
    return out


def test_tree_shape_follows_workspace_order(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    g = ws.add_group("2025", None)
    ws.add_project(EdtProject("", "Розница", r"D:\a", edt_version="2025.2.6+4", group_id=g.id))
    ws.add_project(EdtProject("", "Опт", r"D:\b", edt_version="2025.2.6+4"))
    model = build_edt_model(ws, "", DARK)
    assert _names(model) == [(KIND_GROUP, "2025", 0), (KIND_PROJECT, "Розница", 1), (KIND_PROJECT, "Опт", 0)]
    assert model.item(0, 0).data(ID_ROLE) == g.id


def test_filter_keeps_group_with_matching_descendant(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    g = ws.add_group("2025", None)
    ws.add_project(EdtProject("", "Розница", r"D:\a", group_id=g.id))
    ws.add_project(EdtProject("", "Опт", r"D:\b"))
    model = build_edt_model(ws, "роз", DARK)
    assert _names(model) == [(KIND_GROUP, "2025", 0), (KIND_PROJECT, "Розница", 1)]


def test_filter_matches_workspace_path_too(tmp_path: Path) -> None:
    project = EdtProject("", "Опт", r"D:\edt\wholesale")
    assert matches(project, "WHOLE") is True
    assert matches(project, "розн") is False
    assert matches(project, "") is True


def test_version_column_marks_not_installed(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Старая", r"D:\a", edt_version="2024.2.6+7"))
    ws.add_project(EdtProject("", "Новая", r"D:\b", edt_version="2025.2.6+4"))
    model = build_edt_model(ws, "", DARK)
    old, new = model.item(0, 1), model.item(1, 1)
    assert old.text() == "2024.2.6+7"
    assert old.toolTip() == "EDT 2024.2.6+7 не найден"
    assert old.foreground().color() == QColor(DARK.problem)
    assert new.toolTip() == ""
    assert new.foreground().color() != QColor(DARK.problem)


def test_empty_version_shows_dash(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Без версии", r"D:\a"))
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 1).text() == "—"
    assert model.item(0, 1).toolTip() == "Версия EDT не задана"


def test_status_and_missing_dir_after_scan(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    p = ws.add_project(EdtProject("", "Розница", r"D:\a", edt_version="2025.2.6+4"))
    ws.apply_scan(EdtScan(running={p.id: 42}, present={p.id: False}))
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 0).text() == "Розница" + MISSING_SUFFIX
    assert model.item(0, 2).text() == RUNNING_GLYPH
    assert model.item(0, 2).toolTip() == "Запущен (PID 42)"
    assert model.item(0, 2).foreground().color() == QColor(DARK.accent)


def test_no_status_before_scan(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Розница", r"D:\a"))
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 0).text() == "Розница"
    assert model.item(0, 2).text() == ""
    assert model.item(0, 0).toolTip() == r"D:\a"


def test_tooltip_lists_project_dir(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Р", r"D:\a", project_dir=r"D:\a\proj"))
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 0).toolTip() == "D:\\a\nПроект: D:\\a\\proj"
```

Имя палитры (`DARK`) взять из `onecstarter.ui.theme` — как в `tests/ui/test_tree_model.py`.

- [ ] **Step 3: Модель дерева — реализация**

`src/onecstarter/ui/edt/__init__.py` — пустой.

`src/onecstarter/ui/edt/tree_model.py`:

```python
"""Модель дерева раздела «EDT» (спека v3, §7): группы, записи, версия, статус.

Модель собирается заново на каждую перестройку — тот же приём, что
`ui/bases/tree_model.py`: порядок и вложенность даёт координатор,
здесь только раскладка по колонкам и подсветка.
"""  # noqa: RUF002

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel

from onecstarter.domain.edt import EdtProject
from onecstarter.services.edt import EdtStatus, EdtWorkspace
from onecstarter.ui.theme import Palette

ID_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2
KIND_GROUP = "group"
KIND_PROJECT = "project"

COLUMNS = ("Проект", "EDT", "")
MISSING_SUFFIX = " (нет каталога)"
RUNNING_GLYPH = "●"
NOT_INSTALLED_HINT = "EDT {version} не найден"
NO_VERSION_HINT = "Версия EDT не задана"
CLI_BUSY_HINT = "Выполняется команда CLI"


def matches(project: EdtProject, query: str) -> bool:
    needle = query.casefold().strip()
    if not needle:
        return True
    return needle in project.name.casefold() or needle in project.workspace.casefold()


def build_edt_model(workspace: EdtWorkspace, query: str, palette: Palette) -> QStandardItemModel:
    model = QStandardItemModel(0, len(COLUMNS))
    model.setHorizontalHeaderLabels(list(COLUMNS))
    _fill(model.invisibleRootItem(), None, workspace, query, palette)
    return model


def _fill(
    parent: QStandardItem,
    group_id: str | None,
    workspace: EdtWorkspace,
    query: str,
    palette: Palette,
) -> bool:
    """Заполнить детей `group_id`; вернуть, есть ли среди них видимые записи."""
    groups, projects = workspace.children(group_id)
    visible = False
    for group in groups:
        item = QStandardItem(group.name)
        item.setEditable(False)
        item.setData(group.id, ID_ROLE)
        item.setData(KIND_GROUP, KIND_ROLE)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        if _fill(item, group.id, workspace, query, palette):
            parent.appendRow([item, _plain(""), _plain("")])
            visible = True
    for project in projects:
        if not matches(project, query):
            continue
        parent.appendRow(_project_row(project, workspace.status(project.id), palette))
        visible = True
    return visible


def _plain(text: str) -> QStandardItem:
    item = QStandardItem(text)
    item.setEditable(False)
    return item


def _project_row(project: EdtProject, status: EdtStatus, palette: Palette) -> list[QStandardItem]:
    name = _plain(project.name + (MISSING_SUFFIX if status.workspace_present is False else ""))
    name.setData(project.id, ID_ROLE)
    name.setData(KIND_PROJECT, KIND_ROLE)
    tooltip = project.workspace
    if project.project_dir:
        tooltip += f"\nПроект: {project.project_dir}"
    name.setToolTip(tooltip)

    version = _plain(project.edt_version or "—")
    if not project.edt_version:
        version.setToolTip(NO_VERSION_HINT)
        version.setForeground(QBrush(QColor(palette.text_dim)))
    elif not status.installed:
        version.setToolTip(NOT_INSTALLED_HINT.format(version=project.edt_version))
        version.setForeground(QBrush(QColor(palette.problem)))

    state = _plain("")
    if status.running_pid is not None:
        state.setText(RUNNING_GLYPH)
        state.setToolTip(f"Запущен (PID {status.running_pid})")
        state.setForeground(QBrush(QColor(palette.accent)))
    elif status.cli_busy:
        state.setText(RUNNING_GLYPH)
        state.setToolTip(CLI_BUSY_HINT)
        state.setForeground(QBrush(QColor(palette.problem)))
    return [name, version, state]
```

Run: `uv run pytest tests/ui/test_edt_tree_model.py -q` — зелёное.

- [ ] **Step 4: Монитор — падающие тесты**

`tests/ui/test_edt_monitor.py`:

```python
"""EdtMonitor — калька test_server_monitor.py: скан и обнаружение в подставном «потоке»."""

from collections.abc import Callable
from pathlib import Path

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.services.edt import EdtScan
from onecstarter.ui.edt.monitor import EdtMonitor


class FakeScanner:
    def __init__(self, processes: list[ProcessInfo]) -> None:
        self._processes = processes

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        return list(self._processes)


def _inline(task: Callable[[], None]) -> None:
    task()


def test_scan_now_emits_scan(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    project = EdtProject("p1", "a", str(ws_dir))
    proc = ProcessInfo(pid=5, name="1cedt.exe", executable=None, argv=("x", "-data", str(ws_dir)))
    monitor = EdtMonitor(FakeScanner([proc]), lambda: [project], lambda: [], spawn=_inline)
    received: list[EdtScan] = []
    monitor.scan_ready.connect(received.append)
    monitor.scan_now()
    assert received == [EdtScan(running={"p1": 5}, present={"p1": True})]


def test_discover_now_emits_installations(qapp) -> None:  # type: ignore[no-untyped-def]
    installed = [EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), None, "", 17, "")]
    monitor = EdtMonitor(FakeScanner([]), lambda: [], lambda: list(installed), spawn=_inline)
    received: list[list[EdtInstallation]] = []
    monitor.installations_ready.connect(received.append)
    monitor.discover_now()
    assert received == [installed]


def test_busy_scan_skips_tick(qapp) -> None:  # type: ignore[no-untyped-def]
    pending: list[Callable[[], None]] = []
    monitor = EdtMonitor(FakeScanner([]), lambda: [], lambda: [], spawn=pending.append)
    monitor.scan_now()
    monitor.scan_now()
    assert len(pending) == 1
    pending[0]()
    monitor.scan_now()
    assert len(pending) == 2


def test_scan_failure_emits_empty_scan(qapp) -> None:  # type: ignore[no-untyped-def]
    class Broken:
        def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
            raise RuntimeError("psutil упал")

    monitor = EdtMonitor(Broken(), lambda: [], lambda: [], spawn=_inline)
    received: list[EdtScan] = []
    monitor.scan_ready.connect(received.append)
    monitor.scan_now()
    assert received == [EdtScan(running={}, present={})]


def test_discover_failure_emits_empty_list(qapp) -> None:  # type: ignore[no-untyped-def]
    def broken() -> list[EdtInstallation]:
        raise OSError("диск")

    monitor = EdtMonitor(FakeScanner([]), lambda: [], broken, spawn=_inline)
    received: list[list[EdtInstallation]] = []
    monitor.installations_ready.connect(received.append)
    monitor.discover_now()
    assert received == [[]]
```

- [ ] **Step 5: Монитор — реализация**

`src/onecstarter/ui/edt/monitor.py`:

```python
"""Фоновый монитор раздела «EDT»: скан процессов и каталогов + обнаружение установок.

Калька `ui/servers/monitor.py::ServerMonitor` (её докстринг — прочитать целиком):
`QTimer` в главном потоке тикает каждые `interval_ms`, каждый тик — новый скан
в потоке-демоне; занятый скан пропускает тик. Отличия: два вида задач —
периодический `scan_edt` (процессы `1cedt.exe` + `isdir` каждого workspace)
и обнаружение установок по требованию (`discover_now`, старт и `F5`),
у каждой свой флаг занятости и свой сигнал. Список записей снимается
в главном потоке до спавна задачи — координатор из потока-демона не трогается.
"""  # noqa: RUF002

import logging
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.platform_1c.process_scan import ProcessScanner
from onecstarter.services.edt import EdtScan, scan_edt

_log = logging.getLogger("onecstarter.edt")


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


def _log_failure(stage: str, exc: BaseException) -> None:
    """Тип и кадры без текста исключения — инвариант 5 (см. `background.py`)."""
    frames = " -> ".join(
        f"{Path(frame.filename).name}:{frame.lineno}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
    _log.error("%s: отказ (%s @ %s)", stage, type(exc).__name__, frames)


class EdtMonitor(QObject):
    scan_ready = Signal(object)  # EdtScan
    installations_ready = Signal(object)  # list[EdtInstallation]

    def __init__(
        self,
        scanner: ProcessScanner,
        projects: Callable[[], list[EdtProject]],
        discover: Callable[[], list[EdtInstallation]],
        *,
        interval_ms: int = 5000,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._projects = projects
        self._discover = discover
        self._spawn = spawn
        self._scan_busy = False
        self._discover_busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.scan_now)

    def start(self) -> None:
        self.discover_now()
        self.scan_now()
        self._timer.start()

    def scan_now(self) -> None:
        if self._scan_busy:
            return
        self._scan_busy = True
        projects = self._projects()

        def run() -> None:
            try:
                scan = scan_edt(self._scanner, projects)
            except Exception as exc:
                _log_failure("скан EDT", exc)
                scan = EdtScan(running={}, present={})
            self._scan_busy = False
            self.scan_ready.emit(scan)

        self._spawn(run)

    def discover_now(self) -> None:
        if self._discover_busy:
            return
        self._discover_busy = True

        def run() -> None:
            try:
                found = self._discover()
            except Exception as exc:
                _log_failure("обнаружение EDT", exc)
                found = []
            self._discover_busy = False
            self.installations_ready.emit(found)

        self._spawn(run)
```

Run: `uv run pytest tests/ui/test_edt_monitor.py -q` — зелёное.

- [ ] **Step 6: Каркас вьюхи — падающие тесты**

`tests/ui/test_edt_view.py`:

```python
"""EdtView: дерево, фильтр, запуск по Enter/двойному клику, статус, F5 (спека §7)."""

from itertools import count
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from onecstarter.domain.edt import EdtInstallation, EdtProject, EditorResolution
from onecstarter.domain.launch import LaunchCommand
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.ui.edt.tree_model import ID_ROLE, RUNNING_GLYPH
from onecstarter.ui.edt.view import EdtView
from onecstarter.ui.theme import DARK

INSTALLED = [
    EdtInstallation("2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")
]


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        ids = count(1)
        self.spawned: list[LaunchCommand] = []
        self.activated: list[int] = []
        self.opened: list[str] = []
        self.errors: list[str] = []
        self.scans_requested = 0
        self.discovers_requested = 0
        self.editor = EditorResolution(None, "", "Не найден — укажите путь в Настройках")
        self.workspace = EdtWorkspace(
            tmp_path / "edt.json",
            discover=lambda: list(INSTALLED),
            edtstart=lambda: None,
            editors=lambda kind: self.editor,
            spawn=self._spawn,
            activate=self._activate,
            open_file=self.opened.append,
            new_id=lambda: f"id-{next(ids)}",
        )
        self.workspace.refresh_installations()

    def _spawn(self, command: LaunchCommand) -> int:
        self.spawned.append(command)
        return 1

    def _activate(self, pid: int) -> bool:
        self.activated.append(pid)
        return True

    def _scan(self) -> None:
        self.scans_requested += 1

    def _discover(self) -> None:
        self.discovers_requested += 1

    def view(self) -> EdtView:
        return EdtView(
            self.workspace,
            palette=DARK,
            request_scan=self._scan,
            request_discover=self._discover,
            show_error=self.errors.append,
        )


@pytest.fixture
def harness(tmp_path: Path, qtbot) -> Harness:  # type: ignore[no-untyped-def]
    return Harness(tmp_path)


def _add(h: Harness, name: str, **overrides: object) -> EdtProject:
    values: dict[str, object] = {"id": "", "name": name, "workspace": rf"D:\edt\{name}", "edt_version": "2025.2.6+4"}
    values.update(overrides)
    return h.workspace.add_project(EdtProject(**values))  # type: ignore[arg-type]


def _select(view: EdtView, project_id: str) -> None:
    model = view.model()
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(ID_ROLE) == project_id:
            view.tree().setCurrentIndex(index)
            return
    raise AssertionError(f"нет строки {project_id}")


def test_tree_shows_projects(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    _add(harness, "a")
    _add(harness, "b")
    view = harness.view()
    qtbot.addWidget(view)
    assert view.model().rowCount() == 2


def test_search_filters_and_enter_launches_first(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    _add(harness, "Розница")
    b = _add(harness, "Опт")
    view = harness.view()
    qtbot.addWidget(view)
    view.search().setText("опт")
    assert view.model().rowCount() == 1
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert [c.arguments for c in harness.spawned] == [
        f'-data "{b.workspace}" -vm "C:\\j\\bin" --launcher.appendVmargs -vmargs -Djava.library.path='
    ]


def test_double_click_launches(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    _select(view, p.id)
    view.tree().doubleClicked.emit(view.tree().currentIndex())
    assert len(harness.spawned) == 1
    assert harness.scans_requested == 1  # подтверждающий скан после запуска


def test_launch_running_activates(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.on_scan(EdtScan(running={p.id: 77}, present={p.id: True}))
    assert view.model().item(0, 2).text() == RUNNING_GLYPH
    view.launch_id(p.id)
    assert harness.activated == [77]
    assert harness.spawned == []


def test_launch_error_is_shown_not_raised(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a", edt_version="2024.2.6+7")
    view = harness.view()
    qtbot.addWidget(view)
    view.launch_id(p.id)
    assert harness.errors == ["EDT 2024.2.6+7 не найден среди установок"]


def test_f5_requests_scan_and_discover(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    qtbot.keyClick(view.tree(), Qt.Key.Key_F5)
    assert harness.scans_requested == 1
    assert harness.discovers_requested == 1


def test_installations_arrival_rebuilds_version_marks(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    _add(harness, "a", edt_version="2026.1.2+2")
    view = harness.view()
    qtbot.addWidget(view)
    assert view.model().item(0, 1).toolTip() == "EDT 2026.1.2+2 не найден"
    view.on_installations(
        [EdtInstallation("2026.1.2+2", Path(r"C:\e2\1cedt.exe"), Path(r"C:\j\bin"), "", 17, "auto")]
    )
    assert view.model().item(0, 1).toolTip() == ""


def test_current_returns_kind_and_id(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    assert view.current() is None
    _select(view, p.id)
    assert view.current() == ("project", p.id)


def test_expansion_survives_rebuild(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    _add(harness, "a", group_id=g.id)
    view = harness.view()
    qtbot.addWidget(view)
    view.tree().collapse(view.model().index(0, 0))
    view.rebuild()
    assert view.tree().isExpanded(view.model().index(0, 0)) is False
    view.tree().expand(view.model().index(0, 0))
    view.rebuild()
    assert view.tree().isExpanded(view.model().index(0, 0)) is True
```

- [ ] **Step 7: Каркас вьюхи — реализация**

`src/onecstarter/ui/edt/view.py`:

```python
"""Раздел «EDT» (спека v3, §7): дерево записей и групп, фильтр, запуск, статус.

Контекстное меню, диалоги и перетаскивание — Task 15–17; здесь каркас:
модель собирается заново из координатора (`rebuild`), раскрытие групп
переживает перестройку по id группы, Enter в поиске запускает первую
видимую запись — тот же приём, что у `BasesView`.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QKeyEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt import EdtInstallation
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.services.errors import ServicesError
from onecstarter.ui.edt.tree_model import ID_ROLE, KIND_PROJECT, KIND_ROLE, build_edt_model
from onecstarter.ui.theme import Palette


class _EdtTree(QTreeView):
    def __init__(self, view: "EdtView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._view._launch_index(self.currentIndex())
            return
        if event.key() == Qt.Key.Key_F5:
            self._view.refresh_all()
            return
        super().keyPressEvent(event)


class EdtView(QWidget):
    def __init__(
        self,
        workspace: EdtWorkspace,
        *,
        palette: Palette,
        request_scan: Callable[[], None] = lambda: None,
        request_discover: Callable[[], None] = lambda: None,
        show_error: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._palette = palette
        self._request_scan = request_scan
        self._request_discover = request_discover
        self._show_error = show_error or self._default_show_error
        self._model = QStandardItemModel()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск: начните вводить имя проекта")
        self._search.textChanged.connect(lambda _text: self.rebuild())
        self._search.returnPressed.connect(self._launch_first_visible)

        self._banner = QWidget()
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_label = QLabel("Список пуст. Импортировать из EDT Start?")
        self._banner_button = QPushButton("Импортировать…")
        banner_layout.addWidget(self._banner_label, 1)
        banner_layout.addWidget(self._banner_button)
        self._banner.hide()

        self._tree = _EdtTree(self)
        self._tree.setHeaderHidden(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setRootIsDecorated(True)
        self._tree.doubleClicked.connect(self._launch_index)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._banner)
        layout.addWidget(self._tree, 1)
        self.rebuild()

    # --- доступ -----------------------------------------------------------

    def workspace(self) -> EdtWorkspace:
        return self._workspace

    def model(self) -> QStandardItemModel:
        return self._model

    def tree(self) -> QTreeView:
        return self._tree

    def search(self) -> QLineEdit:
        return self._search

    def banner(self) -> QWidget:
        return self._banner

    def banner_button(self) -> QPushButton:
        return self._banner_button

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def current(self) -> tuple[str, str] | None:
        index = self._tree.currentIndex()
        if not index.isValid():
            return None
        kind = index.siblingAtColumn(0).data(KIND_ROLE)
        item_id = index.siblingAtColumn(0).data(ID_ROLE)
        if isinstance(kind, str) and isinstance(item_id, str):
            return kind, item_id
        return None

    # --- перестройка ------------------------------------------------------

    def rebuild(self) -> None:
        expanded = self._expanded_ids()
        first_build = self._model.rowCount() == 0 and not expanded
        self._model = build_edt_model(self._workspace, self._search.text(), self._palette)
        self._tree.setModel(self._model)
        self._tree.setColumnWidth(0, 320)
        self._tree.setColumnWidth(1, 110)
        self._restore_expansion(expanded, expand_all=first_build)
        self._banner.setVisible(
            not self._workspace.projects() and self._workspace.edtstart_available()
        )

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.rebuild()

    def on_scan(self, scan: EdtScan) -> None:
        self._workspace.apply_scan(scan)
        self.rebuild()

    def on_installations(self, installations: Sequence[EdtInstallation]) -> None:
        self._workspace.set_installations(installations)
        self.rebuild()

    def refresh_all(self) -> None:
        self._request_discover()
        self._request_scan()

    # --- запуск -----------------------------------------------------------

    def launch_id(self, project_id: str) -> None:
        try:
            self._workspace.launch(project_id)
        except ServicesError as error:
            self._show_error(str(error))
            return
        self._request_scan()

    def _launch_index(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        first = index.siblingAtColumn(0)
        if first.data(KIND_ROLE) == KIND_PROJECT:
            self.launch_id(first.data(ID_ROLE))

    def _launch_first_visible(self) -> None:
        first = self._first_project(QModelIndex())
        if first is not None:
            self.launch_id(first)

    def _first_project(self, parent: QModelIndex) -> str | None:
        for row in range(self._model.rowCount(parent)):
            index = self._model.index(row, 0, parent)
            if index.data(KIND_ROLE) == KIND_PROJECT:
                return index.data(ID_ROLE)
            found = self._first_project(index)
            if found is not None:
                return found
        return None

    # --- раскрытие --------------------------------------------------------

    def _expanded_ids(self) -> set[str]:
        ids: set[str] = set()

        def walk(parent: QModelIndex) -> None:
            for row in range(self._model.rowCount(parent)):
                index = self._model.index(row, 0, parent)
                if self._tree.isExpanded(index):
                    ids.add(index.data(ID_ROLE))
                walk(index)

        walk(QModelIndex())
        return ids

    def _restore_expansion(self, ids: set[str], *, expand_all: bool) -> None:
        def walk(parent: QModelIndex) -> None:
            for row in range(self._model.rowCount(parent)):
                index = self._model.index(row, 0, parent)
                if expand_all or index.data(ID_ROLE) in ids:
                    self._tree.expand(index)
                walk(index)

        walk(QModelIndex())

    def _default_show_error(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()
```

`test_expansion_survives_rebuild`: первая сборка раскрывает всё (`expand_all`), дальше —
по запомненным id; поэтому после `collapse` + `rebuild` группа остаётся свёрнутой.

- [ ] **Step 8: Прогнать**

Run: `uv run pytest tests/ui/test_edt_tree_model.py tests/ui/test_edt_monitor.py tests/ui/test_edt_view.py tests/ui/test_rail_icons.py tests/unit/test_edt_workspace.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 9: Commit**

```bash
git add src/onecstarter/ui/rail_icons.py src/onecstarter/ui/edt src/onecstarter/services/edt.py tests/ui/test_edt_tree_model.py tests/ui/test_edt_monitor.py tests/ui/test_edt_view.py tests/ui/test_rail_icons.py
git commit -m "feat(ui): раздел EDT — значок, модель дерева, монитор, каркас вьюхи с запуском и F5"
```

---

### Task 15: UI — диалог записи с фасадами памяти и языка

**Files:**
- Create: `src/onecstarter/ui/edt/dialog.py`
- Create: `tests/ui/test_edt_dialog.py`

**Interfaces:**
- Consumes: `EdtProject`, `EdtInstallation`, `LANGUAGES`, `split_vm_args`, `join_vm_args` (Tasks 1–3); `russian_button_box`, `ButtonKind` (`ui/dialogs/buttons.py`).
- Produces: `EdtProjectDialog(project: EdtProject | None, installed: Sequence[EdtInstallation], *, defaults: DialogDefaults, choose_directory: Callable[[], str] = browse_for_directory, parent=None)`; `DialogDefaults(max_heap_mb: int, language: str, group_id: str | None)`; `dialog.result_project() -> EdtProject`; `dialog.ok_button()`, `dialog.error_text()`; аксессоры полей `name_edit()`, `workspace_edit()`, `project_dir_edit()`, `version_combo()`, `jvm_edit()`, `heap_combo()`, `language_combo()`, `extra_edit()`, `jvm_note()`; константы `HEAP_CHOICES = (2048, 4096, 8192, 12288, 16384)`, `NOT_INSTALLED_MARK = " (не установлена)"`.

- [ ] **Step 1: Написать падающие тесты**

`tests/ui/test_edt_dialog.py`:

```python
"""Диалог записи EDT: поля, фасады vm_args, версия не из списка, проверки (спека §7)."""

from pathlib import Path

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.ui.edt.dialog import (
    HEAP_CHOICES,
    NOT_INSTALLED_MARK,
    DialogDefaults,
    EdtProjectDialog,
)

JDK = Path(r"C:\jdk17\bin")
INSTALLED = [
    EdtInstallation("2026.1.2+2", Path(r"C:\e26\1cedt.exe"), JDK, "", 17, "products.json"),
    EdtInstallation("2025.2.6+4", Path(r"C:\e25\1cedt.exe"), None, "", 17, ""),
]
DEFAULTS = DialogDefaults(max_heap_mb=8192, language="", group_id=None)


def _new(qtbot, choose: str = "") -> EdtProjectDialog:  # type: ignore[no-untyped-def]
    dialog = EdtProjectDialog(None, INSTALLED, defaults=DEFAULTS, choose_directory=lambda: choose)
    qtbot.addWidget(dialog)
    return dialog


def test_new_dialog_prefills_defaults(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    assert dialog.windowTitle() == "Новый проект EDT"
    assert dialog.heap_combo().currentText() == "8192"
    assert dialog.language_combo().currentData() == ""
    assert [dialog.version_combo().itemText(i) for i in range(dialog.version_combo().count())] == [
        "2026.1.2+2",
        "2025.2.6+4",
    ]
    assert dialog.ok_button().isEnabled() is False
    assert dialog.jvm_note().text() == f"JVM установки: {JDK} (products.json)"


def test_result_project_joins_vm_args(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("Розница")
    dialog.workspace_edit().setText(r"D:\edt\retail")
    dialog.project_dir_edit().setText(r"D:\edt\retail\retail")
    dialog.heap_combo().setCurrentText("4096")
    dialog.language_combo().setCurrentIndex(1)  # ru
    dialog.extra_edit().setText("-Dx=1")
    assert dialog.ok_button().isEnabled() is True
    project = dialog.result_project()
    assert project == EdtProject(
        id="",
        name="Розница",
        workspace=r"D:\edt\retail",
        project_dir=r"D:\edt\retail\retail",
        edt_version="2026.1.2+2",
        jvm_dir="",
        vm_args="-Dx=1 -Xmx4096m -Duser.language=ru",
        group_id=None,
    )


def test_empty_heap_means_no_xmx(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText(r"D:\a")
    dialog.heap_combo().setCurrentText("")
    assert dialog.result_project().vm_args == ""


def test_garbage_heap_disables_ok(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText(r"D:\a")
    dialog.heap_combo().setCurrentText("много")
    assert dialog.ok_button().isEnabled() is False
    assert dialog.error_text() == "Память — целое число мегабайт"


def test_relative_workspace_disables_ok(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText(r"edt\a")
    assert dialog.ok_button().isEnabled() is False
    assert dialog.error_text() == "Путь workspace должен быть абсолютным"


def test_edit_splits_existing_vm_args_and_keeps_group(qtbot) -> None:  # type: ignore[no-untyped-def]
    project = EdtProject(
        id="p1",
        name="Розница",
        workspace=r"D:\edt\retail",
        edt_version="2025.2.6+4",
        jvm_dir=r"D:\my\bin",
        vm_args="-Dnative=true -Xmx12288m -Duser.language=en",
        group_id="g1",
    )
    dialog = EdtProjectDialog(project, INSTALLED, defaults=DEFAULTS, choose_directory=lambda: "")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Проект EDT — Розница"
    assert dialog.heap_combo().currentText() == "12288"
    assert dialog.language_combo().currentData() == "en"
    assert dialog.extra_edit().text() == "-Dnative=true"
    assert dialog.jvm_edit().text() == r"D:\my\bin"
    assert dialog.version_combo().currentText() == "2025.2.6+4"
    assert dialog.jvm_note().text() == "JVM установки: не найдена"
    result = dialog.result_project()
    assert result.id == "p1"
    assert result.group_id == "g1"
    assert result.vm_args == "-Dnative=true -Xmx12288m -Duser.language=en"


def test_unknown_version_stays_selectable_with_mark(qtbot) -> None:  # type: ignore[no-untyped-def]
    project = EdtProject(id="p1", name="Старая", workspace=r"D:\a", edt_version="2024.2.6+7")
    dialog = EdtProjectDialog(project, INSTALLED, defaults=DEFAULTS, choose_directory=lambda: "")
    qtbot.addWidget(dialog)
    assert dialog.version_combo().currentText() == "2024.2.6+7" + NOT_INSTALLED_MARK
    assert dialog.result_project().edt_version == "2024.2.6+7"


def test_browse_fills_workspace(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot, choose=r"D:\picked")
    dialog.workspace_browse().click()
    assert dialog.workspace_edit().text() == r"D:\picked"


def test_browse_cancel_keeps_field(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot, choose="")
    dialog.workspace_edit().setText(r"D:\keep")
    dialog.workspace_browse().click()
    assert dialog.workspace_edit().text() == r"D:\keep"


def test_heap_choices_listed() -> None:
    assert HEAP_CHOICES == (2048, 4096, 8192, 12288, 16384)
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_edt_dialog.py -q`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать**

`src/onecstarter/ui/edt/dialog.py`:

```python
"""Диалог записи раздела «EDT» (спека v3, §7).

Хранится одна строка `vm_args`; память и язык — фасады над ней
(`domain.edt.split_vm_args`/`join_vm_args`), как «Отредактировать как
параметры Java VM…» у EDT Start. Проверки до сохранения: имя и workspace
непусты, workspace абсолютен, память — целое (пусто — без `-Xmx`).
"""  # noqa: RUF002

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt import (
    LANGUAGES,
    EdtInstallation,
    EdtProject,
    join_vm_args,
    split_vm_args,
)
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

HEAP_CHOICES = (2048, 4096, 8192, 12288, 16384)
NOT_INSTALLED_MARK = " (не установлена)"
_HEAP_ERROR = "Память — целое число мегабайт"


@dataclass(frozen=True)
class DialogDefaults:
    max_heap_mb: int
    language: str
    group_id: str | None


def browse_for_directory() -> str:
    """Системный диалог каталога; пустая строка — отмена (как в `ui/servers/dialog.py`)."""
    return QFileDialog.getExistingDirectory()


class EdtProjectDialog(QDialog):
    def __init__(
        self,
        project: EdtProject | None,
        installed: Sequence[EdtInstallation],
        *,
        defaults: DialogDefaults,
        choose_directory: Callable[[], str] = browse_for_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._installed = list(installed)
        self._defaults = defaults
        self._choose_directory = choose_directory
        self.setWindowTitle(f"Проект EDT — {project.name}" if project else "Новый проект EDT")

        self._name = QLineEdit(project.name if project else "")
        self._workspace = QLineEdit(project.workspace if project else "")
        self._workspace_browse = QPushButton("Обзор…")
        self._workspace_browse.clicked.connect(lambda: self._browse_into(self._workspace))
        self._project_dir = QLineEdit(project.project_dir if project else "")
        self._project_dir.setPlaceholderText("пусто — редакторы получают workspace")
        self._project_dir_browse = QPushButton("Обзор…")
        self._project_dir_browse.clicked.connect(lambda: self._browse_into(self._project_dir))

        self._version = QComboBox()
        for installation in self._installed:
            self._version.addItem(installation.version, installation.version)
        current = project.edt_version if project else ""
        if current and self._version.findData(current) < 0:
            self._version.addItem(current + NOT_INSTALLED_MARK, current)
        if current:
            self._version.setCurrentIndex(self._version.findData(current))
        self._version.currentIndexChanged.connect(self._refresh_jvm_note)

        self._jvm = QLineEdit(project.jvm_dir if project else "")
        self._jvm.setPlaceholderText("пусто — JVM установки")
        self._jvm_browse = QPushButton("Обзор…")
        self._jvm_browse.clicked.connect(lambda: self._browse_into(self._jvm))
        self._jvm_note = QLabel("")
        self._jvm_note.setObjectName("SettingsNote")

        parts = split_vm_args(project.vm_args) if project else None
        self._heap = QComboBox()
        self._heap.setEditable(True)
        for choice in HEAP_CHOICES:
            self._heap.addItem(str(choice))
        heap = parts.max_heap_mb if parts else defaults.max_heap_mb
        self._heap.setCurrentText("" if heap is None else str(heap))
        self._heap.currentTextChanged.connect(self._refresh_state)

        self._language = QComboBox()
        for code, label in LANGUAGES:
            self._language.addItem(label, code)
        language = (parts.language if parts else defaults.language) or ""
        index = self._language.findData(language)
        self._language.setCurrentIndex(index if index >= 0 else 0)

        self._extra = QLineEdit(" ".join(parts.rest) if parts else "")
        self._extra.setPlaceholderText("прочие параметры JVM")

        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Имя", self._name)
        form.addRow("Workspace", self._with_browse(self._workspace, self._workspace_browse))
        form.addRow("Каталог проекта", self._with_browse(self._project_dir, self._project_dir_browse))
        form.addRow("Версия EDT", self._version)
        form.addRow("JVM (каталог bin)", self._with_browse(self._jvm, self._jvm_browse))
        form.addRow("", self._jvm_note)
        heap_row = QWidget()
        heap_layout = QHBoxLayout(heap_row)
        heap_layout.setContentsMargins(0, 0, 0, 0)
        heap_layout.addWidget(self._heap, 1)
        heap_layout.addWidget(QLabel("МБ"))
        form.addRow("Память", heap_row)
        form.addRow("Язык интерфейса", self._language)
        form.addRow("Прочие параметры JVM", self._extra)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)

        for edit in (self._name, self._workspace):
            edit.textChanged.connect(self._refresh_state)
        self._refresh_jvm_note()
        self._refresh_state()

    # --- результат --------------------------------------------------------

    def result_project(self) -> EdtProject:
        heap_text = self._heap.currentText().strip()
        heap = int(heap_text) if heap_text else None
        return EdtProject(
            id=self._project.id if self._project else "",
            name=self._name.text().strip(),
            workspace=self._workspace.text().strip(),
            project_dir=self._project_dir.text().strip(),
            edt_version=str(self._version.currentData() or ""),
            jvm_dir=self._jvm.text().strip(),
            vm_args=join_vm_args(heap, str(self._language.currentData() or ""), self._extra.text().split()),
            group_id=self._project.group_id if self._project else self._defaults.group_id,
        )

    # --- состояние --------------------------------------------------------

    def _refresh_state(self, *_args: object) -> None:
        self._error.setText(self._error_for_fields())
        self._buttons.buttons()[0].setEnabled(not self._error.text())

    def _error_for_fields(self) -> str:
        if not self._name.text().strip():
            return "Имя не задано"
        workspace = self._workspace.text().strip()
        if not workspace:
            return "Workspace не задан"
        if not os.path.isabs(workspace):
            return "Путь workspace должен быть абсолютным"
        heap = self._heap.currentText().strip()
        if heap and not heap.isdigit():
            return _HEAP_ERROR
        return ""

    def _refresh_jvm_note(self, *_args: object) -> None:
        version = self._version.currentData()
        for installation in self._installed:
            if installation.version == version:
                if installation.jvm_dir is None:
                    self._jvm_note.setText("JVM установки: не найдена")
                else:
                    self._jvm_note.setText(
                        f"JVM установки: {installation.jvm_dir} ({installation.jvm_source})"
                    )
                return
        self._jvm_note.setText("JVM установки: не найдена")

    def _browse_into(self, edit: QLineEdit) -> None:
        chosen = self._choose_directory()
        if chosen:
            edit.setText(chosen)

    @staticmethod
    def _with_browse(edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    # --- доступ для тестов ------------------------------------------------

    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]

    def error_text(self) -> str:
        return self._error.text()

    def name_edit(self) -> QLineEdit:
        return self._name

    def workspace_edit(self) -> QLineEdit:
        return self._workspace

    def workspace_browse(self) -> QPushButton:
        return self._workspace_browse

    def project_dir_edit(self) -> QLineEdit:
        return self._project_dir

    def version_combo(self) -> QComboBox:
        return self._version

    def jvm_edit(self) -> QLineEdit:
        return self._jvm

    def jvm_note(self) -> QLabel:
        return self._jvm_note

    def heap_combo(self) -> QComboBox:
        return self._heap

    def language_combo(self) -> QComboBox:
        return self._language

    def extra_edit(self) -> QLineEdit:
        return self._extra
```

Примечание к `_refresh_jvm_note`: в тесте `test_new_dialog_prefills_defaults` первой в списке
идёт 2026.1.2+2 с JDK — подпись `JVM установки: C:\jdk17\bin (products.json)`. В тесте
редактирования выбрана 2025.2.6+4 без JDK — «не найдена».

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/ui/test_edt_dialog.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/ui/edt/dialog.py tests/ui/test_edt_dialog.py
git commit -m "feat(ui): диалог записи EDT — версия, JVM, память и язык как фасады над vm_args"
```

---

### Task 16: UI — контекстное меню, группы, перетаскивание

**Files:**
- Create: `src/onecstarter/ui/edt/group_dialog.py`
- Modify: `src/onecstarter/ui/edt/view.py`
- Create: `tests/ui/test_edt_group_dialog.py`
- Modify: `tests/ui/test_edt_view.py`

**Interfaces:**
- Consumes: `EdtView` (Task 14), `EdtProjectDialog`, `DialogDefaults`, `browse_for_directory` (Task 15), `EdtWorkspace` (Tasks 12–13), `EditorKind`, `EDITOR_LABELS` (Task 8), `ask_confirmation` (`ui/dialogs/buttons.py`), `dropped_directory` (`ui/dialogs/infobase.py`).
- Produces: `EdtGroupDialog(name: str, *, title: str, parent=None)` с `name_text()`, `ok_button()`; в `EdtView`: новые параметры конструктора `dialog_defaults: Callable[[], tuple[int, str]] = lambda: (8192, "")` (память, язык для новых записей), `confirm: Callable[[QWidget, str, str], bool] = ask_confirmation`, `choose_directory: Callable[[], str] = browse_for_directory`; методы `build_menu(kind: str | None, item_id: str | None) -> QMenu`, `add_project(group_id: str | None, workspace: str = "")`, `edit_project(project_id)`, `remove_project(project_id)`, `add_group(parent_id)`, `rename_group(group_id)`, `remove_group(group_id)`, `open_in_editor(project_id, kind)`, `open_folder(project_id)`, `handle_drop(source: tuple[str, str], target: tuple[str, str] | None, where: DropTarget)`, `add_project_from_directory(directory: str, target: tuple[str, str] | None)`; `DropTarget(Enum)` с `BEFORE`, `INTO`, `AFTER`; тексты пунктов — константы `MENU_OPEN_EDT = "Открыть в EDT"`, `MENU_OPEN_EXPLORER = "Открыть в Проводнике"`, `MENU_ADD = "Добавить…"`, `MENU_EDIT = "Изменить…"`, `MENU_REMOVE = "Удалить"`, `MENU_ADD_GROUP = "Создать группу"`, `MENU_RENAME_GROUP = "Переименовать группу"`, `MENU_REMOVE_GROUP = "Удалить группу"`, `MENU_IMPORT = "Импорт из EDT Start…"`; пункты редакторов — `f"Открыть в {EDITOR_LABELS[kind]}"`.

- [ ] **Step 1: Диалог группы — тест и реализация**

`tests/ui/test_edt_group_dialog.py`:

```python
from onecstarter.ui.edt.group_dialog import EdtGroupDialog


def test_new_group_dialog(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtGroupDialog("", title="Новая группа")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Новая группа"
    assert dialog.ok_button().isEnabled() is False
    dialog.name_edit().setText("  2025 ")
    assert dialog.ok_button().isEnabled() is True
    assert dialog.name_text() == "2025"


def test_rename_dialog_prefills(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtGroupDialog("Розница", title="Переименование группы")
    qtbot.addWidget(dialog)
    assert dialog.name_edit().text() == "Розница"
    assert dialog.ok_button().isEnabled() is True
```

`src/onecstarter/ui/edt/group_dialog.py`:

```python
"""Имя группы раздела «EDT» — одно поле с русскими кнопками (спека §7)."""

from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box


class EdtGroupDialog(QDialog):
    def __init__(self, name: str, *, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._name = QLineEdit(name)
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow("Имя группы", self._name)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._buttons)
        self._name.textChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self, *_args: object) -> None:
        self.ok_button().setEnabled(bool(self._name.text().strip()))

    def name_text(self) -> str:
        return self._name.text().strip()

    def name_edit(self) -> QLineEdit:
        return self._name

    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]
```

Run: `uv run pytest tests/ui/test_edt_group_dialog.py -q` — зелёное.

- [ ] **Step 2: Меню и операции — падающие тесты**

Добавить в `tests/ui/test_edt_view.py`:

```python
from PySide6.QtWidgets import QMenu

from onecstarter.platform_1c.editors import EditorKind
from onecstarter.ui.edt.view import (
    MENU_ADD,
    MENU_ADD_GROUP,
    MENU_EDIT,
    MENU_IMPORT,
    MENU_OPEN_EDT,
    MENU_OPEN_EXPLORER,
    MENU_REMOVE,
    MENU_REMOVE_GROUP,
    MENU_RENAME_GROUP,
    DropTarget,
)


def _actions(menu: QMenu) -> dict[str, bool]:
    return {a.text(): a.isEnabled() for a in menu.actions() if not a.isSeparator()}


def test_project_menu_items_and_editor_state(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    actions = _actions(view.build_menu("project", p.id))
    assert actions[MENU_OPEN_EDT] is True
    assert actions["Открыть в VS Code"] is False  # редактор не найден
    assert actions["Открыть в Antigravity"] is False
    assert actions[MENU_OPEN_EXPLORER] is True
    assert {MENU_ADD, MENU_EDIT, MENU_REMOVE, MENU_ADD_GROUP, MENU_IMPORT} <= actions.keys()
    tooltips = {a.text(): a.toolTip() for a in view.build_menu("project", p.id).actions()}
    assert tooltips["Открыть в VS Code"] == "Не найден — укажите путь в Настройках"


def test_project_menu_open_edt_disabled_when_not_installed(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a", edt_version="2024.2.6+7")
    view = harness.view()
    qtbot.addWidget(view)
    menu = view.build_menu("project", p.id)
    action = next(a for a in menu.actions() if a.text() == MENU_OPEN_EDT)
    assert action.isEnabled() is False
    assert action.toolTip() == "EDT 2024.2.6+7 не найден"


def test_editor_enabled_when_found_and_opens_folder(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    harness.editor = EditorResolution(Path(r"C:\code\code.cmd"), "PATH", "")
    p = _add(harness, "a", project_dir=r"D:\edt\a\proj")
    view = harness.view()
    qtbot.addWidget(view)
    assert _actions(view.build_menu("project", p.id))["Открыть в VS Code"] is True
    view.open_in_editor(p.id, EditorKind.VSCODE)
    assert harness.spawned[-1].arguments == '"D:\\edt\\a\\proj"'
    view.open_folder(p.id)
    assert harness.opened == [r"D:\edt\a\proj"]


def test_group_and_empty_menus(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    view = harness.view()
    qtbot.addWidget(view)
    group_actions = _actions(view.build_menu("group", g.id))
    assert {MENU_ADD, MENU_ADD_GROUP, MENU_RENAME_GROUP, MENU_REMOVE_GROUP} <= group_actions.keys()
    assert MENU_OPEN_EDT not in group_actions
    empty_actions = _actions(view.build_menu(None, None))
    assert set(empty_actions) == {MENU_ADD, MENU_ADD_GROUP, MENU_IMPORT}


def test_add_project_via_dialog(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    view = harness.view()
    qtbot.addWidget(view)

    def fake_exec(dialog):  # type: ignore[no-untyped-def]
        dialog.name_edit().setText("Новая")
        dialog.workspace_edit().setText(r"D:\edt\new")
        return True

    monkeypatch.setattr(view, "_run_dialog", fake_exec)
    view.add_project(g.id)
    [project] = harness.workspace.projects()
    assert project.name == "Новая"
    assert project.group_id == g.id
    assert project.vm_args == "-Xmx8192m"  # умолчание из dialog_defaults


def test_edit_and_remove_project(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)

    def rename(dialog):  # type: ignore[no-untyped-def]
        dialog.name_edit().setText("b")
        return True

    monkeypatch.setattr(view, "_run_dialog", rename)
    view.edit_project(p.id)
    assert harness.workspace.project(p.id).name == "b"
    confirmed: list[str] = []
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: confirmed.append(text) or True)
    view.remove_project(p.id)
    assert harness.workspace.projects() == []
    assert confirmed == ["Удалить запись «b»? Каталоги на диске не трогаются."]


def test_remove_declined_keeps_project(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: False)
    view.remove_project(p.id)
    assert len(harness.workspace.projects()) == 1


def test_group_lifecycle_via_view(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    view = harness.view()
    qtbot.addWidget(view)
    names = iter(["2025", "Опт"])

    def name_dialog(dialog):  # type: ignore[no-untyped-def]
        dialog.name_edit().setText(next(names))
        return True

    monkeypatch.setattr(view, "_run_dialog", name_dialog)
    view.add_group(None)
    [g] = harness.workspace.groups()
    assert g.name == "2025"
    view.rename_group(g.id)
    assert harness.workspace.groups()[0].name == "Опт"
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    view.remove_group(g.id)
    assert harness.workspace.groups() == []


def test_handle_drop_moves_project_into_group_and_reorders(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    a = _add(harness, "a")
    b = _add(harness, "b")
    view = harness.view()
    qtbot.addWidget(view)
    view.handle_drop(("project", a.id), ("group", g.id), DropTarget.INTO)
    assert harness.workspace.project(a.id).group_id == g.id
    view.handle_drop(("project", a.id), ("project", b.id), DropTarget.BEFORE)
    assert [p.id for p in harness.workspace.children(None)[1]] == [a.id, b.id]
    view.handle_drop(("project", a.id), ("project", b.id), DropTarget.AFTER)
    assert [p.id for p in harness.workspace.children(None)[1]] == [b.id, a.id]
    view.handle_drop(("project", a.id), None, DropTarget.INTO)
    assert harness.workspace.project(a.id).group_id is None


def test_handle_drop_group_into_descendant_shows_error(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    root = harness.workspace.add_group("root", None)
    child = harness.workspace.add_group("child", root.id)
    view = harness.view()
    qtbot.addWidget(view)
    view.handle_drop(("group", root.id), ("group", child.id), DropTarget.INTO)
    assert harness.errors == ["Группу нельзя переместить внутрь самой себя"]


def test_directory_drop_opens_prefilled_dialog(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    g = harness.workspace.add_group("2025", None)
    view = harness.view()
    qtbot.addWidget(view)
    seen: list[tuple[str, str]] = []

    def capture(dialog):  # type: ignore[no-untyped-def]
        seen.append((dialog.workspace_edit().text(), dialog.name_edit().text()))
        return False

    monkeypatch.setattr(view, "_run_dialog", capture)
    view.add_project_from_directory(r"D:\edt\dropped", ("group", g.id))
    assert seen == [(r"D:\edt\dropped", "dropped")]
    assert harness.workspace.projects() == []


def test_delete_key_removes_current_with_confirm(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    _select(view, p.id)
    monkeypatch.setattr(view, "_confirm", lambda parent, title, text: True)
    qtbot.keyClick(view.tree(), Qt.Key.Key_Delete)
    assert harness.workspace.projects() == []
```

- [ ] **Step 3: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_edt_view.py -q`
Expected: `ImportError` на `MENU_ADD`.

- [ ] **Step 4: Реализовать**

В `src/onecstarter/ui/edt/view.py`:

Импорты добавить:

```python
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QDialog, QMenu

from onecstarter.domain.edt import EdtProject
from onecstarter.platform_1c.editors import EDITOR_LABELS, EditorKind
from onecstarter.ui.dialogs.buttons import ask_confirmation
from onecstarter.ui.dialogs.infobase import dropped_directory
from onecstarter.ui.edt.dialog import DialogDefaults, EdtProjectDialog, browse_for_directory
from onecstarter.ui.edt.group_dialog import EdtGroupDialog
from onecstarter.ui.edt.tree_model import KIND_GROUP
```

Константы после импортов:

```python
MENU_OPEN_EDT = "Открыть в EDT"
MENU_OPEN_EXPLORER = "Открыть в Проводнике"
MENU_ADD = "Добавить…"
MENU_EDIT = "Изменить…"
MENU_REMOVE = "Удалить"
MENU_ADD_GROUP = "Создать группу"
MENU_RENAME_GROUP = "Переименовать группу"
MENU_REMOVE_GROUP = "Удалить группу"
MENU_IMPORT = "Импорт из EDT Start…"
NOT_INSTALLED_HINT = "EDT {version} не найден"


class DropTarget(Enum):
    BEFORE = "before"
    INTO = "into"
    AFTER = "after"
```

`_EdtTree` — расширить (перетаскивание по образцу `_BasesTree`, докстринг которого
объясняет, почему событие в конце `ignore()`-ится, а не отдаётся `super()`):

```python
class _EdtTree(QTreeView):
    def __init__(self, view: "EdtView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._view._show_menu)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._view._launch_index(self.currentIndex())
            return
        if event.key() == Qt.Key.Key_F5:
            self._view.refresh_all()
            return
        if event.key() == Qt.Key.Key_Delete:
            self._view._remove_current()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        position = event.position().toPoint()
        index = self.indexAt(position)
        target = self._row_at(index)
        directory = dropped_directory(event.mimeData())
        if directory is not None:
            self._view.add_project_from_directory(directory, target)
            event.acceptProposedAction()
            return
        source = self._row_at(self.currentIndex())
        if source is not None:
            self._view.handle_drop(source, target, self._where_at(index, position.y()))
        event.ignore()

    @staticmethod
    def _row_at(index: QModelIndex) -> tuple[str, str] | None:
        if not index.isValid():
            return None
        first = index.siblingAtColumn(0)
        kind, item_id = first.data(KIND_ROLE), first.data(ID_ROLE)
        return (kind, item_id) if isinstance(kind, str) and isinstance(item_id, str) else None

    def _where_at(self, index: QModelIndex, y: int) -> DropTarget:
        if not index.isValid():
            return DropTarget.INTO
        rect = self.visualRect(index)
        margin = max(1, rect.height() // 4)
        if y - rect.top() < margin:
            return DropTarget.BEFORE
        if rect.bottom() - y < margin:
            return DropTarget.AFTER
        return DropTarget.INTO
```

`EdtView.__init__` — новые параметры после `show_error`:

```python
        dialog_defaults: Callable[[], tuple[int, str]] = lambda: (8192, ""),
        confirm: Callable[[QWidget, str, str], bool] = ask_confirmation,
        choose_directory: Callable[[], str] = browse_for_directory,
```

и поля `self._dialog_defaults = dialog_defaults`, `self._confirm = confirm`,
`self._choose_directory = choose_directory`. Кнопка баннера: `self._banner_button.clicked.connect(self.import_from_edtstart)` — сам метод появится в Task 17; до него поставить заглушку `def import_from_edtstart(self) -> None: return None`.

Методы `EdtView` (раздел «меню и операции»):

```python
    # --- меню ---------------------------------------------------------------

    def build_menu(self, kind: str | None, item_id: str | None) -> QMenu:
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if kind == KIND_PROJECT and item_id is not None:
            self._fill_project_menu(menu, self._workspace.project(item_id))
            menu.addSeparator()
            group_id = self._workspace.project(item_id).group_id
        elif kind == KIND_GROUP and item_id is not None:
            group_id = item_id
        else:
            group_id = None
        menu.addAction(MENU_ADD, lambda: self.add_project(group_id))
        if kind == KIND_PROJECT and item_id is not None:
            menu.addAction(MENU_EDIT, lambda: self.edit_project(item_id))
            menu.addAction(MENU_REMOVE, lambda: self.remove_project(item_id))
        menu.addSeparator()
        menu.addAction(MENU_ADD_GROUP, lambda: self.add_group(group_id))
        if kind == KIND_GROUP and item_id is not None:
            menu.addAction(MENU_RENAME_GROUP, lambda: self.rename_group(item_id))
            menu.addAction(MENU_REMOVE_GROUP, lambda: self.remove_group(item_id))
        if kind != KIND_GROUP:
            menu.addSeparator()
            menu.addAction(MENU_IMPORT, self.import_from_edtstart)
        return menu

    def _fill_project_menu(self, menu: QMenu, project: EdtProject) -> None:
        status = self._workspace.status(project.id)
        open_edt = menu.addAction(MENU_OPEN_EDT, lambda: self.launch_id(project.id))
        if not status.installed and status.running_pid is None:
            open_edt.setEnabled(False)
            open_edt.setToolTip(NOT_INSTALLED_HINT.format(version=project.edt_version or "—"))
        for kind in EditorKind:
            resolution = self._workspace.editor(kind)
            action = menu.addAction(
                f"Открыть в {EDITOR_LABELS[kind]}",
                lambda k=kind: self.open_in_editor(project.id, k),
            )
            if resolution.path is None:
                action.setEnabled(False)
                action.setToolTip(resolution.note)
        menu.addAction(MENU_OPEN_EXPLORER, lambda: self.open_folder(project.id))

    def _show_menu(self, position: QPoint) -> None:
        index = self._tree.indexAt(position)
        row = _EdtTree._row_at(index)
        if row is not None:
            self._tree.setCurrentIndex(index)
        menu = self.build_menu(*(row or (None, None)))
        menu.exec(self._tree.viewport().mapToGlobal(position))

    # --- операции -------------------------------------------------------------

    def _run_dialog(self, dialog: QDialog) -> bool:
        """Точка подмены для тестов: показать модально, вернуть «принят»."""
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _defaults(self, group_id: str | None) -> DialogDefaults:
        heap, language = self._dialog_defaults()
        return DialogDefaults(max_heap_mb=heap, language=language, group_id=group_id)

    def add_project(self, group_id: str | None, workspace: str = "") -> None:
        dialog = EdtProjectDialog(
            None,
            self._workspace.installations(),
            defaults=self._defaults(group_id),
            choose_directory=self._choose_directory,
            parent=self,
        )
        if workspace:
            dialog.workspace_edit().setText(workspace)
            dialog.name_edit().setText(Path(workspace).name)
        if not self._run_dialog(dialog):
            return
        self._apply(lambda: self._workspace.add_project(dialog.result_project()))

    def add_project_from_directory(self, directory: str, target: tuple[str, str] | None) -> None:
        self.add_project(self._group_of(target), directory)

    def edit_project(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        dialog = EdtProjectDialog(
            project,
            self._workspace.installations(),
            defaults=self._defaults(project.group_id),
            choose_directory=self._choose_directory,
            parent=self,
        )
        if self._run_dialog(dialog):
            self._apply(lambda: self._workspace.update_project(dialog.result_project()))

    def remove_project(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        question = f"Удалить запись «{project.name}»? Каталоги на диске не трогаются."
        if self._confirm(self, "Удаление записи", question):
            self._apply(lambda: self._workspace.remove_project(project_id))

    def add_group(self, parent_id: str | None) -> None:
        dialog = EdtGroupDialog("", title="Новая группа", parent=self)
        if self._run_dialog(dialog):
            self._apply(lambda: self._workspace.add_group(dialog.name_text(), parent_id))

    def rename_group(self, group_id: str) -> None:
        current = next(g for g in self._workspace.groups() if g.id == group_id)
        dialog = EdtGroupDialog(current.name, title="Переименование группы", parent=self)
        if self._run_dialog(dialog):
            self._apply(lambda: self._workspace.rename_group(group_id, dialog.name_text()))

    def remove_group(self, group_id: str) -> None:
        current = next(g for g in self._workspace.groups() if g.id == group_id)
        question = f"Удалить группу «{current.name}»? Её содержимое поднимется на уровень выше."
        if self._confirm(self, "Удаление группы", question):
            self._apply(lambda: self._workspace.remove_group(group_id))

    def open_in_editor(self, project_id: str, kind: EditorKind) -> None:
        self._apply(lambda: self._workspace.open_in_editor(project_id, kind), rebuild=False)

    def open_folder(self, project_id: str) -> None:
        self._apply(lambda: self._workspace.open_folder(project_id), rebuild=False)

    def handle_drop(
        self,
        source: tuple[str, str],
        target: tuple[str, str] | None,
        where: DropTarget,
    ) -> None:
        """Перевод «куда бросили» в `move_project`/`move_group` координатора.

        Позиция считается среди соседей того же вида: запись, брошенная
        относительно группы, встаёт первой в родителе этой группы; группа,
        брошенная относительно записи, — последней в группе этой записи.
        """
        kind, item_id = source
        if target is not None and target == source:
            return
        parent, position = self._drop_slot(kind, item_id, target, where)
        if kind == KIND_PROJECT:
            self._apply(lambda: self._workspace.move_project(item_id, parent, position))
        else:
            self._apply(lambda: self._workspace.move_group(item_id, parent, position))

    def _drop_slot(
        self,
        kind: str,
        item_id: str,
        target: tuple[str, str] | None,
        where: DropTarget,
    ) -> tuple[str | None, int]:
        """Родитель и позиция среди соседей того же вида.

        Координатор сперва вынимает источник из списка, поэтому при переносе
        вниз внутри одного родителя позиция цели сдвигается на единицу —
        учтено через `ids.index(item_id) < index`.
        """
        end = 1_000_000
        if target is None:
            return None, end
        target_kind, target_id = target
        if target_kind == KIND_GROUP:
            if where is DropTarget.INTO:
                return target_id, end
            group = next(g for g in self._workspace.groups() if g.id == target_id)
            if kind != KIND_GROUP:
                return group.parent_id, 0
            ids = [g.id for g in self._workspace.children(group.parent_id)[0]]
            parent = group.parent_id
        else:
            project = self._workspace.project(target_id)
            if kind != KIND_PROJECT:
                return project.group_id, end
            ids = [p.id for p in self._workspace.children(project.group_id)[1]]
            parent = project.group_id
        index = ids.index(target_id)
        position = index + (0 if where is DropTarget.BEFORE else 1)
        if item_id in ids and ids.index(item_id) < index:
            position -= 1
        return parent, position

    def _group_of(self, target: tuple[str, str] | None) -> str | None:
        if target is None:
            return None
        kind, item_id = target
        if kind == KIND_GROUP:
            return item_id
        return self._workspace.project(item_id).group_id

    def _remove_current(self) -> None:
        current = self.current()
        if current is None:
            return
        kind, item_id = current
        if kind == KIND_PROJECT:
            self.remove_project(item_id)
        else:
            self.remove_group(item_id)

    def _apply(self, operation: Callable[[], object], *, rebuild: bool = True) -> None:
        try:
            operation()
        except ServicesError as error:
            self._show_error(str(error))
            return
        if rebuild:
            self.rebuild()
```

- [ ] **Step 5: Прогнать**

Run: `uv run pytest tests/ui/test_edt_view.py tests/ui/test_edt_group_dialog.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/ui/edt/view.py src/onecstarter/ui/edt/group_dialog.py tests/ui/test_edt_view.py tests/ui/test_edt_group_dialog.py
git commit -m "feat(ui): раздел EDT — контекстное меню, группы, перетаскивание, каталог из Проводника"
```

---

### Task 17: UI — импорт из EDT Start и баннер пустого списка

**Files:**
- Create: `src/onecstarter/ui/edt/import_dialog.py`
- Modify: `src/onecstarter/ui/edt/view.py`
- Create: `tests/ui/test_edt_import_dialog.py`
- Modify: `tests/ui/test_edt_view.py`

**Interfaces:**
- Consumes: `ImportCandidate` (Task 6); `EdtWorkspace.import_candidates()`, `import_projects()`, `edtstart_available()` (Task 13); `EdtView` (Tasks 14, 16).
- Produces: `EdtImportDialog(candidates: Sequence[ImportCandidate], parent=None)` с `selected() -> list[ImportCandidate]`, `list_widget()`, `ok_button()`; константа `UNKNOWN_VERSION_MARK = "версия неизвестна"`; `EdtView.import_from_edtstart()`; новый параметр `EdtView(show_info: Callable[[str], None] | None = None)`.

- [ ] **Step 1: Диалог импорта — падающие тесты**

`tests/ui/test_edt_import_dialog.py`:

```python
from PySide6.QtCore import Qt

from onecstarter.domain.edt import EdtProject, ImportCandidate
from onecstarter.ui.edt.import_dialog import UNKNOWN_VERSION_MARK, EdtImportDialog

A = ImportCandidate(EdtProject("1", "(2025) А", r"D:\edt\a", edt_version="2025.2.6+4"), True)
B = ImportCandidate(EdtProject("2", "Б", r"D:\edt\b"), False)


def test_all_checked_by_default_with_columns(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtImportDialog([A, B])
    qtbot.addWidget(dialog)
    items = [dialog.list_widget().item(i) for i in range(2)]
    assert [i.checkState() for i in items] == [Qt.CheckState.Checked, Qt.CheckState.Checked]
    assert items[0].text() == "(2025) А — D:\\edt\\a — 2025.2.6+4"
    assert items[1].text() == f"Б — D:\\edt\\b — {UNKNOWN_VERSION_MARK}"
    assert dialog.selected() == [A, B]


def test_unchecked_excluded_and_none_disables_ok(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtImportDialog([A, B])
    qtbot.addWidget(dialog)
    dialog.list_widget().item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected() == [B]
    dialog.list_widget().item(1).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected() == []
    assert dialog.ok_button().isEnabled() is False
```

- [ ] **Step 2: Диалог импорта — реализация**

`src/onecstarter/ui/edt/import_dialog.py`:

```python
"""Импорт из EDT Start (спека v3, §6): кандидаты с галочками, все отмечены."""

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from onecstarter.domain.edt import ImportCandidate
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

UNKNOWN_VERSION_MARK = "версия неизвестна"


class EdtImportDialog(QDialog):
    def __init__(self, candidates: Sequence[ImportCandidate], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импорт из EDT Start")
        self._candidates = list(candidates)
        self._list = QListWidget()
        for candidate in self._candidates:
            version = candidate.project.edt_version if candidate.version_known else UNKNOWN_VERSION_MARK
            item = QListWidgetItem(f"{candidate.project.name} — {candidate.project.workspace} — {version}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._refresh)
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Проекты EDT Start, которых ещё нет в списке:"))
        layout.addWidget(self._list, 1)
        layout.addWidget(self._buttons)
        self.resize(640, 400)
        self._refresh()

    def selected(self) -> list[ImportCandidate]:
        return [
            candidate
            for index, candidate in enumerate(self._candidates)
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _refresh(self, *_args: object) -> None:
        self.ok_button().setEnabled(bool(self.selected()))

    def list_widget(self) -> QListWidget:
        return self._list

    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]
```

Run: `uv run pytest tests/ui/test_edt_import_dialog.py -q` — зелёное.

- [ ] **Step 3: Вьюха — падающие тесты**

В `tests/ui/test_edt_view.py` — в `Harness.__init__` добавить `self.infos: list[str] = []`
и `self.registry: EdtStartRegistry | None = None`; в конструкторе `EdtWorkspace` заменить
`edtstart=lambda: None` на `edtstart=lambda: self.registry`; в `view()` добавить
`show_info=self.infos.append`. Импорты: `EdtStartProduct`, `EdtStartProject` из
`onecstarter.domain.edt`, `EdtStartRegistry` из `onecstarter.platform_1c.edtstart_registry`.

Тесты:

```python
PRODUCT = EdtStartProduct("prod", "2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), ())
ES = EdtStartProject("es", "(2025) А", Path(r"D:\edt\a"), "prod", ("-Xmx8192m",), None)


def test_banner_only_when_empty_and_registry_present(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    view = harness.view()
    qtbot.addWidget(view)
    assert view.banner().isHidden() is True
    harness.registry = EdtStartRegistry((PRODUCT,), (ES,), 0)
    view.rebuild()
    assert view.banner().isHidden() is False
    _add(harness, "a")
    view.rebuild()
    assert view.banner().isHidden() is True


def test_import_adds_selected(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    harness.registry = EdtStartRegistry((PRODUCT,), (ES,), 0)
    view = harness.view()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "_run_dialog", lambda dialog: True)
    view.import_from_edtstart()
    [project] = harness.workspace.projects()
    assert project.workspace == r"D:\edt\a"
    assert project.edt_version == "2025.2.6+4"
    assert harness.infos == ["Импортировано записей: 1"]


def test_import_without_registry_shows_error(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    view = harness.view()
    qtbot.addWidget(view)
    view.import_from_edtstart()
    assert harness.errors == ["EDT Start не найден: реестр %LOCALAPPDATA%\\1C\\1cedtstart не читается"]


def test_import_nothing_new_shows_info(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    harness.registry = EdtStartRegistry((PRODUCT,), (ES,), 0)
    _add(harness, "a", workspace=r"D:\edt\a")
    view = harness.view()
    qtbot.addWidget(view)
    view.import_from_edtstart()
    assert harness.infos == ["Новых проектов в EDT Start нет"]
```

- [ ] **Step 4: Вьюха — реализация**

В `EdtView.__init__` — параметр `show_info: Callable[[str], None] | None = None`,
поле `self._show_info = show_info or self._default_show_info`; заглушку
`import_from_edtstart` заменить:

```python
    def import_from_edtstart(self) -> None:
        candidates = self._workspace.import_candidates()
        if candidates is None:
            self._show_error(
                "EDT Start не найден: реестр %LOCALAPPDATA%\\1C\\1cedtstart не читается"
            )
            return
        if not candidates:
            self._show_info("Новых проектов в EDT Start нет")
            return
        dialog = EdtImportDialog(candidates, parent=self)
        if not self._run_dialog(dialog):
            return
        added = self._workspace.import_projects(dialog.selected())
        self.rebuild()
        message = f"Импортировано записей: {added}"
        skipped = self._workspace.edtstart_skipped()
        if skipped:
            message += f"
Пропущено записей EDT Start без пути или продукта: {skipped}"
        self._show_info(message)

    def _default_show_info(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()
```

Импорт: `from onecstarter.ui.edt.import_dialog import EdtImportDialog`.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest tests/ui/test_edt_view.py tests/ui/test_edt_import_dialog.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/ui/edt/import_dialog.py src/onecstarter/ui/edt/view.py tests/ui/test_edt_import_dialog.py tests/ui/test_edt_view.py
git commit -m "feat(ui): импорт из EDT Start с выбором кандидатов и баннер пустого списка"
```

---

### Task 18: Настройки — группа «EDT» во вьюхе

**Files:**
- Modify: `src/onecstarter/services/edt.py` (`EdtNotes`, `settings_notes`)
- Modify: `src/onecstarter/ui/settings_view.py`
- Modify: `tests/unit/test_edt_workspace.py`
- Modify: `tests/ui/test_settings_view.py`

**Interfaces:**
- Consumes: `Settings` поля (Task 11); `EditorKind`, `find_editor` (Task 8); `read_jdk_version` (Task 7); `LANGUAGES`; `CollapsibleGroup`, `_add_group`, `_add_row` (существуют в `settings_view.py`).
- Produces: `EdtNotes(jvm: str, vscode: str, antigravity: str)`; `settings_notes(jvm_dir: str, editors: Callable[[EditorKind], EditorResolution], jdk_version: Callable[[Path], str | None]) -> EdtNotes`; `SettingsView(edt_notes: Callable[[], EdtNotes] = lambda: EdtNotes("", "", ""))`; аксессоры `edt_jvm_edit()`, `edt_jvm_browse_button()`, `edt_heap_spin()`, `edt_language_combo()`, `editor_vscode_edit()`, `editor_vscode_browse_button()`, `editor_antigravity_edit()`, `editor_antigravity_browse_button()`; заголовки строк — константы `EDT_JVM_ROW = "JDK по умолчанию"`, `EDT_HEAP_ROW = "Память для новых записей, МБ"`, `EDT_LANGUAGE_ROW = "Язык для новых записей"`, `EDT_VSCODE_ROW = "VS Code"`, `EDT_ANTIGRAVITY_ROW = "Antigravity"`; группа — `"EDT"`.

- [ ] **Step 1: Подписи — падающие тесты**

В `tests/unit/test_edt_workspace.py`:

```python
from onecstarter.services.edt import EdtNotes, settings_notes


class TestSettingsNotes:
    def test_empty_jvm_explains_auto(self) -> None:
        notes = settings_notes("", lambda kind: EditorResolution(None, "", "x"), lambda p: None)
        assert notes.jvm == "Не задан — JDK подбирается из products.json, 1cedt.ini или соседних JDK"

    def test_jvm_with_release(self) -> None:
        notes = settings_notes(
            r"C:\jdk\bin", lambda kind: EditorResolution(None, "", "x"), lambda p: "17.0.16"
        )
        assert notes.jvm == "Java 17.0.16"

    def test_jvm_without_release(self) -> None:
        notes = settings_notes(r"C:\nope\bin", lambda kind: EditorResolution(None, "", "x"), lambda p: None)
        assert notes.jvm == "Файл release не найден: версия неизвестна"

    def test_editor_notes(self) -> None:
        def editors(kind: EditorKind) -> EditorResolution:
            if kind is EditorKind.VSCODE:
                return EditorResolution(Path(r"C:\code\code.cmd"), "PATH", "")
            return EditorResolution(None, "", "Не найден — укажите путь в Настройках")

        notes = settings_notes("", editors, lambda p: None)
        assert notes.vscode == r"Найден: C:\code\code.cmd"
        assert notes.antigravity == "Не найден — укажите путь в Настройках"
```

Реализация в `services/edt.py`:

```python
@dataclass(frozen=True)
class EdtNotes:
    jvm: str
    vscode: str
    antigravity: str


def settings_notes(
    jvm_dir: str,
    editors: Callable[[EditorKind], EditorResolution],
    jdk_version: Callable[[Path], str | None],
) -> EdtNotes:
    """Подписи под полями группы «EDT» в Настройках (спека §7)."""
    if not jvm_dir:
        jvm = "Не задан — JDK подбирается из products.json, 1cedt.ini или соседних JDK"
    else:
        version = jdk_version(Path(jvm_dir).parent)
        jvm = f"Java {version}" if version else "Файл release не найден: версия неизвестна"

    def note(kind: EditorKind) -> str:
        resolution = editors(kind)
        return f"Найден: {resolution.path}" if resolution.path is not None else resolution.note

    return EdtNotes(jvm=jvm, vscode=note(EditorKind.VSCODE), antigravity=note(EditorKind.ANTIGRAVITY))
```

Run: `uv run pytest tests/unit/test_edt_workspace.py -q` — зелёное.

- [ ] **Step 2: Вьюха настроек — падающие тесты**

В `tests/ui/test_settings_view.py` — `_view` получает параметр
`edt_notes: Callable[[], EdtNotes] | None = None` и передаёт
`edt_notes=edt_notes or (lambda: EdtNotes("jvm-note", "code-note", "ag-note"))`. Тесты:

```python
from PySide6.QtWidgets import QComboBox, QSpinBox

from onecstarter.services.edt import EdtNotes
from onecstarter.ui.settings_view import (
    EDT_ANTIGRAVITY_ROW,
    EDT_HEAP_ROW,
    EDT_JVM_ROW,
    EDT_LANGUAGE_ROW,
    EDT_VSCODE_ROW,
)


def test_edt_group_and_rows_registered(application: QApplication, tmp_path: Path) -> None:
    view, _ = _view(application, tmp_path)
    assert "EDT" in view.group_labels()
    assert view.edt_jvm_edit() in view.row_control(EDT_JVM_ROW).findChildren(QLineEdit)
    assert view.edt_jvm_browse_button() in view.row_control(EDT_JVM_ROW).findChildren(QPushButton)
    assert isinstance(view.row_control(EDT_HEAP_ROW), QSpinBox)
    assert isinstance(view.row_control(EDT_LANGUAGE_ROW), QComboBox)
    assert view.editor_vscode_edit() in view.row_control(EDT_VSCODE_ROW).findChildren(QLineEdit)
    assert view.editor_antigravity_edit() in view.row_control(EDT_ANTIGRAVITY_ROW).findChildren(QLineEdit)


def test_edt_notes_come_from_injected_probe(application: QApplication, tmp_path: Path) -> None:
    view, _ = _view(application, tmp_path)
    assert view.row_note(EDT_JVM_ROW).text() == "jvm-note"
    assert view.row_note(EDT_VSCODE_ROW).text() == "code-note"
    assert view.row_note(EDT_ANTIGRAVITY_ROW).text() == "ag-note"


def test_edt_fields_show_saved_values(application: QApplication, tmp_path: Path) -> None:
    save_settings(
        tmp_path / "settings.json",
        Settings(
            edt_jvm_dir=r"D:\jdk\bin",
            edt_default_max_heap_mb=4096,
            edt_default_language="ru",
            editor_vscode=r"D:\code.cmd",
            editor_antigravity=r"D:\ag.cmd",
        ),
    )
    view, _ = _view(application, tmp_path)
    assert view.edt_jvm_edit().text() == r"D:\jdk\bin"
    assert view.edt_heap_spin().value() == 4096
    assert view.edt_language_combo().currentData() == "ru"
    assert view.editor_vscode_edit().text() == r"D:\code.cmd"
    assert view.editor_antigravity_edit().text() == r"D:\ag.cmd"


def test_edt_edits_update_store(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path)
    view.edt_jvm_edit().setText(r"D:\j\bin")
    view.edt_jvm_edit().editingFinished.emit()
    view.edt_heap_spin().setValue(12288)
    view.edt_language_combo().setCurrentIndex(2)  # en
    view.editor_vscode_edit().setText(r"D:\c.cmd")
    view.editor_vscode_edit().editingFinished.emit()
    view.editor_antigravity_edit().setText(r"D:\a.cmd")
    view.editor_antigravity_edit().editingFinished.emit()
    assert store.settings.edt_jvm_dir == r"D:\j\bin"
    assert store.settings.edt_default_max_heap_mb == 12288
    assert store.settings.edt_default_language == "en"
    assert store.settings.editor_vscode == r"D:\c.cmd"
    assert store.settings.editor_antigravity == r"D:\a.cmd"


def test_edt_browse_fills_and_saves(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path, choose_directory=lambda: r"D:\picked\bin")
    view.edt_jvm_browse_button().click()
    assert view.edt_jvm_edit().text() == r"D:\picked\bin"
    assert store.settings.edt_jvm_dir == r"D:\picked\bin"
```

Если тест состава ключей `settings.json` во вьюхе (или `test_settings.py`) перечисляет
поля — он уже расширен в Task 11.

- [ ] **Step 3: Реализовать**

В `src/onecstarter/ui/settings_view.py`:

Импорты: `from PySide6.QtWidgets import QComboBox, QSpinBox` (дополнить существующий импорт),
`from onecstarter.domain.edt import LANGUAGES`, `from onecstarter.services.edt import EdtNotes`,
`from onecstarter.services.settings import EDT_HEAP_MIN`.

Константы после `SERVERS_ROOT_ROW_NOTE`:

```python
EDT_JVM_ROW = "JDK по умолчанию"
EDT_HEAP_ROW = "Память для новых записей, МБ"
EDT_LANGUAGE_ROW = "Язык для новых записей"
EDT_VSCODE_ROW = "VS Code"
EDT_ANTIGRAVITY_ROW = "Antigravity"
```

Конструктор: параметр `edt_notes: Callable[[], EdtNotes] = lambda: EdtNotes("", "", "")`
после `choose_directory`, поле `self._edt_notes = edt_notes`. После блока `self._add_group("СЕРВЕРЫ")`:

```python
        self._add_group("EDT")
        notes = self._edt_notes()
        self._edt_jvm, self._edt_jvm_browse, jvm_row = self._path_control(
            store.settings.edt_jvm_dir, "edt_jvm_dir"
        )
        self._add_row(EDT_JVM_ROW, notes.jvm, jvm_row, wide_control=True)
        self._edt_heap = QSpinBox()
        self._edt_heap.setRange(EDT_HEAP_MIN, 262144)
        self._edt_heap.setSingleStep(1024)
        self._edt_heap.setValue(store.settings.edt_default_max_heap_mb)
        self._edt_heap.valueChanged.connect(
            lambda value: self._store.update(edt_default_max_heap_mb=int(value))
        )
        self._add_row(EDT_HEAP_ROW, "Подставляется в -Xmx новой записи", self._edt_heap)
        self._edt_language = QComboBox()
        for code, label in LANGUAGES:
            self._edt_language.addItem(label, code)
        index = self._edt_language.findData(store.settings.edt_default_language)
        self._edt_language.setCurrentIndex(index if index >= 0 else 0)
        self._edt_language.currentIndexChanged.connect(
            lambda _i: self._store.update(edt_default_language=str(self._edt_language.currentData()))
        )
        self._add_row(EDT_LANGUAGE_ROW, "Подставляется в -Duser.language новой записи", self._edt_language)
        self._editor_vscode, self._editor_vscode_browse, vscode_row = self._path_control(
            store.settings.editor_vscode, "editor_vscode"
        )
        self._add_row(EDT_VSCODE_ROW, notes.vscode, vscode_row, wide_control=True)
        self._editor_antigravity, self._editor_antigravity_browse, ag_row = self._path_control(
            store.settings.editor_antigravity, "editor_antigravity"
        )
        self._add_row(EDT_ANTIGRAVITY_ROW, notes.antigravity, ag_row, wide_control=True)
```

Общий сборщик «поле + Обзор…» рядом с `_build_servers_root_control` (тот остаётся как есть):

```python
    def _path_control(self, current: str, field: str) -> tuple[QLineEdit, QPushButton, QWidget]:
        """Поле пути с «Обзор…», сохраняющее `field` в store (как у корня серверов)."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(current)
        browse = QPushButton("Обзор…")

        def save() -> None:
            self._store.update(**{field: edit.text()})

        def pick() -> None:
            chosen = self._choose_directory()
            if chosen:
                edit.setText(chosen)
                save()

        edit.editingFinished.connect(save)
        browse.clicked.connect(pick)
        row_layout.addWidget(edit)
        row_layout.addWidget(browse)
        return edit, browse, row
```

Аксессоры (в блоке «доступ для тестов»):

```python
    def edt_jvm_edit(self) -> QLineEdit:
        return self._edt_jvm

    def edt_jvm_browse_button(self) -> QPushButton:
        return self._edt_jvm_browse

    def edt_heap_spin(self) -> QSpinBox:
        return self._edt_heap

    def edt_language_combo(self) -> QComboBox:
        return self._edt_language

    def editor_vscode_edit(self) -> QLineEdit:
        return self._editor_vscode

    def editor_vscode_browse_button(self) -> QPushButton:
        return self._editor_vscode_browse

    def editor_antigravity_edit(self) -> QLineEdit:
        return self._editor_antigravity

    def editor_antigravity_browse_button(self) -> QPushButton:
        return self._editor_antigravity_browse
```

Для редакторов «Обзор…» выбирает файл `.cmd`, а не каталог. Модульная функция рядом
с `browse_for_servers_root`:

```python
def browse_for_editor_file() -> str:
    """Системный диалог файла лаунчера редактора; пустая строка — отмена."""
    return QFileDialog.getOpenFileName(
        None, "Лаунчер редактора", "", "Командные файлы (*.cmd *.exe)"
    )[0]
```

Конструктор получает `choose_file: Callable[[], str] = browse_for_editor_file` и поле
`self._choose_file`. В `_path_control` — параметр `pick_file: bool = False`; в `pick()`:

```python
            chosen = self._choose_file() if pick_file else self._choose_directory()
```

Строки редакторов зовут `_path_control(..., pick_file=True)`; `_view` в тестах передаёт
`choose_file=lambda: ""`. Тест `test_edt_browse_fills_and_saves` проверяет только JDK (каталог).

- [ ] **Step 4: Прогнать**

Run: `uv run pytest tests/ui/test_settings_view.py tests/unit/test_edt_workspace.py -q && uv run ruff check . && uv run mypy`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/services/edt.py src/onecstarter/ui/settings_view.py tests/unit/test_edt_workspace.py tests/ui/test_settings_view.py
git commit -m "feat(ui): группа EDT в Настройках — JDK, память и язык по умолчанию, пути редакторов"
```

---

### Task 19: Сборка раздела в приложении и smoke

**Files:**
- Modify: `src/onecstarter/ui/app.py`
- Modify: `src/onecstarter/ui/shell.py` (только если `set_section_icon`/`sections` требуют правки — по факту нет)
- Modify: `tests/ui/test_app.py`

**Interfaces:**
- Consumes: всё из Tasks 7–18; `Runtime`, `_build_main_window`, `run_smoke`, `main` (существуют).
- Produces: `Runtime.edt: Path` (`%APPDATA%\OneCStarter\edt.json`); `_build_main_window` возвращает пятый элемент — `EdtMonitor`; раздел «EDT» между «Серверы» и «Настройки»; `main()` зовёт `edt_monitor.start()` рядом с `monitor.start()`; строка `smoke: edt=<число установок>` в самопроверке.

- [ ] **Step 1: Падающие тесты**

В `tests/ui/test_app.py`:

1. Двойник монитора рядом с `_FakeServerMonitor`:

```python
class _FakeEdtMonitor(QObject):
    """Двойник `EdtMonitor` — тот же довод, что у `_FakeServerMonitor`."""

    scan_ready = Signal(object)
    installations_ready = Signal(object)

    def __init__(self, scanner: Any, projects: Any, discover: Any, *, parent: Any = None, **_kwargs: Any) -> None:
        super().__init__(parent)
        self.started = False
        self.discover_calls = 0

    def start(self) -> None:
        self.started = True

    def scan_now(self) -> None:
        pass

    def discover_now(self) -> None:
        self.discover_calls += 1
```

2. В `_Assembly` — поле `edt_monitor: _FakeEdtMonitor`; в `_assemble` — рядом с подменой
`ServerMonitor`:

```python
    def fake_edt_monitor(scanner: Any, projects: Any, discover: Any, **kwargs: Any) -> _FakeEdtMonitor:
        monitor = _FakeEdtMonitor(scanner, projects, discover, **kwargs)
        captured["edt_monitor"] = monitor
        return monitor

    monkeypatch.setattr(app_module, "EdtMonitor", fake_edt_monitor)
```

и `edt_monitor=captured["edt_monitor"]` в конструкторе `_Assembly`.

3. Тесты:

```python
def test_main_starts_the_edt_monitor(assembled: _Assembly) -> None:
    """main() обязан звать edt_monitor.start() рядом с monitor.start() (спека v3, §4)."""
    assert assembled.edt_monitor.started is True


def test_build_main_window_has_edt_section(
    qtbot: Any, monkeypatch: Any, qapp: Any, tmp_path: Any
) -> None:
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    env = {"APPDATA": str(tmp_path), "LOCALAPPDATA": str(tmp_path), "ProgramFiles": str(tmp_path)}
    runtime = build_runtime(env)
    assert runtime.edt == tmp_path / "OneCStarter" / "edt.json"
    window, _tasks, _monitor, _start_probe, edt_monitor = _build_main_window(
        qapp, runtime, env, process_scanner=NullScanner()
    )
    qtbot.addWidget(window)
    labels = [button.toolTip() or button.text() for button in window.section_buttons()]
    assert "EDT" in labels
    window.show_section(labels.index("EDT"))
    assert isinstance(window.current_section(), EdtView)
    assert isinstance(edt_monitor, EdtMonitor)
```

Импорты: `from onecstarter.ui.edt.view import EdtView`, `from onecstarter.ui.edt.monitor import EdtMonitor`,
`from onecstarter.platform_1c.process_scan import NullScanner` (если ещё не импортирован).
Как именно `MainWindow` подписывает кнопки рейла (текст или подсказка) — посмотреть
`shell.py`, строки 71–95, и взять то, что там задаётся из `label`.

4. Все распаковки `_build_main_window(...)` в `tests/ui/test_app.py` и в `src/onecstarter/ui/app.py`
получают пятый элемент: `window, tasks, monitor, start_probe, edt_monitor = ...`
(в тестах — `_edt_monitor`). Найти: `grep -n "_build_main_window(" tests src`.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_app.py -q -x`
Expected: `AttributeError: module 'onecstarter.ui.app' has no attribute 'EdtMonitor'` либо ошибка распаковки.

- [ ] **Step 3: Реализовать в `app.py`**

Импорты:

```python
from onecstarter.domain.edt import EdtInstallation, EditorResolution
from onecstarter.platform_1c.edt_discovery import default_roots, discover_edt, read_jdk_version
from onecstarter.platform_1c.edtstart_registry import default_edtstart_root, read_registry
from onecstarter.platform_1c.editors import EditorKind, find_editor
from onecstarter.services.edt import EdtScan, EdtWorkspace, settings_notes
from onecstarter.ui.edt.monitor import EdtMonitor
from onecstarter.ui.edt.view import EdtView
```

`Runtime` — поле `edt: Path`; в `build_runtime`:

```python
    edt_path = appdata / "OneCStarter" / "edt.json"
    return Runtime(runtime_workspace, rules, list(conventions), settings_path, servers_path, edt_path)
```

(имя первой переменной — как в файле сейчас, `workspace`.)

В `_build_main_window`, после сборки `store` и до `settings_view` (ей нужны подписи):

```python
    # Раздел «EDT» (спека v3). Всё, что ходит по диску, — лямбды над
    # текущими настройками: смена JDK или пути редактора в Настройках
    # действует со следующего обнаружения/меню, без перезапуска.
    def edt_editor(kind: EditorKind) -> EditorResolution:
        setting = (
            store.settings.editor_vscode
            if kind is EditorKind.VSCODE
            else store.settings.editor_antigravity
        )
        return find_editor(kind, setting, env)

    def edt_discover() -> list[EdtInstallation]:
        registry = read_registry(default_edtstart_root(env))
        return discover_edt(default_roots(env), registry, store.settings.edt_jvm_dir)

    edt_workspace = EdtWorkspace(
        runtime.edt,
        discover=edt_discover,
        edtstart=lambda: read_registry(default_edtstart_root(env)),
        editors=edt_editor,
    )
```

`SettingsView(...)` получает
`edt_notes=lambda: settings_notes(store.settings.edt_jvm_dir, edt_editor, read_jdk_version)`.

После `servers_view`:

```python
    edt_view = EdtView(
        edt_workspace,
        palette=controller.palette,
        request_scan=lambda: edt_monitor.scan_now(),
        request_discover=lambda: edt_monitor.discover_now(),
        dialog_defaults=lambda: (
            store.settings.edt_default_max_heap_mb,
            store.settings.edt_default_language,
        ),
    )
    sections = [
        ("Базы", view),
        ("Серверы", servers_view),
        ("EDT", edt_view),
        ("Настройки", settings_view),
    ]
    edt_section = next(i for i, (_t, w) in enumerate(sections) if w is edt_view)
    ...
    window.set_section_icon(edt_section, rail_icons.edt_icon)
```

После `monitor = ServerMonitor(...)`:

```python
    edt_monitor = EdtMonitor(
        process_scanner if process_scanner is not None else PsutilScanner(),
        edt_workspace.projects,
        edt_discover,
        parent=window,
    )
    edt_monitor.scan_ready.connect(edt_view.on_scan)
    edt_monitor.installations_ready.connect(edt_view.on_installations)
    # Смена JDK по умолчанию в Настройках — повод переобнаружить установки.
    store.changed.connect(edt_monitor.discover_now)
```

В `on_theme_changed` — `edt_view.apply_palette(controller.palette)`. Возврат —
`return window, tasks, monitor, start_probe, edt_monitor`; аннотация —
`tuple[MainWindow, StartupTasks, ServerMonitor, Callable[[], None], EdtMonitor]`.

В `main()` после `monitor.start()`:

```python
    edt_monitor.start()
```

В `run_smoke` после строки `smoke: keyring=…`:

```python
        _log.info("smoke: edt=%d", len(edt_discover_for_smoke()))
```

где вместо отдельной функции проще: `_build_main_window` кладёт `edt_workspace` в
`window.edt_workspace: object | None` (по образцу `settings_store`), и smoke пишет
`len(cast(EdtWorkspace, window.edt_workspace).refresh_installations())`. Обнаружение
в smoke — синхронное и настоящее (только чтение диска), `NullScanner` процессов не трогает.

- [ ] **Step 4: Прогнать всё**

Run: `uv run pytest -q > e:/tmp/v3-plan1-task19.log 2>&1; tail -5 e:/tmp/v3-plan1-task19.log && uv run ruff check . && uv run mypy`
Expected: все тесты зелёные (число ≈ 2021 + новые), ruff и mypy чистые. Падение —
открыть лог целиком, не `tail`.

- [ ] **Step 5: Запустить приложение вручную и пройти чек-лист**

`uv run python -m onecstarter` (или как запускается dev-сборка — см. README). Проверить:
раздел «EDT» на рейле; список пуст → баннер импорта (если EDT Start есть); импорт
добавляет записи с версиями; версия не установлена — красным; «Открыть в EDT»
для **тестового** workspace — только с разрешения заказчика (спека §10); Настройки →
группа «EDT» с подписями автопоиска. Результат — в сообщение коммита.

- [ ] **Step 6: Commit**

```bash
git add src/onecstarter/ui/app.py src/onecstarter/ui/shell.py tests/ui/test_app.py
git commit -m "feat(app): раздел EDT собран в окно — монитор, обнаружение, подписи настроек, smoke"
```

---

### Task 20: Verification-only — полный прогон, мутации, `tasks.md`

**Files:**
- Modify: `docs/tasks.md` (новый раздел T-17)
- Modify: `docs/requirements.md` (§5: v3 — «в работе, план 1 из 3»)

- [ ] **Step 1: Полный прогон в файл**

Run: `uv run pytest -q > e:/tmp/v3-plan1-final.log 2>&1; tail -3 e:/tmp/v3-plan1-final.log`
Expected: `passed`, без `failed`/`error`. Затем `uv run ruff check . && uv run mypy`.

- [ ] **Step 2: Мутационная стадия — сводная таблица**

Повторить четыре мутации Tasks 10 и 13 (`.bad`, отказ без JDK, повтор без второго
`spawn`, идемпотентность импорта) чужими руками — исполнитель этой задачи, не автор
тестов; каждую — правкой файла, прогон только названного теста, дословный `FAILED`,
откат правкой. Плюс две новые:

5. `ui/edt/tree_model.py::_project_row` — `if not project.edt_version` → `if project.edt_version`
   (метка «не найден» на пустой версии). Expected: `test_version_column_marks_not_installed`,
   `test_empty_version_shows_dash` падают.
6. `ui/edt/view.py::_fill_project_menu` — убрать `open_edt.setEnabled(False)`. Expected:
   `test_project_menu_open_edt_disabled_when_not_installed` падает.

Результаты — таблицей в T-17 (формат — «Мутационные проверки вехи v2.4», `docs/tasks.md`).

- [ ] **Step 3: `docs/tasks.md` — раздел T-17**

Добавить в конец файла:

```markdown
## T-17. Проекты EDT — `IN PROGRESS` (ветка `feat/2026-09-10-v3-edt`)

Дизайн — [спека v3](superpowers/specs/2026-09-10-v3-edt-design.md). Планы:
[план 1 — раздел](superpowers/plans/2026-09-10-v3-plan1-edt-section.md) (этот),
план 2 — CLI и консоль, план 3 — эксперименты, скил, документы, выпуск.

| # | Задача | Статус |
| --- | --- | --- |
| T-17.1 | План 1: раздел «EDT» — домен, обнаружение, реестр EDT Start, хранилище, координатор, UI, настройки, сборка (20 задач) | DONE |
| T-17.2 | План 2: CLI EDT и консоль (спека §14) | — |
| T-17.3 | План 3: эксперименты 1–7 (спека §10), скил `edt-launch`, документы, выпуск 3.0.0 | — |

### Мутационные проверки плана 1 (дата)

| # | Задача | Мутация | Ф / Т | Результат |
| --- | --- | --- | --- | --- |
| 1 | 10 | `_move_aside` без `replace` | `services/edt_store.py` / `test_corrupt_moves_aside_and_starts_empty`, `test_cannot_move_aside_raises` | … |
| 2 | 13 | `launch` без отказа при `jvm is None` | `services/edt.py` / `test_no_jvm_refuses_before_spawn` | … |
| 3 | 13 | `launch` без ветки активации | `services/edt.py` / `test_running_activates_instead_of_spawn` | … |
| 4 | 6 | `import_candidates` без фильтра по `known` | `domain/edt.py` / `test_idempotent_second_pass`, `test_import_adds_selected_and_is_idempotent` | … |
| 5 | 14 | `_project_row`: инверсия проверки пустой версии | `ui/edt/tree_model.py` / `test_version_column_marks_not_installed`, `test_empty_version_shows_dash` | … |
| 6 | 16 | `_fill_project_menu` без `setEnabled(False)` | `ui/edt/view.py` / `test_project_menu_open_edt_disabled_when_not_installed` | … |
```

Ячейки «…» заполняются дословным `FAILED` из шага 2, «(дата)» — датой прогона.

- [ ] **Step 4: `docs/requirements.md` §5**

Абзац после таблицы роадмапа: `v3 и дальше — план.` → `v3 — в работе (ветка
\`feat/2026-09-10-v3-edt\`, план 1 из 3 закрыт); v4 и дальше — план.`

- [ ] **Step 5: Commit**

```bash
git add docs/tasks.md docs/requirements.md
git commit -m "docs: T-17 — план 1 вехи v3 закрыт, мутационная стадия записана"
```

---

## Чего в плане нет — сознательно

- **CLI и консоль** (спека §14) — план 2: своя ветка задач, свой журнал, свои мутации.
- **Эксперименты 1–7, скил `edt-launch`, README, версия `3.0.0`, сборка и выпуск** — план 3.
  Запуск EDT на машине заказчика в плане 1 встречается один раз — ручной чек-лист Task 19,
  и только с разрешения.
- **Сохранение раскрытия групп между сеансами, ширины колонок** — не в спеке.
- **Общий монитор с серверами** — спека §4 допускает лишь при параметризации без правки
  поведения; калька дешевле и не трогает раздел «Серверы».
