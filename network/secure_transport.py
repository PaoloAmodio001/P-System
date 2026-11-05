from __future__ import annotations

import json
import selectors
import socket
import ssl
import threading
import time
from dataclasses import dataclass


MAX_MESSAGE_SIZE = 16 * 1024 * 1024


@dataclass(frozen=True)
class TLSConfig:
    """
    Explicit trust configuration for P-System node transport.

    certificate:
        Local node certificate.

    private_key:
        Private key belonging to the local certificate.

    ca_file:
        Trust anchor used to authenticate remote node certificates.

    server_hostname:
        TLS hostname/SAN used by the client.  P-System additionally
        verifies the node identity carried by the application handshake.
    """

    certificate: str
    private_key: str
    ca_file: str
    server_hostname: str = "p-system"


class DuplexTLSStream:
    """
    A TLS socket that one thread can read while another one writes.

    An SSL object must not be in two calls at once: a reader and a writer on one
    blocking SSLSocket corrupt the session, with errors such as BAD_RECORD_MAC. Here
    the socket is nonblocking, each SSL call holds a lock, and the wait for the socket
    happens outside the lock. No call can block with the lock held, so neither side
    waits for the other.

    A send has a deadline, so that a peer that does not read cannot hold the sender
    forever. After a TimeoutError the frame may be partly written and the connection
    is unusable: the caller has to close it. Only the writer of the frame is affected.

    A frame may take several SSL calls, so concurrent writers need a lock of their own
    above this one: PeerConnection.send holds it.
    """

    SEND_TIMEOUT = 5.0
    # Added to the deadline, so that a long frame to a slow honest peer can finish.
    SEND_BYTES_PER_SECOND = 1024 * 1024
    # A close from another thread is noticed within this time.
    WAIT_SLICE = 0.2
    _CHUNK = 64 * 1024

    def __init__(self, sock: ssl.SSLSocket) -> None:
        self._sock = sock
        self._io_lock = threading.Lock()
        self._closed = False
        # Bytes read to look ahead and not yet asked for.
        self._ahead = bytearray()
        sock.setblocking(False)
        # Each message is small and waits for an answer. With Nagle and delayed
        # acknowledgements every step of the protocol would cost about 40 ms.
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _wait(self, error: ssl.SSLError, seconds: float = WAIT_SLICE) -> None:
        events = (
            selectors.EVENT_READ
            if isinstance(error, ssl.SSLWantReadError)
            else selectors.EVENT_WRITE
        )

        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self._sock, events)
                selector.select(max(0.0, min(seconds, self.WAIT_SLICE)))
        except (OSError, ValueError) as closed:
            # The socket was closed while waiting.
            raise ConnectionError("CONNECTION CLOSED") from closed

    def _check_open(self) -> None:
        if self._closed:
            raise ConnectionError("CONNECTION CLOSED")

    def sendall(self, data: bytes) -> None:
        frame = memoryview(data)
        offset = 0
        deadline = (
            time.monotonic()
            + self.SEND_TIMEOUT
            + len(frame) / self.SEND_BYTES_PER_SECOND
        )

        while offset < len(frame):
            self._check_open()
            # After a "want" error OpenSSL needs the same bytes again, and the slice
            # stays the same until a call succeeds.
            chunk = frame[offset:offset + self._CHUNK]

            try:
                with self._io_lock:
                    self._check_open()
                    offset += self._sock.send(chunk)
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as error:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    raise TimeoutError("PEER IS NOT READING") from error

                self._wait(error, remaining)

    def frame_available(self) -> bool:
        """
        Whether a whole frame is already here, without waiting for anything. So a frame
        that stops halfway cannot hold back the ones before it. With one thread reading: the
        receive loop. A bad length counts as available, and reading it raises the error.
        """
        while not self._frame_is_ahead():
            self._check_open()

            try:
                with self._io_lock:
                    self._check_open()
                    chunk = self._sock.recv(self._CHUNK)
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                return False

            if not chunk:
                # The end of the stream, which the next read reports.
                return bool(self._ahead)

            self._ahead.extend(chunk)

        return True

    def _frame_is_ahead(self) -> bool:
        if len(self._ahead) < 4:
            return False

        length = int.from_bytes(self._ahead[:4], "big")

        if length <= 0 or length > MAX_MESSAGE_SIZE:
            return True

        return len(self._ahead) >= 4 + length

    def recv(self, size: int) -> bytes:
        if self._ahead:
            data = bytes(self._ahead[:size])
            del self._ahead[:size]
            return data

        while True:
            self._check_open()

            try:
                with self._io_lock:
                    self._check_open()
                    return self._sock.recv(size)
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as error:
                self._wait(error)

    def shutdown(self, how: int) -> None:
        # Under the lock because SSLSocket.shutdown drops the SSL object, and a call in
        # progress must not find it gone.
        with self._io_lock:
            if not self._closed:
                self._sock.shutdown(how)

    def close(self) -> None:
        with self._io_lock:
            self._closed = True
            self._sock.close()

    def __getattr__(self, name: str):
        # getpeercert and the like, which make no SSL call on the session.
        return getattr(self._sock, name)


