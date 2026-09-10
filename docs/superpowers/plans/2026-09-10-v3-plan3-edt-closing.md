# Проекты EDT — план 3 реализации v3: эксперименты, скил, документы, выпуск

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть веху v3: семь экспериментов на машине заказчика возвращают метки достоверности в спеку и в новый доменный скил `edt-launch`; документы догоняют код; версия `3.0.0` собрана, прошла smoke и выпущена.

**Architecture:** эксперименты — протоколы для заказчика с готовыми командами и полями результата, записываются в `docs/research/t17-edt-experiments.md`; их исход правит §0/§0-Д спеки и код там, где факт опровергнут (спека §10: «исход возвращается в §0 и в скил»); скил — через `writing-skills` по Iron Law; выпуск — тем же путём, что v2.4 (`build/build.ps1` → smoke → тег).

**Tech Stack:** PowerShell (замеры), `writing-skills`, PyInstaller + Inno Setup (`build/build.ps1`).

Спека — [2026-09-10-v3-edt-design.md](../specs/2026-09-10-v3-edt-design.md), §10–§13.
База — завершённые [план 1](2026-09-10-v3-plan1-edt-section.md) и
[план 2](2026-09-10-v3-plan2-edt-cli.md) на ветке `feat/2026-09-10-v3-edt`.

## Global Constraints

- **Запуск EDT и CLI — только заказчиком, на тестовом workspace, с явного разрешения**
  (спека §10; CLAUDE.md, «Границы»). Агент готовит команды и читает результаты.
- **Факт без метки не попадает ни в скил, ни в `docs/`** (CLAUDE.md, «Достоверность»).
  Опровергнутый факт правится и в спеке, и в коде, и в тесте, который его фиксировал —
  в одном коммите.
- **Скил — через `writing-skills`, Iron Law**: baseline-сценарий на субагенте без скила
  → скил → проверка тем же сценарием. Формат — как у `platform-launch/` (`SKILL.md` +
  `reference.md`, frontmatter `name`/`description`).
- Тестовый workspace: пустой каталог `<tmp>\edt-test-ws` — EDT создаёт workspace сам
  ([?] спека §0, это тоже проверяется). Рабочие workspace заказчика не трогать.
- Версия — только `pyproject.toml`; smoke собранного экземпляра обязателен до артефактов.
- Коммиты по-русски, без атрибуции.

---

### Task 1: Протоколы экспериментов 1–7 и файл результатов

**Files:**
- Create: `docs/research/t17-edt-experiments.md`

**Interfaces:**
- Consumes: спека §0, §0-Д, §10.
- Produces: файл с семью протоколами, у каждого — цель, команды, поля результата, куда
  уходит исход (строка §0/§0-Д, файл кода, тест).

- [ ] **Step 1: Написать файл протоколов**

`docs/research/t17-edt-experiments.md` — семь разделов по шаблону:

```markdown
# T-17. Эксперименты вехи v3 (EDT) — протоколы и результаты

Выполняет заказчик. Каждый исход правит метку в спеке (§0 / §0-Д) и, если факт
опровергнут, код и тест, названные в поле «Куда уходит».

## Э1. Наша командная строка поднимает EDT

**Цель.** Строка `build_edt_command` запускает EDT 2025.2.6 и 2026.1.2 с JDK из
`products.json`; 2024.2.6 — с JDK из `-vm` в `1cedt.ini` (Zulu 17 в `C:\Program Files\Zulu`,
шаг 2 цепочки). Повтор `-Xmx` — действует последний.

**Подготовка.** Тестовый workspace `<tmp>\edt-test-ws` (пустой каталог). В OneCStarter:
Добавить… → имя `Тест 2025`, workspace — тестовый, версия 2025.2.6+4, память 6144,
прочие — пусто. Аналогично `Тест 2026`, `Тест 2024`.

**Команды.** «Открыть в EDT» для каждой записи. После старта — снять фактическую строку
и heap:
```powershell
Get-CimInstance Win32_Process -Filter "name='1cedt.exe'" | Select-Object ProcessId, CommandLine | Format-List
```
В EDT: Help → About → Installation Details → Configuration — строка `-Xmx` в
`eclipse.vmargs` (или `Runtime.maxMemory` в System properties).

**Результат.**
| Версия | Стартовал | JDK в -vm | Фактический -Xmx | Примечание |
| --- | --- | --- | --- | --- |
| 2025.2.6+4 | | | | |
| 2026.1.2+2 | | | | |
| 2024.2.6+7 | | | | |
Workspace создан по несуществующему `-data`: да / нет.

**Куда уходит.** §0: строки «Командная строка EDT Start» → без изменений либо правка;
«При повторе -Xmx действует последний» → [Ф]/опровергнут; «EDT по несуществующему -data
создаёт workspace» → [Ф]/опровергнут (тогда `EdtWorkspace.launch` проверяет каталог,
`test_launch` дополняется). Код: `domain/edt.py::build_edt_command`, `pick_jvm`.
```

