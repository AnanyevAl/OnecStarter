"""Настройки приложения: чтение и запись settings.json."""

import json
from pathlib import Path

import pytest

from onecstarter.services.settings import (
    SCHEMA_VERSION,
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
    path = tmp_path / "settings.json"
    save_settings(path, Settings(theme=ThemeMode.DARK))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"schema": SCHEMA_VERSION, "theme": "dark"}


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
