from core.conflict_state import ConflictState
from core.state import State
from core.state_view import StateView
from core.verifiable_state import VerifiableState
from core.derive import StateDeriver
from core.conflict_closure import find_conflicts


def build_verifiable_view(
    initial_state: State,
    events,
) -> StateView:

    conflicts = find_conflicts(events)

    if conflicts:
        conflicting_events = []

        for event in events:
            for first_id, second_id in conflicts:
                if event.event_id() in (first_id, second_id):
                    if event not in conflicting_events:
                        conflicting_events.append(event)

        return StateView.ambiguous(
            ConflictState(
                alternatives=tuple(conflicting_events)
            )
        )

    verification = VerifiableState.create(
        initial_state,
        events,
    )

    if not verification.verify(
        initial_state,
        events,
    ):
        raise ValueError("INVALID VERIFIABLE STATE")

    state = StateDeriver.apply_events(
        initial_state,
        list(events),
    )

    return StateView.unique(state)
