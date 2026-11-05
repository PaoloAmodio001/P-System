"""Make the files of a local deployment of 3f+1 nodes with the `psystem` command, for trying it out.

    python scripts/make_local_deployment.py /some/empty/dir --f 1 --sender-balance 1000

Every key is on one machine here, which is what a real deployment must not do: see
docs/OPERATIONS.md. It also writes a docker-compose.yml that starts the nodes.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_PORT = 7000
BASE_API_PORT = 8080


def psystem(*args: str) -> str:
    return subprocess.run(
        [sys.executable, "-m", "network.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--f", type=int, default=1)
    parser.add_argument("--sender-balance", type=int, default=1000)
    args = parser.parse_args()
    base = args.directory.resolve()
    base.mkdir(parents=True, exist_ok=False)
    n = 3 * args.f + 1
    psystem("authority", "init", str(base / "ca"))
    sender = json.loads(psystem("key", "generate", str(base / "sender.key")))
    governance = [
        json.loads(psystem("key", "generate", str(base / f"governance-{i}.key")))["public_key"]
        for i in range(3)
    ]
    members = []
    names = [f"node-{i}" for i in range(n)]

    for name in names:
        directory = base / name
        directory.mkdir()
        psystem("authority", "issue", str(base / "ca"), "--node-id", name, "--out", str(directory))
        members.append(json.loads(psystem("key", "generate", str(directory / "identity.key"))))

    arguments = ["genesis", str(base / "genesis.json"), "--f", str(args.f)]
    for member in members:
        arguments += ["--member", member["public_key"]]
    arguments += ["--balance", f"{sender['account']}={args.sender_balance}"]
    for key in governance:
        arguments += ["--governance", key]
    arguments += ["--governance-threshold", "2"]
    print(psystem(*arguments).strip())

    services = ["services:"]

    for index, name in enumerate(names):
        peers = "".join(
            f'\n[[peers]]\nnode_id = "{other}"\nhost = "{other}"\nport = {BASE_PORT}\n'
            for other in names
            if other != name
        )
        (base / name / "node.toml").write_text(
            f'''node_id = "{name}"
host = "0.0.0.0"
port = {BASE_PORT}
identity_key = "identity.key"
tls_certificate = "{name}.crt"
tls_key = "{name}.key"
tls_authority = "../ca/ca.crt"
genesis = "../genesis.json"
store = "votes.sqlite"

[api]
host = "0.0.0.0"
port = {BASE_API_PORT}
token_file = "api.token"
{peers}'''
        )
        # Inside a container an API on its own localhost could be reached by nobody. So it listens
        # on all the interfaces of the container, with a token, and the port is published only on
        # the localhost of this machine.
        token = base / name / "api.token"
        token.touch(mode=0o600)
        token.write_text(secrets.token_hex(24) + "\n")
        services.append(
            f"""  {name}:
    build: {ROOT}
    user: "{os.getuid()}:{os.getgid()}"
    command: ["node", "--config", "/data/node.toml"]
    restart: on-failure
    read_only: true
    tmpfs: ["/tmp"]
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges:true"]
    ports:
      - "127.0.0.1:{BASE_API_PORT + index}:{BASE_API_PORT}"
    volumes:
      - {base / name}:/data
      - {base}/ca/ca.crt:/ca/ca.crt:ro
      - {base}/genesis.json:/genesis.json:ro"""
        )
        # Once, here: a container that starts never creates a store.
        psystem("init-store", "--config", str(base / name / "node.toml"))

    (base / "docker-compose.yml").write_text("\n".join(services) + "\n")
    print(
        json.dumps(
            {
                "sender": sender["account"],
                "directory": str(base),
                "api": {
                    name: {
                        "url": f"http://127.0.0.1:{BASE_API_PORT + index}",
                        "token_file": str(base / name / "api.token"),
                    }
                    for index, name in enumerate(names)
                },
            }
        )
    )


if __name__ == "__main__":
    main()
