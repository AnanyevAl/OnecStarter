"""Кнопки диалогов с явными русскими подписями.

Ревью задачи 8 (круг 1) поймало дефект запуском, а не по намерению кода:
`QDialogButtonBox(QDialogButtonBox.StandardButton.Close)` рисует подпись
«Close», не «Закрыть». `QTranslator` в проекте нигде не устанавливается,
поэтому стандартные подписи Qt (`Close`, `Ok`, `Cancel`) приходят
по-английски, а интерфейс — русский (requirements.md, §4). Прецедент подмены
уже был — `ui/errors.py` собирает кнопку «Скопировать» текстом вручную;
здесь этот приём вынесен в одно место, чтобы диалоги задач 9–12 (там
понадобятся «ОК»/«Отмена») звали готовую функцию, а не повторяли ошибку
по одной подписи на диалог.

Роли Qt (`AcceptRole`/`RejectRole`) у кнопки определяют, что произойдёт при
клике: `QDialogButtonBox.accepted()`/`rejected()` эмитятся по роли, а не по
тексту, — поэтому подмена подписи не трогает обвязку сигналов, которую уже
использует остальной код (`buttons.rejected.connect(self.reject)`).

Ролей ровно три — только то, что нужно сегодня (задача 8: «Закрыть») и
в ближайших задачах (9–12: «ОК»/«Отмена»); придумывать про запас незачем.

**Задача 10 добавляет `russian_confirm`.** Подтверждение смены вида
размещения (предупреждение о теряемых ключах) — это Да/Нет-вопрос, а не
Accept/Reject диалог, и `QDialogButtonBox` для него не подходит:
`QMessageBox` сам управляет своими кнопками через `addButton`, готовый
button box в него не вставить. Тот же дефект, что и у `russian_button_box`
(без `QTranslator` стандартные подписи Qt английские), только для
`QMessageBox.StandardButton.Yes`/`.No` вместо `Ok`/`Cancel`/`Close` —
своя функция, а не расширение первой чужим API.

**Круг правок 1 (ревью задачи 10).** Первая версия `russian_confirm` зашивала
`box.exec()` внутрь себя — единственный гейт между пользователем и молчаливой
полной перезаписью `Connect` (`BasesView._apply_properties`, `kind_change_warning`)
оказался у себя же и непроверяемым: три теста, вызывавших `_apply_properties`,
подменяли саму функцию лямбдой, поэтому ни настоящие подписи кнопок, ни чтение
клика (`clickedButton() is yes`) не выполнялись ни разу. Тот же класс дефекта,
что стоил задаче 8 круга правок для «Close»: подпись выведена из кода, а не
из запуска. `build_confirm_box`/`is_confirmed` разносят сборку и показ тем же
приёмом, что и `InfobaseDialog.for_new`/`_build_add_dialog` в этой же задаче —
обе ветки выбора и обе подписи теперь проверяются на настоящем виджете
без блокирующего `exec()`.

**`ask_confirmation` — находка 3 ручного чек-листа T-10 (Minor, 29.08.2026).**
Диалог выхода при работающих серверах (`ui/app.py::_ask_quit_confirmation`)
до этой правки звал `QMessageBox.question` со стандартными кнопками —
без установленного `QTranslator` (см. выше) они пришли по-английски
(«Yes»/«No» на скриншоте живого прогона), хотя весь остальной интерфейс
русский. `ServersView._default_confirm_removal` (T-08) уже решала ровно
ту же задачу — Да/Нет-подтверждение с дефолтной кнопкой «Нет» (страховка
от случайного Enter/пробела на диалоге с дорогими последствиями) — своей
копией той же сборки. `ask_confirmation` выносит этот приём в одно место
(`build_confirm_box` → дефолт «Нет» → `exec()` → `is_confirmed`), и оба
места теперь зовут её вместо собственных копий.
"""  # noqa: RUF002

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from onecstarter.ui.components import DialogFooter, FindingsList, Note, repolish


class ButtonKind(Enum):
    """Кнопка диалога, для которой нужна явная русская подпись."""

    CLOSE = "close"
    OK = "ok"
    CANCEL = "cancel"


