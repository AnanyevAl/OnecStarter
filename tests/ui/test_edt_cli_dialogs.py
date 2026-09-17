import pytest
from PySide6.QtCore import Qt

from onecstarter.domain.edt_cli import ImportForm, ProjectCandidate, WorkspaceEntry
from onecstarter.ui.edt.cli_import_dialog import (
    IN_WORKSPACE_SUFFIX,
    NO_DIR,
    NONE_SELECTED,
    NOT_FOUND,
    CliImportDialog,
)
from onecstarter.ui.edt.cli_validate_dialog import CliValidateDialog

CANDIDATES = [
    ProjectCandidate(r"D:\repo\src\cf", "src/cf"),
    ProjectCandidate(r"D:\repo\src\cfe_a", "src/cfe_a"),
    ProjectCandidate(r"D:\repo\src\cfe_b", "src/cfe_b"),
]
ENTRIES = [WorkspaceEntry("cfe_a", r"D:\repo\src\cfe_a", True)]


class ScanSpy:
    def __init__(self, result: list[ProjectCandidate]) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, root: str) -> list[ProjectCandidate]:
        self.calls.append(root)
        return list(self.result)


def _dialog(qtbot, project_dir: str = r"D:\repo", scan: ScanSpy | None = None, **kwargs):  # type: ignore[no-untyped-def]
    spy = scan if scan is not None else ScanSpy(CANDIDATES)
    kwargs.setdefault("is_dir", lambda p: True)
    kwargs.setdefault("choose_directory", lambda: "")
    dialog = CliImportDialog(project_dir, ENTRIES, scan=spy, **kwargs)
    qtbot.addWidget(dialog)
    return dialog, spy


class TestImportDialog:
    def test_prefilled_dir_scanned_on_open(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot)
        assert dialog.windowTitle() == "Импортировать проекты (CLI EDT)"
        assert dialog.existing_dir_edit().text() == r"D:\repo"
        assert spy.calls == [r"D:\repo"]
        items = [dialog.list_widget().item(i) for i in range(dialog.list_widget().count())]
        assert [item.text() for item in items] == [
            "src/cf", "src/cfe_a" + IN_WORKSPACE_SUFFIX, "src/cfe_b"
        ]
        assert [item.checkState() for item in items] == [
            Qt.CheckState.Checked, Qt.CheckState.Unchecked, Qt.CheckState.Checked
        ]
        assert not items[1].flags() & Qt.ItemFlag.ItemIsEnabled
        assert not items[1].flags() & Qt.ItemFlag.ItemIsUserCheckable
        assert items[0].toolTip() == r"D:\repo\src\cf"
        assert dialog.status_text() == "Найдено 3, уже в рабочей области 1"
        assert dialog.ok_button().isEnabled() is True
        assert dialog.form() == ImportForm(
            existing_project_dirs=(r"D:\repo\src\cf", r"D:\repo\src\cfe_b")
        )

    def test_bound_project_never_in_form(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        # Мутационная проверка: mark_in_workspace → всегда False должен уронить этот тест
        dialog, _ = _dialog(qtbot)
        dialog.select_all_button().click()
        assert r"D:\repo\src\cfe_a" not in dialog.selected_paths()

    def test_empty_project_dir_no_scan(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot, project_dir="")
        assert spy.calls == []
        assert dialog.existing_dir_edit().placeholderText() == (
            "каталог с проектами EDT, например клон репозитория"  # noqa: RUF001
        )
        assert dialog.status_text() == ""
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == NONE_SELECTED

    def test_browse_rescans(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot, project_dir="", choose_directory=lambda: r"D:\picked")
        dialog.existing_browse().click()
        assert dialog.existing_dir_edit().text() == r"D:\picked"
        assert spy.calls == [r"D:\picked"]
        assert dialog.list_widget().count() == 3

    def test_editing_finished_rescans(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, spy = _dialog(qtbot, project_dir="")
        dialog.existing_dir_edit().setText(r"D:\typed")
        assert spy.calls == []  # не на каждый символ
        dialog.existing_dir_edit().editingFinished.emit()
        assert spy.calls == [r"D:\typed"]

    def test_select_all_and_none_skip_bound(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)
        dialog.select_none_button().click()
        assert dialog.selected_paths() == []
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == NONE_SELECTED
        dialog.select_all_button().click()
        assert dialog.selected_paths() == [r"D:\repo\src\cf", r"D:\repo\src\cfe_b"]
        assert dialog.list_widget().item(1).checkState() == Qt.CheckState.Unchecked

    def test_unchecked_item_excluded_in_order(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)
        dialog.list_widget().item(0).setCheckState(Qt.CheckState.Unchecked)
        assert dialog.form().existing_project_dirs == (r"D:\repo\src\cfe_b",)

    def test_no_projects_status(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, scan=ScanSpy([]))
        assert dialog.status_text() == NOT_FOUND
        assert dialog.ok_button().isEnabled() is False

    def test_missing_dir_status(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, scan=ScanSpy([]), is_dir=lambda p: False)
        assert dialog.status_text() == NO_DIR
        assert dialog.ok_button().isEnabled() is False

    def test_quote_in_candidate_path_reports_error(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, scan=ScanSpy([ProjectCandidate(r"D:\O'Reilly\p", "p")]))
        assert dialog.ok_button().isEnabled() is False
        assert "Кавычка в значении недопустима" in dialog.error_text()

    def test_xml_variant_fields(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot, project_dir="")
        dialog.xml_radio().setChecked(True)
        assert dialog.list_widget().isEnabled() is False
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

    def test_variant_switch_drops_projects_from_form(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)
        dialog.xml_radio().setChecked(True)
        dialog.xml_dir_edit().setText(r"D:\xml")
        dialog.project_dir_edit().setText(r"D:\new")
        assert dialog.form().existing_project_dirs == ()
        assert dialog.error_text() == ""

    def test_scan_failure_leaves_list_responsive(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        dialog, _ = _dialog(qtbot)

        def broken(root: str) -> list[ProjectCandidate]:
            raise RuntimeError("scan")

        dialog._scan = broken  # подмена точки инъекции после открытия
        dialog.existing_dir_edit().setText(r"D:\other")
        # Не editingFinished.emit(): PySide6 вызывает слот синхронно, но исключение  # noqa: RUF003
        # из слота Qt перехватывает своим хуком (печатает и гасит) — pytest.raises
        # его не увидит. Зовём _rescan() напрямую — тот же код пути.  # noqa: RUF003
        with pytest.raises(RuntimeError, match="scan"):
            dialog._rescan()
        assert dialog.list_widget().signalsBlocked() is False
        dialog.select_none_button().click()
        assert dialog.ok_button().isEnabled() is False
        assert dialog.error_text() == NONE_SELECTED


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
