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
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from onecstarter.config.v8i import parse_v8i
from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import (
    ClientConvention,
    Credentials,
    LaunchCommand,
    LaunchTarget,
)
from onecstarter.domain.version import Installation
from onecstarter.platform_1c.process import spawn as spawn_process
from onecstarter.security.credentials import SERVICE, CredentialBackendError, CredentialStore
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
    LaunchError,
    ReadOnlySourceError,
    ServicesError,
    UnknownItemError,
    UserDataWriteError,
)
from onecstarter.services.groups import GroupPatch, GroupPatchKind, GroupRemoval
from onecstarter.services.launch import LaunchOutcome, launch_infobase
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.user_data import (
    BaseUserData,
    load_user_data,
    record_launch,
    rekey,
    save_user_data,
    set_favorite,
    set_login,
)
from onecstarter.services.writer import write_patch


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
        open_url: Callable[[str], bool] = webbrowser.open,
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
        try:
            self._credentials.delete(key)
        except CredentialBackendError as error:
            raise CredentialStoreError(
                f"Запись удалена, но пароль в диспетчере учётных данных остался: {error}"
            ) from error
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
            try:
                self._credentials.delete(removed)
            except CredentialBackendError as error:
                failed.append(f"{removed}: {error}")
        if failed:
            raise CredentialStoreError(
                "Группа удалена, но пароли её записей остались в диспетчере "
                "учётных данных: " + "; ".join(failed)
            )
        return applied

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

    def launch(self, key: str, forced: LaunchTarget | None = None) -> LaunchOutcome:
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
        self._reject_ambiguous_name(item)
        credentials, store_failure = self._credentials_for_launch(key)
        outcome = launch_infobase(
            item,
            installations=self._installations,
            cfg_rules=self._cfg_rules,
            conventions=self._conventions,
            default_app=self._default_app,
            web_default_is_browser=self._web_default_is_browser,
            forced_target=forced,
            spawn=self._spawn,
            open_url=self._open_url,
            credentials=credentials,
        )
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
        по `/IBName` регистронезависим. Веб-база не проверяется вовсе:
        она открывается браузером по адресу из `ws`, имя в этом пути
        не участвует.
        """  # noqa: RUF002
        if item.kind is ConnectKind.WEB:
            return
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

    def _move_secret(self, rekey_from: str, new_key: str) -> str | None:
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
                f"сохранённый пароль: {error}"
            )
        if secret is None:
            return None
        try:
            self._credentials.write(new_key, secret)
        except CredentialBackendError as error:
            return (
                "Запись изменена, но пароль не перенесён — он остался "
                f"у прежней записи: {error}"  # noqa: RUF001
            )
        try:
            self._credentials.delete(rekey_from)
        except CredentialBackendError as error:
            return (
                "Запись изменена, пароль перенесён, но старая копия осталась "
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
                store_failure = self._move_secret(rekey_from, result.key)
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
