"""Слежение за ibases.v8i. Живёт в ui — инвариант 1 (Qt вне ядра запрещён).

Спека 4a, §5: watcher обязан переживать полную перезапись (наша запись и
перезапись платформой — [Ф] скил v8i-format). [Ф] 07.08.2026, замер на Windows +
PySide6/Qt 6.11.1: после os.replace QFileSystemWatcher файл не теряет — Windows-бэкенд
(ReadDirectoryChangesW) следит через каталог и видит изменение. Потеря watch после
замены — известное поведение inotify-бэкенда (Linux). [Д]

Переподписка в _touched — защитная страховка на случай смены бэкенда/версии Qt и для
файла, который не существует при инициализации. Не исправление наблюдаемой потери.

Дребезг (несколько событий на одну перезапись) гасится одноразовым таймером.
"""  # noqa: RUF002

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


class FileWatcher(QObject):
    changed = Signal()

    def __init__(self, path: Path, debounce_ms: int = 200, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._watcher = QFileSystemWatcher(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.changed)
        self._watcher.fileChanged.connect(self._touched)
        self._watcher.directoryChanged.connect(self._touched)
        self._resubscribe()

    def _resubscribe(self) -> None:
        directory = str(self._path.parent)
        if self._path.parent.is_dir() and directory not in self._watcher.directories():
            self._watcher.addPath(directory)
        if self._path.is_file() and str(self._path) not in self._watcher.files():
            self._watcher.addPath(str(self._path))

    def _touched(self, _path: str) -> None:
        self._resubscribe()
        self._timer.start()
