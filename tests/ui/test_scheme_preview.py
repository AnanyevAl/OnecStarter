"""Предпросмотр схемы: фрагмент кода 1С в цветах схемы (спека v3.2, §5)."""  # noqa: RUF002

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    EDT_DEFAULTS,
    KEY_BY_NAME,
    Scheme,
    to_hex,
)
from onecstarter.ui.edt.scheme_preview import CURRENT_LINE, PREVIEW_SAMPLE, SchemePreview

DARK = Scheme(
    "d",
    {
        **EDT_DEFAULTS,
        "Background": (43, 43, 43),
        "Foreground": (169, 183, 198),
        "BSL_Keywords": (204, 120, 50),
        "Strings": (106, 135, 89),
        "lineNumberColor": (96, 99, 102),
        "currentLineColor": (50, 50, 50),
        "SelectionBackground": (33, 66, 131),
        "SelectionForeground": (255, 255, 255),
        "occurrenceIndicationColor": (52, 65, 52),
        "hyperlinkColor": (40, 123, 222),
    },
)


def _hex(name: str) -> str:
    return to_hex(DARK.colors[name]).lower()


def test_sample_uses_known_keys_covers_all_tokens_and_marks() -> None:
    keys = {key for line in PREVIEW_SAMPLE for _text, key, _mark in line if key}
    assert keys <= set(KEY_BY_NAME)
    tokens = {key.name for key in COLOR_KEYS if key.prefs_file == BSL_PREFS}
    assert tokens <= keys, tokens - keys
    marks = {mark for line in PREVIEW_SAMPLE for _text, _key, mark in line}
    assert {"selection", "occurrence", "hyperlink"} <= marks
    assert 0 <= CURRENT_LINE < len(PREVIEW_SAMPLE)


def test_render_colors_fragments_by_scheme(qtbot) -> None:  # type: ignore[no-untyped-def]
    preview = SchemePreview()
    qtbot.addWidget(preview)
    preview.show_scheme(DARK)
    fragments = preview.fragments()
    # Соседние отрезки с ОДИНАКОВЫМ форматом Qt склеивает в один фрагмент  # noqa: RUF003
    # только отрезки, чьи соседи отличаются цветом (номер строки, ключевое слово, …).
    assert ("Процедура", _hex("BSL_Keywords"), "") in fragments
    assert (" 1 ", _hex("lineNumberColor"), "") in fragments
    assert ("Строка.Сумма", _hex("SelectionForeground"), _hex("SelectionBackground")) in fragments
    assert ("\t\tИтого", _hex("Foreground"), _hex("occurrenceIndicationColor")) in fragments  # noqa: RUF001
    assert ("\tОбновитьСтатус", _hex("hyperlinkColor"), "") in fragments  # noqa: RUF001
    assert ('"Итого: "', _hex("Strings"), "") in fragments
    backgrounds = preview.line_backgrounds()
    assert len(backgrounds) == len(PREVIEW_SAMPLE)
    assert backgrounds[CURRENT_LINE] == _hex("currentLineColor")
    assert backgrounds[0] == ""
    assert _hex("Background") in preview.styleSheet()
    assert _hex("Foreground") in preview.styleSheet()
    assert preview.isReadOnly()


def test_rerender_replaces_document(qtbot) -> None:  # type: ignore[no-untyped-def]
    preview = SchemePreview()
    qtbot.addWidget(preview)
    preview.show_scheme(DARK)
    assert preview.document().blockCount() == len(PREVIEW_SAMPLE)
    preview.show_scheme(Scheme("l", EDT_DEFAULTS))
    assert preview.document().blockCount() == len(PREVIEW_SAMPLE)
    keyword = to_hex(EDT_DEFAULTS["BSL_Keywords"]).lower()
    assert ("Процедура", keyword, "") in preview.fragments()
    assert ("Процедура", _hex("BSL_Keywords"), "") not in preview.fragments()
