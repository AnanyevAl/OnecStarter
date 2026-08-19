import logging
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest
from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QCoreApplication,
    QEvent,
    QObject,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSystemTrayIcon,
)

from onecstarter.domain.launch import LaunchCommand
from onecstarter.services.catalog import EMPTY_COMMON_DATA
from onecstarter.services.hotkeys import parse_hotkey
from onecstarter.services.settings import DEFAULT_HOTKEY, Settings, ThemeMode, save_settings
from onecstarter.services.workspace import Workspace, WorkspacePaths
from onecstarter.ui import app as app_module
from onecstarter.ui import theme
from onecstarter.ui.app import _build_main_window, build_runtime, run_launch, run_smoke
from onecstarter.ui.background import StartupTasks
from onecstarter.ui.bases.view import BasesView
from onecstarter.ui.hotkey import GlobalHotkey
from onecstarter.ui.shell import MainWindow
from onecstarter.ui.theme_controller import ThemeController
from onecstarter.ui.watcher import FileWatcher

from .conftest import CONVENTIONS, FIXTURE, INSTALLED


def test_runtime_builds_on_empty_machine(tmp_path):
    # Пустое окружение: ни платформы, ни файлов — приложение всё равно
    # обязано собраться (пустой список, ошибок нет).
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)
    assert runtime.workspace.items() == []
    assert runtime.cfg_rules == []


def test_runtime_has_no_installations_and_pending_workspace(tmp_path):
    """Спека T-04.6, §3.2: build_runtime — быстрая часть старта, без сети/ФС-обхода.

    Обнаружение платформ и чтение общих списков уходят в StartupTasks —
    Runtime больше не несёт списка installations вовсе (поле удалено),
    а Workspace остаётся в pending до первого set_installations()/
    apply_common_lists() (проводит их _build_main_window).
    """  # noqa: RUF002
    runtime = build_runtime({"APPDATA": str(tmp_path)})
    assert runtime.workspace.installations_pending
    assert runtime.workspace.common_lists_pending


def test_runtime_reads_ibases_and_cfg(tmp_path):
    appdata = tmp_path / "appdata"
    start = appdata / "1C" / "1CEStart"
    start.mkdir(parents=True)
    (start / "ibases.v8i").write_bytes('[База]\r\nConnect=File="C:\\B";\r\n'.encode())
    import codecs

    (start / "1cestart.cfg").write_bytes(
        codecs.BOM_UTF16_LE + "DefaultVersion=8.3-8.3.22.1923\r\n".encode("utf-16-le")
    )
    runtime = build_runtime({"APPDATA": str(appdata)})
    assert [item.name for item in runtime.workspace.items()] == ["База"]
    assert len(runtime.cfg_rules) == 1


# -- задача 17: режим запуска по имени базы (--ib-name) ---------------------
#
# build_runtime подменяется во всех этих тестах намеренно. Настоящий
# build_runtime зовёт find_installations, и на машине с установленной  # noqa: RUF003
# платформой workspace.launch породил бы настоящий процесс 1С — прямой  # noqa: RUF003
# запрет CLAUDE.md («Не запускать процессы 1С без явной просьбы»).  # noqa: RUF003
# Подменённый Runtime несёт Workspace из workspace_factory, у которого  # noqa: RUF003
# spawn инжектирован и только записывает вызов.


@pytest.fixture
def runtime_with(monkeypatch, workspace_factory, tmp_path):
    def make():
        workspace, calls, opened = workspace_factory()
        runtime = app_module.Runtime(
            workspace=workspace,
            cfg_rules=[],
            conventions=[],
            settings=tmp_path / "settings.json",
        )
        monkeypatch.setattr(app_module, "build_runtime", lambda env: runtime)
        return workspace, calls, opened

    return make


@pytest.fixture
def shown_errors(monkeypatch):
    """Перехват QMessageBox.critical: текст ошибки вместо модального окна."""
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *args: messages.append(args[2]))
    )
    return messages


def test_run_launch_starts_base_by_name(runtime_with, shown_errors):
    """Ярлык несёт имя базы — режим находит её и запускает."""
    _, calls, _ = runtime_with()
    assert run_launch("Демо Бухгалтерия", {}) == 0
    assert len(calls) == 1
    assert shown_errors == []


def test_run_launch_finds_name_ignoring_case(runtime_with):
    """[Ф] T-05.3: платформа ищет имя регистронезависимо — и мы тоже."""
    _, calls, _ = runtime_with()
    assert run_launch("дЕмо бУхгалтерия", {}) == 0
    assert len(calls) == 1


def test_run_launch_reports_unknown_name(runtime_with, shown_errors):
    """Неизвестное имя — сообщение в окне, а не в stdout.

    Сборка стоит поверх pythonw.exe, у которого нет консоли (§9 п. 4
    спеки 4a): напечатанный текст ушёл бы в никуда, и пользователь увидел
    бы ярлык, который «ничего не делает».
    """  # noqa: RUF002
    _, calls, _ = runtime_with()
    assert run_launch("Такой базы нет", {}) == 1
    assert calls == []
    assert "Такой базы нет" in shown_errors[0]


def test_run_launch_reports_ambiguous_name(runtime_with, shown_errors):
    """Дубль имени: отказ с объяснением, а не запуск наугад."""  # noqa: RUF002
    workspace, calls, _ = runtime_with()
    workspace.add_infobase("Демо Бухгалтерия", 'File="C:\\Bases\\Dup";')
    assert run_launch("Демо Бухгалтерия", {}) == 1
    assert calls == []
    assert "не единственное" in shown_errors[0]


def test_run_launch_rejects_empty_name(monkeypatch, shown_errors):
    """Ключ --ib-name без значения не должен доходить до чтения списка."""
    def explode(env):
        raise AssertionError("build_runtime не должен вызываться")

    monkeypatch.setattr(app_module, "build_runtime", explode)
    assert run_launch("   ", {}) == 1
    assert "имя информационной базы" in shown_errors[0]


# -- задача T-06: ожидание pending-workspace с отменяемым прогрессом ---------  # noqa: RUF003
#
# `runtime_with`/`workspace_factory` сюда не годятся (см. комментарий в
# conftest.py): фабрика безусловно зовёт `apply_common_lists`, и получить
# от неё pending-Workspace нельзя. Ниже — тот же набор эффектов
# (fake_spawn, детерминированные now/new_id), но без него: installations=None
# и apply_common_lists ни разу не вызван, то есть ровно то, что отдаёт
# настоящий build_runtime (T-04.6, §3.2).


