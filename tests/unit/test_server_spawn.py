"""Серверный spawn: скрытая консоль, редирект stdout в файл, Job (T-10, задача 2)."""

import msvcrt
import sys
import time
import uuid
from pathlib import Path

import psutil
import pytest

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c import server_spawn
from onecstarter.platform_1c.job import JobError, NullJob, ServerJob
from onecstarter.platform_1c.server_spawn import spawn_server


def _printing_command() -> LaunchCommand:
    return LaunchCommand(
        executable=Path(sys.executable),
        arguments='-c "print(\'hello from child\', flush=True); import time; time.sleep(30)"',
    )


def _kill_if_alive(pid: int) -> None:
    if psutil.pid_exists(pid):
        psutil.Process(pid).kill()


class _FailingJob:
    """Фейк протокола `Job`, чей `assign()` всегда отказывает `JobError` (для защитного теста).

    Самостоятельный класс, не наследник `ServerJob`: сигнатура `spawn_server`
    принимает протокол `Job` (долг T-10 «закрытая уния» закрыт задачей 1
    T-12), наследование от конкретной реализации больше не нужно для
    прохождения mypy strict.
    """

    def assign(self, process_handle: int) -> None:
        raise JobError("подставной отказ assign для теста")

    def pids(self) -> tuple[int, ...]:
        return ()

    def close(self) -> None:
        pass

    def is_empty(self) -> bool:
        return True


def test_spawn_server_redirects_stdout_to_log_file(tmp_path: Path) -> None:
    log_path = tmp_path / "j.log"
    pid = spawn_server(_printing_command(), log_path, NullJob())
    try:
        assert psutil.pid_exists(pid)
        deadline = time.monotonic() + 5
        content = ""
        while time.monotonic() < deadline:
            if log_path.exists():
                content = log_path.read_text(encoding="ascii", errors="replace")
                if "hello from child" in content:
                    break
            time.sleep(0.05)
        assert "hello from child" in content, f"строка не появилась в журнале за 5 с: {content!r}"  # noqa: RUF001
    finally:
        _kill_if_alive(pid)


def test_spawn_server_process_dies_when_job_closes(tmp_path: Path) -> None:
    log_path = tmp_path / "j.log"
    job = ServerJob()
    pid = spawn_server(_printing_command(), log_path, job)
    try:
        assert psutil.pid_exists(pid)
        job.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and psutil.pid_exists(pid):
            time.sleep(0.05)
        assert not psutil.pid_exists(pid), "процесс пережил закрытие Job"
    finally:
        _kill_if_alive(pid)


def test_spawn_server_missing_log_dir_raises_oserror_and_spawns_nothing(tmp_path: Path) -> None:
    # Уникальный токен в аргументах — чтобы найти в дереве процессов именно
    # ЭТОТ вызов, а не случайный python.exe системы (антивирус, индексатор).  # noqa: RUF003
    token = f"onecstarter-marker-{uuid.uuid4().hex}"
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments=f'-c "import time; time.sleep(30)  # {token}"',
    )
    log_path = tmp_path / "no-such-dir" / "j.log"

    with pytest.raises(OSError):
        spawn_server(command, log_path, NullJob())

    time.sleep(0.2)  # дать бы успевшему стартовать процессу засветиться
    spawned = [
        proc
        for proc in psutil.process_iter(["cmdline"])
        if proc.info["cmdline"] and any(token in part for part in proc.info["cmdline"])
    ]
    for proc in spawned:
        proc.kill()
    assert not spawned, "процесс порождён, хотя открытие журнала должно было упасть раньше Popen"


