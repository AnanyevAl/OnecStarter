"""Исполнитель пакетных операций: готовность и выполнение (спека v4, §6). Процессы 1С
не порождаются — порождение подменено."""  # noqa: RUF002

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.operations import BaseOutcome, Scenario, Step, StepStatus
from onecstarter.domain.version import parse_version
from onecstarter.platform_1c.job import JobError
from onecstarter.platform_1c.server_spawn import LoggedProcess
from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.services.errors import OperationsBusyError
from onecstarter.services.operations_runner import (
    MAX_PARALLEL,
    POLL_SECONDS,
    BaseFinished,
    CancelToken,
    OperationsRunner,
    RunFinished,
    StepFinished,
    StepStarted,
    readiness_text,
    step_log_path,
    step_result_path,
)
from onecstarter.services.workspace import BatchTarget

CATALOG = load_cli_catalog()
STARTED = datetime(2026, 11, 13, 9, 5, 7)
EXE = Path(r"C:\Program Files\1cv8\8.3.27.2214\bin\1cv8.exe")


def target(key: str = "id:1", name: str = "Бухгалтерия", **changes: object) -> BatchTarget:
    fields: dict[str, object] = {
        "key": key,
        "name": name,
        "group": "Клиенты",
        "executable": EXE,
        "version": parse_version("8.3.27.2214"),
    }
    fields.update(changes)
    return BatchTarget(**fields)  # type: ignore[arg-type]


def runner(tmp_path: Path, *targets: BatchTarget, **deps: object) -> OperationsRunner:
    by_key = {t.key: t for t in targets}
    return OperationsRunner(
        lambda key: by_key.get(key, BatchTarget(key, "", problems=("база не найдена в списке",))),
        CATALOG,
        tmp_path / "ops",
        environ={"USERPROFILE": str(tmp_path / "home")},
        now=lambda: STARTED,
        **deps,  # type: ignore[arg-type]
    )


def dump(tmp_path: Path, **changes: object) -> Scenario:
    step = Step("/DumpIB", (str(tmp_path / "out" / "{база}_{дата}_{время}.dt"),), **changes)  # type: ignore[arg-type]
    return Scenario("u1", "Резерв: ночь", (step,))


def test_prepare_resolves_paths_and_layout(tmp_path: Path) -> None:
    plan = runner(tmp_path, target()).prepare(dump(tmp_path), ["id:1"])
    assert plan.started == STARTED
    assert plan.logs_dir == tmp_path / "ops" / "2026-11-13_090507_Резерв_ ночь"
    base = plan.bases[0]
    assert base.ready and base.problems == ()
    expected = tmp_path / "out" / "Бухгалтерия_2026-11-13_090507.dt"
    assert base.steps[0].values == (str(expected),)
    assert base.steps[0].outputs == (expected,)
    assert base.credentials is None and base.repository is None


def test_prepare_assigns_every_base_its_logs_dir_by_position(tmp_path: Path) -> None:
    plan = runner(tmp_path, target(), target("id:2", "Склад: юг")).prepare(
        dump(tmp_path), ["id:2", "id:9", "id:1"]
    )
    assert [base.logs_dir for base in plan.bases] == [
        plan.logs_dir / "01_Склад_ юг",
        plan.logs_dir / "02_",  # неготовая база — та же формула
        plan.logs_dir / "03_Бухгалтерия",
    ]


def test_second_run_in_the_same_second_gets_a_suffix(tmp_path: Path) -> None:
    subject = runner(tmp_path, target())
    first = subject.prepare(dump(tmp_path), ["id:1"]).logs_dir
    first.mkdir(parents=True)
    second = subject.prepare(dump(tmp_path), ["id:1"]).logs_dir
    assert second == first.with_name(first.name + "_2")
    second.mkdir()
    third = subject.prepare(dump(tmp_path), ["id:1"])
    assert third.logs_dir == first.with_name(first.name + "_3")
    assert third.bases[0].logs_dir == third.logs_dir / "01_Бухгалтерия"


def test_prepare_does_not_touch_the_file_system(tmp_path: Path) -> None:
    runner(tmp_path, target()).prepare(dump(tmp_path), ["id:1"])
    assert not (tmp_path / "ops").exists() and not (tmp_path / "out").exists()


def test_target_problems_pass_through_and_base_is_not_ready(tmp_path: Path) -> None:
    plan = runner(tmp_path).prepare(dump(tmp_path), ["id:9"])
    assert plan.bases[0].problems == ("база не найдена в списке",)
    assert not plan.bases[0].ready


def test_password_is_needed_unless_stored_or_typed(tmp_path: Path) -> None:
    subject = runner(tmp_path, target(login="Иванов"))
    needs = subject.prepare(dump(tmp_path), ["id:1"]).bases[0]
    # «Нужен пароль» — не проблема, а признак: его исправит окно запуска.  # noqa: RUF003
    assert needs.problems == () and needs.needs_password == "Иванов" and not needs.ready
    assert readiness_text(needs) == ("нужен пароль пользователя «Иванов»",)
    typed = subject.prepare(dump(tmp_path), ["id:1"], {"id:1": ""}).bases[0]
    assert typed.ready and typed.credentials is not None
    assert typed.credentials.login == "Иванов" and typed.credentials.password == ""
    stored = (
        runner(tmp_path, target(login="Иванов", password="pw"))
        .prepare(dump(tmp_path), ["id:1"])
        .bases[0]
    )
    assert stored.ready and stored.credentials is not None and stored.credentials.password == "pw"


def test_typed_password_wins_over_the_stored_one(tmp_path: Path) -> None:
    base = (
        runner(tmp_path, target(login="Иванов", password="old"))
        .prepare(dump(tmp_path), ["id:1"], {"id:1": "new"})
        .bases[0]
    )
    assert base.credentials is not None and base.credentials.password == "new"


