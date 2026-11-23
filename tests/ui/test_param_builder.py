"""Конструктор параметров запуска (спека v4, §7.2; экран 2 мокапа)."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QTreeWidget,
)

from onecstarter.domain.cli_catalog import Catalog, Client, Mode, load_catalog
from onecstarter.domain.cli_params import Level
from onecstarter.domain.version import parse_version
from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.services.param_sets import (
    ParamSet,
    load_param_sets,
    save_param_sets,
    upsert_set,
)
from onecstarter.ui.components import Box
from onecstarter.ui.dialogs.param_builder import (
    ACTION_LABELS,
    SECRET_IN_SET,
    SUMMARY_COLOUR_ROLE,
    SUMMARY_GAP,
    SUMMARY_ROLE,
    UNKNOWN_NOTE,
    BuilderPurpose,
    KeyRowDelegate,
    ParamBuilderDialog,
    build_replace_set_box,
    describe_html,
    elide_summary,
)
from onecstarter.ui.theme import LIGHT, stylesheet


def _catalog() -> Catalog:
    def key(name: str, group: str = "debug", **extra: object) -> dict[str, object]:
        entry: dict[str, object] = {
            "name": name,
            "group": group,
            "modes": ["enterprise"],
            "summary": f"кратко {name}",
            "description": f"подробно про {name}",
            "its": "Приложение 7, 7.3",
            "reliability": "doc",
            "versions": {"since": "8.3.18"},
        }
        entry.update(extra)
        return entry

    return load_catalog(
        {
            "group": [
                {"id": "debug", "title": "Отладка и диагностика", "order": 10},
                {"id": "locale", "title": "Язык и локализация", "order": 30},
                {"id": "connection", "title": "Соединение и сжатие", "order": 60},
            ],
            "key": [
                key(
                    "/Debug",
                    args=[
                        {"kind": "enum", "values": ["-tcp", "-http"], "label": "протокол"},
                        {"kind": "flag", "flag": "-attach", "requires": "-http"},
                    ],
                ),
                key(
                    "/DebuggerURL",
                    description="адрес сервера отладки",
                    args=[{"kind": "string", "required": True, "label": "адрес"}],
                ),
                key(
                    "/L",
                    group="locale",
                    modes=["enterprise", "designer"],
                    from_v8i=False,
                    args=[{"kind": "string", "attached": True, "required": True}],
                ),
                key(
                    "/P",
                    group="connection",
                    modes=["enterprise", "designer"],
                    args=[{"kind": "secret", "attached": True}],
                ),
                key(
                    "/SLev",
                    group="connection",
                    clients=["thick"],
                    args=[{"kind": "enum", "values": ["0", "1", "2"], "attached": True}],
                ),
                key("/Proxy", group="connection", modes=["enterprise", "designer"]),
                key("/i85", group="debug", versions={"since": "8.5.1"}),
                key(
                    "/IBName",
                    group="connection",
                    managed=True,
                    args=[{"kind": "string", "attached": True}],
                ),
            ],
        }
    )


def _dialog(qtbot: Any, **kwargs: Any) -> ParamBuilderDialog:
    defaults: dict[str, Any] = {
        "title": "Параметры запуска — База",
        "mode": Mode.ENTERPRISE,
        "purpose": BuilderPurpose.ONCE,
    }
    defaults.update(kwargs)
    dialog = ParamBuilderDialog(_catalog(), **defaults)
    qtbot.addWidget(dialog)
    return dialog


def test_action_label_follows_purpose(qtbot: Any) -> None:
    assert _dialog(qtbot, purpose=BuilderPurpose.WRITE).action_label() == "Применить"
    assert _dialog(qtbot).action_label() == ACTION_LABELS[BuilderPurpose.ONCE]


def test_managed_keys_are_not_offered(qtbot: Any) -> None:
    names = _dialog(qtbot).tree_key_names()
    assert "/IBName" not in names
    assert {"/Debug", "/DebuggerURL", "/L", "/P", "/SLev", "/i85"} <= set(names)


def test_inapplicable_keys_are_dimmed_with_reason(qtbot: Any) -> None:
    dialog = _dialog(qtbot, client=Client.THIN, version=parse_version("8.3.27.2214"))
    assert dialog.is_dimmed("/SLev") and dialog.is_dimmed("/i85")
    assert not dialog.is_dimmed("/Debug")


def test_checking_a_key_appends_it_and_unchecking_removes_it(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Lru  /Foo bar")
    dialog.set_key_checked("/Debug", True)
    assert dialog.result_text() == "/Lru  /Foo bar /Debug"
    dialog.set_key_checked("/L", False)
    assert dialog.result_text() == "/Foo bar /Debug"


def test_untouched_text_is_returned_byte_exact(qtbot: Any) -> None:
    text = '  /lru   /Foo  "x  y"  '
    assert _dialog(qtbot, text=text).result_text() == text


def test_arguments_edit_only_their_key(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Lru   /Debug")
    dialog.set_arg("/Debug", 0, "-http")
    dialog.set_arg("/Debug", 1, "")
    assert dialog.result_text() == "/Lru   /Debug -http -attach"
    dialog.set_arg("/L", 0, "en")
    assert dialog.result_text() == "/Len   /Debug -http -attach"


def test_unknown_keys_are_kept_and_marked(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Foo bar")
    assert dialog.selected_texts() == [f"/Foo — {UNKNOWN_NOTE}"]


def test_secret_is_masked_in_selected_list_and_preview(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text='/P"секрет"')
    assert all("секрет" not in text for text in dialog.selected_texts())
    assert "секрет" not in dialog.preview_text()
    assert "секрет" not in dialog.preview_view().toPlainText()  # показанное, не возвращаемое


def test_findings_use_once_context_with_permanent_line(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Lru", permanent="/Len")
    assert [(f.level, f.text) for f in dialog.findings()] == [
        (Level.INFO, "/L уже есть в постоянных параметрах базы — сработает разовое значение")
    ]


def test_write_purpose_checks_as_permanent_line(qtbot: Any) -> None:
    """[Ф] T-42 Э1 + решение 08.11.2026: /L в постоянной строке — предупреждение."""
    dialog = _dialog(qtbot, purpose=BuilderPurpose.WRITE, text="/Lru")
    assert any(f.level is Level.WARNING and "из списка баз" in f.text for f in dialog.findings())


def test_mode_switch_locked_for_write(qtbot: Any) -> None:
    assert not _dialog(qtbot, purpose=BuilderPurpose.WRITE, mode_locked=True).mode_switch_enabled()
    dialog = _dialog(qtbot)
    dialog.set_mode(Mode.DESIGNER)
    assert dialog.result_mode() is Mode.DESIGNER
    assert dialog.is_dimmed("/Debug")


def test_set_adds_its_keys_and_replaces_same_named(qtbot: Any) -> None:
    sets = (
        ParamSet("Отладка", Mode.ENTERPRISE, "/Debug -http /Len"),
        ParamSet("Тихо", Mode.DESIGNER, "/Lru"),
    )
    dialog = _dialog(qtbot, text="/Lru /Foo", sets=sets)
    assert dialog.set_options() == ["—", "Отладка"]
    dialog.apply_set("Отладка")
    assert dialog.result_text() == "/Len /Foo /Debug -http"


def test_save_as_set_stores_current_line(qtbot: Any) -> None:
    saved: list[ParamSet] = []

    def save(param_set: ParamSet) -> str | None:
        saved.append(param_set)
        return None

    dialog = _dialog(qtbot, text="/Debug -tcp", save_set=save, ask_name=lambda _parent: "Мой")
    dialog.save_as_set()
    assert saved == [ParamSet("Мой", Mode.ENTERPRISE, "/Debug -tcp")]
    assert "Мой" in dialog.set_options()


def test_save_as_set_refuses_secrets_without_asking(qtbot: Any) -> None:
    """Мутационная проверка обязательна: пароль в набор не попадает (спека §4.6)."""

    def ask(_parent: Any) -> str:
        raise AssertionError("имя набора спрашивать не нужно")

    dialog = _dialog(
        qtbot, text='/P"секрет"', save_set=lambda _s: pytest.fail("сохранять нельзя"), ask_name=ask
    )
    dialog.save_as_set()
    assert dialog.notice_text() == SECRET_IN_SET.format(name="/P")


def test_save_error_is_shown(qtbot: Any) -> None:
    dialog = _dialog(
        qtbot, text="/Debug", save_set=lambda _s: "диск недоступен", ask_name=lambda _parent: "Мой"
    )
    dialog.save_as_set()
    assert dialog.notice_text() == "диск недоступен"


def test_search_filters_by_name_and_description(qtbot: Any) -> None:
    dialog = _dialog(qtbot)
    dialog.search("сервера отладки")
    assert dialog.tree_key_names() == ["/DebuggerURL"]
    dialog.search("")
    assert "/L" in dialog.tree_key_names()


def test_remove_selected_drops_unknown_token(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Lru /Foo bar")
    dialog.select_key("/Foo")
    dialog.remove_selected()
    assert dialog.result_text() == "/Lru"


def test_preview_receives_mode_and_text(qtbot: Any) -> None:
    calls: list[tuple[Mode, str]] = []

    def preview(mode: Mode, text: str) -> str:
        calls.append((mode, text))
        return "превью"

    dialog = _dialog(qtbot, text="/Lru", preview=preview)
    assert dialog.preview_text() == "превью"
    assert calls[-1] == (Mode.ENTERPRISE, "/Lru")


def test_key_tree_row_carries_name_and_summary(qtbot: Any) -> None:
    """Мокап, экран 2 (стр. 169): имя — accent моноширинным, описание — text_dim.

    В15; план В, Б1: одна колонка, описание — роль данных элемента.
    """  # noqa: RUF002
    dialog = _dialog(qtbot, palette=LIGHT)
    item = dialog.key_item("/Debug")
    assert item.treeWidget().columnCount() == 1
    assert item.text(0) == "/Debug"
    assert item.data(0, SUMMARY_ROLE) == "— кратко /Debug"
    assert item.foreground(0).color().name() == LIGHT.accent
    assert item.data(0, SUMMARY_COLOUR_ROLE) == LIGHT.text_dim
    assert item.font(0).family() == "Consolas"
    group = item.parent()
    assert group is not None and group.font(0).bold()


def test_inapplicable_key_dims_name_and_summary(qtbot: Any) -> None:
    """Мокап `.off` (стр. 51): прозрачности в QSS нет — приглушаем цветом имя и описание."""
    dialog = _dialog(qtbot, client=Client.THIN, palette=LIGHT)
    item = dialog.key_item("/SLev")
    assert item.foreground(0).color().name() == LIGHT.text_dim
    assert item.data(0, SUMMARY_COLOUR_ROLE) == LIGHT.text_disabled
    assert dialog.is_dimmed("/SLev") and not dialog.is_dimmed("/Debug")


@pytest.mark.parametrize(
    ("width", "expected"),
    [(10_000, "— длинное описание ключа"), (0, ""), (3, "")],
)
def test_elide_summary_keeps_whole_text_or_nothing_when_no_room(
    qapp: Any, width: int, expected: str
) -> None:
    metrics = QFontMetrics(QFont("Segoe UI", 10))
    assert elide_summary(metrics, "— длинное описание ключа", width) == expected


def test_elide_summary_cuts_with_ellipsis(qapp: Any) -> None:
    metrics = QFontMetrics(QFont("Segoe UI", 10))
    text = "— длинное описание ключа"
    shown = elide_summary(metrics, text, metrics.horizontalAdvance(text) // 2)
    assert shown.endswith("…") and len(shown) < len(text)


def test_summary_is_painted_next_to_the_name(qtbot: Any) -> None:
    """План В, Б1: описание видно на экране справа от имени, а не за краем бокса.

    Предпроверка 22.11.2026, п. 5: таблица стилей ставится явно, как в боевом окне, а тусклые
    пиксели считаются только правее конца имени. Рамка QSS-флажка дерева тоже `text_dim`: без
    этого тест был бы зелёным и без делегата, если раньше прошёл `test_app.py`.
    """  # noqa: RUF002
    dialog = _dialog(qtbot, palette=LIGHT)
    dialog.setStyleSheet(stylesheet(LIGHT))
    dialog.show()
    qtbot.waitExposed(dialog)
    item = dialog.key_item("/Debug")
    tree = item.treeWidget()
    assert tree.header().length() <= tree.viewport().width()
    rect = tree.visualItemRect(item)
    option = QStyleOptionViewItem()
    option.initFrom(tree)
    option.rect = rect
    KeyRowDelegate(tree).initStyleOption(option, tree.indexFromItem(item))
    text_rect = tree.style().subElementRect(
        QStyle.SubElement.SE_ItemViewItemText, option, tree
    )
    # Снимок — от rect.left(): отступ текста — место флажка, дальше имя и зазор.
    x0 = (
        text_rect.left()
        - rect.left()
        + QFontMetrics(item.font(0)).horizontalAdvance("/Debug")
        + SUMMARY_GAP
    )
    image = tree.viewport().grab(rect).toImage()
    target = QColor(LIGHT.text_dim)
    dim = 0
    for x in range(x0, image.width()):
        for y in range(image.height()):
            colour = image.pixelColor(x, y)
            distance = (
                abs(colour.red() - target.red())
                + abs(colour.green() - target.green())
                + abs(colour.blue() - target.blue())
            )
            dim += distance < 60
    assert dim >= 5


def test_selected_keys_are_coloured_known_and_unknown(qtbot: Any) -> None:
    """Решение заказчика 4: раскладку не менять; известные — accent, неизвестные — unknown."""
    dialog = _dialog(qtbot, text="/Debug /Foo", palette=LIGHT)
    assert dialog.selected_colours() == [LIGHT.accent, LIGHT.unknown]


def test_description_is_rich_text_with_an_accent_name(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Debug", palette=LIGHT)
    dialog.select_key("/Debug")
    label = dialog.description_label()
    assert label.textFormat() == Qt.TextFormat.RichText
    assert LIGHT.accent in label.text() and "/Debug" in label.text()
    assert "Режим:" in label.text() and LIGHT.text_dim in label.text()


def test_description_meta_names_modes_versions_and_its() -> None:
    """Бывший `test_describe_names_modes_versions_and_its`: `describe` удалена."""
    key = _catalog().key("/L")
    assert key is not None
    assert (
        "Режим: 1С:Предприятие, Конфигуратор · Платформа: с 8.3.18 · ИТС: Приложение 7, 7.3"  # noqa: RUF001
        in describe_html(key, LIGHT)
    )


def test_description_html_escapes_user_catalog_text() -> None:
    key = _catalog().key("/L")
    assert key is not None
    tricky = replace(key, summary="<b>x</b> & y", description="<i>z</i>")
    html = describe_html(tricky, LIGHT)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in html and "&lt;i&gt;z&lt;/i&gt;" in html
    assert "<b>" not in html and "<i>" not in html


def test_preview_colours_keys_unknown_and_base(qtbot: Any) -> None:
    """Мокап `.preview` (стр. 203): база — dim, ключи — accent, неизвестный — unknown."""
    dialog = _dialog(
        qtbot,
        text="/Debug /Foo",
        palette=LIGHT,
        preview=lambda _mode, text: f'1cv8c.exe ENTERPRISE /IBName"Б" {text}'.rstrip(),
    )
    view = dialog.preview_view()
    line = view.toPlainText()
    assert view.format_at(0).foreground().color().name() == LIGHT.text_dim
    assert view.format_at(line.index("/Debug")).foreground().color().name() == LIGHT.accent
    assert view.format_at(line.index("/Foo")).foreground().color().name() == LIGHT.unknown


def test_glued_key_is_unknown_in_the_list_and_in_the_preview(qtbot: Any) -> None:
    """Решение заказчика 4, предпроверка 1.2: прижатый ключ одного цвета в обоих местах.

    В тестовом каталоге `/DebuggerURL` — с раздельным аргументом (как `/C` в реальном).
    """  # noqa: RUF002
    dialog = _dialog(qtbot, text='/DebuggerURL"x"', palette=LIGHT)
    assert dialog.selected_colours() == [LIGHT.unknown]
    view = dialog.preview_view()
    start = view.toPlainText().index("/DebuggerURL")
    assert view.format_at(start).foreground().color().name() == LIGHT.unknown


def test_findings_are_callouts(qtbot: Any) -> None:
    assert _dialog(qtbot, text="/Foo").findings_list().levels() == ["error"]


# -- реальный путь через виджеты (решение 08.11.2026) -----------------------------------


def _edit_widget(dialog: ParamBuilderDialog, index: int = 0) -> QLineEdit:
    widget = dialog._editor_widgets[index]
    assert isinstance(widget, QLineEdit)
    return widget


def test_tab_through_unchanged_field_keeps_fragment_byte_exact(qtbot: Any) -> None:
    text = '/L"ru"  /Debug   -http'
    dialog = _dialog(qtbot, text=text)
    dialog.select_key("/L")
    _edit_widget(dialog).editingFinished.emit()
    assert dialog.result_text() == text


def test_real_edit_rewrites_only_its_fragment(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text='/L"ru"  /Debug   -http')
    dialog.select_key("/L")
    edit = _edit_widget(dialog)
    edit.setText("en")
    edit.editingFinished.emit()
    assert dialog.result_text() == "/Len  /Debug   -http"
    assert dialog.selected_texts()[0] == "/Len"


def test_clearing_enum_updates_dependent_flag_editor(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Debug -http -attach")
    dialog.select_key("/Debug")
    combo, flag = dialog._editor_widgets
    assert isinstance(combo, QComboBox) and isinstance(flag, QCheckBox)
    assert flag.isChecked()
    combo.setCurrentIndex(0)
    combo.activated.emit(0)
    assert dialog.result_text() == "/Debug -attach"
    assert combo.currentText() == ""
    assert flag.isChecked() == ("-attach" in dialog.result_text())


def test_flag_checkbox_toggle_edits_the_string(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Debug -http")
    dialog.select_key("/Debug")
    flag = dialog._editor_widgets[1]
    assert isinstance(flag, QCheckBox)
    flag.setChecked(True)
    assert dialog.result_text() == "/Debug -http -attach"


def test_tree_click_adds_and_removes_key(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Lru")
    item = dialog._key_items["/debug"]
    item.setCheckState(0, Qt.CheckState.Checked)
    assert dialog.result_text() == "/Lru /Debug"
    assert dialog.selected_texts() == ["/Lru", "/Debug"]
    item.setCheckState(0, Qt.CheckState.Unchecked)
    assert dialog.result_text() == "/Lru"


def test_choosing_a_row_shows_its_editors(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/Lru /Debug")
    dialog._selected.setCurrentRow(0)
    assert _edit_widget(dialog).text() == "ru"


def test_set_combo_applies_the_set(qtbot: Any) -> None:
    sets = (ParamSet("Отладка", Mode.ENTERPRISE, "/Debug -http"),)
    dialog = _dialog(qtbot, text="/Lru", sets=sets)
    dialog._set_box.setCurrentIndex(1)
    dialog._set_box.activated.emit(1)
    assert dialog.result_text() == "/Lru /Debug -http"
    assert dialog._set_box.currentIndex() == 0


def test_copy_button_copies_preview(qtbot: Any) -> None:
    copied: list[str] = []
    dialog = _dialog(qtbot, text="/Lru", copy=copied.append)
    button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Копировать строку")
    button.click()
    assert copied == ["/Lru"]


@pytest.mark.parametrize("text", ['/WSP"zzz"', '/AccessToken"zzz"', '/ModifyPassword"zzz"'])
def test_attached_secrets_are_masked_and_not_saved(qtbot: Any, text: str) -> None:
    """Мутационная проверка обязательна: прижатый пароль в набор не попадает."""

    def ask(_parent: Any) -> str:
        raise AssertionError("имя набора спрашивать не нужно")

    dialog = _dialog(
        qtbot, text=text, save_set=lambda _s: pytest.fail("сохранять нельзя"), ask_name=ask
    )
    assert "zzz" not in dialog.preview_text()
    assert "zzz" not in dialog.preview_view().toPlainText()
    assert all("zzz" not in shown for shown in dialog.selected_texts())
    dialog.save_as_set()
    assert dialog.notice_text() == SECRET_IN_SET.format(name=text.split('"')[0])


def test_double_spaces_do_not_block_saving(qtbot: Any) -> None:
    saved: list[ParamSet] = []
    dialog = _dialog(
        qtbot,
        text="/Debug   -tcp",
        save_set=lambda s: saved.append(s),
        ask_name=lambda _parent: "Мой",
    )
    dialog.save_as_set()
    assert len(saved) == 1


def test_enter_in_search_does_not_trigger_the_action(qtbot: Any) -> None:
    dialog = _dialog(qtbot)
    dialog.show()
    accepted: list[int] = []
    dialog.accepted.connect(lambda: accepted.append(1))
    dialog.search("сервера отладки")
    qtbot.keyClick(dialog._search, Qt.Key.Key_Return)
    assert accepted == []
    assert dialog.isVisible()
    current = dialog._tree.currentItem()
    assert current is not None and current.data(0, Qt.ItemDataRole.UserRole) == "/DebuggerURL"


def _proxy_catalog_dialog(qtbot: Any, text: str, saved: list[ParamSet]) -> ParamBuilderDialog:
    return _dialog(
        qtbot, text=text, save_set=lambda s: saved.append(s), ask_name=lambda _parent: "Прокси"
    )


def test_proxy_key_is_not_a_password_and_saves(qtbot: Any) -> None:
    saved: list[ParamSet] = []
    dialog = _proxy_catalog_dialog(qtbot, "/Proxy -PSrv a", saved)
    assert "/P***" not in str(dialog.selected_texts())
    dialog.save_as_set()
    assert [s.params for s in saved] == ["/Proxy -PSrv a"]


def test_proxy_password_blocks_saving(qtbot: Any) -> None:
    saved: list[ParamSet] = []
    dialog = _proxy_catalog_dialog(qtbot, "/Proxy -PSrv a -PPwd x", saved)
    dialog.save_as_set()
    assert saved == []
    assert dialog.notice_text() == SECRET_IN_SET.format(name="/Proxy")
    assert "x" not in dialog.preview_text().split("-PPwd")[1]


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("/ModifyPasswordzzz", "/ModifyPassword"),
        ("/WSPzzz", "/WSP"),
        ("/AccessTokenzzz", "/AccessToken"),
    ],
)
def test_secret_glued_to_unknown_key_name_is_never_shown(
    qtbot: Any, text: str, name: str
) -> None:
    """Мутационная проверка обязательна (финальное ревью, F2): список, замечания, отказ набора."""
    dialog = _dialog(qtbot, text=text, save_set=lambda _s: pytest.fail("сохранять нельзя"))
    assert dialog.selected_texts() == [f"{name} — {UNKNOWN_NOTE}"]
    assert all("zzz" not in (f.key or "") + f.text for f in dialog.findings())
    assert "zzz" not in dialog.preview_text()
    assert "zzz" not in dialog.preview_view().toPlainText()
    dialog.save_as_set()
    assert dialog.notice_text() == SECRET_IN_SET.format(name=name)


def test_glued_known_key_is_labelled_as_spaced_not_unknown(qtbot: Any) -> None:
    """Финальное ревью плана А, I2: `/DebuggerURL"x"` — известный ключ, значение не там.

    В тестовом каталоге `/DebuggerURL` — с раздельным аргументом (как `/C` в реальном).
    """  # noqa: RUF002
    dialog = _dialog(qtbot, text='/DebuggerURL"x"')
    assert dialog.selected_texts() == ["/DebuggerURL — значение пишется через пробел"]
    assert all(UNKNOWN_NOTE not in text for text in dialog.selected_texts())


def test_glued_secret_key_label_does_not_show_its_value(qtbot: Any) -> None:
    """Реальный каталог: прижатый `/WSP"zzz"` подписан именем ключа, значения нет."""
    dialog = ParamBuilderDialog(
        load_cli_catalog(),
        title="Параметры запуска — База",
        mode=Mode.ENTERPRISE,
        purpose=BuilderPurpose.ONCE,
        text='/WSP"zzz"',
    )
    qtbot.addWidget(dialog)
    assert dialog.selected_texts() == ["/WSP — значение пишется через пробел"]


def test_detached_secret_names_its_key(qtbot: Any) -> None:
    dialog = _dialog(qtbot, text="/WSP zzz", save_set=lambda _s: pytest.fail("нельзя"))
    assert "zzz" not in dialog.preview_view().toPlainText()
    dialog.save_as_set()
    assert dialog.notice_text() == SECRET_IN_SET.format(name="/WSP")


def _file_saver(path: Path) -> Any:
    def save(new: ParamSet) -> str | None:
        save_param_sets(path, upsert_set(load_param_sets(path), new))
        return None

    return save


_EXISTING = ParamSet("Отладка", Mode.ENTERPRISE, "/Debug -tcp")


def test_save_as_set_asks_before_replacing_and_replaces_on_yes(
    qtbot: Any, tmp_path: Path
) -> None:
    """Финальное ревью, F5 (решение заказчика 09.11.2026): вопрос при замене."""
    path = tmp_path / "param_sets.json"
    save_param_sets(path, (_EXISTING,))
    asked: list[ParamSet] = []

    def confirm(_parent: Any, existing: ParamSet) -> bool:
        asked.append(existing)
        return True

    dialog = _dialog(
        qtbot, mode=Mode.DESIGNER, text="/Lru", sets=(_EXISTING,), save_set=_file_saver(path),
        ask_name=lambda _parent: "отладка", confirm_replace=confirm,
    )
    dialog.save_as_set()
    assert asked == [_EXISTING]
    assert load_param_sets(path) == (ParamSet("отладка", Mode.DESIGNER, "/Lru"),)


def test_save_as_set_declined_replacement_leaves_file_untouched(
    qtbot: Any, tmp_path: Path
) -> None:
    """Мутационная проверка обязательна (F5): отказ — файл наборов не изменился ни байтом."""
    path = tmp_path / "param_sets.json"
    save_param_sets(path, (_EXISTING,))
    before = path.read_bytes()
    dialog = _dialog(
        qtbot, mode=Mode.DESIGNER, text="/Lru", sets=(_EXISTING,), save_set=_file_saver(path),
        ask_name=lambda _parent: "ОТЛАДКА ", confirm_replace=lambda _parent, _existing: False,
    )
    dialog.save_as_set()
    assert path.read_bytes() == before
    dialog.set_mode(Mode.ENTERPRISE)
    assert dialog.set_options() == ["—", "Отладка"]


def test_save_as_set_with_new_name_does_not_ask(qtbot: Any, tmp_path: Path) -> None:
    path = tmp_path / "param_sets.json"
    save_param_sets(path, (_EXISTING,))
    dialog = _dialog(
        qtbot, text="/Lru", sets=(_EXISTING,), save_set=_file_saver(path),
        ask_name=lambda _parent: "Другой",
        confirm_replace=lambda _parent, _existing: pytest.fail("спрашивать не нужно"),
    )
    dialog.save_as_set()
    assert [s.name for s in load_param_sets(path)] == ["Отладка", "Другой"]


def test_replace_question_names_set_and_mode_and_defaults_to_cancel(qtbot: Any) -> None:
    box = build_replace_set_box(None, _EXISTING)
    qtbot.addWidget(box)
    assert "«Отладка»" in box.text() and "1С:Предприятие" in box.text()  # noqa: RUF001
    default = box.defaultButton()
    assert default is not None and default.text() == "Отмена"
    assert sorted(button.text() for button in box.buttons()) == ["Заменить", "Отмена"]


def test_command_groups_are_not_shown_in_the_key_tree(qtbot: Any) -> None:
    dialog = ParamBuilderDialog(
        load_cli_catalog(),
        title="Параметры запуска — База",
        mode=Mode.DESIGNER,
        purpose=BuilderPurpose.ONCE,
    )
    qtbot.addWidget(dialog)
    tree = dialog.findChildren(QTreeWidget)[0]
    titles = [
        item.text(0)
        for item in (tree.topLevelItem(i) for i in range(tree.topLevelItemCount()))
        if item is not None
    ]
    assert titles
    assert "Резерв и конфигурация" not in titles
    assert "Хранилище конфигурации" not in titles


def test_typing_applies_without_leaving_the_field(qtbot: Any) -> None:
    """Приёмка 21.11.2026, В8: предпросмотр следует за вводом, поле не пересоздаётся."""  # noqa: RUF002
    dialog = _dialog(qtbot, text="/L")
    dialog.select_key("/L")
    edit = _edit_widget(dialog)
    qtbot.keyClicks(edit, "en")
    assert dialog.result_text() == "/Len"
    assert _edit_widget(dialog) is edit and edit.text() == "en"
    assert edit.cursorPosition() == 2


def test_removing_a_key_selects_the_neighbour(qtbot: Any) -> None:
    """Приёмка 21.11.2026, В7: поля и описание не пропадают после «Убрать ключ»."""  # noqa: RUF002
    dialog = _dialog(qtbot, text="/Lru /Debug -http")
    dialog.select_key("/L")
    dialog.remove_selected()
    assert dialog.result_text() == "/Debug -http"
    assert dialog._current_row == 0 and len(dialog._editor_widgets) == 2
    dialog.remove_selected()
    assert dialog.result_text() == "" and dialog._current_row is None


def test_removing_the_last_key_selects_the_previous_one(qtbot: Any) -> None:
    """Финальное ревью плана А, T6-b (В7): убрали последнюю строку — выделена предыдущая."""  # noqa: RUF002
    dialog = _dialog(qtbot, text="/Lru /Debug -http")
    dialog.select_key("/Debug")
    assert dialog._current_row == 1
    dialog.remove_selected()
    assert dialog.result_text() == "/Lru"
    assert dialog._current_row == 0 and len(dialog._editor_widgets) == 1


def test_typing_a_flag_into_the_positional_field_keeps_the_typed_text(qtbot: Any) -> None:
    """Финальное ревью плана А, T6-a: поле, в которое печатают, синхронизация не трогает.

    Аналог `/DisableExtensions` реального каталога: позиционная строка и флаг
    `-AllExtensions`. Набранный в позиционное поле `-AllExtensions` при разборе уходит
    во флаг; без `skip=sender` поле стёрлось бы посреди ввода. Мутационная проверка
    обязательна.
    """  # noqa: RUF002
    catalog = load_catalog(
        {
            "group": [{"id": "config", "title": "Конфигурация", "order": 1}],
            "key": [
                {
                    "name": "/DisableExtensions", "group": "config", "modes": ["enterprise"],
                    "summary": "к", "description": "о", "its": "7.3", "reliability": "doc",  # noqa: RUF001
                    "versions": {"since": "8.3.18"},
                    "args": [
                        {"kind": "string", "label": "имена расширений"},
                        {"kind": "flag", "flag": "-AllExtensions", "label": "все"},
                    ],
                }
            ],
        }
    )
    dialog = ParamBuilderDialog(
        catalog,
        title="Параметры запуска — База",
        mode=Mode.ENTERPRISE,
        purpose=BuilderPurpose.ONCE,
        text="/DisableExtensions",
    )
    qtbot.addWidget(dialog)
    dialog.select_key("/DisableExtensions")
    edit = _edit_widget(dialog)
    qtbot.keyClicks(edit, "-AllExtensions")
    assert dialog.result_text() == "/DisableExtensions -AllExtensions"
    assert _edit_widget(dialog) is edit
    assert edit.text() == "-AllExtensions"
    flag = dialog._editor_widgets[1]
    assert isinstance(flag, QCheckBox) and flag.isChecked()


def test_mode_switch_is_a_segment_with_the_active_mode_primary(qtbot: Any) -> None:
    """Мокап, экран 2 (стр. 162): режим — две кнопки, активная жёлтая (`.btn.pri`)."""
    dialog = _dialog(qtbot)
    enterprise, designer = dialog.mode_button(Mode.ENTERPRISE), dialog.mode_button(Mode.DESIGNER)
    assert enterprise.isCheckable() and enterprise.isChecked()
    assert (enterprise.property("role"), designer.property("role")) == ("primary", None)
    designer.click()
    assert dialog.result_mode() is Mode.DESIGNER
    assert (enterprise.property("role"), designer.property("role")) == (None, "primary")


def test_locked_mode_shows_only_the_active_mode(qtbot: Any) -> None:
    dialog = _dialog(qtbot, purpose=BuilderPurpose.WRITE, mode_locked=True)
    assert not dialog.mode_switch_enabled()
    assert dialog.mode_button(Mode.DESIGNER).isHidden()
    assert not dialog.mode_button(Mode.ENTERPRISE).isHidden()


def test_layout_follows_the_mockup(qtbot: Any) -> None:
    """Мокап, экран 2: бокс 430 px слева, «Выбранные ключи» справа, действие — в полосе."""
    dialog = _dialog(qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert abs(dialog.key_splitter().sizes()[0] - 430) <= 40
    assert dialog.set_box().maximumWidth() == 240
    titles = [box.title_label().text() for box in dialog.findChildren(Box)]
    assert sorted(titles) == ["", "Выбранные ключи"]
    # Фон представлений в боксах — по именам (задача 5), не типовым потомком `#Box`.
    assert dialog.findChild(QTreeWidget, "KeyTree") is not None
    assert dialog.findChild(QListWidget, "SelectedKeys") is not None
    footer_buttons = dialog.footer().findChildren(QPushButton)
    assert dialog.action_button() in footer_buttons
    assert dialog.action_button().property("role") == "primary"
    assert [b.text() for b in footer_buttons if b.text() == "Копировать строку"]


def test_access_code_uc_is_shown_and_saved_in_a_set(qtbot: Any) -> None:
    """Решение заказчика 23.11.2026 (T-44): код доступа `/UC` — не пароль.

    Реальный каталог: виден в предпросмотре и уходит в набор, как любое значение.
    """
    saved: list[ParamSet] = []

    def save(param_set: ParamSet) -> str | None:
        saved.append(param_set)
        return None

    dialog = ParamBuilderDialog(
        load_cli_catalog(),
        title="Параметры запуска — База",
        mode=Mode.ENTERPRISE,
        purpose=BuilderPurpose.ONCE,
        text="/UC 1234",
        save_set=save,
        ask_name=lambda _parent: "Обновление",
    )
    qtbot.addWidget(dialog)
    assert "/UC 1234" in dialog.preview_text()
    dialog.save_as_set()
    assert saved == [ParamSet("Обновление", Mode.ENTERPRISE, "/UC 1234")]