def test_spawn_server_kills_process_when_job_assign_fails(tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: отказ job.assign() не оставляет сервер жить вне Job.

    Мутация «убрать try/except вокруг assign в spawn_server» оставит уже
    порождённый процесс сиротой без гарантии kill-on-close, ради которой
    Job вообще существует (ревью задачи 2, круг исправлений 1, Important).
    """  # noqa: RUF002
    log_path = tmp_path / "j.log"
    # Уникальный токен — чтобы найти в дереве процессов именно этот вызов,
    # а не случайный python.exe системы (тот же приём, что в тесте 3).  # noqa: RUF003
    token = f"onecstarter-marker-{uuid.uuid4().hex}"
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments=f'-c "import time; time.sleep(30)  # {token}"',
    )

    with pytest.raises(JobError):
        spawn_server(command, log_path, _FailingJob())

    deadline = time.monotonic() + 5
    spawned = [
        proc
        for proc in psutil.process_iter(["cmdline"])
        if proc.info["cmdline"] and any(token in part for part in proc.info["cmdline"])
    ]
    while time.monotonic() < deadline and spawned:
        time.sleep(0.05)
        spawned = [
            proc
            for proc in psutil.process_iter(["cmdline"])
            if proc.info["cmdline"] and any(token in part for part in proc.info["cmdline"])
        ]
    for proc in spawned:
        proc.kill()
    assert not spawned, "процесс пережил отказ job.assign() — остался жить вне Job"
    # Находка 1 ручного чек-листа T-10 (волна исправлений 29.08.2026):
    # `_open_append_shared` обязан закрыть СВОЙ fd (try/finally вокруг
    # Popen) ДО job.assign() — иначе хендл журнала утечёт вместе с отказом  # noqa: RUF003
    # Job, и Windows не даст удалить файл, пока хендл открыт (WinError 32).
    # Мутация: убрать `finally: os.close(fd)` в `_open_append_shared`/
    # `spawn_server` — эта строка обязана упасть PermissionError.
    log_path.unlink()


def test_parent_event_survives_child_write(tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: строка, дописанная родителем при живом ребёнке-писателе, не затирается.

    НАХОДКА 1 ручного чек-листа T-10 (Critical, `manual-checklist.md`,
    раздел «Шаг 2»): хендл журнала ребёнку раньше открывался обычным
    `Path.open("ab")` — Windows даёт этому хендлу СВОЙ файловый указатель,
    застывший на позиции конца файла в момент `spawn`. Координатор
    (`ServersWorkspace.log_event`/`append_event`) пишет СВОИМ отдельным
    хендлом (`open("a")` при каждом вызове) и честно попадает в конец
    файла — но когда ребёнок затем пишет через СВОЙ старый хендл, запись
    идёт по ЕГО (устаревшему) указателю, поверх уже дописанной строки
    координатора. В живом прогоне 29.08.2026 так пропали `порождён PID`
    и `работает · PID` — их баннер платформы (длиннее события) просто
    затёр.

    Воспроизведено здесь честно, БЕЗ фейков: ребёнок — настоящий python-
    процесс, который спит 1,5 с (успевает пережить запись координатора)
    и только потом печатает строку длиннее 100 байт (`child_line`) —
    достаточно длинную, чтобы затирание, если оно случится, было видно
    невооружённым взглядом, не только по byte-offset. `spawn_server`
    обязан открыть хендл ребёнку через `_open_append_shared`
    (`FILE_APPEND_DATA` без `FILE_WRITE_DATA`) — запись по такому хендлу
    ОС атомарно направляет в ФАКТИЧЕСКИЙ конец файла независимо от
    указателя, сохранённого в самом хендле, — затирание становится
    невозможно на уровне ОС.

    Мутация: вернуть `spawn_server` на `log_path.open("ab")` вместо
    `_open_append_shared` — тест обязан упасть (строка координатора
    пропадёт из содержимого файла).
    """  # noqa: RUF002
    log_path = tmp_path / "j.log"
    child_line = "x" * 120
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments=(
            f"-c \"import time; time.sleep(1.5); print('{child_line}', flush=True)\""
        ),
    )
    pid = spawn_server(command, log_path, NullJob())
    try:
        # Координатор дописывает «событие» СВОИМ отдельным хендлом, пока
        # ребёнок ещё спит, — тот же приём, что `server_journal.append_event`.
        with log_path.open("a", encoding="utf-8") as f:
            f.write("[00:00:00] событие координатора\n")

        deadline = time.monotonic() + 5
        content = ""
        while time.monotonic() < deadline:
            content = log_path.read_text(encoding="utf-8", errors="replace")
            if child_line in content:
                break
            time.sleep(0.05)

        assert "событие координатора" in content, (
            f"строка координатора пропала из журнала: {content!r}"
        )
        assert child_line in content, f"строка ребёнка не появилась в журнале: {content!r}"
        parent_pos = content.index("событие координатора")
        child_pos = content.index(child_line)
        assert parent_pos < child_pos, "порядок строк нарушен — координатор писал раньше"
    finally:
        _kill_if_alive(pid)


