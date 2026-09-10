from onecstarter.ui.edt.group_dialog import EdtGroupDialog


def test_new_group_dialog(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtGroupDialog("", title="Новая группа")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Новая группа"
    assert dialog.ok_button().isEnabled() is False
    dialog.name_edit().setText("  2025 ")
    assert dialog.ok_button().isEnabled() is True
    assert dialog.name_text() == "2025"


def test_rename_dialog_prefills(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtGroupDialog("Розница", title="Переименование группы")
    qtbot.addWidget(dialog)
    assert dialog.name_edit().text() == "Розница"
    assert dialog.ok_button().isEnabled() is True
