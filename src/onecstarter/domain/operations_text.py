"""Тексты экранов пакетных операций — чистые функции (спека v4, §7.4–§7.6).

Ни Qt, ни ФС, ни часов: окна только расставляют эти строки. `exclusive` каталога измерен
лишь у `/DumpIB` ([Ф] T-42 Э7), поэтому текст говорит «может понадобиться», а не «нужен».
"""  # noqa: RUF002

from collections.abc import Mapping

from onecstarter.domain.cli_catalog import ArgKind, Catalog, Effect
from onecstarter.domain.launch import Credentials
from onecstarter.domain.operations import (
    BaseOutcome,
    BaseResult,
    RepositoryAccess,
    Scenario,
    Step,
    StepResult,
    StepStatus,
    SubstitutionContext,
    SubstitutionError,
    build_step_arguments,
    padded,
    substitute,
)

WAITING = "ждёт"
RUNNING = "выполняется"
PASSWORD_ONCE_NOTE = "Пароль, введённый здесь, используется только в этом запуске."
PASSWORD_ARGV_NOTE = (
    "Пароль передаётся Конфигуратору в командной строке и виден любой программе, "
    "работающей под вашей учётной записью, пока идёт шаг."
)
_MARKS = {StepStatus.OK: "✓", StepStatus.FAILED: "✗", StepStatus.INTERRUPTED: "прерван"}


def bases_genitive(count: int) -> str:
    """«1 базы», «2 баз», «21 базы» — после «для» и «данные»."""
    return "базы" if count % 10 == 1 and count % 100 != 11 else "баз"


