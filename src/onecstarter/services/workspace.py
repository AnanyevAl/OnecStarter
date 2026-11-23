"""Координатор слоя services: состояние и сценарии поверх узких модулей.

Держит байты файла списка баз (не хеш и не разобранный документ — тот
собирается и отбрасывается заново при каждой перестройке), наши данные
и список установленных версий. Эффекты — порождение процесса, открытие
браузера, текущее время и генерация UUID — инжектируются: без этого тесты
недетерминированы, а процессы 1С запускались бы по-настоящему.

Слежения за файлом здесь нет: reload_if_changed вызывает слой представления
по своему триггеру (QFileSystemWatcher живёт в ui — инвариант 1).
"""  # noqa: RUF002

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import (
    ClientConvention,
    ClientKind,
    Credentials,
    LaunchCommand,
    LaunchTarget,
    convention_for,
)
from onecstarter.domain.selection import resolve_version
from onecstarter.domain.version import Installation, VersionNumber, parse_version
from onecstarter.platform_1c.dll_search import open_url as open_url_clean
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.platform_1c.elevation import spawn_elevated as spawn_elevated_process
from onecstarter.platform_1c.process import spawn as spawn_process
from onecstarter.security.credentials import (
    SERVICE,
    CredentialBackendError,
    CredentialStore,
    repository_key,
)
from onecstarter.security.secrets import contains_secret_arguments, has_unclosed_quote
from onecstarter.services.availability import file_path_of
from onecstarter.services.catalog import (
    EMPTY_COMMON_DATA,
    CommonListData,
    CommonListError,
    TreeNode,
    build_tree,
    common_items_from_data,
    dedupe,
    items_from_document,
)
from onecstarter.services.edit import Patch, PatchKind, PatchResult, ReorderPatch, SectionPatch
from onecstarter.services.errors import (
    CredentialStoreError,
    InvalidRequestError,
    LaunchDeclinedError,
    LaunchError,
    ReadOnlySourceError,
    ServicesError,
    UnknownItemError,
    UserDataWriteError,
)
from onecstarter.services.groups import GroupPatch, GroupPatchKind, GroupRemoval
from onecstarter.services.launch import LaunchOutcome, launch_infobase, opens_in_browser
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.paths import ROOT, normalize_folder
from onecstarter.services.user_data import (
    BaseUserData,
    load_user_data,
    record_launch,
    rekey,
    save_user_data,
    set_designer_params,
    set_favorite,
    set_login,
    set_repository,
)
from onecstarter.services.writer import write_patch


def _has_control_chars(text: str) -> bool:
    """Есть ли управляющий символ < 0x20, кроме табуляции (она — разделитель ключей).

    `subprocess.Popen` на NUL поднимает `ValueError`, а не `ServicesError`, — он вылетел
    бы из слота Qt; перевод строки разорвал бы argv (финальное ревью блока 1, F7).
    """  # noqa: RUF002
    return any(ord(char) < 0x20 and char != "\t" for char in text)


def _full_version(text: str | None) -> VersionNumber | None:
    """Полная (четырёхчастная) версия из `Version` секции; иначе `None`."""
    if text is None:
        return None
    try:
        version = parse_version(text.strip())
    except ValueError:
        return None
    return version if version.is_full else None


def _records_word(count: int) -> str:
    """Согласовать слово «запись» с числом: 1 запись, 2 записи, 5 записей."""  # noqa: RUF002
    if count % 100 in range(11, 15):
        return "записей"
    if count % 10 == 1:
        return "запись"
    if count % 10 in (2, 3, 4):
        return "записи"
    return "записей"


@dataclass(frozen=True)
class RepositorySettings:
    """Хранилище конфигурации базы — диалогу свойств. Сам пароль наружу не отдаётся."""

    address: str | None
    user: str | None
    has_password: bool | None  # None — диспетчер учётных данных недоступен


@dataclass(frozen=True)
class BatchTarget:
    """Всё, что исполнителю пакетных операций нужно знать о базе (спека v4, §6.1–§6.3).

    Пароли в `repr` и сравнение не попадают (инвариант 5) — как у `Credentials`.
    """  # noqa: RUF002

    key: str
    name: str
    group: str = ""
    executable: Path | None = None
    version: VersionNumber | None = None
    login: str | None = None
    password: str | None = field(default=None, repr=False, compare=False)
    repository_address: str | None = None
    repository_user: str | None = None
    repository_password: str | None = field(default=None, repr=False, compare=False)
    file_path: str | None = None
    problems: tuple[str, ...] = ()
    # Диспетчер учётных данных отказал: пароли `None`, их можно ввести при запуске.
    store_unavailable: bool = False


# Приёмка 21.11.2026, Р2: окно свойств запирает «ОК» заранее, это — второй рубеж.  # noqa: RUF003
DESIGNER_QUOTE_REFUSAL = (
    "Строка параметров Конфигуратора не сохранена: в ней незакрытая кавычка — закройте её, "
    "иначе строку не проверить на пароль"
)
DESIGNER_SECRET_REFUSAL = (
    "Строка параметров Конфигуратора не сохранена: в ней пароль, а в файле программы он "  # noqa: RUF001
    "лежал бы открытым текстом. Пароль пользователя базы задайте в поле «Пароль» свойств базы"
)


@dataclass(frozen=True)
class WorkspacePaths:
    ibases: Path
    user_data: Path
    cfg_paths: tuple[Path, ...] = ()


