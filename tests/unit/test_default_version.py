import pytest

from onecstarter.domain.default_version import (
    DefaultVersionRule,
    default_version_rules,
    parse_default_version_rule,
    substitute,
)
from onecstarter.domain.version import parse_version


def test_parse_mask_with_target() -> None:
    rule = parse_default_version_rule("8.3-8.3.24.100")
    assert rule.mask == parse_version("8.3")
    assert rule.target == parse_version("8.3.24.100")
    assert rule.arch is None


def test_parse_mask_only() -> None:
    rule = parse_default_version_rule("8.2.15")
    assert rule == DefaultVersionRule(mask=parse_version("8.2.15"), target=None, arch=None)


def test_parse_mask_with_arch() -> None:
    rule = parse_default_version_rule("8.3;x86_64_prt")
    assert rule.mask == parse_version("8.3")
    assert rule.target is None
    assert rule.arch == "x86_64_prt"


def test_parse_garbage_raises() -> None:
    with pytest.raises(ValueError, match="версии"):
        parse_default_version_rule("не версия")


def test_rules_from_entries_key_is_case_insensitive() -> None:
    entries = [
        ("DefaultVersion", "8.3-8.3.24.100"),
        ("DEFAULTVERSION", "8.2.15-8.2.15.315"),
        ("CommonInfoBases", r"\\server\share\bases.v8i"),
        ("DefaultVersion", "мусор — пропустить"),
    ]
    rules = default_version_rules(entries)
    assert [str(rule.mask) for rule in rules] == ["8.3", "8.2.15"]


def test_substitute_exact_mask_match() -> None:
    rules = default_version_rules([("DefaultVersion", "8.3-8.3.24.100")])
    assert substitute(parse_version("8.3"), rules) == parse_version("8.3.24.100")
    # 8.3.24 ≠ 8.3: маска правила сопоставляется точным равенством, не префиксом.
    assert substitute(parse_version("8.3.24"), rules) is None


def test_substitute_first_match_wins() -> None:
    rules = default_version_rules(
        [("DefaultVersion", "8.3-8.3.24.100"), ("DefaultVersion", "8.3-8.3.22.1923")]
    )
    assert substitute(parse_version("8.3"), rules) == parse_version("8.3.24.100")


def test_substitute_skips_rule_without_full_target() -> None:
    rules = default_version_rules([("DefaultVersion", "8.3;x86_64_prt")])
    assert substitute(parse_version("8.3"), rules) is None
