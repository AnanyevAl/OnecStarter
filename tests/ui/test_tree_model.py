from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.availability import Availability
from onecstarter.services.display import MISSING_SUFFIX, Row, RowKind, VersionCell
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui import theme
from onecstarter.ui.bases.tree_model import COLUMNS, KEY_ROLE, KIND_ROLE, build_model


def _stamp(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")


def _base_row(
    key: str = "id:aaa",
    label: str = "Демо",
    note: str | None = None,
    launched: datetime | None = None,
) -> Row:
    item = InfobaseItem(
        key=key,
        name=label,
        folder="/",
        is_group=False,
        connect='File="C:\\B";',
        kind=ConnectKind.FILE,
        requested_version="8.3.25",
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id=None,
        last_launched_at=launched,
    )
    return Row(RowKind.BASE, label, item, (), note)


def _file_item(key: str = "id:file", label: str = "Файловая") -> InfobaseItem:
    return InfobaseItem(
        key=key,
        name=label,
        folder="/",
        is_group=False,
        connect=r'File="D:\bases\acc";',
        kind=ConnectKind.FILE,
        requested_version="8.3.25",
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id=None,
    )


def _group_item(key: str = "grp:клиенты", label: str = "Клиенты") -> InfobaseItem:
    return InfobaseItem(
        key=key,
        name=label,
        folder="/Клиенты",
        is_group=True,
        connect=None,
        kind=ConnectKind.UNKNOWN,
        requested_version=None,
        section_default_version=None,
        app=None,
        source=InfobaseSource.USER,
        order=None,
        section_id=None,
    )


def test_model_has_columns_and_hierarchy(qtbot):
    rows = [
        Row(RowKind.SECTION, "Избранное", None, (_base_row(),)),
        Row(RowKind.GROUP, "Клиенты", _base_row(label="Клиенты").item, (_base_row(key="id:bbb"),)),
    ]
    cells = {"id:aaa": VersionCell("8.3.25.1633 x64", False, None)}
    model = build_model(rows, cells, _stamp, theme.DARK)
    assert [
        model.headerData(i, Qt.Orientation.Horizontal) for i in range(len(COLUMNS))
    ] == list(COLUMNS)
    assert model.rowCount() == 2
    section = model.item(0, 0)
    assert section.rowCount() == 1
    base = section.child(0, 0)
    assert base.data(KEY_ROLE) == "id:aaa"
    assert base.data(KIND_ROLE) == RowKind.BASE.value
    assert section.child(0, 1).text() == "8.3.25.1633 x64"


def test_problem_cell_is_highlighted_and_hint_in_tooltip(qtbot):
    cell = VersionCell(
        "8.3.99.1 — не установлена", True, "Штатный стартер молча запустил бы 8.3.27.2214"
    )
    model = build_model([_base_row()], {"id:aaa": cell}, _stamp, theme.DARK)
    version_item = model.item(0, 1)
    assert version_item.text() == "8.3.99.1 — не установлена"
    assert "8.3.27.2214" in version_item.toolTip()
    assert version_item.foreground().color().name() != model.item(0, 0).foreground().color().name()


def test_launch_stamp_is_formatted(qtbot):
    launched = datetime(2026, 8, 5, tzinfo=UTC)
    model = build_model([_base_row(launched=launched)], {}, _stamp, theme.DARK)
    assert model.item(0, 2).text() == "05.08.2026"


def test_implicit_group_is_dimmed_with_note(qtbot):
    row = Row(RowKind.IMPLICIT_GROUP, "Нет такой группы", None, (), "группы нет в файле")
    model = build_model([row], {}, _stamp, theme.DARK)
    name = model.item(0, 0)
    assert name.data(KEY_ROLE) is None
    assert "нет в файле" in name.toolTip()


def test_common_list_marker_suffix(qtbot):
    row = _base_row()
    marked = Row(row.kind, row.label, replace(row.item, in_common_list=True), (), None)  # type: ignore[type-var]
    model = build_model([marked], {}, _stamp, theme.DARK)
    assert model.item(0, 0).text() == "Демо (в общем списке)"


def test_broken_record_is_marked_in_label_and_colour(qtbot):
    # Спека 4a, §2: битая запись показывается с пометкой «не разобрано».  # noqa: RUF003
    # Тултипа мало — раздел рассчитан на работу с клавиатуры, наведение  # noqa: RUF003
    # мышью не подразумевается (находка финального ревью 07.08.2026).
    row = _base_row(note="Не разобрано: строка 3 не прочитана")  # noqa: RUF001
    item = replace(row.item, parse_error="строка 3 не прочитана")  # type: ignore[type-var]
    broken = Row(row.kind, row.label, item, (), row.note)
    # Модели держим переменными: без ссылки QStandardItemModel собирается
    # сборщиком мусора вместе со своими QStandardItem.  # noqa: RUF003
    healthy_model = build_model([_base_row()], {}, _stamp, theme.DARK)
    broken_model = build_model([broken], {}, _stamp, theme.DARK)
    healthy = healthy_model.item(0, 0)
    name = broken_model.item(0, 0)
    assert name.text() == "Демо (не разобрано)"
    assert "строка 3 не прочитана" in name.toolTip()
    assert name.foreground().color().name() != healthy.foreground().color().name()


def test_base_rows_get_a_placement_icon(qapp: QApplication) -> None:
    rows = [Row(RowKind.BASE, "Файловая", _file_item())]
    model = build_model(rows, {}, _stamp, theme.DARK)
    assert not model.item(0, 0).icon().isNull()
    assert model.item(0, 0).toolTip().endswith("файловая база")


def test_groups_have_no_placement_icon(qapp: QApplication) -> None:
    """Группу отличает структура дерева; значок конкурировал бы со значком базы."""  # noqa: RUF002
    rows = [Row(RowKind.GROUP, "Клиенты", _group_item())]
    model = build_model(rows, {}, _stamp, theme.DARK)
    assert model.item(0, 0).icon().isNull()


def _model_with(availability: dict[str, Availability]) -> QStandardItemModel:
    row = Row(RowKind.BASE, "Файловая", _file_item())
    return build_model([row], {}, _stamp, theme.DARK, availability=availability)


def test_missing_base_gets_the_suffix(qapp: QApplication) -> None:
    model = _model_with({"id:file": Availability.MISSING})
    assert model.item(0, 0).text() == f"Файловая {MISSING_SUFFIX}"


def test_missing_base_tooltip_names_the_directory(qapp: QApplication) -> None:
    model = _model_with({"id:file": Availability.MISSING})
    assert r"Каталог не найден: D:\bases\acc" in model.item(0, 0).toolTip()


def test_present_base_carries_no_mark(qapp: QApplication) -> None:
    model = _model_with({"id:file": Availability.PRESENT})
    assert model.item(0, 0).text() == "Файловая"
    assert "Каталог не найден" not in model.item(0, 0).toolTip()


def test_unknown_state_carries_no_mark(qapp: QApplication) -> None:
    """Пока проход идёт, крестика нет — иначе список на старте весь битый (спека §1)."""
    model = _model_with({"id:file": Availability.UNKNOWN})
    assert model.item(0, 0).text() == "Файловая"


def test_record_absent_from_the_mapping_is_unknown(qapp: QApplication) -> None:
    model = _model_with({})
    assert model.item(0, 0).text() == "Файловая"


def test_availability_defaults_to_nothing_marked(qapp: QApplication) -> None:
    row = Row(RowKind.BASE, "Файловая", _file_item())
    model = build_model([row], {}, _stamp, theme.DARK)
    assert model.item(0, 0).text() == "Файловая"


def test_missing_base_icon_differs_from_present(qapp: QApplication) -> None:
    # Модели держим переменными: без ссылки QStandardItemModel собирается
    # сборщиком мусора вместе со своими QStandardItem (как в тесте выше про  # noqa: RUF003
    # битую запись) — иначе .icon() валится на удалённом C++ объекте.
    missing_model = _model_with({"id:file": Availability.MISSING})
    present_model = _model_with({"id:file": Availability.PRESENT})
    missing = missing_model.item(0, 0)
    present = present_model.item(0, 0)
    assert (
        missing.icon().pixmap(16, 16).toImage()
        != present.icon().pixmap(16, 16).toImage()
    )


def test_relative_path_gets_an_honest_note(qapp: QApplication) -> None:
    """Относительный путь не проверяется — и тултип об этом говорит (спека §2)."""  # noqa: RUF002
    item = replace(_file_item(), connect='File="bases\\acc";')
    row = Row(RowKind.BASE, "Относительная", item)
    model = build_model([row], {}, _stamp, theme.DARK, availability={})
    assert "Путь относительный" in model.item(0, 0).toolTip()
    assert model.item(0, 0).text() == "Относительная"