def _pending_workspace(tmp_path: Any) -> tuple[Workspace, list[LaunchCommand]]:
    calls: list[LaunchCommand] = []
    ibases = tmp_path / "ibases.v8i"
    shutil.copyfile(FIXTURE, ibases)

    def fake_spawn(command: LaunchCommand) -> int:
        calls.append(command)
        return 7

    workspace = Workspace(
        WorkspacePaths(ibases=ibases, user_data=tmp_path / "bases.json", cfg_paths=()),
        installations=None,
        conventions=CONVENTIONS,
        cfg_rules=[],
        default_app=None,
        spawn=fake_spawn,
        now=lambda: datetime.fromisoformat("2026-08-07T10:00:00+00:00"),
        new_id=lambda: "99999999-9999-9999-9999-999999999999",
    )
    assert workspace.installations_pending
    assert workspace.common_lists_pending
    return workspace, calls


def test_run_launch_waits_for_pending_workspace(monkeypatch, tmp_path, qapp):
    """Pending workspace обязан дождаться фона перед запуском (спека §3.5).

    `make_tasks` со синхронным `spawn` (задача выполняется тут же, в
    вызывающем потоке, а не в отдельном) — путь «тёплого кэша»: оба сигнала
    приходят внутри самого `tasks.start()`, раньше первой проверки
    `any(pending.values())` в `_wait_startup`, и `loop.exec()` не запускается
    вовсе. Диалог поэтому не показывается, но `_wait_startup` обязан пройти
    насквозь и вернуть `True` — запуск обязан дойти до spawn-заглушки.
    """  # noqa: RUF002
    workspace, calls = _pending_workspace(tmp_path)
    runtime = app_module.Runtime(
        workspace=workspace, cfg_rules=[], conventions=[], settings=tmp_path / "settings.json"
    )
    monkeypatch.setattr(app_module, "build_runtime", lambda env: runtime)

    def make_tasks() -> StartupTasks:
        return StartupTasks(
            lambda: INSTALLED,
            lambda: EMPTY_COMMON_DATA,
            spawn=lambda task: task(),
        )

    assert run_launch("Демо Бухгалтерия", {}, make_tasks=make_tasks) == 0
    assert len(calls) == 1


def test_run_launch_cancel_returns_one_without_launch(monkeypatch, tmp_path, qapp):
    """Отмена в диалоге прогресса — код 1, запуск не происходит (спека §3.5).

    `spawn`, который никого не запускает: фоновые задачи молчат, ни один
    сигнал не приходит, и `_wait_startup` обязан застрять в `loop.exec()`
    до отмены — не будь ожидания на месте, тест либо вернул бы 0
    без единого вызова `calls`, либо (не будь у `canceled` обработчика)
    завис бы до таймаута раннера.

    Диалог достаётся через `QApplication.topLevelWidgets()`: `QProgressDialog`
    в `_wait_startup` создаётся без родителя и попадает в список
    top-level виджетов сразу при конструировании, ещё до первого `show()` —
    500-мс таймер показа тут ни при чём, найти диалог можно и до того,
    как он станет видимым. Отмена — клик по настоящей кнопке «Отмена», а не
    вызов `dialog.cancel()`: этот слот лишь прячет диалог и `canceled`
    не эмитирует, сигнал подключён Qt прямо к `clicked()` кнопки.
    """  # noqa: RUF002
    workspace, calls = _pending_workspace(tmp_path)
    runtime = app_module.Runtime(
        workspace=workspace, cfg_rules=[], conventions=[], settings=tmp_path / "settings.json"
    )
    monkeypatch.setattr(app_module, "build_runtime", lambda env: runtime)

    def make_tasks() -> StartupTasks:
        return StartupTasks(
            lambda: INSTALLED,
            lambda: EMPTY_COMMON_DATA,
            spawn=lambda task: None,
        )

    def cancel_dialog() -> None:
        # `QProgressDialog.cancel()` только прячет диалог и не эмитирует
        # `canceled` (сигнал подключён Qt непосредственно к `clicked()`
        # кнопки) — клик по настоящей кнопке нужен, чтобы дойти до того же
        # пути, каким сигнал приходит от пользователя.
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QProgressDialog):
                button = widget.findChild(QPushButton)
                assert button is not None, "у QProgressDialog нет кнопки отмены"  # noqa: RUF001
                button.click()
                return
        raise AssertionError("диалог прогресса не найден среди topLevelWidgets")

    QTimer.singleShot(0, cancel_dialog)
    assert run_launch("Демо Бухгалтерия", {}, make_tasks=make_tasks) == 1
    assert calls == []


def test_run_launch_ready_workspace_skips_waiting(runtime_with, shown_errors):
    """Готовый workspace не должен звать `make_tasks` вовсе — не только не ждать.

    Фабрика-бомба вместо обычной проверки «make_tasks=None по умолчанию»:
    мутация Step 6 №2 (убрать условие `if ...pending` перед ожиданием)
    заставила бы звать `_wait_startup`/`make_tasks` всегда, и с обычным
    `run_launch("Демо Бухгалтерия", {})` это осталось бы незамеченным —
    настоящий `StartupTasks` под офскрин просто отработал бы вхолостую.
    """  # noqa: RUF002
    _, calls, _ = runtime_with()

    def bomb() -> StartupTasks:
        raise AssertionError("make_tasks не должен вызываться для готового workspace")

    assert run_launch("Демо Бухгалтерия", {}, make_tasks=bomb) == 0
    assert len(calls) == 1


# -- сборка приложения: проводка внутри main() (финальное ревью, I3) ---------
#
# `main()` не исполнялся в тестах ни разу, и каждая его строка-проводка могла  # noqa: RUF003
# быть удалена незаметно. Проверено на самой дорогой из них: удаление
# `controller.changed.connect(on_theme_changed)` оставляло весь набор зелёным,
# хотя ломало ВТОРОЕ из двух обязательных действий смены темы (спека §2.4) —  # noqa: RUF003
# stylesheet применился бы, а `QBrush` строк и значки остались бы в цветах  # noqa: RUF003
# прежней палитры. Сторож `test_theme_switch_leaves_no_stale_colours` зовёт
# `view.apply_palette` напрямую и этой проводки не касается.
#
# Настоящий `main()` вызывается целиком; подменяется только то, что в тесте
# недопустимо по существу: `build_runtime` (полез бы в реальный %APPDATA%
# и на реальную машину за платформой), `GlobalHotkey` (зарегистрировал бы
# системное сочетание на живой машине), `create_tray` (повесил бы значок
# в настоящий трей; своя проводка у него покрыта в test_tray.py) и  # noqa: RUF003
# `application.exec()` (крутил бы цикл событий бесконечно).


