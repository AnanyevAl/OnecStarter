"""Диалог `validate` CLI EDT (спека §14.2): перечень проектов и файл TSV."""

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt_cli import cli_validate_args
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

EXISTS_ERROR = "Файл уже существует — CLI откажет; выберите другое имя"
NO_DIR_ERROR = "Каталог результата не существует"


def browse_for_tsv(initial: str) -> str:
    """Диалог сохранения TSV; пустая строка — отмена."""
    return QFileDialog.getSaveFileName(None, "Файл результата", initial, "TSV (*.tsv)")[0]


class CliValidateDialog(QDialog):
    def __init__(
        self,
        paths: Sequence[str],
        initial_dir: str,
        default_name: str,
        *,
        choose_save: Callable[[str], str] = browse_for_tsv,
        exists: Callable[[str], bool] = os.path.exists,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Проверить проекты (CLI EDT)")
        self._paths = list(paths)
        self._exists = exists
        self._choose_save = choose_save
        self._list = QListWidget()
        for path in self._paths:
            item = QListWidgetItem(path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._refresh)
        self._file = QLineEdit(str(Path(initial_dir) / default_name))
        self._file.textChanged.connect(self._refresh)
        self._browse = QPushButton("Обзор…")
        self._browse.clicked.connect(self._pick)
        self._error = QLabel("")
        self._error.setObjectName("DialogError")
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self._file, 1)
        file_layout.addWidget(self._browse)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Проекты для проверки:"))
        layout.addWidget(self._list, 1)
        layout.addWidget(QLabel("Файл результата (TSV):"))
        layout.addWidget(file_row)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)
        self.resize(640, 420)
        self._refresh()

    def selected_paths(self) -> list[str]:
        return [
            path
            for index, path in enumerate(self._paths)
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def result_file(self) -> str:
        return self._file.text().strip()

    def _refresh(self, *_args: object) -> None:
        error = ""
        file = self.result_file()
        if not self.selected_paths():
            error = "Не выбран ни один проект"  # noqa: RUF001
        elif not file:
            error = "Укажите файл результата"
        elif self._exists(file):
            error = EXISTS_ERROR
        elif not self._exists(str(Path(file).parent)):
            # M4 ревью: каталог по умолчанию может не существовать (OneDrive KFM),
            # CLI каталог для TSV не создаёт — отказ здесь, не кодом после запуска.
            error = NO_DIR_ERROR
        else:
            try:
                cli_validate_args(self.selected_paths(), file)
            except ValueError as validation_error:  # CliQuoteError — подкласс; как в import-диалоге
                error = str(validation_error)
        self._error.setText(error)
        self.ok_button().setEnabled(not error)

    def _pick(self) -> None:
        chosen = self._choose_save(self._file.text())
        if chosen:
            self._file.setText(chosen)

    # --- доступ ---
    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]

    def error_text(self) -> str:
        return self._error.text()

    def list_widget(self) -> QListWidget:
        return self._list

    def file_edit(self) -> QLineEdit:
        return self._file

    def browse_button(self) -> QPushButton:
        return self._browse
