"""Профиль локального сервера 1С и сборка аргументов ragent.

Форма аргументов снята с работавших запусков сессии T-07 ([Ф] А1
t07-protocol.md): ключи регистронезависимы, но пишем в нижнем регистре
как srv.sh; путь с пробелом — в стандартных Windows-кавычках; без
пробела — без кавычек (обе формы измерены, прочие не проверялись).
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from onecstarter.domain.version import VersionNumber, parse_version


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


_PORT_MIN, _PORT_MAX = 1, 65535


def _basic_normalize(text: str) -> str:
    return text.replace("/", "\\").rstrip("\\").casefold()


def resolve_server_version(
    requested: str, installed: Sequence[VersionNumber]
) -> VersionNumber | None:
    """Точное совпадение либо максимум с префиксом ([Ф] T-02.1 — правило клиентов).

    Тихого фолбэка «максимум вообще» нет намеренно: платформа так делает
    при запуске клиентов, но сервер мы запускаем сами, и запуск не той
    версии на чужом каталоге кластера дороже честного отказа.
    """  # noqa: RUF002
    try:
        wanted = parse_version(requested.strip())
    except ValueError:
        return None
    if wanted in installed:
        return wanted
    matching = [version for version in installed if version.starts_with(wanted)]
    return max(matching) if matching else None


def validate_profile(
    profile: ServerProfile,
    others: Sequence[ServerProfile],
    normalize: Callable[[str], str] = _basic_normalize,
) -> list[str]:
    errors: list[str] = []
    if not profile.name.strip():
        errors.append("Имя профиля не заполнено")
    try:
        parse_version(profile.version.strip())
    except ValueError:
        errors.append(f"Версия {profile.version!r} не разбирается как номер")
    for label, value in (("Порт", profile.port), ("Порт регистрации", profile.regport)):
        if not _PORT_MIN <= value <= _PORT_MAX:
            errors.append(f"{label} {value} вне диапазона 1-65535")
    if profile.range_start > profile.range_end:
        errors.append("Диапазон портов задом наперёд")
    if profile.port == profile.regport:
        errors.append(f"Порт и порт регистрации совпадают ({profile.port})")
    if not profile.cluster_dir.strip():
        errors.append("Каталог кластера не заполнен")
    taken = {
        port: other.name
        for other in others
        for port in (other.port, other.regport)
    }
    for port in (profile.port, profile.regport):
        if port in taken:
            errors.append(f"Порт {port} уже занят профилем «{taken[port]}»")
    mine = normalize(profile.cluster_dir)
    for other in others:
        if normalize(other.cluster_dir) == mine:
            errors.append(f"Каталог кластера уже занят профилем «{other.name}»")
    return errors


def warn_range_overlap(
    profile: ServerProfile, others: Sequence[ServerProfile]
) -> list[str]:
    """[Ф] А5: пересечение безвредно — процессы разводятся по свободным портам."""  # noqa: RUF002
    warnings: list[str] = []
    for other in others:
        if profile.range_start <= other.range_end and other.range_start <= profile.range_end:
            warnings.append(
                f"Диапазон пересекается с профилем «{other.name}» — не ошибка, "  # noqa: RUF001
                "но при исчерпании портов серверы начнут мешать друг другу"
            )
    return warnings
