"""Цикл записи патча в ibases.v8i с переигрыванием при внешнем изменении.

Файл параллельно правит штатный 1cestart.exe и перезаписывает целиком
([Ф] скил v8i-format), поэтому расхождение снапшота — рядовое событие:
патч просто накладывается заново на свежее состояние. Чужие правки
в других секциях и ключах переживают запись; совпавший ключ получает
значение пользователя — он только что его задал.

Ретраев по PermissionError нет: файл не блокируется ни открытым стартером,
ни работающим клиентом ([Ф] T-02.4), поэтому отказ в доступе — настоящая
проблема (права, антивирус), и повторы её только спрячут.
"""  # noqa: RUF002

import os
from pathlib import Path

from onecstarter.config.atomic import (
    ExternalChangeError,
    atomic_write_if_unchanged,
    read_with_snapshot,
)
from onecstarter.config.v8i import LineBreakRejectedError, V8iDocument, parse_v8i, serialize_v8i
from onecstarter.services.edit import Patch, PatchResult, apply_patch
from onecstarter.services.errors import (
    ConcurrentEditError,
    EncodingRejectedError,
    InvalidRequestError,
)

__all__ = ["ConcurrentEditError", "EncodingRejectedError", "write_patch"]


def write_patch(
    path: Path, patch: Patch, new_id: str, attempts: int = 3
) -> tuple[bytes, PatchResult]:
    """Записать патч и сообщить, что он фактически сделал.

    Возвращает записанные байты и `PatchResult`: применился ли патч и каким
    стал ключ цели после применения. Вызывающий обязан смотреть на результат —
    у `REMOVE` цель могла исчезнуть или сменить ключ, а у `UPDATE` ключ
    меняется, когда записи дописывается `ID`.
    """  # noqa: RUF002
    for _ in range(attempts):
        try:
            data, snapshot = read_with_snapshot(path)
        except FileNotFoundError:
            created = _create(path, patch, new_id)
            if created is not None:
                return created
            continue
        document = parse_v8i(data)
        result = _apply(document, patch, new_id)
        payload = _serialize(document)
        if payload == data:
            # Патч не изменил ни байта (например, перестановка на своё же
            # место — находка ревью задачи 15): атомарная замена файла,
            # который может в этот момент держать штатный стартер, —
            # не бесплатная операция, и запускать её ради нулевого
            # результата незачем.
            return payload, result
        try:
            atomic_write_if_unchanged(path, payload, snapshot)
        except ExternalChangeError:
            continue
        return payload, result
    raise ConcurrentEditError(
        f"{path} меняется извне: патч не удалось применить за {attempts} попытки"
    )


def _create(
    path: Path, patch: Patch, new_id: str
) -> tuple[bytes, PatchResult] | None:
    """Создать файл эксклюзивно. `None` — кто-то создал его раньше нас."""  # noqa: RUF002
    document = parse_v8i(b"")
    result = _apply(document, patch, new_id)
    payload = _serialize(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        # Файл появился между нашей проверкой и созданием: его создал кто-то  # noqa: RUF003
        # другой, трогать его нельзя — цикл пойдёт обычным путём.  # noqa: RUF003
        return None
    except BaseException:
        # Эксклюзивное создание удалось, значит файл создали мы, и до нас его  # noqa: RUF003
        # не было. Убираем за собой, чтобы не оставить битый ibases.v8i там,
        # где раньше не было ничего.
        path.unlink(missing_ok=True)
        raise
    return payload, result


def _apply(document: V8iDocument, patch: Patch, new_id: str) -> PatchResult:
    """Применить патч, переводя исключение слоя `config` в исключение слоя `services`.

    `config.v8i` отказывает записи, которая подделала бы секции файла
    (перевод строки в имени или значении ключа) — но наружу слоя это должно
    выглядеть как одна иерархия `ServicesError`, а не голый `ValueError`
    из чужого слоя (инвариант `errors.py`). И основной цикл `write_patch`,
    и `_create` зовут `apply_patch` только через эту обёртку.
    """  # noqa: RUF002
    try:
        return apply_patch(document, patch, new_id)
    except LineBreakRejectedError as error:
        raise InvalidRequestError(str(error)) from error


def _serialize(document: V8iDocument) -> bytes:
    try:
        return serialize_v8i(document)
    except UnicodeEncodeError as error:
        raise EncodingRejectedError(
            "Файл прочитан в кодировке, в которую новый текст не записывается. "
            "Пересохранение в UTF-8 не выполняется: под фолбэковой кодировкой "
            "может лежать другая однобайтовая кодировка, и перекодирование "
            "необратимо испортит данные."
        ) from error
