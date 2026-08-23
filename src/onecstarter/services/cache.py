"""Очистка кэшей 1С по `ID` записи (спека вехи «Завершение v1», §3–§5).

Кэшей два, и это разные по смыслу хранилища (терминология заказчика,
[Проверено, 23.08.2026], протокол T-05.10):

- пользовательский — `%APPDATA%\\1C\\1Cv8\\<ID>`: профили клиентов
  `1cv8.pfl`/`1cv8c.pfl`, история ввода, словарь;
- программный — `%LOCALAPPDATA%\\1C\\1Cv8\\<ID>`: `Config`, `ConfigSave`,
  `SICache` — кэш конфигурации.

Имя каталога кэша равно `ID` секции `.v8i` [Проверено, 23.08.2026: 58
совпадений из 66]. Путь строится ТОЛЬКО из корня окружения и `ID`,
прошедшего проверку на GUID: при пустом `ID` склейка дала бы сам корень
`%LOCALAPPDATA%\\1C\\1Cv8`, и рекурсивное удаление снесло бы кэши всех баз
разом (спека §5.1 — главный риск вехи). Без валидного `ID` адреса нет вовсе.

Удаление — рекурсивным обходом, а не перечнем известных имён: `vrs-cache`
лежит внутри `<ID>\\<user>\\` [Проверено], жёсткий перечень протух бы молча
при смене версии платформы. Обход не следует за junction и символическими
ссылками (спека §5.2) и не останавливается на первой ошибке (решение
заказчика: «пробовать и честно докладывать»). Файловые операции подаются
протоколом `CacheOps` — тот же приём, что `Registry`
в `services/autostart.py`: тест моделирует занятый файл, не имея настоящего.
"""  # noqa: RUF002

import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

__all__ = [
    "CACHE_TITLES",
    "CacheEntry",
    "CacheKind",
    "CacheMeasure",
    "CacheOps",
    "ClearReport",
    "EntryKind",
    "WindowsCacheOps",
    "cache_path",
    "clear",
    "clear_question",
    "format_size",
    "is_valid_cache_id",
    "measure",
    "report_text",
]


class CacheKind(Enum):
    USER = "user"        # %APPDATA%
    PROGRAM = "program"  # %LOCALAPPDATA%


CACHE_TITLES = {CacheKind.USER: "пользовательский", CacheKind.PROGRAM: "программный"}

_ROOT_VARS = {CacheKind.USER: "APPDATA", CacheKind.PROGRAM: "LOCALAPPDATA"}

_GUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def is_valid_cache_id(section_id: str | None) -> bool:
    """GUID и только GUID, без трима: платформа именует каталог точным значением
    `ID`, и значение с пробелами по краям с именем каталога не совпадёт.
    """  # noqa: RUF002
    return section_id is not None and _GUID.fullmatch(section_id) is not None


def cache_path(
    env: Mapping[str, str], kind: CacheKind, section_id: str | None
) -> Path | None:
    """Адрес кэша записи. `None` — адреса нет: невалидный `ID` или нет корня.

    Чистая функция (инвариант 2): обращений к ФС нет, окружение — аргументом.
    Проверка на GUID — защита §5.1: `Path(root) / "1C" / "1Cv8" / ""` дала бы
    сам корень, пустые сегменты pathlib молча отбрасывает.
    """
    if section_id is None or not is_valid_cache_id(section_id):
        return None
    root = env.get(_ROOT_VARS[kind])
    if not root:
        return None
    return Path(root) / "1C" / "1Cv8" / section_id


@dataclass(frozen=True)
class CacheMeasure:
    """Итог замера перед удалением — для вопроса подтверждения (спека §3.5)."""

    files: int
    total_bytes: int


@dataclass(frozen=True)
class ClearReport:
    """Итог удаления: два числа и счётчик первичных отказов (спека §3.7)."""

    deleted: int      # удалено файлов и ссылок
    freed_bytes: int  # сумма размеров удалённых файлов
    failed: int       # первичные отказы; вторичные «папка не пуста» не считаются


_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")


