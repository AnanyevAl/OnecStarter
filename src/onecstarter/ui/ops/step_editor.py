"""Свойства шага сценария: поля по типам аргументов команды каталога (спека v4, §7.4)."""

import os
from collections.abc import Callable, Mapping
from dataclasses import replace
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextDocumentFragment
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_catalog import ArgKind, ArgSpec, Catalog, CatalogCommand
from onecstarter.domain.cli_params import Level
from onecstarter.domain.operations import (
    SUBSTITUTIONS,
    Step,
    SubstitutionContext,
    padded,
    step_problems,
)
from onecstarter.domain.operations_text import example_path, step_hints, step_title
from onecstarter.ui.components import FindingsList, Note, hint_label, mono_span
from onecstarter.ui.theme import DARK, Palette

BOUND_NOTE = "из свойств базы (хранилище конфигурации)"
OVERWRITE_LABEL = "перезаписывать существующее"
CREATE_DIRS_LABEL = "создавать недостающие каталоги"
SUBSTITUTIONS_TAIL = "Дата и время — момент старта сценария, общий для всех баз."


def _substitutions_line(name_markup: Callable[[str], str], tail: str) -> str:
    """Одна строка подсказки о подстановках — и для простого текста, и для rich text."""  # noqa: RUF002
    names = " ".join(name_markup(f"{{{name}}}") for name in SUBSTITUTIONS)
    return f"Подстановки: {names}. {tail}"


SUBSTITUTIONS_HELP = _substitutions_line(str, SUBSTITUTIONS_TAIL)
_PATH_KINDS = (ArgKind.FILE, ArgKind.DIR)


