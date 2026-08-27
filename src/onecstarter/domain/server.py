"""Профиль локального сервера 1С и сборка аргументов ragent.

Форма аргументов снята с работавших запусков сессии T-07 ([Ф] А1
t07-protocol.md): ключи регистронезависимы, но пишем в нижнем регистре
как srv.sh; путь с пробелом — в стандартных Windows-кавычках; без
пробела — без кавычек (обе формы измерены, прочие не проверялись).
"""  # noqa: RUF002

from collections.abc import Sequence
from dataclasses import dataclass

from onecstarter.domain.version import VersionNumber


@dataclass(frozen=True)
class ServerProfile:
    id: str
    name: str
    version: str  # запрошенная: полный номер или маска, как ввёл пользователь
    port: int
    regport: int
    range_start: int
    range_end: int
    cluster_dir: str
    debug: bool = True
    http: bool = True
    extra_args: str = ""


@dataclass(frozen=True)
class ServerConvention:
    min_version: VersionNumber
    bin_dir: str
    ragent: str
    radmin: str
    console: str  # путь .msc от КОРНЯ 1cv8 (родителя каталогов версий), [Ф] Г1


def server_convention_for(
    version: VersionNumber, conventions: Sequence[ServerConvention]
) -> ServerConvention | None:
    best: ServerConvention | None = None
    for convention in conventions:
        if version < convention.min_version:
            continue
        if best is None or convention.min_version > best.min_version:
            best = convention
    return best


def build_ragent_arguments(profile: ServerProfile) -> str:
    parts: list[str] = []
    if profile.debug:
        parts.append("-debug")
    if profile.http:
        parts.append("-http")
    parts.append(f"-port {profile.port}")
    parts.append(f"-regport {profile.regport}")
    parts.append(f"-range {profile.range_start}:{profile.range_end}")
    directory = profile.cluster_dir
    parts.append(f'-d "{directory}"' if " " in directory else f"-d {directory}")
    extra = profile.extra_args.strip()
    if extra:
        parts.append(extra)
    return " ".join(parts)
