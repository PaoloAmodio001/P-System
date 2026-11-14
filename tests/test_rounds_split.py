"""The stall of a split vote, and the rounds that end it (formal/lean/PSystem/QuorumRounds.lean).

Four validators, `f = 1`. A sender signs two versions of nonce 0, and two validators see one first
and two the other: round 0 gives two votes to each, no version reaches the `2f+1 = 3` of a
certificate. Before rounds the nonce stayed locked for ever (`test_split_stays_open_without_rounds`
shows that this is still what round 0 does). With rounds, after a timeout every validator decides the
same version and executes it.

The drivers run in one process and exchange messages through `Network`, which can lose them or hold
them back: what the model allows. The clock is the test's.
"""

from collections import deque

import pytest

from core.attestation import Committee
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import encode_vote_request
from network.quorum import QuorumConfig, QuorumRuntime

SENDER = Identity.create()
PAYER = SENDER.identity_id
GENESIS = State({PAYER: 10})
A = Transfer(PAYER, "bob", 8, 0)
B = Transfer(PAYER, "carol", 8, 0)


def signed(event: Transfer) -> SignedTransfer:
    return SignedTransfer.create(SENDER, event)


class Network:
    """Four runtimes and the messages between them, delivered in order unless dropped."""

    def __init__(self, directory, f: int = 1) -> None:
        self.now = 0.0
        members = sorted((Identity.create() for _ in range(3 * f + 1)), key=lambda i: i.public_key)
        self.committee = Committee.create([m.public_key for m in members], f, GENESIS)
        self.runtimes = [
            QuorumRuntime(QuorumConfig(self.committee, member, directory / f"v{i}.sqlite", create=True), GENESIS)
            for i, member in enumerate(members)
        ]
        for runtime in self.runtimes:
            runtime.driver._clock = lambda: self.now
            runtime.driver.rounds.started = {}
        self.queue: deque = deque()
        self.cut: set[tuple[int, int]] = set()

    @property
    def drivers(self):
        return [runtime.driver for runtime in self.runtimes]

    def send(self, origin: int, output) -> None:
        for message in output.broadcasts:
            for target in range(len(self.runtimes)):
                if target != origin:
                    self.queue.append((origin, target, message))
        for message in output.replies:
            self.queue.append((None, origin, message, "reply-from"))

    def deliver_to(self, target: int, message: dict, origin: int) -> None:
        output = self.drivers[target].handle_message(message)
        self.send(target, output)
        for reply in output.replies:
            # A reply goes back to whoever asked.
            self.queue.append((target, origin, reply))
        # Replies were queued as broadcasts by `send` above when origin is None; nothing else here.

    def run(self, limit: int = 100_000) -> None:
        steps = 0
        while self.queue and steps < limit:
            item = self.queue.popleft()
            steps += 1
            if len(item) == 4:
                continue
            origin, target, message = item
            if (origin, target) in self.cut:
                continue
            output = self.drivers[target].handle_message(message)
            for reply in output.replies:
                self.queue.append((target, origin, reply))
            for broadcast in output.broadcasts:
                for other in range(len(self.runtimes)):
                    if other != target:
                        self.queue.append((target, other, broadcast))
        assert not self.queue, "messages did not settle"

    def submit(self, index: int, event: SignedTransfer) -> None:
        output = self.drivers[index].submit(event)
        for broadcast in output.broadcasts:
            for other in range(len(self.runtimes)):
                if other != index:
                    self.queue.append((index, other, broadcast))

    def tick(self, seconds: float) -> None:
        self.now += seconds
        for index, driver in enumerate(self.drivers):
            output = driver.retry()
            for broadcast in output.broadcasts:
                for other in range(len(self.runtimes)):
                    if other != index:
                        self.queue.append((index, other, broadcast))

    def executed(self):
        return [[c.event for c in runtime.replica.log] for runtime in self.runtimes]

    def close(self) -> None:
        for runtime in self.runtimes:
            runtime.close()


@pytest.fixture
def network(tmp_path):
    made = Network(tmp_path)
    yield made
    made.close()


