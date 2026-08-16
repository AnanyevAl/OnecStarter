"""Диалог группы: создание, переименование/перенос (задача 12)."""

from typing import Any

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui.dialogs.group import GroupDialog


def _group_item(name: str, folder: str = "/", connect: str | None = None) -> InfobaseItem:
    return InfobaseItem(
        key="grp:x", name=name, folder=folder, is_group=True, connect=connect,
        kind=ConnectKind.UNKNOWN, requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id=None,
    )


def test_for_new_dialog_starts_with_empty_name(qtbot: Any) -> None:
    dialog = GroupDialog.for_new(["/", "Клиенты"])
    qtbot.addWidget(dialog)
    assert dialog.name_text() == ""
    assert dialog.parent_path() == "/"


def test_for_new_dialog_preselects_default_folder(qtbot: Any) -> None:
    """Создание подгруппы из меню группы: родитель предложен сразу, не корень."""
    dialog = GroupDialog.for_new(["/", "Клиенты"], default_folder="Клиенты")
    qtbot.addWidget(dialog)
    assert dialog.parent_path() == "Клиенты"


def test_rename_dialog_starts_with_existing_name_and_folder(qtbot: Any) -> None:
    item = _group_item("Розница", folder="/Клиенты")
    dialog = GroupDialog(item, ["/", "Клиенты", "Клиенты/Розница"])
    qtbot.addWidget(dialog)
    assert dialog.name_text() == "Розница"
    assert dialog.parent_path() == "Клиенты"


def test_ok_cancel_button_labels_are_russian(qtbot: Any) -> None:
    """Без QTranslator стандартные подписи Qt пришли бы по-английски (задача 8)."""
    dialog = GroupDialog.for_new(["/"])
    qtbot.addWidget(dialog)
    assert dialog.button_labels() == ["ОК", "Отмена"]  # noqa: RUF001


def test_set_name_and_set_parent_path_drive_the_widgets(qtbot: Any) -> None:
    dialog = GroupDialog.for_new(["/", "Клиенты"])
    qtbot.addWidget(dialog)
    dialog.set_name("Новая")
    dialog.set_parent_path("Клиенты")
    assert dialog.name_text() == "Новая"
    assert dialog.parent_path() == "Клиенты"


def test_set_parent_path_rejects_a_path_not_offered(qtbot: Any) -> None:
    dialog = GroupDialog.for_new(["/"])
    qtbot.addWidget(dialog)
    try:
        dialog.set_parent_path("Нет такой")
    except ValueError:
        pass
    else:
        raise AssertionError("ожидался ValueError на пути, которого нет в списке")


def test_accept_rejects_empty_name_without_closing(qtbot: Any, monkeypatch: Any) -> None:
    # QMessageBox.warning подменяется на no-op: настоящее модальное окно
    # блокировало бы офскрин-тест тем же способом, что и QDialog.exec() —
    # тот же приём, что у InfobaseDialog  # noqa: RUF003
    # (test_accept_is_blocked_when_a_violation_is_present). Круг правок 1,  # noqa: RUF003
    # замечание 3: аргументы вызова записываются, а не отбрасываются, —  # noqa: RUF003
    # реализация, молча вернувшая управление без объяснения, тоже прошла бы
    # старую версию теста (только `result() == 0`).
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        "onecstarter.ui.dialogs.group.QMessageBox.warning",
        lambda *args, **kwargs: calls.append(args),
    )
    dialog = GroupDialog.for_new(["/"])
    qtbot.addWidget(dialog)
    dialog.set_name("   ")
    dialog._on_accept()
    assert dialog.result() == 0  # QDialog.DialogCode.Rejected по умолчанию — ещё не принят
    assert len(calls) == 1
    assert "пуст" in calls[0][-1].casefold()


def test_accept_rejects_a_name_with_a_slash(qtbot: Any, monkeypatch: Any) -> None:
    """Имя группы не может содержать «/» — этот символ разделяет уровни пути.

    Круг правок 1, замечание 3: как и у соседнего теста, объяснение
    проверяется по факту вызова `QMessageBox.warning`, а не только по
    результату `_on_accept`.
    """  # noqa: RUF002
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        "onecstarter.ui.dialogs.group.QMessageBox.warning",
        lambda *args, **kwargs: calls.append(args),
    )
    dialog = GroupDialog.for_new(["/"])
    qtbot.addWidget(dialog)
    dialog.set_name("Старое/Новое")
    dialog._on_accept()
    assert dialog.result() == 0
    assert len(calls) == 1
    assert "/" in calls[0][-1]


def test_accept_with_a_valid_name_accepts_the_dialog(qtbot: Any) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = GroupDialog.for_new(["/"])
    qtbot.addWidget(dialog)
    dialog.set_name("Новая группа")
    dialog._on_accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


# -- Задача 13: секция с пустым Connect= (обязательство 4 блока Б) ---------  # noqa: RUF003


def test_degraded_group_dialog_shows_the_connect_warning(qtbot: Any) -> None:
    """Диалог на секции с пустым Connect= предупреждает до попытки записи.

    [Ф] T-05.6: первая же перезапись платформы удалит Connect= и вычистит
    Version у такой секции — пользователь не узнает об этом иначе.

    Круг правок 1 ревью задачи 13: `warning_text()` доказывает лишь, что
    QLabel держит правильный текст, — виджет, не попавший в раскладку
    диалога, тоже мог бы его держать и остаться невидимым. `warning_shown()`
    проверяет членство в `layout()`, то есть то, что диалог реально рисует.
    """  # noqa: RUF002
    item = _group_item("Секция", connect="")
    dialog = GroupDialog(item, ["/"])
    qtbot.addWidget(dialog)
    assert dialog.warning_shown()
    assert "вычистит Version" in dialog.warning_text()


def test_ordinary_group_dialog_has_no_connect_warning(qtbot: Any) -> None:
    """Настоящая группа (connect is None) не несёт чужого предупреждения.

    Круг правок 1 ревью задачи 13: закреплено и то, что метка не в
    раскладке, а не только то, что её текст пуст, — см. соседний тест.
    """  # noqa: RUF002
    dialog = GroupDialog(_group_item("Секция"), ["/"])
    qtbot.addWidget(dialog)
    assert not dialog.warning_shown()
    assert dialog.warning_text() == ""


def test_new_group_dialog_has_no_connect_warning(qtbot: Any) -> None:
    """Диалог создания новой группы: нет исходной секции — нечего предупреждать."""
    dialog = GroupDialog.for_new(["/"])
    qtbot.addWidget(dialog)
    assert not dialog.warning_shown()
    assert dialog.warning_text() == ""
