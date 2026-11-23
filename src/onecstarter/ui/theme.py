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
from importlib import resources
from pathlib import Path

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
    # Роль «запущен» (задача 21, решение заказчика 11.09.2026): зелёный ▶
    # справа от имени записи. Контраст к четырём фонам (WCAG 2.1):
    # тёмная — 7,65:1 (background), 7,05:1 (surface), 6,4:1 (surface_raised),
    # 6,4:1 (selection); светлая — 5,96:1 (background), 5,5:1 (surface),
    # 6,22:1 (surface_raised), 5,59:1 (selection). Все выше порога 4,5:1.  # noqa: RUF003
    running: str
    # План Б (21.11.2026), мокап v4: смысловые цвета замечаний и состояний, фоны выносок,
    # фон предпросмотра и журнала, текст на фирменном жёлтом, неактивный текст.
    # Контраст (WCAG 2.1) текстовых ролей к восьми фонам — test_text_roles_meet_…;
    # худшие пары: светлая accent на info_bg 4,59:1, warning на info_bg 4,73:1.
    warning: str
    info: str
    unknown: str
    problem_bg: str
    warning_bg: str
    info_bg: str
    code: str
    on_accent: str
    # Контраст неактивного текста WCAG не нормирует; значение — на согласование
    # с заказчиком по живому виду (аудит плана Б, В10).  # noqa: RUF003
    text_disabled: str


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
    running="#66bb6a",
    warning="#e0a040",
    info="#64a0e0",
    unknown="#c792ea",
    problem_bg="#2a1a1a",
    warning_bg="#2a2418",
    info_bg="#18222c",
    code="#121212",
    on_accent="#1a1a1a",
    text_disabled="#6a6a6a",
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
    running="#2c6e2f",
    warning="#9a5b00",
    info="#1f5fa8",
    unknown="#7b3fb0",
    problem_bg="#fdecec",
    warning_bg="#fdf3e1",
    info_bg="#e8f0fb",
    code="#ffffff",
    on_accent="#1a1a1a",
    text_disabled="#9a9a9a",
)

INDICATOR_CHECK = "indicator-check.svg"
INDICATOR_PARTIAL = "indicator-partial.svg"


def indicator_path(name: str) -> Path:
    """Картинка индикатора флажка из пакета (`ui/resources`).

    В сборку попадает только через `datas` spec-файла; гейт — строка `smoke: indicators=`
    (build/smoke.py). Галочка одна на обе темы: `accent_fill` под ней одинаков.
    """  # noqa: RUF002
    return Path(str(resources.files("onecstarter.ui") / "resources" / name))


def _qss_url(name: str) -> str:
    # Прямые слэши — QSS не понимает обратных; кавычки — ради пробелов в пути установки.
    return f'url("{indicator_path(name).as_posix()}")'