def browse_for_step_path(parent: QWidget, arg: ArgSpec, current: str) -> str:
    """Выбрать файл или каталог для аргумента шага. Пустая строка — выбор отменён."""
    if arg.kind is ArgKind.DIR:
        return QFileDialog.getExistingDirectory(parent, arg.label or "Каталог", current)
    pattern = f"*{arg.ext}" if arg.ext else "*"
    if arg.role == "output":
        chosen, _ = QFileDialog.getSaveFileName(
            parent,
            arg.label or "Файл",
            current,
            pattern,
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
    else:
        chosen, _ = QFileDialog.getOpenFileName(parent, arg.label or "Файл", current, pattern)
    return chosen


def _new_form(host: QWidget) -> QFormLayout:
    form = QFormLayout(host)
    form.setContentsMargins(0, 0, 0, 0)
    # В11 (приёмка 21.11.2026): подпись над полем, как в мокапе (стр. 290) —  # noqa: RUF003
    # подпись слева съедала ширину узкой колонки, и от пути оставался хвост.
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    return form


def substitutions_html(palette: Palette) -> str:
    """`SUBSTITUTIONS_HELP` с подстановками акцентом (мокап `.subs code`, стр. 292)."""  # noqa: RUF002
    return _substitutions_line(
        lambda name: mono_span(name, palette.accent), escape(SUBSTITUTIONS_TAIL)
    )


def _label(arg: ArgSpec) -> str:
    if arg.flag and arg.label:
        return f"{arg.flag} ({arg.label})"
    return arg.label or arg.flag or arg.kind.value


class StepEditor(QWidget):
    changed = Signal(object)  # Step

    def __init__(
        self,
        catalog: Catalog,
        *,
        choose_path: Callable[[QWidget, ArgSpec, str], str] = browse_for_step_path,
        environ: Mapping[str, str] | None = None,
        palette: Palette = DARK,
        show_title: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._catalog = catalog
        self._choose_path = choose_path
        self._environ = environ
        self._palette = palette
        self._step: Step | None = None
        self._command: CatalogCommand | None = None
        self._read_only = False
        self._sample: SubstitutionContext | None = None
        self._widgets: dict[int, QWidget] = {}

        self._title = QLabel()
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        self._description = QLabel()
        self._fields = QWidget()
        self._form = _new_form(self._fields)
        self._overwrite = QCheckBox(OVERWRITE_LABEL)
        self._create_dirs = QCheckBox(CREATE_DIRS_LABEL)
        self._overwrite.toggled.connect(self.set_overwrite)
        self._create_dirs.toggled.connect(self.set_create_dirs)
        self._example = hint_label()
        # Финальное ревью плана Б, F6: имя базы в примере и команда шага в заголовке —
        # из файлов пользователя, не разметка.
        for label in (self._title, self._example):
            label.setTextFormat(Qt.TextFormat.PlainText)
        self._substitutions = QLabel()
        self._substitutions.setTextFormat(Qt.TextFormat.RichText)
        self._hints = FindingsList()
        self._problems = FindingsList()
        for label in (
            self._title,
            self._description,
            self._substitutions,
        ):
            label.setWordWrap(True)
        self._substitutions.setObjectName("SettingsNote")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        # Финальное ревью плана Б, F7: скрывать уже в раскладке — `setVisible(True)` до неё
        # показал бы метку на миг отдельным окном верхнего уровня.
        self._title.setHidden(not show_title)
        layout.addWidget(self._description)
        layout.addWidget(self._fields)
        layout.addWidget(self._overwrite)
        layout.addWidget(self._create_dirs)
        layout.addWidget(self._example)
        layout.addWidget(self._substitutions)
        layout.addWidget(self._hints)
        layout.addWidget(self._problems)
        layout.addStretch(1)
        self.apply_palette(palette)
        # Начальное пустое состояние строим напрямую: set_step(None) вышел бы по раннему возврату.
        self._rebuild_fields()
        self._refresh_texts()

    # -- состояние -----------------------------------------------------------

    def set_step(
        self,
        step: Step | None,
        *,
        read_only: bool = False,
        sample: SubstitutionContext | None = None,
    ) -> None:
        if step == self._step and read_only == self._read_only and sample == self._sample:
            return
        self._step = step
        self._read_only = read_only
        self._sample = sample
        self._command = self._catalog.command(step.command) if step is not None else None
        self._rebuild_fields()
        self._refresh_texts()

    def step(self) -> Step | None:
        return self._step

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._substitutions.setText(substitutions_html(palette))

    # -- правка --------------------------------------------------------------

    def set_value(self, index: int, value: str | None) -> None:
        if self._step is None or self._command is None or self._read_only:
            return
        if index >= len(self._command.args):
            return
        # «Не задано» — `None`, не пустая строка; у флага `""` — «включён».  # noqa: RUF003
        if (
            value is not None
            and self._command.args[index].kind is not ArgKind.FLAG
            and not value.strip()
        ):
            value = None
        values = list(padded(self._step.values, self._command.args))
        if values[index] == value:
            return
        values[index] = value
        self._emit(replace(self._step, values=tuple(values)))

    def set_overwrite(self, value: bool) -> None:
        if self._step is None or self._read_only or self._step.overwrite == value:
            return
        self._emit(replace(self._step, overwrite=value))

    def set_create_dirs(self, value: bool) -> None:
        if self._step is None or self._read_only or self._step.create_dirs == value:
            return
        self._emit(replace(self._step, create_dirs=value))

    def browse(self, index: int) -> None:
        if self._step is None or self._command is None or self._read_only:
            return
        if not 0 <= index < len(self._command.args):
            return
        if self._command.args[index].kind not in _PATH_KINDS:
            return
        current = padded(self._step.values, self._command.args)[index] or ""
        chosen = self._choose_path(self, self._command.args[index], current)
        if chosen:
            self.set_value(index, chosen.replace("/", "\\"))
            self._sync_fields()

    def _emit(self, step: Step) -> None:
        self._step = step
        self._sync_fields()
        self._refresh_texts()
        self.changed.emit(step)

    # -- чтение для тестов и раздела ----------------------------------------

    def value_widget(self, index: int) -> QWidget | None:
        return self._widgets.get(index)

    def overwrite_checkbox(self) -> QCheckBox:
        return self._overwrite

    def create_dirs_checkbox(self) -> QCheckBox:
        return self._create_dirs

    def title_text(self) -> str:
        return self._title.text()

    def description_text(self) -> str:
        return self._description.text()

    def example_text(self) -> str:
        return self._example.text()

    def substitutions_text(self) -> str:
        # Читаем показанную метку, а не константу: тест сверяет видимое.  # noqa: RUF003
        return QTextDocumentFragment.fromHtml(self._substitutions.text()).toPlainText()

    def hints_text(self) -> str:
        return "\n".join(self._hints.texts())

    def problems_text(self) -> str:
        return "\n".join(self._problems.texts())

    def form_layout(self) -> QFormLayout:
        return self._form

    def hint_list(self) -> FindingsList:
        return self._hints

    def problem_list(self) -> FindingsList:
        return self._problems

    def example_label(self) -> QLabel:
        return self._example

    def substitutions_label(self) -> QLabel:
        return self._substitutions

    def title_label(self) -> QLabel:
        return self._title

    # -- внутреннее ----------------------------------------------------------

    def _rebuild_fields(self) -> None:
        # Старые виджеты не удаляем синхронно: set_step могут позвать из обработчика их сигнала.
        old = self._fields
        self._fields = QWidget()
        self._form = _new_form(self._fields)
        layout = self.layout()
        if isinstance(layout, QVBoxLayout):
            layout.replaceWidget(old, self._fields)
        old.hide()
        old.deleteLater()
        self._widgets = {}
        command = self._command
        has_output = command is not None and any(arg.role == "output" for arg in command.args)
        for box in (self._overwrite, self._create_dirs):
            box.setVisible(has_output)
            box.setEnabled(not self._read_only)
        self._substitutions.setVisible(
            command is not None and any(arg.kind in _PATH_KINDS for arg in command.args)
        )
        if self._step is None or command is None:
            return
        for index, arg in enumerate(command.args):
            if arg.kind is ArgKind.BOUND:
                continue
            widget = self._field(index, arg)
            widget.setEnabled(not self._read_only)
            self._widgets[index] = widget
        if command.bound:
            self._form.addRow(QLabel(BOUND_NOTE))
        self._sync_fields()
        # Подписи серым, как в мокапе (`.form label`).
        for row in range(self._form.rowCount()):
            item = self._form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            label = item.widget() if item is not None else None
            if isinstance(label, QLabel):
                label.setObjectName("FormLabel")

    def _field(self, index: int, arg: ArgSpec) -> QWidget:
        if arg.kind is ArgKind.FLAG:
            box = QCheckBox(_label(arg))
            box.toggled.connect(lambda on, i=index: self.set_value(i, "" if on else None))
            self._form.addRow(box)
            return box
        if arg.kind is ArgKind.ENUM:
            combo = QComboBox()
            combo.addItem("", None)
            for option in arg.values:
                combo.addItem(option, option)
            combo.activated.connect(
                lambda _row, c=combo, i=index: self.set_value(i, c.currentData())
            )
            self._form.addRow(_label(arg), combo)
            return combo
        edit = QLineEdit()
        if arg.kind in _PATH_KINDS:
            edit.setObjectName("MonoEdit")
        edit.editingFinished.connect(
            lambda e=edit, i=index: self.set_value(i, e.text().strip() or None)
        )
        if arg.kind not in _PATH_KINDS:
            self._form.addRow(_label(arg), edit)
            return edit
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(edit, 1)
        button = QPushButton("…")
        button.setAutoDefault(False)
        button.clicked.connect(lambda _checked=False, i=index: self.browse(i))
        row_layout.addWidget(button)
        self._form.addRow(_label(arg), row)
        button.setEnabled(not self._read_only)
        return edit

    def _sync_fields(self) -> None:
        if self._step is None or self._command is None:
            return
        values = padded(self._step.values[: len(self._command.args)], self._command.args)
        for index, widget in self._widgets.items():
            value = values[index]
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(value is not None)
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(widget.findData(value) if value else 0, 0))
            elif isinstance(widget, QLineEdit):
                if widget.text() != (value or ""):
                    widget.setText(value or "")
                    # В11: setText ставит курсор в конец — был виден хвост.  # noqa: RUF003
                    widget.setCursorPosition(0)
                widget.setToolTip(value or "")
            widget.blockSignals(False)
        for box, flag in (
            (self._overwrite, self._step.overwrite),
            (self._create_dirs, self._step.create_dirs),
        ):
            box.blockSignals(True)
            box.setChecked(flag)
            box.blockSignals(False)

    def _refresh_texts(self) -> None:
        step, command = self._step, self._command
        if step is None:
            for label in (self._title, self._description, self._example):
                label.setText("")
            self._hints.set_notes([])
            self._problems.set_notes([])
            return
        self._title.setText(step_title(step, self._catalog))
        self._description.setText(command.description if command is not None else "")
        self._hints.set_notes(
            [Note(Level.WARNING, text) for text in step_hints(step, self._catalog)]
        )
        self._problems.set_notes(
            [Note(Level.ERROR, text) for text in step_problems(step, self._catalog)]
        )
        self._example.setText(self._example_for(step, command))

    def _example_for(self, step: Step, command: CatalogCommand | None) -> str:
        if command is None or self._sample is None or len(step.values) > len(command.args):
            return ""
        environ = self._environ if self._environ is not None else os.environ
        for arg, value in zip(command.args, padded(step.values, command.args), strict=True):
            if arg.kind in _PATH_KINDS and value:
                return f"Для «{self._sample.base}»: {example_path(value, self._sample, environ)}"
        return ""
