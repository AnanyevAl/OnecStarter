"""Домен EDT: модель, разбор имён каталогов, 1cedt.ini и release JDK (спека §0, §3)."""

import pytest

from onecstarter.domain.edt import (
    DEFAULT_REQUIRED_JAVA,
    LANGUAGES,
    EdtProject,
    IniInfo,
    VmArgsParts,
    java_major,
    join_vm_args,
    parse_ini,
    parse_release,
    split_vm_args,
    version_from_dir_name,
    workspace_key,
)


class TestModel:
    def test_project_defaults_are_empty(self) -> None:
        project = EdtProject(id="p1", name="Розница", workspace=r"D:\edt\retail")
        assert project.project_dir == ""
        assert project.edt_version == ""
        assert project.jvm_dir == ""
        assert project.vm_args == ""
        assert project.group_id is None


class TestWorkspaceKey:
    @pytest.mark.parametrize(
        ("left", "right"),
        [
            (r"D:\edt\Retail", r"d:\EDT\retail"),
            (r"D:\edt\retail\.", r"D:\edt\retail"),
            (r"D:/edt/retail", r"D:\edt\retail"),
            (r"D:\edt\x\..\retail", r"D:\edt\retail"),
        ],
    )
    def test_equal_keys(self, left: str, right: str) -> None:
        assert workspace_key(left) == workspace_key(right)

    def test_different_dirs_differ(self) -> None:
        assert workspace_key(r"D:\edt\a") != workspace_key(r"D:\edt\b")


class TestVersionFromDirName:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("1c-edt-2025.2.6+4-x86_64", "2025.2.6+4"),
            ("1c-edt-2026.1.2+2-x86_64", "2026.1.2+2"),
            ("1c-edt-2024.2.6+7-x86_64", "2024.2.6+7"),
            ("1c-edt-start-0.10.0+448-x86_64", None),  # лаунчер — не EDT
            ("axiom-jdk-full-17.0.16+12-x86_64", None),
            ("1c-edt-2025.2.6+4", None),  # без суффикса разрядности
            ("", None),
        ],
    )
    def test_table(self, name: str, expected: str | None) -> None:
        assert version_from_dir_name(name) == expected


INI_2025 = """-startup
plugins/org.eclipse.equinox.launcher_1.6.600.v20231106-1826.jar
-showsplash
com._1c.g5.v8.dt.product.application
-vmargs
-Dosgi.requiredJavaVersion=17
-Xms80m
-Xmx4096m
"""

INI_2024 = """-startup
plugins/org.eclipse.equinox.launcher_1.6.600.v20231106-1826.jar
-vm
C:\\Program Files\\Zulu\\zulu-17\\bin\\javaw.exe
-vmargs
-Dosgi.requiredJavaVersion=17
-Xmx4096m
"""


class TestParseIni:
    def test_without_vm(self) -> None:
        assert parse_ini(INI_2025) == IniInfo(vm=None, required_java=17)

    def test_with_vm(self) -> None:
        info = parse_ini(INI_2024)
        assert info.vm == r"C:\Program Files\Zulu\zulu-17\bin\javaw.exe"
        assert info.required_java == 17

    def test_required_java_defaults_when_absent(self) -> None:
        assert parse_ini("-vmargs\n-Xmx1g\n").required_java == DEFAULT_REQUIRED_JAVA

    def test_required_java_garbage_defaults(self) -> None:
        assert parse_ini("-Dosgi.requiredJavaVersion=abc\n").required_java == DEFAULT_REQUIRED_JAVA

    def test_vm_at_end_without_value_is_none(self) -> None:
        assert parse_ini("-vmargs\n-vm\n").vm is None

    def test_empty_text(self) -> None:
        assert parse_ini("") == IniInfo(vm=None, required_java=DEFAULT_REQUIRED_JAVA)


RELEASE = """IMPLEMENTOR="Axiom JSC"
JAVA_RUNTIME_VERSION="17.0.16+12-LTS"
JAVA_VERSION="17.0.16"
JAVA_VERSION_DATE="2025-07-15"
"""


class TestRelease:
    def test_parse_release(self) -> None:
        assert parse_release(RELEASE) == "17.0.16"

    def test_parse_release_missing(self) -> None:
        assert parse_release('IMPLEMENTOR="X"\n') is None

    @pytest.mark.parametrize(
        ("version", "expected"),
        [("17.0.16", 17), ("25.0.2", 25), ("1.8.0_392", 8), ("21", 21), ("", None), ("x.y", None)],
    )
    def test_java_major(self, version: str, expected: int | None) -> None:
        assert java_major(version) == expected


class TestSplitVmArgs:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("", VmArgsParts(None, None, ())),
            ("-Xmx8192m", VmArgsParts(8192, None, ())),
            ("-Xmx8g", VmArgsParts(8192, None, ())),
            ("-Xmx524288k", VmArgsParts(512, None, ())),
            ("-Xmx1073741824", VmArgsParts(1024, None, ())),
            ("-Duser.language=ru", VmArgsParts(None, "ru", ())),
            (
                "-Xmx4096m -DnativeFormBufferedLayoutRender=true -Xmx8192m",
                VmArgsParts(8192, None, ("-DnativeFormBufferedLayoutRender=true",)),
            ),  # повтор -Xmx — берётся последний (спека §2)
            (
                '-Dfoo="a b" -Xmx2g',
                VmArgsParts(2048, None, ('-Dfoo="a b"',)),
            ),
            ("-Xmxabc", VmArgsParts(None, None, ("-Xmxabc",))),  # неразбираемый
            ('-Dbroken="unterminated', VmArgsParts(None, None, ('-Dbroken="unterminated',))),
        ],
    )
    def test_table(self, text: str, expected: VmArgsParts) -> None:
        assert split_vm_args(text) == expected


class TestJoinVmArgs:
    @pytest.mark.parametrize(
        ("heap", "language", "rest", "expected"),
        [
            (None, None, (), ""),
            (8192, None, (), "-Xmx8192m"),
            (None, "ru", (), "-Duser.language=ru"),
            (8192, "en", ("-Dx=1",), "-Dx=1 -Xmx8192m -Duser.language=en"),
            (None, "", ("-Dx=1",), "-Dx=1"),  # пустой язык = по умолчанию
        ],
    )
    def test_table(
        self, heap: int | None, language: str | None, rest: tuple[str, ...], expected: str
    ) -> None:
        assert join_vm_args(heap, language, rest) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "-Xmx8192m",
            "-Dx=1 -Xmx8192m -Duser.language=ru",
            "-DnativeFormBufferedLayoutRender=true",
        ],
    )
    def test_roundtrip(self, text: str) -> None:
        parts = split_vm_args(text)
        assert split_vm_args(join_vm_args(parts.max_heap_mb, parts.language, parts.rest)) == parts


def test_languages_have_default_first() -> None:
    assert LANGUAGES[0] == ("", "По умолчанию")
    assert [code for code, _label in LANGUAGES] == ["", "ru", "en"]
