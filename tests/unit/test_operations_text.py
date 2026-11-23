"""Тексты экранов пакетных операций — табличные тесты чистых функций (спека v4, §7.4–§7.6)."""  # noqa: RUF002

from datetime import datetime
from typing import Any

import pytest

from onecstarter.domain.cli_catalog import Effect
from onecstarter.domain.operations import (
    BaseOutcome,
    BaseResult,
    Scenario,
    Step,
    StepResult,
    StepStatus,
    SubstitutionContext,
)
from onecstarter.domain.operations_text import (
    action_label,
    bases_genitive,
    effect_notes,
    example_path,
    format_duration,
    outcome_text,
    preview_arguments,
    replace_warning,
    runs_word,
    step_cell,
    step_hints,
    step_summary,
    step_title,
)
from onecstarter.services.cli_catalog import load_cli_catalog

CATALOG = load_cli_catalog()
CONTEXT = SubstitutionContext(
    "Склад: юг", "Клиенты", "8.3.27.2214", datetime(2026, 11, 14, 9, 5, 7)
)


@pytest.mark.parametrize(
    ("count", "word"), [(1, "базы"), (2, "баз"), (5, "баз"), (11, "баз"), (21, "базы")]
)
def test_bases_genitive(count: int, word: str) -> None:
    assert bases_genitive(count) == word


@pytest.mark.parametrize(
    ("count", "word"),
    [(1, "запуск"), (3, "запуска"), (5, "запусков"), (12, "запусков"), (22, "запуска")],
)
def test_runs_word(count: int, word: str) -> None:
    assert runs_word(count) == word


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0, "00:00"), (9.9, "00:09"), (134, "02:14"), (3600, "1:00:00"), (-5, "00:00")],
)
def test_format_duration(seconds: float, text: str) -> None:
    assert format_duration(seconds) == text


@pytest.mark.parametrize(
    ("result", "running", "text"),
    [
        (None, None, "ждёт"),
        (None, 37.0, "⟳ 00:37…"),
        (StepResult("/DumpIB", StepStatus.OK, 0, 134.0), None, "✓ 02:14 · 0"),
        (StepResult("/DumpIB", StepStatus.FAILED, 1, 9.0, "занята"), None, "✗ 00:09 · 1"),
        (StepResult("/DumpIB", StepStatus.FAILED, None, 0.0, "отказ"), None, "✗ 00:00"),
        (StepResult("/DumpIB", StepStatus.INTERRUPTED, None, 5.0), None, "прерван 00:05"),
        (StepResult("/DumpIB", StepStatus.SKIPPED), None, "пропущен"),
    ],
)
def test_step_cell(result: StepResult | None, running: float | None, text: str) -> None:
    assert step_cell(result, running) == text


def test_outcome_text() -> None:
    failed = (
        StepResult("/DumpIB", StepStatus.OK, 0, 1.0),
        StepResult("/UpdateDBCfg", StepStatus.FAILED, 1, 2.0, "объект захвачен"),
    )
    cases = [
        (BaseResult("k", "Б", BaseOutcome.OK), "готово"),
        (BaseResult("k", "Б", BaseOutcome.FAILED, failed), "ошибка: объект захвачен"),
        (BaseResult("k", "Б", BaseOutcome.FAILED), "ошибка"),
        (BaseResult("k", "Б", BaseOutcome.INTERRUPTED), "прервано"),
        (BaseResult("k", "Б", BaseOutcome.CANCELLED), "отменено"),
        (
            BaseResult("k", "Б", BaseOutcome.NOT_READY, problems=("база не найдена в списке", "x")),
            "пропущена: база не найдена в списке",
        ),
        (BaseResult("k", "Б", BaseOutcome.NOT_READY), "пропущена"),
    ]
    for result, text in cases:
        assert outcome_text(result) == text


def test_step_title_and_summary() -> None:
    dump = Step("/DumpIB", (r"D:\Backup\{база}.dt",))
    assert step_title(dump, CATALOG) == "Выгрузить информационную базу в файл .dt"
    assert step_summary(dump, CATALOG) == r"D:\Backup\{база}.dt"
    update = Step("/ConfigurationRepositoryUpdateCfg", (None, None, ""))
    assert step_summary(update, CATALOG) == "хранилище из свойств базы · -force"
    assert step_summary(Step("/DumpCfg"), CATALOG) == "без параметров"
    unknown = Step("/NoSuchCommand")
    assert step_title(unknown, CATALOG) == "/NoSuchCommand"
    assert step_summary(unknown, CATALOG) == "команды нет в каталоге"


