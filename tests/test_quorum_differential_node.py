"""Differential test B: a real Node in quorum mode vs the Lean model runNode.

Differential A compares QuorumReplica. This one goes through what surrounds it: encoded
messages into Node._handle_peer_message, the driver, the buffer, and the public fields
of the node. After EACH message, the public state, the log and the votes read from the
file through a separate connection must be what runNode computes.

This is EMPIRICAL evidence of correspondence, not a refinement proof.

The input for Lean comes from the messages and not from what the node did. If it came
from a trace of the replica, the code under test would choose its own input. So a small
oracle here, which uses nothing of network/quorum.py, turns each message into inputs of
the model, by the rules of the protocol:

- A request with a valid signature by its sender is a `voteRequest`. One with a bad
  signature, or signed by someone else, is no input at all: the model has no message,
  and `auth` there depends only on the event.
- An event whose sender is not an identity can never be authorized. That one is a line
  `U` for Lean, so `auth` refuses it there too.
- After each valid certificate, all those seen since the last restart are tried again in
  order of id until nothing can change. The model needs no buffer, because delivering an
  input again is the same as trying again, and this is that delivery.
- A restart loses the buffer: only what ran is still known afterwards.

The trace of the replica is a second comparison: run through Lean, it must end in the same
state. It would catch inputs that the oracle and the node agree on for the wrong reason.

The halt is not in the model, since runNode does not stop. The comparison holds up to the
halt, and from there the oracle gives no more inputs: the expected state is frozen. The
trace stops there too: the driver still asks the replica after a halt, and the store
refuses, which Lean, having no halt, would not.

Not covered here: id collisions, because the decoder rebuilds the event, so differential A
keeps those. Cases are for one node: several nodes are in tests/test_quorum_node.py, and on
real TLS later. Evidence (SIGNED_TRANSFER and the like) must be no input at all.

Runs on the seeds of differential A, with PSYSTEM_DIFF_SEEDS.
"""

import json
import os
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.attestation import Committee, QuorumCertificate, Vote, vote_payload
from core.decision_status import DecisionStatus
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    encode_certificate,
    encode_signed_transfer,
    encode_vote,
    encode_vote_request,
)
from network.node import Node
from network.quorum import QuorumConfig, VoteStoreError
from network.reconciliation_protocol import KnowledgeResponse
from tests.test_quorum_check_driver import _run, quorum_check  # noqa: F401
from tests.test_quorum_differential import (
    _NO_EVENT,
    IDENTITIES,
    NEGATIVE,
    SEEDS,
    VALID,
    Entry,
    _event_id_as_nat,
    _lean_entry,
    _lean_event,
    _python_vote,
    _random_entries,
    _signed,
    _split_outputs,
)

CASES = int(os.environ.get("PSYSTEM_DIFF_NODE_CASES", "500"))
MIN_SEEN = 25


def _fixed_identity(value: int) -> Identity:
    return Identity(Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32))


SENDERS = [_fixed_identity(value) for value in (41, 42, 43)]
SENDER_BY_ID = {identity.identity_id: identity for identity in SENDERS}
# No key has this identity: nothing it "sends" can ever be authorized.
ALIAS = "alias-with-no-identity"
ACCOUNTS = [identity.identity_id for identity in SENDERS] + [ALIAS, "dave"]


@dataclass
class NodeCase:
    f: int
    balances: dict[str, int]
    nonces: dict[str, int]
    pool: list[Transfer] = field(default_factory=list)
    messages: list[tuple] = field(default_factory=list)


# --- The oracle: from messages to inputs of the model ----------------------


@dataclass
class Plan:
    """What the oracle expects. `ends[i]` is how many inputs follow message i."""

    inputs: list[str] = field(default_factory=list)
    ends: list[int] = field(default_factory=list)
    replies: list[bool] = field(default_factory=list)
    broadcasts: list[list[str]] = field(default_factory=list)
    malformed: list[bool] = field(default_factory=list)
    halted: list[bool] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _authorized(event: Transfer, kind: str = VALID) -> bool:
    return kind == VALID and event.sender in SENDER_BY_ID


