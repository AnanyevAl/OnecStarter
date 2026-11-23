"""Конструктор параметров запуска (спека v4, §7.2; экран 2 мокапа).

Модальный диалог над одной строкой параметров. Единственный источник правды —
разобранная строка `_parsed` (`domain/cli_params.py`): дерево, список выбранных,
редакторы, предпросмотр и замечания перерисовываются из неё. Правка ключа —
`with_key`, поэтому фрагменты, которых пользователь не касался (в том числе
неизвестные ключи), остаются байт в байт (спека §4.1, п. 5).
"""  # noqa: RUF002, RUF100

from collections.abc import Callable, Sequence
from enum import Enum
from html import escape

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QRect, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QGuiApplication, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_catalog import (
    CLIENT_TITLES,
    MODE_TITLES,
    ArgKind,
    Catalog,
    CatalogKey,
    Client,
    Mode,
)
from onecstarter.domain.cli_params import (
    CheckContext,
    Finding,
    ParsedParams,
    Where,
    bind,
    check,
    key_name_of,
    parse,
    render,
    with_key,
    without_key,
)
from onecstarter.domain.version import VersionNumber
from onecstarter.security.secrets import contains_secret_arguments, redact_arguments
from onecstarter.services.param_sets import ParamSet, sets_for, upsert_set
from onecstarter.ui.command_line import CommandLineView, catalog_word_known
from onecstarter.ui.components import (
    Box,
    DialogFooter,
    FindingsList,
    bold_font,
    dim_label,
    mono_font,
    mono_span,
    notes_from_findings,
)
from onecstarter.ui.dialogs.buttons import PRIMARY, mark_button
from onecstarter.ui.theme import DARK, Palette

KEY_ROLE = Qt.ItemDataRole.UserRole
NO_SET = "—"
SET_BOX_WIDTH = 240
KEY_PANEL_WIDTH = 430
# План В, Б1 (повторная приёмка 21.11.2026): описание — в той же строке,  # noqa: RUF003
# что и имя (мокап, экран 2, `.k`). Две колонки с моноширинными именами  # noqa: RUF003
# выталкивали описание за край бокса.
SUMMARY_ROLE = Qt.ItemDataRole.UserRole + 1
SUMMARY_COLOUR_ROLE = Qt.ItemDataRole.UserRole + 2
SUMMARY_GAP = 6
SEARCH_PLACEHOLDER = "Поиск ключа: имя или слово из описания"
UNKNOWN_NOTE = "нет в каталоге: оставлен как есть"
GLUED_NOTE = "значение пишется через пробел"
SECRET_IN_SET_ANY = "Пароль в набор не сохраняется — уберите его из строки"  # noqa: RUF001
SECRET_IN_SET = "Пароль в набор не сохраняется — уберите ключ {name}"


def elide_summary(metrics: QFontMetrics, summary: str, width: int) -> str:
    """Описание в остаток строки: целиком, с «…» справа или пусто, если места нет совсем."""  # noqa: RUF002
    if width <= metrics.horizontalAdvance("…"):
        return ""
    return metrics.elidedText(summary, Qt.TextElideMode.ElideRight, width)


