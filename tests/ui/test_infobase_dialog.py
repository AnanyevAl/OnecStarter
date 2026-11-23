"""Диалог свойств записи: показ, правка, добавление, drag&drop каталога."""

import re
from typing import Any

import pytest
from PySide6.QtCore import QEvent, QMimeData, QObject, QRect, Qt, QUrl
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QWidget,
)

from onecstarter.domain.cli_catalog import Mode
from onecstarter.domain.connect import ConnectKind, classify_connect
from onecstarter.services.cli_catalog import load_cli_catalog
from onecstarter.services.model import InfobaseItem, InfobaseSource, NewInfobase
from onecstarter.services.workspace import RepositorySettings
from onecstarter.ui.components import FORM_LABEL_WIDTH, DialogFooter
from onecstarter.ui.dialogs.group_picker import INDENT
from onecstarter.ui.dialogs.infobase import (
    CREDENTIALS_UNAVAILABLE_NOTE,
    DESIGNER_QUOTE_NOTE,
    DESIGNER_SECRET_NOTE,
    HIDDEN_VALUE,
    OS_AUTH_TOOLTIP,
    PASSWORD_NOT_KEPT_NOTE,
    STORED_PASSWORD_REMOVAL_NOTE,
    WEB_CLIENT_PLACEMENT_NOTE,
    DialogCredentials,
    InfobaseDialog,
    build_connect,
    dropped_directory,
    other_keys,
)
from onecstarter.ui.settings_group import chevron_pixmap
from onecstarter.ui.theme import LIGHT
from tests.ui.conftest import CONVENTIONS, INSTALLED  # noqa: F401


def _item(connect: str, keys: tuple[tuple[str, str], ...], **kwargs: Any) -> InfobaseItem:
    defaults: dict[str, Any] = {
        "key": "id:x", "name": "Бухгалтерия", "folder": "/", "is_group": False,
        "connect": connect, "kind": classify_connect(connect), "requested_version": None,
        "section_default_version": None, "app": None, "source": InfobaseSource.USER,
        "order": None, "section_id": "x", "keys": keys,
    }
    return InfobaseItem(**{**defaults, **kwargs})


def test_secret_section_keys_are_hidden_not_shown() -> None:
    """PPasswd — обязательство 2 ревью плана 3, достижимое только отсюда.

    Хранение паролей вне v1 (§0 спеки 4a), поэтому значение не показывается
    и не редактируется: поле правки пароля создало бы способ записать пароль
    в .v8i открытым текстом.
    """
    item = _item(
        'Srvr="s";Ref="r";',
        (("PPasswd", "AB12CD"), ("PUser", "proxy-user"), ("XTest", "1")),
    )
    assert other_keys(item) == [
        ("PPasswd", HIDDEN_VALUE),
        ("PUser", "proxy-user"),
        ("XTest", "1"),
    ]


def test_secret_values_are_hidden_in_the_widget_not_only_in_the_function(
    qtbot: Any,
) -> None:
    """Маскировка доказывается на таблице диалога, а не на чистой функции.

    Финальное ревью, I6: сторож выше проверяет `other_keys()`, а
    `other_rows()` возвращал тот же список, а не содержимое виджета —
    единственный путь значения на экран (`QTableWidgetItem`,
    `InfobaseDialog.__init__`) не был покрыт ничем, и подмена значения
    при заполнении таблицы не роняла ни один тест маскировки. Цена:
    `PPasswd` — зашифрованный пароль прокси, который спека §3.1 требует
    не показывать, — выводился бы открытым текстом.

    Ячейки читаются напрямую с `QTableWidget`, а не через `other_rows()`,
    чтобы сторож не зависел от того, откуда этот метод берёт данные.
    """  # noqa: RUF002
    item = _item(
        'Srvr="s";Ref="r";',
        (("PPasswd", "AB12CD"), ("PUser", "proxy-user")),
    )
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    table = dialog._table

    cells = [(table.item(row, 0), table.item(row, 1)) for row in range(table.rowCount())]
    assert all(name is not None and value is not None for name, value in cells)
    shown = {name.text(): value.text() for name, value in cells if name and value}

    assert shown == {"PPasswd": HIDDEN_VALUE, "PUser": "proxy-user"}
    assert "AB12CD" not in shown.values()


def test_typed_keys_do_not_repeat_in_the_table() -> None:
    """Connect в таблицу не идёт вовсе: он несёт пароли и показан размещением."""
    item = _item(
        'Srvr="s";Ref="r";Pwd="secret";',
        (("Connect", 'Srvr="s";Ref="r";Pwd="secret";'), ("Version", "8.3.25"),
         ("App", "ThinClient"), ("WA", "1"), ("ID", "x"), ("OrderInList", "-1"),
         ("Folder", "/"), ("External", "0")),
    )
    shown = dict(other_keys(item))
    assert "Connect" not in shown
    assert "Version" not in shown
    assert shown == {"External": "0"}


def test_dialog_shows_placement_and_other_keys(qtbot: Any) -> None:
    item = _item('Srvr="localhost";Ref="ACC";', (("External", "0"),))
    dialog = InfobaseDialog(item, groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.name_text() == "Бухгалтерия"
    assert dialog.placement_text() == 'Srvr="localhost";Ref="ACC"'
    assert dialog.other_rows() == [("External", "0")]


def test_dialog_warns_about_uninstalled_version(qtbot: Any) -> None:
    """Обязательство §4 спеки 4a: подсветка была в 4a, объяснение — здесь."""
    item = _item('File="D:\\b";', (), requested_version="8.3.99.1")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert "не установлена" in dialog.version_hint()


def test_ok_cancel_button_labels_are_russian(qtbot: Any) -> None:
    """Задача 9: диалог начинает писать, кнопка «Закрыть» больше не подходит.

    Тот же дефект, что ловила задача 8 (круг 1) для «Close»: без QTranslator
    стандартные подписи Qt приходят по-английски. Здесь — «ОК»/«Отмена».
    """  # noqa: RUF002
    item = _item('Srvr="localhost";Ref="ACC";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.button_labels() == ["ОК", "Отмена"]  # noqa: RUF001


def test_untouched_dialog_reports_no_changes(qtbot: Any) -> None:
    """Открыл и закрыл — файл не тронут.

    Иначе правка версии перезаписала бы Connect и молча потеряла бы Usr,
    LocaleCode и всё, чего мы не понимаем.
    """
    item = _item('Srvr="s";Ref="r";Usr="admin";', (("External", "0"),))
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None)


# Круг правок 1 (ревью задачи 9, самая сильная модель): табличный тест  # noqa: RUF003
# `test_replace_fragment_keeps_everything_else` в задаче 9 проверял
# `replace_fragment` в отрыве от того, как заполняется поле, — и не поймал
# три критических дефекта на этих самых краевых случаях, потому что поле
# заполнялось одним разбором (`parse_connect`), а писалось другим  # noqa: RUF003
# (`fragment_spans`). Здесь тот же набор краевых случаев проверяется через
# настоящий `InfobaseDialog`, без единого действия пользователя.
@pytest.mark.parametrize(
    ("connect", "kind_hint"),
    [
        # Экранированная кавычка внутри значения — раньше `parse_connect`
        # разворачивал `""` в `"`, `replace_fragment` писал развёрнутое
        # значение обратно в заквоченный слот, разрушая экранирование.
        ('File="C:\\Dir with ""quoted"" bit";Ref="r";', "file"),
        # Пробел перед «=» — решение заказчика (круг правок 2): такой
        # фрагмент не находится по имени вовсе, поле «Сервер» становится
        # нередактируемым (C3), а не пустым/стёртым. Untouched-инвариант  # noqa: RUF003
        # здесь про другое: `Ref` (без пробела) по-прежнему находится
        # и не должен пострадать от соседа, которого не нашли.
        ('Srvr ="s";Ref="r";', "server-space-before-eq"),
        # Пробел после «=», перед кавычкой — `_unquote` проверял первый
        # символ значения (пробел, не кавычка) и не снимал кавычки вовсе.
        ('Srvr= "s" ;Ref="r";', "server-space-after-eq"),
        # Значение без кавычек с пробелами вокруг.  # noqa: RUF003
        ("Srvr= s ;Ref=r;", "server-unquoted-spaces"),
        # SERVER только с Srvr — Ref не существует в строке вовсе.  # noqa: RUF003
        ('Srvr="only";', "server-srvr-only"),
        # SERVER только с Ref — Srvr не существует в строке вовсе.  # noqa: RUF003
        ('Ref="only";', "server-ref-only"),
        # Непарная кавычка — фрагменты Srvr и Ref склеены в один, ни один
        # из них не находится ни одним из разборов.
        ('Srvr=s";Ref="r";', "server-unpaired-quote"),
        # Круг правок 2, item 5: тот же набор краевых случаев, что и у  # noqa: RUF003
        # test_replace_fragment_keeps_everything_else, — их отсутствие здесь
        # и спрятало три критических дефекта в прошлый раз.
        # Имя в нижнем регистре.
        ('srvr="s";Ref="r";', "server-lowercase-name"),
        # Пустое значение в кавычках.
        ('File="";', "file-empty-quoted-value"),
        # Пустое значение без кавычек.
        ("Srvr=;Ref=r;", "server-empty-unquoted-value"),
        # Фрагмент без «=» не мешает соседним.
        ("Srvr=s;GARBAGE;Ref=r;", "server-fragment-without-equals"),
    ],
)
def test_untouched_dialog_writes_nothing_for_edge_case_connect_strings(
    qtbot: Any, connect: str, kind_hint: str
) -> None:
    """Нетронутый диалог не пишет Connect ни на одном краевом случае разбора."""
    item = _item(connect, ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None), kind_hint


@pytest.mark.parametrize(
    ("connect", "kind_hint"),
    [
        ('File="D:\\b";', "file"),
        ('Srvr="s";Ref="r";', "server"),
        ('ws="http://srv/base";', "web"),
    ],
)
@pytest.mark.parametrize("version", ["8.3.25.1633", "8.3.99.1", "8.3"])
def test_untouched_dialog_with_version_writes_nothing(
    qtbot: Any, connect: str, kind_hint: str, version: str
) -> None:
    """Открыл свойства, нажал ОК — ключ Version остался в секции.

    Дыра, которую закрывает тест: ни один прежний охранный тест не давал
    записи `requested_version`, а именно на нём стоит риск вехи. Три значения
    покрывают три ветки `version_options`: установленная, не установленная
    и маска — у двух последних пункт добавляется отдельно, и без него
    `findData` вернул бы -1.
    """  # noqa: RUF002
    item = _item(connect, (), requested_version=version)
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None), f"{kind_hint} / {version}"


