"""Differential test: Python QuorumReplica vs the Lean model runNode.

The Lean model (formal/lean/PSystem/Quorum.lean) carries the theorems
no_double_spend, state_is_derive and convergence_after_exchange. This test checks,
on random adversarial inputs, that the replica does what runNode does: after EACH
input, the same votes, the same executed events in the same order, and the same
balances and nonces. Comparing each step keeps two errors from cancelling out.

This is EMPIRICAL evidence of correspondence, not a refinement proof.

Correspondence between the two sides:

- Event ids are SHA-256 hex in Python and Nat in Lean, passed as int(hex, 16).
  Some cases force two different events to share an id, which SHA-256 cannot
  produce on demand, to exercise the id lock.
- Signatures are real Ed25519 in Python and symbolic in Lean: (signer, whole event).
  Each Python signature is built to have the same outcome: valid, made on another
  event (also one with the same id), made by another validator, or garbage.
- A signer outside the committee cannot be written in Lean, where signers are
  Fin n. It is passed as an invalid signature, which has the same effect: every
  signature must verify.
- A restart exists only on the Python side: the replica is rebuilt from disk, and
  the model must not notice. Cases with a forced id have no restart, because events
  read back from disk have their real id.

Events are well formed here (natural numbers, hex parents). Malformed ones cannot
be written in Lean, and are refused before the replica (subphase 5.4).

Three seeds run by default. PSYSTEM_DIFF_SEEDS sets the total number of seeds:
PSYSTEM_DIFF_SEEDS=15 is the run required before merging, see
docs/PROOF-OBLIGATIONS.md (obligation O7).
"""

import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.attestation import Committee, QuorumCertificate, Vote, vote_payload
from core.event import Transfer
from core.state import State
from crypto.identity import Identity
from network.quorum import QuorumReplica, SqliteVoteStore
from tests.test_quorum_check_driver import _run, quorum_check  # noqa: F401

ACCOUNTS = ["alice", "bob", "carol", "dave"]
CASES = 3000
SEEDS = (
    [20261104, 20261105, 20261106] + [20270000 + extra for extra in range(1000)]
)[: int(os.environ.get("PSYSTEM_DIFF_SEEDS", "3"))]
KEY_SEED = 20261104
MIN_DECISIVE = 30

# Kinds of signature entries.
VALID = "valid"
ON_OTHER_EVENT = "on other event"
ON_SAME_ID_EVENT = "on other event with the same id"
BY_OTHER_VALIDATOR = "by other validator"
GARBAGE = "garbage"
OUTSIDER = "signer outside the committee"
NEGATIVE = "negative signer index"
BAD_KINDS = (ON_OTHER_EVENT, ON_SAME_ID_EVENT, BY_OTHER_VALIDATOR, GARBAGE)


@dataclass(frozen=True)
class ForcedIdTransfer(Transfer):
    """A hash collision: the id is a field of this one event, not its hash."""

    forced_id: str = ""

    def event_id(self) -> str:
        return self.forced_id


def _identities(count: int) -> list[Identity]:
    rng = random.Random(KEY_SEED)
    identities = [
        Identity(Ed25519PrivateKey.from_private_bytes(rng.randbytes(32)))
        for _ in range(count)
    ]
    identities.sort(key=lambda identity: identity.public_key)
    return identities


IDENTITIES = {f: _identities(3 * f + 1) for f in (0, 1, 2)}
OUTSIDER_IDENTITY = Identity(
    Ed25519PrivateKey.from_private_bytes(random.Random(KEY_SEED + 1).randbytes(32))
)


@dataclass
class Entry:
    """One signature of a certificate."""

    validator: int
    kind: str = VALID
    aux: object = None  # the other event, or the other validator


@dataclass
class Case:
    f: int
    balances: dict[str, int]
    nonces: dict[str, int]
    refused: set[str] = field(default_factory=set)
    inputs: list[tuple] = field(default_factory=list)


def _event_id_as_nat(event: Transfer) -> int:
    return int(event.event_id(), 16)


