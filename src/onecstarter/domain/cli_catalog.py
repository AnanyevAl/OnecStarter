"""Каталог ключей командной строки 1С — модель, целостность, поиск (спека v4, §3).

Чистый модуль: ни ФС, ни Qt. Данные — `platform_1c/cli_catalog.toml`, их читает
`services/cli_catalog.py`. Здесь — типы, проверка целостности (§3.5) и поиск ключа
по написанию в строке (§4.1, п. 3).

Регистр имён не учитывается: **[Ф]** T-42 Э2 — платформа принимает `/len`, `/c`,
`/out` и в командной строке, и в `AdditionalParameters`.
"""  # noqa: RUF002

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from onecstarter.domain.version import VersionNumber, parse_version


class CatalogError(ValueError):
    """Данные каталога нарушают правило целостности (спека §3.5)."""


class Mode(Enum):
    ENTERPRISE = "enterprise"
    DESIGNER = "designer"


class Client(Enum):
    THIN = "thin"
    THICK = "thick"
    WEB = "web"


class ArgKind(Enum):
    FLAG = "flag"
    ENUM = "enum"
    FILE = "file"
    DIR = "dir"
    STRING = "string"
    INT = "int"
    SECRET = "secret"
    # Значение берётся из свойств базы, а не из шага сценария (спека §3.1).  # noqa: RUF003
    BOUND = "bound"


class Effect(Enum):
    """Что команда пакетного режима делает с базой (спека §3.3)."""  # noqa: RUF002

    NONE = "none"
    MODIFIES = "modifies"
    REPLACES = "replaces"


EFFECT_RANK: dict[Effect, int] = {Effect.NONE: 0, Effect.MODIFIES: 1, Effect.REPLACES: 2}
BOUND_SOURCES = frozenset({"repository.address", "repository.user", "repository.password"})
_ROLES = frozenset({"input", "output"})


class Reliability(Enum):
    FACT = "fact"
    DOC = "doc"
    UNVERIFIED = "unverified"


MODE_TITLES: dict[Mode, str] = {Mode.ENTERPRISE: "1С:Предприятие", Mode.DESIGNER: "Конфигуратор"}  # noqa: RUF001
CLIENT_TITLES: dict[Client, str] = {
    Client.THIN: "тонкий клиент",
    Client.THICK: "толстый клиент",
    Client.WEB: "веб-клиент",
}


@dataclass(frozen=True)
class ArgSpec:
    """Аргумент ключа.

    `flag` — имя подпараметра (`-attach`, `-PSrv`); `None` — значение без имени.
    `attached` — значение пишется вплотную: к ключу (`/Lru`, только первый аргумент без
    `flag`) или к подпараметру (`-TPort1538`). `requires` — подпараметр или значение
    enum этого же ключа, без которого аргумент не действует (`-attach` → `-http`).
    """

    kind: ArgKind
    flag: str | None = None
    values: tuple[str, ...] = ()
    required: bool = False
    attached: bool = False
    requires: str | None = None
    label: str = ""
    # Значение всегда в кавычках, как пишет программа: /N"…", /P"…", /IBName"…"
    # ([Ф] T-05.15, T-02.6). Без признака — кавычки только при необходимости: /Len ([Ф] T-42).
    quoted: bool = False
    # file/dir: входной файл обязан существовать, выходной — не существовать (спека §6.3).
    role: str | None = None
    ext: str = ""
    # bound: откуда взять значение — одно из BOUND_SOURCES.
    source: str | None = None


@dataclass(frozen=True)
class CatalogGroup:
    id: str
    title: str
    order: int


@dataclass(frozen=True)
class CatalogKey:
    name: str
    group: str
    modes: frozenset[Mode]
    clients: frozenset[Client]
    summary: str
    description: str
    its: str
    reliability: Reliability
    args: tuple[ArgSpec, ...] = ()
    since: VersionNumber | None = None
    until: VersionNumber | None = None
    managed: bool = False
    # False — платформа не применяет ключ из AdditionalParameters ([Ф] T-42 Э1: /L).
    from_v8i: bool = True

    @property
    def secret(self) -> bool:
        return any(arg.kind is ArgKind.SECRET for arg in self.args)

    @property
    def takes_attached(self) -> bool:
        return bool(self.args) and self.args[0].attached and self.args[0].flag is None


@dataclass(frozen=True)
class CatalogCommand:
    """Команда пакетного режима Конфигуратора (`[[command]]`, спека §3.1, §3.3)."""

    name: str
    group: str
    effect: Effect
    exclusive: bool
    summary: str
    description: str
    its: str
    reliability: Reliability
    args: tuple[ArgSpec, ...] = ()
    since: VersionNumber | None = None
    until: VersionNumber | None = None

    @property
    def bound(self) -> bool:
        return any(arg.kind is ArgKind.BOUND for arg in self.args)


