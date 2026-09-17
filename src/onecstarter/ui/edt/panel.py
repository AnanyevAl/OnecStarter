"""Панель путей под деревом раздела «EDT» (решение заказчика 11.09.2026; v3.1 §3).

Заголовок жирным, два пути — `PathLink` (ссылка открывает каталог, ПКМ — меню
«Открыть каталог»/«Копировать»). Ряд кнопок снят по замечанию 1 заказчика.
Версии здесь нет — она видна в списке.
"""

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
