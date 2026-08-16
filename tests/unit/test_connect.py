import pytest

from onecstarter.domain.connect import (
    ConnectFragment,
    ConnectKind,
    classify_connect,
    extra_fragment_names,
    find_fragment,
    parse_connect,
    raw_fragment_value,
    replace_fragment,
)


def test_file_connect() -> None:
    fragments = parse_connect('File="C:\\Bases\\Demo";')
    assert fragments == [ConnectFragment(name="File", value="C:\\Bases\\Demo")]
    assert classify_connect('File="C:\\Bases\\Demo";') is ConnectKind.FILE


def test_server_connect() -> None:
    fragments = parse_connect('Srvr="srv-1c:1541";Ref="demo";')
    assert fragments == [
        ConnectFragment(name="Srvr", value="srv-1c:1541"),
        ConnectFragment(name="Ref", value="demo"),
    ]
    assert classify_connect('Srvr="srv-1c:1541";Ref="demo";') is ConnectKind.SERVER


def test_web_connect_lowercase_name() -> None:
    # [Ф] в реальных файлах имя фрагмента ws — строчными.
    assert classify_connect('ws="http://web-server/resource/";') is ConnectKind.WEB


def test_classification_is_case_insensitive() -> None:
    assert classify_connect('FILE="C:\\Bases\\Demo";') is ConnectKind.FILE


def test_semicolon_inside_quotes_is_not_separator() -> None:
    fragments = parse_connect('Srvr="srv;backup";Ref="demo";')
    assert fragments[0] == ConnectFragment(name="Srvr", value="srv;backup")


def test_doubled_quotes_become_literal_quote() -> None:
    fragments = parse_connect('File="C:\\Каталог с ""кавычкой""";')  # noqa: RUF001
    assert fragments[0].value == 'C:\\Каталог с "кавычкой"'  # noqa: RUF001


def test_unquoted_value() -> None:
    fragments = parse_connect("Srvr=srv;Ref=demo;")
    assert fragments == [
        ConnectFragment(name="Srvr", value="srv"),
        ConnectFragment(name="Ref", value="demo"),
    ]


def test_find_fragment_case_insensitive() -> None:
    fragments = parse_connect('File="C:\\Bases\\Demo";')
    assert find_fragment(fragments, "file") == "C:\\Bases\\Demo"
    assert find_fragment(fragments, "Srvr") is None


def test_garbage_is_unknown() -> None:
    assert parse_connect("просто текст") == []
    assert classify_connect("просто текст") is ConnectKind.UNKNOWN
    assert classify_connect("") is ConnectKind.UNKNOWN


@pytest.mark.parametrize(
    ("connect", "name", "value", "expected"),
    [
        ('File="D:\\b";', "File", "E:\\c", 'File="E:\\c";'),
        # Всё, кроме значения, сохраняется дословно: пробелы, порядок, кавычки.
        ('Srvr="s"; Ref="r";Usr="admin";', "Srvr", "s2", 'Srvr="s2"; Ref="r";Usr="admin";'),
        # Значение без кавычек в исходнике остаётся без кавычек.
        ("Srvr=s;Ref=r;", "Ref", "r2", "Srvr=s;Ref=r2;"),
        # Регистр имени в файле не трогаем — сравнение регистронезависимое.
        ('srvr="s";', "Srvr", "s2", 'srvr="s2";'),
        # Пробелы вокруг кавычек — часть текста снаружи значения, не трогаются.
        #
        # Круг правок 2: исходный случай был 'Srvr = "s" ;...' (пробел И перед,  # noqa: RUF003
        # И после «=») — пробел перед «=» больше не совместим с решением  # noqa: RUF003
        # заказчика «не обрезать имя» (такой фрагмент теперь не находится
        # вовсе, см. test_parse_connect_does_not_trim_fragment_name). Здесь
        # оставлен только пробел после «=», ради которого случай и написан, —
        # пробелы вокруг кавычек, а не вокруг имени.  # noqa: RUF003
        ('Srvr= "s" ;Ref="r";', "Srvr", "s2", 'Srvr= "s2" ;Ref="r";'),
        # Пустое значение в кавычках — замена вставляется между ними.
        ('Pwd="";Usr="admin";', "Pwd", "x", 'Pwd="x";Usr="admin";'),
        # Пустое значение без кавычек — то же самое, без них.
        ("Ref=;Srvr=s;", "Ref", "r", "Ref=r;Srvr=s;"),
        # Фрагмент без «=» не мешает найти и заменить соседний.
        ("Srvr=s;GARBAGE;Ref=r;", "Ref", "r2", "Srvr=s;GARBAGE;Ref=r2;"),
        # Круг правок 3: пробел после «;» (перед именем следующего фрагмента) —  # noqa: RUF003
        # обычное форматирование, обрезается вместе со всем куском целиком,  # noqa: RUF003
        # а не остаётся частью имени.  # noqa: RUF003
        ('Srvr="s"; Ref="r";', "Ref", "r2", 'Srvr="s"; Ref="r2";'),
        # Экранированная кавычка внутри значения (`""` = литеральная «"»)
        # заменяется целиком вместе со значением — фрагмент ищется по внешним  # noqa: RUF003
        # кавычкам, а не по первой попавшейся.  # noqa: RUF003
        (
            'File="C:\\Дир с ""кавычкой""";Ref="r";',  # noqa: RUF001
            "File",
            "E:\\new",
            'File="E:\\new";Ref="r";',
        ),
    ],
)
def test_replace_fragment_keeps_everything_else(
    connect: str, name: str, value: str, expected: str
) -> None:
    """Правка одного фрагмента не пересобирает строку соединения.

    Пересборка потеряла бы Usr, LocaleCode, wsp* и неизвестные ключи —
    то, что пользователь в неё положил и о чём мы не знаем.
    """  # noqa: RUF002
    assert replace_fragment(connect, name, value) == expected


