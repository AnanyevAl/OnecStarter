"""Диалог `import` CLI EDT (спека §14.2): существующий проект или файлы XML."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt_cli import ImportForm, cli_import_args
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.edt.dialog import browse_for_directory


class CliImportDialog(QDialog):
    def __init__(
        self,
        *,
        choose_directory: Callable[[], str] = browse_for_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импортировать проект (CLI EDT)")
        self._choose_directory = choose_directory
        self._existing = QRadioButton("Существующий проект EDT")
        self._xml = QRadioButton("Файлы конфигурации XML")
        self._existing.setChecked(True)
        self._existing_dir = QLineEdit()
        self._existing_browse = QPushButton("Обзор…")
        self._existing_browse.clicked.connect(lambda: self._browse_into(self._existing_dir))
        self._xml_dir = QLineEdit()
        self._xml_browse = QPushButton("Обзор…")
        self._xml_browse.clicked.connect(lambda: self._browse_into(self._xml_dir))
        self._project_dir = QLineEdit()
        self._project_dir.setPlaceholderText("каталог нового проекта — или имя ниже")
        self._project_dir_browse = QPushButton("Обзор…")
        self._project_dir_browse.clicked.connect(lambda: self._browse_into(self._project_dir))
        self._project_name = QLineEdit()
        self._project_name.setPlaceholderText("имя нового проекта в workspace")
        self._base_project = QLineEdit()
        self._base_project.setPlaceholderText("для расширений и внешних обработок")
        self._platform_version = QLineEdit()
        self._platform_version.setPlaceholderText("8.3.24 — пусто: из файлов")
        self._build = QCheckBox("Собрать после импорта (--build)")
        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self._existing)
        form.addRow("Каталог проекта", self._row(self._existing_dir, self._existing_browse))
        form.addRow(self._xml)
        form.addRow("Каталог файлов XML", self._row(self._xml_dir, self._xml_browse))
        form.addRow(
            "Каталог нового проекта", self._row(self._project_dir, self._project_dir_browse)
        )
        form.addRow("Имя нового проекта", self._project_name)
        form.addRow("Базовый проект", self._base_project)
        form.addRow("Версия платформы", self._platform_version)
        form.addRow("", self._build)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)

        for widget in (
            self._existing_dir,
            self._xml_dir,
            self._project_dir,
            self._project_name,
            self._base_project,
            self._platform_version,
        ):
            widget.textChanged.connect(self._refresh)
        self._existing.toggled.connect(self._refresh)
        self._build.toggled.connect(self._refresh)
        self._refresh()

    def form(self) -> ImportForm:
        if self._existing.isChecked():
            return ImportForm(existing_project_dir=self._existing_dir.text().strip())
        return ImportForm(
            configuration_files=self._xml_dir.text().strip(),
            project_dir=self._project_dir.text().strip(),
            project_name=self._project_name.text().strip(),
            base_project_name=self._base_project.text().strip(),
            platform_version=self._platform_version.text().strip(),
            build_after=self._build.isChecked(),
        )

    def _refresh(self, *_args: object) -> None:
        xml = self._xml.isChecked()
        for widget in (
            self._xml_dir,
            self._xml_browse,
            self._project_dir,
            self._project_dir_browse,
            self._project_name,
            self._base_project,
            self._platform_version,
            self._build,
        ):
            widget.setEnabled(xml)
        for widget in (self._existing_dir, self._existing_browse):
            widget.setEnabled(not xml)
        try:
            cli_import_args(self.form())
        except ValueError as error:
            self._error.setText(str(error))
            self.ok_button().setEnabled(False)
            return
        self._error.setText("")
        self.ok_button().setEnabled(True)

    def _browse_into(self, edit: QLineEdit) -> None:
        chosen = self._choose_directory()
        if chosen:
            edit.setText(chosen)

    @staticmethod
    def _row(edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    # --- доступ ---
    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]

    def error_text(self) -> str:
        return self._error.text()

    def existing_radio(self) -> QRadioButton:
        return self._existing

    def xml_radio(self) -> QRadioButton:
        return self._xml

    def existing_dir_edit(self) -> QLineEdit:
        return self._existing_dir

    def existing_browse(self) -> QPushButton:
        return self._existing_browse

    def xml_dir_edit(self) -> QLineEdit:
        return self._xml_dir

    def project_dir_edit(self) -> QLineEdit:
        return self._project_dir

    def project_name_edit(self) -> QLineEdit:
        return self._project_name

    def base_project_edit(self) -> QLineEdit:
        return self._base_project

    def platform_version_edit(self) -> QLineEdit:
        return self._platform_version

    def build_checkbox(self) -> QCheckBox:
        return self._build
