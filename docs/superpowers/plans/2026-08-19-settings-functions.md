# Функции настроек — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести раздел «Настройки» до утверждённого мокапа: сделать настраиваемыми
закрытие в трей, глобальный хоткей и лимит «Недавних», добавить автозапуск при входе
в Windows.

**Architecture:** Чистые модули в `services` (разбор сочетания, команда автозапуска,
модель настроек) + единый писатель файла `SettingsStore` в `ui` + тонкая проводка
в `ui/app.py`. Реестр и `user32` подаются инъекцией — тесты не трогают ни живой
HKCU, ни настоящую регистрацию хоткеев.

**Tech Stack:** Python 3.12+, PySide6, pytest, ruff, mypy (strict вне `onecstarter.ui.*`),
`uv` как раннер, PyInstaller + Inno Setup для поставки.

**Спека:** [2026-08-19-settings-functions-design.md](../specs/2026-08-19-settings-functions-design.md).
Читать целиком перед началом: каждая задача ссылается на её параграфы.

## Global Constraints

- **Qt только в `src/onecstarter/ui/`.** Пакеты `domain`, `config`, `platform_1c`,
  `security`, `services` не импортируют `PySide6` ни прямо, ни транзитивно. Каждый
  новый модуль ядра дописывается в список `CORE` в `tests/unit/test_no_qt_in_core.py`,
  иначе протечка пройдёт тест зелёной.
- **Запись в пользовательские файлы — атомарная**, через `onecstarter.config.atomic.atomic_write`.
- **Секреты — только через `security/`.** В новых настройках секретов нет.
- **`SCHEMA_VERSION` остаётся `1`.** Bump схемы запрещён (§6.1 спеки).
- **Мутационная проверка обязательна** для защитных тестов: порядок — правка → зелёные →
  коммит → мутация → откат; результат пишется в **коммитуемый** документ (`docs/tasks.md`).
  Мутацию ставит не автор теста. На табличных тестах чистых функций не требуется.
- **Метки достоверности** для фактов о Windows: проверено / из документации / не проверено.
  Утверждение без метки в код-докстринг и `docs/` не попадает.
- **Русские тексты интерфейса**, кодировка исходников UTF-8 без BOM.
- **Команды:** `uv run pytest`, `uv run ruff check .`, `uv run mypy`. Все три обязаны
  быть зелёными перед коммитом — **проверять по кодам выхода, не по хвосту вывода.**
- **Коммиты с кавычками в сообщении** — через `git commit -F <файл>` (PowerShell 5.1
  ломает вложенные кавычки в аргументах нативных команд).
- **Ветка:** `settings-functions`. В `master` ничего не коммитить.

## Файловая структура

**Создаются:**

| Файл | Ответственность |
| --- | --- |
| `src/onecstarter/services/hotkeys.py` | Разбор и каноническая запись сочетания «строка ↔ (модификаторы, VK)». Чистый, без Qt и без системных вызовов. |
| `src/onecstarter/services/autostart.py` | Команда автозапуска и операции над значением реестра через инъецируемый интерфейс + единственная реализация поверх `winreg`. |
| `src/onecstarter/ui/settings_store.py` | Единственный писатель `settings.json`: держит текущий `Settings`, пишет целиком, сигналит об изменении. |
| `src/onecstarter/ui/hotkey_edit.py` | Поле захвата сочетания: Qt-событие клавиши → `HotkeySpec`. |
| `tests/unit/test_hotkeys.py` | Табличные тесты разбора/записи сочетания. |
| `tests/unit/test_autostart.py` | Тесты команды и операций над реестром на поддельном реестре. |
| `tests/ui/test_settings_store.py` | Тесты единого писателя, включая защитный «смена темы не затирает остальные поля». |
| `tests/ui/test_hotkey_edit.py` | Тесты поля захвата сочетания. |

**Изменяются:**

| Файл | Что меняется |
| --- | --- |
| `src/onecstarter/services/settings.py` | Три новых поля с мягким чтением; константы дефолтов и границ. |
| `src/onecstarter/services/display.py` | `RECENT_LIMIT` уходит; `display_forest` принимает `recent_limit` аргументом. |
| `src/onecstarter/ui/theme_controller.py` | Пишет через `SettingsStore`, а не сам. |
| `src/onecstarter/ui/settings_view.py` | Четыре группы мокапа, новые ряды и статусы. |
| `src/onecstarter/ui/hotkey.py` | Регистрация вынесена в `rebind(spec)`; сочетание больше не зашито. |
| `src/onecstarter/ui/bases/view.py` | `recent_limit` провайдером в `rebuild`. |
| `src/onecstarter/ui/app.py` | Проводка: store, трей, хоткей, балун, тихий старт. |
| `src/onecstarter/__main__.py` | Разбор `--autostart`. |
| `build/installer.iss` | Удаление значения Run при деинсталляции. |
| `build/smoke.py` | Проверка автозапуск-ветки в собранном экземпляре. |
| `tests/unit/test_no_qt_in_core.py` | Два новых модуля ядра в `CORE`. |
| `tests/unit/test_settings.py`, `tests/unit/test_display.py`, `tests/ui/test_hotkey.py`, `tests/ui/test_theme_controller.py`, `tests/ui/test_settings_view.py`, `tests/ui/test_bases_view.py`, `tests/ui/test_app.py`, `tests/unit/test_entry_point.py` | Догоняют изменившиеся сигнатуры и новое поведение. |
| `docs/tasks.md` | Запись мутационных проверок. |

---

### Task 1: Разбор сочетания клавиш (чистый модуль)

**Files:**
- Create: `src/onecstarter/services/hotkeys.py`
- Create: `tests/unit/test_hotkeys.py`
- Modify: `tests/unit/test_no_qt_in_core.py:8-25` (добавить модуль в `CORE`)

**Interfaces:**
- Consumes: ничего.
- Produces: `HotkeySpec(modifiers: int, vk: int, key: str)`; `parse_hotkey(text: str) -> HotkeySpec | None`;
  `format_hotkey(spec: HotkeySpec) -> str`; константы `MOD_ALT`, `MOD_CONTROL`, `MOD_SHIFT`,
  `MOD_WIN`, `REQUIRED_MODIFIERS`, `MODIFIER_ORDER`.

Спека §4.1 и §4.5. Правило: обязателен хотя бы один из Ctrl/Alt/Win; Shift — только
вдобавок. Разбор терпим к порядку, регистру и пробелам; запись всегда канонична.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/unit/test_hotkeys.py`:

```python
"""Разбор и каноническая запись сочетания глобального хоткея."""

import pytest

from onecstarter.services.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    HotkeySpec,
    format_hotkey,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("text", "modifiers", "vk", "key"),
    [
        ("Ctrl+Alt+B", MOD_CONTROL | MOD_ALT, 0x42, "B"),
        ("ctrl+alt+b", MOD_CONTROL | MOD_ALT, 0x42, "B"),
        ("  Ctrl + Alt + B ", MOD_CONTROL | MOD_ALT, 0x42, "B"),
        ("Alt+Ctrl+B", MOD_CONTROL | MOD_ALT, 0x42, "B"),
        ("Ctrl+Shift+F5", MOD_CONTROL | MOD_SHIFT, 0x74, "F5"),
        ("Win+1", MOD_WIN, 0x31, "1"),
        ("Ctrl+Alt+Shift+Win+Z", MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN, 0x5A, "Z"),
    ],
)
def test_parses_valid_combinations(text: str, modifiers: int, vk: int, key: str) -> None:
    assert parse_hotkey(text) == HotkeySpec(modifiers, vk, key)


@pytest.mark.parametrize(
    "text",
    [
        "",             # пусто — «выключен», решает вызывающий, не разбор
        "B",            # без модификатора
        "Shift+B",      # только Shift — модификатором не считается (§4.1)
        "Ctrl+",        # нет клавиши
        "+B",           # нет модификатора
        "Ctrl+Ctrl+B",  # повтор модификатора
        "Ctrl+Alt+Щ",   # клавиша вне поддерживаемого набора
        "Ctrl+Alt+F13",
        "Ctrl+Alt+B+C",
        "мусор",
    ],
)
def test_rejects_invalid_combinations(text: str) -> None:
    assert parse_hotkey(text) is None


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("alt+ctrl+b", "Ctrl+Alt+B"),
        ("win+shift+alt+ctrl+z", "Ctrl+Alt+Shift+Win+Z"),
        ("Ctrl + Alt + f5", "Ctrl+Alt+F5"),
    ],
)
def test_format_is_canonical(text: str, canonical: str) -> None:
    """Одно сочетание — одно написание в файле.

    Иначе сравнение «изменилось ли» начнёт врать на двух написаниях
    одного и того же (спека §4.1).
    """
    spec = parse_hotkey(text)
    assert spec is not None
    assert format_hotkey(spec) == canonical


def test_parse_format_round_trip() -> None:
    for text in ("Ctrl+Alt+B", "Ctrl+Alt+Shift+Win+Z", "Win+F12", "Alt+0"):
        spec = parse_hotkey(text)
        assert spec is not None
        assert parse_hotkey(format_hotkey(spec)) == spec
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `uv run pytest tests/unit/test_hotkeys.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.hotkeys'`

- [ ] **Step 3: Реализовать модуль**

Создать `src/onecstarter/services/hotkeys.py`:

```python
"""Сочетание глобального хоткея: разбор строки и каноническая запись.

Чистый модуль (инвариант 1): ни Qt, ни обращений к системе. Занятость
сочетания здесь не определяется — это свойство системы, а не строки,
и выясняется отказом `RegisterHotKey` в слое ui.

Коды модификаторов и виртуальных клавиш — **[Из документации Microsoft]**
(`RegisterHotKey`, Virtual-Key Codes): буквы `A`–`Z` = 0x41–0x5A совпадают
с ASCII, цифры `0`–`9` = 0x30–0x39, `F1`–`F12` = 0x70–0x7B.

Поддерживаются буквы, цифры и F1–F12 — набор намеренно узкий: то, что
пользователь может назвать словом и что заведомо есть на любой раскладке.
"""  # noqa: RUF002

from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# Порядок записи: он же порядок в каноническом написании.
MODIFIER_ORDER = (
    ("Ctrl", MOD_CONTROL),
    ("Alt", MOD_ALT),
    ("Shift", MOD_SHIFT),
    ("Win", MOD_WIN),
)

# Shift сам по себе модификатором не считается: Shift+буква — это ввод
# текста, и глобальный перехват отобрал бы его у всей системы (спека §4.1).
REQUIRED_MODIFIERS = MOD_CONTROL | MOD_ALT | MOD_WIN

__all__ = [
    "MODIFIER_ORDER",
    "MOD_ALT",
    "MOD_CONTROL",
    "MOD_SHIFT",
    "MOD_WIN",
    "REQUIRED_MODIFIERS",
    "HotkeySpec",
    "format_hotkey",
    "parse_hotkey",
]


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: int
    vk: int
    key: str


_MODIFIER_BY_NAME = {name.casefold(): bit for name, bit in MODIFIER_ORDER}

_VK_BY_KEY: dict[str, int] = {
    **{chr(code): code for code in range(0x41, 0x5B)},  # A–Z
    **{chr(code): code for code in range(0x30, 0x3A)},  # 0–9
    **{f"F{number}": 0x6F + number for number in range(1, 13)},  # F1–F12
}


def parse_hotkey(text: str) -> HotkeySpec | None:
    """Разобрать сочетание. `None` — строка не годится сочетанием.

    Пустая строка тоже даёт `None`, но означает не то же самое: «выключен»
    против «мусор». Различает их вызывающий (`services.settings`), потому
    что решение о дефолте — его, а не разбора.
    """  # noqa: RUF002
    parts = [part.strip() for part in text.split("+")]
    if len(parts) < 2 or any(not part for part in parts):
        return None
    modifiers = 0
    for part in parts[:-1]:
        bit = _MODIFIER_BY_NAME.get(part.casefold())
        if bit is None or modifiers & bit:
            return None
        modifiers |= bit
    if not modifiers & REQUIRED_MODIFIERS:
        return None
    key = parts[-1].upper()
    vk = _VK_BY_KEY.get(key)
    if vk is None:
        return None
    return HotkeySpec(modifiers, vk, key)


def format_hotkey(spec: HotkeySpec) -> str:
    """Каноническое написание: модификаторы в порядке MODIFIER_ORDER, затем клавиша."""
    names = [name for name, bit in MODIFIER_ORDER if spec.modifiers & bit]
    return "+".join([*names, spec.key])
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `uv run pytest tests/unit/test_hotkeys.py -q`
Expected: PASS, 21 passed

- [ ] **Step 5: Внести модуль в сторожа инварианта 1**

В `tests/unit/test_no_qt_in_core.py` в кортеж `CORE` после строки
`"onecstarter.services.display",` добавить:

```python
    "onecstarter.services.hotkeys",
