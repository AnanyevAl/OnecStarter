"""Диапазоны версий ключей каталога по «Приложению 7» ИТС (спека v4, §3.4).

PDF «Приложения 7» 8.3.18…8.5.4 лежат в `temp/` и в репозиторий не входят (CLAUDE.md,
«Границы»): прогон воспроизводим только там, где они есть. Из каждого PDF берётся
только множества имён ключей раздела 7.3 и команд раздела 7.4 — ни строки текста ИТС
в вывод не попадает.
Результат переносится в `src/onecstarter/platform_1c/cli_catalog.toml` вручную.

Запуск: `uv run python build/catalog_versions.py` (нужен `pdftotext` в PATH).
"""

import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_KEY_LINE = re.compile(r"^\s*/([A-Za-z@][A-Za-z0-9_@]*)")
# Заголовки без косой черты встречаются в PDF: «UsePrivilegedMode» (7.3.1) и «DisplayPerformance»
# (7.3.7) — найдено исполнением задачи 2, план правлен 08.11.2026.
_BARE_KEYS = ("UsePrivilegedMode", "DisplayPerformance")
_VERSION = re.compile(r"_(\d+\.\d+\.\d+)")


def _section_names(text: str, start: str, stop: str, bare: tuple[str, ...] = ()) -> set[str]:
    """Имена, с которых начинаются строки раздела от заголовка `start` до заголовка `stop`."""  # noqa: RUF002
    inside = False
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(start):
            inside = True
            continue
        if stripped.startswith(stop):
            break
        if not inside:
            continue
        match = _KEY_LINE.match(line)
        if match:
            names.add("/" + match.group(1))
        elif stripped in bare:
            names.add("/" + stripped)
    return names


def section_keys(text: str) -> set[str]:
    """Имена ключей, с которых начинаются строки раздела 7.3 (до «7.4.»)."""  # noqa: RUF002
    return _section_names(text, "7.3. ", "7.4. ", _BARE_KEYS)


def section_commands(text: str) -> set[str]:
    """Имена команд, с которых начинаются строки раздела 7.4 (до «7.5.»)."""  # noqa: RUF002
    return _section_names(text, "7.4. ", "7.5. ")


def _number(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def version_ranges(
    found: Mapping[str, set[str]], names: Iterable[str]
) -> dict[str, tuple[str | None, str | None]]:
    """`since` — первая версия с ключом; `until` — последняя, если в новейшей ключа нет."""  # noqa: RUF002
    versions = sorted(found, key=_number)
    latest = versions[-1] if versions else None
    result: dict[str, tuple[str | None, str | None]] = {}
    for name in names:
        folded = name.casefold()
        present = [v for v in versions if folded in {k.casefold() for k in found[v]}]
        if not present:
            result[name] = (None, None)
            continue
        until = None if present[-1] == latest else present[-1]
        result[name] = (present[0], until)
    return result


def _pdf_text(pdf: Path) -> str:
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "out.txt"
        subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), str(out)], check=True
        )
        return out.read_text(encoding="utf-8")


def main() -> int:
    pdfs = sorted((ROOT / "temp").glob("Приложение 7*.pdf"))
    found: dict[str, set[str]] = {}
    found_commands: dict[str, set[str]] = {}
    for pdf in pdfs:
        match = _VERSION.search(pdf.name)
        if match:
            text = _pdf_text(pdf)
            found[match.group(1)] = section_keys(text)
            found_commands[match.group(1)] = section_commands(text)
    if not found:
        print("Нет PDF «Приложения 7» в temp/ — прогон невозможен.")
        return 1
    catalog = tomllib.loads(
        (ROOT / "src" / "onecstarter" / "platform_1c" / "cli_catalog.toml").read_text("utf-8")
    )
    names = [entry["name"] for entry in catalog["key"]]
    print(f"Версии документации: {', '.join(sorted(found, key=_number))}")
    for name, (since, until) in version_ranges(found, names).items():
        print(f"{name}\tsince={since}\tuntil={until}")
    command_names = [entry["name"] for entry in catalog.get("command", [])]
    for name, (since, until) in version_ranges(found_commands, command_names).items():
        print(f"{name}\tsince={since}\tuntil={until}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
