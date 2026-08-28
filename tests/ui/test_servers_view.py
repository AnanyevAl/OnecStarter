"""Раздел «Серверы»: список профилей и чужие серверы (T-08, задача 14).

Воркспейс — настоящий `ServersWorkspace` на `tmp_path` с локальными фейками
`FakeControl`/`FakeSpawn` (тот же приём, что и в `tests/unit/test_servers.py`,
но не импортируется оттуда — там классы модульные, а не для переиспользования
извне, и раздувать связь между unit- и ui-наборами незачем). Снимок процессов
кладётся напрямую через `ServersWorkspace.apply_scan(ScanSnapshot(...))` —
конструировать `ProcessScanner` ради одного снимка в каждом тесте избыточно,
сама функция `scan_servers` уже покрыта юнит-тестами.

Задача 5 (T-10) добавляет выделение карточки и панель «Журнал профиля»:
`FakeSpawn`/`_workspace` уже несут `logs_dir` (миграция задачи 4) —
переиспользуются как есть, отдельного фейка для журнала не нужно, тесты
читают реальный файл, который пишет `ServersWorkspace.log_event`/`start`.
Клик — `qtbot.mouseRelease(view.profile_card(index), Qt.MouseButton.LeftButton)`
по образцу брифа: событие уходит напрямую в виджет карточки, а не по
экранным координатам, так что перекрытие карточки дочерними QLabel
(`WA_TransparentForMouseEvents`, см. `view.py`) тесту не мешает.
"""  # noqa: RUF002

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import ServerProfile
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.process_control import ProcessMismatchError
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.services.servers import ScanSnapshot, ServersWorkspace
from onecstarter.ui import theme
from onecstarter.ui.servers.dialog import ServerProfileDialog
from onecstarter.ui.servers.view import ServersView

RAGENT = r"C:\Program Files\1cv8\8.3.25.1633\bin\ragent.exe"
FOREIGN_RAGENT = r"C:\Program Files\1cv8\8.3.22.1923\bin\ragent.exe"


@dataclass
class FakeControl:
    """`ProcessControl` с детьми по словарю и журналом вызовов (см. `test_servers.py`)."""  # noqa: RUF002

    children_map: dict[int, list[ProcessInfo]] = field(default_factory=dict)
    mismatched: frozenset[int] = field(default_factory=frozenset)
    calls: list[tuple[str, int]] = field(default_factory=list)

    def children(self, pid: int) -> list[ProcessInfo]:
        self.calls.append(("children", pid))
        return list(self.children_map.get(pid, []))

    def terminate(self, pid: int, expected_create_time: float) -> None:
        self.calls.append(("terminate", pid))
        if pid in self.mismatched:
            raise ProcessMismatchError(
                f"pid {pid}: create_time не совпадает с ожидаемым — PID переиспользован"  # noqa: RUF001
            )


@dataclass
class FakeSpawn:
    """`server_spawn` — сигнатура `Callable[[LaunchCommand, Path], int]` (T-10, задача 4)."""

    pid: int = 4242
    calls: list[LaunchCommand] = field(default_factory=list)

    def __call__(self, command: LaunchCommand, log_path: Path) -> int:
        self.calls.append(command)
        return self.pid


def _profile(**overrides: object) -> ServerProfile:
    values: dict[str, str | int | bool] = {
        "id": "p1",
        "name": "8.3.25 отладка",
        "version": "8.3.25",
        "port": 1540,
        "regport": 1541,
        "range_start": 1560,
        "range_end": 1591,
        "cluster_dir": r"E:\srv\srv_8.3.25.1633",
    }
    values.update(overrides)  # type: ignore[arg-type]
    return ServerProfile(**values)  # type: ignore[arg-type]


def _agent(
    pid: int,
    cluster_dir: str,
    *,
    port: int = 1540,
    regport: int = 1541,
    exe: str | None = RAGENT,
) -> ProcessInfo:
    argv = (
        "ragent.exe",
        "-d",
        cluster_dir,
        "-port",
        str(port),
        "-regport",
        str(regport),
    )
    return ProcessInfo(
        pid=pid,
        name="ragent.exe",
        executable=Path(exe) if exe else None,
        argv=argv,
        create_time=100.0 + pid,
    )


def _workspace(
    tmp_path: Path,
    profiles: tuple[ServerProfile, ...] = (),
    *,
    control: FakeControl | None = None,
    spawn: FakeSpawn | None = None,
    registered_radmin: object = None,
) -> ServersWorkspace:
    kwargs: dict[str, object] = {
        "control": control if control is not None else FakeControl(),
        "server_spawn": spawn if spawn is not None else FakeSpawn(),
        "logs_dir": tmp_path / "logs",
    }
    if registered_radmin is not None:
        kwargs["registered_radmin"] = registered_radmin
    workspace = ServersWorkspace(tmp_path / "servers.json", **kwargs)  # type: ignore[arg-type]
    for profile in profiles:
        workspace.add_profile(profile)
    return workspace


