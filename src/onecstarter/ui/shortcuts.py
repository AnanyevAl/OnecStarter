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
    # M-10 финального ревью ветки v3.1 (по желанию заказчика): сочетание
    # регистрирует оболочка (`ui/shell.py`, QShortcut(StandardKey.Find)),
    # а не вьюха «Базы» — пустой `sequences`, как у Enter/Insert/Delete ниже,  # noqa: RUF003
    # чтобы test_shortcut_reference_matches_registered_shortcuts не ждал
    # от этой вьюхи собственного QShortcut на Ctrl+F.
    ShortcutSpec("Ctrl+F", "Поиск (Базы и EDT)", ()),
    ShortcutSpec("Enter", "Запустить выбранную базу; в поиске — первую найденную", ()),
    ShortcutSpec("F3", "Запустить (1С:Предприятие)", ("F3",)),  # noqa: RUF001
    ShortcutSpec("F4", "Конфигуратор", ("F4",)),
    ShortcutSpec("F5", "Обновить список и перепроверить доступность каталогов", ("F5",)),
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
    ShortcutSpec(
        "Alt+↑ / Alt+↓",
        "Переставить запись или группу (только в режиме «как в файле»)",
        ("Alt+Up", "Alt+Down"),
    ),
)

EDT_SHORTCUTS: tuple[ShortcutSpec, ...] = (
    # Как у баз: Enter/Insert/Delete/F5 — keyPressEvent дерева (пустой sequences),  # noqa: RUF003
    # Ctrl+F — оболочка; QShortcut вьюхи регистрирует только Alt+Enter.
    ShortcutSpec("Ctrl+F", "Поиск (Базы и EDT)", ()),
    ShortcutSpec("Enter", "Открыть в EDT выбранную запись; в поиске — первую найденную", ()),
    ShortcutSpec("Alt+Enter", "Изменить запись или группу", ("Alt+Return", "Alt+Enter")),
    ShortcutSpec("Insert", "Добавить запись в группу текущей строки", ()),
    ShortcutSpec("Delete", "Удалить запись или группу (с подтверждением)", ()),  # noqa: RUF001
    ShortcutSpec("F5", "Обновить установки EDT и состояние записей", ()),
)


def window_shortcut_label(section_count: int) -> str:
    """Диапазон "Alt+1 … Alt+N" по числу разделов, а не литералом (задача 8, спека §2.2).

    Имена разделов живут в проводке окна (`ui/app.py`); копия в справочнике
    настроек стала бы второй правдой, расходящейся при первом же
    переименовании. Диапазон вместо этого строится из ЧИСЛА разделов —
    а девятый предел не превышается, даже если разделов больше: раздел
    после девятого сочетания уже не получает (`MainWindow.__init__`).
    """  # noqa: RUF002
    count = max(1, min(section_count, 9))
    return f"Alt+1 … Alt+{count}"


# Одна строка на всё окно, а не по разделу: сочетание общее для любого  # noqa: RUF003
# раздела рельсы, а не только «Базы» или «EDT» (в отличие от Ctrl+F выше,  # noqa: RUF003
# который несмотря на регистрацию в оболочке документирован внутри таблиц
# конкретных разделов — там он единственный такой).
#
# Спека §2.2 запрещает ровно одно: копировать сюда ИМЕНА разделов — они
# живут в проводке окна (`ui/app.py`) и разошлись бы со справочником при  # noqa: RUF003
# первом же переименовании. ЧИСЛО разделов — наоборот, ровно то, из чего
# диапазон обязан строиться (пример спеки на сегодняшних четырёх разделах:
# «Alt+1 … Alt+4»). `window_shortcut_label(9)` ниже — не диапазон для показа,
# а запасное значение по умолчанию потолком механизма: этот модуль не видит  # noqa: RUF003
# список разделов `ui/app.py` и не должен — настоящее число приходит после
# сборки окна вызовом `SettingsView.set_window_section_count(len(sections))`,
# тем же приёмом отложенной инъекции, что уже применяют `set_hotkey_handler`
# и `MainWindow.set_section_icon` в той же проводке.
WINDOW_SHORTCUTS: tuple[ShortcutSpec, ...] = (
    ShortcutSpec(
        window_shortcut_label(9),
        "Переход в раздел рельсы по его порядковому номеру",  # noqa: RUF001
        tuple(f"Alt+{number}" for number in range(1, 10)),
    ),
)
