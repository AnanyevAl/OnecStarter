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
    "DefaultClient",
    "Settings",
    "ThemeMode",
    "load_settings",
    "save_settings",
]


class ThemeMode(Enum):
    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"


class DefaultClient(Enum):
    """Чем запускать базу, когда клиент не указан в её записи (спека вехи §2).

    «Конфигуратора» и «Авто» здесь нет намеренно (спека §2.4): конфигуратор
    нельзя задать умолчанием, а «Авто» платформа отрабатывает сама через
    /AppAutoCheckMode, когда выбор не сделан явно ([Ф] T-02.6).
    """  # noqa: RUF002

    THIN = "thin"
    THICK = "thick"

    @property
    def default_app(self) -> str | None:
        """Что передать проводке в `Workspace.set_default_app`/`build_runtime`.

        `None` для тонкого: тонкий и есть поведение по умолчанию — запуск
        с /AppAutoCheckMode, как до вехи (спека §2.1, у существующих
        установок ничего не меняется). Для толстого — явное значение
        формата ключа `App`: такой клиент передаётся без /AppAutoCheckMode
        (решение заказчика 23.08.2026, спека §2.2).
        """  # noqa: RUF002
        return _APP_VALUES.get(self)


_APP_VALUES = {DefaultClient.THICK: "ThickClient"}


@dataclass(frozen=True)
class Settings:
    theme: ThemeMode = ThemeMode.AUTO
    close_to_tray: bool = True
    hotkey: str = DEFAULT_HOTKEY
    recent_limit: int = DEFAULT_RECENT_LIMIT
    default_client: DefaultClient = DefaultClient.THIN
    # Корень каталогов серверов (спека §3.5). Пустая строка — не задан; новый
    # профиль сервера в этом случае предлагает `<корень>\srv_<версия>`,
    # подставить которое диалогу профиля нечем. Путь не валидируется здесь —
    # несуществующий или недоступный каталог не порча ЭТОГО файла, диалог
    # профиля решает, что делать с плохим значением.  # noqa: RUF003
    servers_root: str = ""
    # T-11, п. 9 (решение заказчика 29.08.2026): успешный запуск базы прячет
    # окно в трей. Дефолт False — поведение существующих установок не меняется.
    # На запуск серверного профиля не действует (решение (а)); без трея  # noqa: RUF003
    # не действует (решение (б)) — это решает проводка ui/app.py, не модель.  # noqa: RUF003
    hide_on_launch: bool = False


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
        default_client=_client_of(payload.get("default_client")),
        servers_root=_servers_root_of(payload.get("servers_root")),
        hide_on_launch=_bool_of(payload.get("hide_on_launch"), default=False),
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
        "default_client": settings.default_client.value,
        "servers_root": settings.servers_root,
        "hide_on_launch": settings.hide_on_launch,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, text.encode("utf-8"))


def _theme_of(value: Any) -> ThemeMode:
    """Незнакомое значение — не порча: более новая версия могла записать свой режим."""
    try:
        return ThemeMode(value)
    except ValueError:
        return ThemeMode.AUTO


def _client_of(value: Any) -> DefaultClient:
    """Незнакомое значение — не порча: более новая версия могла записать своё."""
    try:
        return DefaultClient(value)
    except ValueError:
        return DefaultClient.THIN


def _servers_root_of(value: Any) -> str:
    """Не-строка — не порча файла: дефолт «корень не задан» (спека §3.5).

    Годная строка возвращается как есть, без валидации пути: проверка
    существования или доступности каталога — дело диалога профиля сервера,
    не этого модуля, и уж точно не повод унести settings.json в `.bad`.
    """  # noqa: RUF002
    return value if isinstance(value, str) else ""


def _bool_of(value: Any, *, default: bool = True) -> bool:
    """Не-булево — не порча файла: дефолт поля, как у режима темы."""  # noqa: RUF002
    return value if isinstance(value, bool) else default


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
    """Сверху — обрезание до RECENT_MAX, снизу — дефолт (решение заказчика 20.08.2026).

    Асимметрично намеренно: значение больше `RECENT_MAX` — пользователь явно
    хотел «много», обрезаем до максимума, это осмысленный ввод, не порча.
    Значение меньше `RECENT_MIN` (то есть отрицательное) — мягко в дефолт,
    НЕ в `RECENT_MIN` (`0`): `0` — осознанный выбор «не показывать ветку
    „Недавние" вовсе», и молча выдать его из битого файла означало бы
    подменить выбор пользователя видимым изменением поведения, которого он
    не совершал. `0`, прочитанный из файла, так и остаётся `0`.

    `bool` отсекается первым: он подкласс `int`, и `true` в файле
    иначе прошёл бы единицей.
    """  # noqa: RUF002
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_RECENT_LIMIT
    if value < RECENT_MIN:
        return DEFAULT_RECENT_LIMIT
    return min(RECENT_MAX, value)


def _move_aside(path: Path) -> None:
    """Убрать испорченный файл. Не вышло — и ладно: перезапишем поверх."""  # noqa: RUF002
    try:
        path.replace(path.with_name(path.name + ".bad"))
    except OSError:
        return
