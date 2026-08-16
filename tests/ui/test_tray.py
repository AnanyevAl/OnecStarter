from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from onecstarter.config.v8i import parse_v8i
from onecstarter.services.catalog import items_from_document
from onecstarter.services.model import InfobaseItem, InfobaseSource
from onecstarter.services.settings import ThemeMode
from onecstarter.ui import app_icon, theme
from onecstarter.ui.tray import create_tray, make_icon, populate_tray_menu

FIXTURE = Path(__file__).parent.parent / "fixtures" / "anonymized.v8i"


def _favorites() -> list[InfobaseItem]:
    document = parse_v8i(FIXTURE.read_bytes())
    items = items_from_document(document, InfobaseSource.USER, {})
    base1 = next(item for item in items if item.name == "Демо Бухгалтерия")
    base2 = next(item for item in items if item.name == "Демо Розница")
    return [replace(base1, favorite=True), replace(base2, favorite=True)]


def test_menu_lists_show_favorites_and_quit(qtbot):
    launched: list[str] = []
    shown: list[int] = []
    quit_calls: list[int] = []
    menu = QMenu()
    populate_tray_menu(
        menu,
        _favorites(),
        lambda: shown.append(1),
        launched.append,
        lambda: quit_calls.append(1),
        theme_mode=lambda: ThemeMode.DARK,
        on_theme=lambda mode: None,
    )
    labels = [action.text() for action in menu.actions() if action.text()]
    assert labels[0] == "Показать"
    assert "Демо Бухгалтерия" in labels
    assert "Демо Розница" in labels
    assert labels[-1] == "Выход"


def test_menu_actions_trigger_callbacks(qtbot):
    launched: list[str] = []
    shown: list[int] = []
    quit_calls: list[int] = []
    menu = QMenu()
    populate_tray_menu(
        menu,
        _favorites(),
        lambda: shown.append(1),
        launched.append,
        lambda: quit_calls.append(1),
        theme_mode=lambda: ThemeMode.DARK,
        on_theme=lambda mode: None,
    )
    actions = {action.text(): action for action in menu.actions() if action.text()}
    actions["Показать"].trigger()
    actions["Демо Бухгалтерия"].trigger()
    actions["Демо Розница"].trigger()
    actions["Выход"].trigger()
    assert shown == [1]
    favorites = _favorites()
    assert launched == [favorites[0].key, favorites[1].key]
    assert quit_calls == [1]


def test_icon_is_not_null(qtbot):
    assert not make_icon().isNull()


def _icon_image(icon: Any, size: int) -> QImage:
    image = icon.pixmap(size, size).toImage()
    assert isinstance(image, QImage)
    return image


def test_tray_icon_matches_the_application_icon(qapp: Any) -> None:
    """Трей больше не рисует свой глиф — берёт фирменный значок приложения.

    Находка заказчика на контрольной точке 16.08.2026: заголовок окна,
    панель задач (`build/onecstarter.ico`) и трей показывали три РАЗНЫХ
    значка — трей рисовал собственный жёлтый треугольник запуска
    (`assert not make_icon().isNull()` было единственной проверкой и не
    ловило бы даже полную подмену рисунка). Теперь `make_icon()` — тонкая
    обёртка над `app_icon.application_icon()`, и на каждом фирменном размере
    кадра (`app_icon.ICON_SIZES`) иконка трея — тот же QImage, что
    и `app_icon.application_icon()` того же размера.

    Сравнение через `QImage.__eq__`, не через сырые байты `constBits()`:
    измерено — `QIcon.pixmap(...).toImage()` возвращает
    `Format_ARGB32_Premultiplied`, и в полностью прозрачных пикселях (alpha=0)
    RGB-биты «безразличны» и могут отличаться байт в байт у двух логически
    идентичных изображений, полученных разными путями рендера. `QImage ==`
    сравнивает содержимое корректно и с этим согласуется (проверено
    вручную: побайтовое сравнение на размере 24 ложно падало на первом же
    полностью прозрачном пикселе, `==` — нет).
    """  # noqa: RUF002
    tray_icon = make_icon()
    for size in app_icon.ICON_SIZES:
        tray_image = _icon_image(tray_icon, size)
        brand_image = _icon_image(app_icon.application_icon(), size)
        assert tray_image == brand_image, size


def test_tray_icon_stays_branded_across_theme_changes(qapp: Any) -> None:
    """Иконка трея не перекрашивается при смене темы — решение заказчика 16.08.2026.

    До задачи 13a этот же вывод («иконка трея от палитры не зависит») стоял
    на других основаниях: свой рисунок треугольника был жёстко привязан
    к `TRAY_GROUND`/`TRAY_MARK` — константам вне палитры, заведёнными
    отдельно ради этого свойства (спека 4b, §2.4: панель задач красится
    системной темой, а не нашей). Обе константы задачей 13a убраны как
    мёртвый код — обоснование стало проще и сильнее: иконка трея —
    тот же `application_icon()`, что и заголовок окна, а `draw_app_icon`
    вообще не принимает палитру аргументом, перекрашиваться неоткуда
    (см. `test_app_icon.py::test_draw_app_icon_does_not_depend_on_the_palette_argument`,
    тот же факт на уровне самого рисования, изолированно от трея).
    """  # noqa: RUF002
    original = qapp.styleSheet()
    try:
        baseline = _icon_image(make_icon(), 48)
        for palette in (theme.LIGHT, theme.DARK):
            qapp.setStyleSheet(theme.stylesheet(palette))
            assert _icon_image(make_icon(), 48) == baseline, palette
    finally:
        qapp.setStyleSheet(original)


