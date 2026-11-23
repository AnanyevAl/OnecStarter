"""Н1 (повторная приёмка 21.11.2026): запуск внешних программ без пути DLL PyInstaller."""  # noqa: RUF002

import inspect
import os
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from onecstarter.platform_1c import dll_search
from onecstarter.services.console_admin import ConsoleAdmin
from onecstarter.services.edt import EdtWorkspace
from onecstarter.services.launch import launch_infobase
from onecstarter.services.servers import ServersWorkspace
from onecstarter.services.workspace import Workspace

BUNDLE = r"C:\app\_internal"


@pytest.fixture(autouse=True)
def _keep_real_dll_directory() -> Iterator[None]:
    """Ревью задачи 10, п. 4: тесты с настоящим WinAPI возвращают исходный путь, а не `None`."""  # noqa: RUF002
    original = dll_search.get_dll_directory()
    restore = dll_search.set_dll_directory
    yield
    restore(original)


def _fake_dll_directory(monkeypatch: pytest.MonkeyPatch) -> dict[str, str | None]:
    """Путь DLL — в словаре: тесты окружения не трогают настоящий `SetDllDirectoryW`."""
    state: dict[str, str | None] = {"dir": BUNDLE}
    monkeypatch.setattr(dll_search, "get_dll_directory", lambda: state["dir"])
    monkeypatch.setattr(dll_search, "set_dll_directory", lambda p: state.__setitem__("dir", p))
    monkeypatch.setattr(sys, "_MEIPASS", BUNDLE, raising=False)
    return state


def _frozen_environment(monkeypatch: pytest.MonkeyPatch) -> str:
    """Окружение собранной программы: хук `pyi_rth_pyside6` (PyInstaller 6.22.1) дописывает
    `_MEIPASS`, `PySide6/__init__.py` (6.11.1) — `_MEIPASS\\PySide6`; `_internal2` — сосед с общим
    префиксом, он не внутри `_MEIPASS` и обязан остаться (ревью задачи 10, раунд 2)."""  # noqa: RUF002
    path = os.pathsep.join(
        [
            BUNDLE + r"\PySide6",
            BUNDLE,
            r"C:\Windows\system32",
            "",
            "c:\\APP\\_internal\\",
            r"C:\app\tools\..\_internal\PySide6",
            BUNDLE + "2",
            r"C:\tools",
        ]
    )
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("QT_PLUGIN_PATH", BUNDLE + r"\PySide6\plugins")
    monkeypatch.setenv("QML2_IMPORT_PATH", BUNDLE + r"\PySide6\qml")
    return path


def test_real_dll_directory_is_cleared_inside_and_restored_after(tmp_path: Path) -> None:
    """Настоящий WinAPI: внутри блока пути нет, после — прежний (как у собранной программы)."""  # noqa: RUF002
    dll_search.set_dll_directory(str(tmp_path))
    with dll_search.clean_dll_search(frozen=True):
        assert dll_search.get_dll_directory() is None
    assert dll_search.get_dll_directory() == str(tmp_path)


def test_restored_even_when_the_launch_fails(tmp_path: Path) -> None:
    dll_search.set_dll_directory(str(tmp_path))
    with pytest.raises(OSError), dll_search.clean_dll_search(frozen=True):
        raise OSError("запуск не удался")
    assert dll_search.get_dll_directory() == str(tmp_path)


def test_not_frozen_leaves_the_directory_alone(tmp_path: Path) -> None:
    dll_search.set_dll_directory(str(tmp_path))
    with dll_search.clean_dll_search(frozen=False):
        assert dll_search.get_dll_directory() == str(tmp_path)


def test_frozen_is_read_from_sys_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    dll_search.set_dll_directory(str(tmp_path))
    with dll_search.clean_dll_search():
        assert dll_search.get_dll_directory() is None


