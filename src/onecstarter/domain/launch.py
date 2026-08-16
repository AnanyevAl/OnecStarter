"""Выбор клиента и сборка командной строки запуска.

Командная строка собирается строкой, а не argv-списком: эталон — снятые
с реального процесса командные строки штатного стартера ([Ф] скил
platform-launch), побайтовое совпадение с ними проверяется тестами.
Секреты в аргументы не попадают: основной путь запуска — /IBName, при
котором платформа сама читает всё нужное из ibases.v8i.
"""  # noqa: RUF002

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from onecstarter.domain.connect import parse_connect
from onecstarter.domain.version import Installation, VersionNumber
from onecstarter.security.secrets import is_secret_key


class ClientKind(Enum):
    THIN = "thin"
    THICK = "thick"
    DESIGNER = "designer"


@dataclass(frozen=True)
class ClientConvention:
    min_version: VersionNumber
    bin_dir: str
    executables: Mapping[ClientKind, str]


def convention_for(
    version: VersionNumber, conventions: Sequence[ClientConvention]
) -> ClientConvention | None:
    best: ClientConvention | None = None
    for convention in conventions:
        if version < convention.min_version:
            continue
        if best is None or convention.min_version > best.min_version:
            best = convention
    return best


@dataclass(frozen=True)
class ClientChoice:
    client: ClientKind
    auto_check_mode: bool


_APP_CLIENTS = {"thinclient": ClientKind.THIN, "thickclient": ClientKind.THICK}


def choose_client(
    app: str | None,
    default_app: str | None,
    forced: ClientKind | None = None,
) -> ClientChoice:
    if forced is not None:
        return ClientChoice(forced, auto_check_mode=False)
    explicit = _client_from_app(app)
    if explicit is not None:
        # [Ф] T-02.6: при явном App стартер не передаёт /AppAutoCheckMode.
        return ClientChoice(explicit, auto_check_mode=False)
    fallback = _client_from_app(default_app) or ClientKind.THIN
    return ClientChoice(fallback, auto_check_mode=True)


def is_web_client_app(app: str | None) -> bool:
    """Называет ли значение `App` веб-клиент.

    Веб-клиенту не соответствует исполняемый файл, поэтому сценарий запуска
    обязан отсеять такую запись до сборки команды.
    """  # noqa: RUF002
    return app is not None and app.casefold() == "webclient"


def _client_from_app(app: str | None) -> ClientKind | None:
    if app is None:
        return None
    if is_web_client_app(app):
        raise ValueError("App=WebClient запускается браузером, а не исполняемым файлом")  # noqa: RUF001
    return _APP_CLIENTS.get(app.casefold())


def quote_launch_value(value: str) -> str:
    doubled = value.replace('"', '""')
    return f'"{doubled}"'


def build_arguments(
    client: ClientKind,
    *,
    ib_name: str | None = None,
    connect: str | None = None,
    auto_check_version: bool,
    auto_check_mode: bool,
) -> str:
    if (ib_name is None) == (connect is None):
        raise ValueError("Нужно ровно одно из: ib_name, connect")
    mode = "DESIGNER" if client is ClientKind.DESIGNER else "ENTERPRISE"
    parts = [mode]
    if ib_name is not None:
        parts.append(f"/IBName{quote_launch_value(ib_name)}")
    else:
        if connect is None:
            # Недостижимо: выше проверено «ровно одно из ib_name, connect».
            # Ветка нужна только чтобы mypy сузил connect до str.
            raise ValueError("Нужно ровно одно из: ib_name, connect")
        # Паритетный страж — тот же, что уже стоит в `redact_connect`
        # (security/secrets.py). Круг правок 2 (ревью задачи 9, item 1):  # noqa: RUF003
        # непарная кавычка сдвигает границы фрагментов так, что имя секретного
        # ключа может оказаться внутри значения СОСЕДНЕГО (несекретного)
        # фрагмента — `parse_connect` в этом случае не находит его отдельным  # noqa: RUF003
        # именем в принципе, сканирование по именам бессильно. Проверка идёт
        # до разбора и не зависит от его качества — защита от утечки пароля  # noqa: RUF003
        # в argv (скил platform-launch, «Пароль в командной строке —
        # неустранимая утечка») не должна держаться на корректности парсера.
        if connect.count('"') % 2:
            raise ValueError(
                "Строка соединения с непарной кавычкой не передаётся через "  # noqa: RUF001
                "командную строку — разбор фрагментов на секреты в ней недостоверен"
            )
        secrets = [
            fragment.name
            for fragment in parse_connect(connect)
            if is_secret_key(fragment.name)
        ]
        if secrets:
            # Сообщение несёт только имена ключей, значения — никогда.
            raise ValueError(
                f"Пароль ({', '.join(secrets)}) в строке соединения не передаётся "
                "через командную строку — используйте /IBName или уберите эти ключи"
            )
        # [Ф] T-05.1: значение прижато к ключу, кавычки внутри удвоены —
        # форма снята с реального запуска, путь с пробелом работает.  # noqa: RUF003
        parts.append(f"/IBConnectionString{quote_launch_value(connect)}")
    parts.append("/AppAutoCheckVersion" if auto_check_version else "/AppAutoCheckVersion-")
    if auto_check_mode:
        parts.append("/AppAutoCheckMode")
    return " ".join(parts)


@dataclass(frozen=True)
class LaunchCommand:
    executable: Path
    arguments: str

    @property
    def command_line(self) -> str:
        return f'"{self.executable}" {self.arguments}'


def build_launch_command(
    installation: Installation,
    convention: ClientConvention,
    client: ClientKind,
    arguments: str,
) -> LaunchCommand:
    executable = installation.path / convention.bin_dir / convention.executables[client]
    return LaunchCommand(executable=executable, arguments=arguments)
