"""The wallet reads its journal through an index, in numeric order, and signs no nonce it cannot order.

Nonces are stored as text, and "10" < "9" as text. Before, `next_nonce` and `unfinished` read the whole journal
into memory and sorted it in Python. Now SQL does it with an index on CAST(nonce AS INTEGER), which has 64 bits, so
the wallet refuses a nonce outside 0 .. 2**63 - 1 before it signs anything.
"""

import pytest

from crypto.identity import Identity
from sdk.client import MAX_WALLET_NONCE, Wallet, WalletError


@pytest.fixture
def wallet(tmp_path):
    made = Wallet(Identity.create(), tmp_path / "wallet.sqlite")
    yield made
    made.close()


def plan(wallet, sql, *arguments) -> str:
    rows = wallet._connection.execute("EXPLAIN QUERY PLAN " + sql, arguments).fetchall()
    return " ".join(str(row[-1]) for row in rows)


def test_nine_comes_before_ten(wallet):
    for nonce in (10, 9, 11):
        wallet.transfer("bob", 1, nonce=nonce)

    assert wallet.next_nonce() == 12
    assert [s.transfer.nonce for s in wallet.unfinished(9)] == [9, 10, 11]
    assert [s.transfer.nonce for s in wallet.unfinished(10)] == [10, 11]
    assert wallet.unfinished(12) == []


def test_the_largest_nonce_it_signs(wallet):
    wallet.transfer("bob", 1, nonce=MAX_WALLET_NONCE)

    assert wallet.next_nonce() == MAX_WALLET_NONCE + 1
    assert [s.transfer.nonce for s in wallet.unfinished(MAX_WALLET_NONCE)] == [MAX_WALLET_NONCE]
    assert wallet.unfinished(MAX_WALLET_NONCE + 1) == []


@pytest.mark.parametrize("nonce", [-1, MAX_WALLET_NONCE + 1, True, 1.0, "3"])
def test_a_nonce_it_cannot_order_is_refused_before_signing(wallet, nonce):
    with pytest.raises(WalletError):
        wallet.transfer("bob", 1, nonce=nonce)

    assert wallet._connection.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


def test_both_queries_use_the_index(wallet):
    wallet.transfer("bob", 1)

    assert "events_by_nonce" in plan(wallet, "SELECT MAX(CAST(nonce AS INTEGER)) FROM events")
    assert "events_by_nonce" in plan(
        wallet,
        "SELECT nonce, canonical, signature FROM events WHERE CAST(nonce AS INTEGER) >= ? "
        "ORDER BY CAST(nonce AS INTEGER)",
        0,
    )


def test_a_journal_made_before_the_index_gets_it(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite"
    identity = Identity.create()
    Wallet(identity, path).close()
    connection = sqlite3.connect(path)
    connection.execute("DROP INDEX events_by_nonce")
    connection.commit()
    connection.close()

    again = Wallet(identity, path)
    names = {row[0] for row in again._connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    again.close()

    assert "events_by_nonce" in names
