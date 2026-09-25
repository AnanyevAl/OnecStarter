"""Обнаружение установок EDT и JDK на диске (спека v3, §3; факты — §0).

Единственное место, где раздел «EDT» ходит по каталогам установок. Что
именно считать установкой и как выбрать JDK — решает `domain.edt`
(`version_from_dir_name`, `pick_jvm`); здесь — только сбор существующих
кандидатов.
"""  # noqa: RUF002

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from onecstarter.domain.edt import (
    EDT_EXE,
    EdtInstallation,
    parse_ini,
    parse_release,
    pick_jvm,
    version_from_dir_name,
)
from onecstarter.platform_1c.edtstart_registry import EdtStartRegistry

__all__ = ["EdtRoot", "default_roots", "discover_edt", "find_installations", "read_jdk_version"]


@dataclass(frozen=True)
class EdtRoot:
    """Корень скана и его глубина.

    Глубина у каждого корня своя, потому что раскладку задают разные хозяева:
    у `components` её задаёт установщик 1С и она проверена [Ф], у корней,
    которые лепит человек, она неизвестна (спека §1.3, §1.5).
    """  # noqa: RUF002

    path: Path
    max_depth: int


def default_roots(env: Mapping[str, str]) -> list[EdtRoot]:
    """Общая установка ([Ф]) и пользовательская (`productsRoot`, раскладка [?]).

    Глубина — своя у каждого корня (спека §1.3): у `components` раскладку задаёт
    установщик 1С и она проверена [Ф] — exe на уровне 1, глубины 2 хватает с запасом.
    У пользовательского каталога раскладка неизвестна и проверить её нечем [?] —
    глубина 3, и на таком узком корне это стоит четыре сотых миллисекунды [Ф].
    """  # noqa: RUF002
    components = Path(env.get("ProgramFiles", r"C:\Program Files")) / "1C" / "1CE" / "components"
    installations = Path(env.get("LOCALAPPDATA", ".")) / "1C" / "1cedtstart" / "installations"
    return [EdtRoot(components, 2), EdtRoot(installations, 3)]


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


def _is_installation(folder: Path) -> bool:
    return (folder / EDT_EXE).is_file()


def _is_jdk(folder: Path) -> bool:
    """Каталог JDK: файл `release` И подкаталог `bin`.

    Одного `release` мало: файл с таким именем встречается и в чужих каталогах,
    а обрывать на нём обход значило бы терять установки под ним.
    """  # noqa: RUF002
    return (folder / "release").is_file() and (folder / "bin").is_dir()


def find_installations(root: EdtRoot) -> tuple[list[Path], list[tuple[str, Path]]]:
    """Каталоги установок и каталоги JDK одним обходом.

    Обход останавливается на обоих видах листьев: внутрь найденной установки
    (`plugins`, `features`, `p2`) и внутрь JDK не заходим. Отсечение ветки JDK —
    не микрооптимизация: без него глубина 3 на `components` стоит 48,6 мс
    и 246 каталогов вместо 23,1 мс и 63 [Ф]. Заодно оно снимает нужду в отдельном
    проходе `_auto_jdks` по тем же корням — эту работу теперь делает один обход.

    Уровень 0 (сам корень) проверяется тоже: путь, указанный прямо на каталог
    установки, обязан работать независимо от того, угадали мы глубину или нет
    (спека §1.5, запасной выход вехи).
    """
    installations: list[Path] = []
    jdks: list[tuple[str, Path]] = []

    def walk(folder: Path, depth: int) -> None:
        if _is_installation(folder):
            installations.append(folder)
            return
        if _is_jdk(folder):
            version = read_jdk_version(folder)
            if version is not None:
                jdks.append((version, folder))
            return
        if depth >= root.max_depth:
            return
        for child in _children(folder):
            walk(child, depth + 1)

    if not root.path.is_dir():
        return [], []
    walk(root.path, 0)
    return installations, jdks


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
