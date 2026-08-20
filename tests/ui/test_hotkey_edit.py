"""Поле захвата сочетания: Qt-событие клавиши → каноническая строка."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from onecstarter.services.hotkeys import MOD_ALT, MOD_CONTROL
from onecstarter.ui.hotkey_edit import HotkeyEdit, spec_from_event


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


VK_B = 0x42
SCAN_B = 48
# На клавише латинской `B` в русской раскладке стоит «И» (ЙЦУКЕН: нижний ряд  # noqa: RUF003
# ZXCVBNM → ЯЧСМИТЬ). Именно её `key()` и отдаёт при активной русской
# раскладке, тогда как драйверный `nativeVirtualKey` остаётся `VK_B`
# (спека §4.1, находка блока В протокола 20.08.2026).  # noqa: RUF003
#
# Первая редакция этих тестов брала «Б» (`0x411`) и утверждала, что она
# приходит с клавиши `B`. Это неверно — «Б» живёт на клавише `,`  # noqa: RUF003
# (`VK_OEM_COMMA`), то есть в одном классе с «Ё» и «Ж»: у неё нет латинского  # noqa: RUF003
# буквенного эквивалента, и она правильно отвергается. Тест доказывал верное
# утверждение событием, которого железо не порождает (находка финального
# ревью ветки, п. Б-2).
KEY_CYRILLIC_I = 0x418
KEY_CYRILLIC_BE = 0x411


def _press(
    key: Qt.Key | int,
    modifiers: Qt.KeyboardModifier,
    *,
    native_vk: int = 0,
    native_scan: int = 0,
) -> QKeyEvent:
    """Нажатие клавиши. `native_vk=0` — событие без кода от драйвера.

    Ноль здесь не для краткости: короткий конструктор `QKeyEvent` именно его
    и ставит, а значит `native_vk=0` — честная модель синтезированного
    события, на котором обязан работать запасной путь `spec_from_event`.
    """  # noqa: RUF002
    return QKeyEvent(
        QKeyEvent.Type.KeyPress, key, modifiers, native_scan, native_vk, 0
    )


def test_captures_modifier_combination(application: QApplication) -> None:
    event = _press(
        Qt.Key.Key_B,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.modifiers == MOD_CONTROL | MOD_ALT
    assert spec.key == "B"


def test_bare_modifier_press_is_not_a_combination(application: QApplication) -> None:
    """Пока нажат только Ctrl, сочетания ещё нет — поле не должно дёргаться."""
    event = _press(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    assert spec_from_event(event) is None


def test_key_without_modifier_is_rejected(application: QApplication) -> None:
    event = _press(Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier)
    assert spec_from_event(event) is None


def test_shift_only_is_rejected(application: QApplication) -> None:
    event = _press(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier)
    assert spec_from_event(event) is None


def test_widget_emits_canonical_text(application: QApplication) -> None:
    edit = HotkeyEdit()
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(
        _press(
            Qt.Key.Key_B,
            Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier,
        )
    )

    assert seen == ["Ctrl+Alt+B"]
    assert edit.text() == "Ctrl+Alt+B"


def test_widget_ignores_unusable_press(application: QApplication) -> None:
    edit = HotkeyEdit()
    edit.set_combination("Ctrl+Alt+B")
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(_press(Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier))

    assert seen == []
    assert edit.text() == "Ctrl+Alt+B"


def test_delete_clears_to_disabled(application: QApplication) -> None:
    """Backspace/Delete — способ выключить хоткей (спека §4.1)."""
    edit = HotkeyEdit()
    edit.set_combination("Ctrl+Alt+B")
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(_press(Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier))

    assert seen == [""]
    assert edit.text() == HotkeyEdit.DISABLED_TEXT


def test_set_combination_shows_disabled_placeholder(application: QApplication) -> None:
    edit = HotkeyEdit()
    edit.set_combination("")
    assert edit.text() == HotkeyEdit.DISABLED_TEXT


def test_cyrillic_layout_captures_the_latin_key_of_the_same_button(
    application: QApplication,
) -> None:
    """Русская раскладка не мешает назначить сочетание (спека §4.1).

    Прогон блока В 20.08.2026: заказчик, сменив сочетание, не смог вернуть
    `Ctrl+Alt+B` — при русской раскладке поле молча не реагировало. Промахом
    это не было: то же сочетание в системе срабатывает при любой раскладке
    (шаг Б3), потому что `RegisterHotKey` подписан на драйверный код `0x42`.
    Захват обязан читать тот же код, а не раскладко-зависимый `key()`.
    """  # noqa: RUF002
    event = _press(
        KEY_CYRILLIC_I,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=VK_B,
        native_scan=SCAN_B,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.key == "B"
    assert spec.vk == VK_B


def test_cyrillic_key_without_latin_counterpart_is_still_rejected(
    application: QApplication,
) -> None:
    """«Ж» на клавише `;` — настоящий промах, и трактовка для него не меняется.

    Драйверный код такой клавиши (`VK_OEM_1`) в поддержанный набор не входит:
    ни буква, ни цифра, ни F-клавиша.

    Что именно охраняет этот тест (уточнено по разбору мутаций 20.08.2026,
    прежняя формулировка обещала больше, чем тест ловит): `key_name_for_vk`
    не имеет права перевести НЕподдержанный драйверный код в имя ИЗ набора.
    Мусорное имя на выходе таблицы безопасно — его добьёт `parse_hotkey`,
    и отказ сохранится; а вот подстановка годного имени превращает промах
    в чужое рабочее сочетание, и остановить это уже некому.
    """  # noqa: RUF002
    event = _press(
        0x416,  # «Ж»
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=0xBA,  # VK_OEM_1, клавиша `;`
        native_scan=39,
    )
    assert spec_from_event(event) is None


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (Qt.Key.Key_B, "B"),
        (Qt.Key.Key_1, "1"),
        # F-клавиша обязательна: у неё единственной имя многосимвольное,  # noqa: RUF003
        # и только на ней видно, что запасной путь не режет и не путает имя.
        (Qt.Key.Key_F5, "F5"),
    ],
)
def test_synthesized_event_without_native_code_still_captures(
    key: Qt.Key, expected: str, application: QApplication
) -> None:
    """Запасной путь: `nativeVirtualKey == 0` — код от драйвера не пришёл.

    Так выглядят события, собранные программно (короткий конструктор
    `QKeyEvent` ставит ноль). Терять на них работающий захват нельзя:
    иначе правка ради раскладки сломала бы всё, что синтезирует нажатия.

    Три стимула, а не один (разбор мутаций 20.08.2026): в первой редакции
    тест бил ровно по латинской `B` — тем же стимулом, что и соседний
    `test_captures_modifier_combination`, — и потому был бессилен. Мутация
    `QKeySequence(...).toString()[:1]` пережила весь набор из 1235 тестов,
    молча превращая `Ctrl+Alt+F5` в `Ctrl+Alt+F`: не отказ, а подмена
    сочетания на другое, рабочее. Ловит её только F-клавиша.
    """  # noqa: RUF002
    event = _press(
        key,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.key == expected


def test_native_code_wins_over_the_layout_dependent_key(
    application: QApplication,
) -> None:
    """При расхождении двух источников верить драйверу, а не раскладке.

    Сторож приоритета: если бы `key()` проверялся первым, кириллический код
    дал бы `None` ещё до того, как драйверный код был бы прочитан вовсе.
    """  # noqa: RUF002
    latin = _press(
        Qt.Key.Key_G,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=VK_B,
        native_scan=SCAN_B,
    )
    spec = spec_from_event(latin)
    assert spec is not None
    assert spec.key == "B"


def test_widget_accepts_cyrillic_layout_press(application: QApplication) -> None:
    """Поле целиком, не только разбор события: значение встаёт и уходит наружу."""
    edit = HotkeyEdit()
    edit.set_combination("Ctrl+Alt+G")
    seen: list[str] = []
    edit.captured.connect(seen.append)

    edit.keyPressEvent(
        _press(
            KEY_CYRILLIC_I,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
            native_vk=VK_B,
            native_scan=SCAN_B,
        )
    )

    assert seen == ["Ctrl+Alt+B"]
    assert edit.text() == "Ctrl+Alt+B"


def test_cyrillic_be_lives_on_another_key_and_is_rejected(
    application: QApplication,
) -> None:
    """«Б» — это клавиша `,`, а не клавиша `B` (находка ревью ветки, п. Б-2).

    Тест закрепляет разделение двух классов, которые прежняя редакция путала:
    буква с латинским позиционным эквивалентом принимается (тест выше),
    буква без него отвергается — `VK_OEM_COMMA` в наборе не значится.
    Спутав их, следующий исполнитель решит, что правка про раскладку
    не работает, и «починит» верное поведение.
    """  # noqa: RUF002
    event = _press(
        KEY_CYRILLIC_BE,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=0xBC,  # VK_OEM_COMMA
        native_scan=51,
    )
    assert spec_from_event(event) is None


def test_numpad_key_is_not_silently_taken_for_the_main_row(
    application: QApplication,
) -> None:
    """NumPad 5 — не главная «5», и подменять одну другой нельзя.

    Драйвер шлёт `VK_NUMPAD5` (`0x65`), а `key()` для той же клавиши отдаёт
    `Key_5`. Приняв нажатие по `key()`, поле показало бы `Ctrl+Alt+5`,
    `RegisterHotKey` подписался бы на код главного ряда `0x35` — и клавиша,
    которую пользователь нажал при назначении, хоткей не подняла бы никогда.
    Это ровно то «назначено на экране, не работает в системе», ради чего
    таблица VK — одна на оба направления.

    Правило: код от драйвера пришёл (не ноль) — судит только таблица.
    Нет кода — только тогда запасной путь через `key()`.
    """  # noqa: RUF002
    event = _press(
        Qt.Key.Key_5,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        native_vk=0x65,  # VK_NUMPAD5
        native_scan=76,
    )
    assert spec_from_event(event) is None


def test_shifted_digit_is_named_by_the_driver_not_by_the_punctuation(
    application: QApplication,
) -> None:
    """`Ctrl+Alt+Shift+2` на US-раскладке, где `key()` отдаёт `@`.

    Правка расширила набор принимаемых нажатий, и расширение полезное:
    имя берётся у драйвера (`0x32` — цифра `2`), а не у символа, который
    получился бы с учётом Shift. До правки такое нажатие отвергалось,
    хотя `RegisterHotKey` принял бы его без разговоров.
    """  # noqa: RUF002
    event = _press(
        Qt.Key.Key_At,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier,
        native_vk=0x32,
        native_scan=3,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.key == "2"
