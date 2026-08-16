import subprocess
import sys

# Пакеты-контейнеры импортировать бесполезно: их __init__ пуст, и протечка
# в подмодуле осталась бы незамеченной. Перечисляем сами модули ядра.
# Новый модуль ядра (services/domain/config/platform_1c/security) — новая
# строка здесь, иначе протечка Qt в него прошла бы этот тест зелёной.
CORE = (
    "onecstarter.diagnostics",
    "onecstarter.services",
    "onecstarter.services.workspace",
    "onecstarter.services.display",
    "onecstarter.services.settings",
    "onecstarter.services.connection",
    "onecstarter.config.v8i",
    "onecstarter.config.atomic",
    "onecstarter.config.cestart_cfg",
    "onecstarter.config.shell_link",
    "onecstarter.domain.launch",
    "onecstarter.domain.selection",
    "onecstarter.platform_1c.discovery",
    "onecstarter.platform_1c.process",
    "onecstarter.platform_1c.registry",
    "onecstarter.security.secrets",
)

PROBE = (
    "import sys;"
    + "".join(f"import {module};" for module in CORE)
    + "leaked=[m for m in sys.modules if m.split('.')[0]=='PySide6'];"
    "print(leaked)"
)


def test_core_packages_do_not_import_qt() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", f"Qt протёк в ядро: {result.stdout}"