def test_repository_data_is_required_only_for_bound_steps(tmp_path: Path) -> None:
    update = Scenario("u2", "Из хранилища", (Step("/ConfigurationRepositoryUpdateCfg"),))
    assert runner(tmp_path, target()).prepare(update, ["id:1"]).bases[0].problems == (
        "не задан пользователь хранилища конфигурации",
    )
    ready = (
        runner(tmp_path, target(repository_user="builder", repository_password="rpw"))
        .prepare(update, ["id:1"])
        .bases[0]
    )
    assert ready.ready and ready.repository is not None
    assert (ready.repository.address, ready.repository.user) == (None, "builder")
    assert runner(tmp_path, target()).prepare(dump(tmp_path), ["id:1"]).bases[0].ready


UPDATE = Scenario("u2", "Из хранилища", (Step("/ConfigurationRepositoryUpdateCfg"),))


def test_repository_password_is_needed_unless_stored_or_typed(tmp_path: Path) -> None:
    subject = runner(tmp_path, target(repository_user="builder"))
    needs = subject.prepare(UPDATE, ["id:1"]).bases[0]
    assert needs.problems == () and needs.needs_repository_password and not needs.ready
    assert needs.repository is None
    assert readiness_text(needs) == ("нужен пароль хранилища конфигурации",)
    typed = subject.prepare(UPDATE, ["id:1"], repository_passwords={"id:1": ""}).bases[0]
    assert typed.ready and typed.repository is not None and typed.repository.password == ""


def test_typed_repository_password_wins_over_the_stored_one(tmp_path: Path) -> None:
    subject = runner(tmp_path, target(repository_user="builder", repository_password="old"))
    base = subject.prepare(UPDATE, ["id:1"], repository_passwords={"id:1": "new"}).bases[0]
    assert base.ready and base.repository is not None and base.repository.password == "new"
    assert "new" not in repr(base)


def test_both_passwords_needed_and_store_unavailable_is_one_line(tmp_path: Path) -> None:
    broken = target(login="Иванов", repository_user="builder", store_unavailable=True)
    base = runner(tmp_path, broken).prepare(UPDATE, ["id:1"]).bases[0]
    assert base.problems == () and base.store_unavailable and not base.ready
    assert readiness_text(base) == (
        "нужен пароль пользователя «Иванов»",
        "нужен пароль хранилища конфигурации",
        "диспетчер учётных данных Windows недоступен — пароль нужно ввести",
    )


def test_typed_passwords_rescue_a_base_with_an_unavailable_store(tmp_path: Path) -> None:
    broken = target(login="Иванов", repository_user="builder", store_unavailable=True)
    base = (
        runner(tmp_path, broken)
        .prepare(UPDATE, ["id:1"], {"id:1": "pw"}, {"id:1": "rpw"})
        .bases[0]
    )
    assert base.ready and readiness_text(base) == ()


def test_store_unavailable_without_a_login_is_ready(tmp_path: Path) -> None:
    base = runner(tmp_path, target(store_unavailable=True)).prepare(dump(tmp_path), ["id:1"])
    assert base.bases[0].ready and readiness_text(base.bases[0]) == ()


def test_needs_and_problems_together(tmp_path: Path) -> None:
    duplicate = target(login="Иванов", problems=("имя базы в списке не единственное",))
    subject = runner(tmp_path, duplicate)
    base = subject.prepare(dump(tmp_path), ["id:1"]).bases[0]
    assert base.problems == ("имя базы в списке не единственное",)
    assert readiness_text(base) == (
        "имя базы в списке не единственное", "нужен пароль пользователя «Иванов»",
    )


def test_not_ready_record_carries_the_readiness_text(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target(login="Иванов"))
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, CancelToken())
    assert record.bases[0].outcome is BaseOutcome.NOT_READY
    assert record.bases[0].problems == ("нужен пароль пользователя «Иванов»",)
    assert world.commands == [] and record.bases[0].logs_dir == ""


def test_unavailable_file_base_directory(tmp_path: Path) -> None:
    missing = str(tmp_path / "нет")
    problems = (
        runner(tmp_path, target(file_path=missing)).prepare(dump(tmp_path), ["id:1"]).bases[0]
    ).problems
    assert problems == (f"каталог базы недоступен: {missing}",)
    (tmp_path / "db").mkdir()
    assert (
        runner(tmp_path, target(file_path=str(tmp_path / "db")))
        .prepare(dump(tmp_path), ["id:1"])
        .bases[0]
        .ready
    )


def test_existing_output_blocks_unless_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "Бухгалтерия_2026-11-13_090507.dt"
    existing.write_bytes(b"x")
    blocked = runner(tmp_path, target()).prepare(dump(tmp_path), ["id:1"]).bases[0]
    assert blocked.problems == (f"шаг 1 (/DumpIB): файл уже существует: {existing}",)
    allowed = runner(tmp_path, target()).prepare(dump(tmp_path, overwrite=True), ["id:1"])
    assert allowed.bases[0].ready


def test_missing_input_file_and_unfilled_step(tmp_path: Path) -> None:
    restore = Scenario("u3", "Загрузка", (Step("/RestoreIB", (str(tmp_path / "нет.dt"),)),))
    assert runner(tmp_path, target()).prepare(restore, ["id:1"]).bases[0].problems == (
        f"шаг 1 (/RestoreIB): входной файл не найден: {tmp_path / 'нет.dt'}",
    )
    unfilled = Scenario("u4", "Загрузка", (Step("/RestoreIB", (None,)),))
    assert runner(tmp_path, target()).prepare(unfilled, ["id:1"]).bases[0].problems == (
        "шаг 1 (/RestoreIB): не задан обязательный параметр «файл выгрузки»",
    )


