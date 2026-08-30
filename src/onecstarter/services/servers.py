"""Координатор раздела «Серверы»: профили, снимок процессов, статусы.

Задача T-08.10 закрыла CRUD-контур над `servers.json`. Эта задача (T-08.11)
добавляет чтение живых процессов: снимок ragent/rmngr (`scan_servers`,
зовётся из фонового потока UI — чистая функция поверх `ProcessScanner`),
его применение (`apply_scan`, главный поток — сопоставляет процессы
с профилями через `match_profiles`) и производные от снимка вопросы:
`statuses` (что запущено, какая версия разрешилась, не разъехался ли
каталог кластера с версией) и `foreign_servers` (чужие ragent — [Ф] В1).
Эта задача (T-08.12) добавляет сами эффекты запуска и остановки: `start`
(§6.4 — второй ragent на каталоге кластера, уже занятом совпавшим процессом
последнего снимка, не запускается нами никогда) и `stop`. Эта задача (T-08.13)
добавляет смену версии консоли администрирования: `current_console_version`
(чтение — версия из пути зарегистрированной `radmin.dll`, без UAC),
`register_console` (эффект — `run_elevated("regsvr32", ...)`, §7: отказ
пользователя в UAC-диалоге — штатный исход, транслируется в
`ConsoleRegistrationDeclinedError`, а не в ошибку) и `open_console`
(`open_file` на путь `.msc`). §7: регистрация зовётся ТОЛЬКО из явного
действия UI — ни конструктор, ни `apply_scan`, ни `statuses` её не трогают
(см. `_registered_radmin`/`_run_elevated`/`_open_file` — только сохранены
в конструкторе, эффекты живут в методах этой задачи).

T-10 (задача 4) перевела запуск на дочерний жизненный цикл: спека §12,
пересмотр решения 26.08.2026 — исходная редакция «отвязанный процесс,
переживает закрытие» ДЕЙСТВОВАЛА в T-08 и БОЛЬШЕ НЕ действует. `start`
порождает сервер через `server_spawn` (инъекция) — закрытие OneCStarter
(или его крах) гасит дерево серверов вместе с лаунчером ([Ф] Б1/Б2 T-09).
Второй эффект той задачи — журнал профиля (`services/server_journal.py`):
`start` ротирует прошлый запуск (BEST-EFFORT — правка финального ревью
ветки T-10, п.1: `Path.replace` внутри `rotate_journal` падает
`PermissionError [WinError 32]`, если журнал ещё держит открытым процесс
прошлого запуска — `dbgs`/`rmngr`, переживший `ragent`, снятый из
Диспетчера задач без штатной остановки; Python `open()` не даёт
`FILE_SHARE_DELETE`. Отказ ротации пишет событие в журнал и НЕ прерывает
запуск — записи просто продолжаются в тот же файл; полноценное решение,
открытие с явным `FILE_SHARE_DELETE`, — долг вехи, см. `docs/tasks.md`),
пишет событие `запуск: …` до порождения процесса и `порождён PID …` после
успешного `server_spawn`; `stop` — событие успеха или `отказ остановки: …`
перед отказом; `log_event` — точка входа для событий снаружи координатора
(UI, исход §8). `logs_dir` — обязательный параметр конструктора, каталог
журналов профилей (`%APPDATA%\\OneCStarter\\logs\\servers`, спека §12.6,
собирается в `app.py`).

T-12 (задача 3) меняет саму модель владения процессами: истина о НАШЕМ
сервере — не снимок и не сопоставление по командной строке, а Windows Job
Object НА КАЖДЫЙ ЗАПУСК ПРОФИЛЯ (спека T-12 §3, `platform_1c/job.py`).
Координатор получает `job_factory` (инъекция, `Callable[[], Job]`) и держит
по одному живому Job на профиль (`_jobs`) плюс PID порождённого нами
`ragent` (`_spawned`): `start` заводит новый Job и отдаёт его
`server_spawn` (`Callable[[LaunchCommand, Path, Job], int]`), `stop` — это
`job.close()`, и всё дерево гасит сама ОС по kill-on-close ([Ф] Б2 T-09 на
живом дереве `ragent`, [Ф] 29.08.2026 на остатках). `running_count`
и `log_shutdown` спрашивают Job, а не снимок, — этим закрыт долг T-10
«вопрос о выходе считает чужие процессы».

Отсюда три следствия, каждое — решение заказчика 29.08.2026.
Первое (решение 4): ЧУЖИМ процессом мы не управляем никогда — совпавший
по каталогу кластера `ragent`, запущенный не лаунчером, виден на карточке,
но `stop` для него честно отказывает: Job у профиля нет и взяться ему
неоткуда. Второе (решения 2 и 3): остатки НАШЕГО прошлого дерева (`ragent`
снят извне, дети живы в Job) гасит сам `start` — закрывает старый Job ДО
порождения нового; удаление работающего профиля сначала останавливает его.
Третье (спека T-12 §4): чужие держатели портов профиля
(`domain/server_match.py::port_holders`, [Ф] А3 T-07 — `rmngr` переживает
`ragent` и держит его `regport`) — вопрос диагностики, а не «сироты,
которые мы гасим»: `start` на них отказывает ДО ротации журнала и spawn,
а действия «погасить чужое» больше нет вовсе. Вместе с этим ушли модуль
остановки по PID (`TerminateProcess` со сверкой `create_time`, `platform_1c`,
T-08), гонка PID §6.2 и её собственный класс ошибки остановки
(`errors.py`): гасит теперь ОС, а сверять PID со снимком незачем —
Job отвечает об одном и том же дереве.

Приём инъекции эффектов и отката состояния в памяти при отказе записи —
тот же, что в `services/workspace.py::Workspace` (см. её докстринг
и `_store_user`): экран, построенный по `profiles()`, обязан показывать
то же, что реально лежит в файле, а не то, что мы хотели туда записать.
Приём разделения снимка на «применить» (главный поток, чистое) и «прочитать»
(фон, эффект) — тот же, что `Workspace.apply_common_lists`/`common_lists_pending`
(докстринг `workspace.py`): до первого `apply_scan` снимка нет вовсе,
и `scan_pending` отличает это состояние от «серверов действительно нет».
"""  # noqa: RUF002

