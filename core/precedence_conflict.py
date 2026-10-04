from core.precedence import PrecedenceAttestation


def contradictory(
    first: PrecedenceAttestation,
    second: PrecedenceAttestation,
) -> bool:
    return (
        first.earlier_event == second.later_event
        and first.later_event == second.earlier_event
    )
