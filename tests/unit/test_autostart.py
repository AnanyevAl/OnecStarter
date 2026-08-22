"""Автозапуск: команда и операции над значением реестра.

Реестр — поддельный: живой HKCU тесты не трогают (спека §8), тот же приём,
что с инъекцией user32 в глобальном хоткее.
"""  # noqa: RUF002

import winreg

import pytest

from onecstarter.services.autostart import (
    AUTOSTART_FLAG,
    RUN_KEY,
    VALUE_NAME,
    NullRegistry,
    WindowsRegistry,
    autostart_command,
    disable,
    enable,
    is_enabled,
)


class FakeRegistry:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.deleted: list[str] = []
        self.written: list[tuple[str, str]] = []

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, data: str) -> None:
        self.written.append((name, data))
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


@pytest.mark.parametrize("data", ["", "   ", "\t", "\r\n"])
def test_empty_value_is_not_autostart(data: str) -> None:
    """Пустое значение в Run — не включённый автозапуск (находка шага А3, 21.08.2026).

    Не гипотетический случай, а измеренный: установщик версии 0.1.0 сам создавал
    в `HKCU\\...\\Run` значение `OneCStarter` длиной 0 символов. `ValueType: string`
    без `ValueData` создаёт пустую строку, а флаг `dontcreatekey` этому не мешает —
    он про КЛЮЧ (**[из документации Inno Setup]** «Setup will not attempt to create
    the key or any value if the key did not already exist»), а ключ `Run` существует
    на любой машине всегда.

    Цена ошибки — ложь о состоянии системы, а не мусор в реестре: пока `is_enabled`
    отвечал «включено» на любое непустое-по-факту-существования значение, раздел
    «Настройки» показывал автозапуск включённым, хотя Windows при входе выполнять
    было нечего. Пользователь, видя «включено», не стал бы включать — и расхождение
    не вылечилось бы никогда (тот самый сценарий, о котором предупреждает докстринг
    `is_enabled`).

    Пробельные строки здесь не педантизм: `write` принимает что угодно, а чужой
    установщик или ручная правка реестра могут оставить и такое.
    """  # noqa: RUF002
    registry = FakeRegistry({VALUE_NAME: data})
    assert is_enabled(registry) is False
    # Чтение не смеет чинить реестр: «самолечение» пустого значения превратило
    # бы показ состояния в запись в HKCU при каждом открытии раздела, которой
    # пользователь не просил. Мутация с таким удалением переживала набор  # noqa: RUF003
    # (разбор 22.08.2026), пока эта строка не появилась.
    assert registry.values == {VALUE_NAME: data}
    assert registry.written == []
    assert registry.deleted == []


@pytest.mark.parametrize(
    "data",
    [
        r'"C:\other\OneCStarter.exe" --autostart',  # наш формат
        r'"C:\other\OneCStarter.exe"',              # чужой писатель, без флага
        r"C:\o\s.exe",                             # без кавычек, коротко
        "x",                                        # короче любого мыслимого порога
    ],
)
def test_any_non_blank_value_is_autostart(data: str) -> None:
    """Включено — любое непустое значение, в какой бы форме оно ни было записано.

    Находка мутационной проверки 22.08.2026: тест «включено» подавал ровно одно
    значение — наше собственное, с путём в кавычках и флагом. Из-за этого любое
    лишнее условие на СОДЕРЖИМОЕ проходило незамеченным: мутации
    `and AUTOSTART_FLAG in value` и `and len(value) > 4` пережили весь набор.

    Цена такой дыры — зеркало только что закрытого дефекта. Значение без флага
    Windows исполняет: программа стартует при входе, а тумблер показывал бы
    «выключено». Ни путь, ни флаг не сверяются намеренно (докстринг `is_enabled`).
    """  # noqa: RUF002
    registry = FakeRegistry({VALUE_NAME: data})
    assert is_enabled(registry) is True
    # Та же сверка, что в тесте отказа, и по той же причине: защита от побочных  # noqa: RUF003
    # эффектов, поставленная только в одну ветку, оставляет открытой вторую —
    # а именно непустая и срабатывает на живой машине при каждом открытии  # noqa: RUF003
    # раздела (находка мутационной проверки 22.08.2026).
    assert registry.values == {VALUE_NAME: data}
    assert registry.written == []
    assert registry.deleted == []


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


def test_null_registry_reports_autostart_off() -> None:
    """Реестр-заглушка для самопроверки сборки: автозапуска нет (долг №8).

    `run_smoke` поднимает настоящее окно, а `SettingsView` читает реестр прямо
    в конструкторе. С настоящим `WindowsRegistry` самопроверка собранного
    экземпляра зависела бы от состояния той машины, где идёт сборка: результат
    smoke менялся бы от того, включён ли автозапуск у сборщика.
    """  # noqa: RUF002
    assert is_enabled(NullRegistry()) is False
    assert NullRegistry().read(VALUE_NAME) is None


