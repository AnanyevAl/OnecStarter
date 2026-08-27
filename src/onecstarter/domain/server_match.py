"""Разбор командных строк семейства ragent и сопоставление с профилями.

Краевые случаи нормализации сняты живьём ([Ф] Б1/А1 t07-protocol.md):
прямые слэши сохраняются, rmngr дописывает хвостовой разделитель —
в том числе внутрь кавычек; NTFS регистронезависима. Имена ключей
регистронезависимы ([Ф] А1).
"""  # noqa: RUF002

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from onecstarter.domain.server import ServerProfile
from onecstarter.domain.version import VersionNumber, parse_version


@dataclass(frozen=True)
class RagentProcess:
    pid: int
    executable: Path | None  # None — нет доступа ([Ф] В1: чужой/служба)  # noqa: RUF003
    argv: tuple[str, ...] | None
    create_time: float


@dataclass(frozen=True)
class RagentParams:
    port: int | None
    regport: int | None
    range_text: str | None
    cluster_dir: str | None


_SEPARATORS = re.compile(r"[\\/]+")


def normalize_cluster_dir(text: str) -> str:
    cleaned = text.strip().strip('"')
    cleaned = _SEPARATORS.sub("\\\\", cleaned)
    return cleaned.rstrip("\\").casefold()


_VALUE_KEYS = {"-port": "port", "-regport": "regport", "-range": "range_text", "-d": "cluster_dir"}


def extract_ragent_params(argv: Sequence[str]) -> RagentParams:
    values: dict[str, str] = {}
    index = 1
    while index < len(argv):
        token = argv[index]
        field = _VALUE_KEYS.get(token.casefold())
        if field is not None and index + 1 < len(argv):
            candidate = argv[index + 1]
            if not candidate.startswith("-"):
                values[field] = candidate
                index += 2
                continue
        index += 1

    def _int_of(name: str) -> int | None:
        raw = values.get(name)
        if raw is None or not raw.isdigit():
            return None
        return int(raw)

    return RagentParams(
        port=_int_of("port"),
        regport=_int_of("regport"),
        range_text=values.get("range_text"),
        cluster_dir=values.get("cluster_dir"),
    )


def version_from_exe_path(path: Path) -> VersionNumber | None:
    try:
        return parse_version(path.parent.parent.name)
    except ValueError:
        return None


@dataclass(frozen=True)
class ForeignServer:
    process: RagentProcess
    version: VersionNumber | None
    params: RagentParams | None  # None — командная строка недоступна ([Ф] В1)  # noqa: RUF003


@dataclass(frozen=True)
class MatchResult:
    by_profile: Mapping[str, tuple[RagentProcess, ...]]
    foreign: tuple[ForeignServer, ...]


def match_profiles(
    profiles: Sequence[ServerProfile], processes: Sequence[RagentProcess]
) -> MatchResult:
    wanted = {normalize_cluster_dir(p.cluster_dir): p.id for p in profiles}
    matched: dict[str, list[RagentProcess]] = {p.id: [] for p in profiles}
    foreign: list[ForeignServer] = []
    for process in processes:
        params = extract_ragent_params(process.argv) if process.argv else None
        cluster = params.cluster_dir if params else None
        profile_id = wanted.get(normalize_cluster_dir(cluster)) if cluster else None
        if profile_id is not None:
            matched[profile_id].append(process)
            continue
        version = version_from_exe_path(process.executable) if process.executable else None
        foreign.append(ForeignServer(process=process, version=version, params=params))
    return MatchResult(
        by_profile={key: tuple(value) for key, value in matched.items()},
        foreign=tuple(foreign),
    )
