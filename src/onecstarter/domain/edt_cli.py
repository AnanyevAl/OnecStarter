"""Домен CLI EDT (спека v3, §14; факты — §0-Д): строки команд и командная строка.

Чистые функции: ни ФС, ни процессов. Имена команд `import`/`validate`, ключ
`--yes`, одинарные кавычки вокруг пути с пробелом и кириллицей (только с прямыми
слэшами: обратные Gogo в кавычках не разбирает, код 204) — [Ф] Э6
(13.09.2026, `docs/research/t17-edt-experiments.md`). Несколько путей в
`--project-list` — список Gogo в квадратных скобках `['a' 'b']` [Ф] Э6:
через пробел без скобок CLI отвечает кодом 204 «Не найден вариант вызова».

Кодировка вывода: `1cedtcli.exe` — обёртка над `1cedtc.exe`, которая дописывает
свой `-Dfile.encoding=<кодовая страница консоли>` ПОСЛЕ наших `-vmargs`, поэтому
флаги `-Dstdout.encoding=UTF-8` и им подобные бесполезны [Ф] Э6. Лечит смена
кодовой страницы скрытой консоли до запуска — `wrap_console_utf8` заворачивает
командную строку в `cmd.exe /d /v:off /c "chcp 65001 >nul & …"` [Ф] Э6.
Плата за cmd.exe: `%ИМЯ%` раскрывается даже в кавычках — значения с `%`
отвергаются (`quote_cli_arg`, `wrap_console_utf8`).

Перечень проектов workspace — реестр `.metadata/.plugins/org.eclipse.core.resources/
.projects/<имя>/.location`, а не подкаталоги workspace: конфигурации заказчика
лежат вне workspace и привязаны на месте [Ф] Э6, 11 workspace. Формат `.location` —
`parse_project_location` ([Д] исходники Eclipse `LocalMetaArea`, [Ф] снятые байты).

Несколько проектов — по одной команде `import --project` на каталог
(`cli_import_commands`); одним сеансом их выполняет режим `-file <скрипт>`. У обёртки
`1cedtcli.exe` нет ключа `-vm`, а после `-file` она пересобирает хвост без кавычек,
поэтому JDK для скрипта задаётся своим ini через `-ini-file` (`cli_ini_text`,
`build_cli_script_command`; [Ф] Э12, `docs/research/t20-edt-import-experiments.md`).
Кандидаты на импорт (`ProjectCandidate`) находит `services/edt_cli.py::scan_projects`,
привязанных помечает `mark_in_workspace` по реестру рабочей области.
"""  # noqa: RUF002

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote

from onecstarter.domain.edt import workspace_key
from onecstarter.domain.launch import LaunchCommand

_PLATFORM_VERSION = re.compile(r"^\d+(\.\d+){1,3}$")

# Реестр проектов Eclipse-workspace относительно каталога workspace ([Ф] Э6).
PROJECTS_REGISTRY = Path(".metadata") / ".plugins" / "org.eclipse.core.resources" / ".projects"

# `org.eclipse.core.internal.localstore.SafeChunkyOutputStream`: маркеры чанка ([Д]).
_BEGIN_CHUNK = bytes.fromhex("40B18B8123BC00141A2596E7A393BE1E")
_END_CHUNK = bytes.fromhex("C058FBF323BC00141A51F38C7BBB77C6")
_URI_PREFIX = "URI//"  # `LocalMetaArea.URI_PREFIX` ([Д])
# Символы, которые cmd.exe толкует вне двойных кавычек ([Ф] замер ревью 13.09.2026:
# внутри "…" целы; `!` гасит /v:off; `%` раскрывается и в кавычках — проверяется отдельно).
_CMD_SPECIALS = frozenset("&|<>^")
_CMD_MAX_LINE = 8191  # предел длины строки cmd.exe ([Ф] «Слишком длинная входная строка», код 1)


class CliQuoteError(ValueError):
    """Значение содержит кавычку или `%` (спека §14.2): одинарная — экранирование
    Gogo не проверялось; двойная — вся команда идёт как `-command "…"` (§14.3), и `"`
    внутри разорвёт внешние кавычки (правка M3 финального ревью плана 2); `%` —
    команда идёт через `cmd.exe` (Э6), который раскрывает `%ИМЯ%` и в кавычках.
    """


