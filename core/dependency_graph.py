from dataclasses import dataclass
from core.event import Transfer


@dataclass(frozen=True)
class DependencyGraph:
    dependencies: dict[str, frozenset[str]]

    @classmethod
    def build(
        cls,
        events: list[Transfer],
    ) -> "DependencyGraph":
        event_ids = {
            event.event_id()
            for event in events
        }

        dependencies = {}

        for event in events:
            event_id = event.event_id()

            missing = set(event.parents) - event_ids

            if missing:
                raise ValueError(
                    f"UNKNOWN PARENT: {sorted(missing)}"
                )

            dependencies[event_id] = frozenset(
                event.parents
            )

        return cls(
            dependencies=dependencies,
        )

    def parents_of(self, event_id: str) -> frozenset[str]:
        return self.dependencies.get(
            event_id,
            frozenset(),
        )

    def ready(
        self,
        completed: set[str],
    ) -> frozenset[str]:
        """
        Events whose causal dependencies have all
        already been completed.
        """
        return frozenset(
            event_id
            for event_id, parents in self.dependencies.items()
            if event_id not in completed
            and parents.issubset(completed)
        )

    def complete(self) -> bool:
        return not self.dependencies

    def has_cycle(self) -> bool:
        remaining = {
            event_id: set(parents)
            for event_id, parents in self.dependencies.items()
        }

        while remaining:
            ready = {
                event_id
                for event_id, parents in remaining.items()
                if not parents
            }

            if not ready:
                return True

            for event_id in ready:
                del remaining[event_id]

            for parents in remaining.values():
                parents.difference_update(ready)

        return False
