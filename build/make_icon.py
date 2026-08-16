"""Генерация build/onecstarter.ico из фирменного значка приложения.

Без логотипа 1С (граница бренда, требования §4). ICO собирается вручную
из PNG-кадров: формат с PNG внутри поддерживается с Windows Vista,
Pillow ради одного файла не нужен. Само рисование значка сюда больше
не встроено — общий источник для заголовка окна, панели задач и трея
живёт в `onecstarter.ui.app_icon` (замечание заказчика 16.08.2026:
у приложения были три РАЗНЫХ значка, теперь один источник глифа).

Запуск: uv run python build/make_icon.py  (перерисовать и закоммитить).
"""  # noqa: RUF002

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer
from PySide6.QtGui import QGuiApplication, QImage

from onecstarter.ui.app_icon import draw_app_icon

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).parent / "onecstarter.ico"


def _png_bytes(image: QImage) -> bytes:
    """QImage → PNG-байты одного кадра `.ico`."""
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    # Стаб PySide6 6.11.1 объявляет format: bytes | bytearray | memoryview | None,
    # но рантайм это не принимает — ValueError на b"PNG"/bytearray(b"PNG")/QByteArray
    # (проверено вручную), рабочее значение только str. Расхождение стаба
    # с рантаймом, а не опечатка — mypy глушим прицельно на этой строке.  # noqa: RUF003
    image.save(buffer, "PNG")  # type: ignore[call-overload]
    return bytes(buffer.data().data())  # QBuffer.data() -> QByteArray, .data() -> bytes


def pack_ico(frames: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = b""
    body = b""
    offset = 6 + 16 * len(frames)
    for size, png in frames:
        entries += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset
        )
        offset += len(png)
        body += png
    return header + entries + body


def main() -> int:
    QGuiApplication(sys.argv)  # offscreen выставляет вызывающий
    OUTPUT.write_bytes(
        pack_ico([(size, _png_bytes(draw_app_icon(size))) for size in SIZES])
    )
    print(f"записан {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
