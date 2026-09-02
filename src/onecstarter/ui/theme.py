"""Палитры интерфейса и сборка stylesheet по палитре.

Тёмная — по мотивам портала «1С для разработчиков» (temp/style/), цвета сняты
с эталонных скриншотов. Светлая эталона не имеет и собрана под порог контраста
4,5:1 (WCAG 2.1): жёлтый акцент #f2d54c на белом даёт 1,5:1 и как цвет текста
негоден, поэтому в светлой он заменён затемнённым янтарём. Без бренда 1С
(requirements.md, §4).

Палитра передаётся явно тем виджетам, которые запекают цвет в объект
(QBrush элементов модели, QPixmap иконок). Глобальной «текущей палитры»
в модуле нет намеренно: она потребовала бы сброса в каждом UI-тесте,
и забытый сброс дал бы тест, зелёный из-за соседа.
"""  # noqa: RUF002

from dataclasses import dataclass

from onecstarter.services.settings import ThemeMode


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    surface_raised: str
    border: str
    text: str
    text_dim: str
    accent: str
    accent_fill: str
    selection: str
    problem: str


DARK = Palette(
    background="#161616",
    surface="#1e1e1e",
    surface_raised="#262626",
    border="#333333",
    text="#e8e8e8",
    text_dim="#9a9a9a",
    accent="#f2d54c",
    accent_fill="#f2d54c",
    selection="#262626",
    problem="#e57373",
)

# Палитра мокапа (docs/superpowers/specs/assets/2026-08-08-v1-plan4b-mockup.html),
# утверждена заказчиком 15.08.2026 (спека рестайла §1). Иерархия поверхностей
# инвертирована относительно прежней светлой темы: приподнятое — белое на
# сером фоне, а не серое на белом.  # noqa: RUF003
#
# Замеры контраста (WCAG 2.1), 15.08.2026, к каждому фону включая `selection`:
# худшие значения — на `surface` — text 15,40:1, text_dim 5,92:1, accent
# 4,67:1, problem 4,97:1; на `selection` — text 15,66:1, text_dim 6,02:1,
# accent 4,75:1, problem 5,06:1. Все выше порога 4,5:1.  # noqa: RUF003
LIGHT = Palette(
    background="#fafafa",
    surface="#f0f1f3",
    surface_raised="#ffffff",
    border="#d8dbe0",
    text="#1a1a1a",
    text_dim="#5c5c5c",
    accent="#8a6600",
    accent_fill="#f2d54c",
    problem="#c62828",
    selection="#fdf3cf",
)


def stylesheet(palette: Palette) -> str:
    return f"""
QMainWindow, QDialog, QMessageBox {{ background: {palette.background}; }}
QWidget {{ color: {palette.text}; font-size: 10pt; }}
#NavRail {{ background: {palette.surface}; border-right: 1px solid {palette.border}; }}
#NavRail QToolButton {{
    border: none; border-left: 2px solid transparent;
    padding: 8px 2px; color: {palette.text_dim}; font-size: 8pt;
}}
#NavRail QToolButton:checked {{
    color: {palette.accent}; border-left: 2px solid {palette.accent_fill};
    background: {palette.surface_raised};
}}
QLineEdit {{
    background: {palette.surface_raised}; border: 1px solid {palette.border};
    border-radius: 4px; padding: 6px 8px;
}}
QLineEdit:focus {{ border: 1px solid {palette.accent}; }}
QLineEdit:read-only {{ background: {palette.surface}; color: {palette.text_dim}; }}
QTreeView {{ background: {palette.background}; border: none; }}
QTreeView::item {{ padding: 4px; }}
/* [Ф] smoke №1, 08.08.2026, замечание 1: без явного color здесь текст
   выделенной строки красит стиль windows11 своим цветом хайлайта —
   он рассчитан на тёмный системный выбор и на нашем светлом
   surface_raised даёт светлое по светлому, нечитаемо.
   Эксперимент (offscreen, grab() + сэмплинг пикселей, задача 5 круг
   правок 2): без этого правила пиксели выделенного текста НЕ содержат
   Qt::ForegroundRole строки вовсе — цвет из QBrush в tree_model.py
   (битая запись — palette.problem, неявный узел — palette.text_dim)
   стилем при выделении игнорируется, побеждает встроенный хайлайт
   стиля. С этим правилом внутри :selected побеждает уже оно — все
   выделенные строки красятся в palette.text одинаково читаемо, а свой
   цвет (проблема/приглушённость) строка получает обратно сразу же,
   как только выделение снимается. Строки с parse_error/cell.problem
   при выделении временно теряют красный — это плата за читаемость,
   а не дефект: сам факт «строка выделена» и так виден по фону. */
QTreeView::item:selected {{ background: {palette.selection}; color: {palette.text}; }}
QHeaderView::section {{
    background: {palette.surface}; color: {palette.text_dim};
    border: none; padding: 4px 8px;
}}
QMenu {{ background: {palette.surface_raised}; border: 1px solid {palette.border}; }}
/* [Ф] 08.08.2026, замеры на машине заказчика (задача 6, шаг 1): правило
   QMenu выше переводит меню на раскладку по QSS, где padding пункта нулевой.
   Без этой строки sizeHint = 152 px при содержимом 128 px — на колонку
   значка, поля и зазор между названием и сочетанием остаётся 24 px,
   и подсказка налезает на название. С ней sizeHint = 200 px. */
QMenu::item {{ padding: 5px 28px 5px 28px; }}
QMenu::item:selected {{ background: {palette.surface}; color: {palette.accent}; }}
QToolTip {{
    background: {palette.surface_raised}; color: {palette.text};
    border: 1px solid {palette.border};
}}
#ConnectionPanel {{ background: {palette.surface}; border-top: 1px solid {palette.border}; }}
#ConnectionPath {{
    font-family: Consolas, "Cascadia Mono", monospace;
    border: none; background: transparent; padding: 0;
    color: {palette.text};
}}
#PanelKindWord {{ color: {palette.text_dim}; }}
#ConnectionPanel QPushButton {{
    border: 1px solid {palette.border}; background: {palette.surface_raised};
    border-radius: 4px; padding: 2px 9px;
}}
#ConnectionPanel QPushButton:disabled {{ color: {palette.text_dim}; }}
#SettingsSub, #SettingsNote {{ color: {palette.text_dim}; font-size: 8pt; }}
#SettingsGroupLabel {{
    color: {palette.accent}; border: none; background: transparent;
    text-align: left; padding: 0;
}}
#SettingsBlockLabel {{
    color: {palette.text}; border: none; background: transparent;
    text-align: left; padding: 0;
}}
#ThemeSeg QPushButton {{
    border: 1px solid {palette.border}; background: {palette.surface_raised};
    padding: 3px 10px; font-size: 9pt;
}}
#ThemeSeg QPushButton:checked {{
    background: {palette.selection}; color: {palette.accent}; font-weight: 600;
}}
"""  # noqa: RUF001


def palette_for(mode: ThemeMode, system: ThemeMode) -> Palette:
    """Действующая палитра: явный выбор побеждает, AUTO следует за системой.

    `system` обязан быть LIGHT или DARK — «системный AUTO» не существует;
    неопределённость системы разрешает detect_system_mode до вызова.
    """
    effective = system if mode is ThemeMode.AUTO else mode
    return LIGHT if effective is ThemeMode.LIGHT else DARK
