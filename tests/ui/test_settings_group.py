"""Сворачиваемая группа настроек: свёртка, шеврон, тело."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from onecstarter.ui.settings_group import CollapsibleGroup, chevron_pixmap
from onecstarter.ui.theme import DARK, LIGHT


# Фикстура объявляется в каждом файле UI-тестов отдельно — общей в
# `tests/ui/conftest.py` нет (проверено по всем файлам каталога).
@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


# [Ф] Замер 02.09.2026, PySide6 6.11.1: `isHidden()` отражает ТОЛЬКО явное
# скрытие самого виджета и не наследуется от предка — у строки внутри  # noqa: RUF003
# скрытого тела группы он остаётся `False`. Проверять видимость внутри
# группы им нельзя: тест прошёл бы всегда и не проверял бы ничего.
# Окно раздела в офскрин-тесте не показано, поэтому `isVisible()` тоже
# не годится — верный предикат `isVisibleTo(<предок>)` (спека §1.6).


def test_group_is_collapsed_on_creation(application: QApplication) -> None:
    """По умолчанию свёрнуто — решение заказчика 02.09.2026 (спека §1.4)."""
    group = CollapsibleGroup("СЕРВЕРЫ")
    body = QLabel("строка")
    group.body_layout().addWidget(body)

    assert group.is_expanded() is False
    assert body.isVisibleTo(group) is False


def test_expanding_shows_the_body_and_collapsing_hides_it(
    application: QApplication,
) -> None:
    group = CollapsibleGroup("СЕРВЕРЫ")
    body = QLabel("строка")
    group.body_layout().addWidget(body)

    group.set_expanded(True)
    assert body.isVisibleTo(group) is True

    group.set_expanded(False)
    assert body.isVisibleTo(group) is False


def test_toggled_signal_reports_the_new_state(application: QApplication) -> None:
    group = CollapsibleGroup("СЕРВЕРЫ")
    seen: list[bool] = []
    group.toggled.connect(seen.append)

    group.set_expanded(True)
    group.set_expanded(False)

    assert seen == [True, False]


def test_chevron_differs_between_states(application: QApplication) -> None:
    """Свёрнуто — «>», раскрыто — он же вниз. Одна картинка на оба состояния
    означала бы, что шеврон не сообщает состояние вовсе."""  # noqa: RUF002
    collapsed = chevron_pixmap(False, DARK.accent).toImage()
    expanded = chevron_pixmap(True, DARK.accent).toImage()

    assert not collapsed.isNull()
    assert collapsed != expanded


def test_chevron_follows_the_palette(application: QApplication) -> None:
    """Смена темы перекрашивает шеврон: он рисуется, а не берётся из шрифта."""  # noqa: RUF002
    group = CollapsibleGroup("СЕРВЕРЫ")
    group.set_palette(DARK)
    dark = group.chevron().toImage()
    group.set_palette(LIGHT)

    assert group.chevron().toImage() != dark


def test_note_stays_visible_while_the_body_is_collapsed(
    application: QApplication,
) -> None:
    """Подпись блока — не часть сворачиваемого тела (нужна `_add_block`, задача 2)."""
    note = QLabel("подпись")
    group = CollapsibleGroup("Сочетания раздела «Базы»", note=note)
    body = QLabel("таблица")
    group.body_layout().addWidget(body)

    assert group.is_expanded() is False
    assert note.isVisibleTo(group) is True
    assert body.isVisibleTo(group) is False


def test_group_header_is_reachable_by_tab(application: QApplication) -> None:
    """Заголовок — `QToolButton` именно ради хода по клавиатуре (спека §1.2).

    [Ф] замер 02.09.2026: `focusPolicy` кнопки — `TabFocus`. Снять его
    (например, вернувшись к `QLabel` с обработкой мыши) значило бы
    отнять у раздела ход по Tab целиком, а рамку фокуса в теме
    превратить в недостижимую декорацию — раздел, где всё свёрнуто,
    без клавиатуры становится заметно менее пригодным.
    """  # noqa: RUF002
    group = CollapsibleGroup("СЕРВЕРЫ")

    assert group.button().focusPolicy() & Qt.FocusPolicy.TabFocus
