from core.state import State
from core.event import Transfer
from core.resolver import ConflictResolver


class StateDeriver:
    @staticmethod
    def _topological_order(events: list[Transfer]) -> list[Transfer]:
        by_id = {
            event.event_id(): event
            for event in events
        }

        for event in events:
            for parent in event.parents:
                if parent not in by_id:
                    raise ValueError(
                        f"UNKNOWN PARENT: {parent}"
                    )

        result = []
        remaining = set(by_id)

        while remaining:
            ready = []

            for event_id in remaining:
                event = by_id[event_id]

                if all(
                    parent not in remaining
                    for parent in event.parents
                ):
                    ready.append(event)

            if not ready:
                raise ValueError(
                    "CYCLIC EVENT DEPENDENCY"
                )

            ready.sort(
                key=lambda event: event.event_id()
            )

            for event in ready:
                result.append(event)
                remaining.remove(event.event_id())

        return result

    @staticmethod
    def apply_events(
        initial: State,
        events: list[Transfer],
    ) -> State:

        if not ConflictResolver.compatible(events):
            raise ValueError("CONFLICTING EVENTS")

        state = initial.copy()

        ordered = StateDeriver._topological_order(events)

        for event in ordered:
            if event.amount <= 0:
                raise ValueError("INVALID AMOUNT")

            if event.sender == event.receiver:
                raise ValueError("INVALID TRANSFER")

            expected_nonce = state.nonce(event.sender)

            if event.nonce != expected_nonce:
                raise ValueError(
                    f"INVALID NONCE: expected "
                    f"{expected_nonce}, "
                    f"got {event.nonce}"
                )

            if state.balance(event.sender) < event.amount:
                raise ValueError(
                    f"INSUFFICIENT BALANCE: "
                    f"{event.sender}"
                )

            state.balances[event.sender] -= event.amount

            state.balances[event.receiver] = (
                state.balances.get(event.receiver, 0)
                + event.amount
            )

            state.nonces[event.sender] = (
                expected_nonce + 1
            )

        return state