@pytest.mark.parametrize("action", ["write", "delete"])
def test_null_registry_refuses_to_change_anything(action: str) -> None:
    """Молчаливая заглушка хуже отсутствующей: изменение обязано быть слышным.

    Самопроверка тумблера не трогает, но если однажды тронет — правильный
    исход `run_smoke` красный, а не «всё хорошо, только ничего не записалось».
    """  # noqa: RUF002
    registry = NullRegistry()
    with pytest.raises(RuntimeError, match="самопроверк"):
        if action == "write":
            registry.write(VALUE_NAME, "что угодно")
        else:
            registry.delete(VALUE_NAME)


class _FakeKey:
    """Ключ реестра как контекстный менеджер — `winreg` отдаёт именно такой."""

    def __init__(self, store: dict[str, object]) -> None:
        self.store = store

    def __enter__(self) -> "_FakeKey":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _winreg_stub(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, object], *, key_exists: bool = True
) -> dict[str, object]:
    """Подменить функции `winreg`: живой HKCU в тестах неприкосновенен.

    Патчится сам `winreg`, а не атрибут модуля `autostart`: тот делает
    `import winreg` и зовёт функции через объект модуля, так что это один
    и тот же объект — а обращение через чужой модуль `mypy` в strict-режиме
    справедливо не пропускает.
    """  # noqa: RUF002
    opened: list[int] = []

    def open_key(
        root: object, path: str, _reserved: int = 0, access: int = winreg.KEY_READ
    ) -> _FakeKey:
        # Куст и путь проверяются здесь, а не «где-нибудь»: подделка, молча  # noqa: RUF003
        # принимающая любой аргумент, пропустила бы чтение из HKLM — там наше
        # значение чужое, а запись потребовала бы прав администратора, чего  # noqa: RUF003
        # модуль явно не требует (находка мутационной проверки 22.08.2026).
        assert root == winreg.HKEY_CURRENT_USER, "автозапуск живёт в HKCU"
        assert path == RUN_KEY
        if not key_exists:
            raise FileNotFoundError(2, "нет ключа")
        opened.append(access)
        return _FakeKey(values)

    def query(key: _FakeKey, name: str) -> tuple[object, int]:
        if name not in key.store:
            raise FileNotFoundError(2, "нет значения")
        return key.store[name], 1

    def create_key(root: object, path: str, _reserved: int = 0, access: int = 0) -> _FakeKey:
        assert root == winreg.HKEY_CURRENT_USER, "автозапуск живёт в HKCU"
        assert path == RUN_KEY
        # Флаг доступа — не украшение: с KEY_READ живой реестр отдал бы  # noqa: RUF003
        # PermissionError при первом же включении тумблера, а подделка,  # noqa: RUF003
        # принимающая любой `*args`, этого не замечала (находка 22.08.2026).
        assert access & winreg.KEY_SET_VALUE, "запись требует KEY_SET_VALUE"
        return _FakeKey(values)

    def set_value(key: _FakeKey, name: str, _r: int, kind: int, data: str) -> None:
        # Тип значения — измеренный факт (докстринг модуля: **[Проверено,
        # 19.08.2026]** все значения ключа Run — REG_SZ), и до сих пор его  # noqa: RUF003
        # не удерживал ни один тест. REG_DWORD со строкой упал бы TypeError  # noqa: RUF003
        # при первом включении автозапуска в собранном экземпляре.
        assert kind == winreg.REG_SZ, "значения ключа Run — строки"
        key.store[name] = data

    def delete_value(key: _FakeKey, name: str) -> None:
        if name not in key.store:
            raise FileNotFoundError(2, "нет значения")
        del key.store[name]

    # Остальные функции модуля запираются: мутация, позвавшая неперехваченную
    # (`DeleteKey` разрушителен), ушла бы в живой HKCU машины разработчика.
    for name in ("DeleteKey", "DeleteKeyEx", "SetValue", "EnumValue", "EnumKey"):
        if hasattr(winreg, name):
            monkeypatch.setattr(winreg, name, _forbidden(name))

    monkeypatch.setattr(winreg, "OpenKey", open_key)
    monkeypatch.setattr(winreg, "QueryValueEx", query)
    monkeypatch.setattr(winreg, "CreateKeyEx", create_key)
    monkeypatch.setattr(winreg, "SetValueEx", set_value)
    monkeypatch.setattr(winreg, "DeleteValue", delete_value)
    return values


