# T-19. Э8–Э11 — цветовая схема рабочей области EDT (v3.2)

Заказчик выполняет шаги (запуск и выход EDT, действия в редакторе), агент пишет и снимает
файлы скриптом `docs/research/t19-edt-scheme.py` (домен `edt_scheme`, без сервиса и UI).
Каждый исход правит метку в спеке v3.2 §0 и скил `edt-launch` (раздел «Цвета редактора»);
опровергнутый факт — код и тест в том же коммите. Дата проведения — Э10, Э11, Э9 шаг 0 —
18.09.2026; Э8, Э9 шаги 1–4 — <дата>.

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

| id | label | os |
| --- | --- | --- |
| `org.eclipse.e4.ui.css.theme.e4_default` | %theme.win («Light») | win32 (и gtk/mac под своими label) |
| `org.eclipse.e4.ui.css.theme.e4_dark` | %theme.dark («Dark») | win32, linux, macosx |
| `org.eclipse.e4.ui.css.theme.e4_classic` | %theme.classic | — |
| `org.eclipse.e4.ui.css.theme.high-contrast` | %theme.high-contrast | — |

Источник — `plugin.xml` `org.eclipse.ui.themes_1.2.2300.v20230807-1354` **[Д]**. Кандидат
светлой — `org.eclipse.e4.ui.css.theme.e4_default` **[Д]**; подтверждение — шаг 1 (заказчик).

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
| 0. id тем | 4 id (таблица выше); кандидат светлой — `e4_default` [Д] |
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
рабочей области (светлая тема), агент снимает цвета пипеткой → **[Ф, визуально]**. Шаг 1
дал все 22 значения — шаг 2 не понадобился.

| Ключ | Значение | Источник | Метка |
| --- | --- | --- | --- |
| BSL_Keywords | 127,0,85 | `keywordTextStyle` | [Д] |
| BSL_Pragmas | 125,125,125 | `pragmaTextStyle` | [Д] |
| Preprocessor | 0,0,205 | `preprocessorTextStyle` | [Д] |
| Builtinfunction | 127,0,85 | `builtinTextStyle` | [Д] |
| Strings | 42,0,255 | `stringTextStyle` | [Д] |
| Numbers | 0,0,0 | `numberTextStyle` без RGB → `defaultTextStyle` (0,0,0) | [Д] |
| Comment | 63,127,95 | `commentTextStyle` | [Д] |
| Operators | 0,0,0 | `operatorTextStyle` без RGB → default | [Д] |
| Brackets | 0,0,0 | `bracketTextStyle` без RGB → default | [Д] |
| Label | 125,125,125 | `labelTextStyle` | [Д] |
| Others | 0,0,0 | `variableTextStyle`/`defaultTextStyle` (0,0,0) | [Д] |
| Background | 255,255,255 | системный (`.SystemDefault=true`): Windows «Окно» | [Д] |
| Foreground | 0,0,0 | системный: Windows «Текст окна» | [Д] |
| SelectionBackground | 0,120,215 | системный: Windows «Выделение» (COLOR_HIGHLIGHT) | [Д] |
| SelectionForeground | 255,255,255 | системный: Windows «Текст выделения» | [Д] |
| currentLineColor | 232,242,254 | `org.eclipse.ui.editors` plugin.xml, `colorDefinition id="…currentLineColor" value="232,242,254"` | [Д] |
| lineNumberColor | 120,120,120 | там же, `lineNumberRulerColor` value="120,120,120" | [Д] |
| occurrenceIndicationColor | 212,212,212 | `org.eclipse.xtext.ui_2.33.0` plugin.xml, `colorPreferenceKey="occurrenceIndicationColor"` value="212,212,212" | [Д] |
| hyperlinkColor | 0,102,204 | `org.eclipse.ui.editors` plugin.xml: `hyperlinkColor` value="COLOR_LINK_FOREGROUND" → системный цвет ссылки Windows (COLOR_HOTLIGHT 0,102,204) | [Д] |
| FindScope | 185,176,180 | там же, `findScope` value="185,176,180" | [Д] |
| currentIPColor | 198,219,174 | `org.eclipse.debug.ui_3.18.200` plugin.xml, `colorPreferenceKey="currentIPColor"` value="198,219,174" | [Д] |
| printMarginColor | 176,180,185 | `org.eclipse.ui.editors` plugin.xml, `printMarginColor` value="176,180,185" | [Д] |

`EDT_DEFAULTS` совпадал со всеми 22 значениями, кроме `hyperlinkColor` (было 0,0,255 —
системный синий по догадке [?]; стало 0,102,204 — системный COLOR_HOTLIGHT [Д]); константа
и комментарий к ней правятся этим коммитом.

