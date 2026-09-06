# Хранение логина и пароля для запуска базы — план реализации v2.2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** по спеке
[2026-09-04-v22-credentials-design.md](../specs/2026-09-04-v22-credentials-design.md)
дать записи базы логин и пароль: логин — в наших данных, пароль — в Windows
Credential Manager, при запуске оба передаются клиенту 1С через `/N` и `/P`.

**Architecture:** два гейта до кода — эксперимент на тестовой базе (работает
ли `/N /P` при `/IBName` вообще) и round-trip `keyring` внутри замороженной
сборки. Дальше слоями снизу вверх: `security/` (хранилище и редакция) →
`domain/launch.py` (`Credentials`, сборка аргументов) → `services/`
(наши данные, `Workspace`, запуск) → `ui/` (оба диалога, применение) →
документы и релиз. Учётные данные никогда не идут через путь записи `.v8i`
и никогда не попадают в `repr`, сообщения и логи.

**Tech Stack:** Python 3.14, PySide6 6.11.1, `keyring` 25.7.0 (зависимость
с 0.1.0), pytest + pytest-qt, uv, ruff, mypy, PyInstaller.

## Global Constraints

- **Qt только в `src/onecstarter/ui/`.** `security/credentials.py` импортирует
  `keyring`, Qt он не тянет; модуль добавляется в явный список `CORE`
  в `tests/unit/test_no_qt_in_core.py` — иначе страж его не видит.
- **`mypy` strict** для всего, кроме `onecstarter.ui.*`; `uv run ruff check .`
  и `uv run mypy` чисты после каждой задачи. `# noqa: RUF001/002/003` — только
  там, где ruff реально ругнулся; RUF100 ловит лишние.
- **Ветка:** `feat/2026-09-04-v22-credentials` от `master@608c028`. Не пушить
  без явного согласия заказчика.
- **Пароль никогда не попадает** в `.v8i`, `bases.json`, сообщения об
  ошибках, логи, `LaunchOutcome`, `repr`/`str` любых объектов, отчёты задач
  и коммиты. Тестовые пароли — только выдуманные строки вроде `"p@ss"`.
- **Полный прогон pytest — только в файл**:
  `PYTHONFAULTHANDLER=1 uv run pytest -rA --tb=long -p no:cacheprovider > <файл> 2>&1`.
  Код 139 — известный долг T-12 п. 15, не регресс: повторить, повтор обязан
  пройти.
- **Защитный тест обязан упасть на мутации** до того, как считается
  написанным. Мутация формулируется как «выключи проверяемое поведение»;
  строку ищет тот, кто проследил зависимость теста. Что ломали — в отчёт.
- **Обработчик на сигнале обязан быть выполнен тестом**: кнопку — `.click()`,
  пункт — `.trigger()`, а не прямой вызов целевого метода.
- **Докстринг, который переносят или переписывают, не теряет объяснений.**
  Блоки кода в плане показывают структуру; исходный текст берётся из файла
  (`git show <база>:<путь>`), новое дописывается.
- **Оболочка PowerShell 5.1**: нет `&&`/`||`; многострочный коммит —
  `git commit -F <файл>`. Сборка — только из PowerShell-инструмента.
- **Окончания строк проверять байтами**: `docs/tasks.md`, `theme.py` — CRLF.
  Править побайтово, `git diff --stat` обязан показать строки, не файл.
- **Запуск 1С, Конфигуратора, GUI собранного приложения и установщика —
  только заказчик.** Агенту разрешены компиляция ISCC и smoke-сборка.
- **Достоверность фактов о 1С**: каждое утверждение о механике платформы
  несёт метку [Ф]/[Д]/[Р]; код по [Р] не пишется.
- **Версия** — только `pyproject.toml`, поднимается в последней задаче.

---

## File Structure

| Файл | Ответственность | Задача |
| --- | --- | --- |
| `docs/research/t05-14-launch-matrix.ps1` | **создаётся.** Скрипт-помощник эксперимента: команда, хеши, снимок процесса | 0a |
| `docs/research/t05-14-results.md` | **создаётся.** Шаблон записи результатов, потом сами результаты | 0a, 0b |
| `.claude/skills/platform-launch/SKILL.md`, `reference.md` | [Ф] по итогам эксперимента | 0b |
| `src/onecstarter/ui/app.py` | `run_smoke`: round-trip `keyring` внутри frozen-сборки | 1 |
| `build/onecstarter.spec`, `build/smoke.py` | `hiddenimports`; проверка строки `smoke: keyring=ok` | 1 |
| `src/onecstarter/security/credentials.py` | **создаётся.** `CredentialStore`, `KeyringStore`, `MemoryStore`, `CredentialBackendError` | 2 |
| `src/onecstarter/security/secrets.py` | `redact_arguments` | 2 |
| `tests/unit/test_credentials.py`, `tests/unit/test_secrets.py` | тесты хранилища и редакции | 2 |
| `src/onecstarter/domain/launch.py` | `Credentials`; `build_arguments(credentials=)` | 3 |
| `tests/unit/test_launch.py` | побайтовые тесты строки с учётными данными | 3 |
| `src/onecstarter/services/user_data.py` | `BaseUserData.login`, кодек, `set_login` | 4 |
| `src/onecstarter/services/errors.py` | `CredentialStoreError` | 4 |
| `src/onecstarter/services/workspace.py` | инъекция хранилища; `set_credentials`, `credentials_of`; `launch`; rekey; remove | 4 |
| `src/onecstarter/services/launch.py` | `launch_infobase(credentials=)`; редакция в ошибке и исходе | 4 |
| `tests/unit/test_user_data.py`, `test_workspace.py`, `test_services_launch.py` | тесты слоя services | 4 |
| `src/onecstarter/ui/dialogs/infobase.py` | три строки, `DialogCredentials`, `credentials()`, `credentials_changed()` | 5 |
| `src/onecstarter/ui/bases/view.py` | передача `credentials_of`; применение в обоих путях | 5 |
| `tests/ui/conftest.py`, `test_infobase_dialog.py`, `test_bases_view.py` | `MemoryStore` в фабрике; тесты диалога и путей | 5 |
| `docs/requirements.md`, `docs/tasks.md`, `pyproject.toml` | документы, веха T-14, версия 2.2.0 | 6 |

---

## Task 0a: скрипт-помощник эксперимента T-05.14 и шаблон результатов

**Files:**
- Create: `docs/research/t05-14-launch-matrix.ps1`
- Create: `docs/research/t05-14-results.md`

**Interfaces:**
- Produces: файл результатов, который заказчик заполняет; задача 0b читает его.

Это подготовка гейта. Запуски делает заказчик — ему нужен инструмент,
который печатает точную команду, считает хеш `ibases.v8i` до и после,
снимает командную строку процесса 1С и пишет строку результата
**с заменённым паролем**.

- [ ] **Step 1: Скрипт**

Создать `docs/research/t05-14-launch-matrix.ps1`. **Сохранить в UTF-8
с BOM**: PowerShell 5.1 читает `.ps1` без BOM как ANSI, и все кириллические
строки скрипта (подсказки, «<пароль>») выйдут кракозябрами. Проверка:
первые три байта файла — `EF BB BF`.

```powershell
<#
Эксперимент T-05.14 (спека v2.2, §1): работает ли /N /P при запуске по /IBName.
Запускает заказчик. Пароль в файл результатов НЕ пишется — заменяется на <пароль>.

Пример:
  .\t05-14-launch-matrix.ps1 -Exe "C:\Program Files\1cv8\8.3.25.1633\bin\1cv8c.exe" `
      -IbName "Тест пароля" -User tester -Run B
#>
param(
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $IbName,
    [Parameter(Mandatory)] [string] $User,
    [Parameter(Mandatory)] [ValidateSet("A", "B", "B2", "C", "D")] [string] $Run,
    [string] $FilePath = ""   # только для D: каталог файловой базы
)

$ibases = Join-Path $env:APPDATA "1C\1CEStart\ibases.v8i"
$results = Join-Path $PSScriptRoot "t05-14-results.md"

function Quote([string] $value) { '"' + $value.Replace('"', '""') + '"' }

# Симметричная сборка вместо Replace() по готовой строке: $arguments и $shown
# строит одна и та же функция, различаясь только переданным секретом. Так
# показ/запись никогда не расходятся с реальным экранированием Quote() —
# в частности, если пароль содержит `"`, Quote() удваивает её (pa"ss -> pa""ss),
# и Replace(pa"ss, ...) по уже собранной строке такую двойную форму не находит,
# и настоящий пароль остаётся в строке. Symmetric build исключает это в принципе.
function Build-Arguments([string] $secret) {
    switch ($Run) {
        "A"  { $extra = "" }
        "B"  { $extra = "/N$(Quote $User) /P$(Quote $secret)" }
        "B2" { $extra = "/N$User /P$secret" }
        "C"  { $extra = "/N$(Quote $User) /P$(Quote $secret) /WA-" }
        "D"  { $extra = "/N$(Quote $User) /P$(Quote $secret)" }
    }
    if ($Run -eq "D") {
        if (-not $FilePath) { Write-Host "Для D нужен -FilePath"; exit 1 }
        $target = "/IBConnectionString$(Quote "File=""$FilePath"";")"
    } else {
        $target = "/IBName$(Quote $IbName)"
    }
    return "ENTERPRISE $target $extra /AppAutoCheckVersion /AppAutoCheckMode".Trim()
}

if ($Run -eq "A") {
    # A не передаёт учётные данные вовсе — спрашивать пароль незачем.
    $password = ""
} else {
    $password = Read-Host "Пароль пользователя $User (в файл не попадёт)"
    if (-not $password) {
        Write-Host "Для запуска $Run нужен пароль"
        exit 1
    }
}

$arguments = Build-Arguments $password
$shown = Build-Arguments "<пароль>"

$before = (Get-FileHash $ibases -Algorithm SHA256).Hash
Write-Host ""
Write-Host "Запуск $Run`:"
Write-Host "  `"$Exe`" $shown"
Write-Host ""
Start-Process -FilePath $Exe -ArgumentList $arguments
Start-Sleep -Seconds 6

$snapshot = Get-CimInstance Win32_Process -Filter "Name='1cv8.exe' OR Name='1cv8c.exe'" |
    Select-Object -ExpandProperty CommandLine
$snapshotShown = $snapshot -join "`n"
if ($password) {
    # WMI отдаёт командную строку так, как она реально легла в память процесса:
    # для B/C/D пароль внутри кавычек Quote() — в удвоенной форме (pa"ss ->
    # pa""ss); для B2 без кавычек — в исходной. Гасим сначала удвоенную форму,
    # потом исходную, иначе неэкранированный "хвост" останется в открытом виде.
    $doubled = $password.Replace('"', '""')
    $snapshotShown = $snapshotShown.Replace($doubled, "<пароль>").Replace($password, "<пароль>")
}
Write-Host "Win32_Process.CommandLine (пароль заменён):"
Write-Host $snapshotShown
Write-Host ""

$dialog = Read-Host "Диалог авторизации появился? (y/n)"
$who = Read-Host "Под кем вошли (заголовок окна / «О программе»; пусто если не вошли)"
Read-Host "Закройте клиент 1С и нажмите Enter"
$after = (Get-FileHash $ibases -Algorithm SHA256).Hash
$changed = if ($before -eq $after) { "нет" } else { "ДА" }

$row = "| $Run | ``$shown`` | $dialog | $who | $changed |"
Add-Content -Path $results -Value $row -Encoding UTF8
Write-Host "Записано: $row"
```

> Блок выше — содержимое `docs/research/t05-14-launch-matrix.ps1` на коммите
> `b5af121`. Первая редакция плана несла дефект (Critical в ревью задачи 0a):
> `.Replace($password, …)` по уже собранной строке не находил удвоенную
> `Quote()` кавычку, и пароль с `"` уходил в файл результатов. Исправлено
> симметричной сборкой `$shown` той же функцией, что `$arguments`, и guard
> пустого пароля. План правится вслед за находкой.

- [ ] **Step 2: Шаблон результатов**

Создать `docs/research/t05-14-results.md`:

```markdown
# T-05.14 — /N /P при запуске по /IBName

Спека v2.2, §1. Заполняет скрипт `t05-14-launch-matrix.ps1`, запускает
заказчик. Пароль в этом файле не появляется — скрипт заменяет его
на `<пароль>` и в команде, и в снимке процесса.

Тестовая база: файловая, без конфигурации, пользователь `tester`,
аутентификация 1С включена, аутентификация ОС выключена. Готовность
подтверждена: запуск из штатного стартера спрашивает логин и пароль.

Версия платформы: <заполнить>. Дата: <заполнить>.

| Запуск | Команда | Диалог? | Вошли как | ibases.v8i изменился? |
| --- | --- | --- | --- | --- |
```

