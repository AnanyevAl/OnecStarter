# T-10 «Журнал профиля и дочерние серверы» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Тихий запуск серверов без консольных окон, дочерний жизненный цикл (выход лаунчера завершает серверы через Job Object, с подтверждением), файл журнала на профиль и tail-панель «Журнал профиля» в разделе.

**Architecture:** Новый серверный spawn в `platform_1c` (скрытая консоль + редирект в файл + Job Object kill-on-close — все механики измерены T-09); журнал — чистые функции `services/server_journal.py` (ротация, события с временем); координатор пишет события и использует новый spawn через инъекцию (Job в services не протекает); UI — выделение карточки и tail-панель, подтверждение выхода в `MainWindow`/трее.

**Tech Stack:** Python ≥ 3.13, PySide6 (только ui), ctypes (Job — по эталону `e:\tmp\t09\b2_job.py`), pytest.

Спека: [2026-08-26-v2-servers-design.md](../specs/2026-08-26-v2-servers-design.md) **§12** (решения 28.08.2026).
Факты: [t09-protocol.md](../../research/t09-protocol.md) — все «[Ф] А…/Б…» ниже оттуда; [Ф] Б2 T-07 — из t07-protocol.md.
Ветка: продолжаем `feat/2026-08-26-v2-servers` (T-10 строится поверх T-08, сливаются вместе).

## Global Constraints

- Qt только в `src/onecstarter/ui/`; новый модуль ядра — строка в `CORE` (`tests/unit/test_no_qt_in_core.py`) в той же задаче.
- Клиентский `platform_1c/process.py::spawn` НЕ трогается — отвязанный запуск клиентов остаётся как есть. Меняется только серверный путь.
- Job Object в `services` не протекает: координатор получает `server_spawn: Callable[[LaunchCommand, Path], int]` инъекцией, Job запечён проводкой `app.py`.
- Журнал: `%APPDATA%\OneCStarter\logs\servers\<id>.log`, прошлый запуск → `<id>.1.log` (спека §12.6); наши строки — UTF-8, `[HH:MM:SS] текст`; tail декодирует `utf-8, errors="replace"` (хвост T-09.3 — кодировка кириллицы платформы не снята).
- «Закрытие в трей» — не выход: серверы живут. Выход (крестик при выключенном трее, «Выход» в трее) при работающих серверах — подтверждение «Остановить N серверов и выйти?», дефолт «Отмена» (§12.3). Гашение при выходе — самим Job (kill-on-close при смерти процесса, [Ф] Б2 T-09), явного кода остановки не нужно.
- Проверки: `uv run pytest`, `uv run ruff check .`, `uv run mypy` — коды 0 после каждой задачи; mypy strict вне `onecstarter.ui.*`.
- Тесты не запускают живой `ragent` (правило «Границы»); Job/spawn тестируются подставными python-процессами.
- Защитные тесты — докстринг «ЗАЩИТНЫЙ ТЕСТ»; их мутации ставит независимый агент (задача 9).
- Подписи UI по-русски; цвета — только роли `Palette`.

---

### Task 1: Job Object — гарантия смерти дерева с лаунчером

**Files:**
- Create: `src/onecstarter/platform_1c/job.py`
- Test: `tests/unit/test_job.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.platform_1c.job",`)

**Interfaces:**
- Produces: `class ServerJob` — `__init__(self)` лениво НЕ создаёт объект; `assign(self, process_handle: int) -> None` — при первом вызове создаёт Job c `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` и кладёт процесс; handle Job живёт до конца процесса лаунчера намеренно (kill-on-close = гарантия «выход/крах гасит все серверы», [Ф] Б1/Б2 T-09); `JobError(Exception)` при отказе WinAPI. `class NullJob` — `assign` no-op (для smoke). Структуры ctypes — дословно из эталона `e:\tmp\t09\b2_job.py` (проверен живым ragent-деревом, [Ф] Б2): `IO_COUNTERS`, `JOBOBJECT_BASIC_LIMIT_INFORMATION`, `JOBOBJECT_EXTENDED_LIMIT_INFORMATION`, `JobObjectExtendedLimitInformation = 9`, `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000`.

