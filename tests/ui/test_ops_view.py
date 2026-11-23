"""Раздел «Операции» (спека v4, §7.4): сценарии, шаги, предпросмотр, запуск."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QTextDocumentFragment
from pytestqt.qtbot import QtBot

from onecstarter.domain.operations import BUILTIN_SCENARIOS, BaseOutcome, BaseRef, Scenario, Step
from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.services.model import InfobaseItem
from onecstarter.services.operations_runner import BUSY_TEXT
from onecstarter.services.operations_store import OperationsData, load_operations
from onecstarter.ui.components import Box
from onecstarter.ui.ops.base_checklist import BaseListDialog
from onecstarter.ui.ops.command_picker import CommandPicker
from onecstarter.ui.ops.controller import OperationsController
from onecstarter.ui.ops.run_dialog import RunDialog
from onecstarter.ui.ops.view import (
    EFFECT_CHIPS,
    OperationsView,
    PreviewBase,
    StepRow,
    step_row,
    step_row_html,
    step_row_text,
)
from onecstarter.ui.theme import LIGHT
from tests.ui.ops_fakes import ScriptedRunner, dump_scenario, make_controller, target


def _view(
    qtbot: QtBot,
    tmp_path: Path,
    workspace_factory: Any,
    *,
    scenarios: tuple[Scenario, ...] = (),
    spawn: Callable[[Callable[[], None]], None] | None = None,
    **kwargs: Any,
) -> tuple[OperationsView, OperationsController, ScriptedRunner, list[InfobaseItem], list[str]]:
    workspace, _, _ = workspace_factory()
    items = workspace.items()
    bases = [item for item in items if not item.is_group][:2]
    targets = {base.key: target(base.key, base.name) for base in bases}
    extra = {} if spawn is None else {"spawn": spawn}
    controller, runner = make_controller(
        tmp_path, targets=targets, data=OperationsData(scenarios=scenarios), **extra
    )
    errors: list[str] = []
    preview_base = kwargs.pop(
        "preview_base",
        lambda key: PreviewBase(
            next(b.name for b in bases if b.key == key), "Клиенты", "8.3.27.2214", "Иванов"
        ),
    )
    view = OperationsView(
        controller,
        items=lambda: items,
        preview_base=preview_base,
        on_error=errors.append,
        now=lambda: datetime(2026, 11, 14, 9, 5, 7),
        **kwargs,
    )
    qtbot.addWidget(view)
    return view, controller, runner, bases, errors


def _current(view: OperationsView) -> Scenario:
    scenario = view.current()
    assert scenario is not None
    return scenario


def _step_of(view: OperationsView) -> Step:
    step = view.step_editor().step()
    assert step is not None
    return step


def _stored(tmp_path: Path) -> tuple[Scenario, ...]:
    return load_operations(tmp_path / "operations.json").scenarios


def test_list_shows_builtin_and_own_scenarios(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    own = dump_scenario(tmp_path)
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, scenarios=(own,))
    assert view.list_titles() == [
        "Заготовки",
        "Выгрузить в .dt",
        "Загрузить из .dt",
        "Выгрузить .cf",
        "Мои",
        "Ночной архив",
    ]
    assert view.scenario_ids() == [*(s.id for s in BUILTIN_SCENARIOS), "u1"]
    assert view.current() == BUILTIN_SCENARIOS[0]  # выбран первый


def test_builtin_is_read_only_and_copy_is_editable(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory)
    view.select_scenario("builtin:restore-dt")
    assert not view.name_edit().isEnabled()
    assert view.note_text() == "Заготовка: чтобы изменить, сделайте копию"
    assert view.step_texts() == [
        "1. Загрузить информационную базу из файла .dt — /RestoreIB · заменяет данные\n"
        "без параметров"
    ]
    view.select_step(0)
    widget = view.step_editor().value_widget(0)
    assert widget is not None and not widget.isEnabled()

    view.copy_current()

    copy = _current(view)
    assert copy.name == "Загрузить из .dt — копия" and not copy.builtin
    assert view.name_edit().isEnabled() and view.note_text() == ""
    assert _stored(tmp_path) == (copy,)


def test_new_scenario_rename_and_name_clash(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    view, _, _, _, errors = _view(qtbot, tmp_path, workspace_factory)
    view.add_scenario()
    assert _current(view).name == "Новый сценарий" and _stored(tmp_path)[0].id == "new1"

    view.rename("  Ночной архив ")
    assert _current(view).name == "Ночной архив" and _stored(tmp_path)[0].name == "Ночной архив"
    assert "Ночной архив" in view.list_titles()

    view.rename("выгрузить в .DT")  # занято заготовкой
    assert errors == ["Сценарий с именем «выгрузить в .DT» уже есть"]  # noqa: RUF001
    assert _current(view).name == "Ночной архив"
    assert view.name_edit().text() == "Ночной архив"  # поле вернулось к сохранённому
    view.rename("   ")
    assert _current(view).name == "Ночной архив" and len(errors) == 1  # пустое имя — без записи


def test_steps_are_added_edited_moved_and_removed(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    picks = iter(["/DumpIB", "/UpdateDBCfg", None])

    def pick(dialog: CommandPicker) -> bool:
        name = next(picks)
        if name is None:
            return False
        dialog.select(name)
        return True

    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, pick_command=pick)
    view.add_scenario()
    view.add_step()
    view.add_step()
    view.add_step()  # выбор отменён
    assert [step.command for step in _current(view).steps] == ["/DumpIB", "/UpdateDBCfg"]
    assert view.step_texts() == [
        "1. Выгрузить информационную базу в файл .dt — /DumpIB\nбез параметров",  # noqa: RUF001
        "2. Обновить конфигурацию базы данных — /UpdateDBCfg · меняет базу\nбез параметров",  # noqa: RUF001
    ]

    view.select_step(0)
    editor = view.step_editor()
    before = editor.value_widget(0)
    editor.set_value(0, r"D:\Backup\{база}.dt")
    assert _stored(tmp_path)[0].steps[0] == Step("/DumpIB", (r"D:\Backup\{база}.dt",))
    assert view.step_texts()[0].endswith(r"D:\Backup\{база}.dt")
    assert editor.value_widget(0) is before  # редактор не пересоздан после сохранения

    view.move_step(1)
    assert [step.command for step in _current(view).steps] == ["/UpdateDBCfg", "/DumpIB"]
    assert _step_of(view).command == "/DumpIB"  # выделение ушло вместе с шагом  # noqa: RUF003
    view.move_step(1)  # ниже некуда
    assert [step.command for step in _stored(tmp_path)[0].steps] == ["/UpdateDBCfg", "/DumpIB"]
    view.remove_step()
    assert [step.command for step in _stored(tmp_path)[0].steps] == ["/UpdateDBCfg"]


def test_bases_list_and_stop_flag_are_saved(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    chosen: list[list[str]] = []

    def choose(dialog: BaseListDialog) -> bool:
        chosen.append(dialog.checklist().checked_keys())
        for key in keys_to_check:
            dialog.checklist().set_checked(key, True)
        return True

    view, _, _, bases, _ = _view(qtbot, tmp_path, workspace_factory, choose_bases=choose)
    keys_to_check = [bases[0].key, bases[1].key]
    view.add_scenario()
    assert view.bases_text() == "" and _current(view).bases is None

    view.edit_bases()
    refs = (BaseRef(bases[0].key, bases[0].name), BaseRef(bases[1].key, bases[1].name))
    assert chosen == [[]] and _stored(tmp_path)[0].bases == refs
    assert view.bases_text() == f"{bases[0].name} · {bases[1].name}"

    view.edit_bases()
    assert chosen[1] == keys_to_check  # диалог открылся с сохранённым списком  # noqa: RUF003
    view.set_saved_bases(False)
    assert _stored(tmp_path)[0].bases is None and view.bases_text() == ""

    view.set_stop_on_error(False)
    assert _stored(tmp_path)[0].stop_on_error is False


def test_preview_shows_the_command_for_the_first_base_with_masked_passwords(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    workspace, _, _ = workspace_factory()
    first = next(item for item in workspace.items() if not item.is_group)
    scenario = Scenario(
        "u1",
        "Ночной архив",
        (Step("/DumpIB", (r"D:\Backup\{база}_{дата}.dt",)),),
        bases=(BaseRef(first.key, first.name),),
    )
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, scenarios=(scenario,))
    view.select_scenario("u1")
    assert view.preview_text() == ""  # шаг не выбран
    view.select_step(0)
    assert view.preview_title() == f"Команда шага 1 для «{first.name}» (пароли скрыты):"
    text = view.preview_text()
    assert text.startswith(f'1cv8.exe DESIGNER /IBName"{first.name}" /N"Иванов" /P***')
    assert "2026-11-14_090507_Ночной архив" in text and text.count("***") == 1
    assert view.step_editor().example_text().startswith(f"Для «{first.name}»: D:\\Backup\\")

    view.set_saved_bases(False)  # базы спрашиваются — пример на условном имени
    assert view.preview_title() == "Команда шага 1 для «Имя базы» (пароли скрыты):"
    assert '/IBName"Имя базы"' in view.preview_text() and "/N" not in view.preview_text()


def test_labels_with_user_text_are_plain_text(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Финальное ревью плана Б, F6: имя базы и команда шага — из файлов пользователя.

    `QLabel` с `AutoText` принял бы `<b>x</b>` за разметку: имя показалось бы жирным «x».
    """  # noqa: RUF002
    workspace, _, _ = workspace_factory()
    first = next(item for item in workspace.items() if not item.is_group)
    name = "<b>x</b>"
    scenario = Scenario(
        "u1",
        "Ночной архив",
        (Step("/DumpIB", (r"D:\Backup\{база}.dt",)), Step("/<i>Z</i>")),
        bases=(BaseRef(first.key, name),),
    )
    view, _, _, _, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(scenario,),
        preview_base=lambda _key: PreviewBase(name, "Клиенты", "8.3.27.2214", "Иванов"),
    )
    view.select_scenario("u1")
    view.select_step(0)
    editor = view.step_editor()
    shown = [view.bases_label(), view.preview_title_label(), editor.example_label()]
    assert all(name in label.text() for label in shown)
    view.select_step(1)
    shown += [view.editor_box().title_label(), editor.title_label()]
    assert all("<i>Z</i>" in label.text() for label in shown[3:])
    for label in shown:
        assert label.textFormat() == Qt.TextFormat.PlainText, label.text()


