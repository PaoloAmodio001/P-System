from core.event import Transfer
from core.state import State
from core.proof import apply_transfer


def state_conflict(
    initial: State,
    first: Transfer,
    second: Transfer,
) -> bool:
    """
    Returns True when the two events cannot both be applied
    successfully to the same initial state in either order.
    """

    try:
        state_ab = apply_transfer(
            apply_transfer(initial, first),
            second,
        )
    except ValueError:
        state_ab = None

    try:
        state_ba = apply_transfer(
            apply_transfer(initial, second),
            first,
        )
    except ValueError:
        state_ba = None

    return state_ab is None and state_ba is None
