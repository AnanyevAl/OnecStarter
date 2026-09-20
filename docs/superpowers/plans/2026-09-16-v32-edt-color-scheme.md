# v3.2 — цветовая схема рабочей области EDT: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** команда «Цветовая схема…» у записи EDT открывает диалог с источниками схем (каталог из настроек: темы IDEA `.xml/.icls/.jar`, `.tmTheme`, `.csi`; «Текущая (рабочая область)»; «По умолчанию EDT»), предпросмотром кода 1С, таблицей 22 цветов, инверсией и сохранением в `.csi`; «Применить» атомарно пишет два prefs-файла рабочей области (и тему окна, если Э9 подтвердит), когда EDT на этой области закрыт; версия `3.2.0` собрана и прошла smoke.

**Architecture:** домен `domain/edt_scheme.py` — чистые функции: модель `ColorKey`/`COLOR_KEYS`/`Scheme`, цвета (`from_hex`, `idea_color`, `fill_missing`, `invert`), парсеры `.csi`/IDEA XML/`.jar`/`.tmTheme` над текстом и байтами, Java properties без потерь (`parse_prefs`/`render_prefs`: чужие ключи, порядок, комментарии, перевод строки сохраняются; тождество `render_prefs(t, {}) == t`). Сервис `services/edt_scheme.py` — `SchemeCatalog` (скан каталога, ленивое чтение) и `WorkspaceSchemes` (чтение/атомарная запись prefs, отказ при занятой области). UI — `ui/edt/scheme_dialog.py` + `ui/edt/scheme_preview.py`, пункт меню в `ui/edt/view.py`, строка «Каталог цветовых схем» в настройках. Эксперименты Э8–Э11 идут **после** домена (Task 4–5): Э8 пишет prefs нашим рендером, Э11 гонит реальные темы через наш разбор — без домена им нечем работать; всё, что эксперименты могут опровергнуть, живёт в константах и таблицах домена (`EDT_DEFAULTS`, `THEME_IDS`, `NEW_PREFS_NEWLINE`, `IDEA_MAP`, `TMTHEME_MAP`) и правится Task 5 до сервиса и UI.

**Tech Stack:** Python 3.13, PySide6 6.11 (только `ui/`), `xml.etree`, `plistlib`, `zipfile`, `json` (стандартная библиотека, внешних зависимостей нет), pytest + pytest-qt (offscreen), ruff, mypy strict вне `ui.*`, PyInstaller + Inno Setup (`build/build.ps1`).

Спека — [2026-09-16-v32-edt-color-scheme-design.md](../specs/2026-09-16-v32-edt-color-scheme-design.md).
Ветка — `feat/2026-09-16-v32` от `master` `96f0755` (v3.1.2). Скил `edt-launch` читать перед
работой с рабочей областью EDT (CLAUDE.md). Веха в `docs/tasks.md` — **T-19**.

## Global Constraints

- **EDT запускается только заказчиком, только с явного разрешения, только на новой тестовой
  рабочей области `E:\tmp\edt-scheme\ws1`** (пустой каталог — EDT создаёт `.metadata` сама,
  [Ф] Э1). Рабочие области заказчика `E:\edt\…` не трогать. Материалы `temp/color/` — читать
  можно, копировать в репозиторий (код, тексты, шаблон предпросмотра, архив тем) — нет
  (спека §10, CLAUDE.md «Границы»).
- **Факт без метки не попадает ни в скил, ни в `docs/`** ([Ф]/[Д]/[?]/[Р]); метка [Ф]
  называет команду или условие. Опровергнутый факт правится в спеке, коде и тесте одним коммитом.
- **Qt только в `ui/`**: `domain/edt_scheme.py` и `services/edt_scheme.py` не импортируют
  PySide6 — оба добавляются в `tests/unit/test_no_qt_in_core.py::CORE`. Домен — чистые функции:
  ни ФС, ни процессов; `zipfile` — над `io.BytesIO`.
- **Без потерь (инвариант 3)**: `render_prefs` сохраняет чужие ключи, комментарии, пустые строки,
  порядок и перевод строки существующего файла; заменяет значения наших ключей на месте; новые
  ключи вставляет по алфавиту среди существующих; новый файл — `eclipse.preferences.version=1`
  плюс ключи по алфавиту, перевод строки `NEW_PREFS_NEWLINE` (CRLF — как у всех пяти файлов
  заказчика [Ф], Eclipse на Windows пишет `newLine()` [Д]; Э8 уточняет). Кодировка чтения и
  записи prefs — `latin-1` (Java properties, любой байт проходит туда и обратно).
- **Атомарная запись (инвариант 4)**: каждый prefs-файл — `config.atomic.atomic_write`;
  каталог `.settings` создаётся; два файла последовательно, первый не откатывается (спека §7).
- **Ключи prefs — ровно 22** (спека §0): 11 токенов
  `com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles.<Имя>.color` (`Builtin\ function` —
  пробел экранирован), 11 цветов редактора; у `Background`, `Foreground`, `SelectionBackground`,
  `SelectionForeground`, `hyperlinkColor` парный `<ключ>.SystemDefault=false`. Ключей вне
  списка не пишем. Короткое имя ключа `Builtin function` в модели и `.csi` — **`Builtinfunction`**
  (совместимость с `.csi` обработки заказчика, где имя без пробела).
- **Цвет IDEA** — hex **без ведущих нулей** (`ff` = `0000ff`, `7f00`, `0`), иногда `#RRGGBB`,
  пустое или `undefined` — не задан ([Ф] 18.09.2026, 641 тема каталога заказчика:
  длины 1–6, 612 значений с `#`, 3 `undefined`); разбирается `idea_color`, не `from_hex`.
- **«По умолчанию EDT»** без правок пользователя = **удаление наших ключей** из prefs
  (`WorkspaceSchemes.reset`) — EDT вернёт свои умолчания любой версии; `EDT_DEFAULTS` служит
  для показа «Текущей» без файлов и предпросмотра умолчаний. Правленные умолчания — обычная
  запись.
- **Тема окна**: `THEME_IDS` содержит только подтверждённые id (тёмная [Ф]; светлая — после Э9);
  комбо «Тема окна» строится по `THEME_IDS` и скрыт, когда там нет ни одного варианта кроме
  «не трогать». Если Э9 покажет, что EDT не читает `themeid` при старте, — `THEME_IDS = {}`.
- **Тексты дословно**: пункт меню «Цветовая схема…» (сразу после «Открыть в EDT»); заголовок
  «Цветовая схема — <имя записи>»; источники «Текущая (рабочая область)», «По умолчанию EDT»;
  подсказки «Каталог схем не задан — Настройки → EDT», «Каталог схем не найден: <путь>»,
  «не удалось прочитать: <причина>», «Закройте EDT: рабочая область занята»; кнопки
  «Инвертировать», «Сохранить в файл…», «Применить», «Закрыть»; «Тема окна:» с вариантами
  «не трогать», «тёмная», «светлая»; после применения «Схема применена. Изменения видны после
  запуска EDT»; ошибка записи «Не удалось записать <путь>: <причина>»; строка настроек
  «Каталог цветовых схем» с подсказкой «Темы IntelliJ IDEA (.xml, .icls, .jar), TextMate
  (.tmTheme) и файлы .csi; подкаталоги на один уровень»; заголовки таблицы «Цвет», «Образец»,
  «Код»; поиск «Поиск: имя схемы».
- **Границы (спека §10)**: без Конфигуратора (`1cv8.pfl`), без онлайн-галерей, без встроенного
  набора схем, без применения к нескольким записям, без хранения схемы в записи, без шрифтов.
- **Мутационная проверка** (CLAUDE.md) обязательна для: отказа `apply` при занятой области
  **до записи**; сохранности чужих ключей и перевода строки в `render_prefs`; отсутствия
  временного файла после записи. Результат — дословно в `docs/tasks.md`, T-19.
- **Фикстуры `tests/fixtures/edt_schemes/`** — только свои маленькие файлы (спека §9), не из
  `temp/`. Полный прогон pytest — в файл (`uv run pytest -q > e:/tmp/<имя>.log 2>&1`); субагенты
  запускают pytest только в обычном режиме. Флейк pytest-qt `access violation` — повторить.
- Патчи файлов с кириллицей и обратными слэшами — через Write/Edit, не bash-heredoc.
- Версия — только `pyproject.toml` (`3.2.0`); smoke собранного экземпляра обязателен.
  Коммиты по-русски, без атрибуции.

---

### Task 1: Домен — модель, ключи, цвета

**Files:**
- Create: `src/onecstarter/domain/edt_scheme.py`
- Create: `tests/unit/test_edt_scheme_model.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (`CORE` — строка `"onecstarter.domain.edt_scheme"` после `"onecstarter.domain.edt_cli"`)

**Interfaces:**
- Produces: `RGB = tuple[int, int, int]`; константы `BSL_PREFS`, `EDITORS_PREFS`, `THEME_PREFS`,
  `TOKEN_PREFIX`, `EDITOR_PREFIX`, `SYSTEM_DEFAULT_SUFFIX`, `CURRENT_NAME`, `DEFAULT_NAME`;
  `ColorKey(name, title, prefs_file, prefs_key, system_default, background)`; `COLOR_KEYS`
  (22), `KEY_BY_NAME`; `Scheme(name, colors, source="")` (всегда все 22 ключа, лишние
  отбрасываются, недостающие — `ValueError`); `to_hex(rgb) -> str`, `from_hex(text) -> RGB | None`,
  `idea_color(text) -> RGB | None`, `parse_rgb(text) -> RGB | None`, `format_rgb(rgb) -> str`,
  `luminance(rgb) -> float`, `DARK_LUMINANCE`, `is_dark_rgb(rgb) -> bool` (целочисленно, общий
  порог для `is_dark` и `fill_missing`), `is_dark(scheme) -> bool`, `invert(scheme) -> Scheme`,
  `fill_missing(partial, fallback_fg, fallback_bg) -> dict[str, RGB]`,
  `complete(name, partial, source="") -> Scheme`, `EDT_DEFAULTS: dict[str, RGB]`.

- [ ] **Step 1: Тесты модели и цветов**

`tests/unit/test_edt_scheme_model.py`:

```python
"""Домен цветовой схемы EDT: модель, ключи, цвета (спека v3.2, §2)."""

import pytest

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    EDITORS_PREFS,
    EDT_DEFAULTS,
    KEY_BY_NAME,
    RGB,
    Scheme,
    complete,
    fill_missing,
    format_rgb,
    from_hex,
    idea_color,
    invert,
    is_dark,
    parse_rgb,
    to_hex,
)

TOKEN_PREFIX = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


def test_color_keys_are_22_tokens_then_editor() -> None:
    assert len(COLOR_KEYS) == 22
    files = [key.prefs_file for key in COLOR_KEYS]
    assert files[:11] == [BSL_PREFS] * 11
    assert files[11:] == [EDITORS_PREFS] * 11
    assert len(KEY_BY_NAME) == 22
    assert all(key.title for key in COLOR_KEYS)


def test_token_keys_match_edt_identifiers() -> None:
    """11 идентификаторов — [Д] строки класса BslHighlightingConfiguration плагина
    bsl.ui (18.09.2026); пробел в `Builtin function` в файле экранирован ([Ф] спека §0)."""
    tokens = {key.prefs_key for key in COLOR_KEYS if key.prefs_file == BSL_PREFS}
    names = (
        "BSL_Keywords",
        "BSL_Pragmas",
        "Brackets",
        "Builtin\\ function",
        "Comment",
        "Label",
        "Numbers",
        "Operators",
        "Others",
        "Preprocessor",
        "Strings",
    )
    assert tokens == {f"{TOKEN_PREFIX}{name}.color" for name in names}
    assert KEY_BY_NAME["Builtinfunction"].prefs_key == f"{TOKEN_PREFIX}Builtin\\ function.color"


def test_editor_keys_and_flags() -> None:
    editor = {key.name: key for key in COLOR_KEYS if key.prefs_file == EDITORS_PREFS}
    assert editor["Background"].prefs_key == "AbstractTextEditor.Color.Background"
    assert editor["FindScope"].prefs_key == "AbstractTextEditor.Color.FindScope"
    assert editor["lineNumberColor"].prefs_key == "lineNumberColor"
    assert {name for name, key in editor.items() if key.system_default} == {
        "Background",
        "Foreground",
        "SelectionBackground",
        "SelectionForeground",
        "hyperlinkColor",
    }
    assert {key.name for key in COLOR_KEYS if key.background} == {
        "Background",
        "SelectionBackground",
        "currentLineColor",
        "occurrenceIndicationColor",
        "FindScope",
        "currentIPColor",
    }


def test_scheme_requires_all_keys_and_drops_extras() -> None:
    with pytest.raises(ValueError, match="Background"):
        Scheme("x", {"BSL_Keywords": (1, 2, 3)})
    scheme = Scheme("x", {**EDT_DEFAULTS, "Extra": (0, 0, 0)}, "C:/x.csi")
    assert "Extra" not in scheme.colors
    assert list(scheme.colors) == [key.name for key in COLOR_KEYS]
    assert scheme.source == "C:/x.csi"


def test_edt_defaults_cover_all_keys() -> None:
    assert set(EDT_DEFAULTS) == set(KEY_BY_NAME)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#FF8000", (255, 128, 0)),
        ("ff8000", (255, 128, 0)),
        ("#F80", (255, 136, 0)),
        (" #ff8000 ", (255, 128, 0)),
        ("#FF80", None),
        ("ggg", None),
        ("", None),
        ("#FF8000FF", None),
    ],
)
def test_from_hex(text: str, expected: RGB | None) -> None:
    assert from_hex(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    # [Ф] 18.09.2026, 641 тема каталога заказчика: hex без ведущих нулей (Java
    # Integer.toHexString), встречаются `#RRGGBB`, пустое и `undefined`.
    [
        ("ff", (0, 0, 255)),
        ("7f00", (0, 127, 0)),
        ("0", (0, 0, 0)),
        ("2b2b2b", (43, 43, 43)),
        ("#112328", (17, 35, 40)),
        ("A3A08", (10, 58, 8)),
        ("fff", (0, 15, 255)),
        ("", None),
        ("undefined", None),
        ("1234567", None),
    ],
)
def test_idea_color(text: str, expected: RGB | None) -> None:
    assert idea_color(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("255,140,110", (255, 140, 110)),
        (" 1, 2 ,3 ", (1, 2, 3)),
        ("256,0,0", None),
        ("-1,0,0", None),
        ("1,2", None),
        ("a,b,c", None),
        ("", None),
    ],
)
def test_parse_rgb(text: str, expected: RGB | None) -> None:
    assert parse_rgb(text) == expected


def test_to_hex_and_format_rgb() -> None:
    assert to_hex((255, 128, 0)) == "#FF8000"
    assert format_rgb((1, 2, 3)) == "1,2,3"
    assert from_hex(to_hex((7, 8, 9))) == (7, 8, 9)


def _scheme(**overrides: RGB) -> Scheme:
    return Scheme("t", {**EDT_DEFAULTS, **overrides})


@pytest.mark.parametrize(
    ("background", "dark"),
    [((30, 30, 30), True), ((255, 255, 255), False), ((128, 128, 128), False), ((0, 0, 200), True)],
)
def test_is_dark_by_background_luminance(background: RGB, dark: bool) -> None:
    assert is_dark(_scheme(Background=background)) is dark


def test_invert_flips_every_channel_and_keeps_name() -> None:
    scheme = Scheme("Тёмная", {**EDT_DEFAULTS, "Background": (10, 20, 30)}, "x.csi")
    inverted = invert(scheme)
    assert inverted.name == "Тёмная"
    assert inverted.source == "x.csi"
    assert inverted.colors["Background"] == (245, 235, 225)
    assert all(
        inverted.colors[name] == tuple(255 - c for c in rgb) for name, rgb in scheme.colors.items()
    )
    assert invert(inverted) == scheme


def test_fill_missing_light_shifts_towards_each_other() -> None:
    filled = fill_missing({}, (0, 0, 0), (255, 255, 255))
    assert set(filled) == set(KEY_BY_NAME)
    assert filled["Background"] == (255, 255, 255)
    assert filled["Foreground"] == (0, 0, 0)
    assert filled["currentLineColor"] == (235, 235, 235)  # фоновый ключ: фон −20
    assert filled["BSL_Keywords"] == (20, 20, 20)  # текстовый ключ: текст +20


def test_fill_missing_dark_uses_partial_background_and_fallback_foreground() -> None:
    filled = fill_missing({"Background": (10, 10, 10), "Strings": (1, 2, 3)}, (240, 240, 240), (0, 0, 0))
    assert filled["Background"] == (10, 10, 10)
    assert filled["Foreground"] == (240, 240, 240)
    assert filled["Strings"] == (1, 2, 3)
    assert filled["currentLineColor"] == (30, 30, 30)
    assert filled["Comment"] == (220, 220, 220)


def test_fill_missing_clamps_channels() -> None:
    filled = fill_missing({"Background": (0, 0, 0), "Foreground": (10, 10, 10)}, (0, 0, 0), (0, 0, 0))
    assert filled["Comment"] == (0, 0, 0)
    light = fill_missing({"Background": (250, 250, 250), "Foreground": (250, 250, 250)}, (0, 0, 0), (0, 0, 0))
    assert light["Comment"] == (255, 255, 255)
    assert light["currentLineColor"] == (230, 230, 230)


def test_fill_missing_and_is_dark_agree_at_mid_grey() -> None:
    """(128,128,128) — ровно порог: не тёмный для обеих функций (целочисленная яркость)."""
    grey: RGB = (128, 128, 128)
    assert is_dark(_scheme(Background=grey)) is False
    filled = fill_missing({"Background": grey, "Foreground": (0, 0, 0)}, (0, 0, 0), (0, 0, 0))
    assert filled["currentLineColor"] == (108, 108, 108)  # светлая ветка: фон −20
    assert filled["Comment"] == (20, 20, 20)  # текст +20
    dark = (127, 128, 128)
    assert is_dark(_scheme(Background=dark)) is True
    darker = fill_missing({"Background": dark}, (0, 0, 0), (0, 0, 0))
    assert darker["currentLineColor"] == (147, 148, 148)


def test_complete_fills_from_edt_defaults() -> None:
    scheme = complete("t", {"BSL_Keywords": (1, 2, 3)}, "C:/t.xml")
    assert scheme.name == "t"
    assert scheme.source == "C:/t.xml"
    assert scheme.colors["BSL_Keywords"] == (1, 2, 3)
    assert scheme.colors["Background"] == EDT_DEFAULTS["Background"]
    assert scheme.colors["Foreground"] == EDT_DEFAULTS["Foreground"]
```

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/unit/test_edt_scheme_model.py -q`
Expected: `ImportError`/`ModuleNotFoundError: onecstarter.domain.edt_scheme`.

- [ ] **Step 3: Модуль домена**

`src/onecstarter/domain/edt_scheme.py`:

```python
"""Цветовая схема редактора кода EDT (спека v3.2): модель, цвета, разбор источников,
Java properties без потерь.

Чистые функции над текстом и байтами — ни ФС, ни процессов (инварианты 1–2 CLAUDE.md).
Факты: два файла prefs и 22 ключа — [Ф] 16.09.2026, пять рабочих областей заказчика;
11 идентификаторов токенов — [Д] строки констант класса `BslHighlightingConfiguration`
плагина `com._1c.g5.v8.dt.bsl.ui` (18.09.2026). Умолчания цветов — `EDT_DEFAULTS`,
метка достоверности — в комментарии к константе (Э10).
"""  # noqa: RUF002

import re
from collections.abc import Mapping
from dataclasses import dataclass

RGB = tuple[int, int, int]

BSL_PREFS = "com._1c.g5.v8.dt.bsl.ui.prefs"
EDITORS_PREFS = "org.eclipse.ui.editors.prefs"
THEME_PREFS = "org.eclipse.e4.ui.css.swt.theme.prefs"
TOKEN_PREFIX = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."
EDITOR_PREFIX = "AbstractTextEditor.Color."
SYSTEM_DEFAULT_SUFFIX = ".SystemDefault"
CURRENT_NAME = "Текущая (рабочая область)"
DEFAULT_NAME = "По умолчанию EDT"
SHIFT = 20  # сдвиг канала для недостающих цветов, как у обработки заказчика [Р]


@dataclass(frozen=True)
class ColorKey:
    name: str  # короткое имя: «BSL_Keywords», «Background»; в .csi — то же
    title: str  # подпись в таблице диалога
    prefs_file: str  # BSL_PREFS | EDITORS_PREFS
    prefs_key: str  # ключ как записан в файле (пробел экранирован)
    system_default: bool = False  # писать парный `<ключ>.SystemDefault=false`
    background: bool = False  # фоновый цвет: вывод недостающих и инверсия предпросмотра


def _token(name: str, title: str, token: str) -> ColorKey:
    return ColorKey(name, title, BSL_PREFS, f"{TOKEN_PREFIX}{token}.color")


def _editor(
    name: str, title: str, key: str, *, system_default: bool = False, background: bool = False
) -> ColorKey:
    return ColorKey(name, title, EDITORS_PREFS, key, system_default, background)


# Порядок — порядок показа в таблице: 11 токенов, затем 11 цветов редактора (спека §2).
COLOR_KEYS: tuple[ColorKey, ...] = (
    _token("BSL_Keywords", "Ключевые слова", "BSL_Keywords"),
    _token("BSL_Pragmas", "Директивы (&НаКлиенте)", "BSL_Pragmas"),
    _token("Preprocessor", "Препроцессор (#Если)", "Preprocessor"),
    _token("Builtinfunction", "Встроенные функции", "Builtin\\ function"),
    _token("Strings", "Строки", "Strings"),
    _token("Numbers", "Числа", "Numbers"),
    _token("Comment", "Комментарии", "Comment"),
    _token("Operators", "Операторы", "Operators"),
    _token("Brackets", "Скобки", "Brackets"),
    _token("Label", "Метки", "Label"),
    _token("Others", "Прочее (идентификаторы)", "Others"),
    _editor("Background", "Фон", EDITOR_PREFIX + "Background", system_default=True, background=True),
    _editor("Foreground", "Текст", EDITOR_PREFIX + "Foreground", system_default=True),
    _editor(
        "SelectionBackground",
        "Фон выделения",
        EDITOR_PREFIX + "SelectionBackground",
        system_default=True,
        background=True,
    ),
    _editor(
        "SelectionForeground",
        "Текст выделения",
        EDITOR_PREFIX + "SelectionForeground",
        system_default=True,
    ),
    _editor("currentLineColor", "Текущая строка", "currentLineColor", background=True),
    _editor("lineNumberColor", "Номера строк", "lineNumberColor"),
    _editor("occurrenceIndicationColor", "Вхождения", "occurrenceIndicationColor", background=True),
    _editor("hyperlinkColor", "Гиперссылки", "hyperlinkColor", system_default=True),
    _editor("FindScope", "Область поиска", EDITOR_PREFIX + "FindScope", background=True),
    _editor("currentIPColor", "Текущая инструкция (отладка)", "currentIPColor", background=True),
    _editor("printMarginColor", "Граница печати", "printMarginColor"),
)
KEY_BY_NAME: dict[str, ColorKey] = {key.name: key for key in COLOR_KEYS}


@dataclass(frozen=True)
class Scheme:
    name: str
    colors: dict[str, RGB]  # ключ — ColorKey.name; всегда все 22, в порядке COLOR_KEYS
    source: str = ""  # путь файла или "" для «Текущая»/«По умолчанию»

    def __post_init__(self) -> None:
        missing = [key.name for key in COLOR_KEYS if key.name not in self.colors]
        if missing:
            raise ValueError(f"в схеме нет цветов: {', '.join(missing)}")
        object.__setattr__(self, "colors", {key.name: self.colors[key.name] for key in COLOR_KEYS})


# --- цвета -------------------------------------------------------------------

_HEX6 = re.compile(r"^#?([0-9A-Fa-f]{6})$")
_HEX3 = re.compile(r"^#?([0-9A-Fa-f]{3})$")
_IDEA_HEX = re.compile(r"^#?([0-9A-Fa-f]{1,6})$")


def to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def from_hex(text: str) -> RGB | None:
    """`#RRGGBB`, `RRGGBB`, `#RGB` (CSS-сокращение); иначе None."""
    value = text.strip()
    match6 = _HEX6.match(value)
    if match6:
        hexes = match6.group(1)
        return (int(hexes[0:2], 16), int(hexes[2:4], 16), int(hexes[4:6], 16))
    match3 = _HEX3.match(value)
    if match3:
        hexes = match3.group(1)
        return (int(hexes[0] * 2, 16), int(hexes[1] * 2, 16), int(hexes[2] * 2, 16))
    return None