def test_remove_asks_and_builtin_cannot_be_removed(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    answers = iter([False, True])
    asked: list[str] = []

    def confirm(_parent: object, name: str) -> bool:
        asked.append(name)
        return next(answers)

    own = dump_scenario(tmp_path)
    view, _, _, _, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), confirm_remove=confirm
    )
    view.select_scenario("builtin:dump-dt")
    view.remove_current()
    assert asked == []  # заготовку не удаляют и не спрашивают
    view.select_scenario("u1")
    view.remove_current()
    assert asked == ["Ночной архив"] and view.current() == own
    view.remove_current()
    assert _stored(tmp_path) == () and view.current() == BUILTIN_SCENARIOS[0]


def test_failed_save_is_reported_and_rolled_back(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = dump_scenario(tmp_path)
    view, _, _, _, errors = _view(qtbot, tmp_path, workspace_factory, scenarios=(own,))
    view.select_scenario("u1")

    def refuse(path: Path, data: OperationsData) -> None:
        raise OSError("диск занят")

    monkeypatch.setattr("onecstarter.ui.ops.controller.save_operations", refuse)
    view.stop_checkbox().setChecked(False)  # правка, как её делает пользователь
    assert errors == ["Сценарий не сохранён: диск занят"]
    assert _current(view).stop_on_error is True and view.stop_checkbox().isChecked()


def test_builtin_cannot_be_edited_from_code(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    picked: list[int] = []

    def pick(dialog: CommandPicker) -> bool:
        picked.append(1)
        return False

    view, _, _, _, errors = _view(qtbot, tmp_path, workspace_factory, pick_command=pick)
    view.select_scenario("builtin:dump-dt")
    before = _current(view)
    view.set_stop_on_error(not before.stop_on_error)
    view.set_saved_bases(True)
    view.rename("Другое имя")
    view.add_step()
    view.select_step(0)
    view.move_step(1)
    view.remove_step()
    assert errors == [] and picked == []  # ни сообщений, ни окна выбора команды
    assert _current(view) == before and view.step_texts()
    assert view.stop_checkbox().isChecked() is before.stop_on_error
    assert _stored(tmp_path) == ()


def _accepting(dialog: RunDialog) -> bool:
    dialog.refresh_now()
    dialog.action_button().click()
    return dialog.outcome() is not None


def test_run_from_the_section_uses_the_saved_list_and_shows_progress(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    seen: list[list[str]] = []

    def run(dialog: RunDialog) -> bool:
        seen.append(dialog.checklist().checked_keys())
        return _accepting(dialog)

    workspace, _, _ = workspace_factory()
    first = next(item for item in workspace.items() if not item.is_group)
    scenario = Scenario(
        "u1",
        "Ночной архив",
        dump_scenario(tmp_path).steps,
        bases=(BaseRef(first.key, first.name), BaseRef("id:gone", "Розница старая")),
    )
    view, controller, runner, _, errors = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(scenario,), run_dialog=run
    )
    view.select_scenario("u1")

    view.run_button().click()

    assert errors == [] and seen == [[first.key, "id:gone"]]
    assert runner.run_calls[0]["keys"] == [first.key, "id:gone"]
    assert view.run_panel().cells()[0] == [first.name, "✓ 00:02 · 0", "готово"]
    assert view.run_panel().cells()[1][2] == "пропущена: база не найдена в списке"
    assert controller.history_count() == 1


def test_run_for_given_keys_and_remembering_the_list(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    def run(dialog: RunDialog) -> bool:
        dialog.remember_checkbox().setChecked(True)
        return _accepting(dialog)

    own = dump_scenario(tmp_path)
    view, _, runner, bases, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), run_dialog=run
    )
    view.request_run("u1", [bases[1].key, "id:unknown"])
    assert runner.run_calls[0]["keys"] == [bases[1].key]  # неизвестный ключ из меню отброшен
    assert _stored(tmp_path)[0].bases == (BaseRef(bases[1].key, bases[1].name),)
    view.request_run("нет такого", [bases[0].key])
    assert len(runner.run_calls) == 1


def test_cancelled_dialog_starts_nothing(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    view, _, runner, bases, errors = _view(
        qtbot, tmp_path, workspace_factory, run_dialog=lambda _dialog: False
    )
    view.request_run("builtin:dump-dt", [bases[0].key])
    assert runner.run_calls == [] and errors == []


def test_second_run_is_refused_while_one_is_active(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    pending: list[Callable[[], None]] = []
    opened: list[int] = []

    def run(dialog: RunDialog) -> bool:
        opened.append(1)
        dialog.refresh_now()
        pending.pop()()  # готовность
        dialog.action_button().click()
        return dialog.outcome() is not None

    own = dump_scenario(tmp_path)
    view, controller, _, bases, errors = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), spawn=pending.append, run_dialog=run
    )
    view.request_run("u1", [bases[0].key])
    assert controller.running and opened == [1]
    view.request_run("u1", [bases[0].key])
    assert errors == [BUSY_TEXT] and opened == [1]  # второе окно не открывалось


def test_retry_opens_the_dialog_for_failed_bases(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    seen: list[list[str]] = []

    def run(dialog: RunDialog) -> bool:
        seen.append(dialog.checklist().checked_keys())
        return _accepting(dialog)

    own = dump_scenario(tmp_path)
    view, _, runner, bases, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), run_dialog=run
    )
    runner.outcomes[bases[1].key] = BaseOutcome.FAILED
    view.request_run("u1", [bases[0].key, bases[1].key])
    runner.outcomes.clear()

    view.run_panel().retry_button().click()

    assert seen[1] == [bases[1].key]
    assert runner.run_calls[1]["keys"] == [bases[1].key]


