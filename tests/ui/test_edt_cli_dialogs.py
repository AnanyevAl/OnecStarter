from PySide6.QtCore import Qt

from onecstarter.domain.edt_cli import ImportForm
from onecstarter.ui.edt.cli_import_dialog import CliImportDialog
from onecstarter.ui.edt.cli_validate_dialog import CliValidateDialog


class TestImportDialog:
    def test_existing_variant(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        assert dialog.existing_radio().isChecked() is True
        assert dialog.ok_button().isEnabled() is False
        dialog.existing_dir_edit().setText(r"D:\src\proj")
        assert dialog.ok_button().isEnabled() is True
        assert dialog.form() == ImportForm(existing_project_dir=r"D:\src\proj")

    def test_xml_variant_fields(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        dialog.xml_radio().setChecked(True)
        dialog.xml_dir_edit().setText(r"D:\xml")
        assert dialog.ok_button().isEnabled() is False  # нет каталога/имени
        dialog.project_name_edit().setText("ext")
        dialog.base_project_edit().setText("base")
        dialog.platform_version_edit().setText("8.3.24")
        dialog.build_checkbox().setChecked(True)
        assert dialog.ok_button().isEnabled() is True
        assert dialog.form() == ImportForm(
            configuration_files=r"D:\xml",
            project_name="ext",
            base_project_name="base",
            platform_version="8.3.24",
            build_after=True,
        )

    def test_variant_switch_clears_other_fields_from_form(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        dialog.existing_dir_edit().setText(r"D:\a")
        dialog.xml_radio().setChecked(True)
        dialog.xml_dir_edit().setText(r"D:\xml")
        dialog.project_dir_edit().setText(r"D:\new")
        assert dialog.form().existing_project_dir == ""
        assert dialog.error_text() == ""

    def test_single_quote_reports_error(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: "")
        qtbot.addWidget(dialog)
        dialog.existing_dir_edit().setText(r"D:\O'Reilly")
        assert dialog.ok_button().isEnabled() is False
        assert "Кавычка в значении недопустима" in dialog.error_text()

    def test_browse_fills_active_field(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliImportDialog(choose_directory=lambda: r"D:\picked")
        qtbot.addWidget(dialog)
        dialog.existing_browse().click()
        assert dialog.existing_dir_edit().text() == r"D:\picked"


PATHS = [r"D:\ws\conf", r"D:\ws\conf.ext"]


def _dirs_only(path: str) -> bool:
    """Фейк `os.path.exists`: каталоги есть, файла результата нет (M4 ревью:
    диалог проверяет и каталог результата, `exists=lambda p: False` его отвергал бы).
    """  # noqa: RUF002
    return not path.lower().endswith(".tsv")


class TestValidateDialog:
    def test_all_checked_and_default_file(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            PATHS, r"C:\Users\u\Documents", "validate-a-20260910-1200.tsv",
            choose_save=lambda initial: "", exists=_dirs_only,
        )
        qtbot.addWidget(dialog)
        assert dialog.selected_paths() == PATHS
        assert dialog.file_edit().text() == r"C:\Users\u\Documents\validate-a-20260910-1200.tsv"
        assert dialog.ok_button().isEnabled() is True

    def test_nothing_checked_disables_ok(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            PATHS, r"C:\d", "r.tsv", choose_save=lambda i: "", exists=_dirs_only
        )
        qtbot.addWidget(dialog)
        for row in range(2):
            dialog.list_widget().item(row).setCheckState(Qt.CheckState.Unchecked)
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == "Не выбран ни один проект"  # noqa: RUF001

    def test_existing_file_rejected(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            PATHS, r"C:\d", "r.tsv", choose_save=lambda i: "", exists=lambda p: True
        )
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == "Файл уже существует — CLI откажет; выберите другое имя"

    def test_browse_replaces_file(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            PATHS, r"C:\d", "r.tsv", choose_save=lambda i: r"E:\out\x.tsv", exists=_dirs_only
        )
        qtbot.addWidget(dialog)
        dialog.browse_button().click()
        assert dialog.result_file() == r"E:\out\x.tsv"

    def test_empty_paths_list(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            [], r"C:\d", "r.tsv", choose_save=lambda i: "", exists=_dirs_only
        )
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False

    def test_single_quote_in_path_reports_error(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog = CliValidateDialog(
            [r"D:\O'Reilly\conf"], r"C:\d", "r.tsv",
            choose_save=lambda i: "", exists=_dirs_only,
        )
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False
        assert "Кавычка в значении недопустима" in dialog.error_text()

    def test_missing_result_dir_rejected(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """M4 ревью: `Documents` может не существовать (OneDrive KFM) — CLI не создаст
        каталог для TSV; проверка каталога — тем же `exists`, что и файла."""
        seen: list[str] = []

        def exists(path: str) -> bool:
            seen.append(path)
            return False

        dialog = CliValidateDialog(
            PATHS, r"C:\nope\Documents", "r.tsv", choose_save=lambda i: "", exists=exists
        )
        qtbot.addWidget(dialog)
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == "Каталог результата не существует"
        assert r"C:\nope\Documents" in seen  # проверялся именно родитель файла
