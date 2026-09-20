# T-19. Э8–Э11 — цветовая схема рабочей области EDT (v3.2)

Заказчик выполняет шаги (запуск и выход EDT, действия в редакторе), агент пишет и снимает
файлы скриптом `docs/research/t19-edt-scheme.py` (домен `edt_scheme`, без сервиса и UI).
Каждый исход правит метку в спеке v3.2 §0 и скил `edt-launch` (раздел «Цвета редактора»);
опровергнутый факт — код и тест в том же коммите. Дата проведения — Э10, Э11, Э9 шаг 0 —
18.09.2026; Э8, Э9 шаги 1–4 — 20.09.2026. Четыре запуска EDT вместо запланированных 7–8:
шаги объединены (2+3 Э8 в один запуск; 1+2+4 Э9 в один запуск с перезапуском из Preferences).

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

**Шаг 0 (заказчик, 08:05:12).** Создать каталог `E:\tmp\edt-scheme\ws1`, запись «Схема-тест» в
OneCStarter, «Открыть в EDT». В EDT завести проект `23111` и открыть модуль — цвета по
умолчанию (светлые). File → Exit. **Агент:** `snapshot` — после первого запуска и выхода
в `.settings` 19 файлов других плагинов; `com._1c.g5.v8.dt.bsl.ui.prefs`,
`org.eclipse.ui.editors.prefs`, `org.eclipse.e4.ui.css.swt.theme.prefs` отсутствуют — чистая
рабочая область этих файлов не имеет (подтверждает [Ф] «6 из 11»).

**Шаг 1 (запись 08:05:24, запуск, выход 08:07:34).** `write … --csi dark22.csi --canary` →
`bsl.ui.prefs` 931 байт, 13 ключей (11 токенов + версия + `onecstarter.canary=1`), CRLF, по
алфавиту; `editors.prefs` 759 байт, 18 ключей (11 цветов + 5 `.SystemDefault` + версия +
канарейка), CRLF. `snapshot`. **Заказчик:** «Открыть в EDT», открыть модуль (скриншот): фон
редактора тёмный 43,43,43, ключевые слова оранжевые, препроцессор `#Область` фиолетовый,
комментарии серые, номера строк серые — схема применена; тема окна светлая (не трогали). File
→ Exit. **Агент:** `snapshot` (после выхода `workbench.prefs`, `.log` записаны 08:07:33–34) —
оба наших файла **не тронуты**: `editors.prefs` байт в байт как записали; `bsl.ui.prefs` —
тоже (отличие только от нашей более поздней правки на шаге 2). Канарейка на месте, перевод
строки CRLF, порядок прежний.

| Поле | Результат |
| --- | --- |
| Цвета в редакторе после запуска | применены (фон, токены, номера строк, текущая строка) |
| Файлы после выхода: перевод строки | CRLF (не переписаны) |
| Порядок ключей / новые ключи | без изменений; новых нет |
| `onecstarter.canary` | на месте |
| Наши значения | без изменений |

**Шаг 2 (агент, гонка).** Первая попытка (08:08:03) легла уже после выхода EDT — не засчитана.
Повтор: EDT запущена на `ws1` (процесс `1cedt.exe -data E:\tmp\edt-scheme\ws1` подтверждён),
08:11:52 `write … --override Strings=#FF00FF` → в файле `Strings.color=255,0,255`. **Заказчик:**
File → Exit (08:12:04 — `workbench.prefs`). **Агент:** `snapshot` — `bsl.ui.prefs` mtime
08:11:51, байт в байт как при правке: `Strings.color=255,0,255` — **правка пережила выход**.
EDT не переписывает узлы настроек, которые не меняла в памяти (dirty-флаги Eclipse
Preferences). Случай «пользователь меняет цвета в самой EDT при нашей правке» не проверялся —
тогда EDT сбрасывает свои значения на диск и наша правка потеряется **[Д]** → предусловие
«EDT закрыта» остаётся.

**Шаг 3 (агент, 08:09:48, без `.SystemDefault=false`).** `write … --csi dark22.csi
--no-system-default` (флагов 0, `editors.prefs` 477 байт, 13 ключей). **Заказчик:** запуск,
открыть модуль (скриншот): фон редактора **белый** (системный), хотя
`AbstractTextEditor.Color.Background=43,43,43` в файле; токены наши (ключевые слова оранжевые,
строки зелёные), текущая строка и вхождения — наши тёмные (у них флага нет). Выход. **Агент:**
`snapshot`. Флаг **обязателен** для пяти ключей.

| Шаг | Результат |
| --- | --- |
| 0. чистая область | файлов prefs нет (19 файлов других плагинов) [Ф] |
| 1. приём записи | цвета применились; выход не переписал файлы (CRLF, порядок, канарейка) [Ф] |
| 2. гонка (правка при запущенном EDT) | правка пережила выход — EDT не трогает узлы, которые не меняла [Ф]; смена цвета в самой EDT не проверялась [Д] |
| 3. без `.SystemDefault=false` | фон системный (белый), хотя в файле наш — флаг обязателен [Ф] |

