"""Панель хода выполнения сценария (спека v4, §7.6): таблица «база × шаг», отмена, журнал.

Панель знает о запуске только `RunInfo` (без паролей) и события исполнителя, уже
доставленные в главный поток контроллером.
"""  # noqa: RUF002

import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_params import Level
from onecstarter.domain.operations import (
    BaseOutcome,
    BaseResult,
    RunRecord,
    StepResult,
    StepStatus,
    decode_log,
    failed_keys,
)
from onecstarter.domain.operations_text import (
    RUNNING,
    WAITING,
    outcome_text,
    runs_word,
    step_cell,
    step_title,
)
from onecstarter.services.operations_runner import (
    BaseFinished,
    RunEvent,
    StepFinished,
    StepStarted,
    step_log_path,
)
from onecstarter.ui.bases.panel import open_in_explorer
from onecstarter.ui.components import Note, hint_label
from onecstarter.ui.dialogs.buttons import (
    DANGER,
    PRIMARY,
    ButtonKind,
    Choice,
    ChoiceDialog,
    mark_button,
    russian_button_box,
)
from onecstarter.ui.ops.controller import OperationsController, RunBase, RunInfo
from onecstarter.ui.theme import DARK, Palette

IDLE_TEXT = "В этом сеансе сценарии не запускались"  # noqa: RUF001
SOFT_LABEL = "Отменить после текущего шага"
HARD_LABEL = "Прервать сейчас"
LOG_LABEL = "Открыть журнал"
OUTPUT_LABEL = "Открыть каталог выгрузки"
RETRY_LABEL = "Повторить для ошибочных"
SOFT_SUFFIX = " · отмена после текущего шага"
NO_LOG_TEXT = "Журнал шага пуст или ещё не создан."
NOT_STARTED = "—"
NOT_FINISHED = "не завершена"
ABORT_TITLE = "Прервать сейчас?"
ABORT_TEXT = "Процессы Конфигуратора будут сняты, остальные шаги не запустятся."
ABORT_WARNING = (
    "Если прервать загрузку .dt или обновление базы данных, база может остаться в "
    "неработоспособном состоянии."
)
ABORT_LABEL = "Прервать"
KEEP_LABEL = "Продолжить выполнение"
_SUMMARY = (
    (BaseOutcome.OK, "готово"),
    (BaseOutcome.FAILED, "с ошибкой"),  # noqa: RUF001
    (BaseOutcome.INTERRUPTED, "прервано"),
    (BaseOutcome.CANCELLED, "отменено"),
    (BaseOutcome.NOT_READY, "пропущено"),
)


class Tone(Enum):
    """Цвет ячейки по смыслу; значение — имя роли палитры (мокап `.ok/.err/.run/.wait`)."""

    OK = "running"
    ERROR = "problem"
    RUNNING = "info"
    WARNING = "warning"
    MUTED = "text_dim"


def step_tone(result: StepResult | None, running: bool) -> Tone:
    if result is None:
        return Tone.RUNNING if running else Tone.MUTED
    if result.status is StepStatus.OK:
        return Tone.OK
    if result.status is StepStatus.SKIPPED:
        return Tone.MUTED
    return Tone.ERROR


_OUTCOME_TONES = {
    BaseOutcome.OK: Tone.OK,
    BaseOutcome.FAILED: Tone.ERROR,
    BaseOutcome.INTERRUPTED: Tone.ERROR,
    BaseOutcome.CANCELLED: Tone.WARNING,
    BaseOutcome.NOT_READY: Tone.MUTED,
}


def outcome_tone(outcome: BaseOutcome) -> Tone:
    return _OUTCOME_TONES[outcome]


def tone_colour(tone: Tone, palette: Palette) -> str:
    return str(getattr(palette, tone.value))


def build_abort_box(parent: QWidget | None) -> ChoiceDialog:
    """Подтверждение жёсткой отмены; по умолчанию — «Продолжить выполнение» (спека §7.6, мокап)."""
    return ChoiceDialog(
        parent,
        title=ABORT_TITLE,
        text=ABORT_TEXT,
        choices=(Choice("abort", ABORT_LABEL, DANGER), Choice("keep", KEEP_LABEL, PRIMARY)),
        default="keep",
        escape="keep",
        note=Note(Level.WARNING, ABORT_WARNING),
    )


def abort_confirmed(dialog: ChoiceDialog) -> bool:
    return dialog.chosen() == "abort"


