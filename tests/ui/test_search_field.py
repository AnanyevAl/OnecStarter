"""Поле поиска: крестик очистки и подсказка Ctrl+F (спека v3.1, §6)."""

from typing import Any

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
