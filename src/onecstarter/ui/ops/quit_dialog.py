"""Вопрос о выходе при активном запуске сценария (спека v4, §6.6, §7.7; мокап, экран 7)."""  # noqa: RUF002

from PySide6.QtWidgets import QWidget

from onecstarter.ui.dialogs.buttons import DANGER, PRIMARY, Choice, ChoiceDialog
from onecstarter.ui.ops.quit_gate import QuitChoice as QuitChoice

QUIT_TITLE = "Выполняется сценарий"
WAIT_LABEL = "Дождаться шага и выйти"
ABORT_LABEL = "Прервать и выйти"
STAY_LABEL = "Не выходить"  # noqa: RUF001
_ANSWERS = {"wait": QuitChoice.WAIT, "abort": QuitChoice.ABORT}


def build_operations_quit_box(parent: QWidget | None, message: str) -> ChoiceDialog:
    """Мокап, экран 7: «Не выходить» слева; «Дождаться…» — главная и по умолчанию."""  # noqa: RUF002
    return ChoiceDialog(
        parent,
        title=QUIT_TITLE,
        text=message,
        choices=(
            Choice("stay", STAY_LABEL, left=True),
            Choice("wait", WAIT_LABEL, PRIMARY),
            Choice("abort", ABORT_LABEL, DANGER),
        ),
        default="wait",
        escape="stay",
    )


def read_quit_choice(dialog: ChoiceDialog) -> QuitChoice:
    return _ANSWERS.get(dialog.chosen() or "", QuitChoice.STAY)


def ask_operations_quit(parent: QWidget | None, message: str) -> QuitChoice:
    dialog = build_operations_quit_box(parent, message)
    dialog.exec()
    return read_quit_choice(dialog)
