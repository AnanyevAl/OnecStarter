# v3.1 — замечания по проверке v3: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть шесть замечаний заказчика по v3 (пути-ссылки в панелях, «Рабочая область», колонка «Память», крестик и Ctrl+F в поиске, группа «О программе») и выпустить 3.1.0.

**Architecture:** один новый виджет `ui/path_link.py::PathLink` (QLabel с rich-text ссылкой и контекстным меню) заменяет поле + кнопки в обеих панелях; чистая функция `domain/edt.py::effective_heap_mb` кормит третью колонку дерева EDT; `ui/search_field.py::SearchField` — QLineEdit с действием очистки и подсказкой Ctrl+F; одна комбинация Ctrl+F в оболочке; группа настроек «О ПРОГРАММЕ» с версией из метаданных пакета, гейт `smoke: version=`.

**Tech Stack:** Python 3.13, PySide6 6.11, pytest-qt (offscreen), PyInstaller (`copy_metadata`), Inno Setup.

Спека — [2026-09-15-v31-review-fixes-design.md](../specs/2026-09-15-v31-review-fixes-design.md).
Базовая точка — `master@6b804c4`. Ветка — `feat/2026-09-15-v31` в рабочем каталоге
(как у v3, решение заказчика).

## Global Constraints

- Qt только в `src/onecstarter/ui/`; `domain` — чистые функции без ФС и процессов (CLAUDE.md, инвариант 1–2).
- `uv run ruff check .` чист; `uv run mypy` strict вне `onecstarter.ui.*`; строки ≤ 100 символов; кириллица в комментариях/докстрингах — `# noqa: RUF001/RUF002/RUF003` по образцу соседнего кода.
- Тексты интерфейса — дословно из спеки: «Рабочая область», «Каталог проекта», меню «Открыть каталог» / «Копировать», placeholder «не задан — редакторы получают рабочую область», подсказки поиска «Поиск: начните вводить имя базы (Ctrl+F)» и «Поиск: начните вводить имя проекта (Ctrl+F)», группа «О ПРОГРАММЕ», строки «Версия», «Репозиторий», ссылка `https://github.com/AnanyevAl/OnecStarter`.
- Колонка «Память»: `f"{mb} МБ"`, иначе «—» с подсказкой «-Xmx не задан — действует значение из 1cedt.ini установки»; цепочка запись → установка, настройка «память по умолчанию» в цепочку не входит (спека §5).
- Идентификаторы и ключи `edt.json` не переименовываются — только видимые строки (спека §4).
- Тест на отказ операции обязан падать на сломанной реализации (CLAUDE.md, мутационная проверка); табличные тесты чистых функций — без неё.
- Полные прогоны pytest — в файл: `uv run pytest -q > e:/tmp/<имя>.log 2>&1; tail -3 …`.
- Коммиты по-русски, без атрибуции.

---

### Task 1: Виджет `PathLink`

**Files:**
- Create: `src/onecstarter/ui/path_link.py`
- Modify: `src/onecstarter/ui/theme.py` (правило `#PathLink` рядом с `#ConnectionPath`)
- Test: `tests/ui/test_path_link.py`

**Interfaces:**
- Produces: `PathLink(QLabel)` — `__init__(*, palette: Palette, copy_text: Callable[[str], None] = copy_to_clipboard, parent=None)`; сигнал `open_requested = Signal(str)`; методы `set_placeholder(text: str)`, `set_path(text: str, *, directory: str | None = None)`, `apply_palette(palette)`, `path_text() -> str`, `elided_text() -> str`, `placeholder() -> str`, `link_href() -> str | None`, `context_menu() -> QMenu`; константы `MENU_OPEN = "Открыть каталог"`, `MENU_COPY = "Копировать"`; функция `copy_to_clipboard(text)`.

- [ ] **Step 1: Тесты**

`tests/ui/test_path_link.py`:

```python
"""Путь-ссылка панелей (спека v3.1, §2): ссылка, меню, обрезание, placeholder."""

from typing import Any

from PySide6.QtWidgets import QApplication

from onecstarter.ui import theme
from onecstarter.ui.path_link import MENU_COPY, MENU_OPEN, PathLink

LONG = r"D:\very\long\path\to\the\workspace\of\a\really\big\configuration\with\many\parts"


def _link(copied: list[str]) -> PathLink:
    return PathLink(palette=theme.DARK, copy_text=copied.append)


def test_directory_renders_as_link_and_click_requests_open(qtbot: Any) -> None:
    opened: list[str] = []
    link = _link([])
    qtbot.addWidget(link)
    link.open_requested.connect(opened.append)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")
    assert link.link_href() == r"D:\edt\ws"
    assert theme.DARK.accent in link.text()  # цвет акцента — в разметке ссылки
    link.linkActivated.emit(link.text())  # клик по ссылке штатно даёт linkActivated
    assert opened == [r"D:\edt\ws"]


def test_text_without_directory_is_not_a_link(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path('Srvr="srv";Ref="acc"')
    assert link.link_href() is None
    assert "<a " not in link.text()
    assert link.path_text() == 'Srvr="srv";Ref="acc"'


def test_menu_items_follow_state(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")
    assert [a.text() for a in link.context_menu().actions()] == [MENU_OPEN, MENU_COPY]
    link.set_path("текст без каталога")
    assert [a.text() for a in link.context_menu().actions()] == [MENU_COPY]
    link.set_path("")
    assert link.context_menu().actions() == []


def test_copy_puts_full_text_not_elided(qtbot: Any) -> None:
    copied: list[str] = []
    link = _link(copied)
    qtbot.addWidget(link)
    link.show()
    link.resize(120, 20)
    link.set_path(LONG, directory=LONG)
    assert "…" in link.elided_text() and link.elided_text() != LONG
    assert link.toolTip() == LONG
    [_open, copy] = link.context_menu().actions()
    copy.trigger()
    assert copied == [LONG]


def test_menu_open_triggers_open_requested(qtbot: Any) -> None:
    opened: list[str] = []
    link = _link([])
    qtbot.addWidget(link)
    link.open_requested.connect(opened.append)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")
    link.context_menu().actions()[0].trigger()
    assert opened == [r"D:\edt\ws"]


def test_placeholder_when_empty(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_placeholder("не задан")
    link.set_path("")
    assert link.placeholder() == "не задан"
    assert link.path_text() == ""
    assert "<i" in link.text() and theme.DARK.text_dim in link.text()
    assert link.toolTip() == ""


def test_html_in_path_is_escaped(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\R&D\<ws>", directory=r"D:\R&D\<ws>")
    assert "&amp;" in link.text() and "&lt;ws&gt;" in link.text()
    assert link.path_text() == r"D:\R&D\<ws>"


def test_apply_palette_recolours(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\a", directory=r"D:\a")
    link.apply_palette(theme.LIGHT)
    assert theme.LIGHT.accent in link.text()


def test_default_copy_uses_clipboard(qtbot: Any) -> None:
    link = PathLink(palette=theme.DARK)
    qtbot.addWidget(link)
    link.set_path(r"D:\a")
    link.context_menu().actions()[0].trigger()
    assert QApplication.clipboard().text() == r"D:\a"
```

- [ ] **Step 2: Прогон — падает на импорте**

Run: `uv run pytest -q tests/ui/test_path_link.py`
Expected: `ModuleNotFoundError: onecstarter.ui.path_link`

- [ ] **Step 3: Реализация**

`src/onecstarter/ui/path_link.py`:

