"""Доступность каталога файловой базы: выборка целей и проба ФС (спека §2, §1)."""

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from stat import S_IFDIR, S_IFREG

import pytest

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.availability import (
    DB_FILE_NAME,
    Availability,
    ProbeTarget,
    availability_hint,
    file_path_of,
    path_key,
    probe_paths,
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


def test_driveless_rooted_path_is_not_a_target() -> None:
    """`\\база` — корень без буквы диска, платформа его не разрешит однозначно.

    До Python 3.13 `os.path.isabs` и `Path.is_absolute` расходились ровно
    на этом случае; на используемой версии оба согласны — не абсолютный.
    Явная проверка `file_path_of` перед `probe_targets` — гарантия, что
    `File=` действительно разобрался в один ведущий разделитель, а не
    в UNC (`\\\\bases\\acc`, два разделителя), который абсолютен и был бы
    неверным основанием для этого теста.
    """  # noqa: RUF002
    item = _item(connect=r'File="\bases\acc";')
    assert file_path_of(item) == "\\bases\\acc"
    assert probe_targets([item]) == {}


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


# --- probe_paths: собственно проба ФС (спека §1, §3.4) --------------------


def _stat_result(mode: int) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, 0, 0, 0, 0, 0, 0))


_DIR = _stat_result(S_IFDIR | 0o755)
_FILE = _stat_result(S_IFREG | 0o644)


def _collect(
    targets: Iterable[ProbeTarget], stat: Callable[[str], os.stat_result]
) -> dict[str, Availability]:
    got: dict[str, Availability] = {}
    probe_paths(targets, stat, lambda key, state: got.__setitem__(key, state))
    return got


def test_directory_with_the_database_file_is_present() -> None:
    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], lambda _p: _DIR) == {target.key: Availability.PRESENT}


def test_missing_directory_is_missing() -> None:
    def stat(_path: str) -> os.stat_result:
        raise FileNotFoundError

    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_path_that_is_a_file_is_missing() -> None:
    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], lambda _p: _FILE) == {target.key: Availability.MISSING}


def test_permission_error_counts_as_missing() -> None:
    """Решение заказчика 09.09.2026: два состояния в исходе (спека §1).

    Отказ ФС — не отдельное «не знаю», а тот же крестик. Цена решения
    признана и записана в спеке; тест закрепляет именно её.
    """  # noqa: RUF002

    def stat(_path: str) -> os.stat_result:
        raise PermissionError

    target = ProbeTarget(path_key(r"\\srv\share\b"), r"\\srv\share\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_arbitrary_oserror_counts_as_missing() -> None:
    def stat(_path: str) -> os.stat_result:
        raise OSError(1231, "сеть недоступна")

    target = ProbeTarget(path_key(r"\\srv\share\b"), r"\\srv\share\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_directory_without_the_database_file_is_missing() -> None:
    """Каталог остался, базу перенесли — решение заказчика ловить и это (спека §2)."""

    def stat(path: str) -> os.stat_result:
        if path.endswith(DB_FILE_NAME):
            raise FileNotFoundError
        return _DIR

    target = ProbeTarget(path_key(r"D:\b"), r"D:\b")
    assert _collect([target], stat) == {target.key: Availability.MISSING}


def test_duplicate_paths_cost_one_stat() -> None:
    calls: list[str] = []

    def stat(path: str) -> os.stat_result:
        calls.append(path)
        return _DIR

    same = path_key(r"D:\b")
    _collect([ProbeTarget(same, r"D:\b"), ProbeTarget(same, r"d:/B")], stat)
    assert calls == [r"D:\b", str(Path(r"D:\b") / DB_FILE_NAME)]


def test_stat_is_called_on_the_original_value_not_the_key() -> None:
    """Проверяем ровно то, что откроет платформа, а не нашу нормализацию."""  # noqa: RUF002

    calls: list[str] = []

    def stat(path: str) -> os.stat_result:
        calls.append(path)
        return _DIR

    _collect([ProbeTarget(path_key(r"D:\b\..\b"), r"D:\b\..\b")], stat)
    assert calls[0] == r"D:\b\..\b"


def test_embedded_null_byte_does_not_abort_the_rest_of_the_walk() -> None:
    """Находка ревью Task 2: `os.stat` на пути со встроенным NUL бросает `ValueError`.

    `File=` — значение из чужого файла (`ibases.v8i` правит и платформа, и человек),
    поэтому одна порченая запись не должна погасить проверку остальных путей.
    Здесь `stat` — тестовая подмена, а не реальный `os.stat`: воспроизводим именно
    тип исключения, а не полагаемся на поведение ОС.
    """  # noqa: RUF002

    def stat(path: str) -> os.stat_result:
        if "\x00" in path:
            raise ValueError("embedded null byte")
        return _DIR

    bad_path = "D:\\b\x00ad"
    bad = ProbeTarget(path_key(bad_path), bad_path)
    good = ProbeTarget(path_key(r"D:\good"), r"D:\good")
    assert _collect([bad, good], stat) == {
        bad.key: Availability.MISSING,
        good.key: Availability.PRESENT,
    }
