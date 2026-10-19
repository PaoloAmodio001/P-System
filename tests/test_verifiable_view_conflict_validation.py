import pytest

from core.event import Transfer
from core.state import State
from core.verifiable_view import build_verifiable_view


def _initial():
    return State(
        balances={"alice": 10, "bob": 0},
        nonces={"alice": 0, "bob": 0},
    )


def _conflicting_events():
    return (
        Transfer("alice", "bob", 3, 0),
        Transfer("alice", "carol", 4, 0),
    )


def test_invalid_amount_is_rejected_even_when_conflict_exists():
    initial = _initial()
    valid, _ = _conflicting_events()
    invalid = Transfer("alice", "carol", 0, 0)

    with pytest.raises(ValueError, match="INVALID VERIFIABLE STATE"):
        build_verifiable_view(initial, [valid, invalid])


def test_missing_parent_is_rejected_even_when_conflict_exists():
    initial = _initial()
    first, second = _conflicting_events()
    orphan = Transfer(
        "bob", "carol", 1, 0,
        parents=("f" * 64,),
    )

    with pytest.raises(ValueError, match="INVALID VERIFIABLE STATE"):
        build_verifiable_view(initial, [first, second, orphan])


def test_invalid_descendant_context_is_rejected_during_conflict():
    initial = _initial()
    first, second = _conflicting_events()
    # Il primo evento accredita Bob di 3; il discendente ne spende 4.
    invalid_child = Transfer(
        "bob", "dave", 4, 0,
        parents=(first.event_id(),),
    )

    with pytest.raises(ValueError, match="INVALID VERIFIABLE STATE"):
        build_verifiable_view(
            initial,
            [first, second, invalid_child],
        )


def test_valid_conflicting_alternatives_remain_ambiguous():
    view = build_verifiable_view(
        _initial(),
        list(_conflicting_events()),
    )

    assert view.is_ambiguous()
    assert view.has_winner() is False
    assert set(view.alternatives()) == set(_conflicting_events())
