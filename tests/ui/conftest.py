"""Оснастка UI-тестов: offscreen-платформа Qt до первого импорта PySide6."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import codecs
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from onecstarter.domain.launch import ClientConvention, ClientKind, LaunchCommand
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.services.catalog import read_common_lists
from onecstarter.services.workspace import Workspace, WorkspacePaths

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"

CONVENTIONS = [
    ClientConvention(
        min_version=parse_version("8.2"),
        bin_dir="bin",
        executables={
            ClientKind.THIN: "1cv8c.exe",
            ClientKind.THICK: "1cv8.exe",
            ClientKind.DESIGNER: "1cv8.exe",
        },
    )
]
INSTALLED = [
    Installation(parse_version("8.3.25.1633"), Path(r"C:\Program Files\1cv8\8.3.25.1633"), Arch.X64)
]


@pytest.fixture
def workspace_factory(tmp_path):
    def factory(installations=None, cfg_paths=()):
        calls: list[LaunchCommand] = []
        opened: list[str] = []
        ibases = tmp_path / "ibases.v8i"
        if not ibases.exists():
            shutil.copyfile(FIXTURE, ibases)

        def fake_spawn(command: LaunchCommand) -> int:
            calls.append(command)
            return 7

        def fake_open_url(url: str) -> bool:
            opened.append(url)
            return True

        workspace = Workspace(
            WorkspacePaths(
                ibases=ibases, user_data=tmp_path / "bases.json", cfg_paths=cfg_paths
            ),
            installations=INSTALLED if installations is None else installations,
            conventions=CONVENTIONS,
            cfg_rules=[],
            default_app=None,
            spawn=fake_spawn,
            open_url=fake_open_url,
            now=lambda: datetime.fromisoformat("2026-08-07T10:00:00+00:00"),
            new_id=lambda: "99999999-9999-9999-9999-999999999999",
        )
        # T-02 поставки (спека T-04.6, §3.3): конструктор больше не читает
        # общие списки сам, поэтому фабрика применяет снимок сразу и
        # безусловно — возвращает тесты UI в «загруженный» мир, каким он был
        # до разделения чтения и применения. Тестам конкретно pending-состояния
        # общих списков эта фабрика не подходит — им нужен Workspace
        # без последующего apply_common_lists.
        workspace.apply_common_lists(read_common_lists(list(cfg_paths)))
        return workspace, calls, opened

    return factory


# -- общий список (CommonInfoBases) — задачи 12 (круг правок 1) и 14 --------
#
# Тот же приём, что и `_with_common_list` в tests/unit/test_workspace.py:
# `1cestart.cfg` в UTF-16LE с BOM — так его пишет платформа. Синтетический  # noqa: RUF003
# `.v8i` собирается на лету в `tmp_path`, ничего не попадает
# в `tests/fixtures/` и в репозиторий — обезличивать нечего, содержимое
# выдумано для теста с самого начала.  # noqa: RUF003

COMMON_GROUP_NAME = "Общая группа"
COMMON_GROUP_KEY = "id:aaaa"
COMMON_BASE_NAME = "Общая база"
COMMON_BASE_KEY = "id:bbbb"


def _with_common_list(tmp_path: Path, common: Path) -> tuple[Path, ...]:
    cfg = tmp_path / "1cestart.cfg"
    cfg.write_bytes(codecs.BOM_UTF16_LE + f"CommonInfoBases={common}\r\n".encode("utf-16-le"))
    return (cfg,)


@pytest.fixture
def common_group_cfg_paths(tmp_path):
    """`cfg_paths` с общим списком, несущим одну группу без содержимого.

    Источник только для чтения (дизайн плана 3, §3 и §5) — используется
    там, где нужно доказать, что UI не путает группу общего списка
    с пользовательской (круг правок 1 ревью задачи 12: «Создать группу…»/
    «Переименовать группу…»/«Удалить группу…» не должны вести пользователя
    в тупик или к вводящему в заблуждение сообщению).
    """  # noqa: RUF002
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        f"[{COMMON_GROUP_NAME}]\r\nID=aaaa\r\nOrderInList=-1\r\nFolder=/\r\n".encode()
    )
    return _with_common_list(tmp_path, shared)


@pytest.fixture
def common_base_cfg_paths(tmp_path):
    """`cfg_paths` с общим списком, несущим одну запись базы (не группу).

    Задача 14: перетаскивание записи из общего списка обязано отказать
    через `Workspace._reject_common`, который читает внутренний `_items`,
    а не результат `items()`. Заводить эту запись через
    `mock.patch.object(workspace, "items", ...)` (как подмену для группы
    из общего списка выше) означало бы подделать только витрину — `_find`
    внутри `_reject_common` такую запись всё равно не нашёл бы, и отказ
    пришёл бы не тем: `TargetGoneError` вместо `ReadOnlySourceError`.
    Настоящий общий список — единственный способ провести запись через
    реальную загрузку (`read_common_lists` + `common_items_from_data`),
    как это происходит в файле.
    """  # noqa: RUF002
    shared = tmp_path / "shared_base.v8i"
    shared.write_bytes(
        (
            f'[{COMMON_BASE_NAME}]\r\nID=bbbb\r\nConnect=Srvr="s";Ref="r";\r\n'
            "OrderInList=-1\r\nFolder=/\r\n"
        ).encode()
    )
    return _with_common_list(tmp_path, shared)


@pytest.fixture
def broken_common_cfg_paths(tmp_path):
    """`cfg_paths` с общим списком, путь к которому не читается.

    Задача 14, круг правок 1: даёт `RowKind.NOTE` — строку ошибки чтения
    общего списка (`CommonListError`, `display_forest`) внутри ветки «Общие
    списки». Файл-«общий список» намеренно не создаётся: `read_common_lists`
    ловит `OSError` при чтении и превращает её в такую строку — тот же
    путь, каким платформа сталкивается с недоступным общим списком.
    """  # noqa: RUF002
    missing = tmp_path / "missing.v8i"
    return _with_common_list(tmp_path, missing)