class _RecordingView(BasesView):
    """`BasesView`, записывающая перекраску, — всё остальное настоящее."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.palettes: list[theme.Palette] = []

    def apply_palette(self, palette: theme.Palette) -> None:
        self.palettes.append(palette)
        super().apply_palette(palette)


class _RecordingWindow(MainWindow):
    """`MainWindow`, записывающая перекраску, — всё остальное настоящее."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.palettes: list[theme.Palette] = []

    def apply_palette(self, palette: theme.Palette) -> None:
        self.palettes.append(palette)
        super().apply_palette(palette)


class _StyleHintsStub(QObject):
    """Двойник `QStyleHints`: свой `colorSchemeChanged`, живущий один тест.

    Настоящий `QGuiApplication.styleHints()` — объект приложения, общий
    на весь прогон, и подписка, которую `main()` на него вешает, пережила бы
    тест. Пережившее замыкание зовёт `controller.refresh_system()`, а тот
    в режиме AUTO доходит до `view.apply_palette` уже уничтоженного виджета:
    наблюдался плавающий access violation в чужом `QApplication.setStyleSheet`
    (тот сам меняет цветовую схему и поднимает `colorSchemeChanged`) примерно
    на половине прогонов — падал не тест, а процесс. Свой сигнал заодно делает
    проверяемой ещё одну строку проводки: следование системной теме.
    """  # noqa: RUF002

    colorSchemeChanged = Signal(int)  # noqa: N815


class _FakeTray:
    """Двойник `QSystemTrayIcon`: настоящий повесил бы значок в живой трей.

    Нужен ради ветки «трей есть»: именно она включает `close_to_tray`,
    то есть «закрытие окна прячет приложение, а не закрывает». `create_tray`
    сам покрыт своим набором (`test_tray.py`); здесь проверяется, что
    `main()` делает с его результатом.
    """  # noqa: RUF002

    def __init__(self) -> None:
        self.tooltips: list[str] = []

    def setToolTip(self, text: str) -> None:  # noqa: N802
        self.tooltips.append(text)


class _FakeHotkey(QAbstractNativeEventFilter):
    """Замена `GlobalHotkey`: настоящая зовёт `RegisterHotKey` у Windows.

    Наследует `QAbstractNativeEventFilter`: `_build_main_window` теперь ставит
    фильтр безусловно (`application.installNativeEventFilter(hotkey)`), а тот
    у PySide6 отказывает объекту неверного типа — обычный `object` здесь
    свалил бы `main()` с `TypeError` ещё до дела теста. `nativeEventFilter`
    переопределён пустышкой по той же причине: раз фильтр действительно
    ставится на `qapp`, метод — чистая виртуальная функция C++-базы, и Qt
    честно роняет `NotImplementedError` на первом же нативном событии сессии,
    не обязательно из теста хоткея (так и обнаружилось — падал несвязанный
    `test_watcher.py::test_atomic_replace_keeps_watching`).

    `instances` — реестр всех созданных за тест объектов: `qapp` у pytest-qt
    сессионный, `aboutToQuit` в тестах не эмитируется (см. `fake_exec`), и
    без явной уборки каждый фильтр, поставленный `_build_main_window`/`main()`
    (мест вызова 15+: и через `_assemble`, и впрямую — `test_build_main_window_*`,
    `test_run_smoke_*`), оставался бы в цепочке `qapp` до конца сессии и получал
    нативные события ВСЕХ последующих тестов. Снимает реестр автоиспользуемая
    `_cleanup_fake_hotkey_filters` ниже — по всем местам создания разом, а не
    только по `_assemble`, где объект и так уже был на виду.
    """  # noqa: RUF002

    instances: ClassVar[list["_FakeHotkey"]] = []

    def __init__(self, callback: Any, **_kwargs: Any) -> None:
        super().__init__()
        self.callback = callback
        self.registered = False
        self.disposed = False
        self.rebind_calls: list[Any] = []
        _FakeHotkey.instances.append(self)

    def rebind(self, spec: Any) -> bool:
        self.rebind_calls.append(spec)
        self.registered = spec is not None
        return True

    def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:  # noqa: N802
        return False, 0

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture(autouse=True)
def _cleanup_fake_hotkey_filters(qapp: Any) -> Iterator[None]:
    """Снять с `qapp` все нативные фильтры `_FakeHotkey`, поставленные тестом.

    См. докстринг `_FakeHotkey.instances` выше: без этой уборки фильтр
    одного теста продолжает получать нативные события всех следующих
    (сессионный `qapp`, `aboutToQuit` в тестах не эмитируется) — так и
    падал несвязанный `test_watcher.py::test_atomic_replace_keeps_watching`.
    Teardown фикстуры pytest выполняется и при упавшем теле теста — в
    отличие от кода после `yield` внутри самого тела `_assemble`, поэтому
    уборка стоит здесь, а не там.
    """  # noqa: RUF002
    yield
    for hotkey in _FakeHotkey.instances:
        qapp.removeNativeEventFilter(hotkey)
    _FakeHotkey.instances.clear()


class _FakeStartupTasks(QObject):
    """Двойник `StartupTasks`: настоящий поднимает поток-демон, обнаруживающий
    платформы на реальной машине и читающий общие списки по сети — недопустимо
    в модульном тесте (и опасно: `_assemble` разбирает дерево виджетов вручную
    сразу после `main()`, см. `window.close()`/`deleteLater()` ниже, а
    настоящий поток может пережить эту разборку и обратиться к уже
    уничтоженному `tasks`/`window`). Сигналы настоящие — та же причина, что
    у `_StyleHintsStub`: `_build_main_window` подключает к ним обработчики
    через `.connect()`, и подделка без реального `Signal` там же и упала бы.
    Саму проводку сигнал → Workspace/BasesView проверяет отдельный тест,
    `test_build_main_window_wires_background_results`, который зовёт
    `_build_main_window` напрямую и эмитирует их руками — здесь важен только
    факт вызова `start()`.
    """  # noqa: RUF002

    installations_ready = Signal(object)  # list[Installation]
    common_lists_ready = Signal(object)  # CommonListData

    def __init__(
        self, discover: Any, read_common: Any, *, parent: Any = None, **_kwargs: Any
    ) -> None:
        super().__init__(parent)
        self.discover = discover
        self.read_common = read_common
        self.started = False

    def start(self) -> None:
        self.started = True


