from core.snapshot import GraphSnapshot
from core.resolver import ConflictResolver


def compatible(
    first: GraphSnapshot,
    second: GraphSnapshot,
) -> bool:
    """
    Verifica se due snapshot possono coesistere.

    Non richiede che contengano gli stessi eventi.
    Cerca soltanto conflitti tra gli eventi conosciuti
    da entrambi gli snapshot.
    """

    events = list(first.events) + list(second.events)

    return ConflictResolver.compatible(events)
