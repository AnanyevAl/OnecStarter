"""Владелец настроек: единственный, кто пишет settings.json.

До вехи файл писал `ThemeController.set_mode` — целиком, из одного поля
(`Settings(theme=mode)`). С четырьмя полями это молча стирало бы соседние
настройки, поэтому писатель стал один (спека §6.2). Чтение и запись
остаются чистыми функциями `services/settings.py`; здесь — только текущее
состояние, сигнал и обработка отказа записи.

Автозапуск через store не ходит: его истина — реестр (спека §3.1).
"""  # noqa: RUF002

from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from onecstarter.services.settings import Settings, load_settings, save_settings


class SettingsStore(QObject):
    changed = Signal()

    def __init__(self, path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._settings = load_settings(path)
        self.last_save_error: str | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def path(self) -> Path:
        """Куда пишутся настройки — разделу «Настройки» для подписи."""
        return self._path

    def update(self, **changes: Any) -> None:
        """Изменить поля и записать файл целиком.

        `replace`, а не сборка нового `Settings` из переданного: собранный
        заново объект вернул бы к дефолтам всё, что не назвали, — ровно тот
        дефект, ради которого писатель стал один.

        Значение применяется даже при отказе записи: пользователь его
        выбрал, и откатывать выбор из-за недоступного файла значило бы
        спорить с ним молча. Причина уходит в `last_save_error`, показать
        её обязан слой представления.
        """  # noqa: RUF002
        self._settings = replace(self._settings, **changes)
        try:
            save_settings(self._path, self._settings)
            self.last_save_error = None
        except OSError as error:
            self.last_save_error = f"Не удалось сохранить {self._path}: {error}"  # noqa: RUF001
        self.changed.emit()

    def store_quietly(self, **changes: Any) -> str | None:
        """Изменить поля и записать файл, НЕ испуская `changed` (T-38).

        Для того, что меняется часто и ни на что вокруг не влияет, — ширин
        колонок. На `changed` подписано переобнаружение установок EDT
        (`ui/app.py`, `edt_monitor.discover_now`): `update` на каждое
        перетаскивание колонки запускал бы обход дисков.

        Отказ записи возвращается текстом, а не кладётся в `last_save_error`:
        его показывает слой представления, а модальное окно в ответ на
        перетаскивание колонки хуже потерянной ширины (спека §2.2).
        """  # noqa: RUF002
        self._settings = replace(self._settings, **changes)
        try:
            save_settings(self._path, self._settings)
        except OSError as error:
            return f"Не удалось сохранить {self._path}: {error}"  # noqa: RUF001
        return None
