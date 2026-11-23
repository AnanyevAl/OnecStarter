"""Общие виджеты экранов v4 по мокапу (план Б): подписи, формы, бокс, полоса кнопок,
выноски, чипы.

Вид задают правила темы по objectName и динамическому свойству (`ui/theme.py`), а не
`setStyleSheet` на виджете: смена темы перекрашивает их без `apply_palette`.
"""  # noqa: RUF002

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.cli_params import Finding, Level

MONO_FAMILIES = ("Consolas", "Cascadia Mono")
FORM_LABEL_WIDTH = 170
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def repolish(widget: QWidget) -> None:
    """Переприменить QSS после смены динамического свойства (`role`, `level`)."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def mono_font(point_size: int = 9) -> QFont:
    """Моноширинный шрифт мокапа (`code`, `.mono`: Consolas 12px ≈ 9pt) — для элементов
    моделей, которым QSS по objectName не достаётся."""
    font = QFont()
    font.setFamilies(list(MONO_FAMILIES))
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    return font


def mono_span(text: str, colour: str) -> str:
    """Моноширинный фрагмент rich text цветом `colour` (мокап `code`, `.k`).

    Текст — через `html.escape` (инвариант 5 и GC: пользовательский текст в rich text только
    так). Семейство — первое из `MONO_FAMILIES`: одно место вместо копий в каждом экране.
    """
    return f'<span style="color:{colour}; font-family:{MONO_FAMILIES[0]}">{escape(text)}</span>'


def bold_font(font: QFont) -> QFont:
    """Жирная копия шрифта (мокап `.g` — группы деревьев, подпись «Базы:»)."""
    bold = QFont(font)
    bold.setBold(True)
    return bold


def _named_label(name: str, text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    return label


def dim_label(text: str = "") -> QLabel:
    return _named_label("DimLabel", text)


def hint_label(text: str = "") -> QLabel:
    label = _named_label("Hint", text)
    label.setWordWrap(True)
    return label


def accent_label(text: str) -> QLabel:
    return _named_label("AccentLabel", text)


MENU_SHORTCUT_GAP = 24


def widen_for_shortcuts(menu: QMenu, gap: int = MENU_SHORTCUT_GAP) -> None:
    """План В, Б9 (повторная приёмка 21.11.2026): запас ширины меню с сочетаниями.

    [проверено] снимок меню 21.11.2026: сочетания начинаются в одной колонке у правого края,
    ширина меню — по самому длинному названию, и «Запустить с параметрами…» почти касалось
    «Ctrl+F3». Лишняя ширина отодвигает колонку сочетаний от названий. Вызывать после
    добавления всех пунктов. Повторный вызов запас не удваивает: [проверено] 22.11.2026
    офскрин-пробой — `sizeHint` показанного и дополненного меню учитывает прежний
    `minimumWidth`, поэтому минимум сбрасывается перед замером.
    """  # noqa: RUF002
    if not any("\t" in action.text() for action in menu.actions()):
        return
    menu.setMinimumWidth(0)
    menu.ensurePolished()
    menu.setMinimumWidth(menu.sizeHint().width() + gap)


def align_form(form: QFormLayout, *, label_width: int = FORM_LABEL_WIDTH) -> None:
    """Подписи справа, общая колонка, цвет `text_dim` (мокап, экран 1: `.form label`).

    Звать после того, как строки добавлены. Подписи с уже заданным objectName
    (`AccentLabel`) не переименовываются. Одна ширина нужна потому, что в окне свойств
    три независимые формы (основная и два блока) — иначе колонки подписей разные
    (аудит плана Б, 1.6). Выравнивание ставится и метке: при минимальной ширине
    больше текста текст иначе остался бы прижатым влево внутри неё.
    """  # noqa: RUF002
    form.setLabelAlignment(_RIGHT)
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        label = item.widget() if item is not None else None
        if not isinstance(label, QLabel):
            continue
        if not label.objectName():
            label.setObjectName("FormLabel")
        label.setMinimumWidth(label_width)
        label.setAlignment(_RIGHT)


class Box(QFrame):
    """`.box` мокапа: рамка, фон `surface`, полоса заголовка `.box h4` (`#BoxTitle`)."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Box")
        self._title = QLabel(title)
        self._title.setObjectName("BoxTitle")
        self._title.setVisible(bool(title))
        self._body = QVBoxLayout()
        self._body.setContentsMargins(8, 8, 8, 8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title)
        layout.addLayout(self._body, 1)

    def body_layout(self) -> QVBoxLayout:
        return self._body

    def title_label(self) -> QLabel:
        return self._title

    def set_title(self, text: str) -> None:
        self._title.setText(text)
        self._title.setVisible(bool(text))


