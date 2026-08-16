"""Арифметика OrderInList при перестановке записи внутри группы.

**[Ф]** скил v8i-format, факт 5: `OrderInList` — дробное число, значим только
относительный порядок; пересчёт всего файла в плотную нумерацию запрещён —
он переписывает файл и ломает round-trip.

Отсюда правило: обычно меняется одно значение — среднее между новыми соседями.
Но «среднее» ломается на равных соседях, а они у нас норма, а не край:
`edit._apply_add` пишет каждой новой записи `OrderInList=-1`. Поэтому при
исчерпании зазора пересчитывается **одна группа** — [Р] решение спеки 4b, §4.

**[Р] решение по итогам ревью (круг правок 1, задача 15):** «зазор
исчерпан» проверяется по значению, которое реально ляжет в файл
(`format_order`), а не по промежуточному `float` — иначе соседи вида
`60.6814814814813`/`60.6814814814814` (реальные значения платформы, факт 5)
после округления `%.15g` могут дать одинаковый текст, хотя raw-float
сравнение считало зазор найденным. Пересчёт всей группы включается только
когда **все** её значения совпадают буквально (решение заказчика) — не когда
совпадает лишь старое значение переставляемой записи с одним соседом
(прежняя `_edge_tie` пересчитывала лишнее на настоящих данных заказчика,
переписывая все шесть записей ради одной).

**[Р] решение по итогам ревью (круг правок 2, задача 15):** записываемое
значение обязано не только отличаться от соседа, но и лежать в верную
сторону от него (порядок, не только неравенство), и не переключаться
на научную нотацию — обе проверки в `_between`. Четырнадцать обычных
перетаскиваний записи под первую в одной группе (нормальная работа,
не синтетика) сжимают зазор до `2⁻¹⁴` и без этой проверки дали бы
`OrderInList=6.103515625e-05`.
"""  # noqa: RUF002

from collections.abc import Sequence

__all__ = ["format_order", "reorder_values", "sort_key"]


def sort_key(order: float | None) -> tuple[bool, float]:
    """Ключ сортировки, тот же, что у `catalog.items_from_document`.

    Две копии этого правила разъехались бы, и позиция, посчитанная здесь,
    не совпала бы с позицией на экране.
    """  # noqa: RUF002
    return (order is None, order or 0.0)


def reorder_values(
    orders: Sequence[float | None], moved: int, after: int | None
) -> dict[int, float]:
    """Новые значения `OrderInList`: индекс → значение. Пусто — двигать нечего.

    `orders` — значения всех детей одного родителя **в порядке показа**
    (тот же порядок, что строит `sort_key`: вызывающий обязан отсортировать
    соседей им же, иначе индексы этой функции разъедутся с тем, что видит
    пользователь). `after` — индекс в `orders`, `after is None` — поставить
    в начало.
    """  # noqa: RUF002
    if after == moved:
        return {}
    rest = [index for index in range(len(orders)) if index != moved]
    position = 0 if after is None else rest.index(after) + 1
    target = [*rest[:position], moved, *rest[position:]]
    if target == list(range(len(orders))):
        return {}
    if any(value is None for value in orders):
        # У кого-то нет ключа вовсе — интерполировать не от чего.  # noqa: RUF003
        return _renumber(target)
    if _all_equal(orders):
        # Группа вырождена целиком — зазора нет нигде, а не только в точке  # noqa: RUF003
        # вставки. [Р] решение заказчика (круг правок 1): условие сужено  # noqa: RUF003
        # с «старое значение двигаемой записи совпадает с единственным  # noqa: RUF003
        # соседом» — то ловило и группы, где зазор есть в других местах,
        # и переписывало лишние записи (см. docstring модуля).
        return _renumber(target)
    previous = orders[target[position - 1]] if position > 0 else None
    following = orders[target[position + 1]] if position + 1 < len(target) else None
    value = _between(previous, following)
    return {moved: value} if value is not None else _renumber(target)