- [ ] **Step 3: Коммит**

```powershell
git add docs/research/t05-14-launch-matrix.ps1 docs/research/t05-14-results.md
git commit -m "research: T-05.14 — скрипт-помощник и шаблон результатов эксперимента /N /P"
```

**После этой задачи исполнение ОСТАНАВЛИВАЕТСЯ** до того, как заказчик
заведёт базу и прогонит A, B (при отказе — B2), C и при необходимости D.
Контроллер сообщает заказчику команду запуска скрипта и ждёт результатов.

---

## Task 0b: запись результата эксперимента в скил — гейт

**Files:**
- Modify: `docs/research/t05-14-results.md` (версия, дата, выводы)
- Modify: `.claude/skills/platform-launch/SKILL.md` (раздел «Пароль в командной строке — неустранимая утечка»)
- Modify: `.claude/skills/platform-launch/reference.md` (таблица ключей `/N`, `/P`)

**Interfaces:**
- Consumes: заполненную таблицу результатов.
- Produces: три факта [Ф] с датой, от которых зависят задачи 3 и 4:
  1. `CREDENTIALS_WORK_WITH_IBNAME` — да/нет;
  2. `CREDENTIAL_VALUE_QUOTED` — форма значения (`/N"tester"` или `/Ntester`);
  3. `CREDENTIALS_NEED_WA_MINUS` — нужен ли `/WA-`.

- [ ] **Step 1: Прочитать результаты и вынести вердикт**

Правило: по одному запуску вывод не делается. Если B (или B2) вошёл под
`tester` без диалога и `ibases.v8i` не изменился — результат 1 «да».
Если диалог появился в B и B2, но не в C — результат 3 «да». Если только
D вошёл без диалога — результат 1 «нет, только строкой соединения»,
и это возвращается контроллеру как **BLOCKED**: спека §1 требует
отдельного решения о компромиссе.

Если `ibases.v8i` изменился в любом запуске с `/P` — **BLOCKED**: платформа
дописала учётные данные в файл сама, DPAPI бессмысленно, веха останавливается.

- [ ] **Step 2: Дописать в `SKILL.md` после абзаца «Хранить только в Windows Credential Manager…»**

Пример для исхода «B с кавычками работает, /WA- не нужен»:

```markdown
**[Ф] <дата>, T-05.14:** при запуске по `/IBName` ключи `/N"<имя>" /P"<пароль>"`,
поставленные сразу после `/IBName`, перекрывают запись `.v8i`: клиент входит
под указанным пользователем без диалога. `/WA-` рядом не требуется. Форма
значения — как у `/IBName`: в кавычках, внутренние удвоены. `ibases.v8i`
после запуска не изменился — платформа учётные данные в файл не дописывает.
Снято на тестовой файловой базе без конфигурации, платформа <версия>.
```

При ином исходе текст правится по фактам; опровергнутое в скиле
исправляется, а не дописывается рядом.

- [ ] **Step 3: В `reference.md` у строк `/N<имя>` и `/P<пароль>` дописать столбец достоверности**

Строка 36–37 таблицы: добавить `**[Ф]** T-05.14` и измеренную форму значения.

- [ ] **Step 4: Коммит**

```powershell
git add docs/research/t05-14-results.md .claude/skills/platform-launch/SKILL.md .claude/skills/platform-launch/reference.md
git commit -m "research: T-05.14 — [Ф] /N /P при /IBName, форма значения, /WA-"
```

---

## Task 1: keyring-гейт — round-trip внутри замороженной сборки

**Files:**
- Modify: `src/onecstarter/ui/app.py` (`run_smoke`, около строки 247)
- Modify: `build/onecstarter.spec:57-70` (`Analysis(...)`)
- Modify: `build/smoke.py` (проверка строки лога)
- Test: `tests/ui/test_app.py`

**Interfaces:**
- Consumes: ничего из задач 2–6 — гейт намеренно идёт до них и использует
  `keyring` напрямую.
- Produces: решение «`keyring` или `ctypes`» для задачи 2 (спека §9).

`keyring` ищет бэкенды через entry points; PyInstaller без `hiddenimports`
их не находит, и в frozen-сборке все операции молча отказывают. Проверить
это можно только внутри собранного exe — поэтому round-trip живёт
в `run_smoke`, а `build/smoke.py` читает результат из лога.

- [ ] **Step 1: Падающий тест — `run_smoke` пишет `smoke: keyring=ok`**

В `tests/ui/test_app.py` рядом с существующими тестами `run_smoke`:

```python
class _MemoryVault:
    """Хранилище в памяти — тест не трогает настоящий Credential Manager."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def read(self, key: str) -> str | None:
        return self.data.get(key)

    def write(self, key: str, secret: str) -> None:
        self.data[key] = secret

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def test_smoke_logs_keyring_round_trip(tmp_path, qapp):
    """Самопроверка сборки обязана доказать, что хранилище паролей работает
    именно в собранном экземпляре (спека v2.2, §9): без hiddenimports keyring
    в frozen-сборке молча уходит в пустой бэкенд."""
    vault = _MemoryVault()
    env = {"APPDATA": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}  # как у соседей
    code = run_smoke(str(tmp_path), env, credential_store=vault)

    assert code == 0
    assert "smoke: keyring=ok" in caplog.text  # лог run_smoke читается через caplog
    assert vault.data == {}, "служебная запись обязана быть удалена после проверки"
```

(Сигнатура теста получает фикстуру `caplog`.) Первая редакция плана
выдумала помощник `_smoke_env` и файл `smoke.log` — их в проекте нет:
соседние тесты `run_smoke` строят окружение inline и читают лог через
`caplog`. Исполнитель задачи 1 пошёл по факту; текст приведён к нему.

> **Добавлено по итогам ревью задачи 1 (коммиты bd1ffdc, 54b9bfe).** Линейная
> форма `write → read → delete → read` оставляла служебную запись, если первый
> `read()` бросал; `delete()` ушёл в `finally`, отказ самого удаления не
> заслоняет причину чтения (guard `if result is None`). Это сторожат два
> регрессионных теста в `tests/ui/test_app.py`:
>
> - `test_smoke_keyring_round_trip_deletes_record_even_when_read_fails` —
>   хранилище, у которого `read()` бросает после успешного `write()`:
>   `assert vault.data == {}` и `"smoke: keyring=FAIL: RuntimeError" in caplog.text`;
> - `test_smoke_keyring_round_trip_keeps_read_failure_over_delete_failure` —
>   `read()` бросает `ValueError`, `delete()` — `RuntimeError`:
>   `"smoke: keyring=FAIL: ValueError" in caplog.text` и `"RuntimeError" not in caplog.text`.
>
> Мутации: снять guard → второй тест падает (причина подменена); снять
> `try/except` вокруг `delete` в `finally` → исключение вылетает из
> `run_smoke`, строки `keyring=` нет.

- [ ] **Step 2: Убедиться, что падает**

Run: `uv run pytest tests/ui/test_app.py -k keyring_round_trip -v`
Expected: FAIL — `TypeError: run_smoke() got an unexpected keyword argument 'credential_store'`

- [ ] **Step 3: Реализация в `run_smoke`**

Параметр и проверка. Без инъекции — настоящий `keyring` под служебным
именем; служебное имя обязательно: Credential Manager не привязан
к `APPDATA`, который подменяет smoke.

```python
SMOKE_VAULT_SERVICE = "OneCStarter-smoke"
SMOKE_VAULT_KEY = "round-trip"


class _KeyringSmokeVault:
    """Настоящий keyring под служебным именем: проверка сборки, не данных."""

    def read(self, key: str) -> str | None:
        import keyring

        return keyring.get_password(SMOKE_VAULT_SERVICE, key)

    def write(self, key: str, secret: str) -> None:
        import keyring

        keyring.set_password(SMOKE_VAULT_SERVICE, key, secret)

    def delete(self, key: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(SMOKE_VAULT_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def _keyring_round_trip(vault: object) -> str:
    """`ok` либо причина отказа — одной строкой, без секрета.

    Удаление служебной записи (`vault.delete`) — в `finally` (находка ревью
    задачи 1, Important): раньше `delete()` стоял линейно между двумя
    чтениями, и отказ ПЕРВОГО чтения оставлял запись непотревоженной —
    до вызова `delete()` дело просто не доходило. То же с отказом самого
    удаления: `_KeyringSmokeVault.delete` глотает только `PasswordDeleteError`
    keyring, любое другое исключение раньше вылетало наружу необработанным
    и подменяло собой причину более раннего отказа. Оба случая оставляли
    мусор в настоящем Credential Manager машины сборщика — ровно то, что
    запрещает спека §9. `finally` гарантирует попытку удаления при любом
    исходе чтения; собственный `except Exception` внутри `finally` — чтобы
    отказ САМОГО удаления не заслонил более раннюю причину (`result`,
    захваченный до входа в `finally`) и не прервал функцию раньше
    контрольного чтения `gone` ниже.
    """  # noqa: RUF002
    probe = "smoke"
    try:
        vault.write(SMOKE_VAULT_KEY, probe)  # type: ignore[attr-defined]
    except Exception as error:
        # Самопроверка сборки: любая причина отказа обязана попасть в лог
        # строкой, а не уронить smoke трассировкой. Правило BLE в ruff проекта  # noqa: RUF003
        # не включено — noqa здесь был бы лишним и пойман RUF100.
        return f"FAIL: {type(error).__name__}"

    result: str | None = None
    got: str | None = None
    try:
        got = vault.read(SMOKE_VAULT_KEY)  # type: ignore[attr-defined]
    except Exception as error:
        result = f"FAIL: {type(error).__name__}"
    finally:
        try:
            vault.delete(SMOKE_VAULT_KEY)  # type: ignore[attr-defined]
        except Exception as error:
            if result is None:
                result = f"FAIL: {type(error).__name__}"
    if result is not None:
        return result
    if got != probe:
        return "FAIL: прочитано не то, что записано"

    try:
        gone = vault.read(SMOKE_VAULT_KEY)  # type: ignore[attr-defined]
    except Exception as error:
        return f"FAIL: {type(error).__name__}"
    if gone is not None:
        return "FAIL: запись не удалилась"
    return "ok"

# Блок выше — функция как она закоммичена в bd1ffdc после раунда правок:
# первая редакция плана звала delete() линейно между двумя read(), и отказ
# первого чтения оставлял служебную запись в Credential Manager (Important
# в ревью задачи 1). План правится вслед за находкой.
```

В сигнатуру `run_smoke` добавить `credential_store: object | None = None`;
перед итоговым `return 0` (там, где пишется `smoke: frozen=…`) добавить
той же функцией записи в лог строку:

```python
    vault = credential_store if credential_store is not None else _KeyringSmokeVault()
    log(f"smoke: keyring={_keyring_round_trip(vault)}")
```

(`log` — то же имя, которым в `run_smoke` пишется строка `smoke: frozen=`;
взять из кода, не выдумывать.)

- [ ] **Step 4: Тест проходит**

Run: `uv run pytest tests/ui/test_app.py -k keyring_round_trip -v`
Expected: PASS.

- [ ] **Step 5: Мутация**

Убрать `vault.delete(SMOKE_VAULT_KEY)` из `_keyring_round_trip`.
Expected: FAIL в `test_smoke_logs_keyring_round_trip` — `vault.data == {}`
нарушено. Откатить правкой файла.

- [ ] **Step 6: `hiddenimports` и проверка в `build/smoke.py`**

В `build/onecstarter.spec` в `Analysis(...)` после `datas=[...]`:

```python
    # keyring находит бэкенды через entry points — анализ импортов PyInstaller
    # их не видит, и без этой строки frozen-сборка молча уходит в пустой бэкенд
    # (спека v2.2, §9). Гейт — строка `smoke: keyring=ok` в самопроверке.
    hiddenimports=["keyring.backends.Windows"],
```

В `build/smoke.py` после проверки `sys.frozen` (там, где читается лог):

```python
        if "smoke: keyring=ok" not in log_text:
            print("smoke: хранилище паролей не работает в сборке — см. строку smoke: keyring= в логе")
            return 1
```

(`log_text` — та переменная, в которой уже лежит содержимое лога для
проверок «фаза окно показано» и `sys.frozen`.)

- [ ] **Step 7: Сборка и гейт**

Из PowerShell-инструмента (правило проекта):

```powershell
powershell -File build/build.ps1 -SkipInstaller
```

Expected: `smoke: OK`. Если `smoke: keyring=FAIL: …` — сначала проверить,
что `hiddenimports` попал в spec и сборка пересобрана с нуля. Если после
этого всё равно FAIL — **остановиться и вернуть контроллеру BLOCKED** с текстом
строки: спека §9 предписывает откат на `ctypes` решением, а не тихо.

