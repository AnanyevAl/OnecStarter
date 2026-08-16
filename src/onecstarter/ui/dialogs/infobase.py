"""Диалог записи информационной базы: свойства, добавление, drag&drop каталога.

Типизированные поля (имя, размещение, группа, версия, клиент, аутентификация
ОС) пишутся через `changes()`: точечно, по границам фрагментов `Connect`
(`replace_fragment`), и только то, что пользователь фактически тронул —
нетронутое поле не попадает в правку, даже если его виджет инициализирован
значением, отличным по форме от сырого значения файла (см. `_initial_app`,
`_initial_wa`, добавление текущей версии/нормализованной папки в свои
выпадающие списки).

**Круг правок 1 (ревью задачи 9, самая сильная модель).** Поля размещения
теперь заполняются `raw_fragment_value` — сырым срезом того же разбора,
которым `replace_fragment` потом заменяет значение (`domain/connect.py`,
единый `_iter_raw_fragments`). До этого поле заполнялось через `parse_connect`
(снимает кавычки), а писалось через `fragment_spans` (сырой срез) — на строке
с пробелом вокруг «=» или экранированной кавычкой внутри значения эти два
разбора расходились, и нетронутый диалог молча портил `Connect`. Отсюда же
три следствия:

- поле размещения предлагается редактируемым, только если фрагмент реально
  нашёлся в строке (`_placement_entries`); не нашёлся — поле нередактируемо,
  с пояснением, а не `KeyError` из `changes()` без единого перехваченного
  места (C3);
- символ, который пользователь добавил правкой (а не тот, что уже был
  в файле — например, экранированная пара `""`), блокирует «ОК»
  с объяснением, а не молча портит `Connect` (`_placement_violation`,
  `_FORBIDDEN_PLACEMENT_CHARACTERS`);
- `Folder` сравнивается через `normalize_folder`, а не с сырым значением
  файла: путь группы в `groups` без ведущего слэша, `item.folder` — с ним,
  и без нормализации это расхождение цепляло каждую вложенную запись,
  а не только настоящую сироту без секции-группы (I7).

**Круг правок 2 (ревью задачи 9).** Запрет ввода расширен с кавычки на `;`:
`_edited_connect` применяет `replace_fragment` последовательно к
промежуточной строке, и `;`, вписанный в одно поле размещения, создаёт для
следующего поля новый (чужой) фрагмент в уже изменённом тексте — второй
`replace_fragment` находит не то, что должно (I4 стал item 3, метод
переименован в `_placement_violation`, проверяется и через `_on_accept`,
не только напрямую). `domain/connect.py` перестал обрезать имя фрагмента —
ссылка на факт 6 скила v8i-format здесь была ложной (факт 6 про ключ секции
`Connect`, не про фрагменты внутри его значения), решение — не обрезать
и явно; секция с пробелом вокруг «=» внутри `Connect` теперь снова
классифицируется как `UNKNOWN`, а не притворяется рабочей записью.

**Задача 10 — добавление записи и смена вида размещения.**

- `InfobaseDialog.__init__` принимает `item: InfobaseItem | None`. `None` —
  режим добавления (`for_new`): нет исходной записи, нечего показывать
  в «Версии», «Клиенте», «Аутентификации ОС» и таблице прочих ключей —
  `Workspace.add_infobase` их и не принимает, поэтому строить эти виджеты
  для несуществующей записи означало бы рисовать элементы, которым некуда
  писать.
- **Вид размещения — теперь выпадающий список (`_kind_box`), а не подпись.**
  И для новой записи (обязателен выбор), и для правки существующей — в этом
  и есть задача 10: пользователь может передумать, какого вида база. Поля
  всех трёх видов (`_file_path`, `_server`, `_ref`, `_url`) существуют
  в форме всегда, видна только строка выбранного вида
  (`_update_kind_visibility`, `QFormLayout.setRowVisible`) — так `set_file_path`
  и подобные сеттеры остаются рабочими независимо от того, какой вид сейчас
  выбран.
- **Смена вида переписывает `Connect` целиком.** `File=` и `Srvr=` не
  сосуществуют — точечная правка (`replace_fragment`) здесь не годится,
  строка собирается заново `build_connect`. Всё, что пользователь не ввёл
  заново, пропадает — `kind_change_warning()` обязана предупредить об этом
  до записи (`BasesView._apply_properties`, `QMessageBox`-подтверждение).
  Запись с `item.kind is UNKNOWN` — дополнительный, не выбираемый вручную
  пункт списка (подпись `BADGE_LABELS[UNKNOWN]`): без него нетронутый
  диалог такой записи не находил бы среди трёх обычных пунктов совпадения
  для `item.kind`, откатывался бы на первый (`FILE`) и решал бы, что вид
  сменили, хотя пользователь ничего не трогал, — тот же класс дефекта,
  ради которого написан весь этот файл (I7, M9).
- **Кавычки в новом значении не удваиваются (решение по итогам ревью).**
  Черновик задачи предлагал `value.replace('"', '""')` в `build_connect` —
  это то самое допущение, которое задача 9 явно отвергла для точечной правки
  (`_placement_violation`, «I4»): экранирование кавычек в `Connect` — [Д],
  не [Ф] (скил v8i-format, «Непроверенное»), и удвоить их самим значило бы
  записать в чужой файл догадку, только уже при СБОРКЕ строки, а не при её
  правке — тот же риск, применённый к другому месту кода. `build_connect`
  вместо этого отказывает (`ValueError`) на `"` и `;` в значении; диалог
  не даёт этим символам сюда дойти тем же способом, что и раньше (`_violation`,
  объединяет старую `_placement_violation` для точечной правки и новую
  проверку для пересборки — свежего «сырого» значения для сравнения
  тут нет, весь текст полей выбранного вида — ввод пользователя).
- **`accept_directory`/drag&drop.** Перетащенный каталог — кандидат
  в файловую базу: `dragEnterEvent`/`dragMoveEvent` принимают drop, только
  если это ровно один локальный путь и он каталог (`dropped_directory`),
  `dropEvent` зовёт `accept_directory`, которая переключает вид на `FILE`,
  заполняет путь и, если поле имени пусто, подставляет имя каталога —
  не переписывая то, что пользователь уже ввёл сам.

**Круг правок 1 (ревью задачи 10).** Четыре пункта:

1. Граница исключений (`BasesView._apply_properties`) ловила `ValueError`
   из `build_connect` только на пути правки; `_apply_new_infobase` звала
   `dialog.new_record()` (тот же `build_connect` внутри) без единого `try` —
   несимметрично, хотя оба метода вызываются тестами напрямую, в обход
   `_on_accept`. Приведено к тому же приёму на обоих путях.
2. `russian_confirm` — единственный гейт между пользователем и молчаливой
   полной перезаписью `Connect` — зашивала `box.exec()` внутрь себя, и три
   теста, подменявшие саму функцию лямбдой, ни разу не выполняли настоящую
   подпись кнопок и чтение клика. Разнесена на `build_confirm_box`
   (сборка) / `is_confirmed` (чтение результата) / `russian_confirm`
   (тонкая обвязка с `exec()`) — тем же приёмом, что и у `InfobaseDialog.for_new`.
3. `test_dropped_directory_helper_accepts_a_single_local_directory` сравнивал
   `Path(result) == directory` — на Windows это разделители-нечувствительное
   сравнение, не заметившее бы отката нормализации в `_dropped_directory`.
   Заменено на сравнение строк.
4. Спека §3.1 требует «обзор каталога и drag&drop каталога» — план заявил
   только второе. Кнопка «Обзор…» рядом с полем пути (`_browse_button`,
   `browse_for_directory`, инжектируемый `choose_directory` — тот же приём,
   что и `open_directory` в `ConnectionPanel`) зовёт тот же `accept_directory`,
   что и `dropEvent`.

Прочие ключи секции показываются, но не правятся. Общий редактор ключей
открывает класс порчи, который наши проверки не ловят: [Ф] факт 6 скила
v8i-format — `Connect` с пробелом вокруг «=» платформа не распознаёт
и необратимо добивает секцию.

Секретные значения не показываются и не редактируются. Хранение паролей
вне v1 (§0 спеки 4a), поле правки пароля создало бы способ записать его
в .v8i открытым текстом.
"""  # noqa: RUF002

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from onecstarter.domain.connect import (
    ConnectKind,
    extra_fragment_names,
    raw_fragment_value,
    replace_fragment,
)
from onecstarter.domain.default_version import DefaultVersionRule
from onecstarter.domain.version import Installation
from onecstarter.security.secrets import is_secret_key
from onecstarter.services.connection import BADGE_LABELS, connection_path
from onecstarter.services.display import VersionCell, version_cell
from onecstarter.services.model import InfobaseItem
from onecstarter.services.paths import ROOT, normalize_folder
from onecstarter.ui.dialogs.buttons import ButtonKind, russian_button_box

