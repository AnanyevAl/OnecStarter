# План 3.2.1 — цена скана процессов и perf-режим

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать чтение командных строк у всех процессов системы ради семи нужных и дать программе perf-режим, который покажет, где на машине заказчика стоит главный поток.

**Architecture:** Правка `PsutilScanner` меняет только цену скана, не его результат. Замеры живут в новом модуле `onecstarter/perf.py` без Qt (инвариант 1) и пишут в отдельный `perf.log`, включаясь переменной окружения `ONECSTARTER_PERF`. Четыре точки замера: скан процессов, пересборка дерева баз, heartbeat главного потока и события дерева дольше порога.

**Tech Stack:** Python 3.14, PySide6 6.11.1, psutil 7.x, pytest + pytest-qt, ruff, mypy strict, PyInstaller one-dir.

Спека — [2026-09-23-v321-perf-diagnostics-design.md](../specs/2026-09-23-v321-perf-diagnostics-design.md). Её §-ссылки по тексту плана ведут туда.

## Global Constraints

- **Ветка** `fix/2026-09-23-perf-diagnostics` от `feat/2026-09-16-v32@0a92762`. В `master` не вливать: там 3.1.2, а у заказчика на сервере сборка 3.2.0 из ветки v3.2.
- **Инвариант 1: Qt только в `src/onecstarter/ui/`.** `perf.py` кладётся в корень пакета рядом с `diagnostics.py` и `PySide6` не импортирует — ни прямо, ни транзитивно. Новый модуль ядра обязан появиться строкой в `tests/unit/test_no_qt_in_core.py`, иначе протечка пройдёт тест зелёной.
- **Инвариант 5: секреты и содержимое — не в лог.** В perf-строки идут только метка операции, целое число миллисекунд и целые счётчики. Ни путей, ни имён баз, ни строк соединения, ни `cmdline`. Сигнатура `measure(stage: str, **counters: int)` делает передачу строки в счётчик ошибкой типов, а не вопросом дисциплины.
- **Команды:** `uv run pytest`, `uv run ruff check .`, `uv run mypy`. `mypy` в режиме `strict` для всего, кроме `onecstarter.ui.*`.
- **Полные прогоны pytest — в файл, не в `tail`:** `uv run pytest > e:/tmp/v321-<метка>.log 2>&1`. В проекте есть интермиттентный access violation pytest-qt; при обрезке вывода блок падения теряется.
- **Мутационная проверка обязательна** для задач 1 и 3 (оба теста проверяют **отсутствие** действия). Порядок: сломать реализацию → убедиться, что тест упал и на чём именно → откатить → записать результат в `docs/tasks.md`. Табличные тесты чистых функций мутации не требуют.
- **Версия — из одного места,** `pyproject.toml`. Поднимается до `3.2.1` в задаче 8, не раньше.
- **Русские комментарии и докстринги**, как во всём проекте. Правило `ruff` `RUF002/RUF003` требует `# noqa` на кириллицу в докстрингах и комментариях там, где линтер ругается — смотреть на соседние файлы.

---

### Task 1: Ленивый скан процессов

Корень дефекта (§2, §4): `cmdline` и `exe` читаются у всех процессов, фильтр по имени применяется после. Задача меняет цену, не результат.

**Files:**
- Modify: `src/onecstarter/platform_1c/process_scan.py:52-71` (тело `PsutilScanner`)
- Test: `tests/unit/test_process_scan.py`

**Interfaces:**
- Consumes: ничего от других задач — первая.
- Produces: `PsutilScanner(label: str = "")`, метод `snapshot(names: frozenset[str]) -> list[ProcessInfo]`. `ProcessInfo` и протокол `ProcessScanner` не меняются. Задача 3 добавит в `snapshot` замер, задача 3 же проставит метки в `ui/app.py`.

- [ ] **Step 1: Написать падающие тесты**

Дописать в конец `tests/unit/test_process_scan.py`. Фейк подменяет `psutil.process_iter` внутри модуля `process_scan` и считает обращения к дорогим полям:

```python
class _FakeProcess:
    """Процесс, считающий обращения к дорогим полям.

    `exe()`/`cmdline()` на Windows требуют открыть процесс и прочитать
    его адресное пространство, поэтому счётчик обращений — и есть
    предмет проверки: у несовпавших по имени их звать нельзя.
    """  # noqa: RUF002

    def __init__(
        self,
        pid: int,
        name: str,
        exe: str | None = r"C:\1cv8\bin\ragent.exe",
        argv: list[str] | None = None,
        exe_error: type[BaseException] | None = None,
        cmdline_error: type[BaseException] | None = None,
    ) -> None:
        self.pid = pid
        self.info = {"pid": pid, "name": name}
        self._exe = exe
        self._argv = [] if argv is None else argv
        self._exe_error = exe_error
        self._cmdline_error = cmdline_error
        self.detail_calls = 0

    def exe(self) -> str | None:
        self.detail_calls += 1
        if self._exe_error is not None:
            raise self._exe_error
        return self._exe

    def cmdline(self) -> list[str]:
        self.detail_calls += 1
        if self._cmdline_error is not None:
            raise self._cmdline_error
        return self._argv


def _with_processes(
    monkeypatch: pytest.MonkeyPatch, processes: list[_FakeProcess]
) -> None:
    monkeypatch.setattr(
        process_scan.psutil, "process_iter", lambda attrs: list(processes)
    )


def test_details_are_read_only_for_matching_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matching = _FakeProcess(1, "ragent.exe")
    others = [_FakeProcess(pid, f"chrome{pid}.exe") for pid in range(2, 40)]
    _with_processes(monkeypatch, [matching, *others])

    result = PsutilScanner().snapshot(frozenset({"ragent.exe"}))

    assert [p.pid for p in result] == [1]
    assert matching.detail_calls == 2  # exe + cmdline
    assert [p.detail_calls for p in others] == [0] * len(others)


def test_access_denied_on_one_field_keeps_the_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Прежняя редакция звала Process.as_dict, и тот сам переводил
    # недоступное поле в None ПООТДЕЛЬНОСТИ. Общий try вокруг обоих
    # чтений потерял бы доступный argv у процесса с недоступным exe.
    process = _FakeProcess(
        7, "ragent.exe", exe_error=psutil.AccessDenied, argv=["ragent", "-port", "1540"]
    )
    _with_processes(monkeypatch, [process])

    found = PsutilScanner().snapshot(frozenset({"ragent.exe"}))[0]

    assert found.executable is None
    assert found.argv == ("ragent", "-port", "1540")


def test_process_that_died_between_name_and_details_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Прежняя редакция делала `continue` на NoSuchProcess, и процесс
    # в результат не попадал вовсе. Отдать его с пустыми полями значило бы
    # выдумать факт о том, чего уже нет.
    _with_processes(
        monkeypatch,
        [_FakeProcess(9, "ragent.exe", exe_error=psutil.NoSuchProcess)],
    )

    assert PsutilScanner().snapshot(frozenset({"ragent.exe"})) == []


def test_label_is_accepted_and_does_not_change_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(3, "ragent.exe")])

    labelled = PsutilScanner("servers").snapshot(frozenset({"ragent.exe"}))
    plain = PsutilScanner().snapshot(frozenset({"ragent.exe"}))

    assert labelled == plain
```

