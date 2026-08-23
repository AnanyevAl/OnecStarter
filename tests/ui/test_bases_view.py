import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from PySide6.QtCore import (
    QEvent,
    QMimeData,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    QStandardPaths,
    Qt,
    QUrl,
)
from PySide6.QtGui import QDragMoveEvent, QDropEvent, QKeyEvent, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QTreeView, QWidget

from onecstarter.config.shell_link import build_shell_link, safe_file_name, shortcut_command
from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.launch import ClientKind, LaunchCommand
from onecstarter.domain.version import Installation
from onecstarter.services.cache import CacheEntry, CacheKind, EntryKind
from onecstarter.services.display import COMMON_NOTE, IMPLICIT_NOTE, RowKind
from onecstarter.services.errors import (
    InvalidRequestError,
    LaunchError,
    ReadOnlySourceError,
    ServicesError,
    UnknownItemError,
    UserDataWriteError,
)
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.launch import LaunchOutcome
from onecstarter.services.model import InfobaseItem
from onecstarter.services.paths import ROOT, group_path, normalize_folder, render_folder
from onecstarter.services.settings import DEFAULT_RECENT_LIMIT
from onecstarter.ui import theme
from onecstarter.ui.bases.icons import placement_icon
from onecstarter.ui.bases.tree_model import KEY_ROLE, KIND_ROLE
from onecstarter.ui.bases.view import BasesView, DropTarget
from onecstarter.ui.dialogs.confirm import ask_group_removal, confirm_removal
from onecstarter.ui.dialogs.group import GroupDialog
from onecstarter.ui.dialogs.infobase import InfobaseDialog
from tests.unit.test_cache import FakeCacheOps

from .conftest import COMMON_BASE_KEY, COMMON_GROUP_KEY, COMMON_GROUP_NAME, INSTALLED


def _view(
    qtbot: Any,
    workspace_factory: Any,
    installations: Sequence[Installation] | None = INSTALLED,
    errors: list[ServicesError] | None = None,
    confirm_removal: Callable[[QWidget | None, InfobaseItem], bool] | None = None,
    ask_group_removal: Callable[
        [QWidget | None, str, Sequence[str], int, int], GroupRemoval | None
    ]
    | None = None,
    choose_shortcut_path: Callable[[QWidget | None, str], str] | None = None,
    cfg_paths: tuple[Path, ...] = (),
    cache_env: Mapping[str, str] | None = None,
    cache_ops: Any | None = None,
    confirm_cache_clear: Callable[[QWidget | None, str], bool] | None = None,
    show_cache_report: Callable[[QWidget | None, str], None] | None = None,
) -> tuple[BasesView, list[LaunchCommand], list[ServicesError], list[str]]:
    # По умолчанию — INSTALLED, не None: большинство тестов файла ничего
    # не знают про фоновое обнаружение и ждут готовых версий сразу.
    # Явный installations=None — отдельный случай («обнаружение ещё
    # не закончилось», T-04.6 §3.4), а не синоним «используй умолчание»;  # noqa: RUF003
    # workspace_factory(None, ...) сама подставит INSTALLED для Workspace —
    # пробел здесь только у BasesView, у объекта под тестом.  # noqa: RUF003
    workspace, calls, opened = workspace_factory(installations, cfg_paths=cfg_paths)
    recorded = errors if errors is not None else []
    kwargs: dict[str, Any] = {}
    if confirm_removal is not None:
        # Инъекция, а не монки-патч модуля (задача 11): реальный  # noqa: RUF003
        # `confirm_removal` открывает блокирующий QMessageBox.exec(),
        # который в офскрин-тесте никогда не получит клика — тесты remove_key
        # обязаны подменять именно этот параметр конструктора.
        kwargs["confirm_removal"] = confirm_removal
    if ask_group_removal is not None:
        # Тот же приём для удаления группы (задача 12).
        kwargs["ask_group_removal"] = ask_group_removal
    if choose_shortcut_path is not None:
        # Тот же приём для «Создать ярлык…» (задача 17): настоящий
        # `QFileDialog.getSaveFileName` в офскрин-тесте не дождётся выбора.
        kwargs["choose_shortcut_path"] = choose_shortcut_path
    if cache_env is not None:
        kwargs["cache_env"] = cache_env
    if cache_ops is not None:
        # Инъекция ФС кэша: настоящая WindowsCacheOps ходила бы в живые
        # каталоги %LOCALAPPDATA% машины, на которой идёт прогон.
        kwargs["cache_ops"] = cache_ops
    if confirm_cache_clear is not None:
        # Тот же приём, что confirm_removal: настоящий диалог блокирует офскрин.
        kwargs["confirm_cache_clear"] = confirm_cache_clear
    if show_cache_report is not None:
        kwargs["show_cache_report"] = show_cache_report
    view = BasesView(
        workspace,
        installations=installations,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
        on_error=recorded.append,
        **kwargs,
    )
    qtbot.addWidget(view)
    return view, calls, recorded, opened


def _iter_tree(model: Any, parent: QModelIndex | None = None) -> Iterator[QModelIndex]:
    """Все индексы колонки 0 дерева модели, в глубину, в порядке модели.

    Единственный обходчик на файл (долг ревью 4b, №4 — раньше тот же
    рекурсивный скелет жил семью копиями): роли выставлены только
    на колонке 0 (`ui/bases/tree_model.py`), поэтому предикаты
    вызывающих — поверх этих индексов.
    """  # noqa: RUF002
    parent = QModelIndex() if parent is None else parent
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        yield index
        yield from _iter_tree(model, index)


def _column_texts(view: BasesView, column: int) -> list[str]:
    """Текст заданной колонки во всех строках-базах (RowKind.BASE) дерева.

    Только RowKind.BASE — «у всех не-групп» в вызывающих тестах означает
    именно записи, а не секции/заметки/неявные узлы, у которых своя
    логика колонки версии (build_model их не заполняет вовсе). Строка-база
    может встретиться в дереве дважды («Недавние»/«Избранное» — те же
    ключи, что и в дереве файла, display_forest), дубли не схлопываются:
    вызывающему тесту нужен факт «эта колонка нигде не „…“», а не счётчик.
    """  # noqa: RUF002
    return [
        str(index.siblingAtColumn(column).data() or "")
        for index in _iter_tree(view.model())
        if index.data(KIND_ROLE) == RowKind.BASE.value
    ]


def test_pending_installations_show_ellipsis_then_versions(qtbot, workspace_factory):
    """Спека T-04.6, §3.4: до готовности обнаружения — «…», не пустой список.

    Веб-база («Портал» в анонимизированной фикстуре) исключена из
    сравниваемого множества: version_cell отдаёт ей "веб" безусловно,
    раньше проверки discovery_pending (services/display.py) — у неё нет
    платформы, которую можно было бы «ещё не обнаружить», и это не имеет
    отношения к тому, что здесь проверяется.
    """  # noqa: RUF002
    view, *_ = _view(qtbot, workspace_factory, installations=None)
    pending_texts = {text for text in _column_texts(view, column=1) if text != "веб"}
    assert pending_texts == {"…"}

    view.apply_installations(INSTALLED)

    resolved_texts = _column_texts(view, column=1)
    assert "…" not in resolved_texts


def _type(widget: QWidget, text: str) -> None:
    """Набрать текст посимвольно в обход qtbot.keyClicks.

    На этой машине (PySide6 6.11.1, Qt 6.11.1, QT_QPA_PLATFORM=offscreen)
    QTest.keyClicks зависает насмерть на кириллице — воспроизводится и на
    голом QLineEdit без единой строчки кода проекта, значит баг в
    биндинге/платформенном плагине, а не в реализации. Однобуквенный
    QTest.keyClick(widget, char) не зависает, но портит небайтовые символы
    (наблюдался мохибейк: UTF-8 байты символа возвращались как два разных
    Latin-1 символа). Рабочий обходной путь — тот же приём, которым Qt
    пользуется внутри qWait: собрать QKeyEvent с текстом и отправить его
    виджету напрямую, в обход платформенной раскладки клавиатуры.
    Поведение виджета (посимвольный textChanged) не отличается от реального
    набора — проверено: количество сигналов textChanged равно длине текста.
    """  # noqa: RUF002
    for char in text:
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(
                widget, QKeyEvent(kind, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, char)
            )


def _find_index(view: BasesView, predicate: Any, message: str) -> QModelIndex:
    """Первый индекс дерева (преордер `_iter_tree`), прошедший предикат."""
    index = next((i for i in _iter_tree(view.model()) if predicate(i)), None)
    assert index is not None, message
    return index


def _first_base_index(view: BasesView) -> QModelIndex:
    """Первая строка с KIND_ROLE == RowKind.BASE.value, обходом всего дерева."""  # noqa: RUF002
    return _find_index(
        view,
        lambda i: i.data(KIND_ROLE) == RowKind.BASE.value,
        "в дереве нет ни одной строки базы",
    )


def _select_first_file_base(view: BasesView) -> None:
    """Выбрать первую не-WEB базу — для неё F3/F4 обязаны запускать процесс."""
    item = next(
        i for i in view.workspace().items()
        if not i.is_group and i.kind is not ConnectKind.WEB
    )
    _select_key(view, item.key)


def _select_first_web_base(view: BasesView) -> None:
    """Выбрать первую WEB-базу — явный клиент (F4) для неё не запускается."""
    item = next(
        i for i in view.workspace().items()
        if not i.is_group and i.kind is ConnectKind.WEB
    )
    _select_key(view, item.key)


def _spy_on(monkeypatch: Any, workspace: Any, name: str) -> list[tuple[Any, Any]]:
    """Записывать вызовы метода `Workspace`, не меняя его поведения.

    Финальное ревью, C1: сторожа «нетронутый диалог не пишет в файл»
    сравнивали байты файла до и после, а `services/writer.py` сам не пишет,
    когда патч не изменил ни байта. Байтовое сравнение поэтому не отличает
    «до `update_infobase` не дошли» от «дошли, а writer решил не писать» —
    и оставалось зелёным, когда обе проверки `if not changes ...: return`
    заменялись на `pass`. Спай смотрит на факт вызова, то есть ровно
    на то, что эти проверки и обещают.

    Оригинал вызывается дальше намеренно: сторож обязан оставаться сторожем
    и на положительном пути (соседний тест доказывает, что спай срабатывает,
    когда правка есть), иначе «вызовов не было» могло бы означать просто
    неудачно поставленный спай.
    """  # noqa: RUF002
    calls: list[tuple[Any, Any]] = []
    original = getattr(workspace, name)

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace, name, spy)
    return calls


def _index_of_key(view: BasesView, key: str) -> QModelIndex:
    """Индекс строки с данным ключом привязки (KEY_ROLE колонки 0)."""  # noqa: RUF002
    return _find_index(
        view,
        lambda i: i.data(KEY_ROLE) == key,
        f"строка с ключом {key!r} не найдена в дереве",  # noqa: RUF001
    )


def _select_key(view: BasesView, key: str) -> None:
    """Поставить currentIndex дерева на строку базы с данным ключом."""  # noqa: RUF002
    view._tree.setCurrentIndex(_index_of_key(view, key))


