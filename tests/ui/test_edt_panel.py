"""Панель путей под деревом раздела «EDT»: пути-ссылки (спека v3.1, §3)."""

from onecstarter.domain.edt import EdtProject
from onecstarter.ui import theme
from onecstarter.ui.edt.panel import (
    CAPTION_PROJECT_DIR,
    CAPTION_WORKSPACE,
    PLACEHOLDER_NO_PROJECT_DIR,
    PLACEHOLDER_NONE,
    EdtPanel,
)
from onecstarter.ui.path_link import MENU_COPY, MENU_OPEN


def _panel(opened: list[str], copied: list[str], ok: bool = True) -> EdtPanel:
    def open_directory(path: str) -> bool:
        opened.append(path)
        return ok

    return EdtPanel(open_directory=open_directory, copy_text=copied.append)


def test_empty_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    assert panel.title_text() == PLACEHOLDER_NONE
    assert panel.workspace_link().isHidden() is True
    assert panel.project_dir_link().isHidden() is True


def test_captions_say_workspace_in_russian(qtbot) -> None:  # type: ignore[no-untyped-def]
    assert CAPTION_WORKSPACE == "Рабочая область"
    assert CAPTION_PROJECT_DIR == "Каталог проекта"
    assert PLACEHOLDER_NO_PROJECT_DIR == "не задан — редакторы получают рабочую область"


def test_project_with_both_paths_as_links(qtbot) -> None:  # type: ignore[no-untyped-def]
    opened: list[str] = []
    copied: list[str] = []
    panel = _panel(opened, copied)
    qtbot.addWidget(panel)
    panel.show_project(
        EdtProject("p", "Розница", r"D:\edt\retail", project_dir=r"D:\git\retail"), theme.DARK
    )
    assert panel.title_text() == "Розница"
    assert panel.workspace_link().path_text() == r"D:\edt\retail"
    assert panel.workspace_link().link_href() == r"D:\edt\retail"
    assert panel.project_dir_link().link_href() == r"D:\git\retail"
    assert panel.workspace_link().isHidden() is False
    panel.workspace_link().linkActivated.emit("")
    [_open, copy] = panel.project_dir_link().context_menu().actions()
    assert [_open.text(), copy.text()] == [MENU_OPEN, MENU_COPY]
    copy.trigger()
    assert opened == [r"D:\edt\retail"]
    assert copied == [r"D:\git\retail"]


def test_project_without_project_dir(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "Опт", r"D:\edt\w"), theme.DARK)
    assert panel.project_dir_link().path_text() == ""
    assert panel.project_dir_link().placeholder() == PLACEHOLDER_NO_PROJECT_DIR
    assert panel.project_dir_link().link_href() is None
    assert panel.project_dir_link().context_menu().actions() == []


def test_group_shows_only_title(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_group("2025")
    assert panel.title_text() == "2025"
    assert panel.workspace_link().isHidden() is True


def test_open_failure_reported(qtbot) -> None:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    panel = EdtPanel(open_directory=lambda p: False, copy_text=lambda t: None)
    panel.open_failed.connect(errors.append)
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "a", r"D:\gone"), theme.DARK)
    panel.workspace_link().linkActivated.emit("")
    assert errors == [r"Каталог не найден: D:\gone"]


def test_palette_reaches_links(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "a", r"D:\w"), theme.LIGHT)
    assert theme.LIGHT.accent in panel.workspace_link().text()