В начало файла добавить импорт модуля целиком (для `monkeypatch.setattr` на его `psutil`):

```python
from onecstarter.platform_1c import process_scan
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `uv run pytest tests/unit/test_process_scan.py -v`
Expected: четыре новых теста FAIL. `test_details_are_read_only_for_matching_processes` — на `assert [p.detail_calls for p in others] == [0] * 38` (прежняя редакция не зовёт `exe()`/`cmdline()` вовсе, а берёт значения из `process.info`, поэтому счётчик нулевой, но и у совпавшего он нулевой → упадёт на `matching.detail_calls == 2`). `test_label_...` — `TypeError: PsutilScanner() takes no arguments`. Два существующих интеграционных теста — PASS, их трогать нельзя.

- [ ] **Step 3: Переписать `PsutilScanner`**

Заменить класс целиком:

```python
class PsutilScanner:
    """Настоящий снимок процессов. Единственное место в проекте с `psutil`.

    Имя берётся у всех процессов, `exe`/`cmdline` — только у совпавших.
    Порядок не косметический: имя отдаёт один системный вызов на весь
    список, а командная строка требует открыть процесс и прочитать его
    адресное пространство. Прежняя редакция запрашивала оба поля у всех
    сразу через `attrs` и платила за шестьсот процессов ради семи —
    замер 22.09.2026 на 651 процессе: 81–128 мс против 4,7–5,7 мс при
    том же результате (спека 3.2.1, §4).
    """  # noqa: RUF002

    def __init__(self, label: str = "") -> None:
        # Метка попадает в perf-строку (задача 3) и отличает скан серверов
        # от скана EDT: оба монитора держат свой экземпляр сканера.
        # На результат не влияет.
        self._label = label

    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        result: list[ProcessInfo] = []
        for process in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = process.info
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
            name = info.get("name")
            if name is None or name.casefold() not in names:
                continue
            details = _details_of(process)
            if details is None:
                # Процесс умер между чтением имени и чтением деталей.
                # Прежняя редакция теряла его тем же способом (`continue`
                # на NoSuchProcess), и это правильное поведение: отдать
                # запись с пустыми полями значило бы выдумать факт.
                continue
            executable, argv = details
            result.append(
                ProcessInfo(pid=info["pid"], name=name, executable=executable, argv=argv)
            )
        return result


def _details_of(
    process: psutil.Process,
) -> tuple[Path | None, tuple[str, ...] | None] | None:
    """`exe` и `cmdline` совпавшего процесса. `None` — процесса уже нет.

    Поля читаются ПООТДЕЛЬНОСТИ, и `AccessDenied` на одном не отменяет
    другое: ровно так вёл себя `Process.as_dict` в прежней редакции —
    он переводил каждое недоступное поле в `None` сам. Общий `try`
    вокруг обоих чтений молча потерял бы доступный `argv` у процесса
    с недоступным `exe` ([Ф] В1: чужой процесс или служба SYSTEM).
    """  # noqa: RUF002
    try:
        exe = process.exe()
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied:
        exe = None
    try:
        cmdline = process.cmdline()
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied:
        cmdline = None
    return (Path(exe) if exe else None, tuple(cmdline) if cmdline else None)
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `uv run pytest tests/unit/test_process_scan.py -v`
Expected: все PASS, включая два существующих интеграционных теста **без единой правки в них** — это и есть проверка того, что наблюдаемый результат прежний.

- [ ] **Step 5: Мутационная проверка**

Временно вернуть жадное чтение: в `snapshot` заменить `attrs=["pid", "name"]` на `attrs=["pid", "name", "cmdline", "exe"]` и собрать `details` из `info` вместо `_details_of`.

Run: `uv run pytest tests/unit/test_process_scan.py -v`
Expected: `test_details_are_read_only_for_matching_processes` FAIL на `matching.detail_calls == 2` (детали пришли из `info`, методы не звались). Откатить мутацию, перезапустить — PASS. Записать результат в `docs/tasks.md` в задаче 8.

- [ ] **Step 6: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/platform_1c/process_scan.py tests/unit/test_process_scan.py
git commit -m "perf(scan): детали процессов читаются только у совпавших по имени

Замер 22.09.2026 на 651 процессе: 81-128 мс против 4,7-5,7 мс при том же
результате. AccessDenied ловится отдельно по каждому полю (прежний as_dict
вёл себя так же), NoSuchProcess пропускает процесс целиком."
```

---

### Task 2: Модуль perf.py и включение режима

§5 спеки. Задача самодостаточна: после неё `ONECSTARTER_PERF=1` создаёт пустой `perf.log`, а `measure` умеет писать в него.

**Files:**
- Create: `src/onecstarter/perf.py`
- Create: `tests/unit/test_perf.py`
- Modify: `src/onecstarter/__main__.py:91-93` (в `main`, рядом с `setup_logging`)
- Modify: `tests/unit/test_no_qt_in_core.py:8-9` (список `CORE`)

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `perf.is_enabled(env: Mapping[str, str]) -> bool`
  - `perf.setup(env: Mapping[str, str]) -> Path | None`
  - `perf.measure(stage: str, **counters: int) -> Iterator[dict[str, int]]` — контекстный менеджер, отдающий словарь счётчиков, куда можно дописать значения внутри блока
  - `perf.LOG_NAME = "perf.log"`, `perf.ENV_NAME = "ONECSTARTER_PERF"`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_perf.py`:

