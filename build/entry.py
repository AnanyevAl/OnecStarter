"""Точка входа PyInstaller: тонкая обёртка над onecstarter.__main__.

Отдельный файл, а не __main__.py пакета: PyInstaller требует скрипт,
а скрипт с именем __main__.py конфликтует с одноимённым модулем сборки.
"""  # noqa: RUF002

from onecstarter.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
