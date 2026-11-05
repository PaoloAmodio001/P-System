"""What any peer or client can send must get a clean answer, whatever it is.

Random structures and bytes, from fixed seeds so that a failure repeats. The rule of every decoder
is one: a well-formed value or ValueError. For the driver, malformed input never changes a vote, a
log or a halt. EMPIRICAL: this searches, and it proves nothing. PSYSTEM_FUZZ_ROUNDS asks for more.
"""

import copy
import json
import os
import random

import pytest

from core.attestation import Committee, EpochChange, Governance, QuorumCertificate, Vote
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network import message as wire
from network.handshake import Handshake
from network.quorum import QuorumConfig, QuorumRuntime
from network.secure_transport import SecureTransport

ROUNDS = int(os.environ.get("PSYSTEM_FUZZ_ROUNDS", "3000"))

SENDER = Identity.create()
GENESIS = State({SENDER.identity_id: 100})
MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
SIGNERS = [Identity.create() for _ in range(2)]
GOVERNANCE = Governance(tuple(sorted(s.public_key for s in SIGNERS)), 2)

EVENT = Transfer(SENDER.identity_id, "bob", 1, 0)
SIGNED = SignedTransfer.create(SENDER, EVENT)
VOTE = Vote.create(COMMITTEE, MEMBERS[0], EVENT)
CERTIFICATE = QuorumCertificate(EVENT, (VOTE,))
CHANGE = EpochChange.create(COMMITTEE, COMMITTEE.members, 1, GOVERNANCE, SIGNERS)
REPORT_BASE = {"validator": 0, "votes": [], "signature": "00" * 64}

VALID = {
    "VOTE_REQUEST": (wire.encode_vote_request(SIGNED), wire.decode_vote_request),
    "VOTE": (wire.encode_vote(EVENT, VOTE), wire.decode_vote),
    "CERTIFICATE": (wire.encode_certificate(CERTIFICATE), wire.decode_certificate),
    "CERTIFICATE_SYNC": (
        wire.encode_certificate_sync([CERTIFICATE]),
        wire.decode_certificate_sync,
    ),
    "CERTIFICATE_SYNC_REQUEST": (
        wire.encode_certificate_sync_request({"alice": 1}, 2),
        wire.decode_certificate_sync_request,
    ),
    "EPOCH_CHANGE": (wire.encode_epoch_change(CHANGE), wire.decode_epoch_change),
    "EPOCH_REPORT": (
        {"type": "EPOCH_REPORT", "change_id": "ab" * 32, "report": REPORT_BASE},
        wire.decode_epoch_report,
    ),
    "CLOSURE_VOTE": (
        wire.encode_closure_vote("ab" * 32, VOTE),
        wire.decode_closure_vote,
    ),
    "CLOSURE_VOTE_REQUEST": (
        {
            "type": "CLOSURE_VOTE_REQUEST",
            "closure": {
                "change": wire.encode_epoch_change(CHANGE)["change"],
                "reports": [REPORT_BASE],
                "votes": [],
            },
        },
        wire.decode_closure_vote_request,
    ),
    "EPOCH_CLOSURE": (
        {
            "type": "EPOCH_CLOSURE",
            "closure": {
                "change": wire.encode_epoch_change(CHANGE)["change"],
                "reports": [REPORT_BASE],
                "votes": [],
            },
        },
        wire.decode_epoch_closure,
    ),
}

JUNK = [
    None,
    True,
    False,
    0,
    -1,
    1.5,
    2**256,
    2**64,
    "",
    "x",
    "ab" * 32,
    "AB" * 32,
    "00" * 64,
    "\ud800",
    [],
    [[]],
    {},
    {"type": "VOTE"},
    [None],
    "é" * 100,
]


def paths_of(value, prefix=()):
    yield prefix
    if type(value) is dict:
        for key in value:
            yield from paths_of(value[key], prefix + (key,))
    elif type(value) is list:
        for index in range(len(value)):
            yield from paths_of(value[index], prefix + (index,))