def quote_cli_arg(value: str) -> str:
    """Одинарные кавычки — [Д] справка CLI, [Ф] Э6 (путь с пробелом и кириллицей)."""  # noqa: RUF002
    if "'" in value or '"' in value:
        msg = f"Кавычка в значении недопустима: {value}"
        raise CliQuoteError(msg)
    if "%" in value:
        msg = f"Символ % в значении недопустим (команда идёт через cmd.exe): {value}"
        raise CliQuoteError(msg)
    # Только прямые слэши: с обратными Gogo не снимает кавычки — CLI получает  # noqa: RUF003
    # значение с кавычками, код 204 «Illegal char <:> at index 2» ([Ф] Э6).  # noqa: RUF003
    return "'" + value.replace("\\", "/") + "'"


def cli_build_args() -> str:
    return "build --yes"  # [Д] без --yes команда спрашивает «Really build? (y/n)»


def cli_project_args() -> str:
    return "project"


@dataclass(frozen=True)
class ImportForm:
    existing_project_dirs: tuple[str, ...] = ()
    configuration_files: str = ""
    project_dir: str = ""
    project_name: str = ""
    base_project_name: str = ""
    platform_version: str = ""
    build_after: bool = False


def cli_import_commands(form: ImportForm) -> list[str]:
    """Команды `import`: по одной на каталог проекта; файлы XML — одна (спека v3.1.1 §4.1).

    Порядок — как в форме: успех `import` от порядка не зависит ([Ф] Э6 — расширение
    без базовой конфигурации импортировано с кодом 0).
    """  # noqa: RUF002
    existing = [path.strip() for path in form.existing_project_dirs if path.strip()]
    xml = form.configuration_files.strip()
    if existing and xml:
        msg = "Выберите один вариант импорта: существующий проект или файлы XML"
        raise ValueError(msg)
    if existing:
        return [f"import --project {quote_cli_arg(path)}" for path in existing]
    if not xml:
        msg = "Укажите каталог проекта или каталог файлов конфигурации"
        raise ValueError(msg)
    project_dir = form.project_dir.strip()
    project_name = form.project_name.strip()
    if bool(project_dir) == bool(project_name):
        msg = "Для файлов XML укажите каталог или имя нового проекта — одно из двух"
        raise ValueError(msg)
    parts = ["import", "--configuration-files", quote_cli_arg(xml)]
    if project_dir:
        parts += ["--project", quote_cli_arg(project_dir)]
    else:
        parts += ["--project-name", quote_cli_arg(project_name)]
    if form.base_project_name.strip():
        parts += ["--base-project-name", quote_cli_arg(form.base_project_name.strip())]
    if form.platform_version.strip():
        version = form.platform_version.strip()
        if not _PLATFORM_VERSION.match(version):
            raise ValueError("Версия платформы — вида 8.3.x")
        parts += ["--version", version]
    if form.build_after:
        parts.append("--build")
    return [" ".join(parts)]


def cli_validate_args(paths: Sequence[str], tsv: str) -> str:
    """Список путей — `['a' 'b']` (список Gogo, [Ф] Э6); скобки и для одного пути."""
    if not paths:
        raise ValueError("Не выбран ни один проект")  # noqa: RUF001
    quoted = " ".join(quote_cli_arg(path) for path in paths)
    return f"validate --project-list [{quoted}] --file {quote_cli_arg(tsv)}"


@dataclass(frozen=True)
class WorkspaceEntry:
    name: str
    path: str
    is_project: bool


@dataclass(frozen=True)
class ProjectCandidate:
    """Каталог с `.project`, найденный `services/edt_cli.py::scan_projects` (спека v3.1.1 §2).

    `relative` — путь от корня сканирования через `/` (корень-проект — имя его каталога);
    имя из `.project` не читаем: CLI регистрирует проект по каталогу ([Ф] Э6).
    """  # noqa: RUF002

    path: str
    relative: str
    in_workspace: bool = False