def _entries_are_valid(entries, quorum: int) -> bool:
    validators = [entry.validator for entry in entries]
    return (
        all(entry.kind == VALID for entry in entries)
        and len(set(validators)) == len(validators)
        and len(validators) >= quorum
    )


def _lean_header(case: NodeCase) -> list[str]:
    lines = [f"N {3 * case.f + 1}", f"Q {2 * case.f + 1}"]
    lines += [
        f"A {name} {case.balances[name]} {case.nonces.get(name, 0)}"
        for name in ACCOUNTS
    ]
    # Unauthorizable: a sender that no signature can match, as the auth of the model.
    lines += [
        f"U {_event_id_as_nat(event)}"
        for event in case.pool
        if event.sender not in SENDER_BY_ID
    ]
    return lines


def _executed_ids(driver: Path, directory: Path, case: NodeCase, inputs) -> list[int]:
    run = _run(driver, directory, "\n".join(_lean_header(case) + inputs) + "\n")
    assert run.returncode == 0, run.stderr
    [lines] = _split_outputs(run.stdout)
    section = lines[-1].split(";")[1].removeprefix("exec=")
    return [] if section == "-" else [int(value) for value in section.split(",")]


def _valid_entry_line(event: Transfer, validators) -> str:
    entries = ";".join(f"{v}:{v}:{_signed(event)}" for v in validators)
    return f"C {_lean_event(event)} {entries}"


def make_plan(case: NodeCase, driver: Path, directory: Path) -> Plan:
    plan = Plan()
    quorum = 2 * case.f + 1
    n = 3 * case.f + 1
    own = 0
    votes_held: dict[tuple, bytes] = {}
    known: dict[tuple, bytes] = {}
    seen: dict[bytes, tuple] = {}
    collecting: dict[bytes, tuple[Transfer, set[int]]] = {}
    halted = False
    by_id = {_event_id_as_nat(event): event for event in case.pool}

    def count(name: str, amount: int = 1) -> None:
        plan.stats[name] = plan.stats.get(name, 0) + amount

    def accept(event: Transfer, line: str) -> None:
        """A valid certificate reaches the node. The rule that needs a test here."""
        nonlocal halted
        key = (event.sender, event.nonce)
        canonical = event.canonical()
        holder = known.get(key)

        if holder is not None and holder != canonical:
            halted = True
            collecting.clear()
            count("halts")
            return

        if holder is None:
            known[key] = canonical
            seen[canonical] = (event, line)

        for _ in range(len(seen) + 1):
            for _id, _canonical, retried in sorted(
                (item[0].event_id(), name, item[1]) for name, item in seen.items()
            ):
                plan.inputs.append(retried)

    def vote_for(event: Transfer) -> bool:
        key = (event.sender, event.nonce)
        canonical = event.canonical()
        plan.inputs.append(f"V {_lean_event(event)}")
        if votes_held.get(key, canonical) != canonical:
            count("votes refused by the lock")
            return False
        votes_held[key] = canonical
        count("votes given")
        return True

    for message in case.messages:
        kind = message[0]
        reply = False
        broadcast: list[str] = []
        malformed = False

        if kind == "REQUEST":
            _, event, signer_kind = message
            if not halted and _authorized(event, signer_kind):
                reply = vote_for(event)
            elif not halted and signer_kind == VALID:
                # Signed by the sender it claims, which is no identity: the U line.
                plan.inputs.append(f"V {_lean_event(event)}")
                count("requests refused by auth")
            else:
                count("requests with a bad signature")

        elif kind == "CERTIFICATE":
            _, event, entries = message
            if any(entry.kind == NEGATIVE for entry in entries):
                malformed = True
                count("certificates that do not decode")
            elif not halted:
                line = "C {} {}".format(
                    _lean_event(event),
                    ";".join(_lean_entry(entry, event) for entry in entries) or "-",
                )
                if _entries_are_valid(entries, quorum):
                    accept(event, line)
                    count("valid certificates")
                else:
                    plan.inputs.append(line)
                    count("invalid certificates")

        elif kind == "SUBMIT":
            _, event = message
            if not halted and _authorized(event):
                key = (event.sender, event.nonce)
                if known.get(key) == event.canonical():
                    broadcast = ["CERTIFICATE"]
                    count("submits of a certified event")
                elif vote_for(event):
                    votes = collecting.setdefault(event.canonical(), (event, set()))[1]
                    votes.add(own)
                    if len(votes) >= quorum:
                        del collecting[event.canonical()]
                        accept(event, _valid_entry_line(event, sorted(votes)))
                        broadcast = ["CERTIFICATE"]
                    else:
                        broadcast = ["VOTE_REQUEST"]

        elif kind == "VOTE":
            _, event, validator, valid = message
            entry = collecting.get(event.canonical())
            if entry is not None and valid and validator < n:
                entry[1].add(validator)
                if len(entry[1]) >= quorum:
                    votes = sorted(entry[1])
                    del collecting[event.canonical()]
                    accept(event, _valid_entry_line(event, votes))
                    broadcast = ["CERTIFICATE"]
                    count("certificates made here")

        elif kind == "EVIDENCE":
            count("evidence")

        elif kind == "MALFORMED":
            malformed = True

        elif kind == "RESTART":
            count("restarts")
            collecting.clear()
            executed = _executed_ids(driver, directory, case, plan.inputs)
            if executed:
                count("restarts with a log")
            known = {
                (by_id[value].sender, by_id[value].nonce): by_id[value].canonical()
                for value in executed
            }
            seen = {}

        plan.ends.append(len(plan.inputs))
        plan.replies.append(reply)
        plan.broadcasts.append(broadcast)
        plan.malformed.append(malformed)
        plan.halted.append(halted)

    return plan


