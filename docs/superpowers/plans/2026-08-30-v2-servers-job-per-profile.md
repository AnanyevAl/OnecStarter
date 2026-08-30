# T-12 «Job Object на профиль» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Управлять деревом процессов каждого запущенного профиля через собственный Job Object (истина о наших процессах — у ОС), а не через сопоставление по командной строке и снимок: «Остановить»/«Погасить» = закрыть Job, остатки прошлого запуска видны и гасятся, чужие держатели портов блокируют запуск, чужой `ragent` на нашем каталоге — только показ.

**Architecture:** `platform_1c/job.py` расширяется до `pids()/close()/is_empty()` (QueryInformationJobObject, [Ф] 29.08.2026); `services/servers.py` держит `dict[profile_id, Job]` + `dict[profile_id, pid]`, Job создаётся фабрикой на каждый `start()`, `stop()` = `close()`; `process_control.py` и всё сопоставление «сирот» удаляются, вместо них чистая функция `port_holders` в `domain/server_match.py`; UI — таблица четырёх состояний карточки, «Погасить» → `stop()`, удаление работающего профиля = остановка; `app.py` — `job_factory` вместо одного Job на лаунчер.

**Tech Stack:** Python ≥ 3.13, PySide6 (только ui), ctypes (kernel32: Job Object API), psutil (скан — без изменений), pytest.

Спека: [2026-08-29-v2-servers-job-per-profile-design.md](../specs/2026-08-29-v2-servers-job-per-profile-design.md) (решения заказчика 29.08.2026). Исходная спека v2: [2026-08-26-v2-servers-design.md](../specs/2026-08-26-v2-servers-design.md).
Ветка: **новая**, от `master` ПОСЛЕ слияния `feat/2026-08-26-v2-servers` (T-08/T-10): `feat/2026-08-30-v2-job-per-profile`. Если слияние ещё не состоялось — план не начинать (спека T-12, преамбула).

## Global Constraints

- Qt только в `src/onecstarter/ui/`; `CORE` в `tests/unit/test_no_qt_in_core.py` правится в той же задаче, что удаляет/добавляет модуль ядра.
- Истина о наших процессах — только `Job.pids()`; `services` НЕ сопоставляет наши процессы по argv и не зовёт `psutil` ради остановки. Скан (`process_scan.py`, `ServerMonitor`) остаётся для чужих серверов, чужих держателей портов и состояния «работает (запущен не лаунчером)».
- Чужим не управляем никогда (решение 4): нет ни одного пути кода, который завершает процесс, не входящий в наш Job.
- Job в `services` приходит инъекцией: `job_factory: Callable[[], Job]` и `server_spawn: Callable[[LaunchCommand, Path, Job], int]` — оба обязательные, без дефолта; `ServerJob` в проде, `NullJob` в `run_smoke`.
- Тексты событий журнала — дословно из спеки T-12 §6: `погашены остатки прошлого запуска: PID …`; `ragent завершился извне; остатки дерева: PID …`; `отказ запуска: порт регистрации N занят PID … (запущен не лаунчером)`; остаются `запуск: …`, `порождён PID N`, `работает · PID N`, `остановка по команде пользователя`, `отказ остановки: …`, `отказ запуска: …`, `ротация журнала не удалась (…)`, `выход лаунчера — сервер будет остановлен вместе с ним`. Удаляются `гашение сирот: PID …`.
- Порядок `start()` (спека §3): проверки → живой наш `ragent` в Job → совпавший процесс снимка (§6.4) → чужие держатели портов (отказ ДО ротации и spawn) → остатки в Job (`close()`; ОТКАЗ `close` — тоже отказ запуска, ДО ротации) → новый Job → best-effort ротация → событие `погашены остатки прошлого запуска: PID …` → `запуск: …` → spawn → `порождён PID`. Событие успешного гашения — ПОСЛЕ ротации (правка вслед за находкой задачи 3, 30.08.2026: `rotate_journal` переименовывает текущий файл в `.1.log`, и записанное до неё событие уехало бы в журнал прошлого запуска, тогда как §10 п.3 требует видеть его в ТЕКУЩЕМ журнале рядом со стартом, который оно объясняет).
- ctypes-гигиена в новом/правленом коде `platform_1c`: один `WinDLL` на модуль, `argtypes`/`restype` у каждой функции, `use_last_error=True`, отказ WinAPI → `JobError` с `GetLastError`.
- Проверки: `uv run pytest` (ОБЫЧНЫЙ режим, не фоновый; suite, не завершившийся за 5 мин, — зависание на модальном диалоге), `uv run ruff check .`, `uv run mypy` — коды 0 после каждой задачи; mypy strict вне `onecstarter.ui.*`.
- Тесты не запускают живой `ragent` (правило «Границы»); Job тестируется подставными python-процессами, каждый — `kill()`+`wait()` в `finally`.
- Защитные тесты — докстринг начинается с «ЗАЩИТНЫЙ ТЕСТ» и называет мутацию; их мутации ставит независимый агент (задача 7).
- Подписи UI по-русски; цвета — только роли `Palette` (`accent`/`text_dim`/`problem`); кнопки диалогов — `ask_confirmation` (дефолт «Нет»).
- Реальные пути машины заказчика, hostname и каталог кластера в docs/tests не попадают.

## Карта файлов

| Файл | Что с ним | Задача |
| --- | --- | --- |
| `src/onecstarter/platform_1c/job.py` | `Job(Protocol)` расширен; `ServerJob.pids/close/is_empty`; ctypes-гигиена; `_close_for_tests` удалён | 1 |
| `src/onecstarter/platform_1c/server_spawn.py` | `spawn_server(command, log_path, job: Job)` | 1 |
| `src/onecstarter/domain/server_match.py` | `port_holders`, `port_holders_text` (чистые) | 2 |
| `src/onecstarter/services/servers.py` | Job на профиль: конструктор, `start/stop/remove_profile/statuses/port_holders/running_count/log_shutdown`; `apply_scan` — реконсиляция | 3, 4 |
| `src/onecstarter/services/errors.py` | `ServerStopError` удалён | 3 |
| `src/onecstarter/platform_1c/process_control.py` | удалён целиком | 3 |
| `src/onecstarter/ui/app.py` | `job_factory` вместо `server_job`/`process_control` | 3 |
| `src/onecstarter/ui/servers/view.py` | таблица состояний, остатки/«Погасить», держатели портов, диалог удаления | 3 (минимум), 5 |
| `docs/superpowers/specs/2026-08-26-v2-servers-design.md`, мокап, `docs/tasks.md` | синхронизация | 6 |
| `tests/unit/test_job.py`, `test_server_spawn.py`, `test_server_match.py`, `test_servers.py`, `test_no_qt_in_core.py`; `tests/ui/test_servers_view.py`, `test_app.py` | по задачам | 1–5 |

---

### Task 1: Job — `pids()`, `close()`, `is_empty()`, протокол; `spawn_server` по протоколу

**Files:**
- Modify: `src/onecstarter/platform_1c/job.py`
- Modify: `src/onecstarter/platform_1c/server_spawn.py` (сигнатура `spawn_server`, импорт)
- Test: `tests/unit/test_job.py`, `tests/unit/test_server_spawn.py`

**Interfaces:**
- Consumes: существующий `ServerJob.assign(process_handle: int) -> None`, `JobError`, `NullJob`.
- Produces:
  - `class Job(Protocol)`: `assign(self, process_handle: int) -> None`; `pids(self) -> tuple[int, ...]`; `close(self) -> None`; `is_empty(self) -> bool`. Экспортируется в `__all__`.
  - `ServerJob.pids() -> tuple[int, ...]` — PID всех процессов, СЕЙЧАС находящихся в Job (всё дерево, включая `conhost` и прочих посредников — [Ф] 29.08.2026); `()` пока Job не создан (до первого `assign`) или после `close()`.
  - `ServerJob.close() -> None` — `CloseHandle` (kill-on-close гасит всё, что в Job); идемпотентно: второй вызов — no-op; после него `pids() == ()`.
  - `ServerJob.is_empty() -> bool` — `not self.pids()`.
  - `NullJob`: `pids() == ()`, `close()` no-op, `is_empty() == True`.
  - `spawn_server(command: LaunchCommand, log_path: Path, job: Job) -> int` — тип параметра теперь протокол.
  - Константы модуля `job.py`: `JobObjectBasicProcessIdList = 3`, `_ERROR_MORE_DATA = 234`, `_PID_LIST_INITIAL_CAPACITY = 64` (читается при каждом вызове `pids()` — тест подменяет её через `monkeypatch`).

- [ ] **Step 1: Переписать `tests/unit/test_job.py` — падающие тесты**

Заменить файл целиком:

```python
"""Job Object: дерево серверов умирает с лаунчером ([Ф] Б1/Б2 T-09) и видно ОС ([Ф] 29.08.2026 T-12)."""  # noqa: RUF002
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
    """Родитель + внук, оба в Job; уборка обоих и закрытие Job в `finally`."""
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
        job.close()
        # Находка исполнителя задачи 1: kill-on-close гасит дерево асинхронно —
        # между pid_exists() и kill() процесс мог уже умереть (1 флейк из 5
        # прогонов). Уборка терпит NoSuchProcess, а не проверяет заранее.
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
        """  # noqa: RUF002
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
        """  # noqa: RUF002
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


class TestNullJob:
    def test_null_job_is_a_no_op(self) -> None:
        job = NullJob()
        job.assign(0)
        job.close()
        assert job.pids() == ()
        assert job.is_empty() is True
```

- [ ] **Step 2: RED** — `uv run pytest tests/unit/test_job.py -q` → `AttributeError: 'ServerJob' object has no attribute 'close'` / `pids`.

- [ ] **Step 3: Реализация `job.py`**

Переписать модуль. Докстринг модуля обновить: Job теперь — **на каждый запуск профиля** (T-12, спека §3); хендл закрывается явно в `stop()`/«Погасить»/гашении остатков (`close()`), а при смерти лаунчера — самой ОС (гарантия §12.4 сохраняется). Абзац «держит хендл открытым до конца процесса намеренно» — убрать (он больше не верен). Факт [Ф] 29.08.2026 (проба `QueryInformationJobObject`: список содержит всё дерево, остатки после внешнего убийства родителя видны, `CloseHandle` гасит их все, пустой Job даёт `(0, ())`) — в докстринг `pids()`.

