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


# -- ревью задачи 5: CRITICAL — refresh() не должен дёргать прокрутку -------
#
# `QPlainTextEdit.setPlainText()` безусловно пересобирает документ и
# сбрасывает scrollbar в 0 — даже если новый текст совпадает со старым  # noqa: RUF003
# (подтверждено ревьюером прогоном против PySide6 этого проекта). Раньше
# `refresh()` звал `setPlainText()` на КАЖДЫЙ тик безусловно, и «текст не
# менялся → scrollbar не поедет» было неверным допущением.


def test_refresh_does_not_move_the_scrollbar_when_the_file_is_unchanged(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ (ревью задачи 5, CRITICAL): пользователь прокрутил

    вверх, файл не менялся — `refresh()` не имеет права тронуть scrollbar
    вообще. Мутация «убрать раннюю проверку `tail == toPlainText()`»
    обязана уронить `assert bar.value() == scrolled_value` (станет 0).
    """  # noqa: RUF002
    path = tmp_path / "p1.log"
    path.write_text(
        "\n".join(f"[10:00:{i:02d}] строка {i}" for i in range(200)) + "\n",
        encoding="utf-8",
    )
    panel = _panel(qtbot)
    panel.resize(300, 120)
    panel.show()
    panel.show_journal("8.3.25 отладка", path)
    bar = panel.text_widget().verticalScrollBar()
    assert bar.maximum() > 0, "тест бессмыслен без реальной прокрутки"
    bar.setValue(bar.maximum() // 2)
    scrolled_value = bar.value()
    assert scrolled_value > 0

    panel.refresh()  # файл не менялся

    assert bar.value() == scrolled_value


def test_refresh_restores_the_scroll_position_when_the_file_was_appended(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ (ревью задачи 5, CRITICAL): пользователь прокрутил

    вверх, файл ДОПИСАН — `refresh()` обязан вернуть прежнюю позицию
    прокрутки, а не уронить её к 0 и не утащить к низу. Мутация «вернуть
    `_scroll_to_bottom()`/убрать `bar.setValue(previous_value)` в ветке
    `not was_at_bottom`» обязана уронить финальный `assert`.
    """  # noqa: RUF002
    path = tmp_path / "p1.log"
    path.write_text(
        "\n".join(f"[10:00:{i:02d}] строка {i}" for i in range(200)) + "\n",
        encoding="utf-8",
    )
    panel = _panel(qtbot)
    panel.resize(300, 120)
    panel.show()
    panel.show_journal("8.3.25 отладка", path)
    bar = panel.text_widget().verticalScrollBar()
    assert bar.maximum() > 0, "тест бессмыслен без реальной прокрутки"
    bar.setValue(bar.maximum() // 2)
    scrolled_value = bar.value()
    assert scrolled_value > 0

    with path.open("a", encoding="utf-8") as handle:
        handle.write("[10:05:00] новая строка после ручной прокрутки\n")
    panel.refresh()

    assert bar.value() == scrolled_value


def test_refresh_still_autoscrolls_when_the_user_was_at_the_bottom(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """Обратная сторона защитных тестов выше: у низа — автопрокрутка работает как раньше.

    Допуск в 2 единицы у обоих `assert` — тот же `_SCROLL_TOLERANCE`, что
    и у самой панели (`_is_at_bottom`): `QPlainTextEdit.verticalScrollBar()
    .maximum()`, прочитанный сразу синхронно после `setPlainText()`, может
    на 1 отставать от значения, которое тот же геттер вернёт чуть позже —
    Qt пересчитывает раскладку документа не мгновенно. Строгое `==`
    ловило бы этот шум расчёта раскладки, а не поведение панели.
    """  # noqa: RUF002
    path = tmp_path / "p1.log"
    path.write_text(
        "\n".join(f"[10:00:{i:02d}] строка {i}" for i in range(200)) + "\n",
        encoding="utf-8",
    )
    panel = _panel(qtbot)
    panel.resize(300, 120)
    panel.show()
    panel.show_journal("8.3.25 отладка", path)
    bar = panel.text_widget().verticalScrollBar()
    assert bar.maximum() - bar.value() <= 2  # show_journal сам поставил в конец

    with path.open("a", encoding="utf-8") as handle:
        handle.write("[10:05:00] ещё строка\n")
    panel.refresh()

    assert bar.maximum() - bar.value() <= 2
    assert "ещё строка" in panel.text()


# -- ревью задачи 5: IMPORTANT — refresh() не читает файл целиком -----------


def test_refresh_limits_reading_to_a_fixed_byte_buffer_not_the_whole_file(
    application: QApplication, tmp_path: Path, qtbot: Any
) -> None:
    """ЗАЩИТНЫЙ ТЕСТ (ревью задачи 5, IMPORTANT): чтение ограничено байтовым

    буфером с конца файла, а не всем файлом целиком. Всего 10 строк
    (заведомо меньше лимита в 500) — если бы `refresh()` читал файл
    целиком и резал только по числу строк, первая строка осталась бы
    в хвосте. Каждая строка — около 40 КиБ, все десять вместе заведомо
    больше буфера чтения (256 КиБ), поэтому байтовое ограничение обязано
    отрезать начало файла даже при заведомо малом числе строк.
    Мутация «вернуть `path.read_bytes()` без ограничения буфера» пройдёт
    существующие тесты хвоста (там файлы маленькие), но обязана уронить
    именно этот: первая строка снова окажется в тексте.
    """  # noqa: RUF002
    path = tmp_path / "long-lines.log"
    long_chunk = "x" * (40 * 1024)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"ПЕРВАЯ_СТРОКА {long_chunk}\n")  # noqa: RUF001
        for i in range(1, 9):
            handle.write(f"строка {i} {long_chunk}\n")
        handle.write(f"ПОСЛЕДНЯЯ_СТРОКА {long_chunk}\n")  # noqa: RUF001
    assert path.stat().st_size > 256 * 1024

    panel = _panel(qtbot)
    panel.show_journal("8.3.25 отладка", path)

    assert "ПОСЛЕДНЯЯ_СТРОКА" in panel.text()  # noqa: RUF001
    assert "ПЕРВАЯ_СТРОКА" not in panel.text()  # noqa: RUF001
