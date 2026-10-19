from core.event import deduplicate_events
from core.conflict_state import ConflictState
from core.state import State
from core.state_view import StateView
from core.verifiable_state import VerifiableState
from core.verification_proof import VerificationProof
from core.derive import StateDeriver
from core.conflict_closure import find_conflicts


def _validate_event_context(
    initial_state: State,
    event,
    events_by_id: dict,
) -> None:
    """Validate an event against its complete declared ancestor context."""
    context_ids = set()
    pending = list(event.parents)

    while pending:
        parent_id = pending.pop()

        if parent_id in context_ids:
            continue

        parent = events_by_id.get(parent_id)
        if parent is None:
            raise ValueError("INVALID VERIFIABLE STATE")

        context_ids.add(parent_id)
        pending.extend(parent.parents)

    context_ids.add(event.event_id())
    context = [
        events_by_id[event_id]
        for event_id in context_ids
    ]

    try:
        StateDeriver.apply_events(initial_state, context)
    except ValueError as exc:
        raise ValueError("INVALID VERIFIABLE STATE") from exc


def build_verifiable_view(
    initial_state: State,
    events,
) -> StateView:
    # Normalize the input set by canonical event identity.
    # Repeated delivery of the same event must not create
    # duplicate conflict alternatives.
    events = deduplicate_events(events)
    events.sort(key=lambda event: event.event_id())

    # Validate structural closure before handling conflicts.
    verification = VerificationProof.create(events)
    if not verification.verify(events):
        raise ValueError("INVALID VERIFIABLE STATE")

    conflicts = find_conflicts(events)

    if conflicts:
        events_by_id = {
            event.event_id(): event
            for event in events
        }

        # Validate each event within its own causal history.
        # Never execute mutually conflicting alternatives together.
        for event in events:
            _validate_event_context(
                initial_state,
                event,
                events_by_id,
            )

        conflicting_ids = {
            event_id
            for pair in conflicts
            for event_id in pair
        }
        conflicting_events = [
            event
            for event in events
            if event.event_id() in conflicting_ids
        ]

        return StateView.ambiguous(
            ConflictState(alternatives=tuple(conflicting_events))
        )

    verification = VerifiableState.create(
        initial_state,
        events,
    )

    if not verification.verify(initial_state, events):
        raise ValueError("INVALID VERIFIABLE STATE")

    state = StateDeriver.apply_events(initial_state, events)
    return StateView.unique(state)
