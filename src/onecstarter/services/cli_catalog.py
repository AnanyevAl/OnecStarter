"""Чтение каталога ключей командной строки из данных поставки (спека v4, §2).

Тот же приём, что у `platform_1c/registry.py`: TOML лежит в пакете и читается через
`importlib.resources` — в сборку его кладёт явный `datas` spec-файла (задача 12).
"""  # noqa: RUF002

import tomllib
from importlib import resources

from onecstarter.domain.cli_catalog import Catalog, load_catalog


def load_cli_catalog(data: bytes | None = None) -> Catalog:
    if data is None:
        data = (resources.files("onecstarter.platform_1c") / "cli_catalog.toml").read_bytes()
    return load_catalog(tomllib.loads(data.decode("utf-8")))
