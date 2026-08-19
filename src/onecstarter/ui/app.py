"""Сборка приложения: окружение → Workspace → окно, трей, хоткей, watcher.

Единственное место, где ui знает про расположение файлов и обнаружение
платформы. default_app в v1 не читается из cfg: существование параметра App
уровня 1cestart.cfg экспериментально не подтверждено — None, клиент
выбирается по App секции либо тонкий ([Ф] T-02.6).
"""

import logging
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from onecstarter.config.atomic import atomic_write
from onecstarter.config.cestart_cfg import parse_cestart_cfg
from onecstarter.config.shell_link import build_shell_link, shortcut_command
from onecstarter.domain.default_version import DefaultVersionRule, default_version_rules
from onecstarter.domain.launch import ClientConvention
from onecstarter.domain.version import Installation
from onecstarter.platform_1c.discovery import cfg_paths, find_installations
from onecstarter.platform_1c.registry import load_conventions
from onecstarter.services import autostart
from onecstarter.services.catalog import CommonListData, read_common_lists
from onecstarter.services.errors import ServicesError, UserDataUnavailableError
from onecstarter.services.hotkeys import parse_hotkey
from onecstarter.services.model import InfobaseItem
from onecstarter.services.settings import DEFAULT_RECENT_LIMIT
from onecstarter.services.workspace import Workspace, WorkspacePaths
from onecstarter.ui import app_icon, rail_icons, theme
from onecstarter.ui.background import StartupTasks
from onecstarter.ui.bases.view import BasesView
from onecstarter.ui.hotkey import GlobalHotkey
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.settings_view import SettingsView
from onecstarter.ui.shell import MainWindow
from onecstarter.ui.theme_controller import ThemeController
from onecstarter.ui.tray import create_tray
from onecstarter.ui.watcher import FileWatcher

_log = logging.getLogger("onecstarter.startup")


@dataclass(frozen=True)
class Runtime:
    workspace: Workspace
    cfg_rules: list[DefaultVersionRule]
    conventions: list[ClientConvention]
    settings: Path


def build_runtime(env: Mapping[str, str]) -> Runtime:
    """Быстрая часть старта: только локальные малые файлы (спека §3.2).

    Ни обнаружения платформ, ни общих списков: обе работы могут висеть
    минутами (антивирус, сетевые шары) и уходят в StartupTasks.
    """  # noqa: RUF002
    conventions = load_conventions()
    cfgs = cfg_paths(env)
    entries: list[tuple[str, str]] = []
    for cfg in cfgs:
        try:
            entries.extend(parse_cestart_cfg(cfg.read_bytes()))
        except OSError:
            continue
    rules = default_version_rules(entries)
    appdata = Path(env.get("APPDATA", "."))
    paths = WorkspacePaths(
        ibases=appdata / "1C" / "1CEStart" / "ibases.v8i",
        user_data=appdata / "OneCStarter" / "bases.json",
        cfg_paths=tuple(cfgs),
    )
    workspace = Workspace(
        paths,
        installations=None,
        conventions=conventions,
        cfg_rules=rules,
        default_app=None,
    )
    settings_path = appdata / "OneCStarter" / "settings.json"
    return Runtime(workspace, rules, list(conventions), settings_path)


def _complain(message: str) -> int:
    """Показать ошибку окном и вернуть код отказа.

    `QApplication` создаётся здесь, а не в начале `run_launch`: успешный
    запуск ничего не показывает, и собирать ради него всё Qt-приложение
    значило бы платить за окно, которого не будет. `QMessageBox.critical`
    крутит собственный модальный цикл — `exec()` приложения не нужен.
    """  # noqa: RUF002
    if QApplication.instance() is None:
        QApplication([])
    QMessageBox.critical(None, "OneCStarter", message)
    return 1