```python
import ctypes
from ctypes import wintypes
from typing import Any, Protocol

__all__ = ["Job", "JobError", "NullJob", "ServerJob"]

JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_ERROR_MORE_DATA = 234
_PID_LIST_INITIAL_CAPACITY = 64

# Один WinDLL на модуль, argtypes/restype у каждой функции (долг T-10 «гигиена ctypes»).
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateJobObjectW.restype = wintypes.HANDLE
_k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_k32.SetInformationJobObject.restype = wintypes.BOOL
_k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_k32.AssignProcessToJobObject.restype = wintypes.BOOL
_k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_k32.QueryInformationJobObject.restype = wintypes.BOOL
_k32.QueryInformationJobObject.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

# IO_COUNTERS / JOBOBJECT_BASIC_LIMIT_INFORMATION / JOBOBJECT_EXTENDED_LIMIT_INFORMATION — как есть.


def _pid_list_type(capacity: int) -> Any:
    """`JOBOBJECT_BASIC_PROCESS_ID_LIST` с массивом на `capacity` записей (ULONG_PTR = c_size_t)."""

    class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * capacity),
        ]

    return JOBOBJECT_BASIC_PROCESS_ID_LIST


class JobError(Exception):
    """Отказ вызова WinAPI Job Object (создание, assign, чтение списка, закрытие)."""


class Job(Protocol):
    def assign(self, process_handle: int) -> None: ...
    def pids(self) -> tuple[int, ...]: ...
    def close(self) -> None: ...
    def is_empty(self) -> bool: ...


class ServerJob:
    def __init__(self) -> None:
        self._handle: int | None = None

    def assign(self, process_handle: int) -> None:
        if self._handle is None:
            self._handle = self._create_job()
        if not _k32.AssignProcessToJobObject(self._handle, process_handle):
            error = ctypes.get_last_error()
            raise JobError(
                f"AssignProcessToJobObject не смог поместить процесс в Job: GetLastError={error}"
            )

    def pids(self) -> tuple[int, ...]:
        if self._handle is None:
            return ()
        capacity = _PID_LIST_INITIAL_CAPACITY
        while True:
            buffer: Any = _pid_list_type(capacity)()
            ok = _k32.QueryInformationJobObject(
                self._handle, JobObjectBasicProcessIdList,
                ctypes.byref(buffer), ctypes.sizeof(buffer), None,
            )
            if ok:
                count = int(buffer.NumberOfProcessIdsInList)
                return tuple(int(buffer.ProcessIdList[i]) for i in range(count))
            error = ctypes.get_last_error()
            if error != _ERROR_MORE_DATA:
                raise JobError(
                    f"QueryInformationJobObject не смог прочитать список процессов Job: "
                    f"GetLastError={error}"
                )
            capacity = max(capacity * 2, int(buffer.NumberOfAssignedProcesses))

    def close(self) -> None:
        if self._handle is None:
            return
        # Ревью задачи 1 (Important 1): хендл забывается ТОЛЬКО после успешного
        # CloseHandle — иначе после отказа Job выглядел бы закрытым (pids() == ()),
        # хотя дерево живо, и services не смог бы показать остатки.
        if not _k32.CloseHandle(self._handle):
            error = ctypes.get_last_error()
            raise JobError(f"CloseHandle не смог закрыть Job: GetLastError={error}")
        self._handle = None

    def is_empty(self) -> bool:
        return not self.pids()

    @staticmethod
    def _create_job() -> int:
        handle = _k32.CreateJobObjectW(None, None)
        if not handle:
            error = ctypes.get_last_error()
            raise JobError(f"CreateJobObjectW не смог создать Job: GetLastError={error}")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _k32.SetInformationJobObject(
            handle, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            error = ctypes.get_last_error()
            _k32.CloseHandle(handle)
            raise JobError(
                f"SetInformationJobObject не смог включить kill-on-close: GetLastError={error}"
            )
        return int(handle)


class NullJob:
    def assign(self, process_handle: int) -> None: ...
    def pids(self) -> tuple[int, ...]:
        return ()
    def close(self) -> None: ...
    def is_empty(self) -> bool:
        return True
```

`_close_for_tests` удалить. `ruff` может потребовать `# noqa: E501` на строке `argtypes` `QueryInformationJobObject` — переносить список по элементам, не глушить.

- [ ] **Step 4: `server_spawn.py`** — импорт `from onecstarter.platform_1c.job import Job, JobError`; сигнатура `def spawn_server(command: LaunchCommand, log_path: Path, job: Job) -> int`. В докстринге модуля абзац «`ServerJob` держит хендл открытым до конца процесса» заменить на: Job — на запуск профиля (T-12), закрывается `ServersWorkspace.stop()`; при смерти лаунчера — ОС. Остальное без изменений.

- [ ] **Step 5: `tests/unit/test_server_spawn.py`** — `job._close_for_tests()` → `job.close()` (в `test_spawn_server_process_dies_when_job_closes`); `_FailingJob` — больше не наследник `ServerJob`, самостоятельный класс со всеми четырьмя методами (`assign` → `raise JobError(...)`, `pids` → `()`, `close` → no-op, `is_empty` → `True`), докстринг: «протокол `Job`, наследование не нужно (долг T-10 «закрытая уния» закрыт)».

- [ ] **Step 6: GREEN** — `uv run pytest tests/unit/test_job.py tests/unit/test_server_spawn.py tests/unit/test_no_qt_in_core.py -q`. Затем полный `uv run pytest -q` (обычный режим), `uv run ruff check .`, `uv run mypy` — все 0. После прогона убедиться, что подставных python-процессов не осталось: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'time.sleep\(120\)' }` — пусто.

- [ ] **Step 7: Коммит** — `feat: T-12 — Job: pids/close/is_empty, протокол Job, ctypes-гигиена (задача 1)`.

---

### Task 2: Чужие держатели портов — чистые функции `port_holders` / `port_holders_text`

**Files:**
- Modify: `src/onecstarter/domain/server_match.py`
- Test: `tests/unit/test_server_match.py`

**Interfaces:**
- Consumes: `RagentProcess`, `extract_ragent_params`, `ServerProfile` (есть).
- Produces:
  - `port_holders(profile: ServerProfile, processes: Sequence[RagentProcess], exclude_pids: Set[int]) -> tuple[RagentProcess, ...]` — процессы снимка (любого имени: `ragent`/`rmngr`), чьи `-port`/`-regport` совпадают с портами профиля и чей PID не в `exclude_pids`. Правило: `params.port in {profile.port, profile.regport}` ИЛИ `params.regport == profile.regport` ([Ф] А3 T-07: у `rmngr` собственный `-port` равен `-regport` агента, поэтому `rmngr` на нашем `regport` — держатель). `argv is None` — пропуск (непрозрачный процесс, сопоставить нечем). Порядок — как во входе.
  - `port_holders_text(profile: ServerProfile, holders: Sequence[RagentProcess]) -> str` — текст красной строки и отказа `start()`. Три формы: только `regport` → `порт регистрации {regport} занят PID {pids} (запущен не лаунчером)`; только `port` → `порт {port} занят PID {pids} (запущен не лаунчером)`; оба → `порты {port} и {regport} заняты PID {pids} (запущен не лаунчером)`. `pids` — через `", "`.

Функция чистая: множество наших PID подаёт `services` (Task 3), сам Job здесь не появляется.

- [ ] **Step 1: Падающие табличные тесты** — дописать в конец `tests/unit/test_server_match.py`:

```python
from onecstarter.domain.server_match import port_holders, port_holders_text  # в блок импортов


def _holder(pid: int, name: str, *args: str) -> RagentProcess:
    return RagentProcess(
        pid=pid, executable=None, argv=(name, *args), create_time=100.0 + pid
    )


