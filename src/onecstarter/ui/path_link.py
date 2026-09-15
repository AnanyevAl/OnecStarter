"""Путь-ссылка панелей (спека v3.1, §2).

`QLabel` с rich-text: текст пути — ссылка цветом акцента (клик и Enter —
`open_requested`), без каталога — обычный текст; ПКМ — меню «Открыть каталог» /
«Копировать». Длинный путь обрезается многоточием посередине по ширине виджета,
полный текст — во всплывающей подсказке; «Копировать» кладёт полный текст.
Замена read-only `QLineEdit` + двух кнопок (замечание 1 заказчика по v3).
"""  # noqa: RUF002

import html
from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QResizeEvent
from PySide6.QtWidgets import QLabel, QMenu, QSizePolicy, QWidget

from onecstarter.ui.theme import Palette

MENU_OPEN = "Открыть каталог"
MENU_COPY = "Копировать"
_MIN_TEXT_WIDTH = 40


def copy_to_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


class PathLink(QLabel):
    open_requested = Signal(str)

    def __init__(
        self,
        *,
        palette: Palette,
        copy_text: Callable[[str], None] = copy_to_clipboard,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._copy_text = copy_text
        self._text = ""
        self._shown = ""
        self._directory: str | None = None
        self._placeholder = ""
        self.setObjectName("PathLink")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        # Ширину диктует раскладка, а не длина пути: иначе длинный путь  # noqa: RUF003
        # растягивал бы панель и окно вместо того, чтобы обрезаться.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        # Открываем свой `_directory`, а не href из разметки: href прошёл  # noqa: RUF003
        # через html.escape и обратно, каталог — первоисточник.
        self.linkActivated.connect(lambda _href: self._request_open())
        self._render()

    # --- состояние -------------------------------------------------------

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self._render()

    def set_path(self, text: str, *, directory: str | None = None) -> None:
        self._text = text
        self._directory = directory if text else None
        self._render()

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._render()

    # --- доступ ----------------------------------------------------------

    def path_text(self) -> str:
        return self._text

    def elided_text(self) -> str:
        return self._shown

    def placeholder(self) -> str:
        return self._placeholder

    def link_href(self) -> str | None:
        return self._directory if self._text else None

    def context_menu(self) -> QMenu:
        menu = QMenu(self)
        if self._directory is not None:
            menu.addAction(MENU_OPEN, self._request_open)
        if self._text:
            menu.addAction(MENU_COPY, lambda: self._copy_text(self._text))
        return menu

    # --- внутреннее ------------------------------------------------------

    def _request_open(self) -> None:
        if self._directory is not None:
            self.open_requested.emit(self._directory)

    def _show_menu(self, pos: QPoint) -> None:
        menu = self.context_menu()
        if not menu.actions():
            menu.deleteLater()
            return
        # popup() вместо exec(): не блокирует, а WA_DeleteOnClose  # noqa: RUF003
        # освобождает меню при закрытии — иначе QMenu(self) копился
        # бы на каждый ПКМ (ревью Task 1). Проверяется тестом с  # noqa: RUF003
        # close() и DeferredDelete.
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        menu.popup(self.mapToGlobal(pos))

    def _render(self) -> None:
        if not self._text:
            self._shown = ""
            self.setToolTip("")
            self.setText(
                f'<i style="color:{self._palette.text_dim}">{html.escape(self._placeholder)}</i>'
            )
            return
        width = max(self.width() - 4, _MIN_TEXT_WIDTH)
        self._shown = self.fontMetrics().elidedText(
            self._text, Qt.TextElideMode.ElideMiddle, width
        )
        self.setToolTip(self._text)
        shown = html.escape(self._shown)
        if self._directory is not None:
            href = html.escape(self._directory, quote=True)
            self.setText(f'<a href="{href}" style="color:{self._palette.accent}">{shown}</a>')
        else:
            self.setText(f'<span style="color:{self._palette.text}">{shown}</span>')

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render()
