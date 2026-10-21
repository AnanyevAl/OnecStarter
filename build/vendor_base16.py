"""Набор схем base16 в поставку (T-24.1): темы `.xml` → `.csi` нашим разборщиком.

Запуск вручную, разово и при смене коммита: `uv run python build/vendor_base16.py`.
Результат коммитится — сборке сеть не нужна. Источник — tinted-theming/base16-jetbrains,
лицензия MIT; её текст кладётся рядом со схемами.

Почему `.csi`, а не исходные `.xml`: 362 темы весят 43,6 МБ (около 120 КБ на тему), а диалог
«Цветовая схема…» берёт из темы только 22 цвета палитры редактора. Конвертация идёт тем же
путём, что проходит `.xml` из каталога пользователя (`parse_idea_xml` → `complete`), так что
результат тот же; `.csi` — около 1,5 КБ на тему. Темы без единого цвета палитры и
с ошибкой разбора в набор не попадают (правило выпуска).
"""  # noqa: RUF002

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from onecstarter.domain.edt_scheme import complete, parse_idea_xml, to_csi

REPO = "tinted-theming/base16-jetbrains"
COMMIT = "e1f4094c166b12957d4497e76c50dc57fb5f013b"
TARGET = Path(__file__).resolve().parent.parent / "src" / "onecstarter" / "schemes" / "base16"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "OneCStarter-vendor"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data: bytes = response.read()
        return data


def main() -> int:
    tree = json.loads(_get(f"https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1"))
    paths = sorted(
        item["path"]
        for item in tree["tree"]
        if item["type"] == "blob"
        and item["path"].startswith("editor-themes/")
        and item["path"].endswith(".xml")
    )
    TARGET.mkdir(parents=True, exist_ok=True)
    for old in TARGET.glob("*.csi"):
        old.unlink()
    raw = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}"
    written = 0
    dropped: list[str] = []
    for path in paths:
        stem = Path(path).stem
        try:
            name, colors = parse_idea_xml(_get(f"{raw}/{path}").decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as error:
            dropped.append(f"{stem}: {error}")
            continue
        if not colors:
            dropped.append(f"{stem}: нет цветов палитры")
            continue
        (TARGET / f"{stem}.csi").write_text(to_csi(complete(name or stem, colors)), "utf-8")
        written += 1
    (TARGET / "LICENSE").write_bytes(_get(f"{raw}/LICENSE"))
    lines = [
        "# Цветовые схемы base16 в поставке",
        "",
        f"- Источник: https://github.com/{REPO}, каталог `editor-themes/`",
        f"- Коммит: `{COMMIT}`",
        f"- Получено: {date.today().isoformat()} скриптом `build/vendor_base16.py`",
        "- Лицензия: MIT, текст — `LICENSE` рядом",
        "- Переработка: `parse_idea_xml` → `complete` → `to_csi` (22 цвета палитры редактора 1С)",  # noqa: RUF001
        f"- Тем в источнике: {len(paths)}, в наборе: {written}, отброшено: {len(dropped)}",
    ]
    lines += [f"  - {line}" for line in dropped]
    (TARGET / "SOURCE.md").write_text("\n".join(lines) + "\n", "utf-8")
    print(f"vendor_base16: тем {len(paths)}, записано {written}, отброшено {len(dropped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
