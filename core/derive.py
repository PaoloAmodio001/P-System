from core.state import State
from core.event import Transfer, deduplicate_events
from core.resolver import ConflictResolver


class StateDeriver:
    @staticmethod
    def _topological_order(events: list[Transfer]) -> list[Transfer]:
        import heapq

        unique_events = deduplicate_events(events)
        by_id = {
            event.event_id(): event
            for event in unique_events
        }

        parents_by_id = {}
        children = {event_id: [] for event_id in by_id}
        indegree = {}

        for event_id, event in by_id.items():
            parent_ids = set(event.parents)
            unknown = parent_ids - by_id.keys()
            if unknown:
                parent = min(unknown)
                raise ValueError(f"UNKNOWN PARENT: {parent}")

            parents_by_id[event_id] = parent_ids
            indegree[event_id] = len(parent_ids)

            for parent_id in parent_ids:
                children[parent_id].append(event_id)

        ready = [
            event_id
            for event_id, degree in indegree.items()
            if degree == 0
        ]
        heapq.heapify(ready)

        result = []
        while ready:
            event_id = heapq.heappop(ready)
            result.append(by_id[event_id])

            for child_id in children[event_id]:
                indegree[child_id] -= 1
                if indegree[child_id] == 0:
                    heapq.heappush(ready, child_id)

        if len(result) != len(by_id):
            raise ValueError("CYCLIC EVENT DEPENDENCY")

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