class Workspace:
    """Координатор: состояние списка баз, наших данных и установленных версий.

    Конструктор вызывает load_user_data и может подняться с
    UserDataUnavailableError, если файл наших данных (bases.json) существует,
    но недоступен для чтения, либо испорченный файл не удалось перенести
    в .bad. Исключение не гасится и обязано дойти до вызывающего — слой UI
    обязан показать пользователю внятное сообщение с путём к файлу, а не
    трассировку. Молча подменять пустыми данными запрещено: первое же
    сохранение затёрло бы живую историю запусков и избранное.
    """  # noqa: RUF002

    def __init__(
        self,
        paths: WorkspacePaths,
        *,
        installations: Sequence[Installation] | None,
        conventions: Sequence[ClientConvention],
        cfg_rules: Sequence[DefaultVersionRule],
        default_app: str | None = None,
        web_default_is_browser: bool = False,
        spawn: Callable[[LaunchCommand], int] = spawn_process,
        spawn_elevated: Callable[[LaunchCommand], int] = spawn_elevated_process,
        open_url: Callable[[str], bool] = open_url_clean,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
        credentials: CredentialStore,
    ) -> None:
        self.paths = paths
        # `None` — «обнаружение платформ ещё не завершено» (спека T-04.6,
        # §3.4), а не «установок нет»: конструктор не обязан ждать фоновую  # noqa: RUF003
        # задачу поиска и вправе получить готовый список сразу (тесты,
        # `run_launch` после обнаружения). Различие живёт в installations_pending.
        self._installations = None if installations is None else list(installations)
        self._conventions = list(conventions)
        self._cfg_rules = list(cfg_rules)
        self._default_app = default_app
        self._web_default_is_browser = web_default_is_browser
        self._spawn = spawn
        self._spawn_elevated = spawn_elevated
        self._open_url = open_url
        self._now = now
        self._new_id = new_id
        self._credentials = credentials
        # Храним сами байты файла, а не хеш: список баз измеряется килобайтами,  # noqa: RUF003
        # хеш экономии не даёт, а байты избавляют от повторного чтения при  # noqa: RUF003
        # перестроении модели.
        self._raw = b""
        self._items: list[InfobaseItem] = []
        self._common_errors: list[CommonListError] = []
        # Снимок общих списков (спека T-04.6, §3.3): конструктор их не читает
        # вовсе — сеть до показа окна недопустима. До первого apply_common_lists
        # снимок пуст, а common_lists_pending говорит об этом отдельно от  # noqa: RUF003
        # «списков нет» — иначе раздел общих списков в UI обманул бы
        # пользователя пустотой вместо «ещё читаются».
        self._common_data: CommonListData = EMPTY_COMMON_DATA
        self._common_loaded = False
        self._user: Mapping[str, BaseUserData] = load_user_data(paths.user_data)
        self._reload()

    def items(self) -> list[InfobaseItem]:
        return list(self._items)

    @property
    def installations_pending(self) -> bool:
        """`True`, пока фоновое обнаружение платформ не отдало результат.

        Спека T-04.6, §3.4: пустой список установок и «обнаружение ещё
        не завершено» — разные состояния, и одно из другого не выводится —
        иначе до готовности колонка версии молча соврала бы «нет
        установленных версий».
        """
        return self._installations is None

    def set_installations(self, installations: Sequence[Installation]) -> None:
        """Положить результат фонового обнаружения платформ.

        Спека T-04.6, §3.3: `Workspace` мутируется только из главного
        потока — вызывающий (сигнал по завершении фона) отвечает за это.
        `_rebuild` не зовётся: записи списка баз не зависят от того, какие
        версии платформы установлены, только запуск и колонка версии в UI.
        """
        self._installations = list(installations)

    @property
    def default_app(self) -> str | None:
        """Текущий клиент по умолчанию — сборке приложения и тестам проводки."""
        return self._default_app

    def set_default_app(self, default_app: str | None) -> None:
        """Сменить клиента по умолчанию на лету (настройка «Клиент по умолчанию»).

        Влияет только на последующие запуски; `_rebuild` не зовётся — записи
        списка от выбора клиента не зависят (тот же довод, что
        у `set_installations`).
        """  # noqa: RUF002
        self._default_app = default_app

    def set_web_launch(self, *, is_browser: bool) -> None:
        """Настройка «Веб-базы открывать». Слабее записи: `App` решает
        раньше (спека v2.3, §3)."""  # noqa: RUF002
        self._web_default_is_browser = is_browser

    @property
    def common_lists_pending(self) -> bool:
        """`True`, пока снимок общих списков ни разу не применялся.

        Спека T-04.6, §3.3: конструктор общие списки не читает — читает их
        фоновая задача старта, а `apply_common_lists` кладёт результат
        в состояние. До первого вызова снимок пуст, и это поле отличает
        такую пустоту («ещё не читали») от «списков действительно нет».
        """  # noqa: RUF002
        return not self._common_loaded

    def apply_common_lists(self, data: CommonListData) -> None:
        """Положить снимок общих списков и перестроить модель по нему.

        Спека T-04.6, §3.3: чтение общих списков (эффект, фон) отделено
        от применения (чистое, главный поток). После вызова снимок —
        источник для всех последующих `_rebuild`, пока не придёт следующий
        `apply_common_lists`: до этой задачи `_rebuild` перечитывал общие
        списки с диска при каждой перестройке (`set_favorite`, `launch`,
        любая правка), то есть сетевые чтения происходили не только
        на старте. Слежения за изменением общих списков не было и не
        появляется — обновляет их только эта фоновая задача.
        """  # noqa: RUF002
        self._common_data = data
        self._common_loaded = True
        self._rebuild()

    def tree(self) -> list[TreeNode]:
        # Дерево строится только по пользовательскому списку. Базы из общих
        # списков — отдельная ветка UI (спека v1, §2), они доступны через items().
        return build_tree([item for item in self._items if item.source is InfobaseSource.USER])

    def common_errors(self) -> list[CommonListError]:
        return list(self._common_errors)

    def reload_if_changed(self) -> bool:
        """Перечитать файл, если он изменился. `False` — перечитывать нечего.

        Отказ чтения тоже даёт `False`: штатный стартер перезаписывает файл
        целиком, и на Windows чтение в этот момент может упасть отказом
        доступа. Вызывает этот метод watcher из Qt-слота, где исключение
        пользователю не показывается (в оконной сборке консоли нет), поэтому
        отказ обязан быть тихим и обратимым — состояние остаётся прежним,
        а следующее событие watcher'а повторит попытку.

        Ошибка чтения при построении (конструктор) не гасится: там она
        означает не гонку с перезаписью, а нерабочее окружение.
        """  # noqa: RUF002
        try:
            payload = self._read_bytes()
        except OSError:
            return False
        if payload == self._raw:
            return False
        self._raw = payload
        self._rebuild()
        return True

    def add_infobase(
        self,
        name: str,
        connect: str,
        folder: str | None = None,
        version: str | None = None,
        app: str | None = None,
    ) -> str:
        """Добавить запись и вернуть её ключ привязки.

        Ключ возвращается, потому что искать новую запись по имени нельзя:
        имена в списке не уникальны (дизайн плана 3, §5 — `ADD` с дублем
        разрешён).

        `version` и `app` попадают в секцию, только когда заданы: «как
        установлено» и «Авто» в диалоге добавления означают отсутствие ключа,
        а не пустое значение (спека §3) — файл читает и перезаписывает
        штатный стартер, и пустая строка вместо отсутствующего ключа меняет
        его поведение.
        """  # noqa: RUF002
        changes: dict[str, str | None] = {"Connect": connect}
        if folder:
            changes["Folder"] = folder
        if version:
            changes["Version"] = version
        if app:
            changes["App"] = app
        result = self._write(SectionPatch(PatchKind.ADD, name=name, changes=changes))
        if result.key is None:
            # Недостижимо: ADD всегда создаёт секцию и возвращает её ключ.
            raise ServicesError("Запись добавлена, но её ключ неизвестен")
        return result.key

    def update_infobase(
        self,
        key: str,
        changes: Mapping[str, str | None],
        new_name: str | None = None,
    ) -> None:
        self._reject_common(key)
        self._write(
            SectionPatch(
                PatchKind.UPDATE, target_key=key, changes=dict(changes), new_name=new_name
            ),
            rekey_from=key,
            move_secret=True,
        )

    def remove_infobase(self, key: str) -> bool:
        """Удалить запись. `False` — цели с таким ключом в файле не нашлось.

        Отсутствие цели не ошибка (дизайн плана 3, §5: пользователь хотел,
        чтобы записи не было — её нет), но и не успех: ключ мог смениться
        из-за правки файла извне, и тогда запись осталась на месте.
        """  # noqa: RUF002
        self._reject_common(key)
        applied = self._write(SectionPatch(PatchKind.REMOVE, target_key=key)).applied
        failed = self._delete_secrets(key)
        if failed:
            raise CredentialStoreError(
                "Запись удалена, но в диспетчере учётных данных остались секреты — "
                "удалите их вручную: " + "; ".join(failed)
            )
        return applied

    def add_group(self, name: str, folder: str | None = None) -> str:
        """Создать секцию-группу и вернуть её ключ привязки."""
        result = self._write(
            GroupPatch(GroupPatchKind.CREATE, name=name, new_folder=folder)
        )
        if result.key is None:
            # Недостижимо: создание всегда даёт секцию и её ключ.
            raise ServicesError("Группа создана, но её ключ неизвестен")
        return result.key

    def update_group(
        self,
        key: str,
        *,
        new_name: str | None = None,
        new_folder: str | None = None,
    ) -> str:
        """Переименовать и/или переместить группу, переписав Folder потомков.

        Одна операция, а не две: и переименование, и перемещение меняют
        собственный путь группы, а значит требуют одного и того же каскада.
        Возвращает фактический ключ группы после применения — он меняется,
        если у секции не было `ID`.
        """  # noqa: RUF002
        self._reject_common(key)
        result = self._write(
            GroupPatch(
                GroupPatchKind.RETARGET,
                target_key=key,
                new_name=new_name,
                new_folder=new_folder,
            ),
            rekey_from=key,
        )
        if result.key is None:
            # Недостижимо: RETARGET либо применяется, либо поднимает исключение.
            raise ServicesError("Группа изменена, но её ключ неизвестен")
        return result.key

    def remove_group(self, key: str, removal: GroupRemoval) -> bool:
        """Удалить группу. `False` — цели с таким ключом в файле не нашлось.

        Политика для содержимого обязательна: `PROMOTE` поднимает потомков
        к родителю удаляемой группы, `RECURSIVE` удаляет их вместе с ней.

        Пароли записей, удалённых вместе с группой, удаляются из хранилища:
        суррогатный ключ секции без ID достался бы новой записи с тем же
        именем и строкой соединения — вместе с «удалённым» паролем.
        """  # noqa: RUF002
        self._reject_common(key)
        before = {item.key for item in self.items() if not item.is_group}
        applied = self._write(
            GroupPatch(GroupPatchKind.REMOVE, target_key=key, removal=removal)
        ).applied
        gone = before - {item.key for item in self.items() if not item.is_group}
        failed: list[str] = []
        for removed in sorted(gone):
            failed += self._delete_secrets(removed)
        if failed:
            raise CredentialStoreError(
                "Группа удалена, но пароли её записей остались в диспетчере "
                "учётных данных — удалите их вручную: " + "; ".join(failed)
            )
        return applied

    def _delete_secrets(self, key: str) -> list[str]:
        """Удалить пароль базы и пароль хранилища записи; вернуть отказы.

        Каждый секрет — в своём `try`: отказ первого не оставляет второй в хранилище
        молча. Отказ называет запись хранилища паролей целиком (ключ секретом не
        является — как в `_move_secret`), значение не называет.
        """
        failed: list[str] = []
        for secret_key, what in ((key, "пароль"), (repository_key(key), "пароль хранилища")):
            try:
                self._credentials.delete(secret_key)
            except CredentialBackendError as error:
                failed.append(f"{what} `{SERVICE}/{secret_key}`: {error}")
        return failed

    def move_within_group(self, key: str, after_key: str | None) -> None:
        """Переставить запись/группу внутри её группы. `after_key is None` — в начало.

        Задача 15, спека 4b, §4: только позиция среди соседей одной группы.
        Перенос между группами — `update_infobase`/`update_group` (меняют
        `Folder`), эта операция `Folder` не трогает вовсе.
        """
        self._reject_common(key)
        self._write(ReorderPatch(target_key=key, after_key=after_key))

    def set_favorite(self, key: str, value: bool) -> None:
        item = self._item(key)
        if item.is_group:
            # Наши данные привязываются только к базам (дизайн плана 3, §4):
            # у групп нет ни истории, ни избранного. Запись в bases.json  # noqa: RUF003
            # по ключу группы была бы мусором без эффекта.
            raise InvalidRequestError(f"«{item.name}» — группа, у неё нет избранного")  # noqa: RUF001
        self._store_user(
            set_favorite(self._user, key, value), "Не удалось сохранить избранное"  # noqa: RUF001
        )
        self._rebuild()

    def credentials_of(self, key: str) -> tuple[str | None, bool | None]:
        """Логин и признак «пароль сохранён» — диалогу. Сам пароль наружу
        не отдаётся никогда (спека v2.2, §4).

        `has_password is None` — «хранилище недоступно», третье состояние
        рядом с «пароль есть» и «пароля нет». Отказ ловится здесь и наружу
        исключением не выходит: логин лежит в наших данных и прочитан ДО
        обращения к хранилищу, а прежняя редакция выбрасывала оба значения
        разом. На машине без Credential Manager диалог свойств показывал
        из-за этого пустое поле «Пользователь» у записи с сохранённым
        логином — и «ОК» затирал логин молча (финальное ревью, I3).
        """  # noqa: RUF002
        login = self._user.get(key, BaseUserData()).login
        try:
            has_password: bool | None = self._credentials.read(key) is not None
        except CredentialBackendError:
            has_password = None
        return login, has_password

    def set_credentials(
        self, key: str, login: str | None, password: str | None, remember: bool
    ) -> None:
        """Записать логин в наши данные, пароль — в хранилище. Порядок важен:
        логин пишется первым, и отказ хранилища не откатывает его — сообщение
        различает «логин записан, пароль нет» (спека §4, §8). Дерево
        перестраивается в любом исходе: логин уже на диске, и модель в памяти
        обязана его отражать до того, как ошибка уйдёт наверх (как `launch`
        и `_write`; тот же класс дефекта, что чинил add5b16).

        `login` пустой → секрет удаляется: пароль без логина неприменим.
        `remember` снят → секрет удаляется. `remember` стоит, `password` не
        задан → сохранённый пароль остаётся (пользователь не перепечатывал).
        """  # noqa: RUF002
        item = self._item(key)
        if item.is_group:
            raise InvalidRequestError(f"«{item.name}» — группа, у неё нет пользователя")  # noqa: RUF001
        normalized = (login or "").strip() or None
        self._store_user(set_login(self._user, key, normalized), "Не удалось сохранить логин")  # noqa: RUF001
        try:
            if normalized is None or not remember:
                self._credentials.delete(key)
            elif password is not None:
                self._credentials.write(key, password)
        except CredentialBackendError as error:
            raise CredentialStoreError(
                f"Логин сохранён, пароль — нет: {error}"
            ) from error
        finally:
            self._rebuild()

    def repository_of(self, key: str) -> RepositorySettings:
        data = self._user.get(key, BaseUserData())
        try:
            has_password: bool | None = self._credentials.read(repository_key(key)) is not None
        except CredentialBackendError:
            has_password = None
        return RepositorySettings(data.repository_address, data.repository_user, has_password)

    def set_repository(
        self,
        key: str,
        address: str | None,
        user: str | None,
        password: str | None,
        remember: bool,
    ) -> None:
        """Адрес и пользователь хранилища — в наши данные, пароль — в хранилище паролей.

        Правила те же, что у `set_credentials`: данные пишутся первыми, отказ хранилища
        паролей их не откатывает; пользователь пуст или «запомнить» снято — секрет
        удаляется; «запомнить» стоит, пароль не задан — сохранённый остаётся.
        """  # noqa: RUF002
        item = self._item(key)
        if item.is_group:
            raise InvalidRequestError(f"«{item.name}» — группа, у неё нет хранилища конфигурации")  # noqa: RUF001
        clean_address = (address or "").strip() or None
        clean_user = (user or "").strip() or None
        if clean_address is not None and _has_control_chars(clean_address):
            raise InvalidRequestError("Адрес хранилища не может содержать управляющие символы")
        if clean_user is not None and _has_control_chars(clean_user):
            raise InvalidRequestError(
                "Имя пользователя хранилища не может содержать управляющие символы"
            )
        self._store_user(
            set_repository(self._user, key, clean_address, clean_user),
            "Не удалось сохранить параметры хранилища конфигурации",  # noqa: RUF001
        )
        secret_key = repository_key(key)
        try:
            if clean_user is None or not remember:
                self._credentials.delete(secret_key)
            elif password is not None:
                self._credentials.write(secret_key, password)
        except CredentialBackendError as error:
            raise CredentialStoreError(
                f"Параметры хранилища сохранены, пароль — нет: {error}"
            ) from error
        finally:
            self._rebuild()

    def opens_in_browser(self, key: str) -> bool:
        """Откроет ли обычный запуск записи браузер (`services.launch.opens_in_browser`).

        Неизвестный ключ — `False`: отказ даст сам запуск, своим сообщением.
        """
        item = self._find(key)
        if item is None:
            return False
        return opens_in_browser(
            item,
            default_app=self._default_app,
            web_default_is_browser=self._web_default_is_browser,
        )

    def batch_target(self, key: str) -> BatchTarget:
        """База для пакетной операции Конфигуратора; исключений не бросает.

        Что мешает запуску — в `problems`. Шаг идёт с `/AppAutoCheckVersion-`:
        перезапуск другой версии нам не нужен.

        Версия файловой базы — `resolve_version`, как у обычного запуска. Серверная база —
        только с точной (полной) версией в `Version` секции, и она должна быть установлена:
        версию клиента серверной базы диктует кластер ([Ф] T-05.16, скил platform-launch,
        факт 14), а клиент не той версии с `/AppAutoCheckVersion-` молча зависает
        ([Ф] T-05.16). Подбор по умолчаниям (`DefaultVersion`, правила cfg, максимальная
        установленная) для серверной базы не применяется. Пакетный режим при версии, не
        совпавшей с кластером, не виснет и не перезапускается — ошибка с кодом 1 в обеих
        полярностях `/AppAutoCheckVersion` ([Ф] Э11, 22.11.2026, скил, факт 18): другой
        версией шаг не выполнится, поэтому правило точной версии остаётся.
        """  # noqa: RUF002
        item = self._find(key)
        if item is None:
            return BatchTarget(key, "", problems=("база не найдена в списке",))
        if item.is_group or item.connect is None:
            return BatchTarget(key, item.name, problems=("это группа, а не база",))  # noqa: RUF001
        folder = normalize_folder(item.folder)
        group = "" if folder == ROOT else folder
        if item.kind is ConnectKind.WEB:
            return BatchTarget(
                key,
                item.name,
                group,
                problems=("веб-база: пакетный режим Конфигуратора с ней не работает",),  # noqa: RUF001
            )
        problems: list[str] = []
        executable: Path | None = None
        version: VersionNumber | None = None
        if self._installations is None:
            problems.append("обнаружение версий платформы ещё не завершено")
        else:
            installed = [installation.version for installation in self._installations]
            if item.kind is ConnectKind.SERVER:
                exact = _full_version(item.requested_version)
                if exact is None:
                    problems.append(
                        "серверная база: задайте в свойствах точную версию платформы "
                        "(например, 8.3.27.2214)"
                    )
                elif exact in installed:
                    version = exact
                else:
                    problems.append(f"версия платформы {item.requested_version} не установлена")
            else:
                version = resolve_version(
                    item.requested_version,
                    item.section_default_version,
                    self._cfg_rules,
                    installed,
                ).version
                if version is None:
                    problems.append(
                        f"версия платформы {item.requested_version} не установлена"
                        if item.requested_version
                        else "версия платформы не определена"
                    )
            if version is not None:
                installation = next(i for i in self._installations if i.version == version)
                convention = convention_for(version, self._conventions)
                if convention is None or ClientKind.DESIGNER not in convention.executables:
                    problems.append("версия платформы не определена")
                else:
                    executable = (
                        installation.path
                        / convention.bin_dir
                        / convention.executables[ClientKind.DESIGNER]
                    )
        try:
            self._reject_ambiguous_name(item)
        except LaunchError:
            problems.append("имя базы в списке не единственное")
        data = self._user.get(key, BaseUserData())
        login = (data.login or "").strip() or None
        user = (data.repository_user or "").strip() or None
        # Отказ диспетчера — не проблема готовности: пароль остаётся `None`, его  # noqa: RUF003
        # можно ввести при запуске (`store_unavailable` объясняет, почему его нет).  # noqa: RUF003
        store_unavailable = False
        secrets: dict[str, str | None] = {}
        for owner, secret_key in ((login, key), (user, repository_key(key))):
            if owner is None:
                continue
            try:
                secrets[secret_key] = self._credentials.read(secret_key)
            except CredentialBackendError:
                store_unavailable = True
        password = secrets.get(key)
        repository_password = secrets.get(repository_key(key))
        return BatchTarget(
            key=key,
            name=item.name,
            group=group,
            executable=executable,
            version=version,
            login=login,
            password=password,
            repository_address=(data.repository_address or "").strip() or None,
            repository_user=user,
            repository_password=repository_password,
            file_path=file_path_of(item),
            problems=tuple(problems),
            store_unavailable=store_unavailable,
        )

    def designer_params_of(self, key: str) -> str | None:
        """Строка параметров Конфигуратора записи (спека v4, §4.3) или `None`."""
        return self._user.get(key, BaseUserData()).designer_params

    def set_designer_params(self, key: str, params: str | None) -> None:
        """Записать строку параметров Конфигуратора в наши данные (`bases.json`).

        Пустая строка — `None`: «параметров нет». Перевод строки и другие управляющие
        символы (кроме табуляции) отвергаются: строка уходит в argv одной строкой. `.v8i`
        не трогается вовсе.

        Строка с паролем не сохраняется (решение заказчика 09.11.2026, финальное ревью
        блока 1, F1): `bases.json` — наш файл, пароль в нём лежал бы открытым текстом
        (инвариант 5). Признак — тот же, что у отказа набора: `contains_secret_arguments`
        (`/P`, `/WSP`, `/ModifyPassword`, `/AccessToken`, `/UC`, `-PPwd`, `-pwd`; строка
        с незакрытой кавычкой — тоже, границы токенов недостоверны, — но со своим текстом,
        приёмка 21.11.2026, Р2). Защита здесь, — чтобы никакой путь UI её не обошёл.
        Текст отказа значения не повторяет.
        """  # noqa: RUF002
        item = self._item(key)
        if item.is_group:
            raise InvalidRequestError(f"«{item.name}» — группа, у неё нет параметров запуска")  # noqa: RUF001
        if params is not None and _has_control_chars(params):
            raise InvalidRequestError(
                "Параметры Конфигуратора не могут содержать перевод строки "
                "и другие управляющие символы"
            )
        if params is not None and has_unclosed_quote(params):
            raise InvalidRequestError(DESIGNER_QUOTE_REFUSAL)
        if params is not None and contains_secret_arguments(params):
            raise InvalidRequestError(DESIGNER_SECRET_REFUSAL)
        normalized = params if params is not None and params.strip() else None
        try:
            self._store_user(
                set_designer_params(self._user, key, normalized),
                "Не удалось сохранить параметры Конфигуратора",  # noqa: RUF001
            )
        finally:
            self._rebuild()

    def launch(
        self,
        key: str,
        forced: LaunchTarget | None = None,
        *,
        elevated: bool = False,
        ask_login: bool = False,
        once: str | None = None,
    ) -> LaunchOutcome:
        if elevated and ask_login:
            # Решение заказчика 03.11.2026 (спека 3.2.5, §1, п. 4): режимы не
            # сочетаются; UI такого вызова не делает — это ошибка программиста.
            raise ValueError("Запуск от имени администратора и с запросом входа не сочетаются")  # noqa: RUF001
        if once is not None and once.strip() and (elevated or ask_login):
            # Спека v4, §4.5: разовые параметры не сочетаются с повышением и входом;  # noqa: RUF003
            # UI такого вызова не делает — это ошибка программиста.
            raise ValueError(
                "Разовые параметры не сочетаются с запуском от имени администратора "  # noqa: RUF001
                "и с запросом входа"  # noqa: RUF001
            )
        if self._installations is None:
            # Спека T-04.6, §3.4: запуск до готовности обязан отказать
            # вежливо, а не молча идти дальше с пустым списком установок —  # noqa: RUF003
            # тогда platform_1c решил бы, что версий действительно нет,
            # и соврал бы пользователю тем же способом, какого ради
            # installations_pending и заведено отдельно от пустого списка.
            raise LaunchError(
                "Обнаружение установленных версий платформы ещё не завершено — "
                "повторите попытку через несколько секунд"
            )
        item = self._item(key)
        if elevated and item.kind is ConnectKind.WEB:
            # T-31: повышать браузер бессмысленно, а клиент к ws= — не тот случай,  # noqa: RUF003
            # о котором просили (спека 3.2.4 ч. 1, §4.1).  # noqa: RUF003
            raise LaunchError(
                f"Для «{item.name}» запуск от имени администратора не предусмотрен: "
                "база опубликована на веб-сервере"
            )
        if ask_login and item.kind is ConnectKind.WEB:
            # T-32: вход в веб-базу решает веб-сервер, /WA- его не касается  # noqa: RUF003
            # (спека 3.2.5, §3.1).
            raise LaunchError(
                f"Для «{item.name}» запуск с запросом входа не предусмотрен: "  # noqa: RUF001
                "база опубликована на веб-сервере"
            )
        if forced is not LaunchTarget.BROWSER:
            # Разовый «Открыть в браузере» — единственный канал, где имя базы
            # не участвует вовсе: открывается URL из `ws`, `/IBName` не строится
            # (финальное ревью ветки, I5). См. `_reject_ambiguous_name`.
            self._reject_ambiguous_name(item)
        credentials: Credentials | None
        store_failure: CredentialStoreError | None
        if ask_login:
            # T-32: хранилище не читается вовсе — сохранённые логин и пароль
            # не уходят в argv и не меняются, а сбой хранилища этот запуск  # noqa: RUF003
            # не ломает (спека 3.2.5, §3.2).
            credentials, store_failure = None, None
        else:
            credentials, store_failure = self._credentials_for_launch(key)
        extra_parts: list[str] = []
        if forced is LaunchTarget.DESIGNER:
            designer = (self._user.get(key, BaseUserData()).designer_params or "").strip()
            if designer:
                # bases.json правится и руками: инвариант сеттера на загрузке не
                # гарантирован. Текст ошибки значения не повторяет.
                if _has_control_chars(designer):
                    raise LaunchError(
                        "Строка параметров Конфигуратора содержит перевод строки или другой "
                        "управляющий символ — исправьте её в свойствах базы."
                    )
                extra_parts.append(designer)
        if once is not None and once.strip():
            if _has_control_chars(once):
                raise LaunchError(
                    "Разовые параметры содержат перевод строки или другой управляющий "
                    "символ — запуск отменён."
                )
            extra_parts.append(once.strip())
        try:
            outcome = launch_infobase(
                item,
                installations=self._installations,
                cfg_rules=self._cfg_rules,
                conventions=self._conventions,
                default_app=self._default_app,
                web_default_is_browser=self._web_default_is_browser,
                forced_target=forced,
                spawn=self._spawn_elevated if elevated else self._spawn,
                open_url=self._open_url,
                credentials=credentials,
                deny_os_auth=ask_login,
                extra_params=" ".join(extra_parts) or None,
            )
        except ElevationDeclinedError as error:
            # Отказ в окне UAC — до записи времени: база не запущена.
            raise LaunchDeclinedError(
                f"«{item.name}»: отказ в повышении прав"
            ) from error
        client = outcome.client.value if outcome.client else "browser"
        # Процесс уже порождён, и об этом сказано прямо в тексте: отказ  # noqa: RUF003
        # записи наших данных — не отказ запуска, и сообщение обязано
        # отличать одно от другого (иначе пользователь решит, что база
        # не запустилась, и нажмёт ещё раз).
        try:
            self._store_user(
                record_launch(self._user, key, client, self._now()),
                "База запущена, но не удалось запомнить время запуска",
            )
        finally:
            self._rebuild()
        if store_failure is not None:
            raise store_failure
        return outcome

    def _credentials_for_launch(
        self, key: str
    ) -> tuple[Credentials | None, CredentialStoreError | None]:
        """Учётные данные для запуска. Отказ хранилища — не отказ запуска:
        клиент запускается без них, платформа спросит сама, а ошибка
        поднимается ПОСЛЕ порождения процесса (спека §8)."""  # noqa: RUF002
        # Нормализация на чтении, а не только на записи: файл bases.json  # noqa: RUF003
        # правится и руками, а `Credentials("")` отвергается доменом  # noqa: RUF003
        # (`__post_init__`, задача 3) — на запуске это было бы необработанным
        # ValueError вместо честного «логина нет».
        login = (self._user.get(key, BaseUserData()).login or "").strip() or None
        if login is None:
            return None, None
        try:
            password = self._credentials.read(key)
        except CredentialBackendError as error:
            return Credentials(login), CredentialStoreError(
                f"Пароль не прочитан, запуск без него: {error}"
            )
        return Credentials(login, password), None

    def find_by_name(self, name: str) -> str:
        """Ключ записи по имени базы. Сравнение без учёта регистра.

        [Ф] T-05.3: платформа ищет имя регистронезависимо и считает дублями
        имена, различающиеся только регистром. Ярлык несёт имя, а не ключ:
        ключ меняется, когда записи дописывается `ID`, и ярлык сломался бы
        от первой же правки записи через нас.

        Группы отсеиваются: имя группы в списке есть, но запускать в ней
        нечего, и без отсева отказ пришёл бы позже и не по делу.
        """  # noqa: RUF002
        wanted = name.casefold()
        found = [
            item
            for item in self._items
            if not item.is_group and item.name.casefold() == wanted
        ]
        if not found:
            raise UnknownItemError(f"Базы с именем «{name}» нет в списке")  # noqa: RUF001
        keys = {item.key for item in found}
        if len(keys) > 1:
            raise LaunchError(
                f"Имя «{name}» в списке не единственное ({len(keys)} "
                f"{_records_word(len(keys))}): запуск по имени неоднозначен"
            )
        return found[0].key

    def _item(self, key: str) -> InfobaseItem:
        for item in self._items:
            if item.key == key:
                return item
        # Ключ может быть суррогатом с хешем строки соединения — в сообщение  # noqa: RUF003
        # он не идёт (инвариант 5).
        raise UnknownItemError(
            "Записи с таким ключом нет в списке — возможно, файл изменился "  # noqa: RUF001
            "извне. Обновите список и повторите"
        )

    def _find(self, key: str) -> InfobaseItem | None:
        return next((item for item in self._items if item.key == key), None)

    def _reject_common(self, key: str) -> None:
        """Отсеять запись из общего списка до попытки записи в файл.

        Общие списки — источник только для чтения (дизайн плана 3, §5:
        «Запись в общий список — ошибка программиста, проверяется на границе
        операции»). Без этой проверки `remove` молча не делает ничего,
        а `update` врёт про удалённую извне запись.

        Неизвестный ключ здесь не отвергается: `REMOVE` обязан оставаться
        идемпотентным, а `UPDATE` по-настоящему исчезнувшей цели даёт
        `TargetGoneError` — и это правда.
        """  # noqa: RUF002
        item = self._find(key)
        if item is not None and item.source is InfobaseSource.COMMON:
            raise ReadOnlySourceError(
                f"«{item.name}» — запись из общего списка, он доступен только для чтения"
            )

    def _reject_ambiguous_name(self, item: InfobaseItem) -> None:
        """Отказать в запуске, если имя базы в списке не единственное.

        Запуск идёт по `/IBName`, а платформа при нескольких базах с таким
        именем прекращает запуск с «Не уникальное имя информационной базы»
        (скил platform-launch, [Ф] T-05.3). Дубли имён формат допускает,
        и `ADD` их разрешает (дизайн плана 3, §5), поэтому диагностику даёт
        запуск — заранее и своими словами, а не отказом клиента 1С.

        Считаются и записи из общих списков — [Ф] T-05.2: `/IBName` видит
        базы из `CommonInfoBases` наравне с пользовательскими. Считаются
        при этом различные ключи привязки, а не строки: [Ф] скил
        v8i-format — `ID` есть ключ идентичности и слияния, поэтому две
        строки с одним `ID` (одна база, попавшая и в пользовательский,
        и в общий список) — одна база, а не две.

        Сравнение имён — без учёта регистра: [Ф] T-05.3 — платформа
        считает дублями и имена, различающиеся только регистром, а поиск
        по `/IBName` регистронезависим.

        Веб-базы проверяются наравне с остальными: с вехи v2.3 они
        запускаются тонким клиентом по `/IBName` (**[Ф]** T-05.16 № 1), и имя
        в этом пути участвует. Прежнее обоснование («открывается браузером
        по адресу из `ws`») перестало быть верным вместе со сменой пути
        запуска.

        Единственное исключение делает **вызывающий** (`launch`): разовый
        `LaunchTarget.BROWSER`. Это единственный канал, где имя базы не
        участвует вовсе — открывается URL из `ws`, `/IBName` не строится, —
        и отказ с советом «переименуйте одну из баз» предлагал бы править
        файл списка ради операции, которой имя безразлично (финальное ревью
        ветки, I5: воспроизведено запуском). Запись, которая уходит в браузер
        не разовым выбором, а `App=WebClient` или настройкой, проверку
        по-прежнему проходит: ветвление по итогу `choose_launch_plan` развело
        бы проверку с местом, где канал выбирается, а разовый выбор известен
        уже здесь, до всякого плана.
        """  # noqa: RUF002
        name = item.name.casefold()
        rivals = [
            other
            for other in self._items
            if not other.is_group and other.name.casefold() == name and other.key != item.key
        ]
        if not rivals:
            return
        count = len({other.key for other in rivals}) + 1
        if any(other.source is InfobaseSource.COMMON for other in rivals):
            # Совет «переименуйте одну из баз» здесь невыполним: общий список
            # доступен только для чтения, и `_reject_common` правку запретит.
            advice = (
                "часть записей пришла из общего списка, он доступен только "
                "для чтения — переименовать можно только запись своего списка"
            )
        else:
            advice = "переименуйте одну из баз"
        raise LaunchError(
            f"Имя «{item.name}» в списке не единственное "
            f"({count} {_records_word(count)}): запуск по имени неоднозначен, {advice}"
        )

    def _store_user(self, updated: Mapping[str, BaseUserData], what: str) -> None:
        """Заменить наши данные и записать их. Отказ ФС — ошибка слоя services.

        Отказ записи откатывает и состояние в памяти. Иначе экран разошёлся
        бы с файлом: модель строится по `self._user`, и звёздочка осталась бы
        гореть на записи, которой в файле нет, — а `BasesView` зовёт
        `rebuild()` **после** `try`, то есть даже показав ошибку, показал бы
        и несуществующее избранное.

        Голая `OSError` наружу не выходит (докстринг `errors.py`): по ней
        не отличить нашу диагностику от случайной ошибки в чужом коде,
        и все ловцы слоя представления её пропускали.
        """  # noqa: RUF002
        previous = self._user
        self._user = updated
        try:
            save_user_data(self.paths.user_data, self._user)
        except OSError as error:
            self._user = previous
            raise UserDataWriteError(f"{what} ({self.paths.user_data}): {error}") from error

    def _move_secret(self, rekey_from: str, new_key: str, what: str = "пароль") -> str | None:
        """Перевесить секрет со старого ключа на новый. `None` — сделано.

        Строка-результат вместо исключения: `_write` собирает отказы
        нескольких подсистем в одно сообщение, и «первое исключение съедает
        остальные» здесь как раз тот дефект, который чинится (финальное
        ревью, I2).

        Три исхода различаются по факту, а не сливаются в «не удалось
        перенести пароль»:

        * отказ `read` — неизвестно даже, был ли у записи пароль; это отказ
          ПРОВЕРКИ. Утверждать, что перенос не удался, значит выдумывать
          несуществующий секрет;
        * отказ `write` — секрет остался под старым ключом и никуда
          не делся;
        * отказ `delete` после успешного `write` — секрет уже под новым
          ключом, но старая копия жива. Это не безобидный мусор:
          суррогатный ключ записи без `ID` унаследует следующая запись
          с тем же именем и строкой соединения — вместе с чужим паролем.
          Поэтому сообщение называет запись хранилища целиком: ключ
          привязки секретом не является (докстринг `errors.py`), а без
          него уборка вручную невозможна.
        """  # noqa: RUF002
        try:
            secret = self._credentials.read(rekey_from)
        except CredentialBackendError as error:
            return (
                "Запись изменена, но не удалось проверить, есть ли у неё "  # noqa: RUF001
                f"сохранённый {what}: {error}"
            )
        if secret is None:
            return None
        try:
            self._credentials.write(new_key, secret)
        except CredentialBackendError as error:
            return (
                f"Запись изменена, но {what} не перенесён — он остался "
                f"у прежней записи: {error}"  # noqa: RUF001
            )
        try:
            self._credentials.delete(rekey_from)
        except CredentialBackendError as error:
            return (
                f"Запись изменена, {what} перенесён, но старая копия осталась "
                "в диспетчере учётных данных — удалите запись "
                f"`{SERVICE}/{rekey_from}` вручную: {error}"
            )
        return None

    def _write(
        self, patch: Patch, rekey_from: str | None = None, *, move_secret: bool = False
    ) -> PatchResult:
        """Применить патч к `.v8i` и привести к новому ключу наши данные.

        `move_secret` — отдельный флаг, а не следствие `rekey_from`
        (финальное ревью, I1): по ветке rekey ходит и `update_group`, ключ
        группы без `ID` меняется при переименовании. У группы пароля быть
        не может по построению (`set_credentials` отказывает группе), но
        `read` всё равно спрашивал хранилище — и на машине без Credential
        Manager переименование группы кончалось сообщением про пароль.
        """  # noqa: RUF002
        new_id = self._new_id()
        payload, result = write_patch(self.paths.ibases, patch, new_id)
        # Наши данные перевешиваются только тогда, когда ключ цели фактически
        # сменился. Прежнее условие смотрело на префикс исходного ключа
        # и перевешивало историю на несуществующий id:, когда ID записи
        # не дописывался.
        #
        # Отказ записи наших данных не отменяет уже состоявшуюся запись
        # в .v8i: файл списка изменён, и состояние (`_raw`, `_rebuild`)
        # обязано это отразить — иначе экран остался бы на старом содержимом,
        # которого в файле уже нет. Поэтому ошибка придерживается и поднимается
        # ПОСЛЕ приведения состояния в порядок, а не вместо него.  # noqa: RUF003
        #
        # Отказы копятся списком, а не первым победившим: `failure = failure  # noqa: RUF003
        # or …` прятал отказ хранилища за отказом `bases.json` целиком —
        # пользователь узнавал про избранное и не узнавал про пароль.
        failures: list[str] = []
        data_failed = False
        if rekey_from is not None and result.key is not None and result.key != rekey_from:
            try:
                self._store_user(
                    rekey(self._user, rekey_from, result.key),
                    "Запись изменена, но не удалось перенести на неё избранное "
                    "и историю запусков",
                )
            except UserDataWriteError as error:
                failures.append(str(error))
                data_failed = True
            if move_secret:
                for old, new, what in (
                    (rekey_from, result.key, "пароль"),
                    (repository_key(rekey_from), repository_key(result.key), "пароль хранилища"),
                ):
                    store_failure = self._move_secret(old, new, what)
                    if store_failure is not None:
                        failures.append(store_failure)
        self._raw = payload
        self._rebuild()
        if failures:
            text = "; ".join(failures)
            # Тип по тому, что отказало: наши данные (в том числе вместе
            # с хранилищем) — `UserDataWriteError`, только хранилище —  # noqa: RUF003
            # `CredentialStoreError`. Оба ловятся как `ServicesError`, но  # noqa: RUF003
            # различаются там, где реакция разная.
            if data_failed:
                raise UserDataWriteError(text)
            raise CredentialStoreError(text)
        return result

    def _reload(self) -> None:
        self._raw = self._read_bytes()
        self._rebuild()

    def _rebuild(self) -> None:
        # common_items_from_data разбирает уже лежащий в памяти снимок
        # (self._common_data), а не читает общие списки заново — вызывается  # noqa: RUF003
        # эта перестройка при каждой правке пользовательского списка,
        # и повторное чтение сети на каждый чих было бы регрессией
        # к дефекту, который спека T-04.6 §3.3 закрывает.
        document = parse_v8i(self._raw)
        items = items_from_document(document, InfobaseSource.USER, self._user)
        common, errors = common_items_from_data(self._common_data, self._user)
        self._items = dedupe(items, common)
        self._common_errors = errors

    def _read_bytes(self) -> bytes:
        try:
            return self.paths.ibases.read_bytes()
        except FileNotFoundError:
            return b""
