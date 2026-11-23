"""Палитры темы. Тёмная — страж: 4a не должен измениться ни на пиксель."""

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

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
    """Светлая — не тёмная с другим фоном: перекрашены все роли.

    Инверсией задача не решалась: #f2d54c на белом даёт 1,5:1, #e57373 — 3,0:1,
    #9a9a9a — 2,8:1 при пороге 4,5:1 (спека §2.2).

    accent_fill в списке намеренно отсутствует: это фирменный жёлтый
    #f2d54c, одинаковый в обеих темах по построению (спека рестайла §2) —
    заливка, не текст, порог 4,5:1 к ней не применяется.
    `on_accent` в списке отсутствует по той же причине, что `accent_fill`: текст
    на фирменном жёлтом одинаков в обеих темах.
    """  # noqa: RUF002
    for field in ("background", "surface", "surface_raised", "border",
                  "text", "text_dim", "accent", "problem", "selection", "running",
                  "warning", "info", "unknown", "problem_bg", "warning_bg",
                  "info_bg", "code", "text_disabled"):
        assert getattr(theme.LIGHT, field) != getattr(theme.DARK, field), field


def test_running_role_is_green_in_both_themes() -> None:
    assert theme.DARK.running == "#66bb6a"
    assert theme.LIGHT.running == "#2c6e2f"


def test_v4_roles_repeat_the_mockup() -> None:
    """Мокап v4 (токены --warn … --code, `.btn.pri`; аудит плана Б, раздел 1).

    `text_disabled` в мокапе нет — предложение аудита, утверждается по живому виду.
    """
    expected = {
        "warning": ("#e0a040", "#9a5b00"),
        "info": ("#64a0e0", "#1f5fa8"),
        "unknown": ("#c792ea", "#7b3fb0"),
        "problem_bg": ("#2a1a1a", "#fdecec"),
        "warning_bg": ("#2a2418", "#fdf3e1"),
        "info_bg": ("#18222c", "#e8f0fb"),
        "code": ("#121212", "#ffffff"),
        "on_accent": ("#1a1a1a", "#1a1a1a"),
        "text_disabled": ("#6a6a6a", "#9a9a9a"),
    }
    for role, (dark, light) in expected.items():
        assert (getattr(theme.DARK, role), getattr(theme.LIGHT, role)) == (dark, light), role


def test_text_on_the_primary_button_is_readable() -> None:
    """`.btn.pri` мокапа: #1a1a1a на фирменном жёлтом — одна пара на обе темы."""  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        assert _contrast(palette.on_accent, palette.accent_fill) >= 4.5


def test_stylesheet_uses_given_palette() -> None:
    assert theme.DARK.background in theme.stylesheet(theme.DARK)
    assert theme.DARK.background not in theme.stylesheet(theme.LIGHT)
    assert theme.LIGHT.accent in theme.stylesheet(theme.LIGHT)


def test_properties_scroll_names_are_transparent_and_never_a_bare_widget_selector() -> None:
    """В4 (решение заказчика 21.11.2026): область прокрутки окна свойств, по objectName."""  # noqa: RUF002
    css = theme.stylesheet(theme.LIGHT)
    rule = re.search(r"([^{}]*#PropertiesScroll[^{}]*)\{([^}]*)\}", css)
    assert rule is not None
    selectors, body = rule.group(1), rule.group(2)
    for name in ("#PropertiesScroll", "#PropertiesViewport", "#PropertiesContent"):
        assert name in selectors
    assert "background: transparent" in body
    assert not re.search(r"(^|[\s,>])QWidget[^{]*\{[^}]*transparent", css)


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


def test_list_and_table_views_use_the_palette_background() -> None:
    """Smoke заказчика 21.09.2026: без правила item view красится ролью Base системной

    палитры — в тёмном режиме Windows тёмный фон под тёмным текстом светлой темы
    (`QWidget { color: palette.text }`). `QListWidget`/`QTableWidget` в диалогах
    («Цветовая схема», CLI-импорт, CLI-валидация, серверы) — те же `QListView`/
    `QTableView` под капотом, правило по типу представления красит их все разом.
    """
    for palette in (theme.DARK, theme.LIGHT):
        props = _rule_properties(theme.stylesheet(palette), "QListView, QTableView")
        assert props["background"] == palette.background