def test_replace_fragment_rejects_unknown_name() -> None:
    with pytest.raises(KeyError):
        replace_fragment('File="D:\\b";', "Srvr", "s")


def test_extra_fragment_names_lists_what_a_kind_change_would_lose() -> None:
    names = extra_fragment_names('Srvr="s";Ref="r";Usr="admin";LocaleCode="ru";', ["Srvr", "Ref"])
    assert names == ["Usr", "LocaleCode"]


# -- единый расщепитель: parse_connect и fragment_spans больше не расходятся -----
#
# Круг правок 1 (ревью задачи 9, самая сильная модель): parse_connect снимал  # noqa: RUF003
# кавычки и не обрезал имя ключа, fragment_spans обрезал имя и отдавал сырой
# текст. Диалог заполнял поле первым разбором, писал — вторым. На нетронутом  # noqa: RUF003
# диалоге с пробелом вокруг «=» или экранированной кавычкой это переписывало  # noqa: RUF003
# Connect с потерей данных без единого действия пользователя.  # noqa: RUF003
#
# Инвариант ниже — не «replace_fragment корректна» (это было верно и раньше,
# в отрыве от заполнения поля), а «разобрал → положил сырое значение в поле →  # noqa: RUF003
# записал == тождество»: raw_fragment_value обязана возвращать ровно то, что
# replace_fragment примет назад без изменения строки.


@pytest.mark.parametrize(
    ("connect", "name"),
    [
        # Экранированная кавычка внутри значения.
        ('File="C:\\Dir with ""quoted"" bit";Ref="r";', "File"),
        ('File="C:\\Dir with ""quoted"" bit";Ref="r";', "Ref"),
        # Пробел после «=», перед кавычкой.
        ('Srvr= "s" ;Ref="r";', "Srvr"),
        # Значение без кавычек с пробелами вокруг.  # noqa: RUF003
        ("Srvr= s ;Ref=r;", "Srvr"),
        # SERVER только с Srvr.  # noqa: RUF003
        ('Srvr="only";', "Srvr"),
        # SERVER только с Ref.  # noqa: RUF003
        ('Ref="only";', "Ref"),
        # Обычный случай без сюрпризов — тождество обязано держаться и здесь.
        ('Srvr="s";Ref="r";', "Srvr"),
        # Имя в нижнем регистре — сравнение регистронезависимое.
        ('srvr="s";Ref="r";', "srvr"),
        # Пустое значение в кавычках.
        ('Pwd="";Usr="admin";', "Pwd"),
        # Пустое значение без кавычек.
        ("Ref=;Srvr=s;", "Ref"),
        # Фрагмент без «=» не мешает найти соседний.
        ("Srvr=s;GARBAGE;Ref=r;", "Ref"),
        # Круг правок 3: пробел после «;» — обычное форматирование.  # noqa: RUF003
        ('Srvr="s"; Ref="r";', "Ref"),
    ],
)
def test_untouched_field_round_trips_identically(connect: str, name: str) -> None:
    """`raw_fragment_value` → `replace_fragment` с тем же значением — тождество.

    Именно отсутствие этой проверки (табличный тест `replace_fragment` в задаче 9
    проверял функцию в отрыве от того, как заполняется поле) спрятало три
    критических дефекта, найденных ревью. Пробел вокруг «=» в имени фрагмента
    (`Srvr ="s"`) сюда не входит — круг правок 2 отменил обрезку имени, и такой
    фрагмент больше не находится по имени вовсе (см.
    `test_raw_fragment_value_is_none_for_a_name_with_surrounding_whitespace`),
    что и есть желаемое поведение, не «тождество».
    """  # noqa: RUF002
    raw = raw_fragment_value(connect, name)
    assert raw is not None
    assert replace_fragment(connect, name, raw) == connect


