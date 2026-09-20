"""Каталог схем и запись в рабочую область (спека v3.2, §4, §7; инвариант 4)."""

import shutil
import zipfile
from pathlib import Path

import pytest

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    EDITORS_PREFS,
    EDT_DEFAULTS,
    THEME_IDS,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    parse_csi,
    parse_prefs,
)
from onecstarter.services.edt_scheme import (
    BUSY_MESSAGE,
    CatalogEntry,
    SchemeCatalog,
    WorkspaceSchemes,
    save_csi,
)
from onecstarter.services.errors import EdtError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edt_schemes"
TOKEN = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


def _catalog(tmp_path: Path) -> SchemeCatalog:
    root = tmp_path / "schemes"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "deep").mkdir()
    (root / "sub2").mkdir()
    shutil.copy(FIXTURES / "dark22.csi", root / "a.csi")
    shutil.copy(FIXTURES / "idea-six.xml", root / "B.XML")
    shutil.copy(FIXTURES / "four-scopes.tmTheme", root / "sub" / "c.tmTheme")
    shutil.copy(FIXTURES / "dark22.csi", root / "sub" / "deep" / "d.csi")  # второй уровень — мимо
    (root / "readme.txt").write_text("x", encoding="utf-8")
    with zipfile.ZipFile(root / "sub2" / "e.jar", "w") as archive:
        archive.writestr("colors/Six.xml", (FIXTURES / "idea-six.xml").read_text(encoding="utf-8"))
    (root / "broken.icls").write_text("<x/>", encoding="utf-8")
    return SchemeCatalog(str(root))