def test_selected_list_and_table_item_has_an_explicit_readable_colour() -> None:
    """Та же причина, что у ``QTreeView::item:selected`` (замечание 1, 08.08.2026):

    без явного ``color`` выделенную строку/ячейку красит хайлайт стиля ``windows11``,
    рассчитанный на тёмный системный выбор — на светлом ``selection`` получилось бы
    светлое по светлому.
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        props = _rule_properties(
            theme.stylesheet(palette),
            "QListView::item:selected, QTableView::item:selected",
        )
        assert props["color"] == palette.text
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

    С переходом панели на `PathLink` (v3.1, замечание 1) цвет пути задаёт
    сам виджет через rich-text (см. `path_link.py`), а не QSS — правило
    `#PathLink` отвечает только за шрифт.
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        panel = _rule_properties(css, "#ConnectionPanel")
        assert panel["background"] == palette.surface
        assert panel["border-top"] == f"1px solid {palette.border}"
        path = _rule_properties(css, "#PathLink")
        assert "Consolas" in path["font-family"]


def test_checked_theme_segment_uses_selection_and_accent() -> None:
    """Спека рестайла §6: активный сегмент — фон selection, текст accent."""
    for palette in (theme.DARK, theme.LIGHT):
        props = _rule_properties(
            theme.stylesheet(palette), "#ThemeSeg QPushButton:checked"
        )
        assert props["background"] == palette.selection
        assert props["color"] == palette.accent


def test_settings_group_header_shows_a_focus_frame() -> None:
    """Заголовок группы — `QToolButton` ради Tab, и фокус обязан быть виден.

    Находка заказчика при живой проверке 02.09.2026: по Tab фокус до
    заголовка доходил, но понять, на каком именно он стоит, было нельзя —
    с кнопки снят весь «хром». Доступность с клавиатуры, ради которой
    заголовок и сделан кнопкой, оказалась фиктивной.

    Цвет рамки — `accent`: та же конвенция, что у `QLineEdit:focus`
    и в спеке рестайла §2 («accent — рамка фокуса»), а не новая
    выдумка рядом с существующей.

    Второе утверждение не менее важно первого: в обычном состоянии
    рамка обязана быть ПРОЗРАЧНОЙ, а не отсутствовать. С `border: none`
    появление фокуса добавляло бы виджету пиксель и дёргало раскладку
    при каждом нажатии Tab.
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        for selector in ("#SettingsGroupLabel", "#SettingsBlockLabel"):
            assert _rule_properties(css, selector)["border"] == "1px solid transparent"
            focus = _rule_properties(css, f"{selector}:focus")
            assert focus["border-color"] == palette.accent


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


@pytest.mark.parametrize(
    "ground",
    ["background", "surface", "surface_raised", "selection",
     "problem_bg", "warning_bg", "info_bg", "code"],
)
@pytest.mark.parametrize(
    "role", ["text", "text_dim", "accent", "problem", "running", "warning", "info", "unknown"]
)
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

    Фоны выносок и `code` добавлены планом Б (21.11.2026): текст
    выносок и предпросмотра рисуется на них, и читаемость на них не следует из
    читаемости на четырёх прежних фонах.
    """  # noqa: RUF002
    assert _contrast(getattr(palette, role), getattr(palette, ground)) >= 4.5


def test_primary_and_danger_roles_are_styled_by_property() -> None:
    """Решение заказчика 1 (21.11.2026): жёлтая главная и красная опасная — по свойству `role`.

    Не `:default`: у кнопок с `autoDefault` статус переходит к кнопке в фокусе (аудит, раздел 4).
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        primary = _rule_properties(css, 'QPushButton[role="primary"]')
        assert primary["background"] == palette.accent_fill
        assert primary["color"] == palette.on_accent
        danger = _rule_properties(css, 'QPushButton[role="danger"]')
        assert danger["color"] == palette.problem
        assert danger["border"] == f"1px solid {palette.problem}"
        for role in ("primary", "danger"):
            off = _rule_properties(css, f'QPushButton[role="{role}"]:disabled')
            assert off["color"] == palette.text_disabled
            assert off["background"] == palette.surface


