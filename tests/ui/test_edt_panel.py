"""Панель путей под деревом раздела «EDT» (решение заказчика 11.09.2026)."""

from onecstarter.domain.edt import EdtProject
from onecstarter.ui import theme
from onecstarter.ui.edt.panel import PLACEHOLDER_NO_PROJECT_DIR, PLACEHOLDER_NONE, EdtPanel


def _panel(opened: list[str], copied: list[str], ok: bool = True) -> EdtPanel:
    def open_directory(path: str) -> bool:
        opened.append(path)
        return ok

    return EdtPanel(open_directory=open_directory, copy_text=copied.append)


def test_empty_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    assert panel.title_text() == PLACEHOLDER_NONE
    assert panel.workspace_field().isHidden() is True
    assert panel.project_dir_field().isHidden() is True


def test_project_with_both_paths(qtbot) -> None:  # type: ignore[no-untyped-def]
    opened: list[str] = []
    copied: list[str] = []
    panel = _panel(opened, copied)
    qtbot.addWidget(panel)
    panel.show_project(
        EdtProject("p", "Розница", r"D:\edt\retail", project_dir=r"D:\git\retail"), theme.DARK
    )
    assert panel.title_text() == "Розница"
    assert panel.workspace_field().text() == r"D:\edt\retail"
    assert panel.project_dir_field().text() == r"D:\git\retail"
    assert panel.workspace_field().isHidden() is False
    panel.workspace_open_button().click()
    panel.project_dir_copy_button().click()
    assert opened == [r"D:\edt\retail"]
    assert copied == [r"D:\git\retail"]


def test_project_without_project_dir(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "Опт", r"D:\edt\w"), theme.DARK)
    assert panel.project_dir_field().text() == ""
    assert panel.project_dir_field().placeholderText() == PLACEHOLDER_NO_PROJECT_DIR
    assert panel.project_dir_field().font().italic() is True
    assert panel.project_dir_open_button().isEnabled() is False
    assert panel.project_dir_copy_button().isEnabled() is False


def test_group_shows_only_title(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _panel([], [])
    qtbot.addWidget(panel)
    panel.show_group("2025")
    assert panel.title_text() == "2025"
    assert panel.workspace_field().isHidden() is True


def test_open_failure_reported(qtbot) -> None:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    panel = EdtPanel(open_directory=lambda p: False, copy_text=lambda t: None)
    panel.open_failed.connect(errors.append)
    qtbot.addWidget(panel)
    panel.show_project(EdtProject("p", "a", r"D:\gone"), theme.DARK)
    panel.workspace_open_button().click()
    assert errors == [r"Каталог не найден: D:\gone"]
