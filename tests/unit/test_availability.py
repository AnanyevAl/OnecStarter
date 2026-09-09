"""Выборка целей проверки доступности: что проверяем и что нет (спека §2)."""

import pytest

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.availability import (
    Availability,
    ProbeTarget,
    availability_hint,
    file_path_of,
    path_key,
    probe_targets,
    relative_path_note,
)
from onecstarter.services.model import InfobaseItem, InfobaseSource


def _item(
    key: str = "id:a",
    connect: str | None = r'File="D:\bases\acc";',
    kind: ConnectKind = ConnectKind.FILE,
    is_group: bool = False,
) -> InfobaseItem:
    return InfobaseItem(
        key=key,
        name="База",
        folder="/",
        is_group=is_group,
        connect=connect,
        kind=kind,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id=None,
    )


def test_file_base_with_absolute_path_is_a_target() -> None:
    targets = probe_targets([_item()])
    assert targets == {"id:a": ProbeTarget(path_key(r"D:\bases\acc"), r"D:\bases\acc")}


def test_unc_path_is_a_target_too() -> None:
    """UNC абсолютен по `os.path.isabs` и проверяется наравне с локальным (спека §2)."""  # noqa: RUF002
    item = _item(connect=r'File="\\srv\share\acc";')
    assert list(probe_targets([item])) == ["id:a"]


@pytest.mark.parametrize(
    "kind",
    [ConnectKind.SERVER, ConnectKind.WEB, ConnectKind.UNKNOWN],
)
def test_non_file_kinds_are_not_targets(kind: ConnectKind) -> None:
    assert probe_targets([_item(kind=kind)]) == {}


def test_group_is_not_a_target() -> None:
    assert probe_targets([_item(connect=None, is_group=True)]) == {}


def test_empty_file_fragment_is_not_a_target() -> None:
    assert probe_targets([_item(connect='File="";')]) == {}


def test_relative_path_is_not_a_target() -> None:
    """Относительно чего платформа его разрешает — [Д], замера нет (спека §2)."""  # noqa: RUF002
    assert probe_targets([_item(connect='File="bases\\acc";')]) == {}


def test_drive_relative_path_is_not_a_target() -> None:
    """`D:база` — относительный от текущего каталога диска, не абсолютный."""
    assert probe_targets([_item(connect='File="D:acc";')]) == {}


def test_two_bases_in_one_directory_share_one_path_key() -> None:
    first = _item(key="id:a", connect=r'File="D:\bases\acc";')
    second = _item(key="id:b", connect=r'File="d:/BASES/acc";')
    targets = probe_targets([first, second])
    assert targets["id:a"].key == targets["id:b"].key


def test_file_path_of_returns_none_for_non_file_records() -> None:
    assert file_path_of(_item(kind=ConnectKind.SERVER)) is None
    assert file_path_of(_item(connect=None, is_group=True)) is None


def test_relative_path_note_only_for_relative_file_records() -> None:
    assert relative_path_note(_item(connect='File="bases\\acc";')) == (
        "Путь относительный — доступность не проверялась"
    )
    assert relative_path_note(_item()) is None
    assert relative_path_note(_item(kind=ConnectKind.SERVER)) is None


def test_availability_hint_speaks_only_about_missing() -> None:
    assert availability_hint(Availability.MISSING, r"D:\b") == r"Каталог не найден: D:\b"
    assert availability_hint(Availability.PRESENT, r"D:\b") is None
    assert availability_hint(Availability.UNKNOWN, r"D:\b") is None