def test_tree_is_populated_from_file(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert "Клиенты" in labels
    assert "Учёт серверный" in labels
    assert "Нет такой группы" in labels  # неявный узел


def test_typing_filters_tree(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    _type(view.search(), "демо роз")
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert labels == ["Клиенты"]


def test_column_width_survives_search_that_shortens_visible_names(qtbot, workspace_factory):
    # Smoke №1 (08.08.2026), замечание 3: rebuild() звал resizeColumnToContents
    # для каждой колонки при каждой пересборке, а фильтр оставляет короткие  # noqa: RUF003
    # имена — колонка «База» схлопывалась на первой же букве поиска.
    view, _, _, _ = _view(qtbot, workspace_factory)
    before = view._tree.columnWidth(0)
    _type(view.search(), "порт")  # "Портал" — заметно короче полного дерева
    assert view._tree.columnWidth(0) == before


def test_enter_in_search_launches_first_visible_base(qtbot, workspace_factory):
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    _type(view.search(), "демо бух")  # noqa: RUF001
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert errors == []
    assert len(calls) == 1
    assert '/IBName"Демо Бухгалтерия"' in calls[0].command_line
    assert "/AppAutoCheckVersion-" in calls[0].command_line


def test_activating_group_row_does_not_launch(qtbot, workspace_factory):
    # Спека 4a, §3: Enter и двойной клик по группе, неявному узлу или
    # заголовку ветки ничего не запускают. Проверяются и вызовы, и ошибки:
    # без guard'а запуск группы дал бы LaunchError в on_error, а не вызов.  # noqa: RUF003
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    model = view.model()
    group_item = next(
        model.item(i, 0) for i in range(model.rowCount())
        if model.item(i, 0).text() == "Клиенты"
    )
    view._launch_index(model.indexFromItem(group_item))
    assert calls == []
    assert errors == []


def test_launch_error_goes_to_handler_not_up(qtbot, workspace_factory):
    view, calls, errors, _ = _view(qtbot, workspace_factory, installations=[])
    _type(view.search(), "демо бух")  # noqa: RUF001
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert calls == []
    assert len(errors) == 1
    assert isinstance(errors[0], LaunchError)


def test_favorite_toggle_shows_favorites_branch(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    view.toggle_favorite(key)
    first = view.model().item(0, 0)
    assert first.text() == "Избранное"
    assert first.child(0, 0).text() == "Демо Бухгалтерия"


def test_recent_branch_appears_after_launch(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    _type(view.search(), "демо бух")  # noqa: RUF001
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    view.search().clear()
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert labels[0] == "Недавние"


def test_rebuild_rereads_keys_from_workspace(qtbot, workspace_factory):
    # Спека 4a, §2: после операции UI берёт свежие items()/tree(), ключи
    # не кешируются — они меняются при дописывании ID.
    view, _, _, _ = _view(qtbot, workspace_factory)
    workspace = view.workspace()
    path = workspace.paths.ibases
    path.write_bytes(path.read_bytes() + '[Новая]\r\nConnect=File="C:\\N";\r\n'.encode())
    assert workspace.reload_if_changed()
    view.rebuild()
    labels = [view.model().item(i, 0).text() for i in range(view.model().rowCount())]
    assert "Новая" in labels


def test_web_base_context_menu_has_only_browser_action(qtbot, workspace_factory):
    # Ветка ConnectKind.WEB в _build_menu: у веб-базы нет исполняемого файла,  # noqa: RUF003
    # поэтому пункты клиентов («Тонкий клиент», «Конфигуратор») не показываются
    # (services/launch.py — веб-база открывается браузером, а не процессом).  # noqa: RUF003
    view, _, _, _ = _view(qtbot, workspace_factory)
    item = next(i for i in view.workspace().items() if i.name == "Портал")
    menu = view._build_menu(item, item.key)
    texts = [action.text() for action in menu.actions()]
    assert any("Открыть в браузере" in text for text in texts)
    assert not any("Тонкий клиент" in text for text in texts)
    assert not any("Конфигуратор" in text for text in texts)


def test_context_menu_has_properties_action(qtbot, workspace_factory):
    """Пункт «Свойства…» (задача 8) — состав меню проверяется без exec()."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    item = next(i for i in view.workspace().items() if i.key == key)
    menu = view._build_menu(item, key)
    texts = [action.text() for action in menu.actions()]
    assert "Свойства…" in texts


# -- отказ записи bases.json доходит до пользователя (финальное ревью, I9) ----
#
# Ловцы в `BasesView` ловят `ServicesError`, а `save_user_data` поднимала  # noqa: RUF003
# голую `OSError` — `Ctrl+D` молча не ставил звёздочку, запуск базы молча
# не обновлял «Последний запуск». Под `pythonw.exe` даже без трассировки.


def _block_user_data(view: BasesView) -> None:
    """Каталог на месте `bases.json`: запись падает, чтение уже состоялось."""
    path = view.workspace().paths.user_data
    if path.is_file():
        path.unlink()
    path.mkdir()


def test_favorite_write_failure_is_shown_and_not_drawn(qtbot, workspace_factory):
    """Отказ виден пользователю, и звёздочка на экране не появляется.

    `rebuild()` стоит после `try`, поэтому без отката состояния в services
    экран показал бы избранное, которого в файле нет.
    """
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _block_user_data(view)

    view.toggle_favorite(key)

    assert len(errors) == 1
    assert isinstance(errors[0], UserDataWriteError)
    assert not next(i for i in view.workspace().items() if i.key == key).favorite
    assert view.model().item(0, 0).text() != "Избранное"


def test_launch_write_failure_is_shown_after_a_real_launch(qtbot, workspace_factory):
    """База запущена, «Последний запуск» не сохранён — и об этом сказано."""  # noqa: RUF002
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    _block_user_data(view)

    view.launch_key("id:44444444-4444-4444-4444-444444444444")

    assert len(calls) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], UserDataWriteError)
    assert "База запущена" in str(errors[0])


# -- отказ до действия: меню записи из общего списка (финальное ревью, I7) ----
#
# Правило «решение „можно ли“ принимается один раз, до показа меню» завёл
# круг правок 1 задачи 12 — но только для групп (`_group_menu_for`). У записи  # noqa: RUF003
# из общего списка все восемь пунктов оставались включёнными: «Удалить
# из списка…» показывала подтверждение и лишь ПОСЛЕ «Да» приносила
# `ReadOnlySourceError`, а «Свойства…» открывали полностью редактируемый  # noqa: RUF003
# диалог. Решение заказчика: отказ показывается раньше, тем же механизмом,
# что и у групп, — неактивный пункт с пояснением.  # noqa: RUF003


def _menu_actions(menu: Any) -> dict[str, Any]:
    return {action.text(): action for action in menu.actions() if action.text()}


def test_common_record_menu_disables_the_writing_actions(
    qtbot, workspace_factory, common_base_cfg_paths
):
    """«Свойства…» и «Удалить из списка…» неактивны и объясняют почему."""
    view, _, _, _ = _view(qtbot, workspace_factory, cfg_paths=common_base_cfg_paths)
    item = next(i for i in view.workspace().items() if i.key == COMMON_BASE_KEY)

    actions = _menu_actions(view._build_menu(item, item.key))

    for label in ("Свойства…", "Удалить из списка…"):
        assert not actions[label].isEnabled(), label
        assert actions[label].toolTip() == COMMON_NOTE, label


def test_common_record_menu_keeps_the_harmless_actions_working(
    qtbot, workspace_factory, common_base_cfg_paths
):
    """Запуск, ярлык и избранное для записи общего списка остаются доступны.

    Первые два в файл списка не пишут вовсе, третий пишет только в наши
    данные (`bases.json`), к которым источник записи отношения не имеет.
    Гасить их значило бы отобрать работающие операции ради симметрии.
    """
    view, _, _, _ = _view(qtbot, workspace_factory, cfg_paths=common_base_cfg_paths)
    item = next(i for i in view.workspace().items() if i.key == COMMON_BASE_KEY)

    actions = _menu_actions(view._build_menu(item, item.key))

    for label in ("Запустить\tF3", "Создать ярлык…", "В избранное\tCtrl+D"):  # noqa: RUF001
        assert actions[label].isEnabled(), label


def test_user_record_menu_keeps_every_action_enabled(qtbot, workspace_factory):
    """Обратная сторона: у своей записи не гаснет ничего."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    item = next(i for i in view.workspace().items() if i.key == key)

    actions = _menu_actions(view._build_menu(item, key))

    assert actions
    assert all(action.isEnabled() for action in actions.values())


def test_properties_dialog_is_built_for_the_requested_item(qtbot, workspace_factory):
    """Ревью задачи 8, круг 1: единственный путь к диалогу разделён на

    «собрать» и «показать» — тем же приёмом, что у `_build_menu`/`_show_menu`
    — чтобы состав можно было проверить без блокирующего `exec()`.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    assert dialog.name_text() == "Демо Бухгалтерия"


def test_properties_dialog_is_none_for_a_missing_key(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    assert view._build_properties_dialog("id:does-not-exist") is None


def test_properties_dialog_gets_real_installations_and_groups(qtbot, workspace_factory):
    """Проброс параметров: не пустые заглушки, а реальные installations/группы.

    `version_hint()` содержит установленную версию только если `installations`
    дошли до диалога; `groups_shown()` содержит путь реальной группы фикстуры
    только если `_group_paths()` действительно вызван и передан.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    assert "8.3.25.1633" in dialog.version_hint()
    assert "Клиенты" in dialog.groups_shown()


def test_apply_properties_writes_the_rename(qtbot, workspace_factory):
    """Задача 9: `_apply_properties` — то, что реально исполняет `dialog.exec()`

    после Accepted (отделено ради тестов тем же приёмом, что build/show).
    Проверка идёт через `Workspace.items()`, а не байты файла: маршрут
    записи (`update_infobase` → `write_patch`) уже покрыт в services.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_name("Бухгалтерия 3.0")
    view._apply_properties(key, dialog)
    assert errors == []
    renamed = next(i for i in view.workspace().items() if i.key == key)
    assert renamed.name == "Бухгалтерия 3.0"


def test_apply_properties_on_untouched_dialog_does_not_write(
    qtbot, workspace_factory, monkeypatch
):
    """Открыл и закрыл кнопкой «ОК» — до `update_infobase` дело не доходит.

    Дополняет `test_untouched_dialog_reports_no_changes` (dialogs-уровень)
    проверкой на реальном маршруте записи: `_apply_properties` не должен
    дойти до `update_infobase`/`write_patch`, если `dialog.changes()` пуст.

    Финальное ревью, C1: раньше здесь стояло только байтовое сравнение
    файла, и замена сторожа `if not changes and new_name is None: return`
    на `pass` весь набор проходил — `services/writer.py` сам не пишет,
    когда патч не изменил ни байта, и байты одинаковы в обоих случаях.
    Различие существенно: дойдя до `Workspace.update_infobase`, первая же
    запись без `ID` получила бы дописанный `ID` — чужой файл изменён,
    ключ привязки сменился. Проверяется поэтому факт вызова; байтовое
    сравнение осталось рядом вторым, независимым утверждением.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    calls = _spy_on(monkeypatch, view.workspace(), "update_infobase")
    before = view.workspace().paths.ibases.read_bytes()

    view._apply_properties(key, dialog)

    after = view.workspace().paths.ibases.read_bytes()
    assert calls == []
    assert errors == []
    assert after == before


def test_apply_properties_calls_the_writer_when_something_changed(
    qtbot, workspace_factory, monkeypatch
):
    """Обратная сторона сторожа C1: спай обязан срабатывать, когда правка есть.

    Без этой пары «вызовов не было» в соседнем тесте могло бы означать
    неудачно поставленный спай, а не сработавший сторож.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_name("Бухгалтерия 3.0")
    calls = _spy_on(monkeypatch, view.workspace(), "update_infobase")

    view._apply_properties(key, dialog)

    assert errors == []
    assert len(calls) == 1
    assert calls[0][0][0] == key


class _RaisingChanges:
    """Двойник диалога, чей `changes()` падает `KeyError` — C3, круг правок 1.

    Диалог сам отфильтровывает поля размещения до реально найденных в Connect
    фрагментов, но это его внутренняя дисциплина, а не гарантия типа: граница
    Qt-слота (`_apply_properties`) обязана остаться рабочей, даже если эта
    дисциплина где-то нарушится — не молчаливым крахом слота, а понятной
    ошибкой пользователю.
    """  # noqa: RUF002

    def kind_change_warning(self) -> str | None:
        # Задача 10: _apply_properties проверяет это ПЕРЕД changes() — двойник
        # обязан отвечать, иначе AttributeError случился бы до KeyError,
        # который и проверяет этот тест.
        return None

    def changes(self) -> tuple[dict[str, str | None], str | None]:
        raise KeyError("Srvr")


def test_apply_properties_reports_a_keyerror_from_changes_instead_of_crashing(
    qtbot, workspace_factory
):
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    before = view.workspace().paths.ibases.read_bytes()
    view._apply_properties(key, _RaisingChanges())  # type: ignore[arg-type]
    after = view.workspace().paths.ibases.read_bytes()
    assert len(errors) == 1
    assert "Srvr" in str(errors[0])
    assert after == before


def test_apply_properties_reports_a_valueerror_from_changes_instead_of_crashing(
    qtbot, workspace_factory
):
    """Задача 10: build_connect может поднять ValueError при смене вида —

    тот же приём и та же граница, что и у KeyError выше: `_on_accept` диалога
    обязан остановить запрещённый символ раньше, но `_apply_properties`
    вызван здесь напрямую, в обход `exec()`/`_on_accept` — граница Qt-слота
    не должна рухнуть, даже если эта дисциплина где-то в будущем нарушится.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"  # "Демо Бухгалтерия", FILE
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.SERVER)
    dialog.set_server("s;evil")
    before = view.workspace().paths.ibases.read_bytes()

    view._apply_properties(key, dialog)

    after = view.workspace().paths.ibases.read_bytes()
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)
    assert after == before


def test_ctrl_1_launches_thin_client_on_current_row(qtbot, workspace_factory):
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    _select_key(view, "id:44444444-4444-4444-4444-444444444444")
    view._launch_current(ClientKind.THIN)
    assert errors == []
    assert len(calls) == 1
    assert "1cv8c.exe" in calls[0].command_line


def test_ctrl_d_toggles_favorite_on_current_row(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    _select_key(view, "id:44444444-4444-4444-4444-444444444444")
    view._toggle_current_favorite()
    first = view.model().item(0, 0)
    assert first.text() == "Избранное"
    assert first.child(0, 0).text() == "Демо Бухгалтерия"


def _expansion(view: BasesView) -> list[tuple[str, bool]]:
    """Снять развёрнутость всех узлов дерева, у которых есть потомки."""  # noqa: RUF002
    model = view.model()
    return [
        (index.data(), view._tree.isExpanded(index))
        for index in _iter_tree(model)
        if model.rowCount(index)
    ]


def test_collapsed_state_survives_a_search_cycle(qtbot, workspace_factory):
    # Находка финального ревью 07.08.2026: expandAll() на время поиска
    # затирал слепок развёрнутости, и при возврате к пустому поиску дерево
    # оставалось развёрнутым навсегда. Целевой сценарий (§3 спеки) гонит
    # через поиск каждый запуск — дефект срабатывал в первую же минуту.
    view, _, _, _ = _view(qtbot, workspace_factory)
    before = _expansion(view)
    assert any(not expanded for _label, expanded in before), (
        "фикстура обязана давать хотя бы один свёрнутый узел, иначе тест пуст"
    )
    _type(view.search(), "демо")
    view.search().clear()
    assert _expansion(view) == before


def test_expansion_made_during_search_is_not_remembered(qtbot, workspace_factory):
    # Разворачивание — следствие фильтра, а не выбор пользователя: оно  # noqa: RUF003
    # не должно пережить очистку поиска (иначе слепок «чистого» состояния
    # снова протекал бы через expandAll).
    view, _, _, _ = _view(qtbot, workspace_factory)
    before = _expansion(view)
    _type(view.search(), "демо")
    assert all(expanded for _label, expanded in _expansion(view))
    view.search().clear()
    assert _expansion(view) == before


def test_expansion_by_user_is_remembered_across_search(qtbot, workspace_factory):
    # Обратная сторона: то, что пользователь развернул сам при пустом
    # поиске, обязано вернуться после цикла поиска.
    view, _, _, _ = _view(qtbot, workspace_factory)
    group = _find_index(view, lambda i: i.data() == "Клиенты", "нет узла Клиенты")
    view._tree.expand(group)
    _type(view.search(), "демо")
    view.search().clear()
    assert dict(_expansion(view))["Клиенты"] is True


def test_same_label_nodes_expand_independently(qtbot, workspace_factory):
    # Minor-замечание ревью: маркер развёрнутости для строк без ключа
    # строился из одной метки, поэтому одноимённые узлы на разных ветках
    # разворачивались вместе. Маркер обязан различать их по пути.
    view, _, _, _ = _view(qtbot, workspace_factory)
    workspace = view.workspace()
    path = workspace.paths.ibases
    path.write_bytes(
        path.read_bytes()
        + '[Первая]\r\nConnect=File="C:\\A";\r\nFolder=/Архив/Старое\r\n'.encode()
        + '[Вторая]\r\nConnect=File="C:\\B";\r\nFolder=/Склад/Старое\r\n'.encode()
    )
    assert workspace.reload_if_changed()
    view.rebuild()

    def find(label: str, parent_label: str) -> QModelIndex:
        # Модель берётся заново на каждый вызов: rebuild() пересоздаёт её
        # целиком, и индексы прежней модели после этого невалидны.
        model = view.model()
        for row in range(model.rowCount()):
            top = model.index(row, 0, QModelIndex())
            if top.data() != parent_label:
                continue
            for child in range(model.rowCount(top)):
                index = model.index(child, 0, top)
                if index.data() == label:
                    return index
        raise AssertionError(f"узел {parent_label}/{label} не найден")

    view._tree.expand(find("Старое", "Архив"))
    view.rebuild()
    assert view._tree.isExpanded(find("Старое", "Архив"))
    assert not view._tree.isExpanded(find("Старое", "Склад"))


def test_enter_in_empty_search_launches_nothing(qtbot, workspace_factory):
    # Minor-замечание финального ревью: случайный Enter в пустом поиске
    # (например, сразу после хоткея, до первой буквы) не должен запустить
    # первую базу леса — единственное нажатие запускало бы чужую реальную
    # базу.
    view, calls, errors, opened = _view(qtbot, workspace_factory)
    assert view.search().text().strip() == ""
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert calls == []
    assert opened == []
    assert errors == []


def test_enter_in_whitespace_only_search_launches_nothing(qtbot, workspace_factory):
    # Пробелы без букв — тоже "пустой" поиск после strip().
    view, calls, errors, opened = _view(qtbot, workspace_factory)
    _type(view.search(), "   ")
    qtbot.keyClick(view.search(), Qt.Key.Key_Return)
    assert calls == []
    assert opened == []
    assert errors == []


def test_ctrl_1_on_web_base_does_nothing(qtbot, workspace_factory):
    # Пересмотрено задачей 7 плана 4b (было
    # test_ctrl_1_on_web_base_does_not_pass_forced_client_through, задача 8
    # плана 4a). Тогда исправили только протаскивание forced_client внутрь
    # workspace.launch(); сам запуск (браузер) всё равно происходил — для
    # Ctrl+1/2/3 это было безопасно, потому что меню для WEB прячет эти
    # пункты. С приходом F4 та же лазейка стала обманом («Конфигуратор»  # noqa: RUF003
    # против «открылся браузер»), поэтому теперь явно затребованный клиент
    # для веб-базы — бездействие: workspace.launch не вызывается вовсе, что
    # здесь проверяется и по перехваченному forced_client, и по исходу.
    view, calls, errors, opened = _view(qtbot, workspace_factory)
    portal = next(i for i in view.workspace().items() if i.name == "Портал")
    _select_key(view, portal.key)

    workspace = view.workspace()
    received: list[ClientKind | None] = []
    original_launch = workspace.launch

    def spy_launch(key: str, forced_client: ClientKind | None = None) -> LaunchOutcome:
        received.append(forced_client)
        return original_launch(key, forced_client)

    workspace.launch = spy_launch  # type: ignore[method-assign]

    view._launch_current(ClientKind.THIN)

    assert received == []
    assert errors == []
    assert calls == []
    assert opened == []


def test_panel_follows_selection(qtbot, workspace_factory):
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)
    index = _first_base_index(view)
    view._tree.setCurrentIndex(index)
    assert view.panel().text() != ""


def test_selecting_a_group_row_shows_the_group_hint_in_the_panel(qtbot, workspace_factory):
    """Задача 4 (отложено): деградация к «пустая карточка» проверена в

    services/test_connection.py на panel_card напрямую (Minor 5); здесь —
    тот же сценарий через живое дерево: `_sync_panel` обязан довести
    KIND_ROLE/KEY_ROLE выделенной строки-группы до panel_card, не потеряв
    вид строки по пути.
    """
    view, _, _, _ = _view(qtbot, workspace_factory)
    _select_key(view, _RETAIL_GROUP_KEY)
    assert view.panel().placeholder() == "Группа — строки подключения нет"


def test_rebuild_keeps_current_row_and_panel(qtbot, workspace_factory):
    # Находка ревью задачи 5: rebuild() восстанавливал развёрнутость, но не
    # текущую строку — новая selectionModel после setModel() всегда без
    # текущего индекса, и панель гасла при любой пересборке.
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _select_key(view, key)
    before = view.panel().text()
    assert before != ""
    view.rebuild()
    assert view._current_base_key() == key
    assert view.panel().text() == before


def test_launch_keeps_current_row_selected_and_panel_visible(qtbot, workspace_factory):
    # Ровно сценарий из отчёта ревью: выделили базу → Ctrl+1 (launch_key
    # зовёт rebuild()) → панель не гаснет, строка над ней остаётся той же.
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _select_key(view, key)
    before = view.panel().text()
    view.launch_key(key)
    assert errors == []
    assert len(calls) == 1
    assert view._current_base_key() == key
    assert view.panel().text() == before


def test_search_keeps_current_row_when_still_visible(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _select_key(view, key)
    _type(view.search(), "демо бух")  # noqa: RUF001
    assert view._current_base_key() == key
    assert view.panel().text() != ""


def test_search_clears_current_row_when_filtered_out(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _select_key(view, key)
    _type(view.search(), "zzz-not-a-real-base")
    assert view._current_base_key() is None
    assert view.panel().text() == ""


def test_ctrl_1_after_search_launches_the_selected_base(qtbot, workspace_factory):
    # Латентный дефект ещё из 4a, панель его лишь проявила: текущая строка  # noqa: RUF003
    # терялась при любой пересборке, поэтому Ctrl+1/2/3 после набора текста
    # в поиске не делали ничего — _current_base_key() возвращал None, работал
    # только Enter (он берёт первую видимую, а не текущую строку).  # noqa: RUF003
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _select_key(view, key)
    _type(view.search(), "демо бух")  # noqa: RUF001
    view._launch_current(ClientKind.THIN)
    assert errors == []
    assert len(calls) == 1
    assert "1cv8c.exe" in calls[0].command_line


def _current_path(view: BasesView) -> str:
    return view._path_to(view._tree.currentIndex().siblingAtColumn(0))


def test_launch_from_file_tree_keeps_current_row_in_file_tree(qtbot, workspace_factory):
    # Smoke №1 (08.08.2026), замечание 4: после запуска запись получает
    # last_launched_at и появляется в «Недавние» вдобавок к своему месту
    # в дереве файла — ключ привязки встречается в модели дважды.
    # _restore_current брала первое совпадение маркера по всему дереву,
    # а «Недавние» стоит выше дерева файла в лесу (display_forest) — курсор  # noqa: RUF003
    # уезжал туда, даже если пользователь выделял запись в дереве файла.
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    _select_key(view, key)
    before = _current_path(view)
    assert "Недавние" not in before, "до первого запуска «Недавних» ещё нет"

    view.launch_key(key)

    assert errors == []
    assert len(calls) == 1
    assert view._current_base_key() == key
    assert _current_path(view) == before


def test_launch_from_recent_keeps_current_row_in_recent(qtbot, workspace_factory):
    # Обратная сторона: если пользователь выделил запись именно в «Недавних»,
    # починка не должна жёстко прибивать курсор к дереву файла — тот же
    # маркер встречается дважды, и предпочесть надо точное совпадение пути,
    # а не «всегда дерево файла».  # noqa: RUF003
    view, calls, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    view.launch_key(key)  # первый запуск создаёт ветку «Недавние»
    assert len(calls) == 1

    _select_key(view, key)  # «Недавние» стоит первой веткой — выбирается она
    before = _current_path(view)
    assert "Недавние" in before

    view.launch_key(key)

    assert errors == []
    assert len(calls) == 2
    assert view._current_base_key() == key
    assert _current_path(view) == before


def _show_exposed(qtbot: Any, view: BasesView) -> None:
    """Показать окно и дождаться экспонирования — иначе keyClick не долетает.

    QShortcut по умолчанию живёт в контексте Qt.ShortcutContext.WindowShortcut:
    событие клавиши уходит обработчику, только если его окно — активное.
    qtbot.addWidget() лишь регистрирует виджет для очистки после теста и не
    показывает его, поэтому без явного show() qtbot.keyClick(view, ...) для
    QShortcut молча не срабатывает (проверено экспериментом — с show() тот же
    keyClick тот же дошёл до обработчика). Причина не связана с offscreen-
    платформой: и `qtbot.keyClick(view.search(), ...)` в тестах Enter выше
    работает без show(), потому что событие идёт напрямую в keyPressEvent
    QLineEdit, а не через карту шорткатов приложения.
    """  # noqa: RUF002
    with qtbot.waitExposed(view):
        view.show()


def test_f3_launches_in_default_mode(qtbot: Any, workspace_factory: Any) -> None:
    """F3 — режим «1С:Предприятие», а не выбор клиента.

    Тонкий или толстый решает App секции либо платформа ([Ф] T-02.6),
    поэтому forced_client не передаётся — как у Enter.
    """  # noqa: RUF002
    workspace, calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)
    _show_exposed(qtbot, view)
    _select_first_file_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F3)

    assert len(calls) == 1
    assert "ENTERPRISE" in calls[0].arguments


def test_f4_launches_designer(qtbot: Any, workspace_factory: Any) -> None:
    workspace, calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)
    _show_exposed(qtbot, view)
    _select_first_file_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F4)

    assert len(calls) == 1
    assert "DESIGNER" in calls[0].arguments


