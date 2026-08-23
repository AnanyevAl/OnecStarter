# План: пакет долга финального ревью вехи «Завершение v1»

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** закрыть пункты 1–9 раздела «Долг, вынесенный финальным ревью вехи
„Завершение v1“» в `docs/tasks.md`. Пункт 10 (очистка блокирует GUI-поток)
не трогается — принятое ограничение v1, решение заказчика 23.08.2026.

**Архитектура:** изменений архитектуры нет. Один косметический фикс чистой
функции (`format_size`), одна правка фейка ФС под поведение настоящей
(`FakeCacheOps.list_dir`), одна правка помощника UI-тестов (фейк по
умолчанию), остальное — закрепляющие тесты. Ветка —
`chore/2026-08-23-completion-debts`, по образцу `chore/2026-08-18-review-debts`.

**Стек:** Python, pytest, PySide6 (только в тестах `tests/ui/`), uv.

## Глобальные ограничения

- Правила `CLAUDE.md` проекта обязательны: Qt только в `src/onecstarter/ui/`;
  выбор версии платформы — чистые функции; никаких процессов 1С и GUI-запусков.
- После каждой задачи: `uv run pytest` (полный), `uv run ruff check .`,
  `uv run mypy` — все с кодом 0. Baseline до начала: **1345 passed**.
- Мутационная стадия (задача 6) исполняется агентом, который не писал ни один
  из тестов задач 1–5 (правило проекта: мутацию ставит не автор теста).
  Табличные тесты чистых функций (задача 1, `format_size`) мутационной
  проверке не подлежат.
- Коммиты — стиль репозитория: `test: …` / `fix: …` / `docs: …`, русский язык.
- Незакоммиченная правка `.gitignore` (`graphify-out/*`) в рабочем дереве —
  чужая для этой ветки, в коммиты не включать (не делать `git add -A`;
  добавлять файлы поимённо).

## Карта файлов

- `src/onecstarter/services/cache.py` — только `format_size` (задача 1).
- `src/onecstarter/ui/bases/view.py` — не меняется (мутации задачи 6 ставятся
  временно и откатываются).
- `tests/unit/test_cache.py` — новые тесты и правка `FakeCacheOps` (задачи 1, 2).
- `tests/ui/test_bases_view.py` — новые UI-тесты, правка докстринга гонки,
  правка помощника `_view` (задачи 2–5).
- `docs/tasks.md` — аннотации закрытия по каждому пункту (задача 7).

---

### Задача 1: `format_size` — единообразное округление (долг №6) и тест `measure` на ссылке (долг №5)

**Files:**
- Modify: `src/onecstarter/services/cache.py:112-125` (`format_size`)
- Test: `tests/unit/test_cache.py` (класс `TestFormatSize`, класс `TestMeasure`)

**Interfaces:**
- Consumes: `format_size`, `measure`, `CacheEntry`, `EntryKind`, `CacheMeasure`,
  `FakeCacheOps`, `_standard_tree`, `ROOT` — всё уже есть в этих файлах.
- Produces: `format_size` с единообразным округлением (банковским, round-half-to-even) в обеих ветках —
  сигнатура не меняется, тексты «207 МБ»/«2,9 ГБ» из существующих тестов
  сохраняются.

Дефект (долг №6): значения <10 округляются (`f"{value:.1f}"`), значения ≥10
усекаются (`int(value)`): 206,94 МБ → «206 МБ», но 9,96 ГБ → «10 ГБ».
Решение: округлять единообразно (банковским round-half-to-even) в обеих ветках; если округление целой ветки
добегает до 1024 — перенос в следующую единицу («1023,6 КБ» → «1 МБ»).

- [ ] **Шаг 1: добавить падающие строки в таблицу `TestFormatSize.test_table`**

К существующим `parametrize`-строкам добавить три:

```python
            (217_000_000, "207 МБ"),         # 206,95 МБ: целая ветка ОКРУГЛЯЕТ, не усекает (долг №6)
            (10_694_058_443, "10 ГБ"),       # 9,96 ГБ: граница «меньше десяти», дробь округляется до целого
            (1_048_400, "1 МБ"),             # 1023,8 КБ: округление добежало до 1024 — перенос единицы
```

- [ ] **Шаг 2: убедиться, что новые строки падают**

