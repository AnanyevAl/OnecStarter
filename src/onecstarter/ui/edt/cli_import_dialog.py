"""Диалог `import` CLI EDT (спека v3 §14.2, v3.1.1 §3): проекты в каталоге или файлы XML.

Каталог подставляется из записи, проекты в нём находит `scan_projects` (правило
мастера импорта Eclipse), уже привязанные к рабочей области — сняты и недоступны:
повторный `import` стоит ≈48 с и ничего не даёт ([Ф] Э6, Э12).
"""  # noqa: RUF002

import os
from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt_cli import (
    ImportForm,
    ProjectCandidate,
    WorkspaceEntry,
    cli_import_commands,
    mark_in_workspace,
)
from onecstarter.services.edt_cli import SCAN_MAX_DEPTH, scan_projects
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.edt.dialog import browse_for_directory

IN_WORKSPACE_SUFFIX = " — уже в рабочей области"
NOT_FOUND = f"Проектов не найдено: каталог с .project ищется до {SCAN_MAX_DEPTH} уровней"  # noqa: RUF001
NO_DIR = "Каталог не существует"
NONE_SELECTED = "Не выбран ни один проект"  # noqa: RUF001
PLACEHOLDER = "каталог с проектами EDT, например клон репозитория"  # noqa: RUF001


class CliImportDialog(QDialog):
    def __init__(
        self,
        project_dir: str,
        entries: Sequence[WorkspaceEntry],
        *,
        scan: Callable[[str], list[ProjectCandidate]] = scan_projects,
        is_dir: Callable[[str], bool] = os.path.isdir,
        choose_directory: Callable[[], str] = browse_for_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импортировать проекты (CLI EDT)")
        self._entries = list(entries)
        self._scan = scan
        self._is_dir = is_dir
        self._choose_directory = choose_directory
        self._candidates: list[ProjectCandidate] = []

        self._existing = QRadioButton("Проекты EDT в каталоге")
        self._xml = QRadioButton("Файлы конфигурации XML")
        self._existing.setChecked(True)
        self._existing_dir = QLineEdit(project_dir)
        self._existing_dir.setPlaceholderText(PLACEHOLDER)
        # Не textChanged: обход трёх уровней от `E:\` не мгновенный  # noqa: RUF003
        self._existing_dir.editingFinished.connect(self._rescan)
        self._existing_browse = QPushButton("Обзор…")
        self._existing_browse.clicked.connect(self._browse_existing)
        self._list = QListWidget()
        self._list.setMinimumHeight(180)
        self._list.itemChanged.connect(self._refresh)
        self._select_all = QPushButton("Выбрать всё")
        self._select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self._select_none = QPushButton("Снять всё")
        self._select_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self._status = QLabel("")

        self._xml_dir = QLineEdit()
        self._xml_browse = QPushButton("Обзор…")
        self._xml_browse.clicked.connect(lambda: self._browse_into(self._xml_dir))
        self._project_dir = QLineEdit()
        self._project_dir.setPlaceholderText("каталог нового проекта — или имя ниже")
        self._project_dir_browse = QPushButton("Обзор…")
        self._project_dir_browse.clicked.connect(lambda: self._browse_into(self._project_dir))
        self._project_name = QLineEdit()
        self._project_name.setPlaceholderText("имя нового проекта в рабочей области")
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

        tools = QWidget()
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.addWidget(self._select_all)
        tools_layout.addWidget(self._select_none)
        tools_layout.addStretch(1)
        tools_layout.addWidget(self._status)

        form = QFormLayout()
        form.addRow(self._existing)
        form.addRow("Каталог", self._row(self._existing_dir, self._existing_browse))
        form.addRow(self._list)
        form.addRow(tools)
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
        self.resize(720, 640)

        for widget in (
            self._xml_dir,
            self._project_dir,
            self._project_name,
            self._base_project,
            self._platform_version,
        ):
            widget.textChanged.connect(self._refresh)
        self._existing.toggled.connect(self._refresh)
        self._build.toggled.connect(self._refresh)
        if project_dir:
            self._rescan()
        else:
            self._refresh()

    def form(self) -> ImportForm:
        if self._existing.isChecked():
            return ImportForm(existing_project_dirs=tuple(self.selected_paths()))
        return ImportForm(
            configuration_files=self._xml_dir.text().strip(),
            project_dir=self._project_dir.text().strip(),
            project_name=self._project_name.text().strip(),
            base_project_name=self._base_project.text().strip(),
            platform_version=self._platform_version.text().strip(),
            build_after=self._build.isChecked(),
        )

    def selected_paths(self) -> list[str]:
        return [
            candidate.path
            for index, candidate in enumerate(self._candidates)
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _rescan(self) -> None:
        root = self._existing_dir.text().strip()
        self._list.blockSignals(True)  # itemChanged на каждом addItem — лишние _refresh
        try:
            self._list.clear()
            self._candidates = []
            status = ""
            if root:
                self._candidates = mark_in_workspace(self._scan(root), self._entries)
                for candidate in self._candidates:
                    suffix = IN_WORKSPACE_SUFFIX if candidate.in_workspace else ""
                    item = QListWidgetItem(candidate.relative + suffix)
                    item.setToolTip(candidate.path)
                    if candidate.in_workspace:
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                        item.setCheckState(Qt.CheckState.Unchecked)
                    else:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Checked)
                    self._list.addItem(item)
                bound = sum(1 for candidate in self._candidates if candidate.in_workspace)
                if self._candidates:
                    status = f"Найдено {len(self._candidates)}, уже в рабочей области {bound}"
                elif self._is_dir(root):
                    status = NOT_FOUND
                else:
                    status = NO_DIR
            self._status.setText(status)
        finally:
            # Отказ self._scan (исключение — ошибка программы, не пользователя,
            # наружу пропускается как есть) не должен оставить список с  # noqa: RUF003
            # заблокированными сигналами: иначе флажки и «Выбрать всё/Снять всё»
            # перестанут вызывать _refresh(), а ОК и строка ошибки застынут  # noqa: RUF003
            # (ревью, раунд правок 1).
            self._list.blockSignals(False)
            self._refresh()

    def _set_all(self, state: Qt.CheckState) -> None:
        for index, candidate in enumerate(self._candidates):
            if not candidate.in_workspace:
                self._list.item(index).setCheckState(state)

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
        for existing_widget in (
            self._existing_dir,
            self._existing_browse,
            self._list,
            self._select_all,
            self._select_none,
        ):
            existing_widget.setEnabled(not xml)
        error = ""
        if not xml and not self.selected_paths():
            error = NONE_SELECTED
        else:
            try:
                cli_import_commands(self.form())
            except ValueError as validation_error:  # CliQuoteError — подкласс
                error = str(validation_error)
        self._error.setText(error)
        self.ok_button().setEnabled(not error)

    def _browse_existing(self) -> None:
        chosen = self._choose_directory()
        if chosen:
            self._existing_dir.setText(chosen)
            self._rescan()

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

    def status_text(self) -> str:
        return self._status.text()

    def list_widget(self) -> QListWidget:
        return self._list

    def select_all_button(self) -> QPushButton:
        return self._select_all

    def select_none_button(self) -> QPushButton:
        return self._select_none

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
