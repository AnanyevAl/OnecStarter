"""Обнаружение установок EDT и JDK на диске (спека v3, §3; факты — §0).

Единственное место, где раздел «EDT» ходит по каталогам установок. Что
именно считать установкой и как выбрать JDK — решает `domain.edt`
(`version_from_dir_name`, `pick_jvm`); здесь — только сбор существующих
кандидатов.
"""  # noqa: RUF002

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from onecstarter.domain.edt import (
    EDT_EXE,
    EdtInstallation,
    java_major,
    parse_ini,
    parse_release,
    pick_jvm,
    version_from_dir_name,
)
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry

__all__ = ["default_roots", "discover_edt", "read_jdk_version"]


def default_roots(env: Mapping[str, str]) -> list[Path]:
    """Общая установка ([Ф]) и пользовательская (`productsRoot`, раскладка [?])."""
    return [
        Path(env.get("ProgramFiles", r"C:\Program Files")) / "1C" / "1CE" / "components",
        Path(env.get("LOCALAPPDATA", ".")) / "1C" / "1cedtstart" / "installations",
    ]


def read_jdk_version(jdk_root: Path) -> str | None:
    try:
        return parse_release((jdk_root / "release").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def _children(root: Path) -> list[Path]:
    try:
        return [child for child in root.iterdir() if child.is_dir()]
    except OSError:
        return []


def _auto_jdks(roots: Sequence[Path]) -> list[tuple[str, Path]]:
    """Пары «JAVA_VERSION из release, каталог bin» — выбор делает `pick_jvm`."""
    found: list[tuple[str, Path]] = []
    for root in roots:
        for child in _children(root):
            version = read_jdk_version(child)
            if version and java_major(version) is not None and (child / "bin").is_dir():
                found.append((version, child / "bin"))
    return found


def _existing_dir(path: Path | None) -> Path | None:
    return path if path is not None and path.is_dir() else None


def _ini_vm(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_file():
        return candidate.parent
    return candidate if candidate.is_dir() else None


def _read_ini(folder: Path) -> str:
    try:
        return (folder / "1cedt.ini").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def discover_edt(
    roots: Sequence[Path],
    registry: EdtStartRegistry | None,
    settings_jvm: str,
) -> list[EdtInstallation]:
    """Каталоги `1c-edt-<версия>-x86_64` с `1cedt.exe` в корнях и по `location` продуктов."""  # noqa: RUF002
    products = {
        os.path.normcase(str(product.exe)): product
        for product in (registry.products if registry is not None else ())
    }
    folders: dict[str, Path] = {}
    for root in roots:
        for child in _children(root):
            folders.setdefault(os.path.normcase(str(child / EDT_EXE)), child)
    for prod in products.values():
        folders.setdefault(os.path.normcase(str(prod.exe)), prod.exe.parent)

    auto = _auto_jdks(roots)
    settings = _existing_dir(Path(settings_jvm)) if settings_jvm else None
    found: list[EdtInstallation] = []
    for exe_key, folder in folders.items():
        version = version_from_dir_name(folder.name)
        exe = folder / EDT_EXE
        if version is None or not exe.is_file():
            continue
        ini = parse_ini(_read_ini(folder))
        product = products.get(exe_key)
        picked = pick_jvm(
            product=_existing_dir(product.jvm_dir) if product is not None else None,
            ini=_ini_vm(ini.vm),
            settings=settings,
            auto=auto,
            required_java=ini.required_java,
        )
        found.append(
            EdtInstallation(
                version=version,
                exe=exe,
                jvm_dir=picked[0] if picked else None,
                vm_args=" ".join(product.args) if product is not None else "",
                required_java=ini.required_java,
                jvm_source=picked[1] if picked else "",
            )
        )
    return sorted(found, key=lambda item: item.version, reverse=True)
