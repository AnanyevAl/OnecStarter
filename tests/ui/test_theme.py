"""Палитры темы. Тёмная — страж: 4a не должен измениться ни на пиксель."""

import re

import pytest

from onecstarter.services.settings import ThemeMode
from onecstarter.ui import theme


def test_dark_palette_repeats_4a_constants() -> None:
    """Значения сняты со скриншотов temp/style/ и утверждены в 4a.

    Задача 1 плана 4b — механическая замена структуры, а не правка вида.
    Тест держит это утверждение: изменение любого значения тёмной палитры
    обязано быть осознанным решением, а не побочным эффектом рефакторинга.
    """  # noqa: RUF002
    assert theme.DARK.background == "#161616"
    assert theme.DARK.surface == "#1e1e1e"
    assert theme.DARK.surface_raised == "#262626"
    assert theme.DARK.border == "#333333"
    assert theme.DARK.text == "#e8e8e8"
    assert theme.DARK.text_dim == "#9a9a9a"
    assert theme.DARK.accent == "#f2d54c"
    assert theme.DARK.problem == "#e57373"


def test_dark_palette_new_roles_repeat_the_mockup() -> None:
    """Мокап 15.08.2026: заливка — фирменный жёлтый, выделение = raised."""
    assert theme.DARK.accent_fill == "#f2d54c"
    assert theme.DARK.selection == "#262626"


def test_light_palette_repeats_the_mockup() -> None:
    """Светлая палитра утверждена мокапом (спека рестайла §1) — прибита
    к значениям так же, как тёмная к значениям 4a: изменение любого цвета
    обязано быть осознанным решением, а не побочным эффектом.
    """  # noqa: RUF002
    assert theme.LIGHT.background == "#fafafa"
    assert theme.LIGHT.surface == "#f0f1f3"
    assert theme.LIGHT.surface_raised == "#ffffff"
    assert theme.LIGHT.border == "#d8dbe0"
    assert theme.LIGHT.text == "#1a1a1a"
    assert theme.LIGHT.text_dim == "#5c5c5c"
    assert theme.LIGHT.accent == "#8a6600"
    assert theme.LIGHT.accent_fill == "#f2d54c"
    assert theme.LIGHT.problem == "#c62828"
    assert theme.LIGHT.selection == "#fdf3cf"


def test_light_palette_differs_in_every_role() -> None:
    """Светлая — не тёмная с другим фоном: перекрашены все восемь ролей.

    Инверсией задача не решалась: #f2d54c на белом даёт 1,5:1, #e57373 — 3,0:1,
    #9a9a9a — 2,8:1 при пороге 4,5:1 (спека §2.2).

    accent_fill в списке намеренно отсутствует: это фирменный жёлтый
    #f2d54c, одинаковый в обеих темах по построению (спека рестайла §2) —
    заливка, не текст, порог 4,5:1 к ней не применяется.
    """  # noqa: RUF002
    for field in ("background", "surface", "surface_raised", "border",
                  "text", "text_dim", "accent", "problem", "selection"):
        assert getattr(theme.LIGHT, field) != getattr(theme.DARK, field), field


def test_stylesheet_uses_given_palette() -> None:
    assert theme.DARK.background in theme.stylesheet(theme.DARK)
    assert theme.DARK.background not in theme.stylesheet(theme.LIGHT)
    assert theme.LIGHT.accent in theme.stylesheet(theme.LIGHT)