- [ ] **Step 8: Линт, типы, коммит**

```powershell
uv run ruff check .
uv run mypy
git add src/onecstarter/ui/app.py build/onecstarter.spec build/smoke.py tests/ui/test_app.py
git commit -m "build: keyring-гейт — round-trip Credential Manager внутри frozen-сборки"
```

---

## Task 2: `security/` — хранилище и редакция командной строки

**Files:**
- Create: `src/onecstarter/security/credentials.py`
- Modify: `src/onecstarter/security/secrets.py` (добавить `redact_arguments`)
- Modify: `tests/unit/test_no_qt_in_core.py:38` (добавить модуль в `CORE`)
- Create: `tests/unit/test_credentials.py`
- Modify: `tests/unit/test_secrets.py`

**Interfaces:**
- Produces:
  - `CredentialStore` — Protocol: `read(key: str) -> str | None`,
    `write(key: str, secret: str) -> None`, `delete(key: str) -> None`
  - `KeyringStore(service: str = "OneCStarter")` — реализация над `keyring`
  - `MemoryStore()` — в памяти, для тестов и самопроверки; атрибут `data: dict[str, str]`
  - `CredentialBackendError(Exception)` — единственное, что поднимает `KeyringStore`
  - `redact_arguments(arguments: str) -> str`; константа `HIDDEN_ARGUMENTS`

- [ ] **Step 1: Падающие тесты хранилища**

Создать `tests/unit/test_credentials.py`:

```python
"""Хранилище паролей: контракт Protocol на фейке и перевод ошибок keyring."""

import pytest

from onecstarter.security.credentials import (
    CredentialBackendError,
    KeyringStore,
    MemoryStore,
)


def test_memory_store_round_trip() -> None:
    store = MemoryStore()
    store.write("id:x", "p@ss")
    assert store.read("id:x") == "p@ss"
    store.delete("id:x")
    assert store.read("id:x") is None


def test_memory_store_delete_of_missing_is_silent() -> None:
    """Удаление отсутствующего — не ошибка: снятие «Запомнить» у записи
    без пароля обязано проходить молча (спека v2.2, §3)."""
    MemoryStore().delete("id:nope")


def test_keyring_store_translates_keyring_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слой выше не знает про keyring — ему нужен один тип отказа."""
    import keyring
    import keyring.errors

    def boom(*_args: object, **_kwargs: object) -> None:
        raise keyring.errors.KeyringError("нет бэкенда")

    monkeypatch.setattr(keyring, "set_password", boom)
    with pytest.raises(CredentialBackendError):
        KeyringStore(service="OneCStarter-test").write("id:x", "p@ss")


def test_keyring_store_delete_of_missing_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring
    import keyring.errors

    def missing(*_args: object, **_kwargs: object) -> None:
        raise keyring.errors.PasswordDeleteError("нет такой")

    monkeypatch.setattr(keyring, "delete_password", missing)
    KeyringStore(service="OneCStarter-test").delete("id:nope")


def test_importing_the_module_does_not_import_keyring() -> None:
    """[Ф] 06.09.2026: import keyring ~200 мс; модуль тянет Workspace на каждом
    старте — keyring обязан грузиться лениво, при первом обращении."""
    import subprocess
    import sys

    probe = (
        "import sys; import onecstarter.security.credentials; "
        "print('keyring' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_failure_repr_never_carries_the_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Текст отказа уходит пользователю — секрета в нём быть не может.

    Проверка идёт через настоящий путь отказа, а не через сконструированное
    вручную исключение с безопасным текстом: `keyring.errors.KeyringError`
    в проде может нести что угодно, включая пароль (`keyring` этого не
    гарантирует), и именно поэтому `_reason` берёт только имя типа —
    здесь это подтверждается, а не постулируется.
    """  # noqa: RUF002
    import keyring
    import keyring.errors

    def boom(*_args: object, **_kwargs: object) -> None:
        raise keyring.errors.KeyringError("отказ, пароль p@ss отвергнут")

    monkeypatch.setattr(keyring, "set_password", boom)
    with pytest.raises(CredentialBackendError) as excinfo:
        KeyringStore(service="OneCStarter-test").write("id:x", "p@ss")
    error = excinfo.value
    assert "p@ss" not in str(error)
    assert "p@ss" not in repr(error)
    assert not any("p@ss" in str(arg) for arg in error.args)
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_credentials.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'onecstarter.security.credentials'`

- [ ] **Step 3: Реализация**

Создать `src/onecstarter/security/credentials.py`:

```python
"""Хранилище паролей записей — Windows Credential Manager через `keyring`.

Инвариант 5: секреты — только через `security/`. Слои выше видят Protocol
и один тип отказа; про `keyring` они не знают. Тот же приём инъекции, что
у `services/autostart.py::Registry`: настоящая реализация в проде, фейк
в памяти — в тестах и самопроверке сборки.

Почему `keyring`, а не своя обёртка над `advapi32`: он зависимость с 0.1.0,
под капотом те же `CredRead`/`CredWrite`, и его не надо сопровождать.
[Ф] 04.09.2026: на машине заказчика `keyring` 25.7.0 выбирает
`WinVaultKeyring` без настройки. Цена — упаковка: без `hiddenimports`
frozen-сборка молча уходит в пустой бэкенд, гейт — задача 1 плана v2.2.

Имя записи в хранилище — ключ привязки базы (`services/model.py::
binding_key`): тот же, что у избранного и истории, поэтому при смене
ключа (`Workspace._write(rekey_from=…)`) секрет переезжает вместе с ними.

`keyring` импортируется ЛЕНИВО, внутри методов, а не на уровне модуля:
[Ф] 06.09.2026 — `import keyring` стоит ~200 мс (тянет `keyring.core`),
первый `get_keyring()` — ещё ~55 мс на entry points. Этот модуль
импортирует `Workspace`, то есть каждый старт программы; платить 200 мс
за функцию, которую большинство не включит, нельзя. Тот же приём, что
у `_KeyringSmokeVault` в `ui/app.py` (задача 1 вехи v2.2).
"""  # noqa: RUF002

from typing import Protocol

SERVICE = "OneCStarter"


class CredentialBackendError(Exception):
    """Хранилище отказало. Текст — только причина, никогда не секрет."""


class CredentialStore(Protocol):
    def read(self, key: str) -> str | None: ...

    def write(self, key: str, secret: str) -> None: ...

    def delete(self, key: str) -> None: ...


class KeyringStore:
    """Настоящее хранилище. `delete` отсутствующей записи — не ошибка:
    снятие «Запомнить» у записи без пароля обязано проходить молча."""

    def __init__(self, service: str = SERVICE) -> None:
        self._service = service

    def read(self, key: str) -> str | None:
        import keyring
        import keyring.errors

        try:
            return keyring.get_password(self._service, key)
        except keyring.errors.KeyringError as error:
            raise CredentialBackendError(_reason(error)) from error

    def write(self, key: str, secret: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.set_password(self._service, key, secret)
        except keyring.errors.KeyringError as error:
            raise CredentialBackendError(_reason(error)) from error

    def delete(self, key: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(self._service, key)
        except keyring.errors.PasswordDeleteError:
            return
        except keyring.errors.KeyringError as error:
            raise CredentialBackendError(_reason(error)) from error


class MemoryStore:
    """Хранилище в памяти — тесты и самопроверка сборки. Настоящий
    Credential Manager машины не трогается."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def read(self, key: str) -> str | None:
        return self.data.get(key)

    def write(self, key: str, secret: str) -> None:
        self.data[key] = secret

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def _reason(error: Exception) -> str:
    """Причина без секрета: keyring в тексте ошибки пароль не печатает,
    но полагаться на это нельзя — берётся только имя типа."""
    return f"диспетчер учётных данных Windows: {type(error).__name__}"
```

В `tests/unit/test_no_qt_in_core.py` в кортеж `CORE` после
`"onecstarter.security.secrets",` добавить `"onecstarter.security.credentials",`.

- [ ] **Step 4: Тесты проходят, включая стража Qt**

Run: `uv run pytest tests/unit/test_credentials.py tests/unit/test_no_qt_in_core.py -v`
Expected: PASS.

- [ ] **Step 5: Падающие тесты редакции**

В `tests/unit/test_secrets.py` дописать:

```python
from onecstarter.security.secrets import HIDDEN_ARGUMENTS, redact_arguments


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ('ENTERPRISE /IBName"x" /AppAutoCheckVersion', 'ENTERPRISE /IBName"x" /AppAutoCheckVersion'),
        ('ENTERPRISE /IBName"x" /N"u" /P"p@ss" /AppAutoCheckVersion',
         'ENTERPRISE /IBName"x" /N"u" /P*** /AppAutoCheckVersion'),
        # Кавычка внутри пароля удвоена формой quote_launch_value — закрывающая
        # граница остаётся однозначной.
        ('/IBName"x" /N"u" /P"a""b" /AppAutoCheckMode', '/IBName"x" /N"u" /P*** /AppAutoCheckMode'),
        # Форма без кавычек (если T-05.14 подтвердит её) — до пробела.
        ("/IBName\"x\" /Nu /Pp@ss /AppAutoCheckMode", '/IBName"x" /Nu /P*** /AppAutoCheckMode'),
        # Непарная кавычка — границы значений недостоверны, показывать нельзя.
        ('/IBName"x" /P"p@ss /AppAutoCheckMode', HIDDEN_ARGUMENTS),
        ("", ""),
    ],
)
def test_redact_arguments(arguments: str, expected: str) -> None:
    assert redact_arguments(arguments) == expected


def test_redact_arguments_never_leaves_the_value() -> None:
    """Сторож fail-closed: при любом исходе значения /P в выводе нет."""
    for arguments in ('/P"p@ss"', "/Pp@ss", '/P"p@ss', '/IBName"a" /P"p@ss" /N"u"'):
        assert "p@ss" not in redact_arguments(arguments)

def test_recursive_group_removal_deletes_the_secrets(tmp_path: Path) -> None:
    """Секреты записей, удалённых вместе с группой, уходят из хранилища.

    Иначе суррогатный ключ секции без ID достался бы новой записи с тем же
    именем и строкой соединения — вместе с «удалённым» паролем. Контроль:
    запись вне группы пароль сохраняет.
    """  # noqa: RUF002
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    # Поддерево «Клиенты» (id:1111…) в фикстуре: подгруппа «Розница» (id:2222…,
    # без Connect — у групп секретов не бывает) и ровно две базы.
    nested = [
        "id:44444444-4444-4444-4444-444444444444",  # Демо Бухгалтерия, /Клиенты
        "id:55555555-5555-5555-5555-555555555555",  # Демо Розница, /Клиенты/Розница
    ]
    outside = "id:66666666-6666-6666-6666-666666666666"  # Учёт серверный, /
    for key in [*nested, outside]:
        workspace.set_credentials(key, "tester", "p@ss", remember=True)

    assert workspace.remove_group(
        "id:11111111-1111-1111-1111-111111111111", GroupRemoval.RECURSIVE
    )

    assert not any(key in store.data for key in nested)
    assert store.data[outside] == "p@ss"
```

- [ ] **Step 6: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_secrets.py -k redact_arguments -v`
Expected: FAIL — `ImportError: cannot import name 'HIDDEN_ARGUMENTS'`

- [ ] **Step 7: Реализация `redact_arguments`**

В `src/onecstarter/security/secrets.py` добавить:

```python
HIDDEN_ARGUMENTS = "<командная строка скрыта>"


def is_secret_key(name: str) -> bool:
    """Несёт ли ключ строки соединения пароль.

    Имя обрезается по краям: `Pwd ` с пробелом перед «=» — тот же пароль,
    что и `Pwd`. Пробелы вокруг «=» в файлах пользователя не гипотетика —
    скил v8i-format фиксирует их отдельным измеренным фактом (факт 6:
    платформа не распознаёт такой ключ и добивает секцию). Направление
    обрезки безопасное: секретов распознаётся больше, не меньше.
    """  # noqa: RUF002
    normalized = name.strip().casefold()
    return normalized in _SECRET_KEYS or normalized.endswith(_SECRET_SUFFIX)