Run: `uv run pytest tests/unit/test_cache.py::TestFormatSize -v`
Ожидание: `217_000_000` даёт «206 МБ» (FAIL), `1_048_400` даёт «1023 КБ» (FAIL),
`10_694_058_443` проходит (граница уже округлялась — строка документирует её).

- [ ] **Шаг 3: реализация**

Заменить тело `format_size` (докстринг дополнить, стиль сохраняется):

```python
def format_size(size: int) -> str:
    """«207 МБ», «2,9 ГБ» — стиль протокола T-05.10: запятая и один знак
    после неё, только когда значение меньше десяти и дробь не нулевая.
    Округление единообразное в обеих ветках — банковское (round-half-to-even), как у round() (долг №6 финального ревью:
    целая ветка усекала — 206,94 МБ показывалось «206 МБ», хотя 9,96 ГБ
    округлялось до «10 ГБ»).
    """
    value = float(size)
    index = 0
    while value >= 1024 and index < len(_UNITS) - 1:
        value /= 1024
        index += 1
    if round(value) >= 1024 and index < len(_UNITS) - 1:
        # Округление добежало до следующей единицы: 1023,6 КБ — это «1 МБ».
        value /= 1024
        index += 1
    if index > 0 and value < 10:
        text = f"{value:.1f}".replace(".", ",").removesuffix(",0")
    else:
        text = str(round(value))
    return f"{text} {_UNITS[index]}"
```

Существующие маркеры `# noqa` на докстринге сохранить, если `ruff` их требует
(проверить `uv run ruff check .`).

- [ ] **Шаг 4: прогнать таблицу**

Run: `uv run pytest tests/unit/test_cache.py::TestFormatSize -v`
Ожидание: PASS все строки.

- [ ] **Шаг 5: тест `measure` на ссылке (долг №5), в класс `TestMeasure`**

«Ссылка = запись без размера» согласовано с `clear`, но не закреплено.
Стимул — тот же приём, что `test_link_is_removed_as_link_and_never_walked`
в `TestClear` этого же файла: цель ссылки существует и видима, если кто-то
всё же зайдёт.

```python
    def test_link_counts_as_entry_without_size_and_is_not_walked(self) -> None:
        """Долг №5 финального ревью: «ссылка = запись без размера» — как в clear.

        Ссылка входит в счётчик записей (files), размера не добавляет,
        и measure не обходит её содержимое (спека §5.2).
        """
        ops = _standard_tree()
        link = ROOT / "vrs-link"
        ops.put(CacheEntry(link, EntryKind.LINK, 0))
        outside = Path(r"C:\outside")
        ops.put_dir(outside)
        ops.put(CacheEntry(outside / "чужое.txt", EntryKind.FILE, 999))
        ops.tree[link] = ops.tree[outside]  # если кто-то всё же зайдёт — увидит цель

        assert measure(ROOT, ops) == CacheMeasure(files=5, total_bytes=650)
        assert link not in ops.listed
```

- [ ] **Шаг 6: прогнать и убедиться, что тест зелёный**

Run: `uv run pytest tests/unit/test_cache.py::TestMeasure -v`
Ожидание: PASS (тест закрепляет существующее поведение; его способность падать
докажет мутационная стадия, задача 6).

- [ ] **Шаг 7: полный прогон и линты**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Ожидание: 1349 passed (baseline 1345 + 3 строки таблицы + 1 тест;
parametrize-строки считаются отдельно), ruff и mypy код 0.

- [ ] **Шаг 8: коммит**

```bash
git add src/onecstarter/services/cache.py tests/unit/test_cache.py
git commit -m "fix: format_size округляет единообразно; тест measure на ссылке (долг №5, №6)"
```

---

### Задача 2: `FakeCacheOps.list_dir` — `FileNotFoundError` как у настоящей ФС (долг №8)

**Files:**
- Modify: `tests/unit/test_cache.py:169-173` (`FakeCacheOps.list_dir`)
- Modify: `tests/ui/test_bases_view.py:3358-3389` (докстринг
  `test_clear_cache_silently_exits_when_directory_disappeared`)

**Interfaces:**
- Consumes: `FakeCacheOps` из `tests/unit/test_cache.py` (импортируется
  UI-тестами: `from tests.unit.test_cache import FakeCacheOps`).