def test_menu_item_padding_precedes_selected_rule() -> None:
    """Страховка от отката правки padding у ``QMenu::item`` — не тест на дефект.

    Дефект (в контекстном меню базы подсказка сочетания налезала на название
    пункта) виден только на настоящем экране: offscreen — наша тестовая
    платформа (см. ``tests/ui/conftest.py``) — не воспроизводит его ни в одном
    из четырёх стилей Qt, ``sizeHint`` от правки не меняется. Показ проверяется
    глазами на машине заказчика; числа замера — план 4b, задача 6, шаг 1.

    Здесь проверяется только то, что лекарство не потерялось при следующей
    правке ``theme.py``: правило ``QMenu::item`` с ненулевым ``padding``
    существует и стоит раньше ``QMenu::item:selected``. Порядок в QSS значим —
    более позднее правило перекрывает более раннее, и перестановка вернула бы
    отступ пункта к нулю (замер круга 4, задача 6).
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        match = re.search(r"QMenu::item\s*\{\s*padding:\s*([^;]+);", css)
        assert match is not None, "правило QMenu::item с padding пропало"  # noqa: RUF001
        padding_parts = match.group(1).split()
        assert any(part not in ("0", "0px") for part in padding_parts), padding_parts
        selected_pos = css.index("QMenu::item:selected")
        assert match.start() < selected_pos, "QMenu::item должен идти раньше :selected"


def _rule_properties(css: str, selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match is not None, f"правило {selector} не найдено в таблице стилей"
    props: dict[str, str] = {}
    for part in match.group(1).split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition(":")
        props[name.strip()] = value.strip()
    return props


def test_selected_tree_item_has_an_explicit_readable_colour() -> None:
    """Smoke №1 (08.08.2026), замечание 1: выделенная строка была нечитаема

    в светлой теме. Правило ``QTreeView::item:selected`` задавало только
    ``background`` — цвет текста оставался за стилем ``windows11``, а тот
    рассчитан на тёмный системный хайлайт и красит выделенный текст светлым;
    на нашем светлом ``surface_raised`` получалось светлое по светлому.

    Offscreen контраст глазами не проверить (задача теста — регрессия
    в QSS, не измерение WCAG), поэтому здесь — то, что проверяемо: явный
    ``color`` есть в правиле для обеих палитр и отличается от ``background``
    того же правила.
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        props = _rule_properties(theme.stylesheet(palette), "QTreeView::item:selected")
        assert "color" in props, "нет явного color у выделенной строки"  # noqa: RUF001
        assert props["color"].casefold() != props["background"].casefold()


def test_selected_tree_row_uses_the_selection_role() -> None:
    """Спека рестайла §2: фон выделенной строки — selection, не surface_raised."""
    for palette in (theme.DARK, theme.LIGHT):
        props = _rule_properties(theme.stylesheet(palette), "QTreeView::item:selected")
        assert props["background"] == palette.selection


def test_checked_rail_button_gets_stripe_fill_and_raised_ground() -> None:
    """Спека рестайла §3: активный раздел — жёлтая полоска, фон raised.

    Полоска в покое прозрачная той же толщины — содержимое кнопки
    не прыгает при переключении.
    """
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        idle = _rule_properties(css, "#NavRail QToolButton")
        checked = _rule_properties(css, "#NavRail QToolButton:checked")
        assert idle["border-left"] == "2px solid transparent"
        assert checked["border-left"] == f"2px solid {palette.accent_fill}"
        assert checked["background"] == palette.surface_raised


