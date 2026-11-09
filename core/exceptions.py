"""Custom exceptions used by P-System."""


class SupplyViolation(Exception):
    """Event transfer would violate the asset-supply conservation invariant.

    Args:
        violated: mapping of owner -> amount taken beyond their declared supply,
                   or any field whose value changed unexpectedly.
        delta: net change in the affected account(s) caused by the event.
    """

    def __init__(self, violated: dict[str, int] | None = None, delta: int = 0):
        self.violated = violated or {}
        self.delta = delta
        super().__init__(
            f"SUPPLY_CONSERVATION_VIOLATION: {violated} (delta={delta})"
        )
