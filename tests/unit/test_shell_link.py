"""Проверки записи ярлыка Windows и разбор эталона, снятого с машины заказчика.

Эталон `tests/fixtures/reference.lnk` создан самой Windows (COM-объект
`WScript.Shell.CreateShortcut`, то есть штатная реализация `IShellLink`).
Он используется двояко:

1. Как источник фактических значений полей — заголовок, флаги, кодировка
   строк. Эти значения закреплены в `test_reference_*` и служат
   исполняемой спецификацией шага 1 задачи 17.
2. Как сторож обезличивания: сырой `.lnk` несёт идентификаторы машины,
   и `test_reference_fixture_carries_no_machine_identity` падает, если
   фикстуру пересняли с живой машины и забыли обезличить.

Побайтового сравнения «наш файл против эталона» здесь нет намеренно: наш
файл законно отличается — мы не пишем ни `TrackerDataBlock` (имя машины),
ни `PropertyStoreDataBlock` (SID пользователя), ни `LinkInfo` (серийный
номер тома). Сравнивается то, что обязано совпадать: постоянный заголовок
и смысл флагов.
"""  # noqa: RUF002

import json
import os
import struct
import subprocess
import sys
import uuid
from pathlib import Path
from typing import NamedTuple

import pytest

from onecstarter.__main__ import parse_ib_name
from onecstarter.config.shell_link import (
    LinkNameRejectedError,
    LinkTargetRejectedError,
    build_shell_link,
    quote_argument,
    safe_file_name,
    shortcut_command,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
REFERENCE = FIXTURES / "reference.lnk"

TRACKER_SIGNATURE = 0xA0000003
PROPERTY_STORE_SIGNATURE = 0xA0000009

HAS_ID_LIST = 0x01
HAS_LINK_INFO = 0x02
HAS_NAME = 0x04
HAS_RELATIVE_PATH = 0x08
HAS_WORKING_DIR = 0x10
HAS_ARGUMENTS = 0x20
IS_UNICODE = 0x80


class ParsedLink(NamedTuple):
    """Разобранный `.lnk` — ровно те поля, о которых говорят проверки."""  # noqa: RUF002

    flags: int
    attributes: int
    creation_time: int
    access_time: int
    write_time: int
    file_size: int
    show_command: int
    id_list: list[bytes]
    name: str | None
    relative_path: str | None
    working_dir: str | None
    arguments: str | None
    blocks: dict[int, bytes]


def _parse(data: bytes) -> ParsedLink:
    """Минимальный разбор MS-SHLLINK — общий для эталона и нашего файла.

    Живёт в тестах, а не в `config/shell_link.py`: читать `.lnk` программе
    незачем, и модуль-писатель, проверяющий сам себя собственным
    же читателем, не доказывал бы ничего. Этот разбор написан по структуре,
    снятой с эталона, и применяется к обоим файлам одинаково.
    """  # noqa: RUF002
    (flags, attributes) = struct.unpack_from("<II", data, 0x14)
    (creation, access, write) = struct.unpack_from("<QQQ", data, 0x1C)
    (file_size,) = struct.unpack_from("<I", data, 0x34)
    (show,) = struct.unpack_from("<I", data, 0x3C)

    offset = 0x4C
    items: list[bytes] = []
    if flags & HAS_ID_LIST:
        (size,) = struct.unpack_from("<H", data, offset)
        cursor = offset + 2
        while True:
            (item_size,) = struct.unpack_from("<H", data, cursor)
            if item_size == 0:
                break
            items.append(data[cursor + 2 : cursor + item_size])
            cursor += item_size
        offset += 2 + size
    if flags & HAS_LINK_INFO:
        (link_info_size,) = struct.unpack_from("<I", data, offset)
        offset += link_info_size

    def take(bit: int) -> tuple[str | None, int]:
        nonlocal offset
        if not flags & bit:
            return None, offset
        (count,) = struct.unpack_from("<H", data, offset)
        raw = data[offset + 2 : offset + 2 + count * 2]
        offset += 2 + count * 2
        return raw.decode("utf-16-le"), offset

    name, _ = take(HAS_NAME)
    relative, _ = take(HAS_RELATIVE_PATH)
    working, _ = take(HAS_WORKING_DIR)
    arguments, _ = take(HAS_ARGUMENTS)

    blocks: dict[int, bytes] = {}
    while offset < len(data):
        (block_size,) = struct.unpack_from("<I", data, offset)
        if block_size < 4:
            break
        (signature,) = struct.unpack_from("<I", data, offset + 4)
        blocks[signature] = data[offset + 8 : offset + block_size]
        offset += block_size

    return ParsedLink(
        flags, attributes, creation, access, write, file_size, show,
        items, name, relative, working, arguments, blocks,
    )


PLACEHOLDER_SID = b"S-1-5-21-1111111111-222222222-333333333-1001"


def _volume_serial(data: bytes) -> int:
    """Серийный номер тома из `LinkInfo` — ещё одно поле с данными машины."""  # noqa: RUF002
    (flags,) = struct.unpack_from("<I", data, 0x14)
    (id_list_size,) = struct.unpack_from("<H", data, 0x4C)
    link_info = 0x4C + 2 + id_list_size
    (volume_offset,) = struct.unpack_from("<I", data, link_info + 12)
    (serial,) = struct.unpack_from("<I", data, link_info + volume_offset + 8)
    assert flags & HAS_LINK_INFO
    return int(serial)


def _property_stores(block: bytes) -> dict[uuid.UUID, dict[int, bytes]]:
    """Разобрать `PropertyStoreDataBlock` в «FormatID → {PID: значение}».

    Значение отдаётся сырыми байтами после типа: для `VT_LPWSTR` — текст
    в ASCII (SID пишется латиницей), для `VT_CLSID` — 16 байт GUID. Тесту
    достаточно сравнить их с ожидаемой заглушкой, разбирать типы незачем.
    """  # noqa: RUF002
    stores: dict[uuid.UUID, dict[int, bytes]] = {}
    offset = 0
    while offset < len(block) - 4:
        (store_size,) = struct.unpack_from("<I", block, offset)
        if store_size == 0:
            break
        format_id = uuid.UUID(bytes_le=block[offset + 8 : offset + 24])
        values: dict[int, bytes] = {}
        cursor = offset + 24
        while cursor < offset + store_size - 4:
            (value_size,) = struct.unpack_from("<I", block, cursor)
            if value_size == 0:
                break
            (pid,) = struct.unpack_from("<I", block, cursor + 4)
            (kind,) = struct.unpack_from("<H", block, cursor + 9)
            payload = block[cursor + 13 : cursor + value_size]
            if kind == 0x1F:  # VT_LPWSTR
                (count,) = struct.unpack_from("<I", payload, 0)
                text = payload[4 : 4 + count * 2].decode("utf-16-le")
                values[pid] = text.rstrip("\x00").encode("ascii")
            else:
                values[pid] = payload[:16]
            cursor += value_size
        stores[format_id] = values
        offset += store_size
    return stores


def _built() -> bytes:
    return build_shell_link(
        Path(r"C:\Program Files\OneCStarter\OneCStarter.exe"),
        '--ib-name "Демо"',
        Path(r"C:\Program Files\OneCStarter"),
        "Демо — OneCStarter",
    )


# -- шаг 1: фактические значения эталона -----------------------------------


def test_reference_header_is_the_constant_prefix() -> None:
    """Первые 20 байт эталона — `HeaderSize` и `LinkCLSID`, они же у нас.

    Это единственная часть заголовка, которая обязана совпадать байт
    в байт: остальное описывает конкретную цель на конкретной машине.
    """  # noqa: RUF002
    reference = REFERENCE.read_bytes()
    assert struct.unpack_from("<I", reference, 0)[0] == 0x4C
    assert uuid.UUID(bytes_le=reference[4:20]) == uuid.UUID("00021401-0000-0000-c000-000000000046")
    assert _built()[:20] == reference[:20]


def test_reference_field_values() -> None:
    """Факт разбора эталона (шаг 1): значения, снятые hexdump'ом 09.08.2026."""
    parsed = _parse(REFERENCE.read_bytes())
    assert parsed.flags == 0xBF
    assert parsed.flags == (
        HAS_ID_LIST | HAS_LINK_INFO | HAS_NAME | HAS_RELATIVE_PATH
        | HAS_WORKING_DIR | HAS_ARGUMENTS | IS_UNICODE
    )
    assert parsed.attributes == 0x20  # FILE_ATTRIBUTE_ARCHIVE
    assert parsed.show_command == 1  # SW_SHOWNORMAL
    # Строки — UTF-16LE: флаг IsUnicode взведён, и разбор как UTF-16
    # даёт осмысленный текст, включая кириллицу в аргументах.
    assert parsed.name == "OneCStarter reference link"
    assert parsed.working_dir == r"C:\Windows\System32"
    assert parsed.arguments == '--ib-name "Демо"'
    # LinkTargetIDList присутствует и заканчивается элементом файла.
    assert len(parsed.id_list) == 5
    assert parsed.id_list[0][:2] == b"\x1f\x50"  # «Этот компьютер»
    assert parsed.id_list[1][:1] == b"\x2f"  # диск
    assert parsed.id_list[-1][:1] == b"\x32"  # файл, ANSI-имя
    # LinkInfo: том с серийным номером и локальный путь — данные машины.  # noqa: RUF003
    assert parsed.flags & HAS_LINK_INFO
    # Времена и размер в заголовке — метаданные настоящего notepad.exe.
    assert parsed.creation_time != 0
    assert parsed.file_size == 360448


def test_reference_fixture_carries_no_machine_identity() -> None:
    """Сторож обезличивания фикстуры: в эталоне нет идентификаторов машины.

    Сырой `.lnk` несёт четыре таких поля, и все четыре невидимы и в имени
    файла, и в свойствах ярлыка в проводнике — заметить их можно только
    в байтах:

    - `TrackerDataBlock.MachineID` — NetBIOS-имя машины открытым ASCII;
    - `Droid`/`DroidBirth` — четыре GUID отслеживания, версия 1 несёт
      MAC-адрес адаптера;
    - `PropertyStoreDataBlock` — SID пользователя, а в нём SID машины;
    - `PropertyStoreDataBlock` — GUID тома системного диска;
    - `LinkInfo.VolumeID` — серийный номер тома.

    Тест падает, если фикстуру пересняли с живой машины и не обезличили.
    Правило фикстур `CLAUDE.md` запрещает вносить такое в репозиторий.
    """  # noqa: RUF002
    parsed = _parse(REFERENCE.read_bytes())
    tracker = parsed.blocks[TRACKER_SIGNATURE]
    assert tracker[8:24] == b"TESTMACHINE\x00\x00\x00\x00\x00"
    assert tracker[24:88] == bytes(64), "GUID'ы отслеживания обязаны быть обнулены"
    stores = _property_stores(parsed.blocks[PROPERTY_STORE_SIGNATURE])
    sid = stores[uuid.UUID("46588ae2-4cbc-4338-bbfc-139326986dce")][4]
    assert sid == PLACEHOLDER_SID, "SID в PropertyStoreDataBlock не заменён на условный"
    volume = stores[uuid.UUID("446d16b1-8dad-4870-a748-402ea43d788c")][104]
    assert volume == bytes(16), "GUID тома в PropertyStoreDataBlock не обнулён"
    assert _volume_serial(REFERENCE.read_bytes()) == 0, "серийный номер тома не обнулён"


# -- сборка нашего ярлыка ---------------------------------------------------


def test_built_link_declares_only_what_it_writes() -> None:
    """Флаги нашего файла — подмножество флагов эталона, без выдуманных бит."""
    reference = _parse(REFERENCE.read_bytes())
    parsed = _parse(_built())
    assert parsed.flags & reference.flags == parsed.flags
    assert parsed.flags == (
        HAS_ID_LIST | HAS_NAME | HAS_WORKING_DIR | HAS_ARGUMENTS | IS_UNICODE
    )
    assert not parsed.flags & HAS_LINK_INFO
    assert parsed.attributes == 0x20
    assert parsed.show_command == 1


def test_built_link_carries_no_machine_data() -> None:
    """Инвариант 5: ярлык пользователя не несёт имени его машины и SID.

    `TrackerDataBlock` и `PropertyStoreDataBlock` по формату необязательны,
    а `LinkInfo` несёт серийный номер тома. Ничего из этого мы не пишем,
    поэтому файл одинаков на любой машине при одних и тех же аргументах.
    """  # noqa: RUF002
    parsed = _parse(_built())
    assert parsed.blocks == {}
    assert parsed.creation_time == 0
    assert parsed.access_time == 0
    assert parsed.write_time == 0
    assert parsed.file_size == 0


def test_built_link_ends_with_the_terminal_block() -> None:
    """`TerminalBlock` — обязательный конец файла по MS-SHLLINK, даже пустой.

    Финальное ревью, I5: удаление строки `payload += struct.pack("<I", 0)`
    из `build_shell_link` проходило все 42 теста файла, включая тот, что
    читает ярлык живым `IShellLink`. `assert parsed.blocks == {}` истинен
    и с блоком, и без него: разбор при `offset == len(data)` в цикл блоков
    не входит вовсе. Windows 11 усечённый файл терпит — но это её
    снисходительность, а не право формата: другая версия оболочки или
    другой потребитель `.lnk` не обязаны быть такими же.
    """  # noqa: RUF002
    assert _built()[-4:] == b"\x00\x00\x00\x00"


def test_built_link_is_deterministic() -> None:
    """Одни и те же аргументы дают один и тот же файл — данных машины нет."""
    assert _built() == _built()


def test_built_link_strings_round_trip() -> None:
    parsed = _parse(_built())
    assert parsed.name == "Демо — OneCStarter"
    assert parsed.working_dir == r"C:\Program Files\OneCStarter"
    assert parsed.arguments == '--ib-name "Демо"'
    assert parsed.relative_path is None


def test_string_data_counts_utf16_code_units() -> None:
    """`CountCharacters` — кодовые единицы UTF-16, а не кодовые точки Python.

    `len(value)` в Python считает кодовые точки, и на суррогатной паре
    (эмодзи и вообще всё за пределами BMP) счётчик занижается на единицу
    за каждый такой символ. Читатель берёт на два байта меньше, чем
    записано, и вся дальнейшая цепочка `StringData` едет: аргументы
    приклеиваются к рабочему каталогу, описание обрезается.

    Отказ при этом молчаливый: ярлык создаётся без ошибки, а по двойному
    клику `Arguments` оказывается пуст, `parse_ib_name` возвращает `None`
    и открывается главное окно вместо запуска базы. Имя вида
    «🔴 Бухгалтерия ПРОД» — не экзотика, а обычная пометка в списке.
    """  # noqa: RUF002
    name = "🔴 Бухгалтерия ПРОД"
    parsed = _parse(
        build_shell_link(
            Path(r"C:\a\b.exe"), f'--ib-name "{name}"', Path(r"C:\a"), f"{name} — OneCStarter"
        )
    )
    assert parsed.name == f"{name} — OneCStarter"
    assert parsed.working_dir == r"C:\a"
    assert parsed.arguments == f'--ib-name "{name}"'


def test_built_id_list_spells_out_the_target() -> None:
    """Цель несёт `LinkTargetIDList`: «Этот компьютер» → диск → части пути.

    [Ф] эксперимент 09.08.2026: `LinkInfo` цель не задаёт вовсе — ярлык
    с верным `LinkInfo` и негодным `LinkTargetIDList` не запускается
    (`WinError 2`), а с верным `LinkTargetIDList` и испорченным `LinkInfo`
    запускается. Имена частей пути пишутся UTF-16 (классы `0x35`/`0x36`),
    а не в кодовой странице ANSI (`0x31`/`0x32`), — так их пишет и сама
    Windows для не-ASCII имён, и так вывод не зависит от кодовой страницы
    машины.

    Первые два элемента — «Этот компьютер» и диск — сверяются с эталоном,
    а не с литералами: у эталона та же цель на диске `C:`, эти два элемента
    обязаны совпадать байт в байт, и такая сверка доказывает, что мы
    воспроизводим Windows, а не собственное представление о ней. Дальше
    сверять нечем: у эталона там `0x31`/`0x32`, которых мы не пишем.
    """  # noqa: RUF002
    reference = _parse(REFERENCE.read_bytes())
    parsed = _parse(_built())
    assert parsed.id_list[0] == reference.id_list[0]
    assert parsed.id_list[1] == reference.id_list[1]
    assert reference.id_list[0][:2] == b"\x1f\x50"
    assert reference.id_list[1][:1] == b"\x2f"
    names = [item[12:].decode("utf-16-le").rstrip("\x00") for item in parsed.id_list[2:]]
    assert names == ["Program Files", "OneCStarter", "OneCStarter.exe"]
    assert [item[0] for item in parsed.id_list[2:]] == [0x35, 0x35, 0x36]
    # У эталона на этих же местах — ANSI-классы, которых мы не пишем.  # noqa: RUF003
    assert [item[0] for item in reference.id_list[2:]] == [0x31, 0x31, 0x32]


def test_built_link_handles_non_ascii_path() -> None:
    """Путь с кириллицей не зависит от кодовой страницы машины."""  # noqa: RUF002
    data = build_shell_link(
        Path(r"C:\Users\Пётр\OneCStarter\OneCStarter.exe"), "", Path(r"C:\Users\Пётр"), ""
    )
    parsed = _parse(data)
    names = [item[12:].decode("utf-16-le").rstrip("\x00") for item in parsed.id_list[2:]]
    assert names == ["Users", "Пётр", "OneCStarter", "OneCStarter.exe"]


def test_built_link_omits_empty_strings() -> None:
    """Пустые описание/аргументы не объявляются флагом и не пишутся."""
    parsed = _parse(build_shell_link(Path(r"C:\a\b.exe"), "", Path(r"C:\a"), ""))
    assert not parsed.flags & HAS_NAME
    assert not parsed.flags & HAS_ARGUMENTS
    assert parsed.flags & HAS_WORKING_DIR


@pytest.mark.parametrize(
    "target",
    [
        Path(r"\\server\share\OneCStarter.exe"),
        Path("OneCStarter.exe"),
        Path("C:\\"),
    ],
)
def test_build_rejects_target_without_drive_path(target: Path) -> None:
    """Сетевой путь и относительный путь отвергаются, а не пишутся кое-как.

    Форма `LinkTargetIDList` для UNC другая, и собрать её из имеющегося
    разбора нельзя. Испорченный ярлык хуже отказа: он молча не запускается
    у пользователя, а причина не видна ни в свойствах, ни в имени файла.
    """  # noqa: RUF002
    with pytest.raises(LinkTargetRejectedError):
        build_shell_link(target, "", Path(r"C:\a"), "")


# -- имя файла ярлыка -------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Бухгалтерия", "Бухгалтерия.lnk"),
        ('Учёт: "склад"/2', "Учёт_ _склад__2.lnk"),
        ("   ", None),
        ("", None),
        ("...", None),
        ("Розница.", "Розница.lnk"),
        ("CON", "_CON.lnk"),
        ("com1", "_com1.lnk"),
        ("a" * 300, "a" * 200 + ".lnk"),
    ],
)
def test_safe_file_name(name: str, expected: str | None) -> None:
    if expected is None:
        with pytest.raises(LinkNameRejectedError):
            safe_file_name(name)
    else:
        assert safe_file_name(name) == expected


