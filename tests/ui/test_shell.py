from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QWidget

from onecstarter.ui import theme
from onecstarter.ui.shell import MainWindow


class _StubSection(QWidget):
    """Раздел-заглушка с настоящим focus_search — в отличие от QLabel

    у остальных тестов файла, где focus_search просто отсутствует и шов
    getattr(...)/callable(...) в show_and_focus_search молча не срабатывает.
    """  # noqa: RUF002

    def __init__(self) -> None:
        super().__init__()
        self.focus_calls = 0

    def focus_search(self) -> None:
        self.focus_calls += 1


def test_window_builds_with_section_and_title(qtbot):
    window = MainWindow([("Базы", QLabel("заглушка"))])
    qtbot.addWidget(window)
    assert window.windowTitle() == "OneCStarter"
    assert window.centralWidget() is not None


def test_rail_buttons_fill_the_rail_regardless_of_label_width(qtbot):
    """Кнопка раздела — полноширинный пункт рельсы, а не кнопка по содержимому.

    QToolButton по умолчанию Fixed по горизонтали: с настоящим шрифтом
    подпись «Базы» давала кнопку ~40 px, прижатую к левому краю рельсы
    ([Ф] живой запуск 15.08.2026), а мокап рисует пункт на всю ширину.
    Оффскрин-платформа дефект маскирует: шрифтов у неё нет, tofu-глифы
    раздували подпись почти до ширины рельсы — поэтому тест не меряет
    одну кнопку против 76 px, а сравнивает две кнопки с заведомо разной
    шириной подписи: при Fixed их ширины разошлись бы и здесь.
    """  # noqa: RUF002
    window = MainWindow(
        [("Б", QLabel("заглушка")), ("Настройки", QLabel("заглушка"))]
    )
    qtbot.addWidget(window)
    window.show()
    short, long = window.section_buttons()
    assert short.width() == long.width()
    assert short.width() >= 70


def test_stylesheet_is_dark_with_accent():
    assert theme.DARK.background.startswith("#")
    assert theme.DARK.accent.startswith("#")
    assert "QTreeView" in theme.stylesheet(theme.DARK)


def test_close_to_tray_hides_instead_of_closing(qtbot):
    window = MainWindow([("Базы", QLabel("заглушка"))])
    qtbot.addWidget(window)
    window.close_to_tray = True
    window.show()
    window.close()
    assert window.isHidden()
    # Окно живо: показ после «закрытия» возможен.
    window.show()
    assert not window.isHidden()


def test_close_with_running_servers_and_declined_confirmation_keeps_window(qtbot):
    """ЗАЩИТНЫЙ ТЕСТ: отказ в подтверждении не закрывает окно и не гасит серверы, §12.3.

    Серверы — дочерние процессы лаунчера (T-10, задача 4: Job Object, задача 7):
    настоящий выход гасит их вместе с окном, поэтому `confirm_quit` (проводка
    `ui/app.py`, задача 6) обязан спросить пользователя, если что-то работает,
    и отказ ("Нет") обязан оставить окно открытым — `event.ignore()`, а не
    обычное закрытие.
    """  # noqa: RUF002
    window = MainWindow([("Базы", QLabel("заглушка"))])
    qtbot.addWidget(window)
    window.confirm_quit = lambda: False
    window.show()

    window.close()

    assert window.isVisible(), "отказ в подтверждении обязан оставить окно открытым"


def test_close_to_tray_hides_without_asking(qtbot):
    """close_to_tray — сворачивание, не выход (§12.2): гейт confirm_quit не звать.

    Ветка `close_to_tray` в `closeEvent` обязана вернуться раньше проверки
    `confirm_quit` — простое скрытие окна серверы не трогает, спрашивать
    пользователя не о чем.
    """  # noqa: RUF002
    calls: list[None] = []

    def confirm_quit() -> bool:
        calls.append(None)
        return True

    window = MainWindow([("Базы", QLabel("заглушка"))])
    qtbot.addWidget(window)
    window.close_to_tray = True
    window.confirm_quit = confirm_quit
    window.show()

    window.close()

    assert window.isHidden()
    assert calls == [], "close_to_tray обязан вернуться раньше confirm_quit"


def test_show_and_focus_search_calls_section_focus_search(qtbot):
    # Шов show_and_focus_search -> section.focus_search() не был покрыт:
    # остальные тесты файла используют QLabel, у которого focus_search нет,  # noqa: RUF003
    # поэтому getattr(...)/callable(...) в реализации молча ничего не зовёт.
    section = _StubSection()
    window = MainWindow([("Базы", section)])
    qtbot.addWidget(window)
    window.show_and_focus_search()
    assert section.focus_calls == 1


def test_show_and_focus_search_keeps_maximized_window(qtbot):
    # showNormal() безусловно сбрасывал развёрнутое окно — хоткей/трей на
    # развёрнутом окне откатывали бы его в обычный размер незаметно  # noqa: RUF003
    # для пользователя.
    window = MainWindow([("Базы", QLabel("заглушка"))])
    qtbot.addWidget(window)
    window.showMaximized()
    assert window.isMaximized()
    window.show_and_focus_search()
    assert window.isMaximized()