```python
"""Путь-ссылка панелей (спека v3.1, §2).

`QLabel` с rich-text: текст пути — ссылка цветом акцента (клик и Enter —
`open_requested`), без каталога — обычный текст; ПКМ — меню «Открыть каталог» /
«Копировать». Длинный путь обрезается многоточием посередине по ширине виджета,
полный текст — во всплывающей подсказке; «Копировать» кладёт полный текст.
Замена read-only `QLineEdit` + двух кнопок (замечание 1 заказчика по v3).
"""  # noqa: RUF002

import html
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QResizeEvent
from PySide6.QtWidgets import QLabel, QMenu, QSizePolicy, QWidget

from onecstarter.ui.theme import Palette

MENU_OPEN = "Открыть каталог"
MENU_COPY = "Копировать"
_MIN_TEXT_WIDTH = 40


def copy_to_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


class PathLink(QLabel):
    open_requested = Signal(str)

    def __init__(
        self,
        *,
        palette: Palette,
        copy_text: Callable[[str], None] = copy_to_clipboard,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._copy_text = copy_text
        self._text = ""
        self._shown = ""
        self._directory: str | None = None
        self._placeholder = ""
        self.setObjectName("PathLink")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        # Ширину диктует раскладка, а не длина пути: иначе длинный путь
        # растягивал бы панель и окно вместо того, чтобы обрезаться.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        # Открываем свой `_directory`, а не href из разметки: href прошёл
        # через html.escape и обратно, каталог — первоисточник.
        self.linkActivated.connect(lambda _href: self._request_open())
        self._render()

    # --- состояние -------------------------------------------------------

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self._render()

    def set_path(self, text: str, *, directory: str | None = None) -> None:
        self._text = text
        self._directory = directory if text else None
        self._render()

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._render()

    # --- доступ ----------------------------------------------------------

    def path_text(self) -> str:
        return self._text

    def elided_text(self) -> str:
        return self._shown

    def placeholder(self) -> str:
        return self._placeholder

    def link_href(self) -> str | None:
        return self._directory if self._text else None

    def context_menu(self) -> QMenu:
        menu = QMenu(self)
        if self._directory is not None:
            menu.addAction(MENU_OPEN, self._request_open)
        if self._text:
            menu.addAction(MENU_COPY, lambda: self._copy_text(self._text))
        return menu

    # --- внутреннее ------------------------------------------------------

    def _request_open(self) -> None:
        if self._directory is not None:
            self.open_requested.emit(self._directory)

    def _show_menu(self, pos: QPoint) -> None:
        menu = self.context_menu()
        if menu.actions():
            menu.exec(self.mapToGlobal(pos))

    def _render(self) -> None:
        if not self._text:
            self._shown = ""
            self.setToolTip("")
            self.setText(
                f'<i style="color:{self._palette.text_dim}">{html.escape(self._placeholder)}</i>'
            )
            return
        width = max(self.width() - 4, _MIN_TEXT_WIDTH)
        self._shown = self.fontMetrics().elidedText(
            self._text, Qt.TextElideMode.ElideMiddle, width
        )
        self.setToolTip(self._text)
        shown = html.escape(self._shown)
        if self._directory is not None:
            href = html.escape(self._directory, quote=True)
            self.setText(f'<a href="{href}" style="color:{self._palette.accent}">{shown}</a>')
        else:
            self.setText(f'<span style="color:{self._palette.text}">{shown}</span>')

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render()
```

`src/onecstarter/ui/theme.py` — после правила `#ConnectionPath {{ … }}` добавить:

```python
#PathLink {{
    font-family: Consolas, "Cascadia Mono", monospace;
    background: transparent; padding: 0;
}}
```

(цвета — не из QSS, а из разметки: QSS `color` не красит `<a>` внутри QLabel).

- [ ] **Step 4: Прогон**

Run: `uv run pytest -q tests/ui/test_path_link.py tests/ui/test_theme.py`
Expected: все PASS. Если `test_copy_puts_full_text_not_elided` не видит `…` — виджет не получил
`resizeEvent` до `set_path`; проверить, что тест зовёт `show()` до `resize()`.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/ui/path_link.py src/onecstarter/ui/theme.py tests/ui/test_path_link.py
git commit -m "feat(ui): PathLink — путь-ссылка с контекстным меню (v3.1, §2)"
```

---

### Task 2: Панель EDT на `PathLink`, «Рабочая область»

**Files:**
- Modify: `src/onecstarter/ui/edt/panel.py` (весь), `src/onecstarter/ui/theme.py:143-148` (правила `#EdtPanel QPushButton` удалить)
- Test: `tests/ui/test_edt_panel.py` (переписать), `tests/ui/test_edt_view.py:296-323`

**Interfaces:**
- Consumes: `PathLink`, `MENU_COPY`, `MENU_OPEN` (Task 1).
- Produces: `EdtPanel.workspace_link() -> PathLink`, `EdtPanel.project_dir_link() -> PathLink`; конструктор `EdtPanel(*, open_directory=open_in_explorer, copy_text=copy_to_clipboard, palette: Palette = DARK, parent=None)`; `show_project(project, palette)`, `show_group(name)`, `show_nothing()`, `title_text()` и сигнал `open_failed(str)` — без изменений; константы `CAPTION_WORKSPACE = "Рабочая область"`, `CAPTION_PROJECT_DIR = "Каталог проекта"`, `PLACEHOLDER_NO_PROJECT_DIR = "не задан — редакторы получают рабочую область"`.

- [ ] **Step 1: Тесты панели**

`tests/ui/test_edt_panel.py` целиком:

```python
"""Панель путей под деревом раздела «EDT»: пути-ссылки (спека v3.1, §3)."""

from onecstarter.domain.edt import EdtProject
from onecstarter.ui import theme
from onecstarter.ui.edt.panel import (
    CAPTION_PROJECT_DIR,
    CAPTION_WORKSPACE,
    PLACEHOLDER_NO_PROJECT_DIR,
    PLACEHOLDER_NONE,
    EdtPanel,
)
from onecstarter.ui.path_link import MENU_COPY, MENU_OPEN


def _panel(opened: list[str], copied: list[str], ok: bool = True) -> EdtPanel:
    def open_directory(path: str) -> bool:
        opened.append(path)
        return ok

    return EdtPanel(open_directory=open_directory, copy_text=copied.append)


def test_empty_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    assert panel.title_text() == PLACEHOLDER_NONE
    assert panel.workspace_link().isHidden() is True
    assert panel.project_dir_link().isHidden() is True


def test_captions_say_workspace_in_russian(qtbot) -> None:  # type: ignore[no-untyped-def]
    assert CAPTION_WORKSPACE == "Рабочая область"
    assert CAPTION_PROJECT_DIR == "Каталог проекта"
    assert PLACEHOLDER_NO_PROJECT_DIR == "не задан — редакторы получают рабочую область"


def test_project_with_both_paths_as_links(qtbot) -> None:  # type: ignore[no-untyped-def]
    opened: list[str] = []
    copied: list[str] = []
    panel = _panel(opened, copied)
    qtbot.addWidget(panel)
    panel.show_project(
        EdtProject("p", "Розница", r"D:\edt\retail", project_dir=r"D:\git\retail"), theme.DARK
    )
    assert panel.title_text() == "Розница"
    assert panel.workspace_link().path_text() == r"D:\edt\retail"
    assert panel.workspace_link().link_href() == r"D:\edt\retail"
    assert panel.project_dir_link().link_href() == r"D:\git\retail"
    assert panel.workspace_link().isHidden() is False
    panel.workspace_link().linkActivated.emit("")
    [_open, copy] = panel.project_dir_link().context_menu().actions()
    assert [_open.text(), copy.text()] == [MENU_OPEN, MENU_COPY]
    copy.trigger()
    assert opened == [r"D:\edt\retail"]
    assert copied == [r"D:\git\retail"]


def test_project_without_project_dir(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "Опт", r"D:\edt\w"), theme.DARK)
    assert panel.project_dir_link().path_text() == ""
    assert panel.project_dir_link().placeholder() == PLACEHOLDER_NO_PROJECT_DIR
    assert panel.project_dir_link().link_href() is None
    assert panel.project_dir_link().context_menu().actions() == []


def test_group_shows_only_title(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_group("2025")
    assert panel.title_text() == "2025"
    assert panel.workspace_link().isHidden() is True


def test_open_failure_reported(qtbot) -> None:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    panel = EdtPanel(open_directory=lambda p: False, copy_text=lambda t: None)
    panel.open_failed.connect(errors.append)
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "a", r"D:\gone"), theme.DARK)
    panel.workspace_link().linkActivated.emit("")
    assert errors == [r"Каталог не найден: D:\gone"]


def test_palette_reaches_links(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "a", r"D:\w"), theme.LIGHT)
    assert theme.LIGHT.accent in panel.workspace_link().text()
```

