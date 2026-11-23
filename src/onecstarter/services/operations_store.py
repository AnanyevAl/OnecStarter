"""Сценарии и история пакетных операций — %APPDATA%\\OneCStarter\\operations.json (спека v4, §5.3).

Файл наш. В нём только пользовательские сценарии (вместе с сохранёнными списками баз) и
история последних запусков; заготовки — константы `domain/operations.py`. Паролей здесь
нет по построению: ни в сценарии, ни в записи истории нет поля, куда они могли бы попасть
(командная строка в историю не пишется).

Политика повреждённого файла отличается от `param_sets.py`: здесь в одном файле лежат
невосполнимые сценарии и одноразовая история, и одна испорченная запись истории не должна
стоить пользователю сценариев. Поэтому:
- `schema` больше нашей — файл создан более новой версией программы: `OperationsUnavailableError`,
  файл не переносится и не меняется (иначе первое же сохранение затёрло бы чужие данные);
- сценарии не разобрались (или иная схема, не JSON) — весь файл в `.bad`, данные пусты;
- сценарии целы, история нет — сценарии возвращаются, история пуста, файл копируется
  в `.bad` (копия: живой файл остаётся, сбой копирования — только строка в лог);
- нечитаемый файл — `OperationsUnavailableError`.
В лог попадают только имена файлов.
"""  # noqa: RUF002

import json
import logging
import shutil
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from onecstarter.config.atomic import atomic_write
from onecstarter.domain.operations import (
    BUILTIN_SCENARIOS,
    BaseOutcome,
    BaseRef,
    BaseResult,
    RunRecord,
    Scenario,
    Step,
    StepResult,
    StepStatus,
)
from onecstarter.services.errors import InvalidRequestError, OperationsUnavailableError

__all__ = [
    "HISTORY_LIMIT",
    "SCHEMA_VERSION",
    "OperationsData",
    "add_run",
    "all_scenarios",
    "copy_of",
    "load_operations",
    "prune_logs",
    "remove_scenario",
    "save_operations",
    "upsert_scenario",
]

SCHEMA_VERSION = 1
HISTORY_LIMIT = 50
_BUILTIN_PREFIX = "builtin:"

_log = logging.getLogger("onecstarter.operations_store")


@dataclass(frozen=True)
class OperationsData:
    scenarios: tuple[Scenario, ...] = ()
    history: tuple[RunRecord, ...] = ()


_DECODE_ERRORS = (ValueError, KeyError, TypeError, OverflowError, RecursionError, AttributeError)


def load_operations(path: Path) -> OperationsData:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return OperationsData()
    except UnicodeDecodeError:
        return _move_aside(path)
    except OSError as error:
        raise OperationsUnavailableError(f"{path} недоступен для чтения") from error
    try:
        payload = json.loads(raw)
    except _DECODE_ERRORS:
        return _move_aside(path)
    if not isinstance(payload, dict):
        return _move_aside(path)
    schema = payload.get("schema")
    if isinstance(schema, int) and not isinstance(schema, bool) and schema > SCHEMA_VERSION:
        raise OperationsUnavailableError(
            f"{path.name} создан более новой версией программы и не будет изменён"
        )
    if schema != SCHEMA_VERSION or isinstance(schema, bool):
        return _move_aside(path)
    entries = payload.get("scenarios")
    if not isinstance(entries, list):
        return _move_aside(path)
    try:
        scenarios = tuple(_scenario(entry) for entry in entries)
    except _DECODE_ERRORS:
        return _move_aside(path)
    history: tuple[RunRecord, ...] = ()
    raw_history = payload.get("history")
    if raw_history is not None:
        try:
            if not isinstance(raw_history, list):
                raise ValueError("history не список")
            history = tuple(_record(entry) for entry in raw_history)
        except _DECODE_ERRORS:
            _copy_aside(path)
    return OperationsData(scenarios, history)


def save_operations(path: Path, data: OperationsData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "scenarios": [_encode_scenario(s) for s in data.scenarios if not s.builtin],
        "history": [_encode_record(record) for record in data.history],
    }
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def all_scenarios(data: OperationsData) -> tuple[Scenario, ...]:
    return (*BUILTIN_SCENARIOS, *data.scenarios)


