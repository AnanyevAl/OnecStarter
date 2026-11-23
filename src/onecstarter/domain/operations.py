"""Сценарии пакетных операций Конфигуратора — модель и чистые функции (спека v4, §5–§6).

Ни ФС, ни процессов, ни часов: время старта и окружение подаются аргументами. Команды —
из каталога (`domain/cli_catalog.py`, `[[command]]`). Значения аргументов шага — кортеж
по порядку `args` команды: у аргументов каталога нет имён (решение плана 2а).
"""  # noqa: RUF002

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import PureWindowsPath

from onecstarter.domain.cli_catalog import (
    EFFECT_RANK,
    ArgKind,
    ArgSpec,
    Catalog,
    CatalogCommand,
    Effect,
)
from onecstarter.domain.launch import Credentials, quote_launch_value

SUBSTITUTIONS = ("база", "дата", "время", "версия", "группа")

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING = re.compile(r"[. ]+$")
_MARKER = re.compile(r"\{([^{}]*)\}")
_TOKEN = re.compile(r"%([^%\\/:]+)%|\{([^{}]*)\}")
# Целое со знаком: `-v -1` у команд хранилища — «последняя версия» ([Д] 7.4.15).  # noqa: RUF003
# Не `\d`: тот пропускает и не-ASCII цифры.  # noqa: RUF003
_DIGITS = re.compile(r"-?[0-9]+")


class SubstitutionError(ValueError):
    """В шаблоне неизвестная подстановка или незаданная переменная окружения."""  # noqa: RUF002


@dataclass(frozen=True)
class BaseRef:
    """Ссылка на базу из наших данных: ключ записи `bases.json` и имя для показа."""

    key: str
    name: str


@dataclass(frozen=True)
class Step:
    command: str
    values: tuple[str | None, ...] = ()
    overwrite: bool = False
    create_dirs: bool = True


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    steps: tuple[Step, ...]
    stop_on_error: bool = True
    # None — спрашивать базы при запуске; кортеж — сохранённый список.
    bases: tuple[BaseRef, ...] | None = None
    builtin: bool = False


@dataclass(frozen=True)
class SubstitutionContext:
    base: str
    group: str  # путь группы через «/»; корень — пустая строка
    version: str
    started: datetime


def sanitize_component(value: str) -> str:
    """Значение подстановки → часть имени файла Windows (спека §5.2).

    `<>:"/\\|?*` и управляющие символы — `_`; завершающие точки и пробелы — `_` по одному
    на символ (Windows их молча отбрасывает, и два разных имени совпали бы).
    Зарезервированные имена устройств (CON, NUL, COM1…) сознательно не обрабатываются:
    стандартные шаблоны всегда добавляют `_{дата}_{время}` и расширение.
    """
    replaced = _FORBIDDEN.sub("_", value)
    tail = _TRAILING.search(replaced)
    if tail is None:
        return replaced
    return replaced[: tail.start()] + "_" * len(tail.group())


def substitute(template: str, context: SubstitutionContext, environ: Mapping[str, str]) -> str:
    """Раскрыть `%ИМЯ%` и `{подстановки}`. Неизвестное имя — `SubstitutionError`.

    Один проход по шаблону: раскрытые значения повторно не разбираются. Переменные
    окружения вставляются как есть (это путь, а не часть имени), имена — без учёта
    регистра; значения подстановок проходят `sanitize_component`. Пара `%` внутри одного
    компонента пути всегда читается как имя переменной окружения, экранирования нет
    (`D:\\50% и 60%.dt` — ошибка, а не текст). Дата и время — момент старта сценария,
    общий для всех баз и шагов.
    """  # noqa: RUF002
    folded = {name.casefold(): value for name, value in environ.items()}
    values = {
        "база": context.base,
        "дата": context.started.strftime("%Y-%m-%d"),
        "время": context.started.strftime("%H%M%S"),
        "версия": context.version,
        "группа": context.group,
    }

    def replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        if env_name is not None:
            if env_name.casefold() not in folded:
                raise SubstitutionError(f"не задана переменная окружения %{env_name}%")
            return folded[env_name.casefold()]
        name = match.group(2)
        if name not in values:
            raise SubstitutionError(f"неизвестная подстановка {{{name}}}")
        return sanitize_component(values[name])

    return _TOKEN.sub(replace, template)


def padded(values: tuple[str | None, ...], args: tuple[ArgSpec, ...]) -> tuple[str | None, ...]:
    """Значения шага, дополненные `None` до числа аргументов команды."""
    return values + (None,) * (len(args) - len(values))


def has_control_chars(value: str) -> bool:
    """Есть ли в строке управляющие символы (< 0x20: NUL, табуляция, CR, LF…).

    Такое значение в командной строке разорвало бы аргумент или подменило его смысл.
    """  # noqa: RUF002
    return any(ord(char) < 0x20 for char in value)


