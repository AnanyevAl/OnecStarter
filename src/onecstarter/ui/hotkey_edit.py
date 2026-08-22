"""Поле захвата сочетания: нажатие клавиш вместо ввода текста.

Отдельный файл, а не часть `settings_view`: перевод Qt-модификаторов
в наши биты — единственная Qt-специфичная часть работы с сочетанием,
и держать её рядом с раскладкой раздела значило бы смешать две разные
ответственности в одном файле.

Поле только захватывает. Сохранение, регистрацию и показ отказа делает
раздел «Настройки»: занятость сочетания — свойство системы, а не ввода
(спека §4.2).
"""  # noqa: RUF002

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QLineEdit, QWidget

from onecstarter.services.hotkeys import (
    HotkeySpec,
    format_hotkey,
    key_name_for_vk,
    parse_hotkey,
)

_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr,
}

_CLEAR_KEYS = {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}

_MODIFIER_NAMES = (
    (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
    (Qt.KeyboardModifier.AltModifier, "Alt"),
    (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    (Qt.KeyboardModifier.MetaModifier, "Win"),
)


def spec_from_event(event: QKeyEvent) -> HotkeySpec | None:
    """Сочетание из нажатия. `None` — нажатое сочетанием не является.

    Правило допустимости не дублируется: строка собирается и отдаётся
    в `parse_hotkey`, который один решает, годится ли она. Иначе два
    места судили бы об одном и разошлись бы при первой же правке.
    """  # noqa: RUF002
    key = Qt.Key(event.key())
    if key in _MODIFIER_KEYS:
        # Модификатор ещё удерживается, клавиши нет — сочетания пока нет.
        # Это быстрый путь, а не рубеж: одиночный модификатор отвергается  # noqa: RUF003
        # и без него — VK модификаторов (0x10-0x12, 0x5B) лежат вне
        # диапазонов таблицы, а запасной путь даёт имена `Control`/`Meta`,  # noqa: RUF003
        # которых `parse_hotkey` не знает (находка ревью ветки, п. Н-2).  # noqa: RUF003
        return None
    modifiers = event.modifiers()
    names = [name for bit, name in _MODIFIER_NAMES if modifiers & bit]
    key_name = _key_name(event, key)
    if not key_name:
        return None
    return parse_hotkey("+".join([*names, key_name]))


def _key_name(event: QKeyEvent, key: Qt.Key) -> str:
    """Имя клавиши: код от драйвера, а `key()` — только когда кода нет.

    Суть правки 20.08.2026 (спека §4.1). `key()` при русской раскладке
    отдаёт кириллический код, и `Ctrl+Alt+B` не назначался вовсе, хотя
    в системе это сочетание срабатывает при любой раскладке:
    `RegisterHotKey` подписан на `nativeVirtualKey`, тот же для клавиши
    в обеих раскладках.

    Драйверный код есть — судит ТОЛЬКО таблица, и его отсутствие в ней
    означает отказ (уточнено по находке финального ревью ветки, п. Б-1).
    Прежняя редакция уходила в `key()` на любом коде вне таблицы, и NumPad 5
    (`VK_NUMPAD5`, `0x65`) принимался именем главного ряда: поле показывало
    `Ctrl+Alt+5`, регистрация уходила на `0x35`, а нажатие клавиши, которой
    сочетание назначали, хоткей не поднимало никогда. Захват обязан читать
    ровно то, на что подпишется регистрация, — иначе таблица VK перестаёт
    быть одной на оба направления.

    Запасной путь — только при нулевом коде: так выглядят события, собранные
    программно, а не пришедшие от драйвера. Короткий конструктор `QKeyEvent`
    ставит ноль — **[проверено, 20.08.2026]**; синтез через `KEYEVENTF_UNICODE`
    оставляет `wVk` нулевым — **[из документации Microsoft]**. Терять на таких
    событиях работающий захват нельзя.
    """  # noqa: RUF002
    native_vk = event.nativeVirtualKey()
    if native_vk:
        return key_name_for_vk(native_vk) or ""
    # int(key), а не сам enum: конструктор QKeySequence в PySide6  # noqa: RUF003
    # перегружен, и передача Qt.Key может уйти не в ту перегрузку.
    return QKeySequence(int(key)).toString()


class HotkeyEdit(QLineEdit):
    """Только для чтения: значение появляется нажатием, а не набором текста."""  # noqa: RUF002

    DISABLED_TEXT = "не назначено"

    captured = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText(self.DISABLED_TEXT)
        self.setToolTip(
            "Нажмите сочетание с Ctrl, Alt или Win. "  # noqa: RUF001
            "Backspace или Delete — выключить вызов."
        )

    def set_combination(self, text: str) -> None:
        """Показать сохранённое значение. Пустая строка — «не назначено»."""
        self.setText(text or self.DISABLED_TEXT)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = Qt.Key(event.key())
        if key in _CLEAR_KEYS:
            self.set_combination("")
            self.captured.emit("")
            event.accept()
            return
        spec = spec_from_event(event)
        if spec is None:
            # Непригодное нажатие не стирает уже назначенное: пользователь
            # промахнулся, а не отказался от сочетания.  # noqa: RUF003
            event.accept()
            return
        text = format_hotkey(spec)
        self.set_combination(text)
        self.captured.emit(text)
        event.accept()
