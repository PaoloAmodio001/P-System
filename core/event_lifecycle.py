"""Explicit lifecycle states separating authentication, authorization and execution."""
from enum import Enum


class EventLifecycle(str, Enum):
    RECEIVED = "RECEIVED"
    AUTHENTICATED = "AUTHENTICATED"
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    EXECUTABLE = "EXECUTABLE"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CONFLICTED = "CONFLICTED"


EXECUTABLE_LIFECYCLE_STATES = frozenset({
    EventLifecycle.AUTHORIZED,
    EventLifecycle.EXECUTABLE,
})
