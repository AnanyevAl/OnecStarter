"""Номера версий платформы 1С: разбор, числовое сравнение, маски.

Сравнение — покомпонентное числовое: лексикографический порядок строк
даёт 8.3.9 > 8.3.18 и ломает выбор версии (скил platform-launch, факт 5).
Маска сравнивается как кортеж чисел: startswith по строке ловит 8.3.250.1
маской 8.3.25. «Полная» версия = 4 компонента — решение плана 2, не факт
формата: ИТС термин «полный номер» не определяет.
"""  # noqa: RUF002

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")

FULL_VERSION_PARTS = 4


@dataclass(frozen=True, order=True)
class VersionNumber:
    parts: tuple[int, ...]

    @property
    def is_full(self) -> bool:
        return len(self.parts) == FULL_VERSION_PARTS

    def starts_with(self, prefix: "VersionNumber") -> bool:
        return self.parts[: len(prefix.parts)] == prefix.parts

    def __str__(self) -> str:
        return ".".join(str(part) for part in self.parts)


def parse_version(text: str) -> VersionNumber:
    if not _VERSION_RE.match(text):
        raise ValueError(f"Некорректный номер версии: {text!r}")
    return VersionNumber(tuple(int(part) for part in text.split(".")))


class Arch(Enum):
    """Фактическая разрядность исполняемого файла.

    Не путать со словарём предпочтений AppArch (x86_prt, x86_64_prt) —
    тот остаётся строками там, где читается из файлов 1С.
    """  # noqa: RUF002

    X86 = "x86"
    X64 = "x86_64"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Installation:
    version: VersionNumber
    path: Path
    arch: Arch