import logging
import os
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PureWindowsPath

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import (
    ServerConvention,
    ServerProfile,
    build_ragent_arguments,
    resolve_server_version,
    validate_profile,
)
from onecstarter.domain.server_match import (
    ForeignServer,
    MatchResult,
    RagentProcess,
    match_profiles,
    normalize_cluster_dir,
    port_holders,
    port_holders_text,
    version_from_exe_path,
)
from onecstarter.domain.version import VersionNumber
from onecstarter.platform_1c import console, elevation
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.platform_1c.job import Job, JobError
from onecstarter.platform_1c.process_scan import ProcessInfo, ProcessScanner
from onecstarter.platform_1c.server_discovery import ServerInstallation, console_path
from onecstarter.services import server_journal
from onecstarter.services.errors import (
    ConsoleRegistrationDeclinedError,
    ConsoleRegistrationError,
    ServerError,
    UnknownItemError,
)
from onecstarter.services.server_store import load_profiles, save_profiles

# services не пишет в stdout/stderr напрямую (тот же довод, что и у остальных  # noqa: RUF003
# "тихих" отказов слоя) — единственное, что может отказать без права
# прервать вызывающего, это запись события в журнал (`log_event`, T-10):
# антивирус, полный диск, отвалившийся роуминг-профиль. Такой отказ уходит
# в этот логгер, а не наружу, — см. `log_event`.  # noqa: RUF003
_log = logging.getLogger("onecstarter.servers")

__all__ = [
    "SCAN_NAMES",
    "ScanSnapshot",
    "ServerStatus",
    "ServersWorkspace",
    "scan_servers",
]

# rmngr нужен для поиска ЧУЖИХ держателей портов ([Ф] А3, t07-protocol.md):  # noqa: RUF003
# переживший своего ragent rmngr держит его regport, и новый ragent поверх  # noqa: RUF003
# такого держателя поднимается полумёртвым (спека T-12 §4). rphost и dbda
# сканировать незачем — они запускаются без -d (нет каталога кластера для
# сопоставления с профилем), и для статуса «запущен/остановлен» профиля  # noqa: RUF003
# не нужны ([Ф] Б1, t07-protocol.md).
SCAN_NAMES: frozenset[str] = frozenset({"ragent.exe", "rmngr.exe"})

# Спека §3.2: каталог кластера мог быть заведён руками под другую версию —
# эвристика ищет в имени листового каталога число вида версии 1С (3-4  # noqa: RUF003
# компонента, как в «8.3.25» или «8.3.25.1633») и сверяет его с фактически  # noqa: RUF003
# разрешённой версией профиля. Предупреждение, не блокер запуска.
_VERSION_IN_DIR_RE = re.compile(r"\d+(?:\.\d+){2,3}")


@dataclass(frozen=True)
class ScanSnapshot:
    """Сырой снимок процессов серверов 1С, разложенный по имени.

    Результат `scan_servers` — эффект (чтение живых процессов), сама эта
    структура данных чистая: конверсию в доменные типы и сопоставление
    с профилями делает `ServersWorkspace.apply_scan` в главном потоке.
    """  # noqa: RUF002

    agents: tuple[ProcessInfo, ...]
    managers: tuple[ProcessInfo, ...]


def _snapshot_agents(snapshot: ScanSnapshot) -> tuple[RagentProcess, ...]:
    """Сырые `ProcessInfo` снимка → `RagentProcess` для `match_profiles`.

    Общий шаг `apply_scan` и `ServersWorkspace._save` (IMPORTANT 6,
    финальное ревью ветки): конверсия чистая (без эффектов), поэтому
    её безопасно звать и из применения нового снимка, и из пересопоставления
    УЖЕ имеющегося снимка после правки списка профилей.
    """
    return tuple(
        RagentProcess(
            pid=info.pid,
            executable=info.executable,
            argv=info.argv,
            create_time=info.create_time,
        )
        for info in snapshot.agents
    )


def _snapshot_processes(snapshot: ScanSnapshot) -> tuple[RagentProcess, ...]:
    """Все процессы снимка (ragent и rmngr) как `RagentProcess` — вход `port_holders`."""  # noqa: RUF002
    return tuple(
        RagentProcess(
            pid=info.pid, executable=info.executable, argv=info.argv, create_time=info.create_time
        )
        for info in (*snapshot.agents, *snapshot.managers)
    )


def scan_servers(scanner: ProcessScanner) -> ScanSnapshot:
    """Один снимок ragent/rmngr, разложенный по `name.casefold()`.

    Модульная функция, а не метод: зовётся из фонового потока UI (эффект,
    сеть недопустима из конструктора и из главного потока — тот же довод,
    что у `apply_common_lists` в `workspace.py`), а её результат передаётся
    в `ServersWorkspace.apply_scan` уже из главного потока.
    """  # noqa: RUF002
    processes = scanner.snapshot(SCAN_NAMES)
    agents = tuple(p for p in processes if p.name.casefold() == "ragent.exe")
    managers = tuple(p for p in processes if p.name.casefold() == "rmngr.exe")
    return ScanSnapshot(agents=agents, managers=managers)


