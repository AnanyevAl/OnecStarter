"""Панель путей под деревом раздела «EDT» (решение заказчика 11.09.2026).

Калька `ui/bases/panel.py::ConnectionPanel`: заголовок жирным, пути в read-only
`QLineEdit` (выделение и Ctrl+C штатно), кнопки «Копировать»/«Открыть каталог»
у каждого пути. Версии здесь нет — она видна в списке.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from onecstarter.domain.edt import EdtProject
from onecstarter.ui.bases.panel import open_in_explorer
from onecstarter.ui.theme import Palette

PLACEHOLDER_NONE = "Выберите проект"
PLACEHOLDER_NO_PROJECT_DIR = "не задан — редакторы получают workspace"


def _copy_to_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


class _PathRow:
    def __init__(
        self,
        caption: str,
        copy_text: Callable[[str], None],
        open_directory: Callable[[str], bool],
        on_failure: Callable[[str], None],
    ) -> None:
        self.caption = QLabel(caption)
        self.caption.setObjectName("PanelKindWord")
        self.field = QLineEdit()
        self.field.setObjectName("ConnectionPath")
        self.field.setReadOnly(True)
        self.copy = QPushButton("Копировать")
        self.open = QPushButton("Открыть каталог")
        self.copy.clicked.connect(lambda: copy_text(self.field.text()))

        def open_dir() -> None:
            path = self.field.text()
            if path and not open_directory(path):
                on_failure(f"Каталог не найден: {path}")

        self.open.clicked.connect(open_dir)

    def widgets(self) -> tuple[QWidget, ...]:
        return (self.caption, self.field, self.copy, self.open)

    def show(self, path: str, placeholder: str, palette: Palette) -> None:
        self.field.setText(path)
        self.field.setPlaceholderText(placeholder if not path else "")
        field_palette = self.field.palette()
        field_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette.text_dim))
        self.field.setPalette(field_palette)
        font = self.field.font()
        font.setItalic(not path)
        self.field.setFont(font)
        self.copy.setEnabled(bool(path))
        self.open.setEnabled(bool(path))
        for widget in self.widgets():
            widget.setVisible(True)

    def hide(self) -> None:
        for widget in self.widgets():
            widget.setVisible(False)


class EdtPanel(QWidget):
    open_failed = Signal(str)

    def __init__(
        self,
        *,
        open_directory: Callable[[str], bool] = open_in_explorer,
        copy_text: Callable[[str], None] = _copy_to_clipboard,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EdtPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._title = QLabel(PLACEHOLDER_NONE)
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        self._workspace = _PathRow("Workspace", copy_text, open_directory, self.open_failed.emit)
        self._project_dir = _PathRow(
            "Каталог проекта", copy_text, open_directory, self.open_failed.emit
        )
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        for row, path_row in enumerate((self._workspace, self._project_dir)):
            grid.addWidget(path_row.caption, row, 0)
            grid.addWidget(path_row.field, row, 1)
            grid.addWidget(path_row.copy, row, 2)
            grid.addWidget(path_row.open, row, 3)
        grid.setColumnStretch(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        layout.addWidget(self._title)
        layout.addLayout(grid)
        self.show_nothing()

    def show_project(self, project: EdtProject, palette: Palette) -> None:
        self._title.setText(project.name)
        self._workspace.show(project.workspace, "", palette)
        self._project_dir.show(project.project_dir, PLACEHOLDER_NO_PROJECT_DIR, palette)

    def show_group(self, name: str) -> None:
        self._title.setText(name)
        self._workspace.hide()
        self._project_dir.hide()

    def show_nothing(self) -> None:
        self._title.setText(PLACEHOLDER_NONE)
        self._workspace.hide()
        self._project_dir.hide()

    # --- доступ ---
    def title_text(self) -> str:
        return self._title.text()

    def workspace_field(self) -> QLineEdit:
        return self._workspace.field

    def project_dir_field(self) -> QLineEdit:
        return self._project_dir.field

    def workspace_open_button(self) -> QPushButton:
        return self._workspace.open

    def project_dir_open_button(self) -> QPushButton:
        return self._project_dir.open

    def workspace_copy_button(self) -> QPushButton:
        return self._workspace.copy

    def project_dir_copy_button(self) -> QPushButton:
        return self._project_dir.copy
