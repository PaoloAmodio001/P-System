"""Four virtual machines under QEMU/KVM, and campaigns of faults on them that last hours.

    python scripts/vm_lab.py prepare LAB --image debian-13-genericcloud-amd64.qcow2
    python scripts/vm_lab.py up LAB
    python scripts/vm_lab.py campaign LAB --profile network --hours 2 --out benchmarks/results/vm.jsonl
    python scripts/vm_lab.py down LAB

Each node runs in a virtual machine of its own: its own kernel, network stack, disk and clock. The
machines share one Ethernet segment (a QEMU multicast socket, which needs no root on the host), and
every fault is made inside them as root: `tc netem` for latency, jitter, loss, corruption, reordering,
duplication and bandwidth, blackhole routes for partitions, `kill -9` for the crash of a process, and a reset of
the machine through the QEMU monitor for a power cut, which loses what the disk had not written.

A campaign is `tests/chaos.py` on these machines: the honest traffic, the sender that signs two versions
of one spend, and the same checks at the end (no two decided versions, every certificate verifies, the
balances add up, every honest transfer final, the honest nodes converge and none halted). In the profile
`byzantine` member 3 is a validator with no vote lock (`scripts/byzantine_member.py`): it signs every
version it is asked for, in round 0 and in every round.

**This is one host.** The machines share its CPUs and its disk, and their network is a socket on it. What
this adds to tests/chaos.py is a kernel of its own for each node, faults made by the kernel, and the loss
of a whole machine. It does not replace separate machines on a real network: docs/SEPARATE-MACHINES.md.
"""

import argparse
import datetime
import http.server
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COUNT = 4
PORT = 7000
API_PORT = 8080
LAN = "10.10.0"
INTERFACE = "lan0"
MEMORY_MB = 1536
MULTICAST = "230.0.0.1:12345"


def lan_address(index: int) -> str:
    return f"{LAN}.{11 + index}"


def ssh_port(index: int) -> int:
    return 22200 + index


def api_port(index: int) -> int:
    return 18180 + index


def mac(index: int, nic: int) -> str:
    return f"52:54:00:00:{nic:02x}:{11 + index:02x}"


# --- Commands made inside a machine ----------------------------------------------------------------


def netem_command(**options) -> str:
    """`tc` replacing the qdisc of the LAN. Options in the units of netem: `delay="20ms 5ms"`, `loss="2%"`."""
    words = " ".join(f"{name.replace('_', '-')} {value}" for name, value in options.items())
    return f"tc qdisc replace dev {INTERFACE} root netem {words}"


def clear_netem_command() -> str:
    return f"tc qdisc del dev {INTERFACE} root 2>/dev/null || true"


def partition_command(others: list[int]) -> str:
    """No route to these members. Each side gets the same, so nothing passes either way."""
    return " && ".join(f"ip route replace blackhole {lan_address(other)}/32" for other in others)


def heal_command() -> str:
    return f"{clear_netem_command()}; ip route flush type blackhole 2>/dev/null || true"


# --- The host side ---------------------------------------------------------------------------------


