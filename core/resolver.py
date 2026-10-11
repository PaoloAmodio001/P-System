from core.event import Transfer


class ConflictResolver:

    @staticmethod
    def conflicting(a: Transfer, b: Transfer) -> bool:
        """
        Two transfers conflict when they attempt to spend
        the same sender state at the same nonce.
        """

        if a.sender != b.sender:
            return False

        if a.nonce != b.nonce:
            return False

        return a.event_id() != b.event_id()

    @staticmethod
    def compatible(events: list[Transfer]) -> bool:
        for i, first in enumerate(events):
            for second in events[i + 1:]:
                if ConflictResolver.conflicting(first, second):
                    return False

        return True
