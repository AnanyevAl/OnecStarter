"""Цветовая схема редактора кода EDT (спека v3.2): модель, цвета, разбор источников,
Java properties без потерь.

Чистые функции над текстом и байтами — ни ФС, ни процессов (инварианты 1–2 CLAUDE.md).
Факты: два файла prefs и 22 ключа — [Ф] 16.09.2026, пять рабочих областей заказчика;
11 идентификаторов токенов — [Д] строки констант класса `BslHighlightingConfiguration`
плагина `com._1c.g5.v8.dt.bsl.ui` (18.09.2026). Умолчания цветов — `EDT_DEFAULTS`,
метка достоверности — в комментарии к константе (Э10).
"""  # noqa: RUF002

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

RGB = tuple[int, int, int]

BSL_PREFS = "com._1c.g5.v8.dt.bsl.ui.prefs"
EDITORS_PREFS = "org.eclipse.ui.editors.prefs"
THEME_PREFS = "org.eclipse.e4.ui.css.swt.theme.prefs"
TOKEN_PREFIX = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."
EDITOR_PREFIX = "AbstractTextEditor.Color."
SYSTEM_DEFAULT_SUFFIX = ".SystemDefault"
CURRENT_NAME = "Текущая (рабочая область)"
DEFAULT_NAME = "По умолчанию EDT"
SHIFT = 20  # сдвиг канала для недостающих цветов, как у обработки заказчика [Р]  # noqa: RUF003


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
    _editor(
        "Background",
        "Фон",
        EDITOR_PREFIX + "Background",
        system_default=True,
        background=True,
    ),
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

DARK_LUMINANCE = 128  # порог яркости (0–255): ниже — тёмный фон  # noqa: RUF003


def is_dark_rgb(rgb: RGB) -> bool:
    """Тёмный ли цвет: целочисленная яркость, без плавающей точки — (128,128,128) ровно
    на пороге и тёмным не считается."""
    return 299 * rgb[0] + 587 * rgb[1] + 114 * rgb[2] < DARK_LUMINANCE * 1000


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
    3 `undefined`. Сокращение `#RGB` здесь НЕ действует: `fff` — это `000fff`."""  # noqa: RUF002
    match = _IDEA_HEX.match(text.strip())
    if match is None:
        return None
    return from_hex(match.group(1).zfill(6))


def parse_rgb(text: str) -> RGB | None:
    """`R,G,B` из prefs; не три числа или вне 0–255 — None (спека §7: ключ не задан)."""  # noqa: RUF002
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


def luminance(rgb: RGB) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


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
    на светлом — наоборот. Заданные ключи не трогаются."""  # noqa: RUF002
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
# на снятые с установки и ставит метку.  # noqa: RUF003
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

# --- Java properties без потерь --------------------------------------------------
#
# Формат [Ф] спека §0: `ключ=значение`, `eclipse.preferences.version=1`, ключи по алфавиту;
# у заказчика — CRLF и мусорные строки `=`, `ï»¿=` (ключи с пустым значением),  # noqa: RUF003
# которые EDT переживает. Минимальный разбор: разделитель только `=`, экранирование
# `\ `, `\=`, `\:`, `\\`, `\uXXXX`, `\t`/`\n`/`\r`/`\f`; продолжение строки обратным слэшем
# не поддерживается (Eclipse его не пишет). Строки без `=`, пустые и комментарии  # noqa: RUF003
# `#`/`!` сохраняются на месте. Кодировка — забота вызывающего (latin-1).

PREFS_VERSION_LINE = "eclipse.preferences.version=1"
# Перевод строки НОВОГО файла; существующий сохраняет свой. [?] до Э8: все пять файлов
# заказчика — CRLF ([Ф]); Eclipse на Windows пишет `BufferedWriter.newLine()` ([Д]).
NEW_PREFS_NEWLINE = "\r\n"
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


@dataclass(frozen=True)
class PrefsLine:
    raw: str  # строка без перевода
    key: str | None = None  # None — не пара «ключ=значение»
    key_text: str = ""  # ключ как записан (с экранированием и пробелами)  # noqa: RUF003
    value: str = ""


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


def parse_prefs_line(raw: str) -> PrefsLine:
    stripped = raw.lstrip()
    if not stripped or stripped[0] in "#!":
        return PrefsLine(raw)
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\":
            index += 2
            continue
        if char == "=":
            key_text = raw[:index]
            value = unescape_property(raw[index + 1 :].lstrip())
            return PrefsLine(raw, unescape_property(key_text).strip(), key_text, value)
        index += 1
    return PrefsLine(raw)


def _split_lines(text: str) -> list[str]:
    """Не `str.splitlines`: тот режет и по `\\x85`/`\\x1c`…, которые в latin-1 — данные."""  # noqa: RUF002
    if not text:
        return []
    lines = _LINE_BREAK.split(text)
    if lines and lines[-1] == "" and _LINE_BREAK.search(text[-2:]):
        lines.pop()
    return lines


def _newline_of(existing: str) -> str:
    if not existing:
        return NEW_PREFS_NEWLINE
    return "\r\n" if "\r\n" in existing else "\n"


def parse_prefs(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in _split_lines(text):
        line = parse_prefs_line(raw)
        if line.key is not None:
            result[line.key] = line.value
    return result


def render_prefs(
    existing: str, updates: Mapping[str, str], remove: Iterable[str] = ()
) -> str:
    """Подставить наши ключи в текст prefs без потерь (инвариант 3).

    Строки существующего файла остаются на местах: комментарии, пустые, чужие ключи,
    порядок, перевод строки, наличие завершающего перевода. Значение нашего ключа
    заменяется на месте (текст ключа — как был); ключ, которого не было, вставляется перед
    первым существующим ключом, большим по алфавиту (Eclipse хранит ключи отсортированными,
    сравнение — по снятому экранированию), иначе в конец; `remove` — ключи, строки которых
    удаляются. Пустой `existing` — новый файл: `eclipse.preferences.version=1` плюс ключи
    по алфавиту, перевод строки `NEW_PREFS_NEWLINE`. Тождество: `render_prefs(t, {}) == t`.
    """
    newline = _newline_of(existing)
    lines = [parse_prefs_line(raw) for raw in _split_lines(existing)]
    if not lines:
        lines = [parse_prefs_line(PREFS_VERSION_LINE)]
    removed = {unescape_property(key).strip() for key in remove}
    result = [line for line in lines if line.key is None or line.key not in removed]
    pending = {unescape_property(key).strip(): (key, value) for key, value in updates.items()}
    for index, line in enumerate(result):
        if line.key is not None and line.key in pending:
            _key_text, value = pending.pop(line.key)
            result[index] = PrefsLine(f"{line.key_text}={value}", line.key, line.key_text, value)
    for normalized in sorted(pending):
        key_text, value = pending[normalized]
        position = next(
            (i for i, line in enumerate(result) if line.key is not None and line.key > normalized),
            len(result),
        )
        result.insert(position, PrefsLine(f"{key_text}={value}", normalized, key_text, value))
    text = newline.join(line.raw for line in result)
    if not existing or existing.endswith(("\n", "\r")):
        text += newline
    return text


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
