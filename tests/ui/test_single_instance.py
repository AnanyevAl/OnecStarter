"""Канал «покажи окно» между экземплярами (T-39, спека 3.2.5 §6.2)."""

import gc
import time
import uuid
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

from onecstarter.ui.single_instance import ActivationServer, request_activation


def _name() -> str:
    return f"OneCStarter-test-{uuid.uuid4().hex}"


def test_request_reaches_the_running_instance(qtbot: Any) -> None:
    name = _name()
    calls: list[int] = []
    server = ActivationServer(name, lambda: calls.append(1))
    assert server.listening
    assert request_activation(name) is True
    qtbot.waitUntil(lambda: calls == [1], timeout=3000)


def test_without_a_running_instance_request_fails_within_timeout(qtbot: Any) -> None:
    started = time.monotonic()
    assert request_activation(_name(), connect_timeout_ms=300) is False
    assert time.monotonic() - started < 2.0


def test_unknown_message_is_ignored(qtbot: Any) -> None:
    name = _name()
    calls: list[int] = []
    server = ActivationServer(name, lambda: calls.append(1))
    socket = QLocalSocket()
    socket.connectToServer(name)
    assert socket.waitForConnected(1000)
    socket.write(b"hello\n")
    socket.waitForBytesWritten(1000)
    qtbot.wait(300)
    assert calls == []
    socket.disconnectFromServer()
    del server


def test_destroying_server_after_serving_does_not_crash(qtbot: Any) -> None:
    # Регрессия: лямбда-слот и deleteLater на дочернем сокете давали access violation
    # при уничтожении сервера, пока удаление сокета ещё в очереди.
    name = _name()
    calls: list[int] = []
    server = ActivationServer(name, lambda: calls.append(1))
    assert request_activation(name) is True
    deadline = time.monotonic() + 3
    while not calls and time.monotonic() < deadline:
        QCoreApplication.processEvents()
    assert calls == [1]
    del server
    gc.collect()
