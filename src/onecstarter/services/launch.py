"""Сценарий запуска базы: команда → процесс или браузер.

Своей логики почти нет — склеиваются готовые слои. Запуск идёт по /IBName:
платформа сама читает из ibases.v8i ключи WA, AdditionalParameters и прочие
([Ф] скил platform-launch), а секреты из строки соединения не попадают
в argv. Базы из общих списков запускаются так же — [Ф] T-05.2: клиент
находит имя из `CommonInfoBases` и материализует запись в ibases.v8i.

Ошибки поднимаются до порождения процесса: неустановленная версия видна
пользователю заранее, а не после падения клиента.
"""  # noqa: RUF002

import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from onecstarter.domain.connect import ConnectKind, find_fragment, parse_connect
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import (
    ClientChoice,
    ClientConvention,
    ClientKind,
    LaunchCommand,
    build_arguments,
    build_launch_command,
    choose_client,
    convention_for,
    is_web_client_app,
)
from onecstarter.domain.selection import ResolutionSource, resolve_version
from onecstarter.domain.version import Installation, VersionNumber
from onecstarter.platform_1c.process import spawn as spawn_process
from onecstarter.security.secrets import redact_connect
from onecstarter.services.errors import LaunchError
from onecstarter.services.model import InfobaseItem

__all__ = ["LaunchError", "LaunchKind", "LaunchOutcome", "launch_infobase"]


class LaunchKind(Enum):
    PROCESS = "process"
    BROWSER = "browser"


@dataclass(frozen=True)
class LaunchOutcome:
    kind: LaunchKind
    client: ClientKind | None
    command_line: str | None
    url: str | None
    pid: int | None
    version: VersionNumber | None


def launch_infobase(
    item: InfobaseItem,
    *,
    installations: Sequence[Installation],
    cfg_rules: Sequence[DefaultVersionRule],
    conventions: Sequence[ClientConvention],
    default_app: str | None,
    forced_client: ClientKind | None = None,
    spawn: Callable[[LaunchCommand], int] = spawn_process,
    open_url: Callable[[str], bool] = webbrowser.open,
) -> LaunchOutcome:
    """Запустить базу: процесс клиента или браузер для веб-базы.

    Уникальность имени в списке проверяет вызывающий: запуск идёт по `/IBName`,
    а платформа при нескольких базах с одним именем прекращает запуск с ошибкой
    (скил platform-launch). Здесь запись уже одна и вне списка, определить
    неоднозначность по ней нельзя.
    """  # noqa: RUF002
    if item.is_group or item.connect is None:
        raise LaunchError(f"«{item.name}» — группа, а не информационная база")  # noqa: RUF001

    if item.kind is ConnectKind.WEB:
        return _launch_web(item, open_url)

    # App=WebClient на не-веб базе отсеивается до разбора версии: исполняемого
    # файла у веб-клиента нет, а открывать браузером нечего — строка соединения  # noqa: RUF003
    # не ws=. Ошибка про версию тут увела бы пользователя не туда.
    choice = _choose_client(item, default_app, forced_client)

    resolution = resolve_version(
        item.requested_version,
        item.section_default_version,
        cfg_rules,
        [installation.version for installation in installations],
    )
    if resolution.version is None:
        raise LaunchError(_version_problem(item, resolution.source))
    installation = next(
        installation
        for installation in installations
        if installation.version == resolution.version
    )
    convention = convention_for(resolution.version, conventions)
    if convention is None:
        raise LaunchError(
            f"Для версии {resolution.version} нет соглашения раскладки в реестре версий"
        )
    arguments = build_arguments(
        choice.client,
        ib_name=item.name,
        auto_check_version=False,
        auto_check_mode=choice.auto_check_mode,
    )
    command = build_launch_command(installation, convention, choice.client, arguments)
    try:
        pid = spawn(command)
    except OSError as error:
        # Спека 4a, §3: командная строка в сообщении — для «скопировать
        # для отчёта». Секретов в ней нет: запуск идёт по /IBName.
        raise LaunchError(
            f"Не удалось запустить клиента для «{item.name}»: {error}.\n"  # noqa: RUF001
            f"Команда: {command.command_line}"
        ) from error
    return LaunchOutcome(
        kind=LaunchKind.PROCESS,
        client=choice.client,
        command_line=command.command_line,
        url=None,
        pid=pid,
        version=resolution.version,
    )


def _choose_client(
    item: InfobaseItem, default_app: str | None, forced_client: ClientKind | None
) -> ClientChoice:
    """Выбрать клиента, переведя отказ домена в ошибку слоя.

    Единственный отказ `choose_client` — `App=WebClient`: у веб-клиента нет
    исполняемого файла. Какое из двух значений `App` до него дошло, решает
    сам `choose_client`, поэтому источник определяется по факту, а порядок
    разрешения здесь не дублируется.
    """  # noqa: RUF002
    try:
        return choose_client(item.app, default_app, forced_client)
    except ValueError as error:
        source = "в записи" if is_web_client_app(item.app) else "умолчанием машины"
        raise LaunchError(
            f"Для «{item.name}» {source} задан App=WebClient, но строка соединения "
            "не ws= — веб-клиент запускать нечем"
        ) from error


def _launch_web(item: InfobaseItem, open_url: Callable[[str], bool]) -> LaunchOutcome:
    # Форма URL веб-базы [не проверено]: берём значение ws как есть.
    url = find_fragment(parse_connect(item.connect or ""), "ws")
    if not url:
        raise LaunchError(f"У «{item.name}» не найден адрес публикации (ws)")  # noqa: RUF001
    if not open_url(url):
        # webbrowser.open возвращает False, когда браузер открыть не удалось.
        # Игнорируя результат, мы записали бы неоткрывшуюся базу в историю как
        # успешно запущенную. URL в сообщение не идёт: он может нести учётные
        # данные (ws="http://user:pass@host/").
        raise LaunchError(
            f"Не удалось открыть браузер для «{item.name}»: "  # noqa: RUF001
            "проверьте браузер по умолчанию"
        )
    return LaunchOutcome(
        kind=LaunchKind.BROWSER, client=None, command_line=None, url=url, pid=None, version=None
    )


def _version_problem(item: InfobaseItem, source: ResolutionSource) -> str:
    safe_connect = redact_connect(item.connect or "")
    if source is ResolutionSource.INVALID_REQUEST:
        return f"У «{item.name}» неразбираемая версия «{item.requested_version}» ({safe_connect})"  # noqa: RUF001
    return (
        f"Для «{item.name}» запрошена версия {item.requested_version}, "
        f"на этой машине она не установлена ({safe_connect})"
    )
