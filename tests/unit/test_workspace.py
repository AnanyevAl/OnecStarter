import codecs
import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import pytest

from onecstarter.config.v8i import V8iSection, parse_v8i
from onecstarter.domain.connect import ConnectKind
from onecstarter.domain.launch import (
    ClientConvention,
    ClientKind,
    LaunchCommand,
    LaunchTarget,
)
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.security.credentials import (
    CredentialBackendError,
    CredentialStore,
    MemoryStore,
    repository_key,
)
from onecstarter.services.catalog import read_common_lists
from onecstarter.services.errors import (
    CredentialStoreError,
    InvalidRequestError,
    LaunchDeclinedError,
    LaunchError,
    ReadOnlySourceError,
    ServicesError,
    UnknownItemError,
    UserDataUnavailableError,
    UserDataWriteError,
)
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.launch import LaunchKind
from onecstarter.services.model import InfobaseSource, binding_key, group_binding_key
from onecstarter.services.user_data import set_designer_params, set_login
from onecstarter.services.workspace import (
    DESIGNER_QUOTE_REFUSAL,
    RepositorySettings,
    Workspace,
    WorkspacePaths,
    _records_word,
)

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
STAMP = "2026-08-04T07:12:44+00:00"


def _no_elevation(command: LaunchCommand) -> int:
    raise AssertionError(f"повышение прав не ожидалось: {command.command_line}")


def _raw_workspace(
    tmp_path: Path,
    calls: list[LaunchCommand] | None = None,
    cfg_paths: tuple[Path, ...] = (),
    installations: Sequence[Installation] | None = INSTALLED,
    store: CredentialStore | None = None,
    spawn_elevated: Callable[[LaunchCommand], int] | None = None,
) -> Workspace:
    """Собрать Workspace как есть — без снимка общих списков.

    Низкоуровневый хелпер для тестов, которым важно именно состояние
    «сразу после конструктора»: pending общих списков и/или pending
    установок (§3.3–3.4 спеки T-04.6). `_workspace` ниже — обёртка над
    этим хелпером для всех остальных тестов, которым не до тонкостей
    и нужен уже «загруженный» Workspace. `store` — хранилище паролей;
    по умолчанию `MemoryStore()`, настоящий Credential Manager машины
    тестами не трогается (задача 4 вехи v2.2).
    """  # noqa: RUF002
    ibases = tmp_path / "ibases.v8i"
    if not ibases.exists():
        shutil.copyfile(FIXTURE, ibases)
    recorded = calls if calls is not None else []

    def fake_spawn(command: LaunchCommand) -> int:
        recorded.append(command)
        return 7

    return Workspace(
        WorkspacePaths(ibases=ibases, user_data=tmp_path / "bases.json", cfg_paths=cfg_paths),
        installations=installations,
        conventions=CONVENTIONS,
        cfg_rules=[],
        default_app=None,
        spawn=fake_spawn,
        spawn_elevated=spawn_elevated or _no_elevation,
        open_url=lambda url: True,
        now=lambda: datetime.fromisoformat(STAMP),
        new_id=lambda: "99999999-9999-9999-9999-999999999999",
        credentials=store if store is not None else MemoryStore(),
    )


def _workspace(
    tmp_path: Path,
    calls: list[LaunchCommand] | None = None,
    cfg_paths: tuple[Path, ...] = (),
    store: CredentialStore | None = None,
) -> Workspace:
    """Собрать Workspace и сразу применить снимок общих списков.

    Большинству тестов файла не важно, что применение снимка — теперь
    отдельный шаг (§3.3 спеки T-04.6, задача T-02 поставки): они писались
    до разделения конструктора и `apply_common_lists` и ждут уже
    «загруженный» мир. Тесты, которым важен именно момент до применения
    снимка (pending), используют `_raw_workspace` напрямую.
    """
    workspace = _raw_workspace(tmp_path, calls, cfg_paths, store=store)
    workspace.apply_common_lists(read_common_lists(list(cfg_paths)))
    return workspace


def test_items_are_loaded_from_file(tmp_path: Path) -> None:
    assert len(_workspace(tmp_path).items()) == 9


# -- T-02 поставки: снимок общих списков и pending-установки ----------------
#
# Спека T-04.6, §3.3: конструктор Workspace не читает общие списки и не
# получает установки платформы — обе фоновые задачи стартуют параллельно  # noqa: RUF003
# показу окна, а их результат приходит позже через apply_common_lists()/  # noqa: RUF003
# set_installations(). §3.4: пустой список установок и «обнаружение ещё
# не завершено» — разные состояния, второе выражается через None.


def test_constructor_does_not_read_common_lists(tmp_path: Path) -> None:
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Общая база]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'.encode()
    )
    cfg_paths = _with_common_list(tmp_path, shared)
    workspace = _raw_workspace(tmp_path, cfg_paths=cfg_paths)

    names = {item.name for item in workspace.items()}
    assert "Общая база" not in names  # снимок ещё не применён
    assert workspace.common_lists_pending

    workspace.apply_common_lists(read_common_lists(list(cfg_paths)))
    names = {item.name for item in workspace.items()}
    assert "Общая база" in names
    assert not workspace.common_lists_pending


def test_rebuild_does_not_reread_common_lists_from_disk(tmp_path: Path) -> None:
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Общая база]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'.encode()
    )
    cfg_paths = _with_common_list(tmp_path, shared)
    workspace = _raw_workspace(tmp_path, cfg_paths=cfg_paths)
    workspace.apply_common_lists(read_common_lists(list(cfg_paths)))

    shared.write_bytes(b"")  # источник изменился на диске
    workspace.set_favorite("id:44444444-4444-4444-4444-444444444444", True)

    names = {item.name for item in workspace.items()}
    assert "Общая база" in names  # снимок жив, диск не перечитан


def test_installations_none_means_pending_and_launch_refuses(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls, installations=None)
    assert workspace.installations_pending

    key = "id:44444444-4444-4444-4444-444444444444"
    with pytest.raises(LaunchError) as excinfo:
        workspace.launch(key)
    assert "не завершено" in str(excinfo.value)
    assert not calls

    workspace.set_installations(INSTALLED)
    assert not workspace.installations_pending
    workspace.launch(key)
    assert len(calls) == 1


def test_empty_installations_are_not_pending(tmp_path: Path) -> None:
    workspace = _raw_workspace(tmp_path, installations=[])
    assert not workspace.installations_pending


def test_reload_detects_external_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert not workspace.reload_if_changed()
    path = workspace.paths.ibases
    path.write_bytes(path.read_bytes() + "[Чужая]\r\nConnect=File=\"C:\\B\";\r\n".encode())
    assert workspace.reload_if_changed()
    assert len(workspace.items()) == 10


def test_reload_survives_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Отказ чтения — не изменение: состояние прежнее, попытка повторяема.

    Штатный стартер перезаписывает `ibases.v8i` целиком, и на Windows чтение
    в этот момент может упасть отказом доступа. `reload_if_changed` зовёт
    watcher из Qt-слота: исключение оттуда пользователю не показывается
    (в оконной сборке консоли нет), поэтому отказ обязан быть тихим
    и обратимым, а не терять список и не ронять обновление навсегда.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    before = workspace.items()
    path = workspace.paths.ibases
    path.write_bytes(path.read_bytes() + '[Чужая]\r\nConnect=File="C:\\B";\r\n'.encode())
    original = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self == path:
            raise PermissionError(13, "файл занят другим процессом")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    assert not workspace.reload_if_changed()
    assert workspace.items() == before

    # Файл освободился — следующее событие watcher'а подхватывает правку.  # noqa: RUF003
    monkeypatch.undo()
    assert workspace.reload_if_changed()
    assert len(workspace.items()) == len(before) + 1


def test_own_write_does_not_look_like_external_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Новая", 'File="C:\\Bases\\New";')
    assert not workspace.reload_if_changed()
    assert any(item.name == "Новая" for item in workspace.items())


