"""Раздел «Настройки»: четыре группы утверждённого мокапа.

Порядок групп — мокапа: ВНЕШНИЙ ВИД, ОКНО И ЗАПУСК, ГОРЯЧИЕ КЛАВИШИ,
СПИСОК БАЗ. Собственных запечённых цветов нет, красит общий stylesheet
(#ThemeSeg, #SettingsGroupLabel, #SettingsNote).

Раздел не знает ни о `GlobalHotkey`, ни о том, как поднято окно: сочетание
уходит наружу через `on_hotkey`, а обратно приходит текст отказа либо `None`.
Занятость сочетания — свойство системы, и решать о ней разделу нечем.

Автозапуск идёт мимо store: его истина — реестр (спека §3.1). Реестр
подаётся инъекцией — тесты не трогают живой HKCU.
"""  # noqa: RUF002

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services import autostart
from onecstarter.services.settings import RECENT_MAX, RECENT_MIN, ThemeMode
from onecstarter.ui.hotkey_edit import HotkeyEdit
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.theme_controller import ThemeController

CHOICES = (
    (ThemeMode.AUTO, "Авто"),
    (ThemeMode.LIGHT, "Светлая"),
    (ThemeMode.DARK, "Тёмная"),
)

NOT_FROZEN_NOTE = "Доступно в установленной версии — из исходников ссылка в реестре протухнет"

# Windows держит автозапуск в двух местах: значение в `Run` (его пишем мы,  # noqa: RUF003
# спека §3.1) и метку `StartupApproved`, которую ставит «Диспетчер задач».
# Отключив автозапуск там, пользователь получает мёртвую запись при нашем
# «включено», и тумблер тут бессилен: он перезаписывает `Run`, а метку  # noqa: RUF003
# не трогает — **[проверено, 21.08.2026, шаг В7 ручного прогона]**.  # noqa: RUF003
# Читать `StartupApproved` мы не беремся: формат не документирован, а на живой  # noqa: RUF003
# машине кодировка оказалась ещё и неоднородной (`0x01` у нашей записи против  # noqa: RUF003
# `0x03` у соседних отключённых). Раз состояние не в наших силах — честный  # noqa: RUF003
# минимум сказать, где его менять. Решение заказчика 21.08.2026.  # noqa: RUF003
AUTOSTART_ROW_NOTE = (
    "Программа стартует в трей: вызов и запуск избранного доступны сразу. "
    "Отключённый в «Диспетчере задач» автозапуск включается только там же"
)


