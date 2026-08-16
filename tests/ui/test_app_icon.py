"""Тесты onecstarter.ui.app_icon — единственный источник фирменного значка.

Замечание заказчика на контрольной точке 16.08.2026: заголовок окна, панель
задач (.ico) и трей показывали три РАЗНЫХ значка. `app_icon.py` — общий
источник глифа для всех трёх мест; этот файл проверяет сам глиф и сборку
QIcon, а не потребителей (те покрыты test_app.py и test_tray.py).
"""  # noqa: RUF002

from typing import Any

from PySide6.QtGui import QImage

from onecstarter.ui import theme
from onecstarter.ui.app_icon import ICON_SIZES, application_icon, draw_app_icon


def _has_pixel_of_color(image: QImage, color_name: str) -> bool:
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).name() == color_name:
                return True
    return False


def test_draw_app_icon_returns_a_square_image_of_the_requested_size() -> None:
    # Краевые размеры набора кадров (§ брифа): 16 — самый мелкий, где
    # округление/пропорции легче всего съезжают, 256 — самый крупный.
    for size in (16, 256):
        image = draw_app_icon(size)
        assert image.width() == size
        assert image.height() == size


def test_draw_app_icon_paints_surface_and_accent_fill() -> None:
    """Значок непустой: несёт оба фирменных цвета — фон и «полки»."""  # noqa: RUF002
    for size in ICON_SIZES:
        image = draw_app_icon(size)
        assert _has_pixel_of_color(image, theme.DARK.surface), size
        assert _has_pixel_of_color(image, theme.DARK.accent_fill), size


def test_draw_app_icon_corners_are_transparent() -> None:
    """Скруглённый квадрат — угол (0,0) вне фигуры, почти не тронут даже сглаживанием.

    Не строго `== 0`: измерено (offscreen, PySide6 6.11.1) — на 16×16
    сглаживание (`QPainter.RenderHint.Antialiasing`) оставляет в самом
    угловом пикселе едва уловимый след дуги (alpha=2 из 255, ~0.8%); на
    24×24 и крупнее в этой же точке — уже точный ноль. Порог `<= 3`
    отделяет измеренный шум сглаживания от настоящей заливки (surface
    и accent_fill рисуются непрозрачными, alpha=255) — брифовое «alpha == 0»
    было гипотезой, не пережившей проверку на самом мелком кадре.
    """  # noqa: RUF002
    for size in (16, 256):
        image = draw_app_icon(size)
        assert image.pixelColor(0, 0).alpha() <= 3


def test_draw_app_icon_does_not_depend_on_the_palette_argument() -> None:
    """Сигнатура — только size: палитра не параметр (решение заказчика 16.08.2026).

    Тавтологический, но целенаправленный тест: `draw_app_icon` обязана
    рисовать фиксированными цветами `theme.DARK`, а не текущей темой
    приложения — иначе значок в трее/заголовке начал бы меняться при
    переключении темы, чего заказчик прямо не хочет (все значки одинаковые
    всегда).
    """  # noqa: RUF002
    first = draw_app_icon(32)
    second = draw_app_icon(32)
    assert first == second


def test_application_icon_has_frames_for_every_icon_size(qapp: Any) -> None:
    icon = application_icon()
    sizes = {(size.width(), size.height()) for size in icon.availableSizes()}
    assert sizes == {(size, size) for size in ICON_SIZES}


def test_application_icon_is_not_null(qapp: Any) -> None:
    assert not application_icon().isNull()
