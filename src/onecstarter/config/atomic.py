"""Атомарная запись пользовательских файлов 1С.

ibases.v8i параллельно перезаписывает штатный 1cestart.exe, поэтому запись
только через временный файл в том же каталоге + замена, с проверкой снапшота.
Между проверкой снапшота и заменой остаётся окно гонки: слой services
обрабатывает ExternalChangeError слиянием и повтором. Блокировок нет.
"""  # noqa: RUF002

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ExternalChangeError(Exception):
    """Файл изменён извне после того, как мы его прочитали."""  # noqa: RUF002


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    digest: str


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_with_snapshot(path: Path) -> tuple[bytes, FileSnapshot]:
    data = path.read_bytes()
    return data, FileSnapshot(path=path, digest=_digest(data))


def atomic_write(path: Path, data: bytes) -> None:
    """Записать `data` в `path` через временный файл + замену.

    На Windows `Path.replace` может выбросить `PermissionError`, если другой
    процесс держит `path` открытым; повторные попытки — забота вызывающего
    слоя (services), не этой функции.
    """  # noqa: RUF002
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_if_unchanged(path: Path, data: bytes, snapshot: FileSnapshot) -> None:
    try:
        current = path.read_bytes()
    except FileNotFoundError as error:
        raise ExternalChangeError(f"{path} удалён после чтения") from error
    if _digest(current) != snapshot.digest:
        raise ExternalChangeError(f"{path} изменён извне после чтения")
    atomic_write(path, data)
