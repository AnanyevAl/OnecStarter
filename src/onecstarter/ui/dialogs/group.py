"""Диалог группы: создание и переименование/перенос (задача 12).

Два поля — имя и родитель (путь существующей группы или корень). Тот же
приём build/show-разделения и русских подписей кнопок, что и у
`InfobaseDialog` (`for_new`/обычный конструктор, `russian_button_box`,
задачи 8–10): `item is None` — диалог создания, иначе — диалог
переименования и переноса существующей группы.

**Имя без `/`.** Этот символ разделяет уровни пути группы (`services/paths.py`,
`services/groups.py._validate_name` отвергает то же самое при записи).
Диалог обязан заблокировать «ОК» до попытки записи и сказать об этом
своими словами, а не переслать пользователю чужое сообщение об ошибке
записи, — тот же приём, что и `InfobaseDialog._on_accept`/`_violation` для
запрещённых символов в `Connect`. `services` всё равно остаётся последним
рубежом — это второй, самостоятельный барьер на случай вызова в обход
диалога, не замена ему.

**Родитель — не отфильтрован от себя и потомков.** Список путей в выпадающем
списке — все существующие группы плюс корень, без предварительной проверки
цикличности (нельзя перенести группу внутрь самой себя или своего потомка).
Тот же принцип, что у `InfobaseDialog` и `require_group_exists`: клиентская
сторона не дублирует проверку сервера — `Workspace.update_group` уже
отвергает такой перенос `InvalidRequestError`
(«...нельзя переместить внутрь себя или своего потомка»), и ошибка идёт
через обычный путь `ServicesError` → `_on_error`, как и любая другая отказанная
операция записи в этом проекте.
"""  # noqa: RUF002

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from onecstarter.services.display import EMPTY_CONNECT_NOTE, is_degraded_group
from onecstarter.services.model import InfobaseItem
from onecstarter.services.paths import ROOT, normalize_folder
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box


class GroupDialog(QDialog):
    def __init__(
        self,
        item: InfobaseItem | None,
        groups: Sequence[str],
        *,
        default_folder: str = ROOT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self.setWindowTitle(
            f"Переименование группы — {item.name}" if item is not None else "Новая группа"
        )

        self._name = QLineEdit(item.name if item is not None else "")

        folder_options = list(groups)
        current_folder = normalize_folder(item.folder) if item is not None else default_folder
        if current_folder not in folder_options:
            folder_options.append(current_folder)
        self._parent_box = QComboBox()
        self._parent_box.addItems(folder_options)
        self._parent_box.setCurrentText(current_folder)

        form = QFormLayout()
        form.addRow("Имя", self._name)
        form.addRow("Родитель", self._parent_box)

        degraded = item is not None and is_degraded_group(item)
        self._warning = QLabel(EMPTY_CONNECT_NOTE if degraded else "")
        self._warning.setWordWrap(True)

        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if self._warning.text():
            layout.addWidget(self._warning)
        layout.addLayout(form)
        layout.addWidget(self._buttons)

    @classmethod
    def for_new(
        cls,
        groups: Sequence[str],
        *,
        default_folder: str = ROOT,
        parent: QWidget | None = None,
    ) -> "GroupDialog":
        """Диалог создания группы: то же окно, без исходной записи.

        `default_folder` — путь, предложенный родителем по умолчанию: корень
        для пустого места дерева, путь конкретной группы — для «Создать
        группу…» на строке контекстного меню этой группы (подгруппа
        создаётся внутри неё, а не в корне).
        """  # noqa: RUF002
        return cls(None, groups, default_folder=default_folder, parent=parent)

    def _on_accept(self) -> None:
        """Заблокировать «ОК» на пустом имени или «/» — до попытки записи.

        `services.groups._validate_name` отвергает то же самое при записи,
        но её сообщение появилось бы уже после закрытия диалога и не
        объясняло бы, почему именно «/» нельзя, — та же граница и тот же
        приём, что у `InfobaseDialog._on_accept`/`_violation`.
        """  # noqa: RUF002
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Пустое имя", "Имя группы не может быть пустым.")
            return
        if "/" in name:
            QMessageBox.warning(
                self,
                "Недопустимый символ",
                f"Имя «{name}» содержит «/» — этот символ разделяет уровни "
                "пути группы.",
            )
            return
        self.accept()

    def name_text(self) -> str:
        return self._name.text().strip()

    def parent_path(self) -> str:
        return self._parent_box.currentText()

    def button_labels(self) -> list[str]:
        """Подписи кнопок диалога — тот же тест, что и ревью задачи 8: подмена не забыта."""
        return [button.text() for button in self._buttons.buttons()]

    def warning_text(self) -> str:
        """Текст предупреждения о пустом Connect= — пусто, если секция обычная.

        Задача 13: `is_degraded_group` покрыта табличным тестом, но урок 3
        задачи 12 — чистая функция может быть проверена, а строка, доносящая
        её результат до экрана, нет. Этот метод даёт тесту то, что реально
        нарисовано в диалоге, а не то, что вычислила функция в обход виджета.

        Сам по себе этого недостаточно: свойство `text()` у сохранённого
        объекта не доказывает, что объект попал в раскладку диалога, —
        см. `warning_shown()` (круг правок 1 ревью задачи 13).
        """  # noqa: RUF002
        return self._warning.text()

    def warning_shown(self) -> bool:
        """Показано ли предупреждение о пустом Connect= в раскладке диалога.

        Круг правок 1 ревью задачи 13: `warning_text()` проверяет только то,
        что `QLabel` держит текст, а не то, что виджет вообще виден
        пользователю, — `layout.addWidget(self._warning)` вызывается условно,
        и виджет, не добавленный в раскладку, продолжает существовать
        и отдавать `.text()`, оставаясь при этом невидимым. Мутация,
        ломающая именно передачу объекта в раскладку (а не текст в нём),
        осталась бы незамеченной без этой проверки.
        """  # noqa: RUF002
        layout = self.layout()
        assert layout is not None  # выставляется в __init__, всегда есть
        return layout.indexOf(self._warning) != -1

    # -- значения для тестов, в обход имитации ввода ------------------------
    #
    # Тот же приём, что и у InfobaseDialog (M9, круг правок 1 ревью задачи 9):  # noqa: RUF003
    # set_parent_path падает, если запрошенного пути нет среди предложенных
    # диалогом, вместо того, чтобы молча дописывать его, — иначе тест мог бы  # noqa: RUF003
    # выбрать то, чего настоящий виджет не предлагает.

    def set_name(self, value: str) -> None:
        self._name.setText(value)

    def set_parent_path(self, value: str) -> None:
        index = self._parent_box.findText(value)
        if index < 0:
            raise ValueError(f"диалог не предлагает путь «{value}»")
        self._parent_box.setCurrentIndex(index)