def format_order(value: float) -> str:
    """Записать значение так, как пишет платформа: целое — без дробной части.

    **[Д] не проверено:** для очень маленьких (`< 1e-4` по модулю) и очень
    больших значений `%g` переключается на научную нотацию (`1e-07`,
    `1e+308`). Читает ли платформа такую запись в `OrderInList` вообще,
    экспериментально не проверялось, и метка остаётся честной — но
    **утверждение о том, что наша арифметика такие значения не порождает,
    было ложным** (найдено ревью, круг правок 2, задача 15): четырнадцать
    обычных перетаскиваний записи под первую в одной группе сжимают зазор
    до `2⁻¹⁴`, и `format_order` на этом значении отдаёт `"6.103515625e-05"`.
    Это не синтетика — рядовая работа внутри одной группы. Сама функция
    формат не ограничивает (у неё нет контекста «пишем в файл» или «просто
    печатаем число»); границу держит `_between` — см. её докстринг.
    """  # noqa: RUF002
    return f"{value:.15g}"


def _renumber(target: Sequence[int]) -> dict[int, float]:
    return {index: float(rank) for rank, index in enumerate(target)}


def _all_equal(values: Sequence[float | None]) -> bool:
    return len(set(values)) == 1


def _between(previous: float | None, following: float | None) -> float | None:
    """Значение строго между соседями — по тексту, который реально попадёт
    в файл, а не по промежуточному `float`. `None` — зазора нет, нужен
    пересчёт группы.

    **[Ф] находка ревью (круг правок 1, задача 15):** прежняя проверка
    сравнивала `previous < middle < following` по сырому `float`, а
    записывается `format_order(middle)` (`%.15g`, 15 значащих цифр).
    У соседей вида `60.6814814814813`/`60.6814814814814` среднее нуждается
    в 16-й значащей цифре — округление до 15 может дать текст, совпадающий
    с ОДНИМ ИЗ соседей: `middle = 60.68148148148135`,
    `format_order(middle) == "60.6814814814813" == format_order(previous)`.
    Raw-float сравнение считало бы зазор найденным, хотя после записи и
    перечитывания это уже не так — запись попадает в ничью с соседом,
    и порядок между ними решает файловый, а не запрошенный. Тот же принцип
    на краю (только один сосед): значение обязано быть строго БОЛЬШЕ/МЕНЬШЕ
    соседа ПОСЛЕ форматирования (не просто «отличаться» — находка ревью,
    круг правок 2: `_between(1_000_000_000_000_002.0, None)` раньше давал
    `1_000_000_000_000_003.0`, который `format_order` пишет как `"1e+15"`,
    а читается обратно как `1e15 == 1_000_000_000_000_000.0` — МЕНЬШЕ
    соседа, хотя проверка «отличается» это пропускала).

    **[Р] решение по итогам ревью (круг правок 2, задача 15):** научная
    нотация в записываемом тексте — сама по себе признак «зазора не
    осталось», при любом положении (интервал или край). Мы не знаем,
    читает ли платформа `OrderInList` в научной нотации ([Д],
    `format_order`), и вместо того чтобы гадать, уходим в форму, в которой
    сомнений нет — тот же приём, что уже применён к кавычкам в задаче 9:
    не угадывать поведение платформы, а не создавать ситуацию, где догадка
    понадобилась бы. Пересчёт группы всегда даёт маленькие целые
    (`_renumber`) — научная нотация из них не получается никогда.

    `None` у соседа здесь означает «соседа нет» (край списка), а не
    «нет ключа»: случай отсутствующего ключа отсечён вызывающим.
    """  # noqa: RUF002
    if previous is None and following is None:
        return 0.0
    if previous is None:
        neighbor = following or 0.0
        candidate = neighbor - 1.0
        return candidate if _fits_before(candidate, neighbor) else None
    if following is None:
        candidate = previous + 1.0
        return candidate if _fits_after(candidate, previous) else None
    middle = (previous + following) / 2
    return middle if _fits_between(middle, previous, following) else None


def _fits_before(candidate: float, neighbor: float) -> bool:
    """`candidate` пишется без научной нотации и реально меньше `neighbor`."""
    text = format_order(candidate)
    return "e" not in text and float(text) < neighbor


def _fits_after(candidate: float, neighbor: float) -> bool:
    """`candidate` пишется без научной нотации и реально больше `neighbor`."""
    text = format_order(candidate)
    return "e" not in text and float(text) > neighbor


def _fits_between(candidate: float, previous: float, following: float) -> bool:
    """`candidate` пишется без научной нотации и реально лежит между соседями."""
    text = format_order(candidate)
    if "e" in text:
        return False
    written = float(text)
    return previous < written < following