# -- цель и аргументы ярлыка ------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Демо", "Демо"),
        ("--ib-name", "--ib-name"),
        ("Демо Розница", '"Демо Розница"'),
        ("", '""'),
        ('Учёт "склад"', '"Учёт \\"склад\\""'),
        ("C:\\Базы\\", "C:\\Базы\\"),
        ("C:\\Мои базы\\", '"C:\\Мои базы\\\\"'),
    ],
)
def test_quote_argument(value: str, expected: str) -> None:
    """Кавычки по правилам `CommandLineToArgvW` — их применяет и Windows.

    Имя базы приходит из чужого файла и может содержать пробел и кавычку;
    без экранирования `--ib-name` получил бы обрезанное имя.

    Это сверка с **нашей моделью** правил. Сверку с настоящим
    `CommandLineToArgvW` делает `test_quote_argument_survives_real_parser`
    ниже — без неё табличный тест доказывал бы только внутреннюю
    непротиворечивость.
    """  # noqa: RUF002
    assert quote_argument(value) == expected


_ARGV_SINK = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n"
)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="CommandLineToArgvW разбирает командную строку только на Windows",
)
@pytest.mark.parametrize(
    "name",
    [
        "Демо",
        "Демо Розница",
        'Учёт "склад"',
        'Демо "1С" ПРОД',  # noqa: RUF001
        '"',
        'Базы\\"тест"',
        "Демо ПРОД\\",
        "C:\\Мои базы\\",
        "🔴 Бухгалтерия ПРОД",
    ],
)
def test_quote_argument_survives_real_parser(tmp_path: Path, name: str) -> None:
    """Имя базы доходит до процесса целиком через настоящий `CommandLineToArgvW`.

    Командная строка собирается нашим `quote_argument` и отдаётся
    `CreateProcess` строкой (на Windows `subprocess` передаёт её как есть),
    а разбирает её обратно сам Windows — тот же разборщик, что получает
    аргументы ярлыка. Проверяется и то, что до `parse_ib_name` доходит
    ровно исходное имя.

    Ветка экранирования кавычки (`shell_link.quote_argument`) иначе
    не проверялась бы ничем, кроме таблицы против нашей же модели правил —
    а именно ей исходный чек-лист шага 8 и не доверял.
    """  # noqa: RUF002
    sink = tmp_path / "sink.py"
    sink.write_text(_ARGV_SINK, encoding="utf-8")
    out = tmp_path / "argv.json"
    command = " ".join(
        quote_argument(part)
        for part in [sys.executable, str(sink), str(out), "--ib-name", name]
    )
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    argv = json.loads(out.read_text(encoding="utf-8"))
    assert argv == ["--ib-name", name]
    assert parse_ib_name(argv) == name


