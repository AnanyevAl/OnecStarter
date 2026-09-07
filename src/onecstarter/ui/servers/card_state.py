"""Чистые функции карточки профиля: состояние, тексты, цвета, стили.

Вынесено из `ui/servers/view.py` (долг T-12, п. 10): файл вьюхи перевалил
за тысячу строк, а этот блок ни от чего в ней не зависит — ни одной ссылки
на `self`, ни одного виджета, только `ServerStatus`/`ServerProfile` на входе
и строка либо `CardState` на выходе. Тот же приём, что у
`ui/dialogs/confirm.py::group_removal_question` в разделе «Базы»: текст,
который нужно проверять табличными тестами, живёт отдельно от того, кто его
показывает.

Имена публичные (без подчёркивания) намеренно: модуль и есть их дом,
а `app.py` пользуется `card_state()` напрямую (долг T-12, п. 5) — приватное
имя, импортируемое из чужого модуля, лгало бы о границе.

Qt здесь нет и не появляется — кроме `Palette`, которая сама голый датакласс
цветов (`ui/theme.py`). Инвариант 1 `CLAUDE.md` это не нарушает: модуль лежит
в `ui/`, просто не тянет виджеты.
"""  # noqa: RUF002

from enum import Enum

from onecstarter.domain.server import ServerProfile
from onecstarter.domain.server_match import ForeignServer
from onecstarter.services.servers import ServerStatus
from onecstarter.ui.theme import Palette

__all__ = [
    "CardState",
    "button_state",
    "card_border_style",
    "card_state",
    "detail_line",
    "flags_text",
    "foreign_text",
    "removal_question",
    "status_colour",
    "status_text",
]

_RANGE_DASH = "–"  # тире мокапа («1560–1591»), не дефис  # noqa: RUF001, RUF003

_FOREIGN_TOOLTIP = (
    "Сервер запущен не лаунчером — остановить его "  # noqa: RUF001
    "можно только там, где он был запущен"
)


class CardState(Enum):
    """Четыре взаимоисключающих состояния карточки профиля (T-12, задача 5)."""

    RUNNING = "running"    # наш ragent жив в Job
    REMNANTS = "remnants"  # Job не пуст, ragent в нём нет
    FOREIGN = "foreign"    # Job пуст, снимок нашёл совпавший ragent — только показ (решение 4)
    STOPPED = "stopped"


def card_state(status: ServerStatus) -> CardState:
    """Состояние карточки: Job профиля главнее снимка процессов (T-12 §3).

    Порядок проверок и есть решение заказчика 4 от 29.08.2026: снимок
    (`processes`) спрашивается ПОСЛЕДНИМ и отвечает только на вопрос
    «есть ли на нашем каталоге кластера чужой `ragent`». Наш он или нет,
    командная строка не говорит — говорит только наличие PID в НАШЕМ Job.
    Поэтому «работает» = порождённый нами `ragent` жив в Job, а совпавший
    процесс без Job — `FOREIGN`, показ без управления.
    """  # noqa: RUF002
    if status.spawned_pid is not None and status.spawned_pid in status.job_pids:
        return CardState.RUNNING
    if status.job_pids:
        return CardState.REMNANTS
    if status.processes:
        return CardState.FOREIGN
    return CardState.STOPPED


def status_text(status: ServerStatus) -> str:
    """Текст статуса карточки — состояние Job главнее разрешения версии.

    IMPORTANT 3 (финальное ревью ветки, правка спеки §3.1; в T-12 — «Job
    главнее версии»): раньше `resolved is None` проверялся первым
    и подавлял «работает» даже у живого сервера — карточка работающего
    профиля с неразрешённой версией (например, после удаления установки,
    которой он был запущен) показывала «версия не установлена», хотя
    остановка версии не требует вовсе. Порядок теперь: сначала состояние
    (`card_state`), «версия не установлена» — только для `STOPPED`.
    """  # noqa: RUF002
    state = card_state(status)
    if state is CardState.RUNNING:
        return f"работает · PID {status.spawned_pid}"
    if state is CardState.REMNANTS:
        pids = ", ".join(str(pid) for pid in status.job_pids)
        return f"остановлен · остатки прошлого запуска: PID {pids}"
    if state is CardState.FOREIGN:
        pids = ", ".join(str(p.pid) for p in status.processes)
        return f"работает (запущен не лаунчером) · PID {pids}"
    if status.resolved is None:
        return "версия не установлена"
    return "остановлен"


def status_colour(status: ServerStatus, palette: Palette) -> str:
    """Цвет статуса — тот же приоритет, что `status_text` (IMPORTANT 3).

    Остатки прошлого запуска красятся problem, а не dim: профиль
    «остановлен», но его порты заняты собственными недобитыми процессами —
    это состояние, требующее действия, а не спокойный простой.
    """  # noqa: RUF002
    state = card_state(status)
    if state in (CardState.RUNNING, CardState.FOREIGN):
        return palette.accent
    if state is CardState.REMNANTS or status.resolved is None:
        return palette.problem
    return palette.text_dim


