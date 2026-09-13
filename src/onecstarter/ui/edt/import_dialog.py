"""Импорт из EDT Start (спека v3, §6): кандидаты с галочками, все отмечены."""  # noqa: RUF002

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt import ImportCandidate
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

UNKNOWN_VERSION_MARK = "версия неизвестна"


class EdtImportDialog(QDialog):
    def __init__(
        self, candidates: Sequence[ImportCandidate], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импорт из EDT Start")
        self._candidates = list(candidates)
        self._list = QListWidget()
        for candidate in self._candidates:
            version = (
                candidate.project.edt_version
                if candidate.version_known
                else UNKNOWN_VERSION_MARK
            )
            item = QListWidgetItem(
                f"{candidate.project.name} — {candidate.project.workspace} — {version}"
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._refresh)
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Проекты EDT Start, которых ещё нет в списке:"))
        layout.addWidget(self._list, 1)
        layout.addWidget(self._buttons)
        self.resize(640, 400)
        self._refresh()

    def selected(self) -> list[ImportCandidate]:
        return [
            candidate
            for index, candidate in enumerate(self._candidates)
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _refresh(self, *_args: object) -> None:
        self.ok_button().setEnabled(bool(self.selected()))

    def list_widget(self) -> QListWidget:
        return self._list

    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]