def idea_color(text: str) -> RGB | None:
    """Цвет из XML темы IDEA: hex без ведущих нулей (`ff` = `0000ff`, `7f00`, `0`) —
    Java `Integer.toHexString`; иногда `#RRGGBB`; пусто или `undefined` — не задан.
    [Ф] 18.09.2026: 641 тема каталога заказчика — длины 1–6, 612 значений с `#`,
    3 `undefined`. Сокращение `#RGB` здесь НЕ действует: `fff` — это `000fff`."""
    match = _IDEA_HEX.match(text.strip())
    if match is None:
        return None
    return from_hex(match.group(1).zfill(6))


def parse_rgb(text: str) -> RGB | None:
    """`R,G,B` из prefs; не три числа или вне 0–255 — None (спека §7: ключ не задан)."""
    parts = text.strip().split(",")
    if len(parts) != 3:
        return None
    try:
        values = [int(part.strip()) for part in parts]
    except ValueError:
        return None
    if any(value < 0 or value > 255 for value in values):
        return None
    return (values[0], values[1], values[2])


def format_rgb(rgb: RGB) -> str:
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


DARK_LUMINANCE = 128  # порог яркости (0–255): ниже — тёмный фон


def luminance(rgb: RGB) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def is_dark_rgb(rgb: RGB) -> bool:
    """Тёмный ли цвет: целочисленная яркость, без плавающей точки — (128,128,128) ровно
    на пороге и тёмным не считается. (Ревью задачи 1: `0.299·128+0.587·128+0.114·128 =
    127.999…`, и `luminance(...) < 128` расходилось между `is_dark` и `fill_missing`.)"""
    return 299 * rgb[0] + 587 * rgb[1] + 114 * rgb[2] < DARK_LUMINANCE * 1000


def is_dark(scheme: Scheme) -> bool:
    return is_dark_rgb(scheme.colors["Background"])


def invert(scheme: Scheme) -> Scheme:
    colors = {name: (255 - r, 255 - g, 255 - b) for name, (r, g, b) in scheme.colors.items()}
    return Scheme(scheme.name, colors, scheme.source)


def _shift(rgb: RGB, delta: int) -> RGB:
    return (
        min(255, max(0, rgb[0] + delta)),
        min(255, max(0, rgb[1] + delta)),
        min(255, max(0, rgb[2] + delta)),
    )


def fill_missing(partial: Mapping[str, RGB], fallback_fg: RGB, fallback_bg: RGB) -> dict[str, RGB]:
    """Дополнить до 22 ключей. `Background`/`Foreground` — из `partial` или запасные;
    остальные недостающие — сдвиг на `SHIFT` по каналам навстречу друг другу [Р]:
    на тёмном фоне фоновые ключи светлеют от фона, текстовые темнеют от текста;
    на светлом — наоборот. Заданные ключи не трогаются."""
    background = partial.get("Background", fallback_bg)
    foreground = partial.get("Foreground", fallback_fg)
    delta = SHIFT if is_dark_rgb(background) else -SHIFT
    result: dict[str, RGB] = {}
    for key in COLOR_KEYS:
        if key.name in partial:
            result[key.name] = partial[key.name]
        elif key.name == "Background":
            result[key.name] = background
        elif key.name == "Foreground":
            result[key.name] = foreground
        elif key.background:
            result[key.name] = _shift(background, delta)
        else:
            result[key.name] = _shift(foreground, -delta)
    return result


def complete(name: str, partial: Mapping[str, RGB], source: str = "") -> Scheme:
    """Схема из частичного набора: недостающие — `fill_missing` от `EDT_DEFAULTS`."""
    return Scheme(
        name, fill_missing(partial, EDT_DEFAULTS["Foreground"], EDT_DEFAULTS["Background"]), source
    )


# Светлая схема EDT по умолчанию. [?] до Э10 — значения по умолчанию Eclipse JDT/текстового
# редактора ([Д] исходники Eclipse: lineNumberColor 120,120,120, currentLineColor 232,242,254,
# printMarginColor 176,180,185, occurrenceIndicationColor 212,212,212, FindScope 185,176,180,
# currentIPColor 198,219,174; фон/текст/выделение — системные цвета Windows). Э10 заменяет
# на снятые с установки и ставит метку.
EDT_DEFAULTS: dict[str, RGB] = {
    "BSL_Keywords": (127, 0, 85),
    "BSL_Pragmas": (125, 125, 125),
    "Preprocessor": (0, 0, 205),
    "Builtinfunction": (127, 0, 85),
    "Strings": (42, 0, 255),
    "Numbers": (0, 0, 0),
    "Comment": (63, 127, 95),
    "Operators": (0, 0, 0),
    "Brackets": (0, 0, 0),
    "Label": (125, 125, 125),
    "Others": (0, 0, 0),
    "Background": (255, 255, 255),
    "Foreground": (0, 0, 0),
    "SelectionBackground": (0, 120, 215),
    "SelectionForeground": (255, 255, 255),
    "currentLineColor": (232, 242, 254),
    "lineNumberColor": (120, 120, 120),
    "occurrenceIndicationColor": (212, 212, 212),
    "hyperlinkColor": (0, 0, 255),
    "FindScope": (185, 176, 180),
    "currentIPColor": (198, 219, 174),
    "printMarginColor": (176, 180, 185),
}
```

- [ ] **Step 4: Прогон — зелёный, статика**

Run: `uv run pytest tests/unit/test_edt_scheme_model.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check src/onecstarter/domain/edt_scheme.py tests/unit/test_edt_scheme_model.py && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`. Ruff `RUF001/002/003` на кириллице —
`# noqa` по месту, как в `domain/edt_cli.py`.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/domain/edt_scheme.py tests/unit/test_edt_scheme_model.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(edt): домен цветовой схемы — модель ColorKey/Scheme, 22 ключа, цвета (v3.2, задача 1)"
```

---

### Task 2: Домен — Java properties без потерь, prefs рабочей области, тема окна

**Files:**
- Modify: `src/onecstarter/domain/edt_scheme.py` (добавить в конец; импорты `Iterable`, `Enum`)
- Create: `tests/fixtures/edt_schemes/bsl-crlf.prefs` (байт в байт, CRLF)
- Create: `tests/unit/test_edt_scheme_prefs.py`

**Interfaces:**
- Consumes: Task 1 (`COLOR_KEYS`, `Scheme`, `parse_rgb`, `format_rgb`, `CURRENT_NAME`).
- Produces: `PREFS_VERSION_LINE`, `NEW_PREFS_NEWLINE`, `PrefsLine(raw, key, key_text, value, newline)`,
  `unescape_property(text) -> str`, `parse_prefs_line(raw) -> PrefsLine`,
  `parse_prefs(text) -> dict[str, str]`,
  `render_prefs(existing, updates: Mapping[str, str], remove: Iterable[str] = ()) -> str`,
  `prefs_updates(scheme) -> dict[str, dict[str, str]]`, `prefs_removals() -> dict[str, list[str]]`,
  `scheme_from_workspace_prefs(bsl_prefs, editors_prefs, defaults) -> Scheme`,
  `ThemeChoice` (`KEEP`/`DARK`/`LIGHT`), `THEME_KEY = "themeid"`, `THEME_IDS: dict[ThemeChoice, str]`,
  `theme_prefs_update(choice) -> dict[str, str] | None`.

- [ ] **Step 1: Фикстура**

`tests/fixtures/edt_schemes/bsl-crlf.prefs` — записать **байтами** (Write в редакторе может
подменить концы строк, поэтому создать через Python):

```bash
uv run python -c "from pathlib import Path; p=Path('tests/fixtures/edt_schemes/bsl-crlf.prefs'); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'=\r\ncom._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles.BSL_Keywords.color=204,120,50\r\ncom._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles.Builtin\\\\ function.color=255,198,109\r\ncom._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles.Strings.color=106,135,89\r\neclipse.preferences.version=1\r\n\\\\u00EF\\\\u00BB\\\\u00BF=\r\n')"
```

Проверить: `uv run python -c "print(open('tests/fixtures/edt_schemes/bsl-crlf.prefs','rb').read())"` —
шесть строк, каждая с `\r\n`, вторая-с-конца `eclipse.preferences.version=1`, последняя
`\u00EF\u00BB\u00BF=` (обратный слэш и `u`, не байты BOM), третья содержит `Builtin\ function`
(один обратный слэш). Структура — как у файлов заказчика ([Ф] спека §0: первая строка `=`,
последняя `\u00EF\u00BB\u00BF=`, CRLF); цвета свои.

- [ ] **Step 2: Тесты**

`tests/unit/test_edt_scheme_prefs.py`:

```python
"""Java properties без потерь и prefs рабочей области (спека v3.2, §3; инвариант 3)."""

from pathlib import Path

import pytest

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    CURRENT_NAME,
    EDITORS_PREFS,
    EDT_DEFAULTS,
    NEW_PREFS_NEWLINE,
    PREFS_VERSION_LINE,
    THEME_IDS,
    THEME_KEY,
    Scheme,
    ThemeChoice,
    parse_prefs,
    parse_prefs_line,
    prefs_removals,
    prefs_updates,
    render_prefs,
    scheme_from_workspace_prefs,
    theme_prefs_update,
    unescape_property,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "edt_schemes" / "bsl-crlf.prefs"
TOKEN = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


def _fixture() -> str:
    return FIXTURE.read_bytes().decode("latin-1")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Builtin\\ function", "Builtin function"),
        ("a\\=b\\:c", "a=b:c"),
        ("x\\\\y", "x\\y"),
        ("\\u00EF\\u00BB\\u00BF", "\u00ef\u00bb\u00bf"),
        ("tab\\there", "tab\there"),
        ("trailing\\", "trailing\\"),
        ("\\uZZZZ", "uZZZZ"),
    ],
)
def test_unescape_property(text: str, expected: str) -> None:
    assert unescape_property(text) == expected


def test_parse_prefs_line_classifies() -> None:
    assert parse_prefs_line("# comment").key is None
    assert parse_prefs_line("! comment").key is None
    assert parse_prefs_line("").key is None
    assert parse_prefs_line("no separator").key is None
    line = parse_prefs_line(" key\\ one = value=with=eq")
    assert (line.key, line.key_text, line.value) == ("key one", " key\\ one ", "value=with=eq")


def test_parse_prefs_unescapes_and_keeps_garbage_keys() -> None:
    parsed = parse_prefs(_fixture())
    assert parsed[f"{TOKEN}Builtin function.color"] == "255,198,109"
    assert parsed[f"{TOKEN}BSL_Keywords.color"] == "204,120,50"
    assert parsed["eclipse.preferences.version"] == "1"
    assert parsed[""] == ""
    assert parsed["\u00ef\u00bb\u00bf"] == ""


def test_render_roundtrip_identity_crlf_and_lf() -> None:
    text = _fixture()
    assert "\r\n" in text
    assert render_prefs(text, {}) == text
    lf = text.replace("\r\n", "\n")
    assert render_prefs(lf, {}) == lf


def test_render_replaces_in_place_keeps_order_garbage_and_crlf() -> None:
    text = _fixture()
    rendered = render_prefs(text, {f"{TOKEN}Strings.color": "1,2,3"})
    lines = rendered.split("\r\n")
    assert lines[0] == "="
    assert lines[3] == f"{TOKEN}Strings.color=1,2,3"
    assert lines[-2] == "\\u00EF\\u00BB\\u00BF="
    assert lines[-1] == ""
    assert "\n" not in rendered.replace("\r\n", "")
    assert len(lines) == len(text.split("\r\n"))


def test_render_inserts_new_key_in_sorted_position_by_unescaped_key() -> None:
    rendered = render_prefs(_fixture(), {f"{TOKEN}Comment.color": "9,9,9"})
    keys = [line.split("=")[0] for line in rendered.split("\r\n") if line]
    assert keys.index(f"{TOKEN}Comment.color") == keys.index(f"{TOKEN}Builtin\\ function.color") + 1
    assert keys.index(f"{TOKEN}Comment.color") == keys.index(f"{TOKEN}Strings.color") - 1


def test_render_new_file_has_version_line_sorted_keys_and_newline() -> None:
    rendered = render_prefs("", {"lineNumberColor": "1,1,1", "AbstractTextEditor.Color.Background": "2,2,2"})
    assert rendered == NEW_PREFS_NEWLINE.join(
        ["AbstractTextEditor.Color.Background=2,2,2", PREFS_VERSION_LINE, "lineNumberColor=1,1,1", ""]
    )


def test_render_preserves_comments_blank_lines_and_foreign_keys() -> None:
    existing = "# note\n\nforeign=1\nlineNumberColor=0,0,0\n"
    rendered = render_prefs(existing, {"lineNumberColor": "5,5,5"})
    assert rendered == "# note\n\nforeign=1\nlineNumberColor=5,5,5\n"


def test_render_without_trailing_newline_stays_without() -> None:
    assert render_prefs("a=1\nb=2", {"b": "3"}) == "a=1\nb=3"
    assert render_prefs("a=1\nb=2", {"c": "0"}) == "a=1\nb=2\nc=0"


def test_render_keeps_each_line_ending_as_is() -> None:
    mixed = "a=1\nb=2\r\nc=3\rd=4"
    assert render_prefs(mixed, {}) == mixed
    assert render_prefs(mixed, {"b": "9"}) == "a=1\nb=9\r\nc=3\rd=4"
    # новый ключ — доминирующим переводом строки файла (CRLF, если встречается)
    assert render_prefs(mixed, {"e": "5"}) == "a=1\nb=2\r\nc=3\rd=4\r\ne=5"
    assert render_prefs("a=1\nb=2\n", {"c": "0"}) == "a=1\nb=2\nc=0\n"


def test_render_empty_existing_is_a_new_file_not_identity() -> None:
    assert render_prefs("", {}) == PREFS_VERSION_LINE + NEW_PREFS_NEWLINE


def test_render_trailing_newline_survives_removal_and_mixed_endings() -> None:
    assert render_prefs("a=1\nb=2", {"c": "3"}, remove=["b"]) == "a=1\nc=3"
    assert render_prefs("a=1\nb=2\n", {}, remove=["b"]) == "a=1\n"
    assert render_prefs("a=1\r\nb=2\n", {}) == "a=1\r\nb=2\n"
    assert render_prefs("a=1\r\nb=2\n", {"c": "3"}) == "a=1\r\nb=2\nc=3\r\n"


def test_render_removes_keys_and_keeps_rest() -> None:
    rendered = render_prefs(_fixture(), {}, remove=[f"{TOKEN}Builtin\\ function.color", "absent"])
    assert "Builtin" not in rendered
    assert rendered.startswith("=\r\n")
    assert rendered.endswith("\\u00EF\\u00BB\\u00BF=\r\n")


def test_prefs_updates_split_by_file_with_system_default_flags() -> None:
    updates = prefs_updates(Scheme("x", EDT_DEFAULTS))
    assert set(updates) == {BSL_PREFS, EDITORS_PREFS}
    assert len(updates[BSL_PREFS]) == 11
    assert len(updates[EDITORS_PREFS]) == 16
    assert updates[BSL_PREFS][f"{TOKEN}Builtin\\ function.color"] == "127,0,85"
    assert updates[EDITORS_PREFS]["AbstractTextEditor.Color.Background.SystemDefault"] == "false"
    assert updates[EDITORS_PREFS]["hyperlinkColor.SystemDefault"] == "false"
    assert "lineNumberColor.SystemDefault" not in updates[EDITORS_PREFS]
    assert set(prefs_removals()[EDITORS_PREFS]) == set(updates[EDITORS_PREFS])
    assert set(prefs_removals()[BSL_PREFS]) == set(updates[BSL_PREFS])


def test_scheme_from_workspace_prefs_uses_file_values_else_defaults() -> None:
    bsl = f"{TOKEN}BSL_Keywords.color=1,2,3\r\n{TOKEN}Strings.color=300,0,0\r\n"
    editors = "lineNumberColor=7,7,7\nAbstractTextEditor.Color.Background=bad\n"
    scheme = scheme_from_workspace_prefs(bsl, editors, EDT_DEFAULTS)
    assert scheme.name == CURRENT_NAME
    assert scheme.colors["BSL_Keywords"] == (1, 2, 3)
    assert scheme.colors["Strings"] == EDT_DEFAULTS["Strings"]
    assert scheme.colors["lineNumberColor"] == (7, 7, 7)
    assert scheme.colors["Background"] == EDT_DEFAULTS["Background"]
    empty = scheme_from_workspace_prefs("", "", EDT_DEFAULTS)
    assert empty.colors == {key.name: EDT_DEFAULTS[key.name] for key in COLOR_KEYS}


def test_theme_prefs_update_follows_theme_ids() -> None:
    assert theme_prefs_update(ThemeChoice.KEEP) is None
    assert THEME_IDS[ThemeChoice.DARK] == "org.eclipse.e4.ui.css.theme.e4_dark"
    assert theme_prefs_update(ThemeChoice.DARK) == {THEME_KEY: THEME_IDS[ThemeChoice.DARK]}
    expected = {THEME_KEY: THEME_IDS[ThemeChoice.LIGHT]} if ThemeChoice.LIGHT in THEME_IDS else None
    assert theme_prefs_update(ThemeChoice.LIGHT) == expected
```

- [ ] **Step 3: Прогон — падает**

Run: `uv run pytest tests/unit/test_edt_scheme_prefs.py -q`
Expected: `ImportError` (`parse_prefs` и остальные не определены).

- [ ] **Step 4: Реализация**

В `src/onecstarter/domain/edt_scheme.py` — импорты `from collections.abc import Iterable, Mapping`,
`from dataclasses import dataclass, replace`, `from enum import Enum`; в конец модуля:

```python
# --- Java properties без потерь --------------------------------------------------
#
# Формат [Ф] спека §0: `ключ=значение`, `eclipse.preferences.version=1`, ключи по алфавиту;
# у заказчика — CRLF и мусорные строки `=`, `\u00EF\u00BB\u00BF=` (ключи с пустым значением),
# которые EDT переживает. Минимальный разбор: разделитель только `=`, экранирование
# `\ `, `\=`, `\:`, `\\`, `\uXXXX`, `\t`/`\n`/`\r`/`\f`; продолжение строки обратным слэшем
# не поддерживается (Eclipse его не пишет). Строки без `=`, пустые и комментарии `#`/`!`
# сохраняются на месте. Кодировка — забота вызывающего (latin-1).

PREFS_VERSION_LINE = "eclipse.preferences.version=1"
# Перевод строки НОВОГО файла; существующий сохраняет свой. [?] до Э8: все пять файлов
# заказчика — CRLF ([Ф]); Eclipse на Windows пишет `BufferedWriter.newLine()` ([Д]).
NEW_PREFS_NEWLINE = "\r\n"
_LINE_BREAK = re.compile(r"(\r\n|\r|\n)")  # группа — терминатор остаётся в результате split
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


@dataclass(frozen=True)
class PrefsLine:
    raw: str  # строка без перевода
    key: str | None = None  # None — не пара «ключ=значение»
    key_text: str = ""  # ключ как записан (с экранированием и пробелами)
    value: str = ""
    newline: str = ""  # перевод строки, каким он был в файле; "" — последняя строка без него