_LABELS: dict[ButtonKind, str] = {
    ButtonKind.CLOSE: "Закрыть",
    ButtonKind.OK: "ОК",  # noqa: RUF001
    ButtonKind.CANCEL: "Отмена",
}
_ROLES: dict[ButtonKind, QDialogButtonBox.ButtonRole] = {
    ButtonKind.CLOSE: QDialogButtonBox.ButtonRole.RejectRole,
    ButtonKind.OK: QDialogButtonBox.ButtonRole.AcceptRole,
    ButtonKind.CANCEL: QDialogButtonBox.ButtonRole.RejectRole,
}

PRIMARY: Final = "primary"
DANGER: Final = "danger"
ButtonEmphasis = Literal["primary", "danger"]


def mark_button(button: QPushButton, role: ButtonEmphasis | None) -> None:
    """Жёлтая главная (`primary`) или красная опасная (`danger`) кнопка (решение заказчика 1).

    Свойство, а не `:default`: у кнопок с `autoDefault` статус «по умолчанию» переходит к
    кнопке в фокусе — жёлтой стала бы «…» или «Отмена» (аудит плана Б, раздел 4).
    `None` снимает роль.
    """  # noqa: RUF002
    button.setProperty("role", role)
    repolish(button)


def accept_button(box: QDialogButtonBox) -> QPushButton:
    """Кнопка с ролью `AcceptRole` — «ОК» окна (`russian_button_box` даёт `QPushButton`)."""  # noqa: RUF002
    return cast(
        QPushButton,
        next(
            b
            for b in box.buttons()
            if box.buttonRole(b) == QDialogButtonBox.ButtonRole.AcceptRole
        ),
    )


def russian_button_box(*kinds: ButtonKind) -> QDialogButtonBox:
    """Собрать `QDialogButtonBox` с явными русскими подписями кнопок.

    Порядок кнопок — порядок аргументов. `accepted`/`rejected` работают как
    обычно: подписаться на них можно сразу после вызова, без дополнительной
    возни с ролями отдельных кнопок.

    «ОК» — жёлтая главная кнопка окна (мокап `.btn.pri`, решение заказчика 1) во всех
    диалогах сразу: роль ставится здесь, а не в каждом диалоге, — так «ОК» профиля сервера
    и проекта EDT разошлись со свойствами базы (замечание к 4.0.0, T-45).
    """  # noqa: RUF002
    box = QDialogButtonBox()
    for kind in kinds:
        button = box.addButton(_LABELS[kind], _ROLES[kind])
        if kind is ButtonKind.OK:
            mark_button(button, PRIMARY)
    return box


def accept_on_ctrl_enter(dialog: QDialog, box: QDialogButtonBox) -> None:
    """Ctrl+Enter — «ОК» окна (пожелание пользователей, приёмка 21.11.2026, П1).

    Нажимается сама кнопка: проверки окна срабатывают, неактивная «ОК» — нет.
    """  # noqa: RUF002
    ok = accept_button(box)
    for sequence in ("Ctrl+Return", "Ctrl+Enter"):
        shortcut = QShortcut(QKeySequence(sequence), dialog)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(lambda: ok.click() if ok.isEnabled() else None)


def build_confirm_box(parent: QWidget | None, title: str, text: str) -> QMessageBox:
    """Собрать Да/Нет-`QMessageBox` без показа — для тестов и `russian_confirm`.

    Тот же приём, что и у `InfobaseDialog.for_new`/`_build_add_dialog`
    (задача 10): сборка отдельно от показа, чтобы подписи кнопок и обработка
    клика проверялись без блокирующего `exec()` — см. «Круг правок 1»
    в докстринге модуля.
    """  # noqa: RUF002
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton("Да", QMessageBox.ButtonRole.YesRole)
    box.addButton("Нет", QMessageBox.ButtonRole.NoRole)
    return box


def is_confirmed(box: QMessageBox) -> bool:
    """Ответили ли «Да» — по роли нажатой кнопки. `False`, если ещё не нажата.

    Роль, а не identity кнопки: `build_confirm_box` не отдаёт наружу ссылку
    на саму кнопку «Да» (звать её незачем никому, кроме этой проверки), а
    роль — то же самое сравнение по существу и не требует её хранить.
    """  # noqa: RUF002
    clicked = box.clickedButton()
    return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.YesRole


