"""Диалог профиля сервера и диалог смены версии консоли администрирования.

Мокап — [2026-08-26-v2-servers-mockup.html](../../../../docs/superpowers/specs/
assets/2026-08-26-v2-servers-mockup.html), секции «Диалог профиля» и «Смена версии
консоли администрирования». Образцы приёмов — `ui/dialogs/infobase.py`
(`InfobaseDialog.for_new`/`for_edit`, живая валидация полей, инъекция
`choose_directory`) и `ui/dialogs/confirm.py` (сборка диалога отдельно от
показа). T-08, задача 15.

**`ServerProfileDialog`.** Живая валидация на каждое изменение поля: черновик
`ServerProfile` собирается из текущих значений виджетов и прогоняется через
`validate_profile`/`warn_range_overlap` (domain/server.py) с нормализацией
`normalize_cluster_dir` (domain/server_match.py) — теми же чистыми функциями,
которыми `ServersWorkspace` проверяет профиль перед записью
(`services/servers.py::_validate`). Диалог не изобретает собственных правил
валидации, только читает их результат.

Диапазон портов — единственное составное поле формы (`start:end` в одном
`QLineEdit`, мокап): формат, не разбирающийся как два числа через
двоеточие, — собственная ошибка ДО вызова `validate_profile` (`_parse_range`
возвращает `None`, `_refresh_state` останавливается на этом раньше, чем
успевает собрать черновик с осмысленными `range_start`/`range_end`).

**Подстановка каталога (спека §3.2, «Каталог кластера подставляется от
разрешённой версии, не маски»).** Обработчик подписан ТОЛЬКО на сигнал
изменения поля версии (`currentTextChanged`), а не вызывается из общего
`_refresh_state` — иначе первый же пересчёт состояния диалога (в конце
`__init__`, до того как пользователь вообще тронул форму) переписал бы
каталог уже сохранённого профиля в `for_edit`, то есть нетронутый диалог
менял бы данные пользователя тем же классом дефекта, ради которого написан
весь `infobase.py` («untouched dialog does nothing»). Подписка ставится
ПОСЛЕ того, как начальные значения полей уже расставлены, поэтому
программная инициализация текста версии сама подстановку не запускает.

Условие подстановки — «каталог пуст ИЛИ ещё не правился руками» (обе
половины ИЛИ, буквально по брифу): once пользователь стёр подставленный
каталог руками, пустое поле продолжает подставляться при следующей смене
версии, а вот руками ВПИСАННЫЙ путь (`textEdited`, не программный `setText`)
останавливает подстановку насовсем для этой сессии диалога, пока каталог
снова не станет пустым. Кнопка «Обзор…» тоже считается ручной правкой —
пользователь явно выбрал каталог, это не менее осознанное решение, чем
ввод текста, хотя `textEdited` при программном `setText()` из обработчика
кнопки не эмитится (потому флаг выставляется явно в обработчике, а не
только слушанием сигнала).

**Про цвета.** Диалог, как и `InfobaseDialog`, не запекает свой `Palette` —
классы `for_new`/`for_edit` в задаче намеренно не несут параметра палитры,
а `InfobaseDialog._required_hint` (образец, на который ссылается бриф)
тоже не красит строку пояснения, полагаясь на общий stylesheet приложения.
Ошибка и предупреждение здесь — два отдельных `QLabel` (`error_text()`/
`warning_text()`), различаемых по смыслу и по влиянию на «ОК», а не по
запечённому HEX-цвету; сильная раскраска через `Palette` — материал для
отдельной находки ревью, если понадобится.

**`ConsoleDialog`.** Только собирает выбор пользователя — версии
с `radmin.dll` (`installed`), метки «текущая» ([Ф] Г2, чтение HKLM без UAC)
и «работает» ([Ф] Г3 — консоль требует точного совпадения сборки с сервером,
поэтому пользователю показывается, какие версии сейчас держат живой
`ragent`). Саму перерегистрацию (`ServersWorkspace.register_console`)
и открытие `.msc` (`open_console`) диалог не зовёт — это задача 16,
у которой будет доступ и к `ServersWorkspace`, и к `Palette` для интеграции
с остальным разделом. Кнопки «Сделать текущей и открыть»/«Открыть» тут —
только состояние `enabled`, обработчики клика на них навешивает вызывающий
код следующей задачи.
"""  # noqa: RUF002

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.server import (
    ServerProfile,
    resolve_server_version,
    validate_profile,
    warn_range_overlap,
)
from onecstarter.domain.server_match import normalize_cluster_dir
from onecstarter.domain.version import VersionNumber
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