def redact_connect(connect: str) -> str:
    """Строка соединения без значений секретных ключей — для показа человеку.

    Политика — fail-closed: там, где разбор перестаёт быть однозначным,
    возвращается заглушка вместо строки. Показать строку частично хуже,
    чем не показать вовсе, — пароль из неё уже не отозвать
    (инвариант 5 CLAUDE.md).

    Разобранная строка пересобирается заново из фрагментов, а не правится
    поиском и заменой: значение секретного ключа в вывод не переносится
    вообще. Замена по совпадению значения так не умеет — parse_connect
    снимает кавычки, и значение с экранированной кавычкой в исходном тексте
    не находится, а одинаковые значения у секретного и обычного ключа
    затираются оба.

    Скрывается строка целиком в трёх случаях:

    - непарные кавычки: разбор склеивает хвост строки в значение соседнего
      фрагмента, и `Pwd="secret"` печатается дословно внутри значения
      несекретного ключа;
    - непустая строка, из которой не вышло ни одного фрагмента (`Pwd"x"`
      без «=»): показывать было бы нечего, кроме исходного текста;
    - в собранном результате остался секретный ключ с настоящим значением —
      признак того, что границы фрагментов разъехались.

    Разобранная строка при этом нормализуется: исходные кавычки, пробелы
    и фрагменты без «=» не сохраняются. Это допустимо — результат идёт
    в сообщение пользователю и обратно в .v8i не пишется никогда.

    **Гарантия не абсолютная.** Проверки закрывают строки, у которых разбор
    расходится с исходным текстом наблюдаемым образом. Остаётся класс
    испорченных строк, где кавычки парные, разбор при этом устойчив, а
    секрет спрятан внутри значения несекретного ключа: `Usr=a"b;Pwd=x"c;`
    разбирается в один фрагмент `Usr` и повторным разбором не ловится.
    Это известное ограничение, а не оплошность: закрыть его можно только
    разбором строки соединения по правилам платформы, которые
    экспериментально не сняты (скил v8i-format, «Непроверенное»).
    """  # noqa: RUF002
    if not connect.strip():
        # Скрывать нечего: пустая строка секрета не несёт.
        return connect
    if connect.count('"') % 2:
        return _HIDDEN
    fragments = parse_connect(connect)
    if not fragments:
        return _HIDDEN
    parts = [
        f"{fragment.name}={_MASK}"
        if is_secret_key(fragment.name) and fragment.value
        else f"{fragment.name}={fragment.value}"
        for fragment in fragments
    ]
    redacted = ";".join(parts) + ";"
    if _leaks_secret(redacted):
        return _HIDDEN
    return redacted


def strip_url_credentials(url: str) -> str | None:
    """Адрес без `user:pass@` и без query-параметров с секретным именем.

    `None` — показать адрес надёжно не вышло. Политика fail-closed, как
    у `redact_connect`: где разбор перестаёт быть однозначным, показывать
    нельзя вовсе.

    Разбор идёт `urllib.parse.urlsplit` безусловно — даже когда в строке нет
    буквального «@». Раньше был ранний выход `if "@" not in url: return url`,
    и это был баг, а не оптимизация: `urlsplit` сам NFKC-нормализует authority
    и поднимает `ValueError`, если нормализация вносит новый «/», «?», «#»,
    «@» или «:» — то есть сам ловит юникодных двойников «собаки»
    (`＠` U+FF20, `﹫` U+FE6B и подобные). Ранний выход по буквальному «@»
    обходил этот разбор стороной и пропускал двойника на экран, потому что
    для него `"@" not in url` было истинным. Наивный поиск «@» до первого
    «/» тоже не годится: он ошибается на `http://user:pa/ss@srv/base`,
    где authority обрывается на незакодированном «/», и хвост с паролем
    уезжает в путь. Стандартный парсер режет оба случая по RFC.

    Четыре исхода, где возвращается `None`:

    - `urlsplit` или разбор порта подняли `ValueError` — адрес не разбирается
      (сюда же попадают юникодные двойники «собаки» в authority, см. выше);
    - query-строка несёт параметр с секретным именем (`is_secret_key`) —
      скрывается весь адрес, а не только параметр: показать частично хуже,
      чем не показать вовсе (та же политика, что у `redact_connect`).
      Проверяется до решения про «@», поэтому работает и для адресов
      без учётных данных в authority;
    - «@» есть — буквально или после NFKC-нормализации всей строки, чем
      заодно ловятся двойники вне authority, — но не в authority:
      `urlsplit("user:pass@srv/base")` принимает «user» за схему,
      и пароль остался бы в пути;
    - после пересборки «@» всё ещё на месте: границы разъехались.

    IPv6-хост `hostname` отдаёт без скобок (`::1`, не `[::1]`) — их нужно
    вернуть явно перед пересборкой: `urlunsplit` с голым `::1:8080` вместо
    `[::1]:8080` даёт адрес, который `urlsplit` обратно не разбирает.

    Плата за fail-closed — законный «@» в пути (`http://srv/base@2`) тоже
    скрывается. Это осознанный обмен: адрес хоста пользователь узнает
    из диалога свойств, а пароль из буфера обмена уже не отозвать
    (инвариант 5 CLAUDE.md).
    """  # noqa: RUF002
    try:
        split = urlsplit(url)
        netloc = split.netloc
        host = split.hostname or ""
        port = split.port
    except ValueError:
        return None
    query_names = (name for name, _value in parse_qsl(split.query, keep_blank_values=True))
    if any(is_secret_key(name) for name in query_names):
        return None
    if "@" not in unicodedata.normalize("NFKC", url):
        return url
    if "@" not in netloc:
        return None
    if ":" in host:
        host = f"[{host}]"
    if port is not None:
        host = f"{host}:{port}"
    cleaned = urlunsplit((split.scheme, host, split.path, split.query, split.fragment))
    return None if "@" in cleaned else cleaned


def _leaks_secret(redacted: str) -> bool:
    """Остался ли в собранном результате секретный ключ с настоящим значением.

    Проверка идёт по повторному разбору вывода: если границы фрагментов
    при первом разборе разъехались, спрятанный внутри чужого значения
    `Pwd=...` всплывает здесь отдельным фрагментом.
    """  # noqa: RUF002
    return any(
        is_secret_key(fragment.name) and fragment.value not in ("", _MASK)
        for fragment in parse_connect(redacted)
    )


def _tokenize_arguments(arguments: str) -> list[str] | None:
    """Командная строка → токены с учётом кавычек, либо `None` при их разъезде.

    Вне кавычек пробел завершает токен. Кавычка открывает режим цитирования;
    внутри него удвоенная кавычка (`""`, форма `quote_launch_value`) —
    экранированная пара и остаётся частью токена как есть, одиночная —
    закрывает режим. Конец строки при незакрытой кавычке — `None`: граница
    токенов недостоверна, редактировать по ним нельзя (fail-closed, та же
    политика, что у непарной кавычки в `redact_connect`).
    """  # noqa: RUF002
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    index = 0
    length = len(arguments)
    while index < length:
        char = arguments[index]
        if in_quotes:
            if char == '"':
                if index + 1 < length and arguments[index + 1] == '"':
                    current.append('""')
                    index += 2
                    continue
                current.append('"')
                in_quotes = False
            else:
                current.append(char)
            index += 1
            continue
        if char == " ":
            if current:
                tokens.append("".join(current))
                current = []
        elif char == '"':
            current.append('"')
            in_quotes = True
        else:
            current.append(char)
        index += 1
    if in_quotes:
        return None
    if current:
        tokens.append("".join(current))
    return tokens


def redact_arguments(arguments: str) -> str:
    """Командная строка запуска без значения `/P` — для сообщений и исходов.

    Строка сначала разбирается на токены (`_tokenize_arguments`), потом
    пересобирается — та же схема, что у `redact_connect`, и по той же
    причине: правка по сырому тексту не различает настоящий `/P` и мнимый
    внутри чужого значения (`/IBName"a/P"`), из-за чего секрет может
    просочиться в вывод (находка ревью задачи 2, 06.09.2026).

    Каждый токен, начинающийся с `/P` (включая `/PP...` — переизбыточная
    редакция безопасна: [Д] других ключей на `/P` в режиме `ENTERPRISE`
    нет), заменяется целиком на `/P***` — форма значения для читателя роли
    не играет, а секрет из сообщения уже не отозвать. Незакрытая кавычка
    делает границы токенов недостоверными: показывается заглушка, а не
    строка частично. Токены при пересборке разделяются одним пробелом —
    нормализация допустима по той же причине, что и в `redact_connect`.
    """  # noqa: RUF002
    tokens = _tokenize_arguments(arguments)
    if tokens is None:
        return HIDDEN_ARGUMENTS
    return " ".join("/P***" if token.startswith("/P") else token for token in tokens)
```

> Блок выше — код `secrets.py` на коммите f80680a. Первая редакция плана
> держала регулярку по сырой строке; ревью задачи 2 воспроизвело утечку
> (`/IBName"a/P" /P"secret"` → secret в выводе). Заменено разбором
> на токены с учётом кавычек и пересборкой — тот же приём, что
> у `redact_connect`. Вакуумный тест первой редакции заменён тестом
> через реальный путь `KeyringStore.write` с секретом в тексте исключения.

Обновить докстринг модуля `secrets.py`: к списку «что тут определено»
дописать абзац о `redact_arguments` — исходный текст не сокращать.

- [ ] **Step 8: Тесты проходят**

Run: `uv run pytest tests/unit/test_secrets.py -v`
Expected: PASS.

- [ ] **Step 9: Мутации**

1. В `redact_arguments` убрать проверку непарной кавычки.
   Expected: FAIL в `test_redact_arguments` (случай с заглушкой)
   и в `test_redact_arguments_never_leaves_the_value`.
2. В `MemoryStore.delete` заменить `pop(key, None)` на `del self.data[key]`.
   Expected: FAIL в `test_memory_store_delete_of_missing_is_silent`.
3. Поднять `import keyring` на уровень модуля `credentials.py`.
   Expected: FAIL в `test_importing_the_module_does_not_import_keyring`.

Откатить правкой файлов.

- [ ] **Step 10: Линт, типы, коммит**

```powershell
uv run ruff check .
uv run mypy
git add src/onecstarter/security/credentials.py src/onecstarter/security/secrets.py tests/unit/test_credentials.py tests/unit/test_secrets.py tests/unit/test_no_qt_in_core.py
git commit -m "feat: security — хранилище паролей над keyring и редакция /P в командной строке"
```

---

## Task 3: `domain/launch.py` — `Credentials` и сборка аргументов

**Files:**
- Modify: `src/onecstarter/domain/launch.py` (`build_arguments`, около строки 98)
- Modify: `tests/unit/test_launch.py` (класс `TestBuildArguments`)

**Interfaces:**
- Consumes: результат задачи 0b — форма значения и нужен ли `/WA-`.
- Produces: `Credentials(login: str, password: str | None = None)` — frozen,
  `password` с `repr=False`; `build_arguments(..., credentials: Credentials | None = None)`.

Код ниже — для исхода «B с кавычками работает, `/WA-` не нужен». При ином
исходе задачи 0b меняется **только** `_credential_arguments`:

| Исход 0b | Что меняется |
| --- | --- |
| форма без кавычек | `f"/N{login} /P{password}"` без `quote_launch_value`; тест с кавычкой в пароле заменяется на тест отказа `ValueError` — в такой форме пробел и кавычка не передаются |
| нужен `/WA-` | к строке добавляется ` /WA-`, ожидание в тестах — соответственно |
| работает только D | задача 3 приостанавливается, контроллер возвращает вопрос заказчику (спека §1) |

- [ ] **Step 1: Падающие тесты**

В `tests/unit/test_launch.py` в класс `TestBuildArguments`:

```python
    def test_credentials_go_right_after_ibname(self) -> None:
        """[Ф] T-05.14: /N /P сразу после /IBName, форма значения — как у /IBName."""
        arguments = build_arguments(
            ClientKind.THIN,
            ib_name="empty",
            auto_check_version=True,
            auto_check_mode=True,
            credentials=Credentials("tester", "p@ss"),
        )
        assert arguments == (
            'ENTERPRISE /IBName"empty" /N"tester" /P"p@ss" /AppAutoCheckVersion /AppAutoCheckMode'
        )

    def test_login_without_password_passes_only_n(self) -> None:
        """Спека v2.2, §4: один /N — платформа спросит только пароль."""
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=True,
            auto_check_mode=True, credentials=Credentials("tester"),
        )
        assert arguments == 'ENTERPRISE /IBName"empty" /N"tester" /AppAutoCheckVersion /AppAutoCheckMode'

    def test_quote_in_password_is_doubled(self) -> None:
        arguments = build_arguments(
            ClientKind.THIN, ib_name="empty", auto_check_version=True,
            auto_check_mode=True, credentials=Credentials("u", 'a"b'),
        )
        assert '/P"a""b"' in arguments

    def test_credentials_never_appear_in_repr(self) -> None:
        """Дефолтный repr датакласса печатал бы пароль в любой трассировке
        и в `pytest -rA` (инвариант 5)."""
        credentials = Credentials("tester", "p@ss")
        assert "p@ss" not in repr(credentials)
        assert "p@ss" not in str(credentials)
        assert "tester" in repr(credentials)

    def test_connect_string_path_still_rejects_secrets_with_credentials(self) -> None:
        """Страж строки соединения не ослабляется новым аргументом."""
        with pytest.raises(ValueError, match="Pwd"):
            build_arguments(
                ClientKind.THIN, connect='File="D:\\b";Pwd="x";',
                auto_check_version=True, auto_check_mode=True,
                credentials=Credentials("u", "p"),
            )
