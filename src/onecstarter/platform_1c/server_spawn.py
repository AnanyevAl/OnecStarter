"""Порождение серверных процессов 1С — скрытая консоль, файл-журнал, Job.

`CREATE_NO_WINDOW` вместо `DETACHED_PROCESS`, которым запускается клиент
(`process.py::spawn`): `DETACHED_PROCESS` лишает `ragent` консоли, и его дети
(`rmngr`, `rphost`, `dbgs`, `dbda`, `java` из `dbgs`), не найдя её, заводят
каждый своё окно — это и есть дефект ручного чек-листа 28.08.2026
(`docs/tasks.md`, «Находка ручного чек-листа»). Скрытая консоль
(`CREATE_NO_WINDOW`) даёт `ragent` консоль, просто невидимую, — дети её
наследуют и своих окон не открывают ([Ф] А3 T-09, `docs/research/t09-protocol.md`,
эксперимент T-09.4: «ни одного окна у всего дерева, дерево живо»).

stdout `ragent` перенаправляется в файл журнала. Ловить этим файлом весь
вывод дерева не получится и не нужно: баннеры `rmngr`/`rphost` существуют
только в их собственных окнах и не попадают ни в унаследованную консоль, ни
в редирект — в файле практически оказывается только строка `dbgs`, и это
ожидаемый результат, а не недостача ([Ф] А1 T-09, эксперимент T-09.2).

`job.assign()` обязан идти сразу после `Popen`, до того как `ragent`
породит первого ребёнка: `AssignProcessToJobObject` не поглощает уже
существующих потомков — находка задачи 1 T-10 (`platform_1c/job.py`,
`test_job.py::test_close_kills_parent_and_grandchild`). Между `Popen` и
`assign` стоит только выход из `with` (закрытие родительского хендла файла
журнала) — он намеренный и безопасный: закрытие родительской стороны
файла не влияет на уже унаследованный дочерним процессом дескриптор.
В проде запас времени до первого ребёнка ~12 c, но порядок вызовов здесь —
часть контракта, а не оптимизация под конкретный замер.

Если `job.assign()` откажет (`JobError`), уже порождённый процесс сервера
жёстко убивается здесь же, до того как исключение уйдёт наружу: сервер без
Job — это сервер без гарантии kill-on-close, ради которой всё строилось
(`platform_1c/job.py`), и оставлять его висеть в этом состоянии нельзя.
Жёсткое `process.kill()` (`TerminateProcess` под капотом) в этой ситуации
безопасно — то же решение, что и штатное завершение через Job Object
([Ф] Б2 T-07: `TerminateProcess` не портит файлы кластера).
"""  # noqa: RUF002

import subprocess
import warnings
from pathlib import Path

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.job import JobError, NullJob, ServerJob

__all__ = ["spawn_server"]


def spawn_server(command: LaunchCommand, log_path: Path, job: ServerJob | NullJob) -> int:
    """Запустить серверный процесс тихо, с редиректом stdout в `log_path`, в `job`.

    `OSError` (файл журнала не открылся, `Popen` не смог создать процесс)
    уходит наружу как есть: перевод в `ServerError` — дело вызывающего слоя
    (`services`), контракт T-08 этот модуль не меняет. `JobError` (отказ
    `job.assign()`) тоже уходит наружу как есть, но не раньше, чем уже
    порождённый процесс будет убит — сервер без Job здесь не оставляем.
    """  # noqa: RUF002
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            command.command_line,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    # КРИТИЧНО ([Ф] находка задачи 1 T-10, см. докстринг модуля): assign
    # сразу после Popen, до того как ragent породит первого ребёнка.
    try:
        job.assign(int(process._handle))  # type: ignore[attr-defined]
    except JobError:
        # Круг исправлений 1 (ревью задачи 2, Important): без Job процесс  # noqa: RUF003
        # не даёт той гарантии смерти с лаунчером, ради которой весь этот  # noqa: RUF003
        # модуль существует — сервер без Job не оставляем. Popen.kill()
        # на Windows уже безопасен, если процесс успел умереть сам
        # (ловит PermissionError и сверяет код выхода — cpython subprocess).
        process.kill()
        raise
    pid = process.pid
    # Процесс брошен намеренно: жизнь сервера определяет Job, а не время  # noqa: RUF003
    # жизни Popen-объекта. Тот же приём, что в process.py::spawn — точечно
    # подавляем ResourceWarning «subprocess N is still running» при del.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        del process
    return pid
