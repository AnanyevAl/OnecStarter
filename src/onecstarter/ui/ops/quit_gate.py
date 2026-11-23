"""Выход из программы при активном запуске сценария (спека v4, §6.6, §7.7).

Автомат без Qt-зависимостей: окружение подаётся вызываемыми объектами, поэтому
все ветки проверяются быстрыми тестами без сборки окна.
"""

from collections.abc import Callable
from enum import Enum


class QuitChoice(Enum):
    STAY = "stay"
    WAIT = "wait"
    ABORT = "abort"


class QuitGate:
    """Состояние «выход отложен до конца запуска».

    Вызывающий (`confirm_quit` окна) зовёт `check()` после вопросов о серверах и CLI:
    `True` — выходить можно сейчас, и тогда вызывающий сам отмечает выход в журналах;
    `False` — выход отложен или отменён. `consented` — согласие уже получено
    (`on_run_finished` отметил выход и запросил закрытие): повторный проход
    `closeEvent` через `confirm_quit` ничего не спрашивает и ничего не отмечает.
    """  # noqa: RUF002

    def __init__(
        self,
        *,
        running: Callable[[], bool],
        question: Callable[[], str],
        ask: Callable[[str], QuitChoice],
        cancel_soft: Callable[[], None],
        cancel_hard: Callable[[], None],
        revoke_soft: Callable[[], None],
        finalize: Callable[[], None],
        quit_app: Callable[[], None],
        show_window: Callable[[], None],
        get_title: Callable[[], str],
        set_title: Callable[[str], None],
        wait_title: str,
    ) -> None:
        self._running = running
        self._question = question
        self._ask = ask
        self._cancel_soft = cancel_soft
        self._cancel_hard = cancel_hard
        self._revoke_soft = revoke_soft
        self._finalize = finalize
        self._quit_app = quit_app
        self._show_window = show_window
        self._get_title = get_title
        self._set_title = set_title
        self._wait_title = wait_title
        self._saved_title: str | None = None
        self.pending = False
        self.consented = False

    def _restore_title(self) -> None:
        if self._saved_title is not None:
            self._set_title(self._saved_title)
            self._saved_title = None

    def check(self) -> bool:
        if self.consented or not self._running():
            return True
        choice = self._ask(self._question())
        if not self._running():
            # Запуск закончился, пока был открыт вопрос: ждать нечего. Сигнал конца
            # пришёл во вложенном цикле событий и ничего не отметил.
            if choice is QuitChoice.STAY:
                if self.pending:
                    self._revoke_soft()
                self.pending = False
                self._restore_title()
                return False
            return True
        if choice is QuitChoice.STAY:
            # «Не выходить» отменяет и отложенный выход; отмену, поданную выходом,  # noqa: RUF003
            # снимаем (Р4); отмену кнопкой панели контроллер не снимет.  # noqa: RUF003
            if self.pending:
                self._revoke_soft()
            self.pending = False
            self._restore_title()
            return False
        self.pending = True
        if choice is QuitChoice.ABORT:
            self._cancel_hard()
        else:
            self._cancel_soft()
        if self._saved_title is None:
            self._saved_title = self._get_title()
        self._set_title(self._wait_title)
        self._show_window()
        return False

    def on_run_started(self) -> None:
        self.pending = False
        self._restore_title()

    def on_run_finished(self, _record: object = None) -> None:
        if not self.pending:
            return
        self.pending = False
        self.consented = True
        self._finalize()
        self._quit_app()
