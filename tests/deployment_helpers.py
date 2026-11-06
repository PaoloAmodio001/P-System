"""A whole deployment on disk, made with the `psystem` command as an operator would make it."""

import json
import random
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from tests.die_with_parent import command

ROOT = Path(__file__).resolve().parent.parent


def psystem(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "network.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


_PORTS_GIVEN: set[int] = set()
# Every node started in this process and not yet stopped: see tests/test_no_orphans.py.
_RUNNING: set[subprocess.Popen] = set()


def stop_leftovers() -> None:
    """Kill what a test left running, whatever way it ended. The conftest calls this after each test."""
    for process in list(_RUNNING):
        process.kill()
        process.wait(timeout=10)
        _RUNNING.discard(process)


def free_port() -> int:
    """
    A port for a process to bind later. Below the range the kernel takes from for outgoing connections,
    so that one of those cannot get there first: that killed a node at its start, once, on a busy machine.
    Never the same one twice in a run.
    """
    while True:
        port = random.randint(20_000, 32_000)

        if port in _PORTS_GIVEN:
            continue

        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue

        _PORTS_GIVEN.add(port)
        return port

class Deployment:
    def __init__(
        self,
        base: Path,
        nodes: int = 4,
        f: int = 1,
        balance: int = 1000,
        extra_senders: int = 0,
    ) -> None:
        self.base = base
        self.balance_per_sender = balance
        self.count = nodes
        self.processes: dict[int, subprocess.Popen] = {}
        self.ports = [free_port() for _ in range(nodes)]
        self.api_ports = [free_port() for _ in range(nodes)]
        psystem("authority", "init", str(base / "ca"))
        self.sender_key = base / "sender.key"
        self.sender = json.loads(psystem("key", "generate", str(self.sender_key)))
        self.governance_keys = [base / f"gov{i}.key" for i in range(3)]
        governance = [
            json.loads(psystem("key", "generate", str(path)))["public_key"]
            for path in self.governance_keys
        ]
        members = []

        for index in range(nodes):
            directory = self.directory(index)
            directory.mkdir()
            psystem(
                "authority", "issue", str(base / "ca"),
                "--node-id", self.node_id(index),
                "--out", str(directory),
            )
            members.append(
                json.loads(psystem("key", "generate", str(directory / "identity.key")))
            )

        self.members = members
        arguments = ["genesis", str(base / "genesis.json"), "--f", str(f)]

        for member in members:
            arguments += ["--member", member["public_key"]]

        arguments += ["--balance", f"{self.sender['account']}={balance}"]
        self.extra_sender_keys = [base / f"sender{i}.key" for i in range(extra_senders)]

        for path in self.extra_sender_keys:
            account = json.loads(psystem("key", "generate", str(path)))["account"]
            arguments += ["--balance", f"{account}={balance}"]

        for key in governance:
            arguments += ["--governance", key]

        arguments += ["--governance-threshold", "2"]
        self.genesis = json.loads(psystem(*arguments))

        for index in range(nodes):
            self.write_config(index)

    def directory(self, index: int) -> Path:
        return self.base / f"n{index}"

    def node_id(self, index: int) -> str:
        return f"node-{index}"

    def api_url(self, index: int) -> str:
        return f"http://127.0.0.1:{self.api_ports[index]}"

    def store(self, index: int) -> Path:
        return self.directory(index) / "votes.sqlite"

    def peer_port(self, index: int, other: int) -> int:
        """The port where node `index` reaches node `other`."""
        return self.ports[other]

    def write_config(self, index: int, extra: str = "") -> None:
        node_id = self.node_id(index)
        peers = "".join(
            f'\n[[peers]]\nnode_id = "{self.node_id(other)}"\n'
            f'host = "127.0.0.1"\nport = {self.peer_port(index, other)}\n'
            for other in range(self.count)
            if other != index
        )
        (self.directory(index) / "node.toml").write_text(
            f'''node_id = "{node_id}"
host = "127.0.0.1"
port = {self.ports[index]}
identity_key = "identity.key"
tls_certificate = "{node_id}.crt"
tls_key = "{node_id}.key"
tls_authority = "../ca/ca.crt"
genesis = "../genesis.json"
store = "votes.sqlite"
sync_interval = 0.3
{extra}
[api]
port = {self.api_ports[index]}
{peers}'''
        )

    def start(self, index: int, create: bool = True) -> None:
        arguments = command(
            "-m", "network.cli", "node",
            "--config", str(self.directory(index) / "node.toml"),
        )

        if create:
            arguments.append("--create-store")

        log = (self.directory(index) / "node.log").open("a")
        self.processes[index] = subprocess.Popen(
            arguments,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
        )
        _RUNNING.add(self.processes[index])
        # The line it prints when it is up.
        line = self.processes[index].stdout.readline()
        assert line, (self.directory(index) / "node.log").read_text()[-2000:]
        assert json.loads(line)["node_id"]

    def start_all(self) -> None:
        for index in range(self.count):
            self.start(index)

    def kill(self, index: int) -> None:
        process = self.processes.pop(index)
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)
        _RUNNING.discard(process)

    def stop(self, index: int) -> int:
        process = self.processes.pop(index)
        process.send_signal(signal.SIGTERM)
        code = process.wait(timeout=20)
        _RUNNING.discard(process)
        return code

    def stop_all(self) -> None:
        for process in list(self.processes.values()):
            process.kill()
            process.wait(timeout=10)
            _RUNNING.discard(process)
        self.processes.clear()

    def log_lines(self, index: int) -> list[dict]:
        path = self.directory(index) / "node.log"
        return [json.loads(line) for line in path.read_text().splitlines() if line.startswith("{")]


def wait_until(condition, seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if condition():
                return True
        except OSError:
            pass
        time.sleep(0.05)
    return condition()


def permissions(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
