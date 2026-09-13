"""Домен CLI EDT: строки команд и командная строка 1cedtcli.exe (спека §14.2-14.3, факты §0-Д)."""

from pathlib import Path

import pytest

from onecstarter.domain.edt_cli import (
    CliQuoteError,
    ImportForm,
    WorkspaceEntry,
    build_cli_command,
    cli_build_args,
    cli_import_args,
    cli_project_args,
    cli_validate_args,
    location_blob,
    parse_project_location,
    quote_cli_arg,
    workspace_projects,
    wrap_console_utf8,
)
from onecstarter.domain.launch import LaunchCommand

CLI = Path(r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedtcli.exe")
JDK = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin")


class TestQuote:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (r"D:\edt\a", "'D:/edt/a'"),  # обратные слэши → прямые ([Ф] Э6: иначе код 204)
            (r"D:\edt\a b\проект", "'D:/edt/a b/проект'"),
            ("D:/edt/a", "'D:/edt/a'"),
            (r"\\server\share\ws", "'//server/share/ws'"),
            ("name", "'name'"),
        ],
    )
    def test_single_quotes(self, value: str, expected: str) -> None:
        assert quote_cli_arg(value) == expected

    @pytest.mark.parametrize(
        ("value", "quote"),
        [
            ("O'Reilly", "'"),  # одинарная — экранирование Gogo не проверялось
            ('conf "v2"', '"'),  # двойная разорвёт внешние кавычки -command "…" (M3 ревью)
            ('D:\\ws\\"a', '"'),
        ],
    )
    def test_quote_inside_rejected(self, value: str, quote: str) -> None:
        with pytest.raises(CliQuoteError, match="Кавычка в значении недопустима") as excinfo:
            quote_cli_arg(value)
        assert value in str(excinfo.value)
        assert quote in value

    def test_percent_rejected(self) -> None:
        # Вся команда идёт через cmd.exe (Э6: chcp 65001 до 1cedtcli.exe), а cmd  # noqa: RUF003
        # раскрывает %ИМЯ% даже внутри кавычек — молчаливая подмена хуже отказа.
        with pytest.raises(CliQuoteError, match="%"):
            quote_cli_arg(r"D:\ws\%TEMP%")


def test_fixed_commands() -> None:
    assert cli_build_args() == "build --yes"  # [Д] без --yes ждёт подтверждения
    assert cli_project_args() == "project"