def test_rename_only_touches_the_header(qtbot: Any) -> None:
    item = _item('Srvr="s";Ref="r";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Бухгалтерия 3.0")
    assert dialog.changes() == ({}, "Бухгалтерия 3.0")


def test_server_edit_keeps_other_fragments(qtbot: Any) -> None:
    item = _item('Srvr="old";Ref="r";Usr="admin";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_server("new")
    changes, name = dialog.changes()
    assert name is None
    assert changes == {"Connect": 'Srvr="new";Ref="r";Usr="admin";'}


def test_version_choice_is_written(qtbot: Any) -> None:
    item = _item('File="D:\\b";', (), requested_version="8.3.99.1")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_version("8.3.25.1633")
    assert dialog.changes() == ({"Version": "8.3.25.1633"}, None)


def test_untouched_dialog_with_uninstalled_version_reports_no_changes(qtbot: Any) -> None:
    """Тот же принцип, что у Connect, применённый к версии.

    `_version` — выпадающий список из установленных версий плюс «как
    установлено»: без отдельного пункта для самой запрошенной, но не
    установленной версии нетронутый диалог не нашёл бы её в списке и молча
    выбрал бы первый пункт («как установлено»), что при ОК стёрло бы
    Version из файла.
    """  # noqa: RUF002
    item = _item('File="D:\\b";', (), requested_version="8.3.99.1")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None)


def test_untouched_dialog_with_app_auto_reports_no_changes(qtbot: Any) -> None:
    """Нетронутый диалог с `App=Auto` ничего не пишет.

    Комбобокс сопоставляет `App=Auto` и отсутствие ключа пункту «Авто» с данными
    `None`; если бы сравнение в `changes()` шло с сырым `item.app` («Auto»),
    нетронутый диалог решил бы, что App поменяли на `None`, и переписал бы ключ.
    """  # noqa: RUF002
    item = _item('File="D:\\b";', (), app="Auto")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None)


def test_untouched_dialog_with_orphan_folder_reports_no_changes(qtbot: Any) -> None:
    """База в папке без секции-группы (`Folder` без своей секции) — обычное дело.

    `groups` формируется из существующих секций-групп и такой путь не несёт;
    `QComboBox.setCurrentText` на нередактируемом списке молча остаётся
    на первом пункте, если текста нет среди элементов, — без явного
    добавления текущей папки нетронутый диалог перенёс бы запись в корень.
    """
    item = _item('File="D:\\b";', (), folder="/Нет такой группы")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None)


