"""Проверка новой версии — чистая логика (T-25, спека блока 3 выпуска 3.2.3)."""

import hashlib

import pytest

from onecstarter.domain.update import (
    Release,
    is_newer,
    parse_release,
    sha256_matches,
    version_tuple,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v3.2.4", (3, 2, 4)),
        ("3.2.4", (3, 2, 4)),
        ("3.2", (3, 2)),
        ("v10.0.1", (10, 0, 1)),
        ("3.2.4-rc1", None),
        ("abc", None),
        ("", None),
        ("v", None),
    ],
)
def test_version_tuple(text: str, expected: tuple[int, ...] | None) -> None:
    assert version_tuple(text) == expected


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("3.2.4", "3.2.3", True),
        ("3.2.3", "3.2.3", False),
        ("3.2.2", "3.2.3", False),
        ("3.10.0", "3.9.9", True),  # числа, не строки
        ("4.0", "3.9.9", True),
        ("мусор", "3.2.3", False),
        ("3.2.4", "неизвестна", False),
    ],
)
def test_is_newer(latest: str, current: str, expected: bool) -> None:
    assert is_newer(latest, current) is expected


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "tag_name": "v3.2.4",
        "html_url": "https://github.com/AnanyevAl/OnecStarter/releases/tag/v3.2.4",
        "assets": [
            {
                "name": "OneCStarter-3.2.4-portable.zip",
                "browser_download_url": "https://example/portable.zip",
                "digest": "sha256:aa",
            },
            {
                "name": "OneCStarter-3.2.4-setup.exe",
                "browser_download_url": "https://example/setup.exe",
                "digest": "sha256:bb",
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_parse_release_picks_the_setup_asset() -> None:
    assert parse_release(_payload()) == Release(
        version="3.2.4",
        page_url="https://github.com/AnanyevAl/OnecStarter/releases/tag/v3.2.4",
        setup_name="OneCStarter-3.2.4-setup.exe",
        setup_url="https://example/setup.exe",
        setup_digest="sha256:bb",
    )


def test_parse_release_without_setup_asset() -> None:
    release = parse_release(_payload(assets=[]))
    assert release.setup_url is None
    assert release.setup_name is None


def test_parse_release_without_digest() -> None:
    assets = [{"name": "x-setup.exe", "browser_download_url": "https://example/x"}]
    assert parse_release(_payload(assets=assets)).setup_digest is None


@pytest.mark.parametrize("payload", [[], "x", {"html_url": "u"}, {"tag_name": 3}])
def test_parse_release_rejects_foreign_shape(payload: object) -> None:
    with pytest.raises(ValueError):
        parse_release(payload)


def test_sha256_matches() -> None:
    data = b"setup"
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    assert sha256_matches(data, digest) is True
    assert sha256_matches(data + b"!", digest) is False
    assert sha256_matches(data, None) is False
    assert sha256_matches(data, "md5:" + hashlib.md5(data).hexdigest()) is False
    assert sha256_matches(data, digest.upper().replace("SHA256", "sha256")) is True
