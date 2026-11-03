"""Regression: TCP network tests must not depend on receive latency.

The scenarios below used to wait with a fixed ``time.sleep``. With a 0.3 s
delay injected into ``Node._handle_peer_message`` (the handler every
inbound peer message goes through), they failed. They now poll
for the expected condition; this module reruns them under the same delay so
that a reintroduced fixed sleep is caught.
"""
import time

import pytest

# Import the modules, not the test functions: a test function imported
# into this namespace would be collected and run a second time by pytest.
import tests.test_adversarial_inconsistent_sync as adversarial
import tests.test_hidden_event_tcp as hidden_event
import tests.test_partition_reconnect_conflict as partition_reconnect
import tests.test_sync_idempotence as idempotence
import tests.test_sync_order_determinism as order_determinism
from network.node import Node

RECEIVE_DELAY = 0.3

SCENARIOS = [
    idempotence.test_repeated_sync_is_idempotent,
    hidden_event.test_hidden_conflict_changes_status_via_tcp,
    adversarial.test_adversarial_node_cannot_make_peers_forget_conflicting_events,
    order_determinism.test_conflict_status_is_independent_of_sync_order_and_duplicates,
    partition_reconnect.test_partition_reconnect_preserves_both_conflicting_alternatives,
]


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=[scenario.__module__.rsplit(".", 1)[-1] for scenario in SCENARIOS],
)
def test_scenario_survives_slow_receive_path(monkeypatch, scenario):
    original = Node._handle_peer_message
    delayed_calls = []

    def slow_handle_peer_message(self, message, connection=None):
        delayed_calls.append(message.get("type"))
        time.sleep(RECEIVE_DELAY)
        return original(self, message, connection)

    monkeypatch.setattr(
        Node,
        "_handle_peer_message",
        slow_handle_peer_message,
    )

    scenario()

    # The injected delay must actually sit on the path the scenario
    # exercises; otherwise this test would pass without testing anything.
    assert delayed_calls
