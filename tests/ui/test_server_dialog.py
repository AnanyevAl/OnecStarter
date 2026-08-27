"""Диалог профиля сервера и диалог консоли администрирования (T-08, задача 15)."""

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from onecstarter.domain.server import ServerProfile
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.ui import theme
from onecstarter.ui.servers.dialog import ConsoleDialog, ConsoleVersionRow, ServerProfileDialog


def _type(widget: QWidget, text: str) -> None:
    """Набрать текст посимвольно взаправду (эмитит textEdited), не только setText.

    Тот же обходной путь, что `_type` в `test_bases_view.py` (см. её докстринг):
    `QTest.keyClicks` виснет на этой машине на кириллице, однобуквенный
    `QTest.keyClick` портит небайтовые символы — собираем `QKeyEvent`
    и шлём напрямую виджету, в обход платформенной раскладки клавиатуры.
    """
    for char in text:
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(
                widget, QKeyEvent(kind, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, char)
            )


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


# -- дубль порта: ОК неактивна, причина видна, исправление активирует ------  # noqa: RUF003


def test_duplicate_port_with_other_profile_disables_ok_with_reason(
    application: QApplication,
) -> None:
    existing = [_profile()]
    dialog = ServerProfileDialog.for_new(existing, [_installation()], r"E:\srv")
    dialog.name_edit().setText("Новый профиль")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\custom")

    # Дефолты for_new (1540/1541, по образцу srv.sh) совпадают с портами  # noqa: RUF003
    # existing — дубль виден без единой правки полей порта.
    assert dialog.ok_button().isEnabled() is False
    assert "1540" in dialog.error_text()
    assert "8.3.25 отладка" in dialog.error_text()


def test_fixing_the_duplicate_port_enables_ok(application: QApplication) -> None:
    existing = [_profile()]
    dialog = ServerProfileDialog.for_new(existing, [_installation()], r"E:\srv")
    dialog.name_edit().setText("Новый профиль")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\custom")
    assert dialog.ok_button().isEnabled() is False

    dialog.port_edit().setText("1640")
    dialog.regport_edit().setText("1641")

    assert dialog.ok_button().isEnabled() is True
    assert dialog.error_text() == ""


# -- смена regport в for_edit: предупреждение, не блокер -------------------


def test_for_edit_regport_change_warns_and_keeps_ok_enabled(application: QApplication) -> None:
    profile = _profile()
    dialog = ServerProfileDialog.for_edit(profile, [], [_installation()], "")

    dialog.regport_edit().setText("1642")

    assert "новый пустой реестр" in dialog.warning_text()
    assert dialog.ok_button().isEnabled() is True
    assert dialog.error_text() == ""


def test_for_edit_untouched_regport_has_no_warning(application: QApplication) -> None:
    profile = _profile()
    dialog = ServerProfileDialog.for_edit(profile, [], [_installation()], "")
    assert dialog.warning_text() == ""


# -- подстановка каталога от разрешённой версии (спека §3.2) ---------------


def test_version_mask_substitutes_dir_from_the_resolved_version(
    application: QApplication,
) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation("8.3.25.1633")], r"E:\srv")

    dialog.version_combo().setEditText("8.3.25")

    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.25.1633"
    assert dialog.resolved_text() == "→ 8.3.25.1633"


def test_unresolved_version_does_not_substitute_and_shows_not_installed(
    application: QApplication,
) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation("8.3.25.1633")], r"E:\srv")

    dialog.version_combo().setEditText("8.5.1")

    assert dialog.dir_edit().text() == ""
    assert dialog.resolved_text() == "→ не установлена"


def test_manual_dir_edit_stops_further_substitution(application: QApplication) -> None:
    dialog = ServerProfileDialog.for_new(
        [], [_installation("8.3.25.1633"), _installation("8.3.27.2214")], r"E:\srv"
    )
    dialog.version_combo().setEditText("8.3.25")
    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.25.1633"

    dialog.dir_edit().clear()
    _type(dialog.dir_edit(), r"E:\custom\path")

    dialog.version_combo().setEditText("8.3.27")

    assert dialog.dir_edit().text() == r"E:\custom\path"


def test_browse_selected_directory_also_stops_substitution(application: QApplication) -> None:
    """«Обзор…» — тоже ручная правка (докстринг модуля), не только ввод текста."""
    dialog = ServerProfileDialog.for_new(
        [],
        [_installation("8.3.25.1633"), _installation("8.3.27.2214")],
        r"E:\srv",
        choose_directory=lambda: r"E:\chosen\dir",
    )
    dialog.version_combo().setEditText("8.3.25")
    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.25.1633"

    dialog.browse_button().click()
    assert dialog.dir_edit().text() == r"E:\chosen\dir"

    dialog.version_combo().setEditText("8.3.27")

    assert dialog.dir_edit().text() == r"E:\chosen\dir"