class SecureTransport:
    """
    Mandatory TLS 1.3 transport.

    No plaintext fallback is provided.
    """

    MAX_MESSAGE_SIZE = MAX_MESSAGE_SIZE

    @staticmethod
    def create_server_context(config: TLSConfig) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3

        context.verify_mode = ssl.CERT_REQUIRED

        context.load_cert_chain(
            certfile=config.certificate,
            keyfile=config.private_key,
        )

        context.load_verify_locations(
            cafile=config.ca_file,
        )

        return context

    @staticmethod
    def create_client_context(config: TLSConfig) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3

        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True

        context.load_cert_chain(
            certfile=config.certificate,
            keyfile=config.private_key,
        )

        context.load_verify_locations(
            cafile=config.ca_file,
        )

        return context

    @staticmethod
    def wrap_server(
        connection: socket.socket,
        context: ssl.SSLContext,
    ) -> ssl.SSLSocket:
        """
        Perform the TLS server handshake before returning the connection.
        """
        return context.wrap_socket(
            connection,
            server_side=True,
        )

    @staticmethod
    def wrap_client(
        connection: socket.socket,
        context: ssl.SSLContext,
        server_hostname: str,
    ) -> ssl.SSLSocket:
        """
        Perform the TLS client handshake before returning the connection.
        """
        return context.wrap_socket(
            connection,
            server_hostname=server_hostname,
        )

    @staticmethod
    def peer_certificate(
        connection: ssl.SSLSocket,
    ) -> dict:
        certificate = connection.getpeercert()

        if not certificate:
            raise ssl.SSLError("PEER CERTIFICATE NOT AVAILABLE")

        return certificate

    @staticmethod
    def peer_names(connection: ssl.SSLSocket) -> set[str]:
        """The DNS names in the certificate of the peer, which the authority has signed."""
        certificate = connection.getpeercert()

        if not certificate:
            return set()

        return {
            value
            for kind, value in certificate.get("subjectAltName", ())
            if kind == "DNS"
        }

    @staticmethod
    def encode_payload(message: dict) -> bytes:
        payload = json.dumps(
            message,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        if not payload:
            raise ValueError("INVALID EMPTY MESSAGE")

        return payload

    @staticmethod
    def frame_of_payload(payload: bytes) -> bytes:
        if len(payload) > MAX_MESSAGE_SIZE:
            raise ValueError("MESSAGE TOO LARGE")

        return len(payload).to_bytes(4, "big") + payload

    @staticmethod
    def send(connection, message: dict) -> None:
        connection.sendall(
            SecureTransport.frame_of_payload(SecureTransport.encode_payload(message))
        )

    @staticmethod
    def decode_payload(payload: bytes) -> dict:
        try:
            message = json.loads(
                payload.decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("INVALID JSON MESSAGE") from exc

        if not isinstance(message, dict):
            raise ValueError("INVALID MESSAGE TYPE")

        return message

    @staticmethod
    def receive(connection) -> dict:
        header = SecureTransport._read_exact(
            connection,
            4,
        )

        length = int.from_bytes(
            header,
            "big",
        )

        if length <= 0 or length > MAX_MESSAGE_SIZE:
            raise ValueError("INVALID MESSAGE LENGTH")

        return SecureTransport.decode_payload(
            SecureTransport._read_exact(
                connection,
                length,
            )
        )

    @staticmethod
    def _read_exact(connection, size: int) -> bytes:
        data = bytearray()

        while len(data) < size:
            chunk = connection.recv(
                size - len(data)
            )

            if not chunk:
                raise ConnectionError(
                    "CONNECTION CLOSED"
                )

            data.extend(chunk)

        return bytes(data)
