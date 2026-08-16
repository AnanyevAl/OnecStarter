import pytest

from onecstarter.domain.launch import ClientKind, convention_for
from onecstarter.domain.version import parse_version
from onecstarter.platform_1c.registry import load_conventions


def test_packaged_registry_loads() -> None:
    conventions = load_conventions()
    assert len(conventions) == 1
    convention = conventions[0]
    assert convention.min_version == parse_version("8.2")
    assert convention.bin_dir == "bin"
    # [Ф] T-02.6: тонкий клиент файловой базы — 1cv8c.exe, не 1cv8s.exe.
    assert convention.executables[ClientKind.THIN] == "1cv8c.exe"
    assert convention.executables[ClientKind.THICK] == "1cv8.exe"
    assert convention.executables[ClientKind.DESIGNER] == "1cv8.exe"


def test_packaged_registry_covers_experiment_versions() -> None:
    conventions = load_conventions()
    assert convention_for(parse_version("8.3.25.1633"), conventions) is not None
    assert convention_for(parse_version("8.1.5.100"), conventions) is None


def test_custom_data_overrides_packaged_file() -> None:
    data = b"""
[[conventions]]
min_version = "9.0"
bin_dir = "app"

[conventions.executables]
thin = "client.exe"
"""
    conventions = load_conventions(data)
    assert len(conventions) == 1
    assert conventions[0].min_version == parse_version("9.0")
    assert conventions[0].executables == {ClientKind.THIN: "client.exe"}


def test_unknown_client_key_fails_loud() -> None:
    data = b"""
[[conventions]]
min_version = "8.2"
bin_dir = "bin"

[conventions.executables]
hologram = "1cv9.exe"
"""
    with pytest.raises(ValueError):
        load_conventions(data)