def _lean_event_fields(event: Transfer) -> list[str]:
    # Sorted as in canonical(): for fixed-length hex the two orders agree.
    parents = ",".join(str(int(p, 16)) for p in sorted(event.parents)) or "-"
    return [
        str(_event_id_as_nat(event)),
        event.sender,
        event.receiver,
        str(event.amount),
        str(event.nonce),
        parents,
    ]


def _lean_event(event: Transfer) -> str:
    return " ".join(_lean_event_fields(event))


def _signed(event: Transfer) -> str:
    return "|".join(_lean_event_fields(event))


# Signed by nobody: id 0 and an impossible sender match no event of the cases.
_NO_EVENT = "0|-|-|0|0|-"


def _lean_entry(entry: Entry, event: Transfer) -> str:
    v = entry.validator
    if entry.kind == VALID:
        return f"{v}:{v}:{_signed(event)}"
    if entry.kind in (ON_OTHER_EVENT, ON_SAME_ID_EVENT):
        return f"{v}:{v}:{_signed(entry.aux)}"
    if entry.kind == BY_OTHER_VALIDATOR:
        return f"{v}:{entry.aux}:{_signed(event)}"
    if entry.kind == GARBAGE:
        return f"{v}:{v}:{_NO_EVENT}"
    if entry.kind in (OUTSIDER, NEGATIVE):
        return f"0:0:{_NO_EVENT}"
    raise AssertionError(entry.kind)


def lean_case(case: Case) -> str:
    lines = [f"N {3 * case.f + 1}", f"Q {2 * case.f + 1}"]
    lines += [
        f"A {name} {case.balances[name]} {case.nonces.get(name, 0)}"
        for name in ACCOUNTS
    ]
    lines += [f"U {int(event_id, 16)}" for event_id in sorted(case.refused)]
    for item in case.inputs:
        if item[0] == "V":
            lines.append(f"V {_lean_event(item[1])}")
        elif item[0] == "C":
            entries = ";".join(_lean_entry(e, item[1]) for e in item[2]) or "-"
            lines.append(f"C {_lean_event(item[1])} {entries}")
    return "\n".join(lines)


def _python_vote(committee: Committee, identities, entry: Entry, event) -> Vote:
    v = entry.validator
    if entry.kind == VALID:
        return Vote(v, identities[v].sign(vote_payload(committee, event)))
    if entry.kind in (ON_OTHER_EVENT, ON_SAME_ID_EVENT):
        return Vote(v, identities[v].sign(vote_payload(committee, entry.aux)))
    if entry.kind == BY_OTHER_VALIDATOR:
        return Vote(v, identities[entry.aux].sign(vote_payload(committee, event)))
    if entry.kind == GARBAGE:
        return Vote(v, bytes((v + 1,)) * 64)
    if entry.kind == OUTSIDER:
        return Vote(
            len(identities) + v,
            OUTSIDER_IDENTITY.sign(vote_payload(committee, event)),
        )
    if entry.kind == NEGATIVE:
        # A real signature of the last member: valid if -1 were taken as an index.
        return Vote(-1, identities[-1].sign(vote_payload(committee, event)))
    raise AssertionError(entry.kind)


def _show(replica: QuorumReplica, ids_by_canonical: dict[bytes, int]) -> str:
    def ids(values) -> str:
        return ",".join(map(str, values)) or "-"

    votes = sorted({ids_by_canonical[e.canonical()] for e in replica.votes()})
    executed = [ids_by_canonical[e.canonical()] for e in replica.executed]
    accounts = " ".join(
        f"{name}={replica.state.balance(name)}/{replica.state.nonce(name)}"
        for name in ACCOUNTS
    )
    return f"votes={ids(votes)};exec={ids(executed)};{accounts}"


def _events_of(case: Case) -> list[Transfer]:
    return [item[1] for item in case.inputs if item[0] != "R"]


