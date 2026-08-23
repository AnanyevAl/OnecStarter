"""Подтверждение удаления записи списка (задача 11) и группы (задача 12).

В штатном стартере это единственное место, где легко ошибиться: удаляется
**запись списка**, а файлы базы на диске остаются нетронутыми. Молчание
об этом здесь дороже лишней строки текста, поэтому `removal_question` —
чистая функция под табличным тестом: обязательство к тексту, а не к
виджету (тот же приём, что и у docstring buttons.py — «Круг правок 1»).

`build_removal_confirm_box`/`confirm_removal` переиспользуют
`build_confirm_box`/`is_confirmed` из buttons.py (задача 10), а не
собирают `QMessageBox` заново: те же русские подписи «Да»/«Нет» (без
`QTranslator` стандартные `QMessageBox.StandardButton.Yes`/`.No` пришли бы
по-английски — тот же дефект, который стоил задаче 8 круга правок для
«Close») и то же разделение сборки и показа — состав кнопок и кнопка
по умолчанию проверяются на настоящем виджете без блокирующего `exec()`.

Кнопка по умолчанию — «Нет»: случайный Enter не должен удалить запись.
`build_confirm_box` сама её не назначает (никто из вызывавших её в задаче 10
об этом не просил — там подтверждение открывалось только по клику на пункт
меню, без риска случайного Enter сразу после открытия), поэтому дефолт
назначается здесь, для этого конкретного диалога.

**Задача 12 — удаление группы.** Здесь ставки выше, чем у удаления записи:
удаление каскадное, и по одному подтверждению может исчезнуть целое
поддерево записей пользователя. Обязательство 3 блока Б: [Ф] T-05.9
(эксперимент 05.08.2026) — штатный стартер на удаление группы задаёт один
и тот же вопрос «Удалить группу "имя"?» и для пустой, и для непустой
группы, не называя содержимое, и по «Да» молча каскадит. Быть не хуже
недостаточно — `group_removal_question` обязана перечислить содержимое
(или его количество, `services.display.group_contents`), а сам выбор —
не Да/Нет, а один из трёх исходов (удалить с содержимым / поднять
к родителю / отмена), поэтому `is_confirmed`/`build_confirm_box` сюда не
подходят: тем нужна ровно пара кнопок с зашитыми ролями Yes/No.
`build_group_removal_box`/`read_group_removal`/`ask_group_removal` — тот же
приём «build → exec → read», реализованный отдельно под три исхода вместо
двух.
"""  # noqa: RUF002

from collections.abc import Sequence
from typing import cast

from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from onecstarter.services.groups import GroupRemoval
from onecstarter.services.model import InfobaseItem
from onecstarter.ui.dialogs.buttons import build_confirm_box, is_confirmed


def removal_question(item: InfobaseItem) -> str:
    """Текст вопроса на удаление — чистая функция, без Qt."""
    return (
        f"Удалить «{item.name}» из списка баз?\n\n"
        "Удаляется только запись списка — файлы базы не удаляются "
        "и не изменяются."
    )


def build_removal_confirm_box(parent: QWidget | None, item: InfobaseItem) -> QMessageBox:
    """Собрать диалог подтверждения удаления без показа — для тестов и confirm_removal.

    Тот же приём, что у `_build_menu`/`_build_properties_dialog` в
    `BasesView` (задачи 8, 10): сборка отдельно от показа, чтобы состав
    кнопок и кнопка по умолчанию проверялись без блокирующего `exec()`.
    """  # noqa: RUF002
    box = build_confirm_box(parent, "OneCStarter", removal_question(item))
    # box.buttons() типизирован как list[QAbstractButton] в стабах PySide6,
    # но setDefaultButton() принимает только QPushButton. Фактический тип
    # рантайма — QPushButton: build_confirm_box добавляет кнопки только
    # через QMessageBox.addButton(text, role), которая всегда создаёт
    # и возвращает QPushButton.
    no_button = cast(
        QPushButton, next(button for button in box.buttons() if button.text() == "Нет")
    )
    box.setDefaultButton(no_button)
    return box


def confirm_removal(parent: QWidget | None, item: InfobaseItem) -> bool:
    """Спросить подтверждение удаления. `True` — пользователь ответил «Да»."""
    box = build_removal_confirm_box(parent, item)
    box.exec()
    return is_confirmed(box)


# -- Задача 12: удаление группы ---------------------------------------------

_RECURSIVE_LABEL = "Удалить с содержимым"  # noqa: RUF001
_PROMOTE_LABEL = "Поднять к родителю"
_CANCEL_LABEL = "Отмена"


