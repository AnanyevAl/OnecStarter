"""Блок «Параметры запуска» свойств базы (спека v4, §7.1; экран 1 мокапа)."""

from typing import Any

import pytest
from PySide6.QtWidgets import QLabel, QLineEdit

from onecstarter.domain.cli_catalog import Catalog, Mode, load_catalog
from onecstarter.domain.cli_params import Finding, Level, parse
from onecstarter.ui.dialogs.launch_params import (
    LaunchParamsBlock,
    block_title,
    counts_text,
    plural,
    preview_command,
)


def _catalog() -> Catalog:
    def key(name: str, **extra: object) -> dict[str, object]:
        entry: dict[str, object] = {
            "name": name, "group": "g", "modes": ["enterprise", "designer"], "summary": "к",
            "description": "о", "its": "7.3", "reliability": "doc",  # noqa: RUF001
        }
        entry.update(extra)
        return entry

    return load_catalog(
        {
            "group": [{"id": "g", "title": "Г", "order": 1}],
            "key": [
                key("/L", from_v8i=False, args=[{"kind": "string", "attached": True}]),
                key("/DisableStartupMessages"),
                key("/TechnicalSpecialistMode", modes=["enterprise"]),
                key("/WSP", args=[{"kind": "secret", "required": True}]),
            ],
        }
    )


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 ключей"), (1, "1 ключ"), (2, "2 ключа"), (4, "4 ключа"), (5, "5 ключей"),
     (11, "11 ключей"), (21, "21 ключ"), (22, "22 ключа"), (112, "112 ключей")],
)
def test_plural(count: int, expected: str) -> None:
    assert plural(count, "ключ", "ключа", "ключей") == expected


def test_block_title_variants() -> None:
    catalog = _catalog()
    empty = parse("", catalog)
    assert block_title(empty, None) == "Параметры запуска — нет"
    assert block_title(empty, empty) == "Параметры запуска — нет"
    four = parse("/Lru /DisableStartupMessages /Foo /TechnicalSpecialistMode", catalog)
    one = parse("/TechnicalSpecialistMode", catalog)
    assert block_title(four, one) == "Параметры запуска — 4 ключа · Конфигуратор: 1 ключ"
    assert block_title(empty, one) == "Параметры запуска — Конфигуратор: 1 ключ"
    assert block_title(four, empty) == "Параметры запуска — 4 ключа"


def test_counts_text() -> None:
    findings = (
        Finding(Level.ERROR, "/Foo", "x"),
        Finding(Level.WARNING, "/L", "y"),
        Finding(Level.WARNING, "/Z", "z"),
        Finding(Level.INFO, None, "i"),
    )
    assert counts_text(findings) == "1 ошибка · 2 предупреждения"
    assert counts_text(()) == ""


def test_preview_command_masks_secrets() -> None:
    line = preview_command('База "А"', Mode.ENTERPRISE, None, '/WSN u /WSP "секрет"')  # noqa: RUF001
    assert line == '1cv8c.exe ENTERPRISE /IBName"База ""А""" /WSN u /WSP ***'  # noqa: RUF001
    assert preview_command("Б", Mode.DESIGNER, None, "") == '1cv8.exe DESIGNER /IBName"Б"'


def _block(qtbot: Any, **kwargs: Any) -> LaunchParamsBlock:
    defaults: dict[str, Any] = {
        "enterprise": "", "designer": "", "show_designer": True, "client": None,
        "version": None, "open_builder": lambda _mode, _text: None,
    }
    defaults.update(kwargs)
    block = LaunchParamsBlock(_catalog(), **defaults)
    qtbot.addWidget(block)
    return block


def test_block_shows_counts_title_and_findings(qtbot: Any) -> None:
    block = _block(qtbot, enterprise="/Lru /Foo", designer="/TechnicalSpecialistMode")
    assert block.title() == "Параметры запуска — 2 ключа · Конфигуратор: 1 ключ"
    assert block.counts_label_text() == "1 ошибка · 2 предупреждения"
    assert "/Foo — неизвестный ключ. Строка сохранится как есть." in block.findings_text(
        Mode.ENTERPRISE
    )
    assert "из списка баз платформа не применяет" in block.findings_text(Mode.ENTERPRISE)
    assert "не для режима «Конфигуратор»" in block.findings_text(Mode.DESIGNER)


