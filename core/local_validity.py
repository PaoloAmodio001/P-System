from core.event import Transfer
from core.state import State
from core.proof import verify_transfer


def locally_valid(state: State, event: Transfer) -> bool:
    """
    Un evento è localmente valido rispetto a uno specifico stato.

    Non determina se quello stato sia globalmente vincente.
    """
    return verify_transfer(state, event)
