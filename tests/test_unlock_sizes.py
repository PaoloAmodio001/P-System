"""Sizes and ids of the 5f+1 configuration, with no committee built at import: see test_unlock_mutations."""

from core.attestation import Committee
from core.state import State
from crypto.identity import Identity

GENESIS = State({"alice": 1})


def keys(count):
    return sorted(Identity.create().public_key for _ in range(count))


def test_a_committee_with_unlocking_has_5f_plus_1_members():
    assert Committee.create(keys(6), 1, GENESIS, unlock=True).n == 6
    assert Committee.create(keys(11), 2, GENESIS, unlock=True).quorum == 9


def test_create_keeps_the_setting():
    assert Committee.create(keys(6), 1, GENESIS, unlock=True).unlock
    assert not Committee.create(keys(4), 1, GENESIS).unlock


def test_the_setting_changes_the_id_of_the_same_members():
    # With f = 0 both have one member. Two chains that differ only here must not take each other's votes.
    one = keys(1)
    assert (
        Committee.create(one, 0, GENESIS).committee_id
        != Committee.create(one, 0, GENESIS, unlock=True).committee_id
    )