class TestPortHolders:
    PROFILE = _profile(port=1540, regport=1541, cluster_dir=r"E:\srv\a")

    @pytest.mark.parametrize(
        ("process", "expected"),
        [
            (_holder(1, "rmngr.exe", "-port", "1541"), True),  # [Ф] А3: rmngr на нашем regport
            (_holder(2, "ragent.exe", "-port", "1540", "-regport", "9541", "-d", r"D:\x"), True),
            (_holder(3, "ragent.exe", "-port", "9540", "-regport", "1541", "-d", r"D:\x"), True),
            (_holder(4, "rmngr.exe", "-port", "2541"), False),  # чужие порты
            (_holder(5, "ragent.exe", "-port", "2540", "-regport", "2541"), False),
            (_holder(6, "rmngr.exe", "-port", "хлам"), False),  # порт не число
        ],
    )
    def test_table(self, process: RagentProcess, expected: bool) -> None:
        assert (port_holders(self.PROFILE, [process], frozenset()) == (process,)) is expected

    def test_opaque_process_is_skipped(self) -> None:
        opaque = RagentProcess(pid=7, executable=None, argv=None, create_time=107.0)
        assert port_holders(self.PROFILE, [opaque], frozenset()) == ()

    def test_own_job_pids_are_excluded(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: процесс из НАШЕГО Job — не «чужой держатель», а
        остаток (спека T-12 §4). Мутация «не смотреть `exclude_pids`» уронит тест.
        """  # noqa: RUF002
        ours = _holder(8, "rmngr.exe", "-port", "1541")
        alien = _holder(9, "rmngr.exe", "-port", "1541")
        assert port_holders(self.PROFILE, [ours, alien], frozenset({8})) == (alien,)

    def test_order_is_preserved(self) -> None:
        first = _holder(10, "rmngr.exe", "-port", "1541")
        second = _holder(11, "ragent.exe", "-port", "1540")
        assert port_holders(self.PROFILE, [second, first], frozenset()) == (second, first)


class TestPortHoldersText:
    PROFILE = _profile(port=1540, regport=1541, cluster_dir=r"E:\srv\a")

    def test_regport_only(self) -> None:
        holders = [_holder(300, "rmngr.exe", "-port", "1541"), _holder(301, "rmngr.exe", "-port", "1541")]
        assert port_holders_text(self.PROFILE, holders) == (
            "порт регистрации 1541 занят PID 300, 301 (запущен не лаунчером)"
        )

    def test_port_only(self) -> None:
        holders = [_holder(302, "ragent.exe", "-port", "1540", "-regport", "9541")]
        assert port_holders_text(self.PROFILE, holders) == (
            "порт 1540 занят PID 302 (запущен не лаунчером)"
        )

    def test_both_ports(self) -> None:
        holders = [_holder(303, "ragent.exe", "-port", "1540", "-regport", "1541")]
        assert port_holders_text(self.PROFILE, holders) == (
            "порты 1540 и 1541 заняты PID 303 (запущен не лаунчером)"
        )
```

- [ ] **Step 2: RED** — `uv run pytest tests/unit/test_server_match.py -q` → `ImportError: cannot import name 'port_holders'`.

- [ ] **Step 3: Реализация** — в `server_match.py` (импорт `Set` из `collections.abc` — находка исполнителя задачи 2: `collections.abc.AbstractSet` не существует, есть только устаревший `typing.AbstractSet`):

```python
def _held_ports(profile: ServerProfile, params: RagentParams) -> set[int]:
    """Какие порты ПРОФИЛЯ держит процесс с такими параметрами."""
    held: set[int] = set()
    if params.port is not None and params.port in (profile.port, profile.regport):
        held.add(params.port)
    if params.regport is not None and params.regport == profile.regport:
        held.add(profile.regport)
    return held


def port_holders(
    profile: ServerProfile,
    processes: Sequence[RagentProcess],
    exclude_pids: Set[int],
) -> tuple[RagentProcess, ...]:
    """Чужие процессы снимка, держащие порты профиля (спека T-12 §4).

    [Ф] А3 T-07: `rmngr` переживает `ragent` и держит его `regport` своим
    `-port`; новый `ragent` поверх такого держателя поднимается полумёртвым
    (находка 5 чек-листа T-10). Наши процессы (`exclude_pids` — все PID
    наших Job) — не держатели, а остатки; непрозрачный процесс (`argv is
    None`) пропускается — выдумывать сопоставление нельзя.
    """  # noqa: RUF002
    holders: list[RagentProcess] = []
    for process in processes:
        if process.pid in exclude_pids or process.argv is None:
            continue
        if _held_ports(profile, extract_ragent_params(process.argv)):
            holders.append(process)
    return tuple(holders)


def port_holders_text(profile: ServerProfile, holders: Sequence[RagentProcess]) -> str:
    ports: set[int] = set()
    for holder in holders:
        if holder.argv is not None:
            ports |= _held_ports(profile, extract_ragent_params(holder.argv))
    pids = ", ".join(str(holder.pid) for holder in holders)
    if ports == {profile.regport}:
        return f"порт регистрации {profile.regport} занят PID {pids} (запущен не лаунчером)"
    if ports == {profile.port}:
        return f"порт {profile.port} занят PID {pids} (запущен не лаунчером)"
    return f"порты {profile.port} и {profile.regport} заняты PID {pids} (запущен не лаунчером)"
```

- [ ] **Step 4: GREEN** — `uv run pytest tests/unit/test_server_match.py -q`; `ruff`, `mypy`.

- [ ] **Step 5: Коммит** — `feat: T-12 — port_holders/port_holders_text: чужие держатели портов профиля (задача 2)`.

---

### Task 3: Координатор — Job на запуск профиля; удаление `process_control`; проводка `app.py`

Самая большая задача вехи: меняется контракт `ServersWorkspace`, и всё, что его использует (`app.py`, `view.py`, три тестовых файла), обязано остаться зелёным в ЭТОЙ задаче. UI здесь правится **минимально** — только то, что перестаёт компилироваться/проходить из-за нового контракта (перечислено в Step 8); таблица состояний карточки, диалоги удаления и §8 по Job — задача 5.

**Files:**
- Modify: `src/onecstarter/services/servers.py`
- Modify: `src/onecstarter/services/errors.py` (удалить `ServerStopError`)
- Delete: `src/onecstarter/platform_1c/process_control.py`, `tests/unit/test_process_control.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (убрать строку `"onecstarter.platform_1c.process_control",`)
- Modify: `src/onecstarter/ui/app.py` (`_build_main_window`, `run_smoke`)
- Modify: `src/onecstarter/ui/servers/view.py` (минимум — Step 8)
- Test: `tests/unit/test_servers.py`, `tests/ui/test_servers_view.py`, `tests/ui/test_app.py`

**Interfaces:**
- Consumes: `Job`, `JobError`, `ServerJob`, `NullJob` (задача 1); `port_holders`, `port_holders_text` (задача 2); `spawn_server(command, log_path, job)`.
- Produces:
  - `ServersWorkspace.__init__(self, store_path: Path, *, job_factory: Callable[[], Job], server_spawn: Callable[[LaunchCommand, Path, Job], int], logs_dir: Path, run_elevated=…, open_file=…, registered_radmin=…, new_id=…, now=…)` — параметр `control` удалён.
  - `ServerStatus` (frozen dataclass, остаётся в `services/servers.py` — спека §5 называет `domain/server_match.py`, но класс живёт здесь с T-08, переносить незачем): `profile`, `resolved`, `processes: tuple[RagentProcess, ...]` (ragent снимка, совпавшие по каталогу — наши и чужие), `job_pids: tuple[int, ...]` (всё дерево нашего Job; `()` — Job нет или пуст), `spawned_pid: int | None` (PID порождённого нами `ragent`; `None` — запускали не мы либо `ragent` завершился извне и это уже отмечено, задача 4), `port_holders: tuple[RagentProcess, ...]` (чужие держатели портов), `dir_mismatch: bool`. Поле `orphans` удалено.
  - `port_holders(self, profile_id: str) -> list[RagentProcess]` — вместо `orphan_managers`; `[]` до первого снимка и когда у профиля есть совпавший `ragent` в снимке (живой `ragent` на нашем каталоге — наш или чужой — уже описан состоянием карточки, красная строка о портах была бы шумом).
  - `start(profile_id, server_installations) -> int` — порядок из Global Constraints.
  - `stop(profile_id) -> None` — `close()` Job профиля; Job нет/пуст → `ServerError` («нечего останавливать»); `JobError` → событие `отказ остановки: …` + `ServerError`.
  - `remove_profile(profile_id) -> None` — при непустом Job сначала `stop()` (его `ServerError` — наружу, профиль остаётся); пустой Job — тихо освобождается.
  - `running_count() -> int`, `log_shutdown() -> int` — по профилям с НЕПУСТЫМ Job (`job.pids()`), снимок не участвует.
  - Удалены: `orphan_managers`, `stop_orphans`, `_terminate_or_raise`, `_orphans_for`, `ServerStopError`, модуль `process_control`.
  - `_build_main_window(..., job_factory: Callable[[], Job] | None = None)` — `None` → `ServerJob`; параметры `process_control` и `server_job` удалены; `run_smoke` передаёт `job_factory=NullJob`.

- [ ] **Step 1: Фейки и хелперы в `tests/unit/test_servers.py`**

Удалить `FakeControl` и импорты `ProcessAccessError`/`ProcessMismatchError`/`ServerStopError`. Добавить (импорты: `from collections.abc import Callable`, `from onecstarter.platform_1c.job import Job, JobError`):

```python
@dataclass
class FakeJob:
    """Job с управляемым списком PID (T-12): `pids_value` — что «живёт» в Job;
    `close()` опустошает список и ставит `closed`; `close_error` — `JobError`,
    который поднимает `close()` вместо закрытия."""  # noqa: RUF002

    pids_value: tuple[int, ...] = ()
    closed: bool = False
    close_error: JobError | None = None
    assigned: list[int] = field(default_factory=list)

    def assign(self, process_handle: int) -> None:
        self.assigned.append(process_handle)

    def pids(self) -> tuple[int, ...]:
        return () if self.closed else self.pids_value

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def is_empty(self) -> bool:
        return not self.pids()


@dataclass
class FakeJobFactory:
    """`job_factory`: новый пустой `FakeJob` на каждый вызов, все созданные — в `created`."""

    created: list[FakeJob] = field(default_factory=list)

    def __call__(self) -> FakeJob:
        job = FakeJob()
        self.created.append(job)
        return job


@dataclass
class FakeServerSpawn:
    """Журнал вызовов `server_spawn` (T-12: третий аргумент — Job запуска).

    Как настоящий `spawn_server`, кладёт «порождённый» `pid` в переданный
    `FakeJob` — после успешного вызова `job.pids()` содержит `pid`.
    `probe`, если задан, вызывается В МОМЕНТ spawn, результат — в `probed`:
    так тест проверяет состояние мира (например, «старый Job уже закрыт»)
    именно на границе порождения, а не после возврата из `start()`.
    """  # noqa: RUF002

    pid: int = 4242
    error: Exception | None = None
    probe: Callable[[], object] | None = None
    calls: list[tuple[str, Path, Job]] = field(default_factory=list)
    probed: list[object] = field(default_factory=list)

    def __call__(self, command: LaunchCommand, log_path: Path, job: Job) -> int:
        self.calls.append((command.command_line, log_path, job))
        if self.probe is not None:
            self.probed.append(self.probe())
        if self.error is not None:
            raise self.error
        if isinstance(job, FakeJob):
            job.pids_value = (*job.pids_value, self.pid)
        return self.pid
```

`_workspace(...)`: параметр `control` → `job_factory: object = None`; в `kwargs`: `"job_factory": job_factory if job_factory is not None else FakeJobFactory()`. Хелпер установки:

```python
def _installation_in(tmp_path: Path) -> ServerInstallation:
    return _server_installation(
        "8.3.25.1633", tmp_path / "1cv8" / "8.3.25.1633" / "bin" / "ragent.exe"
    )
```

Все существующие тесты `TestStart`, распаковывающие `spawn.calls[0]` в пару, — теперь тройка `(command_line, log_path, job)`.

- [ ] **Step 2: Новые падающие тесты (`tests/unit/test_servers.py`)**

Удалить классы `TestOrphanManagers`, `TestStopOrphans`; в `TestStop` удалить `test_stop_kills_exactly_matched_pid_and_children`, `test_stop_mismatched_create_time_raises_and_kills_nobody`, `test_stop_mismatched_child_also_raises_honestly`, `test_stop_access_denied_raises_server_stop_error`, `test_stop_failure_logs_refusal_before_raise`, `test_stop_without_snapshot_raises`, `test_stop_without_matched_process_raises`; `test_stop_success_logs_event` — профиль запускается через `start()`. `TestScanPending.test_statuses_before_scan_are_empty_not_stopped`: `status.orphans == ()` → `status.port_holders == ()` и `status.job_pids == ()`. Добавить:

```python
class TestStartWithJob:
    def test_start_creates_a_job_per_launch_and_records_spawned_pid(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ja" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        pid = workspace.start(profile.id, [_installation_in(tmp_path)])

        assert pid == 4242
        assert len(factory.created) == 1
        assert spawn.calls[0][2] is factory.created[0]
        status = workspace.statuses([])[0]
        assert status.job_pids == (4242,)
        assert status.spawned_pid == 4242
        assert workspace.running_count() == 1

    def test_start_refuses_while_own_ragent_is_alive_in_job(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: истина о нашем ragent — Job, не снимок (спека T-12 §3).

        Второй `start()` сразу после первого (снимка ещё не было) обязан
        отказать по `spawned_pid in job.pids()`, не порождая второй ragent.
        Мутация: убрать проверку живого ragent в Job — тест обязан упасть
        (второй spawn состоится).
        """  # noqa: RUF002
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jb" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

        assert "4242" in str(excinfo.value)
        assert len(spawn.calls) == 1
        assert len(factory.created) == 1

    def test_start_with_remnants_closes_old_job_before_spawn_and_logs(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: решение 2 (29.08.2026) — «Запустить» при остатках
        прошлого дерева гасит их САМ (закрывает старый Job) ДО spawn и пишет
        `погашены остатки прошлого запуска: PID …`.
        Мутация: перенести `old_job.close()` после `server_spawn` (или убрать) —
        `spawn.probed[0]` станет `False`.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jc" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        old = factory.created[0]
        old.pids_value = (4300, 4301)  # ragent 4242 снят извне, дети остались
        spawn.pid = 4343
        spawn.probe = lambda: old.closed

        pid = workspace.start(profile.id, [installation])

        assert pid == 4343
        assert spawn.probed == [True]
        assert spawn.calls[1][2] is factory.created[1]
        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "погашены остатки прошлого запуска: PID 4300, 4301" in content
        assert content.index("погашены остатки") < content.index("запуск:")
        status = workspace.statuses([])[0]
        assert status.job_pids == (4343,)
        assert status.spawned_pid == 4343

    def test_start_refuses_when_a_foreign_process_holds_the_profile_port(
        self, tmp_path: Path
    ) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: чужой держатель порта (спека T-12 §4) — отказ ДО
        ротации и spawn, событие `отказ запуска: порт регистрации …`.
        Мутация: убрать проверку `port_holders` в `start` — тест обязан упасть
        (spawn состоится, прошлый журнал уедет в `.1.log`).
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn()
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jd" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())  # regport=1541
        profile = workspace.profiles()[0]
        current = server_journal.journal_path(logs_dir, profile.id)
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_text("прошлый запуск\n", encoding="utf-8")
        holder = _manager(300, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(holder,)))

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [_installation_in(tmp_path)])

        expected = "порт регистрации 1541 занят PID 300 (запущен не лаунчером)"
        assert expected in str(excinfo.value)
        assert spawn.calls == []
        assert factory.created == []
        assert not server_journal.previous_journal_path(logs_dir, profile.id).exists()
        content = current.read_text(encoding="utf-8")
        assert "прошлый запуск" in content
        assert f"отказ запуска: {expected}" in content

    def test_start_does_not_treat_own_remnants_as_port_holders(self, tmp_path: Path) -> None:
        """Остаток НАШЕГО дерева (PID в нашем Job) в снимке с нашим regport —
        не чужой держатель: запуск проходит, остатки гасятся (решение 2)."""
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "je" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        factory.created[0].pids_value = (4300,)
        remnant = _manager(4300, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(remnant,)))
        assert workspace.port_holders(profile.id) == []

        workspace.start(profile.id, [installation])

        assert factory.created[0].closed is True
        assert len(spawn.calls) == 2

    def test_start_spawn_failure_closes_the_fresh_job_and_forgets_it(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(error=OSError("не удалось создать процесс"))
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jf" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]

        with pytest.raises(ServerError):
            workspace.start(profile.id, [_installation_in(tmp_path)])

        assert factory.created[0].closed is True
        assert workspace.statuses([])[0].job_pids == ()
        assert workspace.running_count() == 0

    def test_start_reports_failed_remnant_close_and_keeps_remnants(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "jg" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        installation = _installation_in(tmp_path)
        workspace.start(profile.id, [installation])
        old = factory.created[0]
        old.pids_value = (4300,)
        old.close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError) as excinfo:
            workspace.start(profile.id, [installation])

        assert "CloseHandle отказал" in str(excinfo.value)
        assert len(spawn.calls) == 1
        assert workspace.statuses([])[0].job_pids == (4300,)
        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ запуска: не удалось погасить остатки прошлого запуска" in content


class TestStopWithJob:
    def test_stop_closes_only_this_profiles_job(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: `stop()` закрывает Job ИМЕННО этого профиля; сосед
        жив. Мутация: закрывать все Job — тест обязан упасть.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        ids = iter(["ka" * 16, "kb" * 16])
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: next(ids),
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        first, second = workspace.profiles()
        installation = _installation_in(tmp_path)
        workspace.start(first.id, [installation])
        spawn.pid = 4343
        workspace.start(second.id, [installation])

        workspace.stop(first.id)

        assert factory.created[0].closed is True
        assert factory.created[1].closed is False
        statuses = {s.profile.id: s for s in workspace.statuses([])}
        assert statuses[first.id].job_pids == ()
        assert statuses[first.id].spawned_pid is None
        assert statuses[second.id].job_pids == (4343,)
        content = server_journal.journal_path(logs_dir, first.id).read_text(encoding="utf-8")
        assert "остановка по команде пользователя" in content

    def test_stop_without_job_raises(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "kc" * 16)
        workspace.add_profile(_profile())
        with pytest.raises(ServerError):
            workspace.stop(workspace.profiles()[0].id)

    def test_stop_ignores_a_foreign_matched_ragent(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: решение 4 — совпавший по каталогу ЧУЖОЙ ragent не
        останавливается: Job нет → `ServerError`, ни одного Job не создано.
        Мутация: вернуть остановку по совпавшим процессам снимка — упадёт.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        workspace = _workspace(
            tmp_path / "servers.json", new_id=lambda: "kd" * 16, job_factory=factory
        )
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

        assert factory.created == []

    def test_stop_with_empty_job_raises_and_forgets_it(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ke" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        factory.created[0].pids_value = ()  # дерево умерло целиком

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

        assert factory.created[0].closed is True
        assert workspace.running_count() == 0

    def test_stop_close_failure_logs_refusal_and_raises_server_error(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        logs_dir = tmp_path / "logs"
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "kf" * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=logs_dir)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        factory.created[0].close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError):
            workspace.stop(profile.id)

        content = server_journal.journal_path(logs_dir, profile.id).read_text(encoding="utf-8")
        assert "отказ остановки" in content
        assert "CloseHandle отказал" in content
        assert workspace.statuses([])[0].job_pids == (4242,)  # Job остался — остатки видны


class TestRemoveProfileStopsJob:
    def test_remove_running_profile_closes_its_job(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: решение 3 — удаление работающего профиля = остановка.
        Мутация: убрать `stop()` из `remove_profile` — Job останется открытым.
        """  # noqa: RUF002
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "la" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])

        workspace.remove_profile(profile.id)

        assert factory.created[0].closed is True
        assert workspace.profiles() == []
        assert workspace.running_count() == 0

    def test_remove_profile_keeps_it_when_job_close_fails(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "lb" * 16,
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        factory.created[0].close_error = JobError("CloseHandle отказал")

        with pytest.raises(ServerError):
            workspace.remove_profile(profile.id)

        assert [p.id for p in workspace.profiles()] == [profile.id]


class TestPortHoldersInWorkspace:
    def test_empty_before_scan(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "ma" * 16)
        workspace.add_profile(_profile())
        assert workspace.port_holders(workspace.profiles()[0].id) == []

    def test_foreign_rmngr_on_regport_is_a_holder(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "mb" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        holder = _manager(300, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=(holder,)))
        assert [h.pid for h in workspace.port_holders(profile.id)] == [300]
        assert [h.pid for h in workspace.statuses([])[0].port_holders] == [300]

    def test_holders_suppressed_while_a_matched_ragent_is_alive(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "mc" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(
            700, ("ragent.exe", "-port", "1540", "-regport", "1541", "-d", profile.cluster_dir)
        )
        manager = _manager(701, ("rmngr.exe", "-port", "1541"))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=(manager,)))
        assert workspace.port_holders(profile.id) == []

    def test_unknown_profile_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnknownItemError):
            _workspace(tmp_path / "servers.json").port_holders("ghost" * 6)
```

`TestRunningCount`/`TestLogShutdown` переписать на Job:

```python
class TestRunningCount:
    def test_zero_without_jobs(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "na" * 16)
        workspace.add_profile(_profile())
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
        assert workspace.running_count() == 0

    def test_counts_profiles_with_a_non_empty_job(self, tmp_path: Path) -> None:
        factory = FakeJobFactory()
        ids = iter(["nb" * 16, "nc" * 16])
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: next(ids),
                               job_factory=factory, server_spawn=spawn)
        workspace.add_profile(_profile())
        workspace.add_profile(
            _profile(name="сосед", port=2540, regport=2541, cluster_dir=r"E:\srv\other")
        )
        first, _second = workspace.profiles()
        workspace.start(first.id, [_installation_in(tmp_path)])
        assert workspace.running_count() == 1
        factory.created[0].pids_value = ()
        assert workspace.running_count() == 0

    def test_ignores_a_foreign_matched_ragent(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: долг T-10 — вопрос выхода считал ЧУЖИЕ процессы,
        совпавшие по каталогу; мы их не остановим, считать нельзя.
        Мутация: считать по `_match.by_profile` — тест обязан упасть.
        """  # noqa: RUF002
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: "nd" * 16)
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        agent = _agent(700, ("ragent.exe", "-port", "1540", "-d", profile.cluster_dir))
        workspace.apply_scan(ScanSnapshot(agents=(agent,), managers=()))
        assert workspace.running_count() == 0
```

`TestLogShutdown.test_writes_only_to_running_profiles_and_returns_their_count`: «работающий» — через `start()` с `FakeServerSpawn` (профиль `running`), не через `apply_scan`; добавить `test_ignores_a_foreign_matched_ragent` по образцу выше (`log_shutdown() == 0`, журнала нет). Существующие `TestStart` — `_installation_in`, тройка в `spawn.calls`.

- [ ] **Step 3: RED** — `uv run pytest tests/unit/test_servers.py -q` → `TypeError: __init__() got an unexpected keyword argument 'job_factory'` и ошибки импорта.

- [ ] **Step 4: Реализация `services/servers.py`**

Импорты: убрать `process_control`; добавить `from onecstarter.platform_1c.job import Job, JobError`, `port_holders, port_holders_text` из `domain.server_match`; из `errors` убрать `ServerStopError`. Докстринг модуля — абзац про T-12 (Job на запуск профиля, истина у ОС, `stop` = `close`, чужим не управляем, спека T-12 §3).

```python
def _snapshot_processes(snapshot: ScanSnapshot) -> tuple[RagentProcess, ...]:
    """Все процессы снимка (ragent и rmngr) как `RagentProcess` — вход `port_holders`."""
    return tuple(
        RagentProcess(
            pid=info.pid, executable=info.executable, argv=info.argv, create_time=info.create_time
        )
        for info in (*snapshot.agents, *snapshot.managers)
    )


@dataclass(frozen=True)
class ServerStatus:
    profile: ServerProfile
    resolved: VersionNumber | None
    processes: tuple[RagentProcess, ...]
    job_pids: tuple[int, ...]
    spawned_pid: int | None
    port_holders: tuple[RagentProcess, ...]
    dir_mismatch: bool
```

Конструктор: `self._job_factory = job_factory`, `self._jobs: dict[str, Job] = {}`, `self._spawned: dict[str, int] = {}`.

```python
    def _job_pids(self, profile_id: str) -> tuple[int, ...]:
        job = self._jobs.get(profile_id)
        if job is None:
            return ()
        try:
            return job.pids()
        except JobError as error:
            raise ServerError(f"Не удалось прочитать процессы сервера: {error}") from error

    def _all_job_pids(self) -> set[int]:
        pids: set[int] = set()
        for profile_id in self._jobs:
            pids.update(self._job_pids(profile_id))
        return pids

    def _forget_job(self, profile_id: str) -> None:
        """Убрать Job профиля из учёта, закрыв хендл; отказ close — только в лог."""
        job = self._jobs.pop(profile_id, None)
        self._spawned.pop(profile_id, None)
        if job is not None:
            try:
                job.close()
            except JobError:
                _log.warning("не удалось закрыть Job профиля %s", profile_id)

    def _port_holders_for(
        self, profile: ServerProfile, processes: tuple[RagentProcess, ...]
    ) -> tuple[RagentProcess, ...]:
        if self._snapshot is None or processes:
            return ()
        return port_holders(profile, _snapshot_processes(self._snapshot), self._all_job_pids())

    def port_holders(self, profile_id: str) -> list[RagentProcess]:
        profile = self._profile_or_raise(profile_id)
        return list(self._port_holders_for(profile, self._matched_processes(profile)))

    def running_count(self) -> int:
        return sum(1 for profile_id in self._jobs if self._job_pids(profile_id))

    def log_shutdown(self) -> int:
        count = 0
        for profile in self._profiles:
            if self._job_pids(profile.id):
                self.log_event(
                    profile.id, "выход лаунчера — сервер будет остановлен вместе с ним"
                )
                count += 1
        return count
```

`statuses()` — собирает новые поля: `job_pids=self._job_pids(profile.id)`, `spawned_pid=self._spawned.get(profile.id)`, `port_holders=self._port_holders_for(profile, processes)`.

`start()` после проверок версии/установки:

```python
        job_pids = self._job_pids(profile_id)
        spawned = self._spawned.get(profile_id)
        if spawned is not None and spawned in job_pids:
            raise ServerError(
                f"Сервер «{profile.name}» уже работает, PID {spawned} — второй ragent "
                "на этом каталоге кластера не запускается"
            )
        processes = self._matched_processes(profile)
        if processes:
            pids = ", ".join(str(p.pid) for p in processes)
            raise ServerError(
                f"Сервер «{profile.name}» уже работает, PID {pids} — второй ragent "
                "на этом каталоге кластера не запускается"
            )
        holders = self._port_holders_for(profile, processes)
        if holders:
            message = port_holders_text(profile, holders)
            self.log_event(profile_id, f"отказ запуска: {message}")
            raise ServerError(f"Не удалось запустить сервер «{profile.name}»: {message}")
        old_job = self._jobs.pop(profile_id, None)
        self._spawned.pop(profile_id, None)
        pids_text = ", ".join(str(pid) for pid in job_pids)
        if old_job is not None:
            try:
                old_job.close()
            except JobError as error:
                self._jobs[profile_id] = old_job  # остатки остаются видимыми
                self.log_event(
                    profile_id,
                    f"отказ запуска: не удалось погасить остатки прошлого запуска ({error})",
                )
                raise ServerError(
                    f"Не удалось запустить сервер «{profile.name}»: остатки прошлого "
                    f"запуска (PID {pids_text}) не погашены — {error}"
                ) from error
        # ВНИМАНИЕ (правка вслед за находкой задачи 3, 30.08.2026): событие
        # успешного гашения пишется НИЖЕ, ПОСЛЕ ротации журнала, а не здесь.
        # `rotate_journal` переименовывает текущий файл в `.1.log`, и событие,
        # записанное до неё, уехало бы в журнал ПРОШЛОГО запуска — тогда как
        # §10 п.3 живого чек-листа требует видеть `погашены остатки…` и следом
        # штатный старт в ОДНОМ (текущем) журнале, и этого же требует
        # `test_start_with_remnants_closes_old_job_before_spawn_and_logs`
        # (`content.index("погашены остатки") < content.index("запуск:")` по
        # ТЕКУЩЕМУ журналу). Сам `close()` и его отказ остаются ДО ротации:
        # несостоявшийся запуск не имеет права трогать прошлый журнал — то же
        # правило, что у чужих держателей портов выше.
        job = self._job_factory()
        command = LaunchCommand(
            executable=installation.ragent, arguments=build_ragent_arguments(profile)
        )
        journal = server_journal.journal_path(self._logs_dir, profile_id)
        try:
            server_journal.rotate_journal(self._logs_dir, profile_id)
        except OSError as error:
            # best-effort — как раньше (Important 1 финального ревью T-10), текст str(error)
            self.log_event(
                profile_id,
                f"ротация журнала не удалась ({error}), записи продолжаются в тот же файл",
            )
        if old_job is not None and job_pids:
            self.log_event(profile_id, f"погашены остатки прошлого запуска: PID {pids_text}")
        try:
            server_journal.append_event(journal, f"запуск: {command.command_line}", self._now())
            pid = self._server_spawn(command, journal, job)
        except (OSError, JobError) as error:
            try:
                job.close()
            except JobError:
                _log.warning("не удалось закрыть Job после отказа запуска профиля %s", profile_id)
            self.log_event(profile_id, f"отказ запуска: {error}")
            raise ServerError(...) from error
        self._jobs[profile_id] = job
        self._spawned[profile_id] = pid
        self.log_event(profile_id, f"порождён PID {pid}")
        return pid
```

`stop()`:

```python
        profile = self._profile_or_raise(profile_id)
        job = self._jobs.get(profile_id)
        pids = self._job_pids(profile_id)
        if job is None or not pids:
            self._forget_job(profile_id)  # пустой Job — освободить хендл
            raise ServerError(
                f"Нечего останавливать — сервер «{profile.name}» не запущен лаунчером "
                "(процессы, запущенные не лаунчером, не останавливаются)"
            )
        try:
            job.close()
        except JobError as error:
            stop_error = ServerError(f"Не удалось остановить сервер «{profile.name}»: {error}")
            self.log_event(profile_id, f"отказ остановки: {stop_error}")
            raise stop_error from error
        del self._jobs[profile_id]
        self._spawned.pop(profile_id, None)
        self.log_event(profile_id, "остановка по команде пользователя")
```

`remove_profile()`: после проверки id — `if self._job_pids(profile_id): self.stop(profile_id)` иначе `self._forget_job(profile_id)`; затем `_save` как раньше. Докстринги `start`/`stop`/`remove_profile`/`running_count`/`log_shutdown` — переписать под Job (ссылки на `ProcessControl`, гонку PID §6.2 и «дети снимаются до родителя» убрать). Удалить `orphan_managers`, `stop_orphans`, `_terminate_or_raise`, `_orphans_for`. Из `errors.py` удалить `ServerStopError` (докстринг `log_event` упоминает его — поправить).

- [ ] **Step 5: GREEN unit** — `uv run pytest tests/unit/test_servers.py -q`. Коммит `feat: T-12 — ServersWorkspace: Job на запуск профиля, port_holders, stop=close (задача 3, services)`.

- [ ] **Step 6: Удалить `process_control`** — `git rm src/onecstarter/platform_1c/process_control.py tests/unit/test_process_control.py`; строку из `CORE`; `grep -rn process_control src tests` — пусто, кроме докстрингов `job.py`/`app.py`, которые правятся в Step 7 (в `job.py` фразу «`process_control.py`» заменить на «[Ф] Б2 T-07»). Коммит `chore: T-12 — process_control удалён (задача 3)`.

- [ ] **Step 7: `ui/app.py`** — импорты: `from onecstarter.platform_1c.job import Job, NullJob, ServerJob`; убрать импорт `process_control`. Сигнатура `_build_main_window(..., registered_radmin=None, quit_dialog=None, job_factory: Callable[[], Job] | None = None)` — `process_control` и `server_job` удалены. Проводка:

```python
    servers_workspace = ServersWorkspace(
        runtime.servers,
        job_factory=job_factory if job_factory is not None else ServerJob,
        server_spawn=spawn_server,
        logs_dir=logs_dir,
        registered_radmin=(...),
    )
```

`run_smoke`: `job_factory=NullJob` вместо `process_control=NullControl(), server_job=NullJob()`. Докстринги `_build_main_window`/`run_smoke`/комментарии про `NullControl`/`server_job` переписать: Job — на запуск профиля (T-12), фабрика; `run_smoke` подставляет `NullJob`, чтобы самопроверка не создавала kernel-объектов. `_ConsoleWorkspace` докстринг: ссылка на `process_control.py` → `process_scan.py`.

- [ ] **Step 8: `ui/servers/view.py` — минимум**

Только эти правки (остальное — задача 5):

1. Импорт `port_holders_text` из `onecstarter.domain.server_match`.
2. Блок `if status.orphans:` заменить двумя:

```python
        extinguish_button: QPushButton | None = None
        if status.job_pids and status.spawned_pid not in status.job_pids:
            text = "Остатки прошлого запуска держат порты — погасите их или запустите сервер заново"
            warnings.append(text)
            remnants_row = QHBoxLayout()
            remnants_label = QLabel(text)
            remnants_label.setWordWrap(True)
            remnants_label.setStyleSheet(f"color: {palette.problem};")
            extinguish_button = QPushButton("Погасить")
            extinguish_button.clicked.connect(
                lambda _checked=False, pid=profile.id: self._extinguish(pid)
            )
            remnants_row.addWidget(remnants_label, 1)
            remnants_row.addWidget(extinguish_button)
            card_layout.addLayout(remnants_row)
        if status.port_holders:
            text = port_holders_text(profile, status.port_holders)
            warnings.append(text)
            holders_label = QLabel(text)
            holders_label.setWordWrap(True)
            holders_label.setStyleSheet(f"color: {palette.problem};")
            card_layout.addWidget(holders_label)
```

3. `_extinguish`: `self._workspace.stop_orphans(profile_id)` → `self._workspace.stop(profile_id)`.
4. Докстринг модуля: абзацы про решение 8 и «сирот» — пометить «пересмотрено T-12 (задача 5 этого плана)»; подробная правка — задача 5.

- [ ] **Step 9: `tests/ui/test_servers_view.py` — миграция фикстур**

Удалить `FakeControl` и импорт `ProcessMismatchError`. Добавить `FakeJob`, `FakeJobFactory` (те же, что в Step 1, локальные копии — файл не импортирует из unit-набора), `FakeSpawn.__call__(self, command, log_path, job)` с добавлением `pid` в `FakeJob`. `_workspace(tmp_path, profiles=(), *, spawn=None, job_factory=None, registered_radmin=None)`. Хелпер:

```python
def _start(workspace: ServersWorkspace, profile: ServerProfile) -> None:
    """Профиль «работает» через наш Job (T-12), не через снимок."""
    workspace.start(profile.id, [_installation()])
```

Переписать: `test_stop_button_click_terminates_and_triggers_rescan` → `test_stop_button_click_closes_the_job_and_triggers_rescan` (factory → `_start` → `apply_scan(пустой)` → view → click → `factory.created[0].closed is True`, `rescans == [1]`); `test_stop_failure_is_shown_via_show_error` → `close_error=JobError("CloseHandle отказал")`, `"CloseHandle" in errors[0]`; `test_stop_does_not_arm_the_confirmation_check` → через `_start`; `test_orphans_warning_offers_extinguish_button` → `test_remnants_row_offers_extinguish_button_that_closes_the_job` (после `_start` — `factory.created[0].pids_value = (4300,)`, `view.rebuild()`, кнопка есть, click → `closed is True`, rescan); `test_no_orphans_means_no_extinguish_button` — без изменений по смыслу; новый `test_port_holder_line_is_red_and_has_no_button` (снимок с `rmngr -port 1541` → `profile_warnings(0)` содержит `"порт регистрации 1541 занят PID 321 (запущен не лаунчером)"`, `profile_extinguish_button(0) is None`, `theme.DARK.problem` в стиле QLabel с этим текстом — найти через `view.profile_card(0).findChildren(QLabel)`).

В ЭТОЙ задаче карточка ещё считает статус/кнопку по `status.processes`, поэтому тесты, где профиль «работает» через `apply_scan` с совпавшим агентом (`test_running_profile_shows_stop_button`, `test_removal_of_running_profile_*`, `test_start_confirmed_running_reports_nothing` и т. п.), остаются зелёными — их переводит на Job задача 5. Исключение — те, где клик «Остановить» ждал `control.calls`: они переписаны выше.

- [ ] **Step 10: `tests/ui/test_app.py`**

1. Убрать импорт `NullControl` и `process_control=NullControl()` (`test_monitor_wires_scan_into_servers_workspace_and_view`).
2. Импорты: `from onecstarter.platform_1c.job import NullJob`, `from onecstarter.services.servers import ScanSnapshot, ServersWorkspace` (сейчас импортирован только `ScanSnapshot`). `test_run_smoke_uses_null_job` переписать:

```python
def test_run_smoke_uses_null_job(tmp_path: Any, monkeypatch: Any, qtbot: Any) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: самопроверка подставляет `job_factory=NullJob` — kernel-объектов
    Job она не создаёт даже при запуске профиля (T-12: фабрика на запуск, `ServerJob`
    в конструкторе окна больше не вызывается, поэтому «бомба» на `ServerJob`
    ничего не ловит — проверяем сам аргумент конструктора `ServersWorkspace`).
    Мутация «`run_smoke` не передаёт `job_factory`» обязана уронить тест.
    """  # noqa: RUF002
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    captured = _capture_window(monkeypatch)
    workspace_kwargs: dict[str, Any] = {}

    class _CapturingServersWorkspace(ServersWorkspace):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            workspace_kwargs.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(app_module, "ServersWorkspace", _CapturingServersWorkspace)
    appdata = tmp_path / "appdata"
    target = tmp_path / "out"
    target.mkdir()

    assert run_smoke(str(target), {"APPDATA": str(appdata)}) == 0

    qtbot.addWidget(captured["window"])
    assert workspace_kwargs["job_factory"] is NullJob
```

3. Четыре теста гейта выхода (`test_close_with_running_server_and_declined_dialog_keeps_confirm_quit_false`, `test_confirm_quit_true_logs_shutdown_event_for_running_profile`, `test_closing_window_without_quit_dialog_never_shows_a_confirmation_dialog`, `test_request_quit_declined_does_not_quit_the_application`) делают профиль работающим через `apply_scan` с агентом — теперь `running_count()` по Job. Модульные хелперы:

```python
@dataclass
class _FakeJob:
    pids_value: tuple[int, ...] = ()
    closed: bool = False

    def assign(self, process_handle: int) -> None:
        pass

    def pids(self) -> tuple[int, ...]:
        return () if self.closed else self.pids_value

    def close(self) -> None:
        self.closed = True

    def is_empty(self) -> bool:
        return not self.pids()


_SERVER_INSTALLATION = ServerInstallation(
    installation=Installation(
        parse_version("8.3.25.1633"), Path(r"C:\1cv8\8.3.25.1633"), Arch.X64
    ),
    ragent=Path(r"C:\1cv8\8.3.25.1633\bin\ragent.exe"),
    radmin=Path(r"C:\1cv8\8.3.25.1633\bin\radmin.dll"),
)


def _start_fake_server(servers_view: ServersView, tmp_path: Any, pid: int = 4646) -> ServerProfile:
    """Профиль «работает» через Job (T-12). Требует `job_factory=lambda: _FakeJob((pid,))`
    и подменённого `app_module.spawn_server` ДО `_build_main_window`."""
    servers_view._workspace.add_profile(
        ServerProfile(
            id="", name="Тест", version="8.3.25.1633", port=1540, regport=1541,
            range_start=1560, range_end=1591, cluster_dir=str(tmp_path / "srv"),
        )
    )
    profile = servers_view._workspace.profiles()[0]
    assert servers_view._workspace.start(profile.id, [_SERVER_INSTALLATION]) == pid
    assert servers_view._workspace.running_count() == 1
    return profile
```

В каждом из четырёх тестов: перед `_build_main_window` — `monkeypatch.setattr(app_module, "spawn_server", lambda command, log, job: 4646)`; в вызов — `job_factory=lambda: _FakeJob((4646,))`; блок `add_profile`+`agent`+`apply_scan`+`assert running_count() == 1` → `profile = _start_fake_server(servers_view, tmp_path)`. `test_on_installations_populates_server_installed_and_rebuilds_the_view` — использовать `_SERVER_INSTALLATION` вместо локального дубля.

- [ ] **Step 11: GREEN полный** — `uv run pytest -q` (обычный режим), `uv run ruff check .`, `uv run mypy` — 0/0/0. Коммит `feat: T-12 — проводка job_factory, view/tests на Job (задача 3)`.

---

### Task 4: Сверка Job со снимком — `ragent завершился извне`, освобождение пустых Job

**Files:**
- Modify: `src/onecstarter/services/servers.py` (`apply_scan`, новый `_reconcile_jobs`)
- Test: `tests/unit/test_servers.py`

**Interfaces:**
- Consumes: `_jobs`, `_spawned`, `_forget_job`, `log_event` (задача 3).
- Produces: `apply_scan(snapshot)` после сопоставления зовёт `_reconcile_jobs()`: для каждого Job — `pids()` пуст → `_forget_job` (дерево умерло целиком, хендл освобождается, событий нет); `spawned_pid` известен и его нет в `pids()` → `spawned_pid` забывается (один раз) и пишется `ragent завершился извне; остатки дерева: PID …`. `JobError` при чтении — `_log.warning`, профиль пропускается (снимок не роняем).

- [ ] **Step 1: Падающие тесты** — добавить в `tests/unit/test_servers.py`:

```python
class TestReconcileOnScan:
    """Спека T-12 §4: обнаружение остатков — на снимке монитора, событие один раз."""

    def _running(self, tmp_path: Path, prefix: str) -> tuple[ServersWorkspace, FakeJobFactory, ServerProfile]:
        factory = FakeJobFactory()
        spawn = FakeServerSpawn(pid=4242)
        workspace = _workspace(tmp_path / "servers.json", new_id=lambda: prefix * 16,
                               job_factory=factory, server_spawn=spawn, logs_dir=tmp_path / "logs")
        workspace.add_profile(_profile())
        profile = workspace.profiles()[0]
        workspace.start(profile.id, [_installation_in(tmp_path)])
        return workspace, factory, profile

    def test_external_ragent_death_is_logged_once(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: переход «ragent был в Job → его нет, Job не пуст»
        пишется в журнал РОВНО один раз, `spawned_pid` после него — `None`.
        Мутация: не забывать `spawned_pid` после события — второй снимок
        напишет его ещё раз.
        """  # noqa: RUF002
        workspace, factory, profile = self._running(tmp_path, "ra")
        factory.created[0].pids_value = (4300, 4301)  # ragent 4242 снят извне

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))
        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        content = server_journal.journal_path(tmp_path / "logs", profile.id).read_text(encoding="utf-8")
        assert content.count("ragent завершился извне; остатки дерева: PID 4300, 4301") == 1
        status = workspace.statuses([])[0]
        assert status.spawned_pid is None
        assert status.job_pids == (4300, 4301)
        assert workspace.running_count() == 1  # остатки — всё ещё наш Job (гейт выхода)

    def test_job_whose_tree_is_gone_is_released(self, tmp_path: Path) -> None:
        workspace, factory, profile = self._running(tmp_path, "rb")
        factory.created[0].pids_value = ()

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        assert factory.created[0].closed is True
        status = workspace.statuses([])[0]
        assert status.job_pids == () and status.spawned_pid is None
        assert workspace.running_count() == 0
        content = server_journal.journal_path(tmp_path / "logs", profile.id).read_text(encoding="utf-8")
        assert "завершился извне" not in content

    def test_healthy_job_stays_silent(self, tmp_path: Path) -> None:
        workspace, _factory, profile = self._running(tmp_path, "rc")

        workspace.apply_scan(ScanSnapshot(agents=(), managers=()))

        assert workspace.statuses([])[0].spawned_pid == 4242
        content = server_journal.journal_path(tmp_path / "logs", profile.id).read_text(encoding="utf-8")
        assert "завершился извне" not in content
```

- [ ] **Step 2: RED** — `uv run pytest tests/unit/test_servers.py -k Reconcile -q` (первый и второй падают: события нет / Job не закрыт).

- [ ] **Step 3: Реализация**

```python
    def apply_scan(self, snapshot: ScanSnapshot) -> None:
        self._snapshot = snapshot
        self._match = match_profiles(self._profiles, _snapshot_agents(snapshot))
        self._reconcile_jobs()

    def _reconcile_jobs(self) -> None:
        """Сверить Job с реальностью на снимке монитора (спека T-12 §4).

        Пустой Job — дерево умерло целиком (само или снято извне до последнего
        процесса): хендл освобождается, профиль становится «остановлен».
        `ragent` пропал, а Job не пуст — остатки: событие пишется ОДИН раз
        (после него `spawned_pid` забыт, повторный снимок молчит).
        """  # noqa: RUF002
        for profile_id in list(self._jobs):
            try:
                pids = self._jobs[profile_id].pids()
            except JobError:
                _log.warning("не удалось прочитать Job профиля %s", profile_id)
                continue
            if not pids:
                self._forget_job(profile_id)
                continue
            spawned = self._spawned.get(profile_id)
            if spawned is not None and spawned not in pids:
                del self._spawned[profile_id]
                pids_text = ", ".join(str(pid) for pid in pids)
                self.log_event(profile_id, f"ragent завершился извне; остатки дерева: PID {pids_text}")
```

Докстринг `apply_scan` дополнить абзацем о сверке. Докстринг модуля: «Обнаружение остатков — на снимке».

- [ ] **Step 4: GREEN** — `uv run pytest tests/unit/test_servers.py -q`; полный suite, `ruff`, `mypy` — 0. Коммит `feat: T-12 — сверка Job со снимком: ragent завершился извне, пустые Job освобождаются (задача 4)`.

---

### Task 5: Карточка — таблица состояний, чужой `ragent` только показ, удаление = остановка, §8 по Job

**Files:**
- Modify: `src/onecstarter/ui/servers/view.py`
- Test: `tests/ui/test_servers_view.py`

**Interfaces:**
- Consumes: `ServerStatus.job_pids/spawned_pid/port_holders/processes/resolved` (задача 3), `workspace.stop/remove_profile/log_event`.
- Produces (модуль `view.py`, без Qt — чистые функции текста):
  - `class CardState(Enum)`: `RUNNING`, `REMNANTS`, `FOREIGN`, `STOPPED`.
  - `_card_state(status: ServerStatus) -> CardState`: `spawned_pid is not None and spawned_pid in job_pids` → `RUNNING`; иначе `job_pids` → `REMNANTS`; иначе `processes` → `FOREIGN`; иначе `STOPPED`.
  - `_status_text(status) -> str`: `RUNNING` → `работает · PID {spawned_pid}`; `REMNANTS` → `остановлен · остатки прошлого запуска: PID {job_pids через ", "}`; `FOREIGN` → `работает (запущен не лаунчером) · PID {pids processes через ", "}`; `STOPPED` → `версия не установлена`, если `resolved is None`, иначе `остановлен`.
  - `_status_colour(status, palette) -> str`: `RUNNING`/`FOREIGN` → `accent`; `REMNANTS` → `problem`; `STOPPED` → `problem` при `resolved is None`, иначе `text_dim`.
  - `_button_state(status) -> tuple[str, bool, str]` — (текст, активность, подсказка): `RUNNING` → `("Остановить", True, "")`; `REMNANTS`/`STOPPED` → `("Запустить", resolved is not None, "")`; `FOREIGN` → `("Остановить", False, "Сервер запущен не лаунчером — остановить его можно только там, где он был запущен")`.
  - `_removal_question(profile, state: CardState) -> str`: `RUNNING` → `Сервер «{name}» работает — остановить его и удалить профиль?`; `REMNANTS` → `У профиля «{name}» остались процессы прошлого запуска — погасить их и удалить профиль?`; `FOREIGN` → `Удалить профиль «{name}»? Сервер запущен не лаунчером и продолжит работать — он перейдёт в «Другие серверы на машине».`; `STOPPED` → `Удалить профиль «{name}» из списка серверов?`.
  - `ProfileRow` — без изменений; `_profile_menu_args: list[tuple[str, CardState]]`; `_build_card_menu(profile_id, state)`; `_remove(profile_id, state)`; `_toggle(profile_id, installations, running: bool)` — `running = state is CardState.RUNNING`.
  - `_check_pending_confirmation`: положительный исход — `status.spawned_pid is not None and status.spawned_pid in status.job_pids` → `log_event(id, f"работает · PID {status.spawned_pid}")`; иначе — прежнее сообщение «завершился сразу после запуска» (`show_error` + `log_event`). Снимок (`status.processes`) в решении не участвует.
  - **Страховка `rebuild()` (ревью задачи 3, Important 1):** с T-12 `workspace.statuses()` может поднять `ServerError` (`JobError` из `Job.pids()` → `ServerError`, спека T-12 §7), а `rebuild()` зовётся из слота скана каждые 5 с и после каждого действия — необработанное исключение в слоте Qt оставило бы раздел неперерисовываемым. `rebuild()` читает `statuses()`/`foreign_servers()` ДО `_clear(...)`; при `ServicesError` карточки прошлого `rebuild()` остаются как есть, строка пути показывает `{store_path} · статус недоступен: {error}` цветом `palette.problem`, аксессор `status_problem() -> str | None` отдаёт текст (`None`, когда всё в порядке — и строка пути возвращается к обычному виду/цвету). `on_scan_snapshot()` при том же исключении делает `rebuild()` и НЕ трогает `_pending_confirmation` (проверка §8 откладывается до следующего снимка). Операции (`_toggle`/`_remove`/`_extinguish`) по-прежнему показывают `ServicesError` через `show_error`.

- [ ] **Step 1: Падающие тесты (`tests/ui/test_servers_view.py`)**

Импорты: `from onecstarter.services.servers import ScanSnapshot, ServerStatus, ServersWorkspace`, `from onecstarter.ui.servers.view import CardState, ServersView, _card_state`, `from onecstarter.domain.server_match import RagentProcess`. Хелпер статуса для табличного теста:

```python
def _status(**overrides: object) -> ServerStatus:
    values: dict[str, object] = {
        "profile": _profile(), "resolved": parse_version("8.3.25.1633"), "processes": (),
        "job_pids": (), "spawned_pid": None, "port_holders": (), "dir_mismatch": False,
    }
    values.update(overrides)
    return ServerStatus(**values)  # type: ignore[arg-type]


def _matched(pid: int) -> RagentProcess:
    return RagentProcess(pid=pid, executable=None, argv=("ragent.exe",), create_time=1.0)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (_status(job_pids=(1, 2), spawned_pid=1), CardState.RUNNING),
        (_status(job_pids=(2,), spawned_pid=1), CardState.REMNANTS),
        (_status(job_pids=(2,), spawned_pid=None), CardState.REMNANTS),
        (_status(processes=(_matched(9),)), CardState.FOREIGN),
        (_status(), CardState.STOPPED),
        (_status(job_pids=(1,), spawned_pid=1, processes=(_matched(9),)), CardState.RUNNING),  # Job главнее снимка
    ],
)
def test_card_state_table(status: ServerStatus, expected: CardState) -> None:
    assert _card_state(status) is expected
