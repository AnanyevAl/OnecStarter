"""Разбор и каноническая запись сочетания глобального хоткея."""

import pytest

from onecstarter.services.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    HotkeySpec,
    format_hotkey,
    key_name_for_vk,
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


@pytest.mark.parametrize(
    ("vk", "name"),
    [
        (0x42, "B"),
        (0x41, "A"),
        (0x5A, "Z"),
        (0x30, "0"),
        (0x39, "9"),
        (0x70, "F1"),
        (0x74, "F5"),
        (0x7B, "F12"),
    ],
)
def test_key_name_for_vk_names_supported_keys(vk: int, name: str) -> None:
    """Код от драйвера → имя клавиши (спека §4.1, захват без зависимости от раскладки)."""
    assert key_name_for_vk(vk) == name


@pytest.mark.parametrize(
    "vk",
    [
        0,      # событие синтезировано, драйвер кода не давал — запасной путь UI
        0x10,   # Shift: модификатор, самостоятельным сочетанием не бывает
        0x2E,   # Delete: выключает хоткей, в набор сочетаний не входит
        0x6F,   # на единицу ниже F1
        0x7C,   # F13 — выше поддержанного F12
        0xBC,   # запятая: набор намеренно узкий (докстринг модуля)
        -1,
    ],
)
def test_key_name_for_vk_rejects_unsupported(vk: int) -> None:
    assert key_name_for_vk(vk) is None


def test_key_name_for_vk_agrees_with_parse_hotkey() -> None:
    """Две стороны одной таблицы не расходятся.

    Разъехавшись, они дали бы худший из возможных исходов: захват принимает
    клавишу, которую разбор той же строки потом отвергает, — сочетание
    «назначено» на экране и не работает в системе.
    """
    for vk in (*range(0x30, 0x3A), *range(0x41, 0x5B), *range(0x70, 0x7C)):
        name = key_name_for_vk(vk)
        assert name is not None
        spec = parse_hotkey(f"Ctrl+Alt+{name}")
        assert spec is not None
        assert spec.vk == vk
