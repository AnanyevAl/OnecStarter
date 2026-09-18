# T-19. Э8–Э11 — цветовая схема рабочей области EDT (v3.2)

Заказчик выполняет шаги (запуск и выход EDT, действия в редакторе), агент пишет и снимает
файлы скриптом `docs/research/t19-edt-scheme.py` (домен `edt_scheme`, без сервиса и UI).
Каждый исход правит метку в спеке v3.2 §0 и скил `edt-launch` (раздел «Цвета редактора»);
опровергнутый факт — код и тест в том же коммите. Дата проведения — <дата>.

Тестовая рабочая область — `E:\tmp\edt-scheme\ws1` (новый пустой каталог; тестовые области v3
удалены 18.09.2026). Рабочие области заказчика `E:\edt\…` не участвуют. EDT — 2026.1.2+2
(`C:\Program Files\1C\1CE\components\1c-edt-2026.1.2+2-x86_64`), запись в OneCStarter
«Схема-тест» → `E:\tmp\edt-scheme\ws1`. Схема для записи — `tests/fixtures/edt_schemes/dark22.csi`
(своя тёмная; ключевые слова `#CC7832`, фон `#2B2B2B`). Снимки — `E:\tmp\edt-scheme\snap\<чч-мм-сс>\`.

Команды агента (все — из корня репозитория):

- `uv run python docs/research/t19-edt-scheme.py snapshot E:\tmp\edt-scheme\ws1 E:\tmp\edt-scheme\snap`
- `uv run python docs/research/t19-edt-scheme.py write E:\tmp\edt-scheme\ws1 --csi tests/fixtures/edt_schemes/dark22.csi --canary`
- `… write … --no-system-default` (шаг Э8.3), `… theme E:\tmp\edt-scheme\ws1 dark|light|<id>` (Э9)
- `uv run python docs/research/t19-edt-scheme.py idea-stats "<путь к Template.bin или каталогу тем>" --show "<тема>"` (Э11)
- `uv run python docs/research/t19-edt-scheme.py tmtheme "<файл.tmTheme>"` (Э11)
- `uv run python docs/research/t19-edt-scheme.py defaults "<каталог plugins EDT>" "<javap.exe>"` (Э10)

## Э8. Приём нашей записи

**Цель.** EDT читает prefs, записанные `render_prefs`; что EDT переписывает при выходе
(перевод строки, порядок, неизвестные ключи); нужен ли `.SystemDefault=false`; теряется ли
правка при запущенном EDT ([Д] → [Ф]).

**Шаг 0 (заказчик).** Создать каталог `E:\tmp\edt-scheme\ws1`, запись «Схема-тест» в
OneCStarter, «Открыть в EDT». В EDT завести проект (New → Project… любого типа или импорт
любого тестового проекта) и открыть модуль — цвета по умолчанию (светлые). File → Exit.
**Агент:** `snapshot` → в `.settings` нет `com._1c.g5.v8.dt.bsl.ui.prefs` и
`org.eclipse.ui.editors.prefs`? Записать перечень файлов каталога.

**Шаг 1 (агент).** `write … --csi dark22.csi --canary` → оба файла созданы (CRLF, версия,
ключ-канарейка `onecstarter.canary=1`). `snapshot`. **Заказчик:** «Открыть в EDT», открыть
модуль: фон тёмный, ключевые слова оранжевые (`#CC7832`), строки зелёные? Ответ и (по желанию)
скриншот. File → Exit. **Агент:** `snapshot` — сравнить с предыдущим: перевод строки (CRLF/LF),
порядок ключей, `onecstarter.canary` на месте?, наши 22 значения не изменены?, появились ли
новые ключи (перечислить).

| Поле | Результат |
| --- | --- |
| Цвета в редакторе после запуска | |
| Файлы после выхода: перевод строки | |
| Порядок ключей / новые ключи | |
| `onecstarter.canary` | |
| Наши значения | |

**Шаг 2 (агент, гонка).** При **запущенном** EDT на `ws1` (заказчик подтверждает, что открыт)
выполнить `write … --csi dark22.csi` с предварительно изменённым цветом: сначала
`uv run python -c "…"` не нужно — скрипт принимает `--override Strings=#FF00FF`. **Заказчик:**
File → Exit. **Агент:** `snapshot` — `Strings` в файле `255,0,255` (правка пережила выход) или
прежнее (EDT переписал из памяти)?

**Шаг 3 (агент).** EDT закрыт. `write … --csi dark22.csi --no-system-default` (без пяти
`.SystemDefault=false`). **Заказчик:** запуск, открыть модуль: фон редактора тёмный (наш) или
белый (системный)? Выход. **Агент:** `snapshot`.

**Куда уходит.** §0 строки «Ключи редактора … `.SystemDefault=false`», «Формат файла»,
«EDT при выходе перезаписывает prefs»; `NEW_PREFS_NEWLINE` (если EDT переписал с LF — константа
`"\n"`); скил `edt-launch` — новый раздел «Цвета редактора».

## Э9. Тема окна

**Цель.** id светлой темы; читает ли EDT `themeid` при старте; не перекрывает ли тёмная тема
наши цвета токенов (в `bsl.ui` есть `css/dark/edt-dark_preferencestyle.css`, который задаёт
9 из 11 токенов через `IEclipsePreferences` — [Д] ресурс плагина, 18.09.2026).