def test_raw_fragment_value_is_none_for_a_fragment_that_is_not_there() -> None:
    assert raw_fragment_value('File="D:\\b";', "Srvr") is None


def test_raw_fragment_value_is_none_for_a_name_with_surrounding_whitespace() -> None:
    """Круг правок 2, решение заказчика: имя фрагмента больше не обрезается.

    `Srvr ="s";` — фрагмент с именем `"Srvr "` (пробел внутри имени), а не
    `"Srvr"`; запрос по каноническому имени `"Srvr"` его не находит. Это
    осознанное поведение (см. `test_parse_connect_does_not_trim_fragment_name`),
    не дефект.
    """  # noqa: RUF002
    assert raw_fragment_value('Srvr ="s";Ref="r";', "Srvr") is None


def test_raw_fragment_value_finds_the_fragment_that_swallowed_the_tail() -> None:
    """Непарная кавычка склеивает хвост строки в один фрагмент — не теряет его.

    Круг правок 2, item 1 (безусловный сброс хвоста): `Srvr` находится со
    значением, включающим весь захваченный текст (в т.ч. `;Ref="r";` дословно).
    `Ref` при этом отдельно не выделяется — его «=» не первый в захваченном
    чанке, а `_raw_fragment_of` ищет только первый.
    """  # noqa: RUF002
    connect = 'Srvr=s";Ref="r";'
    assert raw_fragment_value(connect, "Srvr") is not None
    assert raw_fragment_value(connect, "Ref") is None


def test_parse_connect_does_not_trim_fragment_name() -> None:
    """Круг правок 2. Ссылка на факт 6 в прежней версии этой правки была ложной:

    факт 6 — про ключ секции `Connect` (INI-подобная строка `.v8i`, парсится
    в `config/v8i.py`, который тоже не обрезает — `partition("=")` без
    `.strip()`), а не про фрагменты внутри значения `Connect`, и его вывод —
    «разделять по первому `=` без трима имени ключа». Терпит ли платформа
    пробел вокруг «=» внутри самой строки соединения, нигде не задокументировано.
    Не обрезаем: по аналогии с фактом 6, секция с таким пробелом уже испорчена
    (платформа не распознает порченный ключ и добьёт секцию при перезаписи) —
    показать её рабочей SERVER-записью значило бы спрятать порчу, а не починить.
    """  # noqa: RUF002
    fragments = parse_connect('Srvr ="s";')
    assert fragments == [ConnectFragment(name="Srvr ", value="s")]
    assert find_fragment(fragments, "Srvr") is None
    assert classify_connect('Srvr ="s";') is ConnectKind.UNKNOWN


def test_parse_connect_unquotes_value_with_space_after_equals() -> None:
    """Пробел между «=» и кавычкой не мешает распознать кавычки как границы.

    [Д], не [Ф]: терпимость к такому пробелу — предположение, а не факт
    платформы, но отменить её нельзя, не сломав уже проверенный контракт
    `replace_fragment` (`test_replace_fragment_keeps_everything_else`, случай
    `'Srvr = "s" ;Ref="r";'` из задачи 9) — именно эта терпимость находит
    границы кавычек, которые `replace_fragment` потом заменяет.
    """  # noqa: RUF002
    fragments = parse_connect('Srvr= "s" ;Ref="r";')
    assert fragments[0] == ConnectFragment(name="Srvr", value="s")


def test_parse_connect_keeps_whitespace_in_unquoted_value_as_is() -> None:
    """Пробел ВНУТРИ куска (не на его границе) не обрезается — то же решение,

    что и для имени (круг правок 2): неизвестно, различает ли платформа
    значение с пробелами и без. Пробел здесь только ведущий (после «=») —
    хвостовой (перед «;») обрезается вместе со всем куском целиком (круг
    правок 3, `test_parse_connect_strips_the_whole_chunk_not_only_the_name`):
    он стоит на границе куска, а границы куска — то самое, что обрезалось
    и до задачи 9.
    """  # noqa: RUF002
    fragments = parse_connect("Srvr= s ;Ref=r;")
    assert fragments[0].value == " s"


