"""Автозапуск при входе в Windows: значение в HKCU\\...\\Run.

Истина об автозапуске — реестр, а не `settings.json` (спека §3.1): два
источника разошлись бы при переустановке или ручной правке реестра,
и тумблер врал бы либо файлу, либо системе.

**[Проверено, 19.08.2026, машина заказчика]** Значения ключа Run — `REG_SZ`;
путь берётся в кавычки, когда за ним идут аргументы. Наш случай требует
кавычек: за путём идёт `--autostart`, а сам путь содержит пробелы.
**[Из документации Microsoft]** Значения `HKCU\\...\\Run` исполняются при
входе пользователя; прав администратора запись в HKCU не требует.

Реестр подаётся протоколом `Registry`, а не зовётся напрямую: тесты
не смеют трогать живой HKCU (тот же приём, что инъекция user32
в `ui/hotkey.py`). Единственная реализация поверх `winreg` — `WindowsRegistry`.

`OSError` наружу не гасится: тумблер обязан вернуться к фактическому
состоянию, а причина — попасть на экран (спека §3.6).
"""  # noqa: RUF002

import winreg
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OneCStarter"
AUTOSTART_FLAG = "--autostart"

__all__ = [
    "AUTOSTART_FLAG",
    "RUN_KEY",
    "VALUE_NAME",
    "Registry",
    "WindowsRegistry",
    "autostart_command",
    "disable",
    "enable",
    "is_enabled",
]


class Registry(Protocol):
    def read(self, name: str) -> str | None: ...

    def write(self, name: str, data: str) -> None: ...

    def delete(self, name: str) -> None: ...


class WindowsRegistry:
    """Настоящий `HKCU\\...\\Run`. Единственное место с `winreg`."""  # noqa: RUF002

    def read(self, name: str) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            # Нет ключа или нет значения — обычное «автозапуск выключен».
            return None
        return value if isinstance(value, str) else None

    def write(self, name: str, data: str) -> None:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, data)

    def delete(self, name: str) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            # Выключить выключённое — не ошибка.
            return


def autostart_command(executable: str) -> str:
    return f'"{executable}" {AUTOSTART_FLAG}'


def is_enabled(registry: Registry) -> bool:
    """Есть ли наше значение в Run.

    Сравнения с путём текущего экземпляра намеренно нет: значение,
    целящее в другую копию, — это всё равно «OneCStarter стартует при
    входе», и показать «выключено» значило бы соврать о системе.

    Расхождение путей (переустановка в другой каталог без деинсталляции)
    само НЕ лечится (находка финального ревью ветки, п. 8, 20.08.2026):
    тумблер уже показывает «включено», и у пользователя нет повода его
    переключить — самолечение наступило бы только первым включением,
    которого никто не совершит. `Run` при этом продолжает целить в стёртый
    exe, Windows ругается при каждом входе, а раздел молчит, что всё хорошо.
    Основной путь закрывает штатный `uninsdeletevalue` установщика (Task 10,
    `build/installer.iss`) — он удаляет значение при деинсталляции; сверка
    путей между `Run` и текущим экземпляром — отдельное решение, которого
    никто не принимал.
    """  # noqa: RUF002
    return registry.read(VALUE_NAME) is not None


def enable(registry: Registry, executable: str) -> None:
    registry.write(VALUE_NAME, autostart_command(executable))


def disable(registry: Registry) -> None:
    registry.delete(VALUE_NAME)
