"""Job Object: дерево серверов умирает вместе с лаунчером ([Ф] Б1/Б2 T-09)."""  # noqa: RUF002
import subprocess
import sys
import time

import psutil
import pytest

from onecstarter.platform_1c.job import JobError, NullJob, ServerJob


def _spawn_parent_with_grandchild() -> subprocess.Popen[str]:
    """Родитель, который создаёт внука не сразу — оставляя время на `assign()`.

    Задержка перед `Popen` внука обязательна и не косметическая: WinAPI не
    включает в Job уже существующие процессы задним числом. Если внук
    родился раньше, чем родитель попал в Job, `AssignProcessToJobObject`
    его не заденет, и kill-on-close его не погасит — измерено на этой
    машине 28.08.2026 двумя сценариями (`assign` до/после появления
    внука): «до» гасит обоих, «после» оставляет внука в живых. Эталон
    ([Ф] Б2 T-09, `e:\\tmp\\t09\\b2_job.py`) не попадал в эту гонку только
    потому, что `ragent` поднимает `rmngr`/`rphost` 25 секунд, а не
    мгновенно — `assign()` там гарантированно успевает первым. Тест
    воспроизводит тот же порядок (assign раньше рождения внука), а не
    порядок «внук уже точно есть», который эталонная механика в принципе
    не может покрыть.
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


class TestServerJob:
    def test_close_kills_parent_and_grandchild(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: kill-on-close гасит всё дерево ([Ф] Б1 T-09).

        Мутация «assign не кладёт процесс в Job» оставит дерево живым.
        """  # noqa: RUF002
        parent = _spawn_parent_with_grandchild()
        job = ServerJob()
        grandchild: int | None = None
        try:
            # handle Popen, как в проводке
            job.assign(int(parent._handle))  # type: ignore[attr-defined]
            assert parent.stdout is not None
            grandchild = int(parent.stdout.readline())
            job._close_for_tests()
            time.sleep(1)
            assert not psutil.pid_exists(parent.pid)
            assert not psutil.pid_exists(grandchild)
        finally:
            for pid in (parent.pid, grandchild):
                if pid is not None and psutil.pid_exists(pid):
                    psutil.Process(pid).kill()

    def test_assign_bad_handle_raises_job_error(self) -> None:
        job = ServerJob()
        with pytest.raises(JobError):
            job.assign(0)

    def test_null_job_is_a_no_op(self) -> None:
        NullJob().assign(0)  # не падает и ничего не делает