def test_f4_does_nothing_for_web_base(qtbot: Any, workspace_factory: Any) -> None:
    """«Открыть Конфигуратор» и «открылся браузер» — разные вещи.

    launch_infobase для WEB игнорирует forced_client, поэтому наивный вызов
    launch_key открыл бы браузер и выдал бы это за Конфигуратор. Тот же обман
    задача 8 плана 4a уже закрыла для Ctrl+1/2/3 — здесь он не должен вернуться.
    """
    workspace, calls, opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)
    _show_exposed(qtbot, view)
    _select_first_web_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F4)

    assert calls == []
    assert opened == []


def test_f3_opens_browser_for_web_base(qtbot: Any, workspace_factory: Any) -> None:
    workspace, _calls, opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)
    _show_exposed(qtbot, view)
    _select_first_web_base(view)

    qtbot.keyClick(view, Qt.Key.Key_F3)

    assert len(opened) == 1


def test_f3_and_f4_shortcuts_are_registered_on_view(qtbot: Any, workspace_factory: Any) -> None:
    """Подстраховка отдельно от поведения: сама привязка клавиш на месте.

    test_f3_*/test_f4_* выше уже проверяют доставку события через реальный
    QShortcut (после show()+waitExposed keyClick доходит), но эта проверка
    зависит от активного окна — хрупкого свойства тестового окружения.
    Здесь — прямая проверка состава QShortcut на виджете, не зависящая
    от фокуса и активности окна: привязка не может остаться непокрытой,
    даже если окружение теста изменится.
    """
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)

    sequences = {shortcut.key().toString() for shortcut in view.findChildren(QShortcut)}

    assert "F3" in sequences
    assert "F4" in sequences


def _icon_bytes(palette: theme.Palette) -> set[bytes]:
    """Байтовые представления всех четырёх значков размещения для палитры."""
    result: set[bytes] = set()
    for kind in ConnectKind:
        image = placement_icon(kind, palette).pixmap(16, 16).toImage()
        result.add(image.constBits().tobytes())  # type: ignore[union-attr]
    return result


def test_menu_shows_f3_f4_hotkeys_customer_is_used_to(qtbot, workspace_factory):
    # Smoke №1 (08.08.2026), замечание 5: задача 7 добавила F3/F4, но не
    # тронула подписи меню — заказчик видел прежние Ctrl+1/2/3 и не видел
    # клавиш, к которым привык по штатному стартеру. Ctrl+1/Ctrl+2 остаются
    # подписями «Тонкий»/«Толстый клиент» — только они дают явный выбор,
    # которого нет у F3. Ctrl+3 остаётся рабочим псевдонимом «Конфигуратора»  # noqa: RUF003
    # (view.py, __init__), но в меню теперь показан F4.
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    item = next(i for i in view.workspace().items() if i.key == key)
    menu = view._build_menu(item, item.key)
    texts = [action.text() for action in menu.actions()]
    assert "Запустить\tF3" in texts
    assert "Тонкий клиент\tCtrl+1" in texts
    assert "Толстый клиент\tCtrl+2" in texts
    assert "Конфигуратор\tF4" in texts
    assert not any("Ctrl+3" in text for text in texts)


def test_theme_switch_leaves_no_stale_colours(qtbot: Any, workspace_factory: Any) -> None:
    """Обе запечённые точки перекрашиваются: QBrush строк и значки размещения.

    Иконка трея в проверку не входит намеренно — она от палитры не зависит
    (спека 4b, §2.4).
    """  # noqa: RUF002
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
        palette=theme.DARK,
    )
    qtbot.addWidget(view)

    view.apply_palette(theme.LIGHT)

    stale = {theme.DARK.text_dim.casefold(), theme.DARK.problem.casefold()}
    icons_dark = _icon_bytes(theme.DARK)

    model = view.model()
    for index in _iter_tree(model):
        item = model.itemFromIndex(index)
        assert item.foreground().color().name().casefold() not in stale
        if not item.icon().isNull():
            pixels = item.icon().pixmap(16, 16).toImage().constBits()
            assert pixels.tobytes() not in icons_dark  # type: ignore[union-attr]


# -- Задача 10: добавление записи ------------------------------------------------


def test_ctrl_n_shortcut_is_registered_on_view(qtbot: Any, workspace_factory: Any) -> None:
    """Подстраховка отдельно от поведения — тот же приём, что у F3/F4 (задача 7).

    Триггер шортката открыл бы модальный `dialog.exec()` и завис бы
    в офскрин-тесте без монопатча — здесь достаточно проверить саму привязку.
    """  # noqa: RUF002
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)

    sequences = {shortcut.key().toString() for shortcut in view.findChildren(QShortcut)}

    assert "Ctrl+N" in sequences


def test_empty_space_context_menu_offers_to_add_a_base(qtbot, workspace_factory):
    """Задача 10: контекстное меню пустого места дерева больше не выходит молча."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    menu = view._build_empty_space_menu()
    texts = [action.text() for action in menu.actions()]
    assert "Добавить базу…" in texts


def test_add_dialog_is_built_with_real_groups_and_installations(qtbot, workspace_factory):
    """Тот же принцип, что и у `_build_properties_dialog` (задача 9): не заглушки."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    dialog = view._build_add_dialog()
    qtbot.addWidget(dialog)
    assert "Клиенты" in dialog.groups_shown()


def test_apply_new_infobase_adds_a_record(qtbot, workspace_factory):
    view, _, errors, _ = _view(qtbot, workspace_factory)
    before = len(view.workspace().items())
    dialog = view._build_add_dialog()
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\bases\new")
    dialog.set_name("Новая база")

    view._apply_new_infobase(dialog)

    assert errors == []
    items = view.workspace().items()
    assert len(items) == before + 1
    added = next(i for i in items if i.name == "Новая база")
    assert added.connect == r'File="D:\bases\new";'
    assert added.folder == "/"


def test_apply_new_infobase_reports_invalid_name_and_still_rebuilds(qtbot, workspace_factory):
    """Пустое имя отклоняет `validate_section_name` — ошибка идёт в on_error,

    не наружу слота, и ничего не добавляется (тот же приём, что и у
    `_apply_properties`/`toggle_favorite` для остальных операций записи).
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    before = len(view.workspace().items())
    dialog = view._build_add_dialog()
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\bases\new")
    # Имя не заполнено намеренно.

    view._apply_new_infobase(dialog)

    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)
    assert len(view.workspace().items()) == before


def test_apply_new_infobase_reports_a_valueerror_and_does_not_crash(qtbot, workspace_factory):
    """Круг правок 1 (ревью задачи 10): симметрия с `_apply_properties`.

    `dialog.new_record()` зовёт `build_connect`, которая может поднять
    `ValueError` на запрещённом символе, если `_on_accept` диалога почему-то
    не остановил его раньше — тот же источник риска, что и у `dialog.changes()`
    в `_apply_properties` (коммит `3b15170`), только на пути добавления.
    `_apply_new_infobase` вызывается здесь напрямую, в обход `exec()`/
    `_on_accept`, — собственный тестовый набор проекта уже пользуется этим
    доступом (`test_apply_new_infobase_adds_a_record` и соседи), значит
    граница обязана быть рабочей и тут.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    before = len(view.workspace().items())
    dialog = view._build_add_dialog()
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.SERVER)
    dialog.set_server("s;evil")
    dialog.set_name("Тест")

    view._apply_new_infobase(dialog)

    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)
    assert len(view.workspace().items()) == before


def test_add_infobase_does_nothing_when_dialog_is_cancelled(qtbot, workspace_factory, monkeypatch):
    """Полный путь `add_infobase` (build → exec → apply), Cancel — не пишет.

    `exec()` подменяется на Rejected — тот же приём, что и у теста ревью
    задачи 8 для кнопок диалога: настоящий модальный `exec()` завис бы
    в офскрин-тесте.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    before = len(view.workspace().items())
    monkeypatch.setattr(InfobaseDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    view.add_infobase()

    assert len(view.workspace().items()) == before
    assert errors == []


# -- проводка «собрать → показать → применить» (финальное ревью, I2) -------------
#
# Приём «сборка отдельно от показа» (задачи 8-12, 20) сделал состав диалогов
# проверяемым, но саму соединяющую строку `if dialog.exec() == Accepted:`
# не покрыл нигде: `return` первой строкой в `show_properties`, `add_group`,
# `rename_group` и `add_infobase_from_directory` оставлял весь набор зелёным,
# то есть все четыре пункта UI можно было сделать мёртвыми. Образцом служит
# `test_add_infobase_does_nothing_when_dialog_is_cancelled` выше — здесь тот же
# приём доведён до обеих веток (`Accepted` и отказ) для каждого метода.


def _accept(monkeypatch: Any, dialog_class: type) -> None:
    """Заставить `exec()` этого класса диалогов вернуть Accepted без показа."""
    monkeypatch.setattr(dialog_class, "exec", lambda self: QDialog.DialogCode.Accepted)


def _reject(monkeypatch: Any, dialog_class: type) -> None:
    monkeypatch.setattr(dialog_class, "exec", lambda self: QDialog.DialogCode.Rejected)


def test_show_properties_applies_the_dialog_when_accepted(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    applied: list[str] = []
    monkeypatch.setattr(view, "_apply_properties", lambda k, _d: applied.append(k))
    _accept(monkeypatch, InfobaseDialog)

    view.show_properties(key)

    assert applied == [key]


def test_show_properties_applies_nothing_when_cancelled(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    applied: list[str] = []
    monkeypatch.setattr(view, "_apply_properties", lambda k, _d: applied.append(k))
    _reject(monkeypatch, InfobaseDialog)

    view.show_properties("id:44444444-4444-4444-4444-444444444444")

    assert applied == []


def test_add_group_applies_the_dialog_when_accepted(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    applied: list[object] = []
    monkeypatch.setattr(view, "_apply_new_group", applied.append)
    _accept(monkeypatch, GroupDialog)

    view.add_group(ROOT)

    assert len(applied) == 1


def test_add_group_applies_nothing_when_cancelled(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    applied: list[object] = []
    monkeypatch.setattr(view, "_apply_new_group", applied.append)
    _reject(monkeypatch, GroupDialog)

    view.add_group(ROOT)

    assert applied == []


def test_rename_group_applies_the_dialog_when_accepted(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    applied: list[str] = []
    monkeypatch.setattr(view, "_apply_group_properties", lambda k, _d: applied.append(k))
    _accept(monkeypatch, GroupDialog)

    view.rename_group(_RETAIL_GROUP_KEY)

    assert applied == [_RETAIL_GROUP_KEY]


def test_rename_group_applies_nothing_when_cancelled(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    applied: list[str] = []
    monkeypatch.setattr(view, "_apply_group_properties", lambda k, _d: applied.append(k))
    _reject(monkeypatch, GroupDialog)

    view.rename_group(_RETAIL_GROUP_KEY)

    assert applied == []


def test_add_infobase_from_directory_adds_the_record_when_accepted(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Настоящее тело метода, а не цель `monkeypatch.setattr`.

    До этого теста `add_infobase_from_directory` встречалась в наборе только
    как подменяемая цель (тесты `_BasesTree.dropEvent`), и её собственное тело
    не исполнялось ни разу: `return` первой строкой ничего не ломал.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    directory = tmp_path / "Новая база"
    directory.mkdir()
    before = len(view.workspace().items())
    _accept(monkeypatch, InfobaseDialog)

    view.add_infobase_from_directory(str(directory))

    assert errors == []
    items = view.workspace().items()
    assert len(items) == before + 1
    added = next(i for i in items if i.name == "Новая база")
    assert added.connect == 'File="' + str(directory) + '";'
    assert added.folder == "/"


def test_add_infobase_from_directory_adds_nothing_when_cancelled(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    view, _, errors, _ = _view(qtbot, workspace_factory)
    directory = tmp_path / "Новая база"
    directory.mkdir()
    before = len(view.workspace().items())
    _reject(monkeypatch, InfobaseDialog)

    view.add_infobase_from_directory(str(directory))

    assert len(view.workspace().items()) == before
    assert errors == []


# -- Задача 10: смена вида размещения через диалог свойств -----------------------


def test_declined_kind_change_confirmation_writes_nothing(qtbot, workspace_factory, monkeypatch):
    """`_apply_properties` спрашивает перед пересборкой Connect — «Нет» отменяет всё.

    Мелочь ревью задачи 10: тест существует ровно ради доказательства «файл
    не тронут» — байтовое сравнение (тот же приём, что и у соседнего теста
    `test_apply_properties_reports_a_valueerror_from_changes_instead_of_crashing`)
    доказывает это прямее, чем перечитанное поле `item.connect` из свежей
    модели `workspace().items()`.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = view.workspace().add_infobase("Тест", 'Srvr="s";Ref="r";Usr="admin";', "/")
    before = view.workspace().paths.ibases.read_bytes()
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\new")
    monkeypatch.setattr("onecstarter.ui.bases.view.russian_confirm", lambda *a, **kw: False)

    view._apply_properties(key, dialog)

    after = view.workspace().paths.ibases.read_bytes()
    assert after == before
    assert errors == []


