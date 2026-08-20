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


VK_B = 0x42
SCAN_B = 48
# Кириллическая «Б» приходит в `key()` той же клавишей, что латинская B,
# когда активна русская раскладка: `key()` раскладко-зависим, драйверный
# `nativeVirtualKey` — нет (спека §4.1, находка блока В протокола 20.08.2026).  # noqa: RUF003
KEY_CYRILLIC_BE = 0x411


def _press(
    key: Qt.Key | int,
    modifiers: Qt.KeyboardModifier,
    *,
    native_vk: int = 0,
    native_scan: int = 0,
) -> QKeyEvent:
    """Нажатие клавиши. `native_vk=0` — событие без кода от драйвера.

    Ноль здесь не для краткости: короткий конструктор `QKeyEvent` именно его
    и ставит, а значит `native_vk=0` — честная модель синтезированного
    события, на котором обязан работать запасной путь `spec_from_event`.
    """  # noqa: RUF002
    return QKeyEvent(
        QKeyEvent.Type.KeyPress, key, modifiers, native_scan, native_vk, 0
    )


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


def test_cyrillic_layout_captures_the_latin_key_of_the_same_button(
    application: QApplication,
) -> None:
    """Русская раскладка не мешает назначить сочетание (спека §4.1).

    Прогон блока В 20.08.2026: заказчик, сменив сочетание, не смог вернуть
    `Ctrl+Alt+B` — при русской раскладке поле молча не реагировало. Промахом
    это не было: то же сочетание в системе срабатывает при любой раскладке
    (шаг Б3), потому что `RegisterHotKey` подписан на драйверный код `0x42`.
    Захват обязан читать тот же код, а не раскладко-зависимый `key()`.
    """  # noqa: RUF002
    event = _press(
        KEY_CYRILLIC_BE,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=VK_B,
        native_scan=SCAN_B,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.key == "B"
    assert spec.vk == VK_B


def test_cyrillic_key_without_latin_counterpart_is_still_rejected(
    application: QApplication,
) -> None:
    """«Ж» на клавише `;` — настоящий промах, и трактовка для него не меняется.

    Драйверный код такой клавиши (`VK_OEM_1`) в поддержанный набор не входит:
    ни буква, ни цифра, ни F-клавиша. Отказ обязан остаться отказом — иначе
    захват примет то, что `parse_hotkey` потом отвергнет.
    """
    event = _press(
        0x416,  # «Ж»
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=0xBA,  # VK_OEM_1, клавиша `;`
        native_scan=39,
    )
    assert spec_from_event(event) is None


def test_synthesized_event_without_native_code_still_captures(
    application: QApplication,
) -> None:
    """Запасной путь: `nativeVirtualKey == 0` — код от драйвера не пришёл.

    Так выглядят события, собранные программно (короткий конструктор
    `QKeyEvent` ставит ноль). Терять на них работающий захват нельзя:
    иначе правка ради раскладки сломала бы всё, что синтезирует нажатия.
    """
    event = _press(
        Qt.Key.Key_B,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.key == "B"


def test_native_code_wins_over_the_layout_dependent_key(
    application: QApplication,
) -> None:
    """При расхождении двух источников верить драйверу, а не раскладке.

    Сторож приоритета: если бы `key()` проверялся первым, кириллический код
    дал бы `None` ещё до того, как драйверный код был бы прочитан вовсе.
    """  # noqa: RUF002
    latin = _press(
        Qt.Key.Key_G,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=VK_B,
        native_scan=SCAN_B,
    )
    spec = spec_from_event(latin)
    assert spec is not None
    assert spec.key == "B"


def test_widget_accepts_cyrillic_layout_press(application: QApplication) -> None:
    """Поле целиком, не только разбор события: значение встаёт и уходит наружу."""
    edit = HotkeyEdit()
    edit.set_combination("Ctrl+Alt+G")
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(
        _press(
            KEY_CYRILLIC_BE,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
            native_vk=VK_B,
            native_scan=SCAN_B,
        )
    )

    assert seen == ["Ctrl+Alt+B"]
    assert edit.text() == "Ctrl+Alt+B"
