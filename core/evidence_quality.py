from core.evidence import Evidence


def independent_observers(evidence: Evidence) -> frozenset[str]:
    return frozenset(evidence.observed_by)


def has_independent_observation(
    evidence: Evidence,
    minimum: int,
) -> bool:
    return len(independent_observers(evidence)) >= minimum