def test_panel_is_a_surface_with_a_monospace_path() -> None:
    """Спека рестайла §4: панель — surface с верхней границей, путь моноширинный.

    Important 2 финального ревью: `QLineEdit:read-only { color: text_dim }`
    побеждало, потому что `#ConnectionPath` не задавало `color` вовсе —
    путь приглушался вопреки мокапу, где это главное содержимое панели.
    Явный `color: palette.text` в правиле с более высокой специфичностью
    ID обязан перекрыть `QLineEdit:read-only`.
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        panel = _rule_properties(css, "#ConnectionPanel")
        assert panel["background"] == palette.surface
        assert panel["border-top"] == f"1px solid {palette.border}"
        path = _rule_properties(css, "#ConnectionPath")
        assert "Consolas" in path["font-family"]
        assert path["color"] == palette.text


def test_checked_theme_segment_uses_selection_and_accent() -> None:
    """Спека рестайла §6: активный сегмент — фон selection, текст accent."""
    for palette in (theme.DARK, theme.LIGHT):
        props = _rule_properties(
            theme.stylesheet(palette), "#ThemeSeg QPushButton:checked"
        )
        assert props["background"] == palette.selection
        assert props["color"] == palette.accent


@pytest.mark.parametrize(
    ("mode", "system", "expected"),
    [
        (ThemeMode.DARK, ThemeMode.LIGHT, theme.DARK),
        (ThemeMode.LIGHT, ThemeMode.DARK, theme.LIGHT),
        (ThemeMode.AUTO, ThemeMode.LIGHT, theme.LIGHT),
        (ThemeMode.AUTO, ThemeMode.DARK, theme.DARK),
    ],
)
def test_palette_for(mode: ThemeMode, system: ThemeMode, expected: theme.Palette) -> None:
    """Явный выбор побеждает систему; AUTO следует за ней."""
    assert theme.palette_for(mode, system) is expected


def _relative_luminance(colour: str) -> float:
    """Относительная яркость цвета по WCAG 2.1."""
    raw = colour.lstrip("#")
    channels = [int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (high + 0.05) / (low + 0.05)


def test_contrast_formula_reproduces_the_numbers_from_the_spec() -> None:
    """Сначала проверяем сам измеритель, потом им меряем палитры.

    Числа взяты из §2.2 спеки: если формула здесь разойдётся с той, которой
    считали палитру, тест ниже начнёт сторожить не то, что задумано.
    """  # noqa: RUF002
    assert round(_contrast("#f2d54c", "#ffffff"), 1) == 1.5
    assert round(_contrast("#9a9a9a", "#ffffff"), 1) == 2.8
    assert round(_contrast("#e57373", "#ffffff"), 1) == 3.0


@pytest.mark.parametrize("ground", ["background", "surface", "surface_raised", "selection"])
@pytest.mark.parametrize("role", ["text", "text_dim", "accent", "problem"])
@pytest.mark.parametrize(
    "palette", [theme.DARK, theme.LIGHT], ids=["dark", "light"]
)
def test_text_roles_meet_the_contrast_threshold(
    palette: theme.Palette, role: str, ground: str
) -> None:
    """Каждая текстовая роль читается на **каждом** фоне своей темы: 4,5:1.

    Проверка несимметрична по пользе. Тёмная палитра и без того прибита
    к точным значениям 4a, а светлая — нет: `test_light_palette_differs_in_every_role`
    требует лишь непохожести на тёмную, и ошибочный цвет прошёл бы молча.

    Три фона, а не один — это и есть лекарство от найденного дефекта.
    §2.2 дизайна озаглавил колонку «Контраст к `#ffffff`» и считал только
    к нему; `text_dim` был подобран под 4,54:1 к белому, то есть ровно
    на пороге и без запаса. Любой не-белый фон уводил его под норму:
    замер 09.08.2026 дал 4,13:1 на `surface` — и это не умозрительный
    случай, а настоящие пиксели подписей разделов `NavRail`, заголовка
    таблицы и поля только для чтения. У `accent` та же болезнь: 4,47:1
    на `surface` (активная кнопка раздела, выделенный пункт меню).

    Правило намеренно шире сегодняшнего употребления: `problem` на `surface`
    сейчас нигде не рисуется. Дефект родился именно оттого, что проверка была
    уже употребления, — палитра обязана быть корректной целиком, а не в тех
    сочетаниях, которые кто-то не забыл перечислить.

    Чего здесь нет: выделенной строки дерева. Замер (offscreen, `grab()` +
    сэмплинг, все четыре стиля Qt) показал, что на ней `QBrush` элемента
    модели не побеждает — правило `QTreeView::item:selected { color: text }`
    красит текст в `text`, и приглушённый цвет туда не доходит вовсе.
    Выделенная строка даёт 14,5:1; сторожить там нечего.

    Фон `selection` добавлен рестайлом 15.08.2026: в светлой теме это
    бледно-жёлтый #fdf3cf, а не серый surface_raised, и читаемость на нём
    больше не следует из читаемости на трёх остальных фонах.
    """  # noqa: RUF002
    assert _contrast(getattr(palette, role), getattr(palette, ground)) >= 4.5