def test_rotation_succeeds_while_child_holds_journal(tmp_path: Path) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: ротация журнала при живом держателе проходит — FILE_SHARE_DELETE.

    НАХОДКА 1 ручного чек-листа T-10 (побочный эффект лекарства):
    `_open_append_shared` открывает хендл ребёнку с `FILE_SHARE_DELETE` —
    `Path.replace` (то же, что делает `server_journal.rotate_journal`)
    обязан пройти без `OSError`, пока ребёнок жив и держит журнал. Это
    закрывает саму ПРИЧИНУ долга вехи T-10 («ротация журнала» —
    `docs/tasks.md`): раньше `Path.replace` падал `PermissionError
    [WinError 32]`, потому что `Path.open("ab")` не даёт `FILE_SHARE_DELETE`
    (эту ветку best-effort в `services/servers.py::start` трогать не
    нужно — она остаётся страховкой от ЧУЖИХ держателей, открывших файл
    обычным `open()`, см. `tests/unit/test_servers.py::
    test_start_survives_rotation_failure_when_previous_journal_is_locked`).

    Мутация: вернуть `spawn_server` на `log_path.open("ab")` — этот тест
    обязан упасть `PermissionError` на `log_path.replace(previous)`.
    """  # noqa: RUF002
    log_path = tmp_path / "j.log"
    child_line = "child banner after rotation"
    command = LaunchCommand(
        executable=Path(sys.executable),
        arguments=f"-c \"import time; time.sleep(3); print('{child_line}', flush=True)\"",
    )
    pid = spawn_server(command, log_path, NullJob())
    try:
        previous = tmp_path / "j.1.log"
        log_path.replace(previous)  # не должно поднять OSError — ребёнок ещё жив

        deadline = time.monotonic() + 5
        content = ""
        while time.monotonic() < deadline:
            if previous.exists():
                content = previous.read_text(encoding="utf-8", errors="replace")
                if child_line in content:
                    break
            time.sleep(0.05)

        assert child_line in content, (
            f"строка ребёнка не попала в переименованный файл: {content!r}"
        )
        assert not log_path.exists(), "новый текущий файл не должен появиться сам собой"
    finally:
        _kill_if_alive(pid)


def test_open_append_shared_closes_handle_when_open_osfhandle_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: отказ `msvcrt.open_osfhandle` не оставляет Win32-хендл висеть.

    Ревью волны исправлений (29.08.2026): `CreateFileW` и `msvcrt.
    open_osfhandle` — два разных ресурса (Win32 HANDLE и CRT fd); если
    `CreateFileW` успел (валидный хендл получен), а `open_osfhandle` следом
    отказал `OSError` (например, исчерпана таблица файловых дескрипторов
    CRT), сам этот отказ Win32-хендл не закрывает — без явного `CloseHandle`
    в `except`-ветке `_open_append_shared` хендл утёк бы.

    НЕ проверяется через `log_path.unlink()` после отказа: `CreateFileW`
    здесь открывается с `FILE_SHARE_DELETE` (лекарство находки 1, докстринг
    модуля) — этот флаг САМ ПО СЕБЕ разрешает удаление/переименование файла
    ЛЮБЫМ держателем, включая посторонний, независимо от того, закрыт ли
    именно ЭТОТ хендл. Проверено эмпирически при подготовке теста: с
    искусственно убранным `CloseHandle` (мутация) `log_path.unlink()`
    всё равно проходил без ошибки — `unlink()` НЕ различает «хендл закрыт»
    и «хендл утёк, но расшарен на удаление», то есть не годится как
    единственная проверка. Вместо этого сравнивается число открытых
    Win32-хендлов процесса (`psutil.Process().num_handles()`) до и после
    отказа — `CloseHandle` в `except`-ветке обязан вернуть счётчик к
    прежнему значению.

    Дёшево воспроизведено без настоящего исчерпания таблицы CRT-дескрипторов:
    `msvcrt.open_osfhandle` подменена функцией, которая кидает `OSError`
    сразу после того, как `CreateFileW` честно создал файл и вернул хендл.
    Мутация: убрать `try/except OSError` (и `CloseHandle` внутри него)
    вокруг `open_osfhandle` в `_open_append_shared` — счётчик хендлов
    процесса ниже обязан вырасти и не вернуться к прежнему значению
    (проверено вручную при подготовке теста).
    """  # noqa: RUF002
    log_path = tmp_path / "j.log"

    def _failing_open_osfhandle(handle: int, flags: int) -> int:
        raise OSError("подставной отказ open_osfhandle для теста")

    # Патчим стандартный модуль `msvcrt` напрямую, не через `server_spawn.
    # msvcrt`: `server_spawn.__all__` не экспортирует `msvcrt`, mypy strict
    # (`--no-implicit-reexport`) не пропустит доступ к нему как к атрибуту
    # модуля извне. Модули — синглтоны: правка атрибута здесь видна и
    # `server_spawn.py`, который зовёт `msvcrt.open_osfhandle` тем же
    # импортированным объектом.
    monkeypatch.setattr(msvcrt, "open_osfhandle", _failing_open_osfhandle)

    process = psutil.Process()
    before = process.num_handles()

    with pytest.raises(OSError, match="подставной отказ"):
        server_spawn._open_append_shared(log_path)

    after = process.num_handles()
    assert after <= before, f"хендл журнала утёк: было {before}, стало {after}"
