"""Окно запуска сценария: выбор баз, готовность, пароли (спека v4, §7.5, §6.2, §6.3).

Готовность считает `OperationsController` в рабочем потоке; окно принимает только
результат своего последнего запроса. Введённые пароли живут в полях окна и в `RunPlan`
и стираются при закрытии (`forget`); при запуске окно стирает всё, кроме самого запроса.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_catalog import ArgSpec, Effect
from onecstarter.domain.cli_params import Level
from onecstarter.domain.operations import (
    BaseRef,
    Scenario,
    missing_inputs,
    padded,
    scenario_effect,
)
from onecstarter.domain.operations_text import (
    PASSWORD_ARGV_NOTE,
    PASSWORD_ONCE_NOTE,
    action_label,
    effect_notes,
    replace_warning,
)
from onecstarter.services.model import InfobaseItem
from onecstarter.services.operations_runner import PreparedBase, RunPlan, readiness_text
from onecstarter.ui.components import DialogFooter, FindingsList, Note
from onecstarter.ui.dialogs.buttons import DANGER, PRIMARY, mark_button
from onecstarter.ui.dialogs.launch_params import plural
from onecstarter.ui.ops.base_checklist import BaseChecklist
from onecstarter.ui.ops.controller import OperationsController, Prepared
from onecstarter.ui.ops.step_editor import browse_for_step_path
from onecstarter.ui.theme import DARK, Palette

CHECKING = "Проверка готовности…"
CHECK_FAILED = "Проверка готовности не удалась — подробности в журнале программы"
NO_BASES = "Отметьте базы слева"
PARALLEL_LABEL = "Запустить одновременно, а не по очереди"  # noqa: RUF001
REMEMBER_LABEL = "Запомнить отмеченные как список баз сценария"
BUILTIN_REMEMBER_NOTE = "Заготовку изменить нельзя — сделайте копию сценария"
HEADERS = ("База", "Версия", "Вход", "Пароль", "Пароль хранилища", "Готовность")
_NAME, _VERSION, _LOGIN, _PASSWORD, _REPOSITORY, _READY = range(6)
BASES_PANEL_WIDTH = 350
PASSWORD_COLUMN_WIDTH = 170
LOGIN_COLUMN_MAX = 150
# План В, Б3 (решение заказчика 21.11.2026): в ячейке — кратко, как в мокапе  # noqa: RUF003
# (стр. 330), причины — выносками под таблицей: при 980 px в ячейке они переносились
# почти по буквам. Выносок не больше пяти (решение заказчика 22.11.2026): при многих
# неготовых базах они сжимали бы таблицу до шапки.
READY_SKIPPED = "✗ будет пропущена"
UNNAMED_BASE = "база без имени"
REASONS_SHOWN = 5
MORE_REASONS = "и ещё {bases} — причины в подсказке ячейки «Готовность»"
# План В, Б3′ (решение заказчика 22.11.2026, живой замер на реальной машине:  # noqa: RUF003
# при 980×560 и 21 неготовой базе выноски и сообщения ниже сжали таблицу до шапки):  # noqa: RUF003
# выноски — в области прокрутки не выше REASONS_MAX_HEIGHT, таблица — не ниже шапки и
# TABLE_MIN_ROWS строк.
REASONS_MAX_HEIGHT = 96
TABLE_MIN_ROWS = 3


class _ReasonsScroll(QScrollArea):
    """Область прокрутки выносок причин (Б3′): `sizeHint` — высота содержимого при нынешней
    ширине, но не выше `REASONS_MAX_HEIGHT`; стандартные ~36 на 24 em `QScrollArea` не годятся."""  # noqa: RUF002

    def sizeHint(self) -> QSize:  # noqa: N802
        content = self.widget()
        if content is None:
            return super().sizeHint()
        width = self.viewport().width() or content.sizeHint().width()
        height = content.sizeHint().height()
        if content.hasHeightForWidth():
            height = max(height, content.heightForWidth(width))
        return QSize(content.sizeHint().width(), min(height, REASONS_MAX_HEIGHT))


def run_run_dialog(dialog: "RunDialog") -> bool:
    return dialog.exec() == QDialog.DialogCode.Accepted


@dataclass(frozen=True)
class RunRequest:
    plan: RunPlan = field(repr=False)
    parallel: bool
    remember: bool
    refs: tuple[BaseRef, ...]
    scenario: Scenario


class PasswordCell(QWidget):
    """Поле пароля строки таблицы и флажок «пустой» (пустой пароль — тоже пароль)."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("пароль")
        self._empty = QCheckBox("пустой")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._empty)
        self._edit.textChanged.connect(lambda _text: self.changed.emit())
        self._empty.toggled.connect(self._on_empty)

    def value(self) -> str | None:
        if self._empty.isChecked():
            return ""
        return self._edit.text() or None

    def set_text(self, text: str) -> None:
        self._edit.setText(text)

    def set_empty(self, on: bool) -> None:
        self._empty.setChecked(on)

    def state(self) -> tuple[str, bool]:
        return self._edit.text(), self._empty.isChecked()

    def restore(self, state: tuple[str, bool]) -> None:
        # Сигналы дочерних виджетов глушим сами: blockSignals родителя их не глушит.
        for widget in (self._edit, self._empty):
            widget.blockSignals(True)
        self._edit.setText(state[0])
        self._empty.setChecked(state[1])
        self._edit.setEnabled(not state[1])
        for widget in (self._edit, self._empty):
            widget.blockSignals(False)

    def clear(self) -> None:
        self.restore(("", False))

    def _on_empty(self, on: bool) -> None:
        self._edit.setEnabled(not on)
        if on:
            self._edit.blockSignals(True)
            self._edit.clear()
            self._edit.blockSignals(False)
        self.changed.emit()


