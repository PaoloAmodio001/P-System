from dataclasses import dataclass

from core.event import Transfer
from core.signed_event import SignedTransfer
from core.identity_claim import IdentityClaim


@dataclass(frozen=True)
class KnowledgeDigest:
    """
    Compact representation of the event knowledge held by a node.
    """

    event_ids: frozenset[str]

    @classmethod
    def from_events(
        cls,
        events: list[Transfer] | tuple[Transfer, ...],
    ) -> "KnowledgeDigest":
        return cls(
            event_ids=frozenset(
                event.event_id()
                for event in events
            )
        )

    def missing_from(
        self,
        other: "KnowledgeDigest",
    ) -> frozenset[str]:
        """
        Return events known by this digest but absent from other.
        """

        return (
            self.event_ids
            - other.event_ids
        )

    def merge(
        self,
        other: "KnowledgeDigest",
    ) -> "KnowledgeDigest":
        return KnowledgeDigest(
            event_ids=(
                self.event_ids
                | other.event_ids
            )
        )


@dataclass(frozen=True)
class KnowledgeDigestMessage:
    event_ids: frozenset[str]

    def encode(self) -> dict:
        return {
            "type": "KNOWLEDGE_DIGEST",
            "event_ids": sorted(self.event_ids),
        }

    @classmethod
    def decode(cls, message: dict) -> "KnowledgeDigestMessage":
        if message.get("type") != "KNOWLEDGE_DIGEST":
            raise ValueError("INVALID KNOWLEDGE DIGEST")

        return cls(
            event_ids=frozenset(
                message.get("event_ids", [])
            )
        )


@dataclass(frozen=True)
class KnowledgeRequest:
    event_ids: frozenset[str]

    def encode(self) -> dict:
        return {
            "type": "KNOWLEDGE_REQUEST",
            "event_ids": sorted(
                self.event_ids
            ),
        }

    @classmethod
    def decode(
        cls,
        message: dict,
    ) -> "KnowledgeRequest":

        if message.get("type") != "KNOWLEDGE_REQUEST":
            raise ValueError(
                "INVALID KNOWLEDGE REQUEST"
            )

        return cls(
            event_ids=frozenset(
                message.get(
                    "event_ids",
                    [],
                )
            )
        )


@dataclass(frozen=True)
class KnowledgeResponse:
    identities: tuple[IdentityClaim, ...]
    events: tuple[SignedTransfer, ...]

    def encode(self) -> dict:
        return {
            "type": "KNOWLEDGE_RESPONSE",
            "identities": [
                {
                    "identity_id": claim.identity_id,
                    "alias": claim.alias,
                    "public_key": claim.public_key.hex(),
                    "signature": claim.signature.hex(),
                }
                for claim in self.identities
            ],
            "events": [
                {
                    "transfer": {
                        "sender": event.transfer.sender,
                        "receiver": event.transfer.receiver,
                        "amount": event.transfer.amount,
                        "nonce": event.transfer.nonce,
                        "parents": list(
                            event.transfer.parents
                        ),
                    },
                    "public_key": event.public_key.hex(),
                    "signature": event.signature.hex(),
                }
                for event in self.events
            ],
        }

    @classmethod
    def decode(
        cls,
        message: dict,
    ) -> "KnowledgeResponse":

        if message.get("type") != "KNOWLEDGE_RESPONSE":
            raise ValueError(
                "INVALID KNOWLEDGE RESPONSE"
            )

        identities = tuple(
            IdentityClaim(
                identity_id=data["identity_id"],
                alias=data["alias"],
                public_key=bytes.fromhex(
                    data["public_key"]
                ),
                signature=bytes.fromhex(
                    data["signature"]
                ),
            )
            for data in message.get(
                "identities",
                [],
            )
        )

        events = tuple(
            SignedTransfer(
                transfer=Transfer(
                    sender=data["transfer"]["sender"],
                    receiver=data["transfer"]["receiver"],
                    amount=data["transfer"]["amount"],
                    nonce=data["transfer"]["nonce"],
                    parents=tuple(
                        data["transfer"].get(
                            "parents",
                            [],
                        )
                    ),
                ),
                public_key=bytes.fromhex(
                    data["public_key"]
                ),
                signature=bytes.fromhex(
                    data["signature"]
                ),
            )
            for data in message.get(
                "events",
                [],
            )
        )

        return cls(
            identities=identities,
            events=events,
        )


def build_digest(
    events: list[Transfer] | tuple[Transfer, ...],
) -> KnowledgeDigest:
    return KnowledgeDigest.from_events(
        events
    )


def missing_event_ids(
    local: KnowledgeDigest,
    remote: KnowledgeDigest,
) -> frozenset[str]:
    return remote.missing_from(local)


def select_events(
    events: list[SignedTransfer] | tuple[SignedTransfer, ...],
    requested_ids: frozenset[str] | set[str],
) -> tuple[SignedTransfer, ...]:
    requested = set(requested_ids)

    return tuple(
        event
        for event in events
        if event.transfer.event_id() in requested
    )
