"""Фильтр установок с серверными компонентами поверх найденных версий.

Обнаружение версий не дублируется: `server_installations` работает поверх
результата `find_installations` (`platform_1c.discovery`), а не сканирует
файловую систему заново. Серверные компоненты — опция установки: [Ф] Г1
на машине заказчика они стояли во всех версиях 8.3.10…8.5.4, но фильтр
обязан быть честным в обе стороны и не считать сервер установленным без
проверки на диске — ragent.exe и radmin.dll оба должны быть файлами.
"""  # noqa: RUF002

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from onecstarter.domain.server import ServerConvention, server_convention_for
from onecstarter.domain.version import Installation


@dataclass(frozen=True)
class ServerInstallation:
    installation: Installation
    ragent: Path
    radmin: Path


def server_installations(
    installations: Sequence[Installation], conventions: Sequence[ServerConvention]
) -> list[ServerInstallation]:
    found: list[ServerInstallation] = []
    for installation in installations:
        convention = server_convention_for(installation.version, conventions)
        if convention is None:
            continue
        bin_dir = installation.path / convention.bin_dir
        ragent = bin_dir / convention.ragent
        radmin = bin_dir / convention.radmin
        if not ragent.is_file() or not radmin.is_file():
            continue
        found.append(
            ServerInstallation(installation=installation, ragent=ragent, radmin=radmin)
        )
    return found


def console_path(root: Path, convention: ServerConvention) -> Path:
    result = root
    for part in convention.console.split("/"):
        result = result / part
    return result
