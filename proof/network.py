"""Network-model helpers and explicit security scope."""
from dataclasses import dataclass
from enum import Enum


class NetworkFault(str, Enum):
    DROP = "DROP"
    DELAY = "DELAY"
    DUPLICATE = "DUPLICATE"
    REORDER = "REORDER"
    PARTITION = "PARTITION"
    RECONNECT = "RECONNECT"


@dataclass(frozen=True)
class NetworkAssumptions:
    authenticated_transport: bool = False
    confidential_transport: bool = False
    eventual_delivery: bool = False
    max_delay_steps: int | None = None


SECURITY_SCOPE = {
    "event_authenticity": "cryptographic signature",
    "identity_binding": "IdentityClaim",
    "authorization": "identity claim + alias binding",
    "transport_integrity": "TLS 1.3 mutual-authenticated transport; covered by P14 real-TLS tests",
    "transport_confidentiality": "TLS 1.3 encrypted transport; covered by P14 real-TLS tests",
}
