"""Витрина размещения: подпись вида и путь подключения."""

import pytest

from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.services.connection import (
    _DIRTY_URL_NOTE,
    BADGE_LABELS,
    KIND_WORDS,
    connection_path,
    panel_card,
)
from onecstarter.services.display import RowKind
from onecstarter.services.model import InfobaseItem, InfobaseSource


def _base(connect: str | None, *, is_group: bool = False) -> InfobaseItem:
    return InfobaseItem(
        key="id:x",
        name="База",
        folder="/",
        is_group=is_group,
        connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id="x",
    )


def test_every_kind_has_a_label() -> None:
    """UNKNOWN обязан отличаться от трёх известных, а не быть «прочим»."""  # noqa: RUF002
    assert set(BADGE_LABELS) == set(ConnectKind)
    assert BADGE_LABELS[ConnectKind.UNKNOWN] == "строку соединения не разобрали"


@pytest.mark.parametrize(
    ("connect", "text", "directory"),
    [
        (r'File="D:\bases\acc";', r"D:\bases\acc", r"D:\bases\acc"),
        ('Srvr="localhost";Ref="ACC";', 'Srvr="localhost";Ref="ACC"', None),
        ('Srvr="localhost";', 'Srvr="localhost"', None),
        ('ws="http://srv/base";', "http://srv/base", None),
        ('ws="http://user:pass@srv/base";', "http://srv/base", None),
        # Порядок фрагментов в панели наш, а не файловый: Srvr, потом Ref —  # noqa: RUF003
        # так их показывает штатный стартер, с ним и сверяется пользователь.  # noqa: RUF003
        ('Ref="ACC";Srvr="localhost";', 'Srvr="localhost";Ref="ACC"', None),
        # Лишние параметры в панель не идут вовсе (решение заказчика 07.08.2026).
        (r'File="D:\b";Usr="admin";Pwd="s3";', r"D:\b", r"D:\b"),
        # Круг правок 3: пробел после «;» — обычное форматирование, панель  # noqa: RUF003
        # обязана показать оба фрагмента, не только первый.  # noqa: RUF003
        ('Srvr="localhost"; Ref="ACC";', 'Srvr="localhost";Ref="ACC"', None),
    ],
)
def test_connection_path_shows_only_placement(
    connect: str, text: str, directory: str | None
) -> None:
    path = connection_path(_base(connect))
    assert path.text == text
    assert path.directory == directory
    assert path.note is None
    assert path.copyable


@pytest.mark.parametrize(
    ("connect", "is_group"),
    [(None, True), ('Srvr="x";', True), (None, False)],
)
def test_groups_and_connectless_records_show_nothing(connect: str | None, is_group: bool) -> None:
    path = connection_path(_base(connect, is_group=is_group))
    assert path.text == ""
    assert not path.copyable


def test_unknown_kind_gets_a_note_not_a_path() -> None:
    """Полная строка Connect в 4b не показывается и не копируется (§1.4)."""
    path = connection_path(_base("Нечто=1;"))
    assert path.text == ""
    assert path.note == "Строка соединения не распознана"
    assert not path.copyable


def test_web_with_unstrippable_credentials_is_hidden() -> None:
    path = connection_path(_base('ws="user:pass@srv/base";'))
    assert path.text == ""
    assert path.note == _DIRTY_URL_NOTE
    assert not path.copyable


def test_web_with_unparseable_address_gets_the_same_honest_note() -> None:
    """Битый порт: strip_url_credentials тоже даёт None, а «@» в адресе нет —

    пометка не вправе лгать про причину (находка ревью задачи 4).
    """  # noqa: RUF002
    path = connection_path(_base('ws="http://srv:abc/base";'))
    assert path.text == ""
    assert path.note == _DIRTY_URL_NOTE
    assert "@" not in path.note
    assert not path.copyable


def test_empty_file_fragment_is_reported() -> None:
    path = connection_path(_base('File="";'))
    assert path.text == ""
    assert path.note == "В строке соединения пустой путь к базе"  # noqa: RUF001


def test_empty_ws_fragment_is_reported() -> None:
    """Симметрично File="": classify_connect даёт WEB по одному ключу ws."""
    path = connection_path(_base('ws="";'))
    assert path.text == ""
    assert path.note == "В строке соединения пустой адрес публикации (ws)"  # noqa: RUF001
    assert not path.copyable


# Helpers for panel_card tests
def _entry(
    connect: str | None, *, is_group: bool = False, name: str = "База"
) -> InfobaseItem:
    return InfobaseItem(
        key="id:x",
        name=name,
        folder="/",
        is_group=is_group,
        connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id="x",
    )


def _group(name: str) -> InfobaseItem:
    return _entry(None, is_group=True, name=name)


def test_panel_card_for_a_server_base() -> None:
    card = panel_card(RowKind.BASE, _base('Srvr="s";Ref="r";'), "не важно")
    assert card.title == "База"
    assert card.kind_word == "серверная"
    assert card.icon_kind is ConnectKind.SERVER
    assert card.path is not None and card.path.text == 'Srvr="s";Ref="r"'
    assert card.hint is None
    assert card.show_actions is True


def test_panel_card_for_a_group() -> None:
    card = panel_card(RowKind.GROUP, _group("Клиенты"), "Клиенты")
    assert card.title == "Клиенты"
    assert card.kind_word == "группа"
    assert card.icon_kind is None
    assert card.path is None
    assert card.hint == "Группа — строки подключения нет"
    assert card.show_actions is False


def test_panel_card_for_an_implicit_node_uses_the_label() -> None:
    card = panel_card(RowKind.IMPLICIT_GROUP, None, "Нет такой группы")
    assert card.title == "Нет такой группы"
    assert card.kind_word == "неявный узел"
    assert card.hint == (
        "Группы нет в файле — есть только путь Folder. Операции недоступны"
    )
    assert card.show_actions is False


@pytest.mark.parametrize("kind", [RowKind.SECTION, RowKind.NOTE, None])
def test_panel_card_for_service_rows_asks_to_pick_a_base(
    kind: RowKind | None,
) -> None:
    card = panel_card(kind, None, "Избранное")
    assert card.title is None
    assert card.hint == "Выберите базу, чтобы увидеть путь подключения"
    assert card.show_actions is False


def test_panel_card_for_a_vanished_base_degrades_to_the_empty_card() -> None:
    """Запись пропала между rebuild и синхронизацией панели — не падать."""
    card = panel_card(RowKind.BASE, None, "Демо")
    assert card.title is None
    assert card.show_actions is False


def test_panel_card_for_base_kind_on_a_group_item_degrades_to_the_empty_card() -> None:
    """RowKind.BASE, наведённый на групповую запись, — деградация, не путаница.

    На практике модель не даёт такого сочетания (BASE-строка всегда указывает
    на не-группу), но `panel_card` обязана сама решать по `item.is_group`,
    а не доверять слепо виду строки: не `not item.is_group` — panel_card
    показала бы группу как базу, с путём, которого у группы нет.
    """  # noqa: RUF002
    card = panel_card(RowKind.BASE, _group("Клиенты"), "x")
    assert card.title is None
    assert card.hint == "Выберите базу, чтобы увидеть путь подключения"
    assert card.show_actions is False


def test_kind_words_cover_every_connect_kind() -> None:
    assert {kind: KIND_WORDS[kind] for kind in ConnectKind} == {
        ConnectKind.FILE: "файловая",
        ConnectKind.SERVER: "серверная",
        ConnectKind.WEB: "веб",
        ConnectKind.UNKNOWN: "не разобрано",
    }
