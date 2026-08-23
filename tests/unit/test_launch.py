from pathlib import Path

import pytest

from onecstarter.domain.launch import (
    ClientChoice,
    ClientConvention,
    ClientKind,
    LaunchCommand,
    build_arguments,
    build_launch_command,
    choose_client,
    convention_for,
    quote_launch_value,
)
from onecstarter.domain.version import Arch, Installation, parse_version

CONVENTION_8_2 = ClientConvention(
    min_version=parse_version("8.2"),
    bin_dir="bin",
    executables={
        ClientKind.THIN: "1cv8c.exe",
        ClientKind.THICK: "1cv8.exe",
        ClientKind.DESIGNER: "1cv8.exe",
    },
)


class TestChooseClient:
    def test_auto_defaults_to_thin_with_check_mode(self) -> None:
        # [Ф] штатный при App=Auto: 1cv8c.exe ... /AppAutoCheckMode
        assert choose_client(None, None) == ClientChoice(ClientKind.THIN, auto_check_mode=True)
        assert choose_client("Auto", None) == ClientChoice(ClientKind.THIN, auto_check_mode=True)

    def test_auto_uses_default_app(self) -> None:
        choice = choose_client("Auto", "ThickClient")
        assert choice == ClientChoice(ClientKind.THICK, auto_check_mode=True)

    def test_explicit_app_disables_check_mode(self) -> None:
        # [Ф] T-02.6: при явном App стартер не передаёт /AppAutoCheckMode.
        assert choose_client("ThinClient", None) == ClientChoice(
            ClientKind.THIN, auto_check_mode=False
        )
        assert choose_client("thickclient", None) == ClientChoice(
            ClientKind.THICK, auto_check_mode=False
        )

    def test_forced_client_wins(self) -> None:
        choice = choose_client("ThinClient", None, forced=ClientKind.DESIGNER)
        assert choice == ClientChoice(ClientKind.DESIGNER, auto_check_mode=False)

    def test_web_client_is_not_an_executable(self) -> None:
        with pytest.raises(ValueError, match="браузером"):
            choose_client("WebClient", None)

    def test_unknown_app_value_behaves_like_auto(self) -> None:
        choice = choose_client("НечтоНовое", None)
        assert choice == ClientChoice(ClientKind.THIN, auto_check_mode=True)


@pytest.mark.parametrize(
    ("app", "default_app", "forced", "expected", "auto_mode"),
    [
        # настройка работает только при пустом App
        (None, "ThickClient", None, ClientKind.THICK, True),
        (None, "ThinClient", None, ClientKind.THIN, True),
        # App записи бьёт настройку
        ("ThinClient", "ThickClient", None, ClientKind.THIN, False),
        ("ThickClient", "ThinClient", None, ClientKind.THICK, False),
        # принудительный выбор бьёт всё
        ("ThinClient", "ThickClient", ClientKind.DESIGNER, ClientKind.DESIGNER, False),
        (None, "ThickClient", ClientKind.THIN, ClientKind.THIN, False),
    ],
)
def test_priority_table(
    app: str | None,
    default_app: str | None,
    forced: ClientKind | None,
    expected: ClientKind,
    auto_mode: bool,
) -> None:
    """Спека вехи §2.2: принудительный выбор → App записи → настройка."""
    assert choose_client(app, default_app, forced) == ClientChoice(
        expected, auto_check_mode=auto_mode
    )


