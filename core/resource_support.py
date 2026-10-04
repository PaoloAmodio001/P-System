from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from core.event import Transfer


@dataclass(frozen=True)
class ResourceSupport:
    """
    Semantic resources read or modified by an operation.

    For Transfer, the support consists of:
        - sender balance
        - receiver balance
        - sender nonce
    """

    resources: FrozenSet[str]

    def overlaps(self, other: "ResourceSupport") -> bool:
        return bool(self.resources & other.resources)

    def disjoint(self, other: "ResourceSupport") -> bool:
        return not self.overlaps(other)

    def __contains__(self, resource: str) -> bool:
        return resource in self.resources

    def __len__(self) -> int:
        return len(self.resources)


def transfer_resource_support(event: Transfer) -> ResourceSupport:
    """
    Return the complete semantic resource support of a Transfer.

    Event identity is intentionally excluded: it identifies the event,
    but it is not a mutable state resource used by transfer execution.
    """
    return ResourceSupport(
        resources=frozenset(
            {
                f"balance:{event.sender}",
                f"balance:{event.receiver}",
                f"nonce:{event.sender}",
            }
        )
    )
