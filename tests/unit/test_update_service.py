"""Проверка новой версии и скачивание установщика (T-25) — без реальной сети."""

import hashlib
import json
from pathlib import Path

import pytest

from onecstarter.domain.update import Release
from onecstarter.services.errors import UpdateError
from onecstarter.services.update import (
    RELEASES_URL,
    download_verified,
    fetch_latest,
    is_installed_copy,
)

SETUP = b"MZ fake installer"


def _release(digest: str | None) -> Release:
    return Release(
        version="3.2.4",
        page_url="https://example/page",
        setup_name="OneCStarter-3.2.4-setup.exe",
        setup_url="https://example/setup.exe",
        setup_digest=digest,
    )


def test_fetch_latest_asks_releases_url() -> None:
    asked: list[str] = []

    def http_get(url: str) -> bytes:
        asked.append(url)
        return json.dumps({"tag_name": "v3.2.4", "html_url": "https://example/page"}).encode()

    assert fetch_latest(http_get).version == "3.2.4"
    assert asked == [RELEASES_URL]


def test_fetch_latest_network_failure_is_update_error() -> None:
    def http_get(_url: str) -> bytes:
        raise OSError("нет сети")

    with pytest.raises(UpdateError):
        fetch_latest(http_get)


def test_fetch_latest_garbage_is_update_error() -> None:
    with pytest.raises(UpdateError):
        fetch_latest(lambda _url: b"<html>")


def test_download_with_matching_digest_writes_the_file(tmp_path: Path) -> None:
    digest = "sha256:" + hashlib.sha256(SETUP).hexdigest()
    path = download_verified(_release(digest), tmp_path, lambda _url: SETUP)
    assert path == tmp_path / "OneCStarter-3.2.4-setup.exe"
    assert path.read_bytes() == SETUP


def test_download_with_wrong_digest_is_refused_and_leaves_no_file(tmp_path: Path) -> None:
    """Несовпавший SHA-256 — установщик не должен оказаться на диске (T-25, спека §4)."""
    digest = "sha256:" + hashlib.sha256(b"other").hexdigest()
    with pytest.raises(UpdateError):
        download_verified(_release(digest), tmp_path, lambda _url: SETUP)
    assert list(tmp_path.iterdir()) == []


def test_download_without_digest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UpdateError):
        download_verified(_release(None), tmp_path, lambda _url: SETUP)
    assert list(tmp_path.iterdir()) == []


def test_download_network_failure_is_update_error(tmp_path: Path) -> None:
    def http_get(_url: str) -> bytes:
        raise OSError("обрыв")

    digest = "sha256:" + hashlib.sha256(SETUP).hexdigest()
    with pytest.raises(UpdateError):
        download_verified(_release(digest), tmp_path, http_get)


def test_installed_copy_is_recognised_by_uninstaller(tmp_path: Path) -> None:
    assert is_installed_copy(tmp_path) is False
    (tmp_path / "unins000.exe").write_bytes(b"")
    assert is_installed_copy(tmp_path) is True
