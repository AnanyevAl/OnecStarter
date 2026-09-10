"""Домен раздела «EDT»: модель записей, установок и чистые решения (спека v3, §2–§6).

Ничего из этого модуля не обращается к ФС и процессам: всё окружение подаётся
аргументами (инвариант 2). Факты о раскладке EDT — спека §0, метки достоверности
там же; здесь они повторяются рядом с константами, которые на них опираются.
"""  # noqa: RUF002

import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from onecstarter.domain.launch import LaunchCommand

EDT_EXE = "1cedt.exe"  # [Ф] спека §0: каталог установки
CLI_EXE = "1cedtcli.exe"  # [Ф] спека §0-Д: консольная подсистема
# [Ф] -Dosgi.requiredJavaVersion=17 у всех трёх установок  # noqa: RUF003
DEFAULT_REQUIRED_JAVA = 17

# [Ф] спека §0: `1c-edt-<версия>-x86_64`; версия совпадает с installedVersion.label.  # noqa: RUF003
_EDT_DIR = re.compile(r"^1c-edt-(?P<version>\d[0-9A-Za-z.+]*)-x86_64$")
_REQUIRED_JAVA = re.compile(r"^-Dosgi\.requiredJavaVersion=(\d+)$")
_RELEASE_VERSION = re.compile(r'^JAVA_VERSION="([^"]+)"$', re.MULTILINE)

LANGUAGES: tuple[tuple[str, str], ...] = (
    ("", "По умолчанию"),
    ("ru", "Русский"),
    ("en", "English"),
)

_XMX = re.compile(r"^-Xmx(\d+)([kKmMgG]?)$")
_LANGUAGE = re.compile(r"^-Duser\.language=(.+)$")


@dataclass(frozen=True)
class VmArgsParts:
    max_heap_mb: int | None
    language: str | None
    rest: tuple[str, ...]


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
class ImportCandidate:
    project: EdtProject
    version_known: bool  # False — productId без продукта в products.json (спека §6)


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


def import_candidates(
    projects: Sequence[EdtStartProject],
    products: Sequence[EdtStartProduct],
    existing: Iterable[EdtProject],
    new_id: Callable[[], str],
) -> list[ImportCandidate]:
    """Кандидат — проект EDT Start, чьего workspace у нас ещё нет (спека §6).

    `args` продукта в запись не копируются: они остаются на уровне установки
    и читаются вживую (спека §2, три уровня). Повторный вызов на результате
    предыдущего пуст — идемпотентность проверяется тестом и мутацией (§9).
    """  # noqa: RUF002
    known = {workspace_key(project.workspace) for project in existing}
    versions = {product.id: product.version for product in products}
    result: list[ImportCandidate] = []
    for source in projects:
        workspace = str(source.workspace)
        if workspace_key(workspace) in known:
            continue
        version = versions.get(source.product_id)
        result.append(
            ImportCandidate(
                EdtProject(
                    id=new_id(),
                    name=source.label or source.workspace.name,
                    workspace=workspace,
                    edt_version=version or "",
                    jvm_dir=str(source.jvm_dir) if source.jvm_dir is not None else "",
                    vm_args=" ".join(source.args),
                ),
                version_known=version is not None,
            )
        )
    return result


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


def _tokens(text: str) -> list[str]:
    """Разбить строку аргументов, сохраняя кавычки в токенах.

    Незакрытая кавычка — не повод терять текст: вся строка становится
    одним токеном и уходит в «прочее» как есть.
    """
    if not text.strip():
        return []

    tokens: list[str] = []
    current_token = ""
    in_double_quotes = False

    for char in text:
        if char == '"':
            in_double_quotes = not in_double_quotes
            current_token += char
        elif char == " " and not in_double_quotes:
            if current_token:
                tokens.append(current_token)
                current_token = ""
        else:
            current_token += char

    if current_token:
        if in_double_quotes:
            return [text.strip()]
        tokens.append(current_token)

    return tokens


def _heap_mb(amount: str, unit: str) -> int | None:
    value = int(amount)
    unit = unit.lower()
    if unit == "m":
        return value
    if unit == "g":
        return value * 1024
    if unit == "k":
        return value // 1024
    return value // (1024 * 1024)


def split_vm_args(text: str) -> VmArgsParts:
    """Память и язык — из токенов; при повторе `-Xmx` действует последний (спека §2)."""
    heap: int | None = None
    language: str | None = None
    rest: list[str] = []
    for token in _tokens(text):
        xmx = _XMX.match(token)
        if xmx:
            heap = _heap_mb(xmx.group(1), xmx.group(2))
            continue
        lang = _LANGUAGE.match(token)
        if lang:
            language = lang.group(1)
            continue
        rest.append(token)
    return VmArgsParts(max_heap_mb=heap, language=language, rest=tuple(rest))