@dataclass
class _Assembly:
    code: int
    view: _RecordingView
    controller: ThemeController
    window: _RecordingWindow
    watcher: FileWatcher
    workspace: Any
    launch_calls: list[Any]
    tray_args: dict[str, Any]
    hotkey: _FakeHotkey
    hints: _StyleHintsStub
    tray: _FakeTray | None
    stylesheets_before_controller: list[str]
    tasks: _FakeStartupTasks


def _assemble(
    monkeypatch: Any,
    qapp: Any,
    workspace_factory: Any,
    tmp_path: Any,
    tray: _FakeTray | None,
) -> Iterator[_Assembly]:
    """Собрать приложение настоящим `main()` и отдать его части тесту.

    `tray` — то, что вернёт подменённая `create_tray`: `None` (трея
    в системе нет) или двойник. Две ветки, а не одна: признак
    `window.close_to_tray` вычисляется именно из этого результата.
    """  # noqa: RUF002
    workspace, launch_calls, _opened = workspace_factory()
    runtime = app_module.Runtime(
        workspace=workspace,
        cfg_rules=[],
        conventions=[],
        settings=tmp_path / "settings.json",
    )
    monkeypatch.setattr(app_module, "build_runtime", lambda env: runtime)

    captured: dict[str, Any] = {}

    class _CapturingController(ThemeController):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            # Снимок ДО `super()`: `ThemeController.__init__` сам зовёт
            # `application.setStyleSheet` (`_apply`), и после него вызов
            # из `main()` от вызова контроллера уже не отличить.
            captured["stylesheets_before_controller"] = list(stylesheets)
            super().__init__(*args, **kwargs)
            captured["controller"] = self

    class _CapturingView(_RecordingView):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured["view"] = self

    class _CapturingWindow(_RecordingWindow):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured["window"] = self
            captured["shown"] = []

        def show(self) -> None:
            captured["shown"].append(1)
            super().show()

    class _CapturingWatcher(FileWatcher):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured["watcher"] = self

    def fake_create_tray(
        window: Any, favorites: Any, on_launch: Any, on_quit: Any, **kwargs: Any
    ) -> _FakeTray | None:
        captured["tray_args"] = {
            "window": window, "favorites": favorites,
            "on_launch": on_launch, "on_quit": on_quit, **kwargs,
        }
        return tray

    def fake_hotkey(callback: Any, **kwargs: Any) -> _FakeHotkey:
        hotkey = _FakeHotkey(callback, **kwargs)
        captured["hotkey"] = hotkey
        return hotkey

    def fake_startup_tasks(
        discover: Any, read_common: Any, **kwargs: Any
    ) -> _FakeStartupTasks:
        tasks = _FakeStartupTasks(discover, read_common, **kwargs)
        captured["tasks"] = tasks
        return tasks

    monkeypatch.setattr(app_module, "ThemeController", _CapturingController)
    monkeypatch.setattr(app_module, "BasesView", _CapturingView)
    monkeypatch.setattr(app_module, "MainWindow", _CapturingWindow)
    monkeypatch.setattr(app_module, "FileWatcher", _CapturingWatcher)
    monkeypatch.setattr(app_module, "create_tray", fake_create_tray)
    monkeypatch.setattr(app_module, "GlobalHotkey", fake_hotkey)
    monkeypatch.setattr(app_module, "StartupTasks", fake_startup_tasks)
    # QApplication уже создан фикстурой qtbot; второй экземпляр PySide6
    # создать не даёт — main() получает живой.
    monkeypatch.setattr(app_module, "QApplication", lambda argv: qapp)
    hints = _StyleHintsStub()

    class _GuiApplicationStub:
        @staticmethod
        def styleHints() -> _StyleHintsStub:  # noqa: N802
            return hints

    monkeypatch.setattr(app_module, "QGuiApplication", _GuiApplicationStub)
    exec_calls: list[int] = []

    def fake_exec() -> int:
        exec_calls.append(1)
        return 0

    monkeypatch.setattr(qapp, "exec", fake_exec)

    # Таблица стилей записывается, а не ставится по-настоящему. Она у  # noqa: RUF003
    # `QApplication` одна на весь прогон, и её применение поверх дерева
    # виджетов, которое тут же уничтожается, оставляло в кэшах Qt
    # (`QStyleSheetStyle`) следы, из-за которых СЛЕДУЮЩИЙ чужой
    # `setStyleSheet` падал access violation примерно на половине прогонов.
    # Само применение таблицы — не предмет этого файла: оно покрыто
    # тестами `ThemeController`; здесь проверяется только факт вызова.
    stylesheets: list[str] = []
    monkeypatch.setattr(qapp, "setStyleSheet", stylesheets.append)

    name_before = qapp.applicationName()
    try:
        code = app_module.main([])
    finally:
        qapp.setApplicationName(name_before)
    assert exec_calls == [1], "main() обязан дойти до цикла событий"

    assert captured["shown"] == [1], "main() обязан показать окно"
    window = captured["window"]
    controller = captured["controller"]
    yield _Assembly(
        code=code,
        view=captured["view"],
        controller=controller,
        window=window,
        watcher=captured["watcher"],
        workspace=workspace,
        launch_calls=launch_calls,
        tray_args=captured["tray_args"],
        hotkey=captured["hotkey"],
        hints=hints,
        tray=tray,
        stylesheets_before_controller=captured["stylesheets_before_controller"],
        tasks=captured["tasks"],
    )
    # Разбирается вручную и до конца, а не через `qtbot.addWidget`: тот  # noqa: RUF003
    # откладывает удаление до `deleteLater`, то есть до произвольного
    # момента, когда очередь событий раскрутит чужой тест. Собранное здесь
    # приложение — единственное место набора, где за один вызов возникает
    # целое дерево виджетов вместе с `QFileSystemWatcher` и объектом  # noqa: RUF003
    # приложения-родителя; отложенный разбор такого дерева давал плавающий
    # access violation внутри чужого `QApplication.setStyleSheet`.
    # `sendPostedEvents(DeferredDelete)` обязателен: `processEvents()` сам
    # по себе события отложенного удаления не разбирает.  # noqa: RUF003
    window.close()
    window.deleteLater()
    controller.setParent(None)
    controller.deleteLater()
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def assembled(
    monkeypatch: Any, qapp: Any, workspace_factory: Any, tmp_path: Any
) -> Iterator[_Assembly]:
    yield from _assemble(monkeypatch, qapp, workspace_factory, tmp_path, None)


@pytest.fixture
def assembled_with_tray(
    monkeypatch: Any, qapp: Any, workspace_factory: Any, tmp_path: Any
) -> Iterator[_Assembly]:
    yield from _assemble(monkeypatch, qapp, workspace_factory, tmp_path, _FakeTray())


