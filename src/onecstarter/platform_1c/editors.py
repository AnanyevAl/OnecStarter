"""Поиск внешних редакторов (спека v3, §5): настройка → PATH → известные каталоги.

Известные каталоги — [Ф] спека §0 для пользовательской установки VS Code
и Antigravity; системная установка VS Code — [?]. Приоритет решает
`domain.edt.resolve_editor`; здесь — только сбор существующих кандидатов.
"""  # noqa: RUF002

import shutil
from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path

from onecstarter.domain.edt import EditorResolution, resolve_editor

__all__ = ["EDITOR_LABELS", "EditorKind", "find_editor", "known_locations"]


class EditorKind(Enum):
    VSCODE = "vscode"
    ANTIGRAVITY = "antigravity"


EDITOR_LABELS: dict[EditorKind, str] = {
    EditorKind.VSCODE: "VS Code",
    EditorKind.ANTIGRAVITY: "Antigravity",
}

_PATH_NAMES: dict[EditorKind, tuple[str, ...]] = {
    EditorKind.VSCODE: ("code.cmd", "code"),
    EditorKind.ANTIGRAVITY: ("antigravity-ide.cmd", "antigravity-ide"),
}


def known_locations(kind: EditorKind, env: Mapping[str, str]) -> list[Path]:
    local = Path(env.get("LOCALAPPDATA", ".")) / "Programs"
    if kind is EditorKind.VSCODE:
        return [
            local / "Microsoft VS Code" / "bin" / "code.cmd",
            Path(env.get("ProgramFiles", r"C:\Program Files")) / "Microsoft VS Code" / "bin" / "code.cmd",
        ]
    return [local / "Antigravity IDE" / "bin" / "antigravity-ide.cmd"]


def find_editor(
    kind: EditorKind,
    setting: str,
    env: Mapping[str, str],
    *,
    which: Callable[[str], str | None] = shutil.which,
    is_file: Callable[[Path], bool] = Path.is_file,
) -> EditorResolution:
    in_path: Path | None = None
    for name in _PATH_NAMES[kind]:
        hit = which(name)
        if hit:
            in_path = Path(hit)
            break
    known = [path for path in known_locations(kind, env) if is_file(path)]
    return resolve_editor(setting, bool(setting) and is_file(Path(setting)), in_path, known)