# --- The node ------------------------------------------------------------


class Connection:
    """What a peer would get. A vote leaving must already be on disk."""

    initiated_locally = True
    connected = True

    def __init__(self, votes_on_disk):
        self.sent: list[dict] = []
        self.votes_on_disk = votes_on_disk
        self.unsigned: list[str] = []

    def send(self, message: dict) -> None:
        wire = json.loads(json.dumps(message))
        if wire["type"] == "VOTE":
            transfer = wire["transfer"]
            event = Transfer(
                sender=transfer["sender"],
                receiver=transfer["receiver"],
                amount=transfer["amount"],
                nonce=transfer["nonce"],
                parents=tuple(transfer["parents"]),
            )
            if event.canonical() not in self.votes_on_disk():
                self.unsigned.append(transfer["sender"])
        self.sent.append(wire)

    def close(self) -> None:
        self.connected = False


def _signed_request(event: Transfer, signer_kind: str) -> dict:
    identity = SENDER_BY_ID.get(event.sender, SENDERS[0])
    if signer_kind == VALID:
        return encode_vote_request(SignedTransfer.create(identity, event))
    if signer_kind == "bad signature":
        return encode_vote_request(SignedTransfer(event, identity.public_key, bytes(64)))
    other = SENDERS[(SENDERS.index(identity) + 1) % len(SENDERS)]
    return encode_vote_request(SignedTransfer.create(other, event))


def _evidence_message(event: Transfer, path: str) -> dict:
    identity = SENDER_BY_ID.get(event.sender, SENDERS[0])
    signed = SignedTransfer.create(identity, event)
    if path == "SIGNED_TRANSFER":
        return encode_signed_transfer(signed)
    if path == "SIGNED_EVENT_SYNC":
        wire = encode_signed_transfer(signed)
        del wire["type"]
        return {"type": "SIGNED_EVENT_SYNC", "events": [wire]}
    return KnowledgeResponse(identities=(), events=(signed,)).encode()