def test_accepted_kind_change_confirmation_writes_rebuilt_connect(
    qtbot, workspace_factory, monkeypatch
):
    """«Да» — Connect переписывается целиком через build_connect, Usr пропадает."""
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = view.workspace().add_infobase("Тест", 'Srvr="s";Ref="r";Usr="admin";', "/")
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\new")
    monkeypatch.setattr("onecstarter.ui.bases.view.russian_confirm", lambda *a, **kw: True)

    view._apply_properties(key, dialog)

    item = next(i for i in view.workspace().items() if i.key == key)
    assert item.connect == 'File="D:\\new";'
    assert errors == []


def test_kind_change_confirmation_is_not_asked_when_kind_is_unchanged(
    qtbot, workspace_factory, monkeypatch
):
    """Обычная правка (без смены вида) не должна открывать Да/Нет-диалог вовсе."""
    view, _, errors, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    dialog = view._build_properties_dialog(key)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\changed")
    asked: list[int] = []

    def _confirm(*_args: object, **_kwargs: object) -> bool:
        asked.append(1)
        return True

    monkeypatch.setattr("onecstarter.ui.bases.view.russian_confirm", _confirm)

    view._apply_properties(key, dialog)

    assert asked == []
    assert errors == []


# -- Задача 11: удаление записи ---------------------------------------------
#
# `confirm_removal` — параметр конструктора, а не вызов функции модуля  # noqa: RUF003
# напрямую (в отличие от `russian_confirm` в задаче 10 выше): реальная
# реализация открывает блокирующий `QMessageBox.exec()`, который в
# офскрин-тесте никогда не получит клика. Монки-патч модульного имени решил
# бы ту же задачу, но обошёл бы саму функцию стороной — тот класс дефекта
# уже стоил задаче 10 отдельного круга правок (buttons.py, «Круг правок 1»).  # noqa: RUF003
# Инъекция подставляет фейк там, где обычно стоит настоящая функция, и та
# в свою очередь целиком проверена собственным набором tests/ui/test_confirm.py
# на настоящем виджете.


def test_context_menu_has_remove_action(qtbot, workspace_factory):
    """Пункт «Удалить из списка…» — состав меню проверяется без exec()."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    item = next(i for i in view.workspace().items() if i.key == key)
    menu = view._build_menu(item, key)
    texts = [action.text() for action in menu.actions()]
    assert "Удалить из списка…" in texts


def test_confirmed_removal_deletes_the_record(qtbot, workspace_factory):
    """«Да» — запись пропадает из workspace.items(); confirm получает саму запись."""
    key = "id:44444444-4444-4444-4444-444444444444"
    asked: list[InfobaseItem] = []

    def _confirm(_parent: QWidget | None, item: InfobaseItem) -> bool:
        asked.append(item)
        return True

    view, _, errors, _ = _view(qtbot, workspace_factory, confirm_removal=_confirm)

    view.remove_key(key)

    assert key not in [i.key for i in view.workspace().items()]
    assert [item.name for item in asked] == ["Демо Бухгалтерия"]
    assert errors == []


def test_declined_removal_confirmation_writes_nothing(qtbot, workspace_factory):
    """«Нет» — файл не тронут вовсе.

    Байтовое сравнение — тот же приём, что и у соседнего
    `test_declined_kind_change_confirmation_writes_nothing` (задача 10):
    доказывает «файл не тронут» прямее, чем перечитанное поле из свежей
    модели `workspace().items()`. Это тест шага 4 (мутационная проверка):
    обязан упасть, если `confirm_removal` вернуть `True` без вопроса.
    """  # noqa: RUF002
    key = "id:44444444-4444-4444-4444-444444444444"
    view, _, errors, _ = _view(qtbot, workspace_factory, confirm_removal=lambda *_a: False)
    before = view.workspace().paths.ibases.read_bytes()

    view.remove_key(key)

    after = view.workspace().paths.ibases.read_bytes()
    assert after == before
    assert key in [i.key for i in view.workspace().items()]
    assert errors == []


def test_remove_key_with_unknown_key_does_not_ask_and_does_nothing(qtbot, workspace_factory):
    """Ключа нет в текущем списке — вопрос не задаётся вовсе, файл не тронут."""
    asked: list[int] = []

    def _confirm(*_args: object, **_kwargs: object) -> bool:
        asked.append(1)
        return True

    view, _, errors, _ = _view(qtbot, workspace_factory, confirm_removal=_confirm)
    before = view.workspace().paths.ibases.read_bytes()

    view.remove_key("id:does-not-exist")

    after = view.workspace().paths.ibases.read_bytes()
    assert after == before
    assert asked == []
    assert errors == []


def test_remove_key_reports_unknown_item_when_target_is_gone(
    qtbot, workspace_factory, monkeypatch
):
    """`Workspace.remove_infobase` вернул `False` — ключ сменился из-за внешней правки.

    Не ошибка самого `Workspace.remove_infobase` (дизайн плана 3, §5), но
    и не тихий успех для пользователя: он должен узнать, что список стоит
    обновить, а не решить, что запись удалена.
    """  # noqa: RUF002
    key = "id:44444444-4444-4444-4444-444444444444"
    view, _, errors, _ = _view(qtbot, workspace_factory, confirm_removal=lambda *_a: True)
    monkeypatch.setattr(
        type(view.workspace()), "remove_infobase", lambda self, key: False
    )

    view.remove_key(key)

    assert len(errors) == 1
    assert isinstance(errors[0], UnknownItemError)


def test_view_defaults_to_the_real_confirm_removal_dialog(qtbot, workspace_factory):
    """Без явной инъекции конструктор обязан ссылаться на настоящий Qt-диалог.

    `exec()` в офскрин-тесте вызвать нельзя (заблокирует поток без
    настоящего клика), поэтому проверяется то, что подставится по
    умолчанию, — идентичность объекта, а не поведение диалога.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    assert view._confirm_removal is confirm_removal


# -- Задача 12: группы — создание, переименование, перенос, удаление ---------
#
# Ключи из фикстуры anonymized.v8i: «Клиенты» (id:111…1), «Розница» внутри
# «Клиенты» (id:222…2, Folder=/Клиенты), «Демо Бухгалтерия» прямым ребёнком
# «Клиенты», «Демо Розница» — внутри «Розница» (Folder=/Клиенты/Розница).
# Удаление «Клиенты» поэтому — готовый пример каскада на два уровня: прямой
# ребёнок (база и подгруппа) и внук (база внутри подгруппы), не заводя
# отдельную фикстуру только под этот тест.

_CLIENTS_KEY = "id:11111111-1111-1111-1111-111111111111"
_RETAIL_GROUP_KEY = "id:22222222-2222-2222-2222-222222222222"


def test_group_context_menu_offers_create_rename_delete(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    item = next(i for i in view.workspace().items() if i.key == _CLIENTS_KEY)
    menu = view._build_group_menu(item, _CLIENTS_KEY)
    texts = [action.text() for action in menu.actions()]
    assert "Создать группу…" in texts
    assert "Переименовать группу…" in texts
    assert "Удалить группу…" in texts


def test_group_menu_for_user_group_offers_full_operations(qtbot, workspace_factory):
    """`_group_menu_for` — единственная точка решения (круг правок 1): для

    пользовательской группы должно получиться то же полное меню, что
    и раньше у `_build_group_menu` напрямую — регрессия на happy path.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    item = next(i for i in view.workspace().items() if i.key == _CLIENTS_KEY)
    menu = view._group_menu_for(item, _CLIENTS_KEY)
    texts = [action.text() for action in menu.actions()]
    assert "Удалить группу…" in texts
    assert all(action.isEnabled() for action in menu.actions())


def test_common_group_context_menu_disables_all_three_actions(
    qtbot, workspace_factory, common_group_cfg_paths
):
    """Круг правок 1 ревью задачи 12: группа общего списка — не полное меню.

    До этой правки «Создать группу…»/«Переименовать группу…» вели
    в тупик (открывшийся диалог правки или `InvalidRequestError`
    «Группы «X» в списке нет» про группу, которая у пользователя прямо
    на экране) — только «Удалить группу…» было защищено собственным
    guard'ом в `remove_group`. Теперь решение принимает `_group_menu_for`
    до показа меню, единым правилом на все три пункта, тем же приёмом,
    что и у неявного узла.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory, cfg_paths=common_group_cfg_paths)
    item = next(i for i in view.workspace().items() if i.key == COMMON_GROUP_KEY)
    menu = view._group_menu_for(item, COMMON_GROUP_KEY)
    assert menu.toolTipsVisible() is True
    texts = [action.text() for action in menu.actions()]
    assert texts == ["Создать группу…", "Переименовать группу…", "Удалить группу…"]
    for action in menu.actions():
        assert action.isEnabled() is False
        assert action.toolTip() == COMMON_NOTE


def test_group_paths_excludes_common_list_groups(qtbot, workspace_factory, common_group_cfg_paths):
    """`_group_paths()` — общий источник для `GroupDialog` и `InfobaseDialog`

    (круг правок 1): без фильтра путь общей группы попадал в оба выпадающих
    списка и вёл в тот же тупик, что и пункт меню выше — правило одно
    на обоих потребителей, а не отдельная проверка в каждом.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory, cfg_paths=common_group_cfg_paths)
    assert COMMON_GROUP_NAME not in view._group_paths()


def test_implicit_group_context_menu_disables_all_three_actions(qtbot, workspace_factory):
    """[Ф] T-05.7: у неявного узла нет ни секции, ни ключа — операции недоступны

    с пояснением в тултипе, а не молча. `setToolTipsVisible(True)`
    обязателен — без него QMenu тултипы пунктов на этой платформе не
    показывает вовсе, даже если текст в setToolTip есть.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    menu = view._build_implicit_group_menu()
    assert menu.toolTipsVisible() is True
    texts = [action.text() for action in menu.actions()]
    assert texts == ["Создать группу…", "Переименовать группу…", "Удалить группу…"]
    for action in menu.actions():
        assert action.isEnabled() is False
        assert action.toolTip() == IMPLICIT_NOTE


def test_empty_space_context_menu_offers_to_create_a_group(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    menu = view._build_empty_space_menu()
    texts = [action.text() for action in menu.actions()]
    assert "Создать группу…" in texts


# -- создание группы ---------------------------------------------------------


def test_build_add_group_dialog_preselects_given_folder(qtbot, workspace_factory):
    """«Создать группу…» на строке группы предлагает её саму родителем — не корень."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    dialog = view._build_add_group_dialog("Клиенты")
    qtbot.addWidget(dialog)
    assert dialog.parent_path() == "Клиенты"


def test_apply_new_group_adds_a_group(qtbot, workspace_factory):
    view, _, errors, _ = _view(qtbot, workspace_factory)
    dialog = view._build_add_group_dialog(ROOT)
    qtbot.addWidget(dialog)
    dialog.set_name("Новая группа")

    view._apply_new_group(dialog)

    assert errors == []
    added = next(i for i in view.workspace().items() if i.name == "Новая группа")
    assert added.is_group
    assert added.folder == "/"


def test_apply_new_group_reports_invalid_name_and_still_rebuilds(qtbot, workspace_factory):
    """Пустое имя (в обход собственной валидации диалога) отклоняет

    `validate_section_name` в `services` — тот же приём, что и у
    `_apply_new_infobase`: ошибка идёт в `_on_error`, не крах слота, файл
    не тронут.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    before = len(view.workspace().items())
    dialog = view._build_add_group_dialog(ROOT)
    qtbot.addWidget(dialog)
    # Имя не заполнено намеренно — минуя проверку самого диалога (_on_accept).

    view._apply_new_group(dialog)

    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)
    assert len(view.workspace().items()) == before


# -- переименование и перенос группы -----------------------------------------


