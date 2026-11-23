"""Общие виджеты экранов v4 по мокапу (план Б, задачи 6, 7)."""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QWidget,
)

from onecstarter.domain.cli_params import Finding, Level
from onecstarter.ui.components import (
    FORM_LABEL_WIDTH,
    MENU_SHORTCUT_GAP,
    Box,
    Chip,
    DialogFooter,
    FindingsList,
    Note,
    accent_label,
    align_form,
    bold_font,
    dim_label,
    hint_label,
    mono_font,
    mono_span,
    notes_from_findings,
    widen_for_shortcuts,
)


def test_mono_span_escapes_the_text_and_names_the_mono_family() -> None:
    """Одно место разметки «моно + цвет» для описаний, шагов и подстановок (предпроверка 3.5)."""
    assert mono_span("<{база}>", "#123456") == (
        '<span style="color:#123456; font-family:Consolas">&lt;{база}&gt;</span>'
    )


def test_bold_font_is_a_bold_copy() -> None:
    base = QFont()
    bold = bold_font(base)
    assert bold.bold() and not base.bold()


def test_named_labels(qtbot: Any) -> None:
    """QLabel без QApplication роняет процесс — нужен `qtbot` (расхождение с листингом плана)."""  # noqa: RUF002
    assert dim_label("Набор:").objectName() == "DimLabel"  # noqa: RUF001
    hint = hint_label("отмечено 4")
    assert hint.objectName() == "Hint" and hint.wordWrap()
    assert accent_label("1С:Предприятие").objectName() == "AccentLabel"  # noqa: RUF001


def test_mono_font_asks_for_consolas() -> None:
    font = mono_font()
    assert font.family() == "Consolas"
    assert font.styleHint() == QFont.StyleHint.Monospace
    assert font.pointSize() == 9


def test_align_form_right_aligns_labels_in_a_shared_column(qtbot: Any) -> None:
    """Мокап, экран 1 (`.form label`): подписи справа, `text_dim`, колонка общая для трёх форм."""
    host = QWidget()
    qtbot.addWidget(host)
    form = QFormLayout(host)
    form.addRow("Имя", QLineEdit())
    form.addRow(accent_label("1С:Предприятие"), QLineEdit())  # noqa: RUF001
    form.addRow("Путь", QLabel("подсказка"))
    form.addRow("", QLabel("строка без подписи"))  # Qt не создаёт метку для пустого текста
    form.addRow(QLabel("строка на всю ширину"))
    align_form(form)
    right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    assert form.labelAlignment() == right
    labels: list[QLabel] = []
    for row in range(3):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        assert item is not None
        label = item.widget()
        assert isinstance(label, QLabel)
        labels.append(label)
    assert [label.objectName() for label in labels] == ["FormLabel", "AccentLabel", "FormLabel"]
    assert {label.minimumWidth() for label in labels} == {FORM_LABEL_WIDTH}
    assert all(label.alignment() == right for label in labels)
    assert form.itemAt(3, QFormLayout.ItemRole.LabelRole) is None
    assert form.itemAt(4, QFormLayout.ItemRole.LabelRole) is None


def test_box_has_a_title_strip(qtbot: Any) -> None:
    box = Box("Сценарии")
    qtbot.addWidget(box)
    assert box.objectName() == "Box"
    assert box.title_label().objectName() == "BoxTitle"
    assert box.title_label().text() == "Сценарии"
    untitled = Box()
    qtbot.addWidget(untitled)
    assert untitled.title_label().isHidden()
    untitled.set_title("Шаг 1")
    assert not untitled.title_label().isHidden()


def test_footer_puts_left_items_hint_and_actions_in_mockup_order(qtbot: Any) -> None:
    """Мокап `.foot`: слева подсказка или кнопка, справа действия; полоса — `surface`."""
    footer = DialogFooter()
    qtbot.addWidget(footer)
    copy = QPushButton("Копировать строку")
    ok = QPushButton("ОК")  # noqa: RUF001
    footer.add_left(copy)
    footer.add_right(ok)
    footer.set_hint("Предупреждения не мешают сохранить строку.")
    footer.resize(640, 40)
    footer.show()
    qtbot.waitExposed(footer)
    assert footer.objectName() == "DialogFooter"
    assert footer.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert copy.x() < footer.hint_label().x() < ok.x()
    assert footer.hint_text() == "Предупреждения не мешают сохранить строку."
    footer.set_hint("")
    assert footer.hint_label().isHidden()
    assert ok.geometry().right() > footer.width() - 40  # действия прижаты вправо


def test_findings_list_shows_one_callout_per_note(qtbot: Any) -> None:
    """В5: уровень замечания больше не теряется в `"\n".join`."""  # noqa: RUF002
    widget = FindingsList()
    qtbot.addWidget(widget)
    assert widget.isHidden()
    widget.set_notes(
        notes_from_findings(
            [
                Finding(Level.ERROR, "/Foo", "/Foo — неизвестный ключ."),
                Finding(Level.WARNING, "/L", "предупреждение"),
            ]
        )
    )
    assert not widget.isHidden()
    assert [label.objectName() for label in widget.labels()] == ["Callout", "Callout"]
    assert [label.property("level") for label in widget.labels()] == ["error", "warning"]
    assert widget.levels() == ["error", "warning"]
    assert widget.texts() == ["/Foo — неизвестный ключ.", "предупреждение"]
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in widget.labels())
    widget.set_notes([])
    assert widget.isHidden() and widget.labels() == []


