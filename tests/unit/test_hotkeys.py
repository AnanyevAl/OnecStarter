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
        # Только F4 с модификаторами РОВНО Alt запрещён (см. параметризацию  # noqa: RUF003
        # ниже) — эти два система не перехватывает как закрытие окна.
        ("Ctrl+Alt+F4", MOD_CONTROL | MOD_ALT, 0x73, "F4"),
        ("Alt+Shift+F4", MOD_ALT | MOD_SHIFT, 0x73, "F4"),
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
        # Заказчик 20.08.2026: Alt+F4 успешно РЕГИСТРИРУЕТСЯ RegisterHotKey
        # (в отличие от «занято» — это отказ регистрации, а не запрет разбора),  # noqa: RUF003
        # и назначив его, пользователь отбирает закрытие окон у всей Windows.  # noqa: RUF003
        # Ctrl+Alt+F4 и Alt+Shift+F4 система так не перехватывает — они валидны
        # (см. test_parses_valid_combinations).
        "Alt+F4",
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
