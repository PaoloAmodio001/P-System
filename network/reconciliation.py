from network.node import Node


def reconcile(
    first: Node,
    second: Node,
) -> None:
    first_events = set(first.events)
    second_events = set(second.events)

    first.merge_events(
        second_events - first_events,
        broadcast=False,
    )

    second.merge_events(
        first_events - second_events,
        broadcast=False,
    )
