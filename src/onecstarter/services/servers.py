"""Координатор раздела «Серверы»: профили, снимок процессов, статусы.

Задача T-08.10 закрыла CRUD-контур над `servers.json`. Эта задача (T-08.11)
добавляет чтение живых процессов: снимок ragent/rmngr (`scan_servers`,
зовётся из фонового потока UI — чистая функция поверх `ProcessScanner`),
его применение (`apply_scan`, главный поток — сопоставляет процессы
с профилями через `match_profiles`) и производные от снимка вопросы:
`statuses` (что запущено, какая версия разрешилась, не разъехался ли
каталог кластера с версией), `foreign_servers` (чужие ragent — [Ф] В1),
`orphan_managers` (осиротевший rmngr без своего ragent — [Ф] А3). Эта задача
(T-08.12) добавляет сами эффекты запуска и остановки: `start` (§6.4 —
второй ragent на каталоге кластера, уже занятом совпавшим процессом
последнего снимка, не запускается нами никогда) и `stop`/`stop_orphans`
(остановка дерева целиком, [Ф] Б2: `TerminateProcess` не убивает детей,
поэтому список детей снимается ДО завершения родителя). Эта задача (T-08.13)
добавляет смену версии консоли администрирования: `current_console_version`
(чтение — версия из пути зарегистрированной `radmin.dll`, без UAC),
`register_console` (эффект — `run_elevated("regsvr32", ...)`, §7: отказ
пользователя в UAC-диалоге — штатный исход, транслируется в
`ConsoleRegistrationDeclinedError`, а не в ошибку) и `open_console`
(`open_file` на путь `.msc`). §7: регистрация зовётся ТОЛЬКО из явного
действия UI — ни конструктор, ни `apply_scan`, ни `statuses` её не трогают
(см. `_registered_radmin`/`_run_elevated`/`_open_file` — только сохранены
в конструкторе, эффекты живут в методах этой задачи).

T-10 (задача 4) переводит запуск на дочерний жизненный цикл: спека §12,
пересмотр решения 26.08.2026 — исходная редакция «отвязанный процесс,
переживает закрытие» ДЕЙСТВОВАЛА в T-08 и БОЛЬШЕ НЕ действует. Теперь
`start` порождает сервер через `server_spawn` (инъекция, `Callable[[LaunchCommand,
Path], int]` — `platform_1c/server_spawn.py::spawn_server`, запечённый
Job Object'ом в проводке `app.py`, задача 7; сам Job в `services` не
протекает ни импортом, ни параметром) — закрытие OneCStarter (или его
крах) гасит дерево серверов вместе с лаунчером ([Ф] Б1/Б2 T-09). Второй
эффект задачи — журнал профиля (`services/server_journal.py`): `start`
ротирует прошлый запуск (BEST-EFFORT — правка финального ревью ветки
T-10, п.1: `Path.replace` внутри `rotate_journal` падает `PermissionError
[WinError 32]`, если журнал ещё держит открытым процесс прошлого запуска —
`dbgs`/`rmngr`, переживший `ragent`, снятый из Диспетчера задач без
штатной остановки; Python `open()` не даёт `FILE_SHARE_DELETE`. Отказ
ротации пишет событие в журнал и НЕ прерывает запуск — записи просто
продолжаются в тот же файл; полноценное решение, открытие с явным
`FILE_SHARE_DELETE`, — долг вехи, см. `docs/tasks.md`), пишет событие
`запуск: …` до порождения процесса и `порождён PID …` после успешного
`server_spawn`; `stop`/`stop_orphans` — событие успеха или `отказ
остановки: …` перед `ServerStopError`, `log_event` — точка входа для
событий снаружи координатора (UI, задача 5, исход §8). `logs_dir` — новый
обязательный параметр конструктора, каталог журналов профилей
(`%APPDATA%\\OneCStarter\\logs\\servers`, спека §12.6, собирается
в `app.py`).

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
    extract_ragent_params,
    match_profiles,
    normalize_cluster_dir,
    version_from_exe_path,
)
from onecstarter.domain.version import VersionNumber
from onecstarter.platform_1c import console, elevation
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.platform_1c.job import JobError
from onecstarter.platform_1c.process_control import (
    ProcessAccessError,
    ProcessControl,
    ProcessMismatchError,
)
from onecstarter.platform_1c.process_scan import ProcessInfo, ProcessScanner
from onecstarter.platform_1c.server_discovery import ServerInstallation, console_path
from onecstarter.services import server_journal
from onecstarter.services.errors import (
    ConsoleRegistrationDeclinedError,
    ConsoleRegistrationError,
    ServerError,
    ServerStopError,
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

# rmngr нужен для поиска сирот ([Ф] А3, t07-protocol.md): осиротевший rmngr  # noqa: RUF003
# держит regport агента, даже когда сам ragent уже не жив. rphost и dbda
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
    ещё нет или маска не разбирается. `processes` — живые ragent этого
    профиля из последнего снимка. `orphans` — осиротевшие rmngr без своего
    ragent ([Ф] А3). `dir_mismatch` — эвристика спеки §3.2: каталог кластера
    похож на заведённый под другую версию.
    """  # noqa: RUF002

    profile: ServerProfile
    resolved: VersionNumber | None
    processes: tuple[RagentProcess, ...]
    orphans: tuple[ProcessInfo, ...]
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
        control: ProcessControl,
        server_spawn: Callable[[LaunchCommand, Path], int],
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
        # модуля). `server_spawn`/`logs_dir` обязательные и без дефолта
        # (T-10, задача 4): дефолт вида `functools.partial(spawn_server,
        # job=...)` держал бы Job внутри services, а он запечён проводкой  # noqa: RUF003
        # `app.py` (задача 7) — см. докстринг модуля.
        self._control = control
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
        """Удалить профиль по `id`. Неизвестный `id` — ошибка."""
        if not any(existing.id == profile_id for existing in self._profiles):
            raise ServerError(f"Профиля с id «{profile_id}» нет в списке")  # noqa: RUF001
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
        """Статус каждого профиля: версия, живые процессы, сироты, каталог.

        До первого `apply_scan` — `processes=()` и `orphans=()` у всех
        профилей (см. `scan_pending`), `resolved`/`dir_mismatch` от снимка
        не зависят и считаются всегда.
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
                    orphans=self._orphans_for(profile, processes),
                    dir_mismatch=_dir_mismatch(profile.cluster_dir, resolved),
                )
            )
        return result

    def foreign_servers(self) -> list[ForeignServer]:
        """Ragent, не сопоставленные ни с одним профилем ([Ф] В1). До снимка — `[]`."""  # noqa: RUF002
        return list(self._match.foreign) if self._match is not None else []

    def orphan_managers(self, profile_id: str) -> list[ProcessInfo]:
        """Сироты конкретного профиля — тот же расчёт, что в `statuses`.

        Неизвестный `profile_id` — `UnknownItemError` (см. `_profile_or_raise`).
        """
        profile = self._profile_or_raise(profile_id)
        processes = self._matched_processes(profile)
        return list(self._orphans_for(profile, processes))

    def running_count(self) -> int:
        """Число профилей с хотя бы одним живым процессом по последнему снимку.

        `0` до первого `apply_scan` (см. `scan_pending`) — та же семантика,
        что у `statuses`: «снимка ещё не было» не равно «серверов нет». Тому,
        для кого это писалось (проводка T-10, задача 6 — подтверждение
        выхода при работающих серверах), нужно именно число профилей,
        а не число процессов: профиль с двумя ragent на одном каталоге
        (§6.4 — такого мы сами не создаём, но снимок мог застать чужую
        ситуацию) считается один раз.
        """  # noqa: RUF002
        if self._match is None:
            return 0
        return sum(1 for processes in self._match.by_profile.values() if processes)

    def log_shutdown(self) -> int:
        """Отметить в журнале каждого РАБОТАЮЩЕГО профиля выход лаунчера. Возвращает их число.

        НАХОДКА 4 ручного чек-листа T-10 (Minor): дерево серверов гасит
        сама ОС (Job kill-on-close, задача 7) — кода остановки при выходе
        нет и не появится (спека §12.4, решение заказчика), поэтому
        последняя строка журнала работающего профиля до этой правки — либо
        баннер платформы, либо вовсе `запуск: …`; конец сессии читателю
        журнала не виден. Зовётся из `ui/app.py` ПОСЛЕ согласия
        пользователя (или сразу, если серверов нет и спрашивать нечего) —
        ДО `application.quit()`, одним путём на `request_quit` и
        `closeEvent` (`_build_confirm_quit`).

        Та же семантика, что у `running_count`: профиль «работает», если
        по ПОСЛЕДНЕМУ снимку у него есть хотя бы один живой процесс
        (`_matched_processes`) — до первого `apply_scan` ни один профиль
        не работает, событие не пишется никому, возвращается `0`.
        `log_event` сам глотает `OSError` (её докстринг) — отказ записи
        одного журнала не мешает дойти до остальных профилей.
        """  # noqa: RUF002
        count = 0
        for profile in self._profiles:
            if self._matched_processes(profile):
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
        в `ServerError`/`ServerStopError` (см. `_save`, `_terminate_or_raise`,
        `open_console`, `start`), либо (здесь) глотается — но никогда не
        уходит наружу голым.
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
        """Запустить `ragent` профиля дочерним процессом. Отказ — `ServerError` ДО порождения.

        Порядок проверок: неизвестный `profile_id` → `UnknownItemError`;
        версия профиля (точная или маска) не разрешилась ни на одну из
        `server_installations` → `ServerError`; §6.4 — по последнему снимку
        у профиля уже есть совпавший процесс → `ServerError`, второй
        `ragent` на том же каталоге кластера мы не запускаем никогда
        (платформа не гарантирует безопасное поведение при этом, [Р]).
        Только когда все проверки пройдены — журнал и `server_spawn`.

        T-10, задача 4, правка финального ревью ветки (п.1): сразу после
        проверок, ДО порождения процесса, журнал профиля ротируется
        (`server_journal.rotate_journal` — прошлый запуск сохраняется как
        `.1.log`, спека §12.6) — BEST-EFFORT, в СВОЁМ ОТДЕЛЬНОМ
        `try/except OSError`: файл прошлого запуска может ещё держать
        открытым переживший `ragent` процесс (`dbgs`/`rmngr`, снятый из
        Диспетчера задач без штатной остановки), и `Path.replace` падает
        `PermissionError [WinError 32]` (Python `open()` не даёт
        `FILE_SHARE_DELETE`). Раньше эта ошибка стояла в общем `try` со
        spawn и глушила запуск целиком «отказом» без понятной причины —
        теперь отказ ротации только пишет событие `ротация журнала не
        удалась (<текст исключения>), записи продолжаются в тот же файл`
        (правка координатора: текст исключения — ФАКТИЧЕСКАЯ причина
        от ОС, `str(error)`, а не наша ДОГАДКА о ней; для занятого файла
        Windows сама скажет «[WinError 32] Процесс не может получить
        доступ к файлу…», но `OSError` тут может быть и другим — например,
        нет прав на сам `logs_dir`) и запуск идёт как обычно (полноценное
        решение — открытие с явным `FILE_SHARE_DELETE` — долг вехи,
        `docs/tasks.md`). Дальше журнал получает событие `запуск: <командная
        строка>`; только затем зовётся `server_spawn` с путём к ЭТОМУ
        (текущему) журналу — тем же файлом, в который `spawn_server`
        (`platform_1c/server_spawn.py`) перенаправит stdout дерева процессов
        (два независимых писателя одного файла, докстринг
        `server_journal.py`). После успешного `server_spawn` в журнал
        пишется событие `порождён PID <pid>` (pid — то, что вернул
        `server_spawn`, спека §12.1: «PID-ы дерева по скану»). Сервер
        запущен дочерним — закрытие или крах OneCStarter гасит его вместе
        с лаунчером через Job Object, запечённый проводкой `app.py`
        (задача 7); `services` этого не видит и не обязан — исходная
        редакция «отвязанный процесс, переживает закрытие» реализовывалась
        T-08 и здесь больше не действует (спека §12, пересмотр 28.08.2026).

        `OSError` ИЛИ `JobError` из записи события `запуск: …`/`server_spawn`
        (CRITICAL 1a, финальное ревью ветки T-08, расширено задачей 4 T-10 —
        `JobError` из отказа `job.assign()` внутри `spawn_server`, платформа
        `platform_1c/job.py`) переводятся в `ServerError` с командной строкой
        — тем же приёмом, что `services/launch.py::launch_infobase`:
        секретов в команде запуска сервера нет (кластерные пароли этой
        вехой не поддерживаются, §8 спеки), поэтому команду можно показать
        пользователю целиком. Перед `raise` в журнал профиля пишется событие
        `отказ запуска: <текст ошибки>` — через `log_event`, чтобы отказ
        самой записи (тот же диск/антивирус) не подменил собой настоящую
        причину отказа старта. Отказ ротации в этот путь НЕ попадает —
        он не блокирует запуск (см. выше).
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
        processes = self._matched_processes(profile)
        if processes:
            pids = ", ".join(str(p.pid) for p in processes)
            raise ServerError(
                f"Сервер «{profile.name}» уже работает, PID {pids} — второй ragent "
                "на этом каталоге кластера не запускается"
            )
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
            # от системы (правка координатора после волны исправлений),
            # а не наша догадка о причине: OSError здесь мог быть и другим  # noqa: RUF003
            # (например, нет прав на сам logs_dir), и предполагать занятость
            # файла в тексте события было бы враньём в общем случае.
            self.log_event(
                profile_id,
                f"ротация журнала не удалась ({error}), записи продолжаются в тот же файл",
            )
        try:
            server_journal.append_event(journal, f"запуск: {command.command_line}", self._now())
            pid = self._server_spawn(command, journal)
        except (OSError, JobError) as error:
            self.log_event(profile_id, f"отказ запуска: {error}")
            raise ServerError(
                f"Не удалось запустить сервер «{profile.name}»: {error}.\n"  # noqa: RUF001
                f"Команда: {command.command_line}"
            ) from error
        self.log_event(profile_id, f"порождён PID {pid}")
        return pid

    def stop(self, profile_id: str) -> None:
        """Остановить дерево процессов профиля целиком: агент(ы) и их дети.

        [Ф] Б2, t07-protocol.md: `TerminateProcess` не убивает детей — `rmngr`
        и `rphost` продолжают жить и держать порты после смерти `ragent`,
        поэтому на каждый совпавший процесс список детей снимается ДО его
        завершения (иначе можно упустить ребёнка, порождённого в интервале
        между снимком и убийством родителя), а сами дети завершаются уже
        после родителя. Жёсткое завершение безопасно: тот же замер показал,
        что кластер переживает его и поднимается с тем же `clstid`.

        §6.2, гонка PID: `ProcessControl.terminate` сверяет `create_time` из
        снимка с фактическим временем создания процесса; несовпадение
        означает, что Windows успела переиспользовать PID под другой
        процесс, — `stop` немедленно поднимает `ServerStopError` и не идёт
        дальше (ни к оставшимся детям того же агента, ни к следующему
        совпавшему процессу). Процессы других профилей и чужие ragent того
        же снимка вообще не читаются: цикл идёт только по процессам,
        сопоставленным именно этому профилю.

        T-10, задача 4: успешная остановка пишет в журнал профиля событие
        `остановка по команде пользователя`; отказ (`ServerStopError`) пишет
        `отказ остановки: …` ДО `raise` — см. `_terminate_or_raise`.
        """  # noqa: RUF002
        profile = self._profile_or_raise(profile_id)
        processes = self._matched_processes(profile)
        if not processes:
            raise ServerError(
                f"Нечего останавливать — по последнему снимку сервер «{profile.name}» "
                "не запущен; обновите список процессов и повторите"
            )
        for proc in processes:
            kids = self._control.children(proc.pid)
            self._terminate_or_raise(profile_id, proc.pid, proc.create_time)
            for kid in kids:
                self._terminate_or_raise(profile_id, kid.pid, kid.create_time)
        self.log_event(profile_id, "остановка по команде пользователя")

    def stop_orphans(self, profile_id: str) -> None:
        """Погасить осиротевшие `rmngr` профиля ([Ф] А3) без живого `ragent`.

        Пустой список сирот — не ошибка, а no-op: чаще всего сирот и не
        было, и вызывающему не нужно проверять `orphan_managers` заранее —
        и событие в журнал в этом случае не пишется (гасить было нечего).
        Успешное гашение непустого списка пишет одно событие
        `гашение сирот: PID …` со всеми завершёнными PID; отказ —
        `отказ остановки: …` ДО `raise`, см. `_terminate_or_raise`.
        """  # noqa: RUF002
        profile = self._profile_or_raise(profile_id)
        processes = self._matched_processes(profile)
        orphans = self._orphans_for(profile, processes)
        for orphan in orphans:
            self._terminate_or_raise(profile_id, orphan.pid, orphan.create_time)
        if orphans:
            pids = ", ".join(str(orphan.pid) for orphan in orphans)
            self.log_event(profile_id, f"гашение сирот: PID {pids}")

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
        приёмом, что и `start`/`_terminate_or_raise`.
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

    def _terminate_or_raise(
        self, profile_id: str, pid: int, expected_create_time: float
    ) -> None:
        """`control.terminate`, переводящее гонку PID (§6.2) и отказ прав в честный отказ слоя.

        `ProcessMismatchError`/`ProcessAccessError` — исключения слоя
        `platform_1c`, наружу `ServersWorkspace` не выпускает их голыми (тот
        же довод, что у `errors.py`: вызывающему нечем отличить нашу
        диагностику от чужой). `ProcessAccessError` (CRITICAL 1b, финальное
        ревью ветки) — `psutil.AccessDenied` из `PsutilControl.terminate`:
        процесс, совпавший с профилем по каталогу кластера, но запущенный
        другим пользователем или как служба, — нам его не завершить.

        T-10, задача 4: перед `raise` в журнал профиля пишется событие
        `отказ остановки: <текст ServerStopError>` — через `log_event`
        (глотает свой собственный `OSError`, см. его докстринг), так что
        отказ записи журнала не подменяет собой настоящий `ServerStopError`.
        """  # noqa: RUF002
        try:
            self._control.terminate(pid, expected_create_time)
        except ProcessMismatchError as error:
            stop_error = ServerStopError(
                f"PID {pid} переиспользован системой — обновите список процессов "
                "и повторите"
            )
            self.log_event(profile_id, f"отказ остановки: {stop_error}")
            raise stop_error from error
        except ProcessAccessError as error:
            stop_error = ServerStopError(
                f"PID {pid}: нет прав на завершение — возможно, процесс запущен "
                "другим пользователем или службой"
            )
            self.log_event(profile_id, f"отказ остановки: {stop_error}")
            raise stop_error from error

    def _orphans_for(
        self, profile: ServerProfile, processes: tuple[RagentProcess, ...]
    ) -> tuple[ProcessInfo, ...]:
        """rmngr снимка на regport/каталоге профиля при отсутствии его ragent.

        [Ф] А3, t07-protocol.md: rmngr переживает смерть ragent и продолжает
        держать порт регистрации — следующий запуск того же профиля молча
        упадёт на этот порт, если сирота не найдена заранее. У rmngr
        собственный `-port` равен `-regport` агента, поэтому сравниваем
        именно так, а не с `-regport` самого rmngr (такого ключа у него
        может и не быть). Второе условие — совпавший каталог кластера
        (тот же `-d`, если он у rmngr есть). `argv=None` — процесс
        непрозрачен ([Ф] В1) и пропускается: сопоставить нечем, придумывать
        нельзя.

        IMPORTANT 5 (финальное ревью ветки): кандидат исключается из сирот,
        если его СОБСТВЕННЫЙ `-d` совпадает с каталогом ЛЮБОГО живого агента
        текущего снимка (`self._snapshot.agents`, не только процессов ЭТОГО
        профиля) — иначе `-port`-эвристика предлагала бы «Погасить» rmngr
        живого ЧУЖОГО кластера только потому, что он случайно совпал
        с нашим `regport` (коллизия портов между профилем и чужим ragent),
        хотя rmngr принадлежит живому дереву и гасить его нельзя.
        """  # noqa: RUF002
        if self._snapshot is None or processes:
            return ()
        own_dir = normalize_cluster_dir(profile.cluster_dir)
        live_agent_dirs: set[str] = set()
        for agent in self._snapshot.agents:
            if agent.argv is None:
                continue
            agent_dir = extract_ragent_params(agent.argv).cluster_dir
            if agent_dir is not None:
                live_agent_dirs.add(normalize_cluster_dir(agent_dir))
        orphans: list[ProcessInfo] = []
        for manager in self._snapshot.managers:
            if manager.argv is None:
                continue
            params = extract_ragent_params(manager.argv)
            manager_dir = (
                normalize_cluster_dir(params.cluster_dir)
                if params.cluster_dir is not None
                else None
            )
            if manager_dir is not None and manager_dir in live_agent_dirs:
                # rmngr сидит на каталоге ЖИВОГО агента (не обязательно
                # нашего профиля) — не сирота, даже если совпал по -port.
                continue
            port_matches = params.port == profile.regport
            dir_matches = manager_dir == own_dir
            if port_matches or dir_matches:
                orphans.append(manager)
        return tuple(orphans)

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
