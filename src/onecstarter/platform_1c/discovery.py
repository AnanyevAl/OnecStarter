"""Обнаружение установленных версий платформы.

Источник истины — файловая система: реестровых ключей 1С может не быть
даже при семи установленных версиях ([Ф] скил platform-launch, факт 2).
Каталог признаётся установкой, только если его имя разбирается как номер
версии И на месте толстый клиент по соглашению раскладки.

Ограничение v1: общий 1cescmn.cfg не читается — его расположение
не подтверждено на реальной машине (решение 6 плана 2). Читаются два
1cestart.cfg в порядке уровней InstalledLocation из ИТС:
для всех пользователей → локальный. Пути конфигурации пробуются
в порядке ALLUSERSPROFILE → APPDATA, к ним добавляются каталоги
по умолчанию ProgramFiles → ProgramFiles(x86).
"""  # noqa: RUF002

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from onecstarter.config.cestart_cfg import parse_cestart_cfg
from onecstarter.domain.launch import ClientConvention, ClientKind, convention_for
from onecstarter.domain.version import Arch, Installation, VersionNumber, parse_version

_PE_MACHINE = {0x8664: Arch.X64, 0x14C: Arch.X86}
_MZ_HEADER_SIZE = 64


def cfg_paths(env: Mapping[str, str]) -> list[Path]:
    paths: list[Path] = []
    for variable in ("ALLUSERSPROFILE", "APPDATA"):
        root = env.get(variable)
        if root:
            paths.append(Path(root) / "1C" / "1CEStart" / "1cestart.cfg")
    return paths


def default_roots(env: Mapping[str, str]) -> list[Path]:
    roots: list[Path] = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = env.get(variable)
        if base:
            roots.append(Path(base) / "1cv8")
    return roots


def installed_location_roots(entries: Iterable[tuple[str, str]]) -> list[Path]:
    return [
        Path(value) for key, value in entries if key.casefold() == "installedlocation"
    ]


def executable_arch(path: Path) -> Arch:
    try:
        with path.open("rb") as file:
            header = file.read(_MZ_HEADER_SIZE)
            if len(header) < _MZ_HEADER_SIZE or header[:2] != b"MZ":
                return Arch.UNKNOWN
            pe_offset = int.from_bytes(header[60:64], "little")
            file.seek(pe_offset)
            signature = file.read(6)
    except OSError:
        return Arch.UNKNOWN
    if len(signature) < 6 or signature[:4] != b"PE\x00\x00":
        return Arch.UNKNOWN
    machine = int.from_bytes(signature[4:6], "little")
    return _PE_MACHINE.get(machine, Arch.UNKNOWN)


def discover_installations(
    roots: Iterable[Path], conventions: Sequence[ClientConvention]
) -> list[Installation]:
    found: dict[VersionNumber, Installation] = {}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            # Корень из InstalledLocation может быть недоступен: права
            # или отвалившийся сетевой диск. Пропускаем, скан продолжается.
            continue
        for child in children:
            if not child.is_dir():
                continue
            try:
                version = parse_version(child.name)
            except ValueError:
                continue
            if version in found:
                continue
            convention = convention_for(version, conventions)
            if convention is None:
                continue
            marker = convention.executables.get(ClientKind.THICK)
            if marker is None:
                continue
            executable = child / convention.bin_dir / marker
            if not executable.is_file():
                continue
            found[version] = Installation(
                version=version, path=child, arch=executable_arch(executable)
            )
    return sorted(found.values(), key=lambda item: item.version)


def find_installations(
    env: Mapping[str, str], conventions: Sequence[ClientConvention]
) -> list[Installation]:
    entries: list[tuple[str, str]] = []
    for cfg in cfg_paths(env):
        try:
            entries.extend(parse_cestart_cfg(cfg.read_bytes()))
        except OSError:
            continue
    roots = installed_location_roots(entries) + default_roots(env)
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return discover_installations(unique, conventions)