Остальные разделы — той же формы:

- **Э2. Активация окна.** Запись «Тест 2025» открыта → «Открыть в EDT» повторно из
  OneCStarter: окно всплыло? Свернуть EDT → повторить: развернулось? Сразу после старта,
  пока splash: реакция? Результат → §0 «SetForegroundWindow разрешён…»; код —
  `platform_1c/window_activate.py` (при отказе — `AllowSetForegroundWindow`/`AttachThreadInput`,
  отдельная задача).
- **Э3. Редакторы.** Запись с `project_dir` = каталог с пробелом и кириллицей
  (`<tmp>\edt test\проект`). «Открыть в VS Code», «Открыть в Antigravity»: открылся ли
  именно этот каталог? Результат → §0 строки про `.cmd`/Antigravity; при отказе —
  `EdtWorkspace.open_in_editor` через `cmd.exe /c` с экранированием (задача плана правок).
- **Э4. JVM у проекта в EDT Start.** В EDT Start задать Java VM одному проекту → скопировать
  запись из `projects.json` (обезличив путь). Результат → §0 «Ключ переопределения JVM…»,
  `platform_1c/edtstart_registry.py::_jvm_of`, фикстура `projects.json`.
- **Э5. Язык.** В EDT Start задать «Русский» → запустить → `CommandLine` процесса.
  Результат → §0 «Язык интерфейса…»: `-Duser.language=ru` подтверждён/иное;
  `domain/edt.py::_LANGUAGE`.
- **Э6. CLI на закрытом workspace.** Записи «Тест 2025» (EDT закрыт): «Информация по
  проектам», затем «Пересобрать проекты», затем «Импортировать проект…» (существующий —
  любой каталог с `.project`), «Проверить проекты…». Снять: код в консоли, кодировка
  (кириллица читаема?), время до первой строки, `CommandLine` процесса `1cedtcli.exe`
  (формат `-command`). Результат → §0-Д: `-command`, имена `import`/`validate`, кодировка,
  разделитель `--project-list`, `-vmargs` последним; код — `domain/edt_cli.py`.
- **Э7. CLI на открытом workspace и коды.** Открыть «Тест 2025» в EDT → «Информация по
  проектам»: подменю неактивно (ожидаемо). Затем вручную из PowerShell на открытом workspace:
  ```powershell
  & "C:\Program Files\1C\1CE\components\1c-edt-2025.2.6+4-x86_64\1cedtcli.exe" -data <тестовый ws> -command "help --status-codes" -vm "C:\Program Files\1C\1CE\components\axiom-jdk-full-17.0.16+12-x86_64\bin" --launcher.appendVmargs -vmargs -Dsun.stdout.encoding=UTF-8; $LASTEXITCODE
  ```
  и то же с `-command "project"`: число кода `WORKSPACE_IN_USE` и полный вывод
  `help --status-codes`. Результат → §0-Д «Коды завершения», таблица кодов → скил и
  `ui/edt/console_panel.py::state_finished` (имя рядом с числом — Task 4).

- [ ] **Step 2: Commit**

```bash
git add docs/research/t17-edt-experiments.md
git commit -m "docs: T-17 — протоколы экспериментов 1–7 вехи v3"
```

---

### Task 2: Проведение экспериментов и возврат исходов

**Выполняет заказчик** по протоколам Task 1; агент — заполняет результаты, правит спеку,
код и тесты.

**Files:**
- Modify: `docs/research/t17-edt-experiments.md` (результаты)
- Modify: `docs/superpowers/specs/2026-09-10-v3-edt-design.md` (§0, §0-Д — метки)
- Modify: код и тесты по полю «Куда уходит» каждого опровергнутого факта

- [ ] **Step 1: Заполнить результаты Э1–Э7 дословно** (вывод команд, коды, «да/нет»)

- [ ] **Step 2: Правка меток в спеке**

Каждая строка §0/§0-Д, помеченная **[?]** и покрытая экспериментом, получает **[Ф]** с датой
и номером эксперимента либо переписывается по факту. Строки, не покрытые ни одним
экспериментом, остаются **[?]** — так и записать в T-17.

- [ ] **Step 3: Код вслед за опровержением**