def python_run(case: Case, directory: Path, stats: dict | None = None) -> list[str]:
    initial = State(balances=dict(case.balances), nonces=dict(case.nonces))
    identities = IDENTITIES[case.f]
    committee = Committee.create(
        [identity.public_key for identity in identities], case.f, initial
    )
    identity = identities[0]
    ids_by_canonical = {e.canonical(): _event_id_as_nat(e) for e in _events_of(case)}
    path = directory / "votes.sqlite"
    if path.exists():
        path.unlink()

    def auth(event: Transfer) -> bool:
        return event.event_id() not in case.refused

    def open_replica(create: bool):
        store = SqliteVoteStore(path, committee, identity.public_key, create=create)
        return store, QuorumReplica(identity, initial, store, auth)

    store, replica = open_replica(True)
    lines = [_show(replica, ids_by_canonical)]

    for item in case.inputs:
        if item[0] == "R":
            store.close()
            store, replica = open_replica(False)
            continue

        if stats is not None:
            _classify(stats, case, replica, item)

        if item[0] == "V":
            replica.handle_vote_request(item[1])
        else:
            votes = tuple(
                _python_vote(committee, identities, entry, item[1])
                for entry in item[2]
            )
            replica.handle_certificate(QuorumCertificate(item[1], votes))

        lines.append(_show(replica, ids_by_canonical))

    store.close()
    return lines


def _classify(stats: dict, case: Case, replica: QuorumReplica, item: tuple) -> None:
    """
    Which rule decides this input, computed without the rules of the replica.

    A rule counts only when it is the single condition that fails. A certificate with
    a bad signature and a wrong nonce is refused anyway, and says nothing about either
    rule: the outcome must depend on the rule for the comparison to test it.
    """

    def count(reason: str) -> None:
        stats[reason] = stats.get(reason, 0) + 1

    def decide(failing: list[str], success: str) -> None:
        if not failing:
            count(success)
        elif len(failing) == 1:
            count(failing[0])

    event = item[1]
    if item[0] == "V":
        votes = replica.votes()
        if any(v.canonical() == event.canonical() for v in votes):
            if event.event_id() in case.refused:
                return
            count("vote repeated")
            return
        failing = []
        if event.event_id() in case.refused:
            failing.append("vote refused by auth")
        if any((v.sender, v.nonce) == (event.sender, event.nonce) for v in votes):
            failing.append("vote refused by key lock")
        if any(_event_id_as_nat(v) == _event_id_as_nat(event) for v in votes):
            failing.append("vote refused by id lock")
        decide(failing, "vote accepted")
        return

    entries = item[2]
    failing = []
    for kind in (OUTSIDER, NEGATIVE, *BAD_KINDS):
        if any(entry.kind == kind for entry in entries):
            failing.append(f"cert: {kind}")
    if len({entry.validator for entry in entries}) != len(entries):
        failing.append("cert: repeated signer")
    if len(entries) < 2 * case.f + 1:
        failing.append("cert: below quorum")

    state = replica.state
    executed = replica.executed
    executed_ids = {_event_id_as_nat(e) for e in executed}
    if any(e.canonical() == event.canonical() for e in executed):
        failing.append("cert: already executed")
    elif _event_id_as_nat(event) in executed_ids:
        failing.append("cert: id taken by another event")
    if event.amount == 0:
        failing.append("cert: amount zero")
    if event.sender == event.receiver:
        failing.append("cert: self transfer")
    if state.nonce(event.sender) != event.nonce:
        failing.append("cert: wrong nonce")
    if state.balance(event.sender) < event.amount:
        failing.append("cert: insufficient balance")
    if not {int(p, 16) for p in event.parents} <= executed_ids:
        failing.append("cert: parent missing")
    decide(failing, "cert executed")


# --- Generator -----------------------------------------------------------


def _random_event(rng, pool, expected_nonce) -> Transfer:
    if pool and rng.random() < 0.2:
        # Another version of an existing event: same sender and nonce.
        other = rng.choice(pool)
        sender, nonce = other.sender, other.nonce
    else:
        sender = rng.choice(ACCOUNTS)
        nonce = expected_nonce[sender]
        if rng.random() < 0.9:
            expected_nonce[sender] += 1
        else:
            nonce = max(0, nonce + rng.randint(-1, 2))

    receiver = rng.choice([a for a in ACCOUNTS if a != sender])
    if rng.random() < 0.04:
        receiver = sender

    parents: tuple[str, ...] = ()
    if pool and rng.random() < 0.3:
        parents = (rng.choice(pool).event_id(),)
    if rng.random() < 0.04:
        parents += ("%064x" % rng.getrandbits(256),)

    return Transfer(
        sender=sender,
        receiver=receiver,
        amount=rng.choice([0, 1, 1, 1, 2, 2, 3, 4]),
        nonce=nonce,
        parents=parents,
    )


