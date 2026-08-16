import codecs
from collections.abc import Iterator
from pathlib import Path

import pytest

from onecstarter.domain.launch import ClientConvention, ClientKind
from onecstarter.domain.version import Arch, parse_version
from onecstarter.platform_1c.discovery import (
    cfg_paths,
    default_roots,
    discover_installations,
    executable_arch,
    find_installations,
    installed_location_roots,
)

CONVENTIONS = [
    ClientConvention(
        min_version=parse_version("8.2"),
        bin_dir="bin",
        executables={ClientKind.THIN: "1cv8c.exe", ClientKind.THICK: "1cv8.exe"},
    )
]


def _fake_pe(machine: int) -> bytes:
    header = bytearray(64)
    header[0:2] = b"MZ"
    header[60:64] = (64).to_bytes(4, "little")
    return bytes(header) + b"PE\x00\x00" + machine.to_bytes(2, "little")


def _make_installation(root: Path, version: str, machine: int = 0x8664) -> None:
    bin_dir = root / version / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "1cv8.exe").write_bytes(_fake_pe(machine))


def test_executable_arch_x64_and_x86(tmp_path: Path) -> None:
    x64 = tmp_path / "x64.exe"
    x64.write_bytes(_fake_pe(0x8664))
    x86 = tmp_path / "x86.exe"
    x86.write_bytes(_fake_pe(0x14C))
    assert executable_arch(x64) is Arch.X64
    assert executable_arch(x86) is Arch.X86


def test_executable_arch_garbage_is_unknown(tmp_path: Path) -> None:
    not_pe = tmp_path / "data.exe"
    not_pe.write_bytes(b"\x00" * 128)
    assert executable_arch(not_pe) is Arch.UNKNOWN
    assert executable_arch(tmp_path / "missing.exe") is Arch.UNKNOWN


def test_discover_validates_layout_not_just_name(tmp_path: Path) -> None:
    _make_installation(tmp_path, "8.3.25.1633")
    _make_installation(tmp_path, "8.3.10.2252", machine=0x14C)
    (tmp_path / "common").mkdir()  # служебный каталог — не версия
    (tmp_path / "8.3.27.2214").mkdir()  # имя-версия без bin\1cv8.exe — не установка
    installations = discover_installations([tmp_path], CONVENTIONS)
    assert [str(item.version) for item in installations] == ["8.3.10.2252", "8.3.25.1633"]
    assert installations[0].arch is Arch.X86
    assert installations[1].arch is Arch.X64
    assert installations[1].path == tmp_path / "8.3.25.1633"


def test_discover_first_root_wins_for_duplicate_version(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _make_installation(first, "8.3.25.1633")
    _make_installation(second, "8.3.25.1633")
    installations = discover_installations([first, second], CONVENTIONS)
    assert len(installations) == 1
    assert installations[0].path == first / "8.3.25.1633"


def test_discover_survives_missing_root(tmp_path: Path) -> None:
    assert discover_installations([tmp_path / "нет"], CONVENTIONS) == []


def test_discover_survives_unreadable_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Корень из InstalledLocation может быть недоступен: права или отвалившийся
    # сетевой диск. Такой корень пропускается, остальные сканируются.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    good = tmp_path / "good"
    _make_installation(good, "8.3.25.1633")
    original = Path.iterdir

    def fake_iterdir(self: Path) -> Iterator[Path]:
        if self == blocked:
            raise PermissionError(13, "Отказано в доступе")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    installations = discover_installations([blocked, good], CONVENTIONS)
    assert [str(item.version) for item in installations] == ["8.3.25.1633"]


def test_installed_location_key_is_case_insensitive() -> None:
    entries = [
        ("InstalledLocation", r"C:\Program Files\1cv8"),
        ("INSTALLEDLOCATION", r"D:\1cv8"),
        ("DefaultVersion", "8.3"),
    ]
    assert installed_location_roots(entries) == [
        Path(r"C:\Program Files\1cv8"),
        Path(r"D:\1cv8"),
    ]


def test_cfg_paths_and_default_roots() -> None:
    env = {
        "ALLUSERSPROFILE": r"C:\ProgramData",
        "APPDATA": r"C:\Users\demo\AppData\Roaming",
        "ProgramFiles": r"C:\Program Files",
    }
    assert cfg_paths(env) == [
        Path(r"C:\ProgramData\1C\1CEStart\1cestart.cfg"),
        Path(r"C:\Users\demo\AppData\Roaming\1C\1CEStart\1cestart.cfg"),
    ]
    assert default_roots(env) == [Path(r"C:\Program Files\1cv8")]


def test_find_installations_reads_cfg_and_defaults(tmp_path: Path) -> None:
    custom_root = tmp_path / "custom"
    _make_installation(custom_root, "8.3.25.1633")
    default_root = tmp_path / "pf" / "1cv8"
    _make_installation(default_root, "8.3.22.1923")
    appdata = tmp_path / "appdata"
    cfg_dir = appdata / "1C" / "1CEStart"
    cfg_dir.mkdir(parents=True)
    cfg_text = f"InstalledLocation={custom_root}\r\n"
    (cfg_dir / "1cestart.cfg").write_bytes(
        codecs.BOM_UTF16_LE + cfg_text.encode("utf-16-le")
    )
    env = {"APPDATA": str(appdata), "ProgramFiles": str(tmp_path / "pf")}
    installations = find_installations(env, CONVENTIONS)
    assert [str(item.version) for item in installations] == ["8.3.22.1923", "8.3.25.1633"]
