"""Общие фикстуры всего набора тестов."""

from collections.abc import Iterator
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True, scope="session")
def forbid_real_keyring() -> Iterator[None]:
    """Ни один тест не дотягивается до реального Credential Manager.

    Тесты `KeyringStore` подменяют эти же функции своим `monkeypatch` —
    он ложится поверх защиты и снимается обратно на неё.
    """
    import keyring

    def _refuse(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError(
            "тест дотянулся до реального keyring — инъекция хранилища потеряна"
        )

    with pytest.MonkeyPatch.context() as patch:
        for name in ("get_password", "set_password", "delete_password"):
            patch.setattr(keyring, name, _refuse)
        yield