def _random_entries(rng, case: Case, event: Transfer, pool) -> list[Entry]:
    n = 3 * case.f + 1
    quorum = 2 * case.f + 1
    shape = rng.random()

    if shape < 0.50:
        size = rng.randint(quorum, n)
        return [Entry(v) for v in rng.sample(range(n), size)]

    if shape < 0.56:
        size = rng.randint(0, quorum - 1)
        return [Entry(v) for v in rng.sample(range(n), size)]

    entries = [Entry(v) for v in rng.sample(range(n), rng.randint(quorum, n))]

    if shape < 0.62:
        entries.append(Entry(rng.choice(entries).validator))
        return entries

    if shape < 0.71:
        entries.append(Entry(rng.randrange(n), OUTSIDER))
        return entries

    if shape < 0.80:
        entries.append(Entry(rng.randrange(n), NEGATIVE))
        return entries

    target = rng.choice(entries)
    others = [e for e in pool if e.canonical() != event.canonical()]
    same_id = [e for e in others if e.event_id() == event.event_id()]
    different_id = [e for e in others if e.event_id() != event.event_id()]
    choice = rng.random()

    if same_id and choice < 0.7:
        target.kind, target.aux = ON_SAME_ID_EVENT, rng.choice(same_id)
    elif different_id and choice < 0.8:
        target.kind, target.aux = ON_OTHER_EVENT, rng.choice(different_id)
    elif n > 1 and choice < 0.9:
        target.kind = BY_OTHER_VALIDATOR
        target.aux = rng.choice([v for v in range(n) if v != target.validator])
    else:
        target.kind = GARBAGE
    return entries


def random_case(rng: random.Random) -> Case:
    f = rng.choices([0, 1, 2], weights=[5, 75, 20])[0]
    case = Case(
        f=f,
        balances={name: rng.randint(0, 12) for name in ACCOUNTS},
        nonces={
            name: rng.randint(1, 2)
            for name in ACCOUNTS
            if rng.random() < 0.1
        },
    )

    collisions = rng.random() < 0.2
    forced_any = False
    expected_nonce = {name: case.nonces.get(name, 0) for name in ACCOUNTS}
    pool: list[Transfer] = []
    for _ in range(rng.randint(2, 7)):
        event = _random_event(rng, pool, expected_nonce)
        if any(e.canonical() == event.canonical() for e in pool):
            continue
        if collisions and pool and rng.random() < 0.5:
            event = ForcedIdTransfer(
                sender=event.sender,
                receiver=event.receiver,
                amount=event.amount,
                nonce=event.nonce,
                parents=event.parents,
                forced_id=rng.choice(pool).event_id(),
            )
            forced_any = True
        pool.append(event)

    if rng.random() < 0.1:
        case.refused.add(rng.choice(pool).event_id())

    # Reuse some events, so that retries, duplicates and locks all happen.
    for _ in range(rng.randint(1, 16)):
        event = rng.choice(pool)
        if rng.random() < 0.4:
            case.inputs.append(("V", event))
        else:
            case.inputs.append(("C", event, _random_entries(rng, case, event, pool)))

        if not forced_any and rng.random() < 0.08:
            case.inputs.append(("R",))

    return case


def _describe(case: Case) -> str:
    lines = [
        f"f={case.f} balances={case.balances} nonces={case.nonces} "
        f"refused={sorted(case.refused)}"
    ]
    for item in case.inputs:
        if item[0] == "R":
            lines.append("RESTART")
            continue
        event = item[1]
        label = f"id={event.event_id()[:12]} {event!r}"
        if item[0] == "V":
            lines.append(f"VOTE {label}")
        else:
            lines.append(f"CERT {label}")
            lines += [f"    {e.validator} {e.kind} {e.aux!r}" for e in item[2]]
    return "\n".join(lines)


