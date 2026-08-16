"""Запись ярлыка Windows (`.lnk`) — формат MS-SHLLINK, без pywin32 и без COM.

Модуль стоит рядом с `v8i.py` и `cestart_cfg.py`: тот же класс задачи —
чужой двоичный формат, побайтовые тесты, никаких зависимостей. Читать
`.lnk` мы не умеем и не должны: программе это не нужно, а разбор для
тестов живёт в `tests/unit/test_shell_link.py`.

Состав файла взят с эталона `tests/fixtures/reference.lnk`, созданного
самой Windows, и проверен экспериментами на Windows 11 (09.08.2026).
Уровни достоверности по правилу `CLAUDE.md`:

- [Д] `ShellLinkHeader`, `LinkFlags`, `StringData`, состав `ExtraData` —
  открытая спецификация MS-SHLLINK.
- [Р] внутреннее устройство элементов `LinkTargetIDList`: спецификация
  объявляет их содержимое непрозрачным, поэтому источники разные, и это
  различие существенно:

  - классы `0x1F` («Этот компьютер») и `0x2F` (диск) — **сняты с байтов
    эталона**; мы пишем их байт в байт такими же, и тест сверяет их
    не с литералом, а с элементами разобранного эталона;
  - классы `0x31`/`0x32` (имя в кодовой странице ANSI) — тоже сняты
    с эталона, но мы их **не пишем**;
  - классы `0x35`/`0x36` (имя сразу в UTF-16), которыми мы пишем части
    пути, **в эталоне отсутствуют вовсе**. Их разметка перенесена
    по аналогии с `0x31`/`0x32` — тот же 12-байтовый префикс (класс,
    ноль, размер, дата, атрибуты), имя в UTF-16 вместо ANSI. Подтверждение
    не «эталон», а `test_windows_shell_reads_our_link`: он даёт наш файл
    штатному `IShellLink` и сверяет, что тот вычитал цель, аргументы,
    рабочий каталог и описание. До этого теста подтверждением был разовый
    опыт, файл которого в репозиторий не попал, — источник был утрачен,
    и проверить утверждение было нечем.

- [Ф] измерено на Windows 11 09.08.2026, каждый пункт — отдельным
  ярлыком, запущенным через `ShellExecute` (`os.startfile`), и прочитанным
  обратно через `WScript.Shell`:

  1. `LinkInfo` цель **не** задаёт. Ярлык с верным `LinkInfo`
     и `LinkTargetIDList`, указывающим на несуществующий файл, не
     запускается (`WinError 2`); ярлык с верным `LinkTargetIDList`
     и намеренно испорченным путём в `LinkInfo` запускается правильно.
  2. Ярлык вообще без `LinkTargetIDList` не запускается (`WinError 1155`)
     и теряет цель в свойствах — даже если это эталон Windows, у которого
     удалён только этот список.
  3. Ярлык без `LinkInfo`, но с `LinkTargetIDList`, запускается и читается
     обратно правильно — и для ASCII-пути, и для пути с кириллицей.
  4. Имя части пути в элементе класса `0x31`/`0x32` — в кодовой странице
     ANSI машины, и оно ведущее: подменённое ANSI-имя ломает ярлык даже
     при верном Unicode-имени в блоке расширения. Классы `0x35`/`0x36`
     несут имя сразу в UTF-16 — их же пишет сама Windows для не-ASCII
     имён (проверено на ярлыке, который `WScript.Shell` сделал на путь
     с кириллицей: там `0x35`/`0x36`, а не `0x31`/`0x32`), и они снимают
     зависимость от кодовой страницы.
  5. `WScript.Shell` теряет символы за пределами BMP: ярлык, записанный
     им самим, содержит в байтах `??` вместо эмодзи. Это ограничение
     скриптовой обёртки, а не формата — наш файл хранит суррогатную пару
     правильно, и до процесса имя доходит целиком (ярлык →
     `ShellExecute` → `CommandLineToArgvW` → `sys.argv`). Важно при
     чтении результатов `test_windows_shell_reads_our_link`: сверять
     через него астральные символы бессмысленно.

Отсюда состав того, что пишем мы: заголовок, `LinkTargetIDList` на классах
`0x35`/`0x36` и `StringData`. Не пишем ничего из перечисленного ниже —
это не экономия, а требование инварианта 5:

- `TrackerDataBlock` несёт `MachineID`, то есть NetBIOS-имя машины
  пользователя открытым текстом, и четыре GUID отслеживания, где GUID
  версии 1 содержит MAC-адрес адаптера;
- `PropertyStoreDataBlock` несёт SID пользователя (а в нём — SID машины)
  и GUID тома системного диска;
- `LinkInfo` несёт серийный номер тома и его метку.

Ни одно из этих полей не нужно для запуска (пункты 1 и 3 выше), и каждое
превратило бы созданный пользователем ярлык в носитель сведений о его
машине. Побочное следствие — вывод не зависит от машины: одни и те же
аргументы дают один и тот же файл, и это проверяется тестом.
"""  # noqa: RUF002

import struct
from pathlib import Path

