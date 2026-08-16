"""Витрина размещения записи: подпись вида и путь подключения.

Отдельно от `display.py` намеренно: тот отвечает за дерево и его строки,
здесь — разбор строки соединения. Одна ось на модуль.

Панель показывает **только путь подключения, без дополнительных параметров**
(решение заказчика 07.08.2026). Из `Connect` берутся `File` для файловой,
`Srvr` и `Ref` для серверной, `ws` для веб-базы; `Usr`, `Pwd`, `LocaleCode`,
`wsp*` и неизвестные ключи не попадают сюда вовсе. Это снимает вопрос
маскировки для FILE и SERVER: секретов в фрагментах размещения нет
по построению. Остаётся веб-база — её адрес может нести учётные данные,
и их вырезает `security.strip_url_credentials`.

С рестайла 15.08.2026 модуль отдаёт и карточку панели целиком (`panel_card`)
— по-прежнему без Qt.
"""  # noqa: RUF002

from collections.abc import Mapping
from dataclasses import dataclass

from onecstarter.domain.connect import ConnectKind, find_fragment, parse_connect
from onecstarter.security.secrets import strip_url_credentials
from onecstarter.services.display import RowKind
from onecstarter.services.model import InfobaseItem

__all__ = [
    "BADGE_LABELS",
    "KIND_WORDS",
    "ConnectionPath",
    "PanelCard",
    "connection_path",
    "panel_card",
]

BADGE_LABELS: Mapping[ConnectKind, str] = {
    ConnectKind.FILE: "файловая база",
    ConnectKind.SERVER: "серверная база",
    ConnectKind.WEB: "веб-база",
    ConnectKind.UNKNOWN: "строку соединения не разобрали",
}

KIND_WORDS: Mapping[ConnectKind, str] = {
    ConnectKind.FILE: "файловая",
    ConnectKind.SERVER: "серверная",
    ConnectKind.WEB: "веб",
    ConnectKind.UNKNOWN: "не разобрано",
}

_UNKNOWN_NOTE = "Строка соединения не распознана"
_EMPTY_FILE_NOTE = "В строке соединения пустой путь к базе"  # noqa: RUF001
_EMPTY_WS_NOTE = "В строке соединения пустой адрес публикации (ws)"  # noqa: RUF001
_DIRTY_URL_NOTE = (
    "Адрес показать не удалось: разобрать его надёжно нельзя, а показать "  # noqa: RUF001
    "частично значило бы рискнуть учётными данными"
)

_GROUP_HINT = "Группа — строки подключения нет"
_IMPLICIT_HINT = (
    "Группы нет в файле — есть только путь Folder. Операции недоступны"
)
_PICK_HINT = "Выберите базу, чтобы увидеть путь подключения"


@dataclass(frozen=True)
class ConnectionPath:
    """Что панель показывает про выделенную запись.

    `text` пуст — показывать нечего; тогда причина в `note`, либо записи
    просто нет (группа, заголовок, пустое выделение). `directory` заполнен
    только у файловой базы: только для неё осмысленно «Открыть каталог».
    """  # noqa: RUF002

    text: str
    note: str | None = None
    directory: str | None = None

    @property
    def copyable(self) -> bool:
        return bool(self.text)


_NOTHING = ConnectionPath("")


@dataclass(frozen=True)
class PanelCard:
    """Что панель показывает про выделенную строку — любую, не только базу.

    Панель никогда не пустеет (мокап, «панель свойств: остальные
    состояния»): у строки без соединения карточка объясняет, почему его
    нет (`hint`), вместо пустого поля. Ровно одно из `path`/`hint`
    заполнено. `show_actions` — показывать ли кнопки действий; их
    доступность панель выводит из `path` сама.
    """  # noqa: RUF002

    title: str | None
    kind_word: str | None
    icon_kind: ConnectKind | None
    path: ConnectionPath | None
    hint: str | None
    show_actions: bool


_EMPTY_CARD = PanelCard(None, None, None, None, _PICK_HINT, False)


def connection_path(item: InfobaseItem) -> ConnectionPath:
    if item.is_group or not item.connect:
        return _NOTHING
    fragments = parse_connect(item.connect)
    if item.kind is ConnectKind.FILE:
        value = find_fragment(fragments, "File") or ""
        if not value:
            return ConnectionPath("", _EMPTY_FILE_NOTE)
        return ConnectionPath(value, None, value)
    if item.kind is ConnectKind.SERVER:
        # Порядок наш, а не файловый: штатный стартер показывает Srvr, потом  # noqa: RUF003
        # Ref, и пользователь сверяется именно с этой формой.  # noqa: RUF003
        parts = [
            f'{name}="{fragment_value}"'
            for name in ("Srvr", "Ref")
            if (fragment_value := find_fragment(fragments, name))
        ]
        return ConnectionPath(";".join(parts)) if parts else ConnectionPath("", _UNKNOWN_NOTE)
    if item.kind is ConnectKind.WEB:
        raw = find_fragment(fragments, "ws") or ""
        if not raw:
            return ConnectionPath("", _EMPTY_WS_NOTE)
        cleaned = strip_url_credentials(raw)
        if cleaned is None:
            return ConnectionPath("", _DIRTY_URL_NOTE)
        return ConnectionPath(cleaned)
    return ConnectionPath("", _UNKNOWN_NOTE)


def panel_card(
    kind: RowKind | None, item: InfobaseItem | None, label: str
) -> PanelCard:
    """Карточка панели по виду строки (спека рестайла §4, таблица состояний).

    `item` может быть `None` даже при `kind=BASE`: запись исчезает между
    пересборкой модели и синхронизацией панели при внешней правке файла —
    тот же случай, что у `remove_key`/`create_shortcut` в view. Карточка
    деградирует к пустой, а не падает.
    """  # noqa: RUF002
    if kind is RowKind.BASE and item is not None and not item.is_group:
        return PanelCard(
            item.name, KIND_WORDS[item.kind], item.kind,
            connection_path(item), None, True,
        )
    if kind is RowKind.GROUP and item is not None:
        return PanelCard(item.name, "группа", None, None, _GROUP_HINT, False)
    if kind is RowKind.IMPLICIT_GROUP:
        return PanelCard(label, "неявный узел", None, None, _IMPLICIT_HINT, False)
    return _EMPTY_CARD