@dataclass(frozen=True)
class Catalog:
    groups: tuple[CatalogGroup, ...]
    keys: tuple[CatalogKey, ...]
    commands: tuple[CatalogCommand, ...] = ()

    def command(self, name: str) -> CatalogCommand | None:
        wanted = name.casefold()
        return next((c for c in self.commands if c.name.casefold() == wanted), None)

    def group_commands(self, group_id: str) -> tuple[CatalogCommand, ...]:
        return tuple(c for c in self.commands if c.group == group_id)

    def key(self, name: str) -> CatalogKey | None:
        wanted = name.casefold()
        return next((key for key in self.keys if key.name.casefold() == wanted), None)

    def group_keys(self, group_id: str) -> tuple[CatalogKey, ...]:
        return tuple(key for key in self.keys if key.group == group_id)

    def match(self, word: str) -> tuple[CatalogKey, str] | None:
        """Ключ по первому слову токена: самый длинный совпавший префикс (§4.1, п. 3).

        Остаток — прижатое значение как записано (с кавычками). Ключ без прижатого
        аргумента совпадает только целиком: `/DebugX` — неизвестный ключ, а не `/Debug`
        с мусором.
        """  # noqa: RUF002
        folded = word.casefold()
        for key in sorted(self.keys, key=lambda candidate: len(candidate.name), reverse=True):
            name = key.name.casefold()
            if not folded.startswith(name):
                continue
            rest = word[len(key.name) :]
            if not rest or key.takes_attached:
                return key, rest
        return None

    def glued_key(self, word: str) -> CatalogKey | None:
        """Известный ключ, к которому значение в кавычках прижато без пробела (`/C"x"`).

        Только когда `match` слово не узнал, а остаток после имени начинается с кавычки:
        без кавычки опечатку в имени (`/DebugX`) от значения не отличить. Из подходящих —
        самое длинное имя, как у `match`. Приёмка 21.11.2026, Ф1.
        """  # noqa: RUF002
        folded = word.casefold()
        for key in sorted(self.keys, key=lambda candidate: len(candidate.name), reverse=True):
            if folded.startswith(key.name.casefold()) and word[len(key.name) :].startswith('"'):
                return key
        return None


def load_catalog(payload: Mapping[str, Any]) -> Catalog:
    """Каталог из словаря (разобранного TOML). Нарушение целостности — `CatalogError`."""
    groups = tuple(_group(entry) for entry in payload.get("group", []))
    seen_groups: set[str] = set()
    for group in groups:
        if group.id in seen_groups:
            raise CatalogError(f"группа «{group.id}» объявлена дважды")
        seen_groups.add(group.id)
    keys = tuple(_key(entry, seen_groups) for entry in payload.get("key", []))
    seen_names: set[str] = set()
    for key in keys:
        folded = key.name.casefold()
        if folded in seen_names:
            raise CatalogError(f"{key.name}: имя повторяется")
        seen_names.add(folded)
    commands = tuple(_command(entry, seen_groups) for entry in payload.get("command", []))
    seen_commands: set[str] = set()
    for command in commands:
        folded = command.name.casefold()
        if folded in seen_commands:
            raise CatalogError(f"{command.name}: имя повторяется")
        seen_commands.add(folded)
    return Catalog(tuple(sorted(groups, key=lambda group: group.order)), keys, commands)


def _group(entry: Mapping[str, Any]) -> CatalogGroup:
    return CatalogGroup(id=str(entry["id"]), title=str(entry["title"]), order=int(entry["order"]))


def _required_text(entry: Mapping[str, Any], name: str, field_name: str) -> str:
    value = str(entry.get(field_name, "")).strip()
    if not value:
        raise CatalogError(f"{name}: не заполнено поле {field_name}")
    return value


def _enum_set(
    values: Sequence[Any], enum: type[Enum], name: str, field_name: str
) -> frozenset[Any]:
    try:
        return frozenset(enum(str(value)) for value in values)
    except ValueError as error:
        raise CatalogError(f"{name}: неизвестное значение {field_name}") from error


def _version(text: Any, name: str) -> VersionNumber | None:
    if text is None:
        return None
    try:
        return parse_version(str(text))
    except ValueError as error:
        raise CatalogError(f"{name}: версия «{text}» не разбирается") from error


