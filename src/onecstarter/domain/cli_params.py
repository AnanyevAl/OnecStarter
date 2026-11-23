"""Строка параметров запуска: разбор без потерь, привязка аргументов, правка (спека v4, §4.1).

Чистый модуль. **Инвариант:** `render(parse(s)) == s` байт в байт; правка одного ключа
меняет только его фрагмент — пробелы, регистр и кавычки остального сохраняются.

Чтение кавычек — как у платформы (**[Ф]** T-42 Э4): удвоенная кавычка внутри значения —
одна кавычка; `\\"` закрывает значение (остаток слова платформа молча отбрасывает);
значение без кавычек — до первого пробела. Сборка пишет удвоение, как
`domain/launch.py::quote_launch_value`.
"""  # noqa: RUF002

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from onecstarter.domain.cli_catalog import (
    CLIENT_TITLES,
    MODE_TITLES,
    ArgKind,
    ArgSpec,
    Catalog,
    CatalogKey,
    Client,
    Mode,
)
from onecstarter.domain.version import VersionNumber, parse_version
from onecstarter.security.secrets import secret_name_at

_SPACES = (" ", "\t")


@dataclass(frozen=True)
class Token:
    """Фрагмент строки: ключ со своими словами или посторонний текст до первого ключа.

    `raw` — исходный фрагмент вместе с ведущими пробелами; склейка `raw` всех токенов
    и `tail` строки даёт исходную строку. `word` — первое слово как записано;
    `attached` — прижатый к имени остаток первого слова (с кавычками, как записан).
    `glued` — известный ключ, к которому значение прижато в кавычках (`/C"x"`): токен
    по-прежнему неизвестный (`key is None`), но замечание называет ключ (Ф1).
    """  # noqa: RUF002

    raw: str
    word: str
    key: CatalogKey | None
    attached: str
    words: tuple[str, ...]
    stray: bool = False
    glued: CatalogKey | None = None

    @property
    def name(self) -> str:
        """Имя ключа как записано (`/len`), для неизвестного — первое слово."""
        if self.key is None:
            return self.word
        return self.word[: len(self.word) - len(self.attached)]


@dataclass(frozen=True)
class ParsedParams:
    tokens: tuple[Token, ...]
    tail: str
    unclosed_quote: bool

    def key_tokens(self) -> tuple[Token, ...]:
        return tuple(token for token in self.tokens if not token.stray)

    def find(self, name: str) -> Token | None:
        wanted = name.casefold()
        return next(
            (
                token
                for token in self.key_tokens()
                if token.key is not None and token.key.name.casefold() == wanted
            ),
            None,
        )


@dataclass(frozen=True)
class Binding:
    """Значения аргументов ключа по порядку `CatalogKey.args`.

    `None` — аргумента нет; у флага и у подпараметра без значения — пустая строка.
    `extra` — слова, которым нет места: платформа их отбросит.
    """  # noqa: RUF002

    values: tuple[str | None, ...]
    extra: tuple[str, ...]


def _words(text: str) -> tuple[list[tuple[int, int]], bool]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    quoted = False
    for index, char in enumerate(text):
        if char == '"':
            quoted = not quoted
            if start is None:
                start = index
            continue
        if char in _SPACES and not quoted:
            if start is not None:
                spans.append((start, index))
                start = None
            continue
        if start is None:
            start = index
    if start is not None:
        spans.append((start, len(text)))
    return spans, quoted


def parse(text: str, catalog: Catalog) -> ParsedParams:
    spans, unclosed = _words(text)
    groups: list[list[tuple[int, int]]] = []
    for span in spans:
        if text[span[0]] == "/" or not groups:
            groups.append([span])
        else:
            groups[-1].append(span)
    tokens: list[Token] = []
    previous_end = 0
    for group in groups:
        first = text[group[0][0] : group[0][1]]
        end = group[-1][1]
        raw = text[previous_end:end]
        previous_end = end
        rest = tuple(text[start:stop] for start, stop in group[1:])
        if not first.startswith("/"):
            joined = " ".join((first, *rest))
            tokens.append(Token(raw, joined, None, "", (), stray=True))
            continue
        found = catalog.match(first)
        if found is None:
            tokens.append(Token(raw, first, None, "", rest, glued=catalog.glued_key(first)))
        else:
            tokens.append(Token(raw, first, found[0], found[1], rest))
    return ParsedParams(tuple(tokens), text[previous_end:], unclosed)


def render(parsed: ParsedParams) -> str:
    return "".join(token.raw for token in parsed.tokens) + parsed.tail


def key_count(parsed: ParsedParams) -> int:
    """Число ключей для заголовка блока (спека §7.1): неизвестные считаются."""
    return len(parsed.key_tokens())


