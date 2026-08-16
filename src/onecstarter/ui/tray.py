"""Трей: поднять окно, запустить избранную базу, выйти.

Иконка трея — фирменный значок приложения (`onecstarter.ui.app_icon`),
общий с заголовком окна и панелью задач. До задачи 13a трей рисовал
собственный жёлтый треугольник запуска — заказчик на контрольной точке
16.08.2026 показал скриншот с тремя РАЗНЫМИ значками одновременно и
потребовал единообразия. Символика 1С не используется (requirements.md,
§4: без бренда).
"""  # noqa: RUF002

from collections.abc import Callable, Sequence

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from onecstarter.services.model import InfobaseItem
from onecstarter.services.settings import ThemeMode
from onecstarter.ui.app_icon import application_icon
from onecstarter.ui.settings_view import CHOICES


def make_icon() -> QIcon:
    """Иконка трея — фирменный значок приложения, тот же, что у заголовка окна.

    От палитры приложения не зависит — но не по спеке 4b, §2.4 («панель
    задач красится системной темой», старое обоснование, отменённое
    решением заказчика 16.08.2026), а потому что `application_icon()`
    вообще не параметризована палитрой (см. докстринг `draw_app_icon`):
    значок — идентичность приложения, одинаковая во всех трёх местах
    и в любой теме.
    """  # noqa: RUF002
    return application_icon()


def populate_tray_menu(
    menu: QMenu,
    favorites: Sequence[InfobaseItem],
    on_show: Callable[[], None],
    on_launch: Callable[[str], None],
    on_quit: Callable[[], None],
    *,
    theme_mode: Callable[[], ThemeMode],
    on_theme: Callable[[ThemeMode], None],
) -> None:
    """Очистить и заново наполнить меню трея: Показать / избранное / Тема / Выход.

    Принимает уже существующее меню, а не создаёт новое — трей держит одно
    QMenu на весь срок жизни (см. create_tray) и наполняет его перед каждым
    показом через aboutToShow. Раньше здесь строилось новое QMenu на каждое
    открытие и подменялось через setContextMenu — Qt в момент показа уже
    использовал предыдущее меню (aboutToShow нового срабатывает не раньше
    следующего открытия), так что список избранного отставал на один показ,
    а замещённые QMenu не освобождались (утечка по одному на открытие).

    `CHOICES` берётся из `settings_view` — один список подписей на обе точки
    входа (раздел «Настройки» и это подменю), иначе они разойдутся текстом.
    """  # noqa: RUF002
    menu.clear()
    menu.addAction("Показать", on_show)
    if favorites:
        menu.addSeparator()
        for item in favorites:
            key = item.key
            menu.addAction(item.name, lambda checked=False, key=key: on_launch(key))
    menu.addSeparator()
    submenu = menu.addMenu("Тема")
    current = theme_mode()
    for mode, label in CHOICES:
        action = submenu.addAction(label, lambda checked=False, m=mode: on_theme(m))
        action.setCheckable(True)
        action.setChecked(mode is current)
    menu.addAction("Выход", on_quit)


def create_tray(
    window: QWidget,
    favorites_provider: Callable[[], list[InfobaseItem]],
    on_launch: Callable[[str], None],
    on_quit: Callable[[], None],
    *,
    theme_mode: Callable[[], ThemeMode],
    on_theme: Callable[[ThemeMode], None],
) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(make_icon(), window)
    tray.setToolTip("OneCStarter")

    def show_window() -> None:
        show = getattr(window, "show_and_focus_search", window.show)
        show()

    menu = QMenu()

    def rebuild_menu() -> None:
        # Список избранного живой — наполняем перед каждым показом. menu —
        # один и тот же объект на весь срок жизни трея: setContextMenu
        # вызывается один раз ниже, а не на каждую перестройку.  # noqa: RUF003
        populate_tray_menu(
            menu,
            favorites_provider(),
            show_window,
            on_launch,
            on_quit,
            theme_mode=theme_mode,
            on_theme=on_theme,
        )

    menu.aboutToShow.connect(rebuild_menu)
    rebuild_menu()
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: show_window()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()
    return tray