- Produces: `FakeCacheOps.list_dir(path)` на отсутствующем в `self.tree` пути
  поднимает `FileNotFoundError` (подкласс `OSError`) — как `os.scandir`
  в `WindowsCacheOps.list_dir`. Задачи 3–5 полагаются на это поведение.

Дефект: на отсутствующем пути фейк давал `KeyError` (`self.tree[path]`),
настоящий `os.scandir` — `FileNotFoundError`. Защитный тест гонки «каталог
исчез» ловил мутацию через незапланированный сигнал (`KeyError` не является
`OSError` и не глотается `measure`) — это зафиксировано в докстринге самого
теста и вынесено долгом №8.

- [ ] **Шаг 1: правка `list_dir`**

```python
    def list_dir(self, path: Path) -> list[CacheEntry]:
        self.listed.append(path)
        if path in self.unreadable:
            raise PermissionError(5, "отказано в доступе")
        if path not in self.tree:
            # Как os.scandir на отсутствующем каталоге (долг №8 финального
            # ревью: KeyError фейка расходился с настоящей ФС, и защитный
            # тест гонки убивал мутацию незапланированным сигналом).
            raise FileNotFoundError(2, "системе не удаётся найти указанный путь")
        return list(self.tree[path])
```

- [ ] **Шаг 2: переписать хвост докстринга теста гонки**

В `test_clear_cache_silently_exits_when_directory_disappeared`
(`tests/ui/test_bases_view.py`) заменить скобку «(МУТАЦИЯ ПРОВЕРЕНА
23.08.2026: на `FakeCacheOps` `measure` падает `KeyError` … как описано
в докстринге `clear_cache`)» на:

```
    Кандидат мутационной проверки: снять проверку `is_dir` перед замером —
    тест обязан упасть через ЗАПЛАНИРОВАННЫЙ сигнал: `FakeCacheOps.list_dir`
    на отсутствующем корне даёт `FileNotFoundError`, как настоящий
    `os.scandir` (долг №8, закрыт 23.08.2026), `measure` глотает его и
    возвращает ноль, и дело доходит до `confirm_cache_clear` с «(0 Б)» —
    то есть до `pytest.fail`. Перепроверка мутации после правки фейка —
    мутационная стадия пакета долга (см. tasks.md).
```

- [ ] **Шаг 3: полный прогон и линты**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Ожидание: все тесты зелёные (ни один существующий тест не перечисляет
отсутствующий путь в успешном сценарии), ruff/mypy код 0. Если что-то упало —
падение означает скрытую зависимость от `KeyError`; чинить тест, а не фейк.

- [ ] **Шаг 4: коммит**

```bash
git add tests/unit/test_cache.py tests/ui/test_bases_view.py
git commit -m "test: FakeCacheOps.list_dir даёт FileNotFoundError, как настоящая ФС (долг №8)"
```

---

### Задача 3: тесты меню — позиция подменю, COMMON-запись, NO_CACHE_ROOT_NOTE (долги №1, №2, №7)

**Files:**
- Test: `tests/ui/test_bases_view.py` — три новых теста рядом с блоком
  «Задача 7: подменю „Очистить кэш“» (после `test_group_menu_has_no_cache_submenu`).
- Modify: импорты того же файла.

**Interfaces:**
- Consumes: помощники файла `_view`, `_cache_view`, `_cache_actions`,
  `_cache_env`, константа `CACHE_GUID`; `FakeCacheOps`;
  `_with_common_list` из `tests/ui/conftest.py`;
  `NO_CACHE_ROOT_NOTE` из `onecstarter.ui.bases.view`;
  `InfobaseSource` из `onecstarter.services.model`.
- Produces: ничего для следующих задач.

- [ ] **Шаг 1: дополнить импорты**

В `tests/ui/test_bases_view.py`:
- строка 38: `from onecstarter.services.model import InfobaseItem` →
  `from onecstarter.services.model import InfobaseItem, InfobaseSource`
- строка 44: `from onecstarter.ui.bases.view import BasesView, DropTarget` →
  `from onecstarter.ui.bases.view import NO_CACHE_ROOT_NOTE, BasesView, DropTarget`
  (порядок имён — как потребует `ruff`/isort)
- строка 50: к импорту из `.conftest` добавить `_with_common_list`.

