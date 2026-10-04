from dataclasses import dataclass

from core.global_proof import GlobalStateProof


@dataclass(frozen=True)
class Decision:
    """
    Risultato della distinzione tra due candidati di stato.

    X-System non seleziona arbitrariamente un vincitore:
    quando due candidati validi rappresentano stati differenti,
    la decisione resta indeterminata.
    """

    accepted: bool
    reason: str


def distinguish(
    candidate_a: GlobalStateProof,
    candidate_b: GlobalStateProof,
    initial_state=None,
) -> Decision:
    """
    Determina se due GlobalStateProof possono essere distinti
    in modo verificabile.

    Semantica:

    SAME_STATE
        Entrambi i candidati rappresentano lo stesso state_root.

    INVALID_CANDIDATE
        Almeno uno dei candidati non può essere verificato.

    INSUFFICIENT_INFORMATION
        Entrambi i candidati sono validi ma rappresentano
        stati differenti. X-System non introduce un vincitore
        arbitrario.

    Se initial_state non viene fornito, la funzione mantiene
    compatibilità con il modello precedente e utilizza il
    comportamento verificabile disponibile sul candidato.
    """

    if candidate_a.state_root == candidate_b.state_root:
        return Decision(
            accepted=True,
            reason="SAME_STATE",
        )

    if initial_state is None:
        return Decision(
            accepted=False,
            reason="INSUFFICIENT_INFORMATION",
        )

    try:
        valid_a = candidate_a.verify(initial_state)
        valid_b = candidate_b.verify(initial_state)
    except (AttributeError, TypeError, ValueError):
        return Decision(
            accepted=False,
            reason="INVALID_CANDIDATE",
        )

    if not valid_a or not valid_b:
        return Decision(
            accepted=False,
            reason="INVALID_CANDIDATE",
        )

    return Decision(
        accepted=False,
        reason="INSUFFICIENT_INFORMATION",
    )
