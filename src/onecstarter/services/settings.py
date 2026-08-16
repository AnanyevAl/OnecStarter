"""Настройки приложения. Сегодня — только режим темы.

Файл %APPDATA%\\OneCStarter\\settings.json, отдельный от bases.json намеренно:
тот при порче уезжает в .bad вместе со всем содержимым, и настройка темы
уехала бы с историей запусков, будучи ни при чём. Разные времена жизни
и разная частота записи — разные файлы.

Политика отказов мягче, чем у наших данных о базах: работа с settings.json
никогда не мешает работе программы. Нечитаемый или испорченный файл даёт
значения по умолчанию, незнакомое значение режима — AUTO. Ошибку записи
модуль не гасит: показать её обязан слой представления, иначе пользователь
решит, что выбор запомнен.
"""  # noqa: RUF002

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from onecstarter.config.atomic import atomic_write

SCHEMA_VERSION = 1

__all__ = [
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
    return Settings(theme=_theme_of(payload.get("theme")))


def save_settings(path: Path, settings: Settings) -> None:
    """Записать настройки атомарно. `OSError` наружу — гасит вызывающий."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA_VERSION, "theme": settings.theme.value}
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, text.encode("utf-8"))


def _theme_of(value: Any) -> ThemeMode:
    """Незнакомое значение — не порча: более новая версия могла записать свой режим."""
    try:
        return ThemeMode(value)
    except ValueError:
        return ThemeMode.AUTO


def _move_aside(path: Path) -> None:
    """Убрать испорченный файл. Не вышло — и ладно: перезапишем поверх."""  # noqa: RUF002
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError:
        return
