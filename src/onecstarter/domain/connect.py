"""Read-only разбор строки соединения Connect и точечная правка фрагментов.

Строка соединения — не INI: фрагменты Имя=Значение через ";", значение
может быть в двойных кавычках, ";" внутри кавычек — часть значения.
Правило «"" внутри кавычек = литеральная кавычка» — допущение по аналогии
с документированным правилом /IBConnectionString; экранирование кавычек
в Connect экспериментально не проверено (скил v8i-format, «Непроверенное»).
Исходная строка никогда не пересобирается из фрагментов целиком — round-trip
всего документа держит слой config; здесь же живёт точечная правка одного
фрагмента (`replace_fragment`), которая по той же причине не пересобирает,
а вырезает и вставляет заново.

**Один разбор на модуль.** `parse_connect` (дружелюбные имя+значение, кавычки
сняты) и границы фрагментов для точечной правки строятся одним и тем же
проходом `_iter_raw_fragments` — до правки это были два независимых разбора,
и они расходились на реальных данных: `parse_connect` не обрезал пробелы
вокруг имени ключа, второй разбор обрезал. Диалог заполнял поле первым
разбором, писал — вторым; на строке с пробелом перед «=» это стирало значение
на нетронутом поле. Круг правок 1 (ревью задачи 9) свёл оба разбора к одному
прохода ради инварианта «разобрал → положил сырое значение в поле →
записал == тождество».

**Имя фрагмента не обрезается вокруг «=» (круг правок 2).** Круг правок 1
обосновал обрезку пробелов вокруг «=» ссылкой на факт 6 скила v8i-format —
ложной: факт 6 про ключ секции `Connect` в самом файле `.v8i`, а не про
фрагменты внутри его значения, и вывод факта 6 прямо противоположный
обрезке («разделять по первому = без трима имени ключа»). Терпит ли
платформа пробел вокруг «=» внутри строки соединения — не задокументировано
нигде. По той же логике, что и в факте 6: секция с таким пробелом уже
испорчена (платформа не распознает порченный ключ и добьёт секцию при
перезаписи), и обрезка спрятала бы эту порчу от пользователя, а не починила
её. Фрагмент с пробелом вокруг имени (`Srvr ="s"`) просто не находится по
каноническому имени — `raw_fragment_value` вернёт `None`, `classify_connect`
не узнает вид записи, и размещение станет нередактируемым тем же путём,
что и любой другой ненайденный фрагмент (C3).

**Хвост после непарной кавычки не теряется (круг правок 2, item 1).**
`_iter_raw_fragments` сбрасывает остаток строки безусловно, даже если
кавычка осталась непарной, — иначе имена фрагментов в хвосте (в т.ч.
секретных, `Pwd`) пропадали бы из разбора целиком, а не просто теряли
корректное значение. `build_arguments` (`domain/launch.py`) вдобавок
проверяет чётность числа кавычек напрямую, не полагаясь на этот разбор:
защита от утечки пароля в argv не должна зависеть от качества парсинга.

**Обрезается весь кусок целиком, а не имя или значение отдельно (круг
правок 3).** До задачи 9 `_split_fragments` обрезал каждый кусок целиком
(`raw.strip()`) перед разбором по первому «=» — это убирало пробел ПЕРЕД
именем (после предыдущего «;», обычное форматирование: `Srvr="s"; Ref="r";`)
и ПОСЛЕ значения (перед следующим «;»), не трогая пробелы ВНУТРИ куска
(вокруг самого «=»). Круг правок 1 подменил это обрезкой одного имени
(`chunk[:separator].strip()`) — из-за чего вывод про факт 6 выше и оказался
неверно применён. Круг правок 2, откатывая ту ошибку, перепутал «не обрезать
имя вокруг =» с «не обрезать кусок вовсе» и убрал обрезку полностью —
фрагмент после `"; "` (пробел за точкой с запятой) стал находиться под
именем с пробелом (`' Ref'` вместо `'Ref'`), и панель, `classify_connect`
и точечная правка молча теряли или не узнавали самую обычную запись.
Круг правок 3 вернул обрезку куска целиком, оставив нетронутым решение
«не обрезать вокруг =» — оба решения независимы и не противоречат друг
другу: одно про границы КУСКА (форматирование текста), другое про то,
что ВНУТРИ куска (сам фрагмент).

**[Д] Терпимость к пробелу между «=» и открывающей кавычкой.**
`_raw_fragment_of` ищет кавычки в сыром значении, а не только сразу
у «=», — единственное сохранённое допущение из трёх, что круг правок 1
привнёс в `parse_connect` (два других — обрезка значения и обрезка имени —
откачены кругами 2–3). Это предположение о синтаксисе платформы, не факт:
терпит ли платформа такой пробел — не задокументировано нигде. Отменить
его нельзя, не сломав уже проверенный (задача 9) контракт `replace_fragment`
на случае `'Srvr = "s" ;Ref="r";'` (`test_replace_fragment_keeps_everything_else`) —
именно эта терпимость находит границы кавычек, которые `replace_fragment`
потом заменяет.
"""  # noqa: RUF002

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ConnectFragment:
    name: str
    value: str