@dataclass(frozen=True)
class ServerStatus:
    """Всё, что раздел «Серверы» показывает по одному профилю.

    `resolved` — версия, разрешённая по маске/точному номеру профиля против
    установленных платформ (`resolve_server_version`); `None`, если версии
    ещё нет или маска не разбирается.

    Дальше — два независимых источника, и путать их нельзя (T-12 §3).
    `processes` — совпавшие по каталогу кластера `ragent` ПОСЛЕДНЕГО СНИМКА:
    и наши, и чужие, потому что по командной строке они неразличимы.
    `job_pids` — всё дерево НАШЕГО Job этого профиля (`()`, если Job нет или
    он пуст), `spawned_pid` — PID `ragent`, порождённого нами (`None`, если
    запускали не мы либо `ragent` завершился извне). Только эти два поля
    говорят, чем мы вправе управлять: непустой `job_pids` без `spawned_pid`
    внутри — остатки нашего прошлого дерева.

    `port_holders` — чужие процессы снимка, держащие порты профиля
    (`domain/server_match.py`, спека T-12 §4); пусто, пока снимка не было
    и пока у профиля есть совпавший `ragent` (живой `ragent` на нашем
    каталоге уже описан состоянием карточки, красная строка была бы шумом).
    `dir_mismatch` — эвристика спеки §3.2: каталог кластера похож на
    заведённый под другую версию.
    """  # noqa: RUF002

    profile: ServerProfile
    resolved: VersionNumber | None
    processes: tuple[RagentProcess, ...]
    job_pids: tuple[int, ...]
    spawned_pid: int | None
    port_holders: tuple[RagentProcess, ...]
    dir_mismatch: bool


def _dir_mismatch(cluster_dir: str, resolved: VersionNumber | None) -> bool:
    if resolved is None:
        return False
    leaf = PureWindowsPath(cluster_dir).name
    match = _VERSION_IN_DIR_RE.search(leaf)
    if match is None:
        return False
    return match.group() != str(resolved)


