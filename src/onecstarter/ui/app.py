"""Сборка приложения: окружение → Workspace → окно, трей, хоткей, watcher.

Единственное место, где ui знает про расположение файлов и обнаружение
платформы. default_app приходит из настройки «Клиент по умолчанию»
(settings.json, DefaultClient.default_app) — существование параметра App
уровня 1cestart.cfg по-прежнему экспериментально не подтверждено, и cfg
на выбор клиента не влияет. Без App секции и без настройки выбирается
тонкий клиент ([Ф] T-02.6).
"""

import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMessageBox,
    QProgressDialog,
    QSystemTrayIcon,
    QWidget,
)

from onecstarter.config.atomic import atomic_write
from onecstarter.config.cestart_cfg import parse_cestart_cfg
from onecstarter.config.shell_link import build_shell_link, shortcut_command
from onecstarter.domain.default_version import DefaultVersionRule, default_version_rules
from onecstarter.domain.launch import ClientConvention
from onecstarter.domain.server import ServerConvention
from onecstarter.domain.version import Installation, VersionNumber
from onecstarter.platform_1c import console
from onecstarter.platform_1c.discovery import cfg_paths, find_installations
from onecstarter.platform_1c.job import NullJob, ServerJob
from onecstarter.platform_1c.process_control import NullControl, ProcessControl, PsutilControl
from onecstarter.platform_1c.process_scan import NullScanner, ProcessScanner, PsutilScanner
from onecstarter.platform_1c.registry import load_conventions, load_server_conventions
from onecstarter.platform_1c.server_discovery import ServerInstallation, server_installations
from onecstarter.platform_1c.server_spawn import spawn_server
from onecstarter.services import autostart
from onecstarter.services.catalog import CommonListData, read_common_lists
from onecstarter.services.errors import (
    ConsoleRegistrationDeclinedError,
    ServerError,
    ServicesError,
    UserDataUnavailableError,
)
from onecstarter.services.hotkeys import parse_hotkey
from onecstarter.services.model import InfobaseItem
from onecstarter.services.servers import ScanSnapshot, ServersWorkspace
from onecstarter.services.settings import load_settings
from onecstarter.services.workspace import Workspace, WorkspacePaths
from onecstarter.ui import app_icon, rail_icons, theme
from onecstarter.ui.background import StartupTasks
from onecstarter.ui.bases.view import BasesView
from onecstarter.ui.hotkey import GlobalHotkey
from onecstarter.ui.servers.dialog import ConsoleDialog
from onecstarter.ui.servers.monitor import ServerMonitor
from onecstarter.ui.servers.view import ServersView
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
    servers: Path


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
    settings_path = appdata / "OneCStarter" / "settings.json"
    settings = load_settings(settings_path)
    workspace = Workspace(
        paths,
        installations=None,
        conventions=conventions,
        cfg_rules=rules,
        default_app=settings.default_client.default_app,
    )
    servers_path = appdata / "OneCStarter" / "servers.json"
    return Runtime(workspace, rules, list(conventions), settings_path, servers_path)


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
    не порождаются (обе фоновые задачи работают с тем, что в `env`). Реестр
    самопроверка подменяет сама (`NullRegistry`, долг №8): `SettingsView`
    читает его в конструкторе, и с настоящим `WindowsRegistry` результат
    зависел бы от того, включён ли автозапуск на машине сборщика.
    Ярлык пишется с фактическим `frozen`: в сборке исполняется ветка
    `frozen=True` (шаг 8 задачи 17, долг №7), из исходников — `frozen=False`.
    То же значение уходит в лог явной строкой (`smoke: frozen=...`, задача 10,
    спека §3.3) — раньше факт `sys.frozen == True` в сборке подтверждался
    только косвенно, через совпадение цели ярлыка с запущенным exe.

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
    # Реестр — заглушка, а не настоящий HKCU (долг №8): `SettingsView` читает  # noqa: RUF003
    # его прямо в конструкторе, и самопроверка собранного экземпляра иначе  # noqa: RUF003
    # зависела бы от того, включён ли автозапуск на машине сборщика.
    # `NullScanner`/`NullControl` — тот же довод для раздела «Серверы»
    # (T-08, задача 16): самопроверка не должна сканировать и трогать
    # процессы серверов 1С на машине сборщика. `registered_radmin` —  # noqa: RUF003
    # рядом: `ServersView.__init__` безусловно читает HKLM через
    # `current_console_version()` уже при сборке окна (см. докстринг
    # `_build_main_window`), самопроверка отвечает «не зарегистрирована».
    # `NullJob` — та же осторожность для Job Object'а (T-10, задача 7):  # noqa: RUF003
    # самопроверка не запускает серверов, но и создавать kernel-объект,
    # которого некому будет закрыть, ей ни к чему.
    try:
        window, built_tasks, _monitor = _build_main_window(
            application,
            runtime,
            env,
            autostart_registry=autostart.NullRegistry(),
            process_scanner=NullScanner(),
            process_control=NullControl(),
            registered_radmin=lambda: None,
            server_job=NullJob(),
        )
    except ServerError:
        # CRITICAL 2, финальное ревью ветки: конструктор ServersWorkspace
        # внутри _build_main_window (load_profiles на servers.json) не был
        # покрыт ничьим try — отказ уходил голой трассировкой мимо
        # UserDataUnavailableError/OSError веткой выше, которая ловит только
        # build_runtime. Самопроверка сборки обязана сообщить и вернуть 1,
        # не падать.
        _log.exception("smoke: окно не собралось")
        return 1
    try:
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
        frozen = bool(getattr(sys, "frozen", False))
        # Строка для build/smoke.py (задача 10, спека §3.3): явная, а не косвенная  # noqa: RUF003
        # через цель ярлыка, проверка того, что собранный exe исполняет
        # frozen-ветку. Значение — булев признак сборки, не пользовательские
        # данные (инвариант 5).
        _log.info("smoke: frozen=%s", frozen)
        target, arguments = shortcut_command(
            sys.executable, "OneCStarter smoke", frozen=frozen
        )
        payload = build_shell_link(target, arguments, target.parent, "OneCStarter smoke")
        atomic_write(Path(target_dir) / "smoke.lnk", payload)
        _log.info("smoke: ярлык записан")
        return 0
    finally:
        # `run_smoke` не крутит `application.exec()` — `aboutToQuit` не
        # наступает, и без явного снятия здесь собранный exe держал бы
        # сочетание занятым системой до конца процесса при каждой
        # самопроверке (находка финального ревью ветки, п. 9, продолжение).
        # `getattr` — `window.global_hotkey` объявлено `object | None`
        # (окну не положено знать настоящий тип, см. `ui/shell.py`).
        hotkey = getattr(window, "global_hotkey", None)
        if hotkey is not None:
            hotkey.dispose()
            application.removeNativeEventFilter(hotkey)