class ConnectKind(Enum):
    FILE = "file"
    SERVER = "server"
    WEB = "web"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FragmentSpan:
    name: str
    value_start: int
    value_end: int


@dataclass(frozen=True)
class _RawFragment:
    """Один фрагмент, разобранный один раз — общий источник для двух видов вывода.

    `value_start`/`value_end` — границы сырого текста значения (для кавычек:
    между ними, без самих кавычек; удвоенные кавычки внутри не разворачиваются).
    `quoted` говорит, разворачивать ли `""` → `"` для дружелюбного значения
    `parse_connect` — эта развёртка не нужна и вредна для `fragment_spans`:
    точечная правка обязана видеть и писать байты как есть.
    """

    name: str
    value_start: int
    value_end: int
    quoted: bool


def _iter_raw_fragments(connect: str) -> list[_RawFragment]:
    """Разбить строку на фрагменты один раз — источник и для значений, и для границ.

    Разделитель — ";" вне кавычек; кавычка внутри значения переключает режим
    посимвольно, без понимания экранирования (оно [Д], не [Ф] — см. докстринг
    модуля). Хвост после последнего разделителя сбрасывается безусловно —
    в т.ч. когда кавычка в исходнике осталась непарной и `in_quotes` к концу
    строки не вернулся в `False`.

    **Круг правок 2 (ревью задачи 9), item 1.** Раньше хвост обрабатывался
    добавленным в конец сентинелом ";" под тем же условием `not in_quotes`,
    что и обычный разделитель, — при непарной кавычке сентинел никогда
    не срабатывал, и хвост терялся целиком, включая ИМЕНА фрагментов, а не
    только их значения: `parse_connect('File="D:\\b";Pwd=p";')` находил
    только `File`, `Pwd` пропадал бесследно. Последствие — `domain/launch.py`,
    `build_arguments`: сканирование имён фрагментов на секреты переставало
    находить `Pwd` в хвосте, и пароль ушёл бы в argv, читаемый любым процессом
    пользователя (скил platform-launch, «Пароль в командной строке —
    неустранимая утечка»). Безусловный сброс хвоста — тот же приём, что был
    в `_split_fragments` до сведения разборов к одному (задача 9, круг правок 1);
    защита от утечки в `build_arguments` теперь стоит и здесь, и отдельно —
    паритетным стражем, не зависящим от качества этого разбора (см. докстринг
    `build_arguments`).
    """  # noqa: RUF002
    fragments: list[_RawFragment] = []
    start = 0
    in_quotes = False
    for position, char in enumerate(connect):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ";" and not in_quotes:
            fragment = _raw_fragment_of(connect, start, position)
            if fragment is not None:
                fragments.append(fragment)
            start = position + 1
    tail = _raw_fragment_of(connect, start, len(connect))
    if tail is not None:
        fragments.append(tail)
    return fragments


def _raw_fragment_of(connect: str, start: int, end: int) -> _RawFragment | None:
    # Круг правок 3: обрезается весь кусок целиком (лидирующий и хвостовой  # noqa: RUF003
    # пробел на его границах — форматирование вокруг ";"), а не имя  # noqa: RUF003
    # или значение по отдельности. Круги 1 и 2 ошиблись каждый в свою
    # сторону; подробности и решение заказчика — в докстринге модуля.
    raw = connect[start:end]
    stripped = raw.strip()
    if not stripped:
        return None
    leading = len(raw) - len(raw.lstrip())
    chunk_start = start + leading
    chunk_end = chunk_start + len(stripped)
    separator = stripped.find("=")
    if separator < 0:
        return None
    name = stripped[:separator]
    value_start = chunk_start + separator + 1
    value = connect[value_start:chunk_end]
    inner = value.strip()
    if len(inner) >= 2 and inner.startswith('"') and inner.endswith('"'):
        # [Д] — терпимость к пробелу между "=" и открывающей кавычкой,
        # см. докстринг модуля. `rindex` берёт внешнюю закрывающую кавычку
        # куска, поэтому внутренние удвоенные кавычки (экранирование)
        # остаются частью значения, не обрезаются по ним.
        open_at = value.index('"')
        close_at = value.rindex('"')
        return _RawFragment(name, value_start + open_at + 1, value_start + close_at, quoted=True)
    return _RawFragment(name, value_start, chunk_end, quoted=False)


