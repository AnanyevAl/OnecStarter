"""Раздел «EDT» (спека v3, §7): дерево записей и групп, фильтр, запуск, статус.

Контекстное меню, диалоги и перетаскивание — Task 15–17; здесь каркас:
модель собирается заново из координатора (`rebuild`), раскрытие групп
переживает перестройку по id группы, Enter в поиске запускает первую
видимую запись — тот же приём, что у `BasesView`.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QKeyEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt import EdtInstallation
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.services.errors import ServicesError
from onecstarter.ui.edt.tree_model import ID_ROLE, KIND_PROJECT, KIND_ROLE, build_edt_model
from onecstarter.ui.theme import Palette


class _EdtTree(QTreeView):
    def __init__(self, view: "EdtView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._view._launch_index(self.currentIndex())
            return
        if event.key() == Qt.Key.Key_F5:
            self._view.refresh_all()
            return
        super().keyPressEvent(event)


class EdtView(QWidget):
    def __init__(
        self,
        workspace: EdtWorkspace,
        *,
        palette: Palette,
        request_scan: Callable[[], None] = lambda: None,
        request_discover: Callable[[], None] = lambda: None,
        show_error: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._palette = palette
        self._request_scan = request_scan
        self._request_discover = request_discover
        self._show_error = show_error or self._default_show_error
        self._model = QStandardItemModel()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск: начните вводить имя проекта")
        self._search.textChanged.connect(lambda _text: self.rebuild())
        self._search.returnPressed.connect(self._launch_first_visible)

        self._banner = QWidget()
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_label = QLabel("Список пуст. Импортировать из EDT Start?")
        self._banner_button = QPushButton("Импортировать…")
        banner_layout.addWidget(self._banner_label, 1)
        banner_layout.addWidget(self._banner_button)
        self._banner.hide()

        self._tree = _EdtTree(self)
        self._tree.setHeaderHidden(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setRootIsDecorated(True)
        self._tree.doubleClicked.connect(self._launch_index)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._banner)
        layout.addWidget(self._tree, 1)
        self.rebuild()

    # --- доступ -----------------------------------------------------------

    def workspace(self) -> EdtWorkspace:
        return self._workspace

    def model(self) -> QStandardItemModel:
        return self._model

    def tree(self) -> QTreeView:
        return self._tree

    def search(self) -> QLineEdit:
        return self._search

    def banner(self) -> QWidget:
        return self._banner

    def banner_button(self) -> QPushButton:
        return self._banner_button

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def current(self) -> tuple[str, str] | None:
        index = self._tree.currentIndex()
        if not index.isValid():
            return None
        kind = index.siblingAtColumn(0).data(KIND_ROLE)
        item_id = index.siblingAtColumn(0).data(ID_ROLE)
        if isinstance(kind, str) and isinstance(item_id, str):
            return kind, item_id
        return None

    # --- перестройка ------------------------------------------------------

    def rebuild(self) -> None:
        expanded = self._expanded_ids()
        first_build = self._model.rowCount() == 0 and not expanded
        self._model = build_edt_model(self._workspace, self._search.text(), self._palette)
        self._tree.setModel(self._model)
        self._tree.setColumnWidth(0, 320)
        self._tree.setColumnWidth(1, 110)
        self._restore_expansion(expanded, expand_all=first_build)
        self._banner.setVisible(
            not self._workspace.projects() and self._workspace.edtstart_available()
        )

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.rebuild()

    def on_scan(self, scan: EdtScan) -> None:
        self._workspace.apply_scan(scan)
        self.rebuild()

    def on_installations(self, installations: Sequence[EdtInstallation]) -> None:
        self._workspace.set_installations(installations)
        self.rebuild()

    def refresh_all(self) -> None:
        self._request_discover()
        self._request_scan()

    # --- запуск -----------------------------------------------------------

    def launch_id(self, project_id: str) -> None:
        try:
            self._workspace.launch(project_id)
        except ServicesError as error:
            self._show_error(str(error))
            return
        self._request_scan()

    def _launch_index(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        first = index.siblingAtColumn(0)
        if first.data(KIND_ROLE) == KIND_PROJECT:
            self.launch_id(first.data(ID_ROLE))

    def _launch_first_visible(self) -> None:
        first = self._first_project(QModelIndex())
        if first is not None:
            self.launch_id(first)

    def _first_project(self, parent: QModelIndex) -> str | None:
        for row in range(self._model.rowCount(parent)):
            index = self._model.index(row, 0, parent)
            if index.data(KIND_ROLE) == KIND_PROJECT:
                item_id = index.data(ID_ROLE)
                return item_id if isinstance(item_id, str) else None
            found = self._first_project(index)
            if found is not None:
                return found
        return None

    # --- раскрытие --------------------------------------------------------

    def _expanded_ids(self) -> set[str]:
        ids: set[str] = set()

        def walk(parent: QModelIndex) -> None:
            for row in range(self._model.rowCount(parent)):
                index = self._model.index(row, 0, parent)
                if self._tree.isExpanded(index):
                    ids.add(index.data(ID_ROLE))
                walk(index)

        walk(QModelIndex())
        return ids

    def _restore_expansion(self, ids: set[str], *, expand_all: bool) -> None:
        def walk(parent: QModelIndex) -> None:
            for row in range(self._model.rowCount(parent)):
                index = self._model.index(row, 0, parent)
                if expand_all or index.data(ID_ROLE) in ids:
                    self._tree.expand(index)
                walk(index)

        walk(QModelIndex())

    def _default_show_error(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()