def _installation(version: str = "8.3.25.1633") -> ServerInstallation:
    root = Path(r"C:\Program Files\1cv8") / version
    return ServerInstallation(
        installation=Installation(parse_version(version), root, Arch.X64),
        ragent=root / "bin" / "ragent.exe",
        radmin=root / "bin" / "radmin.dll",
    )


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


# -- статусы карточки ---------------------------------------------------------


def test_running_profile_shows_stop_button(application: QApplication, tmp_path: Path) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.button_text == "Остановить"
    assert row.button_enabled is True
    assert "работает" in row.status_text
    assert "PID 100" in row.status_text


def test_running_status_uses_accent_colour(application: QApplication, tmp_path: Path) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    assert theme.DARK.accent in view.profile_status_label(0).styleSheet()


def test_stopped_profile_shows_start_button(application: QApplication, tmp_path: Path) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.button_text == "Запустить"
    assert row.button_enabled is True
    assert row.status_text == "остановлен"


def test_stopped_status_uses_dim_colour(application: QApplication, tmp_path: Path) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    assert theme.DARK.text_dim in view.profile_status_label(0).styleSheet()


def test_unresolved_version_disables_start_and_uses_problem_colour(
    application: QApplication, tmp_path: Path
) -> None:
    """Версия не установлена — «Запустить» неактивна, текст цвета problem (T-06: без зелёного)."""
    profile = _profile(version="8.5.1")
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.button_text == "Запустить"
    assert row.button_enabled is False
    assert row.status_text == "версия не установлена"
    assert theme.DARK.problem in view.profile_status_label(0).styleSheet()


def test_running_process_wins_over_unresolved_version(
    application: QApplication, tmp_path: Path
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ.

    IMPORTANT 3 финального ревью, правка спеки §3.1: раньше `resolved is
    None` проверялся первым и подавлял «работает» даже при живом совпавшем
    процессе — карточка показывала «версия не установлена» и блокировала
    «Остановить», хотя остановка версии не требует вовсе (`stop` работает
    по PID снимка, не по установке). Статус процессов обязан быть главнее
    разрешения версии — здесь версия не разрешается вовсе (`installed=[]`),
    но процесс живой.
    Мутация: вернуть проверку `resolved is None` в начало `_status_text`/
    `_button_state`/`_status_colour` — тест обязан упасть.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))

    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.status_text == "работает · PID 100"
    assert row.button_text == "Остановить"
    assert row.button_enabled is True
    assert theme.DARK.accent in view.profile_status_label(0).styleSheet()


def test_multiple_processes_disable_stop_with_explanation(
    application: QApplication, tmp_path: Path
) -> None:
    """Несколько процессов — все PID видны, остановка неактивна с подсказкой."""  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(
        ScanSnapshot(
            agents=(_agent(100, profile.cluster_dir), _agent(200, profile.cluster_dir)),
            managers=(),
        )
    )

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.button_text == "Остановить"
    assert row.button_enabled is False
    assert "PID 100" in row.status_text
    assert "PID 200" in row.status_text
    assert "не выбрать" in row.status_text


# -- слепое окно до первого скана (IMPORTANT 4b, финальное ревью) -----------


def test_card_is_blind_before_first_scan(application: QApplication, tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ.

    IMPORTANT 4b финального ревью, §4.4: до первого `apply_scan` состояние
    процессов профиля неизвестно — показывать «остановлен» было бы враньём
    (сервер мог уже работать), а активная «Запустить» рисковала бы породить
    второй ragent поверх уже живого, ещё не увиденного скана (§6.4: клик
    по работающему серверу до снимка не должен породить второй ragent).
    Карточка обязана показать «…» и держать кнопку неактивной, пока снимка
    нет вовсе (`workspace.scan_pending`).
    Мутация: убрать проверку `pending` в `ServersView._build_card` — тест
    обязан упасть (карточка покажет «остановлен»/активную «Запустить»).
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    assert workspace.scan_pending is True

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.status_text == "…"
    assert row.button_enabled is False
    assert "первый скан" in view.profile_button(0).toolTip().casefold()


def test_card_leaves_blind_state_after_first_scan(
    application: QApplication, tmp_path: Path
) -> None:
    """После первого `apply_scan` карточка возвращается к обычной логике статуса."""
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    row = view.profile_rows()[0]
    assert row.status_text == "остановлен"
    assert row.button_enabled is True


# -- ЗАЩИТНЫЙ: чужие серверы не несут кнопку остановки вовсе (решение 5) -----


def test_foreign_server_has_no_stop_button(application: QApplication, tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: у чужого сервера нет кнопки остановки вовсе (решение заказчика 5).

    Не «неактивна», а ОТСУТСТВУЕТ как виджет — блок «Другие серверы на
    машине» справочный, без кнопок. Мутация «нарисовать disabled кнопку
    вместо отсутствия» обязана уронить этот тест: `findChildren(QPushButton)`
    поймает и неактивную кнопку тоже, а `button_enabled` из `profile_rows()`
    сюда вообще не относится — у чужих серверов нет `profile_rows()`.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path, ())
    foreign = _agent(999, r"D:\clusters\prod", exe=FOREIGN_RAGENT)
    workspace.apply_scan(ScanSnapshot(agents=(foreign,), managers=()))

    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)

    assert len(view.foreign_rows()) == 1
    widget = view.foreign_row_widget(0)
    assert widget.findChildren(QPushButton) == []