def test_retry_uses_the_scenario_of_that_run_after_rename(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Решение 6: повтор берёт копию сценария прошлого запуска, а не текущую по id."""  # noqa: RUF002
    names: list[str] = []

    def run(dialog: RunDialog) -> bool:
        names.append(dialog._scenario.name)
        return _accepting(dialog)

    own = dump_scenario(tmp_path)
    view, _, runner, bases, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), run_dialog=run
    )
    runner.outcomes[bases[1].key] = BaseOutcome.FAILED
    view.request_run("u1", [bases[0].key, bases[1].key])
    runner.outcomes.clear()
    view.select_scenario("u1")
    view.rename("Совсем другое имя")
    assert _current(view).name == "Совсем другое имя"

    view.run_panel().retry_button().click()

    assert names == [own.name, own.name]
    assert runner.run_calls[1]["keys"] == [bases[1].key]


def test_retry_works_after_the_scenario_was_deleted(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    names: list[str] = []

    def run(dialog: RunDialog) -> bool:
        names.append(dialog._scenario.name)
        return _accepting(dialog)

    own = dump_scenario(tmp_path)
    view, controller, runner, bases, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), run_dialog=run
    )
    runner.outcomes[bases[1].key] = BaseOutcome.FAILED
    view.request_run("u1", [bases[0].key, bases[1].key])
    runner.outcomes.clear()
    assert controller.remove_scenario("u1") is None

    view.run_panel().retry_button().click()

    assert names == [own.name, own.name]
    assert runner.run_calls[1]["keys"] == [bases[1].key]


def test_run_dialog_is_forgotten_even_if_the_stub_raises(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    seen: list[RunDialog] = []

    def run(dialog: RunDialog) -> bool:
        seen.append(dialog)
        dialog.refresh_now()
        assert dialog._plan is not None  # план собран и держит данные запуска
        raise RuntimeError("сбой окна")

    own = dump_scenario(tmp_path)
    view, _, runner, bases, _ = _view(
        qtbot, tmp_path, workspace_factory, scenarios=(own,), run_dialog=run
    )
    with pytest.raises(RuntimeError):
        view.request_run("u1", [bases[0].key])
    assert runner.run_calls == []
    assert seen[0]._plan is None  # forget() вызван: план и пароли стёрты


def test_dialogs_do_not_accumulate_as_children_of_the_view(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    own = dump_scenario(tmp_path)
    view, _, _, bases, _ = _view(
        qtbot,
        tmp_path,
        workspace_factory,
        scenarios=(own,),
        run_dialog=_accepting,
        choose_bases=lambda _dialog: True,
        pick_command=lambda _dialog: False,
    )
    view.select_scenario("u1")
    view.request_run("u1", [bases[0].key])
    view.edit_bases()
    view.add_step()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for kind in (RunDialog, BaseListDialog, CommandPicker):
        assert view.findChildren(kind) == []


def test_controller_problem_is_shown(qtbot: QtBot, tmp_path: Path, workspace_factory: Any) -> None:
    _, controller, _, _, errors = _view(qtbot, tmp_path, workspace_factory)
    controller.problem.emit("История запуска не сохранена: диск занят")
    assert errors == ["История запуска не сохранена: диск занят"]


def test_scenarios_are_a_tree_with_bold_unselectable_groups(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """В12 (приёмка 21.11.2026): «Заготовки» и «Мои» читаются как группы."""  # noqa: RUF002
    own = dump_scenario(tmp_path)
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, scenarios=(own,), palette=LIGHT)
    tree = view.scenario_tree()
    found = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
    headers = [header for header in found if header is not None]
    assert len(headers) == len(found)
    assert [header.text(0) for header in headers] == ["Заготовки", "Мои"]
    for header in headers:
        assert header.font(0).bold()
        assert not header.flags() & Qt.ItemFlag.ItemIsSelectable
        assert header.foreground(0).color().name() == LIGHT.text_dim
        assert header.isExpanded()
    own_item = headers[1].child(0)
    assert own_item is not None
    assert own_item.text(0) == "Ночной архив"
    assert not tree.rootIsDecorated()
    assert tree.objectName() == "ScenarioTree"  # фон в боксе — по имени (задача 5)


def test_replacing_preset_carries_a_danger_chip(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап, экран 4 (стр. 261): «Загрузить из .dt» с чипом «заменяет»."""  # noqa: RUF002
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, palette=LIGHT)
    restore = view.scenario_item("builtin:restore-dt")
    assert restore is not None
    assert restore.text(1) == "заменяет"
    assert restore.foreground(1).color().name() == LIGHT.problem
    dump = view.scenario_item(BUILTIN_SCENARIOS[0].id)
    assert dump is not None and dump.text(1) == ""


