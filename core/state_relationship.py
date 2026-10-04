from enum import Enum

from core.event import Transfer
from core.proof import apply_transfer
from core.state import State


class StateRelationship(Enum):
    COMPATIBLE = "COMPATIBLE"
    ORDER_DEPENDENT = "ORDER_DEPENDENT"
    CONFLICT = "CONFLICT"


def classify_relationship(
    initial: State,
    first: Transfer,
    second: Transfer,
) -> StateRelationship:
    first_valid = True
    second_valid = True

    try:
        apply_transfer(
            apply_transfer(initial, first),
            second,
        )
    except ValueError:
        first_valid = False

    try:
        apply_transfer(
            apply_transfer(initial, second),
            first,
        )
    except ValueError:
        second_valid = False

    if first_valid and second_valid:
        return StateRelationship.COMPATIBLE

    if first_valid != second_valid:
        return StateRelationship.ORDER_DEPENDENT

    return StateRelationship.CONFLICT
