"""Каталог ключей командной строки: модель, целостность (спека v4, §3.5), поиск ключа (§4.1)."""

from typing import Any

import pytest

from onecstarter.domain.cli_catalog import (
    BOUND_SOURCES,
    ArgKind,
    CatalogError,
    Client,
    Effect,
    Mode,
    Reliability,
    load_catalog,
)
from onecstarter.domain.version import parse_version
from onecstarter.services.cli_catalog import load_cli_catalog


def _key(name: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "group": "g",
        "modes": ["enterprise"],
        "summary": "кратко",
        "description": "подробно",
        "its": "Приложение 7, 7.3",
        "reliability": "doc",
    }
    entry.update(overrides)
    return entry


def _payload(*keys: dict[str, Any]) -> dict[str, Any]:
    return {"group": [{"id": "g", "title": "Группа", "order": 10}], "key": list(keys)}


def test_loads_key_with_args_versions_and_flags() -> None:
    catalog = load_catalog(
        _payload(
            _key(
                "/Debug",
                clients=["thin", "thick"],
                versions={"since": "8.3.18"},
                args=[
                    {"kind": "enum", "values": ["-tcp", "-http"]},
                    {"kind": "flag", "flag": "-attach", "requires": "-http"},
                ],
            ),
            _key(
                "/L",
                reliability="fact",
                from_v8i=False,
                args=[{"kind": "string", "attached": True, "label": "код языка"}],
            ),
            _key("/IBName", managed=True, args=[{"kind": "string", "attached": True}]),
        )
    )
    debug = catalog.key("/debug")
    assert debug is not None
    assert debug.modes == frozenset({Mode.ENTERPRISE})
    assert debug.clients == frozenset({Client.THIN, Client.THICK})
    assert debug.since == parse_version("8.3.18") and debug.until is None
    assert debug.args[0].kind is ArgKind.ENUM and debug.args[0].values == ("-tcp", "-http")
    assert debug.args[1].requires == "-http"
    language = catalog.key("/L")
    assert language is not None and language.from_v8i is False
    assert language.reliability is Reliability.FACT and language.takes_attached
    ib_name = catalog.key("/IBName")
    assert ib_name is not None and ib_name.managed


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("/Lru", ("/L", "ru")),
        ("/lEN", ("/L", "EN")),
        ("/NoProxy", ("/NoProxy", "")),
        ('/N"tester"', ("/N", '"tester"')),
        ("/Nadmin", ("/N", "admin")),
        ("/Debug", ("/Debug", "")),
        ("/DebugX", None),
        ("/Foo", None),
        ("-attach", None),
    ],
)
def test_match_takes_longest_prefix_and_attached_only_where_allowed(
    word: str, expected: tuple[str, str] | None
) -> None:
    catalog = load_catalog(
        _payload(
            _key("/L", args=[{"kind": "string", "attached": True}]),
            _key("/N", args=[{"kind": "string", "attached": True}]),
            _key("/NoProxy"),
            _key("/Debug", args=[{"kind": "enum", "values": ["-tcp", "-http"]}]),
        )
    )
    found = catalog.match(word)
    if expected is None:
        assert found is None
    else:
        assert found is not None
        assert (found[0].name, found[1]) == expected


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        (_payload(_key("/A"), _key("/a")), "/a: имя повторяется"),
        (_payload(_key("A")), "A: имя ключа начинается с «/»"),  # noqa: RUF001
        (_payload(_key("/A", group="нет")), "/A: группы «нет» нет в каталоге"),
        (_payload(_key("/A", summary="")), "/A: не заполнено поле summary"),
        (_payload(_key("/A", its="")), "/A: не заполнено поле its"),
        (_payload(_key("/A", reliability="maybe")), "/A: неизвестное значение reliability"),
        (_payload(_key("/A", modes=[])), "/A: не задан ни один режим"),
        (_payload(_key("/A", modes=["web"])), "/A: неизвестное значение modes"),
        (
            _payload(_key("/A", args=[{"kind": "flag", "flag": "-x", "requires": "-y"}])),
            "/A: requires «-y» не ссылается на подпараметр этого ключа",
        ),
        (
            _payload(_key("/A", versions={"since": "8.5.4", "until": "8.3.18"})),
            "/A: since позже until",
        ),
        (_payload(_key("/A", versions={"since": "8.3.x"})), "/A: версия «8.3.x» не разбирается"),
        (
            _payload(_key("/A", args=[{"kind": "string"}, {"kind": "string", "attached": True}])),
            "/A: прижатым к ключу может быть только первый аргумент",
        ),
        (_payload(_key("/A", args=[{"kind": "enum"}])), "/A: у enum нет values"),  # noqa: RUF001
        (_payload(_key("/A", args=[{"kind": "flag"}])), "/A: у flag нет имени подпараметра"),  # noqa: RUF001
    ],
)
def test_integrity_violations_are_named(payload: dict[str, Any], fragment: str) -> None:
    with pytest.raises(CatalogError, match=fragment):
        load_catalog(payload)


