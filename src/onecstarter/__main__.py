"""Точка входа gui-скрипта onecstarter (pyproject: onecstarter.__main__:main).

Три режима: без аргументов — обычное окно (с `--autostart` — то же, но окно
не показывается: программа живёт в трее), с `--ib-name <имя>` — запуск
одной базы и выход, с `--smoke <каталог>` — самопроверка собранного
экземпляра (задача 10 запускает её из `build/smoke.py`). Режим `--ib-name`
нужен ярлыкам с рабочего стола (задача 17): ярлык несёт имя базы, а не
ключ привязки, потому что ключ меняется, когда записи дописывается `ID`.

`PySide6` импортируется внутри `_dispatch`, а не на уровне модуля: разбор
аргументов обязан оставаться проверяемым без Qt.

Лог и faulthandler настраиваются в `main` до вызова `_dispatch` — то есть
до первого импорта `ui` — намеренно: спека T-04.6 требует поймать даже
отказ самого импорта (например, `ModuleNotFoundError` из повреждённой
сборки), а без лога, открытого заранее, такой отказ ушёл бы в никуда —
у оконной сборки (pythonw.exe) нет ни консоли, ни видимого stderr.
"""  # noqa: RUF002

import logging
import os
import sys
from collections.abc import Sequence

from onecstarter import diagnostics as diagnostics  # реэкспорт: entry.diagnostics в тестах

IB_NAME_OPTION = "--ib-name"
SMOKE_OPTION = "--smoke"
AUTOSTART_OPTION = "--autostart"


def parse_smoke_dir(argv: Sequence[str]) -> str | None:
    """Каталог самопроверки из `--smoke`. `None` — ключа нет, режим не наш.

    Поддерживаются те же две формы записи, что у `--ib-name`: `--smoke DIR`
    и `--smoke=DIR`. Ключ без значения даёт пустую строку, а не `None` —
    тот же довод, что у `parse_ib_name`: молча уйти в обычное окно значило
    бы спрятать опечатку в вызове. Свой разбор, а не `argparse`, по той же
    причине — у оконной сборки (pythonw.exe) нет консоли, а `argparse`
    на неизвестный ключ печатает справку в stderr и зовёт `sys.exit`.
    """  # noqa: RUF002
    prefix = f"{SMOKE_OPTION}="
    for index, argument in enumerate(argv):
        if argument == SMOKE_OPTION:
            following = argv[index + 1 :]
            return following[0] if following else ""
        if argument.startswith(prefix):
            return argument[len(prefix) :]
    return None


def parse_ib_name(argv: Sequence[str]) -> str | None:
    """Имя базы из `--ib-name`. `None` — ключа нет, нужно обычное окно.

    Поддерживаются обе формы записи: `--ib-name Демо` и `--ib-name=Демо`.
    Ключ без значения даёт пустую строку, а не `None`: «запустить неизвестно
    что» и «показать окно» — разные намерения, и молча открыть окно значило
    бы спрятать от пользователя опечатку в ярлыке.

    Свой разбор, а не `argparse`: у оконной сборки нет консоли, а `argparse`
    на неизвестный ключ печатает справку в stderr и зовёт `sys.exit` — оба
    действия в сборке поверх pythonw.exe не видны пользователю вовсе.
    """  # noqa: RUF002
    prefix = f"{IB_NAME_OPTION}="
    for index, argument in enumerate(argv):
        if argument == IB_NAME_OPTION:
            following = argv[index + 1 :]
            return following[0] if following else ""
        if argument.startswith(prefix):
            return argument[len(prefix) :]
    return None


def has_autostart_flag(argv: Sequence[str]) -> bool:
    """Запуск при входе в Windows: окно не показывается (спека §3.4).

    Флаг без значения, поэтому сравнение точное: `--autostart-something`
    нашим ключом не является и молча тихий старт не включает.
    """
    return AUTOSTART_OPTION in argv


def main(argv: Sequence[str] | None = None) -> int:
    """Настроить диагностику и поймать всё, что уйдёт из `_dispatch`.

    Молчаливый отказ старта исключается как класс (спека T-04.6): что бы
    ни случилось внутри `_dispatch` — включая отказ самого импорта `ui` —
    пользователь увидит системное окно, а в лог попадёт трассировка.
    """  # noqa: RUF002
    arguments = list(sys.argv[1:] if argv is None else argv)
    log_path = diagnostics.setup_logging(os.environ)
    diagnostics.enable_faulthandler(os.environ)
    try:
        return _dispatch(arguments)
    except Exception:
        logging.getLogger("onecstarter").exception("необработанная ошибка старта")
        details = f"\n\nПодробности: {log_path}" if log_path else ""  # noqa: RUF001
        diagnostics.show_fatal_error(
            "OneCStarter не смог запуститься из-за внутренней ошибки." + details
        )
        return 1


def _dispatch(arguments: list[str]) -> int:
    """Выбор режима: самопроверка, запуск одной базы или обычное окно.

    `--smoke` проверяется первым: он определён независимо от `--ib-name`,
    и порядок проверки не должен зависеть от того, в каком порядке ключи
    перечислены в аргументах вызова.
    """
    smoke_dir = parse_smoke_dir(arguments)
    if smoke_dir is not None:
        if not smoke_dir.strip():
            logging.getLogger("onecstarter").error("--smoke указан без каталога")
            return 1
        from onecstarter.ui.app import run_smoke

        return run_smoke(smoke_dir, os.environ)

    name = parse_ib_name(arguments)
    if name is None:
        from onecstarter.ui.app import main as show_window

        return show_window(start_hidden=has_autostart_flag(arguments))
    from onecstarter.ui.app import run_launch

    return run_launch(name, os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