def confirm_abort(parent: QWidget | None) -> bool:
    dialog = build_abort_box(parent)
    dialog.exec()
    return abort_confirmed(dialog)


def build_log_dialog(parent: QWidget | None, title: str, text: str) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    view = QPlainTextEdit(text)
    view.setObjectName("CodePreview")
    view.setReadOnly(True)
    buttons = russian_button_box(ButtonKind.CLOSE)
    buttons.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    layout.addWidget(view, 1)
    layout.addWidget(buttons)
    dialog.resize(760, 480)
    return dialog


def show_step_log(parent: QWidget | None, title: str, text: str) -> None:
    build_log_dialog(parent, title, text).exec()


class RunPanel(QWidget):
    retry_requested = Signal(object, object)  # Scenario, list[str]

    def __init__(
        self,
        controller: OperationsController,
        *,
        confirm_abort: Callable[[QWidget | None], bool] = confirm_abort,
        open_path: Callable[[str], bool] = open_in_explorer,
        show_log: Callable[[QWidget | None, str, str], None] = show_step_log,
        clock: Callable[[], float] = time.monotonic,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._confirm_abort = confirm_abort
        self._open_path = open_path
        self._show_log = show_log
        self._clock = clock
        self._palette = palette
        self._info: RunInfo | None = None
        self._record: RunRecord | None = None
        self._active = False
        self._aborted = False
        self._soft_requested = False
        self._rows: dict[str, int] = {}
        self._running: dict[tuple[str, int], float] = {}
        self._results: dict[tuple[str, int], StepResult] = {}
        self._outcomes: dict[str, BaseResult] = {}

        self._header = QLabel(IDLE_TEXT)
        self._header.setTextFormat(Qt.TextFormat.PlainText)  # имя сценария — пользовательское
        self._header.setWordWrap(True)
        self._table = QTableWidget(0, 0)
        self._table.setObjectName("OpsTable")
        self._table.setShowGrid(False)
        # В14: заголовок по центру обрезался с двух сторон — влево (мокап, с. 62).  # noqa: RUF003
        self._table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._soft = QPushButton(SOFT_LABEL)
        self._hard = QPushButton(HARD_LABEL)
        self._log = QPushButton(LOG_LABEL)
        self._output = QPushButton(OUTPUT_LABEL)
        self._retry = QPushButton(RETRY_LABEL)
        self._history = hint_label()  # мокап `.q` (стр. 372)
        mark_button(self._hard, DANGER)  # мокап `.btn.danger` (стр. 362)
        self._soft.clicked.connect(self._on_soft)
        self._hard.clicked.connect(self._on_hard)
        self._log.clicked.connect(self._open_log_dir)
        self._output.clicked.connect(self._open_output_dir)
        self._retry.clicked.connect(self._on_retry)
        # Мокап `.title` (стр. 21, 362): шапка — полоса surface с линией снизу.  # noqa: RUF003
        self._header_bar = QWidget()
        self._header_bar.setObjectName("PanelHeader")
        self._header_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top = QHBoxLayout(self._header_bar)
        top.setContentsMargins(12, 6, 12, 6)
        top.addWidget(self._header, 1)
        top.addWidget(self._soft)
        top.addWidget(self._hard)
        bottom = QHBoxLayout()
        bottom.addWidget(self._log)
        bottom.addWidget(self._output)
        bottom.addWidget(self._retry)
        bottom.addStretch(1)
        bottom.addWidget(self._history)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._header_bar)
        layout.addWidget(self._table, 1)
        layout.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.tick)
        controller.run_started.connect(self._on_started)
        controller.run_event.connect(self._on_event)
        controller.run_finished.connect(self._on_finished)
        self._refresh_buttons()
        self._refresh_history()

    def _header_text(self, column: int) -> str:
        item = self._table.horizontalHeaderItem(column)
        assert item is not None
        return item.text()

    def _cell(self, row: int, column: int) -> QTableWidgetItem:
        item = self._table.item(row, column)
        assert item is not None  # все ячейки созданы при старте запуска
        return item

    # -- чтение для тестов ---------------------------------------------------

    def header_text(self) -> str:
        return self._header.text()

    def history_text(self) -> str:
        return self._history.text()

    def column_titles(self) -> list[str]:
        return [self._header_text(column) for column in range(self._table.columnCount())]

    def cells(self) -> list[list[str]]:
        return [
            [self._cell(row, column).text() for column in range(self._table.columnCount())]
            for row in range(self._table.rowCount())
        ]

    def cell_tooltip(self, row: int, column: int) -> str:
        return self._cell(row, column).toolTip()

    def soft_button(self) -> QPushButton:
        return self._soft

    def hard_button(self) -> QPushButton:
        return self._hard

    def log_button(self) -> QPushButton:
        return self._log

    def output_button(self) -> QPushButton:
        return self._output

    def retry_button(self) -> QPushButton:
        return self._retry

    def timer_active(self) -> bool:
        return self._timer.isActive()

    def select_base(self, key: str) -> None:
        self._table.selectRow(self._rows[key])

    def table(self) -> QTableWidget:
        return self._table

    def header_bar(self) -> QWidget:
        return self._header_bar

    def header_tooltips(self) -> list[str]:
        items = (self._table.horizontalHeaderItem(c) for c in range(self._table.columnCount()))
        return [item.toolTip() if item is not None else "" for item in items]

    def cell_colour(self, row: int, column: int) -> str:
        return str(self._cell(row, column).foreground().color().name())

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        if self._info is not None:
            for base in self._info.bases:
                self._refresh_row(base)

    # -- события запуска ------------------------------------------------------

    def _on_started(self, info: RunInfo) -> None:
        self._info = info
        self._record = None
        self._active = True
        self._aborted = False
        self._soft_requested = False
        self._running = {}
        self._results = {}
        self._outcomes = {}
        catalog = self._controller.catalog
        steps = info.scenario.steps
        # Решение заказчика 6 (21.11.2026): короткий заголовок «N. /Команда», полное — подсказкой.
        titles = ["База", *(f"{n}. {step.command}" for n, step in enumerate(steps, 1)), "Итог"]
        self._table.clear()
        self._table.setColumnCount(len(titles))
        self._table.setHorizontalHeaderLabels(titles)
        for number, step in enumerate(steps, start=1):
            head = self._table.horizontalHeaderItem(number)
            if head is not None:
                head.setToolTip(f"{number}. {step_title(step, catalog)}")
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, len(steps) + 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(len(steps) + 1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setRowCount(len(info.bases))
        self._rows = {}
        for row, base in enumerate(info.bases):
            self._rows[base.key] = row
            for column in range(len(titles)):
                self._table.setItem(row, column, QTableWidgetItem())
            self._cell(row, 0).setText(base.name)
            self._refresh_row(base)
        self._refresh_header()
        self._refresh_buttons()
        self._timer.start()

    def _on_event(self, event: RunEvent) -> None:
        if self._info is None:
            return
        if isinstance(event, StepStarted):
            self._running[(event.key, event.index)] = self._clock()
            self._refresh_key(event.key)
        elif isinstance(event, StepFinished):
            self._running.pop((event.key, event.index), None)
            self._results[(event.key, event.index)] = event.result
            self._refresh_key(event.key)
        elif isinstance(event, BaseFinished):
            self._outcomes[event.result.key] = event.result
            for index, result in enumerate(event.result.steps):
                self._results.setdefault((event.result.key, index), result)
            self._refresh_key(event.result.key)

    def _on_finished(self, record: RunRecord | None) -> None:
        self._active = False
        self._record = record
        self._running = {}
        self._aborted = record is None
        self._timer.stop()
        if self._aborted and self._info is not None:
            for base in self._info.bases:
                self._refresh_row(base)
        self._refresh_header()
        self._refresh_buttons()
        self._refresh_history()

    def tick(self) -> None:
        if self._info is None:
            return
        for key in {key for key, _index in self._running}:
            self._refresh_key(key)

    # -- отрисовка -----------------------------------------------------------

    def _refresh_key(self, key: str) -> None:
        if self._info is None:
            return
        base = next((b for b in self._info.bases if b.key == key), None)
        if base is not None:
            self._refresh_row(base)

    def _paint(self, item: QTableWidgetItem, tone: Tone) -> None:
        item.setForeground(QColor(tone_colour(tone, self._palette)))

    def _refresh_row(self, base: RunBase) -> None:
        if self._info is None:
            return
        row = self._rows[base.key]
        outcome = self._outcomes.get(base.key)
        steps = len(self._info.scenario.steps)
        for index in range(steps):
            item = self._cell(row, index + 1)
            result = self._results.get((base.key, index))
            started = self._running.get((base.key, index))
            unreached = result is None and started is None
            if not base.ready or ((outcome is not None or self._aborted) and unreached):
                # Неготовая база и шаги, до которых дело не дошло (мягкая отмена, сбой запуска).
                item.setText(NOT_STARTED)
                item.setToolTip("")
                self._paint(item, Tone.MUTED)
                continue
            elapsed = self._clock() - started if started is not None else None
            item.setText(step_cell(result, elapsed))
            self._paint(item, step_tone(result, started is not None))
            failed = result is not None and result.status is not StepStatus.OK
            item.setToolTip(result.message if result is not None and failed else "")
        total = self._cell(row, steps + 1)
        if outcome is not None:
            total.setText(outcome_text(outcome))
            total.setToolTip("\n".join(outcome.problems))
            self._paint(total, outcome_tone(outcome.outcome))
        elif self._aborted:
            total.setText(NOT_FINISHED)
            total.setToolTip("")
            self._paint(total, Tone.WARNING)
        elif any(key == base.key for key, _index in self._running):
            total.setText(RUNNING)
            self._paint(total, Tone.RUNNING)
        else:
            total.setText(WAITING)
            self._paint(total, Tone.MUTED)

    def _refresh_header(self) -> None:
        info = self._info
        if info is None:
            self._header.setText(IDLE_TEXT)
            return
        name = info.scenario.name
        started = f"начато {info.started:%d.%m.%Y %H:%M}"
        if self._active:
            suffix = SOFT_SUFFIX if self._soft_requested else ""
            self._header.setText(f"Выполняется «{name}» · {started}{suffix}")
        elif self._record is None:
            self._header.setText(f"Запуск «{name}» сорван ошибкой программы")
        else:
            counts = [
                f"{title}: {count}"
                for outcome, title in _SUMMARY
                if (count := sum(1 for base in self._record.bases if base.outcome is outcome))
            ]
            self._header.setText(f"Завершён «{name}» · {started} · {', '.join(counts)}")

    def _refresh_buttons(self) -> None:
        info = self._info
        self._soft.setEnabled(self._active and not self._soft_requested)
        self._hard.setEnabled(self._active)
        self._log.setEnabled(info is not None)
        self._output.setEnabled(info is not None and any(base.output_dir for base in info.bases))
        self._retry.setEnabled(
            not self._active and self._record is not None and bool(failed_keys(self._record))
        )

    def _refresh_history(self) -> None:
        count = self._controller.history_count()
        self._history.setText(f"История: {count} {runs_word(count)}")

    # -- действия ------------------------------------------------------------

    def _on_soft(self) -> None:
        self._controller.cancel_soft()
        self._soft_requested = True
        self._refresh_header()
        self._refresh_buttons()

    def _on_hard(self) -> None:
        if self._confirm_abort(self):
            self._controller.cancel_hard()

    def _on_retry(self) -> None:
        if self._info is not None and self._record is not None:
            self.retry_requested.emit(self._info.scenario, list(failed_keys(self._record)))

    def _selected_base(self) -> RunBase | None:
        if self._info is None:
            return None
        row = self._table.currentRow()
        selected = bool(self._table.selectionModel().selectedRows())
        return self._info.bases[row] if selected and 0 <= row < len(self._info.bases) else None

    def _open_log_dir(self) -> None:
        if self._info is None:
            return
        base = self._selected_base()
        went = base is not None and base.ready and bool(base.logs_dir)
        self._open_path(base.logs_dir if base is not None and went else self._info.logs_dir)

    def _open_output_dir(self) -> None:
        if self._info is None:
            return
        base = self._selected_base()
        path = base.output_dir if base is not None else ""
        if not path:
            path = next((b.output_dir for b in self._info.bases if b.output_dir), "")
        if path:
            self._open_path(path)

    def _on_double_click(self, row: int, column: int) -> None:
        if self._info is None or not 1 <= column <= len(self._info.scenario.steps):
            return
        self.open_step_log(self._info.bases[row].key, column - 1)

    def open_step_log(self, key: str, index: int) -> None:
        if self._info is None:
            return
        base = next((b for b in self._info.bases if b.key == key), None)
        if base is None:
            return
        text = ""
        if base.logs_dir:
            try:
                text = decode_log(step_log_path(Path(base.logs_dir), index).read_bytes())
            except OSError:
                text = ""
        step = self._info.scenario.steps[index]
        title = step_title(step, self._controller.catalog)
        self._show_log(
            self, f"Журнал: «{base.name}», шаг {index + 1} — {title}", text.strip() or NO_LOG_TEXT
        )