```python
"""perf: замеры под флагом — без Qt, отдельный файл лога."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from onecstarter import perf


def _cleanup() -> None:
    """Снять обработчики своего логгера и сбросить флаг между тестами.

    Тот же приём, что `_cleanup_root` в test_diagnostics.py, но логгер
    свой, а не корневой: perf не имеет права добавлять обработчики
    в корень — иначе его строки утекли бы в onecstarter.log.
    """  # noqa: RUF002
    perf.reset_for_tests()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    _cleanup()
    yield
    _cleanup()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("Yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("мусор", False),
    ],
)
def test_is_enabled(value: str, expected: bool) -> None:
    assert perf.is_enabled({perf.ENV_NAME: value}) is expected


def test_is_enabled_without_the_variable() -> None:
    assert perf.is_enabled({}) is False


def test_setup_creates_the_file_when_enabled(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path == tmp_path / "OneCStarter" / "logs" / "perf.log"


def test_setup_does_nothing_when_disabled(tmp_path: Path) -> None:
    assert perf.setup({"APPDATA": str(tmp_path)}) is None
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()


def test_setup_survives_unwritable_directory(tmp_path: Path) -> None:
    blocker = tmp_path / "APPDATA"
    blocker.write_text("файл на месте каталога", encoding="utf-8")
    assert perf.setup({"APPDATA": str(blocker), perf.ENV_NAME: "1"}) is None


def _read(path: Path) -> str:
    for handler in logging.getLogger("onecstarter.perf").handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def test_measure_writes_stage_duration_and_counters(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None

    with perf.measure("скан процессов (servers)", просмотрено=1183) as counters:
        counters["совпало"] = 7

    line = _read(path).strip()
    assert " PERF скан процессов (servers): " in line
    assert " мс, просмотрено=1183, совпало=7" in line


def test_measure_writes_nothing_when_disabled(tmp_path: Path) -> None:
    perf.setup({"APPDATA": str(tmp_path)})
    with perf.measure("что-то", строк=3) as counters:
        counters["ещё"] = 1
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()


def test_measure_reports_even_when_the_block_raises(tmp_path: Path) -> None:
    # Замер — диагностика; потерять его на отказе значило бы потерять
    # ровно тот случай, ради которого он и включён.
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    with pytest.raises(ValueError), perf.measure("падучая операция"):
        raise ValueError("нарочно")
    assert "падучая операция" in _read(path)


def test_log_line_carries_no_logger_name_and_no_level(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    with perf.measure("операция"):
        pass
    line = _read(path).strip()
    assert "onecstarter.perf" not in line
    assert "INFO" not in line


def test_enabled_reflects_setup(tmp_path: Path) -> None:
    assert perf.enabled() is False
    perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert perf.enabled() is True


def test_repeated_setup_does_not_duplicate_log_lines(tmp_path: Path) -> None:
    # Повторный setup — не гипотетика: в __main__ он может позваться дважды
    # при повторном входе в main (тесты, будущие сценарии перезапуска).
    # Второй RotatingFileHandler на тот же файл задвоил бы каждую строку
    # замера, и любой подсчёт по логу стал бы неверным вдвое.
    env = {"APPDATA": str(tmp_path), perf.ENV_NAME: "1"}
    first = perf.setup(env)
    second = perf.setup(env)
    assert first == second
    assert first is not None

    with perf.measure("test-stage", n=1):
        pass

    lines = [line for line in _read(first).splitlines() if line.strip()]
    assert len(lines) == 1


def test_failed_repeated_setup_keeps_the_working_handler(tmp_path: Path) -> None:
    # Отказ поверх УЖЕ РАБОТАЮЩЕГО setup — не то же самое, что отказ с нуля  # noqa: RUF003
    # (test_setup_survives_unwritable_directory): здесь есть что терять.
    # Если второй setup сносит рабочий обработчик раньше, чем убедится,
    # что новый создался, — замеры первого вызова молча пропадают:
    # _enabled остаётся True, а писать некуда (propagate=False, до  # noqa: RUF003
    # lastResort уровень INFO не дотягивает).
    first = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert first is not None

    blocker = tmp_path / "заблокированный" / "APPDATA"
    blocker.parent.mkdir(parents=True)
    blocker.write_text("файл на месте каталога", encoding="utf-8")
    second = perf.setup({"APPDATA": str(blocker), perf.ENV_NAME: "1"})
    assert second is None

    with perf.measure("после неудачного повторного setup"):
        pass

    assert "после неудачного повторного setup" in _read(first)
```

Порядок в файле: `_read` объявляется до тестов, которые ею пользуются.

- [ ] **Step 2: Запустить, убедиться что падают**

Run: `uv run pytest tests/unit/test_perf.py -v`
Expected: все FAIL с `ModuleNotFoundError: No module named 'onecstarter.perf'`.

- [ ] **Step 3: Написать модуль**

Создать `src/onecstarter/perf.py`:

```python
"""Замеры длительности под флагом — отдельный файл, без Qt.

Включается переменной `ONECSTARTER_PERF`: portable запускают двойным
кликом, и ключ командной строки потребовал бы править ярлык, а переменная
одинаково работает для `OneCStarter.exe` и `OneCStarterc.exe`.

Свой файл, а не `onecstarter.log`: при включённом режиме поток строк
измеряется тысячами в час, и ротация основного лога (512 КБ) стёрла бы
за несколько часов историю стартов за месяц — ту самую, по которой
22.09.2026 и был поставлен диагноз (спека 3.2.1, §1).

В строки идут только метка операции, миллисекунды и ЦЕЛЫЕ счётчики:
лог прикладывают к issue (инвариант 5). Сигнатура `**counters: int`
делает передачу пути или имени базы вместо счётчика ошибкой типов,
а не вопросом дисциплины исполнителя — но только для счётчиков: `stage`
типизирован как `str`, и mypy пропустит в него любую строку, включая
путь или имя базы. За тем, что `stage` — литерал, а не собранная
из данных строка, следит вызывающий код; подробнее — в докстринге
`measure`.
"""  # noqa: RUF002

import logging
import logging.handlers
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

LOG_NAME = "perf.log"
ENV_NAME = "ONECSTARTER_PERF"
_TRUE = frozenset({"1", "true", "yes", "on"})
# Слово PERF — литерал, а не уровень записи: имя логгера в строку
# не выводится, все записи файла принадлежат одному логгеру, и повторять
# его в каждой строке незачем.
_FORMAT = "%(asctime)s PERF %(message)s"
# 4 МБ × 3 — около пяти суток при двух сканах в 5 с (спека §11).
_MAX_BYTES = 4 * 1024 * 1024
_BACKUPS = 3

_log = logging.getLogger("onecstarter.perf")
_enabled = False


def is_enabled(env: Mapping[str, str]) -> bool:
    """Включён ли режим. Чистая функция, ничего не настраивает."""
    return env.get(ENV_NAME, "").strip().casefold() in _TRUE


def enabled() -> bool:
    """Включён ли режим ПОСЛЕ `setup`. Для горячих мест, зовущих часто."""
    return _enabled


def setup(env: Mapping[str, str]) -> Path | None:
    """Настроить perf-лог. `None` — режим выключен либо файл не вышел.

    Отказ не роняет программу — тот же принцип, что у
    `diagnostics.setup_logging`: приложение важнее лога.

    Идемпотентна: повторный вызов не добавляет второй обработчик поверх
    старого (иначе `measure` задваивал бы каждую строку и держал открытым
    лишний файловый дескриптор) — но снимает прежний ТОЛЬКО после того,
    как новый успешно создан. Отказ создания (недоступный каталог) обязан
    заставать прежнее рабочее состояние нетронутым: обратный порядок
    однажды уже приводил к тому, что второй неудачный `setup` сносил
    рабочий обработчик первого, `_enabled` оставался `True`, а строки
    `measure` после этого молча терялись — писать было некуда.
    """  # noqa: RUF002
    global _enabled
    if not is_enabled(env):
        return None
    directory = Path(env.get("APPDATA", ".")) / "OneCStarter" / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            directory / LOG_NAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUPS,
            encoding="utf-8",
        )
    except OSError:
        # Прежнее состояние (обработчики, _enabled) не тронуто: если до
        # этого вызова режим уже работал, он продолжает работать.
        return None
    handler.setFormatter(logging.Formatter(_FORMAT))
    for old in list(_log.handlers):
        _log.removeHandler(old)
        old.close()
    _log.setLevel(logging.INFO)
    _log.addHandler(handler)
    # Свои строки не уходят в корневой логгер и, значит, в onecstarter.log:
    # иначе включённый режим залил бы основной лог и стёр его историю
    # ротацией — ровно то, ради чего файл и разделён.
    _log.propagate = False
    _enabled = True
    return directory / LOG_NAME


@contextmanager
def measure(stage: str, **counters: int) -> Iterator[dict[str, int]]:
    """Замерить блок и записать строку. При выключенном режиме — пустышка.

    Отдаёт словарь счётчиков: величина бывает известна только по ходу
    блока (число строк в пересборке дерева). Строка пишется и тогда,
    когда блок бросил исключение: замер — диагностика, и потерять его
    на отказе значило бы потерять ровно тот случай, ради которого
    режим и включён.

    `stage` обязан быть литералом ровно с текстом операции, а не строкой,
    собранной из данных (путь, имя базы, строка соединения) — mypy это
    не проверит: типы гарантируют целочисленность только `**counters`,
    `stage: str` пропустит что угодно. Ответственность за это несёт
    вызывающий код (инвариант 5).
    """  # noqa: RUF002
    if not _enabled:
        yield dict(counters)
        return
    values = dict(counters)
    started = time.monotonic()
    try:
        yield values
    finally:
        elapsed = int((time.monotonic() - started) * 1000)
        tail = "".join(f", {key}={value}" for key, value in values.items())
        _log.info("%s: %d мс%s", stage, elapsed, tail)


def reset_for_tests() -> None:
    """Снять обработчики и выключить режим. Только для тестов."""
    global _enabled
    for handler in list(_log.handlers):
        _log.removeHandler(handler)
        handler.close()
    _enabled = False
```

