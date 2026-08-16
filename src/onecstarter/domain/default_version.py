"""Правила DefaultVersion из 1cestart.cfg: таблица подстановки, не скаляр.

Грамматика <маска>[-<полная версия>][;<разрядность>] — скил platform-launch.
Разделитель маски и цели — дефис. Правило без цели задаёт предпочтение
разрядности; в подстановке версии не участвует.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from onecstarter.domain.version import VersionNumber, parse_version


@dataclass(frozen=True)
class DefaultVersionRule:
    mask: VersionNumber
    target: VersionNumber | None
    arch: str | None


def parse_default_version_rule(value: str) -> DefaultVersionRule:
    body, has_arch, arch = value.partition(";")
    mask_text, has_target, target_text = body.partition("-")
    return DefaultVersionRule(
        mask=parse_version(mask_text.strip()),
        target=parse_version(target_text.strip()) if has_target else None,
        arch=arch.strip() if has_arch else None,
    )


def default_version_rules(entries: Iterable[tuple[str, str]]) -> list[DefaultVersionRule]:
    rules: list[DefaultVersionRule] = []
    for key, value in entries:
        if key.casefold() != "defaultversion":
            continue
        try:
            rules.append(parse_default_version_rule(value))
        except ValueError:
            continue
    return rules


def substitute(mask: VersionNumber, rules: Sequence[DefaultVersionRule]) -> VersionNumber | None:
    for rule in rules:
        if rule.mask == mask and rule.target is not None and rule.target.is_full:
            return rule.target
    return None
