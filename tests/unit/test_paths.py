import pytest

from onecstarter.services.paths import (
    ROOT,
    group_path,
    is_inside,
    normalize_folder,
    render_folder,
    retarget,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ROOT),
        ("", ROOT),
        ("   ", ROOT),
        ("/", ROOT),
        ("//", ROOT),
        ("/Клиенты", "Клиенты"),
        ("Клиенты", "Клиенты"),
        ("/Клиенты/Розница/", "Клиенты/Розница"),
    ],
)
def test_normalize_folder(raw: str | None, expected: str) -> None:
    assert normalize_folder(raw) == expected


def test_group_path_of_root_group_is_its_name() -> None:
    assert group_path("/", "Клиенты") == "Клиенты"


def test_group_path_appends_name_to_parent() -> None:
    assert group_path("/Клиенты", "Розница") == "Клиенты/Розница"


@pytest.mark.parametrize(
    ("path", "ancestor", "expected"),
    [
        ("Клиенты", "Клиенты", True),
        ("Клиенты/Розница", "Клиенты", True),
        ("КлиентыVIP", "Клиенты", False),  # noqa: RUF001
        ("КлиентыVIP/Опт", "Клиенты", False),  # noqa: RUF001
        ("Клиенты", "Клиенты/Розница", False),
        ("Клиенты", ROOT, True),
    ],
)
def test_is_inside_compares_by_segments(path: str, ancestor: str, expected: bool) -> None:
    """`Клиенты` и `КлиентыVIP` совпадают как префиксы строк, но потомками
    друг другу не приходятся: наивный startswith утащил бы чужую ветку.
    """  # noqa: RUF002
    assert is_inside(path, ancestor) is expected


@pytest.mark.parametrize(
    ("path", "old", "new", "expected"),
    [
        ("Клиенты", "Клиенты", "Партнёры", "Партнёры"),
        ("Клиенты/Розница", "Клиенты", "Партнёры", "Партнёры/Розница"),
        ("Клиенты/Розница/Опт", "Клиенты", "Архив/Партнёры", "Архив/Партнёры/Розница/Опт"),
        ("КлиентыVIP", "Клиенты", "Партнёры", "КлиентыVIP"),  # noqa: RUF001
        ("Клиенты/Розница", "Клиенты", ROOT, "Розница"),
        ("Клиенты", "Клиенты", ROOT, ROOT),
        (ROOT, ROOT, "Архив", "Архив"),
        ("Клиенты", ROOT, "Архив", "Архив/Клиенты"),
    ],
)
def test_retarget_replaces_ancestor_prefix(
    path: str, old: str, new: str, expected: str
) -> None:
    assert retarget(path, old, new) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [(ROOT, "/"), ("Клиенты", "/Клиенты"), ("Клиенты/Розница", "/Клиенты/Розница")],
)
def test_render_folder_writes_leading_slash(path: str, expected: str) -> None:
    """[Ф] мастер стартера пишет `Folder=/` и `Folder=/<путь родителя>`."""
    assert render_folder(path) == expected