class Lab:
    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        self.share = self.base / "share"
        self.seed = self.base / "seed"
        self.key = self.base / "ssh" / "id_ed25519"

    def disk(self, index: int) -> Path:
        return self.base / f"vm{index}.qcow2"

    def monitor(self, index: int) -> Path:
        return self.base / f"vm{index}.monitor"

    def pidfile(self, index: int) -> Path:
        return self.base / f"vm{index}.pid"

    def ssh(self, index: int, command: str, timeout: float = 60, check: bool = True) -> str:
        done = subprocess.run(
            [
                "ssh", "-i", str(self.key), "-p", str(ssh_port(index)),
                "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                "root@127.0.0.1", command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if check and done.returncode != 0:
            raise RuntimeError(f"vm{index}: {command}: {done.stderr.strip()[-1000:]}")
        return done.stdout

    def push(self, index: int, *paths: str) -> None:
        """Copy these paths of the share to /share on the machine (the cloud kernel has no 9p)."""
        tar = subprocess.Popen(["tar", "-C", str(self.share), "-cf", "-", *paths], stdout=subprocess.PIPE)
        done = subprocess.run(
            ["ssh", "-i", str(self.key), "-p", str(ssh_port(index)),
             "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             "-o", "LogLevel=ERROR", "-o", "BatchMode=yes", "root@127.0.0.1",
             "mkdir -p /share && tar -xf - -C /share"],
            stdin=tar.stdout,
            capture_output=True,
            timeout=600,
        )
        tar.wait()
        if done.returncode != 0 or tar.returncode != 0:
            raise RuntimeError(f"vm{index}: push {paths}: {done.stderr.decode()[-500:]}")

    def reachable(self, index: int) -> bool:
        """Up, with its first setup done."""
        try:
            done = subprocess.run(
                ["ssh", "-i", str(self.key), "-p", str(ssh_port(index)),
                 "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                 "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                 "root@127.0.0.1", "test -f /var/lib/psystem-ready"],
                capture_output=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return False
        return done.returncode == 0

    def power_cut(self, index: int) -> None:
        """A reset of the machine: what its disk cache held is lost, as on a power cut."""
        with socket.socket(socket.AF_UNIX) as monitor:
            monitor.connect(str(self.monitor(index)))
            monitor.recv(4096)
            monitor.sendall(b"system_reset\n")
            time.sleep(0.2)


def prepare(options) -> int:
    lab = Lab(options.lab)
    lab.base.mkdir(parents=True, exist_ok=True)
    (lab.share / "src").mkdir(parents=True, exist_ok=True)

    # Python 3.14, relocatable, and the wheels of requirements.lock: the machines need no network.
    python = sorted(Path(options.python).glob("cpython-3.14*-linux-x86_64-gnu"))
    if not python:
        raise SystemExit(f"no standalone CPython 3.14 in {options.python}: uv python install 3.14 --install-dir ...")
    if not (lab.share / "python").exists():
        shutil.copytree(python[0], lab.share / "python", symlinks=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "download", "--quiet", "--require-hashes", "-r",
         str(ROOT / "requirements.lock"), "-d", str(lab.share / "wheelhouse")],
        check=True,
    )

    # The Lean core and its runtime, as the image of the Dockerfile has them.
    from network.quorum import lean_core

    library = Path(os.environ.get("PSYSTEM_LEAN_CORE", lean_core.DEFAULT_LIBRARY))
    (lab.share / "lean").mkdir(exist_ok=True)
    shutil.copy2(library, lab.share / "lean" / "libPSystem_PSystem.so")
    shutil.copy2(lean_core._lean_prefix() / "lib" / "lean" / "libleanshared.so", lab.share / "lean")

    lab.key.parent.mkdir(exist_ok=True)
    if not lab.key.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(lab.key)], check=True)

    for index in range(COUNT):
        if not lab.disk(index).exists():
            subprocess.run(
                ["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2",
                 "-b", str(Path(options.image).resolve()), str(lab.disk(index)), "8G"],
                check=True,
            )
        write_seed(lab, index)

    (lab.share / "setup.sh").write_text(SETUP)
    shutil.copy2(ROOT / "scripts" / "byzantine_member.py", lab.share / "byzantine_member.py")
    sync_source(lab)
    print(json.dumps({"lab": str(lab.base)}))
    return 0


def sync_source(lab: Lab) -> None:
    """The code the nodes run: this checkout, copied whole each time."""
    target = lab.share / "src"
    for name in ("core", "crypto", "network", "sdk"):
        shutil.rmtree(target / name, ignore_errors=True)
        shutil.copytree(ROOT / name, target / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "requirements.lock", target)
    shutil.copy2(ROOT / "scripts" / "byzantine_member.py", lab.share / "byzantine_member.py")


