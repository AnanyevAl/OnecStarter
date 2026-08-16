"""Выбор версии платформы: чистая функция, всё окружение аргументами.

Гибрид наших и платформенных правил (спека 4a, §4): установленный
DefaultVersion побеждает маску даже вне её ([Ф] T-05.5), заданный но не
установленный — игнорируется молчаливо ([Р] конфликт с требованием
видимости, см. fallback).

fallback = что молча запустил бы штатный стартер — отдельная функция
по платформенным правилам. Расхождения между нашим выбором и fallback
показываются в UI.

fallback = None только при пустом пуле установленных версий; в остальных
случаях = платформенный выбор по данному пулу.

Исключение — INVALID_REQUEST (запрошенная версия не разбирается): туда
`_platform_choice` не доходит вообще (ветка возвращается раньше, чем он
вызывается), и `fallback` там — сразу `overall` (максимум установленной
пула). Это [Р] экстраполяция «максимум вообще», а не измеренное поведение:
как штатный стартер обходится с неразбираемой `Version`, экспериментально
не снималось.
"""  # noqa: RUF002

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from onecstarter.domain.default_version import DefaultVersionRule, substitute
from onecstarter.domain.version import VersionNumber, parse_version


class ResolutionSource(Enum):
    EXACT = "exact"
    SECTION_DEFAULT = "section-default"
    CFG_DEFAULT = "cfg-default"
    PREFIX_MAX = "prefix-max"
    MAX_INSTALLED = "max-installed"
    NOT_INSTALLED = "not-installed"
    INVALID_REQUEST = "invalid-request"


@dataclass(frozen=True)
class VersionResolution:
    version: VersionNumber | None
    source: ResolutionSource
    requested: VersionNumber | None
    fallback: VersionNumber | None


def resolve_version(
    requested: str | None,
    section_default: str | None,
    cfg_rules: Sequence[DefaultVersionRule],
    installed: Iterable[VersionNumber],
) -> VersionResolution:
    pool = sorted(set(installed))
    overall = pool[-1] if pool else None

    if requested is not None:
        try:
            wanted = parse_version(requested)
        except ValueError:
            # [Р] fallback = overall — экстраполяция, не измерение (см.  # noqa: RUF003
            # докстринг модуля): _platform_choice сюда не доходит, требует
            # разобранного wanted.
            return VersionResolution(None, ResolutionSource.INVALID_REQUEST, None, overall)
    else:
        wanted = None

    fallback = _platform_choice(wanted, section_default, cfg_rules, pool, overall)

    if wanted is None:
        if overall is not None:
            return VersionResolution(overall, ResolutionSource.MAX_INSTALLED, None, fallback)
        return VersionResolution(None, ResolutionSource.NOT_INSTALLED, None, None)

    if wanted.is_full:
        if wanted in pool:
            return VersionResolution(wanted, ResolutionSource.EXACT, wanted, fallback)
        return VersionResolution(None, ResolutionSource.NOT_INSTALLED, wanted, fallback)

    refined = _try_parse(section_default) if section_default is not None else None
    if refined is not None and refined.is_full and refined in pool:
        # [Ф] T-05.5: DefaultVersion побеждает неполную Version даже вне маски —
        # здесь мы следуем платформе (спека 4a, §4: это явное значение штатного
        # ключа, а не тихая подмена).  # noqa: RUF003
        return VersionResolution(refined, ResolutionSource.SECTION_DEFAULT, wanted, fallback)
    # [Р] спека 4a, §4: заданный, но не установленный DefaultVersion платформа  # noqa: RUF003
    # молча меняет на максимум вообще ([Ф] T-05.5). Тихую подмену не
    # воспроизводим: идём дальше по цепочке, расхождение показывает fallback.

    target = substitute(wanted, cfg_rules)
    if target is not None and target in pool:
        return VersionResolution(target, ResolutionSource.CFG_DEFAULT, wanted, fallback)

    matching = [version for version in pool if version.starts_with(wanted)]
    if matching:
        return VersionResolution(matching[-1], ResolutionSource.PREFIX_MAX, wanted, fallback)
    return VersionResolution(None, ResolutionSource.NOT_INSTALLED, wanted, fallback)


def _platform_choice(
    wanted: VersionNumber | None,
    section_default: str | None,
    cfg_rules: Sequence[DefaultVersionRule],
    pool: Sequence[VersionNumber],
    overall: VersionNumber | None,
) -> VersionNumber | None:
    """Что молча запустил бы штатный стартер — по правилам платформы.

    Отдельная логика, а не копия нашего выбора (спека 4a, §4): расхождения
    и есть то, что подсказка в UI обязана показать честно.

    - полная версия: установлена — она и есть; нет — максимум вообще ([Ф] T-02.8);
    - маска + DefaultVersion секции: установлен — побеждает даже вне маски,
      не установлен — максимум вообще, без возврата к префиксу ([Ф] T-05.5);
    - маска без DefaultVersion: подстановка cfg ([Д] ИТС, цель должна быть
      установлена — [Р] экстраполяция), затем максимум с префиксом ([Ф] T-02.1);
    - маска без совпадений и версия без запроса — максимум вообще
      ([Р] экстраполяция T-02.8, поведение платформы не снималось).

    DefaultVersion неполный или неразбираемый трактуется как отсутствующий —
    [Р], этот случай экспериментально не снимался.
    """  # noqa: RUF002
    if wanted is None:
        return overall
    if wanted.is_full:
        return wanted if wanted in pool else overall
    refined = _try_parse(section_default) if section_default is not None else None
    if refined is not None and refined.is_full:
        return refined if refined in pool else overall
    target = substitute(wanted, cfg_rules)
    if target is not None and target in pool:
        return target
    matching = [version for version in pool if version.starts_with(wanted)]
    if matching:
        return matching[-1]
    return overall


def _try_parse(text: str) -> VersionNumber | None:
    try:
        return parse_version(text)
    except ValueError:
        return None
