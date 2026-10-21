"""Проверка новой версии — чистая логика, без сети и без Qt (T-25).

Спека — docs/superpowers/specs/2026-10-20-v323-block3-update-check-design.md.
Ответ GitHub `releases/latest` разбирается здесь; запрос и скачивание — в
`services/update.py`.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["Release", "is_newer", "parse_release", "sha256_matches", "version_tuple"]

_VERSION = re.compile(r"v?(\d+(?:\.\d+)*)")
SETUP_SUFFIX = "-setup.exe"


@dataclass(frozen=True)
class Release:
    """Выпуск на GitHub: версия без «v», страница и ассет установщика, если он есть."""

    version: str
    page_url: str
    setup_name: str | None
    setup_url: str | None
    setup_digest: str | None


def version_tuple(text: str) -> tuple[int, ...] | None:
    """`v3.2.4` → `(3, 2, 4)`. Суффиксы (`-rc1`) и прочее — `None`: не сравниваем."""
    match = _VERSION.fullmatch(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str) -> bool:
    """Новее ли `latest`, чем `current`. Неразбираемая сторона — «нет»."""
    latest_parts = version_tuple(latest)
    current_parts = version_tuple(current)
    if latest_parts is None or current_parts is None:
        return False
    return latest_parts > current_parts


def parse_release(payload: object) -> Release:
    """Ответ `releases/latest` → `Release`. Чужая форма — `ValueError`."""
    if not isinstance(payload, Mapping):
        raise ValueError("ответ GitHub — не объект")
    tag = payload.get("tag_name")
    page = payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(page, str):
        raise ValueError("в ответе GitHub нет tag_name или html_url")
    setup: Mapping[str, object] | None = None
    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            name = asset.get("name") if isinstance(asset, Mapping) else None
            if isinstance(name, str) and name.endswith(SETUP_SUFFIX):
                setup = asset
                break
    name = setup.get("name") if setup is not None else None
    url = setup.get("browser_download_url") if setup is not None else None
    digest = setup.get("digest") if setup is not None else None
    return Release(
        version=tag.removeprefix("v"),
        page_url=page,
        setup_name=name if isinstance(name, str) else None,
        setup_url=url if isinstance(url, str) else None,
        setup_digest=digest if isinstance(digest, str) else None,
    )


def sha256_matches(data: bytes, digest: str | None) -> bool:
    """Совпадает ли SHA-256 данных с `digest` GitHub (`sha256:<hex>`). Иной вид — нет."""  # noqa: RUF002
    if digest is None:
        return False
    kind, _sep, expected = digest.partition(":")
    if kind.lower() != "sha256" or not expected:
        return False
    return hashlib.sha256(data).hexdigest() == expected.lower()
