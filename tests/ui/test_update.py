"""Уведомление о новой версии и установка по кнопке (T-25) — без сети и процессов."""  # noqa: RUF002

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from onecstarter.domain.update import Release
from onecstarter.ui.settings_store import SettingsStore
from onecstarter.ui.update import (
    UpdateBanner,
    UpdateChecker,
    UpdateController,
    UpdateDownloader,
)

_SYNC = lambda task: task()  # noqa: E731 — синхронный «поток» для детерминизма
SETUP = b"MZ fake installer"
GOOD_DIGEST = "sha256:" + hashlib.sha256(SETUP).hexdigest()


def _release_json(version: str, digest: str | None = GOOD_DIGEST) -> bytes:
    asset: dict[str, Any] = {
        "name": f"OneCStarter-{version}-setup.exe",
        "browser_download_url": "https://example/setup.exe",
    }
    if digest is not None:
        asset["digest"] = digest
    return json.dumps(
        {
            "tag_name": f"v{version}",
            "html_url": f"https://example/releases/v{version}",
            "assets": [asset],
        }
    ).encode()


class Net:
    """Фейковая сеть: ответ API и байты установщика; считает запросы."""

    def __init__(self, latest: str = "3.2.4", digest: str | None = GOOD_DIGEST) -> None:
        self.latest = latest
        self.digest = digest
        self.fail = False
        self.asked: list[str] = []

    def get(self, url: str) -> bytes:
        self.asked.append(url)
        if self.fail:
            raise OSError("нет сети")
        if url.endswith("setup.exe"):
            return SETUP
        return _release_json(self.latest, self.digest)


class Rig:
    def __init__(
        self,
        tmp_path: Path,
        qtbot: Any,
        *,
        consent: bool | None = None,
        answer: bool = True,
        installable: bool = True,
        confirm: bool = True,
        net: Net | None = None,
    ) -> None:
        self.net = net or Net()
        self.store = SettingsStore(tmp_path / "settings.json")
        if consent is not None:
            self.store.update(check_updates=consent)
        self.asked_consent = 0
        self.launched: list[Path] = []
        self.quits = 0
        self.statuses: list[str] = []
        self.opened: list[str] = []
        self.banner = UpdateBanner(open_url=self.opened.append)
        qtbot.addWidget(self.banner)

        def ask() -> bool:
            self.asked_consent += 1
            return answer

        def quit_app() -> None:
            self.quits += 1

        self.controller = UpdateController(
            self.store,
            self.banner,
            UpdateChecker("3.2.3", self.net.get, spawn=_SYNC),
            UpdateDownloader(tmp_path / "update", self.net.get, spawn=_SYNC),
            installable=installable,
            ask_consent=ask,
            confirm_quit=lambda: confirm,
            launch=self.launched.append,
            quit_app=quit_app,
            on_status=self.statuses.append,
        )


@pytest.fixture
def rig_factory(tmp_path: Path, qtbot: Any) -> Callable[..., Rig]:
    return lambda **kwargs: Rig(tmp_path, qtbot, **kwargs)


# --- полоса ------------------------------------------------------------------


def _release(version: str = "3.2.4") -> Release:
    return Release(version, "https://example/page", "s-setup.exe", "https://example/s", GOOD_DIGEST)


def test_banner_offers_install_only_for_installed_copy(qtbot: Any) -> None:
    banner = UpdateBanner(open_url=lambda _url: None)
    qtbot.addWidget(banner)
    banner.show_release(_release(), installable=True)
    assert not banner.isHidden()
    assert "3.2.4" in banner.text()
    assert not banner.install_button().isHidden()
    banner.show_release(_release(), installable=False)
    assert banner.install_button().isHidden()


def test_banner_notes_open_the_release_page_and_close_hides(qtbot: Any) -> None:
    opened: list[str] = []
    banner = UpdateBanner(open_url=opened.append)
    qtbot.addWidget(banner)
    banner.show_release(_release(), installable=False)
    banner.notes_button().click()
    assert opened == ["https://example/page"]
    banner.close_button().click()
    assert banner.isHidden()


