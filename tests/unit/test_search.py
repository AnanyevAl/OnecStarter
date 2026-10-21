"""Поиск со звёздочкой (T-26, спека 2026-09-29-search-wildcard-design.md, §2)."""  # noqa: RUF002

import pytest

from onecstarter.domain.search import matches_pattern


@pytest.mark.parametrize(
    ("text", "query", "expected"),
    [
        # без звёздочки — нынешняя подстрока без учёта регистра
        ("Демо Бухгалтерия", "бух", True),  # noqa: RUF001
        ("Демо Бухгалтерия", "БУХ", True),
        ("Демо Бухгалтерия", "розн", False),
        ("Ёлка", "елка", False),  # «ё» не приравнивается к «е»  # noqa: RUF003
        # части по порядку
        ("amad Бухгалтерия UU", "amad*UU", True),
        ("Копия amad-2 UU test", "amad*UU", True),
        ("UU amad", "amad*UU", False),  # обратный порядок
        # звёздочка по краям ничего не меняет
        ("amad Бухгалтерия UU", "*amad*UU*", True),
        # одинокие звёздочки, пустой и пробельный запрос — совпадает всё
        ("что угодно", "*", True),
        ("что угодно", "**", True),
        ("что угодно", "", True),
        ("что угодно", "   ", True),
        # спецсимволы ищутся буквально
        ("Бухгалтерия 3.0", "3.0", True),
        ("Бухгалтерия 3x0", "3.0", False),
        ("УТ (копия)", "УТ (", True),  # noqa: RUF001
        ("a+b [c] ? \\d", "+b [c] ? \\", True),
        # части не перекрываются
        ("aaa", "aa*aa", False),
        ("aaaa", "aa*aa", True),
        # пробелы внутри частей значимы
        ("amad x UU", "amad * UU", True),
        ("amadUU", "amad * UU", False),
        # кириллица с разным регистром по частям  # noqa: RUF003
        ("ДЕМО розница", "демо*РОЗ", True),  # noqa: RUF001
    ],
)
def test_matches_pattern(text: str, query: str, expected: bool) -> None:
    assert matches_pattern(text, query) is expected