- [ ] **Step 4: Запустить тесты модуля**

Run: `uv run pytest tests/unit/test_perf.py -v`
Expected: все PASS.

- [ ] **Step 5: Внести модуль в тест изоляции Qt**

В `tests/unit/test_no_qt_in_core.py` добавить в кортеж `CORE` сразу после `"onecstarter.diagnostics",`:

```python
    "onecstarter.perf",
```

Run: `uv run pytest tests/unit/test_no_qt_in_core.py -v`
Expected: PASS.

- [ ] **Step 6: Позвать setup из точки входа**

В `src/onecstarter/__main__.py` добавить импорт рядом с существующим:

```python
from onecstarter import perf as perf  # реэкспорт: entry.perf в тестах
```

и в `main`, сразу после `diagnostics.enable_faulthandler(os.environ)`:

```python
    perf.setup(os.environ)
```

- [ ] **Step 7: Проверить, что точка входа не сломалась**

Run: `uv run pytest tests/unit/test_entry_point.py -v`
Expected: все PASS без правок в тестах.

- [ ] **Step 8: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/perf.py src/onecstarter/__main__.py tests/unit/test_perf.py tests/unit/test_no_qt_in_core.py
git commit -m "feat(perf): модуль замеров под ONECSTARTER_PERF с отдельным perf.log

Режим выключен по умолчанию. Свой файл и своя ротация 4 МБ x 3, чтобы
поток замеров не стирал историю стартов в onecstarter.log. В строки идут
только метка, миллисекунды и целые счётчики (инвариант 5)."
```

---

### Task 3: Замер скана процессов и метки мониторов

§6 спеки, первая строка таблицы. Даёт ответ на вопрос «сколько процессов на сервере и сколько стоит скан», который сейчас неизвестен (§0).

**Files:**
- Modify: `src/onecstarter/platform_1c/process_scan.py` (метод `snapshot` из задачи 1)
- Modify: `src/onecstarter/ui/app.py:1043-1045` и `:1060-1064` (создание сканеров)
- Test: `tests/unit/test_process_scan.py`

**Interfaces:**
- Consumes: `PsutilScanner(label)` из задачи 1; `perf.measure`, `perf.setup`, `perf.reset_for_tests` из задачи 2.
- Produces: строка вида `скан процессов (servers): 412 мс, просмотрено=1183, совпало=7`.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_process_scan.py`:

```python
def test_scan_is_measured_with_counters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_processes(
        monkeypatch,
        [_FakeProcess(1, "ragent.exe"), _FakeProcess(2, "chrome.exe")],
    )
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    try:
        PsutilScanner("servers").snapshot(frozenset({"ragent.exe"}))
        for handler in logging.getLogger("onecstarter.perf").handlers:
            handler.flush()
        line = path.read_text(encoding="utf-8").strip()
    finally:
        perf.reset_for_tests()
    assert "скан процессов (servers): " in line
    assert "просмотрено=2" in line
    assert "совпало=1" in line


def test_scan_without_label_still_names_the_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(1, "ragent.exe")])
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    try:
        PsutilScanner().snapshot(frozenset({"ragent.exe"}))
        for handler in logging.getLogger("onecstarter.perf").handlers:
            handler.flush()
        line = path.read_text(encoding="utf-8").strip()
    finally:
        perf.reset_for_tests()
    assert "скан процессов: " in line
    assert "()" not in line


def test_scan_writes_nothing_when_perf_is_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_processes(monkeypatch, [_FakeProcess(1, "ragent.exe")])
    perf.setup({"APPDATA": str(tmp_path)})
    try:
        PsutilScanner("servers").snapshot(frozenset({"ragent.exe"}))
    finally:
        perf.reset_for_tests()
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()
```

Добавить в начало файла недостающие импорты:

```python
import logging

from onecstarter import perf
```

- [ ] **Step 2: Запустить, убедиться что падают**

Run: `uv run pytest tests/unit/test_process_scan.py -k "scan_is_measured or scan_without_label or scan_writes_nothing" -v`
Expected: первые два FAIL — файл пуст, строки нет. Третий может пройти случайно (замера нет вовсе) — это нормально, его смысл проявится после реализации, и он проверяется мутацией на шаге 5.

- [ ] **Step 3: Обернуть тело `snapshot` замером**

В `process_scan.py` добавить импорт `from onecstarter import perf` и переписать `snapshot`:

```python
    def snapshot(self, names: frozenset[str]) -> list[ProcessInfo]:
        stage = f"скан процессов ({self._label})" if self._label else "скан процессов"
        with perf.measure(stage) as counters:
            result: list[ProcessInfo] = []
            seen = 0
            for process in psutil.process_iter(attrs=["pid", "name"]):
                seen += 1
                try:
                    info = process.info
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
                name = info.get("name")
                if name is None or name.casefold() not in names:
                    continue
                details = _details_of(process)
                if details is None:
                    continue
                executable, argv = details
                result.append(
                    ProcessInfo(
                        pid=info["pid"], name=name, executable=executable, argv=argv
                    )
                )
            # Счётчики заполняются ДО выхода из блока — `measure` читает
            # словарь в `finally`, и дописать в него после выхода поздно.
            counters["просмотрено"] = seen
            counters["совпало"] = len(result)
            return result
```

- [ ] **Step 4: Запустить тесты сканера целиком**

Run: `uv run pytest tests/unit/test_process_scan.py -v`
Expected: все PASS, включая тесты задачи 1 и два исходных интеграционных.

- [ ] **Step 5: Мутационная проверка**

Ломать надо проверку включённости в `setup`, а НЕ условие в `measure`. Разница существенная и проверена на этой кодовой базе (находка ревью задачи 3, 23.09.2026): при выключенном режиме `setup` возвращает `None` до создания обработчика, у логгера `onecstarter.perf` обработчиков нет вовсе, и `_log.info` из мутированной `measure` уходит в `lastResort`, который режет запись по уровню `WARNING`. Файлу неоткуда взяться независимо от `measure` — мутация через неё оставляет оба теста зелёными и ничего не доказывает.

Это не значит, что guard `if not _enabled:` в `measure` бесполезен: он быстрый путь для горячих мест — пропускает `time.monotonic()`, построение словаря и форматирование строки. Мутацией такое назначение не проверяется в принципе, падение теста никогда не будет сигналом о производительности.

Временно сломать в `src/onecstarter/perf.py` проверку в начале `setup`: заменить `if not is_enabled(env):` на `if False:`.

