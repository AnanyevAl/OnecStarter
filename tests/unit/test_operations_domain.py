"""Сценарии пакетных операций: подстановки, проверка шага, опасность (спека v4, §5)."""

from datetime import datetime

import pytest

from onecstarter.domain.cli_catalog import Effect
from onecstarter.domain.launch import Credentials
from onecstarter.domain.operations import (
    BUILTIN_SCENARIOS,
    BaseOutcome,
    BaseResult,
    RepositoryAccess,
    RunRecord,
    Scenario,
    Step,
    SubstitutionContext,
    SubstitutionError,
    build_step_arguments,
    command_words,
    decode_log,
    error_text,
    failed_keys,
    leftovers,
    missing_inputs,
    sanitize_component,
    scenario_effect,
    step_problems,
    step_succeeded,
    substitute,
)
from onecstarter.services.cli_catalog import load_cli_catalog

CONTEXT = SubstitutionContext(
    base="Бухгалтерия: филиал",
    group="Клиенты/ООО «Ромашка»",  # noqa: RUF001
    version="8.3.27.2214",
    started=datetime(2026, 11, 13, 9, 5, 7),
)
ENV = {"USERPROFILE": r"C:\Users\tester"}


@pytest.mark.parametrize("char", [*list('<>:"/\\|?*'), "\x00", "\x1f"])
def test_forbidden_characters_become_underscores(char: str) -> None:
    assert sanitize_component(f"a{char}b") == "a_b"


@pytest.mark.parametrize(
    ("value", "expected"), [("имя. ", "имя__"), ("имя...", "имя___"), ("", ""), (" x", " x")]
)
def test_trailing_dots_and_spaces_become_underscores(value: str, expected: str) -> None:
    assert sanitize_component(value) == expected


def test_all_substitutions_resolve() -> None:
    text = substitute(r"D:\out\{группа}\{база}_{дата}_{время}_{версия}.dt", CONTEXT, ENV)
    assert text == (
        r"D:\out\Клиенты_ООО «Ромашка»\Бухгалтерия_ филиал_2026-11-13_090507_8.3.27.2214.dt"  # noqa: RUF001
    )


def test_root_group_is_empty() -> None:
    context = SubstitutionContext("База", "", "8.3.27.2214", CONTEXT.started)
    assert substitute("{группа}|{база}", context, ENV) == "|База"


def test_environment_variables_expand_case_insensitively() -> None:
    assert substitute(r"%userprofile%\Documents", CONTEXT, ENV) == r"C:\Users\tester\Documents"


def test_unknown_substitution_and_variable_are_errors() -> None:
    with pytest.raises(SubstitutionError, match=r"неизвестная подстановка {сервер}"):
        substitute("{сервер}.dt", CONTEXT, ENV)
    with pytest.raises(SubstitutionError, match="не задана переменная окружения %NOPE%"):
        substitute(r"%NOPE%\x.dt", CONTEXT, ENV)


def test_text_without_markers_is_untouched() -> None:
    assert substitute(r"D:\Бэкапы\база.dt", CONTEXT, ENV) == r"D:\Бэкапы\база.dt"


def test_step_problems() -> None:
    catalog = load_cli_catalog()
    assert step_problems(Step("/DumpIB", (r"D:\x.dt",)), catalog) == ()
    assert step_problems(Step("/NoSuch"), catalog) == ("команды нет в каталоге",)
    assert step_problems(Step("/DumpIB", (None,)), catalog) == (
        "не задан обязательный параметр «файл выгрузки»",
    )
    assert step_problems(Step("/DumpIB", (" ",)), catalog) == (
        "не задан обязательный параметр «файл выгрузки»",
    )
    assert step_problems(Step("/DumpIB", ("{сервер}.dt",)), catalog) == (
        "неизвестная подстановка {сервер}",
    )