- [ ] **Step 1: Написать падающие тесты**

```python
"""Job Object: дерево серверов умирает вместе с лаунчером ([Ф] Б1/Б2 T-09)."""
import subprocess
import sys
import time

import psutil
import pytest

from onecstarter.platform_1c.job import JobError, NullJob, ServerJob


def _sleeper_with_grandchild() -> tuple[subprocess.Popen[str], int]:
    parent = subprocess.Popen(
        [sys.executable, "-c",
         "import subprocess,sys,time;"
         "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
         "print(p.pid,flush=True);time.sleep(120)"],
        stdout=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert parent.stdout is not None
    return parent, int(parent.stdout.readline())


class TestServerJob:
    def test_close_kills_parent_and_grandchild(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: kill-on-close гасит всё дерево ([Ф] Б1 T-09).

        Мутация «assign не кладёт процесс в Job» оставит дерево живым.
        """
        parent, grandchild = _sleeper_with_grandchild()
        job = ServerJob()
        try:
            job.assign(int(parent._handle))  # noqa: SLF001 — handle Popen, как в проводке
            job._close_for_tests()
            time.sleep(1)
            assert not psutil.pid_exists(parent.pid)
            assert not psutil.pid_exists(grandchild)
        finally:
            for pid in (parent.pid, grandchild):
                if psutil.pid_exists(pid):
                    psutil.Process(pid).kill()

    def test_assign_bad_handle_raises_job_error(self) -> None:
        job = ServerJob()
        with pytest.raises(JobError):
            job.assign(0)

    def test_null_job_is_a_no_op(self) -> None:
        NullJob().assign(0)  # не падает и ничего не делает
```

- [ ] **Step 2: RED** — `uv run pytest tests/unit/test_job.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Реализация** — структуры и последовательность вызовов дословно из `e:\tmp\t09\b2_job.py` (CreateJobObjectW → SetInformationJobObject(kill-on-close) → AssignProcessToJobObject); отказы WinAPI → `JobError(f"... GetLastError={ctypes.get_last_error()}")`. `_close_for_tests()` — закрыть handle (в проде не зовётся: handle живёт до смерти процесса — это и есть гарантия). Докстринг модуля: почему handle не закрывается ([Ф] Б2 — закрытие гасит дерево; смерть лаунчера закрывает handle сама).

- [ ] **Step 4: GREEN + CORE.** — `uv run pytest tests/unit/test_job.py tests/unit/test_no_qt_in_core.py -q`.

- [ ] **Step 5:** `ruff`/`mypy`/коммит `feat: Job Object — дерево серверов умирает с лаунчером (T-10, задача 1)`.

---

### Task 2: Серверный spawn — тихо, в файл, в Job

**Files:**
- Create: `src/onecstarter/platform_1c/server_spawn.py`
- Test: `tests/unit/test_server_spawn.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.platform_1c.server_spawn",`)

**Interfaces:**
- Consumes: `LaunchCommand` (`domain/launch.py`), `ServerJob`/`NullJob` (задача 1).
- Produces: `spawn_server(command: LaunchCommand, log_path: Path, job: ServerJob | NullJob) -> int` — открывает `log_path` на дозапись (`"ab"`), `subprocess.Popen(command.command_line, creationflags=subprocess.CREATE_NO_WINDOW, stdout=f, stderr=subprocess.STDOUT, close_fds=True)`, `job.assign(int(process._handle))`, вернуть pid; `Popen` брошен с подавлением `ResourceWarning` (образец — `process.py::spawn`, тот же приём). `CREATE_NO_WINDOW` вместо `DETACHED_PROCESS` — [Ф] А3 T-09: скрытая консоль не плодит окна у детей (DETACHED плодил — дефект чек-листа); файл ловит stdout-канал ([Ф] А1: практически только dbgs — этого и ждём). `OSError` (файл не открылся, Popen упал) — наружу, переводит вызывающий (сохранение контракта T-08: services переводит в ServerError).