- [ ] **Шаг 2: тест позиции подменю (долг №1)**

```python
def test_cache_submenu_sits_above_removal_item(qtbot, workspace_factory, tmp_path):
    """Долг №1 финального ревью (спека §3.2): «Очистить кэш» — выше
    разделителя перед «Удалить из списка…», разрушительный пункт остаётся
    один в самом низу.
    """
    ops = FakeCacheOps()
    view, _calls, _errors, _opened = _cache_view(
        qtbot, workspace_factory, tmp_path, ops,
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n',
    )
    item = view.workspace().items()[0]
    actions = view._build_menu(item, item.key).actions()
    texts = [a.text() for a in actions]
    cache_index = texts.index("Очистить кэш")
    removal_index = texts.index("Удалить из списка…")
    assert cache_index < removal_index
    # Между подменю и «Удалить…» есть разделитель — кэш не в «разрушительном» хвосте.
    assert any(a.isSeparator() for a in actions[cache_index + 1 : removal_index])
```

- [ ] **Шаг 3: тест COMMON-записи (долг №2)**

```python
def test_cache_submenu_stays_enabled_for_common_entry(
    qtbot, workspace_factory, tmp_path
):
    """Долг №2 финального ревью: дизейбл пунктов COMMON-записи не зацепил кэш.

    Кэш локален и к источнику записи отношения не имеет — пункты подменю
    осознанно активны, в отличие от «Свойства…» и «Удалить из списка…»,
    которые пишут в файл списка (спека §3.2).
    """
    shared = tmp_path / "shared.v8i"
    shared.write_bytes(
        f'[Общая кэшная]\r\nID={CACHE_GUID}\r\nConnect=Srvr="s";Ref="r";\r\n'.encode()
    )
    cfg_paths = _with_common_list(tmp_path, shared)
    ops = FakeCacheOps()
    for var in ("roaming", "local"):
        ops.tree[Path(tmp_path / var / "1C" / "1Cv8" / CACHE_GUID)] = []
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cfg_paths=cfg_paths, cache_env=_cache_env(tmp_path), cache_ops=ops,
    )
    item = next(
        i for i in view.workspace().items() if i.source is InfobaseSource.COMMON
    )
    menu = view._build_menu(item, item.key)
    by_text = {a.text(): a for a in menu.actions()}
    # Сам дизейбл COMMON на месте…
    assert not by_text["Свойства…"].isEnabled()
    assert not by_text["Удалить из списка…"].isEnabled()
    # …а кэш он не зацепил.
    actions = _cache_actions(menu)
    assert actions is not None
    assert actions["Пользовательский…"].isEnabled()
    assert actions["Программный…"].isEnabled()
```

Замечание исполнителю: `workspace_factory` сам вызывает `apply_common_lists`
по `cfg_paths` (см. `tests/ui/conftest.py`). Если `ruff` откажет импорту
приватного `_with_common_list` — добавить точечный `# noqa` в строку импорта,
как сделано для других осознанных отступлений файла, либо построить cfg
на месте (3 строки: файл-«общий список» + cfg с `CommonInfoBases=`, образец —
`_with_common_list` в conftest).

- [ ] **Шаг 4: тест NO_CACHE_ROOT_NOTE (долг №7)**

```python
def test_cache_item_disabled_without_cache_root(qtbot, workspace_factory, tmp_path):
    """Долг №7 финального ревью: ID валиден, но в окружении нет корня кэша
    (LOCALAPPDATA) — пункт неактивен с подсказкой NO_CACHE_ROOT_NOTE,
    а не CACHE_EMPTY_NOTE: причина другая, подсказка тоже другая.
    """
    ops = FakeCacheOps()
    ops.tree[Path(tmp_path / "roaming" / "1C" / "1Cv8" / CACHE_GUID)] = []
    (tmp_path / "ibases.v8i").write_bytes(
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env={"APPDATA": str(tmp_path / "roaming")},  # LOCALAPPDATA нет
        cache_ops=ops,
    )
    item = view.workspace().items()[0]
    actions = _cache_actions(view._build_menu(item, item.key))
    assert actions is not None
    assert actions["Пользовательский…"].isEnabled()
    assert not actions["Программный…"].isEnabled()
    assert actions["Программный…"].toolTip() == NO_CACHE_ROOT_NOTE
```

