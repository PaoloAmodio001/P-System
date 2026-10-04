from core.conflict_state import ConflictState


class ConflictReconciler:
    @staticmethod
    def merge(
        first: ConflictState,
        second: ConflictState,
    ) -> ConflictState:
        alternatives = []

        for event in first.alternatives + second.alternatives:
            if event not in alternatives:
                alternatives.append(event)

        return ConflictState(
            alternatives=tuple(alternatives)
        )