@dataclass
class Result:
    lines: list[str] = field(default_factory=list)
    replies: list[bool] = field(default_factory=list)
    broadcasts: list[list[str]] = field(default_factory=list)
    malformed: list[bool] = field(default_factory=list)
    halted: list[bool] = field(default_factory=list)
    unsigned: list[str] = field(default_factory=list)
    conflicted: bool = False
    trace: list[str] = field(default_factory=list)
    store_failure: str | None = None


def run_node(case: NodeCase, directory: Path) -> Result:
    initial = State(balances=dict(case.balances), nonces=dict(case.nonces))
    identities = IDENTITIES[case.f]
    committee = Committee.create(
        [identity.public_key for identity in identities], case.f, initial
    )
    path = directory / "node-votes.sqlite"
    for leftover in directory.glob("node-votes.sqlite*"):
        leftover.unlink()
    ids = {event.canonical(): _event_id_as_nat(event) for event in case.pool}
    result = Result()

    def votes_on_disk() -> set[bytes]:
        # A separate connection: what would survive a crash at this moment.
        connection = sqlite3.connect(path)
        rows = connection.execute("SELECT canonical FROM votes").fetchall()
        connection.close()
        return {row[0].encode() for row in rows}

    def open_node(create: bool) -> Node:
        node = Node(
            "diff-node",
            initial,
            quorum=QuorumConfig(committee, identities[0], path, create=create),
        )
        replica = node._quorum.replica
        real_vote, real_certificate = (
            replica.handle_vote_request,
            replica.handle_certificate,
        )

        def traced_vote(event):
            if not replica.halted():
                result.trace.append(f"V {_lean_event(event)}")
            return real_vote(event)

        def traced_certificate(certificate):
            if not replica.halted():
                # Each signature as it is, not as the driver should have left it: an
                # invalid one reaching the replica must look invalid to Lean too.
                entries = ";".join(
                    f"{vote.validator}:{vote.validator}:{_signed(certificate.event)}"
                    if vote.verify(committee, certificate.event)
                    else f"0:0:{_NO_EVENT}"
                    for vote in certificate.votes
                ) or "-"
                result.trace.append(f"C {_lean_event(certificate.event)} {entries}")
            return real_certificate(certificate)

        replica.handle_vote_request = traced_vote
        replica.handle_certificate = traced_certificate
        return node

    def show(node: Node) -> str:
        # Part of the line, so that a difference is reported as one.
        same = "" if node.events == node.local_events else "EVENTS DIFFER;"
        votes = sorted(ids[canonical] for canonical in votes_on_disk())
        executed = [ids[event.canonical()] for event in node.local_events]
        accounts = " ".join(
            f"{name}={node.state.balance(name)}/{node.state.nonce(name)}"
            for name in ACCOUNTS
        )
        return same + (
            f"votes={','.join(map(str, votes)) or '-'};"
            f"exec={','.join(map(str, executed)) or '-'};{accounts}"
        )

    node = open_node(True)
    result.lines.append(show(node))
    peer = Connection(votes_on_disk)
    node.peer_connections["peer"] = peer

    try:
        for message in case.messages:
            kind = message[0]
            asker = Connection(votes_on_disk)
            before = len(peer.sent)
            malformed = False

            if kind == "RESTART":
                node.stop()
                node = open_node(False)
                node.peer_connections["peer"] = peer
            elif kind == "SUBMIT":
                node.submit(SignedTransfer.create(SENDER_BY_ID.get(
                    message[1].sender, SENDERS[0]
                ), message[1]))
            else:
                wire = _message_to_wire(case, message, committee, identities)
                try:
                    node._handle_peer_message(json.loads(json.dumps(wire)), asker)
                except ValueError:
                    malformed = True

            result.lines.append(show(node))
            result.replies.append(any(m["type"] == "VOTE" for m in asker.sent))
            result.broadcasts.append([m["type"] for m in peer.sent[before:]])
            result.malformed.append(malformed)
            result.halted.append(bool(node._quorum_halt_events))
            result.unsigned += asker.unsigned

        result.conflicted = node.status() == DecisionStatus.CONFLICTED
    except VoteStoreError as error:
        # Nothing in these cases can make an honest store fail, or refuse to reopen.
        result.store_failure = str(error)
    finally:
        node.stop()

    return result