`tests/ui/test_edt_view.py` — в трёх тестах панели заменить аксессоры:
`workspace_field().text()` → `workspace_link().path_text()`, `project_dir_field().text()` →
`project_dir_link().path_text()`, `workspace_field().isHidden()` → `workspace_link().isHidden()`,
`workspace_open_button().click()` → `workspace_link().linkActivated.emit("")`.

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest -q tests/ui/test_edt_panel.py`
Expected: `ImportError: cannot import name 'CAPTION_WORKSPACE'`

- [ ] **Step 3: Реализация**

`src/onecstarter/ui/edt/panel.py` целиком:

```python
"""Панель путей под деревом раздела «EDT» (решение заказчика 11.09.2026; v3.1 §3).

Заголовок жирным, два пути — `PathLink` (ссылка открывает каталог, ПКМ — меню
«Открыть каталог»/«Копировать»). Ряд кнопок снят по замечанию 1 заказчика.
Версии здесь нет — она видна в списке.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from onecstarter.domain.edt import EdtProject
from onecstarter.ui.bases.panel import open_in_explorer
from onecstarter.ui.path_link import PathLink, copy_to_clipboard
from onecstarter.ui.theme import DARK, Palette

PLACEHOLDER_NONE = "Выберите проект"
PLACEHOLDER_NO_PROJECT_DIR = "не задан — редакторы получают рабочую область"
CAPTION_WORKSPACE = "Рабочая область"
CAPTION_PROJECT_DIR = "Каталог проекта"


class EdtPanel(QWidget):
    open_failed = Signal(str)

    def __init__(
        self,
        *,
        open_directory: Callable[[str], bool] = open_in_explorer,
        copy_text: Callable[[str], None] = copy_to_clipboard,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EdtPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._open_directory = open_directory
        self._title = QLabel(PLACEHOLDER_NONE)
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        self._captions = (QLabel(CAPTION_WORKSPACE), QLabel(CAPTION_PROJECT_DIR))
        self._workspace = PathLink(palette=palette, copy_text=copy_text)
        self._project_dir = PathLink(palette=palette, copy_text=copy_text)
        self._project_dir.set_placeholder(PLACEHOLDER_NO_PROJECT_DIR)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        for row, (caption, link) in enumerate(
            zip(self._captions, (self._workspace, self._project_dir), strict=True)
        ):
            caption.setObjectName("PanelKindWord")
            link.open_requested.connect(self._open)
            grid.addWidget(caption, row, 0)
            grid.addWidget(link, row, 1)
        grid.setColumnStretch(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        layout.addWidget(self._title)
        layout.addLayout(grid)
        self.show_nothing()

    def show_project(self, project: EdtProject, palette: Palette) -> None:
        self._title.setText(project.name)
        for link in (self._workspace, self._project_dir):
            link.apply_palette(palette)
        self._workspace.set_path(project.workspace, directory=project.workspace)
        self._project_dir.set_path(project.project_dir, directory=project.project_dir or None)
        self._set_rows_visible(True)

    def show_group(self, name: str) -> None:
        self._title.setText(name)
        self._set_rows_visible(False)

    def show_nothing(self) -> None:
        self._title.setText(PLACEHOLDER_NONE)
        self._set_rows_visible(False)

    def _set_rows_visible(self, visible: bool) -> None:
        for widget in (*self._captions, self._workspace, self._project_dir):
            widget.setVisible(visible)

    def _open(self, path: str) -> None:
        if not self._open_directory(path):
            self.open_failed.emit(f"Каталог не найден: {path}")

    # --- доступ ---
    def title_text(self) -> str:
        return self._title.text()

    def workspace_link(self) -> PathLink:
        return self._workspace

    def project_dir_link(self) -> PathLink:
        return self._project_dir
```

`theme.py`: удалить правила `#EdtPanel QPushButton {{ … }}` и `#EdtPanel QPushButton:disabled {{ … }}`
(кнопок в панели больше нет). Проверить `tests/ui/test_theme.py` — если какой-то тест ищет
эти правила, убрать проверку.

`ui/edt/view.py:265` — `EdtPanel(open_directory=open_directory)` → `EdtPanel(open_directory=open_directory, palette=self._palette)`
(`self._palette` присвоен строкой 221).

- [ ] **Step 4: Прогон**

Run: `uv run pytest -q tests/ui/test_edt_panel.py tests/ui/test_edt_view.py tests/ui/test_theme.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/ui/edt/panel.py src/onecstarter/ui/edt/view.py src/onecstarter/ui/theme.py tests/ui/test_edt_panel.py tests/ui/test_edt_view.py tests/ui/test_theme.py
git commit -m "feat(edt): панель путей на PathLink, «Рабочая область» (v3.1, замечания 1–2)"
```

---

### Task 3: Панель баз на `PathLink`, `PanelCard` без `show_actions`

**Files:**
- Modify: `src/onecstarter/ui/bases/panel.py` (`ConnectionPanel`), `src/onecstarter/services/connection.py:86-101,133-152`, `src/onecstarter/ui/theme.py` (правила `#ConnectionPanel QPushButton`, `#ConnectionPath` — удалить)
- Test: `tests/ui/test_panel.py`, `tests/unit/test_connection.py:140-201`

**Interfaces:**
- Consumes: `PathLink` (Task 1).
- Produces: `ConnectionPanel(*, open_directory=open_in_explorer, copy_text=copy_to_clipboard, palette: Palette = DARK, parent=None)`; `show_card(card, palette)` без изменений; `text()`, `placeholder()`, `title_text()` без изменений; новый `link() -> PathLink`; `PanelCard` — пять полей (`title, kind_word, icon_kind, path, hint`), `show_actions` удалён.

- [ ] **Step 1: Тесты**

`tests/unit/test_connection.py`: удалить все строки `assert card.show_actions is …` (шесть штук).

`tests/ui/test_panel.py`: заменить тесты, использующие кнопки и поле:

```python
def test_group_and_empty_selection_show_hints_not_emptiness(qtbot: Any) -> None:
    """Панель никогда не пустеет (мокап): группа и пустой выбор объясняются."""
    panel = _panel(qtbot, [])
    panel.show_card(
        panel_card(RowKind.GROUP, _item(None, is_group=True), ""), theme.DARK
    )
    assert panel.text() == ""
    assert panel.placeholder() == "Группа — строки подключения нет"
    assert panel.link().context_menu().actions() == []

    panel.show_card(panel_card(None, None, ""), theme.DARK)
    assert panel.placeholder() == "Выберите базу, чтобы увидеть путь подключения"


def test_copy_puts_shown_text_in_clipboard(qtbot: Any) -> None:
    """В буфер идёт ровно то, что на экране — очищенный адрес (§1.4)."""  # noqa: RUF002
    panel = _panel(qtbot, [])
    _show(panel, _item('ws="http://user:pass@srv/base";'))
    [copy] = panel.link().context_menu().actions()
    assert copy.text() == "Копировать"
    copy.trigger()
    assert QApplication.clipboard().text() == "http://srv/base"


def test_only_file_base_is_a_link(qtbot: Any) -> None:
    """Серверная — текст с одним «Копировать»; файловая — ссылка на каталог (спека v3.1 §3)."""
    opened: list[str] = []
    panel = _panel(qtbot, opened)

    _show(panel, _item('Srvr="localhost";Ref="ACC";'))
    assert panel.link().link_href() is None
    assert [a.text() for a in panel.link().context_menu().actions()] == ["Копировать"]

    _show(panel, _item(r'File="D:\bases\acc";'))
    assert panel.link().link_href() == r"D:\bases\acc"
    panel.link().linkActivated.emit("")
    assert opened == [r"D:\bases\acc"]


@pytest.mark.parametrize("palette", [theme.DARK, theme.LIGHT], ids=["dark", "light"])
def test_hint_uses_the_dim_colour_from_the_project_palette(
    qtbot: Any, palette: theme.Palette
) -> None:
    """Подсказка красится палитрой проекта (Important 1 финального ревью рестайла)."""
    panel = _panel(qtbot, [])
    panel.show_card(panel_card(None, None, ""), palette)
    assert palette.text_dim in panel.link().text()


def test_hint_card_shows_the_placeholder_in_italics(qtbot: Any) -> None:
    panel = _panel(qtbot, [])
    panel.show_card(panel_card(None, None, ""), theme.DARK)
    assert "<i" in panel.link().text()


def test_path_card_shows_the_path_upright(qtbot: Any) -> None:
    panel = _panel(qtbot, [])
    _show(panel, _item('Srvr="localhost";Ref="ACC";'))
    assert "<i" not in panel.link().text()


def test_open_failure_shows_a_warning_not_silence(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text)
    )
    panel = ConnectionPanel(open_directory=lambda _path: False)
    qtbot.addWidget(panel)
    _show(panel, _item(r'File="D:\bases\acc";'))
    panel.link().linkActivated.emit("")
    assert warnings == [r"Не удалось открыть каталог: D:\bases\acc"]  # noqa: RUF001
```

Тест `test_open_directory_enabled_only_for_file_kind` удалить (заменён
`test_only_file_base_is_a_link`), `test_hint_placeholder_uses_the_dim_role_from_the_project_palette`
удалить (заменён `test_hint_uses_the_dim_colour_from_the_project_palette`). Импорты `QColor`,
`QPalette` больше не нужны.

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest -q tests/ui/test_panel.py tests/unit/test_connection.py`
Expected: `AttributeError: 'ConnectionPanel' object has no attribute 'link'`; `test_connection` —
PASS уже сейчас (убрали только лишние утверждения).

- [ ] **Step 3: Реализация**

`services/connection.py`: из `PanelCard` убрать поле `show_actions` и абзац докстринга о нём;
`_EMPTY_CARD = PanelCard(None, None, None, None, _PICK_HINT)`; в `panel_card` убрать последний
позиционный аргумент у всех трёх конструкторов.

`ui/bases/panel.py` — `ConnectionPanel`:

```python
class ConnectionPanel(QWidget):
    def __init__(
        self,
        *,
        open_directory: Callable[[str], bool] = open_in_explorer,
        copy_text: Callable[[str], None] = copy_to_clipboard,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._open_directory = open_directory
        self._card = _EMPTY_CARD

        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        self._title = QLabel()
        self._kind_word = QLabel()
        self._kind_word.setObjectName("PanelKindWord")
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(7)
        title_row.addWidget(self._icon)
        title_row.addWidget(self._title)
        title_row.addWidget(self._kind_word)
        title_row.addStretch(1)

        self._link = PathLink(palette=palette, copy_text=copy_text)
        self._link.open_requested.connect(self._do_open)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        layout.addLayout(title_row)
        layout.addWidget(self._link)
        self.show_card(_EMPTY_CARD, None)

    def show_card(self, card: PanelCard, palette: Palette | None) -> None:
        """Показать карточку. Палитра нужна значку и цветам ссылки; None — оба
        не применяются (только стартовое пустое состояние в __init__).
        """  # noqa: RUF002
        self._card = card
        has_title = card.title is not None
        self._title.setVisible(has_title)
        self._title.setText(card.title or "")
        self._kind_word.setVisible(card.kind_word is not None)
        self._kind_word.setText(f"· {card.kind_word}" if card.kind_word else "")
        show_icon = card.icon_kind is not None and palette is not None
        self._icon.setVisible(show_icon)
        if card.icon_kind is not None and palette is not None:
            self._icon.setPixmap(placement_icon(card.icon_kind, palette).pixmap(16, 16))
        if palette is not None:
            self._link.apply_palette(palette)
        note = card.path.note if card.path else None
        self._link.set_placeholder(card.hint or note or "")
        self._link.set_path(
            card.path.text if card.path else "",
            directory=card.path.directory if card.path else None,
        )

    def text(self) -> str:
        return self._link.path_text()

    def placeholder(self) -> str:
        return self._link.placeholder()

    def title_text(self) -> str:
        parts = [self._title.text()] if self._title.text() else []
        if self._kind_word.text():
            parts.append(self._kind_word.text().removeprefix("· "))
        return " · ".join(parts)

    def link(self) -> PathLink:
        return self._link

    def _do_open(self, directory: str) -> None:
        if not self._open_directory(directory):
            # Молчание здесь читалось бы как «открылось где-то не там».
            QMessageBox.warning(
                self, "OneCStarter", f"Не удалось открыть каталог: {directory}"  # noqa: RUF001
            )
```

Импорты: убрать `QColor, QPalette, QApplication, QLineEdit, QPushButton`; добавить
`from onecstarter.ui.path_link import PathLink, copy_to_clipboard` и `DARK` из `theme`.
`open_in_explorer` остаётся здесь (его импортирует `ui/edt/panel.py`).

`ui/bases/view.py:458`: `ConnectionPanel(parent=self)` → `ConnectionPanel(palette=self._palette, parent=self)`
(`self._palette` присвоен строкой 429).

`theme.py`: удалить `#ConnectionPath {{ … }}`, `#ConnectionPanel QPushButton {{ … }}`,
`#ConnectionPanel QPushButton:disabled {{ … }}`; в `tests/ui/test_theme.py` тест про
`#ConnectionPath` (около строки 160–172) переписать на `#PathLink`: правило существует и задаёт
`font-family` с `Consolas`.

- [ ] **Step 4: Прогон**

Run: `uv run pytest -q tests/ui/test_panel.py tests/unit/test_connection.py tests/ui/test_bases_view.py tests/ui/test_theme.py tests/ui/test_edt_panel.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/ui/bases/panel.py src/onecstarter/ui/bases/view.py src/onecstarter/services/connection.py src/onecstarter/ui/theme.py tests/ui/test_panel.py tests/unit/test_connection.py tests/ui/test_theme.py
git commit -m "feat(bases): панель подключения на PathLink — ссылка у файловой базы, меню «Копировать» (v3.1, замечание 1)"
```

---

### Task 4: «Рабочая область» во всех остальных строках

**Files:**
- Modify: `src/onecstarter/ui/edt/dialog.py:74,122,177,179`, `src/onecstarter/services/edt.py:327-329,447,449`, `src/onecstarter/services/edt_cli.py:53`, `src/onecstarter/ui/edt/console_panel.py:26,28,30`, `src/onecstarter/ui/edt/view.py:661`, `src/onecstarter/ui/edt/cli_import_dialog.py:47`, `README.md:78-90`, `docs/requirements.md` (строка v3 в §5)
- Test: `tests/ui/test_edt_console.py:79-81`, `tests/ui/test_edt_dialog.py:84`, `tests/ui/test_edt_view.py:687,700`, `tests/unit/test_edt_cli.py:163-164`, `tests/unit/test_edt_workspace.py:493`

**Interfaces:** только строки; сигнатуры не меняются.

- [ ] **Step 1: Тесты — новые тексты**

| Файл:строка | Было | Стало |
| --- | --- | --- |
| `test_edt_console.py:79` | `общая ошибка, см. журналы workspace` | `общая ошибка, см. журналы рабочей области` |
| `test_edt_console.py:80` | `workspace занят другим приложением` | `рабочая область занята другим приложением` |
| `test_edt_console.py:81` | `…см. журналы workspace` | `…см. журналы рабочей области` |
| `test_edt_dialog.py:84` | `Путь workspace должен быть абсолютным` | `Путь рабочей области должен быть абсолютным` |
| `test_edt_view.py:687` | `Закройте EDT: workspace занят` | `Закройте EDT: рабочая область занята` |
| `test_edt_view.py:700` | `Пересобрать все проекты workspace «a»? Это займёт время` | `Пересобрать все проекты рабочей области «a»? Это займёт время` |
| `test_edt_cli.py:163` | `Закройте EDT: workspace занят` | `Закройте EDT: рабочая область занята` |
| `test_edt_cli.py:164` | `match="workspace занят"` | `match="рабочая область занята"` |
| `test_edt_workspace.py:493` | `match="занят командой CLI"` | `match="занята командой CLI"` |

В `tests/ui/test_edt_dialog.py` добавить:

```python
def test_workspace_field_is_called_working_area(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)  # хелпер файла: EdtProjectDialog(None, INSTALLED, defaults=DEFAULTS, …)
    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert "Рабочая область" in labels
    assert "Workspace" not in labels
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText("")
    assert dialog.error_text() == "Рабочая область не задана"
```

(импорт `QLabel` из `PySide6.QtWidgets`).

- [ ] **Step 2: Прогон — падает на старых текстах**

Run: `uv run pytest -q tests/ui/test_edt_console.py tests/ui/test_edt_dialog.py tests/ui/test_edt_view.py tests/unit/test_edt_cli.py tests/unit/test_edt_workspace.py`
Expected: FAIL там, где строки ещё старые.

- [ ] **Step 3: Реализация — замена строк**

| Файл | Было | Стало |
| --- | --- | --- |
| `ui/edt/dialog.py:122` | `form.addRow("Workspace", …)` | `form.addRow("Рабочая область", …)` |
| `ui/edt/dialog.py:74` | `пусто — редакторы получают workspace` | `пусто — редакторы получают рабочую область` |
| `ui/edt/dialog.py:177` | `Workspace не задан` | `Рабочая область не задана` |
| `ui/edt/dialog.py:179` | `Путь workspace должен быть абсолютным` | `Путь рабочей области должен быть абсолютным` |
| `services/edt.py:328` | `Workspace занят командой CLI — дождитесь…` | `Рабочая область занята командой CLI — дождитесь завершения или прервите её` |
| `services/edt.py:447` | `Путь workspace пуст` | `Путь рабочей области пуст` |
| `services/edt.py:449` | `Путь workspace должен быть абсолютным` | `Путь рабочей области должен быть абсолютным` |
| `services/edt_cli.py:53` | `Закройте EDT: workspace занят` | `Закройте EDT: рабочая область занята` |
| `ui/edt/console_panel.py:26` | `общая ошибка, см. журналы workspace` | `общая ошибка, см. журналы рабочей области` |
| `ui/edt/console_panel.py:28` | `workspace занят другим приложением` | `рабочая область занята другим приложением` |
| `ui/edt/console_panel.py:30` | `…см. журналы workspace` | `…см. журналы рабочей области` |
| `ui/edt/view.py:661` | `Пересобрать все проекты workspace «{…}»?…` | `Пересобрать все проекты рабочей области «{project.name}»? Это займёт время` |
| `ui/edt/cli_import_dialog.py:47` | `имя нового проекта в workspace` | `имя нового проекта в рабочей области` |

`README.md`, раздел «Проекты EDT (v3)»: «список workspace'ов» → «список рабочих областей»,
«вне workspace» → «вне рабочей области», «на workspace, не открытом в EDT» → «на рабочей
области, не открытой в EDT», «из реестра workspace (`.metadata`)» → «из реестра рабочей области
(`.metadata`)». `docs/requirements.md`, строка v3 в §5: «свой реестр workspace'ов» → «свой
реестр рабочих областей EDT».

Докстринги и комментарии кода, спека v3, протоколы экспериментов и скил `edt-launch` **не
трогаются**: там «workspace» — термин Eclipse (спека v3.1 §4).

- [ ] **Step 4: Прогон и остаточный grep**

Run: `uv run pytest -q tests/ui/test_edt_console.py tests/ui/test_edt_dialog.py tests/ui/test_edt_view.py tests/unit/test_edt_cli.py tests/unit/test_edt_workspace.py tests/ui/test_edt_cli_dialogs.py`
Expected: PASS. Затем `grep -rn "workspace" src/onecstarter/ui src/onecstarter/services --include=*.py | grep '"' | grep -v "workspace_\|_workspace\|\.workspace\|workspace=\|workspace:"` — видимых строк со словом не осталось (докстринги допустимы).

- [ ] **Step 5: Commit**

```bash
git add src README.md docs/requirements.md tests
git commit -m "feat(edt): «Рабочая область» вместо «workspace» во всех видимых строках (v3.1, замечание 2)"
```

---

### Task 5: Колонка «Память»

**Files:**
- Modify: `src/onecstarter/domain/edt.py` (после `join_vm_args`), `src/onecstarter/ui/edt/tree_model.py`, `src/onecstarter/ui/edt/view.py:347-363` (ширина колонки)
- Test: `tests/unit/test_edt_domain.py`, `tests/ui/test_edt_tree_model.py`

**Interfaces:**
- Consumes: `split_vm_args(text) -> VmArgsParts` (`.max_heap_mb`), `EdtWorkspace.installation_for(project) -> EdtInstallation | None` (`.vm_args`).
- Produces: `domain/edt.py::effective_heap_mb(project_vm_args: str, installation_vm_args: str) -> int | None`; `tree_model.COLUMNS = ("Проект", "EDT", "Память")`, `HEAP_DEFAULT_HINT = "-Xmx не задан — действует значение из 1cedt.ini установки"`.

- [ ] **Step 1: Тесты**

`tests/unit/test_edt_domain.py` (добавить):

```python
@pytest.mark.parametrize(
    ("project_args", "installation_args", "expected"),
    [
        ("-Xmx6144m", "-Xmx8192m -Dx=1", 6144),  # запись бьёт установку
        ("-Dfoo=1", "-Xmx8192m", 8192),  # только установка
        ("", "", None),  # нигде — JVM возьмёт -Xmx из 1cedt.ini
        ("-Xmx2g -Xmx4096m", "", 4096),  # два -Xmx — последний, как у JVM
        ("-Xmx1g", "", 1024),
    ],
)
def test_effective_heap_mb(project_args: str, installation_args: str, expected: int | None) -> None:
    assert effective_heap_mb(project_args, installation_args) == expected
```

`tests/ui/test_edt_tree_model.py` — заменить `INSTALLED` на установку с памятью и добавить тесты;
`assert model.columnCount() == 2` → `== 3`:

```python
INSTALLED = [
    EdtInstallation(
        "2025.2.6+4", Path(r"C:\e\1cedt.exe"), Path(r"C:\j\bin"), "-Xmx8192m", 17, "auto"
    )
]


def test_memory_column_shows_effective_xmx(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_project(EdtProject("", "Своя", r"D:\a", edt_version="2025.2.6+4", vm_args="-Xmx6144m"))
    ws.add_project(EdtProject("", "Из установки", r"D:\b", edt_version="2025.2.6+4"))
    ws.add_project(EdtProject("", "Без версии", r"D:\c"))
    model = build_edt_model(ws, "", DARK)
    assert model.horizontalHeaderItem(2).text() == "Память"
    assert model.item(0, 2).text() == "6144 МБ"
    assert model.item(1, 2).text() == "8192 МБ"
    assert model.item(2, 2).text() == "—"
    assert model.item(2, 2).toolTip() == HEAP_DEFAULT_HINT
    assert model.item(0, 2).textAlignment() & Qt.AlignmentFlag.AlignRight


def test_group_row_has_empty_memory_cell(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.add_group("2025", None)
    model = build_edt_model(ws, "", DARK)
    assert model.item(0, 2).text() == ""
```

(импорт `HEAP_DEFAULT_HINT` из `tree_model`, `Qt` из `PySide6.QtCore`).

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest -q tests/unit/test_edt_domain.py tests/ui/test_edt_tree_model.py`
Expected: `ImportError` (`effective_heap_mb`, `HEAP_DEFAULT_HINT`).

- [ ] **Step 3: Реализация**

`domain/edt.py` после `join_vm_args`:

```python
def effective_heap_mb(project_vm_args: str, installation_vm_args: str) -> int | None:
    """Действующий `-Xmx` для колонки «Память» (спека v3.1, §5).

    Запись бьёт установку — как в командной строке, где аргументы записи идут
    после аргументов установки и JVM берёт последний `-Xmx` ([Ф] Э1). Нигде
    не задан — `None`: JVM возьмёт `-Xmx` из `1cedt.ini` установки, который
    мы не разбираем. Настройка «память по умолчанию» в цепочку не входит —
    она лишь подставляется в диалог новой записи.
    """  # noqa: RUF002
    for text in (project_vm_args, installation_vm_args):
        heap = split_vm_args(text).max_heap_mb
        if heap is not None:
            return heap
    return None
```

`ui/edt/tree_model.py`:

```python
COLUMNS = ("Проект", "EDT", "Память")
HEAP_DEFAULT_HINT = "-Xmx не задан — действует значение из 1cedt.ini установки"
```

в `_fill` у группы: `parent.appendRow([item, _plain(""), _plain("")])`; у записи:
`parent.appendRow(_project_row(project, workspace.status(project.id), workspace.installation_for(project), palette))`.

`_project_row(project, status, installation: EdtInstallation | None, palette)` — в конце:

```python
    heap = effective_heap_mb(project.vm_args, installation.vm_args if installation else "")
    memory = _plain(f"{heap} МБ" if heap is not None else "—")
    memory.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if heap is None:
        memory.setToolTip(HEAP_DEFAULT_HINT)
        memory.setForeground(QBrush(QColor(palette.text_dim)))
    return [name, version, memory]
```

(импорт `EdtInstallation`, `effective_heap_mb` из `domain.edt`).

`ui/edt/view.py::rebuild`, первая сборка: после `setColumnWidth(1, 110)` добавить
`self._tree.setColumnWidth(2, 90)`. Цикл `widths` уже берёт `len(COLUMNS) - 1` колонок —
ширины двух первых сохраняются между пересборками, третья — нет (последняя, без растяжения;
достаточно умолчания).

- [ ] **Step 4: Прогон**

Run: `uv run pytest -q tests/unit/test_edt_domain.py tests/ui/test_edt_tree_model.py tests/ui/test_edt_view.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/domain/edt.py src/onecstarter/ui/edt/tree_model.py src/onecstarter/ui/edt/view.py tests/unit/test_edt_domain.py tests/ui/test_edt_tree_model.py
git commit -m "feat(edt): колонка «Память» — действующий -Xmx записи или установки (v3.1, замечание 3)"
```

---

### Task 6: Поиск — крестик очистки, подсказка Ctrl+F, одна комбинация в оболочке

**Files:**
- Create: `src/onecstarter/ui/search_field.py`
- Modify: `src/onecstarter/ui/bases/view.py:436-437,543-546`, `src/onecstarter/ui/edt/view.py:244-245,381-384`, `src/onecstarter/ui/shell.py` (конструктор + метод)
- Test: `tests/ui/test_search_field.py` (новый), `tests/ui/test_shell.py`, `tests/ui/test_bases_view.py`, `tests/ui/test_edt_view.py`

**Interfaces:**
- Produces: `SearchField(QLineEdit)` — `__init__(hint: str, palette: Palette, parent=None)`, `setPlaceholderText(f"{hint} (Ctrl+F)")`; `apply_palette(palette)`; `clear_action() -> QAction`; `clear_icon(palette) -> QIcon`; `HOTKEY_SUFFIX = " (Ctrl+F)"`. `MainWindow._focus_current_search()` за `QShortcut(QKeySequence.StandardKey.Find)`.

- [ ] **Step 1: Тесты**

`tests/ui/test_search_field.py`:

```python
"""Поле поиска: крестик очистки и подсказка Ctrl+F (спека v3.1, §6)."""

from typing import Any

from onecstarter.ui import theme
from onecstarter.ui.search_field import SearchField


def test_placeholder_names_the_hotkey(qtbot: Any) -> None:
    field = SearchField("Поиск: начните вводить имя базы", theme.DARK)
    qtbot.addWidget(field)
    assert field.placeholderText() == "Поиск: начните вводить имя базы (Ctrl+F)"


def test_clear_action_visible_only_with_text_and_clears(qtbot: Any) -> None:
    field = SearchField("Поиск", theme.DARK)
    qtbot.addWidget(field)
    assert field.clear_action().isVisible() is False
    field.setText("роз")
    assert field.clear_action().isVisible() is True
    field.clear_action().trigger()
    assert field.text() == ""
    assert field.clear_action().isVisible() is False


def test_clear_icon_is_drawn_in_dim_colour_of_both_palettes(qtbot: Any) -> None:
    from PySide6.QtGui import QColor

    for palette in (theme.DARK, theme.LIGHT):
        field = SearchField("Поиск", palette)
        qtbot.addWidget(field)
        image = field.clear_action().icon().pixmap(16, 16).toImage()
        assert image.pixelColor(8, 8) == QColor(palette.text_dim)  # центр креста
        assert image.pixelColor(0, 8).alpha() == 0  # край прозрачен


def test_apply_palette_redraws_icon(qtbot: Any) -> None:
    from PySide6.QtGui import QColor

    field = SearchField("Поиск", theme.DARK)
    qtbot.addWidget(field)
    field.apply_palette(theme.LIGHT)
    image = field.clear_action().icon().pixmap(16, 16).toImage()
    assert image.pixelColor(8, 8) == QColor(theme.LIGHT.text_dim)
```

`tests/ui/test_shell.py` (добавить):

```python
def test_ctrl_f_focuses_search_of_current_section(qtbot):
    section = _StubSection()
    window = MainWindow([("Базы", section), ("Серверы", QLabel("без поиска"))])
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert section.focus_calls == 1
    window.show_section(1)
    qtbot.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert section.focus_calls == 1  # у «Серверов» поиска нет — ничего не произошло
```

(импорт `Qt` из `PySide6.QtCore`).

В `tests/ui/test_bases_view.py` и `tests/ui/test_edt_view.py` — по одному тесту:

```python
def test_search_hint_and_clear_button(qtbot, workspace_factory):
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(workspace, installations=INSTALLED, cfg_rules=[],
                     recent_limit=lambda: DEFAULT_RECENT_LIMIT, list_order=lambda: ListOrder.FILE)
    qtbot.addWidget(view)
    assert view.search().placeholderText() == "Поиск: начните вводить имя базы (Ctrl+F)"
    view.search().setText("x")
    view.search().clear_action().trigger()
    assert view.search().text() == ""
```

и для EDT — то же с `harness.view()` и подсказкой «Поиск: начните вводить имя проекта (Ctrl+F)».

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest -q tests/ui/test_search_field.py tests/ui/test_shell.py`
Expected: `ModuleNotFoundError: onecstarter.ui.search_field`; тест Ctrl+F — `focus_calls == 0`.

- [ ] **Step 3: Реализация**

`src/onecstarter/ui/search_field.py`:

```python
"""Поле поиска разделов (спека v3.1, §6): крестик очистки и подсказка Ctrl+F.

