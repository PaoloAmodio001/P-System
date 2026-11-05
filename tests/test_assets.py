"""Assets as accounts: `owner/issuer.name.supply`. See core/state.py and QuorumAssets.lean.

Each such account is one more account of the protocol, with its own nonce. What is new is only who
can move it, that it stays inside its asset, and that its issuer starts with the supply.
"""

import random

import pytest

from core.attestation import (
    Committee,
    EpochChange,
    EpochReport,
    Governance,
    QuorumCertificate,
    Vote,
    is_authorized_transfer,
)
from core.derive import StateDeriver
from core.event import Transfer
from core.signed_event import SignedTransfer
from core.state import (
    MAX_SUPPLY,
    State,
    account_asset,
    account_owner,
    asset_account,
    asset_id,
    split_asset_account,
)
from crypto.identity import Identity
from network.message import encode_certificate, encode_vote_request
from network.quorum import QuorumDriver, QuorumReplica, SqliteVoteStore
from sdk.client import Client, Wallet, WalletError
from tests.deployment_helpers import Deployment, psystem, wait_until
from tests.test_hardening import layout, service_with, url  # noqa: F401

ISSUER = Identity.create()
ALICE = Identity.create()
BOB = Identity.create()
PALLET = asset_id(ISSUER.identity_id, "pallet-7", 1)
COIN = asset_id(ISSUER.identity_id, "coin", 1000)
OTHER_COIN = asset_id(ALICE.identity_id, "coin", 1000)


def account(identity, asset=COIN):
    return asset_account(identity.identity_id, asset)


def signed(identity, sender, receiver, amount=1, nonce=0):
    return SignedTransfer.create(identity, Transfer(sender, receiver, amount, nonce))


# Names.


def test_a_name_comes_apart():
    assert split_asset_account(account(ALICE)) == (ALICE.identity_id, COIN)
    assert account_owner(account(ALICE)) == ALICE.identity_id
    assert account_asset(account(ALICE)) == COIN


def test_a_plain_account_has_no_asset():
    assert split_asset_account("bob") is None
    assert account_owner("bob") == "bob"
    assert account_asset("bob") is None


HEX = "a" * 64


@pytest.mark.parametrize(
    "bad",
    [
        f"x/{HEX}.n.1",
        f"{HEX}/x",
        f"{HEX}/{HEX}.n.0",
        f"{HEX}/{HEX}.n.01",
        f"{HEX}/{HEX}.n.-1",
        f"{HEX}/{HEX}.n.{MAX_SUPPLY + 1}",
        f"{HEX}/{HEX}..1",
        f"{HEX}/{HEX}.{'n' * 65}.1",
        f"{HEX}/{HEX}.a b.1",
        f"{HEX}/{HEX}.a/b.1",
        f"{HEX}/{'A' * 64}.n.1",
        f"{'A' * 64}/{HEX}.n.1",
        f"{HEX}/{HEX}.n.1\n",
        f"{HEX}/{HEX}.n.1/x",
    ],
)
def test_what_is_not_quite_a_name_is_a_plain_account(bad):
    assert split_asset_account(bad) is None
    assert account_owner(bad) == bad
    assert State().balance(bad) == 0


def test_the_largest_supply_is_allowed():
    assert MAX_SUPPLY == 2**256 - 1
    assert split_asset_account(f"{HEX}/{HEX}.n.{2**256 - 1}") is not None


@pytest.mark.parametrize(
    "issuer, name, supply",
    [("x", "n", 1), (HEX, "", 1), (HEX, "n", 0), (HEX, "n", -1), (HEX, "n", MAX_SUPPLY + 1)],
)
def test_a_bad_asset_cannot_be_made(issuer, name, supply):
    with pytest.raises(ValueError):
        asset_id(issuer, name, supply)


def test_a_bad_account_cannot_be_made():
    with pytest.raises(ValueError):
        asset_account("x", COIN)
    with pytest.raises(ValueError):
        asset_account(HEX, "not an asset")


# Balances.


def test_the_issuer_starts_with_the_supply_and_nobody_else_with_anything():
    state = State()
    assert state.balance(account(ISSUER)) == 1000
    assert state.balance(account(ALICE)) == 0
    assert state.balance(account(ISSUER, OTHER_COIN)) == 0
    assert state.balance(account(ALICE, OTHER_COIN)) == 1000


def test_a_balance_on_record_wins():
    assert State({account(ISSUER): 3}).balance(account(ISSUER)) == 3
    assert State({account(ISSUER): 0}).balance(account(ISSUER)) == 0