_RANGE_FORMAT_ERROR = "Диапазон — два числа через двоеточие"
_REGPORT_CHANGE_WARNING = (
    "Смена порта регистрации заведёт новый пустой реестр кластера рядом со старым"  # noqa: RUF001
)
_DEFAULT_PORT = "1540"
_DEFAULT_REGPORT = "1541"
_DEFAULT_RANGE = "1560:1591"


def browse_for_directory() -> str:
    """Системный диалог выбора каталога кластера. Пустая строка — отмена.

    Свой экземпляр функции, не импорт `dialogs.infobase.browse_for_directory` —
    тот же выбор, что сделала `SettingsView` для `browse_for_servers_root`:
    модули диалогов друг о друге не знают, инъекция (`choose_directory`)
    и так делает настоящий `QFileDialog` заменимым в тестах.
    """  # noqa: RUF002
    return QFileDialog.getExistingDirectory()


def _parse_int(text: str) -> int:
    """Целое из поля порта. Не число — 0: вне диапазона 1-65535, ошибка найдётся сама."""  # noqa: RUF002
    stripped = text.strip()
    return int(stripped) if stripped.isdigit() else 0


def _parse_range(text: str) -> tuple[int, int] | None:
    """`start:end` из одного поля диапазона. `None` — не разобралось как два числа."""
    parts = text.strip().split(":")
    if len(parts) != 2:
        return None
    start, end = (part.strip() for part in parts)
    if not (start.isdigit() and end.isdigit()):
        return None
    return int(start), int(end)


def _substituted_dir(servers_root: str, resolved: VersionNumber | None) -> str | None:
    """Каталог кластера от корня и РАЗРЕШЁННОЙ версии (спека §3.2). `None` — нечего подставлять."""
    if not servers_root or resolved is None:
        return None
    return servers_root + os.sep + f"srv_{resolved}"


