"""The Quick start of README.md, run as written: Docker, four nodes, a wallet and a client.

This is the only test that builds the published image and follows the README from
`make_local_deployment.py` to `wait_final`. It is slow and skips itself when Docker or its
daemon is not available. The cheap checks of the files the script writes stay in
tests/test_local_deployment.py; the flow on real processes stays in
tests/test_quorum_differential_processes.py.
"""

import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from crypto.identity import Identity
from network.deployment import read_genesis
from sdk.client import ChainVerifier, Client, Wallet
from tests.deployment_helpers import ROOT

pytestmark = pytest.mark.slow

API_PORTS = range(8080, 8084)
BUILD_TIMEOUT = 900
DOWN_TIMEOUT = 180


def docker(*arguments: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def compose(project: str, path: Path, *arguments: str, timeout: float = 60):
    return docker(
        "compose",
        "--project-name",
        project,
        "--file",
        str(path),
        *arguments,
        timeout=timeout,
    )


def require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is not installed")

    try:
        available = docker("info", timeout=30).returncode == 0
        running = docker("compose", "version", timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker is not available")

    if not available:
        pytest.skip("Docker daemon is not running")

    if not running:
        pytest.skip("Docker Compose is not available")


def ports_are_free() -> bool:
    for port in API_PORTS:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                return False

    return True


def wait_until(condition, seconds: float = 120) -> None:
    deadline = time.monotonic() + seconds
    last = None

    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except (ConnectionError, TimeoutError, OSError) as error:
            last = error

        time.sleep(0.25)

    raise AssertionError(f"condition not met: {last}")


def test_the_quick_start_of_the_readme_reaches_a_certified_transfer(tmp_path):
    require_docker()

    if not ports_are_free():
        pytest.skip("ports 8080-8083 are already in use")

    base = tmp_path / "psystem-demo"
    made = subprocess.run(
        [sys.executable, "scripts/make_local_deployment.py", str(base), "--f", "1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert made.returncode == 0, made.stderr

    path = base / "docker-compose.yml"
    project = f"psystem-readme-{uuid.uuid4().hex[:12]}"

    try:
        up = compose(
            project,
            path,
            "up",
            "--detach",
            "--build",
            "--wait",
            "--wait-timeout",
            "180",
            timeout=BUILD_TIMEOUT,
        )

        if up.returncode != 0:
            logs = compose(project, path, "logs", "--no-color", timeout=120)
            pytest.fail(
                "docker compose up failed\n"
                f"stdout:\n{up.stdout[-4000:]}\n"
                f"stderr:\n{up.stderr[-4000:]}\n"
                f"logs:\n{logs.stdout[-8000:]}"
            )

        genesis = read_genesis(base / "genesis.json")
        wallet = Wallet(Identity.load(base / "sender.key"), base / "wallet.sqlite")
        token = (base / "node-0" / "api.token").read_text().strip()
        client = Client("http://127.0.0.1:8080", token=token, timeout=5)

        wait_until(lambda: len(client.status()["peers"]) >= 3)

        signed = wallet.transfer("receiver-account", 8)
        assert client.submit(signed)["accepted"]

        assert client.wait_final(
            signed.transfer,
            ChainVerifier(genesis.committee, genesis.governance),
            seconds=60,
        )

        other_token = (base / "node-3" / "api.token").read_text().strip()
        other = Client("http://127.0.0.1:8083", token=other_token, timeout=5)

        assert other.wait_final(
            signed.transfer,
            ChainVerifier(genesis.committee, genesis.governance),
            seconds=60,
        )
        assert other.account("receiver-account")["balance"] == 8

        nodes = [
            Client(
                f"http://127.0.0.1:{8080 + index}",
                token=(base / f"node-{index}" / "api.token").read_text().strip(),
                timeout=5,
            )
            for index in range(4)
        ]
        wait_until(
            lambda: len({node.status()["state_root"] for node in nodes}) == 1
        )

        assert client.verify_final(
            signed.transfer,
            ChainVerifier(genesis.committee, genesis.governance),
        )
    finally:
        compose(
            project,
            path,
            "down",
            "--remove-orphans",
            "--rmi",
            "local",
            timeout=DOWN_TIMEOUT,
        )