def test_no_global_rules_for_native_controls() -> None:
    """Решение заказчика 1: родные кнопки, списки и флажки `windows11` не перекрашиваются QSS.

    Глобальное правило перевело бы виджет на generic-отрисовку во всех разделах (EDT,
    Серверы, Настройки) — риск 1 аудита. Разрешены только правила с атрибутом, objectName
    или предком.
    """  # noqa: RUF002
    # Б5″ (22.11.2026): исключение — только подконтроль квадрата `QCheckBox::indicator`
    # (с псевдосостояниями). Проверяются и селекторы после запятой.  # noqa: RUF003
    pattern = re.compile(
        r"(?m)(?:^|,)\s*(?!QCheckBox::indicator)(QPushButton|QComboBox|QCheckBox|QRadioButton)"
        r"\s*(\{|:|,)"
    )
    for palette in (theme.DARK, theme.LIGHT):
        assert pattern.findall(theme.stylesheet(palette)) == []


def test_disabled_widgets_are_greyed() -> None:
    """В10: `QWidget { color }` перекрывал серость группы Disabled — правило `:disabled` позже."""  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        assert _rule_properties(css, "QWidget:disabled")["color"] == palette.text_disabled
        assert css.index("QWidget:disabled") > css.index("QWidget {")
        assert _rule_properties(css, "QLineEdit:disabled")["color"] == palette.text_disabled
        menu = _rule_properties(css, "QMenu::item:disabled")
        assert menu["color"] == palette.text_disabled
        # Позже :selected — неактивный пункт под курсором остаётся серым.
        assert css.index("QMenu::item:disabled") > css.index("QMenu::item:selected")


def test_menu_separator_is_a_thin_border_line() -> None:
    """Мокап, экран 3 (`.hr`): без правила разделитель рисует `windows11` (аудит 3.2, В16)."""  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        separator = _rule_properties(theme.stylesheet(palette), "QMenu::separator")
        assert separator["height"] == "1px"
        assert separator["background"] == palette.border


def test_disabled_button_text_takes_the_disabled_role(qtbot: Any) -> None:
    """[гипотеза аудита, В10 — проверена шагом 1 задачи 3] QSS доходит до палитры виджета."""  # noqa: RUF002
    button = QPushButton("Неактивная")
    qtbot.addWidget(button)
    button.setStyleSheet(theme.stylesheet(theme.LIGHT))
    button.setEnabled(False)
    button.ensurePolished()
    colour = button.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)
    assert colour.name() == theme.LIGHT.text_disabled


