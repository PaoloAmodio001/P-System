"""A whole deployment on disk, made with the `psystem` command as an operator would make it."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

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


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Deployment:
    def __init__(self, base: Path, nodes: int = 4, f: int = 1, balance: int = 1000) -> None:
        self.base = base
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

    def write_config(self, index: int, extra: str = "") -> None:
        node_id = self.node_id(index)
        peers = "".join(
            f'\n[[peers]]\nnode_id = "{self.node_id(other)}"\n'
            f'host = "127.0.0.1"\nport = {self.ports[other]}\n'
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
        arguments = [
            sys.executable, "-m", "network.cli", "node",
            "--config", str(self.directory(index) / "node.toml"),
        ]

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
        # The line it prints when it is up.
        assert json.loads(self.processes[index].stdout.readline())["node_id"]

    def start_all(self) -> None:
        for index in range(self.count):
            self.start(index)

    def kill(self, index: int) -> None:
        process = self.processes.pop(index)
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)

    def stop(self, index: int) -> int:
        process = self.processes.pop(index)
        process.send_signal(signal.SIGTERM)
        return process.wait(timeout=20)

    def stop_all(self) -> None:
        for process in list(self.processes.values()):
            process.kill()
            process.wait(timeout=10)
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
