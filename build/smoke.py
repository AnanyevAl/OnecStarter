"""Smoke собранного экземпляра. Обязателен для каждой сборки (CLAUDE.md).

Проверяет собранный dist, а не исходники: (1) консольный exe поднимает окно
offscreen и обе фоновые задачи; (2) ярлык, созданный frozen-веткой, целится
в запущенный exe (шаг 8 задачи 17); (3) лог создан и несёт фазу «окно
показано» — а также однозначную строку с фактическим `sys.frozen` (задача 10,
спека §3.3); (4) exe принимает --autostart и завершается штатно. APPDATA
подменяется — живые данные машины не трогаются.
"""  # noqa: RUF002

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def shortcut_target(lnk: Path) -> str:
    """Цель ярлыка штатным читателем Windows — не нашим кодом."""
    command = (
        "(New-Object -ComObject WScript.Shell)"
        f".CreateShortcut('{lnk}').TargetPath"
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    dist = Path(sys.argv[1]).resolve()
    console_exe = dist / "OneCStarterc.exe"
    if not console_exe.is_file():
        print(f"smoke: нет {console_exe}")
        return 1
    with tempfile.TemporaryDirectory() as scratch:
        appdata = Path(scratch) / "appdata"
        out = Path(scratch) / "out"
        out.mkdir()
        env = dict(os.environ)
        env["APPDATA"] = str(appdata)
        env["QT_QPA_PLATFORM"] = "offscreen"
        run = subprocess.run(
            [str(console_exe), "--smoke", str(out)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if run.returncode != 0:
            print(f"smoke: exe вернул {run.returncode}\n{run.stdout}\n{run.stderr}")
            return 1
        log = appdata / "OneCStarter" / "logs" / "onecstarter.log"
        if not log.is_file():
            print("smoke: лог не создан")
            return 1
        log_text = log.read_text("utf-8")
        if "окно показано" not in log_text:
            print("smoke: фаза «окно показано» не записана в лог")
            return 1
        # Явная (не косвенная через цель ярлыка) проверка sys.frozen в
        # собранном exe — задача 10, спека §3.3.
        if "smoke: frozen=True" not in log_text:
            print("smoke: лог не подтверждает sys.frozen == True в сборке")
            return 1
        lnk = out / "smoke.lnk"
        target = shortcut_target(lnk)
        if Path(target).resolve() != console_exe.resolve():
            print(f"smoke: цель ярлыка {target!r}, ожидался {console_exe}")
            return 1
        # Собранный exe обязан принять --autostart и завершиться штатно.
        # Это НЕ проверка тихого старта: `--smoke` разбирается раньше  # noqa: RUF003
        # (`__main__._dispatch`) и до ветки окна дело не доходит вовсе.
        # Проверяется ровно одно — новый ключ не ломает разбор аргументов
        # в сборке. Само поведение тихого старта покрыто тестом
        # `test_entry_point.py` и ручным прогоном при завершении вехи.
        quiet_appdata = Path(scratch) / "appdata-quiet"
        quiet_env = dict(env)
        quiet_env["APPDATA"] = str(quiet_appdata)
        quiet = subprocess.run(
            [str(console_exe), "--autostart", "--smoke", str(out)],
            env=quiet_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if quiet.returncode != 0:
            print(f"smoke: --autostart вернул {quiet.returncode}\n{quiet.stderr}")
            return 1
    print("smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
