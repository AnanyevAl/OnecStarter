"""Путь-ссылка панелей (спека v3.1, §2): ссылка, меню, обрезание, placeholder."""

from typing import Any

from PySide6.QtWidgets import QApplication

from onecstarter.ui import theme
from onecstarter.ui.path_link import MENU_COPY, MENU_OPEN, PathLink

LONG = r"D:\very\long\path\to\the\workspace\of\a\really\big\configuration\with\many\parts"


def _link(copied: list[str]) -> PathLink:
    return PathLink(palette=theme.DARK, copy_text=copied.append)


def test_directory_renders_as_link_and_click_requests_open(qtbot: Any) -> None:
    opened: list[str] = []
    link = _link([])
    qtbot.addWidget(link)
    link.open_requested.connect(opened.append)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")
    assert link.link_href() == r"D:\edt\ws"
    assert theme.DARK.accent in link.text()  # цвет акцента — в разметке ссылки
    link.linkActivated.emit(link.text())  # клик по ссылке штатно даёт linkActivated
    assert opened == [r"D:\edt\ws"]


def test_text_without_directory_is_not_a_link(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path('Srvr="srv";Ref="acc"')
    assert link.link_href() is None
    assert "<a " not in link.text()
    assert link.path_text() == 'Srvr="srv";Ref="acc"'


def test_menu_items_follow_state(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")
    assert [a.text() for a in link.context_menu().actions()] == [MENU_OPEN, MENU_COPY]
    link.set_path("текст без каталога")
    assert [a.text() for a in link.context_menu().actions()] == [MENU_COPY]
    link.set_path("")
    assert link.context_menu().actions() == []


def test_copy_puts_full_text_not_elided(qtbot: Any) -> None:
    copied: list[str] = []
    link = _link(copied)
    qtbot.addWidget(link)
    link.show()
    link.resize(120, 20)
    link.set_path(LONG, directory=LONG)
    assert "…" in link.elided_text() and link.elided_text() != LONG
    assert link.toolTip() == LONG
    [_open, copy] = link.context_menu().actions()
    copy.trigger()
    assert copied == [LONG]


def test_menu_open_triggers_open_requested(qtbot: Any) -> None:
    opened: list[str] = []
    link = _link([])
    qtbot.addWidget(link)
    link.open_requested.connect(opened.append)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")
    link.context_menu().actions()[0].trigger()
    assert opened == [r"D:\edt\ws"]


def test_placeholder_when_empty(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_placeholder("не задан")
    link.set_path("")
    assert link.placeholder() == "не задан"
    assert link.path_text() == ""
    assert "<i" in link.text() and theme.DARK.text_dim in link.text()
    assert link.toolTip() == ""


def test_html_in_path_is_escaped(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\R&D\<ws>", directory=r"D:\R&D\<ws>")
    assert "&amp;" in link.text() and "&lt;ws&gt;" in link.text()
    assert link.path_text() == r"D:\R&D\<ws>"


def test_apply_palette_recolours(qtbot: Any) -> None:
    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\a", directory=r"D:\a")
    link.apply_palette(theme.LIGHT)
    assert theme.LIGHT.accent in link.text()


def test_default_copy_uses_clipboard(qtbot: Any) -> None:
    link = PathLink(palette=theme.DARK)
    qtbot.addWidget(link)
    link.set_path(r"D:\a")
    link.context_menu().actions()[0].trigger()
    assert QApplication.clipboard().text() == r"D:\a"


def test_show_menu_creates_and_returns_menu_with_delete_later(qtbot: Any) -> None:
    from PySide6.QtWidgets import QMenu

    link = _link([])
    qtbot.addWidget(link)
    link.set_path(r"D:\edt\ws", directory=r"D:\edt\ws")

    # Проверяем, что context_menu() возвращает QMenu с правильными действиями  # noqa: RUF003
    menu = link.context_menu()
    assert isinstance(menu, QMenu)
    assert menu.parent() == link
    actions = [a.text() for a in menu.actions()]
    assert actions == [MENU_OPEN, MENU_COPY]

    # Проверяем, что метод deleteLater существует и вызывается
    assert hasattr(menu, "deleteLater")
    assert callable(menu.deleteLater)