```

- [ ] **Step 6: Полная проверка и коммит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: все три кода выхода 0

```bash
git add src/onecstarter/services/hotkeys.py tests/unit/test_hotkeys.py tests/unit/test_no_qt_in_core.py
git commit -m "feat: разбор и каноническая запись сочетания глобального хоткея"
```

---

### Task 2: Новые поля настроек

**Files:**
- Modify: `src/onecstarter/services/settings.py`
- Modify: `tests/unit/test_settings.py`

**Interfaces:**
- Consumes: `parse_hotkey`, `format_hotkey` из Task 1.
- Produces: `Settings(theme, close_to_tray, hotkey, recent_limit)`; константы
  `DEFAULT_HOTKEY = "Ctrl+Alt+B"`, `DEFAULT_RECENT_LIMIT = 10`, `RECENT_MIN = 0`,
  `RECENT_MAX = 50`.

Спека §6.1. Схема остаётся `1`; отсутствующее поле — дефолт, кривое значение —
мягко в дефолт поля; `recent_limit` зажимается в границы. Автозапуск в файле
не хранится (§3.1) — поля для него нет.

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/unit/test_settings.py`:

```python
def test_defaults_of_new_fields() -> None:
    """Дефолты не меняют поведение работающей программы (спека §1)."""
    settings = Settings()
    assert settings.close_to_tray is True
    assert settings.hotkey == DEFAULT_HOTKEY
    assert settings.recent_limit == DEFAULT_RECENT_LIMIT
    assert DEFAULT_RECENT_LIMIT == 10
    assert DEFAULT_HOTKEY == "Ctrl+Alt+B"


def test_old_file_without_new_keys_reads_with_defaults(tmp_path: Path) -> None:
    """Файл прошлой версии читается без миграции — схема та же (спека §6.1)."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "theme": "light"}), encoding="utf-8")
    assert load_settings(path) == Settings(theme=ThemeMode.LIGHT)
    assert not path.with_name("settings.json.bad").exists()


def test_round_trip_keeps_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings(
        theme=ThemeMode.DARK, close_to_tray=False, hotkey="Win+F9", recent_limit=0
    )
    save_settings(path, settings)
    assert load_settings(path) == settings


def test_all_fields_are_written(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "schema": SCHEMA_VERSION,
        "theme": "auto",
        "close_to_tray": True,
        "hotkey": "Ctrl+Alt+B",
        "recent_limit": 10,
    }


@pytest.mark.parametrize("value", ["да", 1, None, [], {}])
def test_broken_close_to_tray_falls_back(tmp_path: Path, value: object) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema": 1, "close_to_tray": value}), encoding="utf-8"
    )
    assert load_settings(path).close_to_tray is True


def test_empty_hotkey_means_disabled_not_default(tmp_path: Path) -> None:
    """Пустая строка — валидное «выключен» (спека §4.5), а не повод к дефолту."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "hotkey": "   "}), encoding="utf-8")
    assert load_settings(path).hotkey == ""


@pytest.mark.parametrize("value", ["Shift+B", "мусор", "B", 42, None])
def test_unusable_hotkey_falls_back_to_default(tmp_path: Path, value: object) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "hotkey": value}), encoding="utf-8")
    assert load_settings(path).hotkey == DEFAULT_HOTKEY


def test_hotkey_is_canonicalized_on_read(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "hotkey": "alt+ctrl+b"}), encoding="utf-8")
    assert load_settings(path).hotkey == "Ctrl+Alt+B"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), (50, 50), (7, 7), (-3, 0), (999, 50), (10.5, 10), ("10", 10), (True, 10)],
)
def test_recent_limit_is_clamped(tmp_path: Path, value: object, expected: int) -> None:
    """Границы 0–50; не-целое и bool — в дефолт.

    `True` проверяется отдельно: в Python `bool` — подкласс `int`, и без
    явной проверки `{"recent_limit": true}` прошло бы как 1.
    """
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "recent_limit": value}), encoding="utf-8")
    assert load_settings(path).recent_limit == expected
```

В шапке файла заменить блок импорта на:

```python
from onecstarter.services.settings import (
    DEFAULT_HOTKEY,
    DEFAULT_RECENT_LIMIT,
    SCHEMA_VERSION,
    Settings,
    ThemeMode,
    load_settings,
    save_settings,
)
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_settings.py -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_HOTKEY'`

- [ ] **Step 3: Реализовать поля**

В `src/onecstarter/services/settings.py`:

Заменить блок констант и `__all__`:

```python
SCHEMA_VERSION = 1
DEFAULT_HOTKEY = "Ctrl+Alt+B"
DEFAULT_RECENT_LIMIT = 10
RECENT_MIN = 0
RECENT_MAX = 50

__all__ = [
    "DEFAULT_HOTKEY",
    "DEFAULT_RECENT_LIMIT",
    "RECENT_MAX",
    "RECENT_MIN",
    "SCHEMA_VERSION",
    "Settings",
    "ThemeMode",
    "load_settings",
    "save_settings",
]
```

Добавить импорт после `from onecstarter.config.atomic import atomic_write`:

```python
from onecstarter.services.hotkeys import format_hotkey, parse_hotkey
```

Заменить `Settings`:

```python
@dataclass(frozen=True)
class Settings:
    theme: ThemeMode = ThemeMode.AUTO
    close_to_tray: bool = True
    hotkey: str = DEFAULT_HOTKEY
    recent_limit: int = DEFAULT_RECENT_LIMIT
```

Заменить хвост `load_settings` (строку `return Settings(theme=...)`):

```python
    return Settings(
        theme=_theme_of(payload.get("theme")),
        close_to_tray=_bool_of(payload.get("close_to_tray")),
        hotkey=_hotkey_of(payload.get("hotkey")),
        recent_limit=_recent_of(payload.get("recent_limit")),
    )
```

Заменить тело `save_settings` (строку `payload = {...}`):

```python
    payload = {
        "schema": SCHEMA_VERSION,
        "theme": settings.theme.value,
        "close_to_tray": settings.close_to_tray,
        "hotkey": settings.hotkey,
        "recent_limit": settings.recent_limit,
    }
```

Дописать помощники после `_theme_of`:

```python
def _bool_of(value: Any) -> bool:
    """Не-булево — не порча файла: дефолт поля, как у режима темы."""
    return value if isinstance(value, bool) else True


def _hotkey_of(value: Any) -> str:
    """Пустая строка — «выключен» (валидно). Непригодная — дефолт (спека §4.5).

    Годная строка возвращается канонизованной: иначе одно сочетание
    попадёт в файл двумя написаниями и сравнение «изменилось ли» соврёт.
    """  # noqa: RUF002
    if not isinstance(value, str):
        return DEFAULT_HOTKEY
    if not value.strip():
        return ""
    spec = parse_hotkey(value)
    return DEFAULT_HOTKEY if spec is None else format_hotkey(spec)


def _recent_of(value: Any) -> int:
    """Границы 0–50; не-целое — дефолт.

    `bool` отсекается первым: он подкласс `int`, и `true` в файле
    иначе прошёл бы единицей.
    """  # noqa: RUF002
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_RECENT_LIMIT
    return max(RECENT_MIN, min(RECENT_MAX, value))
```

Обновить докстринг модуля: первую строку заменить на
`"""Настройки приложения: тема, поведение окна, глобальный хоткей, «Недавние».`
и дописать абзацем перед закрывающими кавычками:

```
Автозапуск при входе в Windows здесь НЕ хранится: его истина — значение
в реестре (спека §3.1). Два источника истины разошлись бы при
переустановке или ручной правке реестра.

Схема остаётся 1 и при добавлении полей: новые ключи необязательны,
старый файл читается без миграции, а старая версия программы новый файл
не ломает. Bump схемы был бы строго хуже — старая версия увезла бы файл
в `.bad` и потеряла даже тему.
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_settings.py -q`
Expected: PASS

- [ ] **Step 5: Полная проверка и коммит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0. Если `tests/unit/test_display.py` упал на
`RECENT_LIMIT` — это Task 4, здесь ничего не трогать: `display.py` в этой
задаче не менялся, значит падения быть не должно.

```bash
git add src/onecstarter/services/settings.py tests/unit/test_settings.py
git commit -m "feat: поля close_to_tray, hotkey и recent_limit в настройках"
```

---

### Task 3: Автозапуск — команда и операции над реестром

**Files:**
- Create: `src/onecstarter/services/autostart.py`
- Create: `tests/unit/test_autostart.py`
- Modify: `tests/unit/test_no_qt_in_core.py:8-25`

**Interfaces:**
- Consumes: ничего.
- Produces: `RUN_KEY`, `VALUE_NAME`, `AUTOSTART_FLAG`; `Registry` (Protocol с
  `read(name) -> str | None`, `write(name, data) -> None`, `delete(name) -> None`);
  `WindowsRegistry`; `autostart_command(executable: str) -> str`;
  `is_enabled(registry: Registry) -> bool`; `enable(registry: Registry, executable: str) -> None`;
  `disable(registry: Registry) -> None`.

Спека §3.1–3.3, 3.6. Реестр подаётся инъекцией: живой HKCU тесты не трогают.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_autostart.py`:

```python
"""Автозапуск: команда и операции над значением реестра.

Реестр — поддельный: живой HKCU тесты не трогают (спека §8), тот же приём,
что с инъекцией user32 в глобальном хоткее.
"""

import pytest

from onecstarter.services.autostart import (
    AUTOSTART_FLAG,
    RUN_KEY,
    VALUE_NAME,
    autostart_command,
    disable,
    enable,
    is_enabled,
)


class FakeRegistry:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.deleted: list[str] = []

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, data: str) -> None:
        self.values[name] = data

    def delete(self, name: str) -> None:
        self.deleted.append(name)
        self.values.pop(name, None)


class BrokenRegistry(FakeRegistry):
    def write(self, name: str, data: str) -> None:
        raise PermissionError(5, "отказано в доступе")

    def delete(self, name: str) -> None:
        raise PermissionError(5, "отказано в доступе")


def test_key_and_value_names_are_the_documented_ones() -> None:
    assert RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert VALUE_NAME == "OneCStarter"
    assert AUTOSTART_FLAG == "--autostart"


def test_command_quotes_path_and_adds_flag() -> None:
    """Путь в кавычках: за ним идёт аргумент, а сам путь содержит пробелы (спека §3.2)."""
    assert (
        autostart_command(r"C:\Program Files\OneCStarter\OneCStarter.exe")
        == r'"C:\Program Files\OneCStarter\OneCStarter.exe" --autostart'
    )


def test_disabled_when_value_absent() -> None:
    assert is_enabled(FakeRegistry()) is False


def test_enabled_when_value_present() -> None:
    registry = FakeRegistry({VALUE_NAME: r'"C:\other\OneCStarter.exe" --autostart'})
    assert is_enabled(registry) is True


def test_enable_writes_command_of_this_copy() -> None:
    registry = FakeRegistry({VALUE_NAME: r'"C:\old\OneCStarter.exe" --autostart'})
    enable(registry, r"C:\new\OneCStarter.exe")
    assert registry.values[VALUE_NAME] == r'"C:\new\OneCStarter.exe" --autostart'


def test_disable_removes_value() -> None:
    registry = FakeRegistry({VALUE_NAME: "что угодно"})
    disable(registry)
    assert registry.deleted == [VALUE_NAME]
    assert is_enabled(registry) is False


def test_disable_of_absent_value_is_quiet() -> None:
    """Выключить выключённое — не ошибка: значения и так нет."""
    registry = FakeRegistry()
    disable(registry)
    assert is_enabled(registry) is False


def test_write_failure_reaches_caller() -> None:
    """Отказ реестра гасит слой представления, а не мы (спека §3.6).

    Проглотив OSError здесь, мы показали бы пользователю включённый
    тумблер при невыполненной записи.
    """
    with pytest.raises(OSError):
        enable(BrokenRegistry(), r"C:\OneCStarter.exe")
    with pytest.raises(OSError):
        disable(BrokenRegistry({VALUE_NAME: "x"}))
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_autostart.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.autostart'`

- [ ] **Step 3: Реализовать модуль**

Создать `src/onecstarter/services/autostart.py`:

