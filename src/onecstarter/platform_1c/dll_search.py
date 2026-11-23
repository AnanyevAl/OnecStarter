"""Следы `_internal`, которые наследуют запускаемые программы (Н1, приёмка 21.11.2026).

Два канала, оба наследуются дочерними процессами:

1. Путь поиска DLL. [из документации] PyInstaller, «Common Issues and Pitfalls», раздел Windows:
   загрузчик ставит путь поиска библиотек `SetDllDirectoryW` в каталог приложения (one-dir —
   `_internal`), и это наследуют дочерние процессы; отмена — `SetDllDirectoryW(NULL)`.
2. Окружение, два источника:
   - [проверено чтением кода хука PyInstaller 6.22.1, `pyi_rth_pyside6.py`, 22.11.2026]
     runtime-хук PySide6 на Windows дописывает `sys._MEIPASS` в начало `PATH` и ставит
     `QT_PLUGIN_PATH=<_MEIPASS>\\PySide6\\plugins`, `QML2_IMPORT_PATH=<_MEIPASS>\\PySide6\\qml`;
   - [проверено чтением кода PySide6 6.11.1, `PySide6/__init__.py`, 22.11.2026] сам пакет при
     импорте на Windows дописывает в начало `PATH` свой каталог — `<_MEIPASS>\\PySide6`, где
     в собранной программе лежат `VCRUNTIME140.dll`, `MSVCP140*.dll`.
   Ребёнок с таким окружением ищет недостающие DLL в `_internal`, Qt-ребёнок читает наши плагины.
   Поэтому из `PATH` убирается каждый элемент внутри `_MEIPASS` — корень и любые подкаталоги
   (граница — разделитель пути: `..._internal2` не внутри `..._internal`).

[проверено] 21.11.2026: VS Code, запущенный из программы, держал `_internal\\VCRUNTIME140.dll`
установленной копии — установщик новой версии не смог заменить файлы и откатился.
[не проверено] найдёт ли программа свои DLL при ленивой загрузке после глобального сброса —
документация молчит; поэтому оба канала очищаются только на время порождения процесса и
восстанавливаются сразу после. Окружение правится через `os.environ`: так одной правкой
покрыты `Popen` без `env=`, `os.startfile`, `ShellExecuteExW` и `QDesktopServices.openUrl`.

Блокировка реентерабельная (предпроверка плана В, п. 10): `startfile`, `open_url` и
`QDesktopServices.openUrl` идут в потоке интерфейса, а внутри `ShellExecute` бывает вложенный
цикл сообщений (DDE, COM) — в нём может начаться второй запуск в том же потоке. Вложенный блок
видит уже очищенное состояние и возвращает его же, внешний — исходное. Принятый риск: путь DLL
и окружение — состояние процесса; другой поток на время блока лениво грузит DLL без `_internal`
и читает окружение без `_internal` в `PATH` и без `QT_*` — блокировка от этого не защищает.
При повышенном запуске (`elevation._start`) блок держится всё время ожидания ответа в окне UAC;
так же при `startfile` консоли `.msc` (mmc требует повышения). Поток интерфейса ждёт под `_LOCK`,
рабочий поток «Операций» ждёт блокировку на `spawn_logged`; взаимоблокировки нет (поток
интерфейса рабочие потоки не ждёт), задержка ограничена ответом UAC.
"""  # noqa: RUF002

import ctypes
import os
import sys
import threading
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager

_LOCK = threading.RLock()
_QT_KEYS = ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH")


def get_dll_directory() -> str | None:
    kernel32 = ctypes.windll.kernel32
    size = kernel32.GetDllDirectoryW(0, None)
    if size == 0:
        return None
    buffer = ctypes.create_unicode_buffer(size)
    kernel32.GetDllDirectoryW(size, buffer)
    return buffer.value or None


def set_dll_directory(path: str | None) -> None:
    if not ctypes.windll.kernel32.SetDllDirectoryW(path):
        raise ctypes.WinError()


def _normalized(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _inside(path: str, root: str) -> bool:
    normalized = _normalized(path)
    return normalized == root or normalized.startswith(root.rstrip(os.sep) + os.sep)


def _clean_environment(bundle: str | None, saved: dict[str, str]) -> None:
    """Убрать из `os.environ` всё, что лежит внутри `bundle` (`sys._MEIPASS`).

    Прежнее значение ключа попадает в `saved` до его правки — сбой посреди чистки оставляет
    в `saved` всё, что успело измениться, и `_restore_environment` откатывает это.
    """  # noqa: RUF002
    if not bundle:
        return
    root = _normalized(bundle)
    path = os.environ.get("PATH")
    if path is not None:
        items = path.split(os.pathsep)
        kept = [item for item in items if not item or not _inside(item, root)]
        if len(kept) != len(items):
            saved["PATH"] = path
            os.environ["PATH"] = os.pathsep.join(kept)
    for key in _QT_KEYS:
        value = os.environ.get(key)
        if value is not None and any(
            _inside(item, root) for item in value.split(os.pathsep) if item
        ):
            saved[key] = value
            del os.environ[key]


def _restore_environment(saved: dict[str, str]) -> None:
    for key, value in saved.items():
        os.environ[key] = value


@contextmanager
def clean_dll_search(frozen: bool | None = None) -> Iterator[None]:
    """Блок, внутри которого порождённый процесс не наследует от программы
    ни путь DLL, ни `_internal` в окружении."""
    active = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not active:
        yield
        return
    with _LOCK:
        previous = get_dll_directory()
        saved: dict[str, str] = {}
        try:
            _clean_environment(getattr(sys, "_MEIPASS", None), saved)
            set_dll_directory(None)
            yield
        finally:
            try:
                set_dll_directory(previous)
            finally:
                _restore_environment(saved)


def startfile(path: str) -> None:
    with clean_dll_search():
        os.startfile(path)  # noqa: RUF100, S606


def open_url(url: str) -> bool:
    with clean_dll_search():
        return webbrowser.open(url)
