"""Кнопки диалогов с явными русскими подписями (ревью задачи 8, круг 1).

Стандартные `QDialogButtonBox.StandardButton` без установленного
`QTranslator` приходят по-английски (`Close`, `OK`, `Cancel`) — проверено
запуском в этом окружении. Помощник подменяет подпись явным текстом
и одновременно проверяет, что подмена не портит стандартную обвязку
сигналов `accepted`/`rejected`, на которую опираются диалоги.
"""  # noqa: RUF002

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QPushButton, QVBoxLayout

from onecstarter.domain.cli_params import Level
from onecstarter.ui.components import Note
from onecstarter.ui.dialogs.buttons import (
    DANGER,
    PRIMARY,
    ButtonKind,
    Choice,
    ChoiceDialog,
    accept_button,
    accept_on_ctrl_enter,
    ask_confirmation,
    build_confirm_box,
    is_confirmed,
    mark_button,
    russian_button_box,
)


def test_close_button_has_russian_label(qtbot: Any) -> None:
    box = russian_button_box(ButtonKind.CLOSE)
    qtbot.addWidget(box)
    assert [button.text() for button in box.buttons()] == ["Закрыть"]


def test_ok_cancel_buttons_have_russian_labels(qtbot: Any) -> None:
    box = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
    qtbot.addWidget(box)
    assert [button.text() for button in box.buttons()] == ["ОК", "Отмена"]  # noqa: RUF001


def test_close_button_click_emits_rejected(qtbot: Any) -> None:
    """Подмена текста не должна ломать штатный сигнал rejected() по роли кнопки."""
    box = russian_button_box(ButtonKind.CLOSE)
    qtbot.addWidget(box)
    signals: list[str] = []
    box.rejected.connect(lambda: signals.append("rejected"))
    box.buttons()[0].click()
    assert signals == ["rejected"]


def test_ok_button_click_emits_accepted_not_rejected(qtbot: Any) -> None:
    box = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
    qtbot.addWidget(box)
    signals: list[str] = []
    box.accepted.connect(lambda: signals.append("accepted"))
    box.rejected.connect(lambda: signals.append("rejected"))
    box.buttons()[0].click()
    assert signals == ["accepted"]


# -- russian_confirm (задача 10, круг правок 1 ревью) ---------------------------
#
# Три теста ниже, подменявшие `russian_confirm` лямбдой (см. test_bases_view.py),
# проверяют только то, что `_apply_properties` честно вызывает функцию и уважает
# её результат, — саму функцию, включая настоящую подпись кнопок и чтение клика
# (`box.clickedButton() is yes`), они не выполняют ни разу. Тот же класс дефекта,
# что стоил задаче 8 круга правок для «Close»: подпись выведена из кода, а не  # noqa: RUF003
# из запуска, только ставка выше — этот гейт стоит между пользователем и молчаливой
# полной перезаписью Connect. build_confirm_box/is_confirmed — сборка отдельно
# от показа (тот же приём, что и у InfobaseDialog.for_new), поэтому обе ветки  # noqa: RUF003
# выбора и обе подписи проверяются на настоящем виджете без блокирующего exec().  # noqa: RUF003


def test_confirm_box_has_russian_yes_no_labels(qtbot: Any) -> None:
    box = build_confirm_box(None, "Заголовок", "Текст")
    qtbot.addWidget(box)
    assert [button.text() for button in box.buttons()] == ["Да", "Нет"]


def test_is_confirmed_false_before_any_click(qtbot: Any) -> None:
    """Нажатой кнопки ещё нет — `clickedButton()` даёт `None`, не «Да»."""
    box = build_confirm_box(None, "Заголовок", "Текст")
    qtbot.addWidget(box)
    assert is_confirmed(box) is False


def test_is_confirmed_true_when_yes_is_clicked(qtbot: Any) -> None:
    box = build_confirm_box(None, "Заголовок", "Текст")
    qtbot.addWidget(box)
    yes_button = next(b for b in box.buttons() if b.text() == "Да")
    yes_button.click()
    assert is_confirmed(box) is True


def test_is_confirmed_false_when_no_is_clicked(qtbot: Any) -> None:
    box = build_confirm_box(None, "Заголовок", "Текст")
    qtbot.addWidget(box)
    no_button = next(b for b in box.buttons() if b.text() == "Нет")
    no_button.click()
    assert is_confirmed(box) is False


