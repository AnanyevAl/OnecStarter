"""Чтение 1cestart.cfg. В v1 файл только читается, запись не поддерживается."""  # noqa: RUF002

from onecstarter.config.encoding import decode


def parse_cestart_cfg(data: bytes) -> list[tuple[str, str]]:
    text, _ = decode(data)
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        entries.append((key, value))
    return entries


def common_infobase_sources(entries: list[tuple[str, str]]) -> list[str]:
    return [value for key, value in entries if key.casefold() == "commoninfobases"]
