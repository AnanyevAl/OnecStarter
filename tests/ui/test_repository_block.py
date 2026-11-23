"""Блок «Хранилище конфигурации» диалога свойств базы (спека v4, §7.1)."""

from typing import Any

from onecstarter.services.workspace import RepositorySettings
from onecstarter.ui.dialogs.repository import (
    DialogRepository,
    RepositoryBlock,
    repository_title,
)


def test_title_shows_address_and_user_or_none() -> None:
    title = repository_title("tcp://repo/buh", "dev")
    assert title == "Хранилище конфигурации — tcp://repo/buh · dev"
    assert repository_title(None, "dev") == "Хранилище конфигурации — dev"
    assert repository_title("tcp://repo/buh", None) == "Хранилище конфигурации — tcp://repo/buh"
    assert repository_title(None, None) == "Хранилище конфигурации — нет"
    assert repository_title("  ", "") == "Хранилище конфигурации — нет"


def test_block_shows_stored_settings_and_never_the_password(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", True))
    qtbot.addWidget(block)
    assert block.title() == "Хранилище конфигурации — tcp://repo/buh · dev"
    assert not block.is_expanded()
    assert block.address_edit().text() == "tcp://repo/buh"
    assert block.user_edit().text() == "dev"
    assert block.password_edit().text() == ""
    assert block.password_edit().placeholderText() == "сохранён"
    assert block.remember_checkbox().isChecked()
    assert not block.changed()


def test_untouched_block_reports_no_change_and_typed_values_are_normalized(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings(None, None, False), expanded=True)
    qtbot.addWidget(block)
    assert block.is_expanded() and not block.changed()

    block.address_edit().setText("  tcp://repo/zup ")
    block.user_edit().setText(" dev2 ")
    block.password_edit().setText("pw")

    assert block.changed()
    assert block.title() == "Хранилище конфигурации — tcp://repo/zup · dev2"
    assert block.remember_checkbox().isChecked()  # ввод пароля ставит «запомнить»
    values = block.values()
    assert values == DialogRepository("tcp://repo/zup", "dev2", remember=True)
    assert values.password == "pw" and "pw" not in repr(values)


def test_empty_password_field_means_keep_the_stored_one(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("a", "u", True))
    qtbot.addWidget(block)
    block.address_edit().setText("b")
    assert block.changed() and block.values().password is None
    block.address_edit().setText("a")
    assert not block.changed()
    block.remember_checkbox().setChecked(False)
    assert block.changed() and block.values().remember is False


def test_unavailable_store_locks_the_secret_fields_only(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("a", "u", None))
    qtbot.addWidget(block)
    assert not block.password_edit().isEnabled() and not block.remember_checkbox().isEnabled()
    assert block.address_edit().isEnabled() and block.user_edit().isEnabled()
    # Пароль прочитать нельзя — флажок не должен читаться как «удалить сохранённый».
    assert block.values().remember is True and not block.changed()


def test_clearing_the_user_warns_that_the_saved_password_goes(qtbot: Any) -> None:
    """Приёмка 21.11.2026, Р3: удаление пароля видно до «ОК», а не молча."""  # noqa: RUF002
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", True), expanded=True)
    qtbot.addWidget(block)
    block.show()
    assert not block.drop_note_visible()

    block.user_edit().setText("  ")

    assert block.drop_note_visible()
    assert not block.remember_checkbox().isChecked()
    assert block.values().remember is False

    block.user_edit().setText("dev")

    assert not block.drop_note_visible()
    assert block.remember_checkbox().isChecked()


def test_no_saved_password_no_drop_note(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", False), expanded=True)
    qtbot.addWidget(block)
    block.show()
    block.user_edit().setText("")
    assert not block.drop_note_visible()


def test_editing_the_user_keeps_a_deliberately_unchecked_remember(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", True), expanded=True)
    qtbot.addWidget(block)
    block.show()
    block.remember_checkbox().setChecked(False)

    block.user_edit().setText("dev2")

    assert not block.remember_checkbox().isChecked()
    assert not block.drop_note_visible()


def test_restoring_the_user_restores_the_pre_clear_remember(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", True), expanded=True)
    qtbot.addWidget(block)
    block.show()
    block.remember_checkbox().setChecked(False)

    block.user_edit().setText("")
    assert block.drop_note_visible()
    block.user_edit().setText("dev")

    assert not block.drop_note_visible()
    assert not block.remember_checkbox().isChecked()


def test_password_typed_while_user_is_empty_is_remembered_after_user_returns(
    qtbot: Any,
) -> None:
    """Финальное ревью плана А, M2: новый пароль, набранный при пустом пользователе,
    не теряется молча, даже если до очистки «запомнить» было снято."""  # noqa: RUF002
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", True), expanded=True)
    qtbot.addWidget(block)
    block.show()
    block.remember_checkbox().setChecked(False)

    block.user_edit().setText("")
    block.password_edit().setText("new-secret")
    block.user_edit().setText("dev")

    assert block.remember_checkbox().isChecked()
    values = block.values()
    assert values.user == "dev" and values.password == "new-secret" and values.remember


def test_locked_block_cleared_user_no_note_remember_kept(qtbot: Any) -> None:
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", None), expanded=True)
    qtbot.addWidget(block)
    block.show()
    block.user_edit().setText("")
    assert not block.drop_note_visible()
    assert block.values().remember is True


def test_remember_sits_in_the_password_row(qtbot: Any) -> None:
    """Мокап, экран 1 (стр. 144): «☑ запомнить» серым справа от пароля."""
    block = RepositoryBlock(RepositorySettings("tcp://repo/buh", "dev", True))
    qtbot.addWidget(block)
    assert block.remember_checkbox().parentWidget() is block.password_edit().parentWidget()
    assert block.remember_checkbox().objectName() == "InlineCheck"
    summary = block.summary_label()
    assert summary is not None and summary.full_text() == "— tcp://repo/buh · dev"
    assert block.rule_above() is not None