class TestBuildArguments:
    def test_matches_starter_snapshot_for_auto(self) -> None:
        # [Ф] снято с реального процесса:  # noqa: RUF003
        # 1cv8c.exe ENTERPRISE /IBName"empty" /AppAutoCheckVersion /AppAutoCheckMode
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=True, auto_check_mode=True
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /AppAutoCheckVersion /AppAutoCheckMode'

    def test_matches_starter_snapshot_for_explicit_app(self) -> None:
        # [Ф] T-02.6: ENTERPRISE /IBName"..." /AppAutoCheckVersion
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=True, auto_check_mode=False
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /AppAutoCheckVersion'

    def test_self_resolved_version_disables_auto_check(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=False, auto_check_mode=True
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /AppAutoCheckVersion- /AppAutoCheckMode'

    def test_designer_mode_is_first_argument(self) -> None:
        arguments = build_arguments(
            ClientKind.DESIGNER, ib_name="empty", auto_check_version=False, auto_check_mode=False
        )
        assert arguments == 'DESIGNER /IBName"empty" /AppAutoCheckVersion-'

    def test_quotes_in_name_are_doubled(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN,
            ib_name='База "СтройТорг"',
            auto_check_version=False,
            auto_check_mode=False,
        )
        assert '/IBName"База ""СтройТорг"""' in arguments

    def test_connect_route(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN,
            connect='File="C:\\Bases\\Demo";',
            auto_check_version=False,
            auto_check_mode=True,
        )
        assert arguments == (
            'ENTERPRISE /IBConnectionString"File=""C:\\Bases\\Demo"";"'
            " /AppAutoCheckVersion- /AppAutoCheckMode"
        )

    def test_pwd_in_connect_string_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Pwd"):
            build_arguments(
                ClientKind.THIN,
                connect='File="C:\\B";Pwd="secret";',
                auto_check_version=True,
                auto_check_mode=False,
            )

    @pytest.mark.parametrize(
        "fragment",
        [
            "DBPwd=secret",  # пароль пользователя СУБД
            "SPwd=secret",  # пароль администратора кластера
            "wsp=secret",  # пароль пользователя веб-сервера
            "wsppwd=secret",  # пароль прокси
            "dbpwd=secret",  # регистр имени ключа значения не имеет
        ],
    )
    def test_every_password_fragment_is_rejected(self, fragment: str) -> None:
        with pytest.raises(ValueError) as error:
            build_arguments(
                ClientKind.THIN,
                connect=f'Srvr="srv";Ref="base";{fragment};',
                auto_check_version=True,
                auto_check_mode=False,
            )
        assert "secret" not in str(error.value)

    @pytest.mark.parametrize("name", ["Pwd ", " Pwd", "Pwd\t", "\tDBPwd "])
    def test_password_key_with_whitespace_is_rejected(self, name: str) -> None:
        # Пробелы вокруг «=» — реальная порча пользовательских файлов
        # (скил v8i-format, факт 6). Имя ключа обрезается перед сверкой,
        # иначе `Pwd ` уезжает в командную строку как обычный фрагмент.
        with pytest.raises(ValueError) as error:
            build_arguments(
                ClientKind.THIN,
                connect=f'Srvr="srv";Ref="base";{name}="secret";',
                auto_check_version=True,
                auto_check_mode=False,
            )
        assert "secret" not in str(error.value)

    def test_unknown_password_key_is_rejected_too(self) -> None:
        # Список ключей платформы не закрыт: любое имя на «pwd» считаем секретом.
        with pytest.raises(ValueError, match="NewPwd"):
            build_arguments(
                ClientKind.THIN,
                connect='Srvr="srv";Ref="base";NewPwd=secret;',
                auto_check_version=True,
                auto_check_mode=False,
            )

    def test_unpaired_quote_is_rejected_even_when_the_secret_name_is_swallowed(self) -> None:
        """Круг правок 2, item 1: паритетный страж не зависит от разбора.

        `Srvr=x";Pwd=secret;` — непарная кавычка склеивает `Pwd=secret` в
        значение фрагмента `Srvr` целиком: даже с восстановленным (после
        круга правок 2) безусловным сбросом хвоста `parse_connect` находит
        только один фрагмент, `Srvr`, — «Pwd» не выделяется отдельным именем
        вовсе (его «=» не первый в захваченном чанке). Сканирование имён на
        секреты здесь бессильно в принципе — защиту даёт только чётность
        числа кавычек, тот же страж, что уже стоит в `redact_connect`.
        """  # noqa: RUF002
        with pytest.raises(ValueError) as error:
            build_arguments(
                ClientKind.THIN,
                connect='Srvr=x";Pwd=secret;',
                auto_check_version=True,
                auto_check_mode=False,
            )
        assert "secret" not in str(error.value)

    def test_unpaired_quote_is_rejected_even_when_the_secret_name_is_found(self) -> None:
        """Пример из ревью: здесь секрет находится и по имени тоже (после item 1),

        но непарная кавычка сама по себе уже достаточное основание для отказа —
        не передаём connect с непарной кавычкой через командную строку.
        """  # noqa: RUF002
        with pytest.raises(ValueError):
            build_arguments(
                ClientKind.THIN,
                connect='File="D:\\b";Pwd=p";',
                auto_check_version=True,
                auto_check_mode=False,
            )

    def test_non_secret_neighbours_pass(self) -> None:
        # wsp — секрет, но wspuser/wspsrv/wspport/DBUID — нет: сверка по полному имени.
        arguments = build_arguments(
            ClientKind.THIN,
            connect='Srvr="srv";Ref="base";DBUID=sa;wspuser=proxy;wspsrv=p;wspport=8080;',
            auto_check_version=True,
            auto_check_mode=False,
        )
        assert arguments.startswith("ENTERPRISE /IBConnectionString")

    def test_exactly_one_target_required(self) -> None:
        with pytest.raises(ValueError, match="ровно одно"):
            build_arguments(
                ClientKind.THIN, auto_check_version=True, auto_check_mode=True
            )
        with pytest.raises(ValueError, match="ровно одно"):
            build_arguments(
                ClientKind.THIN,
                ib_name="empty",
                connect='File="C:\\B";',
                auto_check_version=True,
                auto_check_mode=True,
            )


def test_quote_launch_value() -> None:
    assert quote_launch_value("empty") == '"empty"'
    assert quote_launch_value('a"b') == '"a""b"'


def test_convention_for_picks_highest_applicable() -> None:
    newer = ClientConvention(
        min_version=parse_version("8.5"),
        bin_dir="bin",
        executables={ClientKind.THIN: "newclient.exe"},
    )
    conventions = [CONVENTION_8_2, newer]
    assert convention_for(parse_version("8.3.25.1633"), conventions) is CONVENTION_8_2
    assert convention_for(parse_version("8.5.4.100"), conventions) is newer
    assert convention_for(parse_version("8.1.5.100"), conventions) is None


def test_build_launch_command_composes_path() -> None:
    installation = Installation(
        version=parse_version("8.3.25.1633"),
        path=Path("C:/Program Files/1cv8/8.3.25.1633"),
        arch=Arch.X64,
    )
    command = build_launch_command(installation, CONVENTION_8_2, ClientKind.THIN, "ENTERPRISE")
    assert command == LaunchCommand(
        executable=Path("C:/Program Files/1cv8/8.3.25.1633/bin/1cv8c.exe"),
        arguments="ENTERPRISE",
    )
    assert command.command_line == (
        '"C:\\Program Files\\1cv8\\8.3.25.1633\\bin\\1cv8c.exe" ENTERPRISE'
    )
