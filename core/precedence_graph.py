from core.precedence import PrecedenceAttestation


class PrecedenceGraph:
    def __init__(self):
        self.edges: dict[str, set[str]] = {}

    def add(self, attestation: PrecedenceAttestation) -> None:
        if not attestation.verify():
            raise ValueError("INVALID ATTESTATION")

        earlier = attestation.earlier_event
        later = attestation.later_event

        self.edges.setdefault(earlier, set()).add(later)
        self.edges.setdefault(later, set())

    def successors(self, event_id: str) -> set[str]:
        return set(self.edges.get(event_id, set()))

    def reachable(self, start: str, target: str) -> bool:
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

    def has_cycle(self) -> bool:
        nodes = set(self.edges)

        for node in nodes:
            if self.reachable(node, node):
                return True

        # reachable() intentionally rejects start == target,
        # so perform explicit DFS for cycle detection.
        visiting = set()
        visited = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True

            if node in visited:
                return False

            visiting.add(node)

            for successor in self.successors(node):
                if visit(successor):
                    return True

            visiting.remove(node)
            visited.add(node)

            return False

        return any(visit(node) for node in nodes)

    def concurrent(self, first: str, second: str) -> bool:
        if first == second:
            return False

        return not (
            self.reachable(first, second)
            or self.reachable(second, first)
        )