def mark_in_workspace(
    candidates: Sequence[ProjectCandidate], entries: Sequence[WorkspaceEntry]
) -> list[ProjectCandidate]:
    """`in_workspace` по реестру рабочей области: совпадение `workspace_key` с путём
    любой записи — и без `.project` тоже, привязка есть."""  # noqa: RUF002
    keys = {workspace_key(entry.path) for entry in entries}
    return [
        replace(candidate, in_workspace=workspace_key(candidate.path) in keys)
        for candidate in candidates
    ]


def workspace_projects(entries: Sequence[WorkspaceEntry], project_dir: str) -> list[str]:
    """Пути проектов для `validate`: записи реестра workspace с `.project` + `project_dir`, если его там нет."""  # noqa: RUF002, E501
    result = [entry.path for entry in entries if entry.is_project]
    if project_dir:
        keys = {workspace_key(path) for path in result}
        if workspace_key(project_dir) not in keys:
            result.insert(0, project_dir)
    return result


def build_cli_command(
    exe: Path,
    workspace: str,
    command: str,
    jvm_dir: Path,
    installation_vm_args: str,
    project_vm_args: str,
) -> LaunchCommand:
    """`-command` до `-vmargs` ([Ф] Э6: обёртка передаёт всё после `-vmargs` JVM ребёнка)."""
    parts = [
        f'-data "{workspace}"',
        f'-command "{command}"',
        f'-vm "{jvm_dir}"',
        "--launcher.appendVmargs",
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))


INSTALLATION_INI = "1cedt.ini"


def build_cli_script_command(
    exe: Path,
    workspace: str,
    script: Path,
    ini: Path,
    installation_vm_args: str,
    project_vm_args: str,
) -> LaunchCommand:
    """`-data "<ws>" -ini-file "<ini>" -vmargs <args> -file "<скрипт>"` ([Ф] Э12).

    У обёртки `1cedtcli.exe` нет ключа `-vm`: после `-file` хвост уходит лаунчеру без
    кавычек и `-vm "C:\\Program Files\\…"` превращается в `C:\\Program`. JDK — в ini
    (`cli_ini_text`). `-ini-file` и `-vmargs` — до `-file` (грамматика обёртки); список
    `-vmargs` не пуст никогда, иначе обёртка приняла бы `-file` за аргумент JVM.
    """  # noqa: RUF002
    parts = [
        f'-data "{workspace}"',
        f'-ini-file "{ini}"',
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
        f'-file "{script}"',
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))


def cli_ini_text(installation_ini: str, jvm_dir: Path) -> str:
    """Свой ini для `-ini-file` ([Ф] Э12): строки `1cedt.ini` установки без `-Dosgi.debug…`
    (так же делает обёртка, копируя ini во `%TEMP%`) и без прежней пары `-vm`/<путь>,
    плюс `-vm` и `<bin JDK>` перед `-vmargs`; нет `-vmargs` — в конец. LF."""
    lines: list[str] = []
    skip_path = False
    inserted = False
    for line in installation_ini.splitlines():
        if skip_path:
            skip_path = False
            continue
        if line.strip() == "-vm":
            skip_path = True
            continue
        if line.startswith("-Dosgi.debug"):
            continue
        if line.strip() == "-vmargs" and not inserted:
            lines += ["-vm", str(jvm_dir)]
            inserted = True
        lines.append(line)
    if not inserted:
        lines += ["-vm", str(jvm_dir)]
    return "\n".join(lines) + "\n"