```

Переписать/добавить (везде «работает» — через `_start(workspace, profile)` с `FakeJobFactory`, `apply_scan(ScanSnapshot(agents=(), managers=()))` до/после по смыслу теста):

- `test_running_profile_shows_stop_button`: `row.status_text == "работает · PID 4242"`, кнопка «Остановить» активна. `test_running_status_uses_accent_colour` — так же.
- `test_running_process_wins_over_unresolved_version`: `_start` (установка передаётся в `start()` напрямую), `installed=lambda: []` у view → всё равно `RUNNING`: `"работает · PID 4242"`, «Остановить» активна, accent.
- `test_multiple_processes_disable_stop_with_explanation` → `test_foreign_matched_ragents_are_show_only` (ЗАЩИТНЫЙ, решение 4): два совпавших агента 100/200, Job нет → `row.status_text == "работает (запущен не лаунчером) · PID 100, 200"`, `button_text == "Остановить"`, `button_enabled is False`, `"не лаунчером" in view.profile_button(0).toolTip()`, accent. Мутация: считать совпавший процесс нашим — кнопка станет активной.
- `test_remnants_state_shows_red_status_and_start_button`: `_start`, `factory.created[0].pids_value = (4300, 4301)`, `view.rebuild()` → `row.status_text == "остановлен · остатки прошлого запуска: PID 4300, 4301"`, `theme.DARK.problem` в стиле статуса, `button_text == "Запустить"`, `button_enabled is True`, `profile_extinguish_button(0) is not None`.
- Удаление: `test_removal_of_running_profile_asks_to_stop_and_refusal_keeps_it_running` (ЗАЩИТНЫЙ: `_start`; `refuse` собирает вопрос; `_trigger_delete`; `"остановить его и удалить" in questions[0]`; `factory.created[0].closed is False`; профиль на месте. Мутация: удалять/останавливать до вопроса — упадёт); `test_removal_of_running_profile_confirmed_stops_and_removes` (`closed is True`, `profiles() == []`); `test_removal_of_remnants_profile_asks_to_extinguish` (`"погасить их и удалить" in questions[0]`); `test_removal_of_foreign_running_profile_warns_it_keeps_running` (совпавший агент, Job нет: `"продолжит работать" in questions[0]`, отказ → профиль на месте); `test_removal_of_stopped_profile_uses_plain_question` — как есть; `test_removal_confirmed_triggers_rescan` — через `_start`.
- §8: `test_start_that_dies_silently_is_reported` — после клика `factory.created[0].pids_value = ()` (ragent умер), `apply_scan(пустой)` + `on_scan_snapshot()` → `errors` с именем и портом; `test_start_confirmed_running_reports_nothing` — после клика Job уже содержит 4242 (FakeSpawn), `apply_scan(пустой)` + `on_scan_snapshot()` → `errors == []`; `test_start_followed_by_unrelated_rebuild_does_not_falsely_report_death` — так же, со снимком без агентов; `test_confirmed_running_is_also_written_to_the_journal` → `"работает · PID 4242" in journal_text`; `test_death_after_start_is_also_written_to_the_journal` → `pids_value = ()`; новый `test_start_that_dies_leaving_remnants_reports_death_and_shows_remnants`: после клика `pids_value = (4300,)`, `apply_scan` + `on_scan_snapshot()` → `errors` не пуст, `row.status_text` начинается с `"остановлен · остатки прошлого запуска"`, в журнале есть и `ragent завершился извне`, и `завершился сразу после запуска`.
- `test_stop_does_not_arm_the_confirmation_check` — `_start`, клик «Остановить», `apply_scan` + `on_scan_snapshot()` → `errors == []`.
- Страховка `rebuild()` (ревью задачи 3): `FakeJob` получает поле `pids_error: JobError | None = None` — `pids()` поднимает его, если задано. `test_rebuild_survives_a_job_that_cannot_be_read` (ЗАЩИТНЫЙ: мутация «убрать `try/except ServicesError` в `rebuild()`» — тест упадёт необработанным `ServerError`): `_start`, `view` построен (карточка «работает · PID 4242» есть), затем `factory.created[0].pids_error = JobError("QueryInformationJobObject отказал")`, `view.rebuild()` — исключения нет, `view.profile_rows()` по-прежнему одна строка с прежним текстом, `"статус недоступен" in view.path_text()`, `theme.DARK.problem` в `view.path_label_style()` (новый аксессор — `styleSheet()` строки пути), `view.status_problem()` содержит `"QueryInformationJobObject"`; `test_rebuild_clears_the_problem_when_statuses_recover` — после `pids_error = None` и `rebuild()` `status_problem() is None`, строка пути без «статус недоступен»; `test_scan_snapshot_with_unreadable_job_keeps_pending_confirmation` — после клика «Запустить» (профиль в ожидании §8) `pids_error` задан, `apply_scan` + `on_scan_snapshot()` → `errors == []`, затем `pids_error = None`, `apply_scan` + `on_scan_snapshot()` → проверка §8 сработала (журнал содержит `работает · PID 4242`).

- [ ] **Step 2: RED** — `uv run pytest tests/ui/test_servers_view.py -q` (`ImportError: CardState`).

- [ ] **Step 3: Реализация `view.py`**

```python
from enum import Enum