Кроме того (снято тем же прогоном `defaults`, входит в ожидания Э9 шага 4): `plugin.xml`
`org.eclipse.ui.editors` задаёт для тёмной темы `colorOverride` (`currentLineColor` →
COLOR_TITLE_INACTIVE_BACKGROUND_GRADIENT, `printMarginColor` → COLOR_WIDGET_NORMAL_SHADOW,
`hyperlinkColor` → COLOR_LIST_SELECTION, `lineNumberRulerColor` и `findScope` →
COLOR_WIDGET_DARK_SHADOW), а `css/dark/edt-dark_preferencestyle.css` из `bsl.ui` — прямые
значения 9 из 11 токенов: `Builtinfunction` 255,140,110, `BSL_Keywords` 255,120,90, `Comment`
120,136,147, `Operators`/`Others`/`Brackets`/`Numbers` 181,181,181, `Preprocessor` 160,202,244,
`Strings` 240,255,125 (без `Label` и `BSL_Pragmas`) — [Д] ресурс плагина, 18.09.2026.

**Куда уходит.** `EDT_DEFAULTS` с меткой в комментарии; §0 «Цвета EDT по умолчанию».

## Э11. Реальные темы через наш разбор

**Цель.** Таблицы `IDEA_MAP`/`TMTHEME_SCOPES` дают ожидаемое на настоящих файлах.

**Шаг 1 (агент).** `idea-stats "<temp\color\…\IDEA_Themes\Ext\Template.bin>" --show "<светлая>" --show "<тёмная>" --show "<с пустыми>"`
— по каждому из 22 ключей: в скольких из 641 тем цвет найден; для отсутствующих — какие
атрибуты IDEA встречаются в таких темах чаще всего (кандидаты в запасные `IdeaSource`);
три темы — таблица «ключ → hex» и `is_dark`. Ожидание: `Background`/`Foreground`/`BSL_Keywords`/
`Strings`/`Comment`/`Numbers` ≥ 90 %; для остальных — решение по кандидатам.

**Результат.** `idea-stats` по `Template.bin` (641 файл, установка
`PUBID_1236182-ColorSchemesInstaller`): разобрано **626**, **15** — `ValueError` «не XML:
not well-formed (invalid token)»: в атрибуте `name` неэкранированные кавычки
(`<option name="String "$$$"">`, `name="SCOPE_KEY_Revert: MADRID-375 "Group events by flow
change""`). Список: Badwolf, Civic Monokai, ColorfulDark (×3), Cylox, Dev-Tools-Bright,
Greenish, Material Monokai New, Solarized Darcula, Solarized dark green python, Solarized
dark python, Tuteta и ещё два — 2,3 % каталога. Решение **[Р]**: не чиним (правка чужого
экспорта — не наша зона), диалог переноса схемы помечает такие файлы «не удалось прочитать:
не XML …».

Покрытие ключей основным (первым) источником из 626:

| Ключ | Найдено | Доля | Ключ | Найдено | Доля |
| --- | --- | --- | --- | --- | --- |
| BSL_Keywords | 571 | 91 % | Background | 570 | 91 % |
| BSL_Pragmas | 474 | 75 % | Foreground | 575 | 91 % |
| Preprocessor | 495 | 79 % | SelectionBackground | 516 | 82 % |
| Builtinfunction | 462 | 73 % | SelectionForeground | 351 | 56 % |
| Strings | 572 | 91 % | currentLineColor | 518 | 82 % |
| Numbers | 541 | 86 % | lineNumberColor | 482 | 76 % |
| Comment | 530 | 84 % | occurrenceIndicationColor | 429 | 68 % |
| Operators | 440 | 70 % | hyperlinkColor | 435 | 69 % |
| Brackets | 378 | 60 % | FindScope | 493 | 78 % |
| Label | 321 | 51 % | currentIPColor | 414 | 66 % |
| Others | 464 | 74 % | printMarginColor | 385 | 61 % |

Ожидание подтвердилось для `Background`/`Foreground`/`BSL_Keywords`/`Strings` (≥ 90 %);
`Comment` 84 % и `Numbers` 86 % — чуть ниже порога, запасной источник поднимает их до 87 %
и 90 %. Для остальных — цепочки запасных `IdeaSource`, замер (сколько тем закрывает каждый
шаг, накопленная доля):

