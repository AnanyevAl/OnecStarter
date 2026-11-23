"""Раздел «Операции»: сценарии пакетных операций Конфигуратора (спека v4, §7.4).

Каждая правка сценария сразу пишется в `operations.json` через `OperationsController`;
отказ записи показывается сообщением, показ откатывается к сохранённому. Заготовки
только читаются. Модальные окна показывают функции-параметры — тесты их подменяют.
"""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_catalog import Catalog, Effect
from onecstarter.domain.operations import (
    BaseRef,
    Scenario,
    Step,
    SubstitutionContext,
    sanitize_component,
    scenario_effect,
)
from onecstarter.domain.operations_text import preview_arguments, step_summary, step_title
from onecstarter.security.secrets import redact_arguments
from onecstarter.services.errors import ServicesError
from onecstarter.services.model import InfobaseItem
from onecstarter.services.operations_runner import BUSY_TEXT
from onecstarter.ui.command_line import CommandLineView, base_length_through
from onecstarter.ui.components import Box, bold_font, dim_label, hint_label, mono_span
from onecstarter.ui.dialogs.buttons import PRIMARY, ask_confirmation, mark_button
from onecstarter.ui.errors import show_service_error
from onecstarter.ui.ops.base_checklist import BaseListDialog, run_base_list_dialog
from onecstarter.ui.ops.command_picker import CommandPicker, run_command_picker
from onecstarter.ui.ops.controller import OperationsController
from onecstarter.ui.ops.run_dialog import RunDialog, run_run_dialog
from onecstarter.ui.ops.run_panel import RunPanel
from onecstarter.ui.ops.step_editor import StepEditor
from onecstarter.ui.theme import DARK, Palette

ID_ROLE = Qt.ItemDataRole.UserRole + 1
BUILTIN_HEADER = "Заготовки"
OWN_HEADER = "Мои"
BUILTIN_NOTE = "Заготовка: чтобы изменить, сделайте копию"
SAMPLE_BASE = "Имя базы"
RUN_LABEL = "▶ Выполнить…"
SCENARIOS_TITLE = "Сценарии"
SCENARIO_TITLE = "Сценарий"
EDITOR_TITLE = "Свойства шага"
REPLACES_CHIP = "заменяет"
EFFECT_CHIPS = {Effect.MODIFIES: "меняет базу", Effect.REPLACES: "заменяет данные"}
EFFECT_BADGES = {effect: f" · {text}" for effect, text in EFFECT_CHIPS.items()}
_ACCESSIBLE = Qt.ItemDataRole.AccessibleTextRole
RUN_PANEL_SPLIT = (520, 240)  # план В, Б7: доли верх/панель хода при первом показе  # noqa: RUF003


@dataclass(frozen=True)
class PreviewBase:
    """База для предпросмотра команды и примера пути. Паролей здесь нет."""

    name: str
    group: str = ""
    version: str = ""
    login: str | None = None
    repository_address: str | None = None
    repository_user: str | None = None


def confirm_scenario_removal(parent: QWidget, name: str) -> bool:
    return ask_confirmation(parent, "Операции", f"Удалить сценарий «{name}»?")


@dataclass(frozen=True)
class StepRow:
    """Части строки шага: из них собираются и плоская строка, и видимая (мокап `.step`)."""

    number: int
    title: str
    command: str
    effect: Effect | None  # только эффекты с чипом (`EFFECT_CHIPS`)  # noqa: RUF003
    summary: str


def step_row(number: int, step: Step, catalog: Catalog) -> StepRow:
    command = catalog.command(step.command)
    effect = command.effect if command is not None and command.effect in EFFECT_CHIPS else None
    return StepRow(
        number, step_title(step, catalog), step.command, effect, step_summary(step, catalog)
    )


def step_row_text(row: StepRow) -> str:
    """Плоская строка — диктору (`AccessibleTextRole`) и `step_texts()`; текст прежний."""
    badge = EFFECT_BADGES[row.effect] if row.effect is not None else ""
    return f"{row.number}. {row.title} — {row.command}{badge}\n{row.summary}"