def group_removal_question(
    label: str, names: Sequence[str], bases: int, groups: int
) -> str:
    """Текст вопроса на удаление группы — перечисляет содержимое, не молчит о нём.

    Обязательство 3 блока Б: [Ф] T-05.9 — штатный стартер задаёт один
    и тот же вопрос «Удалить группу "имя"?» и для пустой, и для непустой
    группы и после «Да» молча каскадит всё поддерево. Быть не хуже
    недостаточно — текст обязан назвать, что именно пропадёт: до 10
    элементов (`names`, уже посчитаны по всему поддереву в
    `display.group_contents`, а не только по прямым детям) — именами,
    больше — числом записей и вложенных групп.
    """  # noqa: RUF002
    head = f"Удалить группу «{label}»?"
    if not bases and not groups:
        return f"{head}\n\nГруппа пуста."  # noqa: RUF001
    if names:
        listed = "\n".join(f"  • {name}" for name in names)
        body = f"В группе и её подгруппах:\n{listed}"  # noqa: RUF001
    else:
        body = (
            f"В группе и её подгруппах: записей — {bases}, "  # noqa: RUF001
            f"вложенных групп — {groups}."
        )
    return (
        f"{head}\n\n{body}\n\n"
        "Выберите, что сделать с содержимым. Файлы баз не удаляются "  # noqa: RUF001
        "и не изменяются."
    )


def build_group_removal_box(
    parent: QWidget | None, label: str, names: Sequence[str], bases: int, groups: int
) -> QMessageBox:
    """Собрать диалог решения об удалении группы без показа — три исхода, не два.

    `build_confirm_box` (buttons.py) сюда не подходит: он всегда рисует ровно
    две кнопки с зашитыми подписями «Да»/«Нет» под роли Yes/No — здесь нужны
    три кнопки с другими подписями и без этой пары ролей («Удалить
    с содержимым» — `GroupRemoval.RECURSIVE`, «Поднять к родителю» —
    `GroupRemoval.PROMOTE`, «Отмена» — отказ). Раздвигать сигнатуру
    `build_confirm_box` параметрами ради единственного вызывающего значило
    бы тащить в общий билдер частность одного диалога — вместо этого сборка
    вынесена в отдельную функцию, тем же приёмом «отделить от показа», что
    и `build_removal_confirm_box`/`build_confirm_box`: состав кнопок и
    кнопка по умолчанию проверяются на настоящем виджете без блокирующего
    `exec()`.

    Кнопка по умолчанию — «Отмена»: случайный Enter не должен запустить
    каскадное удаление содержимого.
    """  # noqa: RUF002
    box = QMessageBox(parent)
    box.setWindowTitle("OneCStarter")
    box.setText(group_removal_question(label, names, bases, groups))
    box.addButton(_RECURSIVE_LABEL, QMessageBox.ButtonRole.DestructiveRole)
    box.addButton(_PROMOTE_LABEL, QMessageBox.ButtonRole.ActionRole)
    cancel_button = box.addButton(_CANCEL_LABEL, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    return box


def read_group_removal(box: QMessageBox) -> GroupRemoval | None:
    """Что выбрал пользователь по роли нажатой кнопки. `None` — отмена или ещё не нажата.

    Роль, а не текст кнопки — тот же приём, что и у `is_confirmed`
    (buttons.py): не требует хранить ссылку на саму кнопку и не путает
    подпись с языком интерфейса.
    """  # noqa: RUF002
    clicked = box.clickedButton()
    if clicked is None:
        return None
    role = box.buttonRole(clicked)
    if role == QMessageBox.ButtonRole.DestructiveRole:
        return GroupRemoval.RECURSIVE
    if role == QMessageBox.ButtonRole.ActionRole:
        return GroupRemoval.PROMOTE
    return None


def ask_group_removal(
    parent: QWidget | None, label: str, names: Sequence[str], bases: int, groups: int
) -> GroupRemoval | None:
    """Спросить решение по удалению группы. `None` — пользователь отказался."""
    box = build_group_removal_box(parent, label, names, bases, groups)
    box.exec()
    return read_group_removal(box)


# -- Веха «Завершение v1»: очистка кэша --------------------------------------  # noqa: RUF003


def build_cache_confirm_box(parent: QWidget | None, question: str) -> QMessageBox:
    """Собрать подтверждение очистки кэша без показа — для тестов и confirm_cache_clear.

    Текст вопроса готовит `services/cache.py::clear_question` — с именем базы
    и размером, посчитанным до удаления (спека §3.5). Кнопка по умолчанию —
    «Нет»: очистка необратима, случайный Enter не должен её запустить
    (тот же довод, что у удаления записи).
    """  # noqa: RUF002
    box = build_confirm_box(parent, "OneCStarter", question)
    no_button = cast(
        QPushButton, next(button for button in box.buttons() if button.text() == "Нет")
    )
    box.setDefaultButton(no_button)
    return box


def confirm_cache_clear(parent: QWidget | None, question: str) -> bool:
    """Спросить подтверждение очистки кэша. `True` — ответили «Да»."""
    box = build_cache_confirm_box(parent, question)
    box.exec()
    return is_confirmed(box)
