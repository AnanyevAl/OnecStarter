"""Консоль раздела «EDT» (спека v3, §14.5): сворачиваемая обёртка над `JournalPanel`.

Свёрнута по умолчанию — виден только заголовок; раскрывается вьюхой при запуске
команды; свёрнутая вручную остаётся свёрнутой до следующего запуска. Состояние
между сеансами не хранится.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from onecstarter.ui.servers.journal_panel import JournalPanel
from onecstarter.ui.theme import Palette

CONSOLE_TITLE = "Консоль"
STATE_RUNNING = "выполняется"
STATE_INTERRUPTED = "прервано"
STATE_NOT_STARTED = "не запущен"


def state_finished(code: int) -> str:
    return f"завершено, код {code}"


class EdtConsole(QWidget):
    interrupt_requested = Signal()
    open_journal_requested = Signal()
    open_result_requested = Signal()

    def __init__(self, *, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = False
        self._header = QToolButton()
        self._header.setAutoRaise(True)
        self._header.clicked.connect(self._toggle)
        self._title = QLabel("")
        self._state = QLabel(STATE_NOT_STARTED)
        self._state.setObjectName("SettingsNote")
        self._interrupt = QPushButton("Прервать")
        self._interrupt.clicked.connect(self.interrupt_requested)
        self._journal = QPushButton("Открыть журнал")
        self._journal.clicked.connect(self.open_journal_requested)
        self._result = QPushButton("Открыть результат")
        self._result.clicked.connect(self.open_result_requested)
        self._panel = JournalPanel(palette=palette)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._header)
        header.addWidget(self._title, 1)
        header.addWidget(self._state)
        header.addWidget(self._interrupt)
        header.addWidget(self._journal)
        header.addWidget(self._result)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self._panel)
        self.set_buttons(interrupt=False, journal=False, result=False)
        self._apply_expanded()

    # --- состояние -------------------------------------------------------

    def show_run(self, project_name: str, label: str, state: str, path: Path | None) -> None:
        # Заголовок собирается из непустых частей (задача 6: `project_name`/
        # `label` не всегда оба заданы) — пустая часть не оставляет висячий  # noqa: RUF003
        # разделитель " · ".
        title = " · ".join(part for part in (project_name, label) if part)
        self._title.setText(title)
        self._state.setText(state)
        self._panel.show_journal(project_name, path)

    def set_state(self, state: str) -> None:
        self._state.setText(state)

    def set_buttons(self, *, interrupt: bool, journal: bool, result: bool) -> None:
        self._interrupt.setVisible(interrupt)
        self._journal.setVisible(journal)
        self._result.setVisible(result)

    def expand(self) -> None:
        self._expanded = True
        self._apply_expanded()

    def collapse(self) -> None:
        self._expanded = False
        self._apply_expanded()

    def is_expanded(self) -> bool:
        return self._expanded

    def apply_palette(self, palette: Palette) -> None:
        self._panel.apply_palette(palette)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._apply_expanded()

    def _apply_expanded(self) -> None:
        self._header.setText(f"{CONSOLE_TITLE} {'▾' if self._expanded else '▸'}")
        self._panel.setVisible(self._expanded)

    # --- доступ ----------------------------------------------------------

    def header_button(self) -> QToolButton:
        return self._header

    def title_label(self) -> QLabel:
        return self._title

    def state_label(self) -> QLabel:
        return self._state

    def interrupt_button(self) -> QPushButton:
        return self._interrupt

    def journal_button(self) -> QPushButton:
        return self._journal

    def result_button(self) -> QPushButton:
        return self._result

    def journal_panel(self) -> JournalPanel:
        return self._panel