def _split_outputs(stdout: str) -> list[list[str]]:
    results, current = [], []
    for line in stdout.splitlines():
        if line == "---":
            results.append(current)
            current = []
        else:
            current.append(line)
    assert not current
    return results


def _lean_lines(driver: Path, directory: Path, case: Case) -> list[str]:
    run = _run(driver, directory, lean_case(case) + "\n")
    assert run.returncode == 0, run.stderr
    [lines] = _split_outputs(run.stdout)
    return lines


def minimize(case: Case, driver: Path, directory: Path) -> Case:
    """Remove inputs while Python and Lean still disagree."""

    def differs(candidate: Case) -> bool:
        return python_run(candidate, directory) != _lean_lines(
            driver, directory, candidate
        )

    changed = True
    while changed:
        changed = False
        for index in range(len(case.inputs) - 1, -1, -1):
            candidate = Case(
                case.f,
                case.balances,
                case.nonces,
                case.refused,
                case.inputs[:index] + case.inputs[index + 1:],
            )
            if differs(candidate):
                case = candidate
                changed = True
    return case


def _first_difference(python: list[str], lean: list[str]) -> str:
    for index, (p, l) in enumerate(zip(python, lean)):
        if p != l:
            return f"after input {index}:\n  python {p}\n  lean   {l}"
    return f"lengths differ: python {len(python)}, lean {len(lean)}"


def generate(seed: int, driver: Path, directory: Path):
    rng = random.Random(seed)
    cases = [random_case(rng) for _ in range(CASES)]
    run = _run(driver, directory, "\n---\n".join(map(lean_case, cases)) + "\n")
    assert run.returncode == 0, run.stderr
    results = _split_outputs(run.stdout)
    assert len(results) == CASES
    return cases, results


DECISIVE_RULES = (
    "vote accepted",
    "vote repeated",
    "vote refused by auth",
    "vote refused by key lock",
    "vote refused by id lock",
    "cert executed",
    # "cert: already executed" is not here because it can never decide alone: once an
    # event has run the nonce of its sender has moved, so delivering it again also has
    # the wrong nonce. The id check matters only for another event with the same id.
    "cert: id taken by another event",
    "cert: amount zero",
    "cert: self transfer",
    "cert: wrong nonce",
    "cert: insufficient balance",
    "cert: parent missing",
    "cert: below quorum",
    "cert: repeated signer",
    f"cert: {OUTSIDER}",
    f"cert: {NEGATIVE}",
    f"cert: {ON_OTHER_EVENT}",
    f"cert: {ON_SAME_ID_EVENT}",
    f"cert: {BY_OTHER_VALIDATOR}",
    f"cert: {GARBAGE}",
)


@pytest.mark.parametrize("seed", SEEDS)
def test_replica_matches_runnode(quorum_check, tmp_path, seed):  # noqa: F811
    cases, lean_results = generate(seed, quorum_check, tmp_path)
    stats: dict[str, int] = {}
    restarts = 0

    for index, (case, lean) in enumerate(zip(cases, lean_results)):
        restarts += sum(item[0] == "R" for item in case.inputs)
        python = python_run(case, tmp_path, stats)
        if python != lean:
            smallest = minimize(case, quorum_check, tmp_path)
            pytest.fail(
                f"seed {seed} case {index} diverges. Minimal case:\n"
                f"{_describe(smallest)}\n"
                + _first_difference(
                    python_run(smallest, tmp_path),
                    _lean_lines(quorum_check, tmp_path, smallest),
                )
            )

    print(f"\nseed {seed}: restarts {restarts}, decisive:")
    for rule in DECISIVE_RULES:
        print(f"  {stats.get(rule, 0):6d}  {rule}")

    # The comparison must exercise every rule where it alone decides the outcome.
    missing = {
        rule: stats.get(rule, 0)
        for rule in DECISIVE_RULES
        if stats.get(rule, 0) < MIN_DECISIVE
    }
    assert not missing, f"rules not exercised enough: {missing}"
    assert restarts >= MIN_DECISIVE
