"""Диалог «Цветовая схема — <запись>» (спека v3.2, §5): источники, предпросмотр,
таблица 22 цветов, инверсия, сохранение в `.csi`, тема окна, «Применить».

Правки цветов живут в диалоге и не трогают файлы до «Применить»; запись ничего не
запоминает — истина в рабочей области (§1). Занятость области проверяется дважды:
кнопка при открытии (подсказка) и сервис при записи (гонка со сканом, §4). Ошибка
чтения источника помечает строку списка и не трогает таблицу (§7). «По умолчанию EDT»
без правок — `WorkspaceSchemes.reset` (снять наши ключи), с правками — обычная запись.
Палитра диалога — из темы OneCStarter (общий stylesheet), предпросмотр — цветами схемы.
"""  # noqa: RUF002

import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt_scheme import (
    COLOR_KEYS,
    CURRENT_NAME,
    DEFAULT_NAME,
    EDT_DEFAULTS,
    RGB,
    THEME_IDS,
    Scheme,
    ThemeChoice,
    from_hex,
    invert,
    to_hex,
)
from onecstarter.services.edt_scheme import (
    BUSY_MESSAGE,
    CatalogEntry,
    SchemeCatalog,
    WorkspaceSchemes,
    save_csi,
)
from onecstarter.services.errors import EdtError
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.edt.scheme_preview import SchemePreview
from onecstarter.ui.search_field import SearchField
from onecstarter.ui.theme import Palette

TITLE = "Цветовая схема — {name}"
HINT_NO_DIR = "Каталог схем не задан — Настройки → EDT"
HINT_MISSING_DIR = "Каталог схем не найден: {path}"
APPLIED_MESSAGE = "Схема применена. Изменения видны после запуска EDT"
BUTTON_INVERT = "Инвертировать"
BUTTON_SAVE = "Сохранить в файл…"
BUTTON_APPLY = "Применить"
THEME_LABEL = "Тема окна:"
THEME_TITLES: dict[ThemeChoice, str] = {
    ThemeChoice.KEEP: "не трогать",
    ThemeChoice.DARK: "тёмная",
    ThemeChoice.LIGHT: "светлая",
}
COLUMN_TITLES = ("Цвет", "Образец", "Код")
SEARCH_HINT = "Поиск: имя схемы"
KIND_CURRENT = "current"
KIND_DEFAULT = "default"
KIND_CATALOG = "catalog"
_ICON = 12
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PROBLEM_FALLBACK: RGB = (229, 115, 115)


def browse_for_csi(initial: str) -> str:
    """Диалог сохранения `.csi`; пустая строка — отмена."""
    return QFileDialog.getSaveFileName(
        None, "Сохранить схему", initial, "Цветовая схема (*.csi)"
    )[0]


def pick_color(current: RGB) -> RGB | None:
    color = QColorDialog.getColor(QColor(current[0], current[1], current[2]), None, "Цвет")
    return (color.red(), color.green(), color.blue()) if color.isValid() else None


def swatch_icon(rgb: RGB, border: str) -> QIcon:
    """Кружок цвета `rgb` с обводкой `border` (hex палитры) — значок строки источника."""  # noqa: RUF002
    pixmap = QPixmap(_ICON, _ICON)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(rgb[0], rgb[1], rgb[2]))
    painter.setPen(QColor(border))
    painter.drawEllipse(1, 1, _ICON - 2, _ICON - 2)
    painter.end()
    return QIcon(pixmap)