- [ ] **Шаг 5: прогнать три новых теста**

Run: `uv run pytest tests/ui/test_bases_view.py -k "cache_submenu_sits_above or stays_enabled_for_common or disabled_without_cache_root" -v`
Ожидание: PASS все три (закрепляют существующее поведение; их способность
падать докажет мутационная стадия, задача 6).

- [ ] **Шаг 6: полный прогон и линты**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Ожидание: все зелёные, коды 0.

- [ ] **Шаг 7: коммит**

```bash
git add tests/ui/test_bases_view.py
git commit -m "test: позиция подменю кэша, COMMON-запись, подсказка без корня кэша (долги №1, №2, №7)"
```

---

### Задача 4: сценарий `clear_cache` — параметризация по виду и выходы `None` (долги №3, №4)

**Files:**
- Test: `tests/ui/test_bases_view.py` — блок «Задача 8: сценарий очистки»
  (после `test_clear_cache_silently_exits_when_directory_disappeared`).

**Interfaces:**
- Consumes: `_view`, `_cache_env`, `_ops_with_program_cache`, `CACHE_GUID`,
  `FakeCacheOps`, `CacheEntry`, `CacheKind`, `EntryKind` — всё уже
  импортировано в файле.
- Produces: ничего для следующих задач.

- [ ] **Шаг 1: параметризованный тест «удаляется ровно запрошенный вид» (долг №3)**

Оба корня существуют и наполнены — перепутанный вид ловится и по удалённому,
и по уцелевшему дереву, и по слову в вопросе:

```python
@pytest.mark.parametrize(
    ("kind", "cleared_var", "kept_var", "title"),
    [
        (CacheKind.USER, "roaming", "local", "пользовательский"),
        (CacheKind.PROGRAM, "local", "roaming", "программный"),
    ],
)
def test_clear_cache_clears_exactly_requested_kind(
    qtbot, workspace_factory, tmp_path, kind, cleared_var, kept_var, title
):
    """Долг №3 финального ревью: сценарий параметризован по CacheKind —
    перепутанный вид на втором пункте ловится: удаляется ровно запрошенный
    корень, второй не тронут, и вопрос называет правильный вид.
    """
    (tmp_path / "ibases.v8i").write_bytes(
        f'[Кэшная]\r\nID={CACHE_GUID}\r\nConnect=File="C:\\B";\r\n'.encode()
    )
    ops = FakeCacheOps()
    roots = {}
    for var in ("roaming", "local"):
        root = Path(tmp_path / var / "1C" / "1Cv8" / CACHE_GUID)
        ops.tree[root] = []
        ops.put(CacheEntry(root / "data.bin", EntryKind.FILE, 100))
        roots[var] = root
    asked: list[str] = []

    def agree(parent, question):
        asked.append(question)
        return True

    view, _calls, _errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=agree,
        show_cache_report=lambda parent, text: None,
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, kind)
    assert title in asked[0].casefold()
    assert roots[cleared_var] not in ops.tree
    assert roots[kept_var] in ops.tree
    assert any(
        e.path == roots[kept_var] / "data.bin" for e in ops.tree[roots[kept_var]]
    )
```

- [ ] **Шаг 2: тест выхода `item is None` (долг №4)**

```python
def test_clear_cache_ignores_unknown_key(qtbot, workspace_factory, tmp_path):
    """Долг №4 финального ревью: запись исчезла между построением меню
    и кликом (`item is None`) — молчаливый выход, как у remove_key и
    create_shortcut: ни вопроса, ни сводки, ни ошибки, дерево не тронуто.
    """
    ops, _root = _ops_with_program_cache(tmp_path)
    before = {p: list(es) for p, es in ops.tree.items()}
    view, _calls, errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: pytest.fail("вопрос по пропавшей записи"),
        show_cache_report=lambda parent, text: pytest.fail("сводка по пропавшей записи"),
    )
    view.clear_cache("id:00000000-0000-0000-0000-000000000000", CacheKind.PROGRAM)
    assert ops.tree == before
    assert errors == []
```

- [ ] **Шаг 3: тест выхода `path is None` (долг №4)**

