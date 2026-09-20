"""Предпросмотр цветовой схемы редактора EDT (спека v3.2, §5).

Фрагмент кода 1С размечен вручную: `PREVIEW_SAMPLE` — строки из отрезков
(текст, ключ схемы, пометка). Ключ `""` — обычный текст (`Foreground`); пометки:
`selection` — фрагмент под выделением, `occurrence` — вхождения идентификатора,
`hyperlink` — имя вызываемой процедуры. Номера строк — первый отрезок каждой строки
цветом `lineNumberColor`; строка `CURRENT_LINE` подсвечена `currentLineColor`.
Виджет красится цветами схемы, не темы OneCStarter (§5) — стиль по objectName.
Текст образца — свой, не из обработки заказчика (§10).
"""  # noqa: RUF002

from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QTextEdit, QWidget

from onecstarter.domain.edt_scheme import RGB, Scheme, to_hex

Run = tuple[str, str, str]

PREVIEW_SAMPLE: tuple[tuple[Run, ...], ...] = (
    (("&НаКлиенте", "BSL_Pragmas", ""),),
    (
        ("Процедура", "BSL_Keywords", ""),
        (" ПересчитатьИтоги", "", ""),
        ("(", "Brackets", ""),
        ("Документ", "Others", ""),
        (", ", "Operators", ""),
        ("Показывать", "", ""),
        (" = ", "Operators", ""),
        ("Ложь", "BSL_Keywords", ""),
        (")", "Brackets", ""),
        (" Экспорт", "BSL_Keywords", ""),
    ),
    (("\t// Сумма по строкам с учётом скидки", "Comment", ""),),  # noqa: RUF001
    (("\tИтого", "", ""), (" = ", "Operators", ""), ("0", "Numbers", ""), (";", "Operators", "")),  # noqa: RUF001
    (
        ("\tДля Каждого", "BSL_Keywords", ""),
        (" Строка ", "", ""),
        ("Из", "BSL_Keywords", ""),
        (" Документ.Товары ", "", ""),
        ("Цикл", "BSL_Keywords", ""),
    ),
    (
        ("\t\tИтого", "", "occurrence"),  # noqa: RUF001
        (" = ", "Operators", ""),
        ("Итого", "", "occurrence"),
        (" + ", "Operators", ""),
        ("Строка.Сумма", "", "selection"),
        (" * ", "Operators", ""),
        ("(", "Brackets", ""),
        ("1", "Numbers", ""),
        (" - ", "Operators", ""),
        ("Строка.Скидка", "", ""),
        (" / ", "Operators", ""),
        ("100", "Numbers", ""),
        (")", "Brackets", ""),
        (";", "Operators", ""),
    ),
    (("\tКонецЦикла", "BSL_Keywords", ""), (";", "Operators", "")),  # noqa: RUF001
    (("\t#Если Клиент Тогда", "Preprocessor", ""),),
    (
        ("\t\tСообщить", "Builtinfunction", ""),  # noqa: RUF001
        ("(", "Brackets", ""),
        ('"Итого: "', "Strings", ""),
        (" + ", "Operators", ""),
        ("Формат", "Builtinfunction", ""),
        ("(", "Brackets", ""),
        ("Итого", "", ""),
        (", ", "Operators", ""),
        ('"ЧДЦ=2"', "Strings", ""),
        ("))", "Brackets", ""),
        (";", "Operators", ""),
    ),
    (("\t#КонецЕсли", "Preprocessor", ""),),
    (
        ("\tЕсли", "BSL_Keywords", ""),  # noqa: RUF001
        (" Показывать ", "", ""),
        ("И", "BSL_Keywords", ""),
        (" Итого ", "", ""),
        ("> ", "Operators", ""),
        ("1000", "Numbers", ""),
        (" Тогда", "BSL_Keywords", ""),
    ),
    (("\t\tПерейти", "BSL_Keywords", ""), (" ~Проверка", "Label", ""), (";", "Operators", "")),  # noqa: RUF001
    (("\tКонецЕсли", "BSL_Keywords", ""), (";", "Operators", "")),  # noqa: RUF001
    (("\t~Проверка:", "Label", ""),),
    (
        ("\tОбновитьСтатус", "", "hyperlink"),  # noqa: RUF001
        ("(", "Brackets", ""),
        ("Документ", "", ""),
        (")", "Brackets", ""),
        (";", "Operators", ""),
    ),
    (("КонецПроцедуры", "BSL_Keywords", ""),),
)
CURRENT_LINE = 8  # строка с «Сообщить(…)» — подсветка «текущая строка»  # noqa: RUF003


def _qcolor(rgb: RGB) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2])


def _format(foreground: RGB) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(_qcolor(foreground))
    return fmt


def _run_format(colors: dict[str, RGB], key: str, mark: str) -> QTextCharFormat:
    fmt = _format(colors[key or "Foreground"])
    if mark == "selection":
        fmt.setForeground(_qcolor(colors["SelectionForeground"]))
        fmt.setBackground(_qcolor(colors["SelectionBackground"]))
    elif mark == "occurrence":
        fmt.setBackground(_qcolor(colors["occurrenceIndicationColor"]))
    elif mark == "hyperlink":
        fmt.setForeground(_qcolor(colors["hyperlinkColor"]))
        fmt.setFontUnderline(True)
    return fmt


class SchemePreview(QTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SchemePreview")
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

    def show_scheme(self, scheme: Scheme) -> None:
        """Перерисовать образец цветами `scheme` (не `render`: то — `QWidget.render`)."""
        colors = scheme.colors
        background = to_hex(colors["Background"]).lower()
        foreground = to_hex(colors["Foreground"]).lower()
        self.setStyleSheet(
            f"QTextEdit#SchemePreview {{ background-color: {background}; color: {foreground}; }}"
        )
        self.clear()
        cursor = QTextCursor(self.document())
        for index, runs in enumerate(PREVIEW_SAMPLE):
            block = QTextBlockFormat()
            if index == CURRENT_LINE:
                block.setBackground(_qcolor(colors["currentLineColor"]))
            if index == 0:
                cursor.setBlockFormat(block)
            else:
                cursor.insertBlock(block)
            cursor.insertText(f"{index + 1:>2} ", _format(colors["lineNumberColor"]))
            for text, key, mark in runs:
                cursor.insertText(text, _run_format(colors, key, mark))

    # --- доступ для тестов ---

    def fragments(self) -> list[tuple[str, str, str]]:
        """(текст, цвет текста, фон) каждого фрагмента документа; фон `""`, если не задан."""
        result: list[tuple[str, str, str]] = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fmt = fragment.charFormat()
                background = (
                    fmt.background().color().name()
                    if fmt.hasProperty(QTextCharFormat.Property.BackgroundBrush)
                    else ""
                )
                result.append((fragment.text(), fmt.foreground().color().name(), background))
                iterator += 1
            block = block.next()
        return result

    def line_backgrounds(self) -> list[str]:
        result: list[str] = []
        block = self.document().begin()
        while block.isValid():
            fmt = block.blockFormat()
            result.append(
                fmt.background().color().name()
                if fmt.hasProperty(QTextCharFormat.Property.BackgroundBrush)
                else ""
            )
            block = block.next()
        return result