def _message_to_wire(case, message, committee, identities) -> dict:
    kind = message[0]
    if kind == "REQUEST":
        return _signed_request(message[1], message[2])
    if kind == "CERTIFICATE":
        votes = tuple(
            _python_vote(committee, identities, entry, message[1])
            for entry in message[2]
        )
        return encode_certificate(QuorumCertificate(message[1], votes))
    if kind == "VOTE":
        _, event, validator, valid = message
        if validator >= len(identities):
            signature = bytes(64)
        elif valid:
            signature = identities[validator].sign(vote_payload(committee, event))
        else:
            signature = bytes((validator + 1,)) * 64
        return encode_vote(event, Vote(validator, signature))
    if kind == "EVIDENCE":
        return _evidence_message(message[1], message[2])
    if kind == "MALFORMED":
        return message[1]
    raise AssertionError(kind)


# --- Comparing -----------------------------------------------------------


def compare(case: NodeCase, plan: Plan, lean: list[str], result: Result) -> str | None:
    """The first difference, or None."""
    if result.store_failure is not None:
        return f"the store failed: {result.store_failure}"

    if result.lines[0] != lean[0]:
        return f"before any message:\n  python {result.lines[0]}\n  lean   {lean[0]}"

    for index, message in enumerate(case.messages):
        where = f"after message {index} ({message[0]})"
        expected = lean[plan.ends[index]]
        if result.lines[index + 1] != expected:
            return f"{where}:\n  python {result.lines[index + 1]}\n  lean   {expected}"
        if result.replies[index] != plan.replies[index]:
            return f"{where}: vote sent {result.replies[index]}, expected {plan.replies[index]}"
        if result.broadcasts[index] != plan.broadcasts[index]:
            return f"{where}: sent {result.broadcasts[index]}, expected {plan.broadcasts[index]}"
        if result.malformed[index] != plan.malformed[index]:
            return f"{where}: malformed {result.malformed[index]}, expected {plan.malformed[index]}"
        if result.halted[index] != plan.halted[index]:
            return f"{where}: halted {result.halted[index]}, expected {plan.halted[index]}"

    if result.unsigned:
        return f"a vote left before it was on disk: {result.unsigned[0]}"

    final_halted = plan.halted[-1] if plan.halted else False
    if result.conflicted != final_halted:
        return f"status CONFLICTED is {result.conflicted}, halted is {final_halted}"

    return None


def _lean_text(case: NodeCase, inputs: list[str]) -> str:
    return "\n".join(_lean_header(case) + inputs)


def _lean_lines(case: NodeCase, inputs, driver: Path, directory: Path) -> list[str]:
    run = _run(driver, directory, _lean_text(case, inputs) + "\n")
    assert run.returncode == 0, run.stderr
    [lines] = _split_outputs(run.stdout)
    return lines


def difference_of(case: NodeCase, driver: Path, directory: Path) -> str | None:
    plan = make_plan(case, driver, directory)
    result = run_node(case, directory)
    lean = _lean_lines(case, plan.inputs, driver, directory)
    found = compare(case, plan, lean, result)
    if found is not None:
        return found
    trace = _lean_lines(case, result.trace, driver, directory)
    if trace[-1] != result.lines[-1]:
        return f"trace of the replica:\n  python {result.lines[-1]}\n  lean   {trace[-1]}"
    return None


def minimize(case: NodeCase, driver: Path, directory: Path) -> NodeCase:
    changed = True
    while changed:
        changed = False
        for index in range(len(case.messages) - 1, -1, -1):
            candidate = NodeCase(
                case.f,
                case.balances,
                case.nonces,
                case.pool,
                case.messages[:index] + case.messages[index + 1:],
            )
            if difference_of(candidate, driver, directory) is not None:
                case = candidate
                changed = True
    return case