def russian_confirm(parent: QWidget | None, title: str, text: str) -> bool:
    """Да/Нет-подтверждение с русскими подписями кнопок. `True` — ответили «Да»."""  # noqa: RUF002
    box = build_confirm_box(parent, title, text)
    box.exec()
    return is_confirmed(box)


def ask_confirmation(parent: QWidget | None, title: str, text: str) -> bool:
    """Да/Нет-подтверждение с дефолтной кнопкой «Нет». `True` — ответили «Да».

    Находка 3 ручного чек-листа T-10 (см. докстринг модуля): общий приём
    для диалогов с дорогими последствиями — выход при работающих серверах
    и удаление профиля. Отдельная функция от `russian_confirm` (задача 10)
    намеренно: та дефолтную кнопку не ставит — подмена подписи в её месте
    использования (смена вида размещения) не несёт того же риска
    случайного согласия на Enter/пробел, что выход или удаление профиля.

    `box.buttons()` типизирован в стабах PySide6 как `list[QAbstractButton]`,
    но `setDefaultButton()` принимает только `QPushButton` — фактический
    тип рантайма гарантирован тем, что `build_confirm_box` добавляет
    кнопки только через `addButton(text, role)`.
    """  # noqa: RUF002
    box = build_confirm_box(parent, title, text)
    no_button = cast(
        QPushButton | None, next((b for b in box.buttons() if b.text() == "Нет"), None)
    )
    if no_button is not None:
        box.setDefaultButton(no_button)
    box.exec()
    return is_confirmed(box)


@dataclass(frozen=True)
class Choice:
    """Кнопка `ChoiceDialog`: ключ ответа, подпись, роль, сторона полосы."""

    key: str
    label: str
    role: ButtonEmphasis | None = None
    left: bool = False


class ChoiceDialog(QDialog):
    """Вопрос с явными кнопками в полосе `.foot` (мокап v4, экраны 6 и 7).

    `QMessageBox` раскладывает кнопки по ролям платформы и не умеет выноску (аудит плана Б,
    раздел 4). Кнопка по умолчанию — `default`; у всех снят `autoDefault`: иначе статус «по
    умолчанию» уходит к кнопке в фокусе, и Enter нажал бы её (урок v3.2). Esc и закрытие
    окна — ответ `escape`.
    """  # noqa: RUF002

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        text: str,
        choices: Sequence[Choice],
        default: str,
        escape: str,
        note: Note | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._escape = escape
        self._chosen: str | None = None
        self._text = QLabel(text)
        # В тексте бывает имя сценария от пользователя: только PlainText (GC).  # noqa: RUF003
        self._text.setTextFormat(Qt.TextFormat.PlainText)
        self._text.setWordWrap(True)
        self._notes = FindingsList()
        if note is not None:
            self._notes.set_notes([note])
        footer = DialogFooter()
        self._buttons: dict[str, QPushButton] = {}
        for choice in choices:
            button = QPushButton(choice.label)
            button.setAutoDefault(False)
            mark_button(button, choice.role)
            button.clicked.connect(lambda _checked=False, key=choice.key: self._choose(key))
            if choice.left:
                footer.add_left(button)
            else:
                footer.add_right(button)
            self._buttons[choice.key] = button
        self._buttons[default].setDefault(True)
        content = QVBoxLayout()
        content.setContentsMargins(16, 16, 16, 12)
        content.addWidget(self._text)
        content.addWidget(self._notes)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(content)
        layout.addWidget(footer)
        self._buttons[default].setFocus()

    def text(self) -> str:
        return self._text.text()

    def text_label(self) -> QLabel:
        return self._text

    def chosen(self) -> str | None:
        return self._chosen

    def button(self, key: str) -> QPushButton:
        return self._buttons[key]

    def note_list(self) -> FindingsList:
        return self._notes

    def _choose(self, key: str) -> None:
        self._chosen = key
        self.accept()

    def reject(self) -> None:
        if self._chosen is None:
            self._chosen = self._escape
        super().reject()