class ServerProfileDialog(QDialog):
    def __init__(
        self,
        profile: ServerProfile | None,
        *,
        existed: Sequence[ServerProfile],
        installed: Sequence[ServerInstallation],
        servers_root: str,
        parent: QWidget | None = None,
        choose_directory: Callable[[], str] = browse_for_directory,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._existed = list(existed)
        self._installed = list(installed)
        self._servers_root = servers_root
        self._choose_directory = choose_directory
        # Флаг «трогал руками»: останавливает автоподстановку каталога
        # (см. докстринг модуля). Программные setText из подстановки самой
        # его не выставляют — только textEdited (ввод) и явная установка  # noqa: RUF003
        # в обработчике «Обзор…» (тоже осознанный ручной выбор).
        self._dir_touched = False

        self.setWindowTitle(
            f"Профиль сервера — {profile.name}" if profile is not None else "Профиль сервера"
        )

        self._name_edit = QLineEdit(profile.name if profile is not None else "")

        self._version_combo = QComboBox()
        self._version_combo.setEditable(True)
        for installation in self._installed:
            self._version_combo.addItem(str(installation.installation.version))
        if profile is not None:
            self._version_combo.setEditText(profile.version)
        else:
            self._version_combo.setCurrentIndex(-1)
            self._version_combo.setEditText("")

        self._resolved_label = QLabel("")
        version_row = QWidget()
        version_row_layout = QHBoxLayout(version_row)
        version_row_layout.setContentsMargins(0, 0, 0, 0)
        version_row_layout.addWidget(self._version_combo, 1)
        version_row_layout.addWidget(self._resolved_label)

        self._port_edit = QLineEdit(str(profile.port) if profile is not None else _DEFAULT_PORT)
        self._regport_edit = QLineEdit(
            str(profile.regport) if profile is not None else _DEFAULT_REGPORT
        )
        port_row = QWidget()
        port_row_layout = QHBoxLayout(port_row)
        port_row_layout.setContentsMargins(0, 0, 0, 0)
        port_row_layout.addWidget(self._port_edit)
        port_row_layout.addWidget(QLabel("регистрации"))
        port_row_layout.addWidget(self._regport_edit)

        self._range_edit = QLineEdit(
            f"{profile.range_start}:{profile.range_end}" if profile is not None else _DEFAULT_RANGE
        )

        self._dir_edit = QLineEdit(profile.cluster_dir if profile is not None else "")
        self._browse_button = QPushButton("Обзор…")
        self._browse_button.clicked.connect(self._browse_for_directory)
        dir_row = QWidget()
        dir_row_layout = QHBoxLayout(dir_row)
        dir_row_layout.setContentsMargins(0, 0, 0, 0)
        dir_row_layout.addWidget(self._dir_edit, 1)
        dir_row_layout.addWidget(self._browse_button)

        self._debug_checkbox = QCheckBox()
        self._debug_checkbox.setChecked(profile.debug if profile is not None else True)
        self._http_checkbox = QCheckBox()
        self._http_checkbox.setChecked(profile.http if profile is not None else True)
        self._extra_edit = QLineEdit(profile.extra_args if profile is not None else "")

        form = QFormLayout()
        form.addRow("Имя", self._name_edit)
        form.addRow("Версия", version_row)
        form.addRow("Порт", port_row)
        form.addRow("Диапазон", self._range_edit)
        form.addRow("Каталог кластера", dir_row)
        form.addRow("Отладка (-debug)", self._debug_checkbox)
        form.addRow("HTTP (-http)", self._http_checkbox)
        form.addRow("Доп. аргументы", self._extra_edit)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)

        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        # box.buttons() типизирован как list[QAbstractButton] в стабах PySide6 —
        # тот же cast, что и в dialogs/confirm.py: фактический тип рантайма
        # QPushButton гарантирован тем, что russian_button_box добавляет
        # кнопки только через QDialogButtonBox.addButton(text, role).
        self._ok_button = cast(
            QPushButton,
            next(
                button
                for button in self._buttons.buttons()
                if self._buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole
            ),
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addWidget(self._warning_label)
        layout.addWidget(self._buttons)

        # Подписка — после того как начальные значения полей уже расставлены
        # (см. докстринг модуля): программная инициализация версии/полей сама
        # ничего не пересчитывает и не подставляет.
        self._name_edit.textChanged.connect(self._refresh_state)
        self._port_edit.textChanged.connect(self._refresh_state)
        self._regport_edit.textChanged.connect(self._refresh_state)
        self._range_edit.textChanged.connect(self._refresh_state)
        self._dir_edit.textEdited.connect(self._mark_dir_touched)
        self._dir_edit.textChanged.connect(self._refresh_state)
        self._version_combo.currentTextChanged.connect(self._maybe_substitute_dir)
        self._version_combo.currentTextChanged.connect(self._refresh_state)

        self._refresh_state()

    @classmethod
    def for_new(
        cls,
        existed: Sequence[ServerProfile],
        installed: Sequence[ServerInstallation],
        servers_root: str,
        parent: QWidget | None = None,
        *,
        choose_directory: Callable[[], str] = browse_for_directory,
    ) -> "ServerProfileDialog":
        return cls(
            None,
            existed=existed,
            installed=installed,
            servers_root=servers_root,
            parent=parent,
            choose_directory=choose_directory,
        )

    @classmethod
    def for_edit(
        cls,
        profile: ServerProfile,
        existed_without_self: Sequence[ServerProfile],
        installed: Sequence[ServerInstallation],
        servers_root: str,
        parent: QWidget | None = None,
        *,
        choose_directory: Callable[[], str] = browse_for_directory,
    ) -> "ServerProfileDialog":
        return cls(
            profile,
            existed=existed_without_self,
            installed=installed,
            servers_root=servers_root,
            parent=parent,
            choose_directory=choose_directory,
        )

    # -- подстановка каталога и живая валидация ------------------------------

    def _mark_dir_touched(self, _text: str) -> None:
        self._dir_touched = True

    def _browse_for_directory(self) -> None:
        path = self._choose_directory()
        if not path:
            return
        # Явный выбор каталога — такая же ручная правка, как ввод текста
        # (см. докстринг модуля): останавливает дальнейшую автоподстановку,
        # хотя setText() ниже сам textEdited не эмитит.
        self._dir_touched = True
        self._dir_edit.setText(path)

    def _maybe_substitute_dir(self, _text: str = "") -> None:
        """Спека §3.2: подставить `<корень>\\srv_<разрешённая>`, если можно и не мешали."""
        resolved = resolve_server_version(
            self._version_combo.currentText(),
            [installation.installation.version for installation in self._installed],
        )
        target = _substituted_dir(self._servers_root, resolved)
        if target is None:
            return
        if self._dir_edit.text() != "" and self._dir_touched:
            return
        if self._dir_edit.text() != target:
            self._dir_edit.setText(target)

    def _draft_profile(self, range_parsed: tuple[int, int] | None = None) -> ServerProfile:
        if range_parsed is None:
            range_parsed = _parse_range(self._range_edit.text()) or (0, 0)
        range_start, range_end = range_parsed
        return ServerProfile(
            id=self._profile.id if self._profile is not None else "",
            name=self._name_edit.text().strip(),
            version=self._version_combo.currentText().strip(),
            port=_parse_int(self._port_edit.text()),
            regport=_parse_int(self._regport_edit.text()),
            range_start=range_start,
            range_end=range_end,
            cluster_dir=self._dir_edit.text().strip(),
            debug=self._debug_checkbox.isChecked(),
            http=self._http_checkbox.isChecked(),
            extra_args=self._extra_edit.text(),
        )

    def _refresh_state(self, *_args: object) -> None:
        resolved = resolve_server_version(
            self._version_combo.currentText(),
            [installation.installation.version for installation in self._installed],
        )
        self._resolved_label.setText(
            f"→ {resolved}" if resolved is not None else "→ не установлена"
        )

        range_parsed = _parse_range(self._range_edit.text())
        if range_parsed is None:
            # Своя ошибка до validate_profile (бриф, шаг 1): диапазон,
            # не разбирающийся как два числа, не даёт собрать осмысленный
            # черновик — сравнивать/сохранять там пока нечего.
            self._error_label.setText(_RANGE_FORMAT_ERROR)
            self._warning_label.setText("")
            self._ok_button.setEnabled(False)
            return

        draft = self._draft_profile(range_parsed)
        errors = validate_profile(draft, self._existed, normalize=normalize_cluster_dir)
        self._error_label.setText("\n".join(errors))
        self._ok_button.setEnabled(not errors)

        warnings = list(warn_range_overlap(draft, self._existed))
        if self._profile is not None and draft.regport != self._profile.regport:
            # [Ф] А2: реестр кластера живёт в reg_<regport> внутри -d,  # noqa: RUF003
            # смена порта регистрации молча заводит новый пустой реестр
            # рядом со старым. Не блокер — предупреждение, ОК остаётся  # noqa: RUF003
            # активной, если других ошибок нет.
            warnings.append(_REGPORT_CHANGE_WARNING)
        self._warning_label.setText("\n".join(warnings))

    # -- результат -------------------------------------------------------------

    def result_profile(self) -> ServerProfile:
        """Профиль по текущим значениям полей. Зовётся только когда «ОК» активна."""  # noqa: RUF002
        return self._draft_profile()

    # -- доступ для тестов -------------------------------------------------

    def ok_button(self) -> QPushButton:
        return self._ok_button

    def error_text(self) -> str:
        return self._error_label.text()

    def warning_text(self) -> str:
        return self._warning_label.text()

    def resolved_text(self) -> str:
        return self._resolved_label.text()

    def name_edit(self) -> QLineEdit:
        return self._name_edit

    def version_combo(self) -> QComboBox:
        return self._version_combo

    def port_edit(self) -> QLineEdit:
        return self._port_edit

    def regport_edit(self) -> QLineEdit:
        return self._regport_edit

    def range_edit(self) -> QLineEdit:
        return self._range_edit

    def dir_edit(self) -> QLineEdit:
        return self._dir_edit

    def browse_button(self) -> QPushButton:
        return self._browse_button

    def debug_checkbox(self) -> QCheckBox:
        return self._debug_checkbox

    def http_checkbox(self) -> QCheckBox:
        return self._http_checkbox

    def extra_edit(self) -> QLineEdit:
        return self._extra_edit


@dataclass(frozen=True)
class ConsoleVersionRow:
    """Что видно в строке версии диалога консоли — аксессор тестам."""

    version: VersionNumber
    current: bool
    running: bool


class ConsoleDialog(QDialog):
    def __init__(
        self,
        installed: Sequence[ServerInstallation],
        current: VersionNumber | None,
        running_versions: Sequence[VersionNumber],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._installed = list(installed)
        self._current = current
        running = set(running_versions)
        self._rows = [
            ConsoleVersionRow(
                version=si.installation.version,
                current=current is not None and si.installation.version == current,
                running=si.installation.version in running,
            )
            for si in self._installed
        ]

        self.setWindowTitle("Консоль администрирования")

        self._list = QListWidget()
        for si, row in zip(self._installed, self._rows, strict=True):
            badges = [
                label
                for flag, label in ((row.current, "текущая"), (row.running, "работает"))
                if flag
            ]
            text = str(row.version)
            if badges:
                text = f"{text}   ·   {' · '.join(badges)}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, si)
            self._list.addItem(item)

        note = QLabel(
            "Смена версии перерегистрирует radmin.dll — Windows спросит "
            "подтверждение администратора (UAC)"
        )
        note.setWordWrap(True)

        self._register_button = QPushButton("Сделать текущей и открыть")
        self._open_button = QPushButton("Открыть")
        self._open_button.setEnabled(current is not None)
        self._cancel_button = QPushButton("Отмена")
        self._cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._register_button)
        button_row.addWidget(self._open_button)
        button_row.addWidget(self._cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addWidget(note)
        layout.addLayout(button_row)

        self._list.currentItemChanged.connect(self._refresh_register_button)
        current_index = next((i for i, row in enumerate(self._rows) if row.current), None)
        if current_index is not None:
            self._list.setCurrentRow(current_index)
        elif self._rows:
            self._list.setCurrentRow(0)
        self._refresh_register_button()

    @classmethod
    def build(
        cls,
        installed: Sequence[ServerInstallation],
        current: VersionNumber | None,
        running_versions: Sequence[VersionNumber],
        parent: QWidget | None = None,
    ) -> "ConsoleDialog":
        return cls(installed, current, running_versions, parent=parent)

    def _refresh_register_button(self, *_args: object) -> None:
        selected = self.selected_installation()
        is_current = (
            selected is not None
            and self._current is not None
            and selected.installation.version == self._current
        )
        self._register_button.setEnabled(selected is not None and not is_current)

    def selected_installation(self) -> ServerInstallation | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return cast(ServerInstallation, item.data(Qt.ItemDataRole.UserRole))

    def version_rows(self) -> list[ConsoleVersionRow]:
        return list(self._rows)

    def register_button(self) -> QPushButton:
        return self._register_button

    def open_button(self) -> QPushButton:
        return self._open_button

    def cancel_button(self) -> QPushButton:
        return self._cancel_button

    def list_widget(self) -> QListWidget:
        """Список версий — тестам, чтобы менять выбор (`setCurrentRow`)."""
        return self._list
