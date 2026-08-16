# tests/unit/test_services_launch.py
from pathlib import Path

import pytest

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.launch import ClientConvention, ClientKind, LaunchCommand
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.security.secrets import redact_connect
from onecstarter.services.launch import LaunchError, LaunchKind, launch_infobase
from onecstarter.services.model import InfobaseItem, InfobaseSource, item_from_section

CONVENTIONS = [
    ClientConvention(
        min_version=parse_version("8.2"),
        bin_dir="bin",
        executables={
            ClientKind.THIN: "1cv8c.exe",
            ClientKind.THICK: "1cv8.exe",
            ClientKind.DESIGNER: "1cv8.exe",
        },
    )
]
INSTALLED = [
    Installation(parse_version("8.3.25.1633"), Path(r"C:\Program Files\1cv8\8.3.25.1633"), Arch.X64)
]


def _item(raw: str) -> InfobaseItem:
    return item_from_section(parse_v8i(raw.encode()).sections[0], InfobaseSource.USER)


def test_redact_connect_hides_values_not_names() -> None:
    redacted = redact_connect('Srvr="srv-1c";Ref="acc";DBPwd=тайна;Usr=Иванов;')
    assert "тайна" not in redacted
    assert "DBPwd=***" in redacted
    assert "Usr=Иванов" in redacted


def test_redact_connect_hides_value_with_escaped_quote() -> None:
    # parse_connect снимает кавычки и разэкранирует "" -> "; замена по совпадению
    # исходной подстроки не находит распакованное значение — регресс-тест на это.  # noqa: RUF003
    redacted = redact_connect('Srvr="s";Ref="r";Pwd="sec""ret";')
    assert 'sec""ret' not in redacted
    assert 'sec"ret' not in redacted
    assert "secret" not in redacted


def test_redact_connect_does_not_hide_matching_non_secret_value() -> None:
    # Секретный и обычный ключ с одинаковым значением: затираться должен только  # noqa: RUF003
    # секретный — замена по значению стирает оба, это и есть регресс-тест.  # noqa: RUF003
    redacted = redact_connect('Srvr="s";Usr="x";Pwd="x";')
    assert "Pwd=***" in redacted
    assert "Usr=x" in redacted


def test_redact_connect_keeps_non_secret_fragments() -> None:
    redacted = redact_connect('Srvr="s";Ref="r";Pwd="secret";')
    assert 'Srvr=s' in redacted
    assert 'Ref=r' in redacted


def test_redact_connect_without_fragments_returned_as_is() -> None:
    assert redact_connect("") == ""


def test_redact_connect_hides_string_without_fragments() -> None:
    # Замерено до правки: `Pwd"hunter2"` возвращался целиком — ни одного
    # фрагмента с «=» не вышло, и функция отдавала исходную строку.  # noqa: RUF003
    redacted = redact_connect('Pwd"hunter2"')
    assert "hunter2" not in redacted


def test_redact_connect_hides_string_with_unpaired_quote() -> None:
    # Замерено до правки: 'Usr="a"";Pwd="secret";' -> 'Usr="a"";Pwd="secret";;'.
    # Непарная кавычка склеила хвост строки в значение несекретного Usr.
    redacted = redact_connect('Usr="a"";Pwd="secret";')
    assert "secret" not in redacted


def test_redact_connect_hides_secret_swallowed_by_neighbour_value() -> None:
    # Замерено до правки: 'Srvr="s;Pwd="hunter2";' -> 'Srvr="s;Pwd="hunter2";;'.
    # Кавычки парные, но границы фрагментов разъехались, и пароль оказался
    # внутри значения Srvr.
    redacted = redact_connect('Srvr="s;Pwd="hunter2";')
    assert "hunter2" not in redacted


def test_redact_connect_hides_secret_hidden_in_quoted_value() -> None:
    redacted = redact_connect('Ref="r;Pwd=x"')
    assert "Pwd=x" not in redacted


@pytest.mark.parametrize("name", ["Pwd ", " Pwd", "Pwd\t", "\tDBPwd "])
def test_redact_connect_hides_secret_key_with_whitespace(name: str) -> None:
    # Замерено до правки: 'Srvr="s";Ref="r";Pwd ="hunter2";' ->
    # 'Srvr=s;Ref=r;Pwd =hunter2;'. Имя `Pwd ` с пробелом секретом  # noqa: RUF003
    # не считалось, и пароль уходил в текст ошибки дословно.
    redacted = redact_connect(f'Srvr="s";Ref="r";{name}="hunter2";')
    assert "hunter2" not in redacted
    assert "***" in redacted


