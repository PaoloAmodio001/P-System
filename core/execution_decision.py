from dataclasses import dataclass

from core.execution_relations import ExecutionRelations


@dataclass(frozen=True)
class ExecutionDecision:
    executable: tuple[str, ...]
    causal: tuple[tuple[str, str], ...]
    parallel: tuple[tuple[str, str], ...]
    conflicts: tuple[tuple[str, str], ...]

    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def decide(relations: ExecutionRelations) -> ExecutionDecision:
    blocked = {
        event_id
        for pair in relations.conflicts
        for event_id in pair
    }

    all_events = set(relations.event_ids)

    if not all_events:
        all_events = {
            event_id
            for pair in (
                relations.causal
                + relations.parallel
                + relations.conflicts
            )
            for event_id in pair
        }

    executable = tuple(
        sorted(all_events - blocked)
    )

    return ExecutionDecision(
        executable=executable,
        causal=relations.causal,
        parallel=relations.parallel,
        conflicts=relations.conflicts,
    )