def test_favorite_survives_reload(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = "id:44444444-4444-4444-4444-444444444444"
    workspace.set_favorite(key, True)
    workspace.reload_if_changed()
    assert next(item for item in workspace.items() if item.key == key).favorite


def test_update_of_section_without_id_rekeys_user_data(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    old_key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    workspace.set_favorite(old_key, True)
    workspace.update_infobase(old_key, {"Version": "8.3.25"})
    new_key = "id:99999999-9999-9999-9999-999999999999"
    item = next(item for item in workspace.items() if item.key == new_key)
    assert item.favorite


def test_set_default_app_reaches_launch(tmp_path: Path) -> None:
    """Смена клиента по умолчанию влияет на следующий запуск — без пересборки.

    Проверяется поведение (какой exe в команде), а не хранимое поле:
    правило «тест проверяет поведение, а не намерение».
    """  # noqa: RUF002
    (tmp_path / "ibases.v8i").write_bytes(
        '[БезКлиента]\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = workspace.items()[0].key

    workspace.launch(key)
    assert calls[-1].executable.name == "1cv8c.exe"  # тонкий — как и раньше

    workspace.set_default_app("ThickClient")
    workspace.launch(key)
    assert calls[-1].executable.name == "1cv8.exe"  # настройка доехала
    assert workspace.default_app == "ThickClient"


def test_launch_records_history(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls)
    key = "id:44444444-4444-4444-4444-444444444444"
    workspace.launch(key)
    item = next(item for item in workspace.items() if item.key == key)
    assert item.launch_count == 1
    assert item.last_launched_at is not None
    assert len(calls) == 1


def test_launch_of_unknown_key_raises(tmp_path: Path) -> None:
    with pytest.raises(UnknownItemError):
        _workspace(tmp_path).launch("id:нет такого")


def test_unknown_key_message_offers_a_way_out(tmp_path: Path) -> None:
    """Сообщение обязано говорить, что делать, а не только что случилось.

    Ключ исчезает при внешней правке файла — штатным стартером, например.
    Пользователю нужно знать, что список надо перечитать.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    with pytest.raises(UnknownItemError) as info:
        workspace.launch("id:нет-такого")
    assert "обновите список" in str(info.value).casefold()


def test_remove_drops_section(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.remove_infobase("id:44444444-4444-4444-4444-444444444444")
    assert not any(item.name == "Демо Бухгалтерия" for item in workspace.items())


def test_add_returns_key_of_new_record(tmp_path: Path) -> None:
    # Искать новую запись по имени нельзя: имена в списке не уникальны.
    workspace = _workspace(tmp_path)
    key = workspace.add_infobase("Новая", 'File="C:\\Bases\\New";')
    assert next(item for item in workspace.items() if item.key == key).name == "Новая"


def _raw_section(tmp_path: Path, name: str) -> V8iSection:
    """Секция ровно как она лежит в файле — не модель `Workspace` в памяти.

    Перечитывает `ibases.v8i` с диска и разбирает заново, независимо от
    состояния `Workspace`: расхождение между записанным файлом и объектом
    в памяти (в любую сторону) — именно то, что обязана ловить проверка
    «версия и клиент не заданы по умолчанию не пишутся в чужой файл».
    """  # noqa: RUF002
    document = parse_v8i((tmp_path / "ibases.v8i").read_bytes())
    return next(section for section in document.sections if section.name == name)


def test_add_infobase_writes_version_and_app_when_given(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    key = workspace.add_infobase(
        "Новая", 'File="D:\\Bases\\New";', "/", version="8.3.25.1633", app="ThinClient"
    )

    item = next(i for i in workspace.items() if i.key == key)
    assert item.requested_version == "8.3.25.1633"
    assert item.app == "ThinClient"

    section = _raw_section(tmp_path, "Новая")
    assert section.get("Version") == "8.3.25.1633"
    assert section.get("App") == "ThinClient"


@pytest.mark.parametrize(
    "version, app",
    [
        pytest.param(None, None, id="not-given"),
        pytest.param("", "", id="empty-string"),
    ],
)
def test_add_infobase_writes_neither_key_when_version_and_app_are_falsy(
    tmp_path: Path, version: str | None, app: str | None
) -> None:
    """«Как установлено» и «Авто» молчат — ни отсутствие, ни пустая строка не пишутся.

    Пустая строка (`version=""`/`app=""`) сегодня недостижима через UI —
    комбобоксы диалога добавления кладут `None`, не `""` — но метод
    `add_infobase` публичный, и guard `if version:`/`if app:` в нём существует
    именно ради этого случая: нижний рубеж `_apply_add` (services/edit.py)
    отбрасывает только `None`, а пустая строка ушла бы в чужой `.v8i` как
    `Version=`/`App=` — платформа читает такой ключ иначе, чем его отсутствие.
    Находка финального ревью ветки v2.1: случай был закреплён только разовой
    мутацией без постоянного теста.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)

    workspace.add_infobase("Новая", 'File="D:\\Bases\\New";', "/", version=version, app=app)

    section = _raw_section(tmp_path, "Новая")
    assert section.get("Version") is None
    assert section.get("App") is None


def test_duplicate_name_makes_launch_ambiguous(tmp_path: Path) -> None:
    """Замерено: вторая база с существующим именем делает незапускаемыми обе.
    Платформа при нескольких базах с одним именем прекращает запуск по
    `/IBName` с ошибкой (скил platform-launch) — говорим об этом заранее.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Демо Бухгалтерия", 'File="C:\\Bases\\Dup";')
    with pytest.raises(LaunchError) as error:
        workspace.launch("id:44444444-4444-4444-4444-444444444444")
    assert "Демо Бухгалтерия" in str(error.value)
    assert "(2 записи)" in str(error.value)
    assert "переименуйте одну из баз" in str(error.value)


def test_names_differing_only_in_case_are_duplicates_too(tmp_path: Path) -> None:
    """[Ф] T-05.3: платформа считает дублями имена, различающиеся только
    регистром, — запуск по `/IBName` прекращается с «Не уникальное имя
    информационной базы». Сравниваем так же, иначе пропускаем заведомо
    обречённый запуск.

    Вторая база добавляется к существующей из фикстуры, а не парой
    `add_infobase`: стаб `new_id` в `_workspace` выдаёт один и тот же
    GUID, и две добавленные записи слились бы по ключу привязки.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    workspace.add_infobase("демо бухгалтерия", 'File="C:\\Bases\\Dup";')
    with pytest.raises(LaunchError) as error:
        workspace.launch("id:44444444-4444-4444-4444-444444444444")
    assert "не единственное" in str(error.value)


# -- задача 17: поиск записи по имени базы (режим --ib-name) ---------------


def test_find_by_name_returns_binding_key(tmp_path: Path) -> None:
    """Ярлык несёт имя базы, а не ключ, — `find_by_name` переводит одно в другое.

    Ключ в ярлык не годится: он меняется, когда записи дописывается `ID`,
    и ярлык сломался бы от первой же правки записи через нас.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    assert workspace.find_by_name("Демо Бухгалтерия") == (
        "id:44444444-4444-4444-4444-444444444444"
    )


def test_find_by_name_ignores_case(tmp_path: Path) -> None:
    """[Ф] T-05.3: платформа ищет имя базы регистронезависимо — ищем так же.

    Иначе наш поиск разошёлся бы с платформой: ярлык с именем в другом
    регистре у неё сработал бы, а у нас — нет.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    assert workspace.find_by_name("дЕмо бУхгалтерия") == (
        "id:44444444-4444-4444-4444-444444444444"
    )


def test_find_by_name_rejects_unknown_name(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(UnknownItemError) as error:
        workspace.find_by_name("Такой базы нет")
    assert "Такой базы нет" in str(error.value)


def test_find_by_name_skips_groups(tmp_path: Path) -> None:
    """Группа — не база: ярлык на неё запускать нечего.

    Имя группы в списке есть, и без явного отсева поиск вернул бы её ключ,
    а запуск упал бы позже и не по делу.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    assert any(item.name == "Клиенты" and item.is_group for item in workspace.items())
    with pytest.raises(UnknownItemError):
        workspace.find_by_name("Клиенты")


def test_find_by_name_rejects_ambiguous_name(tmp_path: Path) -> None:
    """Дубль имени — отказ до запуска, той же причины, что и у `launch`."""  # noqa: RUF002
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Демо Бухгалтерия", 'File="C:\\Bases\\Dup";')
    with pytest.raises(LaunchError) as error:
        workspace.find_by_name("Демо Бухгалтерия")
    assert "не единственное" in str(error.value)
    assert "(2 записи)" in str(error.value)


def test_same_base_in_both_lists_is_shown_once(tmp_path: Path) -> None:
    """[Ф] скил v8i-format: `ID` — ключ идентичности и слияния, значит это
    одна база. Выигрывает пользовательская запись, а пометка сообщает UI,
    что та же база есть и в общем списке.
    """  # noqa: RUF002
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Демо Бухгалтерия]\r\nConnect=File="C:\\Bases\\Demo";\r\n'
        "ID=44444444-4444-4444-4444-444444444444\r\n".encode()
    )
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    key = "id:44444444-4444-4444-4444-444444444444"
    matching = [item for item in workspace.items() if item.key == key]
    assert len(matching) == 1
    assert matching[0].source is InfobaseSource.USER
    assert matching[0].in_common_list
    assert workspace.launch(key).pid == 7


def test_duplicate_in_common_list_gets_its_own_advice(tmp_path: Path) -> None:
    """Разные базы с одним именем, но одна пришла из общего списка: совет
    «переименуйте одну из баз» здесь невыполним — общий список только
    для чтения, и `_reject_common` правку запретит.
    """  # noqa: RUF002
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Демо Бухгалтерия]\r\nConnect=File="C:\\Bases\\Other";\r\nID=aaaa\r\n'.encode()
    )
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    with pytest.raises(LaunchError) as error:
        workspace.launch("id:44444444-4444-4444-4444-444444444444")
    assert "общего списка" in str(error.value)


@pytest.mark.parametrize(
    ("count", "word"), [(1, "запись"), (2, "записи"), (5, "записей"), (11, "записей")]
)
def test_records_word_agrees_with_number(count: int, word: str) -> None:
    assert _records_word(count) == word


def test_duplicate_web_names_are_rejected_before_launch(tmp_path: Path) -> None:
    """Замена удалённого в Task 0 test_duplicate_name_does_not_block_web_base.

    Запуск веб-базы идёт по /IBName ([Ф] T-05.16 № 1), а платформа при дублях
    имени прекращает запуск с «Не уникальное имя информационной базы»
    ([Ф] T-05.3). Прежнее обоснование («открывается браузером по адресу
    из ws, имя в пути не участвует») умерло вместе с браузерным путём.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Портал", 'File="C:\\Bases\\Dup";')
    with pytest.raises(LaunchError) as error:
        workspace.launch("id:77777777-7777-7777-7777-777777777777")
    # Бриф проверял подстроку "уникальн" — текст ошибки ПЛАТФОРМЫ, приведённый
    # в докстринге для обоснования. Наш код бросает "не единственное" (строки
    # 397, 452 — тот же путь); правило исправлено, см. отчёт задачи 4.
    assert "не единственное" in str(error.value)


def _workspace_with_two_web_bases(tmp_path: Path) -> Workspace:
    """Список из двух веб-записей с ОДНИМ именем и разными адресами.

    Свой файл, а не `anonymized.v8i`: дубль имени нужен именно у веб-записей,
    а в фикстуре «Портал» ровно один.
    """  # noqa: RUF002
    sections = (
        "[Портал]\r\n"
        'Connect=ws="http://web-server/resource/";\r\n'
        "ID=77777777-7777-7777-7777-777777777777\r\n"
        "[Портал]\r\n"
        'Connect=ws="http://web-server/other/";\r\n'
        "ID=88888888-8888-8888-8888-888888888888\r\n"
    )
    (tmp_path / "ibases.v8i").write_bytes(sections.encode())
    return _workspace(tmp_path)


def test_explicit_browser_launch_is_not_blocked_by_a_duplicate_name(tmp_path: Path) -> None:
    """Находка финального ревью ветки, I5: «Открыть в браузере» — единственный
    канал, где имя базы не участвует вовсе.

    Отказ по дублю имени защищает запуск по `/IBName`: платформа при
    нескольких базах с одним именем прекращает запуск ([Ф] T-05.3). Разовый
    выбор `LaunchTarget.BROWSER` идёт не по имени, а по адресу из `ws`, и совет
    «переименуйте одну из баз» тут предлагает править файл списка ради
    операции, которой имя безразлично.
    """  # noqa: RUF002
    workspace = _workspace_with_two_web_bases(tmp_path)

    outcome = workspace.launch(
        "id:77777777-7777-7777-7777-777777777777", LaunchTarget.BROWSER
    )

    assert outcome.kind is LaunchKind.BROWSER
    assert outcome.url == "http://web-server/resource/"


def test_duplicate_name_still_blocks_the_same_web_record_without_forced_browser(
    tmp_path: Path,
) -> None:
    """Обратная сторона теста выше: пропуск проверки — только у явного браузера.

    Без этой пары `_reject_ambiguous_name` мог бы отключиться для веб-записей
    целиком, и тест выше остался бы зелёным на пустышке. Тот же приём, что
    у пары `test_workspace_passes_web_setting_to_launch` / `..._goes_to_the_thin_client`.
    """  # noqa: RUF002
    workspace = _workspace_with_two_web_bases(tmp_path)

    with pytest.raises(LaunchError) as error:
        workspace.launch("id:77777777-7777-7777-7777-777777777777")

    assert "не единственное" in str(error.value)


def test_duplicate_name_still_blocks_explicit_thin_client_too(tmp_path: Path) -> None:
    """Граница пропуска — именно `BROWSER`, не «любой явный канал».

    Повторное ревью ветки (мутационная таблица T-15, строка 15): пара тестов
    выше берёт `forced=None` (запуск по умолчанию) и `forced=LaunchTarget.BROWSER`,
    а `LaunchTarget.THIN` нигде не встречается. Условие в `Workspace.launch`
    — `if forced is not LaunchTarget.BROWSER:` — а не «пропустить проверку для
    любого явного `forced`»: у тонкого клиента на веб-базе `/IBName` строится
    по имени, и дубль его так же ломает, как и неявный запуск. Без этого теста
    мутация `if forced is None:` расширила бы пропуск на все разовые каналы
    незаметно.
    """  # noqa: RUF002
    workspace = _workspace_with_two_web_bases(tmp_path)

    with pytest.raises(LaunchError) as error:
        workspace.launch("id:77777777-7777-7777-7777-777777777777", LaunchTarget.THIN)

    assert "не единственное" in str(error.value)


def test_remove_reports_when_key_changed_externally(tmp_path: Path) -> None:
    """Замерено: внешний процесс дописал `ID` записи без него — `remove` по
    старому ключу возвращал `None` без исключения, а запись оставалась.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    old_key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    path = workspace.paths.ibases
    path.write_bytes(
        path.read_bytes().replace(
            b'Connect=File="C:\\Bases\\Manual";\r\n',
            b'Connect=File="C:\\Bases\\Manual";\r\nID=bbbb\r\n',
        )
    )
    assert not workspace.remove_infobase(old_key)
    workspace.reload_if_changed()
    assert any(item.name == "Без идентификатора" for item in workspace.items())


def test_update_of_section_with_empty_id_keeps_user_data(tmp_path: Path) -> None:
    """Замерено: у секции с `ID=` (пустое значение) избранное и история
    исчезали — данные перевешивались на `id:<new_id>`, которого в файле нет.
    """  # noqa: RUF002
    ibases = tmp_path / "ibases.v8i"
    ibases.write_bytes(
        '[Пустой ID]\r\nConnect=File="C:\\Bases\\E";\r\nID=\r\nOrderInList=1\r\n'.encode()
    )
    workspace = _workspace(tmp_path)
    old_key = binding_key(None, 'File="C:\\Bases\\E";', "Пустой ID")
    workspace.set_favorite(old_key, True)
    workspace.update_infobase(old_key, {"Version": "8.3.25"})
    new_key = "id:99999999-9999-9999-9999-999999999999"
    assert next(item for item in workspace.items() if item.key == new_key).favorite


def test_update_infobase_cannot_drop_connect(tmp_path: Path) -> None:
    """Превратить базу в группу обычной правкой нельзя: у групп нет ни
    избранного, ни истории, и запись потеряла бы наши данные молча.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    before = workspace.paths.ibases.read_bytes()
    with pytest.raises(InvalidRequestError):
        workspace.update_infobase(
            "id:44444444-4444-4444-4444-444444444444", {"Connect": None}
        )
    assert workspace.paths.ibases.read_bytes() == before


def test_set_favorite_rejects_unknown_key(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(UnknownItemError):
        workspace.set_favorite("id:нет такого", True)
    assert not (tmp_path / "bases.json").exists()


def test_set_favorite_rejects_group(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(InvalidRequestError):
        workspace.set_favorite("id:11111111-1111-1111-1111-111111111111", True)
    assert not (tmp_path / "bases.json").exists()


def _with_common_list(tmp_path: Path, common: Path) -> tuple[Path, ...]:
    """Собрать 1cestart.cfg в UTF-16LE с BOM — так его пишет платформа."""  # noqa: RUF002
    cfg = tmp_path / "1cestart.cfg"
    cfg.write_bytes(codecs.BOM_UTF16_LE + f"CommonInfoBases={common}\r\n".encode("utf-16-le"))
    return (cfg,)


def test_same_base_in_two_common_lists_is_shown_once(tmp_path: Path) -> None:
    """Один и тот же ID в двух общих списках — одна база, а не две."""  # noqa: RUF002
    section = (
        '[Общая]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'
    ).encode()
    first = tmp_path / "shared-1.v8i"
    second = tmp_path / "shared-2.v8i"
    first.write_bytes(section)
    second.write_bytes(section)
    cfg_all = tmp_path / "1cestart-all.cfg"
    cfg_user = tmp_path / "1cestart-user.cfg"
    cfg_all.write_bytes(
        codecs.BOM_UTF16_LE + f"CommonInfoBases={first}\r\n".encode("utf-16-le")
    )
    cfg_user.write_bytes(
        codecs.BOM_UTF16_LE + f"CommonInfoBases={second}\r\n".encode("utf-16-le")
    )
    workspace = _workspace(tmp_path, cfg_paths=(cfg_all, cfg_user))
    assert sum(1 for item in workspace.items() if item.key == "id:aaaa") == 1


def test_common_list_base_is_visible_but_not_in_tree(tmp_path: Path) -> None:
    """Общие списки — отдельная ветка UI (дизайн плана 3, §2): база из них
    видна в items(), но в дерево пользовательского списка не попадает.
    """
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Общая]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'.encode()
    )
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    common = next(item for item in workspace.items() if item.key == "id:aaaa")
    assert common.source is InfobaseSource.COMMON
    assert not any(
        node.item is not None and node.item.key == "id:aaaa" for node in workspace.tree()
    )
    assert workspace.common_errors() == []


def test_unreadable_common_list_is_reported_not_fatal(tmp_path: Path) -> None:
    missing = tmp_path / "нет.v8i"
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, missing))
    assert len(workspace.items()) == 9
    assert [error.path for error in workspace.common_errors()] == [missing]


def test_write_to_common_list_record_is_refused(tmp_path: Path) -> None:
    """Замерено: `remove` по ключу общей базы молча ничего не делал,
    а `update` врал про «удалена извне» — запись никто не удалял.
    """  # noqa: RUF002
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        '[Общая]\r\nConnect=File="C:\\Bases\\Shared";\r\nID=aaaa\r\n'.encode()
    )
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    with pytest.raises(ReadOnlySourceError):
        workspace.remove_infobase("id:aaaa")
    with pytest.raises(ReadOnlySourceError):
        workspace.update_infobase("id:aaaa", {"Version": "8.3.25"})
    with pytest.raises(ReadOnlySourceError):
        workspace.move_within_group("id:aaaa", None)
    assert any(item.key == "id:aaaa" for item in workspace.items())