def test_main_returns_the_event_loop_code(assembled: _Assembly) -> None:
    assert assembled.code == 0


def test_main_starts_the_background_tasks(assembled: _Assembly) -> None:
    """main() обязан звать tasks.start() после показа окна (спека T-04.6, §3.2).

    `_build_main_window` сама `start()` не вызывает (иначе окно ждало бы
    готовности обнаружения платформ, ровно то, от чего задача уходит) —
    вызов обязан остаться в `main()`, и без сторожа его потеря осталась бы
    незамеченной: приложение всё равно показало бы окно и не упало, просто
    колонка версии молчала бы «…» вечно.
    """  # noqa: RUF002
    assert assembled.tasks.started is True


def test_main_repaints_the_bases_view_on_theme_change(assembled: _Assembly) -> None:
    """Второе из двух обязательных действий смены темы (спека §2.4).

    Первое (`application.setStyleSheet`) делает сам контроллер и оно покрыто
    его тестами. Второе — `view.apply_palette` — живёт только здесь, в проводке
    `controller.changed → on_theme_changed`, и без него `QBrush` строк и значки
    размещения остались бы в цветах прежней палитры.
    """  # noqa: RUF002
    assembled.view.palettes.clear()

    assembled.controller.set_mode(ThemeMode.LIGHT)

    assert assembled.controller.palette is theme.LIGHT
    assert assembled.view.palettes == [theme.LIGHT]


def test_main_repaints_the_window_rail_on_theme_change(assembled: _Assembly) -> None:
    """Третье действие смены темы (задача 2 рестайла, `ui/app.py`).

    `view.apply_palette` перекрашивает список баз, `application.setStyleSheet`
    красит остальное — но значки рельсы (`rail_icons`) запечены в пиксмапы
    так же, как значки размещения, и требуют собственного
    `window.apply_palette(controller.palette)` в `on_theme_changed`. Ре-ревью
    задачи 2: удаление этой строки не роняло ни один тест набора — эта
    проверка ловит именно её.
    """  # noqa: RUF002
    assembled.window.palettes.clear()

    assembled.controller.set_mode(ThemeMode.LIGHT)

    assert assembled.controller.palette is theme.LIGHT
    assert assembled.window.palettes == [theme.LIGHT]


def test_main_follows_the_system_theme(assembled: _Assembly) -> None:
    """Режим «Авто» обязан отзываться на смену системной темы на лету.

    Проводка `styleHints().colorSchemeChanged → controller.refresh_system`
    живёт только в `main()`; без неё «Авто» применялась бы один раз при
    старте, и спека §2.4 («вариант „применится после перезапуска“
    отклонён») исполнялась бы наполовину.
    """
    assert assembled.controller.mode is ThemeMode.AUTO
    assembled.view.palettes.clear()

    assembled.hints.colorSchemeChanged.emit(0)

    assert assembled.view.palettes == [assembled.controller.palette]


def test_main_starts_the_view_with_the_saved_palette(assembled: _Assembly) -> None:
    """Палитра доходит до `BasesView` уже при сборке, а не только при смене.

    Без этого первый показ шёл бы в тёмной палитре независимо от настройки,
    и светлая тема появлялась бы только после ручного переключения.
    """  # noqa: RUF002
    assert assembled.view._palette is assembled.controller.palette


def test_main_rebuilds_the_view_when_the_file_changes(assembled: _Assembly) -> None:
    """Проводка watcher → `reload_if_changed` → `rebuild`, а не только сам watcher.

    `FileWatcher` покрыт своим набором (`test_watcher.py`), но соединяющая
    строка `watcher.changed.connect(on_file_changed)` — нет: внешняя правка
    списка не доезжала бы до экрана, а обнаружилось бы это только руками.
    """  # noqa: RUF002
    path = assembled.workspace.paths.ibases
    path.write_bytes(path.read_bytes() + '[Извне]\r\nConnect=File="C:\\X";\r\n'.encode())

    assembled.watcher.changed.emit()

    labels = [
        assembled.view.model().item(row, 0).text()
        for row in range(assembled.view.model().rowCount())
    ]
    assert "Извне" in labels


def test_main_gives_the_tray_only_favorite_bases(assembled: _Assembly) -> None:
    """Замыкание `favorites()` — тоже проводка: трей не должен видеть группы."""
    key = "id:44444444-4444-4444-4444-444444444444"
    assembled.workspace.set_favorite(key, True)

    favorites = assembled.tray_args["favorites"]()

    assert [item.key for item in favorites] == [key]


def test_main_gives_the_tray_the_real_launcher(assembled: _Assembly) -> None:
    """Пункт избранного в трее запускает базу через ту же `BasesView.launch_key`."""
    assembled.tray_args["on_launch"]("id:44444444-4444-4444-4444-444444444444")

    assert len(assembled.launch_calls) == 1


def test_main_disposes_the_hotkey_on_quit(assembled: _Assembly, qapp: Any) -> None:
    """`RegisterHotKey` без парного `UnregisterHotKey` держит сочетание до

    перезагрузки — отвязка обязана быть подключена к `aboutToQuit`.

    Проверяется отключением, а не эмиссией: `aboutToQuit` у живого
    `QApplication` — сигнал общего пользования, и его настоящая эмиссия
    посреди прогона дёргает чужие обработчики завершения (наблюдался
    аварийный выход процесса в следующем же тесте, внутри `setStyleSheet`).
    `disconnect` отвечает на тот же вопрос — подписка есть или нет —
    и заодно убирает её за собой.
    """  # noqa: RUF002
    disconnected = qapp.aboutToQuit.disconnect(assembled.hotkey.dispose)

    assert disconnected is True


def test_main_dresses_the_application_before_the_controller_exists(
    assembled: _Assembly,
) -> None:
    """`setStyleSheet` в `main()` обязателен, и его нельзя доказать «потом».

    Ре-ревью, N1: прежняя проверка смотрела на `stylesheets[0]` уже после
    возврата `main()` — и удаление строки `application.setStyleSheet(...)`
    из `ui/app.py` оставляло **993 passed**. `ThemeController.__init__`
    зовёт `setStyleSheet` сам, режим по умолчанию `AUTO` на этой машине
    разрешается в `DARK`, и первый элемент списка совпадал с ожидаемым
    без строки в продукте вовсе.

    Строка в продукте нужна не ради красоты: `QMessageBox.critical`
    при отказе `build_runtime` (`ui/app.py`, ветки `UserDataUnavailableError`
    и `OSError`) показывается **до** создания контроллера — без неё
    единственное окно, которое пользователь в этом сценарии увидит,
    пришло бы нестилизованным.

    Поэтому снимок берётся в момент конструирования контроллера, до его
    `super().__init__`: там видно ровно то, что успел сделать `main()` сам.
    """  # noqa: RUF002
    assert assembled.stylesheets_before_controller == [theme.stylesheet(theme.DARK)]


