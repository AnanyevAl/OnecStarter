"""Проверка строки параметров по контексту (спека v4, §4.2; [Ф] T-42 Э1, Э3, Э4)."""

import pytest

from onecstarter.domain.cli_catalog import Catalog, Client, Mode, load_catalog
from onecstarter.domain.cli_params import CheckContext, Finding, Level, Where, check, parse
from onecstarter.domain.version import parse_version
from onecstarter.services.cli_catalog import load_cli_catalog


def _catalog() -> Catalog:
    def key(name: str, **extra: object) -> dict[str, object]:
        entry: dict[str, object] = {
            "name": name, "group": "g", "modes": ["enterprise"], "summary": "к",
            "description": "о", "its": "7.3", "reliability": "doc",  # noqa: RUF001
            "versions": {"since": "8.3.18"},
        }
        entry.update(extra)
        return entry

    return load_catalog(
        {
            "group": [{"id": "g", "title": "Г", "order": 1}],
            "key": [
                key("/L", modes=["enterprise", "designer"], from_v8i=False,
                    args=[{"kind": "string", "attached": True, "required": True,
                           "label": "код языка"}]),
                key("/C", args=[{"kind": "string", "required": True, "label": "параметр запуска"}]),
                key("/P", modes=["enterprise", "designer"],
                    args=[{"kind": "secret", "attached": True}]),
                key("/IBName", managed=True, args=[{"kind": "string", "attached": True}]),
                key("/SLev", clients=["thick"],
                    args=[{"kind": "enum", "values": ["0", "1", "2"], "attached": True}]),
                key("/Debug", args=[
                    {"kind": "enum", "values": ["-tcp", "-http"]},
                    {"kind": "flag", "flag": "-attach", "requires": "-http"},
                ]),
                key("/i85", versions={"since": "8.5.1"}),
                key("/Old", versions={"since": "8.3.18", "until": "8.3.20"}),
                key("/DisableBackgroundIndexBuild", modes=["designer"]),
            ],
        }
    )


def _check(text: str, **context: object) -> list[Finding]:
    defaults: dict[str, object] = {"where": Where.ONCE, "mode": Mode.ENTERPRISE}
    defaults.update(context)
    return list(check(parse(text, _catalog()), CheckContext(**defaults)))  # type: ignore[arg-type]


def _texts(findings: list[Finding]) -> list[tuple[Level, str]]:
    return [(finding.level, finding.text) for finding in findings]


def test_clean_string_has_no_findings() -> None:
    assert _check('/Lru /C "x y" /Debug -http -attach') == []


@pytest.mark.parametrize(
    ("text", "context", "expected"),
    [
        (
            "мусор /Lru",
            {},
            (Level.ERROR, "Текст до первого ключа — не ключ: ключи начинаются с «/»"),  # noqa: RUF001
        ),
        (
            '/C "x',
            {},
            (
                Level.ERROR,
                "Незакрытая кавычка: платформа прочитает строку не так, как она написана",
            ),
        ),
        ("/Foo", {}, (Level.ERROR, "/Foo — неизвестный ключ. Строка сохранится как есть.")),
        (
            '/P"секрет"',
            {"where": Where.PERMANENT},
            (
                Level.ERROR,
                "/P: пароль в .v8i хранится открытым текстом — используйте поле «Пароль»",
            ),
        ),
        (
            '/P"секрет"',
            {"where": Where.SET},
            (
                Level.ERROR,
                "/P: пароль в строке хранится открытым текстом — используйте поле «Пароль»",
            ),
        ),
        (
            '/IBName"x"',
            {},
            (
                Level.WARNING,
                "/IBName: подключение к базе программа задаёт сама — ключ здесь не нужен",
            ),
        ),
        ("/C x", {"mode": Mode.DESIGNER}, (Level.WARNING, "/C — не для режима «Конфигуратор»")),
        (
            "/DisableBackgroundIndexBuild",
            {},
            (Level.WARNING, "/DisableBackgroundIndexBuild — не для режима «1С:Предприятие»"),  # noqa: RUF001
        ),
        (
            "/SLev2",
            {"client": Client.THIN},
            (Level.WARNING, "/SLev — не для клиента «тонкий клиент»"),
        ),
        (
            "/i85",
            {"version": parse_version("8.3.27.2214")},
            (Level.WARNING, "/i85 появился в 8.5.1, а база запускается версией 8.3.27.2214"),  # noqa: RUF001
        ),
        (
            "/Old",
            {"version": parse_version("8.3.25.1633")},
            (Level.WARNING, "/Old убран после 8.3.20, а база запускается версией 8.3.25.1633"),  # noqa: RUF001
        ),
        ("/C", {}, (Level.ERROR, "/C: не задано значение «параметр запуска»")),
        ("/Debug -attach", {}, (Level.WARNING, "/Debug: -attach действует только вместе с -http")),  # noqa: RUF001
        (
            "/C Q4 без кавычек",
            {},
            (
                Level.WARNING,
                "/C: «без кавычек» платформа отбросит молча — "
                "значение с пробелами возьмите в кавычки",  # noqa: RUF001
            ),
        ),
        ("/Lru /Len", {}, (Level.WARNING, "/L указан дважды")),
        (
            "/Len",
            {"where": Where.PERMANENT},
            (
                Level.WARNING,
                "/L из списка баз платформа не применяет — задайте его при разовом "  # noqa: RUF001
                "запуске или в строке Конфигуратора",
            ),
        ),
    ],
)
def test_finding_rows(text: str, context: dict[str, object], expected: tuple[Level, str]) -> None:
    assert expected in _texts(_check(text, **context))


