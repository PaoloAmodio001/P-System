"""Quorum messages (network/message.py): VOTE_REQUEST, VOTE, CERTIFICATE and
CERTIFICATE_SYNC.

A decoder takes what any peer sent. It returns a well-formed value or raises
ValueError, and never anything else. What a value means is decided later: decoding
does not check signatures or the rules of a certificate.
"""

import copy
import json
import random

import pytest

from core.attestation import (
    Committee,
    QuorumCertificate,
    Vote,
    is_well_formed_event,
)
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity
from network.message import (
    decode_certificate,
    decode_certificate_sync,
    decode_vote,
    decode_vote_request,
    encode_certificate,
    encode_certificate_sync,
    encode_vote,
    encode_vote_request,
)

GENESIS = State({"alice": 10})
LOW = "ab" * 32
HIGH = "cd" * 32
EVENT = Transfer("alice", "bob", 8, 0, (LOW, HIGH))

MEMBERS = sorted(
    (Identity.create() for _ in range(4)),
    key=lambda identity: identity.public_key,
)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, GENESIS)
SENDER = Identity.create()


def certificate(event=EVENT, indexes=(0, 1, 2)):
    return QuorumCertificate(
        event,
        tuple(Vote.create(COMMITTEE, MEMBERS[i], event) for i in indexes),
    )


def wire(message):
    """What a peer receives: the transport carries JSON."""
    return json.loads(json.dumps(message))


def vote_request_message():
    return encode_vote_request(SignedTransfer.create(SENDER, EVENT))


def vote_message():
    return encode_vote(EVENT, Vote.create(COMMITTEE, MEMBERS[0], EVENT))


def certificate_message():
    return encode_certificate(certificate())


def certificate_sync_message():
    return encode_certificate_sync([certificate()])


CODECS = {
    "VOTE_REQUEST": (vote_request_message, decode_vote_request),
    "VOTE": (vote_message, decode_vote),
    "CERTIFICATE": (certificate_message, decode_certificate),
    "CERTIFICATE_SYNC": (certificate_sync_message, decode_certificate_sync),
}


# Where the event sits in the messages that carry one at the top level.
EVENT_CODECS = ["VOTE_REQUEST", "VOTE", "CERTIFICATE"]


# --- Round trips -------------------------------------------------------------


def test_vote_request_round_trip():
    signed = SignedTransfer.create(SENDER, EVENT)
    decoded = decode_vote_request(wire(encode_vote_request(signed)))

    assert decoded.transfer.canonical() == EVENT.canonical()
    assert decoded.public_key == SENDER.public_key
    assert decoded.signature == signed.signature
    assert decoded.verify()
    assert decoded.identity_id == SENDER.identity_id


def test_vote_round_trip():
    vote = Vote.create(COMMITTEE, MEMBERS[2], EVENT)
    event, decoded = decode_vote(wire(encode_vote(EVENT, vote)))

    assert event == EVENT
    assert decoded == vote
    assert decoded.verify(COMMITTEE, event)


def test_certificate_round_trip():
    original = certificate()
    decoded = decode_certificate(wire(encode_certificate(original)))

    assert decoded == original
    assert decoded.verify(COMMITTEE)


def test_certificate_sync_round_trip_keeps_the_order():
    # The order matters: this message is the log, logOf in the theorem.
    first = certificate(Transfer("alice", "bob", 1, 0))
    second = certificate(Transfer("alice", "bob", 1, 1, (first.event.event_id(),)))
    decoded = decode_certificate_sync(wire(encode_certificate_sync([first, second])))

    assert decoded == [first, second]
    assert all(item.verify(COMMITTEE) for item in decoded)


def test_empty_certificate_sync_round_trip():
    assert decode_certificate_sync(wire(encode_certificate_sync([]))) == []


def test_message_formats_are_fixed():
    # A change here is a change of protocol, between nodes of different versions.
    vote = Vote(1, b"\x01" * 64)
    event = {
        "sender": "alice",
        "receiver": "bob",
        "amount": 8,
        "nonce": 0,
        "parents": [LOW, HIGH],
    }
    votes = [{"validator": 1, "signature": "01" * 64}]

    assert encode_vote(EVENT, vote) == {
        "type": "VOTE",
        "transfer": event,
        "validator": 1,
        "signature": "01" * 64,
    }
    assert encode_certificate(QuorumCertificate(EVENT, (vote,))) == {
        "type": "CERTIFICATE",
        "transfer": event,
        "votes": votes,
    }
    assert encode_certificate_sync([QuorumCertificate(EVENT, (vote,))]) == {
        "type": "CERTIFICATE_SYNC",
        "certificates": [
            {"type": "CERTIFICATE", "transfer": event, "votes": votes},
        ],
    }
    assert encode_vote_request(
        SignedTransfer(EVENT, b"\x02" * 32, b"\x03" * 64)
    ) == {
        "type": "VOTE_REQUEST",
        "transfer": event,
        "public_key": "02" * 32,
        "signature": "03" * 64,
    }


