from dataclasses import dataclass


@dataclass
class PeerReconnectState:
    attempts: int = 0
    next_retry: float = 0.0
    last_success: float | None = None
