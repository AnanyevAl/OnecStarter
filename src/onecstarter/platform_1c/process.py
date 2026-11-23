"""Порождение процессов клиентов 1С — отвязанных, не дочерних (для серверных
процессов, дочерних Job Object'у лаунчера, — `server_spawn.py`, T-10).

Командная строка передаётся строкой, а не списком: форма аргументов
(/IBName"...") снята с реального процесса штатного стартера, и Popen
не должен переигрывать её квотирование. Процесс отсоединяется: судьба
клиента 1С не связана с жизнью OneCStarter.
"""  # noqa: RUF002

import subprocess
import warnings

from onecstarter.domain.launch import LaunchCommand
from onecstarter.platform_1c.dll_search import clean_dll_search


def spawn(command: LaunchCommand) -> int:
    # Н1: клиент 1С не наследует путь DLL `_internal` собранной программы.  # noqa: RUF003
    with clean_dll_search():
        process = subprocess.Popen(
            command.command_line,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    pid = process.pid
    # Ожидание завершения намеренно пропущено: судьба клиента 1С не связана  # noqa: RUF003
    # с жизнью OneCStarter. Брошенный Popen издаёт в __del__ ResourceWarning  # noqa: RUF003
    # «subprocess N is still running» — подавляем его точечно при удалении.  # noqa: RUF003
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        del process
    return pid