class CardState(Enum):
    RUNNING = "running"    # наш ragent жив в Job
    REMNANTS = "remnants"  # Job не пуст, ragent в нём нет
    FOREIGN = "foreign"    # Job пуст, снимок нашёл совпавший ragent — только показ (решение 4)
    STOPPED = "stopped"


def _card_state(status: ServerStatus) -> CardState:
    if status.spawned_pid is not None and status.spawned_pid in status.job_pids:
        return CardState.RUNNING
    if status.job_pids:
        return CardState.REMNANTS
    if status.processes:
        return CardState.FOREIGN
    return CardState.STOPPED


def _status_text(status: ServerStatus) -> str:
    state = _card_state(status)
    if state is CardState.RUNNING:
        return f"работает · PID {status.spawned_pid}"
    if state is CardState.REMNANTS:
        pids = ", ".join(str(pid) for pid in status.job_pids)
        return f"остановлен · остатки прошлого запуска: PID {pids}"
    if state is CardState.FOREIGN:
        pids = ", ".join(str(p.pid) for p in status.processes)
        return f"работает (запущен не лаунчером) · PID {pids}"
    if status.resolved is None:
        return "версия не установлена"
    return "остановлен"


def _status_colour(status: ServerStatus, palette: Palette) -> str:
    state = _card_state(status)
    if state in (CardState.RUNNING, CardState.FOREIGN):
        return palette.accent
    if state is CardState.REMNANTS or status.resolved is None:
        return palette.problem
    return palette.text_dim


