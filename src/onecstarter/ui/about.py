"""«О программе» (спека v3.1, §7): версия из метаданных пакета, ссылка на репозиторий.

Версия — из одного места (`pyproject.toml`, CLAUDE.md «Сборка»): метаданные
пакета собираются из него; в exe их кладёт `copy_metadata` в `build/onecstarter.spec`,
гейт — строка `smoke: version=` в самопроверке сборки.
"""  # noqa: RUF002

import importlib.metadata

REPOSITORY_URL = "https://github.com/AnanyevAl/OnecStarter"
VERSION_UNKNOWN = "неизвестна"


def app_version() -> str:
    try:
        return importlib.metadata.version("onecstarter")
    except importlib.metadata.PackageNotFoundError:
        return VERSION_UNKNOWN