def _wait_startup(workspace: Workspace, tasks: StartupTasks) -> bool:
    """Дождаться фоновых задач; False — пользователь отменил.

    Диалог показывается только если не уложились в полсекунды: в норме
    (тёплый кэш антивируса) ожидание невидимо. Отмена возвращает управление
    сразу — фоновые потоки демоны, их не ждём (спека §3.5).
    """
    loop = QEventLoop()
    dialog = QProgressDialog(
        "Обнаружение установленных версий платформы…", "Отмена", 0, 0
    )
    dialog.setWindowTitle("OneCStarter")
    dialog.setMinimumDuration(0)  # показом управляем сами, см. таймер ниже
    cancelled: list[bool] = []

    def on_cancel() -> None:
        cancelled.append(True)
        loop.quit()

    dialog.canceled.connect(on_cancel)
    pending = {
        "installations": workspace.installations_pending,
        "common": workspace.common_lists_pending,
    }

    def done(kind: str) -> None:
        pending[kind] = False
        if not any(pending.values()):
            loop.quit()

    def on_installations(found: list[Installation]) -> None:
        workspace.set_installations(found)
        done("installations")

    def on_common(data: CommonListData) -> None:
        workspace.apply_common_lists(data)
        done("common")

    tasks.installations_ready.connect(on_installations)
    tasks.common_lists_ready.connect(on_common)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(dialog.show)
    timer.start(500)
    tasks.start()
    if any(pending.values()):
        loop.exec()
    timer.stop()
    # Результат — до close(), не после: QProgressDialog.close() сама эмитирует
    # canceled (тот же путь, что закрытие крестиком окна) независимо от того,
    # был диалог вообще показан — иначе успешное завершение задач тоже
    # попало бы в cancelled и функция всегда отдавала бы False.
    result = not cancelled
    dialog.close()
    return result


def run_launch(
    name: str,
    env: Mapping[str, str],
    *,
    make_tasks: Callable[[], StartupTasks] | None = None,
) -> int:
    """Запустить базу по имени и выйти. Окно не показывается.

    Ошибки идут в QMessageBox, а не в stdout: entry point собран поверх
    pythonw.exe, у которого нет консоли (§9 п. 4 спеки 4a), и текст ушёл бы
    в никуда — пользователь увидел бы ярлык, который молча ничего не делает.

    Имя, а не ключ привязки, потому что ключ меняется, когда записи
    дописывается `ID`: ярлык сломался бы от первой же правки записи
    через нас (`Workspace.find_by_name`).

    `build_runtime` больше не обнаруживает платформы и не читает общие
    списки сам (спека T-04.6, §3.2) — Workspace приходит pending, и без
    ожидания `find_by_name`/`launch` работали бы по пустому списку установок
    и незагруженным общим спискам. `make_tasks` — инъекция фабрики фоновых
    задач только для тестов, тот же приём, что `choose_shortcut_path`
    в `BasesView`: `None` собирает настоящий `StartupTasks`.
    """  # noqa: RUF002
    if not name.strip():
        return _complain(
            "Не указано имя информационной базы: ключ --ib-name без значения"  # noqa: RUF001
        )
    try:
        runtime = build_runtime(env)
    except UserDataUnavailableError as error:
        return _complain(str(error))
    except OSError as error:
        return _complain(f"Не удалось прочитать список баз: {error}")  # noqa: RUF001
    workspace = runtime.workspace
    if workspace.installations_pending or workspace.common_lists_pending:
        if QApplication.instance() is None:
            QApplication([])
        tasks = (
            make_tasks()
            if make_tasks is not None
            else StartupTasks(
                lambda: find_installations(env, runtime.conventions),
                lambda: read_common_lists(list(workspace.paths.cfg_paths)),
            )
        )
        if not _wait_startup(workspace, tasks):
            return 1  # отмена — потоки-демоны умрут вместе с процессом  # noqa: RUF003
    try:
        workspace.launch(workspace.find_by_name(name))
    except ServicesError as error:
        # Сюда приходят и «базы с таким именем нет», и «имя не единственное»,  # noqa: RUF003
        # и отказ самого запуска — все три текста слой services готовит
        # безопасными для показа (инвариант 5).
        return _complain(str(error))
    return 0


