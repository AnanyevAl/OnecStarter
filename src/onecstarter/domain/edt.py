"""Домен раздела «EDT»: модель записей, установок и чистые решения (спека v3, §2–§6).

Ничего из этого модуля не обращается к ФС и процессам: всё окружение подаётся
аргументами (инвариант 2). Факты о раскладке EDT — спека §0, метки достоверности
там же; здесь они повторяются рядом с константами, которые на них опираются.
"""  # noqa: RUF002

import os
import re
from dataclasses import dataclass
from pathlib import Path

EDT_EXE = "1cedt.exe"  # [Ф] спека §0: каталог установки
CLI_EXE = "1cedtcli.exe"  # [Ф] спека §0-Д: консольная подсистема
# [Ф] -Dosgi.requiredJavaVersion=17 у всех трёх установок  # noqa: RUF003
DEFAULT_REQUIRED_JAVA = 17

# [Ф] спека §0: `1c-edt-<версия>-x86_64`; версия совпадает с installedVersion.label.  # noqa: RUF003
_EDT_DIR = re.compile(r"^1c-edt-(?P<version>\d[0-9A-Za-z.+]*)-x86_64$")
_REQUIRED_JAVA = re.compile(r"^-Dosgi\.requiredJavaVersion=(\d+)$")
_RELEASE_VERSION = re.compile(r'^JAVA_VERSION="([^"]+)"$', re.MULTILINE)


@dataclass(frozen=True)
class EdtGroup:
    id: str
    name: str
    parent_id: str | None = None


@dataclass(frozen=True)
class EdtProject:
    id: str
    name: str
    workspace: str  # путь для -data; обязателен
    project_dir: str = ""  # каталог для редакторов; "" — редакторы получают workspace
    edt_version: str = ""  # точно как в имени каталога установки: "2025.2.6+4"
    jvm_dir: str = ""  # каталог bin JDK; "" — JVM установки
    vm_args: str = ""  # аргументы JVM записи; "" — действуют 1cedt.ini и установка
    group_id: str | None = None


@dataclass(frozen=True)
class EdtInstallation:
    version: str
    exe: Path
    jvm_dir: Path | None  # подобранный каталог bin; None — не найден
    vm_args: str  # args продукта из products.json; "" — продукта там нет
    required_java: int
    jvm_source: str  # "products.json" | "1cedt.ini" | "settings" | "auto" | ""


@dataclass(frozen=True)
class EdtStartProduct:
    id: str
    version: str  # installedVersion.label
    exe: Path
    jvm_dir: Path | None
    args: tuple[str, ...]


@dataclass(frozen=True)
class EdtStartProject:
    id: str
    label: str
    workspace: Path
    product_id: str
    args: tuple[str, ...]
    jvm_dir: Path | None  # [?] ключ jvmPath у записи — спека §0, эксперимент 4  # noqa: RUF003


@dataclass(frozen=True)
class IniInfo:
    vm: str | None
    required_java: int


def workspace_key(path: str) -> str:
    """Ключ пути для сравнения: регистр, разделители, `.`/`..` — без обращения к диску.

    Та же формула, что `services/availability.py::path_key`; повторена здесь,
    потому что `domain` не импортирует `services`.
    """  # noqa: RUF002
    return os.path.normcase(os.path.normpath(path))


def version_from_dir_name(name: str) -> str | None:
    match = _EDT_DIR.match(name)
    return match.group("version") if match else None


def parse_ini(text: str) -> IniInfo:
    """`-vm` — строка после него (если есть), `-Dosgi.requiredJavaVersion=N` — порог JDK."""
    lines = [line.strip() for line in text.splitlines()]
    vm: str | None = None
    required = DEFAULT_REQUIRED_JAVA
    for index, line in enumerate(lines):
        if line == "-vm" and index + 1 < len(lines) and lines[index + 1]:
            vm = lines[index + 1]
            continue
        match = _REQUIRED_JAVA.match(line)
        if match:
            required = int(match.group(1))
    return IniInfo(vm=vm, required_java=required)


def parse_release(text: str) -> str | None:
    """`JAVA_VERSION="17.0.16"` из файла `release` в каталоге JDK ([Ф] спека §0)."""
    match = _RELEASE_VERSION.search(text)
    return match.group(1) if match else None


def java_major(version: str) -> int | None:
    """`17.0.16` → 17; старая схема `1.8.0_392` → 8."""
    parts = version.split(".")
    try:
        first = int(parts[0])
    except ValueError:
        return None
    if first == 1 and len(parts) > 1:
        try:
            return int(parts[1].split("_")[0])
        except ValueError:
            return None
    return first
