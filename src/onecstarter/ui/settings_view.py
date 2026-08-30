"""Раздел «Настройки»: четыре группы утверждённого мокапа v1 плюс СЕРВЕРЫ (v2).

Порядок групп v1-мокапа: ВНЕШНИЙ ВИД, ОКНО И ЗАПУСК, ГОРЯЧИЕ КЛАВИШИ,
СПИСОК БАЗ. Собственных запечённых цветов нет, красит общий stylesheet
(#ThemeSeg, #SettingsGroupLabel, #SettingsNote). Шестая настройка группы
«ОКНО И ЗАПУСК» — «Клиент по умолчанию» (спека вехи «Завершение v1», §2):
сегмент того же вида, что тема, только выбор идёт в `store`, а не в
`ThemeController`.

Группа СЕРВЕРЫ (спека §3.5, T-08 задача 7) — за пределами утверждённого мокапа
v1, вставлена сразу ПОСЛЕ «ОКНО И ЗАПУСК» и перед «ГОРЯЧИЕ КЛАВИШИ»: спека §3.5
требует соседства с существующими настройками запуска, круг исправлений 1
ревью задачи 7 (место «последней группой» было ошибкой брифа-умолчания,
спека главнее). Несёт «Корень каталогов серверов», от которого новый профиль
сервера предлагает `<корень>\\srv_<версия>`. Поле пути + кнопка «Обзор…» —
тем же приёмом инъекции диалога (`choose_directory`), что и `InfobaseDialog`
в `dialogs/infobase.py`.

Раздел не знает ни о `GlobalHotkey`, ни о том, как поднято окно: сочетание
уходит наружу через `on_hotkey`, а обратно приходит текст отказа либо `None`.
Занятость сочетания — свойство системы, и решать о ней разделу нечем.

Автозапуск идёт мимо store: его истина — реестр (спека §3.1). Реестр
подаётся инъекцией — тесты не трогают живой HKCU.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services import autostart
from onecstarter.services.settings import (
    RECENT_MAX,
    RECENT_MIN,
    DefaultClient,
    ListOrder,
    ThemeMode,
)
from onecstarter.ui.hotkey_edit import HotkeyEdit
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.shortcuts import BASES_SHORTCUTS
from onecstarter.ui.theme_controller import ThemeController

CHOICES = (
    (ThemeMode.AUTO, "Авто"),
    (ThemeMode.LIGHT, "Светлая"),
    (ThemeMode.DARK, "Тёмная"),
)

CLIENT_CHOICES = (
    (DefaultClient.THIN, "Тонкий"),
    (DefaultClient.THICK, "Толстый"),
)

ORDER_CHOICES = (
    (ListOrder.FILE, "Как в файле"),
    (ListOrder.ALPHABETICAL, "По алфавиту"),
)

NOT_FROZEN_NOTE = "Доступно в установленной версии — из исходников ссылка в реестре протухнет"

# Windows держит автозапуск в двух местах: значение в `Run` (его пишем мы,  # noqa: RUF003
# спека §3.1) и метку `StartupApproved`, которую ставит «Диспетчер задач».
# Отключив автозапуск там, пользователь получает мёртвую запись при нашем
# «включено», и тумблер тут бессилен: он перезаписывает `Run`, а метку  # noqa: RUF003
# не трогает — **[проверено, 22.08.2026, шаг В7 ручного прогона]**.  # noqa: RUF003
# Читать `StartupApproved` мы не беремся: формат не документирован, а на живой  # noqa: RUF003
# машине кодировка оказалась ещё и неоднородной (`0x01` у нашей записи против  # noqa: RUF003
# `0x03` у соседних отключённых). Раз состояние не в наших силах — честный  # noqa: RUF003
# минимум сказать, где его менять. Решение заказчика 22.08.2026.  # noqa: RUF003
AUTOSTART_ROW_NOTE = (
    "Программа стартует в трей: вызов и запуск избранного доступны сразу. "
    "Отключённый в «Диспетчере задач» автозапуск включается только там же"
)

SERVERS_ROOT_ROW_NOTE = "Новые профили серверов предлагают каталог <корень>\\srv_<версия>"


def browse_for_servers_root() -> str:
    """Системный диалог выбора корня каталогов серверов. Пустая строка — отмена.

    Инъекция, а не вызов модульного имени напрямую — тот же приём, что
    у `browse_for_directory` в `dialogs/infobase.py`: настоящий `QFileDialog`
    в офскрин-тесте не дождётся выбора каталога.
    """  # noqa: RUF002
    return QFileDialog.getExistingDirectory()


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
        choose_directory: Callable[[], str] = browse_for_servers_root,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._store = store
        self._registry = autostart_registry
        self._frozen = frozen
        self._executable = executable
        self._on_hotkey = on_hotkey
        self._choose_directory = choose_directory
        self._buttons: list[QPushButton] = []
        self._client_buttons: list[QPushButton] = []
        self._order_buttons: list[QPushButton] = []
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

        # T-11, п. 9 (решение заказчика 29.08.2026): любой способ запуска базы
        # прячет окно; на серверные профили не действует; без трея — не действует.
        self._hide_on_launch = QCheckBox()
        self._hide_on_launch.setChecked(store.settings.hide_on_launch)
        self._hide_on_launch.toggled.connect(self._choose_hide_on_launch)
        self._add_row(
            "Запуск базы сворачивает окно в трей",
            "Любой способ запуска: Enter, F3/F4, меню, поиск, трей. Без трея не действует",
            self._hide_on_launch,
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

        self._add_row(
            "Клиент по умолчанию",
            "Чем запускать базу, где клиент не указан. Выбор в записи (App) "
            "и Ctrl+1/Ctrl+2 главнее",
            self._build_client_segment(),
        )

        self._add_group("СЕРВЕРЫ")
        self._add_row(
            "Корень каталогов серверов",
            SERVERS_ROOT_ROW_NOTE,
            self._build_servers_root_control(store.settings.servers_root),
        )

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

        self._shortcut_rows: list[tuple[str, str]] = []
        self._add_block(
            "Сочетания раздела «Базы»",
            "Зашиты в программу и не меняются (решение заказчика 29.08.2026)",
            self._build_shortcut_reference(),
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
        self._add_row(
            "Порядок списка",
            "«По алфавиту» — только показ: файл списка и штатный стартер порядка "
            "не видят, перестановка Alt+↑/↓ и мышью отключена",
            self._build_order_segment(),
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

    def _add_block(self, title: str, note: str, body: QWidget) -> None:
        """Строка настроек во всю ширину: заголовок, подпись, тело под ними.

        Для справочной таблицы `_add_row` не годится: та ставит орган
        управления справа узкой колонкой, а таблице нужна ширина раздела.
        Регистрируется в `_row_notes`/`_row_controls` так же, как строки
        `_add_row`, — тесты находят её теми же аксессорами.
        """  # noqa: RUF002
        row_title = QLabel(title)
        row_note = QLabel(note)
        row_note.setObjectName("SettingsNote")
        row_note.setWordWrap(True)
        self._row_notes[title] = row_note
        self._row_controls[title] = body
        self._layout.addWidget(row_title)
        self._layout.addWidget(row_note)
        self._layout.addWidget(body)

    def _build_shortcut_reference(self) -> QWidget:
        """Таблица «сочетание — действие» по `BASES_SHORTCUTS` (T-11, п. 3, только чтение)."""
        table = QWidget()
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(2)
        for row, spec in enumerate(BASES_SHORTCUTS):
            keys = QLabel(spec.label)
            keys_font = keys.font()
            keys_font.setBold(True)
            keys.setFont(keys_font)
            grid.addWidget(keys, row, 0)
            grid.addWidget(QLabel(spec.title), row, 1)
            self._shortcut_rows.append((spec.label, spec.title))
        grid.setColumnStretch(1, 1)
        return table

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

    def _build_segment(
        self,
        choices: Sequence[tuple[Any, str]],
        is_current: Callable[[Any], bool],
        choose: Callable[[Any], None],
        registry: list[QPushButton],
    ) -> QWidget:
        """Сегментный переключатель — один билдер на клиента и порядок списка (T-11)."""
        seg = QWidget()
        seg.setObjectName("ThemeSeg")
        seg_layout = QHBoxLayout(seg)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        buttons = QButtonGroup(self)
        buttons.setExclusive(True)
        for value, label in choices:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(is_current(value))
            button.clicked.connect(lambda _checked=False, v=value: choose(v))
            buttons.addButton(button)
            seg_layout.addWidget(button)
            registry.append(button)
        return seg

    def _build_client_segment(self) -> QWidget:
        return self._build_segment(
            CLIENT_CHOICES,
            lambda client: client is self._store.settings.default_client,
            self._choose_client,
            self._client_buttons,
        )

    def _build_order_segment(self) -> QWidget:
        return self._build_segment(
            ORDER_CHOICES,
            lambda order: order is self._store.settings.list_order,
            self._choose_order,
            self._order_buttons,
        )

    def _build_servers_root_control(self, current: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self._servers_root = QLineEdit(current)
        self._servers_root.editingFinished.connect(self._choose_servers_root)
        self._servers_root_browse = QPushButton("Обзор…")
        self._servers_root_browse.clicked.connect(self._browse_servers_root)
        row_layout.addWidget(self._servers_root)
        row_layout.addWidget(self._servers_root_browse)
        return row

    # --- доступ для тестов ------------------------------------------------

    def group_labels(self) -> list[str]:
        return list(self._group_labels)

    def theme_buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def client_buttons(self) -> list[QPushButton]:
        return list(self._client_buttons)

    def order_buttons(self) -> list[QPushButton]:
        return list(self._order_buttons)

    def tray_checkbox(self) -> QCheckBox:
        return self._tray

    def hide_on_launch_checkbox(self) -> QCheckBox:
        return self._hide_on_launch

    def autostart_checkbox(self) -> QCheckBox:
        return self._autostart

    def hotkey_edit(self) -> HotkeyEdit:
        return self._hotkey

    def recent_spinbox(self) -> QSpinBox:
        return self._recent

    def shortcut_reference_rows(self) -> list[tuple[str, str]]:
        """Строки справочника сочетаний в порядке показа — что реально попало в таблицу."""
        return list(self._shortcut_rows)

    def servers_root_edit(self) -> QLineEdit:
        return self._servers_root

    def servers_root_browse_button(self) -> QPushButton:
        return self._servers_root_browse

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
        её отсутствие (находка мутационной проверки 22.08.2026).

        Что метод отдаёт: подпись, ЗАРЕГИСТРИРОВАННУЮ строкой при сборке, —
        не результат обхода layout. Связь с раскладкой сторожит отдельно
        `isHidden()` в тесте: виджет, не попавший в раскладку, скрыт. Уточнено
        по находке финального ревью ветки — прежний докстринг обещал проверку
        раскладки, которой аксессор сам по себе не делает.
        """  # noqa: RUF002
        return self._row_notes[title]

    def row_control(self, title: str) -> QWidget:
        """Орган управления строки по её заголовку.

        Парный к `row_note`: заголовок и подпись можно оставить на местах,
        а под ними поставить чужой переключатель — верная подсказка над чужим
        тумблером врёт ровно так же, как подсказка не на той строке (находка
        мутационной проверки 22.08.2026, мутация «строка автозапуска несёт
        чекбокс трея»). Прочие аксессоры вьюхи отдают виджеты по ссылке и
        потому к строке их не привязывают вовсе.

        Как и `row_note`, отдаёт зарегистрированное при сборке, а не найденное
        в layout.
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

    def _choose_client(self, client: DefaultClient) -> None:
        self._store.update(default_client=client)

    def _choose_order(self, order: ListOrder) -> None:
        self._store.update(list_order=order)

    def _choose_tray(self, checked: bool) -> None:
        self._store.update(close_to_tray=checked)

    def _choose_hide_on_launch(self, checked: bool) -> None:
        self._store.update(hide_on_launch=checked)

    def _choose_recent(self, value: int) -> None:
        self._store.update(recent_limit=value)

    def _choose_servers_root(self) -> None:
        self._store.update(servers_root=self._servers_root.text())

    def _browse_servers_root(self) -> None:
        """Обработчик «Обзор…»: заполнить поле и сохранить сразу.

        Пустая строка от `self._choose_directory()` — пользователь отменил
        выбор (контракт `QFileDialog.getExistingDirectory`, см.
        `browse_for_servers_root`, тот же приём — `dialogs.infobase.
        browse_for_directory`): поле не трогается, store не пишется.
        Сохранение — явным вызовом `store.update`, а не через `editingFinished`:
        `setText` его не эмитит (сигнал только по Enter/потере фокуса),
        а поведение поля обязано быть тем же, что и у ручного ввода —
        применяется сразу.
        """  # noqa: RUF002
        path = self._choose_directory()
        if not path:
            return
        self._servers_root.setText(path)
        self._store.update(servers_root=path)

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

        for button, (client, _label) in zip(
            self._client_buttons, CLIENT_CHOICES, strict=True
        ):
            button.setChecked(client is settings.default_client)

        for button, (order, _label) in zip(self._order_buttons, ORDER_CHOICES, strict=True):
            button.setChecked(order is settings.list_order)

        blocked = self._tray.blockSignals(True)
        self._tray.setChecked(settings.close_to_tray)
        self._tray.blockSignals(blocked)

        blocked = self._hide_on_launch.blockSignals(True)
        self._hide_on_launch.setChecked(settings.hide_on_launch)
        self._hide_on_launch.blockSignals(blocked)

        blocked = self._recent.blockSignals(True)
        self._recent.setValue(settings.recent_limit)
        self._recent.blockSignals(blocked)

        self._hotkey.set_combination(settings.hotkey)

        # `blockSignals`, как у `_tray`/`_recent`: `QLineEdit.setText` не эмитит  # noqa: RUF003
        # `editingFinished` (тот срабатывает только по Enter/потере фокуса),
        # так что здесь это защитный дубль на случай, если поле обрастёт ещё
        # одним сигналом (`textChanged` и т. п.) — не подтверждено мутацией
        # именно на этой паре сигналов, см. докстринг задачи.
        blocked = self._servers_root.blockSignals(True)
        self._servers_root.setText(settings.servers_root)
        self._servers_root.blockSignals(blocked)

        self._status.setText(self._store.last_save_error or "")
