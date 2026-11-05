"""Four nodes in containers, each on a network of its own, with latency and loss through tc netem.

    python scripts/netem_lab.py measure lab --delay 25 --jitter 5 --loss 0.1 --out results.jsonl

Each node is on its own Docker network, and a router container joins them all. Every packet between two
nodes crosses the router, and `tc netem` on each of its interfaces adds the delay and the loss on the way
out, so the delay given here is each way and a round trip takes twice that. To isolate a node the router
takes its interface down, which stops both directions.

**This is one machine.** The nodes share its CPU and its disk, so a heavy load measures that too. What it
adds to tests/chaos.py is the kernel network stack with a real delay and real loss between containers.
It does not replace a run on separate machines: see docs/OPERATIONS.md.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.make_host_deployment import write_deployment  # noqa: E402

COUNT = 4
PROJECT = "psystem-netem"
IMAGE = "psystem-netem:lab"
PORT = 7000
API_PORT = 8080
BASE_API_PORT = 18080


def node_address(index: int) -> str:
    return f"172.30.{index}.10"


def router_address(index: int) -> str:
    return f"172.30.{index}.2"


def compose_file(base: Path, uid: int, gid: int) -> str:
    """Nodes run as this user, with no capabilities: the route goes in from outside, once they are up."""
    lines = ["services:"]

    for index in range(COUNT):
        name = f"node-{index}"
        lines.append(
            f"""  {name}:
    image: {IMAGE}
    user: "{uid}:{gid}"
    command: ["node", "--config", "/data/{name}/node.toml"]
    working_dir: /data/{name}
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges:true"]
    ports:
      - "127.0.0.1:{BASE_API_PORT + index}:{API_PORT}"
    volumes:
      - {base}:/data
    networks:
      net{index}:
        ipv4_address: {node_address(index)}"""
        )

    lines.append(
        f"""  router:
    image: {IMAGE}
    entrypoint: ["sleep", "infinity"]
    cap_add: ["NET_ADMIN"]
    sysctls:
      net.ipv4.ip_forward: "1"
    networks:"""
    )

    for index in range(COUNT):
        lines.append(f"      net{index}:\n        ipv4_address: {router_address(index)}")

    lines.append("networks:")

    for index in range(COUNT):
        lines.append(
            f"""  net{index}:
    ipam:
      config:
        - subnet: 172.30.{index}.0/24"""
        )

    return "\n".join(lines) + "\n"


def netem_arguments(delay_ms: float, jitter_ms: float, loss_percent: float) -> list[str]:
    arguments = ["netem"]

    if delay_ms:
        arguments += ["delay", f"{delay_ms}ms"]

        if jitter_ms:
            arguments += [f"{jitter_ms}ms"]

    if loss_percent:
        arguments += ["loss", f"{loss_percent}%"]

    return arguments


def run(*command: str, capture: bool = False) -> str:
    done = subprocess.run(command, check=True, capture_output=capture, text=True)
    return done.stdout if capture else ""


def compose(base: Path, *arguments: str) -> None:
    run("docker", "compose", "-p", PROJECT, "-f", str(base / "docker-compose.yml"), *arguments)


def as_root(service: str, *command: str, capture: bool = False) -> str:
    return run(
        "docker", "exec", "--privileged", "-u", "root", f"{PROJECT}-{service}-1", *command,
        capture=capture,
    )


def router_interface(index: int) -> str:
    """Which interface of the router faces node `index`: Docker does not promise the order."""
    for line in as_root("router", "ip", "-o", "-4", "addr", capture=True).splitlines():
        fields = line.split()

        if fields[3].startswith(router_address(index) + "/"):
            return fields[1]

    raise RuntimeError(f"NO INTERFACE OF THE ROUTER FACES NODE {index}")


def set_network(delay_ms: float, jitter_ms: float, loss_percent: float) -> None:
    for index in range(COUNT):
        arguments = netem_arguments(delay_ms, jitter_ms, loss_percent)

        if len(arguments) > 1:
            as_root("router", "tc", "qdisc", "replace", "dev", router_interface(index), "root", *arguments)


def add_routes() -> None:
    for index in range(COUNT):
        as_root(f"node-{index}", "ip", "route", "add", "172.30.0.0/16", "via", router_address(index))


def round_trip_ms(samples: int = 20) -> float:
    """Measured, from node 0 to node 3, by the time of a TCP connection: did the emulation take?"""
    code = (
        "import socket,statistics,time\n"
        "times=[]\n"
        f"for _ in range({samples}):\n"
        "    started=time.perf_counter()\n"
        f"    socket.create_connection(('{node_address(COUNT - 1)}',{PORT}),timeout=5).close()\n"
        "    times.append(time.perf_counter()-started)\n"
        "print(statistics.median(times)*1000)\n"
    )
    return round(float(as_root("node-0", "python", "-c", code, capture=True)), 1)


def build_image() -> None:
    run("docker", "build", "-q", "-t", IMAGE, "-f", str(ROOT / "deploy" / "netem" / "Dockerfile"), str(ROOT))


def isolate_command(interface: str) -> str:
    return f"docker exec --privileged -u root {PROJECT}-router-1 ip link set {interface} down"


def heal_command(interface: str) -> str:
    return f"docker exec --privileged -u root {PROJECT}-router-1 ip link set {interface} up"


def measure(options) -> int:
    import os

    base = options.directory.resolve()
    hosts = {f"node-{index}": node_address(index) for index in range(COUNT)}
    write_deployment(base, hosts, PORT, API_PORT)
    (base / "docker-compose.yml").write_text(compose_file(base, os.getuid(), os.getgid()))
    build_image()

    try:
        compose(base, "up", "-d", "--wait")
        add_routes()
        set_network(options.delay, options.jitter, options.loss)
        interface = router_interface(COUNT - 1)
        round_trip = round_trip_ms()
        arguments = [
            sys.executable, str(ROOT / "scripts" / "measure_network.py"),
            "--sender-key", str(base / "sender.key"),
            "--latency-events", str(options.latency_events),
            "--throughput-events", str(options.throughput_events),
            "--recovery-events", str(options.recovery_events),
            "--isolate", isolate_command(interface),
            "--heal", heal_command(interface),
        ]

        for index in range(COUNT):
            arguments += [
                "--api",
                f"http://127.0.0.1:{BASE_API_PORT + index}={base / f'node-{index}' / 'api.token'}",
            ]

        output = subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=3600)
        result = {
            "delay_ms_each_way": options.delay,
            "jitter_ms": options.jitter,
            "loss_percent": options.loss,
            "measured_round_trip_ms": round_trip,
            **json.loads(output.stdout),
        }
        print(json.dumps(result))

        if options.out:
            with options.out.open("a") as out:
                out.write(json.dumps(result) + "\n")

        return 0 if result["same_state_on_all"] else 1
    finally:
        compose(base, "down", "-v", "--timeout", "5")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["measure"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--delay", type=float, default=0.0, help="milliseconds each way")
    parser.add_argument("--jitter", type=float, default=0.0)
    parser.add_argument("--loss", type=float, default=0.0, help="percent, each way")
    parser.add_argument("--latency-events", type=int, default=100)
    parser.add_argument("--throughput-events", type=int, default=2000)
    parser.add_argument("--recovery-events", type=int, default=1000)
    parser.add_argument("--out", type=Path)
    return measure(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
