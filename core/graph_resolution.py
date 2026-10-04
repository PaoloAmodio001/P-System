from core.event import Transfer
from core.precedence_graph import PrecedenceGraph
from core.resolver import ConflictResolver


class GraphResolver:
    @staticmethod
    def resolve(
        events: list[Transfer],
        graph: PrecedenceGraph,
    ) -> list[Transfer]:
        event_map = {
            event.event_id(): event
            for event in events
        }

        # Il grafo non può contenere cicli.
        if graph.has_cycle():
            raise ValueError("CYCLIC PRECEDENCE")

        # Tutti gli eventi devono essere compatibili.
        if not ConflictResolver.compatible(events):
            raise ValueError("CONFLICTING EVENTS")

        # Restituisce tutti gli eventi validi.
        # La causalità determina le dipendenze,
        # non un ordinamento globale artificiale.
        return [
            event_map[event_id]
            for event_id in sorted(event_map)
        ]
