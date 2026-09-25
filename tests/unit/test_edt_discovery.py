"""Обнаружение EDT и JDK на диске: раскладка [Ф] спека §0, цепочка JDK §3."""

from pathlib import Path

import pytest

import onecstarter.platform_1c.edt_discovery as edt_discovery_module
from onecstarter.domain.edt import EdtStartProduct
from onecstarter.platform_1c.edt_discovery import (
    EdtRoot,
    EdtRootScan,
    default_roots,
    discover_edt,
    find_installations,
    read_jdk_version,
)
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry

_ROOT_DEPTH = 3  # с запасом хватает для фикстур этого файла — не глубина продакшна  # noqa: RUF003

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
    # Тип изменился с задачей 5 (спека §1.3): вместо списка путей — список пар  # noqa: RUF003
    # «путь, глубина». Сами пути не менялись — только обёртка.
    env = {"ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
    assert default_roots(env) == [
        EdtRoot(Path(r"C:\Program Files\1C\1CE\components"), 2),
        EdtRoot(Path(r"C:\Users\u\AppData\Local\1C\1cedtstart\installations"), 3),
    ]


def test_default_roots_carry_their_own_depth() -> None:
    env = {"ProgramFiles": r"C:\PF", "LOCALAPPDATA": r"C:\LA"}
    roots = {root.path.name: root.max_depth for root in default_roots(env)}
    assert roots["components"] == 2
    assert roots["installations"] == 3


def test_read_jdk_version(tmp_path: Path) -> None:
    assert read_jdk_version(_jdk(tmp_path, "17.0.16")) == "17.0.16"
    assert read_jdk_version(tmp_path / "nope") is None


def _make_installation(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "1cedt.exe").write_text("", encoding="utf-8")
    return folder


def _make_jdk(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "release").write_text('JAVA_VERSION="21"\n', encoding="utf-8")
    (folder / "bin").mkdir()
    return folder


def test_installation_found_at_each_level_within_depth(tmp_path: Path) -> None:
    # Уровень 0 — сам корень: это запасной выход вехи (спека §1.5), путь прямо
    # на каталог установки обязан работать независимо от угаданной глубины.
    for level, parts in enumerate(([], ["a"], ["b", "c"], ["d", "e", "f"])):
        root = tmp_path / f"root{level}"
        _make_installation(root.joinpath(*parts))
        found, _jdks = find_installations(EdtRoot(root, max_depth=3))
        assert len(found) == 1, f"уровень {level} не найден"


def test_depth_is_a_hard_limit(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _make_installation(root / "a" / "b" / "c")
    assert find_installations(EdtRoot(root, max_depth=2))[0] == []
    assert len(find_installations(EdtRoot(root, max_depth=3))[0]) == 1


def test_walk_does_not_enter_a_found_installation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    installation = _make_installation(root / "edt")
    _make_installation(installation / "plugins" / "nested")
    found, _jdks = find_installations(EdtRoot(root, max_depth=3))
    assert found == [installation]


def test_jdk_is_a_leaf(tmp_path: Path) -> None:
    # Без отсечения глубина 3 на components стоит 48,6 мс против 23,1 [Ф].
    root = tmp_path / "root"
    jdk = _make_jdk(root / "jdk")
    (jdk / "legal" / "java.base").mkdir(parents=True)
    _make_installation(jdk / "legal" / "edt")
    found, jdks = find_installations(EdtRoot(root, max_depth=3))
    assert [path for _version, path in jdks] == [jdk]
    assert found == []


def test_release_without_bin_is_not_a_jdk(tmp_path: Path) -> None:
    root = tmp_path / "root"
    folder = root / "notjdk"
    folder.mkdir(parents=True)
    (folder / "release").write_text("", encoding="utf-8")
    _make_installation(folder / "inner")
    found, jdks = find_installations(EdtRoot(root, max_depth=3))
    assert jdks == []
    assert len(found) == 1


def test_missing_root_is_skipped(tmp_path: Path) -> None:
    assert find_installations(EdtRoot(tmp_path / "нет", max_depth=3)) == ([], [])


def _root(path: Path) -> EdtRoot:
    return EdtRoot(path, _ROOT_DEPTH)


def _registry_with(exe: Path, label: str) -> EdtStartRegistry:
    """Реестр с одним продуктом — по образцу инлайновых `EdtStartRegistry` этого файла."""  # noqa: RUF002
    return EdtStartRegistry(
        products=(EdtStartProduct(id="p", version=label, exe=exe, jvm_dir=None, args=()),),
        projects=(),
        skipped=0,
    )


class TestDiscover:
    def test_finds_installations_and_auto_jdk(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _edt(tmp_path, "2026.1.2+2")
        jdk17 = _jdk(tmp_path, "17.0.16")
        jdk25 = _jdk(tmp_path, "25.0.2")
        (tmp_path / "1c-edt-start-0.10.0+448-x86_64").mkdir()  # лаунчер — не EDT
        found = discover_edt([_root(tmp_path)], None, "").installations
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
        [found] = discover_edt([_root(tmp_path)], registry, "").installations
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
        [found] = discover_edt([_root(tmp_path)], registry, "").installations
        assert found.jvm_dir == jdk17 / "bin"
        assert found.jvm_source == "auto"

    def test_ini_vm_used_when_exists(self, tmp_path: Path) -> None:
        zulu = tmp_path / "zulu" / "bin"
        zulu.mkdir(parents=True)
        (zulu / "javaw.exe").write_bytes(b"")
        ini = f"-vm\n{zulu / 'javaw.exe'}\n-vmargs\n-Dosgi.requiredJavaVersion=17\n"
        _edt(tmp_path, "2024.2.6+7", ini)
        [found] = discover_edt([_root(tmp_path)], None, "").installations
        assert found.jvm_dir == zulu
        assert found.jvm_source == "1cedt.ini"

    def test_ini_vm_missing_on_disk_ignored(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent" / "jdk" / "bin" / "javaw.exe"
        ini = f"-vm\n{nonexistent}\n-vmargs\n"
        _edt(tmp_path, "2024.2.6+7", ini)
        [found] = discover_edt([_root(tmp_path)], None, "").installations
        assert found.jvm_dir is None
        assert found.jvm_source == ""

    def test_settings_jvm(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        mine = tmp_path / "myjdk" / "bin"
        mine.mkdir(parents=True)
        [found] = discover_edt([_root(tmp_path)], None, str(mine)).installations
        assert found.jvm_dir == mine
        assert found.jvm_source == "settings"

    def test_too_old_auto_jdk_not_picked(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _jdk(tmp_path, "11.0.2")
        [found] = discover_edt([_root(tmp_path)], None, "").installations
        assert found.jvm_dir is None

    def test_same_major_newest_full_version_wins(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _jdk(tmp_path, "17.0.9")
        newest = _jdk(tmp_path, "17.0.16")
        [found] = discover_edt([_root(tmp_path)], None, "").installations
        assert found.jvm_dir == newest / "bin"

    def test_product_location_outside_roots(self, tmp_path: Path) -> None:
        elsewhere = _edt(tmp_path / "elsewhere", "2025.2.6+4")
        registry = _registry_with(elsewhere / "1cedt.exe", "2025.2.6+4")
        roots = tmp_path / "roots"
        roots.mkdir()
        [found] = discover_edt([_root(roots)], registry, "").installations
        assert found.exe == elsewhere / "1cedt.exe"

    def test_same_install_from_root_and_product_not_duplicated(self, tmp_path: Path) -> None:
        edt = _edt(tmp_path, "2025.2.6+4")
        registry = _registry_with(edt / "1cedt.exe", "2025.2.6+4")
        result = discover_edt([_root(tmp_path)], registry, "")
        assert len(result.installations) == 1

    def test_missing_root_and_dir_without_exe(self, tmp_path: Path) -> None:
        (tmp_path / "1c-edt-2025.2.6+4-x86_64").mkdir()  # без 1cedt.exe
        result = discover_edt([_root(tmp_path), _root(tmp_path / "nope")], None, "")
        assert result.installations == []
        assert result.rejected == []
        # Ревью, круг 1 (Important + сомнение исполнителя): существующий, но
        # пустой корень и вовсе отсутствующий — разные картины, обе с  # noqa: RUF003
        # found=0. `roots` обязан различать их через `exists`, иначе лог,
        # построенный поверх этого поля, не может сказать больше числа.
        assert result.roots == [
            EdtRootScan(tmp_path, _ROOT_DEPTH, True, 0),
            EdtRootScan(tmp_path / "nope", _ROOT_DEPTH, False, 0),
        ]

    def test_scanned_roots_report_found_count_per_root(self, tmp_path: Path) -> None:
        _edt(tmp_path, "2025.2.6+4")
        _edt(tmp_path, "2026.1.2+2")
        result = discover_edt([_root(tmp_path)], None, "")
        assert result.roots == [EdtRootScan(tmp_path, _ROOT_DEPTH, True, 2)]


def test_discover_edt_walks_each_root_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Important ревью, круг 1: обход каждого корня — один раз за вызов `discover_edt`,

    не дважды (было — цикл логирования в `ui/app.py` плюс этот обход). Здесь
    проверяется низкоуровневая часть гарантии: `discover_edt` сама не зовёт
    `find_installations` больше одного раза на корень.
    """
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"  # не существует
    calls: list[EdtRoot] = []
    real = edt_discovery_module.find_installations

    def counting(root: EdtRoot) -> tuple[list[Path], list[tuple[str, Path]]]:
        calls.append(root)
        return real(root)

    monkeypatch.setattr(edt_discovery_module, "find_installations", counting)
    discover_edt([_root(root_a), _root(root_b)], None, "")
    assert calls == [_root(root_a), _root(root_b)], "по одному вызову на корень, не по два"


def test_registry_version_wins_over_directory_name(tmp_path: Path) -> None:
    # Худший из трёх дефектов: ответ есть в products.json, а мы его  # noqa: RUF003
    # игнорируем.
    folder = _make_installation(tmp_path / "root" / "1C_EDT 2026.1")
    registry = _registry_with(folder / "1cedt.exe", "2026.1.2+2")
    result = discover_edt([_root(tmp_path / "root")], registry, "")
    assert [i.version for i in result.installations] == ["2026.1.2+2"]


def test_config_ini_used_when_name_does_not_match_mask(tmp_path: Path) -> None:
    folder = _make_installation(tmp_path / "root" / "1C_EDT 2026.1")
    config = folder / "configuration"
    config.mkdir()
    (config / "config.ini").write_text(
        "product.version=2026.1.2\neclipse.buildId=2026.1.2.2\n", encoding="utf-8"
    )
    result = discover_edt([_root(tmp_path / "root")], None, "")
    assert [i.version for i in result.installations] == ["2026.1.2+2"]


def test_directory_mask_still_works(tmp_path: Path) -> None:
    _make_installation(tmp_path / "root" / "1c-edt-2025.2.6+4-x86_64")
    result = discover_edt([_root(tmp_path / "root")], None, "")
    assert [i.version for i in result.installations] == ["2025.2.6+4"]


def test_installation_without_version_is_rejected(tmp_path: Path) -> None:
    # Версия — ключ привязки проекта к установке (EdtProject.edt_version),
    # и установка без версии эту привязку ломает. Решение заказчика 25.09.2026.
    folder = _make_installation(tmp_path / "root" / "какой-то каталог")
    result = discover_edt([_root(tmp_path / "root")], None, "")
    assert result.installations == []
    assert [path for path, _reason in result.rejected] == [folder]


def test_rejected_carries_the_reason(tmp_path: Path) -> None:
    _make_installation(tmp_path / "root" / "без версии")
    result = discover_edt([_root(tmp_path / "root")], None, "")
    assert "верси" in result.rejected[0][1].casefold()


def test_registry_entry_without_exe_on_disk_is_rejected(tmp_path: Path) -> None:
    # Запись пережила перенос/переустановку EDT: exe, на который она указывает,
    # больше не существует. Кандидат не должен просто исчезнуть — лог
    # обнаружения (спека §1.4) обязан увидеть и его, отдельно от «нет  # noqa: RUF003
    # версии».
    exe = tmp_path / "root" / "1c-edt-2025.2.6+4-x86_64" / "1cedt.exe"
    registry = _registry_with(exe, "2025.2.6+4")
    result = discover_edt([_root(tmp_path / "root")], registry, "")
    assert result.installations == []
    assert [path for path, _reason in result.rejected] == [exe.parent]
    assert "1cedt.exe" in result.rejected[0][1]
    assert "верси" not in result.rejected[0][1].casefold()