def test_unreadable_user_data_reaches_the_caller(tmp_path: Path) -> None:
    """Недоступный bases.json не гасится конструктором: молча подменив его
    пустыми данными, первое же сохранение затёрло бы историю запусков.
    """  # noqa: RUF002
    # Каталог на месте файла: чтение падает OSError, а не FileNotFoundError.  # noqa: RUF003
    (tmp_path / "bases.json").mkdir()
    with pytest.raises(UserDataUnavailableError):
        _workspace(tmp_path)


# -- отказ записи bases.json (финальное ревью, I9) --------------------------
#
# Чтение наших данных разобрано до мелочей (`UserDataUnavailableError` выше),
# запись не была покрыта ничем и своего типа ошибки не имела: `OSError`
# из `save_user_data` выходила голой мимо всех ловцов слоя представления
# (они ловят `ServicesError`). Цена: `Ctrl+D` молча не ставит звёздочку,
# запуск базы молча не обновляет «Последний запуск», а `rebuild()` в  # noqa: RUF003
# `BasesView` стоит ПОСЛЕ `try` — экран расходится с файлом. Под `pythonw.exe`  # noqa: RUF003
# трассировки нет вовсе.
#
# Препятствие во всех трёх тестах — каталог на месте `bases.json`, созданный
# ПОСЛЕ построения Workspace: до этого момента файла нет, и конструктор
# (`load_user_data`) проходит штатно, как на чистой машине.


