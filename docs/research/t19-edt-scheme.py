"""T-19 (v3.2), Э8–Э11: запись prefs нашим рендером, снимки файлов рабочей области,
статистика разбора тем IDEA, поиск умолчаний EDT в jar. EDT скрипт НЕ запускает.  # noqa: RUF002

Запуск: `uv run python docs/research/t19-edt-scheme.py <команда> …` (домен `edt_scheme`
доступен через установленный пакет). Протокол — `t19-edt-scheme-experiments.md`.
"""  # noqa: RUF002

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from onecstarter.domain.edt_scheme import (
    BSL_PREFS,
    COLOR_KEYS,
    EDITORS_PREFS,
    SYSTEM_DEFAULT_SUFFIX,
    THEME_IDS,
    THEME_KEY,
    THEME_PREFS,
    Scheme,
    ThemeChoice,
    complete,
    from_hex,
    is_dark,
    parse_csi,
    parse_idea_xml,
    parse_prefs,
    parse_tmtheme,
    prefs_updates,
    render_prefs,
    to_hex,
    unescape_property,
)

SETTINGS = Path(".metadata") / ".plugins" / "org.eclipse.core.runtime" / ".settings"
CANARY = "onecstarter.canary"
PREFS_FILES = (BSL_PREFS, EDITORS_PREFS, THEME_PREFS)
OUR_KEYS = {unescape_property(key.prefs_key) for key in COLOR_KEYS}
EDITOR_KEY_NAMES = tuple(
    key.prefs_key for key in COLOR_KEYS if key.prefs_file == EDITORS_PREFS
)
JAVAP_CLASSES = {
    "com._1c.g5.v8.dt.bsl.ui_": (
        "com._1c.g5.v8.dt.bsl.ui.syntaxcoloring.BslHighlightingConfiguration"
    ),
    "org.eclipse.ui.workbench.texteditor_": (
        "org.eclipse.ui.texteditor.AbstractDecoratedTextEditorPreferenceConstants"
    ),
    "org.eclipse.ui.editors_": (
        "org.eclipse.ui.internal.editors.text.TextEditorDefaultsPreferenceInitializer"
    ),
}
PLUGIN_XML_JARS = (
    "org.eclipse.ui.editors_",
    "org.eclipse.ui.workbench.texteditor_",
    "org.eclipse.debug.ui_",
    "com._1c.g5.v8.dt.bsl.ui_",
)


def settings_dir(workspace: str) -> Path:
    return Path(workspace) / SETTINGS


def read(path: Path) -> str:
    return path.read_bytes().decode("latin-1") if path.exists() else ""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("latin-1"))
    print(f"записан {path}: {len(text)} байт")


def newline_kind(text: str) -> str:
    crlf, lf = text.count("\r\n"), text.count("\n")
    if crlf and crlf == lf:
        return "CRLF"
    if lf and not crlf:
        return "LF"
    return (
        f"смешанный (CRLF {crlf}, LF {lf - crlf})"
        if lf
        else "нет переводов"
    )


def cmd_write(args: argparse.Namespace) -> None:
    scheme = complete(
        Path(args.csi).stem,
        parse_csi(Path(args.csi).read_text(encoding="utf-8-sig")),
    )
    if args.override:
        colors = dict(scheme.colors)
        for item in args.override:
            name, _, value = item.partition("=")
            rgb = from_hex(value)
            if rgb is None or name not in colors:
                sys.exit(f"плохой --override {item}")
            colors[name] = rgb
        scheme = Scheme(scheme.name, colors)
    updates = prefs_updates(scheme)
    for name in (BSL_PREFS, EDITORS_PREFS):
        pairs = dict(updates[name])
        remove: list[str] = []
        if args.no_system_default:
            remove = [
                key
                for key in pairs
                if key.endswith(SYSTEM_DEFAULT_SUFFIX)
            ]
            pairs = {
                key: value
                for key, value in pairs.items()
                if key not in remove
            }
        if args.canary:
            pairs[CANARY] = "1"
        path = settings_dir(args.workspace) / name
        write(path, render_prefs(read(path), pairs, remove))