def test_three_boxes_with_widths_and_a_primary_run(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап, экран 4 (стр. 254–290); В11, п. 1: правая колонка не уже 300 px."""  # noqa: RUF002
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory)
    view.resize(1280, 800)
    view.show()
    qtbot.waitExposed(view)
    titles = {box.title_label().text() for box in view.findChildren(Box)}
    assert titles == {"Сценарии", "Сценарий", "Свойства шага"}
    sizes = view.editor_splitter().sizes()
    assert sizes[0] <= 260 and sizes[2] >= 300
    assert view.run_button().property("role") == "primary"
    assert view.bases_label().objectName() == "Hint"


def test_step_rows_follow_the_mockup(qtbot: QtBot, tmp_path: Path, workspace_factory: Any) -> None:
    """Мокап `.step` (стр. 277–279): название жирным, команда и номер — dim, чип по эффекту."""  # noqa: RUF002
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, palette=LIGHT)
    view.select_scenario("builtin:restore-dt")
    label = view.step_row_label(0)
    assert label.textFormat() == Qt.TextFormat.RichText
    assert "<b>Загрузить информационную базу из файла .dt</b>" in label.text()
    assert f'color:{LIGHT.problem}">заменяет данные' in label.text()
    assert f'<i style="color:{LIGHT.text_dim}">без параметров</i>' in label.text()
    assert view.steps_list().objectName() == "Steps"
    assert view.step_texts() == [
        "1. Загрузить информационную базу из файла .dt — /RestoreIB · заменяет данные\n"
        "без параметров"
    ]


def test_stop_on_error_sits_in_the_step_buttons_row(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап (стр. 280): `＋ Шаг ↑ ↓ ✕ … ☑ остановить на первой ошибке` одной строкой."""  # noqa: RUF002
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory)
    view.resize(1280, 800)
    view.show()
    qtbot.waitExposed(view)
    stop, add = view.stop_checkbox(), view.add_step_button()
    assert abs(stop.geometry().center().y() - add.geometry().center().y()) <= 4
    assert stop.x() > add.x()