Run: `uv run pytest tests/unit/test_process_scan.py::test_scan_writes_nothing_when_perf_is_off tests/unit/test_perf.py::test_measure_writes_nothing_when_disabled -v`
Expected: оба FAIL на `assert not ... .exists()` — при выключенном режиме файл появился. Откатить мутацию, перезапустить — PASS. Записать результат в `docs/tasks.md` в задаче 8.

- [ ] **Step 6: Проставить метки в проводке окна**

В `src/onecstarter/ui/app.py` заменить два места создания сканеров.

Было (около строки 1043):
```python
    monitor = ServerMonitor(
        process_scanner if process_scanner is not None else PsutilScanner(), parent=window
    )
```
Стало:
```python
    monitor = ServerMonitor(
        process_scanner if process_scanner is not None else PsutilScanner("servers"),
        parent=window,
    )
```

Было (около строки 1060):
```python
        edt_monitor = EdtMonitor(
            process_scanner if process_scanner is not None else PsutilScanner(),
```
Стало:
```python
        edt_monitor = EdtMonitor(
            process_scanner if process_scanner is not None else PsutilScanner("edt"),
```

- [ ] **Step 7: Проверить проводку окна**

Run: `uv run pytest tests/ui/test_app.py -v`
Expected: все PASS. Тесты подставляют свой `process_scanner`, поэтому метки на них не влияют.

- [ ] **Step 8: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/platform_1c/process_scan.py src/onecstarter/ui/app.py tests/unit/test_process_scan.py
git commit -m "feat(perf): длительность скана процессов с числом просмотренных и совпавших

