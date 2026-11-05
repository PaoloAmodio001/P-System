"""Network faults injected between real processes, and the checks that must hold whatever they do.

Every link between two nodes passes through a proxy in this process, which delays, stalls, cuts,
corrupts and throttles real TLS traffic. TLS and TCP turn these into what a node can see: a late
byte, a dead connection, a peer that stops reading. Messages cannot be reordered or dropped one by
one under TLS, so these faults reach the node only as lost connections.

`Campaign.run` drives traffic and faults, then heals the network and checks:

- at most one event with a certificate for each (sender, nonce), over what all nodes say;
- every certificate verifies against the chain, without trusting any node;
- once healed, all nodes reach one state root, and no node halted;
- every transfer of an honest sender becomes final once healed;
- balances add up to what the genesis gave.

This is EMPIRICAL: one machine, these faults, these seeds. Campaigns are repeatable in their
choices, not in their timing.
"""

import json
import random
import socket
import threading
import time
from dataclasses import dataclass, field

from core.attestation import EpochChange
from core.event import Transfer
from core.signed_event import SignedTransfer
from crypto.identity import Identity
from network.deployment import read_genesis
from network.message import decode_certificate, encode_epoch_change
from sdk.client import ApiError, ChainVerifier, Client, Wallet
from tests.deployment_helpers import Deployment, free_port, wait_until

CHUNK = 65536


