from core.distributed_executor import DistributedExecutor
from core.event import Transfer
from core.execution_plan import build_execution_plan
from core.state import State


def test_two_nodes_converge_on_parallel_events():
    initial = State({
        "alice": 10,
        "bob": 10,
        "carol": 0,
        "dave": 0,
    })

    first = Transfer("alice", "carol", 5, 0)
    second = Transfer("bob", "dave", 5, 0)

    events = [first, second]

    plan = build_execution_plan(
        initial,
        events,
    )

    node_a = DistributedExecutor("node-a")
    node_b = DistributedExecutor("node-b")

    result_a = node_a.execute(
        initial,
        events,
        plan,
    )

    result_b = node_b.execute(
        initial,
        list(reversed(events)),
        plan,
    )

    assert result_a.state_root == result_b.state_root
    assert result_a.state_root != initial.root()


def test_conflicting_plan_is_not_executed():
    initial = State({
        "alice": 10,
        "bob": 0,
        "carol": 0,
    })

    first = Transfer("alice", "bob", 6, 0)
    second = Transfer("alice", "carol", 7, 0)

    events = [first, second]

    plan = build_execution_plan(
        initial,
        events,
    )

    node = DistributedExecutor("node-a")

    try:
        node.execute(initial, events, plan)
    except ValueError as exc:
        assert str(exc) == "CANNOT EXECUTE CONFLICTING PLAN"
    else:
        raise AssertionError("CONFLICTING PLAN WAS EXECUTED")


def test_nodes_converge_with_different_event_arrival_order():
    initial = State({
        "alice": 10,
        "bob": 10,
        "carol": 0,
        "dave": 0,
        "erin": 0,
    })

    # Alice has a local causal sequence.
    alice_first = Transfer(
        "alice",
        "carol",
        4,
        0,
    )

    alice_second = Transfer(
        "alice",
        "erin",
        3,
        1,
        parents=(alice_first.event_id(),),
    )

    # Bob acts independently.
    bob_event = Transfer(
        "bob",
        "dave",
        5,
        0,
    )

    events = [
        alice_first,
        alice_second,
        bob_event,
    ]

    plan = build_execution_plan(
        initial,
        events,
    )

    node_a = DistributedExecutor("node-a")
    node_b = DistributedExecutor("node-b")

    # Different arrival order.
    result_a = node_a.execute(
        initial,
        [
            alice_first,
            alice_second,
            bob_event,
        ],
        plan,
    )

    result_b = node_b.execute(
        initial,
        [
            bob_event,
            alice_second,
            alice_first,
        ],
        plan,
    )

    assert result_a.state_root == result_b.state_root


def test_multiple_independent_causal_chains_converge():
    initial = State({
        "alice": 20,
        "bob": 20,
        "carol": 20,
        "dave": 0,
        "erin": 0,
        "frank": 0,
        "gina": 0,
    })

    # Alice chain: A0 -> A1 -> A2
    a0 = Transfer("alice", "dave", 5, 0)

    a1 = Transfer(
        "alice",
        "erin",
        4,
        1,
        parents=(a0.event_id(),),
    )

    a2 = Transfer(
        "alice",
        "frank",
        3,
        2,
        parents=(a1.event_id(),),
    )

    # Bob chain: B0 -> B1
    b0 = Transfer("bob", "dave", 6, 0)

    b1 = Transfer(
        "bob",
        "erin",
        5,
        1,
        parents=(b0.event_id(),),
    )

    # Carol chain: C0 -> C1 -> C2
    c0 = Transfer("carol", "dave", 4, 0)

    c1 = Transfer(
        "carol",
        "erin",
        3,
        1,
        parents=(c0.event_id(),),
    )

    c2 = Transfer(
        "carol",
        "gina",
        2,
        2,
        parents=(c1.event_id(),),
    )

    events = [
        a0, a1, a2,
        b0, b1,
        c0, c1, c2,
    ]

    plan = build_execution_plan(
        initial,
        events,
    )

    node_a = DistributedExecutor("node-a")
    node_b = DistributedExecutor("node-b")

    result_a = node_a.execute(
        initial,
        events,
        plan,
    )

    result_b = node_b.execute(
        initial,
        [
            c2, c0, b1, a2,
            c1, b0, a0, a1,
        ],
        plan,
    )

    assert result_a.state_root == result_b.state_root

    assert result_a.completed == frozenset(
        event.event_id()
        for event in events
    )

    assert result_b.completed == result_a.completed