class KeyRowDelegate(QStyledItemDelegate):
    """Строка ключа: штатные фон, выделение и флажок, затем имя и описание двумя цветами.

    Имя — шрифтом и цветом элемента (моноширинный, `accent` или `text_dim`), описание —
    шрифтом дерева и цветом `SUMMARY_COLOUR_ROLE`, усечённое по ширине. Строки без
    описания (группы) рисуются штатно.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        summary = index.data(SUMMARY_ROLE)
        if not summary:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        name = opt.text
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        name_brush = index.data(Qt.ItemDataRole.ForegroundRole)
        name_colour = (
            name_brush.color() if isinstance(name_brush, QBrush) else opt.palette.text().color()
        )
        summary_font = widget.font() if widget is not None else opt.font
        painter.save()
        try:
            painter.setFont(opt.font)
            painter.setPen(name_colour)
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            painter.drawText(rect, int(align), name)
            left = rect.left() + QFontMetrics(opt.font).horizontalAdvance(name) + SUMMARY_GAP
            summary_rect = QRect(left, rect.top(), max(rect.right() - left, 0), rect.height())
            painter.setFont(summary_font)
            painter.setPen(QColor(str(index.data(SUMMARY_COLOUR_ROLE))))
            shown = elide_summary(QFontMetrics(summary_font), str(summary), summary_rect.width())
            painter.drawText(summary_rect, int(align), shown)
        finally:
            painter.restore()


class BuilderPurpose(Enum):
    WRITE = "write"  # «…» в свойствах базы
    ONCE = "once"  # Ctrl+F3 / Ctrl+F4, пункты меню


ACTION_LABELS = {
    BuilderPurpose.WRITE: "Применить",
    BuilderPurpose.ONCE: "Запустить один раз",
}


def ask_set_name(parent: QWidget) -> str | None:
    name, accepted = QInputDialog.getText(parent, "Сохранить как набор", "Имя набора:")
    return name.strip() if accepted and name.strip() else None


REPLACE_LABEL = "Заменить"
CANCEL_LABEL = "Отмена"


def replace_set_question(existing: ParamSet) -> str:
    return (
        f"Набор «{existing.name}» ({MODE_TITLES[existing.mode]}) уже есть. "  # noqa: RUF001
        "Заменить его текущей строкой?"  # noqa: RUF001
    )


def build_replace_set_box(parent: QWidget | None, existing: ParamSet) -> QMessageBox:
    """Вопрос о замене набора без показа — для тестов и `ask_replace_set`.

    Кнопка по умолчанию — «Отмена»: случайный Enter не должен затереть набор
    (решение заказчика 09.11.2026, финальное ревью блока 1, F5).
    """  # noqa: RUF002
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Сохранить как набор")
    box.setText(replace_set_question(existing))
    box.addButton(REPLACE_LABEL, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(CANCEL_LABEL, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box


def ask_replace_set(parent: QWidget, existing: ParamSet) -> bool:
    box = build_replace_set_box(parent, existing)
    box.exec()
    clicked = box.clickedButton()
    return clicked is not None and clicked.text() == REPLACE_LABEL


def run_builder_dialog(dialog: "ParamBuilderDialog") -> bool:
    return dialog.exec() == QDialog.DialogCode.Accepted


def _copy_to_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def inapplicable_reason(
    key: CatalogKey, mode: Mode, client: Client | None, version: VersionNumber | None
) -> str | None:
    if mode not in key.modes:
        return f"не для режима «{MODE_TITLES[mode]}»"
    if mode is Mode.ENTERPRISE and client is not None and key.clients and client not in key.clients:
        return f"не для клиента «{CLIENT_TITLES[client]}»"
    if version is not None and key.since is not None and version < key.since:
        return f"появился в {key.since}"
    if version is not None and key.until is not None and version > key.until:
        return f"убран после {key.until}"
    return None


def _meta(key: CatalogKey) -> str:
    modes = ", ".join(MODE_TITLES[mode] for mode in Mode if mode in key.modes)
    platform = f"с {key.since}" if key.since is not None else "нет данных о версиях"  # noqa: RUF001
    if key.until is not None:
        platform += f" по {key.until}"
    return f"Режим: {modes} · Платформа: {platform} · ИТС: {key.its}"


def describe_html(key: CatalogKey, palette: Palette) -> str:
    """Описание ключа (мокап, экран 2, стр. 196–197): имя — accent моно, мета — text_dim."""  # noqa: RUF002
    return (
        f'<span style="color:{palette.text_dim}">Описание:</span> '
        f"{mono_span(key.name, palette.accent)}"
        f" — {escape(key.summary)}<br>{escape(key.description)}<br>"
        f'<span style="color:{palette.text_dim}">{escape(_meta(key))}</span>'
    )


def _has_secret_value(parsed: ParsedParams) -> str | None:
    for token in parsed.key_tokens():
        key = token.key
        if key is None:
            continue
        values = bind(token).values
        if any(
            arg.kind is ArgKind.SECRET and value
            for arg, value in zip(key.args, values, strict=False)
        ):
            return key.name
    return None


def _attached_secret_name(parsed: ParsedParams) -> str | None:
    """Имя ключа, чей текст `redact_arguments` меняет: прижатый пароль (`/WSP"x"`) и т. п."""
    for token in parsed.key_tokens():
        if contains_secret_arguments(token.raw):
            return key_name_of(token.word)
    return "" if contains_secret_arguments(render(parsed)) else None


class ParamBuilderDialog(QDialog):
    def __init__(
        self,
        catalog: Catalog,
        *,
        title: str,
        mode: Mode,
        purpose: BuilderPurpose,
        text: str = "",
        client: Client | None = None,
        version: VersionNumber | None = None,
        mode_locked: bool = False,
        permanent: str = "",
        sets: Sequence[ParamSet] = (),
        save_set: Callable[[ParamSet], str | None] = lambda _set: None,
        ask_name: Callable[[QWidget], str | None] = ask_set_name,
        confirm_replace: Callable[[QWidget, ParamSet], bool] = ask_replace_set,
        preview: Callable[[Mode, str], str] = lambda _mode, text: redact_arguments(text),
        copy: Callable[[str], None] = _copy_to_clipboard,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._catalog = catalog
        self._mode = mode
        self._purpose = purpose
        self._client = client
        self._version = version
        self._permanent = parse(permanent, catalog)
        self._sets = tuple(sets)
        self._save_set = save_set
        self._ask_name = ask_name
        self._confirm_replace = confirm_replace
        self._preview = preview
        self._copy = copy
        self._palette = palette
        self._parsed = parse(text, catalog)
        self._current_row: int | None = None
        self._key_items: dict[str, QTreeWidgetItem] = {}
        self._editor_widgets: list[QWidget] = []

        self._set_box = QComboBox()
        self._set_box.setFixedWidth(SET_BOX_WIDTH)
        self._set_box.activated.connect(self._on_set_chosen)
        self._save_set_button = QPushButton("Сохранить как набор…")
        self._save_set_button.setAutoDefault(False)
        self._save_set_button.clicked.connect(self.save_as_set)
        # Мокап, экран 2 (стр. 162): режим — сегмент из двух кнопок, активная жёлтая.
        self._enterprise = QPushButton(MODE_TITLES[Mode.ENTERPRISE])
        self._designer = QPushButton(MODE_TITLES[Mode.DESIGNER])
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for button in (self._enterprise, self._designer):
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setEnabled(not mode_locked)
            self._mode_group.addButton(button)
        (self._enterprise if mode is Mode.ENTERPRISE else self._designer).setChecked(True)
        if mode_locked:
            # Запертый режим: серая жёлтая кнопка не отличалась бы от серой обычной.
            (self._designer if mode is Mode.ENTERPRISE else self._enterprise).setVisible(False)
        for button in (self._enterprise, self._designer):
            button.toggled.connect(self._on_mode_toggled)
        self._mark_mode()
        top = QHBoxLayout()
        top.addWidget(dim_label("Набор:"))  # noqa: RUF001
        top.addWidget(self._set_box)
        top.addWidget(self._save_set_button)
        top.addStretch(1)
        top.addWidget(dim_label("Режим:"))
        top.addWidget(self._enterprise)
        top.addWidget(self._designer)

        self._search = QLineEdit()
        self._search.setPlaceholderText(SEARCH_PLACEHOLDER)
        self._search.textChanged.connect(self.search)
        self._search.installEventFilter(self)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.setItemDelegate(KeyRowDelegate(self._tree))
        self._tree.itemChanged.connect(self._on_tree_changed)
        self._tree.currentItemChanged.connect(self._on_tree_current)
        # Имена — для фона в боксе (`#KeyTree, #SelectedKeys`, задача 5): типовое правило
        # потомка `#Box` задело бы выпадающие списки редакторов ключей (решение заказчика 1).
        self._tree.setObjectName("KeyTree")
        left = Box()
        left.body_layout().addWidget(self._search)
        left.body_layout().addWidget(self._tree, 1)

        self._selected = QListWidget()
        self._selected.currentRowChanged.connect(self._on_selected_row)
        self._editors = QWidget()
        self._editors_layout = QFormLayout(self._editors)
        self._remove_button = QPushButton("Убрать ключ")
        self._remove_button.setAutoDefault(False)
        self._remove_button.clicked.connect(self.remove_selected)
        self._description = QLabel()
        self._description.setWordWrap(True)
        self._description.setTextFormat(Qt.TextFormat.RichText)
        self._selected.setObjectName("SelectedKeys")
        right = Box("Выбранные ключи")
        right.body_layout().addWidget(self._selected)
        right.body_layout().addWidget(self._editors)
        right.body_layout().addWidget(self._remove_button)
        right.body_layout().addWidget(self._description)
        self._splitter = QSplitter()
        self._splitter.addWidget(left)
        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([KEY_PANEL_WIDTH, 520])

        self._preview_box = CommandLineView(palette)
        self._preview_box.setMaximumHeight(72)
        self._findings_label = FindingsList()
        self._notice = QLabel()
        self._notice.setWordWrap(True)
        copy_button = QPushButton("Копировать строку")
        copy_button.setAutoDefault(False)
        copy_button.clicked.connect(lambda: self._copy(self.preview_text()))
        self._action = QPushButton(ACTION_LABELS[purpose])
        self._action.setDefault(True)
        self._action.clicked.connect(self.accept)
        mark_button(self._action, PRIMARY)
        cancel = QPushButton("Отмена")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        self._footer = DialogFooter()
        self._footer.add_left(copy_button)
        self._footer.add_right(self._action)
        self._footer.add_right(cancel)

        content = QVBoxLayout()
        content.setContentsMargins(10, 10, 10, 8)
        content.addLayout(top)
        content.addWidget(self._splitter, 1)
        content.addWidget(dim_label("Командная строка, с которой стартует клиент:"))  # noqa: RUF001
        content.addWidget(self._preview_box)
        content.addWidget(self._findings_label)
        content.addWidget(self._notice)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content, 1)
        layout.addWidget(self._footer)
        self.resize(1000, 660)

        self._build_tree()
        self._fill_sets()
        self._refresh()

    # -- чтение для вызывающего и тестов -----------------------------------

    def result_text(self) -> str:
        return render(self._parsed)

    def result_mode(self) -> Mode:
        return self._mode

    def findings(self) -> tuple[Finding, ...]:
        if self._purpose is BuilderPurpose.ONCE:
            where = Where.ONCE
        else:
            where = Where.PERMANENT if self._mode is Mode.ENTERPRISE else Where.DESIGNER_LINE
        context = CheckContext(
            where=where,
            mode=self._mode,
            client=self._client if self._mode is Mode.ENTERPRISE else None,
            version=self._version,
            permanent=self._permanent if where is Where.ONCE else None,
        )
        return check(self._parsed, context)

    def preview_text(self) -> str:
        return self._preview(self._mode, self.result_text())

    def notice_text(self) -> str:
        return self._notice.text()

    def action_label(self) -> str:
        return self._action.text()

    def set_options(self) -> list[str]:
        return [self._set_box.itemText(index) for index in range(self._set_box.count())]

    def mode_button(self, mode: Mode) -> QPushButton:
        return self._enterprise if mode is Mode.ENTERPRISE else self._designer

    def key_splitter(self) -> QSplitter:
        return self._splitter

    def action_button(self) -> QPushButton:
        return self._action

    def footer(self) -> DialogFooter:
        return self._footer

    def set_box(self) -> QComboBox:
        return self._set_box

    def mode_switch_enabled(self) -> bool:
        return self._enterprise.isEnabled()

    def tree_key_names(self) -> list[str]:
        return [
            str(item.data(0, KEY_ROLE))
            for item in self._key_items.values()
            if not item.isHidden() and not item.parent().isHidden()
        ]

    def is_dimmed(self, name: str) -> bool:
        item = self._key_items[name.casefold()]
        return item.foreground(0).color().name() == self._palette.text_dim

    def key_item(self, name: str) -> QTreeWidgetItem:
        return self._key_items[name.casefold()]

    def selected_colours(self) -> list[str]:
        return [
            self._selected.item(row).foreground().color().name()
            for row in range(self._selected.count())
        ]

    def description_label(self) -> QLabel:
        return self._description

    def preview_view(self) -> CommandLineView:
        return self._preview_box

    def findings_list(self) -> FindingsList:
        return self._findings_label

    def selected_texts(self) -> list[str]:
        return [self._selected.item(row).text() for row in range(self._selected.count())]

    # -- действия -------------------------------------------------------------

    def set_mode(self, mode: Mode) -> None:
        (self._enterprise if mode is Mode.ENTERPRISE else self._designer).setChecked(True)

    def set_key_checked(self, name: str, checked: bool) -> None:
        key = self._catalog.key(name)
        if key is None:
            return
        if checked and self._parsed.find(key.name) is None:
            self._parsed = with_key(self._parsed, key, (), self._catalog)
            self._current_row = len(self._parsed.key_tokens()) - 1
        elif not checked:
            self._parsed = without_key(self._parsed, key.name, self._catalog)
            self._current_row = None
        self._refresh()

    def select_key(self, name: str) -> None:
        wanted = name.casefold()
        for row, token in enumerate(self._parsed.key_tokens()):
            label = token.key.name if token.key is not None else token.word
            if label.casefold() == wanted:
                self._current_row = row
                break
        self._refresh()

    def set_arg(self, name: str, index: int, value: str | None) -> None:
        self._apply_arg(name, index, value)
        self._refresh()

    def remove_selected(self) -> None:
        row = self._current_row
        tokens = self._parsed.key_tokens()
        if row is None or row >= len(tokens):
            return
        target = tokens[row]
        kept = [token.raw for token in self._parsed.tokens if token is not target]
        text = "".join(kept).lstrip(" \t") if kept else ""
        self._parsed = parse(text + (self._parsed.tail if kept else ""), self._catalog)
        remaining = len(self._parsed.key_tokens())
        # Приёмка 21.11.2026, В7: выделить соседа — поля и описание не пропадают.  # noqa: RUF003
        self._current_row = min(row, remaining - 1) if remaining else None
        self._refresh()

    def apply_set(self, name: str) -> None:
        chosen = next((item for item in self._sets if item.name == name), None)
        if chosen is None:
            return
        parsed = self._parsed
        for token in parse(chosen.params, self._catalog).key_tokens():
            if token.key is not None:
                parsed = with_key(parsed, token.key, bind(token).values, self._catalog)
            else:
                base = render(parsed).rstrip(" \t")
                joined = f"{base} {token.raw.strip()}" if base else token.raw.strip()
                parsed = parse(joined, self._catalog)
        self._parsed = parsed
        self._refresh()

    def search(self, text: str) -> None:
        needle = text.strip().casefold()
        for index in range(self._tree.topLevelItemCount()):
            node = self._tree.topLevelItem(index)
            if node is None:
                continue
            visible = 0
            for child_index in range(node.childCount()):
                child = node.child(child_index)
                key = self._catalog.key(str(child.data(0, KEY_ROLE)))
                haystack = f"{key.name} {key.summary} {key.description}".casefold() if key else ""
                hidden = bool(needle) and needle not in haystack
                child.setHidden(hidden)
                visible += 0 if hidden else 1
            node.setHidden(visible == 0)

    def save_as_set(self) -> None:
        secret = _has_secret_value(self._parsed) or _attached_secret_name(self._parsed)
        if secret is not None:
            self._notice.setText(SECRET_IN_SET.format(name=secret) if secret else SECRET_IN_SET_ANY)
            return
        name = self._ask_name(self)
        if not name:
            return
        # Решение заказчика 09.11.2026 (F5): `upsert_set` сравнивает имена без учёта
        # регистра и режима — набор с таким именем заменяется только после вопроса.  # noqa: RUF003
        wanted = name.strip().casefold()
        existing = next((s for s in self._sets if s.name.strip().casefold() == wanted), None)
        if existing is not None and not self._confirm_replace(self, existing):
            return
        new = ParamSet(name, self._mode, self.result_text())
        error = self._save_set(new)
        if error:
            self._notice.setText(error)
            return
        self._notice.setText(f"Набор «{name}» сохранён")  # noqa: RUF001
        self._sets = upsert_set(self._sets, new)
        self._fill_sets()

    # -- внутреннее -------------------------------------------------------------

    def _apply_arg(self, name: str, index: int, value: str | None) -> None:
        token = self._parsed.find(name)
        if token is None or token.key is None:
            return
        key = token.key
        values = list(bind(token).values)
        values += [None] * (len(key.args) - len(values))
        values[index] = value
        self._parsed = with_key(self._parsed, key, tuple(values), self._catalog)

    def _build_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        self._key_items = {}
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        bold = bold_font(self._tree.font())
        mono = mono_font()
        for group in self._catalog.groups:
            keys = [key for key in self._catalog.group_keys(group.id) if not key.managed]
            if not keys:
                continue
            node = QTreeWidgetItem([group.title])
            node.setFlags(Qt.ItemFlag.ItemIsEnabled)
            node.setFont(0, bold)  # мокап `.tree .g`
            self._tree.addTopLevelItem(node)
            node.setFirstColumnSpanned(True)
            for key in keys:
                child = QTreeWidgetItem([key.name])
                child.setData(0, SUMMARY_ROLE, f"— {key.summary}")
                child.setData(0, KEY_ROLE, key.name)
                child.setFlags(flags)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setFont(0, mono)
                node.addChild(child)
                self._key_items[key.name.casefold()] = child
            node.setExpanded(True)
        self._tree.blockSignals(False)
        self._mark_applicability()

    def _mark_applicability(self) -> None:
        self._tree.blockSignals(True)
        for item in self._key_items.values():
            key = self._catalog.key(str(item.data(0, KEY_ROLE)))
            if key is None:
                continue
            reason = inapplicable_reason(key, self._mode, self._client, self._version)
            tip = reason or key.summary
            item.setToolTip(0, tip)
            palette = self._palette
            item.setForeground(0, QColor(palette.text_dim if reason else palette.accent))
            item.setData(
                0, SUMMARY_COLOUR_ROLE, palette.text_disabled if reason else palette.text_dim
            )
        self._tree.blockSignals(False)

    def _fill_sets(self) -> None:
        self._set_box.blockSignals(True)
        self._set_box.clear()
        self._set_box.addItem(NO_SET)
        for item in sets_for(self._sets, self._mode):
            self._set_box.addItem(item.name)
        self._set_box.blockSignals(False)

    def _refresh(self) -> None:
        self._refresh_views()
        self._rebuild_editors()

    def _refresh_views(self) -> None:
        present = {
            token.key.name.casefold()
            for token in self._parsed.key_tokens()
            if token.key is not None
        }
        self._tree.blockSignals(True)
        for name, item in self._key_items.items():
            state = Qt.CheckState.Checked if name in present else Qt.CheckState.Unchecked
            item.setCheckState(0, state)
        self._tree.blockSignals(False)

        self._selected.blockSignals(True)
        self._selected.clear()
        mono = mono_font()
        for token in self._parsed.key_tokens():
            colour = self._palette.unknown
            if token.key is None and token.glued is not None:
                # Прижатый известный ключ (Ф1): имя без значения — в нём бывает пароль.
                text = f"{token.glued.name} — {GLUED_NOTE}"
            elif token.key is None:
                text = f"{key_name_of(token.word)} — {UNKNOWN_NOTE}"
            else:
                text = redact_arguments(token.raw.strip())
                colour = self._palette.accent
            row = QListWidgetItem(text)
            row.setForeground(QColor(colour))  # решение заказчика 4
            row.setFont(mono)
            self._selected.addItem(row)
        if self._current_row is not None and self._current_row < self._selected.count():
            self._selected.setCurrentRow(self._current_row)
        self._selected.blockSignals(False)

        line = self.preview_text()
        base = self._preview(self._mode, "")
        self._preview_box.show_line(
            line,
            base_length=len(base) if base and line.startswith(base) else 0,
            is_known=catalog_word_known(self._catalog),
        )
        self._findings_label.set_notes(notes_from_findings(self.findings()))

    def _rebuild_editors(self) -> None:
        while self._editors_layout.rowCount():
            self._editors_layout.removeRow(0)
        self._editor_widgets = []
        tokens = self._parsed.key_tokens()
        row = self._current_row
        token = tokens[row] if row is not None and row < len(tokens) else None
        self._remove_button.setEnabled(token is not None)
        if token is None or token.key is None:
            self._description.setText("")
            return
        key = token.key
        self._description.setText(describe_html(key, self._palette))
        values = bind(token).values
        if not key.args:
            self._editors_layout.addRow(QLabel("аргументов нет"))
        name = key.name
        for index, arg in enumerate(key.args):
            value = values[index] if index < len(values) else None
            label = arg.label or arg.flag or arg.kind.value
            if arg.kind is ArgKind.FLAG:
                box = QCheckBox(f"{arg.flag} ({arg.label})" if arg.label else str(arg.flag))
                box.setChecked(value is not None)
                box.toggled.connect(
                    lambda on, i=index: self._edit_from_widget(name, i, "" if on else None)
                )
                self._editors_layout.addRow(box)
                self._editor_widgets.append(box)
            elif arg.kind is ArgKind.ENUM:
                combo = QComboBox()
                combo.addItem("", None)
                for option in arg.values:
                    combo.addItem(option, option)
                found = combo.findData(value) if value else 0
                combo.setCurrentIndex(max(found, 0))
                combo.activated.connect(
                    lambda _row, c=combo, i=index: self._edit_from_widget(name, i, c.currentData())
                )
                self._editors_layout.addRow(label, combo)
                self._editor_widgets.append(combo)
            else:
                edit = QLineEdit(value or "")
                if arg.kind is ArgKind.SECRET:
                    edit.setEchoMode(QLineEdit.EchoMode.Password)
                edit.editingFinished.connect(
                    lambda e=edit, i=index: self._edit_from_widget(name, i, e.text() or None)
                )
                # Приёмка 21.11.2026, В8: и по вводу.  # noqa: RUF003
                edit.textEdited.connect(
                    lambda text, e=edit, i=index: self._edit_from_widget(
                        name, i, text or None, sender=e
                    )
                )
                self._editors_layout.addRow(label, edit)
                self._editor_widgets.append(edit)

    def _edit_from_widget(
        self, name: str, index: int, value: str | None, sender: QWidget | None = None
    ) -> None:
        """Правка из редактора. Значение не изменилось — строку не трогаем (решение 08.11.2026).

        Редакторы не пересоздаются — виджет-отправитель жив; остальные подтягиваются
        из `_parsed` с заблокированными сигналами.
        """  # noqa: RUF002
        token = self._parsed.find(name)
        if token is None or token.key is None:
            return
        values = bind(token).values
        if (values[index] if index < len(values) else None) == value:
            return
        self._apply_arg(name, index, value)
        self._refresh_views()
        self._sync_editors(skip=sender)

    def _sync_editors(self, skip: QWidget | None = None) -> None:
        row = self._current_row
        tokens = self._parsed.key_tokens()
        token = tokens[row] if row is not None and row < len(tokens) else None
        if token is None or token.key is None:
            return
        values = bind(token).values
        for index, widget in enumerate(self._editor_widgets):
            if widget is skip:
                continue
            value = values[index] if index < len(values) else None
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(value is not None)
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(widget.findData(value) if value else 0, 0))
            elif isinstance(widget, QLineEdit) and widget.text() != (value or ""):
                widget.setText(value or "")
            widget.blockSignals(False)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Enter в поиске не нажимает кнопку действия: только переходит к первому найденному."""
        if (
            watched is self._search
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            self._focus_first_match()
            return True
        return super().eventFilter(watched, event)

    def _focus_first_match(self) -> None:
        for index in range(self._tree.topLevelItemCount()):
            node = self._tree.topLevelItem(index)
            if node is None or node.isHidden():
                continue
            for child_index in range(node.childCount()):
                child = node.child(child_index)
                if not child.isHidden():
                    self._tree.setCurrentItem(child)
                    return

    def _on_tree_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        name = item.data(0, KEY_ROLE)
        if isinstance(name, str):
            self.set_key_checked(name, item.checkState(0) == Qt.CheckState.Checked)

    def _on_tree_current(self, current: QTreeWidgetItem | None, _previous: object) -> None:
        name = current.data(0, KEY_ROLE) if current is not None else None
        key = self._catalog.key(name) if isinstance(name, str) else None
        if key is not None:
            self._description.setText(describe_html(key, self._palette))

    def _on_selected_row(self, row: int) -> None:
        self._current_row = row if row >= 0 else None
        self._rebuild_editors()

    def _mark_mode(self) -> None:
        for button in (self._enterprise, self._designer):
            mark_button(button, PRIMARY if button.isChecked() else None)

    def _on_mode_toggled(self, checked: bool) -> None:
        if not checked:
            return
        self._mark_mode()
        self._mode = Mode.ENTERPRISE if self._enterprise.isChecked() else Mode.DESIGNER
        self._mark_applicability()
        self._fill_sets()
        self._refresh()

    def _on_set_chosen(self, index: int) -> None:
        if index > 0:
            self.apply_set(self._set_box.itemText(index))
            self._set_box.setCurrentIndex(0)
