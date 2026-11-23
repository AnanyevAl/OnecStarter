"""Дерево баз с флажками: выбор баз для сценария (спека v4, §7.4, §7.5)."""  # noqa: RUF002

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
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

from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.operations import BaseRef
from onecstarter.services.model import InfobaseItem
from onecstarter.services.paths import ROOT, normalize_folder
from onecstarter.ui.components import bold_font, hint_label
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box
from onecstarter.ui.theme import DARK, Palette

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
NAME_ROLE = Qt.ItemDataRole.UserRole + 2
MISSING_GROUP = "Из сохранённого списка"
MISSING_NOTE = "не найдена в списке баз"
SEARCH_PLACEHOLDER = "Поиск базы"
_CHECKABLE = (
    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
)


def run_base_list_dialog(dialog: "BaseListDialog") -> bool:
    return dialog.exec() == QDialog.DialogCode.Accepted


class BaseChecklist(QWidget):
    changed = Signal()

    def __init__(
        self,
        items: Sequence[InfobaseItem],
        *,
        checked: Sequence[str] = (),
        missing: Sequence[BaseRef] = (),
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._bases: dict[str, QTreeWidgetItem] = {}
        self._groups: dict[str, QTreeWidgetItem] = {}
        self._search = QLineEdit()
        self._search.setPlaceholderText(SEARCH_PLACEHOLDER)
        self._search.textChanged.connect(self.search)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._count = hint_label()
        check_all = QPushButton("Все")  # noqa: RUF001
        uncheck_all = QPushButton("Снять")
        for button in (check_all, uncheck_all):
            button.setAutoDefault(False)
        check_all.clicked.connect(self.check_all)
        uncheck_all.clicked.connect(self.uncheck_all)
        bar = QHBoxLayout()
        bar.addWidget(check_all)
        bar.addWidget(uncheck_all)
        bar.addStretch(1)
        bar.addWidget(self._count)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search)
        layout.addWidget(self._tree, 1)
        layout.addLayout(bar)

        wanted = set(checked)
        for item in items:
            if item.is_group:
                continue
            folder = normalize_folder(item.folder)
            label = f"{item.name} · веб" if item.kind is ConnectKind.WEB else item.name
            self._add_base(
                None if folder == ROOT else folder, item.key, item.name, label, item.key in wanted
            )
        for ref in missing:
            self._add_base(
                MISSING_GROUP, ref.key, ref.name, f"{ref.name} — {MISSING_NOTE}", True, missing=True
            )
        for path in self._groups:
            self._sync_group(path)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._refresh_count()

    # -- сборка --------------------------------------------------------------

    def _add_base(
        self,
        group: str | None,
        key: str,
        name: str,
        label: str,
        on: bool,
        *,
        missing: bool = False,
    ) -> None:
        existing = self._bases.get(key)
        if existing is not None:  # база и в списке, и среди «не найденных»: отмечаем имеющуюся
            if on:
                existing.setCheckState(0, Qt.CheckState.Checked)
            return
        row = QTreeWidgetItem([label])
        row.setData(0, KEY_ROLE, key)
        row.setData(0, NAME_ROLE, name)
        row.setFlags(_CHECKABLE)
        row.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        if missing:
            row.setForeground(0, QColor(self._palette.problem))  # мокап, стр. 320
        if group is None:
            self._tree.addTopLevelItem(row)
        else:
            node = self._groups.get(group)
            if node is None:
                node = QTreeWidgetItem([group])
                node.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                node.setFont(0, bold_font(self._tree.font()))  # мокап `.tree .g`
                node.setCheckState(0, Qt.CheckState.Unchecked)
                self._tree.addTopLevelItem(node)
                node.setExpanded(True)
                self._groups[group] = node
            node.addChild(row)
        self._bases[key] = row

    # -- чтение --------------------------------------------------------------

    def all_keys(self) -> list[str]:
        """Ключи баз в порядке показа: корневые и группы — как в дереве."""
        keys: list[str] = []
        for index in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(index)
            if top is None:
                continue
            rows = (
                [top] if top.childCount() == 0 else [top.child(i) for i in range(top.childCount())]
            )
            for row in rows:
                key = row.data(0, KEY_ROLE)
                if isinstance(key, str):
                    keys.append(key)
        return keys

    def visible_keys(self) -> list[str]:
        return [key for key in self.all_keys() if not self._bases[key].isHidden()]

    def checked_keys(self) -> list[str]:
        return [
            key
            for key in self.all_keys()
            if self._bases[key].checkState(0) == Qt.CheckState.Checked
        ]

    def checked_refs(self) -> list[BaseRef]:
        return [
            BaseRef(key, str(self._bases[key].data(0, NAME_ROLE))) for key in self.checked_keys()
        ]

    def base_labels(self) -> list[str]:
        return [self._bases[key].text(0) for key in self.all_keys()]

    def group_paths(self) -> list[str]:
        return list(self._groups)

    def group_keys(self, path: str) -> list[str]:
        node = self._groups[path]
        return [str(node.child(i).data(0, KEY_ROLE)) for i in range(node.childCount())]

    def group_state(self, path: str) -> Qt.CheckState:
        return self._groups[path].checkState(0)

    def group_item(self, path: str) -> QTreeWidgetItem:
        return self._groups[path]

    def base_item(self, key: str) -> QTreeWidgetItem:
        return self._bases[key]

    def count_label(self) -> QLabel:
        return self._count

    def count_text(self) -> str:
        return self._count.text()

    # -- правка --------------------------------------------------------------

    def set_checked(self, key: str, on: bool) -> None:
        row = self._bases.get(key)
        if row is not None:
            row.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def set_group_checked(self, path: str, on: bool) -> None:
        self._groups[path].setCheckState(
            0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        )

    def check_all(self) -> None:
        self._set_visible(True)

    def uncheck_all(self) -> None:
        self._set_visible(False)

    def search(self, text: str) -> None:
        needle = text.strip().casefold()
        for row in self._bases.values():
            name = str(row.data(0, NAME_ROLE))
            row.setHidden(bool(needle) and needle not in name.casefold())
        self._tree.blockSignals(True)
        for node in self._groups.values():
            node.setHidden(all(node.child(i).isHidden() for i in range(node.childCount())))
        for path in self._groups:
            self._sync_group(path)
        self._tree.blockSignals(False)

    # -- внутреннее ----------------------------------------------------------

    def _set_visible(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        self._tree.blockSignals(True)
        for key in self.visible_keys():
            self._bases[key].setCheckState(0, state)
        for path in self._groups:
            self._sync_group(path)
        self._tree.blockSignals(False)
        self._refresh_count()
        self.changed.emit()

    def _sync_group(self, path: str) -> None:
        node = self._groups[path]
        children = [node.child(i) for i in range(node.childCount())]
        shown = [child for child in children if not child.isHidden()]
        # при поиске состояние группы — по видимым базам (скрытые ей не подчиняются)
        states = {child.checkState(0) for child in (shown or children)}
        if states == {Qt.CheckState.Checked}:
            state = Qt.CheckState.Checked
        elif Qt.CheckState.Checked in states:
            state = Qt.CheckState.PartiallyChecked
        else:
            state = Qt.CheckState.Unchecked
        node.setCheckState(0, state)

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        self._tree.blockSignals(True)
        if item.data(0, KEY_ROLE) is None:  # узел группы: состояние уходит её базам
            if item.checkState(0) != Qt.CheckState.PartiallyChecked:
                for index in range(item.childCount()):
                    child = item.child(index)
                    if not child.isHidden():
                        child.setCheckState(0, item.checkState(0))
        for path in self._groups:
            self._sync_group(path)
        self._tree.blockSignals(False)
        self._refresh_count()
        self.changed.emit()

    def _refresh_count(self) -> None:
        self._count.setText(f"отмечено {len(self.checked_keys())}")


class BaseListDialog(QDialog):
    def __init__(
        self,
        items: Sequence[InfobaseItem],
        *,
        checked: Sequence[str] = (),
        missing: Sequence[BaseRef] = (),
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Список баз сценария")
        self._checklist = BaseChecklist(
            items, checked=checked, missing=missing, palette=palette
        )
        buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        for button in buttons.buttons():
            if isinstance(button, QPushButton):
                button.setAutoDefault(False)  # Enter в поиске не закрывает окно
        layout = QVBoxLayout(self)
        layout.addWidget(self._checklist, 1)
        layout.addWidget(buttons)
        self.resize(420, 520)

    def checklist(self) -> BaseChecklist:
        return self._checklist