def _set_tray_tooltip(
    tray: QSystemTrayIcon | None, combination: str | None, *, busy: bool = False
) -> None:
    if tray is None:
        return
    if combination is None:
        tray.setToolTip("OneCStarter")
    elif busy:
        tray.setToolTip(f"OneCStarter — {combination} занято другим приложением")
    else:
        tray.setToolTip(f"OneCStarter — {combination}")


class _ConsoleWorkspace(Protocol):
    """Часть `ServersWorkspace`, которую действительно использует `_console_flow`.

    Протокол, а не сам `ServersWorkspace` — тот же довод, что у
    `ProcessScanner`/`ProcessControl` (`platform_1c/process_scan.py`,
    `process_control.py`): узкая структурная зависимость вместо конкретного
    класса делает функцию тестируемой фейком без наследования от реального
    `ServersWorkspace` (у него собственный конструктор с эффектами) и без
    `# type: ignore` на границе теста.
    """  # noqa: RUF002

    def current_console_version(self) -> VersionNumber | None: ...

    def register_console(self, target: ServerInstallation) -> None: ...

    def open_console(self, root: Path, convention: ServerConvention) -> None: ...


def _console_flow(
    workspace: _ConsoleWorkspace,
    installed: Sequence[ServerInstallation],
    running_versions: Sequence[VersionNumber],
    convention: ServerConvention,
    *,
    show_error: Callable[[str], None],
    show_info: Callable[[str], None],
    run_dialog: Callable[[ConsoleDialog], int] = lambda dialog: dialog.exec(),
    parent: QWidget | None = None,
) -> None:
    """Проводка диалога «Консоль администрирования…» (T-08, задача 16, §7 спеки).

    Вынесена из `on_console` (`_build_main_window`) в функцию уровня модуля
    ради инъекции `run_dialog` — исполнителя диалога: настоящая реализация
    зовёт блокирующий `QDialog.exec()`, тестовая — программно кликает по
    нужной кнопке (`register_button()`/`open_button()`) и отдаёт
    `dialog.result()`, ни разу не поднимая модальный цикл событий (тот же
    приём, что `_accept`/`_reject` в тестах `ServerProfileDialog`,
    `tests/ui/test_servers_view.py`).

    `ConsoleDialog.register_button()`/`open_button()` сами диалог не закрывают
    (задача 15, докстринг `ui/servers/dialog.py`: обработчики клика — забота
    вызывающего кода этой задачи) — здесь они подключаются к `accept()` с
    запоминанием, какая кнопка привела к принятию, чтобы отличить «Сделать
    текущей и открыть» от простого «Открыть».

    Отказ пользователя в UAC (`ConsoleRegistrationDeclinedError`) — штатный
    исход §7 спеки, не ошибка программы: `show_info`, не `show_error`.
    Перехватывается ДО общего `ServicesError` — `ConsoleRegistrationDeclinedError`
    сама наследует `ServerError`/`ServicesError` (`services/errors.py`), и общий
    перехват первым замаскировал бы штатный исход под отказ.
    """  # noqa: RUF002
    current = workspace.current_console_version()
    dialog = ConsoleDialog.build(installed, current, running_versions, parent)
    action: list[str] = []

    def register() -> None:
        action.append("register")
        dialog.accept()

    def open_current() -> None:
        action.append("open")
        dialog.accept()

    dialog.register_button().clicked.connect(register)
    dialog.open_button().clicked.connect(open_current)

    if run_dialog(dialog) != QDialog.DialogCode.Accepted or not action:
        return

    if action[-1] == "register":
        selected = dialog.selected_installation()
        if selected is None:
            return
        try:
            workspace.register_console(selected)
        except ConsoleRegistrationDeclinedError as error:
            show_info(str(error))
            return
        except ServicesError as error:
            show_error(str(error))
            return
        root = selected.installation.path.parent
    else:
        match = next((si for si in installed if si.installation.version == current), None)
        if match is None:
            return
        root = match.installation.path.parent

    workspace.open_console(root, convention)