def test_step_problems_are_numbered(tmp_path: Path) -> None:
    scenario = Scenario(
        "u5",
        "Плохой",
        (
            Step("/DumpIB", (str(tmp_path / "a.dt"),)),
            Step("/NoSuch"),
            Step("/DumpCfg", (r"%NOPE%\a.cf",)),
        ),
    )
    assert runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0].problems == (
        "шаг 2 (/NoSuch): команды нет в каталоге",
        "шаг 3 (/DumpCfg): не задана переменная окружения %NOPE%",
    )


def test_two_steps_writing_the_same_file_conflict(tmp_path: Path) -> None:
    path = str(tmp_path / "a.dt")
    scenario = Scenario("u6", "Дважды", (Step("/DumpIB", (path,)), Step("/DumpIB", (path,))))
    assert runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0].problems == (
        f"шаг 2 (/DumpIB): файл уже существует: {tmp_path / 'a.dt'}",
    )


def test_version_of_the_base_goes_into_the_substitution(tmp_path: Path) -> None:
    scenario = Scenario(
        "u7", "Версия", (Step("/DumpIB", (str(tmp_path / "{версия}_{группа}.dt"),)),)
    )
    base = runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0]
    assert base.steps[0].values == (str(tmp_path / "8.3.27.2214_Клиенты.dt"),)


def test_input_may_be_the_output_of_an_earlier_step(tmp_path: Path) -> None:
    path = str(tmp_path / "a.cf")
    scenario = Scenario("u8", "Цепочка", (Step("/DumpCfg", (path,)), Step("/LoadCfg", (path,))))
    base = runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0]
    assert base.ready and len(base.steps) == 2


def test_input_of_a_step_is_not_satisfied_by_a_later_step(tmp_path: Path) -> None:
    path = str(tmp_path / "a.cf")
    scenario = Scenario("u9", "Наоборот", (Step("/LoadCfg", (path,)), Step("/DumpCfg", (path,))))
    assert runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0].problems == (
        f"шаг 1 (/LoadCfg): входной файл не найден: {tmp_path / 'a.cf'}",
    )


def test_typed_password_without_a_login_is_ignored(tmp_path: Path) -> None:
    base = runner(tmp_path, target()).prepare(dump(tmp_path), ["id:1"], {"id:1": "pw"}).bases[0]
    assert base.ready and base.credentials is None


def test_existing_output_directory_blocks_unless_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "tree"
    out.mkdir()
    scenario = Scenario("u10", "Файлы", (Step("/DumpConfigToFiles", (str(out),)),))
    assert runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0].problems == (
        f"шаг 1 (/DumpConfigToFiles): файл уже существует: {out}",
    )


def test_ready_base_has_a_prepared_step_for_every_scenario_step(tmp_path: Path) -> None:
    scenario = Scenario(
        "u11",
        "Два",
        (Step("/DumpIB", (str(tmp_path / "a.dt"),)), Step("/DumpCfg", (str(tmp_path / "a.cf"),))),
    )
    base = runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0]
    assert base.ready and len(base.steps) == len(scenario.steps)


@pytest.mark.parametrize("value", ["a.dt", r"\a.dt", "C:a.dt", r"out\{база}.dt"])
def test_path_must_be_absolute_after_substitution(tmp_path: Path, value: str) -> None:
    scenario = Scenario("u20", "Относительный", (Step("/DumpIB", (value,)),))
    base = runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0]
    resolved = value.replace("{база}", "Бухгалтерия")
    assert base.problems == (f"шаг 1 (/DumpIB): путь должен быть полным: {resolved}",)


def test_required_value_empty_after_substitution(tmp_path: Path) -> None:
    scenario = Scenario("u21", "Корень", (Step("/DumpCfg", (str(tmp_path / "a.cf"), None)),))
    assert runner(tmp_path, target()).prepare(scenario, ["id:1"]).bases[0].ready
    scenario = Scenario(
        "u21", "Корень", (Step("/ReduceEventLogSize", ("{группа}",)),)
    )
    base = runner(tmp_path, target(group="")).prepare(scenario, ["id:1"]).bases[0]
    assert base.problems == (
        "шаг 1 (/ReduceEventLogSize): не задан обязательный параметр "
        "«новая граница журнала, дата в виде ГГГГ-ММ-ДД»",  # noqa: RUF001
    )


def test_control_characters_in_an_environment_value_are_refused(tmp_path: Path) -> None:
    subject = OperationsRunner(
        lambda key: target(), CATALOG, tmp_path / "ops",
        environ={"OUT": str(tmp_path) + "\r\nx"}, now=lambda: STARTED,
    )
    scenario = Scenario("u22", "Окружение", (Step("/DumpIB", (r"%OUT%\a.dt",)),))
    assert subject.prepare(scenario, ["id:1"]).bases[0].problems == (
        "шаг 1 (/DumpIB): параметр «файл выгрузки» содержит управляющий символ",
    )


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"name": "Бух\nгалтерия"}, "имя базы содержит управляющий символ"),  # noqa: RUF001
        (
            {"login": "Ива\tнов", "password": "pw"},  # noqa: RUF001
            "имя пользователя базы содержит управляющий символ",
        ),
        ({"login": "Иванов", "password": "p\x00w"}, "пароль содержит управляющий символ"),
    ],
)
def test_control_characters_in_base_data_are_refused(
    tmp_path: Path, changes: dict[str, Any], problem: str
) -> None:
    base = runner(tmp_path, target(**changes)).prepare(dump(tmp_path), ["id:1"]).bases[0]
    assert problem in base.problems and not base.ready
    assert "p\x00w" not in " ".join(base.problems)


