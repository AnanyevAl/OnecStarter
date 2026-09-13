"""EdtImportDialog: список кандидатов с галочками, все отмечены по умолчанию (спека §6)."""  # noqa: RUF002

from PySide6.QtCore import Qt

from onecstarter.domain.edt import EdtProject, ImportCandidate
from onecstarter.ui.edt.import_dialog import UNKNOWN_VERSION_MARK, EdtImportDialog

A = ImportCandidate(EdtProject("1", "(2025) А", r"D:\edt\a", edt_version="2025.2.6+4"), True)  # noqa: RUF001
B = ImportCandidate(EdtProject("2", "Б", r"D:\edt\b"), False)


def test_all_checked_by_default_with_columns(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtImportDialog([A, B])
    qtbot.addWidget(dialog)
    items = [dialog.list_widget().item(i) for i in range(2)]
    assert [i.checkState() for i in items] == [Qt.CheckState.Checked, Qt.CheckState.Checked]
    assert items[0].text() == "(2025) А — D:\\edt\\a — 2025.2.6+4"  # noqa: RUF001
    assert items[1].text() == f"Б — D:\\edt\\b — {UNKNOWN_VERSION_MARK}"
    assert dialog.selected() == [A, B]


def test_unchecked_excluded_and_none_disables_ok(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = EdtImportDialog([A, B])
    qtbot.addWidget(dialog)
    dialog.list_widget().item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected() == [B]
    dialog.list_widget().item(1).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected() == []
    assert dialog.ok_button().isEnabled() is False