# [Д] MS-SHLLINK: размер заголовка и CLSID ярлыка — постоянные.
_HEADER_SIZE = 0x4C
_LINK_CLSID = b"\x01\x14\x02\x00\x00\x00\x00\x00\xc0\x00\x00\x00\x00\x00\x00\x46"

# [Р] CLSID «Этот компьютер» — первый элемент списка, снят с эталона.  # noqa: RUF003
_MY_COMPUTER = b"\xe0\x4f\xd0\x20\xea\x3a\x69\x10\xa2\xd8\x08\x00\x2b\x30\x30\x9d"

_HAS_ID_LIST = 0x01
_HAS_NAME = 0x04
_HAS_WORKING_DIR = 0x10
_HAS_ARGUMENTS = 0x20
_IS_UNICODE = 0x80

_FILE_ATTRIBUTE_ARCHIVE = 0x20
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_SW_SHOWNORMAL = 1

# [Р] классы элементов пути: каталог и файл с именем в UTF-16.  # noqa: RUF003
_ITEM_DIRECTORY = 0x35
_ITEM_FILE = 0x36

# Запрещённые в имени файла Windows символы плюс управляющие.
_FORBIDDEN = '<>:"/\\|?*'
# Имена устройств DOS: файл с таким именем создать нельзя, расширение  # noqa: RUF003
# от этого не спасает — `CON.lnk` так же недопустим, как `CON`.
_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{digit}" for digit in range(1, 10)]
    + [f"LPT{digit}" for digit in range(1, 10)]
)
# Предел имени файла на NTFS — 255 символов; оставляем запас на «.lnk»
# и на то, что каталог назначения выбирает пользователь.
_MAX_STEM = 200


class LinkNameRejectedError(ValueError):
    """Имя базы не превращается в имя файла ярлыка.

    Слой `config` отдаёт свою ошибку, а не `ServicesError`: обратная
    зависимость `config` → `services` перевернула бы слои (тот же приём,
    что у `LineBreakRejectedError` в `v8i.py` — её переводит `writer.py`).
    """  # noqa: RUF002


class LinkTargetRejectedError(ValueError):
    """Для такой цели мы не умеем собрать `LinkTargetIDList`.

    Список строится как «Этот компьютер → диск → части пути», и другой
    формы у нас нет: у сетевого пути (UNC) устройство списка другое,
    а у относительного пути нет ни диска, ни начала. Отказ лучше файла,
    который молча не запустится у пользователя.
    """  # noqa: RUF002


def safe_file_name(name: str) -> str:
    """Имя базы → имя файла ярлыка с расширением `.lnk`.

    Запрещённые в именах файлов символы заменяются подчёркиванием, а не
    выбрасываются: `Учёт: склад` и `Учёт склад` — разные базы, и склеивать
    их в одно имя файла нельзя. Пробелы сохраняются — они в именах файлов
    разрешены.
    """  # noqa: RUF002
    cleaned = "".join("_" if character in _FORBIDDEN or ord(character) < 32 else character
                      for character in name)
    cleaned = cleaned.strip().rstrip(".").strip()
    if not cleaned:
        raise LinkNameRejectedError(
            f"Из имени «{name}» не получается имя файла: в нём нет ни одного "
            "символа, допустимого в имени файла Windows"
        )
    if cleaned.upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return f"{cleaned[:_MAX_STEM]}.lnk"


def quote_argument(value: str) -> str:
    """Экранировать один аргумент по правилам `CommandLineToArgvW`.

    Имя базы приходит из чужого файла и может содержать и пробел,
    и кавычку. Без экранирования `--ib-name` получил бы обрезанное имя,
    и ярлык открывал бы не ту базу или не открывал никакую.
    """
    if value and not any(character in value for character in ' \t"'):
        return value
    parts = ['"']
    backslashes = 0
    for character in value:
        if character == "\\":
            backslashes += 1
            continue
        if character == '"':
            # Перед кавычкой все накопленные слэши удваиваются, и сама
            # кавычка экранируется ещё одним.
            parts.append("\\" * (backslashes * 2 + 1))
            parts.append('"')
        else:
            parts.append("\\" * backslashes)
            parts.append(character)
        backslashes = 0
    # Слэши перед закрывающей кавычкой удваиваются, иначе она сама
    # окажется экранированной и аргумент «съест» следующий.
    parts.append("\\" * (backslashes * 2))
    parts.append('"')
    return "".join(parts)


def shortcut_command(executable: str, name: str, *, frozen: bool) -> tuple[Path, str]:
    """Цель и аргументы ярлыка на нашу программу для базы `name`.

    Чистая функция, отдельно от диалога сохранения: собранный экземпляр
    запускается сам (`frozen`), а из исходников — через интерпретатор,
    и тогда в аргументы добавляется `-m onecstarter`. Внутри диалога это
    было бы непроверяемо.
    """  # noqa: RUF002
    parts: list[str] = [] if frozen else ["-m", "onecstarter"]
    parts += ["--ib-name", name]
    return Path(executable), " ".join(quote_argument(part) for part in parts)