def test_lead_sentence_is_bold_and_user_text_is_escaped(qtbot: Any) -> None:
    """Мокап, экран 5 (стр. 350): первое предложение предупреждения о замене — жирным."""  # noqa: RUF002
    widget = FindingsList()
    qtbot.addWidget(widget)
    widget.set_notes(
        [Note(Level.ERROR, "Данные 2 баз будут заменены. Копию <программа> не делает.", lead=True)]
    )
    label = widget.labels()[0]
    assert label.textFormat() == Qt.TextFormat.RichText
    assert label.text() == (
        "<b>Данные 2 баз будут заменены.</b> Копию &lt;программа&gt; не делает."
    )
    assert widget.texts() == ["Данные 2 баз будут заменены. Копию <программа> не делает."]


def test_same_notes_do_not_rebuild_the_labels(qtbot: Any) -> None:
    """Строка проверяется на каждый символ — метки не пересоздаются без нужды (В4: высота окна)."""  # noqa: RUF002
    widget = FindingsList()
    qtbot.addWidget(widget)
    notes = [Note(Level.WARNING, "x")]
    widget.set_notes(notes)
    first = widget.labels()[0]
    widget.set_notes(list(notes))
    assert widget.labels()[0] is first


def test_chip_level_is_a_dynamic_property(qtbot: Any) -> None:
    chip = Chip(Level.ERROR, "1 ошибка")
    qtbot.addWidget(chip)
    assert chip.objectName() == "Chip" and chip.property("level") == "error"
    chip.set_level(Level.WARNING)
    assert chip.property("level") == "warning" and chip.level() is Level.WARNING


def test_lead_escapes_head_and_text_without_separator(qtbot: Any) -> None:
    """Экранируются все три места: голова, хвост и ветка без «. »."""
    widget = FindingsList()
    qtbot.addWidget(widget)
    widget.set_notes(
        [
            Note(Level.ERROR, "<b>Голова</b>. Хвост", lead=True),
            Note(Level.ERROR, "<i>без точки</i>", lead=True),
        ]
    )
    first, second = widget.labels()
    assert first.text() == "<b>&lt;b&gt;Голова&lt;/b&gt;.</b> Хвост"
    assert second.text() == "<b>&lt;i&gt;без точки&lt;/i&gt;</b>"


def test_chip_set_level_repolishes(qtbot: Any) -> None:
    """Без `repolish` QSS не перечитывает свойство: qproperty-alignment не меняется."""
    chip = Chip(Level.ERROR, "x")
    qtbot.addWidget(chip)
    chip.setStyleSheet('QLabel#Chip[level="warning"] { qproperty-alignment: AlignRight; }')
    chip.ensurePolished()
    before = chip.alignment()
    chip.set_level(Level.WARNING)
    assert before != Qt.AlignmentFlag.AlignRight
    assert chip.alignment() & Qt.AlignmentFlag.AlignRight


def test_menu_with_shortcuts_gets_extra_width(qapp: object) -> None:
    """План В, Б9: колонка сочетаний прижата к правому краю меню — запас ширины раздвигает её
    и длинное название («Запустить с параметрами…» почти касалось «Ctrl+F3»)."""  # noqa: RUF002
    menu = QMenu()
    menu.addAction("Запустить с параметрами…\tCtrl+F3")  # noqa: RUF001
    menu.addAction("Свойства…\tAlt+Enter")
    menu.ensurePolished()
    natural = menu.sizeHint().width()
    widen_for_shortcuts(menu)
    assert menu.minimumWidth() == natural + MENU_SHORTCUT_GAP


def test_widening_again_does_not_add_the_gap_twice(qapp: object) -> None:
    """Предпроверка плана В, п. 22: `sizeHint` показанного и дополненного меню учитывает
    прежний минимум — без сброса повторный вызов прибавлял запас ещё раз."""  # noqa: RUF002
    menu = QMenu()
    menu.addAction("Запустить с параметрами…\tCtrl+F3")  # noqa: RUF001
    widen_for_shortcuts(menu)
    menu.show()
    QApplication.processEvents()
    menu.hide()
    menu.addAction("Обновить\tF5")
    widen_for_shortcuts(menu)
    widen_for_shortcuts(menu)
    twin = QMenu()
    twin.addAction("Запустить с параметрами…\tCtrl+F3")  # noqa: RUF001
    twin.addAction("Обновить\tF5")
    twin.ensurePolished()
    assert menu.minimumWidth() == twin.sizeHint().width() + MENU_SHORTCUT_GAP


def test_menu_without_shortcuts_is_left_alone(qapp: object) -> None:
    menu = QMenu()
    menu.addAction("Показать")
    widen_for_shortcuts(menu)
    assert menu.minimumWidth() == 0