def test_clearing_the_directory_resumes_substitution(application: QApplication) -> None:
    """Условие подстановки — «пусто ИЛИ не тронуто» (буквально по брифу): опустевшее

    руками поле снова подставляется на следующей смене версии.
    """
    dialog = ServerProfileDialog.for_new(
        [], [_installation("8.3.25.1633"), _installation("8.3.27.2214")], r"E:\srv"
    )
    dialog.version_combo().setEditText("8.3.25")
    _type(dialog.dir_edit(), "x")  # трогаем руками — подстановка остановлена
    dialog.dir_edit().clear()  # но теперь поле снова пустое

    dialog.version_combo().setEditText("8.3.27")

    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.27.2214"


# -- пустой каталог и мусорный диапазон — свои ошибки -----------------------


def test_empty_dir_is_a_validation_error(application: QApplication) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation()], "")
    dialog.name_edit().setText("Новый")
    dialog.version_combo().setEditText("8.3.25.1633")

    assert dialog.dir_edit().text() == ""
    assert dialog.ok_button().isEnabled() is False
    assert "каталог" in dialog.error_text().casefold()


def test_garbage_range_is_its_own_error_before_validate_profile(
    application: QApplication,
) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation()], "")
    dialog.name_edit().setText("Новый")
    dialog.dir_edit().setText(r"E:\srv\x")

    dialog.range_edit().setText("1560-1591")  # дефис вместо двоеточия

    assert dialog.ok_button().isEnabled() is False
    assert dialog.error_text() == "Диапазон — два числа через двоеточие"


def test_fixing_the_range_format_clears_the_error(application: QApplication) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation()], "")
    dialog.name_edit().setText("Новый")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\x")
    dialog.range_edit().setText("1560-1591")
    assert dialog.ok_button().isEnabled() is False

    dialog.range_edit().setText("1560:1591")

    assert dialog.ok_button().isEnabled() is True
    assert dialog.error_text() == ""


# -- дефолты for_new и итоговый профиль -------------------------------------


def test_for_new_defaults_match_srv_sh_conventions(application: QApplication) -> None:
    dialog = ServerProfileDialog.for_new([], [], "")

    assert dialog.name_edit().text() == ""
    assert dialog.version_combo().currentText() == ""
    assert dialog.port_edit().text() == "1540"
    assert dialog.regport_edit().text() == "1541"
    assert dialog.range_edit().text() == "1560:1591"
    assert dialog.dir_edit().text() == ""
    assert dialog.debug_checkbox().isChecked() is True
    assert dialog.http_checkbox().isChecked() is True
    assert dialog.extra_edit().text() == ""


def test_result_profile_builds_expected_profile_from_the_fields(
    application: QApplication,
) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation("8.3.25.1633")], "")
    dialog.name_edit().setText("Тест")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\custom")
    dialog.port_edit().setText("1640")
    dialog.regport_edit().setText("1641")
    dialog.range_edit().setText("1660:1691")
    dialog.debug_checkbox().setChecked(False)
    dialog.http_checkbox().setChecked(False)
    dialog.extra_edit().setText("-conf-version-min 1")

    result = dialog.result_profile()

    assert result == ServerProfile(
        id="",
        name="Тест",
        version="8.3.25.1633",
        port=1640,
        regport=1641,
        range_start=1660,
        range_end=1691,
        cluster_dir=r"E:\srv\custom",
        debug=False,
        http=False,
        extra_args="-conf-version-min 1",
    )


def test_for_edit_prefills_fields_and_keeps_the_id(application: QApplication) -> None:
    profile = ServerProfile(
        id="p9",
        name="Правка",
        version="8.3.25",
        port=1540,
        regport=1541,
        range_start=1560,
        range_end=1591,
        cluster_dir=r"E:\custom\mydir",
        debug=False,
        http=True,
        extra_args="-x",
    )
    dialog = ServerProfileDialog.for_edit(profile, [], [_installation("8.3.25.1633")], r"E:\srv")

    assert dialog.name_edit().text() == "Правка"
    assert dialog.version_combo().currentText() == "8.3.25"
    assert dialog.port_edit().text() == "1540"
    assert dialog.regport_edit().text() == "1541"
    assert dialog.range_edit().text() == "1560:1591"
    assert dialog.debug_checkbox().isChecked() is False
    assert dialog.http_checkbox().isChecked() is True
    assert dialog.extra_edit().text() == "-x"
    # Мутационная проверка (CLAUDE.md): каталог задан ИНАЧЕ, чем его  # noqa: RUF003
    # подставила бы §3.2 от разрешённой версии (srv_8.3.25.1633) — если бы
    # подстановка ошибочно срабатывала уже при открытии нетронутого диалога
    # (а не только на смену версии пользователем), это поле изменилось бы,  # noqa: RUF003
    # и untouched-инвариант (тот же принцип, что у InfobaseDialog) был бы  # noqa: RUF003
    # нарушен молча.
    assert dialog.dir_edit().text() == r"E:\custom\mydir"
    assert dialog.result_profile() == profile


