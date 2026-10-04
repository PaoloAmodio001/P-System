from core.decision_engine import DecisionContext
from core.decision_status import DecisionStatus
from core.event import Transfer


def _encode_event(event: Transfer) -> dict:
    return {
        "sender": event.sender,
        "receiver": event.receiver,
        "amount": event.amount,
        "nonce": event.nonce,
        "parents": list(event.parents),
    }


def _decode_event(data: dict) -> Transfer:
    return Transfer(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=data["amount"],
        nonce=data["nonce"],
        parents=tuple(
            data.get("parents", [])
        ),
    )


def encode_decision_context(
    context: DecisionContext,
) -> dict:
    return {
        "type": "DECISION_CONTEXT",
        "status": context.status.value,

        "knowledge": [
            _encode_event(event)
            for event in sorted(
                context.knowledge.events,
                key=lambda event: event.event_id(),
            )
        ],

        "known_events": sorted(
            context.knowledge.event_ids()
        ),

        "potentially_relevant": sorted(
            context.boundary.potentially_relevant
        ),

        "irrelevant": sorted(
            context.boundary.irrelevant
        ),

        "impact_nodes": sorted(
            node.key()
            for node in context.impact.nodes
        ),

        "conflict_events": sorted(
            event.event_id()
            for event in context.conflict.alternatives
        ),
    }


def decode_decision_context(
    message: dict,
) -> dict:
    if message.get("type") != "DECISION_CONTEXT":
        raise ValueError(
            "INVALID DECISION CONTEXT"
        )

    events = frozenset(
        _decode_event(data)
        for data in message.get(
            "knowledge",
            [],
        )
    )

    return {
        "status": DecisionStatus(
            message["status"]
        ),
        "events": events,
        "known_events": frozenset(
            message.get(
                "known_events",
                [],
            )
        ),
        "potentially_relevant": frozenset(
            message.get(
                "potentially_relevant",
                [],
            )
        ),
        "irrelevant": frozenset(
            message.get(
                "irrelevant",
                [],
            )
        ),
        "impact_nodes": frozenset(
            message.get(
                "impact_nodes",
                [],
            )
        ),
        "conflict_events": frozenset(
            message.get(
                "conflict_events",
                [],
            )
        ),
    }


def decode_decision_status(
    message: dict,
) -> DecisionStatus:
    return decode_decision_context(
        message
    )["status"]
