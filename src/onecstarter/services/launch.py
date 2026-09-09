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

from onecstarter.domain.connect import find_fragment, parse_connect
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.launch import (
    ClientConvention,
    ClientKind,
    Credentials,
    LaunchCommand,
    LaunchPlan,
    LaunchRefusal,
    LaunchTarget,
    RefusalReason,
    build_arguments,
    build_launch_command,
    choose_launch_plan,
    convention_for,
    is_web_client_app,
)
from onecstarter.domain.selection import ResolutionSource, resolve_version
from onecstarter.domain.version import Installation, VersionNumber
from onecstarter.platform_1c.process import spawn as spawn_process
from onecstarter.security.secrets import redact_arguments, redact_connect
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
    web_default_is_browser: bool = False,
    forced_target: LaunchTarget | None = None,
    spawn: Callable[[LaunchCommand], int] = spawn_process,
    open_url: Callable[[str], bool] = webbrowser.open,
    credentials: Credentials | None = None,
) -> LaunchOutcome:
    """Запустить базу: процесс клиента или браузер.

    Канал решает `App` записи, а не вид строки соединения (спека v2.3, §3):
    веб-база с `App=ThinClient` уходит тонким клиентом по `/IBName`, а браузер
    открывается только там, где план сказал «клиента нет». До v2.3 здесь
    стояло короткое замыкание `kind is WEB -> браузер`, из-за которого
    `App`, разовый выбор клиента и учётные данные до веб-базы не доходили.

    Уникальность имени в списке проверяет вызывающий: запуск идёт по `/IBName`,
    а платформа при нескольких базах с одним именем прекращает запуск с ошибкой
    (скил platform-launch). Здесь запись уже одна и вне списка, определить
    неоднозначность по ней нельзя.
    """  # noqa: RUF002
    if item.is_group or item.connect is None:
        raise LaunchError(f"«{item.name}» — группа, а не информационная база")  # noqa: RUF001

    plan = _plan(item, default_app, web_default_is_browser, forced_target)
    if plan.client is None:
        return _launch_web(item, open_url)

    installation, version = _installation_for(item, plan, installations, cfg_rules)
    convention = convention_for(installation.version, conventions)
    if convention is None:
        raise LaunchError(
            f"Для версии {installation.version} нет соглашения раскладки в реестре версий"
        )
    arguments = build_arguments(
        plan.client,
        ib_name=item.name,
        auto_check_version=plan.auto_check_version,
        auto_check_mode=plan.auto_check_mode,
        credentials=credentials,
    )
    command = build_launch_command(installation, convention, plan.client, arguments)
    try:
        pid = spawn(command)
    except OSError as error:
        # Спека 4a, §3: командная строка в сообщении — для «скопировать
        # для отчёта». С v2.2 в аргументах может быть /P — показывается  # noqa: RUF003
        # только редактированная форма (спека v2.2, §6).
        raise LaunchError(
            f"Не удалось запустить клиента для «{item.name}»: {error}.\n"  # noqa: RUF001
            f"Команда: \"{command.executable}\" {redact_arguments(command.arguments)}"
        ) from error
    return LaunchOutcome(
        kind=LaunchKind.PROCESS,
        client=plan.client,
        command_line=f'"{command.executable}" {redact_arguments(command.arguments)}',
        url=None,
        pid=pid,
        version=version,
    )


_REFUSAL_TEXTS = {
    RefusalReason.THICK_TO_WEB: (
        "«{name}» опубликована на веб-сервере (ws=): её открывает тонкий клиент "
        "или браузер, толстый клиент и Конфигуратор к ней не подключаются"
    ),
    RefusalReason.WEB_APP_THICK: (
        "Для «{name}» в записи задан App=ThickClient, но база опубликована "
        "на веб-сервере (ws=) — толстый клиент к ней не подключается"
    ),
    RefusalReason.BROWSER_FOR_SERVER: (
        "«{name}» — серверная база, браузером её не открыть: в браузере "
        "работают только базы, опубликованные на веб-сервере"
    ),
    RefusalReason.BROWSER_FOR_FILE: (
        "«{name}» — файловая база, браузером её не открыть: в браузере "
        "работают только базы, опубликованные на веб-сервере"
    ),
    RefusalReason.BROWSER_FOR_UNKNOWN: (
        "У «{name}» не разобран вид размещения, браузером её не открыть: "  # noqa: RUF001
        "в браузере работают только базы, опубликованные на веб-сервере"
    ),
}


def _plan(
    item: InfobaseItem,
    default_app: str | None,
    web_default_is_browser: bool,
    forced_target: LaunchTarget | None,
) -> LaunchPlan:
    """План запуска; оба вида отказа переводятся в `LaunchError` здесь.

    Отказов два происхождения. Типизированный `LaunchRefusal` — новые причины
    вехи v2.3 (спека §3): их пять, и различить их вызывающему можно только
    по `reason`. `ValueError` из `choose_client` — прежний путь `App=WebClient`
    у не-ws записи, он не тронут вехой и сохраняет своё сообщение.
    """  # noqa: RUF002
    try:
        outcome = choose_launch_plan(
            item.kind,
            item.app,
            default_app,
            web_default_is_browser=web_default_is_browser,
            forced=forced_target,
        )
    except ValueError as error:
        source = "в записи" if is_web_client_app(item.app) else "умолчанием машины"
        raise LaunchError(
            f"Для «{item.name}» {source} задан App=WebClient, но строка соединения "
            "не ws= — веб-клиент запускать нечем"
        ) from error
    if isinstance(outcome, LaunchRefusal):
        raise LaunchError(_REFUSAL_TEXTS[outcome.reason].format(name=item.name))
    return outcome


def _installation_for(
    item: InfobaseItem,
    plan: LaunchPlan,
    installations: Sequence[Installation],
    cfg_rules: Sequence[DefaultVersionRule],
) -> tuple[Installation, VersionNumber | None]:
    """Установка, из которой порождать процесс, и версия для `LaunchOutcome`.

    При `auto_check_version` версию выбирает платформа по ответу сервера
    (**[Ф]** T-05.16 № 4, 7): порождаем максимальную установленную, наш
    процесс завершается за секунды, платформа поднимает нужную. Возвращаемая
    версия при этом `None` — какая запустится, мы не знаем, и врать в UI нельзя.
    """
    if plan.auto_check_version:
        if not installations:
            raise LaunchError(
                f"Для «{item.name}» не найдено ни одной установленной версии платформы"
            )
        return max(installations, key=lambda installation: installation.version), None

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
    return installation, resolution.version


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