class ServersWorkspace:
    """Координатор: список профилей серверов и их хранение в `servers.json`.

    Конструктор вызывает `load_profiles` и может подняться с
    `ServersUnavailableError` (наследник `ServerError`), если файл профилей
    существует, но недоступен для чтения либо испорченный файл не удалось
    перенести в `.bad`. Исключение не гасится и обязано дойти до вызывающего —
    молча подменять его пустым списком нельзя: первое же сохранение затёрло бы
    настроенные профили без следа (докстринг `server_store.py`).
    """  # noqa: RUF002

    def __init__(
        self,
        store_path: Path,
        *,
        job_factory: Callable[[], Job],
        server_spawn: Callable[[LaunchCommand, Path, Job], int],
        logs_dir: Path,
        run_elevated: Callable[[str, str], int] = elevation.run_elevated,
        open_file: Callable[[str], None] = os.startfile,
        registered_radmin: Callable[[], Path | None] = console.registered_radmin_path,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self.store_path = store_path
        # Эффекты (сканы, остановка, запуск, регистрация консоли) — только
        # сохранены здесь; конструктор их не вызывает. `_run_elevated`
        # зовётся только из `register_console` — по явному действию UI,
        # никогда отсюда, из `apply_scan` или `statuses` (§7, докстринг
        # модуля). `job_factory`/`server_spawn`/`logs_dir` обязательные
        # и без дефолта (T-12, задача 3): какой Job настоящий, решает
        # проводка `app.py` (`ServerJob` в проде, `NullJob` в самопроверке),
        # а не слой services — здесь Job виден только контрактом `Job`.  # noqa: RUF003
        self._job_factory = job_factory
        self._server_spawn = server_spawn
        self._logs_dir = logs_dir
        self._run_elevated = run_elevated
        self._open_file = open_file
        self._registered_radmin = registered_radmin
        self._new_id = new_id
        self._now = now
        self._profiles: list[ServerProfile] = load_profiles(store_path)
        # Снимок процессов (спека T-08.11): конструктор его не читает — сеть/  # noqa: RUF003
        # процессы недопустимы до показа окна (тот же довод, что у  # noqa: RUF003
        # `Workspace._common_data`). До первого apply_scan оба поля `None`,  # noqa: RUF003
        # и это состояние отличается от «снимок применён, но пуст» —
        # см. `scan_pending`.
        self._snapshot: ScanSnapshot | None = None
        self._match: MatchResult | None = None
        # T-12: один живой Job на профиль плюс PID порождённого нами
        # `ragent`. Оба словаря — ЕДИНСТВЕННЫЙ источник истины о том, чем  # noqa: RUF003
        # мы вправе управлять (докстринг модуля); снимок процессов в этот
        # вопрос не входит. Ключ обоих — `profile.id`; профиля может уже
        # не быть в `_profiles` (удалён), поэтому `remove_profile`
        # обязана освободить Job сама, не надеясь на сборщик мусора.
        self._jobs: dict[str, Job] = {}
        self._spawned: dict[str, int] = {}

    def profiles(self) -> list[ServerProfile]:
        return list(self._profiles)

    def add_profile(self, profile: ServerProfile) -> None:
        """Добавить профиль. Пустой `id` — подставляется `new_id()`.

        Непустой `id`, совпавший с уже существующим профилем, — ошибка:
        `add_profile` создаёт новую запись, а не правит существующую
        (для этого `update_profile`).
        """  # noqa: RUF002
        if profile.id == "":
            profile = replace(profile, id=self._new_id())
        elif any(existing.id == profile.id for existing in self._profiles):
            raise ServerError(f"Профиль с id «{profile.id}» уже существует")  # noqa: RUF001
        # Новый профиль ещё не в self._profiles — others это весь текущий
        # список, фильтровать по id не нужно.
        self._validate(profile, self._profiles)
        self._save([*self._profiles, profile])

    def update_profile(self, profile: ServerProfile) -> None:
        """Заменить профиль с тем же `id`. Неизвестный `id` — ошибка."""  # noqa: RUF002
        if not any(existing.id == profile.id for existing in self._profiles):
            raise ServerError(f"Профиля с id «{profile.id}» нет в списке")  # noqa: RUF001
        others = [existing for existing in self._profiles if existing.id != profile.id]
        self._validate(profile, others)
        updated = [
            profile if existing.id == profile.id else existing for existing in self._profiles
        ]
        self._save(updated)

    def remove_profile(self, profile_id: str) -> None:
        """Удалить профиль по `id`, сначала остановив его сервер. Неизвестный `id` — ошибка.

        Решение заказчика 3 (29.08.2026): удаление РАБОТАЮЩЕГО профиля —
        это и остановка тоже. Раньше (T-08, решение 8) профиль просто
        пропадал из списка, а его `ragent` оставался жить — и увидеть его
        было уже негде, кроме как в «Других серверах на машине». С Job
        такого выбора нет вовсе: хендл принадлежал профилю, и, если бы мы
        просто забыли о нём, дерево пережило бы удаление только до выхода
        лаунчера (kill-on-close), то есть умерло бы всё равно, но без
        единой строки в журнале.

        Поэтому непустой Job останавливается через `stop` (события журнала
        и `ServerError` — его; отказ закрытия НЕ удаляет профиль: он
        остаётся в списке вместе со своим Job, и пользователю есть что
        повторить). Пустой Job — тихо освобождается: закрывать хендл, за
        которым уже никого нет, незачем сообщать.
        """  # noqa: RUF002
        if not any(existing.id == profile_id for existing in self._profiles):
            raise ServerError(f"Профиля с id «{profile_id}» нет в списке")  # noqa: RUF001
        if self._job_pids(profile_id):
            self.stop(profile_id)
        else:
            self._forget_job(profile_id)
        updated = [existing for existing in self._profiles if existing.id != profile_id]
        self._save(updated)

    def apply_scan(self, snapshot: ScanSnapshot) -> None:
        """Положить снимок процессов и сопоставить его с профилями.

        Главный поток — тот же приём разделения, что `scan_servers`/этот
        метод и `Workspace.apply_common_lists`: чтение живых процессов
        (эффект) уже случилось в `scan_servers`, здесь только конверсия
        `ProcessInfo` → `RagentProcess` и чистое сопоставление через
        `match_profiles`. Результат и сырые `managers` из снимка остаются
        в состоянии до следующего `apply_scan`.
        """  # noqa: RUF002
        self._snapshot = snapshot
        self._match = match_profiles(self._profiles, _snapshot_agents(snapshot))

    @property
    def scan_pending(self) -> bool:
        """`True`, пока снимок процессов ни разу не применялся.

        Тот же приём, что `Workspace.common_lists_pending` (докстринг
        `workspace.py`): «снимка ещё не было» и «снимок применён, и живых
        серверов в нём нет» — разные состояния. Без этого различия экран
        до первого скана показал бы все профили остановленными, хотя
        на самом деле мы их просто ещё не проверяли.
        """
        return self._snapshot is None

    def statuses(self, installed: Sequence[VersionNumber]) -> list[ServerStatus]:
        """Статус каждого профиля: версия, процессы снимка, наш Job, держатели портов.

        До первого `apply_scan` — `processes=()` и `port_holders=()` у всех
        профилей (см. `scan_pending`); `job_pids`/`spawned_pid` от снимка
        не зависят вовсе (T-12: наш Job знает о себе сам, снимка не ждёт),
        `resolved`/`dir_mismatch` — тоже, они считаются всегда.
        """  # noqa: RUF002
        result: list[ServerStatus] = []
        for profile in self._profiles:
            resolved = resolve_server_version(profile.version, installed)
            processes = self._matched_processes(profile)
            result.append(
                ServerStatus(
                    profile=profile,
                    resolved=resolved,
                    processes=processes,
                    job_pids=self._job_pids(profile.id),
                    spawned_pid=self._spawned.get(profile.id),
                    port_holders=self._port_holders_for(profile, processes),
                    dir_mismatch=_dir_mismatch(profile.cluster_dir, resolved),
                )
            )
        return result

    def foreign_servers(self) -> list[ForeignServer]:
        """Ragent, не сопоставленные ни с одним профилем ([Ф] В1). До снимка — `[]`."""  # noqa: RUF002
        return list(self._match.foreign) if self._match is not None else []

    def port_holders(self, profile_id: str) -> list[RagentProcess]:
        """Чужие держатели портов профиля — тот же расчёт, что в `statuses`.

        Неизвестный `profile_id` — `UnknownItemError` (см. `_profile_or_raise`).
        """
        profile = self._profile_or_raise(profile_id)
        return list(self._port_holders_for(profile, self._matched_processes(profile)))

    def running_count(self) -> int:
        """Число профилей с НЕПУСТЫМ Job — то есть запущенных нами и ещё живых.

        T-12 закрывает долг T-10: считалось по последнему снимку, и чужой
        `ragent`, случайно оказавшийся на каталоге кластера нашего профиля,
        поднимал вопрос «Остановить N серверов и выйти?» о процессе,
        который мы всё равно не остановим (решение 4 — чужим не управляем).
        Теперь снимок в этом вопросе не участвует вовсе: считаются профили,
        у которых есть свой Job и в нём кто-то жив. Дерево из десятка
        процессов — по-прежнему один профиль: спрашивающему (гейт выхода,
        `ui/app.py::_confirm_quit_with_servers`) нужно число серверов,
        а не число процессов.
        """  # noqa: RUF002
        return sum(1 for profile_id in self._jobs if self._job_pids(profile_id))

    def log_shutdown(self) -> int:
        """Отметить в журнале каждого РАБОТАЮЩЕГО профиля выход лаунчера. Возвращает их число.

        НАХОДКА 4 ручного чек-листа T-10 (Minor): дерево серверов гасит
        сама ОС (Job kill-on-close) — кода остановки при выходе нет
        и не появится (спека §12.4, решение заказчика), поэтому последняя
        строка журнала работающего профиля до этой правки — либо баннер
        платформы, либо вовсе `запуск: …`; конец сессии читателю журнала
        не виден. Зовётся из `ui/app.py` ПОСЛЕ согласия пользователя (или
        сразу, если серверов нет и спрашивать нечего) — ДО
        `application.quit()`, одним путём на `request_quit` и `closeEvent`
        (`_build_confirm_quit`).

        Та же семантика «работает», что у `running_count` (T-12): непустой
        Job профиля, а не совпавший процесс снимка. Разница не косметическая
        — «сервер будет остановлен вместе с ним» правда только про наш Job;
        чужому `ragent` на нашем каталоге кластера выход лаунчера ничего
        не сделает, и обещать это в его журнале было бы враньём.
        `log_event` сам глотает `OSError` (её докстринг) — отказ записи
        одного журнала не мешает дойти до остальных профилей.
        """  # noqa: RUF002
        count = 0
        for profile in self._profiles:
            if self._job_pids(profile.id):
                self.log_event(
                    profile.id, "выход лаунчера — сервер будет остановлен вместе с ним"  # noqa: RUF001
                )
                count += 1
        return count

    def journal_path(self, profile_id: str) -> Path:
        """Путь к текущему журналу профиля. Неизвестный `id` — `UnknownItemError`."""
        self._profile_or_raise(profile_id)
        return server_journal.journal_path(self._logs_dir, profile_id)

    def log_event(self, profile_id: str, text: str) -> None:
        """Дописать событие в журнал профиля. Неизвестный `id` — `UnknownItemError`.

        `OSError` глотается (только залогирован через `_log`, не поднят) —
        единственное место во всём модуле, где отказ ФС не мешает вызывающему:
        журнал — вспомогательный канал наблюдения (T-10), а не условие
        успеха операции. Везде в этом файле OSError либо переводится
        в `ServerError` (см. `_save`, `open_console`, `start`), либо (здесь)
        глотается — но никогда не уходит наружу голым.
        """  # noqa: RUF002
        self._profile_or_raise(profile_id)
        path = server_journal.journal_path(self._logs_dir, profile_id)
        try:
            server_journal.append_event(path, text, self._now())
        except OSError:
            _log.warning("не удалось записать событие в журнал профиля %s", profile_id)

    def start(
        self,
        profile_id: str,
        server_installations: Sequence[ServerInstallation],
    ) -> int:
        """Запустить `ragent` профиля в НОВОМ Job. Отказ — `ServerError` ДО порождения.

        Порядок (спека T-12 §3, дословно): неизвестный `profile_id` →
        `UnknownItemError`; версия профиля (точная или маска) не разрешилась
        ни на одну из `server_installations` → `ServerError`; НАШ `ragent`
        жив в Job профиля (`spawned_pid` есть в `job.pids()`) → `ServerError`;
        §6.4 — по последнему снимку у профиля уже есть совпавший процесс
        (наш или чужой, по командной строке они неразличимы) → `ServerError`,
        второй `ragent` на том же каталоге кластера мы не запускаем никогда
        (платформа не гарантирует безопасное поведение при этом, [Р]); чужой
        держатель портов профиля (T-12 §4) → событие `отказ запуска: <текст
        port_holders_text>` и `ServerError` — ДО ротации журнала и spawn,
        чтобы отказ не съел прошлый журнал ротацией.

        Первая проверка нужна именно по Job, а не по снимку: между запуском
        и следующим сканом (до 5 с, спека §4.4) снимок ещё не знает о нашем
        `ragent`, и повторное нажатие «Запустить» подняло бы второй сервер
        на том же каталоге кластера. Job знает о нём сразу.

        Дальше — остатки НАШЕГО прошлого дерева (решение 2 заказчика
        29.08.2026): если Job профиля непуст, а наш `ragent` в нём уже
        не значится, значит его сняли извне, а дети (`rmngr`/`rphost`/`dbgs`)
        живы и держат порты. Такой Job закрывается ЗДЕСЬ, до порождения
        нового: kill-on-close гасит остатки целиком ([Ф] 29.08.2026). Отказ
        `close()` (`JobError`) — отказ ЗАПУСКА: старый Job возвращается
        в учёт (остатки обязаны остаться видимыми на карточке), в журнал
        идёт `отказ запуска: не удалось погасить остатки прошлого запуска
        (…)`, наружу — `ServerError`. Порождать новый `ragent` поверх живых
        остатков нельзя: он поднимется полумёртвым на занятых портах
        (находка 5 чек-листа T-10).

        Событие УСПЕШНОГО гашения (`погашены остатки прошлого запуска:
        PID …`) пишется ПОСЛЕ ротации журнала, а не сразу после `close()`
        (находка задачи 3 T-12; спека §3 и план предписывали обратный
        порядок, они правлены вслед): ротация переименовывает текущий файл
        в `.1.log`, и событие, записанное до неё, уехало бы в журнал
        ПРОШЛОГО запуска — ровно туда, куда читатель не смотрит. Пункт 3
        живого чек-листа спеки (§10) требует видеть `погашены остатки…`
        и следом штатный старт в ОДНОМ (текущем) журнале. Отказ гашения при
        этом остаётся ДО ротации: несостоявшийся запуск не имеет права
        трогать прошлый журнал — то же правило, что и у чужих держателей
        портов выше.

        Ротация — BEST-EFFORT, в СВОЁМ ОТДЕЛЬНОМ `try/except OSError`
        (правка финального ревью ветки T-10, п.1): файл прошлого запуска
        может ещё держать открытым переживший `ragent` процесс
        (`dbgs`/`rmngr`, снятый из Диспетчера задач без штатной остановки),
        и `Path.replace` падает `PermissionError [WinError 32]` (Python
        `open()` не даёт `FILE_SHARE_DELETE`). Раньше эта ошибка стояла
        в общем `try` со spawn и глушила запуск целиком «отказом» без
        понятной причины — теперь отказ ротации только пишет событие
        `ротация журнала не удалась (<текст исключения>), записи продолжаются
        в тот же файл` (текст исключения — ФАКТИЧЕСКАЯ причина от ОС,
        `str(error)`, а не наша ДОГАДКА о ней: `OSError` тут может быть
        и другим — например, нет прав на сам `logs_dir`) и запуск идёт как
        обычно (полноценное решение — открытие с явным `FILE_SHARE_DELETE` —
        долг вехи, `docs/tasks.md`).

        Дальше журнал получает событие `запуск: <командная строка>`; только
        затем зовётся `server_spawn` с путём к ЭТОМУ (текущему) журналу —
        тем же файлом, в который `spawn_server` перенаправит stdout дерева
        процессов (два независимых писателя одного файла, докстринг
        `server_journal.py`), — и с СВЕЖИМ Job, куда `spawn_server` кладёт
        порождённый процесс сразу после `Popen`. После успеха в журнал
        пишется `порождён PID <pid>`, а Job и PID запоминаются за профилем:
        с этого момента `stop`, `running_count` и статус карточки отвечают
        по ним.

        `OSError` ИЛИ `JobError` из записи события `запуск: …`/`server_spawn`
        (CRITICAL 1a, финальное ревью ветки T-08; `JobError` — отказ
        `job.assign()` внутри `spawn_server`) переводятся в `ServerError`
        с командной строкой — тем же приёмом, что
        `services/launch.py::launch_infobase`: секретов в команде запуска
        сервера нет (кластерные пароли этой вехой не поддерживаются, §8
        спеки), поэтому команду можно показать пользователю целиком. Свежий
        Job при этом закрывается и в учёт НЕ попадает: держать хендл, за
        которым никого нет, незачем, а `spawn_server` при отказе `assign`
        уже убил порождённый процесс сам. Перед `raise` в журнал профиля
        пишется `отказ запуска: <текст ошибки>` — через `log_event`, чтобы
        отказ самой записи (тот же диск/антивирус) не подменил собой
        настоящую причину отказа старта. Отказ ротации в этот путь НЕ
        попадает — он не блокирует запуск (см. выше).
        """  # noqa: RUF002
        profile = self._profile_or_raise(profile_id)
        resolved = resolve_server_version(
            profile.version, [si.installation.version for si in server_installations]
        )
        if resolved is None:
            raise ServerError(
                f"Версия «{profile.version}» профиля «{profile.name}» не установлена — "
                "проверьте список установленных платформ"
            )
        installation = next(
            (si for si in server_installations if si.installation.version == resolved),
            None,
        )
        if installation is None:
            # Недостижимо в норме: resolved получен из версий тех же
            # server_installations. Явный отказ вместо StopIteration —
            # слой services не выпускает наружу голых системных исключений.
            raise ServerError(
                f"Версия «{resolved}» разрешилась, но установка для неё не найдена"
            )
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
            raise ServerError(
                f"Не удалось запустить сервер «{profile.name}»: {message}"  # noqa: RUF001
            )
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
                    f"Не удалось запустить сервер «{profile.name}»: остатки прошлого "  # noqa: RUF001
                    f"запуска (PID {pids_text}) не погашены — {error}"
                ) from error
        job = self._job_factory()
        command = LaunchCommand(
            executable=installation.ragent, arguments=build_ragent_arguments(profile)
        )
        journal = server_journal.journal_path(self._logs_dir, profile_id)
        try:
            server_journal.rotate_journal(self._logs_dir, profile_id)
        except OSError as error:
            # Important 1 финального ревью ветки T-10: ротация — отдельный
            # try/except, НЕ общий со spawn (T-10, п.1).  # noqa: RUF003
            # Файл прошлого запуска может держать открытым переживший ragent
            # процесс — Path.replace падает PermissionError [WinError 32]
            # (Python open() не даёт FILE_SHARE_DELETE). Это не отказ
            # запуска: записи продолжаются в тот же (текущий) файл журнала,
            # см. докстринг метода. Текст события — фактический str(error)
            # от системы, а не наша догадка о причине: OSError здесь мог  # noqa: RUF003
            # быть и другим (например, нет прав на сам logs_dir).
            self.log_event(
                profile_id,
                f"ротация журнала не удалась ({error}), записи продолжаются в тот же файл",
            )
        if old_job is not None and job_pids:
            # ПОСЛЕ ротации (см. докстринг метода): до неё событие уехало бы
            # в журнал прошлого запуска (.1.log) вместе с переименованным  # noqa: RUF003
            # файлом, а читателю оно нужно рядом со стартом, который оно  # noqa: RUF003
            # объясняет (спека §10, п.3 живого чек-листа).
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
            raise ServerError(
                f"Не удалось запустить сервер «{profile.name}»: {error}.\n"  # noqa: RUF001
                f"Команда: {command.command_line}"
            ) from error
        self._jobs[profile_id] = job
        self._spawned[profile_id] = pid
        self.log_event(profile_id, f"порождён PID {pid}")
        return pid

    def stop(self, profile_id: str) -> None:
        """Остановить сервер профиля: закрыть его Job — дерево гасит ОС.

        T-12, спека §3: `stop` — это `job.close()`, и всё. Kill-on-close
        гасит ВСЁ дерево процессов Job разом ([Ф] Б2 T-09 на живом дереве
        `ragent`, [Ф] 29.08.2026 на остатках без родителя), поэтому ни
        обхода детей, ни сверки `create_time`, ни гонки PID §6.2 здесь
        больше нет: они существовали ровно потому, что `TerminateProcess`
        не убивает детей ([Ф] Б2 T-07) и приходилось гасить дерево вручную
        по PID из снимка.

        Нечего останавливать — если Job профиля нет или он пуст. Это,
        в частности, и есть случай ЧУЖОГО `ragent`, совпавшего с профилем
        по каталогу кластера (решение 4 заказчика 29.08.2026): он виден
        в статусе, но не наш, Job у него неоткуда взяться, и мы его не
        трогаем — отказ прямо это и говорит. Пустой Job при отказе
        освобождается (`_forget_job`): дерево умерло само, держать хендл
        не за чем.

        Отказ `close()` (`JobError` — `CloseHandle` вернул ошибку) —
        `ServerError`; Job при этом ОСТАЁТСЯ в учёте, потому что
        `ServerJob.close()` на неудаче не теряет хендл (докстринг
        `platform_1c/job.py`) и `pids()` продолжает отвечать: остатки видны
        на карточке, попытку можно повторить. Перед `raise` в журнал
        профиля пишется `отказ остановки: <текст ошибки>` — через
        `log_event` (глотает свой собственный `OSError`), так что отказ
        записи журнала не подменяет собой настоящую причину.
        """  # noqa: RUF002
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
            stop_error = ServerError(
                f"Не удалось остановить сервер «{profile.name}»: {error}"  # noqa: RUF001
            )
            self.log_event(profile_id, f"отказ остановки: {stop_error}")
            raise stop_error from error
        del self._jobs[profile_id]
        self._spawned.pop(profile_id, None)
        self.log_event(profile_id, "остановка по команде пользователя")

    def current_console_version(self) -> VersionNumber | None:
        """Версия консоли, зарегистрированной СЕЙЧАС в реестре; `None` — не зарегистрирована.

        Чтение, не эффект UAC: `_registered_radmin` читает HKLM обычным
        пользователем ([Ф] Г2). Версия извлекается из пути `radmin.dll`
        (`<корень>\\<версия>\\bin\\radmin.dll`) той же функцией, что и для
        чужих ragent (`version_from_exe_path`, [Ф] В1) — путь до `radmin.dll`
        имеет ту же форму `<версия>\\bin\\<файл>`, что и до `ragent.exe`.
        """  # noqa: RUF002
        path = self._registered_radmin()
        if path is None:
            return None
        return version_from_exe_path(path)

    def register_console(self, target: ServerInstallation) -> None:
        """Перерегистрировать консоль на `radmin.dll` версии `target` — эффект с UAC.

        [Ф] Г2: одна команда `regsvr32 /s "<dll>"` без предварительного `/u`
        (CLSID стабильны между версиями, `register_arguments`). Отказ
        пользователя в диалоге UAC (`ElevationDeclinedError`) — штатный исход
        §7, не ошибка программы: транслируется в
        `ConsoleRegistrationDeclinedError`, UI обязан показать «версия консоли
        не изменена», а не сообщение об ошибке. Ненулевой код возврата
        `regsvr32` — настоящий сбой регистрации, код попадает в текст
        `ConsoleRegistrationError`, чтобы было что показать и с чем прийти
        в поддержку. Единственная точка входа для UAC-повышения во всём
        координаторе — см. докстринг конструктора и защитный тест
        `test_nothing_registers_without_explicit_call`.
        """  # noqa: RUF002
        try:
            exit_code = self._run_elevated("regsvr32", console.register_arguments(target.radmin))
        except ElevationDeclinedError as error:
            raise ConsoleRegistrationDeclinedError(
                "Запрос прав администратора отклонён — версия консоли не изменена"
            ) from error
        if exit_code != 0:
            raise ConsoleRegistrationError(
                f"Регистрация консоли не удалась — regsvr32 вернул код {exit_code}"
            )

    def open_console(self, root: Path, convention: ServerConvention) -> None:
        """Открыть `.msc` консоли администрирования — тот же файл для всех версий.

        Путь строится от `root` (родитель каталогов версий) по `convention`
        (`console_path`, `platform_1c/server_discovery.py`); какая именно
        версия `radmin.dll` за ним стоит сейчас, определяет реестр, не этот
        вызов — см. `current_console_version`/`register_console`. `OSError`
        `os.startfile` (файл `.msc` отсутствует, нет ассоциации) переводится
        в `ServerError` (CRITICAL 1c, финальное ревью ветки) — тем же
        приёмом, что и `start`/`_save`.
        """
        path = console_path(root, convention)
        try:
            self._open_file(str(path))
        except OSError as error:
            raise ServerError(f"Не удалось открыть консоль: {error}") from error  # noqa: RUF001

    def _profile_or_raise(self, profile_id: str) -> ServerProfile:
        """Найти профиль по `id` либо поднять `UnknownItemError`.

        Тот же приём, что `Workspace.find_by_name`/`_item`: тихая пустота
        замаскировала бы программную ошибку вызывающего («ничего не нашли»
        вместо «профиля, который спросили, больше нет в списке») под
        честный отрицательный результат операции.
        """
        profile = next((p for p in self._profiles if p.id == profile_id), None)
        if profile is None:
            raise UnknownItemError(
                f"Профиля с id «{profile_id}» нет в списке — возможно, он "  # noqa: RUF001
                "удалён с момента последнего снимка; обновите список профилей "  # noqa: RUF001
                "и повторите"
            )
        return profile

    def _matched_processes(self, profile: ServerProfile) -> tuple[RagentProcess, ...]:
        return self._match.by_profile.get(profile.id, ()) if self._match else ()

    def _job_pids(self, profile_id: str) -> tuple[int, ...]:
        """PID всего дерева Job профиля; `()`, если Job у профиля нет.

        `JobError` (`QueryInformationJobObject` отказал) переводится
        в `ServerError`: `services` не выпускает наружу голых исключений
        `platform_1c` — вызывающему нечем отличить нашу диагностику
        от чужой (докстринг `errors.py`).
        """  # noqa: RUF002
        job = self._jobs.get(profile_id)
        if job is None:
            return ()
        try:
            return job.pids()
        except JobError as error:
            raise ServerError(
                f"Не удалось прочитать процессы сервера: {error}"  # noqa: RUF001
            ) from error

    def _all_job_pids(self) -> set[int]:
        """Все PID всех наших Job — исключающий набор для `port_holders`.

        Держатель порта, оказавшийся в ЛЮБОМ нашем Job, — не чужой, а наш
        остаток (спека T-12 §4): о нём карточка говорит своей строкой
        «остатки прошлого запуска», и предлагать его же как чужого
        держателя было бы двойным учётом одного факта.
        """  # noqa: RUF002
        pids: set[int] = set()
        for profile_id in self._jobs:
            pids.update(self._job_pids(profile_id))
        return pids

    def _forget_job(self, profile_id: str) -> None:
        """Убрать Job профиля из учёта, закрыв хендл; отказ close — только в лог.

        Зовётся там, где закрывать НЕЧЕГО по существу (Job пуст, дерево
        умерло само) или профиль уходит из списка: пользователю сообщать
        не о чем, а хендл держать незачем. Отказ `close()` здесь не может
        стать отказом операции — сама операция от него не зависит, — поэтому
        уходит в `_log`, тем же приёмом, что `OSError` в `log_event`.
        """  # noqa: RUF002
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
        """Чужие держатели портов профиля по последнему снимку (спека T-12 §4).

        Пусто до первого снимка и когда у профиля есть совпавший `ragent`:
        живой `ragent` на нашем каталоге кластера — наш или чужой — уже
        описан состоянием карточки, и красная строка о занятых портах рядом
        с ним была бы шумом (порты держит именно он, это нормально).
        """  # noqa: RUF002
        if self._snapshot is None or processes:
            return ()
        return port_holders(profile, _snapshot_processes(self._snapshot), self._all_job_pids())

    def _validate(self, profile: ServerProfile, others: list[ServerProfile]) -> None:
        errors = validate_profile(profile, others, normalize=normalize_cluster_dir)
        if errors:
            raise ServerError(errors[0])

    def _save(self, updated: list[ServerProfile]) -> None:
        """Заменить список профилей и записать его. Отказ ФС откатывает память.

        Тот же приём, что `Workspace._store_user`: без отката экран после
        отказа записи показал бы профиль, которого в файле нет.

        IMPORTANT 6 (финальное ревью ветки): после успешной записи, если
        снимок процессов уже есть (`self._snapshot is not None`),
        пересопоставляем его с ОБНОВЛЁННЫМ списком профилей — тем же
        `match_profiles`, что и `apply_scan`, через общий `_snapshot_agents`.
        Без этого правка каталога кластера профиля продолжала бы показывать
        процесс СТАРОГО каталога как «работает» до следующего планового
        скана (до 5 с, спека §4.4): снимок живых PID не поменялся, поменялся
        только список профилей, а старое сопоставление `self._match` держит
        прежнюю привязку PID → id, пока его не пересчитать.
        """  # noqa: RUF002
        previous = self._profiles
        self._profiles = updated
        try:
            save_profiles(self.store_path, self._profiles)
        except OSError as error:
            self._profiles = previous
            raise ServerError(
                f"Не удалось сохранить профили серверов ({self.store_path}): {error}"  # noqa: RUF001
            ) from error
        if self._snapshot is not None:
            self._match = match_profiles(self._profiles, _snapshot_agents(self._snapshot))
