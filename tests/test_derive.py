from core.state import State
from core.event import Transfer
from core.derive import StateDeriver


def test_deterministic_state():

    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    events = [
        Transfer("alice", "bob", 3, 0),
        Transfer("alice", "carol", 2, 1),
    ]

    state_a = StateDeriver.apply_events(
        initial,
        events,
    )

    state_b = StateDeriver.apply_events(
        initial,
        list(reversed(events)),
    )

    assert state_a.root() == state_b.root()

    assert state_a.balance("alice") == 5
    assert state_a.balance("bob") == 3
    assert state_a.balance("carol") == 2


def test_conflicting_events_rejected():

    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    events = [
        Transfer("alice", "bob", 8, 0),
        Transfer("alice", "carol", 8, 0),
    ]

    try:
        StateDeriver.apply_events(initial, events)
        assert False
    except ValueError as error:
        assert str(error) == "CONFLICTING EVENTS"
