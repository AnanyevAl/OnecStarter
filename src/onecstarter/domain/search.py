"""Поиск со звёздочкой (T-26, спека 2026-09-29-search-wildcard-design.md, §2).

`*` — «любые символы», всё остальное ищется буквально: в именах баз обычны
`.`, `(`, `+`, и регулярные выражения давали бы ошибки разбора и ложные
совпадения. Модуль `re` не используется намеренно.
"""  # noqa: RUF002


def matches_pattern(text: str, query: str) -> bool:
    """Совпадает ли `text` с запросом: части между `*` ищутся по порядку, без учёта регистра.

    Пустой запрос и запрос из одних `*` совпадают со всем. Совпадения частей
    не перекрываются; шаблон не привязан к началу и концу текста. Запрос без
    `*` — ровно прежняя проверка подстроки (`casefold`, [Ф] T-05.3).
    """  # noqa: RUF002
    parts = [part for part in query.strip().casefold().split("*") if part]
    folded = text.casefold()
    position = 0
    for part in parts:
        found = folded.find(part, position)
        if found < 0:
            return False
        position = found + len(part)
    return True