def test_app_choice_is_written(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_app("ThinClient")
    assert dialog.changes() == ({"App": "ThinClient"}, None)


def test_switching_back_to_auto_writes_app_auto_explicitly(qtbot: Any) -> None:
    """Приёмка 21.11.2026, Ф3: «Авто» — `App=Auto`, а не удаление ключа."""  # noqa: RUF002
    item = _item('File="D:\\b";', (), app="ThinClient")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_app(None)
    assert dialog.changes() == ({"App": "Auto"}, None)


@pytest.mark.parametrize(
    ("keys", "checked_on_open", "actions", "expected"),
    [
        # Нет ключа: платформа и штатный стартер читают это как WA=1 ([Ф] T-30).
        ((), True, (), {}),
        ((), True, (False,), {"WA": "0"}),
        ((("WA", "1"),), True, (False,), {"WA": "0"}),
        ((("WA", "0"),), False, (True,), {"WA": "1"}),
        ((("WA", "0"),), False, (), {}),
        ((("WA", "1"),), True, (False, True), {}),
    ],
)
def test_os_auth_checkbox_reads_missing_wa_as_on_and_writes_zero(
    qtbot: Any,
    keys: tuple[tuple[str, str], ...],
    checked_on_open: bool,
    actions: tuple[bool, ...],
    expected: dict[str, str],
) -> None:
    """T-30.2: снятый флажок пишет WA=0 — удалённый ключ платформа читает как WA=1.

    Мутационная проверка обязательна: снятый флажок снова даёт `None` —
    падают строки «сняли»; чтение `== "1"` — падают строки «нет ключа».
    """
    item = _item('File="D:\\b";', keys)
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog._os_auth.isChecked() is checked_on_open
    for value in actions:
        dialog.set_os_auth(value)
    assert dialog.changes() == (expected, None)


def test_os_auth_checkbox_tooltip_names_starter_options(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert OS_AUTH_TOOLTIP == (
        "Как «Вариант аутентификации» в штатном стартере: отмечено — "
        "«Выбирать автоматически», снято — «Запрашивать имя и пароль»"
    )
    assert dialog._os_auth.toolTip() == OS_AUTH_TOOLTIP


def test_folder_choice_is_written(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_folder("Клиенты")
    assert dialog.changes() == ({"Folder": "Клиенты"}, None)


def test_file_path_edit_keeps_other_fragments(qtbot: Any) -> None:
    item = _item('File="D:\\b";Usr="admin";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path("E:\\c")
    assert dialog.changes() == ({"Connect": 'File="E:\\c";Usr="admin";'}, None)


def test_web_url_edit_keeps_other_fragments(qtbot: Any) -> None:
    item = _item('ws="http://old/base";wsp="user";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_url("http://new/base")
    assert dialog.changes() == ({"Connect": 'ws="http://new/base";wsp="user";'}, None)


def test_unknown_kind_has_no_placement_fields_to_edit(qtbot: Any) -> None:
    """`UNKNOWN` — строку соединения не разобрали, править в ней нечего."""
    item = _item("просто текст", ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog._placement_fields() == []


def test_folder_picker_shows_groups_as_a_tree(qtbot: Any) -> None:
    """T-11, п. 5: выпадающий список групп — с отступом по вложенности, значения — пути."""  # noqa: RUF002
    item = _item('File="D:\\b";', (), folder="/Клиенты/Розница")
    dialog = InfobaseDialog(
        item, groups=["/", "Клиенты", "Клиенты/Розница"], installations=INSTALLED, cfg_rules=[]
    )
    qtbot.addWidget(dialog)
    assert dialog.groups_shown() == ["/", "Клиенты", "Клиенты/Розница"]
    assert dialog._folder.currentText() == f"{INDENT}Розница"
    assert dialog.changes() == ({}, None)


# -- I7 (круг правок 1): normalize_folder на обеих сторонах сравнения ------------


def test_untouched_nested_record_reports_no_folder_change(qtbot: Any) -> None:
    """Обычная вложенная запись — не осиротевшая, но форма пути не совпадает.

    `groups` несёт нормализованный путь («Клиенты», без слэша — так строит
    `group_path`), `item.folder` — сырое значение файла («/Клиенты», со
    слэшем — так пишет платформа, [Ф] render_folder). До правки сравнение
    шло по сырому виду, расхождение цепляло КАЖДУЮ вложенную запись, а не
    только настоящую сироту без секции-группы: нетронутый диалог решал бы,
    что Folder надо переписать на нормализованный вид.
    """  # noqa: RUF002
    item = _item('File="D:\\b";', (), folder="/Клиенты")
    dialog = InfobaseDialog(item, groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.changes() == ({}, None)


def test_untouched_nested_record_does_not_duplicate_the_group_in_the_dropdown(
    qtbot: Any,
) -> None:
    """Тот же случай с другой стороны: список групп не должен раздваиваться."""  # noqa: RUF002
    item = _item('File="D:\\b";', (), folder="/Клиенты")
    dialog = InfobaseDialog(item, groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.groups_shown().count("Клиенты") == 1


# -- M9 (круг правок 1): сеттеры падают, если пункта нет среди предложенных -----


def test_set_folder_rejects_a_value_the_dialog_never_offered(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    with pytest.raises(ValueError, match="Незнакомая группа"):
        dialog.set_folder("Незнакомая группа")


def test_set_version_rejects_a_value_the_dialog_never_offered(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    with pytest.raises(ValueError, match=r"9\.9\.9\.9"):
        dialog.set_version("9.9.9.9")


def test_set_app_rejects_a_value_the_dialog_never_offered(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    with pytest.raises(ValueError, match="WebClient"):
        dialog.set_app("WebClient")


def test_web_record_accepts_web_client_app(qtbot: Any) -> None:
    item = _item('ws="http://srv/base";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_app("WebClient")
    assert dialog.changes() == ({"App": "WebClient"}, None)


# -- I1 финального ревью ветки: «Веб-клиент» плюс не-веб размещение ------------  # noqa: RUF003


def test_web_client_app_blocks_ok_after_the_placement_changed(qtbot: Any) -> None:
    """Находка I1: диалог давал собрать незапускаемую запись и молча её сохранить.

    Пункт «Веб-клиент (браузер)» добавляется по виду СОХРАНЁННОЙ записи
    (`item.kind`), а размещение меняется тут же, отдельным комбобоксом.
    Сочетание `App=WebClient` + `File=` отвергается при КАЖДОМ запуске,
    и связать отказ со сменой размещения, сделанной раньше, пользователь
    не сможет.

    Путь заполняется намеренно: без него «ОК» и так неактивна («Заполните:
    «Путь»»), и тест был бы зелёным на пустышке. Разделяет два случая
    именно текст пояснения.
    """  # noqa: RUF002
    item = _item('ws="http://srv/base";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    dialog.set_app("WebClient")
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path("D:\\Bases\\Acc")

    assert not dialog.accepts()
    assert dialog.required_hint() == WEB_CLIENT_PLACEMENT_NOTE

    # Блокировка не залипает: вернули веб-размещение — «ОК» снова активна.  # noqa: RUF003
    dialog.set_kind(ConnectKind.WEB)
    assert dialog.accepts()
    assert dialog.required_hint() == ""


def test_other_client_is_free_to_go_with_any_placement(qtbot: Any) -> None:
    """Обратная сторона: блокируется ровно веб-клиент, а не смена размещения.

    Без этой пары проверка могла бы запирать «ОК» на любой смене вида,
    и тест выше остался бы зелёным.
    """  # noqa: RUF002
    item = _item('ws="http://srv/base";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    dialog.set_app("ThinClient")
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path("D:\\Bases\\Acc")

    assert dialog.accepts()


def test_record_that_already_carries_web_client_app_is_not_locked_out(qtbot: Any) -> None:
    """Сочетание, уже лежащее в файле, «ОК» не запирает.

    Тот же принцип, что у `_placement_violation`: то, чего пользователь
    не трогал, — не его ввод. Запись с `App=WebClient` при не-ws строке
    соединения существует (спека §6), и открыть её ради правки группы
    или версии обязано быть можно. Пункт достаётся ей существующим
    механизмом «незнакомое значение сохраняем отдельным пунктом».
    """  # noqa: RUF002
    item = _item('File="D:\\b";', (), app="WebClient")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    assert dialog.accepts()
    assert dialog.changes() == ({}, None)

    # А вот тронуть размещение и оставить веб-клиент — уже нельзя.  # noqa: RUF003
    dialog.set_kind(ConnectKind.SERVER)
    dialog.set_server("srv")
    dialog.set_ref("acc")
    assert not dialog.accepts()
    assert dialog.required_hint() == WEB_CLIENT_PLACEMENT_NOTE


# -- I4/item 3 (круги правок 1-2): недопустимый символ блокирует ОК -------------  # noqa: RUF003


def test_quote_typed_by_user_is_flagged_as_a_violation(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path('D:\\evil"path')
    assert dialog._placement_violation() == ("Путь", '"')


def test_semicolon_typed_by_user_is_flagged_as_a_violation(qtbot: Any) -> None:
    """Круг правок 2, item 3: воспроизведено через настоящий диалог ревьюером.

    `_edited_connect` применяет `replace_fragment` последовательно к
    промежуточной строке: `;`, вписанный в поле «Сервер», создаёт для поля
    «Имя базы на сервере» новый (чужой) фрагмент `Ref` в уже изменённом
    тексте — второй `replace_fragment` находит и правит не то, что должно,
    даже если само поле осталось нетронутым, и в файл уходит дублированный
    ключ вместо набранного текста. `;` — легальный символ в путях Windows
    и в query URL, не экзотика.
    """  # noqa: RUF002
    item = _item("Srvr=s;Ref=r;", ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_server("s;Ref=evil")
    assert dialog._placement_violation() == ("Сервер", ";")


def test_pre_existing_escaped_quote_is_not_a_violation_when_untouched(qtbot: Any) -> None:
    """Экранированная пара `""`, уже бывшая в файле, — не ввод пользователя."""
    item = _item('File="C:\\Dir with ""quoted"" bit";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog._placement_violation() is None


def test_no_forbidden_character_no_violation(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path("E:\\clean")
    assert dialog._placement_violation() is None


def test_accept_is_blocked_when_a_violation_is_present(qtbot: Any, monkeypatch: Any) -> None:
    """Круг правок 2, item 4: три теста выше зовут `_placement_violation()`

    напрямую — предикат доказан, но ничто не связывало «ввёл кавычку → диалог
    не принят». `QMessageBox.warning` подменяется на no-op: настоящее модальное
    окно блокировало бы офскрин-тест тем же способом, что и `QDialog.exec()`
    (тот же приём, что у `_build_menu`/`_show_menu`/`_build_properties_dialog`).
    """  # noqa: RUF002
    monkeypatch.setattr(
        "onecstarter.ui.dialogs.infobase.QMessageBox.warning",
        lambda *args, **kwargs: None,
    )
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path('D:\\evil"path')
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_accept_succeeds_when_there_is_no_violation(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Бухгалтерия 3.0")
    dialog._on_accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


# -- I6 (круг правок 1): действующая версия видна и без явного Version ----------


def test_version_hint_shows_effective_version_when_none_requested(qtbot: Any) -> None:
    """Задача 8 показывала действующую версию даже когда Version не задан —

    QComboBox не должен был потерять эту информацию, просто заменив собой
    QLabel.
    """
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert "8.3.25.1633" in dialog.version_hint()


def test_web_kind_default_version_label_has_no_nonsensical_web_suffix(qtbot: Any) -> None:
    """Круг правок 2, item 5: `cell.text` подставлялся в подпись безусловно —

    у веб-записи `version_cell` всегда отдаёт `cell.text == "веб"` (Version
    там ни на что не влияет), и подпись читалась как «как установлено (веб)».

    Задача 5 вехи v2.3 (спека §4): с неё `cell.hint` у WEB — больше не
    `None`, а честная подсказка про публикацию, и слово «веб» законно
    встречается в её тексте («веб-сервере»). Проверка сужена до самого
    исходного дефекта — скобочного «(веб)», приклеенного к подписи, а не
    до полного отсутствия слова «веб» в подсказке.
    """  # noqa: RUF002
    item = _item('ws="http://srv/base";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.version_hint().startswith("как установлено")
    assert "(веб)" not in dialog.version_hint()


def test_web_kind_with_explicit_version_has_no_nonsensical_web_suffix(qtbot: Any) -> None:
    """Круг правок 3, мелочь 1: тот же дефект строкой ниже в `_version_options`.

    Пункт для запрошенной-но-не-подошедшей версии тоже брал подпись из
    `cell.text` безусловно — веб-запись с `Version=8.3.99.1` показывала бы
    в выпадающем списке пункт с подписью «веб» вместо «8.3.99.1».

    Задача 5 вехи v2.3 (спека §4): проверка сужена так же, как в соседнем
    тесте выше — «(веб)» скобочным суффиксом быть не должно, но честная
    подсказка про публикацию законно содержит слово «веб».
    """  # noqa: RUF002
    item = _item('ws="http://srv/base";', (), requested_version="8.3.99.1")
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert "(веб)" not in dialog.version_hint()
    assert "8.3.99.1" in dialog.version_hint()


# -- C3 (круг правок 1): предлагаем только реально найденные фрагменты ----------


def test_server_with_only_srvr_offers_only_srvr_for_editing(qtbot: Any) -> None:
    item = _item('Srvr="only";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert [name for name, _field in dialog._placement_fields()] == ["Srvr"]


def test_server_with_only_ref_offers_only_ref_for_editing(qtbot: Any) -> None:
    item = _item('Ref="only";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert [name for name, _field in dialog._placement_fields()] == ["Ref"]


def test_unpaired_quote_offers_only_the_fragment_that_swallowed_the_tail(qtbot: Any) -> None:
    """Непарная кавычка склеивает Srvr и Ref в один фрагмент, а не теряет их.

    Круг правок 2, item 1 (безусловный сброс хвоста): `Srvr` находится —
    с захваченным (нечистым) значением, — `Ref` внутри того же хвоста
    отдельно не выделяется вовсе и остаётся нередактируемым (C3). Untouched-
    ное поведение при этом не меняется: `changes()` по-прежнему пуст,
    потому что поле показывает и вернёт тот же самый захваченный текст.
    """  # noqa: RUF002
    item = _item('Srvr=s";Ref="r";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert [name for name, _field in dialog._placement_fields()] == ["Srvr"]
    assert dialog.changes() == ({}, None)


# -- Задача 10: build_connect ---------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "kwargs", "expected"),
    [
        (ConnectKind.FILE, {"file_path": r"D:\bases\acc"}, r'File="D:\bases\acc";'),
        (ConnectKind.SERVER, {"server": "srv", "ref": "ACC"}, 'Srvr="srv";Ref="ACC";'),
        (ConnectKind.WEB, {"url": "http://srv/b"}, 'ws="http://srv/b";'),
    ],
)
def test_build_connect(kind: ConnectKind, kwargs: dict[str, str], expected: str) -> None:
    assert build_connect(kind, **kwargs) == expected


@pytest.mark.parametrize("char", ['"', ";"])
def test_build_connect_rejects_forbidden_characters(char: str) -> None:
    """Кавычки и `;` в новом значении отклоняются, а не удваиваются/пропускаются.

    Решение по итогам ревью (см. докстринг `build_connect`): экранирование
    кавычек в Connect не подтверждено (скил v8i-format, «Непроверенное»),
    удвоить их самим при сборке новой строки значило бы сделать то же самое
    предположение, которое задача 9 уже отвергла для точечной правки
    существующей записи (`_placement_violation`). `;` разделяет фрагменты
    и оборвал бы значение пополам.
    """  # noqa: RUF002
    with pytest.raises(ValueError, match=re.escape(char)):
        build_connect(ConnectKind.FILE, file_path=f'D:\\a{char}b')


def test_build_connect_rejects_unknown_kind() -> None:
    """UNKNOWN не входит в набор видов, для которых определена сборка."""
    with pytest.raises(ValueError, match="UNKNOWN"):
        build_connect(ConnectKind.UNKNOWN, file_path="x")


# -- Задача 10: диалог добавления записи -----------------------------------------


def test_new_record_returns_name_connect_and_folder(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/", "Клиенты"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\bases\acc")
    dialog.set_name("Бухгалтерия")
    dialog.set_folder("Клиенты")
    assert dialog.new_record() == NewInfobase(
        name="Бухгалтерия", connect=r'File="D:\bases\acc";', folder="Клиенты"
    )


def test_new_record_defaults_kind_to_file(qtbot: Any) -> None:
    """Диалог добавления сразу предлагает рабочий вид, не пустое состояние."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\bases\acc")
    dialog.set_name("Бухгалтерия")
    assert dialog.new_record() == NewInfobase(
        name="Бухгалтерия", connect=r'File="D:\bases\acc";', folder="/"
    )


def test_new_record_server_kind(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.SERVER)
    dialog.set_server("srv")
    dialog.set_ref("ACC")
    dialog.set_name("Учёт")
    assert dialog.new_record() == NewInfobase(
        name="Учёт", connect='Srvr="srv";Ref="ACC";', folder="/"
    )


def test_new_dialog_has_no_hint_os_auth_or_other_keys_widgets(qtbot: Any) -> None:
    """Записи ещё не существует — показывать расхождение с платформой, WA
    и прочие ключи секции нечего.

    Задача 7: «Версия» и «Клиент» диалог добавления теперь строит и
    показывает (см. `test_add_dialog_offers_version_and_client` ниже) —
    этот тест больше не о них, а о том, что подсказка версии
    (`version_hint`), аутентификация ОС и таблица прочих ключей
    у записи, которой ещё нет, не появляются. Косвенная проверка через
    публичные геттеры, а не через private-атрибуты: `version_hint`/
    `other_rows` обязаны остаться безопасными для диалога добавления,
    а не падать `AttributeError`, если кто-то их всё-таки вызовет.
    """  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.version_hint() == ""
    assert dialog.other_rows() == []


def test_add_dialog_offers_version_and_client(qtbot: Any) -> None:
    """Задача 7: диалог добавления предлагает то же самое, что диалог правки."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\Bases\New")
    dialog.set_name("Новая")

    dialog.set_version("8.3.25.1633")
    dialog.set_app("ThinClient")
    record = dialog.new_record()

    assert record.version == "8.3.25.1633"
    assert record.app == "ThinClient"


def test_untouched_add_dialog_asks_for_neither_version_nor_client(qtbot: Any) -> None:
    """По умолчанию «как установлено» и «Авто» — в файл не пишется ничего.

    `.v8i` читает и перезаписывает штатный стартер 1С: пустая строка вместо
    отсутствующего ключа — дефект записи, а не мелочь.
    """  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\Bases\New")
    dialog.set_name("Новая")

    record = dialog.new_record()

    assert record.version is None
    assert record.app is None


def test_set_kind_rejects_a_value_the_dialog_never_offered(qtbot: Any) -> None:
    """M9: диалог добавления не предлагает UNKNOWN — это не цель выбора."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    with pytest.raises(ValueError, match="UNKNOWN"):
        dialog.set_kind(ConnectKind.UNKNOWN)


def test_new_dialog_quote_is_flagged_as_a_violation(qtbot: Any) -> None:
    """Та же защита, что и у правки существующей записи, — на пути пересборки.

    Здесь сравнивать введённое значение не с чем (записи ещё нет), поэтому
    `_violation` проверяет само значение целиком, а не разницу с сырым срезом.
    """  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path('D:\\evil"path')
    assert dialog._violation() == ("Путь", '"')


def test_new_dialog_accept_is_blocked_when_a_violation_is_present(
    qtbot: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "onecstarter.ui.dialogs.infobase.QMessageBox.warning",
        lambda *args, **kwargs: None,
    )
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path("D:\\evil;path")
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted


# -- незаполненное обязательное поле гасит «ОК» (I8, расширено N3) --------------  # noqa: RUF003
#
# `_on_accept` проверял только запрещённые символы, поэтому `Ctrl+N` → задано
# только имя → «ОК» давал `build_connect(FILE, file_path="")` == `File="";`,  # noqa: RUF003
# и запись с пустым путём уходила в файл, общий со штатным стартером  # noqa: RUF003
# (замечание I8).
#
# Ре-ревью, N3: имя было защищено только `validate_section_name` в services,  # noqa: RUF003
# то есть отказом ПОСЛЕ нажатия «ОК». Внутри одного диалога получалось  # noqa: RUF003
# противоречие: поле пути запирает кнопку до клика, поле имени — нет.
# Решение заказчика 09.08.2026 «отказ показывается до действия» распространяется
# и на имя; спека §3.1 расширена с «размещение» на «имя и размещение».  # noqa: RUF003


def test_new_dialog_refuses_an_empty_placement_before_the_click(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Новая база")

    assert dialog.accepts() is False
    assert dialog.required_hint() == "Заполните: «Путь»"


def test_new_dialog_refuses_an_empty_name_before_the_click(qtbot: Any) -> None:
    """Имя — такое же обязательное поле, как и размещение (N3)."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\bases\new")

    assert dialog.accepts() is False
    assert dialog.required_hint() == "Заполните: «Имя»"


def test_new_dialog_lists_every_empty_required_field(qtbot: Any) -> None:
    """Пустой диалог перечисляет всё, что мешает, а не первое попавшееся."""  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    assert dialog.accepts() is False
    assert dialog.required_hint() == "Заполните: «Имя», «Путь»"


def test_new_dialog_treats_a_whitespace_name_as_empty(qtbot: Any) -> None:
    """Имя из одних пробелов `validate_section_name` тоже отвергает."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\bases\new")

    dialog.set_name("   ")

    assert dialog.accepts() is False


def test_existing_record_refuses_a_cleared_name(qtbot: Any) -> None:
    """Стереть имя у существующей записи и нажать «ОК» тоже нельзя."""  # noqa: RUF002
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.accepts() is True

    dialog.set_name("")

    assert dialog.accepts() is False


def test_new_dialog_accepts_once_everything_required_is_filled(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    dialog.set_name("Новая база")
    dialog.set_file_path(r"D:\bases\new")

    assert dialog.accepts() is True
    assert dialog.required_hint() == ""


def test_new_dialog_treats_whitespace_as_an_empty_placement(qtbot: Any) -> None:
    """Путь из одних пробелов — то же пустое размещение, только незаметное."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    dialog.set_file_path("   ")

    assert dialog.accepts() is False


def test_new_dialog_requires_both_server_fields(qtbot: Any) -> None:
    """У серверной базы обязательны оба поля: `Srvr` без `Ref` нерабочая."""  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Новая база")
    dialog.set_kind(ConnectKind.SERVER)

    assert dialog.accepts() is False
    assert dialog.required_hint() == "Заполните: «Сервер», «Имя базы на сервере»"

    dialog.set_server("srv")
    assert dialog.accepts() is False
    assert dialog.required_hint() == "Заполните: «Имя базы на сервере»"

    dialog.set_ref("ACC")
    assert dialog.accepts() is True


def test_kind_change_rechecks_the_placement(qtbot: Any) -> None:
    """Смена вида пересчитывает состояние «ОК»: поля нового вида ещё пусты."""  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Новая база")
    dialog.set_file_path(r"D:\bases\new")
    assert dialog.accepts() is True

    dialog.set_kind(ConnectKind.WEB)

    assert dialog.accepts() is False
    assert dialog.required_hint() == "Заполните: «Адрес»"


def test_dropped_directory_unblocks_the_ok_button(qtbot: Any, tmp_path: Any) -> None:
    """Перетащенный каталог заполняет и путь, и пустое имя — «ОК» оживает сама.

    Оба обязательных поля закрываются одним жестом (`accept_directory`
    подставляет имя каталога, если имя пусто), поэтому кнопка становится
    активной без единого нажатия клавиши.
    """  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.accepts() is False

    dialog.accept_directory(str(tmp_path))

    assert dialog.accepts() is True


def test_existing_record_refuses_a_cleared_placement(qtbot: Any) -> None:
    """Стереть путь у существующей записи и нажать «ОК» тоже нельзя."""  # noqa: RUF002
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.accepts() is True

    dialog.set_file_path("")

    assert dialog.accepts() is False


def test_unparsed_placement_does_not_lock_the_ok_button(qtbot: Any) -> None:
    """Фрагмент не нашёлся — поле нередактируемо, и «ОК» оно не запирает.

    Требовать заполнить то, что заполнить нельзя (`_init_placement` делает
    такое поле `setReadOnly`), значило бы запереть диалог навсегда у записи,
    открытой ради правки версии или группы. Пустого размещения мы ей при
    этом не создаём — эта часть `Connect` просто не трогается.
    """  # noqa: RUF002
    # Пробел вокруг «=» — фрагмент не находится по имени (круг правок 2
    # задачи 9), поле «Сервер» остаётся нередактируемым и пустым.
    item = _item('Srvr ="s";Ref="r";', (), kind=ConnectKind.SERVER)
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    assert dialog._server.isReadOnly()
    assert dialog._server.text() == ""
    assert dialog.accepts() is True


def test_unknown_record_does_not_lock_the_ok_button(qtbot: Any) -> None:
    """У неразобранной записи полей размещения нет — правка версии возможна."""  # noqa: RUF002
    item = _item("что-то непонятное", ())
    assert item.kind is ConnectKind.UNKNOWN
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)

    assert dialog.accepts() is True


# -- Задача 10: смена вида размещения существующей записи -----------------------


def test_kind_change_warns_about_lost_keys(qtbot: Any) -> None:
    """Смена вида перезаписывает Connect целиком — молчать об этом нельзя."""  # noqa: RUF002
    item = _item('Srvr="s";Ref="r";Usr="admin";LocaleCode="ru";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.kind_change_warning() is None
    dialog.set_kind(ConnectKind.FILE)
    warning = dialog.kind_change_warning()
    assert warning is not None
    assert "Usr" in warning and "LocaleCode" in warning


def test_kind_change_warning_is_none_when_nothing_would_be_lost(qtbot: Any) -> None:
    """Только Srvr/Ref в записи — смена вида ничего не теряет, нагонять нечего."""
    item = _item('Srvr="s";Ref="r";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    assert dialog.kind_change_warning() is None


def test_untouched_dialog_with_unknown_kind_reports_no_changes(qtbot: Any) -> None:
    """Регрессия задачи 10: UNKNOWN как пункт _kind_box не должен читаться

    как «вид сменили» на нетронутом диалоге (I7/M9 — тот же класс дефекта,
    что и несогласованная форма Folder в задаче 9).
    """
    item = _item("просто текст", ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.kind_change_warning() is None
    assert dialog.changes() == ({}, None)


def test_kind_change_writes_rebuilt_connect_via_changes(qtbot: Any) -> None:
    """`changes()` кладёт Connect = build_connect(...) при смене вида (шаг 3 брифа)."""
    item = _item('Srvr="s";Ref="r";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\new")
    changes, name = dialog.changes()
    assert name is None
    assert changes["Connect"] == r'File="D:\new";'


def test_kind_change_back_to_original_uses_point_edit_again(qtbot: Any) -> None:
    """Туда-обратно (SERVER → FILE → SERVER) — снова точечная правка, не пересборка.

    Пользователь мог передумать; вернувшись к исходному виду, диалог обязан
    вести себя так, будто вид не трогали, и сохранить Usr, который пересборка
    потеряла бы.
    """
    item = _item('Srvr="s";Ref="r";Usr="admin";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_kind(ConnectKind.SERVER)
    assert dialog.kind_change_warning() is None
    assert dialog.changes() == ({}, None)


# -- Задача 10: drag&drop каталога -----------------------------------------------


def test_dropped_directory_fills_path_and_name(qtbot: Any) -> None:
    """Перетащили каталог — имя подставилось из его названия, если поле пустое."""  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.accept_directory(r"D:\bases\Бухгалтерия")
    assert dialog.new_record().name == "Бухгалтерия"
    assert dialog.new_record().connect == r'File="D:\bases\Бухгалтерия";'


def test_dropped_directory_does_not_overwrite_typed_name(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Своё имя")
    dialog.accept_directory(r"D:\bases\Бухгалтерия")
    assert dialog.new_record().name == "Своё имя"


def test_dropped_directory_on_existing_server_record_switches_kind_to_file(qtbot: Any) -> None:
    """Перетаскивание каталога на диалог правки — тоже смена вида (задача 10).

    Тот же путь, что и ручной выбор в `_kind_box`: `Usr` — фрагмент сверх
    Srvr/Ref, warning загорится, и запись не пострадает без подтверждения
    (`BasesView._apply_properties`).
    """
    item = _item('Srvr="s";Ref="r";Usr="admin";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.accept_directory(r"D:\bases\Новая")
    assert dialog._kind_box.currentData() is ConnectKind.FILE
    assert dialog.kind_change_warning() is not None


def test_dropped_directory_helper_accepts_a_single_local_directory(tmp_path: Any) -> None:
    """Разделители пути нормализуются под ОС — см. докстринг `dropped_directory`.

    Круг правок 1 (ревью задачи 10): сравнение было через `Path(result) ==
    directory`, а на Windows `Path("a/b") == Path("a\\b")` — тест не заметил бы
    отката нормализующей обёртки `Path(...)` внутри `dropped_directory` назад
    к сырому `toLocalFile()` (прямые слэши, см. докстринг функции). Строгое
    сравнение строк требует, чтобы разделители были фактически приведены
    к виду ОС, а не просто эквивалентны как путь.
    """  # noqa: RUF002
    directory = tmp_path / "Бухгалтерия"
    directory.mkdir()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(directory))])
    assert dropped_directory(mime) == str(directory)


def test_dropped_directory_helper_rejects_multiple_urls(tmp_path: Any) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))])
    assert dropped_directory(mime) is None


def test_dropped_directory_helper_rejects_a_file(tmp_path: Any) -> None:
    """Файловая база — каталог с 1Cv8.1CD внутри, не сам файл базы."""  # noqa: RUF002
    file_path = tmp_path / "f.txt"
    file_path.write_text("x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(file_path))])
    assert dropped_directory(mime) is None


def test_dropped_directory_helper_rejects_a_non_local_url() -> None:
    mime = QMimeData()
    mime.setUrls([QUrl("http://example.com/base")])
    assert dropped_directory(mime) is None


# -- Задача 10, круг правок 1 (ревью): пробел плана — кнопка «Обзор…» --------
#
# Спека §3.1 требует «обзор каталога и drag&drop каталога»; план потерял первую
# половину при декомпозиции — ни один из брифов задач 10-19 её не заявлял.
# Диалог выбора инжектируется (`choose_directory`) тем же приёмом, что
# и `open_directory` в `ConnectionPanel` (`ui/bases/panel.py`): состав
# и поведение проверяются без модального `QFileDialog`.


def test_browse_button_fills_path_and_name_when_directory_chosen(qtbot: Any) -> None:
    """Выбор каталога через «Обзор…» — те же правила, что и у drag&drop."""  # noqa: RUF002
    dialog = InfobaseDialog.for_new(
        groups=["/"],
        installations=INSTALLED,
        cfg_rules=[],
        choose_directory=lambda: r"D:\bases\Бухгалтерия",
    )
    qtbot.addWidget(dialog)
    dialog._browse_button.click()
    assert dialog.new_record().name == "Бухгалтерия"
    assert dialog.new_record().connect == r'File="D:\bases\Бухгалтерия";'


def test_browse_button_does_not_overwrite_typed_name(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(
        groups=["/"],
        installations=INSTALLED,
        cfg_rules=[],
        choose_directory=lambda: r"D:\bases\Бухгалтерия",
    )
    qtbot.addWidget(dialog)
    dialog.set_name("Своё имя")
    dialog._browse_button.click()
    assert dialog.new_record().name == "Своё имя"


def test_browse_button_does_nothing_when_cancelled(qtbot: Any) -> None:
    """Пустая строка от `choose_directory` — тот же контракт, что у `QFileDialog`

    (отмена выбора отдаёт пустую строку) — поле не трогается.
    """  # noqa: RUF002
    dialog = InfobaseDialog.for_new(
        groups=["/"], installations=INSTALLED, cfg_rules=[], choose_directory=lambda: ""
    )
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"D:\already")
    dialog._browse_button.click()
    assert dialog.new_record().connect == r'File="D:\already";'


# -- T-11, п. 6: автоимя из набранного пути и имени в кластере --------------


def test_typed_file_path_suggests_the_directory_name(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\bases\Зарплата")

    dialog._file_path.editingFinished.emit()

    assert dialog.name_text() == "Зарплата"


def test_typed_cluster_ref_suggests_the_name(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.SERVER)
    dialog.set_server("srv")
    dialog.set_ref("ACC_2026")

    dialog._ref.editingFinished.emit()

    assert dialog.name_text() == "ACC_2026"


def test_typed_name_survives_path_edit(qtbot: Any) -> None:
    """ЗАЩИТНЫЙ ТЕСТ: подстановка только в пустое имя — введённое не перезаписывается.

    Мутация: `_suggest_name` без проверки `not self._name.text().strip()`.
    """  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Своё имя")
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path(r"D:\bases\Зарплата")

    dialog._file_path.editingFinished.emit()

    assert dialog.name_text() == "Своё имя"


def test_drive_root_suggests_nothing(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.FILE)
    dialog.set_file_path("D:\\")

    dialog._file_path.editingFinished.emit()

    assert dialog.name_text() == ""


def test_editing_dialog_keeps_its_name_on_path_edit(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_file_path(r"E:\c\Другая")

    dialog._file_path.editingFinished.emit()

    assert dialog.name_text() == "Бухгалтерия"


def test_browse_button_has_russian_label(qtbot: Any) -> None:
    """Тот же урок, что и «Close» в задаче 8: подпись проверяется запуском."""
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog._browse_button.text() == "Обзор…"


# -- v2.2: логин, пароль и «Запомнить» в обоих диалогах (задача 5) ----------


def test_dialog_offers_login_password_and_remember_off_by_default(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.login_edit().text() == ""
    assert dialog.password_edit().echoMode() == QLineEdit.EchoMode.Password
    assert dialog.remember_checkbox().isChecked() is False
    assert "командной строке" in dialog.credentials_note().text()


def test_stored_password_is_not_shown_in_the_dialog(qtbot: Any) -> None:
    """Спека v2.2, §4: диалог знает только признак — сам пароль не возвращается."""
    dialog = InfobaseDialog(
        _item('File="D:\\b";', ()), groups=["/"], installations=INSTALLED,
        cfg_rules=[], login="tester", has_password=True,
    )
    qtbot.addWidget(dialog)
    assert dialog.login_edit().text() == "tester"
    assert dialog.password_edit().text() == ""
    assert "сохранён" in dialog.password_edit().placeholderText()
    assert dialog.remember_checkbox().isChecked() is True
    assert dialog.credentials_changed() is False


def test_password_without_login_blocks_ok_with_a_hint(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Демо")
    dialog.set_file_path(r"D:\Bases\Demo")
    assert dialog.accepts()

    dialog.password_edit().setText("p@ss")

    assert not dialog.accepts()
    assert "Пользователь" in dialog.required_hint()


def test_credentials_accessor_and_repr(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")
    dialog.remember_checkbox().setChecked(True)

    credentials = dialog.credentials()

    assert isinstance(credentials, DialogCredentials)
    # По полям, не через `==`: у пароля compare=False (иначе упавший assert  # noqa: RUF003
    # печатал бы его в дифе pytest), и равенство пароль не проверяет.  # noqa: RUF003
    assert credentials.login == "tester"
    assert credentials.password == "p@ss"
    assert credentials.remember is True
    assert "p@ss" not in repr(credentials)
    assert dialog.credentials_changed() is True


def test_clearing_login_with_stored_password_warns(qtbot: Any) -> None:
    dialog = InfobaseDialog(
        _item('File="D:\\b";', ()), groups=["/"], installations=INSTALLED,
        cfg_rules=[], login="tester", has_password=True,
    )
    qtbot.addWidget(dialog)
    dialog.login_edit().setText("")
    assert "будет удалён" in dialog.credentials_note().text()
    assert dialog.credentials_changed() is True


# -- финальный fix-раунд v2.2: недоступное хранилище и судьба пароля --------


def test_unavailable_store_shows_login_and_locks_credentials(qtbot: Any) -> None:
    """`has_password=None` — «хранилище недоступно», а не «пароля нет».

    Логин известен (он в `bases.json`) и обязан быть виден; всё, что ведёт
    к операции над хранилищем, заперто — иначе «ОК» на такой машине молча
    стирал бы сохранённый логин и уходил в ветку `delete` (I3).
    """  # noqa: RUF002
    dialog = InfobaseDialog(
        _item('Srvr="s";Ref="r";', ()), groups=["/"], installations=INSTALLED,
        cfg_rules=[], login="tester", has_password=None,
    )
    qtbot.addWidget(dialog)
    assert dialog.login_edit().text() == "tester"
    assert dialog.login_edit().isReadOnly()
    assert dialog.password_edit().isEnabled() is False
    assert dialog.remember_checkbox().isEnabled() is False
    assert dialog.credentials_note().text() == CREDENTIALS_UNAVAILABLE_NOTE
    assert dialog.credentials_changed() is False


def test_typing_a_password_turns_remember_on(qtbot: Any) -> None:
    """Спека §4 задаёт умолчание «выключено», но не судьбу введённого пароля:
    молча выбросить его нельзя. Ввод включает галочку, снять её можно назад."""  # noqa: RUF002
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.remember_checkbox().isChecked() is False

    dialog.password_edit().setText("p@ss")

    assert dialog.remember_checkbox().isChecked() is True


def test_unchecking_remember_with_a_typed_password_warns(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")

    dialog.remember_checkbox().setChecked(False)

    assert dialog.credentials_note().text() == PASSWORD_NOT_KEPT_NOTE


def test_unchecking_remember_with_a_stored_password_warns(qtbot: Any) -> None:
    dialog = InfobaseDialog(
        _item('Srvr="s";Ref="r";', ()), groups=["/"], installations=INSTALLED,
        cfg_rules=[], login="tester", has_password=True,
    )
    qtbot.addWidget(dialog)

    dialog.remember_checkbox().setChecked(False)

    assert dialog.credentials_note().text() == STORED_PASSWORD_REMOVAL_NOTE


# -- T-29: «Сервер» — выпадающий список серверов существующих записей ----------


def _choices(dialog: InfobaseDialog) -> list[str]:
    box = dialog._server_box
    return [box.itemText(i) for i in range(box.count())]


def test_server_field_offers_known_servers(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(
        groups=["/"], installations=INSTALLED, cfg_rules=[], servers=["srv-a", "srv-b"]
    )
    qtbot.addWidget(dialog)
    assert _choices(dialog) == ["srv-a", "srv-b"]
    assert dialog._server.text() == ""  # первый вариант не подставился сам


def test_server_field_keeps_record_value_absent_from_choices(qtbot: Any) -> None:
    item = _item('Srvr="own";Ref="r";', ())
    dialog = InfobaseDialog(
        item, groups=["/"], installations=INSTALLED, cfg_rules=[], servers=["srv-a"]
    )
    qtbot.addWidget(dialog)
    assert dialog._server.text() == "own"
    assert dialog.changes() == ({}, None)


def test_server_chosen_from_the_list_reaches_connect(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(
        groups=["/"], installations=INSTALLED, cfg_rules=[], servers=["srv-a", "srv-b"]
    )
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.SERVER)
    dialog._server_box.setCurrentIndex(1)
    dialog.set_ref("ACC")
    dialog.set_name("Учёт")
    assert dialog.new_record() == NewInfobase(
        name="Учёт", connect='Srvr="srv-b";Ref="ACC";', folder="/"
    )


def test_typed_server_wins_over_choices(qtbot: Any) -> None:
    dialog = InfobaseDialog.for_new(
        groups=["/"], installations=INSTALLED, cfg_rules=[], servers=["srv-a"]
    )
    qtbot.addWidget(dialog)
    dialog.set_kind(ConnectKind.SERVER)
    dialog.set_server("typed")
    dialog.set_ref("ACC")
    dialog.set_name("Учёт")
    assert dialog.new_record().connect == 'Srvr="typed";Ref="ACC";'


def test_unparsed_server_field_gets_no_choices(qtbot: Any) -> None:
    """Поле только для чтения (`Srvr` не разобран) — выбор из списка обошёл бы запрет."""
    item = _item('Ref="only";', ())
    dialog = InfobaseDialog(
        item, groups=["/"], installations=INSTALLED, cfg_rules=[], servers=["srv-a"]
    )
    qtbot.addWidget(dialog)
    assert _choices(dialog) == []


def test_server_field_has_no_inline_completion(qtbot: Any) -> None:
    """Дописанный хвост чужого варианта при подтверждении ушёл бы в строку соединения."""
    dialog = InfobaseDialog.for_new(
        groups=["/"], installations=INSTALLED, cfg_rules=[], servers=["srv-a"]
    )
    qtbot.addWidget(dialog)
    assert dialog._server_box.completer() is None


def _params_dialog(qtbot: Any, keys: tuple[tuple[str, str], ...], **kwargs: Any) -> InfobaseDialog:
    item = _item('File="D:\\b";', keys)
    dialog = InfobaseDialog(
        item, groups=["/"], installations=INSTALLED, cfg_rules=[],
        catalog=load_cli_catalog(), **kwargs,
    )
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.parametrize(
    ("keys", "typed", "expected"),
    [
        ((), "", {}),
        ((), "/Len", {"AdditionalParameters": "/Len"}),
        ((("AdditionalParameters", "/Lru"),), "/Lru", {}),
        ((("AdditionalParameters", "/Lru"),), "  /Lru /C x", {"AdditionalParameters": "  /Lru /C x"}),  # noqa: E501
        ((("AdditionalParameters", "/Lru"),), "", {"AdditionalParameters": None}),
        ((("AdditionalParameters", "/Lru"),), "   ", {"AdditionalParameters": None}),
    ],
)
def test_additional_parameters_written_only_when_changed(
    qtbot: Any, keys: tuple[tuple[str, str], ...], typed: str, expected: dict[str, str | None]
) -> None:
    """Мутационная проверка обязательна: нетронутая строка не пишется, текст — как набран."""
    dialog = _params_dialog(qtbot, keys)
    block = dialog.launch_params_block()
    assert block is not None
    block.set_enterprise_text(typed)
    assert dialog.changes() == (expected, None)


def test_additional_parameters_not_duplicated_in_other_keys(qtbot: Any) -> None:
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/Lru"), ("XTest", "1")))
    assert dialog.other_rows() == [("XTest", "1")]


def test_designer_params_are_reported_separately(qtbot: Any) -> None:
    dialog = _params_dialog(qtbot, (), designer_params="/DisableStartupMessages")
    block = dialog.launch_params_block()
    assert block is not None
    assert not dialog.designer_params_changed()
    block.set_designer_text("")
    assert dialog.designer_params_changed() and dialog.designer_params() is None
    assert dialog.changes() == ({}, None)


def test_expanded_callback_and_builder_are_wired(qtbot: Any) -> None:
    states: list[bool] = []
    dialog = _params_dialog(
        qtbot, (), params_expanded=False, on_params_expanded=states.append,
        open_builder=lambda mode, text: "/Len" if mode is Mode.ENTERPRISE else None,
    )
    block = dialog.launch_params_block()
    assert block is not None
    block.set_expanded(True)
    block.run_builder(Mode.ENTERPRISE)
    assert states == [True]
    assert dialog.changes() == ({"AdditionalParameters": "/Len"}, None)


def test_no_catalog_no_block(qtbot: Any) -> None:
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.launch_params_block() is None


def test_designer_params_never_go_into_v8i_changes(qtbot: Any) -> None:
    """Мутационная проверка: строка Конфигуратора живёт в bases.json, не в .v8i (§4.3)."""
    dialog = _params_dialog(qtbot, (), designer_params="/DisableStartupMessages")
    block = dialog.launch_params_block()
    assert block is not None
    block.set_designer_text("/TechnicalSpecialistMode")
    assert dialog.designer_params_changed()
    assert dialog.designer_params() == "/TechnicalSpecialistMode"
    assert dialog.changes() == ({}, None)


@pytest.mark.parametrize(
    ("typed", "note"),
    [
        ('/Len /Out "C:\\a b.txt', DESIGNER_QUOTE_NOTE),
        ('/P"zzz"', DESIGNER_SECRET_NOTE),
    ],
)
def test_designer_line_that_cannot_be_saved_locks_ok_before_the_click(
    qtbot: Any, typed: str, note: str
) -> None:
    """Приёмка 21.11.2026, Р2: «ОК» неактивна, строка остаётся в поле, пояснение рядом."""  # noqa: RUF002
    dialog = _params_dialog(qtbot, (), designer_params="/Len")
    block = dialog.launch_params_block()
    assert block is not None and dialog.accepts()

    block.set_designer_text(typed)

    assert not dialog.accepts()
    assert dialog.required_hint() == note
    assert "zzz" not in dialog.required_hint()
    assert block.designer_text() == typed

    block.set_designer_text("/Len /DisableStartupMessages")
    assert dialog.accepts() and dialog.required_hint() == ""


def test_untouched_designer_line_with_a_secret_does_not_lock_ok(qtbot: Any) -> None:
    """Финальное ревью плана А, T2: нетронутая строка «ОК» не запирает (спека §4.3)."""  # noqa: RUF002
    dialog = _params_dialog(qtbot, (), designer_params='/P"zzz"')
    assert dialog.launch_params_block() is not None
    assert dialog.accepts()
    assert dialog.required_hint() == ""
    assert not dialog.designer_params_changed()



def _press_ctrl_enter(dialog: QDialog) -> None:
    """Сочетание Ctrl+Enter: на offscreen `keyClick` не доходит до `QShortcut`,
    поэтому проверяем подключение обоих ключей и испускаем `activated`."""
    shortcuts = {s.key().toString(): s for s in dialog.findChildren(QShortcut)}
    assert {"Ctrl+Return", "Ctrl+Enter"} <= shortcuts.keys()
    shortcuts["Ctrl+Return"].activated.emit()


def test_ctrl_enter_accepts_the_properties_dialog(qtbot: Any) -> None:
    """П1."""
    item = _item('File="D:\\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    qtbot.waitExposed(dialog)
    _press_ctrl_enter(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_blocks_take_the_dialog_palette(qtbot: Any) -> None:
    """Аудит плана Б, 0.4: без палитры шеврон блока в светлой теме — `DARK.text` по `#fafafa`."""
    dialog = _params_dialog(
        qtbot, (), palette=LIGHT, repository=RepositorySettings(None, None, False)
    )
    for block in (dialog.launch_params_block(), dialog.repository_block()):
        assert block is not None
        assert block.chevron().toImage() == chevron_pixmap(False, LIGHT.text).toImage()


def test_expanding_a_block_with_findings_does_not_clip_the_notes(qtbot: Any) -> None:
    """В4 (приёмка 21.11.2026): подпись под «Запомнить пароль» обрезалась.

    Решение заказчика 21.11.2026: содержимое в `QScrollArea` — метки получают свою
    `heightForWidth`, нижняя полоса остаётся. Без прокрутки (офскрин 800 на 800, потолок
    `adjustSize` 533 px при sizeHint ~1100) тест красный.
    """  # noqa: RUF002
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/L en /Foo /Bar /Baz"),))
    dialog.show()
    qtbot.waitExposed(dialog)
    block = dialog.launch_params_block()
    assert block is not None
    block.set_expanded(True)
    labels = [dialog.credentials_note(), *block.findings_list(Mode.ENTERPRISE).labels()]
    assert len(labels) >= 3

    def fits() -> bool:
        return all(label.height() >= label.heightForWidth(label.width()) for label in labels)

    qtbot.waitUntil(fits, timeout=2000)


def test_form_labels_are_right_aligned_in_one_column(qtbot: Any) -> None:
    """Мокап `.form label` (колонка 170px, справа): три формы окна — одна колонка подписей."""
    dialog = _params_dialog(qtbot, (), repository=RepositorySettings(None, None, False))
    params, repository = dialog.launch_params_block(), dialog.repository_block()
    assert params is not None and repository is not None
    forms = [
        dialog._form,
        params.findChildren(QFormLayout)[0],
        repository.findChildren(QFormLayout)[0],
    ]
    for form in forms:
        assert form.labelAlignment() & Qt.AlignmentFlag.AlignRight
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is not None:
                label = item.widget()
                assert label is not None
                assert label.minimumWidth() == FORM_LABEL_WIDTH


def test_ok_is_the_primary_button_in_the_footer(qtbot: Any) -> None:
    """Мокап `.btn.pri` и `.foot` (стр. 123): жёлтая «ОК» в нижней полосе, подсказка — слева."""  # noqa: RUF002
    item = _item('File="D:\b";', ())
    dialog = InfobaseDialog(item, groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    footer = dialog.findChild(DialogFooter)
    assert footer is not None
    buttons = {button.text(): button for button in footer.findChildren(QPushButton)}
    assert buttons["ОК"].property("role") == "primary"  # noqa: RUF001
    assert buttons["Отмена"].property("role") is None
    # Пояснение — подсказка самой полосы (`.q` мокапа), а не вторая метка рядом.  # noqa: RUF003
    dialog.set_name("")
    assert dialog.required_hint() and footer.hint_text() == dialog.required_hint()
    assert not footer.hint_label().isHidden()
    assert footer.hint_label().objectName() == "Hint"


def _spy_fit(dialog: InfobaseDialog, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    original = dialog._fit_to_content

    def spy() -> None:
        calls.append(1)
        original()

    monkeypatch.setattr(dialog, "_fit_to_content", spy)
    return calls


class _ResizeCounter(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            self.count += 1
        return False


def test_block_toggle_and_content_change_fit_the_window_but_never_shrink_it(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """В4, механизм: раскрытие блока и смена содержимого — пересчёт, размер не отнимается.

    Мутационная проверка (задача 12, шаг 6): без подключений пересчёт не зовётся, без
    `max` окно, выбранное пользователем крупнее, сжимается. Финальное ревью плана Б, F1:
    шпион — на `_fit_to_content` (`adjustSize` он больше не зовёт).
    """  # noqa: RUF002
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/L en /Foo"),))
    dialog.resize(1100, 790)
    dialog.show()
    qtbot.waitExposed(dialog)
    calls = _spy_fit(dialog, monkeypatch)
    block = dialog.launch_params_block()
    assert block is not None
    size = dialog.size()
    block.set_expanded(True)
    assert len(calls) >= 1
    calls.clear()
    block.content_changed.emit()
    assert len(calls) == 1
    assert dialog.width() >= size.width() and dialog.height() >= size.height()


def test_refit_never_shrinks_an_enlarged_window_even_for_a_moment(qtbot: Any) -> None:
    """Финальное ревью плана Б, F1: пересчёт не сжимает окно до `sizeHint` и не растит обратно.

    Замер ревьюера: при окне 1000 на 700 прежний `adjustSize` + `resize(max(...))` давал два
    события Resize на каждый пересчёт — на живом Windows окно дрожало.
    """
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/L en /Foo"),))
    dialog.resize(1000, 700)
    dialog.show()
    qtbot.waitExposed(dialog)
    block = dialog.launch_params_block()
    assert block is not None
    size = dialog.size()
    counter = _ResizeCounter()
    dialog.installEventFilter(counter)
    block.content_changed.emit()
    dialog.removeEventFilter(counter)
    assert counter.count == 0
    assert dialog.size() == size


def test_typing_in_the_params_line_does_not_touch_the_window_size(qtbot: Any) -> None:
    """Финальное ревью плана Б, F1: ввод, не меняющий замечаний, размер не пересчитывает."""
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/Lru /Foo"),))
    dialog.resize(1000, 700)
    dialog.show()
    qtbot.waitExposed(dialog)
    block = dialog.launch_params_block()
    assert block is not None
    block.set_expanded(True)
    edit = block.findChildren(QLineEdit, "MonoEdit")[0]
    before = block.findings_text(Mode.ENTERPRISE)
    size = dialog.size()
    counter = _ResizeCounter()
    dialog.installEventFilter(counter)
    edit.setCursorPosition(len("/Lru"))
    qtbot.keyClicks(edit, "sxyz")
    dialog.removeEventFilter(counter)
    assert block.findings_text(Mode.ENTERPRISE) == before
    assert counter.count == 0
    assert dialog.size() == size


def test_findings_change_refits_the_window(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Финальное ревью плана Б, F1: смена набора замечаний — пересчёт есть."""
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/Lru"),))
    dialog.show()
    qtbot.waitExposed(dialog)
    block = dialog.launch_params_block()
    assert block is not None
    calls = _spy_fit(dialog, monkeypatch)
    block.set_enterprise_text("/Lru /Foo")
    assert calls


def test_typing_does_not_refit_the_window_unless_the_hint_changes(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Б (решение заказчика 21.11.2026): пересчёт размера — при смене подсказки «ОК».

    Мутация (задача 12, фикс-раунд): безусловный вызов в `_refresh_ok_state` — красный.
    """  # noqa: RUF002
    dialog = _params_dialog(qtbot, ())
    dialog.show()
    qtbot.waitExposed(dialog)
    calls = _spy_fit(dialog, monkeypatch)
    dialog.set_name("A")
    dialog.set_name("AB")
    assert dialog.required_hint() == ""
    assert calls == []
    dialog.set_name("")
    assert dialog.required_hint()
    assert len(calls) == 1


def _ceiling(dialog: InfobaseDialog) -> int:
    return dialog.screen().availableGeometry().height() * 2 // 3


def test_dialog_opens_no_smaller_than_its_content_below_the_ceiling(qtbot: Any) -> None:
    """Фикс-раунд 2: sizeHint `QScrollArea` не должен урезать окно (432 на 324 вместо содержимого).

    Мутация — голый `QScrollArea` вместо `_ContentScroll`: красный.
    """
    dialog = _params_dialog(qtbot, ())
    dialog.show()
    qtbot.waitExposed(dialog)
    content = dialog.findChild(QWidget, "PropertiesContent")
    assert content is not None
    hint = content.sizeHint()
    # Окно при показе ограничено 2/3 экрана и по ширине (офскрин 800 на 800).
    screen_width = dialog.screen().availableGeometry().width() * 2 // 3
    assert dialog.width() >= min(hint.width(), screen_width)
    assert dialog.height() >= min(hint.height(), _ceiling(dialog))


def test_expanding_a_block_really_grows_the_window_up_to_the_ceiling(qtbot: Any) -> None:
    """Фикс-раунд 2: раскрытие блока растит высоту окна (до 2/3 экрана)."""
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/L en /Foo /Bar /Baz"),))
    dialog.resize(780, 330)  # шире содержимого (702): горизонтальной полосы быть не должно
    dialog.show()
    qtbot.waitExposed(dialog)
    before = dialog.height()
    block = dialog.launch_params_block()
    assert block is not None
    block.set_expanded(True)
    assert dialog.height() > before
    assert dialog.height() >= _ceiling(dialog) - 2
    scroll = dialog.findChild(QScrollArea, "PropertiesScroll")
    assert scroll is not None
    # Содержимое выше потолка: вертикальная полоса есть, горизонтальной нет, метки целы.
    qtbot.waitUntil(scroll.verticalScrollBar().isVisible, timeout=2000)
    qtbot.waitUntil(lambda: not scroll.horizontalScrollBar().isVisible(), timeout=2000)
    labels = [dialog.credentials_note(), *block.findings_list(Mode.ENTERPRISE).labels()]
    qtbot.waitUntil(
        lambda: all(label.height() >= label.heightForWidth(label.width()) for label in labels),
        timeout=2000,
    )


def test_credentials_note_text_change_refits_the_window(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Фикс-раунд 2 (minor): смена текста подписи под «Запомнить пароль» — пересчёт размера."""
    dialog = _params_dialog(qtbot, ())
    dialog.show()
    qtbot.waitExposed(dialog)
    calls: list[int] = []
    monkeypatch.setattr(dialog, "_fit_to_content", lambda: calls.append(1))
    before = dialog.credentials_note().text()
    dialog.login_edit().setText("user")  # без логина менялась бы и подсказка «ОК»  # noqa: RUF003
    calls.clear()
    dialog.password_edit().setText("x")
    dialog.remember_checkbox().setChecked(False)
    assert dialog.credentials_note().text() != before
    assert calls


def test_long_repository_address_does_not_widen_the_form(qtbot: Any) -> None:
    """План В, Б4: адрес в сводке блока не растягивает содержимое окна свойств.

    Предпроверка 22.11.2026, п. 3: ширина 780 задаётся до показа — на офскрине `adjustSize`
    даёт 533 (2/3 от 800) при минимуме содержимого 626, полоса была бы и без адреса. П. 7:
    желаемая ширина окна с длинным адресом не больше, чем с коротким, — иначе при первом
    показе окно открывалось бы шириной до 2/3 экрана.
    """  # noqa: RUF002
    address = "tcp://repository-server.very-long-domain-name.example.local:1742/dept/project/main"
    short = _params_dialog(
        qtbot, (), repository=RepositorySettings("tcp://repo/buh", "dev", False)
    )
    dialog = _params_dialog(qtbot, (), repository=RepositorySettings(address, None, False))
    assert dialog.sizeHint().width() <= short.sizeHint().width()
    dialog.resize(780, 500)
    dialog.show()
    qtbot.waitExposed(dialog)
    content = dialog.findChild(QWidget, "PropertiesContent")
    assert content is not None
    assert content.minimumSizeHint().width() < 700
    scroll = dialog.findChild(QScrollArea, "PropertiesScroll")
    assert scroll is not None
    qtbot.waitUntil(lambda: not scroll.horizontalScrollBar().isVisible(), timeout=2000)


def test_dialog_opens_within_two_thirds_of_the_work_area(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """План В, Б6: `adjustSize` Qt ограничивал окно 2/3 экрана (1200 → 800), а не рабочей
    области (1152 → 768). Рабочая область подменена: 800 на 450, потолок — 533 на 300."""  # noqa: RUF002
    monkeypatch.setattr(
        InfobaseDialog, "_available_area", lambda self: QRect(0, 0, 800, 450)
    )
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/L en /Foo"),))
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog.height() <= 300
    assert dialog.width() <= 533


def test_size_set_before_show_is_not_capped(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Предпроверка плана В, п. 4: потолок — только у размера, выбранного `adjustSize` Qt.

    Размер, заданный до показа, остаётся: тесты роста окна задают его ради ширины без
    горизонтальной полосы. [проверено] 22.11.2026 пробой: `WA_Resized` в `showEvent` стоит
    после `resize()` и снят после `adjustSize`.
    """  # noqa: RUF002
    monkeypatch.setattr(
        InfobaseDialog, "_available_area", lambda self: QRect(0, 0, 800, 450)
    )
    dialog = _params_dialog(qtbot, (("AdditionalParameters", "/L en /Foo"),))
    dialog.resize(780, 400)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert (dialog.width(), dialog.height()) == (780, 400)


def test_other_keys_table_header_spans_the_width(qtbot: Any) -> None:
    """План В, Б10: шапка «Прочие ключи секции» — на всю ширину таблицы."""  # noqa: RUF002
    dialog = _params_dialog(qtbot, (("XTest", "1"),))
    table = dialog.findChild(QTableWidget)
    assert table is not None
    dialog.show()
    qtbot.waitExposed(dialog)
    header = table.horizontalHeader()
    last = header.count() - 1
    assert header.sectionPosition(last) + header.sectionSize(last) >= table.viewport().width() - 1
