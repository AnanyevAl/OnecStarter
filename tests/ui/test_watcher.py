import os
import tempfile
import time
from pathlib import Path

from onecstarter.ui.watcher import FileWatcher


def _replace_atomically(path: Path, payload: bytes, attempts: int = 20) -> None:
    """Как пишет и платформа, и наш atomic_write: временный файл + замена.

    Ретрай — на гонку файловых хендлов Windows: два быстрых `os.replace`
    подряд изредка встречают `PermissionError [WinError 5]` (антивирус,
    индексатор, ещё не закрытый хендл watcher'а). Это свойство среды,
    а не дефект продукта, поэтому ретрай здесь, в тестовом хелпере,
    и не в `atomic_write` (план 4a, Task 9, примечание о флаке).
    """  # noqa: RUF002
    handle, temp_name = tempfile.mkstemp(dir=path.parent)
    os.close(handle)
    temp = Path(temp_name)
    temp.write_bytes(payload)
    for attempt in range(attempts):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def test_plain_write_emits_changed(qtbot, tmp_path):
    target = tmp_path / "ibases.v8i"
    target.write_bytes(b"[A]\r\n")
    watcher = FileWatcher(target, debounce_ms=50)
    with qtbot.waitSignal(watcher.changed, timeout=3000):
        target.write_bytes(b"[A]\r\nConnect=x\r\n")


def test_atomic_replace_keeps_watching(qtbot, tmp_path):
    # Спека 4a, §5: полная перезапись (материализация общей базы, перезапись
    # штатным стартером) не должна отключать слежение. Тест проверяет наблюдаемое
    # поведение (сигнал приходит после замен), а не механизм переподписки — на  # noqa: RUF003
    # Windows механизм этим тестом недоказуем ([Ф] 07.08.2026: бэкенд не теряет
    # файл, отключение _resubscribe не валит тест).
    target = tmp_path / "ibases.v8i"
    target.write_bytes(b"[A]\r\n")
    watcher = FileWatcher(target, debounce_ms=50)
    with qtbot.waitSignal(watcher.changed, timeout=3000):
        _replace_atomically(target, b"[B]\r\n")
    # Второе срабатывание — доказательство переподписки после замены.
    with qtbot.waitSignal(watcher.changed, timeout=3000):
        _replace_atomically(target, b"[C]\r\n")


def test_debounce_merges_bursts(qtbot, tmp_path):
    target = tmp_path / "ibases.v8i"
    target.write_bytes(b"[A]\r\n")
    watcher = FileWatcher(target, debounce_ms=200)
    fired = []
    watcher.changed.connect(lambda: fired.append(1))
    target.write_bytes(b"[B]\r\n")
    target.write_bytes(b"[C]\r\n")
    qtbot.wait(700)
    assert len(fired) == 1
