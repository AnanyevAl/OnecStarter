"""Секреты: список секретных ключей и вырезание учётных данных из адреса."""

import pytest

from onecstarter.security.secrets import is_secret_key, strip_url_credentials


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("", ""),
        ("http://srv/base", "http://srv/base"),
        ("https://srv:8443/base", "https://srv:8443/base"),
        ("http://user:pass@srv/base", "http://srv/base"),
        ("http://user:pass@srv:8080/base", "http://srv:8080/base"),
        ("http://user@srv/base", "http://srv/base"),
        # «@» вне authority: границы фрагментов неясны, показывать нельзя.
        # urlsplit("user:pass@srv/base") принимает «user» за схему, и наивная
        # проверка «есть ли @ в netloc» пропустила бы пароль на экран.
        ("user:pass@srv/base", None),
        # Незакодированный «/» в пароле: netloc обрывается на нём, и хвост
        # «ss@srv» уезжает в path. Такой URL платформа не приняла бы, но
        # показать его дословно значит показать пароль.  # noqa: RUF003
        ("http://user:pa/ss@srv/base", None),
        # Плата за fail-closed: законный «@» в пути тоже скрывается.
        ("http://srv/base@2", None),
        # Юникодный двойник «собаки»: U+FF20 FULLWIDTH COMMERCIAL AT.
        # Ранний выход по буквальному «@» пропускал бы его на экран —  # noqa: RUF003
        # `urlsplit` сам NFKC-нормализует authority и ловит такие символы.
        ("http://user:pass＠srv/base", None),  # noqa: RUF001
        # Тот же класс: U+FE6B SMALL COMMERCIAL AT.
        ("http://user:pass﹫srv/base", None),
        # Двойник вне authority — в пути. urlsplit его не ловит: собственная  # noqa: RUF003
        # NFKC-проверка urlsplit смотрит только на netloc. Без нормализации
        # всей строки внутри самой функции этот случай прошёл бы насквозь
        # молча — как и его ASCII-аналог "http://srv/base@2", который тоже  # noqa: RUF003
        # скрывается (§ платы за fail-closed).
        ("http://srv/base＠2", None),  # noqa: RUF001
        # IPv6 в скобках: hostname отдаёт голый "::1", скобки нужно вернуть
        # явно — иначе пересобранный адрес `urlsplit` обратно не разбирает.
        ("http://user:pass@[::1]:8080/base", "http://[::1]:8080/base"),
        ("http://user:pass@[::1]/base", "http://[::1]/base"),
        # Секрет в query — "@" в адресе нет вовсе, но скрывается весь адрес,
        # а не только параметр (та же политика, что у redact_connect).  # noqa: RUF003
        ("http://srv/base?usr=a&pwd=secret", None),
        # Query без секретных имён проходит насквозь без изменений.
        ("http://srv/base?foo=bar", "http://srv/base?foo=bar"),
    ],
)
def test_strip_url_credentials(url: str, expected: str | None) -> None:
    assert strip_url_credentials(url) == expected


def test_ppasswd_is_a_secret() -> None:
    """Зашифрованный пароль прокси — ключ секции, а не фрагмент Connect.

    Суффиксное правило endswith("pwd") его не ловит: «ppasswd» кончается
    на «sswd». Обязательство 2 ревью плана 3 — становится достижимым
    вместе с показом свойств записи (задача 8).
    """  # noqa: RUF002
    assert is_secret_key("PPasswd")
    assert is_secret_key("ppasswd")
    assert not is_secret_key("PUser")
