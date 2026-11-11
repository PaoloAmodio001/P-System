"""
What the parts of quorum mode share: the log, the error of the store, and which events can run.

Quorum mode: docs/FORMAL-SPECIFICATION.md, section 13.1. The model is in formal/lean/PSystem/Quorum.lean.
"""

import logging

from core.event import Transfer


LOG = logging.getLogger("psystem.quorum")


def is_executable_event(event: Transfer) -> bool:
    """The part of executability that no later state can change."""
    return event.amount > 0 and event.sender != event.receiver


class VoteStoreError(Exception):
    """
    The store cannot be trusted or could not record a write.

    Not a ValueError on purpose: a caller must not treat a failure to record as a
    malformed message. No signature may follow it.
    """