def split(network: Network) -> None:
    """Validators 0 and 1 vote A, 2 and 3 vote B; each version's requests reach only its side."""
    network.cut = {(0, 2), (0, 3), (1, 2), (1, 3), (2, 0), (2, 1), (3, 0), (3, 1)}
    network.submit(0, signed(A))
    network.submit(2, signed(B))
    network.run()
    network.cut = set()


def test_split_stays_open_without_rounds(network):
    split(network)
    # Round 0 alone: two votes for each version, no certificate, nothing executed.
    assert network.executed() == [[], [], [], []]
    for driver in network.drivers:
        state = driver.replica.round_state(PAYER, 0)
        assert state["decided"] is None and state["round"] == 0

    # However often the requests are sent again: each validator keeps its first vote.
    for _ in range(5):
        network.tick(0.3)
        network.run()
    assert network.executed() == [[], [], [], []]


def test_rounds_end_the_split(network):
    split(network)
    network.tick(network.drivers[0].rounds.ROUND_FIRST_SECONDS + 0.1)
    network.run()

    executed = network.executed()
    assert executed[0] in ([A], [B])
    assert executed == [executed[0]] * 4
    for driver in network.drivers:
        state = driver.replica.round_state(PAYER, 0)
        assert state["decided"] == executed[0][0].event_id()
        assert state["round"] >= 1


def test_a_faulty_leader_costs_a_round(network):
    split(network)
    first_leader = network.drivers[0].rounds.leader(PAYER, 0, 1)
    # The leader of round 1 hears nothing and says nothing.
    network.cut = {(i, first_leader) for i in range(4)} | {(first_leader, i) for i in range(4)}
    network.tick(network.drivers[0].rounds.ROUND_FIRST_SECONDS + 0.1)
    network.run()
    assert all(not log for i, log in enumerate(network.executed()) if i != first_leader)

    # Round 2 has another leader: the three others decide.
    network.tick(network.drivers[0].rounds.timeout_of(1) + 0.1)
    network.run()
    others = [log for i, log in enumerate(network.executed()) if i != first_leader]
    assert others[0] in ([A], [B]) and others == [others[0]] * 3

    # The leader that was cut off catches up when it hears again.
    network.cut = set()
    network.tick(network.drivers[0].rounds.timeout_of(2) + 0.1)
    network.run()
    assert network.executed() == [others[0]] * 4


def test_without_a_split_round_0_decides_in_one_step(network):
    network.submit(0, signed(A))
    network.run()
    # All four voted A: the fast path, no precommit and no timeout.
    assert network.executed() == [[A]] * 4
    for driver in network.drivers:
        assert driver.replica.round_state(PAYER, 0)["round"] == 0


def test_a_proposal_not_from_the_leader_is_ignored(network):
    from core.attestation import RoundProposal, RoundReport

    split(network)
    leader = network.drivers[0].rounds.leader(PAYER, 0, 1)
    other = (leader + 1) % 4
    impostor = network.runtimes[other].replica
    reports = tuple(
        RoundReport.create(network.committee, runtime.replica._identity, PAYER, 0, 1, None, None)
        for runtime in network.runtimes[:3]
    )
    proposal = RoundProposal.create(network.committee, impostor._identity, 1, signed(B), reports)

    for driver in network.drivers:
        assert driver.rounds.handle_proposal(proposal) == []
        state = driver.replica.round_state(PAYER, 0)
        assert all(round_ == 0 for round_, _ in state["prevotes"])


def _certificate(network: Network, event: Transfer, members) -> "QuorumCertificate":
    from core.attestation import QuorumCertificate, Vote

    votes = tuple(
        Vote.create(network.committee, network.runtimes[i].replica._identity, event) for i in members
    )
    return QuorumCertificate(event, votes)


def test_a_prepare_by_sync_is_no_decision(network):
    # A split can give 2f+1 votes of round 0 to a value that a round later loses. Sent as if it were
    # a log, it must not be taken as decided: the decision of the other value would halt the node.
    from network.message import encode_certificate, encode_certificate_sync

    driver = network.drivers[0]
    driver.handle_message(encode_certificate_sync([_certificate(network, A, (0, 1, 2))]))
    assert driver._known == {}

    driver.handle_message(encode_certificate(_certificate(network, B, (0, 1, 2, 3))))
    assert not driver.halted
    assert network.executed()[0] == [B]