def upsert_scenario(data: OperationsData, scenario: Scenario) -> OperationsData:
    """Заменить сценарий с тем же `id` или дописать в конец. Заготовки не меняются."""  # noqa: RUF002
    if scenario.builtin or scenario.id.startswith(_BUILTIN_PREFIX):
        raise InvalidRequestError("Заготовку изменить нельзя — сделайте копию")
    if not scenario.id:
        raise InvalidRequestError("У сценария нет идентификатора")  # noqa: RUF001
    if not scenario.name.strip():
        raise InvalidRequestError("Не задано имя сценария")  # noqa: RUF001
    if any(current.id == scenario.id for current in data.scenarios):
        updated = tuple(scenario if c.id == scenario.id else c for c in data.scenarios)
    else:
        updated = (*data.scenarios, scenario)
    return replace(data, scenarios=updated)


def remove_scenario(data: OperationsData, scenario_id: str) -> OperationsData:
    if scenario_id.startswith(_BUILTIN_PREFIX):
        raise InvalidRequestError("Заготовку удалить нельзя")
    return replace(data, scenarios=tuple(s for s in data.scenarios if s.id != scenario_id))


def copy_of(scenario: Scenario, new_id: str, existing_names: Collection[str]) -> Scenario:
    """Копия сценария (в том числе заготовки) — свой, с незанятым именем."""  # noqa: RUF002
    taken = {name.strip().casefold() for name in existing_names}
    name = f"{scenario.name} — копия"
    number = 2
    while name.casefold() in taken:
        name = f"{scenario.name} — копия {number}"
        number += 1
    return replace(scenario, id=new_id, name=name, builtin=False)


def add_run(data: OperationsData, record: RunRecord) -> tuple[OperationsData, tuple[str, ...]]:
    """Дописать запуск в историю; вернуть каталоги журналов выпавших записей.

    Каталог, на который ещё ссылается оставшаяся запись, не возвращается: файл правится
    руками, и два запуска могут указывать на один каталог. Повторов нет, порядок сохранён.
    """
    history = (*data.history, record)
    dropped = history[:-HISTORY_LIMIT] if len(history) > HISTORY_LIMIT else ()
    kept = history[-HISTORY_LIMIT:]
    in_use = {old.logs_dir for old in kept}
    result: list[str] = []
    for old in dropped:
        if old.logs_dir not in in_use and old.logs_dir not in result:
            result.append(old.logs_dir)
    return replace(data, history=kept), tuple(result)


def prune_logs(
    dirs: Sequence[str], logs_root: Path, rmtree: Callable[[str], None] = shutil.rmtree
) -> None:
    """Удалить каталоги журналов — только прямых детей `logs_root`; остальное пропустить.

    Пути приходят из редактируемого файла, поэтому проверка чисто текстовая (диск не
    трогается, ссылки не раскрываются): путь абсолютный, без `..`, его родитель — сам
    корень (без учёта регистра), имя не пусто, не кончается точкой или пробелом и не
    несёт запрещённых в имени символов. Win32 молча отбрасывает завершающие точки и
    пробелы: `C:\\ops\\...` и `C:\\ops\\. ` для него — сам `C:\\ops`, и `rmtree` удалил бы
    весь каталог журналов. Наши каталоги запусков — всегда прямые дети каталога
    операций, их имена проходят `sanitize_component`. Отказ удаления — строка в лог
    программы, не ошибка (спека §5.3); в лог пути не попадают.
    """  # noqa: RUF002
    root = PureWindowsPath(str(logs_root))
    for directory in dirs:
        if not _child_of(PureWindowsPath(directory), root):
            _log.warning("каталог журналов вне каталога операций — не удалён")
            continue
        try:
            rmtree(directory)
        except (OSError, ValueError) as error:
            _log.warning("каталог журналов операции не удалён: %s", type(error).__name__)


_BAD_NAME_CHARS = frozenset('<>:"/\\|?*')


def _child_of(path: PureWindowsPath, root: PureWindowsPath) -> bool:
    name = path.name
    return (
        path.is_absolute()
        and ".." not in path.parts
        and path.parent == root
        and bool(name)
        and not name.endswith((".", " "))
        and not any(char in _BAD_NAME_CHARS or ord(char) < 0x20 for char in name)
    )


