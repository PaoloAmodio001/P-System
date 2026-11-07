"""Two orders of governance for one epoch split the reports and block that epoch for good.

`docs/PROTOCOL.md`:90 states the limit: with `threshold` governance keys, two signatures are
the proof, and the protocol has no way out. The first test records the permanent block. The
second is the recovery that does not exist, kept as a strict xfail so that implementing one
forces this file to change.
"""

import pytest

from network.message import encode_epoch_change
from tests.test_quorum_reports import CHANGE, OTHER, Cluster, report_of, wire


@pytest.fixture
def cluster(tmp_path):
    made = Cluster(tmp_path)
    yield made
    made.close()


def split_epoch(cluster):
    report_of(cluster, 0, CHANGE)
    report_of(cluster, 1, CHANGE)
    report_of(cluster, 2, OTHER)
    report_of(cluster, 3, OTHER)


def test_a_split_epoch_never_closes(cluster):
    split_epoch(cluster)

    assert cluster.epochs() == [0, 0, 0, 0]
    assert all(store.closures() == [] for store in cluster.stores.values())

    for index in (0, 1):
        assert cluster.drivers[index].handle_message(
            wire(encode_epoch_change(OTHER))
        ).replies == ()
    for index in (2, 3):
        assert cluster.drivers[index].handle_message(
            wire(encode_epoch_change(CHANGE))
        ).replies == ()

    assert cluster.epochs() == [0, 0, 0, 0]


def test_the_lock_on_an_order_survives_a_restart(cluster):
    split_epoch(cluster)
    cluster.restart(0)

    assert cluster.drivers[0].handle_message(
        wire(encode_epoch_change(OTHER))
    ).replies == ()
    assert cluster.epochs() == [0, 0, 0, 0]


@pytest.mark.xfail(
    strict=True,
    reason="No timeout or emergency governance exists: a split epoch is a documented permanent block",
)
def test_a_timeout_or_emergency_governance_recovers_a_split_epoch(cluster):
    split_epoch(cluster)

    # This is the recovery an operator would want. It must not be described as available.
    cluster.clock.now += 3600

    for index in range(4):
        cluster.drivers[index].retry()

    assert cluster.epochs() == [1, 1, 1, 1]