_FOREIGN_TOOLTIP = "Сервер запущен не лаунчером — остановить его можно только там, где он был запущен"


def _button_state(status: ServerStatus) -> tuple[str, bool, str]:
    state = _card_state(status)
    if state is CardState.RUNNING:
        return "Остановить", True, ""
    if state is CardState.FOREIGN:
        return "Остановить", False, _FOREIGN_TOOLTIP
    return "Запустить", status.resolved is not None, ""


def _removal_question(profile: ServerProfile, state: CardState) -> str:
    if state is CardState.RUNNING:
        return f"Сервер «{profile.name}» работает — остановить его и удалить профиль?"
    if state is CardState.REMNANTS:
        return (
            f"У профиля «{profile.name}» остались процессы прошлого запуска — "
            "погасить их и удалить профиль?"
        )
    if state is CardState.FOREIGN:
        return (
            f"Удалить профиль «{profile.name}»? Сервер запущен не лаунчером и продолжит "
            "работать — он перейдёт в «Другие серверы на машине»."
        )
    return f"Удалить профиль «{profile.name}» из списка серверов?"
```

Страховка `rebuild()` (ревью задачи 3, Important 1):

```python
    def rebuild(self) -> None:
        server_installations = self._installed()
        installed_versions = [si.installation.version for si in server_installations]
        try:
            statuses = self._workspace.statuses(installed_versions)
            foreign = self._workspace.foreign_servers()
        except ServicesError as error:
            # T-12: statuses() читает Job.pids() — отказ WinAPI (JobError → ServerError)
            # не должен оставить раздел неперерисовываемым: карточки прошлого
            # rebuild() остаются, строка пути показывает причину.
            self._status_problem = str(error)
            self._path_label.setText(
                f"{self._workspace.store_path} · статус недоступен: {error}"
            )
            self._path_label.setStyleSheet(f"color: {self._palette.problem};")
            return
        self._status_problem = None
        self._path_label.setStyleSheet("")
        self._clear(self._cards_layout)
        ...  # дальше как раньше: сброс списков, _build_card по statuses, _build_foreign_row по foreign, строка пути
