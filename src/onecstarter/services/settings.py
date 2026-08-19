"""Настройки приложения: тема, поведение окна, глобальный хоткей, «Недавние».

Файл %APPDATA%\\OneCStarter\\settings.json, отдельный от bases.json намеренно:
тот при порче уезжает в .bad вместе со всем содержимым, и настройка темы
уехала бы с историей запусков, будучи ни при чём. Разные времена жизни
и разная частота записи — разные файлы.

Политика отказов мягче, чем у наших данных о базах: работа с settings.json
никогда не мешает работе программы. Нечитаемый или испорченный файл даёт
значения по умолчанию, незнакомое значение режима — AUTO. Ошибку записи
модуль не гасит: показать её обязан слой представления, иначе пользователь
решит, что выбор запомнен.

Автозапуск при входе в Windows здесь НЕ хранится: его истина — значение
в реестре (спека §3.1). Два источника истины разошлись бы при
переустановке или ручной правке реестра.

Схема остаётся 1 и при добавлении полей: новые ключи необязательны,
старый файл читается без миграции, а старая версия программы новый файл
не ломает. Bump схемы был бы строго хуже — старая версия увезла бы файл
в `.bad` и потеряла даже тему.
"""  # noqa: RUF002

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.services.hotkeys import format_hotkey, parse_hotkey

SCHEMA_VERSION = 1
DEFAULT_HOTKEY = "Ctrl+Alt+B"
DEFAULT_RECENT_LIMIT = 10
RECENT_MIN = 0
RECENT_MAX = 50

__all__ = [
    "DEFAULT_HOTKEY",
    "DEFAULT_RECENT_LIMIT",
    "RECENT_MAX",
    "RECENT_MIN",
    "SCHEMA_VERSION",
    "Settings",
    "ThemeMode",
    "load_settings",
    "save_settings",
]


class ThemeMode(Enum):
    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Settings:
    theme: ThemeMode = ThemeMode.AUTO
    close_to_tray: bool = True
    hotkey: str = DEFAULT_HOTKEY
    recent_limit: int = DEFAULT_RECENT_LIMIT


def load_settings(path: Path) -> Settings:
    """Прочитать настройки. Никогда не поднимает исключений."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings()
    except (OSError, UnicodeDecodeError):
        # Недоступен или не в UTF-8. В отличие от bases.json падать нельзя:  # noqa: RUF003
        # цена ошибки — забытый выбор темы, а не затёртая история запусков.  # noqa: RUF003
        return Settings()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ValueError("неподдерживаемая схема")
    except (ValueError, TypeError):
        _move_aside(path)
        return Settings()
    return Settings(
        theme=_theme_of(payload.get("theme")),
        close_to_tray=_bool_of(payload.get("close_to_tray")),
        hotkey=_hotkey_of(payload.get("hotkey")),
        recent_limit=_recent_of(payload.get("recent_limit")),
    )


def save_settings(path: Path, settings: Settings) -> None:
    """Записать настройки атомарно. `OSError` наружу — гасит вызывающий."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "theme": settings.theme.value,
        "close_to_tray": settings.close_to_tray,
        "hotkey": settings.hotkey,
        "recent_limit": settings.recent_limit,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, text.encode("utf-8"))


def _theme_of(value: Any) -> ThemeMode:
    """Незнакомое значение — не порча: более новая версия могла записать свой режим."""
    try:
        return ThemeMode(value)
    except ValueError:
        return ThemeMode.AUTO


def _bool_of(value: Any) -> bool:
    """Не-булево — не порча файла: дефолт поля, как у режима темы."""  # noqa: RUF002
    return value if isinstance(value, bool) else True


def _hotkey_of(value: Any) -> str:
    """Пустая строка — «выключен» (валидно). Непригодная — дефолт (спека §4.5).

    Годная строка возвращается канонизованной: иначе одно сочетание
    попадёт в файл двумя написаниями и сравнение «изменилось ли» соврёт.
    """
    if not isinstance(value, str):
        return DEFAULT_HOTKEY
    if not value.strip():
        return ""
    spec = parse_hotkey(value)
    return DEFAULT_HOTKEY if spec is None else format_hotkey(spec)


def _recent_of(value: Any) -> int:
    """Границы 0-50; не-целое — дефолт.

    `bool` отсекается первым: он подкласс `int`, и `true` в файле
    иначе прошёл бы единицей.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_RECENT_LIMIT
    return max(RECENT_MIN, min(RECENT_MAX, value))


def _move_aside(path: Path) -> None:
    """Убрать испорченный файл. Не вышло — и ладно: перезапишем поверх."""  # noqa: RUF002
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError:
        return
