from dataclasses import dataclass


@dataclass(frozen=True)
class RelevanceGraph:
    edges: dict[str, frozenset[str]]

    @classmethod
    def build(
        cls,
        edges: dict[str, set[str] | frozenset[str]],
    ) -> "RelevanceGraph":
        return cls(
            edges={
                source: frozenset(targets)
                for source, targets in edges.items()
            }
        )

    def successors(self, node: str) -> frozenset[str]:
        return self.edges.get(
            node,
            frozenset(),
        )

    def reachable(
        self,
        start: str,
        target: str,
    ) -> bool:
        if start == target:
            return False

        visited = set()
        stack = [start]

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)

            for successor in self.successors(current):
                if successor == target:
                    return True

                stack.append(successor)

        return False

    def closure(
        self,
        roots: set[str] | frozenset[str],
    ) -> frozenset[str]:

        result = set(roots)
        stack = list(roots)

        while stack:
            current = stack.pop()

            for successor in self.successors(current):
                if successor in result:
                    continue

                result.add(successor)
                stack.append(successor)

        return frozenset(result)
