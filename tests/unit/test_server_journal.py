"""Тесты журнала профиля: ротация и события."""
from datetime import datetime
from pathlib import Path

from onecstarter.services.server_journal import (
    append_event,
    journal_path,
    previous_journal_path,
    rotate_journal,
)


class TestRotate:
    def test_current_becomes_previous(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ: ротация сохраняет прошлый запуск (спека §12.6).

        Мутация «rotate удаляет файл вместо переноса» теряет историю.
        """  # noqa: RUF002
        journal_path(tmp_path, "p1").parent.mkdir(parents=True, exist_ok=True)
        journal_path(tmp_path, "p1").write_text("старый запуск", encoding="utf-8")
        rotate_journal(tmp_path, "p1")
        assert not journal_path(tmp_path, "p1").exists()
        assert previous_journal_path(tmp_path, "p1").read_text(encoding="utf-8") == "старый запуск"

    def test_missing_current_is_a_no_op(self, tmp_path: Path) -> None:
        """rotate_journal не падает и не создаёт пустых файлов."""
        rotate_journal(tmp_path, "p1")
        assert not journal_path(tmp_path, "p1").exists()
        assert not previous_journal_path(tmp_path, "p1").exists()


class TestAppendEvent:
    def test_line_format_and_encoding(self, tmp_path: Path) -> None:
        append_event(tmp_path / "j.log", "запуск: тест", datetime(2026, 8, 28, 9, 5, 7))
        assert (tmp_path / "j.log").read_text(encoding="utf-8") == "[09:05:07] запуск: тест\n"

    def test_appends_not_overwrites(self, tmp_path: Path) -> None:
        """append_event добавляет в конец, не затирая предыдущие строки."""
        path = tmp_path / "j.log"
        append_event(path, "первое событие", datetime(2026, 8, 28, 9, 5, 7))
        append_event(path, "второе событие", datetime(2026, 8, 28, 9, 5, 8))
        content = path.read_text(encoding="utf-8")
        assert content == "[09:05:07] первое событие\n[09:05:08] второе событие\n"