```python
"""Автозапуск при входе в Windows: значение в HKCU\\...\\Run.

Истина об автозапуске — реестр, а не `settings.json` (спека §3.1): два
источника разошлись бы при переустановке или ручной правке реестра,
и тумблер врал бы либо файлу, либо системе.

**[Проверено, 19.08.2026, машина заказчика]** Значения ключа Run — `REG_SZ`;
путь берётся в кавычки, когда за ним идут аргументы. Наш случай требует
кавычек: за путём идёт `--autostart`, а сам путь содержит пробелы.
**[Из документации Microsoft]** Значения `HKCU\\...\\Run` исполняются при
входе пользователя; прав администратора запись в HKCU не требует.

Реестр подаётся протоколом `Registry`, а не зовётся напрямую: тесты
не смеют трогать живой HKCU (тот же приём, что инъекция user32
в `ui/hotkey.py`). Единственная реализация поверх `winreg` — `WindowsRegistry`.

`OSError` наружу не гасится: тумблер обязан вернуться к фактическому
состоянию, а причина — попасть на экран (спека §3.6).
"""  # noqa: RUF002

import winreg
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OneCStarter"
AUTOSTART_FLAG = "--autostart"

__all__ = [
    "AUTOSTART_FLAG",
    "RUN_KEY",
    "VALUE_NAME",
    "Registry",
    "WindowsRegistry",
    "autostart_command",
    "disable",
    "enable",
    "is_enabled",
]


class Registry(Protocol):
    def read(self, name: str) -> str | None: ...

    def write(self, name: str, data: str) -> None: ...

    def delete(self, name: str) -> None: ...


class WindowsRegistry:
    """Настоящий `HKCU\\...\\Run`. Единственное место с `winreg`."""

    def read(self, name: str) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            # Нет ключа или нет значения — обычное «автозапуск выключен».
            return None
        return value if isinstance(value, str) else None

    def write(self, name: str, data: str) -> None:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, data)

    def delete(self, name: str) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            # Выключить выключённое — не ошибка.
            return


def autostart_command(executable: str) -> str:
    return f'"{executable}" {AUTOSTART_FLAG}'


def is_enabled(registry: Registry) -> bool:
    """Есть ли наше значение в Run.

    Сравнения с путём текущего экземпляра намеренно нет: значение,
    целящее в другую копию, — это всё равно «OneCStarter стартует при
    входе», и показать «выключено» значило бы соврать о системе.
    Включение всегда перезаписывает команду путём текущей копии,
    поэтому расхождение самолечится первым же включением.
    """  # noqa: RUF002
    return registry.read(VALUE_NAME) is not None


def enable(registry: Registry, executable: str) -> None:
    registry.write(VALUE_NAME, autostart_command(executable))


def disable(registry: Registry) -> None:
    registry.delete(VALUE_NAME)
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/unit/test_autostart.py -q`
Expected: PASS, 9 passed

- [ ] **Step 5: Внести модуль в сторожа инварианта 1**

В `tests/unit/test_no_qt_in_core.py` в `CORE` после
`"onecstarter.services.hotkeys",` добавить:

```python
    "onecstarter.services.autostart",
```

- [ ] **Step 6: Полная проверка и коммит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0

```bash
git add src/onecstarter/services/autostart.py tests/unit/test_autostart.py tests/unit/test_no_qt_in_core.py
git commit -m "feat: модуль автозапуска над HKCU Run с инъекцией реестра"
```

---

### Task 4: Лимит «Недавних» аргументом вместо константы

**Files:**
- Modify: `src/onecstarter/services/display.py:19` (убрать `RECENT_LIMIT`), `:72-95` (сигнатура)
- Modify: `src/onecstarter/ui/bases/view.py:284-300` (конструктор), `:456` (вызов)
- Modify: `tests/unit/test_display.py`
- Modify: `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `DEFAULT_RECENT_LIMIT` из Task 2.
- Produces: `display_forest(items, tree, common_errors, *, recent_limit: int) -> list[Row]`
  — параметр **обязательный**, без значения по умолчанию; `BasesView(..., recent_limit: Callable[[], int])`.

Спека §5. Умолчания у `display_forest` нет намеренно: дефолт жил бы вторым
источником истины рядом с `DEFAULT_RECENT_LIMIT`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/unit/test_display.py`: удалить `RECENT_LIMIT` из блока импорта
(строка 17). Из теста со строкой `assert RECENT_LIMIT == 10` убрать **только
эту строку**, тест переименовать по тому, что он реально проверяет.

> **Исправлено 19.08.2026 по находке Task 4.** Первая редакция шага велела
> удалить тест целиком — это была ошибка плана: та же функция была
> единственной, покрывавшей сортировку ветки «Недавние» по убыванию времени
> запуска, и буквальное исполнение стёрло бы покрытие без замены. Ни один
> из двух новых тестов сортировку не проверяет. Суффикс `_and_limited`
> в исходном имени был неточен и до вехи: при двух записях и лимите 10
> обрезание не срабатывало никогда, проверялась лишь константа-канарейка.

Функцию-помощник на строке 46 привести к виду:

```python
    return display_forest(items, build_tree(items), [], recent_limit=DEFAULT_RECENT_LIMIT)
```

Добавить импорт `from onecstarter.services.settings import DEFAULT_RECENT_LIMIT`
и дописать тесты:

```python
def test_recent_limit_zero_hides_the_branch() -> None:
    """0 — ветки «Недавние» нет вовсе (подпись мокапа, спека §5)."""
    items = [
        _base_item(name=f"База {index}", last_launched_at=_stamp(index))
        for index in range(3)
    ]
    forest = display_forest(items, build_tree(items), [], recent_limit=0)
    assert all(row.label != "Недавние" for row in forest)


def test_recent_limit_cuts_the_branch() -> None:
    items = [
        _base_item(name=f"База {index}", last_launched_at=_stamp(index))
        for index in range(5)
    ]
    forest = display_forest(items, build_tree(items), [], recent_limit=2)
    recent = next(row for row in forest if row.label == "Недавние")
    assert len(recent.children) == 2
```

Помощники `_base_item` и `_stamp` в файле уже есть — если имена отличаются,
использовать существующие (посмотреть первые 60 строк файла); суть теста
не меняется: пять записей с разным временем запуска.

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_display.py -q`
Expected: FAIL — `TypeError: display_forest() got an unexpected keyword argument 'recent_limit'`

- [ ] **Step 3: Реализовать**

В `src/onecstarter/services/display.py` удалить строку `RECENT_LIMIT = 10`
и изменить сигнатуру и тело `display_forest`:

```python
def display_forest(
    items: Sequence[InfobaseItem],
    tree: Sequence[TreeNode],
    common_errors: Sequence[CommonListError],
    *,
    recent_limit: int,
) -> list[Row]:
    """Собрать лес раздела: Избранное, Недавние, дерево файла, Общие списки.

    Пустые виртуальные ветки не показываются — они шум. Порядок записей
    внутри веток повторяет порядок items (он уже отсортирован по OrderInList),
    Недавние — по времени запуска, новые сверху.

    `recent_limit` — обязательный аргумент, а не константа с умолчанием:
    это пользовательская настройка (спека §5), и значение по умолчанию
    здесь было бы вторым источником истины рядом с
    `settings.DEFAULT_RECENT_LIMIT`. `0` гасит ветку целиком.
    """  # noqa: RUF002
```

и строку 93 заменить на:

```python
    recent = tuple(_base_row(item) for item in launched[:recent_limit])
```

В `src/onecstarter/ui/bases/view.py` в конструктор `BasesView` добавить
параметр после `cfg_rules`:

```python
        recent_limit: Callable[[], int],
```

и в теле после `self._cfg_rules = list(cfg_rules)`:

```python
        # Провайдер, а не число: настройка меняется на лету и следующая
        # пересборка обязана взять новое значение (тот же приём, что
        # `theme_mode=lambda: controller.mode` у трея).
        self._recent_limit = recent_limit
```

Вызов на строке 456 заменить на:

```python
        forest = display_forest(
            items,
            self._workspace.tree(),
            self._workspace.common_errors(),
            recent_limit=self._recent_limit(),
        )
```

- [ ] **Step 4: Догнать существующие вызовы `BasesView`**

В `tests/ui/test_bases_view.py` и `tests/ui/test_app.py` найти все создания
`BasesView(` и добавить аргумент:

Run: `uv run pytest -q 2>&1 | Select-String "recent_limit"`

Каждому вызову дописать `recent_limit=lambda: 10,` рядом с `cfg_rules=`.
В `src/onecstarter/ui/app.py` в `_build_main_window` — тоже
(временно `recent_limit=lambda: DEFAULT_RECENT_LIMIT` с импортом из
`onecstarter.services.settings`; на настоящий store его переведёт Task 8).

- [ ] **Step 5: Запустить и убедиться, что проходит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0, 1104+ passed

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/services/display.py src/onecstarter/ui/bases/view.py src/onecstarter/ui/app.py tests/unit/test_display.py tests/ui/test_bases_view.py tests/ui/test_app.py
git commit -m "refactor: лимит Недавних аргументом display_forest вместо константы"
```

---

### Task 5: SettingsStore — единственный писатель файла

**Files:**
- Create: `src/onecstarter/ui/settings_store.py`
- Create: `tests/ui/test_settings_store.py`
- Modify: `src/onecstarter/ui/theme_controller.py`
- Modify: `src/onecstarter/ui/app.py:303` (создание контроллера)
- Modify: `tests/ui/test_theme_controller.py`, `tests/ui/test_settings_view.py`
  (только помощники, строившие `ThemeController` из `Path`)

> **Исправлено 19.08.2026 по находке ревью Task 5.** Из списка убран
> `ui/settings_view.py`: ни один шаг задачи его не правит, и править не должен.
> `last_save_error` становится свойством контроллера именно затем, чтобы
> существующие читатели не менялись; новая сигнатура `SettingsView` —
> предмет Task 8, и трогать файл здесь значило бы забежать вперёд.

**Interfaces:**
- Consumes: `Settings`, `load_settings`, `save_settings` из Task 2.
- Produces: `SettingsStore(path, parent=None)` с `changed: Signal()`,
  свойствами `settings: Settings`, `path: Path`, полем `last_save_error: str | None`
  и методом `update(**changes: Any) -> None`;
  `ThemeController(application, store, *, system_mode=detect_system_mode)`.

Спека §6.2. Это первый защитный тест вехи — **обязательна мутационная проверка**
(Task 10).

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/ui/test_settings_store.py`:

```python
"""Единственный писатель settings.json: пишет целиком, не теряя чужих полей."""

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import Settings, ThemeMode, load_settings, save_settings
from onecstarter.ui.settings_store import SettingsStore


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def test_starts_from_file(application: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.LIGHT, recent_limit=3))
    store = SettingsStore(path)
    assert store.settings.theme is ThemeMode.LIGHT
    assert store.settings.recent_limit == 3