def test_main_hides_the_window_into_a_live_tray(assembled_with_tray: _Assembly) -> None:
    """Трей есть — закрытие окна прячет приложение, а не закрывает.

    Ре-ревью, N2: проверка ниже утверждала `close_to_tray is False` —
    значение, которое ставит конструктор `MainWindow`, при `create_tray`,
    возвращающей `None`. Мутация `window.close_to_tray = False` не роняла
    ничего, и ветка «трей есть», ради которой признак и существует,
    не была покрыта нигде.
    """  # noqa: RUF002
    assert assembled_with_tray.window.close_to_tray is True


def test_main_sets_the_combination_tooltip_on_success(assembled_with_tray: _Assembly) -> None:
    """Тултип трея на успешной регистрации несёт сочетание (спека §4.3).

    Task 6 ставила здесь фиксированный «OneCStarter» — тултип, различающий
    успех/занятость/выключено, был предметом Task 9. `_FakeHotkey.rebind`
    хардкоженно отдаёт `True` (см. её докстринг), поэтому через полный
    `main()` здесь проверяется именно ветка успеха; занятое и выключенное
    сочетание — предмет `test_busy_hotkey_shows_balloon_and_tooltip` и
    `test_disabled_hotkey_sets_the_plain_tooltip` (`_window_with_settings`,
    настоящий `GlobalHotkey.rebind` с инжектированным `register`) — там
    результат правда управляет исходом, а не хардкоженное поле подделки
    (долг Task 9, п. 2).
    """  # noqa: RUF002
    assert assembled_with_tray.tray is not None
    assert assembled_with_tray.tray.tooltips == [f"OneCStarter — {DEFAULT_HOTKEY}"]


def test_main_rebinds_the_hotkey_from_settings(assembled: _Assembly) -> None:
    """`_build_main_window` больше не полагается на регистрацию в конструкторе.

    `rebind` обязан быть вызван ровно один раз, значением из настроек
    (дефолт — `DEFAULT_HOTKEY`, тестовый `Runtime` указывает на несуществующий
    `settings.json`, поэтому `SettingsStore` отдаёт значения по умолчанию).
    """
    assert assembled.hotkey.rebind_calls == [parse_hotkey(DEFAULT_HOTKEY)]


def test_main_does_not_hide_the_window_into_a_missing_tray(assembled: _Assembly) -> None:
    """Трея нет — закрытие окна закрывает приложение, а не прячет его в никуда."""  # noqa: RUF002
    assert assembled.window.close_to_tray is False


# -- _build_main_window напрямую: сборка окна отдельно от main() (T-04.6) ----
#
# Ниже — не через `main()`/`_assemble`: `_build_main_window` тестируется
# как самостоятельная единица, без QApplication-подмен, без create_tray/
# GlobalHotkey-моков, кроме одного (GlobalHotkey — настоящий зовёт
# RegisterHotKey у Windows, регистрировать реальное системное сочетание  # noqa: RUF003
# ради этих тестов незачем и небезопасно). create_tray не подменяется:
# под offscreen-платформой QSystemTrayIcon.isSystemTrayAvailable() честно
# возвращает False, и настоящий create_tray сам отдаёт None — подменять
# нечего.


def _version_column_texts(view: BasesView) -> list[str]:
    """Текст колонки «Версия» верхнего уровня дерева — без обхода вглубь.

    Достаточно для фикстуры этого файла (один базовый элемент в корне,
    без групп и без Недавних/Избранного — они не показываются пустыми,
    display_forest): вложенный обход, как у `_column_texts` в
    test_bases_view.py, здесь не нужен.
    """  # noqa: RUF002
    model = view.model()
    return [str(model.index(row, 1).data() or "") for row in range(model.rowCount())]


def test_build_main_window_wires_background_results(
    qtbot: Any, monkeypatch: Any, qapp: Any, tmp_path: Any
) -> None:
    """Спека T-04.6, §3.3: результат фона обязан дойти и до Workspace, и до BasesView.

    `tasks.start()` не вызывается — сигналы эмитируются вручную: реальный
    фоновый поток тут не нужен, только проводка installations_ready/
    common_lists_ready → Workspace.set_installations/apply_common_lists →
    BasesView.apply_installations/rebuild, которую строит `_build_main_window`.
    `runtime` собран настоящим `build_runtime` над файлом с одной записью —
    пустой список ничего не показал бы в колонке версии, и проверка
    «эллипсис исчез» осталась бы бессмысленной. Workspace на входе честно
    pending по обоим полям (build_runtime больше не обнаруживает платформы
    и не читает общие списки сам).

    Круг правок 1: проверка одних лишь `installations_pending`/
    `common_lists_pending` не отличила бы рабочую проводку от сломанной —
    `Workspace.set_installations`/`apply_common_lists` их снимают
    независимо от того, позвал ли обработчик `view.apply_installations`/
    `view.rebuild()`. Колонка версии в самом BasesView — единственное,
    что действительно доказывает, что результат фона дошёл до экрана.
    """  # noqa: RUF002
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    start = tmp_path / "1C" / "1CEStart"
    start.mkdir(parents=True)
    (start / "ibases.v8i").write_bytes('[Демо]\r\nConnect=File="C:\\Demo";\r\n'.encode())
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)
    assert runtime.workspace.installations_pending
    assert runtime.workspace.common_lists_pending

    window, tasks = _build_main_window(qapp, runtime, env)
    qtbot.addWidget(window)
    view = window.current_section()
    assert isinstance(view, BasesView)
    assert _version_column_texts(view) == ["…"]

    tasks.installations_ready.emit(INSTALLED)
    tasks.common_lists_ready.emit(EMPTY_COMMON_DATA)

    assert not runtime.workspace.installations_pending
    assert not runtime.workspace.common_lists_pending
    assert "…" not in _version_column_texts(view)