def test_group_dialog_is_built_for_the_requested_group(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    dialog = view._build_group_dialog(_RETAIL_GROUP_KEY)
    assert dialog is not None
    qtbot.addWidget(dialog)
    assert dialog.name_text() == "Розница"
    assert dialog.parent_path() == "Клиенты"


def test_group_dialog_is_none_for_a_missing_key(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    assert view._build_group_dialog("id:does-not-exist") is None


def test_apply_group_properties_writes_the_rename(qtbot, workspace_factory):
    view, _, errors, _ = _view(qtbot, workspace_factory)
    dialog = view._build_group_dialog(_RETAIL_GROUP_KEY)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_name("Розница 2")

    view._apply_group_properties(_RETAIL_GROUP_KEY, dialog)

    assert errors == []
    renamed = next(i for i in view.workspace().items() if i.key == _RETAIL_GROUP_KEY)
    assert renamed.name == "Розница 2"


def test_apply_group_properties_on_untouched_dialog_does_not_write(
    qtbot, workspace_factory, monkeypatch
):
    """Открыл и закрыл «ОК» без правок — до `update_group` дело не доходит.

    Финальное ревью, C1 (та же находка, что и у `_apply_properties`):
    байтовое сравнение оставалось зелёным при замене сторожа
    `if name is None and folder is None: return` на `pass`, потому что
    `services/writer.py` сам не пишет патч, не меняющий ни байта. Смотрим
    поэтому на факт вызова, а байты — рядом, вторым утверждением.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    dialog = view._build_group_dialog(_RETAIL_GROUP_KEY)
    assert dialog is not None
    qtbot.addWidget(dialog)
    calls = _spy_on(monkeypatch, view.workspace(), "update_group")
    before = view.workspace().paths.ibases.read_bytes()

    view._apply_group_properties(_RETAIL_GROUP_KEY, dialog)

    after = view.workspace().paths.ibases.read_bytes()
    assert calls == []
    assert errors == []
    assert after == before


def test_apply_group_properties_calls_the_writer_when_something_changed(
    qtbot, workspace_factory, monkeypatch
):
    """Обратная сторона сторожа C1 для групп: спай срабатывает, когда правка есть."""
    view, _, errors, _ = _view(qtbot, workspace_factory)
    dialog = view._build_group_dialog(_RETAIL_GROUP_KEY)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_name("Розница 2")
    calls = _spy_on(monkeypatch, view.workspace(), "update_group")

    view._apply_group_properties(_RETAIL_GROUP_KEY, dialog)

    assert errors == []
    assert len(calls) == 1
    assert calls[0][0][0] == _RETAIL_GROUP_KEY


def test_apply_group_properties_moves_and_cascades_children(qtbot, workspace_factory):
    """Проводка вызова: `update_group` получает реальный `new_folder`, а не

    молча теряет выбор пользователя. Сам каскад `Folder` потомков — уже
    сервисный функционал (T-04.4, покрыт своим набором тестов) — здесь
    проверяется только то, что BasesView его действительно вызывает.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    dialog = view._build_group_dialog(_RETAIL_GROUP_KEY)  # "Розница", сейчас /Клиенты
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_parent_path("/")

    view._apply_group_properties(_RETAIL_GROUP_KEY, dialog)

    assert errors == []
    moved = next(i for i in view.workspace().items() if i.key == _RETAIL_GROUP_KEY)
    assert moved.folder == "/"
    child = next(i for i in view.workspace().items() if i.name == "Демо Розница")
    assert child.folder == "/Розница"


# -- удаление группы (обязательство 3 блока Б) --------------------------------
#
# `ask_group_removal` — параметр конструктора, инъекция, а не монки-патч  # noqa: RUF003
# модуля (тот же приём, что и у `confirm_removal` в задаче 11, см. комментарий  # noqa: RUF003
# у `_view()`): реальная реализация открывает блокирующий `QMessageBox.exec()`.  # noqa: RUF003


def test_remove_group_asks_with_recursively_computed_contents(qtbot, workspace_factory):
    """Подтверждение видит содержимое всего поддерева, не только прямых детей.

    «Клиенты» → прямой ребёнок «Демо Бухгалтерия» и подгруппа «Розница», а
    «Демо Розница» лежит уже внутри «Розница» — попадёт в подсчёт только
    рекурсией по всему поддереву ([Ф] T-05.9 — каскад рекурсивный).
    """  # noqa: RUF002
    asked: list[tuple[str, list[str], int, int]] = []

    def _ask(
        _parent: QWidget | None, label: str, names: Sequence[str], bases: int, groups: int
    ) -> GroupRemoval | None:
        asked.append((label, list(names), bases, groups))
        return None  # отмена — файл не тронут, это отдельный тест ниже

    view, _, errors, _ = _view(qtbot, workspace_factory, ask_group_removal=_ask)

    view.remove_group(_CLIENTS_KEY)

    assert len(asked) == 1
    label, names, bases, groups = asked[0]
    assert label == "Клиенты"
    assert bases == 2  # Демо Бухгалтерия + Демо Розница (рекурсивно, внутри Розницы)
    assert groups == 1  # Розница
    # «Розница (группа)» — GROUP_CONTENT_MARK (круг правок 1): подгруппа
    # отличима от базы внутри неё в одном плоском списке имён.
    assert set(names) == {"Розница (группа)", "Демо Розница", "Демо Бухгалтерия"}
    assert errors == []


def test_declined_group_removal_writes_nothing(qtbot, workspace_factory):
    """Отмена (`None`) — файл не тронут вовсе.

    Байтовое сравнение — тот же приём, что и у
    `test_declined_removal_confirmation_writes_nothing` (задача 11): это тест
    шага 5 мутационной проверки, обязан упасть, если `remove_group` перестанет
    учитывать результат подтверждения.
    """  # noqa: RUF002
    view, _, errors, _ = _view(
        qtbot, workspace_factory, ask_group_removal=lambda *_a, **_kw: None
    )
    before = view.workspace().paths.ibases.read_bytes()

    view.remove_group(_CLIENTS_KEY)

    after = view.workspace().paths.ibases.read_bytes()
    assert after == before
    assert _CLIENTS_KEY in [i.key for i in view.workspace().items()]
    assert errors == []


def test_recursive_group_removal_deletes_the_whole_subtree(qtbot, workspace_factory):
    view, _, errors, _ = _view(
        qtbot, workspace_factory, ask_group_removal=lambda *_a, **_kw: GroupRemoval.RECURSIVE
    )

    view.remove_group(_CLIENTS_KEY)

    names = {i.name for i in view.workspace().items()}
    assert "Клиенты" not in names
    assert "Розница" not in names
    assert "Демо Бухгалтерия" not in names
    assert "Демо Розница" not in names
    assert errors == []


def test_promote_group_removal_keeps_children_at_parent(qtbot, workspace_factory):
    view, _, errors, _ = _view(
        qtbot, workspace_factory, ask_group_removal=lambda *_a, **_kw: GroupRemoval.PROMOTE
    )

    view.remove_group(_CLIENTS_KEY)

    items = view.workspace().items()
    assert "Клиенты" not in [i.name for i in items]
    accounting = next(i for i in items if i.name == "Демо Бухгалтерия")
    assert accounting.folder == "/"
    retail_group = next(i for i in items if i.name == "Розница")
    assert retail_group.folder == "/"
    retail_base = next(i for i in items if i.name == "Демо Розница")
    assert retail_base.folder == "/Розница"
    assert errors == []


def test_remove_group_with_unknown_key_does_not_ask_and_does_nothing(qtbot, workspace_factory):
    asked: list[int] = []

    def _ask(*_args: object, **_kwargs: object) -> GroupRemoval | None:
        asked.append(1)
        return GroupRemoval.RECURSIVE

    view, _, errors, _ = _view(qtbot, workspace_factory, ask_group_removal=_ask)
    before = view.workspace().paths.ibases.read_bytes()

    view.remove_group("id:does-not-exist")

    after = view.workspace().paths.ibases.read_bytes()
    assert after == before
    assert asked == []
    assert errors == []


def test_remove_group_rejects_a_base_key(qtbot, workspace_factory):
    """Круг правок 1, замечание 6: самый опасный метод не должен принять

    ключ базы за группу. `_find_group_node`/`group_contents` не различают
    вид секции — узел базы тоже проходит их обход (просто без потомков),
    и без явной проверки пользователь увидел бы «Удалить группу
    "Демо Розница"? Группа пуста.» вместо диагностики. Из UI недостижимо
    (меню базы не предлагает «Удалить группу…»), но метод публичный —
    защита нужна независимо от того, что сегодня к нему ведёт.
    """  # noqa: RUF002
    key = "id:44444444-4444-4444-4444-444444444444"  # "Демо Бухгалтерия", база
    asked: list[int] = []

    def _ask(*_args: object, **_kwargs: object) -> GroupRemoval | None:
        asked.append(1)
        return GroupRemoval.RECURSIVE

    view, _, errors, _ = _view(qtbot, workspace_factory, ask_group_removal=_ask)

    view.remove_group(key)

    assert asked == []
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)
    assert "Демо Бухгалтерия" in str(errors[0])
    assert key in [i.key for i in view.workspace().items()]


def test_remove_group_refuses_common_list_group(qtbot, workspace_factory, common_group_cfg_paths):
    """Круг правок 1, замечание 2: guard остаётся — метод достижим напрямую,

    в обход `_group_menu_for` (которая с этого круга правок больше не
    предлагает «Удалить группу…» для общего списка вовсе). Сообщение обязано
    остаться внятным («доступна только для чтения»), а не «группа не
    найдена» — `Workspace.tree()` строится только по пользовательскому
    источнику, и без этой проверки `_find_group_node` не нашёл бы группу
    общего списка и выдал бы вводящий в заблуждение диагноз.
    """  # noqa: RUF002
    asked: list[int] = []

    def _ask(*_args: object, **_kwargs: object) -> GroupRemoval | None:
        asked.append(1)
        return GroupRemoval.RECURSIVE

    view, _, errors, _ = _view(
        qtbot, workspace_factory, cfg_paths=common_group_cfg_paths, ask_group_removal=_ask
    )

    view.remove_group(COMMON_GROUP_KEY)

    assert asked == []
    assert len(errors) == 1
    assert isinstance(errors[0], ReadOnlySourceError)


def test_remove_group_reports_unknown_item_when_target_is_gone(
    qtbot, workspace_factory, monkeypatch
):
    """`Workspace.remove_group` вернул `False` — ключ сменился из-за внешней правки.

    Тот же приём, что и у `test_remove_key_reports_unknown_item_when_target_is_gone`
    (задача 11): не ошибка самой операции, но и не тихий успех для пользователя.
    """  # noqa: RUF002
    view, _, errors, _ = _view(
        qtbot, workspace_factory, ask_group_removal=lambda *_a, **_kw: GroupRemoval.RECURSIVE
    )
    monkeypatch.setattr(
        type(view.workspace()), "remove_group", lambda self, key, removal: False
    )

    view.remove_group(_CLIENTS_KEY)

    assert len(errors) == 1
    assert isinstance(errors[0], UnknownItemError)


def test_view_defaults_to_the_real_ask_group_removal_dialog(qtbot, workspace_factory):
    """Тот же приём, что и у соседнего теста для `confirm_removal`."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    assert view._ask_group_removal is ask_group_removal


# -- Задача 14: перенос по группам перетаскиванием ---------------------------
#
# Ключи из той же фикстуры, что и у задачи 12 (см. комментарий выше):  # noqa: RUF003
# «Учёт серверный» (id:666…6, Folder=/) — запись базы прямо в корне;
# «Потерянная» (id:888…8, Folder=/Нет такой группы) — единственная запись
# фикстуры внутри неявного узла ([Ф] T-05.7), готовый пример для отказов.
#
# Порядок корневых строк дерева (проверено скриптом при подготовке задачи,
# `workspace.tree()` на этой фикстуре): 0 «Клиенты» (группа, 2 потомка —
# «Розница» и «Демо Бухгалтерия»), 1 «Пустая группа», 2 «Учёт серверный»,
# 3 «Портал», 4 «Без идентификатора», 5 «Нет такой группы» (неявный узел,
# потомок — «Потерянная»).

_SERVER_BASE_KEY = "id:66666666-6666-6666-6666-666666666666"


def _root_index(view: BasesView, row: int) -> QModelIndex:
    return view.model().index(row, 0)


def _find_index_by_kind(view: BasesView, kind: RowKind) -> QModelIndex:
    """Первая строка данного `KIND_ROLE`, обходом всего дерева.

    Круг правок 1 ревью задачи 14: не завязано на конкретный номер строки —
    состав веток («Общие списки» и т. п.) собирается фикстурой теста и
    смещал бы фиксированный индекс, а сам факт, какая именно секция найдена,
    для этих тестов не важен (проверка одна на весь класс `RowKind.SECTION`,
    а не отдельно на «Избранное»/«Недавние»/«Общие списки»).
    """  # noqa: RUF002
    return _find_index(
        view,
        lambda i: i.data(KIND_ROLE) == kind.value,
        f"в дереве нет строки вида {kind}",
    )


# Задача 20: `_BasesTree.dropEvent` теперь читает `event.mimeData()` (проверка
# на брошенный каталог) даже на пути, который раньше её не трогал вовсе —
# тем самым обнажив ту же мину, что и `_drag_move_event` (см. её докстринг):
# `QMimeData()`, созданный внутри вызова функции без внешней ссылки, ничем не
# держится Python-стороной, и после возврата `_drop_event` сборщик мусора
# вправе забрать его в любой момент, оставив `QDropEvent` с висячим указателем  # noqa: RUF003
# — первое же обращение к `event.mimeData()` внутри `dropEvent` тогда падает
# `AttributeError` (на этой машине — реинтерпретация как голый `QObject`) или
# роняет процесс. До задачи 20 `dropEvent` дерева не читал `mimeData()`
# никогда, и мина не срабатывала ни разу за все тесты задач 14/15. Модульная
# константа переживает весь прогон и не зависит от того, держит ли вызывающий
# тест свою собственную ссылку.
_EMPTY_MIME = QMimeData()


def _drop_event(pos: QPoint, mime: QMimeData | None = None) -> QDropEvent:
    return QDropEvent(
        QPointF(pos),
        Qt.DropAction.MoveAction,
        mime if mime is not None else _EMPTY_MIME,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _visible_rect_of_kind(view: BasesView, kind: RowKind) -> QRect:
    """Прямоугольник первой строки данного вида — обязательно видимой.

    Без `expandAll()` первая найденная строка может лежать в свёрнутой ветке,
    и `visualRect` вернёт пустой прямоугольник: `center()` тогда даёт
    `QPoint(0, 0)`, `indexAt` — совсем другую строку, и проверка проходит
    (или падает) не по той причине, о которой написана. Поймано на этих же
    тестах: проверка про край строки сперва «прошла» именно вхолостую.
    Пустой прямоугольник поэтому валит тест здесь, а не молча искажает его.
    """  # noqa: RUF002
    view._tree.expandAll()
    rect = view._tree.visualRect(_find_index_by_kind(view, kind))
    assert not rect.isEmpty(), f"строка вида {kind} не видима — прямоугольник пуст"
    return rect


def _visible_rect_of_key(view: BasesView, key: str) -> QRect:
    """Прямоугольник строки с этим ключом привязки — обязательно видимой.

    Тот же приём и та же страховка от пустого прямоугольника, что
    у `_visible_rect_of_kind`: без `expandAll()` строка может лежать
    в свёрнутой ветке, и `center()` указал бы совсем на другую строку.
    """  # noqa: RUF002
    view._tree.expandAll()
    rect = view._tree.visualRect(_index_of_key(view, key))
    assert not rect.isEmpty(), f"строка {key!r} не видима — прямоугольник пуст"
    return rect


def _drag_move_event(
    pos: QPoint, mime: QMimeData | None = None
) -> tuple[QDragMoveEvent, QMimeData]:
    """Событие и его `QMimeData` — вызывающий обязан держать ссылку на второе.

    `QDragMoveEvent`, собранный из Python, своим `QMimeData` не владеет.
    Если ссылку не удержать, сборщик мусора оставляет висячий указатель,
    и первое же обращение роняет процесс с access violation — в том числе
    обращение из `repr()`, которым pytest оформляет сообщение упавшего
    `assert`. То есть падал бы не тест, а весь прогон, и падал бы только
    тогда, когда проверка не прошла: зелёный прогон эту мину не показывает.
    Поймано при написании этих тестов 09.08.2026 (PySide6, Windows).

    По той же причине в проверках ниже результат сперва кладётся
    в переменную, а `assert` смотрит уже на неё: так в repr попадает `bool`,
    а не Qt-объект.

    Задача 20: `mime` — необязательный, тем же приёмом, что и у `_drop_event`
    — вызывающему из тестов приёма каталога нужен собственный `QMimeData`
    с URL каталога, а не пустой по умолчанию.
    """  # noqa: RUF002
    data = mime if mime is not None else QMimeData()
    return (
        QDragMoveEvent(
            pos,
            Qt.DropAction.MoveAction,
            data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
        data,
    )


def _directory_mime(path: Any) -> QMimeData:
    """`QMimeData` с одним локальным URL каталога — то, что несёт Проводник."""  # noqa: RUF002
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    return mime


# -- handle_drop: перенос по Workspace, без Qt ---------------------------


def test_drop_into_group_changes_folder(qtbot: Any, workspace_factory: Any) -> None:
    view, _, errors, _ = _view(qtbot, workspace_factory)
    base = next(i for i in view.workspace().items() if not i.is_group and i.folder == "/")
    group = next(i for i in view.workspace().items() if i.is_group)

    view.handle_drop(base.key, group.key, DropTarget.INTO)

    moved = next(i for i in view.workspace().items() if i.key == base.key)
    assert moved.folder == render_folder(group_path(group.folder, group.name))
    assert errors == []


def test_drop_into_root_moves_out_of_group(qtbot: Any, workspace_factory: Any) -> None:
    view, _, errors, _ = _view(qtbot, workspace_factory)
    nested = next(i for i in view.workspace().items() if not i.is_group and i.folder != "/")

    view.handle_drop(nested.key, None, DropTarget.INTO)

    assert next(i for i in view.workspace().items() if i.key == nested.key).folder == "/"
    assert errors == []


def test_drop_before_or_after_moves_into_the_targets_parent_only(
    qtbot: Any, workspace_factory: Any
) -> None:
    """[Р] ограничение v1 (план 4b, §12): между РАЗНЫМИ группами BEFORE/AFTER
    меняют только группу, позиция среди соседей не переносится.

    `_SERVER_BASE_KEY` (Folder=/) и `_RETAIL_GROUP_KEY` (Folder=/Клиенты) —
    в разных группах, поэтому здесь только путь родителя цели. Перестановка
    внутри ОДНОЙ группы — задача 15, см. test_drop_before_within_same_group_
    repositions ниже: там источник и цель делят родителя, и `handle_drop`
    зовёт `_reorder`/`Workspace.move_within_group`, а не эту ветку.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)

    view.handle_drop(_SERVER_BASE_KEY, _RETAIL_GROUP_KEY, DropTarget.AFTER)

    moved = next(i for i in view.workspace().items() if i.key == _SERVER_BASE_KEY)
    assert moved.folder == "/Клиенты"  # родитель «Розницы», а не «Розница» сама  # noqa: RUF003
    assert errors == []


