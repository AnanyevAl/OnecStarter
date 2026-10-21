"""Набор схем в поставке (T-24.1): base16, MIT, готовые .csi."""  # noqa: RUF002

from onecstarter.domain.edt_scheme import COLOR_KEYS
from onecstarter.services.edt_scheme import SchemeCatalog, bundled_schemes_dir, load_entry


def test_bundled_set_is_present_with_license() -> None:
    root = bundled_schemes_dir()
    assert (root / "base16" / "LICENSE").is_file()
    assert (root / "base16" / "SOURCE.md").is_file()


def test_every_bundled_scheme_loads_with_full_palette() -> None:
    entries = SchemeCatalog(str(bundled_schemes_dir())).entries()
    assert len(entries) >= 300
    for entry in entries:
        assert entry.kind == "csi"
        scheme = load_entry(entry)
        assert len(scheme.colors) == len(COLOR_KEYS), entry.name
