"""Разбор аргументов точки входа: режим `--ib-name` против обычного окна.

Живёт в unit-тестах, а не в `tests/ui/`, намеренно: разбор аргументов
обязан оставаться проверяемым без Qt, поэтому `onecstarter.__main__`
импортирует `ui.app` внутри функции, а не на уровне модуля.
"""  # noqa: RUF002

import logging
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from onecstarter.__main__ import has_autostart_flag, main, parse_ib_name, parse_smoke_dir


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], None),
        (["--ib-name", "Демо"], "Демо"),
        (["--ib-name=Демо"], "Демо"),
        (["--ib-name", "Демо Розница"], "Демо Розница"),
        (["--ib-name=Демо Розница"], "Демо Розница"),
        (["--ib-name", "--ib-name"], "--ib-name"),
        (["/IBName", "Демо"], None),
    ],
)
def test_parse_ib_name(argv: list[str], expected: str | None) -> None:
    assert parse_ib_name(argv) == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--smoke", r"C:\tmp"], r"C:\tmp"),
        ([r"--smoke=C:\tmp"], r"C:\tmp"),
        (["--smoke"], ""),
        ([], None),
        (["--ib-name", "Демо"], None),
    ],
)
def test_parse_smoke_dir(argv: list[str], expected: str | None) -> None:
    assert parse_smoke_dir(argv) == expected


def test_option_without_value_is_not_the_same_as_absent() -> None:
    """Ключ без значения даёт пустую строку, а не `None`.

    «Запустить неизвестно что» и «показать окно» — разные намерения.
    Молча открыть окно значило бы спрятать от пользователя опечатку
    в ярлыке: он ждал запуска базы, а получил окно и никакой диагностики.
    """  # noqa: RUF002
    assert parse_ib_name(["--ib-name"]) == ""
    assert parse_ib_name([]) is None


def test_autostart_flag_detected() -> None:
    assert has_autostart_flag(["--autostart"]) is True
    assert has_autostart_flag(["--autostart", "--ib-name", "Демо"]) is True


def test_autostart_flag_absent() -> None:
    assert has_autostart_flag([]) is False
    assert has_autostart_flag(["--ib-name", "Демо"]) is False
    assert has_autostart_flag(["--autostart-something"]) is False


# -- развилка `main`: разбор → нужный режим (финальное ревью, I3) -------------
#
# `parse_ib_name` покрыт таблично, а сама развилка — нет: `main` мог бы звать  # noqa: RUF003
# не тот режим или не звать никакого, и набор остался бы зелёным. Подменяются
# именно атрибуты модуля `onecstarter.ui.app` — `__main__.main` импортирует
# их внутри функции (Qt не должен требоваться для разбора аргументов),
# поэтому подмена доходит до настоящего вызова.


class _AppStub(types.ModuleType):
    """Подставной `onecstarter.ui.app`: записывает вызовы, ничего не рисует.

    Ставится в `sys.modules` целиком, а не подменяется атрибутами
    настоящего модуля, ради инварианта этого файла: разбор аргументов
    и развилка режимов обязаны проверяться **без Qt** (см. докстринг
    модуля). Настоящий `ui.app` тянет `PySide6` одним своим импортом,
    а `run_launch` полез бы в реальный `%APPDATA%` за списком баз.

    Подмена доходит до вызова потому, что `__main__.main` импортирует
    оба имени внутри функции, а не на уровне модуля.
    """  # noqa: RUF002

    def __init__(self) -> None:
        super().__init__("onecstarter.ui.app")
        self.window_calls: list[tuple[Any, ...]] = []
        self.launch_calls: list[tuple[Any, ...]] = []
        self.smoke_calls: list[tuple[Any, ...]] = []

    def main(self, *, start_hidden: bool = False) -> int:
        self.window_calls.append((start_hidden,))
        return 0

    def run_launch(self, name: str, env: Any) -> int:
        self.launch_calls.append((name, env))
        # Не 0 и не 1: код возврата обязан прийти от режима, а не быть  # noqa: RUF003
        # «успехом по умолчанию» или совпасть с кодом отказа развилки.  # noqa: RUF003
        return 3

    def run_smoke(self, target_dir: str, env: Any) -> int:
        self.smoke_calls.append((target_dir, env))
        # Своё число, отличное от кодов других режимов и от 0/1 — та же
        # причина, что у run_launch выше.  # noqa: RUF003
        return 5


@pytest.fixture
def app_stub(monkeypatch: pytest.MonkeyPatch) -> _AppStub:
    stub = _AppStub()
    monkeypatch.setitem(sys.modules, "onecstarter.ui.app", stub)
    return stub


def test_main_without_arguments_opens_the_window(app_stub: _AppStub) -> None:
    assert main([]) == 0
    assert app_stub.window_calls == [(False,)]
    assert app_stub.launch_calls == []


def test_main_with_autostart_opens_the_window_hidden(app_stub: _AppStub) -> None:
    """`--autostart` доходит до `show_window(start_hidden=True)` (спека §3.4).

    Без этой проводки автозапуск ничем не отличался бы от обычного окна:
    `has_autostart_flag` покрыт табличными тестами выше, но развилка
    `_dispatch`, которая передаёт его результат дальше, — нет.
    """  # noqa: RUF002
    assert main(["--autostart"]) == 0
    assert app_stub.window_calls == [(True,)]
    assert app_stub.launch_calls == []


