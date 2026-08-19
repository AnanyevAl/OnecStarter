"""Главное окно: узкая навигация разделов + текущий раздел.

В v1 разделов два («Базы», «Настройки») — каркас держит произвольный список
разделов как независимых виджетов (спека 4a, §1; спека 4b, §2.5).
"""  # noqa: RUF002

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.ui import theme
from onecstarter.ui.theme import Palette


class MainWindow(QMainWindow):
    """Главное окно: узкая навигация разделов + текущий раздел.

    Разделы приходят списком пар «подпись, виджет»; разделы стоят подряд
    сверху; §3 спеки рестайла 15.08.2026 отменяет §2.5 спеки 4b.
    """

    def __init__(
        self,
        sections: Sequence[tuple[str, QWidget]],
        parent: QWidget | None = None,
        palette: Palette = theme.DARK,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OneCStarter")
        self.resize(900, 600)
        self.close_to_tray = False
        # Проставляются сборкой приложения (ui/app.py): окну они нужны
        # только как владельцу времени жизни, поведение их не читает.
        self.settings_store: object | None = None
        self.global_hotkey: object | None = None
        self._palette = palette
        self._icon_factories: dict[int, Callable[[Palette], QIcon]] = {}
        self._stack = QStackedWidget()
        self._buttons: list[QToolButton] = []
        group = QButtonGroup(self)
        group.setExclusive(True)

        rail = QFrame()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(76)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 8, 0, 8)
        for index, (label, widget) in enumerate(sections):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # QToolButton по умолчанию Fixed по горизонтали — кнопка сжимается
            # до естественной ширины подписи и прижимается к левому краю
            # рельсы ([Ф] живой запуск 15.08.2026: «Базы» — 40 px). Пункт
            # рельсы — на всю её ширину, контент центрируется кнопкой.
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            button.clicked.connect(lambda _checked=False, i=index: self.show_section(i))
            group.addButton(button)
            rail_layout.addWidget(button)
            self._buttons.append(button)
            self._stack.addWidget(widget)
        rail_layout.addStretch(1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(rail)
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

    def section_buttons(self) -> list[QToolButton]:
        return list(self._buttons)

    def current_section(self) -> QWidget:
        return self._stack.currentWidget()

    def show_section(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._buttons[index].setChecked(True)

    def set_section_icon(
        self, index: int, factory: Callable[[Palette], QIcon]
    ) -> None:
        """Назначить разделу значок-фабрику; значок строится из палитры.

        Фабрика, а не готовый QIcon: цвета значка запечены в пиксмапы,
        и смена темы обязана перерисовать их заново (apply_palette) —
        тот же принцип, что у значков размещения в build_model.
        """  # noqa: RUF002
        self._icon_factories[index] = factory
        self._buttons[index].setIcon(factory(self._palette))

    def apply_palette(self, palette: Palette) -> None:
        """Перерисовать значки разделов из новой палитры."""
        self._palette = palette
        for index, factory in self._icon_factories.items():
            self._buttons[index].setIcon(factory(palette))

    def show_and_focus_search(self) -> None:
        """Поднять окно и поставить фокус в поиск раздела (хоткей, трей).

        showNormal() сбрасывает развёрнутое (maximized) состояние окна —
        вызывать его нужно только чтобы вывести окно из свёрнутого
        (minimized) или скрытого (hide()) состояния. Если окно уже видимо
        развёрнутым, обычный show() поднимает его, не трогая geometry.
        """  # noqa: RUF002
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        focus = getattr(self._stack.currentWidget(), "focus_search", None)
        if callable(focus):
            focus()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # Закрытие при живом трее — сворачивание: приложение продолжает
        # работать в фоне ради глобального хоткея ([Р] спека 4a, §3).  # noqa: RUF003
        if self.close_to_tray:
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)