# -- Задача 15: BEFORE/AFTER внутри одной группы — перестановка, не перенос --
#
# «Демо Бухгалтерия» (id:444…4) и «Розница» (`_RETAIL_GROUP_KEY`) — прямые
# дети «Клиенты»: в фикстуре Розница имеет OrderInList=-1, Демо Бухгалтерия —
# 60.68…, поэтому исходный порядок показа — Розница, затем Демо Бухгалтерия.

_DEMO_ACCOUNTING_KEY = "id:44444444-4444-4444-4444-444444444444"


def _clients_children(view: BasesView) -> list[str]:
    node = next(node for node in view.workspace().tree() if node.label == "Клиенты")
    return [child.label for child in node.children]


def test_drop_before_within_same_group_repositions(qtbot: Any, workspace_factory: Any) -> None:
    """BEFORE внутри одной группы двигает позицию, а не только Folder.

    Наблюдаемая точка — порядок в `tree()` после `handle_drop` (который
    зовёт `rebuild()`), не значение OrderInList и не байты файла: тот же
    урок, что задачи 9/12/13/14 находили на ступень ближе к пользователю,
    чем было покрыто.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    assert _clients_children(view) == ["Розница", "Демо Бухгалтерия"]

    view.handle_drop(_DEMO_ACCOUNTING_KEY, _RETAIL_GROUP_KEY, DropTarget.BEFORE)

    assert _clients_children(view) == ["Демо Бухгалтерия", "Розница"]
    assert errors == []
    # Перестановка, не перенос: Folder не менялся.
    moved = next(i for i in view.workspace().items() if i.key == _DEMO_ACCOUNTING_KEY)
    assert moved.folder == "/Клиенты"


def test_drop_after_within_same_group_repositions(qtbot: Any, workspace_factory: Any) -> None:
    """AFTER — зеркальная сторона: тот же результат, обратное направление."""
    view, _, errors, _ = _view(qtbot, workspace_factory)

    view.handle_drop(_RETAIL_GROUP_KEY, _DEMO_ACCOUNTING_KEY, DropTarget.AFTER)

    assert _clients_children(view) == ["Демо Бухгалтерия", "Розница"]
    assert errors == []


def test_drop_onto_implicit_node_is_refused(qtbot: Any, workspace_factory: Any) -> None:
    """У неявного узла нет секции и ключа — операции над ним невозможны.

    [Ф] T-05.7: платформа рисует такой узел из висячего Folder, секции
    для него не создаёт. Молча положить туда запись значило бы создать
    висячий Folder уже своими руками.
    """  # noqa: RUF002
    errors: list[ServicesError] = []
    view, _, _, _ = _view(qtbot, workspace_factory, errors=errors)
    base = next(i for i in view.workspace().items() if not i.is_group)
    before = base.folder

    view.handle_drop(base.key, None, DropTarget.INTO, target_is_implicit=True)

    assert next(i for i in view.workspace().items() if i.key == base.key).folder == before
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)


def test_drop_onto_virtual_branch_is_refused_with_its_own_message(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Заголовок ветки/NOTE-строка — не неявный узел, отказ со своим текстом.

    Круг правок 1 ревью задачи 14: до этой правки `target_is_implicit`
    вычислялся по пустому `KEY_ROLE`, а он пуст и у заголовков «Избранное»/
    «Недавние»/«Общие списки» (`RowKind.SECTION`), и у строк ошибок общего
    списка (`RowKind.NOTE`), не только у настоящего неявного узла. Бросок
    на заголовок получал сообщение «Этой группы нет в файле» — бессмысленный
    совет создать группу для ветки, у которой `Folder` не существует
    в принципе. `target_is_virtual` — отдельный флаг с отдельным текстом,
    без единого слова про `Folder`.
    """  # noqa: RUF002
    errors: list[ServicesError] = []
    view, _, _, _ = _view(qtbot, workspace_factory, errors=errors)
    base = next(i for i in view.workspace().items() if not i.is_group)
    before = base.folder

    view.handle_drop(base.key, None, DropTarget.INTO, target_is_virtual=True)

    assert next(i for i in view.workspace().items() if i.key == base.key).folder == before
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidRequestError)
    assert "Folder" not in str(errors[0])


def test_drop_of_common_record_is_refused(
    qtbot: Any, workspace_factory: Any, common_base_cfg_paths: Any
) -> None:
    """Общий список только для чтения — отказ приходит из services.

    Проверка стоит в UI, а не только в services: без неё перетаскивание
    выглядело бы удавшимся (Qt нарисовал бы перенос), а файл остался бы
    прежним. Дерево обязано пересобраться и вернуть запись на место.

    Настоящий общий список (`common_base_cfg_paths`), а не
    `mock.patch.object(workspace, "items", ...)`: `Workspace._reject_common`
    проверяет внутренний `_items`, до которого патч `items()` не достаёт —
    с ним запись, подложенная только в возврат `items()`, была бы не найдена
    вовсе и дала бы `TargetGoneError`, а не `ReadOnlySourceError` (поймано
    прогоном этого теста при подготовке задачи, см. отчёт).
    """  # noqa: RUF002
    errors: list[ServicesError] = []
    view, _, _, _ = _view(
        qtbot, workspace_factory, errors=errors, cfg_paths=common_base_cfg_paths
    )
    common = next(i for i in view.workspace().items() if i.key == COMMON_BASE_KEY)
    group = next(i for i in view.workspace().items() if i.is_group)

    view.handle_drop(common.key, group.key, DropTarget.INTO)

    assert len(errors) == 1
    assert isinstance(errors[0], ReadOnlySourceError)


def test_drop_onto_common_list_group_is_refused_by_the_cursor(
    qtbot: Any, workspace_factory: Any, common_group_cfg_paths: Any
) -> None:
    """Строка общего списка — не только не источник, но и не цель.

    `_folder_of_drop` ищет цель только среди `InfobaseSource.USER`, тем же
    структурным приёмом, что и `_group_paths()` (задача 12): без фильтра
    `services` отказал бы с «Группы «Общая группа» в списке нет», хотя
    пользователь видит её на экране — тот же класс вводящей в заблуждение
    диагностики, который круг правок 1 задачи 12 убрал из меню.

    **Что изменилось и почему (финальное ревью, I10).** Прежняя редакция
    этого теста называлась `..._is_a_structural_no_op` и закрепляла
    `assert errors == []` как намеренное поведение: бросок молча
    не делал ничего. Заказчик это решение пересмотрел — ровно тот симптом
    он описал в ручном smoke №2 («трижды бросил и трижды получил ничего»),
    и решение §14 п. 5 спеки (отказ курсором во время перетаскивания)
    применили тогда только к соседнему случаю `INTO` на строку-базу,
    а сюда — нет. Теперь `_rejects_drop_at` отвергает и эту цель, поэтому
    настоящее перетаскивание до `handle_drop` не доходит вовсе.

    Проверяются обе стороны: курсор отказывает **до** отпускания, а
    `handle_drop`, достижимый напрямую в обход курсора, остаётся
    безопасным — файл не меняется. Молчание `handle_drop` теперь
    не заявление о поведении для пользователя, а свойство последнего
    рубежа, до которого пользователь уже не доберётся.
    """  # noqa: RUF002
    errors: list[ServicesError] = []
    view, _, _, _ = _view(
        qtbot, workspace_factory, errors=errors, cfg_paths=common_group_cfg_paths
    )
    base = next(i for i in view.workspace().items() if not i.is_group and i.folder == "/")
    before = base.folder
    rect = _visible_rect_of_key(view, COMMON_GROUP_KEY)

    rejected = view._tree._rejects_drop_at(rect.center())
    at_edge = view._tree._rejects_drop_at(QPoint(rect.center().x(), rect.top()))
    view.handle_drop(base.key, COMMON_GROUP_KEY, DropTarget.INTO)

    assert rejected is True
    assert at_edge is True, "у цели вне пользовательского списка отказ не зависит от стороны"  # noqa: RUF001
    assert next(i for i in view.workspace().items() if i.key == base.key).folder == before
    assert errors == []


def test_drop_onto_common_list_record_is_refused_by_the_cursor(
    qtbot: Any, workspace_factory: Any, common_base_cfg_paths: Any
) -> None:
    """Запись общего списка — такая же немая цель, как и его группа (I10).

    Для неё немым был не только `INTO` (вложить запись в запись нельзя
    и в своём списке), но и `BEFORE`/`AFTER`: `_reorder` не находит цель
    среди `InfobaseSource.USER` и уходит в `_folder_of_drop`, а тот
    по той же причине отдаёт `None`.
    """  # noqa: RUF002
    errors: list[ServicesError] = []
    view, _, _, _ = _view(
        qtbot, workspace_factory, errors=errors, cfg_paths=common_base_cfg_paths
    )
    rect = _visible_rect_of_key(view, COMMON_BASE_KEY)

    at_middle = view._tree._rejects_drop_at(rect.center())
    at_edge = view._tree._rejects_drop_at(QPoint(rect.center().x(), rect.bottom()))

    assert at_middle is True
    assert at_edge is True


def test_drop_into_a_base_is_a_no_op(qtbot: Any, workspace_factory: Any) -> None:
    """INTO на запись базы, а не группу: вложить запись в запись нельзя."""  # noqa: RUF002
    errors: list[ServicesError] = []
    view, _, _, _ = _view(qtbot, workspace_factory, errors=errors)
    base = next(i for i in view.workspace().items() if not i.is_group and i.folder == "/")
    other = next(
        i for i in view.workspace().items()
        if not i.is_group and i.key != base.key and i.folder == "/"
    )
    before = other.folder

    view.handle_drop(other.key, base.key, DropTarget.INTO)

    assert next(i for i in view.workspace().items() if i.key == other.key).folder == before
    assert errors == []


# -- Задача 15: Alt+↑/Alt+↓ — перестановка с клавиатуры ----------------------  # noqa: RUF003


