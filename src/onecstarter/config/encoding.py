"""Байты ↔ текст для файлов 1С: кодировка и BOM определяются по факту."""  # noqa: RUF002

import codecs
from dataclasses import dataclass

_BOMS: list[tuple[bytes, str]] = [
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
]


@dataclass(frozen=True)
class TextFormat:
    encoding: str
    bom: bytes


def _terminal(data: bytes) -> tuple[str, TextFormat]:
    return data.decode("latin-1"), TextFormat("latin-1", b"")


def decode(data: bytes) -> tuple[str, TextFormat]:
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data[len(bom):].decode(encoding), TextFormat(encoding, bom)
            except UnicodeDecodeError:
                return _terminal(data)
    for encoding in ("utf-8", "cp1251"):
        try:
            return data.decode(encoding), TextFormat(encoding, b"")
        except UnicodeDecodeError:
            continue
    return _terminal(data)


def encode(text: str, fmt: TextFormat) -> bytes:
    """Закодировать `text` обратно в `fmt.encoding` с исходным BOM.

    Может выбросить `UnicodeEncodeError`, если документ, прочитанный в
    устаревшей/фолбэк-кодировке (например, latin-1), был изменён символами,
    выходящими за её пределы; политика реакции (пересохранить как UTF-8)
    относится к слою services, не сюда.
    """  # noqa: RUF002
    return fmt.bom + text.encode(fmt.encoding)
