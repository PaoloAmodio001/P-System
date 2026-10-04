"""Abstract signed-event lifecycle state machine used by the proof model."""
from dataclasses import dataclass
from enum import Enum


class Transition(str, Enum):
    RECEIVE = "RECEIVE"
    VERIFY_SIGNATURE = "VERIFY_SIGNATURE"
    REGISTER_CLAIM = "REGISTER_CLAIM"
    AUTHORIZE = "AUTHORIZE"
    EXECUTE = "EXECUTE"
    REJECT = "REJECT"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class AbstractEventState:
    authenticated: bool = False
    identity_bound: bool = False
    authorized: bool = False
    executable: bool = False
    executed: bool = False
    rejected: bool = False
    conflicted: bool = False

    def can_execute(self) -> bool:
        return (
            self.authenticated
            and self.identity_bound
            and self.authorized
            and self.executable
            and not self.rejected
            and not self.conflicted
        )