def describe(case: NodeCase) -> str:
    lines = [f"f={case.f} balances={case.balances} nonces={case.nonces}"]
    lines += [f"pool id={e.event_id()[:12]} {e!r}" for e in case.pool]
    for message in case.messages:
        if message[0] == "CERTIFICATE":
            entries = ", ".join(f"{e.validator}:{e.kind}" for e in message[2])
            lines.append(f"CERTIFICATE id={message[1].event_id()[:12]} [{entries}]")
        else:
            lines.append(repr(message))
    return "\n".join(lines)


# --- Generator -----------------------------------------------------------

MALFORMED = (
    {"type": "VOTE_REQUEST"},
    {"type": "VOTE", "transfer": 1, "validator": 0, "signature": "zz"},
    {"type": "CERTIFICATE", "transfer": {}, "votes": []},
    {"type": "CERTIFICATE", "transfer": {"sender": "a"}, "votes": 3},
)


def _random_event(rng, pool, expected_nonce) -> Transfer:
    if pool and rng.random() < 0.25:
        other = rng.choice(pool)
        sender, nonce = other.sender, other.nonce
    else:
        sender = rng.choices(ACCOUNTS[:4], weights=[6, 6, 6, 3])[0]
        nonce = expected_nonce[sender]
        expected_nonce[sender] += 1

    receiver = rng.choice([name for name in ACCOUNTS if name != sender])
    parents = ()
    if pool and rng.random() < 0.4:
        parents = (rng.choice(pool).event_id(),)
    return Transfer(
        sender=sender,
        receiver=receiver,
        amount=rng.choice([0, 1, 1, 2, 2, 3, 4]),
        nonce=nonce,
        parents=parents,
    )


def _add_children_waiting_for_a_parent(rng, case: NodeCase, expected: dict) -> None:
    """
    Certificates that become ready together, so that their order is under test. A
    certificate that can run does so when it arrives, so this takes waiting for a parent.
    """
    parent_sender, *child_senders = rng.sample(ACCOUNTS[:3], 3)
    parent = Transfer(parent_sender, "dave", 1, 0)
    children = [Transfer(sender, "dave", 1, 0, (parent.event_id(),)) for sender in child_senders]
    rng.shuffle(children)

    for sender in (parent_sender, *child_senders):
        case.balances[sender] = max(case.balances[sender], 2)
        expected[sender] = 1

    quorum = 2 * case.f + 1
    case.pool += [parent, *children]
    for event in (*children, parent):
        entries = [Entry(v) for v in rng.sample(range(3 * case.f + 1), quorum)]
        case.messages.append(("CERTIFICATE", event, entries))


def random_case(rng: random.Random) -> NodeCase:
    case = NodeCase(
        f=rng.choices([0, 1, 2], weights=[5, 80, 15])[0],
        balances={name: rng.randint(0, 12) for name in ACCOUNTS},
        nonces={},
    )
    expected = {name: 0 for name in ACCOUNTS}

    if rng.random() < 0.3:
        _add_children_waiting_for_a_parent(rng, case, expected)

    for _ in range(rng.randint(2, 6)):
        event = _random_event(rng, case.pool, expected)
        if all(e.canonical() != event.canonical() for e in case.pool):
            case.pool.append(event)

    n = 3 * case.f + 1

    for _ in range(rng.randint(1, 14)):
        event = rng.choice(case.pool)
        draw = rng.random()
        if draw < 0.45:
            case.messages.append(
                ("CERTIFICATE", event, _random_entries(rng, case, event, case.pool))
            )
        elif draw < 0.62:
            kind = rng.choices(
                [VALID, "bad signature", "signed by another"], weights=[8, 1, 1]
            )[0]
            case.messages.append(("REQUEST", event, kind))
        elif draw < 0.75:
            case.messages.append(("SUBMIT", event))
            for validator in rng.sample(range(n), rng.randint(0, n)):
                case.messages.append(("VOTE", event, validator, rng.random() < 0.85))
        elif draw < 0.80:
            case.messages.append(
                ("VOTE", event, rng.randrange(n + 1), rng.random() < 0.7)
            )
        elif draw < 0.90:
            path = rng.choice(
                ["SIGNED_TRANSFER", "SIGNED_EVENT_SYNC", "KNOWLEDGE_RESPONSE"]
            )
            case.messages.append(("EVIDENCE", event, path))
        elif draw < 0.93:
            case.messages.append(("MALFORMED", rng.choice(MALFORMED)))
        else:
            case.messages.append(("RESTART",))

    return case


