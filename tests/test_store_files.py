"""What a node with no store does, and who can read a store or a backup.

A node with no store must stop with exit code 2, on which deploy/systemd/psystem.service does not restart.
A store and its backup show every event, and copying one into place by hand makes a validator faulty, so
they are for their owner, whatever the umask. An existing store of an earlier version is tightened too.
"""

import os
import stat
import subprocess
import sys

import pytest

from network.cli import main
from network.quorum import SqliteVoteStore
from tests.deployment_helpers import ROOT, Deployment


@pytest.fixture
def open_umask():
    before = os.umask(0)
    yield
    os.umask(before)


@pytest.fixture
def made(tmp_path, open_umask):
    deployment = Deployment(tmp_path)
    return tmp_path, deployment.directory(0) / "node.toml", deployment.directory(0) / "votes.sqlite"


def mode_of(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_a_node_with_no_store_returns_2(made, capsys, monkeypatch):
    _, config, store = made
    assert not store.exists()
    # Under capture stderr has no descriptor, and that error would also give 2, for the wrong reason.
    monkeypatch.setattr("faulthandler.register", lambda *_, **__: None)
    assert main(["node", "--config", str(config)]) == 2
    assert "CANNOT OPEN VOTE STORE" in capsys.readouterr().err
    assert not store.exists()


def test_a_real_process_with_no_store_exits_with_2_and_no_traceback(made):
    _, config, store = made
    result = subprocess.run(
        [sys.executable, "-m", "network.cli", "node", "--config", str(config)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr
    assert "CANNOT OPEN VOTE STORE" in result.stderr
    assert not store.exists()


def test_a_new_store_is_for_its_owner(made):
    _, config, store = made
    assert main(["init-store", "--config", str(config)]) == 0
    assert mode_of(store) == 0o600


def test_an_older_store_is_tightened_when_opened(made):
    _, config, store = made
    assert main(["init-store", "--config", str(config)]) == 0
    os.chmod(store, 0o644)
    from network.deployment import read_node_config

    read = read_node_config(config)
    SqliteVoteStore(store, read.genesis.committee, read.identity.public_key, governance=read.genesis.governance).close()
    assert mode_of(store) == 0o600


def test_a_backup_is_for_its_owner(made, tmp_path):
    _, config, store = made
    assert main(["init-store", "--config", str(config)]) == 0
    out = tmp_path / "backup.sqlite"
    assert main(["backup", str(store), "--out", str(out)]) == 0
    assert mode_of(out) == 0o600


def test_a_backup_over_an_open_file_is_for_its_owner_too(made, tmp_path):
    _, config, store = made
    assert main(["init-store", "--config", str(config)]) == 0
    out = tmp_path / "backup.sqlite"
    out.touch(mode=0o644)
    os.chmod(out, 0o644)
    assert main(["backup", str(store), "--out", str(out)]) == 0
    assert mode_of(out) == 0o600


def test_a_restored_store_is_for_its_owner(made, tmp_path):
    base, config, store = made
    assert main(["init-store", "--config", str(config)]) == 0
    out = tmp_path / "backup.sqlite"
    assert main(["backup", str(store), "--out", str(out)]) == 0
    target = tmp_path / "restored.sqlite"
    assert main([
        "restore", str(out), "--to", str(target),
        "--genesis", str(base / "genesis.json"),
        "--key", str(config.parent / "identity.key"),
    ]) == 0
    assert mode_of(target) == 0o600


def test_the_guard_of_a_signer_is_for_its_owner(tmp_path, open_umask):
    from network.remote_signer import SignerGuard

    path = tmp_path / "guard.sqlite"
    SignerGuard(path)
    assert mode_of(path) == 0o600


def test_the_directories_of_a_deployment_are_for_their_owner(tmp_path, open_umask):
    sys.path.insert(0, str(ROOT / "scripts"))

    try:
        import make_host_deployment
    finally:
        sys.path.pop(0)

    base = tmp_path / "out"
    make_host_deployment.write_deployment(base, {f"node-{i}": f"10.0.0.{i}" for i in range(4)})
    assert mode_of(base / "node-0") == 0o700
    assert mode_of(base / "node-0" / "votes.sqlite") == 0o600