def test_an_asset_moves_and_its_total_stays():
    events = [
        Transfer(account(ISSUER), account(ALICE), 300, 0),
        Transfer(account(ALICE), account(BOB), 100, 0),
        Transfer(account(ISSUER), account(BOB), 700, 1),
    ]
    state = StateDeriver.apply_events(State(), events)
    assert state.balance(account(ISSUER)) == 0
    assert state.balance(account(ALICE)) == 200
    assert state.balance(account(BOB)) == 800


def test_more_than_the_supply_does_not_execute():
    with pytest.raises(ValueError):
        StateDeriver.apply_events(State(), [Transfer(account(ISSUER), account(ALICE), 1001, 0)])


def test_each_account_of_an_owner_has_its_own_nonce():
    events = [
        Transfer(account(ALICE, OTHER_COIN), account(BOB, OTHER_COIN), 1, 0),
        Transfer(account(ISSUER), account(BOB), 1, 0),
    ]
    state = StateDeriver.apply_events(State({ISSUER.identity_id: 5}), events)
    assert state.nonce(account(ALICE, OTHER_COIN)) == 1
    assert state.nonce(account(ISSUER)) == 1
    assert state.nonce(ISSUER.identity_id) == 0


@pytest.mark.parametrize("seed", range(10))
def test_any_run_of_authorized_transfers_keeps_the_total(seed):
    # The same property as `asset_supply_conserved`, on Python.
    rng = random.Random(seed)
    people = [ISSUER, ALICE, BOB]
    state = State()
    for _ in range(200):
        sender, receiver = rng.sample(people, 2)
        event = Transfer(
            account(sender),
            account(receiver),
            rng.randint(1, 400),
            state.nonce(account(sender)),
        )
        if StateDeriver._execution_failure(state, event) is None:
            StateDeriver._apply_one(state, event)
    assert sum(state.balance(account(person)) for person in people) == 1000


def test_the_state_root_does_not_depend_on_the_order_of_receipt():
    events = [
        Transfer(account(ISSUER), account(ALICE), 300, 0),
        Transfer(account(ALICE), account(BOB), 100, 0),
    ]
    first = StateDeriver.apply_events(State(), events)
    second = StateDeriver.apply_events(State(), list(reversed(events)))
    assert first.root() == second.root()


# Who may move it.


def test_its_owner_moves_it():
    assert is_authorized_transfer(signed(ALICE, account(ALICE), account(BOB)))


def test_nobody_else_moves_it():
    assert not is_authorized_transfer(signed(BOB, account(ALICE), account(BOB)))


def test_not_even_its_issuer():
    assert not is_authorized_transfer(signed(ISSUER, account(ALICE), account(BOB)))


def test_it_stays_in_its_asset():
    assert not is_authorized_transfer(signed(ALICE, account(ALICE), account(BOB, OTHER_COIN)))


def test_it_does_not_leave_for_the_native_unit():
    assert not is_authorized_transfer(signed(ALICE, account(ALICE), BOB.identity_id))


def test_the_native_unit_does_not_enter_an_asset():
    assert not is_authorized_transfer(signed(ALICE, ALICE.identity_id, account(BOB)))


def test_a_transfer_of_the_native_unit_is_as_before():
    assert is_authorized_transfer(signed(ALICE, ALICE.identity_id, "bob"))
    assert not is_authorized_transfer(signed(BOB, ALICE.identity_id, "bob"))


def test_a_name_that_is_not_quite_an_asset_belongs_to_nobody():
    # Otherwise a signer could use it to move what is not theirs, or the other way around.
    name = f"{ALICE.identity_id}/not-an-asset"
    assert not is_authorized_transfer(signed(ALICE, name, "bob"))


# In the protocol.


MEMBERS = sorted((Identity.create() for _ in range(4)), key=lambda m: m.public_key)
COMMITTEE = Committee.create([m.public_key for m in MEMBERS], 1, State())


@pytest.fixture
def driver(tmp_path):
    store = SqliteVoteStore(tmp_path / "v.sqlite", COMMITTEE, MEMBERS[0].public_key, create=True)
    made = QuorumDriver(
        QuorumReplica(MEMBERS[0], State(), store, lambda event: True),
        require_funds=True,
        max_nonce_ahead=16,
    )
    yield made
    store.close()


def replies_to(driver, one):
    return driver.handle_message(encode_vote_request(one)).replies


def test_a_validator_votes_for_a_transfer_by_the_issuer(driver):
    assert replies_to(driver, signed(ISSUER, account(ISSUER), account(ALICE)))


def test_a_validator_does_not_vote_for_a_stranger_moving_an_asset(driver):
    assert not replies_to(driver, signed(BOB, account(ISSUER), account(BOB)))


def test_a_validator_does_not_vote_across_assets(driver):
    assert not replies_to(driver, signed(ISSUER, account(ISSUER), account(ALICE, OTHER_COIN)))