def test_nested_blocks_on_one_thread_do_not_freeze(tmp_path: Path) -> None:
    """Предпроверка плана В, п. 10: внутри `ShellExecute` бывает вложенный цикл сообщений, и в
    нём может начаться второй запуск в том же потоке — блокировка обязана быть реентерабельной.

    Блоки — в отдельном потоке с таймаутом: на нереентерабельной блокировке тест падает, а не
    зависает. Мутацию запускать этим тестом в одиночку — зависший поток держит блокировку.
    """  # noqa: RUF002
    dll_search.set_dll_directory(str(tmp_path))
    seen: list[str | None] = []

    def nested() -> None:
        with dll_search.clean_dll_search(frozen=True):
            with dll_search.clean_dll_search(frozen=True):
                seen.append(dll_search.get_dll_directory())
            seen.append(dll_search.get_dll_directory())

    worker = threading.Thread(target=nested, daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert seen == [None, None]
    assert dll_search.get_dll_directory() == str(tmp_path)


def test_environment_is_cleaned_inside_and_restored_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ревью задачи 10, п. 1 и раунд 2: из `PATH` уходит всё внутри `_MEIPASS` — сам корень
    и подкаталоги (регистр, `\\` в конце и `..` не важны), сосед `_internal2` и прочие элементы с их
    порядком — на месте; ключи Qt, указывающие внутрь, сняты."""  # noqa: RUF002
    _fake_dll_directory(monkeypatch)
    path = _frozen_environment(monkeypatch)
    with dll_search.clean_dll_search(frozen=True):
        assert os.environ["PATH"] == os.pathsep.join(
            [r"C:\Windows\system32", "", BUNDLE + "2", r"C:\tools"]
        )
        assert "QT_PLUGIN_PATH" not in os.environ
        assert "QML2_IMPORT_PATH" not in os.environ
    assert os.environ["PATH"] == path
    assert os.environ["QT_PLUGIN_PATH"] == BUNDLE + r"\PySide6\plugins"
    assert os.environ["QML2_IMPORT_PATH"] == BUNDLE + r"\PySide6\qml"


def test_environment_restored_even_when_the_launch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_dll_directory(monkeypatch)
    path = _frozen_environment(monkeypatch)
    with pytest.raises(OSError), dll_search.clean_dll_search(frozen=True):
        raise OSError("запуск не удался")
    assert os.environ["PATH"] == path
    assert os.environ["QT_PLUGIN_PATH"] == BUNDLE + r"\PySide6\plugins"
    assert os.environ["QML2_IMPORT_PATH"] == BUNDLE + r"\PySide6\qml"


def test_partial_environment_cleaning_is_rolled_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ревью задачи 10, раунд 2: сбой посреди чистки окружения не оставляет его полуочищенным.

    Сбой вызывается ключом не той природы после `PATH` и `QT_PLUGIN_PATH`: `os.environ.get(42)`
    поднимает `TypeError`, когда два ключа уже правлены.
    """  # noqa: RUF002
    _fake_dll_directory(monkeypatch)
    path = _frozen_environment(monkeypatch)
    monkeypatch.setattr(dll_search, "_QT_KEYS", ("QT_PLUGIN_PATH", 42))
    with pytest.raises(TypeError), dll_search.clean_dll_search(frozen=True):
        pytest.fail("блок не должен начаться: чистка окружения не удалась")
    assert os.environ["PATH"] == path
    assert os.environ["QT_PLUGIN_PATH"] == BUNDLE + r"\PySide6\plugins"


def test_absent_qt_keys_stay_absent_and_foreign_ones_stay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ключа не было — после блока его нет; ключ, указывающий не в `_MEIPASS`, не трогается."""  # noqa: RUF002
    _fake_dll_directory(monkeypatch)
    path = _frozen_environment(monkeypatch)
    monkeypatch.delenv("QML2_IMPORT_PATH")
    monkeypatch.setenv("QT_PLUGIN_PATH", r"C:\Qt\plugins")
    with dll_search.clean_dll_search(frozen=True):
        assert "QML2_IMPORT_PATH" not in os.environ
        assert os.environ["QT_PLUGIN_PATH"] == r"C:\Qt\plugins"
    assert "QML2_IMPORT_PATH" not in os.environ
    assert os.environ["QT_PLUGIN_PATH"] == r"C:\Qt\plugins"
    assert os.environ["PATH"] == path


def test_not_frozen_leaves_the_environment_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_dll_directory(monkeypatch)
    path = _frozen_environment(monkeypatch)
    with dll_search.clean_dll_search(frozen=False):
        assert os.environ["PATH"] == path
        assert os.environ["QT_PLUGIN_PATH"] == BUNDLE + r"\PySide6\plugins"
        assert os.environ["QML2_IMPORT_PATH"] == BUNDLE + r"\PySide6\qml"


@pytest.mark.parametrize(
    ("function", "parameter", "expected"),
    [
        (ConsoleAdmin.__init__, "open_file", dll_search.startfile),
        (EdtWorkspace.__init__, "open_file", dll_search.startfile),
        (ServersWorkspace.__init__, "open_file", dll_search.startfile),
        (launch_infobase, "open_url", dll_search.open_url),
        (Workspace.__init__, "open_url", dll_search.open_url),
    ],
)
def test_services_open_files_and_links_through_dll_search(
    function: Callable[..., object], parameter: str, expected: object
) -> None:
    """Предпроверка плана В, п. 25: умолчания служб — через `dll_search`, иначе Н1 вернётся."""  # noqa: RUF002
    assert inspect.signature(function).parameters[parameter].default is expected