def step_problems(step: Step, catalog: Catalog) -> tuple[str, ...]:
    """Что не так с шагом само по себе, без базы и ФС (спека §6.3).

    Значение проверяется по типу аргумента каталога: `enum` — только из `values`,
    `int` — только цифры, `flag` — `None` или `""`, `bound` — не задаётся вовсе.
    Без этого значение `enum` вида `X /RestoreIB "…"` ушло бы в командную строку,
    а опасность сценария осталась бы NONE. Значение в текст проблемы не попадает.
    """  # noqa: RUF002
    command = catalog.command(step.command)
    if command is None:
        return ("команды нет в каталоге",)
    if len(step.values) > len(command.args):
        return ("число значений не совпадает с числом параметров команды",)  # noqa: RUF001
    problems: list[str] = []
    for arg, value in zip(command.args, padded(step.values, command.args), strict=True):
        if arg.kind is ArgKind.BOUND:
            if value is not None:
                problems.append("параметр берётся из свойств базы и в шаге не задаётся")
            continue
        if value is not None and has_control_chars(value):
            problems.append(f"параметр «{arg.label}» содержит управляющий символ")
            continue
        if arg.required and (value is None or not value.strip()):
            problems.append(f"не задан обязательный параметр «{arg.label}»")
            continue
        if value is None:
            continue
        if arg.kind is ArgKind.ENUM:
            if value not in arg.values:
                problems.append(f"недопустимое значение параметра «{arg.label}»")
            continue
        if arg.kind is ArgKind.INT:
            if _DIGITS.fullmatch(value) is None:
                problems.append(f"параметр «{arg.label}» — целое число")
            continue
        if arg.kind is ArgKind.FLAG:
            if value != "":
                problems.append(f"недопустимое значение параметра «{arg.label}»")
            continue
        for name in _MARKER.findall(value):
            if name not in SUBSTITUTIONS:
                problems.append(f"неизвестная подстановка {{{name}}}")
    return tuple(problems)


def missing_inputs(scenario: Scenario, catalog: Catalog) -> tuple[tuple[int, int], ...]:
    """Обязательные входные файлы и каталоги, не заданные в сценарии.

    Пары (номер шага с нуля, номер аргумента команды): их спрашивают в окне запуска
    (у заготовки «Загрузить из .dt» файл не задан — `((0, 0),)`). Шаг с командой не из
    каталога пропускается: о нём скажет `step_problems`.
    """  # noqa: RUF002
    missing: list[tuple[int, int]] = []
    for step_index, step in enumerate(scenario.steps):
        command = catalog.command(step.command)
        if command is None or len(step.values) > len(command.args):
            continue
        for arg_index, (arg, value) in enumerate(
            zip(command.args, padded(step.values, command.args), strict=True)
        ):
            if (
                arg.kind in (ArgKind.FILE, ArgKind.DIR)
                and arg.role == "input"
                and arg.required
                and (value is None or not value.strip())
            ):
                missing.append((step_index, arg_index))
    return tuple(missing)


def scenario_effect(scenario: Scenario, catalog: Catalog) -> Effect:
    """Опасность сценария — максимум `effect` его шагов (спека §5.1)."""  # noqa: RUF002
    effect = Effect.NONE
    for step in scenario.steps:
        command = catalog.command(step.command)
        if command is not None and EFFECT_RANK[command.effect] > EFFECT_RANK[effect]:
            effect = command.effect
    return effect


_DOCUMENTS = r"%USERPROFILE%\Documents\OneCStarter\{база}_{дата}_{время}"

BUILTIN_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "builtin:dump-dt",
        "Выгрузить в .dt",
        (Step("/DumpIB", (_DOCUMENTS + ".dt",)),),
        builtin=True,
    ),
    Scenario(
        "builtin:restore-dt", "Загрузить из .dt", (Step("/RestoreIB", (None,)),), builtin=True
    ),
    Scenario(
        "builtin:dump-cf",
        "Выгрузить .cf",
        (Step("/DumpCfg", (_DOCUMENTS + ".cf",)),),
        builtin=True,
    ),
)


@dataclass(frozen=True)
class RepositoryAccess:
    """Доступ к хранилищу конфигурации для команд с `bound` (спека §6.1)."""  # noqa: RUF002

    address: str | None
    user: str
    password: str | None = field(default=None, repr=False, compare=False)


def command_words(command: CatalogCommand, values: tuple[str | None, ...]) -> list[str]:
    """Команда шага и её аргументы — слова командной строки, без `bound`.

    Строки, файлы и каталоги — всегда в кавычках с удвоением внутренних ([Ф] T-42:
    форма скрипта `t42b-batch.ps1`); `enum` и `int` — как есть; `flag` включён при любом
    значении, кроме `None`.
    """  # noqa: RUF002
    words = [command.name]
    for arg, value in zip(command.args, padded(values, command.args), strict=True):
        if arg.kind is ArgKind.BOUND or value is None:
            continue
        if arg.kind is ArgKind.FLAG:
            assert arg.flag is not None  # целостность каталога: у flag есть имя  # noqa: RUF003
            words.append(arg.flag)
            continue
        text = value if arg.kind in (ArgKind.ENUM, ArgKind.INT) else quote_launch_value(value)
        if arg.flag is None:
            words.append(text)
        elif arg.attached:
            words.append(f"{arg.flag}{text}")
        else:
            words.append(f"{arg.flag} {text}")
    return words


