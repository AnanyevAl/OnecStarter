import codecs
import shutil
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest

from onecstarter.domain.launch import ClientConvention, ClientKind, LaunchCommand
from onecstarter.domain.version import Arch, Installation, parse_version
from onecstarter.services.catalog import read_common_lists
from onecstarter.services.errors import (
    InvalidRequestError,
    LaunchError,
    ReadOnlySourceError,
    ServicesError,
    UnknownItemError,
    UserDataUnavailableError,
    UserDataWriteError,
)
from onecstarter.services.groups import GroupRemoval
from onecstarter.services.model import InfobaseSource, binding_key, group_binding_key
from onecstarter.services.workspace import Workspace, WorkspacePaths, _records_word

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


def _raw_workspace(
    tmp_path: Path,
    calls: list[LaunchCommand] | None = None,
    cfg_paths: tuple[Path, ...] = (),
    installations: Sequence[Installation] | None = INSTALLED,
) -> Workspace:
    """Собрать Workspace как есть — без снимка общих списков.

    Низкоуровневый хелпер для тестов, которым важно именно состояние
    «сразу после конструктора»: pending общих списков и/или pending
    установок (§3.3–3.4 спеки T-04.6). `_workspace` ниже — обёртка над
    этим хелпером для всех остальных тестов, которым не до тонкостей
    и нужен уже «загруженный» Workspace.
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
        open_url=lambda url: True,
        now=lambda: datetime.fromisoformat(STAMP),
        new_id=lambda: "99999999-9999-9999-9999-999999999999",
    )


def _workspace(
    tmp_path: Path,
    calls: list[LaunchCommand] | None = None,
    cfg_paths: tuple[Path, ...] = (),
) -> Workspace:
    """Собрать Workspace и сразу применить снимок общих списков.

    Большинству тестов файла не важно, что применение снимка — теперь
    отдельный шаг (§3.3 спеки T-04.6, задача T-02 поставки): они писались
    до разделения конструктора и `apply_common_lists` и ждут уже
    «загруженный» мир. Тесты, которым важен именно момент до применения
    снимка (pending), используют `_raw_workspace` напрямую.
    """
    workspace = _raw_workspace(tmp_path, calls, cfg_paths)
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


def test_duplicate_name_does_not_block_web_base(tmp_path: Path) -> None:
    """Веб-база открывается браузером по адресу из `ws`, а не по `/IBName`,
    поэтому неоднозначность имени её запуску не мешает.
    """  # noqa: RUF002
    workspace = _workspace(tmp_path)
    workspace.add_infobase("Портал", 'File="C:\\Bases\\Dup";')
    assert workspace.launch("id:77777777-7777-7777-7777-777777777777").url


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
