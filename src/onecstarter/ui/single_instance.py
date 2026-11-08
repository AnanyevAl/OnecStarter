"""Канал «покажи окно» между экземплярами программы (T-39, спека 3.2.5 §6.2).

Признак «уже запущено» — мьютекс (`platform_1c/instance_lock.py`); канал только
передаёт первому экземпляру просьбу поднять окно. Отказ открыть канал не мешает
работе: повторный запуск тогда не поднимет окно, но и второй экземпляр не запустит —
мьютекс держится.
"""

import logging
import time
from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

__all__ = ["ACTIVATE_MESSAGE", "ActivationServer", "request_activation"]

ACTIVATE_MESSAGE = b"activate\n"
_log = logging.getLogger(__name__)


class ActivationServer(QObject):
    def __init__(
        self, name: str, on_activate: Callable[[], None], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._on_activate = on_activate
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept)
        # На Windows (именованные каналы) это не очистка устаревшего канала  # noqa: RUF003
        # (вероятно, пустая операция, [?]); оставлено для симметрии, безвредно.
        QLocalServer.removeServer(name)
        if not self._server.listen(name):
            _log.warning("канал «покажи окно» не открыт: %s", self._server.errorString())

    @property
    def listening(self) -> bool:
        return self._server.isListening()

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.readyRead.connect(self._on_ready_read)
            socket.disconnected.connect(socket.deleteLater)
            self._read(socket)

    def _on_ready_read(self) -> None:
        # Связанный слот, не лямбда: замыкание на сокете роняет процесс при
        # уничтожении сервера, пока удаление сокета стоит в очереди.
        self._read(cast(QLocalSocket, self.sender()))

    def _read(self, socket: QLocalSocket) -> None:
        if not socket.canReadLine():
            return
        if bytes(socket.readLine().data()) == ACTIVATE_MESSAGE:
            self._on_activate()
        socket.disconnectFromServer()


def _send(socket: QLocalSocket, deadline: float) -> bool:
    """Записать сообщение и дождаться, пока оно целиком уйдёт в канал.

    Доставка считается по сигналу `bytesWritten`, а не по `bytesToWrite() == 0`:
    при обрыве канала Qt обнуляет буфер записи, и «пусто» не значит «доставлено».
    Цикл событий прокачивается: если сервер живёт в этом же потоке (тесты), Windows
    дописывает канал только в нём. Между процессами одного блокирующего ожидания
    хватает лишь при отзывчивом сервере: сервер с занятым циклом событий (первый
    экземпляр ещё собирает окно) подключение принимает сразу, но запись завершается,
    только когда он начнёт читать ([Ф] опыт двумя процессами 08.11.2026).
    """  # noqa: RUF002
    written = 0

    def on_written(count: int) -> None:
        nonlocal written
        written += count

    socket.bytesWritten.connect(on_written)
    socket.write(ACTIVATE_MESSAGE)
    while (
        written < len(ACTIVATE_MESSAGE)
        and socket.state() == QLocalSocket.LocalSocketState.ConnectedState
        and time.monotonic() < deadline
    ):
        QCoreApplication.processEvents()
        socket.waitForBytesWritten(20)
    return written >= len(ACTIVATE_MESSAGE)


def request_activation(
    name: str, connect_timeout_ms: int = 3000, write_timeout_ms: int = 20000
) -> bool:
    """Попросить работающий экземпляр поднять окно. `True` — просьба доставлена.

    Два срока. Подключение повторяется до `connect_timeout_ms`: первый экземпляр
    мог ещё не открыть канал (мьютекс он захватывает раньше). Подключение доказывает,
    что первый жив и прошёл `listen`, поэтому запись после него ждёт дольше —
    до `write_timeout_ms`: первый, пока собирает окно (секунды на холодном старте),
    просьбу не читает. Верхняя граница подключения — с точностью до одной попытки
    (200 мс); запись получает свой срок целиком, даже если подключение пришлось
    на конец первого.
    """  # noqa: RUF002
    connect_deadline = time.monotonic() + connect_timeout_ms / 1000
    while True:
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(200):
            delivered = _send(socket, time.monotonic() + write_timeout_ms / 1000)
            socket.disconnectFromServer()
            return delivered
        if time.monotonic() >= connect_deadline:
            return False
        time.sleep(0.1)
