"""Автозапуск: команда и операции над значением реестра.

Реестр — поддельный: живой HKCU тесты не трогают (спека §8), тот же приём,
что с инъекцией user32 в глобальном хоткее.
"""  # noqa: RUF002

import pytest

from onecstarter.services.autostart import (
    AUTOSTART_FLAG,
    RUN_KEY,
    VALUE_NAME,
    autostart_command,
    disable,
    enable,
    is_enabled,
)


class FakeRegistry:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.deleted: list[str] = []

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, data: str) -> None:
        self.values[name] = data

    def delete(self, name: str) -> None:
        self.deleted.append(name)
        self.values.pop(name, None)


class BrokenRegistry(FakeRegistry):
    def write(self, name: str, data: str) -> None:
        raise PermissionError(5, "отказано в доступе")

    def delete(self, name: str) -> None:
        raise PermissionError(5, "отказано в доступе")


def test_key_and_value_names_are_the_documented_ones() -> None:
    assert RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert VALUE_NAME == "OneCStarter"
    assert AUTOSTART_FLAG == "--autostart"


def test_command_quotes_path_and_adds_flag() -> None:
    """Путь в кавычках: за ним идёт аргумент, а сам путь содержит пробелы (спека §3.2)."""  # noqa: RUF002
    assert (
        autostart_command(r"C:\Program Files\OneCStarter\OneCStarter.exe")
        == r'"C:\Program Files\OneCStarter\OneCStarter.exe" --autostart'
    )


def test_disabled_when_value_absent() -> None:
    assert is_enabled(FakeRegistry()) is False


def test_enabled_when_value_present() -> None:
    registry = FakeRegistry({VALUE_NAME: r'"C:\other\OneCStarter.exe" --autostart'})
    assert is_enabled(registry) is True


def test_enable_writes_command_of_this_copy() -> None:
    registry = FakeRegistry({VALUE_NAME: r'"C:\old\OneCStarter.exe" --autostart'})
    enable(registry, r"C:\new\OneCStarter.exe")
    assert registry.values[VALUE_NAME] == r'"C:\new\OneCStarter.exe" --autostart'


def test_disable_removes_value() -> None:
    registry = FakeRegistry({VALUE_NAME: "что угодно"})
    disable(registry)
    assert registry.deleted == [VALUE_NAME]
    assert is_enabled(registry) is False


def test_disable_of_absent_value_is_quiet() -> None:
    """Выключить выключённое — не ошибка: значения и так нет."""
    registry = FakeRegistry()
    disable(registry)
    assert is_enabled(registry) is False


def test_write_failure_reaches_caller() -> None:
    """Отказ реестра гасит слой представления, а не мы (спека §3.6).

    Проглотив OSError здесь, мы показали бы пользователю включённый
    тумблер при невыполненной записи.
    """  # noqa: RUF002
    with pytest.raises(OSError):
        enable(BrokenRegistry(), r"C:\OneCStarter.exe")
    with pytest.raises(OSError):
        disable(BrokenRegistry({VALUE_NAME: "x"}))