def unescape_property(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\" or index + 1 >= len(text):
            out.append(char)
            index += 1
            continue
        following = text[index + 1]
        if following == "u" and index + 6 <= len(text):
            try:
                out.append(chr(int(text[index + 2 : index + 6], 16)))
                index += 6
                continue
            except ValueError:
                pass
        out.append(_ESCAPES.get(following, following))
        index += 2
    return "".join(out)


def parse_prefs_line(raw: str, newline: str = "") -> PrefsLine:
    stripped = raw.lstrip()
    if not stripped or stripped[0] in "#!":
        return PrefsLine(raw, newline=newline)
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\":
            index += 2
            continue
        if char == "=":
            key_text = raw[:index]
            value = unescape_property(raw[index + 1 :].lstrip())
            return PrefsLine(raw, unescape_property(key_text).strip(), key_text, value, newline)
        index += 1
    return PrefsLine(raw, newline=newline)


def _split_lines(text: str) -> list[tuple[str, str]]:
    """(строка, её перевод) — перевод каждой строки сохраняется как есть (инвариант 3;
    ревью задачи 2: единый стиль на файл нормализовал бы смешанные концы строк).
    Не `str.splitlines`: тот режет и по `\\x85`/`\\x1c`…, которые в latin-1 — данные."""
    if not text:
        return []
    parts = _LINE_BREAK.split(text)  # [текст, терминатор, текст, …, текст]
    pairs = [(parts[i], parts[i + 1]) for i in range(0, len(parts) - 1, 2)]
    if parts[-1]:
        pairs.append((parts[-1], ""))
    return pairs


def _newline_of(existing: str) -> str:
    """Перевод строки для НОВЫХ строк: как в файле (CRLF, если встречается), иначе LF."""
    if not existing:
        return NEW_PREFS_NEWLINE
    return "\r\n" if "\r\n" in existing else "\n"


def parse_prefs(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw, _newline in _split_lines(text):
        line = parse_prefs_line(raw)
        if line.key is not None:
            result[line.key] = line.value
    return result


def render_prefs(existing: str, updates: Mapping[str, str], remove: Iterable[str] = ()) -> str:
    """Подставить наши ключи в текст prefs без потерь (инвариант 3).

    Строки существующего файла остаются на местах: комментарии, пустые, чужие ключи,
    порядок, перевод строки КАЖДОЙ строки (в том числе отсутствие завершающего). Значение
    нашего ключа заменяется на месте (текст ключа и его перевод строки — как были); ключ,
    которого не было, вставляется перед первым существующим ключом, большим по алфавиту
    (Eclipse хранит ключи отсортированными, сравнение — по снятому экранированию), иначе
    в конец — с переводом строки файла (`_newline_of`); `remove` — ключи, строки которых
    удаляются. Пустой `existing` — новый файл: `eclipse.preferences.version=1` плюс ключи
    по алфавиту, перевод строки `NEW_PREFS_NEWLINE`. Тождество для существующего файла:
    `render_prefs(t, {}) == t` при непустом `t`; пустой `t` — новый файл, не тождество.
    """  # noqa: RUF002
    newline = _newline_of(existing)
    lines = [parse_prefs_line(raw, ending) for raw, ending in _split_lines(existing)]
    if not lines:
        lines = [parse_prefs_line(PREFS_VERSION_LINE, newline)]
    removed = {unescape_property(key).strip() for key in remove}
    result = [line for line in lines if line.key is None or line.key not in removed]
    pending = {unescape_property(key).strip(): (key, value) for key, value in updates.items()}
    for index, line in enumerate(result):
        if line.key is not None and line.key in pending:
            _key_text, value = pending.pop(line.key)
            result[index] = PrefsLine(
                f"{line.key_text}={value}", line.key, line.key_text, value, line.newline
            )
    for normalized in sorted(pending):
        key_text, value = pending[normalized]
        position = next(
            (i for i, line in enumerate(result) if line.key is not None and line.key > normalized),
            len(result),
        )
        result.insert(position, PrefsLine(f"{key_text}={value}", normalized, key_text, value, newline))
    # Терминаторы: у каждой строки, кроме последней, он обязан быть (свой или файла);
    # у последней — свой, если файл заканчивался переводом строки, иначе никакого.
    # Один проход после всех правок (ревью задачи 2: фикс при вставке не покрывал
    # удаление последней строки без терминатора).
    trailing = not existing or existing.endswith(("\n", "\r"))
    for index, line in enumerate(result):
        if index == len(result) - 1:
            wanted = (line.newline or newline) if trailing else ""
        else:
            wanted = line.newline or newline
        if wanted != line.newline:
            result[index] = replace(line, newline=wanted)
    return "".join(line.raw + line.newline for line in result)


# --- prefs рабочей области --------------------------------------------------------


def prefs_updates(scheme: Scheme) -> dict[str, dict[str, str]]:
    """По файлу → пары ключ/значение схемы, включая `.SystemDefault=false` (спека §0)."""
    result: dict[str, dict[str, str]] = {BSL_PREFS: {}, EDITORS_PREFS: {}}
    for key in COLOR_KEYS:
        result[key.prefs_file][key.prefs_key] = format_rgb(scheme.colors[key.name])
        if key.system_default:
            result[key.prefs_file][key.prefs_key + SYSTEM_DEFAULT_SUFFIX] = "false"
    return result


def prefs_removals() -> dict[str, list[str]]:
    """Ключи, которые снимает «По умолчанию EDT», — те же, что пишет `prefs_updates`."""
    return {name: list(keys) for name, keys in prefs_updates(Scheme("", EDT_DEFAULTS)).items()}


def scheme_from_workspace_prefs(
    bsl_prefs: str, editors_prefs: str, defaults: Mapping[str, RGB]
) -> Scheme:
    """«Текущая»: `R,G,B` из файла, иначе (нет ключа, не разобрался) — из `defaults`."""
    values = {BSL_PREFS: parse_prefs(bsl_prefs), EDITORS_PREFS: parse_prefs(editors_prefs)}
    colors: dict[str, RGB] = {}
    for key in COLOR_KEYS:
        raw = values[key.prefs_file].get(unescape_property(key.prefs_key))
        rgb = parse_rgb(raw) if raw is not None else None
        colors[key.name] = rgb if rgb is not None else defaults[key.name]
    return Scheme(CURRENT_NAME, colors)


# --- тема окна ----------------------------------------------------------------------


class ThemeChoice(Enum):
    KEEP = "keep"
    DARK = "dark"
    LIGHT = "light"


THEME_KEY = "themeid"
# [Ф] 16.09.2026: тёмная — `org.eclipse.e4.ui.css.theme.e4_dark` (тёмные рабочие области
# заказчика). Светлая — после Э9; до него отсутствует: комбо «Тема окна» строится только по
# подтверждённым вариантам. Читает ли EDT ключ при старте — Э9; опровергнет — словарь пуст.
THEME_IDS: dict[ThemeChoice, str] = {ThemeChoice.DARK: "org.eclipse.e4.ui.css.theme.e4_dark"}


def theme_prefs_update(choice: ThemeChoice) -> dict[str, str] | None:
    theme_id = THEME_IDS.get(choice)
    return None if theme_id is None else {THEME_KEY: theme_id}
```

- [ ] **Step 5: Прогон — зелёный, статика**

Run: `uv run pytest tests/unit/test_edt_scheme_prefs.py tests/unit/test_edt_scheme_model.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 6: Мутационная проверка сохранности**

Временно в `render_prefs` заменить `result = [line for line in lines if …]` на
`result = [line for line in lines if line.key is not None and line.key not in removed]`
(теряет строки без ключа). Run: `uv run pytest tests/unit/test_edt_scheme_prefs.py -q` —
ожидается `FAILED test_render_preserves_comments_blank_lines_and_foreign_keys` и
`test_render_roundtrip_identity_crlf_and_lf`. Затем временно `newline = "\n"` — ожидается
`FAILED …roundtrip…` и `…keeps_order_garbage_and_crlf`. Откатить обе правки (`git diff` пуст по
модулю кроме новых функций), результат записать в отчёт задачи для `docs/tasks.md`.

- [ ] **Step 7: Коммит**

```bash
git add src/onecstarter/domain/edt_scheme.py tests/unit/test_edt_scheme_prefs.py tests/fixtures/edt_schemes/bsl-crlf.prefs
git commit -m "feat(edt): Java properties без потерь, prefs рабочей области, тема окна (v3.2, задача 2)"
```

---

### Task 3: Домен — источники схем (`.csi`, IDEA XML/`.jar`, `.tmTheme`)

**Files:**
- Modify: `src/onecstarter/domain/edt_scheme.py` (добавить в конец; импорты `io`, `json`,
  `plistlib`, `zipfile`, `from xml.etree import ElementTree`)
- Create: `tests/fixtures/edt_schemes/idea-six.xml`, `tests/fixtures/edt_schemes/four-scopes.tmTheme`,
  `tests/fixtures/edt_schemes/dark22.csi`
- Create: `tests/unit/test_edt_scheme_sources.py`

**Interfaces:**
- Consumes: Task 1 (`COLOR_KEYS`, `KEY_BY_NAME`, `Scheme`, `from_hex`, `idea_color`, `to_hex`).
- Produces: `parse_csi(text) -> dict[str, RGB]`, `to_csi(scheme) -> str`,
  `IdeaSource(attribute, component="")`, `IDEA_MAP: dict[str, tuple[IdeaSource, ...]]`,
  `parse_idea_xml(text) -> tuple[str, dict[str, RGB]]`,
  `parse_idea_jar(data: bytes) -> tuple[str, dict[str, RGB]]`,
  `TMTHEME_SCOPES: tuple[tuple[str, str], ...]`, `TMTHEME_GENERAL: dict[str, str]`,
  `tm_color(text) -> RGB | None`, `parse_tmtheme(text) -> tuple[str, dict[str, RGB]]`.
  Все парсеры поднимают `ValueError` с причиной по-русски; имя `""`, если источник его не несёт.

- [ ] **Step 1: Фикстуры**

`tests/fixtures/edt_schemes/idea-six.xml` (шесть атрибутов с цветом; `ff` без ведущих нулей,
`#2f2f2f` с решёткой, пустой `SELECTION_FOREGROUND`, `DEFAULT_LABEL` без значения — цвета
общеизвестной палитры Darcula, не из `temp/`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<scheme name="Шесть атрибутов" version="142" parent_scheme="Darcula">
  <option name="LINE_SPACING" value="1.0" />
  <colors>
    <option name="CARET_ROW_COLOR" value="323232" />
    <option name="LINE_NUMBERS_COLOR" value="606366" />
    <option name="SELECTION_BACKGROUND" value="214283" />
    <option name="SELECTION_FOREGROUND" value="" />
    <option name="RIGHT_MARGIN_COLOR" value="#2f2f2f" />
  </colors>
  <attributes>
    <option name="TEXT">
      <value>
        <option name="FOREGROUND" value="a9b7c6" />
        <option name="BACKGROUND" value="2b2b2b" />
      </value>
    </option>
    <option name="DEFAULT_KEYWORD">
      <value>
        <option name="FOREGROUND" value="cc7832" />
      </value>
    </option>
    <option name="DEFAULT_STRING">
      <value>
        <option name="FOREGROUND" value="6a8759" />
      </value>
    </option>
    <option name="DEFAULT_NUMBER">
      <value>
        <option name="FOREGROUND" value="6897bb" />
      </value>
    </option>
    <option name="DEFAULT_LINE_COMMENT">
      <value>
        <option name="FOREGROUND" value="808080" />
        <option name="FONT_TYPE" value="2" />
      </value>
    </option>
    <option name="DEFAULT_FUNCTION_CALL">
      <value>
        <option name="FOREGROUND" value="ff" />
      </value>
    </option>
    <option name="DEFAULT_LABEL" baseAttributes="DEFAULT_IDENTIFIER" />
  </attributes>
</scheme>
```

`tests/fixtures/edt_schemes/four-scopes.tmTheme` (четыре `scope`; `lineHighlight` с альфой;
scope-список через запятую):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>name</key>
  <string>Четыре области</string>
  <key>settings</key>
  <array>
    <dict>
      <key>settings</key>
      <dict>
        <key>background</key>
        <string>#1E1E1E</string>
        <key>foreground</key>
        <string>#D4D4D4</string>
        <key>lineHighlight</key>
        <string>#2A2A2AAA</string>
        <key>selection</key>
        <string>#264F78</string>
      </dict>
    </dict>
    <dict>
      <key>name</key>
      <string>Keyword</string>
      <key>scope</key>
      <string>keyword.control, keyword.other</string>
      <key>settings</key>
      <dict>
        <key>foreground</key>
        <string>#569CD6</string>
      </dict>
    </dict>
    <dict>
      <key>name</key>
      <string>String</string>
      <key>scope</key>
      <string>string</string>
      <key>settings</key>
      <dict>
        <key>foreground</key>
        <string>#CE9178</string>
      </dict>
    </dict>
    <dict>
      <key>name</key>
      <string>Comment</string>
      <key>scope</key>
      <string>comment.line</string>
      <key>settings</key>
      <dict>
        <key>foreground</key>
        <string>#6A9955</string>
        <key>fontStyle</key>
        <string>italic</string>
      </dict>
    </dict>
    <dict>
      <key>name</key>
      <string>Number</string>
      <key>scope</key>
      <string>constant.numeric</string>
      <key>settings</key>
      <dict>
        <key>foreground</key>
        <string>#B5CEA8</string>
      </dict>
    </dict>
  </array>
</dict>
</plist>
```

`tests/fixtures/edt_schemes/dark22.csi` (без BOM; `DesignerColors` — чтобы проверить, что
раздел игнорируется; одно неизвестное имя):

```json
{
  "DesignerColors": [
    {"Name": "Keywords", "Color": "#FF0000"}
  ],
  "EDTColors": [
    {"Name": "BSL_Keywords", "Color": "#CC7832"},
    {"Name": "BSL_Pragmas", "Color": "#BBB529"},
    {"Name": "Preprocessor", "Color": "#9876AA"},
    {"Name": "Builtinfunction", "Color": "#FFC66D"},
    {"Name": "Strings", "Color": "#6A8759"},
    {"Name": "Numbers", "Color": "#6897BB"},
    {"Name": "Comment", "Color": "#808080"},
    {"Name": "Operators", "Color": "#A9B7C6"},
    {"Name": "Brackets", "Color": "#A9B7C6"},
    {"Name": "Label", "Color": "#BBB529"},
    {"Name": "Others", "Color": "#A9B7C6"},
    {"Name": "Background", "Color": "#2B2B2B"},
    {"Name": "Foreground", "Color": "#A9B7C6"},
    {"Name": "SelectionBackground", "Color": "#214283"},
    {"Name": "SelectionForeground", "Color": "#A9B7C6"},
    {"Name": "currentLineColor", "Color": "#323232"},
    {"Name": "lineNumberColor", "Color": "#606366"},
    {"Name": "occurrenceIndicationColor", "Color": "#344134"},
    {"Name": "hyperlinkColor", "Color": "#287BDE"},
    {"Name": "FindScope", "Color": "#32593D"},
    {"Name": "currentIPColor", "Color": "#2D6099"},
    {"Name": "printMarginColor", "Color": "#555555"},
    {"Name": "Unknown", "Color": "#000000"}
  ]
}
```

- [ ] **Step 2: Тесты**

`tests/unit/test_edt_scheme_sources.py`:

```python
"""Разбор источников схем: .csi, IDEA XML/.jar, .tmTheme (спека v3.2, §3)."""

import io
import zipfile
from pathlib import Path

import pytest

from onecstarter.domain.edt_scheme import (
    COLOR_KEYS,
    EDT_DEFAULTS,
    Scheme,
    parse_csi,
    parse_idea_jar,
    parse_idea_xml,
    parse_tmtheme,
    tm_color,
    to_csi,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edt_schemes"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- .csi ---


def test_parse_csi_reads_edt_colors_skips_unknown_and_designer() -> None:
    colors = parse_csi(_read("dark22.csi"))
    assert len(colors) == 22
    assert colors["Builtinfunction"] == (255, 198, 109)
    assert colors["Background"] == (43, 43, 43)
    assert "Unknown" not in colors
    assert "Keywords" not in colors


def test_parse_csi_tolerates_bom_and_bad_colors() -> None:
    text = "\ufeff" + '{"EDTColors": [{"Name": "Strings", "Color": "zzz"}, {"Name": "Numbers", "Color": "#010203"}, 5]}'
    assert parse_csi(text) == {"Numbers": (1, 2, 3)}


@pytest.mark.parametrize("text", ['{"DesignerColors": []}', "[]", "not json", '{"EDTColors": 1}'])
def test_parse_csi_rejects_without_section(text: str) -> None:
    with pytest.raises(ValueError):
        parse_csi(text)


def test_to_csi_round_trips_and_writes_only_edt_colors() -> None:
    scheme = Scheme("x", parse_csi(_read("dark22.csi")))
    text = to_csi(scheme)
    assert text.endswith("\n")
    assert '"DesignerColors"' not in text
    assert parse_csi(text) == scheme.colors
    assert text.index('"BSL_Keywords"') < text.index('"printMarginColor"')


# --- IDEA ---


def test_parse_idea_xml_maps_attributes_and_colors() -> None:
    name, colors = parse_idea_xml(_read("idea-six.xml"))
    assert name == "Шесть атрибутов"
    assert colors["BSL_Keywords"] == (204, 120, 50)
    assert colors["Strings"] == (106, 135, 89)
    assert colors["Numbers"] == (104, 151, 187)
    assert colors["Comment"] == (128, 128, 128)
    assert colors["Builtinfunction"] == (0, 0, 255)  # `ff` без ведущих нулей
    assert colors["Background"] == (43, 43, 43)
    assert colors["Foreground"] == (169, 183, 198)
    assert colors["currentLineColor"] == (50, 50, 50)
    assert colors["lineNumberColor"] == (96, 99, 102)
    assert colors["SelectionBackground"] == (33, 66, 131)
    assert colors["printMarginColor"] == (47, 47, 47)  # `#2f2f2f`
    assert "SelectionForeground" not in colors  # пустое значение
    assert "Label" not in colors  # baseAttributes без value
    assert "Others" not in colors


def test_parse_idea_xml_without_colors_section_and_without_name() -> None:
    text = (
        "<scheme version=\"1\"><attributes><option name=\"DEFAULT_KEYWORD\"><value>"
        "<option name=\"FOREGROUND\" value=\"1\"/></value></option></attributes></scheme>"
    )
    name, colors = parse_idea_xml(text)
    assert name == ""
    assert colors == {"BSL_Keywords": (0, 0, 1)}


@pytest.mark.parametrize(
    "text",
    ["<theme name=\"x\"/>", "<scheme name=\"x\"", "", "plain text"],
)
def test_parse_idea_xml_rejects_non_scheme(text: str) -> None:
    with pytest.raises(ValueError):
        parse_idea_xml(text)


def _jar(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_parse_idea_jar_takes_first_scheme_under_colors() -> None:
    data = _jar(
        {
            "META-INF/plugin.xml": "<idea-plugin/>",
            "colors/Six.xml": _read("idea-six.xml"),
            "colors/Zeta.xml": "<scheme name=\"zeta\"/>",
        }
    )
    name, colors = parse_idea_jar(data)
    assert name == "Шесть атрибутов"  # первый по имени среди colors/*.xml
    assert colors["BSL_Keywords"] == (204, 120, 50)


def test_parse_idea_jar_falls_back_to_any_scheme_xml() -> None:
    data = _jar({"META-INF/plugin.xml": "<idea-plugin/>", "themes/Six.xml": _read("idea-six.xml")})
    assert parse_idea_jar(data)[0] == "Шесть атрибутов"


@pytest.mark.parametrize(
    "data",
    [b"not a zip", _jar({"META-INF/plugin.xml": "<idea-plugin/>"}), _jar({"colors/bad.xml": "<x>"})],
)
def test_parse_idea_jar_rejects(data: bytes) -> None:
    with pytest.raises(ValueError):
        parse_idea_jar(data)


def test_parse_idea_jar_corrupted_entry_is_value_error() -> None:
    data = bytearray(_jar({"colors/x.xml": _read("idea-six.xml")}))
    # портим имя в локальном заголовке первой записи (смещение 30 — начало имени): каталог
    # архива цел, а `read()` поднимает BadZipFile «File name in directory ... differ»
    data[30] = ord("z")
    with pytest.raises(ValueError, match="нет темы"):
        parse_idea_jar(bytes(data))


# --- tmTheme ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [("#1E1E1E", (30, 30, 30)), ("#2A2A2AAA", (42, 42, 42)), ("1e1e1e", (30, 30, 30)), ("#12", None), ("", None)],
)
def test_tm_color_strips_alpha(text: str, expected: tuple[int, int, int] | None) -> None:
    assert tm_color(text) == expected


def test_parse_tmtheme_maps_general_and_scopes() -> None:
    name, colors = parse_tmtheme(_read("four-scopes.tmTheme"))
    assert name == "Четыре области"
    assert colors["Background"] == (30, 30, 30)
    assert colors["Foreground"] == (212, 212, 212)
    assert colors["currentLineColor"] == (42, 42, 42)
    assert colors["SelectionBackground"] == (38, 79, 120)
    assert colors["BSL_Keywords"] == (86, 156, 214)
    assert colors["Strings"] == (206, 145, 120)
    assert colors["Comment"] == (106, 153, 85)
    assert colors["Numbers"] == (181, 206, 168)
    assert "Operators" not in colors
    assert "lineNumberColor" not in colors


def test_parse_tmtheme_scope_precedence_and_first_match_wins() -> None:
    text = (
        '<plist version="1.0"><dict><key>settings</key><array>'
        "<dict><key>scope</key><string>keyword.operator</string><key>settings</key><dict>"
        "<key>foreground</key><string>#010101</string></dict></dict>"
        "<dict><key>scope</key><string>keyword.control.import</string><key>settings</key><dict>"
        "<key>foreground</key><string>#020202</string></dict></dict>"
        "<dict><key>scope</key><string>keyword</string><key>settings</key><dict>"
        "<key>foreground</key><string>#030303</string></dict></dict>"
        "<dict><key>scope</key><string>keyword.control</string><key>settings</key><dict>"
        "<key>foreground</key><string>#040404</string></dict></dict>"
        "</array></dict></plist>"
    )
    name, colors = parse_tmtheme(text)
    assert name == ""
    assert colors["Operators"] == (1, 1, 1)
    assert colors["Preprocessor"] == (2, 2, 2)
    assert colors["BSL_Keywords"] == (3, 3, 3)  # первое совпадение, `keyword.control` позже


@pytest.mark.parametrize(
    "text",
    ["<plist version=\"1.0\"><dict><key>name</key><string>x</string></dict></plist>", "<plist>", "", "<plist version=\"1.0\"><array/></plist>"],
)
def test_parse_tmtheme_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_tmtheme(text)


def test_every_parser_output_completes_to_scheme() -> None:
    for colors in (
        parse_csi(_read("dark22.csi")),
        parse_idea_xml(_read("idea-six.xml"))[1],
        parse_tmtheme(_read("four-scopes.tmTheme"))[1],
    ):
        scheme = Scheme("x", {**EDT_DEFAULTS, **colors})
        assert list(scheme.colors) == [key.name for key in COLOR_KEYS]
```

- [ ] **Step 3: Прогон — падает**

Run: `uv run pytest tests/unit/test_edt_scheme_sources.py -q`
Expected: `ImportError` (`parse_csi` и остальные не определены).

- [ ] **Step 4: Реализация**

В начало модуля — импорты `io`, `json`, `plistlib`, `zipfile`, `from xml.etree import ElementTree`;
в конец:

```python
# --- .csi (JSON обработки заказчика) -----------------------------------------------
#
# [Ф] `{"DesignerColors": [...], "EDTColors": [{"Name", "Color": "#RRGGBB"}, …]}`; имена
# `EDTColors` — наши короткие имена (`Builtinfunction` без пробела). `DesignerColors`
# читаем мимо, при записи не пишем (спека §0).


def parse_csi(text: str) -> dict[str, RGB]:
    try:
        payload = json.loads(text.lstrip("\ufeff"))
    except ValueError as error:
        raise ValueError(f"не JSON: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("EDTColors"), list):
        raise ValueError("нет раздела EDTColors")
    result: dict[str, RGB] = {}
    for item in payload["EDTColors"]:
        if not isinstance(item, dict):
            continue
        name, color = item.get("Name"), item.get("Color")
        if not isinstance(name, str) or name not in KEY_BY_NAME or not isinstance(color, str):
            continue
        rgb = from_hex(color)
        if rgb is not None:
            result[name] = rgb
    return result


def to_csi(scheme: Scheme) -> str:
    payload = {
        "EDTColors": [
            {"Name": key.name, "Color": to_hex(scheme.colors[key.name])} for key in COLOR_KEYS
        ]
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# --- темы IntelliJ IDEA -------------------------------------------------------------
#
# [Ф] структура (641 тема каталога заказчика): `<scheme name version parent_scheme>` с
# `<colors><option name value/>` и `<attributes><option name><value><option name="FOREGROUND"
# value/>…`; `.icls` — тот же XML; `.jar` — zip с `colors/*.xml`. Соответствие атрибутов нашим
# ключам — [Р] первое приближение, Э11 правит (кортеж — запасные варианты по порядку).


@dataclass(frozen=True)
class IdeaSource:
    attribute: str  # имя option в <attributes> (component задан) или в <colors> (пусто)
    component: str = ""  # "FOREGROUND" | "BACKGROUND" | ""


IDEA_MAP: dict[str, tuple[IdeaSource, ...]] = {
    "BSL_Keywords": (IdeaSource("DEFAULT_KEYWORD", "FOREGROUND"),),
    "BSL_Pragmas": (IdeaSource("DEFAULT_METADATA", "FOREGROUND"),),
    "Preprocessor": (IdeaSource("DEFAULT_CONSTANT", "FOREGROUND"),),
    "Builtinfunction": (IdeaSource("DEFAULT_FUNCTION_CALL", "FOREGROUND"),),
    "Strings": (IdeaSource("DEFAULT_STRING", "FOREGROUND"),),
    "Numbers": (IdeaSource("DEFAULT_NUMBER", "FOREGROUND"),),
    "Comment": (IdeaSource("DEFAULT_LINE_COMMENT", "FOREGROUND"),),
    "Operators": (IdeaSource("DEFAULT_OPERATION_SIGN", "FOREGROUND"),),
    "Brackets": (IdeaSource("DEFAULT_BRACKETS", "FOREGROUND"),),
    "Label": (IdeaSource("DEFAULT_LABEL", "FOREGROUND"),),
    "Others": (IdeaSource("DEFAULT_IDENTIFIER", "FOREGROUND"),),
    "Background": (IdeaSource("TEXT", "BACKGROUND"),),
    "Foreground": (IdeaSource("TEXT", "FOREGROUND"),),
    "SelectionBackground": (IdeaSource("SELECTION_BACKGROUND"),),
    "SelectionForeground": (IdeaSource("SELECTION_FOREGROUND"),),
    "currentLineColor": (IdeaSource("CARET_ROW_COLOR"),),
    "lineNumberColor": (IdeaSource("LINE_NUMBERS_COLOR"),),
    "occurrenceIndicationColor": (IdeaSource("IDENTIFIER_UNDER_CARET_ATTRIBUTES", "BACKGROUND"),),
    "hyperlinkColor": (IdeaSource("HYPERLINK_ATTRIBUTES", "FOREGROUND"),),
    "FindScope": (IdeaSource("SEARCH_RESULT_ATTRIBUTES", "BACKGROUND"),),
    "currentIPColor": (IdeaSource("EXECUTIONPOINT_ATTRIBUTES", "BACKGROUND"),),
    "printMarginColor": (IdeaSource("RIGHT_MARGIN_COLOR"),),
}


def _idea_tables(root: ElementTree.Element) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    colors: dict[str, str] = {}
    attributes: dict[str, dict[str, str]] = {}
    colors_node = root.find("colors")
    if colors_node is not None:
        for option in colors_node.findall("option"):
            colors[option.get("name", "")] = option.get("value", "")
    attributes_node = root.find("attributes")
    if attributes_node is not None:
        for option in attributes_node.findall("option"):
            values = {
                inner.get("name", ""): inner.get("value", "")
                for inner in option.findall("value/option")
            }
            attributes[option.get("name", "")] = values
    return colors, attributes


def parse_idea_xml(text: str) -> tuple[str, dict[str, RGB]]:
    """(имя из атрибута `name` или "", цвета). Пустое значение → ключ не задан."""
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise ValueError(f"не XML: {error}") from error
    if root.tag != "scheme":
        raise ValueError(f"не тема IDEA: корень <{root.tag}>")
    colors, attributes = _idea_tables(root)
    result: dict[str, RGB] = {}
    for name, sources in IDEA_MAP.items():
        for source in sources:
            if source.component:
                value = attributes.get(source.attribute, {}).get(source.component, "")
            else:
                value = colors.get(source.attribute, "")
            rgb = idea_color(value)
            if rgb is not None:
                result[name] = rgb
                break
    return root.get("name", ""), result


def parse_idea_jar(data: bytes) -> tuple[str, dict[str, RGB]]:
    """Первая тема из `colors/*.xml`; если там нет — любой `*.xml` с корнем <scheme>."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ValueError(f"не zip: {error}") from error
    with archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        names.sort(key=lambda name: (not name.lower().startswith("colors/"), name.lower()))
        for name in names:
            try:
                return parse_idea_xml(archive.read(name).decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError, zipfile.BadZipFile):
                # BadZipFile и из `read()`: каталог архива цел, запись повреждена
                # (ревью задачи 3) — такая запись просто не тема
                continue
    raise ValueError("в архиве нет темы (colors/*.xml)")


# --- TextMate .tmTheme ---------------------------------------------------------------
#
# [Д] формат TextMate: plist, `settings` — массив словарей; первый без `scope` — общие цвета,
# остальные — по `scope` (список через запятую). Соответствие — [Р], Э11 на реальных файлах.
# Порядок кортежа важен: частные префиксы раньше общих (`keyword.operator` до `keyword`).

TMTHEME_SCOPES: tuple[tuple[str, str], ...] = (
    ("keyword.control.import", "Preprocessor"),
    ("meta.preprocessor", "Preprocessor"),
    ("keyword.operator", "Operators"),
    ("keyword", "BSL_Keywords"),
    ("constant.numeric", "Numbers"),
    ("constant.language", "BSL_Pragmas"),
    ("string", "Strings"),
    ("comment", "Comment"),
    ("support.function", "Builtinfunction"),
    ("entity.name.tag", "Label"),
    ("variable", "Others"),
    ("punctuation", "Brackets"),
)
TMTHEME_GENERAL: dict[str, str] = {
    "background": "Background",
    "foreground": "Foreground",
    "lineHighlight": "currentLineColor",
    "selection": "SelectionBackground",
    "selectionForeground": "SelectionForeground",
    "gutterForeground": "lineNumberColor",
    "findHighlight": "FindScope",
}
_TM_HEX = re.compile(r"^#?([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?$")


def tm_color(text: str) -> RGB | None:
    """`#RRGGBB` или `#RRGGBBAA` (альфа отбрасывается); иначе None."""
    match = _TM_HEX.match(text.strip())
    return None if match is None else from_hex(match.group(1))


def _scope_matches(scope: str, prefix: str) -> bool:
    return scope == prefix or scope.startswith(prefix + ".")


def parse_tmtheme(text: str) -> tuple[str, dict[str, RGB]]:
    try:
        payload = plistlib.loads(text.encode("utf-8"))
    except Exception as error:  # plistlib: ExpatError / ValueError / InvalidFileException
        raise ValueError(f"не plist: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("settings"), list):
        raise ValueError("нет массива settings")
    result: dict[str, RGB] = {}
    for entry in payload["settings"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("settings"), dict):
            continue
        values: dict[str, object] = entry["settings"]
        scope = entry.get("scope")
        if not isinstance(scope, str):
            for tm_key, our_key in TMTHEME_GENERAL.items():
                raw = values.get(tm_key)
                rgb = tm_color(raw) if isinstance(raw, str) else None
                if rgb is not None and our_key not in result:
                    result[our_key] = rgb
            continue
        raw = values.get("foreground")
        rgb = tm_color(raw) if isinstance(raw, str) else None
        if rgb is None:
            continue
        scopes = [part.strip() for part in scope.split(",")]
        for prefix, our_key in TMTHEME_SCOPES:
            if our_key not in result and any(_scope_matches(s, prefix) for s in scopes):
                result[our_key] = rgb
                break
    name = payload.get("name")
    return (name if isinstance(name, str) else ""), result
```

Замечание к `parse_tmtheme`: `except Exception` — единственное место; `plistlib` поднимает
`xml.parsers.expat.ExpatError`, `ValueError`, `plistlib.InvalidFileException` в зависимости
от порчи, перечислять их — хрупко. `BLE` в ruff проекта не включён, `noqa` не нужен
(`RUF100` включён и ругается на лишние `noqa`).

Проверка precedence в `test_parse_tmtheme_scope_precedence…`: `keyword.operator` совпадает с
префиксом `keyword.operator` (Operators), а с `keyword` — тоже, но `Operators` стоит раньше в
`TMTHEME_SCOPES`, и цикл прерывается на первом совпадении; `keyword.control.import` → Preprocessor;
`keyword` → BSL_Keywords; `keyword.control` (четвёртый) → BSL_Keywords уже занят → пропуск.

- [ ] **Step 5: Прогон — зелёный, статика**

Run: `uv run pytest tests/unit/test_edt_scheme_sources.py tests/unit/test_edt_scheme_prefs.py tests/unit/test_edt_scheme_model.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/domain/edt_scheme.py tests/unit/test_edt_scheme_sources.py tests/fixtures/edt_schemes/
git commit -m "feat(edt): разбор .csi, тем IDEA (xml/jar) и .tmTheme — цвет IDEA без ведущих нулей (v3.2, задача 3)"
```

---

### Task 4: Протокол Э8–Э11 и скрипт `t19-edt-scheme.py`

**Files:**
- Create: `docs/research/t19-edt-scheme-experiments.md`
- Create: `docs/research/t19-edt-scheme.py`

**Interfaces:**
- Consumes: домен Task 1–3 (`parse_csi`, `complete`, `prefs_updates`, `render_prefs`, `parse_prefs`,
  `parse_idea_xml`, `parse_tmtheme`, `to_hex`, `is_dark`, `Scheme`, `THEME_IDS`, `THEME_KEY`,
  константы файлов).
- Produces: протокол для заказчика и скрипт, которым агент пишет и снимает файлы; EDT скрипт
  **не запускает**.

- [ ] **Step 1: Протокол**

`docs/research/t19-edt-scheme-experiments.md`:

```markdown
# T-19. Э8–Э11 — цветовая схема рабочей области EDT (v3.2)

Заказчик выполняет шаги (запуск и выход EDT, действия в редакторе), агент пишет и снимает
файлы скриптом `docs/research/t19-edt-scheme.py` (домен `edt_scheme`, без сервиса и UI).
Каждый исход правит метку в спеке v3.2 §0 и скил `edt-launch` (раздел «Цвета редактора»);
опровергнутый факт — код и тест в том же коммите. Дата проведения — <дата>.

Тестовая рабочая область — `E:\tmp\edt-scheme\ws1` (новый пустой каталог; тестовые области v3
удалены 18.09.2026). Рабочие области заказчика `E:\edt\…` не участвуют. EDT — 2026.1.2+2
(`C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64`), запись в OneCStarter
«Схема-тест» → `E:\tmp\edt-scheme\ws1`. Схема для записи — `tests/fixtures/edt_schemes/dark22.csi`
(своя тёмная; ключевые слова `#CC7832`, фон `#2B2B2B`). Снимки — `E:\tmp\edt-scheme\snap\<чч-мм-сс>\`.

Команды агента (все — из корня репозитория):

- `uv run python docs/research/t19-edt-scheme.py snapshot E:\tmp\edt-scheme\ws1 E:\tmp\edt-scheme\snap`
- `uv run python docs/research/t19-edt-scheme.py write E:\tmp\edt-scheme\ws1 --csi tests/fixtures/edt_schemes/dark22.csi --canary`
- `… write … --no-system-default` (шаг Э8.3), `… theme E:\tmp\edt-scheme\ws1 dark|light|<id>` (Э9)
- `uv run python docs/research/t19-edt-scheme.py idea-stats "<путь к Template.bin или каталогу тем>" --show "<тема>"` (Э11)
- `uv run python docs/research/t19-edt-scheme.py tmtheme "<файл.tmTheme>"` (Э11)
- `uv run python docs/research/t19-edt-scheme.py defaults "<каталог plugins EDT>" "<javap.exe>"` (Э10)

## Э8. Приём нашей записи

**Цель.** EDT читает prefs, записанные `render_prefs`; что EDT переписывает при выходе
(перевод строки, порядок, неизвестные ключи); нужен ли `.SystemDefault=false`; теряется ли
правка при запущенном EDT ([Д] → [Ф]).

**Шаг 0 (заказчик).** Создать каталог `E:\tmp\edt-scheme\ws1`, запись «Схема-тест» в
OneCStarter, «Открыть в EDT». В EDT завести проект (New → Project… любого типа или импорт
любого тестового проекта) и открыть модуль — цвета по умолчанию (светлые). File → Exit.
**Агент:** `snapshot` → в `.settings` нет `com._1c.g5.v8.dt.bsl.ui.prefs` и
`org.eclipse.ui.editors.prefs`? Записать перечень файлов каталога.

**Шаг 1 (агент).** `write … --csi dark22.csi --canary` → оба файла созданы (CRLF, версия,
ключ-канарейка `onecstarter.canary=1`). `snapshot`. **Заказчик:** «Открыть в EDT», открыть
модуль: фон тёмный, ключевые слова оранжевые (`#CC7832`), строки зелёные? Ответ и (по желанию)
скриншот. File → Exit. **Агент:** `snapshot` — сравнить с предыдущим: перевод строки (CRLF/LF),
порядок ключей, `onecstarter.canary` на месте?, наши 22 значения не изменены?, появились ли
новые ключи (перечислить).

| Поле | Результат |
| --- | --- |
| Цвета в редакторе после запуска | |
| Файлы после выхода: перевод строки | |
| Порядок ключей / новые ключи | |
| `onecstarter.canary` | |
| Наши значения | |

**Шаг 2 (агент, гонка).** При **запущенном** EDT на `ws1` (заказчик подтверждает, что открыт)
выполнить `write … --csi dark22.csi` с предварительно изменённым цветом: сначала
`uv run python -c "…"` не нужно — скрипт принимает `--override Strings=#FF00FF`. **Заказчик:**
File → Exit. **Агент:** `snapshot` — `Strings` в файле `255,0,255` (правка пережила выход) или
прежнее (EDT переписал из памяти)?

**Шаг 3 (агент).** EDT закрыт. `write … --csi dark22.csi --no-system-default` (без пяти
`.SystemDefault=false`). **Заказчик:** запуск, открыть модуль: фон редактора тёмный (наш) или
белый (системный)? Выход. **Агент:** `snapshot`.

**Куда уходит.** §0 строки «Ключи редактора … `.SystemDefault=false`», «Формат файла»,
«EDT при выходе перезаписывает prefs»; `NEW_PREFS_NEWLINE` (если EDT переписал с LF — константа
`"\n"`); скил `edt-launch` — новый раздел «Цвета редактора».

## Э9. Тема окна

**Цель.** id светлой темы; читает ли EDT `themeid` при старте; не перекрывает ли тёмная тема
наши цвета токенов (в `bsl.ui` есть `css/dark/edt-dark_preferencestyle.css`, который задаёт
9 из 11 токенов через `IEclipsePreferences` — [Д] ресурс плагина, 18.09.2026).

**Шаг 0 (агент, [Д]).** Перечислить id тем из `plugin.xml` jar `org.eclipse.ui.themes_*`
(`plugins\` установки 2026.1.2): `<theme id="…" label="…">`. Записать таблицу id → label.

**Шаг 1 (заказчик).** EDT на `ws1`: Window → Preferences → General → Appearance → Theme:
светлая (Light), Apply and Restart (или выход). **Агент:** `snapshot` →
`org.eclipse.e4.ui.css.swt.theme.prefs`: значение `themeid` — id светлой **[Ф]**.

**Шаг 2 (агент).** EDT закрыт. `theme ws1 dark`. **Заказчик:** запуск — окно тёмное? Выход.
**Шаг 3 (агент).** `theme ws1 light` (id из шага 1). **Заказчик:** запуск — окно светлое? Выход.

**Шаг 4 (агент).** EDT закрыт. `write … --csi dark22.csi` + `theme ws1 dark`. **Заказчик:**
запуск, открыть модуль: ключевые слова `#CC7832` (наши) или `255,120,90` (CSS тёмной темы)?
Выход. **Агент:** `snapshot` — `bsl.ui.prefs`: значения наши или из CSS?

| Шаг | Результат |
| --- | --- |
| 0. id тем | |
| 1. светлый id | |
| 2. тёмная по `themeid` | |
| 3. светлая по `themeid` | |
| 4. тёмная тема vs наши токены | |

**Куда уходит.** §0 «Тема окна EDT»; `THEME_IDS` (светлый id — или `{}`, если шаги 2–3
показали, что ключ при старте не читается); если шаг 4 показал перекрытие — спека §5:
переключатель «тёмная» применяет тему, а схема — при следующем «Применить» (текст диалога),
либо переключатель убирается; решение — заказчика.

## Э10. Цвета EDT по умолчанию

**Цель.** `EDT_DEFAULTS` — из установки, не с потолка.

**Шаг 1 (агент, [Д]).** `defaults "<plugins>" "<javap>"`: скрипт печатает (а) строки
`plugin.xml` четырёх jar (`org.eclipse.ui.editors`, `org.eclipse.ui.workbench.texteditor`,
`org.eclipse.debug.ui`, `com._1c.g5.v8.dt.bsl.ui`) с нашими ключами и `colorPreferenceValue`;
(б) `javap -c -p` классов `com._1c.g5.v8.dt.bsl.ui.syntaxcoloring.BslHighlightingConfiguration`,
`org.eclipse.ui.texteditor.AbstractDecoratedTextEditorPreferenceConstants`,
`org.eclipse.ui.internal.editors.text.TextEditorDefaultsPreferenceInitializer` — фрагменты
вокруг `org/eclipse/swt/graphics/RGB."<init>"` с предшествующими `bipush`/`sipush`/`iconst`
и ближайшей строкой `ldc`; (в) `css/dark/edt-dark_preferencestyle.css` из `bsl.ui`
(тёмные значения токенов). `javap` — `C:\Program Files\1C\1CE\components\axiom-jdk-full-*\bin\javap.exe`
(найти сканом, не хардкодить).

**Шаг 2 (заказчик, только если шаг 1 не дал 22 значений).** Скриншот модуля в чистой
рабочей области (светлая тема), агент снимает цвета пипеткой → **[Ф, визуально]**.

| Ключ | Значение | Источник / метка |
| --- | --- | --- |
| BSL_Keywords | | |
| … (22 строки) | | |

**Куда уходит.** `EDT_DEFAULTS` с меткой в комментарии; §0 «Цвета EDT по умолчанию».

## Э11. Реальные темы через наш разбор

**Цель.** Таблицы `IDEA_MAP`/`TMTHEME_SCOPES` дают ожидаемое на настоящих файлах.

**Шаг 1 (агент).** `idea-stats "<temp\color\…\IDEA_Themes\Ext\Template.bin>" --show "<светлая>" --show "<тёмная>" --show "<с пустыми>"`
— по каждому из 22 ключей: в скольких из 641 тем цвет найден; для отсутствующих — какие
атрибуты IDEA встречаются в таких темах чаще всего (кандидаты в запасные `IdeaSource`);
три темы — таблица «ключ → hex» и `is_dark`. Ожидание: `Background`/`Foreground`/`BSL_Keywords`/
`Strings`/`Comment`/`Numbers` ≥ 90 %; для остальных — решение по кандидатам.

**Шаг 2 (агент + заказчик).** Файл `.tmTheme` из каталога заказчика (путь — у заказчика;
если нет — поиск `Get-ChildItem -Path $env:USERPROFILE,E:\ -Recurse -Filter *.tmTheme -ErrorAction SilentlyContinue | Select-Object -First 5`);
`tmtheme "<файл>"` — таблица ключ → hex; сверка с ожиданием (ключевые слова, строки,
комментарии, фон). Нет файла — метка `.tmTheme` остаётся **[Д]**, записать.

| Тема | Найдено ключей | Расхождения | Правка таблицы |
| --- | --- | --- | --- |

**Куда уходит.** `IDEA_MAP` (запасные источники), `TMTHEME_SCOPES`/`TMTHEME_GENERAL`,
тесты `test_edt_scheme_sources.py`; §0 строки «Тема IDEA», «`.tmTheme`», «Соответствие».
```

- [ ] **Step 2: Скрипт**

`docs/research/t19-edt-scheme.py`:

```python
"""T-19 (v3.2), Э8–Э11: запись prefs нашим рендером, снимки файлов рабочей области,
статистика разбора тем IDEA, поиск умолчаний EDT в jar. EDT скрипт НЕ запускает.

Запуск: `uv run python docs/research/t19-edt-scheme.py <команда> …` (домен `edt_scheme`
доступен через установленный пакет). Протокол — `t19-edt-scheme-experiments.md`.
"""

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    EDITORS_PREFS,
    SYSTEM_DEFAULT_SUFFIX,
    THEME_IDS,
    THEME_KEY,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    complete,
    from_hex,
    is_dark,
    parse_csi,
    parse_idea_xml,
    parse_prefs,
    parse_tmtheme,
    prefs_updates,
    render_prefs,
    to_hex,
    unescape_property,
)

SETTINGS = Path(".metadata") / ".plugins" / "org.eclipse.core.runtime" / ".settings"
CANARY = "onecstarter.canary"
PREFS_FILES = (BSL_PREFS, EDITORS_PREFS, THEME_PREFS)
BASE_KEYS = {unescape_property(key.prefs_key) for key in COLOR_KEYS}
# всё, что пишет prefs_updates: 22 ключа и пять .SystemDefault (ревью задачи 4 —
# без флагов снимок называл свои же ключи «чужими»)
OUR_KEYS = BASE_KEYS | {
    unescape_property(key.prefs_key + SYSTEM_DEFAULT_SUFFIX)
    for key in COLOR_KEYS
    if key.system_default
}
EDITOR_KEY_NAMES = tuple(key.prefs_key for key in COLOR_KEYS if key.prefs_file == EDITORS_PREFS)
JAVAP_CLASSES = {
    "com._1c.g5.v8.dt.bsl.ui_": "com._1c.g5.v8.dt.bsl.ui.syntaxcoloring.BslHighlightingConfiguration",
    "org.eclipse.ui.workbench.texteditor_": "org.eclipse.ui.texteditor.AbstractDecoratedTextEditorPreferenceConstants",
    "org.eclipse.ui.editors_": "org.eclipse.ui.internal.editors.text.TextEditorDefaultsPreferenceInitializer",
}
PLUGIN_XML_JARS = ("org.eclipse.ui.editors_", "org.eclipse.ui.workbench.texteditor_", "org.eclipse.debug.ui_", "com._1c.g5.v8.dt.bsl.ui_")


def settings_dir(workspace: str) -> Path:
    return Path(workspace) / SETTINGS


def read(path: Path) -> str:
    return path.read_bytes().decode("latin-1") if path.exists() else ""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("latin-1"))
    print(f"записан {path}: {len(text)} байт")


def newline_kind(text: str) -> str:
    crlf, lf = text.count("\r\n"), text.count("\n")
    if crlf and crlf == lf:
        return "CRLF"
    if lf and not crlf:
        return "LF"
    return f"смешанный (CRLF {crlf}, LF {lf - crlf})" if lf else "нет переводов"


def cmd_write(args: argparse.Namespace) -> None:
    scheme = complete(Path(args.csi).stem, parse_csi(Path(args.csi).read_text(encoding="utf-8-sig")))
    if args.override:
        colors = dict(scheme.colors)
        for item in args.override:
            name, _, value = item.partition("=")
            rgb = from_hex(value)
            if rgb is None or name not in colors:
                sys.exit(f"плохой --override {item}")
            colors[name] = rgb
        scheme = Scheme(scheme.name, colors)
    updates = prefs_updates(scheme)
    for name in (BSL_PREFS, EDITORS_PREFS):
        pairs = dict(updates[name])
        remove: list[str] = []
        if args.no_system_default:
            remove = [key for key in pairs if key.endswith(SYSTEM_DEFAULT_SUFFIX)]
            pairs = {key: value for key, value in pairs.items() if key not in remove}
        if args.canary:
            pairs[CANARY] = "1"
        path = settings_dir(args.workspace) / name
        write(path, render_prefs(read(path), pairs, remove))


def cmd_theme(args: argparse.Namespace) -> None:
    choice = {"dark": ThemeChoice.DARK, "light": ThemeChoice.LIGHT}.get(args.theme)
    theme_id = THEME_IDS.get(choice) if choice is not None else args.theme
    if not theme_id:
        sys.exit(f"нет id для {args.theme}: заполните THEME_IDS или передайте id явно")
    path = settings_dir(args.workspace) / THEME_PREFS
    write(path, render_prefs(read(path), {THEME_KEY: theme_id}))


def cmd_snapshot(args: argparse.Namespace) -> None:
    source = settings_dir(args.workspace)
    target = Path(args.out) / datetime.now().strftime("%H-%M-%S")
    target.mkdir(parents=True, exist_ok=True)
    print(f"каталог {source}: {'есть' if source.is_dir() else 'нет'}")
    if source.is_dir():
        print("  файлы:", ", ".join(sorted(p.name for p in source.iterdir())))
    for name in PREFS_FILES:
        path = source / name
        print(f"--- {name}")
        if not path.exists():
            print("  нет файла")
            continue
        shutil.copy2(path, target / name)
        text = read(path)
        lines = text.replace("\r\n", "\n").split("\n")
        parsed = parse_prefs(text)
        keys = [k for k in parsed]
        print(f"  {len(text)} байт, перевод строки: {newline_kind(text)}")
        print(f"  первая строка: {lines[0]!r}; последняя: {lines[-2] if lines[-1] == '' else lines[-1]!r}")
        print(f"  ключей {len(keys)}, по алфавиту: {keys == sorted(keys)}")
        print(f"  наших ключей: {len(BASE_KEYS & set(keys))} из 22; .SystemDefault: {sum(k.endswith(SYSTEM_DEFAULT_SUFFIX) for k in keys)}")
        print(f"  канарейка {CANARY}: {parsed.get(CANARY, '—')}")
        for key in sorted(set(keys) - OUR_KEYS - {CANARY, "eclipse.preferences.version"}):
            print(f"  чужой ключ: {key}={parsed[key]!r}")
        if name == THEME_PREFS:
            print(f"  {THEME_KEY}={parsed.get(THEME_KEY, '—')}")
    print(f"снимок: {target}")


def _iter_idea_themes(source: Path) -> Iterator[tuple[str, str]]:
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if path.suffix.lower() in (".xml", ".icls"):
                yield path.name, path.read_text(encoding="utf-8-sig", errors="replace")
        return
    with zipfile.ZipFile(source) as archive:
        for name in sorted(archive.namelist()):
            if name.lower().endswith((".xml", ".icls")):
                try:
                    data = archive.read(name)
                except zipfile.BadZipFile as error:  # битая запись не роняет статистику
                    print(f"! {name}: повреждённая запись архива ({error})")
                    continue
                yield name, data.decode("utf-8-sig", errors="replace")


def cmd_idea_stats(args: argparse.Namespace) -> None:
    present: Counter[str] = Counter()
    candidates: dict[str, Counter[str]] = {key.name: Counter() for key in COLOR_KEYS}
    total = 0
    shown = {name.casefold() for name in args.show}
    for file_name, text in _iter_idea_themes(Path(args.source)):
        try:
            theme_name, colors = parse_idea_xml(text)
        except ValueError as error:
            print(f"! {file_name}: {error}")
            continue
        total += 1
        present.update(colors.keys())  # не `update(colors)`: Counter суммировал бы значения
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            root = None
        if root is not None:
            attributes = {
                option.get("name", ""): {
                    inner.get("name", ""): inner.get("value", "")
                    for inner in option.findall("value/option")
                }
                for option in root.findall("attributes/option")
            }
            for key in COLOR_KEYS:
                if key.name in colors or key.prefs_file != BSL_PREFS:
                    continue
                for attr, values in attributes.items():
                    if attr.startswith("DEFAULT_") and values.get("FOREGROUND"):
                        candidates[key.name][attr] += 1
        if file_name.casefold() in shown or Path(file_name).stem.casefold() in shown or theme_name.casefold() in shown:
            scheme = complete(theme_name or file_name, colors)
            print(f"=== {file_name} ({theme_name!r}), тёмная: {is_dark(scheme)}, найдено {len(colors)} из 22")
            for key in COLOR_KEYS:
                mark = "" if key.name in colors else "  (дополнен)"
                print(f"  {key.name:<26} {to_hex(scheme.colors[key.name])}{mark}")
    print(f"тем разобрано: {total}")
    for key in COLOR_KEYS:
        count = present[key.name]
        line = f"{key.name:<26} {count:>4} / {total} ({100 * count // max(total, 1):>3} %)"
        if count < total and candidates[key.name]:
            top = ", ".join(f"{attr} {n}" for attr, n in candidates[key.name].most_common(4))
            line += f"   кандидаты: {top}"
        print(line)


def cmd_tmtheme(args: argparse.Namespace) -> None:
    name, colors = parse_tmtheme(Path(args.file).read_text(encoding="utf-8-sig"))
    scheme = complete(name or Path(args.file).stem, colors)
    print(f"{args.file}: {name!r}, тёмная: {is_dark(scheme)}, найдено {len(colors)} из 22")
    for key in COLOR_KEYS:
        mark = "" if key.name in colors else "  (дополнен)"
        print(f"  {key.name:<26} {to_hex(scheme.colors[key.name])}{mark}")


def cmd_defaults(args: argparse.Namespace) -> None:
    plugins = Path(args.plugins)
    for prefix in PLUGIN_XML_JARS:
        for jar in sorted(plugins.glob(f"{prefix}*.jar")):
            with zipfile.ZipFile(jar) as archive:
                names = archive.namelist()
                if "plugin.xml" in names:
                    text = archive.read("plugin.xml").decode("utf-8", errors="replace")
                    for match in re.finditer(r"<[^<>]*(%s)[^<>]*>" % "|".join(map(re.escape, EDITOR_KEY_NAMES)), text):
                        print(f"[{jar.name} plugin.xml] {' '.join(match.group(0).split())}")
                for name in names:
                    if name.endswith("preferencestyle.css"):
                        print(f"[{jar.name} {name}]")
                        print(archive.read(name).decode("utf-8", errors="replace"))
    for prefix, class_name in JAVAP_CLASSES.items():
        for jar in sorted(plugins.glob(f"{prefix}*.jar")):
            print(f"=== javap {jar.name} {class_name}")
            result = subprocess.run(
                [args.javap, "-c", "-p", "-cp", str(jar), class_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            lines = result.stdout.splitlines()
            for index, line in enumerate(lines):
                if 'org/eclipse/swt/graphics/RGB."<init>"' in line:
                    context = lines[max(0, index - 8) : index + 1]
                    print("\n".join(context))
                    print("-")
            if result.returncode:
                print(result.stderr[:500])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("write", help="записать prefs рабочей области из .csi")
    p.add_argument("workspace")
    p.add_argument("--csi", required=True)
    p.add_argument("--canary", action="store_true", help="добавить ключ onecstarter.canary=1")
    p.add_argument("--no-system-default", action="store_true", help="без .SystemDefault=false")
    p.add_argument("--override", action="append", default=[], help="Имя=#RRGGBB, повторяемый")
    p.set_defaults(func=cmd_write)
    p = sub.add_parser("theme", help="записать themeid")
    p.add_argument("workspace")
    p.add_argument("theme", help="dark | light | <id темы>")
    p.set_defaults(func=cmd_theme)
    p = sub.add_parser("snapshot", help="снять три prefs-файла и описать их")
    p.add_argument("workspace")
    p.add_argument("out")
    p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser("idea-stats", help="статистика разбора тем IDEA (zip или каталог)")
    p.add_argument("source")
    p.add_argument("--show", action="append", default=[], help="имя темы/файла для таблицы")
    p.set_defaults(func=cmd_idea_stats)
    p = sub.add_parser("tmtheme", help="таблица цветов одного .tmTheme")
    p.add_argument("file")
    p.set_defaults(func=cmd_tmtheme)
    p = sub.add_parser("defaults", help="умолчания EDT из jar установки")
    p.add_argument("plugins")
    p.add_argument("javap")
    p.set_defaults(func=cmd_defaults)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Проверка скрипта без EDT**

Run (каталог `E:\tmp\edt-scheme\dry` — временный, EDT не запускается):

```bash
uv run python docs/research/t19-edt-scheme.py write E:/tmp/edt-scheme/dry --csi tests/fixtures/edt_schemes/dark22.csi --canary
uv run python docs/research/t19-edt-scheme.py snapshot E:/tmp/edt-scheme/dry E:/tmp/edt-scheme/snap-dry
uv run python docs/research/t19-edt-scheme.py write E:/tmp/edt-scheme/dry --csi tests/fixtures/edt_schemes/dark22.csi --no-system-default --override Strings=#FF00FF
uv run python docs/research/t19-edt-scheme.py snapshot E:/tmp/edt-scheme/dry E:/tmp/edt-scheme/snap-dry
uv run python docs/research/t19-edt-scheme.py idea-stats tests/fixtures/edt_schemes --show "Шесть атрибутов"
uv run python docs/research/t19-edt-scheme.py tmtheme tests/fixtures/edt_schemes/four-scopes.tmTheme
uv run ruff check docs/research/t19-edt-scheme.py
```

Expected: два файла созданы (CRLF, канарейка); второй снимок — `.SystemDefault` 0, `Strings`
`255,0,255`, канарейка на месте (файл существовал — `render_prefs` сохранил); `idea-stats`
разбирает `idea-six.xml` (11 из 22); `tmtheme` — 8 из 22; ruff чист (mypy на `docs/` не
смотрит — `files` в pyproject). Каталог `dry` удалить.

- [ ] **Step 4: Коммит**

```bash
git add docs/research/t19-edt-scheme-experiments.md docs/research/t19-edt-scheme.py
git commit -m "docs: протокол Э8–Э11 цветовой схемы EDT и скрипт записи/снимков prefs (v3.2, задача 4)"
```

---

### Task 5: Проведение Э8–Э11 и возврат исходов

**Выполняется координатором с заказчиком** (не субагентом): нужны разрешение на запуск EDT
на `E:\tmp\edt-scheme\ws1`, действия в EDT и закрытый EDT между шагами. Э10 и Э11 — работа
агента без EDT (jar установки, архив тем в `temp/`), их можно провести до разрешения.

**Files:**
- Modify: `docs/research/t19-edt-scheme-experiments.md` (результаты)
- Modify: `docs/superpowers/specs/2026-09-16-v32-edt-color-scheme-design.md` (§0, §3, §5)
- Modify: `src/onecstarter/domain/edt_scheme.py` (`EDT_DEFAULTS`, `THEME_IDS`, `NEW_PREFS_NEWLINE`,
  `IDEA_MAP`, `TMTHEME_SCOPES`/`TMTHEME_GENERAL` — по исходам) и тесты Task 1–3
- Modify: `.claude/skills/edt-launch/SKILL.md` (новый раздел «Цвета редактора»),
  `.claude/skills/edt-launch/reference.md` (таблица ключей prefs)
- Modify: `docs/tasks.md` (новый раздел `T-19` между T-18 и T-20 — каркас с таблицей задач и
  «Итог Э8–Э11»)

- [ ] **Step 1: Э10 и Э11 (агент)**

Run: `uv run python docs/research/t19-edt-scheme.py defaults "C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64\plugins" "<javap из axiom-jdk-full-*\bin>" > e:/tmp/t19-defaults.txt 2>&1`
и `idea-stats` по `temp\color\PUBID_1236182-ColorSchemesInstaller\Templates\IDEA_Themes\Ext\Template.bin`
с тремя `--show`. Заполнить таблицы Э10/Э11 в протоколе; `EDT_DEFAULTS` — значения с меткой
([Д] javap/plugin.xml — назвать класс и jar; иначе [?] с предложением шага 2). Кандидаты Э11
с долей ≥ 20 % среди тем без основного атрибута — добавить запасными `IdeaSource` в `IDEA_MAP`,
дописать тест в `test_edt_scheme_sources.py` (тема без основного атрибута берёт запасной).

- [ ] **Step 2: Разрешение и Э8 (заказчик + агент)**

Спросить заказчика: EDT закрыт; разрешение на запуски EDT 2026.1.2+2 на `E:\tmp\edt-scheme\ws1`
(3–4 запуска по ~1 мин). Проверка перед каждой записью:
`Get-CimInstance Win32_Process -Filter "Name='1cedt.exe'" | Select-Object ProcessId, CommandLine`
— нет процесса с `-data E:\tmp\edt-scheme\ws1` (другие рабочие области заказчика могут быть
открыты — не мешают). Шаги 0–3 Э8 по протоколу; результаты дословно в таблицу.

- [ ] **Step 3: Э9 (заказчик + агент)**

Шаги 0–4 Э9. Шаг 4 — только если шаги 2–3 подтвердили чтение `themeid`.

- [ ] **Step 4: Метки и константы**

| Исход | Правка |
| --- | --- |
| Э8.1: цвета применились, EDT переписал файл | §0 «Формат файла» → [Ф] с датой, перевод строки по факту; `NEW_PREFS_NEWLINE` = как пишет EDT; в скиле — «Цвета редактора» |
| Э8.1: канарейка пропала | §0 → EDT удаляет неизвестные ключи [Ф]; `render_prefs` не меняем (чужие ключи всё равно сохраняем — их пишут другие плагины), записать в скил |
| Э8.2: правка при запущенном EDT потеряна | §0 «EDT при выходе перезаписывает» → [Ф]; предусловие «EDT закрыт» обосновано |
| Э8.2: правка пережила выход | §0 → [Ф] «не перезаписывает, если не менял»; предусловие остаётся (гонка возможна при смене настроек), записать |
| Э8.3: без `.SystemDefault=false` фон системный | §0 → [Ф]; ничего не менять |
| Э8.3: фон наш и без флага | §0 → флаг не обязателен [Ф]; пишем всё равно (совместимость с обработкой), записать |
| Э9.1–3: `themeid` читается | `THEME_IDS[ThemeChoice.LIGHT] = "<id>"`; тест `test_theme_prefs_update_follows_theme_ids` — ветка LIGHT; §0 → [Ф] |
| Э9.2–3: не читается | `THEME_IDS = {}`; §0 → [Ф] «не читается при старте»; §5 спеки — переключатель убран (комбо скрыт по `THEME_IDS`); в скил |
| Э9.4: тёмная тема перекрыла токены | §5 спеки: при выборе «тёмная» диалог предупреждает текстом «Тёмная тема EDT заменяет цвета токенов при первом запуске; примените схему повторно после него» — решение заказчика: предупреждение или убрать «тёмная» из комбо; Task 9 получает выбранный вариант |
| Э10: значения найдены | `EDT_DEFAULTS` с меткой [Д] и источником |
| Э11: расхождения | `IDEA_MAP`/`TMTHEME_*` и тесты одним коммитом |

Уточнения по находкам планирования (hex IDEA, `Builtinfunction`, `NEW_PREFS_NEWLINE`,
«По умолчанию EDT» = снятие ключей, `render_prefs` «на месте», `CatalogEntry` без `error`,
CSS тёмной темы, новая тестовая область) в спеку **уже внесены 18.09.2026 вместе с планом** —
Task 5 правит только метки и константы по исходам. В `SKILL.md` — раздел «Цвета редактора» после «Реестр проектов
workspace»: пути двух файлов, 22 ключа (таблица — в `reference.md`), `.SystemDefault`, формат
и перевод строки, что EDT делает при выходе, `themeid` и id тем, CSS тёмной темы; каждая
строка с меткой. «Где это в коде» — `domain/edt_scheme.py`, `services/edt_scheme.py`.

- [ ] **Step 5: Прогон и коммит**

Run: `uv run pytest tests/unit/test_edt_scheme_model.py tests/unit/test_edt_scheme_prefs.py tests/unit/test_edt_scheme_sources.py -q && uv run ruff check . && uv run mypy`

```bash
git add docs/research/t19-edt-scheme-experiments.md docs/superpowers/specs/2026-09-16-v32-edt-color-scheme-design.md src/onecstarter/domain/edt_scheme.py tests/unit/ .claude/skills/edt-launch/ docs/tasks.md
git commit -m "docs(edt): Э8–Э11 проведены — метки в спеке и скиле, умолчания EDT, id тем, таблицы соответствия (v3.2, задача 5)"
```

- [x] **Итог (18–20.09.2026, два коммита: 5а `b6871db` — Э10/Э11/Э9-0 агентом, 5б `e3beb0e` —
  Э8/Э9 с заказчиком).** Э8: prefs приняты; при выходе EDT переписывает только изменённые в
  памяти узлы — правка при запущенной EDT пережила выход [Ф]; без `.SystemDefault=false` фон
  системный белый [Ф]; при смене темы `editors.prefs` переписан байт в байт (CRLF, порядок,
  канарейка) — `NEW_PREFS_NEWLINE` CRLF [Ф]. Э9: светлый id `e4_default` [Ф], `themeid`
  читается при старте [Ф], CSS тёмной темы наши токены не перекрывает и в prefs не пишет [Ф] →
  комбо «Тема окна» — три варианта, предупреждение не нужно. Э10: `EDT_DEFAULTS` из байткода и
  `plugin.xml` [Д], расхождение одно — `hyperlinkColor` 0,102,204. Э11: 626/641 тем, 15 битых
  XML (не чиним), цепочки запасных источников в `IDEA_MAP` (покрытие 80–94 %); `.tmTheme` —
  [Д], файла нет. Четыре запуска EDT вместо 7–8 (шаги объединены). Спека §0/§1/§5/§8, скил
  `edt-launch` («Цвета редактора», `reference.md` §8), `docs/tasks.md` T-19 — обновлены.

---

### Task 6: Сервис — `SchemeCatalog`, `WorkspaceSchemes`, `save_csi`

**Files:**
- Create: `src/onecstarter/services/edt_scheme.py`
- Create: `tests/unit/test_edt_scheme_service.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (`CORE` — `"onecstarter.services.edt_scheme"` после
  `"onecstarter.services.edt_cli"`)

**Interfaces:**
- Consumes: домен (`BSL_PREFS`, `EDITORS_PREFS`, `THEME_PREFS`, `RGB`, `Scheme`, `ThemeChoice`,
  `complete`, `parse_csi`, `parse_idea_xml`, `parse_idea_jar`, `parse_tmtheme`, `prefs_removals`,
  `prefs_updates`, `render_prefs`, `scheme_from_workspace_prefs`, `theme_prefs_update`, `to_csi`);
  `config.atomic.atomic_write`; `services.errors.EdtError`.
- Produces: `SCHEME_KINDS: dict[str, str]` (расширение → вид), `BUSY_MESSAGE`,
  `CatalogEntry(name, path, kind)` (frozen), `SchemeCatalog(directory)` с `directory`, `exists()`,
  `entries() -> list[CatalogEntry]`, `load(entry) -> Scheme`; `save_csi(path, scheme) -> None`;
  `WorkspaceSchemes(workspace, *, is_busy=lambda: False)` с `settings_dir`,
  `current(defaults) -> Scheme`, `apply(scheme, theme) -> None`, `reset(theme) -> None`.
  Все отказы — `EdtError` с текстом для пользователя.

- [ ] **Step 1: Тесты**

`tests/unit/test_edt_scheme_service.py`:

```python
"""Каталог схем и запись в рабочую область (спека v3.2, §4, §7; инвариант 4)."""

import shutil
import zipfile
from pathlib import Path

import pytest

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    EDITORS_PREFS,
    EDT_DEFAULTS,
    THEME_IDS,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    parse_csi,
    parse_prefs,
)
from onecstarter.services.edt_scheme import (
    BUSY_MESSAGE,
    CatalogEntry,
    SchemeCatalog,
    WorkspaceSchemes,
    save_csi,
)
from onecstarter.services.errors import EdtError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edt_schemes"
TOKEN = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


def _catalog(tmp_path: Path) -> SchemeCatalog:
    root = tmp_path / "schemes"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "deep").mkdir()
    (root / "sub2").mkdir()
    shutil.copy(FIXTURES / "dark22.csi", root / "a.csi")
    shutil.copy(FIXTURES / "idea-six.xml", root / "B.XML")
    shutil.copy(FIXTURES / "four-scopes.tmTheme", root / "sub" / "c.tmTheme")
    shutil.copy(FIXTURES / "dark22.csi", root / "sub" / "deep" / "d.csi")  # второй уровень — мимо
    (root / "readme.txt").write_text("x", encoding="utf-8")
    with zipfile.ZipFile(root / "sub2" / "e.jar", "w") as archive:
        archive.writestr("colors/Six.xml", (FIXTURES / "idea-six.xml").read_text(encoding="utf-8"))
    (root / "broken.icls").write_text("<x/>", encoding="utf-8")
    return SchemeCatalog(str(root))


def test_catalog_entries_root_and_first_level_by_extension_sorted(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    assert catalog.exists() is True
    entries = catalog.entries()
    assert [(e.name, e.kind) for e in entries] == [
        ("a", "csi"),
        ("B", "idea"),
        ("broken", "idea"),
        ("c", "tmtheme"),
        ("e", "jar"),
    ]
    assert entries[3].path == tmp_path / "schemes" / "sub" / "c.tmTheme"


def test_catalog_missing_directory_is_empty(tmp_path: Path) -> None:
    catalog = SchemeCatalog(str(tmp_path / "nope"))
    assert catalog.exists() is False
    assert catalog.entries() == []


def test_catalog_loads_each_kind(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    by_name = {entry.name: entry for entry in catalog.entries()}
    csi = catalog.load(by_name["a"])
    assert csi.name == "a"
    assert csi.colors["Background"] == (43, 43, 43)
    assert csi.source == str(by_name["a"].path)
    idea = catalog.load(by_name["B"])
    assert idea.name == "Шесть атрибутов"  # имя из XML, не stem
    assert idea.colors["BSL_Keywords"] == (204, 120, 50)
    # `Others` в XML нет → `fill_missing`: тёмный фон, текст (169,183,198) − 20 по каналам
    assert idea.colors["Others"] == (149, 163, 178)
    assert catalog.load(by_name["c"]).colors["Strings"] == (206, 145, 120)
    assert catalog.load(by_name["e"]).name == "Шесть атрибутов"


def test_catalog_load_error_is_edt_error_with_reason(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    broken = next(entry for entry in catalog.entries() if entry.name == "broken")
    with pytest.raises(EdtError, match="не удалось прочитать"):
        catalog.load(broken)
    with pytest.raises(EdtError, match="не удалось прочитать"):
        catalog.load(CatalogEntry("gone", tmp_path / "gone.csi", "csi"))


def test_save_csi_writes_atomically(tmp_path: Path) -> None:
    path = tmp_path / "out" / "Моя.csi"
    scheme = Scheme("Моя", EDT_DEFAULTS)
    save_csi(path, scheme)
    assert parse_csi(path.read_text(encoding="utf-8")) == scheme.colors
    assert [p.name for p in path.parent.iterdir()] == ["Моя.csi"]
    (tmp_path / "file").write_text("x", encoding="utf-8")
    with pytest.raises(EdtError, match="Не удалось записать"):
        save_csi(tmp_path / "file" / "x.csi", scheme)


def _workspace(tmp_path: Path, busy: bool = False) -> WorkspaceSchemes:
    return WorkspaceSchemes(str(tmp_path / "ws"), is_busy=lambda: busy)


def _dark() -> Scheme:
    return Scheme("d", parse_csi((FIXTURES / "dark22.csi").read_text(encoding="utf-8")))


def test_apply_creates_settings_and_both_files_atomically(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    settings = workspace.settings_dir
    assert settings == tmp_path / "ws" / ".metadata" / ".plugins" / "org.eclipse.core.runtime" / ".settings"
    assert sorted(p.name for p in settings.iterdir()) == [BSL_PREFS, EDITORS_PREFS]
    bsl = parse_prefs((settings / BSL_PREFS).read_bytes().decode("latin-1"))
    assert bsl[f"{TOKEN}Builtin function.color"] == "255,198,109"
    assert bsl["eclipse.preferences.version"] == "1"
    editors = parse_prefs((settings / EDITORS_PREFS).read_bytes().decode("latin-1"))
    assert editors["AbstractTextEditor.Color.Background"] == "43,43,43"
    assert editors["AbstractTextEditor.Color.Background.SystemDefault"] == "false"
    assert not list(settings.glob("*.tmp"))


def test_apply_preserves_foreign_keys_and_crlf(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.settings_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "bsl-crlf.prefs", workspace.settings_dir / BSL_PREFS)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    text = (workspace.settings_dir / BSL_PREFS).read_bytes().decode("latin-1")
    assert text.startswith("=\r\n")
    assert text.endswith("\\u00EF\\u00BB\\u00BF=\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert parse_prefs(text)[f"{TOKEN}Strings.color"] == "106,135,89"


def test_apply_refuses_when_busy_before_writing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, busy=True)
    with pytest.raises(EdtError, match=BUSY_MESSAGE):
        workspace.apply(_dark(), ThemeChoice.DARK)
    assert not workspace.settings_dir.exists()
    with pytest.raises(EdtError, match=BUSY_MESSAGE):
        workspace.reset(ThemeChoice.KEEP)


def test_apply_writes_theme_only_when_chosen(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    assert not (workspace.settings_dir / THEME_PREFS).exists()
    workspace.apply(_dark(), ThemeChoice.DARK)
    theme = parse_prefs((workspace.settings_dir / THEME_PREFS).read_bytes().decode("latin-1"))
    assert theme["themeid"] == THEME_IDS[ThemeChoice.DARK]
    assert theme["eclipse.preferences.version"] == "1"


def test_current_reads_files_else_defaults(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.current(EDT_DEFAULTS).colors == Scheme("", EDT_DEFAULTS).colors
    workspace.apply(_dark(), ThemeChoice.KEEP)
    assert workspace.current(EDT_DEFAULTS).colors == _dark().colors


def test_reset_removes_our_keys_keeps_foreign_and_skips_missing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.reset(ThemeChoice.KEEP)
    assert not workspace.settings_dir.exists()
    workspace.settings_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "bsl-crlf.prefs", workspace.settings_dir / BSL_PREFS)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    workspace.reset(ThemeChoice.KEEP)
    bsl = parse_prefs((workspace.settings_dir / BSL_PREFS).read_bytes().decode("latin-1"))
    assert set(bsl) == {"", "eclipse.preferences.version", "\u00ef\u00bb\u00bf"}
    editors = parse_prefs((workspace.settings_dir / EDITORS_PREFS).read_bytes().decode("latin-1"))
    assert set(editors) == {"eclipse.preferences.version"}


def test_write_failure_is_edt_error_with_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.settings_dir.parent.mkdir(parents=True)
    workspace.settings_dir.write_text("файл вместо каталога", encoding="utf-8")
    with pytest.raises(EdtError, match="Не удалось записать"):
        workspace.apply(_dark(), ThemeChoice.KEEP)
```

Первый тест-заглушка `test_catalog_scans_root_and_first_level_by_extension_sorted` **не
оставлять**: удалить его, тело — `test_catalog_entries`. (Оставлено в тексте плана только
чтобы показать порядок чтения; в файле — один тест `test_catalog_entries`.)

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/unit/test_edt_scheme_service.py -q`
Expected: `ModuleNotFoundError: onecstarter.services.edt_scheme`.

- [ ] **Step 3: Реализация**

`src/onecstarter/services/edt_scheme.py`:

```python
"""Каталог цветовых схем и запись схемы в рабочую область EDT (спека v3.2, §4).

Каталог — настройка `edt_schemes_dir`: файлы корня и подкаталогов первого уровня по
расширениям, чтение ленивое (`load`), ошибка разбора — `EdtError` с причиной, диалог
показывает её у строки. Рабочая область — два prefs-файла в
`<workspace>\\.metadata\\.plugins\\org.eclipse.core.runtime\\.settings` (третий — тема окна);
каждый пишется атомарно (инвариант 4), чужие ключи и перевод строки сохраняются
(`render_prefs`, инвариант 3). Кодировка — latin-1 (Java properties).

Занятость области проверяет вызывающий (статус «запущен», `cli_busy`), но сервис
переспрашивает через `is_busy` перед записью — защита от гонки со сканом (§4).
`OSError` наружу не выходит — только `EdtError` с путём и причиной (§7).
"""  # noqa: RUF002

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    EDITORS_PREFS,
    RGB,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    complete,
    parse_csi,
    parse_idea_jar,
    parse_idea_xml,
    parse_tmtheme,
    prefs_removals,
    prefs_updates,
    render_prefs,
    scheme_from_workspace_prefs,
    theme_prefs_update,
    to_csi,
)
from onecstarter.services.errors import EdtError

__all__ = [
    "BUSY_MESSAGE",
    "SCHEME_KINDS",
    "CatalogEntry",
    "SchemeCatalog",
    "WorkspaceSchemes",
    "save_csi",
]

SCHEME_KINDS: dict[str, str] = {
    ".csi": "csi",
    ".xml": "idea",
    ".icls": "idea",
    ".jar": "jar",
    ".tmtheme": "tmtheme",
}
BUSY_MESSAGE = "Закройте EDT: рабочая область занята"
READ_FAILED = "не удалось прочитать: {reason}"
WRITE_FAILED = "Не удалось записать {path}: {reason}"
_SETTINGS = Path(".metadata") / ".plugins" / "org.eclipse.core.runtime" / ".settings"


def _reason(error: Exception) -> str:
    return (getattr(error, "strerror", None) or str(error)) or error.__class__.__name__


@dataclass(frozen=True)
class CatalogEntry:
    name: str  # stem файла — подпись строки в диалоге
    path: Path
    kind: str  # значение SCHEME_KINDS


class SchemeCatalog:
    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)

    @property
    def directory(self) -> Path:
        return self._directory

    def exists(self) -> bool:
        return self._directory.is_dir()

    def entries(self) -> list[CatalogEntry]:
        """Корень и подкаталоги первого уровня; расширения без учёта регистра; по имени."""
        found: list[CatalogEntry] = []

        def add(path: Path) -> None:
            kind = SCHEME_KINDS.get(path.suffix.lower())
            if kind is not None and path.is_file():
                found.append(CatalogEntry(path.stem, path, kind))

        try:
            children = list(self._directory.iterdir())
        except OSError:
            return []
        for child in children:
            if child.is_dir():
                try:
                    for nested in child.iterdir():
                        add(nested)
                except OSError:
                    continue
            else:
                add(child)
        found.sort(key=lambda entry: (entry.name.casefold(), str(entry.path).casefold()))
        return found

    def load(self, entry: CatalogEntry) -> Scheme:
        try:
            data = entry.path.read_bytes()
        except OSError as error:
            raise EdtError(READ_FAILED.format(reason=_reason(error))) from error
        try:
            if entry.kind == "csi":
                name, colors = "", parse_csi(data.decode("utf-8-sig"))
            elif entry.kind == "idea":
                name, colors = parse_idea_xml(data.decode("utf-8-sig"))
            elif entry.kind == "jar":
                name, colors = parse_idea_jar(data)
            else:
                name, colors = parse_tmtheme(data.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as error:
            raise EdtError(READ_FAILED.format(reason=error)) from error
        return complete(name or entry.name, colors, str(entry.path))


def save_csi(path: Path, scheme: Scheme) -> None:
    """Записать схему в `.csi` атомарно; каталог создаётся."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, to_csi(scheme).encode("utf-8"))
    except OSError as error:
        raise EdtError(WRITE_FAILED.format(path=path, reason=_reason(error))) from error


class WorkspaceSchemes:
    def __init__(self, workspace: str, *, is_busy: Callable[[], bool] = lambda: False) -> None:
        self._settings_dir = Path(workspace) / _SETTINGS
        self._is_busy = is_busy

    @property
    def settings_dir(self) -> Path:
        return self._settings_dir

    def current(self, defaults: Mapping[str, RGB]) -> Scheme:
        """«Текущая»: значения из файлов, иначе `defaults` (файлов может не быть — штатно)."""
        return scheme_from_workspace_prefs(
            self._read(BSL_PREFS), self._read(EDITORS_PREFS), defaults
        )

    def apply(self, scheme: Scheme, theme: ThemeChoice) -> None:
        """Записать 22 цвета (и тему, если выбрана). Отказ при занятой области — до записи."""
        self._guard()
        updates = prefs_updates(scheme)
        for name in (BSL_PREFS, EDITORS_PREFS):
            self._write(name, render_prefs(self._read(name), updates[name]))
        self._write_theme(theme)

    def reset(self, theme: ThemeChoice) -> None:
        """«По умолчанию EDT»: снять наши ключи; файла нет — не создавать."""
        self._guard()
        removals = prefs_removals()
        for name in (BSL_PREFS, EDITORS_PREFS):
            existing = self._read(name)
            if existing:
                self._write(name, render_prefs(existing, {}, removals[name]))
        self._write_theme(theme)

    def _write_theme(self, theme: ThemeChoice) -> None:
        update = theme_prefs_update(theme)
        if update is not None:
            self._write(THEME_PREFS, render_prefs(self._read(THEME_PREFS), update))

    def _guard(self) -> None:
        if self._is_busy():
            raise EdtError(BUSY_MESSAGE)

    def _read(self, name: str) -> str:
        path = self._settings_dir / name
        try:
            return path.read_bytes().decode("latin-1")
        except FileNotFoundError:
            return ""
        except OSError as error:
            raise EdtError(f"Не удалось прочитать {path}: {_reason(error)}") from error

    def _write(self, name: str, text: str) -> None:
        path = self._settings_dir / name
        try:
            self._settings_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(path, text.encode("latin-1"))
        except OSError as error:
            raise EdtError(WRITE_FAILED.format(path=path, reason=_reason(error))) from error
```

Замечание к `test_write_failure_is_edt_error_with_path`: `.settings` — файл, `mkdir(exist_ok=True)`
поднимает `FileExistsError` (OSError) → `EdtError`. Если на Windows `_read` раньше упадёт
`NotADirectoryError`/`FileNotFoundError` — первое ловится как OSError и тоже даёт `EdtError`
(«Не удалось прочитать»), второе даёт `""` и доходит до записи; тест проверяет только тип и
префикс «Не удалось» — при расхождении текста ослабить `match` до `"Не удалось"`.

- [ ] **Step 4: Прогон — зелёный, статика**

Run: `uv run pytest tests/unit/test_edt_scheme_service.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 5: Мутационная проверка отказа и атомарности**

1. В `apply` перенести `self._guard()` **после** цикла записи. Run:
   `uv run pytest tests/unit/test_edt_scheme_service.py -q -k busy` — ожидается
   `FAILED test_apply_refuses_when_busy_before_writing` на `assert not workspace.settings_dir.exists()`.
   Откатить.
2. В `_write` заменить `atomic_write(path, …)` на `path.write_bytes(…)` и добавить перед этим
   `(path.with_suffix(".tmp")).write_bytes(b"")` — ожидается `FAILED test_apply_creates_settings…`
   на `assert not list(settings.glob("*.tmp"))`. Откатить.
3. В `_write` заменить `render_prefs(self._read(name), …)` в `apply` на `render_prefs("", …)` —
   ожидается `FAILED test_apply_preserves_foreign_keys_and_crlf`. Откатить.

`git diff src/onecstarter/services/edt_scheme.py` пуст после отката; три результата — дословно
в отчёт задачи (для `docs/tasks.md`).

- [ ] **Step 6: Коммит**

```bash
git add src/onecstarter/services/edt_scheme.py tests/unit/test_edt_scheme_service.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(edt): сервис цветовых схем — каталог, атомарная запись prefs, отказ при занятой области (v3.2, задача 6)"
```

---

### Task 7: Настройка «Каталог цветовых схем»

**Files:**
- Modify: `src/onecstarter/services/settings.py` (`Settings.edt_schemes_dir`, `load_settings`,
  `save_settings`)
- Modify: `src/onecstarter/ui/settings_view.py` (константа `EDT_SCHEMES_ROW`, строка в группе
  «EDT» после языка, аксессоры)
- Modify: `tests/unit/test_settings.py` (`test_save_writes_all_fields` — ожидаемый словарь;
  `test_edt_fields_round_trip`; допуск не-строки)
- Modify: `tests/ui/test_settings_view.py` (`test_edt_group_and_rows_registered`; новый тест
  сохранения через «Обзор…»)

**Interfaces:**
- Produces: `Settings.edt_schemes_dir: str = ""`; ключ JSON `"edt_schemes_dir"`;
  `SettingsView.edt_schemes_edit() -> QLineEdit`, `edt_schemes_browse_button() -> QPushButton`;
  `EDT_SCHEMES_ROW = "Каталог цветовых схем"`.

- [ ] **Step 1: Тесты настроек**

`tests/unit/test_settings.py`: в ожидаемый словарь теста записи всех полей (строка ~44,
`assert payload == {…}`) добавить `"edt_schemes_dir": ""` после `"edt_default_language": ""`;
в `test_edt_fields_round_trip` — `edt_schemes_dir=r"D:\schemes"`; в тест допуска не-строк
(строка ~414, `json.dumps({"schema": SCHEMA_VERSION, "edt_jvm_dir": 1, …})`) добавить
`"edt_schemes_dir": ["x"]` и `assert loaded.edt_schemes_dir == ""`.

`tests/ui/test_settings_view.py`: импорт `EDT_SCHEMES_ROW`; в `test_edt_group_and_rows_registered`
после строки про `EDT_LANGUAGE_ROW`:

```python
    assert view.edt_schemes_edit() in view.row_control(EDT_SCHEMES_ROW).findChildren(QLineEdit)
    assert view.edt_schemes_browse_button() in view.row_control(EDT_SCHEMES_ROW).findChildren(
        QPushButton
    )
```

и новый тест рядом с тестами «Обзор…» (по образцу `choose_directory` у серверов):

```python
def test_edt_schemes_browse_saves_directory(application: QApplication, tmp_path: Path) -> None:
    view, store = _view(application, tmp_path, choose_directory=lambda: r"D:\schemes")
    view.edt_schemes_browse_button().click()
    assert view.edt_schemes_edit().text() == r"D:\schemes"
    assert store.settings.edt_schemes_dir == r"D:\schemes"
    assert view.row_note(EDT_SCHEMES_ROW).text().startswith("Темы IntelliJ IDEA")
```

`row_note(title) -> QLabel` и `row_control(title)` — существующие аксессоры `SettingsView`
(`settings_view.py:807`, `:824`).

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/unit/test_settings.py tests/ui/test_settings_view.py -q -x`
Expected: `AssertionError`/`AttributeError` (`edt_schemes_dir`, `edt_schemes_edit`).

- [ ] **Step 3: Реализация**

`services/settings.py`: в `Settings` после `edt_default_language`:

```python
    # Спека v3.2, §6 — каталог цветовых схем EDT (темы IDEA, .tmTheme, .csi; подкаталоги на
    # один уровень). Пустая строка — не задан: диалог схемы показывает подсказку вместо
    # каталога. Не валидируется здесь — несуществующий каталог не порча файла настроек.
    edt_schemes_dir: str = ""
```

В `load_settings` — `edt_schemes_dir=_text_of(payload.get("edt_schemes_dir")),`; в `save_settings`
— `"edt_schemes_dir": settings.edt_schemes_dir,`.

`ui/settings_view.py`: константы после `EDT_LANGUAGE_ROW`:

```python
EDT_SCHEMES_ROW = "Каталог цветовых схем"
EDT_SCHEMES_NOTE = (
    "Темы IntelliJ IDEA (.xml, .icls, .jar), TextMate (.tmTheme) и файлы .csi; "
    "подкаталоги на один уровень"
)
```

В конструкторе после `self._add_row(EDT_LANGUAGE_ROW, …)`:

```python
        self._edt_schemes, self._edt_schemes_browse, schemes_row = self._path_control(
            store.settings.edt_schemes_dir, "edt_schemes_dir"
        )
        self._add_row(EDT_SCHEMES_ROW, EDT_SCHEMES_NOTE, schemes_row, wide_control=True)
```

Аксессоры после `edt_language_combo`:

```python
    def edt_schemes_edit(self) -> QLineEdit:
        return self._edt_schemes

    def edt_schemes_browse_button(self) -> QPushButton:
        return self._edt_schemes_browse
```

- [ ] **Step 4: Прогон — зелёный, статика**

Run: `uv run pytest tests/unit/test_settings.py tests/ui/test_settings_view.py tests/ui/test_settings_store.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/services/settings.py src/onecstarter/ui/settings_view.py tests/unit/test_settings.py tests/ui/test_settings_view.py
git commit -m "feat(settings): каталог цветовых схем EDT — поле с «Обзор…» в группе EDT (v3.2, задача 7)"
```

---

### Task 8: Предпросмотр — `ui/edt/scheme_preview.py`

**Files:**
- Create: `src/onecstarter/ui/edt/scheme_preview.py`
- Create: `tests/ui/test_scheme_preview.py`

**Interfaces:**
- Consumes: домен (`RGB`, `Scheme`, `to_hex`, `COLOR_KEYS`, `KEY_BY_NAME`).
- Produces: `Run = tuple[str, str, str]` (текст, ключ схемы или `""` = `Foreground`, пометка
  `""`/`"selection"`/`"occurrence"`/`"hyperlink"`), `PREVIEW_SAMPLE: tuple[tuple[Run, ...], ...]`,
  `CURRENT_LINE: int`, `SchemePreview(QTextEdit)` с `show_scheme(scheme)`,
  `fragments() -> list[tuple[str, str, str]]` (текст, `#rrggbb` текста, `#rrggbb` фона или `""`),
  `line_backgrounds() -> list[str]`.

- [ ] **Step 1: Тесты**

`tests/ui/test_scheme_preview.py`:

```python
"""Предпросмотр схемы: фрагмент кода 1С в цветах схемы (спека v3.2, §5)."""

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    EDT_DEFAULTS,
    KEY_BY_NAME,
    Scheme,
    to_hex,
)
from onecstarter.ui.edt.scheme_preview import CURRENT_LINE, PREVIEW_SAMPLE, SchemePreview

DARK = Scheme(
    "d",
    {
        **EDT_DEFAULTS,
        "Background": (43, 43, 43),
        "Foreground": (169, 183, 198),
        "BSL_Keywords": (204, 120, 50),
        "Strings": (106, 135, 89),
        "lineNumberColor": (96, 99, 102),
        "currentLineColor": (50, 50, 50),
        "SelectionBackground": (33, 66, 131),
        "SelectionForeground": (255, 255, 255),
        "occurrenceIndicationColor": (52, 65, 52),
        "hyperlinkColor": (40, 123, 222),
    },
)


def _hex(name: str) -> str:
    return to_hex(DARK.colors[name]).lower()


def test_sample_uses_known_keys_covers_all_tokens_and_marks() -> None:
    keys = {key for line in PREVIEW_SAMPLE for _text, key, _mark in line if key}
    assert keys <= set(KEY_BY_NAME)
    tokens = {key.name for key in COLOR_KEYS if key.prefs_file == BSL_PREFS}
    assert tokens <= keys, tokens - keys
    marks = {mark for line in PREVIEW_SAMPLE for _text, _key, mark in line}
    assert {"selection", "occurrence", "hyperlink"} <= marks
    assert 0 <= CURRENT_LINE < len(PREVIEW_SAMPLE)


def test_render_colors_fragments_by_scheme(qtbot) -> None:  # type: ignore[no-untyped-def]
    preview = SchemePreview()
    qtbot.addWidget(preview)
    preview.show_scheme(DARK)
    fragments = preview.fragments()
    # Соседние отрезки с ОДИНАКОВЫМ форматом Qt склеивает в один фрагмент — проверяются
    # только отрезки, чьи соседи отличаются цветом (номер строки, ключевое слово, …).
    assert ("Процедура", _hex("BSL_Keywords"), "") in fragments
    assert (" 1 ", _hex("lineNumberColor"), "") in fragments
    assert ("Строка.Сумма", _hex("SelectionForeground"), _hex("SelectionBackground")) in fragments
    assert ("\t\tИтого", _hex("Foreground"), _hex("occurrenceIndicationColor")) in fragments
    assert ("\tОбновитьСтатус", _hex("hyperlinkColor"), "") in fragments
    assert ('"Итого: "', _hex("Strings"), "") in fragments
    backgrounds = preview.line_backgrounds()
    assert len(backgrounds) == len(PREVIEW_SAMPLE)
    assert backgrounds[CURRENT_LINE] == _hex("currentLineColor")
    assert backgrounds[0] == ""
    assert _hex("Background") in preview.styleSheet()
    assert _hex("Foreground") in preview.styleSheet()
    assert preview.isReadOnly()


def test_rerender_replaces_document(qtbot) -> None:  # type: ignore[no-untyped-def]
    preview = SchemePreview()
    qtbot.addWidget(preview)
    preview.show_scheme(DARK)
    assert preview.document().blockCount() == len(PREVIEW_SAMPLE)
    preview.show_scheme(Scheme("l", EDT_DEFAULTS))
    assert preview.document().blockCount() == len(PREVIEW_SAMPLE)
    keyword = to_hex(EDT_DEFAULTS["BSL_Keywords"]).lower()
    assert ("Процедура", keyword, "") in preview.fragments()
    assert ("Процедура", _hex("BSL_Keywords"), "") not in preview.fragments()
```

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/ui/test_scheme_preview.py -q`
Expected: `ModuleNotFoundError: onecstarter.ui.edt.scheme_preview`.

- [ ] **Step 3: Реализация**

`src/onecstarter/ui/edt/scheme_preview.py`:

```python
"""Предпросмотр цветовой схемы редактора EDT (спека v3.2, §5).

Фрагмент кода 1С размечен вручную: `PREVIEW_SAMPLE` — строки из отрезков
(текст, ключ схемы, пометка). Ключ `""` — обычный текст (`Foreground`); пометки:
`selection` — фрагмент под выделением, `occurrence` — вхождения идентификатора,
`hyperlink` — имя вызываемой процедуры. Номера строк — первый отрезок каждой строки
цветом `lineNumberColor`; строка `CURRENT_LINE` подсвечена `currentLineColor`.
Виджет красится цветами схемы, не темы OneCStarter (§5) — стиль по objectName.
Текст образца — свой, не из обработки заказчика (§10).
"""  # noqa: RUF002

from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QTextEdit, QWidget

from onecstarter.domain.edt_scheme import RGB, Scheme, to_hex

Run = tuple[str, str, str]

PREVIEW_SAMPLE: tuple[tuple[Run, ...], ...] = (
    (("&НаКлиенте", "BSL_Pragmas", ""),),
    (
        ("Процедура", "BSL_Keywords", ""),
        (" ПересчитатьИтоги", "", ""),
        ("(", "Brackets", ""),
        ("Документ", "", ""),
        (", ", "Operators", ""),
        ("Показывать", "", ""),
        (" = ", "Operators", ""),
        ("Ложь", "BSL_Keywords", ""),
        (")", "Brackets", ""),
        (" Экспорт", "BSL_Keywords", ""),
    ),
    (("\t// Сумма по строкам с учётом скидки", "Comment", ""),),
    (("\tИтого", "", ""), (" = ", "Operators", ""), ("0", "Numbers", ""), (";", "Operators", "")),
    (
        ("\tДля Каждого", "BSL_Keywords", ""),
        (" Строка ", "", ""),
        ("Из", "BSL_Keywords", ""),
        (" Документ.Товары ", "", ""),
        ("Цикл", "BSL_Keywords", ""),
    ),
    (
        ("\t\tИтого", "", "occurrence"),
        (" = ", "Operators", ""),
        ("Итого", "", "occurrence"),
        (" + ", "Operators", ""),
        ("Строка.Сумма", "", "selection"),
        (" * ", "Operators", ""),
        ("(", "Brackets", ""),
        ("1", "Numbers", ""),
        (" - ", "Operators", ""),
        ("Строка.Скидка", "", ""),
        (" / ", "Operators", ""),
        ("100", "Numbers", ""),
        (")", "Brackets", ""),
        (";", "Operators", ""),
    ),
    (("\tКонецЦикла", "BSL_Keywords", ""), (";", "Operators", "")),
    (("\t#Если Клиент Тогда", "Preprocessor", ""),),
    (
        ("\t\tСообщить", "Builtinfunction", ""),
        ("(", "Brackets", ""),
        ('"Итого: "', "Strings", ""),
        (" + ", "Operators", ""),
        ("Формат", "Builtinfunction", ""),
        ("(", "Brackets", ""),
        ("Итого", "", ""),
        (", ", "Operators", ""),
        ('"ЧДЦ=2"', "Strings", ""),
        ("))", "Brackets", ""),
        (";", "Operators", ""),
    ),
    (("\t#КонецЕсли", "Preprocessor", ""),),
    (
        ("\tЕсли", "BSL_Keywords", ""),
        (" Показывать ", "", ""),
        ("И", "BSL_Keywords", ""),
        (" Итого ", "", ""),
        ("> ", "Operators", ""),
        ("1000", "Numbers", ""),
        (" Тогда", "BSL_Keywords", ""),
    ),
    (("\t\tПерейти", "BSL_Keywords", ""), (" ~Проверка", "Label", ""), (";", "Operators", "")),
    (("\tКонецЕсли", "BSL_Keywords", ""), (";", "Operators", "")),
    (("\t~Проверка:", "Label", ""),),
    (
        ("\tОбновитьСтатус", "", "hyperlink"),
        ("(", "Brackets", ""),
        ("Документ", "", ""),
        (")", "Brackets", ""),
        (";", "Operators", ""),
    ),
    (("КонецПроцедуры", "BSL_Keywords", ""),),
)
CURRENT_LINE = 8  # строка с «Сообщить(…)» — подсветка «текущая строка»


def _qcolor(rgb: RGB) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2])


def _format(foreground: RGB) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(_qcolor(foreground))
    return fmt


def _run_format(colors: dict[str, RGB], key: str, mark: str) -> QTextCharFormat:
    fmt = _format(colors[key or "Foreground"])
    if mark == "selection":
        fmt.setForeground(_qcolor(colors["SelectionForeground"]))
        fmt.setBackground(_qcolor(colors["SelectionBackground"]))
    elif mark == "occurrence":
        fmt.setBackground(_qcolor(colors["occurrenceIndicationColor"]))
    elif mark == "hyperlink":
        fmt.setForeground(_qcolor(colors["hyperlinkColor"]))
        fmt.setFontUnderline(True)
    return fmt


class SchemePreview(QTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SchemePreview")
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

    def show_scheme(self, scheme: Scheme) -> None:
        """Перерисовать образец цветами `scheme` (не `render`: то — `QWidget.render`)."""
        colors = scheme.colors
        background, foreground = to_hex(colors["Background"]), to_hex(colors["Foreground"])
        self.setStyleSheet(
            f"QTextEdit#SchemePreview {{ background-color: {background}; color: {foreground}; }}"
        )
        self.clear()
        cursor = QTextCursor(self.document())
        for index, runs in enumerate(PREVIEW_SAMPLE):
            block = QTextBlockFormat()
            if index == CURRENT_LINE:
                block.setBackground(_qcolor(colors["currentLineColor"]))
            if index == 0:
                cursor.setBlockFormat(block)
            else:
                cursor.insertBlock(block)
            cursor.insertText(f"{index + 1:>2} ", _format(colors["lineNumberColor"]))
            for text, key, mark in runs:
                cursor.insertText(text, _run_format(colors, key, mark))

    # --- доступ для тестов ---

    def fragments(self) -> list[tuple[str, str, str]]:
        """(текст, цвет текста, фон) каждого фрагмента документа; фон `""`, если не задан."""
        result: list[tuple[str, str, str]] = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fmt = fragment.charFormat()
                background = (
                    fmt.background().color().name()
                    if fmt.hasProperty(QTextCharFormat.Property.BackgroundBrush)
                    else ""
                )
                result.append((fragment.text(), fmt.foreground().color().name(), background))
                iterator += 1
            block = block.next()
        return result

    def line_backgrounds(self) -> list[str]:
        result: list[str] = []
        block = self.document().begin()
        while block.isValid():
            fmt = block.blockFormat()
            result.append(
                fmt.background().color().name()
                if fmt.hasProperty(QTextCharFormat.Property.BackgroundBrush)
                else ""
            )
            block = block.next()
        return result
```

Проверено 18.09.2026 на PySide6 в offscreen: `block.begin()` + `iterator += 1` +
`fragment.charFormat()` дают текст, `#rrggbb` в нижнем регистре и фон только при заданном
`BackgroundBrush`. `QTextEdit.clear()` сбрасывает документ; `QTextBlockFormat` у первого
блока — через `setBlockFormat`, дальше — `insertBlock(fmt)`.

- [ ] **Step 4: Прогон — зелёный, статика**

Run: `uv run pytest tests/ui/test_scheme_preview.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/ui/edt/scheme_preview.py tests/ui/test_scheme_preview.py
git commit -m "feat(edt): предпросмотр цветовой схемы — размеченный фрагмент кода 1С (v3.2, задача 8)"
```

---

### Task 9: Диалог «Цветовая схема — <запись>»

**Files:**
- Create: `src/onecstarter/ui/edt/scheme_dialog.py`
- Create: `tests/ui/test_scheme_dialog.py`

**Interfaces:**
- Consumes: домен (`COLOR_KEYS`, `CURRENT_NAME`, `DEFAULT_NAME`, `EDT_DEFAULTS`, `RGB`, `THEME_IDS`,
  `Scheme`, `ThemeChoice`, `from_hex`, `invert`, `to_hex`); сервис (`BUSY_MESSAGE`,
  `CatalogEntry`, `SchemeCatalog`, `WorkspaceSchemes`, `save_csi`); `EdtError`;
  `SchemePreview`; `SearchField`; `russian_button_box`; `Palette`.
- Produces: `SchemeDialog(project_name, workspace, catalog, *, palette, is_busy, show_info,
  show_error, choose_save=browse_for_csi, choose_color=pick_color, parent=None)`; константы
  `TITLE`, `HINT_NO_DIR`, `HINT_MISSING_DIR`, `APPLIED_MESSAGE`, `BUTTON_INVERT`, `BUTTON_SAVE`,
  `BUTTON_APPLY`, `THEME_LABEL`, `THEME_TITLES`, `COLUMN_TITLES`, `SEARCH_HINT`; аксессоры
  `sources() -> QListWidget`, `table() -> QTableWidget`, `preview() -> SchemePreview`,
  `hint_label() -> QLabel`, `search() -> SearchField`, `apply_button()`, `invert_button()`,
  `save_button()`, `theme_combo() -> QComboBox`, `scheme() -> Scheme`, `set_color(name, rgb)`;
  функции `browse_for_csi(initial) -> str`, `pick_color(current) -> RGB | None`,
  `swatch_icon(rgb, border) -> QIcon`.

- [ ] **Step 1: Тесты**

`tests/ui/test_scheme_dialog.py`:

```python
"""Диалог цветовой схемы (спека v3.2, §5, §7)."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QListWidget

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    CURRENT_NAME,
    DEFAULT_NAME,
    EDT_DEFAULTS,
    RGB,
    THEME_IDS,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    parse_csi,
    parse_prefs,
    to_hex,
)
from onecstarter.services.edt_scheme import BUSY_MESSAGE, SchemeCatalog, WorkspaceSchemes
from onecstarter.ui.edt.scheme_dialog import (
    APPLIED_MESSAGE,
    HINT_MISSING_DIR,
    HINT_NO_DIR,
    THEME_TITLES,
    SchemeDialog,
)
from onecstarter.ui.theme import DARK

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edt_schemes"
BACKGROUND_ROW = 11  # индекс `Background` в COLOR_KEYS: 11 токенов, затем редактор
TOKEN = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.busy = False
        self.workspace_dir = tmp_path / "ws"
        self.catalog_dir = tmp_path / "schemes"
        self.catalog_dir.mkdir()
        shutil.copy(FIXTURES / "dark22.csi", self.catalog_dir / "Тёмная.csi")
        shutil.copy(FIXTURES / "idea-six.xml", self.catalog_dir / "Шесть.xml")
        (self.catalog_dir / "bad.icls").write_text("<x/>", encoding="utf-8")

    def workspace(self) -> WorkspaceSchemes:
        return WorkspaceSchemes(str(self.workspace_dir), is_busy=lambda: self.busy)

    def dialog(
        self,
        catalog: SchemeCatalog | None | str = "auto",
        choose_save: Callable[[str], str] = lambda initial: "",
        choose_color: Callable[[RGB], RGB | None] = lambda rgb: None,
    ) -> SchemeDialog:
        if catalog == "auto":
            catalog = SchemeCatalog(str(self.catalog_dir))
        return SchemeDialog(
            "Запись А",  # noqa: RUF001
            self.workspace(),
            catalog,  # type: ignore[arg-type]
            palette=DARK,
            is_busy=lambda: self.busy,
            show_info=self.infos.append,
            show_error=self.errors.append,
            choose_save=choose_save,
            choose_color=choose_color,
        )


@pytest.fixture
def harness(tmp_path: Path, qtbot) -> Harness:  # type: ignore[no-untyped-def]
    return Harness(tmp_path)


def _rows(sources: QListWidget) -> list[str]:
    return [sources.item(i).text() for i in range(sources.count())]


def _select(dialog: SchemeDialog, text: str) -> None:
    rows = _rows(dialog.sources())
    dialog.sources().setCurrentRow(rows.index(text))


def test_sources_and_current_without_prefs_shows_defaults(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Цветовая схема — Запись А"  # noqa: RUF001
    assert _rows(dialog.sources()) == [CURRENT_NAME, DEFAULT_NAME, "bad", "Тёмная", "Шесть"]
    assert dialog.sources().currentRow() == 0
    assert dialog.table().rowCount() == 22
    assert dialog.table().item(0, 2).text() == to_hex(EDT_DEFAULTS["BSL_Keywords"])
    assert dialog.hint_label().isHidden()
    assert dialog.scheme().name == CURRENT_NAME


def test_current_reads_workspace_prefs(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dark = parse_csi((FIXTURES / "dark22.csi").read_text(encoding="utf-8"))
    harness.workspace().apply(Scheme("d", dark), ThemeChoice.KEEP)
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.table().item(BACKGROUND_ROW, 2).text() == "#2B2B2B"


def test_select_catalog_scheme_fills_table_preview_and_icon(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    assert dialog.table().item(BACKGROUND_ROW, 2).text() == "#2B2B2B"
    assert ("Процедура", "#cc7832", "") in dialog.preview().fragments()
    assert dialog.scheme().name == "Тёмная"
    assert dialog.sources().currentItem().icon().isNull() is False
    _select(dialog, "Шесть")
    assert dialog.scheme().name == "Шесть атрибутов"  # имя из XML
    assert dialog.table().item(0, 2).text() == "#CC7832"


def test_unreadable_entry_marked_and_table_unchanged(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    _select(dialog, "bad")
    item = dialog.sources().currentItem()
    assert item.toolTip().startswith("не удалось прочитать")
    assert item.icon().isNull() is False
    assert dialog.table().item(BACKGROUND_ROW, 2).text() == "#2B2B2B"
    assert dialog.scheme().name == "Тёмная"
    assert harness.errors == []


def test_no_catalog_shows_hint_and_fixed_rows(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog(catalog=None)
    qtbot.addWidget(dialog)
    assert _rows(dialog.sources()) == [CURRENT_NAME, DEFAULT_NAME]
    assert dialog.hint_label().isHidden() is False
    assert dialog.hint_label().text() == HINT_NO_DIR


def test_missing_catalog_dir_shows_path(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    missing = harness.tmp_path / "nope"
    dialog = harness.dialog(catalog=SchemeCatalog(str(missing)))
    qtbot.addWidget(dialog)
    assert _rows(dialog.sources()) == [CURRENT_NAME, DEFAULT_NAME]
    assert dialog.hint_label().text() == HINT_MISSING_DIR.format(path=missing)


def test_edit_hex_updates_scheme_swatch_and_preview_invalid_reverts(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, DEFAULT_NAME)
    dialog.table().item(0, 2).setText("#FF0000")
    assert dialog.scheme().colors["BSL_Keywords"] == (255, 0, 0)
    assert dialog.table().item(0, 1).background().color().name() == "#ff0000"
    assert ("Процедура", "#ff0000", "") in dialog.preview().fragments()
    dialog.table().item(0, 2).setText("zzz")
    assert dialog.table().item(0, 2).text() == "#FF0000"
    assert dialog.scheme().colors["BSL_Keywords"] == (255, 0, 0)


def test_swatch_click_picks_color(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    asked: list[RGB] = []

    def choose(current: RGB) -> RGB | None:
        asked.append(current)
        return (1, 2, 3)

    dialog = harness.dialog(choose_color=choose)
    qtbot.addWidget(dialog)
    dialog.table().cellClicked.emit(0, 1)
    assert asked == [EDT_DEFAULTS["BSL_Keywords"]]
    assert dialog.scheme().colors["BSL_Keywords"] == (1, 2, 3)
    assert dialog.table().item(0, 2).text() == "#010203"
    dialog.table().cellClicked.emit(0, 0)  # не образец — диалог цвета не зовётся
    assert len(asked) == 1


def test_invert_flips_colors_keeps_name(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    dialog.invert_button().click()
    assert dialog.scheme().colors["Background"] == (212, 212, 212)
    assert dialog.scheme().name == "Тёмная"
    assert dialog.table().item(BACKGROUND_ROW, 2).text() == "#D4D4D4"


def test_save_writes_csi_and_selects_new_row(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    initials: list[str] = []
    target = harness.catalog_dir / "Новая.csi"

    def choose(initial: str) -> str:
        initials.append(initial)
        return str(target)

    dialog = harness.dialog(choose_save=choose)
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    dialog.set_color("Strings", (9, 9, 9))
    dialog.save_button().click()
    assert initials == [str(harness.catalog_dir / "Тёмная.csi")]
    saved = parse_csi(target.read_text(encoding="utf-8"))
    assert saved["Strings"] == (9, 9, 9)
    assert saved["Background"] == (43, 43, 43)
    assert "Новая" in _rows(dialog.sources())
    assert dialog.sources().currentItem().text() == "Новая"
    assert dialog.scheme().name == "Новая"
    assert dialog.scheme().colors["Strings"] == (9, 9, 9)


def test_save_cancelled_does_nothing(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog(choose_save=lambda initial: "")
    qtbot.addWidget(dialog)
    dialog.save_button().click()
    assert sorted(p.name for p in harness.catalog_dir.iterdir()) == ["bad.icls", "Тёмная.csi", "Шесть.xml"]


def test_apply_writes_prefs_and_reports(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    assert dialog.apply_button().isEnabled()
    dialog.apply_button().click()
    settings = harness.workspace().settings_dir
    bsl = parse_prefs((settings / BSL_PREFS).read_bytes().decode("latin-1"))
    assert bsl[f"{TOKEN}Builtin function.color"] == "255,198,109"
    assert harness.infos == [APPLIED_MESSAGE]
    assert harness.errors == []


def test_apply_disabled_when_busy_and_refused_on_race(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    harness.busy = True
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.apply_button().isEnabled() is False
    assert dialog.apply_button().toolTip() == BUSY_MESSAGE
    harness.busy = False
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.apply_button().isEnabled()
    harness.busy = True  # гонка: EDT запустился после открытия диалога
    dialog.apply_button().click()
    assert harness.errors == [BUSY_MESSAGE]
    assert harness.infos == []
    assert not harness.workspace().settings_dir.exists()


def test_apply_default_unchanged_resets_not_writes(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, DEFAULT_NAME)
    dialog.apply_button().click()
    assert harness.infos == [APPLIED_MESSAGE]
    assert not harness.workspace().settings_dir.exists()  # снимать нечего — файлов не было
    dialog.set_color("Strings", (1, 1, 1))
    dialog.apply_button().click()
    assert (harness.workspace().settings_dir / BSL_PREFS).exists()


def test_apply_service_error_is_shown(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    settings = harness.workspace().settings_dir
    settings.parent.mkdir(parents=True)
    settings.write_text("файл вместо каталога", encoding="utf-8")
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    dialog.apply_button().click()
    assert harness.errors and harness.errors[0].startswith("Не удалось")
    assert harness.infos == []


def test_theme_combo_follows_theme_ids(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    combo = dialog.theme_combo()
    expected = [THEME_TITLES[ThemeChoice.KEEP]] + [
        THEME_TITLES[choice] for choice in (ThemeChoice.DARK, ThemeChoice.LIGHT) if choice in THEME_IDS
    ]
    assert [combo.itemText(i) for i in range(combo.count())] == expected
    assert combo.isHidden() == (len(expected) == 1)
    if ThemeChoice.DARK in THEME_IDS:
        _select(dialog, "Тёмная")
        combo.setCurrentIndex(expected.index(THEME_TITLES[ThemeChoice.DARK]))
        dialog.apply_button().click()
        theme = parse_prefs(
            (harness.workspace().settings_dir / THEME_PREFS).read_bytes().decode("latin-1")
        )
        assert theme["themeid"] == THEME_IDS[ThemeChoice.DARK]


def test_filter_hides_rows_case_insensitively(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    dialog.search().setText("ШЕСТЬ")
    sources = dialog.sources()
    visible = [sources.item(i).text() for i in range(sources.count()) if not sources.item(i).isHidden()]
    assert visible == ["Шесть"]
    dialog.search().setText("")
    assert all(not sources.item(i).isHidden() for i in range(sources.count()))
```

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/ui/test_scheme_dialog.py -q`
Expected: `ModuleNotFoundError: onecstarter.ui.edt.scheme_dialog`.

- [ ] **Step 3: Реализация**

`src/onecstarter/ui/edt/scheme_dialog.py`:

```python
"""Диалог «Цветовая схема — <запись>» (спека v3.2, §5): источники, предпросмотр,
таблица 22 цветов, инверсия, сохранение в `.csi`, тема окна, «Применить».

Правки цветов живут в диалоге и не трогают файлы до «Применить»; запись ничего не
запоминает — истина в рабочей области (§1). Занятость области проверяется дважды:
кнопка при открытии (подсказка) и сервис при записи (гонка со сканом, §4). Ошибка
чтения источника помечает строку списка и не трогает таблицу (§7). «По умолчанию EDT»
без правок — `WorkspaceSchemes.reset` (снять наши ключи), с правками — обычная запись.
Палитра диалога — из темы OneCStarter (общий stylesheet), предпросмотр — цветами схемы.
"""  # noqa: RUF002

import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt_scheme import (
    COLOR_KEYS,
    CURRENT_NAME,
    DEFAULT_NAME,
    EDT_DEFAULTS,
    RGB,
    THEME_IDS,
    Scheme,
    ThemeChoice,
    from_hex,
    invert,
    to_hex,
)
from onecstarter.services.edt_scheme import (
    BUSY_MESSAGE,
    CatalogEntry,
    SchemeCatalog,
    WorkspaceSchemes,
    save_csi,
)
from onecstarter.services.errors import EdtError
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.edt.scheme_preview import SchemePreview
from onecstarter.ui.search_field import SearchField
from onecstarter.ui.theme import Palette

TITLE = "Цветовая схема — {name}"
HINT_NO_DIR = "Каталог схем не задан — Настройки → EDT"
HINT_MISSING_DIR = "Каталог схем не найден: {path}"
APPLIED_MESSAGE = "Схема применена. Изменения видны после запуска EDT"
BUTTON_INVERT = "Инвертировать"
BUTTON_SAVE = "Сохранить в файл…"
BUTTON_APPLY = "Применить"
THEME_LABEL = "Тема окна:"
THEME_TITLES: dict[ThemeChoice, str] = {
    ThemeChoice.KEEP: "не трогать",
    ThemeChoice.DARK: "тёмная",
    ThemeChoice.LIGHT: "светлая",
}
COLUMN_TITLES = ("Цвет", "Образец", "Код")
SEARCH_HINT = "Поиск: имя схемы"
KIND_CURRENT = "current"
KIND_DEFAULT = "default"
KIND_CATALOG = "catalog"
_ICON = 12
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PROBLEM_FALLBACK: RGB = (229, 115, 115)


def browse_for_csi(initial: str) -> str:
    """Диалог сохранения `.csi`; пустая строка — отмена."""
    return QFileDialog.getSaveFileName(None, "Сохранить схему", initial, "Цветовая схема (*.csi)")[0]


def pick_color(current: RGB) -> RGB | None:
    color = QColorDialog.getColor(QColor(current[0], current[1], current[2]), None, "Цвет")
    return (color.red(), color.green(), color.blue()) if color.isValid() else None


def swatch_icon(rgb: RGB, border: str) -> QIcon:
    """Кружок цвета `rgb` с обводкой `border` (hex палитры) — значок строки источника."""
    pixmap = QPixmap(_ICON, _ICON)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(rgb[0], rgb[1], rgb[2]))
    painter.setPen(QColor(border))
    painter.drawEllipse(1, 1, _ICON - 2, _ICON - 2)
    painter.end()
    return QIcon(pixmap)


class SchemeDialog(QDialog):
    def __init__(
        self,
        project_name: str,
        workspace: WorkspaceSchemes,
        catalog: SchemeCatalog | None,
        *,
        palette: Palette,
        is_busy: Callable[[], bool],
        show_info: Callable[[str], None],
        show_error: Callable[[str], None],
        choose_save: Callable[[str], str] = browse_for_csi,
        choose_color: Callable[[RGB], RGB | None] = pick_color,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE.format(name=project_name))
        self._workspace = workspace
        self._catalog = catalog
        self._palette = palette
        self._is_busy = is_busy
        self._show_info = show_info
        self._show_error = show_error
        self._choose_save = choose_save
        self._choose_color = choose_color
        self._scheme = Scheme(DEFAULT_NAME, EDT_DEFAULTS)
        self._kind = KIND_DEFAULT
        self._rows: list[tuple[str, CatalogEntry | None]] = []
        self._filling = False

        self._search = SearchField(SEARCH_HINT, palette)
        self._search.textChanged.connect(self._filter)
        self._sources = QListWidget()
        self._sources.setObjectName("SchemeSources")
        self._sources.currentRowChanged.connect(self._on_source_changed)
        self._hint = QLabel("")
        self._hint.setObjectName("SchemeHint")
        self._hint.setWordWrap(True)
        self._hint.hide()

        self._preview = SchemePreview()
        self._table = QTableWidget(len(COLOR_KEYS), len(COLUMN_TITLES))
        self._table.setObjectName("SchemeTable")
        self._table.setHorizontalHeaderLabels(list(COLUMN_TITLES))
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 48)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellClicked.connect(self._on_cell_clicked)

        self._invert = QPushButton(BUTTON_INVERT)
        self._invert.clicked.connect(self._on_invert)
        self._save = QPushButton(BUTTON_SAVE)
        self._save.clicked.connect(self._on_save)
        self._theme_label = QLabel(THEME_LABEL)
        self._theme = QComboBox()
        for choice in ThemeChoice:
            if choice is ThemeChoice.KEEP or choice in THEME_IDS:
                self._theme.addItem(THEME_TITLES[choice], choice.value)
        theme_visible = self._theme.count() > 1
        self._theme_label.setVisible(theme_visible)
        self._theme.setVisible(theme_visible)
        self._apply = QPushButton(BUTTON_APPLY)
        self._apply.clicked.connect(self._on_apply)
        self._buttons = russian_button_box(ButtonKind.CLOSE)
        self._buttons.rejected.connect(self.reject)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._search)
        left_layout.addWidget(self._sources, 1)
        left_layout.addWidget(self._hint)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._preview, 2)
        right_layout.addWidget(self._table, 3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        bottom = QHBoxLayout()
        bottom.addWidget(self._invert)
        bottom.addWidget(self._save)
        bottom.addSpacing(12)
        bottom.addWidget(self._theme_label)
        bottom.addWidget(self._theme)
        bottom.addStretch(1)
        bottom.addWidget(self._apply)
        bottom.addWidget(self._buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)
        self.resize(960, 640)

        self._reload_sources(select=None)
        self._refresh_apply()

    # --- источники ---

    def _reload_sources(self, select: Path | None) -> None:
        self._sources.blockSignals(True)
        self._sources.clear()
        self._rows = [(KIND_CURRENT, None), (KIND_DEFAULT, None)]
        self._sources.addItem(QListWidgetItem(CURRENT_NAME))
        self._sources.addItem(QListWidgetItem(DEFAULT_NAME))
        hint = ""
        if self._catalog is None:
            hint = HINT_NO_DIR
        elif not self._catalog.exists():
            hint = HINT_MISSING_DIR.format(path=self._catalog.directory)
        else:
            for entry in self._catalog.entries():
                self._rows.append((KIND_CATALOG, entry))
                item = QListWidgetItem(entry.name)
                item.setToolTip(str(entry.path))
                self._sources.addItem(item)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))
        self._sources.blockSignals(False)
        row = 0
        if select is not None:
            row = next(
                (i for i, (_kind, entry) in enumerate(self._rows) if entry and entry.path == select),
                0,
            )
        self._sources.setCurrentRow(row)  # currentRowChanged → _on_source_changed
        self._filter(self._search.text())

    def _on_source_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._rows):
            return
        kind, entry = self._rows[row]
        item = self._sources.item(row)
        try:
            if kind == KIND_CURRENT:
                scheme = self._workspace.current(EDT_DEFAULTS)
            elif kind == KIND_DEFAULT:
                scheme = Scheme(DEFAULT_NAME, EDT_DEFAULTS)
            else:
                assert self._catalog is not None and entry is not None  # инвариант _rows
                scheme = self._catalog.load(entry)
        except EdtError as error:
            problem = from_hex(self._palette.problem) or _PROBLEM_FALLBACK
            item.setIcon(swatch_icon(problem, self._palette.problem))
            item.setToolTip(str(error))
            return
        self._kind = kind
        item.setIcon(swatch_icon(scheme.colors["Background"], self._palette.border))
        self._show_scheme(scheme)

    def _filter(self, text: str) -> None:
        needle = text.casefold()
        for index in range(self._sources.count()):
            item = self._sources.item(index)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    # --- таблица и предпросмотр ---

    def _show_scheme(self, scheme: Scheme) -> None:
        self._scheme = scheme
        self._fill_table()
        self._preview.show_scheme(scheme)

    def _fill_table(self) -> None:
        self._filling = True
        fixed = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        for row, key in enumerate(COLOR_KEYS):
            rgb = self._scheme.colors[key.name]
            title = QTableWidgetItem(key.title)
            title.setFlags(fixed)
            swatch = QTableWidgetItem("")
            swatch.setFlags(fixed)
            swatch.setBackground(QBrush(QColor(rgb[0], rgb[1], rgb[2])))
            self._table.setItem(row, 0, title)
            self._table.setItem(row, 1, swatch)
            self._table.setItem(row, 2, QTableWidgetItem(to_hex(rgb)))
        self._filling = False

    def set_color(self, name: str, rgb: RGB) -> None:
        colors = dict(self._scheme.colors)
        colors[name] = rgb
        self._scheme = Scheme(self._scheme.name, colors, self._scheme.source)
        row = next(i for i, key in enumerate(COLOR_KEYS) if key.name == name)
        self._filling = True
        self._table.item(row, 1).setBackground(QBrush(QColor(rgb[0], rgb[1], rgb[2])))
        self._table.item(row, 2).setText(to_hex(rgb))
        self._filling = False
        self._preview.show_scheme(self._scheme)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 2:
            return
        key = COLOR_KEYS[item.row()]
        rgb = from_hex(item.text())
        if rgb is None:
            self._filling = True
            item.setText(to_hex(self._scheme.colors[key.name]))
            self._filling = False
            return
        self.set_color(key.name, rgb)

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column != 1:
            return
        key = COLOR_KEYS[row]
        chosen = self._choose_color(self._scheme.colors[key.name])
        if chosen is not None:
            self.set_color(key.name, chosen)

    def _on_invert(self) -> None:
        self._show_scheme(invert(self._scheme))

    # --- сохранение и применение ---

    def _on_save(self) -> None:
        directory = (
            self._catalog.directory
            if self._catalog is not None and self._catalog.exists()
            else Path()
        )
        name = _UNSAFE.sub("_", self._scheme.name).strip() or "scheme"
        chosen = self._choose_save(str(directory / f"{name}.csi"))
        if not chosen:
            return
        path = Path(chosen)
        try:
            save_csi(path, Scheme(path.stem, self._scheme.colors, str(path)))
        except EdtError as error:
            self._show_error(str(error))
            return
        self._reload_sources(select=path)

    def _on_apply(self) -> None:
        if self._is_busy():
            self._show_error(BUSY_MESSAGE)
            self._refresh_apply()
            return
        theme = ThemeChoice(self._theme.currentData())
        try:
            if self._kind == KIND_DEFAULT and self._scheme.colors == EDT_DEFAULTS:
                self._workspace.reset(theme)
            else:
                self._workspace.apply(self._scheme, theme)
        except EdtError as error:
            self._show_error(str(error))
            return
        self._show_info(APPLIED_MESSAGE)

    def _refresh_apply(self) -> None:
        busy = self._is_busy()
        self._apply.setEnabled(not busy)
        self._apply.setToolTip(BUSY_MESSAGE if busy else "")

    # --- доступ ---

    def sources(self) -> QListWidget:
        return self._sources

    def table(self) -> QTableWidget:
        return self._table

    def preview(self) -> SchemePreview:
        return self._preview

    def hint_label(self) -> QLabel:
        return self._hint

    def search(self) -> SearchField:
        return self._search

    def apply_button(self) -> QPushButton:
        return self._apply

    def invert_button(self) -> QPushButton:
        return self._invert

    def save_button(self) -> QPushButton:
        return self._save

    def theme_combo(self) -> QComboBox:
        return self._theme

    def scheme(self) -> Scheme:
        return self._scheme
