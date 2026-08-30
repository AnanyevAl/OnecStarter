"""Job Object: дерево серверов умирает с лаунчером ([Ф] Б1/Б2 T-09) и видно
ОС ([Ф] 29.08.2026 T-12)."""  # noqa: RUF002
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psutil
import pytest

from onecstarter.platform_1c import job as job_module
from onecstarter.platform_1c.job import JobError, NullJob, ServerJob


def _spawn_parent_with_grandchild() -> subprocess.Popen[str]:
    """Родитель, который создаёт внука не сразу — оставляя время на `assign()`.

    Задержка перед `Popen` внука обязательна и не косметическая: WinAPI не
    включает в Job уже существующие процессы задним числом ([Ф] задача 1
    T-10: «до» гасит обоих, «после» оставляет внука в живых). Тест
    воспроизводит порядок «assign раньше рождения внука» — тот же, что в
    проде (`ragent` поднимает детей через ~12 с).
    """  # noqa: RUF002
    return subprocess.Popen(
        [sys.executable, "-c",
         "import subprocess,sys,time;"
         "time.sleep(1);"
         "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
         "print(p.pid,flush=True);time.sleep(120)"],
        stdout=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _wait_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return True
        time.sleep(0.05)
    return not psutil.pid_exists(pid)


@contextmanager
def _tree_in_job() -> Iterator[tuple[ServerJob, subprocess.Popen[str], int]]:
    """Родитель + внук, оба в Job; уборка обоих и закрытие Job в `finally`."""  # noqa: RUF002
    parent = _spawn_parent_with_grandchild()
    job = ServerJob()
    grandchild: int | None = None
    try:
        job.assign(int(parent._handle))  # type: ignore[attr-defined]
        assert parent.stdout is not None
        grandchild = int(parent.stdout.readline())
        time.sleep(0.3)  # внуку — дожить до попадания в список Job
        yield job, parent, grandchild
    finally:
        # `close()` — во ВЛОЖЕННОМ try (волна финального ревью ветки T-12,
        # п. 4): он умеет отказать `JobError` (`CloseHandle` вернул 0,
        # и хендл при этом СОХРАНЯЕТСЯ — правка ревью задачи 1), и стоя
        # первым в общем `finally` он уносил бы с собой уборку  # noqa: RUF003
        # процессов
        # — два `python -c "... time.sleep(120)"` пережили бы прогон
        # и остались бы на машине разработчика до перезагрузки.
        try:
            job.close()
        finally:
            # Уборка гонки с самим `job.close()`: kill-on-close  # noqa: RUF003
            # уже мог
            # погасить родителя/внука асинхронно между этой строкой
            # и следующей — окно «pid_exists() → Process(pid).kill()»
            # гонку не закрывает (found flaky: NoSuchProcess на .kill()
            # при полном прогоне и изредка на изолированном).
            # `NoSuchProcess` здесь — это успех уборки, а не  # noqa: RUF003
            # ошибка теста.
            for pid in (parent.pid, grandchild):
                if pid is not None:
                    try:
                        psutil.Process(pid).kill()
                    except psutil.NoSuchProcess:
                        pass
            parent.wait(timeout=5)


class TestServerJob:
    def test_close_kills_parent_and_grandchild(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: kill-on-close гасит всё дерево ([Ф] Б1 T-09).

        Мутация «assign не кладёт процесс в Job» оставит дерево живым.
        """  # noqa: RUF002
        with _tree_in_job() as (job, parent, grandchild):
            job.close()
            assert _wait_gone(parent.pid)
            assert _wait_gone(grandchild)

    def test_pids_lists_parent_and_grandchild(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: `pids()` отдаёт всё дерево ([Ф] 29.08.2026, проба
        `QueryInformationJobObject(JobObjectBasicProcessIdList)`).

        Мутация «`pids()` всегда возвращает `()`» обязана уронить этот тест.
        """  # noqa: RUF002
        with _tree_in_job() as (job, parent, grandchild):
            pids = set(job.pids())
            assert {parent.pid, grandchild} <= pids
            assert job.is_empty() is False

    def test_pids_keeps_remnants_after_parent_killed_externally(self) -> None:
        """[Ф] 29.08.2026: родитель снят извне (как `ragent` из Диспетчера) —
        внук остаётся в Job и виден в списке; родителя в списке уже нет.
        """
        with _tree_in_job() as (job, parent, grandchild):
            parent.kill()
            parent.wait(timeout=5)
            time.sleep(0.3)
            pids = set(job.pids())
            assert grandchild in pids
            assert parent.pid not in pids
            assert psutil.pid_exists(grandchild)

    def test_close_kills_remnants_after_external_kill(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: `close()` гасит остатки дерева ([Ф] 29.08.2026) —
        основание для «Погасить» и для гашения остатков в `start()` (T-12).

        Мутация «`close()` обнуляет `_handle`, не зовя `CloseHandle`» оставит
        внука в живых (хендл утечёт, kill-on-close не сработает).
        """  # noqa: RUF002
        with _tree_in_job() as (job, parent, grandchild):
            parent.kill()
            parent.wait(timeout=5)
            job.close()
            assert _wait_gone(grandchild), "остаток пережил закрытие Job"
            assert job.pids() == ()
            assert job.is_empty() is True

    def test_pids_of_fresh_job_is_empty(self) -> None:
        job = ServerJob()
        assert job.pids() == ()
        assert job.is_empty() is True

    def test_close_is_idempotent(self) -> None:
        job = ServerJob()
        job.close()  # Job ещё не создан — no-op
        with _tree_in_job() as (job, _parent, _grandchild):
            job.close()
            job.close()  # второй раз — тоже без исключения
            assert job.pids() == ()

    def test_pids_grows_buffer_on_error_more_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """[Д] буфер `JOBOBJECT_BASIC_PROCESS_ID_LIST` растёт при `ERROR_MORE_DATA`:
        стартовая ёмкость 1 заведомо меньше дерева из двух процессов (и их
        `conhost`), список обязан прийти целиком.
        """
        monkeypatch.setattr(job_module, "_PID_LIST_INITIAL_CAPACITY", 1)
        with _tree_in_job() as (job, parent, grandchild):
            assert {parent.pid, grandchild} <= set(job.pids())

    def test_assign_bad_handle_raises_job_error(self) -> None:
        job = ServerJob()
        try:
            with pytest.raises(JobError):
                job.assign(0)
        finally:
            job.close()

    def test_close_raises_and_keeps_handle_when_close_handle_fails(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: отказ `CloseHandle` не должен выглядеть как успешное
        закрытие (ревью задачи 1 T-12, Important 1).

        [Ф] 29.08.2026, эта машина: `CloseHandle` на заведомо невалидном
        хендле `0x7FFFFFFF` отказывает с `GetLastError() == 6`
        (`ERROR_INVALID_HANDLE`) — проверено отдельным скриптом перед
        написанием теста.

        Мутация «`close()` обнуляет `_handle` ДО проверки `CloseHandle`»
        уронит этот тест: после отказа `_handle` обязан остаться прежним
        (иначе повторный `close()` станет no-op, а `pids()`/`is_empty()`
        начнут врать, что Job пуст, хотя настоящий хендл никогда не был
        закрыт и утёк).
        """  # noqa: RUF002
        job = ServerJob()
        job._handle = 0x7FFFFFFF  # заведомо невалидный хендл — CloseHandle отказывает
        try:
            with pytest.raises(JobError):
                job.close()
            assert job._handle == 0x7FFFFFFF, "close() потерял хендл при отказе CloseHandle"
        finally:
            job._handle = None  # ничего реально не открыто — просто снять фейковое значение

    def test_pids_raises_job_error_when_query_fails_for_other_reason(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: отказ `QueryInformationJobObject` не по `ERROR_MORE_DATA`
        обязан всплыть `JobError`, а не тихо превратиться в пустой список.

        [Ф] 29.08.2026, эта машина: тот же невалидный хендл `0x7FFFFFFF`
        валит `QueryInformationJobObject` с `GetLastError() == 6`
        (`ERROR_INVALID_HANDLE`, не 234) — ветка «иначе» в `pids()`.
        """  # noqa: RUF002
        job = ServerJob()
        job._handle = 0x7FFFFFFF
        try:
            with pytest.raises(JobError):
                job.pids()
        finally:
            job._handle = None


class TestNullJob:
    def test_null_job_is_a_no_op(self) -> None:
        job = NullJob()
        job.assign(0)
        job.close()
        assert job.pids() == ()
        assert job.is_empty() is True
