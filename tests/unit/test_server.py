"""Табличные тесты чистых функций — мутационная проверка не требуется (CLAUDE.md)."""
from typing import ClassVar

import pytest

from onecstarter.domain.server import (
    ServerConvention,
    ServerProfile,
    build_ragent_arguments,
    resolve_server_version,
    server_convention_for,
    validate_profile,
    warn_range_overlap,
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


class TestResolveServerVersion:
    INSTALLED: ClassVar = [parse_version(v) for v in ("8.3.25.1560", "8.3.25.1633", "8.3.27.2214")]

    @pytest.mark.parametrize(
        ("requested", "expected"),
        [
            ("8.3.25.1560", "8.3.25.1560"),  # точная — ровно она
            (
                "8.3.25",
                "8.3.25.1633",
            ),  # маска — максимум с префиксом ([Ф] T-02.1)  # noqa: RUF003
            ("8.3", "8.3.27.2214"),
            ("8.3.25.1700", None),  # точной нет — None, без тихого фолбэка
            ("8.5", None),
            ("мусор", None),  # неразборчивое — None, валидация ловит отдельно
        ],
    )
    def test_table(self, requested: str, expected: str | None) -> None:
        got = resolve_server_version(requested, self.INSTALLED)
        assert (str(got) if got else None) == expected


class TestValidateProfile:
    def test_valid_profile_has_no_errors(self) -> None:
        assert validate_profile(_profile(), []) == []

    @pytest.mark.parametrize(
        ("overrides", "fragment"),
        [
            ({"name": "  "}, "имя"),
            ({"version": "не версия"}, "версия"),
            ({"port": 0}, "порт"),
            ({"regport": 70000}, "порт"),
            ({"range_start": 1591, "range_end": 1560}, "диапазон"),
            ({"port": 1541}, "порт"),  # port == regport
            ({"cluster_dir": " "}, "каталог"),
        ],
    )
    def test_bad_fields(self, overrides: dict[str, object], fragment: str) -> None:
        errors = validate_profile(_profile(**overrides), [])
        assert errors and fragment in errors[0].casefold()

    def test_port_clash_with_other_profile(self) -> None:
        other = _profile(
            id="b" * 32,
            name="сосед",
            regport=2541,
            range_start=2560,
            range_end=2591,
            cluster_dir=r"E:\srv\other",
        )
        errors = validate_profile(_profile(), [other])  # port 1540 у обоих  # noqa: RUF003
        assert any("1540" in error for error in errors)

    def test_cluster_dir_clash_is_case_insensitive(self) -> None:
        other = _profile(
            id="b" * 32,
            port=2540,
            regport=2541,
            cluster_dir=r"e:/SRV/srv_8.3.25.1633/",
        )
        errors = validate_profile(_profile(), [other])
        assert any("каталог" in error.casefold() for error in errors)


class TestWarnRangeOverlap:
    def test_overlap_is_warning_not_error(self) -> None:
        # [Ф] А5: пересечение диапазонов безвредно — предупреждение, не отказ.  # noqa: RUF003
        other = _profile(
            id="b" * 32,
            port=2540,
            regport=2541,
            range_start=1580,
            range_end=1611,
            cluster_dir=r"E:\srv\other",
        )
        assert validate_profile(_profile(), [other]) == []
        assert warn_range_overlap(_profile(), [other]) != []

    def test_no_overlap_no_warning(self) -> None:
        other = _profile(
            id="b" * 32,
            port=2540,
            regport=2541,
            range_start=2560,
            range_end=2591,
            cluster_dir=r"E:\srv\other",
        )
        assert warn_range_overlap(_profile(), [other]) == []