# --- Parents have one form on the wire ---------------------------------------


def test_encoder_sorts_parents():
    permuted = Transfer("alice", "bob", 8, 0, (HIGH, LOW))
    assert encode_certificate(certificate(permuted))["transfer"]["parents"] == [LOW, HIGH]


@pytest.mark.parametrize("name", EVENT_CODECS)
def test_decoder_sorts_parents_and_signatures_still_verify(name):
    # The same event in Python, since canonical() sorts them. Without this, two
    # orders are two values that differ under ==, but not on disk after a restart.
    make, decode = CODECS[name]
    message = make()
    message["transfer"]["parents"] = [HIGH, LOW]
    decoded = decode(wire(message))

    if name == "VOTE_REQUEST":
        assert decoded.transfer == EVENT
        assert decoded.verify()
    elif name == "VOTE":
        event, vote = decoded
        assert event == EVENT
        assert vote.verify(COMMITTEE, event)
    else:
        assert decoded.event == EVENT
        assert decoded.verify(COMMITTEE)


# --- Refused messages --------------------------------------------------------


BAD_EVENT_FIELDS = [
    ("amount", -1),
    ("amount", True),
    ("amount", 1.5),
    ("amount", 1.0),
    ("amount", "8"),
    ("amount", None),
    ("amount", 2**256),
    ("nonce", -1),
    ("nonce", False),
    ("nonce", None),
    ("nonce", 2**256),
    ("sender", 1),
    ("sender", ""),
    ("sender", None),
    ("sender", "\ud800"),
    ("receiver", []),
    ("receiver", ""),
    ("receiver", "\udfff"),
    ("parents", None),
    ("parents", LOW),
    ("parents", {}),
    ("parents", [LOW, 1]),
    ("parents", [1, LOW]),
    ("parents", [None]),
    ("parents", [10**63]),
    ("parents", [[LOW]]),
    ("parents", ["z" * 64]),
    ("parents", ["AB" * 32]),
    ("parents", ["ab" * 31]),
    ("parents", ["ab" * 33]),
    ("parents", [LOW + "\n"]),
    ("parents", [""]),
]


@pytest.mark.parametrize("name", EVENT_CODECS)
@pytest.mark.parametrize("field,value", BAD_EVENT_FIELDS)
def test_malformed_event_is_refused(name, field, value):
    make, decode = CODECS[name]
    message = make()
    message["transfer"][field] = value

    with pytest.raises(ValueError):
        decode(message)


@pytest.mark.parametrize("field,value", BAD_EVENT_FIELDS)
def test_malformed_event_in_a_sync_is_refused(field, value):
    message = certificate_sync_message()
    message["certificates"][0]["transfer"][field] = value

    with pytest.raises(ValueError):
        decode_certificate_sync(message)


@pytest.mark.parametrize("name", CODECS)
@pytest.mark.parametrize("message", [None, 1, "CERTIFICATE", [], [("type", "VOTE")]])
def test_message_that_is_not_an_object_is_refused(name, message):
    with pytest.raises(ValueError):
        CODECS[name][1](message)


@pytest.mark.parametrize("name", CODECS)
def test_message_of_another_type_is_refused(name):
    make, decode = CODECS[name]
    message = make()
    message["type"] = "SIGNED_TRANSFER"

    with pytest.raises(ValueError):
        decode(message)


@pytest.mark.parametrize("name", CODECS)
def test_each_missing_field_is_refused(name):
    make, decode = CODECS[name]

    for field in make():
        message = make()
        del message[field]

        with pytest.raises(ValueError):
            decode(message)


@pytest.mark.parametrize("name", CODECS)
def test_unknown_field_is_refused(name):
    make, decode = CODECS[name]
    message = make()
    message["extra"] = 1

    with pytest.raises(ValueError):
        decode(message)