# -- круг исправлений 1 (ревью задачи 15) ------------------------------------
#
# НАХОДКА 1: for_edit молча переписывал уже заданный каталог профиля на
# смену версии — прямое нарушение спеки §3.2 («каталог хранится в профиле
# строкой и после подстановки не пересчитывается»), ровно сценарий «переезда
# на пустой кластер» после доустановки патча. Фикс — for_edit стартует
# с _dir_touched=True (каталог уже существующего профиля неприкосновенен).  # noqa: RUF003


def test_for_edit_version_change_does_not_rewrite_the_existing_directory(
    application: QApplication,
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ (воспроизведён ревьюером): смена версии в for_edit не

    трогает уже заданный каталог кластера, даже когда подстановка нашла бы
    для новой версии осмысленный результат — спека §3.2 требует именно
    это, а не «подставим то, что сейчас разрешилось».
    """  # noqa: RUF002
    profile = ServerProfile(
        id="p9",
        name="Правка",
        version="8.3.25",
        port=1540,
        regport=1541,
        range_start=1560,
        range_end=1591,
        cluster_dir=r"E:\srv\srv_8.3.25.1633",
        debug=True,
        http=True,
        extra_args="",
    )
    dialog = ServerProfileDialog.for_edit(
        profile, [], [_installation("8.3.25.1633"), _installation("8.3.25.1700")], r"E:\srv"
    )

    dialog.version_combo().setEditText("8.3.25.1700")

    assert dialog.resolved_text() == "→ 8.3.25.1700"
    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.25.1633"


def test_for_edit_still_substitutes_when_the_directory_is_actually_empty(
    application: QApplication,
) -> None:
    """Вторая половина условия «пуст ИЛИ не тронут» не зависит от режима:

    профиль с пустым каталогом (гипотетический край) — не заперт навсегда,
    подстановка всё ещё работает, когда полю реально нечего защищать.
    """  # noqa: RUF002
    profile = ServerProfile(
        id="p9",
        name="Правка",
        version="8.3.25",
        port=1540,
        regport=1541,
        range_start=1560,
        range_end=1591,
        cluster_dir="",
        debug=True,
        http=True,
        extra_args="",
    )
    dialog = ServerProfileDialog.for_edit(profile, [], [_installation("8.3.25.1633")], r"E:\srv")

    dialog.version_combo().setEditText("8.3.25.1633")

    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.25.1633"


def test_for_new_still_substitutes_on_version_change(application: QApplication) -> None:
    """Регрессия: НАХОДКА 1 не должна была задеть обычную подстановку for_new."""
    dialog = ServerProfileDialog.for_new([], [_installation("8.3.25.1633")], r"E:\srv")

    dialog.version_combo().setEditText("8.3.25.1633")

    assert dialog.dir_edit().text() == r"E:\srv\srv_8.3.25.1633"


def test_dir_note_shows_the_permanent_guarantee_from_the_mockup(
    application: QApplication,
) -> None:
    dialog = ServerProfileDialog.for_new([], [_installation()], r"E:\srv")

    assert "не пересчитывается" in dialog.dir_note()
    assert "переедет" in dialog.dir_note()


def test_dir_note_is_present_and_unchanged_for_for_edit_too(application: QApplication) -> None:
    profile = _profile()
    dialog = ServerProfileDialog.for_edit(profile, [], [_installation()], r"E:\srv")
    assert dialog.dir_note() != ""


# -- круг исправлений 1 (ревью задачи 15), НАХОДКА 2: цвет предупреждения/ошибки --


def test_without_palette_labels_stay_uncoloured(application: QApplication) -> None:
    existing = [_profile()]
    dialog = ServerProfileDialog.for_new(existing, [_installation()], r"E:\srv")
    dialog.name_edit().setText("Новый")
    dialog.version_combo().setEditText("8.3.25.1633")
    dialog.dir_edit().setText(r"E:\srv\custom")

    assert dialog.error_label_style() == ""
    assert dialog.warning_label_style() == ""


def test_palette_colours_persist_after_text_updates_from_live_validation(
    application: QApplication,
) -> None:
    """Стиль ставится один раз в `__init__` — `setText()` из `_refresh_state`

    (реальная живая валидация, не голая проверка на пустом диалоге) его
    не сбрасывает.
    """  # noqa: RUF002
    palette = theme.DARK
    dialog = ServerProfileDialog.for_edit(_profile(), [], [_installation()], "", palette=palette)

    dialog.regport_edit().setText("1642")  # предупреждение, ОК остаётся активна  # noqa: RUF003
    assert dialog.warning_text() != ""
    assert dialog.warning_label_style() == f"color: {palette.accent};"

    dialog.port_edit().setText("1642")  # тот же порт, что и regport — ошибка
    assert dialog.error_text() != ""
    assert dialog.error_label_style() == f"color: {palette.problem};"

    assert dialog.error_label_style() != dialog.warning_label_style()


def test_palette_is_accepted_by_for_new_too(application: QApplication) -> None:
    palette = theme.LIGHT
    dialog = ServerProfileDialog.for_new([], [_installation()], "", palette=palette)

    assert dialog.error_label_style() == f"color: {palette.problem};"
    assert dialog.warning_label_style() == f"color: {palette.accent};"


# -- ConsoleDialog ------------------------------------------------------------


def test_current_version_is_marked(application: QApplication) -> None:
    installed = [_installation("8.3.22.1923"), _installation("8.3.25.1633")]
    dialog = ConsoleDialog.build(installed, parse_version("8.3.25.1633"), [])

    rows = dialog.version_rows()

    assert rows == [
        ConsoleVersionRow(version=parse_version("8.3.22.1923"), current=False, running=False),
        ConsoleVersionRow(version=parse_version("8.3.25.1633"), current=True, running=False),
    ]


def test_no_current_marks_nothing_current(application: QApplication) -> None:
    dialog = ConsoleDialog.build([_installation("8.3.25.1633")], None, [])
    assert dialog.version_rows()[0].current is False


def test_running_versions_are_marked(application: QApplication) -> None:
    installed = [_installation("8.3.22.1923"), _installation("8.3.25.1633")]
    dialog = ConsoleDialog.build(installed, None, [parse_version("8.3.25.1633")])

    rows = dialog.version_rows()

    assert rows[0].running is False
    assert rows[1].running is True


def test_selected_installation_returns_the_right_entry(application: QApplication) -> None:
    installed = [_installation("8.3.22.1923"), _installation("8.3.25.1633")]
    dialog = ConsoleDialog.build(installed, None, [])

    dialog.list_widget().setCurrentRow(0)
    assert dialog.selected_installation() == installed[0]

    dialog.list_widget().setCurrentRow(1)
    assert dialog.selected_installation() == installed[1]


def test_register_button_disabled_when_selection_is_current(application: QApplication) -> None:
    dialog = ConsoleDialog.build([_installation("8.3.25.1633")], parse_version("8.3.25.1633"), [])
    # Текущая версия выбрана по умолчанию (единственная строка).
    assert dialog.register_button().isEnabled() is False


def test_register_button_enabled_when_selection_is_not_current(
    application: QApplication,
) -> None:
    installed = [_installation("8.3.22.1923"), _installation("8.3.25.1633")]
    dialog = ConsoleDialog.build(installed, parse_version("8.3.25.1633"), [])

    dialog.list_widget().setCurrentRow(0)

    assert dialog.register_button().isEnabled() is True


def test_open_button_enabled_when_current_is_registered(application: QApplication) -> None:
    dialog = ConsoleDialog.build([_installation()], parse_version("8.3.25.1633"), [])
    assert dialog.open_button().isEnabled() is True


def test_open_button_disabled_when_nothing_is_registered(application: QApplication) -> None:
    dialog = ConsoleDialog.build([_installation()], None, [])
    assert dialog.open_button().isEnabled() is False


def test_cancel_button_rejects_the_dialog(application: QApplication) -> None:
    dialog = ConsoleDialog.build([], None, [])
    dialog.cancel_button().click()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_empty_installed_list_has_no_rows(application: QApplication) -> None:
    dialog = ConsoleDialog.build([], parse_version("8.3.25.1633"), [])
    assert dialog.version_rows() == []
    assert dialog.selected_installation() is None
    assert dialog.register_button().isEnabled() is False
