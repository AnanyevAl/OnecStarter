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
    return luminance(scheme.colors["Background"]) < 127.5


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
    delta = SHIFT if luminance(background) < 128 else -SHIFT
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