```

Замечания исполнителю:
- `QTableWidget.setItem` эмитит `itemChanged` — отсюда флаг `_filling`; без него заполнение
  таблицы зациклится через `_on_item_changed` → `set_color`.
- `assert` в `_on_source_changed` — сужение типов для mypy (`S101` в ruff проекта не включён,
  `noqa` не ставить — `RUF100`).
- `self._scheme.colors == EDT_DEFAULTS` — сравнение словарей без учёта порядка; `Scheme`
  нормализует ключи к порядку `COLOR_KEYS`, `EDT_DEFAULTS` и так в нём.
- Если Э9 (Task 5) выбрал вариант «предупреждение при тёмной теме» — добавить в `_on_apply`
  перед записью: при `theme is ThemeChoice.DARK` `self._show_info(<текст из спеки §5>)`
  после успешной записи вместо `APPLIED_MESSAGE`; тест — в `test_theme_combo_follows_theme_ids`.

- [ ] **Step 4: Прогон — зелёный, статика**

Run: `uv run pytest tests/ui/test_scheme_dialog.py tests/ui/test_scheme_preview.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/ui/edt/scheme_dialog.py tests/ui/test_scheme_dialog.py
git commit -m "feat(edt): диалог «Цветовая схема» — источники, таблица 22 цветов, инверсия, .csi, применение (v3.2, задача 9)"
```

---

### Task 10: Пункт меню «Цветовая схема…» и проводка в приложении

**Files:**
- Modify: `src/onecstarter/ui/edt/view.py` (импорты; `MENU_SCHEME`; параметр `schemes_dir`;
  пункт в `_fill_project_menu`; метод `color_scheme`)
- Modify: `src/onecstarter/ui/app.py` (`EdtView(…, schemes_dir=lambda: store.settings.edt_schemes_dir, …)`)
- Modify: `tests/ui/test_edt_view.py` (`Harness.view` — параметр `schemes_dir`; импорт
  `MENU_SCHEME`, `SchemeDialog`; три теста)

**Interfaces:**
- Consumes: `SchemeDialog`, `SchemeCatalog`, `WorkspaceSchemes`; `EdtWorkspace.running_pid`,
  `cli_busy`, `project`.
- Produces: `MENU_SCHEME = "Цветовая схема…"`; `EdtView(…, schemes_dir: Callable[[], str] = lambda: "")`;
  `EdtView.color_scheme(project_id) -> None`.

- [ ] **Step 1: Тесты**

В `tests/ui/test_edt_view.py`: импорт `MENU_SCHEME` в список из `onecstarter.ui.edt.view`;
`from onecstarter.ui.edt.scheme_dialog import SchemeDialog`; `Harness.view` получает
`schemes_dir: Callable[[], str] = lambda: ""` и передаёт `schemes_dir=schemes_dir` в `EdtView`.
Тесты (после `test_project_menu_open_edt_disabled_when_not_installed`):

```python
def test_project_menu_has_color_scheme_right_after_open_edt(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    texts = [a.text() for a in view.build_menu("project", p.id).actions() if not a.isSeparator()]
    assert texts.index(MENU_SCHEME) == texts.index(MENU_OPEN_EDT) + 1
    assert _actions(view.build_menu("project", p.id))[MENU_SCHEME] is True


def test_color_scheme_opens_dialog_for_record(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    schemes = harness.tmp_path / "schemes"
    schemes.mkdir()
    (schemes / "x.csi").write_text('{"EDTColors": []}', encoding="utf-8")
    view = harness.view(schemes_dir=lambda: str(schemes))
    qtbot.addWidget(view)
    captured: list[SchemeDialog] = []

    def run_dialog(dialog: QDialog) -> bool:
        assert isinstance(dialog, SchemeDialog)
        captured.append(dialog)
        return False

    monkeypatch.setattr(view, "_run_dialog", run_dialog)
    view.color_scheme(p.id)
    assert captured[0].windowTitle() == "Цветовая схема — a"
    assert [captured[0].sources().item(i).text() for i in range(captured[0].sources().count())][2:] == ["x"]
    assert captured[0].apply_button().isEnabled()


def test_color_scheme_dialog_sees_running_workspace_as_busy(harness: Harness, qtbot, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = _add(harness, "a")
    view = harness.view()
    qtbot.addWidget(view)
    view.on_scan(EdtScan(running={p.id: 4242}, present={p.id: True}))
    captured: list[SchemeDialog] = []
    monkeypatch.setattr(view, "_run_dialog", lambda dialog: captured.append(dialog) or False)
    view.color_scheme(p.id)
    assert captured[0].apply_button().isEnabled() is False
    assert captured[0].hint_label().text() == "Каталог схем не задан — Настройки → EDT"
```

`QDialog` уже импортирован в тесте? Если нет — добавить в импорт из `PySide6.QtWidgets`.

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest tests/ui/test_edt_view.py -q -k "color_scheme"`
Expected: `ImportError: MENU_SCHEME` / `TypeError: unexpected keyword 'schemes_dir'`.

- [ ] **Step 3: Реализация**

`ui/edt/view.py`: импорты `from onecstarter.services.edt_scheme import SchemeCatalog, WorkspaceSchemes`
и `from onecstarter.ui.edt.scheme_dialog import SchemeDialog`; константа после `MENU_OPEN_EDT`:
`MENU_SCHEME = "Цветовая схема…"`. В `__init__` — параметр `schemes_dir: Callable[[], str] = lambda: ""`
(после `dialog_defaults`), `self._schemes_dir = schemes_dir`. В `_fill_project_menu` сразу после
блока `if status.cli_busy: … open_edt.setToolTip(CLI_BUSY_HINT)`:

```python
        # v3.2 §5: доступен всегда — занятость области видна внутри диалога («Применить»).
        menu.addAction(MENU_SCHEME, lambda: self.color_scheme(project.id))
```

Метод после `open_folder`:

```python
    def color_scheme(self, project_id: str) -> None:
        """«Цветовая схема…» (спека v3.2, §5): один диалог на запись, истина — в workspace."""
        project = self._workspace.project(project_id)
        directory = self._schemes_dir()
        catalog = SchemeCatalog(directory) if directory else None

        def busy() -> bool:
            return (
                self._workspace.running_pid(project_id) is not None
                or self._workspace.cli_busy(project_id)
            )

        dialog = SchemeDialog(
            project.name,
            WorkspaceSchemes(project.workspace, is_busy=busy),
            catalog,
            palette=self._palette,
            is_busy=busy,
            show_info=self._show_info,
            show_error=self._show_error,
            parent=self,
        )
        self._run_dialog(dialog)
```

`ui/app.py`, конструктор `EdtView` (строка ~1000): после `dialog_defaults=lambda: (…),` —
`schemes_dir=lambda: store.settings.edt_schemes_dir,`.

- [ ] **Step 4: Прогон — зелёный, статика**

Run: `uv run pytest tests/ui/test_edt_view.py tests/ui/test_app.py -q && uv run ruff check . && uv run mypy`
Expected: `passed`, `All checks passed!`, `Success`.

- [ ] **Step 5: Коммит**

```bash
git add src/onecstarter/ui/edt/view.py src/onecstarter/ui/app.py tests/ui/test_edt_view.py
git commit -m "feat(edt): пункт «Цветовая схема…» в меню записи, каталог схем из настроек (v3.2, задача 10)"
```

---

### Task 11: Документы, версия 3.2.0, полный прогон, сборка, smoke, выпуск

**Files:**
- Modify: `README.md` (раздел «EDT» — подраздел «### Цветовая схема» перед «**Клавиши.**»;
  раздел «Настройки» — строка «Каталог цветовых схем»; раздел «Установка» — имена артефактов
  `3.2.0`), `docs/requirements.md` (§5 — строка `v3.2` после `v3.1.1`), `docs/tasks.md`
  (T-19 — таблица коммитов, «Полный прогон и статика», «Мутационные проверки», «Гейты сборки»),
  `pyproject.toml` (`version = "3.2.0"`), `uv.lock`
- Create: `dist/RELEASE-3.2.0.md` (не в репозитории — `dist/` в `.gitignore`)
- Run: полный прогон, `build/build.ps1`

- [ ] **Step 1: README и requirements**

README, после подраздела «### Импорт проектов» (перед абзацем «**Клавиши.**»):

```markdown
### Цветовая схема

Цвета редактора кода EDT живут в настройках рабочей области (два файла в
`.metadata\.plugins\org.eclipse.core.runtime\.settings`), и в самой EDT их приходится
задавать по одному. Контекстное меню записи → «Цветовая схема…» открывает диалог:
слева — источники (текущие цвета рабочей области, умолчания EDT и схемы из каталога,
заданного в Настройках → EDT: темы IntelliJ IDEA `.xml`/`.icls`/`.jar`, TextMate
`.tmTheme`, файлы `.csi`), справа — предпросмотр фрагмента кода 1С и таблица из
22 цветов, каждый правится кликом по образцу или кодом `#RRGGBB`. «Инвертировать»
переворачивает схему, «Сохранить в файл…» пишет её в `.csi` в каталог схем.
«Применить» записывает цвета в рабочую область сразу — EDT на ней должна быть закрыта
(при выходе EDT переписывает свои настройки из памяти); изменения видны после
следующего запуска. Запись ничего не запоминает: истина — в рабочей области.
«По умолчанию EDT» без правок снимает наши ключи, и EDT возвращает свои умолчания.
Чужие ключи в файлах настроек сохраняются, запись атомарная.
```

Если Э9 подтвердил тему окна — добавить предложение: «Переключатель «Тема окна» пишет
`themeid` тёмной или светлой темы Eclipse; «не трогать» оставляет как есть.» Если Э8 показал,
что EDT удаляет неизвестные ключи, — убрать «Чужие ключи … сохраняются» (оставить «запись
атомарная»).

README, раздел «Настройки»: в перечень группы EDT добавить «каталог цветовых схем».
Раздел «Установка»: `OneCStarter-3.1.2-setup.exe` / `-portable.zip` → `3.2.0`.

`docs/requirements.md` §5, после строки `v3.1.1`:
`| v3.2 | Цветовая схема рабочей области EDT: каталог схем (темы IDEA, .tmTheme, .csi), предпросмотр, таблица 22 цветов, инверсия, сохранение в .csi, атомарная запись prefs при закрытой EDT | — |`.
В абзаце после таблицы — «v3.2 (`3.2.0`) закрыта <дата>: эксперименты Э8–Э11 вернули метки
в спеку и скил `edt-launch` ([tasks.md](tasks.md), T-19)».

- [ ] **Step 2: tasks.md — T-19 целиком**

Раздел T-19 (создан Task 5 каркасом) дополнить таблицей коммитов (из `git log --oneline master..`),
разделами:

```markdown
### Итог Э8–Э11 (<дата>)

<по протоколу: что подтверждено [Ф], что опровергнуто, что осталось [?]>

### Полный прогон и статика (<дата>)

Полный прогон: `<N> passed in <t>s` (`e:/tmp/v32-full.log`; флейк T-12 п. 15 — <проявился/нет>).
`ruff check .` — `All checks passed!`. `mypy` — `Success: no issues found in <M> source files`.

### Мутационные проверки (<дата>)

| Правило | Мутация | Упавший тест | На чём |
| --- | --- | --- | --- |
| строки без ключа сохраняются | `render_prefs` отбрасывает строки без ключа | `test_render_preserves_comments_blank_lines_and_foreign_keys`, `…roundtrip…` | `assert rendered == …` |
| перевод строки сохраняется | `newline = "\n"` | `…roundtrip…`, `…keeps_order_garbage_and_crlf` | `"\r\n" not in …` |
| отказ до записи | `_guard()` после цикла записи | `test_apply_refuses_when_busy_before_writing` | `assert not settings_dir.exists()` |
| атомарность | `write_bytes` + оставленный `.tmp` | `test_apply_creates_settings_and_both_files_atomically` | `assert not list(glob("*.tmp"))` |
| чужие ключи при записи | `render_prefs("", …)` вместо существующего текста | `test_apply_preserves_foreign_keys_and_crlf` | `startswith("=\r\n")` |

### Гейты сборки 3.2.0 (<дата>)

`build/build.ps1`: `smoke: frozen`, `smoke: keyring=ok`, `smoke: edt=<n>`, `smoke: version=3.2.0`;
артефакты `dist/OneCStarter-3.2.0-setup.exe`, `dist/OneCStarter-3.2.0-portable.zip`.
```

Строки таблицы мутаций — из отчётов Task 2 и Task 6 дословно (упавший тест и assert).

- [ ] **Step 3: Версия и полный прогон**

`pyproject.toml`: `version = "3.2.0"`. `uv sync`.

Run: `uv run pytest -q > e:/tmp/v32-full.log 2>&1; tail -3 e:/tmp/v32-full.log && uv run ruff check . && uv run mypy`
Expected: `… passed` (ожидание ≈ 2520 + ~90 новых), `All checks passed!`, `Success`.
Флейк `access violation` — повторить в `e:/tmp/v32-full-2.log`.

- [ ] **Step 4: Сборка и smoke**

Run: `powershell -ExecutionPolicy Bypass -File build/build.ps1`
Expected: `smoke: frozen`, `smoke: keyring=ok`, `smoke: edt=<n>`, `smoke: version=3.2.0`,
`dist/OneCStarter-3.2.0-setup.exe`, `dist/OneCStarter-3.2.0-portable.zip`.

- [ ] **Step 5: Заметки к выпуску**

`dist/RELEASE-3.2.0.md` (по образцу `dist/RELEASE-3.1.2.md`):

```markdown
## OneCStarter 3.2.0

### Проекты EDT

- **Цветовая схема рабочей области.** «Цветовая схема…» в меню записи: источники — текущие
  цвета области, умолчания EDT и каталог схем из настроек (темы IntelliJ IDEA `.xml`/`.icls`/`.jar`,
  TextMate `.tmTheme`, `.csi`); предпросмотр кода 1С, таблица 22 цветов с правкой по клику,
  «Инвертировать», «Сохранить в файл…» (`.csi`). «Применить» пишет два файла настроек
  рабочей области атомарно, чужие ключи сохраняются; EDT на этой области должна быть
  закрыта — изменения видны после запуска. <Тема окна — по итогу Э9.>
- Настройки → EDT: «Каталог цветовых схем».

### Файлы

- `OneCStarter-3.2.0-setup.exe` — установщик (per-user, права администратора не нужны).
- `OneCStarter-3.2.0-portable.zip` — распаковать и запустить `OneCStarter.exe`.

Настройки и списки хранятся в `%APPDATA%\OneCStarter`, при обновлении сохраняются.
```

- [ ] **Step 6: Коммит**

```bash
git add README.md docs/requirements.md docs/tasks.md pyproject.toml uv.lock
git commit -m "docs: v3.2 — T-19, README «Цветовая схема», requirements; версия 3.2.0, гейты сборки"
```

- [ ] **Step 7: Ручной smoke заказчика и выпуск (координатор)**

Заказчику: поставить `setup.exe` **поверх** 3.1.2 (урок T-21: `_internal` меняется — новые модули),
проверить «О программе» = 3.2.0; на записи EDT (закрытой) открыть «Цветовая схема…»: каталог
из настроек виден, тёмная тема IDEA из его каталога — предпросмотр тёмный, «Применить» →
сообщение; запустить EDT, открыть модуль — цвета применились; «По умолчанию EDT» → «Применить»
→ запуск — умолчания вернулись. На запущенной области — «Применить» неактивна с подсказкой.

С подтверждения: `git checkout master && git merge --no-ff feat/2026-09-16-v32 -m "v3.2 — цветовая схема рабочей области EDT (T-19)"`,
`git tag v3.2.0`, `git push origin master --tags`,
`gh release create v3.2.0 dist/OneCStarter-3.2.0-setup.exe dist/OneCStarter-3.2.0-portable.zip --title "OneCStarter 3.2.0" --notes-file dist/RELEASE-3.2.0.md --latest`.
Скриншот диалога для README (`docs/assets/screenshot-edt-scheme.png`) — по решению заказчика:
`E:\tmp\OneCStarter-demo\shoot.py` дополнить сценой `SchemeDialog` на демо-каталоге
(память `readme-screenshots`); без скриншота README остаётся текстовым.

---

## Самопроверка плана (18.09.2026)

**Покрытие спеки.** §0 — метки: Task 5 (Э8–Э11), `idea_color` и `NEW_PREFS_NEWLINE` — Task 1–2
с находкой 18.09.2026. §1 — источники (каталог, «Текущая», «По умолчанию»; без встроенного
набора и галерей): Task 6, 9; полный редактор с предпросмотром, инверсией, `.csi`: Task 8–9;
«Применить» пишет сразу при закрытой EDT: Task 6, 9; тема окна — Task 2 (`THEME_IDS`), 9;
один диалог на запись, каталог в настройках: Task 7, 10. §2 модель — Task 1. §3 парсеры и
properties — Task 2–3 (`parse_prefs`/`render_prefs`, `prefs_updates`, `to_csi`,
`theme_prefs_update`, `scheme_from_workspace_prefs`; имя IDEA из XML — `parse_idea_xml`
возвращает имя, каталог берёт stem для строки). §4 сервис — Task 6 (`SchemeCatalog`,
`WorkspaceSchemes`, `is_busy`, `EDT_DEFAULTS`, «По умолчанию» = снятие ключей). §5 диалог —
Task 8–10 (список, значок-кружок, фильтр, подсказка без каталога, предпросмотр с номерами
строк/текущей строкой/выделением/вхождениями/гиперссылкой, таблица 22×3, кнопки, тема,
сообщение после применения, палитра темы OneCStarter). §6 настройка — Task 7. §7 ошибки —
Task 6 (создание `.settings`, `EdtError` с путём, последовательная запись), Task 9 (пометка
нечитаемого источника, подсказки, отказ при гонке). §8 эксперименты — Task 4–5. §9 тесты —
Task 1–3, 6–10; фикстуры — Task 2–3 (свои файлы). §10 границы — Global Constraints.
§11 модули — все перечислены (`pyproject.toml` — Task 11; скил — Task 5).

**Отступления от первой редакции спеки (внесены в спеку 18.09.2026 вместе с планом, обоснование — Global Constraints):**
`idea_color` вместо `from_hex` для IDEA; короткое имя `Builtinfunction`; `NEW_PREFS_NEWLINE`
CRLF; «По умолчанию EDT» = `reset`; `CatalogEntry` без поля `error` — ошибка в подсказке
строки диалога (`EdtError` из `load`); `parse_idea_xml`/`parse_idea_jar`/`parse_tmtheme`
возвращают `(имя, цвета)`; `is_busy` — в конструкторе `WorkspaceSchemes`; порядок задач:
домен раньше экспериментов (обоснование — в Architecture).

**Заглушки.** Пройдено поиском по `TBD`, `TODO`, `позже`, `аналогично задаче`: нет.
Единственные значения, которых план не знает заранее, — исходы Э8–Э11; для каждого исхода
Task 5 называет конкретную константу и правку, а код Task 2/9 работает при любом из них
(`THEME_IDS` пустой или полный, `NEW_PREFS_NEWLINE` CRLF или LF).

**Типы между задачами.** `RGB`, `Scheme(name, colors, source)`, `ColorKey.name`/`title`/
`prefs_file`/`prefs_key`/`system_default`/`background` — Task 1 → 2, 3, 6, 8, 9;
`render_prefs(existing, updates, remove)` — Task 2 → 4, 6; `prefs_updates`/`prefs_removals`
— Task 2 → 6; `parse_*` `(str, dict)` — Task 3 → 6; `CatalogEntry(name, path, kind)`,
`SchemeCatalog.entries/load/exists/directory`, `WorkspaceSchemes.current/apply/reset/settings_dir`,
`save_csi` — Task 6 → 9, 10; `SchemePreview.show_scheme/fragments/line_backgrounds` — Task 8 → 9;
`SchemeDialog(project_name, workspace, catalog, *, palette, is_busy, show_info, show_error,
choose_save, choose_color, parent)` — Task 9 → 10; `Settings.edt_schemes_dir` — Task 7 → 10.
`ThemeChoice`/`THEME_IDS`/`theme_prefs_update` — Task 2 → 4, 6, 9. Совпадают.
