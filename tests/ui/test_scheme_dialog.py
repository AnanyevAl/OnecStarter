"""Диалог цветовой схемы (спека v3.2, §5, §7)."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QListWidget, QPushButton, QTableWidgetItem

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    CURRENT_NAME,
    DEFAULT_NAME,
    EDT_DEFAULTS,
    RGB,
    THEME_IDS,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    parse_csi,
    parse_prefs,
    to_hex,
)
from onecstarter.services.edt_scheme import BUSY_MESSAGE, SchemeCatalog, WorkspaceSchemes
from onecstarter.ui.edt.scheme_dialog import (
    APPLIED_MESSAGE,
    HINT_MISSING_DIR,
    HINT_NO_DIR,
    THEME_TITLES,
    SchemeDialog,
)
from onecstarter.ui.theme import DARK

FIXTURES = Path(__file__).parent.parent / "fixtures" / "edt_schemes"
BACKGROUND_ROW = 11  # индекс `Background` в COLOR_KEYS: 11 токенов, затем редактор
TOKEN = "com._1c.g5.v8.dt.bsl.Bsl.syntaxColorer.tokenStyles."


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.busy = False
        self.workspace_dir = tmp_path / "ws"
        self.catalog_dir = tmp_path / "schemes"
        self.catalog_dir.mkdir()
        shutil.copy(FIXTURES / "dark22.csi", self.catalog_dir / "Тёмная.csi")
        shutil.copy(FIXTURES / "idea-six.xml", self.catalog_dir / "Шесть.xml")
        (self.catalog_dir / "bad.icls").write_text("<x/>", encoding="utf-8")

    def workspace(self) -> WorkspaceSchemes:
        return WorkspaceSchemes(str(self.workspace_dir), is_busy=lambda: self.busy)

    def dialog(
        self,
        catalog: SchemeCatalog | str | None = "auto",
        choose_save: Callable[[str], str] = lambda initial: "",
        choose_color: Callable[[RGB], RGB | None] = lambda rgb: None,
        default_dir: str | None = None,
    ) -> SchemeDialog:
        if catalog == "auto":
            catalog = SchemeCatalog(str(self.catalog_dir))
        return SchemeDialog(
            "Запись А",  # noqa: RUF001
            self.workspace(),
            catalog,  # type: ignore[arg-type]
            palette=DARK,
            is_busy=lambda: self.busy,
            show_info=self.infos.append,
            show_error=self.errors.append,
            choose_save=choose_save,
            choose_color=choose_color,
            default_dir=default_dir if default_dir is not None else str(Path.home()),
        )


@pytest.fixture
def harness(tmp_path: Path, qtbot) -> Harness:  # type: ignore[no-untyped-def]
    return Harness(tmp_path)


def _rows(sources: QListWidget) -> list[str]:
    return [sources.item(i).text() for i in range(sources.count())]


def _select(dialog: SchemeDialog, text: str) -> None:
    rows = _rows(dialog.sources())
    dialog.sources().setCurrentRow(rows.index(text))


def _cell(dialog: SchemeDialog, row: int, column: int) -> QTableWidgetItem:
    """Ячейка таблицы; сужение `QTableWidgetItem | None` — таблица заполнена диалогом."""
    item = dialog.table().item(row, column)
    assert item is not None
    return item


def test_sources_and_current_without_prefs_shows_defaults(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Цветовая схема — Запись А"  # noqa: RUF001
    assert _rows(dialog.sources()) == [CURRENT_NAME, DEFAULT_NAME, "bad", "Тёмная", "Шесть"]
    assert dialog.sources().currentRow() == 0
    assert dialog.table().rowCount() == 22
    assert _cell(dialog, 0, 2).text() == to_hex(EDT_DEFAULTS["BSL_Keywords"])
    assert dialog.hint_label().isHidden()
    assert dialog.scheme().name == CURRENT_NAME


def test_current_reads_workspace_prefs(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dark = parse_csi((FIXTURES / "dark22.csi").read_text(encoding="utf-8"))
    harness.workspace().apply(Scheme("d", dark), ThemeChoice.KEEP)
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert _cell(dialog, BACKGROUND_ROW, 2).text() == "#2B2B2B"


def test_select_catalog_scheme_fills_table_preview_and_icon(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    assert _cell(dialog, BACKGROUND_ROW, 2).text() == "#2B2B2B"
    assert ("Процедура", "#cc7832", "") in dialog.preview().fragments()
    assert dialog.scheme().name == "Тёмная"
    assert dialog.sources().currentItem().icon().isNull() is False
    _select(dialog, "Шесть")
    assert dialog.scheme().name == "Шесть атрибутов"  # имя из XML
    assert _cell(dialog, 0, 2).text() == "#CC7832"


def test_every_source_row_has_icon_slot_so_text_does_not_shift(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    sources = dialog.sources()
    size = QSize(12, 12)
    for index in range(sources.count()):
        assert sources.item(index).icon().isNull() is False
    # незагруженная строка — прозрачная заглушка, загруженная — кружок цвета фона схемы
    blank = sources.item(_rows(sources).index("Тёмная")).icon().pixmap(size).toImage()
    assert blank.pixelColor(6, 6).alpha() == 0
    _select(dialog, "Тёмная")
    loaded = sources.item(_rows(sources).index("Тёмная")).icon().pixmap(size).toImage()
    assert loaded.pixelColor(6, 6) == QColor(43, 43, 43)


def test_unreadable_entry_marked_and_table_unchanged(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    _select(dialog, "bad")
    item = dialog.sources().currentItem()
    assert item.toolTip().startswith("не удалось прочитать")
    assert item.icon().isNull() is False
    assert _cell(dialog, BACKGROUND_ROW, 2).text() == "#2B2B2B"
    assert dialog.scheme().name == "Тёмная"
    assert harness.errors == []


def test_no_catalog_shows_hint_and_fixed_rows(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog(catalog=None)
    qtbot.addWidget(dialog)
    assert _rows(dialog.sources()) == [CURRENT_NAME, DEFAULT_NAME]
    assert dialog.hint_label().isHidden() is False
    assert dialog.hint_label().text() == HINT_NO_DIR


def test_missing_catalog_dir_shows_path(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    missing = harness.tmp_path / "nope"
    dialog = harness.dialog(catalog=SchemeCatalog(str(missing)))
    qtbot.addWidget(dialog)
    assert _rows(dialog.sources()) == [CURRENT_NAME, DEFAULT_NAME]
    assert dialog.hint_label().text() == HINT_MISSING_DIR.format(path=missing)


def test_edit_hex_updates_scheme_swatch_and_preview_invalid_reverts(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, DEFAULT_NAME)
    _cell(dialog, 0, 2).setText("#FF0000")
    assert dialog.scheme().colors["BSL_Keywords"] == (255, 0, 0)
    assert _cell(dialog, 0, 1).background().color().name() == "#ff0000"
    assert ("Процедура", "#ff0000", "") in dialog.preview().fragments()
    _cell(dialog, 0, 2).setText("zzz")
    assert _cell(dialog, 0, 2).text() == "#FF0000"
    assert dialog.scheme().colors["BSL_Keywords"] == (255, 0, 0)


def test_swatch_click_picks_color(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    asked: list[RGB] = []

    def choose(current: RGB) -> RGB | None:
        asked.append(current)
        return (1, 2, 3)

    dialog = harness.dialog(choose_color=choose)
    qtbot.addWidget(dialog)
    dialog.table().cellClicked.emit(0, 1)
    assert asked == [EDT_DEFAULTS["BSL_Keywords"]]
    assert dialog.scheme().colors["BSL_Keywords"] == (1, 2, 3)
    assert _cell(dialog, 0, 2).text() == "#010203"
    dialog.table().cellClicked.emit(0, 0)  # не образец — диалог цвета не зовётся
    assert len(asked) == 1


def test_invert_flips_colors_keeps_name(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    dialog.invert_button().click()
    assert dialog.scheme().colors["Background"] == (212, 212, 212)
    assert dialog.scheme().name == "Тёмная"
    assert _cell(dialog, BACKGROUND_ROW, 2).text() == "#D4D4D4"


def test_save_writes_csi_and_selects_new_row(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    initials: list[str] = []
    target = harness.catalog_dir / "Новая.csi"

    def choose(initial: str) -> str:
        initials.append(initial)
        return str(target)

    dialog = harness.dialog(choose_save=choose)
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    dialog.set_color("Strings", (9, 9, 9))
    dialog.save_button().click()
    assert initials == [str(harness.catalog_dir / "Тёмная.csi")]
    saved = parse_csi(target.read_text(encoding="utf-8"))
    assert saved["Strings"] == (9, 9, 9)
    assert saved["Background"] == (43, 43, 43)
    assert "Новая" in _rows(dialog.sources())
    assert dialog.sources().currentItem().text() == "Новая"
    assert dialog.scheme().name == "Новая"
    assert dialog.scheme().colors["Strings"] == (9, 9, 9)


def test_save_cancelled_does_nothing(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog(choose_save=lambda initial: "")
    qtbot.addWidget(dialog)
    dialog.save_button().click()
    assert sorted(p.name for p in harness.catalog_dir.iterdir()) == [
        "bad.icls",
        "Тёмная.csi",
        "Шесть.xml",
    ]


def test_apply_writes_prefs_and_reports(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    assert dialog.apply_button().isEnabled()
    dialog.apply_button().click()
    settings = harness.workspace().settings_dir
    bsl = parse_prefs((settings / BSL_PREFS).read_bytes().decode("latin-1"))
    assert bsl[f"{TOKEN}Builtin function.color"] == "255,198,109"
    assert harness.infos == [APPLIED_MESSAGE]
    assert harness.errors == []


def test_apply_disabled_when_busy_and_refused_on_race(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    harness.busy = True
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.apply_button().isEnabled() is False
    assert dialog.apply_button().toolTip() == BUSY_MESSAGE
    harness.busy = False
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    assert dialog.apply_button().isEnabled()
    harness.busy = True  # гонка: EDT запустился после открытия диалога
    dialog.apply_button().click()
    assert harness.errors == [BUSY_MESSAGE]
    assert harness.infos == []
    assert not harness.workspace().settings_dir.exists()


def test_apply_default_unchanged_resets_not_writes(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, DEFAULT_NAME)
    dialog.apply_button().click()
    assert harness.infos == [APPLIED_MESSAGE]
    assert not harness.workspace().settings_dir.exists()  # снимать нечего — файлов не было
    dialog.set_color("Strings", (1, 1, 1))
    dialog.apply_button().click()
    assert (harness.workspace().settings_dir / BSL_PREFS).exists()


def test_apply_service_error_is_shown(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    settings = harness.workspace().settings_dir
    settings.parent.mkdir(parents=True)
    settings.write_text("файл вместо каталога", encoding="utf-8")
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    _select(dialog, "Тёмная")
    dialog.apply_button().click()
    assert harness.errors and harness.errors[0].startswith("Не удалось")  # noqa: RUF001
    assert harness.infos == []


def test_theme_combo_follows_theme_ids(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    combo = dialog.theme_combo()
    expected = [THEME_TITLES[ThemeChoice.KEEP]] + [
        THEME_TITLES[choice]
        for choice in (ThemeChoice.DARK, ThemeChoice.LIGHT)
        if choice in THEME_IDS
    ]
    assert [combo.itemText(i) for i in range(combo.count())] == expected
    assert combo.isHidden() == (len(expected) == 1)
    if ThemeChoice.DARK in THEME_IDS:
        _select(dialog, "Тёмная")
        combo.setCurrentIndex(expected.index(THEME_TITLES[ThemeChoice.DARK]))
        dialog.apply_button().click()
        theme = parse_prefs(
            (harness.workspace().settings_dir / THEME_PREFS).read_bytes().decode("latin-1")
        )
        assert theme["themeid"] == THEME_IDS[ThemeChoice.DARK]


def test_filter_hides_rows_case_insensitively(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    dialog.search().setText("ШЕСТЬ")
    sources = dialog.sources()
    visible = [
        sources.item(i).text() for i in range(sources.count()) if not sources.item(i).isHidden()
    ]
    assert visible == ["Шесть"]
    dialog.search().setText("")
    assert all(not sources.item(i).isHidden() for i in range(sources.count()))


# --- ревью финального прогона v3.2 (задачи 1-3) ---


def test_save_outside_catalog_keeps_edited_scheme_and_apply_writes_it(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    """Сохранение вне каталога не должно сбрасывать таблицу на «Текущую» (ревью, задача 1)."""
    target = harness.tmp_path / "out" / "Моя.csi"

    def choose(initial: str) -> str:
        assert initial.startswith(str(harness.tmp_path))
        return str(target)

    dialog = harness.dialog(catalog=None, choose_save=choose, default_dir=str(harness.tmp_path))
    qtbot.addWidget(dialog)
    _select(dialog, DEFAULT_NAME)
    dialog.set_color("Strings", (9, 9, 9))
    dialog.save_button().click()
    saved = parse_csi(target.read_text(encoding="utf-8"))
    assert saved["Strings"] == (9, 9, 9)
    assert dialog.scheme().colors["Strings"] == (9, 9, 9)
    assert dialog.sources().currentRow() == -1
    dialog.apply_button().click()
    settings = harness.workspace().settings_dir
    bsl = parse_prefs((settings / BSL_PREFS).read_bytes().decode("latin-1"))
    assert bsl[f"{TOKEN}Strings.color"] == "9,9,9"


def test_enter_in_search_does_not_trigger_buttons(harness: Harness, qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    for button in dialog.findChildren(QPushButton):
        assert button.isDefault() is False
        assert button.autoDefault() is False
    before = dialog.scheme()
    qtbot.keyClick(dialog.search(), Qt.Key.Key_Return)
    assert dialog.scheme() == before
    assert harness.infos == []


def test_unreadable_current_marks_row_and_table_has_defaults(  # type: ignore[no-untyped-def]
    harness: Harness, qtbot
) -> None:
    """`WorkspaceSchemes.current()` кидает при открытии — таблица не остаётся пустой."""
    settings = harness.workspace().settings_dir
    (settings / BSL_PREFS).mkdir(parents=True)  # директория вместо файла → OSError не ENOENT
    dialog = harness.dialog()
    qtbot.addWidget(dialog)
    row0 = dialog.sources().item(0)
    assert row0.toolTip().startswith("Не удалось прочитать")  # noqa: RUF001
    assert dialog.table().rowCount() == 22
    assert _cell(dialog, 0, 2).text() == to_hex(EDT_DEFAULTS["BSL_Keywords"])
    assert harness.errors == []
    dialog.set_color("Strings", (1, 2, 3))  # не должно упасть на `assert swatch is not None`