def test_foreign_row_full_form_shows_version_ports_dir_pid(
    application: QApplication, tmp_path: Path
) -> None:
    workspace = _workspace(tmp_path, ())
    foreign = _agent(999, r"D:\clusters\prod", port=2040, regport=2041, exe=FOREIGN_RAGENT)
    workspace.apply_scan(ScanSnapshot(agents=(foreign,), managers=()))

    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)

    text = view.foreign_rows()[0]
    assert "8.3.22.1923" in text
    assert "2040" in text and "2041" in text
    assert r"D:\clusters\prod" in text
    assert "PID 999" in text


def test_foreign_row_limited_form_without_cmdline_access(
    application: QApplication, tmp_path: Path
) -> None:
    """Командная строка недоступна ([Ф] В1) — строка без портов и каталога, но с версией."""  # noqa: RUF002
    workspace = _workspace(tmp_path, ())
    opaque = ProcessInfo(
        pid=555,
        name="ragent.exe",
        executable=Path(FOREIGN_RAGENT),
        argv=None,
        create_time=100.0,
    )
    workspace.apply_scan(ScanSnapshot(agents=(opaque,), managers=()))

    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)

    text = view.foreign_rows()[0]
    assert "PID 555" in text
    assert "нет доступа" in text
    assert "порт" not in text.casefold()
    assert "8.3.22.1923" in text


def test_foreign_row_limited_form_without_executable_omits_version(
    application: QApplication, tmp_path: Path
) -> None:
    """Ни командной строки, ни пути исполняемого файла — версии показать нечем."""
    workspace = _workspace(tmp_path, ())
    opaque = ProcessInfo(pid=777, name="ragent.exe", executable=None, argv=None, create_time=1.0)
    workspace.apply_scan(ScanSnapshot(agents=(opaque,), managers=()))

    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)

    text = view.foreign_rows()[0]
    assert "PID 777" in text
    assert "нет доступа" in text


# -- удаление профиля (круг правок 1: контекстное меню карточки) ------------
#
# Решение контроллера (круг правок 1 ревью задачи 14): «Удалить» больше не
# кнопка карточки (эталон мокапа несёт ровно одну кнопку, паттерн проекта
# для разрушительных действий — контекстное меню, `BasesView._build_menu`).
# `profile_menu(index)` отдаёт собранный `QMenu` без показа — тем же
# приёмом, что `_build_menu` в `BasesView`: тесты зовут действие через
# `QAction.trigger()`, а не через прямой вызов приватного `_remove` и не  # noqa: RUF003
# через блокирующий `QMenu.exec()`.


def _trigger_delete(view: ServersView, index: int) -> None:
    """«Удалить профиль…» из контекстного меню карточки — тестовый аксессор.

    `QAction.trigger()` эмитит `triggered` синхронно и зовёт подключённый
    слот без показа настоящего меню — офскрин-тест не должен открывать
    `QMenu.exec()`, он блокирует.
    """
    menu = view.profile_menu(index)
    action = next(a for a in menu.actions() if "Удалить" in a.text())
    action.trigger()


def _trigger_properties(view: ServersView, index: int) -> None:
    """«Свойства…» из контекстного меню карточки (задача 15) — тот же приём."""
    menu = view.profile_menu(index)
    action = next(a for a in menu.actions() if "Свойства" in a.text())
    action.trigger()


def test_removal_of_running_profile_warns_it_keeps_running(
    application: QApplication, tmp_path: Path
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: удаление РАБОТАЮЩЕГО профиля предупреждает, что сервер
    продолжит работать (решение заказчика 8), а отказ в диалоге оставляет
    профиль на месте — сторожит от «сначала удалить, потом спросить».
    Действие вызывается через контекстное меню карточки (`profile_menu`),
    не через приватный `_remove` напрямую.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    questions: list[str] = []

    def refuse(question: str) -> bool:
        questions.append(question)
        return False

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        confirm_removal=refuse,
    )

    _trigger_delete(view, 0)

    assert questions
    assert "продолжит работать" in questions[0]
    assert any(p.id == profile.id for p in workspace.profiles())


def test_removal_of_running_profile_confirmed_removes_it(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        confirm_removal=lambda _question: True,
    )

    _trigger_delete(view, 0)

    assert workspace.profiles() == []