def run_smoke(
    target_dir: str,
    env: Mapping[str, str],
    *,
    timeout_ms: int = 30000,
    make_tasks: Callable[[], StartupTasks] | None = None,
) -> int:
    """Самопроверка собранного экземпляра — вызывает `build/smoke.py` (задача 10).

    Поднимает настоящее окно через `_build_main_window`, дожидается обеих
    фоновых задач (обнаружение платформ, чтение общих списков) и пишет
    ярлык `smoke.lnk` в `target_dir` нашим кодом (`shell_link.py`) — не ради
    самого файла, а как проверка того, что запись ярлыка работает именно
    в собранном экземпляре: если сборка PyInstaller потеряла зависимость
    или испортила кодировку, тест упадёт здесь, а не у пользователя при
    первом сохранении ярлыка на рабочий стол.

    Окружение готовит вызывающий: `QT_QPA_PLATFORM=offscreen` и подменённый
    `APPDATA` — живые данные пользователя не трогаются, процессы 1С
    не порождаются (обе фоновые задачи работают с тем, что в `env`).
    Ярлык пишется с фактическим `frozen`: в сборке исполняется ветка
    `frozen=True` (шаг 8 задачи 17, долг №7), из исходников — `frozen=False`.

    `make_tasks` — та же инъекция фабрики фоновых задач, что у `run_launch`,
    только для теста таймаута: молчаливая замена (`spawn`, ничего не
    запускающий) не эмитирует сигналов, и ожидание обязано остановиться
    по `timeout_ms`, а не повиснуть до конца прогона тестов.
    """  # noqa: RUF002
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication([])
    try:
        runtime = build_runtime(env)
    except (UserDataUnavailableError, OSError):
        _log.exception("smoke: рантайм не собрался")
        return 1
    window, built_tasks = _build_main_window(application, runtime, env)
    tasks = built_tasks if make_tasks is None else make_tasks()
    pending = {"installations": True, "common": True}
    loop = QEventLoop()

    def done(kind: str) -> None:
        pending[kind] = False
        if not any(pending.values()):
            loop.quit()

    tasks.installations_ready.connect(lambda _found: done("installations"))
    tasks.common_lists_ready.connect(lambda _data: done("common"))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    window.show()
    _log.info("smoke: окно показано")
    tasks.start()
    if any(pending.values()):
        loop.exec()
    timer.stop()
    if any(pending.values()):
        _log.error("smoke: фоновые задачи не завершились за %d мс", timeout_ms)
        return 1
    target, arguments = shortcut_command(
        sys.executable, "OneCStarter smoke", frozen=bool(getattr(sys, "frozen", False))
    )
    payload = build_shell_link(target, arguments, target.parent, "OneCStarter smoke")
    atomic_write(Path(target_dir) / "smoke.lnk", payload)
    _log.info("smoke: ярлык записан")
    return 0


