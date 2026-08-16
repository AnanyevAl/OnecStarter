from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from onecstarter.domain.connect import ConnectKind
from onecstarter.services.display import Row, RowKind, VersionCell
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