def test_step_preview_colours_the_base_and_keys(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап `.preview` (стр. 283): начало строки — dim, ключи — accent."""
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory, palette=LIGHT)
    view.select_scenario(BUILTIN_SCENARIOS[0].id)
    view.select_step(0)
    preview = view.preview_view()
    line = preview.toPlainText()
    assert line.startswith('1cv8.exe DESIGNER /IBName"Имя базы"')
    assert preview.format_at(0).foreground().color().name() == LIGHT.text_dim
    assert preview.format_at(line.index("/DumpIB")).foreground().color().name() == LIGHT.accent
    assert view.preview_text() == line


_BUILTIN_STEPS = [step for scenario in BUILTIN_SCENARIOS for step in scenario.steps]


def test_step_row_html_escapes_user_text(qapp: Any) -> None:
    """Финальное ревью плана Б, F4: имя, команда и пояснение шага — из файла сценария.

    Мутация — убрать `escape` у заголовка: `<b>` пользователя становится разметкой.
    """  # noqa: RUF002
    row = StepRow(1, "a<b>&c", "/X<y>", None, "<i>s</i>")
    html = step_row_html(row, LIGHT)
    shown = QTextDocumentFragment.fromHtml(html).toPlainText()
    for part in ("a<b>&c", "/X<y>", "<i>s</i>"):
        assert part in shown, part
    assert "a<b>" not in html and "<y>" not in html and "<i>s</i>" not in html


@pytest.mark.parametrize("step", _BUILTIN_STEPS, ids=lambda step: step.command)
def test_step_row_text_and_html_show_the_same_parts(qapp: Any, step: Step) -> None:
    """Предпроверка 3.4: строка для диктора и `step_texts()` и видимая — из одних частей."""
    row = step_row(1, step, load_cli_catalog())
    text = step_row_text(row)
    shown = QTextDocumentFragment.fromHtml(step_row_html(row, LIGHT)).toPlainText()
    parts = [str(row.number), row.title, row.command, row.summary]
    if row.effect is not None:
        parts.append(EFFECT_CHIPS[row.effect])
    for part in parts:
        assert part in text and part in shown, part


def test_editor_box_is_titled_by_the_step(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """Мокап (стр. 287): «Шаг 1 — Выгрузить информационную базу» в полосе бокса."""
    view, _, _, _, _ = _view(qtbot, tmp_path, workspace_factory)
    view.select_scenario(BUILTIN_SCENARIOS[0].id)
    assert view.editor_box().title_label().text() == "Свойства шага"
    view.select_step(0)
    assert view.editor_box().title_label().text() == (
        "Шаг 1 — Выгрузить информационную базу в файл .dt"
    )
    assert view.step_editor().title_label().isHidden()


def test_run_panel_starts_tall_enough_for_two_rows(
    qtbot: QtBot, tmp_path: Path, workspace_factory: Any
) -> None:
    """План В, Б7: панель хода получала ~136 px и при окне 900 — таблица в полстроки."""  # noqa: RUF002
    view, *_ = _view(qtbot, tmp_path, workspace_factory)
    view.resize(1239, 860)
    view.show()
    qtbot.waitExposed(view)
    assert view.run_panel().height() >= 230
