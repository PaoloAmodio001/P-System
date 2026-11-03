"""Committee, votes and quorum certificates (core/attestation.py).

QuorumCertificate.verify must follow certValid in formal/lean/PSystem/Quorum.lean:
pairwise distinct signers, at least 2f+1 of them, and every signature valid.
"""

from hashlib import sha256

import pytest

import core.attestation
from core.attestation import (
    MAX_EVENT_INTEGER,
    Attestation,
    Committee,
    QuorumCertificate,
    Vote,
    is_well_formed_event,
    vote_payload,
)
from core.event import Transfer
from core.identity_claim import IdentityClaim
from core.signed_event import SignedTransfer
from core.state import State
from crypto.identity import Identity, verify_signature

GENESIS = State({"alice": 10})
EVENT = Transfer(sender="alice", receiver="bob", amount=8, nonce=0)
OTHER = Transfer(sender="alice", receiver="carol", amount=8, nonce=0)


def make_committee(f=1, genesis=GENESIS):
    """A committee and its identities, in committee order."""
    identities = [Identity.create() for _ in range(3 * f + 1)]
    committee = Committee.create(
        [identity.public_key for identity in identities],
        f,
        genesis,
    )
    identities.sort(key=lambda identity: identity.public_key)
    return committee, identities


def votes_from(committee, identities, indexes, event=EVENT):
    return tuple(
        Vote.create(committee, identities[index], event)
        for index in indexes
    )


# --- Committee -----------------------------------------------------------


@pytest.mark.parametrize("f,n,quorum", [(0, 1, 1), (1, 4, 3), (2, 7, 5), (3, 10, 7)])
def test_committee_sizes(f, n, quorum):
    committee, _ = make_committee(f)
    assert committee.f == f
    assert committee.n == n
    assert committee.quorum == quorum


@pytest.mark.parametrize("f,size", [(1, 3), (1, 5), (1, 7), (2, 4), (0, 2), (0, 0)])
def test_committee_rejects_size_other_than_3f_plus_1(f, size):
    keys = [Identity.create().public_key for _ in range(size)]
    with pytest.raises(ValueError):
        Committee.create(keys, f, GENESIS)


@pytest.mark.parametrize("f", [-1, True, 1.0, "1", None])
def test_committee_rejects_bad_fault_bound(f):
    keys = [Identity.create().public_key for _ in range(4)]
    with pytest.raises(ValueError):
        Committee.create(keys, f, GENESIS)


def test_committee_rejects_repeated_member():
    # Otherwise one validator would count twice towards the quorum.
    key = Identity.create().public_key
    keys = [key, key] + [Identity.create().public_key for _ in range(2)]
    with pytest.raises(ValueError):
        Committee.create(keys, 1, GENESIS)


@pytest.mark.parametrize("bad_key", [b"short", b"x" * 33, "a" * 32, None])
def test_committee_rejects_malformed_key(bad_key):
    keys = [Identity.create().public_key for _ in range(3)] + [bad_key]
    with pytest.raises((ValueError, TypeError)):
        Committee.create(keys, 1, GENESIS)


def test_committee_constructor_requires_sorted_members():
    # The index of a member is its validator number, so the order is not free.
    keys = sorted(Identity.create().public_key for _ in range(4))
    root = GENESIS.root()
    assert Committee(tuple(keys), 1, root).n == 4
    with pytest.raises(ValueError):
        Committee(tuple(reversed(keys)), 1, root)


@pytest.mark.parametrize("root", ["", "abc", "A" * 64, "g" * 64, None, b"a" * 64])
def test_committee_rejects_malformed_genesis_root(root):
    keys = sorted(Identity.create().public_key for _ in range(4))
    with pytest.raises(ValueError):
        Committee(tuple(keys), 1, root)


def test_committee_order_of_keys_does_not_matter():
    keys = [Identity.create().public_key for _ in range(4)]
    first = Committee.create(keys, 1, GENESIS)
    second = Committee.create(list(reversed(keys)), 1, GENESIS)
    assert first == second
    assert first.committee_id == second.committee_id


