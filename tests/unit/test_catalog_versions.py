"""Извлечение имён ключей раздела 7.3 и диапазоны версий (build/catalog_versions.py)."""

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "catalog_versions", ROOT / "build" / "catalog_versions.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLE = """\
7.2.3. Запуск в режиме создания информационной базы
/AddToList — не из раздела 7.3
7.3. Общие команды запуска
7.3.1. Указание параметров подключения
/F <каталог>
Каталог, в котором расположен файл базы данных.
 /N<имя>
UsePrivilegedMode
Запуск клиентского приложения в привилегированном режиме.
/IBConnectionString находился в командной строке раньше них.
7.4. Команды пакетного режима запуска конфигуратора
/DumpIB <имя файла>
"""


def test_section_keys_takes_only_section_7_3_and_line_starts() -> None:
    keys = _module().section_keys(SAMPLE)
    assert keys == {"/F", "/N", "/IBConnectionString", "/UsePrivilegedMode"}


def test_version_ranges_since_until() -> None:
    found = {
        "8.3.18": {"/F", "/Old"},
        "8.3.20": {"/F", "/Old", "/New"},
        "8.5.4": {"/F", "/New"},
    }
    ranges = _module().version_ranges(found, ["/F", "/Old", "/New", "/Absent"])
    assert ranges == {
        "/F": ("8.3.18", None),
        "/Old": ("8.3.18", "8.3.20"),
        "/New": ("8.3.20", None),
        "/Absent": (None, None),
    }


def test_section_commands_takes_only_section_7_4_and_line_starts() -> None:
    commands = _module().section_commands(SAMPLE)
    assert commands == {"/DumpIB"}
