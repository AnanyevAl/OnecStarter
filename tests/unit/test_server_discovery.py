from pathlib import Path

from onecstarter.domain.server import ServerConvention
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.registry import load_server_conventions
from onecstarter.platform_1c.server_discovery import console_path, server_installations

CONV = ServerConvention(
    parse_version("8.2"), "bin", "ragent.exe", "radmin.dll", "common/1CV8 Servers (x86-64).msc"
)


def test_load_server_conventions_from_shipped_toml() -> None:
    conventions = load_server_conventions()
    assert conventions and conventions[0].ragent == "ragent.exe"


def test_filters_by_presence_of_server_components(tmp_path: Path) -> None:
    full = tmp_path / "8.3.25.1633"
    (full / "bin").mkdir(parents=True)
    (full / "bin" / "ragent.exe").write_bytes(b"")
    (full / "bin" / "radmin.dll").write_bytes(b"")
    bare = tmp_path / "8.3.27.2214"
    (bare / "bin").mkdir(parents=True)  # клиентская установка без сервера
    installations = [
        Installation(parse_version(p.name), p, Arch.X64) for p in (full, bare)
    ]
    found = server_installations(installations, [CONV])
    assert [str(item.installation.version) for item in found] == ["8.3.25.1633"]
    assert found[0].ragent == full / "bin" / "ragent.exe"


def test_console_path_is_from_root_not_version_dir(tmp_path: Path) -> None:
    assert console_path(tmp_path, CONV) == tmp_path / "common" / "1CV8 Servers (x86-64).msc"