def test_committee_id_binds_members_fault_bound_and_genesis():
    keys = [Identity.create().public_key for _ in range(4)]
    base = Committee.create(keys, 1, GENESIS)

    other_member = Committee.create(
        keys[:3] + [Identity.create().public_key], 1, GENESIS
    )
    other_genesis = Committee.create(keys, 1, State({"alice": 11}))
    assert base.committee_id != other_member.committee_id
    assert base.committee_id != other_genesis.committee_id

    # Same size, other fault bound is impossible for a valid committee; bind
    # it anyway by comparing with a larger one that contains the same keys.
    larger = Committee.create(
        keys + [Identity.create().public_key for _ in range(3)], 2, GENESIS
    )
    assert base.committee_id != larger.committee_id


def test_index_of():
    committee, identities = make_committee()
    for index, identity in enumerate(identities):
        assert committee.index_of(identity.public_key) == index
    assert committee.index_of(Identity.create().public_key) is None


# --- Vote ----------------------------------------------------------------


def test_vote_verifies_for_its_event_and_validator():
    committee, identities = make_committee()
    vote = Vote.create(committee, identities[2], EVENT)
    assert vote.validator == 2
    assert vote.verify(committee, EVENT)


def test_vote_does_not_verify_for_another_event():
    committee, identities = make_committee()
    vote = Vote.create(committee, identities[2], EVENT)
    assert not vote.verify(committee, OTHER)


def test_vote_attributed_to_another_validator_does_not_verify():
    committee, identities = make_committee()
    vote = Vote.create(committee, identities[2], EVENT)
    assert not Vote(1, vote.signature).verify(committee, EVENT)


def test_create_refuses_a_key_outside_the_committee():
    committee, _ = make_committee()
    with pytest.raises(ValueError):
        Vote.create(committee, Identity.create(), EVENT)


@pytest.mark.parametrize("validator", [-1, 4, 100, True, False, 1.0, "1", None])
def test_vote_with_invalid_validator_does_not_verify(validator):
    # -1 matters: as a list index it would silently select the last member.
    committee, identities = make_committee()
    signature = identities[-1].sign(vote_payload(committee, EVENT))
    assert not Vote(validator, signature).verify(committee, EVENT)


@pytest.mark.parametrize("signature", [b"", b"x" * 64, b"x" * 63, "x", None])
def test_vote_with_malformed_signature_does_not_verify(signature):
    committee, _ = make_committee()
    assert not Vote(0, signature).verify(committee, EVENT)


# --- Domain separation ---------------------------------------------------


def test_vote_from_another_committee_does_not_verify():
    committee, identities = make_committee()
    other = Committee.create(
        [identity.public_key for identity in identities],
        1,
        State({"alice": 11}),
    )
    assert committee.committee_id != other.committee_id
    vote = Vote.create(other, identities[0], EVENT)
    assert not vote.verify(committee, EVENT)


def test_signature_of_a_transfer_is_not_a_vote():
    committee, identities = make_committee()
    signed = SignedTransfer.create(identities[0], EVENT)
    assert not Vote(0, signed.signature).verify(committee, EVENT)


def test_vote_is_not_a_signature_of_a_transfer():
    committee, identities = make_committee()
    vote = Vote.create(committee, identities[0], EVENT)
    assert not SignedTransfer(
        EVENT, identities[0].public_key, vote.signature
    ).verify()


def test_vote_is_not_an_attestation_or_an_identity_claim():
    committee, identities = make_committee()
    identity = identities[0]
    vote = Vote.create(committee, identity, EVENT)
    assert not Attestation(
        EVENT.event_id(), identity.public_key, 1, vote.signature
    ).verify()

    claim = IdentityClaim.create(identity, "alice")
    assert not IdentityClaim(
        claim.identity_id, claim.alias, claim.public_key, vote.signature
    ).verify()