Своё действие очистки, а не `setClearButtonEnabled`: у штатного значок — из
системной темы Qt, и его видимость на нашей тёмной палитре ничем не
гарантирована. Значок рисуется цветом `palette.text_dim` по образцу
`ui/rail_icons.py` и перерисовывается при смене темы.
"""  # noqa: RUF002

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLineEdit, QWidget

from onecstarter.ui.theme import Palette

HOTKEY_SUFFIX = " (Ctrl+F)"
_SIZE = 16


def clear_icon(palette: Palette) -> QIcon:
    """Косой крест 8×8 в центре 16×16, цвет — `palette.text_dim`."""
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(palette.text_dim))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(4, 4), QPointF(12, 12))
    painter.drawLine(QPointF(12, 4), QPointF(4, 12))
    painter.end()
    return QIcon(pixmap)


class SearchField(QLineEdit):
    def __init__(self, hint: str, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(hint + HOTKEY_SUFFIX)
        self._clear = QAction("Очистить", self)
        self._clear.setIcon(clear_icon(palette))
        self._clear.setVisible(False)
        self._clear.triggered.connect(self.clear)
        self.addAction(self._clear, QLineEdit.ActionPosition.TrailingPosition)
        self.textChanged.connect(lambda text: self._clear.setVisible(bool(text)))

    def apply_palette(self, palette: Palette) -> None:
        self._clear.setIcon(clear_icon(palette))

    def clear_action(self) -> QAction:
        return self._clear
```

Если `image.pixelColor(8, 8)` в тесте не совпадает из-за сглаживания на пересечении линий —
проверять точку на линии, например `(6, 6)`, и заменить в обоих тестах.

`ui/bases/view.py:436-437`: `self._search = QLineEdit()` + `setPlaceholderText(...)` →
`self._search = SearchField("Поиск: начните вводить имя базы", self._palette)`
(`self._palette` присвоен строкой 429, раньше); в `apply_palette` (строка 543) добавить
`self._search.apply_palette(palette)`; аннотацию `search() -> QLineEdit` заменить на
`-> SearchField`.

`ui/edt/view.py:244-245`: то же с `"Поиск: начните вводить имя проекта"` и `self._palette`
(присвоен строкой 221); в `apply_palette` (строка 381) — `self._search.apply_palette(palette)`;
`search() -> SearchField`.

`ui/shell.py`, в конце `__init__`:

```python
        # Одна комбинация на окно: два QShortcut с Ctrl+F в разделах Qt счёл бы
        # неоднозначными и не сработал бы ни один (спека v3.1, §6).
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self, self._focus_current_search)
```

и метод:

```python
    def _focus_current_search(self) -> None:
        focus = getattr(self._stack.currentWidget(), "focus_search", None)
        if callable(focus):
            focus()
```

(`show_and_focus_search` переписать на вызов `self._focus_current_search()` после подъёма окна).
Импорты: `QKeySequence`, `QShortcut` из `PySide6.QtGui`.

- [ ] **Step 4: Прогон**

Run: `uv run pytest -q tests/ui/test_search_field.py tests/ui/test_shell.py tests/ui/test_bases_view.py tests/ui/test_edt_view.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/ui/search_field.py src/onecstarter/ui/bases/view.py src/onecstarter/ui/edt/view.py src/onecstarter/ui/shell.py tests/ui/test_search_field.py tests/ui/test_shell.py tests/ui/test_bases_view.py tests/ui/test_edt_view.py
git commit -m "feat(ui): крестик очистки и Ctrl+F в поиске разделов (v3.1, замечания 4–5)"
```

---

### Task 7: Группа «О ПРОГРАММЕ», версия в сборке, гейт smoke

**Files:**
- Create: `src/onecstarter/ui/about.py`
- Modify: `src/onecstarter/ui/settings_view.py` (после группы «СПИСОК БАЗ»), `src/onecstarter/ui/app.py:483` (строка smoke), `build/onecstarter.spec:62-70`, `build/smoke.py:80-86`
- Test: `tests/ui/test_about.py` (новый), `tests/ui/test_settings_view.py:148-166`, `tests/ui/test_app.py` (рядом с `test_smoke_logs_keyring_round_trip`)

**Interfaces:**
- Produces: `ui/about.py::app_version() -> str` («неизвестна» без метаданных), `REPOSITORY_URL = "https://github.com/AnanyevAl/OnecStarter"`; `SettingsView.version_label() -> QLabel`, `SettingsView.repository_label() -> QLabel`; строка лога `smoke: version=<x.y.z>`.

- [ ] **Step 1: Тесты**

`tests/ui/test_about.py`:

```python
"""«О программе»: версия из метаданных пакета, без падения при их отсутствии (спека v3.1, §7)."""

import importlib.metadata

import pytest

from onecstarter.ui import about


def test_version_comes_from_package_metadata() -> None:
    assert about.app_version() == importlib.metadata.version("onecstarter")


def test_version_unknown_without_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(about.importlib.metadata, "version", missing)
    assert about.app_version() == "неизвестна"


def test_repository_url() -> None:
    assert about.REPOSITORY_URL == "https://github.com/AnanyevAl/OnecStarter"
```

`tests/ui/test_settings_view.py`: в `test_groups_are_in_section_order` добавить последний
элемент `"О ПРОГРАММЕ"` и обновить докстринг («семь групп … О ПРОГРАММЕ (v3.1) последней»);
импорт `from onecstarter.ui import about`; добавить:

```python
def test_about_group_shows_version_and_repository_link(
    application: QApplication, tmp_path: Path
) -> None:
    view, _ = _view(application, tmp_path)
    assert view.version_label().text() == about.app_version()
    assert about.REPOSITORY_URL in view.repository_label().text()
    assert view.repository_label().openExternalLinks() is True
```

`tests/ui/test_app.py`, рядом с `test_smoke_logs_keyring_round_trip` (импорт `from onecstarter.ui import about`):

```python
def test_smoke_logs_version(tmp_path: Any, monkeypatch: Any, qtbot: Any, caplog: Any) -> None:
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    captured = _capture_window(monkeypatch)
    target = tmp_path / "out"
    target.mkdir()
    with caplog.at_level(logging.INFO):
        code = run_smoke(str(target), {"APPDATA": str(tmp_path / "appdata")}, credential_store=_MemoryVault())
    assert code == 0
    assert f"smoke: version={about.app_version()}" in caplog.text
    qtbot.addWidget(captured["window"])
```

- [ ] **Step 2: Прогон — падает**

Run: `uv run pytest -q tests/ui/test_about.py tests/ui/test_settings_view.py tests/ui/test_app.py -k "about or groups_are or smoke_logs_version"`
Expected: `ModuleNotFoundError: onecstarter.ui.about`.

- [ ] **Step 3: Реализация**

`src/onecstarter/ui/about.py`:

```python
"""«О программе» (спека v3.1, §7): версия из метаданных пакета, ссылка на репозиторий.

