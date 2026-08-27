"""Координатор раздела «Серверы»: профили и их хранение.

Эта задача (T-08, задача 10) закрывает только CRUD-контур над `servers.json`:
чтение при старте, добавление/правка/удаление с валидацией, атомарная
запись с откатом состояния в памяти при отказе. Сканирование живых
процессов ragent, их остановка, запуск сервера и регистрация консоли —
последующие задачи; их эффекты (`control`, `spawn`, `run_elevated`,
`open_file`, `registered_radmin`) инжектируются уже сейчас конструктором
и сохраняются в полях, но здесь не вызываются — задел, чтобы сигнатура
координатора не менялась вслед за каждой следующей задачей.

Приём инъекции эффектов и отката состояния в памяти при отказе записи —
тот же, что в `services/workspace.py::Workspace` (см. её докстринг
и `_store_user`): экран, построенный по `profiles()`, обязан показывать
то же, что реально лежит в файле, а не то, что мы хотели туда записать.
"""  # noqa: RUF002

import os
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import ServerProfile, validate_profile
from onecstarter.domain.server_match import normalize_cluster_dir
from onecstarter.platform_1c import console, elevation, process
from onecstarter.platform_1c.process_control import ProcessControl
from onecstarter.services.errors import ServerError
from onecstarter.services.server_store import load_profiles, save_profiles

__all__ = ["ServersWorkspace"]


class ServersWorkspace:
    """Координатор: список профилей серверов и их хранение в `servers.json`.

    Конструктор вызывает `load_profiles` и может подняться с
    `ServersUnavailableError` (наследник `ServerError`), если файл профилей
    существует, но недоступен для чтения либо испорченный файл не удалось
    перенести в `.bad`. Исключение не гасится и обязано дойти до вызывающего —
    молча подменять его пустым списком нельзя: первое же сохранение затёрло бы
    настроенные профили без следа (докстринг `server_store.py`).
    """  # noqa: RUF002

    def __init__(
        self,
        store_path: Path,
        *,
        control: ProcessControl,
        spawn: Callable[[LaunchCommand], int] = process.spawn,
        run_elevated: Callable[[str, str], int] = elevation.run_elevated,
        open_file: Callable[[str], None] = os.startfile,
        registered_radmin: Callable[[], Path | None] = console.registered_radmin_path,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.store_path = store_path
        # Эффекты следующих задач (сканы, остановка, запуск, регистрация
        # консоли) — только сохранены, здесь не вызываются (см. докстринг
        # модуля).
        self._control = control
        self._spawn = spawn
        self._run_elevated = run_elevated
        self._open_file = open_file
        self._registered_radmin = registered_radmin
        self._new_id = new_id
        self._profiles: list[ServerProfile] = load_profiles(store_path)

    def profiles(self) -> list[ServerProfile]:
        return list(self._profiles)

    def add_profile(self, profile: ServerProfile) -> None:
        """Добавить профиль. Пустой `id` — подставляется `new_id()`.

        Непустой `id`, совпавший с уже существующим профилем, — ошибка:
        `add_profile` создаёт новую запись, а не правит существующую
        (для этого `update_profile`).
        """  # noqa: RUF002
        if profile.id == "":
            profile = replace(profile, id=self._new_id())
        elif any(existing.id == profile.id for existing in self._profiles):
            raise ServerError(f"Профиль с id «{profile.id}» уже существует")  # noqa: RUF001
        # Новый профиль ещё не в self._profiles — others это весь текущий
        # список, фильтровать по id не нужно.
        self._validate(profile, self._profiles)
        self._save([*self._profiles, profile])

    def update_profile(self, profile: ServerProfile) -> None:
        """Заменить профиль с тем же `id`. Неизвестный `id` — ошибка."""  # noqa: RUF002
        if not any(existing.id == profile.id for existing in self._profiles):
            raise ServerError(f"Профиля с id «{profile.id}» нет в списке")  # noqa: RUF001
        others = [existing for existing in self._profiles if existing.id != profile.id]
        self._validate(profile, others)
        updated = [
            profile if existing.id == profile.id else existing for existing in self._profiles
        ]
        self._save(updated)

    def remove_profile(self, profile_id: str) -> None:
        """Удалить профиль по `id`. Неизвестный `id` — ошибка."""
        if not any(existing.id == profile_id for existing in self._profiles):
            raise ServerError(f"Профиля с id «{profile_id}» нет в списке")  # noqa: RUF001
        updated = [existing for existing in self._profiles if existing.id != profile_id]
        self._save(updated)

    def _validate(self, profile: ServerProfile, others: list[ServerProfile]) -> None:
        errors = validate_profile(profile, others, normalize=normalize_cluster_dir)
        if errors:
            raise ServerError(errors[0])

    def _save(self, updated: list[ServerProfile]) -> None:
        """Заменить список профилей и записать его. Отказ ФС откатывает память.

        Тот же приём, что `Workspace._store_user`: без отката экран после
        отказа записи показал бы профиль, которого в файле нет.
        """  # noqa: RUF002
        previous = self._profiles
        self._profiles = updated
        try:
            save_profiles(self.store_path, self._profiles)
        except OSError as error:
            self._profiles = previous
            raise ServerError(
                f"Не удалось сохранить профили серверов ({self.store_path}): {error}"  # noqa: RUF001
            ) from error
