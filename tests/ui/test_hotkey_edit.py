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
        # F12, а не F5, — по той же причине, что и в тесте драйверного пути:  # noqa: RUF003
        # трёхсимвольное имя ловит усечение и до одного символа, и до двух.
        (Qt.Key.Key_F12, "F12"),
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


@pytest.mark.parametrize(
    ("key", "native_vk", "extra_modifier", "expected"),
    [
        # Буква: `key()` кириллический, драйверный код латинский.
        (KEY_CYRILLIC_I, VK_B, Qt.KeyboardModifier.NoModifier, "B"),
        # Цифра под Shift: `key()` отдаёт `@`, драйвер — цифру `2`.
        (Qt.Key.Key_At, 0x32, Qt.KeyboardModifier.ShiftModifier, "2"),
        # F-клавиша: единственная форма с многосимвольным именем. Именно F12,  # noqa: RUF003
        # а не F5: трёхсимвольное имя доминирует двухсимвольное как  # noqa: RUF003
        # представитель класса — убивает и усечение до одного символа,
        # и до двух («F12»[:2] == «F1», тоже рабочее сочетание).
        (Qt.Key.Key_F12, 0x7B, Qt.KeyboardModifier.NoModifier, "F12"),
    ],
)
def test_driver_code_names_every_form_of_key(
    key: Qt.Key | int,
    native_vk: int,
    extra_modifier: Qt.KeyboardModifier,
    expected: str,
    application: QApplication,
) -> None:
    """Драйверный путь именует все три формы имени, и `vk` совпадает с нажатым.

    Три формы, а не одна (находка мутационной проверки 20.08.2026, вторая
    волна): прошлая волна параметризовала так **запасной** путь, а основной —
    драйверный, по которому идёт каждое реальное нажатие, — остался закреплён
    только односимвольными именами. Мутация `(key_name_for_vk(vk) or "")[:1]`
    пережила из-за этого весь набор из 1240 тестов, превращая и `F5`, и `F12`
    в `Ctrl+Alt+F`: не отказ, а тихая подмена на другое рабочее сочетание.

    Сверка `spec.vk == native_vk` — дублирующая запись инварианта «регистрация
    уходит ровно на нажатый код». Собственной различающей силы у неё нет, и
    честно сказать об этом важнее, чем оставить громкую формулировку: `spec.vk`
    выводится из имени (`parse_hotkey` берёт его из `_VK_BY_KEY`), а не из
    события, поэтому при верном `spec.key` совпадение следует автоматически.
    Настоящий сторож round-trip двух сторон таблицы — сплошной перебор
    в `test_key_name_for_vk_agrees_with_parse_hotkey`; здесь инвариант записан
    в точке применения, чтобы следующий исполнитель видел его там, где он важен.

    Заодно закреплено полезное расширение набора: `Ctrl+Alt+Shift+2`
    на US-раскладке до правки отвергалось, хотя `RegisterHotKey` принял бы
    его без разговоров.
    """  # noqa: RUF002
    event = _press(
        key,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | extra_modifier,
        native_vk=native_vk,
        native_scan=3,
    )
    spec = spec_from_event(event)
    assert spec is not None
    assert spec.key == expected
    assert spec.vk == native_vk