def _servers_word(n: int) -> str:
    """Склонение «сервер» под число `n` для вопроса гейта выхода (T-10, задача 6).

    Стандартное русское правило числительных: 1 — «сервер», 2-4 — «сервера»,
    иначе «серверов» — с исключением на 11-14 (родительный падеж множественного
    числа даже при остатке 1-4 от деления на 10: «11 серверов», не «11 сервер»).
    """  # noqa: RUF002
    if 11 <= n % 100 <= 14:
        return "серверов"
    last_digit = n % 10
    if last_digit == 1:
        return "сервер"
    if 2 <= last_digit <= 4:
        return "сервера"
    return "серверов"


def _confirm_quit_with_servers(
    running_count: Callable[[], int], ask: Callable[[str], bool]
) -> bool:
    """Гейт выхода: серверов нет — тихо `True`; иначе спросить пользователя (спека §12.3).

    T-10, задача 4 перевела серверы на дочерний жизненный цикл: закрытие
    (или крах) лаунчера гасит их вместе с ним через Job Object (задача 7).
    Молчаливый выход без вопроса потерял бы работающие кластеры без
    предупреждения, поэтому `n == 0` (`running_count` — обычно
    `ServersWorkspace.running_count`, число профилей с живым процессом по
    последнему снимку, `0` и до первого скана) — единственный случай, когда
    подтверждение не нужно и `ask` не зовётся вовсе. `_servers_word` даёт
    верное склонение числительного в тексте вопроса.
    """  # noqa: RUF002
    n = running_count()
    if n == 0:
        return True
    return ask(f"Остановить {n} {_servers_word(n)} и выйти?")


