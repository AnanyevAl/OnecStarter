"""Панель пути подключения: показ, копирование, открытие каталога."""

from typing import Any

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.services.connection import panel_card
from onecstarter.services.display import RowKind
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.ui import theme
from onecstarter.ui.bases.panel import ConnectionPanel


def _item(connect: str | None, *, is_group: bool = False) -> InfobaseItem:
    return InfobaseItem(
        key="id:x", name="База", folder="/", is_group=is_group, connect=connect,
        kind=classify_connect(connect) if connect else ConnectKind.UNKNOWN,
        requested_version=None, section_default_version=None, app=None,
        source=InfobaseSource.USER, order=None, section_id="x",
    )


def _panel(qtbot: Any, opened: list[str]) -> ConnectionPanel:
    def open_directory(path: str) -> bool:
        opened.append(path)
        return True

    panel = ConnectionPanel(open_directory=open_directory)
    qtbot.addWidget(panel)
    return panel


def _show(panel: ConnectionPanel, item: InfobaseItem | None) -> None:
    kind = None if item is None else RowKind.BASE
    panel.show_card(panel_card(kind, item, ""), theme.DARK)


def test_shows_server_path_with_title_and_kind_word(qtbot: Any) -> None:
    panel = _panel(qtbot, [])
    _show(panel, _item('Srvr="localhost";Ref="ACC";'))
    assert panel.text() == 'Srvr="localhost";Ref="ACC"'
    assert panel.title_text() == "База · серверная"


def test_group_and_empty_selection_show_hints_not_emptiness(qtbot: Any) -> None:
    """Панель никогда не пустеет (мокап): группа и пустой выбор объясняются."""
    panel = _panel(qtbot, [])
    panel.show_card(
        panel_card(RowKind.GROUP, _item(None, is_group=True), ""), theme.DARK
    )
    assert panel.text() == ""
    assert panel.placeholder() == "Группа — строки подключения нет"
    assert panel.copy_button().isHidden()

    panel.show_card(panel_card(None, None, ""), theme.DARK)
    assert panel.placeholder() == "Выберите базу, чтобы увидеть путь подключения"


def test_note_is_shown_instead_of_path(qtbot: Any) -> None:
    panel = _panel(qtbot, [])
    _show(panel, _item("Нечто=1;"))
    assert panel.text() == ""
    assert "не распознана" in panel.placeholder()


def test_copy_puts_shown_text_in_clipboard(qtbot: Any) -> None:
    """В буфер идёт ровно то, что на экране — очищенный адрес (§1.4)."""  # noqa: RUF002
    panel = _panel(qtbot, [])
    _show(panel, _item('ws="http://user:pass@srv/base";'))
    assert panel.copy_button().isEnabled()
    panel.copy_button().click()
    assert QApplication.clipboard().text() == "http://srv/base"


def test_open_directory_enabled_only_for_file_kind(qtbot: Any) -> None:
    """Мокап: у серверной базы кнопка видна, но неактивна — не спрятана."""  # noqa: RUF002
    opened: list[str] = []
    panel = _panel(qtbot, opened)

    _show(panel, _item('Srvr="localhost";Ref="ACC";'))
    assert not panel.open_button().isEnabled()

    _show(panel, _item(r'File="D:\bases\acc";'))
    assert panel.open_button().isEnabled()
    panel.open_button().click()
    assert opened == [r"D:\bases\acc"]


@pytest.mark.parametrize("palette", [theme.DARK, theme.LIGHT], ids=["dark", "light"])
def test_hint_placeholder_uses_the_dim_role_from_the_project_palette(
    qtbot: Any, palette: theme.Palette
) -> None:
    """Important 1 финального ревью: подсказка красится палитрой проекта.

    QLineEdit.placeholderText Qt берёт цвет из СИСТЕМНОЙ QPalette —
    ThemeController применяет только stylesheet, placeholder мимо него.
    Замер: 2,49:1 в тёмной, 2,15:1 в светлой — порог проекта 4,5:1.
    show_card обязан выставлять QPalette.ColorRole.PlaceholderText поля
    из переданной палитры при каждом вызове.
    """
    panel = _panel(qtbot, [])
    panel.show_card(panel_card(None, None, ""), palette)
    colour = panel.path_field().palette().color(QPalette.ColorRole.PlaceholderText)
    assert colour == QColor(palette.text_dim)


def test_hint_card_shows_the_placeholder_in_italics(qtbot: Any) -> None:
    """Мокап: подсказка курсивом — панель никогда не пустеет, но отличима от пути."""
    panel = _panel(qtbot, [])
    panel.show_card(panel_card(None, None, ""), theme.DARK)
    assert panel.path_field().font().italic()


def test_path_card_shows_the_path_upright(qtbot: Any) -> None:
    """Обратная сторона: показан путь — курсив снят."""
    panel = _panel(qtbot, [])
    _show(panel, _item('Srvr="localhost";Ref="ACC";'))
    assert not panel.path_field().font().italic()


def test_open_failure_shows_a_warning_not_silence(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Каталога нет → сообщение, не тишина» (бриф): открытие отказало."""
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text)
    )
    panel = ConnectionPanel(open_directory=lambda _path: False)
    qtbot.addWidget(panel)
    _show(panel, _item(r'File="D:\bases\acc";'))
    panel.open_button().click()
    assert warnings == [r"Не удалось открыть каталог: D:\bases\acc"]  # noqa: RUF001
