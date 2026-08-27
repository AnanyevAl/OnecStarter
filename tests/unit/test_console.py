"""Тесты чтения регистрации консоли кластера: фейковый `read_value`.

Живой реестр HKLM в тестах не трогается — только словарь-заглушка,
подставленная параметром `read_value`.
"""

from pathlib import Path

from onecstarter.platform_1c.console import (
    RADMIN_CLSIDS,
    register_arguments,
    registered_radmin_path,
)

_SUBKEY = f"SOFTWARE\\Classes\\CLSID\\{RADMIN_CLSIDS[0]}\\InprocServer32"


class TestRegisteredRadminPath:
    def test_found_key_returns_path_with_version(self) -> None:
        fake_registry = {
            _SUBKEY: r"C:\Program Files\1cv8\8.3.25.1633\bin\radmin.dll",
        }
        result = registered_radmin_path(read_value=fake_registry.get)
        assert result == Path(r"C:\Program Files\1cv8\8.3.25.1633\bin\radmin.dll")

    def test_missing_key_returns_none(self) -> None:
        result = registered_radmin_path(read_value=lambda _subkey: None)
        assert result is None


class TestRegisterArguments:
    def test_exact_quoted_command_without_slash_u(self) -> None:
        dll = Path(r"C:\Program Files\1cv8\8.3.25.1633\bin\radmin.dll")
        assert register_arguments(dll) == (
            '/s "C:\\Program Files\\1cv8\\8.3.25.1633\\bin\\radmin.dll"'
        )
