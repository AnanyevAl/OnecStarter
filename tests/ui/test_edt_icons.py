"""Значки раздела EDT: зелёный ▶ — запущен (задача 21), круг акцента — команда CLI (план 2)."""

from onecstarter.ui import theme
from onecstarter.ui.edt.icons import cli_busy_icon, running_icon


def test_running_icon_is_green_triangle(qapp) -> None:  # type: ignore[no-untyped-def]
    icon = running_icon(theme.DARK)
    assert not icon.isNull()
    image = icon.pixmap(16, 16).toImage()
    assert image.pixelColor(6, 8).name() == theme.DARK.running  # внутри треугольника
    assert image.pixelColor(14, 1).alpha() == 0  # угол вне треугольника прозрачен


def test_cli_busy_icon_is_accent_circle(qapp) -> None:  # type: ignore[no-untyped-def]
    icon = cli_busy_icon(theme.DARK)
    assert not icon.isNull()
    image = icon.pixmap(16, 16).toImage()
    assert image.pixelColor(8, 8).name() == theme.DARK.accent  # центр круга
    assert image.pixelColor(0, 0).alpha() == 0  # угол вне круга прозрачен