def cmd_theme(args: argparse.Namespace) -> None:
    choice = {"dark": ThemeChoice.DARK, "light": ThemeChoice.LIGHT}.get(
        args.theme
    )
    theme_id = (
        THEME_IDS.get(choice) if choice is not None else args.theme
    )
    if not theme_id:
        sys.exit(
            f"нет id для {args.theme}: заполните THEME_IDS или "
            "передайте id явно"
        )
    path = settings_dir(args.workspace) / THEME_PREFS
    write(path, render_prefs(read(path), {THEME_KEY: theme_id}))


def cmd_snapshot(args: argparse.Namespace) -> None:
    source = settings_dir(args.workspace)
    target = Path(args.out) / datetime.now().strftime("%H-%M-%S")
    target.mkdir(parents=True, exist_ok=True)
    print(f"каталог {source}: {'есть' if source.is_dir() else 'нет'}")
    if source.is_dir():
        print("  файлы:", ", ".join(sorted(p.name for p in source.iterdir())))
    for name in PREFS_FILES:
        path = source / name
        print(f"--- {name}")
        if not path.exists():
            print("  нет файла")
            continue
        shutil.copy2(path, target / name)
        text = read(path)
        lines = text.replace("\r\n", "\n").split("\n")
        parsed = parse_prefs(text)
        keys = list(parsed)
        print(f"  {len(text)} байт, перевод строки: {newline_kind(text)}")
        print(
            f"  первая строка: {lines[0]!r}; "
            f"последняя: {lines[-2] if lines[-1] == '' else lines[-1]!r}"
        )
        print(
            f"  ключей {len(keys)}, по алфавиту: {keys == sorted(keys)}"
        )
        print(
            f"  наших ключей: {len(OUR_KEYS & set(keys))} из 22; "
            f".SystemDefault: "
            f"{sum(k.endswith(SYSTEM_DEFAULT_SUFFIX) for k in keys)}"
        )
        print(f"  канарейка {CANARY}: {parsed.get(CANARY, '—')}")
        for key in sorted(
            set(keys) - OUR_KEYS - {CANARY, "eclipse.preferences.version"}
        ):
            print(f"  чужой ключ: {key}={parsed[key]!r}")
        if name == THEME_PREFS:
            print(f"  {THEME_KEY}={parsed.get(THEME_KEY, '—')}")
    print(f"снимок: {target}")


def _iter_idea_themes(source: Path) -> Iterator[tuple[str, str]]:
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if path.suffix.lower() in (".xml", ".icls"):
                yield path.name, path.read_text(
                    encoding="utf-8-sig", errors="replace"
                )
        return
    with zipfile.ZipFile(source) as archive:
        for name in sorted(archive.namelist()):
            if name.lower().endswith((".xml", ".icls")):
                yield (
                    name,
                    archive.read(name).decode("utf-8-sig", errors="replace"),
                )


def cmd_idea_stats(args: argparse.Namespace) -> None:
    present: Counter[str] = Counter()
    candidates: dict[str, Counter[str]] = {
        key.name: Counter() for key in COLOR_KEYS
    }
    total = 0
    shown = {name.casefold() for name in args.show}
    for file_name, text in _iter_idea_themes(Path(args.source)):
        try:
            theme_name, colors = parse_idea_xml(text)
        except ValueError as error:
            print(f"! {file_name}: {error}")
            continue
        total += 1
        present.update(colors.keys())
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            root = None
        if root is not None:
            attributes = {
                option.get("name", ""): {
                    inner.get("name", ""): inner.get("value", "")
                    for inner in option.findall("value/option")
                }
                for option in root.findall("attributes/option")
            }
            for key in COLOR_KEYS:
                if key.name in colors or key.prefs_file != BSL_PREFS:
                    continue
                for attr, values in attributes.items():
                    if attr.startswith("DEFAULT_") and values.get(
                        "FOREGROUND"
                    ):
                        candidates[key.name][attr] += 1
        if (
            file_name.casefold() in shown
            or Path(file_name).stem.casefold() in shown
            or theme_name.casefold() in shown
        ):
            scheme = complete(theme_name or file_name, colors)
            print(
                f"=== {file_name} ({theme_name!r}), "
                f"тёмная: {is_dark(scheme)}, найдено {len(colors)} из 22"
            )
            for key in COLOR_KEYS:
                mark = "" if key.name in colors else "  (дополнен)"
                print(
                    f"  {key.name:<26} {to_hex(scheme.colors[key.name])}{mark}"
                )
    print(f"тем разобрано: {total}")
    for key in COLOR_KEYS:
        count = present[key.name]
        line = (
            f"{key.name:<26} {count:>4} / {total} "
            f"({100 * count // max(total, 1):>3} %)"
        )
        if count < total and candidates[key.name]:
            top = ", ".join(
                f"{attr} {n}" for attr, n in
                candidates[key.name].most_common(4)
            )
            line += f"   кандидаты: {top}"
        print(line)


