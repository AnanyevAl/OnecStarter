"""Диалог записи раздела «EDT» (спека v3, §7).

Хранится одна строка `vm_args`; память и язык — фасады над ней
(`domain.edt.split_vm_args`/`join_vm_args`), как «Отредактировать как
параметры Java VM…» у EDT Start. Проверки до сохранения: имя и workspace
непусты, workspace абсолютен, память — целое (пусто — без `-Xmx`).
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt import (
    LANGUAGES,
    EdtInstallation,
    EdtProject,
    join_vm_args,
    split_vm_args,
)
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

HEAP_CHOICES = (2048, 4096, 8192, 12288, 16384)
NOT_INSTALLED_MARK = " (не установлена)"
_HEAP_ERROR = "Память — целое число мегабайт"


@dataclass(frozen=True)
class DialogDefaults:
    max_heap_mb: int
    language: str
    group_id: str | None


def browse_for_directory() -> str:
    """Системный диалог каталога; пустая строка — отмена (как в `ui/servers/dialog.py`)."""
    return QFileDialog.getExistingDirectory()


class EdtProjectDialog(QDialog):
    def __init__(
        self,
        project: EdtProject | None,
        installed: Sequence[EdtInstallation],
        *,
        defaults: DialogDefaults,
        choose_directory: Callable[[], str] = browse_for_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._installed = list(installed)
        self._defaults = defaults
        self._choose_directory = choose_directory
        self.setWindowTitle(f"Проект EDT — {project.name}" if project else "Новый проект EDT")

        self._name = QLineEdit(project.name if project else "")
        self._workspace = QLineEdit(project.workspace if project else "")
        self._workspace_browse = QPushButton("Обзор…")
        self._workspace_browse.clicked.connect(lambda: self._browse_into(self._workspace))
        self._project_dir = QLineEdit(project.project_dir if project else "")
        self._project_dir.setPlaceholderText("пусто — редакторы получают workspace")
        self._project_dir_browse = QPushButton("Обзор…")
        self._project_dir_browse.clicked.connect(lambda: self._browse_into(self._project_dir))

        self._version = QComboBox()
        for installation in self._installed:
            self._version.addItem(installation.version, installation.version)
        current = project.edt_version if project else ""
        if current and self._version.findData(current) < 0:
            self._version.addItem(current + NOT_INSTALLED_MARK, current)
        if current:
            self._version.setCurrentIndex(self._version.findData(current))
        self._version.currentIndexChanged.connect(self._refresh_jvm_note)

        self._jvm = QLineEdit(project.jvm_dir if project else "")
        self._jvm.setPlaceholderText("пусто — JVM установки")
        self._jvm_browse = QPushButton("Обзор…")
        self._jvm_browse.clicked.connect(lambda: self._browse_into(self._jvm))
        self._jvm_note = QLabel("")
        self._jvm_note.setObjectName("SettingsNote")

        parts = split_vm_args(project.vm_args) if project else None
        self._heap = QComboBox()
        self._heap.setEditable(True)
        for choice in HEAP_CHOICES:
            self._heap.addItem(str(choice))
        heap = parts.max_heap_mb if parts else defaults.max_heap_mb
        self._heap.setCurrentText("" if heap is None else str(heap))
        self._heap.currentTextChanged.connect(self._refresh_state)

        self._language = QComboBox()
        for code, label in LANGUAGES:
            self._language.addItem(label, code)
        language = (parts.language if parts else defaults.language) or ""
        index = self._language.findData(language)
        self._language.setCurrentIndex(index if index >= 0 else 0)

        self._extra = QLineEdit(" ".join(parts.rest) if parts else "")
        self._extra.setPlaceholderText("прочие параметры JVM")

        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Имя", self._name)
        form.addRow("Workspace", self._with_browse(self._workspace, self._workspace_browse))
        form.addRow(
            "Каталог проекта", self._with_browse(self._project_dir, self._project_dir_browse)
        )
        form.addRow("Версия EDT", self._version)
        form.addRow("JVM (каталог bin)", self._with_browse(self._jvm, self._jvm_browse))
        form.addRow("", self._jvm_note)
        heap_row = QWidget()
        heap_layout = QHBoxLayout(heap_row)
        heap_layout.setContentsMargins(0, 0, 0, 0)
        heap_layout.addWidget(self._heap, 1)
        heap_layout.addWidget(QLabel("МБ"))
        form.addRow("Память", heap_row)
        form.addRow("Язык интерфейса", self._language)
        form.addRow("Прочие параметры JVM", self._extra)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)

        for edit in (self._name, self._workspace):
            edit.textChanged.connect(self._refresh_state)
        self._refresh_jvm_note()
        self._refresh_state()

    # --- результат --------------------------------------------------------

    def result_project(self) -> EdtProject:
        heap_text = self._heap.currentText().strip()
        heap = int(heap_text) if heap_text else None
        return EdtProject(
            id=self._project.id if self._project else "",
            name=self._name.text().strip(),
            workspace=self._workspace.text().strip(),
            project_dir=self._project_dir.text().strip(),
            edt_version=str(self._version.currentData() or ""),
            jvm_dir=self._jvm.text().strip(),
            vm_args=join_vm_args(
                heap, str(self._language.currentData() or ""), self._extra.text().split()
            ),
            group_id=self._project.group_id if self._project else self._defaults.group_id,
        )

    # --- состояние --------------------------------------------------------

    def _refresh_state(self, *_args: object) -> None:
        self._error.setText(self._error_for_fields())
        self._buttons.buttons()[0].setEnabled(not self._error.text())

    def _error_for_fields(self) -> str:
        if not self._name.text().strip():
            return "Имя не задано"
        workspace = self._workspace.text().strip()
        if not workspace:
            return "Workspace не задан"
        if not Path(workspace).is_absolute():
            return "Путь workspace должен быть абсолютным"
        heap = self._heap.currentText().strip()
        if heap and not heap.isdigit():
            return _HEAP_ERROR
        return ""

    def _refresh_jvm_note(self, *_args: object) -> None:
        version = self._version.currentData()
        for installation in self._installed:
            if installation.version == version:
                if installation.jvm_dir is None:
                    self._jvm_note.setText("JVM установки: не найдена")
                else:
                    self._jvm_note.setText(
                        f"JVM установки: {installation.jvm_dir} ({installation.jvm_source})"
                    )
                return
        self._jvm_note.setText("JVM установки: не найдена")

    def _browse_into(self, edit: QLineEdit) -> None:
        chosen = self._choose_directory()
        if chosen:
            edit.setText(chosen)

    @staticmethod
    def _with_browse(edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    # --- доступ для тестов ------------------------------------------------

    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]

    def error_text(self) -> str:
        return self._error.text()

    def name_edit(self) -> QLineEdit:
        return self._name

    def workspace_edit(self) -> QLineEdit:
        return self._workspace

    def workspace_browse(self) -> QPushButton:
        return self._workspace_browse

    def project_dir_edit(self) -> QLineEdit:
        return self._project_dir

    def version_combo(self) -> QComboBox:
        return self._version

    def jvm_edit(self) -> QLineEdit:
        return self._jvm

    def jvm_note(self) -> QLabel:
        return self._jvm_note

    def heap_combo(self) -> QComboBox:
        return self._heap

    def language_combo(self) -> QComboBox:
        return self._language

    def extra_edit(self) -> QLineEdit:
        return self._extra