def test_other_signatures_of_the_same_key_are_not_votes():
    committee, identities = make_committee()
    identity = identities[0]
    attestation = Attestation.create(identity, EVENT.event_id(), 1)
    claim = IdentityClaim.create(identity, "alice")
    assert not Vote(0, attestation.signature).verify(committee, EVENT)
    assert not Vote(0, claim.signature).verify(committee, EVENT)


def test_payload_starts_with_the_domain_tag_and_binds_the_committee():
    committee, identities = make_committee()
    payload = vote_payload(committee, EVENT)
    assert not payload.startswith(EVENT.canonical())
    assert bytes.fromhex(committee.committee_id) in payload
    assert payload.endswith(EVENT.canonical())
    assert verify_signature(
        identities[0].public_key,
        identities[0].sign(payload),
        payload,
    )


def test_payload_of_permuted_parents_is_the_same():
    # canonical() sorts parents: these are one event, so one vote covers both.
    committee, identities = make_committee()
    first = Transfer("alice", "bob", 1, 0, ("a" * 64, "b" * 64))
    second = Transfer("alice", "bob", 1, 0, ("b" * 64, "a" * 64))
    vote = Vote.create(committee, identities[0], first)
    assert vote.verify(committee, second)


# --- QuorumCertificate: the rules of certValid ---------------------------


@pytest.mark.parametrize("f", [0, 1, 2, 3])
def test_certificate_with_exactly_a_quorum_is_valid(f):
    committee, identities = make_committee(f)
    votes = votes_from(committee, identities, range(committee.quorum))
    assert QuorumCertificate(EVENT, votes).verify(committee)


@pytest.mark.parametrize("f", [0, 1, 2, 3])
def test_certificate_with_all_members_is_valid(f):
    committee, identities = make_committee(f)
    votes = votes_from(committee, identities, range(committee.n))
    assert QuorumCertificate(EVENT, votes).verify(committee)


@pytest.mark.parametrize("f", [0, 1, 2, 3])
def test_certificate_one_short_of_a_quorum_is_invalid(f):
    committee, identities = make_committee(f)
    votes = votes_from(committee, identities, range(committee.quorum - 1))
    assert not QuorumCertificate(EVENT, votes).verify(committee)


def test_empty_certificate_is_invalid():
    committee, _ = make_committee()
    assert not QuorumCertificate(EVENT, ()).verify(committee)


def test_repeated_signer_does_not_count_twice():
    committee, identities = make_committee()
    two = votes_from(committee, identities, [0, 1])
    assert not QuorumCertificate(EVENT, two + (two[0],)).verify(committee)


def test_repeated_signer_invalidates_even_above_the_quorum():
    # Nodup in certValid applies to the whole list, not to the signers counted.
    committee, identities = make_committee()
    three = votes_from(committee, identities, [0, 1, 2])
    assert not QuorumCertificate(EVENT, three + (three[0],)).verify(committee)


def test_one_bad_signature_invalidates_even_above_the_quorum():
    # certValid requires every signature to verify. Counting only the valid
    # ones would also be safe, but it is not what the model says.
    committee, identities = make_committee()
    three = votes_from(committee, identities, [0, 1, 2])
    bad = Vote(3, b"x" * 64)
    assert QuorumCertificate(EVENT, three).verify(committee)
    assert not QuorumCertificate(EVENT, three + (bad,)).verify(committee)


def test_signature_on_another_event_invalidates():
    committee, identities = make_committee()
    good = votes_from(committee, identities, [0, 1])
    wrong = votes_from(committee, identities, [2], event=OTHER)
    assert not QuorumCertificate(EVENT, good + wrong).verify(committee)


def test_signer_outside_the_committee_invalidates():
    committee, identities = make_committee()
    good = votes_from(committee, identities, [0, 1, 2])
    outsider = Identity.create().sign(vote_payload(committee, EVENT))
    for index in (4, -1, 99):
        assert not QuorumCertificate(
            EVENT, good + (Vote(index, outsider),)
        ).verify(committee)