def test_control_characters_in_a_typed_password_are_refused(tmp_path: Path) -> None:
    subject = runner(tmp_path, target(login="Иванов"))
    base = subject.prepare(dump(tmp_path), ["id:1"], {"id:1": 'pw" /RestoreIB\r\n'}).bases[0]
    assert base.problems == ("пароль содержит управляющий символ",)
    assert "RestoreIB" not in repr(base)


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"repository_address": "tcp://repo\r\n"}, "адрес хранилища содержит управляющий символ"),
        ({"repository_user": "bui\tlder"}, "пользователь хранилища содержит управляющий символ"),
    ],
)
def test_control_characters_in_repository_data_are_refused(
    tmp_path: Path, changes: dict[str, Any], problem: str
) -> None:
    fields: dict[str, Any] = {"repository_user": "builder", "repository_password": "rpw"}
    fields.update(changes)
    update = Scenario("u23", "Из хранилища", (Step("/ConfigurationRepositoryUpdateCfg"),))
    base = runner(tmp_path, target(**fields)).prepare(update, ["id:1"]).bases[0]
    assert base.problems == (problem,)


class FakeJob:
    def __init__(self, world: "World") -> None:
        self.world = world
        self.closed = False
        self.closed_while_running = False
        self.process: FakeProcess | None = None

    def assign(self, process_handle: int) -> None: ...

    def pids(self) -> tuple[int, ...]:
        return ()

    def close(self) -> None:
        if self.world.job_refuses:
            raise JobError("CloseHandle отказал")
        if self.world.job_refusals > 0:
            self.world.job_refusals -= 1
            raise JobError("CloseHandle отказал")
        self.closed = True
        if self.process is not None and self.process.code is None:
            self.closed_while_running = True
            self.process.end(0, natural=False)  # [Ф] Э10: закрытие Job даёт код 0, файлов нет


class FakeProcess:
    """Процесс, который сам завершается через `polls` опросов с кодом `exit_code`.

    `/Out` и `/DumpResult` пишутся только при естественном завершении — снятый процесс
    результата не оставляет."""  # noqa: RUF002

    def __init__(
        self, world: "World", polls: int, exit_code: int, writer: Callable[[], None]
    ) -> None:
        self.world, self.polls, self.exit_code, self.writer = world, polls, exit_code, writer
        self.code: int | None = None
        self.killed = False

    def end(self, code: int, *, natural: bool) -> None:
        self.code = code
        self.world.running -= 1
        if natural:
            self.writer()

    def poll(self) -> int | None:
        if self.code is None:
            self.polls -= 1
            if self.polls <= 0:
                self.end(self.exit_code, natural=True)
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        return self.code if self.code is not None else 0

    def kill(self) -> None:
        if self.world.kill_refuses:
            raise OSError("доступ запрещён")
        self.killed = True
        if self.code is None:
            self.end(-1, natural=False)


class World:
    """Подменное порождение: запоминает команды, пишет /Out и /DumpResult как платформа."""

    def __init__(self) -> None:
        self.commands: list[LaunchCommand] = []
        self.jobs: list[FakeJob] = []
        # фрагмент команды → (код, журнал, опросы)
        self.script: dict[str, tuple[int, str, int]] = {}
        self.running = 0
        self.peak = 0
        self.spawn_error: Exception | None = None
        self.job_refuses = False
        self.job_refusals = 0  # сколько ближайших close() откажут
        self.kill_refuses = False
        self.dump_result: str | None = None  # перекрыть содержимое /DumpResult
        self.write_result = True  # False — штатный выход без файла /DumpResult
        self.clock = 0.0
        self.on_sleep: Callable[[], None] | None = None

    def job(self) -> FakeJob:
        job = FakeJob(self)
        self.jobs.append(job)
        return job

    def spawn(self, command: LaunchCommand, log_path: Path, job: FakeJob) -> LoggedProcess:
        if self.spawn_error is not None:
            raise self.spawn_error
        self.commands.append(command)
        code, log, polls = next(
            (value for fragment, value in self.script.items() if fragment in command.arguments),
            (0, "", 1),
        )
        out = _path_after(command.arguments, "/Out")
        result = _path_after(command.arguments, "/DumpResult")

        def write() -> None:
            out.write_bytes(b"\xef\xbb\xbf" + log.encode("utf-8"))
            if not self.write_result:
                return
            result.write_text(
                self.dump_result if self.dump_result is not None else str(code), encoding="utf-8"
            )

        process = FakeProcess(self, polls, code, write)
        job.process = process
        self.running += 1
        self.peak = max(self.peak, self.running)
        return LoggedProcess(pid=1, process=process)  # type: ignore[arg-type]

    def sleep(self, seconds: float) -> None:
        self.clock += seconds
        if self.on_sleep is not None:
            self.on_sleep()

    def monotonic(self) -> float:
        return self.clock


def _path_after(arguments: str, key: str) -> Path:
    tail = arguments.split(f'{key} "', 1)[1]
    return Path(tail.split('"', 1)[0])


def live(tmp_path: Path, world: World, *targets: BatchTarget) -> OperationsRunner:
    return runner(
        tmp_path, *targets, job_factory=world.job, spawn=world.spawn, sleep=world.sleep,
        monotonic=world.monotonic,
    )


def two_steps(tmp_path: Path, stop_on_error: bool = True) -> Scenario:
    return Scenario(
        "u1", "Резерв",
        (Step("/DumpIB", (str(tmp_path / "out" / "{база}.dt"),)),
         Step("/DumpCfg", (str(tmp_path / "out" / "{база}.cf"),))),
        stop_on_error=stop_on_error,
    )


