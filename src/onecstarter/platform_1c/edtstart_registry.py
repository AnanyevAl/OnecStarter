"""Реестр 1C:EDT Start — только чтение (спека v3, §6; факты — §0).

`%LOCALAPPDATA%\\1C\\1cedtstart\\products.json` — установленные EDT с JVM
и аргументами уровня «среда разработки»; `projects.json` — workspace'ы.
Разбор терпимый: неизвестные ключи игнорируются, запись без обязательных
ключей пропускается со счётчиком. В эти файлы никогда не пишем (решение
заказчика, спека §1).
"""  # noqa: RUF002

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from onecstarter.domain.edt import EdtStartProduct, EdtStartProject

__all__ = [
    "EdtStartRegistry",
    "default_edtstart_root",
    "file_url_to_path",
    "parse_products",
    "parse_projects",
    "read_registry",
]


@dataclass(frozen=True)
class EdtStartRegistry:
    products: tuple[EdtStartProduct, ...]
    projects: tuple[EdtStartProject, ...]
    skipped: int


def default_edtstart_root(env: Mapping[str, str]) -> Path:
    return Path(env.get("LOCALAPPDATA", ".")) / "1C" / "1cedtstart"


def file_url_to_path(url: str) -> Path:
    """`file:///C:/Program%20Files/x/bin/` → `C:\\Program Files\\x\\bin` ([Ф] спека §0)."""
    parsed = urlparse(url)
    raw = unquote(parsed.path)
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw[1:]
    return Path(raw.rstrip("/\\"))


def _jvm_of(entry: Mapping[str, Any]) -> Path | None:
    value = entry.get("jvmPath")
    return file_url_to_path(value) if isinstance(value, str) and value else None


def _args_of(entry: Mapping[str, Any]) -> tuple[str, ...]:
    value = entry.get("args")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _entries(text: str) -> list[Mapping[str, Any]]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def parse_products(text: str) -> list[EdtStartProduct]:
    products: list[EdtStartProduct] = []
    for entry in _entries(text):
        location = entry.get("location")
        installed = entry.get("installedVersion")
        version = installed.get("label") if isinstance(installed, dict) else None
        if not isinstance(location, str) or not isinstance(version, str):
            continue
        products.append(
            EdtStartProduct(
                id=str(entry.get("id", "")),
                version=version,
                exe=Path(location),
                jvm_dir=_jvm_of(entry),
                args=_args_of(entry),
            )
        )
    return products


def parse_projects(text: str) -> tuple[list[EdtStartProject], int]:
    projects: list[EdtStartProject] = []
    skipped = 0
    for entry in _entries(text):
        location = entry.get("location")
        product_id = entry.get("productId")
        if not isinstance(location, str) or not isinstance(product_id, str):
            skipped += 1
            continue
        projects.append(
            EdtStartProject(
                id=str(entry.get("id", "")),
                label=str(entry.get("label", "")),
                workspace=Path(location),
                product_id=product_id,
                args=_args_of(entry),
                jvm_dir=_jvm_of(entry),
            )
        )
    return projects, skipped


def read_registry(root: Path) -> EdtStartRegistry | None:
    """`None` — реестра нет или он не читается; раздел живёт без него (спека §6)."""
    products_path = root / "products.json"
    projects_path = root / "projects.json"
    try:
        products = parse_products(products_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    try:
        projects, skipped = parse_projects(projects_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        projects, skipped = [], 0
    except (OSError, ValueError):
        return None
    return EdtStartRegistry(tuple(products), tuple(projects), skipped)