def runs_word(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "запусков"
    if count % 10 == 1:
        return "запуск"
    if 2 <= count % 10 <= 4:
        return "запуска"
    return "запусков"


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def step_cell(result: StepResult | None, running_seconds: float | None = None) -> str:
    """Ячейка «база × шаг»: статус, время, код возврата (спека §7.6)."""  # noqa: RUF002
    if result is None:
        if running_seconds is None:
            return WAITING
        return f"⟳ {format_duration(running_seconds)}…"
    if result.status is StepStatus.SKIPPED:
        return "пропущен"
    text = f"{_MARKS[result.status]} {format_duration(result.seconds)}"
    return f"{text} · {result.code}" if result.code is not None else text


def outcome_text(result: BaseResult) -> str:
    if result.outcome is BaseOutcome.OK:
        return "готово"
    if result.outcome is BaseOutcome.INTERRUPTED:
        return "прервано"
    if result.outcome is BaseOutcome.CANCELLED:
        return "отменено"
    if result.outcome is BaseOutcome.NOT_READY:
        return f"пропущена: {result.problems[0]}" if result.problems else "пропущена"
    message = next(
        (s.message for s in result.steps if s.status is StepStatus.FAILED and s.message), ""
    )
    return f"ошибка: {message}" if message else "ошибка"


def step_title(step: Step, catalog: Catalog) -> str:
    command = catalog.command(step.command)
    if command is None or not command.summary:
        return step.command
    return command.summary[:1].upper() + command.summary[1:]


def step_summary(step: Step, catalog: Catalog) -> str:
    """Строка под заголовком шага в списке шагов: заданные значения, как они записаны."""
    command = catalog.command(step.command)
    if command is None or len(step.values) > len(command.args):
        return "команды нет в каталоге" if command is None else "значения не совпадают с каталогом"  # noqa: RUF001
    parts = ["хранилище из свойств базы"] if command.bound else []
    for arg, value in zip(command.args, padded(step.values, command.args), strict=True):
        if value is None or arg.kind is ArgKind.BOUND:
            continue
        if arg.kind is ArgKind.FLAG:
            parts.append(arg.flag or arg.label)
        elif arg.flag is None:
            parts.append(value)
        else:
            parts.append(f"{arg.flag} {value}")
    return " · ".join(parts) if parts else "без параметров"


def effect_notes(scenario: Scenario, catalog: Catalog) -> tuple[str, ...]:
    """Сообщения окна запуска: что шаги делают с базой (спека §7.5)."""  # noqa: RUF002
    notes: list[str] = []
    for number, step in enumerate(scenario.steps, start=1):
        command = catalog.command(step.command)
        if command is None:
            continue
        title = step_title(step, catalog)
        if command.effect is Effect.MODIFIES:
            notes.append(f"Шаг {number} «{title}» меняет базу.")
        elif command.effect is Effect.REPLACES:
            notes.append(f"Шаг {number} «{title}» полностью заменяет данные базы.")
        if command.exclusive:
            notes.append(
                f"Шагу {number} «{title}» может понадобиться монопольный доступ: при открытых "
                "сеансах он завершится ошибкой, а её текст попадёт в журнал."  # noqa: RUF001
            )
        values = padded(step.values[: len(command.args)], command.args)
        for arg, value in zip(command.args, values, strict=True):
            if (arg.flag or "").casefold() == "-sessionterminate" and value == "force":
                notes.append(
                    f"Шаг {number} «{title}» завершит сеансы пользователей базы "
                    "(-SessionTerminate force)."
                )
    return tuple(notes)


def replace_warning(count: int) -> str:
    """Красное сообщение заменяющего сценария (решение заказчика 13.11.2026, спека §7.5)."""
    return (
        f"Данные {count} {bases_genitive(count)} будут полностью заменены. Если загрузка "
        "прервётся или завершится ошибкой, база останется испорченной: её придётся "
        "восстанавливать из резервной копии. Копию программа сама не делает."
    )


def action_label(effect: Effect, count: int) -> str:
    """Кнопка действия окна запуска: у заменяющего сценария она называет последствие."""  # noqa: RUF002
    if effect is Effect.REPLACES:
        return f"Заменить данные {count} {bases_genitive(count)}"
    return f"Выполнить для {count} {bases_genitive(count)}"


def step_hints(step: Step, catalog: Catalog) -> tuple[str, ...]:
    """Подсказки редактора шага об ограничениях, которых проверка шага не выражает.

    Не блокируют: шаг с подсказкой сохраняется и выполняется. `requires` у аргументов
    команд в `step_problems` не проверяется (план 2а, отложенное) — о нём говорит подсказка.
    """  # noqa: RUF002
    command = catalog.command(step.command)
    if command is None or len(step.values) > len(command.args):
        return ()
    values = padded(step.values, command.args)
    given = {
        (arg.flag or "").casefold()
        for arg, value in zip(command.args, values, strict=True)
        if value is not None and arg.flag
    }
    chosen = {value.casefold() for value in values if value}
    hints: list[str] = []
    for arg, value in zip(command.args, values, strict=True):
        if value is None or not arg.requires:
            continue
        need = arg.requires.casefold()
        if need not in given and need not in chosen:
            hints.append(f"{arg.flag or arg.label} действует только вместе с {arg.requires}")  # noqa: RUF001
    name = command.name.casefold()
    if name == "/dumpconfigtofiles" and "-update" in given and not step.overwrite:
        hints.append(
            "-update дополняет прежнюю выгрузку: каталог уже должен существовать — "
            "включите «перезаписывать существующее»."
        )
    if name == "/mergecfg" and not given & {"-enablesupport", "-disablesupport"}:
        hints.append(
            "Если конфигурацию можно поставить на поддержку, платформа ждёт -EnableSupport "
            "или -DisableSupport."
        )
    return tuple(hints)


def example_path(template: str, context: SubstitutionContext, environ: Mapping[str, str]) -> str:
    """Шаблон пути, раскрытый для базы-примера, либо текст причины, почему он не раскрылся."""
    try:
        return substitute(template, context, environ)
    except SubstitutionError as error:
        return str(error)


def preview_arguments(
    step: Step,
    catalog: Catalog,
    *,
    base_name: str,
    login: str | None,
    repository_address: str | None,
    repository_user: str | None,
    logs_dir: str,
    index: int,
    context: SubstitutionContext | None,
    environ: Mapping[str, str],
) -> str:
    """Аргументы `1cv8.exe` шага для предпросмотра (спека §7.4). Пароли — заглушка `***`.

    Настоящих паролей функция не получает вовсе. Шаблоны раскрываются, когда известен
    контекст базы; нераскрываемый шаблон остаётся как записан — о причине скажет готовность.
    """  # noqa: RUF002
    command = catalog.command(step.command)
    if command is None or len(step.values) > len(command.args):
        return ""
    values: list[str | None] = []
    for arg, value in zip(command.args, padded(step.values, command.args), strict=True):
        if value is None or arg.kind is ArgKind.BOUND:
            values.append(None)
            continue
        if context is not None:
            try:
                value = substitute(value, context, environ)
            except SubstitutionError:
                pass
        values.append(value)
    repository = (
        RepositoryAccess(repository_address, repository_user or "<пользователь хранилища>", "***")
        if command.bound
        else None
    )
    return build_step_arguments(
        ib_name=base_name,
        credentials=Credentials(login, "***") if login else None,
        out_path=f"{logs_dir}\\step{index + 1}.log",
        result_path=f"{logs_dir}\\step{index + 1}.result",
        repository=repository,
        command=command,
        values=tuple(values),
    )