def test_bool_cannot_stand_in_for_a_validator():
    # True == 1, and a set would treat them as one signer.
    committee, identities = make_committee()
    votes = votes_from(committee, identities, [0, 1, 2])
    disguised = (votes[0], Vote(True, votes[1].signature), votes[2])
    assert not QuorumCertificate(EVENT, disguised).verify(committee)


def test_certificate_from_another_committee_is_invalid():
    committee, identities = make_committee()
    other = Committee.create(
        [identity.public_key for identity in identities],
        1,
        State({"alice": 11}),
    )
    votes = votes_from(other, identities, [0, 1, 2])
    assert QuorumCertificate(EVENT, votes).verify(other)
    assert not QuorumCertificate(EVENT, votes).verify(committee)


def test_certificate_does_not_verify_for_another_event():
    committee, identities = make_committee()
    votes = votes_from(committee, identities, [0, 1, 2])
    assert not QuorumCertificate(OTHER, votes).verify(committee)


def test_order_of_signatures_does_not_matter():
    committee, identities = make_committee()
    votes = votes_from(committee, identities, [2, 0, 3])
    assert QuorumCertificate(EVENT, votes).verify(committee)


def test_faulty_validators_alone_cannot_certify():
    # f faulty validators sign both versions. They need f+1 honest votes more.
    for f in (1, 2, 3):
        committee, identities = make_committee(f)
        faulty = votes_from(committee, identities, range(f))
        assert not QuorumCertificate(EVENT, faulty).verify(committee)


def test_invalid_validator_of_any_type_makes_it_invalid_not_an_error():
    # An unhashable value must not reach the check for repeated signers.
    committee, identities = make_committee()
    good = votes_from(committee, identities, [0, 1, 2])
    for validator in ([0], {"a": 1}, {0}):
        bad = Vote(validator, b"x" * 64)
        assert not QuorumCertificate(EVENT, good + (bad,)).verify(committee)


@pytest.mark.parametrize(
    "indexes",
    [
        [0, 1],  # too few
        [0, 0, 1, 1],  # repeated
        [0, 1, 2, 4],  # one outside the committee
        [0, 1, 2, -1],
    ],
)
def test_no_signature_is_checked_before_the_checks_on_signers(monkeypatch, indexes):
    # Otherwise a large forged certificate would cost one verification per entry.
    def fail(*_):
        raise AssertionError("signature checked before the checks on signers")

    committee, _ = make_committee()
    monkeypatch.setattr(core.attestation, "verify_signature", fail)
    votes = tuple(Vote(index, b"x" * 64) for index in indexes)
    assert not QuorumCertificate(EVENT, votes).verify(committee)


# --- Fixed formats -------------------------------------------------------
#
# Votes on disk and signatures of other nodes depend on these bytes, so a change
# is a change of protocol. Expected values are written out, not computed by the
# code under test.

FIXED_KEYS = tuple(bytes([value]) * 32 for value in (1, 2, 3, 4))
FIXED_ROOT = sha256(b'{"balances":{"alice":10},"nonces":{}}').hexdigest()
FIXED_ID = sha256(
    (
        '{"f":1,"genesis_root":"' + FIXED_ROOT + '","members":['
        + ",".join('"' + key.hex() + '"' for key in FIXED_KEYS)
        + "]}"
    ).encode()
).hexdigest()


def test_committee_id_format_is_fixed():
    committee = Committee(FIXED_KEYS, 1, FIXED_ROOT)
    assert committee == Committee.create(FIXED_KEYS, 1, GENESIS)
    assert committee.committee_id == FIXED_ID


def test_vote_payload_format_is_fixed():
    committee = Committee(FIXED_KEYS, 1, FIXED_ROOT)
    assert vote_payload(committee, EVENT) == (
        b"P-SYSTEM/QUORUM-VOTE/v1\0"
        + bytes.fromhex(FIXED_ID)
        + b'{"amount":8,"nonce":0,"parents":[],"receiver":"bob","sender":"alice"}'
    )


