"""services/cache.py: пути, размеры, тексты. Часть — защитные тесты вехи."""

from pathlib import Path

import pytest

from onecstarter.services.cache import (
    CacheEntry,
    CacheKind,
    CacheMeasure,
    ClearReport,
    EntryKind,
    WindowsCacheOps,
    cache_path,
    clear,
    clear_question,
    format_size,
    is_valid_cache_id,
    measure,
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
            # Из файла .v8i недостижим — парсер режет по строкам, значение
            # с переводом строки в ID не попадёт. Но это единственный случай  # noqa: RUF003
            # в наборе, отличающий `fullmatch` от `match(...) + "$"` (`$`
            # у необёрнутого regex совпадает и перед завершающим `\n`) —  # noqa: RUF003
            # страхует будущий рефакторинг регэкспа, который заменил бы
            # fullmatch на match+$ по невнимательности.
            f"{GUID}\n",
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
            (217_000_000, "207 МБ"),         # 206,95 МБ: округляет, не усекает
            (10_694_058_443, "10 ГБ"),       # 9,96 ГБ: граница, округляется до целого
            (1_048_400, "1 МБ"),             # 1023,8 КБ: округление → перенос единицы
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
        # Спека §3.5: последствия удаления пользовательского кэша не
        # проверены (в отличие от программного) — вопрос не вправе обещать
        # безобидность.
        assert "создаст заново" not in text

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


class FakeCacheOps:
    """ФС в памяти, ведёт себя как настоящая: remove_dir отказывает непустому
    каталогу и каталогу из busy_dirs (даже пустому — имитация rmdir на чистом
    каталоге, который всё равно отказал), занятый файл — PermissionError,
    удаления реально убирают записи.

    Богатый стимул, а не пустышка — требование мутационной проверки проекта:
    бессильная мутация всегда означала бедный стимул, не слабое утверждение.
    """  # noqa: RUF002

    def __init__(self) -> None:
        self.tree: dict[Path, list[CacheEntry]] = {}
        self.busy: set[Path] = set()
        self.busy_dirs: set[Path] = set()
        self.unreadable: set[Path] = set()
        self.removed_links: list[Path] = []
        self.listed: list[Path] = []

    def put_dir(self, path: Path) -> None:
        self.tree.setdefault(path, [])
        parent = path.parent
        if parent in self.tree and all(e.path != path for e in self.tree[parent]):
            self.tree[parent].append(CacheEntry(path, EntryKind.DIR, 0))

    def put(self, entry: CacheEntry) -> None:
        self.tree.setdefault(entry.path.parent, []).append(entry)
        if entry.kind is EntryKind.DIR:
            self.tree.setdefault(entry.path, [])

    def list_dir(self, path: Path) -> list[CacheEntry]:
        self.listed.append(path)
        if path in self.unreadable:
            raise PermissionError(5, "отказано в доступе")
        if path not in self.tree:
            # Как os.scandir на отсутствующем каталоге (долг №8 финального
            # ревью: KeyError фейка расходился с настоящей ФС, и защитный  # noqa: RUF003
            # тест гонки убивал мутацию незапланированным сигналом).
            raise FileNotFoundError(2, "системе не удаётся найти указанный путь")
        return list(self.tree[path])

    def is_dir(self, path: Path) -> bool:
        return path in self.tree

    def _drop(self, path: Path) -> None:
        for entries in self.tree.values():
            for entry in list(entries):
                if entry.path == path:
                    entries.remove(entry)

    def remove_file(self, path: Path) -> None:
        if path in self.busy:
            raise PermissionError(32, "файл используется другим процессом")
        self._drop(path)

    def remove_dir(self, path: Path) -> None:
        if path in self.busy_dirs:
            raise PermissionError(5, "папка недоступна для удаления")
        if self.tree.get(path):
            raise OSError(145, "Папка не пуста")
        self.tree.pop(path, None)
        self._drop(path)

    def remove_link(self, path: Path) -> None:
        self.removed_links.append(path)
        self._drop(path)


ROOT = Path(r"C:\cache") / GUID


def _standard_tree() -> FakeCacheOps:
    """<ID>/{Config/{a,b}, SICache/c, top} — форма снятая с настоящего кэша."""  # noqa: RUF002
    ops = FakeCacheOps()
    ops.put_dir(ROOT)
    ops.put(CacheEntry(ROOT / "Config", EntryKind.DIR, 0))
    ops.put(CacheEntry(ROOT / "Config" / "a.bin", EntryKind.FILE, 100))
    ops.put(CacheEntry(ROOT / "Config" / "b.bin", EntryKind.FILE, 200))
    ops.put(CacheEntry(ROOT / "SICache", EntryKind.DIR, 0))
    ops.put(CacheEntry(ROOT / "SICache" / "c.bin", EntryKind.FILE, 300))
    ops.put(CacheEntry(ROOT / "top.pfl", EntryKind.FILE, 50))
    return ops


class TestMeasure:
    def test_counts_files_and_bytes_recursively(self) -> None:
        assert measure(ROOT, _standard_tree()) == CacheMeasure(files=4, total_bytes=650)

    def test_unreadable_subdir_is_skipped(self) -> None:
        """Замер — оценка для вопроса, а не отчёт: недочитанное не роняет его."""  # noqa: RUF002
        ops = _standard_tree()
        ops.unreadable.add(ROOT / "Config")
        assert measure(ROOT, ops) == CacheMeasure(files=2, total_bytes=350)

    def test_link_counts_as_entry_without_size_and_is_not_walked(self) -> None:
        """Долг №5 финального ревью: «ссылка = запись без размера» — как в clear.

        Ссылка входит в счётчик записей (files), размера не добавляет,
        и measure не обходит её содержимое (спека §5.2).
        """
        ops = _standard_tree()
        link = ROOT / "vrs-link"
        ops.put(CacheEntry(link, EntryKind.LINK, 0))
        outside = Path(r"C:\outside")
        ops.put_dir(outside)
        ops.put(CacheEntry(outside / "чужое.txt", EntryKind.FILE, 999))
        ops.tree[link] = ops.tree[outside]  # если кто-то всё же зайдёт — увидит цель

        assert measure(ROOT, ops) == CacheMeasure(files=5, total_bytes=650)
        assert link not in ops.listed


class TestClear:
    def test_full_success_removes_everything_including_root(self) -> None:
        ops = _standard_tree()
        report = clear(ROOT, ops)
        assert report == ClearReport(deleted=4, freed_bytes=650, failed=0)
        assert ROOT not in ops.tree

    def test_busy_file_does_not_stop_walk_and_secondary_is_not_counted(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §3.6–§3.7): обход не останавливается,
        вторичная «Папка не пуста» не попадает в счётчик отказов.

        Кандидаты мутационной проверки: остановить обход на первой ошибке
        (b.bin и c.bin перестанут удаляться); начать считать вторичные
        (failed станет 3: файл + Config + корень).
        """  # noqa: RUF002
        ops = _standard_tree()
        ops.busy.add(ROOT / "Config" / "a.bin")
        report = clear(ROOT, ops)
        # b.bin идёт ПОСЛЕ занятого a.bin в том же каталоге — и удалён.
        assert report == ClearReport(deleted=3, freed_bytes=550, failed=1)
        # Config и корень не удалены (не пусты), но это вторичные отказы.
        assert ROOT in ops.tree
        assert any(e.path == ROOT / "Config" / "a.bin" for e in ops.tree[ROOT / "Config"])

    def test_link_is_removed_as_link_and_never_walked(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §5.2): по ссылке обход не идёт.

        Кандидат мутационной проверки: последовать за ссылкой (обойти её
        содержимое как каталог) — тест обязан упасть по list_dir на ссылке.
        """  # noqa: RUF002
        ops = _standard_tree()
        link = ROOT / "vrs-link"
        ops.put(CacheEntry(link, EntryKind.LINK, 0))
        # Цель ссылки существует как каталог с файлом — обход НЕ должен её видеть.  # noqa: RUF003
        outside = Path(r"C:\outside")
        ops.put_dir(outside)
        ops.put(CacheEntry(outside / "чужое.txt", EntryKind.FILE, 999))
        ops.tree[link] = ops.tree[outside]  # если кто-то всё же зайдёт — увидит цель

        report = clear(ROOT, ops)
        assert link in ops.removed_links
        assert link not in ops.listed
        assert any(e.path == outside / "чужое.txt" for e in ops.tree[outside])
        assert report.deleted == 5  # 4 файла + ссылка
        assert report.freed_bytes == 650  # чужие 999 байт не тронуты и не посчитаны

    def test_unreadable_dir_is_one_primary_failure(self) -> None:
        ops = _standard_tree()
        ops.unreadable.add(ROOT / "SICache")
        report = clear(ROOT, ops)
        assert report.failed == 1
        assert report.deleted == 3  # a, b, top.pfl
        assert ROOT in ops.tree  # корень не пуст — вторичный отказ, не считан

    def test_clean_subdir_rmdir_failure_is_primary(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §3.7): отказ rmdir на каталоге, где всё внутри
        уже удалилось, — первичный отказ, и его нужно посчитать.

        О таком каталоге ничем другим не сказано, в отличие от «папка не
        пуста» из-за занятого файла внутри (это вторичный отказ и не считается).

        Кандидат мутационной проверки: убрать `failed += 1` из ветки
        `except OSError` при `ops.remove_dir(entry.path)` внутри `clear_dir` —
        этот тест обязан упасть на `report.failed == 1`.
        """  # noqa: RUF002
        ops = _standard_tree()
        ops.busy_dirs.add(ROOT / "SICache")
        report = clear(ROOT, ops)
        assert report.failed == 1
        assert report.deleted == 4  # a, b, c.bin, top.pfl — все файлы всё равно удалены
        assert report.freed_bytes == 650
        # SICache опустел (c.bin удалён), но сам каталог остался — rmdir отказал.
        assert ops.tree[ROOT / "SICache"] == []
        # Корень не пуст (SICache никуда не делся) — его rmdir даже не пробуется.  # noqa: RUF003
        assert ROOT in ops.tree

    def test_root_rmdir_failure_after_full_cleanup_is_primary(self) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §3.7): отказ rmdir самого корня после того,
        как всё его содержимое удалилось без ошибок, — тоже первичный отказ.

        Кандидат мутационной проверки: убрать `failed += 1` из ветки
        `except OSError` вокруг `ops.remove_dir(root)` в `clear()` — этот
        тест обязан упасть на `report.failed == 1`.
        """  # noqa: RUF002
        ops = _standard_tree()
        ops.busy_dirs.add(ROOT)
        report = clear(ROOT, ops)
        assert report == ClearReport(deleted=4, freed_bytes=650, failed=1)
        assert ROOT in ops.tree  # корень пуст изнутри, но сам rmdir отказал


class TestWindowsCacheOpsIntegration:
    """Настоящая ФС на tmp_path: живые кэши и профиль не трогаются."""

    def test_measure_and_clear_real_tree(self, tmp_path: Path) -> None:
        root = tmp_path / GUID
        (root / "Config").mkdir(parents=True)
        (root / "Config" / "a.bin").write_bytes(b"x" * 100)
        (root / "top.pfl").write_bytes(b"y" * 50)
        ops = WindowsCacheOps()

        assert measure(root, ops) == CacheMeasure(files=2, total_bytes=150)
        report = clear(root, ops)
        assert report == ClearReport(deleted=2, freed_bytes=150, failed=0)
        assert not root.exists()

    def test_junction_is_removed_without_touching_target(self, tmp_path: Path) -> None:
        """ЗАЩИТНЫЙ ТЕСТ (спека §5.2) на настоящем reparse point.

        Кандидат мутационной проверки: классифицировать junction каталогом
        (убрать is_junction из list_dir) — содержимое цели будет удалено,
        и тест обязан упасть на «чужое.txt существует».
        """  # noqa: RUF002
        import _winapi

        target = tmp_path / "target"
        target.mkdir()
        (target / "чужое.txt").write_bytes(b"z" * 10)
        root = tmp_path / GUID
        root.mkdir()
        (root / "своё.bin").write_bytes(b"a" * 5)
        _winapi.CreateJunction(str(target), str(root / "junction"))
        ops = WindowsCacheOps()

        entries = {e.path.name: e.kind for e in ops.list_dir(root)}
        assert entries["junction"] is EntryKind.LINK

        report = clear(root, ops)
        assert not root.exists()
        assert (target / "чужое.txt").exists()  # цель не тронута
        assert report == ClearReport(deleted=2, freed_bytes=5, failed=0)
