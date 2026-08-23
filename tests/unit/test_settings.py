"""Настройки приложения: чтение и запись settings.json."""

import json
from pathlib import Path

import pytest

from onecstarter.services.settings import (
    DEFAULT_HOTKEY,
    DEFAULT_RECENT_LIMIT,
    SCHEMA_VERSION,
    DefaultClient,
    Settings,
    ThemeMode,
    load_settings,
    save_settings,
)


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "settings.json") == Settings(theme=ThemeMode.AUTO)


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.LIGHT))
    assert load_settings(path) == Settings(theme=ThemeMode.LIGHT)


def test_schema_is_written(tmp_path: Path) -> None:
    """Файл несёт все шесть ключей, включая номер схемы.

    Долг №3 вехи закрыт здесь: соседний `test_all_fields_are_written` проверял
    ровно то же самое на дефолтных настройках и удалён. Разница была
    в единственном поле темы, а утверждение — одно и то же: `save_settings`
    пишет полный состав, а не только изменённое.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.DARK))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "schema": SCHEMA_VERSION,
        "theme": "dark",
        "close_to_tray": True,
        "hotkey": "Ctrl+Alt+B",
        "recent_limit": 10,
        "default_client": "thin",
    }


def test_unknown_theme_value_falls_back_to_auto(tmp_path: Path) -> None:
    """Совместимость вперёд: незнакомое значение — не порча файла.

    Более новая версия могла записать режим, которого мы не знаем. Уносить
    за это весь файл в .bad значило бы терять настройки при откате версии.
    """
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "theme": "solarized"}), encoding="utf-8")
    assert load_settings(path).theme is ThemeMode.AUTO
    assert not path.with_name("settings.json.bad").exists()


def test_corrupt_file_moves_aside_and_starts_clean(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{не json", encoding="utf-8")
    assert load_settings(path) == Settings()
    assert path.with_name("settings.json.bad").read_text(encoding="utf-8") == "{не json"


def test_unreadable_file_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настройки не смеют мешать старту — в отличие от bases.json.

    У load_user_data недоступный файл поднимает UserDataUnavailableError:
    подмена пустыми данными затёрла бы историю запусков. Здесь цена ошибки
    другая — теряется выбор темы, — и падать из-за неё приложению нельзя.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "theme": "light"}), encoding="utf-8")

    original = Path.read_text

    def refuse(self: Path, **kwargs: object) -> str:
        if self == path:
            raise PermissionError(13, "занят другим процессом")
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", refuse)
    assert load_settings(path) == Settings(theme=ThemeMode.AUTO)


def test_save_reports_failure(tmp_path: Path) -> None:
    """Отказ записи виден вызывающему: тему покажем, но соврать «запомнили» нельзя.

    Финальное ревью, I11: препятствием был родитель целевого пути (файл
    вместо каталога), и `OSError` прилетала из `path.parent.mkdir(...)` —
    первой же строки `save_settings`. До `atomic_write` дело не доходило
    вовсе, поэтому ни отключение атомарной записи, ни проглатывание
    `OSError` внутри неё тест бы не заметил, а `ThemeController.
    last_save_error` остался бы пустым и пользователь получил бы молчаливое
    «запомнили». Препятствие теперь — сам целевой путь при живом родителе:
    каталог с именем `settings.json`, поверх которого `atomic_write`
    не сможет переставить временный файл.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.mkdir()

    with pytest.raises(OSError):
        save_settings(path, Settings())

    # Родитель существует и доступен: отказ пришёл именно с записи, а не  # noqa: RUF003
    # с создания каталога.  # noqa: RUF003
    assert path.parent.is_dir()


def test_defaults_of_new_fields() -> None:
    """Дефолты не меняют поведение работающей программы (спека §1)."""
    settings = Settings()
    assert settings.close_to_tray is True
    assert settings.hotkey == DEFAULT_HOTKEY
    assert settings.recent_limit == DEFAULT_RECENT_LIMIT
    assert DEFAULT_RECENT_LIMIT == 10
    assert DEFAULT_HOTKEY == "Ctrl+Alt+B"