def test_catalog_entries_root_and_first_level_by_extension_sorted(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    assert catalog.exists() is True
    entries = catalog.entries()
    assert [(e.name, e.kind) for e in entries] == [
        ("a", "csi"),
        ("B", "idea"),
        ("broken", "idea"),
        ("c", "tmtheme"),
        ("e", "jar"),
    ]
    assert entries[3].path == tmp_path / "schemes" / "sub" / "c.tmTheme"


def test_catalog_missing_directory_is_empty(tmp_path: Path) -> None:
    catalog = SchemeCatalog(str(tmp_path / "nope"))
    assert catalog.exists() is False
    assert catalog.entries() == []


def test_catalog_loads_each_kind(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    by_name = {entry.name: entry for entry in catalog.entries()}
    csi = catalog.load(by_name["a"])
    assert csi.name == "a"
    assert csi.colors["Background"] == (43, 43, 43)
    assert csi.source == str(by_name["a"].path)
    idea = catalog.load(by_name["B"])
    assert idea.name == "Шесть атрибутов"  # имя из XML, не stem
    assert idea.colors["BSL_Keywords"] == (204, 120, 50)
    # `Others` в XML нет → запасной источник `TEXT.FOREGROUND` (Э11)
    assert idea.colors["Others"] == (169, 183, 198)
    assert catalog.load(by_name["c"]).colors["Strings"] == (206, 145, 120)
    assert catalog.load(by_name["e"]).name == "Шесть атрибутов"


def test_catalog_load_error_is_edt_error_with_reason(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    broken = next(entry for entry in catalog.entries() if entry.name == "broken")
    with pytest.raises(EdtError, match="не удалось прочитать"):
        catalog.load(broken)
    with pytest.raises(EdtError, match="не удалось прочитать"):
        catalog.load(CatalogEntry("gone", tmp_path / "gone.csi", "csi"))


def test_save_csi_writes_atomically(tmp_path: Path) -> None:
    path = tmp_path / "out" / "Моя.csi"
    scheme = Scheme("Моя", EDT_DEFAULTS)
    save_csi(path, scheme)
    assert parse_csi(path.read_text(encoding="utf-8")) == scheme.colors
    assert [p.name for p in path.parent.iterdir()] == ["Моя.csi"]
    (tmp_path / "file").write_text("x", encoding="utf-8")
    with pytest.raises(EdtError, match="Не удалось записать"):  # noqa: RUF001
        save_csi(tmp_path / "file" / "x.csi", scheme)


def _workspace(tmp_path: Path, busy: bool = False) -> WorkspaceSchemes:
    return WorkspaceSchemes(str(tmp_path / "ws"), is_busy=lambda: busy)


def _dark() -> Scheme:
    return Scheme("d", parse_csi((FIXTURES / "dark22.csi").read_text(encoding="utf-8")))


def test_apply_creates_settings_and_both_files_atomically(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    settings = workspace.settings_dir
    expected = (
        tmp_path / "ws" / ".metadata" / ".plugins" / "org.eclipse.core.runtime" / ".settings"
    )
    assert settings == expected
    assert sorted(p.name for p in settings.iterdir()) == [BSL_PREFS, EDITORS_PREFS]
    bsl = parse_prefs((settings / BSL_PREFS).read_bytes().decode("latin-1"))
    assert bsl[f"{TOKEN}Builtin function.color"] == "255,198,109"
    assert bsl["eclipse.preferences.version"] == "1"
    editors = parse_prefs((settings / EDITORS_PREFS).read_bytes().decode("latin-1"))
    assert editors["AbstractTextEditor.Color.Background"] == "43,43,43"
    assert editors["AbstractTextEditor.Color.Background.SystemDefault"] == "false"
    assert not list(settings.glob("*.tmp"))


def test_apply_preserves_foreign_keys_and_crlf(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.settings_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "bsl-crlf.prefs", workspace.settings_dir / BSL_PREFS)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    text = (workspace.settings_dir / BSL_PREFS).read_bytes().decode("latin-1")
    assert text.startswith("=\r\n")
    assert text.endswith("\\u00EF\\u00BB\\u00BF=\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert parse_prefs(text)[f"{TOKEN}Strings.color"] == "106,135,89"


def test_apply_refuses_when_busy_before_writing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, busy=True)
    with pytest.raises(EdtError, match=BUSY_MESSAGE):
        workspace.apply(_dark(), ThemeChoice.DARK)
    assert not workspace.settings_dir.exists()
    with pytest.raises(EdtError, match=BUSY_MESSAGE):
        workspace.reset(ThemeChoice.KEEP)


def test_apply_writes_theme_only_when_chosen(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    assert not (workspace.settings_dir / THEME_PREFS).exists()
    workspace.apply(_dark(), ThemeChoice.DARK)
    theme = parse_prefs((workspace.settings_dir / THEME_PREFS).read_bytes().decode("latin-1"))
    assert theme["themeid"] == THEME_IDS[ThemeChoice.DARK]
    assert theme["eclipse.preferences.version"] == "1"


def test_current_reads_files_else_defaults(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.current(EDT_DEFAULTS).colors == Scheme("", EDT_DEFAULTS).colors
    workspace.apply(_dark(), ThemeChoice.KEEP)
    assert workspace.current(EDT_DEFAULTS).colors == _dark().colors


def test_reset_removes_our_keys_keeps_foreign_and_skips_missing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.reset(ThemeChoice.KEEP)
    assert not workspace.settings_dir.exists()
    workspace.settings_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "bsl-crlf.prefs", workspace.settings_dir / BSL_PREFS)
    workspace.apply(_dark(), ThemeChoice.KEEP)
    workspace.reset(ThemeChoice.KEEP)
    bsl = parse_prefs((workspace.settings_dir / BSL_PREFS).read_bytes().decode("latin-1"))
    assert set(bsl) == {"", "eclipse.preferences.version", "ï»¿"}
    editors = parse_prefs((workspace.settings_dir / EDITORS_PREFS).read_bytes().decode("latin-1"))
    assert set(editors) == {"eclipse.preferences.version"}


def test_reset_with_only_one_prefs_file_touches_only_it(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.settings_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "bsl-crlf.prefs", workspace.settings_dir / BSL_PREFS)
    workspace.reset(ThemeChoice.KEEP)
    assert not (workspace.settings_dir / EDITORS_PREFS).exists()
    bsl = parse_prefs((workspace.settings_dir / BSL_PREFS).read_bytes().decode("latin-1"))
    assert set(bsl) == {"", "eclipse.preferences.version", "ï»¿"}
    assert not list(workspace.settings_dir.glob("*.tmp"))


def test_write_failure_is_edt_error_with_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.settings_dir.parent.mkdir(parents=True)
    workspace.settings_dir.write_text("файл вместо каталога", encoding="utf-8")
    with pytest.raises(EdtError, match="Не удалось записать"):  # noqa: RUF001
        workspace.apply(_dark(), ThemeChoice.KEEP)
