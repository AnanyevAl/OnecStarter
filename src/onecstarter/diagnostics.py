"""Лог, faulthandler и последнее окно ошибки — без Qt.

Работает до любого импорта ui: перехват в __main__ обязан поймать и отказ
самого импорта (спека T-04.6, §4.2 — «ModuleNotFoundError ушёл в никуда»,
§9 п. 4 спеки 4a). Содержимое лога — счётчики и длительности, без строк
соединения и путей баз (инвариант 5, спека §4.1).
"""

import ctypes
import faulthandler
import logging
import logging.handlers
import sys
from collections.abc import Mapping
from pathlib import Path

LOG_NAME = "onecstarter.log"
CRASH_NAME = "crash.log"
_MB_ICONERROR = 0x10
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def log_directory(env: Mapping[str, str]) -> Path:
    """Каталог лога: `%APPDATA%\\OneCStarter\\logs`."""
    return Path(env.get("APPDATA", ".")) / "OneCStarter" / "logs"


def setup_logging(env: Mapping[str, str]) -> Path | None:
    """Настроить лог; None — не вышло. Приложение важнее лога (спека §4.2)."""
    directory = log_directory(env)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            directory / LOG_NAME, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:
        # Консольный exe (OneCStarterc.exe): лог виден живьём — сценарий
        # «запустите консольный exe и пришлите вывод» (спека §4.3).
        mirror = logging.StreamHandler()
        mirror.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(mirror)
    return directory / LOG_NAME


def enable_faulthandler(env: Mapping[str, str]) -> None:
    """Падения нативного кода Qt — в crash.log. Файл остаётся открытым намеренно."""
    try:
        stream = (log_directory(env) / CRASH_NAME).open("a", encoding="utf-8")
        faulthandler.enable(stream)
    except OSError:
        pass


def show_fatal_error(message: str) -> None:
    """Системное окно без Qt: у оконной сборки нет ни консоли, ни stderr."""  # noqa: RUF002
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "OneCStarter", _MB_ICONERROR)
    except Exception:  # не Windows: лог уже записан, окна не будет
        pass