```

`on_scan_snapshot()`: `self.rebuild()`; если после него `self._status_problem is not None` — `return` без `_check_pending_confirmation` (ожидание §8 сохраняется до следующего снимка); иначе — как раньше. Аксессоры: `status_problem() -> str | None`, `path_label_style() -> str` (`self._path_label.styleSheet()`).

В `_build_card`: `button_text, button_enabled, button_tooltip = _button_state(status)` (в слепом окне до первого снимка — как раньше, свои значения); `state = _card_state(status)`; `running = state is CardState.RUNNING`; `self._profile_menu_args.append((profile.id, state))`; меню/`_remove` получают `state`; `_remove` зовёт `_removal_question(profile, state)` и `remove_profile` (остановка — внутри воркспейса, задача 3). `_check_pending_confirmation` — как в Interfaces. Докстринги модуля/`_status_text`/`_removal_question`/`_remove` переписать: решение 8 отменено (T-12, решение 3), решение 5 отменено (решение 4), «сироты» → «остатки в Job» и «чужие держатели портов»; IMPORTANT 3 (процессы главнее версии) сохраняется — теперь «Job главнее версии».

- [ ] **Step 4: GREEN** — `uv run pytest tests/ui/test_servers_view.py -q`; полный suite, `ruff`, `mypy` — 0. Коммит `feat: T-12 — карточка: таблица состояний, чужой ragent только показ, удаление = остановка (задача 5)`.

---

### Task 6: Документы вслед за кодом — исходная спека, мокап, `tasks.md`

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-v2-servers-design.md`
- Modify: `docs/superpowers/specs/assets/2026-08-26-v2-servers-mockup.html`
- Modify: `docs/tasks.md`
- Modify: `docs/superpowers/specs/2026-08-29-v2-servers-job-per-profile-design.md` (только §5 — уточнение про `ServerStatus`)