Для каждого опровергнутого факта — правка функции из поля «Куда уходит» и её табличного
теста в одном коммите: `fix(domain): …по итогам Э<N>`. Ожидаемые точки: `build_edt_command`
(Э1), `bring_to_front` (Э2), `open_in_editor` (Э3), `_jvm_of` (Э4), `_LANGUAGE` (Э5),
`build_cli_command`/`cli_validate_args`/`_LIST_SEPARATOR`/`CLI_ENCODING_ARGS` (Э6).

- [ ] **Step 4: Таблица кодов CLI (Э7)**

В `ui/edt/console_panel.py`:

```python
CLI_STATUS_NAMES: dict[int, str] = {}  # заполняется по выводу help --status-codes (Э7)


def state_finished(code: int) -> str:
    name = CLI_STATUS_NAMES.get(code)
    return f"завершено, код {code}" + (f" ({name})" if name else "")
```

Тест `test_state_constants` дополняется строкой на известный код (например,
`WORKSPACE_IN_USE`). Пока таблица пуста — прежний текст, тесты плана 2 не меняются.

- [ ] **Step 5: Прогон и коммит**

Run: `uv run pytest -q > e:/tmp/v3-plan3-task2.log 2>&1; tail -3 e:/tmp/v3-plan3-task2.log && uv run ruff check . && uv run mypy`

```bash
git add docs/research/t17-edt-experiments.md docs/superpowers/specs/2026-09-10-v3-edt-design.md src tests
git commit -m "docs: T-17 — эксперименты 1–7 проведены, метки §0/§0-Д обновлены, код вслед за находками"
```

---

### Task 3: Скил `edt-launch` через `writing-skills`

**Files:**
- Create: `.claude/skills/edt-launch/SKILL.md`
- Create: `.claude/skills/edt-launch/reference.md`
- Modify: `CLAUDE.md` («Доменные скилы проекта»)

**Interfaces:**
- Consumes: спека §0, §0-Д после Task 2; результаты Э1–Э7.
- Produces: третий доменный скил проекта.

- [ ] **Step 1: RED — baseline на субагенте без скила**

Вызвать `writing-skills`. Сценарий baseline (субагенту без доступа к спеке и скилу):
«Собери командную строку запуска 1C:EDT 2025.2.6 для workspace `D:\edt\ws` с памятью 8 ГБ;
объясни, откуда взять JVM и где EDT Start хранит список проектов; можно ли запустить CLI
на открытом в EDT workspace». Зафиксировать ответ и его ошибки (ожидаемо: `-vm` пропущен,
реестр EDT Start неизвестен, блокировка workspace не названа).

- [ ] **Step 2: GREEN — написать скил**

`SKILL.md` — frontmatter:

```markdown
---
name: edt-launch
description: Use when launching 1C:EDT from code or command line, discovering installed EDT versions and their JDK, reading the 1C:EDT Start registry (products.json/projects.json), building 1cedt.exe or 1cedtcli.exe command lines, or running EDT CLI commands (build, import, validate, project)
---
```

Разделы `SKILL.md` (каждый факт с меткой и датой, из спеки §0/§0-Д после Task 2):

1. Раскладка: `components\1c-edt-<версия>-x86_64\{1cedt.exe,1cedtc.exe,1cedtcli.exe,1cedt.ini}`, JDK рядом.
2. EDT Start: `%LOCALAPPDATA%\1C\1cedtstart\{products,projects,preferences}.json` — ключи, `location` = workspace (не проект), `jvmPath` как `file:///`.
3. `1cedt.ini` без `-vm` у установок EDT Start; `-Dosgi.requiredJavaVersion`; `-Xmx4096m`.
4. Командная строка EDT — дословно; порядок аргументов уровней; `-Djava.library.path=`.
5. Окно у `1cedt.exe`; блокировка workspace.
6. CLI: `1cedtcli.exe -data … -command "…"` до `-vmargs`; команды и ключи; `--yes`;
   коды завершения (таблица из Э7); кодировка вывода; одинарные кавычки.
7. Редакторы: пути `code.cmd`, `antigravity-ide.cmd`.
8. Что НЕ проверено — отдельным списком.

`reference.md` — полные таблицы: ключи `products.json`/`projects.json`, команды CLI с
ключами и описаниями из ресурсов плагина, коды возврата.

- [ ] **Step 3: Проверка тем же сценарием на субагенте со скилом**

Ответ обязан содержать `-vm`, `--launcher.appendVmargs`, путь к `projects.json`, слово
«workspace занят/`WORKSPACE_IN_USE`». Расхождение — правка скила, повтор.

- [ ] **Step 4: `CLAUDE.md`**