def test_successful_run_emits_events_and_writes_logs(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    plan = subject.prepare(two_steps(tmp_path), ["id:1"])
    events: list[object] = []
    record = subject.run(plan, events.append, CancelToken())
    assert [type(event) for event in events] == [
        StepStarted, StepFinished, StepStarted, StepFinished, BaseFinished, RunFinished,
    ]
    base = record.bases[0]
    assert base.outcome is BaseOutcome.OK
    assert [(s.command, s.status, s.code) for s in base.steps] == [
        ("/DumpIB", StepStatus.OK, 0), ("/DumpCfg", StepStatus.OK, 0),
    ]
    assert (tmp_path / "out").is_dir()  # create_dirs
    base_dir = plan.logs_dir / "01_Бухгалтерия"
    assert plan.bases[0].logs_dir == base_dir and base.logs_dir == str(base_dir)
    assert step_log_path(base_dir, 0) == base_dir / "step1.log"
    assert step_result_path(base_dir, 1) == base_dir / "step2.result"
    assert step_log_path(base_dir, 0).exists() and step_result_path(base_dir, 1).exists()
    assert world.commands[0].executable == EXE
    assert '/DumpIB "' in world.commands[0].arguments
    assert events[-1] == RunFinished(record)
    assert record.logs_dir == str(plan.logs_dir) and record.started == STARTED


def test_passwords_never_reach_run_log(tmp_path: Path) -> None:
    world = World()
    subject = live(
        tmp_path, world,
        target(login="Иванов", password="p@ss-базы", repository_user="builder",
               repository_password="p@ss-хранилища"),
    )
    scenario = Scenario("u2", "Хранилище", (Step("/ConfigurationRepositoryUpdateCfg"),))
    plan = subject.prepare(scenario, ["id:1"])
    record = subject.run(plan, lambda event: None, CancelToken())
    assert "p@ss-базы" in world.commands[0].arguments  # в argv пароль есть — в журнале нет
    log = (plan.logs_dir / "01_Бухгалтерия" / "run.log").read_text(encoding="utf-8")
    assert "p@ss-базы" not in log and "p@ss-хранилища" not in log
    assert "/ConfigurationRepositoryUpdateCfg" in log
    assert "p@ss" not in repr(record) and "p@ss" not in repr(plan)


def test_failed_step_stops_only_its_base(tmp_path: Path) -> None:
    world = World()
    world.script = {'/IBName"Склад"': (1, "Соединение…\r\nФайл базы занят\r\n", 1)}  # noqa: RUF001
    subject = live(tmp_path, world, target(), target("id:2", "Склад"))
    record = subject.run(
        subject.prepare(two_steps(tmp_path), ["id:2", "id:1"]), lambda event: None, CancelToken()
    )
    failed, fine = record.bases
    assert failed.outcome is BaseOutcome.FAILED
    assert [(s.status, s.message) for s in failed.steps] == [
        (StepStatus.FAILED, "Файл базы занят"), (StepStatus.SKIPPED, ""),
    ]
    assert fine.outcome is BaseOutcome.OK


def test_without_stop_on_error_next_steps_still_run(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (1, "Ошибка", 1)}
    subject = live(tmp_path, world, target())
    record = subject.run(
        subject.prepare(two_steps(tmp_path, stop_on_error=False), ["id:1"]),
        lambda event: None, CancelToken(),
    )
    assert [s.status for s in record.bases[0].steps] == [StepStatus.FAILED, StepStatus.OK]
    assert record.bases[0].outcome is BaseOutcome.FAILED


def test_mismatched_dump_result_is_a_failure(tmp_path: Path) -> None:
    world = World()
    world.dump_result = "1"  # код возврата 0, а /DumpResult «1»  # noqa: RUF003
    subject = live(tmp_path, world, target())
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, CancelToken())
    step = record.bases[0].steps[0]
    assert (step.status, step.code, step.message) == (StepStatus.FAILED, 0, "код возврата 0")


def test_exit_code_zero_without_dump_result_is_a_failure(tmp_path: Path) -> None:
    world = World()
    world.write_result = False  # штатный выход, а /DumpResult не появился  # noqa: RUF003
    subject = live(tmp_path, world, target())
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, CancelToken())
    step = record.bases[0].steps[0]
    assert (step.status, step.code, step.message) == (
        StepStatus.FAILED, 0, "результат не получен (нет файла /DumpResult)",
    )
    assert record.bases[0].outcome is BaseOutcome.FAILED


def test_exit_code_zero_without_dump_result_shows_the_last_log_line(tmp_path: Path) -> None:
    world = World()
    world.write_result = False
    world.script = {"/DumpIB": (0, "Начало\r\nНе удалось записать файл\r\n", 1)}  # noqa: RUF001
    subject = live(tmp_path, world, target())
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, CancelToken())
    step = record.bases[0].steps[0]
    assert (step.status, step.message) == (StepStatus.FAILED, "Не удалось записать файл")  # noqa: RUF001


