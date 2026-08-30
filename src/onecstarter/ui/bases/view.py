"""Раздел «Базы»: поиск, дерево, запуск. Целевой сценарий — хоткей →
2–3 буквы → Enter (requirements.md, боль Б).

Виджет не кеширует ни ключи, ни строки: любое изменение — rebuild()
и свежие items()/tree() из Workspace (спека 4a, §2). Расчёты без Qt
живут в services/display.py, здесь — только отображение и события.
"""  # noqa: RUF002

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import cast

from PySide6.QtCore import QModelIndex, QPoint, QStandardPaths, Qt
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeySequence,
    QShortcut,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from onecstarter.config.atomic import atomic_write
from onecstarter.config.shell_link import (
    LinkNameRejectedError,
    LinkTargetRejectedError,
    build_shell_link,
    safe_file_name,
    shortcut_command,
)
from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import ClientKind
from onecstarter.domain.version import Installation
from onecstarter.services import cache
from onecstarter.services.catalog import TreeNode
from onecstarter.services.connection import panel_card
from onecstarter.services.display import (
    COMMON_NOTE,
    IMPLICIT_NOTE,
    Row,
    RowKind,
    display_forest,
    filter_rows,
    group_contents,
    version_cell,
)
from onecstarter.services.errors import (
    InvalidRequestError,
    ReadOnlySourceError,
    ServicesError,
    UnknownItemError,
)
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.paths import ROOT, group_path, normalize_folder, render_folder
from onecstarter.services.workspace import Workspace
from onecstarter.ui import errors as error_ui
from onecstarter.ui import theme
from onecstarter.ui.bases.panel import ConnectionPanel
from onecstarter.ui.bases.tree_model import KEY_ROLE, KIND_ROLE, build_model
from onecstarter.ui.dialogs.buttons import russian_confirm
from onecstarter.ui.dialogs.confirm import (
    ask_group_removal,
    confirm_cache_clear,
    confirm_removal,
)
from onecstarter.ui.dialogs.group import GroupDialog
from onecstarter.ui.dialogs.infobase import InfobaseDialog, dropped_directory
from onecstarter.ui.theme import Palette


def _format_stamp(stamp: datetime) -> str:
    return stamp.astimezone().strftime("%d.%m.%Y %H:%M")


# Задача 7 (спека §3.4): подменю «Очистить кэш» показывает пункт неактивным
# с одной из этих подсказок, а не молча — тот же приём, что у COMMON_NOTE/  # noqa: RUF003
# IMPLICIT_NOTE в services/display.py, только текст свой для кэша.
NO_CACHE_ID_NOTE = "У записи нет ID — каталог кэша не определить"  # noqa: RUF001
# Отдельно от NO_CACHE_ID_NOTE (находка финального ревью): невалидный ID
# записи и отсутствие корня в окружении (APPDATA/LOCALAPPDATA) — разные
# причины, и подсказка не должна путать одну с другой.  # noqa: RUF003
NO_CACHE_ROOT_NOTE = "В окружении нет корня кэша (APPDATA/LOCALAPPDATA)"  # noqa: RUF001
CACHE_EMPTY_NOTE = "кэш пуст"


def browse_for_shortcut_path(parent: QWidget | None, suggested: str) -> str:
    """Диалог сохранения ярлыка. Пустая строка — пользователь отказался.

    Инъекция, а не вызов модульного имени напрямую — тот же приём, что
    у `browse_for_directory` в `dialogs/infobase.py`: настоящий
    `QFileDialog` в офскрин-тесте не дождётся выбора файла.
    """  # noqa: RUF002
    path, _ = QFileDialog.getSaveFileName(parent, "Создать ярлык", suggested, "Ярлык (*.lnk)")
    return path


def show_cache_report(parent: QWidget | None, text: str) -> None:
    """Сводка очистки кэша: два числа, без трассировок (спека §3.7).

    Инъекция, а не прямой вызов в clear_cache — тот же приём, что
    у confirm_removal: настоящий QMessageBox.exec() блокирует офскрин-тест.
    """  # noqa: RUF002
    QMessageBox.information(parent, "OneCStarter", text)


class DropTarget(Enum):
    """Куда относительно строки-цели ложится перетащенная запись/группа."""

    INTO = "into"
    BEFORE = "before"
    AFTER = "after"


