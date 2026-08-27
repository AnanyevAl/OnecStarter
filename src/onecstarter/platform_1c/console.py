"""Чтение текущей зарегистрированной версии консоли администрирования кластера.

`.msc`-файл консоли один на все версии платформы — версия «консоли», которую
видит пользователь, это версия зарегистрированной `radmin.dll`, а не файл на
диске рядом с ней. Регистрация живёт в `HKLM\\SOFTWARE\\Classes\\CLSID` под
двумя стабильными GUID (`RADMIN_CLSIDS`) — сами GUID не меняются между
версиями платформы. Перещёлкивает оба CLSID **повышенный** `regsvr32 /s`
([Ф] Г2, 26.08.2026, `docs/research/t07-protocol.md`: замер — регистрация
руками заказчика из повышенной консоли; регистрация без повышения не
проверялась и в проде не нужна — приложение всегда повышает `regsvr32`
через UAC, §7). А вот ЧТЕНИЕ этих двух ключей повышения не требует: сами
GUID при смене версии не меняются, поэтому текущая версия консоли
определяется чтением `InprocServer32` (default-значение) только первого
CLSID из HKLM обычным пользователем — это и делает `registered_radmin_path`,
без UAC.

Перезапись поверх без `/u` работает ([Ф] Г2: повышенный `regsvr32 /s` другой
версии перещёлкнул оба CLSID без предварительного удаления старой) —
`register_arguments` поэтому строит ровно одну команду, без шага удаления.
"""  # noqa: RUF002

import winreg
from collections.abc import Callable
from pathlib import Path

__all__ = ["RADMIN_CLSIDS", "register_arguments", "registered_radmin_path"]

RADMIN_CLSIDS: tuple[str, str] = (
    "{803144C8-17E6-4926-86C5-C195B6D226D4}",
    "{A42674D4-2D97-4988-A81D-2C113CC42A95}",
)


def _winreg_read(subkey: str) -> str | None:
    """Настоящее чтение HKLM. Единственное место в модуле с `winreg`."""  # noqa: RUF002
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
            # "" — default-значение ключа; эквивалентно None в winreg (проверено
            # экспериментом на HKLM\SOFTWARE\Classes\.txt), но typeshed требует str.
            value, _kind = winreg.QueryValueEx(key, "")
    except FileNotFoundError:
        # Нет ключа — консоль не зарегистрирована.
        return None
    return value if isinstance(value, str) else None


def registered_radmin_path(
    read_value: Callable[[str], str | None] | None = None,
) -> Path | None:
    """Путь к текущей зарегистрированной `radmin.dll`; `None` — не зарегистрирована.

    `read_value` — инъекция для тестов: подаётся подключ под HKLM, ожидается
    default-значение или `None`. По умолчанию (боевой путь) читает настоящий
    реестр через `winreg`.
    """
    read = read_value if read_value is not None else _winreg_read
    subkey = f"SOFTWARE\\Classes\\CLSID\\{RADMIN_CLSIDS[0]}\\InprocServer32"
    value = read(subkey)
    return Path(value) if value else None


def register_arguments(dll: Path) -> str:
    """Аргументы `regsvr32` для регистрации `dll` — без `/u` ([Ф] Г2)."""
    return f'/s "{dll}"'
