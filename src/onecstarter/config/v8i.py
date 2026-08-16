"""Модель и разбор ibases.v8i: всё исходное сохраняется для round-trip.

Имена ключей сравниваются без учёта регистра. Регистр имён ключей в .v8i
экспериментально не проверялся — скилы проекта молчат, поэтому
регистронезависимое сравнение выбрано как безопасное: иначе ключ иного регистра
остался бы не найден, и мы дописали бы второй экземпляр одного ключа в файл.
При изменении значения написание ключа в файле сохраняется.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from onecstarter.config.encoding import TextFormat, decode, encode


class LineBreakRejectedError(ValueError):
    """Текст с переводом строки нельзя записать в файл построчного формата.

    Формат `.v8i` строчный: заголовок секции — `[<имя>]`, пара ключ-значение —
    `<ключ>=<значение>`, каждый на своей строке и без экранирования. Перевод
    строки внутри любой из этих частей превращает одну запись в несколько
    и подделывает секции в файле, который мы делим со штатным стартером.
    Записанное обязано читаться как записанное.
    """  # noqa: RUF002


def _reject_line_breaks(what: str, text: str) -> None:
    if "\r" in text or "\n" in text:
        raise LineBreakRejectedError(f"{what} не может содержать перевод строки")


@dataclass
class RawLine:
    text: str
    ending: str


@dataclass
class KeyValueLine:
    key: str
    value: str
    text: str
    ending: str


@dataclass
class V8iSection:
    header: RawLine
    lines: list[KeyValueLine | RawLine] = field(default_factory=list)
    default_ending: str = "\r\n"

    @property
    def name(self) -> str:
        return self.header.text.strip()[1:-1]

    def get(self, key: str) -> str | None:
        wanted = key.casefold()
        for line in self.lines:
            if isinstance(line, KeyValueLine) and line.key.casefold() == wanted:
                return line.value
        return None

    def set(self, key: str, value: str) -> None:
        _reject_line_breaks("Имя ключа", key)
        _reject_line_breaks("Значение ключа", value)
        wanted = key.casefold()
        for line in self.lines:
            if isinstance(line, KeyValueLine) and line.key.casefold() == wanted:
                line.value = value
                # Написание имени ключа в файле сохраняется: правка значения
                # не повод переименовывать чужой ключ.
                line.text = f"{line.key}={value}"
                return
        if self.lines:
            closed = _close_last_ending(self.lines, self.default_ending)
        else:
            closed = _close_last_ending([self.header], self.default_ending)
        new_ending = "" if closed else self.default_ending
        self.lines.append(KeyValueLine(key, value, f"{key}={value}", new_ending))

    def rename(self, name: str) -> None:
        """Переписать заголовок секции. Единственный способ сменить имя.

        Прямое присваивание `header.text` обходит проверку формата, а заголовок
        пишется одной строкой без экранирования: перевод строки в имени
        превратил бы одну секцию в несколько.
        """  # noqa: RUF002
        _reject_line_breaks("Имя секции", name)
        self.header.text = f"[{name}]"

    @property
    def connect(self) -> str | None:
        return self.get("Connect")

    @property
    def id(self) -> str | None:
        return self.get("ID")

    @property
    def version(self) -> str | None:
        return self.get("Version")

    @property
    def default_version(self) -> str | None:
        return self.get("DefaultVersion")

    @property
    def folder(self) -> str | None:
        return self.get("Folder")

    @property
    def is_group(self) -> bool:
        # [Ф] T-05.6: пустое значение Connect= платформа трактует так же,
        # как отсутствие ключа, — секция показывается и канонизируется
        # как группа.
        return not self.connect


@dataclass
class V8iDocument:
    prologue: list[RawLine]
    sections: list[V8iSection]
    fmt: TextFormat
    default_ending: str

    def find_by_id(self, section_id: str) -> V8iSection | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def append_section(self, name: str) -> V8iSection:
        _reject_line_breaks("Имя секции", name)
        if self.sections:
            last = self.sections[-1]
            if last.lines:
                _close_last_ending(last.lines, self.default_ending)
            else:
                _close_last_ending([last.header], self.default_ending)
        elif self.prologue:
            _close_last_ending(self.prologue, self.default_ending)
        section = V8iSection(
            header=RawLine(f"[{name}]", self.default_ending),
            default_ending=self.default_ending,
        )
        self.sections.append(section)
        return section

    def remove_section(self, section: V8iSection) -> None:
        for index, candidate in enumerate(self.sections):
            if candidate is section:
                del self.sections[index]
                return
        raise ValueError("Секция не входит в документ")


def _close_last_ending(lines: Sequence[KeyValueLine | RawLine], default_ending: str) -> bool:
    """Если хвост списка строк не завершён переводом строки — завершить его.

    Возвращает True, если конец был дозаписан: значит новая строка, которую
    допишет вызывающий код, получит ending == "" и станет последней строкой
    файла. Возвращает False, если дозаписывать было нечего (список пуст или
    последняя строка уже завершена) — тогда новая строка получит
    default_ending.
    """  # noqa: RUF002
    if not lines:
        return False
    last = lines[-1]
    if last.ending == "":
        last.ending = default_ending
        return True
    return False


def _split_ending(raw: str) -> tuple[str, str]:
    if raw.endswith("\r\n"):
        return raw[:-2], "\r\n"
    if raw.endswith("\n"):
        return raw[:-1], "\n"
    return raw, ""


def _is_header(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("[") and stripped.endswith("]") and len(stripped) >= 2


def _iter_raw_lines(text: str) -> list[str]:
    """Разбить текст на строки, признавая концом строки только "\\n"/"\\r\\n".

    В отличие от `str.splitlines`, не считает границей строки одиночный "\\r"
    и «экзотические» юникодные разделители (NEL \\x85, \\u2028, \\u2029, \\v,
    \\f, \\x1c-\\x1e) — они остаются частью текста строки, как и положено
    байтам, которые формат 1С не трактует как переводы строк.
    """  # noqa: RUF002
    lines: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char == "\n":
            lines.append(text[start : index + 1])
            start = index + 1
    if start < len(text):
        lines.append(text[start:])
    return lines


def parse_v8i(data: bytes) -> V8iDocument:
    text, fmt = decode(data)
    endings: Counter[str] = Counter()
    prologue: list[RawLine] = []
    sections: list[V8iSection] = []
    for raw in _iter_raw_lines(text):
        line_text, ending = _split_ending(raw)
        if ending:
            endings[ending] += 1
        if _is_header(line_text):
            sections.append(V8iSection(header=RawLine(line_text, ending)))
            continue
        if sections:
            if "=" in line_text:
                key, _, value = line_text.partition("=")
                sections[-1].lines.append(KeyValueLine(key, value, line_text, ending))
            else:
                sections[-1].lines.append(RawLine(line_text, ending))
        else:
            prologue.append(RawLine(line_text, ending))
    default_ending = endings.most_common(1)[0][0] if endings else "\r\n"
    for section in sections:
        section.default_ending = default_ending
    return V8iDocument(prologue, sections, fmt, default_ending)


def serialize_v8i(doc: V8iDocument) -> bytes:
    parts: list[str] = []
    for line in doc.prologue:
        parts.append(line.text + line.ending)
    for section in doc.sections:
        parts.append(section.header.text + section.header.ending)
        for body_line in section.lines:
            parts.append(body_line.text + body_line.ending)
    return encode("".join(parts), doc.fmt)