def test_banner_starts_hidden(qtbot: Any) -> None:
    banner = UpdateBanner(open_url=lambda _url: None)
    qtbot.addWidget(banner)
    assert banner.isHidden()


# --- согласие и проверка при старте --------------------------------------------


def test_first_start_asks_and_yes_checks(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(answer=True)
    rig.controller.start_on_launch(window_shown=True)
    assert rig.asked_consent == 1
    assert rig.store.settings.check_updates is True
    assert rig.net.asked  # проверка ушла
    assert not rig.banner.isHidden()


def test_first_start_no_saves_refusal_and_does_not_check(rig_factory: Callable[..., Rig]) -> None:
    """Ответ «Нет» — ни одного запроса (обещание §4 требований)."""
    rig = rig_factory(answer=False)
    rig.controller.start_on_launch(window_shown=True)
    assert rig.store.settings.check_updates is False
    assert rig.net.asked == []


def test_refusal_is_remembered(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(consent=False)
    rig.controller.start_on_launch(window_shown=True)
    assert rig.asked_consent == 0
    assert rig.net.asked == []


def test_hidden_start_neither_asks_nor_checks(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory()
    rig.controller.start_on_launch(window_shown=False)
    assert rig.asked_consent == 0
    assert rig.store.settings.check_updates is None
    assert rig.net.asked == []


def test_consent_given_checks_without_asking(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(consent=True)
    rig.controller.start_on_launch(window_shown=True)
    assert rig.asked_consent == 0
    assert rig.net.asked


def test_background_failure_is_silent(rig_factory: Callable[..., Rig]) -> None:
    net = Net()
    net.fail = True
    rig = rig_factory(consent=True, net=net)
    rig.controller.start_on_launch(window_shown=True)
    assert rig.statuses == []
    assert rig.banner.isHidden()


# --- ручная проверка -------------------------------------------------------------


def test_manual_check_reports_up_to_date(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(consent=False, net=Net(latest="3.2.3"))
    rig.controller.check_now()
    assert rig.statuses[-1] == "Установлена последняя версия"
    assert rig.banner.isHidden()


def test_manual_check_reports_new_version(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(consent=False)
    rig.controller.check_now()
    assert rig.statuses[-1] == "Вышла версия 3.2.4"
    assert not rig.banner.isHidden()


def test_manual_check_reports_failure(rig_factory: Callable[..., Rig]) -> None:
    net = Net()
    net.fail = True
    rig = rig_factory(consent=False, net=net)
    rig.controller.check_now()
    assert rig.statuses[-1].startswith("Не удалось проверить:")  # noqa: RUF001


# --- установка ---------------------------------------------------------------------


def test_install_launches_after_quit_is_confirmed(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(consent=True)
    rig.controller.start_on_launch(window_shown=True)
    rig.banner.install_button().click()
    assert [path.name for path in rig.launched] == ["OneCStarter-3.2.4-setup.exe"]
    assert rig.launched[0].read_bytes() == SETUP
    assert rig.quits == 1


def test_install_declined_quit_does_not_launch(rig_factory: Callable[..., Rig]) -> None:
    rig = rig_factory(consent=True, confirm=False)
    rig.controller.start_on_launch(window_shown=True)
    rig.banner.install_button().click()
    assert rig.launched == []
    assert rig.quits == 0


def test_install_with_wrong_digest_never_launches(rig_factory: Callable[..., Rig]) -> None:
    """Несовпавший SHA-256 — установщик не запускается, полоса объясняет (T-25, §4)."""
    wrong = "sha256:" + hashlib.sha256(b"other").hexdigest()
    rig = rig_factory(consent=True, net=Net(digest=wrong))
    rig.controller.start_on_launch(window_shown=True)
    rig.banner.install_button().click()
    assert rig.launched == []
    assert rig.quits == 0
    assert "контрольная сумма" in rig.banner.text()