def test_build_main_window_sets_the_application_icon(
    qtbot: Any, monkeypatch: Any, qapp: Any, tmp_path: Any
) -> None:
    """Заголовок окна и Alt-Tab получают фирменный значок (замечание заказчика 16.08.2026).

    До этой задачи `application.setWindowIcon` не вызывался нигде в продукте —
    Windows подставляла заголовку что-то своё, отличное и от `.ico` панели
    задач, и от значка трея (три разных значка на одном скриншоте, находка
    заказчика на контрольной точке). `_build_main_window` ставит значок на
    `QApplication`, а не только на `MainWindow`: у окна нет собственной
    иконки, оно наследует иконку приложения, и именно `application.windowIcon()`
    доказывает, что вызов действительно произошёл — проверка на самом окне
    прошла бы и без строки в продукте.
    """  # noqa: RUF002
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)

    window, _tasks = _build_main_window(qapp, runtime, env)
    qtbot.addWidget(window)

    assert qapp.windowIcon().availableSizes()


def test_startup_log_has_no_connect_strings(
    qtbot: Any, caplog: Any, monkeypatch: Any, qapp: Any, workspace_factory: Any, tmp_path: Any
) -> None:
    """Сторож инварианта 5 на фазовые сообщения сборки окна (МУТАЦИЯ).

    Фикстура несёт настоящие Srvr=/File= (workspace_factory → anonymized.v8i,
    tests/fixtures) — форму, в которой Connect реально встречается в файле
    списка баз, а не выдуманную для теста строку. `_build_main_window` сейчас
    сама ничего не логирует — сторож стоит на будущее: попадёт лог с
    содержимым записи в код сборки окна (саму функцию или то, что она
    вызывает — BasesView, Workspace), эта проверка обязана покраснеть.
    """  # noqa: RUF002
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    workspace, _calls, _opened = workspace_factory()
    runtime = app_module.Runtime(
        workspace=workspace, cfg_rules=[], conventions=[], settings=tmp_path / "settings.json"
    )

    with caplog.at_level(logging.INFO):
        window, _tasks = _build_main_window(qapp, runtime, {"APPDATA": str(tmp_path)})
        window.show()
    qtbot.addWidget(window)

    assert "Srvr" not in caplog.text
    assert "File=" not in caplog.text


def test_build_main_window_installs_the_hotkey_native_filter(
    qtbot: Any, monkeypatch: Any, qapp: Any, tmp_path: Any
) -> None:
    """`application.installNativeEventFilter(hotkey)` — без него WM_HOTKEY

    никогда не дойдёт до `GlobalHotkey.nativeEventFilter` (спека §4.2).

    Долг Task 9, п. 3: эта строка проводки не была покрыта ни одним тестом
    ни до вехи (когда регистрация стояла в конструкторе `GlobalHotkey` и
    фильтр ставился условно), ни в Task 6 (фильтр стал безусловным, но
    сам факт установки так и остался непроверенным). `_FakeHotkey`
    подходит: `installNativeEventFilter` у PySide6 отказывает объекту, не
    унаследованному от `QAbstractNativeEventFilter`, а нам важен только
    факт вызова с верным объектом — не настоящая доставка сообщений.
    """  # noqa: RUF002
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    installed: list[Any] = []

    def spy(self: Any, event_filter: Any) -> None:
        installed.append(event_filter)

    monkeypatch.setattr(QApplication, "installNativeEventFilter", spy)
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)

    window, _tasks = _build_main_window(qapp, runtime, env)
    qtbot.addWidget(window)

    assert installed == [window.global_hotkey]


# -- задача 9: проводка настроек — close_to_tray, хоткей, тихий старт --------
#
# Ниже — сборка окна поверх настоящих `GlobalHotkey`/`SettingsStore` и
# настоящего (но недоступного под offscreen без подмены) `QSystemTrayIcon`:
# `register`/`unregister` инжектированы в `GlobalHotkey` — настоящий
# `RegisterHotKey` в тестах не звучит ни разу (CLAUDE.md, «настоящий
# RegisterHotKey в тестах не звать»). Ровно поэтому `rebind()` здесь
# отдаёт то, что задал тест (через `register_result`), а не хардкоженное  # noqa: RUF003
# поле подделки — находка ревью Task 6, долг Task 9 п. 2.


def _settings_path(tmp_path: Path) -> Path:
    """Куда смотрит build_runtime при APPDATA=tmp_path (см. ui/app.py)."""
    return tmp_path / "OneCStarter" / "settings.json"


def _window_with_settings(
    qapp: Any,
    tmp_path: Any,
    monkeypatch: Any,
    *,
    tray_available: bool,
    register_result: int = 1,
    registrations: list[Any] | None = None,
    messages: list[Any] | None = None,
    tooltips: list[Any] | None = None,
) -> Any:
    """Собрать окно поверх подменённых трея и user32.

    Настоящая регистрация хоткея и настоящий трей в offscreen-тесте
    недопустимы: первая отобрала бы сочетание у машины разработчика,
    второй недоступен под offscreen-платформой.

    Возврат не аннотирован `MainWindow` нарочно: `settings_store` и
    `global_hotkey` объявлены в `shell.py` как `object | None` (окну не
    положено знать их настоящий тип, только владеть временем жизни), и
    строгий mypy отказал бы в доступе к `.update`/`.registered` ниже —
    тем же полям, которыми пользуются тесты этого блока.
    """  # noqa: RUF002
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: tray_available)
    )
    if messages is not None:
        monkeypatch.setattr(
            QSystemTrayIcon,
            "showMessage",
            lambda self, title, text, *args: messages.append((title, text)),
        )
    if tooltips is not None:
        monkeypatch.setattr(
            QSystemTrayIcon,
            "setToolTip",
            lambda self, text: tooltips.append(text),
        )

    def register(hwnd: Any, hotkey_id: Any, modifiers: Any, vk: Any) -> int:
        if registrations is not None:
            registrations.append((modifiers, vk))
        return register_result

    monkeypatch.setattr(
        "onecstarter.ui.app.GlobalHotkey",
        lambda callback: GlobalHotkey(
            callback, register=register, unregister=lambda hwnd, hotkey_id: 1
        ),
    )
    env = {"APPDATA": str(tmp_path)}
    runtime = build_runtime(env)
    window, _tasks = _build_main_window(qapp, runtime, env)
    return window


def test_close_to_tray_follows_the_setting(qapp: Any, tmp_path: Any, monkeypatch: Any) -> None:
    """Настройка выключена — крестик завершает программу (спека §2)."""
    save_settings(_settings_path(tmp_path), Settings(close_to_tray=False))
    window = _window_with_settings(qapp, tmp_path, monkeypatch, tray_available=True)
    assert window.close_to_tray is False