- [ ] **Step 1: Исходная спека** (правки по T-12 §8, каждая — с пометкой «пересмотрено T-12, 29.08.2026» и ссылкой `[T-12](2026-08-29-v2-servers-job-per-profile-design.md)`):
  - §2, решение 5: дописать «**Пересмотрено T-12:** совпавший чужой `ragent` — только показ («работает (запущен не лаунчером)»), управляем только тем, что запустили сами». Решение 8: «**Пересмотрено T-12:** удаление работающего профиля = остановка (вопрос «остановить его и удалить профиль?»)».
  - §4.2: пункт `process_control.py` заменить на «`job.py`: `ServerJob` — Job Object на запуск профиля: `assign`/`pids`/`close`/`is_empty` ([Ф] 29.08.2026 — `QueryInformationJobObject` отдаёт всё дерево; `CloseHandle` гасит остатки). `process_control.py` удалён T-12: остановка — закрытие Job, не `TerminateProcess` по снимку».
  - §4.3: `ServerStopError` убрать из перечня ошибок.
  - §6.2 «Гонка PID»: «**Снято T-12** для наших процессов — Job вместо снимка; остаётся доводом, почему чужими процессами не управляем».
  - §6.3: «Совпавший чужой процесс — только показ (T-12)»; фразу про отказ `TerminateProcess` на совпавшем — убрать.
  - §6.4: дополнить «и при чужом держателе порта профиля (`-port`/`-regport` у процесса не из наших Job) — отказ до ротации и spawn (T-12 §4)».
  - §12.4: «**T-12:** Job — на каждый запуск профиля; «Остановить»/«Погасить» = закрытие Job; при выходе/крахе все Job kill-on-close по-прежнему».
- [ ] **Step 2: Мокап** — в обеих темах (`light`/`dark`) заменить карточку «Общий стенд … служба» на две: (а) `Общий стенд <span class="st on">● работает (запущен не лаунчером) · PID 4120</span>` с подстрокой `<div class="d">Запущен не лаунчером — остановить можно только там, где он был запущен</div>` и `<span class="btn off">Остановить</span>`; (б) новая карточка `8.3.24 стенд <span class="st bad">○ остановлен · остатки прошлого запуска: PID 7712, 7730</span>` с красной строкой `<div class="d prob">Остатки прошлого запуска держат порты — погасите их или запустите сервер заново</div>` и кнопками `<span class="btn">Запустить</span> <span class="btn">Погасить</span>`. В `<p>` над мокапом «Четыре состояния строки» → перечислить состояния T-12 (работает · PID; остановлен · остатки; работает (запущен не лаунчером); остановлен) и красную строку держателей портов. Порты/PID вымышленные.
- [ ] **Step 3: `docs/tasks.md`** — новый раздел `## T-12. Job Object на профиль — WIP` после T-11 (спека, план, ветка, что сделано по задачам 1–5, «финальный гейт и мутации — задача 7»); в «Долг вехи T-10» пометить закрытыми T-12: «`running_count()` считает чужие» (`~~…~~ закрыто T-12`), «гигиена ctypes в `job.py`», «`Job(Protocol)` не используется как аннотация / закрытая уния `ServerJob | NullJob`»; в T-10 § «Находки» строки 5–6 — «закрыто T-12». Долг вехи T-12 (сознательно): чужой `dbgs` на 1550 не опознаётся ([Р], спека §4); гонка «`close()` остатков → порты освобождаются → новый `ragent`» не измерена ([Р], проверяется живым чек-листом §10 п. 3).
- [ ] **Step 4: Спека T-12 §5** — фразу «`domain/server_match.py`. `ServerStatus` получает…» уточнить: `ServerStatus` живёт в `services/servers.py` (там же с T-08), в `domain` — только `port_holders`/`port_holders_text`.
- [ ] **Step 5:** `uv run ruff check .` (не трогает md, но привычный гейт), коммит `docs: T-12 — спека v2, мокап и tasks.md вслед за кодом (задача 6)`.

---

### Task 7: Финальный гейт — полный прогон, сборка со smoke, мутации независимым агентом

Исполнитель этой задачи — **не автор тестов вехи** (независимый агент; правило CLAUDE.md «Мутационная проверка тестов»). Отчёт — `.superpowers/sdd/2026-08-30-v2-servers-job-per-profile/task-7-report.md`.

**Files:**
- Modify: `docs/tasks.md` (раздел T-12: итог гейта, таблица мутаций)

- [ ] **Step 1: Гейты на итоговом дереве** — `uv run pytest -q` (обычный режим; число тестов и время — в отчёт), `uv run ruff check .`, `uv run mypy` — 0/0/0. После прогона: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'time.sleep\(' }` — пусто (подставные процессы прибраны).
- [ ] **Step 2: Сборка** — `build/build.ps1` БЕЗ редиректа `2>&1` (PowerShell 5.1 оборачивает stderr native-команд в `NativeCommandError`); собранный exe закрыт заранее. Smoke собранного экземпляра — `OK`, размер dist — в отчёт.
- [ ] **Step 3: Мутации** — по протоколу: правка → ТОЛЬКО названный тест → дословный результат (`FAILED …::… - AssertionError: …`) → `git checkout -- <файл>` → `git status --short` пуст. Все 14:

| # | Мутация | Файл | Тест |
| --- | --- | --- | --- |
| 1 | `close()` обнуляет `_handle`, не зовя `CloseHandle` | `platform_1c/job.py` | `test_close_kills_remnants_after_external_kill` |
| 2 | `pids()` всегда возвращает `()` | `platform_1c/job.py` | `test_pids_lists_parent_and_grandchild` |
| 3 | `start()` закрывает старый Job ПОСЛЕ `server_spawn` | `services/servers.py` | `test_start_with_remnants_closes_old_job_before_spawn_and_logs` |
| 4 | `start()` не проверяет `port_holders` | `services/servers.py` | `test_start_refuses_when_a_foreign_process_holds_the_profile_port` |
| 5 | `start()` не проверяет живой `ragent` в Job (`spawned in job_pids`) | `services/servers.py` | `test_start_refuses_while_own_ragent_is_alive_in_job` |
| 6 | `stop()` закрывает ВСЕ Job | `services/servers.py` | `test_stop_closes_only_this_profiles_job` |
| 7 | `running_count()` считает по `_match.by_profile` | `services/servers.py` | `TestRunningCount::test_ignores_a_foreign_matched_ragent` |
| 8 | `_reconcile_jobs` не забывает `spawned_pid` после события | `services/servers.py` | `test_external_ragent_death_is_logged_once` |
| 9 | `remove_profile` не останавливает Job | `services/servers.py` | `test_remove_running_profile_closes_its_job` |
| 10 | `_remove` во view удаляет без вопроса | `ui/servers/view.py` | `test_removal_of_running_profile_asks_to_stop_and_refusal_keeps_it_running` |
| 11 | `run_smoke` не передаёт `job_factory` | `ui/app.py` | `test_run_smoke_uses_null_job` |
| 12 | `_button_state` считает `FOREIGN` активной «Остановить» | `ui/servers/view.py` | `test_foreign_matched_ragents_are_show_only` |
| 13 | `port_holders` игнорирует `exclude_pids` | `domain/server_match.py` | `test_own_job_pids_are_excluded` |
| 14 | `rebuild()` без `try/except ServicesError` вокруг `statuses()` | `ui/servers/view.py` | `test_rebuild_survives_a_job_that_cannot_be_read` |

Мутации 1–2 поднимают подставные python-процессы — после каждой проверить, что живых не осталось (команда из Step 1).
- [ ] **Step 4: `docs/tasks.md`** — в разделе T-12: число тестов, коды гейтов, итог сборки/smoke, таблица «# | Мутация | Файл | Тест | Результат» с дословными результатами; статус раздела — «код готов, ждёт финального ревью ветки и живого чек-листа (спека T-12 §10)».
- [ ] **Step 5: Коммит** — `docs: T-12 — финальный гейт и мутации 1–13 (задача 7)`.

После задачи 7 — финальное ревью ветки (SDD), затем живой чек-лист спеки T-12 §10 с заказчиком (запуски `ragent` — только заказчик) и `finishing-a-development-branch`.