_BINARY = "недопустимое значение параметра «двоичные данные — во встроенное хранилище»"
_JOBS = "параметр «число фоновых заданий загрузки (0 — по числу процессоров)» — целое число"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((r"D:\x.dt", "+"), ()),
        ((r"D:\x.dt", "-"), ()),
        ((r"D:\x.dt", "yes"), (_BINARY,)),
        ((r"D:\x.dt", ""), (_BINARY,)),
        ((r"D:\x.dt", "+ /UpdateDBCfg"), (_BINARY,)),
        ((r"D:\x.dt", None, "4"), ()),
        ((r"D:\x.dt", None, "0"), ()),
        ((r"D:\x.dt", None, "4 /UpdateDBCfg"), (_JOBS,)),
        ((r"D:\x.dt", None, "-1"), ()),  # знак допустим: `-v -1` — последняя версия хранилища
        ((r"D:\x.dt", None, "1-"), (_JOBS,)),
        ((r"D:\x.dt", None, "--1"), (_JOBS,)),
        ((r"D:\x.dt", None, ""), (_JOBS,)),
        ((r"D:\x.dt", None, "٣"), (_JOBS,)),  # арабская цифра: `\d` её пропустил бы
    ],
)
def test_enum_and_int_values_are_checked_by_the_catalog(
    values: tuple[str | None, ...], expected: tuple[str, ...]
) -> None:
    assert step_problems(Step("/RestoreIB", values), load_cli_catalog()) == expected


def _values_by_flag(command_name: str, **by_flag: str) -> tuple[str | None, ...]:
    command = load_cli_catalog().command(command_name)
    assert command is not None
    return tuple(by_flag.get((arg.flag or "").lstrip("-"), None) for arg in command.args)


def test_enum_value_carrying_another_command_is_refused() -> None:
    """Значение enum, несущее `/RestoreIB`, не должно попасть в argv: опасность сценария
    считалась бы по `/CompareCfg` (NONE), и красного подтверждения не было бы."""
    catalog = load_cli_catalog()
    good = {
        "FirstConfigurationType": "MainConfiguration",
        "SecondConfigurationType": "DBConfiguration",
        "ReportType": "Brief",
        "ReportFormat": "txt",
        "ReportFile": r"D:\report.txt",
    }
    compare = _values_by_flag("/CompareCfg", **good)
    assert step_problems(Step("/CompareCfg", compare), catalog) == ()
    bad = {**good, "FirstConfigurationType": 'MainConfiguration /RestoreIB "C:\\x.dt"'}
    compare = _values_by_flag("/CompareCfg", **bad)
    assert step_problems(Step("/CompareCfg", compare), catalog) == (
        "недопустимое значение параметра «откуда взять первую конфигурацию»",
    )


@pytest.mark.parametrize(
    ("value", "ok"), [(None, True), ("", True), ("false", False), ("x", False)]
)
def test_flag_value_is_none_or_empty(value: str | None, ok: bool) -> None:
    flags = {"update": value} if value is not None else {}
    values = (r"D:\tree", *_values_by_flag("/DumpConfigToFiles", **flags)[1:])
    expected = () if ok else (
        "недопустимое значение параметра «обновить прежнюю выгрузку: записать только "
        "изменившиеся объекты»",
    )
    assert step_problems(Step("/DumpConfigToFiles", values), load_cli_catalog()) == expected


@pytest.mark.parametrize("char", ["\t", "\r", "\n", "\x00", "\x1f"])
def test_control_characters_in_any_value_are_refused(char: str) -> None:
    catalog = load_cli_catalog()
    problems = step_problems(Step("/DumpIB", (f"D:\\a{char}b.dt",)), catalog)
    assert problems == ("параметр «файл выгрузки» содержит управляющий символ",)
    extension = step_problems(Step("/DumpCfg", (r"D:\a.cf", f"Расш{char}/RestoreIB")), catalog)
    assert extension == ("параметр «имя расширения» содержит управляющий символ",)
    assert "RestoreIB" not in " ".join(extension)


def test_bound_argument_must_not_carry_a_value() -> None:
    catalog = load_cli_catalog()
    command = catalog.command("/ConfigurationRepositoryUpdateCfg")
    assert command is not None
    values: tuple[str | None, ...] = tuple(
        "tcp://evil" if arg.kind.value == "bound" else None for arg in command.args
    )
    assert step_problems(Step("/ConfigurationRepositoryUpdateCfg", values), catalog) == (
        ("параметр берётся из свойств базы и в шаге не задаётся",) * 3
    )
    assert step_problems(Step("/ConfigurationRepositoryUpdateCfg"), catalog) == ()