def test_window_switches_sections(qtbot):
    """Панель навигации переключает разделы; активна ровно одна кнопка."""
    # Без аннотации возврата: qtbot нетипизирован, а частичная аннотация  # noqa: RUF003
    # (только -> None) ловится mypy strict как неполная — disallow_untyped_defs
    # в tests.ui.* выключен, но disallow_incomplete_defs остаётся.
    first, second = QLabel("Базы"), QLabel("Настройки")
    window = MainWindow([("Базы", first), ("Настройки", second)])
    qtbot.addWidget(window)

    assert window.current_section() is first
    window.show_section(1)
    assert window.current_section() is second
    assert [button.isChecked() for button in window.section_buttons()] == [False, True]


def test_sections_sit_together_at_the_top(qtbot):
    """Спека рестайла §3: «Настройки» сразу под «Базами», распорка — после всех.

    Отменяет §2.5 спеки 4b (раздел-обслуживание внизу): мокап утверждён
    позже и показывает разделы подряд.
    """
    from PySide6.QtWidgets import QFrame

    window = MainWindow([("Базы", QLabel("а")), ("Настройки", QLabel("б"))])  # noqa: RUF001
    qtbot.addWidget(window)
    rail = window.findChild(QFrame, "NavRail")
    assert rail is not None
    layout = rail.layout()
    assert layout is not None
    kinds = [
        "spacer" if layout.itemAt(i).spacerItem() is not None else "widget"  # type: ignore[union-attr]
        for i in range(layout.count())
    ]
    assert kinds == ["widget", "widget", "spacer"]


def test_ctrl_f_focuses_search_of_current_section(qtbot):
    """Одна комбинация Ctrl+F на окно — QShortcut оболочки, не раздела (спека v3.1, §6).

    Два QShortcut с одним и тем же Ctrl+F в разных разделах Qt счёл бы
    неоднозначными и не сработал бы ни один — отсюда шов в оболочке,
    тот же getattr(...)/callable(...), что уже был в show_and_focus_search.

    Контекст `WindowShortcut` (умолчание QShortcut) требует именно АКТИВНОГО
    окна, а не просто видимого/экспонированного — на offscreen-платформе
    show()+waitExposed() этого не гарантирует (замер: isActiveWindow() ==
    False сразу после них), поэтому окно явно активируется и тест ждёт
    события активации, прежде чем слать хоткей.
    """  # noqa: RUF002
    section = _StubSection()
    window = MainWindow([("Базы", section), ("Серверы", QLabel("без поиска"))])
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    with qtbot.waitActive(window, timeout=2000):
        window.activateWindow()
    qtbot.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert section.focus_calls == 1
    window.show_section(1)
    qtbot.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert section.focus_calls == 1  # у «Серверов» поиска нет — ничего не произошло  # noqa: RUF003


def _window_with_sections(qtbot: Any, labels: list[str]) -> tuple[MainWindow, list[QWidget]]:
    widgets: list[QWidget] = [QLabel(label) for label in labels]
    window = MainWindow(sections=list(zip(labels, widgets, strict=True)))
    qtbot.addWidget(window)
    return window, widgets


def test_alt_number_switches_section(qtbot: Any) -> None:
    """Alt+3 переключает на третий раздел рельсы — задача 8, спека §2.2.

    У MainWindow нет геттера индекса — есть current_section() -> QWidget
    (shell.py:116), поэтому сверяем сам виджет и отметку на кнопке:
    show_section() сам проставляет checked нужной кнопке.

    Контекст `WindowShortcut` (умолчание QShortcut) требует именно АКТИВНОГО
    окна — тот же замер offscreen-платформы, что и у test_ctrl_f_focuses_
    search_of_current_section: без show()+waitActive() клавиша до QShortcut
    не доходит и раздел не переключается вовсе.
    """  # noqa: RUF002
    sections = ["Базы", "Серверы", "EDT", "Настройки"]
    window, widgets = _window_with_sections(qtbot, sections)
    window.show()
    qtbot.waitExposed(window)
    with qtbot.waitActive(window, timeout=2000):
        window.activateWindow()
    QTest.keyClick(window, Qt.Key.Key_3, Qt.KeyboardModifier.AltModifier)
    assert window.current_section() is widgets[2]
    assert window.section_buttons()[2].isChecked()


def test_only_nine_sections_get_shortcuts(qtbot: Any) -> None:
    """Alt+0 не занимаем, а после девятого раздела сочетаний уже не хватает."""  # noqa: RUF002
    window, _widgets = _window_with_sections(qtbot, [f"Раздел {n}" for n in range(1, 12)])
    sequences = {s.key().toString() for s in window.findChildren(QShortcut)}
    assert "Alt+9" in sequences
    assert "Alt+0" not in sequences
    assert not any(f"Alt+{n}" in sequences for n in (10, 11))


def test_button_tooltip_carries_the_shortcut(qtbot: Any) -> None:
    """Подсказка кнопки называет своё сочетание — не только справочник в Настройках."""
    window, _widgets = _window_with_sections(qtbot, ["Базы", "Серверы"])
    assert "Alt+1" in window.section_buttons()[0].toolTip()


def test_section_icon_follows_the_palette(qtbot):
    """Значок раздела перерисовывается при apply_palette — цвет не запекается."""
    from onecstarter.ui import rail_icons

    window = MainWindow([("Базы", QLabel("а"))], palette=theme.DARK)  # noqa: RUF001
    qtbot.addWidget(window)
    window.set_section_icon(0, rail_icons.bases_icon)
    button = window.section_buttons()[0]
    dark = button.icon().pixmap(16, 16).toImage().constBits().tobytes()  # type: ignore[union-attr]
    window.apply_palette(theme.LIGHT)
    light = button.icon().pixmap(16, 16).toImage().constBits().tobytes()  # type: ignore[union-attr]
    assert dark != light
