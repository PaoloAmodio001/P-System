"""Make the files for nodes on separate machines, one directory for each.

    python scripts/make_host_deployment.py out --host node-0=10.0.0.1 --host node-1=10.0.0.2 \
        --host node-2=10.0.0.3 --host node-3=10.0.0.4

Copy `out/<name>`, `out/ca/ca.crt` and `out/genesis.json` to each machine: see "Four machines" in
docs/OPERATIONS.md. Every key is made here, on one machine, which is good for a measurement and not for a
real deployment: there each member makes its own, and only the public key travels.
"""

import argparse
import json
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def psystem(*args: str) -> str:
    return subprocess.run(
        [sys.executable, "-m", "network.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def node_config(
    name: str,
    hosts: dict[str, str],
    port: int,
    api_port: int,
    snapshot_every: int | None = None,
) -> str:
    peers = "".join(
        f'\n[[peers]]\nnode_id = "{other}"\nhost = "{address}"\nport = {port}\n'
        for other, address in hosts.items()
        if other != name
    )
    snapshots = "" if snapshot_every is None else f"\n[snapshots]\nevery = {snapshot_every}\n"
    # The rate is for a measurement: the default limit of the API would measure itself.
    return f'''node_id = "{name}"
host = "0.0.0.0"
port = {port}
identity_key = "identity.key"
tls_certificate = "{name}.crt"
tls_key = "{name}.key"
tls_authority = "../ca/ca.crt"
genesis = "../genesis.json"
store = "votes.sqlite"
sync_interval = 1.0
{snapshots}
[api]
host = "0.0.0.0"
port = {api_port}
token_file = "api.token"
requests_per_second = 100000.0
burst = 100000.0
{peers}'''


def write_deployment(
    base: Path,
    hosts: dict[str, str],
    port: int = 7000,
    api_port: int = 8080,
    balance: int = 10**9,
    snapshot_every: int | None = None,
) -> dict:
    """The directories of the nodes, and what a measurement needs to know."""
    count = len(hosts)
    f = (count - 1) // 3

    if count != 3 * f + 1 or f == 0:
        raise ValueError("A COMMITTEE HAS 3f+1 MEMBERS, WITH f OF AT LEAST 1")

    base.mkdir(parents=True, exist_ok=False)
    psystem("authority", "init", str(base / "ca"))
    sender = json.loads(psystem("key", "generate", str(base / "sender.key")))
    governance = [
        json.loads(psystem("key", "generate", str(base / f"governance-{i}.key")))["public_key"]
        for i in range(3)
    ]
    members = []

    for name, address in hosts.items():
        directory = base / name
        directory.mkdir(mode=0o700)
        psystem("authority", "issue", str(base / "ca"), "--node-id", name, "--out", str(directory))
        members.append(json.loads(psystem("key", "generate", str(directory / "identity.key"))))
        token = directory / "api.token"
        token.touch(mode=0o600)
        token.write_text(secrets.token_hex(24) + "\n")

    arguments = ["genesis", str(base / "genesis.json"), "--f", str(f)]
    for member in members:
        arguments += ["--member", member["public_key"]]
    arguments += ["--balance", f"{sender['account']}={balance}"]
    for key in governance:
        arguments += ["--governance", key]
    arguments += ["--governance-threshold", "2"]
    psystem(*arguments)

    for name in hosts:
        (base / name / "node.toml").write_text(
            node_config(name, hosts, port, api_port, snapshot_every)
        )
        psystem("init-store", "--config", str(base / name / "node.toml"))

    return {"sender": sender["account"], "names": list(hosts), "directory": str(base)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--host", action="append", required=True, help="name=address, once for each node")
    parser.add_argument("--port", type=int, default=7000)
    parser.add_argument("--api-port", type=int, default=8080)
    parser.add_argument("--snapshot-every", type=int)
    options = parser.parse_args()
    hosts = dict(item.split("=", 1) for item in options.host)
    print(
        json.dumps(
            write_deployment(
                options.directory.resolve(),
                hosts,
                options.port,
                options.api_port,
                snapshot_every=options.snapshot_every,
            )
        )
    )


if __name__ == "__main__":
    main()