@pytest.mark.parametrize("name", EVENT_CODECS)
def test_each_missing_or_unknown_event_field_is_refused(name):
    make, decode = CODECS[name]

    for field in make()["transfer"]:
        message = make()
        del message["transfer"][field]

        with pytest.raises(ValueError):
            decode(message)

    message = make()
    message["transfer"]["memo"] = "x"

    with pytest.raises(ValueError):
        decode(message)


@pytest.mark.parametrize("name", EVENT_CODECS)
@pytest.mark.parametrize("event", [None, 1, "event", []])
def test_event_that_is_not_an_object_is_refused(name, event):
    make, decode = CODECS[name]
    message = make()
    message["transfer"] = event

    with pytest.raises(ValueError):
        decode(message)


BAD_SIGNATURES = [
    None,
    1,
    [],
    "",
    "01",
    "01" * 63,
    "01" * 65,
    "zz" * 64,
    # bytes.fromhex accepts both of these, so one signature would have many forms.
    "AB" * 64,
    "01 " * 63 + "01",
    "01" * 64 + "\n",
]

BAD_VALIDATORS = [None, True, False, -1, 1.0, "1", [], {}]


@pytest.mark.parametrize("name", ["VOTE_REQUEST", "VOTE"])
@pytest.mark.parametrize("signature", BAD_SIGNATURES)
def test_bad_signature_field_is_refused(name, signature):
    make, decode = CODECS[name]
    message = make()
    message["signature"] = signature

    with pytest.raises(ValueError):
        decode(message)


@pytest.mark.parametrize(
    "public_key",
    [None, 1, "", "02" * 31, "02" * 33, "zz" * 32, "AB" * 32, "02" * 32 + "\n"],
)
def test_bad_public_key_field_is_refused(public_key):
    message = vote_request_message()
    message["public_key"] = public_key

    with pytest.raises(ValueError):
        decode_vote_request(message)


@pytest.mark.parametrize("validator", BAD_VALIDATORS)
def test_bad_validator_in_a_vote_is_refused(validator):
    message = vote_message()
    message["validator"] = validator

    with pytest.raises(ValueError):
        decode_vote(message)


@pytest.mark.parametrize("validator", BAD_VALIDATORS)
def test_bad_validator_in_a_certificate_is_refused(validator):
    message = certificate_message()
    message["votes"][0]["validator"] = validator

    with pytest.raises(ValueError):
        decode_certificate(message)


@pytest.mark.parametrize("signature", BAD_SIGNATURES)
def test_bad_signature_in_a_certificate_is_refused(signature):
    message = certificate_message()
    message["votes"][0]["signature"] = signature

    with pytest.raises(ValueError):
        decode_certificate(message)


@pytest.mark.parametrize("votes", [None, 1, "votes", {}, [None], [1], [[]], ["vote"]])
def test_votes_of_a_wrong_type_are_refused(votes):
    message = certificate_message()
    message["votes"] = votes

    with pytest.raises(ValueError):
        decode_certificate(message)


@pytest.mark.parametrize("entry", [{}, {"validator": 0}, {"signature": "01" * 64}])
def test_vote_entry_with_missing_fields_is_refused(entry):
    message = certificate_message()
    message["votes"][0] = entry

    with pytest.raises(ValueError):
        decode_certificate(message)


def test_vote_entry_with_an_unknown_field_is_refused():
    message = certificate_message()
    message["votes"][0]["extra"] = 1

    with pytest.raises(ValueError):
        decode_certificate(message)


@pytest.mark.parametrize(
    "certificates",
    [None, 1, "x", {}, [None], [1], [[]], [{}], [{"type": "VOTE"}]],
)
def test_certificates_of_a_wrong_type_are_refused(certificates):
    message = certificate_sync_message()
    message["certificates"] = certificates

    with pytest.raises(ValueError):
        decode_certificate_sync(message)


def test_one_bad_certificate_refuses_the_whole_sync():
    message = encode_certificate_sync([certificate(), certificate()])
    message["certificates"][1]["votes"][0]["validator"] = -1

    with pytest.raises(ValueError):
        decode_certificate_sync(message)


# --- Decoding is about form, verification is about meaning ---------------------