def _ask_quit_confirmation(parent: QWidget, message: str) -> bool:
    """Обёртка `QMessageBox.question` для гейта выхода — дефолт «Нет» (спека §12.3).

    Модульная функция, не замыкание внутри `_build_main_window` (находка
    ревью T-10, задача 6): `_build_main_window` собирает окно и для тестов
    (тот же приём, что `run_smoke`), и внутри тестового набора offscreen
    `QMessageBox.question` всё равно не показывается по-настоящему, но
    БЕЗУСЛОВНОЕ подключение настоящего диалога вешало бы teardown любого
    теста с работающим сервером (`qtbot`/`_assemble` зовут `window.close()`)
    в вечном модальном ожидании. Диалог поэтому передаётся СНАРУЖИ через
    параметр `quit_dialog` — `None` (тесты, `run_smoke`) оставляет
    `window.confirm_quit` пустым, реальным значением его наполняет только
    `main()`.

    Дефолтная кнопка `No`, а не `Yes`: диалог, спрашивающий про остановку
    РАБОТАЮЩИХ серверов, не должен позволять случайному Enter/пробелу
    согласиться на неё — тот же приём осторожности, что у диалогов удаления
    (`_default_confirm_removal`, `ui/servers/view.py`).
    """  # noqa: RUF002
    answer = QMessageBox.question(
        parent,
        "OneCStarter",
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def _build_main_window(
    application: QApplication,
    runtime: Runtime,
    env: Mapping[str, str],
    *,
    autostart_registry: autostart.Registry | None = None,
    process_scanner: ProcessScanner | None = None,
    process_control: ProcessControl | None = None,
    registered_radmin: Callable[[], Path | None] | None = None,
    quit_dialog: Callable[[QWidget, str], bool] | None = None,
    server_job: ServerJob | NullJob | None = None,
) -> tuple[MainWindow, StartupTasks, ServerMonitor]:
    """Собрать окно, трей, хоткей, watcher и фоновые задачи, не запуская их.

    Вынесено из `main()` (спека T-04.6, §3.2): окно обязано появиться
    раньше, чем обнаружение платформ и чтение общих списков закончатся —
    обе задачи могут висеть минутами (антивирус, сетевые шары). `main()`
    показывает окно и только затем зовёт `tasks.start()`/`monitor.start()` —
    здесь задачи и монитор серверов только собираются и подключаются
    к `Workspace`/`BasesView`/`ServersWorkspace`/`ServersView`, `start()`
    не вызывается ни разу («собрать, не запуская», T-08, задача 16).

    `process_scanner`/`process_control` — та же инъекция для `run_smoke`,
    что и `autostart_registry`: `None` собирает настоящие `PsutilScanner`/
    `PsutilControl`, а самопроверка сборки подставляет `NullScanner`/
    `NullControl` — она поднимает настоящее окно и не должна сканировать
    процессы машины сборщика (тот же довод, что у долга №8 T-04.7).

    `registered_radmin` — та же инъекция, но для ЧТЕНИЯ HKLM: находка этой
    задачи (не входила в план дословно) — `ServersView.__init__` зовёт
    `rebuild()` уже в конструкторе, а тот безусловно читает
    `ServersWorkspace.current_console_version()`, то есть настоящий HKLM
    ([Ф] Г2, `platform_1c/console.py::registered_radmin_path`) при КАЖДОЙ
    сборке окна, не только по явному действию пользователя над консолью —
    в отличие от процессов серверов, этого чтения не избежать инъекцией
    `process_scanner`/`process_control` в `ServersWorkspace`. `None` —
    настоящий `console.registered_radmin_path`, самопроверка сборки
    подставляет `lambda: None` (тот же довод, что у `NullScanner`/
    `NullControl` — долг №8: чтение HKLM машины сборщика не должно решать,
    что покажет self-test).

    `quit_dialog` — та же по духу инъекция, но найденная не при написании,
    а при мутационной проверке (T-10, задача 6, находка координатора):
    первая редакция ставила `window.confirm_quit` безусловно, с настоящим
    `_ask_quit_confirmation` внутри замыкания — teardown ЛЮБОГО теста
    с работающим сервером (`qtbot addWidget`/`_assemble` зовут
    `window.close()`) вешался на модальный `QMessageBox.question` под
    offscreen-платформой навсегда, потому что диалог там не показывается,
    но и не отвечает сам. `None` (тесты этого файла, `run_smoke` — гейта
    нет вовсе) оставляет `window.confirm_quit` пустым; значение передаёт
    только `main()` (`quit_dialog=_ask_quit_confirmation`) — единственное
    место, откуда реальный диалог вообще может появиться.

    `server_job` — тот же приём инъекции, что `process_scanner`/`process_control`,
    но для Job Object'а (T-10, задача 7, `platform_1c/job.py`): `None`
    собирает настоящий `ServerJob()` — это безопасно и для тестов, и для
    сборки окна как таковой, потому что создание kernel-объекта в нём
    ленивое (только при первом `assign()`, а не в конструкторе). `run_smoke`
    всё равно подставляет `NullJob()` явной инъекцией, тем же доводом, что
    `NullScanner`/`NullControl` (долг №8): самопроверка не должна создавать
    Job вовсе, а не полагаться на то, что лень конструктора её не выдаст.

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
        recent_limit=lambda: store.settings.recent_limit,
        palette=controller.palette,
        cache_env=env,
    )
    settings_view = SettingsView(
        controller,
        store,
        autostart_registry=(
            autostart_registry if autostart_registry is not None else autostart.WindowsRegistry()
        ),
        frozen=bool(getattr(sys, "frozen", False)),
        executable=sys.executable,
    )
    # Раздел «Серверы» (T-08, задача 16). `servers_workspace`/`server_installed`
    # (холдер — сеттера у ServersView нет, тот же приём, что `recent_limit=  # noqa: RUF003
    # lambda:` у BasesView) собраны раньше самого раздела: конструктору  # noqa: RUF003
    # ServersView нужны и воркспейс, и живой снимок установок сразу.
    # T-10, задача 4: конструктор ServersWorkspace лишился дефолта у spawn —  # noqa: RUF003
    # `server_spawn`/`logs_dir` теперь обязательны. T-10, задача 7: НАСТОЯЩИЙ
    # Job Object — `job` живёт длиной с сам процесс лаунчера (`server_job`  # noqa: RUF003
    # параметр функции; `None` собирает `ServerJob()`, `run_smoke` подставляет
    # `NullJob()`), `spawn_server` кладёт в него каждый запущенный сервер
    # сразу после `Popen` (`platform_1c/server_spawn.py`). [Ф] Б2 T-09:
    # закрытие/крах лаунчера закрывает хендл Job, и это гасит всё дерево
    # серверов вместе с ним — явного кода остановки серверов при выходе  # noqa: RUF003
    # приложения не требуется и здесь нет.
    logs_dir = runtime.servers.parent / "logs" / "servers"
    job = server_job if server_job is not None else ServerJob()
    servers_workspace = ServersWorkspace(
        runtime.servers,
        control=process_control if process_control is not None else PsutilControl(),
        server_spawn=lambda command, log: spawn_server(command, log, job),
        logs_dir=logs_dir,
        registered_radmin=(
            registered_radmin if registered_radmin is not None else console.registered_radmin_path
        ),
    )
    server_installed: list[ServerInstallation] = []

    # Манера показа — та же, что `ServersView._default_show_error`/
    # `_default_confirm_removal`: `QMessageBox` с иконкой, заголовком  # noqa: RUF003
    # «OneCStarter» и `parent=servers_view`. Определены здесь (не внутри
    # ServersView), потому что `_console_flow` — снаружи вьюхи и своего
    # способа показать ошибку/информацию не имеет.
    def _show_servers_error(message: str) -> None:
        box = QMessageBox(servers_view)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()

    def _show_servers_info(message: str) -> None:
        box = QMessageBox(servers_view)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()

    def on_console() -> None:
        installed_versions = [si.installation.version for si in server_installed]
        # [Ф] Г3: консоль требует точного совпадения сборки с сервером —  # noqa: RUF003
        # версии профилей, у которых сейчас есть живой процесс, идут  # noqa: RUF003
        # в ConsoleDialog как «работает» (её докстринг, ui/servers/dialog.py).
        running_versions = [
            status.resolved
            for status in servers_workspace.statuses(installed_versions)
            if status.processes and status.resolved is not None
        ]
        convention = load_server_conventions()[0]
        _console_flow(
            servers_workspace,
            list(server_installed),
            running_versions,
            convention,
            show_error=_show_servers_error,
            show_info=_show_servers_info,
            parent=servers_view,
        )

    # `request_scan`/`monitor` — взаимная вперёдссылка внутри одной функции:
    # `monitor` собирается ниже (ему нужен уже построенный `window` как
    # родитель), а `servers_view` нужен `monitor.scan_now` уже сейчас.  # noqa: RUF003
    # Обе лямбды не читают имя до первого настоящего вызова (клик/сигнал,  # noqa: RUF003
    # много позже возврата из этой функции), поэтому порядок безопасен —
    # тот же приём, что и у остальных обработчиков ниже (`tray`, `hotkey`).  # noqa: RUF003
    servers_view = ServersView(
        servers_workspace,
        installed=lambda: list(server_installed),
        palette=controller.palette,
        request_scan=lambda: monitor.scan_now(),
        show_error=_show_servers_error,
        on_console=on_console,
    )

    sections = [("Базы", view), ("Серверы", servers_view), ("Настройки", settings_view)]
    # Ключ — сам объект вьюхи, а не подпись: подпись показывается пользователю  # noqa: RUF003
    # и однажды может быть переименована, и тогда поиск по ней уронил бы старт
    # `StopIteration` ещё до создания окна (находка ревью ветки 22.08.2026).
    bases_section = next(i for i, (_t, w) in enumerate(sections) if w is view)
    servers_section = next(i for i, (_t, w) in enumerate(sections) if w is servers_view)
    settings_section = next(i for i, (_t, w) in enumerate(sections) if w is settings_view)
    window = MainWindow(sections, palette=controller.palette)
    window.set_section_icon(bases_section, rail_icons.bases_icon)
    window.set_section_icon(servers_section, rail_icons.servers_icon)
    window.set_section_icon(settings_section, rail_icons.settings_icon)

    monitor = ServerMonitor(
        process_scanner if process_scanner is not None else PsutilScanner(), parent=window
    )

    def on_scan(snapshot: ScanSnapshot) -> None:
        # Единственный путь, из которого зовётся on_scan_snapshot() (не
        # rebuild()) — круг исправлений 1, ревью задачи 16: §8 обязан видеть
        # именно СВЕЖИЙ снимок, а не любую перестройку карточек (докстринг  # noqa: RUF003
        # ServersView.on_scan_snapshot).
        servers_workspace.apply_scan(snapshot)
        servers_view.on_scan_snapshot()

    monitor.snapshot_ready.connect(on_scan)

    def on_theme_changed() -> None:
        # settings_view красится общим stylesheet (ThemeController._apply) —
        # у неё нет запечённых цветов и метода apply_palette. BasesView  # noqa: RUF003
        # и ServersView перекрашивать обязаны явно: цвета запечены в QBrush,
        # в стили карточек и в значки. И рельсу тоже: значки разделов —
        # пара пиксмапов из палитры.
        view.apply_palette(controller.palette)
        servers_view.apply_palette(controller.palette)
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

    def _build_confirm_quit(dialog: Callable[[QWidget, str], bool]) -> Callable[[], bool]:
        def confirm_quit() -> bool:
            return _confirm_quit_with_servers(
                servers_workspace.running_count, lambda message: dialog(window, message)
            )

        return confirm_quit

    # T-10, задача 6 (находка координатора, см. докстринг параметра
    # `quit_dialog` выше): гейт собирается ТОЛЬКО когда снаружи дали диалог —
    # без него `confirm_quit` остаётся `None`, и `MainWindow.closeEvent`
    # никогда не дойдёт до `QMessageBox.question`, даже под offscreen, даже
    # с работающим сервером.  # noqa: RUF003
    confirm_quit = _build_confirm_quit(quit_dialog) if quit_dialog is not None else None
    window.confirm_quit = confirm_quit

    def request_quit() -> None:
        """Пункт «Выход» трея — тот же гейт, что закрытие окна, плюс сам выход.

        Дублирует `MainWindow.closeEvent` не проводом через него (трей не
        закрывает окно, чтобы выйти — оно может быть уже скрыто в трее),
        а прямым вызовом того же `confirm_quit`: отказ пользователя обязан
        оставить приложение работающим, не только окно видимым. Без гейта
        (`confirm_quit is None` — тесты, `run_smoke`, хотя тот трей вообще
        не собирает) выход происходит сразу, без вопроса.

        Выход после подтверждения — обычный `application.quit()`, без единой
        строки, останавливающей серверы явно: [Ф] Б2 T-09 — дерево серверов
        гасит сама смерть процесса лаунчера, закрывающая хендл Job Object'а
        (kill-on-close, `platform_1c/job.py`), и до неё дело здесь не доходит
        вообще — эффект наступает уже ПОСЛЕ `application.quit()`, снаружи
        этой функции.
        """  # noqa: RUF002
        if confirm_quit is not None and not confirm_quit():
            return
        application.quit()

    tray = create_tray(
        window,
        favorites,
        view.launch_key,
        on_quit=request_quit,
        theme_mode=lambda: controller.mode,
        on_theme=controller.set_mode,
    )
    window.tray_available = tray is not None

    hotkey = GlobalHotkey(window.show_and_focus_search)
    application.installNativeEventFilter(hotkey)

    def dispose_hotkey() -> None:
        # Фильтр ставит не сам `GlobalHotkey` — его ставит эта функция  # noqa: RUF003
        # строкой выше (`application.installNativeEventFilter`), значит и
        # снимать обязан тот же владелец (находка финального ревью ветки,
        # п. 9): `GlobalHotkey.dispose()` снимает только регистрацию
        # `RegisterHotKey`, `removeNativeEventFilter` без этой обёртки
        # не звался вовсе.
        hotkey.dispose()
        application.removeNativeEventFilter(hotkey)

    application.aboutToQuit.connect(dispose_hotkey)
    # Ссылки на окне — тестам и на время жизни процесса: без них store
    # и хоткей собрал бы сборщик мусора сразу после выхода из функции.
    window.settings_store = store
    window.global_hotkey = hotkey

    def apply_close_to_tray() -> None:
        # Трея нет — настройка ведёт себя как выключенная (спека §2):
        # спрятать окно, из которого его нечем вернуть, значит потерять  # noqa: RUF003
        # программу с экрана.  # noqa: RUF003
        window.close_to_tray = store.settings.close_to_tray and tray is not None

    def apply_hotkey(text: str) -> str | None:
        """Перевесить хоткей. Текст отказа либо None."""
        spec = parse_hotkey(text)
        if spec is None:
            hotkey.rebind(None)
            _set_tray_tooltip(tray, None)
            return None
        if hotkey.rebind(spec):
            _set_tray_tooltip(tray, text)
            return None
        _set_tray_tooltip(tray, text, busy=True)
        return f"Сочетание {text} занято другим приложением"

    recent_limit_seen = store.settings.recent_limit

    def rebuild_if_recent_limit_changed() -> None:
        # Круг исправлений 1, находка 2: `store.changed` эмитируется на  # noqa: RUF003
        # любую настройку, а дереву есть дело только до `recent_limit`  # noqa: RUF003
        # («Недавние» строятся по этому числу). Смена темы уже перестраивает
        # дерево своим путём (controller.changed → on_theme_changed →
        # view.apply_palette → rebuild()) — безусловная перестройка здесь
        # дублировала бы её, а close_to_tray/хоткей к дереву отношения  # noqa: RUF003
        # не имеют вовсе (решение заказчика 20.08.2026).
        nonlocal recent_limit_seen
        current = store.settings.recent_limit
        if current == recent_limit_seen:
            return
        recent_limit_seen = current
        view.rebuild()

    def apply_default_client() -> None:
        runtime.workspace.set_default_app(store.settings.default_client.default_app)

    apply_close_to_tray()
    apply_default_client()
    store.changed.connect(apply_close_to_tray)
    store.changed.connect(apply_default_client)
    store.changed.connect(rebuild_if_recent_limit_changed)
    settings_view.set_hotkey_handler(apply_hotkey)

    problem = apply_hotkey(store.settings.hotkey)
    if problem is not None:
        settings_view.report_hotkey_problem(problem)
        if tray is not None:
            # Балун, а не модальное окно: при тихом автозапуске диалог  # noqa: RUF003
            # встречал бы пользователя при каждом входе в систему
            # (спека §4.3). **[Проверено, 19.08.2026, эксперимент §7]**
            tray.showMessage("OneCStarter", problem, QSystemTrayIcon.MessageIcon.Warning, 7000)
        else:
            # Трея нет — два канала из трёх (балун и тултип) вырождаются,
            # а третий, строка у поля, лежит в разделе, который пользователь  # noqa: RUF003
            # не открывал: программа стартует на «Базах» (долг №10). Раз
            # показать нечем, кроме окна, — открыть его сразу на «Настройках».  # noqa: RUF003
            # Диалога по-прежнему нет: без трея тихого старта не бывает,
            # `main` в этом случае окно показывает (спека §3.4).
            window.show_section(settings_section)

    tasks = StartupTasks(
        lambda: find_installations(env, runtime.conventions),
        lambda: read_common_lists(list(runtime.workspace.paths.cfg_paths)),
        parent=window,
    )

    def on_installations(found: list[Installation]) -> None:
        runtime.workspace.set_installations(found)
        view.apply_installations(found)
        # Серверные установки — фильтр найденных версий (server_installations),
        # не отдельное обнаружение: и ragent.exe, и radmin.dll должны реально
        # лежать на диске (докстринг platform_1c/server_discovery.py).
        server_installed[:] = server_installations(found, load_server_conventions())
        servers_view.rebuild()

    def on_common(data: CommonListData) -> None:
        runtime.workspace.apply_common_lists(data)
        view.rebuild()

    tasks.installations_ready.connect(on_installations)
    tasks.common_lists_ready.connect(on_common)

    return window, tasks, monitor


def main(argv: list[str] | None = None, *, start_hidden: bool = False) -> int:
    """Обычный запуск. `start_hidden` — старт при входе в Windows (спека §3.4).

    Тихий старт показывает окно всё равно, если трея нет: невидимый процесс,
    который нечем вызвать, пользователю не принадлежит. Признак — доступность
    трея САМА ПО СЕБЕ (`window.tray_available`), не `window.close_to_tray`
    (находка финального ревью ветки, п. 2): то поле уже смешивает настройку
    крестика И доступность трея через AND (спека §2), и пользователь,
    выключивший «сворачивание в трей» и включивший автозапуск, получал бы
    окно в лицо при каждом входе в Windows, хотя трей жив и скрываться
    было чем.
    """  # noqa: RUF002
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

    try:
        window, tasks, monitor = _build_main_window(
            application, runtime, os.environ, quit_dialog=_ask_quit_confirmation
        )
    except ServerError as error:
        # CRITICAL 2, финальное ревью ветки: try вокруг build_runtime выше
        # не покрывал конструктор ServersWorkspace внутри _build_main_window
        # (load_profiles на servers.json) — ServersUnavailableError уходила
        # голой трассировкой мимо обеих веток выше, которые ловят только
        # отказ build_runtime. Тот же образец, что UserDataUnavailableError:
        # сообщение с путём в окне, а не крах без объяснения.  # noqa: RUF003
        QMessageBox.critical(None, "OneCStarter", str(error))
        return 1
    if start_hidden and window.tray_available:
        _log.info("тихий старт: окно скрыто, программа в трее")
    else:
        window.show()
        _log.info("окно показано")
    tasks.start()
    # Монитор серверов — рядом с tasks.start(), не внутри _build_main_window  # noqa: RUF003
    # (её докстринг, «собрать, не запуская»): периодический скан обязан
    # начаться только после того, как окно решило, показываться ему сразу
    # или остаться скрытым в трее.
    monitor.start()
    return application.exec()