def wrap_console_utf8(command: LaunchCommand, comspec: Path) -> LaunchCommand:
    """`cmd.exe /d /v:off /c "chcp 65001 >nul & <командная строка>"` ([Ф] Э6).

    `1cedtcli.exe` берёт кодовую страницу консоли в `-Dfile.encoding` ребёнка;
    в скрытой консоли (`CREATE_NO_WINDOW`) она OEM (cp866), и вывод команды
    вместе с внутренним логом EDT идёт в cp866. `chcp 65001` в той же консоли
    до запуска даёт `-Dfile.encoding=UTF-8`. cmd после `/c` снимает первую и
    последнюю кавычку строки — внутренние кавычки остаются как есть. `/d` —
    без AutoRun, `/v:off` — без раскрытия `!имя!`; `%имя%` cmd раскрывает всегда,
    поэтому строка с `%` отвергается.
    """  # noqa: RUF002
    line = command.command_line
    if "%" in line:
        msg = f"Символ % в командной строке недопустим (команда идёт через cmd.exe): {line}"
        raise CliQuoteError(msg)
    specials = _unquoted_cmd_specials(line)
    if specials:
        msg = (
            f"Символы {specials!r} вне кавычек недопустимы (команда идёт через cmd.exe; "
            f"обычно это vm_args): {line}"
        )
        raise CliQuoteError(msg)
    arguments = f'/d /v:off /c "chcp 65001 >nul & {line}"'
    wrapped = LaunchCommand(executable=comspec, arguments=arguments)
    if len(wrapped.command_line) > _CMD_MAX_LINE:
        msg = (
            f"Командная строка длиннее предела cmd.exe ({_CMD_MAX_LINE} символов) — "
            "уменьшите перечень проектов"
        )
        raise CliQuoteError(msg)
    return wrapped


def _unquoted_cmd_specials(line: str) -> str:
    """`& | < > ^` вне двойных кавычек — их cmd истолкует: `D:\\R&D` режет строку и запускает
    `D`, `a|b` уводит вывод в трубу ([Ф] замер ревью 13.09.2026). `-data`, `-command`, `-vm`
    всегда в кавычках; без кавычек идут только `vm_args` установки и записи."""
    in_quotes = False
    found: list[str] = []
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif not in_quotes and char in _CMD_SPECIALS:
            found.append(char)
    return "".join(found)


def _file_uri_to_path(uri: str) -> str:
    """`file:/E:/a%20b/п` → путь Windows; UNC — `file:////srv/share` ([Д] `URIUtil.toURI`
    Eclipse добавляет лишнюю пару слэшей, чтобы отличить UNC от authority) и `file://srv/share`
    (authority-форма: Eclipse читает, не пишет); 1 или 3 слэша — локальный путь; иные схемы —
    как есть.
    """
    if not uri.startswith("file:"):
        return uri
    rest = unquote(uri[len("file:") :])
    slashes = len(rest) - len(rest.lstrip("/"))
    body = rest.lstrip("/").replace("/", "\\")
    if slashes == 2 or slashes >= 4:
        return "\\\\" + body
    return body


def parse_project_location(raw: bytes) -> str | None:
    """Путь проекта из `.location` реестра workspace; `None` — проект в `<workspace>/<имя>`.

    Формат ([Д] `LocalMetaArea.writePrivateDescription`, [Ф] байты Э6): чанк
    `BEGIN_CHUNK` + `DataOutputStream.writeUTF` строки `URI//<uri>` (пустая —
    расположение по умолчанию) + число динамических ссылок + их имена + `END_CHUNK`.
    Перед записью Eclipse очищает файл (`Workspace.clear`) — в норме ровно один чанк;
    `rfind(BEGIN_CHUNK)` — устойчивость к оборванной записи (BEGIN без END, затем полный
    чанк): `SafeChunkyInputStream.refineChunk` в этом случае тоже берёт последний BEGIN
    ([Д] исходники Eclipse, уточнение ревью 13.09.2026). Modified UTF-8 Java для BMP
    совпадает с UTF-8; повреждённый файл даёт `None`.
    """  # noqa: RUF002
    start = raw.rfind(_BEGIN_CHUNK)
    if start < 0:
        return None
    pos = start + len(_BEGIN_CHUNK)
    if len(raw) < pos + 2:
        return None
    length = int.from_bytes(raw[pos : pos + 2], "big")
    data = raw[pos + 2 : pos + 2 + length]
    if len(data) < length:
        return None
    text = data.decode("utf-8", errors="replace")
    if not text.startswith(_URI_PREFIX):
        return None
    return _file_uri_to_path(text[len(_URI_PREFIX) :])


def location_blob(uri: str | None) -> bytes:
    """Обратная к `parse_project_location`: байты `.location` без ссылок (для тестов и фикстур)."""
    text = "" if uri is None else _URI_PREFIX + uri
    payload = text.encode("utf-8")
    references = (0).to_bytes(4, "big")
    return _BEGIN_CHUNK + len(payload).to_bytes(2, "big") + payload + references + _END_CHUNK
