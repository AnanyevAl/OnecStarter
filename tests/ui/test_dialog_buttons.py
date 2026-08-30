"""Кнопки диалогов с явными русскими подписями (ревью задачи 8, круг 1).

Стандартные `QDialogButtonBox.StandardButton` без установленного
`QTranslator` приходят по-английски (`Close`, `OK`, `Cancel`) — проверено
запуском в этом окружении. Помощник подменяет подпись явным текстом
и одновременно проверяет, что подмена не портит стандартную обвязку
сигналов `accepted`/`rejected`, на которую опираются диалоги.
"""  # noqa: RUF002

from typing import Any

from PySide6.QtWidgets import QMessageBox

from onecstarter.ui.dialogs.buttons import (
    ButtonKind,
    ask_confirmation,
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
