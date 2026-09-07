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

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget

from onecstarter.ui.theme import DARK, Palette

CHEVRON_BOX = 13
CHEVRON_THICKNESS = 1.7
TITLE_POINT_SIZE = 10
TITLE_LETTER_SPACING = 0.8


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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._accent = accent
        self._palette = DARK
        self._chevron = chevron_pixmap(False, DARK.accent)

        self._button = QToolButton()
        self._button.setObjectName(object_name)
        self._button.setText(title)
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

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(6)
        self._body.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._button)
        if self._rule is not None:
            layout.addWidget(self._rule)
        if note is not None:
            layout.addWidget(note)
        layout.addWidget(self._body)

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

    # -- внутреннее --------------------------------------------------------

    def _on_toggled(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._refresh_chevron()
        self.toggled.emit(checked)

    def _refresh_chevron(self) -> None:
        colour = self._palette.accent if self._accent else self._palette.text
        self._chevron = chevron_pixmap(self.is_expanded(), colour)
        self._button.setIcon(QIcon(self._chevron))
