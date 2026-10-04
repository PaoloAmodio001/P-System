from core.event import Transfer
from core.proof import apply_transfer
from core.state import State


def _apply_in_given_order(
    initial: State,
    events: list[Transfer],
) -> State:
    state = initial.copy()

    for event in events:
        state = apply_transfer(state, event)

    return state


def commute(
    initial: State,
    first: Transfer,
    second: Transfer,
) -> bool:
    """
    Verifica la reale commutatività di due eventi.

    Gli eventi vengono applicati nell'ordine fornito:
        first -> second
        second -> first

    Non viene usato alcun ordinamento canonico.
    """

    try:
        state_ab = _apply_in_given_order(
            initial,
            [first, second],
        )

        state_ba = _apply_in_given_order(
            initial,
            [second, first],
        )

    except ValueError:
        return False

    return state_ab.root() == state_ba.root()