def test_item_view_indicators_have_a_frame_and_a_drawn_checkmark() -> None:
    """В6, Б0 [проверено] 21.11.2026: `windows11` рисует отмеченный флажок дерева голой галочкой.

    Рамка — `text_dim`, не `border`: у `border` к фонам 1,33–1,43:1 при пороге 3:1 для
    элементов управления (WCAG 1.4.11, аудит плана Б, раздел 1).
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        frame = _rule_properties(css, "QTreeView::indicator, QListView::indicator")
        assert frame["border"] == f"1px solid {palette.text_dim}"
        assert frame["background"] == palette.surface_raised
        checked = _rule_properties(
            css, "QTreeView::indicator:checked, QListView::indicator:checked"
        )
        assert checked["background"] == palette.accent_fill
        expected = theme.indicator_path(theme.INDICATOR_CHECK).as_posix()
        assert checked["image"] == f'url("{expected}")'
        assert "\\" not in checked["image"]
        partial = _rule_properties(
            css, "QTreeView::indicator:indeterminate, QListView::indicator:indeterminate"
        )
        assert theme.INDICATOR_PARTIAL in partial["image"]


def test_standalone_checkbox_indicator_rules() -> None:
    """Б5″ (решение заказчика 22.11.2026): квадрат отдельного флажка — как у деревьев.

    Замер на `windows11` в тёмной теме: галочка (222,232,232) на акценте Windows
    (173,188,191), контраст 1,6:1 — картинка пакета тёмная, заливка `accent_fill`.
    """  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        base = _rule_properties(css, "QCheckBox::indicator")
        assert base["border"] == f"1px solid {palette.text_dim}"
        assert base["width"] == "14px"
        assert base["height"] == "14px"
        assert base["border-radius"] == "3px"
        assert base["background"] == palette.surface_raised
        checked = _rule_properties(css, "QCheckBox::indicator:checked")
        assert checked["background"] == palette.accent_fill
        expected = theme.indicator_path(theme.INDICATOR_CHECK).as_posix()
        assert checked["image"] == f'url("{expected}")'
        partial = _rule_properties(css, "QCheckBox::indicator:indeterminate")
        assert theme.INDICATOR_PARTIAL in partial["image"]
        off = _rule_properties(css, "QCheckBox::indicator:disabled")
        assert off["border-color"] == palette.text_disabled
        assert off["background"] == palette.surface
        off_checked = _rule_properties(
            css,
            "QCheckBox::indicator:checked:disabled, QCheckBox::indicator:indeterminate:disabled",
        )
        assert off_checked["background"] == palette.text_disabled
        focus = _rule_properties(css, "QCheckBox::indicator:focus")
        assert focus["border-color"] == palette.accent


def _checkbox_indicator_image(
    qtbot: Any, palette: theme.Palette, *, state: Qt.CheckState = Qt.CheckState.Checked
) -> tuple[Any, Any]:
    """(снимок квадрата индикатора, его прямоугольник) у отмеченного QCheckBox.

    Стиль — на родителе, не на QApplication: глобальная таблица утекла бы в другие тесты.
    """  # noqa: RUF002
    parent = QWidget()
    qtbot.addWidget(parent)
    layout = QHBoxLayout(parent)
    box = QCheckBox("флажок")
    box.setCheckState(state)
    layout.addWidget(box)
    parent.setStyleSheet(theme.stylesheet(palette))
    parent.resize(200, 60)
    parent.show()
    qtbot.waitExposed(parent)
    option = QStyleOptionButton()
    box.initStyleOption(option)
    rect = box.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, box)
    return box.grab().toImage(), rect


def _luminance(colour: QColor) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(colour.red()) + 0.7152 * channel(colour.green()) + (
        0.0722 * channel(colour.blue())
    )


@pytest.mark.parametrize("palette", [theme.DARK, theme.LIGHT], ids=["dark", "light"])
def test_checked_standalone_checkbox_shows_a_dark_mark_on_the_accent_fill(
    qtbot: Any, palette: theme.Palette
) -> None:
    """Б5″: в квадрате отдельного флажка — заливка `accent_fill` и тёмная галочка, контраст ≥ 3:1.

    Мутация — убрать `image` у `QCheckBox::indicator:checked`: нет тёмных пикселей.
    """  # noqa: RUF002
    image, rect = _checkbox_indicator_image(qtbot, palette)
    fill = QColor(palette.accent_fill)
    inside = [
        QColor(image.pixel(x, y))
        for x in range(rect.left() + 2, rect.right() - 1)
        for y in range(rect.top() + 2, rect.bottom() - 1)
    ]
    assert inside, rect
    assert any(pixel.rgb() == fill.rgb() for pixel in inside), "нет заливки accent_fill"
    dark = [pixel for pixel in inside if pixel.lightness() < 80]
    assert dark, "нет тёмной галочки внутри квадрата"
    lighter, darker = sorted((_luminance(fill), _luminance(dark[0])), reverse=True)
    assert (lighter + 0.05) / (darker + 0.05) >= 3, (palette.accent_fill, dark[0].name())


def test_focused_standalone_checkbox_indicator_border_is_the_accent(qtbot: Any) -> None:
    """Б5″: `QCheckBox::indicator:focus` — рамка `accent`; проверка, что подконтроль это рисует."""
    palette = theme.LIGHT
    parent = QWidget()
    qtbot.addWidget(parent)
    layout = QHBoxLayout(parent)
    box = QCheckBox("флажок")
    layout.addWidget(box)
    parent.setStyleSheet(theme.stylesheet(palette))
    parent.resize(200, 60)
    parent.show()
    qtbot.waitExposed(parent)
    box.setFocus()
    qtbot.waitUntil(box.hasFocus)
    option = QStyleOptionButton()
    box.initStyleOption(option)
    rect = box.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, box)
    image = box.grab().toImage()
    accent = QColor(palette.accent).rgb()
    edge = [
        image.pixel(x, rect.top() + rect.height() // 2) for x in (rect.left(), rect.left() + 1)
    ]
    assert accent in edge, [QColor(p).name() for p in edge]


def test_indicator_images_ship_with_the_package() -> None:
    for name in (theme.INDICATOR_CHECK, theme.INDICATOR_PARTIAL):
        path = theme.indicator_path(name)
        assert path.is_file(), path
        assert "#1a1a1a" in path.read_text("utf-8")  # on_accent обеих тем


def _checked_tree_pixels(
    qtbot: Any,
    palette: theme.Palette,
    *,
    disabled: bool = False,
    state: Qt.CheckState = Qt.CheckState.Checked,
) -> tuple[bool, bool]:
    """(есть заливка, есть галочка) у отмеченного флажка дерева.

    Заливка — `accent_fill`, у неактивного дерева — `text_disabled` (финальное ревью плана Б,
    F2: прежде неактивный отмеченный флажок тёмной темы выглядел снятым).

    Заливку рисует `background`, галочку — только `image: url(...)`. Поэтому галочка ищется
    тёмными пикселями **внутри** жёлтого квадрата (ужатого на 2 px от краёв, где рамка и
    сглаживание углов): текст строки лежит правее и в счёт не идёт, хотя у светлой темы
    `text` совпадает с цветом галочки `#1a1a1a` (предпроверка плана, 3.1).
    """  # noqa: RUF002
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    tree.setHeaderHidden(True)
    tree.setStyleSheet(theme.stylesheet(palette))
    item = QTreeWidgetItem(["отмечен"])
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(0, state)
    tree.addTopLevelItem(item)
    tree.setDisabled(disabled)
    tree.resize(240, 80)
    tree.show()
    qtbot.waitExposed(tree)
    image = tree.viewport().grab(tree.visualItemRect(item)).toImage()
    fill = QColor(palette.text_disabled if disabled else palette.accent_fill).rgb()
    points = [
        (x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixel(x, y) == fill
    ]
    if not points:
        return False, False
    # Квадрат флажка — первая слева сплошная полоса столбцов: текст строки неактивного
    # дерева того же цвета `text_disabled`, что и заливка, и расширил бы рамку поиска.
    columns = sorted({x for x, _ in points})
    right = columns[0]
    while right + 1 in columns:
        right += 1
    points = [(x, y) for x, y in points if x <= right]
    xs, ys = [x for x, _ in points], [y for _, y in points]
    inside = [
        image.pixel(x, y)
        for x in range(min(xs) + 2, max(xs) - 1)
        for y in range(min(ys) + 2, max(ys) - 1)
    ]
    # Заливка — не меньше четверти внутренних пикселей (галочка занимает около половины):
    # рамка неактивного флажка того же цвета `text_disabled`, и без этого условия рамка
    # вокруг пустого квадрата сошла бы за заливку (внутри неё заливки нет вовсе).
    filled = bool(inside) and 4 * sum(pixel == fill for pixel in inside) >= len(inside)
    mark = any(QColor(pixel).lightness() < 80 for pixel in inside)
    return filled, mark


def test_checked_tree_item_draws_the_fill_and_the_checkmark(qtbot: Any) -> None:
    """Мутационная проверка обязательна: без `background` нет заливки, без `image` — галочки."""
    assert _checked_tree_pixels(qtbot, theme.LIGHT) == (True, True)


@pytest.mark.parametrize("palette", [theme.DARK, theme.LIGHT], ids=["dark", "light"])
@pytest.mark.parametrize(
    "state", [Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked], ids=["checked", "partial"]
)
def test_disabled_checked_tree_item_still_looks_checked(
    qtbot: Any, palette: theme.Palette, state: Qt.CheckState
) -> None:
    """Финальное ревью плана Б, F2: неактивный отмеченный флажок не выглядит снятым.

    Место — импорт EDT через CLI: в режиме XML список проектов неактивен. Прежде правило
    `::indicator:disabled` клало `surface` (тёмная тема — #1e1e1e) под галочку #1a1a1a.
    Мутация — убрать правило `:checked:disabled`: красный.
    """
    assert _checked_tree_pixels(qtbot, palette, disabled=True, state=state) == (True, True)


def test_missing_indicator_image_draws_no_checkmark(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Контроль самой проверки: нечитаемый `url()` оставляет фон, но не галочку.

    Без этого теста проверка пути ниже могла бы оказаться зелёной и при сломанном пути —
    так было в первой редакции плана, где искалась только заливка (предпроверка, 3.1).
    """
    monkeypatch.setattr(theme, "indicator_path", lambda name: tmp_path / "нет такого" / name)
    assert _checked_tree_pixels(qtbot, theme.LIGHT) == (True, False)


def test_indicator_url_survives_spaces_and_cyrillic_in_the_path(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Установка — в профиле пользователя: в имени бывают пробел и кириллица."""
    spaced = tmp_path / "Иван Петров" / "resources"
    spaced.mkdir(parents=True)
    for name in (theme.INDICATOR_CHECK, theme.INDICATOR_PARTIAL):
        shutil.copyfile(theme.indicator_path(name), spaced / name)
    monkeypatch.setattr(theme, "indicator_path", lambda name: spaced / name)
    assert _checked_tree_pixels(qtbot, theme.LIGHT) == (True, True)


def test_block_titles_of_the_properties_dialog_have_no_plate() -> None:
    """В1 (приёмка 21.11.2026): без правила нативный стиль рисует checked/hover-плашку."""  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        props = _rule_properties(css, "#LaunchParamsTitle, #RepositoryTitle")
        assert props["background"] == "transparent"
        assert props["border"] == "1px solid transparent"
        focus = _rule_properties(css, "#LaunchParamsTitle:focus, #RepositoryTitle:focus")
        assert focus["border-color"] == palette.accent
        assert _rule_properties(css, "#BlockSummary")["color"] == palette.text_dim


def test_callouts_follow_the_mockup_and_the_customer_decision() -> None:
    """Мокап `.msg`, `.msg.err`, `.msg.info`; решение заказчика 2: текст ошибки — `problem`."""
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        base = _rule_properties(css, "QLabel#Callout")
        assert base["border-left"] == f"3px solid {palette.warning}"
        assert base["background"] == palette.warning_bg
        assert base["color"] == palette.text
        error = _rule_properties(css, 'QLabel#Callout[level="error"]')
        assert (error["border-left-color"], error["background"], error["color"]) == (
            palette.problem, palette.problem_bg, palette.problem,
        )
        info = _rule_properties(css, 'QLabel#Callout[level="info"]')
        assert (info["border-left-color"], info["background"]) == (palette.info, palette.info_bg)


def test_chips_are_coloured_by_level() -> None:
    """Мокап `.chip.danger`, `.chip.warn` (стр. 52–54)."""  # noqa: RUF002
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        assert _rule_properties(css, "QLabel#Chip")["border-radius"] == "8px"
        error = _rule_properties(css, 'QLabel#Chip[level="error"]')
        assert (error["border-color"], error["color"]) == (palette.problem, palette.problem)
        warning = _rule_properties(css, 'QLabel#Chip[level="warning"]')
        assert (warning["border-color"], warning["color"]) == (palette.warning, palette.warning)


def test_named_text_roles() -> None:
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        assert _rule_properties(css, "#FormLabel, #DimLabel")["color"] == palette.text_dim
        accent = _rule_properties(css, "#AccentLabel")
        assert (accent["color"], accent["font-weight"]) == (palette.accent, "600")
        hint = _rule_properties(css, "#Hint")
        assert (hint["color"], hint["font-style"]) == (palette.text_dim, "italic")
        mono = _rule_properties(css, "#CodePreview, #MonoEdit")
        assert "Consolas" in mono["font-family"]
        assert _rule_properties(css, "#CodePreview")["background"] == palette.code


def test_boxes_footer_header_and_lists() -> None:
    for palette in (theme.DARK, theme.LIGHT):
        css = theme.stylesheet(palette)
        line = f"1px solid {palette.border}"
        box = _rule_properties(css, "#Box")
        assert (box["background"], box["border"]) == (palette.surface, line)
        views = _rule_properties(css, "#KeyTree, #SelectedKeys, #ScenarioTree, #Steps")
        assert views["background"] == palette.surface
        # Решение заказчика 1: типовой потомок бокса задел бы выпадающие списки QComboBox.
        assert not re.search(r"#Box\s+Q", css)
        title = _rule_properties(css, "#BoxTitle")
        assert (title["color"], title["border-bottom"]) == (palette.text_dim, line)
        assert _rule_properties(css, "#DialogFooter")["border-top"] == line
        assert _rule_properties(css, "#PanelHeader")["border-bottom"] == line
        steps = _rule_properties(css, "QListView#Steps::item:selected")
        assert steps["border-left"] == f"3px solid {palette.accent_fill}"
        assert _rule_properties(css, "QTableView#OpsTable::item")["border-bottom"] == line
        checked = _rule_properties(css, "#BasesMode QRadioButton:checked:enabled")
        assert checked["color"] == palette.accent
        assert _rule_properties(css, "QCheckBox#InlineCheck:enabled")["color"] == palette.text_dim
        # Без `:enabled` правило с objectName перебило бы `QWidget:disabled` (В10).  # noqa: RUF003
        assert "QRadioButton:checked {" not in css and "QCheckBox#InlineCheck {" not in css


def test_mono_rule_reaches_the_widget_font(qtbot: Any) -> None:
    """[проверено 21.11.2026, Б3] QSS-шрифт виден в `font()` после полировки."""
    edit = QLineEdit()
    qtbot.addWidget(edit)
    edit.setObjectName("MonoEdit")
    edit.setStyleSheet(theme.stylesheet(theme.DARK))
    edit.ensurePolished()
    assert edit.font().family() == "Consolas"


def test_splitter_handle_follows_the_theme_switched_on_the_fly(qapp: Any, qtbot: Any) -> None:
    """План В, Б2: родная ручка сплиттера держала цвет темы запуска (тёмная → светлая — чёрная
    полоса, наоборот — белая). Правило темы перекрашивает её при каждой смене."""  # noqa: RUF002
    from PySide6.QtWidgets import QSplitter, QWidget

    splitter = QSplitter()
    splitter.addWidget(QWidget())
    splitter.addWidget(QWidget())
    splitter.resize(200, 100)
    qtbot.addWidget(splitter)
    previous = qapp.styleSheet()
    try:
        for palette in (theme.DARK, theme.LIGHT, theme.DARK):
            qapp.setStyleSheet(theme.stylesheet(palette))
            splitter.show()
            qtbot.waitExposed(splitter)
            handle = splitter.handle(1)
            image = handle.grab().toImage()
            centre = image.pixelColor(image.width() // 2, image.height() // 2)
            assert centre.name() == palette.background
    finally:
        qapp.setStyleSheet(previous)
