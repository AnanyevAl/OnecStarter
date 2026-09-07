"""Модель записи списка баз и ключ привязки наших данных.

Ключ привязки: ID секции, если он есть, иначе суррогат. У базы суррогат — хеш
нормализованной строки соединения плюс нормализованное имя. У группы — её
собственный путь **как есть**: регистр значим ([Ф] T-05.7), секретов в пути
нет. Префиксы обязательны, иначе суррогат столкнётся с UUID —
см. `binding_key`, `group_binding_key` и `key_of_section`.

Два разных по достоверности факта, поэтому порознь:

- **[Ф]** скил v8i-format: слияние идёт только по `ID`, опираться на порядок
  секций между сеансами нельзя. Замерено на платформе 8.3.25.1633.
- **[Д]** справочник v8i-format по ИТС: `Connect` ключом идентичности
  не является, допустимы несколько секций с одинаковой строкой соединения
  и разными именами. Экспериментально это не подтверждалось.
"""  # noqa: RUF002

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from onecstarter.config.v8i import KeyValueLine, V8iDocument, V8iSection
from onecstarter.domain.connect import (
    PLACEMENT_FRAGMENTS,
    ConnectKind,
    classify_connect,
    parse_connect,
)
from onecstarter.services.errors import InvalidRequestError
from onecstarter.services.paths import group_path

_SURROGATE_DIGEST_LENGTH = 16


class InfobaseSource(Enum):
    USER = "user"
    COMMON = "common"


def normalize(text: str) -> str:
    return text.strip().casefold()


def binding_key(section_id: str | None, connect: str | None, name: str) -> str:
    if section_id:
        return f"id:{section_id}"
    # Строка соединения несёт пароли (Pwd, DBPwd, SPwd, wsp, wsppwd), а ключи  # noqa: RUF003
    # привязки индексируют bases.json и попадают в сообщения об ошибках.  # noqa: RUF003
    # Поэтому в ключ идёт только хеш: инвариант 5 запрещает секреты и в наших
    # файлах, и в сообщениях. Имя базы не секрет и остаётся открытым.
    digest = hashlib.sha256(normalize(connect or "").encode("utf-8")).hexdigest()
    return f"cs:{digest[:_SURROGATE_DIGEST_LENGTH]}|{normalize(name)}"


def group_binding_key(section_id: str | None, path: str) -> str:
    """Ключ привязки группы: `ID`, а без него — собственный путь как есть.

    Путь не нормализуется: [Ф] T-05.7 — платформа сопоставляет `Folder`
    с именем группы с учётом регистра, и пути, различающиеся только
    регистром, — разные узлы дерева. Casefold склеил бы их в один ключ.
    Хеш не нужен: секретов в пути группы нет, а имя базы в суррогате
    `binding_key` тоже открыто.
    """  # noqa: RUF002
    if section_id:
        return f"id:{section_id}"
    return f"grp:{path}"


