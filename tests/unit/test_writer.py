from pathlib import Path

import pytest

from onecstarter.config import atomic
from onecstarter.config.v8i import parse_v8i
from onecstarter.services.catalog import items_from_document
from onecstarter.services.edit import PatchKind, ReorderPatch, SectionPatch
from onecstarter.services.errors import InvalidRequestError
from onecstarter.services.groups import GroupPatch, GroupPatchKind
from onecstarter.services.model import InfobaseSource
from onecstarter.services.writer import (
    ConcurrentEditError,
    EncodingRejectedError,
    write_patch,
)

NEW_ID = "99999999-9999-9999-9999-999999999999"
ONE_SECTION = "[Демо]\r\nConnect=File=\"C:\\Bases\\Demo\";\r\nID=abc\r\n".encode()

ADD = SectionPatch(PatchKind.ADD, name="Новая", changes={"Connect": 'File="C:\\Bases\\New";'})


def test_creates_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    payload, result = write_patch(path, ADD, NEW_ID)
    document = parse_v8i(path.read_bytes())
    assert [section.name for section in document.sections] == ["Новая"]
    assert payload == path.read_bytes()
    assert (result.applied, result.key) == (True, f"id:{NEW_ID}")


def test_reports_that_missing_remove_target_was_not_found(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    _, result = write_patch(path, SectionPatch(PatchKind.REMOVE, target_key="id:нет"), NEW_ID)
    assert (result.applied, result.key) == (False, None)


def test_appends_to_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    write_patch(path, ADD, NEW_ID)
    names = [section.name for section in parse_v8i(path.read_bytes()).sections]
    assert names == ["Демо", "Новая"]


def test_keeps_source_encoding(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes("[Демо]\r\nConnect=File=\"C:\\B\";\r\n".encode("cp1251"))
    write_patch(path, ADD, NEW_ID)
    data = path.read_bytes()
    assert "Новая".encode("cp1251") in data
    assert "Новая".encode() not in data


def test_external_change_is_replayed_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    original = atomic.atomic_write_if_unchanged
    state = {"first": True}

    def meddling(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        if state["first"]:
            state["first"] = False
            # Штатный стартер дописал свою секцию между нашим чтением и записью.
            target.write_bytes(
                ONE_SECTION + "[Чужая]\r\nConnect=File=\"C:\\Bases\\Other\";\r\n".encode()
            )
        original(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", meddling)
    write_patch(path, ADD, NEW_ID)
    names = [section.name for section in parse_v8i(path.read_bytes()).sections]
    assert names == ["Демо", "Чужая", "Новая"]


def test_gives_up_after_three_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    calls = {"count": 0}

    def always_changed(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        calls["count"] += 1
        raise atomic.ExternalChangeError("изменён извне")

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", always_changed)
    with pytest.raises(ConcurrentEditError):
        write_patch(path, ADD, NEW_ID)
    # Число попыток — ровно attempts=3, не "хотя бы одна" и не бесконечный цикл.
    assert calls["count"] == 3


def test_create_race_falls_back_to_normal_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Файла нет; пока мы пытаемся создать его эксклюзивно, кто-то (штатный
    стартер) успевает создать его первым. `_create` обязана вернуть `None`
    и не тронуть чужой файл — цикл идёт обычным путём и дописывает патч
    к тому, что уже лежит на диске.
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    original_open = Path.open
    state = {"first": True}

    def racing_open(
        self: Path, mode: str = "r", *args: object, **kwargs: object
    ) -> object:
        if mode == "xb" and state["first"]:
            state["first"] = False
            # Штатный стартер создал файл раньше, чем мы успели.
            self.write_bytes(ONE_SECTION)
            raise FileExistsError
        return original_open(self, mode, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", racing_open)
    write_patch(path, ADD, NEW_ID)
    names = [section.name for section in parse_v8i(path.read_bytes()).sections]
    assert names == ["Демо", "Новая"]


def test_unencodable_text_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ibases.v8i"
    # 0x98 — единственный неопределённый байт cp1251, поэтому файл не читается
    # ни в UTF-8, ни в cp1251 и достаётся фолбэку latin-1. Проверено: другие
    # «мусорные» байты (0x81, 0x8d, 0xff) в cp1251 разбираются, и тогда
    # кириллица записалась бы штатно.
    path.write_bytes(b"[Demo]\r\nConnect=File=\"C:\\B\";\r\nX=\x98\r\n")
    with pytest.raises(EncodingRejectedError):
        write_patch(path, SectionPatch(PatchKind.ADD, name="Кириллица", changes={}), NEW_ID)


def test_line_break_in_value_is_a_layer_error(tmp_path: Path) -> None:
    """UI ловит ServicesError, а не ValueError из слоя config."""  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    patch = SectionPatch(
        PatchKind.UPDATE, target_key="id:abc", changes={"Version": "8.3\r\n[Чужая]"}
    )
    with pytest.raises(InvalidRequestError):
        write_patch(path, patch, NEW_ID)
    assert path.read_bytes() == ONE_SECTION


def test_line_break_in_value_is_a_layer_error_on_create(tmp_path: Path) -> None:
    """Тот же перевод слоёв нужен и на пути создания файла: `_create` зовёт
    `apply_patch` отдельно от основного цикла, и без своей обёртки эта ветка
    выпустила бы `LineBreakRejectedError` из `config` мимо `ServicesError`.
    """
    path = tmp_path / "ibases.v8i"
    patch = SectionPatch(
        PatchKind.ADD, name="Новая", changes={"Connect": 'File="C:\\A";\r\n[Чужая]'}
    )
    with pytest.raises(InvalidRequestError):
        write_patch(path, patch, NEW_ID)
    assert not path.exists()


def test_group_cascade_is_computed_on_the_fresh_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Каскад обязан считаться по тому документу, в который мы пишем сейчас.
    Список целей, собранный до чтения свежего файла, пропустил бы базу,
    которую штатный стартер добавил в группу между нашими попытками, —
    и она осталась бы с Folder на исчезнувший путь.
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    group = "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n"
    path.write_bytes(group.encode())
    original = atomic.atomic_write_if_unchanged
    state = {"first": True}

    def meddling(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        if state["first"]:
            state["first"] = False
            target.write_bytes(
                (
                    group + '[Новая]\r\nConnect=File="C:\\Bases\\New";\r\n'
                    "ID=new\r\nFolder=/Клиенты\r\n"
                ).encode()
            )
        original(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", meddling)
    write_patch(
        path,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Партнёры"),
        NEW_ID,
    )
    folders = {
        section.id: section.folder for section in parse_v8i(path.read_bytes()).sections
    }
    assert folders["grp"] == "/"
    assert folders["new"] == "/Партнёры"


# -- ReorderPatch: перестановка внутри группы, записанная на диск (задача 15) --

_THREE = (
    '[Первая]\r\nConnect=File="D:\\a";\r\nID=11111111-1111-1111-1111-111111111111\r\n'
    "OrderInList=10\r\n"
    '[Вторая]\r\nConnect=File="D:\\b";\r\nID=22222222-2222-2222-2222-222222222222\r\n'
    "OrderInList=20\r\n"
    '[Третья]\r\nConnect=File="D:\\c";\r\nID=33333333-3333-3333-3333-333333333333\r\n'
    "OrderInList=30\r\n"
)


def test_reorder_writes_only_the_moved_section(tmp_path: Path) -> None:
    """Зазор есть — меняется одно значение, соседние секции не тронуты."""
    path = tmp_path / "ibases.v8i"
    path.write_bytes(_THREE.encode("utf-8"))

    payload, result = write_patch(
        path,
        ReorderPatch(
            target_key="id:33333333-3333-3333-3333-333333333333",
            after_key="id:11111111-1111-1111-1111-111111111111",
        ),
        "unused",
    )

    assert result.applied
    text = payload.decode("utf-8")
    assert "OrderInList=15" in text
    assert "OrderInList=10" in text
    assert "OrderInList=20" in text
    assert "OrderInList=30" not in text


def test_reorder_to_the_same_place_does_not_touch_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Промах мышью (перестановка на своё же место) — рядовое событие;
    атомарная замена файла, который может в этот момент держать штатный
    стартер, — нет (круг правок 1 ревью задачи 15).
    """
    path = tmp_path / "ibases.v8i"
    path.write_bytes(_THREE.encode("utf-8"))
    calls = {"count": 0}

    def tracking(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        calls["count"] += 1
        atomic.atomic_write_if_unchanged(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", tracking)

    payload, result = write_patch(
        path,
        # «Первая» и так первая в группе — after=None просит то же самое место.
        ReorderPatch(
            target_key="id:11111111-1111-1111-1111-111111111111", after_key=None
        ),
        "unused",
    )

    assert result.applied
    assert calls["count"] == 0
    assert payload == _THREE.encode("utf-8")
    assert path.read_bytes() == _THREE.encode("utf-8")


def test_update_with_the_same_connect_does_not_touch_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`payload == data` в `write_patch` — общая проверка, не только для
    `ReorderPatch` (ревью, круг правок 2: закреплено тестом хотя бы ещё на
    одном виде патча). Диалог свойств открыли и закрыли без правок —
    `changes` содержит то же значение `Connect`, что уже в файле.
    """
    path = tmp_path / "ibases.v8i"
    path.write_bytes(ONE_SECTION)
    calls = {"count": 0}

    def tracking(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        calls["count"] += 1
        atomic.atomic_write_if_unchanged(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", tracking)

    payload, result = write_patch(
        path,
        SectionPatch(
            PatchKind.UPDATE,
            target_key="id:abc",
            changes={"Connect": 'File="C:\\Bases\\Demo";'},
        ),
        NEW_ID,
    )

    assert result.applied
    assert calls["count"] == 0
    assert payload == ONE_SECTION


def test_retarget_group_to_the_same_name_does_not_touch_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Тот же общий фикс на `GroupPatch.RETARGET`: переименование группы
    в то же имя (диалог открыли и закрыли без правок) не пишет файл.
    """
    path = tmp_path / "ibases.v8i"
    group = "[Клиенты]\r\nID=grp\r\nOrderInList=-1\r\nFolder=/\r\n".encode()
    path.write_bytes(group)
    calls = {"count": 0}

    def tracking(target: Path, data: bytes, snapshot: atomic.FileSnapshot) -> None:
        calls["count"] += 1
        atomic.atomic_write_if_unchanged(target, data, snapshot)

    monkeypatch.setattr("onecstarter.services.writer.atomic_write_if_unchanged", tracking)

    payload, result = write_patch(
        path,
        GroupPatch(GroupPatchKind.RETARGET, target_key="id:grp", new_name="Клиенты"),
        NEW_ID,
    )

    assert result.applied
    assert calls["count"] == 0
    assert payload == group


def test_reorder_renumbers_group_when_no_gap(tmp_path: Path) -> None:
    """Все соседи с OrderInList=-1 — так выглядит список после наших добавлений.

    `edit._apply_add` пишет -1 каждой новой записи, поэтому равные соседи
    у нас норма. Пересчитывается одна группа, файл целиком не переписывается
    (скил v8i-format, факт 5).
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    path.write_bytes(
        _THREE.replace("OrderInList=10", "OrderInList=-1")
        .replace("OrderInList=20", "OrderInList=-1")
        .replace("OrderInList=30", "OrderInList=-1")
        .encode("utf-8")
    )

    payload, _result = write_patch(
        path,
        ReorderPatch(
            target_key="id:33333333-3333-3333-3333-333333333333", after_key=None
        ),
        "unused",
    )

    text = payload.decode("utf-8")
    assert "OrderInList=-1" not in text
    # Значения в файловом порядке секций: Первая, Вторая, Третья.
    # Третья ушла в начало, поэтому её значение наименьшее.
    values = [
        int(line.split("=")[1])
        for line in text.splitlines()
        if line.startswith("OrderInList=")
    ]
    assert values == [1, 2, 0]


def test_reorder_refuses_anchor_from_another_group(tmp_path: Path) -> None:
    """Ставить «после» записи из чужой группы бессмысленно — это перенос."""
    path = tmp_path / "ibases.v8i"
    path.write_bytes(
        (
            _THREE
            + "[Клиенты]\r\nID=44444444-4444-4444-4444-444444444444\r\n"
            "OrderInList=-1\r\nFolder=/\r\nExternal=0\r\n"
            '[Внутри]\r\nConnect=File="D:\\d";\r\n'
            "ID=55555555-5555-5555-5555-555555555555\r\n"
            "OrderInList=5\r\nFolder=/Клиенты\r\n"
        ).encode("utf-8")
    )

    with pytest.raises(InvalidRequestError):
        write_patch(
            path,
            ReorderPatch(
                target_key="id:11111111-1111-1111-1111-111111111111",
                after_key="id:55555555-5555-5555-5555-555555555555",
            ),
            "unused",
        )


def test_reorder_achieves_the_requested_order_end_to_end(tmp_path: Path) -> None:
    """Сквозной прогон apply_patch → serialize → parse → items_from_document.

    Найдено ревью (круг правок 1, задача 15): «П» и «Н» — реальные соседние
    значения платформы (`60.6814814814813`/`60.6814814814814`, скил
    v8i-format, факт 5), «М» — секция, которую переставляем между ними
    (`after_key="П"`). «М» стоит ПЕРВОЙ в файле, до правки — если среднее
    round-trip-коллидирует с «П» (была найдена именно эта коллизия), тай-брейк
    стабильной сортировки по файловому порядку отдаёт «М» перед «П», и вместо
    запрошенного «П, М, Н» получается «М, П, Н».
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    path.write_bytes(
        (
            '[М]\r\nConnect=File="D:\\m";\r\nID=11111111-1111-1111-1111-111111111111\r\n'  # noqa: RUF001
            "OrderInList=100\r\n"
            '[П]\r\nConnect=File="D:\\p";\r\nID=22222222-2222-2222-2222-222222222222\r\n'
            "OrderInList=60.6814814814813\r\n"
            '[Н]\r\nConnect=File="D:\\n";\r\nID=33333333-3333-3333-3333-333333333333\r\n'  # noqa: RUF001
            "OrderInList=60.6814814814814\r\n"
        ).encode()
    )

    payload, _result = write_patch(
        path,
        ReorderPatch(
            target_key="id:11111111-1111-1111-1111-111111111111",
            after_key="id:22222222-2222-2222-2222-222222222222",
        ),
        "unused",
    )

    document = parse_v8i(payload)
    items = items_from_document(document, InfobaseSource.USER, {})
    assert [item.name for item in items] == ["П", "М", "Н"]  # noqa: RUF001


def test_reorder_falls_back_to_renumber_before_writing_scientific_notation(
    tmp_path: Path,
) -> None:
    """14 обычных перетаскиваний записи под первую — не синтетика, рядовая
    работа внутри одной группы (находка ревью, круг правок 2, задача 15).

    Каждая новая запись добавляется обычным `ADD` (`OrderInList=-1`) и сразу
    переставляется «после A» — так же, как пользователь тащит мышью только
    что добавленную базу к началу группы. Это сжимает зазор между A и самой
    свежей записью вдвое на каждом шаге. На 14-м шаге зазор дошёл бы
    до `2⁻¹⁴`, и `format_order` отдал бы научную нотацию
    (`"6.103515625e-05"`); вместо этого срабатывает пересчёт группы — в файле
    только целые.
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    path.write_bytes(

            b'[A]\r\nConnect=File="D:\\a";\r\nID=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\r\n'
            b"OrderInList=0\r\n"
            b'[B]\r\nConnect=File="D:\\b";\r\nID=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\r\n'
            b"OrderInList=1\r\n"
            b'[C]\r\nConnect=File="D:\\c";\r\nID=cccccccc-cccc-cccc-cccc-cccccccccccc\r\n'
            b"OrderInList=2\r\n"

    )
    a_key = "id:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    for i in range(14):
        new_id = f"n{i:02d}"
        write_patch(
            path,
            SectionPatch(
                PatchKind.ADD, name=f"N{i}", changes={"Connect": f'File="D:\\n{i}";'}
            ),
            new_id,
        )
        write_patch(
            path, ReorderPatch(target_key=f"id:{new_id}", after_key=a_key), "unused"
        )

    document = parse_v8i(path.read_bytes())
    assert len(document.sections) == 17  # A, B, C + 14 добавленных
    values = [section.get("OrderInList") for section in document.sections]
    assert all(value is not None and "e" not in value.lower() for value in values)


def test_reorder_preserves_order_with_very_large_neighbor_values(tmp_path: Path) -> None:
    """Находка ревью (круг правок 2, задача 15): `_between(1000000000000002.0,
    None)` раньше давал `1000000000000003.0`, который `format_order` пишет
    как `"1e+15"`, а читается обратно как `1e15 == 1000000000000000.0` —
    МЕНЬШЕ соседа. Запрошено «Малая после Большой», получалось «Малая
    до Большой».

    Достижимость узкая — такие значения `OrderInList` не встречаются
    в природе (скил v8i-format, факт 5: реальные значения на девять
    порядков меньше), но раз они возможны в файле (ручная правка, перенос
    из другой системы), патч обязан сохранять порядок и на них.
    """  # noqa: RUF002
    path = tmp_path / "ibases.v8i"
    path.write_bytes(
        (
            '[Малая]\r\nConnect=File="D:\\s";\r\nID=11111111-1111-1111-1111-111111111111\r\n'
            "OrderInList=5\r\n"
            '[Большая]\r\nConnect=File="D:\\b";\r\n'
            "ID=22222222-2222-2222-2222-222222222222\r\n"
            "OrderInList=1000000000000002\r\n"
        ).encode()
    )

    payload, _result = write_patch(
        path,
        ReorderPatch(
            target_key="id:11111111-1111-1111-1111-111111111111",
            after_key="id:22222222-2222-2222-2222-222222222222",
        ),
        "unused",
    )

    document = parse_v8i(payload)
    items = items_from_document(document, InfobaseSource.USER, {})
    assert [item.name for item in items] == ["Большая", "Малая"]
