"""Сборка OneCStarter — единственный источник правды (CLAUDE.md, «Сборка»).

one-dir, два exe из одного Analysis: OneCStarter.exe (windowed)
и OneCStarterc.exe (console, для диагностики — спека T-04.6, §4.3).
Версия — из pyproject.toml, единственного места (CLAUDE.md).
"""

import tomllib
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent  # noqa: F821 — SPECPATH определяет PyInstaller
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
NUMBERS = tuple(int(part) for part in VERSION.split("."))[:4]
NUMBERS = NUMBERS + (0,) * (4 - len(NUMBERS))
ICON = str(Path(SPECPATH) / "onecstarter.ico")  # noqa: F821

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "041904B0",
                    [
                        StringStruct("ProductName", "OneCStarter"),
                        StringStruct("FileDescription", "Запуск информационных баз 1С:Предприятие"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("ProductVersion", VERSION),
                        StringStruct("LegalCopyright", "MIT License"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1049, 1200])]),
    ],
)

a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],  # noqa: F821
    pathex=[str(ROOT / "src")],
    # registry.toml читается через importlib.resources (platform_1c/registry.py) —
    # не .py, PyInstaller не находит такие файлы анализом импортов, нужен явный datas.
    datas=[
        (
            str(ROOT / "src" / "onecstarter" / "platform_1c" / "registry.toml"),
            "onecstarter/platform_1c",
        )
    ],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="OneCStarter",
    console=False,
    icon=ICON,
    version=version_info,
)
exe_cli = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="OneCStarterc",
    console=True,
    icon=ICON,
    version=version_info,
)
coll = COLLECT(exe_gui, exe_cli, a.binaries, a.datas, name="OneCStarter")
