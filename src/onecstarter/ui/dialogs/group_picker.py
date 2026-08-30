"""Выбор группы деревом — общий орган диалогов записи и группы (T-11, п. 5).

`QComboBox`, пункты которого отступом повторяют вложенность групп: корень
первым, родитель всегда раньше потомков, глубина — по числу сегментов пути.
Значение пункта (`userData`) — нормализованный путь (`services/paths.
normalize_folder`), подпись — последний сегмент с отступом. Путь, чей
родитель в наборе отсутствует (неявная группа, [Ф] T-05.7), показывается
целиком: отступ без родителя над ним вводил бы в заблуждение.

Настоящий `QTreeView` в popup не взят намеренно: разворачивание узлов
и выбор родителя в popup требуют ручной обработки, а список групп
заказчика измеряется десятком строк — отступ показывает ту же иерархию,
клавиатурная навигация остаётся штатной.

Контракт для диалогов и тестов: `paths()` — пути в порядке показа,
`current_path()`/`set_current_path()` — выбранное; `set_current_path`
падает `ValueError` на пути, которого орган не предлагает (тот же приём,
что `InfobaseDialog.set_folder`, M9 круг правок 1).
"""  # noqa: RUF002

from collections.abc import Sequence

from PySide6.QtWidgets import QComboBox, QWidget

from onecstarter.services.paths import ROOT

INDENT = "    "
ROOT_LABEL = "/ (корень)"


def _segments(path: str) -> list[str]:
    return [] if path == ROOT else path.split("/")


def build_items(paths: Sequence[str]) -> list[tuple[str, str]]:
    """Пары (подпись, путь) в порядке дерева; путь без родителя в наборе — целиком."""
    ordered = sorted({ROOT, *paths}, key=_segments)
    known = set(ordered)
    items: list[tuple[str, str]] = []
    for path in ordered:
        segments = _segments(path)
        if not segments:
            items.append((ROOT_LABEL, path))
            continue
        parent = "/".join(segments[:-1]) or ROOT
        if parent in known:
            items.append((f"{INDENT * (len(segments) - 1)}{segments[-1]}", path))
        else:
            items.append((path, path))
    return items


class GroupPicker(QComboBox):
    def __init__(self, paths: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill(paths)

    def _fill(self, paths: Sequence[str]) -> None:
        for label, path in build_items(paths):
            self.addItem(label, path)

    def paths(self) -> list[str]:
        return [self.itemData(index) for index in range(self.count())]

    def current_path(self) -> str:
        data = self.currentData()
        return data if isinstance(data, str) else ROOT

    def set_current_path(self, path: str) -> None:
        index = self.findData(path)
        if index < 0:
            raise ValueError(f"орган не предлагает группу «{path}»")
        self.setCurrentIndex(index)

    def ensure_path(self, path: str) -> None:
        """Добавить путь, которого нет среди групп, сохранив порядок дерева и выбор.

        Список путей снимается ДО `clear()` — после очистки `paths()` пуст.
        """
        if self.findData(path) >= 0:
            return
        current = self.current_path()
        known = self.paths()
        self.clear()
        self._fill([*known, path])
        self.set_current_path(current)