def test_decoder_does_not_decide_what_verify_decides():
    event = Transfer("alice", "bob", 1, 0)
    good = Vote.create(COMMITTEE, MEMBERS[0], event)
    cases = {
        "too few signers": (good,),
        "repeated signer": (good, good, good),
        "signer outside the committee": (
            Vote(99, good.signature),
            Vote.create(COMMITTEE, MEMBERS[1], event),
            Vote.create(COMMITTEE, MEMBERS[2], event),
        ),
        "wrong signature": (
            Vote(0, b"\x00" * 64),
            Vote.create(COMMITTEE, MEMBERS[1], event),
            Vote.create(COMMITTEE, MEMBERS[2], event),
        ),
    }

    for votes in cases.values():
        decoded = decode_certificate(
            wire(encode_certificate(QuorumCertificate(event, votes)))
        )
        assert decoded.votes == votes
        assert decoded.verify(COMMITTEE) is False


def test_changing_any_event_field_on_the_wire_invalidates_the_certificate():
    changes = {
        "sender": "mallory",
        "receiver": "mallory",
        "amount": 9,
        "nonce": 1,
        "parents": [LOW],
    }

    for field, value in changes.items():
        message = certificate_message()
        message["transfer"][field] = value
        assert decode_certificate(wire(message)).verify(COMMITTEE) is False


def test_decoded_vote_request_with_a_changed_event_does_not_verify():
    message = vote_request_message()
    message["transfer"]["amount"] = 9
    assert decode_vote_request(wire(message)).verify() is False


# --- Arbitrary input -----------------------------------------------------------


JUNK = [
    None,
    True,
    False,
    0,
    1,
    -1,
    1.5,
    float("nan"),
    float("inf"),
    2**256,
    "",
    "x",
    "\ud800",
    "\x00",
    "ab" * 32,
    "01" * 64,
    "VOTE",
    "CERTIFICATE",
    [],
    [None],
    [[]],
    {},
    {"type": "VOTE"},
    {"": None},
]


def _paths(value, path=()):
    yield path
    if isinstance(value, dict):
        for key in value:
            yield from _paths(value[key], path + (key,))
    elif isinstance(value, list):
        for index in range(len(value)):
            yield from _paths(value[index], path + (index,))


def _corrupt(message, rng):
    """Replace, remove or add something at a random place of the message."""
    path = rng.choice(list(_paths(message)))

    if not path:
        return copy.deepcopy(rng.choice(JUNK))

    holder = message
    for step in path[:-1]:
        holder = holder[step]

    action = rng.randrange(3)

    if action == 0:
        holder[path[-1]] = copy.deepcopy(rng.choice(JUNK))
    elif action == 1:
        del holder[path[-1]]
    elif isinstance(holder, dict):
        holder[rng.choice(["extra", "", "type"])] = copy.deepcopy(rng.choice(JUNK))
    else:
        holder.insert(path[-1], copy.deepcopy(rng.choice(JUNK)))

    return message


def _events_of(decoded):
    if isinstance(decoded, SignedTransfer):
        return [decoded.transfer]
    if isinstance(decoded, tuple):
        return [decoded[0]]
    if isinstance(decoded, QuorumCertificate):
        return [decoded.event]
    return [item.event for item in decoded]


def _votes_of(decoded):
    if isinstance(decoded, SignedTransfer):
        return []
    if isinstance(decoded, tuple):
        return [decoded[1]]
    if isinstance(decoded, QuorumCertificate):
        return list(decoded.votes)
    return [vote for item in decoded for vote in item.votes]


@pytest.mark.parametrize("name", CODECS)
def test_corrupted_messages_give_a_value_or_valueerror(name):
    """PROPERTY_TESTED, on one fixed seed per message type."""
    make, decode = CODECS[name]
    rng = random.Random(f"quorum messages {name}")
    accepted = refused = 0

    for _ in range(4000):
        message = make()

        for _ in range(rng.choice([1, 1, 1, 2, 3])):
            message = _corrupt(message, rng)

            if not isinstance(message, (dict, list)):
                break

        try:
            decoded = decode(message)
        except ValueError:
            refused += 1
            continue

        accepted += 1
        assert all(is_well_formed_event(event) for event in _events_of(decoded))
        assert all(
            type(vote.validator) is int
            and vote.validator >= 0
            and type(vote.signature) is bytes
            and len(vote.signature) == 64
            for vote in _votes_of(decoded)
        )

        # Whatever was accepted can be verified without an exception.
        for event in _events_of(decoded):
            event.canonical()

        if name == "CERTIFICATE":
            assert decoded.verify(COMMITTEE) in (True, False)

    # Otherwise the test would pass by refusing, or by accepting, everything.
    assert refused > 2000
    assert accepted > 50