Метка монитора (servers/edt) отличает два скана в логе. Число процессов
на машине заказчика сейчас неизвестно — эта строка и даст ответ."
```

---

### Task 4: Замер пересборки дерева баз

§6 спеки, вторая строка. Гипотеза о дорогой пересборке опровергнута (§3), но замер остаётся: если после правки скана UI не ускорится, эта строка отделит пересборку от всего прочего.

**Files:**
- Modify: `src/onecstarter/ui/bases/view.py:562-645` (метод `rebuild`)
- Test: `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `perf.measure`, `perf.setup`, `perf.reset_for_tests` из задачи 2.
- Produces: строка `пересборка списка баз: N мс, строк=M`. Метка без внутреннего двоеточия намеренно: `measure` дописывает своё `": N мс"`, и метка вида `раздел «Базы»: rebuild` дала бы в логе два двоеточия подряд (находка ревью задачи 4).

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/ui/test_bases_view.py`:

```python
def test_rebuild_is_measured_with_row_count(
    qtbot: Any, workspace_factory: Any, tmp_path: Path
) -> None:
    view, _calls, _errors, _opened = _view(qtbot, workspace_factory)
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    try:
        view.rebuild()
        for handler in logging.getLogger("onecstarter.perf").handlers:
            handler.flush()
        lines = [
            line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    finally:
        perf.reset_for_tests()
    assert len(lines) == 1
    assert "пересборка списка баз: " in lines[0]
    assert " мс, строк=" in lines[0]


def test_rebuild_writes_nothing_when_perf_is_off(
    qtbot: Any, workspace_factory: Any, tmp_path: Path
) -> None:
    view, _calls, _errors, _opened = _view(qtbot, workspace_factory)
    perf.setup({"APPDATA": str(tmp_path)})
    try:
        view.rebuild()
    finally:
        perf.reset_for_tests()
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()
```

Добавить в начало файла недостающие импорты (если их там ещё нет):

```python
import logging

from onecstarter import perf
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `uv run pytest tests/ui/test_bases_view.py -k "rebuild_is_measured" -v`
Expected: FAIL — файл пуст, `len(lines) == 1` не выполняется.

- [ ] **Step 3: Вынести тело `rebuild` и обернуть вызов**

В `view.py` добавить импорт `from onecstarter import perf`.

Переотступать восемьдесят строк тела внутрь `with` не нужно и рискованно: тело переезжает в приватный метод целиком, без единой правки внутри, а замер оборачивает его вызов.

Переименовать существующий метод `def rebuild(self) -> None:` в `def _rebuild_now(self) -> int:`, оставив докстринг и тело без изменений, и дописать в самый конец его тела (после `self._sync_panel()`):

```python
        return len(self._rows)
```

На освободившееся место поставить новый публичный метод:

```python
    def rebuild(self) -> None:
        """Пересобрать дерево, замерив пересборку при включённом perf-режиме.

        Тело живёт в `_rebuild_now` отдельным методом, а не внутри `with`:
        обёртка вокруг восьмидесяти строк существующего кода потребовала бы
        переотступить их целиком — правка, где легко потерять строку молча.
        """  # noqa: RUF002
        with perf.measure("пересборка списка баз") as counters:
            counters["строк"] = self._rebuild_now()
```

Внешние вызовы `self.rebuild()` и подмены `view.rebuild` в тестах продолжают работать: имя и сигнатура публичного метода прежние.

- [ ] **Step 4: Запустить тесты раздела**

Run: `uv run pytest tests/ui/test_bases_view.py -v`
Expected: все PASS — и два новых, и все существующие тесты раздела без правок.

- [ ] **Step 5: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/bases/view.py tests/ui/test_bases_view.py
git commit -m "feat(perf): замер пересборки дерева баз с числом строк"
```

---

### Task 5: Heartbeat главного потока

§6 спеки, третья строка. Главный компонент вехи: он ловит простой главного потока независимо от причины и потому остаётся полезным, даже если диагноз §2 окажется неверным.

**Files:**
- Create: `src/onecstarter/ui/heartbeat.py`
- Create: `tests/ui/test_heartbeat.py`
- Modify: `src/onecstarter/ui/app.py` (в `main`, рядом с `tasks.start()`)

**Предупреждение о тестах (находка ревью задачи 5, 23.09.2026).** Теста
`test_each_tick_measures_from_the_previous_one` НЕДОСТАТОЧНО: его первый тик
сам превышает порог, и на нём мутация «обновлять `_last` только в ветке
отчёта» ведёт себя неотличимо от правильного кода. Дыру закрывает
`test_consecutive_short_ticks_stay_silent` — несколько коротких тиков подряд,
ни один из которых не запаздывал. Без него весь набор оставался зелёным на
реализации, которая врёт о простое в обычной работе.

**Interfaces:**
- Consumes: `perf.measure` не используется — строка пишется напрямую через `perf`; нужны `perf.enabled()` из задачи 2.
- Produces:
  - `Heartbeat(parent: QObject | None = None, *, interval_ms: int = 50, threshold_ms: int = 150, clock: Callable[[], float] = time.monotonic)` с методами `start()` и `_tick()`
  - `maybe_start_heartbeat(env: Mapping[str, str], parent: QObject) -> Heartbeat | None`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/ui/test_heartbeat.py`:

```python
"""Heartbeat главного потока: опоздание тика — это простой."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject

from onecstarter import perf
from onecstarter.ui.heartbeat import Heartbeat, maybe_start_heartbeat


class _Clock:
    """Часы под управлением теста: ждать настоящие 150 мс незачем."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _lines(path: Path) -> list[str]:
    for handler in logging.getLogger("onecstarter.perf").handlers:
        handler.flush()
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_long_stall_is_reported(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        clock.now += 0.430  # 430 мс вместо ожидаемых 50
        beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert len(lines) == 1
    assert "главный поток стоял 430 мс" in lines[0]


def test_short_gap_is_silent(tmp_path: Path) -> None:
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        clock.now += 0.120  # 120 мс — меньше порога
        beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert lines == []


def test_each_tick_measures_from_the_previous_one(tmp_path: Path) -> None:
    # Без обновления отметки на каждом тике второй тик посчитал бы
    # паузу от самого старта и отчитался бы о простое, которого не было.
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        clock.now += 0.430
        beat._tick()
        clock.now += 0.050
        beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert len(lines) == 1


def test_consecutive_short_ticks_stay_silent(tmp_path: Path) -> None:
    # Мутация «обновлять `_last` только в ветке отчёта» на этом тесте не
    # проходит: если ни один тик сам не превысил порог, отметка никогда
    # не обновляется, и разрыв копится от старта — 4x50 мс дают 200 мс
    # «простоя», которого не было. Правильная реализация обновляет
    # `_last` на каждом тике и не даёт разрыву накопиться.
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    clock = _Clock()
    try:
        beat = Heartbeat(interval_ms=50, threshold_ms=150, clock=clock)
        beat.start()
        for _ in range(4):
            clock.now += 0.050
            beat._tick()
        lines = _lines(path)
    finally:
        perf.reset_for_tests()
    assert lines == []


def test_not_started_when_perf_is_off(tmp_path: Path) -> None:
    perf.setup({"APPDATA": str(tmp_path)})
    parent = QObject()
    try:
        assert maybe_start_heartbeat({"APPDATA": str(tmp_path)}, parent) is None
    finally:
        perf.reset_for_tests()


def test_started_when_perf_is_on(tmp_path: Path) -> None:
    env = {"APPDATA": str(tmp_path), perf.ENV_NAME: "1"}
    perf.setup(env)
    parent = QObject()
    try:
        beat = maybe_start_heartbeat(env, parent)
        assert beat is not None
        assert beat.parent() is parent
    finally:
        perf.reset_for_tests()
```

- [ ] **Step 2: Запустить, убедиться что падают**

Run: `uv run pytest tests/ui/test_heartbeat.py -v`
Expected: все FAIL с `ModuleNotFoundError: No module named 'onecstarter.ui.heartbeat'`.

- [ ] **Step 3: Написать модуль**

Создать `src/onecstarter/ui/heartbeat.py`:

```python
"""Простой главного потока, измеренный опозданием собственного тика.

Таймер живёт в главном потоке и обязан тикать каждые `interval_ms`.
Если тик пришёл заметно позже — ровно столько главный поток был ничем
не занят по своей воле: его держали. Причина безразлична — GIL под
нативным вызовом, долгая отрисовка, чужой код; поэтому heartbeat
остаётся полезным, даже если диагноз спеки 3.2.1 §2 окажется неверным.

Создаётся только при включённом perf-режиме: 20 пробуждений в секунду
даром не нужны (спека §11).
"""  # noqa: RUF002

import logging
import time
from collections.abc import Callable, Mapping

from PySide6.QtCore import QObject, QTimer

from onecstarter import perf

_log = logging.getLogger("onecstarter.perf")


class Heartbeat(QObject):
    """Тикает в главном потоке и докладывает о собственных опозданиях."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        interval_ms: int = 50,
        threshold_ms: int = 150,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self._threshold_ms = threshold_ms
        # Часы инъекцией: тест не обязан ждать настоящие 150 мс, чтобы
        # проверить порог, — тот же приём, что `now=` у Workspace.
        self._clock = clock
        self._last = clock()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._last = self._clock()
        self._timer.start()

    def _tick(self) -> None:
        now = self._clock()
        # round(), не int(): при накоплении дробных секунд (клок теста,
        # монотонные часы) усечение вниз однажды уже дало 429 мс вместо
        # фактических 430 — ошибка представления float, не логики.
        gap_ms = round((now - self._last) * 1000)
        # Отметка обновляется ВСЕГДА, до всякого решения о записи: иначе
        # следующий тик считал бы паузу от предыдущего опоздания и
        # доложил бы о простое, которого не было.
        self._last = now
        if gap_ms >= self._threshold_ms:
            _log.info("главный поток стоял %d мс", gap_ms)


def maybe_start_heartbeat(env: Mapping[str, str], parent: QObject) -> Heartbeat | None:
    """Завести heartbeat, если режим включён. `None` — выключен.

    Отдельная функция, а не условие в `main`: развилка проверяется
    таблично, без поднятия окна.
    """  # noqa: RUF002
    if not perf.is_enabled(env):
        return None
    beat = Heartbeat(parent)
    beat.start()
    return beat
```

- [ ] **Step 4: Запустить тесты heartbeat**

Run: `uv run pytest tests/ui/test_heartbeat.py -v`
Expected: все PASS.

- [ ] **Step 5: Подключить в `main`**

В `src/onecstarter/ui/app.py` добавить импорт:

```python
from onecstarter.ui.heartbeat import maybe_start_heartbeat
```

и в функции `main`, сразу после строки `tasks.start()`:

```python
    # Время жизни — окно, как у мониторов: ссылка нужна, иначе объект
    # соберёт сборщик мусора и тики прекратятся молча.
    maybe_start_heartbeat(os.environ, window)
```

- [ ] **Step 6: Проверить, что окно собирается**

Run: `uv run pytest tests/ui/test_app.py -v`
Expected: все PASS.

- [ ] **Step 7: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/heartbeat.py src/onecstarter/ui/app.py tests/ui/test_heartbeat.py
git commit -m "feat(perf): heartbeat главного потока — опоздание тика как простой

Ловит простой независимо от причины: GIL, отрисовка, чужой код. Порог
150 мс при интервале 50 мс. Создаётся только при включённом perf-режиме."
```

---

### Task 6: Замер событий дерева баз

§6 спеки, четвёртая строка. Раскрытие группы — то, на что заказчик жалуется прямо, — нашим кодом не обрабатывается вовсе; без этой точки оно осталось бы безымянной паузой heartbeat.

**Files:**
- Modify: `src/onecstarter/ui/bases/view.py:203-206` (`_BasesTree.__init__`), плюс новый метод `event`
- Test: `tests/ui/test_bases_view.py`

**Ловушка pytest-qt (находка задачи 6, 23.09.2026).** Тесты обязаны сбрасывать
`tree._perf = False` в `finally` ДО `perf.reset_for_tests()`. Без этого они падают
стабильно, а не изредка: `_BasesTree` — живой видимый виджет, `pytest-qt` зовёт
`QApplication.processEvents()` в хуке `pytest_runtest_call`, и отложенные события
дерева проходят через `event()` уже исчерпанным тестовым итератором часов —
`RuntimeError: generator raised StopIteration`. `monkeypatch.setattr` эту проблему
НЕ решает, и это проверено экспериментом при ревью: его откат происходит в фазе
teardown, то есть ПОЗЖЕ, чем `_process_events()` после фазы call. Помогает только
сброс внутри тела теста.

**Interfaces:**
- Consumes: `perf.is_enabled` из задачи 2. `perf.enabled()` здесь НЕ нужен: флаг читается один раз в `__init__`, а не на каждом событии, — в этом и смысл атрибута.
- Produces: строка `дерево баз: событие <ИмяТипа> N мс`.

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/ui/test_bases_view.py`:

```python
def test_slow_tree_event_is_reported(
    qtbot: Any, workspace_factory: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _calls, _errors, _opened = _view(qtbot, workspace_factory)
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    tree = view.tree()
    # Дерево читает флаг в __init__, а perf включён уже после его создания:
    # выставляем явно — так же, как это произойдёт в бою, где setup()
    # отрабатывает в main() до сборки окна.
    tree._perf = True
    # Часы дерева под управлением теста: настоящую паузу в 100 мс
    # воспроизводить незачем.
    ticks = iter([0.0, 0.250])
    monkeypatch.setattr(tree, "_clock", lambda: next(ticks))
    try:
        tree.event(QEvent(QEvent.Type.User))
        lines = _lines_of(path)
    finally:
        perf.reset_for_tests()
    assert len(lines) == 1
    assert "дерево баз: событие User 250 мс" in lines[0]


def test_fast_tree_event_is_silent(
    qtbot: Any, workspace_factory: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _calls, _errors, _opened = _view(qtbot, workspace_factory)
    path = perf.setup({"APPDATA": str(tmp_path), perf.ENV_NAME: "1"})
    assert path is not None
    tree = view.tree()
    tree._perf = True
    ticks = iter([0.0, 0.010])
    monkeypatch.setattr(tree, "_clock", lambda: next(ticks))
    try:
        tree.event(QEvent(QEvent.Type.User))
        lines = _lines_of(path)
    finally:
        perf.reset_for_tests()
    assert lines == []


def test_tree_events_are_not_measured_when_perf_is_off(
    qtbot: Any, workspace_factory: Any, tmp_path: Path
) -> None:
    view, _calls, _errors, _opened = _view(qtbot, workspace_factory)
    perf.setup({"APPDATA": str(tmp_path)})
    try:
        view.tree().event(QEvent(QEvent.Type.User))
    finally:
        perf.reset_for_tests()
    assert not (tmp_path / "OneCStarter" / "logs" / "perf.log").exists()
```

Вспомогательная функция `_lines_of` и импорт `QEvent` добавляются в файл до самих тестов — тесты выше уже ею пользуются:

```python
from PySide6.QtCore import QEvent


def _lines_of(path: Path) -> list[str]:
    for handler in logging.getLogger("onecstarter.perf").handlers:
        handler.flush()
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 2: Запустить, убедиться что падают**

Run: `uv run pytest tests/ui/test_bases_view.py -k "tree_event" -v`
Expected: FAIL — у `_BasesTree` нет ни `_perf`, ни `_clock`, ни своего `event`.

- [ ] **Step 3: Добавить замер в `_BasesTree`**

В `view.py` в `_BasesTree.__init__` после `self._view = view`:

```python
        # Флаг читается ОДИН РАЗ и хранится атрибутом: `event` — самый
        # горячий метод в проекте (каждое движение мыши, каждый таймер),
        # и вызов функции проверки на каждое событие там неуместен.
        self._perf = perf.is_enabled(os.environ)
        # Часы инъекцией — тем же приёмом, что у Heartbeat: тест не должен
        # воспроизводить настоящую паузу, чтобы проверить порог.
        self._clock = time.monotonic
```

и новый метод сразу после `__init__`:

```python
    def event(self, event: QEvent) -> bool:  # noqa: N802
        """Событие дольше порога — в perf-лог, с именем типа.

        Локальный фильтр на одном виджете, а не `installEventFilter`
        на `QApplication`: глобальный вызывался бы на каждое событие мыши
        и таймера во всём приложении тысячи раз в секунду и на медленной
        машине сам стал бы частью измеряемого (спека 3.2.1, §6).

        Имя типа события содержимого пользователя не несёт — тот же
        порог допустимого, что у мест кадров в `_log_failure`.
        """  # noqa: RUF002
        if not self._perf:
            return super().event(event)
        started = self._clock()
        handled = super().event(event)
        # round(), не int(): усечение вниз даёт 429 мс вместо 430
        # (ошибка представления float, находка задачи 5).
        elapsed = round((self._clock() - started) * 1000)
        if elapsed >= _SLOW_EVENT_MS:
            _perf_log.info(
                "дерево баз: событие %s %d мс", QEvent.Type(event.type()).name, elapsed
            )
        return handled
```

Константу и логгер — на уровень модуля, рядом с прочими константами файла:

```python
# Порог «событие было долгим». Ниже него в логе окажется шум от обычной
# перерисовки; выше — потеряется то, ради чего замер и заведён.
_SLOW_EVENT_MS = 100
_perf_log = logging.getLogger("onecstarter.perf")
```

Импорты файла дополнить: `import logging`, `import time`, `from PySide6.QtCore import QEvent` (к существующей строке импорта из `QtCore`), `from onecstarter import perf`. `os` в файле уже импортирован.

- [ ] **Step 4: Запустить тесты раздела целиком**

Run: `uv run pytest tests/ui/test_bases_view.py -v`
Expected: все PASS. Особое внимание — существующим тестам drag-and-drop и `keyPressEvent`: они идут **без правок**, и это гейт того, что перехват `event` ничего не сломал.

- [ ] **Step 5: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/ui/bases/view.py tests/ui/test_bases_view.py
git commit -m "feat(perf): события дерева баз дольше 100 мс — в лог с именем типа

Раскрытие группы нашим кодом не обрабатывается вовсе, и без этой точки
оно осталось бы безымянной паузой heartbeat. Локальный фильтр на одном
виджете: глобальный eventFilter сам стал бы частью измеряемого."
```

---

### Task 7: Версия программы в логе старта

§7 спеки. Недочёт, вскрытый этой же сессией: версию на сервере пришлось определять косвенно — по тому, в каком запуске в логе впервые появились строки «доступность каталогов».

**Files:**
- Modify: `src/onecstarter/__main__.py` (в `main`, после `perf.setup`)
- Test: `tests/unit/test_entry_point.py`

**Interfaces:**
- Consumes: `about.app_version()` из `src/onecstarter/ui/about.py` — существующая функция, Qt не импортирует.
- Produces: строка `onecstarter: версия 3.2.1, процесс 64-бит` в `onecstarter.log`.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/unit/test_entry_point.py`:

```python
def test_main_logs_version_at_start(
    app_stub: _AppStub,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from onecstarter.ui import about

    # APPDATA подменяется обязательно: `main` настраивает лог настоящим
    # `diagnostics.setup_logging`, и без подмены тест писал бы в живой
    # `%APPDATA%\OneCStarter\logs` машины, где идёт прогон. Тот же приём,
    # что в test_main_catches_dispatch_failure_and_reports ниже.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    with caplog.at_level(logging.INFO, logger="onecstarter"):
        assert main([]) == 0

    assert f"версия {about.app_version()}" in caplog.text
    assert "процесс" in caplog.text
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `uv run pytest tests/unit/test_entry_point.py -k "logs_version" -v`
Expected: FAIL — строки в логе нет.

- [ ] **Step 3: Написать строку старта**

В `src/onecstarter/__main__.py`, в `main`, **внутри существующего `try`**, первой строкой перед `return _dispatch(arguments)`:

```python
    try:
        # Внутри try и локальным импортом намеренно: `ui/__init__.py` пуст,
        # а `ui/about.py` Qt не тянет, но если в битой сборке упадёт и он —
        # отказ поймает тот же обработчик, что ловит отказ импорта `ui`
        # (спека T-04.6 §4.2). Косвенно определять версию по косвенным
        # признакам лога нам уже пришлось однажды (спека 3.2.1, §7).
        from onecstarter.ui import about

        logging.getLogger("onecstarter").info(
            "версия %s, процесс %d-бит", about.app_version(), 64 if sys.maxsize > 2**32 else 32
        )
        return _dispatch(arguments)
```

Остальное тело `try`/`except` не меняется.

- [ ] **Step 4: Запустить тесты точки входа**

Run: `uv run pytest tests/unit/test_entry_point.py -v`
Expected: все PASS, существующие — без правок.

- [ ] **Step 5: Линт, типы, коммит**

```bash
uv run ruff check . && uv run mypy
git add src/onecstarter/__main__.py tests/unit/test_entry_point.py
git commit -m "feat(diag): версия и разрядность процесса — первой строкой лога старта

Версию на сервере заказчика пришлось определять косвенно, по тому,
в каком запуске в логе впервые появились строки новой вехи."
```

---

### Task 8: README, версия, полный прогон и сборка

Заключительная задача вехи: документация для заказчика, версия, все гейты и собранный экземпляр.

**Files:**
- Modify: `README.md:171-175` (раздел «Диагностика»)
- Modify: `pyproject.toml` (версия)
- Modify: `docs/tasks.md` (запись вехи и результаты мутационных проверок)

**Interfaces:**
- Consumes: всё из задач 1–7.
- Produces: `dist/OneCStarter-3.2.1-portable.zip` и `dist/OneCStarter-3.2.1-setup.exe`.

- [ ] **Step 1: Дописать раздел «Диагностика» в README**

Заменить раздел целиком:

````markdown
## Диагностика

Лог: `%APPDATA%\OneCStarter\logs\onecstarter.log`. Первая строка каждого
запуска — версия программы и разрядность процесса. Если приложение
не стартует — запустите `OneCStarterc.exe` (консольная сборка) и приложите
вывод к issue.

### Замеры производительности

Если программа работает медленно, включите perf-режим — он пишет
длительности операций в отдельный файл
`%APPDATA%\OneCStarter\logs\perf.log`:

```powershell
$env:ONECSTARTER_PERF = "1"
.\OneCStarter.exe
```

В лог попадают длительность скана процессов с их числом, пересборка списка
баз, паузы главного потока дольше 150 мс и события списка дольше 100 мс.
Ни путей к базам, ни имён баз, ни командных строк в этом файле нет —
только счётчики и миллисекунды, файл можно приложить к issue целиком.

Режим выключен по умолчанию; чтобы выключить его в текущем окне PowerShell,
уберите переменную: `Remove-Item Env:ONECSTARTER_PERF`.
````

- [ ] **Step 2: Поднять версию**

В `pyproject.toml` заменить `version = "3.2.0"` на `version = "3.2.1"`.

- [ ] **Step 3: Полный прогон тестов в файл**

Run: `uv run pytest > e:/tmp/v321-full.log 2>&1`
Expected: `passed`, ноль `failed`. Число тестов — не меньше 2658 плюс новые (ориентир: около 2680). При падении — смотреть файл целиком, не `tail`: в проекте есть интермиттентный access violation pytest-qt, и его блок теряется при обрезке.

- [ ] **Step 4: Линт и типы**

Run: `uv run ruff check . && uv run mypy`
Expected: `All checks passed!` и `Success: no issues found`.

- [ ] **Step 5: Сборка и smoke**

Run: `powershell -File build/build.ps1`
Expected: `smoke: OK`, в выводе smoke строка `smoke: version=3.2.1`, на выходе `dist/OneCStarter-3.2.1-setup.exe` и `dist/OneCStarter-3.2.1-portable.zip`.

- [ ] **Step 6: Проверить perf-режим на собранном экземпляре**

```powershell
$env:ONECSTARTER_PERF = "1"
.\dist\OneCStarter\OneCStarterc.exe
```

Expected: в консоли видны строки старта с версией; после закрытия окна
в `%APPDATA%\OneCStarter\logs\perf.log` есть строки `скан процессов (servers)`
с числом просмотренных процессов. Убедиться глазами, что **ни одного пути
и ни одного имени базы** в файле нет (инвариант 5).

Затем без переменной:

```powershell
Remove-Item Env:ONECSTARTER_PERF
.\dist\OneCStarter\OneCStarterc.exe
```

Expected: `perf.log` не пополняется ни одной новой строкой.

- [ ] **Step 7: Записать веху в docs/tasks.md**

Добавить раздел вехи по образцу соседних записей: состав задач, результаты
**обеих мутационных проверок** (задача 1 шаг 5, задача 3 шаг 5) с указанием,
какой тест упал и на каком утверждении, числа полного прогона, размеры
артефактов сборки. Отдельным пунктом — **открытый критерий §9 спеки**:
диагноз считается подтверждённым, только когда с сервера придёт лог, где
«обнаружение платформ: закончено за N мс» вернулось к десяткам миллисекунд.
До этого веха закрыта по коду, но не по результату.

- [ ] **Step 8: Коммит**

```bash
git add README.md pyproject.toml docs/tasks.md
git commit -m "docs: 3.2.1 — perf-режим в README, версия, запись вехи

Веха закрыта по коду. По результату — после лога с сервера: критерий
проверки диагноза в спеке, §9."
```

---

## Самопроверка плана

**Покрытие спеки.** §1 — не требует кода (улика). §2 — диагноз, проверяется задачей 8 шаг 6 и критерием §9. §3 — отрицательное требование, выполнено отсутствием задач на debounce и кэш значков. §4 → задача 1. §5 → задача 2. §6 → задачи 3, 4, 5, 6 (по строке таблицы на задачу). §7 → задача 7. §8 — отрицательное требование, выполнено. §9 → задача 8 шаг 7 (открытый пункт в `docs/tasks.md`). §10 → тесты в каждой задаче, мутации в задачах 1 и 3. §11 → смягчения разложены по задачам: `event()` при выключенном режиме (задача 6 шаг 3), heartbeat только под флагом (задача 5 шаг 3), раздельные `AccessDenied`/`NoSuchProcess` (задача 1 шаг 3), ротация 4 МБ × 3 (задача 2 шаг 3).

**Согласованность имён.** `perf.is_enabled` / `perf.enabled` / `perf.setup` / `perf.measure` / `perf.reset_for_tests` / `perf.ENV_NAME` / `perf.LOG_NAME` — определены в задаче 2, используются задачами 3–7 в том же написании. `PsutilScanner(label)` определён в задаче 1, метки проставлены в задаче 3. `_details_of` — задача 1, зовётся в задаче 3 в переписанном `snapshot`. `Heartbeat` / `maybe_start_heartbeat` — задача 5. `_SLOW_EVENT_MS` / `_perf_log` — задача 6.

**Порядок зависимостей.** Задача 1 ни от чего не зависит. Задача 2 ни от чего не зависит. Задачи 3–7 зависят от задачи 2; задача 3 — ещё и от задачи 1 (переписывает её `snapshot`). Задача 8 — от всех. Задачи 4, 5, 6, 7 независимы между собой и могут идти в любом порядке после задачи 2.
