"""Значки рельсы: покой приглушённый, активный — акцентный, тема перерисовывает."""

from collections import Counter
from collections.abc import Callable

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from onecstarter.ui import rail_icons, theme

_Factory = Callable[[theme.Palette], QIcon]
_FACTORIES: tuple[_Factory, ...] = (
    rail_icons.bases_icon,
    rail_icons.settings_icon,
    rail_icons.servers_icon,
)


def _dominant(icon: QIcon, state: QIcon.State) -> str:
    image = icon.pixmap(16, 16, QIcon.Mode.Normal, state).toImage()
    counts: Counter[str] = Counter(
        image.pixelColor(x, y).name().casefold()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )
    return counts.most_common(1)[0][0]


@pytest.mark.parametrize("factory", _FACTORIES, ids=("bases", "settings", "servers"))
@pytest.mark.parametrize("palette", (theme.DARK, theme.LIGHT), ids=("dark", "light"))
def test_off_state_is_dim_and_on_state_is_accent(
    qapp: QApplication, factory: _Factory, palette: theme.Palette
) -> None:
    icon = factory(palette)
    assert _dominant(icon, QIcon.State.Off) == palette.text_dim.casefold()
    assert _dominant(icon, QIcon.State.On) == palette.accent.casefold()


def test_all_sections_have_different_icons(qapp: QApplication) -> None:
    images = [factory(theme.DARK).pixmap(16, 16).toImage() for factory in _FACTORIES]
    blobs = [image.constBits().tobytes() for image in images]  # type: ignore[union-attr]
    assert len(set(blobs)) == len(blobs)
