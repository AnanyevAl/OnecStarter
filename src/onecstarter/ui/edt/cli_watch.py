"""Ожидание кода завершения команды CLI в потоке-демоне → сигнал Qt (спека §14.4).

Тот же приём, что у фоновых проб (`ui/background.py`): поток ждёт `Popen.wait()`,
результат уходит сигналом в главный поток, где `EdtView` зовёт `EdtCli.finish`.

«Прервать» (`EdtCli.interrupt`) закрывает хендл Job, а не хендл процесса:
kill-on-close гасит дерево, и `wait()` штатно возвращается с кодом убитого
процесса — сигнал приходит с числом, а `EdtCli.finish` его отбрасывает, потому
что run уже не в учёте. Ветка `except OSError` → `None` — страховка на случай
отказа самого ожидания, а не ожидаемый путь прерывания (уточнение M8
финального ревью плана 2).
"""  # noqa: RUF002

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from onecstarter.services.edt_cli import CliRun


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


class CliWatcher(QObject):
    # Сам `CliRun`, не id записи: после «Прервать» и повторного запуска на той же
    # записи запоздавший сигнал старого run не должен закрыть новый — слот
    # сверяет объект с живым run (находка ревью Task 6).  # noqa: RUF003
    finished = Signal(object, object)  # CliRun, int | None

    def __init__(
        self,
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._spawn = spawn

    def watch(self, run: CliRun) -> None:
        def wait() -> None:
            try:
                code: int | None = run.process.wait()
            except OSError:
                code = None
            self.finished.emit(run, code)

        self._spawn(wait)
