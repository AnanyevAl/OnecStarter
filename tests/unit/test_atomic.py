from pathlib import Path

import pytest

from onecstarter.config.atomic import (
    ExternalChangeError,
    atomic_write,
    atomic_write_if_unchanged,
    read_with_snapshot,
)


def test_atomic_write_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"first")
    assert target.read_bytes() == b"first"
    atomic_write(target, b"second")
    assert target.read_bytes() == b"second"


def test_no_temp_files_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"data")
    assert [p.name for p in tmp_path.iterdir()] == ["ibases.v8i"]


def test_write_if_unchanged_passes_when_untouched(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"original")
    data, snapshot = read_with_snapshot(target)
    assert data == b"original"
    atomic_write_if_unchanged(target, b"updated", snapshot)
    assert target.read_bytes() == b"updated"


def test_write_if_unchanged_detects_external_change(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"original")
    _, snapshot = read_with_snapshot(target)
    target.write_bytes(b"changed by 1cestart")
    with pytest.raises(ExternalChangeError):
        atomic_write_if_unchanged(target, b"updated", snapshot)
    assert target.read_bytes() == b"changed by 1cestart"


def test_write_if_unchanged_detects_deleted_file(tmp_path: Path) -> None:
    target = tmp_path / "ibases.v8i"
    atomic_write(target, b"original")
    _, snapshot = read_with_snapshot(target)
    target.unlink()
    with pytest.raises(ExternalChangeError):
        atomic_write_if_unchanged(target, b"updated", snapshot)