def _encode_scenario(scenario: Scenario) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "stop_on_error": scenario.stop_on_error,
        "bases": (
            None
            if scenario.bases is None
            else [{"key": ref.key, "name": ref.name} for ref in scenario.bases]
        ),
        "steps": [
            {
                "command": step.command,
                "values": list(step.values),
                "overwrite": step.overwrite,
                "create_dirs": step.create_dirs,
            }
            for step in scenario.steps
        ],
    }


def _scenario(value: Any) -> Scenario:
    if not isinstance(value, dict):
        raise ValueError("сценарий не объект")
    bases = value.get("bases")
    return Scenario(
        id=str(value["id"]),
        name=str(value["name"]),
        steps=tuple(_step(step) for step in value["steps"]),
        stop_on_error=bool(value.get("stop_on_error", True)),
        bases=(
            None
            if bases is None
            else tuple(BaseRef(str(ref["key"]), str(ref["name"])) for ref in bases)
        ),
    )


def _step(value: Any) -> Step:
    if not isinstance(value, dict):
        raise ValueError("шаг не объект")
    return Step(
        command=str(value["command"]),
        values=tuple(None if item is None else str(item) for item in value.get("values", [])),
        overwrite=bool(value.get("overwrite", False)),
        create_dirs=bool(value.get("create_dirs", True)),
    )


def _encode_record(record: RunRecord) -> dict[str, Any]:
    return {
        "scenario_id": record.scenario_id,
        "scenario_name": record.scenario_name,
        "started": record.started.isoformat(timespec="seconds"),
        "logs_dir": record.logs_dir,
        "bases": [
            {
                "key": base.key,
                "name": base.name,
                "outcome": base.outcome.value,
                "problems": list(base.problems),
                "logs_dir": base.logs_dir,
                "steps": [
                    {
                        "command": step.command,
                        "status": step.status.value,
                        "code": step.code,
                        "seconds": step.seconds,
                        "message": step.message,
                    }
                    for step in base.steps
                ],
            }
            for base in record.bases
        ],
    }


def _record(value: Any) -> RunRecord:
    if not isinstance(value, dict):
        raise ValueError("запись истории не объект")
    return RunRecord(
        scenario_id=str(value["scenario_id"]),
        scenario_name=str(value["scenario_name"]),
        started=datetime.fromisoformat(str(value["started"])),
        logs_dir=str(value["logs_dir"]),
        bases=tuple(
            BaseResult(
                key=str(base["key"]),
                name=str(base["name"]),
                outcome=BaseOutcome(str(base["outcome"])),
                steps=tuple(
                    StepResult(
                        command=str(step["command"]),
                        status=StepStatus(str(step["status"])),
                        code=None if step.get("code") is None else int(step["code"]),
                        seconds=float(step.get("seconds", 0.0)),
                        message=str(step.get("message", "")),
                    )
                    for step in base.get("steps", [])
                ),
                problems=tuple(str(problem) for problem in base.get("problems", [])),
                logs_dir=str(base.get("logs_dir", "")),
            )
            for base in value["bases"]
        ),
    )


def _move_aside(path: Path) -> OperationsData:
    """Перенести повреждённый файл в `.bad`; в лог — только имена файлов."""
    bad = path.with_name(path.name + ".bad")
    try:
        path.replace(bad)
    except OSError as error:
        raise OperationsUnavailableError(
            f"{path} повреждён, но его не удалось перенести в .bad"  # noqa: RUF001
        ) from error
    _log.warning("%s повреждён и перенесён в %s, сценарии и история пусты", path.name, bad.name)
    return OperationsData()


def _copy_aside(path: Path) -> None:
    """Скопировать файл с испорченной историей в `.bad`; сбой — предупреждение."""  # noqa: RUF002
    bad = path.with_name(path.name + ".bad")
    try:
        shutil.copyfile(path, bad)
    except OSError:
        _log.warning("%s: история повреждена, копия в %s не создана", path.name, bad.name)
        return
    _log.warning("%s: история повреждена, копия в %s, история пуста", path.name, bad.name)