def test_step_with_wrong_number_of_values_is_a_problem() -> None:
    catalog = load_cli_catalog()
    assert step_problems(Step("/DumpIB", ("a.dt", "лишнее")), catalog) == (
        "число значений не совпадает с числом параметров команды",  # noqa: RUF001
    )
    # Короткий кортеж допустим: недостающие значения — «не задано».
    restore = catalog.command("/RestoreIB")
    assert restore is not None
    assert step_problems(Step("/RestoreIB", ("a.dt",)), catalog) == ()


def test_scenario_effect_is_the_maximum_of_steps() -> None:
    catalog = load_cli_catalog()
    dump, update, restore = (
        Step("/DumpIB", ("a.dt",)),
        Step("/UpdateDBCfg"),
        Step("/RestoreIB", ("a.dt",)),
    )
    assert scenario_effect(Scenario("1", "a", (dump,)), catalog) is Effect.NONE
    assert scenario_effect(Scenario("2", "b", (dump, update)), catalog) is Effect.MODIFIES
    assert scenario_effect(Scenario("3", "c", (dump, restore, update)), catalog) is Effect.REPLACES
    assert scenario_effect(Scenario("4", "d", ()), catalog) is Effect.NONE
    assert scenario_effect(Scenario("5", "e", (Step("/NoSuch"),)), catalog) is Effect.NONE


_RESTORE_DT = next(s for s in BUILTIN_SCENARIOS if s.id == "builtin:restore-dt")


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        (_RESTORE_DT.steps, ((0, 0),)),
        ((Step("/RestoreIB", (r"D:\a.dt",)),), ()),
        ((Step("/RestoreIB", (" ",)),), ((0, 0),)),
        ((Step("/RestoreIB"),), ((0, 0),)),
        ((Step("/DumpIB", (None,)),), ()),  # выход, а не вход  # noqa: RUF003
        ((Step("/UpdateCfg", (None, None)),), ((0, 0), (0, 1))),
        ((Step("/DumpIB", (r"D:\a.dt",)), Step("/LoadCfg", (None,))), ((1, 0),)),
        ((Step("/LoadConfigFromFiles"),), ()),  # каталог не обязателен (есть -Archive)
        ((Step("/NoSuch", (None,)),), ()),
        ((), ()),
    ],
)
def test_missing_inputs(steps: tuple[Step, ...], expected: tuple[tuple[int, int], ...]) -> None:
    assert missing_inputs(Scenario("x", "x", steps), load_cli_catalog()) == expected


def _result(key: str, outcome: BaseOutcome) -> BaseResult:
    return BaseResult(key, key, outcome)


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ((), ()),
        (
            (
                ("a", BaseOutcome.OK), ("b", BaseOutcome.FAILED), ("c", BaseOutcome.INTERRUPTED),
                ("d", BaseOutcome.CANCELLED), ("e", BaseOutcome.NOT_READY),
            ),
            ("b", "c"),
        ),
        ((("b", BaseOutcome.FAILED), ("b", BaseOutcome.FAILED)), ("b",)),
        ((("a", BaseOutcome.OK),), ()),
    ],
)
def test_failed_keys(
    outcomes: tuple[tuple[str, BaseOutcome], ...], expected: tuple[str, ...]
) -> None:
    record = RunRecord(
        "u1", "Сценарий", datetime(2026, 11, 14), r"C:\ops\run",
        tuple(_result(key, outcome) for key, outcome in outcomes),
    )
    assert failed_keys(record) == expected