def test_not_ready_base_is_skipped_and_others_run(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    events: list[object] = []
    record = subject.run(
        subject.prepare(dump(tmp_path), ["id:9", "id:1"]), events.append, CancelToken()
    )
    assert isinstance(events[0], BaseFinished)
    assert record.bases[0].outcome is BaseOutcome.NOT_READY
    assert record.bases[0].problems == ("база не найдена в списке",)
    assert record.bases[1].outcome is BaseOutcome.OK
    assert len(world.commands) == 1


def test_output_that_appeared_after_prepare_fails_the_step_without_a_process(
    tmp_path: Path,
) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    plan = subject.prepare(dump(tmp_path), ["id:1"])
    plan.bases[0].steps[0].outputs[0].parent.mkdir(parents=True)
    plan.bases[0].steps[0].outputs[0].write_bytes("чужой файл".encode())
    record = subject.run(plan, lambda event: None, CancelToken())
    step = record.bases[0].steps[0]
    assert step.status is StepStatus.FAILED and "файл уже существует" in step.message
    assert world.commands == []
    assert plan.bases[0].steps[0].outputs[0].read_bytes() == "чужой файл".encode()


def test_sequential_by_default_and_at_most_four_in_parallel(tmp_path: Path) -> None:
    targets = [target(f"id:{n}", f"База {n}") for n in range(6)]
    keys = [t.key for t in targets]
    world = World()
    world.script = {"/DumpIB": (0, "", 3)}
    subject = live(tmp_path, world, *targets)
    subject.run(subject.prepare(dump(tmp_path), keys), lambda event: None, CancelToken())
    assert world.peak == 1
    world = World()
    world.script = {"/DumpIB": (0, "", 3)}
    subject = live(tmp_path, world, *targets)
    record = subject.run(
        subject.prepare(dump(tmp_path), keys), lambda event: None, CancelToken(), parallel=True
    )
    assert world.peak == MAX_PARALLEL == 4
    assert all(base.outcome is BaseOutcome.OK for base in record.bases)
    assert [base.key for base in record.bases] == keys  # порядок записи — порядок плана


def test_soft_cancel_lets_the_running_step_finish(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 3)}
    subject = live(tmp_path, world, target(), target("id:2", "Склад"))
    cancel = CancelToken()
    at_finish: list[tuple[bool, float]] = []

    def on_event(event: object) -> None:
        if isinstance(event, StepStarted):
            cancel.request_soft()
        if isinstance(event, StepFinished):
            at_finish.append((world.jobs[0].closed_while_running, world.clock))

    record = subject.run(subject.prepare(two_steps(tmp_path), ["id:1", "id:2"]), on_event, cancel)
    first, second = record.bases
    assert [s.status for s in first.steps] == [StepStatus.OK, StepStatus.SKIPPED]
    assert first.outcome is BaseOutcome.CANCELLED
    assert second.outcome is BaseOutcome.CANCELLED and second.steps == ()
    assert len(world.commands) == 1
    # Шаг дожил сам: Job у живого процесса не закрывали, прошло не меньше 2 опросов.  # noqa: RUF003
    assert at_finish[0][0] is False and at_finish[0][1] >= 2 * POLL_SECONDS
    assert not any(job.closed_while_running for job in world.jobs)


def test_hard_cancel_closes_the_job_and_removes_the_partial_dump(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    subject = live(tmp_path, world, target(), target("id:2", "Склад"))
    plan = subject.prepare(two_steps(tmp_path), ["id:1", "id:2"])
    partial = plan.bases[0].steps[0].outputs[0].with_suffix(".n1")
    cancel = CancelToken()
    world.on_sleep = cancel.request_hard  # отмена приходит, когда процесс уже идёт

    def on_event(event: object) -> None:
        if isinstance(event, StepStarted):
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_bytes(b"half")  # платформа пишет во временный файл — Э10

    record = subject.run(plan, on_event, cancel)
    first, second = record.bases
    assert world.jobs[0].closed and world.jobs[0].closed_while_running
    assert [s.status for s in first.steps] == [StepStatus.INTERRUPTED, StepStatus.SKIPPED]
    assert first.outcome is BaseOutcome.INTERRUPTED
    assert second.outcome is BaseOutcome.CANCELLED
    assert not partial.exists()


def test_hard_cancel_with_a_refusing_job_kills_the_process(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    world.job_refuses = True
    subject = live(tmp_path, world, target())
    cancel = CancelToken()
    world.on_sleep = cancel.request_hard
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, cancel)
    step = record.bases[0].steps[0]
    process = world.jobs[0].process
    assert process is not None and process.killed
    assert step.status is StepStatus.INTERRUPTED and step.message == ""


def test_hard_cancel_with_job_and_kill_refusing_still_ends_the_run(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    world.job_refuses = world.kill_refuses = True
    subject = live(tmp_path, world, target())
    cancel = CancelToken()
    world.on_sleep = cancel.request_hard
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, cancel)
    step = record.bases[0].steps[0]
    assert step.status is StepStatus.INTERRUPTED and "не удалось снять процесс" in step.message
    assert subject.busy_keys() == frozenset()


def test_second_run_is_refused_while_the_first_is_active(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    plan = subject.prepare(dump(tmp_path), ["id:1"])
    seen: list[frozenset[str]] = []

    def on_event(event: object) -> None:
        if isinstance(event, StepStarted):
            seen.append(subject.busy_keys())
            with pytest.raises(OperationsBusyError, match="Уже выполняется другой сценарий"):
                subject.run(plan, lambda event: None, CancelToken())

    subject.run(plan, on_event, CancelToken())
    assert seen == [frozenset({"id:1"})]
    assert subject.busy_keys() == frozenset()
    # После завершения новый запуск возможен (выходной файл фейк не создаёт).
    subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda event: None, CancelToken())


def test_spawn_failure_fails_the_step_and_releases_the_runner(tmp_path: Path) -> None:
    world = World()
    world.spawn_error = OSError("нет файла")
    subject = live(tmp_path, world, target())
    plan = subject.prepare(dump(tmp_path), ["id:1"])
    record = subject.run(plan, lambda event: None, CancelToken())
    step = record.bases[0].steps[0]
    assert step.status is StepStatus.FAILED
    assert step.message.startswith("Не удалось запустить Конфигуратор")  # noqa: RUF001
    assert subject.busy_keys() == frozenset()


def test_value_error_from_the_spawn_fails_the_step_without_its_text(tmp_path: Path) -> None:
    world = World()
    world.spawn_error = ValueError("embedded null character in p@ss")
    subject = live(tmp_path, world, target(), target("id:2", "Склад"))
    record = subject.run(
        subject.prepare(two_steps(tmp_path), ["id:1", "id:2"]), lambda e: None, CancelToken()
    )
    for base in record.bases:
        assert base.outcome is BaseOutcome.FAILED
        assert base.steps[0].status is StepStatus.FAILED
        assert base.steps[0].message == (
            "Не удалось запустить Конфигуратор: недопустимая командная строка"  # noqa: RUF001
        )
    assert "p@ss" not in repr(record)
    assert subject.busy_keys() == frozenset()


def test_listener_failing_on_every_event_does_not_stop_the_steps(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 3)}
    subject = live(tmp_path, world, target(), target("id:2", "Склад"))
    plan = subject.prepare(two_steps(tmp_path), ["id:1", "id:2"])
    errors: list[RuntimeError] = []
    seen: list[object] = []

    def explode(event: object) -> None:
        seen.append(event)
        errors.append(RuntimeError(f"слушатель упал {len(errors)}"))
        raise errors[-1]

    record = subject.run(plan, explode, CancelToken(), parallel=True)
    assert len(world.commands) == 4  # все шаги обеих баз выполнены
    assert [base.outcome for base in record.bases] == [BaseOutcome.OK, BaseOutcome.OK]
    assert all(len(base.steps) == 2 for base in record.bases)
    assert not any(job.closed_while_running for job in world.jobs)
    assert subject.listener_failure is errors[0]  # первое, а не последнее  # noqa: RUF003
    assert sum(isinstance(e, BaseFinished) for e in seen) == 2
    assert isinstance(seen[-1], RunFinished)
    assert subject.busy_keys() == frozenset() and not subject.running