# What each must have been exercised, or the comparison says little.
EXERCISED = (
    "votes given",
    "votes refused by the lock",
    "requests refused by auth",
    "requests with a bad signature",
    "valid certificates",
    "invalid certificates",
    "certificates that do not decode",
    "certificates made here",
    "submits of a certified event",
    "evidence",
    "halts",
    "restarts",
    "restarts with a log",
    "executed later by a retry",
    "several ready together",
)


@pytest.mark.parametrize("seed", SEEDS)
def test_node_matches_runnode(quorum_check, tmp_path, seed):  # noqa: F811
    rng = random.Random(seed + 500)
    cases = [random_case(rng) for _ in range(CASES)]
    plans = [make_plan(case, quorum_check, tmp_path) for case in cases]

    run = _run(
        quorum_check,
        tmp_path,
        "\n---\n".join(_lean_text(c, p.inputs) for c, p in zip(cases, plans)) + "\n",
    )
    assert run.returncode == 0, run.stderr
    lean_results = _split_outputs(run.stdout)
    assert len(lean_results) == len(cases)

    stats: dict[str, int] = {}

    for index, (case, plan, lean) in enumerate(zip(cases, plans, lean_results)):
        result = run_node(case, tmp_path)
        found = compare(case, plan, lean, result)
        if found is None:
            trace = _lean_lines(case, result.trace, quorum_check, tmp_path)
            if trace[-1] != result.lines[-1]:
                found = (
                    f"trace of the replica:\n  python {result.lines[-1]}\n"
                    f"  lean   {trace[-1]}"
                )
        if found is not None:
            smallest = minimize(case, quorum_check, tmp_path)
            pytest.fail(
                f"seed {seed} case {index} diverges. Minimal case:\n"
                f"{describe(smallest)}\n"
                f"{difference_of(smallest, quorum_check, tmp_path)}"
            )

        for name, amount in plan.stats.items():
            stats[name] = stats.get(name, 0) + amount
        later, together = _retried(case, result)
        stats["executed later by a retry"] = (
            stats.get("executed later by a retry", 0) + later
        )
        stats["several ready together"] = (
            stats.get("several ready together", 0) + together
        )

    print(f"\nseed {seed}, {len(cases)} cases:")
    for name in EXERCISED:
        print(f"  {stats.get(name, 0):6d}  {name}")

    # The floor applies to a whole corpus. A short run only compares.
    if CASES >= 500:
        missing = {
            name: stats.get(name, 0)
            for name in EXERCISED
            if stats.get(name, 0) < MIN_SEEN
        }
        assert not missing, f"not exercised enough: {missing}"


def _retried(case: NodeCase, result: Result) -> tuple[int, int]:
    """
    Events that ran on a message other than their own certificate's, and messages where
    two or more waiting ones of different senders ran at once.
    """
    count = 0
    together = 0
    ids = {_event_id_as_nat(event): event for event in case.pool}

    def executed(line: str) -> list[int]:
        section = line.split(";")[1].removeprefix("exec=")
        return [] if section == "-" else [int(value) for value in section.split(",")]

    for index, message in enumerate(case.messages):
        new = executed(result.lines[index + 1])[len(executed(result.lines[index])):]
        waiting = [
            ids[value]
            for value in new
            if message[0] != "CERTIFICATE" or ids[value] != message[1]
        ]
        count += len(waiting)
        if len({event.sender for event in waiting}) >= 2:
            together += 1
    return count, together