**Шаг 0 (агент, [Д]).** Перечислить id тем из `plugin.xml` jar `org.eclipse.ui.themes_*`
(`plugins\` установки 2026.1.2): `<theme id="…" label="…">`. Записать таблицу id → label.

**Шаг 1 (заказчик).** EDT на `ws1`: Window → Preferences → General → Appearance → Theme:
светлая (Light), Apply and Restart (или выход). **Агент:** `snapshot` →
`org.eclipse.e4.ui.css.swt.theme.prefs`: значение `themeid` — id светлой **[Ф]**.

**Шаг 2 (агент).** EDT закрыт. `theme ws1 dark`. **Заказчик:** запуск — окно тёмное? Выход.
**Шаг 3 (агент).** `theme ws1 light` (id из шага 1). **Заказчик:** запуск — окно светлое? Выход.

**Шаг 4 (агент).** EDT закрыт. `write … --csi dark22.csi` + `theme ws1 dark`. **Заказчик:**
запуск, открыть модуль: ключевые слова `#CC7832` (наши) или `255,120,90` (CSS тёмной темы)?
Выход. **Агент:** `snapshot` — `bsl.ui.prefs`: значения наши или из CSS?

| Шаг | Результат |
| --- | --- |
| 0. id тем | |
| 1. светлый id | |
| 2. тёмная по `themeid` | |
| 3. светлая по `themeid` | |
| 4. тёмная тема vs наши токены | |

**Куда уходит.** §0 «Тема окна EDT»; `THEME_IDS` (светлый id — или `{}`, если шаги 2–3
показали, что ключ при старте не читается); если шаг 4 показал перекрытие — спека §5:
переключатель «тёмная» применяет тему, а схема — при следующем «Применить» (текст диалога),
либо переключатель убирается; решение — заказчика.

## Э10. Цвета EDT по умолчанию

**Цель.** `EDT_DEFAULTS` — из установки, не с потолка.

**Шаг 1 (агент, [Д]).** `defaults "<plugins>" "<javap>"`: скрипт печатает (а) строки
`plugin.xml` четырёх jar (`org.eclipse.ui.editors`, `org.eclipse.ui.workbench.texteditor`,
`org.eclipse.debug.ui`, `com._1c.g5.v8.dt.bsl.ui`) с нашими ключами и `colorPreferenceValue`;
(б) `javap -c -p` классов `com._1c.g5.v8.dt.bsl.ui.syntaxcoloring.BslHighlightingConfiguration`,
`org.eclipse.ui.texteditor.AbstractDecoratedTextEditorPreferenceConstants`,
`org.eclipse.ui.internal.editors.text.TextEditorDefaultsPreferenceInitializer` — фрагменты
вокруг `org/eclipse/swt/graphics/RGB."<init>"` с предшествующими `bipush`/`sipush`/`iconst`
и ближайшей строкой `ldc`; (в) `css/dark/edt-dark_preferencestyle.css` из `bsl.ui`
(тёмные значения токенов). `javap` — `C:\Program Files\1C\1CE\components\axiom-jdk-full-*\bin\javap.exe`
(найти сканом, не хардкодить).

**Шаг 2 (заказчик, только если шаг 1 не дал 22 значений).** Скриншот модуля в чистой
рабочей области (светлая тема), агент снимает цвета пипеткой → **[Ф, визуально]**.

| Ключ | Значение | Источник / метка |
| --- | --- | --- |
| BSL_Keywords | | |
| … (22 строки) | | |

**Куда уходит.** `EDT_DEFAULTS` с меткой в комментарии; §0 «Цвета EDT по умолчанию».

## Э11. Реальные темы через наш разбор

**Цель.** Таблицы `IDEA_MAP`/`TMTHEME_SCOPES` дают ожидаемое на настоящих файлах.

**Шаг 1 (агент).** `idea-stats "<temp\color\…\IDEA_Themes\Ext\Template.bin>" --show "<светлая>" --show "<тёмная>" --show "<с пустыми>"`
— по каждому из 22 ключей: в скольких из 641 тем цвет найден; для отсутствующих — какие
атрибуты IDEA встречаются в таких темах чаще всего (кандидаты в запасные `IdeaSource`);
три темы — таблица «ключ → hex» и `is_dark`. Ожидание: `Background`/`Foreground`/`BSL_Keywords`/
`Strings`/`Comment`/`Numbers` ≥ 90 %; для остальных — решение по кандидатам.

**Шаг 2 (агент + заказчик).** Файл `.tmTheme` из каталога заказчика (путь — у заказчика;
если нет — поиск `Get-ChildItem -Path $env:USERPROFILE,E:\ -Recurse -Filter *.tmTheme -ErrorAction SilentlyContinue | Select-Object -First 5`);
`tmtheme "<файл>"` — таблица ключ → hex; сверка с ожиданием (ключевые слова, строки,
комментарии, фон). Нет файла — метка `.tmTheme` остаётся **[Д]**, записать.

| Тема | Найдено ключей | Расхождения | Правка таблицы |
| --- | --- | --- | --- |

**Куда уходит.** `IDEA_MAP` (запасные источники), `TMTHEME_SCOPES`/`TMTHEME_GENERAL`,
тесты `test_edt_scheme_sources.py`; §0 строки «Тема IDEA», «`.tmTheme`», «Соответствие».