def _forbidden(name: str) -> object:
    def guard(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(f"тест полез в живой реестр: {name}")

    return guard


def test_windows_registry_reads_string_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Единственная реализация поверх `winreg` до сих пор не была покрыта вовсе.

    Долг, добавленный финальным ревью ветки 22.08.2026: `isinstance(value, str)`
    и глушение `FileNotFoundError` в `WindowsRegistry` не удерживались ничем.
    Живой `HKCU` тесты не трогают (спека §8) — подменяется сам модуль `winreg`.
    """
    _winreg_stub(monkeypatch, {VALUE_NAME: "полезная строка"})
    assert WindowsRegistry().read(VALUE_NAME) == "полезная строка"


@pytest.mark.parametrize("kind", [123, b"\x01\x02", ["список"]])
def test_windows_registry_ignores_non_string_value(
    kind: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Нестроковое значение под нашим именем — не автозапуск, а чужой мусор.

    `REG_DWORD` под именем `OneCStarter` мог бы прийти от чужой программы или
    кривой правки. Без проверки типа он утёк бы в `is_enabled` и дальше
    в сравнение строк — вместо честного «выключено» получили бы падение
    в разделе «Настройки».
    """  # noqa: RUF002
    _winreg_stub(monkeypatch, {VALUE_NAME: kind})
    assert WindowsRegistry().read(VALUE_NAME) is None


@pytest.mark.parametrize("key_exists", [True, False])
def test_windows_registry_read_of_missing_value_is_quiet(
    key_exists: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Нет значения — обычное «выключено», а не ошибка. И нет самого ключа — тоже.

    Две разные причины `FileNotFoundError` (нет ключа `Run`, нет значения в нём)
    обязаны давать один ответ: автозапуска нет. Иначе на машине без ключа
    раздел показывал бы ошибку чтения там, где всё в порядке.
    """  # noqa: RUF002
    _winreg_stub(monkeypatch, {}, key_exists=key_exists)
    assert WindowsRegistry().read(VALUE_NAME) is None


def test_windows_registry_write_then_read(monkeypatch: pytest.MonkeyPatch) -> None:
    values = _winreg_stub(monkeypatch, {})
    WindowsRegistry().write(VALUE_NAME, "команда")
    assert values == {VALUE_NAME: "команда"}
    assert WindowsRegistry().read(VALUE_NAME) == "команда"


def test_windows_registry_delete_removes_value(monkeypatch: pytest.MonkeyPatch) -> None:
    values = _winreg_stub(monkeypatch, {VALUE_NAME: "команда"})
    WindowsRegistry().delete(VALUE_NAME)
    assert values == {}


@pytest.mark.parametrize("key_exists", [True, False])
def test_windows_registry_delete_of_absent_value_is_quiet(
    key_exists: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Выключить выключённое — не ошибка (докстринг `delete`), при любой причине.

    Тот же класс, что и у чтения: ключа нет или значения в нём нет — исход
    один. Без этого выключение тумблера на чистой машине падало бы наружу
    и показывало пользователю ошибку вместо «уже выключено».
    """  # noqa: RUF002
    _winreg_stub(monkeypatch, {}, key_exists=key_exists)
    WindowsRegistry().delete(VALUE_NAME)


def test_windows_registry_read_does_not_swallow_other_errors(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Отказ в доступе — не «выключено»: спека §3.6 требует показать причину.

    Глушится ровно `FileNotFoundError`. `PermissionError` обязан дойти до
    вьюхи, которая запирает тумблер и пишет текст ошибки — молча показать
    «выключено» значило бы соврать о состоянии, которого мы не знаем.
    """  # noqa: RUF002
    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(5, "отказано в доступе")

    monkeypatch.setattr(winreg, "OpenKey", denied)
    with pytest.raises(PermissionError):
        WindowsRegistry().read(VALUE_NAME)


def test_windows_registry_delete_does_not_swallow_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отказ в доступе при удалении обязан дойти до вьюхи (спека §3.6).

    Симметрия к тесту чтения, и она не formальность: `delete` глушит
    `FileNotFoundError` («выключить выключённое — не ошибка»), а мутация,
    расширяющая перехват до `Exception`, переживала набор. Последствие —
    выключение тумблера падает в HKCU, `_choose_autostart` не видит `OSError`,
    и пользователь получает «выключено» вместо причины отказа.
    """  # noqa: RUF002

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(5, "отказано в доступе")

    monkeypatch.setattr(winreg, "OpenKey", denied)
    with pytest.raises(PermissionError):
        WindowsRegistry().delete(VALUE_NAME)


def test_windows_registry_opens_the_key_for_writing_when_deleting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Удаление открывает ключ на запись, а не на чтение.

    Мутация `KEY_SET_VALUE` → `KEY_READ` в `delete` переживала набор: подделка
    принимала любой флаг доступа молча. На живом реестре это `PermissionError`
    при первом же выключении тумблера — то есть отказ там, где спека обещает
    тихий успех.
    """  # noqa: RUF002
    seen: list[int] = []

    class _Key:
        def __enter__(self) -> "_Key":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def open_key(_root: object, _path: str, _reserved: int = 0, access: int = 0) -> _Key:
        seen.append(access)
        return _Key()

    monkeypatch.setattr(winreg, "OpenKey", open_key)
    monkeypatch.setattr(winreg, "DeleteValue", lambda _key, _name: None)

    WindowsRegistry().delete(VALUE_NAME)

    assert seen and seen[0] & winreg.KEY_SET_VALUE