def button_state(status: ServerStatus) -> tuple[str, bool, str]:
    """Текст, активность и подсказка кнопки — тот же приоритет, что `status_text`.

    Остановка не требует разрешённой версии вовсе (`stop` закрывает Job,
    установка ему не нужна) — «Остановить» активна независимо от
    `resolved`. У `FOREIGN` кнопка остаётся «Остановить», но НЕАКТИВНА
    с подсказкой (решение заказчика 4): чужой процесс мы не остановим,
    и обещать это активной кнопкой значило бы гнать пользователя
    в гарантированный отказ. У `REMNANTS`/`STOPPED` — «Запустить»,
    неактивная, только если версия не разрешилась: запускать нечем.
    """  # noqa: RUF002
    state = card_state(status)
    if state is CardState.RUNNING:
        return "Остановить", True, ""
    if state is CardState.FOREIGN:
        return "Остановить", False, _FOREIGN_TOOLTIP
    return "Запустить", status.resolved is not None, ""


def flags_text(profile: ServerProfile) -> str:
    parts: list[str] = []
    if profile.debug:
        parts.append("-debug")
    if profile.http:
        parts.append("-http")
    extra = profile.extra_args.strip()
    if extra:
        parts.append(extra)
    return " ".join(parts)


def detail_line(status: ServerStatus) -> str:
    profile = status.profile
    resolved_text = str(status.resolved) if status.resolved is not None else "?"
    ports = (
        f"порты {profile.port} / {profile.regport} / "
        f"{profile.range_start}{_RANGE_DASH}{profile.range_end}"
    )
    line = f"{profile.version} → {resolved_text} · {ports}"
    flags = flags_text(profile)
    return f"{line} · {flags}" if flags else line


def removal_question(profile: ServerProfile, state: CardState) -> str:
    """Текст вопроса на удаление профиля — свой на каждое состояние карточки.

    Решение заказчика 3 от 29.08.2026 отменило решение 8 T-08: удаление
    профиля, запущенного НАМИ, теперь его и останавливает, и вопрос обязан
    говорить именно это — «продолжит работать» стало бы прямым враньём
    (`ServersWorkspace.remove_profile` закрывает Job до удаления записи).
    То же и с остатками: они не переживут удаления, значит вопрос —
    про гашение. Прежняя формулировка уцелела ровно для `FOREIGN`: чужой
    `ragent` действительно продолжит работать и станет виден в «Других
    серверах на машине» — Job у него нет, и трогать его нам нечем.
    """  # noqa: RUF002
    if state is CardState.RUNNING:
        return (
            f"Сервер «{profile.name}» работает — остановить его и удалить профиль?"  # noqa: RUF001
        )
    if state is CardState.REMNANTS:
        return (
            f"У профиля «{profile.name}» остались процессы прошлого запуска — "  # noqa: RUF001
            "погасить их и удалить профиль?"
        )
    if state is CardState.FOREIGN:
        return (
            f"Удалить профиль «{profile.name}»? Сервер запущен не лаунчером и продолжит "
            "работать — он перейдёт в «Другие серверы на машине»."
        )
    return f"Удалить профиль «{profile.name}» из списка серверов?"


def card_border_style(is_selected: bool, palette: Palette) -> str:
    """Рамка карточки — `palette.accent`, только у выделенной (задача 5, T-10).

    Ширина рамки одна и та же в обоих состояниях (`transparent` у
    невыделенной) — иначе выделение сдвигало бы содержимое карточки
    на толщину рамки.
    """  # noqa: RUF002
    colour = palette.accent if is_selected else "transparent"
    return f"QWidget#ServerCard {{ border: 2px solid {colour}; border-radius: 4px; }}"


def foreign_text(entry: ForeignServer) -> str:
    """Строка блока «Другие серверы на машине»: полная или ограниченная форма ([Ф] В1).

    Ограниченная — когда командная строка недоступна (`params is None`,
    чужой пользователь или служба): без портов и каталога, версия — только
    если виден путь исполняемого файла (`executable`, доступен без
    повышения даже для SYSTEM-процессов, см. `process_scan.py`).
    """  # noqa: RUF002
    if entry.params is None:
        text = (
            f"PID {entry.process.pid} · нет доступа к командной строке "
            "(другой пользователь или служба)"
        )
        return f"{text} · {entry.version}" if entry.version is not None else text
    version_text = str(entry.version) if entry.version is not None else "?"
    if entry.params.port is not None and entry.params.regport is not None:
        ports = f"порты {entry.params.port} / {entry.params.regport}"
    else:
        ports = "порты ?"
    directory = entry.params.cluster_dir or "?"
    return f"{version_text} · {ports} · {directory} · PID {entry.process.pid}"
