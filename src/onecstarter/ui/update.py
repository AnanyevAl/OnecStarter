"""Уведомление о новой версии и установка по кнопке (T-25).

Спека — docs/superpowers/specs/2026-10-20-v323-block3-update-check-design.md.

Сеть и файлы — `services/update.py`; здесь потоки, полоса над разделами и контроллер,
который решает, когда спрашивать согласие, когда проверять и когда запускать установщик.
Запросов без согласия нет (§4 требований): фоновая проверка — только при
`check_updates is True`, ручная — по кнопке пользователя.
"""  # noqa: RUF002

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QWidget

from onecstarter.domain.update import Release, is_newer
from onecstarter.services.errors import UpdateError
from onecstarter.services.update import HttpGet, download_verified, fetch_latest
from onecstarter.ui.settings_store import SettingsStore

__all__ = ["UpdateBanner", "UpdateChecker", "UpdateController", "UpdateDownloader"]

_log = logging.getLogger(__name__)

UP_TO_DATE = "Установлена последняя версия"
FOUND = "Вышла версия {version}"
FAILED = "Не удалось проверить: {reason}"  # noqa: RUF001
CHECKING = "Проверка…"
DOWNLOADING = "Скачивание версии {version}…"


def _spawn_daemon(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


def _open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class UpdateChecker(QObject):
    """Проверка последнего выпуска в фоне; результат — одним из трёх сигналов."""

    found = Signal(object)  # Release
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(
        self,
        current_version: str,
        http_get: HttpGet,
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._current = current_version
        self._http_get = http_get
        self._spawn = spawn

    def start(self) -> None:
        self._spawn(self._run)

    def _run(self) -> None:
        try:
            release = fetch_latest(self._http_get)
        except UpdateError as error:
            self.failed.emit(str(error))
            return
        if is_newer(release.version, self._current):
            self.found.emit(release)
        else:
            self.up_to_date.emit()


class UpdateDownloader(QObject):
    """Скачивание установщика с проверкой SHA-256 в фоне."""  # noqa: RUF002

    ready = Signal(object)  # Path
    failed = Signal(str)

    def __init__(
        self,
        directory: Path,
        http_get: HttpGet,
        *,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._directory = directory
        self._http_get = http_get
        self._spawn = spawn

    def start(self, release: Release) -> None:
        self._spawn(lambda: self._run(release))

    def _run(self, release: Release) -> None:
        try:
            path = download_verified(release, self._directory, self._http_get)
        except UpdateError as error:
            self.failed.emit(str(error))
            return
        self.ready.emit(path)


class UpdateBanner(QFrame):
    """Полоса над разделами: «Вышла версия X · Установить · Что нового · ×»."""  # noqa: RUF002

    install_requested = Signal()

    def __init__(
        self,
        *,
        open_url: Callable[[str], None] = _open_url,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("UpdateBanner")
        self._open_url = open_url
        self._release: Release | None = None
        self._label = QLabel()
        self._install = QPushButton("Установить")
        self._install.setAutoDefault(False)
        self._install.clicked.connect(self.install_requested)
        self._notes = QPushButton("Что нового")
        self._notes.setAutoDefault(False)
        self._notes.clicked.connect(self._open_notes)
        self._close = QToolButton()
        self._close.setText("×")  # noqa: RUF001
        self._close.setToolTip("Скрыть до следующего запуска")
        self._close.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._install)
        layout.addWidget(self._notes)
        layout.addWidget(self._close)
        self.hide()

    def show_release(self, release: Release, *, installable: bool) -> None:
        self._release = release
        self._label.setText(FOUND.format(version=release.version))
        self._install.setVisible(installable)
        self._install.setEnabled(True)
        self._notes.setVisible(True)
        self.show()

    def show_downloading(self) -> None:
        if self._release is not None:
            self._label.setText(DOWNLOADING.format(version=self._release.version))
        self._install.setEnabled(False)

    def show_error(self, reason: str) -> None:
        self._label.setText(f"Обновление не установлено: {reason}")
        self._install.setEnabled(True)
        self.show()

    def text(self) -> str:
        return self._label.text()

    def install_button(self) -> QPushButton:
        return self._install

    def notes_button(self) -> QPushButton:
        return self._notes

    def close_button(self) -> QToolButton:
        return self._close

    def _open_notes(self) -> None:
        if self._release is not None:
            self._open_url(self._release.page_url)


class UpdateController(QObject):
    """Согласие, проверка при старте и вручную, установка после подтверждения выхода."""

    def __init__(
        self,
        store: SettingsStore,
        banner: UpdateBanner,
        checker: UpdateChecker,
        downloader: UpdateDownloader,
        *,
        installable: bool,
        ask_consent: Callable[[], bool],
        confirm_quit: Callable[[], bool],
        launch: Callable[[Path], None],
        quit_app: Callable[[], None],
        on_status: Callable[[str], None] = lambda _text: None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._banner = banner
        self._checker = checker
        self._downloader = downloader
        self._installable = installable
        self._ask_consent = ask_consent
        self._confirm_quit = confirm_quit
        self._launch = launch
        self._quit_app = quit_app
        self._on_status = on_status
        self._manual = False
        self._release: Release | None = None
        checker.found.connect(self._on_found)
        checker.up_to_date.connect(self._on_up_to_date)
        checker.failed.connect(self._on_failed)
        banner.install_requested.connect(self._install)
        downloader.ready.connect(self._on_ready)
        downloader.failed.connect(banner.show_error)

    def start_on_launch(self, *, window_shown: bool) -> None:
        """Проверка при старте — только с согласия; вопрос — один раз и при видимом окне."""  # noqa: RUF002
        consent = self._store.settings.check_updates
        if consent is None:
            if not window_shown:
                return
            consent = self._ask_consent()
            self._store.update(check_updates=consent)
        if consent:
            self._manual = False
            self._checker.start()

    def check_now(self) -> None:
        """Кнопка «Проверить обновления» — работает при любом значении согласия."""
        self._manual = True
        self._on_status(CHECKING)
        self._checker.start()

    def _on_found(self, release: Release) -> None:
        self._release = release
        self._banner.show_release(
            release, installable=self._installable and release.setup_url is not None
        )
        if self._manual:
            self._on_status(FOUND.format(version=release.version))

    def _on_up_to_date(self) -> None:
        if self._manual:
            self._on_status(UP_TO_DATE)

    def _on_failed(self, reason: str) -> None:
        # Фоновая проверка молчит: окно с ошибкой сети на каждом старте без сети  # noqa: RUF003
        # было бы наказанием за согласие. Причина — в журнал.
        _log.warning("проверка обновлений не удалась: %s", reason)
        if self._manual:
            self._on_status(FAILED.format(reason=reason))

    def _install(self) -> None:
        if self._release is None:
            return
        self._banner.show_downloading()
        self._downloader.start(self._release)

    def _on_ready(self, path: Path) -> None:
        # Обычное подтверждение выхода (серверы, CLI EDT): отказ — установщик
        # не запускается, скачанный файл остаётся до следующей попытки.
        if not self._confirm_quit():
            if self._release is not None:
                self._banner.show_release(self._release, installable=self._installable)
            return
        self._launch(path)
        self._quit_app()