def unquote(word: str) -> tuple[str, str]:
    """Значение и остаток. Остаток непуст, когда кавычка закрыта посреди слова."""
    if not word.startswith('"'):
        return word, ""
    value: list[str] = []
    index = 1
    while index < len(word):
        char = word[index]
        if char == '"':
            if index + 1 < len(word) and word[index + 1] == '"':
                value.append('"')
                index += 2
                continue
            return "".join(value), word[index + 1 :]
        value.append(char)
        index += 1
    return "".join(value), ""


def quote(value: str) -> str:
    """Кавычки — только где нужно; значение с «/» в начале — всегда в кавычках.

    Без кавычек `/x` при следующем разборе открыл бы новый ключ (ревью задачи 4,
    решение заказчика 08.11.2026). Как платформа читает `"/x"` — [?], не измерено.
    """  # noqa: RUF002
    if (
        value
        and '"' not in value
        and not value.startswith("/")
        and not any(space in value for space in _SPACES)
    ):
        return value
    return '"' + value.replace('"', '""') + '"'


def _flag_index(args: Sequence[ArgSpec], word: str) -> int | None:
    folded = word.casefold()
    for index, arg in enumerate(args):
        if arg.flag is None:
            continue
        flag = arg.flag.casefold()
        if folded == flag or (arg.attached and folded.startswith(flag)):
            return index
    return None


def bind(token: Token) -> Binding:
    key = token.key
    if key is None:
        return Binding((), token.words)
    args = key.args
    values: list[str | None] = [None] * len(args)
    extra: list[str] = []
    if token.attached and key.takes_attached:
        value, junk = unquote(token.attached)
        values[0] = value
        if junk:
            extra.append(junk)
    pending: int | None = None
    for word in token.words:
        if pending is not None:
            value, junk = unquote(word)
            values[pending] = value
            if junk:
                extra.append(junk)
            pending = None
            continue
        flagged = _flag_index(args, word)
        if flagged is not None:
            arg = args[flagged]
            if arg.kind is ArgKind.FLAG:
                values[flagged] = ""
            elif arg.attached and arg.flag is not None:
                values[flagged] = unquote(word[len(arg.flag) :])[0]
            else:
                values[flagged] = ""
                pending = flagged
            continue
        placed = False
        for index, arg in enumerate(args):
            if values[index] is not None or arg.flag is not None or arg.attached:
                continue
            if arg.kind is ArgKind.ENUM:
                if word.casefold() in {value.casefold() for value in arg.values}:
                    values[index] = word
                    placed = True
                    break
                continue
            if arg.kind is ArgKind.FLAG:
                continue
            value, junk = unquote(word)
            values[index] = value
            if junk:
                extra.append(junk)
            placed = True
            break
        if not placed:
            extra.append(word)
    return Binding(tuple(values), tuple(extra))


def format_key(key: CatalogKey, values: Sequence[str | None], spelled: str | None = None) -> str:
    head = spelled or key.name
    parts: list[str] = []
    for arg, value in zip(key.args, values, strict=False):
        if value is None:
            continue
        if arg.attached and arg.flag is None:
            if arg.quoted:
                head += '"' + value.replace('"', '""') + '"'
            else:
                head += quote(value) if arg.kind is not ArgKind.ENUM else value
        elif arg.kind is ArgKind.FLAG:
            parts.append(arg.flag or "")
        elif arg.flag is not None and arg.attached:
            parts.append(arg.flag + value)
        elif arg.flag is not None:
            parts.append(arg.flag)
            if value != "":
                parts.append(quote(value))
        else:
            parts.append(value if arg.kind is ArgKind.ENUM else quote(value))
    return " ".join([head, *parts])


def _closed(parsed: ParsedParams, catalog: Catalog) -> ParsedParams:
    """Строка с закрытой кавычкой: при незакрытой хвост пуст, кавычка встаёт в конец."""  # noqa: RUF002
    if not parsed.unclosed_quote:
        return parsed
    return parse(render(parsed) + '"', catalog)


def _leading(raw: str) -> str:
    return raw[: len(raw) - len(raw.lstrip("".join(_SPACES)))]


