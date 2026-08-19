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
