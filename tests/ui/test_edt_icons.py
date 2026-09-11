"""Значок «запущен» раздела EDT: зелёный треугольник вершиной вправо (задача 21)."""

from onecstarter.ui import theme
from onecstarter.ui.edt.icons import running_icon


def test_running_icon_is_green_triangle(qapp) -> None:  # type: ignore[no-untyped-def]
    icon = running_icon(theme.DARK)
    assert not icon.isNull()
    image = icon.pixmap(16, 16).toImage()
    assert image.pixelColor(6, 8).name() == theme.DARK.running  # внутри треугольника
    assert image.pixelColor(14, 1).alpha() == 0  # угол вне треугольника прозрачен
