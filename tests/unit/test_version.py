from pathlib import Path

import pytest

from onecstarter.domain.version import Arch, Installation, VersionNumber, parse_version


def test_parse_full_version() -> None:
    version = parse_version("8.3.25.1633")
    assert version.parts == (8, 3, 25, 1633)
    assert version.is_full
    assert str(version) == "8.3.25.1633"


def test_parse_mask_is_not_full() -> None:
    assert not parse_version("8.3.25").is_full
    assert not parse_version("8.3").is_full


@pytest.mark.parametrize(
    "bad",
    ["", "8.", ".8", "8..3", "8.3a", "8. 3", "v8.3", "8,3", "8.3.25.1633 "],
)
def test_parse_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError, match="версии"):
        parse_version(bad)


def test_numeric_component_order() -> None:
    # Лексикографически 8.3.9 > 8.3.18 > 8.3.10 — числовой порядок обратный
    # (факт 5 скила platform-launch).
    assert parse_version("8.3.9") < parse_version("8.3.10") < parse_version("8.3.18")


def test_starts_with_compares_tuples_not_strings() -> None:
    mask = parse_version("8.3.25")
    assert parse_version("8.3.25.1633").starts_with(mask)
    # startswith по строке поймал бы 8.3.250.1 — по кортежам не должен.
    assert not parse_version("8.3.250.1").starts_with(mask)


def test_starts_with_longer_prefix_is_false() -> None:
    assert not parse_version("8.3.25").starts_with(parse_version("8.3.25.1633"))


def test_installation_holds_data() -> None:
    installation = Installation(
        version=parse_version("8.3.25.1633"),
        path=Path("C:/Program Files/1cv8/8.3.25.1633"),
        arch=Arch.X64,
    )
    assert installation.arch is Arch.X64
    assert installation.version == VersionNumber((8, 3, 25, 1633))