def _block_user_data(workspace: Workspace) -> None:
    """Сделать `bases.json` недоступным для записи при живом каталоге.

    Каталог на месте файла: `save_user_data` доходит до `atomic_write`,
    и уже `replace` временного файла поверх каталога даёт `OSError` —
    та же точка отказа, что у роуминга, антивируса и полного диска.
    Ставится ПОСЛЕ построения Workspace: до этого момента файла нет,
    и конструктор проходит штатно, как на чистой машине. Если файл успел
    появиться (тест сначала что-то сохранил), он убирается.
    """  # noqa: RUF002
    path = workspace.paths.user_data
    if path.is_file():
        path.unlink()
    path.mkdir()


def test_favorite_reports_a_write_failure(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = "id:44444444-4444-4444-4444-444444444444"
    _block_user_data(workspace)

    with pytest.raises(UserDataWriteError, match="избранное"):
        workspace.set_favorite(key, True)


def test_failed_favorite_write_leaves_no_star_in_memory(tmp_path: Path) -> None:
    """Откат в память: экран после `rebuild()` покажет то же, что в файле.

    Без отката звёздочка горела бы на записи, которой в файле нет, —
    `BasesView.toggle_favorite` зовёт `rebuild()` после `try`, то есть
    даже показав ошибку, показал бы и несуществующее избранное.
    """
    workspace = _workspace(tmp_path)
    key = "id:44444444-4444-4444-4444-444444444444"
    _block_user_data(workspace)

    with pytest.raises(UserDataWriteError):
        workspace.set_favorite(key, True)

    assert not next(item for item in workspace.items() if item.key == key).favorite


def test_launch_reports_a_write_failure_without_claiming_it_did_not_start(
    tmp_path: Path,
) -> None:
    """Процесс уже порождён — сообщение обязано это сказать.

    Иначе пользователь прочтёт отказ как «база не запустилась» и нажмёт
    ещё раз, получив второй экземпляр клиента.
    """
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls)
    key = "id:44444444-4444-4444-4444-444444444444"
    _block_user_data(workspace)

    with pytest.raises(UserDataWriteError, match="База запущена"):
        workspace.launch(key)

    assert len(calls) == 1


def test_rekey_write_failure_still_leaves_the_list_consistent(tmp_path: Path) -> None:
    """Правка `.v8i` состоялась — отказ наших данных её не отменяет.

    Ключ записи сменился (секции дописан `ID`), и состояние обязано это
    отразить: иначе экран остался бы на содержимом, которого в файле уже
    нет. Ошибка придерживается и поднимается ПОСЛЕ приведения состояния
    в порядок, а не вместо него.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    old_key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    workspace.set_favorite(old_key, True)
    _block_user_data(workspace)

    with pytest.raises(UserDataWriteError, match="избранное"):
        workspace.update_infobase(old_key, {"Version": "8.3.25"})

    new_key = "id:99999999-9999-9999-9999-999999999999"
    item = next(item for item in workspace.items() if item.key == new_key)
    assert item.requested_version == "8.3.25", "правка .v8i обязана остаться применённой"
    # Избранное осталось на прежнем ключе, которого в списке больше нет:
    # это честное отражение того, что лежит в файлах, а не потеря.  # noqa: RUF003
    assert not item.favorite


def test_user_data_write_error_is_a_services_error() -> None:
    """Ловцы слоя представления ловят `ServicesError` — тип обязан быть в иерархии."""
    assert issubclass(UserDataWriteError, ServicesError)


def test_add_group_creates_a_node_in_the_tree(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = workspace.add_group("Архив")
    node = next(node for node in workspace.tree() if node.item is not None and node.item.key == key)
    assert node.item is not None
    assert node.item.is_group
    assert node.children == ()


def test_add_group_inside_existing_group(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    key = workspace.add_group("Архив", folder="/Клиенты")
    clients = next(node for node in workspace.tree() if node.label == "Клиенты")
    assert any(child.item is not None and child.item.key == key for child in clients.children)


def test_update_group_moves_the_whole_subtree(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.update_group("id:11111111-1111-1111-1111-111111111111", new_name="Партнёры")
    partners = next(node for node in workspace.tree() if node.label == "Партнёры")
    names = {child.label for child in partners.children}
    assert names == {"Демо Бухгалтерия", "Розница"}
    retail = next(child for child in partners.children if child.label == "Розница")
    assert {child.label for child in retail.children} == {"Демо Розница"}


def test_update_group_keeps_user_data_of_children(tmp_path: Path) -> None:
    """Ключ привязки потомка не зависит от Folder, поэтому избранное
    и история переживают каскад.
    """
    workspace = _workspace(tmp_path)
    child = "id:55555555-5555-5555-5555-555555555555"
    workspace.set_favorite(child, True)
    workspace.update_group("id:11111111-1111-1111-1111-111111111111", new_name="Партнёры")
    assert next(item for item in workspace.items() if item.key == child).favorite


def test_update_group_returns_stable_key_when_id_present(tmp_path: Path) -> None:
    """У группы с ID ключ привязки от имени не зависит и переименование
    его не меняет.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    key = "id:11111111-1111-1111-1111-111111111111"
    assert workspace.update_group(key, new_name="Партнёры") == key


def test_update_group_returns_new_key_when_id_absent(tmp_path: Path) -> None:
    """Без ID ключ суррогатный и строится из собственного пути группы —
    в корне он совпадает с именем. Переименование путь меняет, и вызывающий
    обязан получить новый ключ, иначе следующая операция уйдёт в никуда.
    """  # noqa: RUF002
    ibases = tmp_path / "ibases.v8i"
    ibases.write_bytes(
        "[Клиенты]\r\nOrderInList=-1\r\nFolder=/\r\n"
        "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\nFolder=/Клиенты\r\n".encode()
    )
    workspace = _workspace(tmp_path)
    old_key = group_binding_key(None, "Клиенты")
    new_key = workspace.update_group(old_key, new_name="Партнёры")
    assert new_key != old_key
    assert new_key == group_binding_key(None, "Партнёры")
    assert next(item for item in workspace.items() if item.key == new_key).is_group


def test_remove_group_promotes_children(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.PROMOTE
    )
    names = {node.label for node in workspace.tree()}
    assert "Клиенты" not in names
    assert {"Демо Бухгалтерия", "Розница"} <= names


def test_remove_group_recursive_drops_the_subtree(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.RECURSIVE
    )
    names = {item.name for item in workspace.items()}
    assert names.isdisjoint({"Клиенты", "Розница", "Демо Бухгалтерия", "Демо Розница"})


def test_remove_group_reports_missing_target(tmp_path: Path) -> None:
    assert not _workspace(tmp_path).remove_group("id:нет такого", GroupRemoval.PROMOTE)


def test_move_within_group_changes_the_order_seen_after_rebuild(tmp_path: Path) -> None:
    """Наблюдаемая точка — порядок в `tree()` после перестройки, а не значение
    `OrderInList`, которое вернула чистая функция, и не сырые байты файла.
    Та же дыра, что задачи 9/12/13/14 находили на одну ступень ближе
    к пользователю, чем то, что было покрыто: здесь последняя ступень —
    порядок строк дерева.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    clients = next(node for node in workspace.tree() if node.label == "Клиенты")
    before = [child.label for child in clients.children]
    # Фикстура: «Розница» (OrderInList=-1) стоит раньше «Демо Бухгалтерия»
    # (OrderInList=60.68…) — меньшее значение показывается первым.
    assert before == ["Розница", "Демо Бухгалтерия"]

    demo_key = "id:44444444-4444-4444-4444-444444444444"
    workspace.move_within_group(demo_key, None)

    clients = next(node for node in workspace.tree() if node.label == "Клиенты")
    after = [child.label for child in clients.children]
    assert after == ["Демо Бухгалтерия", "Розница"]


def test_move_within_group_after_key_from_another_group_is_rejected(tmp_path: Path) -> None:
    """Ставить «после» записи чужой группы — перенос, а не перестановка;
    для переноса есть `update_infobase`/`update_group`.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    demo_key = "id:44444444-4444-4444-4444-444444444444"  # Folder=/Клиенты
    server_key = "id:66666666-6666-6666-6666-666666666666"  # Folder=/
    with pytest.raises(InvalidRequestError):
        workspace.move_within_group(demo_key, server_key)


def test_group_operations_refuse_common_list(tmp_path: Path) -> None:
    shared = tmp_path / "shared.v8i"
    shared.write_bytes("[Общая группа]\r\nID=aaaa\r\nOrderInList=-1\r\nFolder=/\r\n".encode())
    workspace = _workspace(tmp_path, cfg_paths=_with_common_list(tmp_path, shared))
    with pytest.raises(ReadOnlySourceError):
        workspace.update_group("id:aaaa", new_name="Другое")
    with pytest.raises(ReadOnlySourceError):
        workspace.remove_group("id:aaaa", GroupRemoval.PROMOTE)


