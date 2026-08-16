"""Подтверждение удаления записи (задача 11).

`removal_question` — единственная точка штатного стартера, где легко
ошибиться: удаляется запись списка, а файлы базы на диске остаются
нетронутыми. Молчание об этом здесь дороже лишней строки текста, поэтому
текст — чистая функция под табличным тестом (обязательство к тексту,
а не к виджету).

`build_removal_confirm_box`/`confirm_removal` переиспользуют
`build_confirm_box`/`is_confirmed` из buttons.py (задача 10) — те же
русские подписи «Да»/«Нет» и то же разделение сборки и показа, чтобы
кнопка по умолчанию проверялась на настоящем виджете, а не через
монки-патч (см. buttons.py, «Круг правок 1»).
"""  # noqa: RUF002

from typing import Any

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui.dialogs.confirm import (
    build_group_removal_box,
    build_removal_confirm_box,
    group_removal_question,
    read_group_removal,
    removal_question,
)


def _item(name: str) -> InfobaseItem:
    return InfobaseItem(
        key="id:x", name=name, folder="/", is_group=False, connect='File="C:\\base";',
        kind=ConnectKind.FILE, requested_version=None, section_default_version=None,
        app=None, source=InfobaseSource.USER, order=None, section_id="x",
    )


def test_removal_question_says_files_are_untouched() -> None:
    """Пользователь обязан понимать: удаляется запись, а не база.

    В штатном стартере это единственная точка, где легко ошибиться,
    и молчание здесь дороже лишней строки.
    """  # noqa: RUF002
    text = removal_question(_item("Бухгалтерия"))
    assert "Бухгалтерия" in text
    assert "файлы базы не удаляются" in text.casefold()


def test_removal_confirm_box_has_russian_yes_no_labels(qtbot: Any) -> None:
    box = build_removal_confirm_box(None, _item("Бухгалтерия"))
    qtbot.addWidget(box)
    assert [button.text() for button in box.buttons()] == ["Да", "Нет"]


def test_removal_confirm_box_default_button_is_no(qtbot: Any) -> None:
    """Случайный Enter не должен удалить запись — кнопка по умолчанию «Нет»."""
    box = build_removal_confirm_box(None, _item("Бухгалтерия"))
    qtbot.addWidget(box)
    no_button = next(button for button in box.buttons() if button.text() == "Нет")
    assert box.defaultButton() is no_button


# -- Задача 12: удаление группы — текст перечисляет содержимое -------------
#
# Обязательство 3 блока Б: штатный стартер на удаление группы задаёт один
# и тот же вопрос «Удалить группу "имя"?» и для пустой, и для непустой
# группы, каскадно удаляя всё поддерево ([Ф] T-05.9, эксперимент 05.08.2026).
# Быть не хуже недостаточно — текст обязан назвать, что пропадёт.


def test_group_removal_question_lists_contents() -> None:
    text = group_removal_question("Клиенты", ["Альфа", "Бета"], 2, 0)
    assert "Альфа" in text and "Бета" in text


def test_group_removal_question_falls_back_to_counts() -> None:
    text = group_removal_question("Клиенты", [], 12, 3)
    assert "12" in text and "3" in text


def test_empty_group_question_says_it_is_empty() -> None:
    assert "пуста" in group_removal_question("Клиенты", [], 0, 0).casefold()


def test_group_removal_box_shows_the_question_text(qtbot: Any) -> None:
    """Круг правок 1, замечание 1: `group_removal_question` была защищена,

    но единственный путь её результата к пользователю (`box.setText(...)`)
    не проверялся ничем — подмена строки на голый вопрос («буквальное
    повторение платформы», мутация (а) этажом выше) оставила бы зелёными
    все тесты про кнопки и кнопку по умолчанию. `box.text()` читается
    офскрин без показа — это не тот разрыв exec(), что принят для клика.
    """  # noqa: RUF002
    box = build_group_removal_box(None, "Клиенты", ["Альфа"], 1, 0)
    qtbot.addWidget(box)
    assert "Альфа" in box.text()


def test_group_removal_box_text_falls_back_to_counts(qtbot: Any) -> None:
    box = build_group_removal_box(None, "Клиенты", [], 12, 3)
    qtbot.addWidget(box)
    assert "12" in box.text()
    assert "3" in box.text()


def test_group_removal_box_has_three_russian_labels(qtbot: Any) -> None:
    # Множество, не список: QMessageBox переупорядочивает кнопки по роли под
    # платформенные соглашения (на этой машине — RejectRole первой), порядок
    # добавления `addButton` он не сохраняет.
    box = build_group_removal_box(None, "Клиенты", ["Альфа"], 1, 0)
    qtbot.addWidget(box)
    assert {button.text() for button in box.buttons()} == {
        "Удалить с содержимым",  # noqa: RUF001
        "Поднять к родителю",
        "Отмена",
    }


def test_group_removal_box_default_button_is_cancel(qtbot: Any) -> None:
    """Случайный Enter не должен запустить каскадное удаление содержимого."""
    box = build_group_removal_box(None, "Клиенты", [], 0, 0)
    qtbot.addWidget(box)
    cancel_button = next(button for button in box.buttons() if button.text() == "Отмена")
    assert box.defaultButton() is cancel_button


def test_read_group_removal_before_any_click_is_none(qtbot: Any) -> None:
    box = build_group_removal_box(None, "Клиенты", [], 0, 0)
    qtbot.addWidget(box)
    assert read_group_removal(box) is None


def test_read_group_removal_recursive_click(qtbot: Any) -> None:
    box = build_group_removal_box(None, "Клиенты", ["Альфа"], 1, 0)
    qtbot.addWidget(box)
    button = next(b for b in box.buttons() if b.text() == "Удалить с содержимым")  # noqa: RUF001
    button.click()
    assert read_group_removal(box) is GroupRemoval.RECURSIVE


def test_read_group_removal_promote_click(qtbot: Any) -> None:
    box = build_group_removal_box(None, "Клиенты", ["Альфа"], 1, 0)
    qtbot.addWidget(box)
    button = next(b for b in box.buttons() if b.text() == "Поднять к родителю")
    button.click()
    assert read_group_removal(box) is GroupRemoval.PROMOTE


def test_read_group_removal_cancel_click_is_none(qtbot: Any) -> None:
    box = build_group_removal_box(None, "Клиенты", ["Альфа"], 1, 0)
    qtbot.addWidget(box)
    button = next(b for b in box.buttons() if b.text() == "Отмена")
    button.click()
    assert read_group_removal(box) is None