def parse_connect(connect: str) -> list[ConnectFragment]:
    """Дружелюбный разбор: кавычки сняты, `""` развёрнуто в `"`.

    Значение без кавычек НЕ обрезается по краям (круг правок 2, то же решение,
    что и для имени): неизвестно, различает ли платформа значение с пробелами
    и без — обрезка была бы догадкой того же класса риска, что и обрезка
    имени. Имя фрагмента тоже не обрезается — см. докстринг модуля.
    """  # noqa: RUF002
    fragments: list[ConnectFragment] = []
    for raw in _iter_raw_fragments(connect):
        text = connect[raw.value_start : raw.value_end]
        value = text.replace('""', '"') if raw.quoted else text
        fragments.append(ConnectFragment(name=raw.name, value=value))
    return fragments


def find_fragment(fragments: Sequence[ConnectFragment], name: str) -> str | None:
    wanted = name.casefold()
    for fragment in fragments:
        if fragment.name.casefold() == wanted:
            return fragment.value
    return None


# Фрагменты размещения по виду записи — единственный источник этого знания:
# по нему и классифицируется строка (classify_connect), и проверяется пустота
# размещения (services.model.validate_connect). Порядок объявления — приоритет
# классификации: File раньше ws раньше Srvr/Ref. Диалог (_PLACEMENT_SPEC
# в ui/dialogs/infobase.py) перечисляет те же фрагменты с метками полей  # noqa: RUF003
# и каноническим регистром записи.
PLACEMENT_FRAGMENTS: Mapping[ConnectKind, tuple[str, ...]] = {
    ConnectKind.FILE: ("file",),
    ConnectKind.WEB: ("ws",),
    ConnectKind.SERVER: ("srvr", "ref"),
    ConnectKind.UNKNOWN: (),
}


def classify_connect(connect: str) -> ConnectKind:
    names = {fragment.name.casefold() for fragment in parse_connect(connect)}
    for kind, fragments in PLACEMENT_FRAGMENTS.items():
        if any(fragment in names for fragment in fragments):
            return kind
    return ConnectKind.UNKNOWN


def fragment_spans(connect: str) -> list[FragmentSpan]:
    """Границы значений фрагментов в исходном тексте, байт в байт.

    Нужны для точечной правки: пересборка строки из разобранных фрагментов
    потеряла бы то, чего мы не понимаем, — а строку соединения пишет
    и платформа, и человек.
    """  # noqa: RUF002
    return [
        FragmentSpan(raw.name, raw.value_start, raw.value_end)
        for raw in _iter_raw_fragments(connect)
    ]


def raw_fragment_value(connect: str, name: str) -> str | None:
    """Сырой (не разобранный) текст значения фрагмента — `None`, если фрагмента нет.

    То самое место, которое `replace_fragment` заменит: одинаковые границы —
    общий `_iter_raw_fragments`. Заполнять этим полем UI, а не значением
    `parse_connect`, — единственный способ, которым «поле → запись» тождественно
    по построению, а не по совпадению (см. докстринг модуля).
    """  # noqa: RUF002
    wanted = name.casefold()
    for raw in _iter_raw_fragments(connect):
        if raw.name.casefold() == wanted:
            return connect[raw.value_start : raw.value_end]
    return None


def replace_fragment(connect: str, name: str, value: str) -> str:
    """Заменить значение фрагмента, не тронув остальной текст.

    Сравнение имени — без учёта регистра, регистр в файле сохраняется.
    Неизвестное имя — `KeyError`: молча дописать фрагмент значило бы менять
    вид размещения там, где вызывающий просил правку значения. Вызывающий,
    которому нужна гарантия отсутствия `KeyError`, обязан сперва убедиться
    через `raw_fragment_value(connect, name) is not None`.
    """
    wanted = name.casefold()
    for span in fragment_spans(connect):
        if span.name.casefold() == wanted:
            return connect[: span.value_start] + value + connect[span.value_end :]
    raise KeyError(name)


def extra_fragment_names(connect: str, keep: Sequence[str]) -> list[str]:
    """Имена фрагментов сверх перечисленных — то, что потеряет смена вида."""
    kept = {name.casefold() for name in keep}
    return [
        fragment.name
        for fragment in parse_connect(connect)
        if fragment.name.casefold() not in kept
    ]