```python
def test_clear_cache_exits_when_address_is_gone(qtbot, workspace_factory, tmp_path):
    """Долг №4 финального ревью: у записи нет валидного ID — `cache_path`
    даёт `None`, сценарий молча выходит (`path is None`), не падая на
    `is_dir(None)` и не задавая вопросов.
    """
    (tmp_path / "ibases.v8i").write_bytes(
        '[БезID]\r\nConnect=File="C:\\B";\r\n'.encode()  # noqa: RUF001
    )
    ops = FakeCacheOps()
    view, _calls, errors, _opened = _view(
        qtbot, workspace_factory,
        cache_env=_cache_env(tmp_path), cache_ops=ops,
        confirm_cache_clear=lambda parent, q: pytest.fail("вопрос без адреса кэша"),
        show_cache_report=lambda parent, text: pytest.fail("сводка без адреса кэша"),
    )
    item = view.workspace().items()[0]
    view.clear_cache(item.key, CacheKind.PROGRAM)
    assert errors == []
```

- [ ] **Шаг 4: прогнать новые тесты**

Run: `uv run pytest tests/ui/test_bases_view.py -k "clears_exactly_requested_kind or ignores_unknown_key or exits_when_address_is_gone" -v`
Ожидание: PASS (4 прогона: 2 параметра + 2 теста).

- [ ] **Шаг 5: полный прогон и линты**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Ожидание: все зелёные, коды 0.

- [ ] **Шаг 6: коммит**

```bash
git add tests/ui/test_bases_view.py
git commit -m "test: очистка кэша параметризована по виду, выходы item/path is None закреплены (долги №3, №4)"
```

---

### Задача 5: фейковый `cache_ops` по умолчанию в помощнике UI-тестов (долг №9)

**Files:**
- Modify: `tests/ui/test_bases_view.py:94-97` (помощник `_view`).

**Interfaces:**
- Consumes: `FakeCacheOps` (уже импортирован, строка 48).
- Produces: `_view(...)` без явного `cache_ops` подаёт в `BasesView` свежий
  `FakeCacheOps()` вместо умолчания конструктора (настоящая `WindowsCacheOps`).

Дефект: тесты без явного `cache_ops` ходили read-only `is_dir` по живым
`%APPDATA%`/`%LOCALAPPDATA%` машины (по фиктивным GUID — безвредно, но фейк
по умолчанию снимает класс проблем целиком). `BasesView` конструируется
напрямую (мимо `_view`) в ~9 местах файла — эти вызовы не строят меню записей
и ФС не трогают, их не менять (долг №9 говорит о помощнике).

- [ ] **Шаг 1: правка `_view`**

Заменить блок:

```python
    if cache_ops is not None:
        # Инъекция ФС кэша: настоящая WindowsCacheOps ходила бы в живые
        # каталоги %LOCALAPPDATA% машины, на которой идёт прогон.
        kwargs["cache_ops"] = cache_ops
```

на:

```python
    # Инъекция ФС кэша: настоящая WindowsCacheOps ходила бы в живые каталоги
    # %LOCALAPPDATA% машины, на которой идёт прогон. Фейк — по умолчанию,
    # а не по запросу (долг №9 финального ревью): свежий экземпляр на вызов,
    # общий мутировал бы состояние между тестами.
    kwargs["cache_ops"] = cache_ops if cache_ops is not None else FakeCacheOps()
```

- [ ] **Шаг 2: полный прогон и линты**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Ожидание: все зелёные (пустой фейк даёт `is_dir=False` — тот же исход, что
настоящая ФС на фиктивных GUID), коды 0.

- [ ] **Шаг 3: коммит**

```bash
git add tests/ui/test_bases_view.py
git commit -m "test: помощник UI-тестов подаёт фейковый cache_ops по умолчанию (долг №9)"
```

---

### Задача 6: мутационная стадия — независимый агент

**Files:**
- Modify (временно, с откатом): `src/onecstarter/services/cache.py`,
  `src/onecstarter/ui/bases/view.py`.
- Create: отчёт в файл воркспейса плана (не в репозиторий).

Исполнитель этой задачи **не должен быть автором тестов задач 1–5** (правило
проекта). Каждая мутация: внести → прогнать названный тест → убедиться, что
он упал и на чём именно → откатить → записать результат. Рабочее дерево после
задачи — чистое (`git status` — только чужой `.gitignore`).

Мутации:

