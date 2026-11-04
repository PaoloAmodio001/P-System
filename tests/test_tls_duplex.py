"""A reader and a writer on one TLS connection, the open point 2 of the plan.

An SSL object is not safe under two simultaneous calls, and quorum mode sends and receives
on the same connection. On the old transport about half of these runs failed, by a TLS
error or a hang: a single run proves nothing, so the test takes several.

Each run is a separate process, because the failure can be a crash or a hang.
"""

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from network.handshake import Handshake
from network.node_tls_identity import get_node_tls_config
from network.peer_connection import PeerConnection
from network.secure_transport import DuplexTLSStream, SecureTransport

WORKER = Path(__file__).with_name("tls_duplex_worker.py")
RUNS = 20


def run_once(count: int, size: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            [sys.executable, str(WORKER), str(count), str(size)],
            capture_output=True,
            text=True,
            timeout=40,
        )
    except subprocess.TimeoutExpired:
        return None


@pytest.mark.parametrize(
    "count,size,runs",
    [
        (3000, 64, RUNS),
        # Frames bigger than a TLS record, so that one send takes several SSL calls.
        (40, 200_000, 3),
    ],
)
def test_reader_and_writer_on_one_tls_connection(count, size, runs):
    results = [run_once(count, size) for _ in range(runs)]
    failed = [
        "hang" if result is None else (result.stdout + result.stderr)[-300:]
        for result in results
        if result is None or result.returncode != 0
    ]
    assert not failed, f"{len(failed)} of {runs} runs failed: {failed[:3]}"


# --- Deadlines and closing, in this process --------------------------------------------


def _tls_stream_pair():
    listener = socket.create_server(("127.0.0.1", 0))
    accepted = {}

    def accept():
        raw, _ = listener.accept()
        accepted["socket"] = SecureTransport.wrap_server(
            raw,
            SecureTransport.create_server_context(get_node_tls_config("duplex-b")),
        )

    thread = threading.Thread(target=accept)
    thread.start()
    client = SecureTransport.wrap_client(
        socket.create_connection(listener.getsockname(), timeout=5),
        SecureTransport.create_client_context(get_node_tls_config("duplex-a")),
        "duplex-b",
    )
    thread.join()
    listener.close()
    return DuplexTLSStream(client), DuplexTLSStream(accepted["socket"])


@pytest.fixture
def streams():
    left, right = _tls_stream_pair()
    yield left, right
    left.close()
    right.close()


def test_send_to_a_peer_that_does_not_read_times_out(streams, monkeypatch):
    left, _ = streams
    monkeypatch.setattr(DuplexTLSStream, "SEND_TIMEOUT", 0.3)
    monkeypatch.setattr(DuplexTLSStream, "SEND_BYTES_PER_SECOND", 10**12)
    frame = b"x" * 1_000_000

    outcome = []

    def write():
        try:
            for _ in range(200):
                left.sendall(frame)
        except TimeoutError as error:
            outcome.append(error)

    # In a thread, so that a send with no deadline fails this test and does not hang it.
    writer = threading.Thread(target=write, daemon=True)
    started = time.monotonic()
    writer.start()
    writer.join(timeout=10)

    assert not writer.is_alive()
    assert outcome
    # Only the last send waits: the ones before filled the buffers of the sockets.
    assert time.monotonic() - started < 5


def test_a_long_frame_gets_more_time(streams, monkeypatch):
    # A deadline fixed in seconds would cut a long frame to a peer that is reading.
    left, right = streams
    monkeypatch.setattr(DuplexTLSStream, "SEND_TIMEOUT", 0.0)
    monkeypatch.setattr(DuplexTLSStream, "SEND_BYTES_PER_SECOND", 1)
    frame = b"y" * 3_000_000
    received = bytearray()

    def read():
        while len(received) < len(frame):
            time.sleep(0.002)
            received.extend(right.recv(65536))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    left.sendall(frame)
    reader.join(timeout=30)
    assert bytes(received) == frame


def test_close_wakes_a_reader_in_another_thread(streams):
    left, _ = streams
    outcome = []

    def read():
        try:
            left.recv(10)
        except ConnectionError as error:
            outcome.append(error)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    time.sleep(0.05)
    left.close()
    reader.join(timeout=3)

    assert not reader.is_alive()
    assert outcome


def test_close_wakes_a_writer_in_another_thread(streams):
    left, _ = streams
    outcome = []

    def write():
        try:
            while True:
                left.sendall(b"z" * 1_000_000)
        except ConnectionError as error:
            outcome.append(error)
        except OSError as error:
            outcome.append(error)

    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    time.sleep(0.2)
    left.close()
    writer.join(timeout=3)

    assert not writer.is_alive()
    assert outcome


def test_peer_connection_wraps_a_tls_socket_and_leaves_others_alone():
    raw_left, raw_right = socket.socketpair()
    plain = PeerConnection.adopt("a", raw_left, Handshake("b", "127.0.0.1", 1))
    assert plain.connection is raw_left
    raw_left.close()
    raw_right.close()


def test_end_of_the_stream_is_seen_by_the_reader(streams):
    left, right = streams
    right.close()
    # An orderly close or a ragged one: an empty read, which _read_exact turns into an error.
    assert left.recv(10) == b""


def test_peer_connection_uses_the_duplex_stream_on_tls():
    client, server = _tls_stream_pair()
    # Unwrapped here, because adopt is what has to wrap it.
    connection = PeerConnection.adopt(
        "a",
        client._sock,
        Handshake("b", "127.0.0.1", 1),
    )
    assert isinstance(connection.connection, DuplexTLSStream)
    connection.close()
    server.close()
