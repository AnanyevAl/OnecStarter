"""Сочетания клавиш раздела «Базы» — одна таблица для регистрации и справочника.

Решение заказчика 29.08.2026 (tasks.md, T-11, п. 3): сочетания зашиты,
настраиваемого keymap нет; раздел «Настройки» показывает их справочником
(только чтение, задача 3). Таблица живёт здесь, а не в `bases/view.py`,
чтобы справочник не импортировал вьюху; расхождение таблицы с реально
созданными `QShortcut` ловит `test_shortcut_reference_matches_registered_
shortcuts` в `tests/ui/test_bases_view.py`.

`sequences` — строки `QKeySequence`, которыми вьюха регистрирует сочетание.
Пустой кортеж — клавиша обрабатывается не `QShortcut`: Enter — сигналами
`activated`/`returnPressed`, `Insert`/`Delete` — `keyPressEvent` дерева
(только при фокусе в нём, T-11 пп. 7–8).
"""  # noqa: RUF002

from dataclasses import dataclass


@dataclass(frozen=True)
class ShortcutSpec:
    label: str
    title: str
    sequences: tuple[str, ...]


BASES_SHORTCUTS: tuple[ShortcutSpec, ...] = (
    ShortcutSpec("Enter", "Запустить выбранную базу; в поиске — первую найденную", ()),
    ShortcutSpec("F3", "Запустить (1С:Предприятие)", ("F3",)),  # noqa: RUF001
    ShortcutSpec("F4", "Конфигуратор", ("F4",)),
    ShortcutSpec("Ctrl+1", "Тонкий клиент", ("Ctrl+1",)),
    ShortcutSpec("Ctrl+2", "Толстый клиент", ("Ctrl+2",)),
    ShortcutSpec("Ctrl+3", "Конфигуратор (то же, что F4)", ("Ctrl+3",)),
    ShortcutSpec("Alt+Enter", "Свойства записи или группы", ("Alt+Return", "Alt+Enter")),
    ShortcutSpec("Ctrl+D", "В избранное / убрать из избранного", ("Ctrl+D",)),  # noqa: RUF001
    ShortcutSpec("Ctrl+N", "Добавить базу", ("Ctrl+N",)),
    ShortcutSpec("Insert", "Добавить базу в группу текущей строки", ()),
    ShortcutSpec(
        "Delete", "Удалить запись или группу из списка (с подтверждением)", ()  # noqa: RUF001
    ),
    ShortcutSpec("Alt+↑ / Alt+↓", "Переставить запись внутри группы", ("Alt+Up", "Alt+Down")),
)