def test_duplicate_group_id_is_rejected() -> None:
    payload = _payload(_key("/A"))
    payload["group"].append({"id": "g", "title": "Ещё", "order": 20})
    with pytest.raises(CatalogError, match="группа «g» объявлена дважды"):
        load_catalog(payload)


def test_group_keys_keep_file_order_and_groups_sort_by_order() -> None:
    payload = {
        "group": [
            {"id": "b", "title": "Вторая", "order": 20},
            {"id": "a", "title": "Первая", "order": 10},
        ],
        "key": [_key("/Z", group="a"), _key("/Y", group="a"), _key("/X", group="b")],
    }
    catalog = load_catalog(payload)
    assert [group.id for group in catalog.groups] == ["a", "b"]
    assert [key.name for key in catalog.group_keys("a")] == ["/Z", "/Y"]


def test_secret_key_is_marked() -> None:
    catalog = load_catalog(_payload(_key("/P", args=[{"kind": "secret", "attached": True}])))
    key = catalog.key("/P")
    assert key is not None and key.secret


EXPECTED_GROUPS = [
    "debug", "startup", "locale", "ui", "auth", "connection", "version", "config", "thick", "other",
]
COMMAND_GROUPS = ["backup", "maintenance", "repository", "external"]


def test_shipped_catalog_loads_and_has_all_groups() -> None:
    catalog = load_cli_catalog()
    assert [group.id for group in catalog.groups] == [*EXPECTED_GROUPS, *COMMAND_GROUPS]
    assert all(catalog.group_keys(group) for group in EXPECTED_GROUPS)
    assert not any(catalog.group_keys(group) for group in COMMAND_GROUPS)
    assert len(catalog.keys) >= 75


@pytest.mark.parametrize(
    "name",
    ["/F", "/S", "/IBName", "/IBConnectionString", "/WS"],
)
def test_connection_keys_are_managed(name: str) -> None:
    key = load_cli_catalog().key(name)
    assert key is not None and key.managed


@pytest.mark.parametrize(
    "name", ["/P", "/WSP", "/ModifyPassword", "/AccessToken", "/UC"]
)
def test_password_like_keys_are_secret(name: str) -> None:
    key = load_cli_catalog().key(name)
    assert key is not None and key.secret


def test_language_key_does_not_apply_from_v8i_and_is_measured() -> None:
    """[Ф] T-42 Э1: /L из AdditionalParameters не действует ни в одном режиме."""
    key = load_cli_catalog().key("/L")
    assert key is not None
    assert key.from_v8i is False
    assert key.reliability is Reliability.FACT
    assert key.modes == frozenset({Mode.ENTERPRISE, Mode.DESIGNER})


def test_only_language_key_is_marked_as_not_applied_from_v8i() -> None:
    assert [key.name for key in load_cli_catalog().keys if not key.from_v8i] == ["/L"]


