"""Чтение реестра EDT Start: терпимый разбор products.json / projects.json (спека §6)."""

import json
import shutil
from pathlib import Path

import pytest

from onecstarter.platform_1c.edtstart_registry import (
    EdtStartRegistry,
    default_edtstart_root,
    file_url_to_path,
    parse_products,
    parse_projects,
    read_registry,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edtstart"


class TestFileUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "file:///C:/Program%20Files/1C/1CE/components/axiom-jdk-full-17.0.16+12-x86_64/bin/",
                Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin"),
            ),
            ("file:///D:/jdk/bin/", Path(r"D:\jdk\bin")),
            ("file:///D:/%D0%BF%D1%83%D1%82%D1%8C/bin", Path(r"D:\путь\bin")),
        ],
    )
    def test_table(self, url: str, expected: Path) -> None:
        assert file_url_to_path(url) == expected


class TestParseProducts:
    def test_reads_fixture(self) -> None:
        products = parse_products((FIXTURES / "products.json").read_text(encoding="utf-8"))
        assert [p.version for p in products] == ["2025.2.6+4", "2026.1.2+2"]
        first = products[0]
        assert first.id == "11111111-1111-1111-1111-111111111111"
        assert first.exe == Path(
            r"C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedt.exe"
        )
        assert first.jvm_dir == Path(
            r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin"
        )
        assert first.args == ("-Xmx8192m", "-DnativeFormBufferedLayoutRender=true")

    def test_product_without_args_has_empty_tuple(self) -> None:
        products = parse_products((FIXTURES / "products.json").read_text(encoding="utf-8"))
        assert products[1].args == ()

    def test_product_without_location_skipped(self) -> None:
        text = json.dumps({"data": [{"id": "x", "installedVersion": {"label": "1"}}]})
        assert parse_products(text) == []

    def test_not_a_dict_is_empty(self) -> None:
        assert parse_products("[]") == []


class TestParseProjects:
    def test_reads_fixture_and_counts_skipped(self) -> None:
        projects, skipped = parse_projects(
            (FIXTURES / "projects.json").read_text(encoding="utf-8")
        )
        assert skipped == 1
        assert [p.label for p in projects] == [
            "(2025) Проект А",  # noqa: RUF001
            "Проект Б без args",
            "(2025) Проект В (с пробелом)",  # noqa: RUF001
            "Проект Г — продукт удалён",
        ]

    def test_args_and_jvm(self) -> None:
        projects, _ = parse_projects((FIXTURES / "projects.json").read_text(encoding="utf-8"))
        assert projects[0].args == ("-Xmx8192m",)
        assert projects[0].jvm_dir is None
        assert projects[1].args == ()
        assert projects[2].jvm_dir == Path(r"D:\jdk\bin")
        assert projects[2].workspace == Path(r"D:\edt\2025-2-6\(2025) проект в_ws")


class TestReadRegistry:
    def test_reads_both_files(self, tmp_path: Path) -> None:
        shutil.copytree(FIXTURES, tmp_path / "1cedtstart")
        registry = read_registry(tmp_path / "1cedtstart")
        assert isinstance(registry, EdtStartRegistry)
        assert len(registry.products) == 2
        assert len(registry.projects) == 4
        assert registry.skipped == 1

    def test_missing_root_is_none(self, tmp_path: Path) -> None:
        assert read_registry(tmp_path / "nope") is None

    def test_broken_json_is_none(self, tmp_path: Path) -> None:
        root = tmp_path / "1cedtstart"
        root.mkdir()
        (root / "products.json").write_text("{", encoding="utf-8")
        (root / "projects.json").write_text("{}", encoding="utf-8")
        assert read_registry(root) is None

    def test_missing_projects_file_gives_empty_projects(self, tmp_path: Path) -> None:
        root = tmp_path / "1cedtstart"
        root.mkdir()
        shutil.copy(FIXTURES / "products.json", root / "products.json")
        registry = read_registry(root)
        assert registry is not None
        assert registry.projects == ()


def test_default_root() -> None:
    assert default_edtstart_root({"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}) == Path(
        r"C:\Users\u\AppData\Local\1C\1cedtstart"
    )
