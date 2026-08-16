"""Раздел «Настройки»: вид мокапа в объёме v1 — тема и честный отказ записи.

Наполнение тонкое намеренно: настройки трея, автозапуска, хоткея
и «Недавних» — следующий этап (спека рестайла §6 и §8). Сегментный
переключатель — три checkable QPushButton в QButtonGroup; собственных
запечённых цветов нет, красит общий stylesheet (#ThemeSeg, #SettingsGroupLabel).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services.settings import ThemeMode
from onecstarter.ui.theme_controller import ThemeController

CHOICES = (
    (ThemeMode.AUTO, "Авто"),
    (ThemeMode.LIGHT, "Светлая"),
    (ThemeMode.DARK, "Тёмная"),
)


class SettingsView(QWidget):
    def __init__(self, controller: ThemeController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._buttons: list[QPushButton] = []

        header = QLabel("Настройки")
        header_font = header.font()
        header_font.setPointSize(13)
        header_font.setBold(True)
        header.setFont(header_font)
        self._path_label = QLabel(f"{controller.path} · применяются сразу")
        self._path_label.setObjectName("SettingsSub")

        group_label = QLabel("ВНЕШНИЙ ВИД")
        group_label.setObjectName("SettingsGroupLabel")

        row_title = QLabel("Тема")
        row_note = QLabel("«Авто» следует теме Windows и переключается вместе с ней")  # noqa: RUF001
        row_note.setObjectName("SettingsNote")
        row_note.setWordWrap(True)

        seg = QWidget()
        seg.setObjectName("ThemeSeg")
        seg_layout = QHBoxLayout(seg)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        buttons = QButtonGroup(self)
        buttons.setExclusive(True)
        for mode, label in CHOICES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(mode is controller.mode)
            button.clicked.connect(lambda _checked=False, m=mode: self._choose(m))
            buttons.addButton(button)
            seg_layout.addWidget(button)
            self._buttons.append(button)

        row = QHBoxLayout()
        body = QVBoxLayout()
        body.setSpacing(1)
        body.addWidget(row_title)
        body.addWidget(row_note)
        row.addLayout(body, stretch=1)
        row.addWidget(seg, alignment=Qt.AlignmentFlag.AlignTop)

        self._status = QLabel("")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(header)
        layout.addWidget(self._path_label)
        layout.addSpacing(10)
        layout.addWidget(group_label)
        layout.addLayout(row)
        layout.addWidget(self._status)
        layout.addStretch(1)

        controller.changed.connect(self._sync)

    def theme_buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def status_text(self) -> str:
        return self._status.text()

    def path_text(self) -> str:
        return self._path_label.text()

    def _choose(self, mode: ThemeMode) -> None:
        self._controller.set_mode(mode)

    def _sync(self) -> None:
        for button, (mode, _label) in zip(self._buttons, CHOICES, strict=True):
            button.setChecked(mode is self._controller.mode)
        self._status.setText(self._controller.last_save_error or "")
