"""Секреты: список секретных ключей и вырезание учётных данных из адреса."""

import pytest

from onecstarter.security.secrets import (
    HIDDEN_ARGUMENTS,
    is_secret_key,
    redact_arguments,
    strip_url_credentials,
)


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


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            'ENTERPRISE /IBName"x" /AppAutoCheckVersion',
            'ENTERPRISE /IBName"x" /AppAutoCheckVersion',
        ),
        ('ENTERPRISE /IBName"x" /N"u" /P"p@ss" /AppAutoCheckVersion',
         'ENTERPRISE /IBName"x" /N"u" /P*** /AppAutoCheckVersion'),
        # Кавычка внутри пароля удвоена формой quote_launch_value — закрывающая
        # граница остаётся однозначной. Удвоение принято [Д] по аналогии
        # с /IBConnectionString (T-05.1): T-05.15 его не измерял — кавычки  # noqa: RUF003
        # в значении не было.
        ('/IBName"x" /N"u" /P"a""b" /AppAutoCheckMode', '/IBName"x" /N"u" /P*** /AppAutoCheckMode'),
        # Форма без кавычек — справочник (B2 T-05.15), измерением не
        # подтверждена и не опровергнута: [Д]. Токенизатор режет и её.
        ("/IBName\"x\" /Nu /Pp@ss /AppAutoCheckMode", '/IBName"x" /Nu /P*** /AppAutoCheckMode'),
        # Непарная кавычка — границы значений недостоверны, показывать нельзя.
        ('/IBName"x" /P"p@ss /AppAutoCheckMode', HIDDEN_ARGUMENTS),
        ("", ""),
        # Находка ревью задачи 2 (06.09.2026): мнимый /P внутри значения
        # /IBName сдвигал границы регулярки и пропускал настоящий секрет.
        # Токенизатор не путает их — /IBName"a/P" целиком один токен.
        (
            '/IBName"a/P" /P"secret" /N"u"',
            '/IBName"a/P" /P*** /N"u"',
        ),
        # /P — часть значения другого ключа, а не отдельный токен: не трогаем.  # noqa: RUF003
        ('/IBName"/P" /N"u"', '/IBName"/P" /N"u"'),
        # Пустое значение /P — токен всё равно начинается с /P и режется.  # noqa: RUF003
        ('/P"" /N"u"', '/P*** /N"u"'),
        # Два /P — оба токена заменены независимо.  # noqa: RUF003
        ('/P"x" /P"y"', '/P*** /P***'),
        # /PP — тоже начинается с /P: переизбыточная редакция безопасна,  # noqa: RUF003
        # других ключей на /P* в режиме ENTERPRISE нет ([Д]).
        ('/PP"x"', "/P***"),
    ],
)
def test_redact_arguments(arguments: str, expected: str) -> None:
    assert redact_arguments(arguments) == expected


def test_redact_arguments_never_leaves_the_value() -> None:
    """Сторож fail-closed: при любом исходе значения /P в выводе нет.

    Две последние пробы — регрессия, а не дубли предыдущих четырёх:
    - `/IBName"a/P" /P"p@ss" /N"u"` — мнимый `/P` в чужом значении перед
      настоящим (форма находки ревью задачи 2, 06.09.2026); ни одна
      из первых четырёх проб её не задевает, там `/P` в тексте только один;
    - `/P"secret p@ss"` — пробел внутри значения `/P`. Если токенизатор
      подменить на `arguments.split()` (не различает кавычки), эта проба
      режется на `/P"secret` и `p@ss"`, второй осколок не начинается
      с `/P` и остаётся в выводе как есть — секрет утекает.
    """  # noqa: RUF002
    arguments_without_the_secret = (
        '/P"p@ss"',
        "/Pp@ss",
        '/P"p@ss',
        '/IBName"a" /P"p@ss" /N"u"',
        '/IBName"a/P" /P"p@ss" /N"u"',
        '/P"secret p@ss"',
    )
    for arguments in arguments_without_the_secret:
        assert "p@ss" not in redact_arguments(arguments)
