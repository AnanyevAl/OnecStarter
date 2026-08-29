"""Журнал профиля: ротация запусков и запись событий.

Два писателя одного файла: наши события в UTF-8 и захваченный stdout дерева процессов.
Наш канал (UTF-8 со временными метками); платформа пишет своё (may contain various
encodings). При чтении tail используется errors="replace", чтобы не сломаться на смешанных
кодировках ([Ф] А1/А4 T-09). Ротация сохраняет прошлый запуск (спека §12.6): текущий
→ прошлый; древний прошлый затирается.

Два независимых писателя одного файла раньше могли столкнуться: ребёнку
(`platform_1c/server_spawn.py::spawn_server`) передавался хендл, открытый
`Path.open("ab")`, с СОБСТВЕННЫМ файловым указателем, застывшим на
позиции конца файла в момент `spawn`, — запись ребёнка по этому хендлу
затирала любое событие `append_event`, дописанное с тех пор ОТДЕЛЬНЫМ
хендлом (находка 1 ручного чек-листа T-10, Critical, [Ф] 29.08.2026,
`.superpowers/sdd/2026-08-28-v2-servers-journal/manual-checklist.md`).
С правкой волны исправлений 29.08.2026 ребёнок пишет хендлом с правом
`FILE_APPEND_DATA` (без `FILE_WRITE_DATA`, `_open_append_shared`
в `server_spawn.py`) — такая запись ОС атомарно направляет в фактический
конец файла независимо от указателя хендла, затирание между двумя
писателями больше невозможно.
"""  # noqa: RUF002

from datetime import datetime
from pathlib import Path

__all__ = [
    "append_event",
    "journal_path",
    "previous_journal_path",
    "rotate_journal",
]


def journal_path(logs_dir: Path, profile_id: str) -> Path:
    """Путь к текущему журналу профиля."""
    return logs_dir / f"{profile_id}.log"


def previous_journal_path(logs_dir: Path, profile_id: str) -> Path:
    """Путь к журналу предыдущего запуска профиля."""
    return logs_dir / f"{profile_id}.1.log"


def rotate_journal(logs_dir: Path, profile_id: str) -> None:
    """Ротировать журнал: текущий → прошлый (старый прошлый затирается).

    Если текущий журнал не существует — no-op. Создаёт logs_dir если её нет.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    current = journal_path(logs_dir, profile_id)
    if not current.exists():
        return
    previous = previous_journal_path(logs_dir, profile_id)
    current.replace(previous)


def append_event(path: Path, text: str, when: datetime) -> None:
    """Дозапись события в журнал: строка со временной меткой в UTF-8.

    Формат: "[HH:MM:SS] текст\\n". Создаёт каталог и файл при необходимости.
    Ошибки ОС пробиваются наружу (журнал не важнее работы).
    """  # noqa: RUF002
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{when:%H:%M:%S}] {text}\n"
    with path.open(mode="a", encoding="utf-8") as f:
        f.write(line)