def with_key(
    parsed: ParsedParams, key: CatalogKey, values: Sequence[str | None], catalog: Catalog
) -> ParsedParams:
    """Заменить фрагмент первого вхождения ключа или дописать ключ в конец.

    Незакрытая кавычка сначала закрывается в конце строки: иначе дописанный ключ
    провалился бы внутрь открытого значения (ревью задачи 4, решение заказчика
    08.11.2026) — единственное исключение из «правка меняет только свой фрагмент».
    """
    parsed = _closed(parsed, catalog)
    current = parsed.find(key.name)
    if current is None:
        separator = " " if parsed.tokens else ""
        text = render(replace(parsed, tail="")) + separator + format_key(key, values) + parsed.tail
        return parse(text, catalog)
    spelled = current.name
    fragment = _leading(current.raw) + format_key(key, values, spelled=spelled)
    tokens = tuple(fragment if token is current else token.raw for token in parsed.tokens)
    return parse("".join(tokens) + parsed.tail, catalog)


def without_key(parsed: ParsedParams, name: str, catalog: Catalog) -> ParsedParams:
    """Убрать все вхождения ключа вместе с ведущими пробелами фрагмента.

    Если удаляется первый токен, ведущие пробелы следующего становятся началом
    строки — их убираем, чтобы строка не начиналась с пробела, которого не было.
    """  # noqa: RUF002
    parsed = _closed(parsed, catalog)
    wanted = name.casefold()
    kept = [
        token
        for token in parsed.tokens
        if token.stray or token.key is None or token.key.name.casefold() != wanted
    ]
    if len(kept) == len(parsed.tokens):
        return parsed
    pieces = [token.raw for token in kept]
    if pieces and parsed.tokens and kept[0] is not parsed.tokens[0]:
        pieces[0] = pieces[0].lstrip("".join(_SPACES))
    tail = parsed.tail if pieces else ""
    return parse("".join(pieces) + tail, catalog)


class Where(Enum):
    PERMANENT = "permanent"
    DESIGNER_LINE = "designer"
    ONCE = "once"
    SET = "set"