def _key(entry: Mapping[str, Any], groups: set[str]) -> CatalogKey:
    name = str(entry.get("name", ""))
    if not name.startswith("/"):
        raise CatalogError(f"{name}: имя ключа начинается с «/»")  # noqa: RUF001
    group = str(entry.get("group", ""))
    if group not in groups:
        raise CatalogError(f"{name}: группы «{group}» нет в каталоге")
    modes = _enum_set(entry.get("modes", []), Mode, name, "modes")
    if not modes:
        raise CatalogError(f"{name}: не задан ни один режим")
    clients = _enum_set(entry.get("clients", []), Client, name, "clients")
    summary = _required_text(entry, name, "summary")
    description = _required_text(entry, name, "description")
    its = _required_text(entry, name, "its")
    try:
        reliability = Reliability(str(entry.get("reliability", "")))
    except ValueError as error:
        raise CatalogError(f"{name}: неизвестное значение reliability") from error
    versions = entry.get("versions", {})
    since = _version(versions.get("since"), name)
    until = _version(versions.get("until"), name)
    if since is not None and until is not None and since > until:
        raise CatalogError(f"{name}: since позже until")
    args = tuple(_arg(raw, name) for raw in entry.get("args", []))
    for index, arg in enumerate(args):
        if index > 0 and arg.attached and arg.flag is None:
            raise CatalogError(f"{name}: прижатым к ключу может быть только первый аргумент")
    _check_requires(args, name)
    return CatalogKey(
        name=name,
        group=group,
        modes=modes,
        clients=clients,
        summary=summary,
        description=description,
        its=its,
        reliability=reliability,
        args=args,
        since=since,
        until=until,
        managed=bool(entry.get("managed", False)),
        from_v8i=bool(entry.get("from_v8i", True)),
    )


def _command(entry: Mapping[str, Any], groups: set[str]) -> CatalogCommand:
    name = str(entry.get("name", ""))
    if not name.startswith("/"):
        raise CatalogError(f"{name}: имя команды начинается с «/»")  # noqa: RUF001
    group = str(entry.get("group", ""))
    if group not in groups:
        raise CatalogError(f"{name}: группы «{group}» нет в каталоге")
    try:
        effect = Effect(str(entry.get("effect", "")))
    except ValueError as error:
        raise CatalogError(f"{name}: неизвестное значение effect") from error
    exclusive = entry.get("exclusive")
    if not isinstance(exclusive, bool):
        raise CatalogError(f"{name}: не задано поле exclusive")
    summary = _required_text(entry, name, "summary")
    description = _required_text(entry, name, "description")
    its = _required_text(entry, name, "its")
    try:
        reliability = Reliability(str(entry.get("reliability", "")))
    except ValueError as error:
        raise CatalogError(f"{name}: неизвестное значение reliability") from error
    versions = entry.get("versions", {})
    since = _version(versions.get("since"), name)
    until = _version(versions.get("until"), name)
    if since is not None and until is not None and since > until:
        raise CatalogError(f"{name}: since позже until")
    args = tuple(_arg(raw, name) for raw in entry.get("args", []))
    if any(arg.kind is ArgKind.SECRET for arg in args):
        # Значение шага лежит в operations.json открытым текстом; секреты команд
        # хранилища — только `bound` из свойств базы (инвариант 5).
        raise CatalogError(f"{name}: у команды не бывает аргумента secret — только bound")  # noqa: RUF001
    _check_requires(args, name)
    return CatalogCommand(
        name=name,
        group=group,
        effect=effect,
        exclusive=exclusive,
        summary=summary,
        description=description,
        its=its,
        reliability=reliability,
        args=args,
        since=since,
        until=until,
    )


def _check_requires(args: tuple[ArgSpec, ...], name: str) -> None:
    """`requires` ссылается на подпараметр или значение enum этого же ключа/команды."""
    known = {arg.flag for arg in args if arg.flag} | {value for arg in args for value in arg.values}
    for arg in args:
        if arg.requires is not None and arg.requires not in known:
            raise CatalogError(
                f"{name}: requires «{arg.requires}» не ссылается на подпараметр этого ключа"
            )


def _arg(raw: Mapping[str, Any], name: str) -> ArgSpec:
    try:
        kind = ArgKind(str(raw.get("kind", "")))
    except ValueError as error:
        raise CatalogError(f"{name}: неизвестный тип аргумента «{raw.get('kind')}»") from error
    values = tuple(str(value) for value in raw.get("values", []))
    flag = raw.get("flag")
    if kind is ArgKind.ENUM and not values:
        raise CatalogError(f"{name}: у enum нет values")  # noqa: RUF001
    if kind is ArgKind.FLAG and not flag:
        raise CatalogError(f"{name}: у flag нет имени подпараметра")  # noqa: RUF001
    role = raw.get("role")
    if role is not None and (str(role) not in _ROLES or kind not in (ArgKind.FILE, ArgKind.DIR)):
        raise CatalogError(f"{name}: role — input или output и только у file/dir")  # noqa: RUF001
    source = raw.get("source")
    if kind is ArgKind.BOUND and str(source) not in BOUND_SOURCES:
        raise CatalogError(f"{name}: у bound неизвестный source «{source}»")  # noqa: RUF001
    if kind is not ArgKind.BOUND and source is not None:
        raise CatalogError(f"{name}: source допустим только у bound")  # noqa: RUF001
    return ArgSpec(
        kind=kind,
        flag=str(flag) if flag else None,
        values=values,
        required=bool(raw.get("required", False)),
        attached=bool(raw.get("attached", False)),
        requires=str(raw["requires"]) if raw.get("requires") else None,
        quoted=bool(raw.get("quoted", False)),
        label=str(raw.get("label", "")),
        role=str(role) if role else None,
        ext=str(raw.get("ext", "")),
        source=str(source) if source else None,
    )