- [ ] **Step 1: Тесты** — подставной процесс: `LaunchCommand(executable=Path(sys.executable), arguments='-c "print(\'hello from child\', flush=True); import time; time.sleep(30)"')` (`command_line` соберёт `"<python>" -c "…"` — форма кавычек штатная для Popen-строки); `spawn_server(cmd, tmp_path/"j.log", NullJob())` → pid жив; опрос файла до 5 с — содержит `hello from child`; убить pid в `finally`. Второй тест: `job=ServerJob()` + `_close_for_tests()` → процесс мёртв (связка spawn↔job). Третий: `log_path` в несуществующем каталоге → `OSError` наружу, процесс не порождён.

- [ ] **Step 2: RED.** **Step 3: Реализация** (докстринг: почему не DETACHED — [Ф] А3, дефект чек-листа 28.08.2026). **Step 4: GREEN + CORE.**

- [ ] **Step 5:** коммит `feat: серверный spawn — скрытая консоль, редирект в журнал, Job (T-10, задача 2)`.

---

### Task 3: Журнал профиля — ротация и события

**Files:**
- Create: `src/onecstarter/services/server_journal.py`
- Test: `tests/unit/test_server_journal.py`
- Modify: `tests/unit/test_no_qt_in_core.py` (строка `"onecstarter.services.server_journal",`)

**Interfaces:**
- Produces: `journal_path(logs_dir: Path, profile_id: str) -> Path` → `logs_dir / f"{profile_id}.log"`; `previous_journal_path(logs_dir, profile_id) -> Path` → `logs_dir / f"{profile_id}.1.log"`; `rotate_journal(logs_dir: Path, profile_id: str) -> None` — текущий → прошлый (`os.replace`, прежний прошлый затирается; отсутствующий текущий — no-op; `logs_dir` создаётся `mkdir(parents=True, exist_ok=True)`); `append_event(path: Path, text: str, when: datetime) -> None` — дозапись строки `f"[{when:%H:%M:%S}] {text}\n"` в UTF-8 (каталог создаётся при необходимости; `OSError` наружу — журнал не важнее работы, гасит вызывающий).

- [ ] **Step 1: Тесты** (ротация — ЗАЩИТНЫЙ):

```python
class TestRotate:
    def test_current_becomes_previous(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: ротация сохраняет прошлый запуск (спека §12.6).

        Мутация «rotate удаляет файл вместо переноса» теряет историю.
        """
        journal_path(tmp_path, "p1").parent.mkdir(parents=True, exist_ok=True)
        journal_path(tmp_path, "p1").write_text("старый запуск", encoding="utf-8")
        rotate_journal(tmp_path, "p1")
        assert not journal_path(tmp_path, "p1").exists()
        assert previous_journal_path(tmp_path, "p1").read_text(encoding="utf-8") == "старый запуск"

    def test_missing_current_is_a_no_op(self, tmp_path: Path) -> None: ...
        # rotate_journal не падает и не создаёт пустых файлов

class TestAppendEvent:
    def test_line_format_and_encoding(self, tmp_path: Path) -> None:
        append_event(tmp_path / "j.log", "запуск: тест", datetime(2026, 8, 28, 9, 5, 7))
        assert (tmp_path / "j.log").read_text(encoding="utf-8") == "[09:05:07] запуск: тест\n"

    def test_appends_not_overwrites(self, tmp_path: Path) -> None: ...
```

(Многоточия — дописать телом по описанию рядом; в тестовом файле многоточий не оставлять.)

- [ ] **Step 2: RED.** **Step 3: Реализация** (докстринг: два писателя одного файла — наши события и stdout дерева; наш канал UTF-8, платформа пишет своё — tail читает с `errors="replace"`, [Ф] А1/А4 T-09). **Step 4: GREEN + CORE.**

- [ ] **Step 5:** коммит `feat: журнал профиля — ротация и события (T-10, задача 3)`.

---

### Task 4: Координатор — дочерний запуск с журналом

**Files:**
- Modify: `src/onecstarter/services/servers.py`
- Test: `tests/unit/test_servers.py`