def _build_main_window(
    application: QApplication, runtime: Runtime, env: Mapping[str, str]
) -> tuple[MainWindow, StartupTasks]:
    """Собрать окно, трей, хоткей, watcher и фоновые задачи, не запуская их.

    Вынесено из `main()` (спека T-04.6, §3.2): окно обязано появиться
    раньше, чем обнаружение платформ и чтение общих списков закончатся —
    обе задачи могут висеть минутами (антивирус, сетевые шары). `main()`
    показывает окно и только затем зовёт `tasks.start()` — здесь задачи
    только собираются и подключаются к `Workspace`/`BasesView`, `start()`
    не вызывается ни разу.

    Значок приложения ставится здесь же, до создания трея (замечание
    заказчика на контрольной точке 16.08.2026): `setWindowIcon` до этой
    задачи не вызывался нигде, и заголовок окна с Alt-Tab получали
    случайную Windows-иконку — третью, отличную от `.ico` панели задач
    и от собственного рисунка трея. `application_icon()` — тот же QIcon,
    что теперь собирает и `ui/tray.py::make_icon`, единственный источник
    глифа — `onecstarter.ui.app_icon`.
    """  # noqa: RUF002
    application.setWindowIcon(app_icon.application_icon())
    store = SettingsStore(runtime.settings, parent=application)
    controller = ThemeController(application, store)
    # installations=None: колонка версии покажет «…» до первого
    # apply_installations — Workspace на этом этапе тоже ещё pending
    # (build_runtime больше не обнаруживает платформы сам).
    view = BasesView(
        runtime.workspace,
        installations=None,
        cfg_rules=runtime.cfg_rules,
        # Заглушка: SettingsStore появится только в задаче 5, настоящий
        # провайдер из настроек подключит задача 9. Здесь — временная
        # ступень, константа по умолчанию, а не решение по проводке.  # noqa: RUF003
        recent_limit=lambda: DEFAULT_RECENT_LIMIT,
        palette=controller.palette,
    )
    settings_view = SettingsView(
        controller,
        store,
        autostart_registry=autostart.WindowsRegistry(),
        frozen=bool(getattr(sys, "frozen", False)),
        executable=sys.executable,
    )
    window = MainWindow(
        [("Базы", view), ("Настройки", settings_view)], palette=controller.palette
    )
    window.set_section_icon(0, rail_icons.bases_icon)
    window.set_section_icon(1, rail_icons.settings_icon)

    def on_theme_changed() -> None:
        # settings_view красится общим stylesheet (ThemeController._apply) —
        # у неё нет запечённых цветов и метода apply_palette. BasesView  # noqa: RUF003
        # перекрашивать обязаны явно: цвета запечены в QBrush и в значки.
        # И рельсу тоже: значки разделов — пара пиксмапов из палитры.
        view.apply_palette(controller.palette)
        window.apply_palette(controller.palette)

    controller.changed.connect(on_theme_changed)
    QGuiApplication.styleHints().colorSchemeChanged.connect(
        lambda _scheme: controller.refresh_system()
    )

    watcher = FileWatcher(runtime.workspace.paths.ibases, parent=window)

    def on_file_changed() -> None:
        if runtime.workspace.reload_if_changed():
            view.rebuild()

    watcher.changed.connect(on_file_changed)

    def favorites() -> list[InfobaseItem]:
        return [
            item
            for item in runtime.workspace.items()
            if not item.is_group and item.favorite
        ]

    tray = create_tray(
        window,
        favorites,
        view.launch_key,
        application.quit,
        theme_mode=lambda: controller.mode,
        on_theme=controller.set_mode,
    )
    window.close_to_tray = tray is not None

    hotkey = GlobalHotkey(window.show_and_focus_search)
    application.installNativeEventFilter(hotkey)
    hotkey.rebind(parse_hotkey(store.settings.hotkey))
    if tray is not None:
        tray.setToolTip("OneCStarter")
    application.aboutToQuit.connect(hotkey.dispose)

    tasks = StartupTasks(
        lambda: find_installations(env, runtime.conventions),
        lambda: read_common_lists(list(runtime.workspace.paths.cfg_paths)),
        parent=window,
    )

    def on_installations(found: list[Installation]) -> None:
        runtime.workspace.set_installations(found)
        view.apply_installations(found)

    def on_common(data: CommonListData) -> None:
        runtime.workspace.apply_common_lists(data)
        view.rebuild()

    tasks.installations_ready.connect(on_installations)
    tasks.common_lists_ready.connect(on_common)

    return window, tasks


def main(argv: list[str] | None = None) -> int:
    application = QApplication(argv if argv is not None else sys.argv)
    application.setApplicationName("OneCStarter")
    application.setStyleSheet(theme.stylesheet(theme.DARK))
    try:
        runtime = build_runtime(os.environ)
    except UserDataUnavailableError as error:
        # Молча подменить данные пустыми нельзя — затрётся живая история
        # (докстринг Workspace). Сообщение с путём, не трассировка.  # noqa: RUF003
        QMessageBox.critical(None, "OneCStarter", str(error))
        return 1
    except OSError as error:
        # Список баз нечитаем по-настоящему: нет прав, недоступен сетевой
        # профиль. Гонку с перезаписью платформой гасит reload_if_changed,  # noqa: RUF003
        # сюда доходит только устойчивый отказ. Стартовать с пустым списком  # noqa: RUF003
        # нельзя — пользователь решит, что базы пропали.
        QMessageBox.critical(
            None, "OneCStarter", f"Не удалось прочитать список баз: {error}"  # noqa: RUF001
        )
        return 1

    window, tasks = _build_main_window(application, runtime, os.environ)
    window.show()
    _log.info("окно показано")
    tasks.start()
    return application.exec()