# --- Well-formed events --------------------------------------------------

PARENT = "ab" * 32

MALFORMED_EVENTS = {
    "negative amount": Transfer("alice", "bob", -1, 0),
    "bool amount": Transfer("alice", "bob", True, 0),
    "float amount": Transfer("alice", "bob", 1.0, 0),
    "string amount": Transfer("alice", "bob", "1", 0),
    "none amount": Transfer("alice", "bob", None, 0),
    "amount over the bound": Transfer("alice", "bob", MAX_EVENT_INTEGER + 1, 0),
    # json refuses to write this many digits: it must not surface as an error.
    "amount with too many digits": Transfer("alice", "bob", 10**5000, 0),
    "negative nonce": Transfer("alice", "bob", 1, -1),
    "bool nonce": Transfer("alice", "bob", 1, False),
    "nonce over the bound": Transfer("alice", "bob", 1, MAX_EVENT_INTEGER + 1),
    "non-string sender": Transfer(1, "bob", 1, 0),
    "empty sender": Transfer("", "bob", 1, 0),
    # JSON "\ud800" decodes to this, and SQLite cannot store it.
    "sender with a lone surrogate": Transfer("\ud800", "bob", 1, 0),
    "non-string receiver": Transfer("alice", None, 1, 0),
    "empty receiver": Transfer("alice", "", 1, 0),
    "receiver with a lone surrogate": Transfer("alice", "\udfff", 1, 0),
    "non-hex parent": Transfer("alice", "bob", 1, 0, ("z" * 64,)),
    "uppercase parent": Transfer("alice", "bob", 1, 0, ("AB" * 32,)),
    "short parent": Transfer("alice", "bob", 1, 0, ("ab" * 31,)),
    "long parent": Transfer("alice", "bob", 1, 0, ("ab" * 33,)),
    "parent with a newline": Transfer("alice", "bob", 1, 0, (PARENT + "\n",)),
    "parent with non-ascii digits": Transfer("alice", "bob", 1, 0, ("٠" * 64,)),
    "non-string parent": Transfer("alice", "bob", 1, 0, (1,)),
    # Its decimal form looks like an event id.
    "integer parent of 64 digits": Transfer("alice", "bob", 1, 0, (10**63,)),
    "parents of mixed type": Transfer("alice", "bob", 1, 0, (PARENT, 1)),
    "unhashable parent": Transfer("alice", "bob", 1, 0, ([PARENT],)),
    "parents as a list": Transfer("alice", "bob", 1, 0, [PARENT]),
    "parents as a string": Transfer("alice", "bob", 1, 0, PARENT),
    "parents set to none": Transfer("alice", "bob", 1, 0, None),
}

WELL_FORMED_EVENTS = {
    "plain": EVENT,
    # Refused at execution, as in the model, where these are natural numbers.
    "amount zero": Transfer("alice", "bob", 0, 0),
    "transfer to self": Transfer("alice", "alice", 1, 0),
    "largest integers": Transfer("alice", "bob", MAX_EVENT_INTEGER, MAX_EVENT_INTEGER),
    "one parent": Transfer("alice", "bob", 1, 0, (PARENT,)),
    "parents in any order": Transfer("alice", "bob", 1, 0, ("cd" * 32, PARENT)),
    "a sender that is not ascii": Transfer("àlice", "bob", 1, 0),
}


@pytest.mark.parametrize("name", MALFORMED_EVENTS)
def test_malformed_event_is_recognized(name):
    assert is_well_formed_event(MALFORMED_EVENTS[name]) is False


@pytest.mark.parametrize("name", WELL_FORMED_EVENTS)
def test_well_formed_event_is_recognized(name):
    assert is_well_formed_event(WELL_FORMED_EVENTS[name]) is True