def test_create_tray_returns_nothing_without_a_system_tray(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Нет трея в системе — нет объекта, и сборка приложения это переживает.

    `ui/app.py` пишет `window.close_to_tray = tray is not None`: без этой
    ветки закрытие окна прятало бы приложение туда, откуда его не достать.
    """  # noqa: RUF002
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    window = QWidget()
    qtbot.addWidget(window)

    tray = create_tray(
        window, list, lambda key: None, lambda: None,
        theme_mode=lambda: ThemeMode.DARK, on_theme=lambda mode: None,
    )

    assert tray is None


def _tray_with(qtbot: Any, monkeypatch: Any, favorites: list[InfobaseItem]) -> Any:
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    window = QWidget()
    qtbot.addWidget(window)
    launched: list[str] = []
    tray = create_tray(
        window,
        lambda: list(favorites),
        launched.append,
        lambda: None,
        theme_mode=lambda: ThemeMode.DARK,
        on_theme=lambda mode: None,
    )
    assert tray is not None
    tray.launched = launched  # type: ignore[attr-defined]
    return tray


def test_create_tray_populates_its_menu_at_once(qtbot: Any, monkeypatch: Any) -> None:
    """Первое наполнение — до первого `aboutToShow`, иначе меню пусто на старте."""
    tray = _tray_with(qtbot, monkeypatch, _favorites()[:1])

    labels = [action.text() for action in tray.contextMenu().actions() if action.text()]

    assert labels[0] == "Показать"
    assert "Демо Бухгалтерия" in labels


def test_create_tray_refreshes_its_menu_before_each_show(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Проводка проверяется там, где живёт, — на меню, собранном `create_tray`.

    Финальное ревью, I3: `test_menu_refreshes_favorites_on_each_show` ниже
    повторяет проводку руками (свой `QMenu`, свой `aboutToShow.connect`)
    и проверяет собственную копию — удаление строки `menu.aboutToShow.connect
    (rebuild_menu)` из `create_tray` оставляло весь набор зелёным, а список
    избранного в живом трее замерзал бы на состоянии первого показа.
    Тот тест остаётся: он документирует, почему меню одно на весь срок
    жизни трея, а не создаётся заново на каждый показ.
    """  # noqa: RUF002
    favorites = _favorites()[:1]
    tray = _tray_with(qtbot, monkeypatch, favorites)
    menu = tray.contextMenu()
    assert "Демо Розница" not in [a.text() for a in menu.actions()]

    favorites.append(_favorites()[1])
    menu.aboutToShow.emit()

    labels = [action.text() for action in menu.actions() if action.text()]
    assert "Демо Бухгалтерия" in labels
    assert "Демо Розница" in labels


def test_tray_menu_actions_launch_through_the_provided_callback(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Пункт избранного, собранный `create_tray`, зовёт настоящий `on_launch`."""
    favorites = _favorites()[:1]
    tray = _tray_with(qtbot, monkeypatch, favorites)
    action = next(
        a for a in tray.contextMenu().actions() if a.text() == "Демо Бухгалтерия"
    )

    action.trigger()

    assert tray.launched == [favorites[0].key]


def test_menu_refreshes_favorites_on_each_show(qtbot):
    # Important-замечание финального ревью: трей держит ОДНО постоянное
    # QMenu и наполняет его заново в собственном aboutToShow (см.  # noqa: RUF003
    # create_tray.rebuild_menu). Старая реализация строила новое QMenu на
    # каждое открытие и подменяла его через setContextMenu — Qt в момент  # noqa: RUF003
    # показа уже использовал предыдущее меню, так что список избранного
    # отставал на один показ. Здесь тот же паттерн: aboutToShow подключён
    # один раз к одному menu, а провайдер favorites между эмиссиями меняется.  # noqa: RUF003
    favorites = _favorites()[:1]
    menu = QMenu()
    menu.aboutToShow.connect(
        lambda: populate_tray_menu(
            menu,
            favorites,
            lambda: None,
            lambda key: None,
            lambda: None,
            theme_mode=lambda: ThemeMode.DARK,
            on_theme=lambda mode: None,
        )
    )

    menu.aboutToShow.emit()
    labels_before = [action.text() for action in menu.actions() if action.text()]
    assert "Демо Бухгалтерия" in labels_before
    assert "Демо Розница" not in labels_before

    favorites.append(_favorites()[1])
    menu.aboutToShow.emit()
    labels_after = [action.text() for action in menu.actions() if action.text()]
    assert "Демо Бухгалтерия" in labels_after
    assert "Демо Розница" in labels_after


def test_menu_has_theme_submenu_with_current_checked() -> None:
    menu = QMenu()
    populate_tray_menu(
        menu, [], lambda: None, lambda key: None, lambda: None,
        theme_mode=lambda: ThemeMode.LIGHT, on_theme=lambda mode: None,
    )
    # Обычный цикл, не генератор/списковое включение: на этой связке
    # PySide6 6.11.1 + Python 3.14.6 вызов action.menu() внутри выражения
    # такого рода роняет процесс с "libshiboken: Internal C++ object  # noqa: RUF003
    # (QMenu) already deleted", тот же вызов в цикле — нет (проверено
    # минимальным повтором вне populate_tray_menu).
    found = None
    for action in menu.actions():
        if action.text() == "Тема":
            found = action.menu()
            break
    assert found is not None
    # action.menu() типизирован в стабах PySide6 как QObject (неточность
    # стабов) — фактически это всегда QMenu для пункта, созданного addMenu().
    submenu = cast(QMenu, found)
    checked = [action.text() for action in submenu.actions() if action.isChecked()]
    assert checked == ["Светлая"]
