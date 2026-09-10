"""Обнаружение EDT и JDK на диске: раскладка [Ф] спека §0, цепочка JDK §3."""

from pathlib import Path

from onecstarter.domain.edt import EdtStartProduct
from onecstarter.platform_1c.edt_discovery import default_roots, discover_edt, read_jdk_version
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry

INI_NO_VM = "-vmargs\n-Dosgi.requiredJavaVersion=17\n-Xmx4096m\n"


def _edt(root: Path, version: str, ini: str = INI_NO_VM) -> Path:
    folder = root / f"1c-edt-{version}-x86_64"
    folder.mkdir(parents=True)
    (folder / "1cedt.exe").write_bytes(b"")
    (folder / "1cedt.ini").write_text(ini, encoding="utf-8")
    return folder


def _jdk(root: Path, version: str) -> Path:
    folder = root / f"axiom-jdk-full-{version}+12-x86_64"
    (folder / "bin").mkdir(parents=True)
    (folder / "release").write_text(f'JAVA_VERSION="{version}"\n', encoding="utf-8")
    return folder


def test_default_roots() -> None:
    env = {"ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
    assert default_roots(env) == [
        Path(r"C:\Program Files\1C\1CE\components"),
        Path(r"C:\Users\u\AppData\Local\1C\1cedtstart\installations"),
    ]


def test_read_jdk_version(tmp_path: Path) -> None:
    assert read_jdk_version(_jdk(tmp_path, "17.0.16")) == "17.0.16"
    assert read_jdk_version(tmp_path / "nope") is None


class TestDiscover:
    def test_finds_installations_and_auto_jdk(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _edt(tmp_path, "2026.1.2+2")
        jdk17 = _jdk(tmp_path, "17.0.16")
        jdk25 = _jdk(tmp_path, "25.0.2")
        (tmp_path / "1c-edt-start-0.10.0+448-x86_64").mkdir()  # лаунчер — не EDT
        found = discover_edt([tmp_path], None, "")
        assert [i.version for i in found] == ["2026.1.2+2", "2025.2.6+4"]
        assert found[0].exe == tmp_path / "1c-edt-2026.1.2+2-x86_64" / "1cedt.exe"
        assert found[0].jvm_dir == jdk25 / "bin"
        assert found[0].jvm_source == "auto"
        assert found[0].required_java == 17
        assert found[0].vm_args == ""
        assert found[0].jvm_dir != jdk17 / "bin"  # старший из подходящих, не первый

    def test_products_json_enriches_jvm_and_args(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        jdk17 = _jdk(tmp_path, "17.0.16")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p",
                    version="2025.2.6+4",
                    exe=edt / "1cedt.exe",
                    jvm_dir=jdk17 / "bin",
                    args=("-Xmx8192m", "-DnativeFormBufferedLayoutRender=true"),
                ),
            ),
            projects=(),
            skipped=0,
        )
        [found] = discover_edt([tmp_path], registry, "")
        assert found.jvm_dir == jdk17 / "bin"
        assert found.jvm_source == "products.json"
        assert found.vm_args == "-Xmx8192m -DnativeFormBufferedLayoutRender=true"

    def test_product_jvm_missing_on_disk_falls_through(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        jdk17 = _jdk(tmp_path, "17.0.16")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p",
                    version="2025.2.6+4",
                    exe=edt / "1cedt.exe",
                    jvm_dir=tmp_path / "gone" / "bin",
                    args=(),
                ),
            ),
            projects=(),
            skipped=0,
        )
        [found] = discover_edt([tmp_path], registry, "")
        assert found.jvm_dir == jdk17 / "bin"
        assert found.jvm_source == "auto"

    def test_ini_vm_used_when_exists(self, tmp_path: Path) -> None:
        zulu = tmp_path / "zulu" / "bin"
        zulu.mkdir(parents=True)
        (zulu / "javaw.exe").write_bytes(b"")
        ini = f"-vm\n{zulu / 'javaw.exe'}\n-vmargs\n-Dosgi.requiredJavaVersion=17\n"
        _edt(tmp_path, "2024.2.6+7", ini)
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir == zulu
        assert found.jvm_source == "1cedt.ini"

    def test_ini_vm_missing_on_disk_ignored(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent" / "jdk" / "bin" / "javaw.exe"
        ini = f"-vm\n{nonexistent}\n-vmargs\n"
        _edt(tmp_path, "2024.2.6+7", ini)
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir is None
        assert found.jvm_source == ""

    def test_settings_jvm(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        mine = tmp_path / "myjdk" / "bin"
        mine.mkdir(parents=True)
        [found] = discover_edt([tmp_path], None, str(mine))
        assert found.jvm_dir == mine
        assert found.jvm_source == "settings"

    def test_too_old_auto_jdk_not_picked(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _jdk(tmp_path, "11.0.2")
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir is None

    def test_same_major_newest_full_version_wins(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _jdk(tmp_path, "17.0.9")
        newest = _jdk(tmp_path, "17.0.16")
        [found] = discover_edt([tmp_path], None, "")
        assert found.jvm_dir == newest / "bin"

    def test_product_location_outside_roots(self, tmp_path: Path) -> None:
        elsewhere = _edt(tmp_path / "elsewhere", "2025.2.6+4")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p", version="2025.2.6+4", exe=elsewhere / "1cedt.exe", jvm_dir=None, args=()
                ),
            ),
            projects=(),
            skipped=0,
        )
        roots = tmp_path / "roots"
        roots.mkdir()
        [found] = discover_edt([roots], registry, "")
        assert found.exe == elsewhere / "1cedt.exe"

    def test_same_install_from_root_and_product_not_duplicated(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        registry = EdtStartRegistry(
            products=(
                EdtStartProduct(
                    id="p", version="2025.2.6+4", exe=edt / "1cedt.exe", jvm_dir=None, args=()
                ),
            ),
            projects=(),
            skipped=0,
        )
        assert len(discover_edt([tmp_path], registry, "")) == 1

    def test_missing_root_and_dir_without_exe(self, tmp_path: Path) -> None:
        (tmp_path / "1c-edt-2025.2.6+4-x86_64").mkdir()  # без 1cedt.exe
        assert discover_edt([tmp_path, tmp_path / "nope"], None, "") == []