class TestImportArgs:
    def test_existing_project(self) -> None:
        assert cli_import_args(ImportForm(existing_project_dir=r"D:\src\proj")) == (
            "import --project 'D:/src/proj'"
        )

    def test_xml_into_project_dir_minimal(self) -> None:
        form = ImportForm(configuration_files=r"D:\xml", project_dir=r"D:\edt\ws\new")
        assert cli_import_args(form) == (
            "import --configuration-files 'D:/xml' --project 'D:/edt/ws/new'"
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
            "import --configuration-files 'D:/xml' --project-name 'ext_a' "
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
        # Скобки и для одного пути: `['p']` принят с кодом 0 (Э6, 13.09.2026)  # noqa: RUF003
        assert cli_validate_args([r"D:\ws\p"], r"D:\out\r.tsv") == (
            "validate --project-list ['D:/ws/p'] --file 'D:/out/r.tsv'"
        )

    def test_several_paths_gogo_list(self) -> None:
        # [Ф] Э6: несколько путей — список Gogo в квадратных скобках; через пробел
        # без скобок CLI отвечает кодом 204 «Не найден вариант вызова команды»  # noqa: RUF003
        assert cli_validate_args([r"D:\ws\a", r"D:\ws\b c"], r"D:\r.tsv") == (
            "validate --project-list ['D:/ws/a' 'D:/ws/b c'] --file 'D:/r.tsv'"
        )

    def test_empty_paths_rejected(self) -> None:
        with pytest.raises(ValueError):
            cli_validate_args([], r"D:\r.tsv")


class TestWorkspaceProjects:
    ENTRIES = (
        WorkspaceEntry("gone", r"D:\nowhere\gone", False),  # в реестре есть, каталога нет
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
    def test_order_command_before_vmargs(self) -> None:
        # Без -D…encoding: обёртка 1cedtcli.exe дописывает свой -Dfile.encoding
        # после наших -vmargs (Э6) — флаги JVM кодировку не меняют
        command = build_cli_command(
            CLI, r"D:\edt\ws", "build --yes", JDK, "-Xmx8192m -Dx=1", "-Xmx4g"
        )
        assert command.executable == CLI
        assert command.arguments == (
            f'-data "D:\\edt\\ws" -command "build --yes" -vm "{JDK}" --launcher.appendVmargs '
            "-vmargs -Xmx8192m -Dx=1 -Djava.library.path= -Xmx4g"
        )

    def test_empty_vm_args(self) -> None:
        command = build_cli_command(CLI, r"D:\ws", "project", JDK, "", "")
        assert command.arguments == (
            f'-data "D:\\ws" -command "project" -vm "{JDK}" --launcher.appendVmargs '
            "-vmargs -Djava.library.path="
        )

    def test_command_with_single_quotes_survives_double_quoting(self) -> None:
        command = build_cli_command(CLI, r"D:\ws", "import --project 'D:/a b'", JDK, "", "")
        assert '-command "import --project \'D:/a b\'"' in command.arguments


class TestWrapConsoleUtf8:
    COMSPEC = Path(r"C:\Windows\System32\cmd.exe")

    def test_chcp_before_cli_in_hidden_console(self) -> None:
        # [Ф] Э6: 1cedtcli.exe берёт кодовую страницу консоли в -Dfile.encoding
        # ребёнка 1cedtc.exe; `chcp 65001` в той же скрытой консоли даёт UTF-8.
        # cmd снимает первую и последнюю кавычку после /c — внутренняя строка цела.
        inner = LaunchCommand(CLI, '-data "D:\\ws" -command "project" -vm "C:\\j\\bin"')
        wrapped = wrap_console_utf8(inner, self.COMSPEC)
        assert wrapped.executable == self.COMSPEC
        assert wrapped.arguments == (
            '/d /v:off /c "chcp 65001 >nul & '
            f'"{CLI}" -data "D:\\ws" -command "project" -vm "C:\\j\\bin""'
        )
        assert wrapped.command_line.startswith(f'"{self.COMSPEC}" /d /v:off /c "chcp 65001')

    def test_percent_anywhere_rejected(self) -> None:
        inner = LaunchCommand(CLI, '-data "D:\\%USERPROFILE%\\ws" -command "project"')
        with pytest.raises(CliQuoteError, match="%"):
            wrap_console_utf8(inner, self.COMSPEC)

    @pytest.mark.parametrize(
        "arguments",
        [
            '-data "D:\\ws" -command "project" -vmargs -Dx=D:\\R&D',  # cmd запустит `D`
            '-data "D:\\ws" -command "project" -vmargs -Dy=a|b',  # вывод уйдёт в трубу
            '-data "D:\\ws" -command "project" -vmargs -Dz=a^b',
            '-data "D:\\ws" -command "project" -vmargs -Dz=1 >out',
        ],
    )
    def test_cmd_specials_outside_quotes_rejected(self, arguments: str) -> None:
        # [Ф] замер ревью 13.09.2026: вне "…" cmd толкует & | < > ^; vm_args идут без кавычек
        with pytest.raises(CliQuoteError, match="вне кавычек"):
            wrap_console_utf8(LaunchCommand(CLI, arguments), self.COMSPEC)

    @pytest.mark.parametrize(
        "arguments",
        [
            '-data "D:\\R&D\\ws (2)" -command "project"',  # внутри кавычек — цел
            '-data "D:\\ws" -command "validate --project-list [\'E:/a&b\' \'E:/c^d\']"',
            '-data "D:\\ws" -command "validate --file \'E:/x|y<z>.tsv\'"',
            '-data "D:\\ws" -command "project" -vmargs -Dfoo="a b" -Dx=!TEMP!',  # /v:off гасит !
        ],
    )
    def test_specials_inside_quotes_accepted(self, arguments: str) -> None:
        wrapped = wrap_console_utf8(LaunchCommand(CLI, arguments), self.COMSPEC)
        assert arguments in wrapped.arguments

    def test_line_longer_than_cmd_limit_rejected(self) -> None:
        # [Ф] замер ревью 13.09.2026: 9009 символов → «Слишком длинная входная строка», код 1
        paths = " ".join(f"'E:/projects/very/long/path/number_{i:04d}/cfe'" for i in range(200))
        inner = LaunchCommand(CLI, f'-data "D:\\ws" -command "validate --project-list [{paths}]"')
        with pytest.raises(CliQuoteError, match="8191"):
            wrap_console_utf8(inner, self.COMSPEC)


# Байты `.location` тестового workspace, снятые 13.09.2026 (Э6): dev_tools,
# привязанный на месте — проект лежит вне каталога workspace.
DEV_TOOLS_LOCATION = (
    b"@\xb1\x8b\x81#\xbc\x00\x14\x1a%\x96\xe7\xa3\x93\xbe\x1e"
    b"\x00$URI//file:/E:/tmp/edt-test/dev_tools"
    b"\x00\x00\x00\x00"
    b"\xc0X\xfb\xf3#\xbc\x00\x14\x1aQ\xf3\x8c{\xbbw\xc6"
)


class TestParseProjectLocation:
    def test_real_bytes(self) -> None:
        assert parse_project_location(DEV_TOOLS_LOCATION) == r"E:\tmp\edt-test\dev_tools"

    @pytest.mark.parametrize(
        ("uri", "expected"),
        [
            ("file:/E:/edt/тест_2026/src/cf", r"E:\edt\тест_2026\src\cf"),  # кириллица без %XX
            ("file:/E:/edt/edt%20test/%D0%BF", r"E:\edt\edt test\п"),  # %20 и %XX — снимаются
            ("file:///E:/edt/x", r"E:\edt\x"),
            ("file:////server/share/x", r"\\server\share\x"),  # [Д] URIUtil.toURI: так пишет Eclipse  # noqa: E501
            ("file://server/share/x", r"\\server\share\x"),  # authority-форма: читает, не пишет
            ("file:/e:/EDT/x", r"e:\EDT\x"),  # регистр не трогаем — сравнение через workspace_key
        ],
    )
    def test_file_uri_to_path(self, uri: str, expected: str) -> None:
        assert parse_project_location(location_blob(uri)) == expected

    def test_default_location_is_none(self) -> None:
        # Пустая строка вместо URI//… — проект в <workspace>\<имя>
        assert parse_project_location(location_blob(None)) is None

    def test_aborted_chunk_then_full_takes_last(self) -> None:
        # Оборванная запись (BEGIN без END), за ней полный чанк: как и
        # SafeChunkyInputStream.refineChunk, берём последний BEGIN ([Д] исходники Eclipse).
        # В здоровом файле чанк один — Eclipse очищает файл перед записью (Workspace.clear).  # noqa: RUF003, E501
        raw = location_blob("file:/D:/old")[:24] + location_blob("file:/D:/new")
        assert parse_project_location(raw) == r"D:\new"

    @pytest.mark.parametrize(
        "raw",
        [b"", b"garbage", DEV_TOOLS_LOCATION[:20], DEV_TOOLS_LOCATION[:40]],
    )
    def test_garbage_or_truncated_is_none(self, raw: bytes) -> None:
        assert parse_project_location(raw) is None

    def test_non_file_scheme_kept_verbatim(self) -> None:
        # Другие схемы (EFS) не превращаем в путь: запись останется «не проект»
        assert parse_project_location(location_blob("efs:/x/y")) == "efs:/x/y"

    def test_blob_roundtrip_matches_real_layout(self) -> None:
        assert location_blob("file:/E:/tmp/edt-test/dev_tools") == DEV_TOOLS_LOCATION