def cmd_tmtheme(args: argparse.Namespace) -> None:
    name, colors = parse_tmtheme(
        Path(args.file).read_text(encoding="utf-8-sig")
    )
    scheme = complete(name or Path(args.file).stem, colors)
    print(
        f"{args.file}: {name!r}, тёмная: {is_dark(scheme)}, "
        f"найдено {len(colors)} из 22"
    )
    for key in COLOR_KEYS:
        mark = "" if key.name in colors else "  (дополнен)"
        print(
            f"  {key.name:<26} {to_hex(scheme.colors[key.name])}{mark}"
        )


def cmd_defaults(args: argparse.Namespace) -> None:
    plugins = Path(args.plugins)
    for prefix in PLUGIN_XML_JARS:
        for jar in sorted(plugins.glob(f"{prefix}*.jar")):
            with zipfile.ZipFile(jar) as archive:
                names = archive.namelist()
                if "plugin.xml" in names:
                    text = archive.read("plugin.xml").decode(
                        "utf-8", errors="replace"
                    )
                    keys_pattern = "|".join(
                        map(re.escape, EDITOR_KEY_NAMES)
                    )
                    for match in re.finditer(
                        f"<[^<>]*({keys_pattern})[^<>]*>", text
                    ):
                        print(
                            f"[{jar.name} plugin.xml] "
                            f"{' '.join(match.group(0).split())}"
                        )
                for name in names:
                    if name.endswith("preferencestyle.css"):
                        print(f"[{jar.name} {name}]")
                        print(
                            archive.read(name).decode(
                                "utf-8", errors="replace"
                            )
                        )
    for prefix, class_name in JAVAP_CLASSES.items():
        for jar in sorted(plugins.glob(f"{prefix}*.jar")):
            print(f"=== javap {jar.name} {class_name}")
            result = subprocess.run(
                [args.javap, "-c", "-p", "-cp", str(jar), class_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            lines = result.stdout.splitlines()
            for index, line in enumerate(lines):
                if 'org/eclipse/swt/graphics/RGB."<init>"' in line:
                    context = lines[max(0, index - 8) : index + 1]
                    print("\n".join(context))
                    print("-")
            if result.returncode:
                print(result.stderr[:500])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("write", help="записать prefs рабочей области из .csi")
    p.add_argument("workspace")
    p.add_argument("--csi", required=True)
    p.add_argument(
        "--canary", action="store_true",
        help="добавить ключ onecstarter.canary=1"
    )
    p.add_argument(
        "--no-system-default", action="store_true",
        help="без .SystemDefault=false"
    )
    p.add_argument(
        "--override", action="append", default=[],
        help="Имя=#RRGGBB, повторяемый"
    )
    p.set_defaults(func=cmd_write)
    p = sub.add_parser("theme", help="записать themeid")
    p.add_argument("workspace")
    p.add_argument("theme", help="dark | light | <id темы>")
    p.set_defaults(func=cmd_theme)
    p = sub.add_parser(
        "snapshot", help="снять три prefs-файла и описать их"
    )
    p.add_argument("workspace")
    p.add_argument("out")
    p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser(
        "idea-stats", help="статистика разбора тем IDEA (zip или каталог)"
    )
    p.add_argument("source")
    p.add_argument(
        "--show", action="append", default=[],
        help="имя темы/файла для таблицы"
    )
    p.set_defaults(func=cmd_idea_stats)
    p = sub.add_parser("tmtheme", help="таблица цветов одного .tmTheme")
    p.add_argument("file")
    p.set_defaults(func=cmd_tmtheme)
    p = sub.add_parser("defaults", help="умолчания EDT из jar установки")
    p.add_argument("plugins")
    p.add_argument("javap")
    p.set_defaults(func=cmd_defaults)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