def test_alt_up_and_alt_down_shortcuts_are_registered_on_view(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Подстраховка отдельно от поведения — тот же приём, что у F3/F4/Ctrl+N."""  # noqa: RUF002
    workspace, _calls, _opened = workspace_factory()
    view = BasesView(
        workspace,
        installations=INSTALLED,
        cfg_rules=[],
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
    )
    qtbot.addWidget(view)

    sequences = {shortcut.key().toString() for shortcut in view.findChildren(QShortcut)}

    assert "Alt+Up" in sequences
    assert "Alt+Down" in sequences


def test_alt_up_moves_the_current_record_before_its_neighbor(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Alt+↑ на «Демо Бухгалтерия» меняет местами с «Розница» над ним."""  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    assert _clients_children(view) == ["Розница", "Демо Бухгалтерия"]
    _show_exposed(qtbot, view)
    _select_key(view, _DEMO_ACCOUNTING_KEY)

    qtbot.keyClick(view, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)

    assert _clients_children(view) == ["Демо Бухгалтерия", "Розница"]
    assert errors == []


def test_alt_down_moves_the_current_record_after_its_neighbor(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Alt+↓ — зеркальная сторона Alt+↑, на записи над соседом."""
    view, _, errors, _ = _view(qtbot, workspace_factory)
    assert _clients_children(view) == ["Розница", "Демо Бухгалтерия"]
    _show_exposed(qtbot, view)
    _select_key(view, _RETAIL_GROUP_KEY)

    qtbot.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)

    assert _clients_children(view) == ["Демо Бухгалтерия", "Розница"]
    assert errors == []


def test_alt_up_at_the_top_of_the_group_is_a_no_op(qtbot: Any, workspace_factory: Any) -> None:
    """Соседа сверху нет — двигать некуда, и `move_within_group` не зовётся.

    `_RETAIL_GROUP_KEY` («Розница») уже стоит первой в «Клиенты» —
    без проверки границы `_move_current` попытался бы читать несуществующую
    строку модели (`neighbor_row < 0`).
    """
    view, _, errors, _ = _view(qtbot, workspace_factory)
    assert _clients_children(view) == ["Розница", "Демо Бухгалтерия"]
    _show_exposed(qtbot, view)
    _select_key(view, _RETAIL_GROUP_KEY)

    qtbot.keyClick(view, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)

    assert _clients_children(view) == ["Розница", "Демо Бухгалтерия"]
    assert errors == []


def test_alt_up_in_a_virtual_branch_is_a_no_op(qtbot: Any, workspace_factory: Any) -> None:
    """«Недавние»/«Избранное» не хранят порядок в OrderInList — Alt+↑ там немой.

    Без `_is_in_file_tree` запись, выбранная в «Недавних», переставилась бы
    в своей НАСТОЯЩЕЙ группе файла — не то место, которое видит пользователь.
    """
    view, _, errors, _ = _view(qtbot, workspace_factory)
    view.launch_key(_DEMO_ACCOUNTING_KEY)  # создаёт ветку «Недавние»
    _show_exposed(qtbot, view)
    _select_key(view, _DEMO_ACCOUNTING_KEY)  # «Недавние» стоит первой веткой
    assert "Недавние" in _current_path(view)
    before = _clients_children(view)

    qtbot.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)

    assert _clients_children(view) == before
    assert errors == []


# -- dropEvent: перевод Qt-события в примитивы handle_drop ---------------
#
# Настоящий drag под offscreen не подделать (нет ни MIME-сессии ОС, ни  # noqa: RUF003
# event.source() — Qt требует его для canDrop() в режиме InternalMove,  # noqa: RUF003
# а из Python его не задать). Но геометрия строки (visualRect) от  # noqa: RUF003
# состояния перетаскивания не зависит, и dropEvent можно вызвать напрямую
# с самодельным событием — так проверяется именно перевод: какую строку  # noqa: RUF003
# нашёл indexAt, что решил _where_at, что из этого дошло до handle_drop.


def test_drop_event_translates_middle_of_row_to_into(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    source_index = _root_index(view, 2)  # "Учёт серверный"
    target_index = _root_index(view, 0)  # "Клиенты"
    tree.setCurrentIndex(source_index)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    tree.dropEvent(_drop_event(tree.visualRect(target_index).center()))

    assert calls == [
        (
            (source_index.data(KEY_ROLE), target_index.data(KEY_ROLE), DropTarget.INTO),
            {"target_is_implicit": False, "target_is_virtual": False},
        )
    ]


def test_drag_move_rejects_the_middle_of_a_base_row(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Бросок «внутрь» записи отвергается курсором, а не молчанием.

    Замечание 3 ручного smoke №2 (09.08.2026): заказчик трижды бросал запись
    на строку другой записи и трижды не получал ничего — ни переноса, ни
    сообщения — и заключил, что перетаскивание сломано. Отказ по сути верен
    (вложить запись в запись нельзя, `_folder_of_drop` отдаёт `None`), неверна
    была его немота: два соседних отказа — неявный узел и служебная строка —
    объясняют себя сообщением, а этот молчал.

    Решение заказчика: показывать отказ курсором во время перетаскивания,
    а не окном после отпускания. Промах мимо межстрочья — частый случай,
    и модальное окно на каждый промах утомляет; курсор же виден до того,
    как кнопка отпущена, и ничего не требует закрывать.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    rect = _visible_rect_of_kind(view, RowKind.BASE)

    rejected = view._tree._rejects_drop_at(rect.center())
    assert rejected is True


def test_drag_move_allows_the_middle_of_a_group_row(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Внутрь группы класть можно — отказ не должен задеть работающий путь."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    rect = _visible_rect_of_kind(view, RowKind.GROUP)

    rejected = view._tree._rejects_drop_at(rect.center())
    assert rejected is False


def test_drag_move_allows_the_edge_of_a_base_row(qtbot: Any, workspace_factory: Any) -> None:
    """У края строки-базы бросок значит «до/после» — это разрешённая операция.

    Отказ обязан смотреть не только на вид строки, но и на сторону: запрещено
    ровно `INTO`, а перестановка относительно той же записи — нет.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    rect = _visible_rect_of_kind(view, RowKind.BASE)

    at_top = view._tree._rejects_drop_at(QPoint(rect.center().x(), rect.top()))
    at_bottom = view._tree._rejects_drop_at(QPoint(rect.center().x(), rect.bottom()))
    assert at_top is False
    assert at_bottom is False


def test_drag_move_event_ignores_a_rejected_position(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Отказ доходит до Qt: событие не принято, значит курсор рисует «нельзя».

    Проверяется именно `ignore()`, а не приём: настоящую drag-сессию под
    offscreen не подделать (`canDrop()` в режиме `InternalMove` требует
    `event.source() is self`, а из Python его не задать), поэтому
    противоположный случай `super().dragMoveEvent` всё равно отверг бы
    самодельное событие — и проверял бы Qt, а не нас.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    event, _mime = _drag_move_event(_visible_rect_of_kind(view, RowKind.BASE).center())
    event.accept()

    tree.dragMoveEvent(event)

    accepted = event.isAccepted()
    assert accepted is False


def test_drop_event_translates_top_edge_of_row_to_before(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    source_index = _root_index(view, 2)
    target_index = _root_index(view, 0)
    tree.setCurrentIndex(source_index)
    calls: list[DropTarget] = []
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: calls.append(args[2])
    )
    rect = tree.visualRect(target_index)

    tree.dropEvent(_drop_event(QPoint(rect.center().x(), rect.top())))

    assert calls == [DropTarget.BEFORE]


def test_drop_event_translates_bottom_edge_of_row_to_after(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    source_index = _root_index(view, 2)
    target_index = _root_index(view, 0)
    tree.setCurrentIndex(source_index)
    calls: list[DropTarget] = []
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: calls.append(args[2])
    )
    rect = tree.visualRect(target_index)

    tree.dropEvent(_drop_event(QPoint(rect.center().x(), rect.bottom())))

    assert calls == [DropTarget.AFTER]


def test_drop_event_on_implicit_node_sets_target_is_implicit(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    source_index = _root_index(view, 2)
    implicit_index = _root_index(view, 5)  # "Нет такой группы"
    assert implicit_index.data(KIND_ROLE) == RowKind.IMPLICIT_GROUP.value
    tree.setCurrentIndex(source_index)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    tree.dropEvent(_drop_event(tree.visualRect(implicit_index).center()))

    assert calls == [
        (
            (source_index.data(KEY_ROLE), None, DropTarget.INTO),
            {"target_is_implicit": True, "target_is_virtual": False},
        )
    ]


def test_drop_event_on_section_header_sets_target_is_virtual(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, common_group_cfg_paths: Any
) -> None:
    """Заголовок ветки («Общие списки») — `target_is_virtual`, не `target_is_implicit`.

    Круг правок 1 ревью задачи 14: `RowKind.SECTION` — тот же пустой
    `KEY_ROLE`, что и у неявного узла, но другой `KIND_ROLE`. Проверка одна
    на весь класс заголовков (`_find_index_by_kind` берёт первую строку
    вида `SECTION` — здесь это «Общие списки», единственная в этой
    фикстуре), а не отдельно на «Избранное»/«Недавние»/«Общие списки»:
    все три ветки заводятся одним и тем же `RowKind.SECTION` в `display_forest`,
    и `dropEvent` не различает их по имени.
    """  # noqa: RUF002
    view, _, _, _ = _view(
        qtbot, workspace_factory, cfg_paths=common_group_cfg_paths
    )
    tree = view._tree
    source_index = _root_index(view, 2)
    section_index = _find_index_by_kind(view, RowKind.SECTION)
    tree.setCurrentIndex(source_index)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    tree.dropEvent(_drop_event(tree.visualRect(section_index).center()))

    assert calls == [
        (
            (source_index.data(KEY_ROLE), None, DropTarget.INTO),
            {"target_is_implicit": False, "target_is_virtual": True},
        )
    ]


def test_drop_event_on_note_row_sets_target_is_virtual(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, broken_common_cfg_paths: Any
) -> None:
    """Строка ошибки чтения общего списка (`RowKind.NOTE`) — тоже `target_is_virtual`.

    Круг правок 1 ревью задачи 14: `NOTE`-строка — третий вид пустого
    `KEY_ROLE`, отличный и от неявного узла, и от заголовка ветки.
    """  # noqa: RUF002
    view, _, _, _ = _view(
        qtbot, workspace_factory, cfg_paths=broken_common_cfg_paths
    )
    tree = view._tree
    # NOTE лежит внутри свёрнутой по умолчанию ветки «Общие списки»:
    # visualRect() невидимой (не развёрнутой) строки — вырожденный QRect,
    # и клик по его центру попал бы совсем не туда. expandAll() делает  # noqa: RUF003
    # каждую строку измеримой, не подменяя саму проверку.
    tree.expandAll()
    source_index = _root_index(view, 2)
    note_index = _find_index_by_kind(view, RowKind.NOTE)
    tree.setCurrentIndex(source_index)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    tree.dropEvent(_drop_event(tree.visualRect(note_index).center()))

    assert calls == [
        (
            (source_index.data(KEY_ROLE), None, DropTarget.INTO),
            {"target_is_implicit": False, "target_is_virtual": True},
        )
    ]


def test_drop_event_with_no_current_row_calls_nothing(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    """Перетаскивание строки без ключа (заголовок, неявный узел) — не источник.

    `currentIndex()` пуста здесь нарочно (`setCurrentIndex(QModelIndex())`):
    dropEvent не имеет представления о ключе перетащенной строки и обязан
    ничего не делать, а не звать `handle_drop` с чем попало.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    tree.setCurrentIndex(QModelIndex())
    calls: list[object] = []
    monkeypatch.setattr(view, "handle_drop", lambda *args, **kwargs: calls.append(1))

    tree.dropEvent(_drop_event(tree.visualRect(_root_index(view, 0)).center()))

    assert calls == []


def test_drop_event_always_ignores_the_event(qtbot: Any, workspace_factory: Any) -> None:
    """Событие не принимается никогда — перестановку строк делает rebuild().

    Замечание ревью задачи 14 («Мелочь»): свежесозданный `QDropEvent` в этой
    сборке PySide6 и так возвращает `isAccepted() is False` — без явного
    `event.accept()` до вызова тест был бы зелёным, даже убери из `dropEvent`
    `event.ignore()` совсем (мутацию 2 ловит другой тест,
    `test_drop_event_never_lets_qt_move_rows_itself`, но докстринг обещал
    больше, чем эта проверка доказывала сама по себе). Событие здесь
    заранее переведено в принятое состояние, и `dropEvent` обязан вернуть
    его обратно.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    tree.setCurrentIndex(_root_index(view, 2))
    event = _drop_event(tree.visualRect(_root_index(view, 0)).center())
    event.accept()
    assert event.isAccepted() is True

    tree.dropEvent(event)

    assert event.isAccepted() is False


def test_drop_event_never_lets_qt_move_rows_itself(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any
) -> None:
    """Мутационная проверка шага 3 задачи 14 (`super().dropEvent()` вместо `ignore()`).

    Если бы `dropEvent` в конце звал `super().dropEvent(event)` вместо
    `event.ignore()`, Qt попытался бы сам вставить строку по mime-данным
    источника — уже в модели, которую `rebuild()` внутри `handle_drop`
    успел подменить новым экземпляром. Проверено экспериментом при
    подготовке задачи: `super()` добавляет цели лишнего ребёнка, собранного
    из чужого mime, не убирая источник, — ни то ни другое не соответствует
    ни экрану, ни файлу. Операция здесь намеренно отказывает
    (`ReadOnlySourceError`), чтобы поймать именно эту мутацию: дерево
    обязано остаться таким, каким его вернул `rebuild()`, без лишнего
    потомка у цели.

    `setDragDropMode(DragDrop)` — только для этого теста, не для боевого
    кода (там `InternalMove`, см. `BasesView.__init__`): `canDrop()` Qt
    в режиме `InternalMove` требует `event.source() is self`, а `source()`
    у события, собранного вручную, всегда пуст — `super().dropEvent()`
    молча проигнорировал бы событие и в исправном, и в сломанном
    `dropEvent`, и мутация осталась бы незамеченной. Геометрия перевода
    (что проверяют тесты выше) от режима не зависит — отличается только
    то, готова ли Qt принять событие, а не то, где оно легло.
    """  # noqa: RUF002
    view, _, errors, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    tree.setDragDropMode(QTreeView.DragDropMode.DragDrop)
    source_index = _root_index(view, 2)  # "Учёт серверный"
    target_index = _root_index(view, 0)  # "Клиенты" — 2 потомка на старте
    tree.setCurrentIndex(source_index)
    mime = view.model().mimeData([source_index])
    children_before = view.model().itemFromIndex(target_index).rowCount()
    assert children_before == 2  # "Розница" и "Демо Бухгалтерия" — см. комментарий выше
    event = _drop_event(tree.visualRect(target_index).center(), mime=mime)

    with mock.patch.object(
        type(view.workspace()), "update_infobase", side_effect=ReadOnlySourceError("отказ")
    ):
        tree.dropEvent(event)

    assert len(errors) == 1
    assert isinstance(errors[0], ReadOnlySourceError)
    rebuilt_target = _root_index(view, 0)  # rebuild() подменил модель — индекс ищем заново
    assert rebuilt_target.data(KEY_ROLE) == _CLIENTS_KEY
    assert view.model().itemFromIndex(rebuilt_target).rowCount() == children_before


# -- Задача 20: приём каталога в разделе «Базы» -----------------------------


@pytest.mark.parametrize(
    "kind",
    [RowKind.SECTION, RowKind.NOTE, RowKind.IMPLICIT_GROUP, None],
)
def test_folder_for_dropped_directory_falls_back_to_root(
    qtbot: Any, workspace_factory: Any, kind: Any
) -> None:
    """Служебные строки и неявный узел дают корень, а не отказ.

    Пользователь целился в список, а не в конкретную ветку; диалог всё равно
    покажет выбранную группу до подтверждения (спека §3.4).
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    value = kind.value if kind is not None else None

    folder = view.folder_for_dropped_directory(None, value)

    assert folder == ROOT


def test_folder_for_dropped_directory_uses_the_group_under_cursor(
    qtbot: Any, workspace_factory: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    group = next(i for i in view.workspace().items() if i.is_group)

    folder = view.folder_for_dropped_directory(group.key, RowKind.GROUP.value)

    assert folder == group_path(group.folder, group.name)


def test_folder_for_dropped_directory_uses_the_parent_of_a_base(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Бросок на запись значит «рядом с ней», то есть в её группу."""  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    base = next(
        i for i in view.workspace().items() if not i.is_group and i.folder != ROOT
    )

    folder = view.folder_for_dropped_directory(base.key, RowKind.BASE.value)

    assert folder == normalize_folder(base.folder)


def test_folder_for_dropped_directory_rejects_a_dangling_folder(
    qtbot: Any, workspace_factory: Any
) -> None:
    """Висячий `Folder` группой не является — такого пункта в диалоге нет.

    [Ф] T-05.7: путь, которому не соответствует ни одна секция, платформа
    рисует неявным узлом. Вернуть его как группу значило бы отдать `set_folder`
    значение, которого нет в списке, и диалог отказал бы уже после броска.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    # Фикстура `anonymized.v8i` такую запись уже содержит («Потерянная»),
    # поэтому состояние не портим — берём готовый краевой случай.
    orphan = next(
        item
        for item in view.workspace().items()
        if not item.is_group and normalize_folder(item.folder) not in view._group_paths()
    )

    folder = view.folder_for_dropped_directory(orphan.key, RowKind.BASE.value)

    assert folder == ROOT


def test_dialog_from_dropped_directory_is_prefilled(
    qtbot: Any, workspace_factory: Any, tmp_path: Any
) -> None:
    """Путь, имя и группа подставлены до показа диалога.

    Сборка отделена от показа тем же приёмом, что у `_build_add_dialog`:
    `exec()` блокирует offscreen-тесты, и без разделения этот путь остался бы
    без покрытия — дефект, который ревью задачи 8 нашло у `show_properties`.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    directory = tmp_path / "Бухгалтерия"
    directory.mkdir()
    group = next(i for i in view.workspace().items() if i.is_group)

    dialog = view.build_dialog_for_dropped_directory(
        str(directory), group.key, RowKind.GROUP.value
    )
    qtbot.addWidget(dialog)

    name, connect, folder = dialog.new_record()
    assert name == "Бухгалтерия"
    assert connect == 'File="' + str(directory) + '";'
    assert folder == group_path(group.folder, group.name)


def test_tree_drop_of_a_directory_opens_the_add_dialog(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Каталог, брошенный на строку, доходит до add_infobase_from_directory."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    rect = _visible_rect_of_kind(view, RowKind.GROUP)
    index = tree.indexAt(rect.center())
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: calls.append(args)
    )
    mime = _directory_mime(tmp_path)

    tree.dropEvent(_drop_event(rect.center(), mime))

    assert calls == [(str(tmp_path), index.data(KEY_ROLE), RowKind.GROUP.value)]


def test_tree_drop_of_a_directory_ignores_a_stale_current_row(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Ветка каталога проверяется ДО чтения currentIndex() — порядок несущий.

    Находка мутационной проверки шага 10: `test_tree_drop_of_a_directory_
    opens_the_add_dialog` не задевает эту перестановку, потому что в свежем
    дереве `currentIndex()` невалиден и `source_key` пуст независимо от
    порядка. Реальный риск — строка, оставшаяся текущей от предыдущего клика
    пользователя (никак не связанного с этим перетаскиванием из Проводника):
    у чужого перетаскивания «текущей строки этого дерева» нет по смыслу, и
    если бы ветка каталога стояла после чтения `currentIndex()`, чужой drop
    прочитался бы ещё и как internal-move той старой строки — `handle_drop`
    получил бы вызов, которого быть не должно.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    stale = next(i for i in view.workspace().items() if not i.is_group)
    _select_key(view, stale.key)
    rect = _visible_rect_of_kind(view, RowKind.GROUP)
    index = tree.indexAt(rect.center())
    add_calls: list[tuple[object, ...]] = []
    drop_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: add_calls.append(args)
    )
    monkeypatch.setattr(
        view, "handle_drop", lambda *args, **kwargs: drop_calls.append(args)
    )
    mime = _directory_mime(tmp_path)

    tree.dropEvent(_drop_event(rect.center(), mime))

    assert add_calls == [(str(tmp_path), index.data(KEY_ROLE), RowKind.GROUP.value)]
    assert drop_calls == []


def test_tree_drop_of_a_file_is_not_taken_for_a_directory(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    """Файл — не каталог: путь добавления не запускается вовсе."""
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    rect = _visible_rect_of_kind(view, RowKind.GROUP)
    plain = tmp_path / "не-каталог.txt"
    plain.write_text("x", encoding="utf-8")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: calls.append(args)
    )

    # Ссылка на mime держится в переменной до вызова dropEvent — иначе сборщик
    # мусора может забрать `QMimeData` до того, как `event.mimeData()` успеет
    # прочитать её изнутри обработчика, и вернуть висячий объект (та же мина,
    # что описана в докстринге `_drag_move_event`; здесь она воспроизводима
    # и на `QDropEvent`, поймано при написании этого теста).
    mime = _directory_mime(plain)

    tree.dropEvent(_drop_event(rect.center(), mime))

    assert calls == []


def test_tree_drag_move_accepts_a_directory_over_a_base_row(
    qtbot: Any, workspace_factory: Any, tmp_path: Any
) -> None:
    """Над строкой-записью каталог принимается, хотя своя запись — нет.

    Разный ответ на один жест намеренный (спека §3.4): своя запись
    «вкладывается» и потому отвергается, чужой каталог «добавляется рядом».
    """
    view, _, _, _ = _view(qtbot, workspace_factory)
    tree = view._tree
    rect = _visible_rect_of_kind(view, RowKind.BASE)
    event, _mime = _drag_move_event(rect.center(), _directory_mime(tmp_path))
    event.ignore()

    tree.dragMoveEvent(event)

    accepted = event.isAccepted()
    assert accepted is True


def test_search_field_does_not_accept_drops(qtbot: Any, workspace_factory: Any) -> None:
    """Иначе QLineEdit вставит путь каталога текстом в строку поиска."""
    view, _, _, _ = _view(qtbot, workspace_factory)

    accepts = view._search.acceptDrops()

    assert accepts is False


def test_view_drop_outside_the_tree_adds_to_root(
    qtbot: Any, workspace_factory: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    view, _, _, _ = _view(qtbot, workspace_factory)
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        view, "add_infobase_from_directory", lambda *args: calls.append(args)
    )
    # Ссылка держится в переменной до вызова dropEvent — та же причина,
    # что и у _directory_mime(plain) выше (test_tree_drop_of_a_file_...).  # noqa: RUF003
    mime = _directory_mime(tmp_path)

    view.dropEvent(_drop_event(QPoint(0, 0), mime))

    assert calls == [(str(tmp_path),)]


# -- задача 17: пункт «Создать ярлык…» --------------------------------------


def _expected_link(name: str) -> bytes:
    """Ожидаемые байты ярлыка — через те же чистые функции, что и вьюха.

    Формат тут не дублируется намеренно: за него отвечает
    `tests/unit/test_shell_link.py`, а этот тест проверяет только то,
    что вьюха собрала ярлык на нашу программу с нужным именем базы.
    """  # noqa: RUF002
    target, arguments = shortcut_command(
        sys.executable, name, frozen=getattr(sys, "frozen", False)
    )
    return build_shell_link(target, arguments, target.parent, f"{name} — OneCStarter")


def test_context_menu_has_create_shortcut_action(qtbot, workspace_factory):
    view, _, _, _ = _view(qtbot, workspace_factory)
    key = "id:44444444-4444-4444-4444-444444444444"
    item = next(i for i in view.workspace().items() if i.key == key)
    assert "Создать ярлык…" in [action.text() for action in view._build_menu(item, key).actions()]


def test_web_base_also_offers_a_shortcut(qtbot, workspace_factory):
    """Веб-база тоже запускается через нас — ярлык на неё осмыслен.

    Ярлык зовёт нашу программу с `--ib-name`, а та для веб-базы открывает
    браузер (`services/launch.py`). Пункты клиентов веб-базе не показываются,
    но этот — показывается.
    """  # noqa: RUF002
    view, _, _, _ = _view(qtbot, workspace_factory)
    item = next(i for i in view.workspace().items() if i.name == "Портал")
    assert "Создать ярлык…" in [
        action.text() for action in view._build_menu(item, item.key).actions()
    ]


def test_create_shortcut_writes_link_for_the_base(qtbot, workspace_factory, tmp_path):
    destination = tmp_path / "Демо Бухгалтерия.lnk"
    view, _, errors, _ = _view(
        qtbot, workspace_factory, choose_shortcut_path=lambda parent, suggested: str(destination)
    )
    view.create_shortcut("id:44444444-4444-4444-4444-444444444444")
    assert errors == []
    assert destination.read_bytes() == _expected_link("Демо Бухгалтерия")


def test_create_shortcut_suggests_desktop_and_safe_file_name(qtbot, workspace_factory):
    """Диалогу подставляется рабочий стол и имя файла из имени базы."""
    suggested: list[str] = []

    def choose(parent, path):
        suggested.append(path)
        return ""

    view, _, _, _ = _view(qtbot, workspace_factory, choose_shortcut_path=choose)
    view.create_shortcut("id:44444444-4444-4444-4444-444444444444")
    assert Path(suggested[0]).name == safe_file_name("Демо Бухгалтерия")
    assert Path(suggested[0]).parent == Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    )


def test_create_shortcut_cancelled_writes_nothing(qtbot, workspace_factory, tmp_path):
    """Отказ от диалога (пустой путь) — ни файла, ни ошибки."""
    view, _, errors, _ = _view(
        qtbot, workspace_factory, choose_shortcut_path=lambda parent, suggested: ""
    )
    view.create_shortcut("id:44444444-4444-4444-4444-444444444444")
    assert list(tmp_path.iterdir()) == [tmp_path / "ibases.v8i"]
    assert errors == []


def test_create_shortcut_reports_write_failure(qtbot, workspace_factory, tmp_path):
    """Несуществующий каталог назначения — сообщение, а не трассировка."""  # noqa: RUF002
    missing = tmp_path / "нет такого каталога" / "Демо.lnk"
    view, _, errors, _ = _view(
        qtbot, workspace_factory, choose_shortcut_path=lambda parent, suggested: str(missing)
    )
    view.create_shortcut("id:44444444-4444-4444-4444-444444444444")
    assert not missing.exists()
    assert len(errors) == 1
    assert "ярлык" in str(errors[0]).lower()


def test_create_shortcut_ignores_unknown_key(qtbot, workspace_factory):
    """Запись могла исчезнуть между построением меню и кликом."""
    asked: list[str] = []

    def choose(parent, path):
        asked.append(path)
        return ""

    view, _, errors, _ = _view(qtbot, workspace_factory, choose_shortcut_path=choose)
    view.create_shortcut("id:00000000-0000-0000-0000-000000000000")
    assert asked == []
    assert errors == []


def test_create_shortcut_refuses_ambiguous_name(qtbot, workspace_factory, tmp_path):
    """Дубль имени — отказ до диалога, а не бесполезный ярлык.

    Ярлык несёт имя, а не ключ, и при двух базах с одним именем запуск
    по нему невозможен. Без этой проверки ярлык создавался бы молча,
    а «Имя не единственное» пользователь получал бы потом и в другом
    месте — по клику, когда связь с созданием ярлыка уже не очевидна.
    """  # noqa: RUF002
    asked: list[str] = []

    def choose(parent, path):
        asked.append(path)
        return str(tmp_path / "должен был отказать.lnk")

    view, _, errors, _ = _view(qtbot, workspace_factory, choose_shortcut_path=choose)
    view.workspace().add_infobase("Демо Бухгалтерия", 'File="C:\\Bases\\Dup";')
    view.create_shortcut("id:44444444-4444-4444-4444-444444444444")
    assert asked == [], "диалог сохранения не должен открываться"
    assert not (tmp_path / "должен был отказать.lnk").exists()
    assert len(errors) == 1
    assert "не единственное" in str(errors[0])


# -- Задача 7: подменю «Очистить кэш» в контекстном меню записи --------------
#
# Доступность решается по данным записи (ID-GUID) и дешёвой проверке
# наличия каталога кэша (спека §3.4/§4 в редакции 23.08.2026); замер размера
# и само удаление — задача 8. FakeCacheOps — та же реализация ФС в памяти,
# что использует собственный набор `services/cache.py` (tests/unit/test_cache.py).

CACHE_GUID = "a1b2c3d4-e5f6-4a0b-8c1d-2e3f4a5b6c7d"


def _cache_env(tmp_path: Path) -> dict[str, str]:
    return {
        "APPDATA": str(tmp_path / "roaming"),
        "LOCALAPPDATA": str(tmp_path / "local"),
    }


def _cache_view(
    qtbot: Any,
    workspace_factory: Any,
    tmp_path: Path,
    ops: Any,
    section_lines: str,
) -> tuple[BasesView, list[LaunchCommand], list[ServicesError], list[str]]:
    (tmp_path / "ibases.v8i").write_bytes(section_lines.encode())
    return _view(
        qtbot, workspace_factory, cache_env=_cache_env(tmp_path), cache_ops=ops
    )


def _cache_actions(menu: Any) -> dict[str, Any] | None:
    submenu = next(
        (a.menu() for a in menu.actions() if a.text() == "Очистить кэш"), None
    )
    if submenu is None:
        return None
    return {a.text(): a for a in submenu.actions()}


def test_cache_submenu_enabled_when_id_and_dirs_exist(
    qtbot, workspace_factory, tmp_path
):
    ops = FakeCacheOps()
    for var in ("roaming", "local"):
        ops.tree[Path(tmp_path / var / "1C" / "1Cv8" / CACHE_GUID)] = []
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n',
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert actions is not None
    assert set(actions) == {"Пользовательский…", "Программный…"}
    assert actions["Пользовательский…"].isEnabled()
    assert actions["Программный…"].isEnabled()


def test_cache_items_disabled_without_id(qtbot, workspace_factory, tmp_path):
    """Спека §3.4: нет ID — адреса не существует, оба пункта неактивны.

    ЗАЩИТНЫЙ ТЕСТ пары к GUID-проверке §5.1: кандидат мутации — снять
    проверку в cache_path, пункты станут активными и тест упадёт.
    """  # noqa: RUF002
    ops = FakeCacheOps()
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        '[БезID]\r\nConnect=File="C:\\B";\r\n',  # noqa: RUF001
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert actions is not None
    assert not actions["Пользовательский…"].isEnabled()
    assert not actions["Программный…"].isEnabled()
    assert "ID" in actions["Программный…"].toolTip()


def test_cache_item_disabled_when_directory_missing(
    qtbot, workspace_factory, tmp_path
):
    """Каталог есть только у пользовательского кэша — программный неактивен."""  # noqa: RUF002
    ops = FakeCacheOps()
    ops.tree[Path(tmp_path / "roaming" / "1C" / "1Cv8" / CACHE_GUID)] = []
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n',
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert actions is not None
    assert actions["Пользовательский…"].isEnabled()
    assert not actions["Программный…"].isEnabled()
    assert actions["Программный…"].toolTip() == "кэш пуст"


def test_group_menu_has_no_cache_submenu(qtbot, workspace_factory, tmp_path):
    """Спека §3.4: у строки-группы подменю не показывается вовсе."""  # noqa: RUF002
    ops = FakeCacheOps()
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f"[Группа]\r\nID={CACHE_GUID}\r\nOrderInList=-1\r\nFolder=/\r\n",
    )
    item = view.workspace().items()[0]
    assert item.is_group
    menu = view._build_group_menu(item, item.key)
    assert _cache_actions(menu) is None


# -- Задача 8: сценарий очистки — замер → подтверждение → удаление → сводка --


def _ops_with_program_cache(tmp_path: Path) -> tuple[FakeCacheOps, Path]:
    """Фейк ФС с программным кэшем записи «Кэшная» + её ibases.v8i.

    Файл списка пишется здесь, ДО _view: workspace_factory копирует общую
    фикстуру, только если tmp_path/"ibases.v8i" ещё не создан.
    """  # noqa: RUF002
    (tmp_path / "ibases.v8i").write_bytes(
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    ops = FakeCacheOps()
    root = Path(tmp_path / "local" / "1C" / "1Cv8" / CACHE_GUID)
    ops.tree[root] = []
    ops.put(CacheEntry(root / "Config", EntryKind.DIR, 0))
    ops.put(CacheEntry(root / "Config" / "a.bin", EntryKind.FILE, 100))
    ops.put(CacheEntry(root / "top.pfl", EntryKind.FILE, 24))
    return ops, root


def test_clear_cache_without_confirmation_deletes_nothing(
    qtbot, workspace_factory, tmp_path
):
    """ЗАЩИТНЫЙ ТЕСТ (спека §3.5, §6): без «Да» не удаляется ничего.

    Кандидат мутационной проверки: снять подтверждение (звать clear без
    вопроса) — тест обязан упасть на «дерево изменилось».
    """  # noqa: RUF002
    ops, _root = _ops_with_program_cache(tmp_path)
    before = {p: list(es) for p, es in ops.tree.items()}
    asked: list[str] = []

    def refuse(parent, question):
        asked.append(question)
        return False

    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops, confirm_cache_clear=refuse,
        show_cache_report=lambda parent, text: pytest.fail("сводка без удаления"),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert ops.tree == before
    assert len(asked) == 1


def test_clear_cache_question_carries_name_and_size(qtbot, workspace_factory, tmp_path):
    ops, _root = _ops_with_program_cache(tmp_path)
    asked: list[str] = []

    def refuse(parent, question):
        asked.append(question)
        return False

    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=refuse,
        show_cache_report=lambda parent, text: None,
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert "Кэшная" in asked[0]
    assert "(124 Б)" in asked[0]  # размер посчитан ДО удаления


def test_clear_cache_confirmed_deletes_and_reports(qtbot, workspace_factory, tmp_path):
    ops, root = _ops_with_program_cache(tmp_path)
    shown: list[str] = []
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: True,
        show_cache_report=lambda parent, text: shown.append(text),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert root not in ops.tree
    assert shown == ["Удалено 2 файла, освобождено 124 Б."]


def test_clear_cache_reports_busy_files_once(qtbot, workspace_factory, tmp_path):
    """Спека §3.7: первичная ошибка в сводке, вторичная «папка не пуста» — нет."""
    ops, root = _ops_with_program_cache(tmp_path)
    ops.busy.add(root / "Config" / "a.bin")
    shown: list[str] = []
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: True,
        show_cache_report=lambda parent, text: shown.append(text),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert shown == [
        "Удалён 1 файл, освобождено 24 Б. Не удалось удалить 1 — "  # noqa: RUF001
        "файлы заняты запущенной 1С; закройте программу и повторите."  # noqa: RUF001
    ]


def test_cache_menu_item_trigger_reaches_clear_cache_with_right_kind(
    qtbot, workspace_factory, tmp_path
):
    """Клик пункта подменю доходит до сценария с правильной парой (key, kind).

    Закрывает ⚠️ ревью задачи 7: раньше лямбда пункта («Программный…») ни
    разу не выполнялась ни одним тестом — состав и подписи пунктов
    проверялись, но не сам клик. Меню строится тем же `_build_menu`, что
    и в проде, а не собирается вручную — иначе привязка (key, kind) внутри
    лямбды и работоспособность параметра-заглушки `_checked=False` остались
    бы непроверенными. `confirm_cache_clear` отказывает («Нет») — удаления
    не происходит, сводка не должна была бы открыться.
    """  # noqa: RUF002
    ops, _root = _ops_with_program_cache(tmp_path)
    asked: list[str] = []

    def refuse(parent, question):
        asked.append(question)
        return False

    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=refuse,
        show_cache_report=lambda parent, text: pytest.fail("сводка без удаления"),
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert actions is not None
    actions["Программный…"].trigger()
    assert len(asked) == 1
    assert "программный" in asked[0].casefold()