def write_seed(lab: Lab, index: int) -> None:
    directory = lab.seed / f"vm{index}"
    directory.mkdir(parents=True, exist_ok=True)
    key = (lab.key.with_suffix(".pub")).read_text().strip()
    (directory / "meta-data").write_text(f"instance-id: psystem-vm{index}\nlocal-hostname: vm{index}\n")
    (directory / "user-data").write_text(
        f"""#cloud-config
disable_root: false
ssh_pwauth: false
users:
  - name: root
    ssh_authorized_keys: ["{key}"]
"""
    )
    (directory / "network-config").write_text(
        f"""version: 2
ethernets:
  wan0:
    match: {{macaddress: "{mac(index, 0)}"}}
    set-name: wan0
    dhcp4: true
  {INTERFACE}:
    match: {{macaddress: "{mac(index, 1)}"}}
    set-name: {INTERFACE}
    addresses: [{lan_address(index)}/24]
"""
    )


# Run once, as root, by cloud-init on the first boot.
SETUP = r"""set -eu
index="$1"
cp -a /share/python /opt/python
/opt/python/bin/python3.14 -m venv /opt/psystem/venv
/opt/psystem/venv/bin/pip install --quiet --no-index --find-links /share/wheelhouse --require-hashes \
    -r /share/src/requirements.lock
mkdir -p /opt/lean/lib/lean /opt/psystem/lib
cp /share/lean/libleanshared.so /opt/lean/lib/lean/
cp /share/lean/libPSystem_PSystem.so /opt/psystem/lib/
cat > /usr/local/bin/psystem-node <<'EOF'
#!/bin/sh
# The node of this machine, or member 3 without its vote lock when the deployment says so.
set -eu
rm -rf /opt/psystem/src && cp -a /share/src /opt/psystem/src
config="$(cat /var/lib/psystem/config)"
create=""
[ -f "$(dirname "$config")/votes.sqlite" ] || create="--create-store"
program="-m network.cli"
[ -f /var/lib/psystem/byzantine ] && program="/share/byzantine_member.py"
exec /opt/psystem/venv/bin/python $program node --config "$config" $create
EOF
chmod +x /usr/local/bin/psystem-node
cat > /etc/systemd/system/psystem.service <<'EOF'
[Unit]
Description=P-System node
After=network-online.target
ConditionPathExists=/var/lib/psystem/config

[Service]
Environment=PYTHONPATH=/opt/psystem/src
Environment=PSYSTEM_LEAN_CORE=/opt/psystem/lib/libPSystem_PSystem.so
Environment=PSYSTEM_LEAN_PREFIX=/opt/lean
ExecStart=/usr/local/bin/psystem-node
Restart=no
StandardOutput=append:/var/log/psystem.log
StandardError=append:/var/log/psystem.log

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable psystem.service
touch /etc/cloud/cloud-init.disabled
touch /var/lib/psystem-ready
"""


class SeedServer:
    """The NoCloud data of cloud-init, over HTTP: QEMU's user network shows the host as 10.0.2.2."""

    def __init__(self, directory: Path) -> None:
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **k)  # noqa: E731
        handler.log_message = lambda *a: None
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


def start_vm(lab: Lab, index: int, seed_port: int) -> None:
    subprocess.run(
        [
            "qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-smp", "1", "-m", str(MEMORY_MB),
            "-name", f"psystem-vm{index}",
            "-drive", f"file={lab.disk(index)},if=virtio,cache=writeback",
            "-netdev", f"user,id=wan,hostfwd=tcp:127.0.0.1:{ssh_port(index)}-:22,"
                       f"hostfwd=tcp:127.0.0.1:{api_port(index)}-:{API_PORT}",
            "-device", f"virtio-net-pci,netdev=wan,mac={mac(index, 0)}",
            "-netdev", f"socket,id=lan,mcast={MULTICAST},localaddr=127.0.0.1",
            "-device", f"virtio-net-pci,netdev=lan,mac={mac(index, 1)}",
            "-smbios", f"type=1,serial=ds=nocloud;s=http://10.0.2.2:{seed_port}/vm{index}/",
            "-monitor", f"unix:{lab.monitor(index)},server,nowait",
            "-serial", f"file:{lab.base / f'vm{index}.console'}",
            "-display", "none", "-daemonize", "-pidfile", str(lab.pidfile(index)),
        ],
        check=True,
    )


