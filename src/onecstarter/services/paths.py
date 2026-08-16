"""Арифметика путей секций-групп .v8i — общий источник для дерева и каскада.

**[Ф]** T-02.3 и скил v8i-format: у секции-группы `Folder` — путь родителя,
собственный путь группы = `Folder` + `/` + имя секции.

Знание о том, кто чей потомок, существует ровно в одном экземпляре. Копия
этой арифметики в модуле правок разъехалась бы с построением дерева, и записи
осиротели бы не от ошибки в алгоритме, а от рассинхронизации двух реализаций.

Сравнение путей посегментное и с учётом регистра. Посегментность обязательна:
`Клиенты` и `КлиентыVIP` совпадают как префиксы строк, но потомками друг другу
не приходятся. Регистр — **[Ф]** T-05.7: платформа сопоставляет `Folder`
с именем группы регистрозависимо; путь, не совпавший ни с одной группой,
она рисует отдельным неявным узлом, секцию для него не создаёт и регистр
`Folder` при перезаписях не нормализует.
"""  # noqa: RUF002

ROOT = "/"


def normalize_folder(folder: str | None) -> str:
    """Канонический вид пути: корень — `/`, иначе без обрамляющих слэшей.

    `/Клиенты`, `Клиенты` и `/Клиенты/` — один и тот же путь.
    """
    stripped = (folder or "").strip()
    return stripped.strip("/") or ROOT


def group_path(folder: str | None, name: str) -> str:
    """Собственный путь секции-группы: путь родителя плюс имя секции."""
    parent = normalize_folder(folder)
    return name if parent == ROOT else f"{parent}/{name}"


def is_inside(path: str, ancestor: str) -> bool:
    """Лежит ли `path` внутри `ancestor` (или равен ему). Сравнение посегментное.

    Корень — предок всего: внутри `ROOT` лежит любой путь.
    """
    if ancestor == ROOT:
        return True
    return path == ancestor or path.startswith(f"{ancestor}/")


def retarget(path: str, old_ancestor: str, new_ancestor: str) -> str:
    """Заменить предка в пути. Путь вне поддерева возвращается как есть.

    Предок-корень (`old_ancestor == ROOT`) означает замену пути целиком: весь
    `path` становится хвостом. Путь, равный самому предку, становится новым
    предком без хвоста.
    """
    if not is_inside(path, old_ancestor):
        return path
    if path == old_ancestor:
        return new_ancestor
    tail = path if old_ancestor == ROOT else path[len(old_ancestor) + 1 :]
    return tail if new_ancestor == ROOT else f"{new_ancestor}/{tail}"


def render_folder(path: str) -> str:
    """Записать путь в файл так, как это делает платформа: с ведущим слэшем.

    **[Ф]** мастер стартера пишет `Folder=/` для корня и `Folder=/<путь родителя>`
    для вложенных. Своя форма записи в том же файле рядом со штатной — лишний
    непроверенный риск на ровном месте.
    """  # noqa: RUF002
    return ROOT if path == ROOT else f"/{path}"