@pytest.mark.parametrize("value", [None, 1, "event", {}, object()])
def test_a_value_that_is_not_an_event_is_not_well_formed(value):
    assert is_well_formed_event(value) is False


@pytest.mark.parametrize("name", MALFORMED_EVENTS)
def test_certificate_on_a_malformed_event_is_invalid_not_an_error(name):
    committee, identities = make_committee()
    # Signed for real wherever the canonical form exists, so that only the event
    # can be the reason for the refusal.
    event = MALFORMED_EVENTS[name]
    try:
        payload = vote_payload(committee, event)
    except (TypeError, ValueError):
        payload = b"no canonical form"
    votes = tuple(
        Vote(index, identities[index].sign(payload))
        for index in range(committee.quorum)
    )

    assert QuorumCertificate(event, votes).verify(committee) is False


@pytest.mark.parametrize(
    "name",
    ["negative amount", "bool amount", "non-hex parent"],
)
def test_malformed_event_is_refused_even_with_valid_signatures(name):
    # These three have a canonical form, so the signatures do verify: without the
    # check on the event this certificate is accepted.
    committee, identities = make_committee()
    event = MALFORMED_EVENTS[name]
    payload = vote_payload(committee, event)
    votes = tuple(
        Vote(index, identities[index].sign(payload))
        for index in range(committee.quorum)
    )

    assert all(vote._verify_payload(committee, payload) for vote in votes)
    assert QuorumCertificate(event, votes).verify(committee) is False


@pytest.mark.parametrize("value", [None, 1, "event", object()])
def test_certificate_on_a_value_that_is_not_an_event_is_invalid(value):
    committee, identities = make_committee()
    votes = votes_from(committee, identities, range(committee.quorum))
    assert QuorumCertificate(value, votes).verify(committee) is False


@pytest.mark.parametrize("name", WELL_FORMED_EVENTS)
def test_certificate_on_a_well_formed_event_is_valid(name):
    committee, identities = make_committee()
    event = WELL_FORMED_EVENTS[name]
    votes = votes_from(committee, identities, range(committee.quorum), event)
    assert QuorumCertificate(event, votes).verify(committee) is True


@pytest.mark.parametrize(
    "votes",
    [None, 1, "votes", [], {}, (None,), (1, 2, 3), ("vote",) * 3, (object(),)],
)
def test_certificate_with_votes_of_a_wrong_type_is_invalid_not_an_error(votes):
    committee, _ = make_committee()
    assert QuorumCertificate(EVENT, votes).verify(committee) is False


def test_certificate_with_votes_in_a_list_is_invalid():
    # Only a tuple: a frozen dataclass that holds a list has no hash.
    committee, identities = make_committee()
    votes = votes_from(committee, identities, range(committee.quorum))
    assert QuorumCertificate(EVENT, list(votes)).verify(committee) is False


@pytest.mark.parametrize("name", MALFORMED_EVENTS)
def test_vote_on_a_malformed_event_does_not_verify_and_is_not_an_error(name):
    committee, identities = make_committee()
    vote = Vote(0, identities[0].sign(b"anything"))
    assert vote.verify(committee, MALFORMED_EVENTS[name]) is False


@pytest.mark.parametrize("name", ["negative amount", "bool amount", "non-hex parent"])
def test_vote_with_a_real_signature_on_a_malformed_event_does_not_verify(name):
    committee, identities = make_committee()
    event = MALFORMED_EVENTS[name]
    vote = Vote(0, identities[0].sign(vote_payload(committee, event)))
    assert vote.verify(committee, event) is False


@pytest.mark.parametrize("name", MALFORMED_EVENTS)
def test_no_vote_can_be_created_on_a_malformed_event(name):
    committee, identities = make_committee()
    with pytest.raises(ValueError):
        Vote.create(committee, identities[0], MALFORMED_EVENTS[name])


def test_integer_bound_is_fixed():
    # Changing it changes which events are valid, so nodes would disagree.
    assert MAX_EVENT_INTEGER == 2**256 - 1
