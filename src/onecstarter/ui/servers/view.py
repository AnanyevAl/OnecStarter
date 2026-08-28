"""Раздел «Серверы»: список профилей и справочный блок чужих серверов машины.

Мокап — [2026-08-26-v2-servers-mockup.html](../../../../docs/superpowers/specs/
assets/2026-08-26-v2-servers-mockup.html), секция «Раздел „Серверы"». Данные —
`ServersWorkspace` (T-08, задачи 10-13): список профилей, снимок процессов
и производные от него `statuses`/`foreign_servers`. Задача 14 добавила показ
и локальные действия карточки (запуск/остановка/удаление профиля, гашение
сирот) — диалоги «Консоль администрирования…»/«+ Профиль»/«Свойства…» тогда
были инъекциями с безопасным дефолтом `lambda: None`.

**Задача 15** подключает `ServerProfileDialog` (`ui/servers/dialog.py`):
`on_add_profile`/`on_edit_profile` теперь по умолчанию открывают настоящий
диалог (`_default_add_profile`/`_default_edit_profile`), а не молчат —
явная инъекция в конструкторе по-прежнему может подменить поведение (тесты,
и в будущем — другой сценарий вызова). `on_console` дефолт не меняется:
диалог консоли администрирования подключает задача 16, кнопка карточки
пока не связана ни с чем. `servers_root` — новая инъекция (по образцу
`installed`): `SettingsStore.settings.servers_root` читается лениво на
каждое открытие диалога профиля, не запоминается в конструкторе — то же
решение, что и у `installed`, обнаружение платформ и настройки могут
поменяться, пока раздел открыт.

**Круг исправлений 1 (ревью задачи 15, НАХОДКА 2).** Бриф буквально требовал
жёлтую строку у предупреждения и problem-цвет у ошибки в `ServerProfileDialog` —
`_build_add_profile_dialog`/`_build_edit_profile_dialog` прокидывают
`self._palette` (она у `ServersView` уже есть) в новый keyword `palette`
диалога.

Приём тот же, что у `SettingsView`: конструктор строит статичный каркас
(шапка, строка пути), а содержимое, зависящее от снимка процессов
(карточки профилей, блок чужих серверов), собирает `rebuild()` в свои
собственные layout-контейнеры — та же деталь, что различает `_add_row`
у настроек и здесь: карточки перестраиваются целиком на каждый `rebuild()`,
а не правятся на месте, потому что состав профилей и число процессов
у каждого меняются между сканами.

Цвета — ТОЛЬКО из `Palette` (accent/text_dim/problem, урок T-06: зелёного
в палитре нет и не появляется): «работает» — accent, «остановлен» — dim,
«версия не установлена» — problem. У чужих серверов («Другие серверы на
машине») нет ни одной кнопки вовсе (решение заказчика 5) — не «неактивная»,
а отсутствующая как виджет: раздел справочный, отвечает на вопрос «почему
порт занят», а не управляет чужим процессом.

Удаление профиля предупреждает отдельно, если сервер запущен (решение
заказчика 8, `_removal_question`): профиль пропадает из списка, но процесс
`ragent`, если он жив, никто не трогает — молчание об этом стоило бы
пользователю потерянного из виду, но работающего сервера. После
подтверждённого удаления карточка обязана позвать `request_scan()`, как
и запуск/остановка (круг правок 1 ревью задачи 14): без пересчёта снимка
процессов работающий сервер молча пропадает из показа целиком, вместо того
чтобы перейти в «Другие серверы на машине» — `foreign_servers()` отдаёт
классификацию ПРЕЖНЕГО снимка, где процесс ещё сопоставлен со своим (уже
удалённым) профилем.

Удаление вынесено в контекстное меню карточки, а не в кнопку (круг правок 1
ревью задачи 14, решение контроллера): эталон мокапа несёт на карточке
ровно одну кнопку, а паттерн проекта для разрушительных действий —
контекстное меню (`BasesView._build_menu`/`_show_menu`).

`_build_card_menu` строит `QMenu` ЛЕНИВО — по факту правого клика внутри
обработчика `customContextMenuRequested`, тот же приём, что и
`BasesView._show_menu` (не в `_build_menu` заранее для всех строк). Между
`rebuild()` в `self` не хранится ни одного `QMenu` — только пара
`(profile_id, running)` на карточку (круг правок 2 ревью задачи 14, находка
подтверждена эмпирически): жадная сборка меню на каждый `rebuild()`
плодила осиротевший `QMenu`+`QAction` на профиль на каждый тик, потому что
`_clear()` убивает только карточки, а меню с родителем `self` переживают
любое число `rebuild()` вплоть до смерти самой вьюхи — и будут дёргаться
периодическим сканом (задача 16) на каждое обновление списка процессов,
а не на реальный клик пользователя. Тестовый аксессор `profile_menu(index)`
строит меню тем же ленивым билдером по требованию — не читает список.

**Задача 5 (T-10)** добавляет выделение карточки кликом и панель «Журнал
профиля» (`ui/servers/journal_panel.py::JournalPanel`), встроенную низом
раздела тем же приёмом, что `ConnectionPanel` у `BasesView` (добавлена
в layout ПОСЛЕ `addStretch(1)` — карточки/список чужих серверов берут
свободное место, панель прибита к низу). `_ProfileCard` (тонкий `QWidget`
с переопределённым `mouseReleaseEvent`) выделяет себя кликом левой кнопкой;
рамка выделения (`palette.accent`, `_card_border_style`) запечена в
`styleSheet()`, как и остальные цвета карточки, — карточки строятся заново
на каждый `rebuild()`, отдельного «снять подсветку у старой» шага не нужно.
Выбор профиля читает и показывает СУЩЕСТВУЮЩИЙ журнал (`workspace.
journal_path`, услуга задачи 3-4 T-10) — сама панель файл не создаёт и
не следит за ним, только периодически перечитывает хвост, пока видима
и путь задан (её докстринг). §8-исход (см. `_check_pending_confirmation`)
теперь ещё и пишет то же сообщение в журнал профиля через
`workspace.log_event` — молчание платформы ([Ф] А3/А4) не должно означать
дыру в журнале, раз уж OneCStarter сам заметил исход.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.server import ServerProfile
from onecstarter.domain.server_match import ForeignServer
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.services.errors import ServicesError
from onecstarter.services.servers import ServerStatus, ServersWorkspace
from onecstarter.ui.dialogs.buttons import build_confirm_box, is_confirmed
from onecstarter.ui.servers.dialog import ServerProfileDialog
from onecstarter.ui.servers.journal_panel import JournalPanel
from onecstarter.ui.theme import Palette

_MONO = "font-family: Consolas, 'Cascadia Mono', monospace;"
_RANGE_DASH = "–"  # тире мокапа («1560–1591»), не дефис  # noqa: RUF001, RUF003


@dataclass(frozen=True)
class ProfileRow:
    """Что видно на карточке профиля — аксессор тестам, по манере `row_note`/`row_control`
    (`settings_view.py`): проверяют зарегистрированное состояние, а не обход layout.
    """  # noqa: RUF002

    name: str
    status_text: str
    button_text: str
    button_enabled: bool


# -- чистые функции текста: без Qt, испытаны через UI-тесты выше по слою ----


def _status_text(status: ServerStatus) -> str:
    """Текст статуса карточки — статус процессов главнее разрешения версии.

    IMPORTANT 3 (финальное ревью ветки, правка спеки §3.1): раньше
    `resolved is None` проверялся первым и подавлял «работает» даже при
    живом совпавшем процессе — карточка работающего сервера с неразрешённой
    версией (например, после удаления установки, которой он был запущен)
    показывала «версия не установлена», хотя остановка версии не требует
    вовсе. Порядок теперь: сначала процессы (они и есть источник истины
    о статусе, решение заказчика 3), «версия не установлена» — только
    для карточки БЕЗ процессов.
    """  # noqa: RUF002
    processes = status.processes
    if processes:
        pids = ", ".join(f"PID {p.pid}" for p in processes)
        if len(processes) == 1:
            return f"работает · {pids}"
        return f"работает · {pids} · не выбрать, кого останавливать"
    if status.resolved is None:
        return "версия не установлена"
    return "остановлен"


def _status_colour(status: ServerStatus, palette: Palette) -> str:
    """Цвет статуса — тот же приоритет, что `_status_text` (IMPORTANT 3)."""
    if status.processes:
        return palette.accent
    if status.resolved is None:
        return palette.problem
    return palette.text_dim


def _button_state(status: ServerStatus) -> tuple[str, bool]:
    """Текст и активность кнопки — тот же приоритет, что `_status_text` (IMPORTANT 3).

    Остановка не требует разрешённой версии вовсе (`stop` работает по PID
    из снимка, не по установке) — «Остановить» активна независимо от
    `resolved`. «Запустить» неактивна, только если процессов нет И версия
    не разрешилась: запускать действительно нечем.
    """
    count = len(status.processes)
    if count == 1:
        return "Остановить", True
    if count > 1:
        return "Остановить", False
    return "Запустить", status.resolved is not None


def _flags_text(profile: ServerProfile) -> str:
    parts: list[str] = []
    if profile.debug:
        parts.append("-debug")
    if profile.http:
        parts.append("-http")
    extra = profile.extra_args.strip()
    if extra:
        parts.append(extra)
    return " ".join(parts)


def _detail_line(status: ServerStatus) -> str:
    profile = status.profile
    resolved_text = str(status.resolved) if status.resolved is not None else "?"
    ports = (
        f"порты {profile.port} / {profile.regport} / "
        f"{profile.range_start}{_RANGE_DASH}{profile.range_end}"
    )
    line = f"{profile.version} → {resolved_text} · {ports}"
    flags = _flags_text(profile)
    return f"{line} · {flags}" if flags else line


def _removal_question(profile: ServerProfile, running: bool) -> str:
    """Текст вопроса на удаление профиля — решение заказчика 8.

    Запущенный профиль предупреждает отдельно: удаляется только запись
    списка, живой `ragent` (если он есть) никто не трогает и он продолжит
    работать, просто перестанет быть виден в разделе.
    """
    if running:
        return (
            f"Удалить профиль «{profile.name}»? Сервер сейчас работает и "
            "продолжит работать — профиль только перестанет быть виден "
            "в списке серверов."
        )
    return f"Удалить профиль «{profile.name}» из списка серверов?"


def _card_border_style(is_selected: bool, palette: Palette) -> str:
    """Рамка карточки — `palette.accent`, только у выделенной (задача 5, T-10).

    Ширина рамки одна и та же в обоих состояниях (`transparent` у
    невыделенной) — иначе выделение сдвигало бы содержимое карточки
    на толщину рамки.
    """  # noqa: RUF002
    colour = palette.accent if is_selected else "transparent"
    return f"QWidget#ServerCard {{ border: 2px solid {colour}; border-radius: 4px; }}"


def _foreign_text(entry: ForeignServer) -> str:
    """Строка блока «Другие серверы на машине»: полная или ограниченная форма ([Ф] В1).

    Ограниченная — когда командная строка недоступна (`params is None`,
    чужой пользователь или служба): без портов и каталога, версия — только
    если виден путь исполняемого файла (`executable`, доступен без
    повышения даже для SYSTEM-процессов, см. `process_scan.py`).
    """  # noqa: RUF002
    if entry.params is None:
        text = (
            f"PID {entry.process.pid} · нет доступа к командной строке "
            "(другой пользователь или служба)"
        )
        return f"{text} · {entry.version}" if entry.version is not None else text
    version_text = str(entry.version) if entry.version is not None else "?"
    if entry.params.port is not None and entry.params.regport is not None:
        ports = f"порты {entry.params.port} / {entry.params.regport}"
    else:
        ports = "порты ?"
    directory = entry.params.cluster_dir or "?"
    return f"{version_text} · {ports} · {directory} · PID {entry.process.pid}"


class _ProfileCard(QWidget):
    """Карточка профиля: клик левой кнопкой (`mouseRelease`) выделяет её (задача 5, T-10).

    `QLabel`-содержимое карточки (`_build_card`) помечено
    `Qt.WidgetAttribute.WA_TransparentForMouseEvents` — иначе клик по имени/
    статусу/детали доставался бы самой QLabel и никогда не долетел бы сюда:
    Qt отдаёт событие мыши тому виджету, что оказался под курсором, а не
    поднимает его по дереву родителей автоматически. Кнопки карточки
    («Запустить»/«Остановить»/«Погасить») остаются как есть — их клик не
    должен ещё и переключать выделение.
    """  # noqa: RUF002

    def __init__(
        self,
        profile_id: str,
        on_clicked: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile_id = profile_id
        self._on_clicked = on_clicked

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_clicked(self._profile_id)
        super().mouseReleaseEvent(event)


class ServersView(QWidget):
    def __init__(
        self,
        workspace: ServersWorkspace,
        *,
        installed: Callable[[], list[ServerInstallation]],
        palette: Palette,
        servers_root: Callable[[], str] = lambda: "",
        confirm_removal: Callable[[str], bool] | None = None,
        show_error: Callable[[str], None] | None = None,
        on_console: Callable[[], None] = lambda: None,
        on_add_profile: Callable[[], None] | None = None,
        on_edit_profile: Callable[[str], None] | None = None,
        request_scan: Callable[[], None] = lambda: None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._installed = installed
        self._palette = palette
        self._servers_root = servers_root
        # Инъекция диалога, а не вызов модульной функции напрямую — тот же  # noqa: RUF003
        # приём, что `confirm_removal`/`choose_directory` у `BasesView`/  # noqa: RUF003
        # `SettingsView`: настоящий `QMessageBox.exec()` блокирует офскрин-тест.
        self._confirm_removal = confirm_removal or self._default_confirm_removal
        self._show_error = show_error or self._default_show_error
        self._on_console = on_console
        # Задача 15: дефолт больше не no-op — открывает настоящий диалог
        # (см. докстринг модуля). `None` — сигнал «вызывающий не подменял»,
        # а не «вызывающий явно хочет тишину»: лямбда-дефолт в сигнатуре  # noqa: RUF003
        # не мог бы сослаться на ещё не существующий `self`.
        self._on_add_profile = (
            on_add_profile if on_add_profile is not None else self._default_add_profile
        )
        self._on_edit_profile = (
            on_edit_profile if on_edit_profile is not None else self._default_edit_profile
        )
        self._request_scan = request_scan

        self._profile_rows: list[ProfileRow] = []
        self._profile_status_labels: list[QLabel] = []
        self._profile_buttons: list[QPushButton] = []
        # (profile_id, running) на карточку — не QMenu (круг правок 2 ревью
        # задачи 14): меню строится лениво по клику/по требованию теста,
        # см. `_build_card_menu`/`profile_menu` и докстринг модуля.
        self._profile_menu_args: list[tuple[str, bool]] = []
        self._profile_warning_texts: list[list[str]] = []
        self._profile_extinguish_buttons: list[QPushButton | None] = []
        self._profile_cards: list[QWidget] = []
        self._foreign_row_texts: list[str] = []
        self._foreign_row_widgets: list[QWidget] = []
        self._console_note_text = ""
        # Задача 16, §8 (круг исправлений 1): профиль, только что запущенный
        # «Запустить», — проверяется на следующем СВЕЖЕМ снимке сканера
        # (см. on_scan_snapshot/_check_pending_confirmation), не на любом
        # rebuild() — посторонние rebuild() (apply_palette, CRUD профиля)
        # видят ещё старый снимок и не имеют права его потребить.  # noqa: RUF003
        self._pending_confirmation: str | None = None
        # Задача 5 (T-10): выделенная кликом карточка — id профиля или None.
        # Переживает rebuild() (список, а не виджет: карточки пересобираются  # noqa: RUF003
        # целиком, id — нет), сбрасывается только явно (`_clear_selection`,
        # зовётся из `_remove` для удалённого выделенного профиля).
        self._selected_profile_id: str | None = None

        header = QLabel("Серверы")
        header_font = header.font()
        header_font.setPointSize(13)
        header_font.setBold(True)
        header.setFont(header_font)

        self._console_button = QPushButton("Консоль администрирования…")
        self._console_button.clicked.connect(lambda: self._on_console())
        self._add_button = QPushButton("+ Профиль")
        self._add_button.clicked.connect(lambda: self._on_add_profile())

        head_row = QHBoxLayout()
        head_row.addWidget(header)
        head_row.addStretch(1)
        head_row.addWidget(self._console_button)
        head_row.addWidget(self._add_button)

        self._path_label = QLabel("")
        self._path_label.setObjectName("ServersSub")
        self._path_label.setWordWrap(True)

        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(10)

        self._foreign_label = QLabel("ДРУГИЕ СЕРВЕРЫ НА МАШИНЕ")  # noqa: RUF001
        self._foreign_label.setObjectName("ServersGroupLabel")
        self._foreign_layout = QVBoxLayout()
        self._foreign_layout.setSpacing(4)

        # Задача 5 (T-10): та же компоновка, что detail-панель «Баз»
        # (`ConnectionPanel` в `BasesView` — карточки/дерево берут `stretch`,
        # панель прибита снизу без него) — добавлена ПОСЛЕ `addStretch(1)`.
        self._journal_panel = JournalPanel(palette=self._palette, parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        layout.addLayout(head_row)
        layout.addWidget(self._path_label)
        layout.addSpacing(10)
        layout.addLayout(self._cards_layout)
        layout.addSpacing(14)
        layout.addWidget(self._foreign_label)
        layout.addLayout(self._foreign_layout)
        layout.addStretch(1)
        layout.addWidget(self._journal_panel)

        self.rebuild()

    # -- сборка содержимого -------------------------------------------------

    def rebuild(self) -> None:
        """Перечитать `statuses`/`foreign_servers` и пересобрать карточки целиком.

        Не правка на месте: число карточек и число процессов у каждой могут
        поменяться между сканами, отслеживать разницу дороже и рискованнее,
        чем перестроить — тот же выбор, что и у `BasesView.rebuild()`.
        """  # noqa: RUF002
        self._clear(self._cards_layout)
        self._clear(self._foreign_layout)
        self._profile_rows = []
        self._profile_status_labels = []
        self._profile_buttons = []
        self._profile_menu_args = []
        self._profile_warning_texts = []
        self._profile_extinguish_buttons = []
        self._profile_cards = []
        self._foreign_row_texts = []
        self._foreign_row_widgets = []

        server_installations = self._installed()
        installed_versions = [si.installation.version for si in server_installations]
        statuses = self._workspace.statuses(installed_versions)
        for status in statuses:
            self._build_card(status, server_installations)
        for entry in self._workspace.foreign_servers():
            self._build_foreign_row(entry)

        self._console_note_text = self._read_console_note()
        self._path_label.setText(
            f"{self._workspace.store_path} · статус — по живым процессам · "
            f"консоль: {self._console_note_text}"
        )

    def on_scan_snapshot(self) -> None:
        """Единственная точка входа §8: свежий снимок сканера уже применён.

        Круг исправлений 1 (ревью задачи 16, Important): `rebuild()` дёргают
        минимум шесть посторонних путей — `apply_palette`, `_remove`,
        `_extinguish`, `_apply_new_profile`, `_apply_edited_profile`,
        `on_installations` (`app.py`) — и ЛЮБОЙ из них в первые секунды после
        «Запустить» видел бы ещё СТАРЫЙ снимок процессов: проверка §8 внутри
        самого `rebuild()` потребляла бы ожидание на этом чужом вызове и
        репортовала бы «умер сразу» о живом, только что запущенном сервере.
        Поэтому проверка живёт здесь, а не в `rebuild()`, и зовётся ровно из
        одного места проводки (`ui/app.py::_build_main_window`):
        `ServerMonitor.snapshot_ready` → `servers_workspace.apply_scan` →
        `servers_view.on_scan_snapshot()`. Метод сам делает `rebuild()` (тот
        же порядок, что раньше — карточки обязаны отразить снимок ДО того,
        как решаем, показывать ли предупреждение) и уже поверх пересчитанных
        `statuses` проверяет ожидающий профиль.
        """  # noqa: RUF002
        self.rebuild()
        server_installations = self._installed()
        installed_versions = [si.installation.version for si in server_installations]
        self._check_pending_confirmation(self._workspace.statuses(installed_versions))

    def _check_pending_confirmation(self, statuses: Sequence[ServerStatus]) -> None:
        """§8 мокапа, [Ф] А3/А4: платформа о смерти ragent сама ничего не пишет.

        Зовётся ТОЛЬКО из `on_scan_snapshot()` (см. её докстринг, круг
        исправлений 1) — не из `rebuild()`. `_toggle` запоминает профиль как
        «ожидает подтверждения» ПОСЛЕ своего собственного немедленного
        `rebuild()` (см. её докстринг): к моменту, когда сюда приходит
        управление, снимок процессов уже гарантированно новый. Профиль
        всё ещё без процессов — типичная причина, которую видит
        пользователь, — порт уже занят другим сервером, поднявшимся раньше.
        Срабатывает не более одного раза на каждую постановку в ожидание —
        флаг сбрасывается здесь безусловно, до всякого решения о показе.

        Задача 5 (T-10): тот же текст, что уходит в `show_error`, ЕЩЁ и
        пишется в журнал профиля через `workspace.log_event` — платформа
        по-прежнему молчит ([Ф] А3/А4), но раз уж OneCStarter сам заметил
        исход, «Журнал профиля» обязан его показать, а не оставить дыру
        между «запуск: …» и следующим событием.
        """  # noqa: RUF002
        profile_id = self._pending_confirmation
        if profile_id is None:
            return
        self._pending_confirmation = None
        status = next((s for s in statuses if s.profile.id == profile_id), None)
        if status is None or status.processes:
            return
        profile = status.profile
        message = (
            f"Сервер «{profile.name}» завершился сразу после запуска. "
            f"Частая причина — занятый порт ({profile.port})."
        )
        self._workspace.log_event(profile_id, message)
        self._show_error(message)

    @staticmethod
    def _clear(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _read_console_note(self) -> str:
        version = self._workspace.current_console_version()
        return str(version) if version is not None else "не зарегистрирована"

    def _build_card(
        self, status: ServerStatus, server_installations: Sequence[ServerInstallation]
    ) -> None:
        profile = status.profile
        palette = self._palette
        pending = self._workspace.scan_pending
        button_tooltip = ""
        if pending:
            # IMPORTANT 4b (финальное ревью ветки, §4.4): до первого снимка
            # процессов состояние карточки неизвестно — «остановлен» было бы
            # враньём (сервер мог уже работать), а активная «Запустить»  # noqa: RUF003
            # рисковала бы породить второй ragent поверх уже живого, ещё
            # не увиденного скана (§6.4). Слепое окно теперь короче:
            # monitor.start() сам просит снимок немедленно
            # (ui/servers/monitor.py::start), но до его прихода карточка  # noqa: RUF003
            # обязана молчать, а не гадать по снимку из прошлого раза.  # noqa: RUF003
            status_text = "…"
            colour = palette.text_dim
            button_text, button_enabled = "Запустить", False
            button_tooltip = "Идёт первый скан процессов — подождите"
        else:
            status_text = _status_text(status)
            colour = _status_colour(status, palette)
            button_text, button_enabled = _button_state(status)
        running = bool(status.processes)

        # Задача 5 (T-10): _ProfileCard — тот же QWidget, что и раньше, плюс
        # mouseReleaseEvent, выделяющий карточку кликом (см. её докстринг).
        card = _ProfileCard(profile.id, self._select_profile, parent=self)
        card.setObjectName("ServerCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(_card_border_style(profile.id == self._selected_profile_id, palette))
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 4, 6, 4)
        card_layout.setSpacing(2)

        title_row = QHBoxLayout()
        name_label = QLabel(profile.name)
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"color: {colour};")
        title_row.addWidget(name_label)
        title_row.addWidget(status_label)
        title_row.addStretch(1)

        detail_label = QLabel(_detail_line(status))
        detail_label.setStyleSheet(f"color: {palette.text_dim}; {_MONO}")
        dir_label = QLabel(profile.cluster_dir)
        dir_label.setStyleSheet(f"color: {palette.text_dim}; {_MONO}")
        # Клик по этим ярлыкам обязан выделять карточку, а не пропадать в  # noqa: RUF003
        # них молча — Qt доставляет событие мыши тому виджету, что оказался
        # под курсором, а не поднимает его по дереву родителей автоматически  # noqa: RUF003
        # (см. докстринг `_ProfileCard`). WA_TransparentForMouseEvents
        # переносит попадание на саму карточку.
        for label in (name_label, status_label, detail_label, dir_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        body_col = QVBoxLayout()
        body_col.setSpacing(1)
        body_col.addLayout(title_row)
        body_col.addWidget(detail_label)
        body_col.addWidget(dir_label)

        toggle_button = QPushButton(button_text)
        toggle_button.setEnabled(button_enabled)
        if button_tooltip:
            toggle_button.setToolTip(button_tooltip)
        toggle_button.clicked.connect(
            lambda _checked=False, pid=profile.id, si=server_installations, r=running: (
                self._toggle(pid, si, r)
            )
        )
        control_col = QVBoxLayout()
        control_col.addWidget(toggle_button)

        body_row = QHBoxLayout()
        body_row.addLayout(body_col, 1)
        body_row.addLayout(control_col)
        card_layout.addLayout(body_row)

        # Удаление — контекстным меню карточки, не кнопкой (круг правок 1
        # ревью задачи 14): эталон мокапа несёт одну кнопку на карточку,
        # разрушительное действие — тем же паттерном, что и у BasesView  # noqa: RUF003
        # (_build_menu/_show_menu). Меню строится ЛЕНИВО внутри обработчика —
        # круг правок 2: жадная сборка на каждый rebuild() плодила
        # осиротевший QMenu на профиль на каждый тик периодического скана
        # (см. докстринг модуля); здесь сохраняются только (id, running).
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda position, w=card, pid=profile.id, r=running: (
                self._build_card_menu(pid, r).exec(w.mapToGlobal(position))
            )
        )

        warnings: list[str] = []
        if status.dir_mismatch:
            resolved_text = str(status.resolved) if status.resolved is not None else "?"
            text = (
                f"Каталог кластера похож на другую версию, а разрешилась "  # noqa: RUF001
                f"{resolved_text} — проверьте путь"
            )
            warnings.append(text)
            mismatch_label = QLabel(text)
            mismatch_label.setWordWrap(True)
            mismatch_label.setStyleSheet(f"color: {palette.problem};")
            card_layout.addWidget(mismatch_label)

        extinguish_button: QPushButton | None = None
        if status.orphans:
            pids = ", ".join(str(orphan.pid) for orphan in status.orphans)
            text = (
                f"Осиротевшие процессы без ragent: PID {pids} — держат "
                "порт регистрации"
            )
            warnings.append(text)
            orphan_row = QHBoxLayout()
            orphan_label = QLabel(text)
            orphan_label.setWordWrap(True)
            orphan_label.setStyleSheet(f"color: {palette.problem};")
            extinguish_button = QPushButton("Погасить")
            extinguish_button.clicked.connect(
                lambda _checked=False, pid=profile.id: self._extinguish(pid)
            )
            orphan_row.addWidget(orphan_label, 1)
            orphan_row.addWidget(extinguish_button)
            card_layout.addLayout(orphan_row)

        self._cards_layout.addWidget(card)
        self._profile_rows.append(
            ProfileRow(
                name=profile.name,
                status_text=status_text,
                button_text=button_text,
                button_enabled=button_enabled,
            )
        )
        self._profile_status_labels.append(status_label)
        self._profile_buttons.append(toggle_button)
        self._profile_menu_args.append((profile.id, running))
        self._profile_warning_texts.append(warnings)
        self._profile_extinguish_buttons.append(extinguish_button)
        self._profile_cards.append(card)

    def _build_card_menu(self, profile_id: str, running: bool) -> QMenu:
        """Собрать контекстное меню карточки без показа — по требованию, не заранее.

        Вызывается лениво: из обработчика `customContextMenuRequested`
        (реальный клик) и из `profile_menu` (тестовый аксессор) — никогда
        из `_build_card`/`rebuild()` (круг правок 2 ревью задачи 14, см.
        докстринг модуля). Отдельный метод, а не однострочный `QMenu` внутри
        вызывающих — тот же приём, что `BasesView._build_menu`: состав
        пунктов проверяется на настоящем виджете без блокирующего `exec()`.
        Задача 15 добавляет «Свойства…» первым пунктом (перед «Удалить
        профиль…», по брифу) — диалог правки, тем же путём (`_on_edit_profile`)
        через который его подменяют тесты, минуя `ServerProfileDialog.exec()`.
        """  # noqa: RUF002
        menu = QMenu(self)
        menu.addAction("Свойства…", lambda: self._on_edit_profile(profile_id))
        menu.addAction(
            "Удалить профиль…", lambda: self._remove(profile_id, running)
        )
        return menu

    def _build_foreign_row(self, entry: ForeignServer) -> None:
        text = _foreign_text(entry)
        widget = QWidget()
        row_layout = QHBoxLayout(widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        label.setStyleSheet(f"color: {self._palette.text_dim}; {_MONO}")
        label.setWordWrap(True)
        row_layout.addWidget(label)
        self._foreign_layout.addWidget(widget)
        self._foreign_row_texts.append(text)
        self._foreign_row_widgets.append(widget)

    # -- реакции --------------------------------------------------------------

    def _toggle(
        self, profile_id: str, server_installations: Sequence[ServerInstallation], running: bool
    ) -> None:
        started = False
        try:
            if running:
                self._workspace.stop(profile_id)
            else:
                self._workspace.start(profile_id, server_installations)
                started = True
        except ServicesError as error:
            self._show_error(str(error))
        self._request_scan()
        self.rebuild()
        if started:
            # Задача 16, §8: запомнить профиль ПОСЛЕ этого rebuild(), не до —
            # этот вызов ещё использует снимок процессов ДО запуска (сканы
            # асинхронны, `request_scan()` только просит новый, не ждёт его),  # noqa: RUF003
            # и немедленная проверка на нём ложно репортовала бы «умер сразу»
            # на каждый успешный запуск. Только «Запустить» ставит в ожидание —
            # у остановки нечего подтверждать (см. `_check_pending_confirmation`).  # noqa: RUF003
            self._pending_confirmation = profile_id

    def _select_profile(self, profile_id: str) -> None:
        """Клик по карточке (задача 5, T-10): выделить и показать её журнал.

        Профиль мог пропасть из списка между показом карточки и кликом
        (тот же довод, что у `_build_edit_profile_dialog`) — тихий выход,
        а не отказ: карточки, ссылающейся на несуществующий id, к моменту
        обработки клика быть не должно, но гонка не стоит показа ошибки
        пользователю. `rebuild()` в конце — тот же приём, что у `_toggle`/
        `_remove`: рамка выделения запечена в `styleSheet()` карточки
        (`_card_border_style`), а карточки строятся заново целиком.
        """  # noqa: RUF002
        profile = next((p for p in self._workspace.profiles() if p.id == profile_id), None)
        if profile is None:
            return
        self._selected_profile_id = profile_id
        self._journal_panel.show_journal(profile.name, self._workspace.journal_path(profile_id))
        self.rebuild()

    def _clear_selection(self) -> None:
        self._selected_profile_id = None
        self._journal_panel.show_journal("", None)

    def _remove(self, profile_id: str, running: bool) -> None:
        profile = next((p for p in self._workspace.profiles() if p.id == profile_id), None)
        if profile is None:
            return
        if not self._confirm_removal(_removal_question(profile, running)):
            return
        try:
            self._workspace.remove_profile(profile_id)
        except ServicesError as error:
            self._show_error(str(error))
        # Задача 5 (T-10): удаление ВЫДЕЛЕННОГО профиля сбрасывает панель
        # в плейсхолдер — иначе «Журнал профиля» продолжал бы показывать
        # журнал записи, которой больше нет в списке серверов. Проверка
        # по факту (профиля больше нет среди profiles()), а не по успеху  # noqa: RUF003
        # remove_profile() — отказ (маловероятный: id только что был в
        # рендере карточки) обязан оставить выделение как было.
        if self._selected_profile_id == profile_id and not any(
            p.id == profile_id for p in self._workspace.profiles()
        ):
            self._clear_selection()
        # Находка ревью задачи 14 (круг правок 1), подтверждена эмпирически:
        # без пересчёта снимка удаление РАБОТАЮЩЕГО профиля выкидывало его  # noqa: RUF003
        # процесс из показа целиком — `foreign_servers()` отдаёт
        # классификацию ПРЕЖНЕГО `apply_scan`, где процесс ещё сопоставлен
        # со своим (уже удалённым) профилем и в `foreign` не попадает.  # noqa: RUF003
        # Решение заказчика 8 требует, чтобы сервер «продолжил работать»
        # и стал виден как чужой — без `request_scan()` он не виден никак.
        self._request_scan()
        self.rebuild()

    def _extinguish(self, profile_id: str) -> None:
        try:
            self._workspace.stop_orphans(profile_id)
        except ServicesError as error:
            self._show_error(str(error))
        self._request_scan()
        self.rebuild()

    # -- диалог профиля (задача 15) --------------------------------------------
    #
    # Приём тот же, что у `BasesView` («build → exec → apply», задача 8):  # noqa: RUF003
    # сборка диалога отделена от показа и от записи, чтобы каждый шаг
    # проверялся без блокирующего `QDialog.exec()`. `_default_add_profile`/
    # `_default_edit_profile` — единственные места, где `exec()` реально
    # вызывается; тесты подменяют его через `monkeypatch.setattr(  # noqa: RUF003
    # ServerProfileDialog, "exec", ...)`, как это делает `test_bases_view.py`
    # для `InfobaseDialog`.

    def _build_add_profile_dialog(self) -> ServerProfileDialog:
        return ServerProfileDialog.for_new(
            self._workspace.profiles(),
            self._installed(),
            self._servers_root(),
            parent=self,
            palette=self._palette,
        )

    def _default_add_profile(self) -> None:
        dialog = self._build_add_profile_dialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_new_profile(dialog)

    def _apply_new_profile(self, dialog: ServerProfileDialog) -> None:
        try:
            self._workspace.add_profile(dialog.result_profile())
        except ServicesError as error:
            self._show_error(str(error))
        # IMPORTANT 6 (финальное ревью ветки): симметрично `_remove`/`_toggle`
        # (см. их докстринги) — без запроса рескана новый профиль мог бы
        # совпасть с УЖЕ живым чужим процессом (переиспользованный каталог  # noqa: RUF003
        # кластера) и не увидеть его сразу. `ServersWorkspace._save` сама  # noqa: RUF003
        # пересопоставляет уже ИМЕЮЩИЙСЯ снимок синхронно (см. её докстринг),
        # `request_scan()` здесь — за свежими данными, которых в старом
        # снимке ещё не было (например, о версии из живого процесса).  # noqa: RUF003
        self._request_scan()
        self.rebuild()

    def _build_edit_profile_dialog(self, profile_id: str) -> ServerProfileDialog | None:
        """`None` — профиль пропал из списка между показом карточки и кликом."""
        profile = next((p for p in self._workspace.profiles() if p.id == profile_id), None)
        if profile is None:
            return None
        others = [p for p in self._workspace.profiles() if p.id != profile_id]
        return ServerProfileDialog.for_edit(
            profile,
            others,
            self._installed(),
            self._servers_root(),
            parent=self,
            palette=self._palette,
        )

    def _default_edit_profile(self, profile_id: str) -> None:
        dialog = self._build_edit_profile_dialog(profile_id)
        if dialog is None:
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_edited_profile(dialog)

    def _apply_edited_profile(self, dialog: ServerProfileDialog) -> None:
        try:
            self._workspace.update_profile(dialog.result_profile())
        except ServicesError as error:
            self._show_error(str(error))
        # IMPORTANT 6 (финальное ревью ветки): тот же довод, что у  # noqa: RUF003
        # `_apply_new_profile` — правка каталога кластера профиля обязана
        # обновить показ немедленно, а не ждать планового скана (до 5 с).  # noqa: RUF003
        self._request_scan()
        self.rebuild()

    # -- дефолты инъекций (переопределяются тестами) --------------------------

    def _default_confirm_removal(self, question: str) -> bool:
        box = build_confirm_box(self, "OneCStarter", question)
        # box.buttons() типизирован как list[QAbstractButton] в стабах PySide6,
        # но setDefaultButton() принимает только QPushButton — тот же приём,
        # что и в dialogs/confirm.py::build_removal_confirm_box: фактический
        # тип рантайма QPushButton гарантирован тем, что build_confirm_box
        # добавляет кнопки только через addButton(text, role).
        no_button = cast(
            QPushButton | None, next((b for b in box.buttons() if b.text() == "Нет"), None)
        )
        if no_button is not None:
            box.setDefaultButton(no_button)
        box.exec()
        return is_confirmed(box)

    def _default_show_error(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("OneCStarter")
        box.setText(message)
        box.exec()

    # -- палитра ----------------------------------------------------------------

    def apply_palette(self, palette: Palette) -> None:
        """Перекрасить перерисовкой: карточки несут цвет в запечённом `styleSheet`."""
        self._palette = palette
        self._journal_panel.apply_palette(palette)
        self.rebuild()

    # -- доступ для тестов --------------------------------------------------

    def profile_rows(self) -> list[ProfileRow]:
        return list(self._profile_rows)

    def profile_status_label(self, index: int) -> QLabel:
        return self._profile_status_labels[index]

    def profile_button(self, index: int) -> QPushButton:
        return self._profile_buttons[index]

    def profile_card(self, index: int) -> QWidget:
        return self._profile_cards[index]

    def selected_profile_id(self) -> str | None:
        return self._selected_profile_id

    def journal_panel(self) -> JournalPanel:
        return self._journal_panel

    def profile_menu(self, index: int) -> QMenu:
        """Контекстное меню карточки — тестам, без показа (по образцу `BasesView`).

        Строит СВЕЖИЙ `QMenu` тем же ленивым билдером (`_build_card_menu`),
        что и реальный клик — не читает предсозданный список (круг правок 2
        ревью задачи 14: между `rebuild()` в `self` не хранится ни одного
        `QMenu`, только пара `(profile_id, running)`). Тестируется прямым
        `trigger()` пункта, не открытием настоящего `QMenu.exec()`.
        """
        profile_id, running = self._profile_menu_args[index]
        return self._build_card_menu(profile_id, running)

    def profile_warnings(self, index: int) -> list[str]:
        return list(self._profile_warning_texts[index])

    def profile_extinguish_button(self, index: int) -> QPushButton | None:
        return self._profile_extinguish_buttons[index]

    def foreign_rows(self) -> list[str]:
        return list(self._foreign_row_texts)

    def foreign_row_widget(self, index: int) -> QWidget:
        return self._foreign_row_widgets[index]

    def console_note(self) -> str:
        return self._console_note_text

    def path_text(self) -> str:
        return self._path_label.text()

    def console_button(self) -> QPushButton:
        return self._console_button

    def add_profile_button(self) -> QPushButton:
        return self._add_button