def parse_order(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class InfobaseItem:
    key: str
    name: str
    folder: str
    is_group: bool
    connect: str | None
    kind: ConnectKind
    requested_version: str | None
    section_default_version: str | None
    app: str | None
    source: InfobaseSource
    order: float | None
    section_id: str | None
    favorite: bool = False
    last_launched_at: datetime | None = None
    launch_count: int = 0
    parse_error: str | None = None
    # Та же запись есть и в общем списке. Показывается один раз —  # noqa: RUF003
    # выигрывает пользовательская, потому что её файл мы вправе править.
    in_common_list: bool = False
    # Все пары ключ-значение секции в файловом порядке. Нужны диалогу свойств:  # noqa: RUF003
    # типизированных полей мало, а платформа пишет свои ключи и переживает  # noqa: RUF003
    # чужие ([Ф] T-02.5), и пользователь вправе видеть, что лежит в его файле.  # noqa: RUF003
    keys: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class NewInfobase:
    """Данные новой записи — вход `Workspace.add_infobase`.

    Датакласс, а не кортеж из пяти значений: позиционные `name`, `connect`,
    `folder`, `version`, `app` — все строки или `None`, и перепутать их
    местами не помешал бы ни один тип.
    """  # noqa: RUF002

    name: str
    connect: str
    folder: str
    version: str | None = None
    app: str | None = None


def key_of_section(section: V8iSection) -> str:
    """Ключ привязки секции документа.

    У группы нет `Connect`, поэтому различающая часть суррогата — одно лишь
    имя, а одинаковые имена подгрупп под разными родителями встречаются
    сплошь и рядом. В ключ группы идёт её собственный путь: он и есть
    идентичность группы, тогда как у записи базы идентичность несёт
    строка соединения.
    """  # noqa: RUF002
    if section.is_group:
        return group_binding_key(section.id, group_path(section.folder, section.name))
    return binding_key(section.id, section.connect, section.name)


def item_from_section(section: V8iSection, source: InfobaseSource) -> InfobaseItem:
    connect = section.connect
    order_value = section.get("OrderInList")
    order = parse_order(order_value)
    problems: list[str] = []
    if order_value is not None and order is None:
        problems.append("OrderInList не число")
    unparsed = sum(
        1
        for line in section.lines
        if not isinstance(line, KeyValueLine) and line.text.strip()
    )
    if unparsed:
        problems.append(f"нераспознанных строк: {unparsed}")
    keys = tuple(
        (line.key, line.value)
        for line in section.lines
        if isinstance(line, KeyValueLine)
    )
    return InfobaseItem(
        key=key_of_section(section),
        name=section.name,
        folder=section.folder or "/",
        is_group=section.is_group,
        connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=section.version,
        section_default_version=section.default_version,
        app=section.get("App"),
        source=source,
        order=order,
        section_id=section.id,
        parse_error="; ".join(problems) or None,
        keys=keys,
    )


@dataclass(frozen=True)
class PatchResult:
    """Что патч сделал на самом деле.

    `applied` — цель найдена и патч применён. `key` — фактический ключ цели
    после применения; `None`, если цели в документе больше нет (удалённая
    секция или ненайденная цель удаления). Без этого вызывающий не отличит
    «удалили» от «не нашли» и не узнает, что ключ записи сменился, — а он
    меняется всякий раз, когда записи дописывается `ID`.

    Живёт здесь, а не в модуле правок: результат применения патча нужен
    и правкам записей, и операциям над группами, а модуль групп импортировать
    модуль правок не может — импорт стал бы циклическим.
    """  # noqa: RUF002

    applied: bool
    key: str | None


def find_target(document: V8iDocument, key: str) -> V8iSection | None:
    """Найти секцию по ключу привязки. Никогда не по позиции: порядок секций
    между сеансами не сохраняется ([Ф] каноникализация платформы).
    """
    for section in document.sections:
        if key_of_section(section) == key:
            return section
    return None


def validate_connect(connect: str) -> None:
    """Отвергнуть строку соединения, которая молча портит запись базы.

    Второй рубеж после обязательных полей диалога (долг ревью 4b, №1):
    программный путь — `build_connect(FILE, file_path="")` даёт `File="";` —
    диалог не проходит, и без рубежа в `services` пустое размещение попадало
    в файл. Пустая строка целиком — вовсе не база: признак группы —
    отсутствие `Connect` ([Ф] T-05.6, пустое значение равносильно снятию).

    Проверяются только фрагменты размещения вида записи (`classify_connect`,
    общий источник — `PLACEMENT_FRAGMENTS`): диалог показывает и требует
    ровно их, а пустой фрагмент чужого вида (`File="…";Ref="";`) может уже
    лежать в живом файле, который пишем не только мы, — рубеж, отвергающий
    его, запирал бы правку записи ошибкой про невидимое пользователю поле
    (финальное ревью ветки 18.08.2026). Отсутствующие фрагменты своего вида
    тоже не требуются: экзотическая, но живая запись (один `Srvr` без `Ref`)
    должна оставаться правимой.
    """  # noqa: RUF002
    if not connect.strip():
        raise InvalidRequestError(
            "Строка соединения не может быть пустой: секция без неё — группа"
        )
    placement = PLACEMENT_FRAGMENTS[classify_connect(connect)]
    for fragment in parse_connect(connect):
        if fragment.name.casefold() not in placement:
            continue
        if not fragment.value.strip():
            raise InvalidRequestError(
                f"{fragment.name}: размещение не может быть пустым"
            )


def validate_section_name(name: str) -> None:
    """Отвергнуть имя секции, которое нельзя записать в файл без потерь.

    Заголовок секции пишется как `[<имя>]` одной строкой и не экранируется:
    перевод строки внутри имени превратил бы одну секцию в несколько,
    подделав записи в файле, который мы делим со штатным стартером.
    """  # noqa: RUF002
    if not name.strip():
        raise InvalidRequestError("Имя секции не может быть пустым")
    if "\r" in name or "\n" in name:
        raise InvalidRequestError("Имя секции не может содержать перевод строки")
