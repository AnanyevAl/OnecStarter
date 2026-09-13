"""Имя группы раздела «EDT» — одно поле с русскими кнопками (спека §7)."""  # noqa: RUF002

from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box


class EdtGroupDialog(QDialog):
    def __init__(self, name: str, *, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._name = QLineEdit(name)
        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow("Имя группы", self._name)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._buttons)
        self._name.textChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self, *_args: object) -> None:
        self.ok_button().setEnabled(bool(self._name.text().strip()))

    def name_text(self) -> str:
        return self._name.text().strip()

    def name_edit(self) -> QLineEdit:
        return self._name

    def ok_button(self) -> QPushButton:
        return self._buttons.buttons()[0]  # type: ignore[return-value]