HIDDEN_VALUE = "значение скрыто"
_UNPARSED_PLACEMENT_HINT = "не удалось разобрать для правки"

# Символы, которые несут смысл в синтаксисе Connect и не могут появиться
# в поле размещения после правки (круг правок 2, item 3): `"` — граница
# значения (экранирование не подтверждено, I4); `;` — разделитель фрагментов,
# из-за которого `replace_fragment`, применяемый последовательно к
# промежуточной строке, находит для соседнего поля не тот фрагмент. Задача 10
# (`build_connect`) применяет тот же запрет к сборке новой строки — см.
# докстринг модуля.
_FORBIDDEN_PLACEMENT_CHARACTERS = ('"', ";")

# Ключи, показанные отдельными полями или служебные для нас. В таблицу  # noqa: RUF003
# «прочих» они не идут: Connect несёт пароли, ID и OrderInList — наша
# внутренняя механика, остальные дублировали бы поля выше.
TYPED_KEYS = frozenset(
    {"connect", "version", "defaultversion", "app", "wa", "id", "orderinlist", "folder"}
)

# Подписанные фрагменты Connect по виду записи — общий источник для формы
# и для точечной правки: (метка поля, имя фрагмента). Порядок объявления
# (FILE, SERVER, WEB) — порядок строк в форме и пунктов выпадающего списка
# видов (`_KIND_CHOICES`).
_PLACEMENT_SPEC: dict[ConnectKind, tuple[tuple[str, str], ...]] = {
    ConnectKind.FILE: (("Путь", "File"),),
    ConnectKind.SERVER: (("Сервер", "Srvr"), ("Имя базы на сервере", "Ref")),
    ConnectKind.WEB: (("Адрес", "ws"),),
}

# Имена фрагментов размещения по виду — без меток, для extra_fragment_names
# (kind_change_warning: что сверх этого набора потеряет смена вида).
_PLACEMENT_KEYS: dict[ConnectKind, tuple[str, ...]] = {
    kind: tuple(name for _label, name in spec) for kind, spec in _PLACEMENT_SPEC.items()
}

# Виды, которые пользователь может выбрать в _kind_box, — все, для которых
# build_connect умеет собрать строку. UNKNOWN сюда не входит: это не цель
# выбора, а обозначение того, что уже есть в правящейся записи (см.  # noqa: RUF003
# докстринг модуля).
_KIND_CHOICES: tuple[ConnectKind, ...] = tuple(_PLACEMENT_SPEC)


