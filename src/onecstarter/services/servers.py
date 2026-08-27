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
поэтому список детей снимается ДО завершения родителя). Регистрация
консоли — последующая задача; эффекты `run_elevated`/`open_file`/
`registered_radmin` по-прежнему только сохранены в полях, здесь не зовутся.

Приём инъекции эффектов и отката состояния в памяти при отказе записи —
тот же, что в `services/workspace.py::Workspace` (см. её докстринг
и `_store_user`): экран, построенный по `profiles()`, обязан показывать
то же, что реально лежит в файле, а не то, что мы хотели туда записать.
Приём разделения снимка на «применить» (главный поток, чистое) и «прочитать»
(фон, эффект) — тот же, что `Workspace.apply_common_lists`/`common_lists_pending`
(докстринг `workspace.py`): до первого `apply_scan` снимка нет вовсе,
и `scan_pending` отличает это состояние от «серверов действительно нет».
"""  # noqa: RUF002

import os
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PureWindowsPath

from onecstarter.domain.launch import LaunchCommand
from onecstarter.domain.server import (
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
)
from onecstarter.domain.version import VersionNumber
from onecstarter.platform_1c import console, elevation, process
from onecstarter.platform_1c.process_control import ProcessControl, ProcessMismatchError
from onecstarter.platform_1c.process_scan import ProcessInfo, ProcessScanner
from onecstarter.platform_1c.server_discovery import ServerInstallation
from onecstarter.services.errors import ServerError, ServerStopError, UnknownItemError
from onecstarter.services.server_store import load_profiles, save_profiles

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
        spawn: Callable[[LaunchCommand], int] = process.spawn,
        run_elevated: Callable[[str, str], int] = elevation.run_elevated,
        open_file: Callable[[str], None] = os.startfile,
        registered_radmin: Callable[[], Path | None] = console.registered_radmin_path,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.store_path = store_path
        # Эффекты следующих задач (сканы, остановка, запуск, регистрация
        # консоли) — только сохранены, здесь не вызываются (см. докстринг
        # модуля).
        self._control = control
        self._spawn = spawn
        self._run_elevated = run_elevated
        self._open_file = open_file
        self._registered_radmin = registered_radmin
        self._new_id = new_id
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
        agents = tuple(
            RagentProcess(
                pid=info.pid,
                executable=info.executable,
                argv=info.argv,
                create_time=info.create_time,
            )
            for info in snapshot.agents
        )
        self._match = match_profiles(self._profiles, agents)

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

    def start(
        self,
        profile_id: str,
        server_installations: Sequence[ServerInstallation],
    ) -> int:
        """Запустить `ragent` профиля. Отказ — `ServerError` ДО порождения процесса.

        Порядок проверок: неизвестный `profile_id` → `UnknownItemError`;
        версия профиля (точная или маска) не разрешилась ни на одну из
        `server_installations` → `ServerError`; §6.4 — по последнему снимку
        у профиля уже есть совпавший процесс → `ServerError`, второй
        `ragent` на том же каталоге кластера мы не запускаем никогда
        (платформа не гарантирует безопасное поведение при этом, [Р]).
        Только когда все проверки пройдены — `spawn`. Никаких частичных
        эффектов: до `spawn` включительно исключение не оставляет следов.
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
        return self._spawn(command)

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
            self._terminate_or_raise(proc.pid, proc.create_time)
            for kid in kids:
                self._terminate_or_raise(kid.pid, kid.create_time)

    def stop_orphans(self, profile_id: str) -> None:
        """Погасить осиротевшие `rmngr` профиля ([Ф] А3) без живого `ragent`.

        Пустой список сирот — не ошибка, а no-op: чаще всего сирот и не
        было, и вызывающему не нужно проверять `orphan_managers` заранее.
        """  # noqa: RUF002
        profile = self._profile_or_raise(profile_id)
        processes = self._matched_processes(profile)
        for orphan in self._orphans_for(profile, processes):
            self._terminate_or_raise(orphan.pid, orphan.create_time)

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

    def _terminate_or_raise(self, pid: int, expected_create_time: float) -> None:
        """`control.terminate`, переводящее гонку PID (§6.2) в честный отказ слоя.

        `ProcessMismatchError` — исключение слоя `platform_1c`, наружу
        `ServersWorkspace` не выпускает его голым (тот же довод, что у
        `errors.py`: вызывающему нечем отличить нашу диагностику от чужой).
        """  # noqa: RUF002
        try:
            self._control.terminate(pid, expected_create_time)
        except ProcessMismatchError as error:
            raise ServerStopError(
                f"PID {pid} переиспользован системой — обновите список процессов "
                "и повторите"
            ) from error

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
        """  # noqa: RUF002
        if self._snapshot is None or processes:
            return ()
        own_dir = normalize_cluster_dir(profile.cluster_dir)
        orphans: list[ProcessInfo] = []
        for manager in self._snapshot.managers:
            if manager.argv is None:
                continue
            params = extract_ragent_params(manager.argv)
            port_matches = params.port == profile.regport
            dir_matches = (
                params.cluster_dir is not None
                and normalize_cluster_dir(params.cluster_dir) == own_dir
            )
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
