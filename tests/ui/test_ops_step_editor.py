"""Свойства шага и выбор команды (спека v4, §7.4)."""

from datetime import datetime
from typing import Any

import shiboken6
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QWidget
from pytestqt.qtbot import QtBot

from onecstarter.domain.cli_catalog import ArgSpec
from onecstarter.domain.operations import Step, SubstitutionContext
from onecstarter.domain.operations_text import step_title
from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.ui.ops.command_picker import CommandPicker
from onecstarter.ui.ops.step_editor import SUBSTITUTIONS_HELP, StepEditor
from onecstarter.ui.theme import LIGHT

CATALOG = load_cli_catalog()
SAMPLE = SubstitutionContext("Склад: юг", "Клиенты", "8.3.27.2214", datetime(2026, 11, 14, 9, 5, 7))


def _editor(qtbot: QtBot, **kwargs: Any) -> tuple[StepEditor, list[Step]]:
    editor = StepEditor(CATALOG, environ={"USERPROFILE": r"C:\Users\me"}, **kwargs)
    qtbot.addWidget(editor)
    emitted: list[Step] = []
    editor.changed.connect(emitted.append)
    return editor, emitted


def _last_values(emitted: list[Step]) -> tuple[str | None, ...]:
    return emitted[-1].values


def test_empty_editor_shows_nothing(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    editor.set_step(None)
    assert editor.step() is None and editor.title_text() == "" and editor.value_widget(0) is None


def test_fresh_editor_hides_output_checkboxes_and_help(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    editor.show()
    boxes = {box.text(): box for box in editor.findChildren(QCheckBox)}
    assert boxes, "ожидались флажки перезаписи и создания каталогов"
    assert all(not box.isVisible() for box in boxes.values())
    helps = [lbl for lbl in editor.findChildren(QLabel) if lbl.objectName() == "SettingsNote"]
    assert helps and all(not lbl.isVisible() for lbl in helps)


def test_fields_follow_the_argument_kinds(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    editor.set_step(Step("/ConfigurationRepositoryUpdateCfg", ("5", None, "")))
    assert editor.title_text() == "Получить конфигурацию из хранилища"
    assert "Обновляет рабочую конфигурацию" in editor.description_text()
    version, revised, force = (editor.value_widget(i) for i in range(3))
    assert isinstance(version, QLineEdit) and version.text() == "5"
    assert isinstance(revised, QCheckBox) and not revised.isChecked()
    assert isinstance(force, QCheckBox) and force.isChecked()
    assert editor.value_widget(5) is None  # bound: поля нет
    restore = Step("/RestoreIB", (r"D:\a.dt", "+"))
    editor.set_step(restore)
    assert isinstance(editor.value_widget(1), QComboBox)
    combo = editor.value_widget(1)
    assert isinstance(combo, QComboBox) and combo.currentData() == "+"


def test_editing_emits_a_new_step_and_empty_means_none(qtbot: QtBot) -> None:
    editor, emitted = _editor(qtbot)
    editor.set_step(Step("/ConfigurationRepositoryUpdateCfg", ("5",)))
    editor.set_value(0, "")
    editor.set_value(2, "")  # флаг включён
    assert emitted[0].values[0] is None
    assert emitted[-1].values[:3] == (None, None, "")
    assert editor.step() == emitted[-1]
    count = len(emitted)
    editor.set_value(0, None)  # значение не изменилось — сигнала нет
    assert len(emitted) == count


def test_typing_in_a_field_updates_the_step(qtbot: QtBot) -> None:
    editor, emitted = _editor(qtbot)
    editor.set_step(Step("/DumpIB", (None,)), sample=SAMPLE)
    field = editor.value_widget(0)
    assert isinstance(field, QLineEdit)
    field.setText(r"%USERPROFILE%\{база}.dt")
    field.editingFinished.emit()
    assert emitted[-1].values == (r"%USERPROFILE%\{база}.dt",)
    assert editor.example_text() == r"Для «Склад: юг»: C:\Users\me\Склад_ юг.dt"
    field.setText("   ")
    field.editingFinished.emit()
    assert _last_values(emitted) == (None,)
    assert editor.example_text() == ""
    assert "не задан обязательный параметр «файл выгрузки»" in editor.problems_text()
    editor.set_value(0, r"D:.dt")
    editor.set_value(0, "   ")  # пробелы без поля: тоже «не задано»
    assert _last_values(emitted) == (None,)


def test_browse_button_fills_the_path(qtbot: QtBot) -> None:
    asked: list[tuple[str, str]] = []

    def choose(_parent: QWidget, arg: ArgSpec, current: str) -> str:
        asked.append((arg.role or "", current))
        return r"D:\Backup\x.dt"

    editor, emitted = _editor(qtbot, choose_path=choose)
    editor.set_step(Step("/DumpIB", (r"D:\old.dt",)))
    editor.browse(0)
    assert asked == [("output", r"D:\old.dt")]
    assert emitted[-1].values == (r"D:\Backup\x.dt",)
    field = editor.value_widget(0)
    assert isinstance(field, QLineEdit) and field.text() == r"D:\Backup\x.dt"
    editor_choose_nothing = StepEditor(CATALOG, choose_path=lambda *_: "")
    qtbot.addWidget(editor_choose_nothing)
    editor_choose_nothing.set_step(Step("/DumpIB", (r"D:\old.dt",)))
    editor_choose_nothing.browse(0)
    assert editor_choose_nothing.step() == Step("/DumpIB", (r"D:\old.dt",))  # отмена выбора


def test_output_flags_only_for_commands_that_write(qtbot: QtBot) -> None:
    editor, emitted = _editor(qtbot)
    editor.set_step(Step("/DumpIB", (r"D:\a.dt",)))
    assert editor.overwrite_checkbox().isVisibleTo(editor)
    editor.set_overwrite(True)
    editor.set_create_dirs(False)
    assert (emitted[-1].overwrite, emitted[-1].create_dirs) == (True, False)
    editor.set_step(Step("/RestoreIB", (r"D:\a.dt",)))
    assert not editor.overwrite_checkbox().isVisibleTo(editor)


def test_hints_and_substitution_help(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    editor.set_step(Step("/DumpConfigToFiles", (r"D:\src", None, None, None, "")))
    assert editor.hints_text() == "-force действует только вместе с -update"  # noqa: RUF001
    assert editor.substitutions_text() == (
        "Подстановки: {база} {дата} {время} {версия} {группа}. "
        "Дата и время — момент старта сценария, общий для всех баз."
    )


def test_read_only_locks_every_field(qtbot: QtBot) -> None:
    editor, emitted = _editor(qtbot)
    editor.set_step(Step("/DumpIB", (r"D:\a.dt",)), read_only=True)
    field = editor.value_widget(0)
    assert field is not None and not field.isEnabled()
    assert not editor.overwrite_checkbox().isEnabled()
    editor.set_value(0, r"D:\b.dt")
    assert emitted == []


def test_unknown_command_is_reported(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    editor.set_step(Step("/NoSuchCommand", ("x",)))
    assert editor.title_text() == "/NoSuchCommand"
    assert editor.problems_text() == "команды нет в каталоге"


def test_command_picker_lists_groups_and_finds_by_description(qtbot: QtBot) -> None:
    picker = CommandPicker(CATALOG)
    qtbot.addWidget(picker)
    names = picker.command_names()
    assert len(names) == len(CATALOG.commands) and "/DumpIB" in names
    assert picker.chosen() is None and not picker.accept_button().isEnabled()

    picker.search("хранилищ")
    assert "/ConfigurationRepositoryUpdateCfg" in picker.command_names()
    assert "/DumpIB" not in picker.command_names()
    picker.search("")
    picker.select("/RestoreIB")
    assert picker.chosen() == "/RestoreIB" and picker.accept_button().isEnabled()
    assert "заменяет данные" in picker.description_text()
    assert picker.accept_button().autoDefault() is False


def test_set_step_from_a_changed_handler_is_safe(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    other = Step("/RestoreIB", (r"D:\z.dt",))
    editor.changed.connect(lambda _step: editor.set_step(other))
    editor.set_step(Step("/DumpIB", (None,)))
    field = editor.value_widget(0)
    assert isinstance(field, QLineEdit)
    field.setText(r"D:\a.dt")
    field.editingFinished.emit()
    # Эмитирующий виджет пережил обработчик: удаление отложено, не синхронное.
    assert shiboken6.isValid(field)
    qtbot.wait(10)  # отложенное удаление старых виджетов
    assert not shiboken6.isValid(field)
    assert editor.step() == other
    assert editor.title_text() == step_title(other, CATALOG)


def test_same_set_step_does_not_rebuild_fields(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot)
    editor.set_step(Step("/DumpIB", (r"D:\a.dt",)), sample=SAMPLE)
    before = editor.value_widget(0)
    editor.set_step(Step("/DumpIB", (r"D:\a.dt",)), sample=SAMPLE)
    assert editor.value_widget(0) is before
    editor.set_step(Step("/DumpIB", (r"D:\a.dt",)), read_only=True, sample=SAMPLE)
    assert editor.value_widget(0) is not before


def test_browse_ignores_bad_index_and_non_path_args(qtbot: QtBot) -> None:
    asked: list[str] = []

    def choose(_parent: QWidget, arg: ArgSpec, current: str) -> str:
        asked.append(current)
        return r"D:\x"

    editor, emitted = _editor(qtbot, choose_path=choose)
    step = Step("/ConfigurationRepositoryUpdateCfg", ("5",))
    editor.set_step(step)
    editor.browse(0)  # int
    editor.browse(99)
    editor.browse(-1)
    assert asked == [] and emitted == [] and editor.step() == step


def test_filter_drops_hidden_selection(qtbot: QtBot) -> None:
    picker = CommandPicker(CATALOG)
    qtbot.addWidget(picker)
    picker.select("/DumpIB")
    assert picker.accept_button().isEnabled()
    picker.search("хранилищ")
    assert picker.chosen() is None and not picker.accept_button().isEnabled()
    assert picker.description_text() == ""


def test_labels_sit_above_fields_and_the_path_shows_its_start(qtbot: QtBot) -> None:
    """В11: подпись над полем (мокап, стр. 290), путь — с начала, целиком в подсказке."""  # noqa: RUF002
    editor, _ = _editor(qtbot)
    path = r"D:\Backup\{база}\{база}_{дата}_{время}.dt"
    editor.set_step(Step("/DumpIB", (path,)))
    assert editor.form_layout().rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows
    edit = editor.value_widget(0)
    assert isinstance(edit, QLineEdit)
    assert edit.cursorPosition() == 0
    assert edit.toolTip() == path
    assert edit.objectName() == "MonoEdit"


def test_hints_and_problems_are_callouts(qtbot: QtBot) -> None:
    """Единообразие с замечаниями строки параметров (аудит 4.14)."""  # noqa: RUF002
    editor, _ = _editor(qtbot)
    editor.set_step(Step("/DumpIB"))
    assert editor.problem_list().levels() and set(editor.problem_list().levels()) == {"error"}
    editor.set_step(Step("/DumpConfigToFiles", (r"D:\src", None, None, None, "")))
    assert editor.hint_list().levels() == ["warning"]
    assert editor.hints_text() == "-force действует только вместе с -update"  # noqa: RUF001


def test_example_is_a_hint_and_substitutions_are_accented(qtbot: QtBot) -> None:
    """Мокап `.q` и `.subs code{color:acc}` (стр. 291–292)."""  # noqa: RUF002
    editor, _ = _editor(qtbot, palette=LIGHT)
    editor.set_step(Step("/DumpIB", (r"%USERPROFILE%\{база}.dt",)), sample=SAMPLE)
    assert editor.example_label().objectName() == "Hint"
    assert LIGHT.accent in editor.substitutions_label().text()
    # Показанный текст равен простой подсказке: оба собраны `_substitutions_line`.  # noqa: RUF003
    assert editor.substitutions_text() == SUBSTITUTIONS_HELP
    assert editor.substitutions_text().startswith("Подстановки: {база} {дата}")


def test_title_can_be_hidden_for_a_boxed_editor(qtbot: QtBot) -> None:
    editor, _ = _editor(qtbot, show_title=False)
    editor.set_step(Step("/DumpIB"))
    assert editor.title_label().isHidden()
    assert editor.title_text() == "Выгрузить информационную базу в файл .dt"
    # Финальное ревью плана Б, F7: метка заголовка — в раскладке редактора, не окно.
    shown, _ = _editor(qtbot)
    assert not shown.title_label().isHidden()
    assert shown.title_label().parentWidget() is shown


def test_substitutions_text_reads_the_shown_label(qtbot: QtBot) -> None:
    """Читает метку, а не константу: иначе тест сверял бы константу с константой."""  # noqa: RUF002
    editor, _ = _editor(qtbot)
    editor.substitutions_label().setText("<b>показано</b>")
    assert editor.substitutions_text() == "показано"
