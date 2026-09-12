"""Раздел «EDT» (спека v3, §7): дерево записей и групп, фильтр, запуск, статус.

Контекстное меню, диалоги и перетаскивание — Task 15–17; здесь каркас:
модель собирается заново из координатора (`rebuild`), раскрытие групп
переживает перестройку по id группы, Enter в поиске запускает первую
видимую запись — тот же приём, что у `BasesView`.

План 2 (спека §14): подменю «CLI» записи и консоль под деревом. Команду
запускает `EdtCli`, код завершения приносит `CliWatcher` сигналом в главный
поток (`on_cli_finished`); консоль показывает журнал выбранной записи, не
раскрываясь сама (§14.5), и раскрывается только при запуске команды.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from datetime import datetime
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
from onecstarter.domain.edt_cli import (
    cli_build_args,
    cli_import_args,
    cli_project_args,
    cli_validate_args,
    workspace_projects,
)
from onecstarter.platform_1c.editors import EDITOR_LABELS, EditorKind
from onecstarter.services.edt import EdtScan, EdtWorkspace
from onecstarter.services.edt_cli import EdtCli, workspace_entries
from onecstarter.services.errors import ServicesError
from onecstarter.ui.bases.panel import open_in_explorer
from onecstarter.ui.dialogs.buttons import ask_confirmation
from onecstarter.ui.dialogs.infobase import dropped_directory
from onecstarter.ui.edt.cli_import_dialog import CliImportDialog
from onecstarter.ui.edt.cli_validate_dialog import CliValidateDialog
from onecstarter.ui.edt.cli_watch import CliWatcher
from onecstarter.ui.edt.console_panel import (
    STATE_INTERRUPTED,
    STATE_NOT_STARTED,
    STATE_RUNNING,
    EdtConsole,
    state_finished,
)
from onecstarter.ui.edt.dialog import DialogDefaults, EdtProjectDialog, browse_for_directory
from onecstarter.ui.edt.group_dialog import EdtGroupDialog
from onecstarter.ui.edt.import_dialog import EdtImportDialog
from onecstarter.ui.edt.panel import EdtPanel
from onecstarter.ui.edt.tree_model import CLI_BUSY_HINT as CLI_BUSY_HINT
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
MENU_CLI = "CLI"
CLI_BUILD = "Пересобрать проекты"
CLI_IMPORT = "Импортировать проект…"
CLI_VALIDATE = "Проверить проекты…"
CLI_PROJECT = "Информация по проектам"
# `CLI_BUSY_HINT` — из `tree_model` (одна строка на значок и меню), реэкспорт выше.
CLI_PAST_RUN = "прошлый запуск"
CLI_CODE_UNKNOWN = "завершено, код неизвестен"


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
        cli: EdtCli | None = None,
        watcher: CliWatcher | None = None,
        documents_dir: str = str(Path.home() / "Documents"),
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
        # CLI EDT (план 2): `cli is None` — подменю не строится, консоль пуста.
        self._cli = cli
        self._watcher = watcher
        self._documents_dir = documents_dir
        self._last_tsv_dir = documents_dir  # каталог последнего TSV — на сеанс (§14.2)
        self._console_project: str | None = None  # чья запись сейчас в консоли
        self._console = EdtConsole(palette=palette)
        self._console.interrupt_requested.connect(self.interrupt_current_cli)
        self._console.open_journal_requested.connect(self._open_console_journal)
        self._console.open_result_requested.connect(self._open_console_result)
        if watcher is not None:
            watcher.finished.connect(self.on_cli_finished)

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
        layout.addWidget(self._console)
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

    def console(self) -> EdtConsole:
        return self._console

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
        """Общий слот текущей строки: панель путей и консоль CLI (§14.5)."""
        self._sync_panel()
        self._sync_console()

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
        self._console.apply_palette(palette)
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
        if status.cli_busy:
            # Меню — подсказка; сам отказ живёт в `EdtWorkspace.launch` (§14.1).
            open_edt.setEnabled(False)
            open_edt.setToolTip(CLI_BUSY_HINT)
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
        if self._cli is not None:
            cli_menu = menu.addMenu(MENU_CLI)
            cli_menu.setToolTipsVisible(True)
            reason = self._cli.unavailable_reason(project.id)
            cli_action = cli_menu.menuAction()
            if reason:
                cli_action.setEnabled(False)
                cli_action.setToolTip(CLI_BUSY_HINT if status.cli_busy else reason)
            cli_menu.addAction(CLI_BUILD, lambda: self.cli_build(project.id))
            cli_menu.addAction(CLI_IMPORT, lambda: self.cli_import(project.id))
            cli_menu.addAction(CLI_VALIDATE, lambda: self.cli_validate(project.id))
            cli_menu.addAction(CLI_PROJECT, lambda: self.cli_project(project.id))

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

    # --- CLI (спека §14) ------------------------------------------------------

    def cli_build(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        question = f"Пересобрать все проекты workspace «{project.name}»? Это займёт время"
        if self._confirm(self, "Пересборка", question):
            self._start_cli(project_id, CLI_BUILD, cli_build_args())

    def cli_project(self, project_id: str) -> None:
        self._start_cli(project_id, CLI_PROJECT, cli_project_args())

    def cli_import(self, project_id: str) -> None:
        dialog = CliImportDialog(choose_directory=self._choose_directory, parent=self)
        if self._run_dialog(dialog):
            self._start_cli(project_id, CLI_IMPORT.rstrip("…"), cli_import_args(dialog.form()))

    def cli_validate(self, project_id: str) -> None:
        project = self._workspace.project(project_id)
        paths = workspace_projects(workspace_entries(project.workspace), project.project_dir)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        dialog = CliValidateDialog(
            paths, self._last_tsv_dir, f"validate-{project.name}-{stamp}.tsv", parent=self
        )
        if not self._run_dialog(dialog):
            return
        tsv = dialog.result_file()
        self._last_tsv_dir = str(Path(tsv).parent)
        self._start_cli(
            project_id,
            CLI_VALIDATE.rstrip("…"),
            cli_validate_args(dialog.selected_paths(), tsv),
            result_file=tsv,
        )

    def _start_cli(self, project_id: str, label: str, command: str, result_file: str = "") -> None:
        if self._cli is None:
            return
        try:
            run = self._cli.start(project_id, label, command, result_file)
        except ServicesError as error:
            self._show_error(str(error))
            return
        project = self._workspace.project(project_id)
        self._console_project = project_id
        self._console.show_run(
            project.name, label, STATE_RUNNING, self._cli.journal_path(project_id)
        )
        self._console.set_buttons(interrupt=True, journal=True, result=False)
        self._console.expand()  # единственное место, где консоль раскрывается сама (§14.5)
        if self._watcher is not None:
            self._watcher.watch(run)
        self.rebuild()

    def on_cli_finished(self, project_id: str, code: object) -> None:
        """Слот `CliWatcher.finished`: код завершения пришёл в главный поток."""
        if self._cli is None:
            return
        self._cli.finish(project_id, code if isinstance(code, int) else None)
        if self._console_project == project_id:
            self._refresh_console_state(project_id)
        self.rebuild()

    def interrupt_current_cli(self) -> None:
        if self._cli is None or self._console_project is None:
            return
        run = self._cli.run(self._console_project)
        if run is None:
            return
        question = (
            f"Прервать «{run.label}»? Сборка останется незавершённой, "
            "EDT пересоберёт при следующем открытии"
        )
        if not self._confirm(self, "Прерывание", question):
            return
        self._cli.interrupt(self._console_project)
        self._refresh_console_state(self._console_project)
        self.rebuild()

    def _refresh_console_state(self, project_id: str) -> None:
        assert self._cli is not None
        result = self._cli.last_result(project_id)
        if result is None:
            self._console.set_state(STATE_NOT_STARTED)
            self._console.set_buttons(interrupt=False, journal=True, result=False)
            return
        if result.interrupted:
            self._console.set_state(STATE_INTERRUPTED)
        elif result.code is None:
            self._console.set_state(CLI_CODE_UNKNOWN)
        else:
            self._console.set_state(state_finished(result.code))
        has_result = (
            bool(result.result_file) and result.code == 0 and Path(result.result_file).exists()
        )
        self._console.set_buttons(interrupt=False, journal=True, result=has_result)

    def _sync_console(self) -> None:
        """Выбор записи переключает журнал консоли, не раскрывая её (спека §14.5)."""
        if self._cli is None:
            return
        current = self.current()
        if current is None or current[0] != KIND_PROJECT:
            return
        project_id = current[1]
        run = self._cli.run(project_id)
        result = self._cli.last_result(project_id)
        path = self._cli.journal_path(project_id)
        project = self._workspace.project(project_id)
        self._console_project = project_id
        if run is not None:
            self._console.show_run(project.name, run.label, STATE_RUNNING, path)
            self._console.set_buttons(interrupt=True, journal=True, result=False)
        elif result is not None:
            self._console.show_run(project.name, result.label, "", path)
            self._refresh_console_state(project_id)
        elif path.exists():
            self._console.show_run(project.name, CLI_PAST_RUN, STATE_NOT_STARTED, path)
            self._console.set_buttons(interrupt=False, journal=True, result=False)
        else:
            self._console.show_run("", "", STATE_NOT_STARTED, None)
            self._console.set_buttons(interrupt=False, journal=False, result=False)

    def _open_console_journal(self) -> None:
        if self._cli is None or self._console_project is None:
            return
        path = str(self._cli.journal_path(self._console_project))
        self._apply(lambda: self._workspace.open_path(path), rebuild=False)

    def _open_console_result(self) -> None:
        if self._cli is None or self._console_project is None:
            return
        result = self._cli.last_result(self._console_project)
        if result is not None and result.result_file:
            self._apply(lambda: self._workspace.open_path(result.result_file), rebuild=False)

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