def build_step_arguments(
    *,
    ib_name: str,
    credentials: Credentials | None,
    out_path: str,
    result_path: str,
    repository: RepositoryAccess | None,
    command: CatalogCommand,
    values: tuple[str | None, ...],
) -> str:
    """Аргументы `1cv8.exe` для шага сценария (спека §6.1; форма — [Ф] T-42, часть Б).

    `/AppAutoCheckVersion-` — всегда: версию для пакетного шага выбрали мы, а перезапуск
    платформой другой версии оставил бы нас ждать не тот процесс. Параметры Конфигуратора
    базы (§4.3) в шаг не добавляются.
    """  # noqa: RUF002
    parts = ["DESIGNER", f"/IBName{quote_launch_value(ib_name)}"]
    if credentials is not None:
        parts.append(f"/N{quote_launch_value(credentials.login)}")
        if credentials.password is not None:
            parts.append(f"/P{quote_launch_value(credentials.password)}")
    parts += [
        "/AppAutoCheckVersion-",
        "/DisableStartupDialogs",
        "/DisableStartupMessages",
        f"/Out {quote_launch_value(out_path)}",
        f"/DumpResult {quote_launch_value(result_path)}",
    ]
    if command.bound:
        if repository is None:
            raise ValueError("Команде хранилища конфигурации не переданы данные хранилища")
        if repository.address:
            parts.append(f"/ConfigurationRepositoryF {quote_launch_value(repository.address)}")
        parts.append(f"/ConfigurationRepositoryN {quote_launch_value(repository.user)}")
        if repository.password is not None:
            parts.append(f"/ConfigurationRepositoryP {quote_launch_value(repository.password)}")
    parts += command_words(command, values)
    return " ".join(parts)


def decode_log(data: bytes) -> str:
    """Текст файла `/Out` или `/DumpResult`: BOM → строгий UTF-8 → cp1251.

    [Ф] T-42 Э6 — UTF-8 с BOM; кодировка всё равно определяется по факту (инвариант 3).
    """  # noqa: RUF002
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def step_succeeded(code: int | None, dump_result: str | None) -> bool:
    """Успех шага — код возврата 0 и `/DumpResult` «0» (спека §6.5).

    Файла `/DumpResult` нет (`None`) — ошибка шага: результат не получен (решение
    заказчика 14.11.2026).
    """
    if code != 0 or dump_result is None:
        return False
    return dump_result.strip().lstrip("\ufeff") == "0"


def error_text(log_text: str, code: int | None) -> str:
    """Текст ошибки шага — последняя непустая строка `/Out` (решение заказчика 13.11.2026)."""
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return f"код возврата {code}" if code is not None else "код возврата неизвестен"


def leftovers(command: CatalogCommand, values: tuple[str | None, ...]) -> tuple[str, ...]:
    """Файлы, которые остаются после снятия процесса посреди шага.

    [Ф] T-42 Э10: `/DumpIB "X.dt"` пишет в `X.n1` рядом и переименовывает в конце.
    Для остальных команд не измерено — ничего не удаляем.
    """
    if command.name.casefold() != "/dumpib" or not values or not values[0]:
        return ()
    path = PureWindowsPath(values[0])
    if not path.name:  # корень диска: `with_suffix` бросил бы ValueError, удалять нечего
        return ()
    return (str(path.with_suffix(".n1")),)


class StepStatus(Enum):
    OK = "ok"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"


class BaseOutcome(Enum):
    OK = "ok"
    FAILED = "failed"
    INTERRUPTED = "interrupted"  # жёсткая отмена
    CANCELLED = "cancelled"  # мягкая отмена: не все шаги начаты
    NOT_READY = "not_ready"  # не прошла готовность, ни одного процесса


@dataclass(frozen=True)
class StepResult:
    command: str
    status: StepStatus
    code: int | None = None
    seconds: float = 0.0
    message: str = ""


@dataclass(frozen=True)
class BaseResult:
    key: str
    name: str
    outcome: BaseOutcome
    steps: tuple[StepResult, ...] = ()
    problems: tuple[str, ...] = ()
    # Каталог журналов базы (`<каталог запуска>/<NN>_<имя>`); "" — база в работу не шла.
    logs_dir: str = ""


@dataclass(frozen=True)
class RunRecord:
    scenario_id: str
    scenario_name: str
    started: datetime
    logs_dir: str
    bases: tuple[BaseResult, ...]


def failed_keys(record: RunRecord) -> tuple[str, ...]:
    """Базы запуска с исходом FAILED или INTERRUPTED — для «Повторить для ошибочных».

    Порядок — порядок записи, повторы убраны.
    """  # noqa: RUF002
    keys: list[str] = []
    for base in record.bases:
        if base.outcome in (BaseOutcome.FAILED, BaseOutcome.INTERRUPTED) and base.key not in keys:
            keys.append(base.key)
    return tuple(keys)