def test_close_to_tray_requires_available_tray(
    qapp: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Трея нет — настройка ведёт себя как выключенная (спека §2)."""
    save_settings(_settings_path(tmp_path), Settings(close_to_tray=True))
    window = _window_with_settings(qapp, tmp_path, monkeypatch, tray_available=False)
    assert window.close_to_tray is False


def test_close_to_tray_updates_without_restart(qapp: Any, tmp_path: Any, monkeypatch: Any) -> None:
    window = _window_with_settings(qapp, tmp_path, monkeypatch, tray_available=True)
    assert window.close_to_tray is True

    window.settings_store.update(close_to_tray=False)

    assert window.close_to_tray is False


def test_disabled_hotkey_is_not_registered(qapp: Any, tmp_path: Any, monkeypatch: Any) -> None:
    """Защитный: пустое сочетание — регистрации нет (спека §4.1).

    Мутация: в проводке звать rebind всегда с дефолтным сочетанием —
    тест обязан упасть на непустом списке регистраций.
    """  # noqa: RUF002
    save_settings(_settings_path(tmp_path), Settings(hotkey=""))
    registered: list[tuple[int, int]] = []
    window = _window_with_settings(
        qapp, tmp_path, monkeypatch, tray_available=True, registrations=registered
    )
    assert registered == []
    assert window.global_hotkey.registered is False


def test_disabled_hotkey_sets_the_plain_tooltip(qapp: Any, tmp_path: Any, monkeypatch: Any) -> None:
    """Выключенное сочетание — тултип без сочетания, без балуна (спека §4.3).

    Долг Task 9, п. 1: третий из трёх исходов rebind, которого не было
    ни разу — до вехи хоткей нельзя было выключить вовсе.
    """
    save_settings(_settings_path(tmp_path), Settings(hotkey=""))
    tooltips: list[str] = []
    messages: list[tuple[str, str]] = []
    _window_with_settings(
        qapp,
        tmp_path,
        monkeypatch,
        tray_available=True,
        tooltips=tooltips,
        messages=messages,
    )
    assert tooltips[-1] == "OneCStarter"
    assert messages == []


def test_success_hotkey_sets_the_combination_tooltip(
    qapp: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Успешная регистрация на старте — тултип с сочетанием, без балуна (спека §4.3)."""  # noqa: RUF002
    tooltips: list[str] = []
    messages: list[tuple[str, str]] = []
    _window_with_settings(
        qapp,
        tmp_path,
        monkeypatch,
        tray_available=True,
        tooltips=tooltips,
        messages=messages,
    )
    assert tooltips[-1] == f"OneCStarter — {DEFAULT_HOTKEY}"
    assert messages == []


def test_busy_hotkey_shows_balloon_and_tooltip(qapp: Any, tmp_path: Any, monkeypatch: Any) -> None:
    """Занято на старте — балун, а не тишина (спека §4.3)."""  # noqa: RUF002
    messages: list[tuple[str, str]] = []
    tooltips: list[str] = []
    window = _window_with_settings(
        qapp,
        tmp_path,
        monkeypatch,
        tray_available=True,
        register_result=0,
        messages=messages,
        tooltips=tooltips,
    )
    assert messages, "балун при занятом сочетании обязателен"
    assert "занят" in messages[0][1]
    assert "занято" in tooltips[-1]
    assert window.global_hotkey.registered is False


# -- задача 8: режим самопроверки (--smoke) ----------------------------------
#
# `run_smoke` собирает настоящее окно через `_build_main_window` и не отдаёт
# его наружу (сигнатура — только `int`), поэтому тесты перехватывают окно  # noqa: RUF003
# подменой `app_module._build_main_window` — тонкой обёрткой вокруг
# настоящей функции — только ради `qtbot.addWidget`, а не ради подмены  # noqa: RUF003
# поведения. `GlobalHotkey` подменяется на `_FakeHotkey` по тому же поводу,
# что у прямых тестов `_build_main_window` выше: настоящий регистрирует  # noqa: RUF003
# системное сочетание, а два новых теста добавили бы ещё одну живую  # noqa: RUF003
# регистрацию на сессию тестов без всякой пользы для проверки.


def _capture_window(monkeypatch: Any) -> dict[str, Any]:
    """Дать тесту ссылку на окно, которое соберёт `run_smoke` изнутри."""
    captured: dict[str, Any] = {}
    real_build = app_module._build_main_window

    def capturing(application: Any, runtime: Any, env: Any) -> Any:
        window, tasks = real_build(application, runtime, env)
        captured["window"] = window
        return window, tasks

    monkeypatch.setattr(app_module, "_build_main_window", capturing)
    return captured


def test_run_smoke_writes_shortcut_and_reports_zero(
    tmp_path: Any, monkeypatch: Any, qtbot: Any
) -> None:
    """Успешная самопроверка: код 0, окно показано, `smoke.lnk` записан.

    Окружение — только `APPDATA` на пустой каталог (обнаружение платформ
    и общие списки мгновенны на пустом окружении, спека §5 задачи 8):
    ни `ibases.v8i`, ни `1cestart.cfg` не создаются — build_runtime
    и без них честно собирает пустой pending-Workspace.
    """
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    captured = _capture_window(monkeypatch)
    appdata = tmp_path / "appdata"
    target = tmp_path / "out"
    target.mkdir()

    assert run_smoke(str(target), {"APPDATA": str(appdata)}) == 0

    assert (target / "smoke.lnk").exists()
    qtbot.addWidget(captured["window"])


def test_run_smoke_times_out_without_background(
    tmp_path: Any, monkeypatch: Any, qtbot: Any
) -> None:
    """Молчащий фон — код 1 за отведённое время, ярлык не пишется.

    `make_tasks` подменяет `StartupTasks` на версию с `spawn`, который
    ничего не запускает: ни один сигнал не приходит, и `run_smoke` обязан
    остановиться по `timeout_ms`, а не повиснуть до конца прогона тестов.
    Без этого сторожа отказ фона (сборка потеряла зависимость обнаружения,
    поток падает молча до эмиссии сигнала) завис бы в `loop.exec()` навсегда
    вместо кода 1.
    """  # noqa: RUF002
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    captured = _capture_window(monkeypatch)
    appdata = tmp_path / "appdata"
    target = tmp_path / "out"
    target.mkdir()

    def make_tasks() -> StartupTasks:
        return StartupTasks(
            lambda: INSTALLED,
            lambda: EMPTY_COMMON_DATA,
            spawn=lambda task: None,
        )

    code = run_smoke(
        str(target), {"APPDATA": str(appdata)}, timeout_ms=100, make_tasks=make_tasks
    )

    assert code == 1
    assert not (target / "smoke.lnk").exists()
    qtbot.addWidget(captured["window"])