def test_group_removal_is_exported_from_the_layer() -> None:
    """UI обязан уметь назвать политику, не импортируя внутренний модуль."""
    from onecstarter import services

    assert services.GroupRemoval is GroupRemoval
    assert "GroupRemoval" in services.__all__


# -- задача 4 вехи v2.2: логин/пароль записи ---------------------------------


def _first_base_key(workspace: Workspace) -> str:
    return next(i.key for i in workspace.items() if not i.is_group)


def test_set_credentials_keeps_the_password_out_of_our_files(tmp_path: Path) -> None:
    """Инвариант 5 по ФАКТУ на диске: ни bases.json, ни ibases.v8i не несут пароль."""
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)

    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    assert store.read(key) == "p@ss"
    assert "p@ss" not in (tmp_path / "bases.json").read_text(encoding="utf-8")
    assert b"p@ss" not in (tmp_path / "ibases.v8i").read_bytes()
    assert workspace.credentials_of(key) == ("tester", True)


def test_unremember_deletes_the_secret(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.set_credentials(key, "tester", None, remember=False)

    assert store.read(key) is None
    assert workspace.credentials_of(key) == ("tester", False)


def test_clearing_login_deletes_the_secret_too(tmp_path: Path) -> None:
    """Секрет без логина неприменим — оставлять его молча нельзя (спека §4)."""  # noqa: RUF002
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.set_credentials(key, None, None, remember=True)

    assert store.read(key) is None
    assert workspace.credentials_of(key) == (None, False)


def test_remember_without_new_password_keeps_the_stored_one(tmp_path: Path) -> None:
    """Пользователь открыл свойства и нажал ОК, не перепечатывая пароль."""  # noqa: RUF002
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.set_credentials(key, "tester", None, remember=True)

    assert store.read(key) == "p@ss"


def test_launch_passes_stored_credentials(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    store = MemoryStore()
    workspace = _workspace(tmp_path, calls=calls, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.launch(key)

    assert '/N"tester" /P"p@ss"' in calls[0].arguments


def test_launch_without_credentials_is_unchanged(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls=calls)
    workspace.launch(_first_base_key(workspace))
    assert "/N" not in calls[0].arguments and "/P" not in calls[0].arguments


def test_remove_deletes_the_secret(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.remove_infobase(key)

    assert store.read(key) is None


def test_recursive_group_removal_deletes_the_secrets(tmp_path: Path) -> None:
    """Находка ревью: ключ секции без ID иначе достался бы новой записи
    с тем же именем и строкой соединения — вместе с «удалённым» паролем.

    Контрольная запись вне группы (`id:6666…`, «Учёт серверный», `Folder=/`)
    проверяет, что удаление не выметает секреты подряд — только те, что
    принадлежат удалённому поддереву (находка ревью раунда 2: реализация,
    удаляющая всё хранилище целиком, тоже прошла бы тест без этой записи).
    «Розница» (`id:2222…`) в `nested` не входит: это подгруппа «Клиенты»,
    а не база — `set_credentials` отказал бы ей `InvalidRequestError`,
    секретов у групп не бывает вовсе. Обе настоящие базы поддерева —
    «Демо Бухгалтерия» (прямой потомок «Клиенты») и «Демо Розница» (потомок
    через «Розницу») — учтены в `nested`; других баз в этом поддереве
    фикстура не несёт.
    """  # noqa: RUF002
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    nested = [
        "id:44444444-4444-4444-4444-444444444444",  # Демо Бухгалтерия, /Клиенты
        "id:55555555-5555-5555-5555-555555555555",  # Демо Розница, /Клиенты/Розница
    ]
    outside = "id:66666666-6666-6666-6666-666666666666"  # Учёт серверный, /
    for key in [*nested, outside]:
        workspace.set_credentials(key, "tester", "p@ss", remember=True)

    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.RECURSIVE
    )

    assert not any(key in store.data for key in nested)
    assert store.data[outside] == "p@ss"


def test_rekey_moves_the_secret(tmp_path: Path) -> None:
    """Запись без ID получает его при первой правке — ключ меняется с cs:
    на id:, и секрет обязан переехать вместе с избранным (спека §3)."""  # noqa: RUF002
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    # Тот же приём, что у test_update_of_section_without_id_rekeys_user_data  # noqa: RUF003
    # (строка ~223 этого файла): запись фикстуры без ID адресуется суррогатным
    # ключом, а new_id фабрики фиксирован — новый ключ известен заранее.  # noqa: RUF003
    old_key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    workspace.set_credentials(old_key, "tester", "p@ss", remember=True)

    workspace.update_infobase(old_key, {"Version": "8.3.25"})

    new_key = "id:99999999-9999-9999-9999-999999999999"
    assert store.read(new_key) == "p@ss"
    assert store.read(old_key) is None


def test_blank_login_in_user_data_launches_without_credentials(tmp_path: Path) -> None:
    """bases.json правится и руками: пустой логин — не логин, а не ValueError на запуске."""  # noqa: RUF002
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls=calls)
    key = _first_base_key(workspace)
    workspace._user = set_login(workspace._user, key, "   ")

    workspace.launch(key)

    assert "/N" not in calls[0].arguments


def test_store_failure_on_write_is_a_services_error_after_user_data_saved(tmp_path: Path) -> None:
    class Broken(MemoryStore):
        def write(self, key: str, secret: str) -> None:
            raise CredentialBackendError("отказ")

    workspace = _workspace(tmp_path, store=Broken())
    key = _first_base_key(workspace)

    with pytest.raises(CredentialStoreError):
        workspace.set_credentials(key, "tester", "p@ss", remember=True)
    assert workspace.credentials_of(key) == ("tester", False), "логин записан, пароль — нет"


def test_store_failure_on_launch_launches_without_credentials_then_reports(tmp_path: Path) -> None:
    class Broken(MemoryStore):
        def read(self, key: str) -> str | None:
            raise CredentialBackendError("отказ")

    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls=calls, store=Broken())
    key = _first_base_key(workspace)
    workspace._user = set_login(workspace._user, key, "tester")

    with pytest.raises(CredentialStoreError):
        workspace.launch(key)
    assert len(calls) == 1, "процесс порождён — отказ хранилища не отказ запуска"
    assert "/P" not in calls[0].arguments


# -- финальный fix-раунд v2.2: перенос секрета при rekey (F1, F2, F3) --------


class _NoStore:
    """Машина без Credential Manager: отказывает ЛЮБОЙ вызов.

    `keyring` на такой машине поднимает `NoKeyringError` уже из
    `get_keyring()`, то есть до различения операций, — поэтому шпион
    отказывает и на `read`, и на `write`, и на `delete`.
    """

    def read(self, key: str) -> str | None:
        raise CredentialBackendError("NoKeyringError")

    def write(self, key: str, secret: str) -> None:
        raise CredentialBackendError("NoKeyringError")

    def delete(self, key: str) -> None:
        raise CredentialBackendError("NoKeyringError")


class _ReadRefused(MemoryStore):
    def read(self, key: str) -> str | None:
        raise CredentialBackendError("NoKeyringError")


class _WriteRefused(MemoryStore):
    def write(self, key: str, secret: str) -> None:
        raise CredentialBackendError("отказ записи")


class _DeleteRefused(MemoryStore):
    def delete(self, key: str) -> None:
        raise CredentialBackendError("отказ удаления")


_ID_LESS_KEY = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
_REKEYED_KEY = "id:99999999-9999-9999-9999-999999999999"


def test_group_rename_never_touches_the_credential_store(tmp_path: Path) -> None:
    """У группы пароля быть не может — хранилище на её пути не спрашивается.

    Ключ группы без `ID` — `grp:<путь>`, он меняется при переименовании,
    то есть `_write` идёт по ветке rekey. Безусловный перенос секрета
    ронял переименование группы на машине без Credential Manager.
    """  # noqa: RUF002
    (tmp_path / "ibases.v8i").write_bytes("[Отдел]\r\nFolder=/\r\n".encode())
    workspace = _raw_workspace(tmp_path, store=_NoStore())
    key = workspace.items()[0].key

    workspace.update_group(key, new_name="Отдел 2")

    assert [item.name for item in workspace.items()] == ["Отдел 2"]


def test_edit_of_id_less_record_with_unavailable_store_reports_unverified_password(
    tmp_path: Path,
) -> None:
    """Отказ `read` — это отказ ПРОВЕРКИ, а не переноса: переносить нечего.

    Прежний текст («не удалось перенести пароль») утверждал факт, которого
    никто не измерял: был ли у записи пароль вообще, неизвестно.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path, store=_ReadRefused())

    with pytest.raises(CredentialStoreError, match="не удалось проверить"):
        workspace.update_infobase(_ID_LESS_KEY, {"Version": "8.3.25"})

    assert any(item.key == _REKEYED_KEY for item in workspace.items())


def test_rekey_delete_failure_says_the_password_moved_and_a_copy_remains(
    tmp_path: Path,
) -> None:
    """Полу-удавшийся перенос: секрет уже под новым ключом, старый остался.

    Сообщение «не удалось перенести пароль» здесь было обратным факту,
    а старая копия — не безобидный мусор: суррогатный ключ унаследует
    новая запись с тем же именем и строкой соединения.
    """  # noqa: RUF002
    store = _DeleteRefused()
    workspace = _workspace(tmp_path, store=store)
    store.data[_ID_LESS_KEY] = "p@ss"

    with pytest.raises(CredentialStoreError) as failure:
        workspace.update_infobase(_ID_LESS_KEY, {"Version": "8.3.25"})

    text = str(failure.value)
    assert "перенесён" in text and "старая копия" in text
    assert _ID_LESS_KEY in text, "без ключа уборка вручную невозможна"
    assert store.data[_REKEYED_KEY] == "p@ss"
    assert store.data[_ID_LESS_KEY] == "p@ss"


def test_rekey_write_failure_says_the_password_stayed_with_the_old_record(
    tmp_path: Path,
) -> None:
    store = _WriteRefused()
    workspace = _workspace(tmp_path, store=store)
    store.data[_ID_LESS_KEY] = "p@ss"

    with pytest.raises(CredentialStoreError, match="не перенесён"):
        workspace.update_infobase(_ID_LESS_KEY, {"Version": "8.3.25"})

    assert list(store.data) == [_ID_LESS_KEY]


def test_rekey_reports_both_the_user_data_and_the_store_failures(tmp_path: Path) -> None:
    """`failure = failure or …` полностью скрывал отказ хранилища за отказом
    `bases.json`: пользователь узнавал про избранное и не узнавал про пароль."""
    store = _WriteRefused()
    workspace = _workspace(tmp_path, store=store)
    store.data[_ID_LESS_KEY] = "p@ss"
    _block_user_data(workspace)

    with pytest.raises(UserDataWriteError) as failure:
        workspace.update_infobase(_ID_LESS_KEY, {"Version": "8.3.25"})

    text = str(failure.value)
    assert "избранное" in text, "отказ наших данных не должен теряться"
    assert "не перенесён" in text, "отказ хранилища не должен маскироваться"


def test_credentials_of_keeps_login_when_the_store_fails(tmp_path: Path) -> None:
    """Логин прочитан из наших данных ДО обращения к хранилищу — терять его
    из-за недоступного Credential Manager нельзя: диалог покажет пустое поле
    и молча сотрёт сохранённый логин по «ОК». `None` — «неизвестно»."""  # noqa: RUF002
    workspace = _workspace(tmp_path, store=_ReadRefused())
    key = _first_base_key(workspace)
    workspace._user = set_login(workspace._user, key, "tester")

    assert workspace.credentials_of(key) == ("tester", None)


# -- v2.3: канал запуска веб-базы через Workspace ---------------------------


def _workspace_with_web_base(
    tmp_path: Path, app: str | None = None, calls: list[LaunchCommand] | None = None
) -> Workspace:
    """Workspace с единственной веб-базой; `app` — значение ключа `App` записи.

    Свой файл, а не `anonymized.v8i`: у «Портала» из фикстуры ключа `App`
    нет вовсе, а спор «настройка против записи» (спека v2.3, §3) требует
    уметь собрать обе стороны. Параметр `app` — отклонение от плана,
    записанное в отчёте задачи 3: план звал этот хелпер без аргумента
    и одновременно требовал от него и записи без `App` (тогда решает
    настройка), и записи с `App=ThinClient` (тогда настройка не решает).
    Одним фиксированным хелпером эти два теста несовместимы.
    """  # noqa: RUF002
    section = (
        "[Портал]\r\n"
        'Connect=ws="http://web-server/resource/";\r\n'
        "ID=77777777-7777-7777-7777-777777777777\r\n"
    )
    if app is not None:
        section += f"App={app}\r\n"
    (tmp_path / "ibases.v8i").write_bytes(section.encode())
    return _workspace(tmp_path, calls)


def _web_key(workspace: Workspace) -> str:
    return next(
        item.key
        for item in workspace.items()
        if not item.is_group and item.kind is ConnectKind.WEB
    )


def test_workspace_passes_web_setting_to_launch(tmp_path: Path) -> None:
    workspace = _workspace_with_web_base(tmp_path)
    workspace.set_web_launch(is_browser=True)
    assert workspace.launch(_web_key(workspace)).kind is LaunchKind.BROWSER


def test_workspace_web_base_without_the_setting_goes_to_the_thin_client(
    tmp_path: Path,
) -> None:
    """Обратная сторона теста выше: без настройки браузер не открывается.

    Без этой пары `set_web_launch` мог бы не делать ничего — веб-база
    уходила бы в браузер сама, как до вехи, и тест настройки остался бы
    зелёным на пустышке.
    """
    calls: list[LaunchCommand] = []
    workspace = _workspace_with_web_base(tmp_path, calls=calls)
    outcome = workspace.launch(_web_key(workspace))
    assert outcome.kind is LaunchKind.PROCESS
    assert calls[0].executable.name == "1cv8c.exe"


def test_workspace_forced_browser_beats_thin_app(tmp_path: Path) -> None:
    """«Открыть в браузере» — разовый выбор, сильнее и App, и настройки."""
    workspace = _workspace_with_web_base(tmp_path, app="ThinClient")
    outcome = workspace.launch(_web_key(workspace), LaunchTarget.BROWSER)
    assert outcome.kind is LaunchKind.BROWSER


def test_workspace_forced_designer_on_web_base_refuses(tmp_path: Path) -> None:
    """Отказ доходит до вызывающего целиком — UI показывает его текстом."""  # noqa: RUF002
    workspace = _workspace_with_web_base(tmp_path, app="ThinClient")
    with pytest.raises(LaunchError) as error:
        workspace.launch(_web_key(workspace), LaunchTarget.DESIGNER)
    assert "ws=" in str(error.value)


_FILE_AND_WEB = (
    '[Файловая]\r\nConnect=File="C:\\B";\r\n'
    '[Веб]\r\nConnect=ws="http://srv/b";\r\n'  # noqa: RUF001
)


def _key_of(workspace: Workspace, name: str) -> str:
    return next(item.key for item in workspace.items() if item.name == name)


def _recording(calls: list[LaunchCommand]) -> Callable[[LaunchCommand], int]:
    def spawn(command: LaunchCommand) -> int:
        calls.append(command)
        return 11

    return spawn


@pytest.mark.parametrize("forced", [None, LaunchTarget.DESIGNER])
def test_elevated_launch_uses_same_command_as_plain(
    tmp_path: Path, forced: LaunchTarget | None
) -> None:
    """T-31: тот же конвейер — версия, канал, учётные данные; другая функция порождения."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    plain: list[LaunchCommand] = []
    elevated: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, plain, spawn_elevated=_recording(elevated))
    key = _key_of(workspace, "Файловая")
    workspace.launch(key, forced)
    workspace.launch(key, forced, elevated=True)
    assert len(plain) == 1
    assert [command.command_line for command in elevated] == [plain[0].command_line]


