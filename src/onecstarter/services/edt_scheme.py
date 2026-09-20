"""Каталог цветовых схем и запись схемы в рабочую область EDT (спека v3.2, §4).

Каталог — настройка `edt_schemes_dir`: файлы корня и подкаталогов первого уровня по
расширениям, чтение ленивое (`load`), ошибка разбора — `EdtError` с причиной, диалог
показывает её у строки. Рабочая область — два prefs-файла в
`<workspace>\\.metadata\\.plugins\\org.eclipse.core.runtime\\.settings` (третий — тема окна);
каждый пишется атомарно (инвариант 4), чужие ключи и перевод строки сохраняются
(`render_prefs`, инвариант 3). Кодировка — latin-1 (Java properties).

Занятость области проверяет вызывающий (статус «запущен», `cli_busy`), но сервис
переспрашивает через `is_busy` перед записью — защита от гонки со сканом (§4).
`OSError` наружу не выходит — только `EdtError` с путём и причиной (§7).
"""  # noqa: RUF002

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    EDITORS_PREFS,
    RGB,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    complete,
    parse_csi,
    parse_idea_jar,
    parse_idea_xml,
    parse_tmtheme,
    prefs_removals,
    prefs_updates,
    render_prefs,
    scheme_from_workspace_prefs,
    theme_prefs_update,
    to_csi,
)
from onecstarter.services.errors import EdtError

__all__ = [
    "BUSY_MESSAGE",
    "SCHEME_KINDS",
    "CatalogEntry",
    "SchemeCatalog",
    "WorkspaceSchemes",
    "save_csi",
]

SCHEME_KINDS: dict[str, str] = {
    ".csi": "csi",
    ".xml": "idea",
    ".icls": "idea",
    ".jar": "jar",
    ".tmtheme": "tmtheme",
}
BUSY_MESSAGE = "Закройте EDT: рабочая область занята"
READ_FAILED = "не удалось прочитать: {reason}"
WRITE_FAILED = "Не удалось записать {path}: {reason}"  # noqa: RUF001
_SETTINGS = Path(".metadata") / ".plugins" / "org.eclipse.core.runtime" / ".settings"


def _reason(error: Exception) -> str:
    return (getattr(error, "strerror", None) or str(error)) or error.__class__.__name__


@dataclass(frozen=True)
class CatalogEntry:
    name: str  # stem файла — подпись строки в диалоге
    path: Path
    kind: str  # значение SCHEME_KINDS


class SchemeCatalog:
    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)

    @property
    def directory(self) -> Path:
        return self._directory

    def exists(self) -> bool:
        return self._directory.is_dir()

    def entries(self) -> list[CatalogEntry]:
        """Корень и подкаталоги первого уровня; расширения без учёта регистра; по имени."""
        found: list[CatalogEntry] = []

        def add(path: Path) -> None:
            kind = SCHEME_KINDS.get(path.suffix.lower())
            if kind is not None and path.is_file():
                found.append(CatalogEntry(path.stem, path, kind))

        try:
            children = list(self._directory.iterdir())
        except OSError:
            return []
        for child in children:
            if child.is_dir():
                try:
                    for nested in child.iterdir():
                        add(nested)
                except OSError:
                    continue
            else:
                add(child)
        found.sort(key=lambda entry: (entry.name.casefold(), str(entry.path).casefold()))
        return found

    def load(self, entry: CatalogEntry) -> Scheme:
        try:
            data = entry.path.read_bytes()
        except OSError as error:
            raise EdtError(READ_FAILED.format(reason=_reason(error))) from error
        try:
            if entry.kind == "csi":
                name, colors = "", parse_csi(data.decode("utf-8-sig"))
            elif entry.kind == "idea":
                name, colors = parse_idea_xml(data.decode("utf-8-sig"))
            elif entry.kind == "jar":
                name, colors = parse_idea_jar(data)
            else:
                name, colors = parse_tmtheme(data.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as error:
            raise EdtError(READ_FAILED.format(reason=error)) from error
        return complete(name or entry.name, colors, str(entry.path))


def save_csi(path: Path, scheme: Scheme) -> None:
    """Записать схему в `.csi` атомарно; каталог создаётся."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, to_csi(scheme).encode("utf-8"))
    except OSError as error:
        raise EdtError(WRITE_FAILED.format(path=path, reason=_reason(error))) from error


class WorkspaceSchemes:
    def __init__(self, workspace: str, *, is_busy: Callable[[], bool] = lambda: False) -> None:
        self._settings_dir = Path(workspace) / _SETTINGS
        self._is_busy = is_busy

    @property
    def settings_dir(self) -> Path:
        return self._settings_dir

    def current(self, defaults: Mapping[str, RGB]) -> Scheme:
        """«Текущая»: значения из файлов, иначе `defaults` (файлов может не быть — штатно)."""
        return scheme_from_workspace_prefs(
            self._read(BSL_PREFS), self._read(EDITORS_PREFS), defaults
        )

    def apply(self, scheme: Scheme, theme: ThemeChoice) -> None:
        """Записать 22 цвета (и тему, если выбрана). Отказ при занятой области — до записи."""
        self._guard()
        updates = prefs_updates(scheme)
        for name in (BSL_PREFS, EDITORS_PREFS):
            self._write(name, render_prefs(self._read(name), updates[name]))
        self._write_theme(theme)

    def reset(self, theme: ThemeChoice) -> None:
        """«По умолчанию EDT»: снять наши ключи; файла нет — не создавать."""
        self._guard()
        removals = prefs_removals()
        for name in (BSL_PREFS, EDITORS_PREFS):
            existing = self._read(name)
            if existing:
                self._write(name, render_prefs(existing, {}, removals[name]))
        self._write_theme(theme)

    def _write_theme(self, theme: ThemeChoice) -> None:
        update = theme_prefs_update(theme)
        if update is not None:
            self._write(THEME_PREFS, render_prefs(self._read(THEME_PREFS), update))

    def _guard(self) -> None:
        if self._is_busy():
            raise EdtError(BUSY_MESSAGE)

    def _read(self, name: str) -> str:
        path = self._settings_dir / name
        try:
            return path.read_bytes().decode("latin-1")
        except FileNotFoundError:
            return ""
        except OSError as error:
            msg = f"Не удалось прочитать {path}: {_reason(error)}"  # noqa: RUF001
            raise EdtError(msg) from error

    def _write(self, name: str, text: str) -> None:
        path = self._settings_dir / name
        try:
            self._settings_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(path, text.encode("latin-1"))
        except OSError as error:
            raise EdtError(WRITE_FAILED.format(path=path, reason=_reason(error))) from error
