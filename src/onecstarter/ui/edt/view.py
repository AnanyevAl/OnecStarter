"""Раздел «EDT» (спека v3, §7): дерево записей и групп, фильтр, запуск, статус.

Контекстное меню, диалоги и перетаскивание — Task 15–17; здесь каркас:
модель собирается заново из координатора (`rebuild`), раскрытие групп
переживает перестройку по id группы, Enter в поиске запускает первую
видимую запись — тот же приём, что у `BasesView`.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, Qt
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.platform_1c.editors import EDITOR_LABELS, EditorKind
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.services.errors import ServicesError
from onecstarter.ui.bases.panel import open_in_explorer
from onecstarter.ui.dialogs.buttons import ask_confirmation
from onecstarter.ui.dialogs.infobase import dropped_directory
from onecstarter.ui.edt.dialog import DialogDefaults, EdtProjectDialog, browse_for_directory
from onecstarter.ui.edt.group_dialog import EdtGroupDialog
from onecstarter.ui.edt.import_dialog import EdtImportDialog
from onecstarter.ui.edt.panel import EdtPanel
from onecstarter.ui.edt.tree_model import (
    COLUMNS,
    ID_ROLE,
    KIND_GROUP,
    KIND_PROJECT,
    KIND_ROLE,
    build_edt_model,
)
from onecstarter.ui.theme import Palette

MENU_OPEN_EDT = "Открыть в EDT"
MENU_OPEN_EXPLORER = "Открыть в Проводнике"
MENU_ADD = "Добавить…"
MENU_EDIT = "Изменить…"
MENU_REMOVE = "Удалить"
MENU_ADD_GROUP = "Создать группу"
MENU_RENAME_GROUP = "Переименовать группу"
MENU_REMOVE_GROUP = "Удалить группу"
MENU_IMPORT = "Импорт из EDT Start…"
NOT_INSTALLED_HINT = "EDT {version} не найден"


class DropTarget(Enum):
    BEFORE = "before"
    INTO = "into"
    AFTER = "after"


class _RightDecorationDelegate(QStyledItemDelegate):
    """Значок состояния — справа от имени, а не слева, как у Qt по умолчанию.

    Ставится только на колонку 0 (имя) — `_EdtTree.__init__`,
    `setItemDelegateForColumn(0, ...)`; колонка версии использует делегат Qt
    по умолчанию.
    """  # noqa: RUF002

    def initStyleOption(  # noqa: N802
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Right


class _EdtTree(QTreeView):
    def __init__(self, view: "EdtView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._view._show_menu)
        self.setItemDelegateForColumn(0, _RightDecorationDelegate(self))
        # Ревью Task 21: с удалением третьей колонки «EDT» стала последней и по  # noqa: RUF003
        # умолчанию наследует растяжение Qt (`stretchLastSection`) — версия
        # раздувалась бы на всю оставшуюся ширину показанного окна, а ручная  # noqa: RUF003
        # ширина колонки терялась молча. Ни одна из колонок здесь декоративная,
        # обеим нужна управляемая ширина.
        self.header().setStretchLastSection(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._view._launch_index(self.currentIndex())
            return
        if event.key() == Qt.Key.Key_F5:
            self._view.refresh_all()
            return
        if event.key() == Qt.Key.Key_Delete:
            self._view._remove_current()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        position = event.position().toPoint()
        index = self.indexAt(position)
        target = self._row_at(index)
        directory = dropped_directory(event.mimeData())
        if directory is not None:
            self._view.add_project_from_directory(directory, target)
            event.acceptProposedAction()
            return
        source = self._row_at(self.currentIndex())
        if source is not None:
            self._view.handle_drop(source, target, self._where_at(index, position.y()))
        event.ignore()

    @staticmethod
    def _row_at(index: QModelIndex) -> tuple[str, str] | None:
        if not index.isValid():
            return None
        first = index.siblingAtColumn(0)
        kind, item_id = first.data(KIND_ROLE), first.data(ID_ROLE)
        return (kind, item_id) if isinstance(kind, str) and isinstance(item_id, str) else None

    def _where_at(self, index: QModelIndex, y: int) -> DropTarget:
        if not index.isValid():
            return DropTarget.INTO
        rect = self.visualRect(index)
        margin = max(1, rect.height() // 4)
        if y - rect.top() < margin:
            return DropTarget.BEFORE
        if rect.bottom() - y < margin:
            return DropTarget.AFTER
        return DropTarget.INTO


class EdtView(QWidget):
    def __init__(
        self,
        workspace: EdtWorkspace,
        *,
        palette: Palette,
        request_scan: Callable[[], None] = lambda: None,
        request_discover: Callable[[], None] = lambda: None,
        show_error: Callable[[str], None] | None = None,
        show_info: Callable[[str], None] | None = None,
        dialog_defaults: Callable[[], tuple[int, str]] = lambda: (8192, ""),
        confirm: Callable[[QWidget, str, str], bool] = ask_confirmation,
        choose_directory: Callable[[], str] = browse_for_directory,
        open_directory: Callable[[str], bool] = open_in_explorer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._palette = palette
        self._request_scan = request_scan
        self._request_discover = request_discover
        self._show_error = show_error or self._default_show_error
        self._show_info = show_info or self._default_show_info
        self._dialog_defaults = dialog_defaults
        self._confirm = confirm
        self._choose_directory = choose_directory
        self._model = QStandardItemModel()
        self._built = False  # первая сборка раскрывает всё; дальше — по запомненным id
        self._last_scan: EdtScan | None = None  # последний применённый снимок монитора

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск: начните вводить имя проекта")
        self._search.textChanged.connect(lambda _text: self.rebuild())
        self._search.returnPressed.connect(self._launch_first_visible)

        self._banner = QWidget()
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_label = QLabel("Список пуст. Импортировать из EDT Start?")
        self._banner_button = QPushButton("Импортировать…")
        self._banner_button.clicked.connect(self.import_from_edtstart)
        banner_layout.addWidget(self._banner_label, 1)
        banner_layout.addWidget(self._banner_button)
        self._banner.hide()

        self._tree = _EdtTree(self)
        self._tree.setHeaderHidden(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setRootIsDecorated(True)
        self._tree.doubleClicked.connect(self._launch_index)

        self._panel = EdtPanel(open_directory=open_directory)
        self._panel.open_failed.connect(self._show_error)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._banner)
        layout.addWidget(self._tree, 1)
        layout.addWidget(self._panel)
        self.rebuild()

    # --- доступ -----------------------------------------------------------

    def workspace(self) -> EdtWorkspace:
        return self._workspace

    def model(self) -> QStandardItemModel:
        return self._model

    def tree(self) -> QTreeView:
        return self._tree

    def panel(self) -> EdtPanel:
        return self._panel

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

    def _on_current_changed(self, *_args: object) -> None:
        """Общий слот текущей строки: панель путей сегодня, консоль — план 2."""
        self._sync_panel()

    def _sync_panel(self) -> None:
        current = self.current()
        if current is None:
            self._panel.show_nothing()
            return
        kind, item_id = current
        if kind == KIND_PROJECT:
            self._panel.show_project(self._workspace.project(item_id), self._palette)
        elif kind == KIND_GROUP:
            group = next(g for g in self._workspace.groups() if g.id == item_id)
            self._panel.show_group(group.name)
        else:
            self._panel.show_nothing()

    # --- перестройка ------------------------------------------------------

    def rebuild(self) -> None:
        """Собрать модель заново, сохранив раскрытие, текущую строку и ширины колонок.

        `setModel` сбрасывает всё это — ширины по умолчанию ставятся только
        при первой сборке, дальше возвращаются снятые перед подменой (I2
        финального ревью ветки). Последняя колонка растянута заголовком,
        её ширина не запоминается.
        """
        expanded = self._expanded_ids()
        current = self.current()
        widths = [self._tree.columnWidth(column) for column in range(len(COLUMNS) - 1)]
        self._model = build_edt_model(self._workspace, self._search.text(), self._palette)
        self._tree.setModel(self._model)
        if not self._built:
            self._tree.setColumnWidth(0, 320)
            self._tree.setColumnWidth(1, 110)
        else:
            for column, width in enumerate(widths):
                self._tree.setColumnWidth(column, width)
        self._restore_expansion(expanded, expand_all=not self._built)
        self._restore_current(current)
        # Модель пересобрана целиком — прежняя selectionModel умерла вместе
        # с ней, подписку нельзя ставить один раз в __init__ (там модели ещё  # noqa: RUF003
        # нет вовсе): переподключаемся здесь и сразу синхронизируем панель
        # (тот же приём, что `BasesView.rebuild`).
        selection = self._tree.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(self._on_current_changed)
        self._on_current_changed()
        self._built = True
        self._banner.setVisible(
            not self._workspace.projects() and self._workspace.edtstart_available()
        )

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.rebuild()

    def on_scan(self, scan: EdtScan) -> None:
        """Снимок монитора: применить всегда, перестраивать — только если он изменился.

        Тик каждые пять секунд с тем же содержимым иначе сбрасывал бы текущую
        строку и рвал начатое перетаскивание (I2 финального ревью ветки).
        """  # noqa: RUF002
        self._workspace.apply_scan(scan)
        if scan == self._last_scan:
            return
        self._last_scan = scan
        self.rebuild()

    def on_installations(self, installations: Sequence[EdtInstallation]) -> None:
        self._workspace.set_installations(installations)
        self.rebuild()

    def refresh_all(self) -> None:
        self._request_discover()
        self._request_scan()

    def import_from_edtstart(self) -> None:
        candidates = self._workspace.import_candidates()
        if candidates is None:
            self._show_error(
                "EDT Start не найден: реестр %LOCALAPPDATA%\\1C\\1cedtstart не читается"
            )
            return
        if not candidates:
            self._show_info("Новых проектов в EDT Start нет")
            return
        dialog = EdtImportDialog(candidates, parent=self)
        if not self._run_dialog(dialog):
            return
        added = self._workspace.import_projects(dialog.selected())
        self.rebuild()
        message = f"Импортировано записей: {added}"
        skipped = self._workspace.edtstart_skipped()
        if skipped:
            message += f"\nПропущено записей EDT Start без пути или продукта: {skipped}"  # noqa: RUF001
        self._show_info(message)

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

    def _restore_current(self, current: tuple[str, str] | None) -> None:
        if current is None:
            return
        kind, item_id = current

        def find(parent: QModelIndex) -> QModelIndex | None:
            for row in range(self._model.rowCount(parent)):
                index = self._model.index(row, 0, parent)
                if index.data(KIND_ROLE) == kind and index.data(ID_ROLE) == item_id:
                    return index
                found = find(index)
                if found is not None:
                    return found
            return None

        index = find(QModelIndex())
        if index is not None:
            self._tree.setCurrentIndex(index)

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

    def _default_show_info(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()

    # --- меню ---------------------------------------------------------------

    def build_menu(self, kind: str | None, item_id: str | None) -> QMenu:
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if kind == KIND_PROJECT and item_id is not None:
            self._fill_project_menu(menu, self._workspace.project(item_id))
            menu.addSeparator()
            group_id = self._workspace.project(item_id).group_id
        elif kind == KIND_GROUP and item_id is not None:
            group_id = item_id
        else:
            group_id = None
        menu.addAction(MENU_ADD, lambda: self.add_project(group_id))
        if kind == KIND_PROJECT and item_id is not None:
            menu.addAction(MENU_EDIT, lambda: self.edit_project(item_id))
            menu.addAction(MENU_REMOVE, lambda: self.remove_project(item_id))
        menu.addSeparator()
        menu.addAction(MENU_ADD_GROUP, lambda: self.add_group(group_id))
        if kind == KIND_GROUP and item_id is not None:
            menu.addAction(MENU_RENAME_GROUP, lambda: self.rename_group(item_id))
            menu.addAction(MENU_REMOVE_GROUP, lambda: self.remove_group(item_id))
        if kind != KIND_GROUP:
            menu.addSeparator()
            menu.addAction(MENU_IMPORT, self.import_from_edtstart)
        return menu

    def _fill_project_menu(self, menu: QMenu, project: EdtProject) -> None:
        status = self._workspace.status(project.id)
        open_edt = menu.addAction(MENU_OPEN_EDT, lambda: self.launch_id(project.id))
        if not status.installed and status.running_pid is None:
            open_edt.setEnabled(False)
            open_edt.setToolTip(NOT_INSTALLED_HINT.format(version=project.edt_version or "—"))
        for kind in EditorKind:
            resolution = self._workspace.editor(kind)
            action: QAction = menu.addAction(
                f"Открыть в {EDITOR_LABELS[kind]}",
                lambda k=kind: self.open_in_editor(project.id, k),
            )
            if resolution.path is None:
                action.setEnabled(False)
                action.setToolTip(resolution.note)
        menu.addAction(MENU_OPEN_EXPLORER, lambda: self.open_folder(project.id))

    def _show_menu(self, position: QPoint) -> None:
        index = self._tree.indexAt(position)
        row = _EdtTree._row_at(index)
        if row is not None:
            self._tree.setCurrentIndex(index)
        menu = self.build_menu(*(row or (None, None)))
        menu.exec(self._tree.viewport().mapToGlobal(position))

    # --- операции -------------------------------------------------------------

    def _run_dialog(self, dialog: QDialog) -> bool:
        """Точка подмены для тестов: показать модально, вернуть «принят»."""
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _defaults(self, group_id: str | None) -> DialogDefaults:
        heap, language = self._dialog_defaults()
        return DialogDefaults(max_heap_mb=heap, language=language, group_id=group_id)

    def add_project(self, group_id: str | None, workspace: str = "") -> None:
        dialog = EdtProjectDialog(
            None,
            self._workspace.installations(),
            defaults=self._defaults(group_id),
            choose_directory=self._choose_directory,
            parent=self,
        )
        if workspace:
            dialog.workspace_edit().setText(workspace)
            dialog.name_edit().setText(Path(workspace).name)
        if not self._run_dialog(dialog):
            return
        self._apply(lambda: self._workspace.add_project(dialog.result_project()))

    def add_project_from_directory(self, directory: str, target: tuple[str, str] | None) -> None:
        self.add_project(self._group_of(target), directory)

    def edit_project(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        dialog = EdtProjectDialog(
            project,
            self._workspace.installations(),
            defaults=self._defaults(project.group_id),
            choose_directory=self._choose_directory,
            parent=self,
        )
        if self._run_dialog(dialog):
            self._apply(lambda: self._workspace.update_project(dialog.result_project()))

    def remove_project(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        question = f"Удалить запись «{project.name}»? Каталоги на диске не трогаются."
        if self._confirm(self, "Удаление записи", question):
            self._apply(lambda: self._workspace.remove_project(project_id))

    def add_group(self, parent_id: str | None) -> None:
        dialog = EdtGroupDialog("", title="Новая группа", parent=self)
        if self._run_dialog(dialog):
            self._apply(lambda: self._workspace.add_group(dialog.name_text(), parent_id))

    def rename_group(self, group_id: str) -> None:
        current = next(g for g in self._workspace.groups() if g.id == group_id)
        dialog = EdtGroupDialog(current.name, title="Переименование группы", parent=self)
        if self._run_dialog(dialog):
            self._apply(lambda: self._workspace.rename_group(group_id, dialog.name_text()))

    def remove_group(self, group_id: str) -> None:
        current = next(g for g in self._workspace.groups() if g.id == group_id)
        question = f"Удалить группу «{current.name}»? Её содержимое поднимется на уровень выше."
        if self._confirm(self, "Удаление группы", question):
            self._apply(lambda: self._workspace.remove_group(group_id))

    def open_in_editor(self, project_id: str, kind: EditorKind) -> None:
        self._apply(lambda: self._workspace.open_in_editor(project_id, kind), rebuild=False)

    def open_folder(self, project_id: str) -> None:
        self._apply(lambda: self._workspace.open_folder(project_id), rebuild=False)

    def handle_drop(
        self,
        source: tuple[str, str],
        target: tuple[str, str] | None,
        where: DropTarget,
    ) -> None:
        """Перевод «куда бросили» в `move_project`/`move_group` координатора.

        Позиция считается среди соседей того же вида: запись, брошенная
        относительно группы, встаёт первой в родителе этой группы; группа,
        брошенная относительно записи, — последней в группе этой записи.
        """
        kind, item_id = source
        if target is not None and target == source:
            return
        parent, position = self._drop_slot(kind, item_id, target, where)
        if kind == KIND_PROJECT:
            self._apply(lambda: self._workspace.move_project(item_id, parent, position))
        else:
            self._apply(lambda: self._workspace.move_group(item_id, parent, position))

    def _drop_slot(
        self,
        kind: str,
        item_id: str,
        target: tuple[str, str] | None,
        where: DropTarget,
    ) -> tuple[str | None, int]:
        """Родитель и позиция среди соседей того же вида.

        Координатор сперва вынимает источник из списка, поэтому при переносе
        вниз внутри одного родителя позиция цели сдвигается на единицу —
        учтено через `ids.index(item_id) < index`.
        """
        end = 1_000_000
        if target is None:
            return None, end
        target_kind, target_id = target
        if target_kind == KIND_GROUP:
            if where is DropTarget.INTO:
                return target_id, end
            group = next(g for g in self._workspace.groups() if g.id == target_id)
            if kind != KIND_GROUP:
                return group.parent_id, 0
            ids = [g.id for g in self._workspace.children(group.parent_id)[0]]
            parent = group.parent_id
        else:
            project = self._workspace.project(target_id)
            if kind != KIND_PROJECT:
                return project.group_id, end
            ids = [p.id for p in self._workspace.children(project.group_id)[1]]
            parent = project.group_id
        index = ids.index(target_id)
        position = index + (0 if where is DropTarget.BEFORE else 1)
        if item_id in ids and ids.index(item_id) < index:
            position -= 1
        return parent, position

    def _group_of(self, target: tuple[str, str] | None) -> str | None:
        if target is None:
            return None
        kind, item_id = target
        if kind == KIND_GROUP:
            return item_id
        return self._workspace.project(item_id).group_id

    def _remove_current(self) -> None:
        current = self.current()
        if current is None:
            return
        kind, item_id = current
        if kind == KIND_PROJECT:
            self.remove_project(item_id)
        else:
            self.remove_group(item_id)

    def _apply(self, operation: Callable[[], object], *, rebuild: bool = True) -> None:
        try:
            operation()
        except ServicesError as error:
            self._show_error(str(error))
            return
        if rebuild:
            self.rebuild()