class SettingsView(QWidget):
    def __init__(
        self,
        controller: ThemeController,
        store: SettingsStore,
        *,
        autostart_registry: autostart.Registry | None = None,
        frozen: bool = False,
        executable: str = "",
        on_hotkey: Callable[[str], str | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._store = store
        self._registry = autostart_registry
        self._frozen = frozen
        self._executable = executable
        self._on_hotkey = on_hotkey
        self._buttons: list[QPushButton] = []
        self._group_labels: list[str] = []
        self._row_notes: dict[str, QLabel] = {}
        self._row_controls: dict[str, QWidget] = {}

        header = QLabel("Настройки")
        header_font = header.font()
        header_font.setPointSize(13)
        header_font.setBold(True)
        header.setFont(header_font)
        self._path_label = QLabel(f"{store.path} · применяются сразу")
        self._path_label.setObjectName("SettingsSub")

        self._status = QLabel("")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(header)
        layout.addWidget(self._path_label)
        layout.addSpacing(10)
        self._layout = layout

        self._add_group("ВНЕШНИЙ ВИД")
        self._add_row(
            "Тема",
            "«Авто» следует теме Windows и переключается вместе с ней",  # noqa: RUF001
            self._build_theme_segment(),
        )

        self._add_group("ОКНО И ЗАПУСК")  # noqa: RUF001
        self._tray = QCheckBox()
        self._tray.setChecked(store.settings.close_to_tray)
        self._tray.toggled.connect(self._choose_tray)
        self._add_row(
            "Закрытие окна сворачивает в трей",
            "Выключено — крестик завершает программу, глобальный вызов перестаёт работать",
            self._tray,
        )

        self._autostart = QCheckBox()
        self._autostart_note = QLabel("")
        self._autostart_note.setObjectName("SettingsNote")
        self._autostart_note.setWordWrap(True)
        self._add_row(
            "Запускать при входе в Windows",
            AUTOSTART_ROW_NOTE,
            self._autostart,
            extra=self._autostart_note,
        )
        self._sync_autostart()
        self._autostart.toggled.connect(self._choose_autostart)

        self._add_group("ГОРЯЧИЕ КЛАВИШИ")
        self._hotkey = HotkeyEdit()
        self._hotkey.set_combination(store.settings.hotkey)
        self._hotkey.captured.connect(self._choose_hotkey)
        self._hotkey_note = QLabel("")
        self._hotkey_note.setObjectName("SettingsNote")
        self._hotkey_note.setWordWrap(True)
        self._add_row(
            "Глобальный вызов окна",
            "Только с модификатором. Занятое сочетание — сообщение, а не тишина",  # noqa: RUF001
            self._hotkey,
            extra=self._hotkey_note,
        )

        self._add_group("СПИСОК БАЗ")
        self._recent = QSpinBox()
        self._recent.setRange(RECENT_MIN, RECENT_MAX)
        self._recent.setValue(store.settings.recent_limit)
        self._recent.valueChanged.connect(self._choose_recent)
        self._add_row(
            "Записей в «Недавних»",
            "0 — ветка «Недавние» не показывается вовсе",
            self._recent,
        )

        layout.addWidget(self._status)
        layout.addStretch(1)

        controller.changed.connect(self._sync)
        store.changed.connect(self._sync)

    # --- сборка раскладки ------------------------------------------------

    def _add_group(self, title: str) -> None:
        label = QLabel(title)
        label.setObjectName("SettingsGroupLabel")
        self._layout.addWidget(label)
        self._group_labels.append(title)

    def _add_row(
        self, title: str, note: str, control: QWidget, *, extra: QWidget | None = None
    ) -> None:
        row_title = QLabel(title)
        row_note = QLabel(note)
        row_note.setObjectName("SettingsNote")
        row_note.setWordWrap(True)
        self._row_notes[title] = row_note
        self._row_controls[title] = control

        body = QVBoxLayout()
        body.setSpacing(1)
        body.addWidget(row_title)
        body.addWidget(row_note)
        if extra is not None:
            body.addWidget(extra)

        row = QHBoxLayout()
        row.addLayout(body, stretch=1)
        row.addWidget(control, alignment=Qt.AlignmentFlag.AlignTop)
        self._layout.addLayout(row)

    def _build_theme_segment(self) -> QWidget:
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
            button.setChecked(mode is self._controller.mode)
            button.clicked.connect(lambda _checked=False, m=mode: self._choose_theme(m))
            buttons.addButton(button)
            seg_layout.addWidget(button)
            self._buttons.append(button)
        return seg

    # --- доступ для тестов ------------------------------------------------

    def group_labels(self) -> list[str]:
        return list(self._group_labels)

    def theme_buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def tray_checkbox(self) -> QCheckBox:
        return self._tray

    def autostart_checkbox(self) -> QCheckBox:
        return self._autostart

    def hotkey_edit(self) -> HotkeyEdit:
        return self._hotkey

    def recent_spinbox(self) -> QSpinBox:
        return self._recent

    def status_text(self) -> str:
        return self._status.text()

    def path_text(self) -> str:
        return self._path_label.text()

    def autostart_note(self) -> str:
        return self._autostart_note.text()

    def row_note(self, title: str) -> QLabel:
        """Подпись строки по её заголовку — тестам, проверяющим место подсказки.

        Аксессор, а не обход раскладки в тесте: обход зашил бы внутреннее
        устройство `_add_row` и сломался бы от любой законной перекомпоновки.
        Нужен, потому что проверки «текст есть на экране» мало: подсказку можно
        повесить под соседнюю настройку, и она начнёт врать увереннее, чем
        её отсутствие (находка мутационной проверки 21.08.2026).
        """  # noqa: RUF002
        return self._row_notes[title]

    def row_control(self, title: str) -> QWidget:
        """Орган управления строки по её заголовку.

        Парный к `row_note`: заголовок и подпись можно оставить на местах,
        а под ними поставить чужой переключатель — верная подсказка над чужим
        тумблером врёт ровно так же, как подсказка не на той строке (находка
        мутационной проверки 21.08.2026, мутация «строка автозапуска несёт
        чекбокс трея»). Аксессоры вьюхи возвращают виджеты по ссылке, поэтому
        без этой связи ни один тест раскладку не проверяет.
        """  # noqa: RUF002
        return self._row_controls[title]

    def hotkey_note(self) -> str:
        return self._hotkey_note.text()

    # --- проводка приложения ------------------------------------------------

    def set_hotkey_handler(self, handler: Callable[[str], str | None]) -> None:
        """Кто перевешивает хоткей. Ставится сборкой приложения после создания."""
        self._on_hotkey = handler

    def report_hotkey_problem(self, problem: str) -> None:
        """Показать отказ, случившийся не по нажатию в разделе (занято на старте)."""
        self._hotkey_note.setText(problem)

    # --- реакции ----------------------------------------------------------

    def _choose_theme(self, mode: ThemeMode) -> None:
        self._controller.set_mode(mode)

    def _choose_tray(self, checked: bool) -> None:
        self._store.update(close_to_tray=checked)

    def _choose_recent(self, value: int) -> None:
        self._store.update(recent_limit=value)

    def _choose_hotkey(self, text: str) -> None:
        """Сохранить выбранное и показать, что ответила система.

        Занятое сочетание сохраняется (спека §4.2): оно освободится, когда
        закроется конфликтующая программа, и заставлять пользователя
        подбирать свободное прямо сейчас незачем. Врать «работает» при этом
        нельзя — отказ виден строкой рядом с полем.
        """  # noqa: RUF002
        self._store.update(hotkey=text)
        problem = self._on_hotkey(text) if self._on_hotkey is not None else None
        self._hotkey_note.setText(problem or "")

    def _choose_autostart(self, checked: bool) -> None:
        if self._registry is None:
            return
        try:
            if checked:
                autostart.enable(self._registry, self._executable)
            else:
                autostart.disable(self._registry)
        except OSError as error:
            # Заметку передаём явно параметром, а не через уже установленный  # noqa: RUF003
            # текст виджета (находка финального ревью ветки, п. 5): прежняя
            # редакция звала `_sync_autostart()` без аргумента, а тот читал  # noqa: RUF003
            # `self._autostart_note.text()` — свой же вывод, установленный
            # строкой выше. Работало только из-за узкого графа вызовов —
            # третий вызывающий, не выставивший текст заранее, получил бы
            # протухшую или пустую заметку.
            self._sync_autostart(note=f"Не удалось изменить автозапуск: {error}")  # noqa: RUF001
            return
        self._autostart_note.setText("")

    def _sync_autostart(self, *, note: str = "") -> None:
        """Привести тумблер к факту: сборка, реестр, доступность чтения.

        `note` — что показать у строки при успешном чтении реестра; источник
        явный (аргумент), а не неявный (текст, уже лежащий в виджете) —
        находка финального ревью ветки, п. 5, см. докстринг `_choose_autostart`.
        """  # noqa: RUF002
        if not self._frozen or self._registry is None:
            self._set_autostart_state(checked=False, enabled=False, note=NOT_FROZEN_NOTE)
            return
        try:
            enabled = autostart.is_enabled(self._registry)
        except OSError as error:
            # Состояние неизвестно: показать «выключено» как факт нельзя
            # (спека §3.6) — тумблер запирается, причина остаётся на экране.
            self._set_autostart_state(
                checked=False,
                enabled=False,
                note=f"Не удалось прочитать автозапуск: {error}",  # noqa: RUF001
            )
            return
        self._set_autostart_state(checked=enabled, enabled=True, note=note)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Тумблер автозапуска — фактическое состояние реестра на момент показа (спека §3.1).

        Пользователь мог снять автозапуск штатным путём (Диспетчер задач →
        Автозагрузка), пока раздел был скрыт; без пересинхронизации при
        каждом показе тумблер держал бы состояние, снятое один раз при
        конструировании (находка финального ревью ветки, п. 5).
        """
        super().showEvent(event)
        self._sync_autostart()

    def _set_autostart_state(self, *, checked: bool, enabled: bool, note: str) -> None:
        # Сигнал глушится: приведение тумблера к факту — не выбор
        # пользователя, и отвечать на него записью в реестр нельзя.
        blocked = self._autostart.blockSignals(True)
        self._autostart.setChecked(checked)
        self._autostart.blockSignals(blocked)
        self._autostart.setEnabled(enabled)
        self._autostart_note.setText(note)

    def _sync(self) -> None:
        """Привести органы к текущим настройкам (смена темы из трея и т. п.).

        Сигналы органов глушатся: приведение к состоянию — не выбор
        пользователя, и отвечать на него новой записью в файл значило бы
        зациклить `changed` → `update` → `changed`.
        """
        for button, (mode, _label) in zip(self._buttons, CHOICES, strict=True):
            button.setChecked(mode is self._controller.mode)
        settings = self._store.settings

        blocked = self._tray.blockSignals(True)
        self._tray.setChecked(settings.close_to_tray)
        self._tray.blockSignals(blocked)

        blocked = self._recent.blockSignals(True)
        self._recent.setValue(settings.recent_limit)
        self._recent.blockSignals(blocked)

        self._hotkey.set_combination(settings.hotkey)
        self._status.setText(self._store.last_save_error or "")
