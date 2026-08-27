"""Табличные тесты чистых функций — мутационная проверка не требуется (CLAUDE.md)."""
from onecstarter.domain.server import (
    ServerConvention,
    ServerProfile,
    build_ragent_arguments,
    server_convention_for,
)
from onecstarter.domain.version import parse_version


def _profile(**overrides: object) -> ServerProfile:
    values: dict[str, str | int | bool] = {
        "id": "a" * 32,
        "name": "8.3.25 отладка",
        "version": "8.3.25",
        "port": 1540,
        "regport": 1541,
        "range_start": 1560,
        "range_end": 1591,
        "cluster_dir": r"E:\srv\srv_8.3.25.1633",
    }
    values.update(overrides)  # type: ignore[arg-type]
    return ServerProfile(**values)  # type: ignore[arg-type]


class TestBuildRagentArguments:
    def test_srv_sh_form_byte_exact(self) -> None:
        # [Ф] А1: форма снята со срабатывавших запусков сессии T-07.  # noqa: RUF003
        assert build_ragent_arguments(_profile()) == (
            r"-debug -http -port 1540 -regport 1541 -range 1560:1591 -d E:\srv\srv_8.3.25.1633"
        )

    def test_path_with_space_is_quoted(self) -> None:
        # [Ф] А1: путь с пробелом работает в стандартных Windows-кавычках.  # noqa: RUF003
        got = build_ragent_arguments(_profile(cluster_dir=r"E:\srv\with space"))
        assert got.endswith(r'-d "E:\srv\with space"')

    def test_flags_off_are_omitted(self) -> None:
        got = build_ragent_arguments(_profile(debug=False, http=False))
        assert got.startswith("-port 1540")

    def test_extra_args_go_last(self) -> None:
        got = build_ragent_arguments(_profile(extra_args="-seclev 1"))
        assert got.endswith("-seclev 1")

    def test_empty_extra_args_add_nothing(self) -> None:
        assert not build_ragent_arguments(_profile(extra_args="  ")).endswith(" ")


class TestServerConventionFor:
    def test_picks_best_min_version(self) -> None:
        old = ServerConvention(
            parse_version("8.2"),
            "bin",
            "ragent.exe",
            "radmin.dll",
            "common/1CV8 Servers (x86-64).msc",
        )
        assert server_convention_for(parse_version("8.3.25.1633"), [old]) is old

    def test_none_below_floor(self) -> None:
        conv = ServerConvention(
            parse_version("8.2"),
            "bin",
            "ragent.exe",
            "radmin.dll",
            "common/1CV8 Servers (x86-64).msc",
        )
        assert server_convention_for(parse_version("8.1"), [conv]) is None
