"""What the script of the local deployment writes is usable from outside its containers."""

import json
import subprocess
import sys

from network.deployment import read_node_config
from tests.deployment_helpers import ROOT, permissions


def test_the_api_can_be_reached_and_is_protected(tmp_path):
    base = tmp_path / "demo"
    result = subprocess.run(
        [sys.executable, "scripts/make_local_deployment.py", str(base), "--f", "1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    said = json.loads(result.stdout.strip().splitlines()[-1])
    compose = (base / "docker-compose.yml").read_text()

    for index in range(4):
        name = f"node-{index}"
        config = read_node_config(base / name / "node.toml")
        # On its own localhost, inside a container, nobody could reach it.
        assert config.api.host == "0.0.0.0"
        assert config.api.token is not None
        assert permissions(base / name / "api.token") == 0o600
        # Published, but only to this machine.
        assert f'"127.0.0.1:{8080 + index}:8080"' in compose
        assert said["api"][name]["url"] == f"http://127.0.0.1:{8080 + index}"

    tokens = {(base / f"node-{index}" / "api.token").read_text() for index in range(4)}
    assert len(tokens) == 4