class Level(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    level: Level
    key: str | None
    text: str


@dataclass(frozen=True)
class CheckContext:
    """Где живёт строка и чем запускается база (спека §4.2).

    `client` — `None`, если клиент не известен заранее (`App=Auto`); `version` — `None`,
    если версия не разрешена (серверная или веб-база, нет установок). Неизвестное —
    не повод для замечания: проверка, которой нечем проверять, молчит.
    """

    where: Where
    mode: Mode
    client: Client | None = None
    version: VersionNumber | None = None
    permanent: ParsedParams | None = None


DOC_FLOOR = parse_version("8.3.18")
_KEY_NAME = re.compile(r"/[\w@]*")


def key_name_of(word: str) -> str:
    """Имя ключа из слова строки без прижатого значения: `/Foo"секрет"` → `/Foo`.

    Для показа неизвестного ключа: в прижатом значении может быть пароль (инвариант 5).
    Слово, которое без учёта регистра начинается с секретного имени, показывается одним
    этим именем: `/UCcode` → `/UC`, `/WSPsecret` → `/WSP`, `/Pass` → `/P` — значение,
    приклеенное без разделителя, иначе ушло бы в замечание (финальное ревью блока 1, F2).
    Список секретных имён — один, в `security/secrets.py` (`secret_name_at`).
    """  # noqa: RUF002, RUF100
    secret = secret_name_at(word)
    if secret is not None:
        return secret
    match = _KEY_NAME.match(word)
    return match.group(0) if match else "/"


def check(parsed: ParsedParams, context: CheckContext) -> tuple[Finding, ...]:
    """Замечания к строке. Ничего не блокирует (спека §4.2): решает вызывающий."""
    findings: list[Finding] = []
    if parsed.unclosed_quote:
        findings.append(
            Finding(
                Level.ERROR,
                None,
                "Незакрытая кавычка: платформа прочитает строку не так, как она написана",
            )
        )
    if context.version is not None and context.version < DOC_FLOOR:
        findings.append(
            Finding(
                Level.INFO,
                None,
                f"Версия {context.version} ниже {DOC_FLOOR} — данных о ключах для неё нет",  # noqa: RUF001
            )
        )
    seen: set[str] = set()
    for token in parsed.tokens:
        if token.stray:
            findings.append(
                Finding(
                    Level.ERROR, None, "Текст до первого ключа — не ключ: ключи начинаются с «/»"  # noqa: RUF001
                )
            )
            continue
        if token.key is None:
            glued = token.glued
            if glued is not None:
                value = "<значение>" if glued.secret else token.word[len(glued.name) :]
                findings.append(
                    Finding(
                        Level.WARNING,
                        glued.name,
                        f"{glued.name}: значение пишется через пробел — {glued.name} {value}",
                    )
                )
                # Прижатый пароль хранится открытым текстом так же, как отдельный:
                # ошибку не теряем (финальное ревью, I1). Значение разбираем так,
                # будто оно записано через пробел: в первый позиционный аргумент.
                separated = replace(
                    token,
                    key=glued,
                    attached="",
                    words=(token.word[len(glued.name) :], *token.words),
                    glued=None,
                )
                findings.extend(_plaintext_secret(glued, bind(separated), context.where))
                continue
            unknown = key_name_of(token.word)
            findings.append(
                Finding(
                    Level.ERROR,
                    unknown,
                    f"{unknown} — неизвестный ключ. Строка сохранится как есть.",
                )
            )
            continue
        name = token.key.name
        if name.casefold() in seen:
            findings.append(Finding(Level.WARNING, name, f"{name} указан дважды"))
        seen.add(name.casefold())
        findings.extend(_key_findings(token, context))
    return tuple(findings)


def _plaintext_secret(key: CatalogKey, binding: Binding, where: Where) -> list[Finding]:
    """ERROR «пароль открытым текстом»: секретный аргумент со значением в хранимой строке.

    Одна на ключ с разобранным значением и на прижатый ключ (I1). Значение в текст
    не попадает (инвариант 5).
    """  # noqa: RUF002
    has_secret_value = any(
        arg.kind is ArgKind.SECRET and value
        for arg, value in zip(key.args, binding.values, strict=False)
    )
    if not has_secret_value or where is Where.ONCE:
        return []
    place = ".v8i" if where is Where.PERMANENT else "строке"
    return [
        Finding(
            Level.ERROR,
            key.name,
            f"{key.name}: пароль в {place} хранится открытым текстом — "
            "используйте поле «Пароль»",
        )
    ]


def _key_findings(token: Token, context: CheckContext) -> list[Finding]:
    key = token.key
    if key is None:  # pragma: no cover — отсеяно в check
        return []
    name = key.name
    binding = bind(token)
    found: list[Finding] = _plaintext_secret(key, binding, context.where)

    def add(level: Level, text: str) -> None:
        found.append(Finding(level, name, text))

    if key.managed:
        add(
            Level.WARNING,
            f"{name}: подключение к базе программа задаёт сама — ключ здесь не нужен",
        )
    if context.mode not in key.modes:
        add(Level.WARNING, f"{name} — не для режима «{MODE_TITLES[context.mode]}»")
    elif (
        context.mode is Mode.ENTERPRISE
        and context.client is not None
        and key.clients
        and context.client not in key.clients
    ):
        add(Level.WARNING, f"{name} — не для клиента «{CLIENT_TITLES[context.client]}»")
    version = context.version
    if version is not None and version >= DOC_FLOOR:
        if key.since is not None and version < key.since:
            add(
                Level.WARNING,
                f"{name} появился в {key.since}, а база запускается версией {version}",  # noqa: RUF001
            )
        elif key.until is not None and version > key.until:
            add(
                Level.WARNING,
                f"{name} убран после {key.until}, а база запускается версией {version}",  # noqa: RUF001
            )
    present = {
        arg.flag.casefold()
        for arg, value in zip(key.args, binding.values, strict=False)
        if value is not None and arg.flag
    } | {
        value.casefold()
        for arg, value in zip(key.args, binding.values, strict=False)
        if value and arg.kind is ArgKind.ENUM
    }
    for arg, value in zip(key.args, binding.values, strict=False):
        label = arg.label or arg.flag or arg.kind.value
        valued_flag_without_value = (
            arg.flag is not None and arg.kind is not ArgKind.FLAG and value == ""
        )
        if (arg.required and not value) or valued_flag_without_value:
            add(Level.ERROR, f"{name}: не задано значение «{label}»")
        if value is not None and arg.requires and arg.requires.casefold() not in present:
            add(
                Level.WARNING,
                f"{name}: {arg.flag or label} действует только вместе с {arg.requires}",  # noqa: RUF001
            )
    if binding.extra:
        # Инвариант 5: отброшенный хвост ключа с паролем не цитируем.  # noqa: RUF003
        dropped = (
            "часть значения после пробела"
            if key.secret
            else f"«{' '.join(binding.extra)}»"
        )
        add(
            Level.WARNING,
            f"{name}: {dropped} платформа отбросит молча — "
            "значение с пробелами возьмите в кавычки",  # noqa: RUF001
        )
    if context.where is Where.PERMANENT and not key.from_v8i:
        add(
            Level.WARNING,
            f"{name} из списка баз платформа не применяет — задайте его при разовом "  # noqa: RUF001
            "запуске или в строке Конфигуратора",
        )
    if (
        context.where is Where.ONCE
        and context.permanent is not None
        and context.permanent.find(name) is not None
    ):
        add(
            Level.INFO,
            f"{name} уже есть в постоянных параметрах базы — сработает разовое значение",
        )
    return found