Версия — из одного места (`pyproject.toml`, CLAUDE.md «Сборка»): метаданные
пакета собираются из него; в exe их кладёт `copy_metadata` в `build/onecstarter.spec`,
гейт — строка `smoke: version=` в самопроверке сборки.
"""  # noqa: RUF002

import importlib.metadata

REPOSITORY_URL = "https://github.com/AnanyevAl/OnecStarter"
VERSION_UNKNOWN = "неизвестна"


def app_version() -> str:
    try:
        return importlib.metadata.version("onecstarter")
    except importlib.metadata.PackageNotFoundError:
        return VERSION_UNKNOWN
```

`ui/settings_view.py`, после строк группы «СПИСОК БАЗ» (перед `layout.addWidget(self._status)`):

```python
        self._add_group("О ПРОГРАММЕ")  # noqa: RUF001
        self._version_label = QLabel(about.app_version())
        self._add_row("Версия", "Из pyproject.toml — единственного места", self._version_label)
        self._repository_label = QLabel(
            f'<a href="{about.REPOSITORY_URL}">{about.REPOSITORY_URL}</a>'
        )
        self._repository_label.setOpenExternalLinks(True)
        self._repository_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._add_row("Репозиторий", "Исходники, выпуски, замечания", self._repository_label)
```

и аксессоры `version_label()`, `repository_label()` рядом с остальными. Импорт
`from onecstarter.ui import about`.

`ui/app.py`, после `_log.info("smoke: keyring=%s", …)`:

```python
        _log.info("smoke: version=%s", about.app_version())
```

`build/onecstarter.spec`: `from PyInstaller.utils.hooks import copy_metadata` и в `Analysis(...)`
`datas=[(…registry.toml…)] + copy_metadata("onecstarter")`, с комментарием: версия в «О программе»
читается из метаданных пакета, без `copy_metadata` frozen-сборка показала бы «неизвестна» —
гейт `smoke: version=`.

`build/smoke.py`, после гейта `edt=`:

```python
        version = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text("utf-8"))["project"]["version"]
        if f"smoke: version={version}" not in log_text:
            print(f"smoke: версия в сборке не совпадает с pyproject.toml ({version}) — см. строку smoke: version= в логе")
            return 1
```

(`import tomllib`; разбить длинные строки под 100 символов). Докстринг модуля дополнить пунктом (7).

- [ ] **Step 4: Прогон**

Run: `uv run pytest -q tests/ui/test_about.py tests/ui/test_settings_view.py tests/ui/test_app.py && uv run ruff check . && uv run mypy`
Expected: PASS; ruff и mypy чисты (`build/` вне mypy).

- [ ] **Step 5: Commit**

```bash
git add src/onecstarter/ui/about.py src/onecstarter/ui/settings_view.py src/onecstarter/ui/app.py build/onecstarter.spec build/smoke.py tests/ui/test_about.py tests/ui/test_settings_view.py tests/ui/test_app.py
git commit -m "feat(settings): группа «О программе» — версия из метаданных и ссылка на GitHub; гейт smoke: version= (v3.1, замечание 6)"
```

---

### Task 8: Версия 3.1.0, документы, сборка и выпуск

**Files:**
- Modify: `pyproject.toml` (`version = "3.1.0"`), `README.md` (артефакты `3.1.0`; в разделе «Чем лучше штатного стартера» одна строка: «Пути в панелях — ссылки: клик открывает каталог, правая кнопка — «Копировать»; поиск — Ctrl+F с крестиком очистки; версия и ссылка на репозиторий — в Настройках → «О программе»»), `docs/requirements.md` §5 (строка `v3.1` после `v3`: «Замечания по проверке v3: пути-ссылки в панелях, «Рабочая область», колонка «Память», крестик и Ctrl+F в поиске, «О программе»»), `docs/tasks.md` (T-17.4 → DONE, новый раздел T-18 со сводкой задач и мутационных проверок)

- [ ] **Step 1: Версия и полный прогон**

`pyproject.toml`: `version = "3.1.0"`. Run: `uv sync && uv run pytest -q > e:/tmp/v31-final.log 2>&1; tail -3 e:/tmp/v31-final.log && uv run ruff check . && uv run mypy`
Expected: все PASS (известный флейк `access violation` pytest-qt — повторить прогон).

- [ ] **Step 2: Мутационные проверки**

- `test_open_failure_reported` (EDT-панель): временно заменить в `EdtPanel._open` условие на
  `if False:` — тест обязан упасть (`errors == []`); откатить.
- `test_open_failure_shows_a_warning_not_silence` (панель баз): то же с `_do_open`.
- `test_version_unknown_without_metadata`: убрать `try/except` в `app_version` — тест падает
  с `PackageNotFoundError`; откатить.
- Результаты — в `docs/tasks.md`, раздел T-18.

- [ ] **Step 3: Документы**

`docs/tasks.md`: T-17.4 → `DONE (замечания 1–6 закрыты вехой v3.1)`; новый раздел
`## T-18. v3.1 — замечания по проверке v3 — DONE (<дата>)` со ссылкой на спеку и план,
таблицей задач 1–7 и мутационными проверками. `docs/requirements.md` §5 — строка v3.1 и абзац
о выпуске. `README.md` — `OneCStarter-3.1.0-setup.exe` / `-portable.zip`.

- [ ] **Step 4: Сборка и smoke**

Run (PowerShell): `powershell -NoProfile -ExecutionPolicy Bypass -File build/build.ps1`
Expected: `smoke: OK` (включая новый гейт `version=3.1.0`), `dist/OneCStarter-3.1.0-portable.zip`,
`dist/OneCStarter-3.1.0-setup.exe`.

- [ ] **Step 5: Ручной smoke заказчика**

Чек-лист: панель EDT — путь рабочей области ссылкой, клик открывает Проводник, ПКМ → «Копировать»;
панель баз — файловая база ссылкой, серверная — только «Копировать»; колонка «Память» с
`8192 МБ`; крестик в поиске на обеих темах; Ctrl+F из любого места раздела; Настройки → «О ПРОГРАММЕ»
показывает `3.1.0` и ссылка открывает GitHub.

- [ ] **Step 6: Commit, слияние, тег (с подтверждения заказчика)**

```bash
git add pyproject.toml uv.lock README.md docs
git commit -m "build: версия 3.1.0; документы вехи v3.1"
git checkout master && git merge --no-ff feat/2026-09-15-v31 -m "Веха v3.1: замечания по проверке v3"
git tag -a v3.1.0 -m "v3.1.0 — замечания по проверке v3"
git push origin master --tags
```

---

## Чего в плане нет — сознательно

- Открытие веб-URL по клику в панели баз (решение заказчика, спека §1).
- Сортировка по колонке «Память», разбор `-Xmx` из `1cedt.ini` для колонки.
- Поиск в разделе «Серверы» (его нет — Ctrl+F там ничего не делает).
- Вынос CLI-части `ui/edt/view.py` — отдельный техдолг, не эта веха.
