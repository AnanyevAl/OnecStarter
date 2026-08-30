from pathlib import Path

import pytest

from onecstarter.domain.server import ServerProfile
from onecstarter.domain.server_match import (
    RagentProcess,
    extract_ragent_params,
    match_profiles,
    normalize_cluster_dir,
    port_holders,
    port_holders_text,
    version_from_exe_path,
)


class TestNormalizeClusterDir:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (r"E:\tmp\t07\srv1", r"e:\tmp\t07\srv1"),
            (
                "E:/tmp/t07/srv1",
                r"e:\tmp\t07\srv1",
            ),  # слэши в argv
            (
                r"e:\tmp\t07\srv1" + "\\",
                r"e:\tmp\t07\srv1",
            ),  # [Ф] rmngr дописывает хвост
            (
                '"e:\\tmp\\srv with space\\\\"',
                r"e:\tmp\srv with space",
            ),  # [Ф] А1: кавычки + слэш  # noqa: RUF003
            (r"E:\\tmp\\\\t07", r"e:\tmp\t07"),  # повторные разделители
            (r"E:\Tmp\T07\SRV1", r"e:\tmp\t07\srv1"),  # NTFS регистронезависима
        ],
    )
    def test_table(self, raw: str, expected: str) -> None:
        assert normalize_cluster_dir(raw) == expected


class TestExtractRagentParams:
    ARGV = (
        "ragent.exe",
        "-debug",
        "-http",
        "-port",
        "2540",
        "-regport",
        "2541",
        "-range",
        "2560:2591",
        "-d",
        r"e:\tmp\t07\srv1",
    )

    def test_full_argv(self) -> None:
        params = extract_ragent_params(self.ARGV)
        assert (params.port, params.regport, params.range_text) == (2540, 2541, "2560:2591")
        assert params.cluster_dir == r"e:\tmp\t07\srv1"

    def test_key_names_are_case_insensitive(self) -> None:
        # [Ф] А1: ключи case-insensitive  # noqa: RUF003
        argv = ("ragent.exe", "-PORT", "2540", "-D", r"e:\srv")
        params = extract_ragent_params(argv)
        assert params.port == 2540 and params.cluster_dir == r"e:\srv"

    def test_missing_keys_give_none(self) -> None:
        params = extract_ragent_params(("ragent.exe", "-debug"))
        assert params.port is None and params.cluster_dir is None

    def test_non_numeric_port_is_none(self) -> None:
        assert extract_ragent_params(("ragent.exe", "-port", "хлам")).port is None

    def test_value_eaten_by_next_key_is_none(self) -> None:
        # -d без значения перед следующим ключом: значение не выдумывается.
        assert extract_ragent_params(("ragent.exe", "-d", "-port", "2540")).cluster_dir is None


class TestVersionFromExePath:
    def test_standard_layout(self) -> None:
        path = Path(r"C:\Program Files\1cv8\8.3.25.1633\bin\ragent.exe")
        assert str(version_from_exe_path(path)) == "8.3.25.1633"

    def test_alien_layout_is_none(self) -> None:
        assert version_from_exe_path(Path(r"C:\tools\ragent.exe")) is None


def _profile(
    profile_id: str = "profile1",
    name: str = "Test Server",
    version: str = "8.3.25.1633",
    port: int = 1540,
    regport: int = 1541,
    range_start: int = 1560,
    range_end: int = 1591,
    cluster_dir: str = r"E:\srv\srv_8.3.25.1633",
) -> ServerProfile:
    return ServerProfile(
        id=profile_id,
        name=name,
        version=version,
        port=port,
        regport=regport,
        range_start=range_start,
        range_end=range_end,
        cluster_dir=cluster_dir,
    )


def _proc(
    pid: int,
    cluster: str | None,
    *,
    exe: str | None = r"C:\Program Files\1cv8\8.3.25.1633\bin\ragent.exe",
) -> RagentProcess:
    argv = None if cluster is None else ("ragent.exe", "-port", "2540", "-d", cluster)
    return RagentProcess(
        pid=pid, executable=Path(exe) if exe else None, argv=argv, create_time=100.0 + pid
    )


