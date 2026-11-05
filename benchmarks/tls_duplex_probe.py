"""Measure a thread in recv and a thread in send on one TLS socket.

This is a measurement of the problem behind DuplexTLSStream, not a test: the failures
depend on timing. The test is tests/test_tls_duplex.py. The scenarios that use a bare
SSLSocket still show the old failure, which is the point of keeping them.

Each run is a separate process, because the outcome can be a crash or a hang.

    python benchmarks/tls_duplex_probe.py direct --size 64 --count 3000 --runs 30

Scenarios:
    direct   both sides send right after the TLS handshake, as readers start
    settled  the same, after one message each way
    node     two real Nodes, each sending while its receive_loop reads
    remedy   prototype: nonblocking socket, one lock on each SSL call, not in network/
"""

import argparse
import json
import os
import select
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.state import State  # noqa: E402
from network.decision_message import encode_decision_context  # noqa: E402
from network.node import Node  # noqa: E402
from network.node_tls_identity import get_node_tls_config  # noqa: E402
from network.peer import Peer  # noqa: E402
from network.peer_connection import PeerConnection  # noqa: E402
from network.secure_transport import SecureTransport  # noqa: E402

JOIN_SECONDS = 25
RUN_TIMEOUT_SECONDS = 40


def _tls_pair():
    listener = socket.create_server(("127.0.0.1", 0))
    accepted = {}

    def accept():
        raw, _ = listener.accept()
        accepted["socket"] = SecureTransport.wrap_server(
            raw,
            SecureTransport.create_server_context(get_node_tls_config("probe-B")),
        )

    acceptor = threading.Thread(target=accept)
    acceptor.start()
    client = SecureTransport.wrap_client(
        socket.create_connection(listener.getsockname(), timeout=5),
        SecureTransport.create_client_context(get_node_tls_config("probe-A")),
        "probe-B",
    )
    acceptor.join()
    client.settimeout(None)
    accepted["socket"].settimeout(None)
    return client, accepted["socket"]


def _peer_connection(sock) -> PeerConnection:
    connection = PeerConnection("probe", "127.0.0.1", 1)
    connection.connection = sock
    return connection


class _LockedNonblocking:
    """The remedy under measurement. select runs outside the lock."""

    def __init__(self, sock):
        self.sock = sock
        sock.setblocking(False)
        self.io_lock = threading.Lock()
        self.send_lock = threading.Lock()

    def _wait(self, error) -> None:
        wants_read = isinstance(error, ssl.SSLWantReadError)
        select.select(
            [self.sock] if wants_read else [],
            [] if wants_read else [self.sock],
            [],
            1,
        )

    def send(self, message: dict) -> None:
        payload = json.dumps(message).encode()
        frame = memoryview(len(payload).to_bytes(4, "big") + payload)
        offset = 0

        with self.send_lock:
            while offset < len(frame):
                try:
                    with self.io_lock:
                        offset += self.sock.send(frame[offset : offset + 65536])
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as error:
                    self._wait(error)

    def _read_exact(self, size: int) -> bytes:
        data = bytearray()

        while len(data) < size:
            try:
                with self.io_lock:
                    chunk = self.sock.recv(size - len(data))
                if not chunk:
                    raise ConnectionError("CONNECTION CLOSED")
                data += chunk
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as error:
                self._wait(error)

        return bytes(data)

    def receive(self) -> dict:
        size = int.from_bytes(self._read_exact(4), "big")
        return json.loads(self._read_exact(size))


def _run_duplex(first, second, size: int, count: int) -> list[str]:
    errors = []

    def reader(connection):
        try:
            for sequence in range(count):
                message = connection.receive()
                assert message["k"] == sequence and len(message["p"]) == size
        except Exception as error:
            errors.append(repr(error)[:120])

    def writer(connection):
        try:
            for sequence in range(count):
                connection.send({"k": sequence, "p": "x" * size})
        except Exception as error:
            errors.append(repr(error)[:120])

    threads = [
        threading.Thread(target=target, args=(connection,), daemon=True)
        for target in (reader, writer)
        for connection in (first, second)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_SECONDS)

    if any(thread.is_alive() for thread in threads):
        errors.append("HUNG")
    return errors


def _direct(size: int, count: int) -> list[str]:
    first, second = _tls_pair()
    return _run_duplex(
        _peer_connection(first), _peer_connection(second), size, count
    )


def _settled(size: int, count: int) -> list[str]:
    first, second = (_peer_connection(sock) for sock in _tls_pair())
    first.send({"hello": 1})
    second.receive()
    second.send({"hello": 2})
    first.receive()
    time.sleep(0.2)
    return _run_duplex(first, second, size, count)


def _remedy(size: int, count: int) -> list[str]:
    first, second = (_LockedNonblocking(sock) for sock in _tls_pair())
    return _run_duplex(first, second, size, count)


def _node(_size: int, count: int) -> list[str]:
    # The message is small, because the handler of a real Node validates it.
    tag = str(os.getpid())
    first = Node(f"probe-a{tag}", State({"alice": 10}), port=0)
    second = Node(f"probe-b{tag}", State({"alice": 10}), port=0)
    first.start()
    second.start()
    host, port = second.address()

    if not first.connect_peer(Peer(node_id=second.node_id, host=host, port=port)):
        return ["NOT CONNECTED"]

    deadline = time.time() + 5
    while time.time() < deadline and (
        second.node_id not in first.peer_connections
        or first.node_id not in second.peer_connections
    ):
        time.sleep(0.01)

    links = {
        first: first.peer_connections[second.node_id],
        second: second.peer_connections[first.node_id],
    }
    errors = []

    def sender(node):
        message = encode_decision_context(node.decision_context())
        try:
            for _ in range(count):
                links[node].send(message)
        except Exception as error:
            errors.append(repr(error)[:120])

    threads = [
        threading.Thread(target=sender, args=(node,), daemon=True)
        for node in links
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_SECONDS)

    if any(thread.is_alive() for thread in threads):
        errors.append("HUNG")

    time.sleep(0.3)
    if any(link.connection is None for link in links.values()):
        errors.append("LINK LOST")
    return errors


SCENARIOS = {
    "direct": _direct,
    "settled": _settled,
    "node": _node,
    "remedy": _remedy,
}


def _one_run(args) -> None:
    errors = SCENARIOS[args.scenario](args.size, args.count)
    print(errors[0] if errors else "OK", flush=True)
    # A daemon thread may still hold the socket: do not wait for it at exit.
    os._exit(1 if errors else 0)


def _measure(args) -> int:
    command = [
        sys.executable,
        __file__,
        args.scenario,
        "--size",
        str(args.size),
        "--count",
        str(args.count),
        "--child",
    ]
    outcomes = Counter()

    for _ in range(args.runs):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            outcomes["HUNG (timeout)"] += 1
            continue

        if result.returncode < 0:
            outcomes[f"CRASH signal {-result.returncode}"] += 1
        else:
            lines = result.stdout.strip().splitlines()
            outcomes[lines[-1][:80] if lines else f"exit {result.returncode}"] += 1

    print(
        f"{args.scenario} size={args.size} count={args.count} "
        f"runs={args.runs}"
    )
    for outcome, times in outcomes.most_common():
        print(f"  {times:3d}  {outcome}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--count", type=int, default=3000)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        _one_run(args)
    return _measure(args)


if __name__ == "__main__":
    raise SystemExit(main())
