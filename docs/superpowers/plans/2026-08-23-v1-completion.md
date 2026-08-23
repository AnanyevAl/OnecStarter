# Завершение v1: клиент по умолчанию и очистка кэша — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть содержание v1 по спеке
[2026-08-23-v1-completion-design.md](../specs/2026-08-23-v1-completion-design.md):
настройка «Клиент по умолчанию» и очистка двух кэшей 1С из контекстного меню записи.

**Architecture:** Клиент по умолчанию — новое поле `Settings`, проводка значения
до `Workspace._default_app` (конструктором через `build_runtime` и на лету через
`store.changed`); логика приоритета уже написана в `domain/launch.py::choose_client`
и не меняется. Очистка кэша — новый модуль `services/cache.py` без Qt: чистая
функция путей с проверкой `ID` на GUID (защита от сноса корня, спека §5.1) и слой
замера/удаления с инъекцией файловых операций (протокол `CacheOps`, образец —
`Registry` в `services/autostart.py`); UI строит подменю в `_build_menu`,
спрашивает подтверждение и показывает сводку.

**Tech Stack:** Python 3.13, PySide6 6.10, pytest + pytest-qt (offscreen), ruff, mypy strict.

## Global Constraints

- Ветка `feat/2026-08-23-v1-completion`; в `master` напрямую не коммитить.
- Qt только в `src/onecstarter/ui/` (инвариант 1): `services/cache.py` и правки
  `services/settings.py`, `services/workspace.py` не импортируют PySide6.
  Сторож уже есть — `tests/unit/test_no_qt_in_core.py`.
- Чистые функции путей не обращаются к ФС (инвариант 2): окружение — аргументом.
- Секреты в сообщения не попадают (инвариант 5); в тестах — только выдуманные GUID
  и имена, ничего с рабочей машины.
- Не запускать процессы 1С. Тесты не трогают живые кэши, реестр и `%APPDATA%` —
  только `tmp_path` и фейки.
- После каждой задачи: `uv run pytest -q` (зелёные, до ветки — 1280 passed),
  `uv run ruff check .` и `uv run mypy` — коды выхода 0, проверять по кодам.
  На кириллицу в комментариях ruff требует `noqa: RUF001/RUF002/RUF003` построчно;
  `ruff check . --add-noqa` умеет проставить, но может добавить `RUF100` — вычистить.
- Коммиты: сообщение писать в файл в scratchpad-каталоге и коммитить
  `git commit -F <файл>` (PowerShell 5.1 ломает кириллицу в `-m`), либо Bash-инструментом.
- Тексты пользовательских сообщений — дословно из спеки, где она их даёт
  (§3.5, §3.7); достоверность фактов о 1С — по меткам спеки, новых фактов не выдумывать.
- Мутационная проверка защитных тестов в задачи НЕ входит: по процессу проекта её
  ставит не автор теста, после коммита (см. раздел «После задач» в конце плана).

---

### Task 1: Поле `default_client` в настройках

**Files:**
- Modify: `src/onecstarter/services/settings.py`
- Test: `tests/unit/test_settings.py`

**Interfaces:**
- Consumes: существующие `Settings`, `load_settings`, `save_settings`.
- Produces: `DefaultClient` (Enum: `THIN = "thin"`, `THICK = "thick"`; свойство
  `app_value -> str` со значениями `"ThinClient"` / `"ThickClient"`),
  поле `Settings.default_client: DefaultClient = DefaultClient.THIN`.
  На них опираются задачи 2 и 3.

- [ ] **Step 1: Создать ветку**

```bash
git checkout -b feat/2026-08-23-v1-completion
```

- [ ] **Step 2: Написать падающие тесты**

В `tests/unit/test_settings.py` (импорт `DefaultClient` добавить к существующему
импорту из `onecstarter.services.settings`):

```python
class TestDefaultClient:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        save_settings(path, Settings(default_client=DefaultClient.THICK))
        assert load_settings(path).default_client is DefaultClient.THICK

    def test_missing_key_is_thin(self, tmp_path: Path) -> None:
        """Старый файл без ключа читается без миграции (докстринг модуля)."""
        path = tmp_path / "settings.json"
        path.write_text('{"schema": 1}', encoding="utf-8")
        assert load_settings(path).default_client is DefaultClient.THIN

    def test_unknown_value_is_thin(self, tmp_path: Path) -> None:
        """Незнакомое значение — не порча: дефолт поля, как у режима темы."""
        path = tmp_path / "settings.json"
        path.write_text('{"schema": 1, "default_client": "designer"}', encoding="utf-8")
        assert load_settings(path).default_client is DefaultClient.THIN

    def test_app_values_match_v8i_app_key(self) -> None:
        """Значения — формат ключа `App` секции: их ждёт `choose_client`."""
        assert DefaultClient.THIN.app_value == "ThinClient"
        assert DefaultClient.THICK.app_value == "ThickClient"
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `uv run pytest tests/unit/test_settings.py -q`
Expected: FAIL, `ImportError: cannot import name 'DefaultClient'`.

- [ ] **Step 4: Реализация в `services/settings.py`**

Рядом с `ThemeMode`:

```python
class DefaultClient(Enum):
    """Чем запускать базу, когда клиент не указан в её записи (спека вехи §2).

    «Конфигуратора» и «Авто» здесь нет намеренно (спека §2.4): конфигуратор
    нельзя задать умолчанием, а «Авто» платформа отрабатывает сама через
    /AppAutoCheckMode, когда выбор не сделан явно ([Ф] T-02.6).
    """  # noqa: RUF002

    THIN = "thin"
    THICK = "thick"

    @property
    def app_value(self) -> str:
        """Значение в формате ключа `App` секции `.v8i` — то, что ждёт `choose_client`."""
        return _APP_VALUES[self]


_APP_VALUES = {DefaultClient.THIN: "ThinClient", DefaultClient.THICK: "ThickClient"}
```

В `Settings` добавить поле `default_client: DefaultClient = DefaultClient.THIN`.
В `load_settings` — `default_client=_client_of(payload.get("default_client"))`,
в `save_settings` — `"default_client": settings.default_client.value` в payload.
Загрузчик — по образцу `_theme_of`:

```python
def _client_of(value: Any) -> DefaultClient:
    """Незнакомое значение — не порча: более новая версия могла записать своё."""
    try:
        return DefaultClient(value)
    except ValueError:
        return DefaultClient.THIN