def format_size(size: int) -> str:
    """«207 МБ», «2,9 ГБ» — стиль протокола T-05.10: запятая и один знак
    после неё, только когда значение меньше десяти и дробь не нулевая.
    """
    value = float(size)
    index = 0
    while value >= 1024 and index < len(_UNITS) - 1:
        value /= 1024
        index += 1
    if index > 0 and value < 10:
        text = f"{value:.1f}".replace(".", ",").removesuffix(",0")
    else:
        text = str(int(value))
    return f"{text} {_UNITS[index]}"


def clear_question(kind: CacheKind, base_name: str, measured: CacheMeasure) -> str:
    """Текст подтверждения — всегда с именем базы и размером (спека §3.5).

    Тон различается по меткам достоверности, а не по стилю:
    про программный кэш [Проверено, 23.08.2026, шаг 8] — после удаления база
    запускается как обычно; про пользовательский последствия [не проверено],
    поэтому текст перечисляет измеренный состав каталога (шаг 6) и не обещает
    «ничего страшного».
    """  # noqa: RUF002
    head = (
        f"Удалить {CACHE_TITLES[kind]} кэш базы «{base_name}» "
        f"({format_size(measured.total_bytes)})?"
    )
    if kind is CacheKind.PROGRAM:
        return f"{head}\n\nКэш конфигурации платформа создаст заново при следующем запуске базы."  # noqa: RUF001
    return (
        f"{head}\n\nВместе с ним будут удалены настройки форм, история ввода "  # noqa: RUF001
        "и словарь этой базы."
    )


def _deleted_phrase(count: int) -> str:
    """«Удалён 1 файл», «Удалено 2 файла», «Удалено 412 файлов»."""
    if count % 100 not in range(11, 15):
        if count % 10 == 1:
            return f"Удалён {count} файл"
        if count % 10 in (2, 3, 4):
            return f"Удалено {count} файла"
    return f"Удалено {count} файлов"


def report_text(report: ClearReport) -> str:
    """Два числа и ничего лишнего (спека §3.7); трассировки не показываются.

    Вторичные отказы («Папка не пуста») в `failed` не входят по построению
    `clear`: каталог не удалился из-за занятого файла, о котором уже сказано.
    """  # noqa: RUF002
    head = f"{_deleted_phrase(report.deleted)}, освобождено {format_size(report.freed_bytes)}."
    if not report.failed:
        return head
    return (
        f"{head} Не удалось удалить {report.failed} — файлы заняты "  # noqa: RUF001
        "запущенной 1С; закройте программу и повторите."  # noqa: RUF001
    )


class EntryKind(Enum):
    FILE = "file"
    DIR = "dir"
    LINK = "link"  # symlink или junction: содержимое по ссылке не обходится


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    kind: EntryKind
    size: int  # байт; у каталогов и ссылок 0  # noqa: RUF003


class CacheOps(Protocol):
    """Файловые операции обхода и удаления — инъекцией, как `Registry`
    в autostart: тест моделирует занятый файл, не имея настоящего."""

    def list_dir(self, path: Path) -> list[CacheEntry]: ...

    def is_dir(self, path: Path) -> bool: ...

    def remove_file(self, path: Path) -> None: ...

    def remove_dir(self, path: Path) -> None: ...

    def remove_link(self, path: Path) -> None: ...