def join_vm_args(max_heap_mb: int | None, language: str | None, rest: Sequence[str]) -> str:
    """Порядок сборки: прочее, затем `-Xmx`, затем `-Duser.language` (спека §2)."""
    tokens = list(rest)
    if max_heap_mb is not None:
        tokens.append(f"-Xmx{max_heap_mb}m")
    if language:
        tokens.append(f"-Duser.language={language}")
    return " ".join(tokens)


def java_version_key(version: str) -> tuple[int, ...]:
    """`17.0.16` → (17, 0, 16); `1.8.0_392` → (1, 8, 0, 392) — для сравнения числами."""
    return tuple(int(part) for part in re.findall(r"\d+", version))


def pick_jvm(
    *,
    product: Path | None,
    ini: Path | None,
    settings: Path | None,
    auto: Sequence[tuple[str, Path]],
    required_java: int,
) -> tuple[Path, str] | None:
    """Цепочка спеки §3: products.json → 1cedt.ini → настройка → старший подходящий JDK.

    Все пути уже проверены на существование вызывающим (иначе `None`);
    здесь — только порядок предпочтения. `auto` — пары «`JAVA_VERSION`
    из `release`, каталог bin»: подходит major ≥ требуемого, побеждает старшая
    полная версия, сравниваемая числами (строкой `17.0.9` > `17.0.16` —
    находка ревью Task 3). Возвращает путь и имя источника для диалога записи.
    """  # noqa: RUF002
    for path, source in ((product, "products.json"), (ini, "1cedt.ini"), (settings, "settings")):
        if path is not None:
            return path, source
    fitting = [
        (version, path)
        for version, path in auto
        if (java_major(version) or 0) >= required_java
    ]
    if not fitting:
        return None
    _version, best = max(fitting, key=lambda pair: (java_version_key(pair[0]), str(pair[1])))
    return best, "auto"


def effective_jvm(project: EdtProject, installation: EdtInstallation) -> Path | None:
    if project.jvm_dir:
        return Path(project.jvm_dir)
    return installation.jvm_dir


def build_edt_command(
    exe: Path,
    workspace: str,
    jvm_dir: Path,
    installation_vm_args: str,
    project_vm_args: str,
) -> LaunchCommand:
    """Дословно строка EDT Start ([Ф] спека §0), включая `-Djava.library.path=`.

    Аргументы установки идут до аргументов записи: при повторе `-Xmx`
    JVM берёт последний ([?] спека §0, эксперимент 1), и запись побеждает.
    """
    parts = [
        f'-data "{workspace}"',
        f'-vm "{jvm_dir}"',
        "--launcher.appendVmargs",
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))


EDITOR_MISSING_NOTE = "Не найден — укажите путь в Настройках"  # noqa: RUF001


def running_workspaces(
    processes: Iterable[tuple[int, tuple[str, ...] | None]],
    projects: Iterable[EdtProject],
) -> dict[str, int]:
    """`-data <путь>` в argv `1cedt.exe` → запись с тем же ключом workspace (спека §4).

    `argv is None` — нет доступа к процессу, пропускается. Первый найденный
    pid остаётся: второго EDT на том же workspace не бывает (блокировка Eclipse),
    а если снимок застал два — активировать первый не хуже второго.
    """  # noqa: RUF002
    by_key = {workspace_key(project.workspace): project.id for project in projects}
    result: dict[str, int] = {}
    for pid, argv in processes:
        if not argv:
            continue
        for index, token in enumerate(argv[:-1]):
            if token != "-data":
                continue
            project_id = by_key.get(workspace_key(argv[index + 1].strip('"')))
            if project_id is not None and project_id not in result:
                result[project_id] = pid
            break
    return result


@dataclass(frozen=True)
class EditorResolution:
    path: Path | None
    source: str  # "settings" | "PATH" | "known" | ""
    note: str  # причина отказа для подсказки; "" — найден


def resolve_editor(
    setting: str,
    setting_exists: bool,
    found_in_path: Path | None,
    known_existing: Sequence[Path],
) -> EditorResolution:
    """Приоритет спеки §5: настройка непуста — только она; пуста — PATH, затем каталоги.

    Явно указанный несуществующий путь — «не найден», без тихого отката
    к автопоиску: пользователь увидит в Настройках, что путь не существует.
    """
    if setting:
        if setting_exists:
            return EditorResolution(Path(setting), "settings", "")
        return EditorResolution(None, "settings", f"Указанный путь не существует: {setting}")
    if found_in_path is not None:
        return EditorResolution(found_in_path, "PATH", "")
    if known_existing:
        return EditorResolution(known_existing[0], "known", "")
    return EditorResolution(None, "", EDITOR_MISSING_NOTE)
