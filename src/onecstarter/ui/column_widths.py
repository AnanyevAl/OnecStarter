"""Ширины колонок списка между пересборками и запусками (T-38, спека 3.2.4 ч. 1, §2).

Колонка 0 (имя) растягивается на оставшуюся ширину и не сохраняется: её ширину
задают окно и соседние колонки (решение заказчика 31.10.2026 — всегда, без
настройки). Остальные колонки тянутся мышью; их ширины уходят в `save`
с задержкой — `sectionResized` идёт на каждом пикселе перетаскивания.

Изменения, сделанные самой программой (смена модели, восстановление, подгонка
по содержимому), в `save` не попадают: на время `rebuilding()` обработчик
выключен. Режимы секций ставятся после каждой смены модели — переживают ли
они `setModel`, не проверено, а повторная установка дешевле проверки.

Ширина колонки без сохранённого значения подгоняется по содержимому один раз
и дальше держится в пределах сеанса, как до T-38 держалась у «Баз».
"""  # noqa: RUF002

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QHeaderView, QTreeView

SAVE_DELAY_MS = 1000


class ColumnWidths(QObject):
    def __init__(
        self,
        tree: QTreeView,
        ids: Sequence[str],
        saved: Mapping[str, int],
        save: Callable[[dict[str, int]], None],
        *,
        delay_ms: int = SAVE_DELAY_MS,
    ) -> None:
        super().__init__(tree)
        self._tree = tree
        self._ids = tuple(ids)
        kept = set(self._ids[1:])
        self._widths = {key: width for key, width in saved.items() if key in kept}
        self._save = save
        self._applying = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._flush)
        tree.header().sectionResized.connect(self._on_resized)

    def widths(self) -> dict[str, int]:
        return dict(self._widths)

    @contextmanager
    def rebuilding(self) -> Iterator[None]:
        """Обернуть смену модели: внутри — без записи, на выходе — режимы и ширины."""
        self._applying = True
        try:
            yield
            self._apply()
        finally:
            self._applying = False

    def _apply(self) -> None:
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, min(len(self._ids), header.count())):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            key = self._ids[column]
            width = self._widths.get(key)
            if width is None:
                self._tree.resizeColumnToContents(column)
                self._widths[key] = self._tree.columnWidth(column)
            else:
                self._tree.setColumnWidth(column, width)

    def _on_resized(self, column: int, _old: int, new: int) -> None:
        if self._applying or column == 0 or column >= len(self._ids):
            return
        self._widths[self._ids[column]] = new
        self._timer.start()

    def _flush(self) -> None:
        self._save(dict(self._widths))
