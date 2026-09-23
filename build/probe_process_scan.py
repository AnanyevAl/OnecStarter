"""Пробник: чем дешевле всего получить список процессов с именами на Windows.

Повод — замер на сервере заказчика 23.09.2026 (спека 3.2.1, §9): тёплый скан
`psutil` стоит там 112 мс на 782 процессах, тогда как на машине разработчика
на 651 процессе — 4–6 мс. При этом детально читаются ВСЕГО ДВА процесса:
дорог не разбор совпавших, а сам обход. Прежде чем менять механизм, нужно
измерить альтернативы там же, где болит, — расхождение в двадцать раз при
почти равном числе процессов доказывает, что мерить на своей машине бесполезно.

Пробник ничего не меняет в системе и никуда не пишет: только читает список
процессов и печатает числа. Имена процессов в вывод НЕ попадают (кроме тех
двух-трёх имён серверов 1С, которые мы и так ищем по фиксированному списку) —
вывод можно приложить к письму целиком.

Запуск на сервере: `probe_process_scan.exe > probe.txt`
"""  # noqa: RUF002

import ctypes
import statistics
import sys
import time
from collections.abc import Callable
from ctypes import wintypes

# Имена, которые ищут мониторы программы. Совпадения по ним — единственное,
# ради чего вообще делается скан.
WANTED = frozenset(
    {"ragent.exe", "rmngr.exe", "rphost.exe", "1cedt.exe", "1cedtcli.exe"}
)
REPEATS = 7

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260


class PROCESSENTRY32W(ctypes.Structure):
    """Запись снимка Toolhelp. Поля и порядок — как в tlhelp32.h."""

    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        # ULONG_PTR: на x64 это 8 байт, и c_size_t даёт правильный размер
        # структуры — ошибка здесь сдвинула бы все последующие поля.
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    )


def _kernel32() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    dll.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    dll.Process32FirstW.restype = wintypes.BOOL
    dll.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    dll.Process32NextW.restype = wintypes.BOOL
    dll.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    dll.CloseHandle.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = (wintypes.HANDLE,)
    return dll


def toolhelp_names() -> list[tuple[int, str]]:
    """Все процессы одним снимком: ни один процесс не открывается.

    Именно этим Toolhelp отличается от `psutil.Process.name()`, который
    на Windows получает имя из пути образа и потому платит за каждый процесс
    отдельно (psutil 7.2.2, `_pswindows.py`).
    """  # noqa: RUF002
    dll = _kernel32()
    snapshot = dll.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        found: list[tuple[int, str]] = []
        ok = dll.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            found.append((entry.th32ProcessID, entry.szExeFile))
            ok = dll.Process32NextW(snapshot, ctypes.byref(entry))
        return found
    finally:
        dll.CloseHandle(snapshot)


def psutil_names() -> list[tuple[int, str]]:
    """Текущий способ программы — для сравнения на той же машине."""
    import psutil

    found: list[tuple[int, str]] = []
    for process in psutil.process_iter(attrs=["pid", "name"]):
        try:
            info = process.info
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        name = info.get("name")
        if name is not None:
            found.append((info["pid"], name))
    return found


def psutil_names_cold() -> list[tuple[int, str]]:
    """psutil со сброшенным кэшем — воспроизводит ПЕРВЫЙ скан после старта.

    Главная аномалия сервера: первый скан там стоил 22 959 мс против 111 мс
    на машине разработчика. `process_iter` держит объекты `Process` между
    вызовами, и имя каждого процесса читается заново только для тех, кого
    в кэше нет. Сброс кэша перед каждым замером даёт повторяемый холодный
    случай вместо одного наблюдения на запуск.
    """  # noqa: RUF002
    import psutil

    psutil.process_iter.cache_clear()
    return psutil_names()


def _measure(label: str, call: "Callable[[], list[tuple[int, str]]]") -> list[float]:
    """Первый вызов и повторы: у psutil они различаются на порядки."""  # noqa: RUF002
    started = time.perf_counter()
    first_result = call()
    first_ms = (time.perf_counter() - started) * 1000
    warm: list[float] = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        call()
        warm.append((time.perf_counter() - started) * 1000)
    print(
        f"{label:<28} процессов {len(first_result):4d} | "
        f"первый {first_ms:8.1f} мс | "
        f"повторы: мин {min(warm):7.1f}  медиана {statistics.median(warm):7.1f}  "
        f"макс {max(warm):7.1f} мс"
    )
    return warm


def main() -> int:
    # Вывод пойдёт в файл (`probe.exe > probe.txt`) и оттуда — письмом.
    # Без явной перенастройки Python возьмёт кодировку консоли (cp866),
    # и кириллица в файле окажется нечитаемой у получателя.  # noqa: RUF003
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    print("Пробник списка процессов — OneCStarter, подготовка вехи 3.3")
    print(f"Python {sys.version.split()[0]}, повторов на способ: {REPEATS}\n")

    try:
        toolhelp = toolhelp_names()
    except OSError as error:
        print(f"Toolhelp недоступен: {error}")
        return 1

    _measure("Toolhelp (снимок)", toolhelp_names)
    try:
        psutil_result = psutil_names()
        _measure("psutil (как сейчас)", psutil_names)
        # Отдельной строкой, потому что именно этот случай на сервере дал
        # двадцать три секунды, а у разработчика — сотню миллисекунд.  # noqa: RUF003
        _measure("psutil (кэш сброшен)", psutil_names_cold)
    except ImportError:
        print("psutil недоступен — сравнения не будет")
        psutil_result = []

    print()
    th_names = {name.casefold() for _pid, name in toolhelp}
    th_hits = sorted(n for n in th_names if n in WANTED)
    print(f"Toolhelp нашёл процессов: {len(toolhelp)}")
    print(f"  из них искомых: {len(th_hits)} — {', '.join(th_hits) if th_hits else 'нет'}")

    if psutil_result:
        ps_pids = {pid for pid, _ in psutil_result}
        th_pids = {pid for pid, _ in toolhelp}
        ps_names = {name.casefold() for _pid, name in psutil_result}
        ps_hits = sorted(n for n in ps_names if n in WANTED)
        print(f"psutil нашёл процессов:   {len(psutil_result)}")
        print(f"  из них искомых: {len(ps_hits)} — {', '.join(ps_hits) if ps_hits else 'нет'}")
        print()
        print("Сходимость двух способов (списки снимаются не одновременно,")
        print("поэтому расхождение в единицы процессов — норма, а не дефект):")  # noqa: RUF001
        print(f"  видят оба:        {len(ps_pids & th_pids)}")  # noqa: RUF001
        print(f"  только Toolhelp:  {len(th_pids - ps_pids)}")
        print(f"  только psutil:    {len(ps_pids - th_pids)}")
        print(f"  искомые совпали:  {'да' if th_hits == ps_hits else 'НЕТ — разобраться'}")  # noqa: RUF001
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
