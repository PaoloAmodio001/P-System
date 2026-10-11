from core.event import Transfer


def incompatible(first: Transfer, second: Transfer) -> bool:
    """
    Determina se due transfer sono intrinsecamente incompatibili.

    Due eventi sono incompatibili quando:
    - appartengono allo stesso sender;
    - usano lo stesso nonce;
    - sono eventi differenti.

    Non determina quale evento sia corretto.
    """
    if first.sender != second.sender:
        return False

    if first.nonce != second.nonce:
        return False

    return first.event_id() != second.event_id()