1. **Долг №4, выход `item`:** в `clear_cache` (`ui/bases/view.py`) удалить
   `if item is None: return`. Ожидание: `test_clear_cache_ignores_unknown_key`
   падает (`AttributeError` на `None.section_id` — guard несущий).
2. **Долг №4, выход `path`:** в `clear_cache` удалить ОБЕ предварительные
   проверки — `if path is None: return` и `if not self._cache_ops.is_dir(path):
   return` — правдоподобное «упрощение» («measure и так глотает ошибки чтения»).
   Ожидание: `test_clear_cache_exits_when_address_is_gone` падает —
   `measure(None)` возвращает ноль (фейк даёт `FileNotFoundError`, `measure`
   его глотает), вопрос «(0 Б)» доходит до `pytest.fail("вопрос без адреса
   кэша")`; заодно падает и `test_clear_cache_silently_exits_when_directory_disappeared`.
   Примечание для отчёта: мутация «удалить ТОЛЬКО `if path is None: return`»
   на фейке БЕССИЛЬНА (`is_dir(None)` честно даёт `False`, выход тот же) —
   так и записать: guard защищает от падения на настоящей `Path.is_dir(None)`
   (`AttributeError`), тест закрывает ветку и отсутствие вопроса/сводки/ошибки.
3. **Долг №7:** в `_add_cache_menu` заменить условие `if path is None:`
   на `if False:` (ветка `NO_CACHE_ROOT_NOTE` мертвеет, управление уходит
   в `elif not self._cache_ops.is_dir(path)`). Ожидание:
   `test_cache_item_disabled_without_cache_root` падает на подсказке —
   вместо `NO_CACHE_ROOT_NOTE` придёт `CACHE_EMPTY_NOTE` («кэш пуст»),
   потому что `is_dir(None)` на фейке даёт `False`.
4. **Долг №2:** в `_add_cache_menu` добавить в конец цикла
   `if item.source is InfobaseSource.COMMON: action.setEnabled(False)`
   (имитация «дизейбл COMMON зацепил кэш»; импорт уже есть в модуле).
   Ожидание: `test_cache_submenu_stays_enabled_for_common_entry` падает
   на `isEnabled()`.
5. **Долг №3:** в `clear_cache` заменить оба использования параметра `kind`
   (`cache.cache_path(..., kind, ...)` и `cache.clear_question(kind, ...)`)
   на `cache.CacheKind.PROGRAM`. Ожидание:
   `test_clear_cache_clears_exactly_requested_kind[CacheKind.USER-...]`
   падает (удалён не тот корень и/или в вопросе не тот вид).
6. **Долг №5:** в `measure` (`services/cache.py`) заменить
   `if entry.kind is EntryKind.DIR:` на
   `if entry.kind is not EntryKind.FILE:` (ссылка обходится как каталог).
   Ожидание: `test_link_counts_as_entry_without_size_and_is_not_walked`
   падает (ссылка в `ops.listed`, чужие 999 байт посчитаны).
7. **Долг №8, перепроверка гонки:** в `clear_cache` удалить
   `if not self._cache_ops.is_dir(path): return`. Ожидание:
   `test_clear_cache_silently_exits_when_directory_disappeared` падает через
   ЗАПЛАНИРОВАННЫЙ сигнал — `pytest.fail("вопрос не должен был задаваться")`
   (фейк теперь даёт `FileNotFoundError`, `measure` глотает, вопрос «(0 Б)»
   доходит до колбэка). Если сигнал другой — это находка, вернуть в волну.
8. **Долг №1:** в `_build_menu` перенести вызов `self._add_cache_menu(menu, item)`
   в самый конец метода (после добавления «Удалить из списка…»). Ожидание:
   `test_cache_submenu_sits_above_removal_item` падает на
   `cache_index < removal_index`.

Каждая мутация ставится и откатывается изолированно (`git diff` пуст между
мутациями, не считая чужого `.gitignore`). Табличные тесты `format_size`
мутационно не проверяются (чистая функция, правило проекта).

Отчёт: файл `mutation-report.md` в воркспейсе плана — по строке на мутацию:
что внесено, какой тест, упал ли, на чём именно (текст ассерта/исключения).
Бессильная мутация из п. 2 — отдельной строкой с обоснованием. Если какой-то
тест НЕ упал — стадия останавливается, находка возвращается волной правок
(чинится тест, мутация перепроверяется).