```

Добавить `"DefaultClient"` в `__all__`. Дефолт THIN — чтобы у существующих
установок не изменилось ничего (спека §2.1): сегодня при пустом `App`
запускается именно тонкий.

- [ ] **Step 5: Тесты зелёные, линт и типы чистые**

Run: `uv run pytest tests/unit/test_settings.py -q && uv run ruff check . && uv run mypy`
Expected: PASS, коды 0.

- [ ] **Step 6: Commit**

`feat: настройка «клиент по умолчанию» — поле default_client в Settings`

---

### Task 2: Проводка `default_app` до `Workspace` и табличные тесты приоритета

**Files:**
- Modify: `src/onecstarter/services/workspace.py` (метод + свойство)
- Modify: `src/onecstarter/ui/app.py` (`build_runtime` читает настройки)
- Test: `tests/unit/test_workspace.py`, `tests/unit/test_launch.py`, `tests/ui/test_app.py`

**Interfaces:**
- Consumes: `DefaultClient` из Task 1; `Workspace.__init__(..., default_app=...)`
  и `choose_client(app, default_app, forced)` — уже существуют.
- Produces: `Workspace.set_default_app(default_app: str | None) -> None` и
  read-only свойство `Workspace.default_app -> str | None`. Их использует Task 3.

- [ ] **Step 1: Падающие тесты**

В `tests/unit/test_workspace.py` — файл уже несёт `CONVENTIONS` (THIN→`1cv8c.exe`,
THICK/DESIGNER→`1cv8.exe`), `INSTALLED` и помощник `_raw_workspace(tmp_path, calls)`,
который копирует общую фикстуру, только если `tmp_path/"ibases.v8i"` ещё не создан —
поэтому свой файл пишется ДО вызова помощника:

```python
def test_set_default_app_reaches_launch(tmp_path: Path) -> None:
    """Смена клиента по умолчанию влияет на следующий запуск — без пересборки.

    Проверяется поведение (какой exe в команде), а не хранимое поле:
    правило «тест проверяет поведение, а не намерение».
    """
    (tmp_path / "ibases.v8i").write_bytes(
        '[БезКлиента]\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    calls: list[LaunchCommand] = []
    workspace = _raw_workspace(tmp_path, calls)
    key = workspace.items()[0].key

    workspace.launch(key)
    assert calls[-1].executable.name == "1cv8c.exe"  # тонкий — как и раньше

    workspace.set_default_app("ThickClient")
    workspace.launch(key)
    assert calls[-1].executable.name == "1cv8.exe"  # настройка доехала
    assert workspace.default_app == "ThickClient"
```

В `tests/unit/test_launch.py` — табличный тест приоритета (спека §6):

```python
@pytest.mark.parametrize(
    ("app", "default_app", "forced", "expected", "auto_mode"),
    [
        # настройка работает только при пустом App
        (None, "ThickClient", None, ClientKind.THICK, True),
        (None, "ThinClient", None, ClientKind.THIN, True),
        # App записи бьёт настройку
        ("ThinClient", "ThickClient", None, ClientKind.THIN, False),
        ("ThickClient", "ThinClient", None, ClientKind.THICK, False),
        # принудительный выбор бьёт всё
        ("ThinClient", "ThickClient", ClientKind.DESIGNER, ClientKind.DESIGNER, False),
        (None, "ThickClient", ClientKind.THIN, ClientKind.THIN, False),
    ],
)
def test_priority_table(
    app: str | None,
    default_app: str | None,
    forced: ClientKind | None,
    expected: ClientKind,
    auto_mode: bool,
) -> None:
    """Спека вехи §2.2: принудительный выбор → App записи → настройка."""
    assert choose_client(app, default_app, forced) == ClientChoice(
        expected, auto_check_mode=auto_mode
    )
```

В `tests/ui/test_app.py`:

```python
def test_build_runtime_reads_default_client(tmp_path):
    """Настройка доезжает и до запуска по ярлыку: build_runtime общий
    для main() и run_launch(), поэтому читается здесь, а не только в окне."""
    save_settings(
        tmp_path / "OneCStarter" / "settings.json",
        Settings(default_client=DefaultClient.THICK),
    )
    runtime = build_runtime({"APPDATA": str(tmp_path)})
    assert runtime.workspace.default_app == "ThickClient"
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_workspace.py tests/unit/test_launch.py tests/ui/test_app.py -q`
Expected: FAIL — у `Workspace` нет `set_default_app`/`default_app`;
`test_priority_table` с `default_app` уже зелёный (логика написана) — это
нормально, он фиксирует контракт спеки §6. `test_build_runtime_reads_default_client`
падает: `default_app` равен `None`.

- [ ] **Step 3: Реализация**

`services/workspace.py`, рядом с `set_installations`:

```python
    @property
    def default_app(self) -> str | None:
        """Текущий клиент по умолчанию — сборке приложения и тестам проводки."""
        return self._default_app

    def set_default_app(self, default_app: str | None) -> None:
        """Сменить клиента по умолчанию на лету (настройка «Клиент по умолчанию»).

        Влияет только на последующие запуски; `_rebuild` не зовётся — записи
        списка от выбора клиента не зависят (тот же довод, что
        у `set_installations`).
        """  # noqa: RUF002
        self._default_app = default_app
```

`ui/app.py`, в `build_runtime` — прочитать настройки и передать значение
(импортировать `load_settings` из `onecstarter.services.settings`):

```python
    settings_path = appdata / "OneCStarter" / "settings.json"
    settings = load_settings(settings_path)
    workspace = Workspace(
        paths,
        installations=None,
        conventions=conventions,
        cfg_rules=rules,
        default_app=settings.default_client.app_value,
    )
    return Runtime(workspace, rules, list(conventions), settings_path)
```

Строку про `default_app=None` в докстринге модуля `ui/app.py` (шапка файла)
обновить: default_app теперь приходит из настройки «Клиент по умолчанию»
(`settings.json`), не из cfg — существование параметра `App` уровня
`1cestart.cfg` по-прежнему экспериментально не подтверждено.

- [ ] **Step 4: Зелёные, линт, типы**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, коды 0.

- [ ] **Step 5: Commit**

`feat: клиент по умолчанию доезжает до Workspace — set_default_app и чтение настроек в build_runtime`

---

### Task 3: Сегмент «Клиент по умолчанию» в разделе «Настройки» и смена на лету

**Files:**
- Modify: `src/onecstarter/ui/settings_view.py`
- Modify: `src/onecstarter/ui/app.py` (`_build_main_window`)
- Test: `tests/ui/test_settings_view.py`, `tests/ui/test_app.py`

**Interfaces:**
- Consumes: `DefaultClient` (Task 1), `Workspace.set_default_app` (Task 2),
  `SettingsStore.update(**changes)` и сигнал `store.changed` — существуют.
- Produces: `SettingsView.client_buttons() -> list[QPushButton]` (аксессор
  для тестов), строка «Клиент по умолчанию» в группе «ОКНО И ЗАПУСК».

- [ ] **Step 1: Падающие тесты**

В `tests/ui/test_settings_view.py`:

```python
def test_client_choices_with_thin_selected(application, tmp_path) -> None:
    view, _ = _view(application, tmp_path)
    assert [b.text() for b in view.client_buttons()] == ["Тонкий", "Толстый"]
    assert view.client_buttons()[0].isChecked()


def test_client_row_is_registered(application, tmp_path) -> None:
    """Сегмент привязан к своей строке — не к чужой (урок мутаций 22.08.2026)."""
    view, _ = _view(application, tmp_path)
    control = view.row_control("Клиент по умолчанию")
    assert all(b in control.findChildren(QPushButton) for b in view.client_buttons())


def test_choice_updates_store(application, tmp_path) -> None:
    view, store = _view(application, tmp_path)
    view.client_buttons()[1].click()
    assert store.settings.default_client is DefaultClient.THICK


def test_external_change_syncs_buttons(application, tmp_path) -> None:
    """Смена через store (другой владелец) приводит сегмент к факту."""
    view, store = _view(application, tmp_path)
    store.update(default_client=DefaultClient.THICK)
    assert view.client_buttons()[1].isChecked()
    assert not view.client_buttons()[0].isChecked()
```

(`QPushButton` и `DefaultClient` импортировать в шапке файла.)

В `tests/ui/test_app.py` — проводка до `Workspace` без пересборки окна
(спека §6, последний пункт табличных тестов; образец сборки —
`test_startup_log_has_no_connect_strings` в этом же файле):

```python
def test_default_client_change_reaches_workspace_without_rebuild(
    qtbot, monkeypatch, qapp, workspace_factory, tmp_path
):
    """store.changed → set_default_app: следующий запуск идёт толстым клиентом.

    Проверка поведением — какой exe в команде запуска, — а не полем.
    """
    monkeypatch.setattr(app_module, "GlobalHotkey", _FakeHotkey)
    (tmp_path / "ibases.v8i").write_bytes(
        '[БезКлиента]\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    workspace, calls, _opened = workspace_factory()
    runtime = app_module.Runtime(
        workspace=workspace, cfg_rules=[], conventions=[],
        settings=tmp_path / "settings.json",
    )
    window, _tasks = _build_main_window(qapp, runtime, {"APPDATA": str(tmp_path)})
    qtbot.addWidget(window)
    key = workspace.items()[0].key

    workspace.launch(key)
    assert calls[-1].executable.name == "1cv8c.exe"

    window.settings_store.update(default_client=DefaultClient.THICK)
    workspace.launch(key)
    assert calls[-1].executable.name == "1cv8.exe"
```

Замечание: `workspace_factory` берёт `tmp_path / "ibases.v8i"`, если файл уже
существует — синтетическая запись выше попадает в Workspace вместо общей
фикстуры, поэтому `items()[0]` — именно она.

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_settings_view.py tests/ui/test_app.py -q`
Expected: FAIL — `client_buttons` не существует; в wiring-тесте второй запуск
идёт `1cv8c.exe`.

- [ ] **Step 3: Реализация `SettingsView`**

Константа рядом с `CHOICES`:

```python
CLIENT_CHOICES = (
    (DefaultClient.THIN, "Тонкий"),
    (DefaultClient.THICK, "Толстый"),
)
```

(импортировать `DefaultClient` из `onecstarter.services.settings`).

В `__init__` — поле `self._client_buttons: list[QPushButton] = []` и строка
в группе «ОКНО И ЗАПУСК», сразу после строки автозапуска:

```python
        self._add_row(
            "Клиент по умолчанию",
            "Чем запускать базу, где клиент не указан. Выбор в записи (App) "
            "и Ctrl+1/Ctrl+2 главнее",
            self._build_client_segment(),
        )
```

Сборка сегмента — по образцу `_build_theme_segment` (тот же `#ThemeSeg`,
его красит общий stylesheet):

```python
    def _build_client_segment(self) -> QWidget:
        seg = QWidget()
        seg.setObjectName("ThemeSeg")
        seg_layout = QHBoxLayout(seg)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        buttons = QButtonGroup(self)
        buttons.setExclusive(True)
        for client, label in CLIENT_CHOICES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(client is self._store.settings.default_client)
            button.clicked.connect(lambda _checked=False, c=client: self._choose_client(c))
            buttons.addButton(button)
            seg_layout.addWidget(button)
            self._client_buttons.append(button)
        return seg
```

Реакция и синхронизация:

```python
    def _choose_client(self, client: DefaultClient) -> None:
        self._store.update(default_client=client)
```

В `_sync`, после цикла по кнопкам темы (сигналы не глушатся — `setChecked`
не эмитит `clicked`, как и у темы):

```python
        for button, (client, _label) in zip(
            self._client_buttons, CLIENT_CHOICES, strict=True
        ):
            button.setChecked(client is settings.default_client)
```

Аксессор рядом с `theme_buttons`:

```python
    def client_buttons(self) -> list[QPushButton]:
        return list(self._client_buttons)
```

Докстринг модуля «четыре группы утверждённого мокапа» дополнить: шестая
настройка «Клиент по умолчанию» — спека вехи «Завершение v1», §2.

- [ ] **Step 4: Реализация проводки в `_build_main_window`**

По образцу `apply_close_to_tray` (вызов сразу + подписка):

```python
    def apply_default_client() -> None:
        runtime.workspace.set_default_app(store.settings.default_client.app_value)

    apply_default_client()
    store.changed.connect(apply_default_client)
```

Разместить рядом с `apply_close_to_tray()` / `store.changed.connect(...)`.

- [ ] **Step 5: Зелёные, линт, типы**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, коды 0.

- [ ] **Step 6: Commit**

`feat: сегмент «Клиент по умолчанию» в настройках, смена на лету через store.changed`

---

### Task 4: `services/cache.py` — чистые функции: пути с GUID-защитой, размер, тексты

**Files:**
- Create: `src/onecstarter/services/cache.py`
- Test: `tests/unit/test_cache.py` (новый файл)

**Interfaces:**
- Consumes: ничего из других задач.
- Produces (используют задачи 5, 7, 8):
  - `CacheKind` (Enum: `USER`, `PROGRAM`), `CACHE_TITLES: dict[CacheKind, str]`
    (`"пользовательский"` / `"программный"`);
  - `is_valid_cache_id(section_id: str | None) -> bool`;
  - `cache_path(env: Mapping[str, str], kind: CacheKind, section_id: str | None) -> Path | None`;
  - `format_size(size: int) -> str`;
  - `CacheMeasure` (frozen dataclass: `files: int`, `total_bytes: int`);
  - `ClearReport` (frozen dataclass: `deleted: int`, `freed_bytes: int`, `failed: int`);
  - `clear_question(kind: CacheKind, base_name: str, measured: CacheMeasure) -> str`;
  - `report_text(report: ClearReport) -> str`.

- [ ] **Step 1: Падающие тесты**

`tests/unit/test_cache.py`:

```python
"""services/cache.py: пути, размеры, тексты. Часть — защитные тесты вехи."""

from pathlib import Path

import pytest

from onecstarter.services.cache import (
    CacheKind,
    CacheMeasure,
    ClearReport,
    cache_path,
    clear_question,
    format_size,
    is_valid_cache_id,
    report_text,
)

GUID = "a1b2c3d4-e5f6-4a0b-8c1d-2e3f4a5b6c7d"
ENV = {"APPDATA": r"C:\Users\u\AppData\Roaming", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}


class TestCachePath:
    def test_valid_guid_builds_both_roots(self) -> None:
        assert cache_path(ENV, CacheKind.USER, GUID) == Path(
            r"C:\Users\u\AppData\Roaming\1C\1Cv8"
        ) / GUID
        assert cache_path(ENV, CacheKind.PROGRAM, GUID) == Path(
            r"C:\Users\u\AppData\Local\1C\1Cv8"
        ) / GUID

    @pytest.mark.parametrize(
        "section_id",
        [
            None,
            "",                      # ГЛАВНЫЙ РИСК (спека §5.1): пустой ID дал бы сам корень
            "не-guid",
            f" {GUID}",              # пробелы по краям — имя каталога не совпадёт
            f"{GUID} ",
            GUID.replace("-", ""),   # 32 hex без дефисов — не форма ID
            GUID[:-1],               # обрезанный
        ],
    )
    def test_invalid_id_gives_no_address(self, section_id: str | None) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §5.1, §6): без валидного GUID адреса нет вовсе.

        При пустом ID склейка Path(root)/"1C"/"1Cv8"/"" дала бы САМ корень
        %LOCALAPPDATA%\\1C\\1Cv8, и рекурсивное удаление снесло бы кэши всех
        баз разом. Кандидат мутационной проверки: снять проверку GUID
        в cache_path — этот тест обязан упасть на пустом ID.
        """  # noqa: RUF002
        assert cache_path(ENV, CacheKind.USER, section_id) is None
        assert cache_path(ENV, CacheKind.PROGRAM, section_id) is None

    def test_missing_root_gives_no_address(self) -> None:
        assert cache_path({}, CacheKind.USER, GUID) is None
        assert cache_path({"APPDATA": ""}, CacheKind.USER, GUID) is None

    def test_is_valid_cache_id(self) -> None:
        assert is_valid_cache_id(GUID)
        assert is_valid_cache_id(GUID.upper())
        assert not is_valid_cache_id(None)
        assert not is_valid_cache_id("")


class TestFormatSize:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            (0, "0 Б"),
            (1023, "1023 Б"),
            (1024, "1 КБ"),
            (9728, "9,5 КБ"),                # 9.5 КБ — один знак, запятая
            (217055232, "207 МБ"),           # пример спеки §3.5
            (3113851290, "2,9 ГБ"),          # стиль протокола T-05.10
        ],
    )
    def test_table(self, size: int, expected: str) -> None:
        assert format_size(size) == expected


class TestTexts:
    def test_program_question_is_calm(self) -> None:
        text = clear_question(
            CacheKind.PROGRAM, "Бухгалтерия", CacheMeasure(files=412, total_bytes=217055232)
        )
        assert "Удалить программный кэш базы «Бухгалтерия» (207 МБ)?" in text
        assert "создаст заново" in text
        # Про пользовательский состав программный вопрос не говорит.
        assert "история ввода" not in text

    def test_user_question_lists_contents_without_promises(self) -> None:
        """Спека §3.5: перечисляет состав, «ничего страшного» не обещает."""
        text = clear_question(
            CacheKind.USER, "Бухгалтерия", CacheMeasure(files=10, total_bytes=1024)
        )
        assert "Удалить пользовательский кэш базы «Бухгалтерия» (1 КБ)?" in text
        assert "настройки форм" in text
        assert "история ввода" in text
        assert "словар" in text

    @pytest.mark.parametrize(
        ("report", "expected"),
        [
            (
                ClearReport(deleted=412, freed_bytes=217055232, failed=0),
                "Удалено 412 файлов, освобождено 207 МБ.",
            ),
            (
                ClearReport(deleted=412, freed_bytes=217055232, failed=7),
                "Удалено 412 файлов, освобождено 207 МБ. Не удалось удалить 7 — "
                "файлы заняты запущенной 1С; закройте программу и повторите.",
            ),
            (ClearReport(deleted=1, freed_bytes=1024, failed=0), "Удалён 1 файл, освобождено 1 КБ."),
            (ClearReport(deleted=2, freed_bytes=0, failed=0), "Удалено 2 файла, освобождено 0 Б."),
        ],
    )
    def test_report_text(self, report: ClearReport, expected: str) -> None:
        assert report_text(report) == expected
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_cache.py -q`
Expected: FAIL, `ModuleNotFoundError: onecstarter.services.cache`.

- [ ] **Step 3: Реализация — создать `src/onecstarter/services/cache.py`**

```python
"""Очистка кэшей 1С по `ID` записи (спека вехи «Завершение v1», §3–§5).

Кэшей два, и это разные по смыслу хранилища (терминология заказчика,
[Проверено, 23.08.2026], протокол T-05.10):

- пользовательский — `%APPDATA%\\1C\\1Cv8\\<ID>`: профили клиентов
  `1cv8.pfl`/`1cv8c.pfl`, история ввода, словарь;
- программный — `%LOCALAPPDATA%\\1C\\1Cv8\\<ID>`: `Config`, `ConfigSave`,
  `SICache` — кэш конфигурации.

Имя каталога кэша равно `ID` секции `.v8i` [Проверено, 23.08.2026: 58
совпадений из 66]. Путь строится ТОЛЬКО из корня окружения и `ID`,
прошедшего проверку на GUID: при пустом `ID` склейка дала бы сам корень
`%LOCALAPPDATA%\\1C\\1Cv8`, и рекурсивное удаление снесло бы кэши всех баз
разом (спека §5.1 — главный риск вехи). Без валидного `ID` адреса нет вовсе.

Удаление — рекурсивным обходом, а не перечнем известных имён: `vrs-cache`
лежит внутри `<ID>\\<user>\\` [Проверено], жёсткий перечень протух бы молча
при смене версии платформы. Обход не следует за junction и символическими
ссылками (спека §5.2) и не останавливается на первой ошибке (решение
заказчика: «пробовать и честно докладывать»). Файловые операции подаются
протоколом `CacheOps` — тот же приём, что `Registry`
в `services/autostart.py`: тест моделирует занятый файл, не имея настоящего.
"""  # noqa: RUF002

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

__all__ = [
    "CACHE_TITLES",
    "CacheKind",
    "CacheMeasure",
    "ClearReport",
    "cache_path",
    "clear_question",
    "format_size",
    "is_valid_cache_id",
    "report_text",
]


class CacheKind(Enum):
    USER = "user"        # %APPDATA%
    PROGRAM = "program"  # %LOCALAPPDATA%


CACHE_TITLES = {CacheKind.USER: "пользовательский", CacheKind.PROGRAM: "программный"}

_ROOT_VARS = {CacheKind.USER: "APPDATA", CacheKind.PROGRAM: "LOCALAPPDATA"}

_GUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def is_valid_cache_id(section_id: str | None) -> bool:
    """GUID и только GUID, без трима: платформа именует каталог точным значением
    `ID`, и значение с пробелами по краям с именем каталога не совпадёт.
    """
    return section_id is not None and _GUID.fullmatch(section_id) is not None


def cache_path(
    env: Mapping[str, str], kind: CacheKind, section_id: str | None
) -> Path | None:
    """Адрес кэша записи. `None` — адреса нет: невалидный `ID` или нет корня.

    Чистая функция (инвариант 2): обращений к ФС нет, окружение — аргументом.
    Проверка на GUID — защита §5.1: `Path(root) / "1C" / "1Cv8" / ""` дала бы
    сам корень, пустые сегменты pathlib молча отбрасывает.
    """
    if section_id is None or not is_valid_cache_id(section_id):
        return None
    root = env.get(_ROOT_VARS[kind])
    if not root:
        return None
    return Path(root) / "1C" / "1Cv8" / section_id


@dataclass(frozen=True)
class CacheMeasure:
    """Итог замера перед удалением — для вопроса подтверждения (спека §3.5)."""

    files: int
    total_bytes: int


@dataclass(frozen=True)
class ClearReport:
    """Итог удаления: два числа и счётчик первичных отказов (спека §3.7)."""

    deleted: int      # удалено файлов и ссылок
    freed_bytes: int  # сумма размеров удалённых файлов
    failed: int       # первичные отказы; вторичные «папка не пуста» не считаются


_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")


def format_size(size: int) -> str:
    """«207 МБ», «2,9 ГБ» — стиль протокола T-05.10: запятая и один знак
    после неё, только когда значение меньше десяти и дробь не нулевая.
    """
    value = float(size)
    index = 0
    while value >= 1024 and index < len(_UNITS) - 1:
        value /= 1024
        index += 1
    if index > 0 and value < 10:
        text = f"{value:.1f}".replace(".", ",").removesuffix(",0")
    else:
        text = str(int(value))
    return f"{text} {_UNITS[index]}"


def clear_question(kind: CacheKind, base_name: str, measured: CacheMeasure) -> str:
    """Текст подтверждения — всегда с именем базы и размером (спека §3.5).

    Тон различается по меткам достоверности, а не по стилю:
    про программный кэш [Проверено, 23.08.2026, шаг 8] — после удаления база
    запускается как обычно; про пользовательский последствия [не проверено],
    поэтому текст перечисляет измеренный состав каталога (шаг 6) и не обещает
    «ничего страшного».
    """  # noqa: RUF002
    head = (
        f"Удалить {CACHE_TITLES[kind]} кэш базы «{base_name}» "
        f"({format_size(measured.total_bytes)})?"
    )
    if kind is CacheKind.PROGRAM:
        return f"{head}\n\nКэш конфигурации платформа создаст заново при следующем запуске базы."
    return (
        f"{head}\n\nВместе с ним будут удалены настройки форм, история ввода "
        "и словарь этой базы."
    )


def _deleted_phrase(count: int) -> str:
    """«Удалён 1 файл», «Удалено 2 файла», «Удалено 412 файлов»."""
    if count % 100 not in range(11, 15):
        if count % 10 == 1:
            return f"Удалён {count} файл"
        if count % 10 in (2, 3, 4):
            return f"Удалено {count} файла"
    return f"Удалено {count} файлов"


def report_text(report: ClearReport) -> str:
    """Два числа и ничего лишнего (спека §3.7); трассировки не показываются.

    Вторичные отказы («Папка не пуста») в `failed` не входят по построению
    `clear`: каталог не удалился из-за занятого файла, о котором уже сказано.
    """
    head = f"{_deleted_phrase(report.deleted)}, освобождено {format_size(report.freed_bytes)}."
    if not report.failed:
        return head
    return (
        f"{head} Не удалось удалить {report.failed} — файлы заняты "
        "запущенной 1С; закройте программу и повторите."
    )
```

- [ ] **Step 4: Зелёные, линт, типы**

Run: `uv run pytest tests/unit/test_cache.py tests/unit/test_no_qt_in_core.py -q && uv run ruff check . && uv run mypy`
Expected: PASS, коды 0. Новый модуль добавляется в кортеж CORE сторожа
`tests/unit/test_no_qt_in_core.py` (сделано fix-волной финального ревью) —
сам по себе он в эту проверку не попадает.

- [ ] **Step 5: Commit**

`feat: services/cache — адреса кэшей с GUID-защитой, формат размера, тексты`

---

### Task 5: `services/cache.py` — замер и удаление с инъекцией файловых операций

**Files:**
- Modify: `src/onecstarter/services/cache.py`
- Test: `tests/unit/test_cache.py`

**Interfaces:**
- Consumes: `CacheMeasure`, `ClearReport` из Task 4.
- Produces (используют задачи 7, 8):
  - `EntryKind` (Enum: `FILE`, `DIR`, `LINK`);
  - `CacheEntry` (frozen dataclass: `path: Path`, `kind: EntryKind`, `size: int`);
  - `CacheOps` (Protocol: `list_dir(path) -> list[CacheEntry]`, `is_dir(path) -> bool`,
    `remove_file(path) -> None`, `remove_dir(path) -> None`, `remove_link(path) -> None`);
  - `WindowsCacheOps` — настоящая ФС;
  - `measure(root: Path, ops: CacheOps) -> CacheMeasure`;
  - `clear(root: Path, ops: CacheOps) -> ClearReport`.

- [ ] **Step 1: Падающие тесты — фейк ФС и сценарии**

Дописать в `tests/unit/test_cache.py` (импорты дополнить: `CacheEntry`,
`CacheOps`, `EntryKind`, `WindowsCacheOps`, `clear`, `measure`):

```python
class FakeCacheOps:
    """ФС в памяти, ведёт себя как настоящая: remove_dir отказывает непустому
    каталогу, занятый файл — PermissionError, удаления реально убирают записи.

    Богатый стимул, а не пустышка — требование мутационной проверки проекта:
    бессильная мутация всегда означала бедный стимул, не слабое утверждение.
    """

    def __init__(self) -> None:
        self.tree: dict[Path, list[CacheEntry]] = {}
        self.busy: set[Path] = set()
        self.unreadable: set[Path] = set()
        self.removed_links: list[Path] = []
        self.listed: list[Path] = []

    def put_dir(self, path: Path) -> None:
        self.tree.setdefault(path, [])
        parent = path.parent
        if parent in self.tree and all(e.path != path for e in self.tree[parent]):
            self.tree[parent].append(CacheEntry(path, EntryKind.DIR, 0))

    def put(self, entry: CacheEntry) -> None:
        self.tree.setdefault(entry.path.parent, []).append(entry)
        if entry.kind is EntryKind.DIR:
            self.tree.setdefault(entry.path, [])

    def list_dir(self, path: Path) -> list[CacheEntry]:
        self.listed.append(path)
        if path in self.unreadable:
            raise PermissionError(5, "отказано в доступе")
        return list(self.tree[path])

    def is_dir(self, path: Path) -> bool:
        return path in self.tree

    def _drop(self, path: Path) -> None:
        for entries in self.tree.values():
            for entry in list(entries):
                if entry.path == path:
                    entries.remove(entry)

    def remove_file(self, path: Path) -> None:
        if path in self.busy:
            raise PermissionError(32, "файл используется другим процессом")
        self._drop(path)

    def remove_dir(self, path: Path) -> None:
        if self.tree.get(path):
            raise OSError(145, "Папка не пуста")
        self.tree.pop(path, None)
        self._drop(path)

    def remove_link(self, path: Path) -> None:
        self.removed_links.append(path)
        self._drop(path)


ROOT = Path(r"C:\cache") / GUID


def _standard_tree() -> FakeCacheOps:
    """<ID>/{Config/{a,b}, SICache/c, top} — форма снятая с настоящего кэша."""
    ops = FakeCacheOps()
    ops.put_dir(ROOT)
    ops.put(CacheEntry(ROOT / "Config", EntryKind.DIR, 0))
    ops.put(CacheEntry(ROOT / "Config" / "a.bin", EntryKind.FILE, 100))
    ops.put(CacheEntry(ROOT / "Config" / "b.bin", EntryKind.FILE, 200))
    ops.put(CacheEntry(ROOT / "SICache", EntryKind.DIR, 0))
    ops.put(CacheEntry(ROOT / "SICache" / "c.bin", EntryKind.FILE, 300))
    ops.put(CacheEntry(ROOT / "top.pfl", EntryKind.FILE, 50))
    return ops


class TestMeasure:
    def test_counts_files_and_bytes_recursively(self) -> None:
        assert measure(ROOT, _standard_tree()) == CacheMeasure(files=4, total_bytes=650)

    def test_unreadable_subdir_is_skipped(self) -> None:
        """Замер — оценка для вопроса, а не отчёт: недочитанное не роняет его."""
        ops = _standard_tree()
        ops.unreadable.add(ROOT / "Config")
        assert measure(ROOT, ops) == CacheMeasure(files=2, total_bytes=350)


class TestClear:
    def test_full_success_removes_everything_including_root(self) -> None:
        ops = _standard_tree()
        report = clear(ROOT, ops)
        assert report == ClearReport(deleted=4, freed_bytes=650, failed=0)
        assert ROOT not in ops.tree

    def test_busy_file_does_not_stop_walk_and_secondary_is_not_counted(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §3.6–§3.7): обход не останавливается,
        вторичная «Папка не пуста» не попадает в счётчик отказов.

        Кандидаты мутационной проверки: остановить обход на первой ошибке
        (b.bin и c.bin перестанут удаляться); начать считать вторичные
        (failed станет 3: файл + Config + корень).
        """  # noqa: RUF002
        ops = _standard_tree()
        ops.busy.add(ROOT / "Config" / "a.bin")
        report = clear(ROOT, ops)
        # b.bin идёт ПОСЛЕ занятого a.bin в том же каталоге — и удалён.
        assert report == ClearReport(deleted=3, freed_bytes=550, failed=1)
        # Config и корень не удалены (не пусты), но это вторичные отказы.
        assert ROOT in ops.tree
        assert any(e.path == ROOT / "Config" / "a.bin" for e in ops.tree[ROOT / "Config"])

    def test_link_is_removed_as_link_and_never_walked(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §5.2): по ссылке обход не идёт.

        Кандидат мутационной проверки: последовать за ссылкой (обойти её
        содержимое как каталог) — тест обязан упасть по list_dir на ссылке.
        """
        ops = _standard_tree()
        link = ROOT / "vrs-link"
        ops.put(CacheEntry(link, EntryKind.LINK, 0))
        # Цель ссылки существует как каталог с файлом — обход НЕ должен её видеть.
        outside = Path(r"C:\outside")
        ops.put_dir(outside)
        ops.put(CacheEntry(outside / "чужое.txt", EntryKind.FILE, 999))
        ops.tree[link] = ops.tree[outside]  # если кто-то всё же зайдёт — увидит цель

        report = clear(ROOT, ops)
        assert link in ops.removed_links
        assert link not in ops.listed
        assert any(e.path == outside / "чужое.txt" for e in ops.tree[outside])
        assert report.deleted == 5  # 4 файла + ссылка
        assert report.freed_bytes == 650  # чужие 999 байт не тронуты и не посчитаны

    def test_unreadable_dir_is_one_primary_failure(self) -> None:
        ops = _standard_tree()
        ops.unreadable.add(ROOT / "SICache")
        report = clear(ROOT, ops)
        assert report.failed == 1
        assert report.deleted == 3  # a, b, top.pfl
        assert ROOT in ops.tree  # корень не пуст — вторичный отказ, не считан
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/unit/test_cache.py -q`
Expected: FAIL, `ImportError` на `measure`/`clear`/`EntryKind`.

- [ ] **Step 3: Реализация — дописать в `services/cache.py`**

Импорты дополнить: `import os`, `import stat`, `from typing import Protocol`.
В `__all__` добавить новые имена.

```python
class EntryKind(Enum):
    FILE = "file"
    DIR = "dir"
    LINK = "link"  # symlink или junction: содержимое по ссылке не обходится


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    kind: EntryKind
    size: int  # байт; у каталогов и ссылок 0


class CacheOps(Protocol):
    """Файловые операции обхода и удаления — инъекцией, как `Registry`
    в autostart: тест моделирует занятый файл, не имея настоящего."""

    def list_dir(self, path: Path) -> list[CacheEntry]: ...

    def is_dir(self, path: Path) -> bool: ...

    def remove_file(self, path: Path) -> None: ...

    def remove_dir(self, path: Path) -> None: ...

    def remove_link(self, path: Path) -> None: ...


class WindowsCacheOps:
    """Настоящая файловая система. Единственное место обхода и удаления.

    Ссылкой считается и symlink, и junction: junction под lstat выглядит
    каталогом (S_IFDIR), и без отдельной проверки рекурсия ушла бы по нему
    за пределы кэша (спека §5.2). `DirEntry.is_junction()` — Python 3.12+.
    """

    def list_dir(self, path: Path) -> list[CacheEntry]:
        entries: list[CacheEntry] = []
        with os.scandir(path) as scan:
            for entry in scan:
                if entry.is_symlink() or entry.is_junction():
                    kind, size = EntryKind.LINK, 0
                elif entry.is_dir(follow_symlinks=False):
                    kind, size = EntryKind.DIR, 0
                else:
                    kind, size = EntryKind.FILE, entry.stat(follow_symlinks=False).st_size
                entries.append(CacheEntry(Path(entry.path), kind, size))
        return entries

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def remove_file(self, path: Path) -> None:
        os.remove(path)

    def remove_dir(self, path: Path) -> None:
        os.rmdir(path)

    def remove_link(self, path: Path) -> None:
        # Junction под lstat — каталог (S_IFDIR) и снимается rmdir, который
        # удаляет саму ссылку, не следуя за ней [проверено на этой машине].
        # Симлинк — и на файл, и на каталог — под lstat S_IFLNK и уходит
        # в unlink; симлинк на каталог CPython на Windows удаляет внутри
        # unlink через RemoveDirectoryW [из исходников CPython, на живой
        # машине не проверено: создание симлинка требует привилегии].
        if stat.S_ISDIR(os.lstat(path).st_mode):
            os.rmdir(path)
        else:
            os.unlink(path)


def measure(root: Path, ops: CacheOps) -> CacheMeasure:
    """Замер до удаления — для подтверждения с размером (спека §3.5).

    Ошибки чтения не поднимаются: замер — оценка для вопроса, а не отчёт;
    недочитанное всё равно не удалится и попадёт в отчёт удаления.
    Ссылки считаются записями без размера, их содержимое не обходится.
    """
    files = 0
    total = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = ops.list_dir(directory)
        except OSError:
            continue
        for entry in entries:
            if entry.kind is EntryKind.DIR:
                stack.append(entry.path)
            else:
                files += 1
                total += entry.size
    return CacheMeasure(files=files, total_bytes=total)


def clear(root: Path, ops: CacheOps) -> ClearReport:
    """Удалить дерево кэша. Обход не останавливается на первой ошибке (§3.6).

    Вторичный отказ — не удалившийся каталог, внутри которого остался занятый
    файл: о файле уже сказано, второй раз о том же не говорим (§3.7). Каталог
    с отказами внутри не пробуется вовсе — исход известен заранее. Отказ
    rmdir на каталоге, где всё внутри удалилось, — первичный: о нём ничем
    другим не сказано. По ссылкам не ходим — удаляем их как ссылки (§5.2).
    """
    deleted = 0
    freed = 0
    failed = 0

    def clear_dir(directory: Path) -> bool:
        """Удалить содержимое каталога; True — внутри не осталось ничего."""
        nonlocal deleted, freed, failed
        try:
            entries = ops.list_dir(directory)
        except OSError:
            failed += 1
            return False
        ok = True
        for entry in entries:
            if entry.kind is EntryKind.DIR:
                if clear_dir(entry.path):
                    try:
                        ops.remove_dir(entry.path)
                    except OSError:
                        failed += 1
                        ok = False
                else:
                    ok = False  # вторичный отказ: rmdir не пробуем и не считаем
            elif entry.kind is EntryKind.LINK:
                try:
                    ops.remove_link(entry.path)
                    deleted += 1
                except OSError:
                    failed += 1
                    ok = False
            else:
                try:
                    ops.remove_file(entry.path)
                    deleted += 1
                    freed += entry.size
                except OSError:
                    failed += 1
                    ok = False
        return ok

    if clear_dir(root):
        try:
            ops.remove_dir(root)
        except OSError:
            failed += 1
    return ClearReport(deleted=deleted, freed_bytes=freed, failed=failed)
```

Примечание (реализация): вместо `os.*` используются pathlib-методы —
правила ruff PTH; семантика та же.

- [ ] **Step 4: Зелёные на фейке**

Run: `uv run pytest tests/unit/test_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Интеграционный тест настоящего адаптера (tmp_path + junction)**

Дописать в `tests/unit/test_cache.py`:

```python
class TestWindowsCacheOpsIntegration:
    """Настоящая ФС на tmp_path: живые кэши и профиль не трогаются."""

    def test_measure_and_clear_real_tree(self, tmp_path: Path) -> None:
        root = tmp_path / GUID
        (root / "Config").mkdir(parents=True)
        (root / "Config" / "a.bin").write_bytes(b"x" * 100)
        (root / "top.pfl").write_bytes(b"y" * 50)
        ops = WindowsCacheOps()

        assert measure(root, ops) == CacheMeasure(files=2, total_bytes=150)
        report = clear(root, ops)
        assert report == ClearReport(deleted=2, freed_bytes=150, failed=0)
        assert not root.exists()

    def test_junction_is_removed_without_touching_target(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §5.2) на настоящем reparse point.

        Кандидат мутационной проверки: классифицировать junction каталогом
        (убрать is_junction из list_dir) — содержимое цели будет удалено,
        и тест обязан упасть на «чужое.txt существует».
        """
        import _winapi

        target = tmp_path / "target"
        target.mkdir()
        (target / "чужое.txt").write_bytes(b"z" * 10)
        root = tmp_path / GUID
        root.mkdir()
        (root / "своё.bin").write_bytes(b"a" * 5)
        _winapi.CreateJunction(str(target), str(root / "junction"))
        ops = WindowsCacheOps()

        entries = {e.path.name: e.kind for e in ops.list_dir(root)}
        assert entries["junction"] is EntryKind.LINK

        report = clear(root, ops)
        assert not root.exists()
        assert (target / "чужое.txt").exists()  # цель не тронута
        assert report == ClearReport(deleted=2, freed_bytes=5, failed=0)
```

Если mypy не знает `_winapi.CreateJunction` — добавить на строку импорта
`# type: ignore[attr-defined]` только по факту ошибки, не заранее.

- [ ] **Step 6: Всё зелёное, линт, типы**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, коды 0.

- [ ] **Step 7: Commit**

`feat: services/cache — замер и рекурсивное удаление с инъекцией ФС, junction не обходится`

---

### Task 6: Правка спеки §4 — доступность пунктов и проверка каталога

**Files:**
- Modify: `docs/superpowers/specs/2026-08-23-v1-completion-design.md` (§4, один абзац)

Находка подготовки плана: §3.4 требует «каталога нет на диске — пункт неактивен
с подписью „кэш пуст“», а §4 запрещает обращение к диску при построении меню —
оба буквально выполнить нельзя. §3.4 — утверждённое заказчиком поведение,
значит переписывается правило §4 (правило проекта: «переписывается правило,
а не подгоняется код под текст»).

- [ ] **Step 1: Заменить предложение в §4**

Было (последний абзац блока про UI):

```
**UI** (`ui/bases/view.py`) строит подменю, спрашивает подтверждение
и показывает сводку. Решение о доступности пунктов принимается по данным
записи, а не по обращению к диску в момент построения меню.
```

Стало:

```
**UI** (`ui/bases/view.py`) строит подменю, спрашивает подтверждение
и показывает сводку. Решение о доступности пунктов принимается по данным
записи и дешёвой проверке наличия каталога (`is_dir` двух путей — иначе
«кэш пуст» из §3.4 узнать не из чего); замер размера и обход дерева
в момент построения меню не выполняются — они идут после клика, перед
подтверждением. (Формулировка уточнена при планировании 23.08.2026:
прежняя запрещала любой диск и была невыполнима вместе с §3.4.)
```

- [ ] **Step 2: Commit**

`docs: спека §4 — доступность пунктов допускает дешёвую проверку наличия каталога`

---

### Task 7: Подменю «Очистить кэш» в контекстном меню записи

**Files:**
- Modify: `src/onecstarter/ui/bases/view.py`
- Modify: `src/onecstarter/ui/app.py` (`_build_main_window` передаёт `cache_env`)
- Test: `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `CacheKind`, `cache_path`, `CacheOps`, `WindowsCacheOps`,
  `CacheEntry`, `EntryKind` (задачи 4–5).
- Produces: подменю «Очистить кэш» в `_build_menu`; константы
  `NO_CACHE_ID_NOTE`, `CACHE_EMPTY_NOTE` в `view.py`; параметры конструктора
  `BasesView`: `cache_env: Mapping[str, str] | None = None` (None → `os.environ`),
  `cache_ops: CacheOps | None = None` (None → `WindowsCacheOps()`). Метод
  `clear_cache(key, kind)` появляется в Task 8 — здесь пункты зовут его,
  поэтому в этой задаче создаётся заглушка метода, реализуемая в Task 8
  (см. Step 3).

- [ ] **Step 1: Расширить помощник `_view` и написать падающие тесты**

Помощник `_view` в `tests/ui/test_bases_view.py` (строки ~51–95) принимает
только явные параметры и собирает из них `kwargs` для `BasesView` — произвольных
`**kwargs` у него НЕТ. Расширить его четырьмя параметрами по тому же образцу
«None → параметр не передаётся» (четвёртый — `show_cache_report` — понадобится
задаче 8, завести сразу):

```python
    cache_env: Mapping[str, str] | None = None,
    cache_ops: Any | None = None,
    confirm_cache_clear: Callable[[QWidget | None, str], bool] | None = None,
    show_cache_report: Callable[[QWidget | None, str], None] | None = None,
```

и в сборку `kwargs`:

```python
    if cache_env is not None:
        kwargs["cache_env"] = cache_env
    if cache_ops is not None:
        # Инъекция ФС кэша: настоящая WindowsCacheOps ходила бы в живые
        # каталоги %LOCALAPPDATA% машины, на которой идёт прогон.
        kwargs["cache_ops"] = cache_ops
    if confirm_cache_clear is not None:
        # Тот же приём, что confirm_removal: настоящий диалог блокирует офскрин.
        kwargs["confirm_cache_clear"] = confirm_cache_clear
    if show_cache_report is not None:
        kwargs["show_cache_report"] = show_cache_report
```

(`Mapping` добавить в импорт `collections.abc` файла.)

Фейк ФС взять из `tests/unit/test_cache.py` импортом — тесты являются пакетом
(`tests/unit/__init__.py` и `tests/ui/__init__.py` существуют):
`from tests.unit.test_cache import FakeCacheOps`. Если ruff/mypy будут против —
продублировать минимальный фейк локально (этой задаче нужны только
`tree`/`is_dir`).

Сами тесты:

```python
CACHE_GUID = "a1b2c3d4-e5f6-4a0b-8c1d-2e3f4a5b6c7d"


def _cache_env(tmp_path):
    return {
        "APPDATA": str(tmp_path / "roaming"),
        "LOCALAPPDATA": str(tmp_path / "local"),
    }


def _cache_view(qtbot, workspace_factory, tmp_path, ops, section_lines):
    (tmp_path / "ibases.v8i").write_bytes(section_lines.encode())
    return _view(
        qtbot, workspace_factory, cache_env=_cache_env(tmp_path), cache_ops=ops
    )


def _cache_actions(menu):
    submenu = next(
        (a.menu() for a in menu.actions() if a.text() == "Очистить кэш"), None
    )
    if submenu is None:
        return None
    return {a.text(): a for a in submenu.actions()}


def test_cache_submenu_enabled_when_id_and_dirs_exist(
    qtbot, workspace_factory, tmp_path
):
    ops = FakeCacheOps()
    for var in ("roaming", "local"):
        ops.tree[Path(tmp_path / var / "1C" / "1Cv8" / CACHE_GUID)] = []
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n',
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert set(actions) == {"Пользовательский…", "Программный…"}
    assert actions["Пользовательский…"].isEnabled()
    assert actions["Программный…"].isEnabled()


def test_cache_items_disabled_without_id(qtbot, workspace_factory, tmp_path):
    """Спека §3.4: нет ID — адреса не существует, оба пункта неактивны.

    ЗАЩИТНЫЙ ТЕСТ пары к GUID-проверке §5.1: кандидат мутации — снять
    проверку в cache_path, пункты станут активными и тест упадёт.
    """
    ops = FakeCacheOps()
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        '[БезID]\r\nConnect=File="C:\\B";\r\n',
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert not actions["Пользовательский…"].isEnabled()
    assert not actions["Программный…"].isEnabled()
    assert "ID" in actions["Программный…"].toolTip()


def test_cache_item_disabled_when_directory_missing(
    qtbot, workspace_factory, tmp_path
):
    """Каталог есть только у пользовательского кэша — программный неактивен."""
    ops = FakeCacheOps()
    ops.tree[Path(tmp_path / "roaming" / "1C" / "1Cv8" / CACHE_GUID)] = []
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n',
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert actions["Пользовательский…"].isEnabled()
    assert not actions["Программный…"].isEnabled()
    assert actions["Программный…"].toolTip() == "кэш пуст"


def test_group_menu_has_no_cache_submenu(qtbot, workspace_factory, tmp_path):
    """Спека §3.4: у строки-группы подменю не показывается вовсе."""
    ops = FakeCacheOps()
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f"[Группа]\r\nID={CACHE_GUID}\r\nOrderInList=-1\r\nFolder=/\r\n",
    )
    item = view.workspace().items()[0]
    assert item.is_group
    menu = view._build_group_menu(item, item.key)
    assert _cache_actions(menu) is None
```

- [ ] **Step 2: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_bases_view.py -q`
Expected: FAIL — подменю «Очистить кэш» не находится (`actions` = None →
TypeError/assert).

- [ ] **Step 3: Реализация в `view.py`**

Импорты: `import os` в шапку; `from collections.abc import Mapping` (уже есть
`Callable, Sequence` — дополнить); `from onecstarter.services import cache`.

Константы рядом с существующими текстами:

```python
NO_CACHE_ID_NOTE = "У записи нет ID — каталог кэша не определить"  # noqa: RUF001
CACHE_EMPTY_NOTE = "кэш пуст"
```

Параметры конструктора `BasesView` (после `choose_shortcut_path`):

```python
        cache_env: Mapping[str, str] | None = None,
        cache_ops: cache.CacheOps | None = None,
```

и в теле `__init__`:

```python
        # Окружение и ФС кэша — инъекцией: тесты подменяют и то и другое,
        # живые кэши в offscreen-прогоне не трогаются.
        self._cache_env: Mapping[str, str] = os.environ if cache_env is None else cache_env
        self._cache_ops: cache.CacheOps = (
            cache.WindowsCacheOps() if cache_ops is None else cache_ops
        )
```

В `_build_menu`, сразу после строки `properties = menu.addAction("Свойства…", ...)`
(выше разделителя перед «В избранное» — спека §3.2: среди операций над записью,
выше разделителя, за которым «Удалить из списка…»):

```python
        self._add_cache_menu(menu, item)
```

Новый метод (рядом с `_build_menu`):

```python
    def _add_cache_menu(self, menu: QMenu, item: InfobaseItem) -> None:
        """Подменю «Очистить кэш» — два пункта, без сочетаний клавиш (спека §3.2).

        Доступность решается по данным записи (ID-GUID) и дешёвой проверке
        наличия каталога; замер размера здесь не выполняется — он идёт после
        клика, перед подтверждением (спека §3.4/§4 в редакции 23.08.2026).
        Многоточия обязательны: каждый пункт ведёт к подтверждению.
        Подсказки неактивных пунктов требуют setToolTipsVisible — тот же
        вывод, что у _build_disabled_group_menu.
        """  # noqa: RUF002
        submenu = menu.addMenu("Очистить кэш")
        submenu.setToolTipsVisible(True)
        labels = (
            (cache.CacheKind.USER, "Пользовательский…"),
            (cache.CacheKind.PROGRAM, "Программный…"),
        )
        for kind, label in labels:
            action = submenu.addAction(
                label,
                lambda _checked=False, k=kind, key=item.key: self.clear_cache(key, k),
            )
            path = cache.cache_path(self._cache_env, kind, item.section_id)
            if path is None:
                action.setEnabled(False)
                action.setToolTip(NO_CACHE_ID_NOTE)
            elif not self._cache_ops.is_dir(path):
                action.setEnabled(False)
                action.setToolTip(CACHE_EMPTY_NOTE)
```

Заглушка метода до Task 8 (иначе пункт при клике падал бы AttributeError;
тело настоящее появится в следующей задаче):

```python
    def clear_cache(self, key: str, kind: cache.CacheKind) -> None:
        """Очистка кэша записи — реализуется задачей 8 плана."""
        raise NotImplementedError
```

В `_build_main_window` (`ui/app.py`) передать окружение в `BasesView`:

```python
    view = BasesView(
        runtime.workspace,
        installations=None,
        cfg_rules=runtime.cfg_rules,
        recent_limit=lambda: store.settings.recent_limit,
        palette=controller.palette,
        cache_env=env,
    )
```

(`cache_ops` не передаётся — настоящая ФС; `run_smoke` получает песочный `env`,
и `is_dir` в нём смотрит только в песочницу.)

- [ ] **Step 4: Зелёные, весь набор**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS. Если какой-то существующий тест меню проверяет полный состав
пунктов — обновить его ожидания, добавив «Очистить кэш» (состав меню изменился
по спеке, тест фиксирует новый состав).

- [ ] **Step 5: Commit**

`feat: подменю «Очистить кэш» в контекстном меню записи, доступность по ID и наличию каталога`

---

### Task 8: Сценарий очистки: замер → подтверждение → удаление → сводка

**Files:**
- Modify: `src/onecstarter/ui/dialogs/confirm.py` (подтверждение очистки)
- Modify: `src/onecstarter/ui/bases/view.py` (`clear_cache` + инъекции)
- Test: `tests/ui/test_confirm.py`, `tests/ui/test_bases_view.py`

**Interfaces:**
- Consumes: `measure`, `clear`, `clear_question`, `report_text` (задачи 4–5),
  заглушка `clear_cache` и `_cache_env`/`_cache_ops` (Task 7),
  `build_confirm_box`/`is_confirmed` из `ui/dialogs/buttons.py`.
- Produces: `build_cache_confirm_box(parent, question) -> QMessageBox`,
  `confirm_cache_clear(parent, question) -> bool` в `dialogs/confirm.py`;
  `show_cache_report(parent, text) -> None` в `view.py`; параметры конструктора
  `BasesView`: `confirm_cache_clear=...`, `show_cache_report=...`.

- [ ] **Step 1: Падающие тесты диалога**

В `tests/ui/test_confirm.py` (по образцу тестов `build_removal_confirm_box`
в этом же файле):

```python
def test_cache_confirm_box_has_yes_no_with_no_as_default(qtbot):
    box = build_cache_confirm_box(None, "Удалить программный кэш базы «Б» (1 КБ)?")
    labels = [button.text() for button in box.buttons()]
    assert labels == ["Да", "Нет"]
    assert box.defaultButton().text() == "Нет"
    assert "Удалить программный кэш" in box.text()
```

- [ ] **Step 2: Падающие тесты сценария**

В `tests/ui/test_bases_view.py` (использует помощники Task 7; `_view` передаёт
новые kwargs):

```python
def _ops_with_program_cache(tmp_path):
    """Фейк ФС с программным кэшем записи «Кэшная» + её ibases.v8i.

    Файл списка пишется здесь, ДО _view: workspace_factory копирует общую
    фикстуру, только если tmp_path/"ibases.v8i" ещё не создан.
    """
    (tmp_path / "ibases.v8i").write_bytes(
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    ops = FakeCacheOps()
    root = Path(tmp_path / "local" / "1C" / "1Cv8" / CACHE_GUID)
    ops.tree[root] = []
    ops.put(CacheEntry(root / "Config", EntryKind.DIR, 0))
    ops.put(CacheEntry(root / "Config" / "a.bin", EntryKind.FILE, 100))
    ops.put(CacheEntry(root / "top.pfl", EntryKind.FILE, 24))
    return ops, root


def test_clear_cache_without_confirmation_deletes_nothing(
    qtbot, workspace_factory, tmp_path
):
    """ЗАЩИТНЫЙ ТЕСТ (спека §3.5, §6): без «Да» не удаляется ничего.

    Кандидат мутационной проверки: снять подтверждение (звать clear без
    вопроса) — тест обязан упасть на «дерево изменилось».
    """
    ops, root = _ops_with_program_cache(tmp_path)
    before = {p: list(es) for p, es in ops.tree.items()}
    asked: list[str] = []

    def refuse(parent, question):
        asked.append(question)
        return False

    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops, confirm_cache_clear=refuse,
        show_cache_report=lambda parent, text: pytest.fail("сводка без удаления"),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert ops.tree == before
    assert len(asked) == 1


def test_clear_cache_question_carries_name_and_size(qtbot, workspace_factory, tmp_path):
    ops, _root = _ops_with_program_cache(tmp_path)
    asked: list[str] = []
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: asked.append(q) or False,
        show_cache_report=lambda parent, text: None,
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert "Кэшная" in asked[0]
    assert "(124 Б)" in asked[0]  # размер посчитан ДО удаления


def test_clear_cache_confirmed_deletes_and_reports(qtbot, workspace_factory, tmp_path):
    ops, root = _ops_with_program_cache(tmp_path)
    shown: list[str] = []
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: True,
        show_cache_report=lambda parent, text: shown.append(text),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert root not in ops.tree
    assert shown == ["Удалено 2 файла, освобождено 124 Б."]


def test_clear_cache_reports_busy_files_once(qtbot, workspace_factory, tmp_path):
    """Спека §3.7: первичная ошибка в сводке, вторичная «папка не пуста» — нет."""
    ops, root = _ops_with_program_cache(tmp_path)
    ops.busy.add(root / "Config" / "a.bin")
    shown: list[str] = []
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: True,
        show_cache_report=lambda parent, text: shown.append(text),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert shown == [
        "Удалён 1 файл, освобождено 24 Б. Не удалось удалить 1 — "
        "файлы заняты запущенной 1С; закройте программу и повторите."
    ]
```

Параметры `confirm_cache_clear`/`show_cache_report` помощник `_view` уже
пробрасывает — они добавлены в него задачей 7.

- [ ] **Step 3: Убедиться, что падают**

Run: `uv run pytest tests/ui/test_confirm.py tests/ui/test_bases_view.py -q`
Expected: FAIL — нет `build_cache_confirm_box`; `clear_cache` поднимает
`NotImplementedError`; конструктор не знает `confirm_cache_clear`.

- [ ] **Step 4: Реализация диалога — `ui/dialogs/confirm.py`**

```python
# -- Веха «Завершение v1»: очистка кэша ---------------------------------------


def build_cache_confirm_box(parent: QWidget | None, question: str) -> QMessageBox:
    """Собрать подтверждение очистки кэша без показа — для тестов и confirm_cache_clear.

    Текст вопроса готовит `services/cache.py::clear_question` — с именем базы
    и размером, посчитанным до удаления (спека §3.5). Кнопка по умолчанию —
    «Нет»: очистка необратима, случайный Enter не должен её запустить
    (тот же довод, что у удаления записи).
    """  # noqa: RUF002
    box = build_confirm_box(parent, "OneCStarter", question)
    no_button = cast(
        QPushButton, next(button for button in box.buttons() if button.text() == "Нет")
    )
    box.setDefaultButton(no_button)
    return box


def confirm_cache_clear(parent: QWidget | None, question: str) -> bool:
    """Спросить подтверждение очистки кэша. `True` — ответили «Да»."""
    box = build_cache_confirm_box(parent, question)
    box.exec()
    return is_confirmed(box)
```

- [ ] **Step 5: Реализация сценария — `view.py`**

Импорт: `from onecstarter.ui.dialogs.confirm import (ask_group_removal, confirm_cache_clear, confirm_removal)`.
Свободная функция рядом с `browse_for_shortcut_path`:

```python
def show_cache_report(parent: QWidget | None, text: str) -> None:
    """Сводка очистки кэша: два числа, без трассировок (спека §3.7).

    Инъекция, а не прямой вызов в clear_cache — тот же приём, что
    у confirm_removal: настоящий QMessageBox.exec() блокирует офскрин-тест.
    """
    QMessageBox.information(parent, "OneCStarter", text)
```

(`QMessageBox` добавить в импорт из `PySide6.QtWidgets`.)

Параметры конструктора (после `cache_ops`):

```python
        confirm_cache_clear: Callable[[QWidget | None, str], bool] = confirm_cache_clear,
        show_cache_report: Callable[[QWidget | None, str], None] = show_cache_report,
```

в теле `__init__`:

```python
        self._confirm_cache_clear = confirm_cache_clear
        self._show_cache_report = show_cache_report
```

Заглушку `clear_cache` из Task 7 заменить настоящим телом:

```python
    def clear_cache(self, key: str, kind: cache.CacheKind) -> None:
        """Очистить кэш записи: замер → подтверждение → удаление → сводка.

        Подтверждение всегда (решение заказчика 23.08.2026, спека §3.5);
        без «Да» не удаляется ничего. Запись могла исчезнуть между
        построением меню и кликом (внешняя правка файла и rebuild) — молча
        выходим, тот же случай, что у remove_key/create_shortcut. Путь
        строится заново по свежим данным записи, а не ловится при построении
        меню: ключ и ID могли смениться.
        """  # noqa: RUF002
        item = next((i for i in self._workspace.items() if i.key == key), None)
        if item is None:
            return
        path = cache.cache_path(self._cache_env, kind, item.section_id)
        if path is None:
            return
        measured = cache.measure(path, self._cache_ops)
        question = cache.clear_question(kind, item.name, measured)
        if not self._confirm_cache_clear(self, question):
            return
        report = cache.clear(path, self._cache_ops)
        self._show_cache_report(self, cache.report_text(report))
```

- [ ] **Step 6: Всё зелёное, линт, типы**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, коды 0.

- [ ] **Step 7: Commit**

`feat: очистка кэша — замер, подтверждение с размером, удаление и сводка`

---

## После задач (стадии процесса, не задачи плана)

Порядок из next-session-prompt: план → ветка → subagent-driven-development →
**мутационная проверка чужими руками** → **финальное ревью ветки на самой
сильной модели** → слияние. Оба обязательны — на трёх предыдущих ветках они
находили то, что пропустили все прочие круги.

**Кандидаты мутаций** (названы спекой §6; мутацию ставит не автор тестов,
порядок: правка → зелёные → коммит → мутация → откат; результат — в
коммитуемый документ):

1. Снять проверку GUID в `cache_path` → обязан упасть
   `test_invalid_id_gives_no_address` на пустом `ID` и
   `test_cache_items_disabled_without_id`.
2. Снять подтверждение (звать `clear` без вопроса) → обязан упасть
   `test_clear_cache_without_confirmation_deletes_nothing`.
3. Начать считать вторичные ошибки (`ok = False` → `failed += 1` на каталогах) →
   обязаны упасть `test_busy_file_does_not_stop_walk_and_secondary_is_not_counted`
   и `test_clear_cache_reports_busy_files_once`.
4. Остановить обход на первой ошибке → обязан упасть
   `test_busy_file_does_not_stop_walk_and_secondary_is_not_counted`
   (b.bin после занятого a.bin).
5. Последовать за ссылкой (классифицировать junction каталогом) → обязаны
   упасть `test_link_is_removed_as_link_and_never_walked` и
   `test_junction_is_removed_without_touching_target`.

По каждой находке мутаций помнить главный урок: спрашивать не «убита ли
мутация», а «где ещё действует это правило и проверено ли оно там».

**Не забыть при закрытии вехи** (вне ветки задач — по решению заказчика):
`docs/tasks.md` — отметить веху; пуш и релиз решает заказчик.