class Link:
    """One direction of connection between two nodes: what the proxy does to it right now."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.delay = 0.0
        self.jitter = 0.0
        self.blocked = False
        self.stalled = False
        self.corrupt_chance = 0.0
        self.cut_chance = 0.0
        self.bytes_per_second = 0
        self.generation = 0

    def clear(self) -> None:
        self.delay = self.jitter = self.corrupt_chance = self.cut_chance = 0.0
        self.blocked = self.stalled = False
        self.bytes_per_second = 0

    def cut(self) -> None:
        self.generation += 1


class Proxy:
    def __init__(self, target_port: int, link: Link) -> None:
        self.target_port = target_port
        self.link = link
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self.port = self._listener.getsockname()[1]
        self._running = True
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while self._running:
            try:
                client, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return

            if self.link.blocked:
                client.close()
                continue

            try:
                server = socket.create_connection(("127.0.0.1", self.target_port), timeout=1)
            except OSError:
                client.close()
                continue

            generation = self.link.generation
            for source, target in ((client, server), (server, client)):
                threading.Thread(
                    target=self._forward,
                    args=(source, target, generation),
                    daemon=True,
                ).start()

    def _forward(self, source: socket.socket, target: socket.socket, generation: int) -> None:
        link = self.link
        source.settimeout(0.2)

        try:
            while self._running and link.generation == generation and not link.blocked:
                if link.stalled:
                    time.sleep(0.05)
                    continue

                try:
                    data = source.recv(CHUNK)
                except TimeoutError:
                    continue

                if not data:
                    return

                if link.rng.random() < link.cut_chance:
                    return

                if link.rng.random() < link.corrupt_chance:
                    position = link.rng.randrange(len(data))
                    data = data[:position] + bytes([data[position] ^ 0x40]) + data[position + 1:]

                wait = link.delay + link.rng.random() * link.jitter

                if link.bytes_per_second:
                    wait += len(data) / link.bytes_per_second

                if wait:
                    time.sleep(wait)

                # Bytes written before the link stalled may still be written: a stall holds
                # what comes after them, as a full buffer would.
                target.settimeout(10)
                target.sendall(data)
        except OSError:
            pass
        finally:
            for side in (source, target):
                try:
                    side.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                side.close()

    def close(self) -> None:
        self._running = False
        self._listener.close()


class ChaosDeployment(Deployment):
    """A deployment whose nodes reach each other only through proxies."""

    def __init__(self, base, rng: random.Random, **options) -> None:
        self.rng = rng
        self.proxy_ports = {}
        self._reserve = options.get("nodes", 4)

        for index in range(self._reserve):
            for other in range(self._reserve):
                if index != other:
                    self.proxy_ports[(index, other)] = free_port()

        super().__init__(base, **options)
        self.links = {}
        self.proxies = []

        for (index, other), _ in self.proxy_ports.items():
            link = Link(random.Random(rng.random()))
            proxy = Proxy(self.ports[other], link)
            self.links[(index, other)] = link
            self.proxies.append(proxy)
            self.proxy_ports[(index, other)] = proxy.port

        for index in range(self.count):
            self.write_config(index)

    def peer_port(self, index: int, other: int) -> int:
        return self.proxy_ports[(index, other)]

    def heal(self) -> None:
        for link in self.links.values():
            link.clear()

    def partition(self, *groups) -> None:
        group_of = {node: number for number, group in enumerate(groups) for node in group}
        for (index, other), link in self.links.items():
            if group_of[index] != group_of[other]:
                link.blocked = True

    def close(self) -> None:
        self.stop_all()
        for proxy in self.proxies:
            proxy.close()


@dataclass
class Report:
    seed: int
    faults: list[str] = field(default_factory=list)
    restarts: int = 0
    submitted: int = 0
    honest_final: int = 0
    equivocations: int = 0
    certified_alternatives: int = 0
    epoch: int = 0
    seconds_to_converge: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.problems

    def to_json(self) -> str:
        return json.dumps({**self.__dict__, "safe": self.safe})


class Campaign:
    FAULTS = (
        "delay",
        "partition_minority",
        "partition_half",
        "isolate_then_heal",
        "stall_link",
        "corrupt",
        "cut",
        "throttle",
        "kill",
    )

    def __init__(self, deployment: ChaosDeployment, seed: int, epoch_change=None) -> None:
        self.deployment = deployment
        self.rng = random.Random(seed)
        self.report = Report(seed)
        self.clients = [Client(deployment.api_url(i), timeout=5) for i in range(deployment.count)]
        self.down: set[int] = set()
        self.honest_identity = Identity.load(deployment.sender_key)
        self.honest_events: list[SignedTransfer] = []
        self.equivocator = Identity.load(deployment.extra_sender_keys[0])
        self.equivocator_nonce = 0
        self.known: dict[tuple[str, int], list[Transfer]] = {}
        self.stop_traffic = threading.Event()
        self.epoch_change = epoch_change
        self.ordered_change = None

    def _try(self, index: int, call):
        if index in self.down:
            return None
        try:
            return call(self.clients[index])
        except (ApiError, OSError, ValueError):
            return None

    def _remember(self, signed: SignedTransfer) -> None:
        event = signed.transfer
        found = self.known.setdefault((event.sender, event.nonce), [])
        if event not in found:
            found.append(event)

    def _traffic(self) -> None:
        rng = random.Random(self.rng.random())
        # A wallet stays in the thread that opened it.
        wallet = Wallet(self.honest_identity, self.deployment.base / "wallet.sqlite")
        while not self.stop_traffic.is_set():
            if rng.random() < 0.8:
                signed = wallet.transfer(rng.choice(("bob", "carol")), 1)
                self.honest_events.append(signed)
                self._remember(signed)
                self._try(rng.randrange(self.deployment.count), lambda c: c.submit(signed))
                self.report.submitted += 1
            else:
                # Two versions of one spend, to different nodes.
                nonce = self.equivocator_nonce
                self.equivocator_nonce += 1
                self.report.equivocations += 1
                sender = self.equivocator.identity_id
                versions = [
                    SignedTransfer.create(self.equivocator, Transfer(sender, receiver, 1, nonce))
                    for receiver in ("bob", "carol")
                ]
                nodes = rng.sample(range(self.deployment.count), 2)
                for version, node in zip(versions, nodes):
                    self._remember(version)
                    self._try(node, lambda c, v=version: c.submit(v))
            time.sleep(rng.uniform(0.02, 0.15))
        wallet.close()

    def _apply_fault(self, seconds: float) -> None:
        deployment = self.deployment
        rng = self.rng
        fault = rng.choice(self.FAULTS)
        nodes = list(range(deployment.count))
        rng.shuffle(nodes)
        self.report.faults.append(fault)
        links = list(deployment.links.values())

        if fault == "delay":
            for link in links:
                link.delay = rng.uniform(0.005, 0.1)
                link.jitter = rng.uniform(0.0, 0.1)
        elif fault == "partition_minority":
            deployment.partition(nodes[:1], nodes[1:])
        elif fault == "partition_half":
            half = len(nodes) // 2
            deployment.partition(nodes[:half], nodes[half:])
        elif fault == "isolate_then_heal":
            deployment.partition(nodes[:1], nodes[1:])
            time.sleep(seconds / 2)
            deployment.heal()
        elif fault == "stall_link":
            for link in rng.sample(links, 3):
                link.stalled = True
        elif fault == "corrupt":
            for link in rng.sample(links, 3):
                link.corrupt_chance = 0.1
        elif fault == "cut":
            for link in links:
                link.cut_chance = 0.02
                link.cut()
        elif fault == "throttle":
            for link in links:
                link.bytes_per_second = rng.randint(2_000, 50_000)
        elif fault == "kill":
            victim = nodes[0]
            if victim not in self.down and not self.down:
                self.down.add(victim)
                deployment.kill(victim)
                time.sleep(seconds / 2)
                deployment.start(victim, create=False)
                self.down.discard(victim)
                self.report.restarts += 1

        time.sleep(seconds)
        deployment.heal()

    def _finish_honest(self, seconds: float) -> None:
        """Nothing here can be final until the network heals. Then each transfer is sent again."""
        deadline = time.monotonic() + seconds
        verifier = self._verifier()

        while time.monotonic() < deadline:
            missing = [
                signed
                for signed in self.honest_events
                if self._try(0, lambda c, e=signed.transfer: c.certificate(e.event_id())) is None
            ]

            if not missing:
                self.report.honest_final = len(self.honest_events)
                return

            for signed in missing[:200]:
                for index in range(self.deployment.count):
                    self._try(index, lambda c, s=signed: c.submit(s))

            time.sleep(0.5)

        self.report.problems.append(
            f"honest transfers not final after healing: {len(missing)}"
        )

    def _verifier(self) -> ChainVerifier:
        genesis = read_genesis(self.deployment.base / "genesis.json")
        verifier = ChainVerifier(genesis.committee, genesis.governance)
        closures = self._try(0, lambda c: c.closures())
        if closures:
            verifier.add_closures(closures)
        return verifier

    def _check_safety(self) -> None:
        report = self.report
        verifier = self._verifier()

        for key, events in self.known.items():
            certified = set()

            for event in events:
                for index in range(self.deployment.count):
                    body = self._try(index, lambda c, e=event: c.certificate(e.event_id()))
                    if body is None:
                        continue
                    certified.add(event.canonical())
                    if not verifier.verify(decode_certificate(body)):
                        report.problems.append(f"certificate does not verify: {event.event_id()}")

            if len(certified) > 1:
                report.problems.append(f"two certified alternatives for {key}")
            report.certified_alternatives += len(certified)

    def _converged(self) -> bool:
        statuses = [self._try(i, lambda c: c.status()) for i in range(self.deployment.count)]
        if any(status is None for status in statuses):
            return False
        return len({(s["state_root"], s["epoch"], s["executed"]) for s in statuses}) == 1

    def run(self, seconds: float, fault_seconds: float = 2.0, settle_seconds: float = 120.0) -> Report:
        deployment = self.deployment
        report = self.report
        assert wait_until(
            lambda: all(len(c.status()["peers"]) == deployment.count - 1 for c in self.clients),
            60,
        )
        traffic = threading.Thread(target=self._traffic, daemon=True)
        traffic.start()
        deadline = time.monotonic() + seconds
        half = time.monotonic() + seconds / 2
        changed = False

        while time.monotonic() < deadline:
            self._apply_fault(fault_seconds)

            if self.epoch_change is not None and not changed and time.monotonic() > half:
                changed = True
                self.epoch_change(self)

            time.sleep(self.rng.uniform(0.0, 0.5))

        self.stop_traffic.set()
        traffic.join(10)
        deployment.heal()
        started = time.monotonic()

        # A proposer may have died with its order. An operator sees the epoch did not change
        # and sends the order again, to any node.
        if self.ordered_change is not None:
            self._order_change(self.rng.randrange(deployment.count))

        self._finish_honest(settle_seconds)

        if not wait_until(self._converged, settle_seconds):
            report.problems.append("nodes did not converge after healing")

        report.seconds_to_converge = round(time.monotonic() - started, 1)

        for index, client in enumerate(self.clients):
            status = self._try(index, lambda c: c.status())
            if status is None:
                report.problems.append(f"node {index} does not answer")
                continue
            report.epoch = max(report.epoch, status["epoch"])
            if status["halted"]:
                report.problems.append(f"node {index} halted")
            if status["conflicted"]:
                report.problems.append(f"node {index} conflicted")

        self._check_safety()
        self._check_balances()
        return report

    def change_committee(self) -> None:
        """An order to change epoch, to one node. Sent again to another if it never closes."""
        genesis = read_genesis(self.deployment.base / "genesis.json")
        signers = [Identity.load(path) for path in self.deployment.governance_keys[:2]]
        keys = [bytes.fromhex(member["public_key"]) for member in self.deployment.members]
        self.ordered_change = EpochChange.create(
            genesis.committee, keys, genesis.committee.f, genesis.governance, signers
        )
        self.report.faults.append("epoch_change")
        self._order_change(self.rng.randrange(self.deployment.count))

    def _order_change(self, index: int) -> None:
        body = encode_epoch_change(self.ordered_change)["change"]
        self._try(index, lambda c: c._request("POST", "/v1/epoch-changes", body))

    def _check_balances(self) -> None:
        accounts = {"bob", "carol", self.honest_identity.identity_id, self.equivocator.identity_id}
        client = self.clients[0]
        total = sum(client.account(account)["balance"] for account in accounts)
        expected = 2 * self.deployment.balance_per_sender
        if total != expected:
            self.report.problems.append(f"balances add up to {total}, not {expected}")