# -- ask_confirmation (T-10, чек-лист, находка 3) --------------------------------
#
# Общий приём для диалогов выхода (`ui/app.py::_ask_quit_confirmation`) и
# удаления профиля (`ui/servers/view.py::ServersView._default_confirm_removal`):
# `build_confirm_box` + дефолтная кнопка «Нет» + `exec()` + `is_confirmed`.
# Раньше каждое место держало собственную копию этой сборки — здесь она
# проверяется один раз на настоящем виджете.


def test_ask_confirmation_sets_no_as_default_button(qtbot: Any, monkeypatch: Any) -> None:
    """Дефолтная кнопка — «Нет»: диалог с дорогими последствиями (остановка
    работающих серверов, удаление профиля) не должен поддаваться случайному
    Enter/пробелу. `exec()` подменён, чтобы не блокировать тест реальным
    показом — сама подмена лишь читает `defaultButton()`, не кликает.
    """  # noqa: RUF002
    captured: dict[str, Any] = {}

    def fake_exec(self: QMessageBox) -> int:
        captured["default_text"] = self.defaultButton().text()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    ask_confirmation(None, "Заголовок", "Текст")

    assert captured["default_text"] == "Нет"


def test_ask_confirmation_returns_false_when_default_button_is_activated(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Подмена `exec()` кликом по дефолтной кнопке (эмуляция Enter/пробела
    на диалоге под offscreen-платформой, где сам `exec()` не показывается)
    обязана дать `False` — тот же исход, что явный клик «Нет».

    Мутация: убрать `setDefaultButton`/вернуть `False` безусловно — тест
    отличит подмену только вместе с тестом выше (тот проверяет САМ факт
    установки дефолтной кнопки).
    """  # noqa: RUF002

    def fake_exec(self: QMessageBox) -> int:
        default = self.defaultButton()
        assert default is not None
        default.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    result = ask_confirmation(None, "Заголовок", "Текст")

    assert result is False


def test_ask_confirmation_returns_true_when_yes_is_activated(
    qtbot: Any, monkeypatch: Any
) -> None:
    def fake_exec(self: QMessageBox) -> int:
        yes_button = next(b for b in self.buttons() if b.text() == "Да")
        yes_button.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    result = ask_confirmation(None, "Заголовок", "Текст")

    assert result is True



def _press_ctrl_enter(dialog: QDialog) -> None:
    """Сочетание Ctrl+Enter: на offscreen `keyClick` не доходит до `QShortcut`,
    поэтому проверяем подключение обоих ключей и испускаем `activated`."""
    shortcuts = {s.key().toString(): s for s in dialog.findChildren(QShortcut)}
    assert {"Ctrl+Return", "Ctrl+Enter"} <= shortcuts.keys()
    shortcuts["Ctrl+Return"].activated.emit()


def test_ctrl_enter_clicks_ok_only_when_it_is_enabled(qtbot: Any) -> None:
    """П1: сочетание нажимает кнопку «ОК», а неактивная «ОК» не срабатывает."""  # noqa: RUF002
    dialog = QDialog()
    qtbot.addWidget(dialog)
    box = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
    box.accepted.connect(dialog.accept)
    QVBoxLayout(dialog).addWidget(box)
    accept_on_ctrl_enter(dialog, box)
    ok = next(
        b for b in box.buttons() if box.buttonRole(b) == QDialogButtonBox.ButtonRole.AcceptRole
    )
    dialog.show()
    dialog.activateWindow()
    qtbot.waitExposed(dialog)
    ok.setEnabled(False)
    _press_ctrl_enter(dialog)
    assert dialog.result() == QDialog.DialogCode.Rejected and dialog.isVisible()
    ok.setEnabled(True)
    _press_ctrl_enter(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_mark_button_sets_and_clears_the_role(qtbot: Any) -> None:
    """Решение заказчика 1: жёлтая главная и красная опасная — по свойству `role`."""
    button = QPushButton("ОК")  # noqa: RUF001
    qtbot.addWidget(button)
    mark_button(button, PRIMARY)
    assert button.property("role") == "primary"
    mark_button(button, DANGER)
    assert button.property("role") == "danger"
    mark_button(button, None)
    assert button.property("role") is None


def test_accept_button_is_the_ok_of_the_box(qtbot: Any) -> None:
    box = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
    qtbot.addWidget(box)
    assert accept_button(box).text() == "ОК"  # noqa: RUF001


def test_mark_button_repolishes_so_the_role_rule_applies(qtbot: Any) -> None:
    """Без `repolish` правило `[role=...]` не подхватывается уже показанной кнопкой.

    Наблюдаемое — `qproperty-flat`: QSS выставляет его только при (пере)полировке.
    """  # noqa: RUF002
    button = QPushButton("ОК")  # noqa: RUF001
    button.setStyleSheet('QPushButton[role="primary"] { qproperty-flat: true; }')
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    assert not button.isFlat()
    mark_button(button, PRIMARY)
    assert button.isFlat()


def _choice_dialog(qtbot: Any) -> ChoiceDialog:
    dialog = ChoiceDialog(
        None,
        title="Выполняется сценарий",
        text="Сценарий ещё идёт.",
        choices=[
            Choice("stay", "Не выходить", left=True),  # noqa: RUF001
            Choice("wait", "Дождаться шага и выйти", PRIMARY),
            Choice("abort", "Прервать и выйти", DANGER),
        ],
        default="wait",
        escape="stay",
        note=Note(Level.WARNING, "База может остаться испорченной."),
    )
    qtbot.addWidget(dialog)
    return dialog


def test_choice_dialog_lays_out_buttons_by_side_and_role(qtbot: Any) -> None:
    """Мокап, экран 7: «Не выходить» слева, справа главная и опасная."""  # noqa: RUF002
    dialog = _choice_dialog(qtbot)
    dialog.resize(600, 200)
    dialog.show()
    qtbot.waitExposed(dialog)
    stay, wait, abort = (dialog.button(key) for key in ("stay", "wait", "abort"))
    assert stay.x() < wait.x() < abort.x()
    assert (wait.property("role"), abort.property("role"), stay.property("role")) == (
        "primary",
        "danger",
        None,
    )
    assert wait.isDefault() and not stay.autoDefault() and not abort.autoDefault()
    assert dialog.note_list().levels() == ["warning"]
    assert dialog.text() == "Сценарий ещё идёт."
    # Имя сценария в тексте — от пользователя: разметкой оно стать не должно (GC).
    assert dialog.text_label().textFormat() == Qt.TextFormat.PlainText


def test_enter_presses_the_default_and_escape_answers_escape(qtbot: Any) -> None:
    """Страховка от случайного Enter: он нажимает кнопку по умолчанию, а не кнопку в фокусе."""  # noqa: RUF002
    dialog = _choice_dialog(qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.button("abort").setFocus()
    # Финальное ревью плана Б, F5: клавиша — в сфокусированную опасную кнопку, не в окно:
    # иначе регрессия `autoDefault` (Enter нажимает кнопку в фокусе) осталась бы зелёной.
    qtbot.keyClick(dialog.button("abort"), Qt.Key.Key_Return)
    assert dialog.chosen() == "wait"
    second = _choice_dialog(qtbot)
    second.show()
    qtbot.waitExposed(second)
    qtbot.keyClick(second, Qt.Key.Key_Escape)
    assert second.chosen() == "stay"


def test_click_answers_its_key(qtbot: Any) -> None:
    dialog = _choice_dialog(qtbot)
    assert dialog.chosen() is None
    dialog.button("abort").click()
    assert dialog.chosen() == "abort"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_left_flag_wins_over_the_order_of_choices(qtbot: Any) -> None:
    """Сторона задаётся `left`, а не порядком в списке: левая кнопка последней в списке."""  # noqa: RUF002
    dialog = ChoiceDialog(
        None,
        title="Вопрос",
        text="Текст",
        choices=[
            Choice("yes", "Да", PRIMARY),
            Choice("no", "Нет", left=True),
        ],
        default="yes",
        escape="no",
    )
    qtbot.addWidget(dialog)
    dialog.resize(500, 150)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.button("no").x() < dialog.button("yes").x()
    assert not dialog.note_list().isVisible()


def test_ok_of_the_button_box_is_the_primary_button(qtbot: Any) -> None:
    """Замечание к 4.0.0 (T-45): «ОК» жёлтая во всех диалогах, как в свойствах базы.

    Роль ставит сама `russian_button_box` — диалог не может её забыть. «Отмена»
    и «Закрыть» — без роли.
    """  # noqa: RUF002
    box = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
    qtbot.addWidget(box)
    roles = {b.text(): b.property("role") for b in box.buttons()}
    assert roles == {"ОК": PRIMARY, "Отмена": None}  # noqa: RUF001
    close = russian_button_box(ButtonKind.CLOSE)
    qtbot.addWidget(close)
    assert [b.property("role") for b in close.buttons()] == [None]