- [ ] Мутации 1–8 поставлены, результаты записаны, рабочее дерево чистое.
- [ ] Коммитов эта задача не создаёт (если не было волны правок).

---

### Задача 7: аннотации закрытия в `docs/tasks.md`

**Files:**
- Modify: `docs/tasks.md:114-145` (раздел «Долг, вынесенный финальным ревью
  вехи „Завершение v1“»).

Вводный абзац раздела дополнить предложением:

```
Пункты 1–9 закрыты пакетом 23.08.2026 (ветка `chore/2026-08-23-completion-debts`,
по образцу `chore/2026-08-18-review-debts`); мутации по защитным тестам ставил
независимый агент, не автор тестов — результаты в аннотациях пунктов. Пункт 10
остаётся принятым ограничением v1 (решение заказчика 23.08.2026).
```

К каждому из пунктов 1–9 дописать в конец аннотацию вида
`**Закрыт (23.08.2026):** <тест/правка>` — фактические имена тестов и правок
взять из коммитов задач 1–5 и отчёта задачи 6:

1. `**Закрыт (23.08.2026):** test_cache_submenu_sits_above_removal_item; мутация «подменю в конец меню» убита.`
2. `**Закрыт (23.08.2026):** test_cache_submenu_stays_enabled_for_common_entry; мутация «дизейбл COMMON зацепил кэш» убита.`
3. `**Закрыт (23.08.2026):** test_clear_cache_clears_exactly_requested_kind (оба вида, оба корня наполнены); мутация «kind подменён на PROGRAM» убита.`
4. `**Закрыт (23.08.2026):** test_clear_cache_ignores_unknown_key, test_clear_cache_exits_when_address_is_gone; мутации: «снять guard item» убита, «снять обе предварительные проверки, положившись на measure» убита; «снять только guard path» на фейке бессильна — guard защищает от падения настоящей Path.is_dir(None), зафиксировано в отчёте стадии.`
5. `**Закрыт (23.08.2026):** test_link_counts_as_entry_without_size_and_is_not_walked; мутация «обойти ссылку как каталог» убита.`
6. `**Закрыт (23.08.2026):** округление единообразное (банковское, round-half-to-even) в обеих ветках с переносом единицы (1023,6 КБ → «1 МБ»); три новые строки таблицы. Табличный тест чистой функции — без мутационной проверки (правило проекта).`
7. `**Закрыт (23.08.2026):** test_cache_item_disabled_without_cache_root; мутация «снять ветку path is None» убита.`
8. `**Закрыт (23.08.2026):** FakeCacheOps.list_dir даёт FileNotFoundError, как os.scandir; мутация «снять is_dir перед замером» перепроверена — тест гонки падает через запланированный сигнал.`
9. `**Закрыт (23.08.2026):** _view подаёт свежий FakeCacheOps() по умолчанию; прямые конструирования BasesView вне помощника меню записей не строят и ФС не трогают.`

Формулировки в аннотациях — сверить с фактическими результатами задачи 6:
если фактический сигнал мутации отличался от ожидания плана, в tasks.md идёт
факт, и правится сам план (правило «план правится вслед за находкой»).

- [ ] **Шаг 1: внести правки**
- [ ] **Шаг 2: `uv run pytest -q` — тесты не задеты (docs-правка), коды 0**
- [ ] **Шаг 3: коммит**

```bash
git add docs/tasks.md
git commit -m "docs: пакет долга финального ревью вехи закрыт — девять пунктов с мутационной стадией"
```

---

## Самопроверка плана

- Покрытие: долги №1–№9 → задачи 3, 3, 4, 4, 1, 1, 3, 2, 5; мутационная
  стадия — задача 6; фиксация — задача 7. Пункт №10 осознанно не в плане.
- Ожидаемый счётчик тестов: 1345 → 1356 прогонов (задача 1: +4 — три строки
  таблицы и один тест; задача 3: +3; задача 4: +4 прогона, из них 2 —
  параметры одного теста).
- Типы и имена сверены с фактическим кодом (строки указаны по состоянию
  ветки на 73f003c).
- Правка 23.08.2026 (финальное ревью ветки): «арифметическое» округление заменено на точное «банковское (round-half-to-even)» — поведение round()/f-строк; требование долга №6 (единообразие веток) не менялось.