def test_removal_confirmed_triggers_rescan(application: QApplication, tmp_path: Path) -> None:
    """НАХОДКА ревью (круг правок 1), подтверждена эмпирически: без
    `request_scan()` после удаления РАБОТАЮЩЕГО профиля его процесс пропадал
    из показа целиком — `foreign_servers()` отдаёт классификацию ПРЕЖНЕГО
    снимка, где процесс ещё сопоставлен со своим (уже удалённым) профилем
    и в «чужие» не попадает. Решение заказчика 8 требует, чтобы сервер
    «продолжил работать» и стал виден как чужой — без пересчёта снимка
    он не виден никак.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    rescans: list[int] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        confirm_removal=lambda _question: True,
        request_scan=lambda: rescans.append(1),
    )

    _trigger_delete(view, 0)

    assert rescans == [1]


def test_removal_of_stopped_profile_uses_plain_question(
    application: QApplication, tmp_path: Path
) -> None:
    """Профиль не запущен — вопрос обычный, без предупреждения про работу."""
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    questions: list[str] = []

    def refuse(question: str) -> bool:
        questions.append(question)
        return False

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        confirm_removal=refuse,
    )

    _trigger_delete(view, 0)

    assert questions
    assert "продолжит работать" not in questions[0]
    assert profile.name in questions[0]


# -- запуск и остановка -------------------------------------------------------


def test_start_button_click_spawns_and_triggers_rescan(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    spawn = FakeSpawn()
    workspace = _workspace(tmp_path, (profile,), spawn=spawn)
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    rescans: list[int] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        request_scan=lambda: rescans.append(1),
    )

    view.profile_button(0).click()

    assert spawn.calls
    assert rescans == [1]


def test_stop_button_click_terminates_and_triggers_rescan(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    control = FakeControl()
    workspace = _workspace(tmp_path, (profile,), control=control)
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    rescans: list[int] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        request_scan=lambda: rescans.append(1),
    )

    view.profile_button(0).click()

    assert ("terminate", 100) in control.calls
    assert rescans == [1]


def test_stop_failure_is_shown_via_show_error(application: QApplication, tmp_path: Path) -> None:
    """Гонка PID (§6.2): `ProcessMismatchError` доходит до пользователя через `show_error`."""
    profile = _profile()
    control = FakeControl(mismatched=frozenset({100}))
    workspace = _workspace(tmp_path, (profile,), control=control)
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    errors: list[str] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()

    assert errors
    assert "PID 100" in errors[0]


# -- задача 16, §8: подтверждающий скан после «Запустить» --------------------
#
# `workspace.start()` не трогает снимок процессов сам (спека T-08.12): сразу
# после успешного запуска `statuses()` всё ещё отдаёт «остановлен» по
# СТАРОМУ снимку — свежих данных ждать неоткуда до следующего `apply_scan`.  # noqa: RUF003
# Поэтому `rebuild()`, вызванный ВНУТРИ `_toggle` сразу после `start()`,
# не может быть тем самым «следующим свежим снимком», который проверяет §8:
# он использует тот же снимок, что и до запуска.
#
# Круг исправлений 1 (ревью задачи 16, Important-находка): проверка §8 живёт  # noqa: RUF003
# НЕ в `rebuild()` — тот дёргают минимум шесть посторонних путей  # noqa: RUF003
# (`apply_palette`, `_remove`, `_extinguish`, `_apply_new_profile`,
# `_apply_edited_profile`, `on_installations` в `app.py`), и любой из них до
# прихода настоящего свежего снимка потребил бы проверку на устаревших
# данных. Единственная точка входа — `ServersView.on_scan_snapshot()`:
# `_toggle` запоминает профиль как «ожидает подтверждения» ПОСЛЕ своего
# немедленного `rebuild()` (см. её докстринг), а проверяет уже  # noqa: RUF003
# `on_scan_snapshot()`, зовущийся ровно из одного места проводки —
# `monitor.snapshot_ready` → `servers_workspace.apply_scan` →
# `servers_view.on_scan_snapshot()` (в приложении) либо явного
# `workspace.apply_scan(...)` + `view.on_scan_snapshot()` (здесь, в тестах).


def test_start_that_dies_silently_is_reported(
    application: QApplication, tmp_path: Path
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ, [Ф] А3: смерть ragent молчалива, в лог ничего не пишется —

    единственный канал, которым пользователь может об этом узнать, это
    `show_error` из `ServersView` сама по себе. Подтверждающий путь — ровно
    тот, каким его зовёт `app.py` (круг исправлений 1, ревью задачи 16):
    `workspace.apply_scan(...)` + `view.on_scan_snapshot()`, а не голый
    `rebuild()`. Мутация «не проверять подтверждающий скан» (или «вернуть
    проверку в `rebuild()`») обязана уронить этот тест.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    errors: list[str] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()
    assert errors == [], "на самом клике репорта быть не должно — снимок ещё старый"

    # Подтверждающий скан: ragent так и не появился в списке процессов —
    # тот же исход, что и «умер сразу после старта, порт занят».
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view.on_scan_snapshot()

    assert errors
    assert profile.name in errors[0]
    assert str(profile.port) in errors[0]


def test_start_confirmed_running_reports_nothing(
    application: QApplication, tmp_path: Path
) -> None:
    """Обратная сторона защитного теста: подтверждающий скан нашёл процесс —

    никакого сообщения, профиль просто жив.
    """
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    errors: list[str] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    view.on_scan_snapshot()

    assert errors == []


def test_start_followed_by_unrelated_rebuild_does_not_falsely_report_death(
    application: QApplication, tmp_path: Path
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ (ревью задачи 16, круг исправлений 1, Important-находка):

    §8 обязана срабатывать только на СВЕЖИЙ снимок (`on_scan_snapshot()`),
    а не на любой `rebuild()`. `rebuild()` дёргают минимум шесть посторонних
    путей (`apply_palette`, `_remove`, `_extinguish`, `_apply_new_profile`,
    `_apply_edited_profile`, `on_installations` в `app.py`) — любой из них
    в первые секунды после «Запустить», ДО того как монитор успел донести
    свежий снимок, видел бы ещё СТАРЫЙ снимок процессов и потребил бы
    ожидание §8 на нём: живой, только что запущенный сервер получил бы
    ложное «завершился сразу после запуска». Здесь посторонний rebuild()
    смоделирован через `apply_palette()` (тот же путь, каким смена темы
    перестраивает карточки) — ревьюер воспроизвёл падение детерминированно
    именно на нём. Мутация «вернуть `_check_pending_confirmation` в
    `rebuild()`» обязана уронить этот тест на первом `assert errors == []`.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    errors: list[str] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()  # «Запустить» — ставит профиль в ожидание

    # Посторонний rebuild() ДО прихода свежего снимка — снимок процессов
    # в workspace всё ещё старый (без агента), но проверка §8 не должна
    # его увидеть вовсе.  # noqa: RUF003
    view.apply_palette(theme.LIGHT)
    assert errors == [], "посторонний rebuild() не должен потреблять проверку §8"

    # Свежий снимок наконец пришёл — сервер на самом деле жив.
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    view.on_scan_snapshot()

    assert errors == [], "первый настоящий свежий снимок показывает живой процесс"


def test_confirmation_check_fires_only_once(application: QApplication, tmp_path: Path) -> None:
    """Один факт постановки в ожидание — не более одного сообщения.

    Второй и следующие `on_scan_snapshot()` после уже проверенного запуска
    не должны повторять предупреждение.
    """
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    errors: list[str] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view.on_scan_snapshot()
    assert len(errors) == 1

    view.on_scan_snapshot()
    view.on_scan_snapshot()

    assert len(errors) == 1


def test_stop_does_not_arm_the_confirmation_check(
    application: QApplication, tmp_path: Path
) -> None:
    """§8 — только про «Запустить»: остановка не должна ставить профиль

    в ожидание подтверждения (он и так только что остановлен намеренно).
    """
    profile = _profile()
    control = FakeControl()
    workspace = _workspace(tmp_path, (profile,), control=control)
    workspace.apply_scan(ScanSnapshot(agents=(_agent(100, profile.cluster_dir),), managers=()))
    errors: list[str] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()  # «Остановить»
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view.on_scan_snapshot()

    assert errors == []


# -- предупреждения под карточкой: dir_mismatch и сироты ---------------------


def test_dir_mismatch_warning_shown_under_card(application: QApplication, tmp_path: Path) -> None:
    profile = _profile(cluster_dir=r"E:\srv\srv_8.3.10.1000")
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    warnings = view.profile_warnings(0)
    assert any("8.3.25.1633" in text and "другую версию" in text for text in warnings)


def test_orphans_warning_offers_extinguish_button(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    control = FakeControl()
    manager = ProcessInfo(
        pid=321,
        name="rmngr.exe",
        executable=None,
        argv=("rmngr.exe", "-port", str(profile.regport)),
        create_time=50.0,
    )
    workspace = _workspace(tmp_path, (profile,), control=control)
    workspace.apply_scan(ScanSnapshot(agents=(), managers=(manager,)))
    rescans: list[int] = []

    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        request_scan=lambda: rescans.append(1),
    )

    assert any("321" in text for text in view.profile_warnings(0))
    button = view.profile_extinguish_button(0)
    assert button is not None

    button.click()

    assert ("terminate", 321) in control.calls
    assert rescans == [1]


def test_no_orphans_means_no_extinguish_button(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    assert view.profile_extinguish_button(0) is None
    assert view.profile_warnings(0) == []


# -- шапка и строка пути -------------------------------------------------------


def test_path_row_shows_store_path(application: QApplication, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, ())
    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)
    assert str(workspace.store_path) in view.path_text()


def test_console_note_shows_not_registered_by_default(
    application: QApplication, tmp_path: Path
) -> None:
    workspace = _workspace(tmp_path, (), registered_radmin=lambda: None)
    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)
    assert "не зарегистрирована" in view.console_note()


def test_console_note_shows_registered_version(
    application: QApplication, tmp_path: Path
) -> None:
    workspace = _workspace(
        tmp_path,
        (),
        registered_radmin=lambda: Path(RAGENT).with_name("radmin.dll"),
    )
    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)
    assert "8.3.25.1633" in view.console_note()


def test_console_button_calls_on_console(application: QApplication, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, ())
    calls: list[int] = []
    view = ServersView(
        workspace, installed=lambda: [], palette=theme.DARK, on_console=lambda: calls.append(1)
    )
    view.console_button().click()
    assert calls == [1]


def test_add_profile_button_calls_on_add_profile(
    application: QApplication, tmp_path: Path
) -> None:
    workspace = _workspace(tmp_path, ())
    calls: list[int] = []
    view = ServersView(
        workspace,
        installed=lambda: [],
        palette=theme.DARK,
        on_add_profile=lambda: calls.append(1),
    )
    view.add_profile_button().click()
    assert calls == [1]


# -- диалог профиля (задача 15): дефолты «+ Профиль»/«Свойства…» ------------
#
# Приём — тот же, что `test_bases_view.py` использует для `InfobaseDialog`
# («build → exec → apply», `_accept`/`_reject` подменяют `exec()` класса
# диалога, не блокируя офскрин-тест). `on_add_profile`/`on_edit_profile`
# больше не no-op по умолчанию (см. докстринг `view.py`) — здесь проверяется
# именно это, а не то, что уже покрыто `test_server_dialog.py` для самого  # noqa: RUF003
# диалога.


def _accept(monkeypatch: pytest.MonkeyPatch, dialog_class: type) -> None:
    monkeypatch.setattr(dialog_class, "exec", lambda self: QDialog.DialogCode.Accepted)


def _reject(monkeypatch: pytest.MonkeyPatch, dialog_class: type) -> None:
    monkeypatch.setattr(dialog_class, "exec", lambda self: QDialog.DialogCode.Rejected)


def test_build_add_profile_dialog_gets_existing_profiles_installed_and_root(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    installation = _installation()
    view = ServersView(
        workspace,
        installed=lambda: [installation],
        palette=theme.DARK,
        servers_root=lambda: r"E:\srv",
    )

    dialog = view._build_add_profile_dialog()

    # for_new передаёт существующие профили как есть (не «без себя» — новой
    # записи ещё нет в списке); дефолтные порты for_new (1540/1541) сразу
    # конфликтуют с единственным existing-профилем — доказывает, что список  # noqa: RUF003
    # действительно дошёл до диалога, а не подставлена пустота.  # noqa: RUF003
    assert "1540" in dialog.error_text()
    assert dialog.ok_button().isEnabled() is False


def test_apply_new_profile_adds_the_profile(application: QApplication, tmp_path: Path) -> None:
    """Отдельно от `exec()` (I2, тот же приём, что `_apply_new_infobase`

    в `BasesView`): `dialog.result_profile()` не считается безусловно
    валидным — тот же рубеж, `ServersWorkspace.add_profile`, что и у обычной
    записи через контроллер, доказывается напрямую.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path, ())
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)
    dialog = ServerProfileDialog.for_new([], [_installation()], "", parent=view)
    dialog.name_edit().setText("Новый профиль")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\new")

    view._apply_new_profile(dialog)

    names = [p.name for p in workspace.profiles()]
    assert names == ["Новый профиль"]