def test_secret_is_allowed_once_and_its_value_never_leaks() -> None:
    findings = _check('/P"секрет"', where=Where.ONCE)
    assert all(finding.level is not Level.ERROR for finding in findings)
    for where in Where:
        assert all("секрет" not in f.text for f in _check('/P"секрет" /C секрет', where=where))


@pytest.mark.parametrize(
    "text",
    ['/Pmy секрет', '/Pass"секрет"', 'секрет123 /Lru', '/Pass"секрет" /Pmy секрет'],  # noqa: RUF001
)
def test_no_finding_echoes_text_that_may_hold_a_password(text: str) -> None:
    """Мутационная проверка обязательна (ревью задачи 5): пароль не попадает в замечания."""
    for where in Where:
        for finding in _check(text, where=where):
            assert "секрет" not in finding.text
            assert finding.key is None or "секрет" not in finding.key


def test_unknown_key_is_named_without_its_attached_value() -> None:
    # Не `/Pass`: `/P` с прижатым значением, `/Pass...` — это `/P` со значением.  # noqa: RUF003
    findings = _check('/Foo"секрет"')
    assert [(f.key, f.text) for f in findings] == [
        ("/Foo", "/Foo — неизвестный ключ. Строка сохранится как есть.")
    ]


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("/UCzzz", "/UC"),
        ("/WSPzzz", "/WSP"),
        ("/wspzzz", "/wsp"),
        ("/AccessTokenzzz", "/AccessToken"),
        ("/ModifyPasswordzzz", "/ModifyPassword"),
        ('/UC"zzz"', "/UC"),
    ],
)
def test_unknown_key_glued_to_secret_name_shows_only_the_name(text: str, name: str) -> None:
    """Мутационная проверка обязательна (финальное ревью, F2): приклеенный секрет не виден.

    `('/UC"zzz"', "/UC")` здесь — неизвестный ключ только потому, что в тестовом каталоге
    нет `/UC`. На реальном каталоге это прижатый `/UC` (Ф1): предупреждение про пробел,
    а в постоянной строке ещё и ошибка о пароле — см.
    `test_glued_secret_in_stored_line_is_also_a_plaintext_password_error`.
    """  # noqa: RUF002
    findings = _check(text)
    assert [(f.key, f.text) for f in findings] == [
        (name, f"{name} — неизвестный ключ. Строка сохранится как есть.")
    ]


def test_extra_words_of_secret_key_are_not_quoted() -> None:
    findings = _check("/Pmy секрет")
    assert (
        Level.WARNING,
        "/P: часть значения после пробела платформа отбросит молча — "
        "значение с пробелами возьмите в кавычки",  # noqa: RUF001
    ) in _texts(findings)


def test_language_key_is_fine_outside_permanent_line() -> None:
    """[Ф] T-42 Э1: /L не действует только из .v8i; в argv — работает."""
    for where in (Where.ONCE, Where.DESIGNER_LINE, Where.SET):
        assert _check("/Len", where=where) == []


def test_once_key_overlapping_permanent_is_info() -> None:
    """[Ф] T-42 Э3: побеждает argv — поэтому info, а не warning (спека §4.5)."""  # noqa: RUF002
    permanent = parse("/C постоянный", _catalog())
    findings = _check("/C разовый", where=Where.ONCE, permanent=permanent)
    assert _texts(findings) == [
        (Level.INFO, "/C уже есть в постоянных параметрах базы — сработает разовое значение")
    ]