**Куда уходит.** §0 строки «Ключи редактора … `.SystemDefault=false`» → [Ф] обязателен (Э8.3);
«Формат файла» → перевод строки CRLF [Ф] (подтверждено и Э9 — EDT переписала `editors.prefs`
при смене темы байт в байт), неизвестные ключи сохраняются [Ф]; «EDT при выходе перезаписывает
prefs из памяти» → переписывает только изменённые узлы [Ф], правка при запущенной EDT
переживает выход, если EDT цвета не меняла (Э8.2); предусловие «EDT закрыта» остаётся; скил
`edt-launch` — новый раздел «Цвета редактора».

## Э9. Тема окна

**Цель.** id светлой темы; читает ли EDT `themeid` при старте; не перекрывает ли тёмная тема
наши цвета токенов (в `bsl.ui` есть `css/dark/edt-dark_preferencestyle.css`, который задаёт
9 из 11 токенов через `IEclipsePreferences` — [Д] ресурс плагина, 18.09.2026).

**Шаг 0 (агент, [Д], 18.09.2026).** Перечислить id тем из `plugin.xml` jar
`org.eclipse.ui.themes_*` (`plugins\` установки 2026.1.2): `<theme id="…" label="…">`.
Записать таблицу id → label.

| id | label | os |
| --- | --- | --- |
| `org.eclipse.e4.ui.css.theme.e4_default` | %theme.win («Light») | win32 (и gtk/mac под своими label) |
| `org.eclipse.e4.ui.css.theme.e4_dark` | %theme.dark («Dark») | win32, linux, macosx |
| `org.eclipse.e4.ui.css.theme.e4_classic` | %theme.classic | — |
| `org.eclipse.e4.ui.css.theme.high-contrast` | %theme.high-contrast | — |

Источник — `plugin.xml` `org.eclipse.ui.themes_1.2.2300.v20230807-1354` **[Д]**. Кандидат
светлой — `org.eclipse.e4.ui.css.theme.e4_default` **[Д]**; подтверждение — шаги 1–2 (заказчик,
20.09.2026).

**Шаги 1, 2, 4 — 20.09.2026, одним запуском с перезапуском из Preferences.** Подготовка
08:12:56: полная схема (5 флагов, строки 106,135,89 — своя, отдельная от Э8) + `theme ws1 dark`
→ `org.eclipse.e4.ui.css.swt.theme.prefs` создан нами: `eclipse.preferences.version=1`,
`themeid=org.eclipse.e4.ui.css.theme.e4_dark`, CRLF.

- **Шаг 2 (тёмный id по файлу).** Запуск: окно **тёмное** (навигатор, панели, редактор) —
  `themeid` читается при старте. Preferences → Внешний вид: «Тема: Тёмная».
- **Шаг 4 (CSS тёмной темы vs наши токены).** В том же запуске строки **зелёные** (наши
  106,135,89), не жёлтые 240,255,125 из `edt-dark_preferencestyle.css`; ключевые слова наши.
  После всего цикла `bsl.ui.prefs` **байт в байт** как записан в 08:12:56 — CSS в файл ничего
  не записал.
- **Шаг 1 (светлый id).** Заказчик: Тема → светлая, Apply and Restart. После перезапуска окно
  светлое, схема цела (строки зелёные, ключевые слова оранжевые). File → Exit. Файл темы,
  переписанный EDT: `eclipse.preferences.version=1`,
  `themeid=org.eclipse.e4.ui.css.theme.e4_default`, CRLF, 79 байт — светлый id
  **`org.eclipse.e4.ui.css.theme.e4_default`**.
- **Шаг 3 (светлый id по файлу)** отдельно не выполнялся: механизм чтения при старте доказан
  шагом 2, id — шагом 1 (записан самой EDT); EDT стартовала светлой с этим id после
  перезапуска.

**Побочный факт (важный).** При смене темы EDT **переписала** `org.eclipse.ui.editors.prefs`
(mtime 08:24:05, при выходе — 08:25:01 `workbench.prefs`), и содержимое совпало **байт в байт**
с нашим: CRLF, тот же порядок по алфавиту, `onecstarter.canary=1` сохранён, 18 ключей. Это
прямое подтверждение: Eclipse на Windows пишет CRLF, ключи по алфавиту, неизвестные ключи не
теряет. `NEW_PREFS_NEWLINE = "\r\n"` → **[Ф]**.

| Шаг | Результат |
| --- | --- |
| 0. id тем | `e4_default` (Light), `e4_dark`, `e4_classic`, `high-contrast` [Д] |
| 1. светлый id | `org.eclipse.e4.ui.css.theme.e4_default` [Ф] |
| 2. тёмная по `themeid` | окно тёмное — читается при старте [Ф] |
| 3. светлая по `themeid` | не выполнялся отдельно (доказано шагами 1–2) |
| 4. тёмная тема vs наши токены | наши; CSS ничего не пишет в prefs [Ф] |

**Куда уходит.** §0 «Тема окна EDT» → светлый id `org.eclipse.e4.ui.css.theme.e4_default` [Ф],
чтение `themeid` при старте [Ф], «CSS тёмной темы» → не перекрывает, в prefs не пишет [Ф];
`THEME_IDS[ThemeChoice.LIGHT]` = светлый id; §1 «Тема окна EDT» — подтверждён Э9 20.09.2026:
три варианта («не трогать», «тёмная», «светлая»); §5 — переключатель в диалоге строится по
`THEME_IDS`, все три варианта доступны, предупреждение о CSS не нужно.

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
