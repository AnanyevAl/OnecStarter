# ruff: noqa: RUF001, RUF002, RUF003 — исследовательский скрипт с русскими текстами
"""T-20 / Э12: 1cedtcli.exe в режимах -file (скрипт) и -command на тестовых рабочих областях.

Запуск: `uv run python docs/research/t20-edt-import.py <шаг 1..4>`.

Командная строка заворачивается тем же кодом, что в программе
(`domain/edt_cli.py::wrap_console_utf8`: `cmd.exe /d /v:off /c "chcp 65001 >nul & …"`),
и уходит в `CreateProcess` строкой через `subprocess.run` — как у `spawn_logged`.

Режим скрипта — `-ini-file "<ini>" -vmargs <args> -file "<скрипт>"`: у обёртки
`1cedtcli.exe` нет ключа `-vm`, JDK задаётся через свой ini (копия `1cedt.ini`
установки без `-Dosgi.debug` + строки `-vm`/`<путь>`); в режиме `-command` хвост
строки уходит лаунчеру сырым, поэтому `-vm "…"` там работает (Э6), а после `-file`
обёртка пересобирает хвост без кавычек — `-vm "C:\\Program Files\\…"` превращается
в `C:\\Program` (16.09.2026, зонды a–h). `;` внутри `-command` — код 204 (зонд i).
"""

import subprocess
import sys
import time
from pathlib import Path

from onecstarter.domain.edt_cli import parse_project_location, wrap_console_utf8
from onecstarter.domain.launch import LaunchCommand
from onecstarter.services.edt_cli import default_comspec

CLI = Path(r"C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64\1cedtcli.exe")
JDK = Path(r"C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin")
BASE = Path(r"E:\tmp\edt-test")
IMP = BASE / "imp"
INI = IMP / "cli.ini"
VM_ARGS = "-Xmx8192m -DnativeFormBufferedLayoutRender=true -Djava.library.path="
REGISTRY = Path(".metadata") / ".plugins" / "org.eclipse.core.resources" / ".projects"


def write_ini() -> None:
    """Копия `1cedt.ini` установки без `-Dosgi.debug` (как делает сама обёртка во
    `%TEMP%\\1cedt.ini`) плюс `-vm` перед `-vmargs`; относительные `plugins/…` лаунчер
    разрешает от каталога exe — обёртка тоже оставляет их относительными."""
    lines: list[str] = []
    for line in (CLI.parent / "1cedt.ini").read_text(encoding="utf-8").splitlines():
        if line.startswith("-Dosgi.debug"):
            continue
        if line == "-vmargs":
            lines += ["-vm", str(JDK)]
        lines.append(line)
    # LF, как пишет программа (cli_ini_text); шаги 1–2 Э12 шли с CRLF (newline по умолчанию)
    INI.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def script_mode(script: Path) -> str:
    write_ini()
    return f'-ini-file "{INI}" -vmargs {VM_ARGS} -file "{script}"'


def command_mode(command: str) -> str:
    return f'-command "{command}" -vm "{JDK}" --launcher.appendVmargs -vmargs {VM_ARGS}'


def run(workspace: Path, mode: str, out: Path) -> None:
    command = LaunchCommand(executable=CLI, arguments=f'-data "{workspace}" {mode}')
    launch = wrap_console_utf8(command, default_comspec())
    print("командная строка:", launch.command_line)
    started = time.monotonic()
    with out.open("wb") as handle:
        code = subprocess.run(  # строка уходит в CreateProcess как есть
            launch.command_line, stdout=handle, stderr=subprocess.STDOUT, check=False
        ).returncode
    seconds = int(time.monotonic() - started)
    print(f"код {code}, {seconds} с, stdout {out.stat().st_size} байт: {out}")
    registry = workspace / REGISTRY
    if registry.is_dir():
        for entry in sorted(registry.iterdir()):
            name = entry.name
            location = entry / ".location"
            path = parse_project_location(location.read_bytes()) if location.is_file() else None
            print(f"реестр: {name} -> {path if path is not None else '(в workspace)'}")
    else:
        print("реестр: каталога нет")
    log = workspace / ".metadata" / "1cedtcli.log"
    if log.is_file():
        print(f"1cedtcli.log: {log.stat().st_size} байт")


STEPS = {
    1: (BASE / "ws-imp1", script_mode(IMP / "s1.cli"), IMP / "s1.out"),
    2: (BASE / "ws-imp2", script_mode(IMP / "s2.cli"), IMP / "s2.out"),
    3: (
        BASE / "ws-imp3",
        command_mode(
            "import --project ['E:/tmp/edt-test/dev_tools' 'E:/tmp/edt-test/imp/консоль копия']"
        ),
        IMP / "s3.out",
    ),
    4: (
        Path(r"E:\edt\тест_2026"),
        command_mode("import --project 'E:/tmp/edt-test/dev_tools'"),
        IMP / "s4.out",
    ),
}

if __name__ == "__main__":
    run(*STEPS[int(sys.argv[1])])
