"""Блок «Хранилище конфигурации» диалога свойств базы (спека v4, §7.1).

Адрес и пользователь — наши данные (`bases.json`), пароль — диспетчер учётных данных
Windows. Сам пароль в блок не приходит: только признак «сохранён» (как у пароля базы).
"""  # noqa: RUF002

from dataclasses import dataclass, field

from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QWidget

from onecstarter.services.workspace import RepositorySettings
from onecstarter.ui.components import align_form
from onecstarter.ui.settings_group import CollapsibleGroup
from onecstarter.ui.theme import DARK, Palette

BLOCK_ID = "repository"
BLOCK_TITLE = "Хранилище конфигурации"
STORED_PLACEHOLDER = "сохранён"
NOTE = (
    "Нужно командам хранилища в сценариях. Пароль хранится в диспетчере учётных данных "
    "Windows и передаётся Конфигуратору в командной строке."
)
UNAVAILABLE_NOTE = "Диспетчер учётных данных Windows недоступен — пароль изменить нельзя."
DROP_NOTE = "Сохранённый пароль хранилища будет удалён"


@dataclass(frozen=True)
class DialogRepository:
    """Что ввёл пользователь. `password is None` — поле пустое, сохранённый не трогать."""

    address: str | None
    user: str | None
    password: str | None = field(default=None, repr=False, compare=False)
    remember: bool = False


def _clean(text: str | None) -> str | None:
    return (text or "").strip() or None


def repository_title(address: str | None, user: str | None) -> str:
    parts = [part for part in (_clean(address), _clean(user)) if part is not None]
    return f"{BLOCK_TITLE} — {' · '.join(parts) if parts else 'нет'}"


class RepositoryBlock(CollapsibleGroup):
    def __init__(
        self,
        settings: RepositorySettings,
        *,
        expanded: bool = False,
        palette: Palette = DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            BLOCK_TITLE,
            accent=False,
            rule=False,
            summary=True,
            rule_above=True,
            object_name="RepositoryTitle",
            parent=parent,
        )
        self._initial = settings
        self._locked = settings.has_password is None
        self._dropping = False
        self._was_remember = bool(settings.has_password)
        self._address = QLineEdit(settings.address or "")
        self._user = QLineEdit(settings.user or "")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        if settings.has_password:
            self._password.setPlaceholderText(STORED_PLACEHOLDER)
        self._remember = QCheckBox("запомнить")
        self._remember.setObjectName("InlineCheck")
        self._remember.setChecked(bool(settings.has_password))
        if self._locked:
            self._password.setEnabled(False)
            self._remember.setEnabled(False)
        note = QLabel(UNAVAILABLE_NOTE if self._locked else NOTE)
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)
        self._drop_note = QLabel(DROP_NOTE)
        self._drop_note.setObjectName("SettingsNote")
        self._drop_note.setWordWrap(True)
        self._drop_note.setVisible(False)
        # Мокап, экран 1 (стр. 144): «запомнить» — в строке пароля, серым (`#InlineCheck`).
        password_row = QWidget()
        password_layout = QHBoxLayout(password_row)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.addWidget(self._password, 1)
        password_layout.addWidget(self._remember)
        form = QFormLayout()
        form.addRow("Адрес", self._address)
        form.addRow("Пользователь", self._user)
        form.addRow("", self._drop_note)
        form.addRow("Пароль", password_row)
        form.addRow("", note)
        align_form(form)
        self.body_layout().addLayout(form)
        self._address.textChanged.connect(self._refresh_title)
        self._user.textChanged.connect(self._refresh_title)
        self._user.textChanged.connect(self._on_user_changed)
        self._password.textChanged.connect(self._autocheck_remember)
        self.set_palette(palette)
        self.set_expanded(expanded)
        self._refresh_title()

    def address_edit(self) -> QLineEdit:
        return self._address

    def user_edit(self) -> QLineEdit:
        return self._user

    def password_edit(self) -> QLineEdit:
        return self._password

    def remember_checkbox(self) -> QCheckBox:
        return self._remember

    def values(self) -> DialogRepository:
        # Диспетчер недоступен: флажок заперт снятым, но это не просьба удалить пароль.
        remember = True if self._locked else self._remember.isChecked()
        return DialogRepository(
            _clean(self._address.text()),
            _clean(self._user.text()),
            self._password.text() or None,
            remember,
        )

    def changed(self) -> bool:
        values = self.values()
        if values.address != _clean(self._initial.address):
            return True
        if values.user != _clean(self._initial.user):
            return True
        if self._locked:
            return False
        return values.password is not None or values.remember != bool(self._initial.has_password)

    def drop_note_visible(self) -> bool:
        return not self._drop_note.isHidden()

    def _on_user_changed(self, text: str) -> None:
        """Приёмка 21.11.2026, Р3: без пользователя сохранённый пароль удаляется
        (`Workspace.set_repository`) — сказать об этом до «ОК» и снять «запомнить»."""  # noqa: RUF002
        if self._locked or not self._initial.has_password:
            return
        dropping = not text.strip()
        if dropping == self._dropping:
            return  # действуем только на переходе через пустого пользователя
        self._dropping = dropping
        self._drop_note.setVisible(dropping)
        if dropping:
            self._was_remember = self._remember.isChecked()
            self._remember.setChecked(False)
        else:
            # Пароль, набранный при пустом пользователе, — просьба запомнить:
            # иначе новый пароль молча не сохранится (финальное ревью, M2).
            self._remember.setChecked(self._was_remember or bool(self._password.text()))

    def _autocheck_remember(self, text: str) -> None:
        if text and not self._locked:
            self._remember.setChecked(True)

    def _refresh_title(self) -> None:
        self.set_title(repository_title(self._address.text(), self._user.text()))