```

Импорт: `from onecstarter.domain.launch import Credentials` к существующим.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_launch.py -k "credentials or login_without or quote_in_password" -v`
Expected: FAIL — `ImportError: cannot import name 'Credentials'`

- [ ] **Step 3: Реализация**

В `src/onecstarter/domain/launch.py` после `ClientConvention`:

```python
@dataclass(frozen=True)
class Credentials:
    """Учётные данные для `/N` и `/P`. `password` не печатается в `repr`:
    дефолтный repr датакласса выводил бы его в любую трассировку
    и в `pytest -rA` (инвариант 5). `None` — только логин, платформа
    спросит пароль сама (спека v2.2, §4)."""

    login: str
    password: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Граница домена: пустой логин = логина нет (спека §4). Services
        # нормализуют до конструирования; сюда пустое не доходит штатно.
        if not self.login.strip():
            raise ValueError("логин пуст")


def _credential_arguments(credentials: Credentials) -> str:
    """[Ф] <дата> T-05.14: форма значения — как у /IBName, в кавычках
    с удвоением; /WA- рядом не требуется. При ином результате эксперимента
    меняется только эта функция."""
    parts = [f"/N{quote_launch_value(credentials.login)}"]
    if credentials.password is not None:
        parts.append(f"/P{quote_launch_value(credentials.password)}")
    return " ".join(parts)
```

(`field` — добавить в импорт из `dataclasses`.)

В `build_arguments` добавить параметр `credentials: Credentials | None = None`
и после строки `parts.append(f"/IBName{quote_launch_value(ib_name)}")`:

```python
        if credentials is not None:
            parts.append(_credential_arguments(credentials))
```

Для ветки строки соединения — то же, но **после** `parts.append(
f"/IBConnectionString…")`: [Д] reference.md — части строки соединения
переопределяются ключами, стоящими в командной строке позже; `Usr=` в
строке не секрет и стража проходит, и явный логин обязан его перекрыть:

```python
        if credentials is not None:
            parts.append(_credential_arguments(credentials))
```

Докстринг модуля: абзац «Секреты в аргументы не попадают: основной путь
запуска — /IBName…» дописать, не заменяя: «С v2.2 учётные данные записи
попадают в аргументы **явно** через `credentials=` — по решению заказчика
04.09.2026 с записанной моделью угроз (спека v2.2, §2); страж секретов
в строке соединения остаётся».

> **Правки вслед за ревью задачи 3 (06.09.2026).** `compare=False` у пароля:
> pytest строит диф полей по `field.compare`, а не по `field.repr`, и упавший
> `assert a == b` печатал бы пароль; `__post_init__` отвергает пустой логин
> (`/N""` не должен собираться); в ветке `connect=` учётные данные идут ПОСЛЕ
> `/IBConnectionString` — [Д] поздний ключ перекрывает часть строки. Первая
> редакция плана всех трёх вещей не учитывала. Тесты: равенство при разных
> паролях, порядок в ветке строки соединения, отказ на пустом логине.

- [ ] **Step 4: Тесты проходят**

Run: `uv run pytest tests/unit/test_launch.py -v`
Expected: PASS, включая семь прежних тестов стража.

- [ ] **Step 5: Мутация**

Убрать `repr=False` у `password`.
Expected: FAIL в `test_credentials_never_appear_in_repr`. Откатить.

- [ ] **Step 6: Линт, типы, коммит**

```powershell
uv run ruff check .
uv run mypy
git add src/onecstarter/domain/launch.py tests/unit/test_launch.py
git commit -m "feat: domain — Credentials и передача /N /P в build_arguments"
```

---

## Task 4: `services/` — логин в наших данных, хранилище в `Workspace`, запуск

**Files:**
- Modify: `src/onecstarter/services/user_data.py` (`BaseUserData`, кодек, `set_login`)
- Modify: `src/onecstarter/services/errors.py`
- Modify: `src/onecstarter/services/workspace.py` (`__init__`, `set_credentials`, `credentials_of`, `launch`, `_write`, `remove_infobase`, `remove_group`)
- Modify: `src/onecstarter/services/launch.py` (`launch_infobase`)
- Modify: `src/onecstarter/ui/app.py:108` (подключение `KeyringStore()` — единственное место)
- Modify: `tests/unit/test_user_data.py`, `tests/unit/test_workspace.py`, `tests/unit/test_services_launch.py`
- Modify: `tests/ui/conftest.py:54`, `tests/ui/test_app.py:286` (`credentials=MemoryStore()` — параметр стал обязательным)
- Create: `tests/conftest.py` (session-guard: тесты не дотягиваются до реального keyring)

**Interfaces:**
- Consumes: `CredentialStore`, `MemoryStore`, `CredentialBackendError`,
  `redact_arguments` (задача 2); `Credentials`, `build_arguments(credentials=)` (задача 3).
- Produces:
  - `BaseUserData.login: str | None`; `set_login(entries, key, login) -> dict[str, BaseUserData]`
  - `CredentialStoreError(ServicesError)`
  - `Workspace(..., *, credentials: CredentialStore)` — обязательный именованный
    параметр без умолчания; реальный `KeyringStore()` подключает только
    `ui/app.py`, тесты передают `MemoryStore()`
  - `Workspace.set_credentials(key: str, login: str | None, password: str | None, remember: bool) -> None`
  - `Workspace.credentials_of(key: str) -> tuple[str | None, bool]` — логин, есть ли пароль
  - `launch_infobase(..., credentials: Credentials | None = None)`

- [ ] **Step 1: Падающие тесты `user_data`**

В `tests/unit/test_user_data.py`:

```python
from onecstarter.services.user_data import set_login


def test_login_round_trips_through_the_file(tmp_path: Path) -> None:
    path = tmp_path / "bases.json"
    save_user_data(path, set_login({}, "id:x", "tester"))
    assert load_user_data(path)["id:x"].login == "tester"


def test_file_without_login_field_loads_as_none(tmp_path: Path) -> None:
    """Файлы прежних версий поля не несут — схема остаётся 1 (спека v2.2, §3)."""
    path = tmp_path / "bases.json"
    path.write_text(
        json.dumps({"schema": 1, "entries": {"id:x": {"favorite": True}}}), encoding="utf-8"
    )
    assert load_user_data(path)["id:x"].login is None


def test_clearing_login_writes_none(tmp_path: Path) -> None:
    entries = set_login(set_login({}, "id:x", "tester"), "id:x", None)
    assert entries["id:x"].login is None
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_user_data.py -k login -v`
Expected: FAIL — `ImportError: cannot import name 'set_login'`

- [ ] **Step 3: Реализация `user_data`**

В `BaseUserData` добавить поле `login: str | None = None`; в `_encode` —
`"login": data.login`; в `_decode` — `login=value.get("login")`;
после `set_favorite`:

```python
def set_login(
    entries: Mapping[str, BaseUserData], key: str, login: str | None
) -> dict[str, BaseUserData]:
    """Логин — не секрет, живёт рядом с избранным (спека v2.2, §3).
    Пароль сюда не попадает никогда — он в `security/credentials.py`."""
    current = entries.get(key, BaseUserData())
    return {**entries, key: replace(current, login=login)}
```

Добавить `set_login` в `__all__`. Докстринг модуля: «Наши данные о базах:
избранное, история запусков и логин пользователя базы».

- [ ] **Step 4: Тесты `user_data` проходят**

Run: `uv run pytest tests/unit/test_user_data.py -v`
Expected: PASS.

- [ ] **Step 5: Падающие тесты `Workspace`**

В `tests/unit/test_workspace.py` (помощник `_workspace(tmp_path, calls, cfg_paths)`
и `_raw_section(tmp_path, name)` уже есть; `_workspace` делегирует
`_raw_workspace`, поэтому ОБА помощника получают параметр
`store: CredentialStore | None = None`, и `_raw_workspace` передаёт
`Workspace(..., credentials=store if store is not None else MemoryStore())` —
параметр конструктора обязателен, см. Step 7):

```python
from onecstarter.security.credentials import CredentialBackendError, MemoryStore
from onecstarter.services.errors import CredentialStoreError


def _first_base_key(workspace: Workspace) -> str:
    return next(i.key for i in workspace.items() if not i.is_group)


def test_set_credentials_keeps_the_password_out_of_our_files(tmp_path: Path) -> None:
    """Инвариант 5 по ФАКТУ на диске: ни bases.json, ни ibases.v8i не несут пароль."""
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)

    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    assert store.read(key) == "p@ss"
    assert "p@ss" not in (tmp_path / "bases.json").read_text(encoding="utf-8")
    assert b"p@ss" not in (tmp_path / "ibases.v8i").read_bytes()
    assert workspace.credentials_of(key) == ("tester", True)


def test_unremember_deletes_the_secret(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.set_credentials(key, "tester", None, remember=False)

    assert store.read(key) is None
    assert workspace.credentials_of(key) == ("tester", False)


def test_clearing_login_deletes_the_secret_too(tmp_path: Path) -> None:
    """Секрет без логина неприменим — оставлять его молча нельзя (спека §4)."""
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.set_credentials(key, None, None, remember=True)

    assert store.read(key) is None
    assert workspace.credentials_of(key) == (None, False)


def test_remember_without_new_password_keeps_the_stored_one(tmp_path: Path) -> None:
    """Пользователь открыл свойства и нажал ОК, не перепечатывая пароль."""
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.set_credentials(key, "tester", None, remember=True)

    assert store.read(key) == "p@ss"


def test_launch_passes_stored_credentials(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    store = MemoryStore()
    workspace = _workspace(tmp_path, calls=calls, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.launch(key)

    assert '/N"tester" /P"p@ss"' in calls[0].arguments


def test_launch_without_credentials_is_unchanged(tmp_path: Path) -> None:
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls=calls)
    workspace.launch(_first_base_key(workspace))
    assert "/N" not in calls[0].arguments and "/P" not in calls[0].arguments


def test_remove_deletes_the_secret(tmp_path: Path) -> None:
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    key = _first_base_key(workspace)
    workspace.set_credentials(key, "tester", "p@ss", remember=True)

    workspace.remove_infobase(key)

    assert store.read(key) is None


def test_rekey_moves_the_secret(tmp_path: Path) -> None:
    """Запись без ID получает его при первой правке — ключ меняется с cs:
    на id:, и секрет обязан переехать вместе с избранным (спека §3)."""
    store = MemoryStore()
    workspace = _workspace(tmp_path, store=store)
    # Тот же приём, что у test_update_of_section_without_id_rekeys_user_data
    # (строка ~223 этого файла): запись фикстуры без ID адресуется суррогатным
    # ключом, а new_id фабрики фиксирован — новый ключ известен заранее.
    old_key = binding_key(None, 'File="C:\Bases\Manual";', "Без идентификатора")
    workspace.set_credentials(old_key, "tester", "p@ss", remember=True)

    workspace.update_infobase(old_key, {"Version": "8.3.25"})

    new_key = "id:99999999-9999-9999-9999-999999999999"
    assert store.read(new_key) == "p@ss"
    assert store.read(old_key) is None


def test_blank_login_in_user_data_launches_without_credentials(tmp_path: Path) -> None:
    """bases.json правится и руками: пустой логин — не логин, а не ValueError на запуске."""
    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls=calls)
    key = _first_base_key(workspace)
    workspace._user = set_login(workspace._user, key, "   ")

    workspace.launch(key)

    assert "/N" not in calls[0].arguments


def test_store_failure_on_write_is_a_services_error_after_user_data_saved(tmp_path: Path) -> None:
    class Broken(MemoryStore):
        def write(self, key: str, secret: str) -> None:
            raise CredentialBackendError("отказ")

    workspace = _workspace(tmp_path, store=Broken())
    key = _first_base_key(workspace)

    with pytest.raises(CredentialStoreError):
        workspace.set_credentials(key, "tester", "p@ss", remember=True)
    assert workspace.credentials_of(key) == ("tester", False), "логин записан, пароль — нет"


def test_store_failure_on_launch_launches_without_credentials_then_reports(tmp_path: Path) -> None:
    class Broken(MemoryStore):
        def read(self, key: str) -> str | None:
            raise CredentialBackendError("отказ")

    calls: list[LaunchCommand] = []
    workspace = _workspace(tmp_path, calls=calls, store=Broken())
    key = _first_base_key(workspace)
    workspace._user = set_login(workspace._user, key, "tester")

    with pytest.raises(CredentialStoreError):
        workspace.launch(key)
    assert len(calls) == 1, "процесс порождён — отказ хранилища не отказ запуска"
    assert "/P" not in calls[0].arguments
```