def test_missing_file_gives_defaults(application: QApplication, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    assert store.settings == Settings()


def test_update_persists_and_signals(application: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    seen: list[int] = []
    store.changed.connect(lambda: seen.append(1))

    store.update(recent_limit=0)

    assert store.settings.recent_limit == 0
    assert load_settings(path).recent_limit == 0
    assert seen == [1]


def test_update_keeps_other_fields(application: QApplication, tmp_path: Path) -> None:
    """Защитный: точечная правка не смеет затирать соседние поля.

    До вехи `ThemeController.set_mode` писал `Settings(theme=mode)` — целый
    файл из одного поля. С четырьмя полями это молча стирало бы выбор
    пользователя (спека §6.2). Мутация: вернуть в `update` запись
    `Settings(**changes)` вместо `replace` — тест обязан упасть.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.update(close_to_tray=False, hotkey="Win+F9", recent_limit=42)

    store.update(theme=ThemeMode.DARK)

    assert store.settings.close_to_tray is False
    assert store.settings.hotkey == "Win+F9"
    assert store.settings.recent_limit == 42
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["close_to_tray"] is False
    assert on_disk["hotkey"] == "Win+F9"
    assert on_disk["recent_limit"] == 42


def test_save_failure_is_reported_not_raised(
    application: QApplication, tmp_path: Path
) -> None:
    """Соврать «запомнили» нельзя: причина ложится в last_save_error.

    Препятствие — каталог на месте целевого файла: `atomic_write` не сможет
    переставить временный файл поверх него (тот же приём, что
    в `test_settings.py::test_save_reports_failure`).
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.mkdir()
    store = SettingsStore(path)

    store.update(recent_limit=1)

    assert store.last_save_error is not None
    assert "settings.json" in store.last_save_error
    # Значение всё равно применено: пользователь его выбрал.
    assert store.settings.recent_limit == 1


def test_successful_save_clears_previous_error(
    application: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "sub" / "settings.json"
    store = SettingsStore(path)
    store.last_save_error = "старая ошибка"

    store.update(recent_limit=2)

    assert store.last_save_error is None
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/ui/test_settings_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.ui.settings_store'`

- [ ] **Step 3: Реализовать store**

Создать `src/onecstarter/ui/settings_store.py`:

```python
"""Владелец настроек: единственный, кто пишет settings.json.

До вехи файл писал `ThemeController.set_mode` — целиком, из одного поля
(`Settings(theme=mode)`). С четырьмя полями это молча стирало бы соседние
настройки, поэтому писатель стал один (спека §6.2). Чтение и запись
остаются чистыми функциями `services/settings.py`; здесь — только текущее
состояние, сигнал и обработка отказа записи.

Автозапуск через store не ходит: его истина — реестр (спека §3.1).
"""  # noqa: RUF002

from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from onecstarter.services.settings import Settings, load_settings, save_settings


class SettingsStore(QObject):
    changed = Signal()

    def __init__(self, path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._settings = load_settings(path)
        self.last_save_error: str | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def path(self) -> Path:
        """Куда пишутся настройки — разделу «Настройки» для подписи."""
        return self._path

    def update(self, **changes: Any) -> None:
        """Изменить поля и записать файл целиком.

        `replace`, а не сборка нового `Settings` из переданного: собранный
        заново объект вернул бы к дефолтам всё, что не назвали, — ровно тот
        дефект, ради которого писатель стал один.

        Значение применяется даже при отказе записи: пользователь его
        выбрал, и откатывать выбор из-за недоступного файла значило бы
        спорить с ним молча. Причина уходит в `last_save_error`, показать
        её обязан слой представления.
        """  # noqa: RUF002
        self._settings = replace(self._settings, **changes)
        try:
            save_settings(self._path, self._settings)
            self.last_save_error = None
        except OSError as error:
            self.last_save_error = f"Не удалось сохранить {self._path}: {error}"  # noqa: RUF001
        self.changed.emit()
```

- [ ] **Step 4: Перевести ThemeController на store**

В `src/onecstarter/ui/theme_controller.py`:

Заменить импорт настроек на:

```python
from onecstarter.services.settings import ThemeMode
from onecstarter.ui.settings_store import SettingsStore
```

Заменить `__init__`, `path` и `set_mode`:

```python
    def __init__(
        self,
        application: QApplication,
        store: SettingsStore,
        *,
        system_mode: Callable[[], ThemeMode] = detect_system_mode,
    ) -> None:
        super().__init__(application)
        self._application = application
        self._store = store
        self._system_mode = system_mode
        self._mode = store.settings.theme
        self._palette = theme.palette_for(self._mode, self._system_mode())
        self._apply()

    @property
    def path(self) -> Path:
        """Куда пишутся настройки — разделу «Настройки» для подписи."""
        return self._store.path

    @property
    def last_save_error(self) -> str | None:
        """Отказ записи виден там же, где был: файл теперь пишет store."""
        return self._store.last_save_error

    def set_mode(self, mode: ThemeMode) -> None:
        self._mode = mode
        # Тема применяется всегда: пользователь её выбрал. Отказ записи
        # не гасится — раздел «Настройки» покажет причину из store.
        self._store.update(theme=mode)
        self._repaint()
```

Удалить строку `self.last_save_error: str | None = None` из старого `__init__`
(она заменена свойством) и убрать неиспользуемые импорты `Settings`,
`load_settings`, `save_settings`.

- [ ] **Step 5: Догнать вызовы**

В `src/onecstarter/ui/app.py` в `_build_main_window` заменить строку 303:

```python
    store = SettingsStore(runtime.settings, parent=application)
    controller = ThemeController(application, store)
```

с импортом `from onecstarter.ui.settings_store import SettingsStore`.

В `tests/ui/test_theme_controller.py` заменить помощник:

```python
def _controller(
    application: QApplication, path: Path, system: ThemeMode = ThemeMode.DARK
) -> ThemeController:
    return ThemeController(application, SettingsStore(path), system_mode=lambda: system)
```

с импортом `from onecstarter.ui.settings_store import SettingsStore`.

Прогнать и починить оставшиеся падения тем же приёмом:

Run: `uv run pytest tests/ui -q`

- [ ] **Step 6: Полная проверка и коммит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0

```bash
git add src/onecstarter/ui/settings_store.py src/onecstarter/ui/theme_controller.py src/onecstarter/ui/app.py tests/ui/test_settings_store.py tests/ui/test_theme_controller.py tests/ui/test_settings_view.py
git commit -m "refactor: SettingsStore единственным писателем settings.json"
```

---

### Task 6: Перерегистрация глобального хоткея

**Files:**
- Modify: `src/onecstarter/ui/hotkey.py`
- Modify: `tests/ui/test_hotkey.py`

**Interfaces:**
- Consumes: `HotkeySpec`, `MOD_ALT`, `MOD_CONTROL` из Task 1.
- Produces: `GlobalHotkey(callback, *, register=None, unregister=None)` — больше
  **не регистрирует в конструкторе**; `rebind(spec: HotkeySpec | None) -> bool`
  (`None` — выключить, `False` — сочетание занято); поле `registered: bool`.

Спека §4.2. Факт перерегистрации — **[Проверено, 19.08.2026, эксперимент §7]**.

- [ ] **Step 1: Написать падающие тесты**

Заменить `tests/ui/test_hotkey.py` целиком:

```python
from typing import Any

from onecstarter.services.hotkeys import parse_hotkey
from onecstarter.ui.hotkey import HOTKEY_ID, WM_HOTKEY, GlobalHotkey

CTRL_ALT_B = parse_hotkey("Ctrl+Alt+B")
CTRL_ALT_Y = parse_hotkey("Ctrl+Alt+Y")


def _hotkey(
    register_result: int = 1,
) -> tuple[GlobalHotkey, dict[str, list[Any]], list[int]]:
    calls: dict[str, list[Any]] = {"register": [], "unregister": []}

    def register(hwnd: int | None, hotkey_id: int, modifiers: int, vk: int) -> int:
        calls["register"].append((hotkey_id, modifiers, vk))
        return register_result

    def unregister(hwnd: int | None, hotkey_id: int) -> int:
        calls["unregister"].append(hotkey_id)
        return 1

    fired: list[int] = []
    hotkey = GlobalHotkey(lambda: fired.append(1), register=register, unregister=unregister)
    return hotkey, calls, fired


def test_constructor_registers_nothing() -> None:
    """Сочетание приходит из настроек — регистрировать в конструкторе нечего."""
    hotkey, calls, _ = _hotkey()
    assert not hotkey.registered
    assert calls["register"] == []


def test_rebind_registers_and_dispatches() -> None:
    hotkey, calls, fired = _hotkey()
    assert CTRL_ALT_B is not None
    assert hotkey.rebind(CTRL_ALT_B) is True
    assert hotkey.registered
    assert calls["register"] == [(HOTKEY_ID, CTRL_ALT_B.modifiers, CTRL_ALT_B.vk)]
    assert hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == [1]


def test_rebind_releases_previous_registration() -> None:
    """Снять прежнее до регистрации нового — иначе сочетание останется занятым нами.

    **[Проверено, 19.08.2026, эксперимент §7 спеки]**: освобождение мгновенно,
    то же сочетание тут же берётся другой регистрацией.
    """
    hotkey, calls, _ = _hotkey()
    assert CTRL_ALT_B is not None
    assert CTRL_ALT_Y is not None
    hotkey.rebind(CTRL_ALT_B)
    hotkey.rebind(CTRL_ALT_Y)
    assert calls["unregister"] == [HOTKEY_ID]
    assert calls["register"][-1] == (HOTKEY_ID, CTRL_ALT_Y.modifiers, CTRL_ALT_Y.vk)


def test_rebind_to_none_disables() -> None:
    """Защитный: выключенный хоткей не регистрируется вовсе (спека §4.1).

    Мутация: убрать ранний выход по `spec is None` — тест обязан упасть
    на непустом `calls["register"]`.
    """
    hotkey, calls, fired = _hotkey()
    assert CTRL_ALT_B is not None
    hotkey.rebind(CTRL_ALT_B)
    calls["register"].clear()

    assert hotkey.rebind(None) is True

    assert not hotkey.registered
    assert calls["register"] == []
    assert calls["unregister"] == [HOTKEY_ID]
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == []


def test_busy_combination_reports_false_and_keeps_app_alive() -> None:
    hotkey, _, fired = _hotkey(register_result=0)
    assert CTRL_ALT_B is not None
    assert hotkey.rebind(CTRL_ALT_B) is False
    assert not hotkey.registered
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID)
    assert fired == []


def test_foreign_messages_are_ignored() -> None:
    hotkey, _, fired = _hotkey()
    assert CTRL_ALT_B is not None
    hotkey.rebind(CTRL_ALT_B)
    assert not hotkey.handle(WM_HOTKEY, HOTKEY_ID + 1)
    assert not hotkey.handle(0x0400, HOTKEY_ID)
    assert fired == []


def test_dispose_unregisters_only_when_registered() -> None:
    hotkey, calls, _ = _hotkey()
    assert CTRL_ALT_B is not None
    hotkey.rebind(CTRL_ALT_B)
    hotkey.dispose()
    assert calls["unregister"] == [HOTKEY_ID]

    busy, busy_calls, _ = _hotkey(register_result=0)
    busy.rebind(CTRL_ALT_B)
    busy.dispose()
    assert busy_calls["unregister"] == []
```

> **Дополнено 19.08.2026 по находке ревью Task 6.** К этому набору нужен ещё
> один тест — `test_rebind_same_combination_releases_and_reregisters`: два
> `rebind` подряд ОДНИМ И ТЕМ ЖЕ сочетанием, прежняя регистрация обязана быть
> снята, новая поставлена. Без него инвариант «снять прежнее до нового даже
> при совпадении» держался только докстрингом: ревьюер вставил в `rebind`
> пропуск снятия при совпадающем `spec` — все семь тестов остались зелёными.
> Инвариант не декоративен: без него программа сама держала бы сочетание
> занятым и `RegisterHotKey` отказал бы ей же.
>
> Там же: докстринг `test_rebind_releases_previous_registration` цитировал
> факт эксперимента про повторную регистрацию ТОГО ЖЕ сочетания, хотя тест
> гоняет разные. Факт переезжает в новый тест, старому докстрингу — своя
> формулировка.

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/ui/test_hotkey.py -q`
Expected: FAIL — `AttributeError: 'GlobalHotkey' object has no attribute 'rebind'`

- [ ] **Step 3: Реализовать**

Заменить `src/onecstarter/ui/hotkey.py` целиком:

```python
"""Глобальный хоткей: поднять окно с фокусом в поиске.

Windows-only (v1 — только Windows, requirements.md §4): RegisterHotKey +
WM_HOTKEY через QAbstractNativeEventFilter. Функции user32 инжектируются —
тесты не трогают реальную регистрацию.

Сочетание приходит из настроек и меняется на лету (спека §4.2), поэтому
конструктор ничего не регистрирует: регистрацию ставит `rebind`. Занятое
сочетание не роняет приложение — `rebind` отдаёт False, всё остальное
работает ([Р] спека 4a, §3).

**[Проверено, 19.08.2026, эксперимент §7 спеки вехи]** Перерегистрация
в одном процессе работает, освобождение сочетания мгновенно, доставка
WM_HOTKEY после смены сохраняется.
"""  # noqa: RUF002

import ctypes
import typing
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

from onecstarter.services.hotkeys import HotkeySpec

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
        self._register = register
        self._unregister = unregister
        self.registered = False

    def rebind(self, spec: HotkeySpec | None) -> bool:
        """Снять прежнюю регистрацию и повесить новую. False — сочетание занято.

        `None` — хоткей выключен: снимаем и ничего не регистрируем, ответ True
        (выключение удалось). Прежнее снимается ДО попытки нового, в том числе
        когда новое сочетание совпадает со старым: иначе мы сами держали бы
        его занятым и отказали бы себе же.
        """  # noqa: RUF002
        if self.registered:
            self._unregister(None, HOTKEY_ID)
            self.registered = False
        if spec is None:
            return True
        self.registered = bool(self._register(None, HOTKEY_ID, spec.modifiers, spec.vk))
        return self.registered

    def handle(self, message_id: int, wparam: int) -> bool:
        """Чистая часть диспетчеризации — тестируется без нативных событий."""
        if not self.registered:
            return False
        if message_id == WM_HOTKEY and wparam == HOTKEY_ID:
            self._callback()
            return True
        return False

    @typing.override
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

- [ ] **Step 4: Догнать вызов в app.py**

В `src/onecstarter/ui/app.py` строки 358-365 временно привести к виду
(настоящую проводку из настроек поставит Task 8):

```python
    hotkey = GlobalHotkey(window.show_and_focus_search)
    application.installNativeEventFilter(hotkey)
    hotkey.rebind(parse_hotkey(store.settings.hotkey))
    if tray is not None:
        tray.setToolTip("OneCStarter")
    application.aboutToQuit.connect(hotkey.dispose)
```

с импортом `from onecstarter.services.hotkeys import parse_hotkey`.

Фильтр ставится безусловно: он безвреден при `registered = False`
(`handle` выходит первой же строкой), а ставить его после каждой удачной
перерегистрации значило бы плодить дубликаты фильтров.

- [ ] **Step 5: Запустить и убедиться, что проходит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0. Тесты `tests/ui/test_app.py`, ожидавшие тултип
`«OneCStarter — Ctrl+Alt+B»`, обновить на новый текст — окончательные
тексты ставит Task 8.

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/ui/hotkey.py src/onecstarter/ui/app.py tests/ui/test_hotkey.py tests/ui/test_app.py
git commit -m "feat: перерегистрация глобального хоткея на лету через rebind"
```

---

### Task 7: Поле захвата сочетания

**Files:**
- Create: `src/onecstarter/ui/hotkey_edit.py`
- Create: `tests/ui/test_hotkey_edit.py`

**Interfaces:**
- Consumes: `HotkeySpec`, `parse_hotkey`, `format_hotkey` из Task 1.
- Produces: `spec_from_event(event: QKeyEvent) -> HotkeySpec | None`;
  `HotkeyEdit(QLineEdit)` с сигналом `captured = Signal(str)` (каноническая
  строка либо `""` для выключения) и методом `set_combination(text: str) -> None`.

Спека §4.1. Поле только захватывает нажатие; сохранение и регистрацию делает
раздел «Настройки» (Task 8).

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/ui/test_hotkey_edit.py`:

```python
"""Поле захвата сочетания: Qt-событие клавиши → каноническая строка."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from onecstarter.services.hotkeys import MOD_ALT, MOD_CONTROL
from onecstarter.ui.hotkey_edit import HotkeyEdit, spec_from_event


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def _press(key: Qt.Key, modifiers: Qt.KeyboardModifier) -> QKeyEvent:
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)


def test_captures_modifier_combination(application: QApplication) -> None:
    event = _press(
        Qt.Key.Key_B,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.modifiers == MOD_CONTROL | MOD_ALT
    assert spec.key == "B"


def test_bare_modifier_press_is_not_a_combination(application: QApplication) -> None:
    """Пока нажат только Ctrl, сочетания ещё нет — поле не должно дёргаться."""
    event = _press(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    assert spec_from_event(event) is None


def test_key_without_modifier_is_rejected(application: QApplication) -> None:
    event = _press(Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier)
    assert spec_from_event(event) is None


def test_shift_only_is_rejected(application: QApplication) -> None:
    event = _press(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier)
    assert spec_from_event(event) is None


def test_widget_emits_canonical_text(application: QApplication) -> None:
    edit = HotkeyEdit()
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(
        _press(
            Qt.Key.Key_B,
            Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier,
        )
    )

    assert seen == ["Ctrl+Alt+B"]
    assert edit.text() == "Ctrl+Alt+B"


def test_widget_ignores_unusable_press(application: QApplication) -> None:
    edit = HotkeyEdit()
    edit.set_combination("Ctrl+Alt+B")
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(_press(Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier))

    assert seen == []
    assert edit.text() == "Ctrl+Alt+B"


def test_delete_clears_to_disabled(application: QApplication) -> None:
    """Backspace/Delete — способ выключить хоткей (спека §4.1)."""
    edit = HotkeyEdit()
    edit.set_combination("Ctrl+Alt+B")
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(_press(Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier))

    assert seen == [""]
    assert edit.text() == HotkeyEdit.DISABLED_TEXT


def test_set_combination_shows_disabled_placeholder(application: QApplication) -> None:
    edit = HotkeyEdit()
    edit.set_combination("")
    assert edit.text() == HotkeyEdit.DISABLED_TEXT
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/ui/test_hotkey_edit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.ui.hotkey_edit'`

- [ ] **Step 3: Реализовать**

Создать `src/onecstarter/ui/hotkey_edit.py`:

```python
"""Поле захвата сочетания: нажатие клавиш вместо ввода текста.

Отдельный файл, а не часть `settings_view`: перевод Qt-модификаторов
в наши биты — единственная Qt-специфичная часть работы с сочетанием,
и держать её рядом с раскладкой раздела значило бы смешать две разные
ответственности в одном файле.

Поле только захватывает. Сохранение, регистрацию и показ отказа делает
раздел «Настройки»: занятость сочетания — свойство системы, а не ввода
(спека §4.2).
"""  # noqa: RUF002

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QLineEdit, QWidget

from onecstarter.services.hotkeys import HotkeySpec, format_hotkey, parse_hotkey

_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr,
}

_CLEAR_KEYS = {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}

_MODIFIER_NAMES = (
    (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
    (Qt.KeyboardModifier.AltModifier, "Alt"),
    (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    (Qt.KeyboardModifier.MetaModifier, "Win"),
)


def spec_from_event(event: QKeyEvent) -> HotkeySpec | None:
    """Сочетание из нажатия. `None` — нажатое сочетанием не является.

    Правило допустимости не дублируется: строка собирается и отдаётся
    в `parse_hotkey`, который один решает, годится ли она. Иначе два
    места судили бы об одном и разошлись бы при первой же правке.
    """  # noqa: RUF002
    key = Qt.Key(event.key())
    if key in _MODIFIER_KEYS:
        # Модификатор ещё удерживается, клавиши нет — сочетания пока нет.
        return None
    modifiers = event.modifiers()
    names = [name for bit, name in _MODIFIER_NAMES if modifiers & bit]
    # int(key), а не сам enum: конструктор QKeySequence в PySide6
    # перегружен, и передача Qt.Key может уйти не в ту перегрузку.
    key_name = QKeySequence(int(key)).toString()
    if not key_name:
        return None
    return parse_hotkey("+".join([*names, key_name]))


class HotkeyEdit(QLineEdit):
    """Только для чтения: значение появляется нажатием, а не набором текста."""

    DISABLED_TEXT = "не назначено"

    captured = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText(self.DISABLED_TEXT)
        self.setToolTip(
            "Нажмите сочетание с Ctrl, Alt или Win. "
            "Backspace или Delete — выключить вызов."
        )

    def set_combination(self, text: str) -> None:
        """Показать сохранённое значение. Пустая строка — «не назначено»."""
        self.setText(text or self.DISABLED_TEXT)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = Qt.Key(event.key())
        if key in _CLEAR_KEYS:
            self.set_combination("")
            self.captured.emit("")
            event.accept()
            return
        spec = spec_from_event(event)
        if spec is None:
            # Непригодное нажатие не стирает уже назначенное: пользователь
            # промахнулся, а не отказался от сочетания.
            event.accept()
            return
        text = format_hotkey(spec)
        self.set_combination(text)
        self.captured.emit(text)
        event.accept()
```

- [ ] **Step 4: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/ui/test_hotkey_edit.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Полная проверка и коммит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0

```bash
git add src/onecstarter/ui/hotkey_edit.py tests/ui/test_hotkey_edit.py
git commit -m "feat: поле захвата сочетания глобального вызова"
```

---

### Task 8: Раздел «Настройки» — четыре группы мокапа

**Files:**
- Modify: `src/onecstarter/ui/settings_view.py`
- Modify: `tests/ui/test_settings_view.py`

**Interfaces:**
- Consumes: `SettingsStore` (Task 5), `HotkeyEdit` (Task 7), `autostart` (Task 3),
  `ThemeController` (Task 5).
- Produces: `SettingsView(controller, store, *, autostart_registry=None, frozen=False,
  executable="", on_hotkey=None, parent=None)`; методы для тестов:
  `theme_buttons()`, `tray_checkbox()`, `autostart_checkbox()`, `hotkey_edit()`,
  `recent_spinbox()`, `status_text()`, `path_text()`, `autostart_note()`,
  `hotkey_note()`.

Спека §2, §3.3, §3.6, §4.2, §5. Порядок групп — ВНЕШНИЙ ВИД, ОКНО И ЗАПУСК,
ГОРЯЧИЕ КЛАВИШИ, СПИСОК БАЗ.

`on_hotkey: Callable[[str], str | None]` — раздел отдаёт выбранное сочетание
наружу и получает обратно текст ошибки либо `None`. Регистрация живёт в проводке
приложения (Task 9), раздел о `GlobalHotkey` не знает.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_settings_view.py` (существующие тесты темы оставить,
поправив конструктор на новую сигнатуру):

```python
"""Раздел «Настройки»: четыре группы мокапа."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.services.autostart import VALUE_NAME, autostart_command
from onecstarter.services.settings import Settings, ThemeMode, save_settings
from onecstarter.ui.hotkey_edit import HotkeyEdit
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.settings_view import SettingsView
from onecstarter.ui.theme_controller import ThemeController

EXE = r"C:\Programs\OneCStarter\OneCStarter.exe"


class FakeRegistry:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, data: str) -> None:
        self.values[name] = data

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


class BrokenRegistry(FakeRegistry):
    def write(self, name: str, data: str) -> None:
        raise PermissionError(5, "отказано в доступе")


class UnreadableRegistry(FakeRegistry):
    def read(self, name: str) -> str | None:
        raise PermissionError(5, "отказано в доступе")


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def _view(
    application: QApplication,
    tmp_path: Path,
    *,
    registry: FakeRegistry | None = None,
    frozen: bool = True,
    on_hotkey=None,
) -> tuple[SettingsView, SettingsStore]:
    store = SettingsStore(tmp_path / "settings.json")
    controller = ThemeController(application, store, system_mode=lambda: ThemeMode.DARK)
    view = SettingsView(
        controller,
        store,
        autostart_registry=registry if registry is not None else FakeRegistry(),
        frozen=frozen,
        executable=EXE,
        on_hotkey=on_hotkey,
    )
    return view, store


def test_groups_are_in_mockup_order(application: QApplication, tmp_path: Path) -> None:
    view, _ = _view(application, tmp_path)
    assert view.group_labels() == [
        "ВНЕШНИЙ ВИД",
        "ОКНО И ЗАПУСК",
        "ГОРЯЧИЕ КЛАВИШИ",
        "СПИСОК БАЗ",
    ]


def test_tray_toggle_persists(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path)
    assert view.tray_checkbox().isChecked() is True

    view.tray_checkbox().setChecked(False)

    assert store.settings.close_to_tray is False


def test_tray_toggle_starts_from_file(application: QApplication, tmp_path: Path) -> None:
    save_settings(tmp_path / "settings.json", Settings(close_to_tray=False))
    view, _ = _view(application, tmp_path)
    assert view.tray_checkbox().isChecked() is False


def test_autostart_disabled_when_not_frozen(
    application: QApplication, tmp_path: Path
) -> None:
    """Из исходников автозапуск недоступен: ссылка в реестре протухнет (спека §3.3)."""
    view, _ = _view(application, tmp_path, frozen=False)
    assert view.autostart_checkbox().isEnabled() is False
    assert "установленной версии" in view.autostart_note()


def test_autostart_reflects_registry(application: QApplication, tmp_path: Path) -> None:
    registry = FakeRegistry({VALUE_NAME: autostart_command(EXE)})
    view, _ = _view(application, tmp_path, registry=registry)
    assert view.autostart_checkbox().isChecked() is True


def test_autostart_writes_registry_not_settings_file(
    application: QApplication, tmp_path: Path
) -> None:
    """Защитный: истина автозапуска — реестр, в файл он не попадает (спека §3.1).

    Мутация: добавить в `Settings` поле автозапуска и писать его в store —
    тест обязан упасть на присутствии ключа в JSON.
    """
    registry = FakeRegistry()
    view, store = _view(application, tmp_path, registry=registry)

    view.autostart_checkbox().setChecked(True)

    assert registry.values[VALUE_NAME] == autostart_command(EXE)
    # Проверки JSON-файла НЕДОСТАТОЧНО: `save_settings` перечисляет ключи
    # явным списком, и лишнее поле в `Settings` в файл не протекло бы
    # никогда — тест остался бы зелёным на сломанной реализации. Сравнение
    # всего store целиком ловит сам факт «автозапуск потрогал настройки».
    assert store.settings == Settings()
    import json

    payload = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "autostart" not in payload


def test_autostart_write_failure_rolls_back_toggle(
    application: QApplication, tmp_path: Path
) -> None:
    """Отказ записи не смеет оставить включённый тумблер (спека §3.6)."""
    view, _ = _view(application, tmp_path, registry=BrokenRegistry())

    view.autostart_checkbox().setChecked(True)

    assert view.autostart_checkbox().isChecked() is False
    assert "отказано" in view.autostart_note()


def test_unreadable_registry_blocks_the_toggle(
    application: QApplication, tmp_path: Path
) -> None:
    """Состояние неизвестно — «выключено» как факт показывать нельзя (спека §3.6)."""
    view, _ = _view(application, tmp_path, registry=UnreadableRegistry())
    assert view.autostart_checkbox().isEnabled() is False
    assert view.autostart_checkbox().isChecked() is False
    assert "отказано" in view.autostart_note()


def test_hotkey_field_shows_saved_value(
    application: QApplication, tmp_path: Path
) -> None:
    save_settings(tmp_path / "settings.json", Settings(hotkey="Win+F9"))
    view, _ = _view(application, tmp_path)
    assert view.hotkey_edit().text() == "Win+F9"


def test_hotkey_capture_saves_and_reports_success(
    application: QApplication, tmp_path: Path
) -> None:
    view, store = _view(application, tmp_path, on_hotkey=lambda _text: None)

    view.hotkey_edit().captured.emit("Ctrl+Alt+Y")

    assert store.settings.hotkey == "Ctrl+Alt+Y"
    assert view.hotkey_note() == ""


def test_busy_hotkey_is_saved_with_honest_status(
    application: QApplication, tmp_path: Path
) -> None:
    """Занятое сочетание сохраняется — оно может освободиться (спека §4.2)."""
    view, store = _view(
        application, tmp_path, on_hotkey=lambda _text: "сочетание занято другим приложением"
    )

    view.hotkey_edit().captured.emit("Ctrl+Alt+Y")

    assert store.settings.hotkey == "Ctrl+Alt+Y"
    assert "занято" in view.hotkey_note()


def test_hotkey_can_be_cleared(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path, on_hotkey=lambda _text: None)

    view.hotkey_edit().captured.emit("")

    assert store.settings.hotkey == ""
    assert view.hotkey_edit().text() == HotkeyEdit.DISABLED_TEXT


def test_recent_spinbox_bounds_and_persistence(
    application: QApplication, tmp_path: Path
) -> None:
    view, store = _view(application, tmp_path)
    spin = view.recent_spinbox()
    assert (spin.minimum(), spin.maximum()) == (0, 50)
    assert spin.value() == 10

    spin.setValue(0)

    assert store.settings.recent_limit == 0
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `uv run pytest tests/ui/test_settings_view.py -q`
Expected: FAIL — `TypeError: SettingsView.__init__() got an unexpected keyword argument 'autostart_registry'`

- [ ] **Step 3: Реализовать раздел**

Заменить `src/onecstarter/ui/settings_view.py` целиком:

```python
"""Раздел «Настройки»: четыре группы утверждённого мокапа.

Порядок групп — мокапа: ВНЕШНИЙ ВИД, ОКНО И ЗАПУСК, ГОРЯЧИЕ КЛАВИШИ,
СПИСОК БАЗ. Собственных запечённых цветов нет, красит общий stylesheet
(#ThemeSeg, #SettingsGroupLabel, #SettingsNote).

Раздел не знает ни о `GlobalHotkey`, ни о том, как поднято окно: сочетание
уходит наружу через `on_hotkey`, а обратно приходит текст отказа либо `None`.
Занятость сочетания — свойство системы, и решать о ней разделу нечем.

Автозапуск идёт мимо store: его истина — реестр (спека §3.1). Реестр
подаётся инъекцией — тесты не трогают живой HKCU.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services import autostart
from onecstarter.services.settings import RECENT_MAX, RECENT_MIN, ThemeMode
from onecstarter.ui.hotkey_edit import HotkeyEdit
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.theme_controller import ThemeController

CHOICES = (
    (ThemeMode.AUTO, "Авто"),
    (ThemeMode.LIGHT, "Светлая"),
    (ThemeMode.DARK, "Тёмная"),
)

NOT_FROZEN_NOTE = "Доступно в установленной версии — из исходников ссылка в реестре протухнет"


class SettingsView(QWidget):
    def __init__(
        self,
        controller: ThemeController,
        store: SettingsStore,
        *,
        autostart_registry: autostart.Registry | None = None,
        frozen: bool = False,
        executable: str = "",
        on_hotkey: Callable[[str], str | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._store = store
        self._registry = autostart_registry
        self._frozen = frozen
        self._executable = executable
        self._on_hotkey = on_hotkey
        self._buttons: list[QPushButton] = []
        self._group_labels: list[str] = []

        header = QLabel("Настройки")
        header_font = header.font()
        header_font.setPointSize(13)
        header_font.setBold(True)
        header.setFont(header_font)
        self._path_label = QLabel(f"{store.path} · применяются сразу")
        self._path_label.setObjectName("SettingsSub")

        self._status = QLabel("")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(header)
        layout.addWidget(self._path_label)
        layout.addSpacing(10)
        self._layout = layout

        self._add_group("ВНЕШНИЙ ВИД")
        self._add_row(
            "Тема",
            "«Авто» следует теме Windows и переключается вместе с ней",  # noqa: RUF001
            self._build_theme_segment(),
        )

        self._add_group("ОКНО И ЗАПУСК")
        self._tray = QCheckBox()
        self._tray.setChecked(store.settings.close_to_tray)
        self._tray.toggled.connect(self._choose_tray)
        self._add_row(
            "Закрытие окна сворачивает в трей",
            "Выключено — крестик завершает программу, глобальный вызов перестаёт работать",
            self._tray,
        )

        self._autostart = QCheckBox()
        self._autostart_note = QLabel("")
        self._autostart_note.setObjectName("SettingsNote")
        self._autostart_note.setWordWrap(True)
        self._add_row(
            "Запускать при входе в Windows",
            "Программа стартует в трей: вызов и запуск избранного доступны сразу",
            self._autostart,
            extra=self._autostart_note,
        )
        self._sync_autostart()
        self._autostart.toggled.connect(self._choose_autostart)

        self._add_group("ГОРЯЧИЕ КЛАВИШИ")
        self._hotkey = HotkeyEdit()
        self._hotkey.set_combination(store.settings.hotkey)
        self._hotkey.captured.connect(self._choose_hotkey)
        self._hotkey_note = QLabel("")
        self._hotkey_note.setObjectName("SettingsNote")
        self._hotkey_note.setWordWrap(True)
        self._add_row(
            "Глобальный вызов окна",
            "Только с модификатором. Занятое сочетание — сообщение, а не тишина",
            self._hotkey,
            extra=self._hotkey_note,
        )

        self._add_group("СПИСОК БАЗ")
        self._recent = QSpinBox()
        self._recent.setRange(RECENT_MIN, RECENT_MAX)
        self._recent.setValue(store.settings.recent_limit)
        self._recent.valueChanged.connect(self._choose_recent)
        self._add_row(
            "Записей в «Недавних»",
            "0 — ветка «Недавние» не показывается вовсе",
            self._recent,
        )

        layout.addWidget(self._status)
        layout.addStretch(1)

        controller.changed.connect(self._sync)
        store.changed.connect(self._sync)

    # --- сборка раскладки ------------------------------------------------

    def _add_group(self, title: str) -> None:
        label = QLabel(title)
        label.setObjectName("SettingsGroupLabel")
        self._layout.addWidget(label)
        self._group_labels.append(title)

    def _add_row(
        self, title: str, note: str, control: QWidget, *, extra: QWidget | None = None
    ) -> None:
        row_title = QLabel(title)
        row_note = QLabel(note)
        row_note.setObjectName("SettingsNote")
        row_note.setWordWrap(True)

        body = QVBoxLayout()
        body.setSpacing(1)
        body.addWidget(row_title)
        body.addWidget(row_note)
        if extra is not None:
            body.addWidget(extra)

        row = QHBoxLayout()
        row.addLayout(body, stretch=1)
        row.addWidget(control, alignment=Qt.AlignmentFlag.AlignTop)
        self._layout.addLayout(row)

    def _build_theme_segment(self) -> QWidget:
        seg = QWidget()
        seg.setObjectName("ThemeSeg")
        seg_layout = QHBoxLayout(seg)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        buttons = QButtonGroup(self)
        buttons.setExclusive(True)
        for mode, label in CHOICES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(mode is self._controller.mode)
            button.clicked.connect(lambda _checked=False, m=mode: self._choose_theme(m))
            buttons.addButton(button)
            seg_layout.addWidget(button)
            self._buttons.append(button)
        return seg

    # --- доступ для тестов ------------------------------------------------

    def group_labels(self) -> list[str]:
        return list(self._group_labels)

    def theme_buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def tray_checkbox(self) -> QCheckBox:
        return self._tray

    def autostart_checkbox(self) -> QCheckBox:
        return self._autostart

    def hotkey_edit(self) -> HotkeyEdit:
        return self._hotkey

    def recent_spinbox(self) -> QSpinBox:
        return self._recent

    def status_text(self) -> str:
        return self._status.text()

    def path_text(self) -> str:
        return self._path_label.text()

    def autostart_note(self) -> str:
        return self._autostart_note.text()

    def hotkey_note(self) -> str:
        return self._hotkey_note.text()

    # --- реакции ----------------------------------------------------------

    def _choose_theme(self, mode: ThemeMode) -> None:
        self._controller.set_mode(mode)

    def _choose_tray(self, checked: bool) -> None:
        self._store.update(close_to_tray=checked)

    def _choose_recent(self, value: int) -> None:
        self._store.update(recent_limit=value)

    def _choose_hotkey(self, text: str) -> None:
        """Сохранить выбранное и показать, что ответила система.

        Занятое сочетание сохраняется (спека §4.2): оно освободится, когда
        закроется конфликтующая программа, и заставлять пользователя
        подбирать свободное прямо сейчас незачем. Врать «работает» при этом
        нельзя — отказ виден строкой рядом с полем.
        """  # noqa: RUF002
        self._store.update(hotkey=text)
        problem = self._on_hotkey(text) if self._on_hotkey is not None else None
        self._hotkey_note.setText(problem or "")

    def _choose_autostart(self, checked: bool) -> None:
        if self._registry is None:
            return
        try:
            if checked:
                autostart.enable(self._registry, self._executable)
            else:
                autostart.disable(self._registry)
        except OSError as error:
            self._autostart_note.setText(f"Не удалось изменить автозапуск: {error}")  # noqa: RUF001
            self._sync_autostart()
            return
        self._autostart_note.setText("")

    def _sync_autostart(self) -> None:
        """Привести тумблер к факту: сборка, реестр, доступность чтения."""
        if not self._frozen or self._registry is None:
            self._set_autostart_state(checked=False, enabled=False, note=NOT_FROZEN_NOTE)
            return
        try:
            enabled = autostart.is_enabled(self._registry)
        except OSError as error:
            # Состояние неизвестно: показать «выключено» как факт нельзя
            # (спека §3.6) — тумблер запирается, причина остаётся на экране.
            self._set_autostart_state(
                checked=False,
                enabled=False,
                note=f"Не удалось прочитать автозапуск: {error}",  # noqa: RUF001
            )
            return
        self._set_autostart_state(checked=enabled, enabled=True, note=self._autostart_note.text())

    def _set_autostart_state(self, *, checked: bool, enabled: bool, note: str) -> None:
        # Сигнал глушится: приведение тумблера к факту — не выбор
        # пользователя, и отвечать на него записью в реестр нельзя.
        blocked = self._autostart.blockSignals(True)
        self._autostart.setChecked(checked)
        self._autostart.blockSignals(blocked)
        self._autostart.setEnabled(enabled)
        self._autostart_note.setText(note)

    def _sync(self) -> None:
        """Привести органы к текущим настройкам (смена темы из трея и т. п.).

        Сигналы органов глушатся: приведение к состоянию — не выбор
        пользователя, и отвечать на него новой записью в файл значило бы
        зациклить `changed` → `update` → `changed`.
        """  # noqa: RUF002
        for button, (mode, _label) in zip(self._buttons, CHOICES, strict=True):
            button.setChecked(mode is self._controller.mode)
        settings = self._store.settings

        blocked = self._tray.blockSignals(True)
        self._tray.setChecked(settings.close_to_tray)
        self._tray.blockSignals(blocked)

        blocked = self._recent.blockSignals(True)
        self._recent.setValue(settings.recent_limit)
        self._recent.blockSignals(blocked)

        self._hotkey.set_combination(settings.hotkey)
        self._status.setText(self._store.last_save_error or "")
```

- [ ] **Step 4: Догнать вызов в app.py**

В `src/onecstarter/ui/app.py` строку `settings_view = SettingsView(controller)` заменить на:

```python
    settings_view = SettingsView(
        controller,
        store,
        autostart_registry=autostart.WindowsRegistry(),
        frozen=bool(getattr(sys, "frozen", False)),
        executable=sys.executable,
    )
```

с импортом `from onecstarter.services import autostart`. Проводку `on_hotkey`
поставит Task 9.

- [ ] **Step 5: Запустить и убедиться, что проходит**

Run: `uv run pytest tests/ui/test_settings_view.py -q; uv run pytest -q`
Expected: коды выхода 0

- [ ] **Step 6: Линт, типы, коммит**

Run: `uv run ruff check .; uv run mypy`
Expected: коды выхода 0

```bash
git add src/onecstarter/ui/settings_view.py src/onecstarter/ui/app.py tests/ui/test_settings_view.py
git commit -m "feat: четыре группы настроек в разделе по мокапу"
```

---

### Task 9: Проводка приложения и тихий автозапуск

**Files:**
- Modify: `src/onecstarter/ui/app.py` (`_build_main_window`, `main`)
- Modify: `src/onecstarter/__main__.py` (разбор `--autostart`)
- Modify: `tests/ui/test_app.py`, `tests/unit/test_entry_point.py`

**Interfaces:**
- Consumes: всё из Task 1–8.
- Produces: `has_autostart_flag(argv: Sequence[str]) -> bool` в `__main__`;
  `main(argv=None, *, start_hidden: bool = False) -> int` в `ui/app.py`;
  `_build_main_window` возвращает прежнюю пару `(MainWindow, StartupTasks)`.

Спека §2, §3.4, §4.2–4.4.

- [ ] **Step 1: Написать падающие тесты разбора флага**

Дописать в `tests/unit/test_entry_point.py`:

```python
def test_autostart_flag_detected() -> None:
    assert has_autostart_flag(["--autostart"]) is True
    assert has_autostart_flag(["--autostart", "--ib-name", "Демо"]) is True


def test_autostart_flag_absent() -> None:
    assert has_autostart_flag([]) is False
    assert has_autostart_flag(["--ib-name", "Демо"]) is False
    assert has_autostart_flag(["--autostart-something"]) is False
```

и добавить `has_autostart_flag` в импорт из `onecstarter.__main__`.

- [ ] **Step 2: Написать падающие тесты проводки**

Дописать в `tests/ui/test_app.py`:

```python
def _settings_path(tmp_path):
    """Куда смотрит build_runtime при APPDATA=tmp_path (см. ui/app.py)."""
    return tmp_path / "OneCStarter" / "settings.json"


def test_close_to_tray_follows_the_setting(qapp, tmp_path, monkeypatch) -> None:
    """Настройка выключена — крестик завершает программу (спека §2)."""
    save_settings(_settings_path(tmp_path), Settings(close_to_tray=False))
    window = _window_with_settings(qapp, tmp_path, monkeypatch, tray_available=True)
    assert window.close_to_tray is False


def test_close_to_tray_requires_available_tray(qapp, tmp_path, monkeypatch) -> None:
    """Трея нет — настройка ведёт себя как выключенная (спека §2)."""
    save_settings(_settings_path(tmp_path), Settings(close_to_tray=True))
    window = _window_with_settings(qapp, tmp_path, monkeypatch, tray_available=False)
    assert window.close_to_tray is False


def test_close_to_tray_updates_without_restart(qapp, tmp_path, monkeypatch) -> None:
    window = _window_with_settings(qapp, tmp_path, monkeypatch, tray_available=True)
    assert window.close_to_tray is True

    window.settings_store.update(close_to_tray=False)

    assert window.close_to_tray is False


def test_disabled_hotkey_is_not_registered(qapp, tmp_path, monkeypatch) -> None:
    """Защитный: пустое сочетание — регистрации нет (спека §4.1).

    Мутация: в проводке звать rebind всегда с дефолтным сочетанием —
    тест обязан упасть на непустом списке регистраций.
    """
    save_settings(_settings_path(tmp_path), Settings(hotkey=""))
    registered: list[tuple[int, int]] = []
    window = _window_with_settings(
        qapp, tmp_path, monkeypatch, tray_available=True, registrations=registered
    )
    assert registered == []
    assert window.global_hotkey.registered is False


def test_busy_hotkey_shows_balloon_and_tooltip(qapp, tmp_path, monkeypatch) -> None:
    """Занято на старте — балун, а не тишина (спека §4.3)."""
    messages: list[tuple[str, str]] = []
    window = _window_with_settings(
        qapp,
        tmp_path,
        monkeypatch,
        tray_available=True,
        register_result=0,
        messages=messages,
    )
    assert messages, "балун при занятом сочетании обязателен"
    assert "занят" in messages[0][1]
```

Помощник `_window_with_settings` дописать рядом с существующими помощниками
файла (посмотреть, как соседние тесты собирают окно, и повторить приём):

```python
def _window_with_settings(
    qapp,
    tmp_path,
    monkeypatch,
    *,
    tray_available: bool,
    register_result: int = 1,
    registrations: list | None = None,
    messages: list | None = None,
):
    """Собрать окно поверх подменённых трея и user32.

    Настоящая регистрация хоткея и настоящий трей в offscreen-тесте
    недопустимы: первая отобрала бы сочетание у машины разработчика,
    второй недоступен под offscreen-платформой.
    """
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: tray_available)
    )
    if messages is not None:
        monkeypatch.setattr(
            QSystemTrayIcon,
            "showMessage",
            lambda self, title, text, *args: messages.append((title, text)),
        )

    def register(hwnd, hotkey_id, modifiers, vk):
        if registrations is not None:
            registrations.append((modifiers, vk))
        return register_result

    monkeypatch.setattr(
        "onecstarter.ui.app.GlobalHotkey",
        lambda callback: GlobalHotkey(
            callback, register=register, unregister=lambda hwnd, hotkey_id: 1
        ),
    )
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)
    window, _tasks = _build_main_window(qapp, runtime, env)
    return window
```

`runtime.settings` указывает в `tmp_path/OneCStarter/settings.json` — файл
настроек в тестах писать по этому пути. Каталог создавать не нужно:
`save_settings` сама делает `parent.mkdir(parents=True, exist_ok=True)`.

- [ ] **Step 3: Запустить и убедиться, что падает**

Run: `uv run pytest tests/unit/test_entry_point.py tests/ui/test_app.py -q`
Expected: FAIL — `ImportError: cannot import name 'has_autostart_flag'`

- [ ] **Step 4: Реализовать разбор флага**

В `src/onecstarter/__main__.py` добавить константу рядом с `SMOKE_OPTION`:

```python
AUTOSTART_OPTION = "--autostart"
```

и функцию после `parse_ib_name`:

```python
def has_autostart_flag(argv: Sequence[str]) -> bool:
    """Запуск при входе в Windows: окно не показывается (спека §3.4).

    Флаг без значения, поэтому сравнение точное: `--autostart-something`
    нашим ключом не является и молча тихий старт не включает.
    """  # noqa: RUF002
    return AUTOSTART_OPTION in argv
```

и в `_dispatch` заменить ветку обычного окна:

```python
    name = parse_ib_name(arguments)
    if name is None:
        from onecstarter.ui.app import main as show_window

        return show_window(start_hidden=has_autostart_flag(arguments))
```

Обновить докстринг модуля: в перечислении режимов после «без аргументов —
обычное окно» дописать «(с `--autostart` — то же, но окно не показывается:
программа живёт в трее)».

- [ ] **Step 5: Реализовать проводку**

В `src/onecstarter/ui/app.py` заменить блок трея и хоткея (строки ~348–365)
на:

```python
    tray = create_tray(
        window,
        favorites,
        view.launch_key,
        application.quit,
        theme_mode=lambda: controller.mode,
        on_theme=controller.set_mode,
    )
    hotkey = GlobalHotkey(window.show_and_focus_search)
    application.installNativeEventFilter(hotkey)
    application.aboutToQuit.connect(hotkey.dispose)
    # Ссылки на окне — тестам и на время жизни процесса: без них store
    # и хоткей собрал бы сборщик мусора сразу после выхода из функции.
    window.settings_store = store
    window.global_hotkey = hotkey
    last_recent_limit = store.settings.recent_limit

    def apply_close_to_tray() -> None:
        # Трея нет — настройка ведёт себя как выключенная (спека §2):
        # спрятать окно, из которого его нечем вернуть, значит потерять
        # программу с экрана.
        window.close_to_tray = store.settings.close_to_tray and tray is not None

    def rebuild_if_recent_limit_changed() -> None:
        """Дерево перестраивается только когда изменился лимит «Недавних».

        **Исправлено 20.08.2026 по находке ревью Task 9.** Первая редакция
        плана вешала на `store.changed` безусловный `view.rebuild()`. Замер
        ревьюера: клик по теме давал ДВЕ перестройки дерева — одна уже идёт
        через `on_theme_changed` → `apply_palette`, — а смена сочетания
        хоткея или поведения крестика дёргала полную перестройку, хотя
        к дереву отношения не имеет. Настройка меняет только показ
        «Недавних» (спека §5); всё остальное дерева не касается.
        """  # noqa: RUF002
        nonlocal last_recent_limit
        if store.settings.recent_limit == last_recent_limit:
            return
        last_recent_limit = store.settings.recent_limit
        view.rebuild()

    def apply_hotkey(text: str) -> str | None:
        """Перевесить хоткей. Текст отказа либо None."""
        spec = parse_hotkey(text)
        if spec is None:
            hotkey.rebind(None)
            _set_tray_tooltip(tray, None)
            return None
        if hotkey.rebind(spec):
            _set_tray_tooltip(tray, text)
            return None
        _set_tray_tooltip(tray, text, busy=True)
        return f"Сочетание {text} занято другим приложением"

    apply_close_to_tray()
    store.changed.connect(apply_close_to_tray)
    store.changed.connect(rebuild_if_recent_limit_changed)
    settings_view.set_hotkey_handler(apply_hotkey)

    problem = apply_hotkey(store.settings.hotkey)
    if problem is not None:
        settings_view.report_hotkey_problem(problem)
        if tray is not None:
            # Балун, а не модальное окно: при тихом автозапуске диалог
            # встречал бы пользователя при каждом входе в систему
            # (спека §4.3). **[Проверено, 19.08.2026, эксперимент §7]**
            tray.showMessage("OneCStarter", problem, QSystemTrayIcon.MessageIcon.Warning, 7000)
```

Заменить создание `settings_view` (Task 8) на вариант без `on_hotkey`
и добавить туда `recent_limit`-провайдер для `BasesView`:

```python
    view = BasesView(
        runtime.workspace,
        installations=None,
        cfg_rules=runtime.cfg_rules,
        recent_limit=lambda: store.settings.recent_limit,
        palette=controller.palette,
    )
```

Добавить помощник модуля перед `_build_main_window`:

```python
def _set_tray_tooltip(
    tray: QSystemTrayIcon | None, combination: str | None, *, busy: bool = False
) -> None:
    if tray is None:
        return
    if combination is None:
        tray.setToolTip("OneCStarter")
    elif busy:
        tray.setToolTip(f"OneCStarter — {combination} занято другим приложением")
    else:
        tray.setToolTip(f"OneCStarter — {combination}")
```

Импорты дописать: `from PySide6.QtWidgets import QSystemTrayIcon`,
`from onecstarter.services.hotkeys import parse_hotkey`. Импорт
`DEFAULT_RECENT_LIMIT`, поставленный времянкой в Task 4, теперь не нужен —
убрать, иначе `ruff` укажет на неиспользуемый.

Заменить `main`:

```python
def main(argv: list[str] | None = None, *, start_hidden: bool = False) -> int:
    """Обычный запуск. `start_hidden` — старт при входе в Windows (спека §3.4).

    Тихий старт показывает окно всё равно, если трея нет: невидимый процесс,
    который нечем вызвать, пользователю не принадлежит.
    """  # noqa: RUF002
    application = QApplication(argv if argv is not None else sys.argv)
    ...  # существующее тело до _build_main_window без изменений
    window, tasks = _build_main_window(application, runtime, os.environ)
    if start_hidden and window.close_to_tray:
        _log.info("тихий старт: окно скрыто, программа в трее")
    else:
        window.show()
        _log.info("окно показано")
    tasks.start()
    return application.exec()
```

`window.close_to_tray` здесь — точный признак «трей есть и им можно
пользоваться»: он уже посчитан `apply_close_to_tray`.

В `MainWindow.__init__` (`src/onecstarter/ui/shell.py`) после
`self.close_to_tray = False` добавить объявления, чтобы mypy и читатель
знали об этих полях:

```python
        # Проставляются сборкой приложения (ui/app.py): окну они нужны
        # только как владельцу времени жизни, поведение их не читает.
        self.settings_store: object | None = None
        self.global_hotkey: object | None = None
```

- [ ] **Step 6: Дописать два метода разделу настроек**

Параметр `on_hotkey` в конструкторе **остаётся** (им пользуются тесты
Task 8, где обработчик известен заранее). Добавляются два метода: сборка
приложения создаёт раздел раньше, чем появляется `GlobalHotkey`, и ставит
обработчик вторым шагом. В `src/onecstarter/ui/settings_view.py` дописать:

```python
    def set_hotkey_handler(self, handler: Callable[[str], str | None]) -> None:
        """Кто перевешивает хоткей. Ставится сборкой приложения после создания."""
        self._on_hotkey = handler

    def report_hotkey_problem(self, problem: str) -> None:
        """Показать отказ, случившийся не по нажатию в разделе (занято на старте)."""
        self._hotkey_note.setText(problem)
```

- [ ] **Step 7: Запустить и убедиться, что проходит**

Run: `uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: коды выхода 0

- [ ] **Step 8: Коммит**

```bash
git add src/onecstarter/ui/app.py src/onecstarter/ui/shell.py src/onecstarter/ui/settings_view.py src/onecstarter/__main__.py tests/ui/test_app.py tests/unit/test_entry_point.py
git commit -m "feat: проводка настроек в приложение и тихий старт при автозапуске"
```

---

### Task 10: Поставка — деинсталляция и smoke

**Files:**
- Modify: `build/installer.iss`
- Modify: `build/smoke.py`

**Interfaces:**
- Consumes: `RUN_KEY`, `VALUE_NAME` из Task 3, `--autostart` из Task 9.
- Produces: ничего для кода.

Спека §3.3, §3.5.

- [ ] **Step 1: Дописать удаление значения в установщик**

В `build/installer.iss` после секции `[Icons]` добавить:

```
[Registry]
; Значение автозапуска пишет само приложение (спека §3.1: истина — реестр).
; Установщик его не создаёт (dontcreatekey), но обязан убрать при удалении:
; иначе после деинсталляции Windows будет пытаться запустить стёртый exe.
; **[Из документации Inno Setup]** — проверяется шагом 3 этой задачи.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OneCStarter"; Flags: dontcreatekey uninsdeletevalue
```

- [ ] **Step 2: Дописать проверку тихого старта в smoke**

В `build/smoke.py` в `main()` перед `print("smoke: OK")` добавить:

```python
        # Собранный exe обязан принять --autostart и завершиться штатно.
        # Это НЕ проверка тихого старта: `--smoke` разбирается раньше
        # (`__main__._dispatch`) и до ветки окна дело не доходит вовсе.
        # Проверяется ровно одно — новый ключ не ломает разбор аргументов
        # в сборке. Само поведение тихого старта покрыто тестом
        # `test_entry_point.py` и ручным прогоном при завершении вехи.
        quiet_appdata = Path(scratch) / "appdata-quiet"
        quiet_env = dict(env)
        quiet_env["APPDATA"] = str(quiet_appdata)
        quiet = subprocess.run(
            [str(console_exe), "--autostart", "--smoke", str(out)],
            env=quiet_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if quiet.returncode != 0:
            print(f"smoke: --autostart вернул {quiet.returncode}\n{quiet.stderr}")
            return 1
```

Дописать в докстринг модуля пункт `(4) exe принимает --autostart и завершается
штатно`.

- [ ] **Step 3: Проверить сборку целиком**

Run: `powershell -ExecutionPolicy Bypass -File build/build.ps1`
Expected: сборка проходит, `smoke: OK`, код выхода 0.

Если Inno Setup на машине нет — собрать хотя бы PyInstaller-часть и smoke,
а проверку `[Registry]` пометить как невыполненную в отчёте задачи;
в спеке §3.5 метка «не проверено» остаётся до фактической проверки.

- [ ] **Step 4: Проверить `sys.frozen` в собранном экземпляре**

Run: `dist\OneCStarter\OneCStarterc.exe --smoke %TEMP%\ocs-frozen`
Ожидается код 0. Затем открыть собранный `OneCStarter.exe` вручную и
убедиться, что в разделе «Настройки» тумблер автозапуска **активен**
(из исходников он заблокирован). Это подтверждение факта §3.3
(«[Из документации PyInstaller] в собранном exe `sys.frozen == True`»)
— повысить метку до «проверено» с датой в спеке.

- [ ] **Step 5: Коммит**

```bash
git add build/installer.iss build/smoke.py docs/superpowers/specs/2026-08-19-settings-functions-design.md
git commit -m "build: удаление значения автозапуска при деинсталляции и smoke тихого старта"
```

---

### Task 11: Мутационная проверка защитных тестов

**Files:**
- Modify: `docs/tasks.md`

**Interfaces:**
- Consumes: тесты из Task 5, 6, 8, 9.
- Produces: раздел с записью проверок в `docs/tasks.md`.

Правило проекта: мутацию ставит **не автор теста**; порядок — правка → зелёные →
коммит → мутация → откат; результат пишется в коммитуемый документ (гитигнорного
леджера недостаточно — находка ревью 18.08).

Четыре защитных теста и их мутации:

| № | Тест | Мутация |
| --- | --- | --- |
| 1 | `test_settings_store.py::test_update_keeps_other_fields` | В `SettingsStore.update` заменить `replace(self._settings, **changes)` на `Settings(**changes)` |
| 2 | `test_hotkey.py::test_rebind_to_none_disables` | В `GlobalHotkey.rebind` убрать ветку `if spec is None: return True` |
| 3 | `test_settings_view.py::test_autostart_writes_registry_not_settings_file` | В `_choose_autostart` дописать `self._store.update(autostart=checked)` (и поле в `Settings`) — **выполнена в Task 8, см. сноску** |
| 4 | `test_app.py::test_disabled_hotkey_is_not_registered` | В `apply_hotkey` заменить `parse_hotkey(text)` на `parse_hotkey(text) or parse_hotkey(DEFAULT_HOTKEY)` |

> **Исправлено 20.08.2026 по находке Task 8.** Мутация №3 в первой редакции
> таблицы была **бессильной**: тест проверял только отсутствие ключа в JSON,
> а `save_settings` перечисляет ключи явным списком — лишнее поле в `Settings`
> в файл не протекло бы никогда, и тест остался бы зелёным на сломанной
> реализации. Тест усилен сравнением `store.settings == Settings()`, мутация
> проведена в Task 8 и подтверждена ревьюером; здесь её не повторять, запись
> перенести из леджера. Урок общий: тест «поле не попало в файл» проверяет
> сериализатор, а не то, трогали ли настройки.

- [ ] **Step 1: Убедиться, что дерево чистое и всё зелёное**

Run: `git status --short; uv run pytest -q`
Expected: пусто и код выхода 0. Мутации ставятся только поверх чистого дерева —
иначе непонятно, что откатывать.

- [ ] **Step 2: Мутация 1 — writer**

Внести мутацию №1 из таблицы. Запустить:

Run: `uv run pytest tests/ui/test_settings_store.py::test_update_keeps_other_fields -q`
Expected: FAIL. Записать, **на чём именно** упал (какое поле и с каким значением).

Откатить: `git checkout -- src/onecstarter/ui/settings_store.py`

- [ ] **Step 3: Мутация 2 — выключенный хоткей**

Внести мутацию №2. Запустить:

Run: `uv run pytest tests/ui/test_hotkey.py::test_rebind_to_none_disables -q`
Expected: FAIL — падение на непустом `calls["register"]`.

Откатить: `git checkout -- src/onecstarter/ui/hotkey.py`

- [ ] **Step 4: Мутация 3 — автозапуск в файле**

Внести мутацию №3. Запустить:

Run: `uv run pytest tests/ui/test_settings_view.py::test_autostart_writes_registry_not_settings_file -q`
Expected: FAIL — ключ автозапуска оказался в JSON.

Откатить: `git checkout -- src/onecstarter/ui/settings_view.py src/onecstarter/services/settings.py`

- [ ] **Step 5: Мутация 4 — молчаливый дефолт хоткея**

Внести мутацию №4. Запустить:

Run: `uv run pytest tests/ui/test_app.py::test_disabled_hotkey_is_not_registered -q`
Expected: FAIL — список регистраций непуст.

Откатить: `git checkout -- src/onecstarter/ui/app.py`

- [ ] **Step 6: Убедиться, что откат полный**

Run: `git status --short; uv run pytest -q; uv run ruff check .; uv run mypy`
Expected: `git status` пуст, три кода выхода 0.

- [ ] **Step 7: Записать результаты**

В `docs/tasks.md` в раздел записей мутационных проверок (там, где лежит
запись от 18.08.2026) дописать блок вехи «Функции настроек» с датой,
четырьмя строками таблицы выше и **фактическим текстом падения** каждой —
не «упал», а на каком утверждении и с каким значением.

- [ ] **Step 8: Коммит**

```bash
git add docs/tasks.md
git commit -m "docs: мутационные проверки защитных тестов вехи функций настроек"
```

---

## Завершение вехи

После Task 11:

1. **`verification-before-completion`** — прогнать три команды, показать коды выхода,
   не заявлять о готовности без вывода.
2. **Ручной прогон на живой платформе** (с согласия заказчика): смена сочетания,
   занятое сочетание, выключение хоткея, крестик при обеих позициях тумблера трея,
   `0` в «Недавних», автозапуск в собранной версии.
3. **Финальное ревью всей ветки на самой сильной модели** — до слияния (правило проекта).
4. **`finishing-a-development-branch`** — решение о слиянии.

## Self-review плана

**Покрытие спеки:**

| Параграф спеки | Задача |
| --- | --- |
| §1 объём и дефолты | Task 2 (дефолты), Task 8 (порядок групп) |
| §2 закрытие в трей | Task 8 (тумблер), Task 9 (конъюнкция с доступностью трея) |
| §3.1 истина в реестре | Task 3, защитный тест в Task 8 |
| §3.2 механика значения | Task 3 |
| §3.3 только в собранной версии | Task 8 (`frozen`), Task 10 (проверка в сборке) |
| §3.4 тихий старт | Task 9 |
| §3.5 деинсталляция | Task 10 |
| §3.6 отказы реестра | Task 8 (обе ветки: запись и чтение) |
| §4.1 правило и хранение | Task 1, Task 2, Task 7 |
| §4.2 смена на лету | Task 6, Task 8, Task 9 |
| §4.3 занято на старте | Task 9 (балун + статус + тултип) |
| §4.4 поведение вызова | без изменений — `show_and_focus_search` уже есть |
| §4.5 кривое значение | Task 2 |
| §5 «Недавние» | Task 4, Task 8 |
| §6.1 схема | Task 2 |
| §6.2 SettingsStore | Task 5 |
| §7 эксперименты | выполнены до плана |
| §8 тестирование | во всех задачах; мутации — Task 11 |
| §9 расхождение с мокапом | Task 8 — `QCheckBox` вместо switch, решение 19.08.2026 |
| §10 границы | ничего за ними не трогается |

**Согласованность имён:** `parse_hotkey`/`format_hotkey`/`HotkeySpec` (Task 1) —
одинаково в Task 2, 6, 7, 9. `SettingsStore.update` (Task 5) — в Task 8, 9.
`autostart.is_enabled/enable/disable` (Task 3) — в Task 8. `recent_limit`
как имя параметра — в Task 4, 8, 9.

**Известные допущения плана, которые исполнитель обязан проверить, а не принять
на веру:**

- Имена помощников в `tests/unit/test_display.py` (`_base_item`, `_stamp`) —
  Task 4, Step 1: посмотреть фактические и использовать их.
- Точные номера строк в `ui/app.py` сдвинутся после каждой задачи — ориентироваться
  по именам функций, а не по числам.
- `QSpinBox.valueChanged` в PySide6 перегружен (`int` и `str`); если mypy или
  ruff ругаются на подключение — подключать `self._recent.valueChanged[int]`.