def up(options) -> int:
    lab = Lab(options.lab)
    seeds = SeedServer(lab.seed)
    try:
        for index in range(COUNT):
            if not lab.pidfile(index).exists():
                start_vm(lab, index, seeds.port)
        deadline = time.monotonic() + options.timeout
        waiting = set(range(COUNT))
        while waiting and time.monotonic() < deadline:
            for index in sorted(waiting):
                if lab.ssh(index, "cloud-init status --wait >/dev/null 2>&1; true", timeout=300, check=False) is not None \
                        and lab.ssh(index, "echo up", timeout=20, check=False).strip() == "up":
                    if not lab.reachable(index):
                        lab.push(index, "python", "wheelhouse", "lean", "src", "setup.sh", "byzantine_member.py")
                        lab.ssh(index, f"sh /share/setup.sh {index} > /var/log/psystem-setup.log 2>&1", timeout=900)
                    waiting.discard(index)
            time.sleep(5)
        if waiting:
            raise SystemExit(f"machines not ready: {sorted(waiting)}; see {lab.base}/vm*.console")
    finally:
        seeds.close()
    kernels = [lab.ssh(index, "uname -r").strip() for index in range(COUNT)]
    print(json.dumps({"ready": True, "kernels": kernels}))
    return 0


def down(options) -> int:
    lab = Lab(options.lab)
    for index in range(COUNT):
        pidfile = lab.pidfile(index)
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 15)
            except ProcessLookupError:
                pass
            pidfile.unlink(missing_ok=True)
    return 0


# --- Campaigns -------------------------------------------------------------------------------------


