"""Кнопки диалогов с явными русскими подписями (ревью задачи 8, круг 1).

Стандартные `QDialogButtonBox.StandardButton` без установленного
`QTranslator` приходят по-английски (`Close`, `OK`, `Cancel`) — проверено
запуском в этом окружении. Помощник подменяет подпись явным текстом
и одновременно проверяет, что подмена не портит стандартную обвязку
сигналов `accepted`/`rejected`, на которую опираются диалоги.
"""  # noqa: RUF002

from typing import Any

from onecstarter.ui.dialogs.buttons import (
    ButtonKind,
    build_confirm_box,
    is_confirmed,
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
