"""Хранилище паролей записей — Windows Credential Manager через `keyring`.

Инвариант 5: секреты — только через `security/`. Слои выше видят Protocol
и один тип отказа; про `keyring` они не знают. Тот же приём инъекции, что
у `services/autostart.py::Registry`: настоящая реализация в проде, фейк
в памяти — в тестах и самопроверке сборки.

Почему `keyring`, а не своя обёртка над `advapi32`: он зависимость с 0.1.0,
под капотом те же `CredRead`/`CredWrite`, и его не надо сопровождать.
[Ф] 04.09.2026: на машине заказчика `keyring` 25.7.0 выбирает
`WinVaultKeyring` без настройки. Цена — упаковка: без `hiddenimports`
frozen-сборка молча уходит в пустой бэкенд, гейт — задача 1 плана v2.2.

Имя записи в хранилище — ключ привязки базы (`services/model.py::
binding_key`): тот же, что у избранного и истории, поэтому при смене
ключа (`Workspace._write(rekey_from=…)`) секрет переезжает вместе с ними.

`keyring` импортируется ЛЕНИВО, внутри методов, а не на уровне модуля:
[Ф] 06.09.2026 — `import keyring` стоит ~200 мс (тянет `keyring.core`),
первый `get_keyring()` — ещё ~55 мс на entry points. Этот модуль
импортирует `Workspace`, то есть каждый старт программы; платить 200 мс
за функцию, которую большинство не включит, нельзя. Тот же приём, что
у `_KeyringSmokeVault` в `ui/app.py` (задача 1 вехи v2.2).
"""  # noqa: RUF002

from typing import Protocol

SERVICE = "OneCStarter"


class CredentialBackendError(Exception):
    """Хранилище отказало. Текст — только причина, никогда не секрет."""


class CredentialStore(Protocol):
    def read(self, key: str) -> str | None: ...

    def write(self, key: str, secret: str) -> None: ...

    def delete(self, key: str) -> None: ...


class KeyringStore:
    """Настоящее хранилище. `delete` отсутствующей записи — не ошибка:
    снятие «Запомнить» у записи без пароля обязано проходить молча."""  # noqa: RUF002

    def __init__(self, service: str = SERVICE) -> None:
        self._service = service

    def read(self, key: str) -> str | None:
        import keyring
        import keyring.errors

        try:
            return keyring.get_password(self._service, key)
        except keyring.errors.KeyringError as error:
            raise CredentialBackendError(_reason(error)) from error

    def write(self, key: str, secret: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.set_password(self._service, key, secret)
        except keyring.errors.KeyringError as error:
            raise CredentialBackendError(_reason(error)) from error

    def delete(self, key: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(self._service, key)
        except keyring.errors.PasswordDeleteError:
            return
        except keyring.errors.KeyringError as error:
            raise CredentialBackendError(_reason(error)) from error


class MemoryStore:
    """Хранилище в памяти — тесты и самопроверка сборки. Настоящий
    Credential Manager машины не трогается."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def read(self, key: str) -> str | None:
        return self.data.get(key)

    def write(self, key: str, secret: str) -> None:
        self.data[key] = secret

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def _reason(error: Exception) -> str:
    """Причина без секрета: keyring в тексте ошибки пароль не печатает,
    но полагаться на это нельзя — берётся только имя типа."""
    return f"диспетчер учётных данных Windows: {type(error).__name__}"