def test_elevated_launch_records_history(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    elevated: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, spawn_elevated=_recording(elevated))
    key = _key_of(workspace, "Файловая")
    workspace.launch(key, elevated=True)
    item = next(item for item in workspace.items() if item.key == key)
    assert item.launch_count == 1
    assert item.last_launched_at is not None


def test_elevated_launch_refuses_web_base(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    plain: list[LaunchCommand] = []
    elevated: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, plain, spawn_elevated=_recording(elevated))
    with pytest.raises(LaunchError, match="веб-сервере"):
        workspace.launch(_key_of(workspace, "Веб"), elevated=True)  # noqa: RUF001
    assert plain == []
    assert elevated == []


def test_declined_uac_raises_declined_and_records_nothing(tmp_path: Path) -> None:
    """Мутационная проверка обязательна: отказ UAC — без записи времени."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())

    def declining(_command: LaunchCommand) -> int:
        raise ElevationDeclinedError("пользователь отказал")

    workspace = _raw_workspace(tmp_path, spawn_elevated=declining)
    key = _key_of(workspace, "Файловая")
    with pytest.raises(LaunchDeclinedError):
        workspace.launch(key, elevated=True)
    item = next(item for item in workspace.items() if item.key == key)
    assert item.launch_count == 0
    assert item.last_launched_at is None


# -- T-32: запуск с запросом входа (Shift+F3/F4) --------------------------------  # noqa: RUF003


@pytest.mark.parametrize(
    ("forced", "executable", "mode"),
    [(None, "1cv8c.exe", "ENTERPRISE"), (LaunchTarget.DESIGNER, "1cv8.exe", "DESIGNER")],
)
def test_ask_login_drops_stored_credentials_and_denies_os_auth(
    tmp_path: Path, forced: LaunchTarget | None, executable: str, mode: str
) -> None:
    """Мутационная проверка обязательна: сохранённые /N /P в режим не попадают."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    store = MemoryStore()
    workspace = _raw_workspace(tmp_path, calls, store=store)
    key = _key_of(workspace, "Файловая")
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.launch(key, forced, ask_login=True)

    assert len(calls) == 1
    assert calls[0].executable.name == executable
    assert calls[0].arguments.startswith(f'{mode} /IBName"Файловая" /WA- ')
    assert "/N" not in calls[0].arguments and "/P" not in calls[0].arguments
    # Сохранённое на месте: режим не «зачищает» учётные данные.
    assert workspace.credentials_of(key) == ("tester", True)
    assert store.read(key) == "p@ss"


def test_ask_login_never_touches_the_credential_store(tmp_path: Path) -> None:
    """Мутационная проверка обязательна: хранилище в режиме не читается вовсе."""

    class Untouchable(MemoryStore):
        def read(self, key: str) -> str | None:
            raise AssertionError("ask_login не должен читать хранилище")

    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls, store=Untouchable())
    key = _key_of(workspace, "Файловая")
    workspace._user = set_login(workspace._user, key, "tester")

    workspace.launch(key, ask_login=True)

    assert len(calls) == 1


def test_ask_login_records_history(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path)
    key = _key_of(workspace, "Файловая")
    workspace.launch(key, ask_login=True)
    item = next(item for item in workspace.items() if item.key == key)
    assert item.launch_count == 1
    assert item.last_launched_at is not None