def build_connect(
    kind: ConnectKind, *, file_path: str = "", server: str = "", ref: str = "", url: str = ""
) -> str:
    """Строка соединения для новой записи или для полной пересборки при смене вида.

    Только фрагменты размещения — прочие ключи новая запись не несёт,
    а при смене вида задача 10 требует явное предупреждение о том, что они
    пропадут (`InfobaseDialog.kind_change_warning`), а не тихую попытку
    сохранить их здесь.

    Кавычки и `;` в значении отклоняются (`ValueError`), а не удваиваются —
    решение по итогам ревью задачи 10, подробности в докстринге модуля:
    экранирование кавычек в Connect — [Д], не [Ф] (скил v8i-format,
    «Непроверенное»), и удвоить их самим означало бы записать в чужой файл
    догадку, ту же самую, что задача 9 отвергла для точечной правки. Диалог
    не даёт этим символам сюда дойти (`InfobaseDialog._violation`); проверка
    здесь — второй, самостоятельный рубеж на случай вызова в обход диалога.
    """  # noqa: RUF002
    if kind not in _PLACEMENT_KEYS:
        raise ValueError(f"build_connect не поддерживает вид размещения {kind}")
    values = {
        ConnectKind.FILE: (("File", file_path),),
        ConnectKind.SERVER: (("Srvr", server), ("Ref", ref)),
        ConnectKind.WEB: (("ws", url),),
    }[kind]
    for name, value in values:
        for char in _FORBIDDEN_PLACEMENT_CHARACTERS:
            if char in value:
                raise ValueError(f"{name}: значение содержит запрещённый символ ({char})")
    return "".join(f'{name}="{value}";' for name, value in values)


def dropped_directory(mime: QMimeData) -> str | None:
    """Путь каталога из mime-данных перетаскивания — `None`, если это не он.

    Принимается ровно один локальный путь, и он обязан быть каталогом:
    несколько путей или отдельный файл — не то перетаскивание, для
    которого написан `accept_directory` (файловая база — каталог
    с `1Cv8.1CD` внутри, не сам файл базы).

    `QUrl.toLocalFile()` на этой машине (PySide6 6.11.1, Windows) отдаёт
    путь с прямыми слэшами — проверено запуском, а не по документации.
    `.v8i` пишет пути с обратными (фикстура, `File="C:\\Bases\\Demo";`),
    и платформа 1С не подтверждена на приём прямых — рисковать нечем,
    `Path(...)` нормализует разделители под ОС до того, как путь попадёт
    в `File=`.
    """  # noqa: RUF002
    urls = mime.urls()
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return str(path) if path.is_dir() else None


def browse_for_directory() -> str:
    """Системный диалог выбора каталога. Пустая строка — пользователь отменил.

    Без родителя: тот же выбор, что и у `open_in_explorer` в панели
    (`ui/bases/panel.py`) — инжектируемая функция сама решает, чем и как
    показываться (кнопка «Обзор…», `InfobaseDialog.__init__`,
    `choose_directory`), вызывающему коду интересен только результат.
    Инъекция — тем же приёмом, что и `open_directory` панели: тесты
    подменяют её и проверяют поведение без модального `QFileDialog`.
    """  # noqa: RUF002
    return QFileDialog.getExistingDirectory()


def other_keys(item: InfobaseItem) -> list[tuple[str, str]]:
    """Прочие ключи секции с уже скрытыми секретными значениями. Без Qt."""  # noqa: RUF002
    return [
        (name, HIDDEN_VALUE if is_secret_key(name) else value)
        for name, value in item.keys
        if name.casefold() not in TYPED_KEYS
    ]


def _typed_value(keys: Sequence[tuple[str, str]], name: str) -> str | None:
    """Значение типизированного ключа секции по имени, без учёта регистра.

    `InfobaseItem` не заводит отдельного поля под `WA` (в отличие от `App`
    и `Version`) — единственный источник его текущего значения `item.keys`.
    """  # noqa: RUF002
    wanted = name.casefold()
    for key, value in keys:
        if key.casefold() == wanted:
            return value
    return None


def _app_key(app: str | None) -> str | None:
    """Привести `App` к данным пункта комбобокса: `None`/`Auto` — «Авто».

    [Ф] скил v8i-format: `App=Auto` и отсутствие ключа `App` означают одно
    и то же (тонкий клиент, `/AppAutoCheckMode`). Без этой нормализации
    запись с явным `App=Auto` в файле (обычное дело — так его пишет сама
    платформа) на нетронутом диалоге отличалась бы от данных пункта «Авто»
    (`None`) и `changes()` молча снимала бы App при каждом открытии-ОК.
    """  # noqa: RUF002
    if app is None or app.casefold() == "auto":
        return None
    return app


_APP_ITEMS = (("Авто", None), ("Тонкий клиент", "ThinClient"), ("Толстый клиент", "ThickClient"))


