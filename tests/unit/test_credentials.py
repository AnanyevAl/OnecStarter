"""Хранилище паролей: контракт Protocol на фейке и перевод ошибок keyring."""

import pytest

from onecstarter.security.credentials import (
    CredentialStoreError,
    KeyringStore,
    MemoryStore,
)


def test_memory_store_round_trip() -> None:
    store = MemoryStore()
    store.write("id:x", "p@ss")
    assert store.read("id:x") == "p@ss"
    store.delete("id:x")
    assert store.read("id:x") is None


def test_memory_store_delete_of_missing_is_silent() -> None:
    """Удаление отсутствующего — не ошибка: снятие «Запомнить» у записи
    без пароля обязано проходить молча (спека v2.2, §3)."""  # noqa: RUF002
    MemoryStore().delete("id:nope")


def test_keyring_store_translates_keyring_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слой выше не знает про keyring — ему нужен один тип отказа."""
    import keyring
    import keyring.errors

    def boom(*_args: object, **_kwargs: object) -> None:
        raise keyring.errors.KeyringError("нет бэкенда")

    monkeypatch.setattr(keyring, "set_password", boom)
    with pytest.raises(CredentialStoreError):
        KeyringStore(service="OneCStarter-test").write("id:x", "p@ss")


def test_keyring_store_delete_of_missing_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring
    import keyring.errors

    def missing(*_args: object, **_kwargs: object) -> None:
        raise keyring.errors.PasswordDeleteError("нет такой")

    monkeypatch.setattr(keyring, "delete_password", missing)
    KeyringStore(service="OneCStarter-test").delete("id:nope")


def test_importing_the_module_does_not_import_keyring() -> None:
    """[Ф] 06.09.2026: import keyring ~200 мс; модуль тянет Workspace на каждом
    старте — keyring обязан грузиться лениво, при первом обращении."""
    import subprocess
    import sys

    probe = (
        "import sys; import onecstarter.security.credentials; "
        "print('keyring' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_failure_repr_never_carries_the_secret() -> None:
    """Текст отказа уходит пользователю — секрета в нём быть не может."""
    error = CredentialStoreError("запись отвергнута")
    assert "p@ss" not in repr(error) and "p@ss" not in str(error)