def test_builtin_scenarios() -> None:
    catalog = load_cli_catalog()
    by_name = {scenario.name: scenario for scenario in BUILTIN_SCENARIOS}
    assert set(by_name) == {"Выгрузить в .dt", "Загрузить из .dt", "Выгрузить .cf"}
    assert all(s.builtin and s.bases is None and s.stop_on_error for s in BUILTIN_SCENARIOS)
    assert len({s.id for s in BUILTIN_SCENARIOS}) == 3
    dump = by_name["Выгрузить в .dt"].steps[0]
    assert dump.command == "/DumpIB"
    assert dump.values[0] == r"%USERPROFILE%\Documents\OneCStarter\{база}_{дата}_{время}.dt"
    assert step_problems(dump, catalog) == ()
    # У загрузки файл не задан: его выбирают при запуске (спека §5.1, §7.5).  # noqa: RUF003
    restore = by_name["Загрузить из .dt"].steps[0]
    assert restore.command == "/RestoreIB" and restore.values == (None,)
    assert scenario_effect(by_name["Загрузить из .dt"], catalog) is Effect.REPLACES
    cf = by_name["Выгрузить .cf"].steps[0]
    assert cf.command == "/DumpCfg"
    assert cf.values[0] is not None and cf.values[0].endswith(".cf")


def test_environment_values_are_inserted_literally_and_not_rescanned() -> None:
    result = substitute(r"%HOME%\{база}.dt", CONTEXT, {"HOME": r"C:\U\{x}\%Y%"})
    assert result == r"C:\U\{x}\%Y%\Бухгалтерия_ филиал.dt"


def test_substitution_values_are_not_re_expanded() -> None:
    context = SubstitutionContext("%USERPROFILE% {дата}", "", "8.3", CONTEXT.started)
    assert substitute("{база}.dt", context, ENV) == "%USERPROFILE% {дата}.dt"


def test_single_percent_is_left_alone() -> None:
    assert substitute(r"D:\50%.dt", CONTEXT, ENV) == r"D:\50%.dt"


def test_two_percents_in_one_component_are_an_environment_variable() -> None:
    with pytest.raises(SubstitutionError) as error:
        substitute(r"D:\50% и 60%.dt", CONTEXT, ENV)
    assert str(error.value) == "не задана переменная окружения % и 60%"


def _cmd(name: str):  # type: ignore[no-untyped-def]
    command = load_cli_catalog().command(name)
    assert command is not None
    return command


def test_step_arguments_for_os_auth_base() -> None:
    text = build_step_arguments(
        ib_name='Склад "Юг"', credentials=None, out_path=r"C:\ops\step1.log",
        result_path=r"C:\ops\step1.result", repository=None,
        command=_cmd("/DumpIB"), values=(r"D:\Бэкапы\юг.dt",),
    )
    assert text == (
        'DESIGNER /IBName"Склад ""Юг""" /AppAutoCheckVersion- /DisableStartupDialogs '
        '/DisableStartupMessages /Out "C:\\ops\\step1.log" /DumpResult "C:\\ops\\step1.result" '
        '/DumpIB "D:\\Бэкапы\\юг.dt"'
    )


def test_step_arguments_with_login_and_password() -> None:
    text = build_step_arguments(
        ib_name="База", credentials=Credentials("Иванов", 'p"w'), out_path="o", result_path="r",
        repository=None, command=_cmd("/DumpIB"), values=("a.dt",),
    )
    assert text.startswith('DESIGNER /IBName"База" /N"Иванов" /P"p""w" /AppAutoCheckVersion- ')


def test_login_without_password_passes_only_the_name() -> None:
    text = build_step_arguments(
        ib_name="База", credentials=Credentials("Иванов"), out_path="o", result_path="r",
        repository=None, command=_cmd("/DumpIB"), values=("a.dt",),
    )
    assert '/N"Иванов" /AppAutoCheckVersion-' in text and "/P" not in text


def test_repository_keys_only_for_bound_commands() -> None:
    access = RepositoryAccess("tcp://repo/main", "builder", "s3cret")
    bound = build_step_arguments(
        ib_name="База", credentials=None, out_path="o", result_path="r", repository=access,
        command=_cmd("/ConfigurationRepositoryUpdateCfg"), values=(),
    )
    assert (
        '/DumpResult "r" /ConfigurationRepositoryF "tcp://repo/main" '
        '/ConfigurationRepositoryN "builder" /ConfigurationRepositoryP "s3cret" '
        "/ConfigurationRepositoryUpdateCfg"
    ) in bound
    plain = build_step_arguments(
        ib_name="База", credentials=None, out_path="o", result_path="r", repository=access,
        command=_cmd("/DumpIB"), values=("a.dt",),
    )
    assert "ConfigurationRepository" not in plain