def test_a_prepare_shown_to_one_node_is_sent_on_once(network):
    from network.message import encode_certificate

    driver = network.drivers[0]
    message = encode_certificate(_certificate(network, A, (1, 2, 3)))
    first = driver.handle_message(message)
    assert [m["type"] for m in first.broadcasts].count("CERTIFICATE") == 1
    again = driver.handle_message(message)
    assert [m["type"] for m in again.broadcasts].count("CERTIFICATE") == 0


def test_a_node_that_gathers_sends_its_prepare_once(network):
    gatherer = network.drivers[0]
    [request] = gatherer.submit(signed(A)).broadcasts
    votes = [network.drivers[i].handle_message(request).replies[0] for i in (1, 2)]

    assert gatherer.handle_message(votes[0]).broadcasts == ()
    prepared = gatherer.handle_message(votes[1]).broadcasts
    assert [m["type"] for m in prepared].count("CERTIFICATE") == 1
    # The same vote again, and three votes still: nothing new to send.
    assert [m["type"] for m in gatherer.handle_message(votes[1]).broadcasts].count("CERTIFICATE") == 0


def test_after_a_long_partition_the_split_is_decided_soon_after_the_heal(network):
    # Campaign seed 103 of scripts/vm_lab.py: after a long partition the keys were in rounds whose
    # timeout had reached a minute, and the messages sent on entering them had been lost. Nothing
    # went again before the next timeout, and honest transfers were not final within the two
    # minutes after the heal. The messages of a round now go again every ROUND_FIRST_SECONDS.
    split(network)
    network.cut = {(i, j) for i in range(4) for j in range(4) if (i < 2) != (j < 2)}
    for _ in range(12):
        network.tick(network.drivers[0].rounds.ROUND_LONGEST_SECONDS + 1)
        network.run()
    assert all(d.replica.round_state(PAYER, 0)["round"] >= 6 for d in network.drivers)

    network.cut = set()
    waited = 0.0
    while waited < 10 and not all(d.replica.log for d in network.drivers):
        network.tick(1.0)
        network.run()
        waited += 1.0

    executed = network.executed()
    assert executed[0] in ([A], [B]) and executed == [executed[0]] * 4
    assert waited <= network.drivers[0].rounds.ROUND_FIRST_SECONDS + 1


def test_round_vote_is_retried_after_signer_recovers(network):
    split(network)

    replica = network.runtimes[0].replica
    rounds = network.drivers[0].rounds
    original_sign_phase = replica.sign_phase
    attempts = 0

    def temporarily_unavailable(event, phase, round_):
        nonlocal attempts
        if phase == "prevote":
            attempts += 1
            if attempts == 1:
                return None
        return original_sign_phase(event, phase, round_)

    replica.sign_phase = temporarily_unavailable

    # Advance the network, then deliver messages only until node 0 attempts
    # its authorized prevote. Stop before peer messages can decide the key.
    network.tick(rounds.ROUND_FIRST_SECONDS + 0.1)

    steps = 0
    while network.queue and attempts == 0:
        item = network.queue.popleft()
        if len(item) == 4:
            continue

        origin, target, message = item
        if (origin, target) in network.cut:
            continue

        output = network.drivers[target].handle_message(message)

        for reply in output.replies:
            network.queue.append((target, origin, reply))

        for broadcast in output.broadcasts:
            for other in range(len(network.runtimes)):
                if other != target:
                    network.queue.append((target, other, broadcast))

        steps += 1
        assert steps < 100_000, "messages did not reach the first signing attempt"

    assert attempts == 1
    state = replica.round_state(PAYER, 0)
    assert state["decided"] is None
    assert rounds.pending_signatures

    # Discard queued peer messages: the key must remain undecided while the
    # local retry is exercised.
    network.queue.clear()

    network.tick(rounds.ROUND_FIRST_SECONDS + 0.1)

    assert attempts >= 2

