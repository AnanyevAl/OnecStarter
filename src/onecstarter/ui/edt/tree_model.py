"""Модель дерева раздела «EDT» (спека v3, §7): группы, записи, версия, статус.

Модель собирается заново на каждую перестройку — тот же приём, что
`ui/bases/tree_model.py`: порядок и вложенность даёт координатор,
здесь только раскладка по колонкам и подсветка.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel

from onecstarter.domain.edt import EdtProject
from onecstarter.services.edt import EdtStatus, EdtWorkspace
from onecstarter.ui.edt.icons import running_icon
from onecstarter.ui.theme import Palette

ID_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2
KIND_GROUP = "group"
KIND_PROJECT = "project"

COLUMNS = ("Проект", "EDT")
MISSING_SUFFIX = " (нет каталога)"
NOT_INSTALLED_HINT = "EDT {version} не найден"
NO_VERSION_HINT = "Версия EDT не задана"
CLI_BUSY_HINT = "Выполняется команда CLI"


def matches(project: EdtProject, query: str) -> bool:
    needle = query.casefold().strip()
    if not needle:
        return True
    return needle in project.name.casefold() or needle in project.workspace.casefold()


def build_edt_model(workspace: EdtWorkspace, query: str, palette: Palette) -> QStandardItemModel:
    model = QStandardItemModel(0, len(COLUMNS))
    model.setHorizontalHeaderLabels(list(COLUMNS))
    _fill(model.invisibleRootItem(), None, workspace, query, palette)
    return model


def _fill(
    parent: QStandardItem,
    group_id: str | None,
    workspace: EdtWorkspace,
    query: str,
    palette: Palette,
) -> bool:
    """Заполнить детей `group_id`; вернуть, есть ли среди них видимые строки.

    Без фильтра группа видна всегда, даже пустая: иначе «Создать группу»
    записывала бы в `edt.json` группу, которую нечем показать, использовать
    и удалить (C1 финального ревью ветки). Под непустым фильтром показываются
    только группы, в которых есть совпадения (спека §7).
    """
    groups, projects = workspace.children(group_id)
    unfiltered = not query.strip()
    visible = False
    for group in groups:
        item = QStandardItem(group.name)
        item.setEditable(False)
        item.setData(group.id, ID_ROLE)
        item.setData(KIND_GROUP, KIND_ROLE)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        has_matches = _fill(item, group.id, workspace, query, palette)
        if has_matches or unfiltered:
            parent.appendRow([item, _plain("")])
            visible = True
    for project in projects:
        if not matches(project, query):
            continue
        parent.appendRow(_project_row(project, workspace.status(project.id), palette))
        visible = True
    return visible


def _plain(text: str) -> QStandardItem:
    item = QStandardItem(text)
    item.setEditable(False)
    return item


def _project_row(project: EdtProject, status: EdtStatus, palette: Palette) -> list[QStandardItem]:
    name = _plain(project.name + (MISSING_SUFFIX if status.workspace_present is False else ""))
    name.setData(project.id, ID_ROLE)
    name.setData(KIND_PROJECT, KIND_ROLE)
    tooltip = project.workspace
    if project.project_dir:
        tooltip += f"\nПроект: {project.project_dir}"  # noqa: RUF001
    if status.running_pid is not None:
        name.setIcon(running_icon(palette))
        tooltip += f"\nЗапущен (PID {status.running_pid})"  # noqa: RUF001
    name.setToolTip(tooltip)

    version = _plain(project.edt_version or "—")
    if not project.edt_version:
        version.setToolTip(NO_VERSION_HINT)
        version.setForeground(QBrush(QColor(palette.text_dim)))
    elif not status.installed:
        version.setToolTip(NOT_INSTALLED_HINT.format(version=project.edt_version))
        version.setForeground(QBrush(QColor(palette.problem)))

    return [name, version]