def test_repository_without_address_and_password_omits_those_keys() -> None:
    text = build_step_arguments(
        ib_name="База", credentials=None, out_path="o", result_path="r",
        repository=RepositoryAccess(None, "builder"),
        command=_cmd("/ConfigurationRepositoryUpdateCfg"), values=(),
    )
    assert '/ConfigurationRepositoryN "builder"' in text
    assert "/ConfigurationRepositoryF" not in text and "/ConfigurationRepositoryP" not in text


def test_bound_command_without_repository_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="хранилищ"):
        build_step_arguments(
            ib_name="База", credentials=None, out_path="o", result_path="r", repository=None,
            command=_cmd("/ConfigurationRepositoryUpdateCfg"), values=(),
        )


def test_command_words_cover_every_argument_kind() -> None:
    restore = _cmd("/RestoreIB")
    assert command_words(restore, ("a b.dt", "-", "4")) == [
        "/RestoreIB", '"a b.dt"', "-UseBinaryDataStorage-", "-JobsCount 4",
    ]
    assert command_words(restore, ("a.dt",)) == ["/RestoreIB", '"a.dt"']
    lock = _cmd("/ConfigurationRepositoryLock")
    values = tuple("" if arg.kind.value == "flag" else None for arg in lock.args)
    assert "-revised" in command_words(lock, values)
    dump_cfg = _cmd("/DumpCfg")
    assert command_words(dump_cfg, ("a.cf", 'Мое "Расш"')) == [  # noqa: RUF001
        "/DumpCfg", '"a.cf"', '-Extension "Мое ""Расш"""',  # noqa: RUF001
    ]


def test_passwords_are_not_in_repr() -> None:
    assert "s3cret" not in repr(RepositoryAccess("a", "u", "s3cret"))


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\xef\xbb\xbf" + "Ошибка".encode(), "Ошибка"),
        ("Ошибка".encode(), "Ошибка"),
        ("Ошибка".encode("cp1251"), "Ошибка"),
        (b"", ""),
    ],
)
def test_decode_log_by_fact(data: bytes, expected: str) -> None:
    assert decode_log(data) == expected


@pytest.mark.parametrize(
    ("code", "dump_result", "expected"),
    [
        (0, "0", True), (0, None, False), (0, " 0\r\n", True), (0, "\ufeff0", True),
        (0, "1", False), (1, "0", False), (1, "1", False), (1, None, False),
        (None, "0", False), (-1, None, False), (0, "", False), (0, "мусор", False),
    ],
)
def test_step_succeeded(code: int | None, dump_result: str | None, expected: bool) -> None:
    assert step_succeeded(code, dump_result) is expected


def test_error_text_is_the_last_non_empty_line() -> None:
    log = (
        "Соединение с хранилищем конфигурации не установлено\r\n"  # noqa: RUF001
        "Соединение с хранилищем конфигурации не установлено\r\n"  # noqa: RUF001
        "Ошибка обновления конфигурации из хранилища\r\n\r\n  \r\n"
    )
    assert error_text(log, 1) == "Ошибка обновления конфигурации из хранилища"
    assert error_text("Одна строка", 1) == "Одна строка"
    assert error_text("", 1) == "код возврата 1"
    assert error_text(" \r\n", None) == "код возврата неизвестен"


def test_leftovers_of_dump_ib() -> None:
    assert leftovers(_cmd("/DumpIB"), (r"D:\out\X1.dt",)) == (r"D:\out\X1.n1",)
    assert leftovers(_cmd("/DumpIB"), (r"D:\out\архив",)) == (r"D:\out\архив.n1",)
    assert leftovers(_cmd("/DumpIB"), (None,)) == ()
    assert leftovers(_cmd("/DumpIB"), ("D:\\",)) == ()
    assert leftovers(_cmd("/DumpIB"), ("",)) == ()
    assert leftovers(_cmd("/DumpIB"), ("D:",)) == ()
    assert leftovers(_cmd("/DumpCfg"), ("a.cf",)) == ()