def test_apply_new_profile_triggers_rescan(application: QApplication, tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ.

    IMPORTANT 6 финального ревью: без `request_scan()` после добавления
    профиля список процессов не пересчитывается до следующего планового
    скана (до 5 с, спека §4.4) — симметрично удалению/переключению
    (`test_removal_confirmed_triggers_rescan`,
    `test_start_button_click_spawns_and_triggers_rescan`).
    Мутация: убрать `self._request_scan()` из `_apply_new_profile` —
    тест обязан упасть.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path, ())
    rescans: list[int] = []
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        request_scan=lambda: rescans.append(1),
    )
    dialog = ServerProfileDialog.for_new([], [_installation()], "", parent=view)
    dialog.name_edit().setText("Новый профиль")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\new")

    view._apply_new_profile(dialog)

    assert rescans == [1]


def test_apply_edited_profile_triggers_rescan(application: QApplication, tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ.

    IMPORTANT 6 финального ревью: симметрично добавлению/удалению — правка
    профиля тоже обязана попросить рескан (свежие данные о версии живого
    процесса и т.п., которых в старом снимке ещё не было). Пересопоставление
    УЖЕ имеющегося снимка проверяет отдельный тест в `test_servers.py`
    (`TestRematchAfterSave`) — здесь только сам факт вызова `request_scan`.
    Мутация: убрать `self._request_scan()` из `_apply_edited_profile` —
    тест обязан упасть.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    rescans: list[int] = []
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        request_scan=lambda: rescans.append(1),
    )
    dialog = view._build_edit_profile_dialog(profile.id)
    assert dialog is not None

    view._apply_edited_profile(dialog)

    assert rescans == [1]


