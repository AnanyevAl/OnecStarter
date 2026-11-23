"""Предпросмотр командной строки с раскраской (мокап v4, `.preview`: `.k`, `.unk`, `.base`).

`command_spans` — чистая функция без Qt: строка → спаны. Окна передают строку уже
замаскированной (`redact_arguments`, `preview_arguments` с `***`): раскраска значения не
раскрывает и маскирование не обходит (инвариант 5).
"""  # noqa: RUF002

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from onecstarter.domain.cli_catalog import Catalog
from onecstarter.ui.theme import DARK, Palette

# Пробелы — отдельные слова; кавычки 1С (удвоенная — в значении) пробел не рвут,  # noqa: RUF003
# незакрытая кавычка тянется до конца строки.
_WORD = re.compile(r'[ \t]+|(?:[^ \t"]|"[^"]*(?:"|$))+')


class SpanKind(Enum):
    BASE = "base"
    KEY = "key"
    UNKNOWN = "unknown"
    TEXT = "text"


@dataclass(frozen=True)
class Span:
    kind: SpanKind
    text: str


def command_spans(
    line: str, *, base_length: int = 0, is_known: Callable[[str], bool]
) -> tuple[Span, ...]:
    """Спаны раскраски: начальные `base_length` символов — `BASE`, слова с «/» — ключи."""  # noqa: RUF002
    spans: list[Span] = []
    if base_length > 0:
        spans.append(Span(SpanKind.BASE, line[:base_length]))
    for word in _WORD.findall(line[base_length:]):
        if word.startswith("/"):
            kind = SpanKind.KEY if is_known(word) else SpanKind.UNKNOWN
        else:
            kind = SpanKind.TEXT
        if kind is SpanKind.TEXT and spans and spans[-1].kind is SpanKind.TEXT:
            spans[-1] = Span(SpanKind.TEXT, spans[-1].text + word)
        else:
            spans.append(Span(kind, word))
    return tuple(spans)


def catalog_word_known(catalog: Catalog) -> Callable[[str], bool]:
    """Слово с «/» знакомо каталогу: ключ (`Catalog.match`, в том числе с прижатым по его
    правилам значением) или команда.

    Ключ с прижатым **в кавычках** значением (`/C"x"`, `Catalog.glued_key`) — незнакомый:
    решение заказчика 4 (21.11.2026) красит его `unknown` в «Выбранных ключах», и предпросмотр
    обязан красить так же (предпроверка плана Б, 1.2; спека §7.2).
    """  # noqa: RUF002

    def known(word: str) -> bool:
        return catalog.match(word) is not None or catalog.command(word) is not None

    return known


def base_length_through(line: str, word: str) -> int:
    """Длина начала строки до конца первого слова, начинающегося с `word` (`0` — нет такого).

    Для `.base` мокапа: начало строки шага (`1cv8.exe DESIGNER /IBName"…"`) собирает домен
    (`build_step_arguments`), отдельной функции или константы для него там нет, а домен план
    не меняет. Граница ищется тем же разбором слов, что у `command_spans`, — кавычки 1С имени
    базы её не сдвигают, и формат строки в UI не повторяется.
    """  # noqa: RUF002
    for match in _WORD.finditer(line):
        if match.group().startswith(word):
            return match.end()
    return 0


class CommandLineView(QPlainTextEdit):
    """Только чтение, objectName `CodePreview` (моно и фон `code` — тема)."""

    def __init__(self, palette: Palette = DARK, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CodePreview")
        self.setReadOnly(True)
        self._palette = palette
        self._spans: tuple[Span, ...] = ()

    def show_line(
        self,
        line: str,
        *,
        base_length: int = 0,
        is_known: Callable[[str], bool] = lambda _word: False,
    ) -> None:
        self._spans = command_spans(line, base_length=base_length, is_known=is_known)
        self._render()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._render()

    def spans(self) -> tuple[Span, ...]:
        return self._spans

    def format_at(self, position: int) -> QTextCharFormat:
        cursor = QTextCursor(self.document())
        cursor.setPosition(position + 1)  # формат символа слева от курсора
        return cursor.charFormat()

    def _render(self) -> None:
        self.clear()
        cursor = QTextCursor(self.document())
        for span in self._spans:
            cursor.insertText(span.text, self._format(span.kind))

    def _format(self, kind: SpanKind) -> QTextCharFormat:
        palette = self._palette
        fmt = QTextCharFormat()
        if kind is SpanKind.BASE:
            fmt.setForeground(QColor(palette.text_dim))
        elif kind is SpanKind.KEY:
            fmt.setForeground(QColor(palette.accent))
            fmt.setFontWeight(QFont.Weight.DemiBold.value)
        elif kind is SpanKind.UNKNOWN:
            fmt.setForeground(QColor(palette.unknown))
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DotLine)
        else:
            fmt.setForeground(QColor(palette.text))
        return fmt
