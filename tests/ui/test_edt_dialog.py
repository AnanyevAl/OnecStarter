"""Диалог записи EDT: поля, фасады vm_args, версия не из списка, проверки (спека §7)."""

from pathlib import Path

from onecstarter.domain.edt import EdtInstallation, EdtProject
from onecstarter.ui.edt.dialog import (
    HEAP_CHOICES,
    NOT_INSTALLED_MARK,
    DialogDefaults,
    EdtProjectDialog,
)

JDK = Path(r"C:\jdk17\bin")
INSTALLED = [
    EdtInstallation("2026.1.2+2", Path(r"C:\e26\1cedt.exe"), JDK, "", 17, "products.json"),
    EdtInstallation("2025.2.6+4", Path(r"C:\e25\1cedt.exe"), None, "", 17, ""),
]
DEFAULTS = DialogDefaults(max_heap_mb=8192, language="", group_id=None)


def _new(qtbot, choose: str = "") -> EdtProjectDialog:  # type: ignore[no-untyped-def]
    dialog = EdtProjectDialog(None, INSTALLED, defaults=DEFAULTS, choose_directory=lambda: choose)
    qtbot.addWidget(dialog)
    return dialog


def test_new_dialog_prefills_defaults(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    assert dialog.windowTitle() == "Новый проект EDT"
    assert dialog.heap_combo().currentText() == "8192"
    assert dialog.language_combo().currentData() == ""
    assert [dialog.version_combo().itemText(i) for i in range(dialog.version_combo().count())] == [
        "2026.1.2+2",
        "2025.2.6+4",
    ]
    assert dialog.ok_button().isEnabled() is False
    assert dialog.jvm_note().text() == f"JVM установки: {JDK} (products.json)"


def test_result_project_joins_vm_args(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("Розница")
    dialog.workspace_edit().setText(r"D:\edt\retail")
    dialog.project_dir_edit().setText(r"D:\edt\retail\retail")
    dialog.heap_combo().setCurrentText("4096")
    dialog.language_combo().setCurrentIndex(1)  # ru
    dialog.extra_edit().setText("-Dx=1")
    assert dialog.ok_button().isEnabled() is True
    project = dialog.result_project()
    assert project == EdtProject(
        id="",
        name="Розница",
        workspace=r"D:\edt\retail",
        project_dir=r"D:\edt\retail\retail",
        edt_version="2026.1.2+2",
        jvm_dir="",
        vm_args="-Dx=1 -Xmx4096m -Duser.language=ru",
        group_id=None,
    )


def test_empty_heap_means_no_xmx(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText(r"D:\a")
    dialog.heap_combo().setCurrentText("")
    assert dialog.result_project().vm_args == ""


def test_garbage_heap_disables_ok(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText(r"D:\a")
    dialog.heap_combo().setCurrentText("много")
    assert dialog.ok_button().isEnabled() is False
    assert dialog.error_text() == "Память — целое число мегабайт"


def test_relative_workspace_disables_ok(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot)
    dialog.name_edit().setText("a")
    dialog.workspace_edit().setText(r"edt\a")
    assert dialog.ok_button().isEnabled() is False
    assert dialog.error_text() == "Путь workspace должен быть абсолютным"


def test_edit_splits_existing_vm_args_and_keeps_group(qtbot) -> None:  # type: ignore[no-untyped-def]
    project = EdtProject(
        id="p1",
        name="Розница",
        workspace=r"D:\edt\retail",
        edt_version="2025.2.6+4",
        jvm_dir=r"D:\my\bin",
        vm_args="-Dnative=true -Xmx12288m -Duser.language=en",
        group_id="g1",
    )
    dialog = EdtProjectDialog(project, INSTALLED, defaults=DEFAULTS, choose_directory=lambda: "")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Проект EDT — Розница"
    assert dialog.heap_combo().currentText() == "12288"
    assert dialog.language_combo().currentData() == "en"
    assert dialog.extra_edit().text() == "-Dnative=true"
    assert dialog.jvm_edit().text() == r"D:\my\bin"
    assert dialog.version_combo().currentText() == "2025.2.6+4"
    assert dialog.jvm_note().text() == "JVM установки: не найдена"
    result = dialog.result_project()
    assert result.id == "p1"
    assert result.group_id == "g1"
    assert result.vm_args == "-Dnative=true -Xmx12288m -Duser.language=en"


def test_unknown_version_stays_selectable_with_mark(qtbot) -> None:  # type: ignore[no-untyped-def]
    project = EdtProject(id="p1", name="Старая", workspace=r"D:\a", edt_version="2024.2.6+7")
    dialog = EdtProjectDialog(project, INSTALLED, defaults=DEFAULTS, choose_directory=lambda: "")
    qtbot.addWidget(dialog)
    assert dialog.version_combo().currentText() == "2024.2.6+7" + NOT_INSTALLED_MARK
    assert dialog.result_project().edt_version == "2024.2.6+7"


def test_browse_fills_workspace(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot, choose=r"D:\picked")
    dialog.workspace_browse().click()
    assert dialog.workspace_edit().text() == r"D:\picked"


def test_browse_cancel_keeps_field(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _new(qtbot, choose="")
    dialog.workspace_edit().setText(r"D:\keep")
    dialog.workspace_browse().click()
    assert dialog.workspace_edit().text() == r"D:\keep"


def test_heap_choices_listed() -> None:
    assert HEAP_CHOICES == (2048, 4096, 8192, 12288, 16384)