def test_ask_login_refuses_web_base(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    with pytest.raises(LaunchError) as error:
        workspace.launch(_key_of(workspace, "Веб"), ask_login=True)  # noqa: RUF001
    assert str(error.value) == (
        "Для «Веб» запуск с запросом входа не предусмотрен: база опубликована на веб-сервере"  # noqa: RUF001
    )
    assert calls == []


def test_ask_login_and_elevated_do_not_combine(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    with pytest.raises(ValueError, match="не сочетаются"):
        workspace.launch(_key_of(workspace, "Файловая"), elevated=True, ask_login=True)
    assert calls == []


def test_designer_params_are_stored_in_user_data_not_in_v8i(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    before = (tmp_path / "ibases.v8i").read_bytes()

    workspace.set_designer_params(key, "/DisableStartupMessages")

    assert workspace.designer_params_of(key) == "/DisableStartupMessages"
    assert (tmp_path / "ibases.v8i").read_bytes() == before


def test_designer_params_survive_reload(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/Len")

    reloaded = _raw_workspace(tmp_path, [])

    assert reloaded.designer_params_of(key) == "/Len"


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_designer_params_are_cleared(tmp_path: Path, value: str | None) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/Len")
    workspace.set_designer_params(key, value)
    assert workspace.designer_params_of(key) is None


def test_designer_params_with_line_break_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    with pytest.raises(InvalidRequestError, match="перевод строки"):
        workspace.set_designer_params(key, "/Len\n/C x")


@pytest.mark.parametrize(
    "params",
    [
        "/WSP zzz",
        '/P"zzz"',
        "/P zzz",
        "/Proxy -PSrv srv -PPort 3128 -PUser u -PPwd zzz",
        "/HttpsCert -file c.pfx -pwd zzz",
        '/Len /ModifyPassword "zzz"',
        "/AccessToken zzz",
        "/Len\t/WSP zzz",
    ],
)
def test_designer_params_with_secret_are_not_saved(tmp_path: Path, params: str) -> None:
    """Мутационная проверка обязательна (финальное ревью, F1; решение заказчика 09.11.2026)."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/Len")
    before = (tmp_path / "bases.json").read_bytes()

    with pytest.raises(InvalidRequestError, match="Пароль") as error:
        workspace.set_designer_params(key, params)

    assert "zzz" not in str(error.value)
    assert "поле «Пароль»" in str(error.value)
    assert (tmp_path / "bases.json").read_bytes() == before
    assert workspace.designer_params_of(key) == "/Len"


def test_designer_params_with_unclosed_quote_get_their_own_refusal(tmp_path: Path) -> None:
    """Приёмка 21.11.2026, Ф2/Р2: о кавычке — свой текст, не о пароле."""  # noqa: RUF002
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/Len")
    before = (tmp_path / "bases.json").read_bytes()

    with pytest.raises(InvalidRequestError) as error:
        workspace.set_designer_params(key, '/Len /Out "C:\\a b.txt')

    assert str(error.value) == DESIGNER_QUOTE_REFUSAL
    assert "незакрытая кавычка" in str(error.value)
    assert (tmp_path / "bases.json").read_bytes() == before


@pytest.mark.parametrize("params", ["/Proxy -PSrv srv -PPort 3128 -PUser u", '/C "a b"\t/Len'])
def test_designer_params_without_secret_are_saved(tmp_path: Path, params: str) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, params)
    assert workspace.designer_params_of(key) == params


def test_update_of_section_without_id_moves_designer_params(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    old_key = binding_key(None, 'File="C:\\Bases\\Manual";', "Без идентификатора")
    workspace.set_designer_params(old_key, "/Len")
    workspace.update_infobase(old_key, {"Version": "8.3.25"})
    assert workspace.designer_params_of("id:99999999-9999-9999-9999-999999999999") == "/Len"


@pytest.mark.parametrize(
    ("forced", "expected"),
    [
        (None, None),
        (LaunchTarget.THIN, None),
        (LaunchTarget.THICK, None),
        (LaunchTarget.DESIGNER, "/DisableStartupMessages"),
    ],
)
def test_designer_params_go_only_to_designer(
    tmp_path: Path, forced: LaunchTarget | None, expected: str | None
) -> None:
    """Мутационная проверка обязательна: строка Конфигуратора не уходит в Предприятие."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/DisableStartupMessages")

    workspace.launch(key, forced)

    if expected is None:
        assert "/DisableStartupMessages" not in calls[0].arguments
    else:
        assert f" {expected} /AppAutoCheckVersion" in calls[0].arguments


def test_once_params_follow_designer_params(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/Lru")

    workspace.launch(key, LaunchTarget.DESIGNER, once="/Len")

    assert " /Lru /Len /AppAutoCheckVersion" in calls[0].arguments


def test_once_params_reach_enterprise(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")

    workspace.launch(key, once="/C x")

    assert calls[0].arguments.startswith('ENTERPRISE /IBName"Файловая" /C x ')


@pytest.mark.parametrize(("elevated", "ask_login"), [(True, False), (False, True)])
def test_once_params_do_not_combine_with_elevation_or_login_prompt(
    tmp_path: Path, elevated: bool, ask_login: bool
) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    with pytest.raises(ValueError, match="не сочетаются"):
        workspace.launch(key, once="/Len", elevated=elevated, ask_login=ask_login)


def test_line_break_in_stored_designer_params_is_launch_error(tmp_path: Path) -> None:
    """Руками правленный bases.json: сеттер обойдён, ошибка — понятная, процесса нет."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")
    workspace._user = set_designer_params(workspace._user, key, "/Len\n/C секрет")

    with pytest.raises(LaunchError, match="перевод строки") as error:
        workspace.launch(key, LaunchTarget.DESIGNER)

    assert "секрет" not in str(error.value)
    assert calls == []


def test_line_break_in_once_params_is_launch_error(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")

    with pytest.raises(LaunchError, match="перевод строки") as error:
        workspace.launch(key, once="/Len\n/C секрет")

    assert "секрет" not in str(error.value)
    assert calls == []


@pytest.mark.parametrize("char", ["\x00", "\x0b", "\x0c", "\x1b", "\x1f"])
def test_control_chars_in_once_and_designer_params_are_launch_errors(
    tmp_path: Path, char: str
) -> None:
    """Мутационная проверка обязательна (финальное ревью, F7): Popen не получает NUL и т. п."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")

    with pytest.raises(LaunchError, match="управляющий символ") as once_error:
        workspace.launch(key, once=f"/Len{char}/C секрет")
    workspace._user = set_designer_params(workspace._user, key, f"/Len{char}/C секрет")
    with pytest.raises(LaunchError, match="управляющий символ") as designer_error:
        workspace.launch(key, LaunchTarget.DESIGNER)

    assert "секрет" not in str(once_error.value) + str(designer_error.value)
    assert calls == []


def test_control_char_in_designer_params_is_not_saved(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    with pytest.raises(InvalidRequestError, match="управляющие символы"):
        workspace.set_designer_params(key, "/Len\x00/C x")
    assert workspace.designer_params_of(key) is None


def test_tab_in_once_params_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    workspace.launch(_key_of(workspace, "Файловая"), once="/C x\t/Len")
    assert len(calls) == 1


def test_padded_designer_params_and_once_are_joined_by_single_space(tmp_path: Path) -> None:
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = _key_of(workspace, "Файловая")
    workspace._user = set_designer_params(workspace._user, key, "  /Lru  ")

    workspace.launch(key, LaunchTarget.DESIGNER, once="  /Len  ")

    assert " /Lru /Len /AppAutoCheckVersion" in calls[0].arguments


def test_additional_parameters_write_touches_only_its_line(tmp_path: Path) -> None:
    """Мутационная проверка обязательна (спека §10.1): порядок, кодировка, BOM, переводы строк."""
    raw = (
        "\ufeff[Файловая]\r\nConnect=File=\"C:\\B\";\r\nID=11111111-1111-1111-1111-111111111111\r\n"
        "XTest=1\r\n[Вторая]\r\nConnect=File=\"C:\\C\";\r\n"
    )
    (tmp_path / "ibases.v8i").write_bytes(raw.encode("utf-8"))
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")

    workspace.update_infobase(key, {"AdditionalParameters": '/Len /C "x ""y"""'})

    expected = raw.replace(
        "XTest=1\r\n", 'XTest=1\r\nAdditionalParameters=/Len /C "x ""y"""\r\n'
    )
    assert (tmp_path / "ibases.v8i").read_bytes() == expected.encode("utf-8")

    workspace.update_infobase(key, {"AdditionalParameters": None})
    assert (tmp_path / "ibases.v8i").read_bytes() == raw.encode("utf-8")


# -- v4, блок 2, задача 3: хранилище конфигурации у базы ---------------------  # noqa: RUF003


def test_repository_settings_are_stored_and_password_goes_to_the_store(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_repository(key, " tcp://repo/main ", " builder ", "s3cret", True)
    assert workspace.repository_of(key) == RepositorySettings("tcp://repo/main", "builder", True)
    assert store.data[repository_key(key)] == "s3cret"
    assert "s3cret" not in (tmp_path / "bases.json").read_text(encoding="utf-8")


def test_repository_password_is_deleted_without_user_or_remember(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    workspace.set_repository(key, "tcp://repo", "builder", None, False)
    assert repository_key(key) not in store.data
    workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    workspace.set_repository(key, "tcp://repo", "", None, True)
    assert repository_key(key) not in store.data


def test_repository_password_kept_when_not_retyped(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    workspace.set_repository(key, "tcp://other", "builder", None, True)
    assert store.data[repository_key(key)] == "s3cret"


def test_repository_of_reports_unavailable_store(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, store=_ReadRefused())
    key = _first_base_key(workspace)
    assert workspace.repository_of(key).has_password is None


def test_repository_password_moves_with_the_record_key(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    # Приём теста test_rekey_moves_the_secret: запись без ID, новый ключ известен заранее.
    old_key = _ID_LESS_KEY
    workspace.set_repository(old_key, "tcp://repo", "builder", "s3cret", True)
    workspace.update_infobase(old_key, {"Version": "8.3.25"})
    assert store.data.get(repository_key(_REKEYED_KEY)) == "s3cret"
    assert repository_key(old_key) not in store.data


def test_removing_a_base_deletes_its_repository_password(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    workspace.remove_infobase(key)
    assert repository_key(key) not in store.data


def test_recursive_group_removal_deletes_the_repository_passwords(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    inside = "id:44444444-4444-4444-4444-444444444444"
    outside = "id:66666666-6666-6666-6666-666666666666"
    for key in (inside, outside):
        workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.RECURSIVE
    )
    assert repository_key(inside) not in store.data
    assert store.data[repository_key(outside)] == "s3cret"


class _SelectiveStore(MemoryStore):
    """Отказывает `delete`/`write` только для названных ключей."""

    def __init__(
        self, refuse_delete: Sequence[str] = (), refuse_write: Sequence[str] = ()
    ) -> None:
        super().__init__()
        self.refuse_delete, self.refuse_write = set(refuse_delete), set(refuse_write)

    def delete(self, key: str) -> None:
        if key in self.refuse_delete:
            raise CredentialBackendError("отказ удаления")
        super().delete(key)

    def write(self, key: str, secret: str) -> None:
        if key in self.refuse_write:
            raise CredentialBackendError("отказ записи")
        super().write(key, secret)


def test_removal_deletes_the_repository_password_even_if_the_base_password_fails(
    tmp_path: Path,
) -> None:
    key = "id:44444444-4444-4444-4444-444444444444"
    store = _SelectiveStore(refuse_delete=[key])
    workspace = _workspace(tmp_path, store=store)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)
    workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    with pytest.raises(CredentialStoreError) as failure:
        workspace.remove_infobase(key)
    assert repository_key(key) not in store.data
    assert store.data[key] == "p@ss"
    text = str(failure.value)
    assert key in text and "p@ss" not in text and "s3cret" not in text


def test_removal_names_both_remaining_secrets(tmp_path: Path) -> None:
    key = "id:44444444-4444-4444-4444-444444444444"
    store = _SelectiveStore(refuse_delete=[key, repository_key(key)])
    workspace = _workspace(tmp_path, store=store)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)
    workspace.set_repository(key, "tcp://repo", "builder", "s3cret", True)
    with pytest.raises(CredentialStoreError) as failure:
        workspace.remove_infobase(key)
    text = str(failure.value)
    assert f"/{key}`" in text and f"/{repository_key(key)}`" in text
    assert "пароль хранилища" in text
    assert "p@ss" not in text and "s3cret" not in text


def test_group_removal_deletes_the_repository_password_even_if_the_base_password_fails(
    tmp_path: Path,
) -> None:
    inside = "id:44444444-4444-4444-4444-444444444444"
    store = _SelectiveStore(refuse_delete=[inside])
    workspace = _workspace(tmp_path, store=store)
    workspace.set_credentials(inside, "tester", "p@ss", remember=True)
    workspace.set_repository(inside, "tcp://repo", "builder", "s3cret", True)
    with pytest.raises(CredentialStoreError) as failure:
        workspace.remove_group("id:11111111-1111-1111-1111-111111111111", GroupRemoval.RECURSIVE)
    assert repository_key(inside) not in store.data
    assert inside in str(failure.value) and "p@ss" not in str(failure.value)


def test_repository_password_move_failure_is_reported(tmp_path: Path) -> None:
    store = _SelectiveStore(refuse_write=[repository_key(_REKEYED_KEY)])
    workspace = _workspace(tmp_path, store=store)
    workspace.set_repository(_ID_LESS_KEY, "tcp://repo", "builder", "s3cret", True)
    with pytest.raises(CredentialStoreError, match="пароль хранилища не перенесён"):
        workspace.update_infobase(_ID_LESS_KEY, {"Version": "8.3.25"})
    assert store.data[repository_key(_ID_LESS_KEY)] == "s3cret"


def test_repository_for_a_group_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    group_key = next(item.key for item in workspace.items() if item.is_group)
    with pytest.raises(InvalidRequestError):
        workspace.set_repository(group_key, "tcp://repo", "builder", None, False)


# -- T-41.5: готовность базы к пакетной операции -----------------------------


def _first_file_base_key(workspace: Workspace) -> str:
    return next(i.key for i in workspace.items() if i.kind is ConnectKind.FILE)


def test_batch_target_of_a_file_base(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, store=MemoryStore())
    key = _first_file_base_key(workspace)
    workspace.set_credentials(key, "Иванов", "pw", True)
    workspace.set_repository(key, "tcp://repo", "builder", "rpw", True)
    target = workspace.batch_target(key)
    assert target.problems == ()
    assert target.executable is not None and target.executable.name.lower() == "1cv8.exe"
    assert target.version is not None
    assert (target.login, target.password) == ("Иванов", "pw")
    assert (target.repository_address, target.repository_user, target.repository_password) == (
        "tcp://repo",
        "builder",
        "rpw",
    )
    assert target.file_path
    assert "pw" not in repr(target)
    assert "rpw" not in repr(target)


def test_batch_target_problems(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert workspace.batch_target("нет такого").problems == ("база не найдена в списке",)
    group = next(item.key for item in workspace.items() if item.is_group)
    assert workspace.batch_target(group).problems == ("это группа, а не база",)  # noqa: RUF001
    web = next(item.key for item in workspace.items() if item.kind is ConnectKind.WEB)
    assert workspace.batch_target(web).problems == (
        "веб-база: пакетный режим Конфигуратора с ней не работает",  # noqa: RUF001
    )


def test_batch_target_before_discovery_and_without_version(tmp_path: Path) -> None:
    pending = _raw_workspace(tmp_path, installations=None)
    key = _first_file_base_key(pending)
    assert pending.batch_target(key).problems == ("обнаружение версий платформы ещё не завершено",)
    empty = _raw_workspace(tmp_path, installations=[])
    assert empty.batch_target(key).problems[0].startswith("версия платформы")


def test_batch_target_reports_unavailable_credential_store(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, store=MemoryStore())
    key = _first_file_base_key(workspace)
    workspace.set_credentials(key, "Иванов", "pw", True)
    broken = _workspace(tmp_path, store=_ReadRefused())
    target = broken.batch_target(key)
    # Отказ диспетчера — не проблема: пароль можно ввести при запуске (F5).
    assert target.problems == () and target.store_unavailable
    assert (target.login, target.password) == ("Иванов", None)
    assert not _workspace(tmp_path, store=MemoryStore()).batch_target(key).store_unavailable


def test_batch_target_group_is_the_folder_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    nested = next(
        item
        for item in workspace.items()
        if not item.is_group and item.kind is not ConnectKind.WEB and item.folder not in ("", "/")
    )
    assert workspace.batch_target(nested.key).group == nested.folder.strip("/")


_SERVER_KEY = "id:66666666-6666-6666-6666-666666666666"  # «Учёт серверный», DefaultVersion
_EXACT_VERSION_PROBLEM = (
    "серверная база: задайте в свойствах точную версию платформы (например, 8.3.27.2214)"
)


def test_batch_target_of_a_server_base_without_version_is_not_ready(tmp_path: Path) -> None:
    """DefaultVersion=8.3.25.1633 установлена, но подбор по умолчаниям для серверной базы
    не применяется: клиент не той версии с /AppAutoCheckVersion- зависает ([Ф] T-05.16)."""  # noqa: RUF002
    target = _workspace(tmp_path).batch_target(_SERVER_KEY)
    assert target.problems == (_EXACT_VERSION_PROBLEM,)
    assert target.executable is None and target.version is None


def test_batch_target_of_a_server_base_with_a_partial_version(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.update_infobase(_SERVER_KEY, {"Version": "8.3.25"})
    target = workspace.batch_target(_SERVER_KEY)
    assert target.problems == (_EXACT_VERSION_PROBLEM,)
    assert target.executable is None


def test_batch_target_of_a_server_base_with_an_installed_exact_version(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.update_infobase(_SERVER_KEY, {"Version": "8.3.25.1633"})
    target = workspace.batch_target(_SERVER_KEY)
    assert target.problems == ()
    assert target.version == parse_version("8.3.25.1633")
    assert target.executable == Path(r"C:\Program Files\1cv8\8.3.25.1633\bin\1cv8.exe")
    assert target.file_path is None


def test_batch_target_of_a_server_base_with_a_missing_exact_version(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.update_infobase(_SERVER_KEY, {"Version": "8.3.27.2214"})
    target = workspace.batch_target(_SERVER_KEY)
    assert target.problems == ("версия платформы 8.3.27.2214 не установлена",)
    assert target.executable is None and target.version is None


def test_batch_target_reports_a_duplicate_name(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Демо Бухгалтерия", 'File="C:\\Bases\\Dup";')
    target = workspace.batch_target("id:44444444-4444-4444-4444-444444444444")
    assert "имя базы в списке не единственное" in target.problems


def test_designer_params_keep_access_code_uc(tmp_path: Path) -> None:
    """Решение заказчика 23.11.2026 (T-44): код доступа `/UC` — не пароль, строка сохраняется."""
    (tmp_path / "ibases.v8i").write_bytes(_FILE_AND_WEB.encode())
    workspace = _raw_workspace(tmp_path, [])
    key = _key_of(workspace, "Файловая")
    workspace.set_designer_params(key, "/UC 1234")
    assert workspace.designer_params_of(key) == "/UC 1234"