class DialogFooter(QWidget):
    """`.foot` мокапа: полоса `surface`, сверху линия; слева кнопка или подсказка, справа действия.

    Растяжка — пружина `Expanding`: при видимой подсказке место забирает она (у неё
    stretch 1), без неё — пружина, и кнопки действий не растягиваются.
    """  # noqa: RUF002

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DialogFooter")
        # Без атрибута фон из QSS у простого QWidget-наследника не рисуется.  # noqa: RUF003
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._hint = hint_label()
        self._hint.setVisible(False)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.addWidget(self._hint, 1)
        self._layout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        self._left_count = 0

    def add_left(self, widget: QWidget, stretch: int = 0) -> None:
        self._layout.insertWidget(self._left_count, widget, stretch)
        self._left_count += 1

    def add_right(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def set_hint(self, text: str) -> None:
        self._hint.setText(text)
        self._hint.setVisible(bool(text))

    def hint_text(self) -> str:
        return self._hint.text()

    def hint_label(self) -> QLabel:
        return self._hint


@dataclass(frozen=True)
class Note:
    """Одно сообщение выноски. `lead` — первое предложение жирным (мокап, экран 5)."""

    level: Level
    text: str
    lead: bool = False


def notes_from_findings(findings: Iterable[Finding]) -> list[Note]:
    return [Note(finding.level, finding.text) for finding in findings]


def _lead_html(text: str) -> str:
    head, separator, tail = text.partition(". ")
    if not separator:
        return f"<b>{escape(text)}</b>"
    return f"<b>{escape(head)}.</b> {escape(tail)}"


class FindingsList(QWidget):
    """Замечания выносками `.msg`: метка на замечание, уровень — свойство `level` (В5).

    Решение заказчика 2 (21.11.2026): полоса слева и слабый фон по уровню; текст ошибки —
    `problem`, остальных — обычный (правила `QLabel#Callout` темы). Метки пересоздаются
    только при смене набора: свойство ставится до первой полировки, `repolish` не нужен.
    Текст без `lead` — `PlainText`: в замечаниях бывают имена ключей из строки пользователя.
    """  # noqa: RUF002

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._notes: tuple[Note, ...] = ()
        self._labels: list[QLabel] = []
        self.setVisible(False)

    def set_notes(self, notes: Sequence[Note]) -> bool:
        """Ставит набор замечаний; `True`, если он изменился (финальное ревью плана Б, F1)."""
        fresh = tuple(notes)
        if fresh == self._notes:
            return False
        self._notes = fresh
        for label in self._labels:
            self._layout.removeWidget(label)
            label.hide()
            label.deleteLater()
        self._labels = []
        for note in fresh:
            label = QLabel()
            label.setObjectName("Callout")
            label.setProperty("level", note.level.value)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if note.lead:
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setText(_lead_html(note.text))
            else:
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setText(note.text)
            self._layout.addWidget(label)
            self._labels.append(label)
        self.setVisible(bool(fresh))
        return True

    def labels(self) -> list[QLabel]:
        return list(self._labels)

    def texts(self) -> list[str]:
        return [note.text for note in self._notes]

    def levels(self) -> list[str]:
        return [note.level.value for note in self._notes]


class Chip(QLabel):
    """`.chip` мокапа: счётчик-«пилюля» (экран 1, строка заголовка блока)."""

    def __init__(
        self, level: Level | None = None, text: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self._level: Level | None = None
        self.set_level(level)

    def set_level(self, level: Level | None) -> None:
        self._level = level
        self.setProperty("level", level.value if level is not None else None)
        repolish(self)

    def level(self) -> Level | None:
        return self._level
