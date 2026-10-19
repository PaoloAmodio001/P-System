from core.event import Transfer, event_payload


def incompatible(first: Transfer, second: Transfer) -> bool:
    """
    Determina se due transfer sono intrinsecamente incompatibili.

    Eventi con lo stesso ID devono avere lo stesso contenuto canonico.
    Un ID riutilizzato per contenuti differenti è un errore di integrità.
    """
    first_id = first.event_id()
    second_id = second.event_id()

    if first_id == second_id:
        if event_payload(first) != event_payload(second):
            raise ValueError("DUPLICATE EVENT ID WITH DIFFERENT CONTENT")
        return False

    if first.sender != second.sender:
        return False

    if first.nonce != second.nonce:
        return False

    return True