def test_old_version_gives_single_info_and_no_range_warnings() -> None:
    findings = _check("/i85 /Old", version=parse_version("8.3.10.2252"))
    assert _texts(findings) == [
        (Level.INFO, "Версия 8.3.10.2252 ниже 8.3.18 — данных о ключах для неё нет")  # noqa: RUF001
    ]


def test_unknown_client_and_version_skip_those_checks() -> None:
    assert _check("/SLev2 /i85") == []


def test_findings_name_keys_canonically() -> None:
    findings = _check("/c", where=Where.ONCE)
    assert [finding.key for finding in findings] == ["/C"]


def test_known_key_with_glued_quoted_value_is_a_warning_not_unknown() -> None:
    """Приёмка 21.11.2026, Ф1: `/C"abc"` — известный ключ, значение не там."""
    assert _texts(_check('/C"abc"')) == [
        (Level.WARNING, '/C: значение пишется через пробел — /C "abc"')
    ]


def test_glued_without_quote_stays_unknown() -> None:
    """Без кавычки опечатку в имени от значения не отличить (докстрока `Catalog.match`)."""
    assert _texts(_check("/Cabc")) == [
        (Level.ERROR, "/Cabc — неизвестный ключ. Строка сохранится как есть.")
    ]


def test_glued_secret_value_is_not_quoted_in_the_warning() -> None:
    """Мутационная проверка обязательна: значение секретного ключа не попадает в текст."""
    catalog = load_catalog(
        {
            "group": [{"id": "g", "title": "Г", "order": 1}],
            "key": [
                {
                    "name": "/Code", "group": "g", "modes": ["enterprise"], "summary": "к",
                    "description": "о", "its": "7.3", "reliability": "doc",  # noqa: RUF001
                    "versions": {"since": "8.3.18"}, "args": [{"kind": "secret"}],
                }
            ],
        }
    )
    findings = check(
        parse('/Code"секрет"', catalog), CheckContext(where=Where.ONCE, mode=Mode.ENTERPRISE)
    )
    assert [(f.level, f.key, f.text) for f in findings] == [
        (Level.WARNING, "/Code", "/Code: значение пишется через пробел — /Code <значение>")
    ]


@pytest.mark.parametrize(
    ("text", "name", "mode"),
    [
        ('/WSP"секрет"', "/WSP", Mode.ENTERPRISE),
        ('/UC"секрет"', "/UC", Mode.ENTERPRISE),
        ('/AccessToken"секрет"', "/AccessToken", Mode.ENTERPRISE),
        ('/WSP"секрет"', "/WSP", Mode.DESIGNER),
    ],
)
@pytest.mark.parametrize(
    ("where", "place"),
    [(Where.PERMANENT, ".v8i"), (Where.DESIGNER_LINE, "строке"), (Where.ONCE, None)],
)
def test_glued_secret_in_stored_line_is_also_a_plaintext_password_error(
    text: str, name: str, mode: Mode, where: Where, place: str | None
) -> None:
    """Финальное ревью плана А, I1: прижатый секрет не теряет ошибку «пароль открытым текстом».

    Реальный каталог: `/WSP pwd` в постоянной строке — ERROR, а `/WSP"pwd"` давал только
    предупреждение про пробел. Мутационная проверка обязательна.
    """  # noqa: RUF002
    findings = check(
        parse(text, load_cli_catalog()), CheckContext(where=where, mode=mode)
    )
    texts = _texts(list(findings))
    assert (
        Level.WARNING,
        f"{name}: значение пишется через пробел — {name} <значение>",
    ) in texts
    plaintext = [
        (f.level, f.key, f.text) for f in findings if "открытым текстом" in f.text
    ]
    if place is None:
        assert plaintext == []
    else:
        assert plaintext == [
            (
                Level.ERROR,
                name,
                f"{name}: пароль в {place} хранится открытым текстом — "
                "используйте поле «Пароль»",
            )
        ]
    assert all("секрет" not in f.text for f in findings)


def test_glued_non_secret_value_of_a_key_with_secret_flag_is_not_a_password() -> None:
    """У `/HttpsCert` секрет — только подпараметр `-pwd`: прижатое значение не пароль.

    Не `/Proxy`: наш `Catalog.match` читает `/Proxy"x"` как `/P` с прижатым `roxy"x"`; как
    читает такую строку платформа — **[?]**, не измерено.
    """  # noqa: RUF002
    findings = check(
        parse('/HttpsCert"x"', load_cli_catalog()),
        CheckContext(where=Where.PERMANENT, mode=Mode.ENTERPRISE),
    )
    assert all("открытым текстом" not in f.text for f in findings)