def _version_options(
    item: InfobaseItem, installations: Sequence[Installation], cell: VersionCell
) -> list[tuple[str, str | None]]:
    """Пункты выпадающего списка версий: «как установлено» + установленные.

    Если запрошенная версия (маска, неполный номер или версия, которой нет
    на машине) не совпадает буквально ни с одной установленной строкой,
    добавляется отдельный пункт с её точным значением. Без него нетронутый
    диалог не находил бы себе пункта с такими данными и откатывался бы
    к первому («как установлено»), а `changes()` восприняла бы это как
    решение пользователя снять `Version` — тот же класс молчаливой порчи,
    ради которого написан `replace_fragment` для `Connect`.

    Пункт «как установлено» получает действующую версию в скобках, если
    `Version` у записи нет вовсе (I6, круг правок 1): без Version секция
    всё равно резолвится в конкретную версию ([Ф] T-05.5 — DefaultVersion
    или максимум установленной), и задача 8 эту версию показывала. Голая
    надпись «как установлено» без неё — шаг назад, а не только смена виджета.

    Кроме WEB (круг правок 2, item 5, и круг правок 3, мелочь 1): там
    `version_cell` всегда отдаёт `cell.text == "веб"` (Version на запуск
    веб-базы не влияет вовсе), и подстановка без разбора читалась бы как
    «как установлено (веб)» или, для пункта запрошенной-но-не-подошедшей
    версии ниже, как голое «веб» вместо самой версии — оба места читают
    `cell.text` только через `display_text`, уже отфильтрованный по WEB.
    """  # noqa: RUF002
    display_text = cell.text if item.kind is not ConnectKind.WEB else ""
    default_label = "как установлено"
    if item.requested_version is None and display_text:
        default_label = f"{default_label} ({display_text})"
    options: list[tuple[str, str | None]] = [(default_label, None)]
    seen: set[str | None] = {None}
    for installation in installations:
        value = str(installation.version)
        if value in seen:
            continue
        seen.add(value)
        options.append((value, value))
    if item.requested_version is not None and item.requested_version not in seen:
        options.append((display_text or item.requested_version, item.requested_version))
    return options