def stylesheet(palette: Palette) -> str:
    return f"""
QMainWindow, QDialog, QMessageBox {{ background: {palette.background}; }}
QWidget {{ color: {palette.text}; font-size: 10pt; }}
/* В10 (приёмка 21.11.2026, Б0 [проверено]): `color` без псевдосостояния выше действует и
   на группу Disabled — неактивные кнопки, пункты и поля выглядели активными. Только цвет:
   фон и рамка нативных виджетов остаются за `windows11` (решение заказчика 1). */
QWidget:disabled {{ color: {palette.text_disabled}; }}
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
QLineEdit:disabled {{ background: {palette.surface}; color: {palette.text_disabled}; }}
/* Раздел «Настройки» (задача 8): viewport QScrollArea по умолчанию красится
   ролью Base — на светлой теме это белое пятно поверх background #fafafa.
   Круг правок 2 (re-review, 17.09.2026, подтверждено скриншотом на живом
   Windows 11): селектор — ТОЛЬКО по objectName, ни одного типового `QWidget`.
   Прошлая редакция (круг правок 1) держала `#SettingsScroll > QWidget` —
   формально верный адрес viewport, но у QScrollArea целых три прямых
   QWidget-потомка: сам viewport (`qt_scrollarea_viewport`) и два служебных
   контейнера полос, `qt_scrollarea_hcontainer`/`qt_scrollarea_vcontainer`
   (внутри каждого — единственный потомок, сам `QScrollBar`). Типовой
   селектор `QWidget` не различает их: правило красило заодно и полосы,
   переключая их с нативного стиля Windows 11 на generic Qt-фолбэк (толще,
   со стрелками и штриховкой) — офскрин-тесты этого не ловят, различие
   нативный/generic виден только на живом экране. Комментарий круга 1
   («три реальных виджета цепочки») был неверен — контейнеров полос не учёл.
   Правильный адрес — именование нужных виджетов кодом (`settings_view.py`:
   `self._scroll.viewport().setObjectName("SettingsViewport")`, содержимое —
   `SettingsContent`) и селектор по трём именам, без единого типового класса:
   полосы прокрутки под правило не попадают в принципе, кто бы ни оказался
   потомком QScrollArea в будущей версии Qt. Пиксельная сверка фона и вида
   полос — не автоматизирована (офскрин не различает нативный/generic стиль),
   проверяется вручную на живой машине (см. `docs/tasks.md`, T-20, «Ручной
   smoke»). */
#SettingsScroll, #SettingsViewport, #SettingsContent {{ background: transparent; }}
/* В4 (решение заказчика 21.11.2026): то же для области прокрутки окна свойств — отдельной
   строкой, правило настроек остаётся однострочным (сторож `test_settings_view.py`). */
#PropertiesScroll, #PropertiesViewport, #PropertiesContent {{ background: transparent; }}
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
/* В6 (приёмка 21.11.2026, Б0 [проверено]): windows11 рисует отмеченный флажок дерева голой
   галочкой при любой схеме. Рамка — text_dim, не border (контраст border к фонам ниже 3:1).
   Галочку QSS без картинки не рисует — SVG пакета (`indicator_path`). */
QTreeView::indicator, QListView::indicator {{
    width: 12px; height: 12px; border: 1px solid {palette.text_dim}; border-radius: 3px;
    background: {palette.surface_raised};
}}
QTreeView::indicator:checked, QListView::indicator:checked {{
    background: {palette.accent_fill}; image: {_qss_url(INDICATOR_CHECK)};
}}
QTreeView::indicator:indeterminate, QListView::indicator:indeterminate {{
    background: {palette.accent_fill}; image: {_qss_url(INDICATOR_PARTIAL)};
}}
QTreeView::indicator:disabled, QListView::indicator:disabled {{
    border-color: {palette.text_disabled}; background: {palette.surface};
}}
/* Финальное ревью плана Б, F2: под отмеченным неактивным флажком `surface` прятал галочку
   #1a1a1a в тёмной теме (#1e1e1e) — флажок выглядел снятым (импорт EDT через CLI, режим XML).
   Заливка `text_disabled` — бледнее активной `accent_fill`, галочка на ней видна. Порядок —
   после общего `:disabled`. */
QTreeView::indicator:checked:disabled, QListView::indicator:checked:disabled,
QTreeView::indicator:indeterminate:disabled, QListView::indicator:indeterminate:disabled {{
    background: {palette.text_disabled};
}}
/* Б5″ (решение заказчика 22.11.2026, живая приёмка плана В): квадрат ОТДЕЛЬНОГО флажка рисуется
   теми же правилами и SVG, что флажки деревьев. Замер на `windows11` в тёмной теме: галочка
   родного QCheckBox почти белая (222,232,232) на акценте Windows (173,188,191) — контраст 1,6:1.
   Откат Б5 (82ad258) оставлял родной вид; решение 1 («нет общих правил для QCheckBox»)
   нарушено только для подконтрола квадрата `::indicator` — сам `QCheckBox` (текст, фон, фокус-
   рамка) по-прежнему родной, сторож `test_no_global_rules_for_native_controls` держит это.
   Размер 14px — родной квадрат `windows11` (у деревьев 12px). */
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {palette.text_dim}; border-radius: 3px;
    background: {palette.surface_raised};
}}
QCheckBox::indicator:checked {{
    background: {palette.accent_fill}; image: {_qss_url(INDICATOR_CHECK)};
}}
QCheckBox::indicator:indeterminate {{
    background: {palette.accent_fill}; image: {_qss_url(INDICATOR_PARTIAL)};
}}
QCheckBox::indicator:disabled {{
    border-color: {palette.text_disabled}; background: {palette.surface};
}}
QCheckBox::indicator:checked:disabled, QCheckBox::indicator:indeterminate:disabled {{
    background: {palette.text_disabled};
}}
QCheckBox::indicator:focus {{ border-color: {palette.accent}; }}
/* Списки и таблицы (v3.2, ручной smoke 21.09.2026): без правила item view красится ролью
   Base системной палитры — в тёмном режиме Windows тёмный фон под тёмным текстом светлой
   темы. Селекторы по типу представлений (как QTreeView выше): QScrollBar под них не
   попадает. Явный color у выделения — по той же причине, что у QTreeView::item:selected. */
QListView, QTableView {{ background: {palette.background}; border: 1px solid {palette.border}; }}
QListView::item:selected, QTableView::item:selected {{
    background: {palette.selection}; color: {palette.text};
}}
QTableView {{ gridline-color: {palette.border}; }}
QTableCornerButton::section {{ background: {palette.surface}; border: none; }}
QHeaderView::section {{
    background: {palette.surface}; color: {palette.text_dim};
    border: none; padding: 4px 8px;
}}
/* План В, Б2 (повторная приёмка 21.11.2026): после смены темы на лету в «Операциях» между
   боксами оставались чёрные (тёмная → светлая) или белые полосы — ручки QSplitter. Причина
   [гипотеза журнала приёмки]: `windows11` красит родную ручку цветом схемы на момент создания.
   Ручка — цвет фона: зазор между боксами. Правило действует на все сплиттеры программы
   (конструктор, окно запуска и другие экраны) — проверяет живой чек-лист плана В, п. 2. */
QSplitter::handle {{ background: {palette.background}; }}
QMenu {{ background: {palette.surface_raised}; border: 1px solid {palette.border}; }}
/* [Ф] 08.08.2026, замеры на машине заказчика (задача 6, шаг 1): правило
   QMenu выше переводит меню на раскладку по QSS, где padding пункта нулевой.
   Без этой строки sizeHint = 152 px при содержимом 128 px — на колонку
   значка, поля и зазор между названием и сочетанием остаётся 24 px,
   и подсказка налезает на название. С ней sizeHint = 200 px. */
QMenu::item {{ padding: 5px 28px 5px 28px; }}
QMenu::item:selected {{ background: {palette.surface}; color: {palette.accent}; }}
QMenu::item:disabled {{ color: {palette.text_disabled}; background: transparent; }}
QMenu::separator {{ height: 1px; background: {palette.border}; margin: 4px 0; }}
QToolTip {{
    background: {palette.surface_raised}; color: {palette.text};
    border: 1px solid {palette.border};
}}
#ConnectionPanel {{ background: {palette.surface}; border-top: 1px solid {palette.border}; }}
#EdtPanel {{ background: {palette.surface}; border-top: 1px solid {palette.border}; }}
#PathLink {{
    font-family: Consolas, "Cascadia Mono", monospace;
    background: transparent; padding: 0;
}}
#PanelKindWord {{ color: {palette.text_dim}; }}
#SettingsSub, #SettingsNote {{ color: {palette.text_dim}; font-size: 8pt; }}
/* Ни font-size, ни font-weight, ни letter-spacing здесь нет НАМЕРЕННО:
   свойства шрифта заголовка группы ставит код — `ui/settings_group.py`,
   `CollapsibleGroup.__init__` (`setFont`), потому что Qt Style Sheets
   не умеют `letter-spacing`, а держать часть свойств шрифта в QSS,
   а часть в `setFont` нельзя — они перебивают друг друга непредсказуемо.
   Здесь остаются только цвет и «хром» самой кнопки QToolButton. */
#SettingsGroupLabel {{
    color: {palette.accent}; background: transparent;
    border: 1px solid transparent; text-align: left; padding: 0;
}}
#SettingsBlockLabel {{
    color: {palette.text}; background: transparent;
    border: 1px solid transparent; text-align: left; padding: 0;
}}
/* Рамка фокуса — accent, та же конвенция, что у `QLineEdit:focus` выше
   и в спеке рестайла §2. Заголовок группы сделан `QToolButton` ИМЕННО
   ради хода по Tab, и без видимого фокуса эта доступность оказалась
   фиктивной: заказчик при живой проверке 02.09.2026 не смог понять,
   на каком заголовке находится. В обычном состоянии рамка прозрачная,
   а не `border: none`, — иначе появление фокуса сдвигало бы раскладку
   на пиксель. [Ф] замер 02.09.2026: `focusPolicy` кнопки — `TabFocus`,
   то есть рамка появляется при ходьбе с клавиатуры и не возникает
   от щелчка мышью. */
#SettingsGroupLabel:focus {{ border-color: {palette.accent}; }}
#SettingsBlockLabel:focus {{ border-color: {palette.accent}; }}
/* В1 (приёмка 21.11.2026): заголовки блоков окна свойств — те же кнопки-заголовки, что у
   `#SettingsBlockLabel`, но со своими objectName; без правила windows11 рисовал плашку
   состояния checked/hover. Сводка рядом — обычным весом, text_dim (мокап, экран 1). */
#LaunchParamsTitle, #RepositoryTitle {{
    color: {palette.text}; background: transparent;
    border: 1px solid transparent; text-align: left; padding: 0;
}}
#LaunchParamsTitle:focus, #RepositoryTitle:focus {{ border-color: {palette.accent}; }}
#BlockSummary {{ color: {palette.text_dim}; }}
#ThemeSeg QPushButton {{
    border: 1px solid {palette.border}; background: {palette.surface_raised};
    padding: 3px 10px; font-size: 9pt;
}}
#ThemeSeg QPushButton:checked {{
    background: {palette.selection}; color: {palette.accent}; font-weight: 600;
}}
/* Роли кнопок (решение заказчика 1, 21.11.2026): остальные кнопки — родные `windows11`,
   их вид задаёт цветовая схема Qt (theme_controller.py). Свойство `role` ставит
   `ui/dialogs/buttons.py::mark_button`; `:default` не годится — у кнопок с autoDefault
   статус «по умолчанию» уходит к кнопке в фокусе (аудит плана Б, раздел 4). Рамка фокуса
   у `danger` — толще на пиксель с тем же внешним размером: цвет рамки уже занят. */
QPushButton[role="primary"] {{
    background: {palette.accent_fill}; color: {palette.on_accent};
    border: 1px solid {palette.accent_fill}; border-radius: 4px; padding: 5px 12px;
}}
QPushButton[role="primary"]:hover {{ border-color: {palette.text_dim}; }}
QPushButton[role="primary"]:pressed, QPushButton[role="primary"]:focus {{
    border-color: {palette.text};
}}
QPushButton[role="danger"] {{
    background: {palette.surface_raised}; color: {palette.problem};
    border: 1px solid {palette.problem}; border-radius: 4px; padding: 5px 12px;
}}
QPushButton[role="danger"]:hover, QPushButton[role="danger"]:pressed {{
    background: {palette.problem_bg};
}}
QPushButton[role="danger"]:focus {{ border-width: 2px; padding: 4px 11px; }}
/* Два одинаковых правила `:disabled`, а не одно через запятую, — сознательно: помощник
   `_rule_properties` в test_theme.py ищет селектор, за которым сразу идёт фигурная скобка,
   и на этом держится раздельная проверка `#CodePreview` (задача 5). Меняя одно, менять и второе. */
QPushButton[role="primary"]:disabled {{
    background: {palette.surface}; color: {palette.text_disabled}; border-color: {palette.border};
}}
QPushButton[role="danger"]:disabled {{
    background: {palette.surface}; color: {palette.text_disabled}; border-color: {palette.border};
}}
/* Именованные элементы экранов v4 (план Б, мокап 2026-11-08): objectName ставят виджеты
   `ui/components.py`, `ui/command_line.py` и экраны. Свойства `level` — динамические,
   ставятся до первой полировки или с `components.repolish`. */
#FormLabel, #DimLabel {{ color: {palette.text_dim}; }}
#AccentLabel {{ color: {palette.accent}; font-weight: 600; }}
#Hint {{ color: {palette.text_dim}; font-style: italic; }}
#CodePreview, #MonoEdit {{ font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt; }}
#CodePreview {{
    background: {palette.code}; border: 1px solid {palette.border}; border-radius: 4px;
    padding: 4px 6px;
}}
#Box {{ background: {palette.surface}; border: 1px solid {palette.border}; border-radius: 4px; }}
/* Представления внутри боксов — по именам, а не типовым потомком бокса: тот задел бы
   выпадающие списки QComboBox редакторов (решение заказчика 1). */
#KeyTree, #SelectedKeys, #ScenarioTree, #Steps {{ background: {palette.surface}; border: none; }}
#BoxTitle {{
    color: {palette.text_dim}; font-size: 9pt; font-weight: 600; padding: 6px 10px;
    border-bottom: 1px solid {palette.border};
}}
QLabel#Chip {{
    font-size: 8pt; padding: 0 6px; border: 1px solid {palette.border}; border-radius: 8px;
    color: {palette.text_dim};
}}
QLabel#Chip[level="error"] {{ border-color: {palette.problem}; color: {palette.problem}; }}
QLabel#Chip[level="warning"] {{ border-color: {palette.warning}; color: {palette.warning}; }}
/* Выноски (решение заказчика 2, 21.11.2026): полоса слева и слабый фон по уровню; текст
   ошибки — problem, предупреждения и сведения — обычный. */
QLabel#Callout {{
    padding: 5px 10px; border-left: 3px solid {palette.warning};
    background: {palette.warning_bg}; color: {palette.text};
}}
QLabel#Callout[level="error"] {{
    border-left-color: {palette.problem}; background: {palette.problem_bg};
    color: {palette.problem};
}}
QLabel#Callout[level="info"] {{ border-left-color: {palette.info}; background: {palette.info_bg}; }}
#DialogFooter {{ background: {palette.surface}; border-top: 1px solid {palette.border}; }}
#PanelHeader {{ background: {palette.surface}; border-bottom: 1px solid {palette.border}; }}
QListView#Steps::item:selected {{ border-left: 3px solid {palette.accent_fill}; }}
QTableView#OpsTable::item {{ border-bottom: 1px solid {palette.border}; }}
#BasesMode QRadioButton:checked:enabled {{ color: {palette.accent}; }}
QCheckBox#InlineCheck:enabled {{ color: {palette.text_dim}; }}
"""  # noqa: RUF001


def palette_for(mode: ThemeMode, system: ThemeMode) -> Palette:
    """Действующая палитра: явный выбор побеждает, AUTO следует за системой.

    `system` обязан быть LIGHT или DARK — «системный AUTO» не существует;
    неопределённость системы разрешает detect_system_mode до вызова.
    """
    effective = system if mode is ThemeMode.AUTO else mode
    return LIGHT if effective is ThemeMode.LIGHT else DARK
