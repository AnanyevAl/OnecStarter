"""Раздел «Серверы»: список профилей и чужие серверы (T-08, задача 14).

Воркспейс — настоящий `ServersWorkspace` на `tmp_path` с локальными фейками
`FakeControl`/`FakeSpawn` (тот же приём, что и в `tests/unit/test_servers.py`,
но не импортируется оттуда — там классы модульные, а не для переиспользования
извне, и раздувать связь между unit- и ui-наборами незачем). Снимок процессов
кладётся напрямую через `ServersWorkspace.apply_scan(ScanSnapshot(...))` —
конструировать `ProcessScanner` ради одного снимка в каждом тесте избыточно,
сама функция `scan_servers` уже покрыта юнит-тестами.
"""  # noqa: RUF002

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import ServerProfile
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.process_control import ProcessMismatchError
from onecstarter.platform_1c.process_scan import ProcessInfo
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.services.servers import ScanSnapshot, ServersWorkspace
from onecstarter.ui import theme
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
    pid: int = 4242
    calls: list[LaunchCommand] = field(default_factory=list)

    def __call__(self, command: LaunchCommand) -> int:
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
        "spawn": spawn if spawn is not None else FakeSpawn(),
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


# -- удаление профиля --------------------------------------------------------


def test_removal_of_running_profile_warns_it_keeps_running(
    application: QApplication, tmp_path: Path
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: удаление РАБОТАЮЩЕГО профиля предупреждает, что сервер
    продолжит работать (решение заказчика 8), а отказ в диалоге оставляет
    профиль на месте — сторожит от «сначала удалить, потом спросить».
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

    view.profile_delete_button(0).click()

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

    view.profile_delete_button(0).click()

    assert workspace.profiles() == []


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

    view.profile_delete_button(0).click()

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
