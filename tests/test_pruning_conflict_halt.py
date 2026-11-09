"""A certificate under a pruned snapshot is logged and stays out; there is no proof to halt on.

The limit is declared in `docs/PROTOCOL.md` ("Snapshots"): with its other half pruned, a node
cannot show two valid certificates for one `(sender, nonce)`. The critical log line is the
operator's only evidence. This test also checks that a restart does not turn the absence of
proof into a halt.
"""

import logging

from tests.test_snapshots import (
    attested,
    certificate,
    driver_of,
    open_replica,
    run,
    take,
    transfer,
    wire,
)
from network.message import encode_certificate


def test_a_pruned_conflict_is_reported_and_does_not_halt(tmp_path, caplog):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))
    root = replica.state.root()

    with caplog.at_level(logging.CRITICAL, logger="psystem.quorum"):
        driver.handle_message(
            wire(encode_certificate(certificate(transfer(0, receiver="carol"))))
        )

    assert "conflicts with a snapshot" in caplog.text
    assert not driver.halted
    assert driver.replica.state.root() == root
    assert driver._buffer == {}
    replica._store.close()


def test_a_restart_does_not_invent_the_missing_half(tmp_path):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))
    root = replica.state.root()
    conflict = certificate(transfer(0, receiver="carol"))
    driver.handle_message(wire(encode_certificate(conflict)))
    replica._store.close()

    again = open_replica(path, create=False)
    driver = driver_of(again, prune=True)

    assert not driver.halted
    driver.handle_message(wire(encode_certificate(conflict)))

    assert not driver.halted
    assert again.state.root() == root
    assert again.state.nonce(transfer(0).sender) == 1
    again._store.close()


def test_the_same_certificate_over_the_snapshot_is_not_noise(tmp_path, caplog):
    path = tmp_path / "1.sqlite"
    replica = open_replica(path)
    driver = driver_of(replica, prune=True)
    run(replica, transfer(0))
    take(driver, attested(replica))

    with caplog.at_level(logging.CRITICAL, logger="psystem.quorum"):
        driver.handle_message(wire(encode_certificate(certificate(transfer(0)))))

    assert "conflicts with a snapshot" not in caplog.text
    assert not driver.halted
    replica._store.close()