**Interfaces:**
- Consumes: задачи 2–3.
- Produces (правки `ServersWorkspace`):
  - Конструктор: параметр `spawn: Callable[[LaunchCommand], int]` ЗАМЕНЯЕТСЯ на `server_spawn: Callable[[LaunchCommand, Path], int]` (дефолт: `functools.partial`-обёртки НЕ давать — параметр обязательный keyword-only, Job запекает проводка app.py; тестам — фейк) + новый обязательный `logs_dir: Path`.
  - `journal_path(self, profile_id: str) -> Path` — через `server_journal.journal_path` (неизвестный id → `UnknownItemError`).
  - `log_event(self, profile_id: str, text: str) -> None` — `append_event(journal_path, text, self._now())`; `OSError` глотается с логом процесса (журнал не важнее работы) — единственное место глотания, с комментарием.
  - `running_count(self) -> int` — число профилей с непустыми `processes` в последнем сопоставлении (0 до снимка).
  - `start(...)`: после всех проверок и ДО spawn — `rotate_journal` + событие `запуск: {command.command_line}`; затем `self._server_spawn(command, journal_path)`; `OSError` → событие `отказ запуска: {error}` + `ServerError` (как в T-08).
  - `stop(...)`/`stop_orphans(...)`: событие `остановка по команде пользователя` / `гашение сирот: PID …` после успешного завершения; `ServerStopError`-путь — событие `отказ остановки: …` перед raise.
  - Докстринги жизненного цикла переписать: серверы дочерние (§12, реверс решения 3), «переживает закрытие» убрать везде по файлу.
- `self._now` уже есть в конструкторе (T-08) — время событий из него.

- [ ] **Step 1: Тесты** — фейк `FakeServerSpawn` (журнал вызовов `(command_line, log_path)`, возвращает pid, режим OSError). ЗАЩИТНЫЕ: `test_start_rotates_journal_and_logs_command` («ЗАЩИТНЫЙ ТЕСТ: прошлый журнал не теряется, команда записана» — прошлый файл существует после старта как `.1.log`, в новом есть `[..] запуск: "<exe>" -debug …`); `test_failed_spawn_logs_the_refusal` (OSError-режим → в журнале `отказ запуска`, поднят ServerError). Обычные: `stop` пишет событие; `log_event` глотает OSError (каталог на месте файла — не падает); `running_count` по снимку; `journal_path` неизвестного id → UnknownItemError; сигнатурная миграция — существующие тесты `FakeSpawn` файла обновить на `FakeServerSpawn` (механическая замена, поведенческие утверждения сохранить).

- [ ] **Step 2: RED.** **Step 3: Реализация.** **Step 4: GREEN** (весь `tests/unit/test_servers.py`).

- [ ] **Step 5:** коммит `feat: координатор — дочерний запуск с журналом профиля (T-10, задача 4)`.

---

### Task 5: UI — выделение карточки и панель «Журнал профиля»

**Files:**
- Modify: `src/onecstarter/ui/servers/view.py`
- Create: `src/onecstarter/ui/servers/journal_panel.py`
- Test: `tests/ui/test_servers_view.py`, `tests/ui/test_journal_panel.py`

**Interfaces:**
- Produces: `JournalPanel(QWidget)` — `__init__(self, *, palette: Palette, parent=None)`; `show_journal(self, title: str, path: Path | None) -> None` (None — «выберите профиль», плейсхолдер dim); `refresh(self) -> None` — перечитать хвост файла (последние ≤ 500 строк, декод `utf-8, errors="replace"`, автопрокрутка вниз, если пользователь не прокрутил вверх); внутренний `QTimer` 1000 мс зовёт `refresh` только пока панель видима и путь задан; `text()` — аксессор тестам; `apply_palette(palette)`. Моноширинный шрифт, фон/цвета — роли палитры.
- `ServersView`: клик по карточке выделяет её (визуально — рамка `palette.accent`, как выделение в мокапе; аксессор `selected_profile_id() -> str | None`); панель встраивается низом раздела (компоновка как detail-панель «Баз»); выбор профиля → `panel.show_journal(имя, workspace.journal_path(id))`; удаление выбранного профиля сбрасывает выбор; §8-исход «сервер завершился сразу после запуска» дополнительно пишется в журнал через `workspace.log_event(profile_id, ...)` (тот же текст, что в `show_error`).