class SchemeDialog(QDialog):
    def __init__(
        self,
        project_name: str,
        workspace: WorkspaceSchemes,
        catalog: SchemeCatalog | None,
        *,
        palette: Palette,
        is_busy: Callable[[], bool],
        show_info: Callable[[str], None],
        show_error: Callable[[str], None],
        choose_save: Callable[[str], str] = browse_for_csi,
        choose_color: Callable[[RGB], RGB | None] = pick_color,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE.format(name=project_name))
        self._workspace = workspace
        self._catalog = catalog
        self._palette = palette
        self._is_busy = is_busy
        self._show_info = show_info
        self._show_error = show_error
        self._choose_save = choose_save
        self._choose_color = choose_color
        self._scheme = Scheme(DEFAULT_NAME, EDT_DEFAULTS)
        self._kind = KIND_DEFAULT
        self._rows: list[tuple[str, CatalogEntry | None]] = []
        self._filling = False

        self._search = SearchField(SEARCH_HINT, palette)
        self._search.textChanged.connect(self._filter)
        self._sources = QListWidget()
        self._sources.setObjectName("SchemeSources")
        self._sources.currentRowChanged.connect(self._on_source_changed)
        self._hint = QLabel("")
        self._hint.setObjectName("SchemeHint")
        self._hint.setWordWrap(True)
        self._hint.hide()

        self._preview = SchemePreview()
        self._table = QTableWidget(len(COLOR_KEYS), len(COLUMN_TITLES))
        self._table.setObjectName("SchemeTable")
        self._table.setHorizontalHeaderLabels(list(COLUMN_TITLES))
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 48)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellClicked.connect(self._on_cell_clicked)

        self._invert = QPushButton(BUTTON_INVERT)
        self._invert.clicked.connect(self._on_invert)
        self._save = QPushButton(BUTTON_SAVE)
        self._save.clicked.connect(self._on_save)
        self._theme_label = QLabel(THEME_LABEL)
        self._theme = QComboBox()
        for choice in ThemeChoice:
            if choice is ThemeChoice.KEEP or choice in THEME_IDS:
                self._theme.addItem(THEME_TITLES[choice], choice.value)
        theme_visible = self._theme.count() > 1
        self._theme_label.setVisible(theme_visible)
        self._theme.setVisible(theme_visible)
        self._apply = QPushButton(BUTTON_APPLY)
        self._apply.clicked.connect(self._on_apply)
        self._buttons = russian_button_box(ButtonKind.CLOSE)
        self._buttons.rejected.connect(self.reject)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._search)
        left_layout.addWidget(self._sources, 1)
        left_layout.addWidget(self._hint)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._preview, 2)
        right_layout.addWidget(self._table, 3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        bottom = QHBoxLayout()
        bottom.addWidget(self._invert)
        bottom.addWidget(self._save)
        bottom.addSpacing(12)
        bottom.addWidget(self._theme_label)
        bottom.addWidget(self._theme)
        bottom.addStretch(1)
        bottom.addWidget(self._apply)
        bottom.addWidget(self._buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)
        self.resize(960, 640)

        self._reload_sources(select=None)
        self._refresh_apply()

    # --- источники ---

    def _reload_sources(self, select: Path | None) -> None:
        self._sources.blockSignals(True)
        self._sources.clear()
        self._rows = [(KIND_CURRENT, None), (KIND_DEFAULT, None)]
        self._sources.addItem(QListWidgetItem(CURRENT_NAME))
        self._sources.addItem(QListWidgetItem(DEFAULT_NAME))
        hint = ""
        if self._catalog is None:
            hint = HINT_NO_DIR
        elif not self._catalog.exists():
            hint = HINT_MISSING_DIR.format(path=self._catalog.directory)
        else:
            for entry in self._catalog.entries():
                self._rows.append((KIND_CATALOG, entry))
                item = QListWidgetItem(entry.name)
                item.setToolTip(str(entry.path))
                self._sources.addItem(item)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))
        self._sources.blockSignals(False)
        row = 0
        if select is not None:
            row = next(
                (
                    i
                    for i, (_kind, entry) in enumerate(self._rows)
                    if entry and entry.path == select
                ),
                0,
            )
        self._sources.setCurrentRow(row)  # currentRowChanged → _on_source_changed
        self._filter(self._search.text())

    def _on_source_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._rows):
            return
        kind, entry = self._rows[row]
        item = self._sources.item(row)
        try:
            if kind == KIND_CURRENT:
                scheme = self._workspace.current(EDT_DEFAULTS)
            elif kind == KIND_DEFAULT:
                scheme = Scheme(DEFAULT_NAME, EDT_DEFAULTS)
            else:
                assert self._catalog is not None and entry is not None  # инвариант _rows
                scheme = self._catalog.load(entry)
        except EdtError as error:
            problem = from_hex(self._palette.problem) or _PROBLEM_FALLBACK
            item.setIcon(swatch_icon(problem, self._palette.problem))
            item.setToolTip(str(error))
            return
        self._kind = kind
        item.setIcon(swatch_icon(scheme.colors["Background"], self._palette.border))
        self._show_scheme(scheme)

    def _filter(self, text: str) -> None:
        needle = text.casefold()
        for index in range(self._sources.count()):
            item = self._sources.item(index)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    # --- таблица и предпросмотр ---

    def _show_scheme(self, scheme: Scheme) -> None:
        self._scheme = scheme
        self._fill_table()
        self._preview.show_scheme(scheme)

    def _fill_table(self) -> None:
        self._filling = True
        fixed = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        for row, key in enumerate(COLOR_KEYS):
            rgb = self._scheme.colors[key.name]
            title = QTableWidgetItem(key.title)
            title.setFlags(fixed)
            swatch = QTableWidgetItem("")
            swatch.setFlags(fixed)
            swatch.setBackground(QBrush(QColor(rgb[0], rgb[1], rgb[2])))
            self._table.setItem(row, 0, title)
            self._table.setItem(row, 1, swatch)
            self._table.setItem(row, 2, QTableWidgetItem(to_hex(rgb)))
        self._filling = False

    def set_color(self, name: str, rgb: RGB) -> None:
        colors = dict(self._scheme.colors)
        colors[name] = rgb
        self._scheme = Scheme(self._scheme.name, colors, self._scheme.source)
        row = next(i for i, key in enumerate(COLOR_KEYS) if key.name == name)
        self._filling = True
        swatch, code = self._table.item(row, 1), self._table.item(row, 2)
        assert swatch is not None and code is not None  # заполнено _fill_table
        swatch.setBackground(QBrush(QColor(rgb[0], rgb[1], rgb[2])))
        code.setText(to_hex(rgb))
        self._filling = False
        self._preview.show_scheme(self._scheme)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 2:
            return
        key = COLOR_KEYS[item.row()]
        rgb = from_hex(item.text())
        if rgb is None:
            self._filling = True
            item.setText(to_hex(self._scheme.colors[key.name]))
            self._filling = False
            return
        self.set_color(key.name, rgb)

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column != 1:
            return
        key = COLOR_KEYS[row]
        chosen = self._choose_color(self._scheme.colors[key.name])
        if chosen is not None:
            self.set_color(key.name, chosen)

    def _on_invert(self) -> None:
        self._show_scheme(invert(self._scheme))

    # --- сохранение и применение ---

    def _on_save(self) -> None:
        directory = (
            self._catalog.directory
            if self._catalog is not None and self._catalog.exists()
            else Path()
        )
        name = _UNSAFE.sub("_", self._scheme.name).strip() or "scheme"
        chosen = self._choose_save(str(directory / f"{name}.csi"))
        if not chosen:
            return
        path = Path(chosen)
        try:
            save_csi(path, Scheme(path.stem, self._scheme.colors, str(path)))
        except EdtError as error:
            self._show_error(str(error))
            return
        self._reload_sources(select=path)

    def _on_apply(self) -> None:
        if self._is_busy():
            self._show_error(BUSY_MESSAGE)
            self._refresh_apply()
            return
        theme = ThemeChoice(self._theme.currentData())
        try:
            if self._kind == KIND_DEFAULT and self._scheme.colors == EDT_DEFAULTS:
                self._workspace.reset(theme)
            else:
                self._workspace.apply(self._scheme, theme)
        except EdtError as error:
            self._show_error(str(error))
            return
        self._show_info(APPLIED_MESSAGE)

    def _refresh_apply(self) -> None:
        busy = self._is_busy()
        self._apply.setEnabled(not busy)
        self._apply.setToolTip(BUSY_MESSAGE if busy else "")

    # --- доступ ---

    def sources(self) -> QListWidget:
        return self._sources

    def table(self) -> QTableWidget:
        return self._table

    def preview(self) -> SchemePreview:
        return self._preview

    def hint_label(self) -> QLabel:
        return self._hint

    def search(self) -> SearchField:
        return self._search

    def apply_button(self) -> QPushButton:
        return self._apply

    def invert_button(self) -> QPushButton:
        return self._invert

    def save_button(self) -> QPushButton:
        return self._save

    def theme_combo(self) -> QComboBox:
        return self._theme

    def scheme(self) -> Scheme:
        return self._scheme
