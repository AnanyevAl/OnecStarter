"""Консоль администрирования кластера: текущая версия, перерегистрация, открытие.

Вынесено из `services/servers.py` (долг T-12, п. 10). Причина не в длине
файла, а в связности: этот блок не делит с остальным координатором ничего —
ни `_jobs`, ни `_spawned`, ни снимок процессов, ни список профилей. Он про
MMC-консоль и запись в HKLM, а не про жизненный цикл `ragent`. Три инъекции
(`registered_radmin`/`run_elevated`/`open_file`) тоже нужны были только ему.

`ServersWorkspace` остаётся фасадом: её `current_console_version`/
`register_console`/`open_console` теперь однострочные делегаты. Так UI
(`_ConsoleWorkspace` в `ui/app.py`) и существующие тесты не задеты вовсе —
переезд логики не обязан ломать границу, которая работает.

§7 спеки: `run_elevated` — единственная точка UAC-повышения во всём слое,
и зовётся она ТОЛЬКО из `register_console`, по явному действию пользователя.
Ни конструктор, ни чтение версии её не трогают (чтение HKLM повышения
не требует — [Ф] Г2).
"""  # noqa: RUF002

import os
from collections.abc import Callable
from pathlib import Path

from onecstarter.domain.server import ServerConvention
from onecstarter.domain.server_match import version_from_exe_path
from onecstarter.domain.version import VersionNumber
from onecstarter.platform_1c import console, elevation
from onecstarter.platform_1c.elevation import ElevationDeclinedError
from onecstarter.platform_1c.server_discovery import ServerInstallation, console_path
from onecstarter.services.errors import (
    ConsoleRegistrationDeclinedError,
    ConsoleRegistrationError,
    ServerError,
)

__all__ = ["ConsoleAdmin"]


class ConsoleAdmin:
    """Три операции над консолью администрирования; своего состояния не держит."""

    def __init__(
        self,
        *,
        run_elevated: Callable[[str, str], int] = elevation.run_elevated,
        open_file: Callable[[str], None] = os.startfile,
        registered_radmin: Callable[[], Path | None] = console.registered_radmin_path,
    ) -> None:
        self._run_elevated = run_elevated
        self._open_file = open_file
        self._registered_radmin = registered_radmin

    def current_version(self) -> VersionNumber | None:
        """Версия консоли, зарегистрированной СЕЙЧАС в реестре; `None` — не зарегистрирована.

        Чтение, не эффект UAC: `_registered_radmin` читает HKLM обычным
        пользователем ([Ф] Г2). Версия извлекается из пути `radmin.dll`
        (`<корень>\\<версия>\\bin\\radmin.dll`) той же функцией, что и для
        чужих ragent (`version_from_exe_path`, [Ф] В1) — путь до `radmin.dll`
        имеет ту же форму `<версия>\\bin\\<файл>`, что и до `ragent.exe`.

        Отказ ЧТЕНИЯ реестра (`OSError` не из семейства «ключа нет») наружу
        уходит как есть: подменять его на `None` значило бы сказать
        «не зарегистрирована» о том, чего мы не смогли прочитать. Показ
        такого отказа — забота UI (долг T-12, п. 11).
        """  # noqa: RUF002
        path = self._registered_radmin()
        if path is None:
            return None
        return version_from_exe_path(path)

    def register(self, target: ServerInstallation) -> None:
        """Перерегистрировать консоль на `radmin.dll` версии `target` — эффект с UAC.

        [Ф] Г2: одна команда `regsvr32 /s "<dll>"` без предварительного `/u`
        (CLSID стабильны между версиями, `register_arguments`). Отказ
        пользователя в диалоге UAC (`ElevationDeclinedError`) — штатный исход
        §7, не ошибка программы: транслируется в
        `ConsoleRegistrationDeclinedError`, UI обязан показать «версия консоли
        не изменена», а не сообщение об ошибке. Ненулевой код возврата
        `regsvr32` — настоящий сбой регистрации, код попадает в текст
        `ConsoleRegistrationError`, чтобы было что показать и с чем прийти
        в поддержку. Единственная точка входа для UAC-повышения во всём
        слое — см. докстринг модуля и защитный тест
        `test_nothing_registers_without_explicit_call`.
        """  # noqa: RUF002
        try:
            exit_code = self._run_elevated("regsvr32", console.register_arguments(target.radmin))
        except ElevationDeclinedError as error:
            raise ConsoleRegistrationDeclinedError(
                "Запрос прав администратора отклонён — версия консоли не изменена"
            ) from error
        if exit_code != 0:
            raise ConsoleRegistrationError(
                f"Регистрация консоли не удалась — regsvr32 вернул код {exit_code}"
            )

    def open(self, root: Path, convention: ServerConvention) -> None:
        """Открыть `.msc` консоли администрирования — тот же файл для всех версий.

        Путь строится от `root` (родитель каталогов версий) по `convention`
        (`console_path`, `platform_1c/server_discovery.py`); какая именно
        версия `radmin.dll` за ним стоит сейчас, определяет реестр, не этот
        вызов — см. `current_version`/`register`. `OSError` `os.startfile`
        (файл `.msc` отсутствует, нет ассоциации) переводится в `ServerError`
        (CRITICAL 1c, финальное ревью ветки) — тем же приёмом, что и
        `start`/`_save` в `ServersWorkspace`.
        """
        path = console_path(root, convention)
        try:
            self._open_file(str(path))
        except OSError as error:
            raise ServerError(f"Не удалось открыть консоль: {error}") from error  # noqa: RUF001