def test_listener_failure_is_reset_by_the_next_run(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())

    def explode(event: object) -> None:
        raise RuntimeError("слушатель упал")

    subject.run(subject.prepare(dump(tmp_path), ["id:1"]), explode, CancelToken())
    assert isinstance(subject.listener_failure, RuntimeError)
    subject.run(subject.prepare(dump(tmp_path, overwrite=True), ["id:1"]), lambda e: None,
                CancelToken())
    assert subject.listener_failure is None


class _Abort(BaseException):
    """Выход из программы посреди запуска — как KeyboardInterrupt."""


def test_base_exception_from_the_listener_closes_jobs_and_escapes(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    subject = live(tmp_path, world, target(), target("id:2", "Склад"))
    plan = subject.prepare(dump(tmp_path), ["id:1", "id:2"])
    started: list[str] = []

    def explode(event: object) -> None:
        if isinstance(event, StepStarted):
            started.append(event.key)
            if len(started) == 2:  # первый процесс уже идёт
                raise _Abort

    with pytest.raises(_Abort):
        subject.run(plan, explode, CancelToken(), parallel=True)
    assert len(world.jobs) == 1 and world.jobs[0].closed_while_running
    assert all(job.closed for job in world.jobs)
    assert subject.busy_keys() == frozenset() and not subject.running


def test_running_is_true_only_during_a_run(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    seen: list[bool] = []
    assert not subject.running
    subject.run(
        subject.prepare(dump(tmp_path), ["id:1"]),
        lambda event: seen.append(subject.running),
        CancelToken(),
    )
    assert seen and all(seen) and not subject.running


def test_step_that_failed_by_itself_during_hard_cancel_fails_the_base(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (1, "Файл базы занят", 2)}
    subject = live(tmp_path, world, target())
    cancel = CancelToken()

    def hook() -> None:
        process = world.jobs[-1].process
        assert process is not None
        process.poll()  # закончился сам с ошибкой, цикл этого не заметил  # noqa: RUF003
        cancel.request_hard()

    world.on_sleep = hook
    record = subject.run(subject.prepare(two_steps(tmp_path), ["id:1"]), lambda e: None, cancel)
    base = record.bases[0]
    assert [(s.status, s.message) for s in base.steps] == [
        (StepStatus.FAILED, "Файл базы занят"), (StepStatus.SKIPPED, ""),
    ]
    assert base.outcome is BaseOutcome.FAILED


def test_stale_step_log_is_removed_before_the_spawn(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    plan = subject.prepare(dump(tmp_path), ["id:1"])
    directory = plan.logs_dir / "01_Бухгалтерия"
    directory.mkdir(parents=True)
    step_log_path(directory, 0).write_text("Старая ошибка", encoding="utf-8")
    at_spawn: list[bool] = []
    original = world.spawn

    def spawn(command: LaunchCommand, log_path: Path, job: FakeJob) -> LoggedProcess:
        at_spawn.append(step_log_path(directory, 0).exists())
        return original(command, log_path, job)

    subject = runner(tmp_path, target(), job_factory=world.job, spawn=spawn, sleep=world.sleep,
                     monotonic=world.monotonic)
    subject.run(plan, lambda e: None, CancelToken())
    assert at_spawn == [False]


def test_partial_dump_is_removed_after_kill_when_the_job_refuses(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    world.job_refuses = True
    subject = live(tmp_path, world, target())
    plan = subject.prepare(dump(tmp_path), ["id:1"])
    partial = plan.bases[0].steps[0].outputs[0].with_suffix(".n1")
    cancel = CancelToken()

    def hook() -> None:
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"half")
        cancel.request_hard()

    world.on_sleep = hook
    record = subject.run(plan, lambda e: None, cancel)
    process = world.jobs[0].process
    assert process is not None and process.killed
    assert record.bases[0].steps[0].status is StepStatus.INTERRUPTED
    assert not partial.exists()


def test_job_is_closed_again_after_a_successful_kill(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    world.job_refusals = 1  # первое закрытие отказало, повторное проходит
    subject = live(tmp_path, world, target())
    cancel = CancelToken()
    world.on_sleep = cancel.request_hard
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, cancel)
    job = world.jobs[0]
    assert job.process is not None and job.process.killed
    assert job.closed  # хендл не потерян
    assert record.bases[0].steps[0].message == ""


def test_hard_cancel_with_a_drive_root_output_does_not_raise(tmp_path: Path) -> None:
    world = World()
    world.script = {"/DumpIB": (0, "", 1000)}
    subject = live(tmp_path, world, target())
    scenario = Scenario("u12", "Корень", (Step("/DumpIB", (tmp_path.anchor,), overwrite=True),))
    cancel = CancelToken()
    world.on_sleep = cancel.request_hard
    record = subject.run(subject.prepare(scenario, ["id:1"]), lambda e: None, cancel)
    assert record.bases[0].steps[0].status is StepStatus.INTERRUPTED


def test_job_creation_failure_fails_the_step_without_an_exception(tmp_path: Path) -> None:
    world = World()

    def refusing_job() -> FakeJob:
        raise JobError("CreateJobObject отказал")

    subject = runner(
        tmp_path, target(), job_factory=refusing_job, spawn=world.spawn, sleep=world.sleep,
        monotonic=world.monotonic,
    )
    record = subject.run(subject.prepare(dump(tmp_path), ["id:1"]), lambda e: None, CancelToken())
    step = record.bases[0].steps[0]
    assert step.status is StepStatus.FAILED and "CreateJobObject" in step.message
    assert world.commands == [] and subject.busy_keys() == frozenset()


def test_step_that_already_exited_is_not_reported_as_interrupted(tmp_path: Path) -> None:
    def run_with(scenario: Scenario) -> BaseOutcome:
        world = World()
        world.script = {"/DumpIB": (0, "", 2)}
        subject = live(tmp_path, world, target())
        cancel = CancelToken()

        def hook() -> None:
            process = world.jobs[-1].process
            assert process is not None
            process.poll()  # процесс закончился сам, цикл этого ещё не заметил
            cancel.request_hard()

        world.on_sleep = hook
        record = subject.run(subject.prepare(scenario, ["id:1"]), lambda e: None, cancel)
        base = record.bases[0]
        assert base.steps[0].status is StepStatus.OK and base.steps[0].code == 0
        assert not world.jobs[0].closed_while_running
        return base.outcome

    assert run_with(two_steps(tmp_path)) is BaseOutcome.INTERRUPTED
    assert run_with(dump(tmp_path)) is BaseOutcome.OK


def test_hard_cancel_before_the_spawn_does_not_start_a_process(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    cancel = CancelToken()
    events: list[object] = []

    def on_event(event: object) -> None:
        events.append(event)
        if isinstance(event, StepStarted):
            cancel.request_hard()

    record = subject.run(subject.prepare(two_steps(tmp_path), ["id:1"]), on_event, cancel)
    base = record.bases[0]
    assert [(s.status, s.message) for s in base.steps] == [
        (StepStatus.INTERRUPTED, ""), (StepStatus.SKIPPED, ""),
    ]
    assert base.outcome is BaseOutcome.INTERRUPTED
    assert world.commands == [] and world.jobs == []
    assert [type(e) for e in events] == [
        StepStarted, StepFinished, BaseFinished, RunFinished,
    ]


def test_stale_step_files_are_not_read_as_this_runs_result(tmp_path: Path) -> None:
    world = World()
    subject = live(tmp_path, world, target())
    plan = subject.prepare(dump(tmp_path), ["id:1"])
    directory = plan.logs_dir / "01_Бухгалтерия"
    directory.mkdir(parents=True)
    (directory / "step1.result").write_text("1", encoding="utf-8")
    (directory / "step1.log").write_text("Старая ошибка", encoding="utf-8")
    original = world.spawn

    def spawn(command: LaunchCommand, log_path: Path, job: FakeJob) -> LoggedProcess:
        assert not (directory / "step1.result").exists()  # к порождению старое убрано
        return original(command, log_path, job)

    subject = runner(tmp_path, target(), job_factory=world.job, spawn=spawn, sleep=world.sleep,
                     monotonic=world.monotonic)
    record = subject.run(plan, lambda e: None, CancelToken())
    step = record.bases[0].steps[0]
    assert step.status is StepStatus.OK and step.message == ""


def shared_output(tmp_path: Path, **changes: object) -> Scenario:
    step = Step("/DumpIB", (str(tmp_path / "out" / "{дата}.dt"),), **changes)  # type: ignore[arg-type]
    return Scenario("u13", "Общий файл", (step,))


@pytest.mark.parametrize("overwrite", [False, True])
def test_two_bases_writing_the_same_file_conflict(tmp_path: Path, overwrite: bool) -> None:
    subject = runner(tmp_path, target(), target("id:2", "Склад"))
    plan = subject.prepare(shared_output(tmp_path, overwrite=overwrite), ["id:1", "id:2"])
    first, second = plan.bases
    shared = tmp_path / "out" / "2026-11-13.dt"
    assert first.ready
    assert second.problems == (f"шаг 1 (/DumpIB): тот же файл пишет база «Бухгалтерия»: {shared}",)


def test_bases_with_their_own_files_do_not_conflict(tmp_path: Path) -> None:
    subject = runner(tmp_path, target(), target("id:2", "Склад"))
    plan = subject.prepare(dump(tmp_path), ["id:1", "id:2"])
    assert all(base.ready for base in plan.bases)


def test_not_ready_base_still_claims_its_outputs(tmp_path: Path) -> None:
    first = target(file_path=str(tmp_path / "нет"))  # каталог базы недоступен
    subject = runner(tmp_path, first, target("id:2", "Склад"))
    plan = subject.prepare(shared_output(tmp_path), ["id:1", "id:2"])
    assert not plan.bases[0].ready
    assert plan.bases[1].problems == (
        f"шаг 1 (/DumpIB): тот же файл пишет база «Бухгалтерия»: "
        f"{tmp_path / 'out' / '2026-11-13.dt'}",
    )


def test_prepare_takes_targets_from_the_given_snapshot(tmp_path: Path) -> None:
    subject = runner(tmp_path, target(name="Из списка"))
    snapshot = {"id:1": target(name="Снимок")}
    plan = subject.prepare(dump(tmp_path), ["id:1"], targets=snapshot.__getitem__)
    assert plan.bases[0].name == "Снимок"
    # Без снимка — прежний источник, заданный при создании исполнителя.
    assert subject.prepare(dump(tmp_path), ["id:1"]).bases[0].name == "Из списка"


def test_soft_cancel_can_be_revoked_but_hard_cannot() -> None:
    token = CancelToken()
    token.request_soft()
    token.revoke_soft()
    assert not token.soft
    token.request_hard()
    token.revoke_soft()
    assert token.soft and token.hard