`binding_key` импортируется из `onecstarter.services.model` (в файле уже
есть — см. `test_update_of_section_without_id_rekeys_user_data`). Фикстура
`anonymized.v8i` несёт ровно одну запись без `ID` — «Без идентификатора»
с `Connect=File="C:\Bases\Manual";` (проверено 06.09.2026).

- [ ] **Step 6: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_workspace.py -k "credentials or secret or rekey_moves" -v`
Expected: FAIL — `TypeError: Workspace.__init__() got an unexpected keyword argument 'credentials'`
(после правки `_workspace`) либо `AttributeError: 'Workspace' object has no attribute 'set_credentials'`.

- [ ] **Step 7: Реализация `errors` и `Workspace`**

`services/errors.py`, после `UserDataWriteError`:

```python
class CredentialStoreError(ServicesError):
    """Диспетчер учётных данных Windows отказал. Текст — причина без секрета.

    Поднимается ПОСЛЕ того, как остальное состояние приведено в порядок
    (запись в `.v8i` и `bases.json` состоялась, процесс порождён) — тем же
    правилом, что `UserDataWriteError`: отказ хранилища не отменяет того,
    что уже сделано, и сообщение обязано это различать.
    """
```

`services/workspace.py`:

```python
from onecstarter.security.credentials import (
    CredentialStore,
    CredentialBackendError,
)
from onecstarter.services.errors import CredentialStoreError
from onecstarter.services.user_data import set_login

# в __init__ — новый именованный параметр без умолчания, рядом с new_id.
# Умолчание `KeyringStore()` запрещено: тест, собравший Workspace без
# параметра, молча читал бы и удалял записи в реальном Credential Manager
# пользователя. Обязательность заставляет каждое место сборки выбрать явно.
        credentials: CredentialStore,
# и в теле:
        self._credentials = credentials
```

Методы, после `set_favorite`:

```python
    def credentials_of(self, key: str) -> tuple[str | None, bool]:
        """Логин и признак «пароль сохранён» — диалогу. Сам пароль наружу
        не отдаётся никогда (спека v2.2, §4)."""
        login = self._user.get(key, BaseUserData()).login
        try:
            has_password = self._credentials.read(key) is not None
        except CredentialBackendError as error:
            raise CredentialStoreError(str(error)) from error
        return login, has_password

    def set_credentials(
        self, key: str, login: str | None, password: str | None, remember: bool
    ) -> None:
        """Записать логин в наши данные, пароль — в хранилище. Порядок важен:
        логин пишется первым, и отказ хранилища не откатывает его — сообщение
        различает «логин записан, пароль нет» (спека §4, §8). Дерево
        перестраивается в любом исходе: логин уже на диске, и модель в памяти
        обязана его отражать до того, как ошибка уйдёт наверх (как `launch`
        и `_write`; тот же класс дефекта, что чинил add5b16).

        `login` пустой → секрет удаляется: пароль без логина неприменим.
        `remember` снят → секрет удаляется. `remember` стоит, `password` не
        задан → сохранённый пароль остаётся (пользователь не перепечатывал).
        """  # noqa: RUF002
        item = self._item(key)
        if item.is_group:
            raise InvalidRequestError(f"«{item.name}» — группа, у неё нет пользователя")  # noqa: RUF001
        normalized = (login or "").strip() or None
        self._store_user(set_login(self._user, key, normalized), "Не удалось сохранить логин")  # noqa: RUF001
        try:
            if normalized is None or not remember:
                self._credentials.delete(key)
            elif password is not None:
                self._credentials.write(key, password)
        except CredentialBackendError as error:
            raise CredentialStoreError(
                f"Логин сохранён, пароль — нет: {error}"  # noqa: RUF001
            ) from error
        finally:
            self._rebuild()
```

В `launch` — перед `launch_infobase(...)`:

```python
        credentials, store_failure = self._credentials_for_launch(key)
        outcome = launch_infobase(
            item,
            ...,
            credentials=credentials,
        )
```

и после существующего `try/except UserDataWriteError` вокруг `record_launch`
(там, где ошибка наших данных поднимается после запуска):

```python
        if store_failure is not None:
            raise store_failure
```

Помощник:

```python
    def _credentials_for_launch(self, key: str) -> tuple[Credentials | None, CredentialStoreError | None]:
        """Учётные данные для запуска. Отказ хранилища — не отказ запуска:
        клиент запускается без них, платформа спросит сама, а ошибка
        поднимается ПОСЛЕ порождения процесса (спека §8)."""
        # Нормализация на чтении, а не только на записи: файл bases.json
        # правится и руками, а `Credentials("")` отвергается доменом
        # (`__post_init__`, задача 3) — на запуске это было бы необработанным
        # ValueError вместо честного «логина нет».
        login = (self._user.get(key, BaseUserData()).login or "").strip() or None
        if login is None:
            return None, None
        try:
            password = self._credentials.read(key)
        except CredentialBackendError as error:
            return Credentials(login), CredentialStoreError(
                f"Пароль не прочитан, запуск без него: {error}"  # noqa: RUF001
            )
        return Credentials(login, password), None
```

В `remove_infobase` — после `_write(REMOVE)`:

```python
        applied = self._write(SectionPatch(PatchKind.REMOVE, target_key=key)).applied
        try:
            self._credentials.delete(key)
        except CredentialBackendError as error:
            raise CredentialStoreError(
                f"Запись удалена, но пароль в диспетчере учётных данных остался: {error}"  # noqa: RUF001
            ) from error
        return applied
```

В `_write` — в блоке `if rekey_from is not None and result.key is not None and result.key != rekey_from:`
после `_store_user(rekey(...))`:

```python
            try:
                secret = self._credentials.read(rekey_from)
                if secret is not None:
                    self._credentials.write(result.key, secret)
                    self._credentials.delete(rekey_from)
            except CredentialBackendError as error:
                failure = failure or CredentialStoreError(
                    f"Запись изменена, но не удалось перенести на неё пароль: {error}"  # noqa: RUF001
                )
```

(тип `failure` расширить до `UserDataWriteError | CredentialStoreError | None`.)

`services/launch.py`: параметр `credentials: Credentials | None = None`
у `launch_infobase`, передаётся в `build_arguments(..., credentials=credentials)`;
текст ошибки и исход — через редакцию:

```python
from onecstarter.security.secrets import redact_arguments, redact_connect
...
            f"Команда: \"{command.executable}\" {redact_arguments(command.arguments)}"
...
        command_line=f'"{command.executable}" {redact_arguments(command.arguments)}',
```

Комментарий «Секретов в ней нет: запуск идёт по /IBName» заменить на:
«С v2.2 в аргументах может быть /P — показывается только редактированная
форма (спека v2.2, §6)».

`remove_group` — секреты удалённых потомков. Ключи потомков не приходят из
`PatchResult` (менять `groups.py`/`model.py` ради этого не нужно): достаточно
разности множеств ключей записей до и после записи — `_write` перестраивает
дерево в любом исходе. При `PROMOTE` ключи не меняются (папка в ключ не
входит) — разность пуста, удалять нечего.

```python
    def remove_group(self, key: str, removal: GroupRemoval) -> bool:
        """<исходный докстринг — из файла>

        Пароли записей, удалённых вместе с группой, удаляются из хранилища:
        суррогатный ключ секции без ID достался бы новой записи с тем же
        именем и строкой соединения — вместе с «удалённым» паролем.
        """  # noqa: RUF002
        self._reject_common(key)
        before = {item.key for item in self.items() if not item.is_group}
        applied = self._write(
            GroupPatch(GroupPatchKind.REMOVE, target_key=key, removal=removal)
        ).applied
        gone = before - {item.key for item in self.items() if not item.is_group}
        failed: list[str] = []
        for removed in sorted(gone):
            try:
                self._credentials.delete(removed)
            except CredentialBackendError as error:
                failed.append(f"{removed}: {error}")
        if failed:
            raise CredentialStoreError(
                "Группа удалена, но пароли её записей остались в диспетчере "
                "учётных данных: " + "; ".join(failed)
            )
        return applied
```

Ключ в тексте ошибки — `id:<GUID>` или суррогат (строка соединения + имя),
секрета в нём нет. Отказ одного удаления не прерывает остальные: пытаемся
удалить все, потом сообщаем обо всех.

- [ ] **Step 7а: Подключение реального хранилища и защита тестов**

Параметр обязателен, поэтому меняются все места сборки `Workspace`
(`grep -rn "Workspace(" src tests --include=*.py`, без `class Workspace`):

1. `src/onecstarter/ui/app.py:108` — единственное место, где появляется
   реальное хранилище:

```python
from onecstarter.security.credentials import KeyringStore
# в вызове Workspace(...) после default_app=...:
        credentials=KeyringStore(),
```

2. `tests/ui/conftest.py:54` и `tests/ui/test_app.py:286` — в вызов
   `Workspace(...)` добавить `credentials=MemoryStore()` (импорт из
   `onecstarter.security.credentials`). В задаче 5 conftest получит
   параметр `store=`; здесь — минимум, чтобы набор остался зелёным.

3. Создать `tests/conftest.py` — session-guard. Хранилище паролей
   пользователя не тестовый стенд: чтение выдаст его секреты, удаление
   их уничтожит. Любой путь до `keyring.*` из теста — потерянная инъекция.

```python
"""Общие фикстуры всего набора тестов."""