class WindowsCacheOps:
    """Настоящая файловая система. Единственное место обхода и удаления.

    Ссылкой считается и symlink, и junction: junction под lstat выглядит
    каталогом (S_IFDIR), и без отдельной проверки рекурсия ушла бы по нему
    за пределы кэша (спека §5.2). `DirEntry.is_junction()` — Python 3.12+.
    """

    def list_dir(self, path: Path) -> list[CacheEntry]:
        entries: list[CacheEntry] = []
        with os.scandir(path) as scan:
            for entry in scan:
                if entry.is_symlink() or entry.is_junction():
                    kind, size = EntryKind.LINK, 0
                elif entry.is_dir(follow_symlinks=False):
                    kind, size = EntryKind.DIR, 0
                else:
                    kind, size = EntryKind.FILE, entry.stat(follow_symlinks=False).st_size
                entries.append(CacheEntry(Path(entry.path), kind, size))
        return entries

    def is_dir(self, path: Path) -> bool:
        """Проверка существования корня кэша; СЛЕДУЕТ за ссылками — для
        решения «идти ли внутрь» при обходе не применять (§5.2).
        """
        return path.is_dir()

    def remove_file(self, path: Path) -> None:
        path.unlink()

    def remove_dir(self, path: Path) -> None:
        path.rmdir()

    def remove_link(self, path: Path) -> None:
        # Junction под lstat — каталог (S_IFDIR) и снимается rmdir, который
        # удаляет саму ссылку, не следуя за ней [проверено на этой машине].
        # Симлинк — и на файл, и на каталог — под lstat S_IFLNK и уходит
        # в unlink; симлинк на каталог CPython на Windows удаляет внутри
        # unlink через RemoveDirectoryW [из исходников CPython, на живой
        # машине не проверено: создание симлинка требует привилегии].
        if stat.S_ISDIR(path.lstat().st_mode):
            path.rmdir()
        else:
            path.unlink()


def measure(root: Path, ops: CacheOps) -> CacheMeasure:
    """Замер до удаления — для подтверждения с размером (спека §3.5).

    Ошибки чтения не поднимаются: замер — оценка для вопроса, а не отчёт;
    недочитанное всё равно не удалится и попадёт в отчёт удаления.
    Ссылки считаются записями без размера, их содержимое не обходится.
    """  # noqa: RUF002
    files = 0
    total = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = ops.list_dir(directory)
        except OSError:
            continue
        for entry in entries:
            if entry.kind is EntryKind.DIR:
                stack.append(entry.path)
            else:
                files += 1
                total += entry.size
    return CacheMeasure(files=files, total_bytes=total)


def clear(root: Path, ops: CacheOps) -> ClearReport:
    """Удалить дерево кэша. Обход не останавливается на первой ошибке (§3.6).

    Вторичный отказ — не удалившийся каталог, внутри которого остался занятый
    файл: о файле уже сказано, второй раз о том же не говорим (§3.7). Каталог
    с отказами внутри не пробуется вовсе — исход известен заранее. Отказ
    rmdir на каталоге, где всё внутри удалилось, — первичный: о нём ничем
    другим не сказано. По ссылкам не ходим — удаляем их как ссылки (§5.2).

    Сам `root` передаётся вызывающим и проверке на reparse point не
    подвергается — обход смотрит на вид только у ДЕТЕЙ каждого каталога
    (`list_dir` классифицирует их). Если сам корень — junction (например,
    кэш перенесён на другой диск подменой каталога ссылкой), `clear_dir`
    зайдёт в него как в обычный каталог и очистит содержимое ЦЕЛИ, а не
    самой ссылки; затем `ops.remove_dir(root)` снимет саму ссылку — так же,
    как `WindowsCacheOps.remove_link` снимает junction внутри дерева, не
    удаляя то, на что он указывает.
    """  # noqa: RUF002
    deleted = 0
    freed = 0
    failed = 0

    def clear_dir(directory: Path) -> bool:
        """Удалить содержимое каталога; True — внутри не осталось ничего."""
        nonlocal deleted, freed, failed
        try:
            entries = ops.list_dir(directory)
        except OSError:
            failed += 1
            return False
        ok = True
        for entry in entries:
            if entry.kind is EntryKind.DIR:
                if clear_dir(entry.path):
                    try:
                        ops.remove_dir(entry.path)
                    except OSError:
                        failed += 1
                        ok = False
                else:
                    ok = False  # вторичный отказ: rmdir не пробуем и не считаем
            elif entry.kind is EntryKind.LINK:
                try:
                    ops.remove_link(entry.path)
                    deleted += 1
                except OSError:
                    failed += 1
                    ok = False
            else:
                try:
                    ops.remove_file(entry.path)
                    deleted += 1
                    freed += entry.size
                except OSError:
                    failed += 1
                    ok = False
        return ok

    if clear_dir(root):
        try:
            ops.remove_dir(root)
        except OSError:
            failed += 1
    return ClearReport(deleted=deleted, freed_bytes=freed, failed=failed)
