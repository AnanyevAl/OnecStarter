"""«О программе»: версия из метаданных пакета, без падения при их отсутствии (спека v3.1, §7)."""  # noqa: RUF002

import importlib.metadata

import pytest

from onecstarter.ui import about


def test_version_comes_from_package_metadata() -> None:
    assert about.app_version() == importlib.metadata.version("onecstarter")


def test_version_unknown_without_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(about.importlib.metadata, "version", missing)  # type: ignore[attr-defined]
    assert about.app_version() == "неизвестна"


def test_repository_url() -> None:
    assert about.REPOSITORY_URL == "https://github.com/AnanyevAl/OnecStarter"
