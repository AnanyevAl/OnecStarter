"""Значки видов размещения: четыре различимых, перекрашиваются палитрой."""

from collections import Counter

import pytest
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication

from onecstarter.domain.connect import ConnectKind
from onecstarter.ui import theme
from onecstarter.ui.bases.icons import _colour_for, placement_icon

_KNOWN = (ConnectKind.FILE, ConnectKind.SERVER, ConnectKind.WEB)
_PALETTES = (theme.DARK, theme.LIGHT)


def _pixels(icon: QIcon) -> bytes:
    image = icon.pixmap(16, 16).toImage()
    return image.constBits().tobytes()  # type: ignore[union-attr]


def _opaque_colours(icon: QIcon) -> Counter[str]:
    """Счётчик цветов непрозрачных пикселей — то, чем значок реально нарисован.

    Сглаживание (`Antialiasing`) даёт по краям фигур соседние оттенки того же
    цвета, поэтому сравнивать нужно преобладающий цвет, а не множество:
    у края круга и у наклонных линий встречаются одиночные `#999999` рядом
    с `#9a9a9a`. Самый частый цвет — ровно тот, которым задано перо.
    """  # noqa: RUF002
    image = icon.pixmap(16, 16).toImage()
    return Counter(
        image.pixelColor(x, y).name().casefold()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )


def _dominant_colour(icon: QIcon) -> str:
    return _opaque_colours(icon).most_common(1)[0][0]


def test_every_kind_has_an_icon(qapp: QApplication) -> None:
    for kind in ConnectKind:
        assert not placement_icon(kind, theme.DARK).isNull(), kind


def test_unknown_differs_from_known_kinds(qapp: QApplication) -> None:
    """§1.3: UNKNOWN — это «не разобрали», а не «прочее»."""  # noqa: RUF002
    unknown = _pixels(placement_icon(ConnectKind.UNKNOWN, theme.DARK))
    for kind in (ConnectKind.FILE, ConnectKind.SERVER, ConnectKind.WEB):
        assert _pixels(placement_icon(kind, theme.DARK)) != unknown, kind


def test_known_kinds_differ_from_each_other(qapp: QApplication) -> None:
    drawn = {
        kind: _pixels(placement_icon(kind, theme.DARK))
        for kind in (ConnectKind.FILE, ConnectKind.SERVER, ConnectKind.WEB)
    }
    assert len(set(drawn.values())) == 3


def test_palette_changes_the_drawing(qapp: QApplication) -> None:
    """Значки создаются внутри build_model, поэтому смена темы их перерисует."""
    assert _pixels(placement_icon(ConnectKind.FILE, theme.DARK)) != _pixels(
        placement_icon(ConnectKind.FILE, theme.LIGHT)
    )


def test_unknown_uses_the_problem_colour_not_the_dimmed_text_colour() -> None:
    """Цвет UNKNOWN проверяется отдельно от формы (находка мутационной

    проверки задачи 5, шаг 10, мутация 2): сравнение сырых пикселей значка
    не ловит подмену цвета — пунктир и «?» и так отличают UNKNOWN пикселями
    от сплошных фигур остальных видов, независимо от того, каким цветом
    их залили. Требование заказчика — различие и формой, и цветом (§1.3).
    """
    assert _colour_for(ConnectKind.UNKNOWN, theme.DARK) == QColor(theme.DARK.problem)
    for kind in (ConnectKind.FILE, ConnectKind.SERVER, ConnectKind.WEB):
        assert _colour_for(kind, theme.DARK) == QColor(theme.DARK.text_dim), kind


# -- цвет на самом значке, а не только в функции (финальное ревью, I4) --------  # noqa: RUF003
#
# Тест выше зовёт `_colour_for` напрямую и не проверяет, что `placement_icon`
# пользуется её результатом: подмена `colour = _colour_for(kind, palette)`
# на `QColor(palette.text_dim)` оставляла все UI-тесты зелёными, и значок
# `UNKNOWN` терял цвет проблемы, различаясь с тремя известными только формой.  # noqa: RUF003
# Требование заказчика (спека §1.3) — различие и формой, и цветом.
#
# Проверяются пиксели готового значка в обеих палитрах: другого способа
# доказать, что нарисовано именно этим цветом, нет.


@pytest.mark.parametrize("palette", _PALETTES, ids=("dark", "light"))
def test_unknown_icon_is_painted_with_the_problem_colour(
    qapp: QApplication, palette: theme.Palette
) -> None:
    drawn = _opaque_colours(placement_icon(ConnectKind.UNKNOWN, palette))

    assert _dominant_colour(placement_icon(ConnectKind.UNKNOWN, palette)) == (
        palette.problem.casefold()
    )
    assert palette.text_dim.casefold() not in drawn


@pytest.mark.parametrize("palette", _PALETTES, ids=("dark", "light"))
@pytest.mark.parametrize("kind", _KNOWN, ids=lambda kind: kind.name.lower())
def test_known_icons_are_painted_with_the_dimmed_text_colour(
    qapp: QApplication, kind: ConnectKind, palette: theme.Palette
) -> None:
    drawn = _opaque_colours(placement_icon(kind, palette))

    assert _dominant_colour(placement_icon(kind, palette)) == palette.text_dim.casefold()
    assert palette.problem.casefold() not in drawn


def test_server_icon_is_two_horizontal_shelves(qapp: QApplication) -> None:
    """Мокап: серверная — две полки, между ними просвет; вертикальной стойки нет.

    Проверяется просвет по центральной горизонтали (y=8): у старой
    вертикальной стойки колонка x∈[5..11] на y=8 непрозрачна, у полок
    на y=8 непрозрачных пикселей нет вовсе.
    """  # noqa: RUF002
    image = placement_icon(ConnectKind.SERVER, theme.DARK).pixmap(16, 16).toImage()
    middle_row = [image.pixelColor(x, 8).alpha() for x in range(16)]
    assert all(alpha == 0 for alpha in middle_row)


def test_unknown_icon_is_round_not_square(qapp: QApplication) -> None:
    """Мокап: «не разобрано» — пунктирный круг; у квадрата углы непрозрачны."""  # noqa: RUF002
    image = placement_icon(ConnectKind.UNKNOWN, theme.DARK).pixmap(16, 16).toImage()
    corners = [(2, 2), (13, 2), (2, 13), (13, 13)]
    assert all(image.pixelColor(x, y).alpha() == 0 for x, y in corners)
