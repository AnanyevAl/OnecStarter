import pytest

from onecstarter.domain.default_version import DefaultVersionRule, default_version_rules
from onecstarter.domain.selection import ResolutionSource, resolve_version
from onecstarter.domain.version import VersionNumber, parse_version

# Реальный набор машины экспериментов T-02 (скил platform-launch, [Ф]).
INSTALLED = [
    parse_version(text)
    for text in (
        "8.3.10.2252",
        "8.3.18.1334",
        "8.3.20.2290",
        "8.3.22.1923",
        "8.3.25.1560",
        "8.3.25.1633",
        "8.3.27.2214",
    )
]

NO_RULES: list[DefaultVersionRule] = []
RULE_8_3_TO_22 = default_version_rules([("DefaultVersion", "8.3-8.3.22.1923")])
RULE_8_3_TO_MISSING = default_version_rules([("DefaultVersion", "8.3-8.3.24.100")])

CASES = [
    # (requested, section_default, cfg_rules, ожидаемая версия, источник)
    pytest.param(
        "8.3.25.1560", "8.3.25.1633", NO_RULES, "8.3.25.1560", ResolutionSource.EXACT,
        id="exact-beats-section-default",  # [Ф] T-02.2
    ),
    pytest.param(
        "8.3.25", "8.3.25.1560", NO_RULES, "8.3.25.1560", ResolutionSource.SECTION_DEFAULT,
        id="mask-refined-by-section-default",  # [Ф] T-02.2
    ),
    pytest.param(
        "8.3.25", None, NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="mask-resolves-to-prefix-max",  # [Ф] T-02.1
    ),
    pytest.param(
        "8.3.2", None, NO_RULES, None, ResolutionSource.NOT_INSTALLED,
        id="mask-8.3.2-does-not-catch-8.3.20",  # кортежи, не startswith
    ),
    pytest.param(
        "8.3.99.1", None, NO_RULES, None, ResolutionSource.NOT_INSTALLED,
        id="missing-full-version-is-visible",  # [Ф] T-02.8, штатный молчит
    ),
    pytest.param(
        "8.3", None, RULE_8_3_TO_22, "8.3.22.1923", ResolutionSource.CFG_DEFAULT,
        id="cfg-rule-beats-prefix-max",
    ),
    pytest.param(
        "8.3", None, RULE_8_3_TO_MISSING, "8.3.27.2214", ResolutionSource.PREFIX_MAX,
        id="cfg-rule-with-missing-target-skipped",
    ),
    pytest.param(
        "8.3.25", "8.3.22.1923", NO_RULES, "8.3.22.1923", ResolutionSource.SECTION_DEFAULT,
        id="section-default-outside-mask-wins",  # [Ф] T-05.5, спека 4a §4
    ),
    pytest.param(
        "8.3.25", "8.3.25.9999", NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="section-default-not-installed-ignored-for-our-choice",  # [Ф] T-05.5, спека 4a §4
    ),
    pytest.param(
        "8.3.25", "8.3", NO_RULES, "8.3.25.1633", ResolutionSource.PREFIX_MAX,
        id="section-default-mask-ignored",
    ),
    pytest.param(
        "8.3.25", "8.3.25.1560", RULE_8_3_TO_22, "8.3.25.1560", ResolutionSource.SECTION_DEFAULT,
        id="section-default-beats-cfg-rule",
    ),
    pytest.param(
        None, None, NO_RULES, "8.3.27.2214", ResolutionSource.MAX_INSTALLED,
        id="no-version-takes-max-installed",
    ),
    pytest.param(
        "8.3.abc", None, NO_RULES, None, ResolutionSource.INVALID_REQUEST,
        id="broken-version-is-reported-not-fixed",
    ),
]


@pytest.mark.parametrize(("requested", "section_default", "rules", "expected", "source"), CASES)
def test_resolution_table(
    requested: str | None,
    section_default: str | None,
    rules: list[DefaultVersionRule],
    expected: str | None,
    source: ResolutionSource,
) -> None:
    resolution = resolve_version(requested, section_default, rules, INSTALLED)
    assert resolution.source is source
    if expected is None:
        assert resolution.version is None
    else:
        assert resolution.version == parse_version(expected)


def test_fallback_is_overall_max() -> None:
    resolution = resolve_version("8.3.99.1", None, [], INSTALLED)
    assert resolution.fallback == parse_version("8.3.27.2214")
    assert resolution.requested == parse_version("8.3.99.1")


def test_fallback_of_installed_exact_version_is_itself() -> None:
    # Штатный стартер запустил бы ту же точную версию — подсказки быть не должно.
    resolution = resolve_version("8.3.25.1560", None, [], INSTALLED)
    assert resolution.fallback == resolution.version


def test_fallback_follows_section_default_outside_mask() -> None:
    # [Ф] T-05.5: DefaultVersion побеждает маску даже вне её.
    resolution = resolve_version("8.3.25", "8.3.22.1923", [], INSTALLED)
    assert resolution.fallback == parse_version("8.3.22.1923")
    assert resolution.fallback == resolution.version  # гибрид: мы следуем платформе


def test_fallback_of_missing_section_default_is_overall_max() -> None:
    # [Ф] T-05.5: не установленный DefaultVersion — тихий максимум вообще,
    # к максимуму с префиксом платформа не возвращается. Мы выбираем префикс,  # noqa: RUF003
    # поэтому подсказка обязана показать расхождение.
    resolution = resolve_version("8.3.25", "8.3.25.9999", [], INSTALLED)
    assert resolution.version == parse_version("8.3.25.1633")
    assert resolution.fallback == parse_version("8.3.27.2214")


def test_fallback_of_prefix_max_matches_our_choice() -> None:
    # [Ф] T-02.1: маска без DefaultVersion → максимум с префиксом у обоих.  # noqa: RUF003
    resolution = resolve_version("8.3.25", None, [], INSTALLED)
    assert resolution.fallback == resolution.version


def test_empty_pool_has_no_fallback() -> None:
    resolution = resolve_version("8.3.25", None, [], [])
    assert resolution.source is ResolutionSource.NOT_INSTALLED
    assert resolution.version is None
    assert resolution.fallback is None


def test_installed_order_does_not_matter() -> None:
    shuffled = list(reversed(INSTALLED))
    resolution = resolve_version("8.3.25", None, [], shuffled)
    assert resolution.version == VersionNumber((8, 3, 25, 1633))


def test_no_request_and_empty_pool() -> None:
    resolution = resolve_version(None, None, [], [])
    assert resolution.source is ResolutionSource.NOT_INSTALLED
    assert resolution.version is None
    assert resolution.fallback is None
