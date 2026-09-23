"""Замеры длительности под флагом — отдельный файл, без Qt.

Включается переменной `ONECSTARTER_PERF`: portable запускают двойным
кликом, и ключ командной строки потребовал бы править ярлык, а переменная
одинаково работает для `OneCStarter.exe` и `OneCStarterc.exe`.

Свой файл, а не `onecstarter.log`: при включённом режиме поток строк
измеряется тысячами в час, и ротация основного лога (512 КБ) стёрла бы
за несколько часов историю стартов за месяц — ту самую, по которой
22.09.2026 и был поставлен диагноз (спека 3.2.1, §1).

В строки идут только метка операции, миллисекунды и ЦЕЛЫЕ счётчики:
лог прикладывают к issue (инвариант 5). Сигнатура `**counters: int`
делает передачу пути или имени базы вместо счётчика ошибкой типов,
а не вопросом дисциплины исполнителя — но только для счётчиков: `stage`
типизирован как `str`, и mypy пропустит в него любую строку, включая
путь или имя базы. За тем, что `stage` — литерал, а не собранная
из данных строка, следит вызывающий код; подробнее — в докстринге
`measure`.
"""  # noqa: RUF002

import logging
import logging.handlers
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

LOG_NAME = "perf.log"
ENV_NAME = "ONECSTARTER_PERF"
_TRUE = frozenset({"1", "true", "yes", "on"})
# Слово PERF — литерал, а не уровень записи: имя логгера в строку  # noqa: RUF003
# не выводится, все записи файла принадлежат одному логгеру, и повторять
# его в каждой строке незачем.  # noqa: RUF003
_FORMAT = "%(asctime)s PERF %(message)s"
# 4 МБ × 3 — около пяти суток при двух сканах в 5 с (спека §11).  # noqa: RUF003
_MAX_BYTES = 4 * 1024 * 1024
_BACKUPS = 3

_log = logging.getLogger("onecstarter.perf")
_enabled = False


def is_enabled(env: Mapping[str, str]) -> bool:
    """Включён ли режим. Чистая функция, ничего не настраивает."""
    return env.get(ENV_NAME, "").strip().casefold() in _TRUE


def enabled() -> bool:
    """Включён ли режим ПОСЛЕ `setup`. Для горячих мест, зовущих часто."""
    return _enabled


def setup(env: Mapping[str, str]) -> Path | None:
    """Настроить perf-лог. `None` — режим выключен либо файл не вышел.

    Отказ не роняет программу — тот же принцип, что у
    `diagnostics.setup_logging`: приложение важнее лога.

    Идемпотентна: повторный вызов не добавляет второй обработчик поверх
    старого (иначе `measure` задваивал бы каждую строку и держал открытым
    лишний файловый дескриптор) — но снимает прежний ТОЛЬКО после того,
    как новый успешно создан. Отказ создания (недоступный каталог) обязан
    заставать прежнее рабочее состояние нетронутым: обратный порядок
    однажды уже приводил к тому, что второй неудачный `setup` сносил
    рабочий обработчик первого, `_enabled` оставался `True`, а строки
    `measure` после этого молча терялись — писать было некуда.
    """  # noqa: RUF002
    global _enabled
    if not is_enabled(env):
        return None
    # Находка финального ревью ветки: heartbeat (`ui/heartbeat.py`) и события
    # дерева (`ui/bases/view.py`, `_BasesTree.event`) смотрят на `is_enabled(env)`
    # напрямую, в обход `_enabled`/`measure()`, и пишут в этот логгер сами.
    # Если ниже не выйдет создать файл, `setup()` вернёт `None`, но переменная
    # окружения при этом остаётся включённой — и без `propagate = False`
    # ИМЕННО ЗДЕСЬ, до попытки создать файл, их строки поднялись бы к корневому
    # логгеру и попали в `onecstarter.log`, стирая ротацией (512 КБ) ровно ту
    # историю стартов, ради которой файлы и разделены. Выставляется безусловно,
    # как только режим признан включённым по переменной — независимо от того,
    # получится ли завести файл.
    _log.propagate = False
    directory = Path(env.get("APPDATA", ".")) / "OneCStarter" / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            directory / LOG_NAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUPS,
            encoding="utf-8",
        )
    except OSError:
        # Прежнее состояние (обработчики, _enabled) не тронуто: если до
        # этого вызова режим уже работал, он продолжает работать.
        # `propagate` уже снят выше и назад не возвращается: `is_enabled(env)`
        # здесь истинно, а значит heartbeat и события дерева всё равно будут  # noqa: RUF003
        # писать в этот логгер напрямую, и корень им закрыт правильно.
        return None
    handler.setFormatter(logging.Formatter(_FORMAT))
    for old in list(_log.handlers):
        _log.removeHandler(old)
        old.close()
    _log.setLevel(logging.INFO)
    _log.addHandler(handler)
    _enabled = True
    return directory / LOG_NAME


@contextmanager
def measure(stage: str, **counters: int) -> Iterator[dict[str, int]]:
    """Замерить блок и записать строку. При выключенном режиме — пустышка.

    Отдаёт словарь счётчиков: величина бывает известна только по ходу
    блока (число строк в пересборке дерева). Строка пишется и тогда,
    когда блок бросил исключение: замер — диагностика, и потерять его
    на отказе значило бы потерять ровно тот случай, ради которого
    режим и включён.

    `stage` обязан быть литералом ровно с текстом операции, а не строкой,
    собранной из данных (путь, имя базы, строка соединения) — mypy это
    не проверит: типы гарантируют целочисленность только `**counters`,
    `stage: str` пропустит что угодно. Ответственность за это несёт
    вызывающий код (инвариант 5).
    """  # noqa: RUF002
    if not _enabled:
        yield dict(counters)
        return
    values = dict(counters)
    started = time.monotonic()
    try:
        yield values
    finally:
        elapsed = int((time.monotonic() - started) * 1000)
        tail = "".join(f", {key}={value}" for key, value in values.items())
        _log.info("%s: %d мс%s", stage, elapsed, tail)


def reset_for_tests() -> None:
    """Вернуть логгер в исходное состояние целиком. Только для тестов.

    До этой правки (находка финального ревью ветки) функция не возвращала
    ни `propagate`, ни уровень: `setup()` меняет оба при первом успешном
    вызове, а обратно их не возвращал никто. Из-за этого `propagate`
    навсегда оставался `False` после первого же `setup()` в сессии
    тестов — и тест на саму находку (перенос `propagate = False` в начало
    `setup()`, до попытки создать файл) не смог бы отличить починку от
    случайного совпадения: `False` было бы и без неё, по наследству
    от более раннего теста.
    """  # noqa: RUF002
    global _enabled
    for handler in list(_log.handlers):
        _log.removeHandler(handler)
        handler.close()
    _log.propagate = True
    _log.setLevel(logging.NOTSET)
    _enabled = False