def test_shipped_descriptions_do_not_repeat_summary() -> None:
    """Описание — не копия краткой строки: конструктор показывает оба."""  # noqa: RUF002
    for key in load_cli_catalog().keys:
        assert key.description.strip() != key.summary.strip(), key.name


def test_every_shipped_key_has_since() -> None:
    """Спека §3.4: диапазон версий у каждой записи; источник — build/catalog_versions.py."""  # noqa: RUF002
    missing = [key.name for key in load_cli_catalog().keys if key.since is None]
    assert missing == []


_GROUP = {"id": "backup", "title": "Резерв и конфигурация", "order": 110}


def _command(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": "/DumpIB",
        "group": "backup",
        "effect": "none",
        "exclusive": True,
        "summary": "выгрузить базу",
        "description": "Выгружает базу в файл.",
        "its": "Приложение 7, 7.4.2",
        "reliability": "fact",
        "args": [{"kind": "file", "role": "output", "ext": ".dt", "required": True}],
    }
    entry.update(changes)
    return entry


def test_command_is_loaded_with_effect_and_file_role() -> None:
    catalog = load_catalog({"group": [_GROUP], "command": [_command()]})
    command = catalog.command("/dumpib")
    assert command is not None
    assert command.effect is Effect.NONE
    assert command.exclusive is True
    assert command.args[0].role == "output"
    assert command.args[0].ext == ".dt"
    assert catalog.group_commands("backup") == (command,)
    assert catalog.keys == ()


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"effect": "wipes"}, "effect"),
        ({"exclusive": None}, "exclusive"),
        ({"group": "nope"}, "группы"),
        ({"summary": ""}, "summary"),
        ({"args": [{"kind": "file", "role": "sideways"}]}, "role"),
        ({"args": [{"kind": "bound", "source": "repository.token"}]}, "source"),
        ({"args": [{"kind": "bound"}]}, "source"),
        ({"args": [{"kind": "string", "source": "repository.user"}]}, "source"),
        ({"args": [{"kind": "secret", "flag": "-P"}]}, "secret"),
        (
            {"args": [{"kind": "flag", "flag": "-force", "requires": "-update"}]},
            "requires «-update» не ссылается",
        ),
    ],
)
def test_command_integrity_violations(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(CatalogError, match=fragment):
        load_catalog({"group": [_GROUP], "command": [_command(**changes)]})


def test_command_requires_may_name_a_flag_or_an_enum_value() -> None:
    args = [
        {"kind": "flag", "flag": "-update"},
        {"kind": "flag", "flag": "-force", "requires": "-update"},
        {"kind": "enum", "flag": "-Mode", "values": ["Fast", "Full"]},
        {"kind": "int", "flag": "-Jobs", "requires": "Full"},
    ]
    command = load_catalog({"group": [_GROUP], "command": [_command(args=args)]}).command(
        "/DumpIB"
    )
    assert command is not None
    assert [arg.requires for arg in command.args] == [None, "-update", None, "Full"]


def test_command_without_effect_is_rejected() -> None:
    entry = _command()
    del entry["effect"]
    with pytest.raises(CatalogError, match="effect"):
        load_catalog({"group": [_GROUP], "command": [entry]})


def test_command_names_are_unique_ignoring_case() -> None:
    with pytest.raises(CatalogError, match="повторяется"):
        load_catalog({"group": [_GROUP], "command": [_command(), _command(name="/DUMPIB")]})


def test_bound_argument_marks_command() -> None:
    bound = [{"kind": "bound", "source": source} for source in sorted(BOUND_SOURCES)]
    catalog = load_catalog(
        {"group": [_GROUP], "command": [_command(name="/ConfigurationRepositoryLock", args=bound)]}
    )
    command = catalog.command("/ConfigurationRepositoryLock")
    assert command is not None and command.bound
    assert all(arg.kind is ArgKind.BOUND for arg in command.args)


_REPLACES = {
    "/RestoreIB", "/LoadCfg", "/LoadConfigFromFiles", "/UpdateCfg", "/MergeCfg",
    "/RollbackCfg", "/DeleteCfg",
}
_MODIFIES = {
    "/UpdateDBCfg", "/IBCheckAndRepair", "/IBRestoreIntegrity", "/ReduceEventLogSize",
    "/ConfigurationRepositoryUpdateCfg", "/ConfigurationRepositoryCommit",
    "/ConfigurationRepositoryBindCfg", "/ConfigurationRepositoryUnbindCfg",
}
_COMMANDS = {
    "backup": {
        "/DumpIB", "/RestoreIB", "/DumpCfg", "/LoadCfg", "/DumpDBCfg", "/UpdateDBCfg",
        "/RollbackCfg", "/UpdateCfg", "/MergeCfg", "/CompareCfg", "/DumpConfigToFiles",
        "/LoadConfigFromFiles", "/DumpDBCfgList", "/DeleteCfg",
    },
    "maintenance": {
        "/IBCheckAndRepair", "/IBRestoreIntegrity", "/ReduceEventLogSize", "/CheckConfig",
        "/CheckModules", "/CheckCanApplyConfigurationExtensions",
    },
    "repository": {
        "/ConfigurationRepository" + tail
        for tail in (
            "UpdateCfg", "Commit", "Lock", "UnLock", "Report", "DumpCfg", "BindCfg",
            "UnbindCfg", "SetLabel", "ClearCache", "ClearLocalCache", "ClearGlobalCache",
            "OptimizeData",
        )
    },
    "external": {
        "/DumpExternalDataProcessorOrReportToFiles",
        "/LoadExternalDataProcessorOrReportFromFiles",
    },
}


def test_shipped_catalog_has_exactly_the_designer_commands() -> None:
    catalog = load_cli_catalog()
    for group, names in _COMMANDS.items():
        assert {command.name for command in catalog.group_commands(group)} == names
    assert len(catalog.commands) == 35


def test_shipped_command_effects_match_the_spec() -> None:
    catalog = load_cli_catalog()
    for command in catalog.commands:
        expected = (
            Effect.REPLACES if command.name in _REPLACES
            else Effect.MODIFIES if command.name in _MODIFIES
            else Effect.NONE
        )
        assert command.effect is expected, command.name


def test_repository_commands_are_bound_and_others_are_not() -> None:
    catalog = load_cli_catalog()
    for command in catalog.commands:
        assert command.bound is (command.group == "repository"), command.name
        if command.bound:
            sources = [arg.source for arg in command.args if arg.kind is ArgKind.BOUND]
            assert sources == ["repository.address", "repository.user", "repository.password"]


def test_shipped_command_arguments_are_labelled_and_files_have_roles() -> None:
    for command in load_cli_catalog().commands:
        for arg in command.args:
            if arg.kind is ArgKind.BOUND:
                continue
            assert arg.label, command.name
            if arg.kind in (ArgKind.FILE, ArgKind.DIR):
                assert arg.role in ("input", "output"), command.name


def test_dump_and_restore_take_one_required_dt_file() -> None:
    catalog = load_cli_catalog()
    dump, restore = catalog.command("/DumpIB"), catalog.command("/RestoreIB")
    assert dump is not None and restore is not None
    assert (dump.args[0].role, dump.args[0].ext, dump.args[0].required) == ("output", ".dt", True)
    assert (restore.args[0].role, restore.args[0].required) == ("input", True)
    assert dump.exclusive and restore.exclusive


def test_every_shipped_command_has_a_since_version() -> None:
    assert all(command.since is not None for command in load_cli_catalog().commands)


def test_only_dump_ib_is_measured_fact() -> None:
    facts = {c.name for c in load_cli_catalog().commands if c.reliability is Reliability.FACT}
    assert facts == {"/DumpIB"}
