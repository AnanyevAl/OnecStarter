"""Поле поиска: крестик очистки и подсказка Ctrl+F (спека v3.1, §6)."""

from typing import Any

from PySide6.QtCore import Qt

from onecstarter.ui import theme
from onecstarter.ui.search_field import SearchField


def test_placeholder_names_the_hotkey(qtbot: Any) -> None:
    field = SearchField("Поиск: начните вводить имя базы", theme.DARK)
    qtbot.addWidget(field)
    assert field.placeholderText() == "Поиск: начните вводить имя базы (Ctrl+F)"


def test_clear_action_visible_only_with_text_and_clears(qtbot: Any) -> None:
    field = SearchField("Поиск", theme.DARK)
    qtbot.addWidget(field)
    assert field.clear_action().isVisible() is False
    field.setText("роз")
    assert field.clear_action().isVisible() is True
    field.clear_action().trigger()
    assert field.text() == ""
    assert field.clear_action().isVisible() is False


def test_clear_icon_is_drawn_in_dim_colour_of_both_palettes(qtbot: Any) -> None:
    from PySide6.QtGui import QColor

    for palette in (theme.DARK, theme.LIGHT):
        field = SearchField("Поиск", palette)
        qtbot.addWidget(field)
        image = field.clear_action().icon().pixmap(16, 16).toImage()
        assert image.pixelColor(8, 8) == QColor(palette.text_dim)  # центр креста
        assert image.pixelColor(0, 8).alpha() == 0  # край прозрачен


def test_apply_palette_redraws_icon(qtbot: Any) -> None:
    from PySide6.QtGui import QColor

    field = SearchField("Поиск", theme.DARK)
    qtbot.addWidget(field)
    field.apply_palette(theme.LIGHT)
    image = field.clear_action().icon().pixmap(16, 16).toImage()
    assert image.pixelColor(8, 8) == QColor(theme.LIGHT.text_dim)


def test_enter_and_tab_request_the_list_when_enabled(qtbot: Any) -> None:
    field = SearchField("Поиск", theme.DARK, list_navigation=True)
    qtbot.addWidget(field)
    seen: list[bool] = []
    field.list_requested.connect(lambda: seen.append(True))
    qtbot.keyClick(field, Qt.Key.Key_Return)
    qtbot.keyClick(field, Qt.Key.Key_Tab)
    assert seen == [True, True]


def test_shift_tab_is_not_captured(qtbot: Any) -> None:
    field = SearchField("Поиск", theme.DARK, list_navigation=True)
    qtbot.addWidget(field)
    seen: list[bool] = []
    field.list_requested.connect(lambda: seen.append(True))
    qtbot.keyClick(field, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert seen == []


def test_list_navigation_is_off_by_default(qtbot: Any) -> None:
    """Диалог «Цветовая схема…» тоже держит SearchField — Tab там обязан уводить фокус."""
    field = SearchField("Поиск", theme.DARK)
    qtbot.addWidget(field)
    seen: list[bool] = []
    field.list_requested.connect(lambda: seen.append(True))
    qtbot.keyClick(field, Qt.Key.Key_Return)
    qtbot.keyClick(field, Qt.Key.Key_Tab)
    assert seen == []