def test_effect_notes_name_step_effect_and_exclusive_access() -> None:
    values: list[str | None] = [None] * 14
    values[13] = "force"  # -SessionTerminate — последний параметр /UpdateDBCfg
    scenario = Scenario(
        "u1",
        "Обновление",
        (
            Step("/DumpIB", (r"D:\a.dt",)),
            Step("/UpdateDBCfg", tuple(values)),
            Step("/RestoreIB", (r"D:\a.dt",)),
        ),
    )
    notes = effect_notes(scenario, CATALOG)
    assert notes == (
        "Шагу 1 «Выгрузить информационную базу в файл .dt» может понадобиться монопольный "
        "доступ: при открытых сеансах он завершится ошибкой, а её текст попадёт в журнал.",  # noqa: RUF001
        "Шаг 2 «Обновить конфигурацию базы данных» меняет базу.",
        "Шагу 2 «Обновить конфигурацию базы данных» может понадобиться монопольный "
        "доступ: при открытых сеансах он завершится ошибкой, а её текст попадёт в журнал.",  # noqa: RUF001
        "Шаг 2 «Обновить конфигурацию базы данных» завершит сеансы пользователей базы "
        "(-SessionTerminate force).",
        "Шаг 3 «Загрузить информационную базу из файла .dt» полностью заменяет данные базы.",
        "Шагу 3 «Загрузить информационную базу из файла .dt» может понадобиться монопольный "
        "доступ: при открытых сеансах он завершится ошибкой, а её текст попадёт в журнал.",  # noqa: RUF001
    )
    assert effect_notes(Scenario("u2", "Пусто", (Step("/NoSuchCommand"),)), CATALOG) == ()


def test_replace_warning_and_action_label() -> None:
    assert replace_warning(2) == (
        "Данные 2 баз будут полностью заменены. Если загрузка прервётся или завершится "
        "ошибкой, база останется испорченной: её придётся восстанавливать из резервной "
        "копии. Копию программа сама не делает."
    )
    assert replace_warning(1).startswith("Данные 1 базы будут")
    assert action_label(Effect.REPLACES, 2) == "Заменить данные 2 баз"
    assert action_label(Effect.MODIFIES, 3) == "Выполнить для 3 баз"
    assert action_label(Effect.NONE, 1) == "Выполнить для 1 базы"


def test_step_hints() -> None:
    # /DumpConfigToFiles: каталог, -Extension, -AllExtensions, -update, -force, …
    force_alone = Step("/DumpConfigToFiles", (r"D:\src", None, None, None, ""))
    assert step_hints(force_alone, CATALOG) == ("-force действует только вместе с -update",)  # noqa: RUF001
    update = Step("/DumpConfigToFiles", (r"D:\src", None, None, "", ""))
    assert step_hints(update, CATALOG) == (
        "-update дополняет прежнюю выгрузку: каталог уже должен существовать — "
        "включите «перезаписывать существующее».",
    )
    overwrite = Step("/DumpConfigToFiles", (r"D:\src", None, None, "", ""), True)
    assert step_hints(overwrite, CATALOG) == ()
    assert step_hints(Step("/MergeCfg", (r"D:\a.cf",)), CATALOG) == (
        "Если конфигурацию можно поставить на поддержку, платформа ждёт -EnableSupport "
        "или -DisableSupport.",
    )
    assert step_hints(Step("/DumpIB", (r"D:\a.dt",)), CATALOG) == ()
    assert step_hints(Step("/NoSuchCommand"), CATALOG) == ()


def test_example_path() -> None:
    environ = {"USERPROFILE": r"C:\Users\me"}
    assert (
        example_path(r"%USERPROFILE%\{база}_{дата}.dt", CONTEXT, environ)
        == r"C:\Users\me\Склад_ юг_2026-11-14.dt"
    )
    assert example_path(r"D:\{нет}.dt", CONTEXT, environ) == "неизвестная подстановка {нет}"


def test_preview_arguments_carry_placeholders_instead_of_passwords() -> None:
    step = Step("/ConfigurationRepositoryUpdateCfg", (None, None, ""))
    text = preview_arguments(
        step,
        CATALOG,
        base_name="Склад",
        login="Иванов",
        repository_address="tcp://repo/buh",
        repository_user="dev",
        logs_dir=r"…\ops\run\01_Склад",
        index=1,
        context=None,
        environ={},
    )
    assert text == (
        'DESIGNER /IBName"Склад" /N"Иванов" /P"***" /AppAutoCheckVersion- '
        "/DisableStartupDialogs /DisableStartupMessages "
        '/Out "…\\ops\\run\\01_Склад\\step2.log" /DumpResult "…\\ops\\run\\01_Склад\\step2.result" '
        '/ConfigurationRepositoryF "tcp://repo/buh" /ConfigurationRepositoryN "dev" '
        '/ConfigurationRepositoryP "***" /ConfigurationRepositoryUpdateCfg -force'
    )


def test_preview_arguments_substitute_when_context_is_known() -> None:
    step = Step("/DumpIB", (r"D:\Backup\{база}.dt",))
    common: dict[str, Any] = {
        "base_name": "Склад: юг",
        "login": None,
        "repository_address": None,
        "repository_user": None,
        "logs_dir": "L",
        "index": 0,
        "environ": {},
    }
    resolved = preview_arguments(step, CATALOG, context=CONTEXT, **common)
    assert resolved.endswith(r'/DumpIB "D:\Backup\Склад_ юг.dt"')
    raw = preview_arguments(step, CATALOG, context=None, **common)
    assert raw.endswith(r'/DumpIB "D:\Backup\{база}.dt"')
    unknown = preview_arguments(Step("/NoSuchCommand"), CATALOG, context=None, **common)
    assert unknown == ""