def test_block_updates_on_edit(qtbot: Any) -> None:
    block = _block(qtbot)
    block.set_enterprise_text("/DisableStartupMessages")
    assert block.title() == "Параметры запуска — 1 ключ"
    assert block.counts_label_text() == ""


def test_builder_result_replaces_line_and_cancel_keeps_it(qtbot: Any) -> None:
    calls: list[tuple[Mode, str]] = []

    def builder(mode: Mode, text: str) -> str | None:
        calls.append((mode, text))
        return "/Len" if mode is Mode.ENTERPRISE else None

    block = _block(qtbot, enterprise="/Lru", designer="/DisableStartupMessages",
                   open_builder=builder)
    block.run_builder(Mode.ENTERPRISE)
    block.run_builder(Mode.DESIGNER)
    assert calls == [(Mode.ENTERPRISE, "/Lru"), (Mode.DESIGNER, "/DisableStartupMessages")]
    assert block.enterprise_text() == "/Len"
    assert block.designer_text() == "/DisableStartupMessages"


def test_designer_row_hidden_for_web(qtbot: Any) -> None:
    block = _block(qtbot, designer="/TechnicalSpecialistMode", show_designer=False)
    assert not block.designer_visible()
    assert block.title() == "Параметры запуска — нет"


def test_expanded_state_is_applied(qtbot: Any) -> None:
    assert _block(qtbot, expanded=True).is_expanded()
    assert not _block(qtbot).is_expanded()


def test_counts_are_chips_on_the_header_line(qtbot: Any) -> None:
    """Мокап, экран 1 (стр. 119): «пилюли» справа в строке заголовка; спека §7.1 — план Б."""
    block = _block(qtbot, enterprise="/Lru /Foo", designer="/TechnicalSpecialistMode")
    assert block.chip_states() == [("error", "1 ошибка"), ("warning", "2 предупреждения")]
    assert all(chip.parentWidget() is block.header_row() for chip in block.chips())
    assert block.button().text() == "Параметры запуска"
    summary = block.summary_label()
    assert summary is not None and summary.full_text() == "— 2 ключа · Конфигуратор: 1 ключ"
    block.set_designer_text("")
    block.set_enterprise_text("/DisableStartupMessages")
    assert block.chip_states() == []


def test_findings_are_callouts_by_level(qtbot: Any) -> None:
    """В5 и решение заказчика 2: ошибка и предупреждение различимы."""  # noqa: RUF002
    block = _block(qtbot, enterprise="/Lru /Foo")
    callouts = block.findings_list(Mode.ENTERPRISE)
    assert sorted(callouts.levels()) == ["error", "warning"]
    assert all(label.objectName() == "Callout" for label in callouts.labels())


def test_parameter_rows_are_accent_labels_and_mono_fields(qtbot: Any) -> None:
    """Мокап `.form .acc` и `.inp.mono` (стр. 41, 32); линия над блоком (стр. 42)."""
    block = _block(qtbot)
    names = [label.text() for label in block.findChildren(QLabel, "AccentLabel")]
    assert names == ["1С:Предприятие", "Конфигуратор"]  # noqa: RUF001
    assert len(block.findChildren(QLineEdit, "MonoEdit")) == 2
    assert block.rule_above() is not None


def test_content_changed_only_when_notes_or_chips_change(qtbot: Any) -> None:
    """Финальное ревью плана Б, F1: сигнал пересчёта окна — не на каждый ввод.

    Решение заказчика 21.11.2026: размер окна свойств пересчитывается при смене структуры
    (набора выносок, чипов), а не на каждое нажатие клавиши в строке параметров.
    """  # noqa: RUF002
    block = _block(qtbot, enterprise="/Lru /Foo")
    edit = block.findChildren(QLineEdit, "MonoEdit")[0]
    emitted: list[int] = []
    block.content_changed.connect(lambda: emitted.append(1))
    before = (block.findings_text(Mode.ENTERPRISE), block.chip_states())
    edit.setCursorPosition(len("/Lru"))
    qtbot.keyClicks(edit, "sx")
    assert edit.text() == "/Lrusx /Foo"
    assert (block.findings_text(Mode.ENTERPRISE), block.chip_states()) == before
    assert emitted == []
    block.set_enterprise_text("/Lrusx")
    assert block.chip_states() == [("warning", "1 предупреждение")]
    assert emitted == [1]
