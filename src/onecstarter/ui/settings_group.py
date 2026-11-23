"""Сворачиваемая группа настроек: заголовок-кнопка, разделитель, тело.

Шеврон рисуется `QPainter`-ом (спека §1.3). Два отвергнутых способа:
глиф `▸` зависит от наличия символа в шрифте — в офскрин-прогоне мокапа
он выходил плашкой, — а `QToolButton.setArrowType` рисует залитый
треугольник, а не «>», и вид зависит ещё и от темы оформления Windows.
Рисованный шеврон не зависит ни от того, ни от другого.

Заголовок — `QToolButton`, а не `QLabel` с `mousePressEvent`: кнопка даёт
фокус по `Tab`, срабатывание пробелом и `Enter` и роль в дереве
доступности бесплатно, а ручная обработка мыши на метке — ничего из этого.

Шрифт заголовка ставится кодом, а не в `stylesheet()`: Qt Style Sheets
не поддерживают `letter-spacing`, а разрядка есть в утверждённом мокапе.
Держать часть свойств шрифта в QSS, а часть в `setFont` нельзя — они
перебивают друг друга непредсказуемо, поэтому в QSS остаются только цвет
и «хром» (см. `theme.py`).
"""  # noqa: RUF002

import html

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.ui.theme import DARK, Palette

CHEVRON_BOX = 13
CHEVRON_THICKNESS = 1.7
TITLE_POINT_SIZE = 10
TITLE_LETTER_SPACING = 0.8
SUMMARY_SEPARATOR = " — "
# Предпроверка, п. 7: желаемая ширина сводки. Без предела `sizeHint` полного адреса
# хранилища уходил в `adjustSize` окна свойств — окно открывалось шириной до 2/3 экрана.
SUMMARY_HINT_MAX = 320


def chevron_pixmap(expanded: bool, colour: str, box: int = CHEVRON_BOX) -> QPixmap:
    """«>» в свёрнутом виде, он же повёрнутый вниз — в раскрытом."""
    pixmap = QPixmap(box, box)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), CHEVRON_THICKNESS)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    near, far, mid = 4.0, box - 4.0, box / 2.0
    path = QPainterPath()
    if expanded:
        path.moveTo(QPointF(near, mid - 1.5))
        path.lineTo(QPointF(mid, far - 1.5))
        path.lineTo(QPointF(far, mid - 1.5))
    else:
        path.moveTo(QPointF(mid - 1.5, near))
        path.lineTo(QPointF(far - 1.5, mid))
        path.lineTo(QPointF(mid - 1.5, far))
    painter.drawPath(path)
    painter.end()
    return pixmap