from collections.abc import Iterator
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True, scope="session")
def forbid_real_keyring() -> Iterator[None]:
    """Ни один тест не дотягивается до реального Credential Manager.

    Тесты `KeyringStore` подменяют эти же функции своим `monkeypatch` —
    он ложится поверх защиты и снимается обратно на неё.
    """
    import keyring

    def _refuse(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError(
            "тест дотянулся до реального keyring — инъекция хранилища потеряна"
        )

    with pytest.MonkeyPatch.context() as patch:
        for name in ("get_password", "set_password", "delete_password"):
            patch.setattr(keyring, name, _refuse)
        yield
```

Проверка защиты (не оставлять в наборе): временно добавить в
`tests/unit/test_credentials.py` тест, зовущий `KeyringStore().read("probe")`,
запустить его одного — он обязан упасть с `AssertionError: тест дотянулся до
реального keyring`, не с `None`. Удалить тест, записать в отчёт.

Run: `uv run pytest tests/unit/test_credentials.py tests/ui/test_app.py -q`
Expected: PASS — тесты `KeyringStore` по-прежнему зелёные поверх защиты,
`test_importing_the_module_does_not_import_keyring` (подпроцесс) не задет.

- [ ] **Step 8: Тест редакции в исходе и ошибке**

В `tests/unit/test_services_launch.py`:

```python
def test_launch_outcome_and_error_hide_the_password(tmp_path: Path) -> None:
    """Спека v2.2, §6: ни исход, ни текст ошибки не несут значение /P."""
    item = _item(...)  # помощник файла, файловая база
    outcome = launch_infobase(
        item, installations=INSTALLED, cfg_rules=[], conventions=CONVENTIONS,
        default_app=None, spawn=lambda command: 7, credentials=Credentials("u", "p@ss"),
    )
    assert "p@ss" not in (outcome.command_line or "")
    assert "/P***" in (outcome.command_line or "")

    def failing(command: LaunchCommand) -> int:
        raise OSError("нет доступа")

    with pytest.raises(LaunchError) as caught:
        launch_infobase(
            item, installations=INSTALLED, cfg_rules=[], conventions=CONVENTIONS,
            default_app=None, spawn=failing, credentials=Credentials("u", "p@ss"),
        )
    assert "p@ss" not in str(caught.value)
```

Помощники `_item`, `INSTALLED`, `CONVENTIONS` — из этого файла или
`tests/ui/conftest.py`, как делают соседние тесты.

- [ ] **Step 9: Все тесты слоя проходят**

Run: `uv run pytest tests/unit/test_user_data.py tests/unit/test_workspace.py tests/unit/test_services_launch.py -v`
Expected: PASS.

- [ ] **Step 10: Мутации**

1. В `set_credentials` положить пароль в наши данные: `set_login(..., f"{normalized}:{password}")`.
   Expected: FAIL в `test_set_credentials_keeps_the_password_out_of_our_files` — по файлу с диска.
2. В `launch.py` убрать `redact_arguments` из текста ошибки.
   Expected: FAIL в `test_launch_outcome_and_error_hide_the_password`.
3. В `remove_infobase` убрать `self._credentials.delete(key)`.
   Expected: FAIL в `test_remove_deletes_the_secret`.
4. В `_write` убрать перенос секрета.
   Expected: FAIL в `test_rekey_moves_the_secret`.
5. В `remove_group` убрать цикл удаления секретов потомков.
   Expected: FAIL в `test_recursive_group_removal_deletes_the_secrets`
   на `assert not any(key in store.data for key in nested)`.

`finally: self._rebuild()` в `set_credentials` мутацией не проверяется:
логин на `InfobaseItem` не проецируется, наблюдаемого поведения у пропуска
перестройки сегодня нет, а тест-шпион на вызов `_rebuild` проверял бы
намерение, а не поведение (правило файла test_workspace.py). Это правка
контракта (докстринг `CredentialStoreError`), фиксируется ревью.

Откатить правкой файлов, все пять записать в отчёт.

- [ ] **Step 11: Линт, типы, коммит**

```powershell
uv run ruff check .
uv run mypy
git add src/onecstarter/services src/onecstarter/ui/app.py tests/conftest.py tests/ui/conftest.py tests/ui/test_app.py tests/unit/test_user_data.py tests/unit/test_workspace.py tests/unit/test_services_launch.py
git commit -m "feat: services — логин в наших данных, пароль в хранилище, передача при запуске"
```

---

## Task 5: `ui/` — три строки в обоих диалогах и применение

**Files:**
- Modify: `src/onecstarter/ui/dialogs/infobase.py` (`__init__:341`, `for_new:525`, `_refresh_ok_state`, новые аксессоры)
- Modify: `src/onecstarter/ui/bases/view.py` (`_build_properties_dialog`, `_apply_properties:1400`, `_apply_new_infobase`)
- Modify: `tests/ui/conftest.py` (`workspace_factory`: `credentials=MemoryStore()` из задачи 4 → параметр `store=`)
- Modify: `tests/ui/test_infobase_dialog.py`, `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `Workspace.set_credentials`, `credentials_of`, `CredentialStoreError` (задача 4); `MemoryStore` (задача 2).
- Produces:
  - `InfobaseDialog(..., login: str | None = None, has_password: bool = False)`; то же у `for_new`
  - `DialogCredentials(login: str | None, password: str | None, remember: bool)` — frozen, `password` с `repr=False`
  - `InfobaseDialog.credentials() -> DialogCredentials`
  - `InfobaseDialog.credentials_changed() -> bool`
  - аксессоры для тестов: `login_edit()`, `password_edit()`, `remember_checkbox()`, `credentials_note()`

- [ ] **Step 1: Падающие тесты диалога**

В `tests/ui/test_infobase_dialog.py`:

```python
from PySide6.QtWidgets import QLineEdit

from onecstarter.ui.dialogs.infobase import DialogCredentials


def test_dialog_offers_login_password_and_remember_off_by_default(qtbot) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    assert dialog.login_edit().text() == ""
    assert dialog.password_edit().echoMode() == QLineEdit.EchoMode.Password
    assert dialog.remember_checkbox().isChecked() is False
    assert "командной строке" in dialog.credentials_note().text()


def test_stored_password_is_not_shown_in_the_dialog(qtbot) -> None:
    """Спека v2.2, §4: диалог знает только признак — сам пароль не возвращается."""
    dialog = InfobaseDialog(
        _item('File="D:\\b";', ()), groups=["/"], installations=INSTALLED,
        cfg_rules=[], login="tester", has_password=True,
    )
    qtbot.addWidget(dialog)
    assert dialog.login_edit().text() == "tester"
    assert dialog.password_edit().text() == ""
    assert "сохранён" in dialog.password_edit().placeholderText()
    assert dialog.remember_checkbox().isChecked() is True
    assert dialog.credentials_changed() is False


def test_password_without_login_blocks_ok_with_a_hint(qtbot) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.set_name("Демо")
    dialog.set_file_path(r"D:\Bases\Demo")
    assert dialog.accepts()

    dialog.password_edit().setText("p@ss")

    assert not dialog.accepts()
    assert "Пользователь" in dialog.required_hint()


def test_credentials_accessor_and_repr(qtbot) -> None:
    dialog = InfobaseDialog.for_new(groups=["/"], installations=INSTALLED, cfg_rules=[])
    qtbot.addWidget(dialog)
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")
    dialog.remember_checkbox().setChecked(True)

    credentials = dialog.credentials()

    # По полям, не через `==`: у пароля compare=False (иначе упавший assert
    # печатал бы его в дифе pytest), и равенство пароль не проверяет.
    assert credentials.login == "tester"
    assert credentials.password == "p@ss"
    assert credentials.remember is True
    assert "p@ss" not in repr(credentials)
    assert dialog.credentials_changed() is True


def test_clearing_login_with_stored_password_warns(qtbot) -> None:
    dialog = InfobaseDialog(
        _item('File="D:\\b";', ()), groups=["/"], installations=INSTALLED,
        cfg_rules=[], login="tester", has_password=True,
    )
    qtbot.addWidget(dialog)
    dialog.login_edit().setText("")
    assert "будет удалён" in dialog.credentials_note().text()
    assert dialog.credentials_changed() is True
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_infobase_dialog.py -k "login or password or credentials" -v`
Expected: FAIL — `ImportError: cannot import name 'DialogCredentials'`

- [ ] **Step 3: Реализация диалога**

Датакласс и текст подписи в `ui/dialogs/infobase.py`:

```python
from dataclasses import dataclass, field

CREDENTIALS_NOTE = (
    "Хранится в диспетчере учётных данных Windows. При запуске передаётся "
    "в командной строке и виден любой программе, работающей под вашей "
    "учётной записью, всё время работы клиента"
)
CLEARING_LOGIN_NOTE = "Поле пользователя пусто — сохранённый пароль будет удалён"
STORED_PASSWORD_PLACEHOLDER = "сохранён"


@dataclass(frozen=True)
class DialogCredentials:
    """Что ввёл пользователь. `password` не печатается (инвариант 5);
    `None` — поле пустое, сохранённый пароль не трогать."""

    login: str | None
    password: str | None = field(default=None, repr=False, compare=False)
    remember: bool = False
```

В `__init__` — параметры `login: str | None = None, has_password: bool = False`
(и в `for_new`, прокинуть в `cls(...)`); поля строятся **всегда**, после
«Клиента»:

```python
        self._initial_login = (login or "").strip() or None
        self._has_password = has_password
        self._login = QLineEdit(self._initial_login or "")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        if has_password:
            self._password.setPlaceholderText(STORED_PASSWORD_PLACEHOLDER)
        self._remember = QCheckBox()
        self._remember.setChecked(has_password)
        self._credentials_note = QLabel(CREDENTIALS_NOTE)
        self._credentials_note.setObjectName("SettingsNote")
        self._credentials_note.setWordWrap(True)

        form.addRow("Пользователь", self._login)
        form.addRow("Пароль", self._password)
        form.addRow("Запомнить пароль", self._remember)
        form.addRow("", self._credentials_note)

        self._login.textChanged.connect(self._refresh_ok_state)
        self._password.textChanged.connect(self._refresh_ok_state)
```

В `_refresh_ok_state` существующая ветка «всё заполнено» заканчивается
ранним `return` — проверка, поставленная после неё, была бы недостижима
для заполненного диалога (дефект первой редакции плана, найден исполнителем).
Поэтому `return` заменяется на `if/else`, а новая проверка идёт следом:

```python
        empty = self._empty_required()
        self._ok_button.setEnabled(not empty)
        if not empty:
            self._required_hint.setText("")
        else:
            fields = ", ".join(f"«{label}»" for label in empty)
            self._required_hint.setText(f"Заполните: {fields}")

        if self._password.text() and not self._login.text().strip():
            self._ok_button.setEnabled(False)
            self._required_hint.setText(
                "Заполните: «Пользователь» — пароль без него не применить"
            )
            return
        self._credentials_note.setText(
            CLEARING_LOGIN_NOTE
            if self._has_password and not self._login.text().strip()
            else CREDENTIALS_NOTE
        )
```

Аксессоры:

```python
    def credentials(self) -> DialogCredentials:
        return DialogCredentials(
            login=self._login.text().strip() or None,
            password=self._password.text() or None,
            remember=self._remember.isChecked(),
        )

    def credentials_changed(self) -> bool:
        """Есть ли что записывать: логин сменился, пароль введён заново или
        галочка переключена. Нетронутый диалог не должен трогать хранилище."""
        current = self.credentials()
        return (
            current.login != self._initial_login
            or current.password is not None
            or current.remember != self._has_password
        )

    def login_edit(self) -> QLineEdit: return self._login
    def password_edit(self) -> QLineEdit: return self._password
    def remember_checkbox(self) -> QCheckBox: return self._remember
    def credentials_note(self) -> QLabel: return self._credentials_note
```

Докстринг модуля: раздел «Секретные значения не показываются и не
редактируются. Хранение паролей вне v1…» **не удалять**, а дописать
следом абзац «v2.2: логин и пароль вводятся здесь, но идут мимо `changes()`
и `new_record()` — отдельным аксессором `credentials()` в
`Workspace.set_credentials`; в `.v8i` пароль не попадает по построению».

Уточнение по ревью задачи 5: фраза «не показываются **и не редактируются**»
после появления поля пароля стала ложной. Объяснение не терять, а перевести
в прошедшее время: «до v2.2 поля пароля не было — оно создало бы способ
записать пароль в `.v8i` открытым текстом; с v2.2 поле есть, но его значение
идёт мимо `changes()`/`new_record()` — в диспетчер учётных данных через
`Workspace.set_credentials`». Докстринг модуля не должен утверждать
обратное коду (правило проекта о документе, разошедшемся с кодом).

- [ ] **Step 4: Тесты диалога проходят**

Run: `uv run pytest tests/ui/test_infobase_dialog.py -v`
Expected: PASS, прежние тесты без правок.

- [ ] **Step 5: Падающие тесты путей применения**

В `tests/ui/conftest.py::workspace_factory` добавить параметр
`store: MemoryStore | None = None` и передавать в `Workspace(...,
credentials=store if store is not None else MemoryStore())`. Кортеж возврата
НЕ менять — его распаковывают позиционно десятки вызывающих. В
`tests/ui/test_bases_view.py::_view` добавить такой же параметр `store` и
прокинуть в фабрику; тесты, которым нужно хранилище, создают его сами
и передают `store=store` — ссылка остаётся у теста.

В `tests/ui/test_bases_view.py`:

```python
def test_properties_apply_stores_credentials(qtbot, workspace_factory) -> None:
    """Путь ОК диалога свойств — `_apply_properties` — доносит учётные данные
    до хранилища; модальный exec() в офскрине не кликается, это приём файла."""
    store = MemoryStore()
    view, *_ = _view(qtbot, workspace_factory, store=store)
    dialog = view._build_properties_dialog(_ACCOUNTING_KEY)
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")
    dialog.remember_checkbox().setChecked(True)

    # Приём файла: `exec()` блокирует офскрин-тесты, поэтому обработчик ОК —
    # `_apply_properties` — зовётся напрямую (см. докстринг show_properties).
    view._apply_properties(_ACCOUNTING_KEY, dialog)

    assert store.read(_ACCOUNTING_KEY) == "p@ss"
    assert view.workspace().credentials_of(_ACCOUNTING_KEY) == ("tester", True)


def test_properties_with_no_changes_does_not_touch_the_store(qtbot, workspace_factory) -> None:
    store = MemoryStore()
    view, *_ = _view(qtbot, workspace_factory, store=store)
    # Нетронутый диалог отдаёт login=None/password=None/remember=False —
    # сломанный credentials_changed() ушёл бы в ветку delete, а не write,
    # поэтому шпион стоит на обеих операциях (находка ревью).
    calls: list[str] = []
    store.write = lambda key, secret: calls.append(f"write {key}")  # type: ignore[method-assign]
    store.delete = lambda key: calls.append(f"delete {key}")  # type: ignore[method-assign]
    dialog = view._build_properties_dialog(_ACCOUNTING_KEY)

    view._apply_properties(_ACCOUNTING_KEY, dialog)

    assert calls == []


def test_properties_edit_of_id_less_record_keeps_entered_credentials(
    qtbot, workspace_factory
) -> None:
    """Правка записи без ID меняет её ключ (дописывается ID). Учётные данные,
    введённые в том же диалоге, обязаны доехать до нового ключа, а не
    потеряться за «файл изменился извне» (находка ревью задачи 5)."""
    store = MemoryStore()
    errors: list[ServicesError] = []
    view, *_ = _view(qtbot, workspace_factory, errors=errors, store=store)
    old_key = binding_key(None, 'File="C:\Bases\Manual";', "Без идентификатора")
    dialog = view._build_properties_dialog(old_key)
    assert dialog is not None
    dialog.set_name("Ручная база")  # правка → update_infobase → запись получает ID
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")
    dialog.remember_checkbox().setChecked(True)

    view._apply_properties(old_key, dialog)

    assert errors == []
    new_key = next(key for key in store.data if key.startswith("id:"))
    assert store.data[new_key] == "p@ss"
    assert old_key not in store.data
    assert view.workspace().credentials_of(new_key) == ("tester", True)


def test_add_dialog_stores_credentials_after_the_record(qtbot, workspace_factory) -> None:
    store = MemoryStore()
    view, *_ = _view(qtbot, workspace_factory, store=store)
    dialog = view._build_add_dialog()
    dialog.set_name("Новая")
    dialog.set_file_path(r"D:\Bases\New")
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")
    dialog.remember_checkbox().setChecked(True)

    view._apply_new_infobase(dialog)

    key = next(i.key for i in view.workspace().items() if i.name == "Новая")
    assert store.read(key) == "p@ss"


def test_add_dialog_store_failure_reports_record_added(qtbot, workspace_factory) -> None:
    """Спека §4: «база добавлена, пароль не сохранён», а не «не удалось добавить»."""
    errors: list[ServicesError] = []
    store = MemoryStore()
    view, *_ = _view(qtbot, workspace_factory, errors=errors, store=store)

    def boom(key: str, secret: str) -> None:
        raise CredentialBackendError("отказ")

    store.write = boom  # type: ignore[method-assign]
    dialog = view._build_add_dialog()
    dialog.set_name("Новая")
    dialog.set_file_path(r"D:\Bases\New")
    dialog.login_edit().setText("tester")
    dialog.password_edit().setText("p@ss")
    dialog.remember_checkbox().setChecked(True)

    view._apply_new_infobase(dialog)

    assert any(i.name == "Новая" for i in view.workspace().items())
    assert errors and "добавлена" in str(errors[0]) and "пароль" in str(errors[0])
```

`_view` возвращает кортеж `(view, calls, recorded, opened)` — не менять;
хранилище приходит параметром `store=` и остаётся ссылкой у теста.

- [ ] **Step 6: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_bases_view.py -k credentials -v`
Expected: FAIL — `TypeError` на неизвестном параметре `store` у `_view`/фабрики
либо `AttributeError` на `login_edit`.

- [ ] **Step 7: Реализация в `view.py`**

`_build_properties_dialog`:

```python
        try:
            login, has_password = self._workspace.credentials_of(key)
        except ServicesError as error:
            self._on_error(error)
            login, has_password = None, False
        return InfobaseDialog(
            item, groups=..., installations=..., cfg_rules=..., parent=self,
            login=login, has_password=has_password,
        )
```

`_apply_properties` — учётные данные применяются **независимо** от правок
`.v8i`; ранний `return` при пустых `changes` больше не последний. Порядок
обязателен: **учётные данные — ДО `update_infobase`.** У записи без `ID`
ключ суррогатный (строка соединения + имя), и любая правка через
`update_infobase` дописывает `ID` и меняет ключ (`rekey_from=key`);
`set_credentials(key, …)` после этого не найдёт запись —
`UnknownItemError`, введённые логин и пароль потеряны за сообщением «файл
изменился извне» (находка ревью задачи 5). Записанные до правки логин и
секрет `_write` переносит на новый ключ сам (rekey задачи 4).

```python
        credentials_changed = dialog.credentials_changed()
        if not changes and new_name is None and not credentials_changed:
            return
        if credentials_changed:
            entered = dialog.credentials()
            try:
                self._workspace.set_credentials(
                    key, entered.login, entered.password, entered.remember
                )
            except ServicesError as error:
                self._on_error(error)
        if changes or new_name is not None:
            try:
                self._workspace.update_infobase(key, changes, new_name)
            except ServicesError as error:
                self._on_error(error)
        self.rebuild()
```

`_apply_new_infobase` — захватить ключ и записать учётные данные после:

```python
        try:
            key = self._workspace.add_infobase(
                record.name, record.connect, record.folder,
                version=record.version, app=record.app,
            )
        except ServicesError as error:
            self._on_error(error)
            self.rebuild()  # инвариант файла: перестройка безусловна (add5b16)
            return
        if dialog.credentials_changed():
            entered = dialog.credentials()
            try:
                self._workspace.set_credentials(
                    key, entered.login, entered.password, entered.remember
                )
            except ServicesError as error:
                self._on_error(
                    InvalidRequestError(
                        f"База «{record.name}» добавлена, но пароль не сохранён: {error}"  # noqa: RUF001
                    )
                )
        self.rebuild()
```

(если после `add_infobase` в текущем коде идёт свой `rebuild()`/выбор
строки — сохранить, вставив блок учётных данных до него.)

- [ ] **Step 8: Тесты проходят**

Run: `uv run pytest tests/ui/test_infobase_dialog.py tests/ui/test_bases_view.py -v`
Expected: PASS.

- [ ] **Step 9: Мутации**

1. В диалоге подставить сохранённый пароль в поле: `self._password.setText("сохранён")`
   при `has_password`. Expected: FAIL в `test_stored_password_is_not_shown_in_the_dialog`.
2. `self._remember.setChecked(True)` безусловно.
   Expected: FAIL в `test_dialog_offers_login_password_and_remember_off_by_default`.
3. В `_apply_properties` вернуть ранний `return` при пустых `changes`
   без учёта `credentials_changed`. Expected: FAIL в `test_properties_apply_stores_credentials`.
4. В `_apply_new_infobase` завернуть отказ хранилища в общий текст «не удалось добавить».
   Expected: FAIL в `test_add_dialog_store_failure_reports_record_added`.
5. `credentials_changed()` → `return True` безусловно.
   Expected: FAIL в `test_properties_with_no_changes_does_not_touch_the_store`
   на `assert calls == []` — в списке `delete id:…`.
6. В `_apply_properties` вернуть блок учётных данных ПОСЛЕ `update_infobase`.
   Expected: FAIL в `test_properties_edit_of_id_less_record_keeps_entered_credentials`
   на `assert errors == []` (UnknownItemError) либо на `credentials_of`.

`self.rebuild()` в ветке отказа `_apply_new_infobase` мутацией не проверяется:
ветка после состоявшейся записи документирована как недостижимая, это
восстановление инварианта файла, фиксируется ревью.

Откатить правкой файлов, все шесть записать в отчёт.

- [ ] **Step 10: Линт, типы, коммит**

```powershell
uv run ruff check .
uv run mypy
git add src/onecstarter/ui/dialogs/infobase.py src/onecstarter/ui/bases/view.py tests/ui/conftest.py tests/ui/test_infobase_dialog.py tests/ui/test_bases_view.py
git commit -m "feat: ui — логин, пароль и «Запомнить» в обоих диалогах записи"
```

---

## Task 6: документы, версия, сборка, живая проверка

**Files:**
- Modify: `docs/requirements.md:53-55`, `:69-79`
- Modify: `docs/tasks.md` (веха T-14; строка долга T-12 п. 2)
- Modify: `pyproject.toml` (`version = "2.2.0"`)

- [ ] **Step 1: Полный прогон в файл**

```powershell
$env:PYTHONFAULTHANDLER=1
uv run pytest -rA --tb=long -p no:cacheprovider > "$env:TEMP\v22.log" 2>&1
$LASTEXITCODE
```

Expected: 0. Код 139 — повторить; любой другой — регресс.

- [ ] **Step 2: `requirements.md`**

§4: из «**Не в v1:** …; хранение паролей.» убрать «хранение паролей»,
дописать «Хранение логина и пароля — v2.2.» §5, новая строка после `v2`:

```markdown
| v2.2 | Учётные данные для запуска: логин в наших данных, пароль в Windows Credential Manager, передача через `/N` `/P` с явным предупреждением об argv | Б |
```

- [ ] **Step 3: `docs/tasks.md` — побайтово, CRLF**

Скриптом с проверкой единственности вхождения (образец —
`.superpowers/sdd/2026-09-02-v21-ui/task-8-report.md` вехи T-13):

1. Строка долга T-12 п. 2 (`PPasswd` не распознаётся) — обернуть в `~~…~~`
   и дописать: «**Закрыто без кода 04.09.2026:** `ppasswd` в `_SECRET_KEYS`
   с 0.1.0, `test_ppasswd_is_a_secret` есть — строка была устаревшей».
2. Веха **T-14** в конец файла по структуре T-13: четыре гейта/решения
   заказчика, результат T-05.14 со ссылкой на `docs/research/t05-14-results.md`,
   **все** мутационные проверки задач 1–5 (что ломали, где отозвалось),
   принятые ограничения (§8 спеки), keyring-гейт и его исход.

Проверка: `git diff --stat docs/tasks.md` показывает строки, не файл.

- [ ] **Step 4: Версия и сборка парой**

`pyproject.toml`: `version = "2.2.0"`. Из PowerShell-инструмента, **без**
`-SkipInstaller` — релиз обязан дать `zip + setup` (урок T-13):

```powershell
powershell -File build/build.ps1
Get-ChildItem dist\*2.2.0*
```

Expected: `smoke: OK`, в логе smoke `keyring=ok`, в `dist/` —
`OneCStarter-2.2.0-portable.zip` **и** `OneCStarter-2.2.0-setup.exe`.

- [ ] **Step 5: Коммит**

```powershell
git add pyproject.toml docs/requirements.md docs/tasks.md uv.lock
git commit -m "release: версия 2.2.0 — учётные данные для запуска базы"
```

- [ ] **Step 6: Живая проверка заказчиком — до слияния**

Заказчику: собранный экземпляр, тестовая база из T-05.14. Проверить глазами:
три строки в свойствах и в добавлении; подпись-предупреждение читается;
«Запомнить» выключено у новой записи; после сохранения — запуск базы без
диалога; снятие галочки — снова диалог; в `%APPDATA%\OneCStarter\bases.json`
пароля нет. Ветка сливается только после его вердикта.

---

## Самопроверка плана

**Покрытие спеки.**

| Раздел спеки | Задача |
| --- | --- |
| §0 предпосылки | учтены в Global Constraints и текстах задач |
| §1 эксперимент, исходы | 0a, 0b (гейт, BLOCKED-ветки описаны) |
| §2 модель угроз, текст предупреждения | 5 (`CREDENTIALS_NOTE` дословно) |
| §3 логин в `bases.json`, пароль в keyring, жизнь ключа | 4 (`set_login`, `set_credentials`, `_write`, `remove_infobase`) |
| §4 оба диалога, умолчания, отдельный путь, добавление, логин без пароля, очистка логина | 5 |
| §5 запуск, `Credentials` `repr=False`, порядок аргументов, `/WA-` условно | 3, 4 |
| §6 редакция | 2 (`redact_arguments`), 4 (применение) |
| §7 компоненты | File Structure |
| §8 отказы и ограничения | 4 (три отказа), 6 (ограничения в T-14) |
| §9 keyring-гейт | 1 |
| §10 инварианты, `CORE` | 2 |
| §11 тесты и мутации | по задачам; сводка — 6 |
| §12 документы | 0b (скил), 6 (requirements, tasks) |
| §13 порядок | порядок задач |
| §14 альтернативы | записаны в спеке, кода не требуют |

**Заглушки.** В задаче 4 `test_rekey_moves_the_secret` несёт конструкцию
`if False else` с явным указанием заменить её способом из соседних тестов
rekey — это не заглушка, а запрет вычислять ключ вместо чтения состояния;
исполнитель обязан заменить и записать, чем. (Перепроверка 06.09.2026:
тест rekey задачи 4 и помощники задачи 5 переписаны на фактические
имена из файлов — `binding_key` + фиксированный `new_id`, параметр `store=`
у фабрики и `_view`; выдуманных помощников в плане не осталось.)

**Согласованность имён.** `CredentialStore`/`KeyringStore`/`MemoryStore`/
`CredentialBackendError` (2, 4, 5), `redact_arguments`/`HIDDEN_ARGUMENTS`
(2, 4), `Credentials` (3, 4), `set_login` (4), `set_credentials`/`credentials_of`
(4, 5), `DialogCredentials`/`credentials()`/`credentials_changed()` (5),
`CredentialStoreError` (4, 5) — совпадают во всех употреблениях.

**Зависимость от эксперимента.** Задачи 3 и 4 пишут код под исход «B
работает, кавычки, без `/WA-`» и несут таблицу, что меняется при ином
исходе; исходы «только D» и «файл изменился» останавливают план явно,
а не тихо.
