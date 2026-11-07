from core.exceptions import SupplyViolation
from core.state import State, account_asset
from core.event import Transfer, deduplicate_events
from core.resolver import ConflictResolver




def check_supply_conservation(event: Transfer) -> None:
    """Raise SupplyViolation if the event crosses declared asset account sets."""
    sender_asset = account_asset(event.sender)
    receiver_asset = account_asset(event.receiver)
    if sender_asset != receiver_asset:
        violated = {}
        if sender_asset is not None:
            violated[sender_asset] = -event.amount
        if receiver_asset is not None:
            violated[receiver_asset] = event.amount
        raise SupplyViolation(violated=violated, delta=event.amount)

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
    def _execution_failure(state: State, event: Transfer) -> str | None:
        """Return why `event` cannot execute on `state`, or None."""
        check_supply_conservation(event)
        expected_nonce = state.nonce(event.sender)

        if event.nonce != expected_nonce:
            return (
                f"INVALID NONCE: expected "
                f"{expected_nonce}, "
                f"got {event.nonce}"
            )

        if state.balance(event.sender) < event.amount:
            return (
                f"INSUFFICIENT BALANCE: "
                f"{event.sender}"
            )

        return None

    @staticmethod
    def _execution_order(
        initial: State,
        events: list[Transfer],
    ) -> list[Transfer]:
        """
        Deterministic execution order for a compatible event set.

        Declared parents are hard constraints. Among the causally
        ready events, the one with the smallest event id that is
        currently executable runs next.

        Earlier versions ran the smallest ready id unconditionally.
        That made the outcome depend on hash values whenever a
        dependency was implicit (consecutive nonces of one sender,
        or spending funds just received), so valid histories were
        rejected depending on their event ids.

        The result depends only on the set of events, never on the
        order in which they were supplied. The greedy choice is
        complete: executing an event of sender X only lowers X's
        balance and advances X's nonce, so it never disables a ready
        event of another sender, and X's own events are totally
        ordered by nonce. If any valid order exists, this finds one.
        """
        ordered = StateDeriver._topological_order(events)

        for event in ordered:
            if event.amount <= 0:
                raise ValueError("INVALID AMOUNT")

            if event.sender == event.receiver:
                raise ValueError("INVALID TRANSFER")
            check_supply_conservation(event)

        by_id = {event.event_id(): event for event in ordered}
        pending_parents = {
            event_id: set(event.parents)
            for event_id, event in by_id.items()
        }
        children = {event_id: [] for event_id in by_id}
        for event_id, parents in pending_parents.items():
            for parent_id in parents:
                children[parent_id].append(event_id)

        ready = sorted(
            event_id
            for event_id, parents in pending_parents.items()
            if not parents
        )

        state = initial.copy()
        result = []

        while ready:
            chosen = None
            for event_id in ready:
                if StateDeriver._execution_failure(
                    state, by_id[event_id]
                ) is None:
                    chosen = event_id
                    break

            if chosen is None:
                raise ValueError(
                    StateDeriver._execution_failure(
                        state, by_id[ready[0]]
                    )
                )

            ready.remove(chosen)
            event = by_id[chosen]
            StateDeriver._apply_one(state, event)
            result.append(event)

            for child_id in children[chosen]:
                pending_parents[child_id].discard(chosen)
                if not pending_parents[child_id]:
                    ready.append(child_id)
            ready.sort()

        return result

    @staticmethod
    def _apply_one(state: State, event: Transfer) -> None:
        check_supply_conservation(event)
        state.balances[event.sender] = state.balance(event.sender) - event.amount

        state.balances[event.receiver] = (
            state.balance(event.receiver)
            + event.amount
        )

        state.nonces[event.sender] = (
            state.nonce(event.sender) + 1
        )

    @staticmethod
    def apply_events(
        initial: State,
        events: list[Transfer],
    ) -> State:

        if not ConflictResolver.compatible(events):
            raise ValueError("CONFLICTING EVENTS")

        state = initial.copy()

        for event in StateDeriver._execution_order(initial, events):
            StateDeriver._apply_one(state, event)

        return state