def step_row_html(row: StepRow, palette: Palette) -> str:
    """Видимая строка (мокап `.step`, стр. 277–279). Пользовательский текст — через `escape`."""  # noqa: RUF002
    chip = ""
    if row.effect is not None:
        colour = palette.problem if row.effect is Effect.REPLACES else palette.warning
        chip = f' <span style="color:{colour}">{EFFECT_CHIPS[row.effect]}</span>'
    return (
        f'<span style="color:{palette.text_dim}">{row.number}</span>&nbsp;&nbsp;'
        f"<b>{escape(row.title)}</b> "
        f"{mono_span(row.command, palette.text_dim)}"
        f"{chip}"
        f'<br><i style="color:{palette.text_dim}">{escape(row.summary)}</i>'
    )


class OperationsView(QWidget):
    def __init__(
        self,
        controller: OperationsController,
        *,
        items: Callable[[], Sequence[InfobaseItem]],
        preview_base: Callable[[str], PreviewBase | None] = lambda _key: None,
        on_error: Callable[[str], None] | None = None,
        confirm_remove: Callable[[QWidget, str], bool] = confirm_scenario_removal,
        pick_command: Callable[[CommandPicker], bool] = run_command_picker,
        choose_bases: Callable[[BaseListDialog], bool] = run_base_list_dialog,
        run_dialog: Callable[[RunDialog], bool] = run_run_dialog,
        now: Callable[[], datetime] = datetime.now,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._catalog = controller.catalog
        self._items = items
        self._preview_base = preview_base
        self._on_error = on_error or (lambda text: show_service_error(self, ServicesError(text)))
        self._confirm_remove = confirm_remove
        self._pick_command = pick_command
        self._choose_bases = choose_bases
        self._run_dialog = run_dialog
        self._now = now
        self._palette = palette
        self._current_id: str | None = None
        self._step_index: int | None = None
        self._loading = False
        self._sample: SubstitutionContext | None = None
        self._sample_base: PreviewBase = PreviewBase(SAMPLE_BASE)
        self._sample_for: tuple[str | None, tuple[BaseRef, ...] | None] | None = None
        # Для какого сценария, списка баз и номера шага собран редактор шага.
        self._editor_key: tuple[str | None, tuple[BaseRef, ...] | None, int | None] | None = None

        self._run = QPushButton(RUN_LABEL)
        self._run.clicked.connect(lambda: self.request_run())
        mark_button(self._run, PRIMARY)  # мокап, экран 4 (стр. 254)
        # В12: «Заготовки» и «Мои» — узлы дерева, сценарии — дочерние с отступом.  # noqa: RUF003
        self._list = QTreeWidget()
        self._list.setObjectName("ScenarioTree")  # фон в боксе — по имени (задача 5)
        self._list.setColumnCount(2)
        self._list.setHeaderHidden(True)
        self._list.setRootIsDecorated(False)
        self._list.setItemsExpandable(False)
        self._list.setIndentation(16)
        header = self._list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._list.currentItemChanged.connect(self._on_list_current)
        self._add = QPushButton("＋")  # noqa: RUF001
        self._copy = QPushButton("Копия")
        self._remove = QPushButton("✕")
        self._add.setToolTip("Новый сценарий")
        self._remove.setToolTip("Удалить сценарий")
        self._add.clicked.connect(self.add_scenario)
        self._copy.clicked.connect(self.copy_current)
        self._remove.clicked.connect(self.remove_current)
        left = Box(SCENARIOS_TITLE)
        left_layout = left.body_layout()
        left_layout.addWidget(self._list, 1)
        list_buttons = QHBoxLayout()
        for button in (self._add, self._copy, self._remove):
            list_buttons.addWidget(button)
        left_layout.addLayout(list_buttons)

        self._name = QLineEdit()
        self._name.editingFinished.connect(lambda: self.rename(self._name.text()))
        self._note = QLabel()
        self._note.setObjectName("SettingsNote")
        self._ask = QRadioButton("спрашивать при запуске")
        self._saved = QRadioButton("сохранённый список")
        self._ask.toggled.connect(self._on_bases_mode)
        self._edit_bases = QPushButton("Изменить список…")
        self._edit_bases.clicked.connect(self.edit_bases)
        self._bases = hint_label()  # мокап `.q` (стр. 275)
        # Финальное ревью плана Б, F6: имена баз, команда шага неизвестной команды —
        # из файлов пользователя; `AutoText` принял бы `<b>` в имени за разметку.
        self._bases.setTextFormat(Qt.TextFormat.PlainText)
        bases_caption = dim_label("Базы:")
        bases_caption.setFont(bold_font(bases_caption.font()))
        # `#BasesMode QRadioButton:checked` — выбранный вариант акцентом (мокап, стр. 273).
        bases_mode = QWidget()
        bases_mode.setObjectName("BasesMode")
        bases_row = QHBoxLayout(bases_mode)
        bases_row.setContentsMargins(0, 0, 0, 0)
        bases_row.addWidget(bases_caption)
        bases_row.addWidget(self._ask)
        bases_row.addWidget(self._saved)
        bases_row.addStretch(1)
        bases_row.addWidget(self._edit_bases)
        self._steps = QListWidget()
        self._steps.setObjectName("Steps")
        self._steps.currentRowChanged.connect(self._on_step_row)
        self._add_step = QPushButton("＋ Шаг")  # noqa: RUF001
        self._up = QPushButton("↑")
        self._down = QPushButton("↓")
        self._remove_step = QPushButton("✕")
        self._add_step.clicked.connect(self.add_step)
        self._up.clicked.connect(lambda: self.move_step(-1))
        self._down.clicked.connect(lambda: self.move_step(1))
        self._remove_step.clicked.connect(self.remove_step)
        step_buttons = QHBoxLayout()
        for button in (self._add_step, self._up, self._down, self._remove_step):
            step_buttons.addWidget(button)
        step_buttons.addStretch(1)
        self._stop = QCheckBox("остановить на первой ошибке")
        self._stop.toggled.connect(self.set_stop_on_error)
        step_buttons.addWidget(self._stop)
        self._preview_title = QLabel()
        self._preview_title.setTextFormat(Qt.TextFormat.PlainText)
        self._preview = CommandLineView(palette)
        self._preview.setMaximumHeight(96)
        center = Box(SCENARIO_TITLE)
        center_layout = center.body_layout()
        center_layout.addWidget(self._name)
        center_layout.addWidget(self._note)
        center_layout.addWidget(bases_mode)
        center_layout.addWidget(self._bases)
        center_layout.addWidget(self._steps, 1)
        center_layout.addLayout(step_buttons)
        center_layout.addWidget(self._preview_title)
        center_layout.addWidget(self._preview)

        self._editor = StepEditor(self._catalog, palette=palette, show_title=False)
        self._editor.changed.connect(self._on_step_edited)
        # В11: узкая колонка показывала хвост пути.  # noqa: RUF003
        self._editor.setMinimumWidth(300)
        self._editor_box = Box(EDITOR_TITLE)
        self._editor_box.title_label().setTextFormat(Qt.TextFormat.PlainText)
        self._editor_box.body_layout().addWidget(self._editor)
        self._panel = RunPanel(controller, palette=palette)
        self._panel.retry_requested.connect(
            lambda scenario, keys: self.request_run(keys=list(keys), scenario=scenario)
        )

        self._editor_area = QSplitter()
        self._editor_area.addWidget(left)
        self._editor_area.addWidget(center)
        self._editor_area.addWidget(self._editor_box)
        self._editor_area.setStretchFactor(0, 0)
        self._editor_area.setStretchFactor(1, 1)
        self._editor_area.setStretchFactor(2, 0)
        # Мокап: 220 / растяжка / 290; правая — 340, чтобы путь читался (В11).  # noqa: RUF003
        self._editor_area.setSizes([220, 640, 340])
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(self._editor_area)
        vertical.addWidget(self._panel)
        vertical.setStretchFactor(0, 3)
        vertical.setStretchFactor(1, 1)
        vertical.setSizes(list(RUN_PANEL_SPLIT))
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(self._run)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top)
        layout.addWidget(vertical, 1)

        controller.scenarios_changed.connect(self._reload_list)
        controller.problem.connect(self._report)
        self._reload_list()

    # -- чтение для тестов и проводки ---------------------------------------

    def current(self) -> Scenario | None:
        return self._controller.scenario(self._current_id) if self._current_id else None

    def scenario_ids(self) -> list[str]:
        return [
            str(row.data(0, ID_ROLE)) for row in self._rows() if row.data(0, ID_ROLE) is not None
        ]

    def list_titles(self) -> list[str]:
        return [row.text(0) for row in self._rows()]

    def scenario_tree(self) -> QTreeWidget:
        return self._list

    def scenario_item(self, scenario_id: str) -> QTreeWidgetItem | None:
        return next((row for row in self._rows() if row.data(0, ID_ROLE) == scenario_id), None)

    def editor_splitter(self) -> QSplitter:
        return self._editor_area

    def editor_box(self) -> Box:
        return self._editor_box

    def bases_label(self) -> QLabel:
        return self._bases

    def step_texts(self) -> list[str]:
        return [str(self._steps.item(row).data(_ACCESSIBLE)) for row in range(self._steps.count())]

    def steps_list(self) -> QListWidget:
        return self._steps

    def step_row_label(self, row: int) -> QLabel:
        label = self._steps.itemWidget(self._steps.item(row))
        assert isinstance(label, QLabel)
        return label

    def add_step_button(self) -> QPushButton:
        return self._add_step

    def preview_view(self) -> CommandLineView:
        return self._preview

    def bases_text(self) -> str:
        return self._bases.text()

    def note_text(self) -> str:
        return self._note.text()

    def preview_title(self) -> str:
        return self._preview_title.text()

    def preview_title_label(self) -> QLabel:
        return self._preview_title

    def preview_text(self) -> str:
        return self._preview.toPlainText()

    def name_edit(self) -> QLineEdit:
        return self._name

    def stop_checkbox(self) -> QCheckBox:
        return self._stop

    def run_button(self) -> QPushButton:
        return self._run

    def step_editor(self) -> StepEditor:
        return self._editor

    def run_panel(self) -> RunPanel:
        return self._panel

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._editor.apply_palette(palette)
        self._panel.apply_palette(palette)
        self._preview.set_palette(palette)
        self._reload_list()  # цвета узлов и чипов запечены в элементы

    # -- список сценариев ----------------------------------------------------

    def select_scenario(self, scenario_id: str) -> None:
        if self._controller.scenario(scenario_id) is None:
            return
        self._current_id = scenario_id
        self._step_index = None
        self._reload_list()

    def add_scenario(self) -> None:
        fresh = self._controller.new_scenario()
        if self._store(fresh):
            self.select_scenario(fresh.id)

    def copy_current(self) -> None:
        if self._current_id is None:
            return
        copy = self._controller.copy_scenario(self._current_id)
        if copy is not None:
            self.select_scenario(copy.id)

    def remove_current(self) -> None:
        scenario = self.current()
        if scenario is None or scenario.builtin:
            return
        if not self._confirm_remove(self, scenario.name):
            return
        error = self._controller.remove_scenario(scenario.id)
        if error is not None:
            self._report(error)
            return
        self._current_id = None
        self._step_index = None
        self._reload_list()

    def _reload_list(self) -> None:
        scenarios = self._controller.scenarios()
        if self._current_id is None or self._controller.scenario(self._current_id) is None:
            self._current_id = scenarios[0].id if scenarios else None
            self._step_index = None
        self._list.blockSignals(True)
        self._list.clear()
        bold = bold_font(self._list.font())
        current: QTreeWidgetItem | None = None
        for header, builtin in ((BUILTIN_HEADER, True), (OWN_HEADER, False)):
            title = QTreeWidgetItem([header, ""])
            title.setFlags(Qt.ItemFlag.ItemIsEnabled)  # не выбирается; не NoItemFlags — не серый
            title.setFont(0, bold)
            title.setForeground(0, QColor(self._palette.text_dim))
            self._list.addTopLevelItem(title)
            for scenario in scenarios:
                if scenario.builtin is not builtin:
                    continue
                replaces = scenario_effect(scenario, self._catalog) is Effect.REPLACES
                row = QTreeWidgetItem([scenario.name, REPLACES_CHIP if replaces else ""])
                row.setData(0, ID_ROLE, scenario.id)
                if replaces:
                    row.setForeground(1, QColor(self._palette.problem))
                title.addChild(row)
                if scenario.id == self._current_id:
                    current = row
            title.setExpanded(True)
        if current is not None:
            self._list.setCurrentItem(current)
        self._list.blockSignals(False)
        self._show_scenario()

    def _rows(self) -> list[QTreeWidgetItem]:
        rows: list[QTreeWidgetItem] = []
        for index in range(self._list.topLevelItemCount()):
            top = self._list.topLevelItem(index)
            if top is None:
                continue
            rows.append(top)
            rows.extend(top.child(child) for child in range(top.childCount()))
        return rows

    def _on_list_current(self, current: QTreeWidgetItem | None, _previous: object) -> None:
        scenario_id = current.data(0, ID_ROLE) if current is not None else None
        if isinstance(scenario_id, str) and scenario_id != self._current_id:
            self._current_id = scenario_id
            self._step_index = None
            self._show_scenario()

    # -- показ сценария ------------------------------------------------------

    def _show_scenario(self) -> None:
        scenario = self.current()
        editable = scenario is not None and not scenario.builtin
        self._loading = True
        self._name.setText(scenario.name if scenario is not None else "")
        self._name.setEnabled(editable)
        self._note.setText(BUILTIN_NOTE if scenario is not None and scenario.builtin else "")
        saved = scenario is not None and scenario.bases is not None
        (self._saved if saved else self._ask).setChecked(True)
        count = len(scenario.bases) if scenario is not None and scenario.bases is not None else 0
        self._saved.setText(f"сохранённый список ({count})" if saved else "сохранённый список")
        for widget in (self._ask, self._saved, self._add_step, self._stop):
            widget.setEnabled(editable)
        self._edit_bases.setEnabled(editable)
        self._bases.setText(
            " · ".join(ref.name for ref in scenario.bases)
            if scenario is not None and scenario.bases
            else ""
        )
        self._stop.setChecked(scenario.stop_on_error if scenario is not None else True)
        self._copy.setEnabled(scenario is not None)
        self._remove.setEnabled(editable)
        self._run.setEnabled(scenario is not None and bool(scenario.steps))
        self._steps.blockSignals(True)
        self._steps.clear()
        steps = scenario.steps if scenario is not None else ()
        for number, step in enumerate(steps, start=1):
            parts = step_row(number, step, self._catalog)
            row = QListWidgetItem()
            # Плоский текст — диктору и step_texts(); видимую строку рисует метка: текст
            # самого элемента делегат нарисовал бы под ней.
            row.setData(_ACCESSIBLE, step_row_text(parts))
            label = QLabel(step_row_html(parts, self._palette))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setContentsMargins(6, 4, 6, 4)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._steps.addItem(row)
            row.setSizeHint(label.sizeHint())
            self._steps.setItemWidget(row, label)
        if self._step_index is not None and self._step_index >= len(steps):
            self._step_index = None
        if self._step_index is not None:
            self._steps.setCurrentRow(self._step_index)
        self._steps.blockSignals(False)
        self._loading = False
        self._refresh_sample(scenario)
        self._show_step()

    def _refresh_sample(self, scenario: Scenario | None) -> None:
        """База-пример: первая из сохранённого списка, иначе условное имя.

        Считается при смене сценария или его списка, а не на каждую правку шага:
        источник читает диспетчер учётных данных.
        """  # noqa: RUF002
        marker = (scenario.id, scenario.bases) if scenario is not None else (None, None)
        if marker == self._sample_for:
            return
        self._sample_for = marker
        base: PreviewBase | None = None
        if scenario is not None and scenario.bases:
            base = self._preview_base(scenario.bases[0].key)
        self._sample_base = base or PreviewBase(SAMPLE_BASE)
        self._sample = SubstitutionContext(
            self._sample_base.name, self._sample_base.group, self._sample_base.version, self._now()
        )

    def _show_step(self) -> None:
        scenario = self.current()
        index = self._step_index
        step = scenario.steps[index] if scenario is not None and index is not None else None
        editable = scenario is not None and not scenario.builtin
        for button in (self._up, self._down, self._remove_step):
            button.setEnabled(editable and step is not None)
        # Шаг тот же — редактор не трогаем: пересборка полей уводит фокус из соседнего поля.
        if self._editor.step() != step or step is None or self._editor_key != self._key(scenario):
            self._editor.set_step(step, read_only=not editable, sample=self._sample)
            self._editor_key = self._key(scenario)
        self._editor_box.set_title(
            f"Шаг {index + 1} — {step_title(step, self._catalog)}"
            if step is not None and index is not None
            else EDITOR_TITLE
        )
        self._refresh_preview(scenario, step, index)

    def _key(
        self, scenario: Scenario | None
    ) -> tuple[str | None, tuple[BaseRef, ...] | None, int | None]:
        if scenario is None:
            return (None, None, None)
        return (scenario.id, scenario.bases, self._step_index)

    def _refresh_preview(
        self, scenario: Scenario | None, step: Step | None, index: int | None
    ) -> None:
        if scenario is None or step is None or index is None or self._sample is None:
            self._preview_title.setText("")
            self._preview.show_line("")
            return
        base = self._sample_base
        logs_dir = (
            f"…\\ops\\{self._sample.started:%Y-%m-%d_%H%M%S}_"
            f"{sanitize_component(scenario.name)}\\01_{sanitize_component(base.name)}"
        )
        arguments = preview_arguments(
            step,
            self._catalog,
            base_name=base.name,
            login=base.login,
            repository_address=base.repository_address,
            repository_user=base.repository_user,
            logs_dir=logs_dir,
            index=index,
            context=self._sample,
            environ=os.environ,
        )
        self._preview_title.setText(f"Команда шага {index + 1} для «{base.name}» (пароли скрыты):")
        line = f"1cv8.exe {redact_arguments(arguments)}" if arguments else ""
        # Строку собирает программа: каждое «/слово» — ключ каталога, неизвестных нет.
        # Начало `.base` — до конца `/IBName…`: формат строки знает домен
        # (`build_step_arguments`), здесь он не повторяется (предпроверка 3.7).
        self._preview.show_line(
            line,
            base_length=base_length_through(line, "/IBName"),
            is_known=lambda _word: True,
        )

    # -- правки --------------------------------------------------------------

    def _report(self, text: str) -> None:
        self._on_error(text)

    def _store(self, scenario: Scenario) -> bool:
        """Сохранить правку. При отказе — сообщение и возврат показа к сохранённому."""
        error = self._controller.save_scenario(scenario)
        if error is not None:
            self._report(error)
            self._editor_key = None  # редактор мог уйти вперёд — пересобрать
            self._show_scenario()
            return False
        return True

    def _editable(self) -> Scenario | None:
        scenario = self.current()
        if self._loading or scenario is None or scenario.builtin:
            return None
        return scenario

    def rename(self, text: str) -> None:
        scenario = self._editable()
        name = text.strip()
        if scenario is None or not name or name == scenario.name:
            if scenario is not None:
                self._name.setText(scenario.name)
            return
        self._store(replace(scenario, name=name))

    def set_saved_bases(self, saved: bool) -> None:
        scenario = self._editable()
        if scenario is None or (scenario.bases is not None) == saved:
            return
        self._store(replace(scenario, bases=() if saved else None))

    def _on_bases_mode(self, ask: bool) -> None:
        if not self._loading:
            self.set_saved_bases(not ask)

    def edit_bases(self) -> None:
        scenario = self._editable()
        if scenario is None:
            return
        items = self._items()
        known = {item.key for item in items if not item.is_group}
        saved = scenario.bases or ()
        dialog = BaseListDialog(
            items,
            checked=[ref.key for ref in saved if ref.key in known],
            missing=[ref for ref in saved if ref.key not in known],
            palette=self._palette,
            parent=self,
        )
        try:
            accepted = self._choose_bases(dialog)
            refs = tuple(dialog.checklist().checked_refs()) if accepted else None
        finally:
            dialog.deleteLater()
        if refs is not None:
            self._store(replace(scenario, bases=refs))

    def set_stop_on_error(self, value: bool) -> None:
        scenario = self._editable()
        if scenario is not None and scenario.stop_on_error != value:
            self._store(replace(scenario, stop_on_error=value))

    # -- шаги ----------------------------------------------------------------

    def select_step(self, index: int) -> None:
        self._steps.setCurrentRow(index)

    def _on_step_row(self, row: int) -> None:
        self._step_index = row if row >= 0 else None
        self._show_step()

    def add_step(self) -> None:
        scenario = self._editable()
        if scenario is None:
            return
        dialog = CommandPicker(self._catalog, palette=self._palette, parent=self)
        try:
            name = dialog.chosen() if self._pick_command(dialog) else None
        finally:
            dialog.deleteLater()
        if name is None:
            return
        self._step_index = len(scenario.steps)
        self._store(replace(scenario, steps=(*scenario.steps, Step(name))))

    def move_step(self, delta: int) -> None:
        scenario = self._editable()
        index = self._step_index
        if scenario is None or index is None:
            return
        target = index + delta
        if not 0 <= target < len(scenario.steps):
            return
        steps = list(scenario.steps)
        steps[index], steps[target] = steps[target], steps[index]
        self._step_index = target
        self._store(replace(scenario, steps=tuple(steps)))

    def remove_step(self) -> None:
        scenario = self._editable()
        index = self._step_index
        if scenario is None or index is None:
            return
        steps = scenario.steps[:index] + scenario.steps[index + 1 :]
        self._step_index = None
        self._store(replace(scenario, steps=steps))

    def _on_step_edited(self, step: Step) -> None:
        scenario = self._editable()
        index = self._step_index
        if scenario is None or index is None or index >= len(scenario.steps):
            return
        steps = list(scenario.steps)
        steps[index] = step
        self._store(replace(scenario, steps=tuple(steps)))

    # -- запуск --------------------------------------------------------------

    def request_run(
        self,
        scenario_id: str | None = None,
        keys: Sequence[str] | None = None,
        *,
        scenario: Scenario | None = None,
    ) -> None:
        """Открыть окно запуска и, после согласия, запустить сценарий (спека §7.5).

        `keys is None` — базы сохранённого списка сценария. `scenario` — сценарий прошлого
        запуска («Повторить для ошибочных»): в нём уже выбран входной файл.
        """
        chosen = scenario
        if chosen is None:
            chosen = self._controller.scenario(scenario_id) if scenario_id else self.current()
        if chosen is None:
            return
        if self._controller.running:
            self._report(BUSY_TEXT)
            return
        items = self._items()
        known = {item.key for item in items if not item.is_group}
        saved = chosen.bases or ()
        if keys is None:
            checked = [ref.key for ref in saved if ref.key in known]
            missing = [ref for ref in saved if ref.key not in known]
        else:
            checked = [key for key in keys if key in known]
            missing = []
        dialog = RunDialog(
            self._controller,
            chosen,
            items,
            checked=checked,
            missing=missing,
            palette=self._palette,
            parent=self,
        )
        try:
            accepted = self._run_dialog(dialog)
            request = dialog.outcome() if accepted else None
        finally:
            dialog.forget()  # окно больше не держит план и пароли
            dialog.deleteLater()
        if request is None:
            return
        if request.remember and not chosen.builtin:
            stored = self._controller.scenario(chosen.id)
            if stored is not None:
                self._store(replace(stored, bases=request.refs))
        error = self._controller.start(request.plan, parallel=request.parallel)
        if error is not None:
            self._report(error)
