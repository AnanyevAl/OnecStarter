"""Загрузка реестра раскладки версий платформы из TOML-данных поставки."""

import tomllib
from importlib import resources

from onecstarter.domain.launch import ClientConvention, ClientKind
from onecstarter.domain.server import ServerConvention
from onecstarter.domain.version import parse_version


def load_conventions(data: bytes | None = None) -> list[ClientConvention]:
    if data is None:
        data = (resources.files("onecstarter.platform_1c") / "registry.toml").read_bytes()
    payload = tomllib.loads(data.decode("utf-8"))
    conventions: list[ClientConvention] = []
    for entry in payload["conventions"]:
        executables = {
            ClientKind(kind): name for kind, name in entry["executables"].items()
        }
        conventions.append(
            ClientConvention(
                min_version=parse_version(entry["min_version"]),
                bin_dir=entry["bin_dir"],
                executables=executables,
            )
        )
    return conventions


def load_server_conventions(data: bytes | None = None) -> list[ServerConvention]:
    if data is None:
        data = (resources.files("onecstarter.platform_1c") / "registry.toml").read_bytes()
    payload = tomllib.loads(data.decode("utf-8"))
    conventions: list[ServerConvention] = []
    for entry in payload["server_conventions"]:
        conventions.append(
            ServerConvention(
                min_version=parse_version(entry["min_version"]),
                bin_dir=entry["bin_dir"],
                ragent=entry["ragent"],
                radmin=entry["radmin"],
                console=entry["console"],
            )
        )
    return conventions
