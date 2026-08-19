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

# Shift сам по себе модификатором не считается: Shift+буква — это ввод  # noqa: RUF003
# текста, и глобальный перехват отобрал бы его у всей системы (спека §4.1).  # noqa: RUF003
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
    **{chr(code): code for code in range(0x41, 0x5B)},  # A–Z  # noqa: RUF003
    **{chr(code): code for code in range(0x30, 0x3A)},  # 0–9  # noqa: RUF003
    **{f"F{number}": 0x6F + number for number in range(1, 13)},  # F1–F12  # noqa: RUF003
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