- [ ] **Step 1: Тесты** — `JournalPanel`: показ файла (написать строки — `text()` их содержит), плейсхолдер при None, дозапись + `refresh()` → хвост дописался, битые байты не роняют (файл с `b"\xff\xfe"` внутри — `errors="replace"`); `ServersView`: клик (mouseRelease по карточке через qtbot) выделяет и показывает журнал профиля; удаление выбранного сбрасывает панель в плейсхолдер; §8-исход пишет строку в журнал (прочитать файл).

- [ ] **Step 2: RED.** **Step 3: Реализация.** **Step 4: GREEN.**

- [ ] **Step 5:** коммит `feat: панель «Журнал профиля» и выделение карточки (T-10, задача 5)`.

---

### Task 6: Подтверждение выхода при работающих серверах

**Files:**
- Modify: `src/onecstarter/ui/shell.py`, `src/onecstarter/ui/app.py`
- Test: `tests/ui/test_shell.py`, `tests/ui/test_app.py`

**Interfaces:**
- Produces: `MainWindow.confirm_quit: Callable[[], bool] | None = None` (атрибут, ставится сборкой — как `settings_store`); `closeEvent`: ветка `close_to_tray` НЕ меняется (скрытие — не выход, серверы живут, §12.2); иначе — если `confirm_quit` задан и вернул `False` → `event.ignore()`, окно остаётся. В `app.py`: `_confirm_quit_with_servers(running_count: Callable[[], int], ask: Callable[[str], bool]) -> bool` — функция уровня модуля: `n = running_count()`; `n == 0` → `True`; иначе `ask(f"Остановить {n} серверов и выйти?")` (тексты склонения: 1 — «сервер», 2-4 — «сервера», иначе «серверов» — маленький чистый помощник `_servers_word(n)` с табличным тестом). Проводка: `window.confirm_quit = lambda: _confirm_quit_with_servers(servers_workspace.running_count, <QMessageBox.question-обёртка, дефолтная кнопка No>)`; трей: `create_tray(..., on_quit=request_quit, ...)`, где `request_quit()` — тот же гейт + `application.quit()`. `run_smoke`: `confirm_quit` не ставится (гейта нет).

- [ ] **Step 1: Тесты** — ЗАЩИТНЫЙ `test_close_with_running_servers_and_declined_confirmation_keeps_window` («ЗАЩИТНЫЙ ТЕСТ: отказ в подтверждении не закрывает окно и не гасит серверы, §12.3»; confirm_quit=lambda: False → после close() окно видимо); `test_close_without_servers_needs_no_confirmation` (счётчик вызовов ask == 0); `test_close_to_tray_hides_without_asking` (гейт не зван); `_confirm_quit_with_servers` — таблица: 0 → True без ask; 3 → текст «Остановить 3 сервера и выйти?»; отказ → False; `_servers_word` — таблица склонений (1/2/5/11/21). Трей: `request_quit` при отказе не зовёт quit (журнал фейка).

- [ ] **Step 2: RED.** **Step 3: Реализация.** **Step 4: GREEN.**

- [ ] **Step 5:** коммит `feat: подтверждение выхода при работающих серверах (T-10, задача 6)`.

---

### Task 7: Проводка app.py — Job, spawn, панель, smoke

**Files:**
- Modify: `src/onecstarter/ui/app.py`
- Test: `tests/ui/test_app.py`

**Interfaces:**
- Produces: `_build_main_window` — новый keyword-параметр `server_job: ServerJob | NullJob | None = None` (None → `ServerJob()`); `logs_dir = <servers.json>.parent / "logs" / "servers"` (от `runtime.servers`); `ServersWorkspace(..., logs_dir=logs_dir, server_spawn=lambda command, log: spawn_server(command, log, job))`; панель из задачи 5 в компоновке раздела; `confirm_quit`/`request_quit` из задачи 6. `run_smoke`: `server_job=NullJob()` (плюс существующие NullScanner/NullControl/registered_radmin). Выход после подтверждения — обычный `quit`: дерево гасит Job при смерти процесса ([Ф] Б2 T-09), явного кода остановки нет — зафиксировать комментарием.