def campaign(options) -> int:
    from tests.chaos import Campaign
    from tests.deployment_helpers import Deployment, wait_until
    from sdk.client import Client

    lab = Lab(options.lab)
    sync_source(lab)
    for index in range(COUNT):
        lab.ssh(index, "rm -rf /share/src /share/runs")
        lab.push(index, "src", "byzantine_member.py")

    class VmDeployment(Deployment):
        """The files of `tests/deployment_helpers.Deployment`, for the addresses of the machines."""

        def write_config(self, index: int, extra: str = "") -> None:
            from scripts.make_host_deployment import node_config

            directory = self.directory(index)
            token = directory / "api.token"
            if not token.exists():
                token.write_text(os.urandom(24).hex() + "\n")
                token.chmod(0o600)
            hosts = {self.node_id(other): lan_address(other) for other in range(self.count)}
            text = node_config(self.node_id(index), hosts, PORT, API_PORT)
            (directory / "node.toml").write_text(text.replace("sync_interval = 1.0", "sync_interval = 0.5"))

        def api_url(self, index: int) -> str:
            return f"http://127.0.0.1:{api_port(index)}"

        def token(self, index: int) -> str:
            return (self.directory(index) / "api.token").read_text().strip()

        # The machine is the process: these are the faults `kill` and its restart.
        def kill(self, index: int) -> None:
            lab.ssh(index, "systemctl kill -s KILL psystem; systemctl reset-failed psystem || true")

        def start(self, index: int, create: bool = True) -> None:
            lab.ssh(index, "systemctl start psystem")

        def start_all(self) -> None:
            for index in range(self.count):
                self.start(index)

        def stop_all(self) -> None:
            for index in range(self.count):
                lab.ssh(index, "systemctl stop psystem || true", check=False)

        def heal(self) -> None:
            for index in range(self.count):
                lab.ssh(index, heal_command(), check=False)

        def partition(self, *groups) -> None:
            group_of = {node: number for number, group in enumerate(groups) for node in group}
            for index in range(self.count):
                others = [o for o in range(self.count) if group_of[o] != group_of[index]]
                if others:
                    lab.ssh(index, partition_command(others))

        def close(self) -> None:
            self.stop_all()
            self.heal()

    class VmCampaign(Campaign):
        PROFILES = {
            "network": ("delay", "loss", "corrupt", "reorder", "throttle",
                        "partition_minority", "partition_half", "isolate_then_heal"),
            "crash": ("kill", "power_cut", "delay", "loss", "partition_minority", "isolate_then_heal"),
            "byzantine": ("delay", "loss", "partition_minority", "partition_half", "kill", "power_cut"),
        }

        def __init__(self, deployment, seed, profile, **kwargs):
            super().__init__(deployment, seed, **kwargs)
            self.profile = profile
            self.FAULTS = self.PROFILES[profile]
            self.clients = [
                Client(deployment.api_url(i), deployment.token(i), timeout=5) for i in range(deployment.count)
            ]
            self.byzantine = {COUNT - 1} if profile == "byzantine" else set()

        def _netem_all(self, rng, **options) -> None:
            for index in range(self.deployment.count):
                lab.ssh(index, netem_command(**options))

        def _apply_fault(self, seconds: float) -> None:
            rng = self.rng
            fault = rng.choice(self.FAULTS)
            nodes = list(range(self.deployment.count))
            rng.shuffle(nodes)
            self.report.faults.append(fault)

            if fault == "delay":
                self._netem_all(rng, delay=f"{rng.randint(5, 150)}ms {rng.randint(0, 50)}ms")
            elif fault == "loss":
                self._netem_all(rng, loss=f"{rng.randint(1, 25)}%")
            elif fault == "corrupt":
                for index in nodes[:2]:
                    lab.ssh(index, netem_command(corrupt=f"{rng.randint(1, 5)}%"))
            elif fault == "reorder":
                self._netem_all(rng, delay="20ms", reorder="25% 50%", duplicate="5%")
            elif fault == "throttle":
                self._netem_all(rng, rate=f"{rng.randint(64, 512)}kbit")
            elif fault == "partition_minority":
                self.deployment.partition(nodes[:1], nodes[1:])
            elif fault == "partition_half":
                self.deployment.partition(nodes[:2], nodes[2:])
            elif fault == "isolate_then_heal":
                self.deployment.partition(nodes[:1], nodes[1:])
                time.sleep(seconds / 2)
                self.deployment.heal()
            elif fault in ("kill", "power_cut"):
                victim = nodes[0]
                if not self.down:
                    self.down.add(victim)
                    if fault == "kill":
                        self.deployment.kill(victim)
                        time.sleep(seconds / 2)
                        self.deployment.start(victim)
                    else:
                        lab.power_cut(victim)
                        # The machine boots again and starts its node from its disk.
                        wait_until(lambda: lab.reachable(victim), 180)
                        wait_until(lambda: lab.ssh(victim, "systemctl is-active psystem", check=False).strip() == "active", 60)
                    self.down.discard(victim)
                    self.report.restarts += 1

            time.sleep(seconds)
            self.deployment.heal()

        def _converged(self) -> bool:
            honest = [i for i in range(self.deployment.count) if i not in self.byzantine]
            statuses = [self._try(i, lambda c: c.status()) for i in honest]
            if any(status is None for status in statuses):
                return False
            return len({(s["state_root"], s["epoch"], s["executed"]) for s in statuses}) == 1

    out = options.out
    out.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + options.hours * 3600
    seed = options.seed
    failures = 0
    runs = lab.share / "runs"

    while time.monotonic() < deadline:
        base = runs / f"{options.profile}-{seed}"
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        deployment = VmDeployment(base, extra_senders=1, balance=1_000_000)
        for index in range(COUNT):
            lab.ssh(index, "rm -rf /share/runs")
            lab.push(index, f"runs/{base.name}")
            byzantine = options.profile == "byzantine" and index == COUNT - 1
            lab.ssh(
                index,
                "systemctl stop psystem 2>/dev/null; "
                f"{heal_command()}; rm -rf /var/lib/psystem && mkdir -p /var/lib/psystem && : > /var/log/psystem.log && "
                f"cp -a /share/runs/{base.name} /var/lib/psystem/run && "
                f"echo /var/lib/psystem/run/n{index}/node.toml > /var/lib/psystem/config && "
                + ("touch /var/lib/psystem/byzantine && " if byzantine else "")
                + "sync",
            )
        deployment.start_all()
        started = time.time()
        change = Campaign.change_committee if seed % 2 else None
        try:
            run = VmCampaign(deployment, seed, options.profile, epoch_change=change)
            report = run.run(seconds=options.campaign_seconds, fault_seconds=options.fault_seconds)
        except Exception as error:  # noqa: BLE001 - a campaign that cannot finish is a result too
            report = None
            counts = []
            failure = repr(error)
        finally:
            # Decisions by round: commit certificates (precommits), against those of round 0 by all.
            counts = lab.ssh(
                0,
                "/opt/psystem/venv/bin/python -c \"import sqlite3; c = sqlite3.connect("
                f"'/var/lib/psystem/run/n0/votes.sqlite'); rows = c.execute('SELECT signatures FROM certificates')"
                ".fetchall(); print(sum('precommit' in r[0] for r in rows), len(rows))\"",
                check=False,
            ).split()
            logs = base / "logs"
            logs.mkdir(exist_ok=True)
            for index in range(COUNT):
                text = lab.ssh(index, "tail -c 2000000 /var/log/psystem.log", check=False, timeout=120)
                (logs / f"vm{index}.log").write_text(text)
            deployment.close()

        line = {
            "kind": "vm-campaign",
            "date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "profile": options.profile,
            "machines": COUNT,
            "seconds": round(time.time() - started),
            "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.strip(),
        }
        if report is None:
            line.update({"seed": seed, "safe": False, "problems": [f"campaign did not finish: {failure}"]})
        else:
            line.update(json.loads(report.to_json()))
        if len(counts) == 2:
            line["decided_by_rounds"], line["decisions_on_node_0"] = int(counts[0]), int(counts[1])
        if options.profile == "byzantine":
            # The attack happened: the second versions member 3 signed against its own lock.
            line["byzantine_second_versions"] = (logs / f"vm{COUNT - 1}.log").read_text().count(
                "byzantine: signed a version the lock refuses"
            )
        with out.open("a") as handle:
            handle.write(json.dumps(line) + "\n")
        print(json.dumps(line), flush=True)
        failures += not line["safe"]
        if not line["safe"]:
            (base / "KEEP").touch()
        else:
            shutil.rmtree(base, ignore_errors=True)
        seed += 1

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("lab", type=Path)
    p.add_argument("--image", required=True, help="a Debian 13 genericcloud qcow2, checked by the caller")
    p.add_argument("--python", default=str(Path.home() / ".local/share/uv/python"))
    u = commands.add_parser("up")
    u.add_argument("lab", type=Path)
    u.add_argument("--timeout", type=float, default=900)
    d = commands.add_parser("down")
    d.add_argument("lab", type=Path)
    c = commands.add_parser("campaign")
    c.add_argument("lab", type=Path)
    c.add_argument("--profile", choices=["network", "crash", "byzantine"], required=True)
    c.add_argument("--hours", type=float, required=True)
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--campaign-seconds", type=float, default=600)
    c.add_argument("--fault-seconds", type=float, default=8)
    c.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()
    return {"prepare": prepare, "up": up, "down": down, "campaign": campaign}[options.action](options)


if __name__ == "__main__":
    sys.exit(main())
