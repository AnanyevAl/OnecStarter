"""diagnostics: лог и перехват — без Qt, до окна."""

import logging
from pathlib import Path

from onecstarter import diagnostics


def _cleanup_root() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def test_setup_logging_creates_rotating_file(tmp_path: Path) -> None:
    try:
        path = diagnostics.setup_logging({"APPDATA": str(tmp_path)})
        assert path == tmp_path / "OneCStarter" / "logs" / "onecstarter.log"
        assert path is not None
        logging.getLogger("onecstarter.test").info("строка")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert "строка" in path.read_text(encoding="utf-8")
    finally:
        _cleanup_root()


def test_setup_logging_survives_unwritable_directory(tmp_path: Path) -> None:
    blocker = tmp_path / "APPDATA"
    # encoding обязателен: по умолчанию write_text берёт ANSI-кодировку
    # машины, и на en-US runner (cp1252) кириллица падает UnicodeEncodeError.
    blocker.write_text("файл на месте каталога", encoding="utf-8")
    try:
        assert diagnostics.setup_logging({"APPDATA": str(blocker)}) is None
    finally:
        _cleanup_root()