- [ ] **Step 1: Тесты** — сборка окна создаёт `ServersView` с панелью; ЗАЩИТНЫЙ `test_run_smoke_uses_null_job` («ЗАЩИТНЫЙ ТЕСТ: самопроверка не создаёт kernel-объект Job и никого туда не кладёт» — фейковый ServerJob-конструктор не зван; образец — test_run_smoke_uses_null_scanner); проводка `confirm_quit` стоит на окне; `monitor`/сканы — без изменений (существующие тесты остаются зелёными).

- [ ] **Step 2: RED.** **Step 3: Реализация.** **Step 4: GREEN.**

- [ ] **Step 5:** коммит `feat: проводка T-10 — Job, серверный spawn, панель журнала (T-10, задача 7)`.

---

### Task 8: Документы — мокап и синхронизация спеки

**Files:**
- Modify: `docs/superpowers/specs/assets/2026-08-26-v2-servers-mockup.html`, `docs/superpowers/specs/2026-08-26-v2-servers-design.md`

**Шаги:**
- [ ] **Step 1:** Мокап: в секцию «Раздел „Серверы"» добавить панель «ЖУРНАЛ ПРОФИЛЯ» низом (glabel + моноширинный блок с примером строк `[09:05:07] запуск: …`, `[09:05:19] работает · PID 18244 …`, строка dbgs), выделенная карточка — рамка акцентом; обе темы.
- [ ] **Step 2:** Спека: в §2.3 и §12 статусные фразы «реализуется T-10» заменить на «реализовано T-10»; убедиться, что ни одна строка §3–§8 не обещает «переживает закрытие» без пометки о пересмотре.
- [ ] **Step 3:** коммит `docs: мокап панели журнала, спека синхронизирована с T-10`.

---

### Task 9: Verification-only — гейт, сборка, мутационная стадия

**Files:**
- Modify: `docs/tasks.md`

**Шаги:**
- [ ] **Step 1:** `uv run pytest -q`, `uv run ruff check .`, `uv run mypy` — коды 0.
- [ ] **Step 2:** `build/build.ps1` — сборка + smoke зелёные; зафиксировать вес dist.
- [ ] **Step 3: Мутационная стадия** — независимый агент (не автор тестов), по мутации на защитный тест, результат дословно, откат, чистое дерево:
  1. `job.py`: `assign` не кладёт процесс в Job (вызов `AssignProcessToJobObject` снят) → `test_close_kills_parent_and_grandchild`.
  2. `server_journal.py`: `rotate_journal` удаляет текущий вместо переноса → `test_current_becomes_previous`.
  3. `servers.py`: `start` не ротирует и не пишет событие → `test_start_rotates_journal_and_logs_command`.
  4. `servers.py`: OSError из spawn не пишет `отказ запуска` → `test_failed_spawn_logs_the_refusal`.
  5. `shell.py`: `closeEvent` игнорирует отказ `confirm_quit` (закрывает всегда) → `test_close_with_running_servers_and_declined_confirmation_keeps_window`.
  6. `app.py`: `run_smoke` создаёт настоящий `ServerJob` → `test_run_smoke_uses_null_job`.
- [ ] **Step 4:** `docs/tasks.md`: T-10 — итог (счётчик тестов, сборка, мутации), T-09.3-хвост перенести в долг вехи, если кириллица так и не встретилась; ручной чек-лист T-10 для заказчика: запуск профиля из сборки — окон нет, журнал наполняется, выход с подтверждением гасит дерево, крах (kill лаунчера из Диспетчера) гасит дерево.
- [ ] **Step 5:** коммит `docs: T-10 — итог реализации, smoke и мутационная стадия`.

---

## Чего в плане нет — сознательно

- ConPTY и любые попытки достать баннеры rmngr/rphost — [Ф] А1 T-09: недостижимы; журнал честно наш.
- Настройка периода tail/размера хвоста — константы (1000 мс, 500 строк), YAGNI.
- Экспорт/очистка журналов из UI — файлы доступны через каталог, «Открыть каталог журналов» не строим до запроса.
- Graceful-остановка перед выходом — [Ф] Б2 T-07/T-09: жёсткое завершение безопасно для кластера, Job достаточно.