def test_launch_spawns_thin_client_by_ibname() -> None:
    calls: list[LaunchCommand] = []
    outcome = launch_infobase(
        _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        spawn=lambda command: (calls.append(command), 4242)[1],  # type: ignore[func-returns-value]
        open_url=lambda url: pytest.fail("браузер не должен открываться"),
    )
    assert outcome.kind is LaunchKind.PROCESS
    assert outcome.pid == 4242
    assert outcome.client is ClientKind.THIN
    assert calls[0].executable.name == "1cv8c.exe"
    assert '/IBName"Демо"' in calls[0].arguments
    assert "/AppAutoCheckVersion-" in calls[0].arguments


def test_forced_designer_uses_thick_executable() -> None:
    calls: list[LaunchCommand] = []
    launch_infobase(
        _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        forced_client=ClientKind.DESIGNER,
        spawn=lambda command: (calls.append(command), 1)[1],  # type: ignore[func-returns-value]
        open_url=lambda url: pytest.fail("браузер не должен открываться"),
    )
    assert calls[0].arguments.startswith("DESIGNER ")
    assert calls[0].executable.name == "1cv8.exe"


def test_web_base_opens_browser() -> None:
    opened: list[str] = []
    outcome = launch_infobase(
        _item('[Портал]\r\nConnect=ws="http://web-server/resource/";\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app=None,
        spawn=lambda command: pytest.fail("процесс не должен порождаться"),
        open_url=lambda url: opened.append(url) or True,  # type: ignore[func-returns-value]
    )
    assert outcome.kind is LaunchKind.BROWSER
    assert opened == ["http://web-server/resource/"]


def test_not_installed_version_fails_before_spawn() -> None:
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.99.1\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "8.3.99.1" in str(error.value)


def test_group_cannot_be_launched() -> None:
    with pytest.raises(LaunchError):
        launch_infobase(
            _item("[Клиенты]\r\nFolder=/\r\n"),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )


def test_web_app_on_file_base_is_refused_with_launch_error() -> None:
    # Замерено до правки: голый ValueError из domain.launch._client_from_app.
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\nApp=WebClient\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "WebClient" in str(error.value)


def test_web_default_app_is_refused_with_launch_error() -> None:
    # Замерено до правки: default_app="WebClient" ронял ValueError на базе,
    # у которой App вообще не задан.  # noqa: RUF003
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app="WebClient",
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "умолчанием машины" in str(error.value)


def test_explicit_client_wins_over_web_default_app() -> None:
    """`App=ThinClient` при `default_app="WebClient"` — рабочий случай:
    `choose_client` до умолчания не доходит, и отказывать здесь нельзя.
    """
    calls: list[LaunchCommand] = []
    launch_infobase(
        _item('[Демо]\r\nConnect=File="C:\\B";\r\nVersion=8.3.25\r\nApp=ThinClient\r\n'),
        installations=INSTALLED,
        cfg_rules=[],
        conventions=CONVENTIONS,
        default_app="WebClient",
        spawn=lambda command: (calls.append(command), 1)[1],  # type: ignore[func-returns-value]
        open_url=lambda url: pytest.fail("браузер не должен открываться"),
    )
    assert calls[0].executable.name == "1cv8c.exe"


def test_web_base_reports_failed_browser() -> None:
    # webbrowser.open вернул False — база не открылась, и в историю запусков
    # она попасть не должна.
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Портал]\r\nConnect=ws="http://web-server/resource/";\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: False,
        )
    assert "http://web-server" not in str(error.value)


def test_error_message_hides_secret_value_behind_spaced_key() -> None:
    # Сквозная проверка: пароль под именем ключа с пробелом не должен  # noqa: RUF003
    # доходить до текста LaunchError.
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Тайная]\r\nConnect=Srvr="s";Pwd ="hunter2";\r\nVersion=8.3.99.1\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "hunter2" not in str(error.value)


def test_error_message_hides_secret_values() -> None:
    with pytest.raises(LaunchError) as error:
        launch_infobase(
            _item('[Тайная]\r\nConnect=Srvr="s";Ref="r";DBPwd=тайна;\r\nVersion=8.3.99.1\r\n'),
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=lambda command: pytest.fail("процесс не должен порождаться"),
            open_url=lambda url: pytest.fail("браузер не должен открываться"),
        )
    assert "тайна" not in str(error.value)


def test_spawn_failure_becomes_launch_error_with_command_line() -> None:
    # Спека 4a, §3: ошибка запуска — сообщение с фактической командной  # noqa: RUF003
    # строкой, а не трассировка OSError.  # noqa: RUF003
    item = _item('[Демо]\r\nConnect=File="C:\\Bases\\Demo";\r\nVersion=8.3.25\r\n')

    def failing_spawn(command: LaunchCommand) -> int:
        raise OSError("описание отказа системы")

    with pytest.raises(LaunchError) as excinfo:
        launch_infobase(
            item,
            installations=INSTALLED,
            cfg_rules=[],
            conventions=CONVENTIONS,
            default_app=None,
            spawn=failing_spawn,
            open_url=lambda url: True,
        )
    message = str(excinfo.value)
    assert "1cv8c.exe" in message
    assert "/IBName" in message