| Ключ | Цепочка `IdeaSource` (атрибут.компонент) | Покрытие |
| --- | --- | --- |
| BSL_Pragmas | DEFAULT_METADATA.FG → DEFAULT_KEYWORD.FG | 75 → 85 % (+61 через KEYWORD; DEFAULT_ATTRIBUTE +42 отвергнут — XML-атрибут не по смыслу) |
| Preprocessor | DEFAULT_CONSTANT.FG → DEFAULT_METADATA.FG → DEFAULT_KEYWORD.FG | 79 → 83 → 92 % |
| Builtinfunction | DEFAULT_FUNCTION_CALL.FG → DEFAULT_FUNCTION_DECLARATION.FG → DEFAULT_CLASS_NAME.FG | 73 → 81 → 84 % |
| Comment | DEFAULT_LINE_COMMENT.FG → DEFAULT_BLOCK_COMMENT.FG → DEFAULT_DOC_COMMENT.FG | 84 → 85 → 87 % |
| Operators | DEFAULT_OPERATION_SIGN.FG → DEFAULT_SEMICOLON.FG → DEFAULT_DOT.FG → TEXT.FG | 70 → 76 → 78 → 94 % |
| Brackets | DEFAULT_BRACKETS.FG → DEFAULT_PARENTHS.FG → DEFAULT_BRACES.FG → TEXT.FG | 60 → 61 → 61 → 92 % |
| Label | DEFAULT_LABEL.FG → DEFAULT_TAG.FG → DEFAULT_METADATA.FG | 51 → 63 → 80 % |
| Others | DEFAULT_IDENTIFIER.FG → DEFAULT_LOCAL_VARIABLE.FG → TEXT.FG | 74 → 80 → 94 % |
| Numbers | DEFAULT_NUMBER.FG → DEFAULT_CONSTANT.FG | 86 → 90 % |
| Strings | DEFAULT_STRING.FG (запасных нет — VALID_STRING_ESCAPE +1) | 91 % |
| BSL_Keywords | DEFAULT_KEYWORD.FG | 91 % |
| SelectionForeground | SELECTION_FOREGROUND → TEXT.FG | 56 → 92 % |
| occurrenceIndicationColor | IDENTIFIER_UNDER_CARET_ATTRIBUTES.BG → WRITE_IDENTIFIER_UNDER_CARET_ATTRIBUTES.BG → SEARCH_RESULT_ATTRIBUTES.BG | 68 → 70 → 84 % |
| FindScope | SEARCH_RESULT_ATTRIBUTES.BG → TEXT_SEARCH_RESULT_ATTRIBUTES.BG → WRITE_SEARCH_RESULT_ATTRIBUTES.BG | 78 → 83 → 84 % |
| currentIPColor | EXECUTIONPOINT_ATTRIBUTES.BG → BREAKPOINT_ATTRIBUTES.BG | 66 → 68 % |
| printMarginColor | RIGHT_MARGIN_COLOR → INDENT_GUIDE | 61 → 79 % |
| hyperlinkColor | HYPERLINK_ATTRIBUTES.FG → FOLLOWED_HYPERLINK_ATTRIBUTES.FG → DEFAULT_KEYWORD.FG | 69 → 71 → 93 % (ссылка обязана отличаться от текста; цвет ключевых слов контрастен [Р]) |
| lineNumberColor | LINE_NUMBERS_COLOR → WHITESPACES | 76 → 82 % |
| currentLineColor | CARET_ROW_COLOR (SELECTION_BACKGROUND +30 отвергнут — слишком ярко для текущей строки) | 82 % |
| SelectionBackground | SELECTION_BACKGROUND (CARET_ROW_COLOR +32 отвергнут — обратное) | 82 % |
| Background / Foreground | TEXT.BG / TEXT.FG | 91 % |

Остальное дополняет `fill_missing` (±20 от текста/фона) — не запасной источник IDEA, а наш
алгоритм для полностью пустой темы.

Три темы (`--show`):

| Тема | `is_dark` | Найдено ключей (из 22) | Фон | Ключевые слова |
| --- | --- | --- | --- | --- |
| AfterGlow | True (тёмная) | 19/22 | #2E2E2E | #CC7833 |
| Default | False (светлая) | 19/22 | #FFFFFF | — |
| Solarized Light | False (светлая) | 19/22 | #FDF6E3 | #B58900 |

`is_dark` и цвета согласуются с названиями тем — санитарная проверка пройдена.

**Шаг 2 (агент + заказчик).** Файл `.tmTheme` из каталога заказчика (путь — у заказчика;
если нет — поиск `Get-ChildItem -Path $env:USERPROFILE,E:\ -Recurse -Filter *.tmTheme -ErrorAction SilentlyContinue | Select-Object -First 5`);
`tmtheme "<файл>"` — таблица ключ → hex; сверка с ожиданием (ключевые слова, строки,
комментарии, фон). Нет файла — метка `.tmTheme` остаётся **[Д]**, записать.

**Результат.** Поиск `Get-ChildItem -Path $env:USERPROFILE,E:\ -Recurse -Filter *.tmTheme
-ErrorAction SilentlyContinue` (90 с) — файлов `.tmTheme` на машине нет; таблица ниже не
заполнена. Метка `.tmTheme` остаётся **[Д]** до присланного заказчиком файла.

| Тема | Найдено ключей | Расхождения | Правка таблицы |
| --- | --- | --- | --- |

**Куда уходит.** `IDEA_MAP` (запасные источники), `TMTHEME_SCOPES`/`TMTHEME_GENERAL`,
тесты `test_edt_scheme_sources.py`; §0 строки «Тема IDEA», «`.tmTheme`», «Соответствие».