def test_shortcut_command_frozen() -> None:
    """Собранный экземпляр — цель сам exe, аргументы только имя базы."""
    target, arguments = shortcut_command(r"C:\Program Files\OneCStarter\OneCStarter.exe",
                                         "Демо Розница", frozen=True)
    assert target == Path(r"C:\Program Files\OneCStarter\OneCStarter.exe")
    assert arguments == '--ib-name "Демо Розница"'


def test_shortcut_command_from_source() -> None:
    """Не заморожены — цель интерпретатор, к аргументам добавляется `-m`."""  # noqa: RUF002
    target, arguments = shortcut_command(r"C:\Python\python.exe", "Демо", frozen=False)
    assert target == Path(r"C:\Python\python.exe")
    assert arguments == "-m onecstarter --ib-name Демо"


# -- сторож [Р]-части: наш файл читает сам Windows --------------------------  # noqa: RUF003


_READ_BACK_SCRIPT = """$ErrorActionPreference = 'Stop'
$LinkPath = $env:ONECSTARTER_LINK
$OutPath = $env:ONECSTARTER_OUT
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($LinkPath)
$values = @($link.TargetPath, $link.Arguments, $link.WorkingDirectory, $link.Description)
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($OutPath, $values, $utf8)
"""


def _read_back_with_windows_shell(link: Path, workdir: Path) -> list[str]:
    """Прочитать наш `.lnk` штатным `IShellLink` и вернуть четыре поля.

    `WScript.Shell.CreateShortcut` — та же реализация `IShellLink`, которой
    пользуется проводник, и тот же источник, из которого снят эталон.
    Значения передаются через файл в UTF-8, а не через stdout: кодировка
    консоли Windows зависит от машины и испортила бы и кириллицу, и эмодзи.

    Пути в скрипт идут через переменные окружения, а не аргументы `-File`:
    PowerShell 5.1 прогоняет аргументы через ANSI-кодовую страницу, и на
    en-US машине (cp1252) кириллический путь превращается в мусор —
    `CreateShortcut` молча отдаёт пустой ярлык (снято на github-runner,
    16.08.2026). Блок окружения процесса — всегда Unicode.

    Цель ярлыка не запускается: читаются только свойства.
    """  # noqa: RUF002
    script = workdir / "read_back.ps1"
    script.write_text(_READ_BACK_SCRIPT, encoding="utf-8")
    out = workdir / "read_back.txt"
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script),
        ],
        env={**os.environ, "ONECSTARTER_LINK": str(link), "ONECSTARTER_OUT": str(out)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"powershell вернул {result.returncode}: {result.stderr}"
    return out.read_text(encoding="utf-8").splitlines()


@pytest.mark.requires_windows_shell
@pytest.mark.skipif(sys.platform != "win32", reason="штатный IShellLink есть только на Windows")
def test_windows_shell_reads_our_link(tmp_path: Path) -> None:
    """Наш файл понимает сама Windows — сторож для [Р]-части формата.

    Разметку элементов `LinkTargetIDList` спецификация объявляет
    непрозрачной, и классов `0x35`/`0x36`, которыми мы пишем части пути,
    в эталоне нет вовсе — там `0x31`/`0x32` с именем в кодовой странице
    ANSI. Наша разметка перенесена по аналогии, и подтвердить её может
    только сам потребитель формата. Без этого теста подтверждением был бы
    разовый опыт, файл которого в репозиторий не попал: источник утрачен,
    проверить нечем, регрессию поймать нечем.

    Взяты нарочно недобрые данные: кириллица с пробелом и в пути, и в имени
    базы — путь проходит элементами `0x35`/`0x36` с не-ASCII именами,
    то есть ровно через ту разметку, ради которой тест и существует.

    Символа за пределами BMP здесь намеренно нет, и добавлять его сюда
    не надо. Проверено 09.08.2026: `WScript.Shell` теряет такие символы
    **сам** — ярлык, записанный им же, содержит в байтах `??` вместо
    эмодзи, то есть потеря происходит до файла. Это ограничение
    скриптового обёртки, а не формата и не нашей записи. Наш файл хранит
    суррогатную пару правильно (`test_string_data_counts_utf16_code_units`
    разбирает байты), и до процесса имя доходит целиком — проверено
    сквозным опытом: ярлык → `ShellExecute` → `CommandLineToArgvW` →
    `sys.argv` → `parse_ib_name` вернул исходное имя с эмодзи.
    """  # noqa: RUF002
    name = "Бухгалтерия ПРОД"
    directory = tmp_path / "Базы 1С"  # noqa: RUF001
    directory.mkdir()
    target = directory / "OneCStarter.exe"
    target.write_bytes(b"")
    link = tmp_path / "проба.lnk"
    link.write_bytes(
        build_shell_link(target, f'--ib-name "{name}"', directory, f"{name} — OneCStarter")
    )

    assert _read_back_with_windows_shell(link, tmp_path) == [
        str(target),
        f'--ib-name "{name}"',
        str(directory),
        f"{name} — OneCStarter",
    ]