def test_add_profile_button_reaches_apply_when_dialog_is_accepted(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Проводка «собрать → показать → применить» (I2 финального ревью

    `BasesView`, тот же приём здесь): `_apply_new_profile` подменяется, чтобы
    доказать саму связку `exec() == Accepted → apply`, не заново гоняя
    валидацию `ServerProfileDialog`.
    """
    workspace = _workspace(tmp_path, ())
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)
    applied: list[ServerProfileDialog] = []
    monkeypatch.setattr(view, "_apply_new_profile", applied.append)
    _accept(monkeypatch, ServerProfileDialog)

    view.add_profile_button().click()

    assert len(applied) == 1


def test_default_add_profile_does_nothing_when_dialog_is_cancelled(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path, ())
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)
    _reject(monkeypatch, ServerProfileDialog)

    view.add_profile_button().click()

    assert workspace.profiles() == []


def test_default_add_profile_shows_error_when_workspace_rejects_it(
    application: QApplication, tmp_path: Path
) -> None:
    """Дубль порта дошёл бы до `ok_button().isEnabled()` в диалоге — здесь

    граница проверяется на уровне `_apply_new_profile`/`ServersWorkspace`
    напрямую (тем же приёмом, что `test_stop_failure_is_shown_via_show_error`),
    в обход живой валидации диалога.
    """
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    errors: list[str] = []
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    dialog = ServerProfileDialog.for_new([], [_installation()], "", parent=view)
    dialog.name_edit().setText("Дубль")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\dup")
    # Диалог сам не пустил бы такой профиль — others у него уже включал  # noqa: RUF003
    # existing и порт 1540 конфликтовал бы. Здесь others у диалога пуст  # noqa: RUF003
    # (`existed=[]`), поэтому его собственная валидация зелёная, а конфликт  # noqa: RUF003
    # ловит именно `ServersWorkspace.add_profile` — граница проверяется
    # отдельно от диалога, как и планировалось (`_apply_new_profile`).

    view._apply_new_profile(dialog)

    assert errors
    assert "1540" in errors[0]
    assert workspace.profiles() == [profile]


def test_properties_menu_item_present_before_delete(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    labels = [action.text() for action in view.profile_menu(0).actions()]

    properties_index = next(i for i, label in enumerate(labels) if "Свойства" in label)
    delete_index = next(i for i, label in enumerate(labels) if "Удалить" in label)
    assert properties_index < delete_index


def test_default_edit_profile_updates_on_accept(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)
    _accept(monkeypatch, ServerProfileDialog)

    _trigger_properties(view, 0)

    updated = next(p for p in workspace.profiles() if p.id == profile.id)
    # exec() подменён на Accepted без изменения полей — диалог открылся
    # с данными исходного профиля (for_edit), и update_profile переписал  # noqa: RUF003
    # тот же профиль тем же значением (untouched-инвариант дошёл до записи).
    assert updated == profile


def test_default_edit_profile_does_nothing_when_dialog_is_cancelled(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)
    _reject(monkeypatch, ServerProfileDialog)

    _trigger_properties(view, 0)

    assert workspace.profiles() == [profile]


def test_build_edit_profile_dialog_returns_none_for_a_vanished_profile(
    application: QApplication, tmp_path: Path
) -> None:
    workspace = _workspace(tmp_path, ())
    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)

    assert view._build_edit_profile_dialog("does-not-exist") is None


def test_on_edit_profile_injection_overrides_the_default(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    calls: list[str] = []
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        on_edit_profile=calls.append,
    )

    _trigger_properties(view, 0)

    assert calls == [profile.id]
    # Инъекция подменяет дефолт целиком — настоящий диалог не открывался,
    # иначе тест завис бы на блокирующем exec() (в этом и смысл проверки).
    assert workspace.profiles() == [profile]


# -- палитра -------------------------------------------------------------------


def test_apply_palette_repaints_status_colours(application: QApplication, tmp_path: Path) -> None:
    profile = _profile(version="8.5.1")
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)
    assert theme.DARK.problem in view.profile_status_label(0).styleSheet()

    view.apply_palette(theme.LIGHT)

    assert theme.LIGHT.problem in view.profile_status_label(0).styleSheet()


# -- отсутствие профилей: аксессоры не падают ----------------------------------


def test_empty_workspace_has_no_profile_rows(application: QApplication, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, ())
    view = ServersView(workspace, installed=lambda: [], palette=theme.DARK)
    assert view.profile_rows() == []
    assert view.foreign_rows() == []


# -- выделение карточки и панель «Журнал профиля» (T-10, задача 5) ----------


def test_journal_panel_starts_with_the_placeholder(
    application: QApplication, tmp_path: Path
) -> None:
    """Ничего не выделено сразу после открытия раздела — панель в плейсхолдере."""
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    assert view.selected_profile_id() is None
    assert view.journal_panel().text() == ""


def test_card_click_selects_it_and_shows_its_journal(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """Клик по карточке (mouseRelease, как в брифе) выделяет её и показывает журнал."""
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    workspace.log_event(profile.id, "тестовое событие")

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    qtbot.mouseRelease(view.profile_card(0), Qt.MouseButton.LeftButton)

    assert view.selected_profile_id() == profile.id
    assert profile.name in view.journal_panel().title_label().text()
    assert "тестовое событие" in view.journal_panel().text()
    # Карточка перестроена целиком (rebuild() внутри _select_profile) —
    # обращаемся к СВЕЖЕЙ карточке по тому же индексу, старая уже мертва.
    assert theme.DARK.accent in view.profile_card(0).styleSheet()


def test_unselected_card_has_no_accent_border(
    application: QApplication, tmp_path: Path
) -> None:
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    assert theme.DARK.accent not in view.profile_card(0).styleSheet()


def test_selecting_another_card_moves_the_border(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    profile_a = _profile(id="a", name="A")
    profile_b = _profile(
        id="b",
        name="B",
        port=1640,
        regport=1641,
        range_start=1660,
        range_end=1691,
        cluster_dir=r"E:\srv\b",
    )
    workspace = _workspace(tmp_path, (profile_a, profile_b))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view = ServersView(workspace, installed=lambda: [_installation()], palette=theme.DARK)

    qtbot.mouseRelease(view.profile_card(0), Qt.MouseButton.LeftButton)
    assert view.selected_profile_id() == profile_a.id

    qtbot.mouseRelease(view.profile_card(1), Qt.MouseButton.LeftButton)

    assert view.selected_profile_id() == profile_b.id
    assert theme.DARK.accent in view.profile_card(1).styleSheet()
    assert theme.DARK.accent not in view.profile_card(0).styleSheet()


def test_deleting_the_selected_profile_resets_the_panel_to_placeholder(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: удаление выделенного профиля обязано сбросить панель.

    Без сброса «Журнал профиля» продолжал бы показывать журнал записи,
    которой больше нет в списке серверов, — заголовок и текст ссылались бы
    на исчезнувший профиль. Мутация «убрать `_clear_selection()` из
    `_remove`» обязана уронить этот тест на первом `assert` после удаления.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        confirm_removal=lambda _question: True,
    )
    qtbot.mouseRelease(view.profile_card(0), Qt.MouseButton.LeftButton)
    assert view.selected_profile_id() == profile.id

    _trigger_delete(view, 0)

    assert view.selected_profile_id() is None
    assert view.journal_panel().text() == ""
    assert "профиль" in view.journal_panel().placeholder().casefold()


def test_deleting_an_unselected_profile_keeps_the_selection(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """Удаление ЧУЖОЙ (не выделенной) карточки не трогает текущее выделение."""
    profile_a = _profile(id="a", name="A")
    profile_b = _profile(
        id="b",
        name="B",
        port=1640,
        regport=1641,
        range_start=1660,
        range_end=1691,
        cluster_dir=r"E:\srv\b",
    )
    workspace = _workspace(tmp_path, (profile_a, profile_b))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        confirm_removal=lambda _question: True,
    )
    qtbot.mouseRelease(view.profile_card(0), Qt.MouseButton.LeftButton)
    assert view.selected_profile_id() == profile_a.id

    _trigger_delete(view, 1)  # удаляем B, выделен A

    assert view.selected_profile_id() == profile_a.id
    assert profile_a.name in view.journal_panel().title_label().text()


def test_death_after_start_is_also_written_to_the_journal(
    application: QApplication, tmp_path: Path
) -> None:
    """§8: то же сообщение, что уходит в `show_error`, попадает и в журнал профиля.

    Платформа сама о причине смерти не пишет ([Ф] А3/А4 T-09) — раз уж
    OneCStarter заметил исход через подтверждающий скан, «Журнал профиля»
    обязан его показать. Тот же путь, каким его зовёт `app.py`
    (`workspace.apply_scan(...)` + `view.on_scan_snapshot()`), что и
    `test_start_that_dies_silently_is_reported` выше.
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    errors: list[str] = []
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        # show_error подменён тем же приёмом, что и у остальных тестов §8  # noqa: RUF003
        # (test_start_that_dies_silently_is_reported): дефолт открывает
        # настоящий блокирующий QMessageBox.exec() — офскрин-тест иначе висит.
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    view.on_scan_snapshot()

    assert errors  # доказывает, что §8 действительно сработала
    journal_text = workspace.journal_path(profile.id).read_text(encoding="utf-8")
    assert "завершился сразу после запуска" in journal_text
    assert str(profile.port) in journal_text


def test_confirmed_running_is_also_written_to_the_journal(
    application: QApplication, tmp_path: Path
) -> None:
    """Important 2 финального ревью ветки T-10: положительный §8-исход тоже в журнал.

    Спека §12.1 обещает «PID-ы дерева по скану, итог подтверждающего
    скана» — не только отказ. Раньше в журнал попадал только отрицательный
    исход (`test_death_after_start_is_also_written_to_the_journal` выше),
    и между «запуск: …» и следующим ручным действием пользователя не
    оставалось никакого следа о том, что сервер вообще поднялся. Тот же
    путь, каким его зовёт `app.py`, что и у теста отрицательной ветки.
    Мутация: убрать запись `работает · PID …` из положительной ветки
    `_check_pending_confirmation` — тест обязан упасть (строки не будет).
    """  # noqa: RUF002
    profile = _profile()
    workspace = _workspace(tmp_path, (profile,))
    workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
    errors: list[str] = []
    view = ServersView(
        workspace,
        installed=lambda: [_installation()],
        palette=theme.DARK,
        show_error=lambda message: errors.append(message),
    )

    view.profile_button(0).click()
    workspace.apply_scan(ScanSnapshot(agents=(_agent(4242, profile.cluster_dir),), managers=()))
    view.on_scan_snapshot()

    assert errors == []  # положительный исход — не §8-предупреждение
    journal_text = workspace.journal_path(profile.id).read_text(encoding="utf-8")
    assert "работает · PID 4242" in journal_text