class TestMatchProfiles:
    def test_match_by_normalized_dir(self) -> None:
        profile = _profile()  # cluster_dir=E:\srv\srv_8.3.25.1633
        result = match_profiles([profile], [_proc(1, "e:/SRV/srv_8.3.25.1633/")])
        assert [p.pid for p in result.by_profile[profile.id]] == [1]
        assert result.foreign == ()

    def test_unmatched_goes_foreign_with_version(self) -> None:
        result = match_profiles([_profile()], [_proc(2, r"D:\clusters\prod")])
        assert result.by_profile[_profile().id] == ()
        foreign = result.foreign[0]
        assert str(foreign.version) == "8.3.25.1633" and foreign.params is not None

    def test_opaque_process_is_always_foreign(self) -> None:
        # [Ф] В1: argv чужих процессов не виден  # noqa: RUF003
        # сопоставление невозможно в принципе
        result = match_profiles([_profile()], [_proc(3, None, exe=None)])
        foreign = result.foreign[0]
        assert foreign.params is None and foreign.version is None

    def test_two_processes_on_one_dir_both_match(self) -> None:
        procs = [_proc(1, r"E:\srv\srv_8.3.25.1633"), _proc(2, r"e:\srv\srv_8.3.25.1633\\")]
        result = match_profiles([_profile()], procs)
        assert len(result.by_profile[_profile().id]) == 2


def _holder(pid: int, name: str, *args: str) -> RagentProcess:
    return RagentProcess(
        pid=pid, executable=None, argv=(name, *args), create_time=100.0 + pid
    )


class TestPortHolders:
    PROFILE = _profile(port=1540, regport=1541, cluster_dir=r"E:\srv\a")

    @pytest.mark.parametrize(
        ("process", "expected"),
        [
            (
                _holder(1, "rmngr.exe", "-port", "1541"),
                True,
            ),  # [Ф] А3: rmngr на нашем regport  # noqa: RUF003
            (_holder(2, "ragent.exe", "-port", "1540", "-regport", "9541", "-d", r"D:\x"), True),
            (_holder(3, "ragent.exe", "-port", "9540", "-regport", "1541", "-d", r"D:\x"), True),
            (_holder(4, "rmngr.exe", "-port", "2541"), False),  # чужие порты
            (_holder(5, "ragent.exe", "-port", "2540", "-regport", "2541"), False),
            (_holder(6, "rmngr.exe", "-port", "хлам"), False),  # порт не число
        ],
    )
    def test_table(self, process: RagentProcess, expected: bool) -> None:
        assert (port_holders(self.PROFILE, [process], frozenset()) == (process,)) is expected

    def test_opaque_process_is_skipped(self) -> None:
        opaque = RagentProcess(pid=7, executable=None, argv=None, create_time=107.0)
        assert port_holders(self.PROFILE, [opaque], frozenset()) == ()

    def test_own_job_pids_are_excluded(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: процесс из НАШЕГО Job — не «чужой держатель», а
        остаток (спека T-12 §4). Мутация «не смотреть `exclude_pids`» уронит тест.
        """  # noqa: RUF002
        ours = _holder(8, "rmngr.exe", "-port", "1541")
        alien = _holder(9, "rmngr.exe", "-port", "1541")
        assert port_holders(self.PROFILE, [ours, alien], frozenset({8})) == (alien,)

    def test_order_is_preserved(self) -> None:
        first = _holder(10, "rmngr.exe", "-port", "1541")
        second = _holder(11, "ragent.exe", "-port", "1540")
        assert port_holders(self.PROFILE, [second, first], frozenset()) == (second, first)


class TestPortHoldersText:
    PROFILE = _profile(port=1540, regport=1541, cluster_dir=r"E:\srv\a")

    def test_regport_only(self) -> None:
        holders = [
            _holder(300, "rmngr.exe", "-port", "1541"),
            _holder(301, "rmngr.exe", "-port", "1541"),
        ]
        assert port_holders_text(self.PROFILE, holders) == (
            "порт регистрации 1541 занят PID 300, 301 (запущен не лаунчером)"
        )

    def test_port_only(self) -> None:
        holders = [_holder(302, "ragent.exe", "-port", "1540", "-regport", "9541")]
        assert port_holders_text(self.PROFILE, holders) == (
            "порт 1540 занят PID 302 (запущен не лаунчером)"
        )

    def test_both_ports(self) -> None:
        holders = [_holder(303, "ragent.exe", "-port", "1540", "-regport", "1541")]
        assert port_holders_text(self.PROFILE, holders) == (
            "порты 1540 и 1541 заняты PID 303 (запущен не лаунчером)"
        )
