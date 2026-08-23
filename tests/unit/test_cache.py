"""services/cache.py: пути, размеры, тексты. Часть — защитные тесты вехи."""

from pathlib import Path

import pytest

from onecstarter.services.cache import (
    CacheKind,
    CacheMeasure,
    ClearReport,
    cache_path,
    clear_question,
    format_size,
    is_valid_cache_id,
    report_text,
)

GUID = "a1b2c3d4-e5f6-4a0b-8c1d-2e3f4a5b6c7d"
ENV = {"APPDATA": r"C:\Users\u\AppData\Roaming", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}


class TestCachePath:
    def test_valid_guid_builds_both_roots(self) -> None:
        assert cache_path(ENV, CacheKind.USER, GUID) == Path(
            r"C:\Users\u\AppData\Roaming\1C\1Cv8"
        ) / GUID
        assert cache_path(ENV, CacheKind.PROGRAM, GUID) == Path(
            r"C:\Users\u\AppData\Local\1C\1Cv8"
        ) / GUID

    @pytest.mark.parametrize(
        "section_id",
        [
            None,
            "",                      # ГЛАВНЫЙ РИСК (спека §5.1): пустой ID дал бы сам корень
            "не-guid",
            f" {GUID}",              # пробелы по краям — имя каталога не совпадёт
            f"{GUID} ",
            GUID.replace("-", ""),   # 32 hex без дефисов — не форма ID
            GUID[:-1],               # обрезанный
        ],
    )
    def test_invalid_id_gives_no_address(self, section_id: str | None) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §5.1, §6): без валидного GUID адреса нет вовсе.

        При пустом ID склейка Path(root)/"1C"/"1Cv8"/"" дала бы САМ корень
        %LOCALAPPDATA%\\1C\\1Cv8, и рекурсивное удаление снесло бы кэши всех
        баз разом. Кандидат мутационной проверки: снять проверку GUID
        в cache_path — этот тест обязан упасть на пустом ID.
        """  # noqa: RUF002
        assert cache_path(ENV, CacheKind.USER, section_id) is None
        assert cache_path(ENV, CacheKind.PROGRAM, section_id) is None

    def test_missing_root_gives_no_address(self) -> None:
        assert cache_path({}, CacheKind.USER, GUID) is None
        assert cache_path({"APPDATA": ""}, CacheKind.USER, GUID) is None

    def test_is_valid_cache_id(self) -> None:
        assert is_valid_cache_id(GUID)
        assert is_valid_cache_id(GUID.upper())
        assert not is_valid_cache_id(None)
        assert not is_valid_cache_id("")


class TestFormatSize:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            (0, "0 Б"),
            (1023, "1023 Б"),
            (1024, "1 КБ"),
            (9728, "9,5 КБ"),                # 9.5 КБ — один знак, запятая
            (217055232, "207 МБ"),           # пример спеки §3.5
            (3113851290, "2,9 ГБ"),          # стиль протокола T-05.10
        ],
    )
    def test_table(self, size: int, expected: str) -> None:
        assert format_size(size) == expected


class TestTexts:
    def test_program_question_is_calm(self) -> None:
        text = clear_question(
            CacheKind.PROGRAM, "Бухгалтерия", CacheMeasure(files=412, total_bytes=217055232)
        )
        assert "Удалить программный кэш базы «Бухгалтерия» (207 МБ)?" in text
        assert "создаст заново" in text
        # Про пользовательский состав программный вопрос не говорит.
        assert "история ввода" not in text

    def test_user_question_lists_contents_without_promises(self) -> None:
        """Спека §3.5: перечисляет состав, «ничего страшного» не обещает."""
        text = clear_question(
            CacheKind.USER, "Бухгалтерия", CacheMeasure(files=10, total_bytes=1024)
        )
        assert "Удалить пользовательский кэш базы «Бухгалтерия» (1 КБ)?" in text
        assert "настройки форм" in text
        assert "история ввода" in text
        assert "словар" in text

    @pytest.mark.parametrize(
        ("report", "expected"),
        [
            (
                ClearReport(deleted=412, freed_bytes=217055232, failed=0),
                "Удалено 412 файлов, освобождено 207 МБ.",
            ),
            (
                ClearReport(deleted=412, freed_bytes=217055232, failed=7),
                "Удалено 412 файлов, освобождено 207 МБ. Не удалось удалить 7 — "  # noqa: RUF001
                "файлы заняты запущенной 1С; закройте программу и повторите.",  # noqa: RUF001
            ),
            (
                ClearReport(deleted=1, freed_bytes=1024, failed=0),
                "Удалён 1 файл, освобождено 1 КБ.",
            ),
            (ClearReport(deleted=2, freed_bytes=0, failed=0), "Удалено 2 файла, освобождено 0 Б."),
        ],
    )
    def test_report_text(self, report: ClearReport, expected: str) -> None:
        assert report_text(report) == expected