class InfobaseDialog(QDialog):
    def __init__(
        self,
        item: InfobaseItem | None,
        *,
        groups: Sequence[str],
        installations: Sequence[Installation],
        cfg_rules: Sequence[DefaultVersionRule],
        parent: QWidget | None = None,
        choose_directory: Callable[[], str] = browse_for_directory,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._choose_directory = choose_directory
        self.setWindowTitle(f"Свойства — {item.name}" if item is not None else "Добавление базы")
        # Перетащить каталог можно и в диалог правки (сменить путь файловой
        # базы), и в диалог добавления (задача 10) — accept_directory сама
        # переключает вид на FILE, так что режим здесь роли не играет.
        self.setAcceptDrops(True)

        self._name = QLineEdit(item.name if item is not None else "")

        self._file_path = QLineEdit()
        self._server = QLineEdit()
        self._ref = QLineEdit()
        self._url = QLineEdit()
        self._init_placement(item)

        # Кнопка «Обзор…» — пробел плана, найденный ревью задачи 10: спека
        # §3.1 требует «обзор каталога и drag&drop каталога», план заявил
        # только второе. Живёт в одной строке формы с полем пути — единственное  # noqa: RUF003
        # место, где строка формы (для видимости через setRowVisible) и поле
        # значения (для чтения .text()) расходятся: `_kind_row_widgets` ниже
        # несёт контейнер, `_kind_rows` — сам QLineEdit, как и для остальных
        # полей.
        self._browse_button = QPushButton("Обзор…")
        self._browse_button.clicked.connect(self._browse_for_directory)
        file_row = QWidget()
        file_row_layout = QHBoxLayout(file_row)
        file_row_layout.setContentsMargins(0, 0, 0, 0)
        file_row_layout.addWidget(self._file_path)
        file_row_layout.addWidget(self._browse_button)

        placement_widgets = self._placement_widgets()
        row_widgets: dict[str, QWidget] = {**placement_widgets, "File": file_row}
        self._kind_rows: dict[ConnectKind, list[tuple[str, QLineEdit]]] = {
            kind: [(label, placement_widgets[name]) for label, name in spec]
            for kind, spec in _PLACEMENT_SPEC.items()
        }
        self._kind_row_widgets: dict[ConnectKind, list[QWidget]] = {
            kind: [row_widgets[name] for _label, name in spec]
            for kind, spec in _PLACEMENT_SPEC.items()
        }

        self._kind_box = QComboBox()
        for kind in _KIND_CHOICES:
            self._kind_box.addItem(BADGE_LABELS[kind], kind)
        if item is not None and item.kind not in _PLACEMENT_KEYS:
            # Запись, чей вид мы не распознали (UNKNOWN), — пункт списка
            # с её собственным видом, чтобы «вид не менялся» совпадало  # noqa: RUF003
            # с фактическим состоянием диалога сразу после открытия (I7/M9,  # noqa: RUF003
            # см. докстринг модуля), а не откатывалось на первый обычный  # noqa: RUF003
            # пункт (FILE).
            self._kind_box.addItem(BADGE_LABELS[item.kind], item.kind)
        initial_kind = item.kind if item is not None else ConnectKind.FILE
        kind_index = self._kind_box.findData(initial_kind)
        self._kind_box.setCurrentIndex(kind_index if kind_index >= 0 else 0)

        # `groups` несёт нормализованные пути (без ведущего слэша, корень —
        # «/»: то же самое, что даёт normalize_folder), а `item.folder` —  # noqa: RUF003
        # сырое значение файла (с ведущим слэшем для вложенных путей,  # noqa: RUF003
        # [Ф] render_folder). Сравнение и поиск текущего пункта идут по
        # normalize_folder с обеих сторон — иначе расхождение форм задевало  # noqa: RUF003
        # бы каждую вложенную запись, а не только настоящую сироту без  # noqa: RUF003
        # секции-группы (I7, круг правок 1). Для новой записи (item is None)
        # «текущей» папки нет — по умолчанию корень.
        folder_options = list(groups)
        current_folder = normalize_folder(item.folder) if item is not None else ROOT
        if current_folder not in folder_options:
            folder_options.append(current_folder)
        self._folder = QComboBox()
        self._folder.addItems(folder_options)
        self._folder.setCurrentText(current_folder)

        form = QFormLayout()
        form.addRow("Имя", self._name)
        form.addRow("Размещение", self._kind_box)
        for kind, spec in _PLACEMENT_SPEC.items():
            for (label, _name), widget in zip(spec, self._kind_row_widgets[kind], strict=True):
                form.addRow(label, widget)
        form.addRow("Группа", self._folder)
        self._form = form
        self._update_kind_visibility()
        self._kind_box.currentIndexChanged.connect(self._update_kind_visibility)

        if item is not None:
            cell = version_cell(item, installations, cfg_rules)
            self._version = QComboBox()
            for text, data in _version_options(item, installations, cell):
                self._version.addItem(text, data)
            version_index = self._version.findData(item.requested_version)
            self._version.setCurrentIndex(version_index if version_index >= 0 else 0)
            self._version_hint = QLabel(cell.hint or "")
            self._version_hint.setWordWrap(True)

            self._app = QComboBox()
            for text, data in _APP_ITEMS:
                self._app.addItem(text, data)
            app_index = self._app.findData(_app_key(item.app))
            if app_index < 0:
                # Незнакомое значение App (не Auto/ThinClient/ThickClient) —
                # сохраняем его как есть отдельным пунктом, а не подменяем  # noqa: RUF003
                # молча одним из трёх известных.
                self._app.addItem(item.app or "", item.app)
                app_index = self._app.count() - 1
            self._app.setCurrentIndex(app_index)
            self._initial_app = self._app.currentData()

            self._os_auth = QCheckBox()
            self._os_auth.setChecked(_typed_value(item.keys, "WA") == "1")
            self._initial_wa = "1" if self._os_auth.isChecked() else None

            form.addRow("Версия", self._version)
            form.addRow("", self._version_hint)
            form.addRow("Клиент", self._app)
            form.addRow("Аутентификация ОС", self._os_auth)  # noqa: RUF001

            self._rows = other_keys(item)
            self._table = QTableWidget(len(self._rows), 2)
            self._table.setHorizontalHeaderLabels(["Ключ", "Значение"])
            self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            for row, (name, value) in enumerate(self._rows):
                self._table.setItem(row, 0, QTableWidgetItem(name))
                self._table.setItem(row, 1, QTableWidgetItem(value))

        self._buttons = russian_button_box(ButtonKind.OK, ButtonKind.CANCEL)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        self._ok_button = next(
            button
            for button in self._buttons.buttons()
            if self._buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole
        )
        # Пояснение к неактивной «ОК» — рядом с ней, а не окном после клика  # noqa: RUF003
        # (решение заказчика: отказ показывается раньше, до действия).
        self._required_hint = QLabel()
        self._required_hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if item is not None:
            layout.addWidget(QLabel("Прочие ключи секции (только чтение)"))
            layout.addWidget(self._table)
        layout.addWidget(self._required_hint)
        layout.addWidget(self._buttons)

        self._name.textChanged.connect(self._refresh_ok_state)
        for field in self._placement_widgets().values():
            field.textChanged.connect(self._refresh_ok_state)
        self._kind_box.currentIndexChanged.connect(self._refresh_ok_state)
        self._refresh_ok_state()

    @classmethod
    def for_new(
        cls,
        *,
        groups: Sequence[str],
        installations: Sequence[Installation],
        cfg_rules: Sequence[DefaultVersionRule],
        parent: QWidget | None = None,
        choose_directory: Callable[[], str] = browse_for_directory,
    ) -> "InfobaseDialog":
        """Диалог добавления записи: то же окно, без исходной записи.

        Строку соединения строит `build_connect` при принятии (`new_record`),
        а не здесь — значений для неё ещё нет, пока пользователь не заполнил
        форму.
        """  # noqa: RUF002
        return cls(
            None,
            groups=groups,
            installations=installations,
            cfg_rules=cfg_rules,
            parent=parent,
            choose_directory=choose_directory,
        )

    def _placement_widgets(self) -> dict[str, QLineEdit]:
        return {"File": self._file_path, "Srvr": self._server, "Ref": self._ref, "ws": self._url}

    def _browse_for_directory(self) -> None:
        """Обработчик «Обзор…» — то же самое, что и drag&drop одного каталога.

        Пустая строка от `self._choose_directory()` — пользователь отменил
        выбор (контракт `QFileDialog.getExistingDirectory`, см.
        `browse_for_directory`): поле не трогается, тем же способом, что
        и «нет каталога в mime-данных» у `dropped_directory`.
        """  # noqa: RUF002
        path = self._choose_directory()
        if path:
            self.accept_directory(path)

    def _init_placement(self, item: InfobaseItem | None) -> None:
        """Собрать поля размещения из фрагментов, реально найденных в Connect.

        `_placement_entries` — источник для точечной правки (`_placement_fields`,
        только те, что действительно нашлись) — C3, круг правок 1:
        `classify_connect` определяет SERVER по наличию любого из Srvr/Ref,
        второй фрагмент может отсутствовать, и просить `replace_fragment`
        заменить несуществующий фрагмент значило бы поднять `KeyError`,
        который `changes()` никак не ловит. `item is None` (диалог
        добавления) — править точечно нечего, поля остаются обычными
        пустыми и полностью редактируемыми.
        """
        self._placement_entries: list[tuple[str, str, QLineEdit, bool]] = []
        self._placement_raw: dict[str, str] = {}
        if item is None:
            return
        widgets = self._placement_widgets()
        connect = item.connect or ""
        for label, fragment_name in _PLACEMENT_SPEC.get(item.kind, ()):
            field = widgets[fragment_name]
            raw = raw_fragment_value(connect, fragment_name)
            if raw is None:
                field.setReadOnly(True)
                field.setPlaceholderText(_UNPARSED_PLACEMENT_HINT)
                self._placement_entries.append((label, fragment_name, field, False))
                continue
            field.setText(raw)
            self._placement_raw[fragment_name] = raw
            self._placement_entries.append((label, fragment_name, field, True))

    def _update_kind_visibility(self) -> None:
        """Показать поля размещения только выбранного вида — остальные скрыты.

        Виджеты общие на все три вида: так сеттеры (`set_file_path` и т. п.)
        остаются рабочими независимо от того, какой вид сейчас выбран,
        а строку соединения при смене вида собирает `build_connect` заново —
        поля лишь источник значений для неё. Переключаются `_kind_row_widgets`
        (то, что реально добавлено в форму), а не `_kind_rows` (поля значений):
        для `File` это разные объекты — строка формы несёт ещё и кнопку
        «Обзор…».
        """  # noqa: RUF002
        selected = self._kind_box.currentData()
        for kind, widgets in self._kind_row_widgets.items():
            visible = kind is selected
            for widget in widgets:
                self._form.setRowVisible(widget, visible)

    def _placement_fields(self) -> list[tuple[str, QLineEdit]]:
        """Пары «имя фрагмента Connect, поле» — только то, что реально нашлось."""
        return [
            (name, field) for _label, name, field, editable in self._placement_entries if editable
        ]

    def _placement_violation(self) -> tuple[str, str] | None:
        """Метка поля и запрещённый символ, добавленный правкой, — `None`, если

        всё чисто. Сравнение — с сырым значением на момент открытия: символ,
        который уже был в поле (например, экранированная пара `""`), —
        не ввод пользователя, трогать его нельзя. Действует только для
        точечной правки существующей записи БЕЗ смены вида — при смене вида
        или для новой записи проверяет `_violation` другим путём (весь
        текст — ввод пользователя, сравнивать не с чем).

        Круг правок 2, item 3: `;` запрещён наравне с `"`. `_edited_connect`
        применяет `replace_fragment` последовательно к промежуточной строке —
        `;`, вписанный в одно поле размещения, создаёт для СЛЕДУЮЩЕГО
        `replace_fragment` новый (чужой) фрагмент с тем же именем в уже
        изменённом тексте: второй `replace_fragment` находит и правит не то,
        что должно, даже если своё поле пользователь не трогал. `"` запрещён
        по прежней причине (I4, круг правок 1): экранирование кавычек
        в Connect — [Д], не [Ф] (скил v8i-format), удвоить самим — записать
        в чужой файл догадку.
        """  # noqa: RUF002
        for label, name, field, editable in self._placement_entries:
            if not editable:
                continue
            current = field.text()
            if current == self._placement_raw[name]:
                continue
            for char in _FORBIDDEN_PLACEMENT_CHARACTERS:
                if char in current:
                    return label, char
        return None

    def _violation(self) -> tuple[str, str] | None:
        """Запрещённый символ в полях размещения — общая проверка на «ОК».

        Вид не менялся — точечная правка существующей записи, сравнение
        с исходным сырым значением (`_placement_violation`, задача 9):
        уже бывшая в файле экранированная пара `""` — не ввод пользователя.
        Вид сменили или это новая запись (`for_new`) — вся строка собирается
        заново `build_connect`, сравнивать значение не с чем: весь текст
        полей выбранного вида — ввод пользователя целиком.
        """  # noqa: RUF002
        item = self._item
        if item is not None and self._kind_box.currentData() is item.kind:
            return self._placement_violation()
        for label, field in self._kind_rows.get(self._kind_box.currentData(), []):
            text = field.text()
            for char in _FORBIDDEN_PLACEMENT_CHARACTERS:
                if char in text:
                    return label, char
        return None

    def _required_placement_fields(self) -> list[tuple[str, QLineEdit]]:
        """Поля размещения выбранного вида, которые пользователь обязан заполнить.

        Нередактируемое поле исключается: `_init_placement` делает таким то,
        чей фрагмент в `Connect` не нашёлся вовсе (C3, круг правок 1 задачи 9),
        и требовать заполнить его значило бы запереть «ОК» навсегда у записи,
        которую пользователь открыл ради правки версии или группы. Такая
        запись уже лежит в файле — пустого размещения мы ей не создаём,
        мы её просто не трогаем в этой части.

        Вид `UNKNOWN` полей размещения не имеет вовсе (`_PLACEMENT_SPEC`),
        и список получается пустым — правка версии/клиента/группы у нераз-
        обранной записи остаётся возможной.
        """  # noqa: RUF002
        return [
            (label, field)
            for label, field in self._kind_rows.get(self._kind_box.currentData(), [])
            if not field.isReadOnly()
        ]

    def _empty_placement(self) -> list[str]:
        """Метки незаполненных обязательных полей размещения."""
        return [
            label
            for label, field in self._required_placement_fields()
            if not field.text().strip()
        ]

    def _empty_required(self) -> list[str]:
        """Метки всех незаполненных обязательных полей — имя и размещение.

        Ре-ревью, N3: имя было защищено только `validate_section_name`
        в `services`, то есть отказом **после** нажатия «ОК». Внутри одного
        диалога получалось противоречие: поле пути запирало кнопку до клика,
        поле имени — нет. Решение заказчика 09.08.2026 «отказ показывается
        до действия» действует на оба поля одинаково (спека §3.1).

        Имя идёт первым: оно и стоит первым в форме, и порядок перечисления
        в пояснении должен совпадать с порядком полей на экране.
        """  # noqa: RUF002
        missing = [] if self._name.text().strip() else ["Имя"]
        return missing + self._empty_placement()

    def _refresh_ok_state(self) -> None:
        """«ОК» неактивна, пока обязательные поля не заполнены, — с пояснением рядом.

        Финальное ревью, I8: `_on_accept` проверял только запрещённые символы,
        и `Ctrl+N` → задано только имя → «ОК» давал запись с пустым `File=""`,
        уходившую в файл, общий со штатным стартером. Размещение не было
        защищено ничем — пробел спеки, а не только кода (§3.1 дополнена).
        Ре-ревью N3 добавило сюда же имя: его защита существовала, но
        срабатывала после клика (см. `_empty_required`).

        Решение заказчика: отказ показывается **раньше, до действия**, —
        неактивный элемент, объясняющий себя, а не сообщение после клика.
        Тот же приём, что у неактивных пунктов меню для общего списка (§3.2).

        Проверка идёт по `strip()`: имя, путь или адрес из одних пробелов —
        то же самое пустое поле, только незаметное глазу (`validate_section_name`
        имя из пробелов тоже отвергает).

        `services` при этом остаётся вторым, самостоятельным рубежом:
        `_apply_new_infobase`/`_apply_properties` достижимы напрямую, в обход
        кнопки, и `Workspace` отвергает пустое имя сам.
        """  # noqa: RUF002
        empty = self._empty_required()
        self._ok_button.setEnabled(not empty)
        if not empty:
            self._required_hint.setText("")
            return
        fields = ", ".join(f"«{label}»" for label in empty)
        self._required_hint.setText(f"Заполните: {fields}")

    def _on_accept(self) -> None:
        """Заблокировать «ОК», если правка вписала запрещённый символ."""  # noqa: RUF002
        violation = self._violation()
        if violation is not None:
            label, char = violation
            QMessageBox.warning(
                self,
                "Недопустимый символ",
                f"Поле «{label}»: символ ({char}) нельзя записать в строку "
                "соединения — он несёт смысл в её синтаксисе, и неверная "
                "догадка испортит запись. Уберите его и повторите.",  # noqa: RUF001
            )
            return
        self.accept()

    def name_text(self) -> str:
        return self._name.text()

    def placement_text(self) -> str:
        item = self._item
        return connection_path(item).text if item is not None else ""

    def other_rows(self) -> list[tuple[str, str]]:
        """Содержимое таблицы прочих ключей — читается с виджета, не с списка.

        Финальное ревью, I6: раньше метод отдавал `list(self._rows)` —
        тот же список, который `__init__` только собирается разложить
        по ячейкам. Единственный путь значения на экран (`QTableWidgetItem`)
        не проверялся ничем: подмена значения при заполнении таблицы не
        роняла ни один тест маскировки, и `PPasswd` — зашифрованный пароль
        прокси, который спека §3.1 требует не показывать, — выводился бы
        открытым текстом. Читаем с виджета: тогда сторож смотрит туда,
        куда смотрит пользователь.
        """  # noqa: RUF002
        if self._item is None:
            return []
        rows: list[tuple[str, str]] = []
        for row in range(self._table.rowCount()):
            name = self._table.item(row, 0)
            value = self._table.item(row, 1)
            rows.append((name.text() if name else "", value.text() if value else ""))
        return rows

    def version_hint(self) -> str:
        if self._item is None:
            return ""
        return f"{self._version.currentText()} {self._version_hint.text()}".strip()

    def button_labels(self) -> list[str]:
        """Подписи кнопок диалога — тест ревью задачи 8: подмена не забыта."""
        return [button.text() for button in self._buttons.buttons()]

    def groups_shown(self) -> list[str]:
        """Пути групп в выпадающем списке — проверка проброса параметра `groups`."""
        return [self._folder.itemText(i) for i in range(self._folder.count())]

    def accepts(self) -> bool:
        """Активна ли «ОК» — то, что видит пользователь до клика."""  # noqa: RUF002
        return self._ok_button.isEnabled()

    def required_hint(self) -> str:
        """Пояснение рядом с «ОК». Пустая строка — пояснять нечего.

        Названо не `placement_hint`: с N3 пояснение говорит и про имя,
        и про размещение, а имя частью размещения не является.
        """  # noqa: RUF002
        return self._required_hint.text()

    def kind_change_warning(self) -> str | None:
        """Что пропадёт при смене вида размещения. `None` — вид не менялся

        (в т. ч. всегда для новой записи — `self._item is None`: терять
        нечего, Connect ещё не существует).

        Смена вида — не правка значения: `File=` и `Srvr=` не сосуществуют,
        строка соединения переписывается целиком (`build_connect`), и всё,
        что пользователь в неё положил, исчезает. Сказать об этом обязаны
        заранее, а не после записи.
        """  # noqa: RUF002
        item = self._item
        if item is None:
            return None
        selected = self._kind_box.currentData()
        if selected is item.kind:
            return None
        lost = extra_fragment_names(item.connect or "", _PLACEMENT_KEYS.get(item.kind, ()))
        if not lost:
            return None
        return (
            "Смена вида размещения перезапишет строку соединения. "
            f"Будут потеряны ключи: {', '.join(lost)}"
        )

    def new_record(self) -> tuple[str, str, str]:
        """Имя, строка соединения и группа — вход `Workspace.add_infobase`.

        Только для диалога добавления (`for_new`): диалог правки существующей
        записи новых записей не создаёт, `changes()` — его собственный путь
        записи.
        """  # noqa: RUF002
        connect = build_connect(
            self._kind_box.currentData(),
            file_path=self._file_path.text(),
            server=self._server.text(),
            ref=self._ref.text(),
            url=self._url.text(),
        )
        return self._name.text().strip(), connect, self._folder.currentText()

    def accept_directory(self, path: str) -> None:
        """Каталог, перетащённый на диалог: путь — в поле, имя — если оно пустое.

        Перетащить можно только каталог (`dragEnterEvent`/`dragMoveEvent`
        проверяют это заранее через `dropped_directory`), и он становится
        `File`-фрагментом файловой базы — единственный вид размещения, для
        которого каталог на диске задаёт значение однозначно. Переключение
        вида на FILE — то же самое, что выбрать его в `_kind_box` руками:
        для правки существующей серверной/веб-записи это смена вида, и она
        пройдёт через то же предупреждение (`kind_change_warning`) перед
        записью.
        """  # noqa: RUF002
        self.set_kind(ConnectKind.FILE)
        self._file_path.setText(path)
        if not self._name.text().strip():
            self._name.setText(Path(path).name)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        # Без явного accept здесь курсор Qt по умолчанию рисует «нельзя
        # бросить» на всём протяжении перемещения, и dropEvent может не
        # дойти вовсе — dragEnterEvent разрешает только самый первый момент
        # входа в область.
        if dropped_directory(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        directory = dropped_directory(event.mimeData())
        if directory is not None:
            self.accept_directory(directory)
            event.acceptProposedAction()

    # -- значения для тестов, в обход имитации ввода -----------------------
    #
    # M9 (круг правок 1): падают, если запрошенного пункта нет среди
    # предложенных диалогом, — вместо того, чтобы молча дописывать его.  # noqa: RUF003
    # Дописывание давало тесту выбрать то, чего настоящий виджет не предлагал
    # (тот же класс ошибки, что и I7 с несогласованной формой Folder).  # noqa: RUF003

    def set_name(self, value: str) -> None:
        self._name.setText(value)

    def set_folder(self, value: str) -> None:
        index = self._folder.findText(value)
        if index < 0:
            raise ValueError(f"диалог не предлагает группу «{value}»")
        self._folder.setCurrentIndex(index)

    def set_version(self, value: str | None) -> None:
        index = self._version.findData(value)
        if index < 0:
            raise ValueError(f"диалог не предлагает версию «{value}»")
        self._version.setCurrentIndex(index)

    def set_app(self, value: str | None) -> None:
        index = self._app.findData(value)
        if index < 0:
            raise ValueError(f"диалог не предлагает клиента «{value}»")
        self._app.setCurrentIndex(index)

    def set_os_auth(self, value: bool) -> None:
        self._os_auth.setChecked(value)

    def set_kind(self, value: ConnectKind) -> None:
        index = self._kind_box.findData(value)
        if index < 0:
            raise ValueError(f"диалог не предлагает вид размещения «{value}»")
        self._kind_box.setCurrentIndex(index)

    def set_file_path(self, value: str) -> None:
        self._file_path.setText(value)

    def set_server(self, value: str) -> None:
        self._server.setText(value)

    def set_ref(self, value: str) -> None:
        self._ref.setText(value)

    def set_url(self, value: str) -> None:
        self._url.setText(value)

    # -- что писать ----------------------------------------------------------

    def changes(self) -> tuple[dict[str, str | None], str | None]:
        """Что править в секции и новое имя. Пустая пара — трогать нечего.

        Только для диалога правки существующей записи: у диалога добавления
        (`self._item is None`) писать нечего этим путём — за него отвечает
        `new_record()`.
        """  # noqa: RUF002
        item = self._item
        if item is None:
            return {}, None
        changes: dict[str, str | None] = {}
        connect = self._connect_changes()
        if connect is not None and connect != item.connect:
            changes["Connect"] = connect
        version = self._version.currentData()
        if version != item.requested_version:
            changes["Version"] = version
        folder = self._folder.currentText()
        if folder != normalize_folder(item.folder):
            changes["Folder"] = folder
        app = self._app.currentData()
        if app != self._initial_app:
            changes["App"] = app
        wa = "1" if self._os_auth.isChecked() else None
        if wa != self._initial_wa:
            changes["WA"] = wa
        name = self._name.text().strip()
        return changes, (name if name != item.name else None)

    def _connect_changes(self) -> str | None:
        """Новое значение Connect для changes() — `None`, если не тронуто.

        Вид сменили — строка переписывается целиком `build_connect`
        (`kind_change_warning` предупреждает об этом заранее): точечная
        правка (`_edited_connect`) тут неприменима, `File=` и `Srvr=`
        не сосуществуют. Вид тот же — прежний точечный путь.
        """  # noqa: RUF002
        item = self._item
        if item is None:
            return None
        if self._kind_box.currentData() is not item.kind:
            return build_connect(
                self._kind_box.currentData(),
                file_path=self._file_path.text(),
                server=self._server.text(),
                ref=self._ref.text(),
                url=self._url.text(),
            )
        return self._edited_connect()

    def _edited_connect(self) -> str | None:
        """Строка соединения после правки полей размещения. `None` — не трогали.

        Точечная замена, а не сборка заново: `replace_fragment` сохраняет
        порядок, пробелы, кавычки и все фрагменты, которых мы не понимаем.
        `_placement_fields` уже отфильтрован до реально найденных фрагментов
        (C3) — `replace_fragment` здесь не может поднять `KeyError`.
        """  # noqa: RUF002
        item = self._item
        source = (item.connect or "") if item is not None else ""
        result = source
        for name, field in self._placement_fields():
            result = replace_fragment(result, name, field.text())
        return None if result == source else result
