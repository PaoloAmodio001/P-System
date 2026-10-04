"""Composable adversarial operations for finite verification."""
from dataclasses import dataclass
from enum import Enum


class AdversarialAction(str, Enum):
    DUPLICATE = "DUPLICATE"
    REORDER = "REORDER"
    DROP = "DROP"
    DELAY = "DELAY"
    FORGE_SIGNATURE = "FORGE_SIGNATURE"
    ALTER_PAYLOAD = "ALTER_PAYLOAD"
    HIDE_RELEVANT_EVENT = "HIDE_RELEVANT_EVENT"
    DELAY_IDENTITY_CLAIM = "DELAY_IDENTITY_CLAIM"
    CONFLICTING_IDENTITY = "CONFLICTING_IDENTITY"
    PARTITION = "PARTITION"
    RECONNECT = "RECONNECT"


@dataclass(frozen=True)
class AdversarialScenario:
    actions: tuple[AdversarialAction, ...]

    def contains(self, action: AdversarialAction) -> bool:
        return action in self.actions