def test_precommit_vote_is_retried_after_signer_recovers(network):
    from core.attestation import PRECOMMIT, PREVOTE, QuorumCertificate, Vote

    split(network)
    network.tick(2.1)

    runtime = network.runtimes[0]
    replica = runtime.replica
    rounds = runtime.driver.rounds

    assert replica.round_state(PAYER, 0)["round"] == 1

    original_sign_phase = replica.sign_phase
    attempts = 0

    def temporarily_unavailable(event, phase, round_):
        nonlocal attempts
        if phase == PRECOMMIT:
            attempts += 1
            if attempts == 1:
                return None
        return original_sign_phase(event, phase, round_)

    replica.sign_phase = temporarily_unavailable

    votes = tuple(
        Vote.create_phase(
            network.committee,
            network.runtimes[i]._identity,
            A,
            PREVOTE,
            1,
        )
        for i in (1, 2, 3)
    )
    certificate = QuorumCertificate(
        A, votes, network.committee.epoch, PREVOTE, 1
    )

    runtime.driver._handle_certificate(certificate)

    assert attempts == 1
    state = replica.round_state(PAYER, 0)
    assert state["decided"] is None
    assert [1, A.event_id()] in state["precommits"]

    pending = (PAYER, 0, PRECOMMIT, 1, A.event_id())
    assert pending in rounds.pending_signatures

    # Round 1 lasts four seconds: retry is due before its timeout.
    network.now += 2.1
    output = runtime.driver.retry()

    assert attempts >= 2
    assert pending not in rounds.pending_signatures
    assert any(
        message.get("type") == "ROUND_VOTE"
        and message.get("phase") == PRECOMMIT
        for message in output.broadcasts
    )


def test_pending_round_vote_is_restored_after_restart(network):
    split(network)

    runtime = network.runtimes[0]
    replica = runtime.replica
    rounds = runtime.driver.rounds
    original_sign_phase = replica.sign_phase
    attempts = 0

    def temporarily_unavailable(event, phase, round_):
        nonlocal attempts
        if phase == "prevote":
            attempts += 1
            if attempts == 1:
                return None
        return original_sign_phase(event, phase, round_)

    replica.sign_phase = temporarily_unavailable

    network.tick(rounds.ROUND_FIRST_SECONDS + 0.1)

    # Deliver only until this validator attempts its prevote.
    steps = 0
    while network.queue and attempts == 0:
        item = network.queue.popleft()
        if len(item) == 4:
            continue

        origin, target, message = item
        if (origin, target) in network.cut:
            continue

        output = network.drivers[target].handle_message(message)

        for reply in output.replies:
            network.queue.append((target, origin, reply))

        for broadcast in output.broadcasts:
            for other in range(len(network.runtimes)):
                if other != target:
                    network.queue.append((target, other, broadcast))

        steps += 1
        assert steps < 100_000, "messages did not reach the first signing attempt"

    assert attempts == 1
    assert replica.round_state(PAYER, 0)["decided"] is None
    assert rounds.pending_signatures
    assert A.event_id() in rounds.signed

    network.queue.clear()

    # Close and reopen the same SQLite store with the same validator identity.
    identity = runtime._identity
    store_path = runtime._config.store_path
    runtime.close()

    from network.quorum import QuorumConfig, QuorumRuntime
    restored = QuorumRuntime(
        QuorumConfig(network.committee, identity, store_path, create=False),
        GENESIS,
    )
    network.runtimes[0] = restored

    restored.driver._clock = lambda: network.now
    restored_rounds = restored.driver.rounds
    restored_rounds.started = {(PAYER, 0): network.now}

    assert A.event_id() in restored_rounds.signed
    assert any(
        item[:2] == (PAYER, 0)
        and item[2] == "prevote"
        for item in restored_rounds.pending_signatures
    )

    # Give the restored pending signature a fresh retry interval.
    for pending in restored_rounds.pending_signatures:
        restored_rounds.pending_signatures[pending] = network.now

    network.now += 2.1
    output = restored.driver.retry()

    assert not restored_rounds.pending_signatures
    assert any(
        message.get("type") == "ROUND_VOTE"
        and message.get("phase") == "prevote"
        for message in output.broadcasts
    )

