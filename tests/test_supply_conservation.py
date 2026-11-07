"""Runtime enforcement of asset supply conservation (priority 1)."""

import pytest

from core.attestation import Committee, QuorumCertificate, Vote
from core.derive import StateDeriver, check_supply_conservation
from core.event import Transfer
from core.exceptions import SupplyViolation
from core.state import State, asset_account, asset_id
from crypto.identity import Identity
from network.quorum import QuorumReplica, SqliteVoteStore

ISSUER = Identity.create()
ALICE = Identity.create()
BOB = Identity.create()
COIN = asset_id(ISSUER.identity_id, "coin", 1000)
OTHER = asset_id(ALICE.identity_id, "other", 500)


def account(identity, asset):
    return asset_account(identity.identity_id, asset)


def committee_and_members():
    identities = [Identity.create() for _ in range(4)]
    identities.sort(key=lambda i: i.public_key)
    committee = Committee.create([m.public_key for m in identities], 1, State())
    return committee, identities


def open_replica(tmp_path, name="votes.sqlite"):
    committee, members = committee_and_members()
    store = SqliteVoteStore(
        tmp_path / name, committee, members[0].public_key, create=True
    )
    # auth accepts the event shape so the supply check is the gate under test
    return QuorumReplica(members[0], State(), store, lambda _e: True), committee, members


def test_check_supply_conservation_rejects_cross_asset_transfer():
    event = Transfer(account(ISSUER, COIN), account(ALICE, OTHER), 10, 0)
    with pytest.raises(SupplyViolation) as exc:
        check_supply_conservation(event)
    assert COIN in exc.value.violated
    assert OTHER in exc.value.violated
    assert exc.value.delta == 10


def test_check_supply_conservation_allows_same_asset():
    event = Transfer(account(ISSUER, COIN), account(ALICE, COIN), 10, 0)
    check_supply_conservation(event)


def test_derive_refuses_cross_asset_event():
    event = Transfer(account(ISSUER, COIN), account(ALICE, OTHER), 10, 0)
    with pytest.raises(SupplyViolation):
        StateDeriver.apply_events(State(), [event])


def test_cross_asset_event_rejected_before_certification(tmp_path):
    replica, committee, members = open_replica(tmp_path)
    event = Transfer(account(ISSUER, COIN), account(ALICE, OTHER), 10, 0)

    with pytest.raises(SupplyViolation):
        replica.handle_vote_request(event, None)

    # No vote recorded, no state change - rejected before certification.
    assert replica.votes() == []
    assert replica.executed == []
    assert replica.state.nonce(event.sender) == 0