class _BasesTree(QTreeView):
    """Дерево раздела «Базы» с перехватом drop (задача 14, §3.3 плана 4b).

    `dropEvent` только переводит Qt-событие в примитивы (ключ источника,
    ключ цели, сторону, признак неявного узла или виртуальной строки) и
    зовёт `BasesView.handle_drop` — саму операцию и запись в файл делает
    `Workspace`, а дерево на экране появляется заново из него, вызовом
    `rebuild()` внутри `handle_drop`. Событие в конце всегда `ignore()`-ится:
    если отдать его `super().dropEvent()`, Qt попробует переставить строки
    сам, причём в модели, которую `rebuild()` уже подменил новым экземпляром
    к этому моменту, — получится не перенос, а вставка лишней строки,
    собранной из чужого (устаревшего) mime-содержимого без наших ролей
    привязки (проверено экспериментом при подготовке задачи: `super()`
    добавляет ребёнка цели, не удаляя источник, — ни то ни другое не
    соответствует ни экрану, ни файлу).

    Ссылка на `view`, а не заранее захваченный `view.handle_drop` — тесты
    подменяют `handle_drop` через `monkeypatch.setattr(view, ...)` уже после
    создания дерева, и без динамического поиска атрибута на каждый вызов
    подмена осталась бы невидимой.

    Геометрия найдена собственным `_where_at`, а не встроенным
    `dropIndicatorPosition()`. Тот геттер Qt пересчитывает только внутри
    штатного `dragMoveEvent`, и только когда `canDrop()` его принял —
    а в режиме `InternalMove` (см. `BasesView.__init__`) это требует
    `event.source() is self`. У события, собранного вручную в тесте,
    `source()` пуст всегда — `canDrop()` его не примет, и
    `dropIndicatorPosition()` останется на прежнем (не относящемся к делу)
    значении. Перевод остался бы непроверяемым — ровно та ловушка, которой
    посвящена задача 14 (`visualRect()` от состояния перетаскивания не
    зависит и даёт тот же результат что при живом drag, только
    воспроизводимый прямым вызовом `dropEvent()`).

    Круг правок 1 (ревью задачи 14): цель определяется по `KIND_ROLE`,
    а не по пустому `KEY_ROLE`. `KEY_ROLE` пуст у трёх разных видов строк —
    неявного узла (`RowKind.IMPLICIT_GROUP`, [Ф] T-05.7), заголовков веток
    «Избранное»/«Недавние»/«Общие списки» (`RowKind.SECTION`) и строк ошибок
    общего списка (`RowKind.NOTE`) — и до этой правки все три получали
    одно и то же сообщение про `Folder`, бессмысленное для веток, у которых
    `Folder` не существует в принципе. Различает их `KIND_ROLE`, тем же
    приёмом, что и контекстное меню задачи 12 (`_show_menu`,
    `kind == RowKind.IMPLICIT_GROUP.value`) — паритет с тем барьером теперь
    настоящий, не только «оба пустые по KEY_ROLE».
    """  # noqa: RUF002

    def __init__(self, view: "BasesView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view

    def _rejects_drop_at(self, position: QPoint) -> bool:
        """Запрещён ли бросок в этой точке — то есть будет ли он немым.

        Вложить запись в запись нельзя — это и раньше было так
        (`BasesView._folder_of_drop` отдаёт `None`), но отказ был **немым**:
        `handle_drop` тихо выходил, ничего не меняя и ничего не говоря.
        Ручной smoke №2 (09.08.2026) показал, чего это стоит: заказчик трижды
        бросил запись на строку записи, трижды не получил ничего и заключил,
        что перетаскивание сломано. Два соседних отказа — неявный узел
        и служебная строка — себя объясняют, этот молчал.

        Решение заказчика: отказывать курсором во время перетаскивания,
        а не окном после отпускания. Промах мимо межстрочья — частый случай,
        модальное окно на каждый промах утомляет; курсор виден до того, как
        кнопка отпущена, и закрывать его не надо.

        **Финальное ревью, I10.** Правило распространено на второй немой
        отказ — строку из «Общих списков». Первая редакция отвергала курсором
        только `INTO` на строку-базу, а `_folder_of_drop` отдаёт `None`
        для **любой** цели вне `InfobaseSource.USER`, с любой стороны:
        бросок на запись или группу общего списка тоже не делал ничего
        и тоже молчал — ровно тот симптом, о котором заказчик написал
        в smoke №2, только на соседнем случае. Поэтому здесь спрашивается
        не «какого вида строка», а «разрешит ли эту цель `_target_of_drop`»:
        строка с ключом привязки, которую он не находит, — цель, до которой
        операция не дойдёт.

        Отказ по-прежнему смотрит и на вид строки, и на сторону: у цели
        пользовательского списка запрещён ровно `INTO` на запись, а
        `BEFORE`/`AFTER` у неё же — разрешённая перестановка.

        Неявный узел и служебные строки сюда не попадают намеренно (у них
        нет `KEY_ROLE`, и `_row_key` отдаёт `None`): у них сообщения
        с подсказкой («создайте группу с тем же именем»), и заменить
        подсказку курсором значило бы обменять помощь на тишину — решение
        заказчика §14 п. 5 спеки.
        """  # noqa: RUF002
        index = self.indexAt(position)
        if not index.isValid():
            return False
        key = self._row_key(index)
        if key is not None and self._view._target_of_drop(key) is None:
            return True
        if self._where_at(index, position.y()) is not DropTarget.INTO:
            return False
        return self._row_kind(index) == RowKind.BASE.value

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Каталог из Проводника принимается отдельно от InternalMove (задача 20).

        Правило одно на все три обработчика этого класса: есть каталог
        в mime-данных — обрабатываем сами, до `super()` не доходим; нет —
        зовём `super()`, и штатная логика `InternalMove` (перенос строк
        мышью, задача 14) работает как раньше.
        """
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        if self._rejects_drop_at(event.position().toPoint()):
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        # Ветка каталога — первой и до чтения currentIndex(): у чужого  # noqa: RUF003
        # перетаскивания (из Проводника) текущей строки ЭТОГО дерева нет
        # вовсе, порядок здесь несущий, а не косметический (задача 20).  # noqa: RUF003
        directory = dropped_directory(event.mimeData())
        if directory is not None:
            index = self.indexAt(event.position().toPoint())
            self._view.add_infobase_from_directory(
                directory, self._row_key(index), self._row_kind(index)
            )
            event.acceptProposedAction()
            return
        source_key = self._row_key(self.currentIndex())
        if source_key is not None:
            position = event.position().toPoint()
            index = self.indexAt(position)
            target_key = self._row_key(index)
            kind = self._row_kind(index)
            self._view.handle_drop(
                source_key,
                target_key,
                self._where_at(index, position.y()),
                target_is_implicit=kind == RowKind.IMPLICIT_GROUP.value,
                target_is_virtual=kind in (RowKind.SECTION.value, RowKind.NOTE.value),
            )
        # Перестановку строк делает rebuild() внутри handle_drop, не Qt —
        # событие не принимается никогда, что бы ни случилось выше.
        event.ignore()

    @staticmethod
    def _row_key(index: QModelIndex) -> str | None:
        # KEY_ROLE стоит только у колонки имени (tree_model.build_model) —  # noqa: RUF003
        # тот же структурный барьер, что и у _current_base_key ниже:  # noqa: RUF003
        # у секций-заголовков, NOTE-строк и неявных узлов роль пуста.  # noqa: RUF003
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        return key if isinstance(key, str) else None

    @staticmethod
    def _row_kind(index: QModelIndex) -> str | None:
        if not index.isValid():
            return None
        kind = index.siblingAtColumn(0).data(KIND_ROLE)
        return kind if isinstance(kind, str) else None

    def _where_at(self, index: QModelIndex, y: int) -> DropTarget:
        """Сторона по позиции курсора в строке: верхняя/нижняя четверть — до/после.

        [Р] экстраполяция задачи 14: платформа своего drag-and-drop не имеет,
        сверять помечать нечем — порог взят по аналогии со штатным поведением
        Qt-предпросмотра (полоска вставки у края строки, заливка — в середине).
        """  # noqa: RUF002
        if not index.isValid():
            return DropTarget.INTO
        rect = self.visualRect(index)
        margin = max(1, rect.height() // 4)
        if y - rect.top() < margin:
            return DropTarget.BEFORE
        if rect.bottom() - y < margin:
            return DropTarget.AFTER
        return DropTarget.INTO


class BasesView(QWidget):
    def __init__(
        self,
        workspace: Workspace,
        *,
        installations: Sequence[Installation] | None,
        cfg_rules: Sequence[DefaultVersionRule],
        recent_limit: Callable[[], int],
        on_error: Callable[[ServicesError], None] | None = None,
        confirm_removal: Callable[[QWidget | None, InfobaseItem], bool] = confirm_removal,
        ask_group_removal: Callable[
            [QWidget | None, str, Sequence[str], int, int], GroupRemoval | None
        ] = ask_group_removal,
        choose_shortcut_path: Callable[
            [QWidget | None, str], str
        ] = browse_for_shortcut_path,
        cache_env: Mapping[str, str] | None = None,
        cache_ops: cache.CacheOps | None = None,
        confirm_cache_clear: Callable[[QWidget | None, str], bool] = confirm_cache_clear,
        show_cache_report: Callable[[QWidget | None, str], None] = show_cache_report,
        parent: QWidget | None = None,
        palette: Palette = theme.DARK,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        # `None` — обнаружение платформ фоном ещё не закончилось (спека
        # T-04.6, §3.4), а не «версий нет»: rebuild() различает эти случаи  # noqa: RUF003
        # через discovery_pending у version_cell, apply_installations кладёт  # noqa: RUF003
        # готовый список и снимает состояние ожидания.
        self._installations = None if installations is None else list(installations)
        self._cfg_rules = list(cfg_rules)
        # Провайдер, а не число: настройка меняется на лету и следующая  # noqa: RUF003
        # пересборка обязана взять новое значение (тот же приём, что
        # `theme_mode=lambda: controller.mode` у трея).  # noqa: RUF003
        self._recent_limit = recent_limit
        self._on_error = on_error or (lambda error: error_ui.show_service_error(self, error))
        # Инъекция, а не вызов функции модуля напрямую (тот же приём, что  # noqa: RUF003
        # у `open_directory` в ConnectionPanel и `choose_directory`  # noqa: RUF003
        # в InfobaseDialog): настоящая реализация открывает блокирующий
        # `QMessageBox.exec()`, и монки-патч модульного имени обошёл бы её
        # стороной в тестах — тот класс дефекта уже стоил задаче 10
        # отдельного круга правок (см. buttons.py, «Круг правок 1»).  # noqa: RUF003
        self._confirm_removal = confirm_removal
        # Тот же приём для удаления группы (задача 12) — ставки выше:
        # удаление каскадное, и подтверждение не Да/Нет, а выбор одного  # noqa: RUF003
        # из трёх исходов (`GroupRemoval | None`).
        self._ask_group_removal = ask_group_removal
        # Тот же приём для «Создать ярлык…» (задача 17): настоящий
        # `QFileDialog.getSaveFileName` блокирует офскрин-тест.
        self._choose_shortcut_path = choose_shortcut_path
        # Окружение и ФС кэша — инъекцией: тесты подменяют и то и другое,
        # живые кэши в offscreen-прогоне не трогаются.
        self._cache_env: Mapping[str, str] = os.environ if cache_env is None else cache_env
        self._cache_ops: cache.CacheOps = (
            cache.WindowsCacheOps() if cache_ops is None else cache_ops
        )
        self._confirm_cache_clear = confirm_cache_clear
        self._show_cache_report = show_cache_report
        self._rows: list[Row] = []
        self._palette = palette
        # Развёрнутость «чистого» (нефильтрованного) дерева и признак того,
        # что сейчас показан результат фильтра. Разделены намеренно: см.
        # rebuild().
        self._expansion: set[str] = set()
        self._filtered = False

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск: начните вводить имя базы")
        self._tree = _BasesTree(self)
        self._tree.setHeaderHidden(False)
        self._tree.setAlternatingRowColors(False)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Задача 14: перенос по группам перетаскиванием. InternalMove, а не  # noqa: RUF003
        # DragDrop — иначе дерево приняло бы и чужое перетаскивание вообще
        # любого содержимого (текст из другого окна и т. п.): без источника
        # в этом дереве `dropEvent` не может определить, ЧТО переносится.
        # Задача 20 пробивает в этом барьере точечное исключение только для
        # каталога Проводника: `_BasesTree.dragEnterEvent`/`dragMoveEvent`
        # проверяют mime на директорию ДО барьера `InternalMove` и принимают
        # её явно, `super()` (штатная проверка Qt, требующая `event.source()
        # is self`) вызывается только тогда, когда каталога в mime нет —
        # так решение заказчика 09.08.2026 (спека §3.4) реализовано, не
        # ослабляя сам барьер для всего остального.
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QTreeView.DragDropMode.InternalMove)
        self._panel = ConnectionPanel(parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._search)
        layout.addWidget(self._tree, stretch=1)
        layout.addWidget(self._panel)

        # Задача 20: дерево занимает большую часть раздела, но не весь —
        # остаются панель пути, поле поиска и поля вокруг. Приём каталога
        # на самом разделе (не только на дереве) закрывает и их.
        self.setAcceptDrops(True)
        # QLineEdit принимает перетаскивание сам и вставил бы путь каталога
        # текстом в строку поиска — бессмысленный результат вместо добавления.
        self._search.setAcceptDrops(False)

        self._search.textChanged.connect(lambda _text: self.rebuild())
        self._search.returnPressed.connect(self._launch_first_visible)
        self._tree.activated.connect(self._launch_index)
        self._tree.customContextMenuRequested.connect(self._show_menu)
        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_current_favorite)
        QShortcut(QKeySequence("Ctrl+N"), self, self.add_infobase)
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self._launch_current(ClientKind.THIN))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self._launch_current(ClientKind.THICK))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self._launch_current(ClientKind.DESIGNER))
        # F3/F4 — как у штатного стартера; заказчик к ним привык.  # noqa: RUF003
        # Ctrl+1/Ctrl+2 остаются: только они дают явный выбор тонкий/толстый,
        # которого у F3 нет. Ctrl+3 дублирует F4 — дубль безвреден.  # noqa: RUF003
        QShortcut(QKeySequence("F3"), self, lambda: self._launch_current(None))
        QShortcut(QKeySequence("F4"), self, lambda: self._launch_current(ClientKind.DESIGNER))
        # Задача 15: перестановка с клавиатуры, соседа берём из того, что  # noqa: RUF003
        # реально видно (см. _move_current) — тот же приём, что и с мышью  # noqa: RUF003
        # (handle_drop/_reorder), только сосед не из-под курсора, а из модели.  # noqa: RUF003
        QShortcut(QKeySequence("Alt+Up"), self, lambda: self._move_current(-1))
        QShortcut(QKeySequence("Alt+Down"), self, lambda: self._move_current(1))
        # T-11, п. 3 (решение заказчика 29.08.2026 — зашить, не keymap):
        # Alt+Enter — «Свойства», как в Проводнике Windows. Return и Enter
        # (цифровой блок) — разные клавиши Qt, регистрируются обе; справочник  # noqa: RUF003
        # в настройках рисуется по ui/shortcuts.py, тест сверяет его с этими  # noqa: RUF003
        # регистрациями.
        QShortcut(QKeySequence("Alt+Return"), self, self._show_current_properties)
        QShortcut(QKeySequence("Alt+Enter"), self, self._show_current_properties)

        self.rebuild()

    # -- доступ для тестов, трея и оболочки --------------------------------

    def workspace(self) -> Workspace:
        return self._workspace

    def model(self) -> QStandardItemModel:
        # _tree.model() возвращает базовый QAbstractItemModel по стубам Qt,
        # но rebuild() всегда ставит именно QStandardItemModel из build_model.
        return cast(QStandardItemModel, self._tree.model())

    def search(self) -> QLineEdit:
        return self._search

    def panel(self) -> ConnectionPanel:
        return self._panel

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def apply_palette(self, palette: Palette) -> None:
        """Сменить палитру и перерисовать: цвета запечены в QBrush и в значки."""
        self._palette = palette
        self.rebuild()

    def apply_installations(self, installations: Sequence[Installation]) -> None:
        """Обнаружение закончилось: показать версии вместо «…»."""
        self._installations = list(installations)
        self.rebuild()

    # -- перестройка --------------------------------------------------------

    def rebuild(self) -> None:
        """Пересобрать модель и вернуть дереву прежнюю развёрнутость и строку.

        Слепок развёрнутости снимается только с нефильтрованного дерева:
        `expandAll()` на время поиска — следствие фильтра, а не выбор
        пользователя. Снимая слепок с развёрнутого фильтром дерева, мы бы
        запомнили «развёрнуто всё» и уже не вернулись бы к свёрнутому виду
        никогда (находка финального ревью 07.08.2026).

        Текущая строка — другое дело: в отличие от развёрнутости, это выбор
        пользователя в обоих режимах, а не следствие фильтра, поэтому её
        маркер снимается всегда, до подмены модели. `setModel()` создаёт
        новую `QItemSelectionModel` без текущего индекса — без явного
        восстановления текущая строка терялась бы при каждом rebuild(),
        включая вызов из launch_key() и из каждого нажатия в поиске. Панель
        пути делает эту потерю видимой, но дефект старше её: до задачи 5
        `Ctrl+1`/`Ctrl+2`/`Ctrl+3` после набора текста в поиске так же молча
        ничего не делали, потому что `_current_base_key()` читает именно
        текущую строку (находка ревью задачи 5).

        Ширины колонок восстанавливаются тем же приёмом (smoke №1, 08.08.2026,
        замечание 3): `resizeColumnToContents` на каждой пересборке схлопывал
        колонку «База» до ширины самого короткого видимого имени — набор
        текста в поиске сужал её на первой же букве. Подгонка по содержимому
        нужна только при самой первой сборке, когда сохранённых ширин ещё
        нет; дальше ширина — как и развёрнутость с текущей строкой — выбор
        пользователя (в том числе ручная подстройка мышью), который не
        должен теряться при каждой перерисовке.
        """  # noqa: RUF002
        current_position = self._current_position()
        column_widths = self._column_widths()
        items = self._workspace.items()
        forest = display_forest(
            items,
            self._workspace.tree(),
            self._workspace.common_errors(),
            recent_limit=self._recent_limit(),
        )
        query = self._search.text()
        self._rows = filter_rows(forest, query)
        # discovery_pending отдельно от пустого списка (спека T-04.6, §3.4):
        # `self._installations is None` — обнаружение ещё не закончилось,
        # `self._installations or []` даёт version_cell пустой список, а не  # noqa: RUF003
        # None, — сигнатура version_cell его не принимает.  # noqa: RUF003
        pending = self._installations is None
        cells = {
            item.key: version_cell(
                item,
                self._installations or [],
                self._cfg_rules,
                discovery_pending=pending,
            )
            for item in items
            if not item.is_group
        }
        if not self._filtered:
            self._expansion = self._expanded_keys()
        model = build_model(self._rows, cells, _format_stamp, self._palette)
        self._tree.setModel(model)
        if column_widths is None:
            # Подгонка по содержимому уместна только на самой первой сборке —
            # ширин ещё нет, восстанавливать нечего.
            for column in range(model.columnCount()):
                self._tree.resizeColumnToContents(column)
        else:
            self._restore_column_widths(column_widths)
        self._filtered = bool(query.strip())
        if self._filtered:
            self._tree.expandAll()
        else:
            self._restore_expansion(self._expansion)
        self._restore_current(current_position)
        # Модель пересобрана целиком — прежняя selectionModel умерла вместе
        # с ней, подписку нельзя ставить один раз в __init__ (там модели ещё  # noqa: RUF003
        # нет вовсе): переподключаемся здесь и сразу синхронизируем панель.
        selection = self._tree.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(lambda *_: self._sync_panel())
        self._sync_panel()

    @staticmethod
    def _marker(index: QModelIndex, path: str) -> str:
        """Устойчивый маркер узла — для запоминания развёрнутости и текущей строки.

        Ключ привязки, если он есть: он переживает и переименование
        родителя, и смену порядка. Иначе — полный путь меток: у секций
        и неявных узлов ключа нет, а одной метки мало — два узла «Старое»
        на разных ветках разворачивались бы вместе.
        """  # noqa: RUF002
        key = index.data(KEY_ROLE)
        return key if isinstance(key, str) else f"label:{path}"

    def _path_to(self, index: QModelIndex) -> str:
        """Путь меток от корня до индекса — тот же формат, что у обхода

        в `_expanded_keys`/`_restore_expansion` (`f"{path}/{label}"` на
        каждом уровне). Строится в обратную сторону, через `.parent()`,
        а не обходом от корня — индекс уже есть, обходить всё дерево
        ради него незачем.
        """  # noqa: RUF002
        labels: list[str] = []
        node = index
        while node.isValid():
            labels.append(str(node.data()))
            node = node.parent()
        return "/" + "/".join(reversed(labels))

    def _current_position(self) -> tuple[str, str] | None:
        """Маркер и путь текущей строки перед пересборкой — `None`, если её нет.

        Путь запоминается отдельно от маркера (smoke №1, 08.08.2026,
        замечание 4): у записи-базы маркер — это её ключ привязки, один
        и тот же независимо от пути (`_marker` для строк с ключом путь
        игнорирует), а один и тот же ключ в модели встречается дважды —
        у своей записи есть место и в дереве файла, и в виртуальной ветке
        «Недавние»/«Избранное» (`display_forest`). Маркера одного недостаточно,
        чтобы отличить два вхождения; путь отличает.
        """  # noqa: RUF002
        index = self._tree.currentIndex().siblingAtColumn(0)
        if not index.isValid():
            return None
        path = self._path_to(index)
        return self._marker(index, path), path

    def _restore_current(self, position: tuple[str, str] | None) -> None:
        """Найти прежнюю строку в новой модели и сделать её текущей.

        Позиции нет (`None`) — текущей строки не остаётся: правильное
        поведение, а не дефект (набор текста в поиске, скрывающий выделенную
        запись, гасит панель, а не показывает случайную соседнюю строку).

        Маркер встречается в модели дважды для записи, показанной и в дереве
        файла, и в «Недавних»/«Избранном» — поэтому в приоритете точное
        совпадение и маркера, и пути; при его отсутствии годится любое
        совпадение маркера (`fallback`) — запись могла переехать в другую
        группу между пересборками, и вернуться к ней по одному ключу
        правильно. Обход всегда идёт по всему дереву без ранней остановки:
        «Недавние» стоит в лесу раньше дерева файла, и первое попавшееся
        совпадение маркера почти всегда оказалось бы дублем не с той веткой.
        """  # noqa: RUF002
        if position is None:
            return
        marker, path = position
        model = self._tree.model()
        exact: QModelIndex | None = None
        fallback: QModelIndex | None = None

        def walk(parent: QModelIndex, here_path: str) -> None:
            nonlocal exact, fallback
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                here = f"{here_path}/{index.data()}"
                if self._marker(index, here) == marker:
                    if here == path:
                        exact = index
                    elif fallback is None:
                        fallback = index
                walk(index, here)

        walk(QModelIndex(), "")
        found = exact if exact is not None else fallback
        if found is not None:
            self._tree.setCurrentIndex(found)

    def _column_widths(self) -> list[int] | None:
        """Ширины колонок перед пересборкой — `None`, если модели ещё нет.

        `None` отличает «первая сборка» (подгонка по содержимому уместна)
        от «уже есть сохранённые ширины» (их надо вернуть) — пустой список
        для этого не годится, колонок всегда три и список никогда не пуст.
        """
        model = self._tree.model()
        if model is None:
            return None
        return [self._tree.columnWidth(column) for column in range(model.columnCount())]

    def _restore_column_widths(self, widths: list[int]) -> None:
        for column, width in enumerate(widths):
            self._tree.setColumnWidth(column, width)

    def _expanded_keys(self) -> set[str]:
        model = self._tree.model()
        if model is None:
            return set()
        keys: set[str] = set()

        def walk(parent: QModelIndex, path: str) -> None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                here = f"{path}/{index.data()}"
                if self._tree.isExpanded(index):
                    keys.add(self._marker(index, here))
                walk(index, here)

        walk(QModelIndex(), "")
        return keys

    def _restore_expansion(self, keys: set[str]) -> None:
        model = self._tree.model()

        def walk(parent: QModelIndex, path: str) -> None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                here = f"{path}/{index.data()}"
                if self._marker(index, here) in keys:
                    self._tree.expand(index)
                walk(index, here)

        walk(QModelIndex(), "")

    # -- запуск и операции ---------------------------------------------------

    def launch_key(self, key: str, forced: ClientKind | None = None) -> None:
        try:
            self._workspace.launch(key, forced)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def toggle_favorite(self, key: str) -> None:
        item = next((i for i in self._workspace.items() if i.key == key), None)
        try:
            self._workspace.set_favorite(key, not (item.favorite if item else False))
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def remove_key(self, key: str) -> None:
        """«Удалить из списка…» — только запись; файлы базы на диске не трогаются.

        Отказ подтверждения (`self._confirm_removal` вернул `False`) и
        отсутствие записи с таким ключом — оба выходят без похода
        в `Workspace`, файл в обоих случаях остаётся нетронутым. Запись
        могла пропасть из списка между построением меню и кликом (внешняя
        правка файла и `rebuild()`), поэтому поиск идёт заново по свежим
        `items()`, а не по ссылке, пойманной при построении меню.

        `Workspace.remove_infobase` может вернуть `False` уже после
        подтверждения: цель есть сейчас, а к моменту записи файл успел
        измениться извне и ключ сместился (тот же класс гонки, что
        и у самого метода — см. его докстринг). Это не `ServicesError`
        (операция вообще не была отвергнута), поэтому `_on_error` вызывается
        явно, а не через `except`.
        """  # noqa: RUF002
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None or not self._confirm_removal(self, item):
            return
        try:
            if not self._workspace.remove_infobase(key):
                self._on_error(
                    UnknownItemError(
                        "Запись не найдена в файле — возможно, список изменился "
                        "извне. Обновите список и повторите"
                    )
                )
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def create_shortcut(self, key: str) -> None:
        """«Создать ярлык…» — файл `.lnk` на нашу программу с именем базы.

        Ярлык несёт **имя** базы, а не ключ привязки: ключ меняется, когда
        записи дописывается `ID`, и ярлык сломался бы от первой же правки
        записи через нас (`Workspace.find_by_name`, `run_launch`).

        Цель — `sys.executable`; когда мы не заморожены, к аргументам
        добавляется `-m onecstarter` (`shortcut_command`). Расчёт цели
        и аргументов — чистая функция в `config/shell_link.py`, а не сборка
        внутри диалога: внутри диалога она осталась бы непроверяемой.

        Запись атомарная (инвариант 4): диалог сохранения разрешает выбрать
        существующий ярлык, и наполовину записанный файл на месте рабочего
        — ровно та потеря, от которой инвариант защищает.

        Неоднозначность имени проверяется **до** диалога, тем же
        `find_by_name`, которым потом будет искать `run_launch`. Две базы
        с одним именем — обычное дело (копия базы в другой группе, та же
        база из общего списка с другим `ID`), и без этой проверки ярлык
        создавался бы молча, а «Имя не единственное» пользователь получал
        бы потом, по клику, когда связь с созданием ярлыка уже не очевидна.

        Проверка неполна и не может быть полной: дубль появится и после
        создания ярлыка — достаточно завести вторую базу с тем же именем.
        Она снимает основной случай и отказывает там, где пользователь ещё
        понимает, о чём речь; окончательный барьер остаётся в `run_launch`.
        """  # noqa: RUF002
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            # Запись могла исчезнуть между построением меню и кликом
            # (внешняя правка файла и rebuild) — тот же случай, что
            # у remove_key: молча выходим, файл не трогаем.  # noqa: RUF003
            return
        try:
            suggested = safe_file_name(item.name)
        except LinkNameRejectedError as error:
            self._on_error(InvalidRequestError(str(error)))
            return
        try:
            self._workspace.find_by_name(item.name)
        except ServicesError as error:
            self._on_error(error)
            return
        desktop = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        )
        chosen = self._choose_shortcut_path(self, str(Path(desktop) / suggested))
        if not chosen:
            return
        target, arguments = shortcut_command(
            sys.executable, item.name, frozen=getattr(sys, "frozen", False)
        )
        try:
            payload = build_shell_link(
                target, arguments, target.parent, f"{item.name} — OneCStarter"
            )
            atomic_write(Path(chosen), payload)
        except LinkTargetRejectedError as error:
            self._on_error(InvalidRequestError(f"Не удалось собрать ярлык: {error}"))  # noqa: RUF001
        except OSError as error:
            self._on_error(
                InvalidRequestError(f"Не удалось сохранить ярлык: {error}")  # noqa: RUF001
            )

    def _launch_index(self, index: QModelIndex) -> None:
        if index.siblingAtColumn(0).data(KIND_ROLE) != RowKind.BASE.value:
            return  # группы, неявные узлы и заголовки не запускаются
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        if key:
            self.launch_key(key)

    def _launch_first_visible(self) -> None:
        # Пустой поиск (после strip) — ничего не запускаем: случайный Enter
        # (например, сразу после хоткея, до первой буквы) не должен
        # запустить первую базу леса — чужую реальную базу одним нажатием.
        if not self._search.text().strip():
            return
        first = self._first_base(self._rows)
        if first is not None:
            self.launch_key(first)

    def _first_base(self, rows: Sequence[Row]) -> str | None:
        for row in rows:
            if row.kind is RowKind.BASE and row.item is not None:
                return row.item.key
            nested = self._first_base(row.children)
            if nested is not None:
                return nested
        return None

    def _sync_panel(self) -> None:
        """Панель получает карточку любой выделенной строки, не только базы.

        Вид строки и ключ — из ролей модели (KIND_ROLE/KEY_ROLE), запись —
        свежим поиском по items(): между построением модели и кликом файл
        мог перечитаться (rebuild), ссылки из модели держать нельзя —
        тот же принцип, что у remove_key.
        """  # noqa: RUF002
        index = self._tree.currentIndex().siblingAtColumn(0)
        kind_value = index.data(KIND_ROLE) if index.isValid() else None
        kind = None
        if isinstance(kind_value, str):
            kind = RowKind(kind_value)
        key = index.data(KEY_ROLE) if index.isValid() else None
        item = None
        if isinstance(key, str):
            item = next((i for i in self._workspace.items() if i.key == key), None)
        label = str(index.data() or "") if index.isValid() else ""
        self._panel.show_card(panel_card(kind, item, label), self._palette)

    def _current_base_key(self) -> str | None:
        index = self._tree.currentIndex()
        if not index.isValid():
            return None
        if index.siblingAtColumn(0).data(KIND_ROLE) != RowKind.BASE.value:
            return None
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        return key if isinstance(key, str) else None

    def _launch_current(self, forced: ClientKind | None) -> None:
        key = self._current_base_key()
        if not key:
            return
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is not None and item.kind is ConnectKind.WEB:
            # launch_infobase игнорирует forced_client для веб-баз (нет
            # исполняемого файла клиента). Раньше здесь стоял безусловный
            # launch_key: с Ctrl+1/2/3 это было честно, потому что меню для WEB  # noqa: RUF003
            # такие пункты прячет. С F4 — уже нет: «Конфигуратор» и «открылся  # noqa: RUF003
            # браузер» разные вещи. Явно затребованный клиент для веб-базы —
            # бездействие, режим по умолчанию (forced is None, F3/Enter) —
            # браузер.
            if forced is not None:
                return
            self.launch_key(key)
        else:
            self.launch_key(key, forced)

    def _toggle_current_favorite(self) -> None:
        key = self._current_base_key()
        if key:
            self.toggle_favorite(key)

    def _show_current_properties(self) -> None:
        """`Alt+Enter` — свойства текущей строки (T-11, п. 3).

        Запись → `show_properties`, группа → диалог группы (`rename_group`).
        Тот же порог, что у пунктов меню: запись или группа общего списка
        (`_build_menu` гасит «Свойства…», `_group_menu_for` — всё меню) —
        бездействие, а не диалог, который отвергнут при «ОК». Неявный узел,
        заголовок ветки, пустое дерево — бездействие.
        """  # noqa: RUF002
        index = self._tree.currentIndex().siblingAtColumn(0)
        if not index.isValid():
            return
        kind = index.data(KIND_ROLE)
        key = index.data(KEY_ROLE)
        if not isinstance(key, str):
            return
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None or item.source is InfobaseSource.COMMON:
            return
        if kind == RowKind.BASE.value:
            self.show_properties(key)
        elif kind == RowKind.GROUP.value:
            self.rename_group(key)

    def _build_menu(self, item: InfobaseItem, key: str) -> QMenu:
        """Собрать контекстное меню базы без показа (для тестов и _show_menu).

        Отделено от _show_menu ради проверки состава пунктов без блокирующего
        QMenu.exec — вызов из теста строит меню и читает тексты действий.

        **Финальное ревью, I7.** Решение «можно ли» принимается здесь, один
        раз, до показа меню — то же правило, что круг правок 1 задачи 12
        завёл для групп (`_group_menu_for`, `_build_disabled_group_menu`),
        и та же его реализация: пункт виден, но неактивен и объясняет себя
        подсказкой. К строкам-записям правило тогда не применили, и у записи
        из общего списка все восемь пунктов были включены: «Удалить из
        списка…» показывало подтверждение и только **после** «Да» приносило
        `ReadOnlySourceError`, а «Свойства…» открывали полностью
        редактируемый диалог, чей «ОК» отвергается тем же способом.
        Решение заказчика 09.08.2026 (спека §3.2): отказ показывается
        раньше, до действия.

        Неактивны ровно те два пункта, которые пишут в файл списка. Запуск,
        «Создать ярлык…» и «В избранное» для записи общего списка работают
        по-настоящему: первые два вообще ничего не пишут в `.v8i`, третий
        пишет только в наши данные (`bases.json`), к которым источник записи
        отношения не имеет.
        """  # noqa: RUF002
        menu = QMenu(self)
        if item.kind is ConnectKind.WEB:
            menu.addAction("Открыть в браузере", lambda: self.launch_key(key))
        else:
            # Подписи — сочетания штатного стартера, к которым привык
            # заказчик (smoke №1, 08.08.2026, замечание 5), а не наши  # noqa: RUF003
            # внутренние хоткеи. Ctrl+1/Ctrl+2 остаются в подписи «Тонкий»/
            # «Толстый клиент»: только они дают явный выбор клиента, которого
            # у F3 нет. У «Конфигуратора» рабочих сочетаний два — F4 и Ctrl+3  # noqa: RUF003
            # (__init__ регистрирует оба, Ctrl+3 псевдонимом), но в меню  # noqa: RUF003
            # показывается только F4 — то, что заказчик ждёт увидеть.
            menu.addAction("Запустить\tF3", lambda: self.launch_key(key))
            menu.addAction(
                "Тонкий клиент\tCtrl+1", lambda: self.launch_key(key, ClientKind.THIN)
            )
            menu.addAction(
                "Толстый клиент\tCtrl+2", lambda: self.launch_key(key, ClientKind.THICK)
            )
            menu.addAction(
                "Конфигуратор\tF4", lambda: self.launch_key(key, ClientKind.DESIGNER)
            )
        menu.addSeparator()
        # Ярлык осмыслен и для веб-базы: он зовёт нашу программу
        # с `--ib-name`, а та открывает браузер (services/launch.py).  # noqa: RUF003
        menu.addAction("Создать ярлык…", lambda: self.create_shortcut(key))
        properties = menu.addAction("Свойства…\tAlt+Enter", lambda: self.show_properties(key))
        self._add_cache_menu(menu, item)
        menu.addSeparator()
        star = "Убрать из избранного" if item.favorite else "В избранное"  # noqa: RUF001
        menu.addAction(f"{star}\tCtrl+D", lambda: self.toggle_favorite(key))
        menu.addSeparator()
        # Разрушительное действие — отдельным пунктом за разделителем, в самом
        # низу, как и в штатном стартере: разделяет обычные операции и то, что
        # трогает файл списка необратимо (remove_key спрашивает подтверждение).
        removal = menu.addAction("Удалить из списка…", lambda: self.remove_key(key))
        if item.source is InfobaseSource.COMMON:
            # `setToolTipsVisible(True)` обязателен: без него `QMenu`
            # на этой платформе подсказки пунктов не показывает вовсе —
            # тот же вывод, что и у `_build_disabled_group_menu`.  # noqa: RUF003
            menu.setToolTipsVisible(True)
            for action in (properties, removal):
                action.setEnabled(False)
                action.setToolTip(COMMON_NOTE)
        return menu

    def _add_cache_menu(self, menu: QMenu, item: InfobaseItem) -> None:
        """Подменю «Очистить кэш» — два пункта, без сочетаний клавиш (спека §3.2).

        Доступность решается по данным записи (ID-GUID) и дешёвой проверке
        наличия каталога; замер размера здесь не выполняется — он идёт после
        клика, перед подтверждением (спека §3.4/§4 в редакции 23.08.2026).
        Многоточия обязательны: каждый пункт ведёт к подтверждению.
        Подсказки неактивных пунктов требуют setToolTipsVisible — тот же
        вывод, что у _build_disabled_group_menu.

        `QMenu(title, menu)` + `menu.addMenu(submenu)`, а не однострочный
        `menu.addMenu("Очистить кэш")`: у последнего наблюдалось «Internal
        C++ object already deleted» (воспроизведено изолированным прогоном
        при реализации задачи — тесты, читающие состав подменю после
        возврата `_build_menu` (`action.menu()`/`submenu.actions()`),
        временами падали с этой ошибкой). Причина не установлена — версия
        про то, что PySide6 не всегда распознаёт владельца через неявный
        `this` внутри вспомогательного метода Qt, была бы догадкой, а не
        фактом. Обход — явный `parent=menu` при создании `QMenu`, тот же
        приём, что и `QMenu(self)` парой строк выше по файлу; с ним ошибка
        не воспроизводится.
        """  # noqa: RUF002
        submenu = QMenu("Очистить кэш", menu)
        menu.addMenu(submenu)
        submenu.setToolTipsVisible(True)
        labels = (
            (cache.CacheKind.USER, "Пользовательский…"),
            (cache.CacheKind.PROGRAM, "Программный…"),
        )
        for kind, label in labels:
            action = submenu.addAction(
                label,
                lambda _checked=False, k=kind, key=item.key: self.clear_cache(key, k),
            )
            if not cache.is_valid_cache_id(item.section_id):
                action.setEnabled(False)
                action.setToolTip(NO_CACHE_ID_NOTE)
                continue
            path = cache.cache_path(self._cache_env, kind, item.section_id)
            if path is None:
                # ID валиден, но окружение не даёт корня (нет APPDATA/
                # LOCALAPPDATA) — причина другая, подсказка тоже другая.
                action.setEnabled(False)
                action.setToolTip(NO_CACHE_ROOT_NOTE)
            elif not self._cache_ops.is_dir(path):
                action.setEnabled(False)
                action.setToolTip(CACHE_EMPTY_NOTE)

    def clear_cache(self, key: str, kind: cache.CacheKind) -> None:
        """Очистить кэш записи: замер → подтверждение → удаление → сводка.

        Подтверждение всегда (решение заказчика 23.08.2026, спека §3.5);
        без «Да» не удаляется ничего. Запись могла исчезнуть между
        построением меню и кликом (внешняя правка файла и rebuild) — молча
        выходим, тот же случай, что у remove_key/create_shortcut. Путь
        строится заново по свежим данным записи, а не ловится при построении
        меню: ключ и ID могли смениться.

        Тем же приёмом накрыт и сам каталог кэша (находка финального
        ревью): он тоже мог исчезнуть между построением меню и кликом.
        Без перепроверки `measure` тихо вернул бы ноль (её ошибки чтения
        не поднимаются — см. докстринг), вопрос подтверждения обещал бы
        «(0 Б)», а `clear` дал бы `failed=1` — и сводка после «Да» лживо
        сообщила бы «файлы заняты запущенной 1С», хотя каталога уже нет.
        """  # noqa: RUF002
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return
        path = cache.cache_path(self._cache_env, kind, item.section_id)
        if path is None:
            return
        if not self._cache_ops.is_dir(path):
            # Каталог исчез между построением меню и кликом — тот же случай,
            # что пропавшая запись: молча выходим, удалять нечего.
            return
        measured = cache.measure(path, self._cache_ops)
        question = cache.clear_question(kind, item.name, measured)
        if not self._confirm_cache_clear(self, question):
            return
        report = cache.clear(path, self._cache_ops)
        self._show_cache_report(self, cache.report_text(report))

    def folder_for_dropped_directory(
        self, target_key: str | None, kind: str | None
    ) -> str:
        """`Folder` новой записи по месту, куда отпустили каталог. Спека §3.4.

        Переиспользует `_folder_of_drop`, а не заводит вторую логику путей:
        для строки-группы это `INTO` (собственный путь группы), для строки-базы
        `AFTER` (путь родителя). Всё остальное — служебные ветки, неявный узел,
        промах мимо строк — корень.

        Итог проверяется на членство в `_group_paths()`. Без этого висячий
        `Folder` ([Ф] T-05.7) вернулся бы как группа, которой в списке диалога
        нет, и `set_folder` отказал бы уже после броска — на ровном месте.

        Дефект плана, найденный на этом шаге: `_folder_of_drop` отдаёт путь
        в файловой форме (`render_folder` — с ведущим слэшем для вложенных,
        `Workspace.update_infobase`/`update_group` ждут именно её), а
        `_group_paths()`/`InfobaseDialog.set_folder` работают в форме
        `normalize_folder` (без ведущего слэша, `group_path` без него же) —
        `_folder_of_drop("Клиенты")` вернул бы `/Клиенты`, чего нет и не
        может быть в `_group_paths()`, и любая настоящая группа проваливала
        бы проверку членства и откатывалась на корень. `normalize_folder`
        приводит результат `_folder_of_drop` (и `None` — тоже безопасно,
        `normalize_folder(None)` даёт `ROOT`) к форме, которую использует
        именно этот диалог.
        """  # noqa: RUF002
        if kind == RowKind.GROUP.value:
            folder = self._folder_of_drop(target_key, DropTarget.INTO)
        elif kind == RowKind.BASE.value:
            folder = self._folder_of_drop(target_key, DropTarget.AFTER)
        else:
            folder = None
        normalized = normalize_folder(folder)
        return normalized if normalized in self._group_paths() else ROOT

    def _build_add_dialog(self) -> InfobaseDialog:
        """Собрать диалог добавления записи без показа (для тестов и add_infobase).

        Тот же приём, что у `_build_menu`/`_build_properties_dialog`: `exec()`
        блокирует офскрин-тесты, поэтому сборка отделена от показа. Без этого
        разделения `add_infobase` повторил бы дефект, который ревью задачи 8
        нашло у `show_properties`, — единственный пользовательский путь без
        покрытия (задача 10, урок 2).
        """  # noqa: RUF002
        return InfobaseDialog.for_new(
            groups=self._group_paths(),
            # Обнаружение платформ может быть ещё не закончено (первые
            # полсекунды старта, спека T-04.6, §3.4) — диалог честно не
            # знает версий, а не получает None, который он не ждёт.  # noqa: RUF003
            installations=self._installations or [],
            cfg_rules=self._cfg_rules,
            parent=self,
        )

    def add_infobase(self) -> None:
        """«Добавить базу…» — пункт меню пустого места дерева и `Ctrl+N`."""
        dialog = self._build_add_dialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_new_infobase(dialog)

    def build_dialog_for_dropped_directory(
        self, directory: str, target_key: str | None, kind: str | None
    ) -> InfobaseDialog:
        """Диалог добавления с подставленными путём, именем и группой.

        Сборка без показа — как `_build_add_dialog`, и по той же причине.
        """  # noqa: RUF002
        dialog = self._build_add_dialog()
        dialog.accept_directory(directory)
        dialog.set_folder(self.folder_for_dropped_directory(target_key, kind))
        return dialog

    def add_infobase_from_directory(
        self, directory: str, target_key: str | None = None, kind: str | None = None
    ) -> None:
        """Каталог, брошенный в раздел, — диалог добавления, а не запись сразу.

        Решение заказчика 09.08.2026 (спека §14, п. 2): имя каталога не всегда
        годится как имя базы, а молчаливое создание записи от случайного броска
        меняет чужой файл без спроса. Диалог и `Workspace.add_infobase`
        используются существующие — второго пути создания записи не появляется.
        """  # noqa: RUF002
        dialog = self.build_dialog_for_dropped_directory(directory, target_key, kind)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_new_infobase(dialog)

    def _apply_new_infobase(self, dialog: InfobaseDialog) -> None:
        """Записать новую запись по данным принятого диалога добавления.

        Отдельно от `add_infobase` ради тестов — тот же приём, что
        у `_apply_properties`/`show_properties`. Отказ `Workspace` (например,
        пустое имя или несуществующая группа) идёт в `_on_error`, а не
        наружу — тем же способом, что и у `_apply_properties`.

        `dialog.new_record()` тоже не считается безусловно успешной — та же
        граница, что и у `dialog.changes()` в `_apply_properties` (круг
        правок 1 ревью задачи 10): `new_record()` зовёт `build_connect`,
        которая поднимает `ValueError` на запрещённых символах, если
        `_on_accept` диалога почему-то не остановил их раньше. До правки
        этот `try` стоял только вокруг `_apply_properties`, а собственный
        тестовый набор вызывает `_apply_new_infobase` тем же прямым
        способом, в обход `exec()`/`_on_accept`.
        """  # noqa: RUF002
        try:
            name, connect, folder = dialog.new_record()
        except ValueError as error:
            self._on_error(
                InvalidRequestError(f"Не удалось прочитать данные диалога: {error}")  # noqa: RUF001
            )
            return
        try:
            self._workspace.add_infobase(name, connect, folder)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def _build_properties_dialog(self, key: str) -> InfobaseDialog | None:
        """Собрать диалог свойств без показа (для тестов и show_properties).

        Тот же приём, что у `_build_menu`/`_show_menu`: `exec()` блокирует
        офскрин-тесты, поэтому сборка отделена от показа и проверяется
        отдельно — какая запись найдена, что произойдёт при отсутствующем
        ключе и что реально дошло до диалога (`installations`, группы).
        """  # noqa: RUF002
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return None
        return InfobaseDialog(
            item,
            groups=self._group_paths(),
            # Тот же случай, что у _build_add_dialog: обнаружение платформ  # noqa: RUF003
            # может быть ещё не закончено.
            installations=self._installations or [],
            cfg_rules=self._cfg_rules,
            parent=self,
        )

    def show_properties(self, key: str) -> None:
        dialog = self._build_properties_dialog(key)
        if dialog is None:
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_properties(key, dialog)

    def _apply_properties(self, key: str, dialog: InfobaseDialog) -> None:
        """Применить правки диалога свойств — отдельно от exec() ради тестов.

        Тот же приём, что у `_build_menu`/`_show_menu` и
        `_build_properties_dialog`/`show_properties` из задачи 8: `exec()`
        блокирует офскрин-тесты, поэтому запись отделена от показа. Пустая
        пара «правок нет, имя не менялось» не идёт в `update_infobase` вовсе —
        задача 9 существует ровно ради того, чтобы нетронутый диалог не тронул
        файл.

        `dialog.changes()` не считается безусловно успешной (C3, круг правок 1
        ревью задачи 9): диалог сам отфильтровывает поля размещения до реально
        найденных в `Connect` фрагментов, но это дисциплина внутри диалога,
        а не гарантия типа — граница Qt-слота обязана остаться рабочей, даже
        если эта дисциплина где-то в будущем нарушится. Задача 10 добавляет
        второй источник той же дисциплины: `build_connect` при смене вида
        поднимает `ValueError` на запрещённых символах, а гарантирует их
        отсутствие только `_on_accept` диалога (та же граница, тот же приём).

        Смена вида размещения (задача 10) переписывает `Connect` целиком —
        список теряемых ключей (`kind_change_warning`) показывается заранее,
        отказ пользователя отменяет всю операцию, не только правку вида,
        и до `Workspace.update_infobase` дело не доходит вовсе.
        """  # noqa: RUF002
        warning = dialog.kind_change_warning()
        if warning is not None and not russian_confirm(self, "Смена вида размещения", warning):
            return
        try:
            changes, new_name = dialog.changes()
        except (KeyError, ValueError) as error:
            self._on_error(
                InvalidRequestError(
                    f"Не удалось прочитать правки диалога: {error}"  # noqa: RUF001
                )
            )
            return
        if not changes and new_name is None:
            return
        try:
            self._workspace.update_infobase(key, changes, new_name)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def _group_paths(self) -> list[str]:
        """Пути существующих групп плюс корень — для выпадающего списка.

        Только пользовательский источник (круг правок 1 ревью задачи 12):
        группа из общего списка (`InfobaseSource.COMMON`) не существует
        в документе, который правит `Workspace` — путь к ней в этом списке
        вёл бы «Создать группу…»/выбор группы у записи в один и тот же
        тупик, `InvalidRequestError` («Группы «X» в списке нет») про группу,
        которая у пользователя прямо на экране. Правило одно на оба
        потребителя (`GroupDialog` и `InfobaseDialog`), а не отдельная
        проверка в каждом.
        """  # noqa: RUF002
        paths = [
            group_path(item.folder, item.name)
            for item in self._workspace.items()
            if item.is_group and item.source is InfobaseSource.USER
        ]
        return [ROOT, *sorted(set(paths))]

    def _build_empty_space_menu(self) -> QMenu:
        """Меню пустого места дерева — добавление записи и создание группы в корне."""
        menu = QMenu(self)
        menu.addAction("Добавить базу…", self.add_infobase)
        menu.addAction("Создать группу…", lambda: self.add_group(ROOT))
        return menu

    def _build_group_menu(self, item: InfobaseItem, key: str) -> QMenu:
        """Меню группы: подгруппа внутри неё, переименование/перенос, удаление.

        Только для группы пользовательского источника — вызывающий
        (`_group_menu_for`) обязан отсеять `InfobaseSource.COMMON` до этого
        вызова. Тот же приём, что у `_build_menu`/`_build_empty_space_menu`:
        отделено от показа, чтобы состав проверялся без блокирующего
        `QMenu.exec`. Разрушительный пункт («Удалить группу…») — за отдельным
        разделителем, в самом низу, как и «Удалить из списка…» в
        `_build_menu` (задача 11).
        """  # noqa: RUF002
        menu = QMenu(self)
        own_path = group_path(item.folder, item.name)
        menu.addAction("Создать группу…", lambda: self.add_group(own_path))
        menu.addAction("Переименовать группу…", lambda: self.rename_group(key))
        menu.addSeparator()
        menu.addAction("Удалить группу…", lambda: self.remove_group(key))
        return menu

    def _build_disabled_group_menu(self, note: str) -> QMenu:
        """Меню группы без операций: три пункта видны, но недоступны — с пояснением.

        Общий билдер для двух случаев, у которых один и тот же результат
        (операции невозможны), но разная причина: неявный узел (`IMPLICIT_NOTE`
        — [Ф] T-05.7, нет ни секции, ни ключа) и группа из общего списка
        (`COMMON_NOTE` — источник только для чтения, `_group_menu_for`).
        До круга правок 1 задачи 12 у каждого случая было своё меню с одним
        и тем же телом — вынесено в одно место, чтобы правило «эти три
        пункта показываются неактивными с пояснением» не разошлось между
        копиями. `setToolTipsVisible(True)` обязателен: без него `QMenu`
        на этой платформе тултипы пунктов не показывает вовсе — сам факт
        наличия текста в `setToolTip` этого не гарантирует.
        """  # noqa: RUF002
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for label in ("Создать группу…", "Переименовать группу…", "Удалить группу…"):
            action = menu.addAction(label)
            action.setEnabled(False)
            action.setToolTip(note)
        return menu

    def _build_implicit_group_menu(self) -> QMenu:
        return self._build_disabled_group_menu(IMPLICIT_NOTE)

    def _group_menu_for(self, item: InfobaseItem, key: str) -> QMenu:
        """Меню группы по её источнику — единственное место, решающее «можно ли».

        Круг правок 1 ревью задачи 12: до этой правки правило «общий список
        только для чтения» проверялось по отдельному guard'у на каждую
        операцию (`remove_group` его получил, `rename_group`/`add_group` —
        нет, и пользователь получал открывшийся диалог правки или сообщение
        «Группы «X» в списке нет» про группу, которая у него на экране).
        Теперь решение принимается один раз здесь, до показа меню: группа
        общего списка получает `_build_disabled_group_menu` (те же три
        неактивных пункта, что у неявного узла, только пояснение —
        `COMMON_NOTE`), пользовательская — полное `_build_group_menu`.
        `remove_group` сохраняет собственную проверку источника как
        последний рубеж (метод достижим напрямую, в обход меню — см. его
        докстринг), но эта проверка больше не единственная защита.
        """  # noqa: RUF002
        if item.source is InfobaseSource.COMMON:
            return self._build_disabled_group_menu(COMMON_NOTE)
        return self._build_group_menu(item, key)

    def _show_menu(self, position: QPoint) -> None:
        index = self._tree.indexAt(position)
        if not index.isValid():
            self._build_empty_space_menu().exec(self._tree.viewport().mapToGlobal(position))
            return
        kind = index.siblingAtColumn(0).data(KIND_ROLE)
        key = index.siblingAtColumn(0).data(KEY_ROLE)
        if kind == RowKind.IMPLICIT_GROUP.value:
            self._build_implicit_group_menu().exec(self._tree.viewport().mapToGlobal(position))
            return
        if kind == RowKind.GROUP.value and key:
            item = next((i for i in self._workspace.items() if i.key == key), None)
            if item is None:
                return
            self._group_menu_for(item, key).exec(self._tree.viewport().mapToGlobal(position))
            return
        if kind != RowKind.BASE.value or not key:
            return
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return
        menu = self._build_menu(item, key)
        menu.exec(self._tree.viewport().mapToGlobal(position))

    # -- Задача 12: создание, переименование, перенос и удаление групп ------

    def _build_add_group_dialog(self, folder: str) -> GroupDialog:
        """Собрать диалог создания группы без показа — тот же приём, что у баз."""  # noqa: RUF002
        return GroupDialog.for_new(self._group_paths(), default_folder=folder, parent=self)

    def add_group(self, folder: str = ROOT) -> None:
        """«Создать группу…» — пустое место дерева (корень) или строка группы."""
        dialog = self._build_add_group_dialog(folder)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_new_group(dialog)

    def _apply_new_group(self, dialog: GroupDialog) -> None:
        """Записать новую группу по данным принятого диалога — отдельно ради тестов.

        Тот же приём, что у `_apply_new_infobase`: `dialog.name_text()` уже
        прошло проверку диалога (непустое, без `/`) при обычном `exec()`, но
        вызов напрямую в обход `_on_accept` (как это делает собственный
        тестовый набор) обязан остаться безопасным — `services.groups`
        второй, самостоятельный рубеж той же проверки.
        """  # noqa: RUF002
        try:
            self._workspace.add_group(dialog.name_text(), dialog.parent_path())
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def _build_group_dialog(self, key: str) -> GroupDialog | None:
        """Собрать диалог переименования/переноса группы без показа."""
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return None
        return GroupDialog(item, self._group_paths(), parent=self)

    def rename_group(self, key: str) -> None:
        """«Переименовать группу…» — правка имени и/или родителя."""
        dialog = self._build_group_dialog(key)
        if dialog is None:
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_group_properties(key, dialog)

    def _apply_group_properties(self, key: str, dialog: GroupDialog) -> None:
        """Применить правки диалога группы — отдельно от exec() ради тестов.

        Пустая пара «имя не менялось, родитель не менялся» не идёт
        в `update_group` вовсе — та же дисциплина задачи 9 для записей:
        нетронутый диалог не должен тронуть файл.
        """
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return
        new_name = dialog.name_text()
        name = new_name if new_name != item.name else None
        new_folder = dialog.parent_path()
        folder = new_folder if new_folder != normalize_folder(item.folder) else None
        if name is None and folder is None:
            return
        try:
            self._workspace.update_group(key, new_name=name, new_folder=folder)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    # -- Задача 14: перенос по группам перетаскиванием -----------------------

    def handle_drop(
        self,
        source_key: str,
        target_key: str | None,
        where: DropTarget,
        *,
        target_is_implicit: bool = False,
        target_is_virtual: bool = False,
    ) -> None:
        """Перенести запись или группу, перетащенную в дереве. §3.3 плана 4b.

        Qt строки не двигает сам: вызывает этот метод и `_BasesTree.dropEvent`
        (перевод настоящего Qt-события), и тест (настоящий drag под offscreen
        не подделать). Модель всегда пересобирается из `Workspace`
        — при отказе операции экран обязан вернуться к тому, что реально
        лежит в файле, а не к тому, что успел нарисовать Qt.

        `target_is_implicit`/`target_is_virtual` — отдельные признаки, а не
        вывод из `target_key is None`: `None` означает три разных исхода —
        «отпустили в пустом месте, значит корень» (`target_key` и так
        `None`, операция разрешена), «отпустили на строке неявного узла»
        ([Ф] T-05.7 — висячий `Folder` без секции, у узла нет ни ключа, ни
        записи в файле) и «отпустили на заголовке ветки или строке ошибки
        общего списка» (`RowKind.SECTION`/`RowKind.NOTE` — не часть файла
        вовсе, `Folder` для них не существует в принципе, а не просто
        неизвестен). Различить эти три исхода по одному `target_key` нельзя
        — различают их два флага, которые `dropEvent` вычисляет структурно,
        по `KIND_ROLE` строки под курсором: `IMPLICIT_GROUP` даёт
        `target_is_implicit`, `SECTION`/`NOTE` — `target_is_virtual`. Тот же
        барьер, что задача 12 нашла для контекстного меню (`_show_menu`,
        `kind == RowKind.IMPLICIT_GROUP.value`) — круг правок 1 этой задачи
        довёл паритет с ним до настоящего: раньше оба флага смешивались
        в один и тот же признак «`KEY_ROLE` пуст», который не отличает
        неявный узел от заголовка ветки.

        Строка общего списка не источник и не цель — тем же структурным
        приёмом, что и у `_group_paths()`/`_group_menu_for` (задача 12),
        а не отдельной проверкой здесь: источник общего списка отсекает
        `Workspace._reject_common` внутри `update_infobase`/`update_group`
        (`ReadOnlySourceError`), а цель общего списка `_target_of_drop`
        не находит вовсе — она ищет только среди `InfobaseSource.USER`.

        Задача 15 добавляет к `BEFORE`/`AFTER` позицию: если источник уже
        лежит в той же группе, что и цель (`source.folder == target.folder`),
        это не перенос, а перестановка — идёт `_reorder`/`Workspace.
        move_within_group`, `Folder` не трогается вовсе. Между разными
        группами позиция по-прежнему не переносится — только сам факт
        переноса, тем же `update_group`/`update_infobase`, что и раньше
        ([Р] ограничение v1 плана 4b, §12).
        """  # noqa: RUF002
        if target_is_implicit:
            self._on_error(
                InvalidRequestError(
                    "Этой группы нет в файле — есть только путь Folder. "
                    "Создайте группу с тем же именем, чтобы класть в неё записи"  # noqa: RUF001
                )
            )
            return
        if target_is_virtual:
            self._on_error(
                InvalidRequestError(
                    "Сюда класть нельзя — это служебная строка раздела "
                    "(заголовок ветки или сообщение об ошибке), а не часть файла"  # noqa: RUF001
                )
            )
            return
        source = next((i for i in self._workspace.items() if i.key == source_key), None)
        if source is None:
            return
        if where is not DropTarget.INTO:
            target = self._target_of_drop(target_key)
            if target is not None and normalize_folder(source.folder) == normalize_folder(
                target.folder
            ):
                self._reorder(source_key, target.key, where)
                return
        folder = self._folder_of_drop(target_key, where)
        if folder is None:
            return
        try:
            if source.is_group:
                self._workspace.update_group(source_key, new_folder=folder)
            else:
                self._workspace.update_infobase(source_key, {"Folder": folder})
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def _reorder(self, key: str, target_key: str, where: DropTarget) -> None:
        """Переставить `key` относительно `target_key` внутри их общей группы.

        Общая точка для мыши (`handle_drop`, вызов выше) и клавиатуры
        (`_move_current`, Alt+↑/Alt+↓) — задача 15. `AFTER` ставит `key` сразу
        за `target_key`; `BEFORE` — перед ним, то есть после настоящего
        предшественника `target_key` в файле (`_sibling_before`) — не после
        того, что визуально стоит перед целью на экране, если фильтр поиска
        что-то спрятал между ними (`handle_drop` вызывается и во время
        активного поиска, а порядок в файле от фильтра не зависит).
        """  # noqa: RUF002
        after_key = target_key if where is DropTarget.AFTER else self._sibling_before(target_key)
        try:
            self._workspace.move_within_group(key, after_key)
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    def _sibling_before(self, target_key: str) -> str | None:
        """Ключ соседа перед целью в её группе — `after_key` для вставки «до».

        Соседи — из `Workspace.items()` в порядке показа: подпоследовательность
        стабильно отсортированного списка совпадает со стабильной сортировкой
        подпоследовательности (см. `order.sort_key`, `edit._apply_reorder`),
        поэтому фильтрация `items()` по родителю уже даёт тот порядок, который
        пересчитает `_apply_reorder` по свежему документу. `None` — цели нет
        среди соседей или она первая: тогда переставляемая запись встаёт
        в начало группы.
        """  # noqa: RUF002
        target = next((i for i in self._workspace.items() if i.key == target_key), None)
        if target is None:
            return None
        parent = normalize_folder(target.folder)
        siblings = [
            item
            for item in self._workspace.items()
            if item.source is InfobaseSource.USER and normalize_folder(item.folder) == parent
        ]
        index = next((i for i, item in enumerate(siblings) if item.key == target_key), None)
        if index is None or index == 0:
            return None
        return siblings[index - 1].key

    def _target_of_drop(self, target_key: str | None) -> InfobaseItem | None:
        """Запись/группа под курсором drop — только из пользовательского источника.

        `target_key is None` (отпустили в пустом месте) не ищется вовсе —
        цели нет, а не «цель — корень» (тем `_folder_of_drop` занимается сам).
        Строка общего списка сюда не попадает: `_folder_of_drop` и `_reorder`
        оба зовут этот метод, и без фильтра по источнику запись из «Общих
        списков» выглядела бы настоящей целью переноса или перестановки.
        """  # noqa: RUF002
        if target_key is None:
            return None
        return next(
            (
                item
                for item in self._workspace.items()
                if item.key == target_key and item.source is InfobaseSource.USER
            ),
            None,
        )

    def _folder_of_drop(self, target_key: str | None, where: DropTarget) -> str | None:
        """Путь `Folder`, куда переносит drop. `None` — переноса не будет.

        `INTO` без цели (`target_key is None`, отпустили в пустом месте) —
        корень. `INTO` на группу — собственный путь этой группы. `BEFORE`/
        `AFTER` — путь родителя цели: сюда попадает только перенос МЕЖДУ
        группами — перестановку внутри одной группы `handle_drop` перехватывает
        раньше и отдаёт `_reorder` (задача 15). Позиция среди соседей при
        переносе между группами по-прежнему не переносится — [Р] ограничение
        v1 плана 4b, §12.

        Запись «внутрь» непустой базы (`where is INTO`, а `target.is_group`
        ложно) даёт `None` — вложить запись в запись нельзя.
        """  # noqa: RUF002
        if target_key is None:
            return ROOT
        target = self._target_of_drop(target_key)
        if target is None:
            return None
        if where is DropTarget.INTO:
            if not target.is_group:
                return None
            return render_folder(group_path(target.folder, target.name))
        return render_folder(normalize_folder(target.folder))

    def _move_current(self, step: int) -> None:
        """Переставить текущую запись/группу на шаг: −1 — вверх, +1 — вниз.

        Сосед берётся из отфильтрованного дерева — соседней строки модели
        (`self._rows`/`build_model`, то же, что рисует поиск), а не из полного
        `Workspace.items()`: во время поиска настоящий сосед по файлу мог быть
        скрыт фильтром, и перестановка мимо него удивила бы пользователя.
        `handle_drop`/`_reorder`, наоборот, всегда берут соседа из полного
        порядка — там цель уже найдена курсором, а не соседством в списке.

        Виртуальные ветки (Избранное/Недавние/Общие списки) не переставляются:
        их порядок не хранится в `OrderInList` (`_is_in_file_tree`).
        """  # noqa: RUF002
        index = self._tree.currentIndex().siblingAtColumn(0)
        if not index.isValid() or not self._is_in_file_tree(index):
            return
        kind = index.data(KIND_ROLE)
        key = index.data(KEY_ROLE)
        if kind not in (RowKind.BASE.value, RowKind.GROUP.value) or not isinstance(key, str):
            return
        model = self._tree.model()
        parent = index.parent()
        neighbor_row = index.row() + step
        if neighbor_row < 0 or neighbor_row >= model.rowCount(parent):
            return
        neighbor = model.index(neighbor_row, 0, parent)
        if neighbor.data(KIND_ROLE) not in (RowKind.BASE.value, RowKind.GROUP.value):
            # Implicit-узел или другая невещественная строка между соседями —
            # не настоящий сосед по файлу, переставлять относительно него
            # нечего (задача 15 не разбирает этот редкий случай подробнее).
            return
        neighbor_key = neighbor.data(KEY_ROLE)
        if not isinstance(neighbor_key, str):
            return
        where = DropTarget.AFTER if step > 0 else DropTarget.BEFORE
        self._reorder(key, neighbor_key, where)

    def _is_in_file_tree(self, index: QModelIndex) -> bool:
        """Строка принадлежит дереву файла, а не виртуальной ветке.

        «Избранное»/«Недавние» строятся отдельным правилом (время запуска),
        «Общие списки» — только для чтения; переставлять в них нечего и некуда.
        Проверка идёт по всей цепочке предков, а не только по первому уровню:
        «Общие списки» вкладывают в себя настоящее поддерево групп, и запись
        внутри него — тоже не часть редактируемого дерева.
        """  # noqa: RUF002
        node = index.parent()
        while node.isValid():
            if node.data(KIND_ROLE) == RowKind.SECTION.value:
                return False
            node = node.parent()
        return True

    def _find_group_node(self, key: str) -> TreeNode | None:
        """Узел дерева группы по ключу — для подсчёта содержимого перед удалением."""

        def walk(nodes: Sequence[TreeNode]) -> TreeNode | None:
            for node in nodes:
                if node.item is not None and node.item.key == key:
                    return node
                found = walk(node.children)
                if found is not None:
                    return found
            return None

        return walk(self._workspace.tree())

    def remove_group(self, key: str) -> None:
        """«Удалить группу…» — обязательство 3 блока Б: подтверждение видит содержимое.

        [Ф] T-05.9 (эксперимент 05.08.2026): штатный стартер задаёт один
        и тот же вопрос «Удалить группу "имя"?» и для пустой, и для непустой
        группы и по «Да» молча каскадит всё поддерево. Быть не хуже
        недостаточно — здесь `group_contents` считает содержимое по всему
        поддереву заранее, `self._ask_group_removal` показывает его
        пользователю и возвращает решение (`RECURSIVE`/`PROMOTE`/`None`
        — отказ).

        Два защитных барьера — не UI-путь, а последний рубеж самого опасного
        метода задачи (круг правок 1 ревью):

        - **Ключ не группы.** `_find_group_node`/`group_contents` не различают
          вид секции — узел базы тоже проходит их обход (только без потомков),
          и без явной проверки пользователь увидел бы «Удалить группу
          "Демо Розница"? Группа пуста.» вместо диагностики. Две строки
          переводят правило из соглашения (меню предлагает пункт только
          группам) в структуру метода.
        - **Группа общего списка.** С круга правок 1 `_group_menu_for` уже
          не предлагает «Удалить группу…» для `InfobaseSource.COMMON`
          (см. её докстринг) — этот путь из UI недостижим. Проверка здесь
          остаётся: метод достижим напрямую (тесты, потенциальные будущие
          вызовы в обход меню), а `Workspace.tree()` строится только
          по пользовательскому источнику — без проверки `_find_group_node`
          не нашёл бы группу общего списка и выдал вводящее в заблуждение
          «группа не найдена» вместо `ReadOnlySourceError`, та же причина,
          по которой `Workspace.update_group`/`remove_group` отвергают такую
          группу при записи (`_reject_common`).
        """  # noqa: RUF002
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return
        if not item.is_group:
            self._on_error(
                InvalidRequestError(f"«{item.name}» — не группа, а запись базы")  # noqa: RUF001
            )
            return
        if item.source is InfobaseSource.COMMON:
            self._on_error(
                ReadOnlySourceError(
                    f"«{item.name}» — группа из общего списка, доступна только "
                    "для чтения"
                )
            )
            return
        node = self._find_group_node(key)
        if node is None:
            self._on_error(
                UnknownItemError(
                    "Группа не найдена в дереве — возможно, список изменился "
                    "извне. Обновите список и повторите"
                )
            )
            return
        names, bases, groups = group_contents(node)
        removal = self._ask_group_removal(self, item.name, names, bases, groups)
        if removal is None:
            return
        try:
            if not self._workspace.remove_group(key, removal):
                self._on_error(
                    UnknownItemError(
                        "Группа не найдена в файле — возможно, список изменился "
                        "извне. Обновите список и повторите"
                    )
                )
        except ServicesError as error:
            self._on_error(error)
        self.rebuild()

    # -- Задача 20: приём каталога вне дерева (панель пути, поле поиска) -----

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Бросок вне дерева — каталог всегда идёт в корень.

        Позиция вне дерева ни на какую строку не указывает: нет ни ключа
        цели, ни её вида, поэтому `add_infobase_from_directory` зовётся
        только с каталогом, без `target_key`/`kind` (в отличие от
        `_BasesTree.dropEvent`, который передаёт оба).
        """  # noqa: RUF002
        directory = dropped_directory(event.mimeData())
        if directory is None:
            return
        self.add_infobase_from_directory(directory)
        event.acceptProposedAction()
