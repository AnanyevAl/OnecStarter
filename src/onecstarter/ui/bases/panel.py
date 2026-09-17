"""Панель свойств под деревом — вариант B мокапа.

Заголовок (значок вида + имя + вид словом), путь — `PathLink` (ссылка на
каталог у файловой базы, текст с одним «Копировать» у серверной/веб).
Расчёт содержимого — services/connection.panel_card, здесь только показ.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from onecstarter.services.connection import PanelCard, panel_card
from onecstarter.ui.bases.icons import placement_icon
from onecstarter.ui.path_link import PathLink, copy_to_clipboard
from onecstarter.ui.theme import DARK, Palette


def open_in_explorer(path: str) -> bool:
    """Открыть каталог проводником. `False` — каталога нет или отказ системы."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


_EMPTY_CARD = panel_card(None, None, "")


class ConnectionPanel(QWidget):
    def __init__(
        self,
        *,
        open_directory: Callable[[str], bool] = open_in_explorer,
        copy_text: Callable[[str], None] = copy_to_clipboard,
        palette: Palette = DARK,
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

        self._link = PathLink(palette=palette, copy_text=copy_text)
        self._link.open_requested.connect(self._do_open)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        layout.addLayout(title_row)
        layout.addWidget(self._link)
        self.show_card(_EMPTY_CARD, None)

    def show_card(self, card: PanelCard, palette: Palette | None) -> None:
        """Показать карточку. Палитра нужна значку и цветам ссылки; None — оба
        не применяются (только стартовое пустое состояние в __init__).
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
        if palette is not None:
            self._link.apply_palette(palette)
        note = card.path.note if card.path else None
        self._link.set_placeholder(card.hint or note or "")
        self._link.set_path(
            card.path.text if card.path else "",
            directory=card.path.directory if card.path else None,
        )

    def text(self) -> str:
        return self._link.path_text()

    def placeholder(self) -> str:
        return self._link.placeholder()

    def title_text(self) -> str:
        parts = [self._title.text()] if self._title.text() else []
        if self._kind_word.text():
            parts.append(self._kind_word.text().removeprefix("· "))
        return " · ".join(parts)

    def link(self) -> PathLink:
        return self._link

    def _do_open(self, directory: str) -> None:
        if not self._open_directory(directory):
            # Молчание здесь читалось бы как «открылось где-то не там».
            QMessageBox.warning(
                self, "OneCStarter", f"Не удалось открыть каталог: {directory}"  # noqa: RUF001
            )
