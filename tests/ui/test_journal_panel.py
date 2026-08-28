"""Панель «Журнал профиля» (T-10, задача 5): показ, плейсхолдер, live tail.

Файл журнала строится напрямую в `tmp_path` — никакого `ServersWorkspace`
тут не нужно, панель работает с голым путём (интерфейс `show_journal`).
Таймер в тестах не участвует нигде (спека брифа): любое обновление
проверяется через явный `refresh()`, а не ожидание тика.
"""  # noqa: RUF002

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from onecstarter.ui import theme
from onecstarter.ui.servers.journal_panel import JournalPanel


@pytest.fixture
def application(qapp: QApplication) -> QApplication:
    return qapp


def _panel(qtbot: Any, palette: theme.Palette = theme.DARK) -> JournalPanel:
    panel = JournalPanel(palette=palette)
    qtbot.addWidget(panel)
    return panel


def test_shows_file_contents(application: QApplication, tmp_path: Path, qtbot: Any) -> None:
    path = tmp_path / "p1.log"
    path.write_text("[10:00:00] запуск: ragent.exe\n[10:00:05] PID 100\n", encoding="utf-8")
    panel = _panel(qtbot)

    panel.show_journal("8.3.25 отладка", path)

    assert "запуск: ragent.exe" in panel.text()
    assert "PID 100" in panel.text()


def test_placeholder_shown_when_no_profile_selected(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """`path is None` — плейсхолдер «выберите профиль», текст журнала пуст."""
    panel = _panel(qtbot)

    panel.show_journal("Профиль, который не выбран", None)

    assert panel.text() == ""
    assert "профиль" in panel.placeholder().casefold()


def test_selecting_profile_clears_the_placeholder_even_with_empty_log(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """Пустой журнал только что созданного профиля — не то же самое, что «не выбран»."""
    path = tmp_path / "fresh.log"
    panel = _panel(qtbot)
    panel.show_journal("Профиль", None)
    assert panel.placeholder() != ""

    panel.show_journal("Новый профиль", path)

    assert panel.text() == ""
    assert panel.placeholder() == ""


def test_refresh_picks_up_appended_lines(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    path = tmp_path / "p1.log"
    path.write_text("[10:00:00] запуск: ragent.exe\n", encoding="utf-8")
    panel = _panel(qtbot)
    panel.show_journal("8.3.25 отладка", path)
    assert "PID 200" not in panel.text()

    with path.open("a", encoding="utf-8") as handle:
        handle.write("[10:00:06] PID 200\n")
    panel.refresh()

    assert "PID 200" in panel.text()


def test_broken_bytes_do_not_crash_the_panel(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: чужой (не наш UTF-8) кусок вывода не роняет панель.

    Платформенный stdout (второй писатель того же файла, [Ф] А1/А4 T-09)
    может нести произвольную кодировку — журнал не наш собственный текст
    целиком. Мутация «decode без errors="replace"» (или без try/except
    вокруг чтения) обязана уронить этот тест исключением `UnicodeDecodeError`.
    """  # noqa: RUF002
    path = tmp_path / "p1.log"
    path.write_bytes(b"[10:00:00] \xff\xfe hello\n[10:00:01] \xd0\xbe\xd0\xba\n")
    panel = _panel(qtbot)

    panel.show_journal("8.3.25 отладка", path)  # не должно поднять исключение

    assert "hello" in panel.text()
    assert "�" in panel.text()  # символ замены на месте битых байт


def test_tail_is_capped_at_500_lines(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    path = tmp_path / "p1.log"
    lines = [f"[10:00:00] строка {i}\n" for i in range(600)]
    path.write_text("".join(lines), encoding="utf-8")
    panel = _panel(qtbot)

    panel.show_journal("8.3.25 отладка", path)

    shown = panel.text().splitlines()
    assert len(shown) == 500
    assert "строка 599" in shown[-1]
    assert "строка 99" not in panel.text()


def test_missing_file_is_not_an_error(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """Профиль выбран, но ни разу не запускался — файла журнала ещё нет."""
    path = tmp_path / "never-started.log"
    panel = _panel(qtbot)

    panel.show_journal("Ещё не запускался", path)

    assert panel.text() == ""


def test_apply_palette_recolours_the_text(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    path = tmp_path / "p1.log"
    path.write_text("[10:00:00] запуск\n", encoding="utf-8")
    panel = _panel(qtbot, palette=theme.DARK)
    panel.show_journal("8.3.25 отладка", path)
    assert theme.DARK.background in panel.text_widget().styleSheet()

    panel.apply_palette(theme.LIGHT)

    assert theme.LIGHT.background in panel.text_widget().styleSheet()
