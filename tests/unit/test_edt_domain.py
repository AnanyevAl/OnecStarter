"""Домен EDT: модель, разбор имён каталогов, 1cedt.ini и release JDK (спека §0, §3)."""

from pathlib import Path

import pytest

from onecstarter.domain.edt import (
    DEFAULT_REQUIRED_JAVA,
    LANGUAGES,
    EdtInstallation,
    EdtProject,
    IniInfo,
    VmArgsParts,
    build_edt_command,
    effective_jvm,
    java_major,
    java_version_key,
    join_vm_args,
    parse_ini,
    parse_release,
    pick_jvm,
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
            (
                "-Dmsg=Don't stop -Xmx8192m",
                VmArgsParts(8192, None, ("-Dmsg=Don't", "stop")),
            ),  # апостроф в значении — не конец токена
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
            '-Dfoo="a b"',
        ],
    )
    def test_roundtrip(self, text: str) -> None:
        parts = split_vm_args(text)
        assert split_vm_args(join_vm_args(parts.max_heap_mb, parts.language, parts.rest)) == parts


def test_languages_have_default_first() -> None:
    assert LANGUAGES[0] == ("", "По умолчанию")
    assert [code for code, _label in LANGUAGES] == ["", "ru", "en"]


JDK17 = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin")
JDK25 = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-25.0.2+12-x86_64\bin")
ZULU = Path(r"C:\Program Files\Zulu\zulu-17\bin")
MINE = Path(r"D:\jdk\bin")


class TestPickJvm:
    def test_products_json_wins(self) -> None:
        assert pick_jvm(
            product=JDK17, ini=ZULU, settings=MINE, auto=[("25.0.2", JDK25)], required_java=17
        ) == (JDK17, "products.json")

    def test_ini_when_no_product(self) -> None:
        assert pick_jvm(product=None, ini=ZULU, settings=MINE, auto=[], required_java=17) == (
            ZULU,
            "1cedt.ini",
        )

    def test_settings_when_no_product_and_ini(self) -> None:
        assert pick_jvm(product=None, ini=None, settings=MINE, auto=[], required_java=17) == (
            MINE,
            "settings",
        )

    def test_auto_picks_newest_fitting(self) -> None:
        assert pick_jvm(
            product=None,
            ini=None,
            settings=None,
            auto=[("17.0.16", JDK17), ("25.0.2", JDK25)],
            required_java=17,
        ) == (JDK25, "auto")

    def test_auto_same_major_picks_newest_full_version_numerically(self) -> None:
        older = Path(r"C:\jdk\axiom-jdk-full-17.0.9+7-x86_64\bin")
        assert pick_jvm(
            product=None,
            ini=None,
            settings=None,
            auto=[("17.0.9", older), ("17.0.16", JDK17)],
            required_java=17,
        ) == (JDK17, "auto")  # строкой "17.0.9" > "17.0.16" — потому сравнение числами

    def test_auto_skips_too_old(self) -> None:
        assert pick_jvm(
            product=None,
            ini=None,
            settings=None,
            auto=[("11.0.2", MINE), ("17.0.16", JDK17)],
            required_java=17,
        ) == (JDK17, "auto")

    def test_nothing_fits(self) -> None:
        assert pick_jvm(
            product=None, ini=None, settings=None, auto=[("11.0.2", MINE)], required_java=17
        ) is None

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("17.0.16", (17, 0, 16)),
            ("25", (25,)),
            ("1.8.0_392", (1, 8, 0, 392)),
            ("", ()),
            ("x", ()),
        ],
    )
    def test_java_version_key(self, version: str, expected: tuple[int, ...]) -> None:
        assert java_version_key(version) == expected


def _installation(**overrides: object) -> EdtInstallation:
    values: dict[str, object] = {
        "version": "2025.2.6+4",
        "exe": Path(r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedt.exe"),
        "jvm_dir": JDK17,
        "vm_args": "-Xmx8192m -DnativeFormBufferedLayoutRender=true",
        "required_java": 17,
        "jvm_source": "products.json",
    }
    values.update(overrides)
    return EdtInstallation(**values)  # type: ignore[arg-type]


class TestBuildEdtCommand:
    def test_repeats_edt_start_line(self) -> None:
        # [Ф] спека §0: снято с живого процесса 1cedt.exe  # noqa: RUF003
        command = build_edt_command(
            _installation().exe,
            r"D:\edt\2025\retail",
            JDK17,
            "-Xmx8192m -DnativeFormBufferedLayoutRender=true",
            "-Xmx8192m",
        )
        assert command.executable == _installation().exe
        assert command.arguments == (
            f'-data "D:\\edt\\2025\\retail" -vm "{JDK17}" --launcher.appendVmargs '
            "-vmargs -Xmx8192m -DnativeFormBufferedLayoutRender=true "
            "-Djava.library.path= -Xmx8192m"
        )

    def test_empty_args_on_both_levels(self) -> None:
        command = build_edt_command(_installation().exe, r"D:\edt\a b", JDK17, "", "")
        assert command.arguments == (
            f'-data "D:\\edt\\a b" -vm "{JDK17}" --launcher.appendVmargs '
            "-vmargs -Djava.library.path="
        )

    def test_command_line_quotes_executable(self) -> None:
        command = build_edt_command(_installation().exe, r"D:\edt\a", JDK17, "", "")
        assert command.command_line.startswith('"C:\\Program Files\\1C\\1CE\\')

    def test_installation_args_project_empty_no_trailing_space(self) -> None:
        command = build_edt_command(
            _installation().exe, r"D:\edt\a", JDK17, "-Xmx8192m", ""
        )
        assert command.arguments == (
            f'-data "D:\\edt\\a" -vm "{JDK17}" --launcher.appendVmargs '
            "-vmargs -Xmx8192m -Djava.library.path="
        )


class TestEffectiveJvm:
    def test_project_override_wins(self) -> None:
        project = EdtProject(id="p", name="n", workspace=r"D:\w", jvm_dir=str(MINE))
        assert effective_jvm(project, _installation()) == MINE

    def test_installation_when_project_empty(self) -> None:
        project = EdtProject(id="p", name="n", workspace=r"D:\w")
        assert effective_jvm(project, _installation()) == JDK17

    def test_none_when_neither(self) -> None:
        project = EdtProject(id="p", name="n", workspace=r"D:\w")
        assert effective_jvm(project, _installation(jvm_dir=None)) is None
