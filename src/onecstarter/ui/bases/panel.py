"""Панель свойств под деревом — вариант B мокапа.

Заголовок (значок вида + имя + вид словом), путь моноширинным, кнопки
действий. Read-only QLineEdit, а не QLabel: поле даёт выделение и Ctrl+C
штатно. Расчёт содержимого — services/connection.panel_card, здесь только
показ и два действия.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services.connection import PanelCard, panel_card
from onecstarter.ui.bases.icons import placement_icon
from onecstarter.ui.theme import Palette


def open_in_explorer(path: str) -> bool:
    """Открыть каталог проводником. `False` — каталога нет или отказ системы."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


_EMPTY_CARD = panel_card(None, None, "")


class ConnectionPanel(QWidget):
    def __init__(
        self,
        *,
        open_directory: Callable[[str], bool] = open_in_explorer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionPanel")
        # Фон и верхняя граница приходят из QSS; без WA_StyledBackground
        # QWidget правила фона к себе не применяет вовсе.  # noqa: RUF003
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._open_directory = open_directory
        self._card = _EMPTY_CARD

        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        self._title = QLabel()
        self._kind_word = QLabel()
        self._kind_word.setObjectName("PanelKindWord")
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(7)
        title_row.addWidget(self._icon)
        title_row.addWidget(self._title)
        title_row.addWidget(self._kind_word)
        title_row.addStretch(1)

        self._field = QLineEdit()
        self._field.setObjectName("ConnectionPath")
        self._field.setReadOnly(True)

        self._copy = QPushButton("Копировать")
        self._copy.clicked.connect(self._do_copy)
        self._open = QPushButton("Открыть каталог")
        self._open.clicked.connect(self._do_open)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        actions.addWidget(self._copy)
        actions.addWidget(self._open)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        layout.addLayout(title_row)
        layout.addWidget(self._field)
        layout.addLayout(actions)
        self.show_card(_EMPTY_CARD, None)

    def show_card(self, card: PanelCard, palette: Palette | None) -> None:
        """Показать карточку. Палитра нужна значку и цвету подсказки; None — оба

        не применяются. None допустим только у стартового пустого состояния
        в __init__: у пустой карточки значка нет по построению, а до первого
        реального show_card подсказку красить ещё не во что.

        Placeholder QLineEdit Qt красит из системной QPalette, а не из
        stylesheet (ThemeController применяет только stylesheet) — поэтому
        цвет подсказки выставляется здесь явно, при каждом вызове, поверх
        палитры самого поля (см. спека рестайла §4, находка финального
        ревью Important 1). Курсив — тем же приёмом мокапа: подсказка
        курсивом, путь — прямым шрифтом.
        """  # noqa: RUF002
        self._card = card
        has_title = card.title is not None
        self._title.setVisible(has_title)
        self._title.setText(card.title or "")
        self._kind_word.setVisible(card.kind_word is not None)
        self._kind_word.setText(f"· {card.kind_word}" if card.kind_word else "")
        show_icon = card.icon_kind is not None and palette is not None
        self._icon.setVisible(show_icon)
        if card.icon_kind is not None and palette is not None:
            self._icon.setPixmap(placement_icon(card.icon_kind, palette).pixmap(16, 16))
        path_text = card.path.text if card.path else ""
        self._field.setText(path_text)
        note = card.path.note if card.path else None
        self._field.setPlaceholderText(card.hint or note or "")
        if palette is not None:
            field_palette = self._field.palette()
            field_palette.setColor(
                QPalette.ColorRole.PlaceholderText, QColor(palette.text_dim)
            )
            self._field.setPalette(field_palette)
        field_font = self._field.font()
        field_font.setItalic(not path_text)
        self._field.setFont(field_font)
        self._copy.setVisible(card.show_actions)
        self._open.setVisible(card.show_actions)
        self._copy.setEnabled(card.path is not None and card.path.copyable)
        self._open.setEnabled(card.path is not None and card.path.directory is not None)

    def text(self) -> str:
        return self._field.text()

    def placeholder(self) -> str:
        return self._field.placeholderText()

    def title_text(self) -> str:
        parts = [self._title.text()] if self._title.text() else []
        if self._kind_word.text():
            parts.append(self._kind_word.text().removeprefix("· "))
        return " · ".join(parts)

    def path_field(self) -> QLineEdit:
        return self._field

    def copy_button(self) -> QPushButton:
        return self._copy

    def open_button(self) -> QPushButton:
        return self._open

    def _do_copy(self) -> None:
        if self._card.path is not None:
            QApplication.clipboard().setText(self._card.path.text)

    def _do_open(self) -> None:
        directory = (self._card.path.directory if self._card.path else None) or ""
        if not self._open_directory(directory):
            # Молчание здесь читалось бы как «открылось где-то не там».
            QMessageBox.warning(
                self, "OneCStarter", f"Не удалось открыть каталог: {directory}"  # noqa: RUF001
            )