def mutate(rng: random.Random, value):
    data = copy.deepcopy(value)

    for _ in range(rng.choice([1, 1, 1, 2, 3])):
        paths = [path for path in paths_of(data) if path]

        if not paths:
            return rng.choice(JUNK)

        path = rng.choice(paths)
        holder = data

        for step in path[:-1]:
            holder = holder[step]

        action = rng.random()

        if action < 0.55:
            holder[path[-1]] = copy.deepcopy(rng.choice(JUNK))
        elif action < 0.75:
            del holder[path[-1]]
        elif type(holder) is dict:
            holder[rng.choice(["extra", "", "type", "epoch"])] = copy.deepcopy(rng.choice(JUNK))
        else:
            holder.insert(path[-1], copy.deepcopy(rng.choice(JUNK)))

    return data


@pytest.mark.parametrize("name", VALID)
def test_decoder_gives_a_value_or_a_value_error(name):
    message, decode = VALID[name]
    decode(message)
    rng = random.Random(name)

    for _ in range(ROUNDS):
        case = mutate(rng, message)
        try:
            decode(case)
        except ValueError:
            pass
        except Exception as error:
            pytest.fail(f"{type(error).__name__}: {error} on {case!r}")


@pytest.mark.parametrize("value", JUNK)
@pytest.mark.parametrize("name", VALID)
def test_decoder_takes_any_value_at_the_top(name, value):
    try:
        VALID[name][1](value)
    except ValueError:
        pass


class ByteStream:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def recv(self, size: int) -> bytes:
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


def test_a_frame_of_any_bytes_gives_a_message_or_a_clean_error():
    rng = random.Random(1)

    for _ in range(ROUNDS):
        size = rng.randrange(0, 64)
        payload = bytes(rng.randrange(256) for _ in range(size))

        if rng.random() < 0.7:
            payload = len(payload).to_bytes(4, "big") + payload

        try:
            result = SecureTransport.receive(ByteStream(payload))
        except (ValueError, ConnectionError, RecursionError):
            continue

        assert type(result) is dict


def test_a_handshake_of_any_shape_gives_a_value_or_a_clean_error():
    rng = random.Random(2)
    valid = Handshake("node", "127.0.0.1", 1).encode()

    for _ in range(ROUNDS):
        try:
            Handshake.decode(mutate(rng, valid))
        except (ValueError, TypeError, KeyError, AttributeError):
            # What the callers catch: test_node_server_handshake checks that nothing escapes.
            pass


@pytest.fixture
def runtime(tmp_path):
    run = QuorumRuntime(
        QuorumConfig(COMMITTEE, MEMBERS[0], tmp_path / "f.sqlite", create=True, governance=GOVERNANCE),
        GENESIS,
    )
    yield run
    run.close()


def _fingerprint(run):
    return (
        [event.canonical() for event in run.replica.votes()],
        [event.canonical() for event in run.replica.executed],
        run.replica.state.root(),
        run.driver.halted,
        run.replica.committee.committee_id,
    )


def test_malformed_messages_change_nothing_in_a_driver(runtime):
    rng = random.Random(3)
    before = _fingerprint(runtime)
    names = list(VALID)

    for _ in range(ROUNDS // 3):
        message = mutate(rng, VALID[rng.choice(names)][0])
        try:
            json.dumps(message)
        except (ValueError, UnicodeEncodeError):
            pass

        if type(message) is not dict:
            continue

        try:
            output = runtime.driver.handle_message(message)
        except ValueError:
            continue

        # What decodes and is not signed correctly may get an answer, and never a vote on a
        # forged event, a certificate, a halt or a change of committee.
        assert output is not None

    votes, executed, _root, halted, committee_id = _fingerprint(runtime)
    assert executed == before[1]
    assert not halted
    assert committee_id == before[4]
    # Only the one signed event of this test can have a vote.
    assert all(vote == EVENT.canonical() for vote in votes)