def test_parse_connect_strips_the_whole_chunk_not_only_the_name() -> None:
    """Круг правок 3: до задачи 9 обрезался ВЕСЬ кусок целиком (`chunk.strip()`

    перед разбором по первому «=»), а не имя или значение по отдельности.
    Круг правок 1 заменил это на обрезку одного имени (неверно — испортило
    значение регистра как «есть-ли-у-платформы-факт»), круг правок 2 —
    на отсутствие обрезки вовсе (тоже неверно, в другую сторону: сломал
    самую обычную форму `"; Ref="`). Обрезка всего куска убирает пробел
    ПЕРЕД именем (после предыдущего «;») и ПОСЛЕ значения (перед следующим
    «;»), не трогая пробелы ВНУТРИ куска — вокруг «=» — ровно то поведение,
    которое было до задачи 9 и которое не давало опровергнуть решение
    заказчика «не обрезать имя вокруг =» (задача решается на разных уровнях:
    границы куска — это форматирование текста, а не части самого фрагмента).
    """  # noqa: RUF002
    fragments = parse_connect(' Srvr ="s" ;')
    assert fragments == [ConnectFragment(name="Srvr ", value="s")]
    assert find_fragment(fragments, "Srvr") is None


def test_parse_connect_finds_fragment_after_semicolon_space() -> None:
    """Круг правок 3: `"; Ref="` — обычное форматирование, не краевой случай.

    Именно отсутствие этой формы в табличных наборах спрятало дефект круга
    правок 2 (обрезка куска подменена обрезкой одного лишь имени, а затем —
    полным отказом от обрезки): `' Ref'` (с пробелом) не находился по имени
    `'Ref'`, панель теряла фрагмент без пометки, `classify_connect` не узнавал
    вид записи.
    """  # noqa: RUF002
    fragments = parse_connect('Srvr="s"; Ref="r";')
    assert [fragment.name for fragment in fragments] == ["Srvr", "Ref"]


@pytest.mark.parametrize(
    ("connect", "expected_kind"),
    [
        ('Srvr="s"; Ref="r";', ConnectKind.SERVER),
        (' File="D:\\b";', ConnectKind.FILE),
        ('Usr="a"; ws="http://x/y";', ConnectKind.WEB),
    ],
)
def test_classify_connect_recognizes_kind_with_semicolon_or_leading_space(
    connect: str, expected_kind: ConnectKind
) -> None:
    """Круг правок 3: ревьюер измерил 16 из 32 сгенерированных строк изменёнными.

    Веб-база с этим дефектом классифицировалась бы `UNKNOWN` и запускалась бы
    процессом вместо браузера — расхождение меняло маршрут запуска, не только
    отображение.
    """  # noqa: RUF002
    assert classify_connect(connect) is expected_kind


@pytest.mark.parametrize(
    ("connect", "expected_names"),
    [
        # Непарная кавычка сразу — Srvr захватывает весь хвост.
        ('Srvr=s";Ref="r";', ["Srvr"]),
        # Первый фрагмент разобран нормально, второй захватывает хвост целиком —
        # его имя (Srvr) не теряется, теряется только корректность его значения.  # noqa: RUF003
        ('File="a";Srvr=x";Ref=y;', ["File", "Srvr"]),
        # Ревьюер: имя секретного ключа в захваченном хвосте не пропадает —
        # это единственная причина, по которой build_arguments мог его найти.  # noqa: RUF003
        ('File="D:\\b";Pwd=p";', ["File", "Pwd"]),
    ],
)
def test_parse_connect_keeps_fragment_names_after_an_unpaired_quote(
    connect: str, expected_names: list[str]
) -> None:
    """Круг правок 2, item 1: хвост после непарной кавычки не пропадает целиком.

    Сентинел «;» в конце расщепителя стоял под тем же условием `not in_quotes`,
    что и обычный разделитель, — при непарной кавычке в исходнике он никогда
    не срабатывал, и хвост терялся целиком, включая ИМЕНА фрагментов, а не
    только их значения. Последствие — `build_arguments` мог пропустить
    секретный ключ (`Pwd`) в хвосте и передать пароль в argv, читаемый любым
    процессом пользователя (скил platform-launch, «Пароль в командной строке —
    неустранимая утечка»).
    """  # noqa: RUF002
    names = [fragment.name for fragment in parse_connect(connect)]
    assert names == expected_names
