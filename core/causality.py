from core.event import Transfer


class CausalGraph:
    def __init__(self):
        self.events: dict[str, Transfer] = {}

    def add(self, event: Transfer) -> str:
        event_id = event.event_id()

        # Every parent must already exist.
        for parent in event.parents:
            if parent not in self.events:
                raise ValueError(
                    f"UNKNOWN PARENT: {parent}"
                )

        self.events[event_id] = event
        return event_id

    def contains(self, event_id: str) -> bool:
        return event_id in self.events

    def parents_of(self, event_id: str) -> tuple[str, ...]:
        if event_id not in self.events:
            raise KeyError(event_id)

        return self.events[event_id].parents

    def ancestors(self, event_id: str) -> set[str]:
        if event_id not in self.events:
            raise KeyError(event_id)

        result = set()
        stack = list(self.events[event_id].parents)

        while stack:
            current = stack.pop()

            if current in result:
                continue

            result.add(current)

            event = self.events.get(current)

            if event:
                stack.extend(event.parents)

        return result
