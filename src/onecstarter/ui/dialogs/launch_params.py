"""Блок «Параметры запуска» диалога свойств базы и его помощники (спека v4, §7.1).

Две строки: «1С:Предприятие» — `AdditionalParameters` записи `.v8i` (её видит и
штатный стартер), «Конфигуратор» — наша строка из `bases.json`, уходит в argv только
при запуске Конфигуратора (решение 14, §1; решение 08.11.2026 о хранении). Проверка
строк ничего не блокирует (спека §4.2) — замечания видны выносками под строками
и чипами в строке заголовка.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

from onecstarter.domain.cli_catalog import Catalog, Client, Mode
from onecstarter.domain.cli_params import (
    CheckContext,
    Finding,
    Level,
    ParsedParams,
    Where,
    check,
    key_count,
    parse,
)
from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import quote_launch_value
from onecstarter.domain.selection import resolve_version
from onecstarter.domain.version import Installation, VersionNumber
from onecstarter.security.secrets import redact_arguments
from onecstarter.services.model import InfobaseItem
from onecstarter.ui.components import (
    Chip,
    FindingsList,
    accent_label,
    align_form,
    notes_from_findings,
)
from onecstarter.ui.settings_group import CollapsibleGroup
from onecstarter.ui.theme import DARK, Palette

BLOCK_TITLE = "Параметры запуска"
ENTERPRISE_ROW = "1С:Предприятие"  # noqa: RUF001
DESIGNER_ROW = "Конфигуратор"
BUILDER_BUTTON = "…"
BLOCK_ID = "launch_params"


def plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        word = many
    elif count % 10 == 1:
        word = one
    elif 2 <= count % 10 <= 4:
        word = few
    else:
        word = many
    return f"{count} {word}"


def _keys(count: int) -> str:
    return plural(count, "ключ", "ключа", "ключей")


def block_title(enterprise: ParsedParams, designer: ParsedParams | None) -> str:
    first = key_count(enterprise)
    second = key_count(designer) if designer is not None else 0
    if not first and second:
        # Приёмка 21.11.2026, В9: «— нет · Конфигуратор» читалось как «нет».  # noqa: RUF003
        return f"{BLOCK_TITLE} — Конфигуратор: {_keys(second)}"
    head = f"{BLOCK_TITLE} — {_keys(first) if first else 'нет'}"
    return f"{head} · Конфигуратор: {_keys(second)}" if second else head


def counts_text(findings: Sequence[Finding]) -> str:
    errors = sum(1 for finding in findings if finding.level is Level.ERROR)
    warnings = sum(1 for finding in findings if finding.level is Level.WARNING)
    parts = []
    if errors:
        parts.append(plural(errors, "ошибка", "ошибки", "ошибок"))
    if warnings:
        parts.append(plural(warnings, "предупреждение", "предупреждения", "предупреждений"))
    return " · ".join(parts)


def base_client(app: str | None) -> Client | None:
    folded = (app or "").casefold()
    if folded == "thinclient":
        return Client.THIN
    if folded == "thickclient":
        return Client.THICK
    return None


def base_version(
    item: InfobaseItem,
    installations: Sequence[Installation],
    cfg_rules: Sequence[DefaultVersionRule],
) -> VersionNumber | None:
    """Версия, которой запустится файловая база; у серверной и веб-базы её решает сервер."""  # noqa: RUF002
    if item.kind is not ConnectKind.FILE:
        return None
    resolution = resolve_version(
        item.requested_version,
        item.section_default_version,
        cfg_rules,
        [installation.version for installation in installations],
    )
    return resolution.version


def additional_parameters(item: InfobaseItem) -> str:
    return next(
        (value for name, value in item.keys if name.casefold() == "additionalparameters"), ""
    )


def preview_command(name: str, mode: Mode, client: Client | None, text: str) -> str:
    """Командная строка «как её увидит клиент» (спека §7.2) — с замаскированными паролями."""  # noqa: RUF002
    if mode is Mode.DESIGNER:
        head = "1cv8.exe DESIGNER"
    elif client is Client.THICK:
        head = "1cv8.exe ENTERPRISE"
    else:
        head = "1cv8c.exe ENTERPRISE"
    line = f"{head} /IBName{quote_launch_value(name)}"
    extra = text.strip()
    return f"{line} {redact_arguments(extra)}" if extra else line


class LaunchParamsBlock(CollapsibleGroup):
    designer_text_changed = Signal(str)
    content_changed = Signal()

    def __init__(
        self,
        catalog: Catalog,
        *,
        enterprise: str,
        designer: str,
        show_designer: bool,
        client: Client | None,
        version: VersionNumber | None,
        open_builder: Callable[[Mode, str], str | None],
        expanded: bool = False,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            BLOCK_TITLE,
            accent=False,
            rule=False,
            summary=True,
            rule_above=True,
            object_name="LaunchParamsTitle",
            parent=parent,
        )
        # Мокап v4, экран 1 (стр. 119): счётчики — «пилюли» справа в строке заголовка
        # (было — подпись под заголовком, спека §7.1 исправлена планом Б).
        self._errors_chip = Chip(Level.ERROR)
        self._warnings_chip = Chip(Level.WARNING)
        for chip in self.chips():
            chip.setVisible(False)
            self.add_header_widget(chip)
        self._catalog = catalog
        self._client = client
        self._version = version
        self._open_builder = open_builder
        self._show_designer = show_designer
        self._enterprise = QLineEdit(enterprise)
        self._designer = QLineEdit(designer)
        for edit in (self._enterprise, self._designer):
            edit.setObjectName("MonoEdit")
        self._enterprise_findings = FindingsList()
        self._designer_findings = FindingsList()
        form = QFormLayout()
        form.addRow(accent_label(ENTERPRISE_ROW), self._line_row(self._enterprise, Mode.ENTERPRISE))
        form.addRow("", self._enterprise_findings)
        self._designer_row = self._line_row(self._designer, Mode.DESIGNER)
        form.addRow(accent_label(DESIGNER_ROW), self._designer_row)
        form.addRow("", self._designer_findings)
        form.setRowVisible(self._designer_row, show_designer)
        form.setRowVisible(self._designer_findings, show_designer)
        align_form(form)
        self.body_layout().addLayout(form)
        self._enterprise.textChanged.connect(self.refresh)
        self._designer.textChanged.connect(self.refresh)
        self._designer.textChanged.connect(self.designer_text_changed)
        self.set_palette(palette)
        self.set_expanded(expanded)
        self.refresh()

    def _line_row(self, edit: QLineEdit, mode: Mode) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        button = QPushButton(BUILDER_BUTTON)
        button.setAutoDefault(False)
        button.clicked.connect(lambda: self.run_builder(mode))
        layout.addWidget(button)
        return row

    def run_builder(self, mode: Mode) -> None:
        edit = self._enterprise if mode is Mode.ENTERPRISE else self._designer
        result = self._open_builder(mode, edit.text())
        if result is not None:
            edit.setText(result)

    def enterprise_text(self) -> str:
        return self._enterprise.text()

    def designer_text(self) -> str:
        return self._designer.text()

    def set_enterprise_text(self, text: str) -> None:
        self._enterprise.setText(text)

    def set_designer_text(self, text: str) -> None:
        self._designer.setText(text)

    def designer_visible(self) -> bool:
        return self._show_designer

    def chips(self) -> list[Chip]:
        return [self._errors_chip, self._warnings_chip]

    def chip_states(self) -> list[tuple[str, str]]:
        return [
            (str(chip.property("level")), chip.text())
            for chip in self.chips()
            if not chip.isHidden()
        ]

    def counts_label_text(self) -> str:
        return " · ".join(text for _level, text in self.chip_states())

    def findings_list(self, mode: Mode) -> FindingsList:
        return self._enterprise_findings if mode is Mode.ENTERPRISE else self._designer_findings

    def findings_text(self, mode: Mode) -> str:
        return "\n".join(self.findings_list(mode).texts())

    def refresh(self) -> None:
        enterprise = parse(self._enterprise.text(), self._catalog)
        designer = parse(self._designer.text(), self._catalog) if self._show_designer else None
        enterprise_findings = check(
            enterprise,
            CheckContext(Where.PERMANENT, Mode.ENTERPRISE, self._client, self._version),
        )
        designer_findings = (
            check(designer, CheckContext(Where.DESIGNER_LINE, Mode.DESIGNER, None, self._version))
            if designer is not None
            else ()
        )
        chips_before = self.chip_states()
        notes_changed = [
            self._enterprise_findings.set_notes(notes_from_findings(enterprise_findings)),
            self._designer_findings.set_notes(notes_from_findings(designer_findings)),
        ]
        self.set_title(block_title(enterprise, designer))
        everything = (*enterprise_findings, *designer_findings)
        errors = sum(1 for finding in everything if finding.level is Level.ERROR)
        warnings = sum(1 for finding in everything if finding.level is Level.WARNING)
        self._errors_chip.setText(plural(errors, "ошибка", "ошибки", "ошибок"))
        self._errors_chip.setVisible(bool(errors))
        self._warnings_chip.setText(
            plural(warnings, "предупреждение", "предупреждения", "предупреждений")
        )
        self._warnings_chip.setVisible(bool(warnings))
        # Финальное ревью плана Б, F1: пересчёт размера окна свойств — только при смене
        # структуры (решение заказчика 21.11.2026); `refresh` идёт на каждое нажатие.
        if any(notes_changed) or self.chip_states() != chips_before:
            self.content_changed.emit()
