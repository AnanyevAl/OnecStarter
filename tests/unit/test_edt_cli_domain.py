"""Домен CLI EDT: строки команд и командная строка 1cedtcli.exe (спека §14.2-14.3, факты §0-Д)."""

from pathlib import Path

import pytest

from onecstarter.domain.edt_cli import (
    CLI_ENCODING_ARGS,
    CliQuoteError,
    ImportForm,
    WorkspaceEntry,
    build_cli_command,
    cli_build_args,
    cli_import_args,
    cli_project_args,
    cli_validate_args,
    quote_cli_arg,
    workspace_projects,
)

CLI = Path(r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedtcli.exe")
JDK = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin")


class TestQuote:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (r"D:\edt\a", "'D:\\edt\\a'"),
            (r"D:\edt\a b\проект", "'D:\\edt\\a b\\проект'"),
            ("name", "'name'"),
        ],
    )
    def test_single_quotes(self, value: str, expected: str) -> None:
        assert quote_cli_arg(value) == expected

    def test_single_quote_inside_rejected(self) -> None:
        with pytest.raises(CliQuoteError):
            quote_cli_arg("O'Reilly")


def test_fixed_commands() -> None:
    assert cli_build_args() == "build --yes"  # [Д] без --yes ждёт подтверждения
    assert cli_project_args() == "project"


class TestImportArgs:
    def test_existing_project(self) -> None:
        assert cli_import_args(ImportForm(existing_project_dir=r"D:\src\proj")) == (
            "import --project 'D:\\src\\proj'"
        )

    def test_xml_into_project_dir_minimal(self) -> None:
        form = ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\edt\ws\new")
        assert cli_import_args(form) == (
            "import --configuration-files 'D:\\xml' --project 'D:\\edt\\ws\\new'"
        )

    def test_xml_into_named_project_full(self) -> None:
        form = ImportForm(
            configuration_files=r"D:\xml",
            project_name="ext_a",
            base_project_name="base",
            platform_version="8.3.24",
            build_after=True,
        )
        assert cli_import_args(form) == (
            "import --configuration-files 'D:\\xml' --project-name 'ext_a' "
            "--base-project-name 'base' --version 8.3.24 --build"
        )

    def test_both_variants_rejected(self) -> None:
        with pytest.raises(ValueError, match="один вариант"):
            cli_import_args(ImportForm(existing_project_dir=r"D:\a", configuration_files=r"D:\xml"))

    def test_xml_without_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="каталог или имя"):
            cli_import_args(ImportForm(configuration_files=r"D:\xml"))

    def test_xml_with_both_targets_rejected(self) -> None:
        with pytest.raises(ValueError, match="каталог или имя"):
            cli_import_args(
                ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\p", project_name="n")
            )

    def test_empty_form_rejected(self) -> None:
        with pytest.raises(ValueError):
            cli_import_args(ImportForm())

    def test_bad_platform_version_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"8\.3\.x"):
            cli_import_args(
                ImportForm(configuration_files=r"D:\xml", project_name="n", platform_version="8;3")
            )


class TestValidateArgs:
    def test_single_path(self) -> None:
        assert cli_validate_args([r"D:\ws\p"], r"D:\out\r.tsv") == (
            "validate --project-list 'D:\\ws\\p' --file 'D:\\out\\r.tsv'"
        )

    def test_several_paths_space_separated(self) -> None:
        # [?] спека §0-Д: разделитель списка — эксперимент 6;
        # константа _LIST_SEPARATOR в одном месте
        assert cli_validate_args([r"D:\ws\a", r"D:\ws\b c"], r"D:\r.tsv") == (
            "validate --project-list 'D:\\ws\\a' 'D:\\ws\\b c' --file 'D:\\r.tsv'"
        )

    def test_empty_paths_rejected(self) -> None:
        with pytest.raises(ValueError):
            cli_validate_args([], r"D:\r.tsv")


class TestWorkspaceProjects:
    ENTRIES = (
        WorkspaceEntry(".metadata", r"D:\ws\.metadata", False),
        WorkspaceEntry("conf", r"D:\ws\conf", True),
        WorkspaceEntry("conf.ext", r"D:\ws\conf.ext", True),
        WorkspaceEntry("Серверы", r"D:\ws\Серверы", True),
        WorkspaceEntry("junk", r"D:\ws\junk", False),
    )

    def test_only_dirs_with_dot_project(self) -> None:
        expected = [r"D:\ws\conf", r"D:\ws\conf.ext", r"D:\ws\Серверы"]
        assert workspace_projects(self.ENTRIES, "") == expected

    def test_project_dir_outside_added_first(self) -> None:
        assert workspace_projects(self.ENTRIES, r"E:\git\repo")[0] == r"E:\git\repo"

    def test_project_dir_inside_not_duplicated(self) -> None:
        result = workspace_projects(self.ENTRIES, r"d:\WS\conf")
        assert result.count(r"D:\ws\conf") == 1
        assert r"d:\WS\conf" not in result


class TestBuildCliCommand:
    def test_order_command_before_vmargs_with_encoding(self) -> None:
        command = build_cli_command(
            CLI, r"D:\edt\ws", "build --yes", JDK, "-Xmx8192m -Dx=1", "-Xmx4g"
        )
        assert command.executable == CLI
        assert command.arguments == (
            f'-data "D:\\edt\\ws" -command "build --yes" -vm "{JDK}" --launcher.appendVmargs '
            f"-vmargs -Xmx8192m -Dx=1 -Djava.library.path= -Xmx4g {CLI_ENCODING_ARGS}"
        )

    def test_empty_vm_args(self) -> None:
        command = build_cli_command(CLI, r"D:\ws", "project", JDK, "", "")
        assert command.arguments == (
            f'-data "D:\\ws" -command "project" -vm "{JDK}" --launcher.appendVmargs '
            f"-vmargs -Djava.library.path= {CLI_ENCODING_ARGS}"
        )

    def test_command_with_single_quotes_survives_double_quoting(self) -> None:
        command = build_cli_command(CLI, r"D:\ws", "import --project 'D:\\a b'", JDK, "", "")
        assert '-command "import --project \'D:\\a b\'"' in command.arguments