class RunDialog(QDialog):
    def __init__(
        self,
        controller: OperationsController,
        scenario: Scenario,
        items: Sequence[InfobaseItem],
        *,
        checked: Sequence[str] = (),
        missing: Sequence[BaseRef] = (),
        choose_path: Callable[[QWidget, ArgSpec, str], str] = browse_for_step_path,
        delay_ms: int = 300,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Выполнить сценарий «{scenario.name}»")
        self._controller = controller
        self._scenario = scenario
        self._catalog = controller.catalog
        self._choose_path = choose_path
        self._effect = scenario_effect(scenario, self._catalog)
        self._bound = any(
            command is not None and command.bound
            for command in (self._catalog.command(step.command) for step in scenario.steps)
        )
        self._plan: RunPlan | None = None
        self._request: RunRequest | None = None
        self._generation: int | None = 0  # None — запрос ушёл, номер ещё не вернулся
        self._early: Prepared | None = None
        self._row_keys: list[str] = []
        self._cells: dict[str, PasswordCell] = {}
        self._repository_cells: dict[str, PasswordCell] = {}
        self._saved: dict[str, tuple[str, bool]] = {}
        self._saved_repository: dict[str, tuple[str, bool]] = {}
        self._inputs: dict[tuple[int, int], QLineEdit] = {}
        self._finished = False
        self._palette = palette

        self._checklist = BaseChecklist(items, checked=checked, missing=missing, palette=palette)
        self._table = QTableWidget(0, len(HEADERS))
        self._table.setObjectName("OpsTable")
        self._table.setHorizontalHeaderLabels(list(HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setColumnHidden(_REPOSITORY, not self._bound)
        # В13 (приёмка 21.11.2026): колонки по 100 px резали «Вход» и «Готовность».  # noqa: RUF003
        self._table.setShowGrid(False)
        self._table.setWordWrap(True)
        header = self._table.horizontalHeader()
        # Б3′: таблицу не сжать ниже шапки и TABLE_MIN_ROWS строк  # noqa: RUF003
        # (плюс горизонтальная полоса и рамка).
        self._table.setMinimumHeight(
            header.sizeHint().height()
            + TABLE_MIN_ROWS * self._table.verticalHeader().defaultSectionSize()
            + self._table.horizontalScrollBar().sizeHint().height()
            + 2 * self._table.frameWidth()
        )
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in (_NAME, _VERSION):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_LOGIN, QHeaderView.ResizeMode.Interactive)
        for column in (_PASSWORD, _REPOSITORY):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self._table.setColumnWidth(column, PASSWORD_COLUMN_WIDTH)
        header.setSectionResizeMode(_READY, QHeaderView.ResizeMode.Stretch)
        # Финальное ревью плана Б, F3: «Готовность» растянута и переносится — высота строк
        # следует за шириной колонки, а не только за заполнением таблицы (`_fill`).  # noqa: RUF003
        # [проверено] 21.11.2026 офскрин: режима ResizeToContents вертикального заголовка
        # мало — после сужения окна строки остаются прежней высоты; пересчёт
        # прямо в `sectionResized` тоже видит старую высоту, поэтому — следующим ходом
        # цикла событий (таблица — контекст: удалённую таблицу таймер не тронет).
        self._table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.sectionResized.connect(self._schedule_row_heights)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._reasons = FindingsList()
        self._reasons_area = _ReasonsScroll()
        self._reasons_area.setWidgetResizable(True)
        self._reasons_area.setFrameShape(QFrame.Shape.NoFrame)
        self._reasons_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._reasons_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._reasons_area.setMaximumHeight(REASONS_MAX_HEIGHT)
        self._reasons_area.setWidget(self._reasons)
        # `setWidget` включает заливку содержимого цветом Window системы: между
        # выносками были бы светлые полосы (ревью, I1). Фон — окна, заливку снимаем
        # и у содержимого, и у вьюпорта.  # noqa: RUF003
        self._reasons.setAutoFillBackground(False)
        self._reasons_area.viewport().setAutoFillBackground(False)
        self._reasons_area.setVisible(False)
        self._warning = FindingsList()
        self._notes = FindingsList()
        self._parallel = QCheckBox(PARALLEL_LABEL)
        self._remember = QCheckBox(REMEMBER_LABEL)
        if scenario.builtin:
            self._remember.setEnabled(False)
            self._remember.setToolTip(BUILTIN_REMEMBER_NOTE)
        self._action = QPushButton()
        self._cancel = QPushButton("Отмена")
        self._action.clicked.connect(self._run)
        self._cancel.clicked.connect(self.reject)
        replacing = self._effect is Effect.REPLACES
        # Заменяющий сценарий: Enter не запускает (спека §7.5).
        self._action.setAutoDefault(not replacing)
        self._cancel.setAutoDefault(replacing)
        (self._cancel if replacing else self._action).setDefault(True)
        # Решение заказчика 1, мокап (стр. 338, 352): у заменяющего сценария  # noqa: RUF003
        # действие — опасное, «Отмена» — главная (и по умолчанию: Enter не запускает, спека §7.5).
        mark_button(self._action, DANGER if replacing else PRIMARY)
        mark_button(self._cancel, PRIMARY if replacing else None)

        inputs = QFormLayout()
        for step_index, arg_index in missing_inputs(scenario, self._catalog):
            command = self._catalog.command(scenario.steps[step_index].command)
            assert command is not None  # missing_inputs пропускает неизвестные команды
            arg = command.args[arg_index]
            edit = QLineEdit()
            edit.textChanged.connect(lambda _text: self._schedule())
            button = QPushButton("…")
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, e=edit, a=arg: self._browse(e, a))
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(edit, 1)
            row_layout.addWidget(button)
            inputs.addRow(f"Шаг {step_index + 1} — {arg.label or 'файл'}", row)
            self._inputs[(step_index, arg_index)] = edit

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(inputs)
        right_layout.addWidget(self._table, 1)
        right_layout.addWidget(self._reasons_area)
        right_layout.addWidget(self._status)
        right_layout.addWidget(self._warning)
        right_layout.addWidget(self._notes)
        right_layout.addWidget(self._parallel)
        right_layout.addWidget(self._remember)
        self._footer = DialogFooter()
        self._footer.add_right(self._action)
        self._footer.add_right(self._cancel)
        splitter = QSplitter()
        splitter.addWidget(self._checklist)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([BASES_PANEL_WIDTH, 630])  # мокап, стр. 309
        content = QVBoxLayout()
        content.setContentsMargins(10, 10, 10, 8)
        content.addWidget(splitter, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content, 1)
        layout.addWidget(self._footer)
        self.resize(980, 560)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._request_prepare)
        self._checklist.changed.connect(self._schedule)
        controller.prepared.connect(self._on_prepared)
        self._refresh_notes()
        self._schedule()

    # -- чтение для вызывающего и тестов ------------------------------------

    def outcome(self) -> RunRequest | None:
        return self._request

    def forget(self) -> None:
        """Стереть план, запрос и введённые пароли: окно больше ничего секретного не держит."""
        self._request = None
        self._wipe()

    def _wipe(self) -> None:
        """Стереть всё, кроме запроса: план, поля паролей и сохранённые состояния."""
        self._plan = None
        self._saved.clear()
        self._saved_repository.clear()
        for cell in (*self._cells.values(), *self._repository_cells.values()):
            cell.clear()

    def checklist(self) -> BaseChecklist:
        return self._checklist

    def action_button(self) -> QPushButton:
        return self._action

    def cancel_button(self) -> QPushButton:
        return self._cancel

    def parallel_checkbox(self) -> QCheckBox:
        return self._parallel

    def remember_checkbox(self) -> QCheckBox:
        return self._remember

    def password_cell(self, key: str) -> PasswordCell | None:
        return self._cells.get(key)

    def repository_cell(self, key: str) -> PasswordCell | None:
        return self._repository_cells.get(key)

    def repository_column_visible(self) -> bool:
        return not self._table.isColumnHidden(_REPOSITORY)

    def table_rows(self) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in range(self._table.rowCount()):
            texts: list[str] = []
            for column in (_NAME, _VERSION, _LOGIN, _READY):
                item = self._table.item(row, column)
                texts.append(item.text() if item is not None else "")
            rows.append(texts)
        return rows

    def status_text(self) -> str:
        return self._status.text()

    def notes_text(self) -> str:
        return "\n".join(self._notes.texts())

    def reasons_text(self) -> str:
        return "\n".join(label.text() for label in self._reasons.labels())

    def reasons_list(self) -> FindingsList:
        return self._reasons

    def reasons_area(self) -> QScrollArea:
        return self._reasons_area

    def warning_text(self) -> str:
        return "\n".join(self._warning.texts())

    def table(self) -> QTableWidget:
        return self._table

    def notes_list(self) -> FindingsList:
        return self._notes

    def warning_list(self) -> FindingsList:
        return self._warning

    def footer_hint_text(self) -> str:
        return self._footer.hint_text()

    def set_input(self, step: int, arg: int, text: str) -> None:
        self._inputs[(step, arg)].setText(text)

    def refresh_now(self) -> None:
        self._timer.stop()
        self._request_prepare()

    # -- готовность ----------------------------------------------------------

    def _schedule(self) -> None:
        self._invalidate()
        # Результат запроса, ушедшего до правки, описывает прежний набор: не принимать.
        self._generation = -1
        self._timer.start()

    def _invalidate(self) -> None:
        self._plan = None
        self._status.setText(CHECKING)
        self._refresh_action()

    def _effective_scenario(self) -> Scenario:
        steps = list(self._scenario.steps)
        for (step_index, arg_index), edit in self._inputs.items():
            command = self._catalog.command(steps[step_index].command)
            if command is None:
                continue
            values = list(padded(steps[step_index].values, command.args))
            values[arg_index] = edit.text().strip() or None
            steps[step_index] = replace(steps[step_index], values=tuple(values))
        return replace(self._scenario, steps=tuple(steps))

    def _inputs_filled(self) -> bool:
        return all(edit.text().strip() for edit in self._inputs.values())

    @staticmethod
    def _typed(
        cells: Mapping[str, PasswordCell],
        saved: Mapping[str, tuple[str, bool]],
        keys: Sequence[str],
    ) -> dict[str, str]:
        """Пароли, которые показывают поля, — живые или сохранённые при снятой отметке."""
        typed: dict[str, str] = {}
        for key in keys:
            cell = cells.get(key)
            if cell is not None:
                value = cell.value()
            elif key in saved:
                text, empty = saved[key]
                value = "" if empty else (text or None)
            else:
                value = None
            if value is not None:
                typed[key] = value
        return typed

    def _request_prepare(self) -> None:
        keys = self._checklist.checked_keys()
        self._invalidate()
        if not keys:
            self._generation = -1  # результаты прежних запросов больше не нужны
            self._fill((), {})
            self._status.setText(NO_BASES)
            return
        self._generation = None
        self._early = None
        generation = self._controller.request_prepare(
            self._effective_scenario(),
            keys,
            self._typed(self._cells, self._saved, keys),
            self._typed(self._repository_cells, self._saved_repository, keys),
        )
        self._generation = generation
        early, self._early = self._early, None
        if early is not None and early.generation == generation:
            self._apply(early)

    def _on_prepared(self, result: Prepared) -> None:
        if self._generation is None:
            # Результат пришёл раньше, чем вернулся номер запроса (синхронное порождение).
            self._early = result
            return
        if result.generation == self._generation:
            self._apply(result)

    def _apply(self, result: Prepared) -> None:
        if result.plan is None:
            self._plan = None
            self._status.setText(CHECK_FAILED)
            # Причины прошлого расчёта не выдаём за нынешние (предпроверка, п. 18).
            self._set_reasons([])
            self._refresh_action()
            return
        self._plan = result.plan
        self._fill(result.plan.bases, result.versions)
        self._status.setText("")
        self._refresh_action()

    # -- таблица -------------------------------------------------------------

    def _fill(self, bases: Sequence[PreparedBase], versions: Mapping[str, str]) -> None:
        keys = [base.key for base in bases]
        if keys != self._row_keys:
            # Набор баз сменился: строки строятся заново, введённое — переносится.  # noqa: RUF003
            self._saved.update({key: cell.state() for key, cell in self._cells.items()})
            self._saved_repository.update(
                {key: cell.state() for key, cell in self._repository_cells.items()}
            )
            self._cells = {}
            self._repository_cells = {}
            self._table.setRowCount(0)
            self._table.setRowCount(len(bases))
            for row in range(len(bases)):
                for column in (_NAME, _VERSION, _LOGIN, _READY):
                    self._table.setItem(row, column, QTableWidgetItem())
            self._row_keys = keys
        for row, base in enumerate(bases):
            self._update_row(row, base, versions.get(base.key, ""))
        hint = self._table.sizeHintForColumn(_LOGIN)
        self._table.setColumnWidth(_LOGIN, min(max(hint, 60), LOGIN_COLUMN_MAX))
        self._table.resizeRowsToContents()
        self._refresh_notes()
        self._refresh_reasons(bases)

    def _schedule_row_heights(self, column: int, _old: int, _new: int) -> None:
        if column == _READY:
            QTimer.singleShot(0, self._table, self._table.resizeRowsToContents)

    def _update_row(self, row: int, base: PreparedBase, version: str) -> None:
        if base.credentials is None:
            login = "без пользователя"
        elif base.needs_password is not None:
            login = f"{base.credentials.login} · пароль не сохранён"
        else:
            login = base.credentials.login
        texts = readiness_text(base)
        ready = "✓" if base.ready else READY_SKIPPED
        for column, text in (
            (_NAME, base.name),
            (_VERSION, version),
            (_LOGIN, login),
            (_READY, ready),
        ):
            item = self._table.item(row, column)
            if item is not None:
                item.setText(text)
        login_item = self._table.item(row, _LOGIN)
        if login_item is not None:
            needs = base.needs_password is not None
            login_item.setForeground(QColor(self._palette.warning if needs else self._palette.text))
            login_item.setToolTip(login)
        ready_item = self._table.item(row, _READY)
        if ready_item is not None:
            ready_item.setToolTip("\n".join(texts))
            ready_item.setForeground(
                QColor(self._palette.running if base.ready else self._palette.problem)
            )
        self._ensure_cell(
            row, _PASSWORD, base.key, base.needs_password is not None, self._cells, self._saved
        )
        self._ensure_cell(
            row,
            _REPOSITORY,
            base.key,
            base.needs_repository_password,
            self._repository_cells,
            self._saved_repository,
        )

    def _ensure_cell(
        self,
        row: int,
        column: int,
        key: str,
        needed: bool,
        cells: dict[str, PasswordCell],
        saved: dict[str, tuple[str, bool]],
    ) -> None:
        if key in cells or not (needed or key in saved):
            return
        cell = PasswordCell()
        if key in saved:
            cell.restore(saved.pop(key))
        cell.changed.connect(self._schedule)
        self._table.setCellWidget(row, column, cell)
        cells[key] = cell

    # -- кнопки и подписи ----------------------------------------------------

    def _ready_count(self) -> int:
        return sum(1 for base in self._plan.bases if base.ready) if self._plan is not None else 0

    def _refresh_action(self) -> None:
        ready = self._ready_count()
        self._action.setText(action_label(self._effect, ready))
        self._action.setEnabled(self._plan is not None and ready > 0 and self._inputs_filled())
        replacing = self._effect is Effect.REPLACES and ready > 0
        self._warning.set_notes(
            [Note(Level.ERROR, replace_warning(ready), lead=True)] if replacing else []
        )

    def _refresh_reasons(self, bases: Sequence[PreparedBase]) -> None:
        # Имя базы, которой нет в списке, — из сохранённого списка сценария
        # (мокап, стр. 330): имя `PreparedBase` для неё пусто. Предпроверка, п. 17.
        names = {ref.key: ref.name for ref in self._checklist.checked_refs()}
        notes: list[Note] = []
        for base in bases:
            if base.ready:
                continue
            label = base.name or names.get(base.key, "") or UNNAMED_BASE
            texts = readiness_text(base)
            notes.append(Note(Level.ERROR, f"{label}: {'; '.join(texts)}" if texts else label))
        if len(notes) > REASONS_SHOWN:
            hidden = len(notes) - REASONS_SHOWN
            more = MORE_REASONS.format(bases=plural(hidden, "база", "базы", "баз"))
            notes = [*notes[:REASONS_SHOWN], Note(Level.ERROR, more)]
        self._set_reasons(notes)

    def _set_reasons(self, notes: Sequence[Note]) -> None:
        self._reasons.set_notes(notes)
        # `FindingsList` прячет себя при пустом наборе — область тоже.
        self._reasons_area.setVisible(bool(notes))

    def _refresh_notes(self) -> None:
        # Мокап, экран 5: `.msg` (что делают шаги) и `.msg.info` (пароль в командной строке).
        notes = [Note(Level.WARNING, text) for text in effect_notes(self._scenario, self._catalog)]
        with_passwords = bool(self._cells or self._repository_cells)
        if with_passwords:
            notes.append(Note(Level.INFO, PASSWORD_ARGV_NOTE))
        self._notes.set_notes(notes)
        self._footer.set_hint(PASSWORD_ONCE_NOTE if with_passwords else "")

    def _browse(self, edit: QLineEdit, arg: ArgSpec) -> None:
        chosen = self._choose_path(self, arg, edit.text())
        if chosen:
            edit.setText(chosen.replace("/", "\\"))

    def _run(self) -> None:
        plan = self._plan
        if plan is None or not self._action.isEnabled():
            return
        # Вторая линия защиты: план обязан быть для текущих баз и сценария.
        if [base.key for base in plan.bases] != self._checklist.checked_keys():
            return
        if plan.scenario != self._effective_scenario():
            return
        self._request = RunRequest(
            plan,
            self._parallel.isChecked(),
            self._remember.isChecked() and self._remember.isEnabled(),
            tuple(self._checklist.checked_refs()),
            self._effective_scenario(),
        )
        self.accept()

    def done(self, code: int) -> None:
        if not self._finished:  # закрытие уже закрытого окна зовёт `done` повторно
            self._finished = True
            self._timer.stop()
            self._controller.prepared.disconnect(self._on_prepared)
        if code == QDialog.DialogCode.Accepted:
            self._wipe()  # у окна остаётся только запрос, который отдаёт `outcome`  # noqa: RUF003
        else:
            self.forget()
        super().done(code)
