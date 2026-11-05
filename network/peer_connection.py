from __future__ import annotations

import socket
import ssl
import threading
import time
from collections import deque

from network.fragments import MAX_ASSEMBLED_SIZE, FragmentAssembler, split_payload
from network.handshake import Handshake
from network.peer import Peer
from network.secure_transport import DuplexTLSStream, SecureTransport, TLSConfig


def _duplex(connection):
    """From here on a connection is read and written by different threads."""
    if isinstance(connection, ssl.SSLSocket):
        return DuplexTLSStream(connection)

    return connection


class Pacer:
    """
    At most `rate` messages per second on average, by waiting. Reading less makes the peer wait,
    through TCP. An honest peer never gets near this, and one that floods costs only itself.
    """

    def __init__(self, rate: float, burst: float, clock=time.monotonic, sleep=time.sleep) -> None:
        self.rate = rate
        self.burst = burst
        self._clock = clock
        self._sleep = sleep
        self._tokens = burst
        self._last = clock()

    def take(self, count: int = 1) -> None:
        now = self._clock()
        self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
        self._last = now
        self._tokens -= count

        if self._tokens < 0:
            self._sleep(-self._tokens / self.rate)


class PeerConnection:
    MAX_RECEIVED_TOGETHER = 64
    MAX_MESSAGES_PER_SECOND = 5000.0
    # Room for the largest message and for what is sent next to it. A peer this far behind
    # loses the connection, and catches up from the log when it comes back.
    MAX_QUEUED_BYTES = MAX_ASSEMBLED_SIZE + 64 * 1024 * 1024

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
    ):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.connection = None
        self.remote_handshake = None
        self.tls_config = None
        self.on_disconnect = None
        self.initiated_locally = True
        self._send_lock = threading.Lock()
        self._assembler = FragmentAssembler()
        self._pacer = Pacer(self.MAX_MESSAGES_PER_SECOND, 2 * self.MAX_MESSAGES_PER_SECOND)
        self._queue_changed = threading.Condition()
        self._queue: deque[list[bytes]] = deque()
        self._queued_bytes = 0
        self._writer: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self.connection is not None

    def connect(
        self,
        peer: Peer,
        tls_config: TLSConfig,
    ) -> Handshake:
        if self.connected:
            raise RuntimeError("ALREADY CONNECTED")

        connection = socket.create_connection(
            peer.address(),
            timeout=2.0,
        )

        try:
            context = SecureTransport.create_client_context(
                tls_config
            )

            connection = SecureTransport.wrap_client(
                connection,
                context,
                peer.node_id,
            )

            SecureTransport.send(
                connection,
                Handshake(
                    node_id=self.node_id,
                    host=self.host,
                    port=self.port,
                ).encode(),
            )

            response = SecureTransport.receive(connection)
            handshake = Handshake.decode(response)

            if handshake.node_id == self.node_id:
                raise ValueError("INVALID PEER IDENTITY")

            if SecureTransport.is_revoked(connection, tls_config):
                raise ValueError("CERTIFICATE OF THE PEER IS REVOKED")

            # Il timeout breve serve solo per stabilire la connessione.
            # La connessione TLS persistente deve poter restare inattiva.
            connection.settimeout(None)

            self.connection = _duplex(connection)
            self.remote_handshake = handshake
            self.tls_config = tls_config

            return handshake

        except Exception:
            connection.close()
            raise

    @classmethod
    def adopt(
        cls,
        node_id: str,
        connection,
        handshake: Handshake,
    ) -> "PeerConnection":
        peer_connection = cls(
            node_id=node_id,
            host=handshake.host,
            port=handshake.port,
        )

        peer_connection.connection = _duplex(connection)
        peer_connection.remote_handshake = handshake
        peer_connection.initiated_locally = False

        return peer_connection

    @staticmethod
    def _frames_of(message: dict) -> list[bytes]:
        """ValueError if no peer could take it."""
        payload = SecureTransport.encode_payload(message)

        if len(payload) <= SecureTransport.MAX_MESSAGE_SIZE:
            return [SecureTransport.frame_of_payload(payload)]

        return [
            SecureTransport.frame_of_payload(SecureTransport.encode_payload(fragment))
            for fragment in split_payload(message.get("type"), payload)
        ]

    def send(self, message: dict) -> None:
        frames = self._frames_of(message)

        # One message at a time: threads writing together on a TLS socket mix their
        # frames and can crash the process. close does not take this lock, because
        # closing also frees a send waiting on a peer that does not read.
        with self._send_lock:
            connection = self.connection

            if connection is None:
                raise ConnectionError("PEER NOT CONNECTED")

            for frame in frames:
                connection.sendall(frame)

    def enqueue(self, message: dict) -> None:
        """
        Send without waiting for this peer, in the order of the calls. A peer that does not
        read then holds back only itself. ConnectionError if it is too far behind, and the
        caller drops the connection, as for a send that fails.
        """
        frames = self._frames_of(message)
        size = sum(len(frame) for frame in frames)

        with self._queue_changed:
            if self.connection is None:
                raise ConnectionError("PEER NOT CONNECTED")

            if self._queued_bytes + size > self.MAX_QUEUED_BYTES:
                raise ConnectionError("PEER IS TOO FAR BEHIND")

            self._queue.append(frames)
            self._queued_bytes += size

            if self._writer is None:
                self._writer = threading.Thread(
                    target=self._write_queued,
                    name=f"psystem-writer-{self.node_id}",
                    daemon=True,
                )
                self._writer.start()

            self._queue_changed.notify_all()

    def _write_queued(self) -> None:
        while True:
            with self._queue_changed:
                while not self._queue and self.connection is not None:
                    self._queue_changed.wait()

                if self.connection is None:
                    return

                frames = self._queue.popleft()

            try:
                with self._send_lock:
                    connection = self.connection

                    if connection is None:
                        return

                    for frame in frames:
                        connection.sendall(frame)
            except (ConnectionError, OSError, TimeoutError):
                self._close_and_notify()
                return

            with self._queue_changed:
                self._queued_bytes -= sum(len(frame) for frame in frames)
                self._queue_changed.notify_all()

    def flush(self, seconds: float) -> bool:
        """Wait for what is queued to be written. False if it was not, within `seconds`."""
        with self._queue_changed:
            return self._queue_changed.wait_for(
                lambda: self._queued_bytes == 0 or self.connection is None,
                timeout=seconds,
            ) and self._queued_bytes == 0

    def _next_message(self) -> dict | None:
        """The next message, or None if the frame was only a piece of one."""
        connection = self.connection

        if connection is None:
            raise ConnectionError("PEER NOT CONNECTED")

        message = SecureTransport.receive(connection)

        if message.get("type") == "FRAGMENT":
            payload = self._assembler.add(message)
            return None if payload is None else SecureTransport.decode_payload(payload)

        if self._assembler.in_progress:
            raise ValueError("MESSAGE INSIDE A FRAGMENTED MESSAGE")

        return message

    def receive(self) -> dict:
        while True:
            message = self._next_message()

            if message is not None:
                return message

    def _received_together(self, message: dict) -> tuple[list[dict], bool]:
        """
        This message and the whole frames already here, up to a limit. True if a frame
        among them was malformed: what came before it still counts, and then the
        connection closes.
        """
        messages = [message]
        connection = self.connection
        frame_available = getattr(connection, "frame_available", None)

        if frame_available is None:
            return messages, False

        try:
            while len(messages) < self.MAX_RECEIVED_TOGETHER and frame_available():
                next_message = self._next_message()

                # A piece of a large message: its rest may take a while, and what is here
                # should not wait for it.
                if next_message is None:
                    break

                messages.append(next_message)
        except (ConnectionError, OSError, TimeoutError, ValueError, RecursionError):
            return messages, True

        return messages, False

    def receive_loop(self, handler, batch_handler=None) -> None:
        """
        Calls `handler(message, self)` for each message. With `batch_handler`, it gets
        `batch_handler(messages, self)`, with the messages that are already here. That is
        what lets several of them share one write to disk.
        """
        # A connection can close between its handshake and this thread: nothing to read, and no
        # error. Raising here only killed the thread with noise.
        while self.connected:
            try:
                message = self.receive()
            except (
                ConnectionError,
                OSError,
                TimeoutError,
                ValueError,
                RecursionError,
            ):
                # ValueError and RecursionError: the peer sent a malformed frame.
                self._close_and_notify()
                return
            except Exception:
                self._close_and_notify()
                raise

            broken = False

            try:
                if batch_handler is None:
                    handler(message, self)
                    self._pacer.take()
                else:
                    messages, broken = self._received_together(message)
                    batch_handler(messages, self)
                    self._pacer.take(len(messages))
            except (ValueError, KeyError, TypeError, IndexError):
                self._close_and_notify()
                return
            except Exception:
                self._close_and_notify()
                raise

            if broken:
                self._close_and_notify()
                return

    def _close_and_notify(self) -> None:
        self.close()
        callback = self.on_disconnect
        if callback is not None:
            callback(self)

    def close(self) -> None:
        if self.connection is None:
            return

        connection = self.connection
        try:
            # Interrompe anche eventuali recv bloccanti in altri thread.
            shutdown = getattr(connection, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
        finally:
            self.connection = None
            self.remote_handshake = None
            self.tls_config = None

            with self._queue_changed:
                self._queue.clear()
                self._queued_bytes = 0
                self._queue_changed.notify_all()
