"""Сворачиваемая группа настроек: свёртка, шеврон, тело."""

import html
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from onecstarter.ui.settings_group import (
    SUMMARY_HINT_MAX,
    SUMMARY_SEPARATOR,
    CollapsibleGroup,
    chevron_pixmap,
)
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


def test_summary_splits_the_title_and_keeps_the_full_text(application: QApplication) -> None:
    """Мокап, экран 1: жирное имя и сводка обычным весом `text_dim` (`#BlockSummary`)."""
    group = CollapsibleGroup("Параметры запуска", accent=False, summary=True)
    group.set_title("Параметры запуска — 4 ключа · Конфигуратор: 1 ключ")
    summary = group.summary_label()
    assert summary is not None and summary.objectName() == "BlockSummary"
    assert group.button().text() == "Параметры запуска"
    assert summary.full_text() == "— 4 ключа · Конфигуратор: 1 ключ"
    # В сводке хранилища — адрес и пользователь, набранные пользователем:  # noqa: RUF003
    # метка обязана быть PlainText, не rich text.
    assert summary.textFormat() == Qt.TextFormat.PlainText
    assert group.title() == "Параметры запуска — 4 ключа · Конфигуратор: 1 ключ"
    group.set_title("Параметры запуска")
    assert summary.isHidden()


def test_clicking_the_summary_toggles_the_group(qtbot: Any) -> None:
    group = CollapsibleGroup("Блок — сводка", accent=False, summary=True)
    qtbot.addWidget(group)
    group.show()
    qtbot.waitExposed(group)
    summary = group.summary_label()
    assert summary is not None
    qtbot.mouseClick(summary, Qt.MouseButton.LeftButton)
    assert group.is_expanded()


def test_header_widgets_sit_right_of_the_summary(qtbot: Any) -> None:
    group = CollapsibleGroup("Блок — сводка", accent=False, summary=True)
    qtbot.addWidget(group)
    chip = QLabel("1 ошибка")
    group.add_header_widget(chip)
    group.resize(520, 60)
    group.show()
    qtbot.waitExposed(group)
    summary = group.summary_label()
    assert summary is not None
    assert chip.parentWidget() is group.header_row()
    assert chip.x() > summary.geometry().right()
    assert chip.geometry().right() > group.width() - 80  # прижат вправо растяжкой


def test_rule_above_follows_the_palette(application: QApplication) -> None:
    """Мокап `.grp{border-top}`: линия над блоком цветом `border`."""
    group = CollapsibleGroup("Блок", accent=False, rule=False, rule_above=True)
    group.set_palette(LIGHT)
    rule = group.rule_above()
    assert rule is not None and LIGHT.border in rule.styleSheet()


def test_plain_group_keeps_its_old_shape(application: QApplication) -> None:
    """Группы «Настроек» не меняются: без строки заголовка и линии сверху."""
    group = CollapsibleGroup("СЕРВЕРЫ")
    assert group.header_row() is None and group.summary_label() is None
    assert group.rule_above() is None
    assert group.button().text() == "СЕРВЕРЫ"
    with pytest.raises(ValueError):
        group.add_header_widget(QLabel("x"))


LONG = "tcp://repository-server.very-long-domain-name.example.local:1742/department/project/main"


def test_long_summary_is_elided_and_does_not_widen_the_group(
    application: QApplication, qtbot: Any
) -> None:
    """План В, Б4 (решение заказчика): длинная сводка — «…» посередине, полный текст — подсказкой.

    Предпроверка 22.11.2026, п. 2: без жирного 10 pt заголовка (`accent=False`) и с коротким
    именем — иначе минимум группы задаёт кнопка (358 px на офскрине), а не сводка.
    """  # noqa: RUF002
    group = CollapsibleGroup("Хранилище", accent=False, summary=True)
    qtbot.addWidget(group)
    group.set_title(f"Хранилище{SUMMARY_SEPARATOR}{LONG}")
    group.resize(500, 60)
    group.show()
    qtbot.waitExposed(group)
    label = group.summary_label()
    assert label is not None
    assert label.full_text() == f"— {LONG}"
    full_width = label.fontMetrics().horizontalAdvance(label.full_text())
    assert group.minimumSizeHint().width() < full_width
    assert label.toolTip() == f"<p style='white-space:pre'>{html.escape(label.full_text())}</p>"
    qtbot.waitUntil(lambda: "…" in label.text(), timeout=2000)
    assert label.text() != label.full_text()


def test_summary_takes_the_free_room_of_the_header(
    application: QApplication, qtbot: Any
) -> None:
    """Предпроверка плана В, п. 7: желаемая ширина сводки ограничена, но свободное место
    строки заголовка она забирает — в широком окне адрес виден целиком."""  # noqa: RUF002
    group = CollapsibleGroup("Хранилище", accent=False, summary=True)
    qtbot.addWidget(group)
    group.add_header_widget(QLabel("1 ошибка"))
    group.set_title(f"Хранилище{SUMMARY_SEPARATOR}{LONG}")
    group.resize(1400, 60)
    group.show()
    qtbot.waitExposed(group)
    label = group.summary_label()
    assert label is not None
    assert label.sizeHint().width() <= SUMMARY_HINT_MAX
    qtbot.waitUntil(lambda: label.text() == label.full_text(), timeout=2000)


def test_summary_tooltip_shows_user_text_literally(application: QApplication) -> None:
    """Предпроверка плана В, п. 20: Qt сам распознаёт rich text в подсказке — текст из полей
    (адрес, пользователь) экранируется."""  # noqa: RUF002
    group = CollapsibleGroup("Хранилище", accent=False, summary=True)
    group.set_title(f"Хранилище{SUMMARY_SEPARATOR}tcp://repo/<b>main</b> · dev")
    label = group.summary_label()
    assert label is not None
    assert "&lt;b&gt;main&lt;/b&gt;" in label.toolTip()
    assert "<b>" not in label.toolTip()
