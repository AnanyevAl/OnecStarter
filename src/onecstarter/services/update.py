"""Проверка новой версии на GitHub и скачивание установщика (T-25). Без Qt.

Спека — docs/superpowers/specs/2026-10-20-v323-block3-update-check-design.md.

Сеть подаётся аргументом `http_get` — в тестах реальных запросов нет. По умолчанию —
`urllib_get`: только `User-Agent` с версией и `Accept`, никаких данных о пользователе
(обещание §4 требований). Прокси — системный: `urllib.request` на Windows читает его
из реестра.

Ошибки наружу — только `UpdateError` с причиной без путей пользователя (инвариант 5).
"""  # noqa: RUF002

import json
import urllib.request
from collections.abc import Callable
from pathlib import Path

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.update import Release, parse_release, sha256_matches
from onecstarter.services.errors import UpdateError

__all__ = [
    "RELEASES_URL",
    "HttpGet",
    "download_verified",
    "fetch_latest",
    "is_installed_copy",
    "urllib_get",
]

RELEASES_URL = "https://api.github.com/repos/AnanyevAl/OnecStarter/releases/latest"
UNINSTALLER_NAME = "unins000.exe"

HttpGet = Callable[[str], bytes]


def urllib_get(url: str, *, version: str, timeout: float = 10.0) -> bytes:
    """GET без данных о пользователе: только версия программы в `User-Agent`."""  # noqa: RUF002
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"OneCStarter/{version}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data: bytes = response.read()
        return data


def fetch_latest(http_get: HttpGet) -> Release:
    """Последний выпуск. Сеть, прокси, лимит, чужой ответ — `UpdateError`."""
    try:
        payload = json.loads(http_get(RELEASES_URL))
        return parse_release(payload)
    except OSError as error:
        raise UpdateError(f"нет связи с GitHub ({type(error).__name__})") from error  # noqa: RUF001
    except ValueError as error:
        raise UpdateError(f"неожиданный ответ GitHub: {error}") from error


def download_verified(release: Release, directory: Path, http_get: HttpGet) -> Path:
    """Скачать установщик и сверить SHA-256 с `digest` GitHub; не совпал — файла нет.

    Файл пишется только после проверки (`atomic_write`), поэтому подменённый или
    битый установщик на диске не появляется вовсе.
    """  # noqa: RUF002
    if release.setup_url is None or release.setup_name is None:
        raise UpdateError("в выпуске нет установщика")
    if release.setup_digest is None:
        raise UpdateError("GitHub не сообщил контрольную сумму установщика — запуск небезопасен")
    try:
        data = http_get(release.setup_url)
    except OSError as error:
        raise UpdateError(f"не удалось скачать установщик ({type(error).__name__})") from error
    if not sha256_matches(data, release.setup_digest):
        raise UpdateError("контрольная сумма установщика не совпала — файл отброшен")
    path = directory / release.setup_name
    try:
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write(path, data)
    except OSError as error:
        raise UpdateError(f"не удалось сохранить установщик ({type(error).__name__})") from error
    return path


def is_installed_copy(exe_dir: Path) -> bool:
    """Поставлено ли установщиком: Inno Setup кладёт деинсталлятор рядом с exe."""  # noqa: RUF002
    return (exe_dir / UNINSTALLER_NAME).is_file()