def test_main_with_ib_name_launches_that_base(app_stub: _AppStub) -> None:
    """Режим ярлыка: имя доходит до `run_launch`, окно не открывается.

    Код возврата — тоже часть проводки: `run_launch` отдаёт 1 на отказе,
    и `main`, вернувший 0 вместо него, соврал бы оболочке об успехе.
    """  # noqa: RUF002
    assert main(["--ib-name", "Демо"]) == 3
    assert app_stub.window_calls == []
    assert [name for name, _env in app_stub.launch_calls] == ["Демо"]


def test_main_with_empty_ib_name_still_goes_to_launch_mode(app_stub: _AppStub) -> None:
    """Ключ без значения — режим запуска с пустым именем, а не окно.

    Окно здесь спрятало бы от пользователя опечатку в ярлыке; отказ
    с сообщением делает `run_launch`.
    """  # noqa: RUF002
    assert main(["--ib-name"]) == 3
    assert app_stub.window_calls == []
    assert [name for name, _env in app_stub.launch_calls] == [""]


def test_main_passes_the_process_environment_to_launch_mode(
    app_stub: _AppStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_launch` получает настоящее окружение процесса, а не пустой словарь.

    Из него собираются пути к `ibases.v8i` и к нашим данным (`APPDATA`):
    подставив сюда что угодно другое, ярлык искал бы базу не в том списке.
    """  # noqa: RUF002
    monkeypatch.setenv("ONECSTARTER_PROBE", "1")

    assert main(["--ib-name=Демо"]) == 3

    _name, env = app_stub.launch_calls[0]
    assert env.get("ONECSTARTER_PROBE") == "1"


# -- задача 8: режим самопроверки (--smoke) ----------------------------------


def test_main_with_smoke_runs_smoke_mode(app_stub: _AppStub) -> None:
    """`--smoke <каталог>` доходит до `run_smoke`, окно обычного режима не открывается.

    По образцу `test_main_with_ib_name_launches_that_base`: код возврата —
    тоже часть проводки, `main` не должен подменять его своим.
    """  # noqa: RUF002
    assert main(["--smoke", r"C:\tmp"]) == 5
    assert app_stub.window_calls == []
    assert app_stub.launch_calls == []
    assert [target for target, _env in app_stub.smoke_calls] == [r"C:\tmp"]


def test_main_with_empty_smoke_dir_returns_one_without_starting(
    app_stub: _AppStub, caplog: pytest.LogCaptureFixture
) -> None:
    """`--smoke` без каталога — отказ до входа в режим, причина в логе.

    Каталог обязателен: `run_smoke` не может ни собрать ярлык, ни отличить
    «каталог не указан» от опечатки. Отказ решает `_dispatch` сам, не
    вызывая `run_smoke` вовсе — по тому же поводу, что и пустое имя базы
    у `--ib-name`, но там отказ (с текстом на экране) делает уже сам
    `run_launch`, поскольку показывать окно ошибки может только Qt-код.
    Здесь Qt ещё не нужен: причина уходит в лог, а не в поглощаемый
    молча код 1.
    """  # noqa: RUF002
    with caplog.at_level(logging.ERROR, logger="onecstarter"):
        assert main(["--smoke"]) == 1
    assert app_stub.smoke_calls == []
    assert app_stub.window_calls == []
    assert "--smoke" in caplog.text


def test_smoke_takes_precedence_over_ib_name(app_stub: _AppStub) -> None:
    """Оба ключа разом — обязана победить самопроверка, а не запуск базы."""  # noqa: RUF002
    assert main(["--smoke", r"C:\tmp", "--ib-name", "Демо"]) == 5
    assert app_stub.launch_calls == []
    assert [target for target, _env in app_stub.smoke_calls] == [r"C:\tmp"]


# -- перехват в main: молчаливый отказ старта исключён (T-04.6) -------------
#
# `_dispatch` несёт прежнюю логику развилки (проверена выше через app_stub);
# здесь проверяется только обвязка `main`: лог настраивается до вызова,
# исключение из `_dispatch` не улетает наружу, а `show_fatal_error` зовётся  # noqa: RUF003
# без реального MessageBoxW — иначе прогон теста заблокировался бы окном.


def _cleanup_root() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def test_main_catches_dispatch_failure_and_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import onecstarter.__main__ as entry

    shown: list[str] = []
    try:
        monkeypatch.setattr(entry.diagnostics, "show_fatal_error", shown.append)
        monkeypatch.setattr(
            entry,
            "_dispatch",
            lambda arguments: (_ for _ in ()).throw(RuntimeError("бах")),  # noqa: RUF001
        )
        monkeypatch.setenv("APPDATA", str(tmp_path))

        assert entry.main([]) == 1

        assert shown and "onecstarter.log" in shown[0]
        log = tmp_path / "OneCStarter" / "logs" / "onecstarter.log"
        assert "бах" in log.read_text(encoding="utf-8")  # noqa: RUF001
    finally:
        _cleanup_root()
