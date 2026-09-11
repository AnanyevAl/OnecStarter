"""Домен CLI EDT (спека v3, §14; факты — §0-Д): строки команд и командная строка.

Чистые функции: ни ФС, ни процессов. Имена команд `import`/`validate` —
[?] выведены из имён методов плагина, подтверждаются экспериментом 6;
ключи — [Д] ресурсы CLI. Разделитель списка `--project-list` — [?],
константа `_LIST_SEPARATOR` в одном месте.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from onecstarter.domain.edt import workspace_key
from onecstarter.domain.launch import LaunchCommand

CLI_ENCODING_ARGS = (  # [?] спека §0-Д: обе пары свойств — JDK 17+ # noqa: RUF003
    "-Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8 "
    "-Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8"
)
_LIST_SEPARATOR = " "
_PLATFORM_VERSION = re.compile(r"^\d+(\.\d+){1,3}$")


class CliQuoteError(ValueError):
    """Значение содержит одинарную кавычку — экранирование Gogo не проверялось (спека §14.2)."""


def quote_cli_arg(value: str) -> str:
    """Одинарные кавычки — [Д] справка CLI («use single quotes … interpreter rules»)."""
    if "'" in value:
        msg = f"Одинарная кавычка в значении недопустима: {value}"
        raise CliQuoteError(msg)
    return f"'{value}'"


def cli_build_args() -> str:
    return "build --yes"  # [Д] без --yes команда спрашивает «Really build? (y/n)»


def cli_project_args() -> str:
    return "project"


@dataclass(frozen=True)
class ImportForm:
    existing_project_dir: str = ""
    configuration_files: str = ""
    project_dir: str = ""
    project_name: str = ""
    base_project_name: str = ""
    platform_version: str = ""
    build_after: bool = False


def cli_import_args(form: ImportForm) -> str:
    existing = form.existing_project_dir.strip()
    xml = form.configuration_files.strip()
    if existing and xml:
        msg = "Выберите один вариант импорта: существующий проект или файлы XML"
        raise ValueError(msg)
    if existing:
        return f"import --project {quote_cli_arg(existing)}"
    if not xml:
        msg = "Укажите каталог проекта или каталог файлов конфигурации"
        raise ValueError(msg)
    project_dir = form.project_dir.strip()
    project_name = form.project_name.strip()
    if bool(project_dir) == bool(project_name):
        msg = (
            "Для файлов XML укажите каталог или имя нового проекта — одно из двух"
        )
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
    return " ".join(parts)


def cli_validate_args(paths: Sequence[str], tsv: str) -> str:
    if not paths:
        raise ValueError("Не выбран ни один проект")  # noqa: RUF001
    quoted = _LIST_SEPARATOR.join(quote_cli_arg(path) for path in paths)
    return f"validate --project-list {quoted} --file {quote_cli_arg(tsv)}"


@dataclass(frozen=True)
class WorkspaceEntry:
    name: str
    path: str
    is_project: bool


def workspace_projects(entries: Sequence[WorkspaceEntry], project_dir: str) -> list[str]:
    """Пути проектов для `validate`: подкаталоги с `.project` + `project_dir`, если вне."""  # noqa: RUF002
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
    """`-command` до `-vmargs` ([?] спека §0-Д): всё после `-vmargs` уходит JVM."""
    parts = [
        f'-data "{workspace}"',
        f'-command "{command}"',
        f'-vm "{jvm_dir}"',
        "--launcher.appendVmargs",
        "-vmargs",
        installation_vm_args.strip(),
        "-Djava.library.path=",
        project_vm_args.strip(),
        CLI_ENCODING_ARGS,
    ]
    return LaunchCommand(executable=exe, arguments=" ".join(part for part in parts if part))