class _SummaryLabel(QLabel):
    """Сводка заголовка блока: щелчок сворачивает блок, длинный текст — «…» посередине.

    План В, Б4 (решение заказчика 21.11.2026): длинный адрес хранилища расширял форму свойств.
    Минимальная ширина — «— …», желаемая — полный текст, но не больше `SUMMARY_HINT_MAX`;
    свободное место строки заголовка метка забирает растяжкой. Показанный текст считается
    от фактической ширины, полный — во всплывающей подсказке, экранированный: в сводке адрес
    и пользователь из полей, а Qt распознаёт rich text в подсказках сам.
    """  # noqa: RUF002

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        tip = f"<p style='white-space:pre'>{html.escape(text)}</p>" if text else ""
        self.setToolTip(tip)
        self._show_elided()
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        base = super().sizeHint()
        wanted = self.fontMetrics().horizontalAdvance(self._full) + 2
        return QSize(min(wanted, SUMMARY_HINT_MAX), base.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        base = super().minimumSizeHint()
        return QSize(self.fontMetrics().horizontalAdvance("— …"), base.height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._show_elided()

    def _show_elided(self) -> None:
        width = self.contentsRect().width()
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, width)
        if shown != self.text():
            self.setText(shown)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class CollapsibleGroup(QWidget):
    """Заголовок-кнопка, необязательные разделитель и подпись, скрываемое тело."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        *,
        accent: bool = True,
        rule: bool = True,
        note: QWidget | None = None,
        object_name: str = "SettingsGroupLabel",
        summary: bool = False,
        rule_above: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._accent = accent
        self._palette = DARK
        self._chevron = chevron_pixmap(False, DARK.accent)

        self._button = QToolButton()
        self._button.setObjectName(object_name)
        self._button.setCheckable(True)
        self._button.setChecked(False)
        self._button.setAutoRaise(True)
        self._button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        font = self._button.font()
        font.setBold(True)
        if accent:
            font.setPointSize(TITLE_POINT_SIZE)
            font.setLetterSpacing(
                font.SpacingType.AbsoluteSpacing, TITLE_LETTER_SPACING
            )
        self._button.setFont(font)
        self._button.toggled.connect(self._on_toggled)

        self._rule: QFrame | None = None
        if rule:
            self._rule = QFrame()
            self._rule.setFrameShape(QFrame.Shape.HLine)
            self._rule.setFixedHeight(1)

        self._rule_above: QFrame | None = None
        if rule_above:
            self._rule_above = QFrame()
            self._rule_above.setFrameShape(QFrame.Shape.HLine)
            self._rule_above.setFixedHeight(1)

        # Мокап v4, экран 1: имя жирным, сводка обычным весом и text_dim, справа чипы.
        # QToolButton rich text не умеет — строка заголовка из кнопки и метки (план Б).
        self._summary: _SummaryLabel | None = None
        self._header: QWidget | None = None
        self._header_layout: QHBoxLayout | None = None
        if summary:
            self._summary = _SummaryLabel()
            self._summary.setObjectName("BlockSummary")
            # Сводка хранилища — адрес и пользователь из полей: только PlainText.
            self._summary.setTextFormat(Qt.TextFormat.PlainText)
            self._summary.setCursor(Qt.CursorShape.PointingHandCursor)
            self._summary.clicked.connect(self._button.toggle)
            self._header = QWidget()
            self._header_layout = QHBoxLayout(self._header)
            self._header_layout.setContentsMargins(0, 0, 0, 0)
            self._header_layout.setSpacing(6)
            self._header_layout.addWidget(self._button)
            self._header_layout.addWidget(self._summary, 1)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(6)
        self._body.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if self._rule_above is not None:
            layout.addWidget(self._rule_above)
        layout.addWidget(self._header if self._header is not None else self._button)
        if self._rule is not None:
            layout.addWidget(self._rule)
        if note is not None:
            layout.addWidget(note)
        layout.addWidget(self._body)

        self.set_title(title)
        self.set_palette(DARK)

    # -- состояние ---------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        self._button.setChecked(expanded)

    def is_expanded(self) -> bool:
        return self._button.isChecked()

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        """Сменить текст заголовка; у группы со сводкой — голова в кнопку, хвост в сводку."""  # noqa: RUF002
        self._title = title
        if self._summary is None:
            self._button.setText(title)
            return
        head, separator, tail = title.partition(SUMMARY_SEPARATOR)
        self._button.setText(head)
        self._summary.set_full_text(f"— {tail}" if separator else "")
        self._summary.setVisible(bool(separator))

    def summary_label(self) -> _SummaryLabel | None:
        return self._summary

    def header_row(self) -> QWidget | None:
        return self._header

    def add_header_widget(self, widget: QWidget) -> None:
        """Виджет справа в строке заголовка (чипы счётчиков блока свойств)."""
        if self._header_layout is None:
            raise ValueError("правый слот есть только у группы со сводкой")  # noqa: RUF001
        self._header_layout.addWidget(widget)

    def rule_above(self) -> QFrame | None:
        return self._rule_above

    def button(self) -> QToolButton:
        """Заголовок — тестам, проверяющим срабатывание по клику и фокус."""
        return self._button

    def chevron(self) -> QPixmap:
        """Текущая картинка шеврона — тестам смены темы."""
        return self._chevron

    def set_palette(self, palette: Palette) -> None:
        """Перекрасить заголовок, шеврон и разделитель под действующую тему."""
        self._palette = palette
        self._refresh_chevron()
        if self._rule is not None:
            self._rule.setStyleSheet(f"background: {palette.border}; border: none;")
        if self._rule_above is not None:
            self._rule_above.setStyleSheet(f"background: {palette.border}; border: none;")

    # -- внутреннее --------------------------------------------------------

    def _on_toggled(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._refresh_chevron()
        self.toggled.emit(checked)

    def _refresh_chevron(self) -> None:
        colour = self._palette.accent if self._accent else self._palette.text
        self._chevron = chevron_pixmap(self.is_expanded(), colour)
        self._button.setIcon(QIcon(self._chevron))