def test_old_file_without_new_keys_reads_with_defaults(tmp_path: Path) -> None:
    """Файл прошлой версии читается без миграции — схема та же (спека §6.1)."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "theme": "light"}), encoding="utf-8")
    assert load_settings(path) == Settings(theme=ThemeMode.LIGHT)
    assert not path.with_name("settings.json.bad").exists()


def test_round_trip_keeps_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings(
        theme=ThemeMode.DARK, close_to_tray=False, hotkey="Win+F9", recent_limit=0
    )
    save_settings(path, settings)
    assert load_settings(path) == settings


@pytest.mark.parametrize("value", ["да", 1, None, [], {}])
def test_broken_close_to_tray_falls_back(tmp_path: Path, value: object) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema": 1, "close_to_tray": value}), encoding="utf-8"
    )
    assert load_settings(path).close_to_tray is True


def test_empty_hotkey_means_disabled_not_default(tmp_path: Path) -> None:
    """Пустая строка — валидное «выключен» (спека §4.5), а не повод к дефолту."""  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "hotkey": "   "}), encoding="utf-8")
    assert load_settings(path).hotkey == ""


@pytest.mark.parametrize("value", ["Shift+B", "мусор", "B", 42, None])
def test_unusable_hotkey_falls_back_to_default(tmp_path: Path, value: object) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "hotkey": value}), encoding="utf-8")
    assert load_settings(path).hotkey == DEFAULT_HOTKEY


def test_hotkey_is_canonicalized_on_read(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "hotkey": "alt+ctrl+b"}), encoding="utf-8")
    assert load_settings(path).hotkey == "Ctrl+Alt+B"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), (50, 50), (7, 7), (-3, 10), (999, 50), (10.5, 10), ("10", 10), (True, 10)],
)
def test_recent_limit_is_clamped(tmp_path: Path, value: object, expected: int) -> None:
    """Сверху — обрезание до 50, снизу — дефолт (решение заказчика 20.08.2026).

    Асимметрично намеренно: `999` — пользователь явно хотел «много», обрезаем
    до максимума, это осмысленный ввод. `-3` — испорченный файл, и подставлять
    оттуда `0` значило бы выдать поломку за осознанный выбор пользователя —
    `0` сам по себе валиден («не показывать ветку „Недавние" вовсе») и не
    должен всплывать из битого значения молча; дефолт честнее. `0` из файла
    остаётся `0` (первый кейс таблицы). `True` проверяется отдельно: в Python
    `bool` — подкласс `int`, и без явной проверки `{"recent_limit": true}`
    прошло бы как 1.
    """  # noqa: RUF002
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema": 1, "recent_limit": value}), encoding="utf-8")
    assert load_settings(path).recent_limit == expected


class TestDefaultClient:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        save_settings(path, Settings(default_client=DefaultClient.THICK))
        assert load_settings(path).default_client is DefaultClient.THICK

    def test_missing_key_is_thin(self, tmp_path: Path) -> None:
        """Старый файл без ключа читается без миграции (докстринг модуля)."""
        path = tmp_path / "settings.json"
        path.write_text('{"schema": 1}', encoding="utf-8")
        assert load_settings(path).default_client is DefaultClient.THIN

    def test_unknown_value_is_thin(self, tmp_path: Path) -> None:
        """Незнакомое значение — не порча: дефолт поля, как у режима темы."""  # noqa: RUF002
        path = tmp_path / "settings.json"
        path.write_text('{"schema": 1, "default_client": "designer"}', encoding="utf-8")
        assert load_settings(path).default_client is DefaultClient.THIN

    def test_default_app_none_for_thin_means_no_default(self) -> None:
        """Тонкий — «умолчания нет»: проводка передаёт None, поведение как до вехи.

        Явное значение здесь дало бы choose_client третий аргумент, и клиент
        из настройки пошёл бы БЕЗ /AppAutoCheckMode (решение заказчика
        23.08.2026, спека §2.2) — для тонкого-по-умолчанию это изменило бы
        поведение существующих установок, чего спека §2.1 запрещает.
        """
        assert DefaultClient.THIN.default_app is None

    def test_default_app_thick_matches_v8i_app_key(self) -> None:
        """Толстый — явное значение в формате ключа `App`, его ждёт `choose_client`."""  # noqa: RUF002
        assert DefaultClient.THICK.default_app == "ThickClient"