В «Доменные скилы проекта» добавить `.claude/skills/edt-launch/` и требование читать его
перед любой работой с EDT, EDT Start и `1cedtcli`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/edt-launch CLAUDE.md
git commit -m "docs(skills): доменный скил edt-launch — раскладка, EDT Start, командные строки, CLI"
```

---

### Task 4: Документы вехи

**Files:**
- Modify: `docs/requirements.md` (§5, §2 при необходимости)
- Modify: `README.md` (раздел «Проекты EDT (v3)»)
- Modify: `docs/tasks.md` (T-17.3, состояние вехи)

- [ ] **Step 1: `requirements.md` §5**

Строка v3 таблицы: содержание уточнить — «свой реестр workspace'ов с группами, запуск EDT
нужной версии с JVM, VS Code/Antigravity, импорт из EDT Start, статус «запущен», CLI
(build/import/validate/project) с консолью». Абзац о выпуске: «v3 выпущена <дата>: …».

- [ ] **Step 2: README — раздел после «Доступность файловых баз (v2.4)»**

```markdown
## Проекты EDT (v3)

Раздел «EDT» — список workspace'ов 1C:EDT с группами. Для записи: версия EDT
(точное совпадение с установленной), JVM, память и язык; «Открыть в EDT» запускает
нужную версию с правильной JVM, повторный запуск переключает на открытое окно.
«Открыть в VS Code» / «Открыть в Antigravity» открывают каталог проекта (может лежать
вне workspace). Импорт из EDT Start — вручную, только новое. Подменю «CLI» — сборка,
импорт, проверка и информация по проектам через `1cedtcli.exe` с выводом в консоль;
работает только на workspace, не открытом в EDT. Список — `%APPDATA%\OneCStarter\edt.json`,
реестр EDT Start только читается.
```

- [ ] **Step 3: `docs/tasks.md` — T-17.3 и итог**

Строка T-17.3 → `DONE`, заголовок T-17 → `DONE (<дата>, ветка …)`, «Состояние вехи»:
что проверено экспериментами, что осталось **[?]**.

- [ ] **Step 4: Commit**

```bash
git add docs/requirements.md README.md docs/tasks.md
git commit -m "docs: веха v3 — requirements §5, README «Проекты EDT», T-17 закрыт"
```

---

### Task 5: Версия 3.0.0, сборка, smoke, выпуск

**Files:**
- Modify: `pyproject.toml` (`version = "3.0.0"`)
- Modify: `build/smoke.py` (гейт `smoke: edt=`)
- Modify: `docs/tasks.md` (гейты вехи)

- [ ] **Step 1: Гейт smoke**

В `build/smoke.py` рядом с проверкой `smoke: keyring=ok` — обязательная строка
`smoke: edt=` (число установок, любое ≥ 0) в логе самопроверки; её отсутствие — отказ.

- [ ] **Step 2: Версия и полный прогон**

`pyproject.toml`: `version = "3.0.0"`. Run: `uv sync && uv run pytest -q > e:/tmp/v3-final.log 2>&1; tail -3 e:/tmp/v3-final.log && uv run ruff check . && uv run mypy`.

- [ ] **Step 3: Сборка и smoke**

Run (PowerShell): `powershell -File build/build.ps1`
Expected: PyInstaller ок → `smoke: …` строки, включая `smoke: edt=N` → `dist/OneCStarter-3.0.0-portable.zip` и установщик.

- [ ] **Step 4: Ручной smoke собранного экземпляра на машине заказчика**

Чек-лист: раздел «EDT» виден; импорт из EDT Start; версия 2024.2.6+7 (нет в products.json,
есть на диске) обнаружена; «Открыть в EDT» тестового workspace; статус «запущен» и
активация; CLI «Информация по проектам» на закрытом workspace; Настройки → EDT.
Результат — в T-17 «Гейты вехи» таблицей, как у v2.4.

- [ ] **Step 5: Финальное ревью ветки, слияние, тег**

`superpowers:finishing-a-development-branch`: ревью диффа `master..feat/2026-09-10-v3-edt`,
волна правок при находках, затем — **с подтверждения заказчика** — слияние в `master`,
тег `v3.0.0`, push ветки, master и тега.

```bash
git checkout master && git merge --no-ff feat/2026-09-10-v3-edt -m "release: v3.0.0 — проекты EDT"
git tag v3.0.0
git push origin master v3.0.0
```

---

## Чего в плане нет — сознательно

- Автопроверка релизов на GitHub, обновление приложения — не в v3 (requirements §4).
- Повторные эксперименты на других версиях EDT — по мере появления у заказчика; скил
  помечает версии, на которых факты сняты.