def build_shell_link(target: Path, arguments: str, working_dir: Path, description: str) -> bytes:
    """Собрать байты ярлыка `.lnk` на `target` с аргументами `arguments`.

    Пустые `arguments`/`description`/`working_dir` не объявляются флагом
    и не пишутся вовсе — файл описывает только то, что в нём есть.
    """  # noqa: RUF002
    id_list = _id_list(target)
    # Рабочий каталог пишется всегда: `Path` пустой строкой не бывает
    # (`str(Path(""))` — это «.»), поэтому условие здесь было бы мёртвым.
    flags = _HAS_ID_LIST | _IS_UNICODE | _HAS_WORKING_DIR
    if description:
        flags |= _HAS_NAME
    if arguments:
        flags |= _HAS_ARGUMENTS

    payload = bytearray()
    payload += struct.pack("<I", _HEADER_SIZE)
    payload += _LINK_CLSID
    payload += struct.pack("<II", flags, _FILE_ATTRIBUTE_ARCHIVE)
    # Времена создания/доступа/изменения и размер — метаданные цели
    # на конкретной машине. MS-SHLLINK разрешает нули («время не задано»),
    # и нули здесь — не заглушка, а отказ переносить чужие метаданные.  # noqa: RUF003
    payload += struct.pack("<QQQ", 0, 0, 0)
    payload += struct.pack("<Ii", 0, 0)
    payload += struct.pack("<I", _SW_SHOWNORMAL)
    payload += struct.pack("<HHII", 0, 0, 0, 0)
    assert len(payload) == _HEADER_SIZE, "заголовок MS-SHLLINK обязан быть 76 байт"

    payload += struct.pack("<H", len(id_list)) + id_list
    if description:
        payload += _string_data(description)
    payload += _string_data(str(working_dir))
    if arguments:
        payload += _string_data(arguments)
    # TerminalBlock: ExtraData пуст, но признак конца обязателен.
    payload += struct.pack("<I", 0)
    return bytes(payload)


def _string_data(value: str) -> bytes:
    """`StringData`: длина в кодовых единицах UTF-16, затем сам текст.

    Считаем именно единицы, а не `len(value)`: [Д] MS-SHLLINK определяет
    `CountCharacters` как число 16-битных единиц, а `len` в Python даёт
    кодовые точки. На символе за пределами BMP (эмодзи в имени базы —
    обычная пометка, а не экзотика) счётчик занижался бы на единицу
    за каждый такой символ, и вся дальнейшая цепочка `StringData` ехала
    бы: аргументы приклеивались к рабочему каталогу, описание обрезалось.
    Ярлык при этом создавался бы без ошибки и ломался молча.
    """  # noqa: RUF002
    encoded = value.encode("utf-16-le")
    return struct.pack("<H", len(encoded) // 2) + encoded


def _item(data: bytes) -> bytes:
    """Элемент `ItemID`: размер вместе с полем размера, затем содержимое."""  # noqa: RUF002
    return struct.pack("<H", len(data) + 2) + data


def _id_list(target: Path) -> bytes:
    """`LinkTargetIDList`: «Этот компьютер» → диск → части пути → терминатор."""
    parts = target.parts
    drive = parts[0][:1] if parts else ""
    if not target.is_absolute() or not drive.isalpha() or len(parts) < 2:
        raise LinkTargetRejectedError(
            f"Ярлык можно создать только для программы на локальном диске, "
            f"а путь — «{target}»"  # noqa: RUF001
        )
    body = _item(b"\x1f\x50" + _MY_COMPUTER)
    body += _item(b"\x2f" + f"{drive.upper()}:\\".encode("ascii") + bytes(19))
    names = parts[1:]
    for index, name in enumerate(names):
        body += _path_item(name, is_directory=index < len(names) - 1)
    # Терминатор списка — элемент нулевого размера.
    return body + b"\x00\x00"


def _path_item(name: str, *, is_directory: bool) -> bytes:
    """Часть пути отдельным `ItemID` с именем в UTF-16 — классы `0x35`/`0x36`.

    [Р] Разметка перенесена по аналогии с классами `0x31`/`0x32` эталона:
    тот же 12-байтовый префикс — класс, ноль, размер файла, дата изменения
    в формате DOS, атрибуты, — а дальше имя в UTF-16 вместо ANSI. Самих
    `0x35`/`0x36` в эталоне нет: он сделан на путь из одних ASCII-имён,
    для которых Windows пишет `0x31`/`0x32`. Подтверждение разметки —
    `test_windows_shell_reads_our_link`, а не эталон.

    Размер и дата остаются нулями: это метаданные файла на конкретной
    машине, а для поиска цели оболочке хватает имени ([Ф] ярлык с нулями
    запускается и читается обратно).
    """  # noqa: RUF002
    body = bytes((_ITEM_DIRECTORY if is_directory else _ITEM_FILE, 0x00))
    body += struct.pack("<II", 0, 0)
    body += struct.pack(
        "<H", _FILE_ATTRIBUTE_DIRECTORY if is_directory else _FILE_ATTRIBUTE_ARCHIVE
    )
    body += name.encode("utf-16-le") + b"\x00\x00"
    return _item(body)
