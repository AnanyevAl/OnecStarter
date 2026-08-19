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
