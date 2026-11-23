"""Выбор команды пакетного режима для нового шага сценария (спека v4, §7.4)."""

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_catalog import Catalog, CatalogCommand, Effect
from onecstarter.ui.theme import DARK, Palette

NAME_ROLE = Qt.ItemDataRole.UserRole + 1
SEARCH_PLACEHOLDER = "Поиск команды: имя или слово из описания"
EFFECT_NOTES = {
    Effect.NONE: "",
    Effect.MODIFIES: "Меняет базу.",
    Effect.REPLACES: "Полностью заменяет данные базы.",
}


def run_command_picker(dialog: "CommandPicker") -> bool:
    return dialog.exec() == QDialog.DialogCode.Accepted


def describe_command(command: CatalogCommand) -> str:
    parts = [f"{command.name} — {command.summary}", command.description]
    note = EFFECT_NOTES[command.effect]
    if note:
        parts.append(note)
    if command.its:
        parts.append(f"ИТС: {command.its}")
    return "\n".join(part for part in parts if part)


class CommandPicker(QDialog):
    def __init__(
        self, catalog: Catalog, *, palette: Palette = DARK, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Добавить шаг")
        self._catalog = catalog
        self._items: dict[str, QTreeWidgetItem] = {}
        self._search = QLineEdit()
        self._search.setPlaceholderText(SEARCH_PLACEHOLDER)
        self._search.textChanged.connect(self.search)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(lambda *_: self._refresh())
        self._tree.itemDoubleClicked.connect(lambda *_: self._accept_if_chosen())
        self._description = QLabel()
        self._description.setWordWrap(True)
        self._accept = QPushButton("Добавить")
        self._accept.setAutoDefault(False)  # Enter в поиске не добавляет шаг
        self._accept.clicked.connect(self._accept_if_chosen)
        cancel = QPushButton("Отмена")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._accept)
        buttons.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._tree, 1)
        layout.addWidget(self._description)
        layout.addLayout(buttons)
        self.resize(640, 520)
        for group in sorted(catalog.groups, key=lambda g: g.order):
            commands = catalog.group_commands(group.id)
            if not commands:
                continue
            node = QTreeWidgetItem([group.title])
            node.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._tree.addTopLevelItem(node)
            for command in commands:
                child = QTreeWidgetItem([f"{command.name} — {command.summary}"])
                child.setData(0, NAME_ROLE, command.name)
                node.addChild(child)
                self._items[command.name.casefold()] = child
            node.setExpanded(True)
        self._refresh()

    def search(self, text: str) -> None:
        words = text.casefold().split()
        for name, item in self._items.items():
            command = self._catalog.command(name)
            haystack = (
                f"{name} {command.summary} {command.description}".casefold()
                if command is not None
                else name
            )
            item.setHidden(not all(word in haystack for word in words))
        for index in range(self._tree.topLevelItemCount()):
            node = self._tree.topLevelItem(index)
            if node is not None:
                node.setHidden(all(node.child(i).isHidden() for i in range(node.childCount())))
        current = self._tree.currentItem()
        parent = current.parent() if current is not None else None
        if current is not None and (current.isHidden() or (parent and parent.isHidden())):
            self._tree.setCurrentIndex(QModelIndex())
            self._refresh()

    def select(self, name: str) -> None:
        item = self._items.get(name.casefold())
        if item is not None:
            self._tree.setCurrentItem(item)

    def chosen(self) -> str | None:
        item = self._tree.currentItem()
        name = item.data(0, NAME_ROLE) if item is not None else None
        return name if isinstance(name, str) else None

    def command_names(self) -> list[str]:
        return [
            str(item.data(0, NAME_ROLE)) for item in self._items.values() if not item.isHidden()
        ]

    def description_text(self) -> str:
        return self._description.text()

    def accept_button(self) -> QPushButton:
        return self._accept

    def _refresh(self) -> None:
        name = self.chosen()
        command = self._catalog.command(name) if name is not None else None
        self._accept.setEnabled(command is not None)
        self._description.setText(describe_command(command) if command is not None else "")

    def _accept_if_chosen(self) -> None:
        if self.chosen() is not None:
            self.accept()