def test_a_validator_refuses_a_second_version_of_a_spend_of_an_asset(driver):
    assert replies_to(driver, signed(ISSUER, account(ISSUER), account(ALICE)))
    assert not replies_to(driver, signed(ISSUER, account(ISSUER), account(BOB)))


def test_an_owner_of_nothing_gets_no_vote_under_the_limit(driver):
    assert not replies_to(driver, signed(ALICE, account(ALICE), account(BOB)))


def test_a_report_with_a_transfer_across_assets_is_refused():
    bad = signed(ISSUER, account(ISSUER), account(ALICE, OTHER_COIN))
    change_id = "a" * 64
    report = EpochReport.create(COMMITTEE, MEMBERS[0], change_id, [bad])
    assert not report.verify(COMMITTEE, change_id)


def test_a_certificate_moves_an_asset_on_a_node(driver):
    event = Transfer(account(ISSUER), account(ALICE), 40, 0)
    votes = tuple(Vote.create(COMMITTEE, member, event) for member in MEMBERS[:3])
    driver.handle_message(encode_certificate(QuorumCertificate(event, votes)))
    assert driver.replica.state.balance(account(ALICE)) == 40
    assert driver.replica.state.balance(account(ISSUER)) == 960


# The wallet.


def test_a_wallet_of_an_asset_signs_for_that_account(tmp_path):
    wallet = Wallet(ISSUER, tmp_path / "j", COIN)
    assert wallet.account == account(ISSUER)
    one = wallet.transfer(ALICE.identity_id, 5)
    assert one.transfer.sender == account(ISSUER)
    assert one.transfer.receiver == account(ALICE)
    assert is_authorized_transfer(one)
    wallet.close()


def test_a_wallet_takes_a_full_account_too(tmp_path):
    wallet = Wallet(ISSUER, tmp_path / "j", COIN)
    assert wallet.transfer(account(ALICE), 5).transfer.receiver == account(ALICE)
    wallet.close()


def test_a_journal_is_for_one_account(tmp_path):
    Wallet(ISSUER, tmp_path / "j", COIN).close()
    with pytest.raises(WalletError, match="ANOTHER ACCOUNT"):
        Wallet(ISSUER, tmp_path / "j", OTHER_COIN)
    with pytest.raises(WalletError, match="ANOTHER ACCOUNT"):
        Wallet(ISSUER, tmp_path / "j")


def test_a_wallet_without_an_asset_is_as_before(tmp_path):
    wallet = Wallet(ALICE, tmp_path / "j")
    assert wallet.account == ALICE.identity_id
    assert wallet.transfer("bob", 1).transfer.receiver == "bob"
    wallet.close()


# The API, and four real processes.


def test_the_api_answers_for_an_account_of_an_asset(layout):  # noqa: F811
    service = service_with(layout)
    service.start()
    try:
        answer = Client(url(service, path="")).account(account(ISSUER))
        assert answer == {"account": account(ISSUER), "balance": 1000, "next_nonce": 0}
    finally:
        service.stop()


def test_the_command_says_the_name_of_an_asset():
    assert psystem("asset-id", "--issuer", HEX, "--name", "n", "--supply", "5").strip() == f"{HEX}.n.5"


@pytest.mark.slow
def test_custody_of_one_item_along_a_chain_on_real_processes(tmp_path):
    # A unique item, moved by whoever holds it. Nothing else can make a second one.
    deployment = Deployment(tmp_path)
    deployment.start_all()

    try:
        api = [Client(deployment.api_url(i)) for i in range(4)]
        assert wait_until(lambda: all(len(c.status()["peers"]) == 3 for c in api))
        maker = Identity.load(deployment.sender_key)
        item = asset_id(maker.identity_id, "pallet-7", 1)
        carrier, shop = Identity.create(), Identity.create()

        # Funds of the item are what admits a vote: the limit on senders with nothing holds too.
        first = Wallet(maker, tmp_path / "maker.j", item).transfer(carrier.identity_id, 1)
        assert api[0].submit(first)["accepted"]
        holder = asset_account(carrier.identity_id, item)
        assert wait_until(lambda: all(c.account(holder)["balance"] == 1 for c in api))

        second = Wallet(carrier, tmp_path / "carrier.j", item).transfer(shop.identity_id, 1)
        assert api[1].submit(second)["accepted"]
        last = asset_account(shop.identity_id, item)
        assert wait_until(lambda: all(c.account(last)["balance"] == 1 for c in api))
        assert api[2].account(holder)["balance"] == 0
        assert api[2].account(asset_account(maker.identity_id, item))["balance"] == 0
        assert len({c.status()["state_root"] for c in api}) == 1
    finally:
        deployment.stop_all()
