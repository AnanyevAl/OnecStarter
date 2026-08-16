# План 4b — правки списка, витрина размещения, светлая тема

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** довести раздел «Базы» до полноценного рабочего места: правка списка и групп,
видимый вид размещения и путь подключения, светлая тема с переключателем,
привычные `F3`/`F4`, ярлыки на рабочем столе.

**Architecture:** расчёты без Qt уходят в `services` (`connection.py`, `settings.py`,
`order.py`) и покрываются табличными тестами; `ui` только рисует и ловит события.
Тема становится объектом-палитрой, передаваемой явно тем виджетам, которые
**запекают цвет в объект**; всё остальное красит общий stylesheet. Запись
в `ibases.v8i` идёт исключительно существующим циклом `write_patch` — новых способов
писать в файл не появляется, добавляется один вид патча.

**Tech Stack:** Python 3.13, PySide6 ≥ 6.10, pytest + pytest-qt, ruff, mypy --strict
(кроме `onecstarter.ui.*`), uv.

**Спека:** [2026-08-08-v1-plan4b-ui-edit-design.md](../specs/2026-08-08-v1-plan4b-ui-edit-design.md).
Ссылки вида «§2.4» ниже — на неё.

## Global Constraints

Требования проекта, действующие в **каждой** задаче. Повторно в задачах не дублируются.

- **Qt только в `src/onecstarter/ui/`.** Пакеты `domain`, `config`, `platform_1c`,
  `security`, `services` не импортируют `PySide6` ни прямо, ни транзитивно.
  Это проверяет существующий `tests/unit/test_no_qt_in_core.py` — он обязан
  оставаться зелёным.
- **Секреты — только через `security/`.** Ни в наших файлах, ни в логах, ни
  в сообщениях об ошибках, ни в буфере обмена, ни в ключах привязки.
- **Запись в пользовательские файлы — атомарная**, через существующие
  `config.atomic` и `services.writer.write_patch`. Своих `open(..., "w")`
  по путям пользователя не появляется.
- **Round-trip `.v8i` без потерь:** неизвестные ключи, порядок и кодировка исходного
  файла сохраняются. Проверяется существующими тестами `test_v8i_roundtrip.py`.
- **Процессы 1С в тестах не запускаются никогда.** `spawn` и `open_url`
  инжектируются фейками (см. `tests/ui/conftest.py`).
- **Факты о 1С — только с меткой.** `[Ф]` проверено экспериментом, `[Д]`
  из документации/не проверено, `[Р]` наше решение. Утверждение без метки
  в код и docs не идёт. Перед работой с форматами читать скилы
  `.claude/skills/v8i-format/` и `.claude/skills/platform-launch/`.
- **Мутационная проверка обязательна** для защитных тестов (перечень — §9 спеки).
  Порядок строгий: правка → тесты зелёные → **коммит** → мутация → откат.
  Откатывать мутацию через `git checkout -- <файл>` до коммита правки нельзя —
  откатится и правка (ловушка, стоившая сессии 07.08.2026 повтора работы).
- **Тексты интерфейса — по-русски**, без бренда 1С (`requirements.md`, §4).
- **Команды проверки:** `uv run pytest`, `uv run ruff check .`, `uv run mypy`.
  Все три обязаны быть чистыми перед коммитом задачи.
- **Базовая линия на входе в план:** 447 тестов зелёные, ruff и mypy чистые,
  `master` = `31f58a3`.

## Файловая структура

**Создаются:**

| Файл | Ответственность |
| --- | --- |
| `src/onecstarter/services/settings.py` | режим темы: чтение и запись `settings.json` |
| `src/onecstarter/services/connection.py` | витрина размещения: подпись вида и путь подключения |
| `src/onecstarter/services/order.py` | арифметика `OrderInList` при перестановке |
| `src/onecstarter/config/shell_link.py` | байты файла `.lnk` (MS-SHLLINK) |
| `src/onecstarter/ui/theme_controller.py` | владелец режима темы, применение и сохранение |
| `src/onecstarter/ui/settings_view.py` | раздел «Настройки» |
| `src/onecstarter/ui/bases/icons.py` | значки видов размещения, рисуются из палитры |
| `src/onecstarter/ui/bases/panel.py` | панель пути подключения под деревом |
| `src/onecstarter/ui/dialogs/infobase.py` | диалог записи: добавление и свойства |
| `src/onecstarter/ui/dialogs/group.py` | диалог группы: создание, переименование, перенос |
| `src/onecstarter/ui/dialogs/confirm.py` | подтверждения удаления записи и группы |

**Изменяются:**

| Файл | Что меняется |
| --- | --- |
| `src/onecstarter/ui/theme.py` | константы → `Palette`, `stylesheet(palette)`, цвета трея |
| `src/onecstarter/ui/tray.py` | иконка от палитры не зависит; подменю «Тема» |
| `src/onecstarter/ui/bases/tree_model.py` | палитра параметром, значки размещения |
| `src/onecstarter/ui/bases/view.py` | палитра, панель, `F3`/`F4`, меню операций, drag&drop |
| `src/onecstarter/ui/shell.py` | `QStackedWidget` и переключение разделов |
| `src/onecstarter/ui/app.py` | контроллер темы, путь `settings.json`, режим `--ib-name` |
| `src/onecstarter/__main__.py` | разбор `--ib-name` |
| `src/onecstarter/security/secrets.py` | `PPasswd`, `strip_url_credentials` |
| `src/onecstarter/services/edit.py` | `ReorderPatch` |
| `src/onecstarter/services/workspace.py` | `move_within_group`, `find_by_name` |

---

### Task 1: `ui/theme.py` — палитра вместо констант

Механическая замена: `DARK` повторяет значения 4a один в один, вид тёмной темы
не меняется. Тема ещё не переключается — появляется только структура (§2.1).

Две строки QSS всё же новые, и обе намеренные:

- `QMenu::item { padding: … }` — исправление дефекта показа, причина снята
  замерами 08.08.2026 (задача 6, шаг 1); правка живёт здесь, потому что задача
  и так переписывает `theme.py` целиком;
- `QLineEdit:read-only` — заготовка под панель пути подключения (задача 5),
  где поле именно read-only. Сегодня правило инертно: ни один виджет
  `setReadOnly` не вызывает. Держим его здесь, чтобы задача 5 не возвращалась
  в `theme.py` за одной строкой.

**Files:**
- Modify: `src/onecstarter/ui/theme.py`
- Modify: `src/onecstarter/ui/tray.py:17-28` (`make_icon`)
- Modify: `src/onecstarter/ui/bases/tree_model.py:23-74`
- Modify: `src/onecstarter/ui/bases/view.py:98-127` (`rebuild`)
- Modify: `src/onecstarter/ui/app.py:70`
- Test: `tests/ui/test_theme.py` (создать)

**Interfaces:**
- Produces:
  - `theme.Palette` — frozen dataclass, поля `background`, `surface`, `surface_raised`,
    `border`, `text`, `text_dim`, `accent`, `problem` (все `str`, hex-строки).
  - `theme.DARK: Palette`, `theme.LIGHT: Palette`.
  - `theme.TRAY_GROUND: str`, `theme.TRAY_MARK: str`.
  - `theme.stylesheet(palette: Palette) -> str`.
  - `tree_model.build_model(rows, cells, format_stamp, palette: Palette) -> QStandardItemModel`
    — палитра **последним позиционным** параметром.
  - `tray.make_icon() -> QIcon` — сигнатура не меняется, палитру не принимает.

- [x] **Step 1: Тест-страж значений тёмной палитры**

Создать `tests/ui/test_theme.py`:

```python
"""Палитры темы. Тёмная — страж: 4a не должен измениться ни на пиксель."""

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


def test_light_palette_differs_in_every_role() -> None:
    """Светлая — не тёмная с другим фоном: перекрашены все восемь ролей.

    Инверсией задача не решалась: #f2d54c на белом даёт 1,5:1, #e57373 — 3,0:1,
    #9a9a9a — 2,8:1 при пороге 4,5:1 (спека §2.2).
    """  # noqa: RUF002
    for field in ("background", "surface", "surface_raised", "border",
                  "text", "text_dim", "accent", "problem"):
        assert getattr(theme.LIGHT, field) != getattr(theme.DARK, field), field


def test_stylesheet_uses_given_palette() -> None:
    assert theme.DARK.background in theme.stylesheet(theme.DARK)
    assert theme.DARK.background not in theme.stylesheet(theme.LIGHT)
    assert theme.LIGHT.accent in theme.stylesheet(theme.LIGHT)
```

- [x] **Step 2: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/ui/test_theme.py -v`
Expected: FAIL — `AttributeError: module 'onecstarter.ui.theme' has no attribute 'DARK'`

- [x] **Step 3: Переписать `ui/theme.py`**

```python
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


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    surface_raised: str
    border: str
    text: str
    text_dim: str
    accent: str
    problem: str


DARK = Palette(
    background="#161616",
    surface="#1e1e1e",
    surface_raised="#262626",
    border="#333333",
    text="#e8e8e8",
    text_dim="#9a9a9a",
    accent="#f2d54c",
    problem="#e57373",
)

# Контрасты по WCAG 2.1 к худшему из трёх фонов палитры, порог 4,5:1:
# text 14,5:1, text_dim 4,8:1, accent 4,8:1, problem 4,7:1.
# Значения text_dim и accent исправлены 09.08.2026 (были #767676 и #8a6d00,
# подобранные только к белому фону) — разбор в §2.2 спеки и в разделе
# «Круг правок 3» этой задачи ниже.
LIGHT = Palette(
    background="#ffffff",
    surface="#f4f4f4",
    surface_raised="#eaeaea",
    border="#d0d0d0",
    text="#1a1a1a",
    text_dim="#666666",
    accent="#7d6200",
    problem="#c62828",
)

# Цвета иконки трея вне палитры намеренно: панель задач красится системной
# темой, а не нашей, и при явно выбранной (не «Авто») теме они расходятся.
# Тёмное поле с жёлтым треугольником читается и на светлой панели, и на тёмной;
# привязка к palette.surface дала бы в светлой теме 1,4:1 — значок пропал бы.
TRAY_GROUND = "#1e1e1e"
TRAY_MARK = "#f2d54c"


def stylesheet(palette: Palette) -> str:
    return f"""
QMainWindow, QDialog, QMessageBox {{ background: {palette.background}; }}
QWidget {{ color: {palette.text}; font-size: 10pt; }}
#NavRail {{ background: {palette.surface}; border-right: 1px solid {palette.border}; }}
#NavRail QToolButton {{ border: none; padding: 10px 12px; color: {palette.text_dim}; }}
#NavRail QToolButton:checked {{
    color: {palette.accent}; border-left: 2px solid {palette.accent};
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
   в светлой теме на surface_raised выходит светлое по светлому. См.
   правку в задаче 5, «Круг правок 2», и полный комментарий в самом
   theme.py — сюда, в план, весь текст эксперимента дублировать незачем. */
QTreeView::item:selected {{ background: {palette.surface_raised}; color: {palette.text}; }}
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
"""
```

- [x] **Step 4: Провести палитру через `tree_model`**

В `src/onecstarter/ui/bases/tree_model.py` заменить импорт `theme` на приём
палитры параметром:

```python
from onecstarter.ui.theme import Palette


def build_model(
    rows: Sequence[Row],
    cells: Mapping[str, VersionCell],
    format_stamp: Callable[[datetime], str],
    palette: Palette,
) -> QStandardItemModel:
    model = QStandardItemModel(0, len(COLUMNS))
    model.setHorizontalHeaderLabels(list(COLUMNS))
    for row in rows:
        model.appendRow(_items_for(row, cells, format_stamp, palette))
    return model
```

`_items_for` получает `palette` последним параметром, `theme.TEXT_DIM` становится
`palette.text_dim`, `theme.PROBLEM` — `palette.problem`, рекурсивный вызов для
`row.children` передаёт `palette` дальше.

- [x] **Step 5: Обновить остальные три места вызова**

`src/onecstarter/ui/bases/view.py` — конструктор принимает палитру, `rebuild`
её передаёт:

```python
        parent: QWidget | None = None,
        palette: Palette = theme.DARK,   # <- новый параметр, последний
    ) -> None:
        # … существующее тело __init__ без изменений, до строки self._rows …
        self._palette = palette          # <- новая строка рядом с self._rows
```

Значение по умолчанию `theme.DARK` — чтобы существующие тесты 4a, строящие
`BasesView(...)` без палитры, остались зелёными: задача 1 вида не меняет.

```python
        model = build_model(self._rows, cells, _format_stamp, self._palette)
```

`src/onecstarter/ui/app.py:70`:

```python
    application.setStyleSheet(theme.stylesheet(theme.DARK))
```

`src/onecstarter/ui/tray.py` — `make_icon` перестаёт зависеть от палитры:

```python
def make_icon() -> QIcon:
    """Иконка трея: жёлтый треугольник запуска на тёмном поле.

    От палитры приложения не зависит намеренно (спека 4b, §2.4): панель задач
    красится системной темой, а не нашей.
    """  # noqa: RUF002
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(theme.TRAY_GROUND))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(theme.TRAY_MARK))
    # … остальное тело make_icon без изменений: setPen(NoPen), drawPolygon,
    # painter.end(), return QIcon(pixmap) …
```

- [x] **Step 6: Прогон**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS — 447 прежних тестов + 3 новых = 450. Вид приложения не изменился.

- [x] **Step 7: Коммит**

```bash
git add src/onecstarter/ui tests/ui/test_theme.py
git commit -m "refactor: тема становится палитрой-объектом, вид не меняется"
```

**Правка smoke №1 (08.08.2026), замечание 1.** Ручной прогон на машине
заказчика после задачи 7 нашёл: выделенная строка дерева нечитаема
в светлой теме — правило `QTreeView::item:selected` из листинга шага 3
выше задавало только `background`, без `color`. Находка разнесена
по правилу проекта: сама правка (`QTreeView::item:selected` с явным
`color: {palette.text}`, листинг шага 3 выше уже приведён к новому виду)
и её тест — в задаче 5, «Круг правок 2» (коммит `064940f`); здесь, в файле,
который правка меняет, — только пометка, чтобы читающий план не
наткнулся на устаревший листинг без объяснения. Перечень всех находок
smoke №1 и то, куда что ушло, — в разделе «Замечания ручного smoke №1
(08.08.2026)» после контрольной точки в задаче 7.

## Круг правок 3 (контраст светлой палитры, 09.08.2026)

Наследство сессии 09.08.2026: тест `test_text_roles_meet_the_contrast_threshold`
(коммит `c2886db`) мерил контраст только к `background` — так же, как §2.2
дизайна, чью колонку «Контраст к `#ffffff`» он воспроизводил. В его докстринге
остался открытый вопрос: `text_dim` на `surface_raised` даёт 3,78:1, дефект это
или допустимое исключение — не проверено.

**Что оказалось.** Вопрос был поставлен не на том месте, и ответ на него —
«не дефект», а настоящий дефект рядом.

1. **Выделенная строка чиста.** Замер (offscreen `grab()` + сэмплинг пикселей,
   все четыре стиля Qt: `windows11`, `windowsvista`, `Windows`, `Fusion`)
   показал: без выделения кисть элемента применяется точно — приходят ровно
   `#767676` и `#c62828`; с выделением во всех четырёх стилях приходит `text`.
   Правило `QTreeView::item:selected { color: {palette.text} }` побеждает
   `Qt::ForegroundRole`, приглушённый цвет на выделение не попадает вовсе.
   Контраст выделенной строки — 14,5:1. Сторожить нечего, и в тест этот случай
   не добавлен (объяснение — в докстринге теста).

2. **Дефект в другом: у `text_dim` и `accent` не было запаса.** Оба подбирались
   к белому впритык (4,54:1 и 4,92:1), а рисуются не только на нём. Замер
   настоящих пикселей светлой темы: подпись раздела `NavRail` — `#767676`
   на `#f4f4f4`, то есть **4,13:1**; то же у заголовка таблицы и поля только
   для чтения. У `accent` на том же `surface` — **4,47:1** (активная кнопка
   раздела, выделенный пункт меню). Порог 4,5:1 не держали три места показа
   из стилевой таблицы, и ни одно из них тестом не покрывалось.

3. **Правка.** `text_dim` `#767676` → `#666666` (худший фон: 3,78 → **4,77**),
   `accent` `#8a6d00` → `#7d6200` (4,09 → **4,82**). Взяты не первые проходящие
   значения (`#696969` даёт 4,56, `#826600` — 4,53), а с запасом: дефект и
   состоял в том, что цвет стоял ровно на пороге. Тёмная палитра порог держит
   на всех трёх фонах (худшее — 5,07:1) и не тронута; `test_dark_palette_
   repeats_4a_constants` это подтверждает.

4. **Тест.** `test_text_roles_meet_the_contrast_threshold` параметризован
   по трём фонам: 2 палитры × 4 роли × 3 фона = 24 случая вместо 8. Правило
   намеренно шире употребления (`problem` на `surface` нигде не рисуется) —
   дефект родился ровно оттого, что проверка была уже употребления.

**Мутационная проверка (обязательна — тест защитный).** Проведена после коммита
правки `93d4778`, откат каждой мутации — `git checkout --` по уже
закоммиченному файлу.

**Мутация 1.** `text_dim` → `#767676`, ровно то значение, что стояло до правки.
Падают `[light-text_dim-surface]` и `[light-text_dim-surface_raised]`,
`[light-text_dim-background]` остаётся **зелёным**. Это главный результат
проверки: старый однофоновый тест держал дефект зелёным, новый его ловит.

**Мутация 2.** `accent` → `#8a6d00`, значение до правки. Падают
`[light-accent-surface]` и `[light-accent-surface_raised]`,
`[light-accent-background]` зелёный. Та же картина.

**Мутация 3.** `text_dim` → `#6f6f6f` — значение, проходящее порог к `background`
(5,02:1) **и** к `surface` (4,57:1), но не к `surface_raised` (4,18:1). Падает
ровно один случай: `[light-text_dim-surface_raised]`. Проверка тому, что третий
фон не довесок к двум первым, а несёт свой вес: тест из двух фонов эту правку
пропустил бы.

Факт: подтверждено, все три мутации пойманы; отменены, повторный полный прогон
после отката — 841 из 841 зелёных, `git status` чист.

---

### Task 2: `services/settings.py` — режим темы на диске

Чистый слой без Qt (§2.3). Политика отказов **намеренно мягче**, чем у `bases.json`.

**Files:**
- Create: `src/onecstarter/services/settings.py`
- Test: `tests/unit/test_settings.py` (создать)

**Interfaces:**
- Consumes: `config.atomic.atomic_write` (существует).
- Produces:
  - `settings.ThemeMode` — `Enum` со значениями `AUTO = "auto"`, `LIGHT = "light"`,
    `DARK = "dark"`.
  - `settings.Settings` — frozen dataclass, поле `theme: ThemeMode = ThemeMode.AUTO`.
  - `settings.SCHEMA_VERSION: int = 1`.
  - `settings.load_settings(path: Path) -> Settings` — **никогда не поднимает
    исключений**.
  - `settings.save_settings(path: Path, settings: Settings) -> None` — поднимает
    `OSError`, если записать не вышло. Гасит его вызывающий (задача 3).

- [x] **Step 1: Тесты**

Создать `tests/unit/test_settings.py`:

```python
"""Настройки приложения: чтение и запись settings.json."""

import json
from pathlib import Path

import pytest

from onecstarter.services.settings import (
    SCHEMA_VERSION,
    Settings,
    ThemeMode,
    load_settings,
    save_settings,
)


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "settings.json") == Settings(theme=ThemeMode.AUTO)


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.LIGHT))
    assert load_settings(path) == Settings(theme=ThemeMode.LIGHT)


def test_schema_is_written(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.DARK))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"schema": SCHEMA_VERSION, "theme": "dark"}


def test_unknown_theme_value_falls_back_to_auto(tmp_path: Path) -> None:
    """Совместимость вперёд: незнакомое значение — не порча файла.

    Более новая версия могла записать режим, которого мы не знаем. Уносить
    за это весь файл в .bad значило бы терять настройки при откате версии.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "theme": "solarized"}), encoding="utf-8")
    assert load_settings(path).theme is ThemeMode.AUTO
    assert not path.with_name("settings.json.bad").exists()


def test_corrupt_file_moves_aside_and_starts_clean(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{не json", encoding="utf-8")
    assert load_settings(path) == Settings()
    assert path.with_name("settings.json.bad").read_text(encoding="utf-8") == "{не json"


def test_unreadable_file_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настройки не смеют мешать старту — в отличие от bases.json.

    У load_user_data недоступный файл поднимает UserDataUnavailableError:
    подмена пустыми данными затёрла бы историю запусков. Здесь цена ошибки
    другая — теряется выбор темы, — и падать из-за неё приложению нельзя.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "theme": "light"}), encoding="utf-8")

    original = Path.read_text

    def refuse(self: Path, **kwargs: object) -> str:
        if self == path:
            raise PermissionError(13, "занят другим процессом")
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", refuse)
    assert load_settings(path) == Settings(theme=ThemeMode.AUTO)


def test_save_reports_failure(tmp_path: Path) -> None:
    """Отказ записи виден вызывающему: тему покажем, но соврать «запомнили» нельзя."""  # noqa: RUF002
    # Каталог занят файлом — создать settings.json внутри него невозможно.
    blocked = tmp_path / "busy"
    blocked.write_text("", encoding="utf-8")
    with pytest.raises(OSError):
        save_settings(blocked / "settings.json", Settings())
```

- [x] **Step 2: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.settings'`

- [x] **Step 3: Реализация**

```python
"""Настройки приложения. Сегодня — только режим темы.

Файл %APPDATA%\\OneCStarter\\settings.json, отдельный от bases.json намеренно:
тот при порче уезжает в .bad вместе со всем содержимым, и настройка темы
уехала бы с историей запусков, будучи ни при чём. Разные времена жизни
и разная частота записи — разные файлы.

Политика отказов мягче, чем у наших данных о базах: работа с settings.json
никогда не мешает работе программы. Нечитаемый или испорченный файл даёт
значения по умолчанию, незнакомое значение режима — AUTO. Ошибку записи
модуль не гасит: показать её обязан слой представления, иначе пользователь
решит, что выбор запомнен.
"""  # noqa: RUF002

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write

SCHEMA_VERSION = 1

__all__ = [
    "SCHEMA_VERSION",
    "Settings",
    "ThemeMode",
    "load_settings",
    "save_settings",
]


class ThemeMode(Enum):
    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Settings:
    theme: ThemeMode = ThemeMode.AUTO


def load_settings(path: Path) -> Settings:
    """Прочитать настройки. Никогда не поднимает исключений."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings()
    except (OSError, UnicodeDecodeError):
        # Недоступен или не в UTF-8. В отличие от bases.json падать нельзя:
        # цена ошибки — забытый выбор темы, а не затёртая история запусков.
        return Settings()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
    except (ValueError, TypeError):
        _move_aside(path)
        return Settings()
    return Settings(theme=_theme_of(payload.get("theme")))


def save_settings(path: Path, settings: Settings) -> None:
    """Записать настройки атомарно. `OSError` наружу — гасит вызывающий."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA_VERSION, "theme": settings.theme.value}
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, text.encode("utf-8"))


def _theme_of(value: Any) -> ThemeMode:
    """Незнакомое значение — не порча: более новая версия могла записать свой режим."""  # noqa: RUF002
    try:
        return ThemeMode(value)
    except ValueError:
        return ThemeMode.AUTO


def _move_aside(path: Path) -> None:
    """Убрать испорченный файл. Не вышло — и ладно: перезапишем поверх."""
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError:
        return
```

- [x] **Step 4: Прогон**

Run: `uv run pytest tests/unit/test_settings.py -v && uv run ruff check . && uv run mypy`
Expected: PASS — 7 тестов.

- [x] **Step 5: Коммит**

```bash
git add src/onecstarter/services/settings.py tests/unit/test_settings.py
git commit -m "feat: настройки приложения в отдельном settings.json"
```

- [x] **Step 6: Мутационная проверка**

Защитный тест здесь один: `test_unreadable_file_does_not_raise` держит решение
«настройки не мешают работе». Мутация: убрать `OSError` из перехвата в
`load_settings` (оставить только `FileNotFoundError` и `UnicodeDecodeError`).

Ожидание: тест падает с `PermissionError`. Записать факт в этот шаг, откатить
мутацию (`git checkout -- src/onecstarter/services/settings.py` — правка уже
закоммичена шагом 5, откат безопасен).

Факт: подтверждено. Убран `OSError` из `except (OSError, UnicodeDecodeError)` в
`load_settings` (оставлен только `UnicodeDecodeError`). Прогон
`uv run pytest tests/unit/test_settings.py -v`: 6 из 7 тестов прошли,
`test_unreadable_file_does_not_raise` упал — `PermissionError: [Errno 13]`
пробросился наружу из `path.read_text(...)` необработанным, что и ожидалось.
Мутация откачена через `git checkout -- src/onecstarter/services/settings.py`,
`git status` после отката — чистый, повторный прогон — 7 из 7 зелёных.

---

### Task 3: `ThemeController`, раздел «Настройки», подменю трея

Переключение темы работает end-to-end (§2.4, §2.5). Четыре коммита внутри задачи —
контроллер, разделы окна, раздел настроек, трей.

**Files:**
- Create: `src/onecstarter/ui/theme_controller.py`
- Create: `src/onecstarter/ui/settings_view.py`
- Modify: `src/onecstarter/ui/theme.py` (добавить `palette_for`)
- Modify: `src/onecstarter/ui/shell.py`
- Modify: `src/onecstarter/ui/tray.py`
- Modify: `src/onecstarter/ui/app.py`
- Modify: `src/onecstarter/ui/bases/view.py` (метод `apply_palette`)
- Test: `tests/ui/test_theme_controller.py` (создать)
- Test: `tests/ui/test_settings_view.py` (создать)
- Test: `tests/ui/test_shell.py` (дополнить)
- Test: `tests/ui/test_tray.py` (дополнить)

**Interfaces:**
- Consumes: `settings.ThemeMode`, `settings.Settings`, `settings.load_settings`,
  `settings.save_settings` (задача 2); `theme.Palette`, `theme.DARK`, `theme.LIGHT`,
  `theme.stylesheet` (задача 1).
- Produces:
  - `theme.palette_for(mode: ThemeMode, system: ThemeMode) -> Palette` — чистая.
  - `theme_controller.detect_system_mode() -> ThemeMode` — `LIGHT` или `DARK`,
    никогда `AUTO`.
  - `theme_controller.ThemeController(QObject)` с сигналом `changed = Signal()`,
    свойствами `mode: ThemeMode`, `palette: Palette`, `last_save_error: str | None`
    и методами `set_mode(mode: ThemeMode) -> None`, `refresh_system() -> None`.
  - `settings_view.SettingsView(QWidget)` с методом `apply_palette(palette) -> None`.
  - `shell.MainWindow(sections: Sequence[tuple[str, QWidget]])` — **сигнатура
    конструктора меняется**: вместо одного виджета список пар «подпись, виджет».
  - `bases.view.BasesView.apply_palette(palette: Palette) -> None`.
  - `tray.create_tray(...)` получает два новых обязательных параметра:
    `theme_mode: Callable[[], ThemeMode]` и `on_theme: Callable[[ThemeMode], None]`.

- [x] **Step 1: Тест чистого выбора палитры**

Дополнить `tests/ui/test_theme.py`:

```python
import pytest

from onecstarter.services.settings import ThemeMode


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
```

- [x] **Step 2: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/ui/test_theme.py -v`
Expected: FAIL — `AttributeError: module 'onecstarter.ui.theme' has no attribute 'palette_for'`

- [x] **Step 3: Реализовать `palette_for`**

В конец `src/onecstarter/ui/theme.py`:

```python
def palette_for(mode: ThemeMode, system: ThemeMode) -> Palette:
    """Действующая палитра: явный выбор побеждает, AUTO следует за системой.

    `system` обязан быть LIGHT или DARK — «системный AUTO» не существует;
    неопределённость системы разрешает detect_system_mode до вызова.
    """  # noqa: RUF002
    effective = system if mode is ThemeMode.AUTO else mode
    return LIGHT if effective is ThemeMode.LIGHT else DARK
```

Импорт вверху файла: `from onecstarter.services.settings import ThemeMode`.

- [x] **Step 4: Тесты контроллера**

Создать `tests/ui/test_theme_controller.py`:

```python
"""Контроллер темы: применение, сохранение, следование системе."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import Settings, ThemeMode, save_settings
from onecstarter.ui import theme
from onecstarter.ui.theme_controller import ThemeController


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def _controller(
    application: QApplication, path: Path, system: ThemeMode = ThemeMode.DARK
) -> ThemeController:
    return ThemeController(application, path, system_mode=lambda: system)


def test_starts_from_saved_mode(application: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.LIGHT))
    controller = _controller(application, path)
    assert controller.mode is ThemeMode.LIGHT
    assert controller.palette is theme.LIGHT


def test_auto_follows_system(application: QApplication, tmp_path: Path) -> None:
    controller = _controller(application, tmp_path / "s.json", system=ThemeMode.LIGHT)
    assert controller.mode is ThemeMode.AUTO
    assert controller.palette is theme.LIGHT


def test_set_mode_applies_stylesheet_and_persists(
    application: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "settings.json"
    controller = _controller(application, path)
    seen: list[int] = []
    controller.changed.connect(lambda: seen.append(1))

    controller.set_mode(ThemeMode.LIGHT)

    assert controller.palette is theme.LIGHT
    assert theme.LIGHT.accent in application.styleSheet()
    assert path.exists()
    assert seen == [1]


def test_refresh_system_repaints_only_in_auto(
    application: QApplication, tmp_path: Path
) -> None:
    """В AUTO смена системной темы меняет палитру; при явном выборе — нет."""
    current = {"mode": ThemeMode.DARK}
    controller = ThemeController(
        application, tmp_path / "s.json", system_mode=lambda: current["mode"]
    )
    current["mode"] = ThemeMode.LIGHT
    controller.refresh_system()
    assert controller.palette is theme.LIGHT

    controller.set_mode(ThemeMode.DARK)
    current["mode"] = ThemeMode.LIGHT
    controller.refresh_system()
    assert controller.palette is theme.DARK


def test_save_failure_is_reported_not_raised(
    application: QApplication, tmp_path: Path
) -> None:
    """Тема применяется, но приложение честно говорит, что не запомнило её.

    Молча проглотить отказ нельзя: пользователь решит, что выбор сохранён,
    и удивится при следующем запуске.
    """  # noqa: RUF002
    blocked = tmp_path / "busy"
    blocked.write_text("", encoding="utf-8")
    controller = _controller(application, blocked / "settings.json")

    controller.set_mode(ThemeMode.LIGHT)

    assert controller.palette is theme.LIGHT
    assert controller.last_save_error is not None
    assert "settings.json" in controller.last_save_error
```

- [x] **Step 5: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/ui/test_theme_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.ui.theme_controller'`

- [x] **Step 6: Реализовать контроллер**

Создать `src/onecstarter/ui/theme_controller.py`:

```python
"""Владелец режима темы: применение, сохранение, следование системе.

О виджетах контроллер не знает: он применяет общий stylesheet и сообщает
сигналом `changed`. Кто из виджетов запекает цвет в объект и обязан
перерисоваться — решает сборка приложения (ui/app.py). Иначе контроллер
пришлось бы учить про BasesView, и его нельзя было бы проверить без окна.
"""  # noqa: RUF002

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import (
    Settings,
    ThemeMode,
    load_settings,
    save_settings,
)
from onecstarter.ui import theme


def detect_system_mode() -> ThemeMode:
    """Системная тема Windows глазами Qt. Возвращает LIGHT или DARK, но не AUTO.

    **[Д] не проверено на нашей сборке.** `QStyleHints.colorScheme()` и сигнал
    `colorSchemeChanged` — из документации Qt 6.5+. Их наличие в PySide6 6.10
    проверяется шагом 7 этой задачи; при отсутствии — запасной путь через
    реестр `AppsUseLightTheme`, и тогда «Авто» применяется только при старте.

    `ColorScheme.Unknown` даёт тёмную — поведение 4a, менять его молча нельзя.
    """  # noqa: RUF002
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme()
    return ThemeMode.LIGHT if scheme == Qt.ColorScheme.Light else ThemeMode.DARK


class ThemeController(QObject):
    changed = Signal()

    def __init__(
        self,
        application: QApplication,
        path: Path,
        *,
        system_mode: Callable[[], ThemeMode] = detect_system_mode,
    ) -> None:
        super().__init__(application)
        self._application = application
        self._path = path
        self._system_mode = system_mode
        self._mode = load_settings(path).theme
        self._palette = theme.palette_for(self._mode, self._system_mode())
        self.last_save_error: str | None = None
        self._apply()

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def palette(self) -> theme.Palette:
        return self._palette

    def set_mode(self, mode: ThemeMode) -> None:
        self._mode = mode
        try:
            save_settings(self._path, Settings(theme=mode))
            self.last_save_error = None
        except OSError as error:
            # Тема применяется всё равно: пользователь её выбрал. Но соврать
            # «запомнили» нельзя — раздел «Настройки» покажет причину.
            self.last_save_error = f"Не удалось сохранить {self._path}: {error}"  # noqa: RUF001
        self._repaint()

    def refresh_system(self) -> None:
        """Системная тема сменилась. При явно выбранной теме — ничего не делаем."""
        if self._mode is ThemeMode.AUTO:
            self._repaint()

    def _repaint(self) -> None:
        self._palette = theme.palette_for(self._mode, self._system_mode())
        self._apply()
        self.changed.emit()

    def _apply(self) -> None:
        self._application.setStyleSheet(theme.stylesheet(self._palette))
```

- [x] **Step 7: Проверить [Д]-допущение о `colorScheme` — до правки `app.py`**

Допущение снимается замером, а не верой (`CLAUDE.md`: не выдавать догадку за факт).

**Мерить на настоящей платформе, не под offscreen.** Первая редакция этого шага
форсировала `QT_QPA_PLATFORM=offscreen` — это была ошибка плана: «Авто» обязано
работать там, где приложение живёт, а offscreen-платформа системную тему не знает
и всегда отвечает `Unknown`.

Run:

```bash
uv run python -c "import sys; from PySide6.QtWidgets import QApplication; from PySide6.QtGui import QGuiApplication; import winreg; a=QApplication(sys.argv); h=QGuiApplication.styleHints(); print('platform:', a.platformName()); print('colorScheme:', h.colorScheme()); print('signal:', hasattr(h,'colorSchemeChanged')); k=winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'); print('AppsUseLightTheme:', winreg.QueryValueEx(k,'AppsUseLightTheme')[0])"
```

Реестр здесь — контрольная величина: он показывает, что Qt отвечает не наугад.

**[Ф] 08.08.2026, PySide6 6.11.1, машина заказчика:**

| Платформа | `colorScheme()` | `AppsUseLightTheme` |
| --- | --- | --- |
| `windows` (настоящая) | `ColorScheme.Dark` | `0` — тёмная |
| `offscreen` | `ColorScheme.Unknown` | — |

Атрибут и сигнал `colorSchemeChanged` в сборке есть, ответ на настоящей платформе
совпадает с реестром. Запасной путь через реестр не понадобился, сигнал подключается
в шаге 13. Докстринг `detect_system_mode` помечен `[Ф]` с датой.

**Следствие для тестов, важное:** под offscreen `colorScheme()` всегда `Unknown`,
то есть `detect_system_mode()` в тестах всегда вернул бы `DARK`. Именно поэтому
`ThemeController` принимает `system_mode` параметром — тест, полагающийся
на настоящее определение, был бы зелёным по совпадению.

Если бы атрибута не оказалось — тело `detect_system_mode` заменяется на чтение
реестра, сигнал в шаге 13 не подключается, пометка `[Д]` меняется на `[Ф]`
с датой замера в обоих случаях.

- [x] **Step 8: Прогон и коммит контроллера**

Run: `uv run pytest tests/ui/test_theme_controller.py tests/ui/test_theme.py -v`
Expected: PASS — 5 тестов контроллера + 4 палитры.

```bash
git add src/onecstarter/ui/theme.py src/onecstarter/ui/theme_controller.py tests/ui/test_theme.py tests/ui/test_theme_controller.py
git commit -m "feat: контроллер темы — режим, применение, сохранение"
```

- [x] **Step 9: Тест разделов окна**

Дополнить `tests/ui/test_shell.py`:

```python
def test_window_switches_sections(qtbot) -> None:
    """Панель навигации переключает разделы; активна ровно одна кнопка."""
    first, second = QLabel("Базы"), QLabel("Настройки")
    window = MainWindow([("Базы", first), ("Настройки", second)])
    qtbot.addWidget(window)

    assert window.current_section() is first
    window.show_section(1)
    assert window.current_section() is second
    assert [button.isChecked() for button in window.section_buttons()] == [False, True]
```

Импорт `QLabel` — из `PySide6.QtWidgets`.

- [x] **Step 10: Реализовать разделы в `ui/shell.py`**

```python
class MainWindow(QMainWindow):
    """Главное окно: узкая навигация разделов + текущий раздел.

    Разделы приходят списком пар «подпись, виджет». Последний по списку
    визуально отделён снизу — туда идут «Настройки» (спека 4b, §2.5):
    раздел-обслуживание не должен стоять в одном ряду с разделами-по-делу.
    """  # noqa: RUF002

    def __init__(
        self,
        sections: Sequence[tuple[str, QWidget]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OneCStarter")
        self.resize(900, 600)
        self.close_to_tray = False
        self._stack = QStackedWidget()
        self._buttons: list[QToolButton] = []
        group = QButtonGroup(self)
        group.setExclusive(True)

        rail = QFrame()
        rail.setObjectName("NavRail")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 8, 0, 8)
        for index, (label, widget) in enumerate(sections):
            if index == len(sections) - 1 and len(sections) > 1:
                rail_layout.addStretch(1)
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked=False, i=index: self.show_section(i))
            group.addButton(button)
            rail_layout.addWidget(button)
            self._buttons.append(button)
            self._stack.addWidget(widget)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(rail)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

    def section_buttons(self) -> list[QToolButton]:
        return list(self._buttons)

    def current_section(self) -> QWidget:
        return self._stack.currentWidget()

    def show_section(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._buttons[index].setChecked(True)
```

`show_and_focus_search` берёт `focus_search` у **текущего** раздела:

```python
        focus = getattr(self._stack.currentWidget(), "focus_search", None)
```

`closeEvent` не меняется. Импорты пополняются
`QButtonGroup` (из `PySide6.QtGui`), `QStackedWidget`, `Sequence` из
`collections.abc`.

- [x] **Step 11: Прогон и коммит разделов**

Run: `uv run pytest tests/ui -v`
Expected: PASS. Существующие тесты `test_shell.py` и `test_app.py`, строившие
`MainWindow(view)`, обновить на `MainWindow([("Базы", view)])`.

```bash
git add src/onecstarter/ui/shell.py tests/ui/test_shell.py tests/ui/test_app.py
git commit -m "feat: окно держит несколько разделов с переключением"
```

- [x] **Step 12: Раздел «Настройки» — тест и реализация**

Создать `tests/ui/test_settings_view.py`:

```python
"""Раздел «Настройки»: выбор темы и честное сообщение об отказе записи."""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from onecstarter.services.settings import ThemeMode
from onecstarter.ui.settings_view import SettingsView
from onecstarter.ui.theme_controller import ThemeController


def _view(qtbot, application: QApplication, path: Path) -> tuple[SettingsView, ThemeController]:
    controller = ThemeController(application, path, system_mode=lambda: ThemeMode.DARK)
    view = SettingsView(controller)
    qtbot.addWidget(view)
    return view, controller


def test_three_choices_with_current_selected(qtbot, qapp, tmp_path: Path) -> None:
    view, _ = _view(qtbot, qapp, tmp_path / "s.json")
    assert [button.text() for button in view.theme_buttons()] == [
        "Авто (как в Windows)",
        "Светлая",
        "Тёмная",
    ]
    assert view.theme_buttons()[0].isChecked()


def test_choice_switches_theme(qtbot, qapp, tmp_path: Path) -> None:
    view, controller = _view(qtbot, qapp, tmp_path / "s.json")
    view.theme_buttons()[1].click()
    assert controller.mode is ThemeMode.LIGHT


def test_save_failure_is_visible(qtbot, qapp, tmp_path: Path) -> None:
    """Отказ записи виден в разделе, а не только в поле контроллера."""
    blocked = tmp_path / "busy"
    blocked.write_text("", encoding="utf-8")
    view, _ = _view(qtbot, qapp, blocked / "settings.json")
    view.theme_buttons()[1].click()
    assert "не удалось сохранить" in view.status_text().casefold()
```

Создать `src/onecstarter/ui/settings_view.py`:

```python
"""Раздел «Настройки». В v1 параметр один — тема.

Раздел тонкий намеренно: он каркас под v2, а не витрина. Глобальный хоткей
и «закрывать окно в трей» сюда не идут — обе настройки требуют своих решений
(перехват занятого сочетания, поведение без трея) и к теме отношения не имеют
(спека 4b, §2.5 и §12).
"""  # noqa: RUF002

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services.settings import ThemeMode
from onecstarter.ui.theme import Palette
from onecstarter.ui.theme_controller import ThemeController

CHOICES = (
    (ThemeMode.AUTO, "Авто (как в Windows)"),
    (ThemeMode.LIGHT, "Светлая"),
    (ThemeMode.DARK, "Тёмная"),
)


class SettingsView(QWidget):
    def __init__(self, controller: ThemeController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._buttons: list[QRadioButton] = []

        box = QGroupBox("Тема оформления")
        box_layout = QVBoxLayout(box)
        for mode, label in CHOICES:
            button = QRadioButton(label)
            button.setChecked(mode is controller.mode)
            button.clicked.connect(lambda _checked=False, m=mode: self._choose(m))
            box_layout.addWidget(button)
            self._buttons.append(button)

        self._status = QLabel("")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(box)
        layout.addWidget(self._status)
        layout.addStretch(1)

        controller.changed.connect(self._sync)

    def theme_buttons(self) -> list[QRadioButton]:
        return list(self._buttons)

    def status_text(self) -> str:
        return self._status.text()

    def apply_palette(self, palette: Palette) -> None:
        """Своих запечённых цветов у раздела нет — метод есть ради единого вызова."""
        del palette

    def _choose(self, mode: ThemeMode) -> None:
        self._controller.set_mode(mode)

    def _sync(self) -> None:
        for button, (mode, _label) in zip(self._buttons, CHOICES, strict=True):
            button.setChecked(mode is self._controller.mode)
        self._status.setText(self._controller.last_save_error or "")
```

Run: `uv run pytest tests/ui/test_settings_view.py -v` — сначала FAIL
(`ModuleNotFoundError`), после создания файла PASS (3 теста).

```bash
git add src/onecstarter/ui/settings_view.py tests/ui/test_settings_view.py
git commit -m "feat: раздел «Настройки» с выбором темы"
```

- [x] **Step 13: Подменю трея и сборка в `app.py`**

Дополнить `tests/ui/test_tray.py`:

```python
def test_menu_has_theme_submenu_with_current_checked() -> None:
    menu = QMenu()
    populate_tray_menu(
        menu, [], lambda: None, lambda key: None, lambda: None,
        theme_mode=lambda: ThemeMode.LIGHT, on_theme=lambda mode: None,
    )
    submenu = next(
        action.menu() for action in menu.actions() if action.text() == "Тема"
    )
    checked = [action.text() for action in submenu.actions() if action.isChecked()]
    assert checked == ["Светлая"]
```

В `src/onecstarter/ui/tray.py` — `populate_tray_menu` и `create_tray` получают
`theme_mode: Callable[[], ThemeMode]` и `on_theme: Callable[[ThemeMode], None]`,
между избранным и «Выход» добавляется:

```python
    menu.addSeparator()
    submenu = menu.addMenu("Тема")
    current = theme_mode()
    for mode, label in CHOICES:
        action = submenu.addAction(label, lambda checked=False, m=mode: on_theme(m))
        action.setCheckable(True)
        action.setChecked(mode is current)
```

`CHOICES` импортируется из `onecstarter.ui.settings_view` — один список подписей
на обе точки входа, иначе они разойдутся текстом.

В `src/onecstarter/ui/app.py`:

```python
    controller = ThemeController(application, paths_settings)
    view = BasesView(..., palette=controller.palette)
    settings_view = SettingsView(controller)
    window = MainWindow([("Базы", view), ("Настройки", settings_view)])

    def on_theme_changed() -> None:
        view.apply_palette(controller.palette)

    controller.changed.connect(on_theme_changed)
    QGuiApplication.styleHints().colorSchemeChanged.connect(
        lambda _scheme: controller.refresh_system()
    )
```

где `paths_settings = appdata / "OneCStarter" / "settings.json"` собирается
в `build_runtime` рядом с `bases.json` и возвращается полем `Runtime.settings`.

`create_tray` получает `theme_mode=lambda: controller.mode` и
`on_theme=controller.set_mode`.

`BasesView.apply_palette`:

```python
    def apply_palette(self, palette: Palette) -> None:
        """Сменить палитру и перерисовать: цвета запечены в QBrush и в значки."""
        self._palette = palette
        self.rebuild()
```

- [x] **Step 14: Прогон, коммит, мутационная проверка**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS.

```bash
git add src/onecstarter/ui tests/ui
git commit -m "feat: переключение темы из раздела «Настройки» и из трея"
```

Мутационная проверка защитного теста «после смены темы не осталось цветов
прежней палитры» переносится в задачу 5 — там появляются значки, и обход модели
проверяет обе запечённые точки сразу. Здесь мутируется
`test_save_failure_is_reported_not_raised`: убрать присваивание
`self.last_save_error` в ветке `except OSError`.

Ожидание: тест падает на `assert controller.last_save_error is not None`.

Факт: подтверждено. После коммита правки убрано присваивание `self.last_save_error`
в ветке `except OSError` (`theme_controller.py`). `test_save_failure_is_reported_not_raised`
упал именно на `assert controller.last_save_error is not None` (`None is not None`).
Заодно упал и `test_save_failure_is_visible` в `test_settings_view.py` (пустая строка вместо
сообщения об ошибке) — тот же дефект виден и на уровне раздела «Настройки». Мутация отменена
правкой обратно (не через `git checkout --`), `git diff` после отката пуст, полный прогон
(`pytest`, `ruff check .`, `mypy`) снова зелёный.

---

### Task 4: `services/connection.py` и `strip_url_credentials`

Чистый расчёт витрины размещения (§1.1–§1.2). Qt здесь нет, рисование — задача 5.

**Files:**
- Create: `src/onecstarter/services/connection.py`
- Modify: `src/onecstarter/security/secrets.py`
- Test: `tests/unit/test_connection.py` (создать)
- Test: `tests/unit/test_secrets.py` (создать, если нет — иначе дополнить)

**Interfaces:**
- Consumes: `domain.connect.ConnectKind`, `parse_connect`, `find_fragment`;
  `services.model.InfobaseItem`.
- Produces:
  - `security.secrets.strip_url_credentials(url: str) -> str | None`.
  - `connection.BADGE_LABELS: Mapping[ConnectKind, str]`.
  - `connection.ConnectionPath` — frozen dataclass с полями `text: str`,
    `note: str | None`, `directory: str | None` и свойством `copyable: bool`.
  - `connection.connection_path(item: InfobaseItem) -> ConnectionPath`.

- [x] **Step 1: Тест вырезания учётных данных**

Дополнить (или создать) `tests/unit/test_secrets.py`:

```python
import pytest

from onecstarter.security.secrets import is_secret_key, strip_url_credentials


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("", ""),
        ("http://srv/base", "http://srv/base"),
        ("https://srv:8443/base", "https://srv:8443/base"),
        ("http://user:pass@srv/base", "http://srv/base"),
        ("http://user:pass@srv:8080/base", "http://srv:8080/base"),
        ("http://user@srv/base", "http://srv/base"),
        # «@» вне authority: границы фрагментов неясны, показывать нельзя.
        # urlsplit("user:pass@srv/base") принимает «user» за схему, и наивная
        # проверка «есть ли @ в netloc» пропустила бы пароль на экран.
        ("user:pass@srv/base", None),
        # Незакодированный «/» в пароле: netloc обрывается на нём, и хвост
        # «ss@srv» уезжает в path. Такой URL платформа не приняла бы, но
        # показать его дословно значит показать пароль.
        ("http://user:pa/ss@srv/base", None),
        # Плата за fail-closed: законный «@» в пути тоже скрывается.
        ("http://srv/base@2", None),
    ],
)
def test_strip_url_credentials(url: str, expected: str | None) -> None:
    assert strip_url_credentials(url) == expected


def test_ppasswd_is_a_secret() -> None:
    """Зашифрованный пароль прокси — ключ секции, а не фрагмент Connect.

    Суффиксное правило endswith("pwd") его не ловит: «ppasswd» кончается
    на «sswd». Обязательство 2 ревью плана 3 — становится достижимым
    вместе с показом свойств записи (задача 8).
    """  # noqa: RUF002
    assert is_secret_key("PPasswd")
    assert is_secret_key("ppasswd")
    assert not is_secret_key("PUser")
```

- [x] **Step 2: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/unit/test_secrets.py -v`
Expected: FAIL — `ImportError: cannot import name 'strip_url_credentials'`

- [x] **Step 3: Реализовать в `security/secrets.py`**

В `_SECRET_KEYS` добавить `"ppasswd"`, докстринг модуля дополнить строкой
про ключи секции. Ниже `redact_connect` добавить:

```python
def strip_url_credentials(url: str) -> str | None:
    """Адрес без `user:pass@` и без query-параметров с секретным именем.

    `None` — показать адрес надёжно не вышло. Политика fail-closed, как
    у `redact_connect`: где разбор перестаёт быть однозначным, показывать
    нельзя вовсе.

    Разбор идёт `urllib.parse.urlsplit` безусловно — даже когда в строке нет
    буквального «@». Ранний выход по буквальному «@» здесь был бы багом:
    `urlsplit` сам NFKC-нормализует authority и поднимает `ValueError`, если
    нормализация вносит новый «/», «?», «#», «@» или «:» — то есть сам ловит
    юникодных двойников «собаки» (`＠` U+FF20, `﹫` U+FE6B и подобные). Ранний
    выход по буквальному «@» обошёл бы этот разбор стороной и пропустил бы
    двойника на экран, потому что для него `"@" not in url` истинно. Наивный
    поиск «@» до первого «/» тоже не годится: он ошибается
    на `http://user:pa/ss@srv/base`, где authority обрывается на
    незакодированном «/», и хвост с паролем уезжает в путь. Стандартный
    парсер режет оба случая по RFC.

    Четыре исхода, где возвращается `None`:

    - `urlsplit` или разбор порта подняли `ValueError` — адрес не разбирается
      (сюда же попадают юникодные двойники «собаки» в authority, см. выше);
    - query-строка несёт параметр с секретным именем (`is_secret_key`) —
      скрывается весь адрес, а не только параметр: показать частично хуже,
      чем не показать вовсе (та же политика, что у `redact_connect`).
      Проверяется до решения про «@», поэтому работает и для адресов
      без учётных данных в authority;
    - «@» есть — буквально или после NFKC-нормализации всей строки, чем
      заодно ловятся двойники вне authority, — но не в authority:
      `urlsplit("user:pass@srv/base")` принимает «user» за схему,
      и пароль остался бы в пути;
    - после пересборки «@» всё ещё на месте: границы разъехались.

    IPv6-хост `hostname` отдаёт без скобок (`::1`, не `[::1]`) — их нужно
    вернуть явно перед пересборкой: `urlunsplit` с голым `::1:8080` вместо
    `[::1]:8080` даёт адрес, который `urlsplit` обратно не разбирает.

    Плата за fail-closed — законный «@» в пути (`http://srv/base@2`) тоже
    скрывается. Это осознанный обмен: адрес хоста пользователь узнает
    из диалога свойств, а пароль из буфера обмена уже не отозвать
    (инвариант 5 CLAUDE.md).
    """  # noqa: RUF002
    try:
        split = urlsplit(url)
        netloc = split.netloc
        host = split.hostname or ""
        port = split.port
    except ValueError:
        return None
    query_names = (name for name, _value in parse_qsl(split.query, keep_blank_values=True))
    if any(is_secret_key(name) for name in query_names):
        return None
    if "@" not in unicodedata.normalize("NFKC", url):
        return url
    if "@" not in netloc:
        return None
    if ":" in host:
        host = f"[{host}]"
    if port is not None:
        host = f"{host}:{port}"
    cleaned = urlunsplit((split.scheme, host, split.path, split.query, split.fragment))
    return None if "@" in cleaned else cleaned
```

Импорт вверху файла: `import unicodedata` и
`from urllib.parse import parse_qsl, urlsplit, urlunsplit`.

**Правка круга 1 (ревью нашло реальный дефект, план предписывал этот код
дословно):** исходная редакция шага возвращала `url` без изменений при
`"@" not in url` ДО разбора и не проверяла query вовсе. Ревью на сильной
модели нашло три дыры: (1) юникодные двойники «собаки» проходили мимо —
`urlsplit` сам их ловит, но только если его вызвать, а ранний выход этого
не делал; (2) IPv6-хост терял скобки при пересборке — адрес переставал
разбираться обратно; (3) секрет в query-строке (`?pwd=...`) не скрывался
вовсе. Функция перестроена так, чтобы разбор запускался всегда, а не только
при буквальном «@» в строке — это было нужно и для юникодных двойников,
и для проверки query у адресов без «@». Код и докстринг здесь приведены
к тому, что реально в `git log` (коммит `1b6908b`), а не к тому, что было
написано в задаче 4 изначально (коммит `c8cd1aa`).

- [x] **Step 4: Тесты витрины размещения**

Создать `tests/unit/test_connection.py`:

```python
"""Витрина размещения: подпись вида и путь подключения."""

import pytest

from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.services.connection import BADGE_LABELS, connection_path
from onecstarter.services.model import InfobaseItem, InfobaseSource


def _base(connect: str | None, *, is_group: bool = False) -> InfobaseItem:
    return InfobaseItem(
        key="id:x",
        name="База",
        folder="/",
        is_group=is_group,
        connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id="x",
    )


def test_every_kind_has_a_label() -> None:
    """UNKNOWN обязан отличаться от трёх известных, а не быть «прочим»."""
    assert set(BADGE_LABELS) == set(ConnectKind)
    assert BADGE_LABELS[ConnectKind.UNKNOWN] == "строку соединения не разобрали"


@pytest.mark.parametrize(
    ("connect", "text", "directory"),
    [
        (r'File="D:\bases\acc";', r"D:\bases\acc", r"D:\bases\acc"),
        ('Srvr="localhost";Ref="ACC";', 'Srvr="localhost";Ref="ACC"', None),
        ('Srvr="localhost";', 'Srvr="localhost"', None),
        ('ws="http://srv/base";', "http://srv/base", None),
        ('ws="http://user:pass@srv/base";', "http://srv/base", None),
        # Порядок фрагментов в панели наш, а не файловый: Srvr, потом Ref —
        # так их показывает штатный стартер, с ним и сверяется пользователь.
        ('Ref="ACC";Srvr="localhost";', 'Srvr="localhost";Ref="ACC"', None),
        # Лишние параметры в панель не идут вовсе (решение заказчика 07.08.2026).
        (r'File="D:\b";Usr="admin";Pwd="s3";', r"D:\b", r"D:\b"),
    ],
)
def test_connection_path_shows_only_placement(
    connect: str, text: str, directory: str | None
) -> None:
    path = connection_path(_base(connect))
    assert path.text == text
    assert path.directory == directory
    assert path.note is None
    assert path.copyable


@pytest.mark.parametrize(
    ("connect", "is_group"),
    [(None, True), ('Srvr="x";', True), (None, False)],
)
def test_groups_and_connectless_records_show_nothing(connect: str | None, is_group: bool) -> None:
    path = connection_path(_base(connect, is_group=is_group))
    assert path.text == ""
    assert not path.copyable


def test_unknown_kind_gets_a_note_not_a_path() -> None:
    """Полная строка Connect в 4b не показывается и не копируется (§1.4)."""
    path = connection_path(_base("Нечто=1;"))
    assert path.text == ""
    assert path.note == "Строка соединения не распознана"
    assert not path.copyable


def test_web_with_unstrippable_credentials_is_hidden() -> None:
    path = connection_path(_base('ws="user:pass@srv/base";'))
    assert path.text == ""
    assert path.note is not None
    assert "@" in path.note
    assert not path.copyable


def test_empty_file_fragment_is_reported() -> None:
    path = connection_path(_base('File="";'))
    assert path.text == ""
    assert path.note == "В строке соединения пустой путь к базе"
```

- [x] **Step 5: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/unit/test_connection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.services.connection'`

- [x] **Step 6: Реализация `services/connection.py`**

```python
"""Витрина размещения записи: подпись вида и путь подключения.

Отдельно от `display.py` намеренно: тот отвечает за дерево и его строки,
здесь — разбор строки соединения. Одна ось на модуль.

Панель показывает **только путь подключения, без дополнительных параметров**
(решение заказчика 07.08.2026). Из `Connect` берутся `File` для файловой,
`Srvr` и `Ref` для серверной, `ws` для веб-базы; `Usr`, `Pwd`, `LocaleCode`,
`wsp*` и неизвестные ключи не попадают сюда вовсе. Это снимает вопрос
маскировки для FILE и SERVER: секретов в фрагментах размещения нет
по построению. Остаётся веб-база — её адрес может нести учётные данные,
и их вырезает `security.strip_url_credentials`.
"""  # noqa: RUF002

from collections.abc import Mapping
from dataclasses import dataclass

from onecstarter.domain.connect import ConnectKind, find_fragment, parse_connect
from onecstarter.security.secrets import strip_url_credentials
from onecstarter.services.model import InfobaseItem

__all__ = ["BADGE_LABELS", "ConnectionPath", "connection_path"]

BADGE_LABELS: Mapping[ConnectKind, str] = {
    ConnectKind.FILE: "файловая база",
    ConnectKind.SERVER: "серверная база",
    ConnectKind.WEB: "веб-база",
    ConnectKind.UNKNOWN: "строку соединения не разобрали",
}

_UNKNOWN_NOTE = "Строка соединения не распознана"
_EMPTY_FILE_NOTE = "В строке соединения пустой путь к базе"
_EMPTY_WS_NOTE = "В строке соединения пустой адрес публикации (ws)"
_DIRTY_URL_NOTE = (
    "Адрес показать не удалось: в нём есть «@», и вырезать учётные данные "
    "надёжно нельзя"
)


@dataclass(frozen=True)
class ConnectionPath:
    """Что панель показывает про выделенную запись.

    `text` пуст — показывать нечего; тогда причина в `note`, либо записи
    просто нет (группа, заголовок, пустое выделение). `directory` заполнен
    только у файловой базы: только для неё осмысленно «Открыть каталог».
    """  # noqa: RUF002

    text: str
    note: str | None = None
    directory: str | None = None

    @property
    def copyable(self) -> bool:
        return bool(self.text)


_NOTHING = ConnectionPath("")


def connection_path(item: InfobaseItem) -> ConnectionPath:
    if item.is_group or not item.connect:
        return _NOTHING
    fragments = parse_connect(item.connect)
    if item.kind is ConnectKind.FILE:
        value = find_fragment(fragments, "File") or ""
        if not value:
            return ConnectionPath("", _EMPTY_FILE_NOTE)
        return ConnectionPath(value, None, value)
    if item.kind is ConnectKind.SERVER:
        # Порядок наш, а не файловый: штатный стартер показывает Srvr, потом
        # Ref, и пользователь сверяется именно с этой формой.
        parts = [
            f'{name}="{value}"'
            for name in ("Srvr", "Ref")
            if (value := find_fragment(fragments, name))
        ]
        return ConnectionPath(";".join(parts)) if parts else ConnectionPath("", _UNKNOWN_NOTE)
    if item.kind is ConnectKind.WEB:
        raw = find_fragment(fragments, "ws") or ""
        if not raw:
            return ConnectionPath("", _EMPTY_WS_NOTE)
        cleaned = strip_url_credentials(raw)
        if cleaned is None:
            return ConnectionPath("", _DIRTY_URL_NOTE)
        return ConnectionPath(cleaned)
    return ConnectionPath("", _UNKNOWN_NOTE)
```

- [x] **Step 7: Прогон и коммит**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS.

```bash
git add src/onecstarter/services/connection.py src/onecstarter/security/secrets.py tests/unit/test_connection.py tests/unit/test_secrets.py
git commit -m "feat: витрина размещения — подпись вида и путь подключения без параметров"
```

- [x] **Step 8: Мутационная проверка (защитный тест, обязательна)**

Мутация 1: тело `strip_url_credentials` заменить на `return url`.
Ожидание: падают `test_strip_url_credentials[http://user:pass@srv/base-...]`
и оба случая с `None`.

Мутация 2: в `connection_path` для `WEB` вернуть `ConnectionPath(raw)` вместо
очищенного. Ожидание: падает
`test_connection_path_shows_only_placement` на строке с `user:pass@`.

Мутация 3: убрать `"ppasswd"` из `_SECRET_KEYS`. Ожидание: падает
`test_ppasswd_is_a_secret`.

Порядок: правка уже закоммичена шагом 7 → мутация → прогон → откат
`git checkout -- <файл>`.

Факт: подтверждено, все три мутации. Правка закоммичена `c8cd1aa`.

Мутация 1: тело `strip_url_credentials` заменено на `return url`. Прогон
`uv run pytest tests/unit/test_secrets.py -v`: 6 из 9 параметризованных
случаев `test_strip_url_credentials` упали (10 — общее число тестов в файле
вместе с `test_ppasswd_is_a_secret`, а не число случаев этого теста) — все,
где в исходном URL есть «@»
(включая оба ожидающих `None`, и три с ожидаемым вырезанием). Шире, чем
формулировка шага («падают … и оба случая с None»), но по факту
и содержит его: без вырезания текст с `user:pass@` не совпадает
с ожидаемым, а строки без надёжного разбора не превращаются в `None`.
Мутация отменена правкой обратно (правка уже закоммичена шагом 7, откат
безопасен) — `git diff` пуст, повторный прогон 10 из 10 зелёных.

Мутация 2: в `connection_path` для `WEB` возвращён `ConnectionPath(raw)`
вместо `ConnectionPath(cleaned)`. Прогон
`uv run pytest tests/unit/test_connection.py -v`: упал
`test_connection_path_shows_only_placement[ws="http://user:pass@srv/base";-http://srv/base-None]`
— `assert path.text == text` с `'http://user:pass@srv/base' == 'http://srv/base'`,
учётные данные видны в тексте панели. Остальные 13 тестов зелёные. Мутация отменена
правкой обратно — `git diff` пуст, повторный прогон 14 из 14 зелёных.

Мутация 3: `"ppasswd"` убран из `_SECRET_KEYS`. Прогон
`uv run pytest tests/unit/test_secrets.py -v`: упал `test_ppasswd_is_a_secret`
на `assert is_secret_key("PPasswd")` (`AssertionError: assert False`).
Остальные 9 тестов зелёные. Мутация отменена
правкой обратно — `git diff` пуст, повторный прогон 10 из 10 зелёных.

После всех трёх откатов `git status` чистый (совпадает с коммитом `c8cd1aa`),
полный прогон `uv run pytest && uv run ruff check . && uv run mypy`: 495 тестов,
ruff и mypy без замечаний.

Три мутации выше проверяли редакцию `strip_url_credentials` из коммита
`c8cd1aa`. Круг правок 1 (ревью на сильной модели) перестроил функцию —
код и докстринг в шаге 3 выше приведены к новой редакции (коммит `1b6908b`),
и три новых защитных теста (юникодные двойники «@», скобки IPv6, секрет
в query) прошли собственную мутационную проверку отдельно — результат
в `.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/task-4-report.md`,
раздел «Круг правок 1».

---

### Task 5: значок размещения в дереве и панель пути под ним

Первое, что заказчик увидит на экране из §1.3–§1.4.

**Files:**
- Create: `src/onecstarter/ui/bases/icons.py`
- Create: `src/onecstarter/ui/bases/panel.py`
- Modify: `src/onecstarter/ui/bases/tree_model.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/ui/test_icons.py` (создать)
- Test: `tests/ui/test_panel.py` (создать)
- Test: `tests/ui/test_tree_model.py` (дополнить)
- Test: `tests/ui/test_bases_view.py` (дополнить)

**Interfaces:**
- Consumes: `connection.BADGE_LABELS`, `connection.connection_path`,
  `connection.ConnectionPath` (задача 4); `theme.Palette` (задача 1).
- Produces:
  - `icons.placement_icon(kind: ConnectKind, palette: Palette) -> QIcon`.
  - `panel.ConnectionPanel(QWidget)` с методами
    `show_item(item: InfobaseItem | None) -> None`, `text() -> str`,
    `build_menu() -> QMenu`; конструктор
    `ConnectionPanel(*, open_directory: Callable[[str], bool], parent=None)`.
  - `BasesView.panel() -> ConnectionPanel` — доступ для тестов.

- [x] **Step 1: Тест значков**

Создать `tests/ui/test_icons.py`:

```python
"""Значки видов размещения: четыре различимых, перекрашиваются палитрой."""

from PySide6.QtGui import QIcon

from onecstarter.domain.connect import ConnectKind
from onecstarter.ui import theme
from onecstarter.ui.bases.icons import placement_icon


def _pixels(icon: QIcon) -> bytes:
    image = icon.pixmap(16, 16).toImage()
    return image.constBits().tobytes()


def test_every_kind_has_an_icon(qapp) -> None:
    for kind in ConnectKind:
        assert not placement_icon(kind, theme.DARK).isNull(), kind


def test_unknown_differs_from_known_kinds(qapp) -> None:
    """§1.3: UNKNOWN — это «не разобрали», а не «прочее»."""
    unknown = _pixels(placement_icon(ConnectKind.UNKNOWN, theme.DARK))
    for kind in (ConnectKind.FILE, ConnectKind.SERVER, ConnectKind.WEB):
        assert _pixels(placement_icon(kind, theme.DARK)) != unknown, kind


def test_known_kinds_differ_from_each_other(qapp) -> None:
    drawn = {
        kind: _pixels(placement_icon(kind, theme.DARK))
        for kind in (ConnectKind.FILE, ConnectKind.SERVER, ConnectKind.WEB)
    }
    assert len(set(drawn.values())) == 3


def test_palette_changes_the_drawing(qapp) -> None:
    """Значки создаются внутри build_model, поэтому смена темы их перерисует."""
    assert _pixels(placement_icon(ConnectKind.FILE, theme.DARK)) != _pixels(
        placement_icon(ConnectKind.FILE, theme.LIGHT)
    )
```

- [x] **Step 2: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/ui/test_icons.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.ui.bases.icons'`

- [x] **Step 3: Реализовать `ui/bases/icons.py`**

```python
"""Значки видов размещения, нарисованные кодом из действующей палитры.

Готовых PNG нет намеренно: значки создаются внутри build_model, а модель
пересобирается при смене темы, — значит новой запечённой точки цвета
не появляется (спека 4b, §1.3).

UNKNOWN рисуется иначе трёх известных и цветом проблемы: это не «прочее»,
а «строку соединения не разобрали» (§9 п. 2 спеки 4a).
"""  # noqa: RUF002

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from onecstarter.domain.connect import ConnectKind
from onecstarter.ui.theme import Palette

_SIZE = 16


def placement_icon(kind: ConnectKind, palette: Palette) -> QIcon:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    colour = QColor(palette.problem if kind is ConnectKind.UNKNOWN else palette.text_dim)
    pen = QPen(colour)
    pen.setWidthF(1.4)
    painter.setPen(pen)
    _DRAW[kind](painter, colour)
    painter.end()
    return QIcon(pixmap)


def _draw_file(painter: QPainter, colour: QColor) -> None:
    """Папка: корешок сверху слева, тело ниже."""
    painter.setBrush(colour)
    painter.drawRect(QRectF(1.5, 4.0, 13.0, 9.0))
    painter.drawRect(QRectF(1.5, 2.5, 5.5, 1.5))


def _draw_server(painter: QPainter, colour: QColor) -> None:
    """Стойка: три горизонтальные полки."""
    painter.setBrush(colour)
    for top in (2.5, 6.5, 10.5):
        painter.drawRect(QRectF(2.0, top, 12.0, 3.0))


def _draw_web(painter: QPainter, colour: QColor) -> None:
    """Глобус: окружность, экватор и меридиан."""
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(1.5, 1.5, 13.0, 13.0))
    painter.drawLine(QPointF(1.5, 8.0), QPointF(14.5, 8.0))
    painter.drawEllipse(QRectF(5.0, 1.5, 6.0, 13.0))


def _draw_unknown(painter: QPainter, colour: QColor) -> None:
    """Пунктирный контур со знаком вопроса: строку соединения не разобрали."""
    pen = QPen(colour)
    pen.setWidthF(1.4)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(1.5, 1.5, 13.0, 13.0))
    painter.setPen(QPen(colour))
    font = painter.font()
    font.setBold(True)
    font.setPointSizeF(8.0)
    painter.setFont(font)
    painter.drawText(QRectF(1.5, 1.5, 13.0, 13.0), Qt.AlignmentFlag.AlignCenter, "?")


_DRAW = {
    ConnectKind.FILE: _draw_file,
    ConnectKind.SERVER: _draw_server,
    ConnectKind.WEB: _draw_web,
    ConnectKind.UNKNOWN: _draw_unknown,
}
```

- [x] **Step 4: Значок в модели — тест и правка**

Дополнить `tests/ui/test_tree_model.py`:

```python
def test_base_rows_get_a_placement_icon(qapp) -> None:
    rows = [Row(RowKind.BASE, "Файловая", _file_item())]
    model = build_model(rows, {}, _stamp, theme.DARK)
    assert not model.item(0, 0).icon().isNull()
    assert model.item(0, 0).toolTip().endswith("файловая база")


def test_groups_have_no_placement_icon(qapp) -> None:
    """Группу отличает структура дерева; значок конкурировал бы со значком базы."""
    rows = [Row(RowKind.GROUP, "Клиенты", _group_item())]
    model = build_model(rows, {}, _stamp, theme.DARK)
    assert model.item(0, 0).icon().isNull()
```

В `tree_model._items_for`, внутри ветки `if row.item is not None:`, до установки
`KEY_ROLE`:

```python
        if not row.item.is_group and row.kind is RowKind.BASE:
            name.setIcon(placement_icon(row.item.kind, palette))
            label = BADGE_LABELS[row.item.kind]
            name.setToolTip(f"{row.note}\n{label}" if row.note else label)
```

Импорты: `from onecstarter.services.connection import BADGE_LABELS`,
`from onecstarter.ui.bases.icons import placement_icon`.

Существующая установка тултипа из `row.note` (строки 51–52) остаётся для строк
без значка; чтобы не затирать друг друга, перенести её в `elif row.note:`.

- [x] **Step 5: Тест панели**

Создать `tests/ui/test_panel.py`:

```python
"""Панель пути подключения: показ, копирование, открытие каталога."""

from PySide6.QtWidgets import QApplication

from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui.bases.panel import ConnectionPanel


def _item(connect: str | None, *, is_group: bool = False) -> InfobaseItem:
    return InfobaseItem(
        key="id:x", name="База", folder="/", is_group=is_group, connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=None, section_default_version=None, app=None,
        source=InfobaseSource.USER, order=None, section_id="x",
    )


def _panel(qtbot, opened: list[str]) -> ConnectionPanel:
    panel = ConnectionPanel(open_directory=lambda path: (opened.append(path), True)[1])
    qtbot.addWidget(panel)
    return panel


def test_shows_server_path(qtbot) -> None:
    panel = _panel(qtbot, [])
    panel.show_item(_item('Srvr="localhost";Ref="ACC";'))
    assert panel.text() == 'Srvr="localhost";Ref="ACC"'


def test_clears_on_group_and_on_empty_selection(qtbot) -> None:
    panel = _panel(qtbot, [])
    panel.show_item(_item('Srvr="localhost";'))
    panel.show_item(None)
    assert panel.text() == ""
    panel.show_item(_item(None, is_group=True))
    assert panel.text() == ""


def test_note_is_shown_instead_of_path(qtbot) -> None:
    panel = _panel(qtbot, [])
    panel.show_item(_item("Нечто=1;"))
    assert panel.text() == ""
    assert "не распознана" in panel.placeholder()


def test_copy_puts_shown_text_in_clipboard(qtbot) -> None:
    """В буфер идёт ровно то, что на экране — очищенный адрес (§1.4)."""
    panel = _panel(qtbot, [])
    panel.show_item(_item('ws="http://user:pass@srv/base";'))
    next(a for a in panel.build_menu().actions() if a.text() == "Копировать").trigger()
    assert QApplication.clipboard().text() == "http://srv/base"


def test_open_directory_only_for_file_kind(qtbot) -> None:
    opened: list[str] = []
    panel = _panel(qtbot, opened)

    panel.show_item(_item('Srvr="localhost";Ref="ACC";'))
    assert "Открыть каталог" not in [a.text() for a in panel.build_menu().actions()]

    panel.show_item(_item(r'File="D:\bases\acc";'))
    next(a for a in panel.build_menu().actions() if a.text() == "Открыть каталог").trigger()
    assert opened == [r"D:\bases\acc"]


def test_menu_is_empty_without_a_path(qtbot) -> None:
    panel = _panel(qtbot, [])
    panel.show_item(None)
    assert panel.build_menu().actions() == []
```

- [x] **Step 6: Реализовать `ui/bases/panel.py`**

```python
"""Панель пути подключения под деревом.

Read-only QLineEdit, а не QLabel: поле даёт выделение и Ctrl+C штатно,
без своего кода. Расчёт содержимого — services/connection.py, здесь только
показ и два действия.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QWidget,
)

from onecstarter.services.connection import ConnectionPath, connection_path
from onecstarter.services.model import InfobaseItem


def open_in_explorer(path: str) -> bool:
    """Открыть каталог проводником. `False` — каталога нет или отказ системы."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class ConnectionPanel(QWidget):
    def __init__(
        self,
        *,
        open_directory: Callable[[str], bool] = open_in_explorer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._open_directory = open_directory
        self._path = ConnectionPath("")

        self._caption = QLabel("Путь:")
        self._field = QLineEdit()
        self._field.setReadOnly(True)
        self._field.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._field.customContextMenuRequested.connect(self._show_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self._caption)
        layout.addWidget(self._field, stretch=1)

    def show_item(self, item: InfobaseItem | None) -> None:
        self._path = ConnectionPath("") if item is None else connection_path(item)
        self._field.setText(self._path.text)
        self._field.setPlaceholderText(self._path.note or "")

    def text(self) -> str:
        return self._field.text()

    def placeholder(self) -> str:
        return self._field.placeholderText()

    def build_menu(self) -> QMenu:
        """Собрать меню без показа — состав проверяется тестом без exec."""
        menu = QMenu(self)
        if not self._path.copyable:
            return menu
        menu.addAction("Копировать", self._copy)
        if self._path.directory:
            menu.addAction("Открыть каталог", self._open)
        return menu

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._path.text)

    def _open(self) -> None:
        directory = self._path.directory or ""
        if not self._open_directory(directory):
            # Молчание здесь читалось бы как «открылось где-то не там».
            QMessageBox.warning(
                self, "OneCStarter", f"Не удалось открыть каталог: {directory}"  # noqa: RUF001
            )

    def _show_menu(self, position: QPoint) -> None:
        menu = self.build_menu()
        if menu.actions():
            menu.exec(self._field.mapToGlobal(position))
```

- [x] **Step 7: Подключить панель в `BasesView`**

В `__init__`, рядом с созданием `self._tree`:

```python
        self._panel = ConnectionPanel(parent=self)
```

и в раскладку, ниже дерева (существующие строки `layout.addWidget` остаются
на месте, добавляется одна):

```python
        layout.addWidget(self._tree, stretch=1)
        layout.addWidget(self._panel)          # <- новая строка
```

Подписываться на выделение в `__init__` **нельзя**: модели ещё нет,
`self._tree.selectionModel()` вернёт `None`. Подписка ставится в `rebuild()` —
см. ниже.

**Правка круга 1 (ревью задачи 5).** Листинг ниже в исходной редакции этого
шага показывал только переподключение сигнала и вызов `_sync_panel()` —
без восстановления текущей строки. Это предписывало код с дефектом: `setModel()`
создаёт новую `QItemSelectionModel` без текущего индекса, и `_sync_panel()`
в конце `rebuild()` честно резолвил `key=None` — панель гасла при любой
пересборке, включая вызов из `launch_key()` (Ctrl+1 сразу после выделения
базы) и из каждого нажатия в поиске. Тот же корень оказался дефектом ещё
из 4a: `Ctrl+1`/`Ctrl+2`/`Ctrl+3` после набора текста в поиске не делали
ничего, потому что `_current_base_key()` читает именно текущую строку,
а не первую видимую (в отличие от `Enter` → `_launch_first_visible`).

Решение — восстанавливать текущую строку тем же устойчивым маркером,
которым уже восстанавливается развёрнутость (`_marker`). Маркер снимается
**до** подмены модели и **всегда**, независимо от фильтра: в отличие
от развёрнутости, текущая строка — это выбор пользователя в обоих режимах,
а не следствие поиска. `rebuild()`:

```python
        current_marker = self._current_marker()
        # ... пересборка forest/cells как раньше ...
        model = build_model(self._rows, cells, _format_stamp, self._palette)
        self._tree.setModel(model)
        # ... resizeColumnToContents, expandAll/_restore_expansion как раньше ...
        self._restore_current(current_marker)
        selection = self._tree.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(lambda *_: self._sync_panel())
        self._sync_panel()
```

Новые вспомогательные методы:

```python
    def _path_to(self, index: QModelIndex) -> str:
        """Путь меток от корня до индекса — тот же формат, что у обхода

        в `_expanded_keys`/`_restore_expansion`. Строится в обратную сторону,
        через `.parent()`, а не обходом от корня — индекс уже есть.
        """
        labels: list[str] = []
        node = index
        while node.isValid():
            labels.append(str(node.data()))
            node = node.parent()
        return "/" + "/".join(reversed(labels))

    def _current_marker(self) -> str | None:
        index = self._tree.currentIndex().siblingAtColumn(0)
        if not index.isValid():
            return None
        return self._marker(index, self._path_to(index))

    def _restore_current(self, marker: str | None) -> None:
        """Маркера нет или узел исчез (удалён, скрыт фильтром) — текущей

        строки не остаётся, и это правильно: панель гаснет, а не показывает
        случайную соседнюю строку.
        """
        if marker is None:
            return
        model = self._tree.model()

        def walk(parent: QModelIndex, path: str) -> QModelIndex | None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                here = f"{path}/{index.data()}"
                if self._marker(index, here) == marker:
                    return index
                found = walk(index, here)
                if found is not None:
                    return found
            return None

        found = walk(QModelIndex(), "")
        if found is not None:
            self._tree.setCurrentIndex(found)

    def panel(self) -> ConnectionPanel:
        return self._panel

    def _sync_panel(self) -> None:
        key = self._current_base_key()
        item = None if key is None else next(
            (i for i in self._workspace.items() if i.key == key), None
        )
        self._panel.show_item(item)
```

Тесты (добавлены кругом 1, все пять — см. `test_bases_view.py`):
выделить → `rebuild()` → строка и панель те же; выделить → `launch_key()` →
панель не гаснет (сценарий отчёта ревью); выделить → поиск, оставляющий
запись видимой → строка осталась текущей; выделить → поиск, скрывающий
запись → текущей строки нет, панель пуста, ошибок нет; выделить → поиск →
`Ctrl+1` запускает эту базу (латентный дефект 4a, фиксирует именно починку).

Тест в `tests/ui/test_bases_view.py`:

```python
def test_panel_follows_selection(qtbot, workspace_factory) -> None:
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    index = _first_base_index(view)
    view._tree.setCurrentIndex(index)
    assert view.panel().text() != ""
```

`_first_base_index` — существующий помощник этого файла; если его нет, добавить
рядом с прочими помощниками обход модели до первой строки с `KIND_ROLE == "base"`.

- [x] **Step 8: Прогон и коммит**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS.

```bash
git add src/onecstarter/ui tests/ui
git commit -m "feat: значок вида размещения в дереве и панель пути подключения"
```

- [x] **Step 9: Тест «после смены темы не осталось цветов прежней палитры»**

Обещан §9 спеки. Ставится здесь, потому что только теперь запечённых точек две —
`QBrush` строк и значки.

```python
def test_theme_switch_leaves_no_stale_colours(qtbot, workspace_factory) -> None:
    """Обе запечённые точки перекрашиваются: QBrush строк и значки размещения.

    Иконка трея в проверку не входит намеренно — она от палитры не зависит
    (спека 4b, §2.4).
    """  # noqa: RUF002
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[], palette=theme.DARK)
    qtbot.addWidget(view)

    view.apply_palette(theme.LIGHT)

    stale = {theme.DARK.text_dim.casefold(), theme.DARK.problem.casefold()}
    icons_dark = _icon_bytes(theme.DARK)

    def walk(parent: QModelIndex) -> None:
        model = view.model()
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            item = model.itemFromIndex(index)
            assert item.foreground().color().name().casefold() not in stale
            if not item.icon().isNull():
                assert item.icon().pixmap(16, 16).toImage().constBits().tobytes() \
                    not in icons_dark
            walk(index)

    walk(QModelIndex())
```

`_icon_bytes(palette)` — помощник, возвращающий множество байтовых представлений
всех четырёх значков для этой палитры.

- [x] **Step 10: Мутационная проверка (обязательна)**

Мутация 1: убрать `self.rebuild()` из `BasesView.apply_palette`.
Ожидание: падает `test_theme_switch_leaves_no_stale_colours` — цвета остались
тёмными.

Мутация 2: в `placement_icon` брать цвет всегда как `palette.text_dim`
(снять различие для `UNKNOWN`). Ожидание: падает
`test_unknown_differs_from_known_kinds`.

Мутация 3: в `connection_path` для группы вернуть путь вместо `_NOTHING`.
Ожидание: падает `test_clears_on_group_and_on_empty_selection`.

Факт: правка уже закоммичена (шаги 1–9, коммиты `29590a7`, `c3eea4e`)
→ мутация → прогон → откат `git checkout -- <файл>`.

Мутация 1: убрана строка `self.rebuild()` из `apply_palette` в
`src/onecstarter/ui/bases/view.py`. Прогон
`uv run pytest tests/ui/test_bases_view.py -v -k theme_switch`: упал
`test_theme_switch_leaves_no_stale_colours` — `assert pixels.tobytes() not in
icons_dark` не выполнилось: значок остался прежним пикселем тёмной палитры,
потому что модель не пересобралась. Подтверждено как в плане. Откат
`git checkout -- src/onecstarter/ui/bases/view.py`, повторный прогон — зелёный.

Мутация 2: в `_colour_for` (внутри `placement_icon`) цвет заменён на
безусловный `QColor(palette.text_dim)`. Прогон `uv run pytest
tests/ui/test_icons.py -v`: все 4 теста из брифа остались зелёными,
включая `test_unknown_differs_from_known_kinds` — план не подтвердился.
Причина: тест сравнивает сырые байты пикселей целого значка, а UNKNOWN
рисуется другой фигурой (пунктирный контур и «?» вместо сплошной заливки),
так что пиксели расходятся из-за формы независимо от цвета — сравнение
пикселей не проверяет цвет как отдельный факт, хотя требование заказчика
(§1.3) — разница и формой, и цветом одновременно. Это находка мутационной
проверки, а не повод считать шаг пройденным: тест, не ловящий сломанное
поведение, которое обязан ловить по смыслу требования, — то самое
предостережение CLAUDE.md про тест, зелёный на пустышке. Закрыто отдельным
коммитом `326c638` **до** повторной попытки мутации: выбор цвета вынесен
в чистую `_colour_for(kind, palette) -> QColor`, добавлен тест
`test_unknown_uses_the_problem_colour_not_the_dimmed_text_colour`,
сравнивающий цвет напрямую, а не через рендер. С этим тестом мутация
повторена: та же правка (`_colour_for` возвращает только `text_dim`) —
новый тест упал ожидаемо (`AssertionError` на сравнении `QColor`), три
прежних теста остались зелёными (форма всё ещё различает пиксели — это
не баг, а показывает, что старые тесты проверяли форму, а не цвет).
Откат `git checkout -- src/onecstarter/ui/bases/icons.py`, повторный
прогон `tests/ui/test_icons.py` — 5 из 5 зелёных.

Мутация 3: в `connection_path` (`src/onecstarter/services/connection.py`)
ветка для группы отделена от ветки «нет `connect`» и вместо `_NOTHING`
возвращает `ConnectionPath(item.folder)`. Прогон
`uv run pytest tests/ui/test_panel.py tests/unit/test_connection.py -v`:
упали `test_clears_on_group_and_on_empty_selection`
(`assert '/' == ''`, панель показала путь группы вместо пустоты) и попутно
два кейса `test_groups_and_connectless_records_show_nothing` из юнит-тестов
задачи 4 (тот же дефект виден и там, хотя план предсказывал только тест
панели). Подтверждено, шире формулировки плана. Откат
`git checkout -- src/onecstarter/services/connection.py`, повторный
прогон — зелёный.

После всех откатов `git status` чист (совпадает с последним коммитом
`326c638`), полный прогон `uv run pytest && uv run ruff check . && uv run
mypy`: 519 тестов, ruff и mypy без замечаний.

## Круг правок 1 (ревью задачи 5, дефект в коде, предписанном планом дословно)

Ревью нашло реальный дефект: `rebuild()` восстанавливал развёрнутость,
но не текущую строку — `setModel()` даёт новую `QItemSelectionModel` без
текущего индекса, и панель гасла при любой пересборке (включая `Ctrl+1`
сразу после выделения базы — сценарий из отчёта ревью). Тот же корень
оказался латентным дефектом ещё из 4a: `Ctrl+1`/`Ctrl+2`/`Ctrl+3` после
набора текста в поиске не делали ничего. Листинг `rebuild()` в шаге 7 выше
предписывал именно эту потерю дословно — план и код исправлены вместе
(правило CLAUDE.md).

Решение: текущая строка восстанавливается тем же устойчивым маркером,
которым уже восстанавливается развёрнутость (`_marker`), снимается всегда
и до подмены модели (в отличие от развёрнутости — независимо от фильтра).
Полный код — в шаге 7 выше (обновлён), полная мутационная проверка (маркер
и её пять новых тестов) и правки трёх мелочей ревью (две строки короче
100 символов, тест на отказ `_open`, единообразие `_DIRTY_URL_NOTE`) —
в `.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/task-5-report.md`,
раздел «Круг правок 1».

Коммиты круга 1:

- `33c63ca` — fix: rebuild() восстанавливает текущую строку по маркеру дерева
- `dc7b1af` — style: единообразие пометок connection.py — без точки в конце
- `5bf0ac2` — test: покрытие отказа открытия каталога, строки короче 100 символов

Мутационная проверка (обязательна): убрать восстановление текущей строки
из `rebuild()`. Факт: упали три предсказанных теста (`test_rebuild_keeps_current_row_and_panel`,
`test_launch_keeps_current_row_selected_and_panel_visible`,
`test_ctrl_1_after_search_launches_the_selected_base`) и один непредсказанный
(`test_search_keeps_current_row_when_still_visible` — ожидаемо шире:
мутация убирает восстановление целиком, а не только для сценария поиска).
Откат `git checkout -- src/onecstarter/ui/bases/view.py`, повторный прогон —
525 тестов зелёных, ruff и mypy без замечаний.

## Круг правок 2 (ручной smoke №1, 08.08.2026 — обратная связь с живой машины)

Не ревью кода — пять замечаний с реального прогона на машине заказчика,
после задачи 7. Три из пяти — в файлах задачи 5 (`icons.py`, `view.py`);
пункт 1 меняет `theme.py` (задача 1, помечено там же); пункт 5 закрывает
пробел объёма задачи 7 (помечено там же). Полный перечень и маршрутизация —
в разделе «Замечания ручного smoke №1 (08.08.2026)» после контрольной
точки в задаче 7.

**Замечание 1 — выделенная строка нечитаема в светлой теме.** Правка
и её тест — в задаче 1 (`theme.py`, коммит `064940f`), листинг шага 3
задачи 1 приведён к новому виду. `tree_model.py` не тронут: эксперимент
(offscreen, `grab()` + сэмплинг пикселей) показал, что явный `color`
в `:selected` побеждает `Qt::ForegroundRole` строки целиком — решать
в модели не понадобилось, полный разбор — в комментарии QSS `theme.py`.

**Замечание 2 — значки не читаются.** Заливка (`setBrush(colour)` +
`drawRect`) на 16 px съедала силуэт, у папки и стойки вдобавок были
одинаковые пропорции. `icons.py` переведён на контур: `_draw_file`
и `_draw_server` (шаг 3 задачи 5 выше — тот листинг устарел, актуальный
код в `src/onecstarter/ui/bases/icons.py`) теперь рисуют силуэт через
`QPainterPath`/`drawRect`+`drawLine` с `NoBrush`, папка заметно шире,
чем выше, стойка заметно выше, чем шире. `_draw_web`/`_draw_unknown`
не менялись — глобус уже был контуром, пунктир с «?» заказчик просил
не трогать. Коммит `73e6536`. Проверочный скрипт
`.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py` (вне git)
с запасным вариантом B для папки и стойки — на выбор заказчику до
следующего smoke.

**Замечание 3 — колонка «База» схлопывается на первой букве поиска.**
`rebuild()` звал `resizeColumnToContents` на каждой пересборке; фильтр
оставляет короткие имена — колонка сужалась. Ширины теперь снимаются
до подмены модели и восстанавливаются после (`_column_widths`/
`_restore_column_widths`, тот же приём, что и у развёрнутости и текущей
строки); `resizeColumnToContents` остался только для самой первой сборки.

**Замечание 4 — после запуска базы выделение перескакивает в «Недавние».**
Тонкий дефект собственного восстановления текущей строки (круг правок 1):
запись, показанная и в дереве файла, и в «Недавних», имеет один и тот же
маркер (ключ привязки) в двух местах модели — `_restore_current` брала
первое совпадение по всему дереву, а «Недавние» стоит в лесу выше дерева
файла. Теперь запоминается пара «маркер + путь» (`_current_position`),
и восстановление предпочитает точное совпадение обоих, а на маркер
без пути опирается только как на запасной вариант (запись могла
переехать в другую группу между пересборками). Проверено: болезнь
`_restore_expansion`/`_expanded_keys` не касается — группы (в отличие
от баз) никогда не дублируются между «Недавними»/«Избранным» и деревом
файла (`display_forest` кладёт в эти виртуальные ветки только записи баз,
`bases = [item for item in items if not item.is_group]`), а строки-базы
сами никогда не имеют детей и потому никогда не входят в множество
развёрнутых узлов — восстанавливать там нечего.

Замечания 3 и 4 закрыты одним коммитом `3bab162` (оба меняют `rebuild()`
и делят один и тот же приём снятия/восстановления состояния). Мутационная
проверка обязательна для обоих:

- Замечание 3: убрано восстановление ширин (`if column_widths is None: ...
  else: self._restore_column_widths(...)` заменено на безусловный
  `resizeColumnToContents`). Упал `test_column_width_survives_search_that_shortens_visible_names`
  (`assert 120 == 264`). Откат `git checkout --`, повторный прогон зелёный.
- Замечание 4: `_restore_current` возвращена к поиску только по маркеру
  (путь снимается и запоминается, но не используется при сравнении).
  Упал `test_launch_from_file_tree_keeps_current_row_in_file_tree`
  (курсор снова уехал в «Недавние», путь `/Недавние/...` вместо исходного
  `/Клиенты/...`); `test_launch_from_recent_keeps_current_row_in_recent`
  остался зелёным — ожидаемо, тест не должен ловить эту мутацию, он
  как раз против жёсткого «всегда дерево файла». Откат `git checkout --`,
  повторный прогон зелёный.

**Замечание 5 — подписи хоткеев в меню не приведены к F3/F4.** Задача 7
добавила клавиши, но не тронула `_build_menu` — заказчик видел прежние
`Ctrl+1/2/3`. «Запустить» → `F3`, «Конфигуратор» → `F4`; «Тонкий»/«Толстый
клиент» остаются на `Ctrl+1`/`Ctrl+2` — только они дают явный выбор
клиента. `Ctrl+3` остаётся рабочим псевдонимом (`__init__` регистрирует
оба сочетания), но в меню теперь показан `F4`. Коммит `b740ac4`; отметка
о пробеле объёма — в задаче 7 ниже.

После всех откатов `git status` чист, полный прогон
`uv run pytest && uv run ruff check . && uv run mypy`: 536 тестов, ruff
и mypy без замечаний.

Изменённые файлы круга правок 2: `src/onecstarter/ui/theme.py`,
`src/onecstarter/ui/bases/icons.py`, `src/onecstarter/ui/bases/view.py`,
`tests/ui/test_theme.py`, `tests/ui/test_bases_view.py`,
`docs/superpowers/plans/2026-08-08-v1-plan4b-ui-edit.md` (этот файл).

---

### Task 6: дефект показа контекстного меню

Переезд задачи 15 плана 4a (§7 спеки 4b). **Диагностика первым шагом, правка —
по снятой причине.** Догадку за факт не выдаём: offscreen дефект
не воспроизводится ни в одном из четырёх стилей Qt, ширины хватает везде.

**Files:**
- Modify: `src/onecstarter/ui/theme.py` — по итогу диагностики (выполнено
  в задаче 1, см. шаг 2)
- Test: `tests/ui/test_theme.py` — не `test_bases_view.py`: правило живёт
  в `theme.stylesheet()`, к `BasesView` отношения не имеет (уточнено шагом 3)

**Interfaces:**
- Consumes: `BasesView._build_menu` (существует с 4a).
- Produces: изменений в публичных сигнатурах нет.

- [x] **Step 1: Замеры на реальном экране заказчика — ПРОВЕДЕНЫ 08.08.2026**

Сняты до старта плана, четырьмя кругами; скрипты — в рабочем каталоге плана
(`menu_probe.py` … `menu_probe4.py`).

**[Ф] Окружение:** стиль `windows11`, PySide6 6.11.1, `devicePixelRatio = 1.0`,
`logicalDotsPerInch = 96.0`, экран 3440×1440, системный шрифт Segoe UI 9pt.

**[Ф] Круг 1 — все три кандидата спеки опровергнуты:**

| Вариант | `sizeHint().width()` |
| --- | --- |
| тема + табуляция (текущее 4a) | 152 |
| тема + `QAction.setShortcut` | 152 |
| без темы + табуляция | 151 |
| без темы + `setShortcut` | 151 |

Масштабирования нет (100 %), `setShortcut` ширину не меняет, тема добавляет
1 px. Ширина 152 совпадает со скриншотом заказчика (~151).

**[Ф] Круг 2 — колонка сочетаний резервируется, гипотеза о ней опровергнута:**
`showShortcutsInContextMenus` уже `True`; меню без сочетаний — 110, с ними —
152 (`+42`), то есть колонка учтена.

**[Ф] Круг 3 — шрифт учитывается:** при теме `menu.font()` = Segoe UI 10pt,
и `sizeHint` посчитан по нему. Но содержимому нужно 92 px (название
«Толстый клиент») + 36 px (`Ctrl+2`) = **128**, а `sizeHint` = **152**:
на колонку значка, поля и зазор между названием и сочетанием остаётся
**24 px**. У стиля `windows11` одна колонка значка занимает столько же —
зазора не остаётся вовсе.

**[Ф] Круг 4 — причина и лекарство:**

| Вариант | `sizeHint().width()` |
| --- | --- |
| тема как есть | 152 |
| тема + `QMenu::item { padding: 5px 28px; }` | **200** |
| тема без правила `QMenu::item:selected` | 152 |

Заказчик подтвердил глазами 08.08.2026: **первый вариант воспроизводит дефект,
второй его чинит.**

**[Ф] Вывод.** Раскладку меню по QSS включает само правило
`QMenu { background; border }`, а не стилизация пункта: убрать
`QMenu::item:selected` не помогает (152 = 152). В QSS-раскладке `padding`
пункта по умолчанию нулевой, поэтому между названием и сочетанием
не остаётся места. Лекарство — явный `padding` у `QMenu::item`.

- [x] **Step 2: Правка по снятой причине**

Причина — QSS-раскладка с нулевым `padding`. В `theme.stylesheet()` добавляется
правило **до** `QMenu::item:selected`:

```
QMenu::item {{ padding: 5px 28px 5px 28px; }}
```

Кандидаты «табуляция» и «масштабирование» отпадают по кругам 1 и 3, менять
`\t` на `setShortcut` не нужно: на ширину это не влияет (152 = 152).

**Правка выполняется в задаче 1** — она и так переписывает `theme.py` целиком,
и заводить ради одной строки QSS отдельный коммит в том же файле бессмысленно.
Здесь остаются шаги 3–5: тест, прогон и повторный smoke.

- [x] **Step 3: Тест-страховка — переписан по факту диагностики**

Листинг ниже заменяет прежний черновик шага. Тот был написан под кандидат
«заменить табуляцию на `QAction.setShortcut()`» — круг 1 (шаг 1) его опроверг:
`setShortcut` не меняет `sizeHint` (152 = 152 с темой, 151 = 151 без), `\t`
в тексте пункта остался, правка не применялась. Тест на этот кандидат сейчас
падал бы, проверяя несуществующее решение, а до появления кандидата в коде был
бы зелёным по совпадению — то есть бесполезен в обоих направлениях
(`CLAUDE.md`: тест, зелёный на пустышке, хуже отсутствующего).

Проверяемое утверждение — по факту круга 4 и правки шага 2: в `theme.stylesheet()`
есть правило `QMenu::item` с ненулевым `padding`, и оно стоит **до**
`QMenu::item:selected` (порядок в QSS значим — более позднее правило
перекрывает более раннее). Offscreen сам дефект не воспроизводит ни в одном
из четырёх стилей Qt (шаг 1, круг 1), поэтому тест на ширину меню бессмыслен —
он был бы зелёным и до правки. Это страховка от отката, а не доказательство
исправления: единственная настоящая проверка — шаг 5 на машине заказчика.

Положен в `tests/ui/test_theme.py`, а не в `test_bases_view.py`: правило живёт
в `theme.py`, к сборке меню `BasesView` отношения не имеет, и рядом уже
проверяются другие свойства таблицы стилей палитры.

```python
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
```

- [x] **Step 4: Прогон, коммит, мутационная проверка**

Run: `uv run pytest && uv run ruff check . && uv run mypy` — 526 тестов зелёные
(было 525, тест шага 3 — новый), ruff и mypy чистые.

```bash
git add tests/ui/test_theme.py
git commit -m "test: страховка от отката padding QMenu::item"
```

Мутация 1 — убрать правило `QMenu::item { padding: ... }` из `theme.stylesheet()`
(строка удалена, `QMenu::item:selected` осталась). Тест упал на
`assert match is not None, "правило QMenu::item с padding пропало"` — регэксп
не нашёл правило ни в одной из двух палитр.

Мутация 2 — переставить `QMenu::item` **после** `QMenu::item:selected`. Тест
упал на проверке порядка: `assert 1260 < 1198` (позиция найденного правила
стала больше позиции `:selected`) — страховка проверяет не только наличие
правила, но и то, что оно идёт раньше.

Обе мутации отменены через `git checkout -- src/onecstarter/ui/theme.py`:
правка шага 2 уже закоммичена в задаче 1, откат безопасен, теряет только
мутацию. Повторный прогон после каждого отката — 526 из 526 зелёных.

Факт: подтверждено — тест ловит и удаление правила, и перестановку порядка.

- [x] **Step 5: Повторный smoke на машине заказчика**

Единственная настоящая проверка этого дефекта. Результат записать сюда.

Факт: отдельным прогоном не проводился — исполнен контрольной точкой «ручной
smoke №1» 08.08.2026, которая идёт сразу после задачи 7 и содержит пункт
«контекстное меню отрисовано без наложения». Правка задачи 6 к тому моменту
уже была в ветке (`803ba1b`, `d3168a2` — раньше `5f152ba`, которым разнесены
замечания smoke №1). Наложения среди пяти замечаний нет, при этом замечание 5
(«подписи хоткеев остались `Ctrl+1/2/3`») касается того же меню — значит меню
на реальном экране действительно смотрели, а не пропустили. Дефект закрыт.

---

### Task 7: горячие клавиши `F3` и `F4`

§6.1. Идёт **после** задачи 6: если причиной скомканного меню окажется табуляция,
переход на `QAction.setShortcut()` обязан состояться до добавления новых пунктов.

**Files:**
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `BasesView.launch_key`, `BasesView._current_base_key` (существуют).
- Produces: изменений в публичных сигнатурах нет.

- [x] **Step 1: Тесты**

Дополнить `tests/ui/test_bases_view.py`:

```python
def test_f3_launches_in_default_mode(qtbot, workspace_factory) -> None:
    """F3 — режим «1С:Предприятие», а не выбор клиента.

    Тонкий или толстый решает App секции либо платформа ([Ф] T-02.6),
    поэтому forced_client не передаётся — как у Enter.
    """  # noqa: RUF002
    workspace, calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    _select_first_file_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F3)

    assert len(calls) == 1
    assert "ENTERPRISE" in calls[0].arguments


def test_f4_launches_designer(qtbot, workspace_factory) -> None:
    workspace, calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    _select_first_file_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F4)

    assert len(calls) == 1
    assert "DESIGNER" in calls[0].arguments


def test_f4_does_nothing_for_web_base(qtbot, workspace_factory) -> None:
    """«Открыть Конфигуратор» и «открылся браузер» — разные вещи.

    launch_infobase для WEB игнорирует forced_client, поэтому наивный вызов
    launch_key открыл бы браузер и выдал бы это за Конфигуратор. Тот же обман
    задача 8 плана 4a уже закрыла для Ctrl+1/2/3 — здесь он не должен вернуться.
    """  # noqa: RUF002
    workspace, calls, opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    _select_first_web_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F4)

    assert calls == []
    assert opened == []


def test_f3_opens_browser_for_web_base(qtbot, workspace_factory) -> None:
    workspace, _calls, opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    _select_first_web_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F3)

    assert len(opened) == 1
```

Помощники `_select_first_file_base` и `_select_first_web_base` обходят модель
до строки с нужным `KIND_ROLE`/видом и ставят `setCurrentIndex`. Фикстура
`anonymized.v8i` содержит и ws-строку соединения (обязательный набор краевых
случаев, `CLAUDE.md`), поэтому веб-база в ней есть.

- [x] **Step 2: Прогнать, убедиться, что падает**

Run: `uv run pytest tests/ui/test_bases_view.py -k "f3 or f4" -v`
Expected: FAIL — `assert len(calls) == 1` при `calls == []`: клавиши не связаны.

- [x] **Step 3: Реализация**

В `BasesView.__init__` рядом с существующими `QShortcut`:

```python
        # F3/F4 — как у штатного стартера; заказчик к ним привык.
        # Ctrl+1/Ctrl+2 остаются: только они дают явный выбор тонкий/толстый,
        # которого у F3 нет. Ctrl+3 дублирует F4 — дубль безвреден.
        QShortcut(QKeySequence("F3"), self, lambda: self._launch_current(None))
        QShortcut(QKeySequence("F4"), self, lambda: self._launch_current(ClientKind.DESIGNER))
```

`_launch_current` перестаёт молча открывать браузер, когда клиент затребован явно:

```python
    def _launch_current(self, forced: ClientKind | None) -> None:
        key = self._current_base_key()
        if not key:
            return
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is not None and item.kind is ConnectKind.WEB:
            # launch_infobase игнорирует forced_client для веб-баз (нет
            # исполняемого файла клиента). Раньше здесь стоял безусловный
            # launch_key: с Ctrl+1/2/3 это было честно, потому что меню для WEB
            # такие пункты прячет. С F4 — уже нет: «Конфигуратор» и «открылся
            # браузер» разные вещи. Явно затребованный клиент для веб-базы —
            # бездействие, режим по умолчанию — браузер.
            if forced is not None:
                return
            self.launch_key(key)
        else:
            self.launch_key(key, forced)
```

Пункт «Открыть в браузере» в `_build_menu` для `WEB` не меняется — он зовёт
`launch_key(key)` без `forced`.

- [x] **Step 4: Прогон и коммит**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS. Существующий тест 4a на `Ctrl+3` для веб-базы (если он
утверждал открытие браузера) обязан быть пересмотрен: поведение изменилось
осознанно, и тест правится вместе с кодом.

```bash
git add src/onecstarter/ui/bases/view.py tests/ui/test_bases_view.py
git commit -m "feat: F3 запускает предприятие, F4 конфигуратор; явный клиент не подменяется браузером"
```

- [x] **Step 5: Мутационная проверка (обязательна)**

Мутация: убрать `if forced is not None: return` из ветки `WEB`.
Ожидание: падает `test_f4_does_nothing_for_web_base` на `assert opened == []`.

Факт: подтверждено. Правка сделана после коммита `ff0a57b`. Упали два теста:
целевой `test_f4_does_nothing_for_web_base` на `assert opened == []`
(`opened == ['http://web-server/resource/']`) и заодно переписанный
`test_ctrl_1_on_web_base_does_nothing` — оба проверяют один и тот же guard.
Остальные 529 тестов остались зелёными. Мутация отменена
`git checkout -- src/onecstarter/ui/bases/view.py` (безопасно — правка уже
закоммичена), повторный прогон — 531 из 531 зелёных.

**Пробел объёма, найденный smoke №1 (08.08.2026), замечание 5.** Задача
предписывала «`F3`/`F4` и их подсказки в меню» (см. заголовок задачи),
но шаг 3 выше добавил только `QShortcut` и правку `_launch_current` —
`_build_menu` не тронут, комментарий на строке 2691 выше даже прямо
говорит, что «не меняется», не уточняя, что подписи остальных пунктов
(«Запустить», «Конфигуратор») тоже остаются старыми Ctrl-сочетаниями.
На машине заказчика это осталось незамеченным до ручного прогона: меню
показывало `Ctrl+1/2/3`, а не `F3`/`F4`, к которым заказчик привык
по штатному стартеру. Правка — в задаче 5, «Круг правок 2» (коммит
`b740ac4`): «Запустить» → `F3`, «Конфигуратор» → `F4`, `Ctrl+1`/`Ctrl+2`
остаются подписями «Тонкий»/«Толстый клиент». Здесь код задачи 7 не
трогается — единственная правка задачи 7 в этом круге ровно эта пометка,
чтобы шаг 3 выше не выглядел законченным, каким не был.

---

## Контрольная точка: ручной smoke №1

После задачи 7 собрать и прогнать на рабочей машине заказчика. Проверяется:

- переключение темы из раздела «Настройки» и из трея, все три состояния;
- «Авто» следует за темой Windows (сменить тему системы при работающем приложении);
- значки размещения различимы, у неразобранной строки соединения — свой;
- панель пути показывает то же, что штатный стартер, «Копировать» и «Открыть
  каталог» работают;
- контекстное меню отрисовано без наложения;
- `F3` и `F4` запускают то, что обещано.

Замечания заказчика записываются сюда и разносятся по задачам, а не чинятся
по ходу.

Факт: прогон состоялся 08.08.2026, пять замечаний, все воспроизводимы,
все разнесены по задачам и закрыты. Перечень и маршрутизация — в разделе
«Замечания ручного smoke №1 (08.08.2026)» ниже.

---

## Замечания ручного smoke №1 (08.08.2026)

| № | Замечание заказчика | Куда ушло | Коммит(ы) |
| --- | --- | --- | --- |
| 1 | Выделенная строка дерева нечитаема в светлой теме — `QTreeView::item:selected` красил только фон, текст оставался за стилем `windows11` (светлый на светлом) | задача 1 (`theme.py`, листинг шага 3 приведён к новому виду) + задача 5 «Круг правок 2» (эксперимент и тест) | `064940f` |
| 2 | Значки видов размещения не читаются — заливка на 16 px съедала силуэт, у папки и стойки были одинаковые пропорции | задача 5 «Круг правок 2» (`icons.py`, листинг шага 3 задачи 5 устарел — актуальный код в файле) | `73e6536` |
| 3 | Колонка «База» резко сужается при начале набора в поиске — `resizeColumnToContents` на каждой пересборке | задача 5 «Круг правок 2» (`view.py`, `rebuild()`) | `3bab162` |
| 4 | После запуска базы выделение перескакивает в «Недавние» — маркер текущей строки не различал два вхождения одной записи | задача 5 «Круг правок 2» (`view.py`, `_restore_current`/`_current_position`) | `3bab162` |
| 5 | Подписи хоткеев в контекстном меню остались `Ctrl+1/2/3` — задача 7 добавила `F3`/`F4`, но не тронула `_build_menu`, хотя это было в её объёме | задача 7 (пометка о пробеле объёма) + задача 5 «Круг правок 2» (сама правка `_build_menu`) | `b740ac4` |

Замечания 3 и 4 закрыты одним коммитом — обе меняют `rebuild()` и делят
приём снятия/восстановления состояния перед пересборкой модели.

Мутационная проверка обязательна и пройдена для замечаний 3 и 4 (полный
разбор — в задаче 5, «Круг правок 2», выше): оба защищают состояние,
которое пользователь видит напрямую, а не внутренний расчёт.

Полный отчёт с TDD Evidence, деталями каждой правки и находками
самопроверки — `.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/task-5-report.md`,
раздел «Замечания smoke №1». Проверочный скрипт для замечания 2 (вне git,
не в этом плане) —
`.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/icons_probe.py`.

После круга правок 2: `uv run pytest` — 536 тестов, `uv run ruff check .`
и `uv run mypy` — без замечаний.

---

### Task 8: диалог свойств записи — только чтение

Показ без правки (§3.1). Правка — задача 9. Здесь же исполняется обязательство 2
ревью плана 3: `PPasswd` становится достижим и обязан быть скрыт.

**Files:**
- Create: `src/onecstarter/ui/dialogs/infobase.py`
- Modify: `src/onecstarter/services/model.py`
- Modify: `src/onecstarter/ui/bases/view.py` (пункт меню «Свойства…»)
- Test: `tests/unit/test_model.py` (дополнить)
- Test: `tests/ui/test_infobase_dialog.py` (создать)

**Interfaces:**
- Consumes: `security.secrets.is_secret_key` (задача 4), `services.display.version_cell`.
- Produces:
  - `model.InfobaseItem.keys: tuple[tuple[str, str], ...] = ()` — все пары
    ключ-значение секции в файловом порядке.
  - `dialogs.infobase.TYPED_KEYS: frozenset[str]` — casefold-имена ключей,
    показанных отдельными полями и потому не попадающих в таблицу «прочих».
  - `dialogs.infobase.other_keys(item: InfobaseItem) -> list[tuple[str, str]]` —
    прочие ключи с уже скрытыми секретными значениями. **Чистая, без Qt.**
  - `dialogs.infobase.InfobaseDialog(QDialog)` с конструктором
    `InfobaseDialog(item, *, groups: Sequence[str], installations, cfg_rules, parent=None)`
    и методами `name_text() -> str`, `placement_text() -> str`,
    `other_rows() -> list[tuple[str, str]]`, `version_hint() -> str`.
  - `dialogs.infobase.HIDDEN_VALUE: str = "значение скрыто"`.

- [x] **Step 1: Тест на `keys` в модели**

Дополнить `tests/unit/test_model.py`:

```python
def test_item_carries_all_section_keys_in_file_order() -> None:
    """Диалогу свойств нужны прочие ключи секции — в модели их не было.

    Порядок файловый: платформа переносит ключи при каноникализации,
    и показывать их в своём порядке значило бы врать про содержимое файла.
    """  # noqa: RUF002
    document = parse_v8i(
        '[База]\r\nConnect=File="D:\\b";\r\nVersion=8.3.25\r\nXTest=1\r\n'.encode()
    )
    item = item_from_section(document.sections[0], InfobaseSource.USER)
    assert item.keys == (("Connect", 'File="D:\\b";'), ("Version", "8.3.25"), ("XTest", "1"))
```

- [x] **Step 2: Прогнать (FAIL), добавить поле**

Run: `uv run pytest tests/unit/test_model.py -k section_keys -v`
Expected: FAIL — `AttributeError: 'InfobaseItem' object has no attribute 'keys'`

В `InfobaseItem` добавить последним полем:

```python
    # Все пары ключ-значение секции в файловом порядке. Нужны диалогу свойств:
    # типизированных полей мало, а платформа пишет свои ключи и переживает
    # чужие ([Ф] T-02.5), и пользователь вправе видеть, что лежит в его файле.
    keys: tuple[tuple[str, str], ...] = ()
```

В `item_from_section` перед `return`:

```python
    keys = tuple(
        (line.key, line.value)
        for line in section.lines
        if isinstance(line, KeyValueLine)
    )
```

и передать `keys=keys` в конструктор.

- [x] **Step 3: Тесты диалога**

Создать `tests/ui/test_infobase_dialog.py`:

```python
"""Диалог свойств записи: показ типизированных полей и прочих ключей."""

from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui.dialogs.infobase import (
    HIDDEN_VALUE,
    InfobaseDialog,
    other_keys,
)
from tests.ui.conftest import CONVENTIONS, INSTALLED  # noqa: F401


def _item(connect: str, keys: tuple[tuple[str, str], ...], **kwargs) -> InfobaseItem:
    defaults = dict(
        key="id:x", name="Бухгалтерия", folder="/", is_group=False, connect=connect,
        kind=classify_connect(connect), requested_version=None,
        section_default_version=None, app=None, source=InfobaseSource.USER,
        order=None, section_id="x", keys=keys,
    )
    return InfobaseItem(**{**defaults, **kwargs})


def test_secret_section_keys_are_hidden_not_shown() -> None:
    """PPasswd — обязательство 2 ревью плана 3, достижимое только отсюда.

    Хранение паролей вне v1 (§0 спеки 4a), поэтому значение не показывается
    и не редактируется: поле правки создало бы способ записать пароль
    в .v8i открытым текстом.
    """  # noqa: RUF002
    item = _item(
        'Srvr="s";Ref="r";',
        (("PPasswd", "AB12CD"), ("PUser", "proxy-user"), ("XTest", "1")),
    )
    assert other_keys(item) == [
        ("PPasswd", HIDDEN_VALUE),
        ("PUser", "proxy-user"),
        ("XTest", "1"),
    ]


def test_typed_keys_do_not_repeat_in_the_table() -> None:
    """Connect в таблицу не идёт вовсе: он несёт пароли и показан размещением."""
    item = _item(
        'Srvr="s";Ref="r";Pwd="secret";',
        (("Connect", 'Srvr="s";Ref="r";Pwd="secret";'), ("Version", "8.3.25"),
         ("App", "ThinClient"), ("WA", "1"), ("ID", "x"), ("OrderInList", "-1"),
         ("Folder", "/"), ("External", "0")),
    )
    shown = dict(other_keys(item))
    assert "Connect" not in shown
    assert "Version" not in shown
    assert shown == {"External": "0"}


def test_dialog_shows_placement_and_other_keys(qtbot) -> None:
    item = _item('Srvr="localhost";Ref="ACC";', (("External", "0"),))
    dialog = InfobaseDialog(item, groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.name_text() == "Бухгалтерия"
    assert dialog.placement_text() == 'Srvr="localhost";Ref="ACC"'
    assert dialog.other_rows() == [("External", "0")]


def test_dialog_warns_about_uninstalled_version(qtbot) -> None:
    """Обязательство §4 спеки 4a: подсветка была в 4a, объяснение — здесь."""
    item = _item('File="D:\\b";', (), requested_version="8.3.99.1")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert "не установлена" in dialog.version_hint()
```

- [x] **Step 4: Прогнать (FAIL), реализовать диалог**

Run: `uv run pytest tests/ui/test_infobase_dialog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.ui.dialogs.infobase'`

Создать `src/onecstarter/ui/dialogs/infobase.py`:

```python
"""Диалог записи информационной базы: свойства и добавление.

Прочие ключи секции показываются, но не правятся. Общий редактор ключей
открывает класс порчи, который наши проверки не ловят: [Ф] факт 6 скила
v8i-format — `Connect` с пробелом вокруг «=» платформа не распознаёт
и необратимо добивает секцию.

Секретные значения не показываются и не редактируются. Хранение паролей
вне v1 (§0 спеки 4a): поле правки пароля создало бы способ записать его
в .v8i открытым текстом.
"""  # noqa: RUF002

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.version import Installation
from onecstarter.security.secrets import is_secret_key
from onecstarter.services.connection import BADGE_LABELS, connection_path
from onecstarter.services.display import version_cell
from onecstarter.services.model import InfobaseItem
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

HIDDEN_VALUE = "значение скрыто"

# Ключи, показанные отдельными полями или служебные для нас. В таблицу
# «прочих» они не идут: Connect несёт пароли, ID и OrderInList — наша
# внутренняя механика, остальные дублировали бы поля выше.
TYPED_KEYS = frozenset(
    {"connect", "version", "defaultversion", "app", "wa", "id", "orderinlist", "folder"}
)


def other_keys(item: InfobaseItem) -> list[tuple[str, str]]:
    """Прочие ключи секции с уже скрытыми секретными значениями. Без Qt."""
    return [
        (name, HIDDEN_VALUE if is_secret_key(name) else value)
        for name, value in item.keys
        if name.casefold() not in TYPED_KEYS
    ]


class InfobaseDialog(QDialog):
    def __init__(
        self,
        item: InfobaseItem,
        *,
        groups: Sequence[str],
        installations: Sequence[Installation],
        cfg_rules: Sequence[DefaultVersionRule],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Свойства — {item.name}")

        self._name = QLineEdit(item.name)
        self._placement = QLineEdit(connection_path(item).text)
        self._placement.setReadOnly(True)
        self._kind = QLabel(BADGE_LABELS[item.kind])
        self._folder = QComboBox()
        self._folder.addItems(list(groups))
        self._folder.setCurrentText(item.folder)

        cell = version_cell(item, installations, cfg_rules)
        self._version = QLabel(cell.text or "как установлено")
        self._version_hint = QLabel(cell.hint or "")
        self._version_hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Имя", self._name)
        form.addRow("Размещение", self._kind)
        form.addRow("Путь", self._placement)
        form.addRow("Группа", self._folder)
        form.addRow("Версия", self._version)
        form.addRow("", self._version_hint)

        self._rows = other_keys(item)
        self._table = QTableWidget(len(self._rows), 2)
        self._table.setHorizontalHeaderLabels(["Ключ", "Значение"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (name, value) in enumerate(self._rows):
            self._table.setItem(row, 0, QTableWidgetItem(name))
            self._table.setItem(row, 1, QTableWidgetItem(value))

        # Круг правок 1: не QDialogButtonBox.StandardButton.Close — без
        # QTranslator (проект его нигде не ставит) подпись пришла бы
        # английской, «Close». russian_button_box — общий помощник задач 9-12.
        self._buttons = russian_button_box(ButtonKind.CLOSE)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Прочие ключи секции (только чтение)"))
        layout.addWidget(self._table)
        layout.addWidget(self._buttons)

    def name_text(self) -> str:
        return self._name.text()

    def placement_text(self) -> str:
        return self._placement.text()

    def other_rows(self) -> list[tuple[str, str]]:
        return list(self._rows)

    def version_hint(self) -> str:
        return f"{self._version.text()} {self._version_hint.text()}".strip()

    def button_labels(self) -> list[str]:
        """Подписи кнопок диалога — тест на регресс круга правок 1."""  # noqa: RUF002
        return [button.text() for button in self._buttons.buttons()]

    def groups_shown(self) -> list[str]:
        """Пути групп в выпадающем списке — проверка проброса параметра `groups`."""  # noqa: RUF002
        return [self._folder.itemText(i) for i in range(self._folder.count())]
```

Поля `Имя` и `Группа` в этой задаче показываются, но их изменение никуда
не сохраняется — кнопка одна, «Закрыть». Запись появляется в задаче 9.

**Общий помощник кнопок (круг правок 1).** `src/onecstarter/ui/dialogs/buttons.py`
собирает `QDialogButtonBox` с явными русскими подписями кнопок вместо
`QDialogButtonBox.StandardButton`: без установленного `QTranslator`
стандартные подписи Qt приходят по-английски (`Close`, `Ok`, `Cancel`),
а интерфейс проекта — русский (`requirements.md`, §4). `ButtonKind` знает
три роли — `CLOSE` (использована здесь), `OK`/`CANCEL` (понадобятся
диалогам добавления/правки задач 9–12). Роль кнопки (`AcceptRole`/
`RejectRole`) определяет, какой сигнал box эмитит при клике, поэтому
подмена подписи не трогает обвязку `accepted`/`rejected`. Диалоги задач
9–12 обязаны звать `russian_button_box`, а не собирать `QDialogButtonBox`
напрямую — см. ниже, раздел «Круг правок 1».

- [x] **Step 5: Пункт меню «Свойства…»**

В `BasesView._build_menu` перед разделителем избранного:

```python
        menu.addSeparator()
        menu.addAction("Свойства…", lambda: self.show_properties(key))
```

```python
    def _build_properties_dialog(self, key: str) -> InfobaseDialog | None:
        """Собрать диалог свойств без показа (для тестов и show_properties).

        Тот же приём, что у `_build_menu`/`_show_menu` (круг правок 1):
        `exec()` блокирует офскрин-тесты, поэтому сборка отделена от показа
        и проверяется отдельно — какая запись найдена, что произойдёт
        при отсутствующем ключе и что реально дошло до диалога
        (`installations`, группы).
        """
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return None
        return InfobaseDialog(
            item,
            groups=self._group_paths(),
            installations=self._installations,
            cfg_rules=self._cfg_rules,
            parent=self,
        )

    def show_properties(self, key: str) -> None:
        dialog = self._build_properties_dialog(key)
        if dialog is not None:
            dialog.exec()

    def _group_paths(self) -> list[str]:
        """Пути существующих групп плюс корень — для выпадающего списка."""
        paths = [
            group_path(item.folder, item.name)
            for item in self._workspace.items()
            if item.is_group
        ]
        return [ROOT, *sorted(set(paths))]
```

Импорт: `from onecstarter.services.paths import ROOT, group_path`.

- [x] **Step 6: Прогон, коммит, мутационная проверка**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/onecstarter tests
git commit -m "feat: диалог свойств записи; секретные ключи секции скрыты"
```

Мутация (защитный тест, обязательна): в `other_keys` убрать подстановку
`HIDDEN_VALUE` — возвращать `value` всегда.
Ожидание: падает `test_secret_section_keys_are_hidden_not_shown`.

Вторая мутация: убрать `"connect"` из `TYPED_KEYS`.
Ожидание: падает `test_typed_keys_do_not_repeat_in_the_table` —
в таблице появляется строка соединения с `Pwd="secret"`.

Факт: подтверждено, обе мутации. Правка закоммичена `bd82640`. Мутация 1
(убрана подстановка `HIDDEN_VALUE`) уронила `test_secret_section_keys_are_hidden_not_shown`
на первой же строке сравнения: `('PPasswd', 'AB12CD') != ('PPasswd', 'значение скрыто')`.
Мутация 2 (`"connect"` убран из `TYPED_KEYS`) уронила
`test_typed_keys_do_not_repeat_in_the_table` — `Connect` со значением
`Srvr="s";Ref="r";Pwd="secret";` попал в таблицу прочих ключей, пароль
утёк бы на экран открытым текстом. Обе мутации отменены
`git checkout -- src/onecstarter/ui/dialogs/infobase.py` (безопасно —
правка уже закоммичена), после каждого отката все 4 теста диалога
и полный прогон (541/541) снова зелёные.

## Круг правок 1 (ревью задачи 8)

Ревью нашло два дефекта.

1. **Кнопка «Закрыть» рисовалась как «Close».** Отчёт задачи 8 утверждал
   обратное — ошибка не в коде листинга шага 4 (план предписал его
   дословно), а в том, что план не учёл отсутствие `QTranslator`: без него
   `QDialogButtonBox.StandardButton.Close` даёт подпись Qt по умолчанию,
   английскую. Ревьюер проверил запуском
   (`.button(...).text() == 'Close'`), не по намерению кода — то же самое
   было обязано сделать исполнение задачи 8 и не сделало. Правка — общий
   помощник `src/onecstarter/ui/dialogs/buttons.py`
   (`russian_button_box(*ButtonKind)`, роли `CLOSE`/`OK`/`CANCEL`),
   листинг шага 4 выше приведён к нему. Задачи 9–12 обязаны звать эту
   функцию для своих `Ok`/`Cancel`, а не собирать `QDialogButtonBox`
   напрямую по одной подписи на диалог.
2. **Единственный путь пользователя к диалогу (`show_properties`) не был
   проверяемым.** Поиск записи, ветка отсутствующего ключа и проброс
   `installations`/групп в диалог не покрывались тестом — блокирующий
   `dialog.exec()` внутри одного метода не давал так же разделить
   «собрать» и «показать», как это уже сделано для контекстного меню
   (`_build_menu`/`_show_menu`). Правка — `_build_properties_dialog(key)`
   возвращает готовый `InfobaseDialog | None` без показа, `show_properties`
   зовёт его и делает `exec()`; листинг шага 5 выше приведён к этому виду.

Мелочь: `self._item = item` в `InfobaseDialog.__init__` сохранялось,
но нигде не читалось в задаче 8 — удалено (в задаче 9, если понадобится,
вернётся с комментарием, зачем).

Коммит круга 1: `699c3de` — fix: русская подпись кнопки диалога свойств;
сборка диалога отделена от показа.

Новые тесты: `tests/ui/test_dialog_buttons.py` (4 теста на
`russian_button_box` — подписи и что подмена не ломает `accepted`/
`rejected`), `test_close_button_label_is_russian_not_qt_default`
(`test_infobase_dialog.py`), три теста на `_build_properties_dialog`
и `test_context_menu_has_properties_action` (`test_bases_view.py`).
Полный прогон после круга — 550 тестов, `ruff` и `mypy` без замечаний.

---

### Task 9: правка записи

Диалог начинает писать (§3.1). Ключевое решение — **`Connect` не переписывается,
пока пользователь не тронул размещение**.

**Files:**
- Modify: `src/onecstarter/domain/connect.py`
- Modify: `src/onecstarter/ui/dialogs/infobase.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/unit/test_connect.py` (дополнить)
- Test: `tests/ui/test_infobase_dialog.py` (дополнить)

**Interfaces:**
- Consumes: `Workspace.update_infobase(key, changes, new_name)` (существует).
- Produces:
  - `domain.connect.replace_fragment(connect: str, name: str, value: str) -> str` —
    точечная замена значения фрагмента с сохранением всего остального текста.
  - `domain.connect.extra_fragment_names(connect: str, keep: Sequence[str]) -> list[str]` —
    имена фрагментов сверх перечисленных.
  - `dialogs.infobase.InfobaseDialog.changes() -> tuple[dict[str, str | None], str | None]` —
    пара «правки ключей секции, новое имя или None». Пустой словарь и `None` —
    пользователь ничего не менял.
  - Поля диалога, добавляемые здесь: `_app: QComboBox` (Авто / Тонкий / Толстый,
    `currentData()` даёт `None` / `"ThinClient"` / `"ThickClient"`),
    `_os_auth: QCheckBox` (пишет `WA` значением `"1"` или снимает ключ),
    `_version: QComboBox` (`currentData()` — строка версии или `None`
    для «как установлено»), и поля размещения по виду записи:
    `_file_path`, `_server`, `_ref`, `_url` (`QLineEdit`).
  - Методы для тестов, задающие значения без имитации ввода:
    `set_name(str)`, `set_folder(str)`, `set_version(str | None)`,
    `set_app(str | None)`, `set_os_auth(bool)`, `set_file_path(str)`,
    `set_server(str)`, `set_ref(str)`, `set_url(str)`.
  - `InfobaseDialog._placement_fields() -> list[tuple[str, QLineEdit]]` —
    пары «имя фрагмента, поле» для текущего вида записи:
    `FILE` → `[("File", self._file_path)]`, `SERVER` →
    `[("Srvr", self._server), ("Ref", self._ref)]`, `WEB` →
    `[("ws", self._url)]`, `UNKNOWN` → `[]` (правка размещения недоступна:
    строку соединения мы не разобрали и не знаем, что в ней менять).

- [x] **Step 1: Тесты точечной замены**

Дополнить `tests/unit/test_connect.py`:

```python
@pytest.mark.parametrize(
    ("connect", "name", "value", "expected"),
    [
        ('File="D:\\b";', "File", "E:\\c", 'File="E:\\c";'),
        # Всё, кроме значения, сохраняется дословно: пробелы, порядок, кавычки.
        ('Srvr="s"; Ref="r";Usr="admin";', "Srvr", "s2", 'Srvr="s2"; Ref="r";Usr="admin";'),
        # Значение без кавычек в исходнике остаётся без кавычек.
        ("Srvr=s;Ref=r;", "Ref", "r2", "Srvr=s;Ref=r2;"),
        # Регистр имени в файле не трогаем — сравнение регистронезависимое.
        ('srvr="s";', "Srvr", "s2", 'srvr="s2";'),
    ],
)
def test_replace_fragment_keeps_everything_else(
    connect: str, name: str, value: str, expected: str
) -> None:
    """Правка одного фрагмента не пересобирает строку соединения.

    Пересборка потеряла бы Usr, LocaleCode, wsp* и неизвестные ключи —
    то, что пользователь в неё положил и о чём мы не знаем.
    """  # noqa: RUF002
    assert replace_fragment(connect, name, value) == expected


def test_replace_fragment_rejects_unknown_name() -> None:
    with pytest.raises(KeyError):
        replace_fragment('File="D:\\b";', "Srvr", "s")


def test_extra_fragment_names_lists_what_a_kind_change_would_lose() -> None:
    names = extra_fragment_names('Srvr="s";Ref="r";Usr="admin";LocaleCode="ru";', ["Srvr", "Ref"])
    assert names == ["Usr", "LocaleCode"]
```

- [x] **Step 2: Прогнать (FAIL), реализовать в `domain/connect.py`**

Run: `uv run pytest tests/unit/test_connect.py -k fragment -v`
Expected: FAIL — `ImportError: cannot import name 'replace_fragment'`

**Круг правок 1** свёл этот листинг и `parse_connect` к одному разбору
(`_iter_raw_fragments`) — исходный вариант ниже сохранял границы фрагментов
для точечной правки корректно, но заводил их **отдельно** от `parse_connect`,
и два разбора расходились на пробелах вокруг «=» и экранированных кавычках
(разбор ниже подробностей). Актуальный код:

```python
@dataclass(frozen=True)
class FragmentSpan:
    name: str
    value_start: int
    value_end: int


@dataclass(frozen=True)
class _RawFragment:
    """Один фрагмент, разобранный один раз — общий источник для двух видов вывода."""

    name: str
    value_start: int
    value_end: int
    quoted: bool


def _iter_raw_fragments(connect: str) -> list[_RawFragment]:
    """Разбить строку на фрагменты один раз — источник и для значений, и для границ."""  # noqa: RUF002
    fragments: list[_RawFragment] = []
    start = 0
    in_quotes = False
    for position, char in enumerate([*connect, ";"]):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ";" and not in_quotes:
            fragment = _raw_fragment_of(connect, start, position)
            if fragment is not None:
                fragments.append(fragment)
            start = position + 1
    return fragments


def _raw_fragment_of(connect: str, start: int, end: int) -> _RawFragment | None:
    chunk = connect[start:end]
    separator = chunk.find("=")
    if separator < 0:
        return None
    name = chunk[:separator].strip()
    value_start = start + separator + 1
    value = connect[value_start:end]
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        open_at = value.index('"')
        close_at = value.rindex('"')
        return _RawFragment(name, value_start + open_at + 1, value_start + close_at, quoted=True)
    return _RawFragment(name, value_start, end, quoted=False)


def parse_connect(connect: str) -> list[ConnectFragment]:
    """Дружелюбный разбор: кавычки сняты, `""` развёрнуто в `"`."""  # noqa: RUF002
    fragments: list[ConnectFragment] = []
    for raw in _iter_raw_fragments(connect):
        text = connect[raw.value_start : raw.value_end]
        value = text.replace('""', '"') if raw.quoted else text.strip()
        fragments.append(ConnectFragment(name=raw.name, value=value))
    return fragments


def fragment_spans(connect: str) -> list[FragmentSpan]:
    """Границы значений фрагментов в исходном тексте, байт в байт."""  # noqa: RUF002
    return [
        FragmentSpan(raw.name, raw.value_start, raw.value_end)
        for raw in _iter_raw_fragments(connect)
    ]


def raw_fragment_value(connect: str, name: str) -> str | None:
    """Сырой (не разобранный) текст значения фрагмента — `None`, если фрагмента нет.

    То самое место, которое `replace_fragment` заменит: одинаковые границы —
    общий `_iter_raw_fragments`. Заполнять этим полем UI, а не значением
    `parse_connect`, — единственный способ, которым «поле → запись» тождественно
    по построению, а не по совпадению.
    """  # noqa: RUF002
    wanted = name.casefold()
    for raw in _iter_raw_fragments(connect):
        if raw.name.casefold() == wanted:
            return connect[raw.value_start : raw.value_end]
    return None


def replace_fragment(connect: str, name: str, value: str) -> str:
    """Заменить значение фрагмента, не тронув остальной текст.

    Сравнение имени — без учёта регистра, регистр в файле сохраняется.
    Неизвестное имя — `KeyError`: молча дописать фрагмент значило бы менять
    вид размещения там, где вызывающий просил правку значения. Вызывающий,
    которому нужна гарантия отсутствия `KeyError`, обязан сперва убедиться
    через `raw_fragment_value(connect, name) is not None`.
    """  # noqa: RUF002
    wanted = name.casefold()
    for span in fragment_spans(connect):
        if span.name.casefold() == wanted:
            return connect[: span.value_start] + value + connect[span.value_end :]
    raise KeyError(name)


def extra_fragment_names(connect: str, keep: Sequence[str]) -> list[str]:
    """Имена фрагментов сверх перечисленных — то, что потеряет смена вида."""
    kept = {name.casefold() for name in keep}
    return [
        fragment.name
        for fragment in parse_connect(connect)
        if fragment.name.casefold() not in kept
    ]
```

Исходный (до круга правок 1) листинг держал `fragment_spans`/`_span_of`
отдельно от `parse_connect` — сама арифметика границ (кавычки, экранирование)
была верна и осталась в `_raw_fragment_of` почти без изменений; разошлось
именно то, что `parse_connect` не проходил через неё вовсе. Полный разбор —
раздел «Круг правок 1» ниже.

- [x] **Step 3: Тесты правки в диалоге**

```python
def test_untouched_dialog_reports_no_changes(qtbot) -> None:
    """Открыл и закрыл — файл не тронут.

    Иначе правка версии перезаписала бы Connect и молча потеряла бы Usr,
    LocaleCode и всё, чего мы не понимаем.
    """  # noqa: RUF002
    item = _item('Srvr="s";Ref="r";Usr="admin";', (("External", "0"),))
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None)


def test_rename_only_touches_the_header(qtbot) -> None:
    item = _item('Srvr="s";Ref="r";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Бухгалтерия 3.0")
    assert dialog.changes() == ({}, "Бухгалтерия 3.0")


def test_server_edit_keeps_other_fragments(qtbot) -> None:
    item = _item('Srvr="old";Ref="r";Usr="admin";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_server("new")
    changes, name = dialog.changes()
    assert name is None
    assert changes == {"Connect": 'Srvr="new";Ref="r";Usr="admin";'}


def test_version_choice_is_written(qtbot) -> None:
    item = _item('File="D:\\b";', (), requested_version="8.3.99.1")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_version("8.3.25.1633")
    assert dialog.changes() == ({"Version": "8.3.25.1633"}, None)
```

- [x] **Step 4: Реализовать правку**

`_placement` перестаёт быть read-only и разбивается на поля по виду
(`_file_path`, `_server`, `_ref`, `_url`) — показывается набор, отвечающий
`item.kind`. Смена вида в задаче 9 **не реализуется**: она требует
предупреждения о теряемых ключах и отдельного подтверждения — выносится
в задачу 10 вместе с добавлением, где выбор вида и так есть.

`_version` становится `QComboBox` со значениями «как установлено» плюс
установленные версии; текущее — `item.requested_version` или «как установлено».

Ниже — код после обоих кругов правок (первый нашёл App/Folder, круг правок 1
нашёл единый разбор Connect и ещё четыре следствия — полный разбор в разделе
«Круг правок 1» ниже). Поля размещения в `__init__` заполняются
`raw_fragment_value(connect, name)` (сырой срез того же разбора, которым
`replace_fragment` потом заменит значение), а не `find_fragment(parse_connect(…))` —
и только для фрагментов, реально найденных в строке (`_placement_entries`,
C3); не найденный фрагмент — нередактируемое поле с пояснением, а не участник
`_placement_fields()`. `_quote_violation()`/`_on_accept()` блокируют «ОК»,
если правка добавила кавычку в поле размещения (I4).

```python
    def changes(self) -> tuple[dict[str, str | None], str | None]:
        """Что править в секции и новое имя. Пустая пара — трогать нечего."""
        changes: dict[str, str | None] = {}
        connect = self._edited_connect()
        if connect is not None and connect != self._item.connect:
            changes["Connect"] = connect
        version = self._version.currentData()
        if version != self._item.requested_version:
            changes["Version"] = version
        folder = self._folder.currentText()
        if folder != normalize_folder(self._item.folder):
            changes["Folder"] = folder
        app = self._app.currentData()
        if app != self._initial_app:
            changes["App"] = app
        wa = "1" if self._os_auth.isChecked() else None
        if wa != self._initial_wa:
            changes["WA"] = wa
        name = self._name.text().strip()
        return changes, (name if name != self._item.name else None)

    def _edited_connect(self) -> str | None:
        """Строка соединения после правки полей размещения. `None` — не трогали.

        Точечная замена, а не сборка заново: `replace_fragment` сохраняет
        порядок, пробелы, кавычки и все фрагменты, которых мы не понимаем.
        `_placement_fields` уже отфильтрован до реально найденных фрагментов
        (C3) — `replace_fragment` здесь не может поднять `KeyError`.
        """  # noqa: RUF002
        source = self._item.connect or ""
        result = source
        for name, field in self._placement_fields():
            result = replace_fragment(result, name, field.text())
        return None if result == source else result
```

**Первый круг правок (внутри задачи 9) нашёл два дефекта в этом самом коде** —
не в области `Connect`, а в сравнениях `App` и `Folder`, построенных по тому же
неверному шаблону «сравнить с сырым полем `item`»: `App=Auto` (реальное,
частое значение — платформа пишет его сама, фикстура несёт его буквально)
не совпадало бы с данными пункта «Авто» (`None`) и молча снималось бы;
`_folder.setCurrentText(item.folder)` на нередактируемом `QComboBox` молча
оставался бы на первом пункте для записи в папке без своей секции-группы,
перенося её в корень. Правки — сравнение с `self._initial_app` (данные
пункта, который комбобокс выбрал при построении) и явное добавление
`item.folder` в список перед `addItems`, если его там нет; обе защищены
регрессионными тестами и мутацией.

**Круг правок 1 нашёл, что вторая правка была неполной**: `groups` несёт
нормализованный путь без ведущего слэша, `item.folder` — сырой, с ним, и
сравнение/добавление в список без `normalize_folder` цепляло **каждую**
вложенную запись, а не только настоящую сироту (I7 — полный разбор ниже).
Формулировка «осиротевшая папка» в этом месте плана и в отчёте задачи 9
вводила в заблуждение: она называла частный случай общей причиной.

`_version` тоже подвержен этому классу дефекта, но там правка встроена в сам
список опций, а не в сравнение: если `item.requested_version` не совпадает
буквально ни с одной установленной строкой, отдельный пункт с её точным
значением добавляется при построении списка (`_version_options`) — так
`currentData()` нетронутого диалога всегда совпадает с `item.requested_version`.
Круг правок 1 добавил туда же действующую версию в подписи «как установлено»,
когда `Version` не задан вовсе (I6) — задача 8 её показывала, замена `QLabel`
на `QComboBox` в задаче 9 эту информацию потеряла.

Вызов в `BasesView.show_properties`: кнопки становятся `Ok | Cancel`,
и по `Accepted` — запись отделена в `_apply_properties` (тот же приём,
что у `_build_menu`/`_show_menu` из задачи 8: `exec()` блокирует
офскрин-тесты, поэтому применение правок тестируется отдельным вызовом).
Круг правок 1 добавил перехват `KeyError` (C3) — `dialog.changes()` не
считается безусловно успешным, граница Qt-слота обязана остаться рабочей,
даже если дисциплина фильтрации внутри диалога где-то нарушится:

```python
    def show_properties(self, key: str) -> None:
        dialog = self._build_properties_dialog(key)
        if dialog is None:
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_properties(key, dialog)

    def _apply_properties(self, key: str, dialog: InfobaseDialog) -> None:
        try:
            changes, new_name = dialog.changes()
        except KeyError as error:
            self._on_error(
                InvalidRequestError(
                    f"Не удалось прочитать правки диалога: фрагмент {error} "
                    "не найден в строке соединения"
                )
            )
            return
        if not changes and new_name is None:
            return
        try:
            self._workspace.update_infobase(key, changes, new_name)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()
```

- [x] **Step 5: Прогон, коммит, мутационная проверка**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/onecstarter tests
git commit -m "feat: правка записи; строка соединения правится точечно, а не пересобирается"
```

Мутация: в `_edited_connect` собирать строку заново из полей
(`f'Srvr="{server}";Ref="{ref}";'`) вместо `replace_fragment`.
Ожидание: падает `test_server_edit_keeps_other_fragments` — `Usr="admin"` пропал.

Вторая мутация: в `changes()` класть `Connect` всегда, без сравнения с исходным.
Ожидание: падает `test_untouched_dialog_reports_no_changes`.

Факт: подтверждено, обе мутации, после коммита `e8131f6`. Мутация 1
(`_edited_connect` для SERVER собирает `f'Srvr="{server}";Ref="{ref}";'`
вместо `replace_fragment`) уронила не только `test_server_edit_keeps_other_fragments`
(`Usr="admin"` пропал), но и `test_untouched_dialog_reports_no_changes` —
сильнее прогноза брифа: рассылка теряет `Usr` даже без правки поля, потому
что мутация безусловна для вида SERVER. Мутация 2 (`changes()` кладёт
`Connect` всегда, без сравнения с `self._item.connect`) уронила
`test_untouched_dialog_reports_no_changes`, как и предсказано, плюс ещё
9 тестов, сравнивающих `changes()` целиком словарём (лишний ключ `Connect`
ломает точное равенство). Обе мутации откачены через `git checkout --`
после коммита; `uv run pytest && uv run ruff check . && uv run mypy` —
577 тестов, чисто. Дополнительно (не требование брифа, но тот же принцип)
проверены мутацией и свои две правки: возврат сравнения `App` к `item.app`
роняет `test_untouched_dialog_with_app_auto_reports_no_changes`; возврат
`_folder` к `addItems(list(groups))` без добавления `item.folder` роняет
`test_untouched_dialog_with_orphan_folder_reports_no_changes` — обе строго
по прогнозу, обе откачены.

## Круг правок 1 (ревью задачи 9, самая сильная модель)

Ревью нашло три критических дефекта — все в коде, который бриф предписал
дословно, — и подтвердило обе самостоятельные находки исполнителя (`App=Auto`,
`Folder`) как верные, включая проверку, что настоящая правка пользователя
по-прежнему записывается.

**Корень: `domain/connect.py` держал два независимых разбора одной строки.**
`parse_connect` снимал кавычки (`_unquote` схлопывает `""` → `"`) и не обрезал
имя ключа; `fragment_spans`/`_span_of` имя обрезал и отдавал сырой текст
значения. Диалог заполнял поле первым разбором (`find_fragment(parse_connect(…))`),
писал — вторым (`replace_fragment`, через `fragment_spans`). Табличный тест
`replace_fragment` из задачи 9 (шаг 1) был и остался верным — он проверял
функцию **в отрыве** от того, как заполняется поле. Инвариант задачи не
«`replace_fragment` корректна», а **«разобрал → положил в поле → записал ==
тождество»**. Без единого действия пользователя ревьюер получил на реальном
`InfobaseDialog`: `Srvr ="s";Ref="r";` → `Srvr =""` (имя сервера стёрто,
пробел перед «=» не давал `find_fragment` найти фрагмент), заквоченное
значение с экранированной кавычкой — переписанный `Connect` с разрушенным
экранированием, `Ref="r";` без `Srvr` (SERVER по одному Ref) → `KeyError`.
Отдельно: `replace_fragment('Srvr=x";Ref=y";Usr="u";', "Srvr", "NEW")` терял
фрагмент `Ref` целиком из-за пересинхронизации чётности кавычек при
непарной кавычке в исходнике.

**Решение — один расщепитель на модуль.** `_iter_raw_fragments` разбирает
строку один раз; `parse_connect` и `fragment_spans` строятся из него.
Диалог берёт для поля **сырой срез спана** (`raw_fragment_value`), а не
результат `parse_connect`, — «поле → запись» тождественно по построению,
не по совпадению. Раскрытые сознательные изменения наблюдаемого поведения
`parse_connect` (существующие потребители — `services/launch.py`,
`services/connection.py`, `security/secrets.py`, `services/model.py`,
`domain/launch.py` — не задевает, полный прогон 610/610 подтверждает):

- имя фрагмента теперь обрезается по пробелам с обеих сторон «=» (было —
  только в пути `fragment_spans`); чинит и `find_fragment`, и `classify_connect`
  для строк вида `Srvr ="s";` (без второй, «Ref», фрагмента классификация
  раньше давала `UNKNOWN` — [Ф] измерено на этой ветке до правки);
- значение без кавычек тоже обрезается по пробелам (было — сохранялось как
  есть только если совпадало по позиции с концом фрагмента после внешнего
  `.strip()`, что зависело от места фрагмента в строке — случайное, а не
  предусмотренное поведение);
- кавычки распознаются даже когда между «=» и открывающей кавычкой есть
  пробел (было — `_unquote` проверял первый символ значения и, встретив
  пробел, не снимал кавычки вовсе, отдавая их в значении дословно).

**Дальше по находкам ревью:**

- **C3.** `_placement_fields()` предлагает для точечной правки только
  фрагменты, реально найденные в `Connect` (`_placement_entries` фильтрует
  по `raw_fragment_value(...) is not None`) — `classify_connect` даёт
  `SERVER` по наличию **любого** из `Srvr`/`Ref`, второй может отсутствовать
  или быть склеен непарной кавычкой. Не найденное поле показывается
  нередактируемым, с пояснением («не удалось разобрать для правки»), вместо
  попытки `replace_fragment` и необработанного `KeyError`.
  `BasesView._apply_properties` тоже не считает `dialog.changes()` заведомо
  успешным — `KeyError` ловится и превращается в `InvalidRequestError`
  с именем ненайденного фрагмента (не в строку соединения — инвариант 5).
- **I4.** Кавычка, которую пользователь добавил правкой поля размещения
  (сравнение — с сырым значением на момент открытия диалога, экранированная
  пара `""`, уже бывшая в файле, не в счёт), блокирует «ОК» диалоговым
  окном с объяснением. Не удваивается автоматически: правило экранирования
  кавычек в `Connect` в скиле помечено `[Д]`, экспериментом не снято —
  удвоение было бы догадкой, записанной в чужой файл. Строка соединения
  в сообщение не попадает.
- **I6.** Пункт «как установлено» в выпадающем списке версий получил
  действующую версию в скобках, когда `Version` у записи нет вовсе
  (`version_cell` всё равно резолвит её — [Ф] T-05.5). Задача 8 эту версию
  показывала как `QLabel`; замена на `QComboBox` в задаче 9 эту информацию
  молча потеряла — не только сменила виджет.
- **I7.** Формулировка «осиротевшая группа» в исходном тексте задачи 9 и
  отчёте **вводила в заблуждение** — реальная причина не в осиротевших
  папках (это отдельный, тоже настоящий случай — фикстура «Потерянная»),
  а в **несогласованных формах пути**: `_group_paths()`/`groups` отдают
  нормализованный путь без ведущего слэша (`group_path` строится через
  `normalize_folder`), а `item.folder` — сырое значение файла с ведущим
  слэшем для вложенных путей ([Ф] `render_folder`). Без сравнения через
  `normalize_folder` на обеих сторонах расхождение цепляло **каждую**
  вложенную запись (например, `Демо Розница` в `/Клиенты/Розница`), а не
  только настоящую сироту без секции-группы, и дублировало путь группы
  в выпадающем списке. Правка сравнивает и ищет текущий пункт через
  `normalize_folder` с обеих сторон.
- **M9.** `set_folder`/`set_version`/`set_app` теперь падают `ValueError`,
  если запрошенного пункта нет среди предложенных диалогом, вместо того
  чтобы молча дописывать его, — то же самое отношение «поле → запись»
  тождественно, что и у `raw_fragment_value`, было бы сломано, доверяй тест
  сеттеру, который сам подстраивается под любое значение.

**Тесты.** Табличный тест «нетронутый диалог ничего не пишет»
(`test_untouched_dialog_writes_nothing_for_edge_case_connect_strings`,
`tests/ui/test_infobase_dialog.py`), параметризованный теми же краевыми
случаями, что и `test_replace_fragment_keeps_everything_else`: экранированная
кавычка, пробел перед «=», пробел после «=» (в т.ч. перед кавычкой),
значение без кавычек с пробелами, SERVER только с `Srvr`, SERVER только
с `Ref`, непарная кавычка. Плюс: инвариант тождества на уровне домена
(`test_untouched_field_round_trips_identically`, `tests/unit/test_connect.py`,
9 случаев — тот же набор плюс комбинации), регрессии на I4/I6/I7/M9/C3,
интеграционный тест на `KeyError` из `changes()` (`test_bases_view.py`).

**Мутации.** Обязательная — сведение разборов: `parse_connect` временно
переведён на собственный (не единый) путь без обрезки имени — упали 10
тестов, включая целевой `test_parse_connect_strips_fragment_name_around_equals`.
Дополнительно (тот же принцип) проверены мутацией и остальные четыре
находки: C3 (снят фильтр в `_placement_fields()`) воспроизвёл ровно
зарепорченный `KeyError: 'Ref'`; I7 (сравнение `Folder` без `normalize_folder`)
уронил и старый тест на осиротевшую группу, и новый на обычную вложенную
запись; I4 (`_quote_violation` всегда `None`) уронил тест на добавленную
кавычку; I6 (без действующей версии в подписи) уронил регресс-тест.
Все пять мутаций откачены `git checkout --` после коммита; после каждого
отката — 610 тестов, `ruff check .` и `mypy` чисто.

Коммит круга 1: `8c00d07` — fix: единый разбор Connect чинит три критических
дефекта задачи 9.

**Остаточный риск (зафиксирован, не закрыт этим кругом).** Если исходная
строка соединения уже содержит непарную кавычку (сама по себе испорченная,
не результат правки) и пользователь **явно редактирует** поле, чей сырой
срез из-за этой непарности захватил текст соседнего фрагмента (пример:
`Srvr=x";Ref=y";Usr="u";` → правка `Srvr` теряет `Ref=y`), эта потеря не
блокируется I4 (введённый текст кавычки не содержит) и не обнаруживается
C3 (Srvr как фрагмент найден, просто его «сырой срез» шире, чем кажется).
Отличие от исходных находок ревью — здесь нужно явное действие пользователя
над уже испорченными данными, а не молчаливая порча нетронутого диалога;
риск виден (поле показывает захваченный текст дословно), но не объяснён.
Решение отложено — то же семейство ограничений, что и `redact_connect`
документирует для непарных кавычек (`security/secrets.py`). **Ре-ревью
(круг 2) подтвердило эту оценку и явно оставило риск отложенным** — заказчик
решил не расширять круг.

## Круг правок 2 (ре-ревью задачи 9)

Все шесть находок круга 1 подтверждены закрытыми — единый расщепитель
работает, тождество «разобрал → поле → записал» держится, C3/I4/I6/I7/M9
устранены. Правка круга 1 внесла три новых важных дефекта.

**1. Недекларированное изменение: хвост терялся при непарной кавычке.**
Сентинел `;`, добавленный в конец `_iter_raw_fragments`, стоял под тем же
условием `not in_quotes`, что и обычный разделитель, — при непарной кавычке
он никогда не срабатывал, и хвост строки терялся целиком, включая ИМЕНА
фрагментов, а не только их значения:
`parse_connect('File="D:\\b";Pwd=p";')` находил только `File`. Последствие —
`domain/launch.py`, `build_arguments`: сканирование имён фрагментов на
секреты переставало находить `Pwd`, и пароль ушёл бы в argv, читаемый любым
процессом пользователя (скил platform-launch, «Пароль в командной строке —
неустранимая утечка»). Недостижимо сегодня (`services/launch.py` всегда
передаёт `ib_name`, не `connect`), но единственная функция, чья работа —
не дать утечке случиться, ослаблена молча, без теста. Правка двойная:
безусловный сброс хвоста в `_iter_raw_fragments` (тот же приём, что был
в `_split_fragments` до сведения разборов к одному) — и паритетный страж
в `build_arguments` (нечётное число кавычек — отказ), тот же, что уже стоит
в `redact_connect`, не зависящий от качества разбора. Тест, который ловит
именно страж, а не восстановленный разбор: `Srvr=x";Pwd=secret;` — непарная
кавычка сдвигает `Pwd=secret` в значение `Srvr` целиком, `parse_connect`
даже после правки находит только один фрагмент, `Srvr`, — сканирование по
именам здесь бессильно в принципе, спасает только чётность кавычек.

**2. Ссылка на факт 6 скила v8i-format подпирала утверждение, которое факт 6
опровергает.** Обрезка пробелов вокруг «=» в имени фрагмента (круг правок 1)
была обоснована фактом 6 — ложно: факт 6 про ключ секции `Connect` в самом
файле `.v8i` (`config/v8i.py`, `partition("=")` без `.strip()` — уже не
обрезает), а не про фрагменты внутри значения `Connect`, и вывод факта 6
прямо противоположный обрезке: «разделять по первому = без трима имени
ключа». Терпит ли платформа пробел вокруг «=» *внутри строки соединения* —
нигде не задокументировано; непроверенное допущение уехало с меткой [Ф]
в докстринг модуля, в докстринг теста и в этот план. **Решение заказчика:
не обрезать.** `Srvr ="s";` снова классифицируется `UNKNOWN`, размещение
такой записи нередактируемо тем же путём, что и у любого другого
ненайденного фрагмента (C3) — по аналогии с фактом 6 такая секция уже
испорчена, показать её рабочей значило бы спрятать порчу, а не починить.
Единый расщепитель остался: тождество «поле → запись» от трима не зависит.
Заодно проверены (тем же вопросом — факт или допущение) ещё два изменения
из круга 1: обрезка незаквоченного значения оказалась таким же допущением
без функциональной необходимости — откачена; терпимость к пробелу между
«=» и открывающей кавычкой (`Srvr= "s" ;`) — тоже допущение, но откатить её
нельзя без разрыва уже проверенного контракта `replace_fragment`
(`test_replace_fragment_keeps_everything_else`, случай `'Srvr = "s" ;...'`
из задачи 9, шаг 1) — оставлена осознанно, помечена [Д] в докстринге.
Этот же исходный тестовый случай (пробел И перед, И после «=») пришлось
поправить: пробел перед «=» больше не совместим с решением «не обрезать»,
оставлен только пробел после «=», ради которого случай и написан.

**3. Запрет ввода закрывал кавычку, но не точку с запятой.** Воспроизведено
ревьюером через настоящий диалог: исходник `Srvr=s;Ref=r;`, пользователь
вводит в «Сервер» `s;Ref=evil` → диалог принимал ОК, и в файл уходило
`Srvr=s;Ref=r;Ref=r;` — дублированный ключ, и даже не то, что набрано.
Механизм: `_edited_connect` применяет `replace_fragment` последовательно
к промежуточной строке, поэтому правка второго поля перечитывает текст,
вписанный первым, — `;`, вписанный в одно поле размещения, создаёт для
следующего поля новый (чужой) фрагмент с тем же именем в уже изменённом
тексте. `;` — легальный символ в путях Windows и в query URL, не экзотика.
Запрет расширен на все символы, которые несут смысл в синтаксисе Connect:
`"` и `;` (`_FORBIDDEN_PLACEMENT_CHARACTERS`); метод переименован
`_quote_violation` → `_placement_violation`, возвращает `(метка, символ)`,
сообщение называет символ, строка соединения в него не попадает
(инвариант 5). **Item 4 (не покрыт сам отказ):** три теста I4 звали
`_quote_violation()` напрямую — предикат доказан, но ничто не связывало
«ввёл кавычку → диалог не принят». Добавлен тест через `_on_accept`
(`QMessageBox.warning` подменён на no-op тем же приёмом, что и у
`_build_menu`/`_show_menu` — реальное модальное окно блокирует
офскрин-тест).

**Мелочи (item 5):** разворот `classify_connect` в `UNKNOWN` для строк
с непарной кавычкой (побочный эффект бага item 1, до восстановления
безусловного сброса хвоста) нигде не был записан — задокументирован
и заодно исчез вместе с фиксом item 1 (после восстановления сброса хвоста
`classify_connect` для таких строк снова даёт `SERVER`, как и до кругов
правок). `test_unpaired_quote_has_no_editable_placement_fields` проходил
не по той причине, что заявлена в докстринге (до фильтра
`raw_fragment_value is None` дело не доходило — `classify_connect` уже
давал `UNKNOWN`), и после восстановления сброса хвоста стал бы падать
буквально — переписан под действительное поведение
(`test_unpaired_quote_offers_only_the_fragment_that_swallowed_the_tail`).
`cell.text` подставлялся в подпись «как установлено» безусловно — веб-запись
читалась как «как установлено (веб)»; подстановка теперь исключает
`ConnectKind.WEB`. Табличный тест «нетронутый диалог» дополнен до полного
набора краевых случаев `test_replace_fragment_keeps_everything_else`
(имя в нижнем регистре, пустое заквоченное/незаквоченное значение,
фрагмент без «=») — именно неполнота этого набора спрятала три критических
дефекта в прошлый раз.

**Что не тронуто:** остаточный риск правки уже испорченного (непарной
кавычкой) исходника заказчик оставил отложенным — см. выше.

Коммит круга 2: `32231d0` — fix: круг правок 2 — безусловный сброс хвоста,
отмена трима имени, запрет `;`.

Мутации (обязательны для item 1 и item 3, оба защитные):

- item 1: сентинел `;` возвращён под условие `not in_quotes` (реинтродукция
  бага) — упали 4 теста, включая `test_parse_connect_keeps_fragment_names_after_an_unpaired_quote`
  на всех трёх параметрах ревьюера. Паритетный страж `build_arguments`
  при этом остался зелёным на обоих своих тестах — подтверждает, что защита
  от утечки пароля действительно не зависит от качества разбора (сам смысл
  правки item 1).
- item 3: `;` убран из `_FORBIDDEN_PLACEMENT_CHARACTERS` — упал
  `test_semicolon_typed_by_user_is_flagged_as_a_violation`; ручная проверка
  через `changes()` на мутированном коде воспроизвела ровно зарепорченный
  результат — `{"Connect": "Srvr=s;Ref=r;Ref=r;"}`.

Обе мутации откачены `git checkout --` после коммита; после каждого отката —
627 тестов, `ruff check .` и `mypy` чисто; рабочее дерево совпадает
с коммитом (`git status --porcelain` пуст).

**Уточнение задним числом (круг правок 3): «откатить обрезку имени» и
«откатить обрезку куска целиком» — не одно и то же.** Формулировки выше
(«не обрезаем», «терпимость... тоже допущение») описывают решение верно
для обрезки ВОКРУГ «=» (имя, значение), но круг правок 2 на практике
заодно убрал и обрезку самого КУСКА целиком (пробел вокруг «;») — а она
была и до задачи 9, и её убирать было не нужно и не решено. Подробности —
раздел «Круг правок 3» ниже.

## Круг правок 3 (ре-ревью задачи 9, откат круга 2 перелетел цель)

Ре-ревью подтвердило все пять находок круга 2 закрытыми — хвост
восстановлен, паритетный страж `build_arguments` доказанно не зависит
от разбора (ревьюер подменял `parse_connect` на пустой список — страж
всё равно отказал), ложная ссылка на факт 6 вычищена везде (код, тесты,
план), `;` запрещён наравне с `"`, отказ покрыт тестом с обеих сторон
(предикат и реальный `_on_accept`). Один новый важный дефект.

**Откат круга 2 перелетел цель.** Круг 1 ввёл неверную обрезку **имени**
(`chunk[:separator].strip()`) — это была настоящая ошибка, ссылка на
факт 6 её не оправдывала. Но до задачи 9 обрезка всё же была — не имени
и не значения по отдельности, а **всего куска целиком**:

```python
# было в _split_fragments до задачи 9
return [part for part in (raw.strip() for raw in parts) if part]
```

`raw.strip()` убирал пробелы **перед именем** (после «;» — обычное
форматирование, `Srvr="s"; Ref="r";`) и **после значения** (перед «;»),
не трогая пробелы вокруг «=». Круг 1 заменил это обрезкой одного имени —
неверно. Круг 2 заменил это на полное отсутствие обрезки — тоже неверно,
в другую сторону: пробел после «; » стал частью имени следующего
фрагмента, и это прошло незамеченным, потому что нигде не было записано,
что «до задачи 9 обрезка куска была» — было сказано только про имя.

**Что ломало.** Измерено ревьюером на настоящем коде: 16 из 32
сгенерированных строк изменились.

```pycon
>>> parse_connect('Srvr="s"; Ref="r";')
[ConnectFragment(name='Srvr', value='s'), ConnectFragment(name=' Ref', value='r')]
```

Последствия: `services/connection.py` — панель показывает `Srvr="s"`
и теряет `Ref`, без пометки; `classify_connect(' File="D:\\b";')` →
`UNKNOWN` вместо `FILE`, то же для `'Usr="a"; ws="http://x/y";'` → `UNKNOWN`
вместо `WEB`, а это меняет маршрут запуска: веб-база пойдёт процессом
вместо браузера; в диалоге строка «Имя базы на сервере» становится
нередактируемой с заведомо ложным пояснением «не удалось разобрать для
правки». Ни один краевой случай в `test_connect.py` и
`test_infobase_dialog.py` не содержал формы `"; "`, поэтому тесты
молчали — та же неполнота табличных наборов, что спрятала три критических
дефекта в первом круге.

**Правка.** `_raw_fragment_of` обрезает весь кусок целиком (`raw.strip()`
на границах, как в `_split_fragments` до задачи 9), затем ищет первый «=»
уже в обрезанном тексте. Решение «не обрезать вокруг =» (круг правок 2)
остаётся нетронутым — оба решения независимы: одно про границы КУСКА
(форматирование текста между фрагментами), другое про то, что ВНУТРИ
куска (сам фрагмент). Differential-проверка (сравнение с до-задачи-9
поведением на пробеле после `;`, перед `;`, перед `=`, после `=`,
в кавычках и без) не нашла новых расхождений сверх уже записанных
решений — полный разбор в отчёте задачи 9.

**Тесты:** форма `"; "` добавлена в оба табличных набора —
`test_replace_fragment_keeps_everything_else` (round-trip) и
`test_untouched_field_round_trips_identically`, — плюс прямой тест на
`classify_connect('Srvr="s"; Ref="r";')` → `SERVER`, на `FILE`/`WEB`
с той же формой, и на то, что панель (`test_connection.py`) показывает
оба фрагмента.

**Три мелочи заодно:** WEB-запись с явным `Version` показывала в
выпадающем списке версий голое «веб» вместо самой версии — тот же
непроверенный `cell.text`, что уже чинили строкой выше в `_version_options`
(круг 2), не тронутой заодно; тест на случай `'Srvr ="s";Ref="r";'`
объяснял его причиной круга 1 («поле оставалось пустым»), хотя после
круга 2 случай уже проходит через нередактируемое размещение — комментарий
приведён к действительности; единственное сохранённое допущение `[Д]`
(терпимость к пробелу после «=» перед кавычкой) вынесено из инлайн-
комментария в докстринг модуля `domain/connect.py`, где уже описаны оба
отката.

**Что не тронуто:** остаточный риск с непарной кавычкой — отложен
заказчиком с круга 1, подтверждён кругом 2, круг не расширялся.
`security/secrets.py` ссылается на факт 6 с той же ошибкой атрибуции, но
файл вне диффа этой задачи — отложено до финального ревью.
`build_arguments` при чётном числе кавычек всё ещё может пропустить `Pwd`
внутри легитимно заквоченного значения соседнего фрагмента — тот же класс
ограничения, что `redact_connect` уже документирует, так было и до
задачи 9. Отложено.

Коммит круга 3: `601ff3c` — fix: круг правок 3 — обрезка куска целиком,
а не имени и значения отдельно.

Мутация (обязательна, защитный тест): `chunk.strip()` убран (`stripped =
raw`) — упало 8 тестов: все новые из этого круга плюс
`test_replace_fragment_keeps_everything_else`/`test_untouched_field_round_trips_identically`
на случае `"; "`. Остальные 628 тестов не пострадали. Откачена
`git checkout --` после коммита; после отката — 636 тестов, `ruff check .`
и `mypy` чисто; `git status --porcelain` пуст.

---

### Task 10: добавление записи и drag&drop каталога

§3.1. Здесь же появляется выбор вида размещения — и предупреждение о теряемых
ключах при смене вида у существующей записи.

**Files:**
- Modify: `src/onecstarter/ui/dialogs/infobase.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Modify: `src/onecstarter/ui/dialogs/buttons.py` — не было в исходном списке; добавляет
  `russian_confirm` (Да/Нет с русскими подписями кнопок, см. Step 3). `QMessageBox.question`
  из исходного текста Step 3 рисует `Yes`/`No` по-английски тем же способом, что и «Close»
  в задаче 8 (нет `QTranslator`) — тот же дефект, для нового места.
- Test: `tests/ui/test_infobase_dialog.py` (дополнить)
- Test: `tests/ui/test_bases_view.py` (дополнить) — не было в исходном списке; `add_infobase`
  и подтверждение смены вида при правке — пользовательские пути `BasesView`, без своего теста
  они остались бы без покрытия тем же способом, что ревью задачи 8 нашло у `show_properties`.

**Interfaces:**
- Consumes: `Workspace.add_infobase(name, connect, folder) -> str` (существует);
  `domain.connect.extra_fragment_names` (задача 9).
- Produces:
  - `dialogs.infobase.build_connect(kind: ConnectKind, *, file_path: str, server: str, ref: str, url: str) -> str` —
    **чистая**, строит строку соединения для новой записи или при смене вида.
  - `InfobaseDialog.for_new(groups, installations, cfg_rules, parent=None) -> InfobaseDialog` —
    конструктор режима добавления.
  - `InfobaseDialog.new_record() -> tuple[str, str, str]` — имя, строка соединения,
    группа.
  - `InfobaseDialog.kind_change_warning() -> str | None`.
  - `dialogs.infobase.browse_for_directory() -> str` и параметр конструктора
    `choose_directory: Callable[[], str]` — добавлено кругом правок 1 ревью
    (пробел плана, см. правку Step 3 ниже: спека §3.1 требовала кнопку
    «Обзор…», исходный список интерфейсов её не заявлял).
  - `ui.dialogs.buttons.build_confirm_box`/`is_confirmed`/`russian_confirm` —
    последний добавлен изначально в Step 3, первые два — кругом правок 1
    ревью (сборка/показ разнесены ради проверяемости, см. «Круг правок 1»
    в конце задачи).

- [x] **Step 1: Тесты**

Заголовок этого шага был утрачен при правке плана «по итогам реализации» ниже:
абзац про кавычки встал на его место, и листинг тестов остался без шага. Найдено
при сверке чекбоксов 09.08.2026, восстановлено — без него задача 10 выглядела
начинающейся со Step 2.

**Правка плана по итогам реализации (кавычки в `build_connect`).** Исходный текст
этого шага предлагал `value.replace('"', '""')` — удвоение кавычек при сборке
новой строки (код ниже заменён на актуальный, а не сохранён рядом: исходная
версия воспроизведена дословно в этом абзаце и в `progress.md`). Это то самое
допущение, которое задача 9 явно отвергла для точечной правки существующей записи
(`_placement_violation`, docstring `domain/connect.py`): экранирование кавычек
в `Connect` — [Д], не [Ф] (скил v8i-format, «Непроверенное»), и удвоить их самим
означало бы записать в чужой файл догадку — тот же риск, просто на новом месте кода
(сборка новой строки, а не правка старой). Решение: `build_connect` **отклоняет**
`"` и `;` в значении (`ValueError`), а не удваивает и не пропускает молча; диалог
не даёт этим символам сюда дойти тем же способом, что и раньше (`InfobaseDialog._violation`,
объединяет старую `_placement_violation` для точечной правки и новую проверку для
пересборки). Четвёртый кейс `test_build_connect` (кавычка внутри значения) заменён
на отдельный параметризованный тест отказа:

```python
@pytest.mark.parametrize(
    ("kind", "kwargs", "expected"),
    [
        (ConnectKind.FILE, {"file_path": r"D:\bases\acc"}, r'File="D:\bases\acc";'),
        (ConnectKind.SERVER, {"server": "srv", "ref": "ACC"}, 'Srvr="srv";Ref="ACC";'),
        (ConnectKind.WEB, {"url": "http://srv/b"}, 'ws="http://srv/b";'),
    ],
)
def test_build_connect(kind: ConnectKind, kwargs: dict[str, str], expected: str) -> None:
    assert build_connect(kind, **kwargs) == expected


@pytest.mark.parametrize("char", ['"', ";"])
def test_build_connect_rejects_forbidden_characters(char: str) -> None:
    with pytest.raises(ValueError, match=re.escape(char)):
        build_connect(ConnectKind.FILE, file_path=f'D:\\a{char}b')


def test_new_record_returns_name_connect_and_folder(qtbot) -> None:
    dialog = InfobaseDialog.for_new(groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\bases\acc")
    dialog.set_name("Бухгалтерия")
    dialog.set_folder("Клиенты")
    assert dialog.new_record() == ("Бухгалтерия", r'File="D:\bases\acc";', "Клиенты")


def test_dropped_directory_fills_path_and_name(qtbot) -> None:
    """Перетащили каталог — имя подставилось из его названия, если поле пустое."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.accept_directory(r"D:\bases\Бухгалтерия")
    assert dialog.new_record()[0] == "Бухгалтерия"
    assert dialog.new_record()[1] == r'File="D:\bases\Бухгалтерия";'


def test_dropped_directory_does_not_overwrite_typed_name(qtbot) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Своё имя")
    dialog.accept_directory(r"D:\bases\Бухгалтерия")
    assert dialog.new_record()[0] == "Своё имя"


def test_kind_change_warns_about_lost_keys(qtbot) -> None:
    """Смена вида перезаписывает Connect целиком — молчать об этом нельзя."""
    item = _item('Srvr="s";Ref="r";Usr="admin";LocaleCode="ru";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.kind_change_warning() is None
    dialog.set_kind(ConnectKind.FILE)
    warning = dialog.kind_change_warning()
    assert warning is not None
    assert "Usr" in warning and "LocaleCode" in warning
```

- [x] **Step 2: Прогнать (FAIL), реализовать**

Актуальный код (см. правку выше про кавычки — `_PLACEMENT_KEYS` собирается из
`_PLACEMENT_SPEC`, а не дублируется отдельным литералом, и функция отказывает
на запрещённых символах вместо удвоения):

```python
_PLACEMENT_KEYS: dict[ConnectKind, tuple[str, ...]] = {
    kind: tuple(name for _label, name in spec) for kind, spec in _PLACEMENT_SPEC.items()
}


def build_connect(
    kind: ConnectKind, *, file_path: str = "", server: str = "", ref: str = "", url: str = ""
) -> str:
    """Строка соединения для новой записи или для полной пересборки при смене вида.

    Кавычки и `;` в значении отклоняются (`ValueError`), а не удваиваются —
    экранирование кавычек в Connect не подтверждено (скил v8i-format,
    «Непроверенное»), удвоить их самим означало бы записать в чужой файл догадку.
    """  # noqa: RUF002
    if kind not in _PLACEMENT_KEYS:
        raise ValueError(f"build_connect не поддерживает вид размещения {kind}")
    values = {
        ConnectKind.FILE: (("File", file_path),),
        ConnectKind.SERVER: (("Srvr", server), ("Ref", ref)),
        ConnectKind.WEB: (("ws", url),),
    }[kind]
    for name, value in values:
        for char in _FORBIDDEN_PLACEMENT_CHARACTERS:
            if char in value:
                raise ValueError(f"{name}: значение содержит запрещённый символ ({char})")
    return "".join(f'{name}="{value}";' for name, value in values)
```

Правка плана: `_PLACEMENT_KEYS[self._item.kind]` из исходного текста поднимает
`KeyError` на записи с `item.kind is UNKNOWN` (строка соединения не разобралась
ни в один известный вид — обычное дело, есть готовый тест
`test_unknown_kind_has_no_placement_fields_to_edit`) — `.get(item.kind, ())` вместо
прямой индексации. `_kind_box` при этом сам получает четвёртый пункт с данными
`item.kind` для такой записи (в дополнение к трём обычным FILE/SERVER/WEB), иначе
`currentData()` никогда не совпал бы с `ConnectKind.UNKNOWN` и нетронутый диалог
такой записи читался бы как «вид сменили» — тот же класс дефекта (I7/M9, задача 9),
ради которого написан весь файл.

```python
    def kind_change_warning(self) -> str | None:
        """Что пропадёт при смене вида размещения. `None` — вид не менялся.

        Смена вида — не правка значения: `File=` и `Srvr=` не сосуществуют,
        строка соединения переписывается целиком, и всё, что пользователь
        в неё положил, исчезает. Сказать об этом обязаны заранее.
        """  # noqa: RUF002
        item = self._item
        if item is None:
            return None
        selected = self._kind_box.currentData()
        if selected is item.kind:
            return None
        lost = extra_fragment_names(item.connect or "", _PLACEMENT_KEYS.get(item.kind, ()))
        if not lost:
            return None
        return (
            "Смена вида размещения перезапишет строку соединения. "
            f"Будут потеряны ключи: {', '.join(lost)}"
        )
```

`accept_directory(path)` заполняет поле каталога и — только если имя пустое —
подставляет `Path(path).name`. `dragEnterEvent` принимает drop, если в
`event.mimeData().urls()` ровно один локальный путь и он каталог; `dropEvent`
зовёт `accept_directory`.

**Правка плана: нормализация разделителей пути.** `QUrl.toLocalFile()` на машине
реализации (PySide6 6.11.1, Windows) отдаёт путь с прямыми слэшами — проверено
запуском, не по документации. `.v8i` пишет пути с обратными (фикстура,
`File="C:\Bases\Demo";`), и платформа 1С не подтверждена на приём прямых —
путь из mime-данных заворачивается в `Path(...)` перед использованием
(`InfobaseDialog._dropped_directory`), которая на Windows нормализует
разделители под ОС.

**Правка плана: `_kind_box` вместо статичной подписи вида.** Исходный интерфейс
не описывал этого явно, но и добавление, и смена вида у существующей записи
требуют выбираемого элемента — прежняя `QLabel` (задачи 8–9) заменена
на `QComboBox`. Поля всех трёх видов (`_file_path`, `_server`, `_ref`, `_url`)
присутствуют в форме всегда, видна только строка выбранного вида
(`QFormLayout.setRowVisible`, метод `_update_kind_visibility`).

- [x] **Step 3: Пункт «Добавить базу…» в `BasesView`**

Пункт добавляется в контекстное меню пустого места дерева (сейчас `_show_menu`
на невалидном индексе просто выходит) и на `Ctrl+N`:

**Правка плана: build/apply-разделение, как у `show_properties`/`_apply_properties`
(задача 8, ревью).** Исходный `add_infobase` ниже зовёт блокирующий `dialog.exec()`
сразу внутри метода — тот же дефект, который ревью задачи 8 нашло у
`show_properties` («единственный пользовательский путь без покрытия»): без
разделения сборки и показа офскрин-тест не может проверить состав диалога
и запись без реального модального цикла. Актуальный код разбит на
`_build_add_dialog()` (сборка), `add_infobase()` (показ) и `_apply_new_infobase()`
(запись — вызывается и из `add_infobase()`, и напрямую из тестов):

```python
    def _build_add_dialog(self) -> InfobaseDialog:
        return InfobaseDialog.for_new(
            groups=self._group_paths(),
            installations=self._installations,
            cfg_rules=self._cfg_rules,
            parent=self,
        )

    def add_infobase(self) -> None:
        dialog = self._build_add_dialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_new_infobase(dialog)

    def _apply_new_infobase(self, dialog: InfobaseDialog) -> None:
        try:
            name, connect, folder = dialog.new_record()
        except ValueError as error:
            self._on_error(InvalidRequestError(f"Не удалось прочитать данные диалога: {error}"))
            return
        try:
            self._workspace.add_infobase(name, connect, folder)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()
```

**Правка плана (круг правок 1 ревью, п. 1 — симметрия границы исключений.)**
Первая версия `_apply_new_infobase` (выше в истории плана и в первом коммите
задачи) звала `dialog.new_record()` без единого `try`, хотя `new_record()`
зовёт тот же `build_connect`, что и `dialog.changes()` в `_apply_properties` —
а там `ValueError` уже ловился отдельным коммитом (`3b15170`) в круге 0. Ревью
поймало асимметрию: собственный тестовый набор проекта вызывает
`_apply_new_infobase` напрямую, в обход `_on_accept`, — тем же способом,
ради которого границу и укрепляли. Актуальный код (выше) ловит `ValueError`
на обоих путях одинаково.

При правке существующей записи со сменённым видом `changes()` кладёт
`Connect = build_connect(...)`, а `_apply_properties` перед записью показывает
`kind_change_warning()` через **`russian_confirm`** (не `QMessageBox.question` —
исправлено по итогам реализации: без `QTranslator` стандартные `Yes`/`No`
пришли бы по-английски, тот же дефект, что задача 8 нашла у «Close»; новый
Да/Нет-помощник — в `ui/dialogs/buttons.py`, тем же приёмом, что и `russian_button_box`)
и отменяет операцию при отказе. Заодно граница Qt-слота `_apply_properties` ловит
`ValueError` из `dialog.changes()` наравне с `KeyError`: `build_connect` при смене
вида может поднять `ValueError` на запрещённых символах, если дисциплина внутри
диалога (`_on_accept`) когда-нибудь нарушится — тот же принцип, что уже применён
к `KeyError`.

**Правка плана (круг правок 1 ревью, п. 4 — пробел декомпозиции: кнопка «Обзор…»).**
Спека §3.1 требует «обзор каталога **и** drag&drop каталога» для поля пути
файловой базы — исходный список интерфейсов и тестов этого шага заявлял только
второе, и ни один из брифов задач 10–19 кнопку не называл. Ревью нашло пробел
и указало, что он принадлежит задаче 10 (единственное место, где вообще есть
поле пути для новой/правящейся файловой записи). Добавлено:

```python
def browse_for_directory() -> str:
    """Системный диалог выбора каталога. Пустая строка — пользователь отменил."""
    return QFileDialog.getExistingDirectory()
```

`InfobaseDialog.__init__`/`for_new` принимают `choose_directory: Callable[[], str]
= browse_for_directory` — инжектируемый выбор, тем же приёмом, что и
`open_directory` в `ConnectionPanel` (`ui/bases/panel.py`), ради проверяемости
без модального `QFileDialog`. Кнопка «Обзор…» (`_browse_button`) стоит в одной
строке формы с полем пути; клик зовёт `self._choose_directory()` и, если
результат не пуст, тот же `accept_directory`, что и `dropEvent` — то же
автозаполнение имени по тем же правилам, что и у drag&drop.

- [x] **Step 4: Прогон, коммит, мутационная проверка**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/onecstarter tests
git commit -m "feat: добавление записи, drag&drop каталога, предупреждение о смене вида"
```

Мутация: в `kind_change_warning` вернуть `None` всегда.
Ожидание: падает `test_kind_change_warns_about_lost_keys`.

Факт: подтверждено. Мутация (`return None` первой строкой тела метода) уронила
`test_kind_change_warns_about_lost_keys`, как и предсказано, — и заодно
`test_declined_kind_change_confirmation_writes_nothing` (`test_bases_view.py`):
без предупреждения `_apply_properties` не спрашивает подтверждения и пишет
пересобранный `Connect` без вопроса, что сильнее прогноза брифа (задел и
интеграционный уровень, не только диалог). Правка отменена `git checkout --`
после проверки; коммит задачи 10 — `6b6aa7d`, отдельный коммит `3b15170`
(граница `_apply_properties` на `ValueError`, см. правку Step 3 выше).
670 → 671 тестов, `ruff`/`mypy` чистые.

**Круг правок 1 (ревью, коммит `bfb5471`).** Четыре замечания:

1. Граница исключений несимметрична — `_apply_new_infobase` без `try` вокруг
   `dialog.new_record()`, хотя `_apply_properties` уже ловила `ValueError`
   из того же `build_connect` (см. правку Step 3 выше). Приведено к симметрии,
   добавлен тест на запрещённый символ на пути добавления, мутация (убрать
   `try`) уронила новый тест.
2. `russian_confirm` — единственный гейт перед полной перезаписью `Connect` —
   ни разу не выполнялась в тестах (все три подменяли саму функцию лямбдой).
   Разнесена на `build_confirm_box`/`is_confirmed`/`russian_confirm`
   (`ui/dialogs/buttons.py`) тем же приёмом сборка/показ, что и у
   `InfobaseDialog.for_new`; мутация (`is_confirmed` всегда `True`) уронила
   оба новых теста на «Нет».
3. Тест нормализации разделителей пути сравнивал через `Path(...)`, что на
   Windows нечувствительно к разделителям и не поймало бы откат правки —
   заменено на строгое сравнение строк, мутация (откат `Path(...)`-обёртки
   в `_dropped_directory`) подтверждена.
4. Кнопка «Обзор…» — см. правку выше.

Мелочь: `test_declined_kind_change_confirmation_writes_nothing` сравнивал
`workspace().items()` вместо байтов файла — приведено к байтовому сравнению,
как у соседнего теста в том же файле.

Факт: все четыре пункта и мелочь исправлены, мутации 1–3 подтверждены
и отменены после проверки. 671 → 680 тестов, `ruff`/`mypy` чистые.

**Решение по кавычкам (см. правку Step 1–2 выше)**: `build_connect` отклоняет
`"` и `;` (`ValueError`), не удваивает. Черновик брифа удваивал кавычки —
это противоречило решению задачи 9 для точечной правки; при реализации выбран
запрет по аналогии с `_placement_violation`, а не новое допущение того же класса.

---

### Task 11: удаление записи

§3.2. Подтверждение с явным «файлы базы не трогаются».

**Files:**
- Create: `src/onecstarter/ui/dialogs/confirm.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/ui/test_confirm.py` (создать)
- Test: `tests/ui/test_bases_view.py` (дополнить)

**Interfaces:**
- Consumes: `Workspace.remove_infobase(key) -> bool` (существует).
- Consumes: `buttons.build_confirm_box`/`buttons.is_confirmed` (задача 10) — переиспользованы
  вместо повторной сборки `QMessageBox` (см. Step 2, «Отступление от снипета»).
- Produces:
  - `dialogs.confirm.removal_question(item: InfobaseItem) -> str` — **чистая**.
  - `dialogs.confirm.build_removal_confirm_box(parent, item) -> QMessageBox` — сборка без
    показа (тот же приём build/show, что и `build_confirm_box`), нужна отдельно, чтобы
    кнопка по умолчанию проверялась на настоящем виджете без блокирующего `exec()`.
  - `dialogs.confirm.confirm_removal(parent, item) -> bool`.
  - `BasesView.__init__(..., confirm_removal: Callable[[QWidget | None, InfobaseItem], bool]
    = confirm_removal, ...)` — параметр конструктора, не в брифе (см. Step 3).
  - `BasesView.remove_key(key: str) -> None`.

- [x] **Step 1: Тест текста подтверждения**

```python
def test_removal_question_says_files_are_untouched() -> None:
    """Пользователь обязан понимать: удаляется запись, а не база.

    В штатном стартере это единственная точка, где легко ошибиться,
    и молчание здесь дороже лишней строки.
    """  # noqa: RUF002
    text = removal_question(_item("Бухгалтерия"))
    assert "Бухгалтерия" in text
    assert "файлы базы не удаляются" in text.casefold()
```

- [x] **Step 2: Прогнать (FAIL), реализовать**

**Отступление от снипета брифа.** Снипет собирал `confirm_removal` заново через
`QMessageBox.question(...)` со стандартными `QMessageBox.StandardButton.Yes`/`.No`.
Без установленного `QTranslator` (в проекте его нигде нет) эти подписи пришли бы
по-английски — тот же класс дефекта, что и «Close» вместо «Закрыть» в задаче 8
(ревью которой и породило `buttons.py`). Задача 10 уже построила для этого
`build_confirm_box`/`is_confirmed` с русскими «Да»/«Нет» и разделением сборки
и показа — реализация переиспользует их, а не дублирует сборку `QMessageBox`:

```python
def build_removal_confirm_box(parent: QWidget | None, item: InfobaseItem) -> QMessageBox:
    box = build_confirm_box(parent, "OneCStarter", removal_question(item))
    no_button = cast(QPushButton, next(b for b in box.buttons() if b.text() == "Нет"))
    box.setDefaultButton(no_button)  # случайный Enter не должен удалить запись
    return box


def confirm_removal(parent: QWidget | None, item: InfobaseItem) -> bool:
    box = build_removal_confirm_box(parent, item)
    box.exec()
    return is_confirmed(box)
```

`removal_question` реализована как в снипете, без изменений. `build_confirm_box`
сама кнопку по умолчанию не назначает (в задаче 10 это было не нужно — там
подтверждение открывалось только по клику на пункт меню, без риска случайного
Enter), поэтому дефолт назначается здесь, для этого конкретного диалога.

- [x] **Step 3: Пункт меню и обработчик**

```python
        menu.addAction("Удалить из списка…", lambda: self.remove_key(key))
```

**Отступление от снипета брифа: инъекция, а не вызов функции модуля.**
Снипет звал `confirm_removal(self, item)` напрямую по имени модуля — тем же
способом, каким задача 10 звала `russian_confirm` в `_apply_properties`. Тот
способ там же и аукнулся: три теста `_apply_properties` подменяли `russian_confirm`
монки-патчем модульного имени, и настоящая функция (подписи кнопок, чтение клика)
не выполнялась в тестах вообще (buttons.py, «Круг правок 1»). Чтобы задача 11 не
повторила тот же круг правок, подтверждение — параметр конструктора `BasesView`,
тем же приёмом, что и `open_directory` у `ConnectionPanel`/`choose_directory`
у `InfobaseDialog`:

```python
class BasesView(QWidget):
    def __init__(
        self,
        workspace: Workspace,
        *,
        ...,
        confirm_removal: Callable[[QWidget | None, InfobaseItem], bool] = confirm_removal,
        ...,
    ) -> None:
        ...
        self._confirm_removal = confirm_removal

    def remove_key(self, key: str) -> None:
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None or not self._confirm_removal(self, item):
            return
        try:
            if not self._workspace.remove_infobase(key):
                self._on_error(
                    UnknownItemError(
                        "Запись не найдена в файле — возможно, список изменился извне. "
                        "Обновите список и повторите"
                    )
                )
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()
```

Тесты `remove_key` подставляют фейк через конструктор (`_view(..., confirm_removal=...)`),
а не монки-патчат `onecstarter.ui.bases.view.confirm_removal` — настоящая
Qt-реализация целиком проверена отдельно, в `tests/ui/test_confirm.py`, на
`build_removal_confirm_box` (подписи кнопок, кнопка по умолчанию) без
блокирующего `exec()`.

- [x] **Step 4: Прогон, коммит, мутационная проверка**

```bash
git add src/onecstarter tests
git commit -m "feat: удаление записи с явным предупреждением про файлы базы"
```

Мутация: убрать из `removal_question` предложение про файлы базы.
Ожидание: падает `test_removal_question_says_files_are_untouched`.

Вторая мутация: в `confirm_removal` вернуть `True` без вопроса.
Ожидание: падает UI-тест, проверяющий, что при отказе запись осталась
(добавить его в `test_bases_view.py`, подменив `confirm_removal` фейком).

**Противоречие брифа, вскрытое при исполнении.** Раз подтверждение —
инъекция (Step 3), тест на «отказ ничего не пишет» подставляет свой фейк
конструктору и никогда не вызывает настоящий `confirm_removal` из
`confirm.py` — мутация в нём для этого теста невидима в принципе (проверено:
после `return True` без вопроса весь набор 689/689 остаётся зелёным). Тот же
непроверяемый разрыв уже был у `russian_confirm` в задаче 10 (buttons.py,
«Круг правок 1») и там был осознанно принят: композиция «собрать + `exec()` +
прочитать клик» не тестируется в принципе (`exec()` блокирует офскрин-тест),
проверены по отдельности обе половины — `build_removal_confirm_box` (состав
кнопок, кнопка по умолчанию, `tests/ui/test_confirm.py`) и `is_confirmed`
(обе ветки клика, уже покрыта в задаче 10). Мутация п. (б) поэтому применена
не к `confirm.py`, а к тому месту, которое тест и его инъекция фактически
охраняют, — к прочтению результата в `remove_key` (`view.py`): временно
`if item is None or not self._confirm_removal(self, item): return` →
`if item is None: return`. Это и есть содержательный эквивалент «подтверждение
вернуло `True` без вопроса» с точки зрения `remove_key`, вызывающего инжектированный
колбэк, а не разбирающего, что происходит внутри него.

Факт: обе мутации подтверждены.
(а) `removal_question` без предложения про файлы — упал `test_removal_question_says_files_are_untouched`
(два соседних теста box'а остались зелёными, как и ожидалось).
(б) `confirm.confirm_removal` → `return True` (снипет брифа) — **не поймана
ни одним тестом** (689/689 зелёные) по причине выше; содержательный эквивалент
в `remove_key` (`if item is None: return`, вырезана проверка `self._confirm_removal`) —
упали `test_declined_removal_confirmation_writes_nothing` (байты файла разошлись)
и `test_confirmed_removal_deletes_the_record` (фейк не был вызван). Обе мутации
откачены (`Edit` для (а), `git checkout --` для (б) — рабочее дерево совпадало
с последним коммитом), повторный прогон — 689/689, `ruff`/`mypy` чистые.

---

### Task 12: группы — создание, переименование, перенос, удаление

§3.2–§3.3. Обязательство 3 блока Б исполняется здесь.

**Files:**
- Create: `src/onecstarter/ui/dialogs/group.py`
- Modify: `src/onecstarter/ui/dialogs/confirm.py`
- Modify: `src/onecstarter/services/display.py` — расчёт содержимого группы
  живёт здесь, рядом с деревом, а не в `connection.py`: он про узлы дерева,
  а не про строку соединения
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/unit/test_display.py` (дополнить)
- Test: `tests/ui/test_confirm.py` (дополнить)
- Test: `tests/ui/test_group_dialog.py` (создать)

**Interfaces:**
- Consumes: `Workspace.add_group`, `update_group`, `remove_group`,
  `groups.GroupRemoval` (существуют); `services.catalog.TreeNode`.
- Produces:
  - `display.group_contents(node: TreeNode) -> tuple[list[str], int, int]` —
    имена содержимого (в глубину, до 10), число записей, число подгрупп.
  - `confirm.group_removal_question(label: str, names: Sequence[str], bases: int, groups: int) -> str` —
    **чистая**.
  - `confirm.build_group_removal_box(parent, label, names, bases, groups) -> QMessageBox` —
    сборка без показа (build/show-разделение, как и у `build_removal_confirm_box`).
  - `confirm.read_group_removal(box) -> GroupRemoval | None` — чтение клика по роли
    кнопки (тот же приём, что `is_confirmed`), без `exec()`.
  - `confirm.ask_group_removal(parent, label, names, bases, groups) -> GroupRemoval | None` —
    `None` — отказ.
  - `dialogs.group.GroupDialog(QDialog)` с `GroupDialog.for_new(groups, *,
    default_folder=ROOT, parent=None)`, `GroupDialog(item, groups, *,
    default_folder=ROOT, parent=None)`, методами `name_text() -> str`,
    `parent_path() -> str`, `button_labels()`, `set_name()`/`set_parent_path()`
    для тестов. `default_folder` — сверх брифа, см. Step 4.
  - `BasesView.__init__(..., ask_group_removal: Callable[[QWidget | None, str,
    Sequence[str], int, int], GroupRemoval | None] = ask_group_removal, ...)` —
    инъекция, тот же приём, что `confirm_removal` (задача 11).
  - `BasesView.add_group(folder=ROOT)`, `rename_group(key)`, `remove_group(key)`.

**До Step 1 — сверка со «сделай так же», как просила инструкция задачи.**
Бриф предлагает `ask_group_removal` с тремя кнопками («Удалить с содержимым» /
«Поднять к родителю» / «Отмена»). `build_confirm_box` (buttons.py, задача 10)
для этого не годится: он всегда рисует ровно две кнопки с зашитыми подписями
«Да»/«Нет» под роли `YesRole`/`NoRole` — сигнатура не принимает ни число
кнопок, ни их подписи. Раздвигать её параметрами ради единственного
вызывающего значило бы тащить в общий билдер частность одного диалога, поэтому
сборка вынесена в отдельную функцию `build_group_removal_box` тем же приёмом
«build → exec → read», что и у `build_confirm_box`/`is_confirmed`, только под
три роли (`DestructiveRole`/`ActionRole`/`RejectRole`) вместо пары Yes/No.

- [x] **Step 1: Тест расчёта содержимого**

```python
@pytest.mark.parametrize(
    ("bases", "subgroups", "expect_names"),
    [(0, 0, True), (3, 1, True), (12, 0, False)],
)
def test_group_contents_lists_names_up_to_ten(
    bases: int, subgroups: int, expect_names: bool
) -> None:
    """До 10 элементов — именами, дальше — количеством.

    Обязательство 3 блока Б: платформа спрашивает «Удалить группу "имя"?»
    и каскадит молча ([Ф] T-05.9). Быть не хуже недостаточно.
    """  # noqa: RUF002
    node = _group_node(bases=bases, subgroups=subgroups)
    names, base_count, group_count = group_contents(node)
    assert base_count == bases
    assert group_count == subgroups
    assert bool(names) is (expect_names and bases + subgroups > 0)
    assert len(names) <= 10
```

Бриф не даёт реализацию тестового помощника `_group_node`. Он собран так,
что базы при наличии подгрупп кладутся ВНУТРЬ первой подгруппы, а не
прямыми детьми узла: если бы обе категории лежали одним плоским уровнем,
подсчёт «только прямые дети» (мутация шага 5) дал бы те же числа, что
и рекурсивный по всему поддереву, — тест был бы зелёным и на сломанной,
и на верной реализации. Случай `(3, 1)` поэтому — не только пример из
брифа, а единственный случай параметризации, реально проверяющий
рекурсию.

- [x] **Step 2: Реализовать `display.group_contents`**

```python
CONTENT_NAME_LIMIT = 10


def group_contents(node: TreeNode) -> tuple[list[str], int, int]:
    """Что лежит в группе: имена (до 10), число баз, число подгрупп.

    Считается по всему поддереву, а не по прямым детям: удаление каскадное
    ([Ф] T-05.9), и «пусто на первом уровне» ничего не обещает.
    """  # noqa: RUF002
    names: list[str] = []
    bases = 0
    groups = 0

    def walk(children: Sequence[TreeNode]) -> None:
        nonlocal bases, groups
        for child in children:
            if child.item is not None and not child.item.is_group:
                bases += 1
            else:
                groups += 1
            names.append(child.label)
            walk(child.children)

    walk(node.children)
    return (names if len(names) <= CONTENT_NAME_LIMIT else []), bases, groups
```

- [x] **Step 3: Тест и реализация текста подтверждения**

```python
def test_group_removal_question_lists_contents() -> None:
    text = group_removal_question("Клиенты", ["Альфа", "Бета"], 2, 0)
    assert "Альфа" in text and "Бета" in text


def test_group_removal_question_falls_back_to_counts() -> None:
    text = group_removal_question("Клиенты", [], 12, 3)
    assert "12" in text and "3" in text


def test_empty_group_question_says_it_is_empty() -> None:
    assert "пуста" in group_removal_question("Клиенты", [], 0, 0).casefold()
```

```python
def group_removal_question(
    label: str, names: Sequence[str], bases: int, groups: int
) -> str:
    head = f"Удалить группу «{label}»?"
    if not bases and not groups:
        return f"{head}\n\nГруппа пуста."
    if names:
        listed = "\n".join(f"  • {name}" for name in names)
        body = f"В группе и её подгруппах:\n{listed}"
    else:
        body = (
            f"В группе и её подгруппах: записей — {bases}, вложенных групп — {groups}."
        )
    return (
        f"{head}\n\n{body}\n\n"
        "Выберите, что сделать с содержимым. Файлы баз не удаляются "
        "и не изменяются."
    )
```

`ask_group_removal` строит `QMessageBox` с тремя кнопками: «Удалить с содержимым»
(`RECURSIVE`), «Поднять к родителю» (`PROMOTE`), «Отмена» (`None`). Кнопка
по умолчанию — «Отмена». Реализовано как задумано: `build_group_removal_box`
(сборка, роли `DestructiveRole`/`ActionRole`/`RejectRole`) / `read_group_removal`
(чтение клика по роли, тот же приём, что `is_confirmed`) / `ask_group_removal`
(build → exec → read) — три отдельные функции вместо одной, чтобы состав кнопок
и чтение клика проверялись без блокирующего `exec()` (`tests/ui/test_confirm.py`
кликает по кнопкам напрямую, тем же приёмом, что `test_dialog_buttons.py` для
`is_confirmed`).

- [x] **Step 4: `GroupDialog` и пункты меню**

Диалог из двух полей: имя (валидация — без `/`, непустое) и родитель
(выпадающий список путей). Пункты меню дерева: «Создать группу…»,
«Переименовать группу…», «Удалить группу…». Для неявного узла (`row.item is None`)
все три недоступны с пояснением в тултипе: у него нет секции и ключа
([Ф] T-05.7).

Обработчики зовут `add_group` / `update_group` / `remove_group` и `rebuild()`;
`ServicesError` уходит в `self._on_error`.

Реализовано с тремя уточнениями сверх текста брифа:

1. **`GroupDialog.for_new`/`__init__` получили keyword-only `default_folder: str
   = ROOT`.** Брифовская сигнатура `for_new(groups, parent=None)` не даёт
   способа предложить группе-родителю не корень, а группу, из чьего
   контекстного меню открыт диалог («Создать группу…» на строке «Клиенты»
   обязана предлагать «Клиенты», а не заставлять пользователя выбирать это
   из списка вручную). Позиционная часть сигнатуры (`item`/`groups`) не
   тронута, `default_folder` — обратимо совместимое добавление.
2. **`setToolTipsVisible(True)` на меню неявного узла.** Без него `QMenu`
   на этой платформе не показывает тултипы пунктов вовсе, даже если текст
   в `setToolTip` есть, — проверено запуском (`test_implicit_group_context_
   menu_disables_all_three_actions`), не по документации.
3. **Защита от «группа не найдена» вместо честного «только для чтения».**
   `Workspace.tree()` строится только по пользовательскому источнику —
   группа из общего списка (`InfobaseSource.COMMON`) в нём не найдётся.
   Без явной проверки `remove_group` показал бы вводящее в заблуждение
   «группа не найдена в дереве» вместо содержательного «доступна только
   для чтения» — добавлена ранняя проверка `item.source is
   InfobaseSource.COMMON` → `ReadOnlySourceError` до похода в
   `_find_group_node`. Не покрыто отдельным тестом (постройка
   common-list-фикстуры в `tests/ui/conftest.py` не входит в объём
   задачи) — риск низкий (три строки, `_reject_common` тот же путь уже
   покрыт для записей задачами 8–11), см. «Замечания» отчёта.

- [x] **Step 5: Прогон, коммит, мутационная проверка**

```bash
git add src/onecstarter tests
git commit -m "feat: операции над группами; удаление перечисляет содержимое"
```

Мутация (обязательна): в `group_removal_question` убрать блок с содержимым,
оставить только «Удалить группу «имя»?» — то есть повторить платформу.
Ожидание: падают `test_group_removal_question_lists_contents` и
`test_group_removal_question_falls_back_to_counts`.

Вторая мутация: в `group_contents` считать только прямых детей (убрать
рекурсию `walk(child.children)`).
Ожидание: падает тест с подгруппой — числа не сходятся.

Факт: обе мутации подтверждены, коммит `2238377`.

(а) `group_removal_question` → только `head` (без блока содержимого).
Упали ровно `test_group_removal_question_lists_contents` и
`test_group_removal_question_falls_back_to_counts`, как и ожидал бриф,
плюс третий тест того же файла — `test_empty_group_question_says_it_is_empty`
(тоже опирался на убранный текст) — более сильный результат, не расхождение
с ожиданием. Остальные 9 тестов `test_confirm.py` остались зелёными.

(б) `group_contents` → строка `walk(child.children)` закомментирована.
Упал `test_group_contents_lists_names_up_to_ten[3-1-True]` (`base_count`:
0 вместо 3) — единственный параметризованный случай с подгруппой, как
и предсказывал бриф. Дополнительно (сверх требования брифа) упал ещё один,
не входивший в мутационный план тест — `test_remove_group_asks_with_
recursively_computed_contents` (`tests/ui/test_bases_view.py`, интеграционный,
на реальной фикстуре `anonymized.v8i`, группа «Клиенты» с базой внутри
подгруппы «Розница»): `bases` = 1 вместо 2. Это подтверждает рекурсию
на настоящем дереве, а не только на синтетическом `_group_node`, — вторая,
независимая линия защиты той же гарантии.

Обе мутации откачены `Edit` до текста коммита `2238377`, `git diff --stat`
после отката — пусто. Повторный прогон: 728/728, `ruff check .` и
`uv run mypy` чистые.

## Круг правок 1 (ревью на сильной модели, коммит `8ee1fcb`)

Ядро задачи (рекурсия, различение `PROMOTE`/`RECURSIVE`, побайтовая
сохранность при отказе, блокировка неявного узла тремя барьерами, расчёт
по `Workspace.tree()`, а не по display-лесу) ревью подтвердило разбором.
Два важных замечания и четыре мелочи:

1. **`box.text()` не проверялся ничем.** `group_removal_question` была
   защищена табличным тестом, но единственный путь её результата
   к пользователю (`build_group_removal_box`: `box.setText(...)`) — нет:
   подмена на голый вопрос («буквальное повторение платформы», мутация (а)
   шага 5, только этажом выше) оставляла бы зелёными все 12 тестов
   `test_confirm.py` и все 18 тестов вида. Добавлены
   `test_group_removal_box_shows_the_question_text`/
   `test_group_removal_box_text_falls_back_to_counts` — читают `box.text()`
   без показа (не тот разрыв `exec()`, что официально принят для клика).

2. **Группа общего списка получала полное меню группы.** «Удалить группу…»
   была защищена собственным guard'ом в `remove_group` (ловил
   `InfobaseSource.COMMON` и отвечал `ReadOnlySourceError`) — верно
   и достижимо, `_find_group_node` не находит группу общего списка
   (`Workspace.tree()` строится только по пользовательскому источнику)
   и без проверки выдал бы вводящее в заблуждение «группа не найдена».
   Но «Переименовать группу…» открывала диалог и падала `ReadOnlySourceError`
   только после «ОК», а «Создать группу…» вела к `InvalidRequestError`
   «Группы «X» в списке нет» про группу прямо на экране пользователя —
   тот же класс сообщения, который для удаления был уже исправлен.
   Причина глубже одного недостающего guard'а: `_group_paths()`
   (переиспользуется `GroupDialog` и `InfobaseDialog`) включала пути
   общих групп без фильтра, и тот же тупик был достижим из корневого
   «Создать группу…».

   **Структурная правка вместо трёх отдельных guard'ов:**
   - `_group_paths()` отфильтрован до `item.source is InfobaseSource.USER` —
     правило одно на оба потребителя (`GroupDialog`/`InfobaseDialog`).
   - `_build_disabled_group_menu(note)` — общий билдер трёх неактивных
     пунктов с пояснением, вынесенный из `_build_implicit_group_menu`
     (было её собственным телом).
   - `_group_menu_for(item, key)` — новая, единственная точка решения:
     группа общего списка получает `_build_disabled_group_menu(COMMON_NOTE)`,
     пользовательская — полное `_build_group_menu`. `_show_menu` зовёт её
     вместо `_build_group_menu` напрямую.
   - `remove_group` сохраняет собственную проверку `InfobaseSource.COMMON`
     как последний рубеж (метод достижим напрямую, в обход меню) — она
     больше не единственная защита, но и не выброшена; добавлен прямой
     тест `test_remove_group_refuses_common_list_group`.
   - Новая фикстура `tests/ui/conftest.py::common_group_cfg_paths` —
     синтетический общий список (тот же приём, что `_with_common_list`
     в `tests/unit/test_workspace.py`: `1cestart.cfg` в UTF-16LE с BOM,
     собирается на лету в `tmp_path`, ничего не попадает в
     `tests/fixtures/`) — понадобится и задаче 14 (перетаскивание записи
     из общего списка упирается в тот же угол).

   Не тронуто намеренно (явно отложено ревью до финального прохода):
   извлечение `_menu_for(index)` как единого диспетчера всех видов строк —
   более широкий рефакторинг, чем нужен для этой находки.

Мелочи (нумерация замечаний брифа сохранена — 1 и 2 заняты структурной
правкой выше):

- **3.** Тесты на пустое имя и `/` в `GroupDialog` проверяли только факт
  блокировки (`result() == 0`), не содержание объяснения — реализация,
  молча вернувшая управление, тоже прошла бы. `QMessageBox.warning` теперь
  монки-патчится на запись аргументов, тексты проверяются по содержанию
  («пуст»/«/»).
- **4.** Граница `CONTENT_NAME_LIMIT` (10) не была проверена —
  параметризация брала 3 и 12, ошибка на единицу (`<` вместо `<=`) была бы
  невидима. Добавлены случаи `(10, 0, True)`/`(11, 0, False)`.
- **5.** Список содержимого не различал базы и подгруппы («Розница» и «Демо
  Розница» неотличимы, хотя первое — группа, а второе — база внутри неё).
  `group_contents` помечает подгруппы `GROUP_CONTENT_MARK = " (группа)"`;
  `test_remove_group_asks_with_recursively_computed_contents` обновлён
  под новый формат имён.
- **6.** `remove_group` не проверял `item.is_group` — ключ базы прошёл бы
  как пустая группа («Удалить группу "Демо Розница"? Группа пуста.») и
  только потом упал бы `InvalidRequestError` из `services`. Две строки
  в самом опасном методе задачи.

В smoke №2 (`task-12-report.md`) добавлен пункт: `PROMOTE` может отказать
уже после выбора пользователя, если у родителя есть подгруппа-тёзка
(`_require_promotion_is_free` в `services/groups.py`) — кнопка предлагается
без знания об исходе, заказчику стоит увидеть этот случай вживую.

Факт: оба замечания и все четыре мелочи исправлены. Мутации подтверждены
и отменены после проверки (все — до текста коммита `8ee1fcb`,
`git diff --stat` после каждого отката — пусто):

- (1) `box.setText` → голый вопрос: упали оба новых теста `box.text()`.
- (2а) `_group_menu_for` без проверки источника: упал
  `test_common_group_context_menu_disables_all_three_actions`.
- (2б) `_group_paths()` без фильтра источника: упал
  `test_group_paths_excludes_common_list_groups`.
- (guard `remove_group`) проверка `InfobaseSource.COMMON` убрана: упал
  `test_remove_group_refuses_common_list_group` — вместо `ReadOnlySourceError`
  пришёл `UnknownItemError` с текстом «не найдена», ровно то сообщение,
  от которого guard защищает.
- (5) `GROUP_CONTENT_MARK` убран: упали `test_group_contents_marks_
  subgroups_not_bases` (синтетический) и
  `test_remove_group_asks_with_recursively_computed_contents`
  (интеграционный, на реальной фикстуре) — независимое подтверждение
  на двух уровнях.
- (6) проверка `item.is_group` в `remove_group` убрана: упал
  `test_remove_group_rejects_a_base_key`.
- (4) `<=` → `<` в `group_contents`: упал ровно граничный случай
  `test_group_contents_lists_names_up_to_ten[10-0-True]`.
- (3) текст предупреждений `GroupDialog` заменён на общий «Ошибка. Нельзя.»:
  упали оба теста `test_accept_rejects_*`.

738/738 (было 728), `ruff check .` и `uv run mypy` чистые.

---

### Task 13: секция с пустым `Connect=`

§3.3, обязательство 4 блока Б. Такая секция уже показывается группой
(`is_group = not connect`), но пользователь не знает, что при первой же
перезаписи платформа её «канонизирует» с потерей `Version` ([Ф] T-05.6).

**Files:**
- Modify: `src/onecstarter/services/display.py`
- Modify: `src/onecstarter/ui/dialogs/group.py`
- Test: `tests/unit/test_display.py` (дополнить)
- Test: `tests/ui/test_group_dialog.py` (дополнить)

**Interfaces:**
- Produces: `display.EMPTY_CONNECT_NOTE: str`; `display.is_degraded_group(item) -> bool`.

- [x] **Step 1: Тесты**

```python
@pytest.mark.parametrize(
    ("connect", "degraded"),
    [(None, False), ("", True), ('Srvr="s";', False)],
)
def test_is_degraded_group(connect: str | None, degraded: bool) -> None:
    """Пустой Connect= отличается от отсутствующего.

    Обе секции платформа показывает группой ([Ф] T-05.6), но у первой
    первая же перезапись удалит Connect= и вычистит Version. Настоящая
    группа этого не переживает — ей нечего терять.
    """  # noqa: RUF002
    assert is_degraded_group(_group_item(connect=connect)) is degraded


def test_degraded_group_row_carries_a_warning() -> None:
    rows = display_forest([_group_item(connect="")], build_tree([_group_item(connect="")]), [])
    assert EMPTY_CONNECT_NOTE in (rows[0].note or "")
```

- [x] **Step 2: Реализация в `display.py`**

```python
EMPTY_CONNECT_NOTE = (
    "У секции пустой ключ Connect=. Платформа показывает её группой, "
    "но при первой же перезаписи удалит Connect= и вычистит Version."
)


def is_degraded_group(item: InfobaseItem) -> bool:
    """Секция-группа с пустым `Connect=`, а не с отсутствующим ключом.

    `is_group` у обеих True ([Ф] T-05.6), различает их только пустая строка
    против `None`: `V8iSection.connect` возвращает значение ключа как есть.
    """  # noqa: RUF002
    return item.is_group and item.connect == ""
```

`_base_note` дополняется веткой:

```python
    if is_degraded_group(item):
        parts.append(EMPTY_CONNECT_NOTE)
```

- [x] **Step 3: Предупреждение в `GroupDialog`**

Открытый на такой секции диалог показывает `EMPTY_CONNECT_NOTE` строкой
над полями. Тест на одном лишь `GroupDialog(item, groups=["/"]).warning_text()`
недостаточен: `warning_text()` доказывает, что `QLabel` держит текст,
а не что виджет попал в раскладку диалога — `layout.addWidget(self._warning)`
вызывается условно, и мутация, ломающая только это условие, оставила бы
такой тест зелёным (найдено ревью задачи 13, круг правок 1). Нужны обе
проверки: `warning_text()` содержит «вычистит Version» **и**
`GroupDialog.warning_shown()` (или эквивалент — проверка членства
`self._warning` в `self.layout()`) возвращает `True`; для обычной группы
и для `for_new` — `warning_shown()` возвращает `False`.

- [x] **Step 4: Прогон, коммит, мутационная проверка**

```bash
git add src/onecstarter tests
git commit -m "feat: секция с пустым Connect= помечена предупреждением о вычистке Version"
```

Мутация: в `is_degraded_group` вернуть `item.is_group` (снять различение
пустой строки и `None`). Ожидание: падает табличный тест на `connect=None` —
у настоящей группы появилось чужое предупреждение.

Факт: коммит `684ffb5`, 745/745 тестов, `ruff`/`mypy` чистые. Мутация
`is_degraded_group → item.is_group` уронила 3 теста (оба граничных случая
табличного `test_is_degraded_group` и `test_ordinary_group_dialog_has_no_connect_warning`) —
как и предсказывал бриф.

Круг правок 1 ревью: первая версия второй (самостоятельной) мутации
проверяла только доставку текста в объект `QLabel`
(`self._warning.text()`), а не в раскладку диалога — `warning_text()`
не отличает виджет, реально показанный пользователю, от виджета,
существующего с правильным текстом, но не добавленного в `layout()`
(`layout.addWidget(self._warning)` вызывается условно). Добавлен
`GroupDialog.warning_shown()` (коммит `6a3b728`), проверяющий
`self.layout().indexOf(self._warning) != -1`. Мутация повторена в двух
формах: (а) текст не попадает в объект — падает; (б) объект не попадает
в раскладку (текст при этом остаётся правильным) — тоже падает, и падает
именно на `warning_shown()`, а не на `warning_text()` (вручную подтверждено:
`warning_text()` при мутации (б) по-прежнему возвращает корректный текст).
Обе ступени мутации откачены, рабочее дерево после отката совпадает
с коммитом `6a3b728` (`git status --short` пуст), полный прогон и линтеры
чистые. Проверка того же класса дефекта в соседних файлах задачи
(`display.py`, `group.py`) не нашла второго случая; в `infobase.py`
(задачи 8–12, не в этом плане) найден похожий, но не идентичный узор —
передано в финальное ревью. Подробности — `task-13-report.md`.

---

### Task 14: перемещение по группам перетаскиванием

§3.3. Qt строки **не двигает сам**: перехватываем drop, зовём операцию
`services`, пересобираем из `Workspace`. Иначе при отказе операции модель
и файл разъедутся.

**Files:**
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `Workspace.update_infobase`, `Workspace.update_group` (существуют).
- Produces:
  - `bases.view.DropTarget` — `Enum` со значениями `INTO = "into"`,
    `BEFORE = "before"`, `AFTER = "after"`.
  - `BasesView.handle_drop(source_key: str, target_key: str | None, where: DropTarget, *,`
    `target_is_implicit: bool = False, target_is_virtual: bool = False) -> None` —
    точка, которую зовёт и Qt, и тест. Настоящий drag в offscreen не
    подделать. Оба флага оставлены отдельными параметрами при исполнении
    (см. «Факт» и «Круг правок 1» ниже): `target_key is None` означает три
    разных исхода — «корень», «неявный узел» и «заголовок ветки/строка
    ошибки общего списка», — а гейт различает их по `KIND_ROLE` строки
    под курсором (`IMPLICIT_GROUP` → `target_is_implicit`,
    `SECTION`/`NOTE` → `target_is_virtual`), не по одному пустому `KEY_ROLE`.

- [x] **Step 1: Тесты**

```python
def test_drop_into_group_changes_folder(qtbot, workspace_factory) -> None:
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    base = next(i for i in workspace.items() if not i.is_group and i.folder == "/")
    group = next(i for i in workspace.items() if i.is_group)

    view.handle_drop(base.key, group.key, DropTarget.INTO)

    moved = next(i for i in workspace.items() if i.key == base.key)
    assert moved.folder == render_folder(group_path(group.folder, group.name))


def test_drop_into_root_moves_out_of_group(qtbot, workspace_factory) -> None:
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(view)
    nested = next(i for i in workspace.items() if not i.is_group and i.folder != "/")

    view.handle_drop(nested.key, None, DropTarget.INTO)

    assert next(i for i in workspace.items() if i.key == nested.key).folder == "/"


def test_drop_onto_implicit_node_is_refused(qtbot, workspace_factory) -> None:
    """У неявного узла нет секции и ключа — операции над ним невозможны.

    [Ф] T-05.7: платформа рисует такой узел из висячего Folder, секции
    для него не создаёт. Молча положить туда запись значило бы создать
    висячий Folder уже своими руками.
    """  # noqa: RUF002
    workspace, _calls, _opened = workspace_factory()
    errors: list[ServicesError] = []
    view = BasesView(
        workspace, installations=INSTALLED, cfg_rules=[], on_error=errors.append
    )
    qtbot.addWidget(view)
    base = next(i for i in workspace.items() if not i.is_group)
    before = base.folder

    view.handle_drop(base.key, None, DropTarget.INTO, target_is_implicit=True)

    assert next(i for i in workspace.items() if i.key == base.key).folder == before
    assert len(errors) == 1


def test_drop_of_common_record_is_refused(qtbot, workspace_factory) -> None:
    """Общий список только для чтения — отказ приходит из services.

    Проверка стоит в UI, а не только в services: без неё перетаскивание
    выглядело бы удавшимся (Qt нарисовал бы перенос), а файл остался бы
    прежним. Дерево обязано пересобраться и вернуть запись на место.
    """  # noqa: RUF002
    workspace, _calls, _opened = workspace_factory()
    errors: list[ServicesError] = []
    view = BasesView(
        workspace, installations=INSTALLED, cfg_rules=[], on_error=errors.append
    )
    qtbot.addWidget(view)

    common = InfobaseItem(
        key="id:common", name="Общая", folder="/", is_group=False,
        connect='Srvr="s";Ref="r";', kind=ConnectKind.SERVER, requested_version=None,
        section_default_version=None, app=None, source=InfobaseSource.COMMON,
        order=None, section_id="common",
    )
    monkeypatched = [*workspace.items(), common]
    with mock.patch.object(workspace, "items", return_value=monkeypatched):
        group = next(i for i in monkeypatched if i.is_group)
        view.handle_drop(common.key, group.key, DropTarget.INTO)

    assert len(errors) == 1
    assert isinstance(errors[0], ReadOnlySourceError)
```

- [x] **Step 2: Реализация**

```python
class DropTarget(Enum):
    INTO = "into"
    BEFORE = "before"
    AFTER = "after"


    def handle_drop(
        self,
        source_key: str,
        target_key: str | None,
        where: DropTarget,
        *,
        target_is_implicit: bool = False,
    ) -> None:
        """Перенести запись или группу. Модель пересобирается из Workspace.

        Qt строки не двигает сам: при отказе операции его перестановка
        осталась бы на экране, а файл — прежним, и пользователь увидел бы
        то, чего в списке нет.
        """  # noqa: RUF002
        if target_is_implicit:
            self._on_error(
                InvalidRequestError(
                    "Этой группы нет в файле — есть только путь Folder. "
                    "Создайте группу с тем же именем, чтобы класть в неё записи"
                )
            )
            return
        folder = self._folder_of_drop(target_key, where)
        if folder is None:
            return
        source = next((i for i in self._workspace.items() if i.key == source_key), None)
        if source is None:
            return
        try:
            if source.is_group:
                self._workspace.update_group(source_key, new_folder=folder)
            else:
                self._workspace.update_infobase(source_key, {"Folder": folder})
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()
```

`_folder_of_drop` для `INTO` даёт собственный путь целевой группы (или `ROOT`
при `target_key is None`), для `BEFORE`/`AFTER` — путь родителя цели.

**[Р] Ограничение v1:** `BEFORE`/`AFTER` меняют только группу, но не позицию,
когда цель лежит в другой группе. Перестановка внутри группы — задача 15;
совмещать перенос и позицию в одном жесте значило бы два патча и две записи
в файл ради одного перетаскивания. Записать это в §12 спеки при исполнении
задачи (правило `CLAUDE.md`: план и спека правятся вслед за находкой).

Дерево получает `setDragEnabled(True)`, `setAcceptDrops(True)`,
`setDropIndicatorShown(True)` и подкласс `QTreeView`, чей `dropEvent` читает
`indexAt(event.position())` и `dropIndicatorPosition()`, переводит их в
`(target_key, where, target_is_implicit)` и зовёт `handle_drop`. Событие
всегда `ignore()`-ится в конце: перестановку делает `rebuild`, а не Qt.

- [x] **Step 3: Прогон, коммит, мутационная проверка**

```bash
git add src/onecstarter/ui/bases/view.py tests/ui/test_bases_view.py
git commit -m "feat: перенос записей и групп перетаскиванием"
```

Мутация: убрать ветку `target_is_implicit`. Ожидание: падает
`test_drop_onto_implicit_node_is_refused`.

Вторая мутация: в `dropEvent` вызвать `super().dropEvent(event)` вместо
`ignore()`. Ожидание: падает тест, проверяющий, что при отказе операции
дерево не изменилось (добавить его, подменив `update_infobase` на бросающий
`ReadOnlySourceError`).

Факт: Реализовано в основном по наброску, с тремя проверенными отклонениями.

1. **`target_is_implicit` оставлен отдельным параметром** (вопрос из "Before You
   Begin"): барьер `KEY_ROLE is None` структурный, но `target_key is None`
   означает два разных исхода — «отпустили в пустом месте, корень» (операция
   разрешена) и «отпустили на неявном узле» (отказ). Различает их только
   отдельный флаг; `dropEvent` вычисляет его по `KEY_ROLE` строки под курсором.
2. **`dropEvent` не использует `dropIndicatorPosition()`.** Экспериментом
   подтверждено: тот геттер Qt обновляет только штатный `dragMoveEvent`, и
   только когда `canDrop()` его примет — а `canDrop()` в режиме `InternalMove`
   требует `event.source() is self`, которое из Python не выставить. Событие,
   собранное вручную в тесте, всегда осталось бы с `dropIndicatorPosition()` на
   значении по умолчанию — перевод остался бы непроверяемым, ровно та ловушка,
   которой посвящена задача. Вместо этого `_where_at` считает сторону сама, по
   `visualRect()` (не зависит от состояния перетаскивания, тот же результат).
   Дерево получает `setDragDropMode(InternalMove)` — без него `super()`
   молча выполнял бы посторонние drop'ы; это тоже проверено экспериментом.
3. **Цель `INTO`/`BEFORE`/`AFTER` фильтруется по `InfobaseSource.USER`**
   (`_folder_of_drop`), тем же структурным приёмом, что `_group_paths()`
   у задачи 12: без фильтра `services` отказывал бы группе общего списка
   с «Группы «X» в списке нет» — верно по факту, вводит в заблуждение
   пользователя, который эту группу видит на экране. Добавлен тест
   (`test_drop_onto_common_list_group_is_a_structural_no_op`) и фикстура
   `common_base_cfg_paths` в `tests/ui/conftest.py` (для записи из общего
   списка — `common_group_cfg_paths` несёт только группу).

Найден и исправлен дефект в тесте самого наброска: `test_drop_of_common_record_is_refused`
из Step 1 подменяет `workspace.items()` через `mock.patch.object`, но
`Workspace._reject_common` читает внутренний `_items`, а не `items()`, — с
подменой только витрины запись остаётся невидимой для проверки, и вместо
`ReadOnlySourceError` тест ловит `TargetGoneError` (запись не найдена в
документе). Тест переписан на настоящий общий список через новую фикстуру
`common_base_cfg_paths` — воспроизведено (тест падал на исходной версии),
исправлено, перепроверено.

Мутационная проверка (обе — по протоколу CLAUDE.md, откат после каждой):
убранная ветка `target_is_implicit` в `handle_drop` — упал
`test_drop_onto_implicit_node_is_refused` (`AssertionError`, ожидалась 1
ошибка, пришло 0), откат. `super().dropEvent(event)` вместо `event.ignore()`
в конце `dropEvent` — упал `test_drop_event_never_lets_qt_move_rows_itself`:
у цели («Клиенты») после отказа операции стало 3 потомка вместо 2 —
`super()` вставил в уже пересобранную `rebuild()`-ом модель лишнего ребёнка,
собранного из чужого mime-содержимого, откат.

Дополнительно к четырём тестам Step 1 написаны: `handle_drop` для BEFORE/AFTER
(родитель цели), для общего списка как цели, для INTO на запись (не группу);
`dropEvent` — перевод середины/верхнего края/нижнего края строки, неявный
узел, отсутствие текущей строки, безусловный `event.ignore()`, мутационный
тест выше. 14 новых тестов, все зелёные; TDD RED подтверждён отдельно
(`git stash` реализации → `ImportError: DropTarget` при сборе модуля → откат
стеша).

Смысл прямого вызова `dropEvent()` с самодельным `QDropEvent` в тестах:
`visualRect()`/`indexAt()`/`KEY_ROLE` не зависят от состояния перетаскивания
и дают тот же результат, что при живом drag, — переведена сама точка перевода
события, а не только `handle_drop`. Не проверено и остаётся за ручным smoke
№2: запуск настоящего перетаскивания мышью (инициация `QDrag`, курсор
"запрещено"/"разрешено", визуальная линия-индикатор в момент наведения,
автопрокрутка при перетаскивании к краю списка).

## Круг правок 1 (ревью задачи 14)

**Замечание:** `target_is_implicit` гейтился по `index.isValid() and target_key
is None` — а пустой `KEY_ROLE` бывает у трёх разных видов строк, не только
у неявного узла: у заголовков веток «Избранное»/«Недавние»/«Общие списки»
(`RowKind.SECTION`) и у строк ошибок чтения общего списка (`RowKind.NOTE`)
тоже. Бросок на заголовок «Общие списки» получал то же сообщение «Этой
группы нет в файле — есть только путь Folder», что и настоящий неявный узел
— бессмысленный совет создать группу для ветки, у которой `Folder` не
существует в принципе. Docstring `handle_drop` заявлял паритет со
структурным барьером задачи 12 (`kind == RowKind.IMPLICIT_GROUP.value`
в `_show_menu`), но фактически гейтился по более грубому условию
(`KEY_ROLE is None`) — паритета не было.

**Правка:** гейт переведён на `KIND_ROLE` строки под курсором —
`IMPLICIT_GROUP` даёт `target_is_implicit` (текст без изменений), `SECTION`
и `NOTE` дают новый `target_is_virtual` со своим текстом («Сюда класть
нельзя — это служебная строка раздела…», без единого слова про `Folder`).
Добавлены три теста: `test_drop_onto_virtual_branch_is_refused_with_its_own_message`
(`handle_drop`, без Qt), `test_drop_event_on_section_header_sets_target_is_virtual`
и `test_drop_event_on_note_row_sets_target_is_virtual` (`dropEvent`, с реальными
строками веток — новая фикстура `broken_common_cfg_paths` в `tests/ui/conftest.py`
даёт `NOTE`-строку через недоступный общий список). Заодно усилен
`test_drop_event_always_ignores_the_event` (замечание «Мелочь» ревью):
событие теперь заранее переводится в принятое (`event.accept()`), иначе
проверка была бы зелёной и без `event.ignore()` в `dropEvent` — свежий
`QDropEvent` и так возвращает `isAccepted() is False`.

Коммит: `aa53140` — «fix: круг правок 1 ревью задачи 14 — цель drop
различает виртуальные строки».

Мутационная проверка (после коммита, откачена): гейт `dropEvent` возвращён
к `target_key is None` (без `KIND_ROLE`). Упали 4 теста — оба новых
(`test_drop_event_on_section_header_sets_target_is_virtual`,
`test_drop_event_on_note_row_sets_target_is_virtual`, оба — заголовок/NOTE
снова помечались `target_is_implicit=True` вместо `target_is_virtual=True`)
и два существующих, чьи точные проверки словаря kwargs перестали совпадать
без ключа `target_is_virtual` (`test_drop_event_translates_middle_of_row_to_into`,
`test_drop_event_on_implicit_node_sets_target_is_implicit`). Откат:
`git checkout -- src/onecstarter/ui/bases/view.py`, `git status --short`
пуст, `uv run pytest -q` → 762 passed.

---

### Task 15: порядок записей — `services/order.py` и `ReorderPatch`

§4. Очевидное «среднее между соседями» у нас **не работает с первого дня**:
`edit._apply_add` пишет каждой новой записи `OrderInList=-1`, значит равные
соседи — норма.

**Files:**
- Create: `src/onecstarter/services/order.py`
- Modify: `src/onecstarter/services/edit.py`
- Modify: `src/onecstarter/services/workspace.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/unit/test_order.py` (создать)
- Test: `tests/unit/test_edit.py` (дополнить)

**Interfaces:**
- Produces:
  - `order.reorder_values(orders: Sequence[float | None], moved: int, after: int | None) -> dict[int, float]` —
    индекс → новое значение; пусто — двигать нечего. `after is None` — в начало.
  - `order.format_order(value: float) -> str`.
  - `edit.ReorderPatch` — frozen dataclass, поля `target_key: str`,
    `after_key: str | None`. Входит в `Patch`.
  - `Workspace.move_within_group(key: str, after_key: str | None) -> None`.

- [x] **Step 1: Табличные тесты**

```python
@pytest.mark.parametrize(
    ("orders", "moved", "after", "expected"),
    [
        # Есть зазор — меняется одно значение.
        ([10.0, 20.0, 30.0], 2, 0, {2: 15.0}),
        ([10.0, 20.0, 30.0], 0, 1, {0: 25.0}),
        # В начало и в конец — за пределы крайних значений.
        ([10.0, 20.0], 1, None, {1: 9.0}),
        ([10.0, 20.0], 0, 1, {0: 21.0}),
        # Никуда не двинули.
        ([10.0, 20.0], 1, 0, {}),
        ([10.0, 20.0], 0, None, {}),
        ([10.0], 0, None, {}),
        # Равные соседи: зазора нет. Так выглядит наш собственный список
        # сразу после добавления — каждой записи пишется OrderInList=-1.
        ([-1.0, -1.0, -1.0], 2, None, {0: 0.0, 1: 1.0, 2: 2.0}),
        # Нет ключа OrderInList хотя бы у одного — интерполировать не от чего.
        ([10.0, None, 30.0], 2, None, {0: 1.0, 1: 2.0, 2: 0.0}),
    ],
)
def test_reorder_values(
    orders: list[float | None], moved: int, after: int | None, expected: dict[int, float]
) -> None:
    assert reorder_values(orders, moved, after) == expected


def test_renumbering_stays_inside_the_group() -> None:
    """Пересчитывается одна группа, а не весь файл.

    Скил v8i-format, факт 5: пересчёт всего файла в плотную нумерацию
    переписывает его целиком и ломает round-trip. Локальный пересчёт
    при исчерпании зазора — вынужденный и редкий ([Р] решение спеки §4).
    """  # noqa: RUF002
    assert set(reorder_values([-1.0, -1.0], 1, None)) == {0, 1}


@pytest.mark.parametrize(
    ("value", "text"),
    [(0.0, "0"), (-1.0, "-1"), (15.0, "15"), (60.6814814814813, "60.6814814814813")],
)
def test_format_order(value: float, text: str) -> None:
    """Целое пишется целым — так его пишет платформа, и diff файла не шумит."""
    assert format_order(value) == text
```

- [x] **Step 2: Прогнать (FAIL), реализовать `services/order.py`**

```python
"""Арифметика OrderInList при перестановке записи внутри группы.

**[Ф]** скил v8i-format, факт 5: `OrderInList` — дробное число, значим только
относительный порядок; пересчёт всего файла в плотную нумерацию запрещён —
он переписывает файл и ломает round-trip.

Отсюда правило: обычно меняется одно значение — среднее между новыми соседями.
Но «среднее» ломается на равных соседях, а они у нас норма, а не край:
`edit._apply_add` пишет каждой новой записи `OrderInList=-1`. Поэтому при
исчерпании зазора пересчитывается **одна группа** — [Р] решение спеки 4b, §4.
"""  # noqa: RUF002

from collections.abc import Sequence

__all__ = ["format_order", "reorder_values", "sort_key"]


def sort_key(order: float | None) -> tuple[bool, float]:
    """Ключ сортировки, тот же, что у `catalog.items_from_document`.

    Две копии этого правила разъехались бы, и позиция, посчитанная здесь,
    не совпала бы с позицией на экране.
    """  # noqa: RUF002
    return (order is None, order or 0.0)


def reorder_values(
    orders: Sequence[float | None], moved: int, after: int | None
) -> dict[int, float]:
    """Новые значения `OrderInList`: индекс → значение. Пусто — двигать нечего.

    `orders` — значения всех детей одного родителя в порядке показа.
    `after is None` — поставить в начало.
    """  # noqa: RUF002
    if after == moved:
        return {}
    rest = [index for index in range(len(orders)) if index != moved]
    position = 0 if after is None else rest.index(after) + 1
    target = [*rest[:position], moved, *rest[position:]]
    if target == list(range(len(orders))):
        return {}
    if any(value is None for value in orders):
        # У кого-то нет ключа вовсе — интерполировать не от чего.
        return _renumber(target)
    previous = orders[target[position - 1]] if position > 0 else None
    following = orders[target[position + 1]] if position + 1 < len(target) else None
    value = _between(previous, following)
    return {moved: value} if value is not None else _renumber(target)


def format_order(value: float) -> str:
    """Записать значение так, как пишет платформа: целое — без дробной части."""
    return f"{value:.15g}"


def _renumber(target: Sequence[int]) -> dict[int, float]:
    return {index: float(rank) for rank, index in enumerate(target)}


def _between(previous: float | None, following: float | None) -> float | None:
    """Значение строго между соседями. `None` — зазора нет, нужен пересчёт.

    `None` у соседа здесь означает «соседа нет» (край списка), а не
    «нет ключа»: случай отсутствующего ключа отсечён вызывающим.
    """  # noqa: RUF002
    if previous is None and following is None:
        return 0.0
    if previous is None:
        return (following or 0.0) - 1.0
    if following is None:
        return previous + 1.0
    middle = (previous + following) / 2
    return middle if previous < middle < following else None
```

- [x] **Step 3: `ReorderPatch` в `services/edit.py`**

```python
@dataclass(frozen=True)
class ReorderPatch:
    """Переставить запись внутри её группы. `after_key is None` — в начало."""

    target_key: str
    after_key: str | None = None


Patch = SectionPatch | GroupPatch | ReorderPatch
```

```python
def _apply_reorder(document: V8iDocument, patch: ReorderPatch) -> PatchResult:
    section = find_target(document, patch.target_key)
    if section is None:
        raise TargetGoneError("Переставляемая запись удалена извне")
    parent = normalize_folder(section.folder)
    # Порядок собирается по свежему документу и той же сортировкой, что
    # и показ: siblings берутся в файловом порядке и стабильно сортируются
    # ключом order.sort_key — подпоследовательность стабильно отсортированного
    # списка совпадает со стабильной сортировкой подпоследовательности.
    siblings = sorted(
        (other for other in document.sections if normalize_folder(other.folder) == parent),
        key=lambda other: sort_key(parse_order(other.get("OrderInList"))),
    )
    orders = [parse_order(other.get("OrderInList")) for other in siblings]
    moved = siblings.index(section)
    after: int | None = None
    if patch.after_key is not None:
        anchor = find_target(document, patch.after_key)
        if anchor is None or anchor not in siblings:
            raise InvalidRequestError(
                "Запись, после которой нужно поставить, лежит в другой группе "
                "или удалена извне"
            )
        after = siblings.index(anchor)
    for index, value in reorder_values(orders, moved, after).items():
        siblings[index].set("OrderInList", format_order(value))
    return PatchResult(applied=True, key=key_of_section(section))
```

`apply_patch` получает ветку `if isinstance(patch, ReorderPatch): return _apply_reorder(document, patch)`
**до** проверки `GroupPatch`.

- [x] **Step 4: `Workspace.move_within_group` и вызов из UI**

```python
    def move_within_group(self, key: str, after_key: str | None) -> None:
        """Переставить запись внутри её группы. `after_key is None` — в начало."""
        self._reject_common(key)
        self._write(ReorderPatch(target_key=key, after_key=after_key))
```

UI: `DropTarget.BEFORE`/`AFTER` внутри одной группы зовут `move_within_group`;
`Alt+↑` и `Alt+↓` двигают текущую запись на одну позицию (соседа берут
из отфильтрованного леса — то, что пользователь видит).

- [x] **Step 5: Интеграционный тест на файле**

```python
_THREE = (
    '[Первая]\r\nConnect=File="D:\\a";\r\nID=11111111-1111-1111-1111-111111111111\r\n'
    "OrderInList=10\r\n"
    '[Вторая]\r\nConnect=File="D:\\b";\r\nID=22222222-2222-2222-2222-222222222222\r\n'
    "OrderInList=20\r\n"
    '[Третья]\r\nConnect=File="D:\\c";\r\nID=33333333-3333-3333-3333-333333333333\r\n'
    "OrderInList=30\r\n"
)


def test_reorder_writes_only_the_moved_section(tmp_path: Path) -> None:
    """Зазор есть — меняется одно значение, соседние секции не тронуты."""
    path = tmp_path / "ibases.v8i"
    path.write_bytes(_THREE.encode("utf-8"))

    payload, result = write_patch(
        path,
        ReorderPatch(target_key="id:33333333-3333-3333-3333-333333333333",
                     after_key="id:11111111-1111-1111-1111-111111111111"),
        "unused",
    )

    assert result.applied
    text = payload.decode("utf-8")
    assert "OrderInList=15" in text
    assert "OrderInList=10" in text
    assert "OrderInList=20" in text
    assert "OrderInList=30" not in text


def test_reorder_renumbers_group_when_no_gap(tmp_path: Path) -> None:
    """Все соседи с OrderInList=-1 — так выглядит список после наших добавлений.

    `edit._apply_add` пишет -1 каждой новой записи, поэтому равные соседи
    у нас норма. Пересчитывается одна группа, файл целиком не переписывается
    (скил v8i-format, факт 5).
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    path.write_bytes(_THREE.replace("OrderInList=10", "OrderInList=-1")
                     .replace("OrderInList=20", "OrderInList=-1")
                     .replace("OrderInList=30", "OrderInList=-1").encode("utf-8"))

    payload, _result = write_patch(
        path,
        ReorderPatch(target_key="id:33333333-3333-3333-3333-333333333333", after_key=None),
        "unused",
    )

    text = payload.decode("utf-8")
    assert "OrderInList=-1" not in text
    # Значения в файловом порядке секций: Первая, Вторая, Третья.
    # Третья ушла в начало, поэтому её значение наименьшее.
    values = [int(line.split("=")[1]) for line in text.splitlines()
              if line.startswith("OrderInList=")]
    assert values == [1, 2, 0]


def test_reorder_refuses_anchor_from_another_group(tmp_path: Path) -> None:
    """Ставить «после» записи из чужой группы бессмысленно — это перенос."""
    path = tmp_path / "ibases.v8i"
    path.write_bytes(
        (_THREE + '[Клиенты]\r\nID=44444444-4444-4444-4444-444444444444\r\n'
         "OrderInList=-1\r\nFolder=/\r\nExternal=0\r\n"
         '[Внутри]\r\nConnect=File="D:\\d";\r\n'
         "ID=55555555-5555-5555-5555-555555555555\r\n"
         "OrderInList=5\r\nFolder=/Клиенты\r\n").encode("utf-8")
    )

    with pytest.raises(InvalidRequestError):
        write_patch(
            path,
            ReorderPatch(target_key="id:11111111-1111-1111-1111-111111111111",
                         after_key="id:55555555-5555-5555-5555-555555555555"),
            "unused",
        )
```

- [x] **Step 6: Прогон, коммит, мутационная проверка**

```bash
git add src/onecstarter tests
git commit -m "feat: перестановка записей внутри группы дробным OrderInList"
```

Мутация (переписана в круге правок 2 под итоговый код — история одной
строкой: см. «Круг правок 1» и «Круг правок 2» ниже): в `reorder_values`
убрать ветку `any(value is None ...)` и проверку `_all_equal(orders)`;
в `_between` считать среднее/`±1.0` по сырому `float` всегда, без
`_fits_before`/`_fits_after`/`_fits_between` (без проверки записываемого
значения, порядка и научной нотации). Ожидание: падают 13 тестов —
`test_order.py` (обе строки `[-1.0, -1.0, -1.0]`, строка с `None`, строка
с соседями `60.6814814814813`/`60.6814814814814`, строка с `1.7e308`,
`test_reorder_values_avoids_a_written_collision_between_close_neighbors`,
`test_reorder_renumbers_before_writing_scientific_notation`,
`test_renumbering_stays_inside_the_group`), `test_writer.py`
(`test_reorder_renumbers_group_when_no_gap`,
`test_reorder_achieves_the_requested_order_end_to_end`,
`test_reorder_falls_back_to_renumber_before_writing_scientific_notation`,
`test_reorder_preserves_order_with_very_large_neighbor_values`) и
`test_edit.py` (`test_reorder_treats_implicit_and_explicit_root_as_one_
group` — вырожденная группа в этом тесте тоже перестаёт пересчитываться
целиком). Подтверждено прогоном 09.08.2026: 13 failed, 803 passed.

Факт: реализовано с одним отклонением от кода брифа — сам код `reorder_values`
из Step 2 оказался неверен относительно СВОЕГО ЖЕ табличного теста из Step 1
(прогнано до реализации, обе стороны проверены руками и скриптом). Строка
`([-1.0, -1.0, -1.0], 2, None, {0: 0.0, 1: 1.0, 2: 2.0})` при `after=None`
(«поставить в начало») ожидала, что переставляемая запись (индекс 2) получит
НАИБОЛЬШЕЕ значение — то есть окажется последней, а не первой; это
противоречит и собственной семантике `after is None`, и соседней строке
таблицы (`[10.0, 20.0], 1, None, {1: 9.0}` — там `after=None` корректно даёт
двигаемой записи меньшее значение). Тест в `test_order.py` исправлен на
семантически верное `{0: 1.0, 1: 2.0, 2: 0.0}` — двигаемая запись получает
наименьшее значение; отдельный тест `test_reorder_to_front_of_degenerate_
group_actually_sorts_first` проверяет это не по словарю, а применением
результата и сортировкой (последняя наблюдаемая точка чистой функции).

Отдельно от опечатки в ожидаемом значении сам алгоритм из брифа не
пересчитывал группу на КРАЮ (при `after is None` или в конец), если у соседа
с этого края такое же значение, как было у самой переставляемой записи до
переноса, — `_between` там всегда находит новое число (`following - 1` /
`previous + 1`), никогда не запуская `_renumber`. Итоговый порядок при этом
получался правильным (проверено: `[-1,-1,-1]`, moved=2, after=None → `{2:
-2.0}`, сортировка даёт `[2, 0, 1]` — верно), но группа копила бы произвольно
уходящие -2, -3, -4… вместо пересчёта, и `test_renumbering_stays_inside_the_
group` (`{0, 1}` обоих ключей) на исходном коде брифа падал (проверено). Добавлена
`order._edge_tie` — сравнение с собственным старым значением переставляемой
записи на краю группы, симметричное `previous == following` внутри
`_between`. Оба расхождения — в отчёте `task-15-report.md` с полным разбором.

Мутационная проверка (по протоколу CLAUDE.md, откат после каждой):

1. **Мутация из брифа буквально** (только `any(value is None...)` и
   `previous < middle < following`, `_edge_tie` не тронута): падает только
   строка с `None` (`test_reorder_values[orders11-2-None-expected11]`) — обе
   строки `[-1.0, -1.0, -1.0]` остаются зелёными, потому что их независимо
   ловит `_edge_tie`, добавленная этой задачей поверх кода брифа. Это
   ожидаемо и хорошо: собственная защита сильнее той, что предполагал бриф.
2. **Полная мутация** (то же плюс `_edge_tie` отключена): падают все четыре
   строки, как и предсказывал бриф — обе `[-1.0, -1.0, -1.0]`, `None`
   и `test_renumbering_stays_inside_the_group`. `test_order.py`: 4 failed,
   19 passed на обеих мутациях.
3. **Вторая мутация (своя, ступень «дошло до дерева»):** в
   `edit._apply_reorder` добавлен `reverse=True` к сортировке соседей —
   тот самый «тонкое место» из инструкции задачи (siblings обязаны
   сортироваться тем же ключом, что и показ). Пример: реальная запись
   `catalog.items_from_document` (`order.sort_key`) не тронута, `order.
   reorder_values` (чистая функция) тоже не тронута — все 23 теста
   `test_order.py` остались зелёными. А `test_edit.py` (3 теста), `test_
   writer.py` (1 тест на файле), `test_workspace.py` (`test_move_within_
   group_changes_the_order_seen_after_rebuild`) и `test_bases_view.py`
   (обе перестановки drop BEFORE/AFTER внутри группы и оба Alt+↑/Alt+↓)
   упали — итого 9 из 221 теста задачи 15. Ровно демонстрирует цепочку
   урока «дошло до последней наблюдаемой точки»: дыра на уровне порядка
   соседей чистой функцией не ловится вовсе, а тестами patch → file →
   tree/UI ловится каждым слоем. После отката `git diff --stat` пуст —
   рабочее дерево совпадает с коммитом `8454d0f`.

Коммит `8454d0f`: `feat: перестановка записей внутри группы дробным
OrderInList`. 804/804 теста, `ruff check .` и `uv run mypy` чистые.

## Круг правок 1 (ревью на самой сильной модели)

Ядро принято независимо (пересчёт не выходит за одну группу, запись нельзя
потерять или задвоить, `sort_key` общий, дефект таблицы брифа диагностирован
верно, обе мутации Step 6 подтверждены построчно; 20 000 случайных случаев
без расхождений запрошенного/полученного порядка). Найдены три дефекта.

**1. Порог зазора проверял не то число, которое записывается.** `_between`
сравнивал `previous < middle < following` по сырому `float`, а на диск идёт
`format_order(middle)` (`%.15g`, 15 значащих цифр). У соседей вида
`60.6814814814813`/`60.6814814814814` (реальные значения платформы, скил
v8i-format факт 5) среднее нуждается в 16-й цифре — округление даёт текст,
совпадающий с одним из соседей: raw-float проверка считала зазор найденным,
а после записи и перечитывания запись попадала в ничью, и порядок между
записями решал файловый, а не запрошенный (показано сквозным прогоном
`apply_patch → serialize → parse → items_from_document`: запрошено «П, М, Н»,
получено «М, П, Н»). Края тоже не проверялись — `previous + 1.0` и
`(following or 0.0) - 1.0` возвращались без проверки отличия от соседа
(доказано на `1.7e308`, где `+1.0` не меняет число вовсе).

**Правка:** `_between` проверяет `float(format_order(candidate))`, а не сам
`candidate` — и на интервале (`previous < written < following`), и на краях
(`written != neighbor`). Формат `format_order` не менялся: смена на «кратчайшее
round-trip представление» не решила бы задачу для по-настоящему соседних
`float` (там нет представимого числа строго между ними в принципе), а более
длинные числа отклонились бы от вида, которым пишет платформа, без всякой
выгоды.

**2. `_all_equal` (был `_edge_tie`) пересчитывал группы, у которых зазор есть.**
Первая версия (`_edge_tie`) сравнивала старое значение переставляемой записи
только с ОДНИМ соседом — и пересчитывала лишнее: на данных вида
`[-1, -1, 311296, 311552, 311808, 312064]` переписывались все шесть записей
ради перестановки одной, хотя зазор относительно `311296` и далее был на
месте. Решение заказчика: пересчитывать только когда **все** значения
группы совпадают буквально — группа вырождена целиком, а не только
в точке вставки. Условие сужено до `_all_equal(orders)`
(`len(set(orders)) == 1`), а старое `own`-сравнение убрано. Тесты брифа
(`[-1,-1], 1, None`; `[-1,-1,-1], 2, None`; `[-1,-1,-1], 1, 2`) продолжают
пересчитываться — они и так вырождены целиком.

**3. Свойство «пересчёт не выходит за группу» не могло упасть по своей
причине.** `test_renumbering_stays_inside_the_group` звал чистую функцию
на списке из двух элементов, где второй группы не существует вовсе —
свойство «соседи собраны верно» живёт в `edit._apply_reorder`
(`normalize_folder(other.folder) == parent`), а не в `order.reorder_values`,
и подмена фильтра на сырое `other.folder == section.folder` пережила бы весь
набор: фикстуры однородны (либо `Folder=` есть у каждой секции, либо ни
у одной). А платформа производит именно неоднородные файлы — секция без
`Folder` рядом с `Folder=/` означает один и тот же корень ([Ф] T-02.3).

**Правка:** новый тест `test_reorder_treats_implicit_and_explicit_root_as_
one_group` (`test_edit.py`) — документ из двух групп, в корне часть секций
без ключа `Folder`, часть — с `Folder=/`; после перестановки все корневые
секции пересчитаны как одна группа, вторая группа не тронута ни байтом.
Заодно устранена мелкая ловушка: `siblings.index(section)`/
`anchor not in siblings` сравнивали `V8iSection` по значению (обычный
dataclass с структурным `__eq__`) — заменено на `_index_of` по идентичности
объекта.

**Мелочи, исправленные заодно:**

- Перестановка «на своё же место» больше не пишет файл: `write_patch`
  сравнивает `payload == data` и возвращает без атомарной записи, если патч
  не изменил ни байта (не только для `ReorderPatch` — общая проверка,
  тот же путь для любого патча).
- `format_order`: докстринг честно помечает `[Д]` — читает ли платформа
  научную нотацию (`1e-07`, `1e+308`) в `OrderInList`, не проверялось;
  реальные значения (факт 5) и наша арифметика на разумных входных данных
  в этот диапазон не попадают, поэтому сам формат не менялся.

**Мутационная проверка (обязательна для пунктов 1–3, откат после каждой):**

1. Возврат `_between` к сырому `float` (`previous < middle < following`,
   без `format_order`-проверки) — падают 4 теста: два новых табличных ряда
   (соседи `60.68…13`/`60.68…14`; `1.7e308`), `test_reorder_values_avoids_
   a_written_collision_between_close_neighbors`,
   `test_reorder_achieves_the_requested_order_end_to_end` (сквозной прогон,
   «М, П, Н» вместо «П, М, Н»). Откат — чисто.
2. Возврат `_all_equal` к старому `_edge_tie` (сравнение с одним соседом) —
   падает ровно `test_reorder_counter_example_from_customer_data_touches_
   one_value` (было 6 переписанных значений вместо 1), остальные тесты
   (включая оба вырожденных ряда `[-1,-1,-1]`) остаются зелёными — старое
   условие их тоже ловило, просто ловило и лишнее. Откат — чисто.
3. Замена `normalize_folder(other.folder) == parent` на сырое
   `other.folder == section.folder` в `_apply_reorder` — падает
   `test_reorder_treats_implicit_and_explicit_root_as_one_group` (секция
   `Folder=/` не пересчитана, осталась с `-1`). Откат — чисто.

**Переформулировка мутации Step 6** (была привязана к коду до круга правок 1
и валила только 1 строку из 4, потому что `_edge_tie` перекрывал остальные):
буквальное применение (`any(value is None...)` + `previous < middle <
following` → всегда среднее, без `format_order`-проверки, `_all_equal` не
тронута) валит только строку с `None`; обе строки `[-1.0, -1.0, -1.0]`
остаются зелёными — их независимо ловит `_all_equal` (после круга правок 1
это финальная защита, а не промежуточная `_edge_tie`). Полное отключение
и `_all_equal`, и format-проверки в `_between` валит все четыре
предсказанные брифом строки — так изначальная мутация Step 6 и была
задумана. Обе формы подтверждены (см. выше).

Прогон после круга правок 1: 811/811 тестов, `ruff check .` и `uv run mypy`
чистые. Отчёт: `task-15-report.md`, раздел «Круг правок 1».

## Круг правок 2 (ре-ревью круга 1)

Круг 1 закрыт и проверен независимо (интервальная ветка порога, сужение до
`_all_equal` — исчерпывающий свод старого условия против нового и 60 000
случайных прогонов дали ноль расхождений, тест на смешанный корень,
сравнение по идентичности). Расширение `payload == data` в `writer.py`
признано верным для всех патчей, а не только `ReorderPatch` — ревьюер
прогнал все четыре формы no-op (`UPDATE` тем же `Connect`, `UPDATE` тем же
именем, `REMOVE` отсутствующей цели, `RETARGET` группы в то же имя) и
подтвердил, что байты и `mtime` не меняются, `PatchResult` цел, `Workspace.
_write` и watcher от факта записи не зависят. Один важный пункт остался
открытым.

**1. Научная нотация достижима обычной работой, а обосновывающее
утверждение было ложным.** Докстринг `format_order` утверждал, что наша
арифметика такие значения «не порождает при разумных входных данных» —
опровергнуто прогоном: начав с группы, пересчитанной в `0, 1, 2, …`,
**четырнадцать обычных перетаскиваний** записи под первую (каждое —
отдельная запись, каждое — простой `after=<первая>`) доводят зазор до
`2⁻¹⁴`, и `format_order` отдаёт `"6.103515625e-05"`. Это не `1.7e308`
из синтетики — нормальная работа внутри одной группы (проверено:
воспроизведено скриптом и живым прогоном через `write_patch` 14 раз подряд).

Метка `[Д]` на вопросе «читает ли платформа научную нотацию» верна и
осталась; ложное фактическое утверждение рядом с ней — убрано.

**Правка:** научная нотация в записываемом тексте — признак «зазора не
осталось», при любом положении. `_fits_before`/`_fits_after`/`_fits_between`
проверяют `"e" not in format_order(candidate)` наравне с порядком; при
провале — `_renumber`. Обоснование в коде: мы не знаем, читает ли платформа
`6.1e-05` в `OrderInList`, и вместо того чтобы гадать, уходим в форму,
в которой сомнений нет — тот же приём, что уже применён к кавычкам
в задаче 9.

**2. `_written_apart` (круг 1) проверяла неравенство, а не порядок.**
Интервальная ветка порог уже проверяла порядком, краевые — только `!=`.
Показано сквозным прогоном: `_between(1000000000000002.0, None)` давала
`1000000000000003.0`, которое `format_order` пишет как `"1e+15"`, а
читается обратно как `1000000000000000.0` — **меньше** соседа. Запрошено
`[Большая, Малая]`, получено `[Малая, Большая]`.

**Правка:** `_fits_before`/`_fits_after` проверяют направление
(`float(text) < neighbor` / `> neighbor`), не только `!=`.

**Найденное при верификации, не в самой правке:** для действующей формулы
края (`previous + 1.0` / `following - 1.0`, формат `%.15g`) порядковая
инверсия без научной нотации математически недостижима — переход в
`%.15g` в scientific происходит ровно на том же пороге величины (≈1e15),
после которого `+1.0`/`-1.0` перестаёт умещаться в 15 значащих цифр.
Подтверждено доказательством (округление `%g` до `p` значащих цифр не может
понизить значение ниже старого при добавлении `+1`, пока представление
остаётся в фиксированной точке) и прогоном: 2 000 000 случайных `previous`
(экспоненты 0–16, оба знака, обе краевые формулы) не дали ни одного случая
инверсии без `"e"` в тексте; мутация «вернуть `!=` вместо порядка, `"e"`-
проверку не трогать» прогнана на всём наборе (816 тестов) — ни один
не упал. Правка оставлена как и запрошено (принцип один в обеих ветках,
`_fits_between` уже был таким), но как самостоятельно детектируемый баг
для текущей формулы она не воспроизводится — задокументировано в отчёте,
а не выдано за подтверждённое мутацией.

**3. `payload == data` — тест только на `ReorderPatch`.** Добавлены
`test_update_with_the_same_connect_does_not_touch_the_file` и
`test_retarget_group_to_the_same_name_does_not_touch_the_file`
(`test_writer.py`) — закрепляют то, что ревьюер уже прогнал вручную.

### Мутационная проверка (обязательна для пунктов 1 и 2)

1. **Точка 1**, интервальная ветка (`_fits_between`, без `"e" in text`):
   падают ровно 2 теста — `test_order.py::test_reorder_renumbers_before_
   writing_scientific_notation` и `test_writer.py::test_reorder_falls_back_
   to_renumber_before_writing_scientific_notation`; весь остальной набор
   (814 из 816) зелёный. Откат — чисто.
2. **Точка 2**, краевые ветки (`_fits_before`/`_fits_after`, `!=` вместо
   порядка, `"e"`-проверка не тронута): ни один тест не падает (816/816) —
   см. «Найденное при верификации» выше. Откат не требовался (мутация
   не вносила регресс, который стоило бы откатывать отдельно).

### Итог круга правок 2

816/816 тестов (было 811, +5 в этом круге), `ruff check .` и `uv run mypy`
чистые.

---

## Контрольная точка: ручной smoke №2

После задачи 15. Проверяется на **копии** рабочего `ibases.v8i`, а не на боевом
файле: операции пишут в него, и откатывать нечем.

**Как обеспечивается копия (готово 09.08.2026).** Не «сделать бэкап и быть
аккуратным», а подмена `APPDATA`: `build_runtime` берёт оттуда все свои пути —
и `ibases.v8i`, и `bases.json`, и `settings.json` (`ui/app.py`). Приложение,
запущенное с `APPDATA`, указывающим на песочницу, до живого файла не дотянется
физически. Машинный `1cestart.cfg` читается из `ALLUSERSPROFILE` отдельно
(`platform_1c/discovery.py`), поэтому список установленных версий и общие
списки остаются настоящими. Проверено вхолостую: из песочницы читаются
66 записей, находятся 7 версий платформы, `settings.json` ложится в песочницу.

**[Ф] Тем же приёмом штатный стартер НЕ изолируется.** Это утверждение стояло
здесь в исходной редакции раздела и было моим домыслом, не замером. Проверка
09.08.2026: `1cestart.exe`, запущенный процессом с `APPDATA`, указывающим
на песочницу, переписал **живой** `ibases.v8i` (mtime сменился, хеш
`736C7E08…` → иной), а копию в песочнице не тронул вовсе (хеш `158BD0A5…`
не изменился). Наше приложение подменой `APPDATA` изолируется — оно читает
переменную окружения через `os.environ` (`ui/app.py`); платформа, судя по
всему, разрешает путь профиля через shell API (`SHGetKnownFolderPath`),
который переменную окружения игнорирует — **[Д], механизм не проверялся,
проверен только результат.**

Практический вывод: пункт «порядок переживает запуск базы из штатного
стартера» в песочнице через `APPDATA` **не проверяется**. Либо другой механизм
изоляции (отдельный пользователь Windows, песочница ОС), либо осознанная
работа на живом файле с бэкапом. Порядок действий, который здесь нарушен
и который надо соблюдать: изоляцию каждого участника проверяют **до** того,
как навести его на настоящие данные, а не после.

**[Ф] Что перезапись платформы делает с файлом** (снято тем же случаем,
64 секции, светлая сторона происшествия). Ни одна секция не потеряна,
ни один ключ не потерян, `Connect`, `ID`, `Folder`, `Version` не изменились
ни у одной записи. Изменились только `OrderInList`/`OrderInTree` у 7 секций;
49 секций сменили позицию в файле; размер 16151 → 16066 байт; кодировка
UTF-8 и BOM сохранены.

**[Ф] Дробный `OrderInList` перезапись платформы переживает** — главный
вопрос задачи 15, закрыт. Дробных значений было 17, осталось 17,
округлённых в целые — ноль. Два значения платформа переписала, и оба ровно
те, что имели **16 значащих цифр**: `0.7223985890652509` → `0.722398589065251`
и `5.056790123456771` → `5.05679012345677`. Все 15 значений, укладывавшихся
в 15 значащих цифр, уцелели побайтно. Вывод: **платформа усекает
`OrderInList` до 15 значащих цифр**. Наш `format_order` пишет `f"{value:.15g}"`,
то есть ровно 15 — совпадение не случайное, но до этого замера оно было
догадкой. Значения, которые пишем мы, переживают перезапись без изменений.
Результат вернуть в скил `v8i-format`.

**Сверка «прочие ключи секции на месте» — не `diff`.** Обычный diff вынес бы
наружу реальные пути к базам и имена организаций (инвариант 5, правило
о фикстурах). Вместо него — снимок «формы» файла нашим же парсером: имена
ключей как есть, значения — длиной и восьмизначным хешем. Этого хватает
доказать «ключ на месте и не изменился» и не хватает восстановить значение.
Инструмент проверен на подсадном дефекте: удаление `OrderInList` и добавление
`Version` он показывает поимённо.

**[Ф] Висячего `Folder` в рабочем списке нет ни одного** (замер 09.08.2026:
64 секции, 6 групп, 58 баз, висячих `Folder` — 0; дробный `OrderInList` —
у 17 секций). Значит последний пункт списка ниже естественным путём
не воспроизводится, и случай заведён искусственно: в копию добавлены две
записи `ZZ …`, одна в несуществующем каталоге `/ZZ Висячий каталог` (она
и создаёт неявный узел), вторая рядом в корне — чтобы было что и куда бросать.
Скрипт инъекции отказывается писать в путь внутри живого `%APPDATA%`;
предохранитель проверен отказом.

- добавление файловой базы перетаскиванием каталога;
- правка серверной базы: сменить сервер, убедиться, что прочие ключи
  секции на месте (сравнением **формы** файла до и после, а не `diff`'ом —
  см. выше);
- удаление записи, подтверждение читается однозначно;
- перестановка записей внутри группы, порядок переживает перезапуск
  приложения;
- ~~порядок переживает запуск базы из штатного стартера~~ — **закрыто
  09.08.2026 без ручной проверки.** Пункт неисполним в песочнице: подмена
  `APPDATA` стартер не изолирует (замер выше), а других способов изоляции
  на этой машине нет — отдельный пользователь Windows заказчиком отклонён.
  Ради одного пункта переписывать живой файл не станем: правило перезаписи
  измерено (усечение `OrderInList` до 15 значащих цифр, остальное
  сохраняется), и вместо ручной проверки поставлен сторож
  `tests/unit/test_order.py::test_what_we_write_survives_the_platform_rewrite`.
  Он гоняет каждое значение, которое порождает `reorder_values` на шести
  раскладках, через модель перезаписи и требует неподвижности. Сама модель
  проверяется отдельным тестом на двух настоящих замерах — приём тот же, что
  у формулы контраста: сначала измеритель, потом им меряем. Мутации: `.15g`
  → `.17g` валит 6 тестов, `.16g` (отличие в одну цифру) — 4, ослабление
  модели до `.17g` валит первым тест самой модели. Остаточный [Д]: измерение
  снято на значениях, записанных платформой, а не нами; наши значения
  под правило подпадают по построению, но отдельным ручным прогоном
  это не подтверждалось;
- создание группы, перенос базы в неё перетаскиванием, удаление группы —
  подтверждение перечисляет содержимое;
- **drag&drop `BEFORE` рядом с неявным узлом** (висячий `Folder`, [Ф]
  T-05.7): `_sibling_before` (мышь) ищет соседа по `Workspace.items()`,
  который неявные узлы не видит вовсе — бросок «до» записи, стоящей визуально
  рядом с неявным узлом, может поставить запись по другую его сторону,
  не ту, что показал курсор. Клавиатурный путь (`Alt+↑`/`Alt+↓`) эту
  ситуацию отлавливает и отказывает (`_is_in_file_tree`/проверка соседней
  строки в `_move_current`), мышиный — нет; проверить оба пути на реальном
  дереве с висячим `Folder`.

Факт: прогон проведён 09.08.2026, все шесть пунктов пройдены. Шесть замечаний,
разобраны ниже: дефект кода среди них один (немой отказ drop, исправлен),
одно — про место в спеке (решение заказчика ожидается), одно — про мою
оснастку, три — задуманное поведение, принятое за сбой.

## Замечания ручного smoke №2 (09.08.2026)

| № | Замечание | Разбор | Куда |
| --- | --- | --- | --- |
| 1 | «Добавление файловой базы перетаскиванием каталога не работает» | **Дефекта кода нет.** Спека §3.1 помещает приём каталога на **диалог** добавления, и там он собран верно: `setAcceptDrops(True)`, `dragEnterEvent`/`dragMoveEvent`/`dropEvent` и тесты с настоящими `QMimeData`/`QUrl`. Дерево намеренно в `InternalMove` (задача 14), Qt отвергает чужой drop ещё до `dropEvent`. Но заказчик бросил каталог на **главное окно** — см. решение ниже | решение заказчика |
| 2 | «Перенос базы в „ZZ Тест соседа в корне“ и „ZZ Тест неявного узла“ не даёт результата» | **Не дефект, виновата оснастка.** Обе строки — записи файловых баз, а не группы; у файловой базы значок размещения — папка, отсюда путаница. Перетаскивание базы на базу ничего делать и не должно. Записи переименованы в `ZZ БАЗА …`, чтобы вид не спорил с сутью | закрыто |
| 3 | «Перенос в „ZZ Висячий каталог“ даёт сообщение» | **Не дефект — задуманный отказ.** У неявного узла нет секции в файле, класть в него нечего ([Ф] T-05.7; обязательства блока Б, пункт 5). Текст «Этой группы нет в файле — есть только путь `Folder`. Создайте группу с тем же именем…» читается однозначно и называет способ обойти. Пункт чек-листа пройден | закрыто |

| 4 | «Правка серверной базы — ОК» | **Пройдено, и это главный результат прогона.** Сверка формы подтвердила точечность правки задачи 9: у записи изменились ровно `Connect` (правка сервера) и `Folder` (перенос в группу), а `ID`, `OrderInList`, `OrderInTree`, `External`, `App`, `AppArch`, `WA`, `Version` остались байт в байт | закрыто |
| 5 | «Группы: создал, перетащил базу, удаление даёт сообщение» | **Пройдено.** Диалог и есть задуманное поведение: подтверждение перечисляет содержимое (`asserts`) и предлагает три исхода — обязательство блока Б, пункт 3. Платформа каскадит молча, мы обязаны быть лучше | закрыто |
| 6 | «Бросок базы рядом с неявным узлом ни к чему не приводит» | **Дефект, исправлен.** Причина не в неявном узле: бросок пришёлся на середину строки-**записи**, а `_folder_of_drop` на `INTO`-в-запись отдаёт `None`, и `handle_drop` выходил молча. Немота и породила оба «не работает» — это же объясняет замечание 2 | коммит `5963d2e` |

### Замечание 6 — круг правок 4 (немой отказ drop)

Отказ по сути был верен, неверна была его немота: соседние отказы (неявный
узел, служебная строка) себя объясняют, этот молчал. Хуже того, молчание было
закреплено тестом `test_drop_into_a_base_is_a_no_op` с `assert errors == []` —
решение принималось осознанно, и smoke показал, что оно неверное.

Решение заказчика 09.08.2026: **отказывать курсором во время перетаскивания,
а не окном после отпускания.** Промах мимо межстрочья — частый случай,
модальное окно на каждый промах утомляет; курсор виден до того, как кнопка
отпущена. Неявный узел и служебные строки намеренно оставлены с сообщениями:
там подсказка («создайте группу с тем же именем»), и менять её на курсор
значило бы обменять помощь на тишину.

Решение вынесено в предикат `_BasesTree._rejects_drop_at` отдельно от
Qt-события: настоящую drag-сессию под offscreen не подделать (`canDrop()`
в режиме `InternalMove` требует `event.source() is self`, из Python его
не задать), а предикат проверяется прямо.

**Две ловушки, найденные при написании тестов, закрыты в самих тестах.**

1. `QDragMoveEvent`, собранный из Python, своим `QMimeData` не владеет. Без
   удержания ссылки процесс падает с access violation — в том числе из `repr()`
   внутри сообщения упавшего `assert`. То есть падал бы весь прогон, и падал бы
   **только на красной проверке**: зелёный прогон эту мину не показывает.
2. Первая строка нужного вида может лежать в свёрнутой ветке: `visualRect` пуст,
   `center()` даёт `QPoint(0, 0)`, `indexAt` находит другую строку. Тест про край
   строки сперва «прошёл» именно так — вхолостую. Помощник `_visible_rect_of_kind`
   разворачивает дерево и валит тест на пустом прямоугольнике.

**Мутационная проверка** (после коммита `5963d2e`, откат `git checkout --`):

| мутация | что упало |
| --- | --- |
| убрать переопределение `dragMoveEvent` | `..._event_ignores_a_rejected_position` |
| предикат всегда `False` | `..._rejects_the_middle_of_a_base_row` + тест события |
| убрать проверку стороны | `..._allows_the_edge_of_a_base_row` |
| запрещать и группу тоже | `..._allows_the_middle_of_a_group_row` |

Каждую мутацию поймал ровно тот тест, который за неё отвечает. Третья строка
ценна отдельно: она доказывает, что тест про край перестал проходить вхолостую.
После отката — 852 из 852, `ruff` и `mypy` чисты.

### Замечание 1 — почему это находка про спеку, а не про код

Спека выбрала диалог, и формально всё работает. Но поведение заказчика —
сильнейшее свидетельство о месте: он не искал, куда бросить каталог, он бросил
его туда, где лежит список. Приём на диалоге вдобавок сомнителен по смыслу:
диалог уже открыт, а в нём рядом стоит кнопка «Обзор…» — перетаскивание там
экономит один клик и требует сначала открыть диалог, то есть выигрыш почти
нулевой. Ценность жеста именно в том, чтобы бросить каталог на окно и получить
готовую запись.

Правка не механическая, поэтому в этот план не берётся: `InternalMove` придётся
менять на `DragDrop`, а `_BasesTree.dropEvent` — учить различать своё
перетаскивание (источник по `currentIndex()`) и чужое (каталог в `mimeData()`),
причём `dragEnterEvent`/`dragMoveEvent` обязаны принимать только каталог,
иначе дерево начнёт принимать текст и файлы из любого окна — ровно то, от чего
задача 14 закрывалась `InternalMove`. По правилу `CLAUDE.md` новой
функциональности предшествует `brainstorming`.

### Что показала сверка формы файла

Инструмент сверки поймал собственный дефект: ключом секции была строка
заголовка **вместе с индексом**, и любая перестановка показывалась как
«секция исчезла» плюс «секция появилась». Исправлено — ключ по значению `ID`,
перемещение показывается отдельно и дефектом не считается. Контроль: сверка
снимка с самим собой пуста.

По существу за прогон: ни один ключ не потерян ни у одной записи, которую
заказчик не пересоздавал намеренно. Единственная запись с потерей ключей
(`App`, `WA`, `Version`, `AppArch`, `External`, `OrderInTree`) была удалена
и добавлена заново — у новой записи их и не должно быть, подпись операции
однозначна: новый `ID` и `OrderInList=-1` (`edit.py`). Перестановка внутри
группы сработала: `OrderInList` изменился ровно у одной записи.

### [Ф] Запуск базы и живой файл — наблюдение закрыто опытом 09.08.2026

Наблюдение (сменился mtime живого `ibases.v8i` при неизменном содержимом)
проверено с согласия заказчика. Опыт поставлен безопасно: запускалась
**синтетическая** запись `ZZ БАЗА в корне (сосед)`, указывающая на
несуществующий путь, — настоящая база не открывалась вовсе.

**Результат 1.** Живой файл: `mtime` сменился, размер и SHA-256 — прежние.
Значит запуск по `/IBName` открывает файл на запись, но содержимого не меняет.
Уточняет [Ф] T-02.5 «CLI-запуск файл не трогает»: содержимое не трогает,
файл открывает. Практический вывод для сверок: `mtime` — ненадёжный признак
правки списка, сверять надо содержимое.

**Результат 2, важнее первого.** Клиент, запущенный процессом с `APPDATA`
на песочницу, искал имя в **живом** списке: запрошенного имени там нет
(оно есть только в копии), и клиент открыл окно выбора базы — реакция
на ненайденное имя по [Ф] T-05.2. То есть платформа берёт путь к списку
не из переменной окружения. Это тот же механизм, что уже был снят
на `1cestart.exe` выше, и теперь он подтверждён вторым, независимым путём.

**Следствие для методики, которое надо помнить следующему исполнителю:**
песочница через `APPDATA` изолирует наше приложение и **не изолирует ни один
процесс 1С**. Всё, что запускает платформу, идёт в живой файл, чем бы
ни была подменена переменная. Оба результата возвращены в скил
`platform-launch` (факты 12 и 13).

---

### ~~Task 16~~: `Shift+F3` / `Shift+F4` — СНЯТА 09.08.2026, перенесена в v2

> **Гейт сработал как задумано, и это его первое настоящее срабатывание.**
> Шаг 1 (инвентаризация, 1С не запускается) выполнен 09.08.2026 и показал,
> что предмета задачи не существует: в рабочем списке 58 записей баз, из них
> со строкой соединения, несущей `Usr`, — **ноль**, несущей пароль — **ноль**.
> Ключ `WA` есть у всех 58 секций со значением `1`, но заказчик подтвердил,
> что ни одна база не входит по учётной записи Windows: значит `WA=1` инертен
> и наблюдаемого эффекта у `Shift+F3` не было бы ни на одной базе.
>
> Решение заказчика: **снять из v1, перенести в v2.** Шаги 2–6 ниже
> не выполняются. Реализовать по неподтверждённой гипотезе механизм, который
> негде проверить и чей эффект никто не увидит, значило бы поселить в пути
> запуска навсегда непроверенный код — цена выше, чем у отсутствия функции.
>
> Текст задачи сохранён целиком: в v2, когда появится база с настроенной
> ОС-аутентификацией или с сохранённым паролем, он понадобится как есть.
> Разбор гипотезы — спека §6.2–§6.3, решение — §14.

§6.2–§6.3. **К коду не переходить, пока не проведён эксперимент.** Механизма
«проигнорируй сохранённые `Usr`/`Pwd`» в справочнике `platform-launch` нет;
то, что есть, — гипотеза на непроверенном месте.

**Files:**
- Modify: `src/onecstarter/domain/launch.py`
- Modify: `src/onecstarter/services/launch.py`
- Modify: `src/onecstarter/services/workspace.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Modify: `.claude/skills/platform-launch/SKILL.md` (возврат результата)
- Modify: `docs/tasks.md` (T-05.13, T-05.12)
- Test: `tests/unit/test_launch.py`, `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `domain.launch.build_arguments` (существует).
- Produces (только при подтверждённой гипотезе):
  - `launch_infobase(..., prompt_credentials: bool = False)`.
  - `Workspace.launch(key, forced_client=None, prompt_credentials=False)`.

- [ ] **Step 1: Эксперимент T-05.13, шаг 0 — инвентаризация (1С не запускается)**

Заказчик 08.08.2026 не уверен, что у него есть базы с сохранёнными учётными
данными. Без этого шага остальные замеры бессмысленны: `F3` и `Shift+F3`
на такой машине неразличимы.

Посчитать в рабочем `ibases.v8i`: сколько строк соединения несут фрагмент
`Usr` или `Pwd`, сколько секций имеют ключ `WA`. Считать **числа**,
не выписывая значения (инвариант 5).

Факт: _(заполнить при исполнении)_

Если таких баз нет — завести две тестовые: одну с сохранённым паролем,
одну с настроенной ОС-аутентификацией. Без них эксперимент не проводится.

- [ ] **Step 2: Эксперимент T-05.13 — матрица замеров**

**Требует явного согласия заказчика на запуск процессов 1С.** Согласие
на протокол T-05 исчерпано; это отдельное разрешение.

Матрица: (`/IBName` | `/IBConnectionString` без `Usr`/`Pwd`) × (без `/WA` |
`/WA-`) × (база с сохранённым `Pwd` | база с `WA=1`) — восемь запусков.
По каждому фиксируется: появился ли диалог авторизации, под кем вошли,
изменился ли `ibases.v8i` (сверять хеш).

Факт: _(заполнить при исполнении)_

- [ ] **Step 3: Развилка по результату**

**Гипотеза подтвердилась** → шаги 4–6.
**Гипотеза опровергнута** → шаги 4–6 не выполняются. Записать [Ф]-результат
в скил `platform-launch` и в `docs/tasks.md`, снять задачу решением заказчика
либо предложить новый кандидат механизма. Подгонять поведение под ожидание
запрещено.

В обоих случаях: результат возвращается в скил (подтверждённое повышается
до **[Ф]**, опровергнутое исправляется), T-05.12 закрывается, `docs/tasks.md`
обновляется.

- [ ] **Step 4: Тест второго пути запуска** _(только при подтверждённой гипотезе)_

```python
def test_prompt_credentials_launches_by_connection_string_without_secrets() -> None:
    """Shift-вариант обходит секцию: платформа не прочитает из неё Usr/Pwd и WA.

    [Ф] T-05.13 (дата и результат замера подставляются шагом 2) — форма
    подтверждена экспериментом. Пароль в argv читается любым процессом
    пользователя (скил platform-launch, «Пароль в командной строке —
    неустранимая утечка»), поэтому его отсутствие проверяется тестом,
    а не считается очевидным.
    """  # noqa: RUF002
    calls: list[LaunchCommand] = []
    item = _item_with_connect('Srvr="s";Ref="r";Usr="admin";Pwd="secret";')

    outcome = launch_infobase(
        item,
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        prompt_credentials=True,
        spawn=lambda command: (calls.append(command), 7)[1],
    )

    assert outcome.command_line is not None
    assert "/IBConnectionString" in outcome.command_line
    assert "/IBName" not in outcome.command_line
    assert "/WA-" in outcome.command_line
    assert "secret" not in outcome.command_line
    assert "Pwd" not in outcome.command_line
    assert "Usr" not in outcome.command_line
    assert 'Srvr=""s""' in outcome.command_line or 'Srvr="s"' in outcome.command_line


def test_normal_launch_still_goes_by_name() -> None:
    """F3/F4 остаются на /IBName: там работает диагностика неуникального имени.

    [Ф] T-05.3: платформа прекращает запуск с «Не уникальное имя
    информационной базы». По строке соединения этой диагностики нет.
    """  # noqa: RUF002
    item = _item_with_connect('Srvr="s";Ref="r";Usr="admin";Pwd="secret";')
    outcome = launch_infobase(
        item, installations=INSTALLED, cfg_rules=[], conventions=CONVENTIONS,
        default_app=None, spawn=lambda command: 7,
    )
    assert outcome.command_line is not None
    assert "/IBName" in outcome.command_line
```

- [ ] **Step 5: Реализация** _(только при подтверждённой гипотезе)_

`build_arguments` получает `prompt_credentials: bool = False`; при нём
в аргументы добавляется `/WA-`, а строка соединения собирается из исходной
**с вырезанными** секретными фрагментами и `Usr` — вырезание живёт
в `security/secrets.py` рядом с прочим знанием о секретах, а не в домене.

`launch_infobase` при `prompt_credentials=True` идёт по строке соединения
вместо `/IBName`. Обычные `F3`/`F4` остаются на `/IBName`: там работает
диагностика неуникального имени ([Ф] T-05.3) и чтение `WA` платформой.

`BasesView` получает `QShortcut("Shift+F3")` и `QShortcut("Shift+F4")`,
пункты меню — соответствующие подписи «…с запросом авторизации».

- [ ] **Step 6: Прогон, коммит, мутационная проверка** _(только при подтверждённой гипотезе)_

```bash
git add src/onecstarter tests .claude/skills/platform-launch docs/tasks.md
git commit -m "feat: Shift+F3/Shift+F4 — запуск с запросом авторизации"
```

Мутация: убрать вырезание секретных фрагментов из строки соединения.
Ожидание: падает тест на отсутствие `Pwd` в командной строке. Это защитный
тест уровня инварианта 5 — пароль в argv читается любым процессом
(скил `platform-launch`, «Пароль в командной строке — неустранимая утечка»).

Факт: _(заполнить при исполнении)_

---

### Task 17: ярлык `.lnk` и режим `--ib-name`

§5. Ярлык указывает на OneCStarter с именем базы; файл собираем своей записью
MS-SHLLINK без `pywin32`.

**Files:**
- Create: `src/onecstarter/config/shell_link.py`
- Modify: `src/onecstarter/services/workspace.py`
- Modify: `src/onecstarter/__main__.py`
- Modify: `src/onecstarter/ui/app.py`
- Modify: `src/onecstarter/ui/bases/view.py`
- Test: `tests/unit/test_shell_link.py` (создать)
- Test: `tests/unit/test_entry_point.py` (создать — разбор `--ib-name` без Qt)
- Test: `tests/unit/test_workspace.py` (дополнить)
- Test: `tests/unit/test_no_qt_in_core.py` (дополнить — новый модуль ядра)
- Test: `tests/ui/test_app.py` (дополнить)
- Test: `tests/ui/test_bases_view.py` (дополнить — пункт «Создать ярлык…»)
- Fixture: `tests/fixtures/reference.lnk` (эталон от заказчика, обезличенный)
- Modify: `pyproject.toml` (маркер `requires_windows_shell`, круг правок 1)

**Interfaces:**
- Produces:
  - `shell_link.build_shell_link(target: Path, arguments: str, working_dir: Path, description: str) -> bytes`.
  - `shell_link.safe_file_name(name: str) -> str` — имя базы → имя файла.
  - `shell_link.shortcut_command(executable: str, name: str, *, frozen: bool) -> tuple[Path, str]`
    — цель и аргументы ярлыка; чистая функция вместо сборки внутри диалога.
  - `shell_link.quote_argument(value: str) -> str` — экранирование по правилам
    `CommandLineToArgvW`: имя базы может содержать пробел и кавычку.
  - `shell_link.LinkNameRejectedError`, `shell_link.LinkTargetRejectedError`.
  - `Workspace.find_by_name(name: str) -> str` — ключ записи; `LaunchError`
    при неоднозначности, `UnknownItemError` при отсутствии.
  - `app.run_launch(name: str, env: Mapping[str, str]) -> int` — режим `--ib-name`.
  - `__main__.parse_ib_name(argv: Sequence[str]) -> str | None` — разбор аргументов
    без Qt (см. дефект 3 шага 5).
  - `ui.bases.view.BasesView.create_shortcut(key: str) -> None` и инъекция
    `choose_shortcut_path`.

- [x] **Step 1: Получить эталонный `.lnk` и разобрать его**

Формат бинарный, и писать его по памяти — ровно то, что `CLAUDE.md` запрещает.
Нужен эталон, созданный **самой Windows**, а не нами.

**Факт 09.08.2026: эталон создан и лежит в `tests/fixtures/reference.lnk`.**
Создан через COM-объект `WScript.Shell` (`CreateShortcut`), то есть штатной
реализацией `IShellLink` самой Windows — источник тот же, что у ярлыка,
сделанного мышью через контекстное меню. Цель — `notepad.exe` в системном
каталоге, аргументы `--ib-name "Демо"`, рабочий каталог системный, описание
`OneCStarter reference link`. Размер 1069 байт.

**[Ф] Находка, которой план не предусматривал: сырой `.lnk` нельзя класть
в публичный репозиторий.** Исходная редакция шага говорила «путь внутри
обезличить», подразумевая только цель ярлыка. На деле Windows пишет в файл
`TrackerDataBlock` (сигнатура `0xA0000003`, 96 байт), а в нём — `MachineID`:
NetBIOS-имя машины открытым ASCII. В снятом эталоне это было настоящее имя
рабочей машины заказчика. Там же четыре GUID'а отслеживания
(`Droid`/`DroidBirth`), а GUID версии 1 по формату несёт MAC-адрес сетевого
адаптера. То и другое — ровно то, что правило фикстур `CLAUDE.md` запрещает
вносить в репозиторий, и заметить это можно только заглянув в байты:
ни имя файла, ни свойства ярлыка в проводнике об этом не говорят.

Обезличено с сохранением структуры: `MachineID` заменён на `TESTMACHINE`
(поле фиксированной длины 16 байт с дополнением нулями — размер блока
не меняется), 64 байта GUID'ов отслеживания обнулены. Размер файла и заголовок
прежние, и Windows по-прежнему читает ярлык корректно — проверено обратным
чтением через `WScript.Shell`: цель, аргументы, рабочий каталог и описание
вернулись те же. Имени машины в файле больше нет.

**Факт разбора 09.08.2026** (hexdump + структурный разбор; значения
закреплены тестом `test_reference_field_values`):

| Поле | Значение |
| --- | --- |
| `HeaderSize` | `0x0000004C` (76) |
| `LinkCLSID` | `{00021401-0000-0000-C000-000000000046}` |
| `LinkFlags` | `0x000000BF` = `HasLinkTargetIDList` + `HasLinkInfo` + `HasName` + `HasRelativePath` + `HasWorkingDir` + `HasArguments` + `IsUnicode` |
| `FileAttributes` | `0x00000020` (`FILE_ATTRIBUTE_ARCHIVE`) |
| времена | реальные FILETIME'ы `notepad.exe`, `FileSize` = 360448 |
| `ShowCommand` | `1` (`SW_SHOWNORMAL`), `HotKey` = 0 |
| `LinkTargetIDList` | 321 байт, 5 элементов: `0x1F` «Этот компьютер» → `0x2F` диск `C:\` → два `0x31` (каталоги `Windows`, `System32`) → один `0x32` (файл `notepad.exe`) |
| `LinkInfo` | 80 байт, `HeaderSize` = `0x1C` (только ANSI), `VolumeIDAndLocalBasePath`, `DriveType` = 3, серийный номер тома, метка `OS`, `LocalBasePath` = `C:\Windows\System32\notepad.exe` |
| `StringData` | **UTF-16LE** (флаг `IsUnicode`): длина в символах + текст без завершающего нуля |
| `ExtraData` | `SpecialFolderDataBlock` (37 = CSIDL_SYSTEM), `KnownFolderDataBlock` (FOLDERID_System), `TrackerDataBlock`, `PropertyStoreDataBlock`, терминатор `0x00000000` |

**[Ф] Вторая находка обезличивания: `MachineID` и GUID'ы отслеживания были
не единственными данными машины в файле.** Разбор `PropertyStoreDataBlock`
(сигнатура `0xA0000009`) показал ещё два поля, о которых прошлая редакция
шага не знала:

- store `{46588AE2-4CBC-4338-BBFC-139326986DCE}`, PID 4, `VT_LPWSTR` —
  **SID пользователя** `S-1-5-21-…-1001`, а в нём SID машины;
- store `{446D16B1-8DAD-4870-A748-402EA43D788C}`, PID 104, `VT_CLSID` —
  **GUID тома системного диска**.

Плюс `LinkInfo.VolumeID.DriveSerialNumber` — серийный номер тома. Всё три
дообезличены с сохранением размеров: SID заменён на условный той же длины
(44 символа), GUID тома и серийный номер обнулены. Размер файла прежний
(1069 байт), Windows читает ярлык корректно — проверено обратным чтением
через `WScript.Shell`.

Чтобы это не повторилось молча, добавлен сторож
`test_reference_fixture_carries_no_machine_identity`: он падает, если
фикстуру пересняли с живой машины и не обезличили. Мутационная проверка
выполнена — подмена SID в фикстуре роняет тест.

**[Р] Остаток риска, который я закрыть не могу:** коммит `4121853`
(«test: эталонный .lnk для задачи 17, обезличенный по байтам») уже содержит
редакцию фикстуры с настоящим SID пользователя и GUID тома. Дообезличивание
сделано новым коммитом, поэтому **в истории ветки эти значения остаются**.
Удалённого репозитория у проекта сейчас нет, ветка не опубликована, так что
утечки наружу пока не произошло. Решение заказчику: до слияния ветки и до
появления remote либо схлопнуть `4121853` с коммитом дообезличивания
(`git rebase -i`), либо принять риск сознательно.

**Без этого шага к реализации не переходить.** Побайтовый тест против
собственного эталона проверял бы только то, что мы не изменили своё же
представление о формате.

- [x] **Step 2: Тесты сборки**

**Дефект 1 плана, найденный на этом шаге: `assert built[:76] == reference[:76]`
неисполним.** Первые 76 байт — это весь заголовок, а в нём лежат `LinkFlags`,
времена создания/доступа/изменения цели и её размер. Времена и размер в эталоне
— настоящие метаданные `notepad.exe` на машине заказчика; воспроизвести их
можно было бы только тем, что мы обязаны **не** делать: читать метаданные цели
и переносить их в файл. Флаги тоже законно различаются: мы не пишем
`LinkInfo` и `RelativePath` (см. шаг 3).

Сравнивать байт в байт можно ровно первые 20 байт — `HeaderSize` и `LinkCLSID`;
это и есть постоянная часть. Остальное проверяется по смыслу:

```python
def test_reference_header_is_the_constant_prefix() -> None:
    assert _built()[:20] == REFERENCE.read_bytes()[:20]


def test_built_link_declares_only_what_it_writes() -> None:
    """Флаги нашего файла — подмножество флагов эталона, без выдуманных бит."""
    reference = _parse(REFERENCE.read_bytes())
    parsed = _parse(_built())
    assert parsed.flags & reference.flags == parsed.flags
```

**Дефект 2 плана: `pytest.raises(InvalidRequestError)` переворачивает слои.**
`InvalidRequestError` живёт в `services.errors`, а `shell_link` — модуль слоя
`config`; зависимость `config` → `services` противоречит и направлению
зависимостей (`services.writer` импортирует `config.v8i`), и докстрингу самого
`services/errors.py` («общий корень исключений слоя services»). Сделано так же,
как с `LineBreakRejectedError` в `v8i.py`: слой `config` заводит собственную
ошибку `LinkNameRejectedError(ValueError)`, а перевод в `InvalidRequestError`
делает потребитель — `BasesView.create_shortcut`.

Итоговый набор тестов имени файла расширен краевыми случаями, которых
в плане не было: имя из одних точек, имя устройства DOS (`CON`, `com1` —
`CON.lnk` так же недопустим, как `CON`) и имя длиннее предела NTFS.

```python
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Бухгалтерия", "Бухгалтерия.lnk"),
        ('Учёт: "склад"/2', "Учёт_ _склад__2.lnk"),
        ("   ", None),
        ("", None),
        ("...", None),
        ("Розница.", "Розница.lnk"),
        ("CON", "_CON.lnk"),
        ("com1", "_com1.lnk"),
        ("a" * 300, "a" * 200 + ".lnk"),
    ],
)
def test_safe_file_name(name: str, expected: str | None) -> None:
    if expected is None:
        with pytest.raises(LinkNameRejectedError):
            safe_file_name(name)
    else:
        assert safe_file_name(name) == expected
```

- [x] **Step 3: Реализация `config/shell_link.py`**

Состав пишется **по разбору эталона из шага 1**, а не по памяти. Модуль
ложится рядом с `v8i.py` и `cestart_cfg.py`: тот же класс задачи — чужой
формат, побайтовые тесты, никаких зависимостей.

**Разбора эталона оказалось мало — состав определён экспериментом.** Эталон
показывает, что Windows пишет, но не что из этого обязательно. Проверено
на Windows 11 09.08.2026: каждый вариант собирался отдельным файлом,
запускался через `ShellExecute` (`os.startfile`, тот же путь, что двойной
клик в проводнике) и читался обратно через `WScript.Shell` (`IShellLink`,
то же, что показывает вкладка «Ярлык» в свойствах). Цель — `cmd.exe`
с `/c echo ok>файл`, признак успеха — появившийся файл.

| Вариант | Запуск | `TargetPath` при обратном чтении |
| --- | --- | --- |
| эталон Windows | работает | верный |
| эталон Windows **без** `LinkTargetIDList` | `WinError 1155` | пусто |
| наш файл: только `LinkInfo`, без `LinkTargetIDList` | `WinError 1155` | пусто |
| наш файл: `LinkTargetIDList` + `LinkInfo` | работает | верный |
| наш файл: `LinkTargetIDList`, **без** `LinkInfo` | работает | верный |
| верный `LinkInfo`, `LinkTargetIDList` на несуществующий файл | `WinError 2` | — |
| верный `LinkTargetIDList`, путь в `LinkInfo` испорчен | **работает** | верный |
| элементы `0x31`/`0x32`, ANSI-имя испорчено, Unicode-имя в блоке `BEEF0004` верное | `WinError 1223` | — |
| элементы `0x35`/`0x36` (имя сразу в UTF-16), путь ASCII и путь с кириллицей | работает | верный |

Выводы, на которых стоит реализация:

1. **`LinkTargetIDList` обязателен и он же задаёт цель.** `LinkInfo` целью
   не является вовсе — ярлык с испорченным `LinkInfo` запускается, а с
   испорченным списком нет. План этого не оговаривал, и «минимальный» файл
   без списка, который казался естественным, не работает совсем.
2. **Части пути пишем элементами классов `0x35`/`0x36`** — имя сразу
   в UTF-16. Классы `0x31`/`0x32` несут имя в кодовой странице ANSI машины,
   и оно ведущее (строка про `WinError 1223`): вывод зависел бы от кодовой
   страницы, а путь с символами вне неё дал бы молча нерабочий ярлык.
   Сама Windows для не-ASCII имён пишет ровно `0x35`/`0x36` — проверено
   на ярлыке, сделанном `WScript.Shell` на путь с кириллицей.
3. **Не пишем `TrackerDataBlock`, `PropertyStoreDataBlock` и `LinkInfo`.**
   Для запуска они не нужны (строки 5 и 6 таблицы), а несут имя машины,
   MAC-адрес, SID пользователя и серийный номер тома — то самое, что
   инвариант 5 запрещает класть в файлы пользователя. Побочное следствие:
   вывод детерминирован, одни и те же аргументы дают один и тот же файл
   на любой машине (`test_built_link_is_deterministic`).
4. **Времена и размер цели — нули.** MS-SHLLINK разрешает («время не
   задано»), и это отказ переносить чужие метаданные, а не заглушка.
5. Блок расширения `BEEF0004` не пишется: версии ≥ 7 требуют ссылку
   на файл в MFT (машинно-зависимая), а без блока ярлык работает.
6. Цель не на локальном диске (UNC, относительный путь, корень диска)
   отвергается `LinkTargetRejectedError`: форма списка для UNC другая,
   и испорченный ярлык хуже отказа.

**Круг правок 1 (ревью 09.08.2026): атрибуция [Р] была неверна.** Первая
редакция докстринга говорила, что разметка классов `0x1F`, `0x2F`, `0x35`,
`0x36` «снята с байтов эталона». Ревью проверило: **`0x35`/`0x36`
в эталоне нет вовсе** — он сделан на путь из одних ASCII-имён, и там
`0x31`/`0x32`. С эталона сняты `0x1F`, `0x2F` и `0x31`/`0x32` (последние
мы не пишем); разметка `0x35`/`0x36` перенесена по аналогии — тот же
12-байтовый префикс, имя в UTF-16 вместо ANSI. Уровень [Р] был честен,
источник — нет.

Пробел закрыт **тестом**, а не второй фикстурой:
`test_windows_shell_reads_our_link` отдаёт наш файл штатному `IShellLink`
(`WScript.Shell` через `subprocess`, без `pywin32`) и сверяет цель,
аргументы, рабочий каталог и описание; цель при этом не запускается.
Вторая фикстура показала бы только, что пишет Windows, оставив наши
собственные байты неподтверждёнными, — а подтвердить их может лишь
потребитель формата. Тест помечен `requires_windows_shell` и пропускается
вне Windows.

Первые два элемента списка теперь сверяются с **разобранным эталоном**,
а не с литералами (замечание ревью): у эталона та же цель на диске `C:`,
и эти два элемента обязаны совпадать байт в байт.

**[Ф] Ограничение инструмента, важное при чтении результатов:**
`WScript.Shell` теряет символы за пределами BMP — ярлык, записанный
им самим, содержит в байтах `??` вместо эмодзи. Потеря происходит
до файла, это ограничение скриптовой обёртки, а не формата. Поэтому
астральные символы через этот сторож не сверяются; их покрывает разбор
байтов (`test_string_data_counts_utf16_code_units`) и сквозной опыт:
ярлык → `ShellExecute` → `CommandLineToArgvW` → `sys.argv` →
`parse_ib_name` вернул исходное имя с эмодзи.

**Дефект 4, найденный ревью: `CountCharacters` считался в кодовых точках.**
`_string_data` писал `len(value)`, а MS-SHLLINK требует число кодовых
**единиц** UTF-16. На суррогатной паре счётчик занижался, и вся цепочка
`StringData` ехала: аргументы приклеивались к рабочему каталогу, описание
обрезалось — при этом ярлык создавался без ошибки. Имя вида
`🔴 Бухгалтерия ПРОД` давало ярлык, который по клику открывал главное окно
вместо запуска базы. Исправлено на `len(value.encode("utf-16-le")) // 2`.

- [x] **Step 4: `Workspace.find_by_name`**

```python
    def find_by_name(self, name: str) -> str:
        """Ключ записи по имени базы. Сравнение без учёта регистра.

        [Ф] T-05.3: платформа ищет имя регистронезависимо и считает дублями
        имена, различающиеся только регистром. Ярлык несёт имя, а не ключ:
        ключ меняется, когда записи дописывается `ID`, и ярлык сломался бы
        от первой же правки записи через нас.
        """  # noqa: RUF002
        wanted = name.casefold()
        found = [
            item for item in self._items
            if not item.is_group and item.name.casefold() == wanted
        ]
        if not found:
            raise UnknownItemError(f"Базы с именем «{name}» нет в списке")  # noqa: RUF001
        keys = {item.key for item in found}
        if len(keys) > 1:
            raise LaunchError(
                f"Имя «{name}» в списке не единственное ({len(keys)} "
                f"{_records_word(len(keys))}): запуск по имени неоднозначен"
            )
        return found[0].key
```

- [x] **Step 5: Режим `--ib-name`**

```python
def run_launch(name: str, env: Mapping[str, str]) -> int:
    """Запустить базу по имени и выйти. Окно не показывается.

    Ошибки идут в QMessageBox, а не в stdout: entry point собран поверх
    pythonw.exe, у которого нет консоли (§9 п. 4 спеки 4a), и текст ушёл бы
    в никуда.
    """  # noqa: RUF002
```

`__main__.main` разбирает `--ib-name <имя>` и уводит в `run_launch`; без
аргументов — прежний путь с окном.

**Дефект 3 плана: разбор аргументов негде было проверить.** Прежний
`__main__.py` импортировал `ui.app` на уровне модуля, то есть тянул `PySide6`
при любом импорте. Разбор аргументов — чистая функция, и держать её за
Qt-барьером незачем: `PySide6` импортируется внутри `main()`, а
`parse_ib_name` проверяется табличным тестом в `tests/unit/`.

`argparse` не используется сознательно: на неизвестный ключ он печатает
справку в stderr и зовёт `sys.exit` — в сборке поверх `pythonw.exe` оба
действия невидимы пользователю.

Решённая по ходу неоднозначность: **`--ib-name` без значения — не то же
самое, что отсутствие ключа.** Первое даёт пустую строку и сообщение
«Не указано имя информационной базы», второе — `None` и обычное окно. Если
бы оба давали окно, опечатка в ярлыке выглядела бы как «ярлык открывает
не то, что должен», без единой подсказки.

- [x] **Step 6: Пункт «Создать ярлык…»**

`QFileDialog.getSaveFileName` с предзаполненным рабочим столом
(`QStandardPaths.StandardLocation.DesktopLocation`) и именем из
`safe_file_name(item.name)`. Цель — `sys.executable`; когда мы не заморожены
(`not getattr(sys, "frozen", False)`), в аргументы добавляется
`-m onecstarter`. Расчёт цели и аргументов — чистая функция с тестом
(`shortcut_command`), а не сборка внутри диалога.

Уточнения по ходу:

- Диалог инжектируется параметром `choose_shortcut_path` — тем же приёмом,
  что `confirm_removal`/`ask_group_removal`/`browse_for_directory`: настоящий
  `QFileDialog` в офскрин-тесте не дождётся выбора.
- Запись через `config.atomic.atomic_write`, а не `Path.write_bytes`
  (инвариант 4): диалог сохранения разрешает выбрать существующий ярлык,
  и наполовину записанный файл на месте рабочего — ровно та потеря,
  от которой инвариант защищает.
- Пункт показывается и веб-базе: ярлык зовёт нашу программу с `--ib-name`,
  а та для веб-базы открывает браузер. Пункты клиентов веб-базе по-прежнему
  не показываются — это разные вещи.
- Имя базы попадает в аргументы через `quote_argument` (правила
  `CommandLineToArgvW`): имя приходит из чужого файла и может содержать
  и пробел, и кавычку.

**Дефект 5, найденный ревью: ярлык на базу с неуникальным именем
создавался молча.** `create_shortcut` не спрашивал `find_by_name` —
проверка дублей стояла только в `run_launch`. Две базы с одним именем —
обычное дело (копия базы в другой группе, та же база из общего списка
с другим `ID`), и пользователь получал ярлык без единой жалобы, а
«Имя не единственное» — потом, по клику, когда связь с созданием ярлыка
уже не очевидна. Проверка перенесена **до** диалога, отказ идёт
в `_on_error`. Она неполна и не может быть полной: дубль появится и после
создания ярлыка — так и записано в докстринге, окончательный барьер
остаётся в `run_launch`.

- [x] **Step 7: Прогон, коммит**

Факт: `6d68434` «feat: ярлык .lnk на OneCStarter и режим запуска по имени
базы», `2d2dd41` «fix: круг правок 1 задачи 17 — счётчик UTF-16,
атрибуция [Р], дубль имени», `2607698` «test: quote_argument против
настоящего CommandLineToArgvW». Прогон по кодам выхода: `pytest` **935
passed** (было 867), `ruff` 0, `mypy` 0 на 111 файлах.

Мутационная проверка защитных тестов — 15 мутаций (9 в первом заходе,
4 в круге правок 1, 2 в круге правок 2), все пойманы, каждая откатывалась
`git checkout --` после прогона:

| Мутация | Тест | Как упал |
| --- | --- | --- |
| SID в фикстуре заменён на другой | `test_reference_fixture_carries_no_machine_identity` | `AssertionError: SID … не заменён на условный` |
| `build_shell_link` пишет `TrackerDataBlock` | `test_built_link_carries_no_machine_data` | `assert {2684354563: …} == {}` |
| `_id_list` не отвергает путь без буквы диска | `test_build_rejects_target_without_drive_path` | `DID NOT RAISE LinkTargetRejectedError` |
| `safe_file_name` не отвергает пустой результат | `test_safe_file_name` | `DID NOT RAISE LinkNameRejectedError` |
| `find_by_name` без проверки неоднозначности | `test_find_by_name_rejects_ambiguous_name` | `DID NOT RAISE LaunchError` |
| `find_by_name` сравнивает с учётом регистра | `test_find_by_name_ignores_case` | `UnknownItemError` |
| `run_launch` без проверки пустого имени | `test_run_launch_rejects_empty_name` | `build_runtime не должен вызываться` |
| `create_shortcut` игнорирует отказ от диалога | `test_create_shortcut_cancelled_writes_nothing` | записан `InvalidRequestError` вместо пустого списка |
| `create_shortcut` без проверки пропавшей записи | `test_create_shortcut_ignores_unknown_key` | `AttributeError: 'NoneType' … 'name'` |
| `_string_data` снова считает кодовые точки | `test_string_data_counts_utf16_code_units` | `struct.error: … buffer of at least 467 bytes` |
| части пути пишутся ANSI-классами `0x31`/`0x32` | `test_windows_shell_reads_our_link` | `IShellLink` вернул `C:\U\a\A…` вместо пути |
| первый элемент списка расходится с эталоном | `test_built_id_list_spells_out_the_target` | `At index 1 diff: b'Q' != b'P'` |
| `create_shortcut` не зовёт `find_by_name` | `test_create_shortcut_refuses_ambiguous_name` | «диалог сохранения не должен открываться» |
| кавычка в имени не экранируется | `test_quote_argument_survives_real_parser` | 3 случая из 9: `Учёт "склад"` вернулось как `Учёт склад` |
| слэши перед закрывающей кавычкой не удваиваются | `test_quote_argument_survives_real_parser` | 2 случая из 9: `Демо ПРОД\` вернулось как `Демо ПРОД"` |

- [ ] **Step 8: Ручная проверка ярлыка на машине заказчика**

Единственная настоящая проверка формата: создать ярлык, открыть его свойства
в проводнике, запустить. Побайтовый тест ловит регрессию, но не ловит
«Windows такой ярлык не принимает».

Часть этой проверки закрыта машинно. Что именно закрыто и чем — по пунктам,
без обобщений:

- **чтение нашего файла штатным `IShellLink`** — постоянным тестом
  `test_windows_shell_reads_our_link` (шаг 3);
- **экранирование имени базы против настоящего `CommandLineToArgvW`** —
  постоянным тестом `test_quote_argument_survives_real_parser` (круг
  правок 2): командная строка собирается нашим `quote_argument` и отдаётся
  `CreateProcess` строкой, разбирает её обратно сам Windows. Девять случаев,
  включая имя из одной кавычки, кавычку внутри имени, обратный слэш перед
  кавычкой и завершающий обратный слэш;
- **доставка имени до процесса через сам ярлык** — сквозными опытами:
  круг правок 1 прогнал имя с пробелами и символом за пределами BMP,
  круг правок 2 — четыре имени с кавычками, включая `Базы\"тест"` и имя
  из одной кавычки. Во всех случаях `parse_ib_name` вернул исходное имя.

**Дефект 6 плана, найденный ре-ревью: пункт про `quote_argument` был снят
преждевременно.** Круг правок 1 закрыл его словами «сквозной опыт это
покрывает», но тот опыт гонял имя `🔴 Бухгалтерия ПРОД` — пробелы
и астральный символ, **без встроенной кавычки**. Ветка экранирования
символа `"` через живой `CommandLineToArgvW` не проходила ни разу, и её
единственной проверкой оставалась таблица против нашей же модели правил —
ровно то, чему исходный пункт и не доверял. Это тот же класс подмены
(заявление о проверке вместо проверки), который круг правок 1 чинил
в атрибуции `[Р]`. Теперь пункт закрыт доказательством: тестом
и сквозным опытом выше. Мутации подтверждают, что проверка живая — снятие
экранирования кавычки роняет 3 случая из 9, отказ от удвоения слэшей
перед закрывающей кавычкой — 2 из 9.

Не закрыто то, что требует живого приложения и глаз:

1. Собранный (frozen) экземпляр: ярлык на `OneCStarter.exe`, а не на
   `python.exe -m onecstarter`. Ветка `frozen=True` в тестах не исполняется
   ни разу — под pytest `sys.frozen` отсутствует. Главный оставшийся пробел.
2. Вид ярлыка в проводнике: значок, подпись, вкладка «Ярлык» — цель,
   рабочая папка, поле «Объект» с аргументом `--ib-name`.
3. Двойной клик по ярлыку на настоящей базе: запускается ли 1С и та ли база.
   Процессы 1С в тестах не запускаются никогда.
4. Ярлык на базу, имя которой в списке не единственное: с круга правок 1
   ожидается отказ **при создании** ярлыка, а не при клике по нему.

Факт: _(заполнить при исполнении — выполняет заказчик)_

---

### Task 18: `UnknownItemError` предлагает обновить список

§8. Хвост 4a: §3 спеки 4a обещает предложение обновить список, задача 14
плана 4a оставила его на 4b.

**Files:**
- Modify: `src/onecstarter/services/workspace.py:272-278`
- Test: `tests/unit/test_workspace.py`

**Interfaces:** изменений в сигнатурах нет.

- [x] **Step 1: Тест**

```python
def test_unknown_key_message_offers_a_way_out(tmp_path: Path) -> None:
    """Сообщение обязано говорить, что делать, а не только что случилось.

    Ключ исчезает при внешней правке файла — штатным стартером, например.
    Пользователю нужно знать, что список надо перечитать.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    with pytest.raises(UnknownItemError) as info:
        workspace.launch("id:нет-такого")
    assert "обновите список" in str(info.value).casefold()
```

- [x] **Step 2: Реализация**

```python
        raise UnknownItemError(
            "Записи с таким ключом нет в списке — возможно, файл изменился "
            "извне. Обновите список и повторите"
        )
```

- [x] **Step 3: Прогон и коммит**

```bash
git add src/onecstarter/services/workspace.py tests/unit/test_workspace.py
git commit -m "fix: сообщение о пропавшей записи предлагает обновить список"
```

Факт: подтверждено. Реализовано дословно по брифу (номера строк в `Files`
устарели — метод `_item` сместился на строку 282, класс `UnknownItemError`
живёт в `services/errors.py`, а не в `workspace.py`; это ожидаемый дрейф,
исправления плана не требует). Мутационная проверка: правка → 867/867
зелёных, `ruff`/`mypy` чистые → коммит `187616c` → мутация (откат текста
исключения на старую однострочную формулировку) → новый тест упал на
`assert "обновите список" in ...` (`AssertionError`) → `git checkout --`
вернул коммит `187616c` → повторный прогон 867/867, `ruff`/`mypy` чистые.

---

### Task 20: приём каталога в разделе «Базы»

Спека §3.4, решения §14. По итогам ручного smoke №2: §3.1 помещал приём каталога
только на диалог, и заказчик его там не нашёл — бросал на список.

Идёт **после** задачи 18 и **перед** задачей 19: финальная верификация обязана
видеть уже всё. Номер 20 при этом больше 19 — так сохранены ссылки на задачи
16–19 в уже написанных коммитах и разделах.

**Files:**

- Modify: `src/onecstarter/ui/dialogs/infobase.py` — `_dropped_directory` становится
  модульной функцией `dropped_directory`
- Modify: `src/onecstarter/ui/bases/view.py` — три обработчика `_BasesTree`,
  `BasesView.folder_for_dropped_directory`, `build_dialog_for_dropped_directory`,
  `add_infobase_from_directory`, обёртки на `BasesView`, запрет drop полю поиска
- Test: `tests/ui/test_infobase_dialog.py` (перевести на модульную функцию)
- Test: `tests/ui/test_bases_view.py` (дополнить)

**Interfaces:**

- Consumes: `InfobaseDialog.for_new`, `.accept_directory`, `.set_folder`,
  `BasesView._build_add_dialog`, `._apply_new_infobase`, `._folder_of_drop`,
  `._group_paths`, `_BasesTree._row_key`, `._row_kind`, `._rejects_drop_at`,
  `services.paths.ROOT` (всё существует).
- Produces:
  - `ui.dialogs.infobase.dropped_directory(mime: QMimeData) -> str | None`
  - `BasesView.folder_for_dropped_directory(target_key: str | None, kind: str | None) -> str`
  - `BasesView.build_dialog_for_dropped_directory(directory: str, target_key: str | None, kind: str | None) -> InfobaseDialog`
  - `BasesView.add_infobase_from_directory(directory: str, target_key: str | None = None, kind: str | None = None) -> None`

- [x] **Step 1: Вынести `dropped_directory` в модульную функцию**

Знание «есть ли в mime ровно один каталог» нужно теперь двоим — диалогу и дереву,
и статический метод одного из них перестал быть для него местом.

В `ui/dialogs/infobase.py` убрать `@staticmethod _dropped_directory` из класса
и положить на уровень модуля **без изменения тела**; докстринг переезжает дословно.

```python
def dropped_directory(mime: QMimeData) -> str | None:
    """Путь каталога из mime-данных перетаскивания — `None`, если это не он.

    ...докстринг переносится дословно, включая замер QUrl.toLocalFile()...
    """  # noqa: RUF002
    urls = mime.urls()
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return str(path) if path.is_dir() else None
```

Три вызова внутри `InfobaseDialog` (`dragEnterEvent`, `dragMoveEvent`, `dropEvent`)
переписать с `self._dropped_directory(...)` на `dropped_directory(...)`.

В `tests/ui/test_infobase_dialog.py` заменить обращения к
`InfobaseDialog._dropped_directory` на импорт `dropped_directory`. **Логика тестов
не меняется** — правится только имя.

- [x] **Step 2: Прогон — существующие тесты обязаны остаться зелёными**

Run: `uv run pytest tests/ui/test_infobase_dialog.py -q`

Expected: PASS, число тестов прежнее. Это рефактор: красный тест здесь означает,
что перенос что-то задел.

```bash
git add src/onecstarter/ui/dialogs/infobase.py tests/ui/test_infobase_dialog.py
git commit -m "refactor: dropped_directory становится модульной функцией"
```

- [x] **Step 3: Тест группы по месту броска (RED)**

В `tests/ui/test_bases_view.py` дополнить импорты:
`from onecstarter.services.paths import ROOT, group_path, normalize_folder`

```python
@pytest.mark.parametrize(
    "kind",
    [RowKind.SECTION, RowKind.NOTE, RowKind.IMPLICIT_GROUP, None],
)
def test_folder_for_dropped_directory_falls_back_to_root(
    qtbot: Any, workspace_factory: Any, kind: Any
) -> None:
    """Служебные строки и неявный узел дают корень, а не отказ.

    Пользователь целился в список, а не в конкретную ветку; диалог всё равно
    покажет выбранную группу до подтверждения (спека §3.4).
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    value = kind.value if kind is not None else None

    folder = view.folder_for_dropped_directory(None, value)

    assert folder == ROOT


def test_folder_for_dropped_directory_uses_the_group_under_cursor(
    qtbot: Any, workspace_factory: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    group = next(i for i in view.workspace().items() if i.is_group)

    folder = view.folder_for_dropped_directory(group.key, RowKind.GROUP.value)

    assert folder == group_path(group.folder, group.name)


def test_folder_for_dropped_directory_uses_the_parent_of_a_base(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Бросок на запись значит «рядом с ней», то есть в её группу."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    base = next(
        i for i in view.workspace().items() if not i.is_group and i.folder != ROOT
    )

    folder = view.folder_for_dropped_directory(base.key, RowKind.BASE.value)

    assert folder == normalize_folder(base.folder)


def test_folder_for_dropped_directory_rejects_a_dangling_folder(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Висячий `Folder` группой не является — такого пункта в диалоге нет.

    [Ф] T-05.7: путь, которому не соответствует ни одна секция, платформа
    рисует неявным узлом. Вернуть его как группу значило бы отдать `set_folder`
    значение, которого нет в списке, и диалог отказал бы уже после броска.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    # Фикстура `anonymized.v8i` такую запись уже содержит («Потерянная»),
    # поэтому состояние не портим — берём готовый краевой случай.
    orphan = next(
        item
        for item in view.workspace().items()
        if not item.is_group and normalize_folder(item.folder) not in view._group_paths()
    )

    folder = view.folder_for_dropped_directory(orphan.key, RowKind.BASE.value)

    assert folder == ROOT
```

- [x] **Step 4: Прогон (FAIL), реализовать `folder_for_dropped_directory`**

Run: `uv run pytest tests/ui/test_bases_view.py -q -k folder_for_dropped`

Expected: FAIL, `AttributeError: 'BasesView' object has no attribute 'folder_for_dropped_directory'`

```python
    def folder_for_dropped_directory(
        self, target_key: str | None, kind: str | None
    ) -> str:
        """`Folder` новой записи по месту, куда отпустили каталог. Спека §3.4.

        Переиспользует `_folder_of_drop`, а не заводит вторую логику путей:
        для строки-группы это `INTO` (собственный путь группы), для строки-базы
        `AFTER` (путь родителя). Всё остальное — служебные ветки, неявный узел,
        промах мимо строк — корень.

        Итог проверяется на членство в `_group_paths()`. Без этого висячий
        `Folder` ([Ф] T-05.7) вернулся бы как группа, которой в списке диалога
        нет, и `set_folder` отказал бы уже после броска — на ровном месте.

        **Находка исполнения задачи 20 (дефект этого шага плана, исправлено
        в тексте):** `_folder_of_drop` отдаёт путь в файловой форме
        (`render_folder` — с ведущим слэшем для вложенных путей, её ждут
        `Workspace.update_infobase`/`update_group`), а `_group_paths()`/
        `InfobaseDialog.set_folder` работают в форме `normalize_folder`
        (без ведущего слэша, как и `group_path`). Код ниже без финального
        `normalize_folder(folder)` компилируется и проходит табличную
        проверку типов, но на живой фикстуре `_folder_of_drop("Клиенты")`
        отдаёт `/Клиенты`, чего нет и не может быть в `_group_paths()`, —
        членство проваливается для ЛЮБОЙ настоящей группы, и функция всегда
        откатывается на корень. Обнаружено прогоном тестов шага 4 (RED
        по другой причине, чем ожидалось), исправлено добавлением
        `normalize_folder` перед проверкой членства.
        """  # noqa: RUF002
        if kind == RowKind.GROUP.value:
            folder = self._folder_of_drop(target_key, DropTarget.INTO)
        elif kind == RowKind.BASE.value:
            folder = self._folder_of_drop(target_key, DropTarget.AFTER)
        else:
            folder = None
        normalized = normalize_folder(folder)
        return normalized if normalized in self._group_paths() else ROOT
```

Run: `uv run pytest tests/ui/test_bases_view.py -q -k folder_for_dropped`

Expected: PASS

- [x] **Step 5: Тест сборки диалога из брошенного каталога (RED)**

```python
def test_dialog_from_dropped_directory_is_prefilled(
    qtbot: Any, workspace_factory: Any, tmp_path: Any
) -> None:
    """Путь, имя и группа подставлены до показа диалога.

    Сборка отделена от показа тем же приёмом, что у `_build_add_dialog`:
    `exec()` блокирует offscreen-тесты, и без разделения этот путь остался бы
    без покрытия — дефект, который ревью задачи 8 нашло у `show_properties`.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    directory = tmp_path / "Бухгалтерия"
    directory.mkdir()
    group = next(i for i in view.workspace().items() if i.is_group)

    dialog = view.build_dialog_for_dropped_directory(
        str(directory), group.key, RowKind.GROUP.value
    )
    qtbot.addWidget(dialog)

    name, connect, folder = dialog.new_record()
    assert name == "Бухгалтерия"
    assert connect == 'File="' + str(directory) + '";'
    assert folder == group_path(group.folder, group.name)
```

- [x] **Step 6: Прогон (FAIL), реализовать сборку и показ**

Run: `uv run pytest tests/ui/test_bases_view.py -q -k dropped_directory_is_prefilled`

Expected: FAIL, нет атрибута `build_dialog_for_dropped_directory`

```python
    def build_dialog_for_dropped_directory(
        self, directory: str, target_key: str | None, kind: str | None
    ) -> InfobaseDialog:
        """Диалог добавления с подставленными путём, именем и группой.

        Сборка без показа — как `_build_add_dialog`, и по той же причине.
        """  # noqa: RUF002
        dialog = self._build_add_dialog()
        dialog.accept_directory(directory)
        dialog.set_folder(self.folder_for_dropped_directory(target_key, kind))
        return dialog

    def add_infobase_from_directory(
        self, directory: str, target_key: str | None = None, kind: str | None = None
    ) -> None:
        """Каталог, брошенный в раздел, — диалог добавления, а не запись сразу.

        Решение заказчика 09.08.2026 (спека §14, п. 2): имя каталога не всегда
        годится как имя базы, а молчаливое создание записи от случайного броска
        меняет чужой файл без спроса. Диалог и `Workspace.add_infobase`
        используются существующие — второго пути создания записи не появляется.
        """  # noqa: RUF002
        dialog = self.build_dialog_for_dropped_directory(directory, target_key, kind)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_new_infobase(dialog)
```

Run: `uv run pytest tests/ui/test_bases_view.py -q -k dropped_directory_is_prefilled`

Expected: PASS

- [x] **Step 7: Тесты приёма каталога деревом (RED)**

Помощник `_drag_move_event` дополняется необязательным `mime` — тем же способом,
что `_drop_event`, и с тем же удержанием ссылки на `QMimeData`:

```python
def _directory_mime(path: Any) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    return mime


def _drag_move_event(
    pos: QPoint, mime: QMimeData | None = None
) -> tuple[QDragMoveEvent, QMimeData]:
    data = mime if mime is not None else QMimeData()
    return (
        QDragMoveEvent(
            pos,
            Qt.DropAction.MoveAction,
            data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
        data,
    )
```

Импорт теста дополнить: `from PySide6.QtCore import QUrl`.

```python
def test_tree_drop_of_a_directory_opens_the_add_dialog(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Каталог, брошенный на строку, доходит до add_infobase_from_directory."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    rect = _visible_rect_of_kind(view, RowKind.GROUP)
    index = tree.indexAt(rect.center())
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: calls.append(args)
    )
    mime = _directory_mime(tmp_path)

    tree.dropEvent(_drop_event(rect.center(), mime))

    assert calls == [(str(tmp_path), index.data(KEY_ROLE), RowKind.GROUP.value)]


def test_tree_drop_of_a_file_is_not_taken_for_a_directory(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Файл — не каталог: путь добавления не запускается вовсе."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    rect = _visible_rect_of_kind(view, RowKind.GROUP)
    plain = tmp_path / "не-каталог.txt"
    plain.write_text("x", encoding="utf-8")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: calls.append(args)
    )
    # Ссылка на mime держится в переменной до вызова dropEvent — ИНАЧЕ (см.
    # находку ниже) сборщик мусора вправе забрать `QMimeData` до того, как
    # `event.mimeData()` внутри обработчика успеет её прочитать.
    mime = _directory_mime(plain)

    tree.dropEvent(_drop_event(rect.center(), mime))

    assert calls == []


def test_tree_drag_move_accepts_a_directory_over_a_base_row(
    qtbot: Any, workspace_factory: Any, tmp_path: Any
) -> None:
    """Над строкой-записью каталог принимается, хотя своя запись — нет.

    Разный ответ на один жест намеренный (спека §3.4): своя запись
    «вкладывается» и потому отвергается, чужой каталог «добавляется рядом».
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    rect = _visible_rect_of_kind(view, RowKind.BASE)
    event, _mime = _drag_move_event(rect.center(), _directory_mime(tmp_path))
    event.ignore()

    tree.dragMoveEvent(event)

    accepted = event.isAccepted()
    assert accepted is True
```

- [x] **Step 8: Прогон (FAIL), реализовать три обработчика `_BasesTree`**

Run: `uv run pytest tests/ui/test_bases_view.py -q -k "tree_drop_of_a or tree_drag_move_accepts"`

Expected: FAIL — каталог до `add_infobase_from_directory` не доходит

Правило одно на все три: **есть каталог — обрабатываем сами, до `super()`
не доходим; нет — зовём `super()`.** Режим `InternalMove` не меняется,
барьер задачи 14 остаётся дословно (спека §3.4).

```python
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        if self._rejects_drop_at(event.position().toPoint()):
            event.ignore()
            return
        super().dragMoveEvent(event)
```

В `dropEvent` ветка каталога встаёт **первой**, до чтения `currentIndex()`:
у чужого перетаскивания текущей строки этого дерева нет вовсе, и порядок
здесь несущий, а не косметический.

```python
    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        directory = dropped_directory(event.mimeData())
        if directory is not None:
            index = self.indexAt(event.position().toPoint())
            self._view.add_infobase_from_directory(
                directory, self._row_key(index), self._row_kind(index)
            )
            event.acceptProposedAction()
            return
        source_key = self._row_key(self.currentIndex())
        # ...существующее тело без изменений...
```

Импорты `view.py`: к `QDragMoveEvent` добавить `QDragEnterEvent`; строку
`from onecstarter.ui.dialogs.infobase import InfobaseDialog` дополнить
до `import InfobaseDialog, dropped_directory`.

Run: та же команда

Expected: PASS

**Находка исполнения задачи 20 (пробел мутационной проверки шага 10,
закрыт добавлением теста здесь же):** `test_tree_drop_of_a_directory_
opens_the_add_dialog` (шаг 7) не отличает правильный порядок веток
`dropEvent` от переставленного — в свежепостроенном дереве
`self.currentIndex()` невалиден и `source_key` пуст независимо от того,
до или после проверки каталога стоит его чтение, и переставленный вариант
всё равно доходит до `add_infobase_from_directory` с тем же результатом.
Настоящий риск, ради которого порядок и назван «несущим» в докстринге
шага, — строка, оставшаяся текущей в дереве от предыдущего клика
пользователя и не связанная с текущим чужим перетаскиванием: без
правильного порядка такой drop прочитался бы ЕЩЁ и как internal-move той
старой строки. Добавлен тест, выставляющий `currentIndex` на реальную
запись перед броском каталога и проверяющий, что `handle_drop` не
вызывается вовсе:

```python
def test_tree_drop_of_a_directory_ignores_a_stale_current_row(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Ветка каталога проверяется ДО чтения currentIndex() — порядок несущий.

    Находка мутационной проверки шага 10: `test_tree_drop_of_a_directory_
    opens_the_add_dialog` не задевает эту перестановку, потому что в свежем
    дереве `currentIndex()` невалиден и `source_key` пуст независимо от
    порядка. Реальный риск — строка, оставшаяся текущей от предыдущего клика
    пользователя (никак не связанного с этим перетаскиванием из Проводника):
    у чужого перетаскивания «текущей строки этого дерева» нет по смыслу, и
    если бы ветка каталога стояла после чтения `currentIndex()`, чужой drop
    прочитался бы ещё и как internal-move той старой строки — `handle_drop`
    получил бы вызов, которого быть не должно.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    stale = next(i for i in view.workspace().items() if not i.is_group)
    _select_key(view, stale.key)
    rect = _visible_rect_of_kind(view, RowKind.GROUP)
    index = tree.indexAt(rect.center())
    add_calls: list[tuple[object, ...]] = []
    drop_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: add_calls.append(args)
    )
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: drop_calls.append(args)
    )
    mime = _directory_mime(tmp_path)

    tree.dropEvent(_drop_event(rect.center(), mime))

    assert add_calls == [(str(tmp_path), index.data(KEY_ROLE), RowKind.GROUP.value)]
    assert drop_calls == []
```

Подтверждено экспериментом: на исправленном (правильно упорядоченном) коде
тест зелёный; на мутации 4 (см. таблицу шага 10) — падает на
`assert drop_calls == []`, а `test_tree_drop_of_a_directory_opens_the_add_
dialog` при той же мутации остаётся зелёным. Коммит теста — `a7c05ae`,
отдельно от коммита реализации (`f0bba96`): находка сделана уже во время
мутационной проверки шага 10, после основного коммита.

- [x] **Step 9: Приём вне дерева и запрет полю поиска**

Дерево занимает большую часть раздела, но не весь: остаются панель пути, поле
поиска и поля вокруг. Без этого шага бросок на панель даст ровно то же
«не работает», с которого задача началась.

```python
def test_search_field_does_not_accept_drops(qtbot: Any, workspace_factory: Any) -> None:
    """Иначе QLineEdit вставит путь каталога текстом в строку поиска."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)

    accepts = view._search.acceptDrops()

    assert accepts is False


def test_view_drop_outside_the_tree_adds_to_root(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: calls.append(args)
    )
    # Ссылка держится в переменной до вызова dropEvent — та же причина,
    # что и у _directory_mime(plain) в шаге 7 (см. находку ниже).
    mime = _directory_mime(tmp_path)

    view.dropEvent(_drop_event(QPoint(0, 0), mime))

    assert calls == [(str(tmp_path),)]
```

**Находка исполнения задачи 20 (время жизни `QMimeData`, дефект этого шага
и шага 7, исправлено в текстах кода тестов выше):** оба теста в исходном
тексте плана вызывали `_drop_event(pos, _directory_mime(x))`, передавая
только что созданный `QMimeData` сразу как аргумент вызова, без сохранения
ссылки на него в переменной теста. `_drop_event` (в отличие от
`_drag_move_event`, которая существовала до задачи 20 и уже возвращает
`(event, mime)` парой ровно по этой причине — см. её докстринг про мину
09.08.2026) отдаёт только `QDropEvent`, не сам `QMimeData`. Как только
вызов `_drop_event(...)` завершается, временный `QMimeData`, созданный
внутри аргумента, не удержан больше никем со стороны Python, и сборщик
мусора вправе забрать его в любой момент — включая момент ДО того, как
`_BasesTree.dropEvent`/`BasesView.dropEvent` успеют прочитать
`event.mimeData()` (эта задача — первая, где обработчики `dropEvent` вообще
читают mime-данные события; до неё эта мина ни разу не срабатывала во всех
тестах задач 14/15, потому что `dropEvent` смотрел только на `currentIndex()`
и роли модели). На боевой машине (PySide6 6.11.1, Windows) воспроизведено
как `AttributeError: 'PySide6.QtCore.QObject' object has no attribute
'urls'` внутри `dropped_directory` — Shiboken реинтерпретирует висячий
указатель как базовый `QObject`. Хуже того: эта же мина сработала и на
всех ДЕСЯТИ уже существующих тестах задач 14/15, использующих
`_drop_event(pos)` без явного `mime=` (там аргумент по умолчанию тоже
создавал временный `QMimeData()` внутри тела функции) — раньше это было
безопасно, потому что `dropEvent` эти данные не читал, но с задачей 20 стало
не так. Исправление на уровне хелпера, а не только вызовов: модульная
константа `_EMPTY_MIME = QMimeData()` в `tests/ui/test_bases_view.py`
(переживает весь прогон, не зависит от того, держит ли конкретный тест
собственную ссылку) стала значением по умолчанию в `_drop_event`, а два
вызова с брошенным каталогом выше держат `mime` в переменной до вызова —
тем же приёмом, что уже применялся для `_drag_move_event`.

Реализация — в `BasesView.__init__` после сборки виджетов:

```python
        self.setAcceptDrops(True)
        # QLineEdit принимает перетаскивание сам и вставил бы путь каталога
        # текстом в строку поиска — бессмысленный результат вместо добавления.
        self._search.setAcceptDrops(False)
```

и три метода `BasesView`; группа здесь всегда корень — позиция вне дерева
ни на какую строку не указывает:

```python
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        directory = dropped_directory(event.mimeData())
        if directory is None:
            return
        self.add_infobase_from_directory(directory)
        event.acceptProposedAction()
```

- [x] **Step 10: Прогон, коммит, мутационная проверка**

Проверять **по кодам выхода команд, а не по хвосту вывода**: `ruff check . | tail -1`
возвращает код `tail`, и цепочка через `&&` на ненулевом коде не остановится —
поймано 09.08.2026, коммит с двумя замечаниями ruff успел уйти.

```bash
uv run ruff check .; echo "ruff=$?"
uv run mypy;          echo "mypy=$?"
uv run pytest -q;     echo "pytest=$?"
git add src/onecstarter tests/ui
git commit -m "feat: каталог, брошенный в раздел «Базы», открывает диалог добавления"
```

**Мутационная проверка обязательна** — тесты защитные. Порядок: правка → зелёные
тесты → коммит → мутация → откат. Откат `git checkout --` до коммита снёс бы
и саму правку (ловушка 07.08.2026).

| Мутация | Ожидание |
| --- | --- |
| убрать `self._search.setAcceptDrops(False)` | падает `test_search_field_does_not_accept_drops` |
| в `folder_for_dropped_directory` убрать проверку членства в `_group_paths()` | падает `..._rejects_a_dangling_folder` |
| в `folder_for_dropped_directory` вернуть `INTO` для `RowKind.BASE` | падает `..._uses_the_parent_of_a_base` |
| в `dropEvent` дерева поставить ветку каталога **после** чтения `currentIndex()` | падает `test_tree_drop_of_a_directory_ignores_a_stale_current_row` (не `..._opens_the_add_dialog` — см. находку шага 8) |
| в `dropped_directory` вернуть `str(path)` без проверки `path.is_dir()` | падает `test_tree_drop_of_a_file_is_not_taken_for_a_directory` |

Факт: подтверждено, все пять мутаций, после коммита `f0bba96`. Мутации 1, 2,
3, 5 упали именно на названных в плане тестах, с ожидаемым сообщением
(`AssertionError` на несовпадении значения). Мутация 4 — находка: тест,
названный в исходной таблице (`test_tree_drop_of_a_directory_opens_the_
add_dialog`), НЕ падает при перестановке ветки каталога после чтения
`currentIndex()` — ни в узкой форме (переставить только чтение), ни
в полной (перенести весь блок каталога в конец метода): дерево в этом тесте
свежепостроено, `currentIndex()` невалиден, `source_key` пуст независимо
от порядка, и мутированный код всё равно вызывает `add_infobase_from_
directory` с тем же результатом — проверено прогоном всех 122 тестов
`test_bases_view.py` под мутацией, ни один не падает. Добавлен и
подтверждён отдельный тест `test_tree_drop_of_a_directory_ignores_a_stale_
current_row` (шаг 8, коммит `a7c05ae`) — он выставляет `currentIndex` на
реальную запись до броска и проверяет отсутствие вызова `handle_drop`;
падает на мутации 4 с `AssertionError: assert [(...)] == []`. Таблица и
раздел шага 8 исправлены на этот тест. После каждой мутации — откат
`git checkout --`; полный `uv run pytest -q` неизменно возвращался к
зелёному состоянию (866/866 после коммита `a7c05ae`, 123/123 в
`test_bases_view.py`), `ruff check .` и `uv run mypy` — чистые.

---

### Task 19: финальная верификация плана

**Files:** правки по итогам — в файлы, где найдены расхождения.

- [x] **Step 1: Полный прогон**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Записать число тестов.

**Проверять по кодам выхода каждой команды, а не по хвосту вывода.**
`uv run ruff check . | tail -1` возвращает код `tail`, и цепочка через `&&`
на ненулевом коде не останавливается — 09.08.2026 так ушёл коммит с двумя
незамеченными замечаниями.

Факт: 10.08.2026 — **1000 тестов**, `ruff` код 0, `mypy` код 0 (111 файлов).
На входе в план было 447, на входе в сессию 09.08 — 825.

- [x] **Step 2: Инварианты `CLAUDE.md`**

```bash
uv run pytest tests/unit/test_no_qt_in_core.py -v
```

Проверить глазами: нет ли в новых модулях `services`/`domain`/`config`
импортов PySide6; нет ли секретов в новых сообщениях; все ли записи в файлы
пользователя идут через `write_patch` или `atomic_write`.

Факт: 10.08.2026 — `test_no_qt_in_core.py` зелёный; прямых импортов `PySide6`
вне `ui/` нет (единственное упоминание — фраза в докстринге `__main__.py`,
сам импорт ленивый внутри `main`); выбор версии к ФС и процессам не
обращается; своих `open(..., "w")` по пользовательским путям нет, кроме
самого атомарного писателя; знание о секретах живёт в `security/secrets.py`.

- [x] **Step 3: Сверка плана со спекой и обеих — с кодом**

Пройти §11 спеки (таблица обязательств) и убедиться, что каждая строка
закрыта задачей. Расхождения править **в обоих документах**: правило
`CLAUDE.md` — документ, разошедшийся с кодом, врёт следующему исполнителю.

Известные правки, которые обязаны попасть в спеку по итогам:
`[Д]`→`[Ф]` для `QStyleHints.colorScheme` (задача 3, шаг 7); результат
T-05.13 (задача 16); ограничение `BEFORE`/`AFTER` между группами
(задача 14) — в §12 спеки.

Факт: 10.08.2026 — таблица §11 спеки пройдена построчно, каждое обязательство
сверено **с кодом**, а не с памятью. Из пятнадцати закрыто тринадцать; два
(`Shift+F3`/`Shift+F4` и `/WA+`) перенесены в v2 вместе со снятой задачей 16
и помечены в §11. Расхождения спеки с кодом, найденные финальным ревью (M15:
`make_icon(palette)` в §2.1, несуществующий вызов в §9), исправлены **в спеке**,
код не подгонялся.

- [x] **Step 4: Отчёт по мутационным проверкам**

Собрать в одном месте: сколько мутаций проведено, сколько валят адресный тест,
какие не валят и почему это приемлемо. Отчёт — в этот шаг.

Факт: 10.08.2026. Мутационные проверки прошли **все двадцать задач** плана;
в тексте плана 32 блока «Мутационная проверка». Считаны только те, где
зафиксирован факт срабатывания.

За сессию 09–10.08.2026 отдельно:

| Круг | Мутаций | Поймано | Не поймано |
| --- | --- | --- | --- |
| контраст палитры (круг правок 3 задачи 1) | 3 | 3 | — |
| `OrderInList` — неподвижная точка | 3 | 3 | — |
| немой отказ drop (круг правок 4 задачи 14) | 4 | 4 | — |
| задача 20 | 5 | 4 | 1 → закрыта новым тестом |
| задача 17 и два круга правок | 15 | 15 | — |
| задача 18 | 1 | 1 | — |
| ре-ревью финальной волны (независимые) | 33 | 30 | 3 |
| ре-ревью закрывающей волны (независимые) | 4 | 4 | — |

**Не пойманное разобрано, а не списано.** Из трёх выживших в ре-ревью финальной
волны две оказались настоящими дырами (N1 и N2 — сторожа сборки приложения,
зелёные на пустышке) и закрыты закрывающей волной. Третья —
`finally: self._rebuild()` на пути отказа `launch` — **непойма́ема по построению**:
после отката `self._user` состояние тождественно исходному, и `_rebuild()`
на пути отказа ничего не меняет. Записано как таковое, а не выдано за успех.

Главный урок круга: мутацию ставит **не тот**, кто писал тест. Автор теста
и его тест — не независимые свидетели. Все находки N1, N2 и пробел мутации 4
задачи 20 пришли от независимых мутаций ревьюеров.

- [ ] **Step 5: Запуск приложения**

Run: `uv run python -m onecstarter`
Убедиться, что окно поднимается, разделы переключаются, тема меняется.

- [x] **Step 6: Ревью всей ветки на самой сильной модели**

Диапазон — от точки ответвления до HEAD. Находки разносятся по задачам;
если ревью нашло дефект в коде, который план предписывал дословно, — ошибка
в плане, и правятся оба (`CLAUDE.md`).

Факт: 09–10.08.2026, проведено на самой сильной модели по диапазону
`ae4a8e0..975de3b` (104 коммита, 66 файлов). Сломанного кода не найдено;
найдено, что **набор тестов местами зелен на сломанной реализации** — 1 Critical
и 10 Important, каждое доказано мутацией. Разбор — в разделе «Круг правок
финального ревью ветки» ниже. Закрыто двумя волнами (`49ea32a..975de3b`
и `975de3b..edb85e7`), обе прошли точечное ре-ревью с независимыми мутациями.
Долг, вынесенный за пределы волн, записан в `docs/tasks.md`.

- [x] **Step 7: Слияние**

Линейной историей (`--ff-only`), как 4a. Перед слиянием — `superpowers:finishing-a-development-branch`.

Факт: 10.08.2026 — слито `--ff-only`, `master` `ae4a8e0` → `483c371`,
116 коммитов, merge-коммитов нет (история линейная). Прогон на слитом
результате: 1000 тестов, `ruff` и `mypy` коды 0.


## Круг правок финального ревью ветки (09.08.2026, шаг 6 задачи 19)

Ревью на самой сильной модели **сломанного кода не нашло**. Оно нашло другое:
набор тестов местами зелен на сломанной реализации, и доказало это мутациями,
а не рассуждением. Правило `CLAUDE.md` («тест, зелёный на пустышке, хуже
отсутствующего») делает это дефектом плана в той же мере, что и дефектом кода:
шаги, предписывавшие такие проверки, формулировали их через доступный результат,
а не через проверяемое утверждение.

Заказчик 09.08.2026 решил: чинить всё — Critical и все десять Important; **отказ
показывается раньше, до действия**, а не сообщением после (где пользователь
не может выполнить операцию — элемент неактивен и объясняет почему).

| # | Находка | Как закрыта |
| --- | --- | --- |
| C1 | Сторожа «нетронутый диалог не пишет в файл» сравнивали байты файла; `writer` сам не пишет патч, не меняющий байтов, поэтому замена обеих проверок на `pass` проходила | сторожа смотрят на факт вызова `update_infobase`/`update_group` (спай на методе экземпляра), байты — вторым утверждением; добавлена обратная пара тестов |
| I2 | `if dialog.exec() == Accepted:` не покрыт нигде — `show_properties`, `add_group`, `rename_group`, `add_infobase_from_directory` можно было сделать мёртвыми | тесты на обе ветки каждого метода; тело `add_infobase_from_directory` теперь исполняется по-настоящему |
| I3 | Сборка приложения не исполнялась ни разу; проводка трея проверялась на своей копии; требуемого спекой §9 теста `make_icon()` не существовало | `ui/app.py:main` вызывается целиком (подменяется только недопустимое в тесте), `create_tray` и `__main__.main` покрыты, тест байтов значка трея написан |
| I4 | `placement_icon` не связана с `_colour_for` ни одной проверкой — `UNKNOWN` мог потерять цвет проблемы | пиксели готового значка в обеих палитрах |
| I5 | `.lnk` без `TerminalBlock` проходил все 42 теста, включая живой `IShellLink` | проверка последних четырёх байт |
| I6 | Маскировка секретов доказывалась на чистой функции; путь значения на экран (`QTableWidgetItem`) не покрыт | `other_rows()` читает виджет; отдельный сторож читает ячейки напрямую |
| I7 | Меню записи из общего списка предлагало то, что всегда откажет | правило «решение принимается один раз, до показа меню» (круг правок 1 задачи 12) распространено на записи; спека §3.2 |
| I8 | Диалог добавления принимал пустое размещение — `File="";` уходил в общий файл | «ОК» неактивна с пояснением; **правило дописано в спеку §3.1** — там его не было вовсе |
| I9 | `OSError` записи `bases.json` шла мимо всех ловцов; `Ctrl+D` и запуск молчали | `UserDataWriteError` + `Workspace._store_user` с откатом состояния; тесты на все три пути |
| I10 | Бросок на строку «Общих списков» — молчание без курсора «нельзя» | `_rejects_drop_at` отвергает любую цель, которую не разрешает `_target_of_drop`; **спека §14 п. 5 расширена**; тест, закреплявший немое поведение, приведён к новому |
| I11 | `test_save_reports_failure` до `atomic_write` не доходил (падал на `mkdir` родителя) | препятствием стал сам целевой путь при живом родителе |
| M15 | Спека расходилась с кодом в двух местах | §2.1 (`make_icon(palette)`) и §9 (мутация «убрать `view.rebuild()` из контроллера») исправлены в документе |

**Мутационная проверка проведена по каждому починенному сторожу** (порядок:
правка → зелёные тесты → коммит → мутация → `git checkout -- <файл>` →
повторный прогон). Полный протокол с диагностикой каждого падения —
в отчёте `.superpowers/sdd/2026-08-08-v1-plan4b-ui-edit/final-fixes-report.md`.

**Отдельная находка процесса, не входившая в замечания.** Тест сборки
приложения в первой редакции ставил настоящую таблицу стилей на общий
`QApplication`. Применение её поверх дерева виджетов, которое тут же
уничтожается, оставляло в кэшах Qt следы, и СЛЕДУЮЩИЙ чужой `setStyleSheet`
падал access violation примерно на половине прогонов — падал процесс, не тест,
поэтому обычный зелёный прогон этого не показывал. Найдено бисекцией по файлам
и стресс-прогоном (8 повторов); таблица стилей в этом тесте теперь записывается,
а не ставится. Урок общий: тест, который трогает состояние **приложения**,
а не только своих виджетов, обязан проверяться повторными прогонами всего
набора, а не одним.
