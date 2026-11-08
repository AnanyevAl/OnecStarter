"""Мьютекс «уже запущено» (T-39, спека 3.2.5 §6.2) — на настоящем объекте ядра."""

import ctypes
import uuid

import pytest

from onecstarter.platform_1c import instance_lock
from onecstarter.platform_1c.instance_lock import acquire, current_session_id, instance_id

ENV = {"USERDOMAIN": "CORP", "USERNAME": "ivanov"}


@pytest.mark.parametrize(
    ("env", "session"),
    [
        ({"USERDOMAIN": "CORP", "USERNAME": "petrov"}, 1),
        ({"USERDOMAIN": "OTHER", "USERNAME": "ivanov"}, 1),
        (ENV, 2),
    ],
)
def test_instance_id_differs_by_account_and_session(env: dict[str, str], session: int) -> None:
    assert instance_id(env, session) != instance_id(ENV, 1)


def test_instance_id_is_stable_and_hides_the_account() -> None:
    name = instance_id(ENV, 1)
    assert name == instance_id(dict(ENV), 1)
    assert name.startswith("OneCStarter-")
    assert len(name) == len("OneCStarter-") + 16
    assert "ivanov" not in name.lower() and "corp" not in name.lower()


def test_instance_id_is_the_contract_between_versions() -> None:
    """Эталон: имя — контракт между версиями начиная с 3.2.5 (спека §6.2).

    Сломался — значит поменялась формула, и новая версия запустится рядом
    со старой. Не «исправлять» литерал, а вернуть формулу.
    """  # noqa: RUF002
    assert instance_id({"USERDOMAIN": "CORP", "USERNAME": "Ivanov"}, 1) == (
        "OneCStarter-1c10ac8693c1ae2c"
    )


@pytest.mark.parametrize(
    "env",
    [
        {"USERDOMAIN": "CORP", "USERNAME": "ivanov"},
        {"USERDOMAIN": "corp", "USERNAME": "IVANOV"},
        {"USERDOMAIN": "Corp", "USERNAME": "IvAnOv"},
    ],
)
def test_instance_id_ignores_letter_case(env: dict[str, str]) -> None:
    assert instance_id(env, 1) == instance_id({"USERDOMAIN": "CORP", "USERNAME": "Ivanov"}, 1)


def test_instance_id_tolerates_missing_variables() -> None:
    assert instance_id({}, 0).startswith("OneCStarter-")


def test_current_session_id_is_a_non_negative_int() -> None:
    assert current_session_id() >= 0


def test_second_acquire_reports_busy_until_first_is_released() -> None:
    """Мутационная проверка: `acquire`, не смотрящий на ERROR_ALREADY_EXISTS, — упадёт."""
    name = f"OneCStarter-test-{uuid.uuid4().hex}"
    first = acquire(name)
    assert first is not None
    try:
        assert acquire(name) is None
    finally:
        first.release()
    again = acquire(name)
    assert again is not None
    again.release()


class _FailingKernel32:
    """`CreateMutexW`, отказывающий с заданной последней ошибкой (без объекта ядра)."""  # noqa: RUF002

    def __init__(self, error: int) -> None:
        self._error = error

    def CreateMutexW(self, *args: object) -> None:  # noqa: N802
        ctypes.set_last_error(self._error)
        return None

    def CloseHandle(self, handle: object) -> int:  # noqa: N802
        raise AssertionError("закрывать нечего: хэндл не получен")


def test_access_denied_means_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Мьютекс создан процессом с повышенными правами — «занято», не отказ."""  # noqa: RUF002
    monkeypatch.setattr(
        instance_lock, "_kernel32", _FailingKernel32(instance_lock.ERROR_ACCESS_DENIED)
    )
    assert acquire("OneCStarter-test-denied") is None


def test_other_failure_is_an_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(instance_lock, "_kernel32", _FailingKernel32(87))  # ERROR_INVALID_PARAMETER
    with pytest.raises(OSError):
        acquire("OneCStarter-test-invalid")
